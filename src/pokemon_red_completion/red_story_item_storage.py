"""Native storage of completed story keys, with exact conservation checks."""
from . import sabrina, silph
from .observation import EventFlag, MapId, event_flag_is_set


def archive_completed_story_keys(emulator, reader, actions):
    before = reader.read()
    pc_before = dict(reader.read_pc_items())
    items = sabrina._sabrina_capacity_deposit_items(dict(before.bag_items))
    if (before.map_id != MapId.SAFFRON_POKECENTER
            or (before.player_y, before.player_x) != (3, 3)
            or before.battle_state or not reader.read_input_readiness().ready
            or not all(event_flag_is_set(before.event_flags, event)
                       for event in (EventFlag.GOT_MASTER_BALL, EventFlag.BEAT_SABRINA))
            or items is None):
        raise ValueError("Storage requires the completed Saffron Center boundary")
    expected_pc = dict(pc_before)
    expected_bag = dict(before.bag_items)
    for item in items:
        expected_pc[int(item)] = expected_pc.get(int(item), 0) + expected_bag.pop(item)
    if len(expected_pc) > 50 or any(count > 99 for count in expected_pc.values()):
        raise ValueError("PC lacks capacity for completed story keys")
    sabrina._store_obsolete_key_items(actions, reader, emulator, silph.DEFAULT_SILPH_TIMING)
    after = reader.read()
    if dict(after.bag_items) != expected_bag or dict(reader.read_pc_items()) != expected_pc:
        raise RuntimeError("Storage did not conserve exact bag and PC inventory")
    for field in ("player_money", "party_species_ids", "party_levels", "party_moves",
                  "party_hp", "party_pp", "party_status", "badge_bits", "event_flags"):
        if getattr(before, field) != getattr(after, field):
            raise RuntimeError(f"Storage changed protected {field}")
    if (after.map_id != before.map_id or (after.player_y, after.player_x) != (3, 3)
            or after.battle_state or not reader.read_input_readiness().ready):
        raise RuntimeError("Storage did not return to its safe Center boundary")
    return {"status": "complete", "stored_items": [int(item) for item in items],
            "bag_stacks_before": len(before.bag_items), "bag_stacks_after": len(after.bag_items),
            "pc_before": sorted(pc_before.items()), "pc_after": sorted(expected_pc.items()),
            "cash_unchanged": True, "model_queries": 0}
