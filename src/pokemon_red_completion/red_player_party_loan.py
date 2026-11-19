"""Repay one declared temporary PC loan through the existing native mechanics.

This is execution support inside the selected goal's port and budget. It never
loads a save, selects a goal, heals implicitly or refreshes the identity guard.
"""

from collections import Counter
from dataclasses import replace
from hashlib import sha256

from .gen1_route_runtime import Gen1TraversalObserver
from .red_goal_skills import finish_center_dialogue, prepare_center_departure
from .red_pc_storage import (
    close_generic_pc_session,
    deposit_party_member,
    face_pc_boundary,
    open_bills_pc,
    switch_box,
    withdraw_box_member,
)
from .red_player_party_guard import RedPlayerPartyGuard
from .red_resource_goal_router import _ROUTE_LIMITS, _walking_plan
from .red_team_training import close_menu
from .route_executor import execute_route


def _stock(runtime):
    guard = runtime.adapter.party_guard
    party = zip(guard.reader.preparation_specimen_refs(), guard.reader.read().members, strict=True)
    return Counter(
        (ref, member.species_id, member.level, member.experience) for ref, member in party
    ) + Counter(
        (member.preparation_ref, member.species_id, member.level, member.experience)
        for member in runtime.reader.read_box_specimen_identities()
    )


def _walk(runtime, actions, world, destination_map, at, *, venue_return=False, allow_cut=False):
    from .red_native_boxed_evolution import native_evolution_pc_replanner
    from .red_routed_recovery import guarded_collection_route_handler
    from .route_executor import ReplanRequest
    from .route_plan import RoutePlanningError

    if runtime.reader.read_bottom_dialogue_box_visible():
        raw = runtime.reader.read()
        if (raw.player_x, raw.player_y) == (3, 3):
            finish_center_dialogue(actions, runtime.reader)
        else:
            close_menu(actions, runtime.reader)
    # Only a pending, named field-carrier repayment opts in. The existing
    # projector and field port verify the real badge, holder and native Cut.
    from .gen1_traversal import cut_capabilities
    from .red_resource_goal_router import _supported_plan
    traversal = (Gen1TraversalObserver(runtime.reader, capability_projector=cut_capabilities)
                 if allow_cut else Gen1TraversalObserver(runtime.reader))
    supported = (lambda p: _supported_plan(p, allow_cut=True)) if allow_cut else _walking_plan
    start = traversal.observe()
    if (start.map_id, start.at) == (destination_map, at):
        return
    world = world.with_current_observation(runtime.reader)
    try:
        plan = world.plan_feasible_to_map(start, destination_map, goal_at=at)
    except RoutePlanningError:
        plan = native_evolution_pc_replanner(
            runtime, world, actions, allow_offscreen_approach=True
        )(
            ReplanRequest(start, destination_map, at, {start.map_id: start.occupied}, 1)
        )
    if not supported(plan):
        raise ValueError("party-loan return requires supported walking-only transport")
    prepare_center_departure(actions, runtime.reader)
    handler = (
        guarded_collection_route_handler(
            actions,
            runtime.reader,
            route_name="temporary PC loan venue return",
            maximum_scripted_dialogues=4,
        )
        if venue_return
        else None
    )

    def replan(request):
        # A Center NPC can move during the walk. Refresh its complete observed
        # occupancy instead of blocking both its old and current square. Keep
        # the executor's blocked tiles, capabilities and exact destination.
        current = world.with_current_observation(runtime.reader)
        replacement = native_evolution_pc_replanner(runtime, current, actions)(request)
        if not supported(replacement):
            raise ValueError("party-loan replan requires supported walking-only transport")
        return replacement

    route_actions = actions
    if allow_cut:
        from .gen1_field_moves import Gen1FieldMovePort
        route_actions = Gen1FieldMovePort(actions, runtime.reader, runtime.emulator,
            cut_block_swaps={swap.before: swap.after for swap in world.rules.cut_block_swaps})
    report = execute_route(
        plan,
        route_actions,
        traversal,
        limits=_ROUTE_LIMITS,
        interruption_handler=handler,
        replanner=replan,
    )
    terminal = traversal.observe()
    if (
        not report.passed
        or (terminal.map_id, terminal.at) != (destination_map, at)
        or not terminal.ready
        or terminal.interruption is not None
    ):
        raise ValueError("party-loan walking return did not reach settled native destination")

    if allow_cut:
        from .red_training_ground_route import record_verified_field_cuts
        record_verified_field_cuts(actions, route_actions)


