from dataclasses import replace

import pytest

from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_scripted_arrival import (
    _decode_trainer_room_arrival as trainer_room_arrival,
)
from pokemon_red_completion.gen1_scripted_arrival import (
    with_scripted_trainer_arrival,
)
from pokemon_red_completion.global_router import MacroEdge, MacroGraph


def test_public_arrival_requires_the_existing_exact_supported_revision(monkeypatch):
    import pokemon_red_completion.gen1_scripted_arrival as arrival
    from pokemon_red_completion.rom import RomValidationError
    rom, map_id, _ = cartridge()
    monkeypatch.setattr(arrival, '_decode_trainer_room_arrival',
                        lambda *_: pytest.fail('unqualified engine must never reach decoder'))
    with pytest.raises(RomValidationError):
        arrival.trainer_room_arrival(rom, map_id, bytes(320))


@pytest.mark.parametrize('events', [None, bytearray(320), [0] * 320])
def test_public_arrival_cannot_use_static_inspection_to_bypass_current_events(monkeypatch, events):
    import pokemon_red_completion.gen1_scripted_arrival as arrival
    monkeypatch.setattr(arrival, 'verify_rom_bytes', lambda _: None)
    monkeypatch.setattr(arrival, '_decode_trainer_room_arrival',
                        lambda *_: pytest.fail('missing observations must not reach decoder'))
    with pytest.raises(CartridgeReadError):
        arrival.trainer_room_arrival(b'qualified-by-test', 113, events)


def cartridge(*, direction=0x40, steps=6, bank=2, map_id=7):
    # Independently assembled tiny LR35902 fixture. Pointers are deliberately
    # separated rather than copied from a real room's contiguous byte layout.
    rom = bytearray(0x20000)
    offset = (bank - 1) * 0x4000

    def put(address, data):
        rom[offset + address : offset + address + len(data)] = data

    rom[0xC23D + map_id] = bank
    rom[0x1AE + map_id * 2 : 0x1B0 + map_id * 2] = (0x4100).to_bytes(2, "little")
    put(0x4107, bytes.fromhex("00 42"))
    put(0x4200, bytes.fromhex("cd 00 20 cd 00 21 21 00 46 11 00 43 fa 4f d6 cd 60 31 ea 4f d6 c9"))
    put(0x4300, bytes.fromhex("80 44 00 50 00 51 00 52 00 53"))
    put(
        0x4480,
        bytes.fromhex(
            "21 00 45 cd bf 34 d2 19 32 af e0 b3 e0 b4 ea d3 cc ea 38 cd "
            "fa 3d cd fe 03 38 09 21 47 d7 cb 56 cb d6 28 9c"
        ),
    )
    put(
        0x4440,
        bytes.fromhex("21 d3 cc 3e")
        + bytes([direction])
        + bytes([0x22]) * (steps - 1)
        + bytes([0x77, 0x3E, steps])
        + bytes.fromhex("ea 38 cd cd 86 34 3e 03 ea 4f d6 ea 39 da c9"),
    )
    put(0x4500, bytes([10, 4, 10, 5, 11, 4, 11, 5, 255]))
    return bytes(rom), map_id, offset


@pytest.mark.parametrize("steps", [1, 2, 6, 9])
@pytest.mark.parametrize("bank,map_id", [(2, 7), (3, 8)])
def test_decode_follows_relocated_pointers_and_actual_movement_count(steps, bank, map_id):
    rom, map_id, _ = cartridge(steps=steps, bank=bank, map_id=map_id)
    arrival = trainer_room_arrival(rom, map_id, bytes(320))
    assert arrival.steps == steps and arrival.event_flag == 2
    assert arrival.settled_at((11, 4)) == (11 - steps, 4)
    assert arrival.settled_at((11, 5)) == (11 - steps, 5)
    assert arrival.settled_at((0, 4)) == (0, 4)


def test_direction_is_cartridge_data_not_an_up_constant():
    rom, map_id, _ = cartridge(direction=0x10, steps=2)
    assert trainer_room_arrival(rom, map_id, bytes(320)).settled_at((11, 4)) == (11, 6)


@pytest.mark.parametrize(
    "address,value",
    [
        (0x4209, 0),
        (0x4300, 0),
        (0x4480, 0),
        (0x4497, 0),
        (0x4498, 2),
        (0x4499, 0),
        (0x449E, 0),
        (0x449F, 0),
        (0x44A1, 0),
        (0x44A2, 0),
        (0x44A3, 0),
        (0x4440, 0),
        (0x4444, 0),
        (0x444B, 5),
        (0x4508, 0),
    ],
)
def test_changed_script_grammar_cannot_silently_predict_an_arrival(address, value):
    rom, map_id, offset = cartridge()
    changed = bytearray(rom)
    assert changed[offset + address] != value
    changed[offset + address] = value
    with pytest.raises(CartridgeReadError):
        trainer_room_arrival(bytes(changed), map_id, bytes(320))


def test_consumed_one_shot_and_unbound_warps_refuse():
    rom, map_id, _ = cartridge()
    events = bytes([4]) + bytes(319)
    with pytest.raises(CartridgeReadError):
        trainer_room_arrival(rom, map_id, events)
    arrival = trainer_room_arrival(rom, map_id, bytes(320))
    edges = {1: (MacroEdge(map_id, "warp", (0, 4), (11, 4), destination_warp_index=0),)}
    graph = MacroGraph(
        edges,
        warp_locations={map_id: ((11, 4), (11, 5), (0, 4))},
        warp_arrivals={map_id: ((11, 4), (11, 5), (0, 4))},
    )
    changed = with_scripted_trainer_arrival(graph, arrival)
    assert changed.edges is graph.edges
    assert changed.warp_locations is graph.warp_locations
    assert changed.warp_arrivals[map_id] == ((5, 4), (5, 5), (0, 4))
    assert graph.warp_arrivals[map_id][0] == (11, 4)
    with pytest.raises(CartridgeReadError):
        with_scripted_trainer_arrival(replace(graph, warp_arrivals=None), arrival)
