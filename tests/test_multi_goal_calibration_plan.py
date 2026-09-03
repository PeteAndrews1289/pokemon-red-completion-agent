from __future__ import annotations

import hashlib

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.multi_goal_calibration_plan import (
    CalibrationRootCandidate,
    MultiGoalCalibrationPlanError,
    build_multi_goal_calibration_schedule,
)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _root(
    slot: str,
    focus: GoalKind,
    menu: tuple[GoalKind, ...],
    *,
    available: bool = True,
    physical: str | None = None,
) -> CalibrationRootCandidate:
    return CalibrationRootCandidate(
        slot_id=slot,
        focus_kind=focus,
        state_sha256=_sha(f"{slot}:state"),
        envelope_sha256=_sha(f"{slot}:envelope"),
        profile_sha256=_sha(f"{slot}:profile"),
        physical_root_sha256=_sha(physical or f"{slot}:root"),
        available_goal_kinds=menu,
        claim_available=available,
    )


def _bank() -> tuple[CalibrationRootCandidate, ...]:
    return (
        _root(
            "develop-claimed",
            GoalKind.DEVELOP_TEAM,
            (GoalKind.DEVELOP_TEAM, GoalKind.ADVANCE_STORY),
            available=False,
        ),
        _root(
            "develop-open",
            GoalKind.DEVELOP_TEAM,
            (
                GoalKind.RESTORE_TEAM,
                GoalKind.DEVELOP_TEAM,
                GoalKind.ADVANCE_STORY,
            ),
        ),
        _root(
            "evolve-open",
            GoalKind.EVOLVE_SPECIES,
            (GoalKind.EVOLVE_SPECIES, GoalKind.EXPLORE),
        ),
        _root(
            "storage-open-a",
            GoalKind.MANAGE_STORAGE,
            (GoalKind.MANAGE_STORAGE, GoalKind.ACQUIRE_SPECIES),
        ),
        _root(
            "storage-open-b",
            GoalKind.MANAGE_STORAGE,
            (
                GoalKind.RECOVER_CONTROL,
                GoalKind.MANAGE_STORAGE,
                GoalKind.DEVELOP_TEAM,
            ),
        ),
    )


def test_schedule_uses_open_quotas_and_every_model_controlled_option() -> None:
    schedule = build_multi_goal_calibration_schedule(_bank())

    assert [root.slot_id for root in schedule.roots] == [
        "develop-open",
        "evolve-open",
        "storage-open-a",
        "storage-open-b",
    ]
    assert [trial.selected_goal_kind for trial in schedule.trials] == [
        GoalKind.DEVELOP_TEAM,
        GoalKind.ADVANCE_STORY,
        GoalKind.EVOLVE_SPECIES,
        GoalKind.EXPLORE,
        GoalKind.MANAGE_STORAGE,
        GoalKind.ACQUIRE_SPECIES,
        GoalKind.MANAGE_STORAGE,
        GoalKind.DEVELOP_TEAM,
    ]
    assert [trial.selected_candidate_index for trial in schedule.trials] == [
        1,
        2,
        0,
        1,
        0,
        1,
        1,
        2,
    ]
    assert schedule.public_dict() == {
        "candidate_rule": "every-model-controlled-option-from-identical-reset",
        "controller_actions": 0,
        "development_labels_opened": 0,
        "emulator_frames": 0,
        "held_out_claim": False,
        "maximum_decisions_per_trial": 1,
        "model_predictions": 0,
        "outcomes_opened": 0,
        "partition": "train",
        "private_path_fields": 0,
        "root_count": 4,
        "root_family_counts": {
            "develop_team": 1,
            "evolve_species": 1,
            "manage_storage": 2,
        },
        "schedule_sha256": schedule.schedule_sha256,
        "schema": "pokemon.red.multi-goal-calibration-plan.v1",
        "selection_rule": (
            "first-eligible-open-train-root-in-authenticated-source-order"
        ),
        "status": "compact_train_calibration_schedule_ready",
        "teacher_queries": 0,
        "transfer_claim": False,
        "trial_count": 8,
        "trial_goal_counts": {
            "acquire_species": 1,
            "advance_story": 1,
            "develop_team": 2,
            "evolve_species": 1,
            "explore": 1,
            "manage_storage": 2,
        },
    }


def test_schedule_is_deterministic_and_does_not_encode_claimed_root() -> None:
    first = build_multi_goal_calibration_schedule(_bank())
    second = build_multi_goal_calibration_schedule(_bank())

    assert first == second
    assert first.schedule_sha256 == second.schedule_sha256
    assert "develop-claimed" not in str(first.private_dict())


def test_schedule_rejects_a_root_without_two_learnable_options() -> None:
    bank = tuple(
        replace
        for replace in _bank()
        if replace.slot_id != "evolve-open"
    ) + (
        _root(
            "evolve-safety-only",
            GoalKind.EVOLVE_SPECIES,
            (GoalKind.EVOLVE_SPECIES, GoalKind.RESTORE_TEAM),
        ),
    )

    with pytest.raises(
        MultiGoalCalibrationPlanError,
        match="insufficient open evolve_species calibration roots",
    ):
        build_multi_goal_calibration_schedule(bank)


def test_schedule_does_not_count_one_physical_root_twice() -> None:
    bank = _bank()[:-1] + (
        _root(
            "storage-duplicate-root",
            GoalKind.MANAGE_STORAGE,
            (GoalKind.MANAGE_STORAGE, GoalKind.DEVELOP_TEAM),
            physical="storage-open-a:root",
        ),
    )

    with pytest.raises(
        MultiGoalCalibrationPlanError,
        match="insufficient open manage_storage calibration roots",
    ):
        build_multi_goal_calibration_schedule(bank)


def test_candidate_rejects_duplicate_goal_kinds() -> None:
    with pytest.raises(MultiGoalCalibrationPlanError, match="menu is invalid"):
        _root(
            "duplicate-menu",
            GoalKind.DEVELOP_TEAM,
            (GoalKind.DEVELOP_TEAM, GoalKind.DEVELOP_TEAM),
        )

