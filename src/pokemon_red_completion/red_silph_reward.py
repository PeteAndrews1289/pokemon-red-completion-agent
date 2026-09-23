"""Bounded earned President reward; no battle authority or fixed walking route."""
from . import silph
from .observation import EventFlag, ItemId, MapId, event_flag_is_set
from .red_npc_approach import approach_npc


def collect_silph_reward(emulator, reader, actions, *, rom):
    before = reader.read()
    if (before.battle_state or before.map_id != MapId.SILPH_CO_11F
            or not event_flag_is_set(before.event_flags, EventFlag.BEAT_SILPH_CO_GIOVANNI)
            or event_flag_is_set(before.event_flags, EventFlag.GOT_MASTER_BALL)
            or dict(before.bag_items).get(ItemId.MASTER_BALL, 0)
            or len(before.bag_items) >= 20 or not reader.read_input_readiness().ready):
        raise ValueError("President reward requires an earned unclaimed field boundary")
    approach_npc(emulator, reader, actions, rom=rom,
                 map_id=int(MapId.SILPH_CO_11F), object_index=1)
    timing = silph.DEFAULT_SILPH_TIMING
    silph._interact(actions, timing.menu_frames)
    for _ in range(16):
        raw = reader.read()
        if (dict(raw.bag_items).get(ItemId.MASTER_BALL) == 1
                and event_flag_is_set(raw.event_flags, EventFlag.GOT_MASTER_BALL)):
            break
        silph._confirm_many(actions, 1, timing.menu_frames)
    else:
        raise RuntimeError("President reward did not arrive within dialogue bound")
    for _ in range(16):
        if reader.read_input_readiness().ready and not reader.read_bottom_dialogue_box_visible():
            break
        silph._confirm_many(actions, 1, timing.menu_frames)
    else:
        raise RuntimeError("President reward dialogue did not settle")
    after = reader.read()
    expected = dict(before.bag_items)
    expected[int(ItemId.MASTER_BALL)] = 1
    if dict(after.bag_items) != expected:
        raise RuntimeError("President reward changed unexpected inventory")
    for key in ("player_money", "party_species_ids", "party_levels", "party_moves",
                "party_hp", "party_pp", "badge_bits"):
        if getattr(before, key) != getattr(after, key):
            raise RuntimeError("President reward changed protected party/resources")
    return {"status": "complete", "master_balls_received": 1, "battle_decisions": 0}
