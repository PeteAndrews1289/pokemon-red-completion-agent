"""Crash-safe title-neutral materialization of one selected-arm causal example.

This is the durable back half between a title adapter's validated setup and the
shared living-Pokedex learner.  It claims a domain-separated logical/physical
successor, commits one CSPRNG behavior draw, resolves only the selected arm
behind a locked controller gate, and records an independently observed outcome
with the exact propensity and action trace.

Pre-input construction may resume only a bounded number of times and only when
the same durable effect meter proves that controller/action/frame counts did not
move.  Once controller authority is durably released, recovery can never execute
again; a missing example becomes a target-free interrupted terminal.

Nothing here knows Red, Crystal, species, maps, ROMs, routes, or emulator APIs.
Those details stay behind the title adapter's selected-arm resolver.
"""

from __future__ import annotations

import math
import re
import secrets
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

from pokemon_red_completion.claim_first_admission import (
    ClaimFirstAdmissionError,
    ClaimFirstRootPair,
    claim_first_pair_registry,
    read_root_pair_claim,
)
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_OUTCOME_NAMES,
    LivingDexCensorReason,
    LivingDexObservedArmExample,
    LivingDexObservedOutcome,
    LivingDexOptionMenu,
    LivingDexOutcomeStatus,
)
from pokemon_red_completion.living_dex_policy_codec import (
    restore_living_dex_policy_menu,
)
from pokemon_red_completion.private_artifacts import (
    CollectionSession,
    PrivateArtifactError,
    PrivateArtifactRoot,
)
from pokemon_red_completion.provenance import canonical_sha256

LIVING_DEX_CAUSAL_IDENTITY_SCHEMA = "pokemon.core.living-dex-causal-identity.v1"
LIVING_DEX_CAUSAL_CLAIM_SCHEMA = "pokemon.core.private-living-dex-causal-claim.v1"
LIVING_DEX_CAUSAL_COMMITMENT_SCHEMA = (
    "pokemon.core.private-living-dex-causal-behavior-commitment.v1"
)
LIVING_DEX_CAUSAL_SELECTION_SCHEMA = (
    "pokemon.core.private-living-dex-causal-behavior-selection.v1"
)
LIVING_DEX_CAUSAL_CONSTRUCTION_START_SCHEMA = (
    "pokemon.core.private-living-dex-causal-construction-start.v1"
)
LIVING_DEX_CAUSAL_CONSTRUCTION_READY_SCHEMA = (
    "pokemon.core.private-living-dex-causal-construction-ready.v1"
)
LIVING_DEX_CAUSAL_EXECUTION_START_SCHEMA = (
    "pokemon.core.private-living-dex-causal-execution-start.v1"
)
LIVING_DEX_CAUSAL_CONTROLLER_RELEASE_SCHEMA = (
    "pokemon.core.private-living-dex-causal-controller-release.v1"
)
LIVING_DEX_CAUSAL_EXAMPLE_SCHEMA = "pokemon.core.private-living-dex-causal-example.v1"
LIVING_DEX_CAUSAL_TERMINAL_SCHEMA = "pokemon.core.private-living-dex-causal-terminal.v1"
LIVING_DEX_CAUSAL_RECEIPT_SCHEMA = "pokemon.core.living-dex-causal-receipt.v1"
LIVING_DEX_CAUSAL_BEHAVIOR_POLICY_SCHEMA = (
    "pokemon.core.living-dex-full-support-behavior-policy.v1"
)
LIVING_DEX_CAUSAL_COLLECTION_ID = "living-dex-causal-example-v1"
LIVING_DEX_CAUSAL_MAXIMUM_CONSTRUCTION_ATTEMPTS = 2
LIVING_DEX_CAUSAL_STORE_ANCHOR_SCHEMA = (
    "pokemon.core.private-living-dex-causal-store-anchor.v1"
)
LIVING_DEX_CAUSAL_STORE_ANCHOR_RECORD_ID = "living-dex-causal-store-anchor-v1"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class LivingDexCausalJournalError(RuntimeError):
    """A causal example cannot be claimed, resumed, or authenticated safely."""


class LivingDexCausalDisposition(StrEnum):
    EXECUTED_SETTLED = "executed_settled"
    EXECUTED_CENSORED = "executed_censored"
    PREINPUT_RETRYABLE = "preinput_retryable"
    RECOVERED_COMPLETE = "recovered_complete"
    RECOVERED_PREINPUT_FAILED = "recovered_preinput_failed"
    RECOVERED_INTERRUPTED = "recovered_interrupted"


class LivingDexCausalTerminalStatus(StrEnum):
    COMPLETE = "complete"
    PREINPUT_FAILED = "preinput_failed"
    POSTRELEASE_INTERRUPTED = "postrelease_interrupted"


@dataclass(frozen=True, slots=True)
class LivingDexCausalEffectCheckpoint:
    """Durable title-adapter effect census used to qualify safe reconstruction."""

    controller_actions: int
    emulator_frames: int

    def __post_init__(self) -> None:
        for value in (self.controller_actions, self.emulator_frames):
            if type(value) is not int or value < 0:  # noqa: E721
                raise LivingDexCausalJournalError("causal effect checkpoint differs")

    def private_dict(self) -> dict[str, int]:
        return {
            "controller_actions": self.controller_actions,
            "emulator_frames": self.emulator_frames,
        }

    def delta(self, after: LivingDexCausalEffectCheckpoint) -> tuple[int, int]:
        if not isinstance(after, LivingDexCausalEffectCheckpoint):
            raise TypeError("causal effect delta needs a checkpoint")
        actions = after.controller_actions - self.controller_actions
        frames = after.emulator_frames - self.emulator_frames
        if actions < 0 or frames < 0:
            raise LivingDexCausalJournalError("causal effect meter moved backwards")
        return actions, frames


@runtime_checkable
class LivingDexCausalEffectMeter(Protocol):
    """Comprehensive action/frame meter plus its safe-recovery incarnation."""

    @property
    def binding_sha256(self) -> str: ...

    @property
    def recovery_instance_sha256(self) -> str: ...

    def checkpoint(self) -> LivingDexCausalEffectCheckpoint: ...


@dataclass(frozen=True, slots=True)
class LivingDexCausalIdentity:
    """Source, setup, state, menu, observer, and meter identity for one datum."""

    source_commit: str
    partition: str
    lineage_sha256: str
    setup_terminal_sha256: str
    setup_pair_claim_sha256: str
    setup_attestation_sha256: str
    state_sha256: str
    envelope_sha256: str
    menu_sha256: str
    binding_roster_sha256: str
    origin_observation_sha256: str
    observer_binding_sha256: str
    effect_meter_binding_sha256: str
    runner_sha256: str
    repeatable_trial_claim_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_commit, str) or _GIT_COMMIT.fullmatch(
            self.source_commit
        ) is None:
            raise LivingDexCausalJournalError("causal source commit differs")
        if self.partition not in {"train", "development"}:
            raise LivingDexCausalJournalError("causal partition differs")
        for value, subject in (
            (self.lineage_sha256, "lineage"),
            (self.setup_terminal_sha256, "setup terminal"),
            (self.setup_pair_claim_sha256, "setup pair claim"),
            (self.setup_attestation_sha256, "setup attestation"),
            (self.state_sha256, "state"),
            (self.envelope_sha256, "envelope"),
            (self.menu_sha256, "menu"),
            (self.binding_roster_sha256, "binding roster"),
            (self.origin_observation_sha256, "origin observation"),
            (self.observer_binding_sha256, "observer binding"),
            (self.effect_meter_binding_sha256, "effect meter binding"),
            (self.runner_sha256, "runner"),
        ):
            _require_sha256(value, subject=subject)
        if self.repeatable_trial_claim_sha256 is not None:
            _require_sha256(
                self.repeatable_trial_claim_sha256,
                subject="repeatable trial claim",
            )

    @property
    def identity_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    @property
    def logical_root_sha256(self) -> str:
        base = canonical_sha256(
            {
                "lineage_sha256": self.lineage_sha256,
                "menu_sha256": self.menu_sha256,
                "partition": self.partition,
                "purpose": "one-selected-arm-causal-example",
                "schema": "pokemon.core.living-dex-causal-logical-root.v1",
                "setup_attestation_sha256": self.setup_attestation_sha256,
                "setup_pair_claim_sha256": self.setup_pair_claim_sha256,
                "setup_terminal_sha256": self.setup_terminal_sha256,
            }
        )
        if self.repeatable_trial_claim_sha256 is None:
            return base
        return canonical_sha256(
            {
                "base_logical_root_sha256": base,
                "repeatable_trial_claim_sha256": (
                    self.repeatable_trial_claim_sha256
                ),
                "schema": (
                    "pokemon.core.living-dex-causal-repeatable-logical-instance.v1"
                ),
            }
        )

    @property
    def physical_root_sha256(self) -> str:
        """Collide bytes unless an explicit preregistered reset owns the trial."""

        base = canonical_sha256(
            {
                "envelope_sha256": self.envelope_sha256,
                "purpose": "one-selected-arm-causal-example",
                "schema": "pokemon.core.living-dex-causal-physical-root.v1",
                "state_sha256": self.state_sha256,
            }
        )
        if self.repeatable_trial_claim_sha256 is None:
            return base
        return canonical_sha256(
            {
                "base_physical_root_sha256": base,
                "repeatable_trial_claim_sha256": (
                    self.repeatable_trial_claim_sha256
                ),
                "schema": (
                    "pokemon.core.living-dex-causal-repeatable-physical-instance.v1"
                ),
            }
        )

    @property
    def plan_sha256(self) -> str:
        return canonical_sha256(
            {
                "binding_roster_sha256": self.binding_roster_sha256,
                "identity_sha256": self.identity_sha256,
                "menu_sha256": self.menu_sha256,
                "observer_binding_sha256": self.observer_binding_sha256,
                "schema": "pokemon.core.living-dex-causal-plan.v1",
            }
        )

    def pair_claim_for_store(self, store_anchor_sha256: str) -> ClaimFirstRootPair:
        anchor = _require_sha256(store_anchor_sha256, subject="store anchor")
        return ClaimFirstRootPair(
            logical_root_sha256=self.logical_root_sha256,
            physical_root_sha256=self.physical_root_sha256,
            stage="causal-example",
            execution_identity_sha256=canonical_sha256(
                {
                    "causal_identity_sha256": self.identity_sha256,
                    "schema": "pokemon.core.living-dex-causal-store-execution.v1",
                    "store_anchor_sha256": anchor,
                }
            ),
            plan_sha256=canonical_sha256(
                {
                    "causal_plan_sha256": self.plan_sha256,
                    "schema": "pokemon.core.living-dex-causal-store-plan.v1",
                    "store_anchor_sha256": anchor,
                }
            ),
            slot_sha256=self.setup_terminal_sha256,
            runner_sha256=self.runner_sha256,
            source_commit=self.source_commit,
        )

    def private_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "binding_roster_sha256": self.binding_roster_sha256,
            "effect_meter_binding_sha256": self.effect_meter_binding_sha256,
            "envelope_sha256": self.envelope_sha256,
            "lineage_sha256": self.lineage_sha256,
            "menu_sha256": self.menu_sha256,
            "observer_binding_sha256": self.observer_binding_sha256,
            "origin_observation_sha256": self.origin_observation_sha256,
            "partition": self.partition,
            "runner_sha256": self.runner_sha256,
            "schema": LIVING_DEX_CAUSAL_IDENTITY_SCHEMA,
            "setup_attestation_sha256": self.setup_attestation_sha256,
            "setup_pair_claim_sha256": self.setup_pair_claim_sha256,
            "setup_terminal_sha256": self.setup_terminal_sha256,
            "source_commit": self.source_commit,
            "state_sha256": self.state_sha256,
        }
        if self.repeatable_trial_claim_sha256 is not None:
            result["repeatable_trial_claim_sha256"] = (
                self.repeatable_trial_claim_sha256
            )
        return result


