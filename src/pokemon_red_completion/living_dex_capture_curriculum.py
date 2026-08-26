"""Title-neutral prospective capture curriculum for living-Pokedex learning.

The legacy Red context bank was recorded for a different experiment and cannot
support the observed-arm 8+4 calibration gate.  This module defines the safer
successor: decide which *semantic decision states* are needed before a title
adapter opens a cartridge, keep deterministic setup work outside the learner's
labels, pre-register every primary and reserve slot, and qualify completed
captures without looking at a selected-arm outcome.

Nothing here can press a button, read a ROM, issue a behavior commitment, claim
a learner decision, observe an outcome, or fit a model.  Red and Crystal adapters
must bind their private state, family, location, and executor identities later.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from fractions import Fraction
from itertools import combinations

from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.provenance import canonical_sha256

LIVING_DEX_CAPTURE_PLAN_SCHEMA = "pokemon.core.living-dex-capture-plan.v1"
LIVING_DEX_CAPTURE_SETUP_SCHEMA = "pokemon.core.living-dex-capture-setup.v1"
LIVING_DEX_CAPTURE_ATTESTATION_SCHEMA = (
    "pokemon.core.private-living-dex-capture-attestation.v1"
)
LIVING_DEX_CAPTURE_TERMINAL_SCHEMA = (
    "pokemon.core.private-living-dex-capture-terminal.v1"
)
LIVING_DEX_CAPTURE_QUALIFICATION_SCHEMA = (
    "pokemon.core.living-dex-capture-qualification.v1"
)
LIVING_DEX_CAPTURE_BEHAVIOR_POLICY = (
    "system-random-rank-full-support-uniform-row-marginal-v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_KIND_ORDER = {kind: index for index, kind in enumerate(LivingDexOptionKind)}


class LivingDexCaptureCurriculumError(ValueError):
    """A prospective capture plan or terminal violates the frozen contract."""


class LivingDexCapturePartition(StrEnum):
    """Partitions admitted by the first observed-arm calibration campaign."""

    TRAIN = "train"
    DEVELOPMENT = "development"


class LivingDexCaptureSetupStatus(StrEnum):
    """Durable terminal for one pre-registered setup slot."""

    COMPLETE = "complete"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class LivingDexCaptureCoverageGate:
    """Minimum learner evidence plus prospectively tolerated setup censoring."""

    minimum_train_examples: int = 8
    minimum_development_examples: int = 4
    minimum_train_option_kinds: int = 4
    minimum_train_families: int = 3
    minimum_development_families: int = 4
    minimum_development_locations: int = 4
    maximum_censored_train_slots: int = 2
    maximum_censored_development_slots: int = 1
    minimum_train_kind_probability_numerator: int = 98
    minimum_train_kind_probability_denominator: int = 100

    def __post_init__(self) -> None:
        positive = (
            self.minimum_train_examples,
            self.minimum_development_examples,
            self.minimum_train_option_kinds,
            self.minimum_train_families,
            self.minimum_development_families,
            self.minimum_development_locations,
            self.minimum_train_kind_probability_numerator,
            self.minimum_train_kind_probability_denominator,
        )
        nonnegative = (
            self.maximum_censored_train_slots,
            self.maximum_censored_development_slots,
        )
        if any(type(value) is not int or value <= 0 for value in positive):  # noqa: E721
            raise LivingDexCaptureCurriculumError(
                "capture coverage positive thresholds differ"
            )
        if any(type(value) is not int or value < 0 for value in nonnegative):  # noqa: E721
            raise LivingDexCaptureCurriculumError(
                "capture coverage censor thresholds differ"
            )
        if self.minimum_train_option_kinds > len(LivingDexOptionKind):
            raise LivingDexCaptureCurriculumError(
                "capture coverage requests unavailable option kinds"
            )
        if self.minimum_train_families > self.minimum_train_examples:
            raise LivingDexCaptureCurriculumError(
                "capture coverage train family threshold is impossible"
            )
        if self.minimum_development_families > (
            self.minimum_development_examples
        ):
            raise LivingDexCaptureCurriculumError(
                "capture coverage development family threshold is impossible"
            )
        if self.minimum_development_locations > (
            self.minimum_development_examples
        ):
            raise LivingDexCaptureCurriculumError(
                "capture coverage development location threshold is impossible"
            )
        probability = self.minimum_train_kind_probability
        if not Fraction(0, 1) < probability <= Fraction(1, 1):
            raise LivingDexCaptureCurriculumError(
                "capture coverage probability threshold differs"
            )

    @property
    def minimum_train_kind_probability(self) -> Fraction:
        return Fraction(
            self.minimum_train_kind_probability_numerator,
            self.minimum_train_kind_probability_denominator,
        )

    def public_dict(self) -> dict[str, object]:
        probability = self.minimum_train_kind_probability
        return {
            "maximum_censored_development_slots": (
                self.maximum_censored_development_slots
            ),
            "maximum_censored_train_slots": self.maximum_censored_train_slots,
            "minimum_development_examples": self.minimum_development_examples,
            "minimum_development_families": self.minimum_development_families,
            "minimum_development_locations": self.minimum_development_locations,
            "minimum_train_examples": self.minimum_train_examples,
            "minimum_train_families": self.minimum_train_families,
            "minimum_train_kind_probability": {
                "denominator": probability.denominator,
                "numerator": probability.numerator,
            },
            "minimum_train_option_kinds": self.minimum_train_option_kinds,
        }


@dataclass(frozen=True, slots=True)
class LivingDexCaptureSetupBoundary:
    """A deterministic title-adapter setup that has no learner authority."""

    setup_plan_sha256: str
    terminal_predicate_sha256: str
    observer_contract_sha256: str
    maximum_controller_actions: int
    maximum_emulator_frames: int
    deterministic_setup: bool = field(default=True, init=False)
    claim_before_controller_input: bool = field(default=True, init=False)
    retry_after_controller_input: bool = field(default=False, init=False)
    capture_before_behavior_draw: bool = field(default=True, init=False)
    learner_labels_emitted: int = field(default=0, init=False)
    learner_behavior_draws: int = field(default=0, init=False)
    learner_outcomes_observed: int = field(default=0, init=False)
    learner_teacher_queries: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        for value, subject in (
            (self.setup_plan_sha256, "setup plan"),
            (self.terminal_predicate_sha256, "terminal predicate"),
            (self.observer_contract_sha256, "observer contract"),
        ):
            _require_sha256(value, subject=subject)
        for numeric_value, subject in (
            (self.maximum_controller_actions, "setup action budget"),
            (self.maximum_emulator_frames, "setup frame budget"),
        ):
            if type(numeric_value) is not int or numeric_value <= 0:  # noqa: E721
                raise LivingDexCaptureCurriculumError(f"{subject} differs")
        if not (
            self.deterministic_setup
            and self.claim_before_controller_input
            and self.capture_before_behavior_draw
            and not self.retry_after_controller_input
        ):
            raise LivingDexCaptureCurriculumError(
                "capture setup authority boundary differs"
            )
        _require_zero_learner_effects(self)

    def private_dict(self) -> dict[str, object]:
        return {
            "capture_before_behavior_draw": self.capture_before_behavior_draw,
            "claim_before_controller_input": self.claim_before_controller_input,
            "deterministic_setup": self.deterministic_setup,
            "learner_behavior_draws": self.learner_behavior_draws,
            "learner_labels_emitted": self.learner_labels_emitted,
            "learner_outcomes_observed": self.learner_outcomes_observed,
            "learner_teacher_queries": self.learner_teacher_queries,
            "maximum_controller_actions": self.maximum_controller_actions,
            "maximum_emulator_frames": self.maximum_emulator_frames,
            "observer_contract_sha256": self.observer_contract_sha256,
            "retry_after_controller_input": self.retry_after_controller_input,
            "schema": LIVING_DEX_CAPTURE_SETUP_SCHEMA,
            "setup_plan_sha256": self.setup_plan_sha256,
            "terminal_predicate_sha256": self.terminal_predicate_sha256,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "capture_before_behavior_draw": self.capture_before_behavior_draw,
            "claim_before_controller_input": self.claim_before_controller_input,
            "deterministic_setup": self.deterministic_setup,
            "learner_behavior_draws": self.learner_behavior_draws,
            "learner_labels_emitted": self.learner_labels_emitted,
            "learner_outcomes_observed": self.learner_outcomes_observed,
            "learner_teacher_queries": self.learner_teacher_queries,
            "maximum_controller_actions": self.maximum_controller_actions,
            "maximum_emulator_frames": self.maximum_emulator_frames,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "retry_after_controller_input": self.retry_after_controller_input,
            "schema": LIVING_DEX_CAPTURE_SETUP_SCHEMA,
        }


@dataclass(frozen=True, slots=True)
class LivingDexProspectiveCaptureSlot:
    """One outcome-blind semantic decision state requested from a title adapter."""

    slot_id: str
    partition: LivingDexCapturePartition
    available_option_kinds: tuple[LivingDexOptionKind, ...]
    family_scope_id: str
    location_scope_id: str
    root_slot_id: str
    setup: LivingDexCaptureSetupBoundary

    def __post_init__(self) -> None:
        for value, subject in (
            (self.slot_id, "capture slot"),
            (self.family_scope_id, "family scope"),
            (self.location_scope_id, "location scope"),
            (self.root_slot_id, "root slot"),
        ):
            _require_safe_id(value, subject=subject)
        if not isinstance(self.partition, LivingDexCapturePartition):
            raise LivingDexCaptureCurriculumError(
                "capture slot partition differs"
            )
        _require_kinds(self.available_option_kinds, minimum=3)
        if not isinstance(self.setup, LivingDexCaptureSetupBoundary):
            raise TypeError("capture slot needs a setup boundary")
        self.setup.__post_init__()

    @property
    def slot_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "available_option_kinds": [
                kind.value for kind in self.available_option_kinds
            ],
            "family_scope_id": self.family_scope_id,
            "location_scope_id": self.location_scope_id,
            "partition": self.partition.value,
            "root_slot_id": self.root_slot_id,
            "schema": "pokemon.core.private-living-dex-capture-slot.v1",
            "setup": self.setup.private_dict(),
            "slot_id": self.slot_id,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "available_option_kinds": [
                kind.value for kind in self.available_option_kinds
            ],
            "complete_distinct_kind_menu_required": True,
            "menu_width": len(self.available_option_kinds),
            "partition": self.partition.value,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "setup": self.setup.public_dict(),
        }


@dataclass(frozen=True, slots=True)
class LivingDexProspectiveCapturePlan:
    """A complete non-adaptive capture campaign frozen before title input."""

    slots: tuple[LivingDexProspectiveCaptureSlot, ...]
    gate: LivingDexCaptureCoverageGate = field(
        default_factory=LivingDexCaptureCoverageGate
    )
    behavior_policy: str = field(
        default=LIVING_DEX_CAPTURE_BEHAVIOR_POLICY,
        init=False,
    )
    execute_every_slot: bool = field(default=True, init=False)
    adaptive_replacement_allowed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.slots, tuple)
            or not self.slots
            or any(
                not isinstance(item, LivingDexProspectiveCaptureSlot)
                for item in self.slots
            )
        ):
            raise LivingDexCaptureCurriculumError(
                "capture plan needs prospective slots"
            )
        if not isinstance(self.gate, LivingDexCaptureCoverageGate):
            raise TypeError("capture plan needs a coverage gate")
        self.gate.__post_init__()
        for item in self.slots:
            item.__post_init__()
        _require_unique((item.slot_id for item in self.slots), "slot identities")
        _require_unique((item.slot_sha256 for item in self.slots), "slot digests")
        _require_unique((item.root_slot_id for item in self.slots), "root slots")
        _require_unique(
            (item.setup.setup_plan_sha256 for item in self.slots),
            "setup plans",
        )
        train = self.partition_slots(LivingDexCapturePartition.TRAIN)
        development = self.partition_slots(LivingDexCapturePartition.DEVELOPMENT)
        if len(train) < (
            self.gate.minimum_train_examples
            + self.gate.maximum_censored_train_slots
        ):
            raise LivingDexCaptureCurriculumError(
                "capture plan lacks pre-registered train reserve"
            )
        if len(development) < (
            self.gate.minimum_development_examples
            + self.gate.maximum_censored_development_slots
        ):
            raise LivingDexCaptureCurriculumError(
                "capture plan lacks pre-registered development reserve"
            )
        development_locations = tuple(
            item.location_scope_id for item in development
        )
        _require_unique(development_locations, "development location scopes")
        train_locations = {item.location_scope_id for item in train}
        if train_locations & set(development_locations):
            raise LivingDexCaptureCurriculumError(
                "capture plan train and development locations overlap"
            )
        train_family_scopes = {item.family_scope_id for item in train}
        development_family_scopes = {
            item.family_scope_id for item in development
        }
        if train_family_scopes & development_family_scopes:
            raise LivingDexCaptureCurriculumError(
                "capture plan train and development family scopes overlap"
            )
        if _minimum_distinct_scope_count(
            train,
            maximum_censored=self.gate.maximum_censored_train_slots,
            scope=lambda item: item.family_scope_id,
        ) < self.gate.minimum_train_families:
            raise LivingDexCaptureCurriculumError(
                "capture plan loses selected train family coverage"
            )
        if _minimum_distinct_scope_count(
            development,
            maximum_censored=self.gate.maximum_censored_development_slots,
            scope=lambda item: item.family_scope_id,
        ) < self.gate.minimum_development_families:
            raise LivingDexCaptureCurriculumError(
                "capture plan loses selected development family coverage"
            )
        offered_train_kinds = {
            kind for item in train for kind in item.available_option_kinds
        }
        if len(offered_train_kinds) < self.gate.minimum_train_option_kinds:
            raise LivingDexCaptureCurriculumError(
                "capture plan lacks offered train option kinds"
            )
        if self.minimum_train_selected_kind_probability < (
            self.gate.minimum_train_kind_probability
        ):
            raise LivingDexCaptureCurriculumError(
                "capture plan selected-kind coverage probability is too small"
            )
        if (
            self.behavior_policy != LIVING_DEX_CAPTURE_BEHAVIOR_POLICY
            or self.execute_every_slot is not True
            or self.adaptive_replacement_allowed
        ):
            raise LivingDexCaptureCurriculumError(
                "capture plan cannot select slots from outcomes"
            )

    def partition_slots(
        self,
        partition: LivingDexCapturePartition,
    ) -> tuple[LivingDexProspectiveCaptureSlot, ...]:
        if not isinstance(partition, LivingDexCapturePartition):
            raise TypeError("capture plan partition differs")
        return tuple(item for item in self.slots if item.partition is partition)

    @property
    def minimum_train_selected_kind_probability(self) -> Fraction:
        return _minimum_kind_coverage_probability(
            self.partition_slots(LivingDexCapturePartition.TRAIN),
            maximum_censored=self.gate.maximum_censored_train_slots,
            minimum_kinds=self.gate.minimum_train_option_kinds,
        )

    @property
    def plan_sha256(self) -> str:
        return canonical_sha256(
            {
                "adaptive_replacement_allowed": self.adaptive_replacement_allowed,
                "behavior_policy": self.behavior_policy,
                "execute_every_slot": self.execute_every_slot,
                "gate": self.gate.public_dict(),
                "schema": LIVING_DEX_CAPTURE_PLAN_SCHEMA,
                "slots": [item.private_dict() for item in self.slots],
            }
        )

    def public_dict(self) -> dict[str, object]:
        partitions = Counter(item.partition.value for item in self.slots)
        widths = Counter(len(item.available_option_kinds) for item in self.slots)
        probability = self.minimum_train_selected_kind_probability
        train = self.partition_slots(LivingDexCapturePartition.TRAIN)
        development = self.partition_slots(LivingDexCapturePartition.DEVELOPMENT)
        return {
            "adaptive_replacement_allowed": self.adaptive_replacement_allowed,
            "behavior_policy": self.behavior_policy,
            "development_family_scope_count": len(
                {item.family_scope_id for item in development}
            ),
            "development_location_scope_count": len(
                {item.location_scope_id for item in development}
            ),
            "execute_every_slot": self.execute_every_slot,
            "family_scope_overlap": 0,
            "gate": self.gate.public_dict(),
            "identity_fields_public": 0,
            "location_scope_overlap": 0,
            "menu_width_counts": _integer_counter(widths),
            "minimum_train_selected_kind_probability": {
                "denominator": probability.denominator,
                "numerator": probability.numerator,
            },
            "minimum_train_selected_kind_probability_role": (
                "prospective_system-commitment_marginal_not_policy-quality"
            ),
            "partition_counts": {
                "development": partitions[LivingDexCapturePartition.DEVELOPMENT.value],
                "train": partitions[LivingDexCapturePartition.TRAIN.value],
            },
            "plan_sha256": self.plan_sha256,
            "private_path_fields": 0,
            "schema": LIVING_DEX_CAPTURE_PLAN_SCHEMA,
            "setup_behavior_draws": 0,
            "setup_learner_labels": 0,
            "setup_outcomes_observed": 0,
            "slot_count": len(self.slots),
            "train_family_scope_count": len(
                {item.family_scope_id for item in train}
            ),
            "train_offered_option_kinds": sorted(
                {
                    kind.value
                    for item in train
                    for kind in item.available_option_kinds
                }
            ),
        }


@dataclass(frozen=True, slots=True)
class LivingDexCaptureAttestation:
    """Private title-adapter proof that one prospective slot became a capture."""

    slot_sha256: str
    setup_plan_sha256: str
    terminal_predicate_sha256: str
    observer_contract_sha256: str
    root_consumption_sha256: str
    state_sha256: str
    envelope_sha256: str
    menu_sha256: str
    observer_binding_sha256: str
    available_option_kinds: tuple[LivingDexOptionKind, ...]
    available_family_sha256s: tuple[str, ...]
    location_sha256: str
    setup_controller_actions: int
    setup_emulator_frames: int
    repeatable: bool = True
    sealed: bool = False
    one_shot: bool = False
    complete_menu_observed: bool = True
    all_available_executors_authenticated: bool = True
    captured_before_behavior_draw: bool = True
    learner_behavior_draws: int = field(default=0, init=False)
    learner_controller_actions: int = field(default=0, init=False)
    learner_labels_emitted: int = field(default=0, init=False)
    learner_outcomes_observed: int = field(default=0, init=False)
    learner_root_claims: int = field(default=0, init=False)
    learner_teacher_queries: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        for value, subject in (
            (self.slot_sha256, "capture slot"),
            (self.setup_plan_sha256, "capture setup"),
            (self.terminal_predicate_sha256, "capture terminal predicate"),
            (self.observer_contract_sha256, "capture observer contract"),
            (self.root_consumption_sha256, "capture root"),
            (self.state_sha256, "capture state"),
            (self.envelope_sha256, "capture envelope"),
            (self.menu_sha256, "capture menu"),
            (self.observer_binding_sha256, "capture observer binding"),
            (self.location_sha256, "capture location"),
        ):
            _require_sha256(value, subject=subject)
        _require_kinds(self.available_option_kinds, minimum=3)
        if (
            not isinstance(self.available_family_sha256s, tuple)
            or len(self.available_family_sha256s)
            != len(self.available_option_kinds)
        ):
            raise LivingDexCaptureCurriculumError(
                "capture family bindings differ from its menu"
            )
        for value in self.available_family_sha256s:
            _require_sha256(value, subject="capture family")
        for numeric_value, subject in (
            (self.setup_controller_actions, "capture setup actions"),
            (self.setup_emulator_frames, "capture setup frames"),
        ):
            if type(numeric_value) is not int or numeric_value < 0:  # noqa: E721
                raise LivingDexCaptureCurriculumError(f"{subject} differ")
        if not (
            self.repeatable
            and not self.sealed
            and not self.one_shot
            and self.complete_menu_observed
            and self.all_available_executors_authenticated
            and self.captured_before_behavior_draw
        ):
            raise LivingDexCaptureCurriculumError(
                "capture safety or repeatability attestation differs"
            )
        _require_zero_learner_effects(self)

    @property
    def attestation_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "all_available_executors_authenticated": (
                self.all_available_executors_authenticated
            ),
            "available_family_sha256s": list(self.available_family_sha256s),
            "available_option_kinds": [
                kind.value for kind in self.available_option_kinds
            ],
            "captured_before_behavior_draw": self.captured_before_behavior_draw,
            "complete_menu_observed": self.complete_menu_observed,
            "envelope_sha256": self.envelope_sha256,
            "learner_behavior_draws": self.learner_behavior_draws,
            "learner_controller_actions": self.learner_controller_actions,
            "learner_labels_emitted": self.learner_labels_emitted,
            "learner_outcomes_observed": self.learner_outcomes_observed,
            "learner_root_claims": self.learner_root_claims,
            "learner_teacher_queries": self.learner_teacher_queries,
            "location_sha256": self.location_sha256,
            "menu_sha256": self.menu_sha256,
            "observer_binding_sha256": self.observer_binding_sha256,
            "observer_contract_sha256": self.observer_contract_sha256,
            "one_shot": self.one_shot,
            "repeatable": self.repeatable,
            "root_consumption_sha256": self.root_consumption_sha256,
            "schema": LIVING_DEX_CAPTURE_ATTESTATION_SCHEMA,
            "sealed": self.sealed,
            "setup_controller_actions": self.setup_controller_actions,
            "setup_emulator_frames": self.setup_emulator_frames,
            "setup_plan_sha256": self.setup_plan_sha256,
            "slot_sha256": self.slot_sha256,
            "state_sha256": self.state_sha256,
            "terminal_predicate_sha256": self.terminal_predicate_sha256,
        }


@dataclass(frozen=True, slots=True)
class LivingDexCaptureSetupTerminal:
    """One durable, non-retryable terminal for every frozen capture slot."""

    slot_sha256: str
    claim_sha256: str
    status: LivingDexCaptureSetupStatus
    setup_controller_actions: int
    setup_emulator_frames: int
    attestation: LivingDexCaptureAttestation | None = None
    retry_allowed: bool = field(default=False, init=False)
    learner_behavior_draws: int = field(default=0, init=False)
    learner_controller_actions: int = field(default=0, init=False)
    learner_labels_emitted: int = field(default=0, init=False)
    learner_outcomes_observed: int = field(default=0, init=False)
    learner_root_claims: int = field(default=0, init=False)
    learner_teacher_queries: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        _require_sha256(self.slot_sha256, subject="capture terminal slot")
        _require_sha256(self.claim_sha256, subject="capture setup claim")
        if not isinstance(self.status, LivingDexCaptureSetupStatus):
            raise LivingDexCaptureCurriculumError(
                "capture setup terminal status differs"
            )
        for value, subject in (
            (self.setup_controller_actions, "terminal setup actions"),
            (self.setup_emulator_frames, "terminal setup frames"),
        ):
            if type(value) is not int or value < 0:  # noqa: E721
                raise LivingDexCaptureCurriculumError(f"{subject} differ")
        if (self.attestation is not None) != (
            self.status is LivingDexCaptureSetupStatus.COMPLETE
        ):
            raise LivingDexCaptureCurriculumError(
                "capture terminal attestation availability differs"
            )
        if self.attestation is not None and (
            self.attestation.slot_sha256 != self.slot_sha256
            or self.attestation.setup_controller_actions
            != self.setup_controller_actions
            or self.attestation.setup_emulator_frames != self.setup_emulator_frames
        ):
            raise LivingDexCaptureCurriculumError(
                "capture terminal and attestation differ"
            )
        if self.retry_allowed:
            raise LivingDexCaptureCurriculumError(
                "claimed capture setup cannot retry"
            )
        _require_zero_learner_effects(self)

    def private_dict(self) -> dict[str, object]:
        return {
            "attestation_sha256": (
                None
                if self.attestation is None
                else self.attestation.attestation_sha256
            ),
            "claim_sha256": self.claim_sha256,
            "learner_behavior_draws": self.learner_behavior_draws,
            "learner_controller_actions": self.learner_controller_actions,
            "learner_labels_emitted": self.learner_labels_emitted,
            "learner_outcomes_observed": self.learner_outcomes_observed,
            "learner_root_claims": self.learner_root_claims,
            "learner_teacher_queries": self.learner_teacher_queries,
            "retry_allowed": self.retry_allowed,
            "schema": LIVING_DEX_CAPTURE_TERMINAL_SCHEMA,
            "setup_controller_actions": self.setup_controller_actions,
            "setup_emulator_frames": self.setup_emulator_frames,
            "slot_sha256": self.slot_sha256,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class LivingDexQualifiedCaptureInventory:
    """Every planned setup terminal reconciled without opening a learner arm."""

    plan: LivingDexProspectiveCapturePlan
    terminals: tuple[LivingDexCaptureSetupTerminal, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.plan, LivingDexProspectiveCapturePlan):
            raise TypeError("capture qualification needs its prospective plan")
        if (
            not isinstance(self.terminals, tuple)
            or any(
                not isinstance(item, LivingDexCaptureSetupTerminal)
                for item in self.terminals
            )
        ):
            raise LivingDexCaptureCurriculumError(
                "capture qualification needs durable terminals"
            )
        slots = {item.slot_sha256: item for item in self.plan.slots}
        self.plan.__post_init__()
        terminal_ids = tuple(item.slot_sha256 for item in self.terminals)
        _require_unique(terminal_ids, "capture terminal slots")
        _require_unique(
            (item.claim_sha256 for item in self.terminals),
            "capture setup claims",
        )
        if set(terminal_ids) != set(slots):
            raise LivingDexCaptureCurriculumError(
                "capture qualification does not reconcile every slot"
            )

        censored = Counter[LivingDexCapturePartition]()
        complete: list[
            tuple[LivingDexProspectiveCaptureSlot, LivingDexCaptureAttestation]
        ] = []
        for terminal in self.terminals:
            terminal.__post_init__()
            slot = slots[terminal.slot_sha256]
            if (
                terminal.setup_controller_actions
                > slot.setup.maximum_controller_actions
                or terminal.setup_emulator_frames > slot.setup.maximum_emulator_frames
            ):
                raise LivingDexCaptureCurriculumError(
                    "capture setup terminal exceeds its frozen budget"
                )
            if terminal.attestation is None:
                censored[slot.partition] += 1
                continue
            attestation = terminal.attestation
            attestation.__post_init__()
            if (
                attestation.setup_plan_sha256 != slot.setup.setup_plan_sha256
                or attestation.terminal_predicate_sha256
                != slot.setup.terminal_predicate_sha256
                or attestation.observer_contract_sha256
                != slot.setup.observer_contract_sha256
                or attestation.available_option_kinds
                != slot.available_option_kinds
            ):
                raise LivingDexCaptureCurriculumError(
                    "capture attestation differs from its prospective slot"
                )
            _require_zero_learner_effects(attestation)
            _require_zero_learner_effects(terminal)
            complete.append((slot, attestation))

        gate = self.plan.gate
        if censored[LivingDexCapturePartition.TRAIN] > (
            gate.maximum_censored_train_slots
        ):
            raise LivingDexCaptureCurriculumError(
                "capture qualification exceeds train censor reserve"
            )
        if censored[LivingDexCapturePartition.DEVELOPMENT] > (
            gate.maximum_censored_development_slots
        ):
            raise LivingDexCaptureCurriculumError(
                "capture qualification exceeds development censor reserve"
            )
        train = tuple(
            pair
            for pair in complete
            if pair[0].partition is LivingDexCapturePartition.TRAIN
        )
        development = tuple(
            pair
            for pair in complete
            if pair[0].partition is LivingDexCapturePartition.DEVELOPMENT
        )
        if len(train) < gate.minimum_train_examples or len(development) < (
            gate.minimum_development_examples
        ):
            raise LivingDexCaptureCurriculumError(
                "capture qualification lacks settled-candidate capacity"
            )

        attestations = tuple(attestation for _, attestation in complete)
        for values, subject in (
            (
                (item.root_consumption_sha256 for item in attestations),
                "capture roots",
            ),
            ((item.state_sha256 for item in attestations), "capture states"),
            ((item.envelope_sha256 for item in attestations), "capture envelopes"),
            (
                (item.observer_binding_sha256 for item in attestations),
                "capture observer bindings",
            ),
        ):
            _require_unique(values, subject)

        # Every logical family scope may span several related setup slots, but
        # two distinct scopes may never share an actual opaque family.  Thus
        # the plan's worst-case surviving scope count applies to the selected
        # arm, not merely to the union of families offered somewhere.
        families_by_scope: dict[str, set[str]] = {}
        for slot, attestation in complete:
            families_by_scope.setdefault(slot.family_scope_id, set()).update(
                attestation.available_family_sha256s
            )
        scope_rows = tuple(families_by_scope.items())
        for index, (left_scope, left_families) in enumerate(scope_rows):
            for right_scope, right_families in scope_rows[index + 1 :]:
                if left_scope != right_scope and left_families & right_families:
                    raise LivingDexCaptureCurriculumError(
                        "capture qualification family scopes overlap"
                    )

        scope_to_location: dict[str, str] = {}
        location_to_scope: dict[str, str] = {}
        for slot, attestation in complete:
            existing = scope_to_location.setdefault(
                slot.location_scope_id,
                attestation.location_sha256,
            )
            if existing != attestation.location_sha256:
                raise LivingDexCaptureCurriculumError(
                    "capture location scope maps to multiple locations"
                )
            existing_scope = location_to_scope.setdefault(
                attestation.location_sha256,
                slot.location_scope_id,
            )
            if existing_scope != slot.location_scope_id:
                raise LivingDexCaptureCurriculumError(
                    "capture location is reused across logical scopes"
                )

        completed_train_slots = tuple(item for item, _ in train)
        probability = _kind_coverage_probability(
            completed_train_slots,
            minimum_kinds=gate.minimum_train_option_kinds,
        )
        if probability < gate.minimum_train_kind_probability:
            raise LivingDexCaptureCurriculumError(
                "capture qualification loses selected-kind power"
            )

    @property
    def qualification_sha256(self) -> str:
        return canonical_sha256(
            {
                "plan_sha256": self.plan.plan_sha256,
                "schema": LIVING_DEX_CAPTURE_QUALIFICATION_SCHEMA,
                "terminals": [item.private_dict() for item in self.terminals],
            }
        )

    def public_dict(self) -> dict[str, object]:
        statuses = Counter(item.status.value for item in self.terminals)
        slot_by_sha = {item.slot_sha256: item for item in self.plan.slots}
        complete = tuple(item for item in self.terminals if item.attestation is not None)
        partition_counts = Counter(
            slot_by_sha[item.slot_sha256].partition.value for item in complete
        )
        train_slots = tuple(
            slot_by_sha[item.slot_sha256]
            for item in complete
            if slot_by_sha[item.slot_sha256].partition
            is LivingDexCapturePartition.TRAIN
        )
        probability = _kind_coverage_probability(
            train_slots,
            minimum_kinds=self.plan.gate.minimum_train_option_kinds,
        )
        return {
            "adaptive_replacement_used": False,
            "all_slots_reconciled": len(self.terminals) == len(self.plan.slots),
            "behavior_draws": 0,
            "controller_authority_attempts": 0,
            "development_complete_count": partition_counts[
                LivingDexCapturePartition.DEVELOPMENT.value
            ],
            "emulator_frames_after_capture": 0,
            "family_scope_overlap": 0,
            "identity_fields_public": 0,
            "learner_controller_actions": 0,
            "learner_labels_emitted": 0,
            "learner_outcomes_observed": 0,
            "learner_root_claims": 0,
            "learner_teacher_queries": 0,
            "location_scope_overlap": 0,
            "minimum_train_selected_kind_probability": {
                "denominator": probability.denominator,
                "numerator": probability.numerator,
            },
            "model_fits": 0,
            "plan_sha256": self.plan.plan_sha256,
            "private_path_fields": 0,
            "qualification_sha256": self.qualification_sha256,
            "retry_allowed": False,
            "schema": LIVING_DEX_CAPTURE_QUALIFICATION_SCHEMA,
            "setup_controller_actions": sum(
                item.setup_controller_actions for item in self.terminals
            ),
            "setup_emulator_frames": sum(
                item.setup_emulator_frames for item in self.terminals
            ),
            "status_counts": {
                status.value: statuses[status.value]
                for status in LivingDexCaptureSetupStatus
            },
            "train_complete_count": partition_counts[
                LivingDexCapturePartition.TRAIN.value
            ],
        }


def qualify_living_dex_capture_inventory(
    plan: LivingDexProspectiveCapturePlan,
    terminals: Sequence[LivingDexCaptureSetupTerminal],
) -> LivingDexQualifiedCaptureInventory:
    """Reconcile a frozen prospective campaign without learner execution."""

    if not isinstance(terminals, Sequence):
        raise TypeError("capture terminals must be a sequence")
    return LivingDexQualifiedCaptureInventory(plan, tuple(terminals))


def _minimum_kind_coverage_probability(
    slots: Sequence[LivingDexProspectiveCaptureSlot],
    *,
    maximum_censored: int,
    minimum_kinds: int,
) -> Fraction:
    frozen = tuple(slots)
    if maximum_censored < 0 or maximum_censored >= len(frozen):
        raise LivingDexCaptureCurriculumError(
            "capture kind probability censor count differs"
        )
    survivor_count = len(frozen) - maximum_censored
    return min(
        _kind_coverage_probability(selection, minimum_kinds=minimum_kinds)
        for selection in combinations(frozen, survivor_count)
    )


def _minimum_distinct_scope_count(
    slots: Sequence[LivingDexProspectiveCaptureSlot],
    *,
    maximum_censored: int,
    scope: Callable[[LivingDexProspectiveCaptureSlot], str],
) -> int:
    frozen = tuple(slots)
    if maximum_censored < 0 or maximum_censored >= len(frozen):
        raise LivingDexCaptureCurriculumError(
            "capture scope censor count differs"
        )
    survivor_count = len(frozen) - maximum_censored
    return min(
        len({scope(item) for item in selection})
        for selection in combinations(frozen, survivor_count)
    )


def _kind_coverage_probability(
    slots: Sequence[LivingDexProspectiveCaptureSlot],
    *,
    minimum_kinds: int,
) -> Fraction:
    states: dict[frozenset[LivingDexOptionKind], Fraction] = {
        frozenset(): Fraction(1, 1)
    }
    for slot in slots:
        probability = Fraction(1, len(slot.available_option_kinds))
        next_states: dict[frozenset[LivingDexOptionKind], Fraction] = {}
        for seen, weight in states.items():
            for kind in slot.available_option_kinds:
                key = seen | {kind}
                next_states[key] = next_states.get(key, Fraction(0, 1)) + (
                    weight * probability
                )
        states = next_states
    return sum(
        (weight for kinds, weight in states.items() if len(kinds) >= minimum_kinds),
        start=Fraction(0, 1),
    )


def _require_kinds(
    kinds: object,
    *,
    minimum: int,
) -> tuple[LivingDexOptionKind, ...]:
    if (
        not isinstance(kinds, tuple)
        or len(kinds) < minimum
        or any(not isinstance(item, LivingDexOptionKind) for item in kinds)
        or len(set(kinds)) != len(kinds)
        or tuple(sorted(kinds, key=_KIND_ORDER.__getitem__)) != kinds
    ):
        raise LivingDexCaptureCurriculumError(
            "capture menu needs canonical distinct option kinds"
        )
    return kinds


def _require_sha256(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise LivingDexCaptureCurriculumError(f"{subject} SHA-256 is invalid")
    return value


def _require_safe_id(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise LivingDexCaptureCurriculumError(f"{subject} identity is invalid")
    return value


def _require_unique(values: Iterable[object], subject: str) -> None:
    frozen: tuple[object, ...] = tuple(values)
    if len(frozen) != len(set(frozen)):
        raise LivingDexCaptureCurriculumError(f"{subject} repeat")


def _require_zero_learner_effects(value: object) -> None:
    fields = (
        "learner_behavior_draws",
        "learner_controller_actions",
        "learner_labels_emitted",
        "learner_outcomes_observed",
        "learner_root_claims",
        "learner_teacher_queries",
    )
    for name in fields:
        current = getattr(value, name, 0)
        if type(current) is not int or current != 0:  # noqa: E721
            raise LivingDexCaptureCurriculumError(
                "capture setup acquired learner authority"
            )


def _integer_counter(values: Mapping[int, int]) -> dict[str, int]:
    return {str(key): values[key] for key in sorted(values)}


__all__ = [
    "LIVING_DEX_CAPTURE_ATTESTATION_SCHEMA",
    "LIVING_DEX_CAPTURE_BEHAVIOR_POLICY",
    "LIVING_DEX_CAPTURE_PLAN_SCHEMA",
    "LIVING_DEX_CAPTURE_QUALIFICATION_SCHEMA",
    "LIVING_DEX_CAPTURE_SETUP_SCHEMA",
    "LIVING_DEX_CAPTURE_TERMINAL_SCHEMA",
    "LivingDexCaptureAttestation",
    "LivingDexCaptureCoverageGate",
    "LivingDexCaptureCurriculumError",
    "LivingDexCapturePartition",
    "LivingDexCaptureSetupBoundary",
    "LivingDexCaptureSetupStatus",
    "LivingDexCaptureSetupTerminal",
    "LivingDexProspectiveCapturePlan",
    "LivingDexProspectiveCaptureSlot",
    "LivingDexQualifiedCaptureInventory",
    "qualify_living_dex_capture_inventory",
]
