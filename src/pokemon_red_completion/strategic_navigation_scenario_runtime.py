"""Plan, execute and strictly reload one short strategic rehearsal."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace

from pokemon_red_completion.actions import MacroAction
from pokemon_red_completion.gen1_cut import (
    CUT_PASSAGE_TILES,
    CutTraversalError,
    plan_cut_candidate_in_graphs,
    staged_cut_path,
)
from pokemon_red_completion.gen1_maps import macro_graph_from_nodes, map_graph
from pokemon_red_completion.gen1_story_routing import (
    GEN1_STORY_PASSAGE_REQUIREMENTS,
    apply_gen1_seafoam_current_requirements,
    apply_gen1_story_requirements,
    gen1_story_static_object_blockers,
)
from pokemon_red_completion.gen1_terrain import (
    Terrain,
    Tileset,
    terrain_with_block,
    tilesets,
    walkable_world,
    water_tilesets,
)
from pokemon_red_completion.gen1_traversal import (
    CUT_CAPABILITY,
    LAND_MODE,
    TraversalRules,
    map_object_events,
    surf_local_graph,
    traversal_rules,
)
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalGraph, LocalPath, without_coordinates
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
from pokemon_red_completion.route_plan import (
    RoutePlan,
    RoutePlanningError,
    plan_route,
    without_warp_transit,
)
from pokemon_red_completion.semantic_traversal import apply_local_passage_requirements
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
    rom: bytes
    terrain: Mapping[int, Terrain]
    rules: TraversalRules
    tilesets: Mapping[int, Tileset]
    water_tilesets: frozenset[int]
    object_blockers: Mapping[int, frozenset[tuple[int, int]]]

    @classmethod
    def from_rom(cls, rom: bytes) -> StrategicScenarioRouteWorld:
        if not isinstance(rom, bytes) or not rom:
            raise ValueError("scenario routing requires immutable ROM bytes")
        maps = map_graph(rom)
        rules = traversal_rules(rom, maps)
        terrain = walkable_world(rom)
        sets = tilesets(rom)
        surf_sets = water_tilesets(rom)
        blockers = {
            map_id: gen1_story_static_object_blockers(
                map_id,
                (event.at for event in map_object_events(rom, {map_id})),
            )
            for map_id in terrain
        }
        local_graphs = apply_gen1_story_requirements(
            {
                map_id: surf_local_graph(
                    local,
                    rules,
                    blocked=blockers[map_id],
                )
                for map_id, local in terrain.items()
            }
        )
        return cls(
            macro_graph_from_nodes(maps),
            local_graphs,
            rom,
            terrain,
            rules,
            sets,
            surf_sets,
            blockers,
        )

    def _graph_for_terrain(self, terrain: Terrain) -> LocalGraph:
        """Rebuild one predicted grid without dropping global requirements."""

        map_id = terrain.map_id
        graph = surf_local_graph(
            terrain,
            self.rules,
            blocked=self.object_blockers[map_id],
        )
        requirements = tuple(
            requirement
            for requirement in GEN1_STORY_PASSAGE_REQUIREMENTS
            if requirement.map_id == map_id
        )
        if requirements:
            graph = apply_local_passage_requirements(
                {map_id: graph},
                requirements,
            )[map_id]
        return apply_gen1_seafoam_current_requirements({map_id: graph})[map_id]

    def _staged_cut_plan(
        self,
        start: TraversalSnapshot,
        goal_map: int,
        *,
        goal_at: tuple[int, int] | None = None,
        blocked: Mapping[int, frozenset[tuple[int, int]]] | None = None,
    ) -> RoutePlan:
        """Find the cheapest route enabled by exactly one explicit Cut action."""

        if CUT_CAPABILITY not in start.capabilities:
            raise RoutePlanningError("the observed party cannot use Cut")
        unavailable = (
            {start.map_id: start.occupied}
            if blocked is None
            else blocked
        )
        replacements = {swap.before: swap.after for swap in self.rules.cut_block_swaps}
        candidates: list[tuple[RoutePlan, int, tuple[int, int]]] = []
        for map_id, terrain in self.terrain.items():
            if terrain.blocks is None:
                continue
            eligible_tiles = CUT_PASSAGE_TILES.get(terrain.tileset, frozenset())
            blocks = sorted(
                {
                    (y // 2, x // 2)
                    for y, row in enumerate(terrain.tiles)
                    for x, tile in enumerate(row)
                    if tile in eligible_tiles and terrain.blocks[y // 2][x // 2] in replacements
                }
            )
            for block_at in blocks:
                before_block = terrain.blocks[block_at[0]][block_at[1]]
                predicted = terrain_with_block(
                    self.rom,
                    terrain,
                    block_at,
                    replacements[before_block],
                    self.tilesets,
                    water_set_ids=self.water_tilesets,
                )
                predicted_graphs = dict(self.local_graphs)
                predicted_graphs[map_id] = self._graph_for_terrain(predicted)
                try:
                    hypothetical = plan_route(
                        self.macro_graph,
                        predicted_graphs,
                        start.map_id,
                        start.at,
                        goal_map,
                        blocked=unavailable,
                        capabilities=start.capabilities,
                        last_outside=start.last_outside_map,
                        start_mode=start.mode,
                        goal_at=goal_at,
                    )
                except RoutePlanningError:
                    continue

                local_uses: list[tuple[int | None, LocalPath]] = [
                    (index, segment.approach)
                    for index, segment in enumerate(hypothetical.segments)
                    if segment.source_map == map_id
                ]
                if (
                    hypothetical.terminal_map == map_id
                    and hypothetical.terminal_approach is not None
                ):
                    local_uses.append((None, hypothetical.terminal_approach))
                for segment_index, local_use in local_uses:
                    map_blocked = unavailable.get(map_id, frozenset())
                    before_graph = without_warp_transit(
                        without_coordinates(
                            self.local_graphs[map_id],
                            map_blocked,
                        ),
                        self.macro_graph.warp_locations.get(map_id, ()),
                        start_at=local_use.coordinates[0],
                    )

                    def graph_builder(
                        changed: Terrain,
                        *,
                        blocked: frozenset[tuple[int, int]] = map_blocked,
                        warp_locations: tuple[tuple[int, int], ...] = (
                            self.macro_graph.warp_locations.get(map_id, ())
                        ),
                        local_start: tuple[int, int] = local_use.coordinates[0],
                    ) -> LocalGraph:
                        return without_warp_transit(
                            without_coordinates(
                                self._graph_for_terrain(changed),
                                blocked,
                            ),
                            warp_locations,
                            start_at=local_start,
                        )

                    try:
                        cut = plan_cut_candidate_in_graphs(
                            self.rom,
                            terrain,
                            self.rules,
                            self.tilesets,
                            local_use.coordinates[0],
                            local_use.coordinates[-1],
                            capabilities=start.capabilities,
                            before_graph=before_graph,
                            graph_builder=graph_builder,
                            start_mode=local_use.modes[0],
                            field_mode=LAND_MODE,
                            goal_mode=local_use.modes[-1],
                            required_block_at=block_at,
                            water_set_ids=self.water_tilesets,
                        )
                    except CutTraversalError:
                        continue
                    staged = staged_cut_path(cut)
                    if segment_index is None:
                        candidate = replace(
                            hypothetical,
                            terminal_approach=staged,
                            terminal_at=staged.coordinates[-1],
                            terminal_mode=staged.modes[-1],
                        )
                    else:
                        segments = list(hypothetical.segments)
                        segments[segment_index] = replace(
                            segments[segment_index],
                            approach=staged,
                        )
                        candidate = replace(hypothetical, segments=tuple(segments))
                    candidates.append((candidate, map_id, block_at))
        if not candidates:
            raise RoutePlanningError(
                f"no staged Cut route from map {start.map_id} to map {goal_map}"
            )
        return min(
            candidates,
            key=lambda item: (
                item[0].cost,
                item[1],
                item[2],
                item[0].actions,
            ),
        )[0]

    def _plan_candidate(
        self,
        start: TraversalSnapshot,
        goal_map: int,
        *,
        goal_at: tuple[int, int] | None = None,
        blocked: Mapping[int, frozenset[tuple[int, int]]] | None = None,
    ) -> RoutePlan:
        try:
            return plan_route(
                self.macro_graph,
                self.local_graphs,
                start.map_id,
                start.at,
                goal_map,
                blocked=({start.map_id: start.occupied} if blocked is None else blocked),
                capabilities=start.capabilities,
                last_outside=start.last_outside_map,
                start_mode=start.mode,
                goal_at=goal_at,
            )
        except RoutePlanningError:
            return self._staged_cut_plan(
                start,
                goal_map,
                goal_at=goal_at,
                blocked=blocked,
            )

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
                plan = self._plan_candidate(start, spec.goal_map.value)
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

    def plan_to_any_map(
        self,
        start: TraversalSnapshot,
        goal_maps: frozenset[int],
    ) -> RoutePlan:
        """Choose the cheapest deterministic route to one declared origin map."""

        if not isinstance(start, TraversalSnapshot):
            raise TypeError("scenario relocation start must be a traversal snapshot")
        if (
            not isinstance(goal_maps, frozenset)
            or not goal_maps
            or any(type(item) is not int or item < 0 for item in goal_maps)  # noqa: E721
        ):
            raise TypeError("scenario relocation goals must be non-negative map IDs")
        candidates: list[RoutePlan] = []
        for goal_map in sorted(goal_maps):
            try:
                candidates.append(self._plan_candidate(start, goal_map))
            except RoutePlanningError:
                continue
        if not candidates:
            raise RoutePlanningError("no route reaches a declared scenario origin")
        return min(
            candidates,
            key=lambda plan: (
                plan.cost,
                plan.terminal_map,
                plan.terminal_at,
                plan.actions,
            ),
        )

    def plan_to_map(
        self,
        start: TraversalSnapshot,
        goal_map: int,
        *,
        goal_at: tuple[int, int] | None = None,
    ) -> RoutePlan:
        """Plan one explicit construction relocation, optionally to a coordinate."""

        if not isinstance(start, TraversalSnapshot):
            raise TypeError("scenario relocation start must be a traversal snapshot")
        if type(goal_map) is not int or goal_map < 0:  # noqa: E721
            raise TypeError("scenario relocation goal must be a non-negative map ID")
        return self._plan_candidate(start, goal_map, goal_at=goal_at)

    def replanner(self) -> RouteReplanner:
        """Recompute the same declared goal after a measured live blocker."""

        def replan(request: ReplanRequest) -> RoutePlan:
            current = request.current
            return self._plan_candidate(
                current,
                request.goal_map,
                blocked=request.blocked,
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
