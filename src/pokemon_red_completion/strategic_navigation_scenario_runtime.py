"""Plan, execute and strictly reload one short strategic rehearsal."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from pokemon_red_completion.actions import MacroAction
from pokemon_red_completion.gen1_maps import macro_graph_from_nodes, map_graph
from pokemon_red_completion.gen1_story_routing import apply_gen1_story_requirements
from pokemon_red_completion.gen1_terrain import walkable_world
from pokemon_red_completion.gen1_traversal import (
    map_object_events,
    surf_local_graph,
    traversal_rules,
)
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalGraph
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.red_trajectory import POKEMON_RED_GAME_ID
from pokemon_red_completion.route_executor import (
    DEFAULT_ROUTE_EXECUTION_LIMITS,
    InterruptionHandler,
    ReplanRequest,
    RouteActionPort,
    RouteExecutionLimits,
    RouteExecutionReport,
    RouteReplanner,
    RouteResourceManager,
    TraversalObserver,
    TraversalSnapshot,
)
from pokemon_red_completion.route_plan import RoutePlan, RoutePlanningError, plan_route
from pokemon_red_completion.strategic_navigation import (
    DestinationUnavailableReason,
    StrategicNavigationTag,
)
from pokemon_red_completion.strategic_navigation_binding import DestinationRouteBinding
from pokemon_red_completion.strategic_navigation_dataset import (
    CollectedStrategicNavigationDataset,
    StrategicNavigationDatasetError,
    load_assigned_strategic_navigation_episode,
)
from pokemon_red_completion.strategic_navigation_protocol import (
    StrategicNavigationScenarioRehearsalAssignment,
)
from pokemon_red_completion.strategic_navigation_runtime import (
    execute_strategic_navigation_route,
)
from pokemon_red_completion.strategic_navigation_scenario_routes import (
    ScenarioObjectiveDestinationSpec,
)
from pokemon_red_completion.strategic_navigation_scenarios import (
    StrategicNavigationScenario,
)
from pokemon_red_completion.strategic_navigation_trajectory import (
    StrategicNavigationTrajectoryObserver,
)
from pokemon_red_completion.trajectory import (
    RecordingExecutor,
    SnapshotProvider,
    SparseEvent,
)
from pokemon_red_completion.trajectory_io import EpisodeTrajectorySink


class StrategicScenarioRuntimeError(RuntimeError):
    """Raised before a rehearsal can overstate a branch or durable result."""


@dataclass(frozen=True, slots=True)
class StrategicScenarioRouteWorld:
    """Immutable cartridge-derived routing inputs shared by all candidates."""

    macro_graph: MacroGraph
    local_graphs: Mapping[int, LocalGraph]

    @classmethod
    def from_rom(cls, rom: bytes) -> StrategicScenarioRouteWorld:
        if not isinstance(rom, bytes) or not rom:
            raise ValueError("scenario routing requires immutable ROM bytes")
        maps = map_graph(rom)
        rules = traversal_rules(rom, maps)
        terrain = walkable_world(rom)
        local_graphs = apply_gen1_story_requirements(
            {
                map_id: surf_local_graph(
                    local,
                    rules,
                    blocked={event.at for event in map_object_events(rom, {map_id})},
                )
                for map_id, local in terrain.items()
            }
        )
        return cls(macro_graph_from_nodes(maps), local_graphs)

    def plan_bindings(
        self,
        specs: tuple[ScenarioObjectiveDestinationSpec, ...],
        start: TraversalSnapshot,
    ) -> tuple[DestinationRouteBinding, ...]:
        """Plan every candidate and retain semantic failures without selecting."""

        if not isinstance(specs, tuple) or len(specs) < 2:
            raise StrategicScenarioRuntimeError(
                "scenario routing requires at least two immutable destination specs"
            )
        bindings: list[DestinationRouteBinding] = []
        for spec in specs:
            if not isinstance(spec, ScenarioObjectiveDestinationSpec):
                raise TypeError("scenario destination specs contain an invalid value")
            try:
                plan = plan_route(
                    self.macro_graph,
                    self.local_graphs,
                    start.map_id,
                    start.at,
                    spec.goal_map.value,
                    blocked={start.map_id: start.occupied},
                    capabilities=start.capabilities,
                    last_outside=start.last_outside_map,
                    start_mode=start.mode,
                )
            except RoutePlanningError:
                bindings.append(
                    DestinationRouteBinding.unavailable(
                        spec.destination_ref,
                        spec.semantic_tags,
                        DestinationUnavailableReason.PLANNER_NO_ROUTE,
                    )
                )
            else:
                bindings.append(
                    DestinationRouteBinding.available(
                        spec.destination_ref,
                        spec.semantic_tags,
                        plan,
                    )
                )
        return tuple(bindings)

    def replanner(self) -> RouteReplanner:
        """Recompute the same declared goal after a measured live blocker."""

        def replan(request: ReplanRequest) -> RoutePlan:
            current = request.current
            return plan_route(
                self.macro_graph,
                self.local_graphs,
                current.map_id,
                current.at,
                request.goal_map,
                blocked=request.blocked,
                capabilities=current.capabilities,
                last_outside=current.last_outside_map,
                start_mode=current.mode,
                goal_at=request.goal_at,
            )

        return replan


def require_executable_scenario_bindings(
    scenario: StrategicNavigationScenario,
    specs: tuple[ScenarioObjectiveDestinationSpec, ...],
    bindings: tuple[DestinationRouteBinding, ...],
) -> str:
    """Fail before opening a one-shot episode unless the branch is genuine."""

    if not isinstance(scenario, StrategicNavigationScenario):
        raise TypeError("scenario must be a StrategicNavigationScenario")
    if len(specs) != len(bindings) or len(bindings) < 2:
        raise StrategicScenarioRuntimeError(
            "scenario candidate binding count differs from its registry"
        )
    if tuple(item.objective_id for item in specs) != scenario.candidate_objective_ids:
        raise StrategicScenarioRuntimeError(
            "scenario candidate binding order differs from its registry"
        )
    if any(
        binding.destination_ref != spec.destination_ref
        or binding.semantic_tags != spec.semantic_tags
        for spec, binding in zip(specs, bindings, strict=True)
    ):
        raise StrategicScenarioRuntimeError(
            "scenario candidate binding identity differs"
        )
    unavailable = tuple(
        spec.objective_id
        for spec, binding in zip(specs, bindings, strict=True)
        if binding.plan is None
    )
    if unavailable:
        raise StrategicScenarioRuntimeError(
            "scenario rehearsal has an unavailable declared candidate"
        )
    selected_index = scenario.candidate_objective_ids.index(
        scenario.teacher_objective_id
    )
    return bindings[selected_index].destination_ref


@dataclass(frozen=True, slots=True)
class StrategicScenarioRehearsalResult:
    report: RouteExecutionReport
    dataset: CollectedStrategicNavigationDataset
    episode_summary: Mapping[str, object]

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "strategic-navigation-scenario-rehearsal-result-v1",
            "status": "complete",
            "episode": dict(self.episode_summary),
            "dataset": self.dataset.public_summary(),
            "route": {
                "acknowledged_steps": len(self.report.executed_steps),
                "interruptions": len(self.report.interruptions),
                "movement_requests": self.report.movement_requests,
                "replans": len(self.report.replans),
                "wait_actions": self.report.wait_actions,
            },
        }


InterruptionHandlerFactory = Callable[
    [RecordingExecutor[MacroAction, object]], InterruptionHandler | None
]


def record_strategic_scenario_rehearsal(
    private_root: PrivateArtifactRoot,
    *,
    assignment: StrategicNavigationScenarioRehearsalAssignment,
    scenario: StrategicNavigationScenario,
    metadata: Mapping[str, object],
    snapshot_provider: SnapshotProvider,
    action_delegate: RouteActionPort,
    traversal_observer: TraversalObserver,
    bindings: tuple[DestinationRouteBinding, ...],
    selected_destination_ref: str,
    interruption_handler_factory: InterruptionHandlerFactory | None = None,
    replanner: RouteReplanner | None = None,
    resource_manager: RouteResourceManager | None = None,
    limits: RouteExecutionLimits = DEFAULT_ROUTE_EXECUTION_LIMITS,
) -> StrategicScenarioRehearsalResult:
    """Durably join one record-before-act choice and exactly one outcome."""

    if not isinstance(private_root, PrivateArtifactRoot):
        raise TypeError("private_root must be a PrivateArtifactRoot")
    if not isinstance(assignment, StrategicNavigationScenarioRehearsalAssignment):
        raise TypeError("assignment must be a scenario rehearsal assignment")
    if assignment.scenario_id != scenario.scenario_id:
        raise StrategicScenarioRuntimeError(
            "scenario rehearsal assignment differs from requested scenario"
        )
    expected_refs = tuple(
        f"pokemon.red:objective:{objective_id}:approach"
        for objective_id in scenario.candidate_objective_ids
    )
    if tuple(binding.destination_ref for binding in bindings) != expected_refs:
        raise StrategicScenarioRuntimeError(
            "scenario rehearsal bindings differ from the preregistered candidates"
        )
    expected_selected = (
        f"pokemon.red:objective:{scenario.teacher_objective_id}:approach"
    )
    if selected_destination_ref != expected_selected:
        raise StrategicScenarioRuntimeError(
            "scenario rehearsal selection differs from the preregistered teacher"
        )
    expected_metadata = assignment.episode_metadata()
    for key in ("collection", "policy", "source", "source_bundle_sha256", "split"):
        if metadata.get(key) != expected_metadata[key]:
            raise StrategicScenarioRuntimeError(
                "scenario rehearsal metadata differs from its assignment"
            )

    writer = private_root.begin_episode(assignment.episode_id)
    with writer:
        sink = EpisodeTrajectorySink(
            writer,
            episode_id=assignment.episode_id,
            game_id=POKEMON_RED_GAME_ID,
        )
        sink.write_episode_header(metadata=metadata)
        recorder: RecordingExecutor[MacroAction, object] = RecordingExecutor(
            delegate=action_delegate,
            snapshot_provider=snapshot_provider,
            sink=sink,
            episode_id=assignment.episode_id,
        )
        trajectory = StrategicNavigationTrajectoryObserver(
            assignment=assignment,
            snapshot_provider=snapshot_provider,
            recorder=recorder,
            sink=sink,
        )
        interruption_handler = (
            interruption_handler_factory(recorder)
            if interruption_handler_factory is not None
            else None
        )
        report = execute_strategic_navigation_route(
            trajectory,
            semantic_need_tags=(
                StrategicNavigationTag.ADVANCE_STORY,
                StrategicNavigationTag.REACH_NEXT_CHALLENGE,
            ),
            origin_semantic_tags=(
                StrategicNavigationTag.OVERWORLD,
                StrategicNavigationTag.SAFE_HUB,
            ),
            origin_region_ref=f"pokemon.red:region:{scenario.origin_region}",
            bindings=bindings,
            selected_destination_ref=selected_destination_ref,
            actions=recorder,
            traversal_observer=traversal_observer,
            interruption_handler=interruption_handler,
            replanner=replanner,
            resource_manager=resource_manager,
            limits=limits,
        )
        trajectory.require_settled()
        if recorder.recording_failures:
            raise StrategicScenarioRuntimeError(
                "scenario trajectory instrumentation failed"
            )
        sink.record_event(
            SparseEvent(
                event_id=f"{assignment.episode_id}:terminal",
                episode_id=assignment.episode_id,
                step_index=recorder.next_step_index,
                kind="terminal",
                payload={
                    "status": "complete",
                    "scenario_rehearsal_complete": True,
                    "strategic_decisions": 1,
                    "strategic_outcomes": 1,
                },
            )
        )
        sink.finalize()

    dataset = load_assigned_strategic_navigation_episode(
        private_root.open_episode(assignment.episode_id),
        assignment=assignment,
    )
    if (
        len(dataset.examples) != 1
        or dataset.examples[0].outcome_status.value != "succeeded"
    ):
        raise StrategicNavigationDatasetError(
            "completed scenario rehearsal failed strict trajectory reload"
        )
    return StrategicScenarioRehearsalResult(
        report=report,
        dataset=dataset,
        episode_summary=writer.summary.public_dict(),
    )
