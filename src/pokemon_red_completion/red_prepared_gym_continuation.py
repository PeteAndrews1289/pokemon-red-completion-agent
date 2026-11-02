"""Resume a prepared, unfinished gym goal from earned state, without purchases."""

from dataclasses import replace

from . import erika
from .actions import MacroAction, MacroActionKind
from .executor import CountingExecutor
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import Gen1TrainerSightProjector
from .gen1_traversal import cut_capabilities
from .observation import Badge, EventFlag, ItemId, MapId, event_flag_is_set
from .red_training_ground_route import RedVermilionGroundTransition


def prepared_erika_available(raw) -> bool:
    return bool(
        raw.battle_state == 0
        and raw.map_id in {MapId.CELADON_CITY, MapId.CELADON_POKECENTER, MapId.CELADON_GYM}
        and erika.early_erika_party_supported(raw.party_species_ids)
        and raw.party_count == len(raw.party_species_ids)
        and raw.first_party_moves
        and len(raw.first_party_moves) == 4
        and raw.first_party_moves[2] == erika.ICE_BEAM_MOVE
        and raw.first_party_pp
        and len(raw.first_party_pp) == 4
        and raw.first_party_pp[2] & 0x3F
        and raw.party_hp
        and raw.party_hp == raw.party_max_hp
        and len(raw.party_hp) == raw.party_count
        and min(raw.party_hp) > 0
        and raw.party_status is not None
        and len(raw.party_status) == raw.party_count
        and not any(raw.party_status)
        and raw.event_flags is not None
        and event_flag_is_set(raw.event_flags, EventFlag.GOT_TM13)
        and raw.badge_bits is not None
        and not raw.badge_bits & int(Badge.RAINBOW)
        and not event_flag_is_set(raw.event_flags, EventFlag.BEAT_ERIKA)
        and raw.bag_items is not None
        and not dict(raw.bag_items).get(ItemId.TM21_MEGA_DRAIN)
    )


