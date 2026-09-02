"""Fast, repeatable mechanics curriculum for battle-policy initialization.

This is deliberately a development tool rather than cartridge evidence. It samples
semantic battle states, projects them through the same title-neutral feature schema
used at runtime, and teaches a model to reproduce a disclosed mechanics oracle.
Authentic emulator outcomes remain the validation and authority boundary.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import numpy as np

from pokemon_red_completion.battle_model import BattleChoiceExample
from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    BattleFeatureBatch,
    BattleFeatureProjector,
    MoveMechanics,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_battle_catalog import (
    PokemonRedBattleCatalog,
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

REPEATABLE_BATTLE_CURRICULUM_SCHEMA = "pokemon.core.battle.repeatable-curriculum.v1"
REPEATABLE_BATTLE_REPORT_SCHEMA = "pokemon.core.battle.repeatable-fit-report.v1"
_MAXIMUM_EXAMPLES = 100_000


class RepeatableBattleCurriculumError(ValueError):
    """Raised when the repeatable development curriculum is invalid."""


@dataclass(frozen=True, slots=True)
class RepeatableBattleExample:
    """One synthetic semantic menu and the disclosed mechanics-oracle choice."""

    example_id: str
    partition: ScenarioPartition
    semantic_state_sha256: str
    features: BattleFeatureBatch
    oracle_scores: tuple[float, ...]
    chosen_index: int

    def __post_init__(self) -> None:
        if not self.example_id or "/" in self.example_id or "\\" in self.example_id:
            raise RepeatableBattleCurriculumError("repeatable example identity is invalid")
        if self.partition is ScenarioPartition.TEST:
            raise RepeatableBattleCurriculumError("synthetic examples cannot enter test")
        if len(self.semantic_state_sha256) != 64:
            raise RepeatableBattleCurriculumError("semantic state digest is invalid")
        if len(self.oracle_scores) != len(self.features.candidate_vectors):
            raise RepeatableBattleCurriculumError("oracle scores differ from candidates")
        if any(not math.isfinite(value) for value in self.oracle_scores):
            raise RepeatableBattleCurriculumError("oracle scores must be finite")
        if not 0 <= self.chosen_index < len(self.oracle_scores):
            raise RepeatableBattleCurriculumError("oracle choice is invalid")
        if not self.features.legal_mask[self.chosen_index]:
            raise RepeatableBattleCurriculumError("oracle choice must be legal")

    def choice_example(self) -> BattleChoiceExample:
        return BattleChoiceExample(
            candidate_features=self.features.candidate_vectors,
            legal_mask=self.features.legal_mask,
            current_pp=self.features.current_pp,
            chosen_index=self.chosen_index,
        )


@dataclass(frozen=True, slots=True)
class RepeatableBattleCurriculum:
    """Deterministic train/development split produced without an emulator."""

    seed: int
    training: tuple[RepeatableBattleExample, ...]
    development: tuple[RepeatableBattleExample, ...]

    def __post_init__(self) -> None:
        if type(self.seed) is not int or self.seed < 0:  # noqa: E721
            raise RepeatableBattleCurriculumError("curriculum seed is invalid")
        if not self.training or not self.development:
            raise RepeatableBattleCurriculumError("both curriculum partitions are required")
        if any(item.partition is not ScenarioPartition.TRAIN for item in self.training):
            raise RepeatableBattleCurriculumError("training partition differs")
        if any(
            item.partition is not ScenarioPartition.DEVELOPMENT
            for item in self.development
        ):
            raise RepeatableBattleCurriculumError("development partition differs")
        identities = tuple(item.example_id for item in (*self.training, *self.development))
        states = tuple(
            item.semantic_state_sha256 for item in (*self.training, *self.development)
        )
        if len(identities) != len(set(identities)) or len(states) != len(set(states)):
            raise RepeatableBattleCurriculumError("curriculum examples must be distinct")

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": REPEATABLE_BATTLE_CURRICULUM_SCHEMA,
            "seed": self.seed,
            "training_examples": len(self.training),
            "development_examples": len(self.development),
            "candidate_count_minimum": min(
                len(item.features.candidate_vectors)
                for item in (*self.training, *self.development)
            ),
            "candidate_count_maximum": max(
                len(item.features.candidate_vectors)
                for item in (*self.training, *self.development)
            ),
            "feature_schema": self.training[0].features.schema_id,
            "source": "disclosed_simulated_mechanics_oracle",
            "emulator_frames": 0,
            "controller_actions": 0,
            "authentic_outcomes": 0,
            "authority_promoted": False,
        }


@dataclass(frozen=True, slots=True)
class RepeatableBattleFitReport:
    curriculum_sha256: str
    model_sha256: str
    training_examples: int
    development_examples: int
    training_accuracy: float
    development_accuracy: float
    fixed_heuristic_development_accuracy: float
    zero_weight_development_accuracy: float
    seed: int
    epochs: int

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": REPEATABLE_BATTLE_REPORT_SCHEMA,
            "curriculum_sha256": self.curriculum_sha256,
            "model_sha256": self.model_sha256,
            "training_examples": self.training_examples,
            "development_examples": self.development_examples,
            "training_accuracy": self.training_accuracy,
            "development_accuracy": self.development_accuracy,
            "fixed_heuristic_development_accuracy": (
                self.fixed_heuristic_development_accuracy
            ),
            "zero_weight_development_accuracy": self.zero_weight_development_accuracy,
            "seed": self.seed,
            "epochs": self.epochs,
            "synthetic_pretraining": True,
            "authentic_outcomes": 0,
            "gameplay_authority": False,
            "transfer_claim": False,
        }


def build_repeatable_red_battle_curriculum(
    *,
    training_examples: int,
    development_examples: int,
    seed: int,
) -> RepeatableBattleCurriculum:
    """Build deterministic Red-backed semantic examples without opening a ROM."""

    _validate_count(training_examples, "training")
    _validate_count(development_examples, "development")
    if type(seed) is not int or not 0 <= seed <= np.iinfo(np.uint64).max:  # noqa: E721
        raise RepeatableBattleCurriculumError("curriculum seed is invalid")
    rng = np.random.default_rng(seed)
    catalog = PokemonRedBattleCatalog()
    move_ids = tuple(
        identifier
        for identifier in catalog.move_ids
        if _move_is_supported(catalog.resolve_move(pokemon_red_move_ref(identifier)))
    )
    if len(move_ids) < 4:  # pragma: no cover - pinned-catalog invariant
        raise RepeatableBattleCurriculumError("mechanics catalog lacks candidate moves")

    def partition(
        kind: ScenarioPartition,
        count: int,
        offset: int,
    ) -> tuple[RepeatableBattleExample, ...]:
        return tuple(
            _sample_example(
                catalog=catalog,
                move_ids=move_ids,
                rng=rng,
                partition=kind,
                ordinal=offset + ordinal,
            )
            for ordinal in range(count)
        )

    return RepeatableBattleCurriculum(
        seed=seed,
        training=partition(ScenarioPartition.TRAIN, training_examples, 0),
        development=partition(
            ScenarioPartition.DEVELOPMENT,
            development_examples,
            training_examples,
        ),
    )


def fit_repeatable_battle_curriculum(
    curriculum: RepeatableBattleCurriculum,
    *,
    seed: int,
    hidden_units: int = 32,
    epochs: int = 200,
    learning_rate: float = 0.01,
    l2: float = 1e-4,
) -> tuple[MaskedMLPMoveRanker, RepeatableBattleFitReport]:
    """Fit a full MLP initialization and report synthetic held-out performance."""

    if not isinstance(curriculum, RepeatableBattleCurriculum):
        raise TypeError("curriculum must be a RepeatableBattleCurriculum")
    model = MaskedMLPMoveRanker.fit(
        feature_names=FEATURE_NAMES,
        examples=tuple(item.choice_example() for item in curriculum.training),
        seed=seed,
        hidden_units=hidden_units,
        epochs=epochs,
        learning_rate=learning_rate,
        l2=l2,
    )
    zero = MaskedMLPMoveRanker(
        feature_names=FEATURE_NAMES,
        input_weights=np.zeros((hidden_units, len(FEATURE_NAMES))),
        hidden_bias=np.zeros(hidden_units),
        output_weights=np.zeros(hidden_units),
        output_bias=0.0,
        training_seed=seed,
    )
    report = RepeatableBattleFitReport(
        curriculum_sha256=curriculum.sha256,
        model_sha256=hashlib.sha256(model.to_json().encode("ascii")).hexdigest(),
        training_examples=len(curriculum.training),
        development_examples=len(curriculum.development),
        training_accuracy=_accuracy(model, curriculum.training),
        development_accuracy=_accuracy(model, curriculum.development),
        fixed_heuristic_development_accuracy=_fixed_heuristic_accuracy(
            curriculum.development
        ),
        zero_weight_development_accuracy=_accuracy(zero, curriculum.development),
        seed=seed,
        epochs=epochs,
    )
    return model, report


def _sample_example(
    *,
    catalog: PokemonRedBattleCatalog,
    move_ids: tuple[int, ...],
    rng: np.random.Generator,
    partition: ScenarioPartition,
    ordinal: int,
) -> RepeatableBattleExample:
    player_species_id = int(rng.choice(catalog.species_ids))
    opponent_species_id = int(rng.choice(catalog.species_ids))
    player_level = int(rng.integers(5, 81))
    opponent_level = int(rng.integers(max(2, player_level - 18), min(100, player_level + 18) + 1))
    player_hp_ratio = float(rng.uniform(0.12, 1.0))
    opponent_hp_ratio = float(rng.uniform(0.12, 1.0))
    player_attack_stage = int(rng.integers(-3, 4))
    player_accuracy_stage = int(rng.integers(-3, 4))
    opponent_defense_stage = int(rng.integers(-3, 4))
    player_status = str(rng.choice(("none", "none", "none", "burn", "paralysis")))
    candidate_count = int(rng.integers(3, 5))
    selected_move_ids = tuple(
        int(value) for value in rng.choice(move_ids, size=candidate_count, replace=False)
    )
    moves = []
    for slot_index, move_id in enumerate(selected_move_ids):
        mechanics = catalog.resolve_move(pokemon_red_move_ref(move_id))
        pp = int(rng.integers(1, mechanics.max_pp + 1))
        moves.append(
            {
                "slot_index": slot_index,
                "move_ref": pokemon_red_move_ref(move_id),
                "pp": pp,
            }
        )
    snapshot = {
        "mode": "battle",
        "features": {
            "menu": {"kind": "battle_main"},
            "party": {
                "lead": {
                    "species_ref": pokemon_red_species_ref(player_species_id),
                    "level": player_level,
                    "hp_ratio": player_hp_ratio,
                    "status": player_status,
                    "moves": moves,
                }
            },
            "battle": {
                "active": True,
                "kind": str(rng.choice(("wild", "trainer"))),
                "opponent_species_ref": pokemon_red_species_ref(opponent_species_id),
                "opponent_level": opponent_level,
                "opponent_hp_ratio": opponent_hp_ratio,
                "player_attack_stage": player_attack_stage,
                "player_accuracy_stage": player_accuracy_stage,
                "opponent_defense_stage": opponent_defense_stage,
                "player_disabled_move_slot": None,
            },
        },
    }
    features = BattleFeatureProjector(catalog).project(snapshot)
    player_types = catalog.resolve_species(
        pokemon_red_species_ref(player_species_id)
    ).types
    opponent_types = catalog.resolve_species(
        pokemon_red_species_ref(opponent_species_id)
    ).types
    scores = tuple(
        _oracle_score(
            catalog.resolve_move(pokemon_red_move_ref(move_id)),
            catalog=catalog,
            player_types=player_types,
            opponent_types=opponent_types,
            player_level=player_level,
            opponent_level=opponent_level,
            player_hp_ratio=player_hp_ratio,
            opponent_hp_ratio=opponent_hp_ratio,
            player_status=player_status,
            player_attack_stage=player_attack_stage,
            player_accuracy_stage=player_accuracy_stage,
            opponent_defense_stage=opponent_defense_stage,
            pp_fraction=features.current_pp[index]
            / catalog.resolve_move(pokemon_red_move_ref(move_id)).max_pp,
        )
        for index, move_id in enumerate(selected_move_ids)
    )
    chosen = int(np.argmax(np.asarray(scores)))
    state_sha = canonical_sha256(snapshot)
    partition_name = partition.value
    return RepeatableBattleExample(
        example_id=f"sim-red-{partition_name}-{ordinal:06d}",
        partition=partition,
        semantic_state_sha256=state_sha,
        features=features,
        oracle_scores=scores,
        chosen_index=chosen,
    )


def _oracle_score(
    move: MoveMechanics,
    *,
    catalog: PokemonRedBattleCatalog,
    player_types: tuple[str, ...],
    opponent_types: tuple[str, ...],
    player_level: int,
    opponent_level: int,
    player_hp_ratio: float,
    opponent_hp_ratio: float,
    player_status: str,
    player_attack_stage: int,
    player_accuracy_stage: int,
    opponent_defense_stage: int,
    pp_fraction: float,
) -> float:
    effectiveness = catalog.type_effectiveness(move.type_name, opponent_types)
    stab = 1.5 if move.type_name in player_types else 1.0
    level_ratio = (player_level + 10.0) / (opponent_level + 10.0)
    stage_ratio = _stage_multiplier(player_attack_stage) / _stage_multiplier(
        opponent_defense_stage
    )
    if move.category != "physical":
        stage_ratio = 1.0
    burn = 0.5 if move.category == "physical" and player_status == "burn" else 1.0
    accuracy_stage = _stage_multiplier(player_accuracy_stage)
    accuracy = min(1.0, move.accuracy * accuracy_stage)
    power = float(move.power)
    if "fixed_damage" in move.effect_flags:
        power = max(power, float(player_level))
    score = power * effectiveness * stab * level_ratio * stage_ratio * burn * accuracy
    score /= max(opponent_hp_ratio, 0.1)
    if "ohko" in move.effect_flags:
        score = 450.0 * accuracy if player_level >= opponent_level else 0.0
    if "charge" in move.effect_flags:
        score *= 0.56
    if "recharge" in move.effect_flags:
        score *= 0.68
    if "recoil" in move.effect_flags:
        score -= 40.0 * (1.0 - player_hp_ratio)
    if "self_destruct" in move.effect_flags:
        score -= 1_000.0
    if "drain" in move.effect_flags:
        score += 24.0 * (1.0 - player_hp_ratio)
    if "multi_hit" in move.effect_flags or "trapping" in move.effect_flags:
        score *= 1.08
    score += 2.0 * pp_fraction
    return float(score)


def _stage_multiplier(stage: int) -> float:
    return (2.0 + stage) / 2.0 if stage >= 0 else 2.0 / (2.0 - stage)


def _move_is_supported(move: MoveMechanics) -> bool:
    return (
        move.power > 0
        and move.category != "status"
        and "counter" not in move.effect_flags
        and "self_destruct" not in move.effect_flags
    )


def _accuracy(
    model: MaskedMLPMoveRanker,
    examples: tuple[RepeatableBattleExample, ...],
) -> float:
    correct = sum(
        model.predict(
            item.features.candidate_vectors,
            legal_mask=item.features.legal_mask,
            current_pp=item.features.current_pp,
        )
        == item.chosen_index
        for item in examples
    )
    return correct / len(examples)


def _fixed_heuristic_accuracy(examples: tuple[RepeatableBattleExample, ...]) -> float:
    signal_index = FEATURE_NAMES.index(
        "move.accuracy_weighted_effective_power_fraction"
    )
    correct = sum(
        int(
            np.argmax(
                np.asarray(
                    [vector[signal_index] for vector in item.features.candidate_vectors]
                )
            )
        )
        == item.chosen_index
        for item in examples
    )
    return correct / len(examples)


def _validate_count(value: int, subject: str) -> None:
    if type(value) is not int or not 1 <= value <= _MAXIMUM_EXAMPLES:  # noqa: E721
        raise RepeatableBattleCurriculumError(
            f"{subject} example count must be from one through {_MAXIMUM_EXAMPLES}"
        )
