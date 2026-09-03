"""Strict parser and durable identities for multi-goal calibration execution."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.multi_goal_calibration_plan import (
    CALIBRATION_ROOT_QUOTAS,
    MODEL_CONTROLLED_GOAL_KINDS,
    MULTI_GOAL_CALIBRATION_SCHEDULE_SCHEMA,
)
from pokemon_red_completion.provenance import canonical_sha256

CAMPAIGN_SCHEMA = "pokemon.red.multi-goal-calibration-campaign.v1"
CAMPAIGN_CONSUMPTION_SCHEMA = (
    "pokemon.red.multi-goal-calibration-campaign-consumption.v1"
)
TRIAL_CLAIM_SCHEMA = "pokemon.red.multi-goal-calibration-trial-claim.v1"
EXECUTION_IDENTITY_SCHEMA = (
    "pokemon.red.multi-goal-calibration-trial-execution.v1"
)
ROOT_RESERVATION_SCHEMA = "pokemon.red.multi-goal-calibration-root-reservation.v1"
OUTCOME_OBJECTIVE = "selected-semantic-option-multioutcome-calibration-v1"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SAFE_EPISODE = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")


class MultiGoalCalibrationExecutionError(ValueError):
    """Raised when a frozen campaign or execution identity differs."""


@dataclass(frozen=True, slots=True)
class CalibrationExecutionRoot:
    physical_root_sha256: str
    record: Mapping[str, object]

    @property
    def available_goal_kinds(self) -> tuple[str, ...]:
        raw = self.record["available_goal_kinds"]
        assert isinstance(raw, list)
        return tuple(raw)


@dataclass(frozen=True, slots=True)
class CalibrationExecutionTrial:
    trial_ordinal: int
    root_ordinal: int
    selected_candidate_index: int
    selected_goal_kind: GoalKind
    episode_id: str
    trial_claim_sha256: str


@dataclass(frozen=True, slots=True)
class MultiGoalCalibrationCampaign:
    plan_sha256: str
    campaign_id: str
    campaign_consumption_sha256: str
    source_commit: str
    source_bundle_sha256: str
    freezer_runner_sha256: str
    development_runner_sha256: str
    runtime_sha256: str
    numpy_runtime_sha256: str
    skill_manifest_sha256: str
    context_plan_sha256: str
    inventory_result_sha256: str
    private_root_identity_sha256: str
    candidate: Mapping[str, object]
    roots: tuple[CalibrationExecutionRoot, ...]
    trials: tuple[CalibrationExecutionTrial, ...]

    def root_reservation_execution_identity(self, runner_sha256: str) -> str:
        return canonical_sha256(
            {
                "campaign_consumption_sha256": self.campaign_consumption_sha256,
                "campaign_plan_sha256": self.plan_sha256,
                "runner_sha256": _digest(runner_sha256, "runner"),
                "schema": ROOT_RESERVATION_SCHEMA,
                "source_commit": self.source_commit,
            }
        )

    def trial_execution_identity(
        self,
        trial_ordinal: int,
        runner_sha256: str,
    ) -> str:
        if not 0 <= trial_ordinal < len(self.trials):
            raise MultiGoalCalibrationExecutionError("trial ordinal is invalid")
        trial = self.trials[trial_ordinal]
        return canonical_sha256(
            {
                "campaign_id": self.campaign_id,
                "campaign_plan_sha256": self.plan_sha256,
                "runner_sha256": _digest(runner_sha256, "runner"),
                "schema": EXECUTION_IDENTITY_SCHEMA,
                "source_commit": self.source_commit,
                "trial_claim_sha256": trial.trial_claim_sha256,
                "trial_ordinal": trial_ordinal,
            }
        )


def parse_multi_goal_calibration_campaign(
    payload: bytes,
) -> MultiGoalCalibrationCampaign:
    """Authenticate one canonical private plan without opening any outcome."""

    try:
        document = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MultiGoalCalibrationExecutionError("campaign is not canonical JSON") from error
    canonical = (
        json.dumps(
            document,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    expected_keys = {
        "campaign_consumption_sha256",
        "campaign_id",
        "candidate",
        "context_plan_sha256",
        "development_runner_sha256",
        "inventory_result_sha256",
        "numpy_runtime_sha256",
        "outcome_objective",
        "private_root_identity_sha256",
        "roots",
        "runner_sha256",
        "runtime_sha256",
        "schedule_sha256",
        "schema",
        "skill_manifest_sha256",
        "source_bundle_sha256",
        "source_commit",
        "trials",
    }
    if (
        not isinstance(document, dict)
        or canonical != payload
        or set(document) != expected_keys
        or document.get("schema") != CAMPAIGN_SCHEMA
        or document.get("outcome_objective") != OUTCOME_OBJECTIVE
    ):
        raise MultiGoalCalibrationExecutionError("campaign layout differs")

    raw_roots = document.get("roots")
    raw_trials = document.get("trials")
    raw_candidate = document.get("candidate")
    if (
        not isinstance(raw_roots, list)
        or len(raw_roots) != 4
        or not isinstance(raw_trials, list)
        or not raw_trials
        or not isinstance(raw_candidate, dict)
    ):
        raise MultiGoalCalibrationExecutionError("campaign denominator differs")

    campaign_id = _digest(document.get("campaign_id"), "campaign")
    stripped = dict(document)
    stripped.pop("campaign_id")
    stripped.pop("campaign_consumption_sha256")
    stripped_trials: list[dict[str, object]] = []
    for raw in raw_trials:
        if not isinstance(raw, dict):
            raise MultiGoalCalibrationExecutionError("campaign trial layout differs")
        item = dict(raw)
        item.pop("episode_id", None)
        item.pop("trial_claim_sha256", None)
        stripped_trials.append(item)
    stripped["trials"] = stripped_trials
    if canonical_sha256(stripped) != campaign_id:
        raise MultiGoalCalibrationExecutionError("campaign identity differs")
    campaign_consumption = _digest(
        document.get("campaign_consumption_sha256"),
        "campaign consumption",
    )
    if campaign_consumption != canonical_sha256(
        {"campaign_id": campaign_id, "schema": CAMPAIGN_CONSUMPTION_SCHEMA}
    ):
        raise MultiGoalCalibrationExecutionError("campaign consumption differs")

    roots = tuple(_parse_root(raw) for raw in raw_roots)
    expected_focus_counts = Counter(
        {kind.value: count for kind, count in CALIBRATION_ROOT_QUOTAS}
    )
    observed_focus_counts = Counter(root.record["focus_kind"] for root in roots)
    if (
        len({root.physical_root_sha256 for root in roots}) != len(roots)
        or observed_focus_counts != expected_focus_counts
    ):
        raise MultiGoalCalibrationExecutionError("campaign roots are not distinct")
    trials = tuple(
        _parse_trial(raw, ordinal, campaign_id, roots)
        for ordinal, raw in enumerate(raw_trials)
    )
    if (
        len({trial.episode_id for trial in trials}) != len(trials)
        or len({trial.trial_claim_sha256 for trial in trials}) != len(trials)
        or {trial.root_ordinal for trial in trials} != set(range(len(roots)))
    ):
        raise MultiGoalCalibrationExecutionError("campaign trial identities differ")
    expected_arms = {
        (root_ordinal, candidate_index, raw_kind)
        for root_ordinal, root in enumerate(roots)
        for candidate_index, raw_kind in enumerate(root.available_goal_kinds)
        if GoalKind(raw_kind) in MODEL_CONTROLLED_GOAL_KINDS
    }
    observed_arms = {
        (
            trial.root_ordinal,
            trial.selected_candidate_index,
            trial.selected_goal_kind.value,
        )
        for trial in trials
    }
    if observed_arms != expected_arms or len(trials) != len(expected_arms):
        raise MultiGoalCalibrationExecutionError("campaign arms are incomplete")
    schedule = {
        "root_slot_ids": [root.record["capture_id"] for root in roots],
        "schema": MULTI_GOAL_CALIBRATION_SCHEDULE_SCHEMA,
        "trials": stripped_trials,
    }
    if canonical_sha256(schedule) != _digest(
        document.get("schedule_sha256"),
        "schedule",
    ):
        raise MultiGoalCalibrationExecutionError("campaign schedule differs")

    source_commit = document.get("source_commit")
    if not isinstance(source_commit, str) or _GIT_COMMIT.fullmatch(source_commit) is None:
        raise MultiGoalCalibrationExecutionError("campaign source commit differs")
    return MultiGoalCalibrationCampaign(
        plan_sha256=hashlib.sha256(payload).hexdigest(),
        campaign_id=campaign_id,
        campaign_consumption_sha256=campaign_consumption,
        source_commit=source_commit,
        source_bundle_sha256=_digest(document.get("source_bundle_sha256"), "source"),
        freezer_runner_sha256=_digest(document.get("runner_sha256"), "freezer runner"),
        development_runner_sha256=_digest(
            document.get("development_runner_sha256"),
            "development runner",
        ),
        runtime_sha256=_digest(document.get("runtime_sha256"), "runtime"),
        numpy_runtime_sha256=_digest(
            document.get("numpy_runtime_sha256"),
            "NumPy runtime",
        ),
        skill_manifest_sha256=_digest(
            document.get("skill_manifest_sha256"),
            "skill manifest",
        ),
        context_plan_sha256=_digest(
            document.get("context_plan_sha256"),
            "context plan",
        ),
        inventory_result_sha256=_digest(
            document.get("inventory_result_sha256"),
            "inventory result",
        ),
        private_root_identity_sha256=_digest(
            document.get("private_root_identity_sha256"),
            "private root",
        ),
        candidate=dict(raw_candidate),
        roots=roots,
        trials=trials,
    )


def _parse_root(value: object) -> CalibrationExecutionRoot:
    if (
        not isinstance(value, dict)
        or set(value) != {"partition", "physical_root_sha256", "root"}
        or value.get("partition") != "train"
        or not isinstance(value.get("root"), dict)
    ):
        raise MultiGoalCalibrationExecutionError("campaign root layout differs")
    record = value["root"]
    assert isinstance(record, dict)
    expected_root_keys = {
        "assignment_id",
        "available_goal_kinds",
        "available_menu_sha256",
        "binding_manifest_sha256",
        "capture_id",
        "entry_index",
        "envelope_file_sha256",
        "envelope_sha256",
        "focus_kind",
        "policy_context_sha256",
        "profile_file_sha256",
        "question_sha256",
        "root_lineage_id",
        "state_file_sha256",
        "state_sha256",
    }
    menu = record.get("available_goal_kinds")
    if (
        set(record) != expected_root_keys
        or not isinstance(menu, list)
        or len(menu) < 2
        or len(set(menu)) != len(menu)
        or any(
            not isinstance(kind, str)
            or kind not in {item.value for item in GoalKind}
            for kind in menu
        )
        or type(record.get("entry_index")) is not int  # noqa: E721
        or record["entry_index"] < 0
    ):
        raise MultiGoalCalibrationExecutionError("campaign root record differs")
    digest_keys = expected_root_keys - {
        "available_goal_kinds",
        "capture_id",
        "entry_index",
        "focus_kind",
        "root_lineage_id",
    }
    for key in digest_keys:
        _digest(record.get(key), f"root {key}")
    focus_kind = record.get("focus_kind")
    capture_id = record.get("capture_id")
    assignment_id = record.get("assignment_id")
    if (
        not isinstance(focus_kind, str)
        or focus_kind not in {item.value for item in GoalKind}
        or not isinstance(capture_id, str)
        or _SAFE_EPISODE.fullmatch(capture_id) is None
        or record.get("root_lineage_id") != f"red-goal-root-{assignment_id}"
        or value.get("physical_root_sha256")
        != root_consumption_sha256(
            state_sha256=_digest(record.get("state_sha256"), "root state"),
            envelope_sha256=_digest(
                record.get("envelope_sha256"),
                "root envelope",
            ),
        )
    ):
        raise MultiGoalCalibrationExecutionError("campaign root focus differs")
    return CalibrationExecutionRoot(
        physical_root_sha256=_digest(
            value.get("physical_root_sha256"),
            "physical root",
        ),
        record=dict(record),
    )


def _parse_trial(
    value: object,
    ordinal: int,
    campaign_id: str,
    roots: tuple[CalibrationExecutionRoot, ...],
) -> CalibrationExecutionTrial:
    expected_keys = {
        "episode_id",
        "maximum_decisions",
        "root_ordinal",
        "selected_candidate_index",
        "selected_goal_kind",
        "trial_claim_sha256",
        "trial_ordinal",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise MultiGoalCalibrationExecutionError("campaign trial layout differs")
    root_ordinal = value.get("root_ordinal")
    selected_index = value.get("selected_candidate_index")
    raw_kind = value.get("selected_goal_kind")
    episode_id = value.get("episode_id")
    if (
        value.get("maximum_decisions") != 1
        or value.get("trial_ordinal") != ordinal
        or type(root_ordinal) is not int  # noqa: E721
        or not 0 <= root_ordinal < len(roots)
        or type(selected_index) is not int  # noqa: E721
        or selected_index < 0
        or not isinstance(raw_kind, str)
        or not isinstance(episode_id, str)
        or _SAFE_EPISODE.fullmatch(episode_id) is None
    ):
        raise MultiGoalCalibrationExecutionError("campaign trial values differ")
    try:
        kind = GoalKind(raw_kind)
    except ValueError as error:
        raise MultiGoalCalibrationExecutionError("campaign trial kind differs") from error
    if (
        kind not in MODEL_CONTROLLED_GOAL_KINDS
        or selected_index >= len(roots[root_ordinal].available_goal_kinds)
        or roots[root_ordinal].available_goal_kinds[selected_index] != kind.value
    ):
        raise MultiGoalCalibrationExecutionError("campaign trial binding differs")
    claim = _digest(value.get("trial_claim_sha256"), "trial claim")
    if claim != canonical_sha256(
        {
            "campaign_id": campaign_id,
            "schema": TRIAL_CLAIM_SCHEMA,
            "trial_ordinal": ordinal,
        }
    ):
        raise MultiGoalCalibrationExecutionError("campaign trial claim differs")
    if episode_id != f"red-multigoal-cal-{campaign_id[:32]}-{ordinal:02d}":
        raise MultiGoalCalibrationExecutionError("campaign episode identity differs")
    return CalibrationExecutionTrial(
        trial_ordinal=ordinal,
        root_ordinal=root_ordinal,
        selected_candidate_index=selected_index,
        selected_goal_kind=kind,
        episode_id=episode_id,
        trial_claim_sha256=claim,
    )


def _digest(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise MultiGoalCalibrationExecutionError(f"{subject} digest is invalid")
    return value


__all__ = [
    "CAMPAIGN_SCHEMA",
    "CalibrationExecutionRoot",
    "CalibrationExecutionTrial",
    "MultiGoalCalibrationCampaign",
    "MultiGoalCalibrationExecutionError",
    "parse_multi_goal_calibration_campaign",
]
