"""Refresh capture and supply destinations without a new policy or walkthrough.

The local profile remains the source of mechanic parameters. This opt-in Red
adapter adds walking transport only when real prerequisites and a cartridge
route exist. Arrival rebinds the real skill from a fresh observation; planning
never fabricates a destination state or grants a successful outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_route_runtime import (
    Gen1RouteInterruptionHandler,
    Gen1TraversalObserver,
)
from pokemon_red_completion.gen1_trainer_sight import Gen1TrainerSightProjector
from pokemon_red_completion.goal_manager import GoalAvailability, GoalKind, GoalUnavailableReason
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context import RedGoalContextRuntime
from pokemon_red_completion.red_goal_context_profile import RedGoalMechanic, RedGoalProviderSpec
from pokemon_red_completion.red_goal_manager import RedGoalObservation
from pokemon_red_completion.red_goal_skills import (
    RedAreaSurveyGoalProvider,
    RedMartResupplyGoalProvider,
)
from pokemon_red_completion.red_living_dex_setup_source import (
    red_living_dex_setup_fresh_observation_sha256,
)
from pokemon_red_completion.red_routed_semantic_goal import (
    FreshRedGoalObservation,
    RedFreshGoalDestinationBinder,
    RedSemanticTransportRoute,
    build_red_routed_semantic_goal_composer,
)
from pokemon_red_completion.route_executor import ReplanRequest, RouteExecutionLimits
from pokemon_red_completion.route_plan import RoutePlan, RoutePlanningError
from pokemon_red_completion.routed_semantic_goal import RoutedSemanticGoalLimits
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
)

_WALK_ACTIONS = frozenset({"up", "right", "down", "left"})
_MECHANICS = frozenset({RedGoalMechanic.WILD_CORRIDOR_CAPTURE, RedGoalMechanic.MART_RESUPPLY})
_ROUTE_LIMITS = RouteExecutionLimits(
    max_step_attempts=8,
    max_readiness_waits=16,
    max_interruptions=16,
    max_replans=8,
    replan_after_unchanged=2,
    retry_wait_frames=24,
    readiness_wait_frames=24,
    transition_settle_frames=180,
)


class RedResourceGoalRoutingError(RuntimeError):
    """A refreshed resource goal cannot keep its observed transport contract."""


@dataclass(slots=True)
class RedResourceGoalRouter:
    """Reuse local skills, adding only feasible capture/supply walking routes."""

    runtime: RedGoalContextRuntime
    actions: CountingExecutor
    world: StrategicScenarioRouteWorld
    maximum_controller_actions: int = 6_000
    maximum_emulator_frames: int = 600_000
    quote_resource_costs: bool = False

    def enumerate(self, observation: RedGoalObservation) -> GoalBindingSet:
        before = (self.actions.actions_executed, self.runtime.emulator.frame_count)
        local = self.runtime.enumerator(self.actions).enumerate(observation)
        if observation.raw.battle_state or not observation.input_ready:
            return local
        traversal = Gen1TraversalObserver(
            self.runtime.reader,
            hazard_projector=Gen1TrainerSightProjector(self.world.rom, self.runtime.reader),
        )
        fresh = FreshRedGoalObservation("0" * 64, observation, traversal.observe())
        # FrameSafeExecutor has no HM action port. Do not advertise Surf/Cut/
        # Strength just because the party knows them; walking is the declared scope.
        if fresh.traversal.mode != "land":
            return local
        origin = red_living_dex_setup_fresh_observation_sha256(fresh)
        replacements: dict[str, ExecutableGoalBinding] = {}
        specs = {spec.kind: spec for spec in self.runtime.profile.providers}
        opportunities = list(local.opportunities)
        for index, opportunity in enumerate(opportunities):
            spec = specs.get(opportunity.kind)
            if (
                opportunity.availability is GoalAvailability.AVAILABLE
                or opportunity.unavailable_reason is not GoalUnavailableReason.MISSING_CAPABILITY
                or spec is None
                or spec.mechanic not in _MECHANICS
            ):
                continue
            provider = self.runtime.provider_for(spec.kind, self.actions)
            if not isinstance(provider, (RedAreaSurveyGoalProvider, RedMartResupplyGoalProvider)):
                raise RedResourceGoalRoutingError("routable resource provider type differs")
            availability = provider.resource_availability(observation)
            if not availability.executable:
                opportunities[index] = replace(
                    opportunity, unavailable_reason=availability.unavailable_reason
                )
                continue
            plan = self._plan(spec, fresh)
            if plan is None:
                continue
            transport = RedSemanticTransportRoute(
                binding_ref=f"red-resource-route:{spec.configuration_sha256}",
                origin_observation_sha256=origin,
                planner_binding_sha256=canonical_sha256(
                    {
                        "schema": "pokemon.red.resource-goal-router.v1",
                        "profile_sha256": self.runtime.profile.profile_sha256,
                        "walking_only": True,
                    }
                ),
                plan=plan,
                actions=self.actions,
                traversal_observer=traversal,
                emulator=self.runtime.emulator,
                interruption_handler=Gen1RouteInterruptionHandler(
                    self.actions,
                    self.runtime.reader,
                    maximum_flees=16,
                    maximum_trainer_battles=8,
                    stabilization_frames=180,
                    route_name="bounded resource-goal transport",
                ),
                replanner=self._replan,
                route_limits=_ROUTE_LIMITS,
            )

            def observe_fresh() -> FreshRedGoalObservation:
                current = FreshRedGoalObservation(
                    "0" * 64, self.runtime.adapter.observe(), traversal.observe()
                )
                return replace(
                    current,
                    observation_sha256=red_living_dex_setup_fresh_observation_sha256(current),
                )

            destination = RedFreshGoalDestinationBinder(
                kind=spec.kind,
                boundary=transport.terminal_boundary,
                observe_fresh=observe_fresh,
                provider=provider,
            )
            binding = build_red_routed_semantic_goal_composer(
                binding_ref=f"red-resource-goal:{origin}:{spec.configuration_sha256}",
                transport=transport,
                destination=destination,
                estimated_effort=min(1.0, 0.36 + len(plan.steps) / 1_000),
                estimated_risk=0.18,
                limits=RoutedSemanticGoalLimits(
                    self.maximum_controller_actions, self.maximum_emulator_frames
                ),
            ).binding()
            if isinstance(provider, RedAreaSurveyGoalProvider):
                binding = replace(
                    binding, search_source_ref=f"pokemon.red:acquisition:{provider.source_id}"
                )
            replacements[binding.binding_ref] = binding
            opportunities[index] = binding.opportunity
        if before != (self.actions.actions_executed, self.runtime.emulator.frame_count):
            raise RedResourceGoalRoutingError("resource-goal enumeration changed the game")
        result = GoalBindingSet(tuple(opportunities), (*local.bindings, *replacements.values()))
        return self._with_quotes(result, observation) if self.quote_resource_costs else result

    def _with_quotes(
        self, bindings: GoalBindingSet, observation: RedGoalObservation
    ) -> GoalBindingSet:
        """Bind exact costs to the same opportunity and executable skill."""
        quoted = []
        for binding in bindings.bindings:
            if binding.kind is GoalKind.RESUPPLY:
                provider = self.runtime.provider_for(binding.kind, self.actions)
                if not isinstance(provider, RedMartResupplyGoalProvider):
                    raise RedResourceGoalRoutingError("resource-cost quote needs a Mart provider")
                binding = self._quoted_binding(binding, provider, observation)
            quoted.append(binding)
        by_ref = {item.binding_ref: item.opportunity for item in quoted}
        return GoalBindingSet(
            tuple(by_ref.get(item.binding_ref, item) for item in bindings.opportunities),
            tuple(quoted),
        )

    def _quoted_binding(
        self,
        binding: ExecutableGoalBinding,
        provider: RedMartResupplyGoalProvider,
        observation: RedGoalObservation,
    ) -> ExecutableGoalBinding:
        quote = provider.resource_quote(observation)

        def execute() -> GoalExecutionReport:
            # Reject stale economic facts before transport or menu input. The
            # destination skill separately verifies actual inventory/money deltas.
            current = provider.resource_quote(self.runtime.adapter.observe())
            if current != quote:
                raise RedResourceGoalRoutingError("resource quote changed before execution")
            return binding.execute()

        return replace(binding, resource_quote=quote, execute=execute)

    def _plan(self, spec: RedGoalProviderSpec, fresh: FreshRedGoalObservation) -> RoutePlan | None:
        parameters = spec.parameters
        target_map = parameters["map_id"]
        x, y = parameters["player_x"], parameters["player_y"]
        if any(type(value) is not int for value in (target_map, x, y)):
            raise RedResourceGoalRoutingError("resource destination is not an integer boundary")
        assert isinstance(target_map, int) and isinstance(x, int) and isinstance(y, int)
        if (fresh.traversal.map_id, fresh.traversal.at) == (target_map, (y, x)):
            return None
        try:
            plan = self.world.plan_feasible_to_map(fresh.traversal, target_map, goal_at=(y, x))
        except RoutePlanningError:
            return None
        if not plan.steps or not _walking_plan(plan):
            return None
        return plan

    def _replan(self, request: ReplanRequest) -> RoutePlan:
        plan = self.world.replanner()(request)
        if not _walking_plan(plan):
            raise RedResourceGoalRoutingError("resource route requires an unsupported field action")
        return plan


def _walking_plan(plan: RoutePlan) -> bool:
    return all(
        step.action_kind is MacroActionKind.MOVE
        and step.action in _WALK_ACTIONS
        and step.source_mode in {None, "land"}
        and step.expected_mode in {None, "land"}
        for step in plan.steps
    )
