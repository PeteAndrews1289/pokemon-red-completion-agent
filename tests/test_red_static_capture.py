from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS
from pokemon_red_completion.gen1_traversal import MapObjectEvent
from pokemon_red_completion.observation import CurrentMapObject, RawGameState
from pokemon_red_completion.red_static_capture import (
    RedStaticCaptureTarget,
    _decode_static_target,
    observe_static_capture,
    require_static_capture_admission,
)


def fixture():
    rom = bytearray(0x10000)
    # Independently constructed Articuno-shaped object3 / event-offset2.
    event = MapObjectEvent(162, 9, 1, 6, 0xFF, 0xFF, 0x43, 3, 74, 50)
    rom[MAP_HEADER_BANKS + 162] = 3
    rom[MAP_HEADER_POINTERS + 324 : MAP_HEADER_POINTERS + 326] = b"\x00\x41"
    rom[0xC105:0xC107] = b"\x00\x42"
    rom[0xC204:0xC206] = b"\x00\x43"
    rom[0xC300:0xC304] = b"\x08\x21\x00\x44"
    # 0xD882 - 0xD747 =315 bytes;315*8+2=2522.
    rom[0xC400:0xC40C] = bytes.fromhex("02 00 82 d8 00 45 00 45 00 45 00 45")
    return rom, event


def test_static_event_follows_text_header_not_sprite_index():
    rom, event = fixture()
    target = _decode_static_target(bytes(rom), event, 144)
    assert target.event_flag == 2522
    assert target.object_index == 3
    assert target.at == (1, 6) and target.internal_species == 74


@pytest.mark.parametrize(
    "at,value",
    [
        (0xC300, 0),
        (0xC301, 0),
        (0xC303, 0x80),
        (0xC400, 16),
        (0xC401, 1),
        (0xC403, 0xC0),
        (0xC405, 0x80),
    ],
)
def test_malformed_binding_refused(at, value):
    rom, event = fixture()
    rom[at] = value
    with pytest.raises(CartridgeReadError):
        _decode_static_target(bytes(rom), event, 144)


def reader(**changes):
    raw = RawGameState(True, 162, 6, 2, 1, 0, event_flags=bytes(320))
    obj = CurrentMapObject(3, 9, (1, 6), 0, 0)
    data = dict(raw=raw, obj=obj, registered=frozenset(), facing="up", ready=True, dialogue=False)
    data.update(changes)
    return NS(
        read=lambda: data["raw"],
        read_pokedex_state=lambda: NS(owned_species=data["registered"]),
        read_current_map_objects=lambda: () if data["obj"] is None else (data["obj"],),
        read_player_facing=lambda: data["facing"],
        read_input_readiness=lambda: NS(ready=data["ready"]),
        read_bottom_dialogue_box_visible=lambda: data["dialogue"],
    )


TARGET = RedStaticCaptureTarget(144, 74, 50, 162, 3, 9, (1, 6), 2522)


@pytest.mark.parametrize("change", [
    {"event_flag": -1}, {"event_flag": 2560}, {"map_id": True},
    {"object_index": 0}, {"at": (-1, 6)}, {"species_number": 145},
    {"level": 0}, {"internal_species": True},
])
def test_invalid_target_identity_refused(change):
    with pytest.raises(ValueError):
        replace(TARGET, **change)


def test_visible_adjacent_object_is_not_resource_qualification():
    result = observe_static_capture(reader(), TARGET)
    assert result.ready_to_interact and result.present_here
    assert not result.registered and not result.consumed


@pytest.mark.parametrize(
    "change",
    [
        {"obj": None},
        {"facing": "left"},
        {"ready": False},
        {"dialogue": True},
        {"registered": frozenset({144})},
        {"obj": CurrentMapObject(3, 9, (1, 6), 0, 255)},
    ],
)
def test_missing_hidden_busy_or_already_owned_not_interactable(change):
    assert not observe_static_capture(reader(**change), TARGET).ready_to_interact


