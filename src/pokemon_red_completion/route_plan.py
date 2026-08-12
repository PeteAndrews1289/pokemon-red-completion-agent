"""Compose map-level choices and local movement into executable actions.

The two routers deliberately solve different problems. ``global_router`` finds
which maps to cross, while ``local_router`` finds legal movement within one map.
This module is the seam between them: it selects an exact cartridge-derived
connection endpoint or warp, routes to it, and carries the observed arrival into
the next local search.

The result is still a static candidate. A live executor must re-observe after
each transition and account for NPCs and story state before trusting the next
segment.
"""

from __future__ import annotations

import heapq
from collections.abc import Mapping
from dataclasses import dataclass

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.global_router import (
    Coordinate,
    MacroEdge,
    MacroGraph,
    MacroPath,
    MacroTransition,
    advance_macro_state,
)
from pokemon_red_completion.local_router import (
    LocalGoal,
    LocalGraph,
    LocalPath,
    LocalRouterError,
    TraversalMode,
    find_local_path,
    find_local_paths,
    without_coordinates,
)


class RoutePlanningError(RuntimeError):
    """Raised when a map path cannot be turned into truthful actions."""


@dataclass(frozen=True, slots=True)
class RouteStep:
    """One requested movement and the exact state that acknowledges it."""

    source_map: int
    source_at: Coordinate
    action: str
    expected_map: int
    expected_at: Coordinate
    kind: str
    action_kind: MacroActionKind
    source_mode: TraversalMode
    expected_mode: TraversalMode
    transient_at: Coordinate | None = None

    def __post_init__(self) -> None:
        if not self.action:
            raise ValueError("a route step needs an action")
        if not self.kind:
            raise ValueError("a route step needs a transition kind")
        if not isinstance(self.action_kind, MacroActionKind):
            raise TypeError("a route step action kind must be a MacroActionKind")
        if self.transient_at in {self.source_at, self.expected_at}:
            raise ValueError("a route-step transient must differ from both endpoints")

    @property
    def macro_action(self) -> MacroAction:
        return MacroAction(self.action_kind, self.action)

    @property
    def stays_on_map(self) -> bool:
        return self.source_map == self.expected_map

    @property
    def can_discover_blocker(self) -> bool:
        return self.kind == "walk" and self.stays_on_map and self.source_mode == self.expected_mode


@dataclass(frozen=True, slots=True)
class RouteSegment:
    """One local approach followed by one cross-map transition."""

    source_map: int
    target_map: int
    approach: LocalPath
    transition: MacroTransition
    passage_kind: str
    #: Stepping onto a warp is itself the transition. Connections instead need
    #: one extra action after reaching the border coordinate.
    transition_action_in_approach: bool

    def __post_init__(self) -> None:
        if not self.passage_kind:
            raise ValueError("a route segment needs a passage kind")
        if self.approach.coordinates[-1] != self.transition.exit_at:
            raise ValueError("a route segment's approach must end at its transition")
        if self.transition_action_in_approach:
            if not self.approach.edges:
                raise ValueError("a warp requires movement onto its trigger coordinate")
            if self.approach.edges[-1].action != self.transition.action:
                raise ValueError("a warp transition must retain its triggering action")

    @property
    def actions(self) -> tuple[str, ...]:
        actions = tuple(edge.action for edge in self.approach.edges)
        if self.transition_action_in_approach:
            return actions
        return (*actions, self.transition.action)


