"""Durable materialization of repeatable Red living-Pokedex decisions.

The adapter and collector deliberately own no filesystem authority.  This module
adds the missing outer state machine: validate the whole calibration plan, freeze
one complete menu, durably claim its scenario namespace, issue and synchronize one
behavior commitment, execute only the selected semantic binding, synchronize its
independently observed outcome, and never reopen a claimed scenario.

The private episode namespace is the claim.  A restart recovers an orphan partial
as permanently interrupted, reloads completed examples through exact canonical
records, skips failed or interrupted scenarios, and executes only namespaces that
were never present.  No ROM, emulator, model, or teacher is opened by this module;
those capabilities remain behind the private bindings supplied by the Red adapter.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum

from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCapture,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexCensorReason,
    LivingDexObservedArmExample,
    LivingDexObservedOutcome,
    LivingDexOptionKind,
    LivingDexOutcomeStatus,
)
from pokemon_red_completion.private_artifacts import (
    CollectionSession,
    EpisodeArtifactState,
    PrivateArtifactError,
    PrivateArtifactRoot,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_option_adapter import (
    RedLivingDexAdaptedScenario,
    RedLivingDexOutcomeSnapshot,
)
from pokemon_red_completion.red_living_dex_option_calibration import (
    MINIMUM_DEVELOPMENT_FAMILIES,
    MINIMUM_DEVELOPMENT_LOCATIONS,
    MINIMUM_SETTLED_DEVELOPMENT_EXAMPLES,
    MINIMUM_SETTLED_TRAIN_EXAMPLES,
    MINIMUM_TRAIN_FAMILIES,
    MINIMUM_TRAIN_OPTION_KINDS,
)
from pokemon_red_completion.red_living_dex_option_collector import (
    RedLivingDexBehaviorCommitment,
    RedLivingDexBehaviorDecision,
    RedLivingDexBehaviorIssuance,
    RedLivingDexCollectedExample,
    RedLivingDexCollectionOrigin,
    collect_red_living_dex_observed_arm,
    issue_red_living_dex_behavior_commitment,
    red_living_dex_behavior_decision,
)

RED_LIVING_DEX_MATERIALIZATION_PLAN_SCHEMA = (
    "pokemon.red.living-dex-durable-materialization-plan.v1"
)
RED_LIVING_DEX_MATERIALIZATION_CLAIM_SCHEMA = (
    "pokemon.red.private-living-dex-materialization-claim.v1"
)
RED_LIVING_DEX_MATERIALIZATION_SELECTION_SCHEMA = (
    "pokemon.red.private-living-dex-materialization-selection.v1"
)
RED_LIVING_DEX_MATERIALIZATION_OBSERVATION_SCHEMA = (
    "pokemon.red.private-living-dex-materialization-observation.v1"
)
RED_LIVING_DEX_MATERIALIZATION_RUN_SCHEMA = (
    "pokemon.red.living-dex-durable-materialization-run.v1"
)
RED_LIVING_DEX_MATERIALIZATION_RECEIPT_SCHEMA = (
    "pokemon.red.living-dex-durable-materialization-receipt.v1"
)
RED_LIVING_DEX_MATERIALIZATION_COLLECTION_ID = (
    "red-living-dex-observed-arm-calibration-v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_TERMINAL_STATUSES = frozenset({"complete", "failed", "interrupted"})


class RedLivingDexOptionMaterializerError(RuntimeError):
    """A durable scenario cannot be claimed, replayed, or represented honestly."""


class RedLivingDexMaterializationDisposition(StrEnum):
    """Whether this invocation executed or recovered one durable scenario."""

    EXECUTED_SETTLED = "executed_settled"
    EXECUTED_CENSORED = "executed_censored"
    RECOVERED_COMPLETE = "recovered_complete"
    SKIPPED_FAILED = "skipped_failed"
    SKIPPED_INTERRUPTED = "skipped_interrupted"


class RedLivingDexMaterializationScenarioOrigin(StrEnum):
    """Whether a row is a ROM-free fixture or a byte-verified private capture."""

    SYNTHETIC_REHEARSAL = "synthetic-rehearsal"
    VERIFIED_REPEATABLE_CAPTURE = "verified-repeatable-capture"


def _require_sha256(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexOptionMaterializerError(f"{subject} SHA-256 is invalid")
    return value


@dataclass(frozen=True, slots=True)
class RedLivingDexMaterializationScenario:
    """One already-frozen menu plus its fresh, scenario-bound outcome observer."""

    adapted: RedLivingDexAdaptedScenario
    partition: str
    observer_binding_sha256: str
    observe_after: Callable[[], RedLivingDexOutcomeSnapshot]
    scenario_origin: RedLivingDexMaterializationScenarioOrigin = field(
        default=RedLivingDexMaterializationScenarioOrigin.SYNTHETIC_REHEARSAL,
        init=False,
    )
    checkpoint_binding_sha256: str | None = field(default=None, init=False)
    checkpoint_attestation_sha256: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.adapted, RedLivingDexAdaptedScenario):
            raise TypeError("materialization scenario needs an adapted Red menu")
        if self.partition not in {"train", "development"}:
            raise RedLivingDexOptionMaterializerError(
                "materialization scenario partition differs"
            )
        _require_sha256(self.observer_binding_sha256, subject="observer binding")
        if not callable(self.observe_after):
            raise TypeError("materialization scenario needs an outcome observer")
        if not isinstance(
            self.scenario_origin,
            RedLivingDexMaterializationScenarioOrigin,
        ):
            raise RedLivingDexOptionMaterializerError(
                "materialization scenario origin differs"
            )
        if self.scenario_origin is (
            RedLivingDexMaterializationScenarioOrigin.SYNTHETIC_REHEARSAL
        ):
            if (
                self.checkpoint_binding_sha256 is not None
                or self.checkpoint_attestation_sha256 is not None
            ):
                raise RedLivingDexOptionMaterializerError(
                    "synthetic scenario cannot claim checkpoint authentication"
                )
        else:
            _require_sha256(
                self.checkpoint_binding_sha256,
                subject="checkpoint binding",
            )
            _require_sha256(
                self.checkpoint_attestation_sha256,
                subject="checkpoint attestation",
            )
        available = self.adapted.menu.available_indices
        if len(available) < 3:
            raise RedLivingDexOptionMaterializerError(
                "materialization scenario needs a complete three-row menu"
            )
        if not all(
            self.adapted.ordered_options[index].authenticated_executor
            for index in available
        ):
            raise RedLivingDexOptionMaterializerError(
                "materialization scenario has a synthetic available executor"
            )
        if any(option.consumed for option in self.adapted.ordered_options):
            raise RedLivingDexOptionMaterializerError(
                "materialization scenario contains a consumed option"
            )

    @property
    def scenario_identity_sha256(self) -> str:
        return self.adapted.before.scenario_identity_sha256

    @property
    def episode_id(self) -> str:
        # The full scenario digest is the namespace key.  Menu, partition, or
        # source changes therefore cannot create a retry identity for one root.
        return f"redldx-{self.scenario_identity_sha256}"

    @property
    def materialization_identity_sha256(self) -> str:
        return canonical_sha256(self.private_identity_dict())

    def private_identity_dict(self) -> dict[str, object]:
        return {
            "binding_sha256s": [
                option.binding_sha256 for option in self.adapted.ordered_options
            ],
            "checkpoint_attestation_sha256": self.checkpoint_attestation_sha256,
            "checkpoint_binding_sha256": self.checkpoint_binding_sha256,
            "menu_sha256": self.adapted.menu.policy_sha256,
            "normalization_provenance_sha256": (
                self.adapted.normalization_provenance_sha256
            ),
            "observer_binding_sha256": self.observer_binding_sha256,
            "partition": self.partition,
            "scenario_identity_sha256": self.scenario_identity_sha256,
            "scenario_origin": self.scenario_origin.value,
            "schema": "pokemon.red.private-living-dex-materialization-identity.v1",
        }

    def public_dict(self) -> dict[str, object]:
        available = self.adapted.menu.available_indices
        return {
            "all_available_executors_authenticated": all(
                self.adapted.ordered_options[index].authenticated_executor
                for index in available
            ),
            "available_candidate_count": len(available),
            "available_option_kinds": sorted(
                {
                    self.adapted.menu.candidates[index].features.kind.value
                    for index in available
                }
            ),
            "candidate_count": len(self.adapted.menu.candidates),
            "complete_menu_frozen": True,
            "identity_fields_public": 0,
            "menu_sha256": self.adapted.menu.policy_sha256,
            "observer_bound_privately": True,
            "partition": self.partition,
            "repeatable": self.adapted.before.scenario_repeatable,
            "scenario_origin": self.scenario_origin.value,
            "verified_repeatable_capture": (
                self.scenario_origin
                is RedLivingDexMaterializationScenarioOrigin.VERIFIED_REPEATABLE_CAPTURE
            ),
        }


def red_living_dex_verified_capture_scenario_identity(
    capture: GoalManagerContextCapture,
) -> str:
    """Derive the only scenario identity accepted for one verified capture."""

    if not isinstance(capture, GoalManagerContextCapture):
        raise TypeError("verified Red scenario needs a goal-manager capture")
    return canonical_sha256(
        {
            "capture_id": capture.capture_id,
            "envelope_sha256": capture.envelope_sha256,
            "purpose": "repeatable-living-dex-observed-arm",
            "schema": "pokemon.red.verified-capture-scenario-identity.v1",
            "state_sha256": capture.state_sha256,
        }
    )


def bind_verified_red_living_dex_materialization_scenario(
    capture: GoalManagerContextCapture,
    adapted: RedLivingDexAdaptedScenario,
    *,
    partition: str,
    observer_binding_sha256: str,
    checkpoint_attestation_sha256: str,
    observe_after: Callable[[], RedLivingDexOutcomeSnapshot],
) -> RedLivingDexMaterializationScenario:
    """Bind a menu to bytes authenticated by the established capture opener.

    The separate attestation digest must come from the later private inventory
    proving that this exact capture is repeatable, nonsealed, and unconsumed.
    This factory verifies the byte join; it does not itself inspect that private
    inventory or authorize execution.
    """

    if not isinstance(capture, GoalManagerContextCapture):
        raise TypeError("verified Red scenario needs a goal-manager capture")
    attestation = _require_sha256(
        checkpoint_attestation_sha256,
        subject="checkpoint attestation",
    )
    expected_identity = red_living_dex_verified_capture_scenario_identity(capture)
    if adapted.before.scenario_identity_sha256 != expected_identity:
        raise RedLivingDexOptionMaterializerError(
            "adapted scenario and verified checkpoint bytes differ"
        )
    scenario = RedLivingDexMaterializationScenario(
        adapted,
        partition,
        observer_binding_sha256,
        observe_after,
    )
    object.__setattr__(
        scenario,
        "scenario_origin",
        RedLivingDexMaterializationScenarioOrigin.VERIFIED_REPEATABLE_CAPTURE,
    )
    object.__setattr__(
        scenario,
        "checkpoint_binding_sha256",
        canonical_sha256(
            {
                "capture_id": capture.capture_id,
                "envelope_sha256": capture.envelope_sha256,
                "schema": "pokemon.red.verified-capture-binding.v1",
                "state_sha256": capture.state_sha256,
            }
        ),
    )
    object.__setattr__(
        scenario,
        "checkpoint_attestation_sha256",
        attestation,
    )
    # The public constructor validates the rehearsal representation first.
    # Re-run the complete invariant set after the authenticated capture fields
    # are installed so this factory cannot bypass future origin invariants.
    scenario.__post_init__()
    return scenario


def red_living_dex_observer_provenance_sha256(
    snapshot: RedLivingDexOutcomeSnapshot,
    *,
    observer_binding_sha256: str,
) -> str:
    """Bind every after-state fact to one declared independent observer."""

    if not isinstance(snapshot, RedLivingDexOutcomeSnapshot):
        raise TypeError("observer provenance needs a Red outcome snapshot")
    binding = _require_sha256(observer_binding_sha256, subject="observer binding")
    return canonical_sha256(_snapshot_provenance_payload(snapshot, binding=binding))


def bind_red_living_dex_observer_provenance(
    snapshot: RedLivingDexOutcomeSnapshot,
    *,
    observer_binding_sha256: str,
) -> RedLivingDexOutcomeSnapshot:
    """Return the same immutable snapshot with independently derived provenance."""

    return replace(
        snapshot,
        observer_provenance_sha256=red_living_dex_observer_provenance_sha256(
            snapshot,
            observer_binding_sha256=observer_binding_sha256,
        ),
    )


@dataclass(frozen=True, slots=True)
class RedLivingDexMaterializationPlan:
    """The minimum 8+4 integration plan, frozen before any scenario claim."""

    scenarios: tuple[RedLivingDexMaterializationScenario, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.scenarios, tuple)
            or not self.scenarios
            or any(
                not isinstance(item, RedLivingDexMaterializationScenario)
                for item in self.scenarios
            )
        ):
            raise RedLivingDexOptionMaterializerError(
                "materialization plan needs frozen Red scenarios"
            )
        identities = tuple(item.scenario_identity_sha256 for item in self.scenarios)
        if len(identities) != len(set(identities)):
            raise RedLivingDexOptionMaterializerError(
                "materialization plan repeats a scenario identity"
            )
        origins = {item.scenario_origin for item in self.scenarios}
        if len(origins) != 1:
            raise RedLivingDexOptionMaterializerError(
                "materialization plan mixes rehearsal and verified captures"
            )
        partitions = Counter(item.partition for item in self.scenarios)
        if partitions["train"] < MINIMUM_SETTLED_TRAIN_EXAMPLES:
            raise RedLivingDexOptionMaterializerError(
                "materialization plan lacks eight train scenarios"
            )
        if partitions["development"] < MINIMUM_SETTLED_DEVELOPMENT_EXAMPLES:
            raise RedLivingDexOptionMaterializerError(
                "materialization plan lacks four development scenarios"
            )

        train = tuple(item for item in self.scenarios if item.partition == "train")
        development = tuple(
            item for item in self.scenarios if item.partition == "development"
        )
        train_kinds = _available_kinds(train)
        train_families = _available_family_hashes(train)
        train_locations = _available_location_hashes(train)
        development_families = _available_family_hashes(development)
        development_locations = _available_location_hashes(development)
        if len(train_kinds) < MINIMUM_TRAIN_OPTION_KINDS:
            raise RedLivingDexOptionMaterializerError(
                "materialization plan lacks four genuine train option kinds"
            )
        if len(train_families) < MINIMUM_TRAIN_FAMILIES:
            raise RedLivingDexOptionMaterializerError(
                "materialization plan lacks three train transformation families"
            )
        if len(development_families) < MINIMUM_DEVELOPMENT_FAMILIES:
            raise RedLivingDexOptionMaterializerError(
                "materialization plan lacks four development transformation families"
            )
        if len(development_locations) < MINIMUM_DEVELOPMENT_LOCATIONS:
            raise RedLivingDexOptionMaterializerError(
                "materialization plan lacks four development locations"
            )
        if train_families & development_families:
            raise RedLivingDexOptionMaterializerError(
                "materialization plan train and development families overlap"
            )
        if train_locations & development_locations:
            raise RedLivingDexOptionMaterializerError(
                "materialization plan train and development locations overlap"
            )

    @property
    def plan_sha256(self) -> str:
        return canonical_sha256(
            {
                "scenario_identities": [
                    item.private_identity_dict() for item in self.scenarios
                ],
                "schema": RED_LIVING_DEX_MATERIALIZATION_PLAN_SCHEMA,
            }
        )

    @property
    def verified_capture_plan(self) -> bool:
        return all(
            item.scenario_origin
            is RedLivingDexMaterializationScenarioOrigin.VERIFIED_REPEATABLE_CAPTURE
            for item in self.scenarios
        )

    def public_dict(self) -> dict[str, object]:
        partitions = Counter(item.partition for item in self.scenarios)
        train = tuple(item for item in self.scenarios if item.partition == "train")
        development = tuple(
            item for item in self.scenarios if item.partition == "development"
        )
        train_families = _available_family_hashes(train)
        train_locations = _available_location_hashes(train)
        development_families = _available_family_hashes(development)
        development_locations = _available_location_hashes(development)
        return {
            "available_width_counts": _integer_counter(
                Counter(
                    len(item.adapted.menu.available_indices)
                    for item in self.scenarios
                )
            ),
            "claim_before_randomization": True,
            "development_family_count": len(development_families),
            "development_location_count": len(development_locations),
            "family_overlap": len(train_families & development_families),
            "identity_fields_public": 0,
            "location_overlap": len(train_locations & development_locations),
            "partition_counts": {
                "development": partitions["development"],
                "train": partitions["train"],
            },
            "plan_sha256": self.plan_sha256,
            "scenario_count": len(self.scenarios),
            "scenario_origin": self.scenarios[0].scenario_origin.value,
            "schema": RED_LIVING_DEX_MATERIALIZATION_PLAN_SCHEMA,
            "train_family_count": len(train_families),
            "train_location_count": len(train_locations),
            "train_offered_option_kind_count": len(_available_kinds(train)),
            "verified_capture_plan": self.verified_capture_plan,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexMaterializationReceipt:
    """One path-free terminal, with a decoded example only when one exists."""

    scenario: RedLivingDexMaterializationScenario
    disposition: RedLivingDexMaterializationDisposition
    state: EpisodeArtifactState
    example: RedLivingDexCollectedExample | None
    newly_executed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, RedLivingDexMaterializationScenario):
            raise TypeError("materialization receipt needs its frozen scenario")
        if not isinstance(self.disposition, RedLivingDexMaterializationDisposition):
            raise TypeError("materialization receipt disposition differs")
        if not isinstance(self.state, EpisodeArtifactState):
            raise TypeError("materialization receipt state differs")
        if type(self.newly_executed) is not bool:  # noqa: E721
            raise TypeError("materialization execution flag differs")
        if self.state.episode_id != self.scenario.episode_id:
            raise RedLivingDexOptionMaterializerError(
                "materialization receipt episode identity differs"
            )
        if self.state.status not in _TERMINAL_STATUSES:
            raise RedLivingDexOptionMaterializerError(
                "materialization receipt is not terminal"
            )
        has_example = self.example is not None
        if has_example != (self.state.status == "complete"):
            raise RedLivingDexOptionMaterializerError(
                "materialization receipt target availability differs"
            )
        if self.example is not None and (
            self.example.adapted is not self.scenario.adapted
            or self.example.example.partition != self.scenario.partition
            or self.example.collection_origin is not _collection_origin(self.scenario)
        ):
            raise RedLivingDexOptionMaterializerError(
                "materialization receipt example binding differs"
            )
        if self.state.status == "complete":
            assert self.example is not None
            expected = (
                RedLivingDexMaterializationDisposition.EXECUTED_SETTLED
                if self.newly_executed
                and self.example.example.outcome.status
                is LivingDexOutcomeStatus.SETTLED
                else RedLivingDexMaterializationDisposition.EXECUTED_CENSORED
                if self.newly_executed
                else RedLivingDexMaterializationDisposition.RECOVERED_COMPLETE
            )
            if self.disposition is not expected or self.state.manifest_sha256 is None:
                raise RedLivingDexOptionMaterializerError(
                    "materialization complete disposition differs"
                )
        else:
            expected = (
                RedLivingDexMaterializationDisposition.SKIPPED_FAILED
                if self.state.status == "failed"
                else RedLivingDexMaterializationDisposition.SKIPPED_INTERRUPTED
            )
            if self.disposition is not expected or self.newly_executed:
                raise RedLivingDexOptionMaterializerError(
                    "materialization skipped disposition differs"
                )

    @property
    def settled(self) -> bool:
        return (
            self.example is not None
            and self.example.example.outcome.status is LivingDexOutcomeStatus.SETTLED
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "behavior_commitment_sha256": (
                None
                if self.example is None
                else self.example.behavior.commitment.commitment_sha256
            ),
            "decision_sha256": (
                None if self.example is None else self.example.example.decision_sha256
            ),
            "disposition": self.disposition.value,
            "identity_fields_public": 0,
            "manifest_sha256": self.state.manifest_sha256,
            "menu_sha256": self.scenario.adapted.menu.policy_sha256,
            "newly_executed": self.newly_executed,
            "bound_after_observation_recorded": (
                self.example is not None
                and self.example.after_observer_provenance_sha256 is not None
            ),
            "partition": self.scenario.partition,
            "reason_code": self.state.reason_code,
            "retry_allowed": False,
            "schema": RED_LIVING_DEX_MATERIALIZATION_RECEIPT_SCHEMA,
            "example_recorded": self.example is not None,
            "state": self.state.status,
            "target_recorded": self.settled,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexMaterializationRun:
    """A restart-safe pass over one frozen plan."""

    plan: RedLivingDexMaterializationPlan
    receipts: tuple[RedLivingDexMaterializationReceipt, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.plan, RedLivingDexMaterializationPlan):
            raise TypeError("materialization run needs its plan")
        if (
            not isinstance(self.receipts, tuple)
            or len(self.receipts) != len(self.plan.scenarios)
            or any(
                not isinstance(item, RedLivingDexMaterializationReceipt)
                for item in self.receipts
            )
            or tuple(item.scenario for item in self.receipts) != self.plan.scenarios
        ):
            raise RedLivingDexOptionMaterializerError(
                "materialization run receipt ordering differs"
            )

    @property
    def examples(self) -> tuple[RedLivingDexCollectedExample, ...]:
        return tuple(
            receipt.example
            for receipt in self.receipts
            if receipt.example is not None
        )

    def public_dict(self) -> dict[str, object]:
        dispositions = Counter(item.disposition.value for item in self.receipts)
        return {
            "censored_examples": sum(
                example.example.outcome.status is LivingDexOutcomeStatus.CENSORED
                for example in self.examples
            ),
            "disposition_counts": {
                disposition.value: dispositions[disposition.value]
                for disposition in RedLivingDexMaterializationDisposition
            },
            "examples_available": len(self.examples),
            "identity_fields_public": 0,
            "new_controller_authority_crossings": sum(
                item.newly_executed for item in self.receipts
            ),
            "plan": self.plan.public_dict(),
            "retry_allowed": False,
            "schema": RED_LIVING_DEX_MATERIALIZATION_RUN_SCHEMA,
            "settled_examples": sum(item.settled for item in self.receipts),
            "unselected_capabilities_executed": 0,
        }


def build_red_living_dex_materialization_plan(
    scenarios: Sequence[RedLivingDexMaterializationScenario],
) -> RedLivingDexMaterializationPlan:
    if not isinstance(scenarios, Sequence):
        raise TypeError("materialization scenarios must be a sequence")
    return RedLivingDexMaterializationPlan(tuple(scenarios))


def run_red_living_dex_materialization_plan(
    store: PrivateArtifactRoot,
    plan: RedLivingDexMaterializationPlan,
) -> RedLivingDexMaterializationRun:
    """Execute or recover every plan row, never reopening a claimed namespace."""

    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("materialization needs a validated private artifact root")
    if not isinstance(plan, RedLivingDexMaterializationPlan):
        raise TypeError("materialization needs a frozen plan")
    receipts: list[RedLivingDexMaterializationReceipt] = []
    with store.collection_session(
        RED_LIVING_DEX_MATERIALIZATION_COLLECTION_ID
    ) as session:
        for scenario in plan.scenarios:
            receipts.append(_materialize_scenario(store, session, scenario))
    return RedLivingDexMaterializationRun(plan, tuple(receipts))


def _materialize_scenario(
    store: PrivateArtifactRoot,
    session: CollectionSession,
    scenario: RedLivingDexMaterializationScenario,
) -> RedLivingDexMaterializationReceipt:
    session.require_store(store)
    state = session.inspect_episode(scenario.episode_id)
    if state.status == "partial":
        state = session.recover_interrupted_episode(scenario.episode_id)
    if state.status == "complete":
        return RedLivingDexMaterializationReceipt(
            scenario,
            RedLivingDexMaterializationDisposition.RECOVERED_COMPLETE,
            state,
            _load_complete_example(store, scenario),
            False,
        )
    if state.status == "failed":
        return RedLivingDexMaterializationReceipt(
            scenario,
            RedLivingDexMaterializationDisposition.SKIPPED_FAILED,
            state,
            None,
            False,
        )
    if state.status == "interrupted":
        return RedLivingDexMaterializationReceipt(
            scenario,
            RedLivingDexMaterializationDisposition.SKIPPED_INTERRUPTED,
            state,
            None,
            False,
        )
    if state.status == "invalid":
        raise RedLivingDexOptionMaterializerError(
            "materialization episode cannot be authenticated"
        )
    if state.status != "absent":
        raise RedLivingDexOptionMaterializerError(
            "materialization scenario has an invalid durable state"
        )
    if any(option.consumed for option in scenario.adapted.ordered_options):
        raise RedLivingDexOptionMaterializerError(
            "unclaimed materialization scenario contains a consumed option"
        )

    # begin_episode durably persists the exclusive namespace before returning.
    # It is therefore the scenario claim and must precede the CSPRNG issuer.
    with store.begin_episode(scenario.episode_id) as writer:
        writer.append("claim", _claim_record(scenario), durable=True)
        commitment = issue_red_living_dex_behavior_commitment(
            scenario.adapted,
            partition=scenario.partition,
        )
        if not commitment.authenticated_issuance:
            raise RedLivingDexOptionMaterializerError(
                "materializer issuer returned unauthenticated randomness"
            )
        behavior = red_living_dex_behavior_decision(
            scenario.adapted.menu,
            commitment=commitment,
        )
        # The exact commitment and selected arm are synced before the collector
        # can call the selected executor.
        writer.append(
            "selection",
            _selection_record(scenario, commitment, behavior),
            durable=True,
        )
        observed_snapshots: list[RedLivingDexOutcomeSnapshot] = []
        collected = collect_red_living_dex_observed_arm(
            scenario.adapted,
            commitment=commitment,
            observe_after=lambda: _observe_bound_after(
                scenario,
                observed_snapshots=observed_snapshots,
            ),
        )
        object.__setattr__(
            collected,
            "collection_origin",
            _collection_origin(scenario),
        )
        if collected.behavior != behavior:
            raise RedLivingDexOptionMaterializerError(
                "collector behavior differs from the durable selection"
            )
        consumed = tuple(
            index
            for index, option in enumerate(scenario.adapted.ordered_options)
            if option.consumed
        )
        if consumed != (behavior.selected_candidate_index,):
            raise RedLivingDexOptionMaterializerError(
                "materializer did not consume exactly the selected option"
            )
        writer.append(
            "observation",
            _observation_record(
                scenario,
                observed_snapshots=observed_snapshots,
                collected=collected,
            ),
            durable=True,
        )
        writer.append("outcome", collected.private_dict(), durable=True)
        summary = writer.complete()

    state = EpisodeArtifactState(
        scenario.episode_id,
        "complete",
        manifest_sha256=summary.manifest_sha256,
    )
    disposition = (
        RedLivingDexMaterializationDisposition.EXECUTED_SETTLED
        if collected.example.outcome.status is LivingDexOutcomeStatus.SETTLED
        else RedLivingDexMaterializationDisposition.EXECUTED_CENSORED
    )
    return RedLivingDexMaterializationReceipt(
        scenario,
        disposition,
        state,
        collected,
        True,
    )


def _claim_record(scenario: RedLivingDexMaterializationScenario) -> dict[str, object]:
    available = scenario.adapted.menu.available_indices
    return {
        "all_available_executors_authenticated": all(
            scenario.adapted.ordered_options[index].authenticated_executor
            for index in available
        ),
        "available_indices": list(available),
        "binding_sha256s": [
            option.binding_sha256 for option in scenario.adapted.ordered_options
        ],
        "checkpoint_attestation_sha256": scenario.checkpoint_attestation_sha256,
        "checkpoint_binding_sha256": scenario.checkpoint_binding_sha256,
        "complete_menu_frozen_before_claim": True,
        "materialization_identity_sha256": (
            scenario.materialization_identity_sha256
        ),
        "menu_sha256": scenario.adapted.menu.policy_sha256,
        "normalization_provenance_sha256": (
            scenario.adapted.normalization_provenance_sha256
        ),
        "observer_binding_sha256": scenario.observer_binding_sha256,
        "partition": scenario.partition,
        "scenario_identity_sha256": scenario.scenario_identity_sha256,
        "scenario_origin": scenario.scenario_origin.value,
        "schema": RED_LIVING_DEX_MATERIALIZATION_CLAIM_SCHEMA,
    }


def _selection_record(
    scenario: RedLivingDexMaterializationScenario,
    commitment: RedLivingDexBehaviorCommitment,
    behavior: RedLivingDexBehaviorDecision,
) -> dict[str, object]:
    selected = scenario.adapted.ordered_options[behavior.selected_candidate_index]
    return {
        "behavior": behavior.public_dict(),
        "commitment": commitment.private_dict(),
        "commitment_sha256": commitment.commitment_sha256,
        "materialization_identity_sha256": (
            scenario.materialization_identity_sha256
        ),
        "observer_binding_sha256": scenario.observer_binding_sha256,
        "schema": RED_LIVING_DEX_MATERIALIZATION_SELECTION_SCHEMA,
        "selected_binding_sha256": selected.binding_sha256,
        "selection_persisted_before_controller_input": True,
    }


def _observe_bound_after(
    scenario: RedLivingDexMaterializationScenario,
    *,
    observed_snapshots: list[RedLivingDexOutcomeSnapshot],
) -> RedLivingDexOutcomeSnapshot:
    if observed_snapshots:
        raise RedLivingDexOptionMaterializerError(
            "materialization observer was called more than once"
        )
    snapshot = scenario.observe_after()
    if not isinstance(snapshot, RedLivingDexOutcomeSnapshot):
        raise RedLivingDexOptionMaterializerError(
            "materialization observer returned an invalid snapshot"
        )
    expected = red_living_dex_observer_provenance_sha256(
        snapshot,
        observer_binding_sha256=scenario.observer_binding_sha256,
    )
    if snapshot.observer_provenance_sha256 != expected:
        raise RedLivingDexOptionMaterializerError(
            "materialization observer receipt is unbound"
        )
    observed_snapshots.append(snapshot)
    return snapshot


def _observation_record(
    scenario: RedLivingDexMaterializationScenario,
    *,
    observed_snapshots: Sequence[RedLivingDexOutcomeSnapshot],
    collected: RedLivingDexCollectedExample,
) -> dict[str, object]:
    if len(observed_snapshots) > 1:
        raise RedLivingDexOptionMaterializerError(
            "materialization recorded more than one after snapshot"
        )
    snapshot = observed_snapshots[0] if observed_snapshots else None
    payload = (
        None
        if snapshot is None
        else _snapshot_provenance_payload(
            snapshot,
            binding=scenario.observer_binding_sha256,
        )
    )
    provenance = None if payload is None else canonical_sha256(payload)
    if provenance != collected.after_observer_provenance_sha256:
        raise RedLivingDexOptionMaterializerError(
            "materialization outcome and observer receipt differ"
        )
    return {
        "after_observation_recorded": payload is not None,
        "independent_observer_calls": collected.independent_observer_calls,
        "materialization_identity_sha256": (
            scenario.materialization_identity_sha256
        ),
        "observer_binding_sha256": scenario.observer_binding_sha256,
        "observer_provenance_sha256": provenance,
        "schema": RED_LIVING_DEX_MATERIALIZATION_OBSERVATION_SCHEMA,
        "snapshot_provenance_payload": payload,
    }


def _load_complete_example(
    store: PrivateArtifactRoot,
    scenario: RedLivingDexMaterializationScenario,
) -> RedLivingDexCollectedExample:
    try:
        reader = store.open_episode(scenario.episode_id)
        if set(reader.stream_names) != {
            "claim",
            "observation",
            "outcome",
            "selection",
        }:
            raise RedLivingDexOptionMaterializerError(
                "materialization episode stream set differs"
            )
        claim = _one_record(reader.iter_stream("claim", max_records=1), subject="claim")
        if claim != _claim_record(scenario):
            raise RedLivingDexOptionMaterializerError(
                "materialization claim differs from the frozen scenario"
            )
        selection = _one_record(
            reader.iter_stream("selection", max_records=1),
            subject="selection",
        )
        commitment_document = _mapping(selection, "commitment", subject="selection")
        commitment = _restore_commitment(commitment_document)
        behavior = red_living_dex_behavior_decision(
            scenario.adapted.menu,
            commitment=commitment,
        )
        if selection != _selection_record(scenario, commitment, behavior):
            raise RedLivingDexOptionMaterializerError(
                "materialization selection does not replay"
            )
        outcome_document = _one_record(
            reader.iter_stream("outcome", max_records=1),
            subject="outcome",
        )
        collected = _restore_collected_example(
            scenario,
            behavior=behavior,
            document=outcome_document,
        )
        observation = _one_record(
            reader.iter_stream("observation", max_records=1),
            subject="observation",
        )
        _validate_observation_record(
            scenario,
            collected=collected,
            document=observation,
        )
        if collected.private_dict() != outcome_document:
            raise RedLivingDexOptionMaterializerError(
                "materialization outcome does not replay"
            )
        return collected
    except RedLivingDexOptionMaterializerError:
        raise
    except PrivateArtifactError as error:
        raise RedLivingDexOptionMaterializerError(
            "materialization episode cannot be authenticated"
        ) from error


def _restore_commitment(
    document: Mapping[str, object],
) -> RedLivingDexBehaviorCommitment:
    expected_keys = {
        "issuance_method",
        "menu_sha256",
        "partition",
        "randomization_seed_sha256",
        "scenario_bound_privately",
        "scenario_identity_sha256",
        "schema",
    }
    if set(document) != expected_keys:
        raise RedLivingDexOptionMaterializerError(
            "materialization commitment fields differ"
        )
    if document.get("issuance_method") != RedLivingDexBehaviorIssuance.SYSTEM_CSPRNG:
        raise RedLivingDexOptionMaterializerError(
            "materialization commitment issuance differs"
        )
    commitment = RedLivingDexBehaviorCommitment(
        _string(document, "scenario_identity_sha256", subject="commitment"),
        _string(document, "partition", subject="commitment"),
        _string(document, "menu_sha256", subject="commitment"),
        _string(document, "randomization_seed_sha256", subject="commitment"),
    )
    object.__setattr__(
        commitment,
        "issuance_origin",
        RedLivingDexBehaviorIssuance.SYSTEM_CSPRNG,
    )
    if commitment.private_dict() != dict(document):
        raise RedLivingDexOptionMaterializerError(
            "materialization commitment does not replay"
        )
    return commitment


def _validate_observation_record(
    scenario: RedLivingDexMaterializationScenario,
    *,
    collected: RedLivingDexCollectedExample,
    document: Mapping[str, object],
) -> None:
    expected_keys = {
        "after_observation_recorded",
        "independent_observer_calls",
        "materialization_identity_sha256",
        "observer_binding_sha256",
        "observer_provenance_sha256",
        "schema",
        "snapshot_provenance_payload",
    }
    if (
        set(document) != expected_keys
        or document.get("schema") != RED_LIVING_DEX_MATERIALIZATION_OBSERVATION_SCHEMA
        or document.get("materialization_identity_sha256")
        != scenario.materialization_identity_sha256
        or document.get("observer_binding_sha256")
        != scenario.observer_binding_sha256
        or document.get("independent_observer_calls")
        != collected.independent_observer_calls
    ):
        raise RedLivingDexOptionMaterializerError(
            "materialization observation receipt differs"
        )
    payload = document.get("snapshot_provenance_payload")
    recorded = document.get("after_observation_recorded")
    provenance = document.get("observer_provenance_sha256")
    if payload is None:
        if (
            recorded is not False
            or provenance is not None
            or collected.after_observer_provenance_sha256 is not None
        ):
            raise RedLivingDexOptionMaterializerError(
                "materialization empty observation receipt differs"
            )
        return
    if not isinstance(payload, Mapping) or recorded is not True:
        raise RedLivingDexOptionMaterializerError(
            "materialization bound observation payload differs"
        )
    expected_provenance = canonical_sha256(payload)
    if (
        provenance != expected_provenance
        or collected.after_observer_provenance_sha256 != expected_provenance
        or payload.get("observer_binding_sha256")
        != scenario.observer_binding_sha256
    ):
        raise RedLivingDexOptionMaterializerError(
            "materialization bound observation provenance differs"
        )


def _restore_collected_example(
    scenario: RedLivingDexMaterializationScenario,
    *,
    behavior: RedLivingDexBehaviorDecision,
    document: Mapping[str, object],
) -> RedLivingDexCollectedExample:
    example_document = _mapping(document, "example", subject="outcome")
    outcome_document = _mapping(example_document, "outcome", subject="example")
    outcome = _restore_outcome(outcome_document)
    probabilities = _float_tuple(
        example_document.get("behavior_probabilities"),
        subject="behavior probabilities",
    )
    example = LivingDexObservedArmExample(
        _string(example_document, "decision_sha256", subject="example"),
        _string(example_document, "partition", subject="example"),
        scenario.adapted.menu,
        _integer(example_document, "selected_candidate_index", subject="example"),
        probabilities,
        outcome,
    )
    after_provenance = document.get("after_observer_provenance_sha256")
    if after_provenance is not None:
        after_provenance = _require_sha256(
            after_provenance,
            subject="after-observer provenance",
        )
    selected_execution_raised = document.get("selected_execution_raised")
    if type(selected_execution_raised) is not bool:  # noqa: E721
        raise RedLivingDexOptionMaterializerError(
            "materialization execution diagnostic differs"
        )
    collected = RedLivingDexCollectedExample(
        scenario.adapted,
        behavior,
        example,
        selected_execution_raised,
        _integer(document, "independent_observer_calls", subject="outcome"),
        after_provenance,
    )
    # The exact complete episode is the only source allowed to restore this
    # provenance bit. Direct collector outputs retain their default origin.
    object.__setattr__(
        collected,
        "collection_origin",
        _collection_origin(scenario),
    )
    return collected


def _restore_outcome(document: Mapping[str, object]) -> LivingDexObservedOutcome:
    try:
        status = LivingDexOutcomeStatus(
            _string(document, "status", subject="observed outcome")
        )
    except ValueError:
        raise RedLivingDexOptionMaterializerError(
            "materialization outcome status differs"
        ) from None
    if status is LivingDexOutcomeStatus.CENSORED:
        try:
            reason = LivingDexCensorReason(
                _string(document, "censor_reason", subject="observed outcome")
            )
        except ValueError:
            raise RedLivingDexOptionMaterializerError(
                "materialization censor reason differs"
            ) from None
        return LivingDexObservedOutcome(status, censor_reason=reason)
    values = _float_tuple(document.get("target_values"), subject="outcome targets")
    if len(values) != 9 or values[0] not in {0.0, 1.0}:
        raise RedLivingDexOptionMaterializerError(
            "materialization settled targets differ"
        )
    return LivingDexObservedOutcome(
        status,
        verified_success=values[0] == 1.0,
        completion_gain=values[1],
        dependency_unlock_gain=values[2],
        action_cost=values[3],
        frame_cost=values[4],
        resource_cost=values[5],
        party_cost=values[6],
        storage_cost=values[7],
        irreversible_loss=values[8],
    )


def _one_record(
    records: Iterable[dict[str, object]],
    *,
    subject: str,
) -> dict[str, object]:
    values = tuple(records)
    if len(values) != 1 or not isinstance(values[0], dict):
        raise RedLivingDexOptionMaterializerError(
            f"materialization {subject} record count differs"
        )
    return values[0]


def _mapping(
    document: Mapping[str, object],
    key: str,
    *,
    subject: str,
) -> Mapping[str, object]:
    value = document.get(key)
    if not isinstance(value, Mapping):
        raise RedLivingDexOptionMaterializerError(
            f"materialization {subject} {key} differs"
        )
    return value


def _string(document: Mapping[str, object], key: str, *, subject: str) -> str:
    value = document.get(key)
    if not isinstance(value, str):
        raise RedLivingDexOptionMaterializerError(
            f"materialization {subject} {key} differs"
        )
    return value


def _integer(document: Mapping[str, object], key: str, *, subject: str) -> int:
    value = document.get(key)
    if type(value) is not int:  # noqa: E721
        raise RedLivingDexOptionMaterializerError(
            f"materialization {subject} {key} differs"
        )
    return value


def _float_tuple(value: object, *, subject: str) -> tuple[float, ...]:
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, (int, float))
        for item in value
    ):
        raise RedLivingDexOptionMaterializerError(
            f"materialization {subject} differ"
        )
    return tuple(float(item) for item in value)


def _snapshot_provenance_payload(
    snapshot: RedLivingDexOutcomeSnapshot,
    *,
    binding: str,
) -> dict[str, object]:
    observation = snapshot.observation
    return {
        "controller_actions": snapshot.controller_actions,
        "emulator_frames": snapshot.emulator_frames,
        "executable_dependency_count": snapshot.executable_dependency_count,
        "irreversible_constraints_remaining": (
            snapshot.irreversible_constraints_remaining
        ),
        "observation": {
            "box_capacity": observation.box_capacity,
            "box_counts": list(observation.box_counts),
            "current_box_index": observation.current_box_index,
            "owned_species": sorted(observation.owned_species),
            "party_limit": observation.party_limit,
            "party_size": observation.party_size,
            "specimens": [
                {
                    "container_index": specimen.container_index,
                    "level": specimen.level,
                    "location": specimen.location.value,
                    "slot_index": specimen.slot_index,
                    "species_ref": specimen.species_ref,
                }
                for specimen in observation.specimens
            ],
        },
        "observer_binding_sha256": binding,
        "party_health_capacity": snapshot.party_health_capacity,
        "party_health_units": snapshot.party_health_units,
        "resource_pool_units": [
            [resource, units] for resource, units in snapshot.resource_pool_units
        ],
        "scenario_identity_sha256": snapshot.scenario_identity_sha256,
        "scenario_repeatable": snapshot.scenario_repeatable,
        "schema": "pokemon.red.private-living-dex-bound-observer-provenance.v1",
        "usable_consumable_units": snapshot.usable_consumable_units,
    }


def _available_kinds(
    scenarios: Sequence[RedLivingDexMaterializationScenario],
) -> frozenset[LivingDexOptionKind]:
    return frozenset(
        scenario.adapted.menu.candidates[index].features.kind
        for scenario in scenarios
        for index in scenario.adapted.menu.available_indices
    )


def _available_family_hashes(
    scenarios: Sequence[RedLivingDexMaterializationScenario],
) -> frozenset[str]:
    return frozenset(
        canonical_sha256(
            {
                "family_ref": scenario.adapted.ordered_options[index].family_ref,
                "schema": "pokemon.red.private-transformation-family-join.v1",
            }
        )
        for scenario in scenarios
        for index in scenario.adapted.menu.available_indices
    )


def _available_location_hashes(
    scenarios: Sequence[RedLivingDexMaterializationScenario],
) -> frozenset[str]:
    return frozenset(
        canonical_sha256(
            {
                "location_ref": scenario.adapted.ordered_options[index].location_ref,
                "schema": "pokemon.red.private-option-location-join.v1",
            }
        )
        for scenario in scenarios
        for index in scenario.adapted.menu.available_indices
    )


def _integer_counter(counts: Counter[int]) -> dict[str, int]:
    return {str(value): counts[value] for value in sorted(counts)}


def _collection_origin(
    scenario: RedLivingDexMaterializationScenario,
) -> RedLivingDexCollectionOrigin:
    return (
        RedLivingDexCollectionOrigin.DURABLE_VERIFIED_CAPTURE
        if scenario.scenario_origin
        is RedLivingDexMaterializationScenarioOrigin.VERIFIED_REPEATABLE_CAPTURE
        else RedLivingDexCollectionOrigin.DURABLE_REHEARSAL
    )


__all__ = [
    "RED_LIVING_DEX_MATERIALIZATION_CLAIM_SCHEMA",
    "RED_LIVING_DEX_MATERIALIZATION_COLLECTION_ID",
    "RED_LIVING_DEX_MATERIALIZATION_PLAN_SCHEMA",
    "RED_LIVING_DEX_MATERIALIZATION_OBSERVATION_SCHEMA",
    "RED_LIVING_DEX_MATERIALIZATION_RECEIPT_SCHEMA",
    "RED_LIVING_DEX_MATERIALIZATION_RUN_SCHEMA",
    "RED_LIVING_DEX_MATERIALIZATION_SELECTION_SCHEMA",
    "RedLivingDexMaterializationDisposition",
    "RedLivingDexMaterializationPlan",
    "RedLivingDexMaterializationReceipt",
    "RedLivingDexMaterializationRun",
    "RedLivingDexMaterializationScenario",
    "RedLivingDexMaterializationScenarioOrigin",
    "RedLivingDexOptionMaterializerError",
    "build_red_living_dex_materialization_plan",
    "bind_red_living_dex_observer_provenance",
    "bind_verified_red_living_dex_materialization_scenario",
    "red_living_dex_observer_provenance_sha256",
    "red_living_dex_verified_capture_scenario_identity",
    "run_red_living_dex_materialization_plan",
]
