"""Teacher-only Red adapter for a narrow, cartridge-verified battle factory.

Write authority is deliberately absent from model/executor interfaces. Only an
isolated emulator copy may call this adapter; it never edits a save on disk.
Supported axes are both Gen I species, moves/PP, levels, five-stat blocks,
current HP, reserve party slots and real trainer opponent rosters. The game,
not this teacher, owns trainer AI after an isolated state is materialized.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .battle_practice_factory import (
    BattlePracticeError,
    BattlePracticeSpec,
    PracticeMove,
    PracticeStats,
)
from .observation import (
    PARTY_HP_OFFSET,
    PARTY_LEVEL_OFFSET,
    PARTY_MAX_HP_OFFSET,
    PARTY_MOVES_OFFSET,
    PARTY_PP_OFFSET,
    PARTY_SPECIES_OFFSET,
    PARTY_STATUS_OFFSET,
    PARTY_STRUCT_STRIDE,
    BattleMenuPhase,
    PokemonRedStateReader,
    RamAddress,
)
from .red_battle_catalog import PokemonRedBattleCatalog
from .red_battle_practice_cartridge import RedPracticeCartridge, RedPracticeSpecies
from .red_battle_scenario import prepare_red_battle_scenario
from .red_pokedex import NICKNAME_LENGTH, PARTY_NICKNAMES_BASE
from .red_trajectory import PokemonRedObservationEncoder

_BATTLE_MOVES = 0xD01C  # pinned wBattleMonMoves, mirrored in active party struct
_BATTLE_PP = 0xD02D  # pinned wBattleMonPP, mirrored in active party struct
_BATTLE_HP = 0xD015
_BATTLE_BOX_LEVEL = 0xD017
_BATTLE_LEVEL = 0xD022
_BATTLE_MAX_HP = 0xD023
_ENEMY_BOX_LEVEL = 0xCFE8
_PLAYER_UNMODIFIED_LEVEL = 0xCD0F
_ENEMY_UNMODIFIED_LEVEL = int(RamAddress.ENEMY_UNMODIFIED_LEVEL)
_PARTY_BOX_LEVEL_OFFSET = 3
_PARTY_EXPERIENCE_OFFSET = 14
_PARTY_STAT_EXP_OFFSET = 17
_PARTY_DVS_OFFSET = 27
_BATTLE_SPECIES = 0xD014
_BATTLE_SPECIES_2 = 0xCFD9
_BATTLE_TYPES = 0xD019
_BATTLE_CATCH_RATE = 0xD01B
_BATTLE_DVS = 0xD020
_ENEMY_TYPES = int(RamAddress.ENEMY_TYPE_1)
_ENEMY_CATCH_RATE = 0xCFEC
_ENEMY_PP = 0xCFFE
_ENEMY_DVS = 0xCFF1
_ENEMY_BASE_STATS = 0xD002
_ENEMY_ACTUAL_CATCH_RATE = 0xD007
_ENEMY_BASE_EXP = 0xD008
_ENEMY_PARTY_OT = 0xD9AC
_PARTY_OT = 0xD273


def _u16(memory: WritableRedMemory, address: int) -> int:
    return memory[address] * 256 + memory[address + 1]


def _put_u16(memory: WritableRedMemory, address: int, value: int) -> None:
    memory[address] = value >> 8
    memory[address + 1] = value & 0xFF


def _stats(memory: WritableRedMemory, base: int) -> PracticeStats:
    return PracticeStats(*(_u16(memory, base + offset) for offset in (0, 2, 4, 6, 8)))


def _put_stats(memory: WritableRedMemory, base: int, stats: PracticeStats) -> None:
    for offset, value in zip(
        (0, 2, 4, 6, 8),
        (
            stats.max_hp,
            stats.attack,
            stats.defense,
            stats.speed,
            stats.special,
        ),
        strict=True,
    ):
        _put_u16(memory, base + offset, value)


def _put_u24(memory: WritableRedMemory, address: int, value: int) -> None:
    for offset in range(3):
        memory[address + offset] = (value >> (16 - 8 * offset)) & 0xFF


def _resolved_moves(
    moves: tuple[PracticeMove, ...],
    catalog: PokemonRedBattleCatalog,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    move_ids: list[int] = []
    pp_values: list[int] = []
    for move in moves:
        try:
            mechanics = catalog.resolve_move(move.move_ref)
            move_id = int(move.move_ref.rsplit(":", 1)[1])
            pp = move.pp
        except (ValueError, IndexError) as error:
            raise BattlePracticeError("Red practice move reference differs") from error
        if pp > mechanics.max_pp or move_id not in catalog.move_ids:
            raise BattlePracticeError("Red practice PP exceeds unboosted move capacity")
        move_ids.append(move_id)
        pp_values.append(pp)
    return tuple((move_ids + [0] * 4)[:4]), tuple((pp_values + [0] * 4)[:4])


class WritableRedMemory(Protocol):
    def __getitem__(self, address: int) -> int: ...

    def __setitem__(self, address: int, value: int) -> None: ...


@dataclass(frozen=True, slots=True)
class RedPracticeReceipt:
    source_state_sha256: str
    root_lineage_id: str
    configuration_sha256: str
    actor_species_id: int
    actor_level: int
    opponent_species_id: int
    opponent_level: int
    actor_move_ids: tuple[int, ...]
    actor_pp: tuple[int, ...]
    opponent_hp: int
    opponent_max_hp: int
    observation_sha256: str
    legal_move_count: int
    actor_hp: int | None = None
    actor_stats: PracticeStats | None = None
    opponent_stats: PracticeStats | None = None
    opponent_move_ids: tuple[int, ...] | None = None
    opponent_pp: tuple[int, ...] | None = None
    actor_experience: int | None = None
    party_reserves: tuple[dict[str, object], ...] | None = None
    opponent_party: tuple[dict[str, object], ...] | None = None
    battle_kind: str = "wild"
    player_party_count: int | None = None

    def public_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema": "pokemon.red.teacher-battle-practice-receipt.v1",
            "assistance": "isolated_teacher_memory_intervention",
            "partition": "train",
            "source_state_sha256": self.source_state_sha256,
            "root_lineage_id": self.root_lineage_id,
            "configuration_sha256": self.configuration_sha256,
            "actor_species_id": self.actor_species_id,
            "actor_level": self.actor_level,
            "opponent_species_id": self.opponent_species_id,
            "opponent_level": self.opponent_level,
            "actor_move_ids": list(self.actor_move_ids),
            "actor_pp": list(self.actor_pp),
            "opponent_hp": self.opponent_hp,
            "opponent_max_hp": self.opponent_max_hp,
            "observation_sha256": self.observation_sha256,
            "legal_move_count": self.legal_move_count,
            "new_independent_upstream_roots": 0,
            "fit_allowed_without_outcomes": False,
            "final_player_action": False,
        }
        if (
            self.actor_stats is not None
            or self.opponent_stats is not None
            or self.actor_hp is not None
        ):
            result.update(
                actor_hp=self.actor_hp,
                actor_stats=self.actor_stats.public_dict() if self.actor_stats else None,
                opponent_stats=self.opponent_stats.public_dict() if self.opponent_stats else None,
            )
        if self.opponent_move_ids is not None:
            result["opponent_move_ids"] = list(self.opponent_move_ids)
            result["opponent_pp"] = list(self.opponent_pp or ())
        if self.actor_experience is not None:
            result["actor_experience"] = self.actor_experience
        if self.party_reserves is not None:
            result["party_reserves"] = list(self.party_reserves)
        if self.opponent_party is not None:
            result["opponent_party"] = list(self.opponent_party)
        if self.battle_kind == "trainer":
            result["schema"] = "pokemon.red.teacher-battle-practice-receipt.v2"
            result["battle_kind"] = "trainer"
            result["player_party_count"] = self.player_party_count
        return result


def materialize_red_train_practice(
    reader: PokemonRedStateReader,
    memory: WritableRedMemory,
    spec: BattlePracticeSpec,
    *,
    cartridge: RedPracticeCartridge | None = None,
) -> RedPracticeReceipt:
    """Edit a private battle copy and verify its semantic readback.

    The caller authenticates loaded source bytes against ``spec`` and owns the
    emulator lifetime. Failed materializations must be discarded, never saved.
    """

    if not isinstance(spec, BattlePracticeSpec):
        raise BattlePracticeError("practice specification differs")
    before = reader.read()
    if (
        before.battle_state != (1 if spec.battle_kind == "wild" else 2)
        or before.map_id is None
        or before.active_party_index is None
        or before.active_party_species_id is None
        or before.active_party_level is None
        or before.enemy_species_id is None
        or before.enemy_level is None
        or before.enemy_hp is None
        or before.enemy_hp <= 0
        or before.enemy_max_hp is None
        or before.battler_moves != before.active_party_moves
        or before.battler_pp != before.active_party_pp
        or reader.read_battle_menu_state(before).phase is not BattleMenuPhase.MAIN
    ):
        raise BattlePracticeError("source is not a supported live battle MAIN boundary")
    if spec.battle_kind == "wild":
        identity = reader.read_wild_capture_identity()
        if (
            identity is None
            or identity.transformed
            or identity.original_species_id != identity.displayed_species_id
        ):
            raise BattlePracticeError("transformed or ambiguous opponent is unsupported")
    elif (
        before.enemy_party_count is None
        or before.enemy_party_position is None
        or before.enemy_party_hp is None
        or not 0 <= before.enemy_party_position < before.enemy_party_count
    ):
        raise BattlePracticeError("source trainer roster is unavailable")
    catalog = PokemonRedBattleCatalog()
    padded_moves, padded_pp = _resolved_moves(spec.actor_moves, catalog)
    enemy_moves, enemy_pp = (
        _resolved_moves(spec.opponent_moves, catalog)
        if spec.opponent_moves is not None
        else (None, None)
    )
    if (
        spec.actor_species_ref is not None
        or spec.opponent_species_ref is not None
        or spec.party_reserves is not None
        or spec.battle_kind == "trainer"
    ) and cartridge is None:
        raise BattlePracticeError("species practice requires authenticated cartridge data")
    try:
        actor_species_id = (
            int(spec.actor_species_ref.rsplit(":", 1)[1])
            if spec.actor_species_ref is not None
            else before.active_party_species_id
        )
        opponent_species_id = (
            int(spec.opponent_species_ref.rsplit(":", 1)[1])
            if spec.opponent_species_ref is not None
            else before.enemy_species_id
        )
        if spec.actor_species_ref is not None:
            catalog.resolve_species(spec.actor_species_ref)
        if spec.opponent_species_ref is not None:
            catalog.resolve_species(spec.opponent_species_ref)
    except (ValueError, IndexError) as error:
        raise BattlePracticeError("Red practice species reference differs") from error
    assert actor_species_id is not None and opponent_species_id is not None
    actor_level = spec.actor_level or before.active_party_level
    opponent_level = spec.opponent_level or before.enemy_level
    assert actor_level is not None and opponent_level is not None
    actor_data = cartridge.species(actor_species_id) if cartridge else None
    opponent_data = cartridge.species(opponent_species_id) if cartridge else None
    actor_auto_stats = (
        spec.actor_stats is None
        and actor_data is not None
        and (spec.actor_species_ref is not None or spec.actor_level is not None)
    )
    opponent_auto_stats = (
        spec.opponent_stats is None
        and opponent_data is not None
        and (spec.opponent_species_ref is not None or spec.opponent_level is not None)
    )
    actor_stats = spec.actor_stats or (
        actor_data.neutral_stats(actor_level)
        if actor_auto_stats and actor_data is not None
        else None
    )
    opponent_stats = spec.opponent_stats or (
        opponent_data.neutral_stats(opponent_level)
        if opponent_auto_stats and opponent_data is not None
        else None
    )
    opponent_max_hp = opponent_stats.max_hp if opponent_stats else before.enemy_max_hp
    if opponent_max_hp is None or spec.opponent_hp > opponent_max_hp:
        raise BattlePracticeError("practice opponent HP exceeds maximum")
    active_base = int(RamAddress.PARTY_MON_1) + before.active_party_index * PARTY_STRUCT_STRIDE
    actor_max_hp = actor_stats.max_hp if actor_stats else before.active_party_max_hp
    actor_hp = (
        spec.actor_hp
        if spec.actor_hp is not None
        else actor_max_hp
        if spec.actor_species_ref is not None
        else before.active_party_hp
    )
    if actor_hp is None or actor_max_hp is None or actor_hp > actor_max_hp:
        raise BattlePracticeError("practice actor HP exceeds maximum")

    # Resolve and validate the entire proposed team before touching emulator RAM.
    resolved_reserves: list[
        tuple[int, int, int, PracticeStats, tuple[int, ...], tuple[int, ...], RedPracticeSpecies]
    ] = []
    target_party_count = before.party_count
    if spec.party_reserves is not None:
        assert cartridge is not None
        if (
            before.party_count is None
            or before.party_species_ids is None
            or not 1 <= before.party_count <= 6
        ):
            raise BattlePracticeError("source party inventory is unavailable")
        target_party_count = max(
            before.party_count, *(reserve.party_slot for reserve in spec.party_reserves)
        )
        added = set(range(before.party_count, target_party_count))
        declared = {reserve.party_slot - 1 for reserve in spec.party_reserves}
        if not added <= declared:
            raise BattlePracticeError("new party slots must be declared contiguously")
        if target_party_count != before.party_count and (
            memory[int(RamAddress.PARTY_COUNT)] != before.party_count
            or memory[int(RamAddress.PARTY_SPECIES) + before.party_count] != 0xFF
        ):
            raise BattlePracticeError("source player party roster differs")
        for reserve in spec.party_reserves:
            index = reserve.party_slot - 1
            if index == before.active_party_index:
                raise BattlePracticeError("reserve slot cannot be active")
            try:
                catalog.resolve_species(reserve.species_ref)
                species_id = int(reserve.species_ref.rsplit(":", 1)[1])
            except (ValueError, IndexError) as error:
                raise BattlePracticeError("reserve species reference differs") from error
            species_data = cartridge.species(species_id)
            stats = reserve.stats or species_data.neutral_stats(reserve.level)
            hp = reserve.hp if reserve.hp is not None else stats.max_hp
            if hp > stats.max_hp:
                raise BattlePracticeError("reserve HP exceeds maximum")
            moves, pp = _resolved_moves(reserve.moves, catalog)
            base = int(RamAddress.PARTY_MON_1) + index * PARTY_STRUCT_STRIDE
            if index < before.party_count and (
                memory[int(RamAddress.PARTY_SPECIES) + index] != before.party_species_ids[index]
                or memory[base + PARTY_SPECIES_OFFSET] != before.party_species_ids[index]
            ):
                raise BattlePracticeError("source reserve species mirrors differ")
            resolved_reserves.append((index, species_id, hp, stats, moves, pp, species_data))

    resolved_enemy_reserves: list[
        tuple[
            int, int, int, int, PracticeStats, tuple[int, ...], tuple[int, ...], RedPracticeSpecies
        ]
    ] = []
    if spec.battle_kind == "trainer":
        assert cartridge is not None
        assert before.enemy_party_position is not None
        assert spec.opponent_party_count is not None
        active_index = before.enemy_party_position
        count = spec.opponent_party_count
        if active_index >= count:
            raise BattlePracticeError("trainer active opponent is outside declared team")
        reserves_by_index = {
            reserve.party_slot - 1: reserve for reserve in spec.opponent_reserves or ()
        }
        if set(reserves_by_index) != set(range(count)) - {active_index}:
            raise BattlePracticeError("trainer team must declare every non-active member")
        if (
            memory[int(RamAddress.ENEMY_PARTY_COUNT)] != before.enemy_party_count
            or memory[int(RamAddress.ENEMY_MON_PARTY_POS)] != active_index
            or memory[int(RamAddress.ENEMY_PARTY_SPECIES) + active_index] != before.enemy_species_id
            or memory[int(RamAddress.ENEMY_PARTY_MON_1) + active_index * PARTY_STRUCT_STRIDE]
            != before.enemy_species_id
        ):
            raise BattlePracticeError("source trainer roster mirrors differ")
        for index, reserve in reserves_by_index.items():
            try:
                catalog.resolve_species(reserve.species_ref)
                species_id = int(reserve.species_ref.rsplit(":", 1)[1])
            except (ValueError, IndexError) as error:
                raise BattlePracticeError("trainer reserve species reference differs") from error
            data = cartridge.species(species_id)
            stats = reserve.stats or data.neutral_stats(reserve.level)
            hp = reserve.hp if reserve.hp is not None else stats.max_hp
            if hp > stats.max_hp:
                raise BattlePracticeError("trainer reserve HP exceeds maximum")
            moves, pp = _resolved_moves(reserve.moves, catalog)
            resolved_enemy_reserves.append(
                (index, species_id, reserve.level, hp, stats, moves, pp, data)
            )
    resolved_enemy_members: list[
        tuple[
            int, int, int, int, PracticeStats, tuple[int, ...], tuple[int, ...], RedPracticeSpecies
        ]
    ] = []
    if spec.battle_kind == "trainer":
        assert before.enemy_party_position is not None
        assert opponent_stats is not None and opponent_data is not None
        assert enemy_moves is not None and enemy_pp is not None
        resolved_enemy_members = [
            (
                before.enemy_party_position,
                opponent_species_id,
                opponent_level,
                spec.opponent_hp,
                opponent_stats,
                enemy_moves,
                enemy_pp,
                opponent_data,
            ),
            *resolved_enemy_reserves,
        ]

    # Battle, party and unmodified stat blocks are distinct Gen I copies.
    # Verify the source mirror before editing, then verify every edited copy.
    changing_combatants = any(
        value is not None
        for value in (
            spec.actor_level,
            spec.opponent_level,
            spec.actor_stats,
            spec.opponent_stats,
            spec.actor_hp,
            spec.actor_species_ref,
            spec.opponent_species_ref,
        )
    )
    if changing_combatants and (
        memory[_BATTLE_LEVEL] != before.active_party_level
        or memory[_PLAYER_UNMODIFIED_LEVEL] != before.active_party_level
        or memory[_ENEMY_UNMODIFIED_LEVEL] != before.enemy_level
        or _u16(memory, _BATTLE_HP) != before.active_party_hp
        or _u16(memory, _BATTLE_MAX_HP) != before.active_party_max_hp
    ):
        raise BattlePracticeError("source battle and party mirrors differ")
    if (spec.actor_species_ref is not None or spec.opponent_species_ref is not None) and (
        memory[_BATTLE_SPECIES] != before.active_party_species_id
        or memory[_BATTLE_SPECIES_2] != before.active_party_species_id
        or memory[int(RamAddress.ENEMY_SPECIES_2)] != before.enemy_species_id
        or memory[int(RamAddress.PARTY_SPECIES) + before.active_party_index]
        != before.active_party_species_id
    ):
        raise BattlePracticeError("source species mirrors differ")
    if spec.actor_species_ref is not None:
        assert actor_data is not None
        memory[int(RamAddress.PARTY_SPECIES) + before.active_party_index] = actor_species_id
        memory[active_base + PARTY_SPECIES_OFFSET] = actor_species_id
        memory[_BATTLE_SPECIES] = actor_species_id
        memory[_BATTLE_SPECIES_2] = actor_species_id
        for base in (active_base + 5, _BATTLE_TYPES):
            memory[base], memory[base + 1] = actor_data.types
        memory[active_base + 7] = actor_data.catch_rate
        memory[_BATTLE_CATCH_RATE] = actor_data.catch_rate
    if spec.opponent_species_ref is not None:
        assert opponent_data is not None
        memory[int(RamAddress.ENEMY_SPECIES)] = opponent_species_id
        memory[int(RamAddress.ENEMY_SPECIES_2)] = opponent_species_id
        memory[_ENEMY_TYPES], memory[_ENEMY_TYPES + 1] = opponent_data.types
        memory[_ENEMY_CATCH_RATE] = opponent_data.catch_rate
        memory[_ENEMY_ACTUAL_CATCH_RATE] = opponent_data.catch_rate
        memory[_ENEMY_BASE_EXP] = opponent_data.base_experience
        for index, value in enumerate(opponent_data.base_stats):
            memory[_ENEMY_BASE_STATS + index] = value
    if spec.actor_level is not None:
        for address in (
            active_base + _PARTY_BOX_LEVEL_OFFSET,
            active_base + PARTY_LEVEL_OFFSET,
            _BATTLE_BOX_LEVEL,
            _BATTLE_LEVEL,
            _PLAYER_UNMODIFIED_LEVEL,
        ):
            memory[address] = actor_level
    if spec.opponent_level is not None:
        level_addresses = (
            (int(RamAddress.ENEMY_LEVEL), _ENEMY_UNMODIFIED_LEVEL)
            if spec.battle_kind == "trainer"
            else (_ENEMY_BOX_LEVEL, int(RamAddress.ENEMY_LEVEL), _ENEMY_UNMODIFIED_LEVEL)
        )
        for address in level_addresses:
            memory[address] = opponent_level
    if actor_stats is not None:
        _put_stats(memory, active_base + PARTY_MAX_HP_OFFSET, actor_stats)
        _put_stats(memory, _BATTLE_MAX_HP, actor_stats)
        _put_stats(memory, _PLAYER_UNMODIFIED_LEVEL + 1, actor_stats)
    if opponent_stats is not None:
        _put_stats(memory, int(RamAddress.ENEMY_MAX_HP), opponent_stats)
        _put_stats(memory, _ENEMY_UNMODIFIED_LEVEL + 1, opponent_stats)
    if actor_auto_stats:
        for index in range(10):
            memory[active_base + _PARTY_STAT_EXP_OFFSET + index] = 0
        for base in (active_base + _PARTY_DVS_OFFSET, _BATTLE_DVS):
            memory[base], memory[base + 1] = 0x88, 0x88
    if opponent_auto_stats:
        memory[_ENEMY_DVS], memory[_ENEMY_DVS + 1] = 0x88, 0x88
    actor_experience = (
        actor_data.experience_at_level(actor_level)
        if actor_data is not None
        and (spec.actor_species_ref is not None or spec.actor_level is not None)
        else None
    )
    if actor_experience is not None:
        _put_u24(memory, active_base + _PARTY_EXPERIENCE_OFFSET, actor_experience)
    if spec.actor_hp is not None or spec.actor_species_ref is not None:
        _put_u16(memory, active_base + PARTY_HP_OFFSET, actor_hp)
        _put_u16(memory, _BATTLE_HP, actor_hp)
    for index, (move_id, move_pp) in enumerate(zip(padded_moves, padded_pp, strict=True)):
        memory[_BATTLE_MOVES + index] = move_id
        memory[_BATTLE_PP + index] = move_pp
        memory[active_base + PARTY_MOVES_OFFSET + index] = move_id
        memory[active_base + PARTY_PP_OFFSET + index] = move_pp
    if enemy_moves is not None and enemy_pp is not None:
        for index, (move_id, move_pp) in enumerate(zip(enemy_moves, enemy_pp, strict=True)):
            memory[int(RamAddress.ENEMY_MOVES) + index] = move_id
            memory[_ENEMY_PP + index] = move_pp
    memory[int(RamAddress.ENEMY_HP)] = spec.opponent_hp >> 8
    memory[int(RamAddress.ENEMY_HP) + 1] = spec.opponent_hp & 0xFF

    if target_party_count is not None and target_party_count != before.party_count:
        assert before.party_count is not None
        assert before.active_party_index is not None
        original_ot = tuple(
            memory[_PARTY_OT + before.active_party_index * NICKNAME_LENGTH + offset]
            for offset in range(NICKNAME_LENGTH)
        )
        memory[int(RamAddress.PARTY_COUNT)] = target_party_count
        memory[int(RamAddress.PARTY_SPECIES) + target_party_count] = 0xFF
        for index in range(before.party_count, target_party_count):
            for offset, value in enumerate(original_ot):
                memory[_PARTY_OT + index * NICKNAME_LENGTH + offset] = value

    for index, species_id, hp, stats, moves, pp, data in resolved_reserves:
        base = int(RamAddress.PARTY_MON_1) + index * PARTY_STRUCT_STRIDE
        reserve = next(item for item in spec.party_reserves or () if item.party_slot == index + 1)
        memory[int(RamAddress.PARTY_SPECIES) + index] = species_id
        memory[base + PARTY_SPECIES_OFFSET] = species_id
        _put_u16(memory, base + PARTY_HP_OFFSET, hp)
        memory[base + _PARTY_BOX_LEVEL_OFFSET] = reserve.level
        memory[base + PARTY_LEVEL_OFFSET] = reserve.level
        memory[base + PARTY_STATUS_OFFSET] = 0
        memory[base + 5], memory[base + 6] = data.types
        memory[base + 7] = data.catch_rate
        _put_u24(memory, base + _PARTY_EXPERIENCE_OFFSET, data.experience_at_level(reserve.level))
        for offset in range(10):
            memory[base + _PARTY_STAT_EXP_OFFSET + offset] = 0
        memory[base + _PARTY_DVS_OFFSET], memory[base + _PARTY_DVS_OFFSET + 1] = 0x88, 0x88
        _put_stats(memory, base + PARTY_MAX_HP_OFFSET, stats)
        for offset, (move, amount) in enumerate(zip(moves, pp, strict=True)):
            memory[base + PARTY_MOVES_OFFSET + offset] = move
            memory[base + PARTY_PP_OFFSET + offset] = amount
        for offset, value in enumerate(data.nickname_bytes):
            memory[PARTY_NICKNAMES_BASE + index * NICKNAME_LENGTH + offset] = value

    if spec.battle_kind == "trainer":
        assert spec.opponent_party_count is not None
        memory[int(RamAddress.ENEMY_PARTY_COUNT)] = spec.opponent_party_count
        for index in range(6):
            memory[int(RamAddress.ENEMY_PARTY_SPECIES) + index] = 0
        memory[int(RamAddress.ENEMY_PARTY_SPECIES) + spec.opponent_party_count] = 0xFF
        for index, species_id, level, hp, stats, moves, pp, data in resolved_enemy_members:
            base = int(RamAddress.ENEMY_PARTY_MON_1) + index * PARTY_STRUCT_STRIDE
            memory[int(RamAddress.ENEMY_PARTY_SPECIES) + index] = species_id
            memory[base + PARTY_SPECIES_OFFSET] = species_id
            _put_u16(memory, base + PARTY_HP_OFFSET, hp)
            memory[base + _PARTY_BOX_LEVEL_OFFSET] = level
            memory[base + PARTY_LEVEL_OFFSET] = level
            memory[base + PARTY_STATUS_OFFSET] = 0
            memory[base + 5], memory[base + 6] = data.types
            memory[base + 7] = data.catch_rate
            _put_u24(memory, base + _PARTY_EXPERIENCE_OFFSET, data.experience_at_level(level))
            for offset in range(10):
                memory[base + _PARTY_STAT_EXP_OFFSET + offset] = 0
            memory[base + _PARTY_DVS_OFFSET], memory[base + _PARTY_DVS_OFFSET + 1] = 0x88, 0x88
            _put_stats(memory, base + PARTY_MAX_HP_OFFSET, stats)
            for offset, (move, amount) in enumerate(zip(moves, pp, strict=True)):
                memory[base + PARTY_MOVES_OFFSET + offset] = move
                memory[base + PARTY_PP_OFFSET + offset] = amount
            for offset, value in enumerate(data.nickname_bytes):
                memory[int(RamAddress.ENEMY_PARTY_NICKNAMES) + index * NICKNAME_LENGTH + offset] = (
                    value
                )

    after = reader.read()
    if (
        target_party_count is not None
        and target_party_count != before.party_count
        and (
            after.party_count != target_party_count
            or memory[int(RamAddress.PARTY_SPECIES) + target_party_count] != 0xFF
        )
    ):
        raise BattlePracticeError("assisted player party count did not read back")
    if spec.battle_kind == "trainer":
        assert spec.opponent_party_count is not None
        if (
            after.enemy_party_count != spec.opponent_party_count
            or after.enemy_party_position != before.enemy_party_position
            or after.enemy_party_hp is None
            or memory[int(RamAddress.ENEMY_PARTY_SPECIES) + spec.opponent_party_count] != 0xFF
        ):
            raise BattlePracticeError("assisted trainer roster did not read back consistently")
        for index, species_id, level, hp, stats, moves, pp, data in resolved_enemy_members:
            base = int(RamAddress.ENEMY_PARTY_MON_1) + index * PARTY_STRUCT_STRIDE
            if (
                after.enemy_party_hp[index] != hp
                or memory[int(RamAddress.ENEMY_PARTY_SPECIES) + index] != species_id
                or memory[base + PARTY_SPECIES_OFFSET] != species_id
                or _u16(memory, base + PARTY_HP_OFFSET) != hp
                or memory[base + _PARTY_BOX_LEVEL_OFFSET] != level
                or memory[base + PARTY_LEVEL_OFFSET] != level
                or memory[base + PARTY_STATUS_OFFSET] != 0
                or tuple(memory[base + 5 + offset] for offset in range(2)) != data.types
                or memory[base + 7] != data.catch_rate
                or tuple(memory[base + PARTY_MOVES_OFFSET + offset] for offset in range(4)) != moves
                or tuple(memory[base + PARTY_PP_OFFSET + offset] for offset in range(4)) != pp
                or _stats(memory, base + PARTY_MAX_HP_OFFSET) != stats
                or tuple(
                    memory[int(RamAddress.ENEMY_PARTY_NICKNAMES) + index * NICKNAME_LENGTH + offset]
                    for offset in range(NICKNAME_LENGTH)
                )
                != tuple(data.nickname_bytes)
            ):
                raise BattlePracticeError("assisted trainer member did not read back consistently")
    for index, species_id, hp, stats, moves, pp, data in resolved_reserves:
        base = int(RamAddress.PARTY_MON_1) + index * PARTY_STRUCT_STRIDE
        reserve = next(item for item in spec.party_reserves or () if item.party_slot == index + 1)
        if (
            after.party_species_ids is None
            or after.party_species_ids[index] != species_id
            or after.party_hp is None
            or after.party_hp[index] != hp
            or after.party_max_hp is None
            or after.party_max_hp[index] != stats.max_hp
            or after.party_levels is None
            or after.party_levels[index] != reserve.level
            or after.party_status is None
            or after.party_status[index] != 0
            or after.party_moves is None
            or after.party_moves[index] != moves
            or after.party_pp is None
            or after.party_pp[index] != pp
            or memory[base + _PARTY_BOX_LEVEL_OFFSET] != reserve.level
            or tuple(memory[base + 5 + offset] for offset in range(2)) != data.types
            or memory[base + 7] != data.catch_rate
            or _stats(memory, base + PARTY_MAX_HP_OFFSET) != stats
            or tuple(memory[base + _PARTY_EXPERIENCE_OFFSET + offset] for offset in range(3))
            != tuple(data.experience_at_level(reserve.level).to_bytes(3, "big"))
            or tuple(memory[base + _PARTY_STAT_EXP_OFFSET + offset] for offset in range(10))
            != (0,) * 10
            or (memory[base + _PARTY_DVS_OFFSET], memory[base + _PARTY_DVS_OFFSET + 1])
            != (0x88, 0x88)
            or tuple(
                memory[PARTY_NICKNAMES_BASE + index * NICKNAME_LENGTH + offset]
                for offset in range(NICKNAME_LENGTH)
            )
            != tuple(data.nickname_bytes)
        ):
            raise BattlePracticeError("assisted reserve did not read back consistently")
    if (
        after.map_id != before.map_id
        or after.battle_state != before.battle_state
        or after.active_party_index != before.active_party_index
        or after.active_party_species_id != actor_species_id
        or after.active_party_level != actor_level
        or after.active_party_hp != actor_hp
        or after.active_party_max_hp != actor_max_hp
        or after.enemy_species_id != opponent_species_id
        or after.enemy_level != opponent_level
        or after.enemy_max_hp != opponent_max_hp
        or after.enemy_hp != spec.opponent_hp
        or after.battler_moves != padded_moves
        or after.battler_pp != padded_pp
        or after.active_party_moves != padded_moves
        or after.active_party_pp != padded_pp
        or tuple(memory[_BATTLE_MOVES + index] for index in range(4)) != padded_moves
        or tuple(memory[_BATTLE_PP + index] for index in range(4)) != padded_pp
        or (
            spec.actor_level is not None
            and any(
                memory[address] != actor_level
                for address in (
                    active_base + _PARTY_BOX_LEVEL_OFFSET,
                    _BATTLE_BOX_LEVEL,
                    _BATTLE_LEVEL,
                    _PLAYER_UNMODIFIED_LEVEL,
                )
            )
        )
        or (
            spec.opponent_level is not None
            and any(
                memory[address] != opponent_level
                for address in (
                    (_ENEMY_UNMODIFIED_LEVEL,)
                    if spec.battle_kind == "trainer"
                    else (_ENEMY_BOX_LEVEL, _ENEMY_UNMODIFIED_LEVEL)
                )
            )
        )
        or (
            actor_stats is not None
            and any(
                _stats(memory, base) != actor_stats
                for base in (
                    active_base + PARTY_MAX_HP_OFFSET,
                    _BATTLE_MAX_HP,
                    _PLAYER_UNMODIFIED_LEVEL + 1,
                )
            )
        )
        or (
            opponent_stats is not None
            and any(
                _stats(memory, base) != opponent_stats
                for base in (
                    int(RamAddress.ENEMY_MAX_HP),
                    _ENEMY_UNMODIFIED_LEVEL + 1,
                )
            )
        )
        or (
            (spec.actor_hp is not None or spec.actor_species_ref is not None)
            and _u16(memory, _BATTLE_HP) != actor_hp
        )
        or (
            spec.actor_species_ref is not None
            and (
                actor_data is None
                or memory[int(RamAddress.PARTY_SPECIES) + before.active_party_index]
                != actor_species_id
                or memory[_BATTLE_SPECIES] != actor_species_id
                or memory[_BATTLE_SPECIES_2] != actor_species_id
                or tuple(memory[_BATTLE_TYPES + i] for i in range(2)) != actor_data.types
                or tuple(memory[active_base + 5 + i] for i in range(2)) != actor_data.types
                or memory[_BATTLE_CATCH_RATE] != actor_data.catch_rate
            )
        )
        or (
            spec.opponent_species_ref is not None
            and (
                opponent_data is None
                or memory[int(RamAddress.ENEMY_SPECIES_2)] != opponent_species_id
                or tuple(memory[_ENEMY_TYPES + i] for i in range(2)) != opponent_data.types
                or memory[_ENEMY_CATCH_RATE] != opponent_data.catch_rate
                or memory[_ENEMY_ACTUAL_CATCH_RATE] != opponent_data.catch_rate
                or memory[_ENEMY_BASE_EXP] != opponent_data.base_experience
                or tuple(memory[_ENEMY_BASE_STATS + i] for i in range(5))
                != opponent_data.base_stats
            )
        )
        or (
            enemy_moves is not None
            and (
                tuple(memory[int(RamAddress.ENEMY_MOVES) + i] for i in range(4)) != enemy_moves
                or tuple(memory[_ENEMY_PP + i] for i in range(4)) != enemy_pp
            )
        )
        or (
            actor_experience is not None
            and (
                tuple(memory[active_base + _PARTY_EXPERIENCE_OFFSET + i] for i in range(3))
                != tuple(actor_experience.to_bytes(3, "big"))
            )
        )
    ):
        raise BattlePracticeError("assisted battle did not read back consistently")
    if spec.opponent_species_ref is not None and spec.battle_kind == "wild":
        assert opponent_data is not None
        after_identity = reader.read_wild_capture_identity()
        if (
            after_identity is None
            or after_identity.original_species_id != opponent_species_id
            or after_identity.displayed_species_id != opponent_species_id
            or after_identity.type_ids != opponent_data.types
        ):
            raise BattlePracticeError("assisted wild identity did not read back")
    prepared = prepare_red_battle_scenario(
        PokemonRedObservationEncoder.from_state_reader(reader), after
    )
    legal_count = sum(prepared.supported_candidate_mask)
    if legal_count < 2:
        raise BattlePracticeError("assisted battle lacks two legal damaging moves")
    return RedPracticeReceipt(
        source_state_sha256=spec.source_state_sha256,
        root_lineage_id=spec.root_lineage_id,
        configuration_sha256=spec.configuration_sha256,
        actor_species_id=after.active_party_species_id,
        actor_level=after.active_party_level,
        opponent_species_id=after.enemy_species_id,
        opponent_level=after.enemy_level,
        actor_move_ids=padded_moves,
        actor_pp=padded_pp,
        opponent_hp=after.enemy_hp,
        opponent_max_hp=opponent_max_hp,
        observation_sha256=prepared.initial_observation_sha256,
        legal_move_count=legal_count,
        actor_hp=actor_hp
        if spec.actor_hp is not None or spec.actor_species_ref is not None
        else None,
        actor_stats=actor_stats,
        opponent_stats=opponent_stats,
        opponent_move_ids=enemy_moves,
        opponent_pp=enemy_pp,
        actor_experience=actor_experience,
        opponent_party=(
            tuple(
                {
                    "party_slot": index + 1,
                    "species_id": species_id,
                    "level": level,
                    "hp": hp,
                    "max_hp": stats.max_hp,
                    "move_ids": list(moves),
                    "pp": list(pp),
                }
                for index, species_id, level, hp, stats, moves, pp, _ in sorted(
                    resolved_enemy_members
                )
            )
            if spec.battle_kind == "trainer"
            else None
        ),
        battle_kind=spec.battle_kind,
        player_party_count=after.party_count,
        party_reserves=(
            tuple(
                {
                    "party_slot": index + 1,
                    "species_id": species_id,
                    "level": next(
                        item.level
                        for item in spec.party_reserves or ()
                        if item.party_slot == index + 1
                    ),
                    "hp": hp,
                    "max_hp": stats.max_hp,
                    "move_ids": list(moves),
                    "pp": list(pp),
                }
                for index, species_id, hp, stats, moves, pp, _ in resolved_reserves
            )
            if spec.party_reserves is not None
            else None
        ),
    )
