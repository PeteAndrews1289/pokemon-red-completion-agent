"""Isolated DEVELOPMENT comparison conditioning, never a player action or TRAIN.

The caller authenticates fresh roots and freezes the paired experiment first.
Every write is disclosed; none of the supplied facts is earned progression.
"""

from .observation import Badge, EventFlag, MapId, RamAddress
from .red_battle_catalog import PokemonRedBattleCatalog, pokemon_red_move_ref
from .red_battle_practice_cartridge import RedPracticeCartridge
from .red_player_income_setup import _apply_fixture_changes, _income_fixture_changes
from .red_player_training_setup import _assisted_progress_baseline


def _authorize(partition, isolated_comparison_setup):
    if partition != "development" or isolated_comparison_setup is not True:
        raise ValueError("branch comparison requires explicit isolated DEVELOPMENT authority")


def prepare_misty_comparison_fixture(memory, *, isolated_comparison_setup, partition, **kwargs):
    """Same fixed level14 gym loading mechanics, explicitly evaluation-only."""
    from .red_player_story_training_setup import _prepare_misty_fixture

    _authorize(partition, isolated_comparison_setup)
    return _prepare_misty_fixture(memory, level=14, hp_percent=100, **kwargs)


def prepare_misty_party_comparison_fixture(
    memory, *, isolated_comparison_setup, partition, hp_percent, **kwargs
):
    """Paired prepared17/20/18/7, half/full health; no additional condition search."""
    from .red_player_story_training_setup import _prepare_misty_party_fixture

    _authorize(partition, isolated_comparison_setup)
    if type(hp_percent) is not int or hp_percent not in (50, 100):
        raise ValueError("comparison health must match one declared condition")
    condition = "injured-prepared" if hp_percent == 50 else "healthy-prepared"
    return _prepare_misty_party_fixture(memory, condition=condition, **kwargs)


def comparison_progress_baseline(raw, *, isolated_comparison_setup, partition, **kwargs):
    _authorize(partition, isolated_comparison_setup)
    return _assisted_progress_baseline(
        raw, isolated_training_setup=True, partition=partition, **kwargs
    )


def prepare_branch_comparison_fixture(
    memory,
    *,
    rom,
    rom_sha256,
    isolated_comparison_setup,
    controller_released,
    battle_state,
    partition,
    hp_percent,
):
    """Fixed level19,427cash,5balls and Center entry; never supply target events."""
    _authorize(partition, isolated_comparison_setup)
    if type(hp_percent) is not int or hp_percent not in (50, 100):
        raise ValueError("comparison health must match one declared condition")
    changes = _income_fixture_changes(
        memory,
        rom=rom,
        rom_sha256=rom_sha256,
        controller_released=controller_released,
        battle_state=battle_state,
        level=19,
        money=427,
        balls=5,
        forest_warp=3,
    )
    flags = (
        EventFlag.BEAT_BROCK,
        EventFlag.BEAT_MISTY,
        EventFlag.BEAT_CERULEAN_RIVAL,
        EventFlag.MET_BILL,
        EventFlag.USED_CELL_SEPARATOR_ON_BILL,
        EventFlag.GOT_SS_TICKET,
        EventFlag.MET_BILL_2,
        EventFlag.BILL_SAID_USE_CELL_SEPARATOR,
        EventFlag.LEFT_BILLS_HOUSE_AFTER_HELPING,
    )
    if int(memory[int(RamAddress.OBTAINED_BADGES)]) != 0 or any(
        int(memory[int(RamAddress.EVENT_FLAGS) + int(f) // 8]) & (1 << (int(f) % 8)) for f in flags
    ):
        raise ValueError("comparison needs a fresh opening,not an earned branch terminal")
    base = int(RamAddress.PARTY_MON_1)
    species = RedPracticeCartridge(rom).species(179)
    if species.national_number != 8:
        raise ValueError("comparison needs cartridge Wartortle")
    a, b = int(memory[base + 27]), int(memory[base + 28])
    stats = species.stats_with_dvs(19, (a >> 4, a & 15, b >> 4, b & 15))
    changes[base] = changes[int(RamAddress.PARTY_SPECIES)] = species.internal_id
    changes[base + 5], changes[base + 6] = species.types
    changes[base + 7] = species.catch_rate
    hp = max(1, stats.max_hp * hp_percent // 100)
    for offset, value in (
        (1, hp),
        (34, stats.max_hp),
        (36, stats.attack),
        (38, stats.defense),
        (40, stats.speed),
        (42, stats.special),
    ):
        changes[base + offset], changes[base + offset + 1] = value >> 8, value & 255
    xp = species.experience_at_level(19)
    for i in range(3):
        changes[base + 14 + i] = (xp >> (16 - 8 * i)) & 255
    moves = species.intrinsic_moves_at_level(19)[-4:]
    catalog = PokemonRedBattleCatalog()
    for i in range(4):
        move = moves[i] if i < len(moves) else 0
        changes[base + 8 + i] = move
        changes[base + 29 + i] = (
            catalog.resolve_move(pokemon_red_move_ref(move)).max_pp if move else 0
        )
    flag = int(EventFlag.BEAT_BROCK)
    address = int(RamAddress.EVENT_FLAGS) + flag // 8
    changes[address] = changes.get(address, int(memory[address])) | 1 << (flag % 8)
    changes[int(RamAddress.OBTAINED_BADGES)] = int(Badge.BOULDER)
    for address in (int(RamAddress.POKEDEX_OWNED), int(RamAddress.POKEDEX_SEEN)):
        changes[address] = int(memory[address]) | (1 << 7)
    changes[0xD365] = int(MapId.CERULEAN_CITY)
    changes[0xD3B1] = changes[0xD3B5] = 0
    changes[0xD3B2] = changes[0xD3B6] = int(MapId.CERULEAN_POKECENTER)
    return _apply_fixture_changes(memory, changes)