@dataclass(frozen=True, slots=True)
class LivingDexCausalBehaviorCommitment:
    """One authenticated system-random seed durably bound before selection."""

    causal_identity_sha256: str
    partition: str
    menu_sha256: str
    randomization_seed_sha256: str
    issuance_method: str = field(default="system-csprng-single-draw-v1", init=False)

    def __post_init__(self) -> None:
        for value, subject in (
            (self.causal_identity_sha256, "causal identity"),
            (self.menu_sha256, "behavior menu"),
            (self.randomization_seed_sha256, "behavior seed"),
        ):
            _require_sha256(value, subject=subject)
        if self.partition not in {"train", "development"}:
            raise LivingDexCausalJournalError("behavior partition differs")
        if self.issuance_method != "system-csprng-single-draw-v1":
            raise LivingDexCausalJournalError("behavior issuance differs")

    @property
    def commitment_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    @property
    def probability_seed_sha256(self) -> str:
        return canonical_sha256(
            {
                "commitment_sha256": self.commitment_sha256,
                "purpose": "available-row-rank-weights",
                "schema": LIVING_DEX_CAUSAL_COMMITMENT_SCHEMA,
            }
        )

    @property
    def draw_seed_sha256(self) -> str:
        return canonical_sha256(
            {
                "commitment_sha256": self.commitment_sha256,
                "purpose": "single-weighted-ticket",
                "schema": LIVING_DEX_CAUSAL_COMMITMENT_SCHEMA,
            }
        )

    def private_dict(self) -> dict[str, object]:
        return {
            "causal_identity_sha256": self.causal_identity_sha256,
            "issuance_method": self.issuance_method,
            "menu_sha256": self.menu_sha256,
            "partition": self.partition,
            "randomization_seed_sha256": self.randomization_seed_sha256,
            "schema": LIVING_DEX_CAUSAL_COMMITMENT_SCHEMA,
        }


@dataclass(frozen=True, slots=True)
class LivingDexCausalBehaviorDecision:
    """Complete replayable propensity vector and one selected available row."""

    commitment: LivingDexCausalBehaviorCommitment
    available_indices: tuple[int, ...]
    integer_weights: tuple[int, ...]
    probabilities: tuple[float, ...]
    selected_candidate_index: int

    def __post_init__(self) -> None:
        if not isinstance(self.commitment, LivingDexCausalBehaviorCommitment):
            raise TypeError("causal behavior decision needs its commitment")
        if (
            not isinstance(self.available_indices, tuple)
            or len(self.available_indices) < 2
            or tuple(sorted(set(self.available_indices))) != self.available_indices
            or not isinstance(self.integer_weights, tuple)
            or not isinstance(self.probabilities, tuple)
            or len(self.integer_weights) != len(self.probabilities)
            or any(
                type(item) is not int  # noqa: E721
                or not 0 <= item < len(self.integer_weights)
                for item in self.available_indices
            )
            or any(type(item) is not int or item < 0 for item in self.integer_weights)  # noqa: E721
            or any(
                type(item) is not float or not math.isfinite(item) or item < 0.0  # noqa: E721
                for item in self.probabilities
            )
            or type(self.selected_candidate_index) is not int  # noqa: E721
            or self.selected_candidate_index not in self.available_indices
        ):
            raise LivingDexCausalJournalError("causal behavior decision fields differ")
        total = sum(self.integer_weights)
        if total <= 0 or not math.isclose(
            sum(self.probabilities), 1.0, rel_tol=0.0, abs_tol=1e-12
        ):
            raise LivingDexCausalJournalError("causal behavior distribution differs")
        expected = _behavior_decision_values(
            len(self.integer_weights),
            self.available_indices,
            commitment=self.commitment,
            integer_weights=self.integer_weights,
        )
        if (
            self.integer_weights != expected[0]
            or self.probabilities != expected[1]
            or self.selected_candidate_index != expected[2]
            or any(
                (weight > 0) is (index not in self.available_indices)
                for index, weight in enumerate(self.integer_weights)
            )
        ):
            raise LivingDexCausalJournalError("causal behavior decision does not replay")

    @property
    def selected_probability(self) -> float:
        return self.probabilities[self.selected_candidate_index]

    def private_dict(self) -> dict[str, object]:
        return {
            "available_indices": list(self.available_indices),
            "commitment": self.commitment.private_dict(),
            "commitment_sha256": self.commitment.commitment_sha256,
            "full_support_over_available_options": True,
            "integer_weights": list(self.integer_weights),
            "menu_sha256": self.commitment.menu_sha256,
            "probabilities": list(self.probabilities),
            "schema": LIVING_DEX_CAUSAL_SELECTION_SCHEMA,
            "selected_candidate_index": self.selected_candidate_index,
            "selected_probability": self.selected_probability,
        }


class LivingDexControllerGate:
    """Journal-owned capability token released only after its durable marker."""

    __slots__ = ("_released",)

    def __init__(self) -> None:
        self._released = False

    @property
    def released(self) -> bool:
        return self._released

    def authorize_controller_input(self) -> None:
        if self._released:
            raise LivingDexCausalJournalError("controller gate was already released")
        self._released = True

    def require_released(self) -> None:
        if not self._released:
            raise LivingDexCausalJournalError("controller gate is locked")


@dataclass(frozen=True, slots=True)
class LivingDexCausalResolvedArm:
    """One selected-only runtime binding returned behind the locked gate."""

    binding_sha256: str
    effect_meter: LivingDexCausalEffectMeter
    execute: Callable[[LivingDexControllerGate], object]
    action_trace: Callable[[], Mapping[str, object]]

    def __post_init__(self) -> None:
        _require_sha256(self.binding_sha256, subject="resolved binding")
        if not isinstance(self.effect_meter, LivingDexCausalEffectMeter):
            raise TypeError("resolved arm needs the comprehensive effect meter")
        for value in (self.execute, self.action_trace):
            if not callable(value):
                raise TypeError("resolved arm needs execution and action-trace callables")


@dataclass(frozen=True, slots=True)
class LivingDexCausalObservation:
    """Independent selected-arm outcome plus its private provenance document."""

    outcome: LivingDexObservedOutcome
    provenance: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, LivingDexObservedOutcome):
            raise TypeError("causal observation needs a living-Dex outcome")
        if not isinstance(self.provenance, Mapping):
            raise TypeError("causal observation needs provenance")
        canonical_sha256(self.provenance)


LivingDexCausalArmResolver = Callable[
    [int, LivingDexControllerGate],
    AbstractContextManager[LivingDexCausalResolvedArm],
]
LivingDexCausalObserver = Callable[[], LivingDexCausalObservation]
LivingDexCausalFailpoint = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class LivingDexCausalScenario:
    """Complete frozen title-neutral inputs beside private selected-arm hooks."""

    identity: LivingDexCausalIdentity
    menu: LivingDexOptionMenu
    binding_sha256s: tuple[str, ...]
    origin_observation: Mapping[str, object]
    effect_meter: LivingDexCausalEffectMeter
    resolve_selected: LivingDexCausalArmResolver
    observe_after: LivingDexCausalObserver
    behavior_integer_weights: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, LivingDexCausalIdentity):
            raise TypeError("causal scenario needs its identity")
        self.identity.__post_init__()
        if not isinstance(self.menu, LivingDexOptionMenu):
            raise TypeError("causal scenario needs its policy menu")
        self.menu.__post_init__()
        if (
            not isinstance(self.binding_sha256s, tuple)
            or len(self.binding_sha256s) != len(self.menu.candidates)
            or any(_SHA256.fullmatch(item) is None for item in self.binding_sha256s)
            or len(set(self.binding_sha256s)) != len(self.binding_sha256s)
        ):
            raise LivingDexCausalJournalError("causal binding roster differs")
        if not isinstance(self.origin_observation, Mapping):
            raise TypeError("causal scenario needs its origin observation")
        if not isinstance(self.effect_meter, LivingDexCausalEffectMeter):
            raise TypeError("causal scenario needs its comprehensive effect meter")
        _require_sha256(self.effect_meter.binding_sha256, subject="effect meter binding")
        _require_sha256(
            self.effect_meter.recovery_instance_sha256,
            subject="effect meter recovery instance",
        )
        checkpoint = self.effect_meter.checkpoint()
        if not isinstance(checkpoint, LivingDexCausalEffectCheckpoint):
            raise TypeError("causal scenario meter returned an invalid checkpoint")
        if not callable(self.resolve_selected) or not callable(self.observe_after):
            raise TypeError("causal scenario needs resolver and observer callables")
        if self.behavior_integer_weights is not None:
            _validate_behavior_integer_weights(
                len(self.menu.candidates),
                self.menu.available_indices,
                self.behavior_integer_weights,
            )
        if (
            self.identity.partition not in {"train", "development"}
            or self.identity.menu_sha256 != self.menu.policy_sha256
            or self.identity.binding_roster_sha256
            != canonical_sha256(
                {
                    "binding_sha256s": list(self.binding_sha256s),
                    "schema": "pokemon.core.living-dex-causal-binding-roster.v1",
                }
            )
            or self.identity.origin_observation_sha256
            != canonical_sha256(self.origin_observation)
            or self.identity.effect_meter_binding_sha256
            != self.effect_meter.binding_sha256
        ):
            raise LivingDexCausalJournalError("causal scenario identity join differs")


@dataclass(frozen=True, slots=True)
class LivingDexCausalTerminal:
    """Immutable no-retry terminal for one claimed causal identity."""

    causal_identity_sha256: str
    pair_claim_sha256: str
    status: LivingDexCausalTerminalStatus
    example_sha256: str | None
    reason_code: str | None
    construction_attempts: int
    retry_allowed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        _require_sha256(self.causal_identity_sha256, subject="terminal identity")
        _require_sha256(self.pair_claim_sha256, subject="terminal pair claim")
        if not isinstance(self.status, LivingDexCausalTerminalStatus):
            raise LivingDexCausalJournalError("causal terminal status differs")
        if (
            type(self.construction_attempts) is not int  # noqa: E721
            or not 0
            <= self.construction_attempts
            <= LIVING_DEX_CAUSAL_MAXIMUM_CONSTRUCTION_ATTEMPTS
        ):
            raise LivingDexCausalJournalError("terminal construction census differs")
        if self.status is LivingDexCausalTerminalStatus.COMPLETE:
            _require_sha256(self.example_sha256, subject="terminal example")
            if self.reason_code is not None:
                raise LivingDexCausalJournalError("complete causal terminal has a reason")
        elif (
            self.example_sha256 is not None
            or not isinstance(self.reason_code, str)
            or not self.reason_code
        ):
            raise LivingDexCausalJournalError("noncomplete causal terminal evidence differs")
        if self.retry_allowed:
            raise LivingDexCausalJournalError("causal terminal cannot retry")

    def private_dict(self) -> dict[str, object]:
        return {
            "causal_identity_sha256": self.causal_identity_sha256,
            "construction_attempts": self.construction_attempts,
            "example_sha256": self.example_sha256,
            "pair_claim_sha256": self.pair_claim_sha256,
            "reason_code": self.reason_code,
            "retry_allowed": self.retry_allowed,
            "schema": LIVING_DEX_CAUSAL_TERMINAL_SCHEMA,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class LivingDexCausalReceipt:
    scenario: LivingDexCausalScenario
    disposition: LivingDexCausalDisposition
    construction_attempts: int
    example: LivingDexObservedArmExample | None
    terminal: LivingDexCausalTerminal | None

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, LivingDexCausalScenario):
            raise TypeError("causal receipt needs its scenario")
        if not isinstance(self.disposition, LivingDexCausalDisposition):
            raise LivingDexCausalJournalError("causal receipt disposition differs")
        if (
            type(self.construction_attempts) is not int  # noqa: E721
            or not 0
            <= self.construction_attempts
            <= LIVING_DEX_CAUSAL_MAXIMUM_CONSTRUCTION_ATTEMPTS
        ):
            raise LivingDexCausalJournalError("causal receipt construction census differs")
        if self.example is not None and not isinstance(
            self.example,
            LivingDexObservedArmExample,
        ):
            raise TypeError("causal receipt example differs")
        if self.terminal is not None and not isinstance(
            self.terminal,
            LivingDexCausalTerminal,
        ):
            raise TypeError("causal receipt terminal differs")
        if self.example is not None and (
            self.example.partition != self.scenario.identity.partition
            or self.example.menu.policy_sha256 != self.scenario.menu.policy_sha256
        ):
            raise LivingDexCausalJournalError("causal receipt example join differs")
        if self.terminal is not None and (
            self.terminal.causal_identity_sha256
            != self.scenario.identity.identity_sha256
            or self.terminal.construction_attempts != self.construction_attempts
            or (self.example is None)
            is (self.terminal.example_sha256 is not None)
        ):
            raise LivingDexCausalJournalError("causal receipt terminal join differs")

    @property
    def retry_allowed(self) -> bool:
        return self.disposition is LivingDexCausalDisposition.PREINPUT_RETRYABLE

    def public_dict(self) -> dict[str, object]:
        return {
            "behavior_draws": 1,
            "causal_train_example_recorded": (
                self.example is not None
                and self.example.partition == "train"
                and self.example.outcome.status is LivingDexOutcomeStatus.SETTLED
            ),
            "construction_attempts": self.construction_attempts,
            "controller_release_recorded": self.terminal is not None
            and self.terminal.status
            in {
                LivingDexCausalTerminalStatus.COMPLETE,
                LivingDexCausalTerminalStatus.POSTRELEASE_INTERRUPTED,
            },
            "disposition": self.disposition.value,
            "example_recorded": self.example is not None,
            "identity_fields_public": 0,
            "menu_sha256": self.scenario.menu.policy_sha256,
            "private_path_fields": 0,
            "retry_allowed": self.retry_allowed,
            "schema": LIVING_DEX_CAUSAL_RECEIPT_SCHEMA,
            "selected_candidate_target_only": self.example is not None,
            "teacher_queries": 0,
            "unselected_action_targets": 0,
            "unselected_runtimes_constructed": 0,
        }


