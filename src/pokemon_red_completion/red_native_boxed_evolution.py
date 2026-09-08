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
from dataclasses import replace
from typing import cast

from pokemon_red_completion import red_goal_context as context
from pokemon_red_completion.collection import CollectionLocation
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_cartridge import wild_tables
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind, GoalUnavailableReason
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.party import PartyObservation
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
)
from pokemon_red_completion.red_party import PokemonRedPartyReader
from pokemon_red_completion.red_team_training import (
    COLLECTION_UNSUPPORTED_MOVE_EFFECTS,
    EvolutionTrainingPaused,
    collection_finisher,
)
from pokemon_red_completion.route_plan import RoutePlanningError
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld
from pokemon_red_completion.training_venue import TrainingVenue


def restore_native_center_party(
    runtime: context.RedGoalContextRuntime, actions: CountingExecutor,
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
        actions, runtime.reader, runtime.emulator, runtime.adapter,
    ).offer(before)
    if offered.binding is None:
        return 0
    if (before.raw.player_x, before.raw.player_y) == (3, 3):
        face_pc_boundary(actions, runtime.reader, "up")
    report = offered.binding.execute()
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


def bind_native_boxed_evolution(
    runtime: context.RedGoalContextRuntime,
    world: StrategicScenarioRouteWorld,
    *,
    maximum_quanta: int = 1,
    retain_quantum: Callable[[], None] | None = None,
    allow_cross_box: bool = False,
) -> context.RedGoalContextRuntime:
    """Return an isolated runtime; do not mutate a saved observer's old profile."""
    if type(maximum_quanta) is not int or not 1 <= maximum_quanta <= 128:
        raise ValueError("native evolution quantum limit differs")
    if type(allow_cross_box) is not bool:
        raise ValueError("native evolution cross-box mode differs")
    runtime = replace(runtime, boxed_level_evolution_cross_box=allow_cross_box)
    spec = next(s for s in runtime.profile.providers if s.kind is GoalKind.EVOLVE_SPECIES)

    def supported_venues(observation: context.RedGoalObservation) -> tuple[TrainingVenue, ...]:
        source_id = cast(str, spec.parameters["source_species_ref"])
        source_internal = red_internal_species_id(red_species_number(source_id))
        tables = wild_tables(world.rom)
        return tuple(
            replace(
                venue, move_slot=native_training_move_slot, move_guard=native_training_move_guard
            )
            for venue in (
                context.ROUTE_11_TRAINING_VENUE,
                context.DIGLETTS_CAVE_TRAINING_VENUE,
                context.MANSION_TRAINING_VENUE,
            )
            if tables.get(venue.map_id)
            and collection_finisher(
                observation.party,
                source_internal,
                context.MANSION_TEAM_POLICY,
                enemy_level=venue.band.rare_maximum_encounter_level
                or venue.band.maximum_encounter_level,
                resources=False,
            )
            is not None
            and all(
                species not in context.MANSION_VOLATILE_ENEMY_SPECIES
                and species not in context.MANSION_ESCORT_ENEMY_SPECIES
                and collection_finisher(
                    observation.party,
                    source_internal,
                    context.MANSION_TEAM_POLICY,
                    enemy_level=level,
                    enemy_species=species,
                    resources=False,
                )
                is not None
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
        if len(specimens) != 2 or not candidates:
            return context.RedGoalSkillAvailability.unavailable(
                GoalUnavailableReason.NO_LEGAL_TARGET
            )
        if not supported_venues(observation):
            return context.RedGoalSkillAvailability.unavailable(
                GoalUnavailableReason.MISSING_CAPABILITY
            )
        return context.RedGoalSkillAvailability.available()

    def train_quantum(
        actions: CountingExecutor,
        source_id: int,
        target_id: int,
    ) -> BoundedEvolutionTrainingResult:
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
        # A higher encounter level alone does not justify travel. Keep a
        # currently executable safe venue for this bounded quantum; otherwise
        # the historical trainer may invoke a transition from an unsupported
        # field boundary. This is local continuity, not a learned venue policy.
        current = runtime.reader.read()
        local_venues = tuple(
            venue for venue in venues if venue.is_in_map(current) or venue.is_in_center(current)
        )
        if local_venues:
            venues = local_venues
        tables = wild_tables(world.rom)
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
            allow_direct_evolution=True,
            collection_shared_experience=True,
            collection_encounters={venue.map_id: tables[venue.map_id] for venue in venues},
            evolution_battle_quantum=4,
            report_label="native bounded collection evolution",
            checkpoint_count=1,
        )
        return BoundedEvolutionTrainingResult(battles, heals + initial_heals)

    def train(
        actions: CountingExecutor,
        source_id: int,
        target_id: int,
    ) -> BoundedEvolutionTrainingResult:
        # The outer player action/frame limit is never reset between quanta.
        # Diagnostic callers retain the original single-quantum interface.
        if maximum_quanta == 1:
            return train_quantum(actions, source_id, target_id)
        source = red_species_ref(red_internal_species_number(source_id))
        target = red_species_ref(red_internal_species_number(target_id))
        initial = runtime.adapter.observe()
        initial_story = runtime.adapter.graph.completed_ids(initial.game_state)
        counts = Counter(s.species_ref for s in initial.collection_observation.specimens)
        expected = counts.copy()
        expected[source] -= 1
        expected[target] += 1
        if counts[source] != 2 or expected[source] < 1:
            raise context.RedGoalContextError("complete evolution must retain its precursor")
        started = time.monotonic()
        battles = heals = 0
        for _ in range(maximum_quanta):
            if time.monotonic() - started >= 600:
                raise context.RedGoalContextError("complete evolution wall limit reached")
            previous = next(
                m
                for m in PokemonRedPartyReader(runtime.emulator).read().members
                if m.species_id == source_id
            )
            try:
                result = train_quantum(actions, source_id, target_id)
                battles += result.battles_completed
                heals += result.healing_trips
            except EvolutionTrainingPaused as paused:
                battles += paused.battles
                heals += paused.healing_trips
            after = runtime.adapter.observe()
            observed = Counter(s.species_ref for s in after.collection_observation.specimens)
            if (
                observed not in (counts, expected)
                or runtime.adapter.graph.completed_ids(after.game_state) != initial_story
                or any(m.hp <= 0 for m in after.party.members)
                or runtime.reader.read().battle_state != 0
                or not runtime.reader.read_input_readiness().ready
            ):
                raise context.RedGoalContextError("complete evolution changed collection or safety")
            if observed == expected:
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
        raise EvolutionTrainingPaused(battles, heals)

    def partial_report(paused: EvolutionTrainingPaused) -> GoalExecutionReport:
        # Final verification independently observes the collection. A partial
        # quantum never carries an exact-evolution or success assertion.
        return GoalExecutionReport(
            0,
            0,
            {
                "bounded": True,
                "evolution_partial": True,
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
        try:
            result = train(actions, source_id, target_id)
            report = GoalExecutionReport(
                0, 0, {"bounded": True, "completed_training_battles": result.battles_completed}
            )
        except EvolutionTrainingPaused as paused:
            report = partial_report(paused)
        return replace(
            report,
            actions_executed=actions.actions_executed - action_start,
            frames_executed=runtime.emulator.frame_count - frame_start,
        )

    def execute(
        request: context.RedBoxedLevelEvolutionGoalRequest,
        actions: CountingExecutor,
    ) -> GoalExecutionReport:
        before = runtime.adapter.observe()
        source = red_species_ref(red_internal_species_number(request.precursor_internal_species_id))
        if sum(s.species_ref == source for s in before.collection_observation.specimens) != 2:
            raise context.RedGoalContextError("native evolution requires two retained precursors")
        if not readiness(before).executable:
            raise context.RedGoalContextError("native evolution training capability is unavailable")
        if context._RedTeamGoalProvider(runtime, spec, actions)._boxed_evolution_request(
            before
        ) != request:
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
        traversal = Gen1TraversalObserver(runtime.reader)
        start = traversal.observe()
        to_pc = world.plan_feasible_to_map(start, start.map_id, goal_at=(4, 13))
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
        identity = canonical_sha256(
            {
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
        )

        pc_access: SemanticPCBoundaryAccess = SemanticVenueRouteBinding(to_pc, identity)
        preparation: dict[str, object] = {}
        if request.current_box_index != before.collection_observation.current_box_index:
            from pokemon_red_completion.red_native_evolution_box_access import (
                prepare_evolution_box,
            )

            pc_access, preparation = prepare_evolution_box(
                runtime, world, actions, traversal, to_pc, request,
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
            replanner=world.replanner(),
            pc_facing="up",
        )
        try:
            report = executor(request, actions)
        except EvolutionTrainingPaused as paused:
            report = partial_report(paused)
        return replace(
            report,
            actions_executed=actions.actions_executed - action_start,
            frames_executed=runtime.emulator.frame_count - frame_start,
            evidence={**report.evidence, **preparation},
        )

    return replace(
        runtime,
        boxed_level_evolution_executor=execute,
        boxed_level_evolution_readiness=readiness,
        party_level_evolution_executor=resume,
    )
