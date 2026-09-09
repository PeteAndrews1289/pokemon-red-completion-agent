"""Independent tiny cartridge assembly for the event-gated RLE script grammar."""

import pytest

from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_scripted_arrival import _decode_trainer_room_arrival


def cartridge(*, bank=3, map_id=12, right=3, end_x=7):
    rom = bytearray(0x20000)
    offset = (bank - 1) * 0x4000

    def put(at, data):
        rom[offset + at:offset + at + len(data)] = data

    rom[0xc23d + map_id] = bank
    rom[0x1ae + map_id * 2:0x1b0 + map_id * 2] = (0x4100).to_bytes(2, 'little')
    put(0x4107, bytes.fromhex('00 42'))
    put(0x4200, bytes.fromhex('cd 00 60 cd 00 21 21 00 48 11 00 43 fa 53 d6 cd 60 31 ea 53 d6 c9'))
    put(0x4300, bytes.fromhex('00 44 00 48 20 48 00 47 40 48'))
    # Different event byte and bits from the real cartridge; positive JR lands
    # at 4480. Fifth coordinate is the sole RLE trigger, not either door tile.
    put(0x4400, bytes.fromhex(
        'fa 49 d7 cb 57 c0 21 00 45 cd 00 30 d2 00 31 '
        'af e0 b4 fa 3d cd fe 03 30 07 3e 01 e0 8c c3 00 32 '
        'fe 05 28 5c 21 4a d7 cb 5e cb de c0 '
        '21 26 d1 cb ee 3e ad cd 00 33 c3 00 60'
    ))
    put(0x4480, bytes.fromhex(
        '3e ff ea 6b cd 21 d3 cc 11 00 46 cd 00 34 3d ea 38 cd '
        'cd 00 35 3e 03 ea 53 d6 ea 39 da c9'
    ))
    put(0x4500, bytes([1, 5, 2, 6, 8, 6, 8, end_x, 10, 4, 255]))
    put(0x4600, bytes([0x40, 2, 0x10, right, 255]))
    put(0x4700, bytes.fromhex('fa 38 cd a7 c0 cd 00 36 af ea 6b cd ea 53 d6 ea 39 da c9'))
    return bytes(rom), map_id, offset


@pytest.mark.parametrize('bank,map_id', [(3, 12), (4, 21)])
@pytest.mark.parametrize('right,end_x', [(3, 7), (5, 9)])
def test_relocated_trigger_event_and_mixed_runs_derive_the_actual_endpoint(
    bank, map_id, right, end_x,
):
    rom, map_id, _ = cartridge(bank=bank, map_id=map_id, right=right, end_x=end_x)
    arrival = _decode_trainer_room_arrival(rom, map_id, bytes(320))
    assert arrival.entrance_coordinates == ((10, 4),)
    assert arrival.direction_runs == (((0, 1), right), ((-1, 0), 2))
    assert arrival.steps == 2 + right
    assert arrival.event_flag == 27
    assert arrival.settled_at((10, 4)) == (8, end_x)
    assert arrival.settled_at((8, 6)) == (8, 6)
    assert arrival.interaction_coordinates == ((1, 5), (2, 6))


def test_queue_consumption_order_controls_intermediate_coordinate_bounds():
    rom, map_id, offset = cartridge()
    changed = bytearray(rom)
    # Stored up2/down3 executes down3/up2. From y0 it stays nonnegative;
    # incorrectly walking storage order crosses y=-2 before ending at y1.
    changed[offset + 0x4504:offset + 0x4508] = bytes([1, 4, 1, 7])
    changed[offset + 0x4508:offset + 0x450a] = bytes([0, 4])
    changed[offset + 0x4600:offset + 0x4605] = bytes.fromhex('40 02 80 03 ff')
    arrival = _decode_trainer_room_arrival(bytes(changed), map_id, bytes(320))
    assert arrival.direction_runs == (((1, 0), 3), ((-1, 0), 2))
    assert arrival.settled_at((0, 4)) == (1, 4)
    changed[offset + 0x4600:offset + 0x4605] = bytes.fromhex('80 03 40 02 ff')
    with pytest.raises(CartridgeReadError):
        _decode_trainer_room_arrival(bytes(changed), map_id, bytes(320))


