"""Observed Mansion interactions composed with the current story-item actor.

The cartridge-specific statue and floor-drop controls are disclosed mechanics.
They do not choose the story objective, buy supplies, sell items or train a party.
Routes are replanned from the live map; there is no chapter movement string.
"""

from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace

from .actions import MacroActionKind
from .blaine import BlaineChapterError, _pulse
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import Gen1TrainerSightProjector
from .gen1_traversal import cut_capabilities
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import EventFlag, ItemId, MapId, event_flag_is_set
from .player_option_challenge import OptionChallenge
from .red_player_field_goals import _field_ready
from .red_player_field_item import field_item_story_option, settle_story_interaction
from .red_player_lesson import capture_player_lesson_snapshot
from .red_player_story_travel import story_travel_binding
from .rom import verify_rom_bytes
from .route_plan import RoutePlanningError

OBJECTIVE = "obtain_secret_key"
EXIT_OBJECTIVE = "defeat_blaine"
UPPER_STATUE = (int(MapId.POKEMON_MANSION_3F), (6, 10))
SOUTH_STATUE = (int(MapId.POKEMON_MANSION_B1F), (26, 18))
NORTH_STATUE = (int(MapId.POKEMON_MANSION_B1F), (4, 20))
# Exact-revision script coordinates, not an ordinary warp-table entrance.
# Cartridge 3F coordinate table has (14,16),(14,17),(14,19). The first drop
# retains coordinates on1F; its native terminal is always checked, never supplied.
DROP_APPROACH = (13, 16)
DROP_TERMINAL = (14, 16)
MANSION_MAPS = frozenset(
    int(m)
    for m in (
        MapId.POKEMON_MANSION_1F,
        MapId.POKEMON_MANSION_2F,
        MapId.POKEMON_MANSION_3F,
        MapId.POKEMON_MANSION_B1F,
    )
)


def mansion_departure_world(world, cartridge_world, raw):
    """Discard only volatile Mansion projections after the native exit reset.

    A closed first-floor projection retained during a nurse trip must not make
    a later entry permanently inaccessible. Start from the same cartridge
    layout a cold continuation uses; live movement still re-observes every
    room, object and passage. Other maps and all topology/requirements stay.
    """
    if (
        raw.map_id in MANSION_MAPS
        or raw.event_flags is None
        or event_flag_is_set(raw.event_flags, int(EventFlag.MANSION_SWITCH_ON))
    ):
        return world
    return replace(world, **{
        name: {**getattr(world, name), **{
            map_id: getattr(cartridge_world, name)[map_id] for map_id in MANSION_MAPS
        }}
        for name in ("terrain", "local_graphs", "object_blockers")
    })


def _toggle_statue(actions, reader, emulator, *, expected):
    """Settle deferred ordinary encounters before each bounded dialogue input."""
    if event_flag_is_set(reader.read().event_flags, int(EventFlag.MANSION_SWITCH_ON)) == expected:
        raise BlaineChapterError("Mansion statue toggle began in its target state.")
    runtime = SimpleNamespace(reader=reader, emulator=emulator)
    _pulse(actions, MacroActionKind.MOVE, "up", frames=120)
    recoveries = []
    for _ in range(16):
        raw = reader.read()
        if raw.battle_state or not reader.read_bottom_dialogue_box_visible():
            recovery = settle_story_interaction(runtime, actions)
            if recovery is not None:
                recoveries.append(dict(recovery))
        raw = reader.read()
        if raw.battle_state:
            raise BlaineChapterError("Mansion statue retained unsupported battle control.")
        if (
            event_flag_is_set(raw.event_flags, int(EventFlag.MANSION_SWITCH_ON)) == expected
            and _field_ready(runtime)
        ):
            return recoveries
        # Short confirmation plus neutral settlement, not a long Confirm hold
        # spanning the setup of a deferred wild encounter.
        _pulse(actions, MacroActionKind.CONFIRM, frames=30)
        _pulse(actions, MacroActionKind.WAIT, frames=120)
    raise BlaineChapterError("Mansion statue did not toggle to the expected state.")


