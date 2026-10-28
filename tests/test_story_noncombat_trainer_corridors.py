"""A whole noncombat quote must not cross a known future trainer corridor."""

from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_fly as projection
from pokemon_red_completion import red_player_story_travel as story
from pokemon_red_completion.gen1_trainer_sight import TrainerFacing, TrainerSightZone
from pokemon_red_completion.global_router import MacroEdge, MacroGraph
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.local_router import LocalGraph
from pokemon_red_completion.red_training_ground_route import RedVermilionGroundTransition
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


def fixture(monkeypatch, *, defeated=False, detour=False):
    from test_red_player_story_travel import setup
    from test_route_plan import line

    runtime, actions, _, raw, lesson = setup(monkeypatch)
    # Complete the real Fly eligibility probe's field observation. With no
    # Thunder badge this fixture still exercises only the quoted ground route.
    raw.game_started = True
    raw.battle_state = 0
    raw.player_y = raw.player_x = 0
    runtime.emulator.pressed_buttons = frozenset()
    runtime.reader.read_input_readiness = lambda: N(ready=True)
    runtime.reader.read_bottom_dialogue_box_visible = lambda: False
    raw.event_flags = b"observed-native-flags"
    objective = N(id="defeat_giovanni", completion_facts=frozenset({"badge:earth"}))
    runtime.adapter.graph.objective = lambda _: objective
    runtime.adapter.graph.available_objectives = lambda _: (objective,)
    snap = TraversalSnapshot(41, (0, 0), True, mode="land")
    monkeypatch.setattr(story, "Gen1TraversalObserver", lambda *a, **k: N(observe=lambda: snap))
    middle = line((0, 0), (0, 1), (0, 2))
    if detour:
        around = line((0, 0), (1, 0), (2, 0), (2, 1), (2, 2), (1, 2), (0, 2))
        edges = dict(middle.edges)
        for at, onward in around.edges.items():
            edges[at] = edges.get(at, ()) + onward
        middle = LocalGraph(edges)
    world = StrategicScenarioRouteWorld(
        macro_graph=MacroGraph({
            41: (MacroEdge(2, kind="warp", at=(0, 1), arrival_at=(0, 0)),),
            2: (MacroEdge(45, kind="warp", at=(0, 2), arrival_at=(0, 0)),),
            45: (),
        }),
        local_graphs={41: line((0, 0), (0, 1)), 2: middle, 45: line((0, 0))},
        rom=b"fixture", terrain={41: None, 2: None, 45: None},
        rules=N(cut_block_swaps=()), tilesets={}, water_tilesets=frozenset(),
        object_blockers={41: frozenset(), 2: frozenset({(1, 1)}), 45: frozenset()},
    )
    zone = TrainerSightZone(2, 1, 1, 1, (1, 1), TrainerFacing.UP, 1, 9, defeated, False)
    monkeypatch.setattr(projection, "_fly_trainer_tables", lambda *a: ((), ()))
    monkeypatch.setattr(projection, "static_trainer_sight_zones", lambda *a: (zone,))
    certificates = []
    monkeypatch.setattr(story, "certified_cash_safe_transition",
                        lambda route, raw, plan: certificates.append(route.route_world) or None)
    return runtime, actions, RedVermilionGroundTransition(b"fixture", world), raw, lesson, snap, certificates


@pytest.mark.parametrize("defeated,border,available", [
    (False, False, False),
    (True, False, True),
    (False, True, True),
])
def test_complete_quote_respects_future_battle_but_first_border_remains_available(
    monkeypatch, defeated, border, available,
):
    runtime, actions, route, raw, lesson, snap, certificates = fixture(
        monkeypatch, defeated=defeated,
    )
    # Geometry alone has a complete route. The future trainer changes legality.
    assert route.route_world.plan_feasible_to_map(snap, 45).terminal_map == 45
    binding = story.story_travel_binding(
        runtime, actions, objective_id="defeat_giovanni", route=route,
        stop_at_map_boundary=border,
    )
    assert (binding is not None) is available
    assert actions.actions_executed == runtime.emulator.frame_count == 0
    assert raw.badge_bits == 0 and lesson["completed_objectives"] == ["receive_pokedex"]
    assert (0, 1) in route.route_world.local_graphs[2].edges
    assert route.route_world.object_blockers[2] == frozenset({(1, 1)})
    if binding is not None:
        assert binding.story_approach_only
    if border:
        assert certificates == [route.route_world]


def test_selected_detour_keeps_same_future_lane_guard_in_execution(monkeypatch):
    runtime, actions, route, raw, lesson, snap, certificates = fixture(monkeypatch, detour=True)
    executed = []

    def execute(selected, _actions, _reader, _emulator):
        plan = selected.route_world.plan_feasible_to_map(snap, selected.destination_map)
        assert all((0, 1) not in segment.approach.coordinates
                   for segment in plan.segments if segment.source_map == 2)
        assert (0, 1) in selected.route_world.object_blockers[2]
        executed.append(selected.route_world)
        raw.map_id = selected.destination_map
        actions.actions_executed += 1
        runtime.emulator.frame_count += 16

    monkeypatch.setattr(RedVermilionGroundTransition, "__call__", execute)
    binding = story.story_travel_binding(
        runtime, actions, objective_id="defeat_giovanni", route=route,
    )
    assert binding is not None and actions.actions_executed == 0
    report = binding.execute()
    assert executed == certificates and executed[0] is not route.route_world
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert not report.evidence["objective_completed"] and report.evidence["trainer_battles"] == 0
    assert raw.badge_bits == 0 and "defeat_giovanni" not in lesson["completed_objectives"]
