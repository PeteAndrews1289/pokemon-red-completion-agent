from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace as N

import pytest
import pokemon_red_completion.red_player_story_training_setup as setup
from pokemon_red_completion.observation import EventFlag, MapId, RamAddress
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from test_red_player_story_training_setup import party_fixture

PARENT = b"synthetic ROM-free exact four-party TRAIN fixture"


def six_party_inputs(monkeypatch):
    memory, args, old_species = party_fixture(monkeypatch)
    args["condition"] = "healthy-rattata19"
    setup.prepare_misty_party_training_fixture(memory, **args)
    cartridge = RedPracticeCartridge(args["rom"])
    definitions = {5: (21, (64, 45, 43)), 108: (23, (35, 43, 40))}

    def species(i):
        if i in definitions:
            dex, moves = definitions[i]
            return replace(cartridge.species(i), national_number=dex,
                           starting_moves=moves, level_up_moves=())
        return old_species(i)

    monkeypatch.setattr(setup, "RedPracticeCartridge", lambda _: N(species=species))
    monkeypatch.setattr(setup, "_MISTY_SIX_PARTY_PARENT_SHA256", sha256(PARENT).hexdigest())
    args.update(condition="healthy-six-party-rattata19", parent_state_bytes=PARENT)
    return memory, args, species


def test_six_party_append_preserves_every_original_byte_and_complete_write_log(monkeypatch):
    memory, args, species = six_party_inputs(monkeypatch)
    before = bytes(memory)
    rows = setup.prepare_misty_party_training_fixture(memory, **args)
    base = int(RamAddress.PARTY_MON_1)
    assert memory[base:base + 44 * 4] == before[base:base + 44 * 4]
    assert memory[0xD273:0xD273 + 11 * 4] == before[0xD273:0xD273 + 11 * 4]
    assert memory[0xD2B5:0xD2B5 + 11 * 4] == before[0xD2B5:0xD2B5 + 11 * 4]
    assert memory[RamAddress.PARTY_COUNT] == 6
    assert tuple(memory[int(RamAddress.PARTY_SPECIES):int(RamAddress.PARTY_SPECIES) + 7]) == (179,165,150,113,5,108,255)
    touched = {r["address"] for r in rows}
    assert rows and len(touched) == len(rows)
    assert all(memory[i] == value for i, value in enumerate(before) if i not in touched)
    assert all(before[r["address"]] == r["before"] and memory[r["address"]] == r["after"] for r in rows)
    fingerprints = set()
    for i in range(6):
        m = base + 44 * i
        fingerprints.add(bytes(memory[m+12:m+14] + memory[m+27:m+29]))
    assert len(fingerprints) == 6
    for i, code, dex, level, moves in [(4,5,21,12,(64,45,43)), (5,108,23,10,(35,43,40))]:
        m = base + 44 * i
        stats = species(code).stats_with_dvs(level, (8,8,8,8+i))
        assert memory[m] == code and memory[m+3] == memory[m+33] == level
        assert int.from_bytes(memory[m+14:m+17],"big") == species(code).experience_at_level(level)
        assert memory[m+4] == 0 and memory[m+17:m+27] == bytes(10)
        assert memory[m+12:m+14] == before[base+12:base+14]
        assert memory[m+27:m+29] == bytes((0x88,0x88+i))
        for offset, value in [(1,stats.max_hp),(34,stats.max_hp),(36,stats.attack),
                              (38,stats.defense),(40,stats.speed),(42,stats.special)]:
            assert int.from_bytes(memory[m+offset:m+offset+2],"big") == value
        assert tuple(memory[m+8:m+12]) == moves + (0,)
        assert tuple(memory[m+29:m+33]) == tuple(setup.PokemonRedBattleCatalog().resolve_move(
            setup.pokemon_red_move_ref(x)).max_pp for x in moves) + (0,)
        for start in [int(RamAddress.POKEDEX_OWNED),int(RamAddress.POKEDEX_SEEN)]:
            assert memory[start+(dex-1)//8] & (1<<((dex-1)%8))
    assert memory[RamAddress.CURRENT_MAP] == before[RamAddress.CURRENT_MAP] == MapId.CERULEAN_GYM
    assert memory[RamAddress.OBTAINED_BADGES] == before[RamAddress.OBTAINED_BADGES]
    assert memory[int(RamAddress.PLAYER_MONEY):int(RamAddress.PLAYER_MONEY)+3] == before[int(RamAddress.PLAYER_MONEY):int(RamAddress.PLAYER_MONEY)+3]


@pytest.mark.parametrize("fault", [
    "partition","authority","released","battle","bool-battle","missing-parent","wrong-parent",
    "parent-type","rom","source-count","source-species","source-level","source-battle-level",
    "map","active-battle","misty","reward","parent-fingerprint","new-fingerprint","late-moves","late-species",
])
def test_six_party_invalid_parent_or_late_reserve_error_is_atomic(monkeypatch, fault):
    memory, args, species = six_party_inputs(monkeypatch)
    base = int(RamAddress.PARTY_MON_1)
    if fault == "partition": args["partition"] = "development"
    elif fault == "authority": args["isolated_training_setup"] = False
    elif fault == "released": args["controller_released"] = False
    elif fault == "battle": args["battle_state"] = 1
    elif fault == "bool-battle": args["battle_state"] = False
    elif fault == "missing-parent": args.pop("parent_state_bytes")
    elif fault == "wrong-parent": args["parent_state_bytes"] = PARENT+b"tamper"
    elif fault == "parent-type": args["parent_state_bytes"] = bytearray(PARENT)
    elif fault == "rom": args["rom_sha256"] = "0"*64
    elif fault == "source-count": memory[RamAddress.PARTY_COUNT] = 5
    elif fault == "source-species": memory[int(RamAddress.PARTY_SPECIES)+3] = 112
    elif fault == "source-level": memory[base+44+33] += 1
    elif fault == "source-battle-level": memory[base+44+3] += 1
    elif fault == "map": memory[RamAddress.CURRENT_MAP] = MapId.CERULEAN_CITY
    elif fault == "active-battle": memory[RamAddress.STATUS_FLAGS_4] |= 1
    elif fault in {"misty","reward"}:
        bit = int(EventFlag.BEAT_MISTY if fault == "misty" else EventFlag.GOT_TM11)
        memory[int(RamAddress.EVENT_FLAGS)+bit//8] |= 1<<(bit%8)
    elif fault == "parent-fingerprint":
        memory[base+44+27:base+44+29] = memory[base+27:base+29]
    elif fault == "new-fingerprint":
        memory[base+44+27:base+44+29] = bytes((0x88,0x8d))
    else:
        def bad(i):
            s = species(i)
            if i == 108:
                return replace(s, starting_moves=(33,), level_up_moves=()) if fault == "late-moves" else replace(s,national_number=151)
            return s
        monkeypatch.setattr(setup,"RedPracticeCartridge",lambda _:N(species=bad))
    before = bytes(memory)
    with pytest.raises(ValueError):
        setup.prepare_misty_party_training_fixture(memory, **args)
    assert bytes(memory) == before


def test_parent_bytes_are_not_a_generic_legacy_fixture_entry(monkeypatch):
    memory, args, _ = party_fixture(monkeypatch)
    args["parent_state_bytes"] = PARENT
    before = bytes(memory)
    with pytest.raises(ValueError):
        setup.prepare_misty_party_training_fixture(memory, **args)
    assert bytes(memory) == before
