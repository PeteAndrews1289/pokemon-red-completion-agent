import pytest
from types import SimpleNamespace as N

from test_red_player_story_fly import setup
from pokemon_red_completion import red_player_story_fly as fly


def test_feasible_onward_return_to_departure_leaves_ground_available(monkeypatch):
    runtime, actions, args, live, world, _, _ = setup(monkeypatch)
    live.visited = (0,)
    monkeypatch.setattr(fly, "story_frontier_plan", lambda w, start, end: N(
        macro_path=N(maps=(start.map_id, 18, args["start"].map_id, end)),
        steps=(N(expected_map=18, expected_at=(2, 2)),)))
    assert fly.story_fly_binding(runtime, actions, **args) is None
    assert live.calls == actions.actions_executed == 0
    assert live.plan_calls == []  # No execution quote for a known cyclic prefix.


def test_next_noncyclic_flight_remains_available(monkeypatch):
    runtime, actions, args, live, _, _, _ = setup(monkeypatch)
    monkeypatch.setattr(fly, "story_frontier_plan", lambda w, start, end: N(
        macro_path=N(maps=(start.map_id, 10, end) if start.map_id == 0 else (1, 7, end)),
        steps=(N(expected_map=7, expected_at=(2, 2)),)))
    binding = fly.story_fly_binding(runtime, actions, **args)
    assert binding is not None
    assert live.plan_calls[0][0].map_id == 1
    assert live.calls == actions.actions_executed == 0


def test_forward_flight_quote_unchanged(monkeypatch):
    runtime, actions, args, live, _, _, _ = setup(monkeypatch)
    binding = fly.story_fly_binding(runtime, actions, **args)
    assert binding is not None
    assert live.plan_calls[0][0].map_id == 0
    assert live.calls == actions.actions_executed == 0


@pytest.mark.parametrize("returned_map,rejected", [(10, True), (172, False), (18, False)])
def test_indoor_guard_uses_actual_outdoor_departure(monkeypatch, returned_map, rejected):
    from test_red_player_story_fly import indoor_setup
    runtime, actions, args, live, _, _, _ = indoor_setup(monkeypatch)
    monkeypatch.setattr(fly,"story_frontier_plan",lambda w,start,end:N(
        macro_path=N(maps=(1,returned_map,end)),
        steps=(N(expected_map=7,expected_at=(2,2)),)))
    binding=fly.story_fly_binding(runtime,actions,**args)
    assert (binding is None) is rejected
    assert actions.actions_executed == live.calls == live.walk_calls == 0