def party_loan_return_center(runtime, world, *, allow_cut=False):
    """Read-only quote of a Center supported by the existing return executor."""
    from . import red_goal_context as context
    from .red_goal_skills import _POKEMON_CENTER_MAPS

    raw = runtime.reader.read()
    if raw.map_id in _POKEMON_CENTER_MAPS:
        return int(raw.map_id)
    venues = (
        context.ROUTE_11_TRAINING_VENUE,
        context.DIGLETTS_CAVE_TRAINING_VENUE,
        context.MANSION_TRAINING_VENUE,
    )
    venue = next((v for v in venues if v.is_in_map(raw)), None)
    centers = (
        []
        if venue is None
        else [m for m in _POKEMON_CENTER_MAPS if venue.is_in_center(replace(raw, map_id=m))]
    )
    if len(centers) != 1:
        # A failed venue transition can stop in its town rather than the venue.
        # Reuse actual walking routes to existing Centers, not a guessed healer
        # or a supplied strategic destination. This does not heal the party.
        from .route_plan import RoutePlanningError

        world = world.with_current_observation(runtime.reader)
        from .gen1_traversal import cut_capabilities
        from .red_resource_goal_router import _supported_plan
        start = (Gen1TraversalObserver(runtime.reader, capability_projector=cut_capabilities)
                 if allow_cut else Gen1TraversalObserver(runtime.reader)).observe()
        supported = (lambda p: _supported_plan(p, allow_cut=True)) if allow_cut else _walking_plan
        choices = []
        for center in sorted(_POKEMON_CENTER_MAPS):
            try:
                plan = world.plan_feasible_to_map(start, int(center), goal_at=(3, 3))
            except RoutePlanningError:
                continue
            if supported(plan):
                choices.append((plan.cost, int(center)))
        if not choices:
            return None
        centers = [min(choices)[1]]
    return int(centers[0])


def _reach_center(runtime, actions, world, *, allow_cut=False):
    center = party_loan_return_center(runtime, world, allow_cut=allow_cut)
    if center is None:
        # A native bird loan can end within Victory Road with no all-walking
        # Center route. Reuse the supported cave exit, Fly, and original loan PC.
        from .observation import MapId
        cave_maps = {MapId.VICTORY_ROAD_1F, MapId.VICTORY_ROAD_2F, MapId.VICTORY_ROAD_3F}
        if allow_cut or runtime.reader.read().map_id not in cave_maps:
            raise ValueError("party-loan return has no executable walking Center")
        from .red_dig_recovery import plan_dig_escape, execute_dig_escape
        raw = runtime.reader.read()
        dig = plan_dig_escape(world, runtime.reader, raw, Gen1TraversalObserver(runtime.reader).observe())
        if dig is not None:
            execute_dig_escape(world, runtime.reader, runtime.emulator, actions, dig)
            # The authenticated landing is outdoors. Resume the ordinary Center route.
            _reach_center(runtime, actions, world)
            return
        try:
            from red_current_source_preparation_20261004 import native_fly_usable, route_to
        except ModuleNotFoundError as error:
            if error.name != "red_current_source_preparation_20261004":
                raise
            raise ValueError("party-loan cave exit requires the native Fly route executor") from error
        from types import SimpleNamespace

        raw = runtime.reader.read()
        guard = runtime.adapter.party_guard
        if (guard.field_carrier is None
                and native_fly_usable(raw) and int(MapId.CERULEAN_CITY) in runtime.reader.read_fly_destinations()
                and len(guard.loanable_refs) == 1
                and set(guard.refs) - set(guard.reader.preparation_specimen_refs()) == set(guard.loanable_refs)):
            session = SimpleNamespace(rt=runtime, em=runtime.emulator, actions=actions)
            route_to(session, world, town=int(MapId.CERULEAN_CITY), map_id=int(MapId.CERULEAN_POKECENTER),
                     at=(3,3), capture_loan=True)
            return
        raise ValueError("party-loan return has no executable walking Center")
    if runtime.reader.read().map_id == center:
        return
    if allow_cut:
        _walk(runtime, actions, world, center, (3, 3), venue_return=True, allow_cut=True)
    else:
        _walk(runtime, actions, world, center, (3, 3), venue_return=True)


