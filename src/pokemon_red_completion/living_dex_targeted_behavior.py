"""Prospective full-support behavior for a targeted living-Pokedex update.

The frozen schedule names a semantic option kind that the collection slot is
intended to exercise.  This module turns that declaration into an explicit,
replayable distribution: every executable row retains non-zero probability,
while rows of the scheduled kind receive most of the probability mass.  The
policy sees no outcome and no title-specific identity.
"""

from __future__ import annotations

from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionAvailability,
    LivingDexOptionKind,
    LivingDexOptionMenu,
)
from pokemon_red_completion.provenance import canonical_sha256

LIVING_DEX_TARGETED_BEHAVIOR_SCHEMA = (
    "pokemon.core.living-dex-targeted-full-support-behavior.v1"
)
LIVING_DEX_TARGETED_FOCUS_WEIGHT = 98
LIVING_DEX_TARGETED_ALTERNATIVE_WEIGHT = 1
LIVING_DEX_TARGETED_BEHAVIOR_SHA256 = canonical_sha256(
    {
        "alternative_weight": LIVING_DEX_TARGETED_ALTERNATIVE_WEIGHT,
        "focus_weight": LIVING_DEX_TARGETED_FOCUS_WEIGHT,
        "outcome_access": False,
        "schema": LIVING_DEX_TARGETED_BEHAVIOR_SCHEMA,
        "title_specific_identity_access": False,
        "unavailable_weight": 0,
    }
)


class LivingDexTargetedBehaviorError(ValueError):
    """A scheduled focus cannot form the declared full-support distribution."""


def living_dex_targeted_behavior_integer_weights(
    menu: LivingDexOptionMenu,
    focus_kind: LivingDexOptionKind,
) -> tuple[int, ...]:
    """Return outcome-blind weights with full support over executable rows."""

    if not isinstance(menu, LivingDexOptionMenu):
        raise TypeError("targeted behavior needs a living-Dex option menu")
    menu.__post_init__()
    if not isinstance(focus_kind, LivingDexOptionKind):
        raise TypeError("targeted behavior needs a semantic focus kind")
    if not any(
        candidate.availability is LivingDexOptionAvailability.AVAILABLE
        and candidate.features.kind is focus_kind
        for candidate in menu.candidates
    ):
        raise LivingDexTargetedBehaviorError(
            "targeted behavior focus kind is not executable"
        )
    return tuple(
        0
        if candidate.availability is not LivingDexOptionAvailability.AVAILABLE
        else (
            LIVING_DEX_TARGETED_FOCUS_WEIGHT
            if candidate.features.kind is focus_kind
            else LIVING_DEX_TARGETED_ALTERNATIVE_WEIGHT
        )
        for candidate in menu.candidates
    )


__all__ = [
    "LIVING_DEX_TARGETED_ALTERNATIVE_WEIGHT",
    "LIVING_DEX_TARGETED_BEHAVIOR_SCHEMA",
    "LIVING_DEX_TARGETED_BEHAVIOR_SHA256",
    "LIVING_DEX_TARGETED_FOCUS_WEIGHT",
    "LivingDexTargetedBehaviorError",
    "living_dex_targeted_behavior_integer_weights",
]
