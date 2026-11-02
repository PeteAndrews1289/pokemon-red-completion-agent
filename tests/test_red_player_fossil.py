from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.red_player_fossil import fossil_pending


def setup_binding(monkeypatch, fault=None):
    from copy import deepcopy
    from dataclasses import dataclass

    from pokemon_red_completion import red_player_fossil as s
    from pokemon_red_completion.actions import MacroActionKind

    flags = bytearray(256)
    flags[1401 // 8] |= 1 << (1401 % 8)
    raw = N(
        map_id=61,
        event_flags=bytes(flags),
        bag_items=((4, 5),),
        battle_state=0,
        party_species_ids=(179,),
        player_money=427,
        badge_bits=1,
    )
    state = N(payload=b"source", ready=True)
    objects = tuple(N(object_index=i, sprite_id=62, at=(6, i + 6), map_id=61) for i in (6, 7))
    live = tuple(N(sprite_index=o.object_index, picture_id=o.sprite_id, at=o.at) for o in objects)
    rt = N(
        reader=N(
            read=lambda: raw, read_current_map_objects=lambda: () if fault == "moved" else live
        ),
        emulator=N(frame_count=0, save_state_bytes=lambda: state.payload),
    )
    actions = N(actions_executed=0)
    monkeypatch.setattr(s, "_field_ready", lambda _: state.ready)
    monkeypatch.setattr(s, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(s, "map_object_events", lambda *a: objects)
    monkeypatch.setattr(
        s,
        "capture_player_lesson_snapshot",
        lambda _: (N(raw=deepcopy(raw)), {"completed_objectives": ["defeat_brock"]}),
    )
    monkeypatch.setattr(s, "Gen1TrainerSightProjector", lambda *a, **k: None)
    monkeypatch.setattr(s, "Gen1TraversalObserver", lambda *a, **k: N(observe=lambda: None))
    monkeypatch.setattr(s, "face_pc_boundary", lambda *a: None)

    @dataclass
    class Route:
        rom: bytes = b"rom"
        destination_map: int = 61
        destination_at: tuple = (7, 12)

        @property
        def route_world(self):
            return N(plan_feasible_to_map=lambda *a, **k: N(cost=20, terminal_at=(7, 12)))

        def __call__(self, *args):
            actions.actions_executed += 1
            rt.emulator.frame_count += 16

    def act(action):
        actions.actions_executed += 1
        rt.emulator.frame_count += 24
        if action.kind is MacroActionKind.INTERACT:
            events = bytearray(raw.event_flags)
            if fault != "event":
                events[1406 // 8] |= 1 << (1406 % 8)
            if fault == "both":
                events[1407 // 8] |= 1 << (1407 % 8)
            raw.event_flags = bytes(events)
            raw.bag_items = ((4, 5), (41, 1)) if fault != "reward" else ((4, 5),)
            if fault == "cash":
                raw.player_money -= 1
            if fault == "party":
                raw.party_species_ids = (1,)
            if fault == "badge":
                raw.badge_bits = 3
            state.payload = b"terminal"

    actions.execute = act
    return s, rt, actions, Route(), state


@pytest.mark.parametrize(
    "fault", [None, "moved", "event", "both", "reward", "cash", "party", "badge"]
)
def test_fossil_execution_proves_native_reward_and_is_single_use(monkeypatch, fault):
    from pokemon_red_completion.goal_manager import GoalDecisionOutcome

    s, rt, actions, route, state = setup_binding(monkeypatch, fault)
    binding = s.fossil_pickup_binding(rt, actions, route=route)
    assert actions.actions_executed == 0
    if fault:
        with pytest.raises(ValueError):
            binding.execute()
    else:
        report = binding.execute()
        assert not report.evidence["objective_completed"]
        assert not report.evidence["learned_fossil_choice"]
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
        with pytest.raises(ValueError, match="consumed"):
            binding.execute()
        state.payload = b"changed"
        assert binding.verify(report).status is GoalDecisionOutcome.FAILED


def test_stale_fossil_offer_never_acts(monkeypatch):
    s, rt, actions, route, state = setup_binding(monkeypatch)
    binding = s.fossil_pickup_binding(rt, actions, route=route)
    state.payload = b"changed"
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    assert actions.actions_executed == 0


@pytest.mark.parametrize(
    "fault", [None, "map", "guard", "taken", "bag", "full", "missing", "short"]
)
def test_fossil_offer_requires_native_guard_reward_and_capacity(fault):
    events = bytearray(256)
    if fault != "guard":
        events[1401 // 8] |= 1 << (1401 % 8)
    if fault == "taken":
        events[1406 // 8] |= 1 << (1406 % 8)
    bag = () if fault != "bag" else ((41, 1),)
    if fault == "full":
        bag = tuple((i, 1) for i in range(1, 21))
    if fault == "missing":
        events = None
    if fault == "short":
        events = bytes(1)
    assert fossil_pending(
        N(map_id=61 if fault != "map" else 60, event_flags=events, bag_items=bag)
    ) is (fault is None)
