"""Strict loader for the non-authoritative Red calibration model bundle."""

from __future__ import annotations

import hashlib
import json
import math
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.goal_manager_model import (
    GoalManagerLinearModel,
    canonical_goal_manager_model_sha256,
)
from pokemon_red_completion.goal_manager_outcome_learning import (
    OUTCOME_UPDATE_MENU_KL_CAP,
    outcome_update_configuration,
)

CALIBRATION_FIT_SUMMARY_SCHEMA = "pokemon.red.multi-goal-calibration-fit-summary.v1"
CALIBRATION_FIT_STATUS = "train_only_calibration_fit_complete"
_MAX_BYTES = 4 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SUMMARY_FIELDS = {
    "base_model_canonical_sha256",
    "campaign_plan_sha256",
    "campaign_roster_sha256",
    "candidate_model_canonical_sha256",
    "candidate_model_file_sha256",
    "configuration",
    "crystal_accesses",
    "fit",
    "fit_runner_sha256",
    "guard_roster_sha256",
    "private_path_fields",
    "promotion_authorized",
    "same_bank_calibration_only",
    "schema",
    "source_bundle_sha256",
    "source_commit",
    "status",
    "teacher_queries",
    "trial_runner_sha256",
    "authority_delta",
}


class MultiGoalCalibrationModelError(ValueError):
    """A fitted calibration bundle failed schema or identity validation."""


@dataclass(frozen=True, slots=True)
class MultiGoalCalibrationModel:
    """Authenticated shadow-only model plus its public provenance."""

    model: GoalManagerLinearModel
    model_file_sha256: str
    summary_file_sha256: str
    source_commit: str
    source_bundle_sha256: str
    campaign_plan_sha256: str
    campaign_roster_sha256: str
    guard_roster_sha256: str

    def public_dict(self) -> dict[str, object]:
        return {
            "authority": "shadow_calibration_only",
            "campaign_plan_sha256": self.campaign_plan_sha256,
            "campaign_roster_sha256": self.campaign_roster_sha256,
            "candidate_model_canonical_sha256": (
                canonical_goal_manager_model_sha256(self.model)
            ),
            "candidate_model_file_sha256": self.model_file_sha256,
            "guard_roster_sha256": self.guard_roster_sha256,
            "private_path_fields": 0,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_commit": self.source_commit,
            "summary_file_sha256": self.summary_file_sha256,
            "targets": 7,
            "roots": 4,
            "teacher_queries": 0,
        }


def load_multi_goal_calibration_model(
    model_path: Path,
    summary_path: Path,
    *,
    expected_model_file_sha256: str,
    expected_summary_file_sha256: str,
) -> MultiGoalCalibrationModel:
    """Load one exact model/summary pair and retain no private path."""

    if not isinstance(model_path, Path) or not isinstance(summary_path, Path):
        raise TypeError("calibration model paths must be Path values")
    expected_model = _digest(expected_model_file_sha256, "expected model")
    expected_summary = _digest(expected_summary_file_sha256, "expected summary")
    model_payload = _read_regular(model_path, "model")
    summary_payload = _read_regular(summary_path, "summary")
    if (
        hashlib.sha256(model_payload).hexdigest() != expected_model
        or hashlib.sha256(summary_payload).hexdigest() != expected_summary
    ):
        raise MultiGoalCalibrationModelError("calibration bundle file identity differs")

    model_document = _canonical_document(model_payload, "model")
    summary = _canonical_document(summary_payload, "summary")
    if set(summary) != _SUMMARY_FIELDS:
        raise MultiGoalCalibrationModelError("calibration fit summary fields differ")
    if (
        summary.get("schema") != CALIBRATION_FIT_SUMMARY_SCHEMA
        or summary.get("status") != CALIBRATION_FIT_STATUS
        or summary.get("same_bank_calibration_only") is not True
        or summary.get("promotion_authorized") is not False
        or summary.get("authority_delta") != 0
        or summary.get("crystal_accesses") != 0
        or summary.get("teacher_queries") != 0
        or summary.get("private_path_fields") != 0
        or summary.get("configuration") != outcome_update_configuration()
    ):
        raise MultiGoalCalibrationModelError("calibration fit scope differs")

    for field in (
        "base_model_canonical_sha256",
        "campaign_plan_sha256",
        "campaign_roster_sha256",
        "candidate_model_canonical_sha256",
        "candidate_model_file_sha256",
        "fit_runner_sha256",
        "guard_roster_sha256",
        "source_bundle_sha256",
        "trial_runner_sha256",
    ):
        _digest(summary.get(field), field)
    source_commit = summary.get("source_commit")
    if not isinstance(source_commit, str) or _GIT_COMMIT.fullmatch(source_commit) is None:
        raise MultiGoalCalibrationModelError("calibration source commit differs")
    if summary["candidate_model_file_sha256"] != expected_model:
        raise MultiGoalCalibrationModelError("calibration model file join differs")

    try:
        model = GoalManagerLinearModel.from_dict(model_document)
    except (TypeError, ValueError) as error:
        raise MultiGoalCalibrationModelError("calibration model document differs") from error
    if canonical_goal_manager_model_sha256(model) != summary["candidate_model_canonical_sha256"]:
        raise MultiGoalCalibrationModelError("calibration model identity join differs")
    _validate_fit(summary.get("fit"))
    return MultiGoalCalibrationModel(
        model=model,
        model_file_sha256=expected_model,
        summary_file_sha256=expected_summary,
        source_commit=source_commit,
        source_bundle_sha256=str(summary["source_bundle_sha256"]),
        campaign_plan_sha256=str(summary["campaign_plan_sha256"]),
        campaign_roster_sha256=str(summary["campaign_roster_sha256"]),
        guard_roster_sha256=str(summary["guard_roster_sha256"]),
    )


