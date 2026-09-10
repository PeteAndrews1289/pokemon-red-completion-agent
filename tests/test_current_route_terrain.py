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
