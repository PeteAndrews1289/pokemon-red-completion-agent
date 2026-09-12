"""Generation I fishing foundation re-exported from :mod:`pokemon_red_completion.fishing`."""

from pokemon_red_completion.fishing import (
    ROD_ITEM_TO_KIND,
    ROD_KIND_TO_ITEM,
    ActionExecutor,
    FishingCastError,
    FishingCastExecutor,
    FishingCastOutcome,
    FishingCastReader,
    FishingCastResult,
    FishingTiming,
    ShorelineStance,
    available_rod_kinds,
    execute_fishing_cast,
    fishable_shoreline_stances,
    item_for_rod_kind,
    rod_kind_for_item,
)

__all__ = [
    "ActionExecutor",
    "FishingCastError",
    "FishingCastExecutor",
    "FishingCastOutcome",
    "FishingCastReader",
    "FishingCastResult",
    "FishingTiming",
    "ROD_ITEM_TO_KIND",
    "ROD_KIND_TO_ITEM",
    "ShorelineStance",
    "available_rod_kinds",
    "execute_fishing_cast",
    "fishable_shoreline_stances",
    "item_for_rod_kind",
    "rod_kind_for_item",
]
