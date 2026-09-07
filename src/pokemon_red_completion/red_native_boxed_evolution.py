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
from pokemon_red_completion.goal_manager import GoalKind, GoalUnavailableReason
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_battle_catalog import (
    PokemonRedBattleCatalog,
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)
from pokemon_red_completion.red_boxed_level_evolution import BoundedEvolutionTrainingResult
from pokemon_red_completion.red_collection import red_internal_species_number, red_species_ref
from pokemon_red_completion.red_dual_capability_curriculum_runtime import SemanticVenueRouteBinding
from pokemon_red_completion.red_goal_boxed_evolution import RedGoalBoxedEvolutionExecutor
from pokemon_red_completion.red_goal_skills import (
    RedCenterRestoreGoalProvider,
    finish_center_dialogue,
)
from pokemon_red_completion.red_party import PokemonRedPartyReader
from pokemon_red_completion.red_team_training import (
    EvolutionTrainingPaused,
    training_type_matchup_acceptable,
)
from pokemon_red_completion.route_plan import RoutePlanningError
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


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
        if move.power <= 0 or move.effect_flags.intersection(
            {"recoil", "self_destruct", "ohko", "charge", "recharge"}
        ):
            continue
        effectiveness = catalog.type_effectiveness(move.type_name, enemy)
        score = move.power * move.accuracy * effectiveness * (1.5 if move.type_name in own else 1.0)
        if score > 0:
            candidates.append((score, -(index + 1)))
    if not candidates:
        raise _PauseForTeamTrainingRecovery
    return -max(candidates)[1]


def bind_native_boxed_evolution(
    runtime: context.RedGoalContextRuntime,
    world: StrategicScenarioRouteWorld,
    *,
    maximum_quanta: int = 1,
    retain_quantum: Callable[[], None] | None = None,
) -> context.RedGoalContextRuntime:
    """Return an isolated runtime; do not mutate a saved observer's old profile."""
    if type(maximum_quanta) is not int or not 1 <= maximum_quanta <= 128:
        raise ValueError("native evolution quantum limit differs")
    spec = next(s for s in runtime.profile.providers if s.kind is GoalKind.EVOLVE_SPECIES)

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
                and s.container_index == observation.collection_observation.current_box_index
            )
        ]
        if len(specimens) != 2 or not candidates:
            return context.RedGoalSkillAvailability.unavailable(
                GoalUnavailableReason.NO_LEGAL_TARGET
            )
        # The native mode permits safe direct trainee battles; the starter is
        # still required for the existing escape mechanism, not mandatory XP.
        from pokemon_red_completion.red_party import BLASTOISE_SPECIES_ID

        escort = next(
            (m for m in observation.party.members if m.species_id == BLASTOISE_SPECIES_ID),
            None,
        )
        if escort is None:
            return context.RedGoalSkillAvailability.unavailable(
                GoalUnavailableReason.MISSING_CAPABILITY
            )
        precursor = min(
            candidates, key=lambda s: (s.location is not CollectionLocation.PARTY, s.slot_index)
        )
        policy = context.MANSION_TEAM_POLICY
        ceiling = (
            precursor.level - policy.minimum_direct_level_advantage
            if policy.minimum_direct_level_advantage
            else precursor.level + policy.max_enemy_level_delta
        )
        from pokemon_red_completion.team_training import MINIMUM_FIGHTABLE_SHARE

        venues = (
            context.ROUTE_11_TRAINING_VENUE,
            context.DIGLETTS_CAVE_TRAINING_VENUE,
            context.MANSION_TRAINING_VENUE,
        )
        if not any(v.band.fightable_share(ceiling) >= MINIMUM_FIGHTABLE_SHARE for v in venues):
            return context.RedGoalSkillAvailability.unavailable(
                GoalUnavailableReason.MISSING_CAPABILITY
            )
        return context.RedGoalSkillAvailability.available()

    def train_quantum(
        actions: CountingExecutor,
        source_id: int,
        target_id: int,
    ) -> BoundedEvolutionTrainingResult:
        trainee = next(
            (m for m in runtime.adapter.observe().party.members if m.species_id == source_id), None
        )
        if trainee is None:
            raise context.RedGoalContextError("native training lost its in-party precursor")
        tables = wild_tables(world.rom)
        from pokemon_red_completion.team_training import (
            member_can_train_at,
            training_safety_ceiling,
        )

        ceiling = training_safety_ceiling(trainee, context.MANSION_TEAM_POLICY)
        venues = tuple(
            replace(venue, move_slot=native_training_move_slot)
            for venue in (
                context.ROUTE_11_TRAINING_VENUE,
                context.DIGLETTS_CAVE_TRAINING_VENUE,
                context.MANSION_TRAINING_VENUE,
            )
            if any(
                level <= ceiling and training_type_matchup_acceptable(trainee.species_id, species)
                for level, species in tables.get(venue.map_id, ())
            )
        )
        if not venues:
            raise context.RedGoalContextError(
                "no cartridge encounter permits safe direct evolution"
            )
        # A higher encounter level alone does not justify travel. Keep a
        # currently executable safe venue for this bounded quantum; otherwise
        # the historical trainer may invoke a transition from an unsupported
        # field boundary. This is local continuity, not a learned venue policy.
        current = runtime.reader.read()
        local_venues = tuple(
            venue
            for venue in venues
            if venue.is_in_map(current)
            and member_can_train_at(trainee, context.MANSION_TEAM_POLICY, venue.band)
        )
        if local_venues:
            venues = local_venues
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
            evolution_battle_quantum=4,
            report_label="native bounded collection evolution",
            checkpoint_count=1,
        )
        return BoundedEvolutionTrainingResult(battles, heals)

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
        heal = RedCenterRestoreGoalProvider(
            actions,
            runtime.reader,
            runtime.emulator,
            runtime.adapter,
        ).offer(before)
        if heal.binding is not None:
            heal.binding.execute()
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
                "battle_quantum": 4,
                "maximum_quanta": maximum_quanta,
                "pc_facing": "up",
            }
        )

        executor = RedGoalBoxedEvolutionExecutor(
            reset_state_sha256=runtime.capture.state_sha256,
            route_to_pc=SemanticVenueRouteBinding(to_pc, identity),
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
        )

    return replace(
        runtime,
        boxed_level_evolution_executor=execute,
        boxed_level_evolution_readiness=readiness,
        party_level_evolution_executor=resume,
    )
