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
from pokemon_red_completion.red_training_ground_route import RedVermilionGroundTransition
from pokemon_red_completion.collection import CollectionLocation
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_cartridge import wild_tables
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind, GoalUnavailableReason
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.observation import MapId, RawGameState
from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.party_development_outcome_learning import (
    PartyDevelopmentOutcomeModel, canonical_party_development_outcome_model_sha256,
)
from pokemon_red_completion.party_development_rank import PARTY_DEVELOPMENT_WORKLOAD_FEATURE_SCHEMA_ID
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
from pokemon_red_completion.red_goal_boxed_evolution import RedGoalBoxedEvolutionExecutor
from pokemon_red_completion.red_goal_skills import (
    RedCenterRestoreGoalProvider,
    finish_center_dialogue,
    prepare_center_departure,
)
from pokemon_red_completion.red_party import PokemonRedPartyReader
from pokemon_red_completion.red_team_training import (
    COLLECTION_UNSUPPORTED_MOVE_EFFECTS,
    EvolutionSettlementReserveReached,
    EvolutionTrainingPaused,
    EvolutionVenueExhausted,
    collection_escape_escort,
    collection_finisher,
    evolution_reserve_requested,
)
from pokemon_red_completion.red_trainer_evolution import level_evolution_edges
from pokemon_red_completion.route_plan import RoutePlanningError
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld
from pokemon_red_completion.training_venue import TrainingVenue


class EvolutionWallLimitReached(EvolutionTrainingPaused):
    """A counted safe pause, not an unreported generic training exception."""


class EvolutionQuantumLimitReached(EvolutionTrainingPaused):
    """All declared quanta finished with verified XP and settled field control."""

    def __init__(self, battles: int, healing_trips: int, maximum_quanta: int) -> None:
        super().__init__(battles, healing_trips)
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


