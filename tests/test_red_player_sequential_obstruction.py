from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_story_obstruction as s
from pokemon_red_completion.gen1_trainer_sight import TrainerFacing, TrainerSightZone
from pokemon_red_completion.route_executor import TraversalHazard, TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError


@pytest.mark.parametrize("fault", [None, "unreachable_first", "other_hazard", "shared"])
def test_sequence_only_offers_safely_approachable_first_blocker(monkeypatch, fault):
    first = TrainerSightZone(14, 1, 203, 1, (5, 5), TrainerFacing.LEFT, 1, 996, False, True)
    second = TrainerSightZone(14, 2, 202, 1, (8, 5), TrainerFacing.LEFT, 1, 997, False, True)
    zones = (first, second)
    if fault == "shared":
        from dataclasses import replace

        zones += (replace(first, sprite_index=3, event_flag=998),)
    hazards = tuple(TraversalHazard(at, "trainer_sight") for t in zones for at in t.lane)
    if fault == "other_hazard":
        hazards += (TraversalHazard((5, 4), "unrelated"),)
    start = TraversalSnapshot(14, (6, 4), True, mode="land", hazards=hazards)
    candidate = N(trainer=first)
    calls = []

    def route(snapshot, destination):
        assert destination == 15
        calls.append(snapshot)
        if snapshot.hazards:
            raise RoutePlanningError("blocked")
        return N(
            steps=(N(expected_map=14, expected_at=(5, 4)), N(expected_map=14, expected_at=(8, 4)))
        )

    monkeypatch.setattr(
        s,
        "local_trainer_funding_candidates",
        lambda *a, **k: () if fault == "unreachable_first" else (candidate,),
    )
    monkeypatch.setattr(s, "planned_sight_approaches", lambda *a: ())
    found = s.blocking_story_trainers(
        b"rom", N(plan_feasible_to_map=route), start, zones, 15, allow_sequence=True
    )
    assert found == ((candidate,) if fault is None else ())
    assert start.hazards == hazards and calls[0] is start


@pytest.mark.parametrize("unknown_first", [False, True])
def test_later_scripted_object_does_not_hide_earlier_reachable_trainer(monkeypatch, unknown_first):
    from pokemon_red_completion import strategic_navigation_scenario_runtime as world_module

    target = TrainerSightZone(61, 5, 230, 4, (17, 29), TrainerFacing.LEFT, 4, 1405, False, True)
    start = TraversalSnapshot(
        61,
        (17, 21),
        True,
        mode="land",
        occupied=frozenset({(8, 12)}),
        hazards=tuple(TraversalHazard(at, "trainer_sight") for at in target.lane),
    )
    candidate = N(trainer=target)

    class World:
        def plan_feasible_to_map(self, *a, **k):
            raise RoutePlanningError("later scripted object blocks every complete route")

    world = World()
    monkeypatch.setattr(world_module, "StrategicScenarioRouteWorld", World)
    steps = (N(expected_map=61, expected_at=(8, 12)), N(expected_map=61, expected_at=(17, 25)))
    if not unknown_first:
        steps = steps[::-1]
    monkeypatch.setattr(
        s,
        "story_object_preview",
        lambda *a: (N(plan_feasible_to_map=lambda *a, **k: N(steps=steps)), start),
    )
    monkeypatch.setattr(s, "local_trainer_funding_candidates", lambda *a, **k: (candidate,))
    assert s.blocking_story_trainers(
        b"rom", world, start, (target,), 60, allow_sequence=True, destination_at=(3, 23)
    ) == (() if unknown_first else (candidate,))
