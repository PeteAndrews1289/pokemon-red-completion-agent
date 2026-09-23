"""Opt-in ordinary-player NPC acquisitions with explicit PC preparation.

Only discovery is action-free. One selected binding owns departure, transport,
storage menus and exchange under the caller's ordinary action/time budgets.
This DEVELOPMENT option is not admission to registered learner training.
"""

from collections import Counter
from dataclasses import replace
from functools import partial

from .actions import MacroAction, MacroActionKind
from .collection import CollectionLocation
from .gen1_cartridge import internal_to_dex
from .gen1_field_moves import (
    GEN1_FIELD_MOVE_IDS,
    Gen1FieldMoveError,
    Gen1FieldMovePort,
    fly_menu_indices,
)
from .gen1_route_runtime import Gen1TraversalObserver
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import RED_FLY_TOWN_NAMES, Badge, EventFlag, event_flag_is_set
from .red_collection import red_species_ref
from .red_collection_fly import red_fly_landings
from .red_indoor_departure_plan import bounded_indoor_departure
from .red_npc_trade import (
    RedNPCTradeError,
    exchange_allowed,
    execute_adjacent_trade,
    stationary_npc_trades,
    verify_npc_exchange,
)
from .red_party import PokemonRedPartyReader
from .red_pc_storage import (
    close_generic_pc_session,
    deposit_party_member,
    face_pc_boundary,
    open_bills_pc,
    switch_box,
    withdraw_box_member,
)
from .red_resource_goal_router import _supported_plan, collection_field_capabilities
from .route_executor import execute_route
from .route_plan import RoutePlanningError


def _approach(world, start, trade):
    y, x = trade.at
    plans = []
    for at in ((y + 1, x), (y, x - 1), (y, x + 1), (y - 1, x)):
        try:
            plan = world.plan_feasible_to_map(start, trade.map_id, goal_at=at)
        except RoutePlanningError:
            continue
        if len(plan.steps) <= 256 and _supported_plan(plan, allow_cut=True):
            plans.append(plan)
    return min(plans, key=lambda p: (p.cost, len(p.steps))) if plans else None


def npc_trade_bindings(runtime, observation, actions, world):
    if not getattr(runtime, "npc_trades", False) or runtime.registration_policy is None:
        return ()
    reader, policy = runtime.reader, runtime.registration_policy
    raw = observation.raw
    if (
        raw.battle_state != 0
        or not observation.input_ready
        or reader.read_bottom_dialogue_box_visible()
        or reader.read_safari_session_state().has_active_session
        or reader.read_pending_trainer_battle_identity() is not None
        or reader.read_fly_menu_state() is not None
    ):
        return ()
    observer = Gen1TraversalObserver(
        reader,
        capability_projector=partial(
            collection_field_capabilities, runtime.emulator, allow_cut=True, allow_surf=False
        ),
    )
    origin = observer.observe()
    if not origin.ready or origin.interruption or origin.mode != "land":
        return ()
    offers = stationary_npc_trades(world.rom)
    flags = reader.read_completed_npc_trades()
    result = []
    for trade in offers:
        if trade.index in flags or not exchange_allowed(
            observation.collection_observation,
            trade,
            policy.protected_counts,
            policy.goal_registered(observation.collection_observation),
        ):
            continue
        binding = _bind(runtime, observation, actions, world, observer, origin, trade, flags)
        if binding is not None:
            result.append(binding)
    return tuple(result)


