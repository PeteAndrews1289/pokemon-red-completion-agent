"""Synthetic instruction fixtures; no cartridge or captured game data."""

import pytest

import pokemon_red_completion.gen1_champion_script as module
from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.rom import RomValidationError


def cartridge(*, banks=(2, 5), relocation=0, first=153, second=176,
              event_address=0xD7A3, event_opcode=0xEE):
    image = bytearray(0x24000)
    locations = {}

    def room(map_id, bank, stage_address, header, script, table, stages):
        offset = (bank - 1) * 0x4000

        def put(address, data, name=None):
            absolute = offset + address + relocation
            image[absolute:absolute + len(data)] = data
            if name:
                locations[name] = absolute

        def word(address):
            return (address + relocation).to_bytes(2, "little")

        image[0xC23D + map_id] = bank
        image[0x1AE + map_id * 2:0x1B0 + map_id * 2] = word(header)
        locations[f"header_pointer_{map_id}"] = 0x1AE + map_id * 2
        put(header + 7, word(script), f"script_pointer_{map_id}")
        put(script, b"\xcd\x3c\x3c\x21" + word(table) + b"\xfa"
            + stage_address + b"\xc3\x97\x3d", f"dispatch_{map_id}")
        put(table, b"".join(word(stage) for stage in stages), f"table_{map_id}")
        return put, word

    def movement(put, word, at, data_at, next_stage, stage_address, data, name):
        # ld a,$ff / ld [wJoyIgnore],a / ld hl,queue / ld de,runs /
        # call DecodeRLEList / dec a / store index / start queue / next stage.
        put(at, bytes.fromhex("3e ff ea 6b cd 21 d3 cc 11") + word(data_at)
            + bytes.fromhex("cd 0c 35 3d ea 38 cd cd 86 34 3e")
            + bytes((next_stage, 0xEA)) + stage_address + b"\xc9", name)
        put(data_at, data, name + "_data")

    stages = (0x4520, 0x4610, 0x4820, 0x4A40, 0x4C00, 0x4D00,
              0x4E00, 0x4F00, 0x5010, 0x5120, 0x5330)
    put, word = room(120, banks[0], b"\x4c\xd6", 0x4100, 0x4230, 0x4350, stages)
    put(stages[0], b"\xc9", "idle")
    movement(put, word, stages[1], 0x5400, 2, b"\x4c\xd6",
             bytes.fromhex("10 02 40 03 20 01 ff"), "entry")
    movement(put, word, stages[9], 0x5510, 10, b"\x4c\xd6",
             bytes.fromhex("80 04 10 01 ff"), "exit")
    # The private fixture need not authenticate intervening engine CALL targets.
    ready = bytes.fromhex("fa 38 cd a7 c0 cd") + bytes(37)
    ready += bytes.fromhex("3e f3 ea 59 d0 fa 15 d7 fe") + bytes((first,))
    ready += bytes.fromhex("20 04 3e 01 18 0a fe") + bytes((second,))
    ready += bytes.fromhex("20 04 3e 02 18 02 3e 03 ea 5d d0 af e0 b4 3e 03 ea 4c d6 c9")
    assert len(ready) == 81
    put(stages[2], ready, "ready")
    defeated = bytes.fromhex("fa 57 d0 fe ff ca 00 20 cd 00 21 21")
    defeated += event_address.to_bytes(2, "little") + bytes((0xCB, event_opcode))
    defeated += bytes(19) + bytes.fromhex("3e 04 ea 4c d6 c9")
    assert len(defeated) == 41
    put(stages[3], defeated, "defeated")
    put(stages[10], bytes.fromhex("fa 38 cd a7 c0 af ea 6b cd 3e 00 ea 4c d6 c9"), "exit_end")
    hall = (0x4B00, 0x4D00, 0x4E00, 0x4F00)
    put, word = room(118, banks[1], b"\x4b\xd6", 0x4710, 0x4820, 0x4960, hall)
    movement(put, word, hall[0], 0x5200, 1, b"\x4b\xd6",
             bytes.fromhex("20 03 40 02 ff"), "hall")
    put(hall[1], bytes.fromhex("fa 38 cd a7 c0"), "hall_wait")
    put(hall[3], b"\xc9", "hall_idle")
    return bytes(image), locations


@pytest.mark.parametrize("banks,relocation", [((2, 5), 0), ((6, 7), 0x180)])
@pytest.mark.parametrize("starter,expected_set", [(153, 1), (176, 2), (1, 3)])
def test_relocated_binding_has_literal_identity_event_and_reverse_execution_order(
    banks, relocation, starter, expected_set,
):
    rom, _ = cartridge(banks=banks, relocation=relocation)
    binding = module._decode_champion_script(rom, starter)
    assert binding.active_identity == (243, 43, expected_set)
    assert binding.event_flag == 741  # event byte $5c, bit5
    assert binding.entry_runs == (((0, -1), 1), ((-1, 0), 3), ((0, 1), 2))
    assert binding.exit_runs == (((0, 1), 1), ((1, 0), 4))
    assert binding.hall_runs == (((-1, 0), 2), ((0, -1), 3))


@pytest.mark.parametrize("starter,expected", [(7, 1), (9, 2), (153, 3)])
def test_starter_comparisons_are_cartridge_operands_not_fixed_species(starter, expected):
    rom, _ = cartridge(first=7, second=9)
    assert module._decode_champion_script(rom, starter).trainer_set == expected


