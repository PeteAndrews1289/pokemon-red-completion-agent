"""Read-only local trainer funding candidates; not executable goal bindings.

Reserve every unbeaten trainer's complete sight lane, including the target's.
Computed approaches end beside the target for deliberate, identity-checked
interaction. Live party preparation, facing, engagement and payout settlement
remain mandatory before these candidates can become earned-resource outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from .actions import MacroActionKind
from .gen1_cartridge import CartridgeReadError
from .gen1_trainer_parties import TrainerPartyQuote, trainer_party_quote
from .gen1_trainer_sight import TrainerFacing, TrainerSightZone
from .route_executor import TraversalSnapshot
from .route_plan import RoutePlan, RoutePlanningError


class TrainerApproachWorld(Protocol):
    def plan_feasible_to_map(
        self, start: TraversalSnapshot, goal_map: int, *, goal_at: tuple[int, int]
    ) -> RoutePlan: ...


@dataclass(frozen=True, slots=True)
class TrainerFundingCandidate:
    trainer: TrainerSightZone
    quote: TrainerPartyQuote
    approach: RoutePlan
    interaction_facing: TrainerFacing


def valid_funding_ledge(source, target, transient, action: str) -> bool:
    """Only a two-square directional jump with its exact intermediate square."""
    directions = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}
    if action not in directions:
        return False
    dy, dx = directions[action]
    return transient == (source[0] + dy, source[1] + dx) and target == (
        source[0] + 2 * dy,
        source[1] + 2 * dx,
    )


def local_trainer_funding_candidates(
    rom: bytes,
    world: TrainerApproachWorld,
    start: TraversalSnapshot,
    trainers: tuple[TrainerSightZone, ...],
    *,
    maximum_steps: int = 256,
    allow_ledges: bool = False,
    allow_cut: bool = False,
    allow_forced_motion: bool = False,
) -> tuple[TrainerFundingCandidate, ...]:
    """Quote reachable undefeated local trainers without issuing any action.

    Unsupported cartridge data fails closed rather than disappearing as a
    conveniently missing candidate. Already-defeated trainers never offer money.
    No candidate implies party safety, repeatable income or permission to fight.
    """
    if type(maximum_steps) is not int or maximum_steps < 1:
        raise ValueError("maximum_steps must be a positive integer")
    if type(allow_cut) is not bool:
        raise TypeError("Cut approach scope must be explicit")
    if type(allow_forced_motion) is not bool:
        raise TypeError("forced-motion approach scope must be explicit")
    if any(t.map_id != start.map_id for t in trainers):
        raise ValueError("funding inventory must belong to the observed map")
    if len({t.sprite_index for t in trainers}) != len(trainers):
        raise ValueError("funding inventory contains duplicate trainer identities")
    if not start.ready or start.interruption is not None or start.mode != "land":
        return ()
    blocked = start.occupied.union(t.at for t in trainers)
    for trainer in trainers:
        if trainer.active:
            blocked = blocked.union(trainer.lane)
    blocked = blocked.union(hazard.at for hazard in start.hazards)
    if start.at in blocked:
        return ()
    origin = replace(start, occupied=blocked)
    result = []
    for trainer in trainers:
        if trainer.defeated:
            continue
        quote = trainer_party_quote(rom, trainer.trainer_class, trainer.trainer_set)
        approaches = []
        for facing in TrainerFacing:
            dy, dx = facing.delta
            at = (trainer.at[0] - dy, trainer.at[1] - dx)
            if min(at) < 0 or at in blocked:
                continue
            try:
                plan = world.plan_feasible_to_map(origin, start.map_id, goal_at=at)
            except RoutePlanningError:
                continue
            if len(plan.steps) > maximum_steps:
                continue
            if any(
                step.source_map != start.map_id or step.expected_map != start.map_id
                for step in plan.steps
            ):
                # Composed routing can legitimately leave/re-enter a cave to
                # reach another component. That is not a LOCAL trainer approach.
                continue
            previous = start.at
            for step in plan.steps:
                # Story gym approaches may cross cartridge-decoded spinners.
                # Authenticate the complete edge, including every intermediate
                # tile, against the same world used for the guarded route.
                graphs = getattr(world, "local_graphs", {})
                graph = graphs.get(start.map_id)
                forced = (
                    allow_forced_motion
                    and step.kind == "forced_motion"
                    and bool(step.via)
                    and not blocked.intersection(step.via)
                    and graph is not None
                    and any(
                        edge.kind == "forced_motion"
                        and edge.target == step.expected_at
                        and edge.action == step.action
                        and edge.action_kind is step.action_kind
                        and edge.via == step.via
                        and edge.transient == step.transient_at
                        and edge.permits_mode(step.source_mode)
                        and edge.next_mode(step.source_mode) == step.expected_mode
                        and edge.requirements <= start.capabilities
                        for edge in graph.neighbors(step.source_at)
                    )
                )
                cut = (
                    allow_cut
                    and "move:cut" in start.capabilities
                    and step.kind == "cut_mutation"
                    and step.action_kind is MacroActionKind.FIELD_MOVE
                    and step.action in {"cut:up", "cut:down", "cut:left", "cut:right"}
                    and step.expected_at == step.source_at
                    and step.transient_at is None
                )
                if (
                    step.source_map != start.map_id
                    or step.expected_map != start.map_id
                    or step.source_at != previous
                    or step.expected_at in blocked
                    or step.transient_at in blocked
                    or not (
                        cut
                        or (
                            step.action_kind is MacroActionKind.MOVE
                            and step.action in {"up", "down", "left", "right"}
                            and (
                                step.kind == "walk"
                                or forced
                                or (
                                    allow_ledges is True
                                    and step.kind == "ledge"
                                    and valid_funding_ledge(
                                        step.source_at,
                                        step.expected_at,
                                        step.transient_at,
                                        step.action,
                                    )
                                )
                            )
                        )
                    )
                    or step.source_mode != "land"
                    or step.expected_mode != "land"
                ):
                    raise CartridgeReadError("trainer approach violates reserved walking corridor")
                previous = step.expected_at
            if previous != at:
                raise CartridgeReadError("trainer approach does not reach its interaction boundary")
            approaches.append(TrainerFundingCandidate(trainer, quote, plan, facing))
        if approaches:
            result.append(min(approaches, key=lambda c: len(c.approach.steps)))
    return tuple(result)
