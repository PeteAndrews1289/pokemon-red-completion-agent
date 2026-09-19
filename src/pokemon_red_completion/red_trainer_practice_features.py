"""Versioned, identity-free stat features for outcome-trained battle heads.

The player can inspect its own stats. Opponent inputs are public species base
stats and a neutral-DV estimate; no opponent live stat, DV, reserve or RNG is
read. This view deliberately does not migrate frozen legacy head weights.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.battle_control_features import (
    CONTROL_FEATURE_NAMES,
    project_control_features,
)
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES as LEGACY_MOVE_NAMES,
)
from pokemon_red_completion.battle_semantics import (
    BattleFeatureBatch,
    BattleMechanicsCatalog,
)
from pokemon_red_completion.battle_switch_target import (
    SWITCH_TARGET_FEATURE_NAMES,
    project_switch_target_candidates,
)

MOVE_SCHEMA_ID = "pokemon.core.battle.move-ranker.observable-stats.v1"
CONTROL_SCHEMA_ID = "pokemon.core.battle.control.observable-stats.v2"
SWITCH_SCHEMA_ID = "pokemon.core.battle.switch.observable-stats.v1"
_STATS = ("attack", "defense", "speed", "special")
_STAT_STATE_NAMES = (
    *(f"observable.player.stat.{name}" for name in _STATS),
    *(f"observable.opponent.public_base.{name}" for name in _STATS),
    *(f"observable.opponent.neutral_estimate.{name}" for name in _STATS),
    "observable.player.special_stage",
    *(
        f"observable.opponent.status.{name}"
        for name in ("none", "sleep", "poison", "burn", "freeze", "paralysis", "other")
    ),
)
MOVE_FEATURE_NAMES = (
    *LEGACY_MOVE_NAMES,
    *_STAT_STATE_NAMES,
    "interaction.physical_attack_over_estimated_defense",
    "interaction.special_over_estimated_special",
    "interaction.player_speed_over_estimated_speed",
)
_STATELESS_CONTROL_INDICES = tuple(
    index for index, name in enumerate(CONTROL_FEATURE_NAMES) if not name.startswith("history.")
)
CONTROL_FEATURE_NAMES_V2 = (
    *(CONTROL_FEATURE_NAMES[index] for index in _STATELESS_CONTROL_INDICES),
    *_STAT_STATE_NAMES,
    *(f"party.best_living_reserve.stat.{name}" for name in _STATS),
)
SWITCH_FEATURE_NAMES_V2 = (
    *SWITCH_TARGET_FEATURE_NAMES,
    *_STAT_STATE_NAMES,
    *(f"candidate.stat.{name}" for name in _STATS),
    *(f"candidate.stat_margin.{name}" for name in _STATS),
)


class TrainerStatFeatureError(ValueError):
    """The rich observation is absent or contains impossible visible stats."""


@dataclass(frozen=True, slots=True)
class TrainerCandidateFeatures:
    schema_id: str
    feature_names: tuple[str, ...]
    candidate_vectors: tuple[tuple[float, ...], ...]
    candidate_slots: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.candidate_vectors or len(self.candidate_vectors) != len(self.candidate_slots):
            raise TrainerStatFeatureError("candidate inventory differs")
        if len(set(self.candidate_slots)) != len(self.candidate_slots):
            raise TrainerStatFeatureError("candidate slots repeat")
        if any(
            len(vector) != len(self.feature_names)
            or any(not np.isfinite(value) or not -1 <= value <= 1 for value in vector)
            for vector in self.candidate_vectors
        ):
            raise TrainerStatFeatureError("candidate feature shape or range differs")


def project_trainer_move_features(
    observation: Mapping[str, object], base: BattleFeatureBatch
) -> TrainerCandidateFeatures:
    state, player, opponent, _ = _visible_stats(observation)
    physical_at = LEGACY_MOVE_NAMES.index("move.category.physical")
    special_at = LEGACY_MOVE_NAMES.index("move.category.special")
    extras = []
    for row in base.candidate_vectors:
        physical, special = row[physical_at], row[special_at]
        extras.append(
            (
                *row,
                *state,
                physical * min(player[0] / max(1, opponent[1]), 4.0) / 4.0,
                special * min(player[3] / max(1, opponent[3]), 4.0) / 4.0,
                min(player[2] / max(1, opponent[2]), 4.0) / 4.0,
            )
        )
    return TrainerCandidateFeatures(
        MOVE_SCHEMA_ID,
        MOVE_FEATURE_NAMES,
        tuple(extras),
        tuple(slot + 1 for slot in base.slot_indices),
    )


def project_trainer_control_features(
    observation: Mapping[str, object],
    *,
    catalog: BattleMechanicsCatalog,
    move_batch: BattleFeatureBatch | None = None,
) -> NDArray[np.float64]:
    state, _, _, members = _visible_stats(observation)
    party = _mapping(_mapping(observation.get("features"), "features").get("party"), "party")
    active_index = _integer(party.get("active_index"), 0, 5, "active index")
    reserves = [
        member
        for index, member in enumerate(members)
        if index != active_index and _integer(member.get("hp"), 0, 999, "member HP") > 0
    ]
    best = max(
        reserves,
        key=lambda member: (
            _integer(member.get("hp"), 0, 999, "reserve HP")
            / _integer(member.get("max_hp"), 1, 999, "reserve maximum HP"),
            _integer(member.get("level"), 1, 100, "level"),
        ),
        default=None,
    )
    reserve_stats = _stat_values(best.get("stats"), "reserve") if best is not None else (0, 0, 0, 0)
    legacy = project_control_features(observation, move_batch=move_batch, catalog=catalog)
    result = np.asarray(
        (
            *(legacy[index] for index in _STATELESS_CONTROL_INDICES),
            *state,
            *(value / 999.0 for value in reserve_stats),
        ),
        dtype=np.float64,
    )
    if result.shape != (len(CONTROL_FEATURE_NAMES_V2),):
        raise TrainerStatFeatureError("control stat feature width differs")
    return result


def project_trainer_switch_features(
    observation: Mapping[str, object], catalog: BattleMechanicsCatalog
) -> TrainerCandidateFeatures:
    state, player, _, members = _visible_stats(observation)
    base = project_switch_target_candidates(observation, catalog)
    rows = []
    for candidate in base.candidates:
        member = members[candidate.party_slot - 1]
        stats = _stat_values(member.get("stats"), "switch candidate")
        rows.append(
            (
                *candidate.features,
                *state,
                *(value / 999.0 for value in stats),
                *(
                    max(-1.0, min(1.0, (value - lead) / 999.0))
                    for value, lead in zip(stats, player, strict=True)
                ),
            )
        )
    return TrainerCandidateFeatures(
        SWITCH_SCHEMA_ID,
        SWITCH_FEATURE_NAMES_V2,
        tuple(rows),
        tuple(candidate.party_slot for candidate in base.candidates),
    )


def _visible_stats(
    observation: Mapping[str, object],
) -> tuple[tuple[float, ...], tuple[int, ...], tuple[int, ...], tuple[Mapping[str, object], ...]]:
    features = _mapping(observation.get("features"), "features")
    party = _mapping(features.get("party"), "party")
    lead = _mapping(party.get("lead"), "lead")
    battle = _mapping(features.get("battle"), "battle")
    player = _stat_values(lead.get("stats"), "player")
    public = _mapping(battle.get("opponent_public_base_stats"), "public opponent")
    bases = tuple(_integer(public.get(name), 1, 255, f"base {name}") for name in _STATS)
    level = _integer(battle.get("opponent_level"), 1, 100, "opponent level")
    estimate = tuple((2 * (base + 8) * level) // 100 + 5 for base in bases)
    stage = _integer(battle.get("player_special_stage"), -6, 6, "special stage")
    status = battle.get("opponent_status")
    statuses = (None, "sleep", "poison", "burn", "freeze", "paralysis", "other")
    if status not in statuses:
        raise TrainerStatFeatureError("opponent status differs")
    members_value = party.get("members")
    if not isinstance(members_value, list) or not members_value:
        raise TrainerStatFeatureError("party member view differs")
    members = tuple(_mapping(member, "party member") for member in members_value)
    state = (
        *(value / 999.0 for value in player),
        *(value / 255.0 for value in bases),
        *(value / 999.0 for value in estimate),
        stage / 6.0,
        *(float(status == item) for item in statuses),
    )
    if len(state) != len(_STAT_STATE_NAMES):
        raise TrainerStatFeatureError("stat feature width differs")
    return state, player, estimate, members


def _stat_values(value: object, label: str) -> tuple[int, int, int, int]:
    stats = _mapping(value, label)
    result = tuple(_integer(stats.get(name), 1, 999, f"{label} {name}") for name in _STATS)
    return result  # type: ignore[return-value]


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TrainerStatFeatureError(f"{label} is missing")
    return value


def _integer(value: object, minimum: int, maximum: int, label: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:  # noqa: E721
        raise TrainerStatFeatureError(f"{label} is outside its public range")
    return value
