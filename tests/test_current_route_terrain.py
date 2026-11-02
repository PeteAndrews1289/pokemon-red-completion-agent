"""Live geometry can open or close paths, without dropping story requirements."""
import pytest
from test_gen1_terrain import cartridge

import pokemon_red_completion.strategic_navigation_scenario_runtime as runtime
from pokemon_red_completion.gen1_terrain import terrain_for, tilesets
from pokemon_red_completion.gen1_traversal import TraversalRules, surf_local_graph
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalGraph, LocalRouterError, find_local_path
from pokemon_red_completion.observation import CurrentMapBlocks
from pokemon_red_completion.semantic_traversal import LocalPassageRequirement


def _world():
    rom = cartridge(block_ids=[[0, 1]], blocks={0: [1] * 16, 1: [2] * 16})
    sets = tilesets(rom)
    terrain = terrain_for(rom, 0, sets)
    rules = TraversalRules((), (), (), (), ())
    return runtime.StrategicScenarioRouteWorld(
        MacroGraph({}), {0: surf_local_graph(terrain, rules), 1: LocalGraph({})},
        rom, {0: terrain}, rules, sets, frozenset(), {0: frozenset()},
    )


def test_live_grid_changes_only_the_observed_map_and_can_close_it_again():
    original = _world()
    with pytest.raises(LocalRouterError):
        find_local_path(original.local_graphs[0], (0, 0), (0, 3), start_mode="land")
    opened = original.with_current_blocks(CurrentMapBlocks(0, ((0, 0),)))
    path = find_local_path(opened.local_graphs[0], (0, 0), (0, 3), start_mode="land")
    assert path.coordinates == (
        (0, 0), (0, 1), (0, 2), (0, 3),
    )
    assert original.terrain[0].blocks == ((0, 1),)
    assert opened.local_graphs[1] is original.local_graphs[1]
    assert opened.macro_graph is original.macro_graph
    closed = opened.with_current_blocks(CurrentMapBlocks(0, ((0, 1),)))
    with pytest.raises(LocalRouterError):
        find_local_path(closed.local_graphs[0], (0, 0), (0, 3), start_mode="land")


def test_overlay_keeps_story_predicates_and_static_object_blockers(monkeypatch):
    from dataclasses import replace
    world = replace(_world(), object_blockers={0: frozenset({(1, 2), (1, 3)})})
    monkeypatch.setattr(runtime, "GEN1_STORY_PASSAGE_REQUIREMENTS", (
        LocalPassageRequirement(0, (0, 1), (0, 2), "story:test-door"),
    ))
    opened = world.with_current_blocks(CurrentMapBlocks(0, ((0, 0),)))
    with pytest.raises(LocalRouterError):
        find_local_path(opened.local_graphs[0], (0, 0), (0, 3), start_mode="land")
    assert find_local_path(opened.local_graphs[0], (0, 0), (0, 3), start_mode="land",
                           capabilities=frozenset({"story:test-door"})).coordinates == (
        (0, 0), (0, 1), (0, 2), (0, 3),
    )
    with pytest.raises(LocalRouterError):
        find_local_path(opened.local_graphs[0], (0, 0), (1, 3), start_mode="land",
                        capabilities=frozenset({"story:test-door"}))


@pytest.mark.parametrize("blocks", [CurrentMapBlocks(5, ((0,),)), CurrentMapBlocks(0, ((0,),))])
def test_wrong_map_or_shape_is_not_invented(blocks):
    with pytest.raises(ValueError):
        _world().with_current_blocks(blocks)


def _reader(*, objects=(), map_id=0, battle=0, ready=True, dialogue=False, engagement=False):
    from types import SimpleNamespace
    raw = SimpleNamespace(game_started=True, battle_state=battle, map_id=map_id)
    return SimpleNamespace(
        read=lambda: raw,
        read_input_readiness=lambda: SimpleNamespace(ready=ready),
        read_bottom_dialogue_box_visible=lambda: dialogue,
        trainer_engagement_active=lambda: engagement,
        read_current_map_blocks=lambda: CurrentMapBlocks(map_id, ((0, 0),)),
        read_current_map_objects=lambda: objects,
    )