@dataclass(frozen=True, slots=True)
class RoutePlan:
    """A continuous, coordinate-preserving execution candidate."""

    macro_path: MacroPath
    start_at: Coordinate
    start_mode: TraversalMode
    segments: tuple[RouteSegment, ...]
    terminal_approach: LocalPath | None
    terminal_at: Coordinate
    terminal_mode: TraversalMode

    def __post_init__(self) -> None:
        if len(self.segments) != len(self.macro_path.edges):
            raise ValueError("a route plan needs one segment per macro edge")
        current_at = self.start_at
        current_mode = self.start_mode
        for index, segment in enumerate(self.segments):
            if (segment.source_map, segment.target_map) != (
                self.macro_path.maps[index],
                self.macro_path.maps[index + 1],
            ):
                raise ValueError("a route segment must follow its macro path")
            if segment.approach.coordinates[0] != current_at:
                raise ValueError("adjacent route segments must share an arrival coordinate")
            if segment.approach.modes[0] != current_mode:
                raise ValueError("adjacent route segments must preserve movement mode")
            current_at = segment.transition.arrival_at
            current_mode = segment.approach.modes[-1]
        if self.terminal_approach is not None:
            if self.terminal_approach.coordinates[0] != current_at:
                raise ValueError("the terminal approach must begin at the last map arrival")
            if self.terminal_approach.modes[0] != current_mode:
                raise ValueError("the terminal approach must preserve movement mode")
            current_at = self.terminal_approach.coordinates[-1]
            current_mode = self.terminal_approach.modes[-1]
        if (self.terminal_at, self.terminal_mode) != (current_at, current_mode):
            raise ValueError("the route terminal must match its final local state")

    @property
    def actions(self) -> tuple[str, ...]:
        return tuple(step.action for step in self.steps)

    @property
    def macro_actions(self) -> tuple[MacroAction, ...]:
        return tuple(step.macro_action for step in self.steps)

    @property
    def steps(self) -> tuple[RouteStep, ...]:
        """Flatten local edges and passages into live acknowledgement contracts."""

        steps: list[RouteStep] = []
        for segment in self.segments:
            coordinates = segment.approach.coordinates
            modes = segment.approach.modes
            for index, edge in enumerate(segment.approach.edges):
                triggers_passage = (
                    segment.transition_action_in_approach
                    and index == len(segment.approach.edges) - 1
                )
                steps.append(
                    RouteStep(
                        source_map=segment.source_map,
                        source_at=coordinates[index],
                        action=edge.action,
                        expected_map=(
                            segment.target_map if triggers_passage else segment.source_map
                        ),
                        expected_at=(
                            segment.transition.arrival_at if triggers_passage else edge.target
                        ),
                        kind=segment.passage_kind if triggers_passage else edge.kind,
                        action_kind=edge.action_kind,
                        source_mode=modes[index],
                        expected_mode=modes[index + 1],
                        transient_at=(None if triggers_passage else edge.transient),
                    )
                )
            if not segment.transition_action_in_approach:
                steps.append(
                    RouteStep(
                        source_map=segment.source_map,
                        source_at=segment.transition.exit_at,
                        action=segment.transition.action,
                        expected_map=segment.target_map,
                        expected_at=segment.transition.arrival_at,
                        kind=segment.passage_kind,
                        action_kind=MacroActionKind.MOVE,
                        source_mode=modes[-1],
                        expected_mode=modes[-1],
                    )
                )
        if self.terminal_approach is not None:
            steps.extend(
                _local_steps(
                    self.terminal_map,
                    self.terminal_approach,
                )
            )
        return tuple(steps)

    @property
    def terminal_map(self) -> int:
        return self.macro_path.maps[-1]

    @property
    def cost(self) -> int:
        """Combined local movement and declared cross-map passage cost."""

        segment_cost = sum(
            sum(edge.cost for edge in segment.approach.edges) + macro_edge.cost
            for segment, macro_edge in zip(
                self.segments,
                self.macro_path.edges,
                strict=True,
            )
        )
        terminal_cost = (
            0
            if self.terminal_approach is None
            else sum(edge.cost for edge in self.terminal_approach.edges)
        )
        return segment_cost + terminal_cost