@dataclass(frozen=True, slots=True)
class _ConstructionAttempt:
    ordinal: int
    start: dict[str, object]
    ready: dict[str, object] | None
    execution_start: dict[str, object] | None

    @property
    def checkpoint(self) -> LivingDexCausalEffectCheckpoint:
        return _restore_checkpoint(self.start["effect_checkpoint"])


@dataclass(frozen=True, slots=True)
class _StoredExample:
    example: LivingDexObservedArmExample
    record_sha256: str


@dataclass(frozen=True, slots=True)
class LivingDexAuthenticatedCausalExample:
    """One fully joined private causal row for aggregate train-only auditing.

    The lineage and causal identity deliberately have no public serializer.
    Consumers may aggregate them in memory but must never publish either value.
    """

    identity: LivingDexCausalIdentity
    behavior: LivingDexCausalBehaviorDecision
    example: LivingDexObservedArmExample
    terminal: LivingDexCausalTerminal
    example_record_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.identity, LivingDexCausalIdentity):
            raise TypeError("authenticated causal row needs its identity")
        if not isinstance(self.behavior, LivingDexCausalBehaviorDecision):
            raise TypeError("authenticated causal row needs its behavior decision")
        if not isinstance(self.example, LivingDexObservedArmExample):
            raise TypeError("authenticated causal row needs its learner example")
        if not isinstance(self.terminal, LivingDexCausalTerminal):
            raise TypeError("authenticated causal row needs its terminal")
        _require_sha256(self.example_record_sha256, subject="sealed example record")
        if (
            self.identity.identity_sha256
            != self.behavior.commitment.causal_identity_sha256
            or self.behavior.commitment.partition != self.identity.partition
            or self.behavior.commitment.menu_sha256 != self.identity.menu_sha256
            or self.example.partition != self.identity.partition
            or self.example.menu.policy_sha256 != self.identity.menu_sha256
            or self.example.selected_candidate_index
            != self.behavior.selected_candidate_index
            or self.example.behavior_probabilities != self.behavior.probabilities
            or self.terminal.causal_identity_sha256 != self.identity.identity_sha256
            or self.terminal.status is not LivingDexCausalTerminalStatus.COMPLETE
            or self.terminal.example_sha256 != self.example_record_sha256
        ):
            raise LivingDexCausalJournalError(
                "authenticated causal row identity join differs"
            )


def load_living_dex_authenticated_causal_examples(
    store: PrivateArtifactRoot,
    *,
    maximum_examples: int = 100,
    collection_session: CollectionSession | None = None,
) -> tuple[LivingDexAuthenticatedCausalExample, ...]:
    """Read the complete immutable causal-example family without row selection.

    The causal collection lock prevents a writer from changing the denominator
    between manifest inventory and payload authentication.  Every matching
    ``lc-example-<sha256>`` record is retained and joined to its claim,
    commitment, behavior selection, release marker, and no-retry terminal.
    """

    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("causal corpus loading needs a private artifact root")
    if type(maximum_examples) is not int or maximum_examples <= 0:  # noqa: E721
        raise LivingDexCausalJournalError(
            "causal corpus maximum must be a positive integer"
        )
    def load_locked() -> tuple[LivingDexAuthenticatedCausalExample, ...]:
        inventory = store.inventory_sealed_record_metadata(
            record_id_prefix="lc-example-",
            expected_kind="living_dex_causal_example",
            maximum_records=maximum_examples,
        )
        store_anchor_sha256 = _read_store_anchor(store)
        return tuple(
            _load_authenticated_causal_example(
                store,
                record_id=metadata.record_id,
                expected_payload_sha256=metadata.declared_record_sha256,
                expected_manifest_sha256=metadata.manifest_sha256,
                store_anchor_sha256=store_anchor_sha256,
            )
            for metadata in inventory
        )

    if collection_session is not None:
        if not isinstance(collection_session, CollectionSession):
            raise TypeError("causal corpus collection session differs")
        try:
            collection_session.require_store(store)
            return load_locked()
        except PrivateArtifactError as error:
            raise LivingDexCausalJournalError(str(error)) from None

    result: tuple[LivingDexAuthenticatedCausalExample, ...] | None = None
    try:
        with store.collection_session(LIVING_DEX_CAUSAL_COLLECTION_ID):
            result = load_locked()
    except PrivateArtifactError as error:
        raise LivingDexCausalJournalError(str(error)) from None
    if result is None:
        raise AssertionError("causal collection session suppressed an exception")
    return result


def materialize_living_dex_causal_example(
    scenario: LivingDexCausalScenario,
    *,
    store: PrivateArtifactRoot,
    claim_registry: Path,
    failpoint: LivingDexCausalFailpoint | None = None,
) -> LivingDexCausalReceipt:
    """Claim, randomize, execute, and retain one selected-arm causal example.

    The caller may invoke this function again only when it returned a receipt
    whose ``retry_allowed`` property is true, or after an actual interruption.
    Every other recovery state is terminal.  A recovered controller-release
    marker is always censored without reconstructing a runtime.
    """

    if not isinstance(scenario, LivingDexCausalScenario):
        raise TypeError("causal materialization needs a scenario")
    scenario.__post_init__()
    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("causal materialization needs a private artifact root")
    if not isinstance(claim_registry, Path):
        raise TypeError("causal materialization needs a claim registry Path")
    if failpoint is not None and not callable(failpoint):
        raise TypeError("causal materialization failpoint must be callable")

    try:
        with store.collection_session(LIVING_DEX_CAUSAL_COLLECTION_ID):
            store_anchor_sha256 = _ensure_store_anchor(store)
            _trip_failpoint(failpoint, "after_store_anchor")
            pair = _ensure_pair_claim(
                scenario.identity,
                claim_registry,
                store_anchor_sha256=store_anchor_sha256,
            )
            _trip_failpoint(failpoint, "after_pair_claim")
            _ensure_local_claim(
                store,
                scenario,
                pair,
                store_anchor_sha256=store_anchor_sha256,
            )
            _trip_failpoint(failpoint, "after_local_claim")

            commitment = _ensure_behavior_commitment(store, scenario)
            _trip_failpoint(failpoint, "after_behavior_commitment")
            selection = _ensure_behavior_selection(store, scenario, commitment)
            _trip_failpoint(failpoint, "after_behavior_selection")

            attempts = _load_construction_attempts(store, scenario, pair, selection)
            release = _find_controller_release(
                store,
                scenario,
                pair,
                selection,
                attempts,
            )
            stored_example = _find_example(
                store,
                scenario,
                pair,
                selection,
                release,
            )
            terminal = _find_terminal(store, scenario, pair)
            if terminal is not None:
                return _receipt_from_terminal(
                    scenario,
                    pair,
                    attempts,
                    release,
                    stored_example,
                    terminal,
                )
            if stored_example is not None:
                if release is None:
                    raise LivingDexCausalJournalError(
                        "causal example exists without controller release"
                    )
                terminal = _publish_terminal(
                    store,
                    scenario,
                    pair,
                    status=LivingDexCausalTerminalStatus.COMPLETE,
                    example_sha256=stored_example.record_sha256,
                    reason_code=None,
                    construction_attempts=len(attempts),
                )
                _trip_failpoint(failpoint, "after_terminal_publish")
                return LivingDexCausalReceipt(
                    scenario,
                    LivingDexCausalDisposition.RECOVERED_COMPLETE,
                    len(attempts),
                    stored_example.example,
                    terminal,
                )
            if release is not None:
                terminal = _publish_terminal(
                    store,
                    scenario,
                    pair,
                    status=LivingDexCausalTerminalStatus.POSTRELEASE_INTERRUPTED,
                    example_sha256=None,
                    reason_code="controller_released_without_durable_example",
                    construction_attempts=len(attempts),
                )
                _trip_failpoint(failpoint, "after_terminal_publish")
                return LivingDexCausalReceipt(
                    scenario,
                    LivingDexCausalDisposition.RECOVERED_INTERRUPTED,
                    len(attempts),
                    None,
                    terminal,
                )

            if attempts:
                unsafe_reason = _unsafe_preinput_recovery_reason(
                    scenario,
                    attempts[-1],
                )
                if unsafe_reason is not None:
                    terminal = _publish_terminal(
                        store,
                        scenario,
                        pair,
                        status=LivingDexCausalTerminalStatus.PREINPUT_FAILED,
                        example_sha256=None,
                        reason_code=unsafe_reason,
                        construction_attempts=len(attempts),
                    )
                    _trip_failpoint(failpoint, "after_terminal_publish")
                    return LivingDexCausalReceipt(
                        scenario,
                        LivingDexCausalDisposition.RECOVERED_PREINPUT_FAILED,
                        len(attempts),
                        None,
                        terminal,
                    )
            if len(attempts) >= LIVING_DEX_CAUSAL_MAXIMUM_CONSTRUCTION_ATTEMPTS:
                terminal = _publish_terminal(
                    store,
                    scenario,
                    pair,
                    status=LivingDexCausalTerminalStatus.PREINPUT_FAILED,
                    example_sha256=None,
                    reason_code="construction_attempt_budget_exhausted",
                    construction_attempts=len(attempts),
                )
                _trip_failpoint(failpoint, "after_terminal_publish")
                return LivingDexCausalReceipt(
                    scenario,
                    LivingDexCausalDisposition.RECOVERED_PREINPUT_FAILED,
                    len(attempts),
                    None,
                    terminal,
                )
            return _execute_construction_attempt(
                scenario,
                store=store,
                pair=pair,
                selection=selection,
                ordinal=len(attempts) + 1,
                failpoint=failpoint,
            )
    except (ClaimFirstAdmissionError, PrivateArtifactError) as error:
        raise LivingDexCausalJournalError(str(error)) from None
    raise AssertionError("causal collection session suppressed an exception")


def _ensure_pair_claim(
    identity: LivingDexCausalIdentity,
    registry: Path,
    *,
    store_anchor_sha256: str,
) -> ClaimFirstRootPair:
    expected = identity.pair_claim_for_store(store_anchor_sha256)
    try:
        restored = read_root_pair_claim(registry, expected.claim_sha256)
    except ClaimFirstAdmissionError:
        try:
            with claim_first_pair_registry(registry) as transaction:
                restored = transaction.claim(expected)
        except ClaimFirstAdmissionError as claim_error:
            try:
                restored = read_root_pair_claim(registry, expected.claim_sha256)
            except ClaimFirstAdmissionError:
                raise claim_error from None
    if restored != expected:
        raise LivingDexCausalJournalError("causal pair claim differs")
    return restored


def _ensure_store_anchor(store: PrivateArtifactRoot) -> str:
    sealed = store.find_sealed_record(
        LIVING_DEX_CAUSAL_STORE_ANCHOR_RECORD_ID,
        expected_kind="living_dex_causal_store_anchor",
    )
    if sealed is None:
        record = {
            "anchor_secret_hex": secrets.token_hex(32),
            "collection_id": LIVING_DEX_CAUSAL_COLLECTION_ID,
            "schema": LIVING_DEX_CAUSAL_STORE_ANCHOR_SCHEMA,
        }
        sealed = store.publish_sealed_record(
            LIVING_DEX_CAUSAL_STORE_ANCHOR_RECORD_ID,
            kind="living_dex_causal_store_anchor",
            record=record,
        )
    return _restore_store_anchor_sha256(sealed.read())


def _read_store_anchor(store: PrivateArtifactRoot) -> str:
    sealed = store.find_sealed_record(
        LIVING_DEX_CAUSAL_STORE_ANCHOR_RECORD_ID,
        expected_kind="living_dex_causal_store_anchor",
    )
    if sealed is None:
        raise LivingDexCausalJournalError("causal store anchor is absent")
    return _restore_store_anchor_sha256(sealed.read())


def _restore_store_anchor_sha256(document: Mapping[str, object]) -> str:
    _exact_keys(
        document,
        {"anchor_secret_hex", "collection_id", "schema"},
        subject="causal store anchor",
    )
    if (
        document["schema"] != LIVING_DEX_CAUSAL_STORE_ANCHOR_SCHEMA
        or document["collection_id"] != LIVING_DEX_CAUSAL_COLLECTION_ID
        or not isinstance(document["anchor_secret_hex"], str)
        or _SHA256.fullmatch(document["anchor_secret_hex"]) is None
    ):
        raise LivingDexCausalJournalError("causal store anchor differs")
    return canonical_sha256(document)


