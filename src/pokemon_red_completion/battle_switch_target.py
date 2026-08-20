"""Permutation-equivariant features for learned battle switch targets.

Switch timing and switch-target binding are separate decisions.  The full-battle
controller can request a switch without seeing a party slot; this module turns
each legal reserve into the same identity-free mechanics vector so a listwise
ranker can learn which reserve should receive that request.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from pokemon_red_completion.battle_matchups import (
    MIN_SAFE_SWITCH_HP_RATIO,
    PartyMatchupProfile,
    project_party_matchups,
)
from pokemon_red_completion.battle_semantics import BattleMechanicsCatalog

SWITCH_TARGET_FEATURE_SCHEMA_ID = "pokemon.core.battle.switch-target.features.v1"
SWITCH_TARGET_FEATURE_NAMES = (
    "candidate.hp_ratio",
    "candidate.has_status",
    "candidate.safe_hp",
    "candidate.level",
    "candidate.level_margin",
    "candidate.offensive_type_margin",
    "candidate.offensive_power",
    "candidate.defensive_resistance",
    "candidate.usable_move_fraction",
    "candidate.mean_pp_fraction",
)


class BattleSwitchTargetError(ValueError):
    """Raised when a semantic observation cannot define a target choice."""


@dataclass(frozen=True, slots=True)
class BattleSwitchTargetCandidate:
    """One ephemeral reserve binding plus its identity-free feature vector."""

    party_slot: int
    features: tuple[float, ...]

    def __post_init__(self) -> None:
        if type(self.party_slot) is not int or not 1 <= self.party_slot <= 6:  # noqa: E721
            raise BattleSwitchTargetError("candidate party slot is invalid")
        if len(self.features) != len(SWITCH_TARGET_FEATURE_NAMES) or any(
            not math.isfinite(value) for value in self.features
        ):
            raise BattleSwitchTargetError("candidate features are invalid")


@dataclass(frozen=True, slots=True)
class BattleSwitchTargetSet:
    """All currently living reserves in their ephemeral observation order."""

    candidates: tuple[BattleSwitchTargetCandidate, ...]

    def __post_init__(self) -> None:
        if not self.candidates or any(
            not isinstance(candidate, BattleSwitchTargetCandidate)
            for candidate in self.candidates
        ):
            raise BattleSwitchTargetError("switch target candidates are empty or invalid")
        slots = tuple(candidate.party_slot for candidate in self.candidates)
        if len(set(slots)) != len(slots):
            raise BattleSwitchTargetError("switch target party slots are duplicated")

    def candidate_index_for_party_slot(self, party_slot: int) -> int:
        matches = tuple(
            index
            for index, candidate in enumerate(self.candidates)
            if candidate.party_slot == party_slot
        )
        if len(matches) != 1:
            raise BattleSwitchTargetError("demonstrated switch target is unavailable")
        return matches[0]


@dataclass(frozen=True, slots=True)
class BattleSwitchTargetExample:
    """One authenticated listwise target choice."""

    observation: BattleSwitchTargetSet
    selected_candidate_index: int
    battle_plan_id: str
    decision_index: int

    def __post_init__(self) -> None:
        if not isinstance(self.observation, BattleSwitchTargetSet):
            raise BattleSwitchTargetError("switch target observation is invalid")
        if (
            type(self.selected_candidate_index) is not int  # noqa: E721
            or not 0 <= self.selected_candidate_index < len(self.observation.candidates)
        ):
            raise BattleSwitchTargetError("selected switch target index is invalid")
        if not isinstance(self.battle_plan_id, str) or not self.battle_plan_id:
            raise BattleSwitchTargetError("battle plan identity is invalid")
        if type(self.decision_index) is not int or self.decision_index < 1:  # noqa: E721
            raise BattleSwitchTargetError("switch target decision index is invalid")


def project_switch_target_candidates(
    observation: Mapping[str, object],
    catalog: BattleMechanicsCatalog,
) -> BattleSwitchTargetSet:
    """Project every living non-active member without exposing party identity."""

    try:
        features = observation["features"]
        if not isinstance(features, Mapping):
            raise BattleSwitchTargetError("observation features are unavailable")
        party = features["party"]
        if not isinstance(party, Mapping):
            raise BattleSwitchTargetError("party observation is unavailable")
        active_index = party["active_index"]
        if type(active_index) is not int or not 0 <= active_index <= 5:  # noqa: E721
            raise BattleSwitchTargetError("active party index is invalid")
        profiles = project_party_matchups(observation, catalog)
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, BattleSwitchTargetError):
            raise
        raise BattleSwitchTargetError("switch target projection failed") from error
    active_slot = active_index + 1
    candidates = tuple(
        BattleSwitchTargetCandidate(
            party_slot=profile.party_slot,
            features=_profile_features(profile),
        )
        for profile in profiles
        if profile.party_slot != active_slot
    )
    return BattleSwitchTargetSet(candidates)


def _profile_features(profile: PartyMatchupProfile) -> tuple[float, ...]:
    return (
        profile.hp_ratio,
        float(profile.has_status),
        float(profile.hp_ratio >= MIN_SAFE_SWITCH_HP_RATIO),
        profile.level_fraction,
        profile.level_margin,
        profile.offensive_type_margin,
        profile.offensive_power,
        profile.defensive_resistance,
        profile.usable_move_fraction,
        profile.mean_pp_fraction,
    )
