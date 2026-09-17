"""ROM-free checks for the 151-species teacher practice catalog."""

import pytest

from pokemon_red_completion import red_battle_practice_cartridge as practice
from pokemon_red_completion.battle_practice_factory import BattlePracticeError
from pokemon_red_completion.observation import GEN1_TYPE_NAMES_BY_CODE
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog


def _synthetic_rom(monkeypatch):
    catalog = PokemonRedBattleCatalog()
    mapping = dict(zip(catalog.species_ids, range(1, 152), strict=True))
    reverse_types = {name: code for code, name in GEN1_TYPE_NAMES_BY_CODE.items()}
    rom = bytearray(0x40000)
    for internal, national in mapping.items():
        name_at = practice._INTERNAL_NAMES_OFFSET + (internal - 1) * practice._INTERNAL_NAME_SIZE
        rom[name_at : name_at + practice._INTERNAL_NAME_SIZE] = (
            bytes([0x80 + internal % 26]) + b"\x50" * 9
        )
        offset = (
            practice._MEW_BASE_STATS_OFFSET
            if national == 151
            else practice._BASE_STATS_OFFSET + (national - 1) * practice._BASE_ROW_SIZE
        )
        row = bytearray(practice._BASE_ROW_SIZE)
        row[0:6] = bytes((national, 45, 49, 49, 45, 65))
        types = catalog.resolve_species(practice.pokemon_red_species_ref(internal)).types
        row[6:8] = bytes(reverse_types[name] for name in (types + types[-1:])[:2])
        row[8:10] = bytes((45, 64))
        row[15:17] = bytes((33, 45))
        row[19] = 3
        row[20] = 0b00000001  # TM01: Mega Punch
        rom[offset : offset + practice._BASE_ROW_SIZE] = row
    monkeypatch.setattr(practice, "internal_to_dex", lambda _rom: mapping)
    monkeypatch.setattr(
        practice,
        "level_up_learnsets",
        lambda _rom: {number: ((10, 73), (20, 75)) for number in mapping.values()},
    )
    return rom, mapping


def test_all_151_species_and_move_sources(monkeypatch):
    rom, mapping = _synthetic_rom(monkeypatch)
    catalog = practice.RedPracticeCartridge(bytes(rom))
    assert catalog.species_ids == tuple(sorted(mapping))
    for internal, national in mapping.items():
        species = catalog.species(internal)
        assert species.national_number == national
        assert species.starting_moves == (33, 45)
        assert species.intrinsic_moves_at_level(9) == (33, 45)
        assert species.intrinsic_moves_at_level(10) == (33, 45, 73)
        assert species.teachable_moves_at_level(20) == (33, 45, 73, 75, 5)
        assert species.neutral_stats(30).max_hp == 67
        assert species.experience_at_level(5) == 135
        assert len(species.nickname_bytes) == 11
        assert species.nickname_bytes[-1] == 0x50


def test_cartridge_rejects_table_corruption_and_unknown_species(monkeypatch):
    rom, mapping = _synthetic_rom(monkeypatch)
    offset = practice._BASE_STATS_OFFSET
    rom[offset] = 0
    with pytest.raises(BattlePracticeError, match="base-stat table"):
        practice.RedPracticeCartridge(bytes(rom))
    rom[offset] = 1
    catalog = practice.RedPracticeCartridge(bytes(rom))
    with pytest.raises(BattlePracticeError, match="unknown Red practice species"):
        catalog.species(max(mapping) + 1)


def test_cartridge_rejects_type_mismatch(monkeypatch):
    rom, _ = _synthetic_rom(monkeypatch)
    rom[practice._BASE_STATS_OFFSET + 6] = 26
    with pytest.raises(BattlePracticeError, match="species types differ"):
        practice.RedPracticeCartridge(bytes(rom))


@pytest.mark.parametrize("level", (1, 32, 50, 100))
@pytest.mark.parametrize("dv", (0, 8, 15))
def test_all_species_neutral_stats_match_gen1_base_plus_dv_formula(monkeypatch, level, dv):
    rom, mapping = _synthetic_rom(monkeypatch)
    cartridge = practice.RedPracticeCartridge(bytes(rom))
    hp_dv = 15 if dv & 1 else 0
    expected = (
        (2 * (45 + hp_dv) * level) // 100 + level + 10,
        (2 * (49 + dv) * level) // 100 + 5,
        (2 * (49 + dv) * level) // 100 + 5,
        (2 * (45 + dv) * level) // 100 + 5,
        (2 * (65 + dv) * level) // 100 + 5,
    )
    for internal in mapping:
        stats = cartridge.species(internal).neutral_stats(level, dv=dv)
        assert (stats.max_hp, stats.attack, stats.defense, stats.speed, stats.special) == expected


def test_native_trainer_dvs_differ_from_uniform_player_dvs(monkeypatch):
    rom, mapping = _synthetic_rom(monkeypatch)
    species = practice.RedPracticeCartridge(bytes(rom)).species(next(iter(mapping)))
    assert species.trainer_stats(32).max_hp == (2 * (45 + 8) * 32) // 100 + 42
    assert species.trainer_stats(32).attack == (2 * (49 + 9) * 32) // 100 + 5
    assert species.trainer_stats(32).attack >= species.neutral_stats(32).attack


def test_all_151_distinct_base_rows_cover_dv_parity_and_level_boundaries(monkeypatch):
    rom, mapping = _synthetic_rom(monkeypatch)
    for _internal, national in mapping.items():
        offset = (
            practice._MEW_BASE_STATS_OFFSET
            if national == 151
            else practice._BASE_STATS_OFFSET + (national - 1) * practice._BASE_ROW_SIZE
        )
        rom[offset + 1 : offset + 6] = bytes(
            20 + (national * multiplier) % 190 for multiplier in (1, 3, 5, 7, 11)
        )
    cartridge = practice.RedPracticeCartridge(bytes(rom))
    for internal, national in mapping.items():
        base = tuple(20 + (national * multiplier) % 190 for multiplier in (1, 3, 5, 7, 11))
        for level in (1, 32, 50, 100):
            for dv in (0, 8, 9, 15):
                hp_dv = 15 if dv % 2 else 0
                expected = (
                    (2 * (base[0] + hp_dv) * level) // 100 + level + 10,
                    *((2 * (stat + dv) * level) // 100 + 5 for stat in base[1:]),
                )
                actual = cartridge.species(internal).neutral_stats(level, dv=dv)
                assert (
                    actual.max_hp,
                    actual.attack,
                    actual.defense,
                    actual.speed,
                    actual.special,
                ) == expected
