"""Observed item obstruction support using the existing native pickup controller."""

from dataclasses import replace
from hashlib import sha256

from .actions import MacroAction, MacroActionKind
from .gen1_acquisition import map_objects
from .gen1_field_moves import gen1_field_capabilities
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import Gen1TrainerSightProjector, TrainerFacing
from .gen1_traversal import cut_capabilities
from .goal_manager import GoalDecisionOutcome, GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .local_router import without_coordinates
from .observation import MapId, semantic_facts
from .player_option_challenge import OptionChallenge
from .red_badge_corridor import qualified_badge_gate_world
from .red_field_item import (
    RedFieldItem,
    collect_visible_field_item,
    field_item_is_available,
    red_field_items,
)
from .red_pc_storage import face_pc_boundary
from .red_player_field_goals import _field_ready
from .red_player_lesson import capture_player_lesson_snapshot
from .red_player_story_travel import DESTINATIONS, story_travel_binding
from .route_plan import RoutePlanningError

_PAID_SAFARI_MAPS = frozenset(int(m) for m in (
    MapId.SAFARI_ZONE_EAST, MapId.SAFARI_ZONE_NORTH,
    MapId.SAFARI_ZONE_WEST, MapId.SAFARI_ZONE_CENTER,
))


def _resource_passage_binding(runtime, actions, route):
    """Reuse reset cave gates only as mechanics within a selected delivery."""
    from .gen1_boulder_switch import (
        victory_road_first_switch,
        victory_road_second_switches,
        victory_road_third_floor,
    )
    from .red_player_victory_road import CAVE_MAPS, _puzzle_option

    raw = runtime.reader.read()
    if raw.map_id not in CAVE_MAPS:
        return None
    second = victory_road_second_switches(route.rom)
    for name, contract in (
        ("first-switch", victory_road_first_switch(route.rom)),
        ("second-switch", second[0]),
        ("third-switch", victory_road_third_floor(route.rom)[0]),
        ("final-switch", second[1]),
    ):
        if raw.map_id != contract.map_id:
            continue
        option = _puzzle_option(runtime, actions, route, name, contract, None)
        if option is not None:
            return option[0]
    return None


