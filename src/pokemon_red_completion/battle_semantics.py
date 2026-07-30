"""Game-neutral battle mechanics and transferable move-ranking features.

The feature view in this module deliberately excludes game-local identifiers,
move-slot positions, route/location state, objectives, and trajectory metadata.
Every candidate is represented with the same shared schema so a ranker can be
reused across games with compatible mechanics catalogs.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.trajectory import SemanticSnapshot

FEATURE_SCHEMA_ID = "pokemon.core.battle.move-ranker.v1"
MAX_LEVEL = 100.0
MAX_STAGE_MAGNITUDE = 6.0
MAX_MOVE_POWER = 255.0
MAX_TYPE_EFFECTIVENESS = 4.0
STAB_MULTIPLIER = 1.5
MAX_EFFECTIVE_POWER = MAX_MOVE_POWER * MAX_TYPE_EFFECTIVENESS * STAB_MULTIPLIER

POKEMON_TYPES = (
    "normal",
    "fighting",
    "flying",
    "poison",
    "ground",
    "rock",
    "bug",
    "ghost",
    "fire",
    "water",
    "grass",
    "electric",
    "psychic",
    "ice",
    "dragon",
)
MOVE_CATEGORIES = ("physical", "special", "status")
STATUS_CATEGORIES = ("none", "sleep", "poison", "burn", "freeze", "paralysis", "other")
EFFECT_FLAGS = (
    "status",
    "boost",
    "debuff",
    "recoil",
    "charge",
    "recharge",
    "drain",
    "heal",
    "multi_hit",
    "fixed_damage",
    "trapping",
    "ohko",
    "self_destruct",
    "confusion",
    "flinch",
    "counter",
)

_STATE_FEATURE_NAMES = (
    "state.player_hp_ratio",
    "state.opponent_hp_ratio",
    "state.player_level_fraction",
    "state.opponent_level_fraction",
    "state.level_difference_fraction",
    "state.player_attack_stage_fraction",
    "state.player_accuracy_stage_fraction",
    "state.opponent_defense_stage_fraction",
    "state.battle_kind.trainer",
    "state.battle_kind.wild",
    *(f"state.player_status.{status}" for status in STATUS_CATEGORIES),
    *(f"state.player_type.{type_name}" for type_name in POKEMON_TYPES),
    *(f"state.opponent_type.{type_name}" for type_name in POKEMON_TYPES),
)
_MOVE_FEATURE_NAMES = (
    "move.pp_fraction",
    "move.power_fraction",
    "move.accuracy",
    *(f"move.category.{category}" for category in MOVE_CATEGORIES),
    *(f"move.type.{type_name}" for type_name in POKEMON_TYPES),
    "move.stab",
    "move.type_effectiveness_fraction",
    "move.effective_power_fraction",
    "move.accuracy_weighted_effective_power_fraction",
    "move.priority",
    *(f"move.effect.{flag}" for flag in EFFECT_FLAGS),
)
_INTERACTION_FEATURE_NAMES = (
    "interaction.physical_x_player_attack_stage",
    "interaction.physical_x_opponent_defense_stage",
    "interaction.physical_x_player_burn",
    "interaction.move_accuracy_x_player_accuracy_stage",
    "interaction.recoil_x_player_missing_hp",
    "interaction.heal_x_player_missing_hp",
    "interaction.drain_x_player_missing_hp",
    "interaction.effective_power_x_opponent_hp",
    "interaction.effective_power_x_level_difference",
    "interaction.fixed_damage_x_player_level",
    "interaction.pp_x_effective_power",
)
FEATURE_NAMES = (
    *_STATE_FEATURE_NAMES,
    *_MOVE_FEATURE_NAMES,
    *_INTERACTION_FEATURE_NAMES,
)


class BattleFeatureError(ValueError):
    """Raised when a snapshot cannot safely produce the fixed feature view."""


@dataclass(frozen=True, slots=True)
class SpeciesMechanics:
    """Transferable mechanics for one species/form."""

    types: tuple[str, ...]

    def __post_init__(self) -> None:
        if not 1 <= len(self.types) <= 2:
            raise ValueError("species must have one or two distinct types")
        if len(set(self.types)) != len(self.types):
            raise ValueError("species types must not contain duplicates")
        if any(type_name not in POKEMON_TYPES for type_name in self.types):
            raise ValueError("species contains an unsupported type")


@dataclass(frozen=True, slots=True)
class MoveMechanics:
    """Transferable mechanics for one selectable battle move."""

    type_name: str
    category: str
    power: int
    accuracy: float
    max_pp: int
    priority: int = 0
    effect_flags: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.type_name not in POKEMON_TYPES:
            raise ValueError("move contains an unsupported type")
        if self.category not in MOVE_CATEGORIES:
            raise ValueError("move contains an unsupported category")
        if type(self.power) is not int or not 0 <= self.power <= MAX_MOVE_POWER:
            raise ValueError(f"move power must be an integer from zero through {MAX_MOVE_POWER:g}")
        if not isinstance(self.accuracy, (int, float)) or isinstance(self.accuracy, bool):
            raise TypeError("move accuracy must be numeric")
        if not math.isfinite(float(self.accuracy)) or not 0.0 <= self.accuracy <= 1.0:
            raise ValueError("move accuracy must be between zero and one")
        if type(self.max_pp) is not int or not 1 <= self.max_pp <= 63:
            raise ValueError("move max_pp must be between one and 63")
        if type(self.priority) is not int or not -1 <= self.priority <= 1:
            raise ValueError("move priority must be -1, 0, or 1")
        if not isinstance(self.effect_flags, frozenset):
            raise TypeError("move effect_flags must be a frozenset")
        if not self.effect_flags <= frozenset(EFFECT_FLAGS):
            raise ValueError("move contains an unsupported effect flag")


class BattleMechanicsCatalog(Protocol):
    """Resolve game-local references into transferable battle mechanics."""

    def resolve_species(self, species_ref: str, /) -> SpeciesMechanics: ...

    def resolve_move(self, move_ref: str, /) -> MoveMechanics: ...

    def type_effectiveness(
        self,
        attacking_type: str,
        defending_types: tuple[str, ...],
        /,
    ) -> float: ...


@dataclass(frozen=True, slots=True)
class BattleFeatureBatch:
    """One move-ranking state with slot metadata kept outside feature vectors."""

    feature_names: tuple[str, ...]
    candidate_vectors: tuple[tuple[float, ...], ...]
    legal_mask: tuple[bool, ...]
    current_pp: tuple[float, ...]
    slot_indices: tuple[int, ...]
    schema_id: str = FEATURE_SCHEMA_ID

    def __post_init__(self) -> None:
        if self.schema_id != FEATURE_SCHEMA_ID:
            raise ValueError(f"schema_id must equal {FEATURE_SCHEMA_ID}")
        if self.feature_names != FEATURE_NAMES:
            raise ValueError("feature_names must exactly match the fixed schema")
        candidate_count = len(self.candidate_vectors)
        if candidate_count == 0:
            raise ValueError("a battle feature batch must contain at least one candidate")
        if not (
            len(self.legal_mask)
            == len(self.current_pp)
            == len(self.slot_indices)
            == candidate_count
        ):
            raise ValueError("candidate metadata lengths must match")
        if len(set(self.slot_indices)) != candidate_count:
            raise ValueError("candidate slot indices must be unique")
        for vector in self.candidate_vectors:
            if len(vector) != len(self.feature_names):
                raise ValueError("candidate vector width does not match feature_names")
            if any(not math.isfinite(value) for value in vector):
                raise ValueError("candidate vectors must contain only finite values")
            if any(not -1.0 <= value <= 1.0 for value in vector):
                raise ValueError("candidate vectors must be bounded between -1 and one")
        for pp, legal in zip(self.current_pp, self.legal_mask, strict=True):
            if not math.isfinite(pp) or pp < 0:
                raise ValueError("current_pp must contain finite non-negative values")
            if legal is not (pp > 0):
                raise ValueError("legal_mask must be derived exactly from current_pp")


@dataclass(frozen=True, slots=True)
class BattleFeatureProjector:
    """Project one semantic battle snapshot into shared candidate vectors."""

    catalog: BattleMechanicsCatalog

    def project(
        self,
        snapshot: SemanticSnapshot | Mapping[str, object],
        /,
    ) -> BattleFeatureBatch:
        payload = snapshot.to_dict() if isinstance(snapshot, SemanticSnapshot) else snapshot
        root = _require_mapping(payload, name="snapshot")
        if root.get("mode") != "battle":
            raise BattleFeatureError("snapshot mode must be battle")
        features = _mapping_field(root, "features")
        menu = _mapping_field(features, "menu")
        if menu.get("kind") != "battle_main":
            raise BattleFeatureError("snapshot must expose the main battle menu")

        party = _mapping_field(features, "party")
        lead = _mapping_field(party, "lead")
        battle = _mapping_field(features, "battle")
        if battle.get("active") is not True:
            raise BattleFeatureError("snapshot must contain an active battle")

        player_species = self.catalog.resolve_species(
            _string_field(lead, "species_ref"),
        )
        opponent_species = self.catalog.resolve_species(
            _string_field(battle, "opponent_species_ref"),
        )
        battle_kind = _choice_field(battle, "kind", choices=("trainer", "wild"))
        player_status = lead.get("status")
        if player_status is None:
            player_status = "none"
        if player_status not in STATUS_CATEGORIES:
            raise BattleFeatureError("party lead status is unsupported")

        player_hp_ratio = _ratio_field(lead, "hp_ratio")
        opponent_hp_ratio = _ratio_field(battle, "opponent_hp_ratio")
        player_level = _integer_field(lead, "level", minimum=1, maximum=100)
        opponent_level = _integer_field(battle, "opponent_level", minimum=1, maximum=100)
        player_level_fraction = player_level / MAX_LEVEL
        level_difference_fraction = (player_level - opponent_level) / MAX_LEVEL
        player_attack_stage_fraction = (
            _integer_field(battle, "player_attack_stage", minimum=-6, maximum=6)
            / MAX_STAGE_MAGNITUDE
        )
        player_accuracy_stage_fraction = (
            _integer_field(battle, "player_accuracy_stage", minimum=-6, maximum=6)
            / MAX_STAGE_MAGNITUDE
        )
        opponent_defense_stage_fraction = (
            _integer_field(battle, "opponent_defense_stage", minimum=-6, maximum=6)
            / MAX_STAGE_MAGNITUDE
        )
        state_values = (
            player_hp_ratio,
            opponent_hp_ratio,
            player_level_fraction,
            opponent_level / MAX_LEVEL,
            level_difference_fraction,
            player_attack_stage_fraction,
            player_accuracy_stage_fraction,
            opponent_defense_stage_fraction,
            float(battle_kind == "trainer"),
            float(battle_kind == "wild"),
            *(_one_hot(player_status, STATUS_CATEGORIES)),
            *(_multi_hot(player_species.types, POKEMON_TYPES)),
            *(_multi_hot(opponent_species.types, POKEMON_TYPES)),
        )
        if len(state_values) != len(_STATE_FEATURE_NAMES):  # pragma: no cover
            raise AssertionError("state feature schema width drifted")

        raw_moves = _sequence_field(lead, "moves")
        candidates: list[tuple[int, float, tuple[float, ...]]] = []
        seen_slots: set[int] = set()
        for raw_move in raw_moves:
            move_view = _require_mapping(raw_move, name="party.lead.moves[]")
            slot_index = _integer_field(move_view, "slot_index", minimum=0, maximum=3)
            if slot_index in seen_slots:
                raise BattleFeatureError("move slot indices must be unique")
            seen_slots.add(slot_index)
            current_pp = float(_integer_field(move_view, "pp", minimum=0, maximum=63))
            move = self.catalog.resolve_move(_string_field(move_view, "move_ref"))
            if current_pp > 0 and "counter" in move.effect_flags:
                raise BattleFeatureError("Counter requires prior-turn received-damage semantics")
            stab = float(move.type_name in player_species.types)
            effectiveness = self.catalog.type_effectiveness(
                move.type_name,
                opponent_species.types,
            )
            if not 0.0 <= effectiveness <= MAX_TYPE_EFFECTIVENESS:
                raise BattleFeatureError("type effectiveness exceeds the fixed feature scale")
            stab_multiplier = STAB_MULTIPLIER if stab else 1.0
            effective_power = float(move.power) * stab_multiplier * effectiveness
            pp_fraction = min(current_pp / move.max_pp, 1.0)
            power_fraction = float(move.power) / MAX_MOVE_POWER
            effective_power_fraction = effective_power / MAX_EFFECTIVE_POWER
            physical = float(move.category == "physical")
            move_values = (
                pp_fraction,
                power_fraction,
                float(move.accuracy),
                *(_one_hot(move.category, MOVE_CATEGORIES)),
                *(_one_hot(move.type_name, POKEMON_TYPES)),
                stab,
                effectiveness / MAX_TYPE_EFFECTIVENESS,
                effective_power_fraction,
                (effective_power * move.accuracy) / MAX_EFFECTIVE_POWER,
                float(move.priority),
                *(float(flag in move.effect_flags) for flag in EFFECT_FLAGS),
            )
            if len(move_values) != len(_MOVE_FEATURE_NAMES):  # pragma: no cover
                raise AssertionError("move feature schema width drifted")
            interaction_values = (
                physical * player_attack_stage_fraction,
                physical * opponent_defense_stage_fraction,
                physical * float(player_status == "burn"),
                move.accuracy * player_accuracy_stage_fraction,
                float("recoil" in move.effect_flags) * (1.0 - player_hp_ratio),
                float("heal" in move.effect_flags) * (1.0 - player_hp_ratio),
                float("drain" in move.effect_flags) * (1.0 - player_hp_ratio),
                effective_power_fraction * opponent_hp_ratio,
                effective_power_fraction * level_difference_fraction,
                float("fixed_damage" in move.effect_flags) * player_level_fraction,
                pp_fraction * effective_power_fraction,
            )
            if len(interaction_values) != len(_INTERACTION_FEATURE_NAMES):  # pragma: no cover
                raise AssertionError("interaction feature schema width drifted")
            candidates.append(
                (
                    slot_index,
                    current_pp,
                    (*state_values, *move_values, *interaction_values),
                )
            )

        candidates.sort(key=lambda candidate: candidate[0])
        return BattleFeatureBatch(
            feature_names=FEATURE_NAMES,
            candidate_vectors=tuple(candidate[2] for candidate in candidates),
            legal_mask=tuple(candidate[1] > 0 for candidate in candidates),
            current_pp=tuple(candidate[1] for candidate in candidates),
            slot_indices=tuple(candidate[0] for candidate in candidates),
        )


def _require_mapping(value: object, *, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise BattleFeatureError(f"{name} must be a mapping")
    return value


def _mapping_field(mapping: Mapping[str, object], field: str) -> Mapping[str, object]:
    if field not in mapping:
        raise BattleFeatureError(f"missing required field: {field}")
    return _require_mapping(mapping[field], name=field)


def _sequence_field(mapping: Mapping[str, object], field: str) -> Sequence[object]:
    value = mapping.get(field)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise BattleFeatureError(f"{field} must be a sequence")
    if not value:
        raise BattleFeatureError(f"{field} must not be empty")
    return value


def _string_field(mapping: Mapping[str, object], field: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value:
        raise BattleFeatureError(f"{field} must be a non-empty string")
    return value


def _integer_field(
    mapping: Mapping[str, object],
    field: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = mapping.get(field)
    if type(value) is not int or not minimum <= value <= maximum:  # noqa: E721
        raise BattleFeatureError(f"{field} must be an integer from {minimum} through {maximum}")
    return value


def _ratio_field(mapping: Mapping[str, object], field: str) -> float:
    value = mapping.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise BattleFeatureError(f"{field} must be numeric")
    ratio = float(value)
    if not math.isfinite(ratio) or not 0.0 <= ratio <= 1.0:
        raise BattleFeatureError(f"{field} must be between zero and one")
    return ratio


def _choice_field(
    mapping: Mapping[str, object],
    field: str,
    *,
    choices: tuple[str, ...],
) -> str:
    value = mapping.get(field)
    if value not in choices:
        raise BattleFeatureError(f"{field} must be one of {choices}")
    assert isinstance(value, str)
    return value


def _one_hot(value: str, choices: tuple[str, ...]) -> tuple[float, ...]:
    if value not in choices:
        raise BattleFeatureError(f"unsupported categorical value: {value}")
    return tuple(float(value == choice) for choice in choices)


def _multi_hot(values: tuple[str, ...], choices: tuple[str, ...]) -> tuple[float, ...]:
    if not values or any(value not in choices for value in values):
        raise BattleFeatureError("unsupported multi-valued categorical feature")
    return tuple(float(choice in values) for choice in choices)