@pytest.mark.parametrize("address,opcode,expected", [
    (0xD747, 0xC6, 0), (0xD748, 0xFE, 15), (0xD886, 0xFE, 2559),
])
def test_event_operand_byte_and_set_bit_are_both_derived(address, opcode, expected):
    rom, _ = cartridge(event_address=address, event_opcode=opcode)
    assert module._decode_champion_script(rom, 153).event_flag == expected


@pytest.mark.parametrize("address,opcode", [
    (0xD746, 0xC6), (0xD887, 0xC6), (0xD747, 0xC7), (0xD747, 0x86),
])
def test_invalid_event_range_or_non_set_hl_opcode_refuses(address, opcode):
    rom, _ = cartridge(event_address=address, event_opcode=opcode)
    with pytest.raises(CartridgeReadError):
        module._decode_champion_script(rom, 153)


@pytest.mark.parametrize("name,delta,value", [
    ("dispatch_120", 7, 0x39), ("dispatch_118", 7, 0x4C),
    ("idle", 0, 0), ("entry", 12, 0), ("entry", 22, 3),
    ("entry", 24, 0x4B), ("exit", 22, 9), ("hall", 22, 2),
    ("hall", 24, 0x4C), ("ready", 0, 0), ("ready", 44, 200),
    ("ready", 44, 248), ("ready", 53, 0x28), ("ready", 78, 0x4B),
    ("defeated", 14, 0), ("exit_end", 0, 0), ("hall_wait", 3, 0),
    ("hall_idle", 0, 0), ("entry_data", 0, 0x30), ("entry_data", 1, 0),
    ("entry_data", 1, 100),
])
def test_unsupported_control_flow_direction_or_queue_bound_refuses(name, delta, value):
    rom, locations = cartridge()
    changed = bytearray(rom)
    at = locations[name] + delta
    assert changed[at] != value
    changed[at] = value
    with pytest.raises(CartridgeReadError):
        module._decode_champion_script(bytes(changed), 153)


def test_overlapping_starter_branches_refuse():
    rom, _ = cartridge(first=7, second=7)
    with pytest.raises(CartridgeReadError):
        module._decode_champion_script(rom, 7)


@pytest.mark.parametrize("data", [b"\xff", b"\x40\x01" * 51])
def test_empty_or_unterminated_movement_refuses(data):
    rom, locations = cartridge()
    changed = bytearray(rom)
    at = locations["entry_data"]
    changed[at:at + len(data)] = data
    with pytest.raises(CartridgeReadError):
        module._decode_champion_script(bytes(changed), 153)


@pytest.mark.parametrize("steps", [100, 101])
def test_physical_queue_capacity_is_one_hundred_steps(steps):
    rom, locations = cartridge()
    changed = bytearray(rom)
    at = locations["entry_data"]
    changed[at:at + 3] = bytes((0x40, steps, 0xFF))
    if steps == 100:
        assert module._decode_champion_script(bytes(changed), 153).entry_runs == (((-1, 0), 100),)
    else:
        with pytest.raises(CartridgeReadError):
            module._decode_champion_script(bytes(changed), 153)


@pytest.mark.parametrize("name,delta", [
    ("header_pointer_120", 0), ("script_pointer_120", 0), ("dispatch_120", 4),
    ("table_120", 2), ("entry", 9), ("header_pointer_118", 0),
    ("script_pointer_118", 0), ("table_118", 0), ("hall", 9),
])
@pytest.mark.parametrize("pointer", [0x3FFF, 0x8000, 0x7FFF])
def test_invalid_or_cross_bank_pointer_cannot_read_neighboring_bytes(name, delta, pointer):
    rom, locations = cartridge()
    changed = bytearray(rom)
    at = locations[name] + delta
    changed[at:at + 2] = pointer.to_bytes(2, "little")
    with pytest.raises(CartridgeReadError):
        module._decode_champion_script(bytes(changed), 153)


@pytest.mark.parametrize("name,remaining", [
    ("header_pointer_120", 1), ("dispatch_120", 11), ("ready", 80),
    ("defeated", 40), ("hall", 26), ("hall_data", 4),
])
def test_truncated_buffers_refuse_without_index_errors(name, remaining):
    rom, locations = cartridge()
    with pytest.raises(CartridgeReadError):
        module._decode_champion_script(rom[:locations[name] + remaining], 153)


@pytest.mark.parametrize("starter", [None, True, 0, 191, "153"])
def test_private_decoder_requires_a_literal_valid_starter(starter):
    rom, _ = cartridge()
    with pytest.raises(CartridgeReadError):
        module._decode_champion_script(rom, starter)


def test_private_decoder_rejects_mutable_image():
    rom, _ = cartridge()
    with pytest.raises(CartridgeReadError):
        module._decode_champion_script(bytearray(rom), 153)


def test_public_api_has_no_synthetic_grammar_revision_bypass(monkeypatch):
    rom, _ = cartridge()
    assert module._decode_champion_script(rom, 153).active_identity == (243, 43, 1)
    monkeypatch.setattr(module, "_decode_champion_script",
                        lambda *_: pytest.fail("unqualified ROM reached private decoder"))
    with pytest.raises(RomValidationError):
        module.champion_script_binding(rom, 153)
    with pytest.raises(TypeError):
        module.champion_script_binding(rom, 153, verify=False)