@pytest.mark.parametrize("length", [0, 315])
def test_missing_event_bytes_not_treated_as_clear(length):
    r = reader()
    r.read = lambda: RawGameState(True, 162, 6, 2, 1, 0, event_flags=bytes(length))
    with pytest.raises(ValueError, match="truncated"):
        observe_static_capture(r, TARGET)


def test_consumed_event_and_offmap_do_not_claim_presence():
    r = reader()
    raw = r.read()
    flags = bytearray(320)
    flags[315] = 4
    r.read = lambda: replace(raw, event_flags=bytes(flags))
    result = observe_static_capture(r, TARGET)
    assert result.consumed and not result.present_here
    r.read = lambda: replace(raw, map_id=41)
    result = observe_static_capture(r, TARGET)
    assert not result.consumed and not result.present_here and not result.ready_to_interact


@pytest.mark.parametrize(
    "obj",
    [
        CurrentMapObject(3, 5, (1, 6), 0, 0),
        CurrentMapObject(3, 9, (2, 6), 0, 0),
        CurrentMapObject(3, 9, (1, 6), 3, 0),
    ],
)
def test_object_drift_refused(obj):
    with pytest.raises(ValueError, match="drifted"):
        observe_static_capture(reader(obj=obj), TARGET)


@pytest.mark.parametrize("fault", [None, "balls", "room", "fainted", "identity"])
def test_interaction_admission_checks_actual_resources(fault):
    r = reader()
    raw = replace(
        r.read(),
        party_count=6,
        party_species_ids=(28,) * 6,
        party_hp=(100,) * 6,
        bag_items=((1, 1),),
    )
    if fault == "balls":
        raw = replace(raw, bag_items=())
    if fault == "fainted":
        raw = replace(raw, party_hp=(0,) * 6)
    r.read = lambda: raw
    r.read_all_box_states = lambda: NS(
        current_box_index=0, boxes=(NS(species_ids=(28,) * (20 if fault == "room" else 19)),)
    )

    def admit():
        return require_static_capture_admission(
            r,
            TARGET,
            internal_species=75 if fault == "identity" else 74,
            level=50,
            ball_id=1,
            minimum_balls=1,
        )

    if fault is None:
        assert admit().ready_to_interact
    else:
        with pytest.raises(ValueError):
            admit()


@pytest.mark.parametrize(
    "fault", [None, "far", "hidden", "owned", "busy", "dialogue", "battle", "off_map"]
)
def test_opt_in_facing_only_admits_the_same_fresh_adjacent_object(fault):
    changes = {"facing": "left"}
    if fault == "hidden":
        changes["obj"] = None
    if fault == "owned":
        changes["registered"] = frozenset({144})
    if fault == "busy":
        changes["ready"] = False
    if fault == "dialogue":
        changes["dialogue"] = True
    r = reader(**changes)
    raw = replace(r.read(), party_count=1, party_hp=(100,), bag_items=((1, 1),))
    if fault == "far":
        raw = replace(raw, player_y=4)
    if fault == "battle":
        raw = replace(raw, battle_state=1)
    if fault == "off_map":
        raw = replace(raw, map_id=41)
    r.read = lambda: raw
    r.read_all_box_states = lambda: NS(current_box_index=0, boxes=(NS(species_ids=()),))
    kwargs = dict(internal_species=74, level=50, ball_id=1, minimum_balls=1)
    # Strict ordinary admission never acquires this relaxed facing behavior.
    with pytest.raises(ValueError):
        require_static_capture_admission(r, TARGET, **kwargs)
    if fault is None:
        admitted = require_static_capture_admission(
            r, TARGET, **kwargs, allow_facing_preparation=True
        )
        assert admitted.present_here and not admitted.ready_to_interact
    else:
        with pytest.raises(ValueError):
            require_static_capture_admission(r, TARGET, **kwargs, allow_facing_preparation=True)