def _object(index, at, image=255):
    from pokemon_red_completion.observation import CurrentMapObject
    return CurrentMapObject(index, 1, at, 1, image)


def test_live_objects_remove_old_blockers_but_retain_offscreen_occupancy():
    from dataclasses import replace
    original = replace(_world(), object_blockers={0: frozenset({(0, 1)}), 1: frozenset({(8, 8)})})
    updated = original.with_current_observation(_reader(objects=(_object(2, (1, 3)),)))
    assert find_local_path(updated.local_graphs[0], (0, 0), (0, 3), start_mode="land")
    with pytest.raises(LocalRouterError):
        find_local_path(updated.local_graphs[0], (0, 0), (1, 3), start_mode="land")
    assert original.object_blockers[0] == {(0, 1)}
    assert updated.object_blockers[1] == {(8, 8)}
    assert updated.local_graphs[1] is original.local_graphs[1]
    assert updated.macro_graph is original.macro_graph


def test_live_object_overlay_does_not_remove_story_requirements(monkeypatch):
    monkeypatch.setattr(runtime, "GEN1_STORY_PASSAGE_REQUIREMENTS", (
        LocalPassageRequirement(0, (0, 1), (0, 2), "story:test-door"),
    ))
    updated = _world().with_current_observation(_reader(objects=(
        _object(1, (1, 1)), _object(2, (1, 2)),
    )))
    with pytest.raises(LocalRouterError):
        find_local_path(updated.local_graphs[0], (0, 0), (0, 3), start_mode="land")
    assert find_local_path(updated.local_graphs[0], (0, 0), (0, 3), start_mode="land",
                           capabilities=frozenset({"story:test-door"}))


def test_guard_on_gated_tile_is_blocked_then_reveals_the_original_gate(monkeypatch):
    monkeypatch.setattr(runtime, "GEN1_STORY_PASSAGE_REQUIREMENTS", (
        LocalPassageRequirement(0, (0, 1), (0, 2), "story:test-door"),
    ))
    world = _world().with_current_observation(_reader(objects=(
        _object(1, (0, 2)), _object(2, (1, 2)),
    )))
    with pytest.raises(LocalRouterError):
        find_local_path(world.local_graphs[0], (0, 0), (0, 3), start_mode="land",
                        capabilities=frozenset({"story:test-door"}))
    moved = world.with_current_observation(_reader(objects=(_object(2, (1, 2)),)))
    with pytest.raises(LocalRouterError):
        find_local_path(moved.local_graphs[0], (0, 0), (0, 3), start_mode="land")
    assert find_local_path(moved.local_graphs[0], (0, 0), (0, 3), start_mode="land",
                           capabilities=frozenset({"story:test-door"}))


@pytest.mark.parametrize("kwargs", [
    {"battle": 1}, {"ready": False}, {"dialogue": True}, {"engagement": True}, {"map_id": 9},
])
def test_live_object_overlay_refuses_unsettled_or_unknown_map(kwargs):
    with pytest.raises(ValueError, match="settled field"):
        _world().with_current_observation(_reader(**kwargs))


def test_live_object_overlay_refuses_mixed_or_changed_read():
    reader = _reader()
    reader.read_current_map_blocks = lambda: CurrentMapBlocks(1, ((0, 0),))
    with pytest.raises(ValueError, match="changed"):
        _world().with_current_observation(reader)


@pytest.mark.parametrize("objects", [
    (_object(1, (0, 1)), _object(2, (0, 1))),
    (_object(1, (0, 1)), _object(1, (1, 1))),
])
def test_live_object_overlay_refuses_duplicate_objects(objects):
    with pytest.raises(ValueError, match="repeats"):
        _world().with_current_observation(_reader(objects=objects))
