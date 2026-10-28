from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_scripted_story_trainer as s


@pytest.mark.parametrize(
    "fault",
    [None, "map", "battle", "object", "position", "dialogue", "bridge", "defeated", "short"],
)
def test_nugget_introduction_is_exact_but_does_not_invent_its_reward(monkeypatch, fault):
    monkeypatch.setattr(s, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(
        s,
        "map_object_events",
        lambda *a: (
            N(
                object_index=1,
                trainer_class=230,
                trainer_set=7 if fault == "object" else 6,
                movement=255,
                y=15,
                x=11,
            ),
        ),
    )
    monkeypatch.setattr(s, "trainer_party_quote", lambda *a: N(expected_victory_money=450))
    flags = bytearray(320)
    for event in range(
        int(s.EventFlag.BEAT_ROUTE_24_TRAINER_1), int(s.EventFlag.BEAT_ROUTE_24_TRAINER_5) + 1
    ):
        if fault != "bridge" or event != int(s.EventFlag.BEAT_ROUTE_24_TRAINER_5):
            flags[event // 8] |= 1 << (event % 8)
    if fault == "defeated":
        event = int(s.EventFlag.BEAT_ROUTE_24_ROCKET)
        flags[event // 8] |= 1 << (event % 8)
    raw = N(
        map_id=3 if fault == "map" else 35,
        battle_state=2 if fault == "battle" else 0,
        player_y=14 if fault == "position" else 15,
        player_x=10,
        event_flags=bytes(1) if fault == "short" else bytes(flags),
    )
    reader = N(read=lambda: raw, read_bottom_dialogue_box_visible=lambda: fault != "dialogue")
    if fault == "object":
        with pytest.raises(ValueError, match="cartridge object"):
            s.nugget_rocket_introduction_contract(b"rom", reader)
    else:
        contract = s.nugget_rocket_introduction_contract(b"rom", reader)
        assert (contract is not None) == (fault is None)
        if contract is not None:
            assert contract.trainer_identity == (230, 30, 6) and contract.victory_items == ()
            assert not s.event_flag_is_set(raw.event_flags, int(s.EventFlag.GOT_NUGGET))


@pytest.mark.parametrize("fault", [None, "reward", "bag", "identity", "ready", "movement", "bridge", "defeated"])
def test_nugget_post_reward_movement_handoff_requires_all_native_evidence(monkeypatch, fault):
    monkeypatch.setattr(s, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(s, "map_object_events", lambda *a:(N(object_index=1,
        trainer_class=230,trainer_set=6,movement=255,y=15,x=11),))
    monkeypatch.setattr(s,"trainer_party_quote",lambda *a:N(expected_victory_money=450))
    flags=bytearray(320)
    for event in (s.EventFlag.BEAT_ROUTE_24_TRAINER_1,s.EventFlag.BEAT_ROUTE_24_TRAINER_2,
                  s.EventFlag.BEAT_ROUTE_24_TRAINER_3,s.EventFlag.BEAT_ROUTE_24_TRAINER_4,
                  s.EventFlag.BEAT_ROUTE_24_TRAINER_5,s.EventFlag.GOT_NUGGET):
        if (fault=="reward" and event==s.EventFlag.GOT_NUGGET) or (fault=="bridge" and event==s.EventFlag.BEAT_ROUTE_24_TRAINER_5):
            continue
        flags[int(event)//8] |= 1 << (int(event)%8)
    if fault=="defeated":
        flags[int(s.EventFlag.BEAT_ROUTE_24_ROCKET)//8] |= 1 << (int(s.EventFlag.BEAT_ROUTE_24_ROCKET)%8)
    raw=N(map_id=35,battle_state=0,player_y=15,player_x=10,event_flags=bytes(flags),
        bag_items=() if fault=="bag" else ((int(s.ItemId.NUGGET),1),))
    reader=N(read=lambda:raw,read_bottom_dialogue_box_visible=lambda:False,
        read_trainer_battle_identity=lambda:(230,30,230,7 if fault=="identity" else 6),
        read_input_readiness=lambda:N(ready=fault=="ready",player_moving_direction=0 if fault=="movement" else 8))
    contract=s.nugget_rocket_introduction_contract(b"rom",reader)
    assert (contract is not None) == (fault is None)


@pytest.mark.parametrize("starter,team", [(177, 4), (153, 5), (176, 6)])
@pytest.mark.parametrize("fault", [None, "map", "object", "identity", "event", "short", "starter"])
def test_tower_rival_exact_branch(monkeypatch, starter, team, fault):
    monkeypatch.setattr(s, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(
        s,
        "map_object_events",
        lambda *a: (N(object_index=1, sprite_id=3 if fault == "object" else 2, movement=255),),
    )

    def quote(rom, cls, number):
        assert (cls, number) == (242, team)
        return N(expected_victory_money=1625)

    monkeypatch.setattr(s, "trainer_party_quote", quote)
    flags = bytearray(320)
    if fault == "event":
        flags[239 // 8] |= 1 << (239 % 8)
    raw = N(
        map_id=144 if fault == "map" else 143,
        battle_state=2,
        event_flags=bytes(1) if fault == "short" else bytes(flags),
    )
    reader = N(
        read=lambda: raw,
        read_rival_starter=lambda: 0 if fault == "starter" else starter,
        read_active_trainer_identity=lambda: (242, 42, team + (fault == "identity")),
    )
    if fault:
        with pytest.raises(ValueError):
            s.tower_rival_contract(b"rom", reader)
    else:
        contract = s.tower_rival_contract(b"rom", reader)
        assert contract.defeated_event == 239 and contract.trainer_identity == (242, 42, team)
        assert contract.objective_id == "rescue_fuji"


@pytest.mark.parametrize("starter,team", [(177, 1), (153, 2), (176, 3)])
@pytest.mark.parametrize("fault", [None, "map", "script", "object", "identity"])
def test_ship_rival_exact_starter_and_room_contract(monkeypatch, starter, team, fault):
    monkeypatch.setattr(s, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(
        s,
        "map_object_events",
        lambda *a: (N(object_index=2, sprite_id=3 if fault == "object" else 2, movement=255),),
    )

    def quote(rom, trainer, number):
        assert (trainer, number) == (242, team)
        return N(expected_victory_money=1300)

    monkeypatch.setattr(s, "trainer_party_quote", quote)
    raw = N(map_id=95 if fault == "map" else 96, battle_state=2)
    reader = N(
        read=lambda: raw,
        read_ss_anne_rival_script=lambda: 4 if fault == "script" else 2,
        read_rival_starter=lambda: starter,
        read_active_trainer_identity=lambda: (
            (225, 25, 1) if fault == "identity" else (242, 42, team)
        ),
    )
    if fault:
        with pytest.raises(ValueError):
            s.ss_anne_rival_contract(b"rom", reader)
    else:
        contract = s.ss_anne_rival_contract(b"rom", reader)
        assert contract.defeated_event is None and contract.trainer_identity == (242, 42, team)


@pytest.mark.parametrize("fault", [None, "field", "position", "object", "defeated", "identity"])
def test_thief_requires_exact_script_and_active_identity(monkeypatch, fault):
    monkeypatch.setattr(s, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(
        s,
        "map_object_events",
        lambda *a: (
            N(
                object_index=2,
                trainer_class=230,
                trainer_set=6 if fault == "object" else 5,
                movement=255,
            ),
        ),
    )
    monkeypatch.setattr(s, "trainer_party_quote", lambda *a: N(expected_victory_money=510))
    flags = bytearray(320)
    if fault == "defeated":
        event = int(s.EventFlag.BEAT_CERULEAN_ROCKET_THIEF)
        flags[event // 8] |= 1 << (event % 8)
    raw = N(
        map_id=3,
        player_x=29 if fault == "position" else 30,
        player_y=9,
        battle_state=2 if fault == "identity" else 0,
        event_flags=bytes(flags),
    )
    reader = N(
        read=lambda: raw,
        trainer_engagement_active=lambda: fault != "field",
        read_active_trainer_identity=lambda: (230, 30, 6),
    )
    if fault:
        with pytest.raises(ValueError):
            s.cerulean_thief_contract(b"rom", reader)
    else:
        contract = s.cerulean_thief_contract(b"rom", reader)
        assert contract.trainer_identity == (230, 30, 5)
        assert contract.victory_items == ((228, 1),)


@pytest.mark.parametrize("fault", [None, "map", "battle", "object", "reward", "defeated"])
def test_nugget_rocket_is_an_exact_already_triggered_contract(monkeypatch, fault):
    monkeypatch.setattr(s, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(
        s,
        "map_object_events",
        lambda *a: (
            N(
                object_index=1,
                trainer_class=230,
                trainer_set=7 if fault == "object" else 6,
                movement=255,
            ),
        ),
    )
    monkeypatch.setattr(s, "trainer_party_quote", lambda *a: N(expected_victory_money=450))
    events = bytearray(320)
    if fault != "reward":
        bit = int(s.EventFlag.GOT_NUGGET)
        events[bit // 8] |= 1 << (bit % 8)
    if fault == "defeated":
        bit = int(s.EventFlag.BEAT_ROUTE_24_ROCKET)
        events[bit // 8] |= 1 << (bit % 8)
    raw = N(
        map_id=3 if fault == "map" else 35,
        battle_state=0 if fault == "battle" else 2,
        event_flags=bytes(events),
    )
    if fault:
        with pytest.raises(ValueError):
            s.nugget_rocket_contract(b"rom", raw)
    else:
        contract = s.nugget_rocket_contract(b"rom", raw)
        assert contract.trainer_identity == (230, 30, 6) and contract.victory_money == 450


@pytest.mark.parametrize("fault", [None, "duplicate", "class", "moving", "event", "truncated"])
def test_fossil_guard_requires_exact_cartridge_object_and_unspent_event(monkeypatch, fault):
    obj = N(
        object_index=1,
        map_id=61,
        trainer_class=209 if fault == "class" else 208,
        trainer_set=2,
        movement=0 if fault == "moving" else 255,
    )
    monkeypatch.setattr(s, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(
        s, "map_object_events", lambda *a: (obj, obj) if fault == "duplicate" else (obj,)
    )
    monkeypatch.setattr(s, "trainer_party_quote", lambda *a: N(expected_victory_money=300))
    events = bytearray(256)
    if fault == "event":
        events[1401 // 8] |= 1 << (1401 % 8)
    raw = N(event_flags=bytes(1) if fault == "truncated" else bytes(events))
    if fault:
        with pytest.raises(ValueError):
            s.fossil_guard_contract(b"rom", raw)
    else:
        contract = s.fossil_guard_contract(b"rom", raw)
        assert contract.trainer_identity == (208, 8, 2) and contract.defeated_event == 1401
        assert contract.objective_id == "reach_cerulean" and contract.victory_money == 300
