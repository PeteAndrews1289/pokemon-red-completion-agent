"""Prospective clean-power lineages for fresh Red living-Dex roots.

The powered causal curriculum needs more independent roots than the historic
inventory can supply.  A new digest or a different RNG byte does not create an
independent experimental unit.  This module therefore commits each episode
before controller input and admits its terminal root only when the execution
proves clean power, no state restore, a distinct upstream trajectory, and the
declared authentic-menu target.

This is a planning and admission boundary.  It does not construct an emulator,
run the teacher, save a state, collect an outcome, score a model, or fit one.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupProtectedEffectCheckpoint,
)

RED_LIVING_DEX_FRESH_EPISODE_PLAN_SCHEMA = (
    "pokemon.red.living-dex-fresh-episode-plan.v1"
)
RED_LIVING_DEX_FRESH_EPISODE_ASSIGNMENT_SCHEMA = (
    "pokemon.red.living-dex-fresh-episode-assignment.v1"
)
RED_LIVING_DEX_FRESH_EPISODE_RECEIPT_SCHEMA = (
    "pokemon.red.living-dex-fresh-episode-receipt.v1"
)
RED_LIVING_DEX_FRESH_EPISODE_FAILURE_RECEIPT_SCHEMA = (
    "pokemon.red.living-dex-fresh-episode-failure-receipt.v1"
)
RED_LIVING_DEX_FRESH_EPISODE_ADMISSION_SCHEMA = (
    "pokemon.red.living-dex-fresh-episode-tranche-admission.v1"
)
RED_LIVING_DEX_FRESH_EPISODE_PREFLIGHT_SCHEMA = (
    "pokemon.red.living-dex-fresh-episode-generator-preflight.v1"
)
RED_LIVING_DEX_FRESH_EPISODE_CAMPAIGN_ID = (
    "red-living-dex-fresh-train-roots-v1"
)
RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID = "mansion_returned"
RED_LIVING_DEX_FRESH_EPISODE_PARTITION = "train"
RED_LIVING_DEX_FRESH_EPISODE_BASELINE_TRAIN_MATCHING = 54
RED_LIVING_DEX_FRESH_EPISODE_FIRST_HARNESS_SEED = 4_500_001

# The observed inventory has only 3, 3, and 8 compatible roots for these
# templates.  Six, six, and one new targeted episodes are the smallest first
# tranche that can remove those direct per-template shortages.  A recensus,
# not this arithmetic, decides whether the global matching actually rose.
RED_LIVING_DEX_FRESH_EPISODE_FIRST_TRANCHE_TARGETS: Mapping[int, int] = {
    2: 6,
    3: 6,
    5: 1,
}
RED_LIVING_DEX_FRESH_EPISODE_STORAGE_BOX_COUNTS = (17, 18, 19)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_WAIT_DOMAIN = b"pokemon-red-living-dex-fresh-episode-wait-v1\0"


class RedLivingDexEpisodeLineageError(ValueError):
    """One fresh episode was post-hoc, cloned, effectful, or off target."""


def derive_red_living_dex_initial_wait_frames(harness_seed: int) -> int:
    """Derive a nonzero pre-controller RNG divergence from one frozen seed."""

    _require_uint64(harness_seed, "fresh-episode harness seed")
    digest = hashlib.sha256(
        _WAIT_DOMAIN + harness_seed.to_bytes(8, byteorder="big")
    ).digest()
    return 1 + int.from_bytes(digest[:2], byteorder="big") % 255


def expected_red_living_dex_first_controller_input_frame(
    initial_wait_frames: int,
) -> int:
    """Bind the timing jitter plus the teacher's fixed clean-boot delay.

    ``initial_wait_frames`` is an additional clean-power timing perturbation,
    matching the established portable-run contract.  The teacher then performs
    its normal button-free boot wait before its first controller pulse.  Keeping
    both pieces explicit prevents a receipt from pretending the controller was
    used earlier than it actually was.
    """

    if type(initial_wait_frames) is not int or initial_wait_frames <= 0:  # noqa: E721
        raise RedLivingDexEpisodeLineageError(
            "fresh-episode initial wait is invalid"
        )
    return initial_wait_frames + DEFAULT_NEW_GAME_TIMING.boot_frames


def compose_red_living_dex_fresh_episode_generator_execution_sha256(
    *,
    source_bundle_sha256: str,
    generator_runner_sha256: str,
    conditioner_runner_sha256: str,
) -> str:
    """Bind the source package plus both executable script surfaces."""

    for value, subject in (
        (source_bundle_sha256, "fresh-episode source bundle"),
        (generator_runner_sha256, "fresh-episode generator runner"),
        (conditioner_runner_sha256, "fresh-episode conditioner runner"),
    ):
        _require_sha256(value, subject)
    return canonical_sha256(
        {
            "conditioner_runner_sha256": conditioner_runner_sha256,
            "generator_runner_sha256": generator_runner_sha256,
            "schema": "pokemon.red.living-dex-fresh-generator-execution.v1",
            "source_bundle_sha256": source_bundle_sha256,
        }
    )


def compose_red_living_dex_fresh_episode_teacher_execution_sha256(
    *,
    source_bundle_sha256: str,
    generator_execution_sha256: str,
) -> str:
    """Bind the deterministic setup teacher and its deliberately absent learners."""

    for value, subject in (
        (source_bundle_sha256, "fresh-episode source bundle"),
        (generator_execution_sha256, "fresh-episode generator execution"),
    ):
        _require_sha256(value, subject)
    return canonical_sha256(
        {
            "battle_model": None,
            "checkpoint_id": RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID,
            "generator_execution_sha256": generator_execution_sha256,
            "objective_model": None,
            "schema": "pokemon.red.living-dex-fresh-setup-teacher.v1",
            "source_bundle_sha256": source_bundle_sha256,
            "teacher_entrypoint": (
                "pokemon_red_completion.play.run_qualified_play"
            ),
            "training_candidate_model": None,
        }
    )


def red_living_dex_storage_pressure_millionths(active_box_count: int) -> int:
    """Return the exact configured storage pressure without float ambiguity."""

    if active_box_count not in RED_LIVING_DEX_FRESH_EPISODE_STORAGE_BOX_COUNTS:
        raise RedLivingDexEpisodeLineageError(
            "fresh-episode active-box target is outside the qualified pressure set"
        )
    # Gen-I boxes hold 20 and the goal manager wants eight free slots.
    free_slots = 20 - active_box_count
    return 1_000_000 - min(free_slots, 8) * 1_000_000 // 8


def _canonical_red_living_dex_fresh_episode_schedule(
) -> tuple[tuple[int, int, int, int | None], ...]:
    """Return frozen seed, wait, template, and box targets without a choice knob."""

    targets = (
        *((2, count) for count in (17, 18, 19, 17, 18, 19)),
        *((3, count) for count in (17, 18, 19, 17, 18, 19)),
        (5, None),
    )
    rows: list[tuple[int, int, int, int | None]] = []
    used_waits: set[int] = set()
    candidate_seed = RED_LIVING_DEX_FRESH_EPISODE_FIRST_HARNESS_SEED
    for template_ordinal, active_box_count in targets:
        while derive_red_living_dex_initial_wait_frames(candidate_seed) in used_waits:
            candidate_seed += 1
            _require_uint64(candidate_seed, "fresh-episode harness seed")
        wait_frames = derive_red_living_dex_initial_wait_frames(candidate_seed)
        used_waits.add(wait_frames)
        rows.append(
            (
                candidate_seed,
                wait_frames,
                template_ordinal,
                active_box_count,
            )
        )
        candidate_seed += 1
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class RedLivingDexFreshEpisodeAssignment:
    """One pre-controller train episode and its declared terminal objective."""

    campaign_id: str
    run_id: str
    ordinal: int
    declared_runs: int
    partition: str
    harness_seed: int
    initial_wait_frames: int
    target_template_ordinal: int
    target_active_box_count: int | None
    target_checkpoint_id: str
    source_bundle_sha256: str
    teacher_execution_sha256: str
    generator_execution_sha256: str
    capacity_evidence_sha256: str
    assignment_id: str
    root_lineage_id: str
    episode_id: str

    def __post_init__(self) -> None:
        if self.campaign_id != RED_LIVING_DEX_FRESH_EPISODE_CAMPAIGN_ID:
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode campaign identity differs"
            )
        _require_safe_id(self.run_id, "fresh-episode run identity")
        if (
            type(self.ordinal) is not int  # noqa: E721
            or type(self.declared_runs) is not int  # noqa: E721
            or not 1 <= self.ordinal <= self.declared_runs
        ):
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode ordinal differs"
            )
        if self.partition != RED_LIVING_DEX_FRESH_EPISODE_PARTITION:
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode partition must remain train"
            )
        _require_uint64(self.harness_seed, "fresh-episode harness seed")
        if self.initial_wait_frames != derive_red_living_dex_initial_wait_frames(
            self.harness_seed
        ):
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode pre-controller wait differs"
            )
        if self.target_template_ordinal not in (
            RED_LIVING_DEX_FRESH_EPISODE_FIRST_TRANCHE_TARGETS
        ):
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode target is not a measured scarce train template"
            )
        if self.target_template_ordinal in {2, 3}:
            red_living_dex_storage_pressure_millionths(
                _require_integer(
                    self.target_active_box_count,
                    "fresh-episode active-box target",
                )
            )
        elif self.target_active_box_count is not None:
            raise RedLivingDexEpisodeLineageError(
                "non-storage fresh episode declares an active-box target"
            )
        if self.target_checkpoint_id != (
            RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID
        ):
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode capture checkpoint differs"
            )
        for value, subject in (
            (self.source_bundle_sha256, "fresh-episode source bundle"),
            (self.teacher_execution_sha256, "fresh-episode teacher execution"),
            (self.generator_execution_sha256, "fresh-episode generator execution"),
            (self.capacity_evidence_sha256, "fresh-episode capacity evidence"),
            (self.assignment_id, "fresh-episode assignment"),
        ):
            _require_sha256(value, subject)
        if self.teacher_execution_sha256 != (
            compose_red_living_dex_fresh_episode_teacher_execution_sha256(
                source_bundle_sha256=self.source_bundle_sha256,
                generator_execution_sha256=self.generator_execution_sha256,
            )
        ):
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode teacher execution is not derived from its generator"
            )
        expected = canonical_sha256(self._commitment_dict())
        if self.assignment_id != expected:
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode assignment was not committed prospectively"
            )
        if self.root_lineage_id != f"red-living-dex-fresh-root-{expected}":
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode root lineage differs from its pre-state assignment"
            )
        if self.episode_id != f"red-ldx-fresh-{expected}":
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode private episode identity differs"
            )

    @property
    def target_storage_pressure_millionths(self) -> int | None:
        if self.target_active_box_count is None:
            return None
        return red_living_dex_storage_pressure_millionths(
            self.target_active_box_count
        )

    def _commitment_dict(self) -> dict[str, object]:
        return {
            "campaign_id": self.campaign_id,
            "capacity_evidence_sha256": self.capacity_evidence_sha256,
            "declared_runs": self.declared_runs,
            "harness_seed": self.harness_seed,
            "initial_wait_frames": self.initial_wait_frames,
            "generator_execution_sha256": self.generator_execution_sha256,
            "ordinal": self.ordinal,
            "partition": self.partition,
            "run_id": self.run_id,
            "schema": RED_LIVING_DEX_FRESH_EPISODE_ASSIGNMENT_SCHEMA,
            "source_bundle_sha256": self.source_bundle_sha256,
            "target_active_box_count": self.target_active_box_count,
            "target_checkpoint_id": self.target_checkpoint_id,
            "target_template_ordinal": self.target_template_ordinal,
            "teacher_execution_sha256": self.teacher_execution_sha256,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            **self._commitment_dict(),
            "assignment_id": self.assignment_id,
            "episode_id": self.episode_id,
            "root_lineage_id": self.root_lineage_id,
            "target_storage_pressure_millionths": (
                self.target_storage_pressure_millionths
            ),
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexFreshEpisodePlan:
    """One path-free, train-only first tranche frozen before gameplay."""

    source_commit: str
    source_bundle_sha256: str
    teacher_execution_sha256: str
    generator_execution_sha256: str
    capacity_evidence_sha256: str
    baseline_train_maximum_matching: int
    assignments: tuple[RedLivingDexFreshEpisodeAssignment, ...]

    def __post_init__(self) -> None:
        if _GIT_OID.fullmatch(self.source_commit) is None:
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode source commit is invalid"
            )
        for value, subject in (
            (self.source_bundle_sha256, "fresh-episode source bundle"),
            (self.teacher_execution_sha256, "fresh-episode teacher execution"),
            (self.generator_execution_sha256, "fresh-episode generator execution"),
            (self.capacity_evidence_sha256, "fresh-episode capacity evidence"),
        ):
            _require_sha256(value, subject)
        if self.teacher_execution_sha256 != (
            compose_red_living_dex_fresh_episode_teacher_execution_sha256(
                source_bundle_sha256=self.source_bundle_sha256,
                generator_execution_sha256=self.generator_execution_sha256,
            )
        ):
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode teacher execution is not derived from its generator"
            )
        if self.baseline_train_maximum_matching != (
            RED_LIVING_DEX_FRESH_EPISODE_BASELINE_TRAIN_MATCHING
        ):
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode plan uses another capacity baseline"
            )
        if not isinstance(self.assignments, tuple) or not self.assignments:
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode plan has no assignments"
            )
        for assignment in self.assignments:
            if not isinstance(assignment, RedLivingDexFreshEpisodeAssignment):
                raise TypeError("fresh-episode plan assignments differ")
            assignment.__post_init__()
        expected_ordinals = tuple(range(1, len(self.assignments) + 1))
        if tuple(item.ordinal for item in self.assignments) != expected_ordinals:
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode assignments are not canonically ordered"
            )
        if any(item.declared_runs != len(self.assignments) for item in self.assignments):
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode assignment total differs"
            )
        expected_schedule = _canonical_red_living_dex_fresh_episode_schedule()
        observed_schedule = tuple(
            (
                item.harness_seed,
                item.initial_wait_frames,
                item.target_template_ordinal,
                item.target_active_box_count,
            )
            for item in self.assignments
        )
        if observed_schedule != expected_schedule:
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode seed and target schedule differs"
            )
        for assignment in self.assignments:
            if (
                assignment.source_bundle_sha256 != self.source_bundle_sha256
                or assignment.teacher_execution_sha256
                != self.teacher_execution_sha256
                or assignment.generator_execution_sha256
                != self.generator_execution_sha256
                or assignment.capacity_evidence_sha256
                != self.capacity_evidence_sha256
            ):
                raise RedLivingDexEpisodeLineageError(
                    "fresh-episode assignment execution binding differs"
                )
        for values, subject in (
            ((item.run_id for item in self.assignments), "run identity"),
            ((item.harness_seed for item in self.assignments), "harness seed"),
            (
                (item.initial_wait_frames for item in self.assignments),
                "pre-controller wait",
            ),
            ((item.assignment_id for item in self.assignments), "assignment"),
            ((item.root_lineage_id for item in self.assignments), "root lineage"),
            ((item.episode_id for item in self.assignments), "episode"),
        ):
            materialized = tuple(values)
            if len(set(materialized)) != len(materialized):
                raise RedLivingDexEpisodeLineageError(
                    f"fresh-episode {subject} is duplicated"
                )
        targets = Counter(
            item.target_template_ordinal for item in self.assignments
        )
        if dict(sorted(targets.items())) != dict(
            RED_LIVING_DEX_FRESH_EPISODE_FIRST_TRANCHE_TARGETS
        ):
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode first tranche does not target every measured shortage"
            )
        storage_values = {
            item.target_storage_pressure_millionths
            for item in self.assignments
            if item.target_storage_pressure_millionths is not None
        }
        if len(storage_values) < 3:
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode tranche lacks three storage-pressure targets"
            )

    @property
    def plan_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def assignment(self, assignment_id: str) -> RedLivingDexFreshEpisodeAssignment:
        matches = tuple(
            item for item in self.assignments if item.assignment_id == assignment_id
        )
        if len(matches) != 1:
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode assignment is unavailable"
            )
        return matches[0]

    def public_dict(self) -> dict[str, object]:
        return {
            "assignments": [item.public_dict() for item in self.assignments],
            "baseline_train_maximum_matching": (
                self.baseline_train_maximum_matching
            ),
            "capacity_evidence_sha256": self.capacity_evidence_sha256,
            "causal_independence": {
                "assignment_precedes_terminal_state": True,
                "clean_power_required": True,
                "distinct_process_episode_required": True,
                "parent_checkpoint_allowed": False,
                "save_state_loads_allowed": 0,
                "state_or_rng_rehash_creates_lineage": False,
            },
            "development_materialized": False,
            "failure_disposition": {
                "all_frozen_assignments_required": True,
                "failed_attempts_retained": True,
                "failure_does_not_discard_other_valid_roots": True,
                "retry_after_consumption": False,
                "successor_targets_require_action_free_recensus": True,
            },
            "first_tranche": True,
            "generator_execution_sha256": self.generator_execution_sha256,
            "partition": RED_LIVING_DEX_FRESH_EPISODE_PARTITION,
            "recensus_required_before_outcome_collection": True,
            "schema": RED_LIVING_DEX_FRESH_EPISODE_PLAN_SCHEMA,
            "source": {
                "commit": self.source_commit,
                "source_bundle_sha256": self.source_bundle_sha256,
            },
            "teacher_execution_sha256": self.teacher_execution_sha256,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexFreshEpisodeReceipt:
    """Path-free terminal proof for one already committed fresh episode."""

    assignment_id: str
    plan_sha256: str
    assignment_claim_sha256: str
    root_lineage_id: str
    episode_id: str
    source_bundle_sha256: str
    teacher_execution_sha256: str
    generator_execution_sha256: str
    started_from_clean_power: bool
    distinct_process_episode: bool
    parent_state_sha256: str | None
    parent_root_lineage_id: str | None
    save_state_loads: int
    terminal_state_saves: int
    initial_wait_frames: int
    first_controller_input_frame: int
    trajectory_prefix_sha256: str
    target_template_ordinal: int
    compatible_template_ordinals: tuple[int, ...]
    observed_storage_pressure_millionths: int | None
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
            (self.assignment_id, "fresh receipt assignment"),
            (self.plan_sha256, "fresh receipt plan"),
            (self.assignment_claim_sha256, "fresh receipt assignment claim"),
            (self.source_bundle_sha256, "fresh receipt source"),
            (self.teacher_execution_sha256, "fresh receipt teacher"),
            (self.generator_execution_sha256, "fresh receipt generator"),
            (self.trajectory_prefix_sha256, "fresh receipt trajectory prefix"),
            (self.terminal_state_sha256, "fresh receipt terminal state"),
            (self.terminal_envelope_sha256, "fresh receipt terminal envelope"),
        ):
            _require_sha256(value, subject)
        _require_safe_id(self.root_lineage_id, "fresh receipt root lineage")
        _require_safe_id(self.episode_id, "fresh receipt episode")
        if self.started_from_clean_power is not True:
            raise RedLivingDexEpisodeLineageError(
                "fresh receipt did not start at clean power"
            )
        if self.distinct_process_episode is not True:
            raise RedLivingDexEpisodeLineageError(
                "fresh receipt reused an emulator process episode"
            )
        if self.parent_state_sha256 is not None or self.parent_root_lineage_id is not None:
            raise RedLivingDexEpisodeLineageError(
                "fresh receipt descends from a checkpoint or parent root"
            )
        for counter_value, expected, subject in (
            (self.save_state_loads, 0, "state loads"),
            (self.terminal_state_saves, 1, "terminal state saves"),
            (self.setup_teacher_executions, 1, "setup teacher executions"),
            (self.learner_teacher_queries, 0, "learner teacher queries"),
            (self.learner_labels, 0, "learner labels"),
            (self.learner_outcomes, 0, "learner outcomes"),
            (self.model_predictions, 0, "model predictions"),
            (self.model_fits, 0, "model fits"),
        ):
            if counter_value != expected:
                raise RedLivingDexEpisodeLineageError(
                    f"fresh receipt {subject} differ"
                )
        if (
            type(self.initial_wait_frames) is not int  # noqa: E721
            or self.initial_wait_frames <= 0
            or self.first_controller_input_frame
            != expected_red_living_dex_first_controller_input_frame(
                self.initial_wait_frames
            )
        ):
            raise RedLivingDexEpisodeLineageError(
                "fresh receipt did not diverge before first controller input"
            )
        if (
            type(self.target_template_ordinal) is not int  # noqa: E721
            or self.target_template_ordinal not in self.compatible_template_ordinals
            or tuple(sorted(set(self.compatible_template_ordinals)))
            != self.compatible_template_ordinals
            or any(
                type(item) is not int or not 0 <= item < 10  # noqa: E721
                for item in self.compatible_template_ordinals
            )
        ):
            raise RedLivingDexEpisodeLineageError(
                "fresh receipt missed its authentic train template"
            )
        if self.observed_storage_pressure_millionths is not None and (
            type(self.observed_storage_pressure_millionths) is not int  # noqa: E721
            or not 0 <= self.observed_storage_pressure_millionths <= 1_000_000
        ):
            raise RedLivingDexEpisodeLineageError(
                "fresh receipt storage pressure is invalid"
            )
        if self.terminal_checkpoint_id != RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID:
            raise RedLivingDexEpisodeLineageError(
                "fresh receipt terminal checkpoint differs"
            )
        if (
            type(self.controller_actions) is not int  # noqa: E721
            or self.controller_actions <= 0
            or type(self.emulator_frames) is not int  # noqa: E721
            or self.emulator_frames <= self.first_controller_input_frame
        ):
            raise RedLivingDexEpisodeLineageError(
                "fresh receipt has no executed clean-power trajectory"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "assignment_id": self.assignment_id,
            "assignment_claim_sha256": self.assignment_claim_sha256,
            "assignment_claims": 1,
            "causal_independence": {
                "distinct_process_episode": self.distinct_process_episode,
                "parent_root_lineage_id": self.parent_root_lineage_id,
                "parent_state_sha256": self.parent_state_sha256,
                "started_from_clean_power": self.started_from_clean_power,
            },
            "compatible_template_ordinals": list(
                self.compatible_template_ordinals
            ),
            "controller_actions": self.controller_actions,
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
            "observed_storage_pressure_millionths": (
                self.observed_storage_pressure_millionths
            ),
            "plan_sha256": self.plan_sha256,
            "root_lineage_id": self.root_lineage_id,
            "root_consumption_claims": 0,
            "save_state_loads": self.save_state_loads,
            "schema": RED_LIVING_DEX_FRESH_EPISODE_RECEIPT_SCHEMA,
            "setup_teacher_executions": self.setup_teacher_executions,
            "source_bundle_sha256": self.source_bundle_sha256,
            "target_template_ordinal": self.target_template_ordinal,
            "teacher_execution_sha256": self.teacher_execution_sha256,
            "terminal_checkpoint_id": self.terminal_checkpoint_id,
            "terminal_envelope_sha256": self.terminal_envelope_sha256,
            "terminal_state_saves": self.terminal_state_saves,
            "terminal_state_sha256": self.terminal_state_sha256,
            "trajectory_prefix_sha256": self.trajectory_prefix_sha256,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexFreshEpisodeFailureReceipt:
    """Path-free terminal disposition for one consumed assignment without a root."""

    assignment_id: str
    plan_sha256: str
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
            (self.assignment_id, "fresh failure assignment"),
            (self.plan_sha256, "fresh failure plan"),
            (self.source_bundle_sha256, "fresh failure source"),
            (self.teacher_execution_sha256, "fresh failure teacher"),
            (self.generator_execution_sha256, "fresh failure generator"),
        ):
            _require_sha256(value, subject)
        if self.assignment_claim_sha256 is not None:
            _require_sha256(
                self.assignment_claim_sha256,
                "fresh failure assignment claim",
            )
        if _SAFE_ID.fullmatch(self.failure_stage) is None:
            raise RedLivingDexEpisodeLineageError(
                "fresh failure stage is invalid"
            )
        if (
            self.attempt_consumed is not True
            or self.retry_allowed is not False
            or self.terminal_root_generated is not False
        ):
            raise RedLivingDexEpisodeLineageError(
                "fresh failure disposition is not terminal"
            )
        if self.effects_known:
            if any(
                type(value) is not int or value < 0  # noqa: E721
                for value in (self.controller_actions, self.emulator_frames)
            ):
                raise RedLivingDexEpisodeLineageError(
                    "fresh failure known effects differ"
                )
        elif self.controller_actions is not None or self.emulator_frames is not None:
            raise RedLivingDexEpisodeLineageError(
                "fresh failure unknown effects were overstated"
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
            "plan_sha256": self.plan_sha256,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "retry_allowed": self.retry_allowed,
            "schema": RED_LIVING_DEX_FRESH_EPISODE_FAILURE_RECEIPT_SCHEMA,
            "source_bundle_sha256": self.source_bundle_sha256,
            "teacher_execution_sha256": self.teacher_execution_sha256,
            "terminal_root_generated": self.terminal_root_generated,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexFreshEpisodePreflight:
    """Action-free proof that one prospective tranche is safe to execute later."""

    plan_sha256: str
    assignments: int
    target_template_counts: tuple[tuple[int, int], ...]
    storage_pressure_values_millionths: tuple[int, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "assignments": self.assignments,
            "behavior_draws": 0,
            "collection_authorized": False,
            "controller_actions": 0,
            "development_materialized": False,
            "emulator_frames": 0,
            "learner_labels": 0,
            "learner_outcomes": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "plan_sha256": self.plan_sha256,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "provider_executions": 0,
            "recensus_required_after_generation": True,
            "success_or_failure_disposition_required_per_assignment": True,
            "root_claims": 0,
            "root_generation_executions": 0,
            "schema": RED_LIVING_DEX_FRESH_EPISODE_PREFLIGHT_SCHEMA,
            "status": "fresh_train_episode_generator_plan_preflight_passed",
            "storage_pressure_values_millionths": list(
                self.storage_pressure_values_millionths
            ),
            "target_template_counts": {
                str(key): value for key, value in self.target_template_counts
            },
            "teacher_queries": 0,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexFreshEpisodeAdmission:
    """All frozen success/failure dispositions; still no outcome authority."""

    plan_sha256: str
    roots_admitted: int
    attempts_failed: int
    target_template_counts: tuple[tuple[int, int], ...]
    storage_pressure_values_millionths: tuple[int, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "collection_authorized": False,
            "attempts_failed": self.attempts_failed,
            "attempts_total": self.roots_admitted + self.attempts_failed,
            "development_materialized": False,
            "model_fits": 0,
            "model_predictions": 0,
            "outcomes": 0,
            "plan_sha256": self.plan_sha256,
            "recensus_required": True,
            "roots_admitted": self.roots_admitted,
            "schema": RED_LIVING_DEX_FRESH_EPISODE_ADMISSION_SCHEMA,
            "status": "fresh_train_dispositions_admitted_pending_action_free_recensus",
            "storage_pressure_values_millionths": list(
                self.storage_pressure_values_millionths
            ),
            "target_template_counts": {
                str(key): value for key, value in self.target_template_counts
            },
        }


def build_red_living_dex_fresh_episode_plan(
    *,
    source_commit: str,
    source_bundle_sha256: str,
    teacher_execution_sha256: str,
    generator_execution_sha256: str,
    capacity_evidence_sha256: str,
) -> RedLivingDexFreshEpisodePlan:
    """Build the canonical 6/6/1 train-first generator qualification tranche."""

    schedule = _canonical_red_living_dex_fresh_episode_schedule()
    declared_runs = len(schedule)
    assignments: list[RedLivingDexFreshEpisodeAssignment] = []
    for ordinal, (
        candidate_seed,
        wait_frames,
        template_ordinal,
        active_box_count,
    ) in enumerate(schedule, start=1):
        run_id = f"red-living-dex-fresh-train-{ordinal:02d}"
        commitment = {
            "campaign_id": RED_LIVING_DEX_FRESH_EPISODE_CAMPAIGN_ID,
            "capacity_evidence_sha256": capacity_evidence_sha256,
            "declared_runs": declared_runs,
            "harness_seed": candidate_seed,
            "initial_wait_frames": wait_frames,
            "generator_execution_sha256": generator_execution_sha256,
            "ordinal": ordinal,
            "partition": RED_LIVING_DEX_FRESH_EPISODE_PARTITION,
            "run_id": run_id,
            "schema": RED_LIVING_DEX_FRESH_EPISODE_ASSIGNMENT_SCHEMA,
            "source_bundle_sha256": source_bundle_sha256,
            "target_active_box_count": active_box_count,
            "target_checkpoint_id": RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID,
            "target_template_ordinal": template_ordinal,
            "teacher_execution_sha256": teacher_execution_sha256,
        }
        assignment_id = canonical_sha256(commitment)
        assignments.append(
            RedLivingDexFreshEpisodeAssignment(
                campaign_id=RED_LIVING_DEX_FRESH_EPISODE_CAMPAIGN_ID,
                run_id=run_id,
                ordinal=ordinal,
                declared_runs=declared_runs,
                partition=RED_LIVING_DEX_FRESH_EPISODE_PARTITION,
                harness_seed=candidate_seed,
                initial_wait_frames=wait_frames,
                target_template_ordinal=template_ordinal,
                target_active_box_count=active_box_count,
                target_checkpoint_id=(
                    RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID
                ),
                source_bundle_sha256=source_bundle_sha256,
                teacher_execution_sha256=teacher_execution_sha256,
                generator_execution_sha256=generator_execution_sha256,
                capacity_evidence_sha256=capacity_evidence_sha256,
                assignment_id=assignment_id,
                root_lineage_id=f"red-living-dex-fresh-root-{assignment_id}",
                # PrivateArtifactRoot permits at most eighty characters.  The
                # digest keeps the identity collision-resistant while this
                # fourteen-character prefix stays inside that durable store.
                episode_id=f"red-ldx-fresh-{assignment_id}",
            )
        )
    return RedLivingDexFreshEpisodePlan(
        source_commit=source_commit,
        source_bundle_sha256=source_bundle_sha256,
        teacher_execution_sha256=teacher_execution_sha256,
        generator_execution_sha256=generator_execution_sha256,
        capacity_evidence_sha256=capacity_evidence_sha256,
        baseline_train_maximum_matching=(
            RED_LIVING_DEX_FRESH_EPISODE_BASELINE_TRAIN_MATCHING
        ),
        assignments=tuple(assignments),
    )


def admit_red_living_dex_fresh_episode_tranche(
    plan: RedLivingDexFreshEpisodePlan,
    receipts: tuple[RedLivingDexFreshEpisodeReceipt, ...],
    failures: tuple[RedLivingDexFreshEpisodeFailureReceipt, ...] = (),
) -> RedLivingDexFreshEpisodeAdmission:
    """Admit every frozen disposition without discarding valid roots after a failure."""

    if not isinstance(plan, RedLivingDexFreshEpisodePlan):
        raise TypeError("fresh-episode admission needs its plan")
    plan.__post_init__()
    if not isinstance(receipts, tuple) or any(
        not isinstance(item, RedLivingDexFreshEpisodeReceipt) for item in receipts
    ):
        raise TypeError("fresh-episode admission needs receipt tuples")
    if not isinstance(failures, tuple) or any(
        not isinstance(item, RedLivingDexFreshEpisodeFailureReceipt)
        for item in failures
    ):
        raise TypeError("fresh-episode admission needs failure receipt tuples")
    if len(receipts) + len(failures) != len(plan.assignments):
        raise RedLivingDexEpisodeLineageError(
            "fresh-episode disposition tranche is incomplete"
        )
    by_assignment = {item.assignment_id: item for item in receipts}
    if len(by_assignment) != len(receipts):
        raise RedLivingDexEpisodeLineageError(
            "fresh-episode receipt assignment is duplicated"
        )
    failed_by_assignment = {item.assignment_id: item for item in failures}
    if len(failed_by_assignment) != len(failures) or set(by_assignment) & set(
        failed_by_assignment
    ):
        raise RedLivingDexEpisodeLineageError(
            "fresh-episode disposition assignment is duplicated"
        )
    expected_assignments = {item.assignment_id for item in plan.assignments}
    if set(by_assignment) | set(failed_by_assignment) != expected_assignments:
        raise RedLivingDexEpisodeLineageError(
            "fresh-episode disposition is outside its prospective plan"
        )
    for assignment in plan.assignments:
        receipt = by_assignment.get(assignment.assignment_id)
        if receipt is None:
            failure = failed_by_assignment[assignment.assignment_id]
            failure.__post_init__()
            if (
                failure.plan_sha256 != plan.plan_sha256
                or failure.source_bundle_sha256
                != assignment.source_bundle_sha256
                or failure.teacher_execution_sha256
                != assignment.teacher_execution_sha256
                or failure.generator_execution_sha256
                != assignment.generator_execution_sha256
            ):
                raise RedLivingDexEpisodeLineageError(
                    "fresh-episode failure differs from its prospective plan"
                )
            continue
        receipt.__post_init__()
        if (
            receipt.plan_sha256 != plan.plan_sha256
            or receipt.root_lineage_id != assignment.root_lineage_id
            or receipt.episode_id != assignment.episode_id
            or receipt.source_bundle_sha256 != assignment.source_bundle_sha256
            or receipt.teacher_execution_sha256
            != assignment.teacher_execution_sha256
            or receipt.generator_execution_sha256
            != assignment.generator_execution_sha256
            or receipt.initial_wait_frames != assignment.initial_wait_frames
            or receipt.target_template_ordinal
            != assignment.target_template_ordinal
            or receipt.terminal_checkpoint_id
            != assignment.target_checkpoint_id
            or receipt.observed_storage_pressure_millionths
            != assignment.target_storage_pressure_millionths
        ):
            raise RedLivingDexEpisodeLineageError(
                "fresh-episode receipt differs from its pre-controller assignment"
            )
    for values, subject in (
        ((item.root_lineage_id for item in receipts), "root lineage"),
        ((item.trajectory_prefix_sha256 for item in receipts), "trajectory prefix"),
        ((item.terminal_state_sha256 for item in receipts), "terminal state"),
        ((item.terminal_envelope_sha256 for item in receipts), "terminal envelope"),
    ):
        materialized = tuple(values)
        if len(set(materialized)) != len(materialized):
            raise RedLivingDexEpisodeLineageError(
                f"fresh-episode tranche repeats a {subject}"
            )
    targets = Counter(item.target_template_ordinal for item in receipts)
    pressures = tuple(
        sorted(
            {
                item.observed_storage_pressure_millionths
                for item in receipts
                if item.observed_storage_pressure_millionths is not None
            }
        )
    )
    expected_success_pressures = {
        assignment.target_storage_pressure_millionths
        for assignment in plan.assignments
        if assignment.assignment_id in by_assignment
        and assignment.target_storage_pressure_millionths is not None
    }
    if set(pressures) != expected_success_pressures:
        raise RedLivingDexEpisodeLineageError(
            "fresh-episode receipts lost an observed storage-pressure disposition"
        )
    return RedLivingDexFreshEpisodeAdmission(
        plan_sha256=plan.plan_sha256,
        roots_admitted=len(receipts),
        attempts_failed=len(failures),
        target_template_counts=tuple(sorted(targets.items())),
        storage_pressure_values_millionths=pressures,
    )


def preflight_red_living_dex_fresh_episode_plan(
    plan: RedLivingDexFreshEpisodePlan,
    *,
    effects_before: RedLivingDexSetupProtectedEffectCheckpoint,
    effects_after: RedLivingDexSetupProtectedEffectCheckpoint,
) -> RedLivingDexFreshEpisodePreflight:
    """Qualify only the prospective plan while every protected effect is zero."""

    if not isinstance(plan, RedLivingDexFreshEpisodePlan):
        raise TypeError("fresh-episode preflight needs its plan")
    plan.__post_init__()
    for checkpoint in (effects_before, effects_after):
        if not isinstance(checkpoint, RedLivingDexSetupProtectedEffectCheckpoint):
            raise TypeError("fresh-episode preflight needs protected-effect checkpoints")
        checkpoint.__post_init__()
    if effects_before != effects_after or any(
        getattr(effects_after, field)
        for field in effects_after.__dataclass_fields__
    ):
        raise RedLivingDexEpisodeLineageError(
            "fresh-episode preflight crossed a protected effect"
        )
    targets = Counter(
        item.target_template_ordinal for item in plan.assignments
    )
    pressures = tuple(
        sorted(
            {
                item.target_storage_pressure_millionths
                for item in plan.assignments
                if item.target_storage_pressure_millionths is not None
            }
        )
    )
    return RedLivingDexFreshEpisodePreflight(
        plan_sha256=plan.plan_sha256,
        assignments=len(plan.assignments),
        target_template_counts=tuple(sorted(targets.items())),
        storage_pressure_values_millionths=pressures,
    )


def encode_red_living_dex_fresh_episode_plan(
    plan: RedLivingDexFreshEpisodePlan,
) -> bytes:
    """Return one canonical path-free public plan."""

    if not isinstance(plan, RedLivingDexFreshEpisodePlan):
        raise TypeError("fresh-episode encoder needs its plan")
    plan.__post_init__()
    return _canonical_line(plan.public_dict())


def parse_red_living_dex_fresh_episode_plan(
    payload: bytes,
) -> RedLivingDexFreshEpisodePlan:
    """Parse and reauthenticate one canonical public generator plan."""

    value = _decode_canonical(payload)
    _exact_keys(
        value,
        {
            "assignments",
            "baseline_train_maximum_matching",
            "capacity_evidence_sha256",
            "causal_independence",
            "development_materialized",
            "failure_disposition",
            "first_tranche",
            "generator_execution_sha256",
            "partition",
            "recensus_required_before_outcome_collection",
            "schema",
            "source",
            "teacher_execution_sha256",
        },
    )
    if (
        value["schema"] != RED_LIVING_DEX_FRESH_EPISODE_PLAN_SCHEMA
        or value["first_tranche"] is not True
        or value["development_materialized"] is not False
        or value["partition"] != RED_LIVING_DEX_FRESH_EPISODE_PARTITION
        or value["recensus_required_before_outcome_collection"] is not True
        or value["causal_independence"]
        != {
            "assignment_precedes_terminal_state": True,
            "clean_power_required": True,
            "distinct_process_episode_required": True,
            "parent_checkpoint_allowed": False,
            "save_state_loads_allowed": 0,
            "state_or_rng_rehash_creates_lineage": False,
        }
        or value["failure_disposition"]
        != {
            "all_frozen_assignments_required": True,
            "failed_attempts_retained": True,
            "failure_does_not_discard_other_valid_roots": True,
            "retry_after_consumption": False,
            "successor_targets_require_action_free_recensus": True,
        }
    ):
        raise RedLivingDexEpisodeLineageError(
            "fresh-episode plan authority boundary differs"
        )
    source = _mapping(value["source"], "fresh-episode source")
    _exact_keys(source, {"commit", "source_bundle_sha256"})
    raw_assignments = value["assignments"]
    if not isinstance(raw_assignments, list):
        raise RedLivingDexEpisodeLineageError(
            "fresh-episode plan assignments are invalid"
        )
    assignments = tuple(_parse_assignment(item) for item in raw_assignments)
    return RedLivingDexFreshEpisodePlan(
        source_commit=_text(source["commit"], "fresh-episode source commit"),
        source_bundle_sha256=_text(
            source["source_bundle_sha256"],
            "fresh-episode source bundle",
        ),
        teacher_execution_sha256=_text(
            value["teacher_execution_sha256"],
            "fresh-episode teacher execution",
        ),
        generator_execution_sha256=_text(
            value["generator_execution_sha256"],
            "fresh-episode generator execution",
        ),
        capacity_evidence_sha256=_text(
            value["capacity_evidence_sha256"],
            "fresh-episode capacity evidence",
        ),
        baseline_train_maximum_matching=_require_integer(
            value["baseline_train_maximum_matching"],
            "fresh-episode capacity baseline",
        ),
        assignments=assignments,
    )


def _parse_assignment(value: object) -> RedLivingDexFreshEpisodeAssignment:
    row = _mapping(value, "fresh-episode assignment")
    _exact_keys(
        row,
        {
            "assignment_id",
            "campaign_id",
            "capacity_evidence_sha256",
            "declared_runs",
            "episode_id",
            "harness_seed",
            "initial_wait_frames",
            "generator_execution_sha256",
            "ordinal",
            "partition",
            "root_lineage_id",
            "run_id",
            "schema",
            "source_bundle_sha256",
            "target_active_box_count",
            "target_checkpoint_id",
            "target_storage_pressure_millionths",
            "target_template_ordinal",
            "teacher_execution_sha256",
        },
    )
    if row["schema"] != RED_LIVING_DEX_FRESH_EPISODE_ASSIGNMENT_SCHEMA:
        raise RedLivingDexEpisodeLineageError(
            "fresh-episode assignment schema differs"
        )
    active_box = row["target_active_box_count"]
    if active_box is not None:
        active_box = _require_integer(active_box, "fresh-episode active-box target")
    assignment = RedLivingDexFreshEpisodeAssignment(
        campaign_id=_text(row["campaign_id"], "fresh-episode campaign"),
        run_id=_text(row["run_id"], "fresh-episode run"),
        ordinal=_require_integer(row["ordinal"], "fresh-episode ordinal"),
        declared_runs=_require_integer(
            row["declared_runs"], "fresh-episode declared runs"
        ),
        partition=_text(row["partition"], "fresh-episode partition"),
        harness_seed=_require_integer(
            row["harness_seed"], "fresh-episode harness seed"
        ),
        initial_wait_frames=_require_integer(
            row["initial_wait_frames"], "fresh-episode initial wait"
        ),
        target_template_ordinal=_require_integer(
            row["target_template_ordinal"], "fresh-episode target template"
        ),
        target_active_box_count=active_box,
        target_checkpoint_id=_text(
            row["target_checkpoint_id"], "fresh-episode checkpoint"
        ),
        source_bundle_sha256=_text(
            row["source_bundle_sha256"], "fresh-episode source bundle"
        ),
        teacher_execution_sha256=_text(
            row["teacher_execution_sha256"], "fresh-episode teacher execution"
        ),
        generator_execution_sha256=_text(
            row["generator_execution_sha256"],
            "fresh-episode generator execution",
        ),
        capacity_evidence_sha256=_text(
            row["capacity_evidence_sha256"], "fresh-episode capacity evidence"
        ),
        assignment_id=_text(row["assignment_id"], "fresh-episode assignment"),
        root_lineage_id=_text(
            row["root_lineage_id"], "fresh-episode root lineage"
        ),
        episode_id=_text(row["episode_id"], "fresh-episode episode"),
    )
    if (
        row["target_storage_pressure_millionths"]
        != assignment.target_storage_pressure_millionths
    ):
        raise RedLivingDexEpisodeLineageError(
            "fresh-episode storage-pressure derivation differs"
        )
    return assignment


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


def _decode_canonical(payload: bytes) -> dict[str, object]:
    if not isinstance(payload, bytes):
        raise TypeError("fresh-episode plan payload must be bytes")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise RedLivingDexEpisodeLineageError(
            "fresh-episode plan is not canonical ASCII JSON"
        ) from None
    if not isinstance(value, dict) or _canonical_line(value) != payload:
        raise RedLivingDexEpisodeLineageError(
            "fresh-episode plan is not canonical ASCII JSON"
        )
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _exact_keys(value: Mapping[str, object], expected: set[str]) -> None:
    if set(value) != expected:
        raise RedLivingDexEpisodeLineageError(
            "fresh-episode document fields differ"
        )


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(
        not isinstance(key, str) for key in value
    ):
        raise RedLivingDexEpisodeLineageError(f"{subject} is invalid")
    return value


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise RedLivingDexEpisodeLineageError(f"{subject} is invalid")
    return value


def _require_safe_id(value: str, subject: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise RedLivingDexEpisodeLineageError(f"{subject} is invalid")
    return value


def _require_sha256(value: str, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexEpisodeLineageError(f"{subject} is invalid")
    return value


def _require_uint64(value: int, subject: str) -> int:
    if type(value) is not int or not 0 <= value < (1 << 64):  # noqa: E721
        raise RedLivingDexEpisodeLineageError(f"{subject} is invalid")
    return value


def _require_integer(value: object, subject: str) -> int:
    if type(value) is not int:  # noqa: E721
        raise RedLivingDexEpisodeLineageError(f"{subject} is invalid")
    return value
