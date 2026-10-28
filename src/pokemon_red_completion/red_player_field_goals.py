"""Resume existing mechanics from a feasible field boundary, not a chapter replay.

Destinations stay adapter-private. Every selected route re-observes arrival;
there is no synthetic destination state, teacher battle fallback or save editing.
"""

from dataclasses import replace
from hashlib import sha256

from .actions import MacroAction, MacroActionKind
from .gen1_acquisition import map_objects
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import Gen1TrainerSightProjector
from .gen1_traversal import cut_capabilities
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from .observation import ItemId, MapId, semantic_facts
from .party_preparation import next_preparation_decision
from .play import (
    DEFAULT_QUALIFIED_PLAY_TIMING,
    QualifiedPlayError,
    _receive_parcel,
    _receive_pokedex,
)
from .provenance import canonical_sha256
from .red_blackout_recovery import settle_red_blackout
from .red_goal_skills import (
    _POKEMON_CENTER_MAPS,
    RedCenterRestoreGoalProvider,
    RedControlRecoveryGoalProvider,
    _raw_party_fully_restored,
)
from .red_party_preparation import observe_preparation_members, preparation_trainee
from .red_player_cash_exposure import certified_cash_safe_transition
from .red_player_lesson import capture_player_lesson_snapshot
from .red_player_preparation_binding import preparation_binding, preparation_estimated_effort
from .red_training_ground_route import ground_route_capability_projector
from .route import COMPLETION_QUEST
from .route_executor import RouteExecutionError, RouteExecutionFailureReason
from .route_plan import RoutePlanningError
from .team_training import TeamTrainingDirective


def _field_ready(runtime):
    raw = runtime.reader.read()
    return bool(
        raw.game_started
        and raw.battle_state == 0
        and runtime.reader.read_input_readiness().ready
        and not getattr(runtime.reader, "read_overworld_start_menu_visible", lambda: False)()
        and not runtime.reader.read_bottom_dialogue_box_visible()
        and not runtime.emulator.pressed_buttons
    )


def nearest_reachable_player_center(runtime, *, route, centers, include_indigo_lobby=False):
    """Read-only minimum-cost healing destination within an explicit inventory.

    Trainer sight remains reserved. This support planner does not select healing
    instead of another goal, or promise safe travel for an arbitrarily weak party.
    """
    if type(include_indigo_lobby) is not bool:
        raise TypeError("Indigo recovery opt-in must be boolean")
    supported = (_POKEMON_CENTER_MAPS | {int(MapId.INDIGO_PLATEAU_LOBBY)}
                 if include_indigo_lobby else _POKEMON_CENTER_MAPS)
    if (
        not isinstance(centers, frozenset)
        or not centers
        or not centers <= supported
        or any(type(m) is not int for m in centers)
    ):
        raise ValueError("declared supported Center inventory required")
    if not _field_ready(runtime):
        return None
    from .gen1_regional_access import observed_cave_guard_world

    base_world = route.route_world
    observed_world = observed_cave_guard_world(base_world, runtime.reader)
    if observed_world is not base_world:
        route = replace(route, route_world=observed_world)
    start = Gen1TraversalObserver(
        runtime.reader,
        capability_projector=ground_route_capability_projector(route, runtime.emulator),
        hazard_projector=Gen1TrainerSightProjector(
            route.rom, runtime.reader, full_event_offsets=True
        ),
    ).observe()
    reachable = []
    for center in sorted(centers):
        at = (7, 7) if center == MapId.INDIGO_PLATEAU_LOBBY else (3, 3)
        try:
            plan = route.route_world.plan_feasible_to_map(start, center, goal_at=at)
        except RoutePlanningError:
            continue
        reachable.append((plan.cost, center))
    return min(reachable)[1] if reachable else None