def compose_route(
    graph: MacroGraph,
    macro_path: MacroPath,
    local_graphs: Mapping[int, LocalGraph],
    start_at: Coordinate,
    *,
    capabilities: frozenset[str] = frozenset(),
    start_mode: TraversalMode = None,
    goal_at: Coordinate | None = None,
    goal_mode: TraversalMode = None,
) -> RoutePlan:
    """Choose exact endpoints and optionally reach a coordinate on the final map."""

    if goal_at is None and goal_mode is not None:
        raise ValueError("a goal movement mode requires a goal coordinate")

    current_at = start_at
    current_mode = start_mode
    segments: list[RouteSegment] = []
    for source_map, target_map, edge in zip(
        macro_path.maps[:-1],
        macro_path.maps[1:],
        macro_path.edges,
        strict=True,
    ):
        local = local_graphs.get(source_map)
        if local is None:
            raise RoutePlanningError(f"map {source_map} has no local traversal graph")
        segment = _compose_segment(
            graph,
            local,
            _ComposedState(source_map, current_at, current_mode, None),
            target_map,
            edge,
            capabilities=capabilities,
        )
        segments.append(segment)
        current_at = segment.transition.arrival_at
        current_mode = segment.approach.modes[-1]
    terminal_approach: LocalPath | None = None
    if goal_at is not None:
        terminal_map = macro_path.maps[-1]
        local = local_graphs.get(terminal_map)
        if local is None:
            raise RoutePlanningError(f"terminal map {terminal_map} has no local traversal graph")
        try:
            terminal_approach = find_local_path(
                local,
                current_at,
                goal_at,
                capabilities=capabilities,
                start_mode=current_mode,
                goal_mode=goal_mode,
            )
        except LocalRouterError as error:
            raise RoutePlanningError(
                f"terminal coordinate {goal_at} is not locally reachable"
            ) from error
        current_at = terminal_approach.coordinates[-1]
        current_mode = terminal_approach.modes[-1]
    return RoutePlan(
        macro_path=macro_path,
        start_at=start_at,
        start_mode=start_mode,
        segments=tuple(segments),
        terminal_approach=terminal_approach,
        terminal_at=current_at,
        terminal_mode=current_mode,
    )


def plan_route(
    graph: MacroGraph,
    local_graphs: Mapping[int, LocalGraph],
    start_map: int,
    start_at: Coordinate,
    goal_map: int,
    *,
    blocked: Mapping[int, frozenset[Coordinate]] | None = None,
    capabilities: frozenset[str] = frozenset(),
    last_outside: int | None = None,
    start_mode: TraversalMode = None,
    goal_at: Coordinate | None = None,
    goal_mode: TraversalMode = None,
) -> RoutePlan:
    """Jointly price map passages and local movement around live blockers.

    A topology-only macro path can be locally impossible or much more
    expensive than a route through additional maps. The search state therefore
    retains map, coordinate, movement mode and outside-return context. Every
    candidate macro edge is priced by its cheapest reachable exact passage,
    and a coordinate goal on the final map is part of that same optimization.
    """

    unavailable = {} if blocked is None else blocked
    projected = {
        map_id: without_coordinates(local, unavailable.get(map_id, frozenset()))
        for map_id, local in local_graphs.items()
    }
    return _find_composed_route(
        graph,
        projected,
        start_map,
        start_at,
        goal_map,
        capabilities=capabilities,
        last_outside=last_outside,
        start_mode=start_mode,
        goal_at=goal_at,
        goal_mode=goal_mode,
    )


@dataclass(frozen=True, slots=True)
class _ComposedState:
    map_id: int
    at: Coordinate
    mode: TraversalMode
    last_outside: int | None