def field_item_resupply_binding(
    runtime, actions, *, route, item_id, unsupported_target_maps=frozenset(),
    require_complete_quote=False,
):
    """One real, finite resource peer; routing/pickup do not choose strategy.

    Quote the full delivery, not a successful prefix without stock. A removed
    item stays absent after reload;
    no fabricated purchase quote, reward, remote inventory or collection credit.
    Existing pickup independently proves the gain and protected native state.
    """
    if type(item_id) is not int or not 1 <= item_id <= 250:
        raise ValueError("field resource needs a cartridge item identity")
    if type(require_complete_quote) is not bool:
        raise TypeError("complete delivery quotation requires an explicit boolean")
    if (not isinstance(unsupported_target_maps, frozenset)
            or any(type(m) is not int or not 0 <= m <= 255
                   for m in unsupported_target_maps)):
        raise ValueError("unsupported field-delivery maps require explicit map IDs")
    if not _field_ready(runtime):
        return None
    raw = runtime.reader.read()
    if (
        raw.bag_items is None
        or dict(raw.bag_items).get(item_id, 0)
        or len(raw.bag_items) >= 20
        or raw.player_money is None
        or not raw.party_hp
        or not any(raw.party_hp)
    ):
        return None
    targets = tuple(
        t
        for t in red_field_items(route.rom, item_id)
        # This delivery promises unchanged cash and uses ordinary wild escape,
        # not Safari admission/session handling. A geometric doorway does not
        # authorize crossing a paid gate, even when the item is still visible.
        if t.map_id not in _PAID_SAFARI_MAPS
        # A caller must not advertise a target whose puzzle/transport mechanics
        # its delivery has not composed. Other real targets remain peers.
        if t.map_id not in unsupported_target_maps
        if field_item_is_available(route.rom, runtime.reader, t)
    )
    if not targets:
        return None
    def quote_arrival(target):
        from .red_player_victory_road import observed_puzzle_world

        current = runtime.reader.read()
        world = observed_puzzle_world(
            qualified_badge_gate_world(route.route_world), runtime.reader
        )
        current_route = replace(route, route_world=world)
        start = Gen1TraversalObserver(
            runtime.reader,
            capability_projector=(
                (lambda r: gen1_field_capabilities(runtime.emulator, r))
                if getattr(route, "allow_surf", False) is True
                else cut_capabilities
            ),
            hazard_projector=Gen1TrainerSightProjector(
                route.rom, runtime.reader, full_event_offsets=True
            ),
        ).observe()
        candidates = []
        try:
            if current.map_id == target.map_id:
                present = {o.sprite_index: o for o in runtime.reader.read_current_map_objects()}
                obj = present.get(target.object_index)
                if (
                    obj is None
                    or obj.moving
                    or (obj.picture_id, obj.at) != (target.sprite_id, target.at)
                ):
                    return None
            for facing in TrainerFacing:
                dy, dx = facing.delta
                at = target.at[0] - dy, target.at[1] - dx
                if min(at) < 0:
                    continue
                try:
                    plan = world.plan_feasible_to_map(start, target.map_id, goal_at=at)
                except RoutePlanningError:
                    continue
                candidates.append((plan.cost, current_route, target.map_id, at, facing.value, None))
        except RoutePlanningError:
            return None
        if candidates:
            return min(candidates, key=lambda row: row[0])
        if current.map_id == target.map_id:
            return None
        passage = _resource_passage_binding(runtime, actions, current_route)
        if passage is not None:
            return (passage.estimated_effort * 3000, current_route, current.map_id,
                    (current.player_y, current.player_x), None, passage)
        # A finite route search may not span the entire world. This remains
        # navigation inside the already selected delivery,not another goal.
        from .red_story_map_frontier import story_frontier_target

        try:
            destination, at = story_frontier_target(world, start, target.map_id)
            try:
                plan = world.plan_feasible_to_map(start, destination, goal_at=at)
            except RoutePlanningError:
                # Relevance may prefer a doorway on a disconnected floor
                # island. Keep the same next map,but let the real guarded
                # planner find a reachable arrival. Never execute the relaxed
                # preview or credit this prefix as acquired stock.
                plan = world.plan_feasible_to_map(start, destination)
                if plan.terminal_map != destination:
                    return None
                at = plan.terminal_at
        except RoutePlanningError:
            return None
        return plan.cost, current_route, destination, at, None, None

    candidates = tuple((quoted, target) for target in targets
                       if (quoted := quote_arrival(target)) is not None
                       and (not require_complete_quote
                            or (quoted[2] == target.map_id and quoted[4] is not None
                                and quoted[5] is None)))
    if not candidates:
        return None
    (cost, _, _, _, _, _), target = min(candidates, key=lambda row: row[0][0])
    source = runtime.emulator.save_state_bytes()
    used, terminal, receipt, route_stopped = False, None, None, False
    expected_bag = dict(raw.bag_items)
    expected_bag[item_id] = 1

    def unchanged_route_stop():
        after = runtime.reader.read()
        fields = ("bag_items", "player_money", "party_species_ids", "party_levels",
                  "party_hp", "party_max_hp", "party_status", "party_moves", "party_pp",
                  "badge_bits", "event_flags")
        return _field_ready(runtime) and all(
            getattr(raw, name, None) is not None
            and getattr(after, name, None) == getattr(raw, name)
            for name in fields
        )

    def execute():
        nonlocal used, terminal, receipt, route_stopped
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("field resupply is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        visited, transitions, passages = set(), 0, []
        for _ in range(32):
            transitions += 1
            current = runtime.reader.read()
            boundary = (current.map_id, current.player_y, current.player_x,
                        getattr(current, "event_flags", b""))
            if boundary in visited or not _field_ready(runtime):
                raise RuntimeError("field resource delivery did not advance a ready boundary")
            visited.add(boundary)
            quoted = quote_arrival(target)
            if quoted is None:
                # A successful prefix can expose a real planning dead end.
                # Retain a measured failure, never supplied stock or success.
                if (
                    transitions <= 1
                    or actions.actions_executed <= a
                    or runtime.emulator.frame_count <= f
                    or not unchanged_route_stop()
                ):
                    raise RuntimeError("field resource delivery has no verified safe route stop")
                route_stopped = True
                terminal = runtime.emulator.save_state_bytes()
                receipt = GoalExecutionReport(
                    actions.actions_executed - a, runtime.emulator.frame_count - f,
                    dict(schema="pokemon.red.field-delivery-route-stop.v1",
                         support="cartridge_finite_field_resupply_stop", item=item_id,
                         route_unavailable=True, protected_native_state_unchanged=True,
                         item_acquired=False, quantity_acquired=0, complete_delivery=False,
                         purchases=0, cash_debit=0, objective_completed=False,
                         source_sha256=sha256(source).hexdigest(),
                         terminal_sha256=sha256(terminal).hexdigest(),
                         quoted_navigation_transitions=transitions),
                )
                return receipt
            _, current_route, destination, at, facing, passage = quoted
            if passage is not None:
                passage_report = passage.execute()
                if (passage.verify(passage_report).status is not GoalDecisionOutcome.SUCCEEDED
                        or passage_report.evidence.get("objective_completed") is not False):
                    raise RuntimeError("field resource return passage is unverified")
                passages.append(dict(passage_report.evidence))
                continue
            replace(current_route, destination_map=destination, destination_at=at)(
                actions, runtime.reader, runtime.emulator
            )
            settle_story_interaction(runtime, actions)
            if facing is not None:
                face_field_item_boundary(runtime, actions, facing)
                collect_visible_field_item(actions, runtime.reader, target)
                break
        else:
            raise RuntimeError("field resource delivery exceeded its finite transition allowance")
        after = runtime.reader.read()
        if (
            not _field_ready(runtime)
            or after.map_id != destination
            or (after.player_y, after.player_x) != at
            or dict(after.bag_items or ()) != expected_bag
            or after.player_money != raw.player_money
            or after.party_species_ids != raw.party_species_ids
            or after.badge_bits != raw.badge_bits
            or field_item_is_available(route.rom, runtime.reader, target)
        ):
            raise RuntimeError("field resupply terminal or resources differ")
        terminal = runtime.emulator.save_state_bytes()
        receipt = GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                support="cartridge_finite_field_resupply",
                item=item_id,
                item_acquired=True,
                quantity_acquired=1,
                complete_delivery=True,
                quoted_navigation_transitions=transitions,
                reopened_passages=passages,
                observed_map_boundary=destination,
                purchases=0,
                cash_debit=0,
                learned_authority="resource_goal_choice",
                learned_pickup=False,
                objective_completed=False,
                automatic_objectives=[],
            ),
        )
        return receipt

    def verify(report):
        if route_stopped:
            # The goal is still failed even when safe continuation is proved.
            if (report is not receipt or runtime.emulator.save_state_bytes() != terminal
                    or not unchanged_route_stop()):
                return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return (
            GoalVerification.succeeded()
            if terminal is not None
            and report is receipt
            and runtime.emulator.save_state_bytes() == terminal
            and _field_ready(runtime)
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return ExecutableGoalBinding(
        "pokemon.red:field-resupply:" + sha256(source).hexdigest() + ":" + str(item_id),
        GoalKind.RESUPPLY,
        min(1.0, cost / 3000),
        0.02,
        execute,
        verify,
    )


def face_field_item_boundary(runtime, actions, direction, *, maximum_wild_exits=2):
    """Finish only native wild setup caused by turning at a blocked field item."""
    from .red_pc_storage import RedPCStorageError

    if type(maximum_wild_exits) is not int or not 0 <= maximum_wild_exits <= 2:
        raise ValueError("field-item facing needs its finite wild-exit bound")
    for attempt in range(maximum_wild_exits + 1):
        before = runtime.reader.read()
        try:
            face_pc_boundary(actions, runtime.reader, direction)
            return
        except RedPCStorageError as error:
            current = runtime.reader.read()
            if (str(error) != "PC facing did not preserve its bound position"
                or before.battle_state != 0 or current.battle_state != 1
                or attempt == maximum_wild_exits or runtime.emulator.pressed_buttons
                or (before.map_id, before.player_y, before.player_x)
                   != (current.map_id, current.player_y, current.player_x)
                or any(getattr(before, key) is None
                       or getattr(before, key) != getattr(current, key) for key in (
                    "player_money", "bag_items", "event_flags", "badge_bits", "party_count",
                    "party_species_ids", "party_levels", "party_max_hp", "party_stats",
                    "party_moves", "party_pp"))):
                raise
            # This existing binder verifies native whole-party escape and custody.
            # No pickup/Confirm is sent until a fresh facing proof succeeds.
            evidence = settle_story_interaction(runtime, actions)
            if evidence is None:
                raise RuntimeError("field-item turn lacks verified wild settlement") from error
            record = getattr(actions, "record_diagnostic_event", None)
            if callable(record):
                record("field_item_turn_wild_settlement", dict(
                    actor="rule_based_support", model_queries=0,
                    map_id=current.map_id,at=[current.player_y,current.player_x],
                    attempt=attempt+1,escape=evidence,item_interaction_executed=False))


def settle_story_interaction(runtime, actions):
    """Let deferred encounter setup settle before sending interaction buttons.

    A route can reach its coordinate before the next tick starts a wild battle.
    Reuse the typed escape actor; never press dialogue Confirm inside that battle.
    """
    from .red_player_wild_recovery import interrupted_wild_binding

    before = runtime.reader.read()
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=120))
    escaped = None
    current = runtime.reader.read()
    if current.battle_state:
        binding = interrupted_wild_binding(runtime, actions, allow_fainted_active=True)
        if current.battle_state != 1 or binding is None:
            raise RuntimeError("story interaction encountered unsupported battle control")
        escaped = binding.execute()
        if binding.verify(escaped).status is not GoalDecisionOutcome.SUCCEEDED:
            raise RuntimeError("story interaction wild recovery is unverified")
    current = runtime.reader.read()
    if (
        not _field_ready(runtime)
        or current.map_id != before.map_id
        or (current.player_y, current.player_x) != (before.player_y, before.player_x)
    ):
        raise RuntimeError("story interaction did not settle its actual approach")
    return None if escaped is None else escaped.evidence


