"""Selectable earned Victory Road mechanics, never the directed chapter policy.

Rival entry, badge dialogues and Strength use the existing native executors.
The inventory keeps recovery/preparation peers; this adapter never forces them.
"""

from dataclasses import asdict, is_dataclass, replace
from hashlib import sha256

from .actions import MacroAction, MacroActionKind
from .gen1_boulder_switch import (
    victory_road_boulder_drop,
    victory_road_first_switch,
    victory_road_second_switches,
    victory_road_third_floor,
)
from .gen1_field_moves import (
    Gen1FieldMoveError,
    Gen1FieldMovePort,
    fly_menu_indices,
    gen1_field_capabilities,
)
from .gen1_route_runtime import Gen1TraversalObserver, Gen1WildFleeHandler
from .gen1_strength import (
    Gen1StrengthExecutor,
    StrengthGoal,
    StrengthPlanningError,
    StrengthState,
    plan_strength,
)
from .gen1_terrain import terrain_with_block
from .gen1_trainer_parties import trainer_party_quote
from .gen1_trainer_sight import Gen1TrainerSightProjector
from .gen1_traversal import strength_capabilities
from .goal_manager import GoalDecisionOutcome, GoalFailureReason, GoalKind
from .goal_manager_composition_qualification import HardCompositionActionLimiter
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import (
    RED_FLY_TOWN_NAMES,
    Badge,
    ItemId,
    MapId,
    OverworldMovementMode,
    event_flag_is_set,
    semantic_facts,
)
from .party_preparation import PreparationPurpose
from .player_option_challenge import OptionChallenge
from .red_badge_corridor import CORRIDOR_MAPS, quote_badge_corridor, traverse_badge_corridor
from .red_battle_practice_cartridge import RedPracticeCartridge
from .red_collection_fly import red_fly_landings
from .red_machine_teaching import execute_machine_lesson, plan_machine_lesson
from .red_party_preparation import observe_preparation_members
from .red_player_field_goals import _field_ready
from .red_player_league_options import CHAMPION_PLAYER_TARGET, LEAGUE_PLAYER_TARGETS
from .red_player_route22_rival import OBJECTIVE, route22_rival_binding, route22_rival_contract
from .rom import verify_rom_bytes
from .route_plan import RoutePlanningError
from .victory_road import VictoryRoadChapterError
from .victory_road import _step as verified_victory_step

CAVE_MAPS = frozenset(
    int(m)
    for m in (
        MapId.VICTORY_ROAD_1F,
        MapId.VICTORY_ROAD_2F,
        MapId.VICTORY_ROAD_3F,
    )
)
LEAGUE_OBJECTIVES = frozenset(
    target.objective_id for target in LEAGUE_PLAYER_TARGETS + (CHAMPION_PLAYER_TARGET,)
)


def _public(value):
    if is_dataclass(value):
        return _public(asdict(value))
    if isinstance(value, dict):
        return {str(k): _public(v) for k, v in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_public(v) for v in value]
    return value


