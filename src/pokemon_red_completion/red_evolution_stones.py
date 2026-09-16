"""Canonical Red evolution-stone resource bindings.

The cartridge evolution graph proves which item performs a transformation.
This module only records the stable Celadon Mart resource contract needed to
make a buyable stone available after an evolve decision has been selected.
"""

from __future__ import annotations

from dataclasses import dataclass

from .observation import ItemId

EVOLUTION_STONE_PRICE = 2_100


@dataclass(frozen=True, slots=True)
class RedEvolutionStoneOffer:
    item_id: ItemId
    acquisition_source_id: str
    catalog_item_ref: str
    mart_absolute_index: int
    price: int = EVOLUTION_STONE_PRICE


BUYABLE_EVOLUTION_STONES = {
    int(offer.item_id): offer
    for offer in (
        RedEvolutionStoneOffer(
            ItemId.FIRE_STONE,
            "evolution:item:FireStone",
            "pokemon:red:item:fire_stone",
            1,
        ),
        RedEvolutionStoneOffer(
            ItemId.THUNDER_STONE,
            "evolution:item:ThunderStone",
            "pokemon:red:item:thunder_stone",
            2,
        ),
        RedEvolutionStoneOffer(
            ItemId.WATER_STONE,
            "evolution:item:WaterStone",
            "pokemon:red:item:water_stone",
            3,
        ),
        RedEvolutionStoneOffer(
            ItemId.LEAF_STONE,
            "evolution:item:LeafStone",
            "pokemon:red:item:leaf_stone",
            4,
        ),
    )
}


def buyable_evolution_stone(item_id: int) -> RedEvolutionStoneOffer:
    """Return the exact Celadon offer or fail closed for finite/non-Mart stones."""

    try:
        return BUYABLE_EVOLUTION_STONES[item_id]
    except KeyError:
        raise ValueError("item is not a buyable Red evolution stone") from None


__all__ = (
    "BUYABLE_EVOLUTION_STONES",
    "EVOLUTION_STONE_PRICE",
    "RedEvolutionStoneOffer",
    "buyable_evolution_stone",
)
