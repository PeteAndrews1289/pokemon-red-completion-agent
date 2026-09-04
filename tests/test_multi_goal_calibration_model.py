from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from pokemon_red_completion.goal_manager_model import (
    GOAL_MANAGER_FEATURE_NAMES,
    GoalManagerLinearModel,
    canonical_goal_manager_model_sha256,
)
from pokemon_red_completion.goal_manager_outcome_learning import (
    OUTCOME_UPDATE_MENU_KL_CAP,
    outcome_update_configuration,
)
from pokemon_red_completion.multi_goal_calibration_model import (
    MultiGoalCalibrationModelError,
    load_multi_goal_calibration_model,
)


def _line(value: object) -> bytes:
    return (
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("ascii")
        + b"\n"
    )


def _bundle(root: Path) -> tuple[Path, Path, str, str]:
    width = len(GOAL_MANAGER_FEATURE_NAMES)
    model = GoalManagerLinearModel(
        weights=np.full(width, 0.01),
        feature_mean=np.zeros(width),
        feature_scale=np.ones(width),
        l2=0.02,
        training_epochs=1,
    )
    model_payload = _line(model.to_dict())
    model_sha = hashlib.sha256(model_payload).hexdigest()
    metrics_before = {
        "schema": "pokemon.core.goal-manager-outcome-fit-metrics.v1",
        "examples": 7,
        "positive_examples": 4,
        "negative_examples": 3,
        "weighted_binary_cross_entropy": 0.7,
        "mean_selected_probability": 0.5,
        "selected_probabilities": [0.5] * 7,
    }
    metrics_after = {
        **metrics_before,
        "weighted_binary_cross_entropy": 0.69,
        "mean_selected_probability": 0.51,
    }
    update = {
        "schema": "pokemon.core.goal-manager-outcome-update.v1",
        "objective_id": "pokemon.core.goal-manager.capped-ips-policy-gradient.v1",
        "step_size": 0.02,
        "maximum_importance_weight": 4.0,
        "menu_kl_cap": OUTCOME_UPDATE_MENU_KL_CAP,
        "update_steps": 1,
        "before": metrics_before,
        "after": metrics_after,
        "maximum_weight_delta": 0.001,
        "weight_delta_l2": 0.01,
        "weight_delta_l2_cap": 0.02,
    }
    train_set = {
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
    }
    summary = {
        "schema": "pokemon.red.multi-goal-calibration-fit-summary.v1",
        "status": "train_only_calibration_fit_complete",
        "source_commit": "1" * 40,
        "source_bundle_sha256": "2" * 64,
        "fit_runner_sha256": "3" * 64,
        "trial_runner_sha256": "4" * 64,
        "campaign_plan_sha256": "5" * 64,
        "campaign_roster_sha256": "6" * 64,
        "base_model_canonical_sha256": "7" * 64,
        "candidate_model_canonical_sha256": canonical_goal_manager_model_sha256(model),
        "candidate_model_file_sha256": model_sha,
        "configuration": outcome_update_configuration(),
        "fit": {
            "schema": "pokemon.red.multi-goal-calibration-fit.v1",
            "train_set": train_set,
            "update": update,
            "maximum_guard_menu_kl": 0.001,
            "guard_menu_kl_cap": OUTCOME_UPDATE_MENU_KL_CAP,
        },
        "guard_roster_sha256": "8" * 64,
        "same_bank_calibration_only": True,
        "promotion_authorized": False,
        "authority_delta": 0,
        "crystal_accesses": 0,
        "teacher_queries": 0,
        "private_path_fields": 0,
    }
    summary_payload = _line(summary)
    summary_sha = hashlib.sha256(summary_payload).hexdigest()
    model_path = root / "model.json"
    summary_path = root / "summary.json"
    model_path.write_bytes(model_payload)
    summary_path.write_bytes(summary_payload)
    return model_path, summary_path, model_sha, summary_sha


def test_loads_exact_shadow_only_calibration_bundle(tmp_path: Path) -> None:
    model_path, summary_path, model_sha, summary_sha = _bundle(tmp_path)

    loaded = load_multi_goal_calibration_model(
        model_path,
        summary_path,
        expected_model_file_sha256=model_sha,
        expected_summary_file_sha256=summary_sha,
    )

    assert loaded.public_dict() == {
        "authority": "shadow_calibration_only",
        "campaign_plan_sha256": "5" * 64,
        "campaign_roster_sha256": "6" * 64,
        "candidate_model_canonical_sha256": canonical_goal_manager_model_sha256(
            loaded.model
        ),
        "candidate_model_file_sha256": model_sha,
        "guard_roster_sha256": "8" * 64,
        "private_path_fields": 0,
        "source_bundle_sha256": "2" * 64,
        "source_commit": "1" * 40,
        "summary_file_sha256": summary_sha,
        "targets": 7,
        "roots": 4,
        "teacher_queries": 0,
    }


@pytest.mark.parametrize(
    ("path_kind", "mutation"),
    (
        ("summary", lambda value: {**value, "promotion_authorized": True}),
        ("summary", lambda value: {**value, "crystal_accesses": 1}),
        (
            "summary",
            lambda value: {
                **value,
                "fit": {
                    **value["fit"],
                    "train_set": {**value["fit"]["train_set"], "targets": 6},
                },
            },
        ),
        (
            "summary",
            lambda value: {
                **value,
                "fit": {
                    **value["fit"],
                    "update": {
                        **value["fit"]["update"],
                        "after": {
                            **value["fit"]["update"]["after"],
                            "weighted_binary_cross_entropy": 0.8,
                        },
                    },
                },
            },
        ),
        ("model", lambda value: {**value, "weights": [0.0] * len(value["weights"])}),
    ),
)
def test_rejects_rehashed_scope_denominator_loss_or_model_mutation(
    tmp_path: Path,
    path_kind: str,
    mutation: object,
) -> None:
    model_path, summary_path, model_sha, summary_sha = _bundle(tmp_path)
    target = summary_path if path_kind == "summary" else model_path
    value = json.loads(target.read_bytes())
    target.write_bytes(_line(mutation(value)))  # type: ignore[operator]
    changed_model_sha = hashlib.sha256(model_path.read_bytes()).hexdigest()
    changed_summary_sha = hashlib.sha256(summary_path.read_bytes()).hexdigest()

    with pytest.raises(MultiGoalCalibrationModelError):
        load_multi_goal_calibration_model(
            model_path,
            summary_path,
            expected_model_file_sha256=(
                changed_model_sha if path_kind == "model" else model_sha
            ),
            expected_summary_file_sha256=(
                changed_summary_sha if path_kind == "summary" else summary_sha
            ),
        )


def test_rejects_noncanonical_or_symlinked_input(tmp_path: Path) -> None:
    model_path, summary_path, model_sha, summary_sha = _bundle(tmp_path)
    summary_path.write_bytes(summary_path.read_bytes().replace(b",", b", ", 1))
    changed_summary_sha = hashlib.sha256(summary_path.read_bytes()).hexdigest()
    with pytest.raises(MultiGoalCalibrationModelError, match="noncanonical"):
        load_multi_goal_calibration_model(
            model_path,
            summary_path,
            expected_model_file_sha256=model_sha,
            expected_summary_file_sha256=changed_summary_sha,
        )

    summary_path.unlink()
    summary_path.symlink_to(model_path)
    with pytest.raises(MultiGoalCalibrationModelError, match="unreadable"):
        load_multi_goal_calibration_model(
            model_path,
            summary_path,
            expected_model_file_sha256=model_sha,
            expected_summary_file_sha256=summary_sha,
        )
