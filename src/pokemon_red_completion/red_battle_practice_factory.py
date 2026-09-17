"""Teacher-only Red adapter for a narrow, cartridge-verified battle factory.

Write authority is deliberately absent from model/executor interfaces. Only an
isolated emulator copy may call this adapter; it never edits a save on disk.
The first supported axes are actor move IDs/PP and current opponent HP.
Species, levels, stats, status and opponent moves are explicitly unsupported.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .battle_practice_factory import BattlePracticeError, BattlePracticeSpec
from .observation import (
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

    def public_dict(self) -> dict[str, object]:
        return {
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
        or spec.opponent_hp > before.enemy_max_hp
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
        or after.active_party_level != before.active_party_level
        or after.active_party_hp != before.active_party_hp
        or after.active_party_max_hp != before.active_party_max_hp
        or after.enemy_species_id != before.enemy_species_id
        or after.enemy_level != before.enemy_level
        or after.enemy_max_hp != before.enemy_max_hp
        or after.enemy_hp != spec.opponent_hp
        or after.battler_moves != padded_moves
        or after.battler_pp != padded_pp
        or after.active_party_moves != padded_moves
        or after.active_party_pp != padded_pp
        or tuple(memory[_BATTLE_MOVES + index] for index in range(4)) != padded_moves
        or tuple(memory[_BATTLE_PP + index] for index in range(4)) != padded_pp
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
    )
