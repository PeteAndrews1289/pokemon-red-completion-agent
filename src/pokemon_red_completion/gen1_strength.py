"""Bounded Generation I planning over player-and-boulder state.

Strength does not unlock a durable map edge. Each push changes the puzzle, and
Red's engine requires the same directional attempt twice before it moves the
boulder. This module therefore searches explicit ``(player, boulders)`` states
and prices a push as two controller inputs.
"""

from __future__ import annotations

import heapq
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.gen1_traversal import (
    STRENGTH_CAPABILITY,
    Direction,
    TraversalRules,
    local_graph,
    strength_capabilities,
)
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.observation import (
    CurrentStrengthBoulder,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
    ReadOnlyMemory,
)
from pokemon_red_completion.route_executor import RouteActionPort

Coordinate = tuple[int, int]
STAIRS_TILE = 0x15
STRENGTH_PUSH_COST = 2
STRENGTH_ACTIVE_MASK = 1 << 0
TRIED_PUSH_BOULDER_MASK = 1 << 6


class StrengthPlanningError(RuntimeError):
    """Raised when a bounded truthful Strength plan cannot be produced."""


@dataclass(frozen=True, slots=True, order=True)
class StrengthBoulder:
    sprite_index: int
    at: Coordinate

    def __post_init__(self) -> None:
        if not 1 <= self.sprite_index <= 15:
            raise ValueError("a boulder sprite index must be between 1 and 15")


@dataclass(frozen=True, slots=True)
class StrengthState:
    player_at: Coordinate
    boulders: tuple[StrengthBoulder, ...]

    def __post_init__(self) -> None:
        if self.boulders != tuple(sorted(self.boulders)):
            raise ValueError("Strength boulders must be sorted by sprite index")
        indices = tuple(item.sprite_index for item in self.boulders)
        coordinates = tuple(item.at for item in self.boulders)
        if len(indices) != len(set(indices)):
            raise ValueError("Strength boulder sprite indices must be unique")
        if len(coordinates) != len(set(coordinates)):
            raise ValueError("Strength boulder coordinates must be unique")
        if self.player_at in coordinates:
            raise ValueError("the player cannot occupy a boulder coordinate")

    @classmethod
    def from_observation(
        cls,
        player_at: Coordinate,
        boulders: Collection[CurrentStrengthBoulder],
    ) -> StrengthState:
        return cls(
            player_at=player_at,
            boulders=tuple(
                sorted(
                    StrengthBoulder(item.sprite_index, item.at)
                    for item in boulders
                )
            ),
        )

    @property
    def occupied(self) -> frozenset[Coordinate]:
        return frozenset(item.at for item in self.boulders)


@dataclass(frozen=True, slots=True)
class StrengthGoal:
    boulder_at: Coordinate
    boulder_index: int | None = None
    player_at: Coordinate | None = None

    def satisfied_by(self, state: StrengthState) -> bool:
        if self.player_at is not None and state.player_at != self.player_at:
            return False
        return any(
            item.at == self.boulder_at
            and (self.boulder_index is None or item.sprite_index == self.boulder_index)
            for item in state.boulders
        )


@dataclass(frozen=True, slots=True)
class StrengthStep:
    kind: str
    direction: Direction
    source: StrengthState
    result: StrengthState
    boulder_index: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"walk", "push"}:
            raise ValueError("a Strength step must be a walk or push")
        if (self.kind == "push") != (self.boulder_index is not None):
            raise ValueError("only a push step names a boulder")

    @property
    def cost(self) -> int:
        return STRENGTH_PUSH_COST if self.kind == "push" else 1


@dataclass(frozen=True, slots=True)
class StrengthPlan:
    states: tuple[StrengthState, ...]
    steps: tuple[StrengthStep, ...]
    cost: int
    explored_states: int

    def __post_init__(self) -> None:
        if len(self.states) != len(self.steps) + 1:
            raise ValueError("a Strength plan needs one more state than step")
        if sum(step.cost for step in self.steps) != self.cost:
            raise ValueError("a Strength plan cost must equal its steps")