def mansion_exit_option(runtime, actions, _, *, route):
    """Open an observed blocked return after the key, without completing Blaine."""
    if not _field_ready(runtime):
        return None
    before, lesson = capture_player_lesson_snapshot(runtime)
    raw = before.raw
    if (
        raw.map_id not in {int(MapId.POKEMON_MANSION_B1F), int(MapId.POKEMON_MANSION_1F)}
        or raw.bag_items is None
        or not dict(raw.bag_items).get(int(ItemId.SECRET_KEY), 0)
        or raw.player_money is None
        or not raw.party_hp
        or not any(raw.party_hp)
        or EXIT_OBJECTIVE
        not in {o.id for o in runtime.adapter.graph.available_objectives(before.game_state)}
    ):
        return None
    verify_rom_bytes(route.rom)
    switch = event_flag_is_set(raw.event_flags, int(EventFlag.MANSION_SWITCH_ON))
    if raw.map_id == int(MapId.POKEMON_MANSION_B1F):
        # Observe the first floor before quoting its switch-dependent exits.
        travel = story_travel_binding(
            runtime,
            actions,
            objective_id=EXIT_OBJECTIVE,
            route=route,
            intermediate_map=int(MapId.POKEMON_MANSION_1F),
        )
        if travel is not None:
            return travel, OptionChallenge(False, False, 0.0, 0.0, 0.0)
    elif switch:
        return None  # Open first-floor exits belong to ordinary routing.
    target_map, at = NORTH_STATUE if switch else SOUTH_STATUE
    return _mansion_interaction_option(
        runtime,
        actions,
        route=route,
        before=before,
        lesson=lesson,
        switch=switch,
        drop=False,
        target_map=target_map,
        at=at,
        objective=EXIT_OBJECTIVE,
    )


def mansion_secret_key_option(runtime, actions, _, *, route):
    """Prefer a real reachable key; otherwise expose the observed puzzle step."""
    # The observed third floor owns its statue/drop phase. A cold route quote
    # through an unobserved first-floor door is not an alternative completed
    # passage and must not send the player back down the wrong staircase.
    ordinary = (
        None if runtime.reader.read().map_id == int(MapId.POKEMON_MANSION_3F)
        else field_item_story_option(
            runtime, actions, route=route, objective_id=OBJECTIVE, item_id=int(ItemId.SECRET_KEY)
        )
    )
    if ordinary is not None:
        return ordinary
    if not _field_ready(runtime):
        return None
    before, lesson = capture_player_lesson_snapshot(runtime)
    raw = before.raw
    if (
        raw.map_id not in MANSION_MAPS
        or raw.bag_items is None
        or len(raw.bag_items) >= 20
        or dict(raw.bag_items).get(int(ItemId.SECRET_KEY), 0)
        or raw.player_money is None
        or not raw.party_hp
        or not any(raw.party_hp)
        or OBJECTIVE
        not in {o.id for o in runtime.adapter.graph.available_objectives(before.game_state)}
    ):
        return None
    verify_rom_bytes(route.rom)
    switch = event_flag_is_set(raw.event_flags, int(EventFlag.MANSION_SWITCH_ON))
    drop = raw.map_id == int(MapId.POKEMON_MANSION_3F) and switch
    target_map, at = (
        (int(MapId.POKEMON_MANSION_3F), DROP_APPROACH)
        if drop
        else (
            (SOUTH_STATUE if switch else NORTH_STATUE)
            if raw.map_id == int(MapId.POKEMON_MANSION_B1F)
            else UPPER_STATUE
        )
    )
    return _mansion_interaction_option(
        runtime,
        actions,
        route=route,
        before=before,
        lesson=lesson,
        switch=switch,
        drop=drop,
        target_map=target_map,
        at=at,
        objective=OBJECTIVE,
    )