def _validate_fit(value: object) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "guard_menu_kl_cap",
        "maximum_guard_menu_kl",
        "schema",
        "train_set",
        "update",
    }:
        raise MultiGoalCalibrationModelError("calibration fit record differs")
    train_set = value.get("train_set")
    if not isinstance(train_set, Mapping) or train_set != {
        "schema": "pokemon.red.multi-goal-calibration-train-set.v1",
        "targets": 7,
        "roots": 4,
        "positive_targets": 4,
        "negative_targets": 3,
        "selected_goal_kind_counts": {
            "advance_story": 2,
            "develop_team": 2,
            "evolve_species": 1,
            "manage_storage": 2,
        },
        "unique_episode_manifests": 7,
        "teacher_queries": 0,
        "private_path_fields": 0,
    }:
        raise MultiGoalCalibrationModelError("calibration train denominator differs")
    maximum_kl = value.get("maximum_guard_menu_kl")
    if (
        value.get("schema") != "pokemon.red.multi-goal-calibration-fit.v1"
        or value.get("guard_menu_kl_cap") != OUTCOME_UPDATE_MENU_KL_CAP
        or isinstance(maximum_kl, bool)
        or not isinstance(maximum_kl, (int, float))
        or not math.isfinite(float(maximum_kl))
        or not 0.0 <= float(maximum_kl) <= OUTCOME_UPDATE_MENU_KL_CAP
    ):
        raise MultiGoalCalibrationModelError("calibration guard result differs")
    update = value.get("update")
    if not isinstance(update, Mapping):
        raise MultiGoalCalibrationModelError("calibration update record differs")
    before = update.get("before")
    after = update.get("after")
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        raise MultiGoalCalibrationModelError("calibration update metrics differ")
    before_loss = before.get("weighted_binary_cross_entropy")
    after_loss = after.get("weighted_binary_cross_entropy")
    if (
        update.get("schema") != "pokemon.core.goal-manager-outcome-update.v1"
        or update.get("update_steps") != 1
        or before.get("examples") != 7
        or after.get("examples") != 7
        or before.get("positive_examples") != 4
        or after.get("positive_examples") != 4
        or before.get("negative_examples") != 3
        or after.get("negative_examples") != 3
        or isinstance(before_loss, bool)
        or isinstance(after_loss, bool)
        or not isinstance(before_loss, (int, float))
        or not isinstance(after_loss, (int, float))
        or not math.isfinite(float(before_loss))
        or not math.isfinite(float(after_loss))
        or not float(after_loss) < float(before_loss)
    ):
        raise MultiGoalCalibrationModelError("calibration update metrics differ")


def _read_regular(path: Path, subject: str) -> bytes:
    try:
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MAX_BYTES:
            raise OSError
        return path.read_bytes()
    except OSError:
        raise MultiGoalCalibrationModelError(f"calibration {subject} is unreadable") from None


def _canonical_document(payload: bytes, subject: str) -> Mapping[str, object]:
    if not payload or len(payload) > _MAX_BYTES:
        raise MultiGoalCalibrationModelError(f"calibration {subject} is unreadable")
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MultiGoalCalibrationModelError(
            f"calibration {subject} is unreadable"
        ) from error
    if not isinstance(value, Mapping) or _canonical_line(value) != payload:
        raise MultiGoalCalibrationModelError(f"calibration {subject} is noncanonical")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise MultiGoalCalibrationModelError("calibration document has duplicate fields")
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise MultiGoalCalibrationModelError("calibration document has non-finite numbers")


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


def _digest(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise MultiGoalCalibrationModelError(f"calibration {subject} identity differs")
    return value


__all__ = [
    "CALIBRATION_FIT_STATUS",
    "CALIBRATION_FIT_SUMMARY_SCHEMA",
    "MultiGoalCalibrationModel",
    "MultiGoalCalibrationModelError",
    "load_multi_goal_calibration_model",
]