def _ensure_local_claim(
    store: PrivateArtifactRoot,
    scenario: LivingDexCausalScenario,
    pair: ClaimFirstRootPair,
    *,
    store_anchor_sha256: str,
) -> None:
    record = {
        "causal_identity": scenario.identity.private_dict(),
        "causal_identity_sha256": scenario.identity.identity_sha256,
        "pair_claim": pair.private_dict(),
        "pair_claim_sha256": pair.claim_sha256,
        "schema": LIVING_DEX_CAUSAL_CLAIM_SCHEMA,
        "store_anchor_sha256": store_anchor_sha256,
    }
    _publish_exact(
        store,
        _record_id("claim", scenario.identity.identity_sha256),
        kind="living_dex_causal_claim",
        record=record,
    )


def _ensure_behavior_commitment(
    store: PrivateArtifactRoot,
    scenario: LivingDexCausalScenario,
) -> LivingDexCausalBehaviorCommitment:
    record_id = _record_id("commit", scenario.identity.identity_sha256)
    sealed = store.find_sealed_record(
        record_id,
        expected_kind="living_dex_causal_commitment",
    )
    if sealed is None:
        commitment = LivingDexCausalBehaviorCommitment(
            scenario.identity.identity_sha256,
            scenario.identity.partition,
            scenario.menu.policy_sha256,
            secrets.token_hex(32),
        )
        sealed = store.publish_sealed_record(
            record_id,
            kind="living_dex_causal_commitment",
            record=commitment.private_dict(),
        )
    commitment = _restore_behavior_commitment(sealed.read())
    if (
        commitment.causal_identity_sha256 != scenario.identity.identity_sha256
        or commitment.partition != scenario.identity.partition
        or commitment.menu_sha256 != scenario.menu.policy_sha256
    ):
        raise LivingDexCausalJournalError("stored causal behavior commitment differs")
    return commitment


def _ensure_behavior_selection(
    store: PrivateArtifactRoot,
    scenario: LivingDexCausalScenario,
    commitment: LivingDexCausalBehaviorCommitment,
) -> LivingDexCausalBehaviorDecision:
    expected_values = _behavior_decision_values(
        len(scenario.menu.candidates),
        scenario.menu.available_indices,
        commitment=commitment,
        integer_weights=scenario.behavior_integer_weights,
    )
    expected = LivingDexCausalBehaviorDecision(
        commitment,
        scenario.menu.available_indices,
        *expected_values,
    )
    record_id = _record_id("select", scenario.identity.identity_sha256)
    sealed = store.find_sealed_record(
        record_id,
        expected_kind="living_dex_causal_selection",
    )
    if sealed is None:
        sealed = store.publish_sealed_record(
            record_id,
            kind="living_dex_causal_selection",
            record=expected.private_dict(),
        )
    restored = _restore_behavior_decision(sealed.read())
    if restored != expected:
        raise LivingDexCausalJournalError("stored causal behavior selection differs")
    return restored


def _behavior_decision_values(
    candidate_count: int,
    available_indices: Sequence[int],
    *,
    commitment: LivingDexCausalBehaviorCommitment,
    integer_weights: Sequence[int] | None = None,
) -> tuple[tuple[int, ...], tuple[float, ...], int]:
    if type(candidate_count) is not int or candidate_count < 2:  # noqa: E721
        raise LivingDexCausalJournalError("causal behavior candidate census differs")
    available = tuple(available_indices)
    if (
        len(available) < 2
        or tuple(sorted(set(available))) != available
        or any(
            type(index) is not int or not 0 <= index < candidate_count  # noqa: E721
            for index in available
        )
    ):
        raise LivingDexCausalJournalError("causal behavior availability differs")
    if not isinstance(commitment, LivingDexCausalBehaviorCommitment):
        raise TypeError("causal behavior replay needs its commitment")
    weights = (
        tuple(1 if index in available else 0 for index in range(candidate_count))
        if integer_weights is None
        else _validate_behavior_integer_weights(
            candidate_count,
            available,
            integer_weights,
        )
    )
    total = sum(weights)
    probabilities = tuple(weight / total for weight in weights)
    ticket = int(commitment.draw_seed_sha256, 16) % total
    cumulative = 0
    selected: int | None = None
    for index, weight in enumerate(weights):
        cumulative += weight
        if weight > 0 and ticket < cumulative:
            selected = index
            break
    if selected is None:  # pragma: no cover - guarded by positive exact support
        raise LivingDexCausalJournalError("causal behavior ticket did not resolve")
    return weights, probabilities, selected


def _validate_behavior_integer_weights(
    candidate_count: int,
    available_indices: Sequence[int],
    integer_weights: Sequence[int],
) -> tuple[int, ...]:
    """Return one exact full-support distribution over the available rows."""

    available = tuple(available_indices)
    weights = tuple(integer_weights)
    if (
        len(weights) != candidate_count
        or any(type(weight) is not int or weight < 0 for weight in weights)  # noqa: E721
        or any(
            (weights[index] > 0) is (index not in available)
            for index in range(candidate_count)
        )
    ):
        raise LivingDexCausalJournalError(
            "causal behavior weights lack exact available-row support"
        )
    return weights


def _load_construction_attempts(
    store: PrivateArtifactRoot,
    scenario: LivingDexCausalScenario,
    pair: ClaimFirstRootPair,
    selection: LivingDexCausalBehaviorDecision,
) -> tuple[_ConstructionAttempt, ...]:
    attempts: list[_ConstructionAttempt] = []
    gap_seen = False
    for ordinal in range(1, LIVING_DEX_CAUSAL_MAXIMUM_CONSTRUCTION_ATTEMPTS + 1):
        start_record = _find_stage_record(
            store,
            _attempt_record_id("construct", ordinal, scenario.identity.identity_sha256),
            kind="living_dex_causal_construction_start",
        )
        ready_record = _find_stage_record(
            store,
            _attempt_record_id("ready", ordinal, scenario.identity.identity_sha256),
            kind="living_dex_causal_construction_ready",
        )
        execution_record = _find_stage_record(
            store,
            _attempt_record_id("execute", ordinal, scenario.identity.identity_sha256),
            kind="living_dex_causal_execution_start",
        )
        if start_record is None:
            gap_seen = True
            if ready_record is not None or execution_record is not None:
                raise LivingDexCausalJournalError(
                    "causal construction evidence exists without its start"
                )
            continue
        if gap_seen:
            raise LivingDexCausalJournalError("causal construction attempts are not contiguous")
        _validate_construction_start(
            start_record,
            scenario=scenario,
            pair=pair,
            selection=selection,
            ordinal=ordinal,
        )
        if ready_record is not None:
            _validate_construction_ready(
                ready_record,
                scenario=scenario,
                selection=selection,
                start_record=start_record,
                ordinal=ordinal,
            )
        if execution_record is not None:
            if ready_record is None:
                raise LivingDexCausalJournalError(
                    "causal execution start exists without construction ready"
                )
            _validate_execution_start(
                execution_record,
                scenario=scenario,
                selection=selection,
                ready_record=ready_record,
                ordinal=ordinal,
            )
        attempts.append(
            _ConstructionAttempt(
                ordinal,
                start_record,
                ready_record,
                execution_record,
            )
        )
    return tuple(attempts)


def _unsafe_preinput_recovery_reason(
    scenario: LivingDexCausalScenario,
    attempt: _ConstructionAttempt,
) -> str | None:
    if scenario.effect_meter.binding_sha256 != scenario.identity.effect_meter_binding_sha256:
        return "effect_meter_binding_changed_before_recovery"
    if (
        scenario.effect_meter.recovery_instance_sha256
        != attempt.start["effect_meter_recovery_instance_sha256"]
    ):
        return "effect_meter_instance_changed_before_recovery"
    if scenario.effect_meter.checkpoint() != attempt.checkpoint:
        return "protected_effect_changed_before_recovery"
    return None


def _execute_construction_attempt(
    scenario: LivingDexCausalScenario,
    *,
    store: PrivateArtifactRoot,
    pair: ClaimFirstRootPair,
    selection: LivingDexCausalBehaviorDecision,
    ordinal: int,
    failpoint: LivingDexCausalFailpoint | None,
) -> LivingDexCausalReceipt:
    before = scenario.effect_meter.checkpoint()
    start_record = {
        "attempt": ordinal,
        "behavior_selection_sha256": canonical_sha256(selection.private_dict()),
        "causal_identity_sha256": scenario.identity.identity_sha256,
        "effect_checkpoint": before.private_dict(),
        "effect_meter_binding_sha256": scenario.effect_meter.binding_sha256,
        "effect_meter_recovery_instance_sha256": (
            scenario.effect_meter.recovery_instance_sha256
        ),
        "pair_claim_sha256": pair.claim_sha256,
        "schema": LIVING_DEX_CAUSAL_CONSTRUCTION_START_SCHEMA,
    }
    _publish_exact(
        store,
        _attempt_record_id("construct", ordinal, scenario.identity.identity_sha256),
        kind="living_dex_causal_construction_start",
        record=start_record,
    )
    _trip_failpoint(failpoint, "after_construction_start")

    gate = LivingDexControllerGate()
    released = False
    published_example: _StoredExample | None = None
    try:
        with scenario.resolve_selected(selection.selected_candidate_index, gate) as arm:
            _validate_resolved_arm(
                scenario,
                selection=selection,
                arm=arm,
                gate=gate,
                before=before,
            )
            ready_record = {
                "attempt": ordinal,
                "causal_identity_sha256": scenario.identity.identity_sha256,
                "construction_start_sha256": canonical_sha256(start_record),
                "effect_checkpoint": before.private_dict(),
                "effect_meter_binding_sha256": scenario.effect_meter.binding_sha256,
                "schema": LIVING_DEX_CAUSAL_CONSTRUCTION_READY_SCHEMA,
                "selected_binding_sha256": arm.binding_sha256,
                "selected_candidate_index": selection.selected_candidate_index,
            }
            _publish_exact(
                store,
                _attempt_record_id("ready", ordinal, scenario.identity.identity_sha256),
                kind="living_dex_causal_construction_ready",
                record=ready_record,
            )
            _trip_failpoint(failpoint, "after_construction_ready")
            _require_exact_checkpoint(scenario.effect_meter, before, subject="construction")

            execution_start = {
                "attempt": ordinal,
                "behavior_selection_sha256": canonical_sha256(selection.private_dict()),
                "causal_identity_sha256": scenario.identity.identity_sha256,
                "construction_ready_sha256": canonical_sha256(ready_record),
                "effect_checkpoint": before.private_dict(),
                "schema": LIVING_DEX_CAUSAL_EXECUTION_START_SCHEMA,
                "selected_binding_sha256": arm.binding_sha256,
                "selected_candidate_index": selection.selected_candidate_index,
            }
            _publish_exact(
                store,
                _attempt_record_id("execute", ordinal, scenario.identity.identity_sha256),
                kind="living_dex_causal_execution_start",
                record=execution_start,
            )
            _trip_failpoint(failpoint, "after_execution_start")
            _require_exact_checkpoint(scenario.effect_meter, before, subject="execution start")

            release_record = {
                "attempt": ordinal,
                "causal_identity_sha256": scenario.identity.identity_sha256,
                "effect_checkpoint": before.private_dict(),
                "execution_start_sha256": canonical_sha256(execution_start),
                "schema": LIVING_DEX_CAUSAL_CONTROLLER_RELEASE_SCHEMA,
                "selected_binding_sha256": arm.binding_sha256,
                "selected_candidate_index": selection.selected_candidate_index,
            }
            _publish_exact(
                store,
                _record_id("release", scenario.identity.identity_sha256),
                kind="living_dex_causal_controller_release",
                record=release_record,
            )
            released = True
            _trip_failpoint(failpoint, "after_controller_release")
            gate.authorize_controller_input()

            execution_status = "returned"
            execution_exception_type: str | None = None
            try:
                arm.execute(gate)
            except Exception as error:
                execution_status = "raised_exception"
                execution_exception_type = type(error).__name__
            after_execution = scenario.effect_meter.checkpoint()
            action_trace, trace_valid = _read_action_trace(arm)
            observation, observer_valid = _observe_selected_outcome(scenario, after_execution)
            if not trace_valid:
                observation = LivingDexCausalObservation(
                    _censored_outcome(LivingDexCensorReason.PROVENANCE_FAILED),
                    {
                        "reason_code": "action_trace_unavailable",
                        "schema": "pokemon.core.private-causal-observation-failure.v1",
                    },
                )
            elif not observer_valid:
                observation = LivingDexCausalObservation(
                    _censored_outcome(LivingDexCensorReason.OBSERVATION_FAILED),
                    observation.provenance,
                )
            after_observation = scenario.effect_meter.checkpoint()
            if after_observation != after_execution:
                observation = LivingDexCausalObservation(
                    _censored_outcome(LivingDexCensorReason.PROVENANCE_FAILED),
                    {
                        "reason_code": "observer_changed_effect_meter",
                        "schema": "pokemon.core.private-causal-observation-failure.v1",
                    },
                )
            published_example = _publish_example(
                store,
                scenario,
                pair=pair,
                selection=selection,
                release_record=release_record,
                selected_binding_sha256=arm.binding_sha256,
                execution_status=execution_status,
                execution_exception_type=execution_exception_type,
                before=before,
                after_execution=after_execution,
                after_observation=after_observation,
                action_trace=action_trace,
                observation=observation,
            )
            _trip_failpoint(failpoint, "after_example_publish")
    except BaseException as error:
        if released:
            _best_effort_postrelease_terminal(
                store,
                scenario,
                pair,
                ordinal=ordinal,
                published_example=published_example,
            )
            raise
        if not isinstance(error, Exception):
            raise
        return _preinput_failure_receipt(
            store,
            scenario,
            pair,
            ordinal=ordinal,
            before=before,
            reason_code=(
                "construction_invariant_failed"
                if isinstance(error, LivingDexCausalJournalError)
                else "construction_failed"
            ),
            failpoint=failpoint,
        )

    if published_example is None:
        raise LivingDexCausalJournalError("causal execution produced no durable example")
    terminal = _publish_terminal(
        store,
        scenario,
        pair,
        status=LivingDexCausalTerminalStatus.COMPLETE,
        example_sha256=published_example.record_sha256,
        reason_code=None,
        construction_attempts=ordinal,
    )
    _trip_failpoint(failpoint, "after_terminal_publish")
    disposition = (
        LivingDexCausalDisposition.EXECUTED_SETTLED
        if published_example.example.outcome.status is LivingDexOutcomeStatus.SETTLED
        else LivingDexCausalDisposition.EXECUTED_CENSORED
    )
    return LivingDexCausalReceipt(
        scenario,
        disposition,
        ordinal,
        published_example.example,
        terminal,
    )


