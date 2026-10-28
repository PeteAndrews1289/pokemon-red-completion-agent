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
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from types import MappingProxyType

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
    _IncrementalLocalPaths,
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


_MAX_LOCAL_INVENTORY_SEARCHES = 256


class _FrozenLocalRouteCache:
    """Bounded query/frontier reuse, owned by one read-only inventory pass."""

    def __init__(self):
        self.graphs = {}
        self.queries = {}
        self.searches = {}
        self.projections = {}
        self.route_macro_graphs = {}
        self.route_worlds = {}
        self.routes = {}
        self.route_invalidated = False
        self.route_hits = 0
        self.route_misses = 0
        self.hits = 0
        self.misses = 0
        self.invalidated = False

    def _retain_graph(self, graph):
        identity = id(graph)
        prior = self.graphs.get(identity)
        if prior is not None and (prior[0] is not graph or graph.edges != prior[1]):
            self.invalidated = True
            raise RoutePlanningError("read-only route inventory changed a local graph")
        if prior is None and len(self.graphs) < 2048:
            self.graphs[identity] = (graph, dict(graph.edges))
        return identity in self.graphs

    def route_key(self, graph, local_graphs, start_map, start_at, goal_map,
                  unavailable, capabilities, last_outside, start_mode, goal_at, goal_mode):
        """Retain all input graphs before reusing one complete pure query."""
        if self.invalidated:
            raise RoutePlanningError("read-only route inventory was invalidated")
        # Subclasses may compute neighbors dynamically; retain their old path.
        if type(graph) is not MacroGraph or any(type(g) is not LocalGraph for g in local_graphs.values()):
            return None
        macro_id, world_id = id(graph), id(local_graphs)
        state = (dict(graph.edges), graph.outside_nodes, dict(graph.warp_locations),
                 dict(graph.retained_outside_overrides),
                 None if graph.warp_arrivals is None else dict(graph.warp_arrivals),
                 None if graph.warp_triggers is None else dict(graph.warp_triggers))
        previous = self.route_macro_graphs.get(macro_id)
        if previous is not None and (previous[0] is not graph or previous[1] != state):
            self.invalidated = self.route_invalidated = True
            raise RoutePlanningError("read-only route inventory changed a macro graph")
        if previous is None:
            if len(self.route_macro_graphs) >= 128:
                return None
            self.route_macro_graphs[macro_id] = (graph, state)
        previous_world = self.route_worlds.get(world_id)
        if previous_world is not None and (
            previous_world[0] is not local_graphs
            or previous_world[1] != {m: id(g) for m, g in local_graphs.items()}
        ):
            self.invalidated = self.route_invalidated = True
            raise RoutePlanningError("read-only route inventory changed a local map inventory")
        if previous_world is None:
            if len(self.route_worlds) >= 128:
                return None
            self.route_worlds[world_id] = (local_graphs, {m: id(g) for m, g in local_graphs.items()})
        retained = True
        for local in local_graphs.values():
            retained = self._retain_graph(local) and retained
        if not retained:
            return None
        return (macro_id, frozenset(self.route_worlds[world_id][1].items()),
                start_map, start_at, goal_map,
                frozenset((m, frozenset(at)) for m, at in unavailable.items()),
                capabilities, last_outside, start_mode, goal_at, goal_mode)

    def verify_routes(self):
        for graph, state in self.route_macro_graphs.values():
            current = (dict(graph.edges), graph.outside_nodes, dict(graph.warp_locations),
                       dict(graph.retained_outside_overrides),
                       None if graph.warp_arrivals is None else dict(graph.warp_arrivals),
                       None if graph.warp_triggers is None else dict(graph.warp_triggers))
            if current != state:
                self.invalidated = self.route_invalidated = True
        for local_graphs, state in self.route_worlds.values():
            if {m: id(g) for m, g in local_graphs.items()} != state:
                self.invalidated = self.route_invalidated = True
        if self.route_invalidated:
            raise RoutePlanningError("read-only route inventory changed a route graph")

    def project(self, graph, blocked):
        """Share only an identical blocker projection within this observation."""
        unavailable = frozenset(blocked)
        if not unavailable:
            return graph
        retained = self._retain_graph(graph)
        key = (id(graph), unavailable)
        cached = self.projections.get(key)
        if cached is not None:
            self._retain_graph(cached)
            return cached
        projected = without_coordinates(graph, unavailable)
        if retained and len(self.graphs) < 2048 and self._retain_graph(projected):
            self.projections[key] = projected
        return projected

    def paths(self, graph, warps, start, goals, capabilities, mode):
        warps, goals = frozenset(warps), frozenset(goals)
        identity = id(graph)
        retained = self._retain_graph(graph)
        key = (identity, warps, start, goals, capabilities, mode)
        if retained and key in self.queries:
            value = self.queries[key]
            self._retain_graph(value[0])
            self.hits += 1
            return value
        self.misses += 1
        search_key = (identity, warps, start, capabilities, mode)
        entry = self.searches.get(search_key)
        if entry is None:
            projected = without_warp_transit(graph, warps, start_at=start)
            projected_retained = self._retain_graph(projected)
            search = None
            if retained and projected_retained and len(self.searches) < _MAX_LOCAL_INVENTORY_SEARCHES:
                search = _IncrementalLocalPaths(projected, start, capabilities=capabilities, start_mode=mode)
                self.searches[search_key] = projected, search
        else:
            projected, search = entry
            projected_retained = self._retain_graph(projected)
        if search is None:
            paths = find_local_paths(projected, start, goals, capabilities=capabilities, start_mode=mode)
        else:
            try:
                paths = search.paths(goals)
            except BaseException:
                # A rejected query must not leave a partially advanced search.
                self.searches.pop(search_key, None)
                raise
        value = projected, MappingProxyType(paths)
        if retained and projected_retained and len(self.queries) < 4096:
            self.queries[key] = value
        return value

    def verify(self):
        self.verify_routes()
        if self.invalidated or any(graph.edges != edges for graph, edges in self.graphs.values()):
            raise RoutePlanningError("read-only route inventory changed a local graph")


