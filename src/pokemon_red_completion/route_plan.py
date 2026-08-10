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

from pokemon_red_completion.global_router import (
    Coordinate,
    MacroEdge,
    MacroGraph,
    MacroPath,
    MacroTransition,
)
from pokemon_red_completion.local_router import (
    LocalGraph,
    LocalPath,
    LocalRouterError,
    find_local_path,
)


class RoutePlanningError(RuntimeError):
    """Raised when a map path cannot be turned into truthful actions."""


@dataclass(frozen=True, slots=True)
class RouteSegment:
    """One local approach followed by one cross-map transition."""

    source_map: int
    target_map: int
    approach: LocalPath
    transition: MacroTransition
    #: Stepping onto a warp is itself the transition. Connections instead need
    #: one extra action after reaching the border coordinate.
    transition_action_in_approach: bool

    def __post_init__(self) -> None:
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
    segments: tuple[RouteSegment, ...]
    terminal_at: Coordinate

    def __post_init__(self) -> None:
        if len(self.segments) != len(self.macro_path.edges):
            raise ValueError("a route plan needs one segment per macro edge")
        if self.segments and self.segments[0].approach.coordinates[0] != self.start_at:
            raise ValueError("the first segment must begin at the route start")

    @property
    def actions(self) -> tuple[str, ...]:
        return tuple(action for segment in self.segments for action in segment.actions)

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
) -> RoutePlan:
    """Choose exact reachable endpoints for every edge in ``macro_path``."""

    current_at = start_at
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
            )
            action_in_approach = False
        elif edge.kind in {"warp", "return"}:
            approach, transition = _warp_transition(
                graph,
                local,
                current_at,
                target_map,
                edge,
                capabilities=capabilities,
            )
            action_in_approach = True
        else:
            raise RoutePlanningError(
                f"map {source_map} uses unsupported {edge.kind!r} transition"
            )
        segments.append(
            RouteSegment(
                source_map=source_map,
                target_map=target_map,
                approach=approach,
                transition=transition,
                transition_action_in_approach=action_in_approach,
            )
        )
        current_at = transition.arrival_at
    return RoutePlan(
        macro_path=macro_path,
        start_at=start_at,
        segments=tuple(segments),
        terminal_at=current_at,
    )


def _best_connection(
    local: LocalGraph,
    start: Coordinate,
    edge: MacroEdge,
    *,
    capabilities: frozenset[str],
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
) -> tuple[LocalPath, MacroTransition]:
    if edge.at is None:
        raise RoutePlanningError("a warp has no trigger coordinate")
    try:
        approach = find_local_path(local, start, edge.at, capabilities=capabilities)
    except LocalRouterError as error:
        raise RoutePlanningError(f"warp at {edge.at} is not locally reachable") from error
    if not approach.edges:
        raise RoutePlanningError(
            "route begins on a warp trigger; moving away and re-entering is not planned yet"
        )

    arrival = edge.arrival_at
    if edge.kind == "return":
        index = edge.destination_warp_index
        locations = graph.warp_locations.get(target_map, ())
        if index is None or index >= len(locations):
            raise RoutePlanningError(
                f"return to map {target_map} has no destination warp {index}"
            )
        arrival = locations[index]
    if arrival is None:
        raise RoutePlanningError("an ordinary warp has no decoded arrival coordinate")
    return approach, MacroTransition(
        exit_at=edge.at,
        arrival_at=arrival,
        action=approach.edges[-1].action,
    )