def _validate_resolved_arm(
    scenario: LivingDexCausalScenario,
    *,
    selection: LivingDexCausalBehaviorDecision,
    arm: LivingDexCausalResolvedArm,
    gate: LivingDexControllerGate,
    before: LivingDexCausalEffectCheckpoint,
) -> None:
    if not isinstance(arm, LivingDexCausalResolvedArm):
        raise TypeError("selected causal resolver returned an invalid arm")
    arm.__post_init__()
    if gate.released:
        raise LivingDexCausalJournalError("selected causal resolver released the controller")
    selected = selection.selected_candidate_index
    if arm.binding_sha256 != scenario.binding_sha256s[selected]:
        raise LivingDexCausalJournalError("selected causal resolver changed its binding")
    if arm.effect_meter is not scenario.effect_meter:
        raise LivingDexCausalJournalError("selected causal resolver changed its effect meter")
    _require_exact_checkpoint(arm.effect_meter, before, subject="selected construction")


def _require_exact_checkpoint(
    meter: LivingDexCausalEffectMeter,
    expected: LivingDexCausalEffectCheckpoint,
    *,
    subject: str,
) -> None:
    actual = meter.checkpoint()
    if not isinstance(actual, LivingDexCausalEffectCheckpoint) or actual != expected:
        raise LivingDexCausalJournalError(f"causal {subject} changed protected effects")


def _read_action_trace(
    arm: LivingDexCausalResolvedArm,
) -> tuple[dict[str, object], bool]:
    try:
        trace = arm.action_trace()
        if not isinstance(trace, Mapping):
            raise TypeError("causal action trace differs")
        result = dict(trace)
        canonical_sha256(result)
    except Exception:
        return (
            {
                "reason_code": "action_trace_unavailable",
                "schema": "pokemon.core.private-causal-action-trace-failure.v1",
            },
            False,
        )
    return result, True


def _observe_selected_outcome(
    scenario: LivingDexCausalScenario,
    after_execution: LivingDexCausalEffectCheckpoint,
) -> tuple[LivingDexCausalObservation, bool]:
    try:
        observation = scenario.observe_after()
        if not isinstance(observation, LivingDexCausalObservation):
            raise TypeError("causal observer returned an invalid observation")
        observation.__post_init__()
        provenance = dict(observation.provenance)
        canonical_sha256(provenance)
        observation = LivingDexCausalObservation(observation.outcome, provenance)
    except Exception as error:
        return (
            LivingDexCausalObservation(
                _censored_outcome(LivingDexCensorReason.OBSERVATION_FAILED),
                {
                    "exception_type": type(error).__name__,
                    "reason_code": "observer_failed",
                    "schema": "pokemon.core.private-causal-observation-failure.v1",
                },
            ),
            False,
        )
    if scenario.effect_meter.checkpoint() != after_execution:
        return (
            LivingDexCausalObservation(
                _censored_outcome(LivingDexCensorReason.PROVENANCE_FAILED),
                {
                    "reason_code": "observer_changed_effect_meter",
                    "schema": "pokemon.core.private-causal-observation-failure.v1",
                },
            ),
            False,
        )
    return observation, True


def _censored_outcome(reason: LivingDexCensorReason) -> LivingDexObservedOutcome:
    return LivingDexObservedOutcome(
        status=LivingDexOutcomeStatus.CENSORED,
        censor_reason=reason,
    )


def _publish_example(
    store: PrivateArtifactRoot,
    scenario: LivingDexCausalScenario,
    *,
    pair: ClaimFirstRootPair,
    selection: LivingDexCausalBehaviorDecision,
    release_record: Mapping[str, object],
    selected_binding_sha256: str,
    execution_status: str,
    execution_exception_type: str | None,
    before: LivingDexCausalEffectCheckpoint,
    after_execution: LivingDexCausalEffectCheckpoint,
    after_observation: LivingDexCausalEffectCheckpoint,
    action_trace: Mapping[str, object],
    observation: LivingDexCausalObservation,
) -> _StoredExample:
    learner_menu = restore_living_dex_policy_menu(scenario.menu.policy_dict())
    decision_sha256 = canonical_sha256(
        {
            "behavior_selection_sha256": canonical_sha256(selection.private_dict()),
            "causal_identity_sha256": scenario.identity.identity_sha256,
            "controller_release_sha256": canonical_sha256(release_record),
            "schema": "pokemon.core.living-dex-causal-decision.v1",
            "selected_binding_sha256": selected_binding_sha256,
            "selected_candidate_index": selection.selected_candidate_index,
        }
    )
    example = LivingDexObservedArmExample(
        decision_sha256=decision_sha256,
        partition=scenario.identity.partition,
        menu=learner_menu,
        selected_candidate_index=selection.selected_candidate_index,
        behavior_probabilities=selection.probabilities,
        outcome=observation.outcome,
    )
    action_delta, frame_delta = before.delta(after_execution)
    trace_document = dict(action_trace)
    provenance_document = dict(observation.provenance)
    record = {
        "action_trace": trace_document,
        "action_trace_sha256": canonical_sha256(trace_document),
        "after_execution_checkpoint": after_execution.private_dict(),
        "after_observation_checkpoint": after_observation.private_dict(),
        "behavior_selection": selection.private_dict(),
        "behavior_selection_sha256": canonical_sha256(selection.private_dict()),
        "causal_identity_sha256": scenario.identity.identity_sha256,
        "controller_action_delta": action_delta,
        "controller_release_sha256": canonical_sha256(release_record),
        "emulator_frame_delta": frame_delta,
        "example": example.public_dict(),
        "example_sha256": canonical_sha256(example.public_dict()),
        "execution_exception_type": execution_exception_type,
        "execution_status": execution_status,
        "origin_observation": dict(scenario.origin_observation),
        "origin_observation_sha256": canonical_sha256(scenario.origin_observation),
        "outcome_provenance": provenance_document,
        "outcome_provenance_sha256": canonical_sha256(provenance_document),
        "pair_claim_sha256": pair.claim_sha256,
        "schema": LIVING_DEX_CAUSAL_EXAMPLE_SCHEMA,
        "selected_binding_sha256": selected_binding_sha256,
    }
    _publish_exact(
        store,
        _record_id("example", scenario.identity.identity_sha256),
        kind="living_dex_causal_example",
        record=record,
    )
    return _StoredExample(example, canonical_sha256(record))


def _preinput_failure_receipt(
    store: PrivateArtifactRoot,
    scenario: LivingDexCausalScenario,
    pair: ClaimFirstRootPair,
    *,
    ordinal: int,
    before: LivingDexCausalEffectCheckpoint,
    reason_code: str,
    failpoint: LivingDexCausalFailpoint | None,
) -> LivingDexCausalReceipt:
    current = scenario.effect_meter.checkpoint()
    unsafe = current != before or reason_code == "construction_invariant_failed"
    if not unsafe and ordinal < LIVING_DEX_CAUSAL_MAXIMUM_CONSTRUCTION_ATTEMPTS:
        return LivingDexCausalReceipt(
            scenario,
            LivingDexCausalDisposition.PREINPUT_RETRYABLE,
            ordinal,
            None,
            None,
        )
    terminal = _publish_terminal(
        store,
        scenario,
        pair,
        status=LivingDexCausalTerminalStatus.PREINPUT_FAILED,
        example_sha256=None,
        reason_code=(
            "protected_effect_changed_before_release" if current != before else reason_code
        ),
        construction_attempts=ordinal,
    )
    _trip_failpoint(failpoint, "after_terminal_publish")
    return LivingDexCausalReceipt(
        scenario,
        LivingDexCausalDisposition.RECOVERED_PREINPUT_FAILED,
        ordinal,
        None,
        terminal,
    )


def _best_effort_postrelease_terminal(
    store: PrivateArtifactRoot,
    scenario: LivingDexCausalScenario,
    pair: ClaimFirstRootPair,
    *,
    ordinal: int,
    published_example: _StoredExample | None,
) -> None:
    try:
        _publish_terminal(
            store,
            scenario,
            pair,
            status=(
                LivingDexCausalTerminalStatus.COMPLETE
                if published_example is not None
                else LivingDexCausalTerminalStatus.POSTRELEASE_INTERRUPTED
            ),
            example_sha256=(
                None if published_example is None else published_example.record_sha256
            ),
            reason_code=(
                "controller_released_before_example"
                if published_example is None
                else None
            ),
            construction_attempts=ordinal,
        )
    except Exception:
        # Preserve the process-level interruption.  Recovery authenticates the
        # release/example records and seals the same terminal on the next call.
        return


def _find_controller_release(
    store: PrivateArtifactRoot,
    scenario: LivingDexCausalScenario,
    pair: ClaimFirstRootPair,
    selection: LivingDexCausalBehaviorDecision,
    attempts: Sequence[_ConstructionAttempt],
) -> dict[str, object] | None:
    record = _find_stage_record(
        store,
        _record_id("release", scenario.identity.identity_sha256),
        kind="living_dex_causal_controller_release",
    )
    if record is None:
        return None
    _exact_keys(
        record,
        {
            "attempt",
            "causal_identity_sha256",
            "effect_checkpoint",
            "execution_start_sha256",
            "schema",
            "selected_binding_sha256",
            "selected_candidate_index",
        },
        subject="controller release",
    )
    ordinal = _integer(record["attempt"], subject="controller release attempt")
    if not 1 <= ordinal <= len(attempts) or ordinal != len(attempts):
        raise LivingDexCausalJournalError("controller release attempt differs")
    attempt = attempts[ordinal - 1]
    if attempt.execution_start is None:
        raise LivingDexCausalJournalError(
            "controller release exists without execution start"
        )
    selected = selection.selected_candidate_index
    if (
        record["schema"] != LIVING_DEX_CAUSAL_CONTROLLER_RELEASE_SCHEMA
        or record["causal_identity_sha256"] != scenario.identity.identity_sha256
        or record["execution_start_sha256"]
        != canonical_sha256(attempt.execution_start)
        or record["selected_candidate_index"] != selected
        or record["selected_binding_sha256"] != scenario.binding_sha256s[selected]
        or _restore_checkpoint(record["effect_checkpoint"]) != attempt.checkpoint
    ):
        raise LivingDexCausalJournalError("stored controller release differs")
    return record


