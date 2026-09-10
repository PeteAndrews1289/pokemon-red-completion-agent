"""Deterministic escort lead planning for recovery and transit in Pokemon Red."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from pokemon_red_completion.party import (
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.red_battle_catalog import (
    RED_BATTLE_CATALOG,
    RedBattleCatalogError,
    pokemon_red_move_ref,
)


class RedCaptureLeadError(RuntimeError):
    """Raised when capture lead selection or party verification fails."""


@dataclass(frozen=True, slots=True)
class RedCaptureLeadPlan:
    """Immutable plan designating a healthy escort lead."""

    target_index: int
    party: PartyObservation

    def __post_init__(self) -> None:
        if not isinstance(self.party, PartyObservation):
            raise TypeError("party must be a PartyObservation")
        if type(self.target_index) is not int or not 0 <= self.target_index < self.party.size:
            raise ValueError("target_index is out of bounds for party size")

    @property
    def requires_swap(self) -> bool:
        return self.target_index != 0

    @property
    def target_member(self) -> PartyMemberObservation:
        return self.party.members[self.target_index]

    def require_current(self, party: PartyObservation) -> None:
        """Verify the current party matches the full planned snapshot."""
        if not isinstance(party, PartyObservation) or party != self.party:
            raise RedCaptureLeadError("party state has changed from planned snapshot")

    def require_result(self, party: PartyObservation) -> None:
        """Verify the expected post-swap permutation and all observed fields."""
        if not isinstance(party, PartyObservation):
            raise RedCaptureLeadError("result party must be a PartyObservation")
        if not self.requires_swap:
            if party != self.party:
                raise RedCaptureLeadError("party changed when no swap was planned")
            return
        if party.size != self.party.size:
            raise RedCaptureLeadError("party size changed during escort swap")
        expected_members = list(self.party.members)
        expected_members[0] = replace(self.party.members[self.target_index], slot=1)
        expected_members[self.target_index] = replace(
            self.party.members[0], slot=self.target_index + 1
        )
        expected = replace(self.party, members=tuple(expected_members))
        if party != expected:
            raise RedCaptureLeadError("party does not match expected post-swap result")


def _validate_threshold(threshold: float) -> None:
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ValueError("minimum_hp_ratio must be a real number")
    if not (0.0 < threshold <= 1.0) or not math.isfinite(threshold):
        raise ValueError("minimum_hp_ratio must be finite and satisfy 0 < x <= 1")


def _evaluate_member(
    member: PartyMemberObservation, minimum_hp_ratio: float,
) -> tuple[bool, int]:
    """Evaluate qualification and sum usable offensive PP.

    Fixed-damage zero-power moves are conservatively treated as unsupported.
    """
    if member.status != StatusCondition.HEALTHY or member.is_fainted or member.hp <= 0:
        return False, 0
    if member.hp_ratio < minimum_hp_ratio:
        return False, 0
    has_damaging_move = False
    offensive_pp = 0
    for move in member.moves:
        if not move.is_usable:
            continue
        try:
            ref = pokemon_red_move_ref(move.move_id)
            mechanics = RED_BATTLE_CATALOG.resolve_move(ref)
        except RedBattleCatalogError as err:
            raise RedCaptureLeadError("escort move mechanics are unsupported") from err
        if (
            mechanics.category != "status" and mechanics.power > 0
            and "self_destruct" not in mechanics.effect_flags
        ):
            has_damaging_move = True
            offensive_pp += move.current_pp
    return has_damaging_move, offensive_pp


def plan_capture_lead(
    party: PartyObservation, *, minimum_hp_ratio: float = 0.5,
) -> RedCaptureLeadPlan:
    """Plan an escort, retaining the current lead when qualified.

    A healthy escort with other fainted members is for guarded recovery only.
    This does not grant capture permission, which requires all members alive.
    Fixed-damage zero-power moves are conservatively unsupported.
    Self-destructive moves do not qualify as sustainable offensive capacity.
    This predicate does not choose battle moves or guarantee safe escape: the
    integrating executor must still guard actual battle actions and resources.
    """
    if not isinstance(party, PartyObservation):
        raise TypeError("party must be a PartyObservation")
    if party.size == 0:
        raise RedCaptureLeadError("party has no members")
    _validate_threshold(minimum_hp_ratio)
    lead = party.lead
    if lead is not None:
        qualified, _ = _evaluate_member(lead, minimum_hp_ratio)
        if qualified:
            return RedCaptureLeadPlan(target_index=0, party=party)
    candidates: list[tuple[tuple[int, float, int, int], int]] = []
    for idx, member in enumerate(party.members):
        qualified, offensive_pp = _evaluate_member(member, minimum_hp_ratio)
        if qualified:
            key = (member.level, member.hp_ratio, offensive_pp, -member.slot)
            candidates.append((key, idx))
    if not candidates:
        raise RedCaptureLeadError("no qualified healthy escort available in party")
    best = max(candidates, key=lambda item: item[0])
    return RedCaptureLeadPlan(target_index=best[1], party=party)