def enumerate_routed_player_goals(
    runtime,
    actions,
    observation,
    *,
    home_map,
    route,
    preparation=None,
    include_parcel=False,
    enumerate_base=None,
):
    """Compose existing field capabilities without silently removing alternatives.

    The caller prospectively declares a preparation configuration, if any.
    None means no additional training capability, not an already-met target
    disguised as a new training goal. Observation never chooses a goal or inputs.
    An optional base enumerator can supply the existing routed resource inventory;
    it receives the same runtime, guarded action port and fresh observation.
    """
    if type(include_parcel) is not bool:
        raise ValueError("parcel capability requires an explicit boolean")
    if enumerate_base is not None and not callable(enumerate_base):
        raise TypeError("base inventory enumerator must be callable")
    ordinary = (
        runtime.enumerator(actions).enumerate(observation)
        if enumerate_base is None
        else enumerate_base(runtime, actions, observation)
    )
    preparation_binding = (
        None
        if preparation is None
        else routed_preparation_binding(
            runtime, actions, home_map=home_map, route=route, **preparation
        )
    )
    restoration = routed_restoration_binding(runtime, actions, home_map=home_map, route=route)
    story = parcel_story_binding(runtime, actions, route=route) if include_parcel else None
    additions = {
        binding.kind: binding
        for binding in (preparation_binding, restoration, story)
        if binding is not None
    }
    if not set(additions) <= {opportunity.kind for opportunity in ordinary.opportunities}:
        raise ValueError("routed player capability is outside the declared goal inventory")
    if any(sum(o.kind is kind for o in ordinary.opportunities) != 1 for kind in additions):
        raise ValueError("routed player replacement has ambiguous existing alternatives")
    return GoalBindingSet(
        tuple(
            additions[o.kind].opportunity if o.kind in additions else o
            for o in ordinary.opportunities
        ),
        tuple(b for b in ordinary.bindings if b.kind not in additions) + tuple(additions.values()),
        allow_resource_variants=ordinary.allow_resource_variants,
    )


def restoration_progress_preserved(runtime, before, after, raw):
    """Healing may discover its native location, never complete unrelated quests."""
    old, new = set(before["completed_objectives"]), set(after["completed_objectives"])
    if (
        before["objective_catalog"] != after["objective_catalog"]
        or not old <= new
        or not new <= set(after["objective_catalog"])
    ):
        return False
    if new == old:
        return True
    facts = semantic_facts(raw)
    for objective_id in new - old:
        required = runtime.adapter.graph.objective(objective_id).completion_facts
        if (
            not required
            or not all(f.startswith("location:") for f in required)
            or not required <= facts
        ):
            return False
    return True