def _find_example(
    store: PrivateArtifactRoot,
    scenario: LivingDexCausalScenario,
    pair: ClaimFirstRootPair,
    selection: LivingDexCausalBehaviorDecision,
    release: Mapping[str, object] | None,
) -> _StoredExample | None:
    record = _find_stage_record(
        store,
        _record_id("example", scenario.identity.identity_sha256),
        kind="living_dex_causal_example",
    )
    if record is None:
        return None
    if release is None:
        raise LivingDexCausalJournalError("causal example exists without controller release")
    _exact_keys(
        record,
        {
            "action_trace",
            "action_trace_sha256",
            "after_execution_checkpoint",
            "after_observation_checkpoint",
            "behavior_selection",
            "behavior_selection_sha256",
            "causal_identity_sha256",
            "controller_action_delta",
            "controller_release_sha256",
            "emulator_frame_delta",
            "example",
            "example_sha256",
            "execution_exception_type",
            "execution_status",
            "origin_observation",
            "origin_observation_sha256",
            "outcome_provenance",
            "outcome_provenance_sha256",
            "pair_claim_sha256",
            "schema",
            "selected_binding_sha256",
        },
        subject="causal example",
    )
    trace = _mapping(record["action_trace"], subject="causal action trace")
    provenance = _mapping(
        record["outcome_provenance"],
        subject="causal outcome provenance",
    )
    origin = _mapping(record["origin_observation"], subject="causal origin observation")
    behavior_document = _mapping(
        record["behavior_selection"],
        subject="causal behavior selection",
    )
    restored_selection = _restore_behavior_decision(behavior_document)
    after_execution = _restore_checkpoint(record["after_execution_checkpoint"])
    after_observation = _restore_checkpoint(record["after_observation_checkpoint"])
    before = _restore_checkpoint(release["effect_checkpoint"])
    action_delta, frame_delta = before.delta(after_execution)
    example_document = _mapping(record["example"], subject="causal learner example")
    example = _restore_observed_arm_example(example_document)
    selected = selection.selected_candidate_index
    expected_decision_sha256 = canonical_sha256(
        {
            "behavior_selection_sha256": canonical_sha256(selection.private_dict()),
            "causal_identity_sha256": scenario.identity.identity_sha256,
            "controller_release_sha256": canonical_sha256(release),
            "schema": "pokemon.core.living-dex-causal-decision.v1",
            "selected_binding_sha256": scenario.binding_sha256s[selected],
            "selected_candidate_index": selected,
        }
    )
    exception_type = record["execution_exception_type"]
    if exception_type is not None and (
        not isinstance(exception_type, str) or not exception_type
    ):
        raise LivingDexCausalJournalError("causal execution exception type differs")
    if (
        record["schema"] != LIVING_DEX_CAUSAL_EXAMPLE_SCHEMA
        or record["causal_identity_sha256"] != scenario.identity.identity_sha256
        or record["pair_claim_sha256"] != pair.claim_sha256
        or record["controller_release_sha256"] != canonical_sha256(release)
        or restored_selection != selection
        or record["behavior_selection_sha256"]
        != canonical_sha256(selection.private_dict())
        or record["selected_binding_sha256"] != scenario.binding_sha256s[selected]
        or record["origin_observation_sha256"]
        != canonical_sha256(scenario.origin_observation)
        or dict(origin) != dict(scenario.origin_observation)
        or record["action_trace_sha256"] != canonical_sha256(trace)
        or record["outcome_provenance_sha256"] != canonical_sha256(provenance)
        or record["controller_action_delta"] != action_delta
        or record["emulator_frame_delta"] != frame_delta
        or record["execution_status"] not in {"returned", "raised_exception"}
        or (record["execution_status"] == "returned") is (exception_type is not None)
        or record["example_sha256"] != canonical_sha256(example.public_dict())
        or example.public_dict() != dict(example_document)
        or example.decision_sha256 != expected_decision_sha256
        or example.partition != scenario.identity.partition
        or example.menu.policy_sha256 != scenario.menu.policy_sha256
        or example.selected_candidate_index != selected
        or example.behavior_probabilities != selection.probabilities
    ):
        raise LivingDexCausalJournalError("stored causal example differs")
    # A changed observer checkpoint is retained only as censored evidence.
    if (
        after_observation != after_execution
        and example.outcome.status is not LivingDexOutcomeStatus.CENSORED
    ):
        raise LivingDexCausalJournalError("observer side effects became a learning target")
    return _StoredExample(example, canonical_sha256(record))


def _publish_terminal(
    store: PrivateArtifactRoot,
    scenario: LivingDexCausalScenario,
    pair: ClaimFirstRootPair,
    *,
    status: LivingDexCausalTerminalStatus,
    example_sha256: str | None,
    reason_code: str | None,
    construction_attempts: int,
) -> LivingDexCausalTerminal:
    terminal = LivingDexCausalTerminal(
        scenario.identity.identity_sha256,
        pair.claim_sha256,
        status,
        example_sha256,
        reason_code,
        construction_attempts,
    )
    _publish_exact(
        store,
        _record_id("terminal", scenario.identity.identity_sha256),
        kind="living_dex_causal_terminal",
        record=terminal.private_dict(),
    )
    return terminal


def _find_terminal(
    store: PrivateArtifactRoot,
    scenario: LivingDexCausalScenario,
    pair: ClaimFirstRootPair,
) -> LivingDexCausalTerminal | None:
    record = _find_stage_record(
        store,
        _record_id("terminal", scenario.identity.identity_sha256),
        kind="living_dex_causal_terminal",
    )
    if record is None:
        return None
    terminal = _restore_terminal(record)
    if (
        terminal.causal_identity_sha256 != scenario.identity.identity_sha256
        or terminal.pair_claim_sha256 != pair.claim_sha256
    ):
        raise LivingDexCausalJournalError("stored causal terminal differs")
    return terminal


def _load_authenticated_causal_example(
    store: PrivateArtifactRoot,
    *,
    record_id: str,
    expected_payload_sha256: str,
    expected_manifest_sha256: str,
    store_anchor_sha256: str,
) -> LivingDexAuthenticatedCausalExample:
    prefix = "lc-example-"
    if not isinstance(record_id, str) or not record_id.startswith(prefix):
        raise LivingDexCausalJournalError("causal example record identity differs")
    identity_sha256 = _require_sha256(
        record_id.removeprefix(prefix),
        subject="example record identity",
    )
    sealed = store.find_sealed_record(
        record_id,
        expected_kind="living_dex_causal_example",
    )
    if sealed is None:
        raise LivingDexCausalJournalError("causal example record is absent")
    if (
        sealed.summary.record_sha256 != expected_payload_sha256
        or sealed.summary.manifest_sha256 != expected_manifest_sha256
    ):
        raise LivingDexCausalJournalError("causal example inventory changed")
    example_record = sealed.read()

    claim_record = _require_stage_record(
        store,
        _record_id("claim", identity_sha256),
        kind="living_dex_causal_claim",
    )
    identity, pair = _restore_local_claim(
        claim_record,
        identity_sha256=identity_sha256,
        store_anchor_sha256=store_anchor_sha256,
    )
    commitment = _restore_behavior_commitment(
        _require_stage_record(
            store,
            _record_id("commit", identity_sha256),
            kind="living_dex_causal_commitment",
        )
    )
    behavior = _restore_behavior_decision(
        _require_stage_record(
            store,
            _record_id("select", identity_sha256),
            kind="living_dex_causal_selection",
        )
    )
    if (
        behavior.commitment != commitment
        or commitment.causal_identity_sha256 != identity_sha256
        or commitment.partition != identity.partition
        or commitment.menu_sha256 != identity.menu_sha256
    ):
        raise LivingDexCausalJournalError("causal behavior identity join differs")

    release = _require_stage_record(
        store,
        _record_id("release", identity_sha256),
        kind="living_dex_causal_controller_release",
    )
    _validate_authenticated_release(
        store,
        release,
        identity_sha256=identity_sha256,
        behavior=behavior,
    )
    example = _restore_authenticated_example_record(
        example_record,
        identity=identity,
        pair=pair,
        behavior=behavior,
        release=release,
    )
    example_record_sha256 = canonical_sha256(example_record)
    terminal = _restore_terminal(
        _require_stage_record(
            store,
            _record_id("terminal", identity_sha256),
            kind="living_dex_causal_terminal",
        )
    )
    if (
        terminal.causal_identity_sha256 != identity_sha256
        or terminal.pair_claim_sha256 != pair.claim_sha256
        or terminal.status is not LivingDexCausalTerminalStatus.COMPLETE
        or terminal.example_sha256 != example_record_sha256
    ):
        raise LivingDexCausalJournalError("causal terminal example join differs")
    return LivingDexAuthenticatedCausalExample(
        identity,
        behavior,
        example,
        terminal,
        example_record_sha256,
    )


def _require_stage_record(
    store: PrivateArtifactRoot,
    record_id: str,
    *,
    kind: str,
) -> dict[str, object]:
    record = _find_stage_record(store, record_id, kind=kind)
    if record is None:
        raise LivingDexCausalJournalError("required causal record is absent")
    return record


def _restore_local_claim(
    document: Mapping[str, object],
    *,
    identity_sha256: str,
    store_anchor_sha256: str,
) -> tuple[LivingDexCausalIdentity, ClaimFirstRootPair]:
    _exact_keys(
        document,
        {
            "causal_identity",
            "causal_identity_sha256",
            "pair_claim",
            "pair_claim_sha256",
            "schema",
            "store_anchor_sha256",
        },
        subject="causal local claim",
    )
    identity = _restore_causal_identity(
        _mapping(document["causal_identity"], subject="causal identity")
    )
    pair = _restore_claim_first_root_pair(
        _mapping(document["pair_claim"], subject="causal pair claim")
    )
    try:
        expected_pair = identity.pair_claim_for_store(store_anchor_sha256)
    except ClaimFirstAdmissionError as error:
        raise LivingDexCausalJournalError(str(error)) from None
    if (
        document["schema"] != LIVING_DEX_CAUSAL_CLAIM_SCHEMA
        or document["causal_identity_sha256"] != identity_sha256
        or identity.identity_sha256 != identity_sha256
        or document["pair_claim_sha256"] != pair.claim_sha256
        or document["store_anchor_sha256"] != store_anchor_sha256
        or pair != expected_pair
    ):
        raise LivingDexCausalJournalError("causal local claim differs")
    return identity, pair


def _validate_authenticated_release(
    store: PrivateArtifactRoot,
    document: Mapping[str, object],
    *,
    identity_sha256: str,
    behavior: LivingDexCausalBehaviorDecision,
) -> None:
    _exact_keys(
        document,
        {
            "attempt",
            "causal_identity_sha256",
            "effect_checkpoint",
            "execution_start_sha256",
            "schema",
            "selected_binding_sha256",
            "selected_candidate_index",
        },
        subject="authenticated controller release",
    )
    attempt = _integer(document["attempt"], subject="controller release attempt")
    if not 1 <= attempt <= LIVING_DEX_CAUSAL_MAXIMUM_CONSTRUCTION_ATTEMPTS:
        raise LivingDexCausalJournalError("controller release attempt differs")
    _restore_checkpoint(document["effect_checkpoint"])
    selected_binding = _require_sha256(
        document["selected_binding_sha256"],
        subject="released binding",
    )
    released_selected = _integer(
        document["selected_candidate_index"],
        subject="released selected candidate",
    )
    _require_sha256(
        document["execution_start_sha256"],
        subject="released execution start",
    )
    execution = _require_stage_record(
        store,
        _attempt_record_id("execute", attempt, identity_sha256),
        kind="living_dex_causal_execution_start",
    )
    _exact_keys(
        execution,
        {
            "attempt",
            "behavior_selection_sha256",
            "causal_identity_sha256",
            "construction_ready_sha256",
            "effect_checkpoint",
            "schema",
            "selected_binding_sha256",
            "selected_candidate_index",
        },
        subject="authenticated execution start",
    )
    _restore_checkpoint(execution["effect_checkpoint"])
    execution_attempt = _integer(execution["attempt"], subject="execution attempt")
    execution_selected = _integer(
        execution["selected_candidate_index"],
        subject="execution selected candidate",
    )
    _require_sha256(
        execution["construction_ready_sha256"],
        subject="construction ready",
    )
    if (
        document["schema"] != LIVING_DEX_CAUSAL_CONTROLLER_RELEASE_SCHEMA
        or document["causal_identity_sha256"] != identity_sha256
        or document["execution_start_sha256"] != canonical_sha256(execution)
        or released_selected != behavior.selected_candidate_index
        or execution["schema"] != LIVING_DEX_CAUSAL_EXECUTION_START_SCHEMA
        or execution_attempt != attempt
        or execution["behavior_selection_sha256"]
        != canonical_sha256(behavior.private_dict())
        or execution["causal_identity_sha256"] != identity_sha256
        or execution_selected != behavior.selected_candidate_index
        or execution["selected_binding_sha256"] != selected_binding
        or execution["effect_checkpoint"] != document["effect_checkpoint"]
    ):
        raise LivingDexCausalJournalError("authenticated controller release differs")


