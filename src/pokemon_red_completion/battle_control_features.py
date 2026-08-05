"""Transferable feature view for high-level Pokémon battle decisions."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.battle_actions import BattleAction, BattleActionKind
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES as MOVE_FEATURE_NAMES,
)
from pokemon_red_completion.battle_semantics import BattleFeatureBatch

CONTROL_FEATURE_SCHEMA_ID = "pokemon.core.battle.control.features.v2"
CONTROL_CLASS_REFS = (
    "pokemon.core:battle:select_move",
    "pokemon.core:battle:recovery",
    "pokemon.core:battle:boost:accuracy",
    "pokemon.core:battle:boost:attack",
    "pokemon.core:battle:boost:special",
    "pokemon.core:battle:switch",
    "pokemon.core:battle:capture",
    "pokemon.core:battle:flee",
)
CONTROL_FEATURE_NAMES = (
    "battle.is_trainer",
    "battle.is_wild",
    "player.level",
    "player.hp_ratio",
    "player.has_status",
    "player.attack_stage",
    "player.special_stage",
    "player.accuracy_stage",
    "player.move_disabled",
    "opponent.level",
    "opponent.hp_ratio",
    "opponent.defense_stage",
    "opponent.is_trapping",
    "party.count",
    "party.active_index",
    "party.living_count",
    "party.living_reserve_count",
    "party.fainted_count",
    "party.status_count",
    "party.mean_hp_ratio",
    "party.minimum_living_hp_ratio",
    "party.mean_level",
    "party.minimum_level",
    "party.maximum_level",
    "resources.capture_items",
    "resources.healing_items",
    "resources.status_recovery_items",
    "resources.revive_items",
    "resources.accuracy_boosts",
    "resources.attack_boosts",
    "resources.special_boosts",
    "progress.badge_count",
    "history.battle_turn",
    "history.opponent_index",
    "history.opponent_turn",
    *(f"history.previous.{value.rsplit(':', 1)[-1]}" for value in CONTROL_CLASS_REFS),
    *(f"history.count.{value.rsplit(':', 1)[-1]}" for value in CONTROL_CLASS_REFS),
    *(f"matchup.player_type.{name}" for name in (
        "normal", "fighting", "flying", "poison", "ground", "rock", "bug", "ghost",
        "fire", "water", "grass", "electric", "psychic", "ice", "dragon",
    )),
    *(f"matchup.opponent_type.{name}" for name in (
        "normal", "fighting", "flying", "poison", "ground", "rock", "bug", "ghost",
        "fire", "water", "grass", "electric", "psychic", "ice", "dragon",
    )),
    "moves.best.category.physical",
    "moves.best.category.special",
    "moves.best.category.status",
    "moves.best.accuracy",
    "moves.best.type_effectiveness",
    "moves.best.effective_power",
    "moves.best.accuracy_weighted_effective_power",
    "moves.usable_count",
    "moves.mean_pp_fraction",
)


@dataclass(frozen=True, slots=True)
class BattleControlHistory:
    """Game-neutral action history available before one battle decision."""

    battle_turn: int = 0
    opponent_index: int = 0
    opponent_turn: int = 0
    previous_class_index: int | None = None
    action_counts: tuple[int, ...] = (0,) * len(CONTROL_CLASS_REFS)

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 0  # noqa: E721
            for value in (self.battle_turn, self.opponent_index, self.opponent_turn)
        ):
            raise BattleControlFeatureError("control history indices must be non-negative")
        if self.previous_class_index is not None and (
            type(self.previous_class_index) is not int  # noqa: E721
            or not 0 <= self.previous_class_index < len(CONTROL_CLASS_REFS)
        ):
            raise BattleControlFeatureError("previous control action is invalid")
        if len(self.action_counts) != len(CONTROL_CLASS_REFS) or any(
            type(value) is not int or value < 0 for value in self.action_counts  # noqa: E721
        ):
            raise BattleControlFeatureError("control action counts are invalid")

    def feature_values(self) -> tuple[float, ...]:
        previous = tuple(
            float(self.previous_class_index == index)
            for index in range(len(CONTROL_CLASS_REFS))
        )
        ceilings = (64, 16, 6, 6, 6, 6, 16, 16)
        counts = tuple(
            min(value, ceiling) / ceiling
            for value, ceiling in zip(self.action_counts, ceilings, strict=True)
        )
        return (
            min(self.battle_turn, 64) / 64.0,
            min(self.opponent_index, 5) / 5.0,
            min(self.opponent_turn, 32) / 32.0,
            *previous,
            *counts,
        )


@dataclass(slots=True)
class BattleControlHistoryTracker:
    """Derive causal temporal features without exposing game or objective identity."""

    battle_plan_id: str | None = None
    opponent_key: tuple[object, object] | None = None
    last_opponent_hp_ratio: float | None = None
    history: BattleControlHistory = BattleControlHistory()

    def before(
        self,
        battle_plan_id: str,
        observation: Mapping[str, object],
    ) -> BattleControlHistory:
        battle = _mapping(
            _mapping(observation.get("features"), "features").get("battle"),
            "battle",
        )
        opponent_key = (battle.get("opponent_species_ref"), battle.get("opponent_level"))
        hp_ratio = _ratio(battle.get("opponent_hp_ratio"), "opponent hp ratio")
        if battle_plan_id != self.battle_plan_id:
            self.battle_plan_id = battle_plan_id
            self.opponent_key = opponent_key
            self.last_opponent_hp_ratio = None
            self.history = BattleControlHistory()
        elif opponent_key != self.opponent_key or (
            self.last_opponent_hp_ratio is not None
            and self.last_opponent_hp_ratio <= 0.25
            and hp_ratio >= 0.9
        ):
            self.opponent_key = opponent_key
            self.history = BattleControlHistory(
                battle_turn=self.history.battle_turn,
                opponent_index=self.history.opponent_index + 1,
                action_counts=self.history.action_counts,
                previous_class_index=self.history.previous_class_index,
            )
        return self.history

    def advance(
        self,
        action: BattleAction,
        observation: Mapping[str, object],
    ) -> None:
        class_index = CONTROL_CLASS_REFS.index(control_class_ref(action))
        counts = list(self.history.action_counts)
        counts[class_index] += 1
        battle = _mapping(
            _mapping(observation.get("features"), "features").get("battle"),
            "battle",
        )
        self.last_opponent_hp_ratio = _ratio(
            battle.get("opponent_hp_ratio"),
            "opponent hp ratio",
        )
        self.history = BattleControlHistory(
            battle_turn=self.history.battle_turn + 1,
            opponent_index=self.history.opponent_index,
            opponent_turn=self.history.opponent_turn + 1,
            previous_class_index=class_index,
            action_counts=tuple(counts),
        )


class BattleControlFeatureError(ValueError):
    """Raised when a semantic observation cannot support battle control."""


@dataclass(frozen=True, slots=True)
class BattleControlExample:
    features: NDArray[np.float64]
    class_index: int
    battle_plan_id: str
    decision_index: int

    def __post_init__(self) -> None:
        if self.features.shape != (len(CONTROL_FEATURE_NAMES),):
            raise BattleControlFeatureError("control feature vector has the wrong shape")
        if not np.all(np.isfinite(self.features)):
            raise BattleControlFeatureError("control feature vector must be finite")
        if type(self.class_index) is not int or not 0 <= self.class_index < len(  # noqa: E721
            CONTROL_CLASS_REFS
        ):
            raise BattleControlFeatureError("control class index is invalid")
        if not self.battle_plan_id:
            raise BattleControlFeatureError("battle plan ID is required")
        if type(self.decision_index) is not int or self.decision_index < 1:  # noqa: E721
            raise BattleControlFeatureError("decision index is invalid")


def control_class_ref(action: BattleAction) -> str:
    """Collapse cartridge-specific targets into a transferable action class."""

    if action.kind is BattleActionKind.SELECT_MOVE:
        return CONTROL_CLASS_REFS[0]
    if action.kind is BattleActionKind.USE_RECOVERY:
        return CONTROL_CLASS_REFS[1]
    if action.kind is BattleActionKind.USE_BOOST:
        assert action.boost_stat is not None
        return f"pokemon.core:battle:boost:{action.boost_stat.value}"
    if action.kind is BattleActionKind.SWITCH:
        return CONTROL_CLASS_REFS[5]
    if action.kind is BattleActionKind.ATTEMPT_CAPTURE:
        return CONTROL_CLASS_REFS[6]
    return CONTROL_CLASS_REFS[7]


def project_control_features(
    observation: Mapping[str, object],
    *,
    move_batch: BattleFeatureBatch | None = None,
    history: BattleControlHistory | None = None,
) -> NDArray[np.float64]:
    """Project one privacy-safe semantic snapshot into normalized transferable state."""

    features = _mapping(observation.get("features"), "features")
    battle = _mapping(features.get("battle"), "battle")
    party = _mapping(features.get("party"), "party")
    lead = _mapping(party.get("lead"), "party.lead")
    resources = _mapping(features.get("resources"), "resources")
    progress = _mapping(features.get("progress"), "progress")
    members_value = party.get("members")
    if not isinstance(members_value, Sequence) or isinstance(members_value, (str, bytes)):
        raise BattleControlFeatureError("party.members must be a sequence")
    members = tuple(_mapping(member, "party member") for member in members_value)
    hp_ratios = tuple(_ratio(member.get("hp_ratio"), "party member hp ratio") for member in members)
    living = tuple(value for value in hp_ratios if value > 0.0)
    levels = tuple(
        _bounded(member.get("level"), 1, 100, "party member level")
        for member in members
    )
    statuses = sum(member.get("status") is not None for member in members)
    active_index = _active_index(party, lead, members)
    kind = battle.get("kind")
    if kind not in {"trainer", "wild"}:
        raise BattleControlFeatureError("battle kind must be trainer or wild")
    temporal = history if history is not None else BattleControlHistory()
    values = (
        float(kind == "trainer"),
        float(kind == "wild"),
        _bounded(lead.get("level"), 1, 100, "player level") / 100.0,
        _ratio(lead.get("hp_ratio"), "player hp ratio"),
        float(lead.get("status") is not None),
        _stage(battle.get("player_attack_stage"), "player attack stage"),
        _stage(battle.get("player_special_stage"), "player special stage"),
        _stage(battle.get("player_accuracy_stage"), "player accuracy stage"),
        float(battle.get("player_disabled_move_slot") is not None),
        _bounded(battle.get("opponent_level"), 1, 100, "opponent level") / 100.0,
        _ratio(battle.get("opponent_hp_ratio"), "opponent hp ratio"),
        _stage(battle.get("opponent_defense_stage"), "opponent defense stage"),
        float(_boolean(battle.get("opponent_using_trapping_move"), "trapping state")),
        _bounded(party.get("count"), 1, 6, "party count") / 6.0,
        active_index / 5.0,
        len(living) / 6.0,
        max(0, len(living) - 1) / 5.0,
        (len(members) - len(living)) / 6.0,
        statuses / 6.0,
        math.fsum(hp_ratios) / len(hp_ratios),
        min(living) if living else 0.0,
        math.fsum(levels) / (100.0 * len(levels)),
        min(levels) / 100.0,
        max(levels) / 100.0,
        _resource(resources, "capture_item_count", 50, default=0),
        _resource(resources, "healing_item_count", 20),
        _resource(resources, "status_recovery_item_count", 20),
        _resource(resources, "revive_item_count", 20),
        _resource(resources, "accuracy_boost_count", 20),
        _resource(resources, "attack_boost_count", 20),
        _resource(resources, "special_boost_count", 20),
        _bounded(progress.get("badge_count"), 0, 8, "badge count") / 8.0,
        *temporal.feature_values(),
        *_move_control_features(move_batch),
    )
    result = np.asarray(values, dtype=np.float64)
    if result.shape != (len(CONTROL_FEATURE_NAMES),) or not np.all(np.isfinite(result)):
        raise BattleControlFeatureError("projected control features are invalid")
    return result


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise BattleControlFeatureError(f"{label} must be a mapping")
    return value


def _bounded(value: object, minimum: int, maximum: int, label: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:  # noqa: E721
        raise BattleControlFeatureError(f"{label} is outside its supported range")
    return value


def _ratio(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise BattleControlFeatureError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise BattleControlFeatureError(f"{label} must be between zero and one")
    return result


def _stage(value: object, label: str) -> float:
    if type(value) is not int or not -6 <= value <= 6:  # noqa: E721
        raise BattleControlFeatureError(f"{label} is outside its supported range")
    return value / 6.0


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise BattleControlFeatureError(f"{label} must be a boolean")
    return value


def _resource(
    resources: Mapping[str, object],
    name: str,
    ceiling: int,
    *,
    default: int | None = None,
) -> float:
    value = resources.get(name, default)
    if type(value) is not int or value < 0:  # noqa: E721
        raise BattleControlFeatureError(f"{name} must be a non-negative integer")
    return min(value, ceiling) / ceiling


def _active_index(
    party: Mapping[str, object],
    lead: Mapping[str, object],
    members: Sequence[Mapping[str, object]],
) -> int:
    explicit = party.get("active_index")
    if explicit is not None:
        return _bounded(explicit, 0, 5, "active party index")
    identity_fields = ("species_ref", "level", "hp", "max_hp", "status")
    matches = tuple(
        index
        for index, member in enumerate(members)
        if all(member.get(name) == lead.get(name) for name in identity_fields)
    )
    if len(matches) != 1:
        raise BattleControlFeatureError("active party index cannot be inferred uniquely")
    return matches[0]


def _move_control_features(batch: BattleFeatureBatch | None) -> tuple[float, ...]:
    width = 30 + 3 + 6
    if batch is None:
        return (0.0,) * width
    vectors = np.asarray(batch.candidate_vectors, dtype=np.float64)
    usable = np.asarray(batch.legal_mask, dtype=np.bool_) & (
        np.asarray(batch.current_pp, dtype=np.float64) > 0
    )
    if not np.any(usable):
        raise BattleControlFeatureError("battle control has no usable move")

    def column(name: str) -> NDArray[np.float64]:
        return vectors[:, MOVE_FEATURE_NAMES.index(name)]

    first = vectors[np.flatnonzero(usable)[0]]
    player_types = tuple(
        float(first[MOVE_FEATURE_NAMES.index(f"state.player_type.{name}")])
        for name in (
            "normal", "fighting", "flying", "poison", "ground", "rock", "bug", "ghost",
            "fire", "water", "grass", "electric", "psychic", "ice", "dragon",
        )
    )
    opponent_types = tuple(
        float(first[MOVE_FEATURE_NAMES.index(f"state.opponent_type.{name}")])
        for name in (
            "normal", "fighting", "flying", "poison", "ground", "rock", "bug", "ghost",
            "fire", "water", "grass", "electric", "psychic", "ice", "dragon",
        )
    )
    weighted = column("move.accuracy_weighted_effective_power_fraction").copy()
    weighted[~usable] = -1.0
    best = int(np.argmax(weighted))
    return (
        *player_types,
        *opponent_types,
        float(vectors[best, MOVE_FEATURE_NAMES.index("move.category.physical")]),
        float(vectors[best, MOVE_FEATURE_NAMES.index("move.category.special")]),
        float(vectors[best, MOVE_FEATURE_NAMES.index("move.category.status")]),
        float(vectors[best, MOVE_FEATURE_NAMES.index("move.accuracy")]),
        float(vectors[best, MOVE_FEATURE_NAMES.index("move.type_effectiveness_fraction")]),
        float(vectors[best, MOVE_FEATURE_NAMES.index("move.effective_power_fraction")]),
        float(weighted[best]),
        float(np.sum(usable)) / 4.0,
        float(np.mean(column("move.pp_fraction")[usable])),
    )
