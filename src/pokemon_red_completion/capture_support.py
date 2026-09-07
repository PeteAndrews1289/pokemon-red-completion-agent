"""Portable, bounded non-damaging status support for a capture skill.

The title adapter supplies verified move effects and immunities. Species names,
raw memory, target identities and routes do not participate in this selector.
This is deterministic skill support, not a learned capture policy.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from pokemon_red_completion.party import PartyObservation, StatusCondition


@dataclass(frozen=True, slots=True)
class CaptureSupportSummary:
    """Public-safe observed skill diagnostics; never a policy feature or target."""

    status_attempts: int
    verified_status_observations: int
    party_preparations: int = 0

    def __post_init__(self) -> None:
        if any(type(value) is not int for value in (
            self.status_attempts, self.verified_status_observations, self.party_preparations,
        )) or not (
            0 <= self.verified_status_observations <= self.status_attempts <= 1_000
            and 0 <= self.party_preparations <= 1
        ):
            raise ValueError("capture support diagnostic bounds differ")

    def public_dict(self) -> dict[str, int]:
        return {"status_attempts": self.status_attempts,
                "verified_status_observations": self.verified_status_observations,
                "party_preparations": self.party_preparations}

    @classmethod
    def from_evidence(cls, evidence: Mapping[str, object]) -> CaptureSupportSummary | None:
        value = evidence.get("capture_support")
        if value is None:
            return None
        if not isinstance(value, Mapping) or set(value) != {
            "status_attempts", "verified_status_observations", "party_preparations",
        } or any(type(item) is not int for item in value.values()):
            raise ValueError("capture support diagnostics differ")
        return cls(value["status_attempts"], value["verified_status_observations"],
                   value["party_preparations"])


@dataclass(frozen=True, slots=True)
class CaptureStatusOption:
    party_slot: int
    move_slot: int
    condition: StatusCondition
    accuracy: float

    def __post_init__(self) -> None:
        if type(self.party_slot) is not int or not 1 <= self.party_slot <= 6:
            raise ValueError("capture status party slot differs")
        if type(self.move_slot) is not int or not 1 <= self.move_slot <= 4:
            raise ValueError("capture status move slot differs")
        if not isinstance(self.condition, StatusCondition) or self.condition not in {
            StatusCondition.SLEEP, StatusCondition.PARALYSIS,
        }:
            raise ValueError("capture support must not damage its target over time")
        if (
            isinstance(self.accuracy, bool)
            or not isinstance(self.accuracy, (int, float))
            or not math.isfinite(self.accuracy)
            or not 0 < self.accuracy <= 1
        ):
            raise ValueError("capture status accuracy differs")


def choose_capture_status(
    party: PartyObservation,
    options: tuple[CaptureStatusOption, ...],
    *,
    target_status: StatusCondition,
    attempts_used: int,
    maximum_attempts: int = 3,
    active_party_slot: int | None = None,
    minimum_hp_ratio: float = 0.5,
) -> CaptureStatusOption | None:
    """Prefer an already-active healthy helper, then accuracy and readiness.

No status success is inferred from the selected move. A caller must read the
actual target status after a bounded turn. Missing capability returns None,
not a damaging replacement move or permission to loop.
    """
    if not isinstance(party, PartyObservation) or not isinstance(target_status, StatusCondition):
        raise TypeError("capture status needs semantic party and target status")
    if type(attempts_used) is not int or attempts_used < 0:
        raise ValueError("capture status attempt count differs")
    if type(maximum_attempts) is not int or not 1 <= maximum_attempts <= 10:
        raise ValueError("capture status attempt bound differs")
    if not isinstance(options, tuple) or any(
        not isinstance(option, CaptureStatusOption) for option in options
    ):
        raise TypeError("capture status options differ")
    if len({(option.party_slot, option.move_slot) for option in options}) != len(options):
        raise ValueError("capture status repeats a move")
    if (
        isinstance(minimum_hp_ratio, bool)
        or not isinstance(minimum_hp_ratio, (float, int))
        or not math.isfinite(minimum_hp_ratio)
        or not 0 < minimum_hp_ratio < 1
    ):
        raise ValueError("capture status safety threshold differs")
    if active_party_slot is not None and (
        type(active_party_slot) is not int or not 1 <= active_party_slot <= len(party.members)
    ):
        raise ValueError("capture status active slot differs")
    for option in options:
        if option.party_slot > len(party.members):
            raise ValueError("capture status option names an absent member")
        if option.move_slot > len(party.members[option.party_slot - 1].moves):
            raise ValueError("capture status option names an absent move")
    if target_status is not StatusCondition.HEALTHY or attempts_used >= maximum_attempts:
        return None
    ready = [
        option for option in options
        if (member := party.members[option.party_slot - 1]).status is StatusCondition.HEALTHY
        and member.hp_ratio > minimum_hp_ratio
        and member.moves[option.move_slot - 1].is_usable
    ]
    return min(
        ready,
        key=lambda option: (
            option.party_slot != active_party_slot,
            -option.accuracy,
            -party.members[option.party_slot - 1].level,
            -party.members[option.party_slot - 1].hp_ratio,
            option.party_slot,
            option.move_slot,
        ),
        default=None,
    )
