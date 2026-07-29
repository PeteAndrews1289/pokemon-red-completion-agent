"""Pure move selection for the source-qualified Misty battle."""

from __future__ import annotations

from pokemon_red_completion.observation import (
    TACKLE_MOVE_ID,
    MapId,
    RawGameState,
)

STARYU_SPECIES_ID = 0x1B
STARMIE_SPECIES_ID = 0x98

_TRAINER_BATTLE_STATE = 2
_TACKLE_SLOT = 1
_CURRENT_PP_MASK = 0x3F
_MISTY_SPECIES = frozenset({STARYU_SPECIES_ID, STARMIE_SPECIES_ID})


class MistyPolicyEvidenceError(ValueError):
    """Raised when current evidence cannot prove the qualified Misty move."""


def choose_misty_move_slot(state: RawGameState) -> int:
    """Choose Tackle for either member of Misty's pinned Red party."""

    if state.battle_state != _TRAINER_BATTLE_STATE:
        raise MistyPolicyEvidenceError(
            "Misty policy requires an active trainer battle."
        )
    if state.map_id != MapId.CERULEAN_GYM:
        raise MistyPolicyEvidenceError(
            "Misty policy requires the Cerulean Gym map."
        )
    if state.enemy_species_id in {None, 0}:
        raise MistyPolicyEvidenceError(
            "Misty policy requires enemy species evidence."
        )
    if state.enemy_species_id not in _MISTY_SPECIES:
        raise MistyPolicyEvidenceError(
            "Misty policy rejected an unexpected enemy species."
        )

    moves = state.first_party_moves
    if moves is None or len(moves) < _TACKLE_SLOT:
        raise MistyPolicyEvidenceError(
            "Misty policy lacks move evidence for slot 1."
        )
    if moves[_TACKLE_SLOT - 1] != TACKLE_MOVE_ID:
        raise MistyPolicyEvidenceError(
            f"Misty policy expected move {TACKLE_MOVE_ID:#04x} in slot 1."
        )

    pp = state.first_party_pp
    if pp is None or len(pp) < _TACKLE_SLOT:
        raise MistyPolicyEvidenceError(
            "Misty policy lacks PP evidence for slot 1."
        )
    if pp[_TACKLE_SLOT - 1] & _CURRENT_PP_MASK == 0:
        raise MistyPolicyEvidenceError(
            "Misty policy requires usable PP in slot 1."
        )
    return _TACKLE_SLOT