def _find_composed_route(
    graph: MacroGraph,
    local_graphs: Mapping[int, LocalGraph],
    start_map: int,
    start_at: Coordinate,
    goal_map: int,
    *,
    capabilities: frozenset[str],
    last_outside: int | None,
    start_mode: TraversalMode,
    goal_at: Coordinate | None,
    goal_mode: TraversalMode,
) -> RoutePlan:
    if goal_at is None and goal_mode is not None:
        raise ValueError("a goal movement mode requires a goal coordinate")

    start = _ComposedState(start_map, start_at, start_mode, last_outside)
    frontier: list[tuple[int, int, _ComposedState]] = [(0, 0, start)]
    best_cost: dict[_ComposedState, int] = {start: 0}
    came_from: dict[
        _ComposedState,
        tuple[_ComposedState, MacroEdge, RouteSegment],
    ] = {}
    best_goal: tuple[int, int, _ComposedState, LocalPath | None] | None = None
    local_path_cache: dict[
        tuple[int, Coordinate, TraversalMode],
        dict[LocalGoal, LocalPath],
    ] = {}
    sequence = 1

    while frontier:
        cost, _, state = heapq.heappop(frontier)
        if cost != best_cost.get(state):
            continue
        if best_goal is not None and cost >= best_goal[0]:
            break

        if state.map_id == goal_map and goal_at is None:
            best_goal = (cost, sequence, state, None)
            break

        local = local_graphs.get(state.map_id)
        if local is None:
            continue
        local = _without_warp_transit(
            local,
            graph.warp_locations.get(state.map_id, ()),
            start_at=state.at,
        )
        cache_key = (state.map_id, state.at, state.mode)
        local_paths = local_path_cache.get(cache_key)
        if local_paths is None:
            goals = _local_goals(graph, state.map_id)
            if state.map_id == goal_map and goal_at is not None:
                goals.add((goal_at, goal_mode))
            local_paths = find_local_paths(
                local,
                state.at,
                goals,
                capabilities=capabilities,
                start_mode=state.mode,
            )
            local_path_cache[cache_key] = local_paths

        if state.map_id == goal_map and goal_at is not None:
            terminal = local_paths.get((goal_at, goal_mode))
            if terminal is not None:
                terminal_cost = sum(edge.cost for edge in terminal.edges)
                candidate = (cost + terminal_cost, sequence, state, terminal)
                if best_goal is None or candidate[:2] < best_goal[:2]:
                    best_goal = candidate
                sequence += 1
                if terminal_cost == 0:
                    break

        for edge in graph.neighbors(state.map_id):
            advanced = advance_macro_state(
                graph,
                (state.map_id, state.last_outside),
                edge,
            )
            if advanced is None:
                continue
            target_map, next_last_outside = advanced
            try:
                candidates = _compose_segment_candidates(
                    graph,
                    local,
                    state,
                    target_map,
                    edge,
                    capabilities=capabilities,
                    local_paths=local_paths,
                )
            except RoutePlanningError:
                continue
            for segment in candidates:
                segment_cost = sum(local_edge.cost for local_edge in segment.approach.edges)
                candidate_cost = cost + segment_cost + edge.cost
                following = _ComposedState(
                    target_map,
                    segment.transition.arrival_at,
                    segment.approach.modes[-1],
                    next_last_outside,
                )
                if candidate_cost >= best_cost.get(following, candidate_cost + 1):
                    continue
                best_cost[following] = candidate_cost
                came_from[following] = (state, edge, segment)
                heapq.heappush(frontier, (candidate_cost, sequence, following))
                sequence += 1

    if best_goal is None:
        destination = f"map {goal_map}"
        if goal_at is not None:
            destination += f" coordinate {goal_at}"
        raise RoutePlanningError(
            f"no locally composable route from map {start_map} {start_at} to {destination}"
        )
    _, _, terminal_state, terminal_approach = best_goal
    return _reconstruct_composed_route(
        came_from,
        start,
        terminal_state,
        terminal_approach,
    )


def _without_warp_transit(
    graph: LocalGraph,
    warp_locations: tuple[Coordinate, ...],
    *,
    start_at: Coordinate,
) -> LocalGraph:
    """Make every unrelated warp an endpoint rather than traversable floor.

    Entering a warp immediately changes maps, so a local path may end on one
    but cannot leave it while pretending to remain on the same map.  The sole
    exception is the route's observed start coordinate: exterior arrivals may
    legitimately settle on a warp tile and must be able to walk away.
    """

    absorbing = frozenset(warp_locations).difference({start_at})
    if not absorbing:
        return graph
    return LocalGraph(
        {
            source: (() if source in absorbing else outgoing)
            for source, outgoing in graph.edges.items()
        }
    )


