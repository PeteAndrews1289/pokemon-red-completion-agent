"""Exact step-search oracle comparisons for compressed Strength planning."""
import random

import pytest

from pokemon_red_completion.gen1_strength import (
    StrengthBoulder,
    StrengthGoal,
    StrengthPlanningError,
    StrengthState,
    _neighbors,
    plan_strength,
)
from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.gen1_traversal import TraversalRules, local_graph
from pokemon_red_completion.observation import Badge, RawGameState


def fixture(picture, player, boulders):
    terrain = Terrain(7, 1,
        tuple(tuple(c != '#' for c in row) for row in picture),
        tuple(tuple(False for _ in row) for row in picture),
        tuple(tuple(False for _ in row) for row in picture),
        tuple(tuple(1 for _ in row) for row in picture))
    rules = TraversalRules((), (), (), (), ())
    initial = StrengthState(
        player, tuple(StrengthBoulder(i + 1, at) for i, at in enumerate(boulders))
    )
    raw = RawGameState(True, 7, player[1], player[0], 1, 0,
                       badge_bits=int(Badge.RAINBOW), party_hp=(10,), party_moves=((70,),))
    return terrain, rules, initial, raw


def compare(args, goal, **kwargs):
    terrain, rules, initial, raw = args
    try:
        reference = plan_strength(terrain, rules, initial, goal, raw, **kwargs)
    except StrengthPlanningError as error:
        assert 'no legal' in str(error)
        with pytest.raises(StrengthPlanningError, match='no legal'):
            plan_strength(terrain, rules, initial, goal, raw, push_macros=True, **kwargs)
        return None
    result = plan_strength(terrain, rules, initial, goal, raw, push_macros=True, **kwargs)
    assert result.cost == reference.cost
    assert result.states[0] == initial and goal.satisfied_by(result.states[-1])
    graph = local_graph(terrain, rules, blocked=frozenset(kwargs.get('blocked', ())))
    for before, step, after in zip(
        result.states[:-1], result.steps, result.states[1:], strict=True
    ):
        assert step.source == before and step.result == after
        assert step in _neighbors(terrain, graph, before, goal)
        if before.player_at != after.player_at:
            assert after.player_at not in kwargs.get('forbidden_player_coordinates', ())
        assert not any((at, step.direction.value) in kwargs.get('forbidden_player_edges', ())
                       for at in (before.player_at, after.player_at))
    return result


@pytest.mark.parametrize('seed', range(32))
def test_changed_layouts_match_exact_minimum_cost(seed):
    rng = random.Random(seed)
    cells = [(y, x) for y in range(3) for x in range(4)]
    player, first, second, blocked, target = rng.sample(cells, 5)
    args = fixture(('....', '....', '....'), player, (first, second))
    goal = StrengthGoal(target, 1 if seed % 2 else None,
                        player_at=cells[seed % len(cells)] if seed % 3 == 0 else None,
                        remove_boulder=seed % 2 == 1 and seed % 5 == 0)
    compare(args, goal, blocked={blocked} if seed % 4 == 0 else (),
            forbidden_player_coordinates={player} if seed % 4 == 1 else (),
            forbidden_player_edges={((1, 1), 'right')} if seed % 4 == 2 else ())


def test_pure_walk_terminal_is_not_lost_when_boulder_already_at_goal():
    args = fixture(('.....', '.....', '.....'), (1, 1), ((1, 2),))
    result = compare(args, StrengthGoal((1, 2), player_at=(0, 4)))
    assert result and all(step.kind == 'walk' for step in result.steps)


def test_drop_keeps_original_one_step_cost_and_stationary_player():
    args = fixture(('.....',), (0, 0), ((0, 1),))
    result = compare(args, StrengthGoal((0, 2), 1, remove_boulder=True))
    assert result and result.cost == 1
    assert result.states[-1] == StrengthState((0, 0), ())


def test_arrival_warp_departure_and_directional_hole_guards():
    args = fixture(('.....', '.....', '.....'), (1, 1), ((1, 2),))
    compare(args, StrengthGoal((1, 0)), forbidden_player_coordinates={(1, 1)})
    compare(args, StrengthGoal((1, 4)), forbidden_player_edges={((1, 3), 'right')})


def test_macro_limit_remains_a_hard_failure():
    terrain, rules, initial, raw = fixture(('.....',), (0, 0), ((0, 2),))
    with pytest.raises(StrengthPlanningError, match='1-state bound'):
        plan_strength(terrain, rules, initial, StrengthGoal((0, 4)), raw,
                      push_macros=True, max_states=1)


def test_flag_does_not_accept_nonboolean_values():
    terrain, rules, initial, raw = fixture(('.....',), (0, 0), ((0, 2),))
    with pytest.raises(ValueError, match='boolean'):
        plan_strength(terrain, rules, initial, StrengthGoal((0, 4)), raw, push_macros=1)
