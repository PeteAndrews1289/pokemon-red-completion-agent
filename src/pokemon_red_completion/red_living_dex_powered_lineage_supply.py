"""Prospective clean-power lineage supply for the powered Red curriculum.

The clustered powered V2 capacity census proved that the historical context
bank is too small.  This module freezes the next *qualification tranche*
without opening a cartridge: twelve new clean-power episodes, immutable
train/development/contingency ownership, explicit target menus and state
conditioning profiles, and a terminal success-or-failure disposition for
every assignment.

This is not an outcome campaign.  A successful disposition means only that a
new independent root reached its declared authentic-menu boundary.  It does
not choose an option, execute a learner arm, observe an outcome, fit a model,
or authorize population-scale generation.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_episode_lineage import (
    RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID,
    derive_red_living_dex_initial_wait_frames,
    expected_red_living_dex_first_controller_input_frame,
)

RED_LIVING_DEX_POWERED_SUPPLY_PLAN_SCHEMA = "pokemon.red.living-dex-powered-lineage-supply-plan.v1"
RED_LIVING_DEX_POWERED_SUPPLY_ASSIGNMENT_SCHEMA = (
    "pokemon.red.living-dex-powered-lineage-supply-assignment.v1"
)
RED_LIVING_DEX_POWERED_SUPPLY_RECEIPT_SCHEMA = (
    "pokemon.red.living-dex-powered-lineage-supply-receipt.v1"
)
RED_LIVING_DEX_POWERED_SUPPLY_FAILURE_SCHEMA = (
    "pokemon.red.living-dex-powered-lineage-supply-failure.v1"
)
RED_LIVING_DEX_POWERED_SUPPLY_ADMISSION_SCHEMA = (
    "pokemon.red.living-dex-powered-lineage-supply-admission.v1"
)
RED_LIVING_DEX_POWERED_SUPPLY_PREFLIGHT_SCHEMA = (
    "pokemon.red.living-dex-powered-lineage-supply-preflight.v1"
)
RED_LIVING_DEX_POWERED_SUPPLY_CAMPAIGN_ID = "red-living-dex-powered-lineage-yield-tranche-v1"
RED_LIVING_DEX_POWERED_SUPPLY_CAPACITY_RESULT_SHA256 = (
    "6509f735bb88f080c696d8591493d729c3d8d6bc83e7c5f254357ea408a8a013"
)
RED_LIVING_DEX_POWERED_SUPPLY_DESIGN_SHA256 = (
    "c20d2934e8f0632e6bb795ccc15cad2bb5aa9ee8330e08a755801344f9ca5b8d"
)
RED_LIVING_DEX_POWERED_SUPPLY_FIRST_HARNESS_SEED = 4_600_001
RED_LIVING_DEX_POWERED_SUPPLY_ASSIGNMENTS = 12
RED_LIVING_DEX_POWERED_SUPPLY_MINIMUM_ROOTS = 9

PoweredSupplyRole = Literal["train", "development", "contingency"]
PoweredSupplyPartition = Literal["train", "development"]

RED_LIVING_DEX_POWERED_SUPPLY_MINIMUM_ROLE_ROOTS: Mapping[PoweredSupplyRole, int] = {
    "train": 2,
    "development": 6,
    "contingency": 1,
}
RED_LIVING_DEX_POWERED_SUPPLY_DEFICITS: Mapping[str, int] = {
    "train_lineages": 22,
    "development_lineages": 78,
    "contingency_lineages": 3,
    "train_attempts": 44,
    "total_lineages": 103,
}

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")


class RedLivingDexPoweredSupplyError(ValueError):
    """A supply plan or disposition is adaptive, cloned, or off target."""


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexPoweredSupplyError(f"{subject} is invalid")
    return value


def _require_safe_id(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise RedLivingDexPoweredSupplyError(f"{subject} is invalid")
    return value


def _require_uint64(value: object, subject: str) -> int:
    if type(value) is not int or not 0 <= value < (1 << 64):  # noqa: E721
        raise RedLivingDexPoweredSupplyError(f"{subject} is invalid")
    return value


@dataclass(frozen=True, slots=True)
class RedLivingDexPoweredConditioningProfile:
    """One public state-shape request supported by the existing conditioner."""

    profile_id: str
    materializer_mode: str
    target_active_box_count: int | None = None

    def __post_init__(self) -> None:
        _require_safe_id(self.profile_id, "conditioning profile")
        _require_safe_id(self.materializer_mode, "materializer mode")
        if self.target_active_box_count is not None and (
            self.materializer_mode != "storage-ready"
            or type(self.target_active_box_count) is not int  # noqa: E721
            or self.target_active_box_count not in {17, 18, 19}
        ):
            raise RedLivingDexPoweredSupplyError("powered supply active-box target differs")
        if self.materializer_mode == "storage-ready" and self.target_active_box_count is None:
            raise RedLivingDexPoweredSupplyError(
                "powered supply storage profile lacks its box target"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "materializer_mode": self.materializer_mode,
            "profile_id": self.profile_id,
            "target_active_box_count": self.target_active_box_count,
        }


RED_LIVING_DEX_POWERED_CONDITIONING_PROFILES = (
    RedLivingDexPoweredConditioningProfile("acquisition-ready", "acquisition-ready"),
    RedLivingDexPoweredConditioningProfile("damaged-center", "damaged-center"),
    RedLivingDexPoweredConditioningProfile("damaged-pc", "damaged-pc"),
    RedLivingDexPoweredConditioningProfile("evolved-team", "evolved-team"),
    RedLivingDexPoweredConditioningProfile("story-developed", "story-developed"),
    RedLivingDexPoweredConditioningProfile("story-funded", "story-funded"),
    RedLivingDexPoweredConditioningProfile("story-resource-scarce", "story-resource-scarce"),
    RedLivingDexPoweredConditioningProfile("storage-17", "storage-ready", 17),
    RedLivingDexPoweredConditioningProfile("storage-18", "storage-ready", 18),
    RedLivingDexPoweredConditioningProfile("storage-19", "storage-ready", 19),
)
_PROFILE_BY_ID = {
    profile.profile_id: profile for profile in RED_LIVING_DEX_POWERED_CONDITIONING_PROFILES
}

# This is a yield qualification, not the 103-lineage population.  The 3/8/1
# role mix follows the observed 22/78/3 deficit closely enough to exercise all
# admission paths.  Templates span every development menu, the missing fifth
# train location prospectively, and the evolve/unlock kinds that were scarce
# in the action-free census.  No success or failure can alter this schedule.
_QUALIFICATION_TARGETS: tuple[tuple[PoweredSupplyRole, int, str], ...] = (
    ("train", 0, "acquisition-ready"),
    ("train", 4, "evolved-team"),
    ("train", 8, "storage-18"),
    ("development", 10, "storage-17"),
    ("development", 11, "evolved-team"),
    ("development", 12, "acquisition-ready"),
    ("development", 13, "damaged-center"),
    ("development", 14, "storage-19"),
    ("development", 11, "story-developed"),
    ("development", 12, "story-funded"),
    ("development", 13, "story-resource-scarce"),
    ("contingency", 11, "damaged-pc"),
)


def powered_supply_partition(role: PoweredSupplyRole) -> PoweredSupplyPartition:
    """Return immutable learner ownership for one supply role."""

    if role == "train":
        return "train"
    if role in {"development", "contingency"}:
        return "development"
    raise RedLivingDexPoweredSupplyError("powered supply role differs")


def powered_supply_collection_id(plan_sha256: str) -> str:
    """Return the shared generation/admission lock identity for one plan."""

    return f"pwr-supply-{_require_sha256(plan_sha256, 'powered supply plan')}"


def powered_supply_profile(
    profile_id: str,
) -> RedLivingDexPoweredConditioningProfile:
    """Resolve one frozen profile without accepting an arbitrary mode."""

    try:
        return _PROFILE_BY_ID[profile_id]
    except KeyError:
        raise RedLivingDexPoweredSupplyError(
            "powered supply conditioning profile differs"
        ) from None


def compose_red_living_dex_powered_supply_generator_sha256(
    *,
    source_bundle_sha256: str,
    generator_runner_sha256: str,
    conditioner_runner_sha256: str,
) -> str:
    """Bind the exact V2 runner, conditioner, and complete source package."""

    for value, subject in (
        (source_bundle_sha256, "powered supply source bundle"),
        (generator_runner_sha256, "powered supply generator runner"),
        (conditioner_runner_sha256, "powered supply conditioner runner"),
    ):
        _require_sha256(value, subject)
    return canonical_sha256(
        {
            "conditioner_runner_sha256": conditioner_runner_sha256,
            "generator_runner_sha256": generator_runner_sha256,
            "schema": "pokemon.red.living-dex-powered-supply-generator-execution.v1",
            "source_bundle_sha256": source_bundle_sha256,
        }
    )


def compose_red_living_dex_powered_supply_teacher_sha256(
    *, source_bundle_sha256: str, generator_execution_sha256: str
) -> str:
    """Bind the deterministic setup teacher and deliberately absent learner."""

    for value, subject in (
        (source_bundle_sha256, "powered supply source bundle"),
        (generator_execution_sha256, "powered supply generator execution"),
    ):
        _require_sha256(value, subject)
    return canonical_sha256(
        {
            "battle_model": None,
            "checkpoint_id": RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID,
            "generator_execution_sha256": generator_execution_sha256,
            "objective_model": None,
            "schema": "pokemon.red.living-dex-powered-supply-teacher.v1",
            "source_bundle_sha256": source_bundle_sha256,
            "teacher_entrypoint": "pokemon_red_completion.play.run_qualified_play",
            "training_candidate_model": None,
        }
    )


def compose_red_living_dex_powered_supply_runtime_execution_sha256(
    *,
    assignment_id: str,
    plan_sha256: str,
    source_commit: str,
    generator_execution_sha256: str,
    generator_runner_sha256: str,
    runtime_identity_sha256: str,
) -> str:
    """Bind one V2 claim to its exact source, runner, and emulator runtime."""

    for value, subject in (
        (assignment_id, "powered supply assignment"),
        (plan_sha256, "powered supply plan"),
        (generator_execution_sha256, "powered supply generator execution"),
        (generator_runner_sha256, "powered supply generator runner"),
        (runtime_identity_sha256, "powered supply runtime identity"),
    ):
        _require_sha256(value, subject)
    if not isinstance(source_commit, str) or _GIT_OID.fullmatch(source_commit) is None:
        raise RedLivingDexPoweredSupplyError("powered supply runtime source commit differs")
    return canonical_sha256(
        {
            "assignment_id": assignment_id,
            "generator_execution_sha256": generator_execution_sha256,
            "plan_sha256": plan_sha256,
            "runner_sha256": generator_runner_sha256,
            "runtime_identity_sha256": runtime_identity_sha256,
            "schema": "pokemon.red.living-dex-powered-supply-runtime-identity.v2",
            "source_commit": source_commit,
        }
    )


def _canonical_schedule() -> tuple[tuple[int, int, PoweredSupplyRole, int, str], ...]:
    rows: list[tuple[int, int, PoweredSupplyRole, int, str]] = []
    used_waits: set[int] = set()
    candidate_seed = RED_LIVING_DEX_POWERED_SUPPLY_FIRST_HARNESS_SEED
    for role, template_ordinal, profile_id in _QUALIFICATION_TARGETS:
        while derive_red_living_dex_initial_wait_frames(candidate_seed) in used_waits:
            candidate_seed += 1
            _require_uint64(candidate_seed, "powered supply harness seed")
        wait_frames = derive_red_living_dex_initial_wait_frames(candidate_seed)
        used_waits.add(wait_frames)
        rows.append((candidate_seed, wait_frames, role, template_ordinal, profile_id))
        candidate_seed += 1
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class RedLivingDexPoweredSupplyAssignment:
    """One immutable clean-power episode assignment made before gameplay."""

    campaign_id: str
    run_id: str
    ordinal: int
    declared_runs: int
    role: PoweredSupplyRole
    partition: PoweredSupplyPartition
    harness_seed: int
    initial_wait_frames: int
    target_template_ordinal: int
    conditioning_profile_id: str
    target_checkpoint_id: str
    source_bundle_sha256: str
    teacher_execution_sha256: str
    generator_execution_sha256: str
    generator_runner_sha256: str
    conditioner_runner_sha256: str
    runtime_identity_sha256: str
    capacity_result_sha256: str
    powered_design_sha256: str
    assignment_id: str
    root_lineage_id: str
    episode_id: str

    def __post_init__(self) -> None:
        if self.campaign_id != RED_LIVING_DEX_POWERED_SUPPLY_CAMPAIGN_ID:
            raise RedLivingDexPoweredSupplyError("powered supply campaign differs")
        _require_safe_id(self.run_id, "powered supply run")
        if (
            type(self.ordinal) is not int  # noqa: E721
            or type(self.declared_runs) is not int  # noqa: E721
            or not 1 <= self.ordinal <= self.declared_runs
        ):
            raise RedLivingDexPoweredSupplyError("powered supply ordinal differs")
        if self.partition != powered_supply_partition(self.role):
            raise RedLivingDexPoweredSupplyError("powered supply partition differs from its role")
        if (
            type(self.target_template_ordinal) is not int  # noqa: E721
            or not 0 <= self.target_template_ordinal < 15
            or (self.partition == "train" and self.target_template_ordinal >= 10)
            or (self.partition == "development" and self.target_template_ordinal < 10)
        ):
            raise RedLivingDexPoweredSupplyError("powered supply target crosses its partition")
        powered_supply_profile(self.conditioning_profile_id)
        _require_uint64(self.harness_seed, "powered supply harness seed")
        if self.initial_wait_frames != derive_red_living_dex_initial_wait_frames(self.harness_seed):
            raise RedLivingDexPoweredSupplyError("powered supply pre-controller wait differs")
        if self.target_checkpoint_id != RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID:
            raise RedLivingDexPoweredSupplyError("powered supply checkpoint differs")
        for value, subject in (
            (self.source_bundle_sha256, "source bundle"),
            (self.teacher_execution_sha256, "teacher execution"),
            (self.generator_execution_sha256, "generator execution"),
            (self.generator_runner_sha256, "generator runner"),
            (self.conditioner_runner_sha256, "conditioner runner"),
            (self.runtime_identity_sha256, "runtime identity"),
            (self.capacity_result_sha256, "capacity result"),
            (self.powered_design_sha256, "powered design"),
            (self.assignment_id, "assignment"),
        ):
            _require_sha256(value, f"powered supply {subject}")
        if (
            self.capacity_result_sha256 != RED_LIVING_DEX_POWERED_SUPPLY_CAPACITY_RESULT_SHA256
            or self.powered_design_sha256 != RED_LIVING_DEX_POWERED_SUPPLY_DESIGN_SHA256
        ):
            raise RedLivingDexPoweredSupplyError("powered supply evidence binding differs")
        if self.generator_execution_sha256 != (
            compose_red_living_dex_powered_supply_generator_sha256(
                source_bundle_sha256=self.source_bundle_sha256,
                generator_runner_sha256=self.generator_runner_sha256,
                conditioner_runner_sha256=self.conditioner_runner_sha256,
            )
        ):
            raise RedLivingDexPoweredSupplyError("powered supply generator binding differs")
        if self.teacher_execution_sha256 != (
            compose_red_living_dex_powered_supply_teacher_sha256(
                source_bundle_sha256=self.source_bundle_sha256,
                generator_execution_sha256=self.generator_execution_sha256,
            )
        ):
            raise RedLivingDexPoweredSupplyError("powered supply teacher binding differs")
        expected = canonical_sha256(self._commitment_dict())
        if self.assignment_id != expected:
            raise RedLivingDexPoweredSupplyError("powered supply assignment is not prospective")
        if self.root_lineage_id != f"red-ldx-powered-root-{expected}":
            raise RedLivingDexPoweredSupplyError("powered supply root lineage differs")
        if self.episode_id != f"red-ldx-pwr-{expected}":
            raise RedLivingDexPoweredSupplyError("powered supply episode differs")

    @property
    def profile(self) -> RedLivingDexPoweredConditioningProfile:
        return powered_supply_profile(self.conditioning_profile_id)

    def _commitment_dict(self) -> dict[str, object]:
        return {
            "campaign_id": self.campaign_id,
            "capacity_result_sha256": self.capacity_result_sha256,
            "conditioner_runner_sha256": self.conditioner_runner_sha256,
            "conditioning_profile_id": self.conditioning_profile_id,
            "declared_runs": self.declared_runs,
            "generator_execution_sha256": self.generator_execution_sha256,
            "generator_runner_sha256": self.generator_runner_sha256,
            "harness_seed": self.harness_seed,
            "initial_wait_frames": self.initial_wait_frames,
            "ordinal": self.ordinal,
            "partition": self.partition,
            "powered_design_sha256": self.powered_design_sha256,
            "role": self.role,
            "run_id": self.run_id,
            "runtime_identity_sha256": self.runtime_identity_sha256,
            "schema": RED_LIVING_DEX_POWERED_SUPPLY_ASSIGNMENT_SCHEMA,
            "source_bundle_sha256": self.source_bundle_sha256,
            "target_checkpoint_id": self.target_checkpoint_id,
            "target_template_ordinal": self.target_template_ordinal,
            "teacher_execution_sha256": self.teacher_execution_sha256,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            **self._commitment_dict(),
            "assignment_id": self.assignment_id,
            "episode_id": self.episode_id,
            "profile": self.profile.public_dict(),
            "root_lineage_id": self.root_lineage_id,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexPoweredSupplyPlan:
    """One source-bound, non-adaptive 3/8/1 yield qualification tranche."""

    source_commit: str
    source_bundle_sha256: str
    teacher_execution_sha256: str
    generator_execution_sha256: str
    generator_runner_sha256: str
    conditioner_runner_sha256: str
    runtime_identity_sha256: str
    capacity_result_sha256: str
    powered_design_sha256: str
    assignments: tuple[RedLivingDexPoweredSupplyAssignment, ...]

    def __post_init__(self) -> None:
        if _GIT_OID.fullmatch(self.source_commit) is None:
            raise RedLivingDexPoweredSupplyError("powered supply source commit differs")
        for value, subject in (
            (self.source_bundle_sha256, "source bundle"),
            (self.teacher_execution_sha256, "teacher execution"),
            (self.generator_execution_sha256, "generator execution"),
            (self.generator_runner_sha256, "generator runner"),
            (self.conditioner_runner_sha256, "conditioner runner"),
            (self.runtime_identity_sha256, "runtime identity"),
            (self.capacity_result_sha256, "capacity result"),
            (self.powered_design_sha256, "powered design"),
        ):
            _require_sha256(value, f"powered supply {subject}")
        if (
            self.capacity_result_sha256 != RED_LIVING_DEX_POWERED_SUPPLY_CAPACITY_RESULT_SHA256
            or self.powered_design_sha256 != RED_LIVING_DEX_POWERED_SUPPLY_DESIGN_SHA256
        ):
            raise RedLivingDexPoweredSupplyError("powered supply plan evidence differs")
        if self.generator_execution_sha256 != (
            compose_red_living_dex_powered_supply_generator_sha256(
                source_bundle_sha256=self.source_bundle_sha256,
                generator_runner_sha256=self.generator_runner_sha256,
                conditioner_runner_sha256=self.conditioner_runner_sha256,
            )
        ):
            raise RedLivingDexPoweredSupplyError(
                "powered supply plan generator binding differs"
            )
        if self.teacher_execution_sha256 != (
            compose_red_living_dex_powered_supply_teacher_sha256(
                source_bundle_sha256=self.source_bundle_sha256,
                generator_execution_sha256=self.generator_execution_sha256,
            )
        ):
            raise RedLivingDexPoweredSupplyError("powered supply plan teacher binding differs")
        if (
            not isinstance(self.assignments, tuple)
            or len(self.assignments) != RED_LIVING_DEX_POWERED_SUPPLY_ASSIGNMENTS
        ):
            raise RedLivingDexPoweredSupplyError(
                "powered supply qualification tranche size differs"
            )
        for assignment in self.assignments:
            if not isinstance(assignment, RedLivingDexPoweredSupplyAssignment):
                raise TypeError("powered supply assignments differ")
            assignment.__post_init__()
        expected_schedule = _canonical_schedule()
        observed_schedule = tuple(
            (
                item.harness_seed,
                item.initial_wait_frames,
                item.role,
                item.target_template_ordinal,
                item.conditioning_profile_id,
            )
            for item in self.assignments
        )
        if observed_schedule != expected_schedule:
            raise RedLivingDexPoweredSupplyError("powered supply qualification schedule differs")
        if tuple(item.ordinal for item in self.assignments) != tuple(
            range(1, len(self.assignments) + 1)
        ) or any(item.declared_runs != len(self.assignments) for item in self.assignments):
            raise RedLivingDexPoweredSupplyError("powered supply assignment order differs")
        expected_roles = Counter({"train": 3, "development": 8, "contingency": 1})
        if Counter(item.role for item in self.assignments) != expected_roles:
            raise RedLivingDexPoweredSupplyError("powered supply role mix differs")
        for assignment in self.assignments:
            if (
                assignment.source_bundle_sha256 != self.source_bundle_sha256
                or assignment.teacher_execution_sha256 != self.teacher_execution_sha256
                or assignment.generator_execution_sha256 != self.generator_execution_sha256
                or assignment.generator_runner_sha256 != self.generator_runner_sha256
                or assignment.conditioner_runner_sha256 != self.conditioner_runner_sha256
                or assignment.runtime_identity_sha256 != self.runtime_identity_sha256
                or assignment.capacity_result_sha256 != self.capacity_result_sha256
                or assignment.powered_design_sha256 != self.powered_design_sha256
            ):
                raise RedLivingDexPoweredSupplyError("powered supply assignment binding differs")
        for values, subject in (
            ((item.run_id for item in self.assignments), "run"),
            ((item.harness_seed for item in self.assignments), "seed"),
            ((item.initial_wait_frames for item in self.assignments), "wait"),
            ((item.assignment_id for item in self.assignments), "assignment"),
            ((item.root_lineage_id for item in self.assignments), "lineage"),
            ((item.episode_id for item in self.assignments), "episode"),
        ):
            materialized = tuple(values)
            if len(set(materialized)) != len(materialized):
                raise RedLivingDexPoweredSupplyError(f"powered supply repeats a {subject}")

    @property
    def plan_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def assignment(self, assignment_id: str) -> RedLivingDexPoweredSupplyAssignment:
        matches = tuple(item for item in self.assignments if item.assignment_id == assignment_id)
        if len(matches) != 1:
            raise RedLivingDexPoweredSupplyError("powered supply assignment is unavailable")
        return matches[0]

    def public_dict(self) -> dict[str, object]:
        return {
            "assignments": [item.public_dict() for item in self.assignments],
            "capacity_result_sha256": self.capacity_result_sha256,
            "causal_independence": {
                "assignment_before_controller_input": True,
                "clean_power_required": True,
                "distinct_process_episode_required": True,
                "parent_checkpoint_allowed": False,
                "save_state_loads_allowed": 0,
                "state_clone_or_rng_rehash_creates_lineage": False,
            },
            "failure_disposition": {
                "all_assignments_require_terminal_disposition": True,
                "failed_attempts_retained": True,
                "replacement_inside_tranche_allowed": False,
                "retry_after_consumption": False,
            },
            "conditioner_runner_sha256": self.conditioner_runner_sha256,
            "generator_execution_sha256": self.generator_execution_sha256,
            "generator_runner_sha256": self.generator_runner_sha256,
            "outcome_collection_authorized": False,
            "population_scale_authorized": False,
            "powered_design_sha256": self.powered_design_sha256,
            "qualification_gate": {
                "minimum_admitted_roots": RED_LIVING_DEX_POWERED_SUPPLY_MINIMUM_ROOTS,
                "minimum_role_roots": dict(RED_LIVING_DEX_POWERED_SUPPLY_MINIMUM_ROLE_ROOTS),
                "recensus_required_after_disposition": True,
            },
            "recorded_capacity_deficits": dict(RED_LIVING_DEX_POWERED_SUPPLY_DEFICITS),
            "runtime_identity_sha256": self.runtime_identity_sha256,
            "schema": RED_LIVING_DEX_POWERED_SUPPLY_PLAN_SCHEMA,
            "source": {
                "commit": self.source_commit,
                "source_bundle_sha256": self.source_bundle_sha256,
            },
            "teacher_execution_sha256": self.teacher_execution_sha256,
            "tranche_kind": "bounded_yield_qualification",
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexPoweredSupplyReceipt:
    """Path-free proof that one frozen assignment created one usable root."""

    assignment_id: str
    plan_sha256: str
    assignment_claim_sha256: str
    role: PoweredSupplyRole
    partition: PoweredSupplyPartition
    root_lineage_id: str
    episode_id: str
    source_bundle_sha256: str
    teacher_execution_sha256: str
    generator_execution_sha256: str
    runtime_identity_sha256: str
    started_from_clean_power: bool
    distinct_process_episode: bool
    save_state_loads: int
    terminal_state_saves: int
    initial_wait_frames: int
    first_controller_input_frame: int
    trajectory_prefix_sha256: str
    conditioning_profile_id: str
    target_template_ordinal: int
    compatible_template_ordinals: tuple[int, ...]
    observed_pressure_millionths: tuple[int, ...]
    root_consumption_sha256: str
    physical_root_sha256: str
    terminal_state_sha256: str
    terminal_envelope_sha256: str
    terminal_checkpoint_id: str
    controller_actions: int
    emulator_frames: int
    setup_teacher_executions: int
    learner_teacher_queries: int
    learner_labels: int
    learner_outcomes: int
    model_predictions: int
    model_fits: int

    def __post_init__(self) -> None:
        for value, subject in (
            (self.assignment_id, "assignment"),
            (self.plan_sha256, "plan"),
            (self.assignment_claim_sha256, "assignment claim"),
            (self.source_bundle_sha256, "source bundle"),
            (self.teacher_execution_sha256, "teacher execution"),
            (self.generator_execution_sha256, "generator execution"),
            (self.runtime_identity_sha256, "runtime identity"),
            (self.trajectory_prefix_sha256, "trajectory prefix"),
            (self.root_consumption_sha256, "root consumption"),
            (self.physical_root_sha256, "physical root"),
            (self.terminal_state_sha256, "terminal state"),
            (self.terminal_envelope_sha256, "terminal envelope"),
        ):
            _require_sha256(value, f"powered supply receipt {subject}")
        _require_safe_id(self.root_lineage_id, "powered supply receipt lineage")
        _require_safe_id(self.episode_id, "powered supply receipt episode")
        powered_supply_profile(self.conditioning_profile_id)
        if self.partition != powered_supply_partition(self.role):
            raise RedLivingDexPoweredSupplyError("powered supply receipt partition differs")
        if self.started_from_clean_power is not True or (self.distinct_process_episode is not True):
            raise RedLivingDexPoweredSupplyError(
                "powered supply receipt is not a clean independent episode"
            )
        for observed, expected, subject in (
            (self.save_state_loads, 0, "state loads"),
            (self.terminal_state_saves, 1, "terminal saves"),
            (self.setup_teacher_executions, 1, "setup teacher executions"),
            (self.learner_teacher_queries, 0, "learner teacher queries"),
            (self.learner_labels, 0, "learner labels"),
            (self.learner_outcomes, 0, "learner outcomes"),
            (self.model_predictions, 0, "model predictions"),
            (self.model_fits, 0, "model fits"),
        ):
            if observed != expected:
                raise RedLivingDexPoweredSupplyError(f"powered supply receipt {subject} differ")
        if self.first_controller_input_frame != (
            expected_red_living_dex_first_controller_input_frame(self.initial_wait_frames)
        ):
            raise RedLivingDexPoweredSupplyError(
                "powered supply receipt controller boundary differs"
            )
        if (
            not isinstance(self.compatible_template_ordinals, tuple)
            or tuple(sorted(set(self.compatible_template_ordinals)))
            != self.compatible_template_ordinals
            or self.target_template_ordinal not in self.compatible_template_ordinals
            or any(
                type(value) is not int or not 0 <= value < 15  # noqa: E721
                for value in self.compatible_template_ordinals
            )
            or any(
                (value < 10) != (self.partition == "train")
                for value in self.compatible_template_ordinals
            )
        ):
            raise RedLivingDexPoweredSupplyError("powered supply receipt menu support differs")
        if (
            not isinstance(self.observed_pressure_millionths, tuple)
            or len(self.observed_pressure_millionths) != 7
            or any(
                type(value) is not int or not 0 <= value <= 1_000_000  # noqa: E721
                for value in self.observed_pressure_millionths
            )
        ):
            raise RedLivingDexPoweredSupplyError("powered supply receipt pressure vector differs")
        expected_physical = canonical_sha256(
            {
                "envelope_sha256": self.terminal_envelope_sha256,
                "schema": "pokemon.red.private-physical-setup-root.v1",
                "state_sha256": self.terminal_state_sha256,
            }
        )
        if self.physical_root_sha256 != expected_physical:
            raise RedLivingDexPoweredSupplyError("powered supply receipt physical root differs")
        if self.root_consumption_sha256 != root_consumption_sha256(
            state_sha256=self.terminal_state_sha256,
            envelope_sha256=self.terminal_envelope_sha256,
        ):
            raise RedLivingDexPoweredSupplyError("powered supply receipt consumption root differs")
        if self.terminal_checkpoint_id != RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID:
            raise RedLivingDexPoweredSupplyError("powered supply receipt checkpoint differs")
        if (
            type(self.controller_actions) is not int  # noqa: E721
            or self.controller_actions <= 0
            or type(self.emulator_frames) is not int  # noqa: E721
            or self.emulator_frames <= self.first_controller_input_frame
        ):
            raise RedLivingDexPoweredSupplyError("powered supply receipt lacks an executed episode")

    def public_dict(self) -> dict[str, object]:
        return {
            "assignment_claim_sha256": self.assignment_claim_sha256,
            "assignment_id": self.assignment_id,
            "compatible_template_ordinals": list(self.compatible_template_ordinals),
            "conditioning_profile_id": self.conditioning_profile_id,
            "controller_actions": self.controller_actions,
            "distinct_process_episode": self.distinct_process_episode,
            "emulator_frames": self.emulator_frames,
            "episode_id": self.episode_id,
            "first_controller_input_frame": self.first_controller_input_frame,
            "generator_execution_sha256": self.generator_execution_sha256,
            "initial_wait_frames": self.initial_wait_frames,
            "learner_labels": self.learner_labels,
            "learner_outcomes": self.learner_outcomes,
            "learner_teacher_queries": self.learner_teacher_queries,
            "model_fits": self.model_fits,
            "model_predictions": self.model_predictions,
            "observed_pressure_millionths": list(self.observed_pressure_millionths),
            "partition": self.partition,
            "physical_root_sha256": self.physical_root_sha256,
            "plan_sha256": self.plan_sha256,
            "role": self.role,
            "root_consumption_sha256": self.root_consumption_sha256,
            "root_lineage_id": self.root_lineage_id,
            "runtime_identity_sha256": self.runtime_identity_sha256,
            "save_state_loads": self.save_state_loads,
            "schema": RED_LIVING_DEX_POWERED_SUPPLY_RECEIPT_SCHEMA,
            "setup_teacher_executions": self.setup_teacher_executions,
            "source_bundle_sha256": self.source_bundle_sha256,
            "started_from_clean_power": self.started_from_clean_power,
            "target_template_ordinal": self.target_template_ordinal,
            "teacher_execution_sha256": self.teacher_execution_sha256,
            "terminal_checkpoint_id": self.terminal_checkpoint_id,
            "terminal_envelope_sha256": self.terminal_envelope_sha256,
            "terminal_state_saves": self.terminal_state_saves,
            "terminal_state_sha256": self.terminal_state_sha256,
            "trajectory_prefix_sha256": self.trajectory_prefix_sha256,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexPoweredSupplyFailure:
    """Terminal no-retry disposition for one assignment without a root."""

    assignment_id: str
    plan_sha256: str
    role: PoweredSupplyRole
    partition: PoweredSupplyPartition
    source_bundle_sha256: str
    teacher_execution_sha256: str
    generator_execution_sha256: str
    assignment_claim_sha256: str | None
    failure_stage: str
    effects_known: bool
    controller_actions: int | None
    emulator_frames: int | None
    attempt_consumed: bool = True
    retry_allowed: bool = False
    terminal_root_generated: bool = False

    def __post_init__(self) -> None:
        for value, subject in (
            (self.assignment_id, "assignment"),
            (self.plan_sha256, "plan"),
            (self.source_bundle_sha256, "source"),
            (self.teacher_execution_sha256, "teacher"),
            (self.generator_execution_sha256, "generator"),
        ):
            _require_sha256(value, f"powered supply failure {subject}")
        if self.assignment_claim_sha256 is not None:
            _require_sha256(
                self.assignment_claim_sha256,
                "powered supply failure assignment claim",
            )
        if self.partition != powered_supply_partition(self.role):
            raise RedLivingDexPoweredSupplyError("powered supply failure partition differs")
        _require_safe_id(self.failure_stage, "powered supply failure stage")
        if (
            self.attempt_consumed is not True
            or self.retry_allowed is not False
            or self.terminal_root_generated is not False
        ):
            raise RedLivingDexPoweredSupplyError("powered supply failure is not terminal")
        if self.effects_known:
            if any(
                type(value) is not int or value < 0  # noqa: E721
                for value in (self.controller_actions, self.emulator_frames)
            ):
                raise RedLivingDexPoweredSupplyError("powered supply failure effects differ")
        elif self.controller_actions is not None or self.emulator_frames is not None:
            raise RedLivingDexPoweredSupplyError(
                "powered supply failure overstates unknown effects"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "assignment_claim_sha256": self.assignment_claim_sha256,
            "assignment_id": self.assignment_id,
            "attempt_consumed": self.attempt_consumed,
            "controller_actions": self.controller_actions,
            "effects_known": self.effects_known,
            "emulator_frames": self.emulator_frames,
            "failure_stage": self.failure_stage,
            "generator_execution_sha256": self.generator_execution_sha256,
            "learner_labels": None,
            "learner_outcomes": None,
            "model_fits": None,
            "model_predictions": None,
            "partition": self.partition,
            "plan_sha256": self.plan_sha256,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "retry_allowed": self.retry_allowed,
            "role": self.role,
            "schema": RED_LIVING_DEX_POWERED_SUPPLY_FAILURE_SCHEMA,
            "source_bundle_sha256": self.source_bundle_sha256,
            "teacher_execution_sha256": self.teacher_execution_sha256,
            "terminal_root_generated": self.terminal_root_generated,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexPoweredSupplyAdmission:
    """Complete tranche disposition; always requires a new action-free census."""

    plan_sha256: str
    runtime_identity_sha256: str
    roots_admitted: int
    attempts_failed: int
    admitted_role_counts: tuple[tuple[str, int], ...]
    qualification_passed: bool

    def __post_init__(self) -> None:
        _require_sha256(self.plan_sha256, "powered supply admission plan")
        _require_sha256(
            self.runtime_identity_sha256,
            "powered supply admission runtime identity",
        )
        if (
            type(self.roots_admitted) is not int  # noqa: E721
            or type(self.attempts_failed) is not int  # noqa: E721
            or self.roots_admitted < 0
            or self.attempts_failed < 0
            or self.roots_admitted + self.attempts_failed
            != RED_LIVING_DEX_POWERED_SUPPLY_ASSIGNMENTS
        ):
            raise RedLivingDexPoweredSupplyError(
                "powered supply admission denominator differs"
            )
        if (
            not isinstance(self.admitted_role_counts, tuple)
            or tuple(sorted(self.admitted_role_counts)) != self.admitted_role_counts
            or len({role for role, _count in self.admitted_role_counts})
            != len(self.admitted_role_counts)
            or any(
                role not in {"train", "development", "contingency"}
                or type(count) is not int  # noqa: E721
                or count <= 0
                for role, count in self.admitted_role_counts
            )
            or sum(count for _role, count in self.admitted_role_counts)
            != self.roots_admitted
        ):
            raise RedLivingDexPoweredSupplyError(
                "powered supply admission role counts differ"
            )
        role_counts = dict(self.admitted_role_counts)
        expected_pass = (
            self.roots_admitted >= RED_LIVING_DEX_POWERED_SUPPLY_MINIMUM_ROOTS
            and all(
                role_counts.get(role, 0) >= minimum
                for role, minimum in RED_LIVING_DEX_POWERED_SUPPLY_MINIMUM_ROLE_ROOTS.items()
            )
        )
        if type(self.qualification_passed) is not bool or (  # noqa: E721
            self.qualification_passed != expected_pass
        ):
            raise RedLivingDexPoweredSupplyError(
                "powered supply admission decision differs"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "admitted_role_counts": dict(self.admitted_role_counts),
            "attempts_failed": self.attempts_failed,
            "attempts_total": self.roots_admitted + self.attempts_failed,
            "collection_authorized": False,
            "model_fits": 0,
            "model_predictions": 0,
            "outcomes": 0,
            "plan_sha256": self.plan_sha256,
            "population_scale_authorized": False,
            "qualification_passed": self.qualification_passed,
            "recensus_required": True,
            "roots_admitted": self.roots_admitted,
            "runtime_identity_sha256": self.runtime_identity_sha256,
            "schema": RED_LIVING_DEX_POWERED_SUPPLY_ADMISSION_SCHEMA,
            "status": (
                "bounded_yield_qualification_passed_pending_recensus"
                if self.qualification_passed
                else "bounded_yield_qualification_failed_population_closed"
            ),
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexPoweredSupplyPreflight:
    """Zero-effect proof that the immutable qualification plan is coherent."""

    plan_sha256: str
    assignments: int
    role_counts: tuple[tuple[str, int], ...]
    target_template_count: int
    conditioning_profile_count: int

    def public_dict(self) -> dict[str, object]:
        return {
            "assignments": self.assignments,
            "behavior_draws": 0,
            "collection_authorized": False,
            "conditioning_profile_count": self.conditioning_profile_count,
            "controller_actions": 0,
            "emulator_frames": 0,
            "learner_labels": 0,
            "learner_outcomes": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "plan_sha256": self.plan_sha256,
            "population_scale_authorized": False,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "provider_executions": 0,
            "role_counts": dict(self.role_counts),
            "root_claims": 0,
            "root_generation_executions": 0,
            "schema": RED_LIVING_DEX_POWERED_SUPPLY_PREFLIGHT_SCHEMA,
            "status": "bounded_powered_lineage_supply_plan_preflight_passed",
            "target_template_count": self.target_template_count,
            "teacher_queries": 0,
        }


def build_red_living_dex_powered_supply_plan(
    *,
    source_commit: str,
    source_bundle_sha256: str,
    teacher_execution_sha256: str,
    generator_execution_sha256: str,
    generator_runner_sha256: str,
    conditioner_runner_sha256: str,
    runtime_identity_sha256: str,
) -> RedLivingDexPoweredSupplyPlan:
    """Build the sole canonical 12-world V2 yield qualification plan."""

    schedule = _canonical_schedule()
    assignments: list[RedLivingDexPoweredSupplyAssignment] = []
    for ordinal, (
        harness_seed,
        wait_frames,
        role,
        target_template_ordinal,
        profile_id,
    ) in enumerate(schedule, start=1):
        partition = powered_supply_partition(role)
        commitment = {
            "campaign_id": RED_LIVING_DEX_POWERED_SUPPLY_CAMPAIGN_ID,
            "capacity_result_sha256": (RED_LIVING_DEX_POWERED_SUPPLY_CAPACITY_RESULT_SHA256),
            "conditioner_runner_sha256": conditioner_runner_sha256,
            "conditioning_profile_id": profile_id,
            "declared_runs": len(schedule),
            "generator_execution_sha256": generator_execution_sha256,
            "generator_runner_sha256": generator_runner_sha256,
            "harness_seed": harness_seed,
            "initial_wait_frames": wait_frames,
            "ordinal": ordinal,
            "partition": partition,
            "powered_design_sha256": RED_LIVING_DEX_POWERED_SUPPLY_DESIGN_SHA256,
            "role": role,
            "run_id": f"red-ldx-powered-yield-{ordinal:02d}",
            "runtime_identity_sha256": runtime_identity_sha256,
            "schema": RED_LIVING_DEX_POWERED_SUPPLY_ASSIGNMENT_SCHEMA,
            "source_bundle_sha256": source_bundle_sha256,
            "target_checkpoint_id": RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID,
            "target_template_ordinal": target_template_ordinal,
            "teacher_execution_sha256": teacher_execution_sha256,
        }
        assignment_id = canonical_sha256(commitment)
        assignments.append(
            RedLivingDexPoweredSupplyAssignment(
                campaign_id=RED_LIVING_DEX_POWERED_SUPPLY_CAMPAIGN_ID,
                run_id=f"red-ldx-powered-yield-{ordinal:02d}",
                ordinal=ordinal,
                declared_runs=len(schedule),
                role=role,
                partition=partition,
                harness_seed=harness_seed,
                initial_wait_frames=wait_frames,
                target_template_ordinal=target_template_ordinal,
                conditioning_profile_id=profile_id,
                target_checkpoint_id=RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID,
                source_bundle_sha256=source_bundle_sha256,
                teacher_execution_sha256=teacher_execution_sha256,
                generator_execution_sha256=generator_execution_sha256,
                generator_runner_sha256=generator_runner_sha256,
                conditioner_runner_sha256=conditioner_runner_sha256,
                runtime_identity_sha256=runtime_identity_sha256,
                capacity_result_sha256=(RED_LIVING_DEX_POWERED_SUPPLY_CAPACITY_RESULT_SHA256),
                powered_design_sha256=(RED_LIVING_DEX_POWERED_SUPPLY_DESIGN_SHA256),
                assignment_id=assignment_id,
                root_lineage_id=f"red-ldx-powered-root-{assignment_id}",
                episode_id=f"red-ldx-pwr-{assignment_id}",
            )
        )
    return RedLivingDexPoweredSupplyPlan(
        source_commit=source_commit,
        source_bundle_sha256=source_bundle_sha256,
        teacher_execution_sha256=teacher_execution_sha256,
        generator_execution_sha256=generator_execution_sha256,
        generator_runner_sha256=generator_runner_sha256,
        conditioner_runner_sha256=conditioner_runner_sha256,
        runtime_identity_sha256=runtime_identity_sha256,
        capacity_result_sha256=(RED_LIVING_DEX_POWERED_SUPPLY_CAPACITY_RESULT_SHA256),
        powered_design_sha256=RED_LIVING_DEX_POWERED_SUPPLY_DESIGN_SHA256,
        assignments=tuple(assignments),
    )


def preflight_red_living_dex_powered_supply_plan(
    plan: RedLivingDexPoweredSupplyPlan,
) -> RedLivingDexPoweredSupplyPreflight:
    """Validate one plan without accepting any effect-bearing callback."""

    if not isinstance(plan, RedLivingDexPoweredSupplyPlan):
        raise TypeError("powered supply preflight needs its plan")
    plan.__post_init__()
    return RedLivingDexPoweredSupplyPreflight(
        plan_sha256=plan.plan_sha256,
        assignments=len(plan.assignments),
        role_counts=tuple(sorted(Counter(item.role for item in plan.assignments).items())),
        target_template_count=len({item.target_template_ordinal for item in plan.assignments}),
        conditioning_profile_count=len({item.conditioning_profile_id for item in plan.assignments}),
    )


def admit_red_living_dex_powered_supply_tranche(
    plan: RedLivingDexPoweredSupplyPlan,
    receipts: tuple[RedLivingDexPoweredSupplyReceipt, ...],
    failures: tuple[RedLivingDexPoweredSupplyFailure, ...],
) -> RedLivingDexPoweredSupplyAdmission:
    """Admit a complete fixed denominator without replacements or retries."""

    if not isinstance(plan, RedLivingDexPoweredSupplyPlan):
        raise TypeError("powered supply admission needs its plan")
    plan.__post_init__()
    if not isinstance(receipts, tuple) or any(
        not isinstance(item, RedLivingDexPoweredSupplyReceipt) for item in receipts
    ):
        raise TypeError("powered supply admission needs receipt tuples")
    if not isinstance(failures, tuple) or any(
        not isinstance(item, RedLivingDexPoweredSupplyFailure) for item in failures
    ):
        raise TypeError("powered supply admission needs failure tuples")
    dispositions: dict[
        str, RedLivingDexPoweredSupplyReceipt | RedLivingDexPoweredSupplyFailure
    ] = {}
    for item in receipts:
        item.__post_init__()
        if item.assignment_id in dispositions:
            raise RedLivingDexPoweredSupplyError("powered supply disposition repeats an assignment")
        dispositions[item.assignment_id] = item
    for failure in failures:
        failure.__post_init__()
        if failure.assignment_id in dispositions:
            raise RedLivingDexPoweredSupplyError("powered supply disposition repeats an assignment")
        dispositions[failure.assignment_id] = failure
    expected = {item.assignment_id for item in plan.assignments}
    if set(dispositions) != expected:
        raise RedLivingDexPoweredSupplyError("powered supply disposition denominator is incomplete")
    for assignment in plan.assignments:
        disposition = dispositions[assignment.assignment_id]
        if (
            disposition.plan_sha256 != plan.plan_sha256
            or disposition.role != assignment.role
            or disposition.partition != assignment.partition
            or disposition.source_bundle_sha256 != assignment.source_bundle_sha256
            or disposition.teacher_execution_sha256 != assignment.teacher_execution_sha256
            or disposition.generator_execution_sha256 != assignment.generator_execution_sha256
        ):
            raise RedLivingDexPoweredSupplyError(
                "powered supply disposition differs from its assignment"
            )
        if isinstance(disposition, RedLivingDexPoweredSupplyReceipt) and (
            disposition.root_lineage_id != assignment.root_lineage_id
            or disposition.runtime_identity_sha256 != assignment.runtime_identity_sha256
            or disposition.episode_id != assignment.episode_id
            or disposition.initial_wait_frames != assignment.initial_wait_frames
            or disposition.conditioning_profile_id != assignment.conditioning_profile_id
            or disposition.target_template_ordinal != assignment.target_template_ordinal
            or disposition.terminal_checkpoint_id != assignment.target_checkpoint_id
        ):
            raise RedLivingDexPoweredSupplyError(
                "powered supply receipt missed its prospective target"
            )
    for values, subject in (
        ((item.assignment_claim_sha256 for item in receipts), "assignment claim"),
        ((item.root_lineage_id for item in receipts), "root lineage"),
        ((item.physical_root_sha256 for item in receipts), "physical root"),
        ((item.trajectory_prefix_sha256 for item in receipts), "trajectory"),
        ((item.terminal_state_sha256 for item in receipts), "terminal state"),
        ((item.terminal_envelope_sha256 for item in receipts), "terminal envelope"),
    ):
        materialized = tuple(values)
        if len(set(materialized)) != len(materialized):
            raise RedLivingDexPoweredSupplyError(f"powered supply repeats a {subject}")
    role_counts = Counter(item.role for item in receipts)
    qualification_passed = len(receipts) >= RED_LIVING_DEX_POWERED_SUPPLY_MINIMUM_ROOTS and all(
        role_counts[role] >= minimum
        for role, minimum in (RED_LIVING_DEX_POWERED_SUPPLY_MINIMUM_ROLE_ROOTS.items())
    )
    return RedLivingDexPoweredSupplyAdmission(
        plan_sha256=plan.plan_sha256,
        runtime_identity_sha256=plan.runtime_identity_sha256,
        roots_admitted=len(receipts),
        attempts_failed=len(failures),
        admitted_role_counts=tuple(sorted(role_counts.items())),
        qualification_passed=qualification_passed,
    )


def encode_red_living_dex_powered_supply_plan(
    plan: RedLivingDexPoweredSupplyPlan,
) -> bytes:
    """Encode one canonical path-free plan."""

    if not isinstance(plan, RedLivingDexPoweredSupplyPlan):
        raise TypeError("powered supply encoder needs its plan")
    plan.__post_init__()
    return _canonical_line(plan.public_dict())


def encode_red_living_dex_powered_supply_receipt(
    receipt: RedLivingDexPoweredSupplyReceipt,
) -> bytes:
    """Encode one canonical path-free successful disposition."""

    if not isinstance(receipt, RedLivingDexPoweredSupplyReceipt):
        raise TypeError("powered supply receipt encoder needs its receipt")
    receipt.__post_init__()
    return _canonical_line(receipt.public_dict())


def encode_red_living_dex_powered_supply_failure(
    failure: RedLivingDexPoweredSupplyFailure,
) -> bytes:
    """Encode one canonical path-free terminal failed disposition."""

    if not isinstance(failure, RedLivingDexPoweredSupplyFailure):
        raise TypeError("powered supply failure encoder needs its failure")
    failure.__post_init__()
    return _canonical_line(failure.public_dict())


def encode_red_living_dex_powered_supply_admission(
    admission: RedLivingDexPoweredSupplyAdmission,
) -> bytes:
    """Encode the action-free complete-tranche decision."""

    if not isinstance(admission, RedLivingDexPoweredSupplyAdmission):
        raise TypeError("powered supply admission encoder needs its admission")
    admission.__post_init__()
    return _canonical_line(admission.public_dict())


def parse_red_living_dex_powered_supply_plan(
    payload: bytes,
) -> RedLivingDexPoweredSupplyPlan:
    """Strictly reopen one canonical public supply plan."""

    value = _decode_canonical(payload, "powered supply plan")
    _exact_keys(
        value,
        {
            "assignments",
            "capacity_result_sha256",
            "causal_independence",
            "conditioner_runner_sha256",
            "failure_disposition",
            "generator_execution_sha256",
            "generator_runner_sha256",
            "outcome_collection_authorized",
            "population_scale_authorized",
            "powered_design_sha256",
            "qualification_gate",
            "recorded_capacity_deficits",
            "runtime_identity_sha256",
            "schema",
            "source",
            "teacher_execution_sha256",
            "tranche_kind",
        },
    )
    source = _mapping(value["source"], "powered supply source")
    _exact_keys(source, {"commit", "source_bundle_sha256"})
    raw_assignments = value["assignments"]
    if not isinstance(raw_assignments, list):
        raise RedLivingDexPoweredSupplyError("powered supply plan assignments differ")
    assignments = tuple(_parse_assignment(item) for item in raw_assignments)
    plan = RedLivingDexPoweredSupplyPlan(
        source_commit=_text(source["commit"], "powered supply source commit"),
        source_bundle_sha256=_text(source["source_bundle_sha256"], "powered supply source bundle"),
        teacher_execution_sha256=_text(
            value["teacher_execution_sha256"],
            "powered supply teacher execution",
        ),
        generator_execution_sha256=_text(
            value["generator_execution_sha256"],
            "powered supply generator execution",
        ),
        generator_runner_sha256=_text(
            value["generator_runner_sha256"],
            "powered supply generator runner",
        ),
        conditioner_runner_sha256=_text(
            value["conditioner_runner_sha256"],
            "powered supply conditioner runner",
        ),
        runtime_identity_sha256=_text(
            value["runtime_identity_sha256"],
            "powered supply runtime identity",
        ),
        capacity_result_sha256=_text(
            value["capacity_result_sha256"],
            "powered supply capacity result",
        ),
        powered_design_sha256=_text(value["powered_design_sha256"], "powered supply design"),
        assignments=assignments,
    )
    if value != plan.public_dict():
        raise RedLivingDexPoweredSupplyError("powered supply plan authority boundary differs")
    return plan


def parse_red_living_dex_powered_supply_receipt(
    payload: bytes,
) -> RedLivingDexPoweredSupplyReceipt:
    """Strictly reopen one canonical successful disposition."""

    value = _decode_canonical(payload, "powered supply receipt")
    receipt = _parse_receipt(value)
    if value != receipt.public_dict():
        raise RedLivingDexPoweredSupplyError(
            "powered supply receipt authority boundary differs"
        )
    return receipt


def parse_red_living_dex_powered_supply_failure(
    payload: bytes,
) -> RedLivingDexPoweredSupplyFailure:
    """Strictly reopen one canonical terminal failed disposition."""

    value = _decode_canonical(payload, "powered supply failure")
    failure = _parse_failure(value)
    if value != failure.public_dict():
        raise RedLivingDexPoweredSupplyError(
            "powered supply failure authority boundary differs"
        )
    return failure


def parse_red_living_dex_powered_supply_admission(
    payload: bytes,
) -> RedLivingDexPoweredSupplyAdmission:
    """Strictly reopen one complete-tranche action-free decision."""

    value = _decode_canonical(payload, "powered supply admission")
    _exact_keys(
        value,
        {
            "admitted_role_counts",
            "attempts_failed",
            "attempts_total",
            "collection_authorized",
            "model_fits",
            "model_predictions",
            "outcomes",
            "plan_sha256",
            "population_scale_authorized",
            "qualification_passed",
            "recensus_required",
            "roots_admitted",
            "runtime_identity_sha256",
            "schema",
            "status",
        },
    )
    raw_counts = _mapping(
        value["admitted_role_counts"],
        "powered supply admission role counts",
    )
    admission = RedLivingDexPoweredSupplyAdmission(
        plan_sha256=_text(value["plan_sha256"], "powered supply admission plan"),
        runtime_identity_sha256=_text(
            value["runtime_identity_sha256"],
            "powered supply admission runtime identity",
        ),
        roots_admitted=_integer(
            value["roots_admitted"], "powered supply admitted roots"
        ),
        attempts_failed=_integer(
            value["attempts_failed"], "powered supply failed attempts"
        ),
        admitted_role_counts=tuple(
            sorted(
                (
                    _text(role, "powered supply admitted role"),
                    _integer(count, "powered supply admitted role count"),
                )
                for role, count in raw_counts.items()
            )
        ),
        qualification_passed=_boolean(
            value["qualification_passed"],
            "powered supply qualification decision",
        ),
    )
    if value != admission.public_dict():
        raise RedLivingDexPoweredSupplyError(
            "powered supply admission authority boundary differs"
        )
    return admission


def powered_supply_receipt_from_mapping(
    value: Mapping[str, object],
) -> RedLivingDexPoweredSupplyReceipt:
    """Authenticate an already-decoded private receipt mapping."""

    receipt = _parse_receipt(value)
    if dict(value) != receipt.public_dict():
        raise RedLivingDexPoweredSupplyError(
            "powered supply receipt authority boundary differs"
        )
    return receipt


def _parse_receipt(value: Mapping[str, object]) -> RedLivingDexPoweredSupplyReceipt:
    row = _mapping(value, "powered supply receipt")
    _exact_keys(
        row,
        {
            "assignment_claim_sha256",
            "assignment_id",
            "compatible_template_ordinals",
            "conditioning_profile_id",
            "controller_actions",
            "distinct_process_episode",
            "emulator_frames",
            "episode_id",
            "first_controller_input_frame",
            "generator_execution_sha256",
            "initial_wait_frames",
            "learner_labels",
            "learner_outcomes",
            "learner_teacher_queries",
            "model_fits",
            "model_predictions",
            "observed_pressure_millionths",
            "partition",
            "physical_root_sha256",
            "plan_sha256",
            "role",
            "root_consumption_sha256",
            "root_lineage_id",
            "runtime_identity_sha256",
            "save_state_loads",
            "schema",
            "setup_teacher_executions",
            "source_bundle_sha256",
            "started_from_clean_power",
            "target_template_ordinal",
            "teacher_execution_sha256",
            "terminal_checkpoint_id",
            "terminal_envelope_sha256",
            "terminal_state_saves",
            "terminal_state_sha256",
            "trajectory_prefix_sha256",
        },
    )
    receipt = RedLivingDexPoweredSupplyReceipt(
        assignment_id=_text(row["assignment_id"], "powered supply receipt assignment"),
        plan_sha256=_text(row["plan_sha256"], "powered supply receipt plan"),
        assignment_claim_sha256=_text(
            row["assignment_claim_sha256"],
            "powered supply receipt assignment claim",
        ),
        role=cast(PoweredSupplyRole, _text(row["role"], "powered supply receipt role")),
        partition=cast(
            PoweredSupplyPartition,
            _text(row["partition"], "powered supply receipt partition"),
        ),
        root_lineage_id=_text(
            row["root_lineage_id"], "powered supply receipt lineage"
        ),
        episode_id=_text(row["episode_id"], "powered supply receipt episode"),
        source_bundle_sha256=_text(
            row["source_bundle_sha256"], "powered supply receipt source"
        ),
        teacher_execution_sha256=_text(
            row["teacher_execution_sha256"], "powered supply receipt teacher"
        ),
        generator_execution_sha256=_text(
            row["generator_execution_sha256"], "powered supply receipt generator"
        ),
        runtime_identity_sha256=_text(
            row["runtime_identity_sha256"], "powered supply receipt runtime identity"
        ),
        started_from_clean_power=_boolean(
            row["started_from_clean_power"], "powered supply clean power"
        ),
        distinct_process_episode=_boolean(
            row["distinct_process_episode"], "powered supply distinct episode"
        ),
        save_state_loads=_integer(
            row["save_state_loads"], "powered supply state loads"
        ),
        terminal_state_saves=_integer(
            row["terminal_state_saves"], "powered supply terminal saves"
        ),
        initial_wait_frames=_integer(
            row["initial_wait_frames"], "powered supply initial wait"
        ),
        first_controller_input_frame=_integer(
            row["first_controller_input_frame"], "powered supply first controller frame"
        ),
        trajectory_prefix_sha256=_text(
            row["trajectory_prefix_sha256"], "powered supply trajectory"
        ),
        conditioning_profile_id=_text(
            row["conditioning_profile_id"], "powered supply conditioning profile"
        ),
        target_template_ordinal=_integer(
            row["target_template_ordinal"], "powered supply target template"
        ),
        compatible_template_ordinals=_integer_tuple(
            row["compatible_template_ordinals"], "powered supply compatible templates"
        ),
        observed_pressure_millionths=_integer_tuple(
            row["observed_pressure_millionths"], "powered supply pressure vector"
        ),
        root_consumption_sha256=_text(
            row["root_consumption_sha256"], "powered supply consumption root"
        ),
        physical_root_sha256=_text(
            row["physical_root_sha256"], "powered supply physical root"
        ),
        terminal_state_sha256=_text(
            row["terminal_state_sha256"], "powered supply terminal state"
        ),
        terminal_envelope_sha256=_text(
            row["terminal_envelope_sha256"], "powered supply terminal envelope"
        ),
        terminal_checkpoint_id=_text(
            row["terminal_checkpoint_id"], "powered supply terminal checkpoint"
        ),
        controller_actions=_integer(
            row["controller_actions"], "powered supply controller actions"
        ),
        emulator_frames=_integer(
            row["emulator_frames"], "powered supply emulator frames"
        ),
        setup_teacher_executions=_integer(
            row["setup_teacher_executions"], "powered supply teacher executions"
        ),
        learner_teacher_queries=_integer(
            row["learner_teacher_queries"], "powered supply learner teacher queries"
        ),
        learner_labels=_integer(row["learner_labels"], "powered supply learner labels"),
        learner_outcomes=_integer(
            row["learner_outcomes"], "powered supply learner outcomes"
        ),
        model_predictions=_integer(
            row["model_predictions"], "powered supply model predictions"
        ),
        model_fits=_integer(row["model_fits"], "powered supply model fits"),
    )
    if row.get("schema") != RED_LIVING_DEX_POWERED_SUPPLY_RECEIPT_SCHEMA:
        raise RedLivingDexPoweredSupplyError("powered supply receipt schema differs")
    return receipt


def _parse_failure(value: Mapping[str, object]) -> RedLivingDexPoweredSupplyFailure:
    row = _mapping(value, "powered supply failure")
    _exact_keys(
        row,
        {
            "assignment_claim_sha256",
            "assignment_id",
            "attempt_consumed",
            "controller_actions",
            "effects_known",
            "emulator_frames",
            "failure_stage",
            "generator_execution_sha256",
            "learner_labels",
            "learner_outcomes",
            "model_fits",
            "model_predictions",
            "partition",
            "plan_sha256",
            "private_identity_fields",
            "private_path_fields",
            "retry_allowed",
            "role",
            "schema",
            "source_bundle_sha256",
            "teacher_execution_sha256",
            "terminal_root_generated",
        },
    )
    failure = RedLivingDexPoweredSupplyFailure(
        assignment_id=_text(row["assignment_id"], "powered supply failure assignment"),
        plan_sha256=_text(row["plan_sha256"], "powered supply failure plan"),
        role=cast(PoweredSupplyRole, _text(row["role"], "powered supply failure role")),
        partition=cast(
            PoweredSupplyPartition,
            _text(row["partition"], "powered supply failure partition"),
        ),
        source_bundle_sha256=_text(
            row["source_bundle_sha256"], "powered supply failure source"
        ),
        teacher_execution_sha256=_text(
            row["teacher_execution_sha256"], "powered supply failure teacher"
        ),
        generator_execution_sha256=_text(
            row["generator_execution_sha256"], "powered supply failure generator"
        ),
        assignment_claim_sha256=_optional_text(
            row["assignment_claim_sha256"], "powered supply failure claim"
        ),
        failure_stage=_text(row["failure_stage"], "powered supply failure stage"),
        effects_known=_boolean(
            row["effects_known"], "powered supply failure effects-known flag"
        ),
        controller_actions=_optional_integer(
            row["controller_actions"], "powered supply failure controller actions"
        ),
        emulator_frames=_optional_integer(
            row["emulator_frames"], "powered supply failure emulator frames"
        ),
        attempt_consumed=_boolean(
            row["attempt_consumed"], "powered supply consumed flag"
        ),
        retry_allowed=_boolean(row["retry_allowed"], "powered supply retry flag"),
        terminal_root_generated=_boolean(
            row["terminal_root_generated"], "powered supply terminal-root flag"
        ),
    )
    if row.get("schema") != RED_LIVING_DEX_POWERED_SUPPLY_FAILURE_SCHEMA:
        raise RedLivingDexPoweredSupplyError("powered supply failure schema differs")
    return failure


def _parse_assignment(value: object) -> RedLivingDexPoweredSupplyAssignment:
    row = _mapping(value, "powered supply assignment")
    _exact_keys(
        row,
        {
            "assignment_id",
            "campaign_id",
            "capacity_result_sha256",
            "conditioner_runner_sha256",
            "conditioning_profile_id",
            "declared_runs",
            "episode_id",
            "generator_execution_sha256",
            "generator_runner_sha256",
            "harness_seed",
            "initial_wait_frames",
            "ordinal",
            "partition",
            "powered_design_sha256",
            "profile",
            "role",
            "root_lineage_id",
            "run_id",
            "runtime_identity_sha256",
            "schema",
            "source_bundle_sha256",
            "target_checkpoint_id",
            "target_template_ordinal",
            "teacher_execution_sha256",
        },
    )
    assignment = RedLivingDexPoweredSupplyAssignment(
        campaign_id=_text(row["campaign_id"], "powered supply campaign"),
        run_id=_text(row["run_id"], "powered supply run"),
        ordinal=_integer(row["ordinal"], "powered supply ordinal"),
        declared_runs=_integer(row["declared_runs"], "powered supply declared runs"),
        role=cast(PoweredSupplyRole, _text(row["role"], "powered supply role")),
        partition=cast(
            PoweredSupplyPartition,
            _text(row["partition"], "powered supply partition"),
        ),
        harness_seed=_integer(row["harness_seed"], "powered supply harness seed"),
        initial_wait_frames=_integer(row["initial_wait_frames"], "powered supply initial wait"),
        target_template_ordinal=_integer(
            row["target_template_ordinal"], "powered supply target template"
        ),
        conditioning_profile_id=_text(
            row["conditioning_profile_id"],
            "powered supply conditioning profile",
        ),
        target_checkpoint_id=_text(row["target_checkpoint_id"], "powered supply checkpoint"),
        source_bundle_sha256=_text(row["source_bundle_sha256"], "powered supply source bundle"),
        teacher_execution_sha256=_text(
            row["teacher_execution_sha256"],
            "powered supply teacher execution",
        ),
        generator_execution_sha256=_text(
            row["generator_execution_sha256"],
            "powered supply generator execution",
        ),
        generator_runner_sha256=_text(
            row["generator_runner_sha256"],
            "powered supply generator runner",
        ),
        conditioner_runner_sha256=_text(
            row["conditioner_runner_sha256"],
            "powered supply conditioner runner",
        ),
        runtime_identity_sha256=_text(
            row["runtime_identity_sha256"],
            "powered supply runtime identity",
        ),
        capacity_result_sha256=_text(
            row["capacity_result_sha256"], "powered supply capacity result"
        ),
        powered_design_sha256=_text(row["powered_design_sha256"], "powered supply design"),
        assignment_id=_text(row["assignment_id"], "powered supply assignment"),
        root_lineage_id=_text(row["root_lineage_id"], "powered supply root lineage"),
        episode_id=_text(row["episode_id"], "powered supply episode"),
    )
    if (
        row.get("schema") != RED_LIVING_DEX_POWERED_SUPPLY_ASSIGNMENT_SCHEMA
        or dict(row) != assignment.public_dict()
    ):
        raise RedLivingDexPoweredSupplyError("powered supply assignment encoding differs")
    return assignment


def terminal_physical_root_sha256(*, state_sha256: str, envelope_sha256: str) -> str:
    """Expose the exact physical-root derivation for strict receipt readers."""

    _require_sha256(state_sha256, "powered supply terminal state")
    _require_sha256(envelope_sha256, "powered supply terminal envelope")
    return canonical_sha256(
        {
            "envelope_sha256": envelope_sha256,
            "schema": "pokemon.red.private-physical-setup-root.v1",
            "state_sha256": state_sha256,
        }
    )


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _decode_canonical(payload: bytes, subject: str) -> dict[str, object]:
    if not isinstance(payload, bytes):
        raise TypeError(f"{subject} payload must be bytes")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise RedLivingDexPoweredSupplyError(f"{subject} is not canonical ASCII JSON") from None
    if not isinstance(value, dict) or _canonical_line(value) != payload:
        raise RedLivingDexPoweredSupplyError(f"{subject} is not canonical ASCII JSON")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise RedLivingDexPoweredSupplyError(f"{subject} differs")
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str]) -> None:
    if set(value) != expected:
        raise RedLivingDexPoweredSupplyError("powered supply document fields differ")


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise RedLivingDexPoweredSupplyError(f"{subject} differs")
    return value


def _integer(value: object, subject: str) -> int:
    if type(value) is not int:  # noqa: E721
        raise RedLivingDexPoweredSupplyError(f"{subject} differs")
    return value


def _optional_integer(value: object, subject: str) -> int | None:
    if value is None:
        return None
    return _integer(value, subject)


def _integer_tuple(value: object, subject: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise RedLivingDexPoweredSupplyError(f"{subject} differs")
    return tuple(_integer(item, subject) for item in value)


def _boolean(value: object, subject: str) -> bool:
    if type(value) is not bool:  # noqa: E721
        raise RedLivingDexPoweredSupplyError(f"{subject} differs")
    return value


def _optional_text(value: object, subject: str) -> str | None:
    if value is None:
        return None
    return _text(value, subject)


__all__ = [
    "RED_LIVING_DEX_POWERED_CONDITIONING_PROFILES",
    "RED_LIVING_DEX_POWERED_SUPPLY_ASSIGNMENTS",
    "RED_LIVING_DEX_POWERED_SUPPLY_CAPACITY_RESULT_SHA256",
    "RED_LIVING_DEX_POWERED_SUPPLY_DEFICITS",
    "RED_LIVING_DEX_POWERED_SUPPLY_DESIGN_SHA256",
    "RED_LIVING_DEX_POWERED_SUPPLY_MINIMUM_ROLE_ROOTS",
    "RED_LIVING_DEX_POWERED_SUPPLY_MINIMUM_ROOTS",
    "RedLivingDexPoweredConditioningProfile",
    "RedLivingDexPoweredSupplyAdmission",
    "RedLivingDexPoweredSupplyAssignment",
    "RedLivingDexPoweredSupplyError",
    "RedLivingDexPoweredSupplyFailure",
    "RedLivingDexPoweredSupplyPlan",
    "RedLivingDexPoweredSupplyPreflight",
    "RedLivingDexPoweredSupplyReceipt",
    "admit_red_living_dex_powered_supply_tranche",
    "build_red_living_dex_powered_supply_plan",
    "compose_red_living_dex_powered_supply_generator_sha256",
    "compose_red_living_dex_powered_supply_runtime_execution_sha256",
    "compose_red_living_dex_powered_supply_teacher_sha256",
    "encode_red_living_dex_powered_supply_plan",
    "encode_red_living_dex_powered_supply_admission",
    "encode_red_living_dex_powered_supply_failure",
    "encode_red_living_dex_powered_supply_receipt",
    "parse_red_living_dex_powered_supply_admission",
    "parse_red_living_dex_powered_supply_failure",
    "parse_red_living_dex_powered_supply_plan",
    "parse_red_living_dex_powered_supply_receipt",
    "powered_supply_partition",
    "powered_supply_collection_id",
    "powered_supply_profile",
    "powered_supply_receipt_from_mapping",
    "preflight_red_living_dex_powered_supply_plan",
    "terminal_physical_root_sha256",
]