def _local_goals(graph: MacroGraph, map_id: int) -> set[LocalGoal]:
    goals: set[LocalGoal] = set()
    for edge in graph.neighbors(map_id):
        if edge.kind == "connection":
            goals.update((transition.exit_at, None) for transition in edge.coordinate_transitions)
        elif edge.kind in {"warp", "return"} and edge.at is not None:
            goals.add((edge.at, None))
    return goals


def _compose_segment(
    graph: MacroGraph,
    local: LocalGraph,
    state: _ComposedState,
    target_map: int,
    edge: MacroEdge,
    *,
    capabilities: frozenset[str],
) -> RouteSegment:
    candidates = _compose_segment_candidates(
        graph,
        local,
        state,
        target_map,
        edge,
        capabilities=capabilities,
        local_paths=None,
    )
    return min(
        enumerate(candidates),
        key=lambda ordered: (
            sum(local_edge.cost for local_edge in ordered[1].approach.edges),
            ordered[0],
        ),
    )[1]


def _compose_segment_candidates(
    graph: MacroGraph,
    local: LocalGraph,
    state: _ComposedState,
    target_map: int,
    edge: MacroEdge,
    *,
    capabilities: frozenset[str],
    local_paths: Mapping[LocalGoal, LocalPath] | None,
) -> tuple[RouteSegment, ...]:
    if edge.kind == "connection":
        if not edge.coordinate_transitions:
            raise RoutePlanningError("a connection has no decoded coordinate transitions")
        candidates: list[RouteSegment] = []
        for transition in edge.coordinate_transitions:
            approach: LocalPath | None
            if local_paths is None:
                try:
                    approach = find_local_path(
                        local,
                        state.at,
                        transition.exit_at,
                        capabilities=capabilities,
                        start_mode=state.mode,
                    )
                except LocalRouterError:
                    continue
            else:
                approach = local_paths.get((transition.exit_at, None))
            if approach is None:
                continue
            candidates.append(
                RouteSegment(
                    source_map=state.map_id,
                    target_map=target_map,
                    approach=approach,
                    transition=transition,
                    passage_kind=edge.kind,
                    transition_action_in_approach=False,
                )
            )
        if not candidates:
            raise RoutePlanningError("no decoded connection coordinate is locally reachable")
        return tuple(candidates)
    if edge.kind in {"warp", "return"}:
        approach, transition, action_in_approach = _warp_transition(
            graph,
            local,
            state.at,
            target_map,
            edge,
            capabilities=capabilities,
            start_mode=state.mode,
            local_paths=local_paths,
        )
        return (
            RouteSegment(
                source_map=state.map_id,
                target_map=target_map,
                approach=approach,
                transition=transition,
                passage_kind=edge.kind,
                transition_action_in_approach=action_in_approach,
            ),
        )
    raise RoutePlanningError(f"map {state.map_id} uses unsupported {edge.kind!r} transition")


def _reconstruct_composed_route(
    came_from: Mapping[
        _ComposedState,
        tuple[_ComposedState, MacroEdge, RouteSegment],
    ],
    start: _ComposedState,
    goal: _ComposedState,
    terminal_approach: LocalPath | None,
) -> RoutePlan:
    states = [goal]
    edges: list[MacroEdge] = []
    segments: list[RouteSegment] = []
    current = goal
    while current != start:
        previous, edge, segment = came_from[current]
        states.append(previous)
        edges.append(edge)
        segments.append(segment)
        current = previous
    ordered_states = tuple(reversed(states))
    ordered_edges = tuple(reversed(edges))
    ordered_segments = tuple(reversed(segments))
    terminal_at = goal.at if terminal_approach is None else terminal_approach.coordinates[-1]
    terminal_mode = goal.mode if terminal_approach is None else terminal_approach.modes[-1]
    return RoutePlan(
        macro_path=MacroPath(
            maps=tuple(state.map_id for state in ordered_states),
            edges=ordered_edges,
        ),
        start_at=start.at,
        start_mode=start.mode,
        segments=ordered_segments,
        terminal_approach=terminal_approach,
        terminal_at=terminal_at,
        terminal_mode=terminal_mode,
    )


