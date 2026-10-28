"""A partial frontier must never be dispatched as the distant static target."""
from dataclasses import dataclass
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_static_approach as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome


@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("continuous", [False, True])
@pytest.mark.parametrize("descriptor", [False, True])
def test_same_map_frontier_uses_quoted_endpoint_and_declines_zero_work(
    monkeypatch, empty, continuous, descriptor,
):
    raw = N(map_id=207, player_y=1, player_x=26, player_money=26389,
        bag_items=((73, 1),), party_species_ids=(151, 114),
        event_flags=b"unchanged", badge_bits=15)
    emulator = N(frame_count=0, state=b"actual-before")
    emulator.save_state_bytes = lambda: emulator.state
    inputs, diagnostics, planned = [], [], []
    actions = N(actions_executed=0,
        record_diagnostic_event=lambda kind, payload: diagnostics.append((kind, payload)))
    runtime = N(reader=N(read=lambda: N(**vars(raw))), emulator=emulator,
        adapter=N(observe=lambda: N(game_state=None), graph=N(
            available_objectives=lambda _: (N(id="reach_fuchsia"),))))
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "_origin", lambda *_: object())
    monkeypatch.setattr(s, "observe_static_capture", lambda *_: N(registered=False, consumed=False))
    endpoint = (1 if empty else 2, 26)
    monkeypatch.setattr(s, "story_frontier_target", lambda *_: (207, endpoint))

    @dataclass
    class Route:
        destination_map: int = 0
        destination_at: tuple = (0, 0)

        @property
        def route_world(self):
            def plan(origin, map_id, *, goal_at):
                planned.append((map_id, goal_at))
                if map_id != 207:
                    raise s.RoutePlanningError("future map target not currently quoted")
                return N(cost=0 if empty else 1, terminal_at=endpoint,
                    steps=() if empty else (N(expected_map=207, expected_at=endpoint),),
                    segments=())
            return N(plan_feasible_to_map=plan)

        def __call__(self, *_):
            assert self.destination_map == 207, "must not dispatch toward a future map"
            assert self.destination_at == endpoint
            inputs.append((self.destination_map, self.destination_at))
            actions.actions_executed += 1
            emulator.frame_count += 16
            emulator.state = b"quoted-terminal"
            raw.player_y, raw.player_x = self.destination_at

    fn = s.static_approach_option if descriptor else s.static_approach_binding
    result = fn(runtime, actions, route=Route(), target=N(map_id=23, at=(62, 10)),
        objective_id="reach_fuchsia", battler=None, continuous_travel=continuous,
        **({"combat_levels": (58, 33)} if descriptor else {}))
    assert not inputs and emulator.frame_count == 0
    assert planned[-1] == (207, endpoint)
    if empty:
        assert result is None
        assert diagnostics[0][0] == "static_approach_quote"
        assert diagnostics[0][1]["reason"] == "no_executable_frontier_steps"
        assert diagnostics[0][1]["controller_inputs"] == 0
        assert emulator.state == b"actual-before"
    else:
        binding = result[0] if descriptor else result
        report = binding.execute()
        assert inputs == [(207, endpoint)] and raw.map_id == 207
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
        assert not report.evidence["activated"] and not report.evidence["objective_completed"]


@pytest.mark.parametrize("explicit_later_step", [False, True])
def test_implicit_stair_arrival_precedes_walking_on_the_next_map(monkeypatch, explicit_later_step):
    raw = N(map_id=207, player_y=1, player_x=26, player_money=26389,
        bag_items=(), party_species_ids=(151,), event_flags=b"same", badge_bits=15)
    em = N(frame_count=0, state=b"before")
    em.save_state_bytes = lambda: em.state
    actions = N(actions_executed=0)
    runtime = N(reader=N(read=lambda: N(**vars(raw))), emulator=em,
        adapter=N(observe=lambda: N(game_state=None), graph=N(
            available_objectives=lambda _: (N(id="reach_fuchsia"),))))
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "_origin", lambda *_: object())
    monkeypatch.setattr(s, "observe_static_capture", lambda *_: N(registered=False, consumed=False))
    monkeypatch.setattr(s, "story_frontier_target", lambda *_: (181, (1, 26)))

    @dataclass
    class Route:
        destination_map: int = 0
        destination_at: tuple = (0, 0)
        @property
        def route_world(self):
            def plan(origin, map_id, *, goal_at):
                if map_id != 181:
                    raise s.RoutePlanningError("future map occupancy")
                return N(cost=1, terminal_at=(1, 26),
                    steps=(N(expected_map=181, expected_at=(2, 26)),) if explicit_later_step else (),
                    segments=(N(target_map=181, transition=N(arrival_at=(1, 26))),))
            return N(plan_feasible_to_map=plan)
        def __call__(self, *_):
            assert (self.destination_map, self.destination_at) == (181, (1, 26))
            raw.map_id = 181
            actions.actions_executed += 4
            em.frame_count += 192
            em.state = b"arrived"
    binding = s.static_approach_binding(runtime, actions, route=Route(),
        target=N(map_id=23, at=(62, 10)), objective_id="reach_fuchsia", battler=None)
    assert binding is not None and not actions.actions_executed
    report = binding.execute()
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert raw.map_id == 181 and (raw.player_y, raw.player_x) == (1, 26)
    assert report.actions_executed == 4 and not report.evidence["activated"]
