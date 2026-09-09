"""Trainer skills must plan from cartridge-derived, not raw, warp arrivals."""
from dataclasses import dataclass, replace

import pytest
import test_red_trainer_story as story_tests

import pokemon_red_completion.gen1_scripted_arrival as arrival
import pokemon_red_completion.red_trainer_story as story
from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.global_router import MacroEdge, MacroGraph
from pokemon_red_completion.observation import CurrentMapBlocks, MapId

fixture = story_tests.fixture


@pytest.mark.parametrize("objective,start_map,target_map,prerequisite,event", [
    ("defeat_lorelei", 174, 245, "story:victory_road_cleared", 2273),
    ("defeat_bruno", 245, 246, "league:lorelei_defeated", 2281),
    ("defeat_agatha", 246, 247, "league:bruno_defeated", 2289),
])
@pytest.mark.parametrize("fault", [None, "decoder", "missing_warps", "wrong_warp"])
def test_each_cross_room_story_uses_qualified_arrival_or_refuses_before_input(
    fixture, monkeypatch, objective, start_map, target_map, prerequisite, event, fault,
):
    old, reader, inputs, observe, zone = fixture
    reader.raw = replace(reader.raw, map_id=start_map)
    raw_events = reader.raw.event_flags
    original_graph = MacroGraph(
        {start_map: (MacroEdge(target_map, "warp", (0, 4), (11, 4),
                              destination_warp_index=0),)},
        warp_locations={target_map: ((11, 4), (11, 5), (0, 4))},
        warp_arrivals=None if fault == "missing_warps" else {
            target_map: ((10, 4) if fault == "wrong_warp" else (11, 4), (11, 5), (0, 4)),
        },
    )
    planned_graphs = []
    old_plan = old.world.plan_feasible_to_map

    @dataclass
    class World:
        rom: bytes
        macro_graph: MacroGraph

        def with_current_blocks(self, blocks):
            assert blocks.map_id == start_map
            return self

        def plan_feasible_to_map(self, start, map_id, *, goal_at):
            assert type(map_id) is int and map_id == target_map
            # Real graph transform must be visible to the actual planning call.
            assert self.macro_graph.warp_arrivals[target_map] == ((5, 4), (5, 5), (0, 4))
            assert self.macro_graph.edges is original_graph.edges
            assert self.macro_graph.warp_locations is original_graph.warp_locations
            planned_graphs.append(self.macro_graph)
            return old_plan(start, 245, goal_at=goal_at)

    world = World(b"qualified-fixture", original_graph)
    calls = []

    def qualify(rom, map_id, events):
        assert rom == world.rom
        assert type(map_id) is int and map_id == target_map
        assert events is raw_events
        calls.append(map_id)
        if fault == "decoder":
            raise CartridgeReadError("unsupported or consumed entry")
        return arrival.ScriptedTrainerArrival(map_id, ((11, 4), (11, 5)), (-1, 0), 6, 2)

    monkeypatch.setattr(arrival, "trainer_room_arrival", qualify)
    reader.read_current_map_blocks = lambda: CurrentMapBlocks(start_map, ((1,),))
    old.runtime.adapter.observe = lambda: replace(observe(), game_state=replace(
        observe().game_state, facts=frozenset({prerequisite}),
    ))
    target = replace(zone, map_id=MapId(target_map), event_flag=event)
    monkeypatch.setattr(story, "static_trainer_sight_zones", lambda *_: (target,))
    skill = story.RedCartridgeLoreleiSkill(old.runtime, old.actions, world,
                                         objective_id=objective)
    available = skill.availability(old.runtime.adapter.observe().game_state)
    assert available.executable is (fault is None)
    assert calls == [target_map]
    assert bool(planned_graphs) is (fault is None)
    assert world.macro_graph is original_graph
    if fault is None:
        assert original_graph.warp_arrivals[target_map] == ((11, 4), (11, 5), (0, 4))
    assert not inputs


def test_same_room_lorelei_does_not_reconsume_entrance_event(fixture, monkeypatch):
    old, reader, inputs, observe, _ = fixture
    flags = bytearray(reader.raw.event_flags)
    flags[284] |= 64  # entrance consumed; trainer still undefeated
    reader.raw = replace(reader.raw, event_flags=bytes(flags))
    monkeypatch.setattr(arrival, "trainer_room_arrival", lambda *_: pytest.fail(
        "same-room continuation must not requalify a consumed entrance"))
    assert old.availability(observe().game_state).executable
    assert not inputs
