from dataclasses import dataclass
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_field_item as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.local_router import LocalEdge, LocalGraph, without_coordinates
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError


def fixture(monkeypatch):
    raw = N(map_id=10, bag_items=(), ready=True)
    state = N(payload=b"source", present=True, moving=False, picture=61, pickup_fail=False)
    item = N(is_item=True, is_trainer=False, extra=(40,), sprite=61, y=1, x=2)
    graph = LocalGraph(
        {
            (1, x): tuple(
                LocalEdge((1, n), "right" if n > x else "left")
                for n in (x - 1, x + 1)
                if 0 <= n <= 4
            )
            for x in range(5)
        }
    )
    calls = []

    @dataclass
    class World:
        local_graphs: dict
        object_blockers: dict
        terrain: dict

        def with_current_observation(self, reader):
            return self

        def _graph_for_terrain(self, terrain):
            return without_coordinates(graph, self.object_blockers[10])

        def plan_feasible_to_map(self, origin, map_id, *, goal_at):
            seen, pending = {origin.at}, [origin.at]
            while pending:
                at = pending.pop()
                for edge in self.local_graphs[map_id].neighbors(at):
                    if edge.target not in seen and edge.target not in origin.occupied:
                        seen.add(edge.target)
                        pending.append(edge.target)
            if goal_at not in seen:
                raise RoutePlanningError("blocked")
            return N(cost=abs(goal_at[1] - origin.at[1]), terminal_at=goal_at)

    @dataclass
    class Route:
        route_world: World
        rom: bytes = b"rom"
        destination_map: int = 10
        destination_at: tuple = (1, 0)

        def __call__(self, actions, reader, emulator):
            # Pickup must use original occupancy, not its hypothetical removal.
            assert (1, 2) in self.route_world.object_blockers[10]
            assert (1, 2) not in self.route_world.local_graphs[10].edges
            calls.append(self.destination_at)
            actions.actions_executed += 1
            emulator.frame_count += 10
            state.payload = b"approached"

    world = World({10: without_coordinates(graph, {(1, 2)})}, {10: frozenset({(1, 2)})}, {10: None})

    def live():
        return (
            [N(sprite_index=1, moving=state.moving, picture_id=state.picture, at=(1, 2))]
            if state.present
            else []
        )

    rt = N(
        reader=N(read=lambda: raw, read_current_map_objects=live),
        emulator=N(frame_count=0, save_state_bytes=lambda: state.payload),
    )
    actions = N(actions_executed=0)
    monkeypatch.setattr(s, "_field_ready", lambda runtime: raw.ready)
    monkeypatch.setattr(s, "map_objects", lambda rom: {10: (item,)})
    monkeypatch.setattr(s, "Gen1TrainerSightProjector", lambda *a, **k: None)
    monkeypatch.setattr(
        s,
        "Gen1TraversalObserver",
        lambda *a, **k: N(
            observe=lambda: TraversalSnapshot(
                map_id=10, at=(1, 0), ready=True, occupied=frozenset({(1, 2)})
            )
        ),
    )
    monkeypatch.setattr(s, "face_pc_boundary", lambda *a: None)

    def collect(actions, reader, target):
        assert calls == [(1, 1)] and target.item_id == 40
        if state.pickup_fail:
            raise RuntimeError("native pickup failed")
        state.payload = b"collected"
        actions.actions_executed += 1
        rt.emulator.frame_count += 10

    monkeypatch.setattr(s, "collect_visible_field_item", collect)
    return rt, actions, Route(world), raw, state, item, calls


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "unready",
        "unknown_bag",
        "full_bag",
        "full_stack",
        "absent",
        "moving",
        "wrong_sprite",
        "trainer",
        "forbidden_item",
        "forbidden_passage",
    ],
)
def test_only_reachable_native_item_obstructions_are_offered(monkeypatch, fault):
    rt, actions, route, raw, state, item, calls = fixture(monkeypatch)
    if fault == "unready":
        raw.ready = False
    if fault == "unknown_bag":
        raw.bag_items = None
    if fault == "full_bag":
        raw.bag_items = tuple((n, 1) for n in range(1, 21))
    if fault == "full_stack":
        raw.bag_items = ((40, 99),)
    if fault == "absent":
        state.present = False
    if fault == "moving":
        state.moving = True
    if fault == "wrong_sprite":
        state.picture = 25
    if fault == "trainer":
        item.is_trainer = True
    forbidden = (
        {(1, 2)}
        if fault == "forbidden_item"
        else {(1, 3)}
        if fault == "forbidden_passage"
        else set()
    )
    binding = s.blocking_field_item_binding(
        rt, actions, route=route, destination_at=(1, 4), forbidden=forbidden
    )
    assert not calls and state.payload == b"source" and rt.emulator.frame_count == 0
    assert (binding is not None) is (fault is None)


@pytest.mark.parametrize("fault", [None, "stale", "pickup_fail", "terminal_changed"])
def test_original_route_native_pickup_and_single_use(monkeypatch, fault):
    rt, actions, route, raw, state, item, calls = fixture(monkeypatch)
    binding = s.blocking_field_item_binding(rt, actions, route=route, destination_at=(1, 4))
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED
    if fault == "stale":
        state.payload = b"different"
        with pytest.raises(ValueError, match="stale"):
            binding.execute()
        assert not calls
        return
    state.pickup_fail = fault == "pickup_fail"
    if fault == "pickup_fail":
        with pytest.raises(RuntimeError, match="native pickup failed"):
            binding.execute()
        assert binding.verify(None).status is GoalDecisionOutcome.FAILED
    else:
        report = binding.execute()
        assert report.actions_executed == 2 and report.frames_executed == 20
        assert report.evidence["learned"] is False
        if fault == "terminal_changed":
            state.payload = b"changed"
        assert binding.verify(report).status is (
            GoalDecisionOutcome.FAILED
            if fault == "terminal_changed"
            else GoalDecisionOutcome.SUCCEEDED
        )
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


def test_no_pickup_when_destination_already_reachable(monkeypatch):
    rt, actions, route, *_ = fixture(monkeypatch)
    assert s.blocking_field_item_binding(rt, actions, route=route, destination_at=(1, 1)) is None
