"""Teacher-only Red adapter for a narrow, cartridge-verified battle factory.

Write authority is deliberately absent from model/executor interfaces. Only an
isolated emulator copy may call this adapter; it never edits a save on disk.
Supported axes are actor moves/PP, both levels, both five-stat blocks and
current HP. Species, status and opponent moves remain unsupported.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .battle_practice_factory import BattlePracticeError, BattlePracticeSpec, PracticeStats
from .observation import (
    PARTY_HP_OFFSET,
    PARTY_LEVEL_OFFSET,
    PARTY_MAX_HP_OFFSET,
    PARTY_MOVES_OFFSET,
    PARTY_PP_OFFSET,
    PARTY_STRUCT_STRIDE,
    BattleMenuPhase,
    PokemonRedStateReader,
    RamAddress,
)
from .red_battle_catalog import PokemonRedBattleCatalog
from .red_battle_scenario import prepare_red_battle_scenario
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
        return result


def materialize_red_train_practice(
    reader: PokemonRedStateReader,
    memory: WritableRedMemory,
    spec: BattlePracticeSpec,
) -> RedPracticeReceipt:
    """Edit a private wild-battle copy and verify its semantic readback.

    The caller authenticates loaded source bytes against ``spec`` and owns the
    emulator lifetime. Failed materializations must be discarded, never saved.
    """

    if not isinstance(spec, BattlePracticeSpec):
        raise BattlePracticeError("practice specification differs")
    before = reader.read()
    if (
        before.battle_state != 1
        or before.map_id is None
        or before.active_party_index is None
        or before.active_party_species_id is None
        or before.active_party_level is None
        or before.enemy_species_id is None
        or before.enemy_level is None
        or before.enemy_hp is None
        or before.enemy_hp <= 0
        or before.enemy_max_hp is None
        or spec.opponent_hp
        > (spec.opponent_stats.max_hp if spec.opponent_stats else before.enemy_max_hp)
        or before.battler_moves != before.active_party_moves
        or before.battler_pp != before.active_party_pp
        or reader.read_battle_menu_state(before).phase is not BattleMenuPhase.MAIN
    ):
        raise BattlePracticeError("source is not a supported live wild MAIN boundary")
    identity = reader.read_wild_capture_identity()
    if (
        identity is None
        or identity.transformed
        or identity.original_species_id != identity.displayed_species_id
    ):
        raise BattlePracticeError("transformed or ambiguous opponent is unsupported")
    catalog = PokemonRedBattleCatalog()
    move_ids: list[int] = []
    pp_values: list[int] = []
    for move in spec.actor_moves:
        try:
            mechanics = catalog.resolve_move(move.move_ref)
            move_id = int(move.move_ref.rsplit(":", 1)[1])
        except (ValueError, IndexError) as error:
            raise BattlePracticeError("Red practice move reference differs") from error
        if move.pp > mechanics.max_pp or move_id not in catalog.move_ids:
            raise BattlePracticeError("Red practice PP exceeds unboosted move capacity")
        move_ids.append(move_id)
        pp_values.append(move.pp)
    padded_moves = tuple((move_ids + [0] * 4)[:4])
    padded_pp = tuple((pp_values + [0] * 4)[:4])
    active_base = int(RamAddress.PARTY_MON_1) + before.active_party_index * PARTY_STRUCT_STRIDE
    actor_hp = spec.actor_hp if spec.actor_hp is not None else before.active_party_hp
    actor_max_hp = spec.actor_stats.max_hp if spec.actor_stats else before.active_party_max_hp
    if actor_hp is None or actor_max_hp is None or actor_hp > actor_max_hp:
        raise BattlePracticeError("practice actor HP exceeds maximum")

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
    actor_level = spec.actor_level or before.active_party_level
    opponent_level = spec.opponent_level or before.enemy_level
    assert actor_level is not None and opponent_level is not None
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
        for address in (_ENEMY_BOX_LEVEL, int(RamAddress.ENEMY_LEVEL), _ENEMY_UNMODIFIED_LEVEL):
            memory[address] = opponent_level
    if spec.actor_stats is not None:
        _put_stats(memory, active_base + PARTY_MAX_HP_OFFSET, spec.actor_stats)
        _put_stats(memory, _BATTLE_MAX_HP, spec.actor_stats)
        _put_stats(memory, _PLAYER_UNMODIFIED_LEVEL + 1, spec.actor_stats)
    if spec.opponent_stats is not None:
        _put_stats(memory, int(RamAddress.ENEMY_MAX_HP), spec.opponent_stats)
        _put_stats(memory, _ENEMY_UNMODIFIED_LEVEL + 1, spec.opponent_stats)
    if spec.actor_hp is not None:
        _put_u16(memory, active_base + PARTY_HP_OFFSET, actor_hp)
        _put_u16(memory, _BATTLE_HP, actor_hp)
    for index, (move_id, pp) in enumerate(zip(padded_moves, padded_pp, strict=True)):
        memory[_BATTLE_MOVES + index] = move_id
        memory[_BATTLE_PP + index] = pp
        memory[active_base + PARTY_MOVES_OFFSET + index] = move_id
        memory[active_base + PARTY_PP_OFFSET + index] = pp
    memory[int(RamAddress.ENEMY_HP)] = spec.opponent_hp >> 8
    memory[int(RamAddress.ENEMY_HP) + 1] = spec.opponent_hp & 0xFF

    after = reader.read()
    if (
        after.map_id != before.map_id
        or after.battle_state != before.battle_state
        or after.active_party_index != before.active_party_index
        or after.active_party_species_id != before.active_party_species_id
        or after.active_party_level != actor_level
        or after.active_party_hp != actor_hp
        or after.active_party_max_hp != actor_max_hp
        or after.enemy_species_id != before.enemy_species_id
        or after.enemy_level != opponent_level
        or after.enemy_max_hp
        != (spec.opponent_stats.max_hp if spec.opponent_stats else before.enemy_max_hp)
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
                    _ENEMY_BOX_LEVEL,
                    _ENEMY_UNMODIFIED_LEVEL,
                )
            )
        )
        or (
            spec.actor_stats is not None
            and any(
                _stats(memory, base) != spec.actor_stats
                for base in (
                    active_base + PARTY_MAX_HP_OFFSET,
                    _BATTLE_MAX_HP,
                    _PLAYER_UNMODIFIED_LEVEL + 1,
                )
            )
        )
        or (
            spec.opponent_stats is not None
            and any(
                _stats(memory, base) != spec.opponent_stats
                for base in (
                    int(RamAddress.ENEMY_MAX_HP),
                    _ENEMY_UNMODIFIED_LEVEL + 1,
                )
            )
        )
        or (spec.actor_hp is not None and _u16(memory, _BATTLE_HP) != actor_hp)
    ):
        raise BattlePracticeError("assisted battle did not read back consistently")
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
        opponent_max_hp=after.enemy_max_hp,
        observation_sha256=prepared.initial_observation_sha256,
        legal_move_count=legal_count,
        actor_hp=actor_hp if spec.actor_hp is not None else None,
        actor_stats=spec.actor_stats,
        opponent_stats=spec.opponent_stats,
    )