def blocking_field_item_binding(runtime, actions, *, route, destination_at, forbidden=frozenset()):
    """Offer only a real reachable item whose removal opens the local destination.

    Removing occupancy is a planning query, never the executable route. Native
    pickup verifies the bag increment, object removal and protected resources.
    """
    if not _field_ready(runtime):
        return None
    raw = runtime.reader.read()
    if raw.bag_items is None:
        return None
    world = route.route_world.with_current_observation(runtime.reader)
    map_id = raw.map_id
    world = replace(
        world,
        object_blockers={
            **world.object_blockers,
            map_id: world.object_blockers[map_id] | forbidden,
        },
        local_graphs={
            **world.local_graphs,
            map_id: without_coordinates(world.local_graphs[map_id], forbidden),
        },
    )
    route = replace(route, route_world=world)
    start = Gen1TraversalObserver(
        runtime.reader,
        capability_projector=cut_capabilities,
        hazard_projector=Gen1TrainerSightProjector(
            route.rom, runtime.reader, full_event_offsets=True
        ),
    ).observe()
    try:
        world.plan_feasible_to_map(start, map_id, goal_at=destination_at)
    except RoutePlanningError:
        pass
    else:
        return None
    present = {o.sprite_index: o for o in runtime.reader.read_current_map_objects()}
    bag = dict(raw.bag_items)
    candidates = []
    for index, obj in enumerate(map_objects(route.rom).get(map_id, ()), 1):
        if not obj.is_item or obj.is_trainer or len(obj.extra) != 1:
            continue
        item = RedFieldItem(obj.extra[0], map_id, index, obj.sprite, (obj.y, obj.x))
        live = present.get(index)
        if (
            live is None
            or live.moving
            or (live.picture_id, live.at) != (item.sprite_id, item.at)
            or item.at in forbidden
            or bag.get(item.item_id, 0) >= 99
            or (item.item_id not in bag and len(bag) >= 20)
        ):
            continue
        hypothetical = replace(
            world,
            object_blockers={
                **world.object_blockers,
                map_id: world.object_blockers[map_id] - {item.at},
            },
        )
        graph = hypothetical._graph_for_terrain(world.terrain[map_id])
        hypothetical = replace(
            hypothetical,
            local_graphs={**world.local_graphs, map_id: without_coordinates(graph, forbidden)},
        )
        probe = replace(start, occupied=start.occupied - {item.at})
        try:
            hypothetical.plan_feasible_to_map(probe, map_id, goal_at=destination_at)
        except RoutePlanningError:
            continue
        for facing in TrainerFacing:
            dy, dx = facing.delta
            at = item.at[0] - dy, item.at[1] - dx
            if min(at) < 0:
                continue
            try:
                plan = world.plan_feasible_to_map(start, map_id, goal_at=at)
            except RoutePlanningError:
                continue
            candidates.append((plan, facing, item))
    if not candidates:
        return None
    plan, facing, target = min(candidates, key=lambda row: row[0].cost)
    source = runtime.emulator.save_state_bytes()
    used, terminal = False, None

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("field item approach is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        replace(route, destination_map=map_id, destination_at=plan.terminal_at)(
            actions, runtime.reader, runtime.emulator
        )
        if not _field_ready(runtime):
            raise ValueError("field item approach did not settle")
        face_field_item_boundary(runtime, actions, facing.value)
        collect_visible_field_item(actions, runtime.reader, target)
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                support="observed_blocking_field_item",
                item=target.item_id,
                learned=False,
                objective_completed=False,
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
        "pokemon.red:field-item:" + sha256(source).hexdigest(),
        GoalKind.ADVANCE_STORY,
        0.05,
        0.02,
        execute,
        verify,
        maximum_cash_debit=0,
    )


