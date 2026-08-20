"""Prospective, path-free contracts for learned clean-start evaluation.

The campaign registry is frozen before any counted root is opened.  It binds
one published source identity, every model role, the supported ROM, the
objective graph, the behavior configuration, and ten deterministic timing
assignments.  Outcome files repeat the observed identities and assistance
counters so an independent checker can reject a plausible-looking completion
that came from another source, model, root, or authority lane.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pokemon_red_completion.collection_protocol import (
    BATTLE_PLAN_ROSTER_SCHEMA,
    BATTLE_START_MAX_OFFSET_FRAMES,
    BATTLE_START_SCHEDULE_DERIVATION,
    BATTLE_START_SCHEDULE_SCHEMA,
    BattleStartSchedule,
    collection_document_sha256,
)

CLEAN_START_CAMPAIGN_SCHEMA = "pokemon-clean-start-learned-stack-campaign-v1"
CLEAN_START_EXECUTION_SCHEMA = "pokemon-clean-start-learned-stack-execution-v1"
CLEAN_START_OUTCOME_SCHEMA = "pokemon-clean-start-learned-stack-outcome-v1"
CLEAN_START_ASSIGNMENT_SCHEMA = "pokemon-clean-start-learned-stack-assignment-v1"
CLEAN_START_SERIES_RESULT_SCHEMA = "pokemon-clean-start-learned-stack-series-result-v1"
CLEAN_START_ASSISTANCE_CLASS = "learned_stack_zero_teacher"
CLEAN_START_GAME_ID = "pokemon.mainline:red:gb:us:rev0"
CLEAN_START_ADAPTER_ID = "pokemon.red.gb.us.rev0.v1"
CLEAN_START_ONTOLOGY_ID = "pokemon.core.v1"
CLEAN_START_ATTEMPTS = 10
CLEAN_START_REQUIRED_SUCCESSES = 8
CLEAN_START_CHECKPOINTS = 312
CLEAN_START_OBJECTIVES = 36

REQUIRED_MODEL_ROLES = (
    "battle_control",
    "battle_move",
    "objective",
    "training_candidate",
    "training_control",
)
ASSISTANCE_COUNTERS = (
    "action_substitutions",
    "expected_route_labels",
    "human_inputs",
    "low_confidence_fallbacks",
    "save_state_loads",
    "safety_fallbacks",
    "teacher_fallbacks",
    "teacher_queries",
    "undeclared_safety_substitutions",
)

_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_DATE = re.compile(r"20[0-9]{2}-[01][0-9]-[0-3][0-9]\Z")
_MAX_REGISTRY_BYTES = 1024 * 1024
_MAX_OUTCOME_BYTES = 256 * 1024
_INITIAL_WAIT_DOMAIN = b"pokemon-clean-start-initial-wait-v1\0"


class CleanStartCampaignError(ValueError):
    """Raised when prospective evaluation evidence is ambiguous or mutable."""


@dataclass(frozen=True, slots=True)
class ModelArtifactIdentity:
    role: str
    artifact_sha256: str

    def __post_init__(self) -> None:
        _require_safe_id(self.role, subject="model role")
        _require_sha256(self.artifact_sha256, subject="model artifact")

    def public_dict(self) -> dict[str, object]:
        return {"artifact_sha256": self.artifact_sha256, "role": self.role}


@dataclass(frozen=True, slots=True)
class CleanStartExecutionIdentity:
    source_commit: str
    source_bundle_sha256: str
    source_published: bool
    worktree_dirty: bool
    rom_sha1: str
    rom_sha256: str
    python_version: str
    emulator_name: str
    emulator_version: str
    objective_graph_sha256: str
    configuration_sha256: str
    models: tuple[ModelArtifactIdentity, ...]

    def __post_init__(self) -> None:
        if _GIT_OID.fullmatch(self.source_commit) is None:
            raise CleanStartCampaignError("source commit is invalid")
        _require_sha256(self.source_bundle_sha256, subject="source bundle")
        if self.source_published is not True or self.worktree_dirty is not False:
            raise CleanStartCampaignError("campaign source must be clean and published")
        if _SHA1.fullmatch(self.rom_sha1) is None:
            raise CleanStartCampaignError("ROM SHA-1 is invalid")
        _require_sha256(self.rom_sha256, subject="ROM")
        for name, version_value in (
            ("python version", self.python_version),
            ("emulator name", self.emulator_name),
            ("emulator version", self.emulator_version),
        ):
            if (
                not isinstance(version_value, str)
                or not version_value
                or len(version_value) > 64
            ):
                raise CleanStartCampaignError(f"{name} is invalid")
        _require_sha256(self.objective_graph_sha256, subject="objective graph")
        _require_sha256(self.configuration_sha256, subject="configuration")
        roles = tuple(model.role for model in self.models)
        if roles != REQUIRED_MODEL_ROLES:
            raise CleanStartCampaignError(
                "model roles must be complete, unique, and canonically ordered"
            )
        if len({model.artifact_sha256 for model in self.models}) != len(self.models):
            raise CleanStartCampaignError("model artifact identities must be distinct")

    @property
    def execution_sha256(self) -> str:
        return collection_document_sha256(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        return {
            "configuration_sha256": self.configuration_sha256,
            "emulator": {"name": self.emulator_name, "version": self.emulator_version},
            "models": [model.public_dict() for model in self.models],
            "objective_graph_sha256": self.objective_graph_sha256,
            "python_version": self.python_version,
            "rom": {"sha1": self.rom_sha1, "sha256": self.rom_sha256},
            "schema": CLEAN_START_EXECUTION_SCHEMA,
            "source": {
                "commit": self.source_commit,
                "published": self.source_published,
                "source_bundle_sha256": self.source_bundle_sha256,
                "worktree_dirty": self.worktree_dirty,
            },
        }


@dataclass(frozen=True, slots=True)
class CleanStartRun:
    run_id: str
    ordinal: int
    harness_seed: int
    initial_wait_frames: int
    battle_schedule_sha256: str

    def __post_init__(self) -> None:
        _require_safe_id(self.run_id, subject="run identity")
        _require_int(self.ordinal, minimum=1, maximum=CLEAN_START_ATTEMPTS, subject="ordinal")
        _require_int(self.harness_seed, minimum=0, maximum=(1 << 64) - 1, subject="seed")
        _require_int(
            self.initial_wait_frames,
            minimum=0,
            maximum=BATTLE_START_MAX_OFFSET_FRAMES,
            subject="initial wait",
        )
        _require_sha256(self.battle_schedule_sha256, subject="battle schedule")

    def public_dict(self) -> dict[str, object]:
        return {
            "battle_schedule_sha256": self.battle_schedule_sha256,
            "harness_seed": self.harness_seed,
            "initial_wait_frames": self.initial_wait_frames,
            "ordinal": self.ordinal,
            "run_id": self.run_id,
        }


@dataclass(frozen=True, slots=True)
class CleanStartAssignment:
    campaign_id: str
    registry_sha256: str
    execution_sha256: str
    run: CleanStartRun
    assignment_id: str

    def public_dict(self) -> dict[str, object]:
        return {
            "assignment_id": self.assignment_id,
            "campaign_id": self.campaign_id,
            "execution_sha256": self.execution_sha256,
            "registry_sha256": self.registry_sha256,
            "root": self.run.public_dict(),
            "schema": CLEAN_START_ASSIGNMENT_SCHEMA,
        }


@dataclass(frozen=True, slots=True)
class CleanStartCampaign:
    campaign_id: str
    recorded_on: str
    game_id: str
    adapter_id: str
    ontology_id: str
    assistance_class: str
    execution: CleanStartExecutionIdentity
    schedule: BattleStartSchedule
    runs: tuple[CleanStartRun, ...]
    registry_sha256: str

    def __post_init__(self) -> None:
        _require_safe_id(self.campaign_id, subject="campaign identity")
        if _DATE.fullmatch(self.recorded_on) is None:
            raise CleanStartCampaignError("campaign date is invalid")
        if self.game_id != CLEAN_START_GAME_ID:
            raise CleanStartCampaignError("campaign game identity is unsupported")
        if self.adapter_id != CLEAN_START_ADAPTER_ID:
            raise CleanStartCampaignError("campaign adapter identity is unsupported")
        if self.ontology_id != CLEAN_START_ONTOLOGY_ID:
            raise CleanStartCampaignError("campaign ontology identity is unsupported")
        if self.assistance_class != CLEAN_START_ASSISTANCE_CLASS:
            raise CleanStartCampaignError("campaign assistance class is not strict")
        _require_sha256(self.registry_sha256, subject="registry")
        if len(self.runs) != CLEAN_START_ATTEMPTS:
            raise CleanStartCampaignError("campaign must declare exactly ten attempts")
        if tuple(run.ordinal for run in self.runs) != tuple(range(1, 11)):
            raise CleanStartCampaignError("campaign ordinals must be contiguous and ordered")
        if len({run.run_id for run in self.runs}) != len(self.runs):
            raise CleanStartCampaignError("campaign run identities are duplicated")
        if len({run.harness_seed for run in self.runs}) != len(self.runs):
            raise CleanStartCampaignError("campaign harness seeds are duplicated")
        if len({run.battle_schedule_sha256 for run in self.runs}) != len(self.runs):
            raise CleanStartCampaignError("campaign battle schedules are duplicated")
        for run in self.runs:
            expected_id = f"{self.campaign_id}-{run.ordinal:02d}"
            if run.run_id != expected_id:
                raise CleanStartCampaignError("campaign run identity is not canonical")
            if run.initial_wait_frames != derive_initial_wait_frames(run.harness_seed):
                raise CleanStartCampaignError("campaign initial wait derivation is invalid")
            if run.battle_schedule_sha256 != self.schedule.schedule_sha256(run.harness_seed):
                raise CleanStartCampaignError("campaign battle schedule derivation is invalid")

    def run(self, run_id: str) -> CleanStartRun:
        _require_safe_id(run_id, subject="run identity")
        for run in self.runs:
            if run.run_id == run_id:
                return run
        raise CleanStartCampaignError("run is not declared by the campaign")

    def assignment(self, run_id: str) -> CleanStartAssignment:
        run = self.run(run_id)
        execution_sha256 = self.execution.execution_sha256
        assignment_id = collection_document_sha256(
            {
                "campaign_id": self.campaign_id,
                "execution_sha256": execution_sha256,
                "registry_sha256": self.registry_sha256,
                "root": run.public_dict(),
                "schema": CLEAN_START_ASSIGNMENT_SCHEMA,
            }
        )
        return CleanStartAssignment(
            campaign_id=self.campaign_id,
            registry_sha256=self.registry_sha256,
            execution_sha256=execution_sha256,
            run=run,
            assignment_id=assignment_id,
        )


@dataclass(frozen=True, slots=True)
class CleanStartOutcome:
    campaign_id: str
    registry_sha256: str
    assignment_id: str
    execution_sha256: str
    run_id: str
    ordinal: int
    status: str
    terminal_reason: str
    report_sha256: str
    started_from_clean_power: bool
    save_state_loaded: bool
    human_input: bool
    controller_released: bool
    initial_wait_frames: int
    battle_schedule_sha256: str
    actions: int
    frames: int
    wall_time_seconds: float
    champion_defeated: bool
    hall_of_fame_entered: bool
    checkpoints: int
    objectives: int
    assistance: tuple[tuple[str, int], ...]
    objective_dispatch_mode: str
    learned_choice_decisions: int
    fixed_dispatch_decisions: int
    component_decisions: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        _require_safe_id(self.campaign_id, subject="outcome campaign")
        _require_sha256(self.registry_sha256, subject="outcome registry")
        _require_sha256(self.assignment_id, subject="outcome assignment")
        _require_sha256(self.execution_sha256, subject="outcome execution")
        _require_safe_id(self.run_id, subject="outcome run")
        _require_int(self.ordinal, minimum=1, maximum=10, subject="outcome ordinal")
        if self.status not in {"complete", "failed", "interrupted"}:
            raise CleanStartCampaignError("outcome status is invalid")
        _require_safe_id(self.terminal_reason, subject="terminal reason")
        _require_sha256(self.report_sha256, subject="private report")
        for name, boolean_value in (
            ("started_from_clean_power", self.started_from_clean_power),
            ("save_state_loaded", self.save_state_loaded),
            ("human_input", self.human_input),
            ("controller_released", self.controller_released),
            ("champion_defeated", self.champion_defeated),
            ("hall_of_fame_entered", self.hall_of_fame_entered),
        ):
            if not isinstance(boolean_value, bool):
                raise CleanStartCampaignError(f"{name} must be boolean")
        _require_int(
            self.initial_wait_frames,
            minimum=0,
            maximum=BATTLE_START_MAX_OFFSET_FRAMES,
            subject="outcome initial wait",
        )
        _require_sha256(self.battle_schedule_sha256, subject="outcome schedule")
        for name, integer_value in (
            ("actions", self.actions),
            ("frames", self.frames),
            ("checkpoints", self.checkpoints),
            ("objectives", self.objectives),
            ("learned choice decisions", self.learned_choice_decisions),
            ("fixed dispatch decisions", self.fixed_dispatch_decisions),
        ):
            _require_int(integer_value, minimum=0, maximum=(1 << 63) - 1, subject=name)
        if (
            isinstance(self.wall_time_seconds, bool)
            or not isinstance(self.wall_time_seconds, (int, float))
            or not 0 <= float(self.wall_time_seconds) < 7 * 24 * 60 * 60
        ):
            raise CleanStartCampaignError("outcome wall time is invalid")
        if not isinstance(self.objective_dispatch_mode, str) or not self.objective_dispatch_mode:
            raise CleanStartCampaignError("objective dispatch mode is invalid")
        if tuple(name for name, _ in self.assistance) != ASSISTANCE_COUNTERS:
            raise CleanStartCampaignError("assistance counters are incomplete or unordered")
        if tuple(name for name, _ in self.component_decisions) != REQUIRED_MODEL_ROLES:
            raise CleanStartCampaignError("component decision counters are incomplete or unordered")
        for name, counter_value in (*self.assistance, *self.component_decisions):
            _require_int(counter_value, minimum=0, maximum=(1 << 63) - 1, subject=name)

    def assistance_dict(self) -> dict[str, int]:
        return dict(self.assistance)

    def component_decisions_dict(self) -> dict[str, int]:
        return dict(self.component_decisions)


@dataclass(frozen=True, slots=True)
class CleanStartRunAssessment:
    run_id: str
    ordinal: int
    classification: str
    reasons: tuple[str, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "classification": self.classification,
            "ordinal": self.ordinal,
            "reasons": list(self.reasons),
            "run_id": self.run_id,
        }


@dataclass(frozen=True, slots=True)
class CleanStartSeriesResult:
    campaign: CleanStartCampaign
    assessments: tuple[CleanStartRunAssessment, ...]

    @property
    def counts(self) -> dict[str, int]:
        return {
            name: sum(item.classification == name for item in self.assessments)
            for name in ("success", "failure", "invalid", "pending")
        }

    @property
    def series_complete(self) -> bool:
        counts = self.counts
        return counts["pending"] == 0 and counts["invalid"] == 0

    @property
    def threshold_met(self) -> bool:
        return self.series_complete and self.counts["success"] >= CLEAN_START_REQUIRED_SUCCESSES

    @property
    def promotion_eligible(self) -> bool:
        return self.threshold_met

    def public_dict(self) -> dict[str, object]:
        counts = self.counts
        return {
            "assistance_class": self.campaign.assistance_class,
            "campaign_id": self.campaign.campaign_id,
            "counts": counts,
            "declared_attempts": CLEAN_START_ATTEMPTS,
            "promotion_eligible": self.promotion_eligible,
            "registry_sha256": self.campaign.registry_sha256,
            "required_successes": CLEAN_START_REQUIRED_SUCCESSES,
            "runs": [assessment.public_dict() for assessment in self.assessments],
            "schema": CLEAN_START_SERIES_RESULT_SCHEMA,
            "series_complete": self.series_complete,
            "status": (
                "passed"
                if self.promotion_eligible
                else ("failed" if self.series_complete else "incomplete_or_invalid")
            ),
            "threshold_met": self.threshold_met,
        }


def derive_initial_wait_frames(harness_seed: int) -> int:
    seed = _require_int(
        harness_seed,
        minimum=0,
        maximum=(1 << 64) - 1,
        subject="harness seed",
    )
    digest = hashlib.sha256(_INITIAL_WAIT_DOMAIN + seed.to_bytes(8, "big")).digest()
    return int.from_bytes(digest[:8], "big") % (BATTLE_START_MAX_OFFSET_FRAMES + 1)


def build_clean_start_campaign(
    *,
    campaign_id: str,
    recorded_on: str,
    execution: CleanStartExecutionIdentity,
    harness_seeds: Sequence[int],
    schedule: BattleStartSchedule,
) -> bytes:
    """Build canonical bytes; parsing the result performs an independent self-check."""

    seeds = tuple(harness_seeds)
    if len(seeds) != CLEAN_START_ATTEMPTS or len(set(seeds)) != len(seeds):
        raise CleanStartCampaignError("exactly ten distinct harness seeds are required")
    runs = [
        {
            "battle_schedule_sha256": schedule.schedule_sha256(seed),
            "harness_seed": seed,
            "initial_wait_frames": derive_initial_wait_frames(seed),
            "ordinal": ordinal,
            "run_id": f"{campaign_id}-{ordinal:02d}",
        }
        for ordinal, seed in enumerate(seeds, start=1)
    ]
    document = {
        "adapter_id": CLEAN_START_ADAPTER_ID,
        "assistance_class": CLEAN_START_ASSISTANCE_CLASS,
        "campaign_id": campaign_id,
        "execution": execution.public_dict(),
        "game_id": CLEAN_START_GAME_ID,
        "ontology_id": CLEAN_START_ONTOLOGY_ID,
        "recorded_on": recorded_on,
        "runs": runs,
        "schedule": {
            "battle_plan_ids": list(schedule.battle_plan_ids),
            "battle_roster_sha256": schedule.battle_roster_sha256,
            "derivation": schedule.derivation,
            "max_offset_frames": schedule.max_offset_frames,
            "schema": schedule.schema,
        },
        "schema": CLEAN_START_CAMPAIGN_SCHEMA,
        "threshold": {
            "attempts_per_assignment": 1,
            "required_successes": CLEAN_START_REQUIRED_SUCCESSES,
            "total_attempts": CLEAN_START_ATTEMPTS,
        },
    }
    payload = _canonical_bytes(document)
    parse_clean_start_campaign(payload)
    return payload


def parse_clean_start_campaign(payload: bytes) -> CleanStartCampaign:
    document, canonical = _decode_canonical(payload, maximum_bytes=_MAX_REGISTRY_BYTES)
    _require_exact_keys(
        document,
        {
            "adapter_id",
            "assistance_class",
            "campaign_id",
            "execution",
            "game_id",
            "ontology_id",
            "recorded_on",
            "runs",
            "schedule",
            "schema",
            "threshold",
        },
        subject="campaign registry",
    )
    if document["schema"] != CLEAN_START_CAMPAIGN_SCHEMA:
        raise CleanStartCampaignError("campaign schema is unsupported")
    threshold = _require_mapping(document["threshold"], subject="campaign threshold")
    _require_exact_keys(
        threshold,
        {"attempts_per_assignment", "required_successes", "total_attempts"},
        subject="campaign threshold",
    )
    if threshold != {
        "attempts_per_assignment": 1,
        "required_successes": CLEAN_START_REQUIRED_SUCCESSES,
        "total_attempts": CLEAN_START_ATTEMPTS,
    }:
        raise CleanStartCampaignError("campaign threshold contract is unsupported")
    execution = _parse_execution(document["execution"])
    schedule = _parse_schedule(document["schedule"])
    runs_value = document["runs"]
    if not isinstance(runs_value, list):
        raise CleanStartCampaignError("campaign runs must be a list")
    runs = tuple(_parse_run(value) for value in runs_value)
    return CleanStartCampaign(
        campaign_id=_require_string(document["campaign_id"], subject="campaign identity"),
        recorded_on=_require_string(document["recorded_on"], subject="campaign date"),
        game_id=_require_string(document["game_id"], subject="game identity"),
        adapter_id=_require_string(document["adapter_id"], subject="adapter identity"),
        ontology_id=_require_string(document["ontology_id"], subject="ontology identity"),
        assistance_class=_require_string(
            document["assistance_class"], subject="assistance class"
        ),
        execution=execution,
        schedule=schedule,
        runs=runs,
        registry_sha256=hashlib.sha256(canonical).hexdigest(),
    )


def parse_clean_start_outcome(payload: bytes) -> CleanStartOutcome:
    document, _ = _decode_canonical(payload, maximum_bytes=_MAX_OUTCOME_BYTES)
    _require_exact_keys(
        document,
        {
            "assistance",
            "authority",
            "campaign_id",
            "completion",
            "execution_sha256",
            "private_report_sha256",
            "registry_sha256",
            "root",
            "runtime",
            "schema",
            "status",
            "terminal_reason",
        },
        subject="run outcome",
    )
    if document["schema"] != CLEAN_START_OUTCOME_SCHEMA:
        raise CleanStartCampaignError("outcome schema is unsupported")
    root = _require_mapping(document["root"], subject="outcome root")
    _require_exact_keys(
        root,
        {"assignment_id", "ordinal", "run_id"},
        subject="outcome root",
    )
    runtime = _require_mapping(document["runtime"], subject="outcome runtime")
    _require_exact_keys(
        runtime,
        {
            "actions",
            "battle_schedule_sha256",
            "controller_released",
            "frames",
            "human_input",
            "initial_wait_frames",
            "save_state_loaded",
            "started_from_clean_power",
            "wall_time_seconds",
        },
        subject="outcome runtime",
    )
    completion = _require_mapping(document["completion"], subject="outcome completion")
    _require_exact_keys(
        completion,
        {"champion_defeated", "checkpoints", "hall_of_fame_entered", "objectives"},
        subject="outcome completion",
    )
    assistance = _parse_counter_mapping(
        document["assistance"],
        expected=ASSISTANCE_COUNTERS,
        subject="assistance counters",
    )
    authority = _require_mapping(document["authority"], subject="outcome authority")
    _require_exact_keys(
        authority,
        {
            "component_decisions",
            "fixed_dispatch_decisions",
            "learned_choice_decisions",
            "objective_dispatch_mode",
        },
        subject="outcome authority",
    )
    component_decisions = _parse_counter_mapping(
        authority["component_decisions"],
        expected=REQUIRED_MODEL_ROLES,
        subject="component decisions",
    )
    return CleanStartOutcome(
        campaign_id=_require_string(document["campaign_id"], subject="outcome campaign"),
        registry_sha256=_require_string(
            document["registry_sha256"], subject="outcome registry"
        ),
        assignment_id=_require_string(root["assignment_id"], subject="outcome assignment"),
        execution_sha256=_require_string(
            document["execution_sha256"], subject="outcome execution"
        ),
        run_id=_require_string(root["run_id"], subject="outcome run"),
        ordinal=_require_int(root["ordinal"], minimum=1, maximum=10, subject="outcome ordinal"),
        status=_require_string(document["status"], subject="outcome status"),
        terminal_reason=_require_string(
            document["terminal_reason"], subject="terminal reason"
        ),
        report_sha256=_require_string(
            document["private_report_sha256"], subject="private report"
        ),
        started_from_clean_power=_require_bool(
            runtime["started_from_clean_power"], subject="clean power flag"
        ),
        save_state_loaded=_require_bool(
            runtime["save_state_loaded"], subject="save-state flag"
        ),
        human_input=_require_bool(runtime["human_input"], subject="human-input flag"),
        controller_released=_require_bool(
            runtime["controller_released"], subject="controller-release flag"
        ),
        initial_wait_frames=_require_int(
            runtime["initial_wait_frames"],
            minimum=0,
            maximum=BATTLE_START_MAX_OFFSET_FRAMES,
            subject="outcome initial wait",
        ),
        battle_schedule_sha256=_require_string(
            runtime["battle_schedule_sha256"], subject="outcome schedule"
        ),
        actions=_require_int(
            runtime["actions"], minimum=0, maximum=(1 << 63) - 1, subject="actions"
        ),
        frames=_require_int(
            runtime["frames"], minimum=0, maximum=(1 << 63) - 1, subject="frames"
        ),
        wall_time_seconds=_require_float(
            runtime["wall_time_seconds"], subject="wall time"
        ),
        champion_defeated=_require_bool(
            completion["champion_defeated"], subject="Champion flag"
        ),
        hall_of_fame_entered=_require_bool(
            completion["hall_of_fame_entered"], subject="Hall-of-Fame flag"
        ),
        checkpoints=_require_int(
            completion["checkpoints"],
            minimum=0,
            maximum=CLEAN_START_CHECKPOINTS,
            subject="checkpoints",
        ),
        objectives=_require_int(
            completion["objectives"],
            minimum=0,
            maximum=CLEAN_START_OBJECTIVES,
            subject="objectives",
        ),
        assistance=assistance,
        objective_dispatch_mode=_require_string(
            authority["objective_dispatch_mode"], subject="objective dispatch mode"
        ),
        learned_choice_decisions=_require_int(
            authority["learned_choice_decisions"],
            minimum=0,
            maximum=(1 << 63) - 1,
            subject="learned choice decisions",
        ),
        fixed_dispatch_decisions=_require_int(
            authority["fixed_dispatch_decisions"],
            minimum=0,
            maximum=(1 << 63) - 1,
            subject="fixed dispatch decisions",
        ),
        component_decisions=component_decisions,
    )


def evaluate_clean_start_series(
    campaign: CleanStartCampaign,
    outcomes: Sequence[CleanStartOutcome],
) -> CleanStartSeriesResult:
    """Evaluate all ten declared slots; absent, duplicate, or alien evidence cannot pass."""

    by_run: dict[str, CleanStartOutcome] = {}
    for candidate_outcome in outcomes:
        if candidate_outcome.run_id in by_run:
            raise CleanStartCampaignError("multiple outcomes claim the same run")
        by_run[candidate_outcome.run_id] = candidate_outcome
    unexpected = set(by_run).difference(run.run_id for run in campaign.runs)
    if unexpected:
        raise CleanStartCampaignError("outcome claims a run outside the campaign")
    assessments: list[CleanStartRunAssessment] = []
    for run in campaign.runs:
        current_outcome = by_run.get(run.run_id)
        if current_outcome is None:
            assessments.append(
                CleanStartRunAssessment(run.run_id, run.ordinal, "pending", ("missing_outcome",))
            )
            continue
        assignment = campaign.assignment(run.run_id)
        binding_reasons = _binding_reasons(campaign, assignment, current_outcome)
        if binding_reasons:
            assessments.append(
                CleanStartRunAssessment(run.run_id, run.ordinal, "invalid", binding_reasons)
            )
            continue
        success_reasons = _success_reasons(current_outcome)
        assessments.append(
            CleanStartRunAssessment(
                run.run_id,
                run.ordinal,
                "success" if not success_reasons else "failure",
                success_reasons,
            )
        )
    return CleanStartSeriesResult(campaign, tuple(assessments))


def _binding_reasons(
    campaign: CleanStartCampaign,
    assignment: CleanStartAssignment,
    outcome: CleanStartOutcome,
) -> tuple[str, ...]:
    reasons: list[str] = []
    checks = (
        (outcome.campaign_id == campaign.campaign_id, "campaign_identity_mismatch"),
        (outcome.registry_sha256 == campaign.registry_sha256, "registry_identity_mismatch"),
        (outcome.assignment_id == assignment.assignment_id, "assignment_identity_mismatch"),
        (outcome.execution_sha256 == assignment.execution_sha256, "execution_identity_mismatch"),
        (outcome.ordinal == assignment.run.ordinal, "ordinal_mismatch"),
        (
            outcome.initial_wait_frames == assignment.run.initial_wait_frames,
            "initial_wait_mismatch",
        ),
        (
            outcome.battle_schedule_sha256 == assignment.run.battle_schedule_sha256,
            "battle_schedule_mismatch",
        ),
    )
    reasons.extend(reason for passed, reason in checks if not passed)
    return tuple(reasons)


def _success_reasons(outcome: CleanStartOutcome) -> tuple[str, ...]:
    reasons: list[str] = []
    checks = (
        (outcome.status == "complete", "run_not_complete"),
        (outcome.terminal_reason == "hall_of_fame_verified", "terminal_reason_not_hall_of_fame"),
        (outcome.started_from_clean_power, "not_started_from_clean_power"),
        (not outcome.save_state_loaded, "save_state_loaded"),
        (not outcome.human_input, "human_input_observed"),
        (outcome.controller_released, "controller_not_released"),
        (outcome.champion_defeated, "champion_not_verified"),
        (outcome.hall_of_fame_entered, "hall_of_fame_not_verified"),
        (outcome.checkpoints == CLEAN_START_CHECKPOINTS, "checkpoint_contract_failed"),
        (outcome.objectives == CLEAN_START_OBJECTIVES, "objective_contract_failed"),
        (
            outcome.objective_dispatch_mode == "model_selected_specialists",
            "objective_dispatch_not_model_selected",
        ),
        (outcome.learned_choice_decisions > 0, "no_learned_objective_choice"),
        (outcome.fixed_dispatch_decisions == 0, "fixed_objective_dispatch_present"),
    )
    reasons.extend(reason for passed, reason in checks if not passed)
    reasons.extend(
        f"assistance_{name}_nonzero"
        for name, value in outcome.assistance
        if value != 0
    )
    reasons.extend(
        f"component_{name}_had_no_authority"
        for name, value in outcome.component_decisions
        if value <= 0
    )
    return tuple(reasons)


def _parse_execution(value: object) -> CleanStartExecutionIdentity:
    execution = _require_mapping(value, subject="campaign execution")
    _require_exact_keys(
        execution,
        {
            "configuration_sha256",
            "emulator",
            "models",
            "objective_graph_sha256",
            "python_version",
            "rom",
            "schema",
            "source",
        },
        subject="campaign execution",
    )
    if execution["schema"] != CLEAN_START_EXECUTION_SCHEMA:
        raise CleanStartCampaignError("execution schema is unsupported")
    source = _require_mapping(execution["source"], subject="execution source")
    _require_exact_keys(
        source,
        {"commit", "published", "source_bundle_sha256", "worktree_dirty"},
        subject="execution source",
    )
    rom = _require_mapping(execution["rom"], subject="execution ROM")
    _require_exact_keys(rom, {"sha1", "sha256"}, subject="execution ROM")
    emulator = _require_mapping(execution["emulator"], subject="execution emulator")
    _require_exact_keys(emulator, {"name", "version"}, subject="execution emulator")
    models_value = execution["models"]
    if not isinstance(models_value, list):
        raise CleanStartCampaignError("execution models must be a list")
    models: list[ModelArtifactIdentity] = []
    for value in models_value:
        model = _require_mapping(value, subject="model identity")
        _require_exact_keys(model, {"artifact_sha256", "role"}, subject="model identity")
        models.append(
            ModelArtifactIdentity(
                role=_require_string(model["role"], subject="model role"),
                artifact_sha256=_require_string(
                    model["artifact_sha256"], subject="model artifact"
                ),
            )
        )
    return CleanStartExecutionIdentity(
        source_commit=_require_string(source["commit"], subject="source commit"),
        source_bundle_sha256=_require_string(
            source["source_bundle_sha256"], subject="source bundle"
        ),
        source_published=_require_bool(source["published"], subject="source published flag"),
        worktree_dirty=_require_bool(source["worktree_dirty"], subject="worktree dirty flag"),
        rom_sha1=_require_string(rom["sha1"], subject="ROM SHA-1"),
        rom_sha256=_require_string(rom["sha256"], subject="ROM SHA-256"),
        python_version=_require_string(execution["python_version"], subject="python version"),
        emulator_name=_require_string(emulator["name"], subject="emulator name"),
        emulator_version=_require_string(emulator["version"], subject="emulator version"),
        objective_graph_sha256=_require_string(
            execution["objective_graph_sha256"], subject="objective graph"
        ),
        configuration_sha256=_require_string(
            execution["configuration_sha256"], subject="configuration"
        ),
        models=tuple(models),
    )


def _parse_schedule(value: object) -> BattleStartSchedule:
    schedule = _require_mapping(value, subject="campaign schedule")
    _require_exact_keys(
        schedule,
        {
            "battle_plan_ids",
            "battle_roster_sha256",
            "derivation",
            "max_offset_frames",
            "schema",
        },
        subject="campaign schedule",
    )
    plan_ids = schedule["battle_plan_ids"]
    if (
        not isinstance(plan_ids, list)
        or not plan_ids
        or any(not isinstance(item, str) for item in plan_ids)
        or len(set(plan_ids)) != len(plan_ids)
    ):
        raise CleanStartCampaignError("campaign battle plan roster is invalid")
    typed_plan_ids = tuple(
        _require_string(item, subject="battle plan identity") for item in plan_ids
    )
    roster_sha256 = collection_document_sha256(
        {"battle_plan_ids": list(typed_plan_ids), "schema": BATTLE_PLAN_ROSTER_SCHEMA}
    )
    if schedule["battle_roster_sha256"] != roster_sha256:
        raise CleanStartCampaignError("campaign battle roster digest is invalid")
    if (
        schedule["schema"] != BATTLE_START_SCHEDULE_SCHEMA
        or schedule["derivation"] != BATTLE_START_SCHEDULE_DERIVATION
        or schedule["max_offset_frames"] != BATTLE_START_MAX_OFFSET_FRAMES
    ):
        raise CleanStartCampaignError("campaign schedule contract is unsupported")
    return BattleStartSchedule(
        battle_plan_ids=typed_plan_ids,
        battle_roster_sha256=roster_sha256,
        derivation=BATTLE_START_SCHEDULE_DERIVATION,
        max_offset_frames=BATTLE_START_MAX_OFFSET_FRAMES,
        schema=BATTLE_START_SCHEDULE_SCHEMA,
    )


def _parse_run(value: object) -> CleanStartRun:
    run = _require_mapping(value, subject="campaign run")
    _require_exact_keys(
        run,
        {
            "battle_schedule_sha256",
            "harness_seed",
            "initial_wait_frames",
            "ordinal",
            "run_id",
        },
        subject="campaign run",
    )
    return CleanStartRun(
        run_id=_require_string(run["run_id"], subject="run identity"),
        ordinal=_require_int(run["ordinal"], minimum=1, maximum=10, subject="run ordinal"),
        harness_seed=_require_int(
            run["harness_seed"],
            minimum=0,
            maximum=(1 << 64) - 1,
            subject="run seed",
        ),
        initial_wait_frames=_require_int(
            run["initial_wait_frames"],
            minimum=0,
            maximum=BATTLE_START_MAX_OFFSET_FRAMES,
            subject="run initial wait",
        ),
        battle_schedule_sha256=_require_string(
            run["battle_schedule_sha256"], subject="battle schedule"
        ),
    )


def _parse_counter_mapping(
    value: object,
    *,
    expected: tuple[str, ...],
    subject: str,
) -> tuple[tuple[str, int], ...]:
    counters = _require_mapping(value, subject=subject)
    _require_exact_keys(counters, set(expected), subject=subject)
    return tuple(
        (
            name,
            _require_int(
                counters[name],
                minimum=0,
                maximum=(1 << 63) - 1,
                subject=f"{subject} {name}",
            ),
        )
        for name in expected
    )


def _decode_canonical(payload: bytes, *, maximum_bytes: int) -> tuple[dict[str, object], bytes]:
    if not isinstance(payload, bytes):
        raise TypeError("evidence payload must be bytes")
    if not payload or len(payload) > maximum_bytes:
        raise CleanStartCampaignError("evidence payload size is invalid")
    try:
        text = payload.decode("ascii")
        document = json.loads(text, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CleanStartCampaignError("evidence is not canonical ASCII JSON") from error
    if not isinstance(document, dict):
        raise CleanStartCampaignError("evidence root must be an object")
    canonical = _canonical_bytes(document)
    if payload != canonical:
        raise CleanStartCampaignError("evidence is not canonical JSON")
    return document, canonical


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CleanStartCampaignError("evidence contains duplicate JSON keys")
        result[key] = value
    return result


def _canonical_bytes(value: object) -> bytes:
    try:
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
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise CleanStartCampaignError("evidence cannot be canonicalized") from error


def _require_mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise CleanStartCampaignError(f"{subject} must be an object")
    return value


def _require_exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    *,
    subject: str,
) -> None:
    if set(value) != expected:
        raise CleanStartCampaignError(f"{subject} fields are invalid")


def _require_string(value: object, *, subject: str) -> str:
    if not isinstance(value, str):
        raise CleanStartCampaignError(f"{subject} must be a string")
    return value


def _require_bool(value: object, *, subject: str) -> bool:
    if not isinstance(value, bool):
        raise CleanStartCampaignError(f"{subject} must be boolean")
    return value


def _require_float(value: object, *, subject: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 <= float(value) < 7 * 24 * 60 * 60
    ):
        raise CleanStartCampaignError(f"{subject} is invalid")
    return float(value)


def _require_safe_id(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise CleanStartCampaignError(f"{subject} is invalid")
    return value


def _require_sha256(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise CleanStartCampaignError(f"{subject} SHA-256 is invalid")
    return value


def _require_int(
    value: object,
    *,
    minimum: int,
    maximum: int,
    subject: str,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:  # noqa: E721
        raise CleanStartCampaignError(f"{subject} is invalid")
    return value
