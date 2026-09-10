"""Red capture prerequisites, distinct from encounter-table species knowledge.

Pinned rule: pret/pokered 1e96034092686d006e863cace09e87273051a3d8,
engine/battle/core.asm IsGhostBattle and engine/items/item_effects.asm ItemUseBall.
This covers unidentified Tower ghosts, not every special/event encounter.
"""

from .observation import ItemId, MapId, RawGameState


def required_wild_source_items(source_id: str) -> tuple[ItemId, ...]:
    """Destination requirements apply even when the player is elsewhere."""
    if source_id in {f"wild:PokemonTower{floor}F:grass" for floor in range(1, 8)}:
        return (ItemId.SILPH_SCOPE,)
    return ()


def is_unidentified_ghost_encounter(raw: RawGameState) -> bool:
    """Only actual wild Tower encounters without a carried Scope are ghosts."""
    return (
        raw.battle_state == 1
        and raw.map_id is not None
        and int(MapId.POKEMON_TOWER_1F) <= raw.map_id <= int(MapId.POKEMON_TOWER_7F)
        and dict(raw.bag_items or ()).get(int(ItemId.SILPH_SCOPE), 0) <= 0
    )
