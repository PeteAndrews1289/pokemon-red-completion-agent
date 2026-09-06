"""Native-player wiring for the existing boxed-evolution skill.

No new teacher or policy: cartridge routes connect the Center, PC and training
boundary; the existing participation trainer owns battle mechanics. Only a
surplus precursor is eligible, so acquiring its evolution cannot erase a living
species. Both preparation and training share the caller's hard action budget.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast

from pokemon_red_completion import red_goal_context as context
from pokemon_red_completion.collection import CollectionLocation
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
from pokemon_red_completion.goal_manager import GoalKind, GoalUnavailableReason
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_boxed_level_evolution import BoundedEvolutionTrainingResult
from pokemon_red_completion.red_collection import red_internal_species_number, red_species_ref
from pokemon_red_completion.red_dual_capability_curriculum_runtime import SemanticVenueRouteBinding
from pokemon_red_completion.red_goal_boxed_evolution import RedGoalBoxedEvolutionExecutor
from pokemon_red_completion.red_goal_skills import RedCenterRestoreGoalProvider
from pokemon_red_completion.route_plan import RoutePlanningError
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


def bind_native_boxed_evolution(
    runtime: context.RedGoalContextRuntime,
    world: StrategicScenarioRouteWorld,
) -> context.RedGoalContextRuntime:
    """Return an isolated runtime; do not mutate a saved observer's old profile."""
    spec = next(s for s in runtime.profile.providers if s.kind is GoalKind.EVOLVE_SPECIES)

    def readiness(observation: context.RedGoalObservation) -> context.RedGoalSkillAvailability:
        source = spec.parameters["source_species_ref"]
        specimens = [
            s for s in observation.collection_observation.specimens if s.species_ref == source
        ]
        candidates = [
            s
            for s in specimens
            if s.location is CollectionLocation.BOX
            and s.container_index == observation.collection_observation.current_box_index
        ]
        if len(specimens) != 2 or not candidates:
            return context.RedGoalSkillAvailability.unavailable(
                GoalUnavailableReason.NO_LEGAL_TARGET
            )
        precursor = min(candidates, key=lambda s: s.slot_index)
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

    def execute(
        request: context.RedBoxedLevelEvolutionGoalRequest,
        actions: CountingExecutor,
    ) -> GoalExecutionReport:
        before = runtime.adapter.observe()
        source = red_species_ref(red_internal_species_number(request.precursor_internal_species_id))
        if sum(s.species_ref == source for s in before.collection_observation.specimens) != 2:
            raise context.RedGoalContextError("native evolution requires two retained precursors")
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
        identity = canonical_sha256(
            {
                "schema": "pokemon.red.native-boxed-evolution.v1",
                "profile": runtime.profile.profile_sha256,
                "max_battles": 32,
                "max_steps": 2_000,
            }
        )

        def train(source_id: int, target_id: int) -> BoundedEvolutionTrainingResult:
            _, battles, heals = context.run_red_team_balancing(
                actions,
                runtime.reader,
                runtime.emulator,
                policy=replace(context.MANSION_TEAM_POLICY, max_battles=32, max_steps=2_000),
                venues=(
                    context.ROUTE_11_TRAINING_VENUE,
                    context.DIGLETTS_CAVE_TRAINING_VENUE,
                    context.MANSION_TRAINING_VENUE,
                ),
                intent=context.MANSION_BALANCED_TEAM_TRAINING_INTENT,
                flee_timing=context.MANSION_TRAINING_FLEE_TIMING,
                hideout_timing=context.DEFAULT_HIDEOUT_TIMING,
                flee_func=cast(Callable[..., None], context._flee),
                volatile_enemy_species=context.MANSION_VOLATILE_ENEMY_SPECIES,
                escort_enemy_species=context.MANSION_ESCORT_ENEMY_SPECIES,
                max_consecutive_flees=context.MANSION_MAX_CONSECUTIVE_FLEES,
                cancel_interval=context.MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
                evolution_target=(source_id, target_id),
                report_label="native bounded collection evolution",
                checkpoint_count=1,
            )
            return BoundedEvolutionTrainingResult(battles, heals)

        executor = RedGoalBoxedEvolutionExecutor(
            reset_state_sha256=runtime.capture.state_sha256,
            route_to_pc=SemanticVenueRouteBinding(to_pc, identity),
            route_to_training=SemanticVenueRouteBinding(to_training, identity),
            training_binding_sha256=identity,
            reader=runtime.reader,
            traversal_observer=traversal,
            observe_collection=lambda: runtime.adapter.observe().collection_observation,
            train_evolution=train,
            emulator=runtime.emulator,
            replanner=world.replanner(),
        )
        report = executor(request, actions)
        return replace(
            report,
            actions_executed=actions.actions_executed - action_start,
            frames_executed=runtime.emulator.frame_count - frame_start,
        )

    return replace(
        runtime, boxed_level_evolution_executor=execute, boxed_level_evolution_readiness=readiness
    )
