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
def region(monkeypatch):
    monkeypatch.setattr(
        funding,
        "trainer_party_quote",
        lambda *args: TrainerPartyQuote(
            201,
            9,
            (TrainerPartyMember(108, 23, 21),),
            15,
            315,
        ),
    )
    grid = LocalGraph(
        {
            (y, x): tuple(
                LocalEdge((y + dy, x + dx), action=action)
                for dy, dx, action in (
                    (-1, 0, "up"),
                    (1, 0, "down"),
                    (0, -1, "left"),
                    (0, 1, "right"),
                )
                if 0 <= y + dy < 7 and 0 <= x + dx < 8
            )
            for y in range(7)
            for x in range(8)
        }
    )
    graph = MacroGraph(
        {
            22: (
                MacroEdge(23, coordinate_transitions=(MacroTransition((5, 7), (5, 0), "right"),)),
            ),
            23: (),
        }
    )
    world = SimpleNamespace(macro_graph=graph, local_graphs={22: grid, 23: grid})
    start = TraversalSnapshot(map_id=22, at=(5, 1), ready=True, mode="land")
    trainers = (
        TrainerSightZone(22, 1, 201, 9, (1, 2), TrainerFacing.UP, 1, 9, True, True),
        TrainerSightZone(23, 1, 201, 9, (2, 4), TrainerFacing.DOWN, 3, 17, False, False),
    )
    return world, start, trainers


def candidates(region, **kwargs):
    world, start, trainers = region
    return funding.regional_trainer_funding_candidates(
        b"test",
        world,
        start,
        trainers,
        inventoried_maps=frozenset({22, 23}),
        **kwargs,
    )


def test_real_connection_plan_reserves_remote_sight_without_cross_map_collision(region):
    (candidate,) = candidates(region)
    assert candidate.trainer.map_id == 23
    assert candidate.approach.macro_path.maps == (22, 23)
    steps = candidate.approach.steps
    assert any(s.expected_map == 22 and s.expected_at == (5, 4) for s in steps)
    assert not any(
        s.expected_map == 23 and s.expected_at in {(2, 4), (3, 4), (4, 4), (5, 4)} for s in steps
    )
    assert sum(s.kind == "connection" for s in steps) == 1
    assert candidate.approach.terminal_map == 23
    assert candidate.approach.terminal_at == (2, 3)
    assert candidate.interaction_facing is TrainerFacing.RIGHT


def test_remote_sight_covering_only_arrival_makes_route_unavailable(region):
    world, start, trainers = region
    target = replace(trainers[1], at=(3, 0), engage_distance=3)
    assert candidates((world, start, (trainers[0], target))) == ()


def test_preserves_live_origin_occupancy(region):
    world, start, trainers = region
    start = replace(start, occupied=frozenset({(4, 1), (6, 1), (5, 0), (5, 2)}))
    assert candidates((world, start, trainers)) == ()


def test_refuses_missing_map_coverage_and_duplicate_identity(region):
    world, start, trainers = region
    with pytest.raises(ValueError, match="complete"):
        funding.regional_trainer_funding_candidates(
            b"", world, start, trainers, inventoried_maps=frozenset({22})
        )
    with pytest.raises(ValueError, match="duplicate"):
        candidates((world, start, trainers + (trainers[1],)))


@pytest.mark.parametrize("bound", [0, -1, True, 1.5])
def test_invalid_bound(region, bound):
    with pytest.raises(ValueError):
        candidates(region, maximum_steps=bound)


def test_step_bound_and_defeated_target(region):
    assert candidates(region, maximum_steps=2) == ()
    world, start, trainers = region
    assert candidates((world, start, tuple(replace(t, defeated=True) for t in trainers))) == ()


@pytest.mark.parametrize(
    "edge_changes",
    [
        {"action_kind": MacroActionKind.FIELD_MOVE},
        {"kind": "ledge"},
        {"result_mode": "water"},
        {"requirements": frozenset({"unobserved-story-event"})},
    ],
)
def test_cannot_use_hm_ledge_water_or_unmet_story_shortcut(region, edge_changes):
    world, _, _ = region
    original = world.local_graphs[23]
    world.local_graphs[23] = LocalGraph(
        {
            at: tuple(
                replace(e, **edge_changes) if at[0] == 5 and e.target[0] == 4 else e
                for e in edges
                if not (at[0] == 5 and e.target[0] == 6)
            )
            for at, edges in original.edges.items()
        }
    )
    assert candidates(region) == ()