@dataclass(frozen=True, slots=True)
class StrengthExecutionTiming:
    settle_frames: int = 60
    max_step_attempts: int = 4
    max_readiness_waits: int = 12

    def __post_init__(self) -> None:
        for name, value in (
            ("settle_frames", self.settle_frames),
            ("max_step_attempts", self.max_step_attempts),
            ("max_readiness_waits", self.max_readiness_waits),
        ):
            if type(value) is not int or value <= 0:  # noqa: E721
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_STRENGTH_EXECUTION_TIMING = StrengthExecutionTiming()


@dataclass(frozen=True, slots=True)
class StrengthPushReceipt:
    ordinal: int
    direction: Direction
    boulder_index: int
    player_before: Coordinate
    player_after: Coordinate
    boulder_before: Coordinate
    boulder_after: Coordinate
    first_attempt_unchanged: bool
    first_attempt_flag_observed: bool


@dataclass(frozen=True, slots=True)
class StrengthExecutionReport:
    plan: StrengthPlan
    terminal: StrengthState
    acknowledged_steps: int
    controller_inputs: int
    wait_actions: int
    pushes: tuple[StrengthPushReceipt, ...]

    @property
    def passed(self) -> bool:
        return self.terminal == self.plan.states[-1]


@dataclass(slots=True)
class Gen1StrengthExecutor:
    """Execute one planned puzzle while proving every live state transition."""

    actions: RouteActionPort
    reader: PokemonRedStateReader
    memory: ReadOnlyMemory
    timing: StrengthExecutionTiming = DEFAULT_STRENGTH_EXECUTION_TIMING
    push_receipts: list[StrengthPushReceipt] = field(default_factory=list, init=False)
    _inputs: int = field(default=0, init=False)
    _waits: int = field(default=0, init=False)

    def execute(self, plan: StrengthPlan) -> StrengthExecutionReport:
        before_raw = self.reader.read()
        map_id = _require_live_overworld(before_raw)
        protected = _protected_state(before_raw)
        if not self.memory.read_u8(RamAddress.STATUS_FLAGS_1) & STRENGTH_ACTIVE_MASK:
            raise StrengthPlanningError("Strength execution requires the active field flag")
        if self._observe_state(map_id) != plan.states[0]:
            raise StrengthPlanningError("live Strength state does not match the plan start")

        for ordinal, step in enumerate(plan.steps, start=1):
            self._wait_ready(map_id, step.source, protected)
            if step.kind == "walk":
                self._execute_walk(map_id, step, protected)
            else:
                self._execute_push(map_id, ordinal, step, protected)
        terminal = self._observe_state(map_id)
        return StrengthExecutionReport(
            plan=plan,
            terminal=terminal,
            acknowledged_steps=len(plan.steps),
            controller_inputs=self._inputs,
            wait_actions=self._waits,
            pushes=tuple(self.push_receipts),
        )

    def _execute_walk(
        self,
        map_id: int,
        step: StrengthStep,
        protected: tuple[object, ...],
    ) -> None:
        for _ in range(self.timing.max_step_attempts):
            self._pulse_direction(step.direction)
            current = self._checked_state(map_id, protected)
            if current == step.result:
                return
            if current != step.source:
                raise StrengthPlanningError("walk changed a different Strength state")
        raise StrengthPlanningError("walk exhausted its acknowledgement budget")

    def _execute_push(
        self,
        map_id: int,
        ordinal: int,
        step: StrengthStep,
        protected: tuple[object, ...],
    ) -> None:
        assert step.boulder_index is not None
        before_boulder = _boulder_at(step.source, step.boulder_index)
        after_boulder = _boulder_at(step.result, step.boulder_index)

        self._pulse_direction(step.direction)
        after_first = self._checked_state(map_id, protected)
        first_flag = bool(
            self.memory.read_u8(RamAddress.MISC_FLAGS) & TRIED_PUSH_BOULDER_MASK
        )
        if after_first != step.source:
            raise StrengthPlanningError("first Strength attempt changed the puzzle")
        if not first_flag:
            raise StrengthPlanningError("first Strength attempt lacked the engine tried-push flag")

        self._pulse_direction(step.direction)
        after_second = self._checked_state(map_id, protected)
        if after_second != step.result:
            raise StrengthPlanningError("second Strength attempt did not make the exact push")
        self.push_receipts.append(
            StrengthPushReceipt(
                ordinal=ordinal,
                direction=step.direction,
                boulder_index=step.boulder_index,
                player_before=step.source.player_at,
                player_after=step.result.player_at,
                boulder_before=before_boulder,
                boulder_after=after_boulder,
                first_attempt_unchanged=True,
                first_attempt_flag_observed=True,
            )
        )

    def _pulse_direction(self, direction: Direction) -> None:
        self.actions.execute(MacroAction(MacroActionKind.MOVE, direction.value))
        self._inputs += 1
        self.actions.execute(
            MacroAction(MacroActionKind.WAIT, repeat=self.timing.settle_frames)
        )
        self._waits += 1

    def _wait_ready(
        self,
        map_id: int,
        expected: StrengthState,
        protected: tuple[object, ...],
    ) -> None:
        for _ in range(self.timing.max_readiness_waits + 1):
            raw = self.reader.read()
            _require_protected(raw, protected)
            if raw.battle_state not in {0, None}:
                raise StrengthPlanningError("Strength execution entered a battle")
            if self._observe_state(map_id) != expected:
                raise StrengthPlanningError("Strength state changed while waiting for readiness")
            if self.reader.read_input_readiness().ready:
                return
            self.actions.execute(
                MacroAction(MacroActionKind.WAIT, repeat=self.timing.settle_frames)
            )
            self._waits += 1
        raise StrengthPlanningError("Strength execution exhausted its readiness budget")

    def _checked_state(
        self,
        map_id: int,
        protected: tuple[object, ...],
    ) -> StrengthState:
        raw = self.reader.read()
        if raw.battle_state not in {0, None}:
            raise StrengthPlanningError("Strength execution entered a battle")
        _require_protected(raw, protected)
        if not self.memory.read_u8(RamAddress.STATUS_FLAGS_1) & STRENGTH_ACTIVE_MASK:
            raise StrengthPlanningError("Strength active field flag disappeared")
        return self._observe_state(map_id)

    def _observe_state(self, map_id: int) -> StrengthState:
        raw = self.reader.read()
        if raw.map_id != map_id or raw.player_y is None or raw.player_x is None:
            raise StrengthPlanningError("Strength execution changed maps or lost position")
        return StrengthState.from_observation(
            (raw.player_y, raw.player_x),
            self.reader.read_current_strength_boulders(),
        )


