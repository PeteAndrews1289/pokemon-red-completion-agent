"""Red mechanics projection for non-damaging capture status support."""

from __future__ import annotations

from collections.abc import Sequence

from pokemon_red_completion.battle_semantics import POKEMON_TYPES
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
    live_type_names: Sequence[str] | None = None,
) -> tuple[CaptureStatusOption, ...]:
    """Project actual move effects, PP and target immunity; no species allowlist."""
    if live_type_names is not None:
        defending = tuple(live_type_names)
        if (isinstance(live_type_names, str) or not 1 <= len(defending) <= 2
                or any(name not in POKEMON_TYPES for name in defending)):
            raise ValueError("live capture types are invalid")
    elif enemy_species_id is not None:
        defending = (
            RED_BATTLE_CATALOG.resolve_species(pokemon_red_species_ref(enemy_species_id)).types
        )
    else:
        defending = ()
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
            if mechanics.type_name == "electric" and "ground" in defending:
                continue
            options.append(CaptureStatusOption(
                member.slot, slot, StatusCondition(condition), mechanics.accuracy,
            ))
    return tuple(options)