_FROZEN_LOCAL_ROUTE_CACHE: ContextVar[_FrozenLocalRouteCache | None] = ContextVar(
    "frozen_local_route_inventory", default=None
)


@contextmanager
def frozen_local_route_inventory():
    """Reuse pure local searches only while constructing one immutable menu.

    Capability, mode, goals, warp rules and graph contents remain exact. No
    route, observation, world or answer survives the outermost scope.
    Existing callers are unchanged unless explicitly opted into this context.
    A changed graph invalidates the inventory even if a planner catches its error.
    """
    existing = _FROZEN_LOCAL_ROUTE_CACHE.get()
    if existing is not None:
        yield existing
        return
    cache = _FrozenLocalRouteCache()
    token = _FROZEN_LOCAL_ROUTE_CACHE.set(cache)
    try:
        yield cache
        cache.verify()
    finally:
        _FROZEN_LOCAL_ROUTE_CACHE.reset(token)
        cache.searches.clear()
        cache.routes.clear()
        cache.route_macro_graphs.clear()
        cache.route_worlds.clear()
        cache.queries.clear()
        cache.projections.clear()
        cache.graphs.clear()


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
    via: tuple[Coordinate, ...] = ()

    def __post_init__(self) -> None:
        if not self.action:
            raise ValueError("a route step needs an action")
        if not self.kind:
            raise ValueError("a route step needs a transition kind")
        if not isinstance(self.action_kind, MacroActionKind):
            raise TypeError("a route step action kind must be a MacroActionKind")
        if self.transient_at in {self.source_at, self.expected_at}:
            raise ValueError("a route-step transient must differ from both endpoints")
        if self.via and (
            self.kind != "forced_motion"
            or {self.source_at, self.expected_at}.intersection(self.via)
        ):
            raise ValueError("forced-motion path must exclude both endpoints")

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
                        via=(() if triggers_passage else edge.via),
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
            target_local=local_graphs.get(target_map),
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
    inventory_cache = _FROZEN_LOCAL_ROUTE_CACHE.get()
    route_key = None
    if inventory_cache is not None:
        route_key = inventory_cache.route_key(
            graph, local_graphs, start_map, start_at, goal_map, unavailable,
            capabilities, last_outside, start_mode, goal_at, goal_mode,
        )
        if route_key is not None and route_key in inventory_cache.routes:
            inventory_cache.route_hits += 1
            inventory_cache.hits += 1
            succeeded, value = inventory_cache.routes[route_key]
            if succeeded:
                return value
            raise RoutePlanningError(*value)
        inventory_cache.route_misses += 1
    projected = {
        map_id: (
            without_coordinates(local, unavailable.get(map_id, frozenset()))
            if inventory_cache is None else
            inventory_cache.project(local, unavailable.get(map_id, frozenset()))
        )
        for map_id, local in local_graphs.items()
    }
    try:
        result = _find_composed_route(
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
    except RoutePlanningError as error:
        # Preserve complex native exception chains instead of flattening them.
        if (route_key is not None and len(inventory_cache.routes) < 1024
            and type(error) is RoutePlanningError
            and error.__cause__ is None and error.__context__ is None):
            inventory_cache.routes[route_key] = (False, error.args)
        raise
    if route_key is not None and len(inventory_cache.routes) < 1024:
        inventory_cache.routes[route_key] = (True, result)
    return result


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
        tuple[
            LocalGraph,
            dict[LocalGoal, LocalPath],
            dict[tuple[int, int], tuple[tuple[RouteSegment, int], ...]],
        ],
    ] = {}
    path_costs: dict[int, tuple[LocalPath, int]] = {}

    def path_cost(path: LocalPath) -> int:
        # Outside-return histories and sibling exits reuse immutable paths.
        # Retain the path with its price so object IDs cannot be recycled;
        # neither survives this one composed search or a new observation.
        priced = path_costs.get(id(path))
        if priced is None:
            priced = path, sum(edge.cost for edge in path.edges)
            path_costs[id(path)] = priced
        return priced[1]

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

        cache_key = (state.map_id, state.at, state.mode)
        cached = local_path_cache.get(cache_key)
        if cached is None:
            local = local_graphs.get(state.map_id)
            if local is None:
                continue
            warp_rules = (
                graph.warp_locations if graph.warp_triggers is None else graph.warp_triggers
            )
            warps = warp_rules.get(state.map_id, ())
            goals = _local_goals(graph, state.map_id)
            if state.map_id == goal_map and goal_at is not None:
                goals.add((goal_at, goal_mode))
            inventory_cache = _FROZEN_LOCAL_ROUTE_CACHE.get()
            if inventory_cache is None:
                local = without_warp_transit(local, warps, start_at=state.at)
                local_paths = find_local_paths(
                    local, state.at, goals, capabilities=capabilities, start_mode=state.mode
                )
            else:
                local, local_paths = inventory_cache.paths(
                    local, warps, state.at, goals, capabilities, state.mode
                )
            # The existing per-search path cache already assumes this observed
            # map/start/mode is unchanged. Retain its identical projection too;
            # outside-return variants must not rebuild the same graph. Neither
            # graph nor paths survive a new observation. Explicit inventory
            # reuse may share the same pure query with its sibling searches.
            # Retained outside-map variants share this exact local state.
            # Once advance_macro_state resolves a passage's target, its
            # composition and price do not depend on the retained context.
            passages: dict[tuple[int, int], tuple[tuple[RouteSegment, int], ...]] = {}
            local_path_cache[cache_key] = local, local_paths, passages
        else:
            local, local_paths, passages = cached

        if state.map_id == goal_map and goal_at is not None:
            terminal = local_paths.get((goal_at, goal_mode))
            if terminal is not None:
                terminal_cost = path_cost(terminal)
                candidate = (cost + terminal_cost, sequence, state, terminal)
                if best_goal is None or candidate[:2] < best_goal[:2]:
                    best_goal = candidate
                sequence += 1
                if terminal_cost == 0:
                    break

        for edge_ordinal, edge in enumerate(graph.neighbors(state.map_id)):
            advanced = advance_macro_state(
                graph,
                (state.map_id, state.last_outside),
                edge,
            )
            if advanced is None:
                continue
            target_map, next_last_outside = advanced
            passage_key = edge_ordinal, target_map
            candidates = passages.get(passage_key)
            if candidates is None:
                try:
                    composed = _compose_segment_candidates(
                        graph,
                        local,
                        state,
                        target_map,
                        edge,
                        capabilities=capabilities,
                        local_paths=local_paths,
                        target_local=local_graphs.get(target_map),
                    )
                except RoutePlanningError:
                    passages[passage_key] = ()
                    continue
                candidates = tuple(
                    (segment, sum(local_edge.cost for local_edge in segment.approach.edges))
                    for segment in composed
                )
                passages[passage_key] = candidates
            for segment, segment_cost in candidates:
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


