"""Bounded, walking-only income candidates across ordinary map connections.

This is a prospective skill planner, not learned trainer selection. It excludes
doors, HMs, ledges and scripted passages; no static candidate authorizes input.
The existing funding executor must recheck live hazards and target identity.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Protocol

from .actions import MacroActionKind
from .gen1_cartridge import CartridgeReadError
from .gen1_trainer_parties import trainer_party_quote
from .gen1_trainer_sight import TrainerFacing, TrainerSightZone
from .global_router import MacroGraph
from .local_router import LocalGraph
from .red_trainer_funding import TrainerFundingCandidate
from .route_executor import TraversalSnapshot
from .route_plan import RoutePlanningError, plan_route


class ConnectedFundingWorld(Protocol):
    @property
    def macro_graph(self) -> MacroGraph: ...

    @property
    def local_graphs(self) -> Mapping[int, LocalGraph]: ...


def connected_funding_maps(graph: MacroGraph, start_map: int) -> frozenset[int]:
    """Current map plus its immediate ordinary connections; no guessed returns."""
    return frozenset(
        {start_map}
        | {
            e.target_map
            for e in graph.neighbors(start_map)
            if e.kind == "connection" and e.target_map is not None
        }
    )


def regional_trainer_funding_candidates(
    rom: bytes,
    world: ConnectedFundingWorld,
    start: TraversalSnapshot,
    trainers: tuple[TrainerSightZone, ...],
    *,
    inventoried_maps: frozenset[int],
    maximum_steps: int = 256,
) -> tuple[TrainerFundingCandidate, ...]:
    """Route only through inventoried maps, reserving bodies and all sight lanes.

    The inventory caller must include every ordinary trainer on every permitted
    map, joining the current map to live objects and other maps to cartridge
    positions. Explicit map coverage distinguishes an empty map from missing data.
    """
    if type(maximum_steps) is not int or maximum_steps < 1:
        raise ValueError("maximum_steps must be a positive integer")
    maps = connected_funding_maps(world.macro_graph, start.map_id)
    if inventoried_maps != maps or any(t.map_id not in maps for t in trainers):
        raise ValueError("regional funding requires complete bounded map inventory")
    if len({(t.map_id, t.sprite_index) for t in trainers}) != len(trainers):
        raise ValueError("regional funding contains duplicate trainer identities")
    if not start.ready or start.interruption is not None or start.mode != "land":
        return ()
    blocked: dict[int, frozenset[tuple[int, int]]] = {m: frozenset() for m in maps}
    blocked[start.map_id] = start.occupied | frozenset(h.at for h in start.hazards)
    for trainer in trainers:
        blocked[trainer.map_id] |= {trainer.at}
        if trainer.active:
            blocked[trainer.map_id] |= set(trainer.lane)
    if start.at in blocked[start.map_id]:
        return ()
    # Filter capabilities at the graph boundary, not by finding an HM route and
    # accepting its walk prefix. Keep every remaining story requirement intact.
    graph = replace(
        world.macro_graph,
        edges={
            m: tuple(
                e
                for e in world.macro_graph.neighbors(m)
                if e.kind == "connection" and e.target_map in maps
            )
            for m in maps
        },
    )
    locals_ = {
        m: LocalGraph(
            {
                at: tuple(
                    e
                    for e in edges
                    if e.kind == "walk"
                    and e.action_kind is MacroActionKind.MOVE
                    and e.action in {"up", "down", "left", "right"}
                    and e.required_mode in {None, "land"}
                    and e.result_mode in {None, "land"}
                )
                for at, edges in world.local_graphs[m].edges.items()
            }
        )
        for m in maps
    }
    result = []
    for trainer in trainers:
        if trainer.defeated:
            continue
        quote = trainer_party_quote(rom, trainer.trainer_class, trainer.trainer_set)
        approaches = []
        for facing in TrainerFacing:
            dy, dx = facing.delta
            at = (trainer.at[0] - dy, trainer.at[1] - dx)
            if min(at) < 0 or at in blocked[trainer.map_id]:
                continue
            try:
                plan = plan_route(
                    graph,
                    locals_,
                    start.map_id,
                    start.at,
                    trainer.map_id,
                    goal_at=at,
                    blocked=blocked,
                    capabilities=start.capabilities,
                    last_outside=start.last_outside_map,
                    start_mode="land",
                    goal_mode="land",
                )
            except RoutePlanningError:
                continue
            if len(plan.steps) > maximum_steps:
                continue
            previous = (start.map_id, start.at)
            for step in plan.steps:
                if (
                    (step.source_map, step.source_at) != previous
                    or step.expected_map not in maps
                    or step.source_at in blocked[step.source_map]
                    or step.expected_at in blocked[step.expected_map]
                    or (
                        step.transient_at is not None
                        and step.transient_at in blocked[step.source_map]
                    )
                    or step.action_kind is not MacroActionKind.MOVE
                    or step.action not in {"up", "down", "left", "right"}
                    or step.kind not in {"walk", "connection"}
                    or step.source_mode != "land"
                    or step.expected_mode != "land"
                ):
                    raise CartridgeReadError("regional trainer approach violates reserved corridor")
                previous = (step.expected_map, step.expected_at)
            if previous != (trainer.map_id, at):
                raise CartridgeReadError("regional trainer approach misses interaction boundary")
            approaches.append(TrainerFundingCandidate(trainer, quote, plan, facing))
        if approaches:
            result.append(min(approaches, key=lambda c: len(c.approach.steps)))
    return tuple(result)