def routed_restoration_binding(
    runtime,
    actions,
    *,
    home_map,
    route,
    allow_blackout_return=False,
    include_indigo_lobby=False,
    observe_trainer_hazards=False,
    alternate_centers=frozenset(),
    require_indigo_checkpoint=False,
):
    """Reach one declared supported Center and verify genuine whole-party healing.

    Opt-in sight-aware quotation agrees with the live Center selector. It masks
    a currently blocked route, not future unseen trainers or a guaranteed return.
    """
    if type(allow_blackout_return) is not bool:
        raise TypeError("explicit restoration blackout scope required")
    if type(include_indigo_lobby) is not bool:
        raise TypeError("Indigo recovery opt-in must be boolean")
    if type(observe_trainer_hazards) is not bool:
        raise TypeError("restoration trainer observation must be an explicit boolean")
    if type(require_indigo_checkpoint) is not bool:
        raise TypeError("Indigo restoration checkpoint must be an explicit boolean")
    if (type(alternate_centers) is not frozenset
            or any(type(m) is not int for m in alternate_centers)
            or not alternate_centers <= _POKEMON_CENTER_MAPS):
        raise ValueError("restoration alternatives require declared ordinary Centers")
    indigo = include_indigo_lobby and home_map == MapId.INDIGO_PLATEAU_LOBBY
    if require_indigo_checkpoint and (not indigo or alternate_centers):
        raise ValueError("Indigo checkpoint requires its exact lobby without alternate Centers")
    nurse_at = (7, 7) if indigo else (3, 3)
    if home_map not in _POKEMON_CENTER_MAPS and not indigo:
        raise ValueError("routed restoration requires a supported Center")
    if not _field_ready(runtime):
        return None
    before, lesson = capture_player_lesson_snapshot(runtime)
    raw = before.raw
    if (
        _raw_party_fully_restored(raw) and not (
            require_indigo_checkpoint
            and runtime.reader.read_last_blackout_map() != int(MapId.INDIGO_PLATEAU)
        )
        or not raw.party_hp
        or not any(raw.party_hp)
        or raw.player_money is None
        or raw.bag_items is None
    ):
        return None
    if (
        raw.map_id == MapId.OAKS_LAB
        and not runtime.reader.read_oaks_errand_state(raw).battled_rival
    ):
        return None
    from .gen1_regional_access import observed_cave_guard_world

    base_world = route.route_world
    observed_world = observed_cave_guard_world(base_world, runtime.reader)
    if observed_world is not base_world:
        route = replace(route, route_world=observed_world)
    origin = Gen1TraversalObserver(
        runtime.reader,
        capability_projector=ground_route_capability_projector(route, runtime.emulator),
        **(
            {
                "hazard_projector": Gen1TrainerSightProjector(
                    route.rom,
                    runtime.reader,
                    full_event_offsets=True,
                )
            }
            if observe_trainer_hazards
            else {}
        ),
    ).observe()
    try:
        travel = route.route_world.plan_feasible_to_map(origin, home_map, goal_at=nurse_at)
    except RoutePlanningError:
        return None
    cash_route = certified_cash_safe_transition(route, raw, travel)
    poison_exposed = bool(
        allow_blackout_return
        and raw.party_status is not None
        and any(status & 8 for status in raw.party_status)
    )
    blackout_home = runtime.reader.read_last_blackout_map() if poison_exposed else None
    state = runtime.emulator.save_state_bytes()
    used, child, child_report = False, None, None
    actual_home, alternate_evidence = home_map, None
    restored_during_travel = False
    blackout_terminal, blackout_report = None, None

    def identities(document):
        return sorted(
            (
                m["specimen_ref"],
                m["species_id"],
                m["level"],
                m["experience"],
                tuple(move[0] for move in m["moves"]),
            )
            for m in document["party"]
        )

    def execute():
        nonlocal \
            used, \
            child, \
            child_report, \
            restored_during_travel, \
            blackout_terminal, \
            blackout_report, \
            actual_home, \
            alternate_evidence
        if used or runtime.emulator.save_state_bytes() != state or not _field_ready(runtime):
            raise ValueError("routed restoration is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        if travel.steps:
            try:
                replace(cash_route or route, destination_map=home_map, destination_at=nurse_at)(
                    actions, runtime.reader, runtime.emulator
                )
            except RouteExecutionError as error:
                after, terminal = capture_player_lesson_snapshot(runtime)
                if (
                    alternate_centers
                    and error.reason is RouteExecutionFailureReason.PLANNER_NO_ROUTE
                    and _field_ready(runtime)
                    and after.raw.map_id != raw.map_id
                    and raw.player_money == after.raw.player_money
                    and raw.bag_items == after.raw.bag_items
                    and lesson["party"] == terminal["party"]
                    and restoration_progress_preserved(runtime, lesson, terminal, after.raw)
                ):
                    alternative = nearest_reachable_player_center(
                        runtime, route=route, centers=alternate_centers - {home_map}
                    ) if alternate_centers - {home_map} else None
                    if alternative is None:
                        raise
                    alternate_evidence = dict(
                        original_center=home_map, actual_center=alternative,
                        original_error_type=type(error).__name__, original_error=str(error),
                        original_reason=error.reason.value,
                        boundary_sha256=sha256(runtime.emulator.save_state_bytes()).hexdigest(),
                        model_goal_queries=0, goal_kind_unchanged=True,
                        support="replan_selected_healing_to_declared_center",
                    )
                    actual_home = alternative
                    replace(route, destination_map=actual_home, destination_at=nurse_at)(
                        actions, runtime.reader, runtime.emulator
                    )
                else:
                    # A poison blackout is a paid failed trip, not nurse success or
                    # permission to forgive an arbitrary world-state divergence.
                    after, terminal = capture_player_lesson_snapshot(runtime)
                    # The route's partial-faint handler deliberately rejects an
                    # all-party blackout. Settle only that observed native loss,
                    # then apply the same strict paid-trip verifier below.
                    pending_blackout = bool(
                        poison_exposed
                        and error.reason is RouteExecutionFailureReason.WORLD_STATE_DIVERGED
                        and after.raw.battle_state == 0
                        and after.raw.party_hp
                        and not any(after.raw.party_hp)
                        and after.raw.player_money == raw.player_money
                        and not runtime.reader.read_input_readiness().ready
                        and runtime.reader.read_bottom_dialogue_box_visible()
                        and not runtime.emulator.pressed_buttons
                        and actions.actions_executed > a
                        and runtime.emulator.frame_count > f
                        and identities(lesson) == identities(terminal)
                        and lesson["completed_objectives"] == terminal["completed_objectives"]
                        and lesson["objective_catalog"] == terminal["objective_catalog"]
                        and all(getattr(after.raw, key) == getattr(raw, key) for key in (
                            "bag_items", "party_count", "party_species_ids", "party_moves",
                            "party_levels", "badge_bits", "event_flags",
                        ))
                    )
                    if pending_blackout:
                        # The cartridge may still be on an intermediate warp map.
                        # Its normal settlement must reach the recorded blackout
                        # home; only that final map is accepted below.
                        settle_red_blackout(
                            actions, runtime.reader, runtime.emulator, allow_field_loss=True
                        )
                        after, terminal = capture_player_lesson_snapshot(runtime)
                    if (
                        not poison_exposed
                        or error.reason is not RouteExecutionFailureReason.WORLD_STATE_DIVERGED
                        or not _field_ready(runtime)
                        or after.raw.map_id != blackout_home
                        or not _raw_party_fully_restored(after.raw)
                        or after.raw.player_money != raw.player_money // 2
                        or after.raw.bag_items != raw.bag_items
                        or any(
                            getattr(after.raw, key) != getattr(raw, key)
                            for key in (
                                "party_count",
                                "party_species_ids",
                                "party_moves",
                                "party_levels",
                                "badge_bits",
                                "event_flags",
                            )
                        )
                        or identities(lesson) != identities(terminal)
                        or lesson["completed_objectives"] != terminal["completed_objectives"]
                        or lesson["objective_catalog"] != terminal["objective_catalog"]
                        or actions.actions_executed <= a
                        or runtime.emulator.frame_count <= f
                        or runtime.emulator.save_state_bytes() == state
                    ):
                        raise
                    blackout_terminal = runtime.emulator.save_state_bytes()
                    blackout_report = GoalExecutionReport(
                        actions.actions_executed - a,
                        runtime.emulator.frame_count - f,
                        dict(
                            mechanic="routed_restoration",
                            model_queries=0,
                            native_blackout_during_selected_restoration=dict(
                                blackout_verified=True,
                                cash_before=raw.player_money,
                                cash_after=after.raw.player_money,
                                cash_lost=raw.player_money - after.raw.player_money,
                                destination_map=blackout_home,
                                learned_recovery=False,
                                nurse_interaction=False,
                                original_route_failure=error.reason.value,
                                pending_dialogue_settled=pending_blackout,
                            ),
                        ),
                    )
                    return blackout_report
        arrival = runtime.reader.read()
        if (
            not _field_ready(runtime)
            or arrival.map_id != actual_home
            or (arrival.player_y, arrival.player_x) != nurse_at
        ):
            raise RuntimeError("routed restoration destination differs")
        if _raw_party_fully_restored(arrival) and not (
            require_indigo_checkpoint
            and runtime.reader.read_last_blackout_map() != int(MapId.INDIGO_PLATEAU)
        ):
            restored_during_travel = True
            return GoalExecutionReport(
                actions.actions_executed - a,
                runtime.emulator.frame_count - f,
                dict(
                    mechanic="routed_restoration",
                    model_queries=0,
                    navigation="cartridge_route_with_existing_flee_support",
                    alternate_center_replan=alternate_evidence,
                    restoration=dict(
                        method="observed_native_restoration_during_travel", nurse_interaction=False
                    ),
                ),
            )
        offer = RedCenterRestoreGoalProvider(
            actions,
            runtime.reader,
            runtime.emulator,
            runtime.adapter,
            require_full_pp_restore=True,
            **({"include_indigo_lobby": True} if indigo else {}),
            **({"require_indigo_checkpoint": True} if require_indigo_checkpoint else {}),
        ).offer(runtime.adapter.observe())
        child = offer.binding
        if child is None:
            raise RuntimeError("routed restoration nurse unavailable")
        child_report = child.execute()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                mechanic="routed_restoration",
                model_queries=0,
                navigation="cartridge_route_with_existing_flee_support",
                alternate_center_replan=alternate_evidence,
                restoration=dict(child_report.evidence),
            ),
        )

    def verify(report):
        if blackout_terminal is not None:
            if (
                report != blackout_report
                or runtime.emulator.save_state_bytes() != blackout_terminal
                or not _field_ready(runtime)
            ):
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            return GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
        after, terminal = capture_player_lesson_snapshot(runtime)
        if (
            not used
            or (
                not restored_during_travel
                and (
                    child is None
                    or child_report is None
                    or child.verify(child_report).status.value != "succeeded"
                )
            )
            or report.actions_executed <= 0
            or not _field_ready(runtime)
            or after.raw.map_id != actual_home
            or (after.raw.player_y, after.raw.player_x) != nurse_at
            or not _raw_party_fully_restored(after.raw)
            or require_indigo_checkpoint
            and runtime.reader.read_last_blackout_map() != int(MapId.INDIGO_PLATEAU)
            or identities(lesson) != identities(terminal)
            or not restoration_progress_preserved(runtime, lesson, terminal, after.raw)
            or after.raw.player_money != raw.player_money
            or after.raw.bag_items != raw.bag_items
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding(
        "pokemon.red:routed-restoration:"
        + canonical_sha256(dict(home=home_map, source=sha256(state).hexdigest(),
            **({"require_indigo_checkpoint": True} if require_indigo_checkpoint else {}),
            **({"alternate_centers": sorted(alternate_centers)} if alternate_centers else {}))),
        GoalKind.RESTORE_TEAM,
        min(1.0, (travel.cost + 40) / 3000),
        0.25,
        execute,
        verify,
        # Already at the nurse means no walking/poison travel exposure. Keep
        # the exact cash verifier; do not certify an injured nonempty route.
        maximum_cash_debit=(
            0 if not travel.steps or (cash_route is not None and not poison_exposed) else None
        ),
    )


def routed_preparation_binding(
    runtime,
    actions,
    *,
    home_map,
    route,
    include_indigo_lobby=False,
    **kwargs,
):
    """Route to a declared supported home, then freshly bind the existing dose."""
    battles, recoveries = kwargs.get("maximum_battles", 3), kwargs.get("maximum_recoveries", 0)
    if type(battles) is not int or not 1 <= battles <= 128:
        raise ValueError("preparation battle allowance must be1..128")
    if type(recoveries) is not int or not 0 <= recoveries <= 127:
        raise ValueError("preparation recovery allowance must be0..127")
    if type(include_indigo_lobby) is not bool:
        raise TypeError("Indigo preparation opt-in must be boolean")
    restore_completed_target = kwargs.get("restore_completed_target", False)
    if type(restore_completed_target) is not bool:
        raise ValueError("completed preparation restoration must be explicit boolean")
    restore_exhausted_partial = kwargs.get("restore_exhausted_partial", False)
    if type(restore_exhausted_partial) is not bool:
        raise ValueError("partial preparation restoration must be explicit boolean")
    if (restore_completed_target or restore_exhausted_partial) and not callable(
        getattr(actions, "execute_restoration", None)
    ):
        raise ValueError("preparation recovery requires the shared metered restoration port")
    indigo = include_indigo_lobby and home_map == MapId.INDIGO_PLATEAU_LOBBY
    nurse_at = (7, 7) if indigo else (3, 3)
    if home_map not in _POKEMON_CENTER_MAPS and not indigo:
        raise ValueError("routed preparation requires a supported Center")
    if indigo:
        kwargs = dict(kwargs, include_indigo_lobby=True)
    if kwargs["battler"].session is not runtime.emulator:
        raise ValueError("routed preparation bypasses the guarded controller")
    if not _field_ready(runtime):
        return None
    raw = runtime.reader.read()
    healthy = _raw_party_fully_restored(raw)
    # A worn party already inside its declared Center may approach the nurse.
    # This never authorizes injured cross-map travel or a different home.
    at_home = raw.map_id == home_map
    if not healthy and not at_home:
        return None
    if (
        raw.map_id == MapId.OAKS_LAB
        and not runtime.reader.read_oaks_errand_state(raw).battled_rival
    ):
        # A geometric exit route cannot replace the mandatory opening battle.
        # Its native story executor, not this field-travel binding, owns that event.
        return None
    try:
        members = observe_preparation_members(runtime.emulator, kwargs["plan"])
        if healthy:
            preparation_trainee(kwargs["plan"], members)
        elif next_preparation_decision(kwargs["plan"], members).directive not in {
            TeamTrainingDirective.TRAIN_MEMBER,
            TeamTrainingDirective.SWITCH_TRAINEE,
            TeamTrainingDirective.RESTORE_TEAM,
        }:
            return None
    except ValueError:
        return None
    start = Gen1TraversalObserver(
        runtime.reader,
        capability_projector=ground_route_capability_projector(route, runtime.emulator),
    ).observe()
    try:
        travel = route.route_world.plan_feasible_to_map(start, home_map, goal_at=nurse_at)
    except RoutePlanningError:
        return None
    if not travel.steps and healthy:
        return preparation_binding(runtime, actions, route=route, **kwargs)
    # Quote the same child venue leg from a typed geometric terminal. This is
    # not a destination observation or an executable child bound before arrival.
    from .red_living_dex_provider_plan import red_living_dex_route_terminal_snapshot

    home = red_living_dex_route_terminal_snapshot(route.route_world, start, travel)
    corridor = kwargs["corridor"]
    try:
        child_travel = route.route_world.plan_feasible_to_map(
            home, corridor.map_id, goal_at=corridor.origin_at
        )
    except RoutePlanningError:
        return None
    effort = preparation_estimated_effort(
        child_travel.cost, battles, approach_cost=travel.cost
    )
    state = runtime.emulator.save_state_bytes()
    used, child, child_report = False, None, None

    def execute():
        nonlocal used, child, child_report
        if used or runtime.emulator.save_state_bytes() != state:
            raise ValueError("routed preparation is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        if travel.steps:
            replace(route, destination_map=home_map, destination_at=nurse_at)(
                actions, runtime.reader, runtime.emulator
            )
        recovery = None
        arrival = runtime.reader.read()
        if (
            not _raw_party_fully_restored(arrival)
            and _field_ready(runtime)
            and arrival.map_id == home_map
            and (arrival.player_y, arrival.player_x) == nurse_at
        ):
            restore = getattr(actions, "execute_restoration", None)
            if restore is None:
                raise RuntimeError("arrival recovery requires the shared metered restoration port")
            offer = RedCenterRestoreGoalProvider(
                actions,
                runtime.reader,
                runtime.emulator,
                runtime.adapter,
                require_full_pp_restore=True,
                **({"include_indigo_lobby": True} if indigo else {}),
            ).offer(runtime.adapter.observe())
            if offer.binding is None:
                raise RuntimeError("restoration unavailable at actual destination")
            restored = restore(offer.binding)
            recovery = dict(
                role="selected_development_restoration",
                model_queries=0,
                actions=restored.actions_executed,
                frames=restored.frames_executed,
                evidence=dict(restored.evidence),
            )
            if not _field_ready(runtime) or not _raw_party_fully_restored(runtime.reader.read()):
                raise RuntimeError("arrival restoration did not produce a ready party")
        child = preparation_binding(runtime, actions, route=route, **kwargs)
        if child is None:
            raise RuntimeError("preparation unavailable at actual destination")
        child_report = child.execute()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                mechanic="routed_preparation",
                support="cartridge_route_then_fresh_binding",
                arrival_restoration=recovery,
                preparation=dict(child_report.evidence),
            ),
        )

    def verify(report):
        if child is None or child_report is None:
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return child.verify(child_report)

    return ExecutableGoalBinding(
        "pokemon.red:routed-preparation:"
        + canonical_sha256(dict(home=home_map, source=sha256(state).hexdigest(),
            **({"restore_exhausted_partial": True} if restore_exhausted_partial else {}))),
        GoalKind.DEVELOP_TEAM,
        effort,
        0.20,
        execute,
        verify,
    )