def _restore_authenticated_example_record(
    document: Mapping[str, object],
    *,
    identity: LivingDexCausalIdentity,
    pair: ClaimFirstRootPair,
    behavior: LivingDexCausalBehaviorDecision,
    release: Mapping[str, object],
) -> LivingDexObservedArmExample:
    _exact_keys(
        document,
        {
            "action_trace",
            "action_trace_sha256",
            "after_execution_checkpoint",
            "after_observation_checkpoint",
            "behavior_selection",
            "behavior_selection_sha256",
            "causal_identity_sha256",
            "controller_action_delta",
            "controller_release_sha256",
            "emulator_frame_delta",
            "example",
            "example_sha256",
            "execution_exception_type",
            "execution_status",
            "origin_observation",
            "origin_observation_sha256",
            "outcome_provenance",
            "outcome_provenance_sha256",
            "pair_claim_sha256",
            "schema",
            "selected_binding_sha256",
        },
        subject="authenticated causal example",
    )
    trace = _mapping(document["action_trace"], subject="causal action trace")
    origin = _mapping(
        document["origin_observation"],
        subject="causal origin observation",
    )
    provenance = _mapping(
        document["outcome_provenance"],
        subject="causal outcome provenance",
    )
    behavior_document = _mapping(
        document["behavior_selection"],
        subject="causal behavior selection",
    )
    restored_behavior = _restore_behavior_decision(behavior_document)
    before = _restore_checkpoint(release["effect_checkpoint"])
    after_execution = _restore_checkpoint(document["after_execution_checkpoint"])
    after_observation = _restore_checkpoint(document["after_observation_checkpoint"])
    action_delta, frame_delta = before.delta(after_execution)
    recorded_action_delta = _integer(
        document["controller_action_delta"],
        subject="controller action delta",
    )
    recorded_frame_delta = _integer(
        document["emulator_frame_delta"],
        subject="emulator frame delta",
    )
    example_document = _mapping(document["example"], subject="causal learner example")
    example = _restore_observed_arm_example(example_document)
    selected = behavior.selected_candidate_index
    expected_decision_sha256 = canonical_sha256(
        {
            "behavior_selection_sha256": canonical_sha256(behavior.private_dict()),
            "causal_identity_sha256": identity.identity_sha256,
            "controller_release_sha256": canonical_sha256(release),
            "schema": "pokemon.core.living-dex-causal-decision.v1",
            "selected_binding_sha256": release["selected_binding_sha256"],
            "selected_candidate_index": selected,
        }
    )
    exception_type = document["execution_exception_type"]
    if exception_type is not None and (
        not isinstance(exception_type, str) or not exception_type
    ):
        raise LivingDexCausalJournalError("causal execution exception type differs")
    if (
        document["schema"] != LIVING_DEX_CAUSAL_EXAMPLE_SCHEMA
        or document["causal_identity_sha256"] != identity.identity_sha256
        or document["pair_claim_sha256"] != pair.claim_sha256
        or document["controller_release_sha256"] != canonical_sha256(release)
        or restored_behavior != behavior
        or document["behavior_selection_sha256"]
        != canonical_sha256(behavior.private_dict())
        or document["selected_binding_sha256"]
        != release["selected_binding_sha256"]
        or document["origin_observation_sha256"] != canonical_sha256(origin)
        or document["origin_observation_sha256"]
        != identity.origin_observation_sha256
        or document["action_trace_sha256"] != canonical_sha256(trace)
        or document["outcome_provenance_sha256"] != canonical_sha256(provenance)
        or recorded_action_delta != action_delta
        or recorded_frame_delta != frame_delta
        or document["execution_status"] not in {"returned", "raised_exception"}
        or (document["execution_status"] == "returned")
        is (exception_type is not None)
        or document["example_sha256"] != canonical_sha256(example.public_dict())
        or example.public_dict() != dict(example_document)
        or example.decision_sha256 != expected_decision_sha256
        or example.partition != identity.partition
        or example.menu.policy_sha256 != identity.menu_sha256
        or example.selected_candidate_index != selected
        or example.behavior_probabilities != behavior.probabilities
    ):
        raise LivingDexCausalJournalError("authenticated causal example differs")
    if (
        after_observation != after_execution
        and example.outcome.status is not LivingDexOutcomeStatus.CENSORED
    ):
        raise LivingDexCausalJournalError("observer side effects became a learning target")
    return example


def _receipt_from_terminal(
    scenario: LivingDexCausalScenario,
    pair: ClaimFirstRootPair,
    attempts: Sequence[_ConstructionAttempt],
    release: Mapping[str, object] | None,
    stored_example: _StoredExample | None,
    terminal: LivingDexCausalTerminal,
) -> LivingDexCausalReceipt:
    del pair
    if terminal.construction_attempts != len(attempts):
        raise LivingDexCausalJournalError("terminal construction census differs")
    if terminal.status is LivingDexCausalTerminalStatus.COMPLETE:
        if (
            release is None
            or stored_example is None
            or terminal.example_sha256 != stored_example.record_sha256
        ):
            raise LivingDexCausalJournalError("complete causal terminal evidence differs")
        return LivingDexCausalReceipt(
            scenario,
            LivingDexCausalDisposition.RECOVERED_COMPLETE,
            len(attempts),
            stored_example.example,
            terminal,
        )
    if stored_example is not None or terminal.example_sha256 is not None:
        raise LivingDexCausalJournalError("failed causal terminal has an example")
    if terminal.status is LivingDexCausalTerminalStatus.POSTRELEASE_INTERRUPTED:
        if release is None:
            raise LivingDexCausalJournalError(
                "post-release terminal lacks controller release"
            )
        disposition = LivingDexCausalDisposition.RECOVERED_INTERRUPTED
    else:
        if release is not None:
            raise LivingDexCausalJournalError(
                "pre-input terminal has controller release"
            )
        disposition = LivingDexCausalDisposition.RECOVERED_PREINPUT_FAILED
    return LivingDexCausalReceipt(
        scenario,
        disposition,
        len(attempts),
        None,
        terminal,
    )


def _validate_construction_start(
    record: Mapping[str, object],
    *,
    scenario: LivingDexCausalScenario,
    pair: ClaimFirstRootPair,
    selection: LivingDexCausalBehaviorDecision,
    ordinal: int,
) -> None:
    _exact_keys(
        record,
        {
            "attempt",
            "behavior_selection_sha256",
            "causal_identity_sha256",
            "effect_checkpoint",
            "effect_meter_binding_sha256",
            "effect_meter_recovery_instance_sha256",
            "pair_claim_sha256",
            "schema",
        },
        subject="construction start",
    )
    _restore_checkpoint(record["effect_checkpoint"])
    _require_sha256(
        record["effect_meter_recovery_instance_sha256"],
        subject="stored effect meter recovery instance",
    )
    if (
        record["schema"] != LIVING_DEX_CAUSAL_CONSTRUCTION_START_SCHEMA
        or record["attempt"] != ordinal
        or record["behavior_selection_sha256"]
        != canonical_sha256(selection.private_dict())
        or record["causal_identity_sha256"] != scenario.identity.identity_sha256
        or record["effect_meter_binding_sha256"]
        != scenario.identity.effect_meter_binding_sha256
        or record["pair_claim_sha256"] != pair.claim_sha256
    ):
        raise LivingDexCausalJournalError("stored construction start differs")


def _validate_construction_ready(
    record: Mapping[str, object],
    *,
    scenario: LivingDexCausalScenario,
    selection: LivingDexCausalBehaviorDecision,
    start_record: Mapping[str, object],
    ordinal: int,
) -> None:
    _exact_keys(
        record,
        {
            "attempt",
            "causal_identity_sha256",
            "construction_start_sha256",
            "effect_checkpoint",
            "effect_meter_binding_sha256",
            "schema",
            "selected_binding_sha256",
            "selected_candidate_index",
        },
        subject="construction ready",
    )
    selected = selection.selected_candidate_index
    if (
        record["schema"] != LIVING_DEX_CAUSAL_CONSTRUCTION_READY_SCHEMA
        or record["attempt"] != ordinal
        or record["causal_identity_sha256"] != scenario.identity.identity_sha256
        or record["construction_start_sha256"] != canonical_sha256(start_record)
        or _restore_checkpoint(record["effect_checkpoint"])
        != _restore_checkpoint(start_record["effect_checkpoint"])
        or record["effect_meter_binding_sha256"]
        != scenario.identity.effect_meter_binding_sha256
        or record["selected_candidate_index"] != selected
        or record["selected_binding_sha256"] != scenario.binding_sha256s[selected]
    ):
        raise LivingDexCausalJournalError("stored construction ready differs")


def _validate_execution_start(
    record: Mapping[str, object],
    *,
    scenario: LivingDexCausalScenario,
    selection: LivingDexCausalBehaviorDecision,
    ready_record: Mapping[str, object],
    ordinal: int,
) -> None:
    _exact_keys(
        record,
        {
            "attempt",
            "behavior_selection_sha256",
            "causal_identity_sha256",
            "construction_ready_sha256",
            "effect_checkpoint",
            "schema",
            "selected_binding_sha256",
            "selected_candidate_index",
        },
        subject="execution start",
    )
    selected = selection.selected_candidate_index
    if (
        record["schema"] != LIVING_DEX_CAUSAL_EXECUTION_START_SCHEMA
        or record["attempt"] != ordinal
        or record["behavior_selection_sha256"]
        != canonical_sha256(selection.private_dict())
        or record["causal_identity_sha256"] != scenario.identity.identity_sha256
        or record["construction_ready_sha256"] != canonical_sha256(ready_record)
        or _restore_checkpoint(record["effect_checkpoint"])
        != _restore_checkpoint(ready_record["effect_checkpoint"])
        or record["selected_candidate_index"] != selected
        or record["selected_binding_sha256"] != scenario.binding_sha256s[selected]
    ):
        raise LivingDexCausalJournalError("stored execution start differs")


def _restore_causal_identity(
    document: Mapping[str, object],
) -> LivingDexCausalIdentity:
    expected_keys = {
        "binding_roster_sha256",
        "effect_meter_binding_sha256",
        "envelope_sha256",
        "lineage_sha256",
        "menu_sha256",
        "observer_binding_sha256",
        "origin_observation_sha256",
        "partition",
        "runner_sha256",
        "schema",
        "setup_attestation_sha256",
        "setup_pair_claim_sha256",
        "setup_terminal_sha256",
        "source_commit",
        "state_sha256",
    }
    if "repeatable_trial_claim_sha256" in document:
        expected_keys.add("repeatable_trial_claim_sha256")
    _exact_keys(
        document,
        expected_keys,
        subject="causal identity",
    )
    if document["schema"] != LIVING_DEX_CAUSAL_IDENTITY_SCHEMA:
        raise LivingDexCausalJournalError("causal identity schema differs")
    identity = LivingDexCausalIdentity(
        source_commit=_string(document["source_commit"], subject="source commit"),
        partition=_string(document["partition"], subject="causal partition"),
        lineage_sha256=_string(document["lineage_sha256"], subject="lineage"),
        setup_terminal_sha256=_string(
            document["setup_terminal_sha256"],
            subject="setup terminal",
        ),
        setup_pair_claim_sha256=_string(
            document["setup_pair_claim_sha256"],
            subject="setup pair claim",
        ),
        setup_attestation_sha256=_string(
            document["setup_attestation_sha256"],
            subject="setup attestation",
        ),
        state_sha256=_string(document["state_sha256"], subject="state"),
        envelope_sha256=_string(document["envelope_sha256"], subject="envelope"),
        menu_sha256=_string(document["menu_sha256"], subject="menu"),
        binding_roster_sha256=_string(
            document["binding_roster_sha256"],
            subject="binding roster",
        ),
        origin_observation_sha256=_string(
            document["origin_observation_sha256"],
            subject="origin observation",
        ),
        observer_binding_sha256=_string(
            document["observer_binding_sha256"],
            subject="observer binding",
        ),
        effect_meter_binding_sha256=_string(
            document["effect_meter_binding_sha256"],
            subject="effect meter binding",
        ),
        runner_sha256=_string(document["runner_sha256"], subject="runner"),
        repeatable_trial_claim_sha256=(
            None
            if "repeatable_trial_claim_sha256" not in document
            else _string(
                document["repeatable_trial_claim_sha256"],
                subject="repeatable trial claim",
            )
        ),
    )
    if identity.private_dict() != dict(document):
        raise LivingDexCausalJournalError("causal identity does not replay")
    return identity


def _restore_claim_first_root_pair(
    document: Mapping[str, object],
) -> ClaimFirstRootPair:
    _exact_keys(
        document,
        {
            "execution_identity_sha256",
            "logical_root_sha256",
            "physical_root_sha256",
            "plan_sha256",
            "runner_sha256",
            "schema",
            "slot_sha256",
            "source_commit",
            "stage",
        },
        subject="causal pair claim",
    )
    try:
        pair = ClaimFirstRootPair(
            logical_root_sha256=_string(
                document["logical_root_sha256"],
                subject="logical root",
            ),
            physical_root_sha256=_string(
                document["physical_root_sha256"],
                subject="physical root",
            ),
            stage=_string(document["stage"], subject="claim stage"),
            execution_identity_sha256=_string(
                document["execution_identity_sha256"],
                subject="execution identity",
            ),
            plan_sha256=_string(document["plan_sha256"], subject="plan"),
            slot_sha256=_string(document["slot_sha256"], subject="slot"),
            runner_sha256=_string(document["runner_sha256"], subject="runner"),
            source_commit=_string(
                document["source_commit"],
                subject="source commit",
            ),
        )
    except ClaimFirstAdmissionError as error:
        raise LivingDexCausalJournalError(str(error)) from None
    if pair.private_dict() != dict(document):
        raise LivingDexCausalJournalError("causal pair claim does not replay")
    return pair


