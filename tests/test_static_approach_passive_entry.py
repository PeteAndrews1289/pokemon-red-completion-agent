"""A proved automatic map-entry event never authorizes arbitrary story changes."""
from dataclasses import dataclass
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_static_approach as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome


def flags(*events):
    data = bytearray(256)
    for event in events:
        data[event // 8] |= 1 << (event % 8)
    return bytes(data)


@pytest.mark.parametrize("fault", [None, "no_defeat", "new_defeat", "different_room",
                                    "same_room", "reverse", "other_flag", "size",
                                    "missing", "wrong_type"])
def test_only_prior_defeat_and_forward_receptionist_entry_are_admitted(fault):
    before = N(map_id=207, event_flags=flags(1935))
    after = N(map_id=181, event_flags=flags(1935, 919))
    if fault == "no_defeat":
        before.event_flags, after.event_flags = flags(), flags(919)
    if fault == "new_defeat":
        before.event_flags = flags()
    if fault == "different_room":
        after.map_id = 207
    if fault == "same_room":
        before.map_id = 181
    if fault == "reverse":
        before.event_flags, after.event_flags = after.event_flags, before.event_flags
    if fault == "other_flag":
        after.event_flags = flags(1935, 919, 920)
    if fault == "size":
        after.event_flags += b"\0"
    if fault == "missing":
        before.event_flags = None
    if fault == "wrong_type":
        before.event_flags = list(before.event_flags)
    assert s._static_approach_events_preserved(before, after) is (fault is None)


@pytest.mark.parametrize("fault", [None, "cash", "bag", "party", "badge", "endpoint", "unready"])
def test_legitimate_passive_entry_still_requires_every_other_guard(monkeypatch, fault):
    raw = N(map_id=207, player_y=1, player_x=26, player_money=25295,
            bag_items=((1, 1),), party_species_ids=(151, 114), badge_bits=15,
            event_flags=flags(1935))
    emulator = N(state=b"source", frame_count=0)
    emulator.save_state_bytes = lambda: emulator.state
    actions = N(actions_executed=0)
    runtime = N(reader=N(read=lambda: N(**vars(raw))), emulator=emulator,
                adapter=N(observe=lambda: N(game_state=None), graph=N(
                    available_objectives=lambda _: (N(id="reach_static"),))))
    monkeypatch.setattr(s, "_field_ready", lambda _: not (fault == "unready" and emulator.frame_count))
    monkeypatch.setattr(s, "_origin", lambda *_: None)
    monkeypatch.setattr(s, "observe_static_capture", lambda *_: N(registered=False, consumed=False))

    @dataclass
    class Route:
        destination_map: int = 0
        destination_at: tuple = (0, 0)

        @property
        def route_world(self):
            return N(plan_feasible_to_map=lambda *_a, **_k: N(
                cost=4, terminal_at=(4, 4), steps=(object(),),
                segments=(N(target_map=181, transition=N(arrival_at=(1, 26))),)))

        def __call__(self, *_):
            raw.map_id = self.destination_map
            raw.player_y, raw.player_x = self.destination_at
            raw.event_flags = flags(1935, 919)
            if fault == "cash": raw.player_money += 1
            if fault == "bag": raw.bag_items = ()
            if fault == "party": raw.party_species_ids = (151,)
            if fault == "badge": raw.badge_bits = 31
            if fault == "endpoint": raw.player_x -= 1
            actions.actions_executed += 4
            emulator.frame_count += 192
            emulator.state = b"terminal"

    binding = s.static_approach_binding(runtime, actions, route=Route(),
        target=N(map_id=235, at=(4, 5)), objective_id="reach_static", battler=None)
    assert actions.actions_executed == 0
    if fault:
        with pytest.raises(ValueError): binding.execute()
    else:
        report = binding.execute()
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
        assert report.evidence["incidental_map_entry_events"] == ["silph_receptionist_returns_to_desk"]
        assert report.evidence["activated"] is False
        assert report.evidence["objective_completed"] is False
        assert report.evidence["automatic_objectives"] == []
        with pytest.raises(ValueError): binding.execute()