def _bind(runtime, observation, actions, world, observer, origin, trade, flags):
    reader, policy = runtime.reader, runtime.registration_policy
    source = min(
        (
            s
            for s in observation.collection_observation.specimens
            if s.species_ref == red_species_ref(trade.give)
            and s.location in {CollectionLocation.PARTY, CollectionLocation.BOX}
        ),
        key=lambda s: (s.location is CollectionLocation.BOX, s.container_index, s.slot_index),
        default=None,
    )
    if source is None:
        return None
    boxed = source.location is CollectionLocation.BOX
    # The shared PC executor supports the post-Pokédex four/five-entry menu,
    # not the early three-entry menu. Prove that prerequisite before offering.
    if boxed and (
        observation.raw.event_flags is None
        or not event_flag_is_set(observation.raw.event_flags, int(EventFlag.GOT_POKEDEX))
    ):
        return None
    party_reader = PokemonRedPartyReader(runtime.emulator)
    original_party = party_reader.read().members
    deposit = None
    if boxed and len(original_party) == 6:
        deposit = next(
            (
                m
                for m in reversed(original_party)
                if not any(move.move_id in GEN1_FIELD_MOVE_IDS for move in m.moves)
            ),
            None,
        )
        if deposit is None or len(reader.read_current_box_state().species_ids) >= 20:
            return None
    departure = None
    start = origin
    # A party-ready source with a bounded direct path needs neither Fly nor a
    # town detour. This also resumes partial transport from its actual endpoint.
    direct = None if boxed else _approach(world, start, trade)
    if direct is None:
        if origin.map_id >= 0x25:
            departure = bounded_indoor_departure(origin, world)
            if departure is None:
                return None
            start = replace(
                start, map_id=departure.terminal_map, at=departure.terminal_at, occupied=frozenset()
            )
        flight = start.map_id != trade.town
        if flight:
            if trade.town not in reader.read_fly_destinations() or not int(
                observation.raw.badge_bits or 0
            ) & int(Badge.THUNDER):
                return None
            try:
                fly_menu_indices(observation.raw)
            except Gen1FieldMoveError:
                return None
            start = replace(
                start,
                map_id=trade.town,
                at=dict(red_fly_landings(world.rom))[trade.town],
                last_outside_map=trade.town,
                occupied=frozenset(),
            )
    else:
        flight = False
    to_pc = None
    if boxed:
        try:
            to_pc = world.plan_feasible_to_map(start, trade.center, goal_at=(4, 13))
        except RoutePlanningError:
            return None
        if len(to_pc.steps) > 128 or not _supported_plan(to_pc):
            return None
        start = replace(
            start,
            map_id=trade.center,
            at=(4, 13),
            occupied=frozenset(),
            last_outside_map=trade.town,
        )
    approach = direct if direct is not None else _approach(world, start, trade)
    if approach is None:
        return None
    inverse = {national: internal for internal, national in internal_to_dex(world.rom).items()}
    before_actions, before_frames = actions.actions_executed, runtime.emulator.frame_count
    original_boxes = reader.read_all_box_states()
    used = completed = False
    receipt = {}

    def field_port():
        return Gen1FieldMovePort(
            actions,
            reader,
            runtime.emulator,
            cut_block_swaps={s.before: s.after for s in world.rules.cut_block_swaps},
        )

    cut_receipts = []

    def route(plan):
        if plan is None or not _supported_plan(plan, allow_cut=True):
            raise RedNPCTradeError("trade route disappeared")
        port = field_port()
        result = execute_route(
            plan,
            port,
            observer,
            replanner=world.replanner(),
        )
        if not result.passed:
            raise RedNPCTradeError("trade route did not settle")
        cut_receipts.extend(port.cut_receipts)
        return len(result.executed_steps)

    def execute():
        nonlocal used, completed, receipt
        if used:
            raise RedNPCTradeError("trade binding already consumed")
        used = True
        if (
            runtime.adapter.observe() != observation
            or observer.observe() != origin
            or party_reader.read().members != original_party
            or reader.read_all_box_states() != original_boxes
            or reader.read_completed_npc_trades() != flags
            or runtime.emulator.frame_count != before_frames
            or actions.actions_executed != before_actions
            or runtime.emulator.pressed_buttons
        ):
            raise RedNPCTradeError("trade origin changed before input")
        steps = route(departure) if departure else 0
        if flight:
            name = RED_FLY_TOWN_NAMES[trade.town].lower().replace(" ", "_")
            field_port().execute(MacroAction(MacroActionKind.FIELD_MOVE, "fly:" + name))
            landed = observer.observe()
            if (
                not landed.ready
                or landed.mode != "land"
                or landed.map_id != trade.town
                or landed.at != dict(red_fly_landings(world.rom))[trade.town]
            ):
                raise RedNPCTradeError("trade flight landing differs")
        if boxed:
            steps += route(
                world.plan_feasible_to_map(observer.observe(), trade.center, goal_at=(4, 13))
            )
            face_pc_boundary(actions, reader, "up")
            open_bills_pc(actions, reader)
            if deposit:
                report = deposit_party_member(
                    actions, reader, party_slot=deposit.slot, expected_species_id=deposit.species_id
                )
                if not report.passed:
                    raise RedNPCTradeError("trade preparation deposit failed")
            if reader.read_current_box_state().box_index != source.container_index:
                report = switch_box(actions, reader, target_box_index=source.container_index)
                if not report.passed:
                    raise RedNPCTradeError("trade preparation box switch failed")
            report = withdraw_box_member(
                actions,
                reader,
                box_slot=source.slot_index + 1,
                expected_species_id=inverse[trade.give],
            )
            if not report.passed:
                raise RedNPCTradeError("trade preparation withdrawal failed")
            close_generic_pc_session(actions, reader)
            prepared = runtime.adapter.observe().collection_observation

            def stock(c):
                return Counter((s.species_ref, s.level) for s in c.specimens)

            if stock(prepared) != stock(observation.collection_observation):
                raise RedNPCTradeError("trade storage preparation changed physical stock")
        steps += route(_approach(world, observer.observe(), trade))
        slot = len(party_reader.read().members) if boxed else source.slot_index + 1
        receipt = execute_adjacent_trade(
            actions,
            reader,
            party_reader,
            trade,
            source_slot=slot,
            source_species_id=inverse[trade.give],
            target_species_id=inverse[trade.receive],
        )
        completed = True
        return GoalExecutionReport(
            actions.actions_executed - before_actions,
            runtime.emulator.frame_count - before_frames,
            {
                "mechanic": "npc_trade",
                "boxed_source": boxed,
                "deposited_party_slot": deposit.slot if deposit else None,
                "fly_used": flight,
                "route_steps": steps,
                "verified_cuts": len(cut_receipts),
                **receipt,
            },
        )

    def verify(report):
        after = runtime.adapter.observe()
        if (
            completed
            and report.actions_executed > 0
            and not runtime.emulator.pressed_buttons
            and not reader.read_bottom_dialogue_box_visible()
            and verify_npc_exchange(
                observation,
                after,
                trade,
                level=source.level,
                flags_before=flags,
                flags_after=reader.read_completed_npc_trades(),
                protected=policy.protected_counts,
            )
        ):
            return GoalVerification.succeeded()
        return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

    effort = sum(len(p.steps) for p in (departure, to_pc, approach) if p is not None)
    return ExecutableGoalBinding(
        binding_ref=f"red-npc-trade:{trade.index}",
        kind=GoalKind.ACQUIRE_SPECIES,
        estimated_effort=min(1.0, (effort + (100 if boxed else 0) + 120) / 1000),
        estimated_risk=0.1,
        execute=execute,
        verify=verify,
        search_source_ref=f"pokemon.red:npc-trade:{trade.index}",
    )
