"""Teacher-only Misty fixtures derived from authenticated fresh TRAIN openings.

All prerequisites, party conditioning and skipped gym trainers are synthetic
baseline, never earned progress. No writes occur until the complete setup has
validated. Actors cannot reach this helper through their action interface.
"""

from .gen1_trainer_sight import trainer_headers
from .observation import Badge, EventFlag, MapId, RamAddress
from .red_battle_catalog import PokemonRedBattleCatalog, pokemon_red_move_ref
from .red_battle_practice_cartridge import RedPracticeCartridge
from .red_player_income_setup import prepare_income_fixture
from .red_safari_training_setup import RED_ROM_SHA256


class _StagedMemory:
    def __init__(self, memory):
        self.memory, self.changes = memory, {}

    def __getitem__(self, address):
        return self.changes.get(address, int(self.memory[address]))

    def __setitem__(self, address, value):
        self.changes[address] = value


def prepare_misty_party_training_fixture(
    memory, *, rom, rom_sha256, isolated_training_setup, controller_released,
    battle_state, partition, condition, parent_state_bytes=None,
):
    """Condition one authenticated TRAIN field copy for declared preparation trials.

    Caller authenticates source bytes/lineage and retains every returned write.
    This is a teacher-only setup, never earned XP/registration or an actor action.
    Only the frozen conditions are supported; no arbitrary party search.
    """
    if isolated_training_setup is not True or partition != "train":
        raise ValueError("party fixture requires explicit isolated TRAIN field authority")
    if condition == "healthy-six-party-rattata20-deferred":
        return _prepare_misty_deferred20_fixture(memory, rom=rom, rom_sha256=rom_sha256,
            controller_released=controller_released, battle_state=battle_state,
            parent_state_bytes=parent_state_bytes)
    if condition == "healthy-six-party-rattata19":
        return _append_misty_training_reserves(memory, rom=rom, rom_sha256=rom_sha256,
            controller_released=controller_released, battle_state=battle_state,
            parent_state_bytes=parent_state_bytes)
    if parent_state_bytes is not None:
        raise ValueError("parent state bytes are only for the declared six-party fixture")
    return _prepare_misty_party_fixture(memory, rom=rom, rom_sha256=rom_sha256,
        controller_released=controller_released, battle_state=battle_state, condition=condition)