def without_warp_transit(
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

    warps = frozenset(warp_locations)
    absorbing = warps.difference({start_at})
    if not warps:
        return graph
    if not graph.edges:
        raise ValueError("max() iterable argument is empty")

    # Edge tuples are immutable: copy the mapping, not every unaffected tuple.
    # Never add absent coordinates or mutate the caller's graph. The projection
    # is fresh for every observed start, with no cache across changing worlds.
    edges = dict(graph.edges)
    for source in absorbing:
        if source in edges:
            edges[source] = ()
    if start_at in warps and start_at in edges:
        # Boundary dimensions matter only when walking off the starting warp.
        # Most connection arrivals need only the absorbing-warp projection.
        max_y = max(source[0] for source in graph.edges)
        max_x = max(source[1] for source in graph.edges)

        def safe_start_departure(edge: object) -> bool:
            target = edge.target  # type: ignore[attr-defined]
            if start_at[0] <= 1 and target[0] < start_at[0]:
                return False
            if start_at[0] >= max_y - 1 and target[0] > start_at[0]:
                return False
            if start_at[1] <= 1 and target[1] < start_at[1]:
                return False
            return not (start_at[1] >= max_x - 1 and target[1] > start_at[1])

        edges[start_at] = tuple(edge for edge in edges[start_at] if safe_start_departure(edge))
    return LocalGraph(edges)


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
    target_local: LocalGraph | None,
) -> RouteSegment:
    candidates = _compose_segment_candidates(
        graph,
        local,
        state,
        target_map,
        edge,
        capabilities=capabilities,
        local_paths=None,
        target_local=target_local,
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
    target_local: LocalGraph | None,
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
            if target_local is not None and not _connection_arrival_is_executable(
                target_local,
                transition.arrival_at,
                approach.modes[-1],
                capabilities,
            ):
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
            source_map=state.map_id,
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


def _connection_arrival_is_executable(
    graph: LocalGraph,
    at: Coordinate,
    mode: TraversalMode,
    capabilities: frozenset[str],
) -> bool:
    """Return whether a connection arrival can continue on the target map.

    A connection preserves the current traversal mode. Checking only its
    source endpoint can therefore select a coordinate that is absent from the
    target graph or whose inward edge cannot be used in that mode. Route 21's
    broad south connection exposed both kinds of invalid Cinnabar arrival.
    """

    if at not in graph.edges:
        return False
    return any(
        edge.permits_mode(mode) and edge.requirements.issubset(capabilities)
        for edge in graph.neighbors(at)
    )


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
            via=edge.via,
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
    source_map: int,
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
    # the decoded outward action. The Generation I adapter clears that action
    # only when the source tileset's cartridge table marks this exact tile as
    # an automatic door/warp. Geometry alone is insufficient: Cerulean's
    # robbed-house top door fires on entry, while the Underground Path top edge
    # needs a second UP from the same coordinate.
    action_in_approach = edge.exit_action is None
    if not approach.edges:
        # A scripted arrival can also leave a directional door's collision
        # trigger suppressed. Re-arm it when a safe ordinary cycle is known,
        # then retain its decoded extra input. An automatic warp needs this
        # cycle; a directional warp with no qualified cycle keeps its existing
        # collision recipe. Never invent an edge to manufacture re-entry.
        cycles = []
        triggers = (
            graph.warp_locations if graph.warp_triggers is None else graph.warp_triggers
        ).get(source_map, ())
        for outward in local.neighbors(start):
            if outward.target in triggers:
                continue
            for inward in local.neighbors(outward.target):
                if outward.target == start or inward.target != start:
                    continue
                if all(
                    step.kind == "walk"
                    and step.action_kind == MacroActionKind.MOVE
                    and step.requirements <= capabilities
                    and step.permits_mode(start_mode)
                    and step.next_mode(start_mode) == start_mode
                    for step in (outward, inward)
                ):
                    cycles.append(
                        LocalPath(
                            (start, outward.target, start),
                            (outward, inward),
                            (start_mode, start_mode, start_mode),
                        )
                    )
        if not cycles and action_in_approach:
            raise RoutePlanningError("route begins on a warp trigger without safe re-entry")
        if cycles:
            approach = min(cycles, key=lambda path: sum(step.cost for step in path.edges))

    arrival = edge.arrival_at
    if edge.kind == "return":
        index = edge.destination_warp_index
        locations = graph.warp_locations.get(target_map, ())
        if index is None or index >= len(locations):
            raise RoutePlanningError(f"return to map {target_map} has no destination warp {index}")
        arrival = locations[index]
    if arrival is None:
        raise RoutePlanningError("an ordinary warp has no decoded arrival coordinate")
    destination_triggers_on_entry = edge.kind == "warp" and any(
        candidate.kind in {"return", "warp"}
        and candidate.at == arrival
        and candidate.exit_action is None
        for candidate in graph.neighbors(target_map)
    )
    if edge.exit_action not in {None, "up", "down", "left", "right"}:
        raise RoutePlanningError(f"unsupported directional warp action {edge.exit_action!r}")
    if graph.warp_arrivals is not None:
        index = edge.destination_warp_index
        locations = graph.warp_locations.get(target_map, ())
        arrivals = graph.warp_arrivals.get(target_map, ())
        if (
            index is None
            or index >= len(locations)
            or len(arrivals) != len(locations)
            or locations[index] != arrival
        ):
            raise RoutePlanningError("warp lacks consistent declared destination arrivals")
        arrival = arrivals[index]
    elif (
        edge.exit_action == "down"
        and not action_in_approach
        and (edge.kind == "return" or destination_triggers_on_entry)
    ):
        # A south-facing return plays the exterior doorway step. An ordinary
        # directional warp plays the same inward step only when its destination
        # warp is cartridge-classified as automatic: Route 2 -> Viridian
        # Forest settles beyond the door, while Route 6 -> Underground Path
        # lands on its directional return warp.
        arrival = arrival[0] + 1, arrival[1]
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
