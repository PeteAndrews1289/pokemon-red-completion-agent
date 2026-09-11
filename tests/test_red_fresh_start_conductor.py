from __future__ import annotations

from dataclasses import replace

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.player_loop import PlayerStepKind, PlayerStepResult
from pokemon_red_completion.red_fresh_start_conductor import (
    FIRST_BADGE_AUTOMATIC_OBJECTIVE_IDS,
    FIRST_BADGE_SELECTED_STAGE_IDS,
    FIRST_BADGE_VERIFIED_OBJECTIVE_IDS,
    FreshFirstBadgeReport,
)
from pokemon_red_completion.route import COMPLETION_QUEST


def _report() -> FreshFirstBadgeReport:
    facts = frozenset(
        fact
        for objective_id in FIRST_BADGE_VERIFIED_OBJECTIVE_IDS
        for fact in COMPLETION_QUEST.objective(objective_id).completion_facts
    )
    steps = tuple(
        PlayerStepResult(
            kind=PlayerStepKind.SKILL_COMPLETED,
            objective_id=objective_id,
            skill_actions_executed=10,
            skill_frames_executed=100,
        )
        for objective_id in FIRST_BADGE_SELECTED_STAGE_IDS
    )
    return FreshFirstBadgeReport(
        steps=steps,
        terminal_state=GameState(GameMode.OVERWORLD, facts, location="pewter_gym"),
        loop={"actions_executed": 30, "decisions": 3, "objectives_completed": 3},
        observer={"verified_objectives": list(FIRST_BADGE_VERIFIED_OBJECTIVE_IDS)},
        objective_policy={
            "branching_decisions": 0,
            "expected_answer_labels_supplied": 0,
            "fixed_dispatch_decisions": 0,
            "route_dispatch_mode": "model_selected_specialists",
            "selected_decisions": 3,
            "singleton_decisions": 3,
        },
        selected_objective_ids=FIRST_BADGE_SELECTED_STAGE_IDS,
        automatic_objective_ids=FIRST_BADGE_AUTOMATIC_OBJECTIVE_IDS,
        initial_wait_frames=0,
        actions_executed=30,
        frames_executed=300,
        controller_released=True,
    )


def test_first_badge_report_separates_model_dispatch_from_automatic_mechanics() -> None:
    report = _report()

    assert report.passed
    public = report.public_dict()
    assert public["selected_objective_ids"] == [
        "power_on",
        "receive_pokedex",
        "reach_pewter",
    ]
    assert public["automatic_objective_ids"] == [
        "begin_adventure",
        "choose_starter",
        "defeat_brock",
    ]
    assert public["assistance"]["deterministic_mechanics"] is True
    assert "not_objective_ranking_competence" in public["limitations"]


def test_first_badge_report_fails_on_authority_inflation_or_missing_badge() -> None:
    report = _report()

    assert not replace(
        report,
        objective_policy={**report.objective_policy, "branching_decisions": 1},
    ).passed
    assert not replace(
        report,
        automatic_objective_ids=("begin_adventure", "choose_starter"),
    ).passed
    assert not replace(
        report,
        terminal_state=GameState(
            GameMode.OVERWORLD,
            report.terminal_state.facts.difference({"badge:boulder"}),
            location="pewter_gym",
        ),
    ).passed

