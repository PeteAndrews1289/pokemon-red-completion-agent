from dataclasses import replace

import pytest
from test_gen1_rle_trainer_arrival import cartridge
from test_observation import RecordingMemory
from test_red_trainer_funding_battle import ScriptedEnvironment, make_candidate, make_state

import pokemon_red_completion.gen1_trainer_dialogue as dialogue
from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_trainer_sight import TrainerHeader
from pokemon_red_completion.observation import PokemonRedStateReader


def test_live_header_is_big_endian_and_text_sprite_is_not_aliased_blink_counter():
    memory = RecordingMemory({0xDA30: 0x63, 0xDA31: 0x97, 0xCF13: 3, 0xFF8C: 6})
    assert PokemonRedStateReader(memory).read_trainer_dialogue_context() == (0x6397, 3)


@pytest.fixture
def fixture(monkeypatch):
    rom, map_id, offset = cartridge()
    rom = bytearray(rom)
    rom[offset + 0x4105 : offset + 0x4107] = bytes.fromhex("00 49")
    rom[offset + 0x4900 : offset + 0x4902] = bytes.fromhex("00 4a")
    rom[offset + 0x4A00 : offset + 0x4A0A] = bytes.fromhex("08 21 00 48 cd cc 31 c3 d7 24")
    rom[offset + 0x441E : offset + 0x4420] = bytes.fromhex("20 29")
    target = make_candidate(at=(2, 6))
    target = replace(target, trainer=replace(target.trainer, map_id=map_id, sprite_index=1))
    monkeypatch.setattr(dialogue, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(
        dialogue, "trainer_room_interaction_coordinates", lambda *_: ((1, 5), (2, 6))
    )
    monkeypatch.setattr(
        dialogue, "trainer_headers", lambda *_a, **_k: (TrainerHeader(map_id, 1, 0, 1139, 0x4800),)
    )
    return rom, offset, target


def test_qualified_thunk_resolves_header_not_copied_real_rom_address(fixture):
    rom, _, target = fixture
    assert dialogue._qualified_header(bytes(rom), target) == 0x4800


def test_map_enum_is_normalized_at_strict_cartridge_parser_boundary(fixture, monkeypatch):
    from pokemon_red_completion.observation import MapId
    rom, _, target = fixture
    target = replace(target, trainer=replace(target.trainer, map_id=MapId.LANCES_ROOM))
    def inspect(_rom, map_id):
        assert type(map_id) is int and map_id == 113
        raise CartridgeReadError('boundary verified')
    monkeypatch.setattr(dialogue, 'trainer_room_interaction_coordinates', inspect)
    with pytest.raises(CartridgeReadError, match='boundary verified'):
        dialogue._qualified_header(bytes(rom), target)


def test_public_binding_checks_revision_before_interpreting_any_dialogue(monkeypatch):
    from pokemon_red_completion.rom import verify_rom_bytes
    monkeypatch.setattr(dialogue, 'verify_rom_bytes', verify_rom_bytes)
    with pytest.raises(ValueError):
        dialogue.bind_scripted_trainer_dialogue(
            b'not a cartridge', None, None, None, final_event_flag=1200,
        )


def test_retained_candidate_is_current_adjacent_text_not_new_navigation(fixture, monkeypatch):
    rom, _, target = fixture
    initial = make_state(map_id=12, yx=(2, 6))
    env = ScriptedEnvironment(initial, dialogue=True)
    env.read_trainer_dialogue_context = lambda: (0x4800, 1)
    env.read_current_map_objects = lambda: ()
    monkeypatch.setattr(dialogue, 'map_object_events', lambda *_: ())
    current = replace(target.trainer, at=(1, 6))
    monkeypatch.setattr(dialogue, 'trainer_sight_zones', lambda *_: (current,))
    monkeypatch.setattr(dialogue, 'trainer_party_quote', lambda *_a, **_k: target.quote)
    def bind():
        return dialogue.retained_scripted_trainer_candidate(
            bytes(rom), env, map_id=12, trainer_event_flag=1139, final_event_flag=1200,
        )
    result = bind()
    assert not result.approach.steps and result.approach.terminal_at == (2, 6)
    for change in ({'visible': False}, {'defeated': True}, {'event_flag': 1138}, {'at': (1, 5)}):
        current = replace(target.trainer, at=(1, 6), **{k:v for k,v in change.items() if k != 'at'})
        if 'at' in change:
            current = replace(current, at=change['at'])
        with pytest.raises(CartridgeReadError):
            bind()
    assert not env.actions


@pytest.mark.parametrize(
    "at,value",
    [
        (0x441A, 2),
        (0x441E, 0),
        (0x441F, 0),
        (0x4207, 1),
        (0x4A00, 0),
        (0x4A01, 0),
        (0x4A02, 1),
        (0x4A04, 0),
        (0x4A05, 0),
        (0x4A07, 0),
        (0x4A09, 0),
        (0x4106, 0x84),
        (0x4901, 0x84),
    ],
)
def test_wrong_text_dispatch_header_or_bank_refuses(fixture, at, value):
    rom, offset, target = fixture
    assert rom[offset + at] != value
    rom[offset + at] = value
    with pytest.raises(CartridgeReadError):
        dialogue._qualified_header(bytes(rom), target)


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "header",
        "sprite",
        "box",
        "pending",
        "map",
        "position",
        "facing",
        "money",
        "bag",
        "hp",
        "species",
        "battle",
        "event",
        "final",
    ],
)
def test_live_prelatch_binding_rechecks_text_and_protected_state(fixture, fault):
    rom, _, target = fixture
    initial = make_state(map_id=12, yx=(2, 6))
    env = ScriptedEnvironment(initial, dialogue=True, ready=True)
    env.read_trainer_dialogue_context = lambda: (
        0x4801 if fault == "header" else 0x4800,
        2 if fault == "sprite" else 1,
    )
    validate = dialogue.bind_scripted_trainer_dialogue(
        bytes(rom), env, target, initial, final_event_flag=1200
    )
    changes = {
        "map": {"map_id": 13},
        "position": {"player_x": 5},
        "money": {"player_money": 501},
        "bag": {"bag_items": ()},
        "hp": {"party_hp": (49, 40)},
        "species": {"party_species_ids": (1, 25)},
        "battle": {"battle_state": 2},
    }
    if fault in changes:
        env.state = replace(env.state, **changes[fault])
    if fault in {"event", "final"}:
        flags = bytearray(initial.event_flags)
        flag = 1139 if fault == "event" else 1200
        flags[flag // 8] |= 1 << (flag % 8)
        env.state = replace(env.state, event_flags=bytes(flags))
    if fault == "box":
        env.dialogue = False
    if fault == "pending":
        env.pending_identity = (201, 10)
    if fault == "facing":
        env.facing = "left"
    if fault:
        with pytest.raises(CartridgeReadError):
            validate()
    else:
        validate()
        env.state = replace(initial, player_money=501)
        with pytest.raises(CartridgeReadError):
            validate()
    assert not env.actions


@pytest.mark.parametrize("fault", [None, "header", "sprite", "pending", "latched",
                                  "hp", "money", "bag", "readiness"])
def test_initializing_sprite_is_not_input_permission_or_a_protected_state_waiver(fixture, fault):
    rom, _, target = fixture
    initial = make_state(map_id=12, yx=(2, 6))
    env = ScriptedEnvironment(initial, dialogue=True, ready=True)
    env.read_trainer_dialogue_context = lambda: (
        0x4801 if fault == "header" else 0x4800, 2 if fault == "sprite" else 0,
    )
    validate = dialogue.bind_scripted_trainer_dialogue(
        bytes(rom), env, target, initial, final_event_flag=1200,
    )
    if fault in {"pending", "latched"}:
        env.pending_identity = (target.trainer.trainer_class,
                                target.trainer.trainer_set if fault == "latched" else 10)
    if fault == "hp":
        env.state = replace(initial, party_hp=(49, 40))
    if fault == "money":
        env.state = replace(initial, player_money=501)
    if fault == "bag":
        env.state = replace(initial, bag_items=())
    if fault == "readiness":
        env.ready = False
    with pytest.raises(CartridgeReadError) as caught:
        validate()
    assert isinstance(caught.value, dialogue.TrainerDialogueInitializing) is (fault is None)
    if fault is None:
        env.read_trainer_dialogue_context = lambda: (0x4800, 1)
        validate()
        env.read_trainer_dialogue_context = lambda: (0x4800, 0)
        # Even after a previous success, this validator never accepts sprite0.
        with pytest.raises(dialogue.TrainerDialogueInitializing):
            validate()
    assert not env.actions
