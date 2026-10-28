from dataclasses import dataclass, replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_story_item_storage as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.observation import EventFlag, ItemId, RawGameState


def source():
    flags = bytearray(256)
    for event in (
        EventFlag.GOT_MASTER_BALL,
        EventFlag.BEAT_ROCKET_HIDEOUT_GIOVANNI,
        EventFlag.GOT_HM01,
    ):
        flags[int(event) // 8] |= 1 << (int(event) % 8)
    keys = ((int(ItemId.CARD_KEY), 1), (int(ItemId.LIFT_KEY), 1), (int(ItemId.SS_TICKET), 1))
    bag = keys + tuple((i, 1) for i in range(100, 117))
    return RawGameState(
        True,
        8,
        10,
        0,
        0,
        0,
        event_flags=bytes(flags),
        bag_items=bag,
        player_money=14000,
        party_species_ids=(28,),
        party_levels=(47,),
    )


@pytest.mark.parametrize("slots", [False, True, 0, 21, 1.0, "2"])
def test_reserve_is_a_strict_bounded_integer(slots):
    with pytest.raises(ValueError, match="reserved"):
        s.completed_key_capacity_items(source(), reserved_slots=slots)


def test_only_native_completed_keys_are_selected_and_reusable_tools_are_retained():
    raw = source()
    assert s.completed_key_capacity_items(raw) == (48, 74)
    assert s.completed_key_capacity_items(replace(raw, event_flags=bytes(256))) == ()
    assert s.completed_key_capacity_items(replace(raw, bag_items=None)) == ()
    assert s.completed_key_capacity_items(replace(raw, event_flags=None)) == ()
    assert s.completed_key_capacity_items(replace(raw, bag_items=raw.bag_items[:-2])) == ()
    tools = tuple(
        (int(item), 1)
        for item in (
            ItemId.SILPH_SCOPE,
            ItemId.POKE_FLUTE,
            ItemId.HM01_CUT,
            ItemId.HM03_SURF,
            ItemId.HM04_STRENGTH,
        )
    )
    raw = replace(raw, bag_items=tools + raw.bag_items[3:18])
    assert len(raw.bag_items) == 20 and s.completed_key_capacity_items(raw) == ()


def fixture(monkeypatch, *, fault=None):
    state = N(
        raw=source(),
        payload=b"source",
        ready=True,
        pc={2: 1},
        deposits=[],
        boxes=("box",),
        dex=("owned",),
    )
    if fault == "unready":
        state.ready = False
    elif fault == "unearned":
        state.raw = replace(state.raw, event_flags=bytes(256))
    elif fault == "pc_full":
        state.pc = {i: 1 for i in range(100, 150)}
    elif fault == "pc_stack":
        state.pc[48] = 99

    @dataclass
    class Route:
        route_world: object
        rom: bytes = b"rom"
        allow_surf: bool = True
        destination_map: int = 182
        destination_at: tuple = (4, 13)

        def __call__(self, actions, reader, emulator):
            assert self.destination_map == 182 and self.destination_at == (4, 13)
            state.raw = replace(state.raw, map_id=182, player_y=4, player_x=13)
            if fault == "approach_cash":
                state.raw = replace(state.raw, player_money=0)
            state.payload = b"at-pc"
            actions.actions_executed += 1
            emulator.frame_count += 10

    def plan(*args, **kwargs):
        assert kwargs["goal_at"] == (4, 13)
        if fault == "no_route":
            raise s.RoutePlanningError("blocked")
        if fault == "quote_mutated":
            state.payload = b"mutated"
        return N(cost=5, terminal_map=182, terminal_at=kwargs["goal_at"])

    reader = N(
        read=lambda: state.raw,
        read_pc_items=lambda: tuple(state.pc.items()),
        read_all_box_states=lambda: state.boxes,
        read_pokedex_state=lambda: state.dex,
    )
    em = N(frame_count=0, save_state_bytes=lambda: state.payload)
    rt, actions = N(reader=reader, emulator=em), N(actions_executed=0)
    monkeypatch.setattr(s, "_field_ready", lambda _: state.ready)
    monkeypatch.setattr(s, "_POKEMON_CENTER_MAPS", frozenset({182}))
    monkeypatch.setattr(s, "Gen1TrainerSightProjector", lambda *a, **k: None)
    monkeypatch.setattr(s, "Gen1TraversalObserver", lambda *a, **k: N(observe=lambda: N()))
    monkeypatch.setattr(s, "certified_cash_safe_transition", lambda route, *a: route)

    def deposit(actions, reader, emulator, item, timing):
        state.deposits.append(int(item))
        bag = dict(state.raw.bag_items)
        amount = bag.pop(int(item))
        if fault != "lost":
            state.pc[int(item)] = state.pc.get(int(item), 0) + amount
        state.raw = replace(state.raw, bag_items=tuple(bag.items()))
        if fault == "extra":
            state.raw = replace(state.raw, bag_items=())
        elif fault == "cash":
            state.raw = replace(state.raw, player_money=0)
        elif fault == "party":
            state.raw = replace(state.raw, party_hp=(1,))
        elif fault == "xp":
            state.raw = replace(state.raw, party_levels=(48,))
        elif fault == "dex":
            state.dex = ("different",)
        elif fault == "boxes":
            state.boxes = ("different",)
        elif fault == "events":
            state.raw = replace(state.raw, event_flags=bytes(256))
        elif fault == "field":
            state.ready = False
        state.payload = b"deposit-" + str(len(state.deposits)).encode()
        actions.actions_executed += 1
        em.frame_count += 10

    monkeypatch.setattr(s.sabrina, "_deposit_pc_item", deposit)
    return rt, actions, Route(N(plan_feasible_to_map=plan)), state


@pytest.mark.parametrize("fault", ["unready", "unearned", "pc_full", "pc_stack", "no_route"])
def test_unavailable_capacity_is_not_an_executable_option(monkeypatch, fault):
    rt, actions, route, state = fixture(monkeypatch, fault=fault)
    assert s.completed_key_storage_binding(rt, actions, route=route) is None
    assert actions.actions_executed == rt.emulator.frame_count == 0 and not state.deposits


@pytest.mark.parametrize("certificate", [True, False])
def test_capacity_goal_conserves_assets_and_never_claims_a_story_reward(monkeypatch, certificate):
    rt, actions, route, state = fixture(monkeypatch)
    if not certificate:
        monkeypatch.setattr(s, "certified_cash_safe_transition", lambda *args: None)
    before = state.raw.bag_items
    binding = s.completed_key_storage_binding(rt, actions, route=route)
    assert binding.kind is GoalKind.MANAGE_STORAGE and binding.maximum_cash_debit == 0
    assert actions.actions_executed == rt.emulator.frame_count == 0
    report = binding.execute()
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert state.deposits == [48, 74] and len(state.raw.bag_items) == 18
    assert dict(state.raw.bag_items) | {48: 1, 74: 1} == dict(before)
    assert state.pc == {2: 1, 48: 1, 74: 1}
    assert not report.evidence["learned_item_selection"] and report.evidence["sales"] == 0
    assert "objective_completed" not in report.evidence
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()
    state.payload = b"changed-after-verification"
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED


@pytest.mark.parametrize(
    "fault",
    [
        "stale",
        "quote_mutated",
        "approach_cash",
        "lost",
        "extra",
        "cash",
        "party",
        "xp",
        "dex",
        "boxes",
        "events",
        "field",
    ],
)
def test_unsafe_storage_fails_without_fabricating_capacity(monkeypatch, fault):
    rt, actions, route, state = fixture(monkeypatch, fault=fault)
    if fault == "quote_mutated":
        with pytest.raises(ValueError, match="quotation"):
            s.completed_key_storage_binding(rt, actions, route=route)
        return
    binding = s.completed_key_storage_binding(rt, actions, route=route)
    if fault == "stale":
        state.payload = b"stale"
    with pytest.raises((ValueError, RuntimeError)):
        binding.execute()
    if fault in {"stale", "approach_cash"}:
        assert not state.deposits
