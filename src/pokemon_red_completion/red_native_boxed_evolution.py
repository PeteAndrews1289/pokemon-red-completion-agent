"""Native-player wiring for the existing boxed-evolution skill.

Cartridge routes connect the Center, PC and training boundary; the existing
trainer owns battle mechanics with explicit direct-trainee opt-in and a
mechanics-based damaging-move selector. This is a deterministic skill, not a new learner. Only a
surplus precursor is eligible, so acquiring its evolution cannot erase a living
species. Both preparation and training share the caller's hard action budget.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from functools import partial
from typing import cast

from pokemon_red_completion import red_goal_context as context
from pokemon_red_completion.blaine import _route_11_heal_and_return
from pokemon_red_completion.collection import CollectionLocation
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_cartridge import CartridgeReadError, wild_tables
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
from pokemon_red_completion.gen1_traversal import map_object_events
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind, GoalUnavailableReason
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.observation import MapId, RawGameState
from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.party_development_outcome_learning import (
    PartyDevelopmentOutcomeModel,
    canonical_party_development_outcome_model_sha256,
)
from pokemon_red_completion.party_development_rank import (
    PARTY_DEVELOPMENT_WORKLOAD_FEATURE_SCHEMA_ID,
    PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_battle_catalog import (
    PokemonRedBattleCatalog,
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)
from pokemon_red_completion.red_boxed_level_evolution import (
    BoundedEvolutionTrainingResult,
    SemanticPCBoundaryAccess,
)
from pokemon_red_completion.red_collection import (
    red_internal_species_id,
    red_internal_species_number,
    red_species_number,
    red_species_ref,
)
from pokemon_red_completion.red_dual_capability_curriculum_runtime import SemanticVenueRouteBinding
from pokemon_red_completion.red_evolution_helper_xp import EvolutionHelperXPExhausted
from pokemon_red_completion.red_goal_boxed_evolution import RedGoalBoxedEvolutionExecutor
from pokemon_red_completion.red_goal_skills import (
    RedCenterRestoreGoalProvider,
    finish_center_dialogue,
    prepare_center_departure,
)
from pokemon_red_completion.red_party import PokemonRedPartyReader, party_observation_from_raw
from pokemon_red_completion.red_team_training import (
    COLLECTION_UNSUPPORTED_MOVE_EFFECTS,
    EvolutionSettlementReserveReached,
    EvolutionTrainingPaused,
    EvolutionMovementLimitReached,
    EvolutionVenueExhausted,
    collection_encounter_coverage,
    collection_escape_escort,
    collection_finisher,
    evolution_reserve_requested,
)
from pokemon_red_completion.red_trainer_evolution import level_evolution_edges
from pokemon_red_completion.red_training_ground_route import RedVermilionGroundTransition
from pokemon_red_completion.route_plan import RoutePlanningError
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld
from pokemon_red_completion.training_venue import TrainingVenue


class EvolutionWallLimitReached(EvolutionTrainingPaused):
    """A counted safe pause, not an unreported generic training exception."""


class EvolutionQuantumLimitReached(EvolutionTrainingPaused):
    """All declared quanta finished with verified XP and settled field control."""

    def __init__(
        self,
        battles: int,
        healing_trips: int,
        maximum_quanta: int,
        *,
        trainee_initial_xp: int | None = None,
        trainee_terminal_xp: int | None = None,
        trainee_xp_gained: int | None = None,
    ) -> None:
        super().__init__(
            battles,
            healing_trips,
            trainee_initial_xp=trainee_initial_xp,
            trainee_terminal_xp=trainee_terminal_xp,
            trainee_xp_gained=trainee_xp_gained,
        )
        self.maximum_quanta = validate_native_evolution_quanta(maximum_quanta)


def native_evolution_training_diagnostics(actions):
    """Connect existing observational sinks; never install training authority.

    Inner wild training still uses the legacy rule-based skill. Its validated
    move selection is an attempt, not proof of a completed attack. Durable input
    records and the terminal summary establish what subsequently happened.
    """
    record = getattr(actions, "record_diagnostic_event", None)
    if not callable(record):
        return {}

    def emit(kind, payload):
        record(kind, dict(actor="rule_based_support", source="native_level_evolution", **payload))

    def selected_move(raw, slot):
        fields = (
            "map_id",
            "battle_state",
            "battle_result",
            "party_species_ids",
            "party_levels",
            "party_hp",
            "party_max_hp",
            "party_status",
            "party_moves",
            "party_pp",
            "active_party_index",
            "active_party_species_id",
            "active_party_level",
            "active_party_hp",
            "active_party_moves",
            "active_party_pp",
            "enemy_species_id",
            "enemy_level",
            "enemy_hp",
            "enemy_max_hp",
            "enemy_status",
            "player_stat_stages",
            "enemy_stat_stages",
            "player_disabled_move_slot",
            "player_confused",
            "enemy_confused",
            "enemy_using_trapping_move",
        )
        emit(
            "wild_training_move",
            dict(
                selected_move_slot=slot,
                selection_validated=True,
                execution_confirmed=False,
                observed={name: getattr(raw, name, None) for name in fields},
            ),
        )

    return dict(
        decision_sink=lambda row: emit("wild_training_control", row.public_dict()),
        candidate_decision_sink=lambda row: emit("wild_training_candidates", row.public_dict()),
        execution_summary_sink=lambda row: emit("wild_training_summary", row.public_dict()),
        move_decision_sink=selected_move,
    )


def _center_blocker_can_walk(blocker, world, map_id):
    """A known roaming NPC can pause between animation steps on the goal tile."""
    if blocker.moving:
        return True
    from .observation import CurrentMapObject

    rom = getattr(world, "rom", None)
    if not isinstance(blocker, CurrentMapObject) or not isinstance(rom, bytes):
        return False
    try:
        matches = tuple(
            event
            for event in map_object_events(rom, (map_id,))
            if event.object_index == blocker.sprite_index and event.sprite_id == blocker.picture_id
        )
    except CartridgeReadError:
        return False
    return len(matches) == 1 and matches[0].can_walk


def native_evolution_pc_replanner(runtime, world, actions, *, allow_offscreen_approach=False):
    """Wait for a known walking NPC on a selected Center PC or return stance.

    No occupied tile is ignored. Once it vacates, fresh native occupancy and
    every other route constraint still apply. Static/unrecognized blockers keep
    the original planner failure, and waiting shares the caller's input budget.
    """
    from .actions import MacroAction, MacroActionKind
    from .red_goal_skills import _POKEMON_CENTER_MAPS

    if type(allow_offscreen_approach) is not bool:
        raise TypeError("offscreen Center approach requires explicit boolean")

    delegate = world.replanner()

    def replan(request):
        if (
            request.goal_map not in _POKEMON_CENTER_MAPS
            or request.current.map_id != request.goal_map
            or request.goal_at not in {(4, 13), (3, 3)}
        ):
            return delegate(request)
        objects = tuple(
            o for o in runtime.reader.read_current_map_objects() if o.at == request.goal_at
        )
        if len(objects) != 1 or not _center_blocker_can_walk(objects[0], world, request.goal_map):
            return world.with_current_observation(runtime.reader).replanner()(request)
        before = runtime.adapter.observe()
        if (
            not before.input_ready
            or before.raw.battle_state
            or (before.raw.map_id, before.raw.player_y, before.raw.player_x)
            != (request.current.map_id, *request.current.at)
        ):
            raise context.RedGoalContextError("PC wait requires the actual ready route boundary")
        if allow_offscreen_approach and not getattr(objects[0], "visible", True):
            # Off-camera movement can remain suspended. Approach the SAME
            # occupied destination through a real adjacent land tile first.
            # Only the initial _walk fallback opts in; in-flight replans retain
            # their original position and bounded-wait contract.
            from .red_player_party_loan import _walk
            from .red_resource_goal_router import _walking_plan
            from .route_plan import RoutePlanningError

            current = world.with_current_observation(runtime.reader)
            y, x = request.goal_at
            choices = []
            for adjacent in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if min(adjacent) < 0 or adjacent == request.current.at:
                    continue
                try:
                    quote = current.plan_feasible_to_map(
                        request.current, request.goal_map, goal_at=adjacent
                    )
                except RoutePlanningError:
                    continue
                if (
                    _walking_plan(quote)
                    and quote.macro_path.maps == (request.goal_map,)
                    and quote.terminal_mode == "land"
                    and quote.terminal_at == adjacent
                ):
                    choices.append((quote.cost, adjacent))
            if not choices:
                raise context.RedGoalContextError(
                    "offscreen Center blocker has no legal local approach"
                )
            adjacent = min(choices)[1]
            _walk(runtime, actions, current, request.goal_map, adjacent)
            approached = runtime.adapter.observe()
            if (
                not approached.input_ready
                or approached.raw.battle_state
                or (approached.raw.map_id, approached.raw.player_y, approached.raw.player_x)
                != (request.goal_map, *adjacent)
                or approached.party != before.party
                or approached.collection_observation != before.collection_observation
                or any(
                    getattr(approached.raw, k) != getattr(before.raw, k)
                    for k in ("player_money", "bag_items", "badge_bits", "event_flags")
                )
            ):
                raise context.RedGoalContextError(
                    "offscreen Center approach changed protected native state"
                )
            live = Gen1TraversalObserver(runtime.reader).observe()
            if not live.ready or live.interruption is not None or live.mode != "land":
                raise context.RedGoalContextError(
                    "offscreen Center approach did not settle on land"
                )
            record = getattr(actions, "record_diagnostic_event", None)
            if callable(record):
                record(
                    "offscreen_center_approach",
                    dict(
                        original_goal_map=request.goal_map,
                        original_goal_at=request.goal_at,
                        approach_at=adjacent,
                        same_map_legal_walk=True,
                        occupied_goal_not_ignored=True,
                        model_queries=0,
                    ),
                )
            request = replace(request, current=live)
            before = approached
        for _ in range(16):
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=120))
            after = runtime.adapter.observe()
            fields = (
                "map_id",
                "player_x",
                "player_y",
                "player_money",
                "bag_items",
                "badge_bits",
                "event_flags",
                "battle_state",
            )
            if (
                not after.input_ready
                or after.party != before.party
                or after.collection_observation != before.collection_observation
                or any(getattr(after.raw, key) != getattr(before.raw, key) for key in fields)
            ):
                raise context.RedGoalContextError("PC wait changed protected native state")
            live = Gen1TraversalObserver(runtime.reader).observe()
            # The route world reserves off-camera sprites too. A visible-only
            # snapshot must not mistake an off-screen occupied goal for vacancy.
            occupied = frozenset(o.at for o in runtime.reader.read_current_map_objects())
            record = getattr(actions, "record_diagnostic_event", None)
            if callable(record):
                record(
                    "center_goal_wait_occupancy",
                    dict(
                        goal_map=request.goal_map,
                        goal_at=request.goal_at,
                        wait_ordinal=_ + 1,
                        logical_occupied=sorted(occupied),
                        visible_occupied=sorted(live.occupied),
                        prior_blocked=sorted(request.blocked.get(request.goal_map, ())),
                        model_queries=0,
                    ),
                )
            # During a step, logical object tiles can advance before rendered
            # occupancy. A free logical destination alone is not a free tile.
            if request.goal_at not in occupied | live.occupied:
                blocked = dict(request.blocked)
                blocked[request.goal_map] = (
                    blocked.get(request.goal_map, frozenset()) - {request.goal_at}
                ) | live.occupied
                return world.with_current_observation(runtime.reader).replanner()(
                    replace(request, current=live, blocked=blocked)
                )
        raise context.RedGoalContextError("moving PC blocker did not vacate within its bound")

    return replan


def center_walk_party_preserved(before, after) -> bool:
    """Keep exact party identity; admit only existing verified nonfaint poison loss."""
    from .red_silph_reward import reward_vitals_preserved

    if before.party == after.party:
        return True
    if (before.party.size != after.party.size
            or not reward_vitals_preserved(before.raw, after.raw)):
        return False
    restored = []
    for old, new in zip(before.party.members, after.party.members, strict=True):
        if old.hp != new.hp and new.hp <= 0:
            return False
        restored.append(replace(new, hp=old.hp))
    return before.party == replace(after.party, members=tuple(restored))


def prepare_native_training_center(
    runtime: context.RedGoalContextRuntime,
    world: StrategicScenarioRouteWorld,
    actions: CountingExecutor,
    *,
    live_route_replanning: bool = False,
) -> None:
    """Reach the existing nurse boundary from an actual retained Center tile."""
    from pokemon_red_completion.red_goal_skills import _POKEMON_CENTER_MAPS
    from pokemon_red_completion.red_resource_goal_router import _ROUTE_LIMITS, _walking_plan
    from pokemon_red_completion.route_executor import execute_route

    before = runtime.adapter.observe()
    if before.raw.map_id not in _POKEMON_CENTER_MAPS or (
        before.raw.player_x,
        before.raw.player_y,
    ) == (3, 3):
        return
    if before.raw.battle_state or not before.input_ready:
        raise context.RedGoalContextError("native Center preparation requires settled control")
    traversal = Gen1TraversalObserver(runtime.reader)
    start = traversal.observe()
    if live_route_replanning:
        world = world.with_current_observation(runtime.reader)
    route = world.plan_feasible_to_map(start, start.map_id, goal_at=(3, 3))
    if not _walking_plan(route):
        raise context.RedGoalContextError("native nurse access must be walking-only")
    prepare_center_departure(actions, runtime.reader)
    if live_route_replanning:
        report = execute_route(
            route, actions, traversal, limits=_ROUTE_LIMITS, replanner=world.replanner()
        )
    else:
        report = execute_route(route, actions, traversal, limits=_ROUTE_LIMITS)
    after = runtime.adapter.observe()
    if (
        not report.passed
        or (after.raw.map_id, after.raw.player_x, after.raw.player_y) != (before.raw.map_id, 3, 3)
        or after.raw.battle_state
        or not after.input_ready
        or not center_walk_party_preserved(before, after)
        or after.collection_observation != before.collection_observation
        or after.raw.bag_items != before.raw.bag_items
        or after.raw.player_money != before.raw.player_money
    ):
        raise context.RedGoalContextError("native nurse access changed its retained boundary")


def restore_native_center_party(
    runtime: context.RedGoalContextRuntime,
    actions: CountingExecutor,
) -> int:
    """Recheck the actual party after storage; a restored old party is insufficient.

    A computed PC return may reach the nurse facing sideways. Use the existing
    stationary-facing guard and whole-party verifier, not the old teacher's
    lead-specific PP signature or an assumed successful interaction.
    """
    from pokemon_red_completion.red_goal_skills import _raw_party_restored
    from pokemon_red_completion.red_pc_storage import face_pc_boundary

    before = runtime.adapter.observe()
    offered = RedCenterRestoreGoalProvider(
        actions,
        runtime.reader,
        runtime.emulator,
        runtime.adapter,
    ).offer(before)
    if offered.binding is None:
        return 0
    if (before.raw.player_x, before.raw.player_y) == (3, 3):
        face_pc_boundary(actions, runtime.reader, "up")
    restoration = getattr(actions, "execute_restoration", None)
    report = restoration(offered.binding) if callable(restoration) else offered.binding.execute()
    after = runtime.adapter.observe()
    if (
        offered.binding.verify(report).status is not GoalDecisionOutcome.SUCCEEDED
        or not _raw_party_restored(after.raw)
        or after.collection_observation != before.collection_observation
        or after.raw.bag_items != before.raw.bag_items
        or after.raw.player_money != before.raw.player_money
    ):
        raise context.RedGoalContextError(
            "native Center recovery did not preserve and heal the party"
        )
    return 1


def native_training_move_slot(state: RawGameState) -> int:
    """Choose usable damage by mechanics, never an older party's slot order.

    The venue's independent per-turn HP/PP guard still runs. Unsupported
    special-damage and risky self-damaging moves are not silently improvised.
    """
    from pokemon_red_completion.red_team_training import (
        _PauseForTeamTrainingRecovery,
        _PauseForTrainingDisable,
    )

    catalog = PokemonRedBattleCatalog()
    if state.active_party_species_id is None or state.enemy_species_id is None:
        raise _PauseForTeamTrainingRecovery
    own = catalog.resolve_species(pokemon_red_species_ref(state.active_party_species_id)).types
    enemy = catalog.resolve_species(pokemon_red_species_ref(state.enemy_species_id)).types
    candidates = []
    disabled_damage = False
    for index, (move_id, pp) in enumerate(
        zip(state.battler_moves or (), state.battler_pp or (), strict=True)
    ):
        if not move_id or pp <= 0:
            continue
        move = catalog.resolve_move(pokemon_red_move_ref(move_id))
        if move.power <= 0 or move.effect_flags.intersection(COLLECTION_UNSUPPORTED_MOVE_EFFECTS):
            continue
        effectiveness = catalog.type_effectiveness(move.type_name, enemy)
        score = move.power * move.accuracy * effectiveness * (1.5 if move.type_name in own else 1.0)
        if score > 0:
            if index + 1 == (state.player_disabled_move_slot or 0):
                disabled_damage = True
            else:
                # Catalog constant damage is HP loss,not nominal base power1.
                # Prefer a qualified high-accuracy finishing move on observed HP;
                # no damage/survival estimate or guaranteed hit is invented.
                constant = catalog.constant_damage_bound(pokemon_red_move_ref(move_id))
                finishes = (
                    constant is not None
                    and type(state.enemy_hp) is int
                    and 0 < state.enemy_hp <= constant
                    and move.accuracy == 1.0
                )
                candidates.append((finishes, score, -(index + 1)))
    if not candidates:
        if disabled_damage:
            raise _PauseForTrainingDisable
        raise _PauseForTeamTrainingRecovery
    return -max(candidates)[2]


def native_training_move_guard(state: RawGameState) -> None:
    """Keep the per-turn health gate without an old party's preferred slots."""
    from pokemon_red_completion.red_team_training import (
        _PauseForTeamTrainingRecovery,
        _PauseForTrainingHealth,
    )

    hp, maximum = state.battler_hp, state.battler_max_hp
    if hp is None or maximum is None or maximum <= 0:
        raise _PauseForTeamTrainingRecovery
    if hp / maximum <= context.MANSION_TEAM_POLICY.retreat_hp_ratio:
        raise _PauseForTrainingHealth
    native_training_move_slot(state)


