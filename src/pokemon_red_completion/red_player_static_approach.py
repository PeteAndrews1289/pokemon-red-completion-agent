"""Observed map-by-map one-off approach, with existing learned trainer handling."""

from dataclasses import replace
from hashlib import sha256

from .gen1_trainer_parties import trainer_party_quote
from .gen1_trainer_sight import trainer_headers, trainer_sight_zones
from .gen1_traversal import map_object_events
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .player_option_challenge import OptionChallenge
from .observation import MapId, event_flag_is_set
from .red_player_field_goals import _field_ready
from .red_player_story_battle import story_battle_binding
from .red_player_story_obstruction import blocking_story_trainers
from .red_player_tower import _origin
from .red_static_capture import observe_static_capture
from .red_story_battle import StoryTrainerContract
from .red_story_map_frontier import story_frontier_target
from .route_plan import RoutePlanningError


def _static_approach_events_preserved(before, after):
    """Keep story flags exact apart from a proved automatic map-entry effect.

    SilphCo1F's cartridge script, after Giovanni's prior defeat, sets the
    receptionist-at-desk event and shows her once. Walking into the lobby
    triggers it without interaction. This does not activate a static target.
    See pret/pokered scripts/SilphCo1F.asm and constants/event_constants.asm.
    """
    if before.event_flags == after.event_flags:
        return True
    receptionist_event, defeated_giovanni_event = 919, 1935
    if (
        not isinstance(before.event_flags, bytes)
        or not isinstance(after.event_flags, bytes)
        or len(before.event_flags) != len(after.event_flags)
        or len(before.event_flags) * 8 <= defeated_giovanni_event
        or before.map_id == int(MapId.SILPH_CO_1F)
        or after.map_id != int(MapId.SILPH_CO_1F)
        or not event_flag_is_set(before.event_flags, defeated_giovanni_event)
        or event_flag_is_set(before.event_flags, receptionist_event)
    ):
        return False
    expected = bytearray(before.event_flags)
    expected[receptionist_event // 8] |= 1 << (receptionist_event % 8)
    return bytes(expected) == after.event_flags


def static_approach_binding(
    runtime, actions, *, route, target, objective_id, battler, continuous_travel=False,
):
    """Reach an adjacent tile or fight an observed obstruction; never activate target."""
    row = _static_approach_option(runtime, actions, route=route, target=target,
                                 objective_id=objective_id, battler=battler,
                                 continuous_travel=continuous_travel)
    return None if row is None else row[0]


def static_approach_option(
    runtime, actions, *, route, target, objective_id, battler, combat_levels,
    continuous_travel=False,
):
    """Pair the unchanged executor with its real next-component challenge.

    Travel is not combat. An actual obstruction quotes that cartridge trainer,
    not the static Pokémon or an eventual boss beyond the map boundary.
    """
    if (not isinstance(combat_levels, tuple) or not combat_levels
            or any(type(level) is not int or not 1 <= level <= 100 for level in combat_levels)):
        raise ValueError("static approach requires actual combat-role levels")
    return _static_approach_option(runtime, actions, route=route, target=target,
                                  objective_id=objective_id, battler=battler,
                                  combat_levels=combat_levels,
                                  continuous_travel=continuous_travel)


def _static_approach_option(
    runtime, actions, *, route, target, objective_id, battler, combat_levels=None,
    continuous_travel=False,
):
    if type(continuous_travel) is not bool:
        raise TypeError("static approach travel scope must be boolean")
    if not _field_ready(runtime):
        return None
    status = observe_static_capture(runtime.reader, target)
    if status.registered or status.consumed:
        return None
    raw = runtime.reader.read()
    if objective_id not in {
        o.id
        for o in runtime.adapter.graph.available_objectives(runtime.adapter.observe().game_state)
    }:
        return None
    if (
        raw.map_id == target.map_id
        and abs(raw.player_y - target.at[0]) + abs(raw.player_x - target.at[1]) == 1
    ):
        return None
    start = _origin(runtime, route)
    plans = []
    neighbors = tuple(
        (target.at[0] + dy, target.at[1] + dx) for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1))
    )
    for at in neighbors:
        if min(at) < 0:
            continue
        try:
            plans.append(route.route_world.plan_feasible_to_map(start, target.map_id, goal_at=at))
        except RoutePlanningError:
            continue
    complete_target_quoted = bool(plans)
    if not plans and raw.map_id != target.map_id:
        # Future-map NPC occupancy may hide a safe earlier boundary. Quote
        # relevance with the existing preview, then independently plan the
        # executable boundary with original occupancy and trainer hazards.
        try:
            boundary_map, boundary_at = story_frontier_target(
                route.route_world, start, target.map_id
            )
            plans.append(
                route.route_world.plan_feasible_to_map(start, boundary_map, goal_at=boundary_at)
            )
        except RoutePlanningError:
            return None
    if not plans:
        zones = trainer_sight_zones(
            trainer_headers(route.rom, {raw.map_id}, full_event_offsets=True),
            map_object_events(route.rom, {raw.map_id}),
            raw,
            runtime.reader.read_current_map_objects(),
        )
        candidates = tuple(
            candidate
            for at in neighbors
            if min(at) >= 0
            for candidate in blocking_story_trainers(
                route.rom,
                route.route_world,
                start,
                zones,
                target.map_id,
                destination_at=at,
                allow_sequence=True,
            )
        )
        if not candidates:
            return None
        trainer = min(candidates, key=lambda c: c.approach.cost).trainer
        contract = StoryTrainerContract.from_cartridge(
            route.rom,
            raw,
            objective_id=objective_id,
            battle_plan_id="observed-static-approach-obstruction",
            map_id=raw.map_id,
            defeated_event=trainer.event_flag,
        )
        binding = story_battle_binding(
            runtime,
            actions,
            contract=contract,
            route=route,
            battler=battler,
            completes_objective=False,
        )
        if binding is None:
            return None
        challenge = OptionChallenge(True, False, 0., 0., 0.)
        if combat_levels is not None:
            quote = trainer_party_quote(route.rom, trainer.trainer_class, trainer.trainer_set)
            challenge = OptionChallenge.from_levels(
                combat_levels=combat_levels, opponent_levels=tuple(m.level for m in quote.party))
        return binding, challenge
    plan = min(plans, key=lambda p: (p.cost, p.terminal_at))
    # An implicit stair/door transition can have no explicit walking steps.
    # Its macro segment still quotes a real map arrival, so it is useful work.
    if not plan.steps and not plan.segments:
        record = getattr(actions, "record_diagnostic_event", None)
        if callable(record):
            record("static_approach_quote", dict(
                objective=objective_id, source_map=raw.map_id,
                source_at=[raw.player_y, raw.player_x], target_map=target.map_id,
                target_at=list(target.at), quoted_at=list(plan.terminal_at),
                executable=False, reason="no_executable_frontier_steps",
                controller_inputs=0,
            ))
        return None
    # A cartridge path through a future map does not quote its live trainer
    # sight. Stop at the first map boundary so the next menu can expose the
    # existing learned obstruction battle instead of failing mid-relocation.
    # This also covers detours that leave and return to the target's own map.
    # Continuous travel is safe only while all remaining steps are observed on
    # this map; the executor still rechecks moving objects and trainer hazards.
    first = plan.segments[0] if plan.segments else None
    destination = first.target_map if first else raw.map_id
    at = first.transition.arrival_at if first else plan.terminal_at
    source = runtime.emulator.save_state_bytes()
    terminal = None
    used = False

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != source:
            raise ValueError("static approach stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        replace(route, destination_map=destination, destination_at=at)(
            actions, runtime.reader, runtime.emulator
        )
        final = runtime.reader.read()
        if (
            not _field_ready(runtime)
            or final.map_id != destination
            or (final.player_y, final.player_x) != at
            or not _static_approach_events_preserved(raw, final)
            or any(
                getattr(raw, k) != getattr(final, k)
                for k in (
                    "player_money",
                    "bag_items",
                    "party_species_ids",
                    "badge_bits",
                )
            )
        ):
            raise ValueError("static approach endpoint or protected state differs")
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                support="observed_static_approach",
                objective=objective_id,
                objective_completed=False,
                activated=False,
                incidental_map_entry_events=(
                    ["silph_receptionist_returns_to_desk"]
                    if raw.event_flags != final.event_flags else []
                ),
                continuous_travel_requested=continuous_travel,
                complete_target_approach=(
                    continuous_travel and complete_target_quoted and first is None
                ),
                automatic_objectives=[],
            ),
        )

    def verify(report):
        return (
            GoalVerification.succeeded()
            if terminal is not None and runtime.emulator.save_state_bytes() == terminal
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        )

    binding = ExecutableGoalBinding(
        "pokemon.red:static-approach:" + sha256(source).hexdigest(),
        GoalKind.ADVANCE_STORY,
        min(1.0, plan.cost / 3000),
        0.1,
        execute,
        verify,
        story_objective_ref=objective_id,
    )
    return binding, OptionChallenge(False, False, 0., 0., 0.)
