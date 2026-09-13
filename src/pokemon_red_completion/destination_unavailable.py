"""Typed, path-free fresh-destination diagnostics; never outcome or policy labels."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pokemon_red_completion.goal_manager import GoalUnavailableReason


@dataclass(frozen=True, slots=True)
class DestinationUnavailableSummary:
    reason: GoalUnavailableReason

    def __post_init__(self) -> None:
        if not isinstance(self.reason, GoalUnavailableReason):
            raise ValueError("destination unavailable reason differs")

    def public_dict(self) -> dict[str, str]:
        return {"reason": self.reason.value}

    @classmethod
    def from_evidence(
        cls, evidence: Mapping[str, object],
    ) -> DestinationUnavailableSummary | None:
        if "destination_unavailable" not in evidence:
            return None
        value = evidence["destination_unavailable"]
        if not isinstance(value, Mapping) or set(value) != {"reason"}:
            raise ValueError("destination unavailable fields differ")
        reason = value["reason"]
        if type(reason) is not str:
            raise ValueError("destination unavailable reason differs")
        try:
            return cls(GoalUnavailableReason(reason))
        except ValueError:
            # Do not reproduce an untrusted string or private path in the error.
            raise ValueError("destination unavailable reason differs") from None
