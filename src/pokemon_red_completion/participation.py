"""Game-neutral party-participation measurements."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PartyParticipationReport:
    """Summarize which party members supplied recorded attack decisions."""

    turns_per_member: tuple[int, ...]
    unobserved_turns: int

    @property
    def observed_turns(self) -> int:
        return sum(self.turns_per_member)

    @property
    def total_turns(self) -> int:
        return self.observed_turns + self.unobserved_turns

    @property
    def participating_members(self) -> int:
        return sum(turns > 0 for turns in self.turns_per_member)

    @property
    def busiest_member_turns(self) -> int:
        return max(self.turns_per_member, default=0)

    @property
    def busiest_member_share(self) -> float | None:
        if self.observed_turns == 0:
            return None
        return self.busiest_member_turns / self.observed_turns

    def public_dict(self) -> dict[str, object]:
        return {
            "turns_per_member": list(self.turns_per_member),
            "observed_turns": self.observed_turns,
            "unobserved_turns": self.unobserved_turns,
            "participating_members": self.participating_members,
            "busiest_member_turns": self.busiest_member_turns,
            "busiest_member_share": self.busiest_member_share,
        }


def summarize_party_participation(
    active_party_indexes: Iterable[int | None],
    *,
    party_size: int,
) -> PartyParticipationReport:
    """Count attack decisions by active slot without inventing missing observations."""
    if party_size < 1:
        raise ValueError("party_size must be positive")
    turns_per_member = [0] * party_size
    unobserved_turns = 0
    for index in active_party_indexes:
        if index is None or not 0 <= index < party_size:
            unobserved_turns += 1
        else:
            turns_per_member[index] += 1
    return PartyParticipationReport(tuple(turns_per_member), unobserved_turns)
