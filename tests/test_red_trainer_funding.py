from dataclasses import replace

import pytest

from pokemon_red_completion import red_trainer_funding as funding
from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_trainer_parties import TrainerPartyMember, TrainerPartyQuote
from pokemon_red_completion.gen1_trainer_sight import TrainerFacing, TrainerSightZone
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_executor import TraversalHazard, TraversalSnapshot
from pokemon_red_completion.route_plan import plan_route


class World:
    def __init__(self):
        self.calls = []
        edges = {}
        for y in range(7):
            for x in range(8):
                edges[(y, x)] = tuple(
                    LocalEdge((y + dy, x + dx), action=action)
                    for dy, dx, action in (
                        (-1, 0, "up"),
                        (1, 0, "down"),
                        (0, -1, "left"),
                        (0, 1, "right"),
                    )
                    if 0 <= y + dy < 7 and 0 <= x + dx < 8
                )
        self.local = LocalGraph(edges)

    def plan_feasible_to_map(self, start, goal_map, *, goal_at):
        self.calls.append(start)
        return plan_route(
            MacroGraph({22: ()}),
            {22: self.local},
            22,
            start.at,
            goal_map,
            goal_at=goal_at,
            blocked={22: start.occupied},
            start_mode=start.mode,
        )


@pytest.fixture
def setup(monkeypatch):
    quotes = []

    def quote(rom, opponent, number):
        quotes.append((opponent, number))
        return TrainerPartyQuote(opponent, number, (TrainerPartyMember(108, 23, 21),), 15, 315)

    monkeypatch.setattr(funding, "trainer_party_quote", quote)
    world = World()
    start = TraversalSnapshot(map_id=22, at=(5, 1), ready=True, mode="land")
    trainers = (
        TrainerSightZone(22, 3, 201, 9, (2, 4), TrainerFacing.DOWN, 3, 1139, False, False),
        TrainerSightZone(22, 4, 212, 2, (3, 6), TrainerFacing.LEFT, 2, 1140, False, True),
        TrainerSightZone(22, 5, 201, 10, (1, 1), TrainerFacing.DOWN, 3, 1141, True, True),
    )
    return world, start, trainers, quotes


def test_computed_adjacent_routes_avoid_all_unbeaten_sight_and_defeated_bodies(setup):
    world, start, trainers, quotes = setup
    candidates = funding.local_trainer_funding_candidates(b"test", world, start, trainers)
    assert quotes == [(201, 9), (212, 2)]
    assert [c.trainer.sprite_index for c in candidates] == [3, 4]
    assert [len(c.approach.steps) for c in candidates] == [5, 8]
    forbidden = {(2, 4), (3, 6), (1, 1), (3, 4), (4, 4), (5, 4), (3, 5)}
    assert all(forbidden <= call.occupied for call in world.calls)
    for candidate in candidates:
        assert not forbidden.intersection(step.expected_at for step in candidate.approach.steps)
        dy, dx = candidate.interaction_facing.delta
        y, x = candidate.approach.terminal_at
        assert (y + dy, x + dx) == candidate.trainer.at
    assert start.occupied == frozenset()  # Enumeration never rewrites the observation.


def test_additional_live_occupancy_and_hazards_are_preserved(setup):
    world, start, trainers, _ = setup
    start = replace(start, occupied=frozenset({(4, 2)}), hazards=(TraversalHazard((5, 2), "test"),))
    funding.local_trainer_funding_candidates(b"test", world, start, trainers)
    assert world.calls
    assert all({(4, 2), (5, 2)} <= call.occupied for call in world.calls)


@pytest.mark.parametrize(
    "changes", [{"ready": False}, {"interruption": "battle:2"}, {"mode": "water"}, {"at": (4, 4)}]
)
def test_unsafe_origin_issues_no_planner_or_quote_calls(setup, changes):
    world, start, trainers, quotes = setup
    assert (
        funding.local_trainer_funding_candidates(
            b"test", world, replace(start, **changes), trainers
        )
        == ()
    )
    assert world.calls == quotes == []


def test_bound_prevents_advertising_overlong_approach(setup):
    world, start, trainers, _ = setup
    assert (
        funding.local_trainer_funding_candidates(b"test", world, start, trainers, maximum_steps=1)
        == ()
    )


def test_already_adjacent_can_be_zero_step_but_still_requires_facing(setup):
    world, start, trainers, _ = setup
    candidates = funding.local_trainer_funding_candidates(
        b"test", world, replace(start, at=(2, 3)), trainers
    )
    assert len(candidates[0].approach.steps) == 0
    assert candidates[0].interaction_facing is TrainerFacing.RIGHT


@pytest.mark.parametrize("bad", [0, -1, True, 1.5])
def test_invalid_bound_refuses(setup, bad):
    world, start, trainers, _ = setup
    with pytest.raises(ValueError):
        funding.local_trainer_funding_candidates(b"test", world, start, trainers, maximum_steps=bad)


def test_duplicate_or_wrong_map_identity_refuses(setup):
    world, start, trainers, _ = setup
    for items in ((trainers[0], trainers[0]), (replace(trainers[0], map_id=23),)):
        with pytest.raises(ValueError):
            funding.local_trainer_funding_candidates(b"test", world, start, items)


def test_unreachable_trainers_are_not_candidates(setup):
    world, start, trainers, _ = setup
    start = replace(start, occupied=frozenset({(4, 1), (6, 1), (5, 0), (5, 2)}))
    assert funding.local_trainer_funding_candidates(b"test", world, start, trainers) == ()


def test_router_cannot_ignore_reserved_corridor(setup, monkeypatch):
    world, start, trainers, _ = setup
    original = world.plan_feasible_to_map

    def ignoring(start, goal_map, *, goal_at):
        return original(replace(start, occupied=frozenset()), goal_map, goal_at=goal_at)

    monkeypatch.setattr(world, "plan_feasible_to_map", ignoring)
    with pytest.raises(CartridgeReadError, match="corridor"):
        funding.local_trainer_funding_candidates(b"test", world, start, trainers)
