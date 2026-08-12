"""Staged Generation I planning around Cut's live map mutation.

Cut is not a durable edge that becomes traversable when the party owns a move.
It is a self-position field action that replaces one block in the active map
buffer. This module may use the cartridge swap table to choose a candidate, but
the executor must observe the mutation and rebuild terrain before it plans the
crossing.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_terrain import (
    Terrain,
    Tileset,
    terrain_with_block,
)
from pokemon_red_completion.gen1_traversal import (
    CUT_CAPABILITY,
    Direction,
    TraversalRules,
    cut_capabilities,
    local_graph,
)
from pokemon_red_completion.local_router import (
    LocalEdge,
    LocalGraph,
    LocalPath,
    LocalRouterError,
    TraversalMode,
    find_local_path,
)
from pokemon_red_completion.observation import RawGameState

OVERWORLD_TILESET = 0
GYM_TILESET = 7
OVERWORLD_CUT_TREE_TILE = 0x3D
GYM_CUT_TREE_TILE = 0x50
CUT_PASSAGE_TILES = {
    OVERWORLD_TILESET: frozenset({OVERWORLD_CUT_TREE_TILE}),
    GYM_TILESET: frozenset({GYM_CUT_TREE_TILE}),
}
CUT_FIELD_ACTION_COST = 4


class CutTraversalError(RuntimeError):
    """Raised when no truthful staged Cut candidate can be built."""


@dataclass(frozen=True, slots=True)
class CutTraversalCandidate:
    """A route to a cutting stance plus a prediction used only for selection."""

    map_id: int
    source_at: tuple[int, int]
    target_at: tuple[int, int]
    direction: Direction
    block_at: tuple[int, int]
    before_block: int
    after_block: int
    approach: LocalPath
    predicted_continuation: LocalPath

    @property
    def predicted_cost(self) -> int:
        return len(self.approach.edges) + len(self.predicted_continuation.edges)


CutGraphBuilder = Callable[[Terrain], LocalGraph]


def staged_cut_path(candidate: CutTraversalCandidate) -> LocalPath:
    """Join the pre-Cut approach and predicted continuation explicitly.

    The inserted field action keeps the player's coordinate unchanged. Its
    successor movement is therefore the first action allowed to enter the
    predicted replacement. The field-move adapter remains responsible for
    proving the exact live mutation before that successor is attempted.
    """

    approach = candidate.approach
    continuation = candidate.predicted_continuation
    if (
        approach.coordinates[-1] != candidate.source_at
        or continuation.coordinates[0] != candidate.source_at
        or approach.modes[-1] != continuation.modes[0]
    ):
        raise CutTraversalError("Cut path stages do not share one traversal state")
    mode = approach.modes[-1]
    cut = LocalEdge(
        target=candidate.source_at,
        action=f"cut:{candidate.direction.value}",
        kind="cut_mutation",
        requirements=frozenset({CUT_CAPABILITY}),
        cost=CUT_FIELD_ACTION_COST,
        action_kind=MacroActionKind.FIELD_MOVE,
        required_mode=mode,
        result_mode=mode,
    )
    return LocalPath(
        coordinates=(
            *approach.coordinates,
            candidate.source_at,
            *continuation.coordinates[1:],
        ),
        edges=(*approach.edges, cut, *continuation.edges),
        modes=(*approach.modes, mode, *continuation.modes[1:]),
    )


def plan_cut_candidate_in_graphs(
    rom: bytes,
    terrain: Terrain,
    rules: TraversalRules,
    sets: Mapping[int, Tileset],
    start: tuple[int, int],
    goal: tuple[int, int],
    *,
    capabilities: frozenset[str],
    before_graph: LocalGraph,
    graph_builder: CutGraphBuilder,
    start_mode: TraversalMode = None,
    field_mode: TraversalMode = None,
    goal_mode: TraversalMode = None,
    required_block_at: tuple[int, int] | None = None,
    water_set_ids: frozenset[int] | None = None,
) -> CutTraversalCandidate:
    """Plan one explicit Cut mutation between two local route boundaries.

    ``before_graph`` must describe the unmodified map. ``graph_builder`` is
    called separately for each cartridge-declared replacement, which lets a
    caller preserve Surf modes, story predicates and static object blockers.
    The predicted continuation is selection evidence only; live execution must
    still observe the exact block replacement before crossing it.
    """

    if CUT_CAPABILITY not in capabilities:
        raise CutTraversalError("Cut requires an observed field-move capability")
    if terrain.blocks is None:
        raise CutTraversalError("Cut planning needs terrain built from explicit blocks")
    if required_block_at is not None:
        block_y, block_x = required_block_at
        if not (0 <= block_y < len(terrain.blocks) and 0 <= block_x < len(terrain.blocks[0])):
            raise CutTraversalError("the required Cut block is outside the map")

    try:
        find_local_path(
            before_graph,
            start,
            goal,
            capabilities=capabilities,
            start_mode=start_mode,
            goal_mode=goal_mode,
        )
    except LocalRouterError:
        pass
    else:
        raise CutTraversalError("Cut is unnecessary because the goal is already reachable")

    replacements = {swap.before: swap.after for swap in rules.cut_block_swaps}
    eligible_tiles = CUT_PASSAGE_TILES.get(terrain.tileset, frozenset())
    candidates: list[CutTraversalCandidate] = []
    for target_y, row in enumerate(terrain.tiles):
        for target_x, tile in enumerate(row):
            if tile not in eligible_tiles:
                continue
            target_at = target_y, target_x
            block_at = target_y // 2, target_x // 2
            if required_block_at is not None and block_at != required_block_at:
                continue
            before_block = terrain.blocks[block_at[0]][block_at[1]]
            after_block = replacements.get(before_block)
            if after_block is None:
                continue
            predicted = terrain_with_block(
                rom,
                terrain,
                block_at,
                after_block,
                sets,
                water_set_ids=water_set_ids,
            )
            if not predicted.can_stand(*target_at) or predicted.tiles[target_y][target_x] == tile:
                continue
            after_graph = graph_builder(predicted)
            for direction in Direction:
                dy, dx = direction.delta
                source_at = target_y - dy, target_x - dx
                if not terrain.can_stand(*source_at):
                    continue
                try:
                    approach = find_local_path(
                        before_graph,
                        start,
                        source_at,
                        capabilities=capabilities,
                        start_mode=start_mode,
                        goal_mode=field_mode,
                    )
                    continuation = find_local_path(
                        after_graph,
                        source_at,
                        goal,
                        capabilities=capabilities,
                        start_mode=field_mode,
                        goal_mode=goal_mode,
                    )
                except LocalRouterError:
                    continue
                if target_at not in continuation.coordinates:
                    continue
                candidates.append(
                    CutTraversalCandidate(
                        map_id=terrain.map_id,
                        source_at=source_at,
                        target_at=target_at,
                        direction=direction,
                        block_at=block_at,
                        before_block=before_block,
                        after_block=after_block,
                        approach=approach,
                        predicted_continuation=continuation,
                    )
                )
    if not candidates:
        raise CutTraversalError(f"no staged Cut candidate opens a route from {start} to {goal}")
    return min(
        candidates,
        key=lambda candidate: (
            candidate.predicted_cost,
            candidate.target_at,
            candidate.source_at,
            candidate.direction.value,
        ),
    )


def plan_cut_candidate(
    rom: bytes,
    terrain: Terrain,
    rules: TraversalRules,
    sets: Mapping[int, Tileset],
    start: tuple[int, int],
    goal: tuple[int, int],
    raw: RawGameState,
    *,
    blocked: Collection[tuple[int, int]] = (),
    water_set_ids: frozenset[int] | None = None,
) -> CutTraversalCandidate:
    """Choose a reachable Cut stance whose predicted replacement opens ``goal``.

    The returned continuation is not executable authority. It proves the
    cartridge-declared replacement is a useful candidate. After the field move,
    callers must discard it, read the live blocks, rebuild terrain, and plan
    again from the observed state.
    """

    if CUT_CAPABILITY not in cut_capabilities(raw):
        raise CutTraversalError("Cut requires Cascade Badge and a living move holder")
    if terrain.blocks is None:
        raise CutTraversalError("Cut planning needs terrain built from explicit blocks")
    if raw.map_id != terrain.map_id:
        raise CutTraversalError(
            f"observed map {raw.map_id} does not match terrain map {terrain.map_id}"
        )
    if raw.player_y is None or raw.player_x is None or (raw.player_y, raw.player_x) != start:
        raise CutTraversalError("Cut planning start does not match the observed player")

    before_graph = local_graph(terrain, rules, blocked=blocked)
    return plan_cut_candidate_in_graphs(
        rom,
        terrain,
        rules,
        sets,
        start,
        goal,
        capabilities=cut_capabilities(raw),
        before_graph=before_graph,
        graph_builder=lambda predicted: local_graph(predicted, rules, blocked=blocked),
        water_set_ids=water_set_ids,
    )


def plan_nearest_cut_candidate(
    rom: bytes,
    terrain: Terrain,
    rules: TraversalRules,
    sets: Mapping[int, Tileset],
    start: tuple[int, int],
    raw: RawGameState,
    *,
    blocked: Collection[tuple[int, int]] = (),
    water_set_ids: frozenset[int] | None = None,
) -> CutTraversalCandidate:
    """Choose the cheapest reachable tree mutation in the current live grid.

    This deliberately plans one mutation only.  A caller that needs several
    trees must execute the returned field action, verify its live block
    replacement, rebuild ``Terrain`` from RAM, and call this function again.
    Cleared trees disappear from the eligible tile set in that new terrain, so
    no durable Cut edge or speculative sequence enters the route graph.
    """

    eligible_tiles = CUT_PASSAGE_TILES.get(terrain.tileset, frozenset())
    candidates: list[CutTraversalCandidate] = []
    for y, row in enumerate(terrain.tiles):
        for x, tile in enumerate(row):
            if tile not in eligible_tiles:
                continue
            try:
                candidate = plan_cut_candidate(
                    rom,
                    terrain,
                    rules,
                    sets,
                    start,
                    (y, x),
                    raw,
                    blocked=blocked,
                    water_set_ids=water_set_ids,
                )
            except CutTraversalError:
                continue
            candidates.append(candidate)
    if not candidates:
        raise CutTraversalError(f"no reachable staged Cut candidate from {start}")
    return min(
        candidates,
        key=lambda candidate: (
            candidate.predicted_cost,
            candidate.target_at,
            candidate.source_at,
            candidate.direction.value,
        ),
    )
