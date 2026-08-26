"""Durable Red setup campaign for the prospective living-Pokedex curriculum.

The prospective 10+5 curriculum names semantic decision states, while the
routed-semantic composer can execute one selected destination.  This module
joins those layers without turning setup movement into a learner target:

* every frozen slot receives one private, complete option-binding manifest;
* each option is bound to an existing Red provider contract and is explicitly
  local or semantic-router derived;
* the whole private plan is sealed before any slot claim;
* ``begin_episode`` is the durable one-shot claim and precedes the setup port;
* complete, failed, and interrupted slots are never retried; and
* public projections expose only aggregate, path-free accounting.

This module owns no ROM, emulator, controller, route planner, teacher, behavior
draw, learner label, outcome observer, model, or policy.  A private title adapter
must supply exact bindings and an execution port later.  ROM-free tests may use
synthetic bindings, but those fixtures are never authentic training evidence.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_capture_curriculum import (
    LIVING_DEX_CAPTURE_ATTESTATION_SCHEMA,
    LivingDexCaptureAttestation,
    LivingDexCapturePartition,
    LivingDexCaptureSetupStatus,
    LivingDexCaptureSetupTerminal,
    LivingDexProspectiveCapturePlan,
    LivingDexProspectiveCaptureSlot,
    LivingDexQualifiedCaptureInventory,
    qualify_living_dex_capture_inventory,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.private_artifacts import (
    CollectionSession,
    EpisodeArtifactState,
    EpisodeWriter,
    PrivateArtifactError,
    PrivateArtifactRoot,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_capture_plan import (
    RED_LIVING_DEX_EXECUTOR_CAPABILITIES,
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.routed_semantic_goal import (
    RoutedSemanticBudgetCheckpoint,
    RoutedSemanticBudgetMeter,
)

RED_LIVING_DEX_SETUP_OPTION_BINDING_SCHEMA = (
    "pokemon.red.private-living-dex-setup-option-binding.v1"
)
RED_LIVING_DEX_SETUP_SLOT_BINDING_SCHEMA = "pokemon.red.private-living-dex-setup-slot-binding.v1"
RED_LIVING_DEX_SETUP_BINDING_PLAN_SCHEMA = "pokemon.red.private-living-dex-setup-binding-plan.v1"
RED_LIVING_DEX_SETUP_OPTION_PROOF_SCHEMA = "pokemon.red.private-living-dex-setup-option-proof.v1"
RED_LIVING_DEX_SETUP_EXECUTION_SCHEMA = "pokemon.red.private-living-dex-setup-execution.v1"
RED_LIVING_DEX_SETUP_PLAN_SEAL_SCHEMA = "pokemon.red.private-living-dex-setup-plan-seal.v1"
RED_LIVING_DEX_SETUP_CLAIM_SCHEMA = "pokemon.red.private-living-dex-setup-claim.v1"
RED_LIVING_DEX_SETUP_TERMINAL_SCHEMA = "pokemon.red.private-living-dex-setup-terminal.v1"
RED_LIVING_DEX_SETUP_RUN_SCHEMA = "pokemon.red.living-dex-setup-run.v1"

RED_LIVING_DEX_SETUP_COLLECTION_ID = "red-living-dex-capture-setup-v1"
RED_LIVING_DEX_SETUP_PLAN_RECORD_ID = "red-living-dex-capture-setup-plan-v1"
RED_LIVING_DEX_SETUP_PLAN_RECORD_KIND = "red_living_dex_setup_plan"
RED_LIVING_DEX_SETUP_TERMINAL_RECORD_KIND = "red_living_dex_setup_terminal"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_REASON = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_TERMINAL_ARTIFACT_STATES = {"complete", "failed", "interrupted"}


class RedLivingDexSetupCampaignError(RuntimeError):
    """A setup binding, claim, execution, or durable terminal is invalid."""


class RedLivingDexSetupTransportKind(StrEnum):
    """Whether one semantic option is available locally or after routing."""

    LOCAL = "local"
    ROUTED = "routed"


class RedLivingDexSetupDisposition(StrEnum):
    """How the current process obtained one permanent setup terminal."""

    EXECUTED_COMPLETE = "executed_complete"
    EXECUTED_FAILED = "executed_failed"
    RECOVERED_COMPLETE = "recovered_complete"
    RECOVERED_FAILED = "recovered_failed"
    RECOVERED_INTERRUPTED = "recovered_interrupted"


_GOAL_KIND_BY_OPTION = {
    LivingDexOptionKind.ACQUIRE: GoalKind.ACQUIRE_SPECIES,
    LivingDexOptionKind.EVOLVE: GoalKind.EVOLVE_SPECIES,
    LivingDexOptionKind.DEVELOP: GoalKind.DEVELOP_TEAM,
    LivingDexOptionKind.MANAGE_STORAGE: GoalKind.MANAGE_STORAGE,
    LivingDexOptionKind.RESUPPLY: GoalKind.RESUPPLY,
    LivingDexOptionKind.UNLOCK_ACCESS: GoalKind.ADVANCE_STORY,
    LivingDexOptionKind.EXPLORE: GoalKind.EXPLORE,
}


def _contract_id(value: type[object]) -> str:
    return f"{value.__module__}.{value.__qualname__}"


_CAPABILITY_BY_KIND = {item.option_kind: item for item in RED_LIVING_DEX_EXECUTOR_CAPABILITIES}
_PROVIDER_CONTRACTS_BY_KIND = {
    kind: tuple(_contract_id(value) for value in capability.executor_types)
    for kind, capability in _CAPABILITY_BY_KIND.items()
}


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupOptionBinding:
    """One exact private join from a captured origin to a real Red provider."""

    option_kind: LivingDexOptionKind
    goal_kind: GoalKind
    transport_kind: RedLivingDexSetupTransportKind
    provider_contract_id: str
    provider_capability_sha256: str
    origin_state_sha256: str
    origin_boundary_sha256: str
    destination_terminal_boundary_sha256: str
    expected_fresh_observation_sha256: str
    expected_provider_offer_sha256: str
    expected_executable_binding_sha256: str
    route_plan_sha256: str | None = None
    route_terminal_predicate_sha256: str | None = None
    route_planner_binding_sha256: str | None = None
    route_source: str = field(default="semantic-router-v1", init=False)
    raw_controller_sequence_steps: int = field(default=0, init=False)
    teacher_route: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.option_kind, LivingDexOptionKind):
            raise RedLivingDexSetupCampaignError("setup option kind differs")
        expected_goal = _GOAL_KIND_BY_OPTION.get(self.option_kind)
        if expected_goal is None or self.goal_kind is not expected_goal:
            raise RedLivingDexSetupCampaignError("setup option goal mapping differs")
        if not isinstance(self.transport_kind, RedLivingDexSetupTransportKind):
            raise RedLivingDexSetupCampaignError("setup option transport kind differs")
        expected_contracts = _PROVIDER_CONTRACTS_BY_KIND.get(self.option_kind, ())
        if self.provider_contract_id not in expected_contracts:
            raise RedLivingDexSetupCampaignError(
                "setup option provider contract is not implemented for its kind"
            )
        capability = _CAPABILITY_BY_KIND[self.option_kind]
        if self.provider_capability_sha256 != capability.capability_sha256:
            raise RedLivingDexSetupCampaignError(
                "setup option provider capability provenance differs"
            )
        for value, subject in (
            (self.origin_state_sha256, "setup option origin state"),
            (self.origin_boundary_sha256, "setup option origin boundary"),
            (
                self.destination_terminal_boundary_sha256,
                "setup option destination terminal",
            ),
            (
                self.expected_fresh_observation_sha256,
                "setup option fresh observation",
            ),
            (self.expected_provider_offer_sha256, "setup option provider offer"),
            (
                self.expected_executable_binding_sha256,
                "setup option executable binding",
            ),
        ):
            _require_sha256(value, subject)
        if self.transport_kind is RedLivingDexSetupTransportKind.LOCAL:
            if self.destination_terminal_boundary_sha256 != self.origin_boundary_sha256:
                raise RedLivingDexSetupCampaignError(
                    "local setup option leaves its captured boundary"
                )
            if any(
                value is not None
                for value in (
                    self.route_plan_sha256,
                    self.route_terminal_predicate_sha256,
                    self.route_planner_binding_sha256,
                )
            ):
                raise RedLivingDexSetupCampaignError("local setup option invents a route binding")
        else:
            if self.destination_terminal_boundary_sha256 == self.origin_boundary_sha256:
                raise RedLivingDexSetupCampaignError(
                    "routed setup option does not leave its captured boundary"
                )
            for route_value, subject in (
                (self.route_plan_sha256, "setup option route plan"),
                (
                    self.route_terminal_predicate_sha256,
                    "setup option route terminal predicate",
                ),
                (
                    self.route_planner_binding_sha256,
                    "setup option route planner binding",
                ),
            ):
                _require_sha256(route_value, subject)
        if (
            self.route_source != "semantic-router-v1"
            or self.raw_controller_sequence_steps != 0
            or self.teacher_route
        ):
            raise RedLivingDexSetupCampaignError(
                "setup option route provenance is not semantic-router derived"
            )

    @property
    def binding_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "destination_terminal_boundary_sha256": (self.destination_terminal_boundary_sha256),
            "expected_executable_binding_sha256": (self.expected_executable_binding_sha256),
            "expected_fresh_observation_sha256": (self.expected_fresh_observation_sha256),
            "expected_provider_offer_sha256": self.expected_provider_offer_sha256,
            "goal_kind": self.goal_kind.value,
            "option_kind": self.option_kind.value,
            "origin_boundary_sha256": self.origin_boundary_sha256,
            "origin_state_sha256": self.origin_state_sha256,
            "provider_capability_sha256": self.provider_capability_sha256,
            "provider_contract_id": self.provider_contract_id,
            "raw_controller_sequence_steps": self.raw_controller_sequence_steps,
            "route_plan_sha256": self.route_plan_sha256,
            "route_planner_binding_sha256": self.route_planner_binding_sha256,
            "route_source": (
                None
                if self.transport_kind is RedLivingDexSetupTransportKind.LOCAL
                else self.route_source
            ),
            "route_terminal_predicate_sha256": (self.route_terminal_predicate_sha256),
            "schema": RED_LIVING_DEX_SETUP_OPTION_BINDING_SCHEMA,
            "teacher_route": self.teacher_route,
            "transport_kind": self.transport_kind.value,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "goal_kind": self.goal_kind.value,
            "option_kind": self.option_kind.value,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "provider_contract_implemented": True,
            "raw_controller_sequence_steps": self.raw_controller_sequence_steps,
            "route_source": (
                None
                if self.transport_kind is RedLivingDexSetupTransportKind.LOCAL
                else self.route_source
            ),
            "teacher_route": self.teacher_route,
            "transport_kind": self.transport_kind.value,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupSlotBinding:
    """The complete private setup and option manifest for one frozen slot."""

    slot_sha256: str
    setup_plan_sha256: str
    terminal_predicate_sha256: str
    observer_contract_sha256: str
    partition: LivingDexCapturePartition
    available_option_kinds: tuple[LivingDexOptionKind, ...]
    root_consumption_sha256: str
    state_sha256: str
    origin_boundary_sha256: str
    envelope_sha256: str
    menu_sha256: str
    observer_binding_sha256: str
    available_family_sha256s: tuple[str, ...]
    location_sha256: str
    option_bindings: tuple[RedLivingDexSetupOptionBinding, ...]

    def __post_init__(self) -> None:
        for value, subject in (
            (self.slot_sha256, "setup slot"),
            (self.setup_plan_sha256, "setup plan"),
            (self.terminal_predicate_sha256, "setup terminal predicate"),
            (self.observer_contract_sha256, "setup observer contract"),
            (self.root_consumption_sha256, "setup root"),
            (self.state_sha256, "setup state"),
            (self.origin_boundary_sha256, "setup origin boundary"),
            (self.envelope_sha256, "setup envelope"),
            (self.menu_sha256, "setup menu"),
            (self.observer_binding_sha256, "setup observer binding"),
            (self.location_sha256, "setup location"),
        ):
            _require_sha256(value, subject)
        if not isinstance(self.partition, LivingDexCapturePartition):
            raise RedLivingDexSetupCampaignError("setup slot partition differs")
        _require_option_kinds(self.available_option_kinds)
        if not isinstance(self.available_family_sha256s, tuple) or len(
            self.available_family_sha256s
        ) != len(self.available_option_kinds):
            raise RedLivingDexSetupCampaignError("setup slot family bindings differ from its menu")
        for value in self.available_family_sha256s:
            _require_sha256(value, "setup family")
        if (
            not isinstance(self.option_bindings, tuple)
            or len(self.option_bindings) != len(self.available_option_kinds)
            or any(
                not isinstance(item, RedLivingDexSetupOptionBinding)
                for item in self.option_bindings
            )
        ):
            raise RedLivingDexSetupCampaignError(
                "setup slot needs one binding for every menu option"
            )
        for item in self.option_bindings:
            item.__post_init__()
        if tuple(item.option_kind for item in self.option_bindings) != (
            self.available_option_kinds
        ):
            raise RedLivingDexSetupCampaignError(
                "setup slot option binding order differs from its menu"
            )
        if any(
            item.origin_state_sha256 != self.state_sha256
            or item.origin_boundary_sha256 != self.origin_boundary_sha256
            for item in self.option_bindings
        ):
            raise RedLivingDexSetupCampaignError(
                "setup slot options do not share the captured origin"
            )
        _require_unique(
            (item.binding_sha256 for item in self.option_bindings),
            "setup option bindings",
        )

    @property
    def binding_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    @property
    def routed_option_count(self) -> int:
        return sum(
            item.transport_kind is RedLivingDexSetupTransportKind.ROUTED
            for item in self.option_bindings
        )

    def private_dict(self) -> dict[str, object]:
        return {
            "available_family_sha256s": list(self.available_family_sha256s),
            "available_option_kinds": [item.value for item in self.available_option_kinds],
            "envelope_sha256": self.envelope_sha256,
            "location_sha256": self.location_sha256,
            "menu_sha256": self.menu_sha256,
            "observer_binding_sha256": self.observer_binding_sha256,
            "observer_contract_sha256": self.observer_contract_sha256,
            "option_bindings": [item.private_dict() for item in self.option_bindings],
            "origin_boundary_sha256": self.origin_boundary_sha256,
            "partition": self.partition.value,
            "root_consumption_sha256": self.root_consumption_sha256,
            "schema": RED_LIVING_DEX_SETUP_SLOT_BINDING_SCHEMA,
            "setup_plan_sha256": self.setup_plan_sha256,
            "slot_sha256": self.slot_sha256,
            "state_sha256": self.state_sha256,
            "terminal_predicate_sha256": self.terminal_predicate_sha256,
        }

    def public_dict(self) -> dict[str, object]:
        transports = Counter(item.transport_kind.value for item in self.option_bindings)
        return {
            "complete_menu_bound": True,
            "menu_width": len(self.available_option_kinds),
            "option_kinds": [item.value for item in self.available_option_kinds],
            "partition": self.partition.value,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "provider_contracts_bound": len(self.option_bindings),
            "transport_counts": {
                kind.value: transports[kind.value] for kind in RedLivingDexSetupTransportKind
            },
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupBindingPlan:
    """All fifteen private Red setup bindings frozen before controller input."""

    prospective_plan: LivingDexProspectiveCapturePlan
    bindings: tuple[RedLivingDexSetupSlotBinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.prospective_plan, LivingDexProspectiveCapturePlan):
            raise TypeError("setup binding plan needs its prospective plan")
        self.prospective_plan.__post_init__()
        canonical_red_plan = build_red_living_dex_prospective_capture_plan()
        if self.prospective_plan.plan_sha256 != canonical_red_plan.plan_sha256:
            raise RedLivingDexSetupCampaignError(
                "setup binding plan does not use the frozen Red 10+5 plan"
            )
        if (
            not isinstance(self.bindings, tuple)
            or len(self.bindings) != len(self.prospective_plan.slots)
            or any(not isinstance(item, RedLivingDexSetupSlotBinding) for item in self.bindings)
        ):
            raise RedLivingDexSetupCampaignError(
                "setup binding plan must account for every frozen slot"
            )
        for item in self.bindings:
            item.__post_init__()
        for slot, binding in zip(
            self.prospective_plan.slots,
            self.bindings,
            strict=True,
        ):
            _require_slot_join(slot, binding)
            local_capable = _slot_is_locally_composable(slot)
            if local_capable and binding.routed_option_count:
                raise RedLivingDexSetupCampaignError(
                    "locally composable setup slot was unnecessarily routed"
                )
            if not local_capable and not binding.routed_option_count:
                raise RedLivingDexSetupCampaignError(
                    "routed setup slot lacks a concrete route binding"
                )
        _require_unique(
            (item.binding_sha256 for item in self.bindings),
            "setup slot bindings",
        )
        for values, subject in (
            ((item.root_consumption_sha256 for item in self.bindings), "setup roots"),
            ((item.state_sha256 for item in self.bindings), "setup states"),
            ((item.envelope_sha256 for item in self.bindings), "setup envelopes"),
            ((item.menu_sha256 for item in self.bindings), "setup menus"),
            (
                (item.observer_binding_sha256 for item in self.bindings),
                "setup observer bindings",
            ),
        ):
            _require_unique(values, subject)
        routed_plans = tuple(
            option.route_plan_sha256
            for binding in self.bindings
            for option in binding.option_bindings
            if option.route_plan_sha256 is not None
        )
        _require_unique(routed_plans, "setup route plans")
        if self.routed_slot_count != 14 or self.local_slot_count != 1:
            raise RedLivingDexSetupCampaignError(
                "setup binding plan routed/local slot census differs"
            )

    @property
    def plan_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    @property
    def routed_slot_count(self) -> int:
        return sum(item.routed_option_count > 0 for item in self.bindings)

    @property
    def local_slot_count(self) -> int:
        return len(self.bindings) - self.routed_slot_count

    def private_dict(self) -> dict[str, object]:
        return {
            "bindings": [item.private_dict() for item in self.bindings],
            "claim_before_controller_input": True,
            "learner_effects": 0,
            "prospective_plan_sha256": self.prospective_plan.plan_sha256,
            "retry_after_controller_input": False,
            "schema": RED_LIVING_DEX_SETUP_BINDING_PLAN_SCHEMA,
        }

    def public_dict(self) -> dict[str, object]:
        partitions = Counter(item.partition.value for item in self.bindings)
        option_transports = Counter(
            option.transport_kind.value
            for binding in self.bindings
            for option in binding.option_bindings
        )
        return {
            "all_slots_bound": len(self.bindings) == 15,
            "claim_before_controller_input": True,
            "complete_menus_bound": len(self.bindings),
            "development_slots": partitions[LivingDexCapturePartition.DEVELOPMENT.value],
            "learner_behavior_draws": 0,
            "learner_labels_emitted": 0,
            "learner_outcomes_observed": 0,
            "local_slots": self.local_slot_count,
            "option_transport_counts": {
                kind.value: option_transports[kind.value] for kind in RedLivingDexSetupTransportKind
            },
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "provider_contracts_bound": sum(len(item.option_bindings) for item in self.bindings),
            "retry_after_controller_input": False,
            "routed_slots": self.routed_slot_count,
            "runtime_private_bindings_authenticated": False,
            "runtime_private_routes_executed": False,
            "schema": RED_LIVING_DEX_SETUP_BINDING_PLAN_SCHEMA,
            "slot_count": len(self.bindings),
            "train_slots": partitions[LivingDexCapturePartition.TRAIN.value],
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupOptionProof:
    """Action-free proof that one planned semantic arm remains executable."""

    option_binding_sha256: str
    fresh_observation_sha256: str
    provider_offer_sha256: str
    executable_binding_sha256: str
    transport_terminal_verified: bool = True
    provider_offer_authenticated: bool = True
    controller_actions: int = field(default=0, init=False)
    emulator_frames: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        for value, subject in (
            (self.option_binding_sha256, "setup option proof binding"),
            (self.fresh_observation_sha256, "setup option proof observation"),
            (self.provider_offer_sha256, "setup option proof provider offer"),
            (self.executable_binding_sha256, "setup option proof executable"),
        ):
            _require_sha256(value, subject)
        if not self.transport_terminal_verified or not self.provider_offer_authenticated:
            raise RedLivingDexSetupCampaignError("setup option proof is not authenticated")
        if self.controller_actions != 0 or self.emulator_frames != 0:
            raise RedLivingDexSetupCampaignError(
                "setup option proof authentication must be action-free"
            )

    def private_dict(self) -> dict[str, object]:
        return {
            "controller_actions": self.controller_actions,
            "emulator_frames": self.emulator_frames,
            "executable_binding_sha256": self.executable_binding_sha256,
            "fresh_observation_sha256": self.fresh_observation_sha256,
            "option_binding_sha256": self.option_binding_sha256,
            "provider_offer_authenticated": self.provider_offer_authenticated,
            "provider_offer_sha256": self.provider_offer_sha256,
            "schema": RED_LIVING_DEX_SETUP_OPTION_PROOF_SCHEMA,
            "transport_terminal_verified": self.transport_terminal_verified,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupExecution:
    """One successful setup result, still before behavior or learner action."""

    slot_binding_sha256: str
    capture_attestation: LivingDexCaptureAttestation
    option_proofs: tuple[RedLivingDexSetupOptionProof, ...]
    behavior_draws: int = field(default=0, init=False)
    learner_labels: int = field(default=0, init=False)
    learner_outcomes: int = field(default=0, init=False)
    model_predictions: int = field(default=0, init=False)
    model_fits: int = field(default=0, init=False)
    teacher_queries: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        _require_sha256(self.slot_binding_sha256, "setup execution binding")
        if not isinstance(self.capture_attestation, LivingDexCaptureAttestation):
            raise TypeError("setup execution needs a capture attestation")
        self.capture_attestation.__post_init__()
        if (
            not isinstance(self.option_proofs, tuple)
            or not self.option_proofs
            or any(
                not isinstance(item, RedLivingDexSetupOptionProof) for item in self.option_proofs
            )
        ):
            raise RedLivingDexSetupCampaignError("setup execution needs option proofs")
        for item in self.option_proofs:
            item.__post_init__()
        _require_unique(
            (item.option_binding_sha256 for item in self.option_proofs),
            "setup execution option proofs",
        )
        if any(
            value != 0
            for value in (
                self.behavior_draws,
                self.learner_labels,
                self.learner_outcomes,
                self.model_predictions,
                self.model_fits,
                self.teacher_queries,
            )
        ):
            raise RedLivingDexSetupCampaignError(
                "setup execution crossed a learner or model boundary"
            )

    def private_dict(self) -> dict[str, object]:
        return {
            "behavior_draws": self.behavior_draws,
            "capture_attestation": self.capture_attestation.private_dict(),
            "learner_labels": self.learner_labels,
            "learner_outcomes": self.learner_outcomes,
            "model_fits": self.model_fits,
            "model_predictions": self.model_predictions,
            "option_proofs": [item.private_dict() for item in self.option_proofs],
            "schema": RED_LIVING_DEX_SETUP_EXECUTION_SCHEMA,
            "slot_binding_sha256": self.slot_binding_sha256,
            "teacher_queries": self.teacher_queries,
        }


@runtime_checkable
class RedLivingDexSetupExecutor(Protocol):
    """Private port that may touch the controller only after durable claim."""

    def execute_setup(
        self,
        binding: RedLivingDexSetupSlotBinding,
    ) -> RedLivingDexSetupExecution: ...


class RedLivingDexControlledSetupFailure(RuntimeError):
    """A sanitized, expected setup failure with no retry semantics."""

    def __init__(self, reason_code: str) -> None:
        if not isinstance(reason_code, str) or _SAFE_REASON.fullmatch(reason_code) is None:
            raise RedLivingDexSetupCampaignError("controlled setup failure reason differs")
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupTerminalRecord:
    """The sealed, private whole-slot terminal independent of episode naming."""

    binding_plan_sha256: str
    slot_binding_sha256: str
    claim_sha256: str
    status: LivingDexCaptureSetupStatus
    reason_code: str | None
    setup_controller_actions: int | None
    setup_emulator_frames: int | None
    attestation_sha256: str | None
    retry_allowed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        for value, subject in (
            (self.binding_plan_sha256, "setup terminal plan"),
            (self.slot_binding_sha256, "setup terminal binding"),
            (self.claim_sha256, "setup terminal claim"),
        ):
            _require_sha256(value, subject)
        if not isinstance(self.status, LivingDexCaptureSetupStatus):
            raise RedLivingDexSetupCampaignError("setup terminal status differs")
        known = self.setup_controller_actions is not None
        if known != (self.setup_emulator_frames is not None):
            raise RedLivingDexSetupCampaignError(
                "setup terminal budget accounting is only partially known"
            )
        if known:
            assert self.setup_controller_actions is not None
            assert self.setup_emulator_frames is not None
            for numeric_value, subject in (
                (self.setup_controller_actions, "setup terminal actions"),
                (self.setup_emulator_frames, "setup terminal frames"),
            ):
                if type(numeric_value) is not int or numeric_value < 0:  # noqa: E721
                    raise RedLivingDexSetupCampaignError(f"{subject} differ")
        if self.status is LivingDexCaptureSetupStatus.COMPLETE:
            if not known or self.reason_code is not None or self.attestation_sha256 is None:
                raise RedLivingDexSetupCampaignError("complete setup terminal evidence differs")
            _require_sha256(self.attestation_sha256, "setup terminal attestation")
        else:
            if (
                not isinstance(self.reason_code, str)
                or _SAFE_REASON.fullmatch(self.reason_code) is None
                or self.attestation_sha256 is not None
            ):
                raise RedLivingDexSetupCampaignError("noncomplete setup terminal evidence differs")
        if self.retry_allowed:
            raise RedLivingDexSetupCampaignError("claimed setup terminal cannot retry")

    @property
    def accounting_known(self) -> bool:
        return self.setup_controller_actions is not None

    def private_dict(self) -> dict[str, object]:
        return {
            "attestation_sha256": self.attestation_sha256,
            "binding_plan_sha256": self.binding_plan_sha256,
            "claim_sha256": self.claim_sha256,
            "reason_code": self.reason_code,
            "retry_allowed": self.retry_allowed,
            "schema": RED_LIVING_DEX_SETUP_TERMINAL_SCHEMA,
            "setup_controller_actions": self.setup_controller_actions,
            "setup_emulator_frames": self.setup_emulator_frames,
            "slot_binding_sha256": self.slot_binding_sha256,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupReceipt:
    """One path-free view of a permanent private setup terminal."""

    binding: RedLivingDexSetupSlotBinding
    terminal: RedLivingDexSetupTerminalRecord
    artifact_state: EpisodeArtifactState
    disposition: RedLivingDexSetupDisposition
    execution: RedLivingDexSetupExecution | None

    def __post_init__(self) -> None:
        if not isinstance(self.binding, RedLivingDexSetupSlotBinding):
            raise TypeError("setup receipt needs its slot binding")
        if not isinstance(self.terminal, RedLivingDexSetupTerminalRecord):
            raise TypeError("setup receipt needs its terminal")
        if not isinstance(self.artifact_state, EpisodeArtifactState):
            raise TypeError("setup receipt needs its artifact state")
        if not isinstance(self.disposition, RedLivingDexSetupDisposition):
            raise TypeError("setup receipt disposition differs")
        if self.terminal.slot_binding_sha256 != self.binding.binding_sha256:
            raise RedLivingDexSetupCampaignError("setup receipt terminal is joined to another slot")
        if self.artifact_state.status not in _TERMINAL_ARTIFACT_STATES:
            raise RedLivingDexSetupCampaignError("setup receipt artifact is not terminal")
        if self.terminal.status is LivingDexCaptureSetupStatus.COMPLETE:
            if self.execution is None or self.artifact_state.status != "complete":
                raise RedLivingDexSetupCampaignError("complete setup receipt lacks its execution")
            if (
                self.execution.capture_attestation.attestation_sha256
                != self.terminal.attestation_sha256
            ):
                raise RedLivingDexSetupCampaignError(
                    "setup receipt attestation differs from its terminal"
                )
        elif self.execution is not None:
            raise RedLivingDexSetupCampaignError(
                "noncomplete setup receipt cannot expose an execution"
            )
        expected_status = {
            RedLivingDexSetupDisposition.EXECUTED_COMPLETE: (LivingDexCaptureSetupStatus.COMPLETE),
            RedLivingDexSetupDisposition.EXECUTED_FAILED: (LivingDexCaptureSetupStatus.FAILED),
            RedLivingDexSetupDisposition.RECOVERED_COMPLETE: (LivingDexCaptureSetupStatus.COMPLETE),
            RedLivingDexSetupDisposition.RECOVERED_FAILED: (LivingDexCaptureSetupStatus.FAILED),
            RedLivingDexSetupDisposition.RECOVERED_INTERRUPTED: (
                LivingDexCaptureSetupStatus.INTERRUPTED
            ),
        }[self.disposition]
        if self.terminal.status is not expected_status:
            raise RedLivingDexSetupCampaignError(
                "setup receipt disposition contradicts its terminal"
            )

    @property
    def newly_executed(self) -> bool:
        return self.disposition in {
            RedLivingDexSetupDisposition.EXECUTED_COMPLETE,
            RedLivingDexSetupDisposition.EXECUTED_FAILED,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "accounting_known": self.terminal.accounting_known,
            "disposition": self.disposition.value,
            "learner_behavior_draws": 0,
            "learner_labels_emitted": 0,
            "learner_outcomes_observed": 0,
            "new_setup_executor_invocation": self.newly_executed,
            "partition": self.binding.partition.value,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "reason_code": self.terminal.reason_code,
            "retry_allowed": False,
            "setup_controller_actions": self.terminal.setup_controller_actions,
            "setup_emulator_frames": self.terminal.setup_emulator_frames,
            "status": self.terminal.status.value,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupRun:
    """A restart-safe pass over all fifteen setup slots."""

    plan: RedLivingDexSetupBindingPlan
    receipts: tuple[RedLivingDexSetupReceipt, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.plan, RedLivingDexSetupBindingPlan):
            raise TypeError("setup run needs its binding plan")
        if (
            not isinstance(self.receipts, tuple)
            or len(self.receipts) != len(self.plan.bindings)
            or any(not isinstance(item, RedLivingDexSetupReceipt) for item in self.receipts)
            or tuple(item.binding for item in self.receipts) != self.plan.bindings
        ):
            raise RedLivingDexSetupCampaignError(
                "setup run does not account for every frozen slot in order"
            )

    @property
    def inventory_qualification_available(self) -> bool:
        if any(not item.terminal.accounting_known for item in self.receipts):
            return False
        try:
            self.qualified_inventory()
        except (RedLivingDexSetupCampaignError, ValueError):
            return False
        return True

    def qualified_inventory(self) -> LivingDexQualifiedCaptureInventory:
        """Build the shared inventory only when every terminal is fully accounted."""

        terminals: list[LivingDexCaptureSetupTerminal] = []
        for slot, receipt in zip(
            self.plan.prospective_plan.slots,
            self.receipts,
            strict=True,
        ):
            terminal = receipt.terminal
            if not terminal.accounting_known:
                raise RedLivingDexSetupCampaignError(
                    "setup run has a terminal with unknown budget accounting"
                )
            assert terminal.setup_controller_actions is not None
            assert terminal.setup_emulator_frames is not None
            attestation = (
                None if receipt.execution is None else receipt.execution.capture_attestation
            )
            terminals.append(
                LivingDexCaptureSetupTerminal(
                    slot_sha256=slot.slot_sha256,
                    claim_sha256=terminal.claim_sha256,
                    status=terminal.status,
                    setup_controller_actions=terminal.setup_controller_actions,
                    setup_emulator_frames=terminal.setup_emulator_frames,
                    attestation=attestation,
                )
            )
        return qualify_living_dex_capture_inventory(
            self.plan.prospective_plan,
            terminals,
        )

    def public_dict(self) -> dict[str, object]:
        statuses = Counter(item.terminal.status.value for item in self.receipts)
        dispositions = Counter(item.disposition.value for item in self.receipts)
        known = tuple(item for item in self.receipts if item.terminal.accounting_known)
        return {
            "all_slots_terminal": len(self.receipts) == len(self.plan.bindings),
            "behavior_draws": 0,
            "disposition_counts": {
                item.value: dispositions[item.value] for item in RedLivingDexSetupDisposition
            },
            "inventory_qualification_available": (self.inventory_qualification_available),
            "learner_controller_actions": 0,
            "learner_labels_emitted": 0,
            "learner_outcomes_observed": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "plan": self.plan.public_dict(),
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "retry_allowed": False,
            "schema": RED_LIVING_DEX_SETUP_RUN_SCHEMA,
            "setup_controller_actions_known_total": sum(
                item.terminal.setup_controller_actions or 0 for item in known
            ),
            "setup_emulator_frames_known_total": sum(
                item.terminal.setup_emulator_frames or 0 for item in known
            ),
            "terminal_accounting_known": len(known),
            "terminal_accounting_unknown": len(self.receipts) - len(known),
            "terminal_status_counts": {
                item.value: statuses[item.value] for item in LivingDexCaptureSetupStatus
            },
            "teacher_queries": 0,
        }


def build_red_living_dex_setup_binding_plan(
    bindings: Sequence[RedLivingDexSetupSlotBinding],
    *,
    prospective_plan: LivingDexProspectiveCapturePlan | None = None,
) -> RedLivingDexSetupBindingPlan:
    """Freeze exact private bindings for the published Red 10+5 schedule."""

    if not isinstance(bindings, Sequence):
        raise TypeError("setup bindings must be a sequence")
    return RedLivingDexSetupBindingPlan(
        prospective_plan=(
            build_red_living_dex_prospective_capture_plan()
            if prospective_plan is None
            else prospective_plan
        ),
        bindings=tuple(bindings),
    )


def run_red_living_dex_setup_campaign(
    store: PrivateArtifactRoot,
    plan: RedLivingDexSetupBindingPlan,
    *,
    executor: RedLivingDexSetupExecutor,
    budget_meter: RoutedSemanticBudgetMeter,
) -> RedLivingDexSetupRun:
    """Execute or recover all slots without reopening a claimed namespace."""

    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("setup campaign needs a validated private artifact root")
    if not isinstance(plan, RedLivingDexSetupBindingPlan):
        raise TypeError("setup campaign needs a frozen binding plan")
    plan.__post_init__()
    if not isinstance(executor, RedLivingDexSetupExecutor):
        raise TypeError("setup campaign needs an execution port")
    if not isinstance(budget_meter, RoutedSemanticBudgetMeter):
        raise TypeError("setup campaign needs an independent budget meter")
    _seal_setup_plan(store, plan)
    receipts: list[RedLivingDexSetupReceipt] = []
    with store.collection_session(RED_LIVING_DEX_SETUP_COLLECTION_ID) as session:
        for ordinal, binding in enumerate(plan.bindings):
            receipts.append(
                _run_setup_slot(
                    store,
                    session,
                    plan,
                    binding,
                    ordinal=ordinal,
                    executor=executor,
                    budget_meter=budget_meter,
                )
            )
    return RedLivingDexSetupRun(plan, tuple(receipts))


def _seal_setup_plan(
    store: PrivateArtifactRoot,
    plan: RedLivingDexSetupBindingPlan,
) -> None:
    record = {
        "binding_plan": plan.private_dict(),
        "binding_plan_sha256": plan.plan_sha256,
        "claim_before_controller_input": True,
        "collection_id": RED_LIVING_DEX_SETUP_COLLECTION_ID,
        "learner_effects": 0,
        "retry_after_controller_input": False,
        "schema": RED_LIVING_DEX_SETUP_PLAN_SEAL_SCHEMA,
    }
    try:
        sealed = store.publish_sealed_record(
            RED_LIVING_DEX_SETUP_PLAN_RECORD_ID,
            kind=RED_LIVING_DEX_SETUP_PLAN_RECORD_KIND,
            record=record,
        )
        if sealed.read() != record:
            raise RedLivingDexSetupCampaignError("setup campaign plan seal failed verification")
    except RedLivingDexSetupCampaignError:
        raise
    except PrivateArtifactError as error:
        raise RedLivingDexSetupCampaignError(str(error)) from None


def _run_setup_slot(
    store: PrivateArtifactRoot,
    session: CollectionSession,
    plan: RedLivingDexSetupBindingPlan,
    binding: RedLivingDexSetupSlotBinding,
    *,
    ordinal: int,
    executor: RedLivingDexSetupExecutor,
    budget_meter: RoutedSemanticBudgetMeter,
) -> RedLivingDexSetupReceipt:
    session.require_store(store)
    episode_id = _episode_id(binding, ordinal)
    claim = _claim_record(plan, binding)
    claim_sha256 = canonical_sha256(claim)
    stored_terminal = _find_terminal(store, plan, binding, claim_sha256)
    state = session.inspect_episode(episode_id)
    if stored_terminal is not None:
        if state.status == "partial":
            state = session.recover_interrupted_episode(episode_id)
        return _receipt_from_terminal(
            store,
            plan,
            binding,
            state,
            stored_terminal,
            newly_executed=False,
        )
    if state.status == "partial":
        state = session.recover_interrupted_episode(episode_id)
    if state.status == "complete":
        execution = _load_complete_execution(store, plan, binding, episode_id)
        terminal = _complete_terminal(plan, binding, claim_sha256, execution)
        _publish_terminal(store, binding, terminal)
        return RedLivingDexSetupReceipt(
            binding,
            terminal,
            state,
            RedLivingDexSetupDisposition.RECOVERED_COMPLETE,
            execution,
        )
    if state.status in {"failed", "interrupted"}:
        status = (
            LivingDexCaptureSetupStatus.FAILED
            if state.status == "failed"
            else LivingDexCaptureSetupStatus.INTERRUPTED
        )
        terminal = RedLivingDexSetupTerminalRecord(
            binding_plan_sha256=plan.plan_sha256,
            slot_binding_sha256=binding.binding_sha256,
            claim_sha256=claim_sha256,
            status=status,
            reason_code=state.reason_code or "process_interrupted",
            setup_controller_actions=None,
            setup_emulator_frames=None,
            attestation_sha256=None,
        )
        _publish_terminal(store, binding, terminal)
        disposition = (
            RedLivingDexSetupDisposition.RECOVERED_FAILED
            if status is LivingDexCaptureSetupStatus.FAILED
            else RedLivingDexSetupDisposition.RECOVERED_INTERRUPTED
        )
        return RedLivingDexSetupReceipt(
            binding,
            terminal,
            state,
            disposition,
            None,
        )
    if state.status == "invalid":
        raise RedLivingDexSetupCampaignError("setup slot artifact cannot be authenticated")
    if state.status != "absent":
        raise RedLivingDexSetupCampaignError("setup slot has an unsupported durable state")
    return _execute_setup_slot(
        store,
        plan,
        binding,
        episode_id=episode_id,
        claim=claim,
        claim_sha256=claim_sha256,
        executor=executor,
        budget_meter=budget_meter,
    )


def _execute_setup_slot(
    store: PrivateArtifactRoot,
    plan: RedLivingDexSetupBindingPlan,
    binding: RedLivingDexSetupSlotBinding,
    *,
    episode_id: str,
    claim: Mapping[str, object],
    claim_sha256: str,
    executor: RedLivingDexSetupExecutor,
    budget_meter: RoutedSemanticBudgetMeter,
) -> RedLivingDexSetupReceipt:
    before = _checkpoint(budget_meter)
    # begin_episode is the durable, exclusive one-shot claim.  Nothing that can
    # call the controller is reachable before this returns and the claim stream
    # is synced.
    with store.begin_episode(episode_id) as writer:
        writer.append("claim", claim, durable=True)
        if _checkpoint(budget_meter) != before:
            raise RedLivingDexSetupCampaignError(
                "setup claim or plan sealing changed the controller budget"
            )
        try:
            execution = executor.execute_setup(binding)
            after = _checkpoint(budget_meter)
            actions, frames = _checkpoint_delta(before, after)
            _validate_execution(binding, execution, actions=actions, frames=frames)
            writer.append("execution", execution.private_dict(), durable=True)
        except RedLivingDexControlledSetupFailure as error:
            return _settle_failed_setup(
                store,
                writer,
                plan,
                binding,
                claim_sha256=claim_sha256,
                before=before,
                budget_meter=budget_meter,
                reason_code=error.reason_code,
            )
        except BaseException as error:
            reason = (
                "process_interrupted"
                if not isinstance(error, Exception)
                else "setup_execution_failed"
            )
            _settle_failed_setup(
                store,
                writer,
                plan,
                binding,
                claim_sha256=claim_sha256,
                before=before,
                budget_meter=budget_meter,
                reason_code=reason,
                interrupted=not isinstance(error, Exception),
            )
            if not isinstance(error, Exception):
                raise
            raise RedLivingDexSetupCampaignError(
                "setup execution failed after durable claim"
            ) from None
        summary = writer.complete()
    state = EpisodeArtifactState(
        episode_id,
        "complete",
        manifest_sha256=summary.manifest_sha256,
    )
    terminal = _complete_terminal(plan, binding, claim_sha256, execution)
    _publish_terminal(store, binding, terminal)
    return RedLivingDexSetupReceipt(
        binding,
        terminal,
        state,
        RedLivingDexSetupDisposition.EXECUTED_COMPLETE,
        execution,
    )


def _settle_failed_setup(
    store: PrivateArtifactRoot,
    writer: EpisodeWriter,
    plan: RedLivingDexSetupBindingPlan,
    binding: RedLivingDexSetupSlotBinding,
    *,
    claim_sha256: str,
    before: RoutedSemanticBudgetCheckpoint,
    budget_meter: RoutedSemanticBudgetMeter,
    reason_code: str,
    interrupted: bool = False,
) -> RedLivingDexSetupReceipt:
    after = _checkpoint(budget_meter)
    actions, frames = _checkpoint_delta(before, after)
    status = (
        LivingDexCaptureSetupStatus.INTERRUPTED
        if interrupted
        else LivingDexCaptureSetupStatus.FAILED
    )
    terminal = RedLivingDexSetupTerminalRecord(
        binding_plan_sha256=plan.plan_sha256,
        slot_binding_sha256=binding.binding_sha256,
        claim_sha256=claim_sha256,
        status=status,
        reason_code=reason_code,
        setup_controller_actions=actions,
        setup_emulator_frames=frames,
        attestation_sha256=None,
    )
    writer.append("failure", terminal.private_dict(), durable=True)
    # Publish the no-retry terminal before finalizing the episode.  A power loss
    # in the tiny publication window can leave an interrupted backing artifact,
    # but the exact terminal remains authoritative and is reconciled on restart.
    _publish_terminal(store, binding, terminal)
    summary = writer.abort(reason_code)
    state = EpisodeArtifactState(
        summary.episode_id,
        "failed",
        reason_code=reason_code,
        manifest_sha256=summary.manifest_sha256,
    )
    disposition = (
        RedLivingDexSetupDisposition.RECOVERED_INTERRUPTED
        if interrupted
        else RedLivingDexSetupDisposition.EXECUTED_FAILED
    )
    return RedLivingDexSetupReceipt(
        binding,
        terminal,
        state,
        disposition,
        None,
    )


def _complete_terminal(
    plan: RedLivingDexSetupBindingPlan,
    binding: RedLivingDexSetupSlotBinding,
    claim_sha256: str,
    execution: RedLivingDexSetupExecution,
) -> RedLivingDexSetupTerminalRecord:
    attestation = execution.capture_attestation
    return RedLivingDexSetupTerminalRecord(
        binding_plan_sha256=plan.plan_sha256,
        slot_binding_sha256=binding.binding_sha256,
        claim_sha256=claim_sha256,
        status=LivingDexCaptureSetupStatus.COMPLETE,
        reason_code=None,
        setup_controller_actions=attestation.setup_controller_actions,
        setup_emulator_frames=attestation.setup_emulator_frames,
        attestation_sha256=attestation.attestation_sha256,
    )


def _claim_record(
    plan: RedLivingDexSetupBindingPlan,
    binding: RedLivingDexSetupSlotBinding,
) -> dict[str, object]:
    return {
        "binding_plan_sha256": plan.plan_sha256,
        "capture_before_behavior_draw": True,
        "claim_before_controller_input": True,
        "complete_menu_sha256": binding.menu_sha256,
        "learner_effects": 0,
        "option_binding_sha256s": [item.binding_sha256 for item in binding.option_bindings],
        "retry_after_controller_input": False,
        "schema": RED_LIVING_DEX_SETUP_CLAIM_SCHEMA,
        "slot_binding_sha256": binding.binding_sha256,
        "slot_sha256": binding.slot_sha256,
    }


def _validate_execution(
    binding: RedLivingDexSetupSlotBinding,
    execution: RedLivingDexSetupExecution,
    *,
    actions: int,
    frames: int,
) -> None:
    if not isinstance(execution, RedLivingDexSetupExecution):
        raise RedLivingDexSetupCampaignError("setup port returned an invalid execution")
    execution.__post_init__()
    if execution.slot_binding_sha256 != binding.binding_sha256:
        raise RedLivingDexSetupCampaignError("setup execution is joined to another slot")
    _require_within_budget(binding, actions=actions, frames=frames)
    attestation = execution.capture_attestation
    if (
        attestation.slot_sha256 != binding.slot_sha256
        or attestation.setup_plan_sha256 != binding.setup_plan_sha256
        or attestation.terminal_predicate_sha256 != binding.terminal_predicate_sha256
        or attestation.observer_contract_sha256 != binding.observer_contract_sha256
        or attestation.root_consumption_sha256 != binding.root_consumption_sha256
        or attestation.state_sha256 != binding.state_sha256
        or attestation.envelope_sha256 != binding.envelope_sha256
        or attestation.menu_sha256 != binding.menu_sha256
        or attestation.observer_binding_sha256 != binding.observer_binding_sha256
        or attestation.available_option_kinds != binding.available_option_kinds
        or attestation.available_family_sha256s != binding.available_family_sha256s
        or attestation.location_sha256 != binding.location_sha256
        or attestation.setup_controller_actions != actions
        or attestation.setup_emulator_frames != frames
    ):
        raise RedLivingDexSetupCampaignError(
            "setup capture attestation differs from its frozen slot binding"
        )
    if len(execution.option_proofs) != len(binding.option_bindings):
        raise RedLivingDexSetupCampaignError(
            "setup execution did not prove every planned menu option"
        )
    for option, proof in zip(
        binding.option_bindings,
        execution.option_proofs,
        strict=True,
    ):
        if (
            proof.option_binding_sha256 != option.binding_sha256
            or proof.fresh_observation_sha256 != option.expected_fresh_observation_sha256
            or proof.provider_offer_sha256 != option.expected_provider_offer_sha256
            or proof.executable_binding_sha256 != option.expected_executable_binding_sha256
        ):
            raise RedLivingDexSetupCampaignError(
                "setup option proof differs from its frozen binding"
            )


def _require_within_budget(
    binding: RedLivingDexSetupSlotBinding,
    *,
    actions: int,
    frames: int,
) -> None:
    slot = _slot_by_sha(binding.slot_sha256)
    if (
        actions > slot.setup.maximum_controller_actions
        or frames > slot.setup.maximum_emulator_frames
    ):
        raise RedLivingDexSetupCampaignError(
            "setup execution exceeded its frozen whole-slot budget"
        )


def _load_complete_execution(
    store: PrivateArtifactRoot,
    plan: RedLivingDexSetupBindingPlan,
    binding: RedLivingDexSetupSlotBinding,
    episode_id: str,
) -> RedLivingDexSetupExecution:
    try:
        reader = store.open_episode(episode_id)
        claims = tuple(reader.iter_stream("claim", max_records=1))
        records = tuple(reader.iter_stream("execution", max_records=1))
    except PrivateArtifactError as error:
        raise RedLivingDexSetupCampaignError(str(error)) from None
    if len(claims) != 1 or claims[0] != _claim_record(plan, binding):
        raise RedLivingDexSetupCampaignError("complete setup artifact has no exact durable claim")
    if len(records) != 1:
        raise RedLivingDexSetupCampaignError("complete setup artifact has no unique execution")
    execution = _restore_execution(records[0])
    attestation = execution.capture_attestation
    _validate_execution(
        binding,
        execution,
        actions=attestation.setup_controller_actions,
        frames=attestation.setup_emulator_frames,
    )
    return execution


def _restore_execution(document: Mapping[str, object]) -> RedLivingDexSetupExecution:
    _exact_keys(
        document,
        {
            "behavior_draws",
            "capture_attestation",
            "learner_labels",
            "learner_outcomes",
            "model_fits",
            "model_predictions",
            "option_proofs",
            "schema",
            "slot_binding_sha256",
            "teacher_queries",
        },
        "setup execution",
    )
    if document["schema"] != RED_LIVING_DEX_SETUP_EXECUTION_SCHEMA:
        raise RedLivingDexSetupCampaignError("setup execution schema differs")
    for key in (
        "behavior_draws",
        "learner_labels",
        "learner_outcomes",
        "model_fits",
        "model_predictions",
        "teacher_queries",
    ):
        if _integer(document[key], f"setup execution {key}") != 0:
            raise RedLivingDexSetupCampaignError(
                "stored setup execution crossed a learner or model boundary"
            )
    raw_proofs = document["option_proofs"]
    if not isinstance(raw_proofs, list):
        raise RedLivingDexSetupCampaignError("setup execution proofs differ")
    return RedLivingDexSetupExecution(
        slot_binding_sha256=_string(
            document["slot_binding_sha256"],
            "setup execution binding",
        ),
        capture_attestation=_restore_capture_attestation(
            _mapping(document["capture_attestation"], "capture attestation")
        ),
        option_proofs=tuple(
            _restore_option_proof(_mapping(item, "setup option proof")) for item in raw_proofs
        ),
    )


def _restore_capture_attestation(
    document: Mapping[str, object],
) -> LivingDexCaptureAttestation:
    expected = {
        "all_available_executors_authenticated",
        "available_family_sha256s",
        "available_option_kinds",
        "captured_before_behavior_draw",
        "complete_menu_observed",
        "envelope_sha256",
        "learner_behavior_draws",
        "learner_controller_actions",
        "learner_labels_emitted",
        "learner_outcomes_observed",
        "learner_root_claims",
        "learner_teacher_queries",
        "location_sha256",
        "menu_sha256",
        "observer_binding_sha256",
        "observer_contract_sha256",
        "one_shot",
        "repeatable",
        "root_consumption_sha256",
        "schema",
        "sealed",
        "setup_controller_actions",
        "setup_emulator_frames",
        "setup_plan_sha256",
        "slot_sha256",
        "state_sha256",
        "terminal_predicate_sha256",
    }
    _exact_keys(document, expected, "capture attestation")
    if document["schema"] != LIVING_DEX_CAPTURE_ATTESTATION_SCHEMA:
        raise RedLivingDexSetupCampaignError("capture attestation schema differs")
    for key in (
        "learner_behavior_draws",
        "learner_controller_actions",
        "learner_labels_emitted",
        "learner_outcomes_observed",
        "learner_root_claims",
        "learner_teacher_queries",
    ):
        if _integer(document[key], f"capture attestation {key}") != 0:
            raise RedLivingDexSetupCampaignError(
                "stored capture attestation crossed a learner boundary"
            )
    raw_kinds = document["available_option_kinds"]
    raw_families = document["available_family_sha256s"]
    if not isinstance(raw_kinds, list) or not isinstance(raw_families, list):
        raise RedLivingDexSetupCampaignError("capture attestation menu bindings differ")
    try:
        kinds = tuple(
            LivingDexOptionKind(_string(item, "capture option kind")) for item in raw_kinds
        )
    except ValueError:
        raise RedLivingDexSetupCampaignError("capture attestation option kind differs") from None
    return LivingDexCaptureAttestation(
        slot_sha256=_string(document["slot_sha256"], "capture slot"),
        setup_plan_sha256=_string(document["setup_plan_sha256"], "capture setup"),
        terminal_predicate_sha256=_string(
            document["terminal_predicate_sha256"],
            "capture terminal predicate",
        ),
        observer_contract_sha256=_string(
            document["observer_contract_sha256"],
            "capture observer contract",
        ),
        root_consumption_sha256=_string(
            document["root_consumption_sha256"],
            "capture root",
        ),
        state_sha256=_string(document["state_sha256"], "capture state"),
        envelope_sha256=_string(document["envelope_sha256"], "capture envelope"),
        menu_sha256=_string(document["menu_sha256"], "capture menu"),
        observer_binding_sha256=_string(
            document["observer_binding_sha256"],
            "capture observer binding",
        ),
        available_option_kinds=kinds,
        available_family_sha256s=tuple(_string(item, "capture family") for item in raw_families),
        location_sha256=_string(document["location_sha256"], "capture location"),
        setup_controller_actions=_integer(
            document["setup_controller_actions"],
            "capture setup actions",
        ),
        setup_emulator_frames=_integer(
            document["setup_emulator_frames"],
            "capture setup frames",
        ),
        repeatable=_boolean(document["repeatable"], "capture repeatability"),
        sealed=_boolean(document["sealed"], "capture sealed flag"),
        one_shot=_boolean(document["one_shot"], "capture one-shot flag"),
        complete_menu_observed=_boolean(
            document["complete_menu_observed"],
            "capture complete-menu flag",
        ),
        all_available_executors_authenticated=_boolean(
            document["all_available_executors_authenticated"],
            "capture executor-authentication flag",
        ),
        captured_before_behavior_draw=_boolean(
            document["captured_before_behavior_draw"],
            "capture behavior boundary",
        ),
    )


def _restore_option_proof(
    document: Mapping[str, object],
) -> RedLivingDexSetupOptionProof:
    _exact_keys(
        document,
        {
            "controller_actions",
            "emulator_frames",
            "executable_binding_sha256",
            "fresh_observation_sha256",
            "option_binding_sha256",
            "provider_offer_authenticated",
            "provider_offer_sha256",
            "schema",
            "transport_terminal_verified",
        },
        "setup option proof",
    )
    if document["schema"] != RED_LIVING_DEX_SETUP_OPTION_PROOF_SCHEMA:
        raise RedLivingDexSetupCampaignError("setup option proof schema differs")
    if (
        _integer(document["controller_actions"], "setup option proof actions") != 0
        or _integer(document["emulator_frames"], "setup option proof frames") != 0
    ):
        raise RedLivingDexSetupCampaignError("setup option proof authentication was actionful")
    return RedLivingDexSetupOptionProof(
        option_binding_sha256=_string(
            document["option_binding_sha256"],
            "setup option proof binding",
        ),
        fresh_observation_sha256=_string(
            document["fresh_observation_sha256"],
            "setup option proof observation",
        ),
        provider_offer_sha256=_string(
            document["provider_offer_sha256"],
            "setup option proof provider offer",
        ),
        executable_binding_sha256=_string(
            document["executable_binding_sha256"],
            "setup option proof executable",
        ),
        transport_terminal_verified=_boolean(
            document["transport_terminal_verified"],
            "setup option proof terminal flag",
        ),
        provider_offer_authenticated=_boolean(
            document["provider_offer_authenticated"],
            "setup option proof provider flag",
        ),
    )


def _find_terminal(
    store: PrivateArtifactRoot,
    plan: RedLivingDexSetupBindingPlan,
    binding: RedLivingDexSetupSlotBinding,
    claim_sha256: str,
) -> RedLivingDexSetupTerminalRecord | None:
    try:
        sealed = store.find_sealed_record(
            _terminal_record_id(binding),
            expected_kind=RED_LIVING_DEX_SETUP_TERMINAL_RECORD_KIND,
        )
    except PrivateArtifactError as error:
        raise RedLivingDexSetupCampaignError(str(error)) from None
    if sealed is None:
        return None
    terminal = _restore_terminal(sealed.read())
    if (
        terminal.binding_plan_sha256 != plan.plan_sha256
        or terminal.slot_binding_sha256 != binding.binding_sha256
        or terminal.claim_sha256 != claim_sha256
    ):
        raise RedLivingDexSetupCampaignError(
            "stored setup terminal is joined to another plan or slot"
        )
    return terminal


def _publish_terminal(
    store: PrivateArtifactRoot,
    binding: RedLivingDexSetupSlotBinding,
    terminal: RedLivingDexSetupTerminalRecord,
) -> None:
    record = terminal.private_dict()
    try:
        sealed = store.publish_sealed_record(
            _terminal_record_id(binding),
            kind=RED_LIVING_DEX_SETUP_TERMINAL_RECORD_KIND,
            record=record,
        )
        if sealed.read() != record:
            raise RedLivingDexSetupCampaignError("setup terminal publication failed verification")
    except RedLivingDexSetupCampaignError:
        raise
    except PrivateArtifactError as error:
        raise RedLivingDexSetupCampaignError(str(error)) from None


def _restore_terminal(
    document: Mapping[str, object],
) -> RedLivingDexSetupTerminalRecord:
    _exact_keys(
        document,
        {
            "attestation_sha256",
            "binding_plan_sha256",
            "claim_sha256",
            "reason_code",
            "retry_allowed",
            "schema",
            "setup_controller_actions",
            "setup_emulator_frames",
            "slot_binding_sha256",
            "status",
        },
        "setup terminal",
    )
    if document["schema"] != RED_LIVING_DEX_SETUP_TERMINAL_SCHEMA:
        raise RedLivingDexSetupCampaignError("setup terminal schema differs")
    if _boolean(document["retry_allowed"], "setup terminal retry flag"):
        raise RedLivingDexSetupCampaignError("stored setup terminal allows retry")
    try:
        status = LivingDexCaptureSetupStatus(_string(document["status"], "setup terminal status"))
    except ValueError:
        raise RedLivingDexSetupCampaignError("setup terminal status differs") from None
    reason = document["reason_code"]
    attestation = document["attestation_sha256"]
    actions = document["setup_controller_actions"]
    frames = document["setup_emulator_frames"]
    if reason is not None and not isinstance(reason, str):
        raise RedLivingDexSetupCampaignError("setup terminal reason differs")
    if attestation is not None and not isinstance(attestation, str):
        raise RedLivingDexSetupCampaignError("setup terminal attestation differs")
    return RedLivingDexSetupTerminalRecord(
        binding_plan_sha256=_string(
            document["binding_plan_sha256"],
            "setup terminal plan",
        ),
        slot_binding_sha256=_string(
            document["slot_binding_sha256"],
            "setup terminal binding",
        ),
        claim_sha256=_string(document["claim_sha256"], "setup terminal claim"),
        status=status,
        reason_code=reason,
        setup_controller_actions=(
            None if actions is None else _integer(actions, "setup terminal actions")
        ),
        setup_emulator_frames=(
            None if frames is None else _integer(frames, "setup terminal frames")
        ),
        attestation_sha256=attestation,
    )


def _receipt_from_terminal(
    store: PrivateArtifactRoot,
    plan: RedLivingDexSetupBindingPlan,
    binding: RedLivingDexSetupSlotBinding,
    state: EpisodeArtifactState,
    terminal: RedLivingDexSetupTerminalRecord,
    *,
    newly_executed: bool,
) -> RedLivingDexSetupReceipt:
    if terminal.status is LivingDexCaptureSetupStatus.COMPLETE:
        if state.status != "complete":
            raise RedLivingDexSetupCampaignError(
                "complete setup terminal lacks a complete backing artifact"
            )
        execution = _load_complete_execution(
            store,
            plan,
            binding,
            state.episode_id,
        )
        disposition = (
            RedLivingDexSetupDisposition.EXECUTED_COMPLETE
            if newly_executed
            else RedLivingDexSetupDisposition.RECOVERED_COMPLETE
        )
    else:
        if state.status not in {"failed", "interrupted"}:
            raise RedLivingDexSetupCampaignError(
                "noncomplete setup terminal lacks a consumed backing artifact"
            )
        execution = None
        disposition = (
            RedLivingDexSetupDisposition.EXECUTED_FAILED
            if newly_executed and terminal.status is LivingDexCaptureSetupStatus.FAILED
            else RedLivingDexSetupDisposition.RECOVERED_FAILED
            if terminal.status is LivingDexCaptureSetupStatus.FAILED
            else RedLivingDexSetupDisposition.RECOVERED_INTERRUPTED
        )
    return RedLivingDexSetupReceipt(
        binding,
        terminal,
        state,
        disposition,
        execution,
    )


def _require_slot_join(
    slot: LivingDexProspectiveCaptureSlot,
    binding: RedLivingDexSetupSlotBinding,
) -> None:
    if (
        binding.slot_sha256 != slot.slot_sha256
        or binding.setup_plan_sha256 != slot.setup.setup_plan_sha256
        or binding.terminal_predicate_sha256 != slot.setup.terminal_predicate_sha256
        or binding.observer_contract_sha256 != slot.setup.observer_contract_sha256
        or binding.partition is not slot.partition
        or binding.available_option_kinds != slot.available_option_kinds
    ):
        raise RedLivingDexSetupCampaignError(
            "setup binding differs from its frozen prospective slot"
        )


def _slot_is_locally_composable(slot: LivingDexProspectiveCaptureSlot) -> bool:
    common: set[str] | None = None
    for kind in slot.available_option_kinds:
        scopes = set(_CAPABILITY_BY_KIND[kind].boundary_scopes)
        common = scopes if common is None else common & scopes
    return bool(common)


def _slot_by_sha(slot_sha256: str) -> LivingDexProspectiveCaptureSlot:
    for slot in build_red_living_dex_prospective_capture_plan().slots:
        if slot.slot_sha256 == slot_sha256:
            return slot
    raise RedLivingDexSetupCampaignError("setup binding names an unknown Red slot")


def _episode_id(binding: RedLivingDexSetupSlotBinding, ordinal: int) -> str:
    return f"redldx-setup-{ordinal:02d}-{binding.binding_sha256[:32]}"


def _terminal_record_id(binding: RedLivingDexSetupSlotBinding) -> str:
    return f"redldx-setup-terminal-{binding.binding_sha256[:32]}"


def _checkpoint(
    meter: RoutedSemanticBudgetMeter,
) -> RoutedSemanticBudgetCheckpoint:
    value = meter.checkpoint()
    if not isinstance(value, RoutedSemanticBudgetCheckpoint):
        raise RedLivingDexSetupCampaignError("setup budget meter returned an invalid checkpoint")
    return value


def _checkpoint_delta(
    before: RoutedSemanticBudgetCheckpoint,
    after: RoutedSemanticBudgetCheckpoint,
) -> tuple[int, int]:
    actions = after.controller_actions - before.controller_actions
    frames = after.emulator_frames - before.emulator_frames
    if actions < 0 or frames < 0:
        raise RedLivingDexSetupCampaignError("setup budget meter moved backwards")
    return actions, frames


def _require_option_kinds(kinds: tuple[LivingDexOptionKind, ...]) -> None:
    if (
        not isinstance(kinds, tuple)
        or len(kinds) < 3
        or len(kinds) != len(set(kinds))
        or any(item not in _GOAL_KIND_BY_OPTION for item in kinds)
    ):
        raise RedLivingDexSetupCampaignError(
            "setup slot needs a complete distinct implemented menu"
        )


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexSetupCampaignError(f"{subject} digest differs")
    return value


def _require_unique(values: Iterable[Hashable], subject: str) -> None:
    rows: tuple[Hashable, ...] = tuple(values)
    if len(rows) != len(set(rows)):
        raise RedLivingDexSetupCampaignError(f"{subject} repeat")


def _exact_keys(
    document: Mapping[str, object],
    expected: set[str],
    subject: str,
) -> None:
    if set(document) != expected:
        raise RedLivingDexSetupCampaignError(f"{subject} fields differ")


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise RedLivingDexSetupCampaignError(f"{subject} differs")
    return value


def _string(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise RedLivingDexSetupCampaignError(f"{subject} differs")
    return value


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise RedLivingDexSetupCampaignError(f"{subject} differs")
    return value


def _boolean(value: object, subject: str) -> bool:
    if type(value) is not bool:  # noqa: E721
        raise RedLivingDexSetupCampaignError(f"{subject} differs")
    return value


__all__ = [
    "RED_LIVING_DEX_SETUP_BINDING_PLAN_SCHEMA",
    "RED_LIVING_DEX_SETUP_COLLECTION_ID",
    "RED_LIVING_DEX_SETUP_PLAN_RECORD_ID",
    "RED_LIVING_DEX_SETUP_RUN_SCHEMA",
    "RedLivingDexControlledSetupFailure",
    "RedLivingDexSetupBindingPlan",
    "RedLivingDexSetupCampaignError",
    "RedLivingDexSetupDisposition",
    "RedLivingDexSetupExecution",
    "RedLivingDexSetupExecutor",
    "RedLivingDexSetupOptionBinding",
    "RedLivingDexSetupOptionProof",
    "RedLivingDexSetupReceipt",
    "RedLivingDexSetupRun",
    "RedLivingDexSetupSlotBinding",
    "RedLivingDexSetupTerminalRecord",
    "RedLivingDexSetupTransportKind",
    "build_red_living_dex_setup_binding_plan",
    "run_red_living_dex_setup_campaign",
]
