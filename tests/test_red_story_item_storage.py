from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion import red_story_item_storage as storage
from pokemon_red_completion.observation import EventFlag, ItemId, RawGameState


@pytest.mark.parametrize("fault", [None, "unearned", "pc_full", "pc_stack_full",
                                      "lost", "extra", "cash", "party", "field"])
def test_storage_conserves_items_and_protected_state(monkeypatch, fault):
    events = bytearray(256)
    for event in (EventFlag.GOT_MASTER_BALL, EventFlag.BEAT_SABRINA):
        events[int(event) // 8] |= 1 << (int(event) % 8)
    if fault == "unearned":
        events = bytearray(256)
    bag = ((int(ItemId.SILPH_SCOPE), 1), (int(ItemId.CARD_KEY), 1), (1, 1), (4, 3))
    raw = [RawGameState(True, 182, 3, 3, 2, 0, event_flags=bytes(events),
                        bag_items=bag, player_money=16459)]
    pc = {2: 1}
    if fault == "pc_full":
        pc = {i: 1 for i in range(100, 150)}
    elif fault == "pc_stack_full":
        pc[int(ItemId.CARD_KEY)] = 99
    calls = []

    def store(*args):
        calls.append(True)
        for item in storage.sabrina.PC_DEPOSIT_ITEMS:
            if fault != "lost":
                pc[int(item)] = pc.get(int(item), 0) + 1
        kept = tuple(row for row in bag if row[0] not in storage.sabrina.PC_DEPOSIT_ITEMS)
        raw[0] = replace(raw[0], bag_items=kept)
        if fault == "extra":
            raw[0] = replace(raw[0], bag_items=())
        elif fault == "cash":
            raw[0] = replace(raw[0], player_money=0)
        elif fault == "party":
            raw[0] = replace(raw[0], party_hp=(1,))
        elif fault == "field":
            raw[0] = replace(raw[0], player_x=4)

    monkeypatch.setattr(storage.sabrina, "_store_obsolete_key_items", store)
    reader = NS(read=lambda: raw[0], read_pc_items=lambda: tuple(pc.items()),
                read_input_readiness=lambda: NS(ready=True))
    if fault:
        with pytest.raises((ValueError, RuntimeError)):
            storage.archive_completed_story_keys(NS(), reader, NS())
        if fault in {"unearned", "pc_full", "pc_stack_full"}:
            assert not calls
    else:
        result = storage.archive_completed_story_keys(NS(), reader, NS())
        assert result["bag_stacks_after"] == 2
        assert pc[int(ItemId.CARD_KEY)] == pc[int(ItemId.SILPH_SCOPE)] == 1


@pytest.mark.parametrize("indigo", (False, True))
@pytest.mark.parametrize("fault", (None, "pc_tile", "cash", "item", "stale"))
def test_routed_keys_use_verified_indigo_pc_and_conserve_every_asset(monkeypatch, indigo, fault):
    from dataclasses import dataclass, field

    events = bytearray(320)
    for event in (EventFlag.GOT_MASTER_BALL, EventFlag.BEAT_ROCKET_HIDEOUT_GIOVANNI):
        events[int(event) // 8] |= 1 << (int(event) % 8)
    bag = (((int(ItemId.CARD_KEY), 1), (int(ItemId.LIFT_KEY), 1))
           + tuple((i, 1) for i in range(80, 98)))
    raw = [RawGameState(True, 174, 7, 7, 2, 0, event_flags=bytes(events),
                       bag_items=bag, player_money=6258)]
    state, pc, quoted = [b"source"], {}, []
    lobby_tiles = [[0] * 16 for _ in range(12)]
    lobby_tiles[7][15] = 0 if fault == "pc_tile" else 0x52
    center_tiles = [[0] * 14 for _ in range(8)]
    center_tiles[3][13] = 0x52
    terrain = {174: NS(tiles=lobby_tiles, walkable=[[True] * 16 for _ in range(12)]),
               182: NS(tiles=center_tiles)}

    def plan(_start, mid, *, goal_at):
        quoted.append((mid, goal_at))
        return NS(cost=1 if mid == 174 else 100, terminal_map=mid, terminal_at=goal_at)
    world = NS(terrain=terrain, plan_feasible_to_map=plan)
    @dataclass
    class Route:
        rom: bytes = b"rom"
        route_world: object = field(default_factory=lambda: world)
        destination_map: int = 174
        destination_at: tuple = (7, 7)

        def __call__(self, *_):
            raw[0] = replace(raw[0], map_id=self.destination_map,
                             player_y=self.destination_at[0], player_x=self.destination_at[1])
            state[0] = b"arrived"

    def deposit(_a, _r, _e, item, _timing):
        if fault != "item":
            pc[int(item)] = pc.get(int(item), 0) + 1
        raw[0] = replace(raw[0], bag_items=tuple(row for row in raw[0].bag_items if row[0] != item),
                         player_money=0 if fault == "cash" else raw[0].player_money)
        state[0] = b"deposited"
    monkeypatch.setattr(storage, "_field_ready", lambda _: True)
    monkeypatch.setattr(storage, "Gen1TraversalObserver", lambda *a, **k: NS(observe=lambda: NS()))
    monkeypatch.setattr(storage, "Gen1TrainerSightProjector", lambda *a, **k: None)
    monkeypatch.setattr(storage, "certified_cash_safe_transition", lambda *a: None)
    monkeypatch.setattr(storage.sabrina, "_deposit_pc_item", deposit)
    em = NS(frame_count=0, save_state_bytes=lambda: state[0])
    reader = NS(read=lambda: raw[0], read_pc_items=lambda: tuple(pc.items()),
                read_all_box_states=lambda: (), read_pokedex_state=lambda: ())
    rt, actions = NS(reader=reader, emulator=em), NS(actions_executed=0)
    binding = storage.completed_key_storage_binding(rt, actions, route=Route(),
        include_indigo_lobby=indigo)
    assert binding is not None
    expected = ((174, (8, 15)) if indigo and fault != "pc_tile"
                else (min(storage._POKEMON_CENTER_MAPS), (4, 13)))
    if fault == "stale":
        state[0] = b"different"
        with pytest.raises(ValueError, match="stale"):
            binding.execute()
        assert not pc
    elif fault in ("cash", "item"):
        with pytest.raises(RuntimeError, match="conserve exact"):
            binding.execute()
    else:
        report = binding.execute()
        assert (raw[0].map_id, (raw[0].player_y, raw[0].player_x)) == expected
        assert ((174, (8, 15)) in quoted) is (indigo and fault != "pc_tile")
        assert len(raw[0].bag_items) == 18 and raw[0].player_money == 6258
        assert pc == {int(ItemId.CARD_KEY): 1, int(ItemId.LIFT_KEY): 1}
        assert binding.verify(report).status.value == "succeeded"


def test_indigo_storage_permission_requires_a_boolean():
    with pytest.raises(TypeError, match="explicit boolean"):
        storage.completed_key_storage_binding(None, None, route=None, include_indigo_lobby=1)


@pytest.mark.parametrize("permission,badges", ((False, 255), (True, 127), (True, 255)))
@pytest.mark.parametrize('spare', [ItemId.TM34_BIDE, ItemId.TM06_TOXIC])
def test_medical_capacity_preserves_hms_and_consumables(permission, badges, spare):
    bag = (((int(spare), 1), (int(ItemId.TM24_THUNDERBOLT), 1),
            (int(ItemId.MASTER_BALL), 1), (int(ItemId.HM03_SURF), 1))
           + tuple((i, 1) for i in range(80, 96)))
    raw = NS(bag_items=bag, event_flags=bytes(320), badge_bits=badges)
    selected = storage.completed_key_capacity_items(raw, allow_spare_tm_storage=permission)
    assert selected == ((int(spare),) if permission and badges == 255 else ())
    with pytest.raises(TypeError, match="explicit boolean"):
        storage.completed_key_capacity_items(raw, allow_spare_tm_storage=1)