def native_evolution_pc_replanner(runtime, world, actions):
    """Wait for an observed moving NPC on a selected Center PC or return stance.

    No occupied tile is ignored. Once it vacates, fresh native occupancy and
    every other route constraint still apply. Static/unrecognized blockers keep
    the original planner failure, and waiting shares the caller's input budget.
    """
    from .actions import MacroAction, MacroActionKind
    from .red_goal_skills import _POKEMON_CENTER_MAPS

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
        if len(objects) != 1 or not objects[0].moving:
            return world.with_current_observation(runtime.reader).replanner()(request)
        before = runtime.adapter.observe()
        if (
            not before.input_ready
            or before.raw.battle_state
            or (before.raw.map_id, before.raw.player_y, before.raw.player_x)
            != (request.current.map_id, *request.current.at)
        ):
            raise context.RedGoalContextError("PC wait requires the actual ready route boundary")
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
            if request.goal_at not in live.occupied:
                blocked = dict(request.blocked)
                blocked[request.goal_map] = (
                    blocked.get(request.goal_map, frozenset()) - {request.goal_at}
                ) | live.occupied
                return world.with_current_observation(runtime.reader).replanner()(
                    replace(request, current=live, blocked=blocked)
                )
        raise context.RedGoalContextError("moving PC blocker did not vacate within its bound")

    return replan


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
    route_options = {"replanner": world.replanner()} if live_route_replanning else {}
    report = execute_route(route, actions, traversal, limits=_ROUTE_LIMITS, **route_options)
    after = runtime.adapter.observe()
    if (
        not report.passed
        or (after.raw.map_id, after.raw.player_x, after.raw.player_y) != (before.raw.map_id, 3, 3)
        or after.raw.battle_state
        or not after.input_ready
        or after.party != before.party
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
    from pokemon_red_completion.red_team_training import _PauseForTeamTrainingRecovery

    catalog = PokemonRedBattleCatalog()
    if state.active_party_species_id is None or state.enemy_species_id is None:
        raise _PauseForTeamTrainingRecovery
    own = catalog.resolve_species(pokemon_red_species_ref(state.active_party_species_id)).types
    enemy = catalog.resolve_species(pokemon_red_species_ref(state.enemy_species_id)).types
    candidates = []
    for index, (move_id, pp) in enumerate(
        zip(state.battler_moves or (), state.battler_pp or (), strict=True)
    ):
        if not move_id or pp <= 0 or index + 1 == (state.player_disabled_move_slot or 0):
            continue
        move = catalog.resolve_move(pokemon_red_move_ref(move_id))
        if move.power <= 0 or move.effect_flags.intersection(COLLECTION_UNSUPPORTED_MOVE_EFFECTS):
            continue
        effectiveness = catalog.type_effectiveness(move.type_name, enemy)
        score = move.power * move.accuracy * effectiveness * (1.5 if move.type_name in own else 1.0)
        if score > 0:
            candidates.append((score, -(index + 1)))
    if not candidates:
        raise _PauseForTeamTrainingRecovery
    return -max(candidates)[1]


def native_training_move_guard(state: RawGameState) -> None:
    """Keep the per-turn health gate without an old party's preferred slots."""
    from pokemon_red_completion.red_team_training import _PauseForTeamTrainingRecovery

    hp, maximum = state.battler_hp, state.battler_max_hp
    if (
        hp is None
        or maximum is None
        or maximum <= 0
        or (hp / maximum <= context.MANSION_TEAM_POLICY.retreat_hp_ratio)
    ):
        raise _PauseForTeamTrainingRecovery
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
        return {}
    from .red_player_party_guard import RedPlayerPartyGuard

    guard = getattr(runtime.adapter, "party_guard", None)
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
            record("native_evolution_settlement_deferred", {
                "actor": "rule_based_support",
                "training_error_type": type(training_error).__name__,
                "battle_active": bool(before.raw.battle_state),
                "input_ready": before.input_ready,
                "model_queries": 0,
                "settlement_executed": False,
            })
        return {"retained_active_roster_restoration_deferred": True}
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
        or model.feature_schema_id != PARTY_DEVELOPMENT_WORKLOAD_FEATURE_SCHEMA_ID
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

    def __post_init__(self):
        if type(self.allow_direct_evolution) is not bool:
            raise ValueError("configured evolution mode requires an explicit boolean")
        validate_native_evolution_venue_model(self.model, self.model_sha256)
        if self.model is None or (
            type(self.training_venues) is not tuple or len(self.training_venues) < 2
            or any(not isinstance(venue, TrainingVenue) for venue in self.training_venues)
            or len({venue.band.identity for venue in self.training_venues}) != len(self.training_venues)
        ):
            raise ValueError("configured native venue policy needs distinct declared venues")


def select_native_evolution_model_venue(
    observation, *, rom: bytes, source_id: int, target_id: int,
    venues: tuple[TrainingVenue, ...], model: PartyDevelopmentOutcomeModel,
    model_sha256: str, choice_state: dict[str, object], actions,
    excluded_helper_species: frozenset[int], allow_guarded_escapes: bool,
) -> TrainingVenue:
    """Select once per action, then recheck the exact retained venue each quantum."""
    from pokemon_red_completion.red_party_development_adapter import build_native_evolution_venue_menu
    action_scope = (source_id, target_id, model_sha256)
    if "venue_identity" in choice_state:
        if choice_state.get("action_scope") != action_scope:
            raise context.RedGoalContextError("native venue choice state belongs to another action or model")
        matches = tuple(venue for venue in venues
                        if venue.band.identity == choice_state["venue_identity"])
        if len(matches) != 1:
            raise EvolutionVenueExhausted(0, 0)
        return matches[0]
    if not venues:
        raise context.RedGoalContextError("native venue model has no executable inventory")
    model_selected = len(venues) > 1
    document = None
    snapshot_sha256 = None
    if model_selected:
        trainee = next((member for member in observation.party.members
                        if member.species_id == source_id), None)
        if trainee is None:
            raise context.RedGoalContextError("native venue model lost the bound trainee")
        menu = build_native_evolution_venue_menu(
            observation, rom=rom, trainee=trainee, target_species_id=target_id,
            policy=context.MANSION_TEAM_POLICY, venues=venues,
            excluded_helper_species=excluded_helper_species,
            allow_guarded_escapes=allow_guarded_escapes, resources=True,
        )
        if tuple(menu.bindings) != tuple(venue.band for venue in venues):
            raise context.RedGoalContextError("native model menu differs from executable venue inventory")
        selected_index = model.predict(menu.candidate_set)
        if (type(selected_index) is not int or selected_index not in range(len(venues))
                or not menu.candidate_available[selected_index]):
            raise context.RedGoalContextError("native venue model selected an illegal binding")
        document = menu.candidate_set.public_dict()
        snapshot_sha256 = menu.semantic_snapshot_sha256
    else:
        selected_index = 0
    selected = venues[selected_index]
    choice_state["venue_identity"] = selected.band.identity
    choice_state["action_scope"] = action_scope
    record = getattr(actions, "record_diagnostic_event", None)
    if callable(record):
        record("native_evolution_venue_choice", dict(
            actor="learned_venue_model" if model_selected else "rule_based_support",
            model_selected=model_selected, model_sha256=model_sha256,
            selected_index=selected_index, selected_venue=selected.band.identity,
            selected_map_id=selected.map_id, candidate_count=len(venues),
            candidate_set=document, semantic_snapshot_sha256=snapshot_sha256,
            decision_lifetime="one-complete-evolution-action",
            nominal_yield_model="unboosted-two-participant-wild-v1",
        ))
    return selected


def _with_native_cave_ground_recovery(venue, world):
    """Keep selected venue transport executable after a PC loan removes Dig."""
    if (
        venue.map_id == int(MapId.POKEMON_MANSION_1F)
        and venue.heal_and_return is context.MANSION_TRAINING_VENUE.heal_and_return
    ):
        from .red_mansion_training_recovery import mansion_native_heal_and_return
        return replace(venue, heal_and_return=partial(
            mansion_native_heal_and_return, world=world, legacy=venue.heal_and_return,
        ))
    if (
        venue.map_id != int(MapId.DIGLETTS_CAVE)
        or venue.heal_and_return is not context.DIGLETTS_CAVE_TRAINING_VENUE.heal_and_return
    ):
        return venue

    def heal_and_return(actions, reader, emulator):
        ground = RedVermilionGroundTransition(rom=world.rom, route_world=world)
        return venue.heal_and_return(
            actions, reader, emulator,
            route_11_recovery=partial(
                _route_11_heal_and_return, ground_transition=ground,
            ),
        )

    return replace(venue, heal_and_return=heal_and_return)




def _mansion_transport_ready(runtime, world, party):
    from .red_mansion_training_recovery import mansion_native_transport_ready
    return mansion_native_transport_ready(runtime, world, party)


def _restore_native_cave_venue_resources(
    runtime, actions, *, source_id, venues, encounters, excluded_helper_species,
) -> int:
    """Nurse the current Cave before resource-checked comparative inference."""
    from pokemon_red_completion.red_team_training import (
        collection_encounter_coverage, execute_evolution_healing_trip,
    )

    before = runtime.adapter.observe()
    if before.raw.map_id != int(MapId.DIGLETTS_CAVE):
        return 0

    def ready(party):
        return all(collection_encounter_coverage(
            party, source_id, context.MANSION_TEAM_POLICY, encounters[venue.map_id],
            resources=True,
            escape_species=(context.MANSION_VOLATILE_ENEMY_SPECIES
                            | context.MANSION_ESCORT_ENEMY_SPECIES),
            excluded_helper_species=excluded_helper_species,
        ) for venue in venues)

    if ready(before.party):
        return 0
    if before.raw.battle_state or not before.input_ready:
        raise context.RedGoalContextError("native Cave resource recovery requires settled control")
    current = tuple(venue for venue in venues if venue.is_in_map(before.raw))
    if len(current) != 1:
        raise context.RedGoalContextError("native Cave resource recovery lacks its current venue")
    execute_evolution_healing_trip(
        actions, runtime.reader, runtime.emulator, current[0].heal_and_return,
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
        raise context.RedGoalContextError("native Cave recovery did not retain stock and restore helper resources")
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
    observe_venue_decision: Callable[[object, tuple[TrainingVenue, ...], int, int], None] | None = None,
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

    def supported_venues(observation: context.RedGoalObservation) -> tuple[TrainingVenue, ...]:
        source_id = cast(str, spec.parameters["source_species_ref"])
        source_internal = red_internal_species_id(red_species_number(source_id))
        party = observation.party
        if source_internal not in party.species_ids() and party.size == 6:
            try:
                request = context._RedTeamGoalProvider(
                    runtime, spec, None
                )._boxed_evolution_request(observation)
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
                move_slot=native_training_move_slot, move_guard=native_training_move_guard
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
            if (
                venue.native_transport_ready is None
                or venue.native_transport_ready(party) is True
            )
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
                excluded_helper_species=excluded_helper_species,
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
                    excluded_helper_species=excluded_helper_species,
                )
                for level, species in tables[venue.map_id]
            )
        )

    def readiness(observation: context.RedGoalObservation) -> context.RedGoalSkillAvailability:
        source = spec.parameters["source_species_ref"]
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
        venues = supported_venues(runtime.adapter.observe())
        if not venues:
            raise context.RedGoalContextError(
                "no cartridge venue permits safe shared-experience evolution"
            )
        if venue_model is not None:
            initial_heals += _restore_native_cave_venue_resources(
                runtime, actions, source_id=source_id, venues=venues,
                encounters=wild_tables(world.rom),
                excluded_helper_species=excluded_helper_species,
            )
        venue_observation = None
        if venue_model is not None or observe_venue_decision is not None:
            if choice_state is None:
                raise context.RedGoalContextError("native venue decision requires action-scoped state")
            venue_observation = replace(
                runtime.adapter.observe(), party=PokemonRedPartyReader(runtime.emulator).read()
            )
        if observe_venue_decision is not None and not choice_state.get("venue_observation_recorded", False):
            before_observer = (
                actions.actions_executed, runtime.emulator.frame_count,
                runtime.emulator.pressed_buttons, runtime.emulator.save_state_bytes(),
            )
            observe_venue_decision(venue_observation, venues, source_id, target_id)
            if before_observer != (
                actions.actions_executed, runtime.emulator.frame_count,
                runtime.emulator.pressed_buttons, runtime.emulator.save_state_bytes(),
            ):
                raise context.RedGoalContextError("native venue observer changed execution state")
            choice_state["venue_observation_recorded"] = True
        if venue_model is not None:
            selected = select_native_evolution_model_venue(
                venue_observation, rom=world.rom, source_id=source_id, target_id=target_id,
                venues=venues, model=venue_model, model_sha256=venue_model_sha256,
                choice_state=choice_state, actions=actions,
                excluded_helper_species=excluded_helper_species,
                allow_guarded_escapes=allow_guarded_venue_escapes,
            )
            venues = (selected,)
        else:
            # A higher encounter level alone does not justify travel. Keep a
            # currently executable safe venue for this bounded quantum; otherwise
            # the historical trainer may invoke a transition from an unsupported
            # field boundary. This is local continuity, not a learned venue policy.
            current = runtime.reader.read()
            local_venues = tuple(
                venue for venue in venues if venue.is_in_map(current) or venue.is_in_center(current)
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
                collection_encounters={venue.map_id: tables[venue.map_id] for venue in venues},
                excluded_collection_helper_species=excluded_helper_species,
                evolution_battle_quantum=4,
                evolution_stop_requested=runtime.evolution_stop_requested,
                report_label="native bounded collection evolution",
                checkpoint_count=1,
                **native_evolution_training_diagnostics(actions),
            )
        except EvolutionTrainingPaused as paused:
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
            raise type(paused)(paused.battles, paused.healing_trips + initial_heals) from paused
        return BoundedEvolutionTrainingResult(battles, heals + initial_heals)

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
                    battles + paused.battles, heals + paused.healing_trips,
                ) from paused
            except EvolutionSettlementReserveReached as paused:
                raise EvolutionSettlementReserveReached(
                    battles + paused.battles,
                    heals + paused.healing_trips,
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
            if retain_quantum is not None:
                retain_quantum()
        raise EvolutionQuantumLimitReached(battles, heals, maximum_quanta)

    def partial_report(paused: EvolutionTrainingPaused) -> GoalExecutionReport:
        # Final verification independently observes the collection. A partial
        # quantum never carries an exact-evolution or success assertion.
        return GoalExecutionReport(
            0,
            0,
            {
                "schema": "pokemon.red.native-evolution-partial.v1",
                "bounded": True,
                "evolution_partial": True,
                "source_species_ref": spec.parameters["source_species_ref"],
                "target_species_ref": spec.parameters["target_species_ref"],
                "settlement_reserve_reached": isinstance(paused, EvolutionSettlementReserveReached),
                "wall_limit_reached": isinstance(paused, EvolutionWallLimitReached),
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
        action_start, frame_start = actions.actions_executed, runtime.emulator.frame_count
        training_error = None
        try:
            result = train(actions, source_id, target_id)
            report = GoalExecutionReport(
                0,
                0,
                {
                    "bounded": True,
                    "completed_training_battles": result.battles_completed,
                    "healing_trips": result.healing_trips,
                },
            )
        except EvolutionTrainingPaused as paused:
            report = partial_report(paused)
        except BaseException as error:
            training_error = error
            raise
        finally:
            settlement = (
                settle_native_evolution(runtime, actions)
                if training_error is None
                else settle_native_evolution(runtime, actions, training_error=training_error)
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
        try:
            to_pc = world.plan_feasible_to_map(start, start.map_id, goal_at=(4, 13))
        except RoutePlanningError:
            from .route_executor import ReplanRequest

            to_pc = pc_replanner(ReplanRequest(start, start.map_id, (4, 13), {}, 1))
        # This is a route-plan start, not a fabricated game observation or offer.
        pc_start = replace(start, at=(4, 13))
        to_training = world.plan_feasible_to_map(pc_start, start.map_id, goal_at=(3, 3))
        from pokemon_red_completion.red_resource_goal_router import _walking_plan

        if not _walking_plan(to_pc) or not _walking_plan(to_training):
            raise RoutePlanningError("native evolution requires walking-only PC access")
        # Plan before any input. Healing is declared skill preparation, not a
        # model-selected outcome; all costs stay inside the outer goal budget.
        restore_native_center_party(runtime, actions)
        # Old checkpoints may contain the already-healed farewell screen. They
        # have no restore offer; explicitly finish that interaction too.
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
                        excluded_helper_species=excluded_helper_species,
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
            identity_document["venue_choice_protocol"] = "native-full-evolution-venue-v1"
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
            train_evolution=lambda source_id, target_id: train(actions, source_id, target_id),
            emulator=runtime.emulator,
            replanner=pc_replanner,
            pc_facing="up",
            registration_policy=registration,
            allow_declared_blastoise_loan=request.declared_blastoise_loan,
            escort_internal_species_id=escort_id,
        )
        try:
            report = executor(request, actions)
        except EvolutionTrainingPaused as paused:
            report = partial_report(paused)
        finally:
            settlement = settle_native_evolution(runtime, actions)
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
                            red_species_number(spec.parameters["source_species_ref"])
                        )
                    )
                    == 1
                )
            )
            if training_venues is not None
            else None
        ),
    )
