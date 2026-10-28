from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.global_router import MacroEdge, MacroGraph
from pokemon_red_completion.local_router import LocalGraph
from pokemon_red_completion.red_regional_trainer_funding import (
    FundingGateTransit,
    observed_fly_funding_gate_region,
)
from pokemon_red_completion.route_executor import TraversalSnapshot


@pytest.fixture
def observed_region():
    region = FundingGateTransit(frozenset({7, 24, 25, 26, 0xB8}), frozenset({0xB8}), 6)
    maps = region.maps | {6, 0x87}
    world = SimpleNamespace(
        macro_graph=MacroGraph({m: () for m in maps}),
        local_graphs={m: LocalGraph({}) for m in maps},
        object_blockers={m: frozenset() for m in maps},
    )
    start = TraversalSnapshot(map_id=0x87, at=(8, 5), ready=True, mode="land", last_outside_map=6)
    return world, start, region


def test_observed_origin_extends_fixed_inventory_without_adding_doors(observed_region):
    world, start, region = observed_region
    result = observed_fly_funding_gate_region(world, start, region, (0, 1, 6, 7, 10))
    assert result == FundingGateTransit(region.maps | {6, 0x87}, region.gate_maps, 6)
    assert region.maps == frozenset({7, 24, 25, 26, 0xB8})
    assert not result.permits(0x87, MacroEdge(6, kind="warp", at=(9, 5), arrival_at=(6, 6)))


@pytest.mark.parametrize("destinations", [(), (0, 1, 6), (True, 7), (7, 256), (7, "7"), [7]])
def test_requires_native_typed_destination_in_declared_region(observed_region, destinations):
    world, start, region = observed_region
    assert observed_fly_funding_gate_region(world, start, region, destinations) is None


@pytest.mark.parametrize("changes", [
    {"ready": False}, {"ready": 1}, {"interruption": "wild_battle"},
    {"mode": "water"}, {"map_id": True}, {"map_id": 0x0B},
    {"last_outside_map": None}, {"last_outside_map": True}, {"last_outside_map": 0x25},
])
def test_unsettled_or_unknown_origin_has_no_offer(observed_region, changes):
    world, start, region = observed_region
    assert observed_fly_funding_gate_region(world, replace(start, **changes), region, (7,)) is None


@pytest.mark.parametrize("inventory", ["macro", "local", "objects"])
@pytest.mark.parametrize("missing", [6, 7, 0x87, 0xB8])
def test_missing_source_destination_or_gate_inventory_fails_closed(observed_region, inventory, missing):
    world, start, region = observed_region
    if inventory == "macro":
        world.macro_graph = replace(world.macro_graph, edges={m: e for m, e in world.macro_graph.edges.items() if m != missing})
    elif inventory == "local":
        world.local_graphs.pop(missing)
    else:
        world.object_blockers.pop(missing)
    assert observed_fly_funding_gate_region(world, start, region, (7,)) is None


def test_unknown_retained_outside_boundary_cannot_enter_region(observed_region):
    world, start, region = observed_region
    world.macro_graph = replace(world.macro_graph, retained_outside_overrides={0xB8: 99})
    assert observed_fly_funding_gate_region(world, start, region, (7,)) is None


def test_requires_complete_typed_static_objects(observed_region):
    world, start, region = observed_region
    world.object_blockers[7] = set()
    assert observed_fly_funding_gate_region(world, start, region, (7,)) is None


def test_untyped_region_is_rejected(observed_region):
    world, start, _ = observed_region
    with pytest.raises(TypeError, match="typed fixed region"):
        observed_fly_funding_gate_region(world, start, None, (7,))