def restore_guarded_party_loan(runtime, actions, world, *, allow_cut_return=False):
    """Return the one named individual and preserve every specimen and resource."""
    guard = getattr(getattr(runtime, "adapter", None), "party_guard", None)
    if not isinstance(guard, RedPlayerPartyGuard) or guard.storage_reader is None:
        raise ValueError("party-loan return requires an explicit storage identity guard")
    guard.verify()
    if guard.field_carrier is not None:
        if guard.field_carrier.phase == "active":
            guard.verify_authorized_active_roster()
            return False
        from .red_field_carrier_custody import settle_pending_field_carrier
        return settle_pending_field_carrier(runtime, actions, world)
    active = guard.reader.preparation_specimen_refs()
    missing = set(guard.refs) - set(active)
    if not missing:
        guard.verify_active_roster_restored()
        return False
    if missing != set(guard.loanable_refs) or len(missing) != 1:
        raise ValueError("party-loan return requires exactly the declared loan")
    originals = [
        m for m in runtime.reader.read_box_specimen_identities() if m.preparation_ref in missing
    ]
    extras = [i + 1 for i, ref in enumerate(active) if ref not in guard.refs]
    before = runtime.adapter.observe()
    if (
        len(originals) != 1
        or before.raw.battle_state
        or not before.input_ready
        or len(active) not in {5, 6}
        # The guard may predate legitimate captures in this same segment.
        # Its retained roster need not already contain six individuals.
        or len(extras) != len(active) - (len(guard.refs) - 1)
        or (len(active) == 6 and not extras)
    ):
        raise ValueError("party-loan return lacks a unique settled storage exchange")
    original, stock = originals[0], _stock(runtime)
    if (
        len(active) == 6
        and before.collection_observation.box_counts[original.box_index]
        >= before.collection_observation.box_capacity
    ):
        raise ValueError("party-loan return needs free space in the original box")
    if allow_cut_return:
        _reach_center(runtime, actions, world, allow_cut=True)
    else:
        _reach_center(runtime, actions, world)
    center = runtime.reader.read().map_id
    _walk(runtime, actions, world, center, (4, 13))
    face_pc_boundary(actions, runtime.reader, "up")
    open_bills_pc(actions, runtime.reader)
    if (
        runtime.reader.read_current_box_state().box_index != original.box_index
        and not switch_box(actions, runtime.reader, target_box_index=original.box_index).passed
    ):
        raise ValueError("party-loan box rotation failed")
    if len(active) == 6:
        slot = extras[0]
        if not deposit_party_member(
            actions,
            runtime.reader,
            party_slot=slot,
            expected_species_id=runtime.reader.read().party_species_ids[slot - 1],
        ).passed:
            raise ValueError("party-loan guest deposit failed")
    originals = [
        m for m in runtime.reader.read_box_specimen_identities() if m.preparation_ref in missing
    ]
    if (
        len(originals) != 1
        or not withdraw_box_member(
            actions,
            runtime.reader,
            box_slot=originals[0].box_slot,
            expected_species_id=originals[0].species_id,
        ).passed
    ):
        raise ValueError("party-loan original withdrawal failed")
    close_generic_pc_session(actions, runtime.reader)
    _walk(runtime, actions, world, center, (3, 3))
    guard.verify_active_roster_restored()
    after = runtime.adapter.observe()
    if (
        stock != _stock(runtime)
        or before.raw.bag_items != after.raw.bag_items
        or before.raw.player_money != after.raw.player_money
        or before.collection_observation.owned_species != after.collection_observation.owned_species
        or after.raw.battle_state
        or not after.input_ready
    ):
        raise ValueError("party-loan return changed stock, resources or field control")
    return True


def party_loan_return_binding(runtime, actions, world, *, on_field_return=None):
    """Compulsory resume of one already-selected, named PC loan; zero queries."""
    from .goal_manager import GoalKind
    from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
    from .red_player_field_goals import _field_ready

    guard = getattr(getattr(runtime, "adapter", None), "party_guard", None)
    if not isinstance(guard, RedPlayerPartyGuard) or not _field_ready(runtime):
        return None
    guard.verify()
    custody = guard.field_carrier
    if custody is not None and custody.phase == "active":
        guard.verify_authorized_active_roster()
        return None
    if custody is None and set(guard.refs) <= set(guard.reader.preparation_specimen_refs()):
        return None
    source = runtime.emulator.save_state_bytes()
    used, terminal = False, None

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != source:
            raise ValueError("pending party loan is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        changed = restore_guarded_party_loan(runtime, actions, world)
        if custody is not None and on_field_return is not None:
            on_field_return(custody)
        if not changed and custody is None:
            raise ValueError("pending party loan was not restored")
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(actions.actions_executed - a, runtime.emulator.frame_count - f,
            dict(support="retained_named_party_loan_return", model_queries=0,
                retained_active_roster_restored=True, learned_party_choice=False))

    def verify(report):
        runtime.adapter.party_guard.verify_active_roster_restored()
        if terminal == runtime.emulator.save_state_bytes() and _field_ready(runtime):
            return GoalVerification.succeeded()
        from .goal_manager import GoalFailureReason

        return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

    return ExecutableGoalBinding("pokemon.red:retained-loan-return:" + sha256(source).hexdigest(),
        GoalKind.RECOVER_CONTROL, 0.0, 0.0, execute, verify)
