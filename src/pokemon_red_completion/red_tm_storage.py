"""Reversible storage of explicitly selected TMs; no sale or discard."""

from . import sabrina, silph
from .observation import ItemId


def tm_storage_inventory(bag, pc, items):
    if not isinstance(items, tuple) or not items or len(set(items)) != len(items):
        raise ValueError("storage needs distinct selected TMs")
    expected_bag, expected_pc = dict(bag), dict(pc)
    for item in items:
        if type(item) is not int or not 201 <= item <= 250 or expected_bag.get(item) != 1:
            raise ValueError("only single owned TM stacks may be archived")
        expected_pc[item] = expected_pc.get(item, 0) + expected_bag.pop(item)
    if len(expected_pc) > 50 or any(count > 99 for count in expected_pc.values()):
        raise ValueError("PC lacks capacity")
    return expected_bag, expected_pc


def store_selected_tms(controller, reader, actions, items):
    """Caller routes to a qualified PC-facing stance before this menu operation."""
    before = reader.read()
    if before.battle_state or not reader.read_input_readiness().ready:
        raise ValueError("TM storage requires ready field control")
    expected_bag, expected_pc = tm_storage_inventory(
        before.bag_items, reader.read_pc_items(), items
    )
    for item in items:
        sabrina._deposit_pc_item(
            actions, reader, controller, ItemId(item), silph.DEFAULT_SILPH_TIMING
        )
    after = reader.read()
    if dict(after.bag_items) != expected_bag or dict(reader.read_pc_items()) != expected_pc:
        raise RuntimeError("TM storage did not conserve bag and PC inventory")
    for field in (
        "map_id",
        "player_x",
        "player_y",
        "player_money",
        "party_species_ids",
        "party_levels",
        "party_moves",
        "party_hp",
        "party_pp",
        "party_status",
        "badge_bits",
        "event_flags",
    ):
        if getattr(before, field) != getattr(after, field):
            raise RuntimeError("TM storage changed protected " + field)
    if not reader.read_input_readiness().ready:
        raise RuntimeError("TM storage did not close its menus")
    return {
        "stored_tms": list(items),
        "bag_stacks_before": len(before.bag_items),
        "bag_stacks_after": len(after.bag_items),
        "sales": 0,
    }