def plan_strength(
    terrain: Terrain,
    rules: TraversalRules,
    initial: StrengthState,
    goal: StrengthGoal,
    raw: RawGameState,
    *,
    blocked: Collection[Coordinate] = (),
    max_states: int = 100_000,
) -> StrengthPlan:
    """Find the cheapest bounded sequence that puts a boulder on ``goal``.

    ``blocked`` is for non-boulder dynamic objects. The current boulders must
    remain in ``initial`` so the search can move them instead of deleting their
    outgoing terrain. Only ordinary one-square walk edges can push a boulder;
    ledges, stairs and title-specific field transitions are rejected.
    """

    if type(max_states) is not int or max_states <= 0:  # noqa: E721
        raise ValueError("max_states must be a positive integer")
    if STRENGTH_CAPABILITY not in strength_capabilities(raw):
        raise StrengthPlanningError("Strength requires Rainbow Badge and a living move holder")
    if raw.map_id != terrain.map_id:
        raise StrengthPlanningError(
            f"observed map {raw.map_id} does not match terrain map {terrain.map_id}"
        )
    observed_at = raw.player_y, raw.player_x
    if None in observed_at or observed_at != initial.player_at:
        raise StrengthPlanningError("Strength planning start does not match the player")
    if not terrain.can_stand(*initial.player_at):
        raise StrengthPlanningError("Strength planning starts outside standable terrain")
    if not terrain.can_stand(*goal.boulder_at):
        raise StrengthPlanningError("Strength goal is outside standable terrain")
    unavailable = frozenset(blocked)
    if initial.player_at in unavailable or initial.occupied & unavailable:
        raise StrengthPlanningError("non-boulder occupancy overlaps the initial Strength state")

    graph = local_graph(terrain, rules, blocked=unavailable)
    if goal.satisfied_by(initial):
        return StrengthPlan((initial,), (), 0, 1)

    frontier: list[tuple[int, int, StrengthState]] = [(0, 0, initial)]
    best_cost = {initial: 0}
    came_from: dict[StrengthState, tuple[StrengthState, StrengthStep]] = {}
    sequence = 1
    explored = 0
    while frontier:
        cost, _, current = heapq.heappop(frontier)
        if cost != best_cost.get(current):
            continue
        explored += 1
        if explored > max_states:
            raise StrengthPlanningError(
                f"Strength search exceeded its {max_states}-state bound"
            )
        if goal.satisfied_by(current):
            return _reconstruct(came_from, initial, current, cost, explored)
        for step in _neighbors(terrain, graph, current):
            following = step.result
            candidate = cost + step.cost
            if candidate >= best_cost.get(following, candidate + 1):
                continue
            best_cost[following] = candidate
            came_from[following] = current, step
            heapq.heappush(frontier, (candidate, sequence, following))
            sequence += 1
    raise StrengthPlanningError(
        f"no legal Strength plan reaches boulder coordinate {goal.boulder_at}"
    )


