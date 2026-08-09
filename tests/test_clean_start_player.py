from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.clean_start_player import (
    CleanStartPlayerError,
    CleanStartPortableReport,
    _exception_chain,
    run_portable_clean_start,
)
from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.player_loop import PlayerRunReport
from pokemon_red_completion.route import COMPLETION_QUEST


def _terminal_run() -> PlayerRunReport:
    facts = frozenset(
        fact for objective in COMPLETION_QUEST for fact in objective.completion_facts
    )
    return PlayerRunReport(
        steps=(),
        terminal_state=GameState(GameMode.HALL_OF_FAME, facts, location="hall_of_fame"),
        graph_complete=True,
        exhausted_step_budget=False,
    )


def _report() -> CleanStartPortableReport:
    return CleanStartPortableReport(
        run=_terminal_run(),
        loop={
            "actions_executed": 638_520,
            "decisions": 21,
            "objectives_completed": 21,
            "replans": 0,
        },
        observer={"latched_fact_count": 36},
        objective_policy={
            "authorized_decisions": 0,
            "expected_answer_labels_supplied": 0,
            "fixed_dispatch_decisions": 0,
            "route_dispatch_mode": "model_selected_specialists",
            "selected_decisions": 21,
            "teacher_fallbacks": 0,
        },
        battle_policy=None,
        training_control=None,
        training_candidate=None,
        initial_wait_frames=17,
        battle_schedule=None,
        automatic_objective_ids=("begin_adventure", "enter_hall_of_fame"),
        selected_objective_ids=("power_on", "defeat_champion"),
        strict_teacher_free_battle_required=False,
        battle_control_authority_required=False,
        battle_switch_target_authority_required=False,
        training_control_authority_required=False,
        training_candidate_authority_required=False,
        controller_released=True,
        frames_executed=45_000_000,
    )


def test_portable_clean_start_report_separates_selected_and_automatic_objectives() -> None:
    report = _report()

    assert report.passed
    public = report.public_dict()
    assert public["status"] == "ok"
    assert public["assistance"] == {
        "expected_route_labels": 0,
        "fixed_objective_dispatches": 0,
        "human_input": False,
        "save_state_loaded": False,
        "teacher_fallbacks": 0,
        "teacher_queries": 0,
    }
    assert public["automatic_objective_ids"] == [
        "begin_adventure",
        "enter_hall_of_fame",
    ]
    assert "early_game_is_one_fourteen_objective_composite" in public["limitations"]


@pytest.mark.parametrize(
    "objective_policy",
    (
        {"route_dispatch_mode": "model_scored_fixed_singleton_dispatches"},
        {
            "route_dispatch_mode": "model_selected_specialists",
            "expected_answer_labels_supplied": 1,
            "fixed_dispatch_decisions": 0,
            "selected_decisions": 21,
        },
        {
            "route_dispatch_mode": "model_selected_specialists",
            "expected_answer_labels_supplied": 0,
            "fixed_dispatch_decisions": 1,
            "selected_decisions": 21,
        },
        {
            "route_dispatch_mode": "model_selected_specialists",
            "expected_answer_labels_supplied": 0,
            "fixed_dispatch_decisions": 0,
            "selected_decisions": 20,
        },
    ),
)
def test_portable_report_fails_closed_on_objective_authority_leak(objective_policy) -> None:
    assert not replace(_report(), objective_policy=objective_policy).passed


def test_portable_report_enforces_requested_battle_and_training_authority() -> None:
    strict = replace(
        _report(),
        strict_teacher_free_battle_required=True,
        battle_policy={
            "decisions": 31,
            "teacher_fallbacks": 0,
            "teacher_queries": 0,
            "teacher_queries_allowed": False,
        },
    )
    assert strict.passed
    assert not replace(
        strict,
        battle_policy={
            "decisions": 31,
            "teacher_fallbacks": 0,
            "teacher_queries": 1,
            "teacher_queries_allowed": False,
        },
    ).passed

    six_role_battle = replace(
        strict,
        battle_control_authority_required=True,
        battle_switch_target_authority_required=True,
        battle_policy={
            "decisions": 31,
            "teacher_fallbacks": 0,
            "teacher_queries": 0,
            "teacher_queries_allowed": False,
            "control_model_execution": {
                "decisions": 31,
                "low_confidence_fallbacks": 0,
                "safety_fallbacks": 0,
            },
            "switch_target_model": {
                "execution": {
                    "decisions": 3,
                    "enabled": True,
                    "fallbacks": {},
                    "rebindings": 3,
                }
            },
        },
    )
    assert six_role_battle.passed
    assert not replace(
        six_role_battle,
        battle_policy={
            **six_role_battle.battle_policy,
            "switch_target_model": {
                "execution": {
                    "decisions": 3,
                    "enabled": True,
                    "fallbacks": {"projection": 1},
                    "rebindings": 2,
                }
            },
        },
    ).passed

    controlled = replace(
        _report(),
        training_control_authority_required=True,
        training_candidate_authority_required=True,
        training_control={
            "controlled_decisions": 100,
            "model_had_execution_authority": True,
            "teacher_fallback_on_model_disagreement": False,
        },
        training_candidate={
            "controlled_decisions": 100,
            "model_had_execution_authority": True,
            "teacher_fallback_on_model_disagreement": False,
        },
    )
    assert controlled.passed
    assert not replace(
        controlled,
        training_candidate={
            "controlled_decisions": 0,
            "model_had_execution_authority": False,
            "teacher_fallback_on_model_disagreement": False,
        },
    ).passed


def test_portable_runner_rejects_incomplete_authority_configuration_before_emulator() -> None:
    with pytest.raises(ValueError, match="initial_wait_frames"):
        run_portable_clean_start("private.gb", objective_model=None, initial_wait_frames=256)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="battle-control execution"):
        run_portable_clean_start(
            "private.gb",
            objective_model=None,  # type: ignore[arg-type]
            execute_battle_control_model=True,
        )
    with pytest.raises(ValueError, match="teacher-free battle"):
        run_portable_clean_start(
            "private.gb",
            objective_model=None,  # type: ignore[arg-type]
            require_teacher_free_battle=True,
        )
    with pytest.raises(ValueError, match="training-control execution"):
        run_portable_clean_start(
            "private.gb",
            objective_model=None,  # type: ignore[arg-type]
            execute_training_control_model=True,
        )
    with pytest.raises(ValueError, match="training-candidate execution"):
        run_portable_clean_start(
            "private.gb",
            objective_model=None,  # type: ignore[arg-type]
            execute_training_candidate_model=True,
        )


def test_clean_start_error_preserves_detached_failure_evidence() -> None:
    original = {"stage": "objective_loop_execution", "frames_executed": 123}

    error = CleanStartPlayerError("failed closed", evidence=original)
    original["frames_executed"] = 999

    assert str(error) == "failed closed"
    assert error.evidence == {
        "stage": "objective_loop_execution",
        "frames_executed": 123,
    }


def test_failure_chain_retains_nested_runtime_causes() -> None:
    root = KeyError("missing battle feature")
    middle = RuntimeError("policy failed")
    middle.__cause__ = root
    outer = CleanStartPlayerError("objective failed")
    outer.__cause__ = middle

    assert _exception_chain(outer) == [
        {"exception_type": "CleanStartPlayerError", "message": "objective failed"},
        {"exception_type": "RuntimeError", "message": "policy failed"},
        {"exception_type": "KeyError", "message": "'missing battle feature'"},
    ]