def test_scope_never_expands_through_warps_or_second_neighbor(region):
    world, _, _ = region
    graph = replace(
        world.macro_graph,
        edges={
            22: world.macro_graph.edges[22]
            + (MacroEdge(40, kind="warp", at=(0, 0), arrival_at=(0, 0)),),
            23: (MacroEdge(41),),
        },
    )
    assert funding.connected_funding_maps(graph, 22) == frozenset({22, 23})


def test_route_postcondition_catches_planner_ignoring_reservations(region, monkeypatch):
    original = funding.plan_route

    def unsafe(*args, **kwargs):
        kwargs["blocked"] = {}
        return original(*args, **kwargs)

    monkeypatch.setattr(funding, "plan_route", unsafe)
    with pytest.raises(CartridgeReadError, match="corridor"):
        candidates(region)


def indoor_region(region):
    world, start, trainers = region
    world.local_graphs[154] = world.local_graphs[22]
    world.macro_graph = replace(world.macro_graph, edges={
        **world.macro_graph.edges,
        154: (MacroEdge(22, kind="warp", at=(5, 3), arrival_at=(5, 1)),),
    })
    return world, replace(start, map_id=154, last_outside_map=22), trainers


def test_opted_indoor_route_crosses_one_exit_then_real_connection(region):
    world, start, trainers = indoor_region(region)
    (candidate,) = funding.regional_trainer_funding_candidates(
        b"test", world, start, trainers,
        inventoried_maps=frozenset({154, 22, 23}), indoor_exit_map=22,
    )
    assert candidate.approach.macro_path.maps == (154, 22, 23)
    assert [s.kind for s in candidate.approach.steps if s.kind != "walk"] == ["warp", "connection"]
    assert candidate.approach.terminal_at == (2, 3)
    assert len(candidate.approach.steps) > 2
    assert funding.regional_trainer_funding_candidates(
        b"test", world, start, trainers, maximum_steps=2,
        inventoried_maps=frozenset({154, 22, 23}), indoor_exit_map=22,
    ) == ()


@pytest.mark.parametrize("exit_map", [True, -1, 37, 23])
def test_indoor_exit_requires_observed_outdoor_identity(region, exit_map):
    world, start, _ = indoor_region(region)
    with pytest.raises(ValueError, match="observed"):
        funding.funding_scope(world.macro_graph, start, indoor_exit_map=exit_map)


def test_indoor_scope_rejects_missing_inventory_and_other_doors(region):
    world, start, trainers = indoor_region(region)
    with pytest.raises(ValueError, match="complete"):
        funding.regional_trainer_funding_candidates(
            b"test", world, start, trainers,
            inventoried_maps=frozenset({22, 23}), indoor_exit_map=22,
        )
    world.macro_graph = replace(world.macro_graph, edges={
        **world.macro_graph.edges,
        154: (MacroEdge(23, kind="warp", at=(5, 3), arrival_at=(5, 1)),),
    })
    assert funding.regional_trainer_funding_candidates(
        b"test", world, start, trainers,
        inventoried_maps=frozenset({154, 22, 23}), indoor_exit_map=22,
    ) == ()


def test_indoor_exit_still_reserves_origin_and_remote_sight(region):
    world, start, trainers = indoor_region(region)
    for blocked in ({(5, 2), (4, 1), (6, 1), (5, 0)}, {(5, 3)}):
        assert funding.regional_trainer_funding_candidates(
            b"test", world, replace(start, occupied=frozenset(blocked)), trainers,
            inventoried_maps=frozenset({154, 22, 23}), indoor_exit_map=22,
        ) == ()
    target = replace(trainers[1], at=(3, 0), engage_distance=3)
    assert funding.regional_trainer_funding_candidates(
        b"test", world, start, (trainers[0], target),
        inventoried_maps=frozenset({154, 22, 23}), indoor_exit_map=22,
    ) == ()


def test_return_exit_uses_retained_outside_and_cartridge_arrival(region):
    world, start, trainers = indoor_region(region)
    world.macro_graph = replace(world.macro_graph, edges={
        **world.macro_graph.edges,
        154: (MacroEdge(None, kind="return", at=(5, 3), destination_warp_index=0),),
    }, warp_locations={22: ((5, 1),)})
    (candidate,) = funding.regional_trainer_funding_candidates(
        b"test", world, start, trainers,
        inventoried_maps=frozenset({154, 22, 23}), indoor_exit_map=22,
    )
    step = next(s for s in candidate.approach.steps if s.kind == "return")
    assert (step.expected_map, step.expected_at) == (22, (5, 1))
    assert candidate.approach.macro_path.maps == (154, 22, 23)
