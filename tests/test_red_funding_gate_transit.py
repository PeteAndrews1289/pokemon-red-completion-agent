"""Declared multi-map income transport; no ROM, inputs or favorable resets."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_regional_trainer_funding as f
from pokemon_red_completion.gen1_trainer_parties import TrainerPartyMember, TrainerPartyQuote
from pokemon_red_completion.gen1_trainer_sight import TrainerFacing, TrainerSightZone
from pokemon_red_completion.global_router import MacroEdge, MacroGraph, MacroTransition
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_executor import TraversalSnapshot


@pytest.fixture
def gate_world(monkeypatch):
    monkeypatch.setattr(f, "trainer_party_quote", lambda *_: TrainerPartyQuote(
        201, 1, (TrainerPartyMember(108, 23, 7),), 10, 70))
    grid = LocalGraph({(y, x): tuple(
        LocalEdge((y+dy, x+dx), action=d)
        for dy, dx, d in ((-1, 0, "up"), (1, 0, "down"),
                         (0, -1, "left"), (0, 1, "right"))
        if 0 <= y+dy < 7 and 0 <= x+dx < 8)
        for y in range(7) for x in range(8)})
    graph = MacroGraph({
        42: (MacroEdge(1, "warp", at=(5, 3), arrival_at=(5, 1)),),
        1: (MacroEdge(13, coordinate_transitions=(
            MacroTransition((5, 7), (5, 0), "right"),)),),
        13: (MacroEdge(50, "warp", at=(5, 3), arrival_at=(5, 1)),),
        50: (MacroEdge(51, "warp", at=(5, 3), arrival_at=(5, 0)),),
        51: (),
    }, outside_nodes=frozenset({1, 13}))
    world = SimpleNamespace(macro_graph=graph, local_graphs={m: grid for m in graph.edges})
    start = TraversalSnapshot(42, (5, 1), ready=True, mode="land", last_outside_map=1)
    target = TrainerSightZone(51, 1, 201, 1, (2, 4), TrainerFacing.DOWN, 1, 17, False, False)
    contract = f.FundingGateTransit(frozenset(graph.edges), frozenset({50}), 4)
    return world, start, target, contract


def run(case, **kwargs):
    world, start, target, contract = case
    options = dict(inventoried_maps=contract.maps, gate_transit=contract,
                   static_blockers={m: frozenset() for m in contract.maps}, indoor_exit_map=1)
    options.update(kwargs)
    return f.regional_trainer_funding_candidates(b"test", world, start, (target,), **options)


def test_declared_gate_route_is_real_and_default_does_not_expand(gate_world):
    world, start, _, contract = gate_world
    assert f.funding_scope(world.macro_graph, start, indoor_exit_map=1) == {42, 1, 13}
    assert f.funding_scope(world.macro_graph, start, indoor_exit_map=1,
                           gate_transit=contract) == contract.maps
    (candidate,) = run(gate_world)
    assert candidate.approach.macro_path.maps == (42, 1, 13, 50, 51)
    assert candidate.quote.expected_victory_money == 70
    assert candidate.approach.terminal_at == (2, 3)
    assert run(gate_world, gate_transit=replace(contract, maximum_transitions=3)) == ()
    assert run(gate_world, maximum_steps=3) == ()


@pytest.mark.parametrize("gate", [47, 49, 50, 70, 73, 76, 79, 184])
def test_gate_inventory_is_not_a_single_forest_route(gate_world, gate):
    world, start, target, contract = gate_world
    def rename(m):
        return gate if m == 50 else m

    world.macro_graph = replace(world.macro_graph, edges={
        rename(m): tuple(replace(e, target_map=rename(e.target_map)) for e in edges)
        for m, edges in world.macro_graph.edges.items()
    })
    world.local_graphs = {rename(m): g for m, g in world.local_graphs.items()}
    contract = replace(contract, maps=frozenset(map(rename, contract.maps)),
                       gate_maps=frozenset({gate}))
    (candidate,) = run((world, start, target, contract))
    assert candidate.approach.macro_path.maps == (42, 1, 13, gate, 51)


def test_multiple_declared_gates_obey_the_same_total_transition_cap(gate_world):
    world, start, target, contract = gate_world
    world.macro_graph = replace(world.macro_graph, edges={
        **world.macro_graph.edges,
        51: (MacroEdge(49, "warp", at=(5, 3), arrival_at=(5, 1)),),
        49: (MacroEdge(14, "warp", at=(5, 3), arrival_at=(5, 0)),),
        14: (),
    })
    world.local_graphs.update({49: world.local_graphs[50], 14: world.local_graphs[51]})
    contract = replace(contract, maps=contract.maps | {49, 14},
                       gate_maps=contract.gate_maps | {49}, maximum_transitions=6)
    case = world, start, replace(target, map_id=14), contract
    (candidate,) = run(case)
    assert candidate.approach.macro_path.maps == (42, 1, 13, 50, 51, 49, 14)
    assert run(case, gate_transit=replace(contract, maximum_transitions=5)) == ()


@pytest.mark.parametrize("kwargs", [
    {"inventoried_maps": frozenset({42, 1, 13, 51})},
    {"static_blockers": None},
    {"static_blockers": {42: frozenset()}},
])
def test_incomplete_transit_inventory_rejected(gate_world, kwargs):
    with pytest.raises(ValueError, match="inventory"):
        run(gate_world, **kwargs)


def test_transit_npc_and_trainer_hazards_respected(gate_world):
    _, _, _, contract = gate_world
    blocks = {m: frozenset() for m in contract.maps}
    blocks[50] = frozenset({(5, 1)})
    assert run(gate_world, static_blockers=blocks) == ()
    world, start, target, _ = gate_world
    transit = replace(target, map_id=50, at=(3, 1), engage_distance=2)
    assert f.regional_trainer_funding_candidates(
        b"test", world, start, (target, transit), inventoried_maps=contract.maps,
        gate_transit=contract, static_blockers={m: frozenset() for m in contract.maps},
        indoor_exit_map=1) == ()


def test_unmet_story_passage_is_not_bypassed(gate_world):
    world, start, target, contract = gate_world
    world.local_graphs[50] = LocalGraph({at: tuple(
        replace(edge, requirements=frozenset({"story:gate_open"})) for edge in edges)
        for at, edges in world.local_graphs[50].edges.items()})
    assert run(gate_world) == ()
    assert run((world, replace(start, capabilities=frozenset({"story:gate_open"})),
                target, contract))


@pytest.mark.parametrize("kind", ["teleport", "elevator", "fly", "hole"])
def test_gate_endpoint_does_not_permit_nonwalking_transport(gate_world, kind):
    world, _, _, _ = gate_world
    world.macro_graph = replace(world.macro_graph, edges={
        **world.macro_graph.edges,
        13: (replace(world.macro_graph.edges[13][0], kind=kind),),
    })
    assert run(gate_world) == ()


def test_arbitrary_door_shortcut_is_excluded(gate_world):
    world, _, _, _ = gate_world
    world.macro_graph = replace(world.macro_graph, edges={
        **world.macro_graph.edges,
        42: world.macro_graph.edges[42] + (
            MacroEdge(51, "warp", at=(5, 2), arrival_at=(2, 3)),),
    })
    assert run(gate_world)[0].approach.macro_path.maps == (42, 1, 13, 50, 51)


@pytest.mark.parametrize("fault", ["origin", "unknown_map", "outside", "override"])
def test_scope_requires_known_origin_and_return_context(gate_world, fault):
    world, start, _, contract = gate_world
    if fault == "origin":
        start = replace(start, map_id=41)
    elif fault == "unknown_map":
        contract = replace(contract, maps=contract.maps | {99})
    elif fault == "outside":
        start = replace(start, last_outside_map=99)
    else:
        world.macro_graph = replace(world.macro_graph, retained_outside_overrides={50: 99})
    with pytest.raises(ValueError, match="origin"):
        f.funding_scope(world.macro_graph, start, gate_transit=contract)


@pytest.mark.parametrize("maps,gates,limit", [
    ({1, 50}, frozenset({50}), 4),
    (frozenset({1, 50}), {50}, 4),
    (frozenset({True, 50}), frozenset({50}), 4),
    (frozenset({1, 50}), frozenset(), 4),
    (frozenset({1, 99}), frozenset({99}), 4),
    (frozenset({1, 50}), frozenset({47}), 4),
    (frozenset(range(17)) | {50}, frozenset({50}), 4),
    (frozenset({1, 50}), frozenset({50}), True),
    (frozenset({1, 50}), frozenset({50}), 0),
    (frozenset({1, 50}), frozenset({50}), 9),
])
def test_invalid_contracts(maps, gates, limit):
    with pytest.raises(ValueError, match="bounded"):
        f.FundingGateTransit(maps, gates, limit)


def test_gate_return_uses_actual_retained_outside(gate_world):
    world, _, target, contract = gate_world
    world.macro_graph = replace(world.macro_graph,
        edges={**world.macro_graph.edges,
               51: (MacroEdge(50, "warp", at=(5, 3), arrival_at=(5, 1)),),
               50: (MacroEdge(None, "return", at=(5, 3), destination_warp_index=0),)},
        warp_locations={13: ((5, 3),)})
    start = TraversalSnapshot(51, (5, 1), ready=True, mode="land", last_outside_map=13)
    target = replace(target, map_id=13)
    result = run((world, start, target, contract), indoor_exit_map=None)
    assert result[0].approach.macro_path.maps == (51, 50, 13)
    assert any(s.kind == "return" for s in result[0].approach.steps)


def test_missing_local_transit_graph_is_not_an_empty_map(gate_world):
    world, _, _, _ = gate_world
    del world.local_graphs[50]
    with pytest.raises(ValueError, match="local traversal inventory"):
        run(gate_world)


def test_departure_contract_is_frozen_in_binding(monkeypatch):
    from test_red_routed_trainer_funding import fixture

    from pokemon_red_completion import red_routed_trainer_funding as routed

    router, state, _, bindings, calls = fixture(monkeypatch)
    contract = f.FundingGateTransit(frozenset({22, 50}), frozenset({50}))
    router.funding_gate_transit = contract
    bound = routed.bind_local_trainer_funding(router, bindings, state).bindings[-1]
    router.funding_gate_transit = replace(contract, maximum_transitions=3)
    revised = routed.bind_local_trainer_funding(router, bindings, state).bindings[-1]
    assert bound.binding_ref != revised.binding_ref
    with pytest.raises(routed.RedTrainerFundingError, match="transit changed"):
        bound.execute()
    assert calls == []


@pytest.mark.parametrize("regional,observed,value", [
    (False, True, "valid"), (True, False, "valid"), (True, True, {}),
])
def test_router_requires_typed_observed_gate_opt_in(regional, observed, value):
    from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter

    contract = f.FundingGateTransit(frozenset({1, 50}), frozenset({50}))
    with pytest.raises(ValueError, match="observed regional"):
        RedResourceGoalRouter(None, None, None, regional_trainer_funding=regional,
                              observed_trainer_funding=observed,
                              funding_gate_transit=contract if value == "valid" else value)