def validate_native_evolution_quanta(value: object) -> int:
    """Bound declared work size; action/frame reserves and wall limit still apply."""
    if type(value) is not int or not 1 <= value <= 512:
        raise ValueError("native evolution quantum limit differs")
    return value


def bind_native_evolution_goal_reserve(
    runtime: context.RedGoalContextRuntime,
    actions: CountingExecutor,
    *,
    maximum_actions: int,
    maximum_frames: int,
) -> context.RedGoalContextRuntime:
    """Reserve a goal's PC return, not merely the larger session's return.

    Inventory is action-free, so this baseline also includes the selected
    goal's subsequent transport. All candidates retain the same origin;
    nothing resets the external meter or converts a partial dose to success.
    The independent composed verifier still rejects any actual overrun.
    """
    for value in (maximum_actions, maximum_frames):
        if type(value) is not int or value <= 0:
            raise ValueError("native evolution goal limits must be positive integers")
    action_start = actions.actions_executed
    frame_start = runtime.emulator.frame_count
    requested = runtime.evolution_stop_requested
    action_reserve = min(3000, max(1, maximum_actions // 4))
    frame_reserve = min(250000, max(1, maximum_frames // 4))

    def stop_requested() -> bool:
        used_actions = actions.actions_executed - action_start
        used_frames = runtime.emulator.frame_count - frame_start
        if used_actions < 0 or used_frames < 0:
            raise context.RedGoalContextError("native evolution goal counters moved backwards")
        return (
            evolution_reserve_requested(requested)
            or maximum_actions - used_actions <= action_reserve
            or maximum_frames - used_frames <= frame_reserve
        )

    return replace(runtime, evolution_stop_requested=stop_requested)


def settle_native_evolution(runtime, actions, *, training_error=None) -> dict[str, bool]:
    """Repay an explicitly guarded PC loan before a composite captures its report.

    No callback means the historical behavior is unchanged. This seam cannot
    authorize an unguarded exchange or label an unrestored roster successful.
    Settlement is metered by the same action port as training, not verification.
    """
    if training_error is not None and not isinstance(training_error, BaseException):
        raise TypeError("deferred evolution settlement needs the actual training error")
    callback = runtime.evolution_settlement
    if callback is None:
        # A closed no-loan party has nothing to repay, but its independently
        # verified active roster still certifies a settled partial quantum.
        # Unknown faults and active battles retain their original failure.
        from .red_player_party_guard import RedPlayerPartyGuard

        guard = getattr(runtime.adapter, "party_guard", None)
        if (
            training_error is None
            and isinstance(guard, RedPlayerPartyGuard)
            and not guard.loanable_refs
            and guard.field_carrier is None
        ):
            observed = runtime.adapter.observe()
            if (
                observed.raw.battle_state == 0
                and observed.input_ready
                and not observed.party.fainted_count
            ):
                guard.verify_active_roster_restored()
                expected = getattr(runtime, "evolution_active_roster_refs", None)
                if expected is None:
                    expected = guard.refs
                if (
                    type(expected) is not tuple
                    or len(set(expected)) != len(expected)
                    or not set(guard.refs) <= set(expected)
                    or set(expected) != set(guard.reader.preparation_specimen_refs())
                ):
                    raise context.RedGoalContextError(
                        "no-loan evolution settlement changed its exact active roster"
                    )
                deposited = getattr(runtime, "evolution_deposited_ref", None)
                if deposited is not None and (
                    type(deposited) is not str
                    or sum(m.preparation_ref == deposited
                           for m in runtime.reader.read_box_specimen_identities()) != 1
                ):
                    raise context.RedGoalContextError(
                        "boxed evolution settlement lost its exact deposited specimen"
                    )
                return {"retained_active_roster_restored": True}
        return {}
    from .red_player_party_guard import RedPlayerPartyGuard

    guard = getattr(runtime.adapter, "party_guard", None)
    if (
        callable(callback)
        and isinstance(guard, RedPlayerPartyGuard)
        and not guard.loanable_refs
        and guard.field_carrier is None
    ):
        # Declared no-loan configuration: no exchange could have been
        # authorized, so there is nothing to repay. Settlement is a verified
        # no-op only when every guarded individual is still active; any
        # displaced member still fails closed. No input is sent here.
        observed = runtime.adapter.observe()
        if observed.raw.battle_state or not observed.input_ready:
            if training_error is None:
                raise context.RedGoalContextError("PC loan settlement requires settled field control")
            return {"retained_active_roster_restoration_deferred": True}
        try:
            guard.verify_active_roster_restored()
        except ValueError as error:
            raise context.RedGoalContextError(
                "no-loan evolution settlement found an unrestored active roster"
            ) from error
        return {"no_loan_active_roster_verified": True}
    if (
        not callable(callback)
        or not isinstance(guard, RedPlayerPartyGuard)
        or not guard.loanable_refs
        or guard.storage_reader is None
    ):
        raise context.RedGoalContextError("evolution settlement needs an explicit guarded PC loan")
    before = runtime.adapter.observe()
    if before.raw.battle_state or not before.input_ready:
        if training_error is None:
            raise context.RedGoalContextError("PC loan settlement requires settled field control")
        # Preserve the original fault and named custody at this exact boundary.
        # Existing compulsory control recovery owns any subsequent game input.
        record = getattr(actions, "record_diagnostic_event", None)
        if callable(record):
            record(
                "native_evolution_settlement_deferred",
                {
                    "actor": "rule_based_support",
                    "training_error_type": type(training_error).__name__,
                    "battle_active": bool(before.raw.battle_state),
                    "input_ready": before.input_ready,
                    "model_queries": 0,
                    "settlement_executed": False,
                },
            )
        return {"retained_active_roster_restoration_deferred": True}
    if guard.field_carrier is not None and guard.field_carrier.phase == "active":
        guard.verify_authorized_active_roster()
        return {"field_carrier_custody_retained": True}
    callback(actions)
    guard.verify_active_roster_restored()
    after = runtime.adapter.observe()
    if (
        before.collection_observation.owned_species != after.collection_observation.owned_species
        or Counter(s.species_ref for s in before.collection_observation.specimens)
        != Counter(s.species_ref for s in after.collection_observation.specimens)
        or before.raw.bag_items != after.raw.bag_items
        or before.raw.player_money != after.raw.player_money
        or after.raw.battle_state
        or not after.input_ready
    ):
        raise context.RedGoalContextError("PC loan settlement changed its collection/resources")
    return {"retained_active_roster_restored": True}


def bind_no_loan_evolution_roster(runtime):
    """Snapshot the actual party before resumed training,including earned catches.

    Retained identity/progress checks remain authoritative. This action-free
    binding permits no additions,replacements or removals during training and
    grants no custody or loan authority. Legacy settlement callers remain exact.
    """
    from .red_player_party_guard import RedPlayerPartyGuard

    guard = getattr(runtime.adapter, "party_guard", None)
    if (
        runtime.evolution_settlement is None
        and isinstance(guard, RedPlayerPartyGuard)
        and not guard.loanable_refs
        and guard.field_carrier is None
    ):
        guard.verify_active_roster_restored()
        return replace(
            runtime, evolution_active_roster_refs=guard.reader.preparation_specimen_refs()
        )
    return runtime


def bind_boxed_evolution_roster(runtime, request):
    """Bind only the declared PC exchange, before it sends any input.

    Protected retained members stay active. The exact observed deposit moves to
    storage and the exact observed boxed precursor becomes active; no other
    replacement is permitted. Named loans keep their existing settlement.
    """
    from .red_player_party_guard import RedPlayerPartyGuard

    guard = getattr(runtime.adapter, "party_guard", None)
    if (runtime.evolution_settlement is not None
            or not isinstance(guard, RedPlayerPartyGuard)
            or guard.loanable_refs or guard.field_carrier is not None):
        return runtime
    if type(request) is not context.RedBoxedLevelEvolutionGoalRequest:
        raise context.RedGoalContextError("boxed evolution roster needs its exact request")
    request.__post_init__()
    guard.verify_active_roster_restored()
    party = guard.reader.read()
    refs = guard.reader.preparation_specimen_refs()
    slot = request.deposit_party_slot - 1
    matches = tuple(m for m in runtime.reader.read_box_specimen_identities()
                    if m.box_index == request.current_box_index
                    and m.box_slot == request.precursor_box_slot
                    and m.species_id == request.precursor_internal_species_id)
    if (type(refs) is not tuple or len(refs) != len(party.members)
            or len(set(refs)) != len(refs) or not 0 <= slot < len(refs)
            or party.members[slot].species_id != request.deposit_internal_species_id
            or refs[slot] in guard.refs or len(matches) != 1
            or matches[0].preparation_ref in refs):
        raise context.RedGoalContextError("boxed evolution roster exchange differs")
    expected = tuple(ref for i, ref in enumerate(refs) if i != slot)
    expected += (matches[0].preparation_ref,)
    if len(set(expected)) != len(expected) or not set(guard.refs) <= set(expected):
        raise context.RedGoalContextError("boxed evolution roster loses retained identity")
    return replace(runtime, evolution_active_roster_refs=expected,
                   evolution_deposited_ref=refs[slot])


def boxed_loan_has_retained_fingerprint_collision(runtime, source_internal: int) -> bool:
    """A guarded party cannot train a boxed fingerprint already active.

    Keep the closed-party identity alarm. Decline the offer before PC input;
    unrelated wild acquisition remains available through the existing menu.
    """
    guard = getattr(runtime.adapter, "party_guard", None)
    if guard is None or not getattr(guard, "loanable_refs", frozenset()):
        return False
    active = set(guard.reader.preparation_specimen_refs())
    return any(
        b.species_id == source_internal and b.preparation_ref in active
        for b in runtime.reader.read_box_specimen_identities()
    )


def native_evolution_encounter_supported(
    party,
    source_internal,
    policy,
    level,
    species,
    *,
    allow_guarded_escapes=False,
    excluded_helper_species=frozenset(),
):
    """An existing defensive escape can cover a volatile venue encounter.

    This changes admission only. The trainer still receives the original
    volatile/escort sets, and retains its live HP, PP, faint and XP guards.
    """
    volatile = species in context.MANSION_VOLATILE_ENEMY_SPECIES
    escorted = species in context.MANSION_ESCORT_ENEMY_SPECIES
    if not allow_guarded_escapes and (volatile or escorted):
        return False
    if volatile or escorted:
        return (
            collection_escape_escort(
                party,
                source_internal,
                policy,
                enemy_level=level,
                enemy_species=species,
                # Discovery asks whether normal nursing can restore capability.
                # Training restores the party first; live escape checks remain strict.
                resources=False,
                excluded_helper_species=excluded_helper_species,
            )
            is not None
        )
    return (
        collection_finisher(
            party,
            source_internal,
            policy,
            enemy_level=level,
            enemy_species=species,
            resources=False,
            excluded_helper_species=excluded_helper_species,
        )
        is not None
    )


def validate_native_evolution_venue_model(model, model_sha256):
    """Authenticate the paired existing workload scorer before native input."""
    if (model is None) != (model_sha256 is None):
        raise ValueError("native venue model and declared identity must be paired")
    if model is not None and (
        not isinstance(model, PartyDevelopmentOutcomeModel)
        or model.feature_schema_id not in (PARTY_DEVELOPMENT_WORKLOAD_FEATURE_SCHEMA_ID, PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID)
        or canonical_party_development_outcome_model_sha256(model) != model_sha256
    ):
        raise ValueError("native venue model differs from its declared workload scorer")


@dataclass(frozen=True)
class NativeEvolutionVenuePolicy:
    """A prospectively configured scorer and its declared execution inventory."""

    model: PartyDevelopmentOutcomeModel = field(repr=False, compare=False)
    model_sha256: str
    training_venues: tuple[TrainingVenue, ...]
    allow_direct_evolution: bool = True
    compare_recipient_yield: bool = False

    def __post_init__(self):
        if type(self.compare_recipient_yield) is not bool:
            raise ValueError("native venue yield comparison requires an explicit boolean")
        if type(self.allow_direct_evolution) is not bool:
            raise ValueError("configured evolution mode requires an explicit boolean")
        validate_native_evolution_venue_model(self.model, self.model_sha256)
        if self.model is None or (
            type(self.training_venues) is not tuple
            or len(self.training_venues) < 2
            or any(not isinstance(venue, TrainingVenue) for venue in self.training_venues)
            or len({venue.band.identity for venue in self.training_venues})
            != len(self.training_venues)
        ):
            raise ValueError("configured native venue policy needs distinct declared venues")


def live_native_evolution_venues(party, source_id, venues, tables, exclusions):
    """Recheck the same per-encounter helper coverage the scorer requires."""
    escaped = context.MANSION_VOLATILE_ENEMY_SPECIES | context.MANSION_ESCORT_ENEMY_SPECIES
    return tuple(
        venue for venue in venues
        if collection_encounter_coverage(
            party, source_id, context.MANSION_TEAM_POLICY, tables[venue.map_id],
            resources=True, escape_species=escaped, excluded_helper_species=exclusions,
        )
    )


def _recipient_yield_choice(candidates, available, frozen):
    """Compare observable recipient XP only when every eligible venue has a known quote."""
    eligible = [(row["candidate_index"], row["features"])
                for row, allowed in zip(candidates, available, strict=True) if allowed]
    if any(features["venue.useful_encounters_known"] != 1.0 for _, features in eligible):
        return frozen, "unknown_yield"
    yields = [(index, features["venue.expected_recipient_xp_per_encounter"])
              for index, features in eligible]
    highest = max(value for _, value in yields)
    winners = [index for index, value in yields if value == highest]
    if len(winners) != 1:
        return frozen, "tied_maximum"
    return winners[0], "unique_maximum"


def select_native_evolution_model_venue(
    observation,
    *,
    rom: bytes,
    source_id: int,
    target_id: int,
    venues: tuple[TrainingVenue, ...],
    model: PartyDevelopmentOutcomeModel,
    model_sha256: str,
    choice_state: dict[str, object],
    actions,
    excluded_helper_species: frozenset[int],
    allow_guarded_escapes: bool,
    allow_direct_evolution: bool = False,
    geometry_quotes=None,
    compare_recipient_yield=False,
) -> TrainingVenue:
    """Select greedily, retaining the venue until verified trainee level progress."""
    from pokemon_red_completion.red_party_development_adapter import (
        build_native_evolution_venue_menu,
    )

    if type(allow_direct_evolution) is not bool:
        raise ValueError("native venue mode requires an explicit boolean")
    if type(compare_recipient_yield) is not bool:
        raise ValueError("native venue yield comparison requires an explicit boolean")
    action_scope = (source_id, target_id, model_sha256, allow_direct_evolution)
    if compare_recipient_yield:
        action_scope += ("recipient-yield-v1",)
    if ("venue_identity" in choice_state or "action_scope" in choice_state) and (
        choice_state.get("action_scope") != action_scope
    ):
        raise context.RedGoalContextError(
            "native venue choice state belongs to another action or model"
        )
    if "venue_identity" in choice_state:
        matches = tuple(
            venue for venue in venues if venue.band.identity == choice_state["venue_identity"]
        )
        if len(matches) != 1:
            raise EvolutionVenueExhausted(0, 0)
        return matches[0]
    if not venues:
        raise context.RedGoalContextError("native venue model has no executable inventory")
    model_selected = len(venues) > 1
    document = None
    snapshot_sha256 = None
    comparator_receipt = {}
    actor = "learned_venue_model" if model_selected else "rule_based_support"
    if model_selected:
        trainee = next(
            (member for member in observation.party.members if member.species_id == source_id), None
        )
        if trainee is None:
            raise context.RedGoalContextError("native venue model lost the bound trainee")
        menu = build_native_evolution_venue_menu(
            observation,
            rom=rom,
            trainee=trainee,
            target_species_id=target_id,
            policy=context.MANSION_TEAM_POLICY,
            venues=venues,
            excluded_helper_species=excluded_helper_species,
            allow_guarded_escapes=allow_guarded_escapes,
            resources=True,
            allow_direct_evolution=allow_direct_evolution,
            geometry_quotes=geometry_quotes,
            include_matchup_context=(
                getattr(model, "feature_schema_id", None)
                == PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID
            ),
        )
        if tuple(menu.bindings) != tuple(venue.band for venue in venues):
            raise context.RedGoalContextError(
                "native model menu differs from executable venue inventory"
            )
        selected_index = model.predict(menu.candidate_set)
        if (
            type(selected_index) is not int
            or selected_index not in range(len(venues))
            or not menu.candidate_available[selected_index]
        ):
            raise context.RedGoalContextError("native venue model selected an illegal binding")
        document = menu.candidate_set.public_dict()
        if compare_recipient_yield:
            frozen = selected_index
            selected_index, reason = _recipient_yield_choice(
                document["candidates"], menu.candidate_available, frozen,
            )
            if reason == "unique_maximum":
                model_selected = False
                actor = "declared_yield_comparator"
            comparator_receipt = dict(
                comparison="recipient-yield-v1", comparison_reason=reason, frozen_model_index=frozen,
                candidate_available=list(menu.candidate_available),
            )
        snapshot_sha256 = menu.semantic_snapshot_sha256
    else:
        selected_index = 0
    selected = venues[selected_index]
    choice_state["venue_identity"] = selected.band.identity
    choice_state["action_scope"] = action_scope
    record = getattr(actions, "record_diagnostic_event", None)
    if callable(record):
        record(
            "native_evolution_venue_choice",
            dict(
                actor=actor,
                **comparator_receipt,
                model_selected=model_selected,
                model_sha256=model_sha256,
                selected_index=selected_index,
                selected_venue=selected.band.identity,
                selected_map_id=selected.map_id,
                candidate_count=len(venues),
                candidate_set=document,
                semantic_snapshot_sha256=snapshot_sha256,
                decision_lifetime="until-verified-trainee-level-progress-within-action",
                nominal_yield_model=(
                    "unboosted-guarded-recipient-wild-v2"
                    if allow_direct_evolution
                    else "unboosted-two-participant-wild-v1"
                ),
                allow_direct_evolution=allow_direct_evolution,
                route_geometry=(
                    None
                    if geometry_quotes is None
                    else [quote.public_dict() for quote in geometry_quotes]
                ),
            ),
        )
    return selected


def _native_route_11_heal_and_return(actions, reader, emulator, *, world, ground_transition):
    """Authenticate field escape before the existing outdoor return skill.

    Dig targets the observed healing anchor. The legacy training helper's
    historical town list is not an authority for that native destination.
    """
    from .red_dig_recovery import execute_dig_escape, plan_dig_escape
    from .red_training_transitions import (
        DIG_MOVE_ID,
        RED_ESCAPE_WARP_TILESETS,
        RED_TRAINING_FLY_OUTDOOR_MAPS,
        red_training_fly_available,
    )

    raw = reader.read()
    if reader.read_current_map_tileset() in RED_ESCAPE_WARP_TILESETS:
        start = Gen1TraversalObserver(reader).observe()
        plan = plan_dig_escape(world, reader, raw, start)
        if plan is not None:
            # Escape must retain an executable onward return. A direct
            # Vermilion anchor needs no Fly; other anchors use the caller's
            # already supported outdoor transport, without broadening it.
            if plan.anchor != int(MapId.VERMILION_CITY) and (
                plan.anchor not in RED_TRAINING_FLY_OUTDOOR_MAPS
                or not red_training_fly_available(raw)
                or int(MapId.VERMILION_CITY) not in reader.read_fly_destinations()
            ):
                raise context.RedGoalContextError("native escape lacks its onward training return")
            execute_dig_escape(world, reader, emulator, actions, plan)
        elif (
            raw.map_id == MapId.POKEMON_MANSION_1F
            and not any(DIG_MOVE_ID in moves for moves in (raw.party_moves or ()))
            and red_training_fly_available(raw)
            and int(MapId.VERMILION_CITY) in reader.read_fly_destinations()
        ):
            # A new training venue may become necessary after verified level
            # progress. Exit the current venue normally before field Fly.
            from .actions import MacroAction, MacroActionKind
            from .gen1_field_moves import Gen1FieldMovePort
            from .red_collection_fly import red_fly_landings
            from .red_training_ground_route import VERMILION_TRAINING_EXTERIOR

            landings = dict(red_fly_landings(world.rom))
            RedVermilionGroundTransition(
                rom=world.rom,
                route_world=world,
                destination_map=int(MapId.CINNABAR_ISLAND),
                destination_at=landings[int(MapId.CINNABAR_ISLAND)],
                full_event_offsets=True,
                observe_terrain=True,
            )(actions, reader, emulator)
            if reader.read().map_id != MapId.CINNABAR_ISLAND:
                raise context.RedGoalContextError("native training egress missed Cinnabar")
            receipt = Gen1FieldMovePort(actions, reader, emulator).execute(
                MacroAction(MacroActionKind.FIELD_MOVE, "fly:vermilion_city")
            )
            arrival = reader.read()
            if (
                receipt.destination_map != int(MapId.VERMILION_CITY)
                or receipt.flight_confirmations != 1
                or arrival.map_id != MapId.VERMILION_CITY
                or (arrival.player_y, arrival.player_x) != VERMILION_TRAINING_EXTERIOR
            ):
                raise context.RedGoalContextError("native training egress missed the Vermilion healing boundary")
            record = getattr(actions, "record_diagnostic_event", None)
            if callable(record):
                record("native_evolution_mansion_egress", dict(
                    source_map=int(MapId.POKEMON_MANSION_1F),
                    exit_map=int(MapId.CINNABAR_ISLAND),
                    destination_map=int(arrival.map_id),
                    flight_confirmations=receipt.flight_confirmations,
                ))
    return _route_11_heal_and_return(
        actions,
        reader,
        emulator,
        ground_transition=ground_transition,
    )


def _with_native_cave_ground_recovery(venue, world):
    """Keep selected venue transport executable after a PC loan removes Dig."""
    if (
        venue.map_id == int(MapId.POKEMON_MANSION_1F)
        and venue.heal_and_return is context.MANSION_TRAINING_VENUE.heal_and_return
    ):
        from .red_mansion_training_recovery import mansion_native_heal_and_return

        return replace(
            venue,
            heal_and_return=partial(
                mansion_native_heal_and_return,
                world=world,
                legacy=venue.heal_and_return,
            ),
        )
    cave = (
        venue.map_id == int(MapId.DIGLETTS_CAVE)
        and venue.heal_and_return is context.DIGLETTS_CAVE_TRAINING_VENUE.heal_and_return
    )
    route_11 = (
        venue.map_id == int(MapId.ROUTE_11)
        and venue.heal_and_return is context.ROUTE_11_TRAINING_VENUE.heal_and_return
    )
    if not (cave or route_11):
        return venue

    def heal_and_return(actions, reader, emulator):
        ground = RedVermilionGroundTransition(rom=world.rom, route_world=world)
        recovery = partial(
            _native_route_11_heal_and_return,
            world=world,
            ground_transition=ground,
        )
        if route_11:
            return recovery(actions, reader, emulator)
        return venue.heal_and_return(
            actions,
            reader,
            emulator,
            route_11_recovery=recovery,
        )

    return replace(venue, heal_and_return=heal_and_return)


def _mansion_transport_ready(runtime, world, party):
    from .red_mansion_training_recovery import mansion_native_transport_ready

    return mansion_native_transport_ready(runtime, world, party)


def _restore_native_cave_venue_resources(
    runtime,
    actions,
    *,
    source_id,
    venues,
    encounters,
    excluded_helper_species,
) -> int:
    """Nurse the current Cave before resource-checked comparative inference."""
    from pokemon_red_completion.red_team_training import (
        collection_encounter_coverage,
        execute_evolution_healing_trip,
    )

    before = runtime.adapter.observe()
    if before.raw.map_id != int(MapId.DIGLETTS_CAVE):
        return 0

    def ready(party):
        return all(
            collection_encounter_coverage(
                party,
                source_id,
                context.MANSION_TEAM_POLICY,
                encounters[venue.map_id],
                resources=True,
                escape_species=(
                    context.MANSION_VOLATILE_ENEMY_SPECIES | context.MANSION_ESCORT_ENEMY_SPECIES
                ),
                excluded_helper_species=excluded_helper_species,
            )
            for venue in venues
        )

    if ready(before.party):
        return 0
    if before.raw.battle_state or not before.input_ready:
        raise context.RedGoalContextError("native Cave resource recovery requires settled control")
    current = tuple(venue for venue in venues if venue.is_in_map(before.raw))
    if len(current) != 1:
        raise context.RedGoalContextError("native Cave resource recovery lacks its current venue")
    execute_evolution_healing_trip(
        actions,
        runtime.reader,
        runtime.emulator,
        current[0].heal_and_return,
        metered=True,
    )
    after = runtime.adapter.observe()
    if (
        not current[0].is_in_map(after.raw)
        or after.raw.battle_state
        or not after.input_ready
        or after.collection_observation != before.collection_observation
        or after.raw.bag_items != before.raw.bag_items
        or after.raw.player_money != before.raw.player_money
        or not ready(after.party)
    ):
        raise context.RedGoalContextError(
            "native Cave recovery did not retain stock and restore helper resources"
        )
    return 1


def bind_native_boxed_evolution(
    runtime: context.RedGoalContextRuntime,
    world: StrategicScenarioRouteWorld,
    *,
    maximum_quanta: int = 1,
    maximum_wall_seconds: int = 600,
    retain_quantum: Callable[[], None] | None = None,
    allow_cross_box: bool = False,
    allow_guarded_venue_escapes: bool = False,
    allow_direct_evolution: bool = True,
    training_venues: tuple[TrainingVenue, ...] | None = None,
    prefer_highest_supported_venue: bool = False,
    venue_model: PartyDevelopmentOutcomeModel | None = None,
    venue_model_sha256: str | None = None,
    observe_venue_decision: Callable[[object, tuple[TrainingVenue, ...], int, int], None]
    | None = None,
) -> context.RedGoalContextRuntime:
    """Return an isolated runtime; do not mutate a saved observer's old profile."""
    maximum_quanta = validate_native_evolution_quanta(maximum_quanta)
    if type(maximum_wall_seconds) is not int or maximum_wall_seconds <= 0:
        raise ValueError("native evolution wall limit must be a positive integer")
    if type(allow_cross_box) is not bool:
        raise ValueError("native evolution cross-box mode differs")
    if type(allow_direct_evolution) is not bool:
        raise ValueError("native evolution direct-fight mode requires an explicit boolean")
    if type(allow_guarded_venue_escapes) is not bool:
        raise ValueError("native evolution guarded-venue mode differs")
    if type(prefer_highest_supported_venue) is not bool:
        raise ValueError("native evolution venue preference differs")
    if observe_venue_decision is not None and not callable(observe_venue_decision):
        raise TypeError("native venue observer must be callable")
    if (venue_model is None) != (venue_model_sha256 is None):
        raise ValueError("native venue model and declared identity must be paired")
    policy = getattr(runtime, "native_evolution_venue_policy", None)
    compare_recipient_yield = False
    if policy is not None:
        if not isinstance(policy, NativeEvolutionVenuePolicy):
            raise ValueError("configured native venue policy differs")
        if venue_model is None:
            # Explicit learned runtime mode replaces the legacy level heuristic.
            venue_model, venue_model_sha256 = policy.model, policy.model_sha256
            prefer_highest_supported_venue = False
        elif venue_model_sha256 != policy.model_sha256:
            raise ValueError("explicit native venue model conflicts with configured policy")
        if training_venues is not None and training_venues != policy.training_venues:
            raise ValueError("explicit native venues conflict with configured policy")
        training_venues = policy.training_venues
        compare_recipient_yield = policy.compare_recipient_yield
        # A declared helper-only regime cannot be weakened by a local default.
        allow_direct_evolution = allow_direct_evolution and policy.allow_direct_evolution
    validate_native_evolution_venue_model(venue_model, venue_model_sha256)
    if venue_model is not None and prefer_highest_supported_venue:
        raise ValueError("native model choice cannot be prefiltered by highest-level preference")
    if training_venues is not None and (
        not isinstance(training_venues, tuple)
        or not training_venues
        or any(not isinstance(v, TrainingVenue) for v in training_venues)
        or len({v.band.identity for v in training_venues}) != len(training_venues)
    ):
        raise ValueError("native evolution declared venues differ")
    runtime = replace(runtime, boxed_level_evolution_cross_box=allow_cross_box)
    spec = next(s for s in runtime.profile.providers if s.kind is GoalKind.EVOLVE_SPECIES)
    registration = runtime.registration_policy
    # A selected evolution has an exact physical-stock delta. Shared-XP helpers
    # must not automatically evolve as a second, unselected transformation.
    # Derive this restriction from the cartridge; never loosen the stock,
    # identity, XP, registration or settlement checks to accept extra changes.
    excluded_helper_species = (
        frozenset(source for source, _, _ in level_evolution_edges(world.rom))
        if registration is not None
        else frozenset()
    )

    certified = getattr(runtime, "certified_evolution_helper_xp", False)
    if type(certified) is not bool:
        raise ValueError("certified helper XP mode must be an explicit boolean")
    helper_xp_guard = None
    if certified:
        from .red_evolution_helper_xp import EvolutionHelperXPGuard

        helper_xp_guard = EvolutionHelperXPGuard.from_rom(world.rom, excluded_helper_species)

    def helper_exclusions(observation, *, diagnostic_headroom=False):
        if helper_xp_guard is None:
            return excluded_helper_species
        # GoalObservation deliberately projects one coherent raw frame without XP.
        # Enrich only this executor-side certificate, never the policy observation.
        coherent = party_observation_from_raw(observation.raw)
        rich = PokemonRedPartyReader(runtime.emulator).read()
        if len(rich.members) != len(coherent.members) or any(
            replace(member, experience=None) != expected
            for member, expected in zip(rich.members, coherent.members, strict=True)
        ):
            return excluded_helper_species
        strict = helper_xp_guard.exclusions(rich, observation.raw)
        if diagnostic_headroom:
            return strict - helper_xp_guard.headroom_exhausted_species(rich, observation.raw)
        return strict

    def allowed(observation: context.RedGoalObservation) -> bool:
        source = cast(str, spec.parameters["source_species_ref"])
        target = cast(str, spec.parameters["target_species_ref"])
        if registration is not None:
            return registration.evolution_allowed(
                observation.collection_observation,
                source,
                target,
            )
        return (
            sum(s.species_ref == source for s in observation.collection_observation.specimens) == 2
        )

    def supported_venues(
        observation: context.RedGoalObservation, *, diagnostic_headroom=False
    ) -> tuple[TrainingVenue, ...]:
        source_id = cast(str, spec.parameters["source_species_ref"])
        source_internal = red_internal_species_id(red_species_number(source_id))
        party = observation.party
        if source_internal not in party.species_ids() and party.size == 6:
            try:
                request = context.boxed_level_evolution_request(runtime, spec, observation)
            except context.RedGoalContextError:
                return ()
            # Both combat and field transport must use the observed helpers
            # left after this exact PC loan. A boxed trainee's field moves and
            # stats are never invented to make the route appear available.
            remaining = tuple(
                member for member in party.members if member.slot != request.deposit_party_slot
            )
            party = replace(
                party,
                members=tuple(
                    replace(member, slot=index + 1) for index, member in enumerate(remaining)
                ),
            )
        tables = wild_tables(world.rom)
        return tuple(
            replace(
                _with_native_cave_ground_recovery(venue, world),
                move_slot=native_training_move_slot,
                move_guard=native_training_move_guard,
            )
            for venue in (
                training_venues
                if training_venues is not None
                else (
                    context.ROUTE_11_TRAINING_VENUE,
                    context.DIGLETTS_CAVE_TRAINING_VENUE,
                    context.MANSION_TRAINING_VENUE,
                )
            )
            if (venue.native_transport_ready is None or venue.native_transport_ready(party) is True)
            and (
                venue_model is None
                or venue.map_id != int(MapId.POKEMON_MANSION_1F)
                or venue.native_transport_ready is not None
                or _mansion_transport_ready(runtime, world, party)
            )
            and tables.get(venue.map_id)
            and collection_finisher(
                party,
                source_internal,
                context.MANSION_TEAM_POLICY,
                enemy_level=venue.band.rare_maximum_encounter_level
                or venue.band.maximum_encounter_level,
                resources=False,
                excluded_helper_species=helper_exclusions(
                    observation, diagnostic_headroom=diagnostic_headroom
                ),
            )
            is not None
            and all(
                native_evolution_encounter_supported(
                    party,
                    source_internal,
                    context.MANSION_TEAM_POLICY,
                    level,
                    species,
                    allow_guarded_escapes=allow_guarded_venue_escapes,
                    excluded_helper_species=helper_exclusions(
                        observation, diagnostic_headroom=diagnostic_headroom
                    ),
                )
                for level, species in tables[venue.map_id]
            )
        )

    def readiness(observation: context.RedGoalObservation) -> context.RedGoalSkillAvailability:
        source = context._text(spec.parameters, "source_species_ref")
        specimens = [
            s for s in observation.collection_observation.specimens if s.species_ref == source
        ]
        candidates = [
            s
            for s in specimens
            if s.location is CollectionLocation.PARTY
            or (
                s.location is CollectionLocation.BOX
                and (
                    allow_cross_box
                    or s.container_index == observation.collection_observation.current_box_index
                )
            )
        ]
        if not allowed(observation) or not candidates:
            return context.RedGoalSkillAvailability.unavailable(
                GoalUnavailableReason.NO_LEGAL_TARGET
            )
        source_internal = red_internal_species_id(red_species_number(source))
        if boxed_loan_has_retained_fingerprint_collision(runtime, source_internal):
            return context.RedGoalSkillAvailability.unavailable(
                GoalUnavailableReason.MISSING_CAPABILITY
            )
        if not supported_venues(observation):
            return context.RedGoalSkillAvailability.unavailable(
                GoalUnavailableReason.MISSING_CAPABILITY
            )
        return context.RedGoalSkillAvailability.available()

    def observe_trainee_xp(source_id: int, target_id: int | None = None) -> int | None:
        try:
            members = PokemonRedPartyReader(runtime.emulator).read().members
        except Exception:
            members = ()
        for member in members:
            if member.species_id == source_id and type(member.experience) is int and member.experience >= 0:
                return member.experience
        if target_id is not None:
            for member in members:
                if member.species_id == target_id and type(member.experience) is int and member.experience >= 0:
                    return member.experience
        return None

    def xp_kwargs(
        initial_xp: int | None,
        terminal_xp: int | None,
    ) -> dict[str, int]:
        if (
            type(initial_xp) is int
            and initial_xp >= 0
            and type(terminal_xp) is int
            and terminal_xp >= initial_xp
        ):
            return {
                "trainee_initial_xp": initial_xp,
                "trainee_terminal_xp": terminal_xp,
                "trainee_xp_gained": terminal_xp - initial_xp,
            }
        return {}

    def check_settlement_reserve(battles: int = 0, heals: int = 0) -> None:
        if evolution_reserve_requested(runtime.evolution_stop_requested):
            if (
                runtime.reader.read().battle_state
                or not runtime.reader.read_input_readiness().ready
            ):
                raise context.RedGoalContextError("evolution reserve requires a safe boundary")
            raise EvolutionSettlementReserveReached(battles, heals)

    def train_quantum(
        actions: CountingExecutor,
        source_id: int,
        target_id: int,
        choice_state: dict[str, object] | None = None,
    ) -> BoundedEvolutionTrainingResult:
        check_settlement_reserve()
        prepare_native_training_center(runtime, world, actions)
        initial_heals = restore_native_center_party(runtime, actions)
        trainee = next(
            (m for m in runtime.adapter.observe().party.members if m.species_id == source_id), None
        )
        if trainee is None:
            raise context.RedGoalContextError("native training lost its in-party precursor")
        current = runtime.adapter.observe()
        current_trainee_xp = observe_trainee_xp(source_id)
        if choice_state is not None:
            initial_trainee_xp = choice_state.setdefault(
                "trainee_initial_xp", current_trainee_xp
            )
            if not isinstance(initial_trainee_xp, int):
                initial_trainee_xp = current_trainee_xp
        else:
            initial_trainee_xp = current_trainee_xp
        venues = supported_venues(current)
        if not venues:
            if (
                helper_xp_guard is not None
                and choice_state is not None
                and choice_state.get("helper_xp_admission_seen", False)
                and type(initial_trainee_xp) is int
                and type(current_trainee_xp) is int
                and current_trainee_xp > initial_trainee_xp
                and current.raw.battle_state == 0
                and current.input_ready
                and not runtime.emulator.pressed_buttons
                and all(member.hp > 0 for member in current.party.members)
            ):
                blocked = helper_exclusions(current) - helper_exclusions(
                    current, diagnostic_headroom=True
                )
                # A diagnostic counterquote can explain a pause, never authorize input.
                if blocked and supported_venues(current, diagnostic_headroom=True):
                    raise EvolutionHelperXPExhausted(
                        0,
                        initial_heals,
                        frozenset(blocked),
                        **xp_kwargs(initial_trainee_xp, current_trainee_xp),
                    )
            raise context.RedGoalContextError(
                "no cartridge venue permits safe shared-experience evolution"
            )
        if helper_xp_guard is not None and choice_state is not None:
            choice_state["helper_xp_admission_seen"] = True
        if venue_model is not None:
            initial_heals += _restore_native_cave_venue_resources(
                runtime,
                actions,
                source_id=source_id,
                venues=venues,
                encounters=wild_tables(world.rom),
                excluded_helper_species=helper_exclusions(runtime.adapter.observe()),
            )
        venue_observation = None
        if venue_model is not None or observe_venue_decision is not None:
            if choice_state is None:
                raise context.RedGoalContextError(
                    "native venue decision requires action-scoped state"
                )
            venue_observation = replace(
                runtime.adapter.observe(), party=PokemonRedPartyReader(runtime.emulator).read()
            )
        if (
            observe_venue_decision is not None
            and choice_state is not None
            and not choice_state.get("venue_observation_recorded", False)
        ):
            before_observer = (
                actions.actions_executed,
                runtime.emulator.frame_count,
                runtime.emulator.pressed_buttons,
                runtime.emulator.save_state_bytes(),
            )
            observe_venue_decision(venue_observation, venues, source_id, target_id)
            if before_observer != (
                actions.actions_executed,
                runtime.emulator.frame_count,
                runtime.emulator.pressed_buttons,
                runtime.emulator.save_state_bytes(),
            ):
                raise context.RedGoalContextError("native venue observer changed execution state")
            choice_state["venue_observation_recorded"] = True
        if venue_model is not None:
            if venue_model_sha256 is None or choice_state is None:
                raise context.RedGoalContextError(
                    "native venue model lacks declared identity or state"
                )
            from .red_native_venue_geometry import quote_native_evolution_venue_geometry

            if "venue_identity" not in choice_state:
                tables = wild_tables(world.rom)
                exclusions = helper_exclusions(venue_observation)
                quoted_venues = venues
                venues = live_native_evolution_venues(
                    venue_observation.party, source_id, venues, tables, exclusions
                )
                record = getattr(actions, "record_diagnostic_event", None)
                if callable(record) and venues != quoted_venues:
                    record("native_evolution_resource_recheck", dict(
                        recoverable_map_ids=[venue.map_id for venue in quoted_venues],
                        live_map_ids=[venue.map_id for venue in venues],
                    ))
                if not venues:
                    if not venue_observation.input_ready or venue_observation.raw.battle_state:
                        raise context.RedGoalContextError("helper resource pause requires settled control")
                    raise EvolutionVenueExhausted(0, initial_heals)

            geometry_quotes = (
                quote_native_evolution_venue_geometry(runtime, world, venue_observation, venues)
                if len(venues) > 1 and "venue_identity" not in choice_state
                else None
            )
            selected = select_native_evolution_model_venue(
                venue_observation,
                rom=world.rom,
                source_id=source_id,
                target_id=target_id,
                venues=venues,
                model=venue_model,
                model_sha256=venue_model_sha256,
                choice_state=choice_state,
                actions=actions,
                excluded_helper_species=helper_exclusions(venue_observation),
                allow_guarded_escapes=allow_guarded_venue_escapes,
                allow_direct_evolution=allow_direct_evolution,
                geometry_quotes=geometry_quotes,
                **({"compare_recipient_yield": True} if compare_recipient_yield else {}),
            )
            venues = (selected,)
        else:
            # A higher encounter level alone does not justify travel. Keep a
            # currently executable safe venue for this bounded quantum; otherwise
            # the historical trainer may invoke a transition from an unsupported
            # field boundary. This is local continuity, not a learned venue policy.
            current_raw = runtime.reader.read()
            local_venues = tuple(
                venue
                for venue in venues
                if venue.is_in_map(current_raw) or venue.is_in_center(current_raw)
            )
            if local_venues:
                # A stronger remote band is not a transport capability. Retain the
                # existing executable local inventory before applying the preference.
                venues = local_venues
            if prefer_highest_supported_venue:
                venues = (max(venues, key=lambda v: v.band.maximum_encounter_level),)
        tables = wild_tables(world.rom)
        try:
            _, battles, heals = context.run_red_team_balancing(
                actions,
                runtime.reader,
                runtime.emulator,
                policy=replace(context.MANSION_TEAM_POLICY, max_battles=32, max_steps=2_000),
                venues=venues,
                intent=context.MANSION_BALANCED_TEAM_TRAINING_INTENT,
                flee_timing=context.MANSION_TRAINING_FLEE_TIMING,
                hideout_timing=context.DEFAULT_HIDEOUT_TIMING,
                flee_func=cast(Callable[..., None], context._flee),
                volatile_enemy_species=context.MANSION_VOLATILE_ENEMY_SPECIES,
                escort_enemy_species=context.MANSION_ESCORT_ENEMY_SPECIES,
                max_consecutive_flees=context.MANSION_MAX_CONSECUTIVE_FLEES,
                cancel_interval=context.MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
                evolution_target=(source_id, target_id),
                allow_direct_evolution=allow_direct_evolution,
                collection_shared_experience=True,
                **(
                    {"recover_collection_faints": True}
                    if getattr(runtime, "evolution_training_faint_recovery", False)
                    else {}
                ),
                collection_encounters={venue.map_id: tables[venue.map_id] for venue in venues},
                excluded_collection_helper_species=excluded_helper_species,
                evolution_battle_quantum=4,
                evolution_stop_requested=runtime.evolution_stop_requested,
                report_label="native bounded collection evolution",
                checkpoint_count=1,
                **(
                    {"collection_helper_xp_guard": helper_xp_guard}
                    if helper_xp_guard is not None
                    else {}
                ),
                **native_evolution_training_diagnostics(actions),
            )
        except EvolutionHelperXPExhausted as paused:
            final_trainee_xp = observe_trainee_xp(source_id)
            if (
                type(initial_trainee_xp) is not int
                or type(final_trainee_xp) is not int
                or final_trainee_xp <= initial_trainee_xp
            ):
                raise context.RedGoalContextError(
                    "helper headroom pause requires verified trainee XP progress"
                ) from paused
            raise EvolutionHelperXPExhausted(
                paused.battles,
                paused.healing_trips + initial_heals,
                paused.blocked_helpers,
                **xp_kwargs(initial_trainee_xp, final_trainee_xp),
            ) from paused
        except EvolutionTrainingPaused as paused:
            final_trainee_xp = observe_trainee_xp(source_id)
            record = getattr(actions, "record_diagnostic_event", None)
            if callable(record):
                record(
                    "wild_training_pause",
                    dict(
                        actor="rule_based_support",
                        source="native_level_evolution",
                        error_type=type(paused).__name__,
                        battles_completed=paused.battles,
                        healing_trips=paused.healing_trips + initial_heals,
                    ),
                )
            # Nursing before the inner trainer belongs to this quantum too.
            # Preserve reserve/wall subtypes so the outer report keeps its cause.
            raise type(paused)(
                paused.battles,
                paused.healing_trips + initial_heals,
                **xp_kwargs(initial_trainee_xp, final_trainee_xp),
            ) from paused
        final_trainee_xp = observe_trainee_xp(source_id, target_id)
        return BoundedEvolutionTrainingResult(
            battles,
            heals + initial_heals,
            **xp_kwargs(initial_trainee_xp, final_trainee_xp),
        )

    def train(
        actions: CountingExecutor,
        source_id: int,
        target_id: int,
    ) -> BoundedEvolutionTrainingResult:
        # The outer player action/frame limit is never reset between quanta.
        # Diagnostic callers retain the original single-quantum interface.
        choice_state: dict[str, object] = {}
        if maximum_quanta == 1:
            return train_quantum(actions, source_id, target_id, choice_state)
        source = red_species_ref(red_internal_species_number(source_id))
        target = red_species_ref(red_internal_species_number(target_id))
        initial = runtime.adapter.observe()
        initial_story = runtime.adapter.graph.completed_ids(initial.game_state)
        counts = Counter(s.species_ref for s in initial.collection_observation.specimens)
        expected = counts.copy()
        expected[source] -= 1
        expected[target] += 1
        if not allowed(initial):
            raise context.RedGoalContextError(
                "registered evolution lacks an eligible unreserved precursor"
                if registration is not None
                else "complete evolution must retain its precursor"
            )
        started = time.monotonic()
        battles = heals = 0
        for _ in range(maximum_quanta):
            check_settlement_reserve(battles, heals)
            if time.monotonic() - started >= maximum_wall_seconds:
                if (
                    runtime.reader.read().battle_state
                    or not runtime.reader.read_input_readiness().ready
                ):
                    raise context.RedGoalContextError(
                        "evolution wall stop requires settled control"
                    )
                raise EvolutionWallLimitReached(battles, heals)
            previous = next(
                m
                for m in PokemonRedPartyReader(runtime.emulator).read().members
                if m.species_id == source_id
            )
            try:
                result = train_quantum(actions, source_id, target_id, choice_state)
                battles += result.battles_completed
                heals += result.healing_trips
            except EvolutionVenueExhausted as paused:
                # A no-win escape horizon is an ordinary failed goal, with all
                # metered work retained. Do not demand XP progress or retry the
                # same venue inside this selected action.
                raise EvolutionVenueExhausted(
                    battles + paused.battles,
                    heals + paused.healing_trips,
                ) from paused
            except (EvolutionSettlementReserveReached, EvolutionMovementLimitReached) as paused:
                raise type(paused)(
                    battles + paused.battles,
                    heals + paused.healing_trips,
                ) from paused
            except EvolutionHelperXPExhausted as paused:
                raise EvolutionHelperXPExhausted(
                    battles + paused.battles, heals + paused.healing_trips, paused.blocked_helpers
                ) from paused
            except EvolutionTrainingPaused as paused:
                battles += paused.battles
                heals += paused.healing_trips
            after = runtime.adapter.observe()
            observed = Counter(s.species_ref for s in after.collection_observation.specimens)
            if registration is not None:
                registration.registered(after.collection_observation)
            if (
                observed not in (counts, expected)
                or runtime.adapter.graph.completed_ids(after.game_state) != initial_story
                or any(m.hp <= 0 for m in after.party.members)
                or runtime.reader.read().battle_state != 0
                or not runtime.reader.read_input_readiness().ready
            ):
                raise context.RedGoalContextError("complete evolution changed collection or safety")
            if observed == expected:
                if registration is not None and not registration.verify_evolution(
                    initial.collection_observation,
                    after.collection_observation,
                    source,
                    target,
                ):
                    raise context.RedGoalContextError("complete evolution lost registration")
                if retain_quantum is not None:
                    retain_quantum()
                return BoundedEvolutionTrainingResult(battles, heals)
            current = next(
                m
                for m in PokemonRedPartyReader(runtime.emulator).read().members
                if m.species_id == source_id
            )
            if (
                previous.experience is None
                or current.experience is None
                or current.experience <= previous.experience
            ):
                raise context.RedGoalContextError("complete evolution made no verified XP progress")
            if venue_model is not None and current.level > previous.level:
                # Keep this committed action and exact trainee. Only a genuine
                # level change expires the venue; unchanged quanta retain it.
                # The next quantum uses the existing full inventory, resource
                # gates, current geometry and frozen greedy selector.
                choice_state.pop("venue_identity", None)
            if retain_quantum is not None:
                retain_quantum()
        raise EvolutionQuantumLimitReached(battles, heals, maximum_quanta)

    def train_with_xp(
        actions: CountingExecutor,
        source_id: int,
        target_id: int,
    ) -> BoundedEvolutionTrainingResult:
        initial_xp = observe_trainee_xp(source_id)
        try:
            result = train(actions, source_id, target_id)
        except EvolutionTrainingPaused as paused:
            if paused.trainee_initial_xp is not None:
                raise
            terminal_xp = observe_trainee_xp(source_id)
            xp_data = xp_kwargs(initial_xp, terminal_xp)
            if not xp_data:
                raise
            if isinstance(paused, EvolutionHelperXPExhausted):
                raise EvolutionHelperXPExhausted(
                    paused.battles,
                    paused.healing_trips,
                    paused.blocked_helpers,
                    **xp_data,
                ) from paused
            if isinstance(paused, EvolutionQuantumLimitReached):
                raise EvolutionQuantumLimitReached(
                    paused.battles,
                    paused.healing_trips,
                    paused.maximum_quanta,
                    **xp_data,
                ) from paused
            raise type(paused)(
                paused.battles,
                paused.healing_trips,
                **xp_data,
            ) from paused
        if result.trainee_initial_xp is not None:
            return result
        terminal_xp = observe_trainee_xp(source_id, target_id)
        return BoundedEvolutionTrainingResult(
            result.battles_completed,
            result.healing_trips,
            **xp_kwargs(initial_xp, terminal_xp),
        )

    def partial_report(paused: EvolutionTrainingPaused) -> GoalExecutionReport:
        # Final verification independently observes the collection. A partial
        # quantum never carries an exact-evolution or success assertion.
        zero_progress = {}
        xp = paused.xp_dict()
        if (type(paused) is EvolutionSettlementReserveReached and paused.battles == 0
                and xp.get("trainee_xp_gained") == 0 and xp):
            party_reader = PokemonRedPartyReader(runtime.emulator)
            refs = party_reader.preparation_specimen_refs()
            trainees = [member for member in party_reader.read().members
                if red_species_ref(red_internal_species_number(member.species_id))
                == spec.parameters["source_species_ref"]]
            if len(trainees) == 1:
                zero_progress = dict(zero_progress_evolution=True,
                    zero_progress_trainee_ref=refs[trainees[0].slot - 1])
        return GoalExecutionReport(
            0,
            0,
            {
                **zero_progress,
                "schema": "pokemon.red.native-evolution-partial.v1",
                "bounded": True,
                "evolution_partial": True,
                "source_species_ref": spec.parameters["source_species_ref"],
                "target_species_ref": spec.parameters["target_species_ref"],
                "settlement_reserve_reached": isinstance(paused, EvolutionSettlementReserveReached),
                "wall_limit_reached": isinstance(paused, EvolutionWallLimitReached),
                **(
                    {"training_movement_limit_reached": True}
                    if type(paused) is EvolutionMovementLimitReached
                    else {}
                ),
                **(
                    {"helper_xp_headroom_exhausted": True}
                    if isinstance(paused, EvolutionHelperXPExhausted)
                    else {}
                ),
                **(
                    {
                        "training_venue_exhausted": True,
                        "no_verified_win_in_quantum": True,
                        "no_verified_win": paused.battles == 0,
                    }
                    if isinstance(paused, EvolutionVenueExhausted)
                    else {}
                ),
                **(
                    {
                        "quantum_limit_reached": True,
                        "completed_training_quanta": paused.maximum_quanta,
                        "maximum_training_quanta": paused.maximum_quanta,
                    }
                    if isinstance(paused, EvolutionQuantumLimitReached)
                    else {}
                ),
                "completed_training_battles": paused.battles,
                "healing_trips": paused.healing_trips,
                **paused.xp_dict(),
            },
        )

    def resume(source_id: int, target_id: int, actions: CountingExecutor) -> GoalExecutionReport:
        before = runtime.adapter.observe()
        if (
            not readiness(before).executable
            or before.party.species_ids().count(source_id) != 1
            or red_species_ref(red_internal_species_number(source_id))
            != spec.parameters["source_species_ref"]
            or red_species_ref(red_internal_species_number(target_id))
            != spec.parameters["target_species_ref"]
        ):
            raise context.RedGoalContextError("resumed evolution lost its unique declared trainee")
        settlement_runtime = bind_no_loan_evolution_roster(runtime)
        action_start, frame_start = actions.actions_executed, runtime.emulator.frame_count
        training_error = None
        try:
            result = train_with_xp(actions, source_id, target_id)
            report = GoalExecutionReport(
                0,
                0,
                {
                    "bounded": True,
                    "completed_training_battles": result.battles_completed,
                    "healing_trips": result.healing_trips,
                    **result.xp_dict(),
                },
            )
        except EvolutionTrainingPaused as paused:
            report = partial_report(paused)
        except BaseException as error:
            training_error = error
            raise
        finally:
            settlement = (
                settle_native_evolution(settlement_runtime, actions)
                if training_error is None
                else settle_native_evolution(
                    settlement_runtime, actions, training_error=training_error
                )
            )
        return replace(
            report,
            actions_executed=actions.actions_executed - action_start,
            frames_executed=runtime.emulator.frame_count - frame_start,
            evidence={
                **report.evidence,
                **settlement,
                **(
                    {"registration_policy_sha256": registration.sha256}
                    if registration is not None
                    else {}
                ),
            },
        )

    def execute(
        request: context.RedBoxedLevelEvolutionGoalRequest,
        actions: CountingExecutor,
    ) -> GoalExecutionReport:
        before = runtime.adapter.observe()
        if not allowed(before):
            raise context.RedGoalContextError(
                "registered evolution lacks an eligible unreserved precursor"
                if registration is not None
                else "native evolution requires two retained precursors"
            )
        if not readiness(before).executable:
            raise context.RedGoalContextError("native evolution training capability is unavailable")
        if (
            context._RedTeamGoalProvider(runtime, spec, actions)._boxed_evolution_request(before)
            != request
        ):
            raise context.RedGoalContextError(
                "native evolution storage request changed before input"
            )
        from .red_player_party_guard import RedPlayerPartyGuard
        from .red_player_party_loan import _stock

        settlement_runtime = bind_boxed_evolution_roster(runtime, request)
        guard = getattr(runtime.adapter, "party_guard", None)
        original_trainee = initial_stock = None
        if isinstance(guard, RedPlayerPartyGuard) and guard.storage_reader is not None:
            matches = tuple(
                specimen for specimen in runtime.reader.read_box_specimen_identities()
                if specimen.box_index == request.current_box_index
                and specimen.box_slot == request.precursor_box_slot
                and specimen.species_id == request.precursor_internal_species_id
            )
            if len(matches) == 1:
                original_trainee = matches[0]
                initial_stock = _stock(runtime)
        retained_helpers = tuple(
            replace(member, slot=index + 1)
            for index, member in enumerate(
                m for m in before.party.members if m.slot != request.deposit_party_slot
            )
        )
        if not supported_venues(replace(before, party=PartyObservation(retained_helpers))):
            raise context.RedGoalContextError("storage preparation would remove the safe finisher")
        action_start = actions.actions_executed
        frame_start = runtime.emulator.frame_count
        prepare_native_training_center(runtime, world, actions)
        traversal = Gen1TraversalObserver(runtime.reader)
        start = traversal.observe()
        pc_replanner = native_evolution_pc_replanner(runtime, world, actions)
        nurse_prepared = False
        try:
            to_pc = world.plan_feasible_to_map(start, start.map_id, goal_at=(4, 13))
        except RoutePlanningError:
            from .route_executor import ReplanRequest

            restore_native_center_party(runtime, actions)
            finish_center_dialogue(actions, runtime.reader)
            nurse_prepared = True
            start = traversal.observe()
            initial_pc_replan = native_evolution_pc_replanner(
                runtime, world, actions, allow_offscreen_approach=True
            )
            to_pc = initial_pc_replan(ReplanRequest(start, start.map_id, (4, 13), {}, 1))
            start = traversal.observe()
            world_now = world.with_current_observation(runtime.reader)
        else:
            world_now = world
        # This is a route-plan start, not a fabricated game observation or offer.
        pc_start = replace(start, at=(4, 13))
        to_training = world_now.plan_feasible_to_map(pc_start, start.map_id, goal_at=(3, 3))
        from pokemon_red_completion.red_resource_goal_router import _walking_plan

        if not _walking_plan(to_pc) or not _walking_plan(to_training):
            raise RoutePlanningError("native evolution requires walking-only PC access")
        # Plan before any input. Healing is declared skill preparation, not a
        # model-selected outcome; all costs stay inside the outer goal budget.
        if not nurse_prepared:
            restore_native_center_party(runtime, actions)
            # A checkpoint may still contain the already-healed farewell screen.
            finish_center_dialogue(actions, runtime.reader)
        # The legacy engine binds Blastoise as its escort. Early native play
        # instead binds a real remaining finisher, after the existing venue
        # coverage, retained-helper, walking-route and Center checks. No empty
        # or guessed escort may disable the engine's party boundary proof.
        escort_id = context.BLASTOISE_SPECIES_ID
        current = runtime.adapter.observe()
        if escort_id not in current.party.species_ids():
            remaining = PartyObservation(
                tuple(
                    replace(member, slot=index + 1)
                    for index, member in enumerate(
                        m for m in current.party.members if m.slot != request.deposit_party_slot
                    )
                )
            )
            retained = replace(current, party=remaining)
            venues = supported_venues(retained)
            finishers = tuple(
                helper
                for venue in venues
                if (
                    helper := collection_finisher(
                        remaining,
                        request.precursor_internal_species_id,
                        context.MANSION_TEAM_POLICY,
                        enemy_level=venue.band.rare_maximum_encounter_level
                        or venue.band.maximum_encounter_level,
                        excluded_helper_species=helper_exclusions(retained),
                    )
                )
                is not None
            )
            if not finishers:
                raise context.RedGoalContextError(
                    "boxed evolution has no observed retained training escort"
                )
            escort_id = max(finishers, key=lambda member: member.level).species_id
        identity_document = {
            "schema": "pokemon.red.native-boxed-evolution.v2",
            "profile": runtime.profile.profile_sha256,
            "max_battles": 32,
            "max_steps": 2_000,
            "direct_evolution": True,
            "collection_shared_experience": True,
            "battle_quantum": 4,
            "maximum_quanta": maximum_quanta,
            "pc_facing": "up",
        }
        if escort_id != context.BLASTOISE_SPECIES_ID:
            identity_document["escort_internal_species_id"] = escort_id
        if maximum_wall_seconds != 600:
            identity_document["maximum_wall_seconds"] = maximum_wall_seconds
        if registration is not None:
            identity_document["registration_policy_sha256"] = registration.sha256
        if allow_guarded_venue_escapes:
            identity_document["guarded_venue_escapes"] = True
        if training_venues is not None:
            identity_document["declared_venues"] = [v.band.identity for v in training_venues]
        if prefer_highest_supported_venue:
            identity_document["prefer_highest_supported_venue"] = True
        if venue_model is not None:
            identity_document["venue_model_sha256"] = venue_model_sha256
            identity_document["venue_choice_protocol"] = (
                "native-recipient-yield-comparison-v1" if compare_recipient_yield else "native-full-evolution-venue-v1"
            )
        identity = canonical_sha256(identity_document)

        pc_access: SemanticPCBoundaryAccess = SemanticVenueRouteBinding(to_pc, identity)
        preparation: dict[str, object] = {}
        if request.current_box_index != before.collection_observation.current_box_index:
            from pokemon_red_completion.red_native_evolution_box_access import (
                prepare_evolution_box,
            )

            pc_access, preparation = prepare_evolution_box(
                runtime,
                world,
                actions,
                traversal,
                to_pc,
                request,
            )
        executor = RedGoalBoxedEvolutionExecutor(
            reset_state_sha256=runtime.capture.state_sha256,
            route_to_pc=pc_access,
            route_to_training=SemanticVenueRouteBinding(to_training, identity),
            training_binding_sha256=identity,
            reader=runtime.reader,
            traversal_observer=traversal,
            observe_collection=lambda: runtime.adapter.observe().collection_observation,
            train_evolution=lambda source_id, target_id: train_with_xp(
                actions, source_id, target_id
            ),
            emulator=runtime.emulator,
            replanner=pc_replanner,
            pc_facing="up",
            registration_policy=registration,
            allow_declared_blastoise_loan=request.declared_blastoise_loan,
            escort_internal_species_id=escort_id,
        )
        venue_exhausted = False
        try:
            report = executor(request, actions)
        except EvolutionTrainingPaused as paused:
            report = partial_report(paused)
            venue_exhausted = type(paused) is EvolutionVenueExhausted and paused.battles == 0
        finally:
            settlement = settle_native_evolution(settlement_runtime, actions)
        if venue_exhausted and initial_stock is not None:
            evidence = dict(report.evidence)
            trainee_identity = (
                original_trainee.preparation_ref, original_trainee.species_id,
                original_trainee.level, original_trainee.experience,
            )
            after = runtime.adapter.observe()
            returned = tuple(
                specimen for specimen in runtime.reader.read_box_specimen_identities()
                if specimen.preparation_ref == original_trainee.preparation_ref
            )
            if (
                settlement.get("retained_active_roster_restored") is True
                and initial_stock[trainee_identity] == 1
                and len(returned) == 1
                and returned[0].species_id == original_trainee.species_id
                and returned[0].experience == original_trainee.experience
                and evidence.get("trainee_initial_xp") == evidence.get("trainee_terminal_xp")
                == original_trainee.experience
                and evidence.get("trainee_xp_gained") == 0
                and after.input_ready and not after.raw.battle_state
                and not runtime.emulator.pressed_buttons
                and before.raw.bag_items == after.raw.bag_items
                and before.raw.player_money == after.raw.player_money
                and before.collection_observation.owned_species == after.collection_observation.owned_species
                and _stock(runtime) == initial_stock
            ):
                evidence.update(
                    zero_progress_evolution=True,
                    zero_progress_trainee_ref=original_trainee.preparation_ref,
                    boxed_no_win_venue=dict(
                        schema="pokemon.red.boxed-no-win-venue.v1",
                        identical_stock_sha256=canonical_sha256(sorted(initial_stock.items())),
                        trainee_boxed_before_and_after=True,
                        trainee_experience=original_trainee.experience,
                    ),
                )
                report = replace(report, evidence=evidence)
        if registration is not None:
            evidence = dict(report.evidence)
            evidence.pop("required_living_preserved", None)
            evidence["registration_policy_sha256"] = registration.sha256
            report = replace(report, evidence=evidence)
        return replace(
            report,
            actions_executed=actions.actions_executed - action_start,
            frames_executed=runtime.emulator.frame_count - frame_start,
            evidence={**report.evidence, **preparation, **settlement},
        )

    return replace(
        runtime,
        boxed_level_evolution_executor=execute,
        boxed_level_evolution_readiness=readiness,
        party_level_evolution_executor=resume,
        party_level_evolution_start_allowed=(
            (
                lambda observation: bool(
                    not observation.raw.battle_state
                    and observation.input_ready
                    and any(
                        v.is_in_map(observation.raw) or v.is_in_center(observation.raw)
                        for v in training_venues
                    )
                    and observation.party.species_ids().count(
                        red_internal_species_id(
                            red_species_number(context._text(spec.parameters, "source_species_ref"))
                        )
                    )
                    == 1
                )
            )
            if training_venues is not None
            else None
        ),
    )
