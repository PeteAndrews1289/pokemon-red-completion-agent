"""Disclosed TRAIN-only income fixture; no actor can call this memory writer.

Retain an authenticated fresh opening and every returned write. Native loading,
trainer defeat/payout and purchases happen after this synthetic setup boundary.
No supplied money, item, XP or prerequisite is an earned outcome.
"""

from .observation import SQUIRTLE_SPECIES_ID, EventFlag, MapId, RamAddress
from .red_battle_catalog import PokemonRedBattleCatalog, pokemon_red_move_ref
from .red_battle_practice_cartridge import RedPracticeCartridge
from .red_safari_training_setup import RED_ROM_SHA256


def prepare_income_fixture(memory, *, rom, rom_sha256, isolated_training_setup,
                           controller_released, battle_state, partition,
                           level, money, balls, forest_warp):
    if isolated_training_setup is not True or partition != "train":
        raise ValueError("income fixture needs explicit bounded isolated TRAIN authority")
    changes = _income_fixture_changes(memory, rom=rom, rom_sha256=rom_sha256,
        controller_released=controller_released, battle_state=battle_state,
        level=level, money=money, balls=balls, forest_warp=forest_warp)
    return _apply_fixture_changes(memory, changes)


def _income_fixture_changes(memory, *, rom, rom_sha256, controller_released,
                            battle_state, level, money, balls, forest_warp):
    """Pure cartridge-derived setup plan; caller separately authenticates authority."""
    from hashlib import sha256

    if (rom_sha256 != RED_ROM_SHA256 or sha256(rom).hexdigest() != rom_sha256
        or controller_released is not True
        or type(battle_state) is not int or battle_state != 0
        or type(level) is not int or not 1 <= level <= 30
        or type(money) is not int or not 0 <= money <= 999999
        or type(balls) is not int or not 0 <= balls <= 99
        or type(forest_warp) is not int or forest_warp not in (2, 3, 4, 5)):
        raise ValueError("income fixture needs explicit bounded isolated TRAIN authority")
    base = int(RamAddress.PARTY_MON_1)
    expected = {
        int(RamAddress.CURRENT_MAP): int(MapId.OAKS_LAB),
        int(RamAddress.OAKS_LAB_SCRIPT): 10,
        int(RamAddress.PARTY_COUNT): 1,
        int(RamAddress.PARTY_SPECIES): SQUIRTLE_SPECIES_ID,
        base: SQUIRTLE_SPECIES_ID,
        int(RamAddress.NUM_BAG_ITEMS): 0,
        0xD3AE: 2, 0xD365: int(MapId.PALLET_TOWN),
        **{0xD3AF+i: b for i, b in enumerate((11, 4, 2, 255, 11, 5, 2, 255))},
        **{base+i: 0 for i in range(17, 27)},
    }
    if (any(int(memory[a]) != b for a, b in expected.items())
        or int(memory[int(RamAddress.STATUS_FLAGS_4)]) & 1):
        raise ValueError("income fixture fresh opening differs; no writes allowed")
    species = RedPracticeCartridge(rom).species(SQUIRTLE_SPECIES_ID)
    a, b = int(memory[base+27]), int(memory[base+28])
    stats = species.stats_with_dvs(level, (a >> 4, a & 15, b >> 4, b & 15))
    moves = species.intrinsic_moves_at_level(level)[-4:]
    catalog = PokemonRedBattleCatalog()
    changes = {
        int(RamAddress.OAKS_LAB_SCRIPT): 18,
        int(RamAddress.VIRIDIAN_MART_SCRIPT): 2,
        0xD365: int(MapId.ROUTE_2),
        0xD3B1: forest_warp, 0xD3B2: int(MapId.VIRIDIAN_FOREST),
        0xD3B5: forest_warp, 0xD3B6: int(MapId.VIRIDIAN_FOREST),
        base+3: level, base+33: level, base+4: 0,
        int(RamAddress.NUM_BAG_ITEMS): int(balls > 0),
        int(RamAddress.BAG_ITEMS): 4 if balls else 255,
    }
    if balls:
        changes.update({int(RamAddress.BAG_ITEMS)+1: balls,
                        int(RamAddress.BAG_ITEMS)+2: 255})
    for flag in (EventFlag.GOT_POKEDEX, EventFlag.GOT_OAKS_PARCEL, EventFlag.OAK_GOT_PARCEL):
        address = int(RamAddress.EVENT_FLAGS) + int(flag)//8
        changes[address] = changes.get(address, int(memory[address])) | 1 << (int(flag)%8)
    for offset, value in ((1, stats.max_hp), (34, stats.max_hp), (36, stats.attack),
                          (38, stats.defense), (40, stats.speed), (42, stats.special)):
        changes[base+offset], changes[base+offset+1] = value >> 8, value & 255
    xp = species.experience_at_level(level)
    for i in range(3):
        changes[base+14+i] = (xp >> (16-8*i)) & 255
        changes[int(RamAddress.PLAYER_MONEY)+i] = int(f"{money:06d}"[2*i:2*i+2], 16)
    for i in range(4):
        move = moves[i] if i < len(moves) else 0
        changes[base+8+i] = move
        changes[base+29+i] = catalog.resolve_move(pokemon_red_move_ref(move)).max_pp if move else 0
    return changes


def _apply_fixture_changes(memory, changes):
    rows = tuple(dict(address=a, before=int(memory[a]), after=v)
                 for a, v in sorted(changes.items()))
    for row in rows:
        memory[row["address"]] = row["after"]
    if any(int(memory[row["address"]]) != row["after"] for row in rows):
        raise ValueError("income fixture readback failed; preserve terminal")
    return rows