def mansion_restoration_binding(runtime, actions, *, route):
    """Honor a selected heal through the observed switch-dependent departure.

    The southern basement statue opens the first-floor return from the drop
    wing. This is an exit mechanic, not a request to collect the key or choose
    healing. Generic routing remains responsible for an already open departure.
    """
    from .red_goal_skills import _raw_party_fully_restored
    from .red_player_field_goals import routed_restoration_binding

    if not _field_ready(runtime):
        return None
    before, lesson = capture_player_lesson_snapshot(runtime)
    raw = before.raw
    if (
        raw.map_id not in {int(MapId.POKEMON_MANSION_1F), int(MapId.POKEMON_MANSION_B1F)}
        or _raw_party_fully_restored(raw)
        or not raw.party_hp
        or not any(raw.party_hp)
        or raw.bag_items is None
        or raw.player_money is None
        or raw.event_flags is None
        or event_flag_is_set(raw.event_flags, int(EventFlag.MANSION_SWITCH_ON))
    ):
        return None
    verify_rom_bytes(route.rom)
    phase = _mansion_interaction_option(
        runtime, actions, route=route, before=before, lesson=lesson,
        switch=False, drop=False, target_map=SOUTH_STATUE[0], at=SOUTH_STATUE[1],
        objective=None, kind=GoalKind.RESTORE_TEAM,
    )
    if phase is None:
        return None
    puzzle, _ = phase
    source = runtime.emulator.save_state_bytes()
    used, child, child_report = False, None, None

    def execute():
        nonlocal used, child, child_report
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("Mansion restoration is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        puzzle_report = puzzle.execute()
        if puzzle.verify(puzzle_report).status.value != "succeeded":
            raise RuntimeError("Mansion restoration departure switch did not verify")
        live_route = replace(
            route, route_world=route.route_world.with_current_observation(runtime.reader)
        )
        # First-floor doors are projected from that floor's live observation.
        # Do not quote a complete Center path through an unobserved locked wing.
        origin = Gen1TraversalObserver(
            runtime.reader, capability_projector=cut_capabilities,
            hazard_projector=Gen1TrainerSightProjector(
                route.rom, runtime.reader, full_event_offsets=True
            ),
        ).observe()
        boundary = live_route.route_world.plan_feasible_to_map(
            origin, int(MapId.POKEMON_MANSION_1F)
        )
        departure = runtime.reader.read()
        replace(live_route, destination_map=int(MapId.POKEMON_MANSION_1F),
                destination_at=boundary.terminal_at)(actions, runtime.reader, runtime.emulator)
        arrival = runtime.reader.read()
        if (
            not _field_ready(runtime)
            or arrival.map_id != int(MapId.POKEMON_MANSION_1F)
            or (arrival.player_y, arrival.player_x) != boundary.terminal_at
            or any(getattr(arrival, name) != getattr(departure, name) for name in (
                "bag_items", "player_money", "event_flags", "badge_bits", "party_species_ids",
                "party_levels", "party_moves", "party_pp",
            ))
        ):
            raise RuntimeError("Mansion restoration first-floor boundary differs")
        live_route = replace(
            route, route_world=route.route_world.with_current_observation(runtime.reader)
        )
        child = routed_restoration_binding(
            runtime, actions, home_map=int(MapId.CINNABAR_POKECENTER), route=live_route,
            observe_trainer_hazards=True, allow_blackout_return=True,
        )
        if child is None:
            raise RuntimeError("Mansion departure has no verified Cinnabar nurse route")
        child_report = child.execute()
        return GoalExecutionReport(
            actions.actions_executed - a, runtime.emulator.frame_count - f,
            dict(support="observed_mansion_departure_then_center", learned_puzzle=False,
                 departure=dict(puzzle_report.evidence), restoration=dict(child_report.evidence),
                 objective_completed=False, purchases=0, sales=0),
        )

    def verify(_):
        if not used or child is None or child_report is None:
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return child.verify(child_report)

    return ExecutableGoalBinding(
        "pokemon.red:mansion-center:" + sha256(source).hexdigest(),
        GoalKind.RESTORE_TEAM, min(1.0, puzzle.estimated_effort + 0.05), puzzle.estimated_risk,
        execute, verify, maximum_cash_debit=0,
    )


def _mansion_interaction_option(
    runtime, actions, *, route, before, lesson, switch, drop, target_map, at, objective,
    kind=GoalKind.ADVANCE_STORY,
):
    raw = before.raw
    world = route.route_world.with_current_observation(runtime.reader)
    route = replace(route, route_world=world)
    start = Gen1TraversalObserver(
        runtime.reader,
        capability_projector=cut_capabilities,
        hazard_projector=Gen1TrainerSightProjector(
            route.rom, runtime.reader, full_event_offsets=True
        ),
    ).observe()
    try:
        plan = world.plan_feasible_to_map(start, target_map, goal_at=at)
    except RoutePlanningError:
        return None
    source = runtime.emulator.save_state_bytes()
    used, terminal = False, None

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("Mansion interaction is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        reader, em = runtime.reader, runtime.emulator
        boxes, dex, pc = (
            reader.read_all_box_states(),
            reader.read_pokedex_state(),
            reader.read_pc_items(),
        )
        replace(route, destination_map=target_map, destination_at=at)(actions, reader, em)
        pending_wild = settle_story_interaction(runtime, actions)
        current = reader.read()
        if (
            not _field_ready(runtime)
            or current.map_id != target_map
            or (current.player_y, current.player_x) != at
            or event_flag_is_set(current.event_flags, int(EventFlag.MANSION_SWITCH_ON)) != switch
        ):
            raise RuntimeError("Mansion interaction approach or switch changed")
        if drop:
            _pulse(actions, MacroActionKind.MOVE, "down", frames=120)
            for _ in range(32):
                current = reader.read()
                if current.battle_state:
                    from .surge import flee_wild

                    if current.battle_state != 1 or current.map_id != int(MapId.POKEMON_MANSION_1F):
                        raise RuntimeError("Mansion drop triggered an unexpected battle")
                    flee_wild(
                        actions,
                        reader,
                        current,
                        expected_map_id=int(MapId.POKEMON_MANSION_1F),
                        route_name="observed Mansion floor drop",
                        stabilization_frames=120,
                        error_type=RuntimeError,
                    )
                if _field_ready(runtime):
                    break
                _pulse(actions, MacroActionKind.WAIT, frames=120)
            current = reader.read()
            if (
                not _field_ready(runtime)
                or current.map_id != int(MapId.POKEMON_MANSION_1F)
                or (current.player_y, current.player_x) != DROP_TERMINAL
            ):
                raise RuntimeError("Mansion floor drop native terminal differs")
        else:
            statue_wild_recovery = _toggle_statue(actions, reader, em, expected=not switch)
        after = reader.read()
        for name in (
            "bag_items",
            "player_money",
            "badge_bits",
            "party_species_ids",
            "party_levels",
            "party_moves",
            "party_pp",
        ):
            if getattr(after, name) != getattr(raw, name):
                raise RuntimeError("Mansion puzzle changed protected " + name)
        if (
            reader.read_all_box_states() != boxes
            or reader.read_pc_items() != pc
            or reader.read_pokedex_state().owned_species != dex.owned_species
            or event_flag_is_set(after.event_flags, int(EventFlag.MANSION_SWITCH_ON))
            != (switch if drop else not switch)
            or not _field_ready(runtime)
        ):
            raise RuntimeError("Mansion puzzle resources or native switch differ")
        terminal = em.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            em.frame_count - f,
            dict(
                support="observed_mansion_floor_drop" if drop else "observed_mansion_statue",
                objective=objective,
                objective_completed=False,
                learned_puzzle=False,
                switch_before=switch,
                switch_after=switch if drop else not switch,
                map_id=after.map_id,
                at=[after.player_y, after.player_x],
                purchases=0,
                sales=0,
                trainer_battles=0,
                automatic_objectives=[],
                pending_wild_recovery=pending_wild,
                statue_wild_recovery=None if drop else statue_wild_recovery,
            ),
        )

    def verify(report):
        after, snapshot = capture_player_lesson_snapshot(runtime)
        passed = (
            terminal is not None
            and runtime.emulator.save_state_bytes() == terminal
            and _field_ready(runtime)
            and set(lesson["completed_objectives"]) == set(snapshot["completed_objectives"])
            and event_flag_is_set(after.raw.event_flags, int(EventFlag.MANSION_SWITCH_ON))
            == (switch if drop else not switch)
        )
        return (
            GoalVerification.succeeded()
            if passed
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    return (
        ExecutableGoalBinding(
            "pokemon.red:mansion-interaction:" + sha256(source).hexdigest(),
            kind,
            min(1.0, plan.cost / 3000),
            0.15,
            execute,
            verify,
            story_objective_ref=objective,
        ),
        OptionChallenge(False, False, 0.0, 0.0, 0.0),
    )