def _restore_behavior_commitment(
    document: Mapping[str, object],
) -> LivingDexCausalBehaviorCommitment:
    _exact_keys(
        document,
        {
            "causal_identity_sha256",
            "issuance_method",
            "menu_sha256",
            "partition",
            "randomization_seed_sha256",
            "schema",
        },
        subject="behavior commitment",
    )
    if document["schema"] != LIVING_DEX_CAUSAL_COMMITMENT_SCHEMA:
        raise LivingDexCausalJournalError("behavior commitment schema differs")
    commitment = LivingDexCausalBehaviorCommitment(
        _string(document["causal_identity_sha256"], subject="causal identity"),
        _string(document["partition"], subject="behavior partition"),
        _string(document["menu_sha256"], subject="behavior menu"),
        _string(document["randomization_seed_sha256"], subject="behavior seed"),
    )
    if commitment.private_dict() != dict(document):
        raise LivingDexCausalJournalError("behavior commitment does not replay")
    return commitment


def _restore_behavior_decision(
    document: Mapping[str, object],
) -> LivingDexCausalBehaviorDecision:
    _exact_keys(
        document,
        {
            "available_indices",
            "commitment",
            "commitment_sha256",
            "full_support_over_available_options",
            "integer_weights",
            "menu_sha256",
            "probabilities",
            "schema",
            "selected_candidate_index",
            "selected_probability",
        },
        subject="behavior selection",
    )
    if (
        document["schema"] != LIVING_DEX_CAUSAL_SELECTION_SCHEMA
        or document["full_support_over_available_options"] is not True
    ):
        raise LivingDexCausalJournalError("behavior selection contract differs")
    commitment_document = _mapping(document["commitment"], subject="behavior commitment")
    commitment = _restore_behavior_commitment(commitment_document)
    available = _integer_tuple(
        document["available_indices"],
        subject="behavior available indices",
    )
    weights = _integer_tuple(document["integer_weights"], subject="behavior weights")
    probabilities = _float_tuple(
        document["probabilities"],
        subject="behavior probabilities",
    )
    decision = LivingDexCausalBehaviorDecision(
        commitment,
        available,
        weights,
        probabilities,
        _integer(document["selected_candidate_index"], subject="selected candidate"),
    )
    if (
        document["commitment_sha256"] != commitment.commitment_sha256
        or document["menu_sha256"] != commitment.menu_sha256
        or document["selected_probability"] != decision.selected_probability
        or decision.private_dict() != dict(document)
    ):
        raise LivingDexCausalJournalError("behavior selection does not replay")
    return decision


def _restore_observed_arm_example(
    document: Mapping[str, object],
) -> LivingDexObservedArmExample:
    _exact_keys(
        document,
        {
            "behavior_probabilities",
            "decision_sha256",
            "menu",
            "menu_sha256",
            "outcome",
            "partition",
            "schema",
            "selected_candidate_index",
            "selected_candidate_target_only",
            "unselected_action_targets",
        },
        subject="learner example",
    )
    if (
        document["schema"]
        != "pokemon.core.living-dex-observed-arm-example.v1"
        or document["selected_candidate_target_only"] is not True
        or document["unselected_action_targets"] != 0
    ):
        raise LivingDexCausalJournalError("learner example contract differs")
    menu_document = _mapping(document["menu"], subject="learner policy menu")
    outcome_document = _mapping(document["outcome"], subject="learner outcome")
    menu = restore_living_dex_policy_menu(menu_document)
    example = LivingDexObservedArmExample(
        decision_sha256=_string(document["decision_sha256"], subject="decision"),
        partition=_string(document["partition"], subject="example partition"),
        menu=menu,
        selected_candidate_index=_integer(
            document["selected_candidate_index"],
            subject="selected candidate",
        ),
        behavior_probabilities=_float_tuple(
            document["behavior_probabilities"],
            subject="behavior probabilities",
        ),
        outcome=_restore_observed_outcome(outcome_document),
    )
    if (
        document["menu_sha256"] != menu.policy_sha256
        or example.public_dict() != dict(document)
    ):
        raise LivingDexCausalJournalError("learner example does not replay")
    return example


def restore_living_dex_observed_arm_example(
    document: Mapping[str, object],
) -> LivingDexObservedArmExample:
    """Validate the typed row only; callers must independently authenticate provenance."""
    return _restore_observed_arm_example(document)


def _restore_observed_outcome(
    document: Mapping[str, object],
) -> LivingDexObservedOutcome:
    _exact_keys(
        document,
        {"censor_reason", "schema", "status", "target_names", "target_values"},
        subject="observed outcome",
    )
    if (
        document["schema"] != "pokemon.core.living-dex-observed-outcome.v1"
        or document["target_names"] != list(LIVING_DEX_OPTION_OUTCOME_NAMES)
    ):
        raise LivingDexCausalJournalError("observed outcome contract differs")
    try:
        status = LivingDexOutcomeStatus(
            _string(document["status"], subject="outcome status")
        )
    except ValueError:
        raise LivingDexCausalJournalError("observed outcome status differs") from None
    if status is LivingDexOutcomeStatus.CENSORED:
        if document["target_values"] is not None:
            raise LivingDexCausalJournalError("censored outcome contains targets")
        try:
            reason = LivingDexCensorReason(
                _string(document["censor_reason"], subject="censor reason")
            )
        except ValueError:
            raise LivingDexCausalJournalError("censor reason differs") from None
        outcome = LivingDexObservedOutcome(status=status, censor_reason=reason)
    else:
        if document["censor_reason"] is not None:
            raise LivingDexCausalJournalError("settled outcome contains a censor reason")
        values = _float_tuple(document["target_values"], subject="outcome targets")
        if len(values) != len(LIVING_DEX_OPTION_OUTCOME_NAMES) or values[0] not in {
            0.0,
            1.0,
        }:
            raise LivingDexCausalJournalError("settled outcome targets differ")
        outcome = LivingDexObservedOutcome(
            status=status,
            verified_success=bool(values[0]),
            completion_gain=values[1],
            dependency_unlock_gain=values[2],
            action_cost=values[3],
            frame_cost=values[4],
            resource_cost=values[5],
            party_cost=values[6],
            storage_cost=values[7],
            irreversible_loss=values[8],
        )
    if outcome.public_dict() != dict(document):
        raise LivingDexCausalJournalError("observed outcome does not replay")
    return outcome


def restore_living_dex_observed_outcome(
    document: Mapping[str, object],
) -> LivingDexObservedOutcome:
    """Strictly restore one title-neutral observed outcome document."""

    if not isinstance(document, Mapping):
        raise TypeError("observed outcome document must be a mapping")
    return _restore_observed_outcome(document)


def _restore_terminal(document: Mapping[str, object]) -> LivingDexCausalTerminal:
    _exact_keys(
        document,
        {
            "causal_identity_sha256",
            "construction_attempts",
            "example_sha256",
            "pair_claim_sha256",
            "reason_code",
            "retry_allowed",
            "schema",
            "status",
        },
        subject="causal terminal",
    )
    if (
        document["schema"] != LIVING_DEX_CAUSAL_TERMINAL_SCHEMA
        or document["retry_allowed"] is not False
    ):
        raise LivingDexCausalJournalError("causal terminal contract differs")
    try:
        status = LivingDexCausalTerminalStatus(
            _string(document["status"], subject="terminal status")
        )
    except ValueError:
        raise LivingDexCausalJournalError("causal terminal status differs") from None
    example_raw = document["example_sha256"]
    reason_raw = document["reason_code"]
    terminal = LivingDexCausalTerminal(
        _string(document["causal_identity_sha256"], subject="terminal identity"),
        _string(document["pair_claim_sha256"], subject="terminal pair claim"),
        status,
        None if example_raw is None else _string(example_raw, subject="terminal example"),
        None if reason_raw is None else _string(reason_raw, subject="terminal reason"),
        _integer(document["construction_attempts"], subject="construction attempts"),
    )
    if terminal.private_dict() != dict(document):
        raise LivingDexCausalJournalError("causal terminal does not replay")
    return terminal


def _restore_checkpoint(value: object) -> LivingDexCausalEffectCheckpoint:
    document = _mapping(value, subject="effect checkpoint")
    _exact_keys(
        document,
        {"controller_actions", "emulator_frames"},
        subject="effect checkpoint",
    )
    checkpoint = LivingDexCausalEffectCheckpoint(
        _integer(document["controller_actions"], subject="controller actions"),
        _integer(document["emulator_frames"], subject="emulator frames"),
    )
    if checkpoint.private_dict() != dict(document):
        raise LivingDexCausalJournalError("effect checkpoint does not replay")
    return checkpoint


def _publish_exact(
    store: PrivateArtifactRoot,
    record_id: str,
    *,
    kind: str,
    record: Mapping[str, object],
) -> None:
    sealed = store.publish_sealed_record(record_id, kind=kind, record=record)
    if sealed.read() != dict(record):
        raise LivingDexCausalJournalError("causal sealed record did not round-trip")


def _find_stage_record(
    store: PrivateArtifactRoot,
    record_id: str,
    *,
    kind: str,
) -> dict[str, object] | None:
    sealed = store.find_sealed_record(record_id, expected_kind=kind)
    if sealed is None:
        return None
    document = sealed.read()
    if not isinstance(document, dict):
        raise LivingDexCausalJournalError("causal sealed record differs")
    return document


def _record_id(stage: str, identity_sha256: str) -> str:
    _require_sha256(identity_sha256, subject="record identity")
    return f"lc-{stage}-{identity_sha256}"


def _attempt_record_id(stage: str, ordinal: int, identity_sha256: str) -> str:
    if type(ordinal) is not int or not 1 <= ordinal <= 9:  # noqa: E721
        raise LivingDexCausalJournalError("causal attempt record ordinal differs")
    _require_sha256(identity_sha256, subject="attempt record identity")
    return f"lc-{stage}{ordinal}-{identity_sha256}"


def _trip_failpoint(
    failpoint: LivingDexCausalFailpoint | None,
    stage: str,
) -> None:
    if failpoint is not None:
        failpoint(stage)


def _exact_keys(
    document: Mapping[str, object],
    expected: set[str],
    *,
    subject: str,
) -> None:
    if not isinstance(document, Mapping) or set(document) != expected:
        raise LivingDexCausalJournalError(f"{subject} fields differ")


def _mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise LivingDexCausalJournalError(f"{subject} differs")
    return value


def _string(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise LivingDexCausalJournalError(f"{subject} differs")
    return value


def _integer(value: object, *, subject: str) -> int:
    if type(value) is not int:  # noqa: E721
        raise LivingDexCausalJournalError(f"{subject} differs")
    return value


def _integer_tuple(value: object, *, subject: str) -> tuple[int, ...]:
    if not isinstance(value, list) or any(type(item) is not int for item in value):  # noqa: E721
        raise LivingDexCausalJournalError(f"{subject} differ")
    return tuple(value)


def _float_tuple(value: object, *, subject: str) -> tuple[float, ...]:
    if not isinstance(value, list) or any(type(item) is not float for item in value):  # noqa: E721
        raise LivingDexCausalJournalError(f"{subject} differ")
    return tuple(value)


def _require_sha256(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise LivingDexCausalJournalError(f"causal {subject} SHA-256 differs")
    return value


__all__ = [
    "LIVING_DEX_CAUSAL_COLLECTION_ID",
    "LIVING_DEX_CAUSAL_MAXIMUM_CONSTRUCTION_ATTEMPTS",
    "LivingDexAuthenticatedCausalExample",
    "LivingDexCausalBehaviorCommitment",
    "LivingDexCausalBehaviorDecision",
    "LivingDexCausalDisposition",
    "LivingDexCausalEffectCheckpoint",
    "LivingDexCausalEffectMeter",
    "LivingDexCausalIdentity",
    "LivingDexCausalJournalError",
    "LivingDexCausalObservation",
    "LivingDexCausalReceipt",
    "LivingDexCausalResolvedArm",
    "LivingDexCausalScenario",
    "LivingDexCausalTerminal",
    "LivingDexCausalTerminalStatus",
    "LivingDexControllerGate",
    "load_living_dex_authenticated_causal_examples",
    "materialize_living_dex_causal_example",
    "restore_living_dex_observed_outcome",
]
