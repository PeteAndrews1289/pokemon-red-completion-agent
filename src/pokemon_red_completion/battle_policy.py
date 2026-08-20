"""Pure semantic move selection for source-qualified battles."""

from __future__ import annotations

from pokemon_red_completion.observation import (
    ABRA_SPECIES_ID,
    BULBASAUR_SPECIES_ID,
    MEGA_PUNCH_MOVE_ID,
    PIDGEOTTO_SPECIES_ID,
    RATTATA_SPECIES_ID,
    TACKLE_MOVE_ID,
    TAIL_WHIP_MOVE_ID,
    WATER_GUN_MOVE_ID,
    RawGameState,
)

_TRAINER_BATTLE_STATE = 2
_TACKLE_SLOT = 1
_TAIL_WHIP_SLOT = 2
_MEGA_PUNCH_SLOT = 3
_WATER_GUN_SLOT = 4
_CURRENT_PP_MASK = 0x3F
_MIN_STAT_STAGE = 1
_MAX_STAT_STAGE = 13
_NEUTRAL_STAT_STAGE = 7
_WATER_GUN_TARGETS = frozenset(
    {
        PIDGEOTTO_SPECIES_ID,
        ABRA_SPECIES_ID,
        RATTATA_SPECIES_ID,
    }
)


class BattlePolicyEvidenceError(ValueError):
    """Raised when a move cannot be selected from complete semantic evidence."""


def choose_cerulean_rival_move_slot(state: RawGameState) -> int:
    """Choose the qualified move slot for the active Cerulean rival Pokémon."""

    if state.battle_state != _TRAINER_BATTLE_STATE:
        raise BattlePolicyEvidenceError("Cerulean rival policy requires an active trainer battle.")
    if state.enemy_species_id in {None, 0}:
        raise BattlePolicyEvidenceError("Cerulean rival policy requires enemy species evidence.")

    if state.enemy_species_id == BULBASAUR_SPECIES_ID:
        _require_stat_stage(
            state.player_attack_stage,
            label="player Attack",
        )
        enemy_defense = _require_stat_stage(
            state.enemy_defense_stage,
            label="enemy Defense",
        )
        if enemy_defense == _NEUTRAL_STAT_STAGE:
            return _require_usable_move(
                state,
                slot=_TAIL_WHIP_SLOT,
                move_id=TAIL_WHIP_MOVE_ID,
            )
        if (
            _require_move_current_pp(
                state,
                slot=_MEGA_PUNCH_SLOT,
                move_id=MEGA_PUNCH_MOVE_ID,
            )
            > 0
        ):
            return _MEGA_PUNCH_SLOT
        return _require_usable_move(state, slot=_TACKLE_SLOT, move_id=TACKLE_MOVE_ID)
    if state.enemy_species_id in _WATER_GUN_TARGETS:
        if (
            _require_move_current_pp(
                state,
                slot=_WATER_GUN_SLOT,
                move_id=WATER_GUN_MOVE_ID,
            )
            > 0
        ):
            return _WATER_GUN_SLOT
        return _require_usable_move(
            state,
            slot=_TACKLE_SLOT,
            move_id=TACKLE_MOVE_ID,
        )
    raise BattlePolicyEvidenceError(
        "Cerulean rival policy rejected an unexpected enemy species."
    )


def _require_stat_stage(value: int | None, *, label: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not _MIN_STAT_STAGE <= value <= _MAX_STAT_STAGE
    ):
        raise BattlePolicyEvidenceError(
            f"Cerulean rival policy requires valid {label} stage evidence."
        )
    return value


def _require_usable_move(state: RawGameState, *, slot: int, move_id: int) -> int:
    if _require_move_current_pp(state, slot=slot, move_id=move_id) == 0:
        raise BattlePolicyEvidenceError(f"Cerulean rival policy requires usable PP in slot {slot}.")
    return slot


def _require_move_current_pp(
    state: RawGameState,
    *,
    slot: int,
    move_id: int,
) -> int:
    moves = state.first_party_moves
    pp = state.first_party_pp
    index = slot - 1
    if moves is None or len(moves) <= index:
        raise BattlePolicyEvidenceError(
            f"Cerulean rival policy lacks move evidence for slot {slot}."
        )
    if pp is None or len(pp) <= index:
        raise BattlePolicyEvidenceError(f"Cerulean rival policy lacks PP evidence for slot {slot}.")
    if moves[index] != move_id:
        raise BattlePolicyEvidenceError(
            f"Cerulean rival policy expected move {move_id:#04x} in slot {slot}."
        )
    return pp[index] & _CURRENT_PP_MASK