def _neighbors(
    terrain: Terrain,
    graph: LocalGraph,
    state: StrengthState,
) -> tuple[StrengthStep, ...]:
    by_coordinate = {item.at: item for item in state.boulders}
    found: list[StrengthStep] = []
    for direction in Direction:
        dy, dx = direction.delta
        adjacent = state.player_at[0] + dy, state.player_at[1] + dx
        boulder = by_coordinate.get(adjacent)
        if boulder is None:
            edge = _walk_edge(graph, state.player_at, adjacent, direction)
            if edge is None or adjacent in state.occupied:
                continue
            following = StrengthState(adjacent, state.boulders)
            found.append(StrengthStep("walk", direction, state, following))
            continue

        beyond = adjacent[0] + dy, adjacent[1] + dx
        if (
            not terrain.can_stand(*beyond)
            or beyond in state.occupied
            or terrain.tiles[beyond[0]][beyond[1]] == STAIRS_TILE
        ):
            continue
        if _walk_edge(graph, adjacent, beyond, direction) is None:
            continue
        moved = tuple(
            sorted(
                StrengthBoulder(item.sprite_index, beyond)
                if item.sprite_index == boulder.sprite_index
                else item
                for item in state.boulders
            )
        )
        following = StrengthState(adjacent, moved)
        found.append(
            StrengthStep("push", direction, state, following, boulder.sprite_index)
        )
    return tuple(found)


def _walk_edge(
    graph: LocalGraph,
    source: Coordinate,
    target: Coordinate,
    direction: Direction,
) -> LocalEdge | None:
    return next(
        (
            edge
            for edge in graph.neighbors(source)
            if edge.target == target
            and edge.kind == "walk"
            and edge.action == direction.value
            and not edge.requirements
        ),
        None,
    )


def _reconstruct(
    came_from: Mapping[StrengthState, tuple[StrengthState, StrengthStep]],
    initial: StrengthState,
    goal: StrengthState,
    cost: int,
    explored: int,
) -> StrengthPlan:
    states = [goal]
    steps: list[StrengthStep] = []
    current = goal
    while current != initial:
        previous, step = came_from[current]
        states.append(previous)
        steps.append(step)
        current = previous
    return StrengthPlan(
        states=tuple(reversed(states)),
        steps=tuple(reversed(steps)),
        cost=cost,
        explored_states=explored,
    )


def _require_live_overworld(raw: RawGameState) -> int:
    if (
        not raw.game_started
        or raw.map_id is None
        or raw.player_y is None
        or raw.player_x is None
        or raw.battle_state != 0
    ):
        raise StrengthPlanningError("Strength execution needs a controllable overworld state")
    return raw.map_id


def _protected_state(raw: RawGameState) -> tuple[object, ...]:
    return (
        raw.party_count,
        raw.party_hp,
        raw.party_status,
        raw.party_moves,
        raw.party_pp,
        raw.bag_items,
    )


def _require_protected(raw: RawGameState, expected: tuple[object, ...]) -> None:
    if _protected_state(raw) != expected:
        raise StrengthPlanningError("Strength execution changed protected party or bag state")


def _boulder_at(state: StrengthState, sprite_index: int) -> Coordinate:
    try:
        return next(
            item.at for item in state.boulders if item.sprite_index == sprite_index
        )
    except StopIteration as error:
        raise StrengthPlanningError(
            f"Strength state lacks planned boulder sprite {sprite_index}"
        ) from error