def _prepare_misty_party_fixture(
    memory, *, rom, rom_sha256, controller_released, battle_state, condition,
):
    """Shared conditioning; public caller separately checks TRAIN/evaluation authority."""
    from hashlib import sha256

    conditions = {
        "injured-prepared": ((179, 166, 150, 113), (17, 20, 18, 7), 50),
        "healthy-less-prepared": ((179, 165, 36, 113), (17, 17, 17, 7), 100),
        "healthy-prepared": ((179, 166, 150, 113), (17, 20, 18, 7), 100),
        "healthy-rattata19": ((179, 165, 150, 113), (17, 19, 18, 7), 100),
        "healthy-rattata18-progressed": ((179, 165, 150, 113), (17, 18, 18, 7), 100),
        "healthy-wartortle19": ((179, 166, 150, 113), (19, 20, 18, 7), 100),
    }
    if (controller_released is not True or type(battle_state) is not int
        or battle_state != 0 or not isinstance(rom, bytes)
        or rom_sha256 != RED_ROM_SHA256 or sha256(rom).hexdigest() != rom_sha256
        or type(condition) is not str or condition not in conditions):
        raise ValueError("party fixture requires explicit isolated TRAIN field authority")
    base = int(RamAddress.PARTY_MON_1)
    expected = {int(RamAddress.CURRENT_MAP): int(MapId.CERULEAN_GYM),
        int(RamAddress.PARTY_COUNT): 1, int(RamAddress.PARTY_SPECIES): 179,
        int(RamAddress.PARTY_SPECIES) + 1: 255, base: 179, base + 33: 14}
    if (any(int(memory[a]) != v for a, v in expected.items())
        or int(memory[int(RamAddress.STATUS_FLAGS_4)]) & 1):
        raise ValueError("party fixture source must be the single-starter field ancestor")
    for flag in (int(EventFlag.BEAT_MISTY), 0xBE):
        if int(memory[int(RamAddress.EVENT_FLAGS) + flag // 8]) & (1 << (flag % 8)):
            raise ValueError("party fixture cannot erase earned Misty progress")
    species_ids, levels, hp_percent = conditions[condition]
    # Source-species move inheritance is fixed, not arbitrary TM/event availability.
    move_sources = (179, 165, 36, 112)
    movesets = ((33, 39, 145, 55), (33, 39, 98, 158), (16, 28, 98), (40, 81))
    expected_dex = {179: 8, 166: 20, 165: 19, 150: 17, 36: 16, 113: 14, 112: 13}
    cartridge, catalog = RedPracticeCartridge(rom), PokemonRedBattleCatalog()
    staged = _StagedMemory(memory)
    ot = (int(memory[base + 12]), int(memory[base + 13]))
    ot_name = tuple(int(memory[0xD273 + i]) for i in range(11))
    fingerprints = set()
    for index, (species_id, level, ancestor_id, moves) in enumerate(
        zip(species_ids, levels, move_sources, movesets, strict=True)
    ):
        species, ancestor = cartridge.species(species_id), cartridge.species(ancestor_id)
        if (species.national_number != expected_dex[species_id]
            or ancestor.national_number != expected_dex[ancestor_id]
            or not set(moves) <= set(ancestor.intrinsic_moves_at_level(level))):
            raise ValueError("party fixture cartridge identity or legal moves differ")
        dvs = (8, 8, 8, 8 + index)
        fingerprint = (*ot, dvs[0] * 16 + dvs[1], dvs[2] * 16 + dvs[3])
        if fingerprint in fingerprints:
            raise ValueError("party fixture fingerprints collide")
        fingerprints.add(fingerprint)
        stats = species.stats_with_dvs(level, dvs)
        member = base + 44 * index
        for offset in range(44):
            staged[member + offset] = 0
        staged[member] = staged[int(RamAddress.PARTY_SPECIES) + index] = species_id
        staged[member + 3] = staged[member + 33] = level
        staged[member + 5], staged[member + 6] = species.types
        staged[member + 7] = species.catch_rate
        staged[member + 12], staged[member + 13] = ot
        staged[member + 27], staged[member + 28] = fingerprint[-2:]
        xp = species.experience_at_level(level)
        if condition == "healthy-rattata18-progressed" and index == 1:
            # A fixed TRAIN contrast from partway through level18, not a reset
            # of a consumed level19 attempt. Both intervening levels are earned.
            next_xp = species.experience_at_level(level + 1)
            if next_xp <= xp:
                raise ValueError("party fixture progression threshold differs")
            xp += (next_xp - xp) // 2
        for j in range(3):
            staged[member + 14 + j] = (xp >> (16 - 8 * j)) & 255
        hp = max(1, stats.max_hp * hp_percent // 100)
        for offset, value in ((1, hp), (34, stats.max_hp), (36, stats.attack),
                              (38, stats.defense), (40, stats.speed), (42, stats.special)):
            staged[member + offset], staged[member + offset + 1] = value >> 8, value & 255
        for j, move in enumerate(moves):
            staged[member + 8 + j] = move
            staged[member + 29 + j] = catalog.resolve_move(pokemon_red_move_ref(move)).max_pp
        for j, value in enumerate(ot_name):
            staged[0xD273 + 11 * index + j] = value
        name = species.nickname_bytes[:10].ljust(11, b"\x50")
        for j, value in enumerate(name):
            staged[0xD2B5 + 11 * index + j] = value
        for start in (int(RamAddress.POKEDEX_OWNED), int(RamAddress.POKEDEX_SEEN)):
            dex_index = species.national_number - 1
            staged[start + dex_index // 8] |= 1 << (dex_index % 8)
    staged[int(RamAddress.PARTY_COUNT)] = 4
    staged[int(RamAddress.PARTY_SPECIES) + 4] = 255
    rows = tuple(dict(address=a, before=int(memory[a]), after=v)
                 for a, v in sorted(staged.changes.items()))
    for row in rows:
        memory[row["address"]] = row["after"]
    if any(int(memory[r["address"]]) != r["after"] for r in rows):
        raise ValueError("party fixture readback failed; retain diagnostic terminal")
    return rows



# Exact original TRAINfar field fixture; no DEVELOPMENT source is accepted here.
_MISTY_SIX_PARTY_PARENT_SHA256 = "e0ec6ba4eeb3dab69c37b29093c3b182ec42278a1962122f46365c32cac9544e"


def _append_misty_training_reserves(
    memory, *, rom, rom_sha256, controller_released, battle_state, parent_state_bytes,
):
    """Append two disclosed, healthy reserves without changing the four originals.

    The setup caller must load these exact parent bytes without intervening input
    and retain source custody, all returned writes and the new observed snapshot.
    Current fixture stats are teacher inputs, never forecasts or earned progress.
    """
    from hashlib import sha256

    if (controller_released is not True or type(battle_state) is not int
        or battle_state != 0 or not isinstance(rom, bytes)
        or rom_sha256 != RED_ROM_SHA256 or sha256(rom).hexdigest() != rom_sha256
        or type(parent_state_bytes) is not bytes
        or sha256(parent_state_bytes).hexdigest() != _MISTY_SIX_PARTY_PARENT_SHA256):
        raise ValueError("six-party fixture requires its exact isolated TRAIN parent")
    base = int(RamAddress.PARTY_MON_1)
    expected = {int(RamAddress.CURRENT_MAP): int(MapId.CERULEAN_GYM),
                int(RamAddress.PARTY_COUNT): 4,
                int(RamAddress.PARTY_SPECIES) + 4: 255}
    for index, (species_id, level) in enumerate(zip((179, 165, 150, 113), (17, 19, 18, 7), strict=True)):
        member = base + 44 * index
        expected.update({int(RamAddress.PARTY_SPECIES) + index: species_id,
                         member: species_id, member + 3: level, member + 33: level})
    if (any(int(memory[a]) != v for a, v in expected.items())
            or int(memory[int(RamAddress.STATUS_FLAGS_4)]) & 1):
        raise ValueError("six-party fixture parent field roster differs")
    for flag in (int(EventFlag.BEAT_MISTY), int(EventFlag.GOT_TM11)):
        if int(memory[int(RamAddress.EVENT_FLAGS) + flag // 8]) & (1 << (flag % 8)):
            raise ValueError("six-party fixture cannot erase earned Misty progress")

    cartridge, catalog = RedPracticeCartridge(rom), PokemonRedBattleCatalog()
    staged = _StagedMemory(memory)
    ot = (int(memory[base + 12]), int(memory[base + 13]))
    ot_name = tuple(int(memory[0xD273 + i]) for i in range(11))
    fingerprints = {
        tuple(int(memory[base + 44 * i + j]) for j in (12, 13, 27, 28))
        for i in range(4)
    }
    if len(fingerprints) != 4:
        raise ValueError("six-party fixture parent specimen fingerprints collide")
    # Low-level, undecided-role coverage. The worker retains only the original
    # four combat specimen refs; this teacher does not choose runtime roles.
    reserves = ((4, 5, 21, 12, (64, 45, 43)),
                (5, 108, 23, 10, (35, 43, 40)))
    for index, species_id, dex, level, moves in reserves:
        species = cartridge.species(species_id)
        if species.national_number != dex or not set(moves) <= set(species.intrinsic_moves_at_level(level)):
            raise ValueError("six-party reserve cartridge identity or legal moves differ")
        dvs = (8, 8, 8, 8 + index)
        fingerprint = (*ot, dvs[0] * 16 + dvs[1], dvs[2] * 16 + dvs[3])
        if fingerprint in fingerprints:
            raise ValueError("six-party reserve specimen fingerprint collides")
        fingerprints.add(fingerprint)
        stats = species.stats_with_dvs(level, dvs)
        member = base + 44 * index
        for offset in range(44):
            staged[member + offset] = 0
        staged[member] = staged[int(RamAddress.PARTY_SPECIES) + index] = species_id
        staged[member + 3] = staged[member + 33] = level
        staged[member + 5], staged[member + 6] = species.types
        staged[member + 7] = species.catch_rate
        staged[member + 12], staged[member + 13] = ot
        staged[member + 27], staged[member + 28] = fingerprint[-2:]
        xp = species.experience_at_level(level)
        for j in range(3):
            staged[member + 14 + j] = (xp >> (16 - 8 * j)) & 255
        for offset, value in ((1, stats.max_hp), (34, stats.max_hp), (36, stats.attack),
                              (38, stats.defense), (40, stats.speed), (42, stats.special)):
            staged[member + offset], staged[member + offset + 1] = value >> 8, value & 255
        for j, move in enumerate(moves):
            staged[member + 8 + j] = move
            staged[member + 29 + j] = catalog.resolve_move(pokemon_red_move_ref(move)).max_pp
        for j, value in enumerate(ot_name):
            staged[0xD273 + 11 * index + j] = value
        name = species.nickname_bytes[:10].ljust(11, b"P")
        for j, value in enumerate(name):
            staged[0xD2B5 + 11 * index + j] = value
        for start in (int(RamAddress.POKEDEX_OWNED), int(RamAddress.POKEDEX_SEEN)):
            dex_index = species.national_number - 1
            staged[start + dex_index // 8] |= 1 << (dex_index % 8)
    staged[int(RamAddress.PARTY_COUNT)] = 6
    staged[int(RamAddress.PARTY_SPECIES) + 6] = 255
    rows = tuple(dict(address=a, before=int(memory[a]), after=v)
                 for a, v in sorted(staged.changes.items()))
    for row in rows:
        memory[row["address"]] = row["after"]
    if any(int(memory[r["address"]]) != r["after"] for r in rows):
        raise ValueError("six-party fixture readback failed; retain diagnostic terminal")
    return rows


def prepare_bill_training_fixture(
    memory, *, rom, rom_sha256, isolated_training_setup, controller_released,
    battle_state, partition,
):
    """Supply only a disclosed fresh TRAIN baseline and native Bill-house entry.

    Bill's request, machine and ticket flags are explicitly absent; all three
    phases must be executed natively. This is not an earned north-route run.
    """
    staged = _StagedMemory(memory)
    prepare_income_fixture(staged, rom=rom, rom_sha256=rom_sha256,
        isolated_training_setup=isolated_training_setup, controller_released=controller_released,
        battle_state=battle_state, partition=partition, level=5, money=3000, balls=5,
        forest_warp=3)
    for flag in (EventFlag.MET_BILL, EventFlag.USED_CELL_SEPARATOR_ON_BILL,
                 EventFlag.GOT_SS_TICKET, EventFlag.MET_BILL_2,
                 EventFlag.BILL_SAID_USE_CELL_SEPARATOR, EventFlag.LEFT_BILLS_HOUSE_AFTER_HELPING):
        address = int(RamAddress.EVENT_FLAGS) + int(flag) // 8
        if int(memory[address]) & (1 << (int(flag) % 8)):
            raise ValueError("Bill fixture requires fresh native phase flags")
    if int(memory[int(RamAddress.OBTAINED_BADGES)]) != 0:
        raise ValueError("Bill fixture requires unbadged fresh opening")
    flag = int(EventFlag.BEAT_BROCK)
    staged[int(RamAddress.EVENT_FLAGS) + flag // 8] |= 1 << (flag % 8)
    staged[int(RamAddress.OBTAINED_BADGES)] = int(Badge.BOULDER)
    staged[0xD365] = int(MapId.ROUTE_25)
    staged[0xD3B1] = staged[0xD3B5] = 0
    staged[0xD3B2] = staged[0xD3B6] = int(MapId.BILLS_HOUSE)
    rows = tuple(dict(address=a, before=int(memory[a]), after=v)
                 for a, v in sorted(staged.changes.items()))
    for row in rows:
        memory[row["address"]] = row["after"]
    if any(int(memory[r["address"]]) != r["after"] for r in rows):
        raise ValueError("Bill fixture readback failed; retain diagnostic terminal")
    return rows


def prepare_misty_training_fixture(
    memory, *, rom, rom_sha256, isolated_training_setup, controller_released,
    battle_state, partition, level, hp_percent,
):
    """Supply one Wartortle14..30, fixed resources, and a loaded gym entry.

    Actual map loading, leader combat, reward and defeat remain native. Use a
    prospectively bounded TRAIN declaration; siblings are one correlated root.
    """
    if isolated_training_setup is not True or partition != "train":
        raise ValueError("Misty fixture requires explicit isolated TRAIN authority")
    return _prepare_misty_fixture(memory, rom=rom, rom_sha256=rom_sha256,
        controller_released=controller_released, battle_state=battle_state,
        level=level, hp_percent=hp_percent)


def _prepare_misty_fixture(
    memory, *, rom, rom_sha256, controller_released, battle_state, level, hp_percent,
):
    """Shared mechanics; public entrypoints retain separate partition authority."""
    from .red_player_income_setup import _apply_fixture_changes, _income_fixture_changes

    if (type(level) is not int or not 14 <= level <= 30
        or type(hp_percent) is not int or hp_percent not in (50, 100)):
        raise ValueError("Misty fixture requires declared bounded level and health")
    staged = _StagedMemory(memory)
    _apply_fixture_changes(staged, _income_fixture_changes(
        staged, rom=rom, rom_sha256=rom_sha256, controller_released=controller_released,
        battle_state=battle_state, level=level, money=3000, balls=5, forest_warp=3))
    gym = int(MapId.CERULEAN_GYM)
    headers = trainer_headers(rom, {gym}, full_event_offsets=True)
    ordinary = tuple(h.event_flag for h in headers if h.sprite_index != 1)
    if (len(ordinary) != 2 or len(set(ordinary)) != 2
        or any(not 0xB0 <= f < int(EventFlag.BEAT_MISTY) for f in ordinary)):
        raise ValueError("Misty fixture needs exact cartridge gym prerequisites")
    base = int(RamAddress.PARTY_MON_1)
    species = RedPracticeCartridge(rom).species(179)
    if species.national_number != 8:
        raise ValueError("Misty fixture requires cartridge Wartortle")
    a, b = int(memory[base + 27]), int(memory[base + 28])
    stats = species.stats_with_dvs(level, (a >> 4, a & 15, b >> 4, b & 15))
    staged[base] = staged[int(RamAddress.PARTY_SPECIES)] = species.internal_id
    staged[base + 5], staged[base + 6] = species.types
    staged[base + 7] = species.catch_rate
    hp = max(1, stats.max_hp * hp_percent // 100)
    for offset, value in ((1, hp), (34, stats.max_hp), (36, stats.attack),
                          (38, stats.defense), (40, stats.speed), (42, stats.special)):
        staged[base + offset], staged[base + offset + 1] = value >> 8, value & 255
    xp = species.experience_at_level(level)
    for i in range(3):
        staged[base + 14 + i] = (xp >> (16 - 8 * i)) & 255
    moves = species.intrinsic_moves_at_level(level)[-4:]
    catalog = PokemonRedBattleCatalog()
    for i in range(4):
        move = moves[i] if i < len(moves) else 0
        staged[base + 8 + i] = move
        staged[base + 29 + i] = (
            catalog.resolve_move(pokemon_red_move_ref(move)).max_pp if move else 0
        )
    for flag in (*ordinary, int(EventFlag.BEAT_BROCK)):
        address = int(RamAddress.EVENT_FLAGS) + flag // 8
        staged[address] |= 1 << (flag % 8)
    for flag in (int(EventFlag.BEAT_MISTY), 0xBE):
        address = int(RamAddress.EVENT_FLAGS) + flag // 8
        if staged[address] & (1 << (flag % 8)):
            raise ValueError("Misty fixture cannot erase an already-earned outcome")
    if int(memory[int(RamAddress.OBTAINED_BADGES)]) != 0:
        raise ValueError("Misty fixture requires unbadged fresh opening")
    staged[int(RamAddress.OBTAINED_BADGES)] = int(Badge.BOULDER)
    for address in (int(RamAddress.POKEDEX_OWNED), int(RamAddress.POKEDEX_SEEN)):
        staged[address] |= 1 << 7  # Synthetic Wartortle registration, not novelty.
    staged[0xD365] = int(MapId.CERULEAN_CITY)
    staged[0xD3B1] = staged[0xD3B5] = 0
    staged[0xD3B2] = staged[0xD3B6] = gym
    rows = tuple(dict(address=a, before=int(memory[a]), after=v)
                 for a, v in sorted(staged.changes.items()))
    for row in rows:
        memory[row["address"]] = row["after"]
    if any(int(memory[r["address"]]) != r["after"] for r in rows):
        raise ValueError("Misty fixture readback failed; retain diagnostic terminal")
    return rows


_MISTY_DEFERRED20_PARENT_SHA256 = "0e691fe7b9c2624cc496ff07170c925c51fab3726245cc1547c887a69724575d"

def _prepare_misty_deferred20_fixture(
    memory, *, rom, rom_sha256, controller_released, battle_state, parent_state_bytes,
):
    """Supply one explicitly deferred20 TRAIN condition; never earned progress.

    Exact original TRAIN parent only. Keep species/moves/PP/OT/DVs/EVs/roles/world;
    canonical existing cartridge/factory helpers supply level20 XP and stat bytes.
    The caller retains every write, authenticates the loaded source without input,
    and exports a new paired TRAIN context with original roles/origin/spent.
    """
    from hashlib import sha256
    from types import SimpleNamespace
    from .party import StatusCondition
    from .red_party import (PokemonRedPartyReader, member_field_address,
        SPECIES_OFFSET, EXPERIENCE_OFFSET, DETERMINANT_VALUES_OFFSET, PP_OFFSET)
    from .red_battle_practice_factory import (_PARTY_BOX_LEVEL_OFFSET,
        _PARTY_STAT_EXP_OFFSET, _put_u16, _put_u24, _put_stats, _stats,
        PARTY_LEVEL_OFFSET, PARTY_HP_OFFSET, PARTY_MAX_HP_OFFSET)
    from .red_player_income_setup import _apply_fixture_changes
    if (controller_released is not True or type(battle_state) is not int
        or battle_state != 0 or type(rom) is not bytes
        or rom_sha256 != RED_ROM_SHA256 or sha256(rom).hexdigest() != rom_sha256
        or type(parent_state_bytes) is not bytes
        or sha256(parent_state_bytes).hexdigest() != _MISTY_DEFERRED20_PARENT_SHA256):
        raise ValueError("deferred20 fixture requires exact isolated TRAIN source")
    if int(memory[RamAddress.CURRENT_MAP]) != int(MapId.CERULEAN_GYM) or int(memory[RamAddress.STATUS_FLAGS_4]) & 1:
        raise ValueError("deferred20 fixture requires original field boundary")
    for flag in (int(EventFlag.BEAT_MISTY), int(EventFlag.GOT_TM11)):
        if int(memory[int(RamAddress.EVENT_FLAGS) + flag // 8]) & (1 << (flag % 8)):
            raise ValueError("deferred20 fixture cannot erase earned Misty progress")
    reader = PokemonRedPartyReader(SimpleNamespace(read_u8=lambda a: int(memory[a])))
    party = reader.read()
    refs = reader.preparation_specimen_refs()
    expected = ((179, 17), (165, 19), (150, 18), (113, 7), (5, 12), (108, 10))
    if (tuple((m.species_id, m.level) for m in party.members) != expected
        or int(memory[int(RamAddress.PARTY_SPECIES) + 6]) != 255
        or any(m.status is not StatusCondition.HEALTHY or m.hp != m.max_hp for m in party.members)):
        raise ValueError("deferred20 source requires exact healthy six-party roster")
    base = member_field_address(1, SPECIES_OFFSET)
    species = RedPracticeCartridge(rom).species(165)
    dvs = (8, 8, 8, 9)
    if (species.national_number != 19 or int(memory[base + _PARTY_BOX_LEVEL_OFFSET]) != 19
        or tuple(int(memory[base + DETERMINANT_VALUES_OFFSET + i]) for i in range(2)) != (0x88, 0x89)
        or any(int(memory[base + _PARTY_STAT_EXP_OFFSET + i]) != 0 for i in range(10))
        or party.members[1].experience != species.experience_at_level(19)
        or _stats(memory, base + PARTY_MAX_HP_OFFSET) != species.stats_with_dvs(19, dvs)
        or tuple(m.move_id for m in party.members[1].moves) != (33, 39, 98, 158)
        or any(m.current_pp != m.max_pp for m in party.members[1].moves)):
        raise ValueError("deferred20 source Rattata XP, DVs, zero-EVs, stats or moves differ")
    stats = species.stats_with_dvs(20, dvs)
    staged = _StagedMemory(memory)
    staged[base + _PARTY_BOX_LEVEL_OFFSET] = staged[base + PARTY_LEVEL_OFFSET] = 20
    _put_u24(staged, base + EXPERIENCE_OFFSET, species.experience_at_level(20))
    _put_stats(staged, base + PARTY_MAX_HP_OFFSET, stats)
    _put_u16(staged, base + PARTY_HP_OFFSET, stats.max_hp)
    projected = PokemonRedPartyReader(SimpleNamespace(read_u8=lambda a: int(staged[a])))
    target = projected.read().members[1]
    if (projected.preparation_specimen_refs() != refs or target.species_id != 165
        or target.level != 20 or target.experience != species.experience_at_level(20)
        or target.hp != target.max_hp or target.moves != party.members[1].moves):
        raise ValueError("deferred20 staged native party readback differs")
    return _apply_fixture_changes(memory, staged.changes)