def _local_steps(map_id: int, path: LocalPath) -> tuple[RouteStep, ...]:
    return tuple(
        RouteStep(
            source_map=map_id,
            source_at=path.coordinates[index],
            action=edge.action,
            expected_map=map_id,
            expected_at=edge.target,
            kind=edge.kind,
            action_kind=edge.action_kind,
            source_mode=path.modes[index],
            expected_mode=path.modes[index + 1],
            transient_at=edge.transient,
        )
        for index, edge in enumerate(path.edges)
    )


def _warp_transition(
    graph: MacroGraph,
    local: LocalGraph,
    start: Coordinate,
    target_map: int,
    edge: MacroEdge,
    *,
    capabilities: frozenset[str],
    start_mode: TraversalMode,
    local_paths: Mapping[LocalGoal, LocalPath] | None = None,
) -> tuple[LocalPath, MacroTransition, bool]:
    if edge.at is None:
        raise RoutePlanningError("a warp has no trigger coordinate")
    approach: LocalPath | None
    if local_paths is None:
        try:
            approach = find_local_path(
                local,
                start,
                edge.at,
                capabilities=capabilities,
                start_mode=start_mode,
            )
        except LocalRouterError as error:
            raise RoutePlanningError(f"warp at {edge.at} is not locally reachable") from error
    else:
        approach = local_paths.get((edge.at, None))
    if approach is None:
        raise RoutePlanningError(f"warp at {edge.at} is not locally reachable")
    # Gen I suppresses immediate retrigger when an ordinary entry deposits the
    # player on its return warp. Starting on that coordinate therefore needs
    # the decoded outward action. Non-boundary return tiles and top-boundary
    # returns fire when approached from inside, but bottom and horizontal map-
    # edge returns require a separate outward input after reaching the edge.
    # Cerulean's robbed-house rear door and the south Underground Path exit are
    # the live cartridge witnesses for the two vertical cases.
    action_in_approach = edge.exit_action is None or (
        edge.kind == "return" and edge.exit_action == "up" and bool(approach.edges)
    )
    if action_in_approach and not approach.edges:
        raise RoutePlanningError(
            "route begins on a warp trigger; moving away and re-entering is not planned yet"
        )

    arrival = edge.arrival_at
    if edge.kind == "return":
        index = edge.destination_warp_index
        locations = graph.warp_locations.get(target_map, ())
        if index is None or index >= len(locations):
            raise RoutePlanningError(f"return to map {target_map} has no destination warp {index}")
        arrival = locations[index]
        if edge.exit_action in {"up", "down"} and not action_in_approach:
            # Pressing outward through a vertical boundary return plays the
            # doorway animation one tile beyond the exterior warp. The one
            # exception above is an internally approached top return, which
            # fires on the entering step and settles *on* that exterior warp.
            # Horizontal pass-through gates also settle on the outside warp.
            dy, dx = {
                "up": (-1, 0),
                "down": (1, 0),
            }.get(edge.exit_action, (0, 0))
            if (dy, dx) == (0, 0):
                raise RoutePlanningError(f"unsupported boundary return action {edge.exit_action!r}")
            arrival = arrival[0] + dy, arrival[1] + dx
        elif edge.exit_action not in {None, "up", "down", "left", "right"}:
            raise RoutePlanningError(f"unsupported boundary return action {edge.exit_action!r}")
    if arrival is None:
        raise RoutePlanningError("an ordinary warp has no decoded arrival coordinate")
    action = approach.edges[-1].action if action_in_approach else edge.exit_action
    if action is None:  # pragma: no cover - guarded by the cases above
        raise RoutePlanningError("warp transition has no triggering action")
    return (
        approach,
        MacroTransition(
            exit_at=edge.at,
            arrival_at=arrival,
            action=action,
        ),
        action_in_approach,
    )
