"""Candidate-relative, game-neutral reserve matchup features.

The controller may use these scalar mechanics without seeing species, move,
party-slot, opponent, map, or objective identity.  A title adapter supplies a
mechanics catalog and observable party move references; the shared layer turns
them into the same matchup quantities in every compatible game.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pokemon_red_completion.battle_semantics import (
    MAX_EFFECTIVE_POWER,
    MAX_LEVEL,
    STAB_MULTIPLIER,
    BattleMechanicsCatalog,
)

MIN_SAFE_SWITCH_HP_RATIO = 0.5
RESERVE_CONTROL_FEATURE_NAMES = (
    "party.reserve_matchup.available",
    "party.reserve_matchup.safe_available",
    "party.reserve_matchup.candidate_count",
    "party.reserve_matchup.best.hp_ratio",
    "party.reserve_matchup.best.has_status",
    "party.reserve_matchup.best.level",
    "party.reserve_matchup.best.level_margin",
    "party.reserve_matchup.best.offensive_type_margin",
    "party.reserve_matchup.best.offensive_power",
    "party.reserve_matchup.best.defensive_resistance",
    "party.reserve_matchup.best.usable_move_fraction",
    "party.reserve_matchup.best.mean_pp_fraction",
    "party.reserve_matchup.advantage.offensive_power",
    "party.reserve_matchup.advantage.defensive_resistance",
    "party.reserve_matchup.advantage.score",
)


class BattleMatchupError(ValueError):
    """Raised when a semantic observation cannot support reserve comparison."""


@dataclass(frozen=True, slots=True)
class PartyMatchupProfile:
    """Identity-free mechanics for one currently living party candidate."""

    party_slot: int
    hp_ratio: float
    has_status: bool
    level_fraction: float
    level_margin: float
    offensive_type_margin: float
    offensive_power: float
    defensive_resistance: float
    usable_move_fraction: float
    mean_pp_fraction: float

    def __post_init__(self) -> None:
        if type(self.party_slot) is not int or not 1 <= self.party_slot <= 6:  # noqa: E721
            raise ValueError("party_slot must be one-based and between one and six")
        for name in (
            "hp_ratio",
            "level_fraction",
            "offensive_power",
            "usable_move_fraction",
            "mean_pp_fraction",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and between zero and one")
        for name in (
            "level_margin",
            "offensive_type_margin",
            "defensive_resistance",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or not -1.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and between minus one and one")

    @property
    def safe(self) -> bool:
        return self.hp_ratio >= MIN_SAFE_SWITCH_HP_RATIO

    @property
    def score(self) -> float:
        """Bounded matchup utility used by both observation and target binding."""

        type_value = (self.offensive_type_margin + 1.0) / 2.0
        defense_value = (self.defensive_resistance + 1.0) / 2.0
        # Level is a real, portable combat resource. The first v3 lineage
        # showed that omitting it preferred a fragile lower-level trainee over
        # the established escort in four early switches. It stays below half
        # the utility so type, power, defense, and health still decide between
        # peers in the late-game roster.
        return min(
            1.0,
            max(
                0.0,
                0.20 * self.offensive_power
                + 0.25 * type_value
                + 0.10 * defense_value
                + 0.10 * self.hp_ratio
                + 0.35 * self.level_fraction,
            ),
        )

    def switch_rank(self) -> tuple[bool, float, float, float, bool, float, float, int]:
        """Prefer safe, useful matchups with deterministic identity-free ties."""

        return (
            self.safe,
            self.score,
            self.offensive_power,
            self.defensive_resistance,
            not self.has_status,
            self.hp_ratio,
            self.level_fraction,
            -self.party_slot,
        )


def project_party_matchups(
    observation: Mapping[str, object],
    catalog: BattleMechanicsCatalog,
) -> tuple[PartyMatchupProfile, ...]:
    """Project every living party member against the observed opponent."""

    if not isinstance(observation, Mapping):
        raise TypeError("observation must be a mapping")
    features = _mapping(observation.get("features"), "features")
    party = _mapping(features.get("party"), "party")
    battle = _mapping(features.get("battle"), "battle")
    opponent = catalog.resolve_species(_string(battle.get("opponent_species_ref"), "opponent"))
    opponent_level = _integer(battle.get("opponent_level"), 1, 100, "opponent level")
    members_value = party.get("members")
    if not isinstance(members_value, Sequence) or isinstance(
        members_value, (str, bytes, bytearray)
    ):
        raise BattleMatchupError("party.members must be a sequence")

    profiles: list[PartyMatchupProfile] = []
    for index, value in enumerate(members_value):
        member = _mapping(value, "party member")
        hp = _integer(member.get("hp"), 0, 999, "party hp")
        max_hp = _integer(member.get("max_hp"), 1, 999, "party max hp")
        if hp > max_hp:
            raise BattleMatchupError("party hp exceeds maximum hp")
        if hp == 0:
            continue
        level = _integer(member.get("level"), 1, 100, "party level")
        species = catalog.resolve_species(_string(member.get("species_ref"), "party species"))
        moves_value = member.get("moves")
        if not isinstance(moves_value, Sequence) or isinstance(
            moves_value, (str, bytes, bytearray)
        ):
            raise BattleMatchupError("party member moves must be a sequence")

        move_profiles: list[tuple[float, float, float]] = []
        for move_value in moves_value:
            move_view = _mapping(move_value, "party move")
            pp = _integer(move_view.get("pp"), 0, 63, "party move pp")
            move = catalog.resolve_move(_string(move_view.get("move_ref"), "party move"))
            pp_fraction = min(pp / move.max_pp, 1.0)
            if pp == 0 or move.category == "status" or move.power == 0:
                continue
            effectiveness = catalog.type_effectiveness(move.type_name, opponent.types)
            stab = STAB_MULTIPLIER if move.type_name in species.types else 1.0
            effective_power = move.power * stab * effectiveness
            move_profiles.append(
                (
                    _effectiveness_margin(effectiveness),
                    min(effective_power * move.accuracy / MAX_EFFECTIVE_POWER, 1.0),
                    pp_fraction,
                )
            )
        best = max(
            move_profiles,
            key=lambda row: (row[1], row[0], row[2]),
            default=(0.0, 0.0, 0.0),
        )
        incoming = max(
            catalog.type_effectiveness(type_name, species.types)
            for type_name in opponent.types
        )
        status = member.get("status")
        if status is not None and (not isinstance(status, str) or not status):
            raise BattleMatchupError("party status must be a semantic string or null")
        profiles.append(
            PartyMatchupProfile(
                party_slot=index + 1,
                hp_ratio=hp / max_hp,
                has_status=status is not None,
                level_fraction=level / MAX_LEVEL,
                level_margin=(level - opponent_level) / MAX_LEVEL,
                offensive_type_margin=best[0],
                offensive_power=best[1],
                defensive_resistance=-_effectiveness_margin(incoming),
                usable_move_fraction=min(len(move_profiles), 4) / 4.0,
                mean_pp_fraction=(
                    math.fsum(row[2] for row in move_profiles) / len(move_profiles)
                    if move_profiles
                    else 0.0
                ),
            )
        )
    return tuple(profiles)


def best_reserve_matchup(
    observation: Mapping[str, object],
    catalog: BattleMechanicsCatalog,
) -> PartyMatchupProfile | None:
    """Return the best living non-active candidate under the shared ranking."""

    active_slot = _active_slot(observation)
    reserves = tuple(
        profile
        for profile in project_party_matchups(observation, catalog)
        if profile.party_slot != active_slot and profile.safe
    )
    return max(reserves, key=PartyMatchupProfile.switch_rank, default=None)


def project_reserve_control_features(
    observation: Mapping[str, object],
    catalog: BattleMechanicsCatalog,
) -> tuple[float, ...]:
    """Summarize the best reserve and its advantage over the active battler."""

    active_slot = _active_slot(observation)
    profiles = project_party_matchups(observation, catalog)
    active = next((profile for profile in profiles if profile.party_slot == active_slot), None)
    if active is None:
        raise BattleMatchupError("active battler is absent or fainted")
    reserves = tuple(profile for profile in profiles if profile.party_slot != active_slot)
    if not reserves:
        return (0.0,) * len(RESERVE_CONTROL_FEATURE_NAMES)
    best = max(reserves, key=PartyMatchupProfile.switch_rank)
    return (
        1.0,
        float(any(profile.safe for profile in reserves)),
        min(len(reserves), 5) / 5.0,
        best.hp_ratio,
        float(best.has_status),
        best.level_fraction,
        best.level_margin,
        best.offensive_type_margin,
        best.offensive_power,
        best.defensive_resistance,
        best.usable_move_fraction,
        best.mean_pp_fraction,
        _clamp_signed(best.offensive_power - active.offensive_power),
        _clamp_signed(best.defensive_resistance - active.defensive_resistance),
        _clamp_signed(best.score - active.score),
    )


def _active_slot(observation: Mapping[str, object]) -> int:
    features = _mapping(observation.get("features"), "features")
    party = _mapping(features.get("party"), "party")
    index = _integer(party.get("active_index"), 0, 5, "active party index")
    return index + 1


def _effectiveness_margin(multiplier: float) -> float:
    if not isinstance(multiplier, (int, float)) or isinstance(multiplier, bool):
        raise BattleMatchupError("type effectiveness must be numeric")
    value = float(multiplier)
    if not math.isfinite(value) or not 0.0 <= value <= 4.0:
        raise BattleMatchupError("type effectiveness is outside the supported range")
    if value == 0.0:
        return -1.0
    return min(1.0, max(-1.0, math.log2(value) / 2.0))


def _clamp_signed(value: float) -> float:
    return min(1.0, max(-1.0, value))


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise BattleMatchupError(f"{label} must be a mapping")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise BattleMatchupError(f"{label} must be a non-empty semantic reference")
    return value


def _integer(value: object, minimum: int, maximum: int, label: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:  # noqa: E721
        raise BattleMatchupError(f"{label} is outside its supported range")
    return value