def parcel_story_binding(runtime, actions, *, route):
    """Resume native parcel pickup/delivery without retriggering the lab rival.

    Reuses the existing revision-specific parcel/Pokedex observation gates. The
    legacy gate supports the current Squirtle curriculum; no broader claim.
    """
    if not _field_ready(runtime):
        return None
    before, lesson = capture_player_lesson_snapshot(runtime)
    raw = before.raw
    state = runtime.reader.read_oaks_errand_state(raw)
    if (
        state.got_pokedex
        or state.oak_got_parcel
        or state.lab_script != 18
        or not state.battled_rival
        or state.first_party_species != 177
        or not raw.party_hp
        or not any(raw.party_hp)
        or state.got_oaks_parcel != state.parcel_in_bag
        or raw.bag_items is None
        or (not state.parcel_in_bag and len(raw.bag_items) >= 20)
        or "receive_pokedex" in lesson["completed_objectives"]
    ):
        return None
    oak = next(
        (
            o
            for o in map_objects(route.rom)[int(MapId.OAKS_LAB)]
            if o.text_and_kind == 5 and o.sprite == 3 and o.movement == 0xFF
        ),
        None,
    )
    if oak is None:
        raise ValueError("cartridge Oak interaction differs")
    target = (oak.y + 1, oak.x)
    origin = Gen1TraversalObserver(runtime.reader).observe()
    try:
        lab = route.route_world.plan_feasible_to_map(origin, int(MapId.OAKS_LAB), goal_at=target)
        mart = (
            None
            if state.parcel_in_bag
            else route.route_world.plan_feasible_to_map(origin, int(MapId.VIRIDIAN_MART))
        )
    except RoutePlanningError:
        return None
    initial = runtime.emulator.save_state_bytes()
    used = False

    def execute():
        nonlocal used
        if used or runtime.emulator.save_state_bytes() != initial:
            raise ValueError("parcel goal is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        # This selected errand explicitly owns bounded native Oak/Mart scripts.
        # Preserve the transition's prohibition on combining generic scripted
        # acknowledgement with the newer ordinary wild/poison-faint recovery.
        scripted = replace(
            route, maximum_scripted_dialogues=4,
            allow_wild_faints=False, allow_field_faint_dialogue=False,
        )
        if mart is not None:
            replace(
                scripted, destination_map=int(MapId.VIRIDIAN_MART), destination_at=mart.terminal_at
            )(actions, runtime.reader, runtime.emulator)
            _receive_parcel(actions, runtime.reader, DEFAULT_QUALIFIED_PLAY_TIMING)
        current = runtime.reader.read_oaks_errand_state(runtime.reader.read())
        if not current.battled_rival or not current.got_oaks_parcel or not current.parcel_in_bag:
            raise RuntimeError("native parcel delivery prerequisites absent")
        replace(scripted, destination_map=int(MapId.OAKS_LAB), destination_at=target)(
            actions, runtime.reader, runtime.emulator
        )
        objects = runtime.reader.read_current_map_objects()
        if not any(o.picture_id == oak.sprite and o.at == (oak.y, oak.x) for o in objects):
            raise RuntimeError("Oak absent at observed handoff")
        if runtime.reader.read_player_facing() != "up":
            actions.execute(MacroAction(MacroActionKind.MOVE, "up"))
        now = runtime.reader.read()
        if (now.player_y, now.player_x) != target or runtime.reader.read_player_facing() != "up":
            raise RuntimeError("parcel handoff facing differs")
        actions.execute(MacroAction(MacroActionKind.INTERACT))
        actions.execute(
            MacroAction(
                MacroActionKind.WAIT, repeat=DEFAULT_QUALIFIED_PLAY_TIMING.dialogue_wait_frames
            )
        )
        recovery = None
        try:
            _receive_pokedex(actions, runtime.reader, DEFAULT_QUALIFIED_PLAY_TIMING)
        except QualifiedPlayError:
            native = runtime.reader.read_oaks_errand_state(runtime.reader.read())
            if not native.pokedex_departure_dialogue:
                raise
            # Same already-selected story goal, within the shared input budget.
            # Reuse the separately native-qualified recovery, not another route
            # or an unbounded increase to the dialogue loop's pulse allowance.
            ra, rf = actions.actions_executed, runtime.emulator.frame_count
            attempts = RedControlRecoveryGoalProvider(
                actions, runtime.reader, runtime.emulator, runtime.adapter
            )._recover()
            recovery = dict(
                reason="native_pokedex_departure_dialogue",
                attempts=attempts,
                actions=actions.actions_executed - ra,
                frames=runtime.emulator.frame_count - rf,
                model_queries=0,
            )
        for _ in range(32):
            if _field_ready(runtime):
                break
            if runtime.reader.read().battle_state:
                raise RuntimeError("parcel handoff entered unexpected battle")
            actions.execute(MacroAction(MacroActionKind.CANCEL))
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=120))
        else:
            raise RuntimeError("parcel handoff did not settle")
        if not runtime.reader.read_oaks_errand_state(runtime.reader.read()).pokedex_snapshot:
            raise RuntimeError("native Pokedex gate not verified")
        runtime.observer.latch_verified_facts(
            COMPLETION_QUEST.objective("receive_pokedex").completion_facts
        )
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                mechanic="native_parcel_delivery",
                lab_rival_replayed=False,
                deterministic_dialogue=True,
                teacher_battle_choices=0,
                bounded_handoff_recovery=recovery,
            ),
        )

    def verify(report):
        after, terminal = capture_player_lesson_snapshot(runtime)

        def party(doc):
            return [
                (m["specimen_ref"], m["species_id"], m["level"], m["experience"])
                for m in doc["party"]
            ]

        expected_bag = tuple((i, n) for i, n in raw.bag_items if i != ItemId.OAKS_PARCEL)
        if (
            used
            and report.actions_executed > 0
            and _field_ready(runtime)
            and runtime.reader.read_oaks_errand_state(after.raw).pokedex_snapshot
            and party(lesson) == party(terminal)
            and after.raw.player_money == raw.player_money
            and after.raw.bag_items == expected_bag
            and set(terminal["completed_objectives"])
            == set(lesson["completed_objectives"]) | {"receive_pokedex"}
        ):
            return GoalVerification.succeeded()
        return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

    effort = min(1.0, (lab.cost + (0 if mart is None else mart.cost) + 160) / 3000)
    return ExecutableGoalBinding(
        "pokemon.red:resumed-parcel:" + canonical_sha256(lesson),
        GoalKind.ADVANCE_STORY,
        effort,
        0.20,
        execute,
        verify,
    )
