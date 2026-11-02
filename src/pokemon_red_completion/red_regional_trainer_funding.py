"""Bounded income candidates across ordinary map connections.

This is a prospective skill planner, not learned trainer selection. Defaults
exclude doors; an explicit observed indoor exit is supported without adding
arbitrary doors, HMs, ledges or scripted passages. No candidate authorizes input.
The existing funding executor must recheck live hazards and target identity.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Protocol

from .actions import MacroActionKind
from .gen1_cartridge import CartridgeReadError
from .gen1_trainer_parties import trainer_party_quote
from .gen1_trainer_sight import TrainerFacing, TrainerSightZone
from .global_router import MacroEdge, MacroGraph
from .local_router import LocalEdge, LocalGraph
from .red_trainer_funding import TrainerFundingCandidate, valid_funding_ledge
from .route_executor import TraversalSnapshot
from .route_plan import RoutePlanningError, plan_route


def _funding_surf_edge(edge: LocalEdge) -> bool:
    """Only cartridge Surf entry, travel and exit; no new movement primitive."""
    directions = {"up", "down", "left", "right"}
    if edge.kind == "water_entry":
        return (
            edge.action_kind is MacroActionKind.FIELD_MOVE
            and edge.action in {"surf:" + d for d in directions}
            and edge.required_mode == "land" and edge.result_mode == "water"
            and "move:surf" in edge.requirements
        )
    return (
        edge.kind in {"water_travel", "water_exit"}
        and edge.action_kind is MacroActionKind.MOVE and edge.action in directions
        and edge.required_mode == "water"
        and edge.result_mode in ({None, "water"} if edge.kind == "water_travel" else {"land"})
    )

# Ordinary passage interiors whose story guards already live in the Red local
# graphs. This is adapter capability metadata, not a route or policy feature.
# Exclude lifts, teleporters, paid gates, badge checkpoints and bike-only gates.
_SUPPORTED_FUNDING_GATES = frozenset({0x2F, 0x31, 0x32, 0x46, 0x49, 0x4C, 0x4F, 0xB8})


@dataclass(frozen=True)
class FundingGateTransit:
    """Explicit bounded map inventory for ordinary-gate funding transport.

    Callers declare the complete region before input; nothing grows it after a
    failure. Every map needs trainer and static-object coverage. Default funding
    remains one-hop and never enables this contract implicitly.
    """

    maps: frozenset[int]
    gate_maps: frozenset[int]
    maximum_transitions: int = 6

    def __post_init__(self):
        if (
            not isinstance(self.maps, frozenset)
            or not 1 <= len(self.maps) <= 16
            or any(type(m) is not int or not 0 <= m < 256 for m in self.maps)
            or not isinstance(self.gate_maps, frozenset)
            or not self.gate_maps
            or any(type(m) is not int for m in self.gate_maps)
            or not self.gate_maps <= self.maps & _SUPPORTED_FUNDING_GATES
            or type(self.maximum_transitions) is not int
            or not 1 <= self.maximum_transitions <= 8
        ):
            raise ValueError("funding gate transit requires a bounded ordinary-gate inventory")

    def permits(self, source: int, edge: MacroEdge) -> bool:
        if edge.kind == "return":
            return bool(source in self.gate_maps and edge.at is not None
                        and edge.destination_warp_index is not None)
        return bool(
            source in self.maps and edge.target_map in self.maps
            and edge.target_map != source
            and edge.kind == "warp"
            and (source in self.gate_maps or edge.target_map in self.gate_maps)
            and edge.at is not None and edge.arrival_at is not None
        )

    def private_dict(self) -> dict[str, object]:
        return dict(maps=sorted(self.maps), gate_maps=sorted(self.gate_maps),
                    maximum_transitions=self.maximum_transitions)


class ConnectedFundingWorld(Protocol):
    @property
    def macro_graph(self) -> MacroGraph: ...

    @property
    def local_graphs(self) -> Mapping[int, LocalGraph]: ...


def observed_fly_funding_gate_region(
    world: ConnectedFundingWorld,
    start: TraversalSnapshot,
    region: FundingGateTransit,
    native_fly_destinations,
) -> FundingGateTransit | None:
    """Quote an existing inventoried region from a legal observed Fly origin.

    The caller opts into a fixed region; this never discovers or enables a door.
    Native Fly admission and every route/battle guard still own execution.
    Keep this as an additional inventory so unrelated town offers stay available.
    """
    from .observation import RED_FLY_TOWN_NAMES

    if not isinstance(region, FundingGateTransit):
        raise TypeError("observed Fly funding requires a typed fixed region")
    if (
        not isinstance(start, TraversalSnapshot)
        or start.ready is not True
        or start.interruption is not None
        or start.mode != "land"
        or type(start.map_id) is not int
        or not 0 <= start.map_id < 256
        or start.map_id == 0x0B
        or not isinstance(native_fly_destinations, (tuple, frozenset))
        or any(type(town) is not int or not 0 <= town < len(RED_FLY_TOWN_NAMES)
               for town in native_fly_destinations)
        or not region.maps.intersection(native_fly_destinations)
    ):
        return None
    outside = start.last_outside_map
    if ((outside is not None and (type(outside) is not int
                                 or not 0 <= outside <= 0x24 or outside == 0x0B))
            or start.map_id >= 0x25 and outside is None):
        return None
    maps = region.maps | {start.map_id} | ({outside} if outside is not None else set())
    blockers = getattr(world, "object_blockers", {})
    if (
        len(maps) > 16
        or not maps <= set(world.macro_graph.edges)
        or not maps <= set(world.local_graphs)
        or not maps <= set(blockers)
        or any(not isinstance(blockers[m], frozenset) for m in maps)
        or any(world.macro_graph.retained_outside_overrides.get(m, m) not in maps
               for m in maps)
    ):
        return None
    return FundingGateTransit(frozenset(maps), region.gate_maps, region.maximum_transitions)


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
    indoor_exit_map: int | None = None,
    static_blockers: Mapping[int, frozenset[tuple[int, int]]] | None = None,
    allow_ledges: bool = False,
    allow_surf: bool = False,
    gate_transit: FundingGateTransit | None = None,
    required_interaction_at: tuple[int, int] | None = None,
) -> tuple[TrainerFundingCandidate, ...]:
    """Route only through inventoried maps, reserving bodies and all sight lanes.

    The inventory caller must include every ordinary trainer on every permitted
    map, joining the current map to live objects and other maps to cartridge
    positions. Explicit map coverage distinguishes an empty map from missing data.
    """
    if type(maximum_steps) is not int or maximum_steps < 1:
        raise ValueError("maximum_steps must be a positive integer")
    if type(allow_surf) is not bool:
        raise TypeError("funding Surf scope must be an explicit boolean")
    if required_interaction_at is not None and (
        not isinstance(required_interaction_at, tuple)
        or len(required_interaction_at) != 2
        or any(type(n) is not int or n < 0 for n in required_interaction_at)
    ):
        raise ValueError("retained funding interaction needs two nonnegative integers")
    maps = funding_scope(world.macro_graph, start, indoor_exit_map=indoor_exit_map,
                         gate_transit=gate_transit)
    if inventoried_maps != maps or any(t.map_id not in maps for t in trainers):
        raise ValueError("regional funding requires complete bounded map inventory")
    if gate_transit is not None and not maps <= set(world.local_graphs):
        raise ValueError("gate transit requires complete local traversal inventory")
    if len({(t.map_id, t.sprite_index) for t in trainers}) != len(trainers):
        raise ValueError("regional funding contains duplicate trainer identities")
    if not start.ready or start.interruption is not None or start.mode != "land":
        return ()
    if gate_transit is not None and static_blockers is None:
        raise ValueError("gate transit requires complete static object inventory")
    if static_blockers is not None and (
        set(static_blockers) != maps
        or any(not isinstance(points, frozenset) for points in static_blockers.values())
    ):
        raise ValueError("regional funding requires complete static object inventory")
    blocked: dict[int, frozenset[tuple[int, int]]] = {
        m: static_blockers[m] if static_blockers is not None else frozenset() for m in maps
    }
    blocked[start.map_id] |= start.occupied | frozenset(h.at for h in start.hazards)
    for trainer in trainers:
        blocked[trainer.map_id] |= {trainer.at}
        if trainer.active:
            blocked[trainer.map_id] |= set(trainer.lane)
    if start.at in blocked[start.map_id]:
        return ()
    # Defaults stay walking-only. An explicit Surf quote requires the actual
    # observed capability and must still begin/end on land; keep story guards.
    surf = allow_surf and "move:surf" in start.capabilities
    graph = replace(
        world.macro_graph,
        edges={
            m: tuple(
                e
                for e in world.macro_graph.neighbors(m)
                if (e.kind == "connection" and e.target_map in maps)
                or (gate_transit is not None and gate_transit.permits(m, e))
                or (
                    indoor_exit_map is not None
                    and m == start.map_id
                    and e.kind in {"warp", "return"}
                    and (
                        e.target_map == indoor_exit_map
                        or (e.kind == "return" and e.target_map is None)
                    )
                )
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
                    if (
                        (
                            (e.kind == "walk" or (
                                allow_ledges is True and e.kind == "ledge"
                                and valid_funding_ledge(at, e.target, e.transient, e.action)
                            ))
                            and e.action_kind is MacroActionKind.MOVE
                            and e.action in {"up", "down", "left", "right"}
                            and e.required_mode in {None, "land"}
                            and e.result_mode in {None, "land"}
                        )
                        or (surf and _funding_surf_edge(e))
                    )
                    and e.transient not in blocked[m]
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
        # The cartridge trainer bit also marks scripted encounters such as
        # stationary legendaries.  They remain reserved bodies/sight lanes
        # above, but they are not ordinary payout candidates and their script
        # identifiers do not index the trainer-party table.  Do not let one
        # such object make an otherwise healthy post-action observation fail.
        if type(trainer.trainer_class) is not int or not 201 <= trainer.trainer_class <= 246:
            continue
        quote = trainer_party_quote(rom, trainer.trainer_class, trainer.trainer_set)
        approaches = []
        for facing in TrainerFacing:
            dy, dx = facing.delta
            at = (trainer.at[0] - dy, trainer.at[1] - dx)
            if required_interaction_at is not None and at != required_interaction_at:
                continue
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
            if gate_transit is not None and (
                len(plan.macro_path.edges) > gate_transit.maximum_transitions
            ):
                continue
            if gate_transit is not None and any(
                edge not in graph.neighbors(source)
                for source, edge in zip(
                    plan.macro_path.maps[:-1], plan.macro_path.edges, strict=True
                )
            ):
                raise CartridgeReadError("gate funding plan contains undeclared transition")
            previous = (start.map_id, start.at)
            for step in plan.steps:
                surf_local_step = surf and step.source_map == step.expected_map and any(
                    _funding_surf_edge(edge)
                    and edge.target == step.expected_at and edge.action == step.action
                    and edge.action_kind is step.action_kind and edge.kind == step.kind
                    and edge.transient == step.transient_at and edge.via == step.via
                    and edge.permits_mode(step.source_mode)
                    and edge.next_mode(step.source_mode) == step.expected_mode
                    and edge.requirements <= start.capabilities
                    for edge in world.local_graphs[step.source_map].neighbors(step.source_at)
                )
                surf_connection = (
                    surf and step.kind == "connection"
                    and step.action_kind is MacroActionKind.MOVE
                    and step.source_mode == step.expected_mode == "water"
                    and any(
                        edge.kind == "connection" and edge.target_map == step.expected_map
                        and any((hop.exit_at, hop.arrival_at, hop.action)
                            == (step.source_at, step.expected_at, step.action)
                            for hop in edge.coordinate_transitions)
                        for edge in graph.neighbors(step.source_map)
                    )
                )
                surf_step = surf_local_step or surf_connection
                if (
                    (step.source_map, step.source_at) != previous
                    or step.expected_map not in maps
                    or step.source_at in blocked[step.source_map]
                    or step.expected_at in blocked[step.expected_map]
                    or (
                        step.transient_at is not None
                        and step.transient_at in blocked[step.source_map]
                    )
                    or (not surf_step and step.action_kind is not MacroActionKind.MOVE)
                    or (not surf_step and step.action not in {"up", "down", "left", "right"})
                    or (
                        step.kind not in {"walk", "connection"}
                        and not surf_step
                        and not (
                            allow_ledges is True
                            and step.kind == "ledge"
                            and step.source_map == step.expected_map
                            and valid_funding_ledge(
                                step.source_at, step.expected_at, step.transient_at, step.action
                            )
                        )
                        and not (
                            indoor_exit_map is not None
                            and step.source_map == start.map_id
                            and step.expected_map == indoor_exit_map
                            and step.kind in {"warp", "return"}
                        )
                        and not (
                            gate_transit is not None
                            and step.kind in {"warp", "return"}
                            and any(
                                gate_transit.permits(step.source_map, edge)
                                and (edge.target_map == step.expected_map
                                     or (edge.kind == "return"
                                         and step.expected_map in gate_transit.maps))
                                for edge in world.macro_graph.neighbors(step.source_map)
                            )
                        )
                    )
                    or (not surf_step and step.source_mode != "land")
                    or (not surf_step and step.expected_mode != "land")
                ):
                    raise CartridgeReadError("regional trainer approach violates reserved corridor")
                previous = (step.expected_map, step.expected_at)
            if previous != (trainer.map_id, at):
                raise CartridgeReadError("regional trainer approach misses interaction boundary")
            approaches.append(TrainerFundingCandidate(trainer, quote, plan, facing))
        if approaches:
            result.append(min(approaches, key=lambda c: len(c.approach.steps)))
    return tuple(result)


def funding_scope(
    graph: MacroGraph,
    start: TraversalSnapshot,
    *,
    indoor_exit_map: int | None = None,
    gate_transit: FundingGateTransit | None = None,
) -> frozenset[int]:
    """Default: indoor exit plus its outside map and immediate connections.

    An explicit gate contract substitutes a fixed fully inventoried region;
    it never grows by exploration. No Fly, HM or arbitrary doors are enabled.
    """
    if indoor_exit_map is not None and (
        type(indoor_exit_map) is not int
        or not 0 <= indoor_exit_map <= 0x24
        or start.map_id < 0x25
        or start.last_outside_map != indoor_exit_map
    ):
        raise ValueError("funding departure requires the observed indoor/outdoor boundary")
    if gate_transit is not None:
        if not isinstance(gate_transit, FundingGateTransit):
            raise TypeError("funding transit needs a typed contract")
        if (
            start.map_id not in gate_transit.maps
            or not gate_transit.maps <= set(graph.edges)
            or (indoor_exit_map is not None and indoor_exit_map not in gate_transit.maps)
            or (start.last_outside_map is not None
                and start.last_outside_map not in gate_transit.maps)
            or any(graph.retained_outside_overrides.get(m, m) not in gate_transit.maps
                   for m in gate_transit.maps)
        ):
            raise ValueError("funding gate inventory does not cover the observed origin")
        return gate_transit.maps
    if indoor_exit_map is None:
        return connected_funding_maps(graph, start.map_id)
    return connected_funding_maps(graph, indoor_exit_map) | {start.map_id}
