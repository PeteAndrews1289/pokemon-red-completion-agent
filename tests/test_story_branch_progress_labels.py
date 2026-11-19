"""Story-branch progress labels: measured, objective-scoped, censored windows stay unknown."""

import math

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_story_branch_value import (
    STORY_BRANCH_TARGET_CONTRACT,
    STORY_BRANCH_TARGET_NAMES,
    StoryBranchStep,
    story_branch_window_targets,
)

S, H = GoalKind.ADVANCE_STORY, GoalKind.RESTORE_TEAM
I = {n: i for i, n in enumerate(STORY_BRANCH_TARGET_NAMES)}


def st(kind=S, obj="fuji", clean=True, won=False, done=(), actions=100, frames=6000, cash=0, quote=None):
    return StoryBranchStep(kind, obj if kind is S else None, clean, won, frozenset(done), actions, frames, cash, quote)


def test_contract_names_extend_the_sequence_channels_with_route_progress():
    assert STORY_BRANCH_TARGET_NAMES[-1] == "route_progress" and len(STORY_BRANCH_TARGET_NAMES) == 8
    assert STORY_BRANCH_TARGET_CONTRACT == "red-story-branch-task-or-horizon-progress-v1"


def test_horizon_window_measures_net_route_progress_and_objective_battles_only():
    steps = [st(won=True), st(kind=H), st(obj="erika", won=True), st(), st(), st(quote=300.0)]
    raw, targets, complete, terminal = story_branch_window_targets(steps, objective_ref="fuji", start_quote=1200.0)
    assert complete and not terminal
    assert raw[I["native_progress"]] == 1  # the Erika win is not credited to Fuji
    assert raw[I["route_progress"]] == pytest.approx(0.75)
    assert targets[I["actions"]] == pytest.approx(500 / 1500) and targets[I["battle_losses"]] is None


def test_leaving_the_route_gives_no_negative_progress():
    steps = [st(), st(), st(), st(), st(quote=2000.0)]
    raw, targets, *_ = story_branch_window_targets(steps, objective_ref="fuji", start_quote=1200.0)
    assert raw[I["route_progress"]] == 0.0 and targets[I["route_progress"]] == 0.0


def test_completion_is_task_terminal_with_full_route_progress():
    steps = [st(won=True), st(won=True, done=("fuji",)), st()]
    raw, targets, complete, terminal = story_branch_window_targets(steps, objective_ref="fuji", start_quote=400.0)
    assert complete and terminal
    assert raw[I["route_progress"]] == 1.0 and raw[I["completed_quests"]] == 1 and raw[I["native_progress"]] == 2
    assert targets[I["completed_quests"]] == pytest.approx(0.5)


def test_censored_windows_are_unknown_not_zero():
    _, targets, complete, _ = story_branch_window_targets([st(), st(clean=False), st()], objective_ref="fuji", start_quote=900.0)
    assert not complete and all(v is None for v in targets)
    _, targets, complete, _ = story_branch_window_targets([st(), st()], objective_ref="fuji", start_quote=900.0)
    assert not complete and all(v is None for v in targets)


def test_unknown_quotes_leave_only_route_progress_unknown():
    steps = [st(), st(), st(), st(), st(quote=None)]
    _, targets, complete, _ = story_branch_window_targets(steps, objective_ref="fuji", start_quote=900.0)
    assert complete and targets[I["route_progress"]] is None and targets[I["actions"]] is not None
    _, targets, *_ = story_branch_window_targets(steps[:4] + [st(quote=10.0)], objective_ref="fuji", start_quote=None)
    assert targets[I["route_progress"]] is None


def test_readiness_branch_vector_is_bounded_and_explicit_about_absence():
    from pokemon_red_completion.player_readiness import CONTEXT_NAMES, BUDGET_NAMES, PlayerReadiness
    from pokemon_red_completion.red_story_branch_value import (READINESS_BRANCH_WIDTH, STORY_BRANCH_FEATURE_NAMES,
                                                             readiness_branch_vector)
    assert readiness_branch_vector(None, combat_required=1.0) == (0.0,) * READINESS_BRANCH_WIDTH
    values = {n: 0.0 for n in CONTEXT_NAMES}
    values.update({"current.hp_fraction": 0.4, "current.fainted_fraction": 1 / 6, "current.pp_known": 1.0, "current.pp_fraction": 0.7})
    r = PlayerReadiness(tuple(values[n] for n in CONTEXT_NAMES) + (0.5,) * len(BUDGET_NAMES), history_observed=False)
    v = readiness_branch_vector(r, combat_required=1.0)
    assert len(v) == READINESS_BRANCH_WIDTH and v[0] == 1.0 and v[1] == 0.0 and v[4] == 0.4 and v[-2] == 0.4
    assert readiness_branch_vector(r, combat_required=0.0)[-2:] == (0.0, 0.0)
    assert STORY_BRANCH_FEATURE_NAMES[-READINESS_BRANCH_WIDTH] == "readiness.observed" and len(STORY_BRANCH_FEATURE_NAMES) == 36
    with pytest.raises(TypeError):
        readiness_branch_vector(object(), combat_required=0.0)


def test_declarations_are_validated():
    with pytest.raises(ValueError):
        story_branch_window_targets([], objective_ref="", start_quote=1.0)
    with pytest.raises(ValueError):
        story_branch_window_targets([], objective_ref="fuji", start_quote=math.inf)
    with pytest.raises(TypeError):
        story_branch_window_targets([object()], objective_ref="fuji", start_quote=1.0)
