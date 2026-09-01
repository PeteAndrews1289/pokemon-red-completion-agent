"""Pokémon Red adapter for the title-neutral battle-source identity contract."""

from __future__ import annotations

from pokemon_red_completion.battle_source_conditioning import (
    BattlePartyIdentity,
    BattlePartyMemberIdentity,
    BattleSourceConditioningError,
)
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.red_battle_catalog import (
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)


def red_battle_party_identity(raw: RawGameState) -> BattlePartyIdentity:
    """Project Red RAM into the portable identity a healer must preserve."""

    if not isinstance(raw, RawGameState):
        raise TypeError("Red battle source identity requires a raw game state")
    count = raw.party_count
    species = raw.party_species_ids
    levels = raw.party_levels
    moves = raw.party_moves
    if (
        type(count) is not int  # noqa: E721
        or not 1 <= count <= 6
        or not isinstance(species, tuple)
        or not isinstance(levels, tuple)
        or not isinstance(moves, tuple)
        or len(species) != count
        or len(levels) != count
        or len(moves) != count
    ):
        raise BattleSourceConditioningError("Red party identity arrays are unavailable")
    return BattlePartyIdentity(
        tuple(
            BattlePartyMemberIdentity(
                species_ref=pokemon_red_species_ref(species_id),
                level=level,
                move_refs=tuple(
                    pokemon_red_move_ref(move_id) for move_id in known_moves if move_id > 0
                ),
            )
            for species_id, level, known_moves in zip(species, levels, moves, strict=True)
        )
    )


__all__ = ["red_battle_party_identity"]
