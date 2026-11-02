"""Native storage of completed story keys, with exact conservation checks."""

from dataclasses import replace
from hashlib import sha256

from . import sabrina, silph
from .gen1_field_moves import surf_permission
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import Gen1TrainerSightProjector
from .gen1_traversal import cut_capabilities, surf_capabilities
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import EventFlag, ItemId, MapId, event_flag_is_set
from .red_goal_skills import _POKEMON_CENTER_MAPS
from .red_player_cash_exposure import certified_cash_safe_transition
from .red_player_field_goals import _field_ready
from .route_plan import RoutePlanningError


def archive_completed_story_keys(emulator, reader, actions):
    before = reader.read()
    pc_before = dict(reader.read_pc_items())
    items = sabrina._sabrina_capacity_deposit_items(dict(before.bag_items))
    if (
        before.map_id != MapId.SAFFRON_POKECENTER
        or (before.player_y, before.player_x) != (3, 3)
        or before.battle_state
        or not reader.read_input_readiness().ready
        or not all(
            event_flag_is_set(before.event_flags, event)
            for event in (EventFlag.GOT_MASTER_BALL, EventFlag.BEAT_SABRINA)
        )
        or items is None
    ):
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
    for field in (
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
            raise RuntimeError(f"Storage changed protected {field}")
    if (
        after.map_id != before.map_id
        or (after.player_y, after.player_x) != (3, 3)
        or after.battle_state
        or not reader.read_input_readiness().ready
    ):
        raise RuntimeError("Storage did not return to its safe Center boundary")
    return {
        "status": "complete",
        "stored_items": [int(item) for item in items],
        "bag_stacks_before": len(before.bag_items),
        "bag_stacks_after": len(after.bag_items),
        "pc_before": sorted(pc_before.items()),
        "pc_after": sorted(expected_pc.items()),
        "cash_unchanged": True,
        "model_queries": 0,
    }


def completed_key_capacity_items(raw, *, reserved_slots=2, allow_spare_tm_storage=False):
    """Keep reusable HMs/Flute/Scope; archive only native-completed keys.

    This is a disclosed inventory mechanic, not learned item selection. Storage
    conserves the assets rather than selling, discarding or overwriting them.
    """
    if type(reserved_slots) is not int or not 1 <= reserved_slots <= 20:
        raise ValueError("reserved bag slots must be an integer from one to twenty")
    if type(allow_spare_tm_storage) is not bool:
        raise TypeError("spare TM storage permission must be an explicit boolean")
    if raw.bag_items is None or raw.event_flags is None:
        return ()
    needed = max(0, len(raw.bag_items) + reserved_slots - 20)
    bag = dict(raw.bag_items)
    eligible = (
        (ItemId.CARD_KEY, EventFlag.GOT_MASTER_BALL),
        (ItemId.LIFT_KEY, EventFlag.BEAT_ROCKET_HIDEOUT_GIOVANNI),
        (ItemId.SS_TICKET, EventFlag.GOT_HM01),
        (ItemId.SECRET_KEY, EventFlag.BEAT_BLAINE),
    )
    items = tuple(
        int(item)
        for item, event in eligible
        if bag.get(int(item)) == 1 and event_flag_is_set(raw.event_flags, int(event))
    )
    if allow_spare_tm_storage and raw.badge_bits == 255:
        # Conserved unused reward TMs are a disclosed, reversible bag-relief
        # fallback. Keep HMs, fossils, balls, medicine and useful held resources.
        # No TM is consumed/taught and none is sold, discarded or released.
        items += tuple(int(item) for item in
                       (ItemId.TM34_BIDE, ItemId.TM46_PSYWAVE, ItemId.TM27_FISSURE,
                        ItemId.TM06_TOXIC)
                       if bag.get(int(item)) == 1)
    return items[:needed]


def completed_key_storage_binding(runtime, actions, *, route, reserved_slots=2,
                                  include_indigo_lobby=False, allow_spare_tm_storage=False):
    """Expose a normal, routed PC deposit as its own capacity goal.

    Existing callers remain unchanged. Current-party travel is guarded; the
    existing PC controller deposits only already-completed singleton keys.
    No progress flag, party member, cash or item quantity is manufactured.
    """
    if type(include_indigo_lobby) is not bool:
        raise TypeError("Indigo storage permission must be an explicit boolean")
    raw = runtime.reader.read()
    items = completed_key_capacity_items(raw, reserved_slots=reserved_slots,
                                        allow_spare_tm_storage=allow_spare_tm_storage)
    if not items or not _field_ready(runtime):
        return None
    pc = dict(runtime.reader.read_pc_items())
    if len(set(pc) | set(items)) > 50 or any(pc.get(item, 0) + 1 > 99 for item in items):
        return None
    source = runtime.emulator.save_state_bytes()
    before_actions, before_frames = actions.actions_executed, runtime.emulator.frame_count
    allow_surf = getattr(route, "allow_surf", False) is True
    observer = Gen1TraversalObserver(
        runtime.reader,
        capability_projector=lambda r: (
            cut_capabilities(r)
            | (
                surf_capabilities(r, surf_allowed=surf_permission(runtime.emulator, r).allowed)
                if allow_surf
                else frozenset()
            )
        ),
        hazard_projector=Gen1TrainerSightProjector(
            route.rom, runtime.reader, full_event_offsets=True
        ),
    )
    start = observer.observe()
    candidates = []
    boundaries = [(int(center), (4, 13)) for center in sorted(_POKEMON_CENTER_MAPS)]
    if include_indigo_lobby:
        # The actual Indigo lobby PC is shifted from a standard Center. Match
        # the pinned ROM's same PC tile before advertising this native boundary.
        lobby = route.route_world.terrain.get(int(MapId.INDIGO_PLATEAU_LOBBY))
        center = route.route_world.terrain.get(int(MapId.SAFFRON_POKECENTER))
        if (lobby is not None and center is not None
                and lobby.tiles[7][15] == center.tiles[3][13] == 0x52
                and lobby.walkable[8][15]):
            boundaries.append((int(MapId.INDIGO_PLATEAU_LOBBY), (8, 15)))
    for center, at in boundaries:
        try:
            plan = route.route_world.plan_feasible_to_map(start, center, goal_at=at)
        except RoutePlanningError:
            continue
        candidates.append(plan)
    if (
        runtime.emulator.save_state_bytes() != source
        or actions.actions_executed != before_actions
        or runtime.emulator.frame_count != before_frames
    ):
        raise ValueError("storage quotation changed its source")
    if not candidates:
        return None
    plan = min(candidates, key=lambda p: (p.cost, p.terminal_map))
    cash_route = certified_cash_safe_transition(route, raw, plan) or route
    used, terminal = False, None

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("key storage is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        replace(cash_route, destination_map=plan.terminal_map, destination_at=plan.terminal_at)(
            actions, runtime.reader, runtime.emulator
        )
        before = runtime.reader.read()
        if (
            not _field_ready(runtime)
            or before.map_id != plan.terminal_map
            or (before.player_y, before.player_x) != plan.terminal_at
            or before.bag_items != raw.bag_items
            or before.player_money != raw.player_money
            or before.party_species_ids != raw.party_species_ids
            or dict(runtime.reader.read_pc_items()) != pc
            or completed_key_capacity_items(before, reserved_slots=reserved_slots,
                                            allow_spare_tm_storage=allow_spare_tm_storage) != items
        ):
            raise RuntimeError("key storage approach changed its reservation")
        boxes, dex = runtime.reader.read_all_box_states(), runtime.reader.read_pokedex_state()
        expected_bag, expected_pc = dict(before.bag_items), dict(pc)
        for item in items:
            sabrina._deposit_pc_item(
                actions, runtime.reader, runtime.emulator, ItemId(item), silph.DEFAULT_SILPH_TIMING
            )
            expected_pc[item] = expected_pc.get(item, 0) + expected_bag.pop(item)
            after = runtime.reader.read()
            if (
                dict(after.bag_items or ()) != expected_bag
                or dict(runtime.reader.read_pc_items()) != expected_pc
                or runtime.reader.read_all_box_states() != boxes
                or runtime.reader.read_pokedex_state() != dex
                or not _field_ready(runtime)
                or any(
                    getattr(after, field) != getattr(before, field)
                    for field in (
                        "map_id",
                        "player_y",
                        "player_x",
                        "party_species_ids",
                        "party_levels",
                        "party_moves",
                        "party_hp",
                        "party_pp",
                        "party_status",
                        "badge_bits",
                        "player_money",
                        "event_flags",
                    )
                )
            ):
                raise RuntimeError("PC deposit did not conserve exact items and protected state")
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                support="completed_key_capacity_storage",
                stored_items=list(items),
                learned_item_selection=False,
                bag_slots_before=len(raw.bag_items),
                bag_slots_after=len(expected_bag),
                items_conserved=True,
                sales=0,
            ),
        )

    def verify(report):
        return (
            GoalVerification.succeeded()
            if terminal is not None
            and runtime.emulator.save_state_bytes() == terminal
            and _field_ready(runtime)
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return ExecutableGoalBinding(
        "pokemon.red:completed-key-storage:" + sha256(source).hexdigest(),
        GoalKind.MANAGE_STORAGE,
        min(1.0, 0.02 + plan.cost / 3000),
        0.0,
        execute,
        verify,
        maximum_cash_debit=0,
    )