def _mechanics_option(
    runtime,
    actions,
    *,
    phase,
    operation,
    valid,
    cost=0.2,
    record=None,
    completes_objective=False,
    objective_ref=OBJECTIVE,
):
    if type(completes_objective) is not bool:
        raise TypeError("Victory Road completion authority must be explicit")
    if completes_objective and objective_ref != OBJECTIVE:
        raise ValueError("Access mechanics cannot complete a League objective")
    source = runtime.emulator.save_state_bytes()
    before = runtime.reader.read()
    protected = {
        name: getattr(before, name)
        for name in (
            "bag_items",
            "player_money",
            "badge_bits",
            "party_species_ids",
            "party_levels",
        )
    }
    used, terminal = False, None

    def terminal_valid(raw):
        return valid(raw) and (
            not completes_objective
            or runtime.adapter.graph.objective(OBJECTIVE).completion_facts <= semantic_facts(raw)
        )

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("Victory Road mechanics option is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        evidence = operation()
        after = runtime.reader.read()
        if (
            not _field_ready(runtime)
            or not terminal_valid(after)
            or any(getattr(after, name) != value for name, value in protected.items())
        ):
            raise RuntimeError("Victory Road mechanic did not prove its terminal")
        if completes_objective:
            runtime.observer.latch_verified_facts(
                runtime.adapter.graph.objective(OBJECTIVE).completion_facts
            )
        terminal = runtime.emulator.save_state_bytes()
        evidence = dict(
            objective=objective_ref,
            objective_completed=completes_objective,
            phase=phase,
            result=_public(evidence),
            support="observed_native_victory_road_mechanics",
            learned_puzzle=False,
            source_sha256=sha256(source).hexdigest(),
            terminal_sha256=sha256(terminal).hexdigest(),
        )
        if record is not None:
            record("victory-road-mechanic", evidence)
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            evidence,
        )

    def verify(report):
        if (
            terminal is None
            or runtime.emulator.save_state_bytes() != terminal
            or not _field_ready(runtime)
            or not terminal_valid(runtime.reader.read())
            or report.evidence["source_sha256"] != sha256(source).hexdigest()
            or report.evidence["terminal_sha256"] != sha256(terminal).hexdigest()
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    binding = ExecutableGoalBinding(
        "pokemon.red:victory-road:" + phase + ":" + sha256(source).hexdigest(),
        GoalKind.ADVANCE_STORY,
        min(1.0, cost),
        0.2,
        execute,
        verify,
        maximum_cash_debit=0,
        story_objective_ref=objective_ref,
    )
    return binding, OptionChallenge(False, False, 0.0, 0.0, 0.0)


def next_puzzle(rom, raw):
    """Required cartridge gates from live flags, not the old chapter schedule.

    The 2F entry clears 1F's transient switch flag. A later floor must not
    replay that completed crossing, nor may Indigo replay any reset cave flag.
    """
    if raw.map_id in {int(MapId.INDIGO_PLATEAU), int(MapId.INDIGO_PLATEAU_LOBBY)}:
        return None
    first = victory_road_first_switch(rom)
    second = victory_road_second_switches(rom)
    third, _ = victory_road_third_floor(rom)
    drop = victory_road_boulder_drop(rom)
    for name, contract in (
        ("first-switch", first),
        ("second-switch", second[0]),
        ("third-switch", third),
        ("boulder-drop", drop),
        ("final-switch", second[1]),
    ):
        if name == "first-switch" and raw.map_id != first.map_id:
            continue
        if not event_flag_is_set(raw.event_flags, contract.event):
            return name, contract
    return None


def observed_puzzle_world(world, reader):
    raw = reader.read()
    for switch in (
        victory_road_first_switch(world.rom),
        *victory_road_second_switches(world.rom),
        victory_road_third_floor(world.rom)[0],
    ):
        if switch.map_id != raw.map_id and event_flag_is_set(raw.event_flags, switch.event):
            changed = terrain_with_block(
                world.rom,
                world.terrain[switch.map_id],
                switch.changed_block_at,
                switch.changed_block,
                world.tilesets,
                water_set_ids=world.water_tilesets,
            )
            world = replace(
                world,
                terrain={**world.terrain, switch.map_id: changed},
                local_graphs={
                    **world.local_graphs,
                    switch.map_id: world._graph_for_terrain(changed),
                },
            )
    return world.with_current_observation(reader)


def strength_warp_guards(graph, map_id):
    """Allow a directional doorway stance, never its outward warp input."""
    forbidden, edges = set(graph.warp_locations[map_id]), set()
    for at in tuple(forbidden):
        exits = [e for e in graph.neighbors(map_id) if e.at == at and e.kind in {"warp", "return"}]
        if exits and all(e.exit_action in {"up", "down", "left", "right"} for e in exits):
            forbidden.remove(at)
            edges.update((at, e.exit_action) for e in exits)
    return frozenset(forbidden), frozenset(edges)


def dropped_boulder_follow_available(rom, raw):
    drop = victory_road_boulder_drop(rom)
    return (
        raw.map_id == drop.map_id
        and event_flag_is_set(raw.event_flags, drop.event)
        and (raw.player_y, raw.player_x)
        in {(drop.at[0], drop.at[1] - 2), (drop.at[0], drop.at[1] - 1)}
    )


def follow_dropped_boulder(runtime, actions, rom):
    """Existing qualified hole support; not a learned or generic hole solver."""
    before = runtime.reader.read()
    if not dropped_boulder_follow_available(rom, before) or before.battle_state != 0:
        raise ValueError("dropped-boulder follow source differs")
    drop = victory_road_boulder_drop(rom)
    escapes = []
    for _ in range(3):
        step_before = runtime.reader.read()
        if step_before.map_id == drop.destination_map:
            break
        label = "verified dropped-boulder follow"
        try:
            verified_victory_step(actions, runtime.reader, "right", label)
        except VictoryRoadChapterError as error:
            interrupted = runtime.reader.read()
            arrivals = {
                (step_before.map_id, step_before.player_y, step_before.player_x + 1),
                (drop.destination_map, 16, 22),
            }
            if (str(error) != label + " entered an unexpected battle."
                    or interrupted.battle_state != 1
                    or (interrupted.map_id, interrupted.player_y, interrupted.player_x)
                    not in arrivals):
                raise
            from .red_player_wild_recovery import interrupted_wild_binding

            escape = interrupted_wild_binding(runtime, actions, rom=rom)
            if escape is None:
                raise RuntimeError("hole encounter lacks a verified ordinary escape") from error
            report = escape.execute()
            settled = runtime.reader.read()
            if (escape.verify(report).status is not GoalDecisionOutcome.SUCCEEDED
                    or not _field_ready(runtime)
                    or (settled.map_id, settled.player_y, settled.player_x)
                    != (interrupted.map_id, interrupted.player_y, interrupted.player_x)):
                raise RuntimeError("hole encounter did not settle at its exact boundary") from error
            escapes.append(dict(report.evidence))
    after = runtime.reader.read()
    if (after.map_id, after.player_y, after.player_x) != (drop.destination_map, 16, 22):
        raise RuntimeError("qualified dropped-boulder arrival changed")
    for key in (
        "party_species_ids",
        "party_levels",
        "party_hp",
        "party_status",
        "party_moves",
        "party_pp",
        "bag_items",
        "badge_bits",
        "player_money",
    ):
        if getattr(after, key) != getattr(before, key):
            raise RuntimeError("hole transition changed protected resources")
    if not any(
        b.sprite_index == 13 and b.at == (16, 23)
        for b in runtime.reader.read_current_strength_boulders()
    ):
        raise RuntimeError("native dropped boulder did not appear on 2F")
    return dict(
        map_id=after.map_id,
        at=(after.player_y, after.player_x),
        authority="existing native-qualified hole support",
        dropped_boulder_verified=True,
        ordinary_wild_escapes=escapes,
    )


def _puzzle_plan(runtime, route, name, contract):
    raw = runtime.reader.read()
    if raw.map_id != contract.map_id or event_flag_is_set(raw.event_flags, contract.event):
        raise StrengthPlanningError("puzzle source is no longer available")
    observer = Gen1TraversalObserver(
        runtime.reader,
        hazard_projector=Gen1TrainerSightProjector(
            route.rom, runtime.reader, full_event_offsets=True
        ),
        capability_projector=lambda r: gen1_field_capabilities(runtime.emulator, r),
    )
    world = observed_puzzle_world(route.route_world, runtime.reader)
    initial = StrengthState.from_observation(
        (raw.player_y, raw.player_x), runtime.reader.read_current_strength_boulders()
    )
    blocked = (runtime.reader.read_current_object_coordinates() - initial.occupied) | frozenset(
        h.at for h in observer.observe().hazards
    )
    forbidden, edges = strength_warp_guards(world.macro_graph, raw.map_id)
    hole = victory_road_boulder_drop(route.rom)
    if raw.map_id == hole.map_id:
        forbidden |= frozenset({hole.at})
    # The native-qualified drop quotes sprite 10; the player cannot enter the
    # hole inside this plan. Its follow transition remains a separate option.
    goal = (
        StrengthGoal(contract.at, boulder_index=10, remove_boulder=True)
        if name == "boulder-drop"
        else StrengthGoal(contract.at)
    )
    plan = plan_strength(
        world.terrain[raw.map_id],
        world.rules,
        initial,
        goal,
        raw,
        blocked=blocked,
        forbidden_player_coordinates=forbidden,
        forbidden_player_edges=edges,
        max_states=100_000,
        push_macros=True,
    )
    return plan, observer


def _puzzle_verified(runtime, name, contract, raw):
    if raw.map_id != contract.map_id or not event_flag_is_set(raw.event_flags, contract.event):
        return False
    if name == "boulder-drop":
        return all(b.sprite_index != 10 for b in runtime.reader.read_current_strength_boulders())
    y, x = contract.changed_block_at
    return runtime.reader.read_current_map_blocks().rows[y][x] == contract.changed_block


def _puzzle_option(runtime, actions, route, name, contract, record, *, objective_ref=OBJECTIVE):
    try:
        plan, observer = _puzzle_plan(runtime, route, name, contract)
    except StrengthPlanningError:
        return None

    def execute():
        port = Gen1FieldMovePort(actions, runtime.reader, runtime.emulator)
        port.execute(MacroAction(MacroActionKind.FIELD_MOVE, "strength:activate"))
        executor = Gen1StrengthExecutor(
            actions,
            runtime.reader,
            runtime.emulator,
            allow_verified_wild_hp_loss=True,
            interruption_handler=Gen1WildFleeHandler(
                port,
                runtime.reader,
                maximum_flees=40,
                stabilization_frames=120,
            ),
            interruption_observer=observer,
        )
        result = executor.execute(plan)
        if not result.passed:
            raise RuntimeError("Strength terminal differs from the selected plan")
        return dict(
            contract=asdict(contract),
            steps=len(plan.steps),
            explored_states=plan.explored_states,
            pushes=len(result.pushes),
            facing_adjustments=sum(p.facing_adjustments for p in result.pushes),
            wild_escapes=len(executor.interruption_receipts),
            verified_wild_hp_loss=sum(
                r.details.get("initial_hp", 0) - r.details.get("final_hp", 0)
                for r in executor.interruption_receipts
            ),
        )

    return _mechanics_option(
        runtime,
        actions,
        phase=name,
        operation=execute,
        valid=lambda raw: _puzzle_verified(runtime, name, contract, raw),
        cost=0.2 + plan.cost / 3000,
        record=record,
        objective_ref=objective_ref,
    )


def _rival_land_before_fly_option(runtime, actions, route, *, world, start, record, objective_ref):
    """A real same-map shore, before re-observing the existing walking-only Fly.

    This is navigation within a selected return. Never project water mode into
    walking, execute a preview flight, or credit the destination before arrival.
    """
    raw = runtime.reader.read()
    town = int(MapId.VIRIDIAN_CITY)
    if (
        getattr(start, "mode", None) != "water" or not start.ready
        or start.interruption is not None
        or not 0 <= raw.map_id <= 0x24 or raw.map_id in {0x0B, town, int(MapId.ROUTE_22)}
        or runtime.reader.read_overworld_movement_mode() is not OverworldMovementMode.SURFING
        or not int(raw.badge_bits or 0) & int(Badge.THUNDER)
        or town not in runtime.reader.read_fly_destinations()
    ):
        return None
    try:
        fly_menu_indices(raw)
    except Gen1FieldMoveError:
        return None
    graph = world.local_graphs.get(raw.map_id)
    if graph is None:
        return None
    shores = {edge.target for edges in graph.edges.values() for edge in edges
              if edge.kind == "water_exit" and edge.required_mode == "water"
              and edge.result_mode == "land"}
    candidates = []
    for at in sorted(shores, key=lambda at: (
        abs(at[0] - start.at[0]) + abs(at[1] - start.at[1]), at,
    ))[:16]:
        try:
            plan = world.plan_feasible_to_map(start, raw.map_id, goal_at=at)
        except RoutePlanningError:
            continue
        if (plan.steps and plan.terminal_mode == "land"
                and all(step.source_map == step.expected_map == raw.map_id
                        for step in plan.steps)):
            candidates.append((plan.cost, at))
    if not candidates:
        return None
    cost, at = min(candidates)

    def land():
        replace(route, route_world=world, destination_map=raw.map_id, destination_at=at)(
            actions, runtime.reader, runtime.emulator,
        )
        return dict(map_id=raw.map_id, at=at, transport="observed_water_exit",
                    navigation_learned=False, flight_executed=False)

    return _mechanics_option(
        runtime, actions, phase="route22-land-before-fly", operation=land,
        valid=lambda r: (r.map_id, r.player_y, r.player_x) == (raw.map_id, *at)
        and runtime.reader.read_overworld_movement_mode() is OverworldMovementMode.WALKING,
        cost=0.2 + cost / 3000, record=record, objective_ref=objective_ref,
    )


def _rival_fly_approach_option(
    runtime, actions, route, *, world, start, walking_plan, record, objective_ref,
    phase="route22-approach-fly",
    landing_town=MapId.VIRIDIAN_CITY,
    onward_destination=MapId.ROUTE_22,
):
    """Shorten the selected approach, never choose or complete its rival battle."""
    raw = runtime.reader.read()
    town = int(landing_town)
    destination = int(onward_destination)
    if (town,destination) not in {
        (int(MapId.VIRIDIAN_CITY),int(MapId.ROUTE_22)),
        (int(MapId.INDIGO_PLATEAU),int(MapId.INDIGO_PLATEAU)),
    }:
        raise ValueError("late-story Fly destination is not declared")
    if (
        not 0 <= raw.map_id <= 0x24
        or raw.map_id in {0x0B, town, destination}
        or not int(raw.badge_bits or 0) & int(Badge.THUNDER)
        or not start.ready or start.interruption is not None or start.mode != "land"
        or runtime.reader.read_overworld_movement_mode() is not OverworldMovementMode.WALKING
        or not runtime.reader.read_input_readiness().ready
        or runtime.reader.read_bottom_dialogue_box_visible()
        or runtime.reader.read_pending_trainer_battle_identity() is not None
        or runtime.reader.read_fly_menu_state() is not None
    ):
        return None
    try:
        fly_menu_indices(raw)
    except Gen1FieldMoveError:
        return None
    if town not in runtime.reader.read_fly_destinations():
        return None
    landing = dict(red_fly_landings(route.rom))[town]
    graph = world.local_graphs.get(town)
    if (graph is None or landing not in graph.edges
            or landing in world.object_blockers[town]):
        return None
    projected = replace(
        start, map_id=town, at=landing, last_outside_map=town, occupied=frozenset(),
    )
    if town == destination:
        onward = None
    else:
        try:
            onward = world.plan_feasible_to_map(projected, destination)
        except RoutePlanningError:
            return None
    # A disclosed navigation quote, not learned value or a win probability.
    # Preserve the shorter existing walk rather than flying from a nearby tile.
    quoted_cost = 40 + (0 if onward is None else onward.cost)
    if walking_plan is not None and quoted_cost >= walking_plan.cost:
        return None

    def fly():
        limited = HardCompositionActionLimiter(
            actions, maximum_actions_per_decision=256, maximum_episode_actions=256,
        )
        port = Gen1FieldMovePort(limited, runtime.reader, runtime.emulator)
        receipt = port.execute(MacroAction(
            MacroActionKind.FIELD_MOVE,
            "fly:" + RED_FLY_TOWN_NAMES[town].lower().replace(" ", "_"),
        ))
        return dict(
            transport="earned_native_fly", navigation_learned=False,
            landing_map=town, landing_at=landing,
            quoted_destination=destination,
            walking_quote=None if walking_plan is None else walking_plan.cost,
            flight_and_onward_quote=quoted_cost,
            flight_receipt=_public(receipt), stopped_at_observed_map_boundary=True,
        )

    return _mechanics_option(
        runtime, actions, phase=phase, operation=fly,
        valid=lambda r: (r.map_id, r.player_y, r.player_x) == (town, *landing),
        cost=0.2 + quoted_cost / 3000, record=record, objective_ref=objective_ref,
    )


def _route_option(
    runtime,
    actions,
    route,
    *,
    world,
    phase,
    destination_map,
    destination_at=None,
    record=None,
    finishes=False,
    objective_ref=OBJECTIVE,
):
    """Quote existing routing and stop on entry before unseen trainer lanes."""
    raw = runtime.reader.read()
    start = Gen1TraversalObserver(
        runtime.reader,
        hazard_projector=Gen1TrainerSightProjector(
            route.rom, runtime.reader, full_event_offsets=True
        ),
        capability_projector=lambda r: gen1_field_capabilities(runtime.emulator, r),
    ).observe()
    if (phase == "route22-return" and destination_map == int(MapId.ROUTE_22)
            and objective_ref in LEAGUE_OBJECTIVES
            and raw.badge_bits == 255
            and int(MapId.INDIGO_PLATEAU) in getattr(
                runtime.reader,"read_fly_destinations",lambda:(),
            )()):
        # Indigo was actually visited. The current League goal remains
        # unfinished; this only returns a selected trip to its earned landing.
        if raw.map_id > 0x24:
            from .red_indoor_departure_plan import bounded_indoor_departure

            departure = bounded_indoor_departure(start,world)
            if departure is not None:
                outside,at = departure.terminal_map,departure.terminal_at

                def depart():
                    replace(route,route_world=world,destination_map=outside,destination_at=at)(
                        actions,runtime.reader,runtime.emulator,
                    )
                    return dict(transport="observed_indoor_departure",map_id=outside,at=at,
                                navigation_learned=False,flight_executed=False)

                return _mechanics_option(
                    runtime,actions,phase="indigo-return-departure",operation=depart,
                    valid=lambda r:(r.map_id,r.player_y,r.player_x)==(outside,*at),
                    cost=0.2+departure.cost/3000,record=record,objective_ref=objective_ref,
                )
        flight = _rival_fly_approach_option(
            runtime,actions,route,world=world,start=start,walking_plan=None,
            record=record,objective_ref=objective_ref,phase="indigo-return-fly",
            landing_town=MapId.INDIGO_PLATEAU,onward_destination=MapId.INDIGO_PLATEAU,
        )
        if flight is not None:
            return flight
    try:
        plan = world.plan_feasible_to_map(
            start,
            destination_map,
            **({"goal_at": destination_at} if destination_at is not None else {}),
        )
    except RoutePlanningError:
        return None
    if (phase in {"route22-approach", "route22-return"}
            and destination_map == int(MapId.ROUTE_22)):
        shore = _rival_land_before_fly_option(
            runtime, actions, route, world=world, start=start,
            record=record, objective_ref=objective_ref,
        )
        if shore is not None:
            return shore
        flight = _rival_fly_approach_option(
            runtime, actions, route, world=world, start=start, walking_plan=plan,
            record=record, objective_ref=objective_ref, phase=phase + "-fly",
        )
        if flight is not None:
            return flight
    target_map, target_at = destination_map, plan.terminal_at
    first = next((s for s in plan.steps if s.expected_map != raw.map_id), None)
    if first is not None:
        target_map, target_at = first.expected_map, first.expected_at
    if (raw.map_id, raw.player_y, raw.player_x) == (target_map, *target_at):
        return None
    completes = objective_ref == OBJECTIVE and finishes and target_map in {
        int(MapId.INDIGO_PLATEAU),
        int(MapId.INDIGO_PLATEAU_LOBBY),
    }

    def travel():
        replace(route, route_world=world, destination_map=target_map, destination_at=target_at)(
            actions,
            runtime.reader,
            runtime.emulator,
        )
        return dict(
            map_id=target_map,
            at=target_at,
            quoted_destination=destination_map,
            qualified_stairs_endpoint=destination_at,
            stopped_at_observed_map_boundary=True,
        )

    return _mechanics_option(
        runtime,
        actions,
        phase=phase,
        operation=travel,
        valid=lambda r: (r.map_id, r.player_y, r.player_x) == (target_map, *target_at),
        cost=0.2 + plan.cost / 3000,
        record=record,
        completes_objective=completes,
        objective_ref=objective_ref,
    )


def _strength_lesson(runtime, rom):
    raw = runtime.reader.read()
    if not dict(raw.bag_items).get(int(ItemId.HM04_STRENGTH)):
        return None
    cartridge = RedPracticeCartridge(rom)
    candidates = []
    for slot, (species, level, hp, moves) in enumerate(
        zip(
            raw.party_species_ids,
            raw.party_levels,
            raw.party_hp,
            raw.party_moves,
            strict=True,
        ),
        1,
    ):
        if hp <= 0 or 70 not in cartridge.species(species).tmhm_moves or 70 in moves:
            continue
        slots = (
            [moves.index(0) + 1]
            if 0 in moves
            else [i for i, move in enumerate(moves, 1) if move not in {15, 19, 57, 70, 148}]
        )
        for move_slot in slots:
            candidates.append((0 if 0 in moves else 1, -level, slot, move_slot))
    if not candidates:
        return None
    _, _, slot, move_slot = min(candidates)
    return plan_machine_lesson(
        rom,
        runtime.reader,
        item_id=int(ItemId.HM04_STRENGTH),
        party_slot=slot,
        replace_slot=move_slot,
    )


def victory_road_story_option(
    runtime, actions, _, *, route, battler, preparation_plan, record=None,
    access_objective_ref=None,
):
    if not _field_ready(runtime):
        return None
    observation = runtime.adapter.observe()
    raw = runtime.reader.read()
    objective_ref = OBJECTIVE if access_objective_ref is None else access_objective_ref
    legal = {o.id for o in runtime.adapter.graph.available_objectives(observation.game_state)}
    if access_objective_ref is not None and (
        objective_ref not in LEAGUE_OBJECTIVES
        or OBJECTIVE not in runtime.adapter.graph.completed_ids(observation.game_state)
        or not event_flag_is_set(raw.event_flags, 1318)
    ):
        return None
    if (
        objective_ref not in legal
        or raw.badge_bits != 255
        or not raw.party_hp
        or not any(raw.party_hp)
        or raw.player_money is None
        or raw.bag_items is None
    ):
        return None
    verify_rom_bytes(route.rom)
    if not event_flag_is_set(raw.event_flags, 1318):
        if raw.map_id == int(MapId.ROUTE_22):
            binding = route22_rival_binding(runtime, actions, route=route, battler=battler)
            if binding is None:
                return None
            contract = route22_rival_contract(route.rom, runtime.reader)
            quote = trainer_party_quote(
                route.rom, contract.trainer_identity[0], contract.trainer_identity[2]
            )
            members = observe_preparation_members(runtime.emulator, preparation_plan)
            return binding, OptionChallenge.from_levels(
                combat_levels=tuple(
                    m.observation.level for m in members if m.purpose is PreparationPurpose.COMBAT
                ),
                opponent_levels=tuple(m.level for m in quote.party),
            )
        # A model-selected preparation excursion can finish at another Center.
        # Reuse the same observed route from that earned endpoint, one map at
        # a time, instead of assuming the party is still in Viridian.
        return _route_option(
            runtime,
            actions,
            route,
            world=route.route_world.with_current_observation(runtime.reader),
            phase="route22-approach",
            destination_map=int(MapId.ROUTE_22),
            record=record,
            objective_ref=objective_ref,
        )
    if raw.map_id == int(MapId.ROUTE_23):
        # After the northern cave exit, prefer actual Indigo feasibility over
        # walking south through the badge corridor again. Before that exit,
        # the closed cave still makes this route unavailable.
        north = _route_option(
            runtime,
            actions,
            route,
            world=observed_puzzle_world(route.route_world, runtime.reader),
            phase="reach-indigo",
            destination_map=int(MapId.INDIGO_PLATEAU),
            record=record,
            finishes=True,
            objective_ref=objective_ref,
        )
        if north is not None:
            return north
    if raw.map_id in CORRIDOR_MAPS and raw.map_id not in CAVE_MAPS:
        # A battle may faint the only Surf holder. Do not advertise an
        # impossible access action and crowd out the real recovery peer.
        try:
            quote_badge_corridor(route.rom, runtime.reader, runtime.emulator)
        except RoutePlanningError:
            return None
        records = []

        def corridor():
            final = traverse_badge_corridor(
                route.rom,
                runtime.reader,
                runtime.emulator,
                actions,
                record=lambda name, value: records.append(dict(name=name, value=_public(value))),
                maximum_flees=40,
                allow_retained_boundary=True,
                allow_party_faints=route.allow_wild_faints,
                allow_field_faint_dialogue=route.allow_field_faint_dialogue,
            )
            return dict(map_id=final.map_id, at=final.at, receipts=records)

        return _mechanics_option(
            runtime,
            actions,
            phase="badge-corridor",
            operation=corridor,
            valid=lambda r: r.map_id == int(MapId.VICTORY_ROAD_1F),
            record=record,
            objective_ref=objective_ref,
        )
    if raw.map_id in CAVE_MAPS and not strength_capabilities(raw):
        lesson = _strength_lesson(runtime, route.rom)
        if lesson is None:
            return None

        def teach():
            execute_machine_lesson(runtime.emulator, actions, runtime.reader, lesson, rom=route.rom)
            return dict(
                lesson=asdict(lesson),
                learned_recipient_selection=False,
                supplied_selection="compatible living holder;prefer empty slot",
            )

        return _mechanics_option(
            runtime,
            actions,
            phase="teach-strength",
            operation=teach,
            valid=lambda r: 70 in r.party_moves[lesson.party_slot - 1],
            record=record,
            objective_ref=objective_ref,
        )
    if raw.map_id in CAVE_MAPS:
        # Preparation can return on the exit side of a floor whose transient
        # switch flags have reset. Prefer a route proven feasible from the
        # actual terrain and boulders, rather than replaying an old puzzle.
        north = _route_option(
            runtime,
            actions,
            route,
            world=observed_puzzle_world(route.route_world, runtime.reader),
            phase="reach-indigo",
            destination_map=int(MapId.INDIGO_PLATEAU),
            record=record,
            finishes=True,
            objective_ref=objective_ref,
        )
        if north is not None:
            return north
        puzzle = next_puzzle(route.rom, raw)
        if puzzle is None:
            return None
        name, contract = puzzle
        if raw.map_id == contract.map_id:
            return _puzzle_option(
                runtime, actions, route, name, contract, record, objective_ref=objective_ref
            )
        if name == "final-switch" and dropped_boulder_follow_available(route.rom, raw):
            return _mechanics_option(
                runtime,
                actions,
                phase="follow-dropped-boulder",
                operation=lambda: follow_dropped_boulder(runtime, actions, route.rom),
                valid=lambda r: (r.map_id, r.player_y, r.player_x) == (contract.map_id, 16, 22),
                record=record,
                objective_ref=objective_ref,
            )
        # Already native-qualified staircase entry coordinates, not a walk
        # string or a strategic preparation schedule. The shared router finds
        # the path, and each new map is re-observed before further movement.
        arrivals = {"second-switch": (8, 0), "third-switch": (7, 23), "final-switch": (14, 25)}
        if name not in arrivals:
            return None
        return _route_option(
            runtime,
            actions,
            route,
            world=observed_puzzle_world(route.route_world, runtime.reader),
            phase="stairs-" + name,
            destination_map=contract.map_id,
            destination_at=arrivals[name],
            record=record,
            objective_ref=objective_ref,
        )
    if raw.map_id not in {
        int(MapId.INDIGO_PLATEAU),
        int(MapId.INDIGO_PLATEAU_LOBBY),
    }:
        # Collection or preparation may leave the earned player elsewhere
        # after the rival is defeated. Keep the unfinished story reachable
        # using the same actual route quote, not a forced return schedule.
        return _route_option(
            runtime,
            actions,
            route,
            world=route.route_world.with_current_observation(runtime.reader),
            phase="route22-return",
            destination_map=int(MapId.ROUTE_22),
            record=record,
            objective_ref=objective_ref,
        )
    return None
