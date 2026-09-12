"""Refresh capture and supply destinations without a new policy or walkthrough.

The local profile remains the source of mechanic parameters. This opt-in Red
adapter adds walking transport only when real prerequisites and a cartridge
route exist. Arrival rebinds the real skill from a fresh observation; planning
never fabricates a destination state or grants a successful outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import partial

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_field_moves import (
    SEAFOAM_ISLANDS_B4F_MAP_ID,
    Gen1FieldMovePort,
    surf_permission,
)
from pokemon_red_completion.gen1_route_runtime import (
    Gen1RouteInterruptionHandler,
    Gen1TraversalObserver,
)
from pokemon_red_completion.gen1_trainer_sight import Gen1TrainerSightProjector
from pokemon_red_completion.gen1_traversal import cut_capabilities, surf_capabilities
from pokemon_red_completion.goal_manager import GoalAvailability, GoalKind, GoalUnavailableReason
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
)
from pokemon_red_completion.observation import MapId, RawGameState, ReadOnlyMemory
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context import RedGoalContextRuntime, _RedTeamGoalProvider
from pokemon_red_completion.red_goal_context_profile import RedGoalMechanic, RedGoalProviderSpec
from pokemon_red_completion.red_goal_manager import RedGoalBindingProvider, RedGoalObservation
from pokemon_red_completion.red_goal_skills import (
    RedAreaSurveyGoalProvider,
    RedMartResupplyGoalProvider,
    prepare_center_departure,
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
from pokemon_red_completion.route_executor import (
    InterruptionHandler,
    ReplanRequest,
    RouteExecutionLimits,
    TraversalSnapshot,
)
from pokemon_red_completion.route_plan import RoutePlan, RoutePlanningError
from pokemon_red_completion.routed_semantic_goal import RoutedSemanticGoalLimits
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
)

_WALK_ACTIONS = frozenset({"up", "right", "down", "left"})
_MECHANICS = frozenset(
    {
        RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
        RedGoalMechanic.MART_RESUPPLY,
        RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
    }
)
# Resource routes also perform bounded encounter search.  Sixteen exits is a
# reasonable transport guard but too small for a five-percent missing encounter:
# a healthy route can exhaust it before the ordinary search budget has a fair
# chance to produce its target.  This remains finite and is covered by the route's
# independent action/frame bounds.
_MAX_ROUTE_FLEES = 128
_MAX_ROUTE_TRAINER_BATTLES = 8
_ROUTE_LIMITS = RouteExecutionLimits(
    max_step_attempts=8,
    max_readiness_waits=16,
    max_interruptions=_MAX_ROUTE_FLEES + _MAX_ROUTE_TRAINER_BATTLES,
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
    prepare_capture_party: bool = True
    prepare_capture_storage: bool = False
    routed_storage_relief: bool = False
    routed_recovery: bool = False
    trainer_funding: bool = False
    trainer_pending_recovery: bool = False
    regional_trainer_funding: bool = False
    observed_trainer_funding: bool = False
    prepare_capture_escort: bool = True
    # Capture-only menus discard RESTORE_TEAM offers. Keep guarded transport
    # and escort preparation enabled without planning unused Center routes.
    include_recovery_offers: bool = True
    # Shared only during one action-free candidate inventory. It is explicitly
    # cleared before returning so a later live observation cannot inherit it.
    route_plan_cache: dict[
        tuple[TraversalSnapshot, int, tuple[int, int] | None], RoutePlan | str
    ] | None = field(default=None, repr=False, compare=False)

    def enumerate(self, observation: RedGoalObservation) -> GoalBindingSet:
        """Enumerate every local and routable goal in the active profile."""
        return self._enumerate(observation, routed_kinds=None)

    def enumerate_routed_kinds(
        self,
        observation: RedGoalObservation,
        routed_kinds: frozenset[GoalKind],
    ) -> GoalBindingSet:
        """Route only requested kinds while preserving the complete local menu.

        Regional source comparison needs one acquisition binding from each
        retargeted profile. Planning unrelated Mart, recovery or evolution
        transports cannot change that binding, but used to dominate inventory
        latency. Live provider availability, traversal capabilities and the
        acquisition route are still recomputed for every source.
        """
        if (
            not isinstance(routed_kinds, frozenset)
            or not routed_kinds
            or any(not isinstance(kind, GoalKind) for kind in routed_kinds)
        ):
            raise TypeError("routed goal kinds must be a non-empty GoalKind frozenset")
        return self._enumerate(observation, routed_kinds=routed_kinds)

    def _enumerate(
        self,
        observation: RedGoalObservation,
        *,
        routed_kinds: frozenset[GoalKind] | None,
    ) -> GoalBindingSet:
        before = (self.actions.actions_executed, self.runtime.emulator.frame_count)
        local = self.runtime.enumerator(self.actions).enumerate(observation)
        if observation.raw.battle_state or not observation.input_ready:
            return local
        traversal = Gen1TraversalObserver(
            self.runtime.reader,
            hazard_projector=Gen1TrainerSightProjector(self.world.rom, self.runtime.reader),
            capability_projector=partial(
                collection_field_capabilities, self.runtime.emulator,
                allow_cut=any(_cut_enabled(s) for s in self.runtime.profile.providers),
                allow_surf=any(_surf_enabled(s) for s in self.runtime.profile.providers),
            ),
        )
        fresh = FreshRedGoalObservation("0" * 64, observation, traversal.observe())
        # New transports start on land and finish at a land encounter corridor.
        # Cut/Surf require explicit options and share the existing primitive meter.
        if fresh.traversal.mode != "land":
            return local
        origin = red_living_dex_setup_fresh_observation_sha256(fresh)
        replacements: dict[str, ExecutableGoalBinding] = {}
        specs = {spec.kind: spec for spec in self.runtime.profile.providers}
        capture_spec = specs.get(GoalKind.ACQUIRE_SPECIES)
        observed_capture = bool(
            capture_spec is not None
            and capture_spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE
            and capture_spec.parameters.get("observed_local_capture") is True
            and capture_spec.parameters["map_id"] == observation.raw.map_id
        )
        if observed_capture:
            from pokemon_red_completion.red_observed_local_capture import (
                bind_observed_local_capture,
            )

            assert capture_spec is not None
            capture = bind_observed_local_capture(self, capture_spec, observation)
            local = GoalBindingSet(
                tuple(
                    (capture.opportunity if capture is not None else replace(
                        item, availability=GoalAvailability.UNAVAILABLE,
                        estimated_effort=None, estimated_risk=None,
                        unavailable_reason=GoalUnavailableReason.MISSING_CAPABILITY,
                    )) if item.kind is GoalKind.ACQUIRE_SPECIES else item
                    for item in local.opportunities
                ),
                tuple(b for b in local.bindings if b.kind is not GoalKind.ACQUIRE_SPECIES)
                + (() if capture is None else (capture,)),
            )
        opportunities = list(local.opportunities)
        for index, opportunity in enumerate(opportunities):
            if routed_kinds is not None and opportunity.kind not in routed_kinds:
                continue
            spec = specs.get(opportunity.kind)
            if observed_capture and opportunity.kind is GoalKind.ACQUIRE_SPECIES:
                # Never reinstate the static, unreachable patch as a fallback.
                continue
            if (
                opportunity.availability is GoalAvailability.AVAILABLE
                or opportunity.unavailable_reason is not GoalUnavailableReason.MISSING_CAPABILITY
                or spec is None
                or spec.mechanic not in _MECHANICS
            ):
                continue
            provider = self.runtime.provider_for(spec.kind, self.actions)
            if not isinstance(
                provider,
                (RedAreaSurveyGoalProvider, RedMartResupplyGoalProvider, _RedTeamGoalProvider),
            ):
                raise RedResourceGoalRoutingError("routable resource provider type differs")
            availability = provider.resource_availability(observation)
            if not availability.executable:
                opportunities[index] = replace(
                    opportunity, unavailable_reason=availability.unavailable_reason
                )
                continue
            if (
                isinstance(provider, RedMartResupplyGoalProvider)
                and provider.affordable_ball_purchase
            ):
                fixed_provider = provider.affordable_provider(observation)
                if fixed_provider is None:
                    raise RedResourceGoalRoutingError("available purchase lost its fixed quote")
                provider = fixed_provider
            plan = self._plan(spec, fresh)
            if plan is None:
                from pokemon_red_completion.red_collection_fly import bind_collection_fly

                flight = bind_collection_fly(self, spec, provider, fresh, traversal)
                if flight is not None:
                    replacements[flight.binding_ref] = flight
                    opportunities[index] = flight.opportunity
                continue
            interruption_handler: InterruptionHandler = Gen1RouteInterruptionHandler(
                self.actions, self.runtime.reader, maximum_flees=_MAX_ROUTE_FLEES,
                maximum_trainer_battles=_MAX_ROUTE_TRAINER_BATTLES, stabilization_frames=180,
                route_name="bounded resource-goal transport",
            )
            if self.routed_recovery:
                from pokemon_red_completion.red_routed_recovery import (
                    guarded_collection_route_handler,
                )
                interruption_handler = guarded_collection_route_handler(
                    self.actions,
                    self.runtime.reader,
                    route_name="guarded resource-goal transport",
                    maximum_flees=_MAX_ROUTE_FLEES,
                )
            from pokemon_red_completion.red_travel_capture_runtime import (
                bind_travel_capture_destination,
                bind_travel_capture_handler,
            )
            interruption_handler = bind_travel_capture_handler(self, spec, interruption_handler)
            transport = RedSemanticTransportRoute(
                binding_ref=f"red-resource-route:{spec.configuration_sha256}",
                origin_observation_sha256=origin,
                planner_binding_sha256=canonical_sha256(
                    {
                        "schema": "pokemon.red.resource-goal-router.v1",
                        "profile_sha256": self.runtime.profile.profile_sha256,
                        "walking_only": not (_cut_enabled(spec) or _surf_enabled(spec)),
                    }
                ),
                plan=plan,
                actions=self.actions,
                traversal_observer=traversal,
                emulator=self.runtime.emulator,
                interruption_handler=interruption_handler,
                replanner=partial(
                    self._replan, allow_cut=_cut_enabled(spec), allow_surf=_surf_enabled(spec),
                ),
                field_actions=self.field_actions_for(spec),
                route_limits=_ROUTE_LIMITS,
                prepare_departure=lambda: prepare_center_departure(
                    self.actions, self.runtime.reader
                ),
            )

            def observe_fresh() -> FreshRedGoalObservation:
                current = FreshRedGoalObservation(
                    "0" * 64, self.runtime.adapter.observe(), traversal.observe()
                )
                return replace(
                    current,
                    observation_sha256=red_living_dex_setup_fresh_observation_sha256(current),
                )

            destination_provider: RedGoalBindingProvider = provider
            if self.routed_recovery and isinstance(provider, RedAreaSurveyGoalProvider):
                from pokemon_red_completion.red_capture_preparation import (
                    EscortPreparedCaptureProvider,
                )
                destination_provider = EscortPreparedCaptureProvider(
                    provider, self.runtime, self.actions,
                )
            destination_provider = bind_travel_capture_destination(
                self, spec, destination_provider, provider, observation, [interruption_handler],
            )
            destination = RedFreshGoalDestinationBinder(
                kind=spec.kind,
                boundary=transport.terminal_boundary,
                observe_fresh=observe_fresh,
                provider=destination_provider,
            )
            binding = build_red_routed_semantic_goal_composer(
                binding_ref=f"red-resource-goal:{origin}:{spec.configuration_sha256}",
                transport=transport,
                destination=destination,
                estimated_effort=min(
                    1.0, 0.36 + len(plan.steps) / 1_000
                    + (provider.search_effort_surcharge
                       if isinstance(provider, RedAreaSurveyGoalProvider) else 0.0),
                ),
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
        if self.routed_storage_relief:
            from pokemon_red_completion.red_routed_storage_relief import (
                bind_routed_storage_relief,
            )
            result = bind_routed_storage_relief(self, result, observation)
        if self.prepare_capture_storage:
            from pokemon_red_completion.red_routed_capture_storage import (
                bind_capture_storage_support,
            )

            result = bind_capture_storage_support(self, result, observation)
        if self.prepare_capture_party and any(
            spec.parameters.get("capture_status_support") is True
            for spec in self.runtime.profile.providers
        ):
            from pokemon_red_completion.red_routed_capture_support import bind_capture_party_support

            result = bind_capture_party_support(self, result, observation)
        if before != (self.actions.actions_executed, self.runtime.emulator.frame_count):
            raise RedResourceGoalRoutingError("capture support enumeration changed the game")
        if self.routed_recovery:
            from pokemon_red_completion.red_capture_preparation import (
                bind_capture_escort,
                prepare_capture_escort,
            )
            from pokemon_red_completion.red_routed_recovery import bind_routed_center_recovery

            def prepare_escort() -> None:
                prepare_capture_escort(self.runtime, self.actions)

            if self.include_recovery_offers:
                result = bind_routed_center_recovery(
                    self, result, observation,
                    prepare_escort=prepare_escort,
                )
            if self.prepare_capture_escort:
                result = bind_capture_escort(self, result, observation)
        if before != (self.actions.actions_executed, self.runtime.emulator.frame_count):
            raise RedResourceGoalRoutingError("recovery enumeration changed the game")
        if self.quote_resource_costs:
            result = self._with_quotes(result, observation)
        # Income is not a Mart purchase and must never inherit a spend quote.
        if self.trainer_funding:
            from pokemon_red_completion.red_routed_trainer_funding import bind_local_trainer_funding

            result = bind_local_trainer_funding(self, result, observation)
        if before != (self.actions.actions_executed, self.runtime.emulator.frame_count):
            raise RedResourceGoalRoutingError("trainer funding enumeration changed the game")
        return result

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

    def plan_feasible_to_map(
        self,
        start: TraversalSnapshot,
        goal_map: int,
        *,
        goal_at: tuple[int, int] | None = None,
    ) -> RoutePlan:
        """Reuse an identical route query only inside one frozen inventory pass."""
        cache = self.route_plan_cache
        if cache is None:
            return self.world.plan_feasible_to_map(start, goal_map, goal_at=goal_at)
        key = (start, goal_map, goal_at)
        if key in cache:
            cached = cache[key]
            if isinstance(cached, str):
                raise RoutePlanningError(cached)
            return cached
        try:
            plan = self.world.plan_feasible_to_map(start, goal_map, goal_at=goal_at)
        except RoutePlanningError as error:
            cache[key] = str(error)
            raise
        cache[key] = plan
        return plan

    def _plan(self, spec: RedGoalProviderSpec, fresh: FreshRedGoalObservation) -> RoutePlan | None:
        parameters = spec.parameters
        if spec.mechanic is RedGoalMechanic.TARGETED_LEVEL_EVOLUTION:
            # Known mechanic entry boundaries, connected by the cartridge router.
            for center in (MapId.CINNABAR_POKECENTER, MapId.VERMILION_POKECENTER):
                try:
                    plan = self.plan_feasible_to_map(
                        fresh.traversal,
                        int(center),
                        goal_at=(3, 3),
                    )
                except RoutePlanningError:
                    continue
                if plan.steps and _supported_plan(
                    plan, allow_cut=_cut_enabled(spec), allow_surf=_surf_enabled(spec),
                ):
                    return plan
            return None
        target_map = parameters["map_id"]
        x, y = parameters["player_x"], parameters["player_y"]
        if any(type(value) is not int for value in (target_map, x, y)):
            raise RedResourceGoalRoutingError("resource destination is not an integer boundary")
        assert isinstance(target_map, int) and isinstance(x, int) and isinstance(y, int)
        if (fresh.traversal.map_id, fresh.traversal.at) == (target_map, (y, x)):
            return None
        try:
            plan = self.plan_feasible_to_map(fresh.traversal, target_map, goal_at=(y, x))
        except RoutePlanningError:
            return None
        if not plan.steps or not _supported_plan(
            plan, allow_cut=_cut_enabled(spec), allow_surf=_surf_enabled(spec),
        ):
            return None
        return plan

    def field_actions_for(self, spec: RedGoalProviderSpec) -> Gen1FieldMovePort | None:
        """Expand field macros through the same counted/budgeted primitive port."""
        if not (_cut_enabled(spec) or _surf_enabled(spec)):
            return None
        return Gen1FieldMovePort(
            self.actions, self.runtime.reader, self.runtime.emulator,
            cut_block_swaps={swap.before: swap.after for swap in self.world.rules.cut_block_swaps},
        )

    def _replan(
        self, request: ReplanRequest, *, allow_cut: bool = False, allow_surf: bool = False,
    ) -> RoutePlan:
        plan = self.world.replanner()(request)
        if not _supported_plan(plan, allow_cut=allow_cut, allow_surf=allow_surf):
            raise RedResourceGoalRoutingError("resource route requires an unsupported field action")
        return plan


def _cut_enabled(spec: RedGoalProviderSpec) -> bool:
    return (spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE
            and spec.parameters.get("cut_transport") is True)


def _surf_enabled(spec: RedGoalProviderSpec) -> bool:
    return (spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE
            and spec.parameters.get("surf_transport") is True)


def collection_field_capabilities(
    memory: ReadOnlyMemory, raw: RawGameState, *, allow_cut: bool, allow_surf: bool,
) -> frozenset[str]:
    """Expose only declared mechanics with live badge/holder/title permission."""
    result = cut_capabilities(raw) if allow_cut else frozenset()
    if allow_surf:
        result = result.union(surf_capabilities(
            raw, surf_allowed=surf_permission(memory, raw).allowed,
        ))
    return result


def _supported_plan(
    plan: RoutePlan, *, allow_cut: bool = False, allow_surf: bool = False,
) -> bool:
    for step in plan.steps:
        if step.action_kind is MacroActionKind.MOVE and step.action in _WALK_ACTIONS:
            modes = {None, "land", "water"} if allow_surf else {None, "land"}
            if step.source_mode not in modes or step.expected_mode not in modes:
                return False
            # Entering water needs the metered Surf macro, not a plain arrow.
            if step.source_mode != "water" and step.expected_mode == "water":
                return False
        elif step.action_kind is MacroActionKind.FIELD_MOVE:
            if allow_cut and step.action in {"cut:" + d for d in _WALK_ACTIONS}:
                if (step.source_mode not in {None, "land"}
                        or step.expected_mode not in {None, "land"}):
                    return False
            elif allow_surf and step.action in {"surf:" + d for d in _WALK_ACTIONS}:
                if (
                    step.source_mode != "land" or step.expected_mode != "water"
                    or step.source_map != step.expected_map
                    or step.source_map == SEAFOAM_ISLANDS_B4F_MAP_ID
                ):
                    return False
            else:
                return False
        else:
            return False
    return True


def _walking_plan(plan: RoutePlan) -> bool:
    return _supported_plan(plan)