def run_prepared_erika_continuation(
    emulator,
    reader,
    executor,
    *,
    rom,
    resume_battle=False,
    remaining_potions=None,
    remaining_status_items=None,
):
    """Use observed routing and existing battle support; no preparation replay.

    The caller must retain/authenticate the outstanding goal choice. This routine
    does not select a goal. Unfinished trainers remain hazards to the router.
    """
    before = reader.read()
    if type(resume_battle) is not bool:
        raise TypeError("active-battle continuation must be explicit")
    if resume_battle and (remaining_potions is None or remaining_status_items is None):
        raise ValueError("active continuation requires retained resource allowances")
    remaining_potions = 6 if remaining_potions is None else remaining_potions
    remaining_status_items = 3 if remaining_status_items is None else remaining_status_items
    if (
        type(remaining_potions) is not int
        or not 0 <= remaining_potions <= 6
        or type(remaining_status_items) is not int
        or not 0 <= remaining_status_items <= 3
    ):
        raise ValueError("invalid retained battle resource allowance")
    if resume_battle:
        if reader.read_active_trainer_identity() != (erika.ERIKA_OPPONENT, erika.ERIKA_CLASS, 1):
            raise ValueError("retained active battle is not Erika")
        if (
            before.battle_state != 2
            or before.map_id != MapId.CELADON_GYM
            or not any(before.party_hp or ())
        ):
            raise ValueError("active Erika continuation lacks a living party")
    elif not prepared_erika_available(before) or not reader.read_input_readiness().ready:
        raise ValueError("prepared Erika continuation lacks its observed input contract")
    actions = CountingExecutor(executor)
    start_frames = emulator.frame_count
    route = replace(
        RedVermilionGroundTransition.from_rom(rom), full_event_offsets=True, observe_terrain=True
    )
    # The existing Cut planner composes one Cut per plan. Enter the destination
    # map first, then solve its interior, using cartridge-derived warp endpoints.
    traversal = Gen1TraversalObserver(
        reader,
        hazard_projector=Gen1TrainerSightProjector(rom, reader, full_event_offsets=True),
        capability_projector=cut_capabilities,
    )
    if not resume_battle and before.map_id != MapId.CELADON_GYM:
        entry = route.route_world.plan_to_map(traversal.observe(), int(MapId.CELADON_GYM))
        replace(route, destination_map=entry.terminal_map, destination_at=entry.terminal_at)(
            actions, reader, emulator
        )
    if not resume_battle:
        replace(route, destination_map=int(MapId.CELADON_GYM), destination_at=(4, 4))(
            actions, reader, emulator
        )
        # Routing proves position, not interaction facing. The NPC occupies (3,4).
        actions.execute(MacroAction(MacroActionKind.MOVE, "up"))
        erika._wait(actions, erika.DEFAULT_ERIKA_TIMING.movement_frames)
        erika._require(reader.read(), MapId.CELADON_GYM, (4, 4), "leader interaction stance")
        actions.execute(MacroAction(MacroActionKind.INTERACT))
        erika._wait(actions, erika.DEFAULT_ERIKA_TIMING.movement_frames)
        erika._enter_battle(actions, reader, erika.DEFAULT_ERIKA_TIMING, "Erika retained goal")
    if not resume_battle:
        erika._require_identity(
            emulator,
            (erika.ERIKA_OPPONENT, erika.ERIKA_CLASS, erika.ERIKA_OPPONENT, 1),
            "Erika retained goal",
        )
    # Attack before the opponent can impose sleep; do not give up the first
    # turn automatically for a boost. Retain owned boosters for later goals.
    boost_used = 0
    erika._battle(
        reader,
        actions,
        emulator,
        MapId.CELADON_GYM,
        erika.DEFAULT_ERIKA_TIMING,
        "Erika",
        erika.ERIKA_LEADER_BATTLE_PLAN,
        move_selector=erika._early_erika_move_slot,
        maximum_super_potions=min(
            remaining_potions, dict(before.bag_items).get(ItemId.SUPER_POTION, 0)
        ),
        maximum_status_items=remaining_status_items,
        status_item_reserve=0,
    )
    for _ in range(erika.DEFAULT_ERIKA_TIMING.dialogue_pulses):
        raw = reader.read()
        if (
            raw.battle_state == 0
            and event_flag_is_set(raw.event_flags, EventFlag.BEAT_ERIKA)
            and event_flag_is_set(raw.event_flags, EventFlag.GOT_TM21)
            and raw.badge_bits & int(Badge.RAINBOW)
            and reader.read_input_readiness().ready
        ):
            break
        erika._pulse(
            actions, MacroActionKind.CONFIRM, frames=erika.DEFAULT_ERIKA_TIMING.movement_frames
        )
    else:
        raise RuntimeError("resumed Erika rewards did not settle")
    exit_plan = route.route_world.plan_to_map(traversal.observe(), int(MapId.CELADON_CITY))
    replace(route, destination_map=exit_plan.terminal_map, destination_at=exit_plan.terminal_at)(
        actions, reader, emulator
    )
    replace(route, destination_map=int(MapId.CELADON_POKECENTER), destination_at=(7, 3))(
        actions, reader, emulator
    )
    erika._heal(actions, reader, emulator, erika.DEFAULT_ERIKA_TIMING)
    after = reader.read()
    expected_bag = dict(before.bag_items)
    status_used = 0
    for item, limit in (
        (ItemId.X_SPECIAL, boost_used),
        (ItemId.AWAKENING, remaining_status_items),
        (ItemId.PARLYZ_HEAL, remaining_status_items),
    ):
        used = expected_bag.get(item, 0) - dict(after.bag_items).get(item, 0)
        if not 0 <= used <= limit:
            raise RuntimeError("resumed Erika exceeded its declared item allowance")
        if used:
            if item in (ItemId.AWAKENING, ItemId.PARLYZ_HEAL):
                status_used += used
            expected_bag[item] -= used
            if not expected_bag[item]:
                del expected_bag[item]
    potions_used = expected_bag.get(ItemId.SUPER_POTION, 0) - dict(after.bag_items).get(
        ItemId.SUPER_POTION, 0
    )
    if not 0 <= potions_used <= remaining_potions or status_used > remaining_status_items:
        raise RuntimeError("resumed Erika exceeded its healing budget")
    if potions_used:
        expected_bag[ItemId.SUPER_POTION] -= potions_used
        if not expected_bag[ItemId.SUPER_POTION]:
            del expected_bag[ItemId.SUPER_POTION]
    expected_bag[int(ItemId.TM21_MEGA_DRAIN)] = 1
    if (
        after.party_species_ids != before.party_species_ids
        or after.party_hp != after.party_max_hp
        or any(after.party_status)
        or dict(after.bag_items) != expected_bag
        or after.player_money <= before.player_money
        or after.first_party_moves != before.first_party_moves
        or after.battle_state
        or after.map_id != MapId.CELADON_POKECENTER
        or (after.player_x, after.player_y) != (3, 3)
        or emulator.pressed_buttons
        or not reader.read_input_readiness().ready
    ):
        raise RuntimeError("resumed Erika terminal failed preservation checks")
    return {
        "status": "complete",
        "objective": "defeat_erika",
        "scripted_support": ["cartridge-derived navigation", "existing battle policy", "healing"],
        "preparation_repeated": False,
        "purchases": 0,
        "super_potions_used": potions_used,
        "actions": actions.actions_executed,
        "frames": emulator.frame_count - start_frames,
        "cash_before": before.player_money,
        "cash_after": after.player_money,
    }
