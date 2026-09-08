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


def local_trainer_funding_candidates(
    rom: bytes,
    world: TrainerApproachWorld,
    start: TraversalSnapshot,
    trainers: tuple[TrainerSightZone, ...],
    *,
    maximum_steps: int = 256,
) -> tuple[TrainerFundingCandidate, ...]:
    """Quote reachable undefeated local trainers without issuing any action.

    Unsupported cartridge data fails closed rather than disappearing as a
    conveniently missing candidate. Already-defeated trainers never offer money.
    No candidate implies party safety, repeatable income or permission to fight.
    """
    if type(maximum_steps) is not int or maximum_steps < 1:
        raise ValueError("maximum_steps must be a positive integer")
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
            previous = start.at
            for step in plan.steps:
                if (
                    step.source_map != start.map_id
                    or step.expected_map != start.map_id
                    or step.source_at != previous
                    or step.expected_at in blocked
                    or step.action_kind is not MacroActionKind.MOVE
                    or step.action not in {"up", "down", "left", "right"}
                    or step.kind != "walk"
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
