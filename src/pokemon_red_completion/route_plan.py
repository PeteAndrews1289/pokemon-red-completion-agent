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

from collections.abc import Mapping
from dataclasses import dataclass

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.global_router import (
    Coordinate,
    MacroEdge,
    MacroGraph,
    MacroPath,
    MacroTransition,
    find_macro_path,
)
from pokemon_red_completion.local_router import (
    LocalGraph,
    LocalPath,
    LocalRouterError,
    TraversalMode,
    find_local_path,
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

    def __post_init__(self) -> None:
        if not self.action:
            raise ValueError("a route step needs an action")
        if not self.kind:
            raise ValueError("a route step needs a transition kind")
        if not isinstance(self.action_kind, MacroActionKind):
            raise TypeError("a route step action kind must be a MacroActionKind")

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
        if edge.kind == "connection":
            approach, transition = _best_connection(
                local,
                current_at,
                edge,
                capabilities=capabilities,
                start_mode=current_mode,
            )
            action_in_approach = False
        elif edge.kind in {"warp", "return"}:
            approach, transition, action_in_approach = _warp_transition(
                graph,
                local,
                current_at,
                target_map,
                edge,
                capabilities=capabilities,
                start_mode=current_mode,
            )
        else:
            raise RoutePlanningError(f"map {source_map} uses unsupported {edge.kind!r} transition")
        segments.append(
            RouteSegment(
                source_map=source_map,
                target_map=target_map,
                approach=approach,
                transition=transition,
                passage_kind=edge.kind,
                transition_action_in_approach=action_in_approach,
            )
        )
        current_at = transition.arrival_at
        current_mode = approach.modes[-1]
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
    """Search both routing layers while excluding currently observed blockers."""

    unavailable = {} if blocked is None else blocked
    projected = {
        map_id: without_coordinates(local, unavailable.get(map_id, frozenset()))
        for map_id, local in local_graphs.items()
    }
    macro_path = find_macro_path(
        graph,
        start_map,
        goal_map,
        last_outside=last_outside,
    )
    return compose_route(
        graph,
        macro_path,
        projected,
        start_at,
        capabilities=capabilities,
        start_mode=start_mode,
        goal_at=goal_at,
        goal_mode=goal_mode,
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
        )
        for index, edge in enumerate(path.edges)
    )


def _best_connection(
    local: LocalGraph,
    start: Coordinate,
    edge: MacroEdge,
    *,
    capabilities: frozenset[str],
    start_mode: TraversalMode,
) -> tuple[LocalPath, MacroTransition]:
    if not edge.coordinate_transitions:
        raise RoutePlanningError("a connection has no decoded coordinate transitions")
    candidates: list[tuple[int, int, LocalPath, MacroTransition]] = []
    for order, transition in enumerate(edge.coordinate_transitions):
        try:
            approach = find_local_path(
                local,
                start,
                transition.exit_at,
                capabilities=capabilities,
                start_mode=start_mode,
            )
        except LocalRouterError:
            continue
        cost = sum(local_edge.cost for local_edge in approach.edges) + edge.cost
        candidates.append((cost, order, approach, transition))
    if not candidates:
        raise RoutePlanningError("no decoded connection coordinate is locally reachable")
    _, _, approach, transition = min(candidates, key=lambda candidate: candidate[:2])
    return approach, transition


def _warp_transition(
    graph: MacroGraph,
    local: LocalGraph,
    start: Coordinate,
    target_map: int,
    edge: MacroEdge,
    *,
    capabilities: frozenset[str],
    start_mode: TraversalMode,
) -> tuple[LocalPath, MacroTransition, bool]:
    if edge.at is None:
        raise RoutePlanningError("a warp has no trigger coordinate")
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
    action_in_approach = edge.exit_action is None
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
        if edge.exit_action in {"up", "down"}:
            # A vertical boundary return is the ordinary Gen I doorway case:
            # the engine walks the player one tile beyond the destination warp.
            # Horizontal pass-through gates instead settle *on* the outside
            # warp tile.  Treating both animations alike made the Route 7 gate
            # predict (10, 19) after a right exit while live RAM reported the
            # cartridge's actual (10, 18).
            dy, dx = {
                "up": (-1, 0),
                "down": (1, 0),
            }.get(edge.exit_action, (0, 0))
            if (dy, dx) == (0, 0):
                raise RoutePlanningError(
                    f"unsupported boundary return action {edge.exit_action!r}"
                )
            arrival = arrival[0] + dy, arrival[1] + dx
        elif edge.exit_action not in {None, "left", "right"}:
            raise RoutePlanningError(
                f"unsupported boundary return action {edge.exit_action!r}"
            )
    if arrival is None:
        raise RoutePlanningError("an ordinary warp has no decoded arrival coordinate")
    action = edge.exit_action if edge.exit_action is not None else approach.edges[-1].action
    return (
        approach,
        MacroTransition(
            exit_at=edge.at,
            arrival_at=arrival,
            action=action,
        ),
        action_in_approach,
    )
