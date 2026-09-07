"""Red mechanics projection for non-damaging capture status support."""

from __future__ import annotations

from pokemon_red_completion.capture_support import CaptureStatusOption
from pokemon_red_completion.party import PartyObservation, StatusCondition
from pokemon_red_completion.red_battle_catalog import (
    RED_BATTLE_CATALOG,
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)


def red_capture_status_options(
    party: PartyObservation,
    *,
    enemy_species_id: int | None = None,
) -> tuple[CaptureStatusOption, ...]:
    """Project actual move effects, PP and target immunity; no species allowlist."""
    defending_types = (
        RED_BATTLE_CATALOG.resolve_species(pokemon_red_species_ref(enemy_species_id)).types
        if enemy_species_id is not None else ()
    )
    options = []
    for member in party.members:
        for slot, move in enumerate(member.moves, 1):
            if not move.is_usable:
                continue
            reference = pokemon_red_move_ref(move.move_id)
            condition = RED_BATTLE_CATALOG.capture_status_effect(reference)
            if condition is None:
                continue
            mechanics = RED_BATTLE_CATALOG.resolve_move(reference)
            # Gen1 Thunder Wave fails against Ground. Normal sleep moves are
            # not damaging Normal attacks and may affect Ghost types.
            if mechanics.type_name == "electric" and "ground" in defending_types:
                continue
            options.append(CaptureStatusOption(
                member.slot, slot, StatusCondition(condition), mechanics.accuracy,
            ))
    return tuple(options)