def test_static_trigger_inspection_does_not_claim_a_consumed_arrival_is_available():
    rom, map_id, _ = cartridge()
    triggers = _decode_trainer_room_arrival(rom, map_id, None).interaction_coordinates
    assert triggers == ((1, 5), (2, 6))
    with pytest.raises(CartridgeReadError):
        _decode_trainer_room_arrival(rom, map_id, bytes([0, 0, 4, 8]) + bytes(316))


def test_semantically_plausible_long_walk_cannot_overwrite_the_pinned_queue_index():
    rom, map_id, offset = cartridge()
    changed = bytearray(rom)
    changed[offset + 0x4504:offset + 0x4508] = bytes([10, 6, 10, 7])
    # Right52/left50 returns to a legitimate trigger within screen-byte bounds,
    # but102 bytes would overlap the queue index. Refuse independently of net.
    changed[offset + 0x4600:offset + 0x4605] = bytes.fromhex('20 32 10 34 ff')
    with pytest.raises(CartridgeReadError, match='step bound'):
        _decode_trainer_room_arrival(bytes(changed), map_id, bytes(320))


def test_plausible_flat_file_bytes_at_vram_pointer_are_not_executable_rom():
    rom, map_id, offset = cartridge()
    changed = bytearray(rom)
    changed[offset + 0x8400:offset + 0x849e] = rom[offset + 0x4400:offset + 0x449e]
    changed[offset + 0x4300:offset + 0x4302] = bytes.fromhex('00 84')
    with pytest.raises(CartridgeReadError):
        _decode_trainer_room_arrival(bytes(changed), map_id, bytes(320))


def test_script_span_cannot_cross_the_switchable_rom_window():
    rom, map_id, offset = cartridge()
    changed = bytearray(rom)
    changed[offset + 0x7ff0:offset + 0x8006] = rom[offset + 0x4200:offset + 0x4216]
    changed[offset + 0x4107:offset + 0x4109] = bytes.fromhex('f0 7f')
    with pytest.raises(CartridgeReadError):
        _decode_trainer_room_arrival(bytes(changed), map_id, bytes(320))


@pytest.mark.parametrize('index,value', [(2, 4), (3, 8)])
def test_either_defeated_or_locked_event_refuses_the_one_shot(index, value):
    rom, map_id, _ = cartridge()
    events = bytearray(320)
    events[index] = value
    with pytest.raises(CartridgeReadError):
        _decode_trainer_room_arrival(rom, map_id, bytes(events))


@pytest.mark.parametrize('address,value', [
    (0x4400, 0), (0x4404, 0), (0x4405, 0), (0x4406, 0),
    (0x4409, 0), (0x440c, 0), (0x4416, 2), (0x4418, 6),
    (0x4421, 4), (0x4422, 0), (0x4423, 0), (0x4428, 0),
    (0x442a, 0), (0x442b, 0), (0x4438, 0),
    (0x4481, 0), (0x4485, 0), (0x448b, 0), (0x448e, 0),
    (0x4492, 0), (0x4496, 2), (0x4498, 0), (0x449d, 0),
    (0x450a, 0), (0x4509, 1), (0x4507, 9),
    (0x4600, 0x50), (0x4601, 0), (0x4602, 0x20),
    (0x4704, 0), (0x4708, 0), (0x470d, 0), (0x4712, 0),
])
def test_changed_branch_queue_or_trigger_cannot_advertise_a_plausible_arrival(address, value):
    rom, map_id, offset = cartridge()
    changed = bytearray(rom)
    assert changed[offset + address] != value
    changed[offset + address] = value
    with pytest.raises(CartridgeReadError):
        _decode_trainer_room_arrival(bytes(changed), map_id, bytes(320))
