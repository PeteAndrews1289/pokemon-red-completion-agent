"""Default-off legal land-to-land Surf for the existing finite-income route."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_regional_trainer_funding as funding
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_trainer_parties import TrainerPartyMember, TrainerPartyQuote
from pokemon_red_completion.gen1_trainer_sight import TrainerFacing, TrainerSightZone
from pokemon_red_completion.global_router import MacroEdge, MacroGraph, MacroTransition
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_executor import TraversalSnapshot


@pytest.fixture
def crossing(monkeypatch):
    monkeypatch.setattr(funding, "trainer_party_quote", lambda *_: TrainerPartyQuote(
        201, 9, (TrainerPartyMember(108, 23, 21),), 15, 315,
    ))
    edges = {
        (0, 0): (LocalEdge((0, 1), action="surf:right", kind="water_entry",
            action_kind=MacroActionKind.FIELD_MOVE, requirements=frozenset({"move:surf"}),
            required_mode="land", result_mode="water"),),
        (0, 1): (LocalEdge((0, 2), action="right", kind="water_travel",
            required_mode="water", result_mode="water"),),
        (0, 2): (LocalEdge((0, 3), action="right", kind="water_exit",
            required_mode="water", result_mode="land"),),
        (0, 3): (LocalEdge((0, 4), action="right", required_mode="land", result_mode="land"),),
        (0, 4): (), (0, 5): (),
    }
    world = SimpleNamespace(macro_graph=MacroGraph({22: ()}), local_graphs={22: LocalGraph(edges)})
    start = TraversalSnapshot(22, (0, 0), ready=True, mode="land",
        capabilities=frozenset({"move:surf"}))
    trainer = TrainerSightZone(22, 1, 201, 9, (0, 5), TrainerFacing.UP, 1, 9, False, False)
    return world, start, (trainer,)


def candidates(case, **kwargs):
    world, start, trainers = case
    return funding.regional_trainer_funding_candidates(b"test", world, start, trainers,
        inventoried_maps=frozenset({22}), **kwargs)


def test_surf_is_default_off_and_requires_observed_capability(crossing):
    assert candidates(crossing) == ()
    world, start, trainers = crossing
    without_capability = (world, replace(start, capabilities=frozenset()), trainers)
    assert candidates(without_capability, allow_surf=True) == ()
    candidate, = candidates(crossing, allow_surf=True)
    assert candidate.approach.start_mode == candidate.approach.terminal_mode == "land"
    assert candidate.approach.terminal_at == (0, 4)
    assert [s.kind for s in candidate.approach.steps] == [
        "water_entry", "water_travel", "water_exit", "walk",
    ]
    assert candidate.interaction_facing is TrainerFacing.RIGHT


@pytest.mark.parametrize("flag", [1, None, "yes"])
def test_surf_scope_is_typed(crossing, flag):
    with pytest.raises(TypeError, match="explicit boolean"):
        candidates(crossing, allow_surf=flag)


@pytest.mark.parametrize("position", [(0, 1), (0, 2), (0, 3)])
def test_water_and_shore_blockers_remain_reserved(crossing, position):
    assert candidates(crossing, allow_surf=True, static_blockers={22: frozenset({position})}) == ()


@pytest.mark.parametrize("changes", [
    {"ready": False}, {"interruption": "wild_battle"}, {"mode": "water"},
])
def test_requires_settled_land_origin(crossing, changes):
    world, start, trainers = crossing
    assert candidates((world, replace(start, **changes), trainers), allow_surf=True) == ()


@pytest.mark.parametrize("at,changes", [
    ((0, 0), {"action": "right"}),
    ((0, 0), {"action_kind": MacroActionKind.MOVE}),
    ((0, 0), {"requirements": frozenset()}),
    ((0, 0), {"result_mode": "land"}),
    ((0, 0), {"kind": "cut_mutation", "action": "cut:right"}),
    ((0, 1), {"required_mode": "land"}),
    ((0, 1), {"result_mode": "land"}),
    ((0, 2), {"result_mode": "water"}),
    ((0, 3), {"requirements": frozenset({"unearned_story"})}),
])
def test_rejects_wrong_transition_or_missing_story_permission(crossing, at, changes):
    world, _, _ = crossing
    graph = world.local_graphs[22]
    world.local_graphs[22] = LocalGraph({
        position: tuple(replace(e, **changes) for e in outgoing) if position == at else outgoing
        for position, outgoing in graph.edges.items()
    })
    assert candidates(crossing, allow_surf=True) == ()


def test_surf_does_not_remove_target_sight_or_allow_water_interaction(crossing):
    world, start, trainers = crossing
    watching = replace(trainers[0], facing=TrainerFacing.LEFT, engage_distance=4)
    assert candidates((world, start, (watching,)), allow_surf=True) == ()
    # Remove the exit: the target must not be advertised from an aquatic stance.
    graph = world.local_graphs[22]
    world.local_graphs[22] = LocalGraph({
        **graph.edges, (0, 2): (replace(graph.edges[(0, 2)][0],
            kind="water_travel", result_mode="water"),),
    })
    assert candidates(crossing, allow_surf=True) == ()


def test_forged_route_cannot_change_authenticated_water_edge(crossing, monkeypatch):
    real = funding.plan_route

    def forged(*args, **kwargs):
        plan = real(*args, **kwargs)
        path = plan.terminal_approach
        return replace(plan, terminal_approach=replace(path,
            edges=(replace(path.edges[0], action="surf:left"), *path.edges[1:])))

    monkeypatch.setattr(funding, "plan_route", forged)
    with pytest.raises(CartridgeReadError, match="reserved corridor"):
        candidates(crossing, allow_surf=True)


def test_exact_water_connection_reuses_existing_map_transition(crossing):
    world, start, trainers = crossing
    original = world.local_graphs[22].edges
    world.macro_graph = MacroGraph({
        22: (MacroEdge(23, coordinate_transitions=(
            MacroTransition((0, 1), (0, 2), "right"),)),), 23: (),
    })
    world.local_graphs = {
        22: LocalGraph({(0, 0): original[(0, 0)], (0, 1): ()}),
        23: LocalGraph({at: outgoing for at, outgoing in original.items() if at[1] >= 2}),
    }
    candidate, = funding.regional_trainer_funding_candidates(
        b"test", world, start, (replace(trainers[0], map_id=23),),
        inventoried_maps=frozenset({22, 23}), allow_surf=True,
    )
    connection, = tuple(s for s in candidate.approach.steps if s.kind == "connection")
    assert (connection.source_map, connection.source_at) == (22, (0, 1))
    assert (connection.expected_map, connection.expected_at) == (23, (0, 2))
    assert connection.source_mode == connection.expected_mode == "water"
    assert candidate.approach.terminal_mode == "land"