def field_item_story_option(runtime, actions, *, route, objective_id, item_id):
    """Expose a registered item objective using real travel and visible pickup.

    No item is spawned and no puzzle passage is presumed open. Off-map travel
    ends at the next map boundary so live doors and trainer sight are observed.
    A caller may compose separate, disclosed puzzle mechanics when needed.
    """
    from .red_training_ground_route import ground_route_capability_projector

    if objective_id not in DESTINATIONS:
        raise ValueError("field item needs a registered story destination")
    if type(item_id) is not int or not 1 <= item_id <= 250:
        raise ValueError("story field item requires a cartridge item identity")
    if not _field_ready(runtime):
        return None
    before, lesson = capture_player_lesson_snapshot(runtime)
    if objective_id not in {
        o.id for o in runtime.adapter.graph.available_objectives(before.game_state)
    }:
        return None
    raw = before.raw
    if (
        raw.bag_items is None
        or dict(raw.bag_items).get(item_id, 0)
        or len(raw.bag_items) >= 20
        or raw.player_money is None
        or not raw.party_species_ids
        or not raw.party_hp
        or not any(raw.party_hp)
    ):
        return None
    targets = red_field_items(route.rom, item_id)
    if len(targets) != 1 or targets[0].map_id != DESTINATIONS[objective_id]:
        raise ValueError("story field item must have one matching cartridge destination")
    target = targets[0]
    challenge = OptionChallenge(False, False, 0.0, 0.0, 0.0)
    if raw.map_id != target.map_id:
        travel = story_travel_binding(
            runtime,
            actions,
            objective_id=objective_id,
            route=route,
            frontier=True,
            stop_at_map_boundary=True,
            allow_surf=getattr(route, "allow_surf", False) is True,
        )
        return None if travel is None else (travel, challenge)
    objects = [
        o
        for o in runtime.reader.read_current_map_objects()
        if o.sprite_index == target.object_index
    ]
    if (
        len(objects) != 1
        or objects[0].moving
        or (objects[0].picture_id, objects[0].at) != (target.sprite_id, target.at)
    ):
        return None
    world = route.route_world.with_current_observation(runtime.reader)
    route = replace(route, route_world=world)
    start = Gen1TraversalObserver(
        runtime.reader,
        capability_projector=ground_route_capability_projector(route, runtime.emulator),
        hazard_projector=Gen1TrainerSightProjector(
            route.rom, runtime.reader, full_event_offsets=True
        ),
    ).observe()
    candidates = []
    for facing in TrainerFacing:
        dy, dx = facing.delta
        at = target.at[0] - dy, target.at[1] - dx
        if min(at) < 0:
            continue
        try:
            plan = world.plan_feasible_to_map(start, target.map_id, goal_at=at)
        except RoutePlanningError:
            continue
        candidates.append((plan.cost, facing.value, plan.terminal_at))
    if not candidates:
        return None
    cost, facing, at = min(candidates)
    source = runtime.emulator.save_state_bytes()
    objective = runtime.adapter.graph.objective(objective_id)
    expected_bag = dict(raw.bag_items)
    expected_bag[item_id] = 1
    used, terminal = False, None

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("story field item is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        replace(route, destination_map=target.map_id, destination_at=at)(
            actions, runtime.reader, runtime.emulator
        )
        settle_story_interaction(runtime, actions)
        face_field_item_boundary(runtime, actions, facing)
        collect_visible_field_item(actions, runtime.reader, target)
        after = runtime.reader.read()
        if (
            dict(after.bag_items) != expected_bag
            or after.player_money != raw.player_money
            or after.badge_bits != raw.badge_bits
            or after.party_species_ids != raw.party_species_ids
            or not objective.completion_facts <= semantic_facts(after)
        ):
            raise RuntimeError("story field item reward or protected resources differ")
        runtime.observer.latch_verified_facts(objective.completion_facts)
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                support="observed_cartridge_story_item",
                item=item_id,
                objective=objective_id,
                objective_completed=True,
                learned_pickup=False,
                purchases=0,
                trainer_battles=0,
                automatic_objectives=[],
            ),
        )

    def verify(report):
        after, snapshot = capture_player_lesson_snapshot(runtime)
        passed = (
            terminal is not None
            and runtime.emulator.save_state_bytes() == terminal
            and _field_ready(runtime)
            and after.raw.map_id == target.map_id
            and dict(after.raw.bag_items) == expected_bag
            and objective.completion_facts <= semantic_facts(after.raw)
            and set(lesson["completed_objectives"]) <= set(snapshot["completed_objectives"])
            and objective_id in snapshot["completed_objectives"]
        )
        return (
            GoalVerification.succeeded()
            if passed
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return (
        ExecutableGoalBinding(
            "pokemon.red:story-field-item:" + sha256(source).hexdigest(),
            GoalKind.ADVANCE_STORY,
            min(1.0, cost / 3000),
            0.02,
            execute,
            verify,
            maximum_cash_debit=0,
            story_objective_ref=objective_id,
        ),
        challenge,
    )
