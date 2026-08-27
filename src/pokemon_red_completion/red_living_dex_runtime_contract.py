"""Lightweight immutable identities for the Red living-Dex runtime boundary."""

from __future__ import annotations

from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.provenance import canonical_sha256

RED_LIVING_DEX_TITLE_ADAPTER_SHA256 = canonical_sha256(
    {
        "claimed_root_observation": "live-red-memory-plus-pair-v1",
        "cold_selected_recipe_resolution": True,
        "exact_cartridge": POKEMON_RED_US_REV_0.sha256,
        "schema": "pokemon.red.living-dex-title-adapter-contract.v1",
    }
)
RED_LIVING_DEX_RUNTIME_FACTORY_SHA256 = canonical_sha256(
    {
        "action_reserved_before_delegate": True,
        "all_arms_closed_by_recipe_scope": True,
        "frame_delta_reconciled_in_finally": True,
        "isolated_pyboy_arm_per_purpose": True,
        "no_adjacent_save_files": True,
        "schema": "pokemon.red.living-dex-runtime-factory-contract.v1",
    }
)

__all__ = [
    "RED_LIVING_DEX_RUNTIME_FACTORY_SHA256",
    "RED_LIVING_DEX_TITLE_ADAPTER_SHA256",
]
