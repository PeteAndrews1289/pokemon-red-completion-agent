"""Settle an already-lost native battle; never cause a loss or reset a save."""

from .actions import MacroAction, MacroActionKind


def settle_red_blackout(actions, reader, emulator, *, maximum_pulses=128):
    if type(maximum_pulses) is not int or maximum_pulses <= 0:
        raise ValueError("blackout settlement requires a positive pulse bound")
    before = reader.read()
    if (
        before.battle_state not in {1, 2}
        or not before.party_hp
        or any(before.party_hp)
        or before.player_money is None
    ):
        raise ValueError("blackout recovery requires an observed all-party loss")
    destination = reader.read_last_blackout_map()
    expected_money = before.player_money // 2
    for _ in range(maximum_pulses):
        current = reader.read()
        if (
            current.battle_state == 0
            and current.map_id == destination
            and current.party_hp == current.party_max_hp
            and current.party_hp
            and min(current.party_hp) > 0
            and current.party_status is not None
            and len(current.party_status) == len(current.party_hp)
            and not any(current.party_status)
            and reader.read_input_readiness().ready
            and not emulator.pressed_buttons
        ):
            if (
                current.player_money != expected_money
                or current.party_species_ids != before.party_species_ids
                or current.bag_items != before.bag_items
                or any(
                    getattr(current, key) != getattr(before, key)
                    for key in (
                        "party_count",
                        "party_moves",
                        "party_levels",
                        "badge_bits",
                        "event_flags",
                    )
                )
            ):
                raise ValueError("blackout recovery changed unexpected resources")
            return {
                "blackout_verified": True,
                "cash_before": before.player_money,
                "cash_after": current.player_money,
                "cash_lost": before.player_money - current.player_money,
                "destination_map": destination,
                "scripted_support": "native blackout dialogue",
            }
        actions.execute(MacroAction(MacroActionKind.CONFIRM))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=120))
    raise RuntimeError("native blackout did not reach its healing anchor within the bound")
