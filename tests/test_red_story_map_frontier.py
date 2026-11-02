from dataclasses import dataclass
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.red_story_map_frontier import story_frontier_target
from pokemon_red_completion.route_executor import TraversalHazard, TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError


@pytest.mark.parametrize("fault", [None, "hazard", "occupied", "unquotable", "no_cut"])
def test_cut_frontier_requires_original_safe_executable_route(monkeypatch, fault):
    from pokemon_red_completion import red_story_map_frontier as m

    endpoint = (7, 5)
    start = TraversalSnapshot(
        map_id=134,
        at=(8, 5),
        ready=True,
        mode="land",
        occupied=frozenset({endpoint}) if fault == "occupied" else frozenset(),
        hazards=(TraversalHazard(endpoint, "trainer_sight"),) if fault == "hazard" else (),
    )
    preview = N(
        plan_feasible_to_map=lambda *a, **k: N(
            steps=(
                N(expected_map=134, expected_at=(8, 5), kind="cut_mutation"),
                N(expected_map=134, expected_at=endpoint, kind="walk"),
            )
        )
    )
    monkeypatch.setattr(m, "story_object_preview", lambda *a: (preview, start))
    calls = []

    def real(origin, destination, *, goal_at):
        assert origin is start and destination == 134 and goal_at == endpoint
        calls.append(goal_at)
        if fault == "unquotable":
            raise RoutePlanningError("real blocked")
        return N(steps=(N(kind="walk" if fault == "no_cut" else "cut_mutation"),))

    world = N(plan_feasible_to_map=real)
    if fault:
        with pytest.raises(RoutePlanningError):
            m.story_cut_frontier_target(world, start, (4, 4))
    else:
        assert m.story_cut_frontier_target(world, start, (4, 4)) == endpoint
    assert len(calls) == (0 if fault in ("hazard", "occupied") else 1)


def test_projection_preserves_nontrainer_hazards_and_original_world():
    seen = []

    @dataclass
    class World:
        object_blockers: dict
        terrain: dict
        local_graphs: dict

        def _graph_for_terrain(self, t):
            return ("requirements-retained", t)

        def plan_feasible_to_map(self, start, destination):
            seen.append((self, start, destination))
            return N(
                steps=(
                    N(expected_map=15, expected_at=(3, 4)),
                    N(expected_map=59, expected_at=(35, 14)),
                    N(expected_map=15, expected_at=(6, 24)),
                    N(expected_map=3, expected_at=(18, 0)),
                )
            )

    world = World(
        {15: frozenset({(2, 2)}), 59: frozenset({(3, 3)})},
        {15: "terrain15", 59: "terrain59"},
        {15: "original15", 59: "original59"},
    )
    start = TraversalSnapshot(
        map_id=15,
        at=(3, 3),
        ready=True,
        mode="land",
        occupied=frozenset({(2, 2)}),
        hazards=(TraversalHazard((2, 3), "trainer_sight"), TraversalHazard((3, 4), "scripted")),
    )
    assert story_frontier_target(world, start, 3) == (59, (35, 14))
    preview, probe, goal = seen[0]
    assert not probe.occupied and tuple(h.kind for h in probe.hazards) == ("scripted",)
    assert world.object_blockers[15] == frozenset({(2, 2)}) and start.occupied
    assert all(not b for b in preview.object_blockers.values())
    assert preview.local_graphs[15][0] == "requirements-retained"


@pytest.mark.parametrize("present", [True, False])
def test_preview_does_not_erase_unresolved_one_off_encounters(monkeypatch, present):
    from pokemon_red_completion import red_story_map_frontier as m

    @dataclass
    class World:
        rom: bytes
        object_blockers: dict
        terrain: dict
        local_graphs: dict

        def _graph_for_terrain(self, terrain):
            return self.object_blockers[terrain]

    m._static_capture_locations.cache_clear()
    monkeypatch.setattr(m, "static_encounters", lambda _: (N(map_id=27, at=(10, 26)),))
    occupied = frozenset({(10, 26), (3, 3)}) if present else frozenset({(3, 3)})
    world = World(b"test", {27: occupied}, {27: 27}, {27: occupied})
    start = TraversalSnapshot(map_id=27, at=(10, 27), ready=True, mode="land",
                              occupied=occupied)
    preview, probe = m.story_object_preview(world, start)
    expected = frozenset({(10, 26)}) if present else frozenset()
    assert preview.object_blockers[27] == preview.local_graphs[27] == expected
    assert probe.occupied == expected
    assert world.object_blockers[27] == occupied
    m._static_capture_locations.cache_clear()


def test_frontier_relevance_never_executes_hypothetical_route(monkeypatch):
    from test_red_player_story_travel import setup

    from pokemon_red_completion import red_player_story_travel as s
    from pokemon_red_completion.route_plan import RoutePlanningError

    rt, actions, route, raw, lesson = setup(monkeypatch)
    monkeypatch.setattr(s, "story_frontier_target", lambda *a: (59, (35, 14)))

    def blocked(start, destination, *, goal_at):
        assert (destination, goal_at) == (59, (35, 14))
        raise RoutePlanningError("actual trainer blocks passage")

    monkeypatch.setattr(
        type(route), "route_world", property(lambda _: N(plan_feasible_to_map=blocked))
    )
    assert (
        s.story_travel_binding(rt, actions, objective_id="reach_pewter", route=route, frontier=True)
        is None
    )
    assert actions.actions_executed == 0


@pytest.mark.parametrize("blocked", [False, True])
def test_shortest_corridor_failure_reuses_existing_search_without_changing_gates(blocked):
    calls = []

    @dataclass
    class World:
        object_blockers: dict
        terrain: dict
        local_graphs: dict

        def _graph_for_terrain(self, terrain):
            return ("story-gates-retained", terrain)

        def plan_feasible_to_map(self, start, destination):
            calls.append("cheap")
            raise RoutePlanningError("short corridor closed")

        def plan_to_map(self, start, destination):
            calls.append("complete")
            assert self.local_graphs[5][0] == "story-gates-retained"
            assert start.capabilities == frozenset({"move:cut"})
            assert start.occupied == frozenset({(4, 4)})
            assert tuple(h.kind for h in start.hazards) == ("scripted",)
            if blocked:
                raise RoutePlanningError("no legal route")
            return N(steps=(N(expected_map=17, expected_at=(0, 1)),))

    world = World({5: frozenset({(1, 1)})}, {5: "terrain"}, {5: "original"})
    start = TraversalSnapshot(
        map_id=5,
        at=(2, 2),
        ready=True,
        capabilities=frozenset({"move:cut"}),
        hazards=(TraversalHazard((4, 4), "scripted"), TraversalHazard((4, 5), "trainer_sight")),
    )
    if blocked:
        with pytest.raises(RoutePlanningError, match="no legal route"):
            story_frontier_target(world, start, 4)
    else:
        assert story_frontier_target(world, start, 4) == (17, (0, 1))
    assert calls == ["cheap", "complete"] and world.local_graphs[5] == "original"
