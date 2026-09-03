"""Expected-utility battle targets aggregated across cartridge RNG trajectories."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_outcome_learning import (
    BattleOutcomeExample,
    BattleOutcomeLearningError,
    BattleOutcomeUpdate,
    BattleOutcomeUpdateReport,
    battle_feature_semantic_sha256,
)
from pokemon_red_completion.battle_semantics import BattleFeatureBatch
from pokemon_red_completion.scenario_lab import ScenarioPartition

_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_UTILITY_TOLERANCE = 1e-9
EXPECTED_UTILITY_RECORD_SCHEMA = "pokemon.core.battle.expected-utility-example.v1"


@dataclass(frozen=True, slots=True)
class BattleExpectedUtilityExample:
    """One visible decision with action values averaged across hidden RNG."""

    root_lineage_id: str
    initial_state_sha256: str
    partition: ScenarioPartition
    features: BattleFeatureBatch
    expected_utilities: tuple[float | None, ...]
    utility_standard_deviations: tuple[float | None, ...]
    trial_counts: tuple[int, ...]
    pre_attack_frame_targets: tuple[int, ...]

    def __post_init__(self) -> None:
        if _SAFE_ID.fullmatch(self.root_lineage_id) is None:
            raise BattleOutcomeLearningError("expected-utility root identity is invalid")
        if _SHA256.fullmatch(self.initial_state_sha256) is None:
            raise BattleOutcomeLearningError("expected-utility state identity is invalid")
        if not isinstance(self.partition, ScenarioPartition):
            raise BattleOutcomeLearningError("expected-utility partition is invalid")
        if not isinstance(self.features, BattleFeatureBatch):
            raise BattleOutcomeLearningError("expected-utility features are invalid")
        width = len(self.features.candidate_vectors)
        if (
            len(self.expected_utilities) != width
            or len(self.utility_standard_deviations) != width
            or len(self.trial_counts) != width
        ):
            raise BattleOutcomeLearningError(
                "expected-utility candidate fields do not match features"
            )
        frames = self.pre_attack_frame_targets
        if (
            len(frames) < 2
            or frames != tuple(sorted(set(frames)))
            or any(type(value) is not int or value < 1 for value in frames)  # noqa: E721
        ):
            raise BattleOutcomeLearningError(
                "expected-utility RNG frame targets are invalid"
            )
        for legal, pp, mean, deviation, count in zip(
            self.features.legal_mask,
            self.features.current_pp,
            self.expected_utilities,
            self.utility_standard_deviations,
            self.trial_counts,
            strict=True,
        ):
            usable = legal and pp > 0
            if usable:
                if (
                    isinstance(mean, bool)
                    or not isinstance(mean, (int, float))
                    or not math.isfinite(float(mean))
                    or isinstance(deviation, bool)
                    or not isinstance(deviation, (int, float))
                    or not math.isfinite(float(deviation))
                    or float(deviation) < 0
                    or type(count) is not int  # noqa: E721
                    or count != len(frames)
                ):
                    raise BattleOutcomeLearningError(
                        "usable expected-utility candidate is invalid"
                    )
            elif mean is not None or deviation is not None or count != 0:
                raise BattleOutcomeLearningError(
                    "unusable expected-utility candidate has trial data"
                )

    @property
    def usable_mask(self) -> NDArray[np.bool_]:
        return np.asarray(
            tuple(
                legal and pp > 0
                for legal, pp in zip(
                    self.features.legal_mask,
                    self.features.current_pp,
                    strict=True,
                )
            ),
            dtype=np.bool_,
        )

    @property
    def best_candidate_indices(self) -> tuple[int, ...]:
        best = max(value for value in self.expected_utilities if value is not None)
        return tuple(
            index
            for index, value in enumerate(self.expected_utilities)
            if value is not None
            and math.isclose(value, best, rel_tol=0.0, abs_tol=_UTILITY_TOLERANCE)
        )

    @property
    def target_distribution(self) -> NDArray[np.float64]:
        result = np.zeros(len(self.expected_utilities), dtype=np.float64)
        winners = self.best_candidate_indices
        result[list(winners)] = 1.0 / len(winners)
        return result

    @property
    def learner_update_eligible(self) -> bool:
        return len(self.best_candidate_indices) < int(np.sum(self.usable_mask))

    @property
    def semantic_cluster_sha256(self) -> str:
        return battle_feature_semantic_sha256(self.features)


def aggregate_battle_rng_trials(
    trials: Iterable[BattleOutcomeExample],
) -> BattleExpectedUtilityExample:
    """Average candidate utility over distinct pre-attack frame targets."""

    rows = tuple(trials)
    if len(rows) < 2 or any(not isinstance(row, BattleOutcomeExample) for row in rows):
        raise BattleOutcomeLearningError("expected utility requires at least two trials")
    first = rows[0]
    if any(
        row.root_lineage_id != first.root_lineage_id
        or row.initial_state_sha256 != first.initial_state_sha256
        or row.partition is not first.partition
        or row.features != first.features
        for row in rows[1:]
    ):
        raise BattleOutcomeLearningError("RNG trials do not share one visible decision")
    scheduled: list[tuple[int, BattleOutcomeExample]] = []
    for row in rows:
        frames = {
            outcome.pre_attack_frames
            for outcome in row.outcomes
            if outcome is not None
        }
        if len(frames) != 1:
            raise BattleOutcomeLearningError(
                "one RNG trial does not share a pre-attack frame target"
            )
        scheduled.append((next(iter(frames)), row))
    scheduled.sort(key=lambda value: value[0])
    frame_targets = tuple(frame for frame, _ in scheduled)
    if len(frame_targets) != len(set(frame_targets)):
        raise BattleOutcomeLearningError("RNG trial frame targets repeat")

    means: list[float | None] = []
    deviations: list[float | None] = []
    counts: list[int] = []
    for candidate_index in range(len(first.outcomes)):
        retained = []
        for _, row in scheduled:
            outcome = row.outcomes[candidate_index]
            if outcome is not None:
                retained.append(outcome.utility)
        values = tuple(retained)
        if not values:
            means.append(None)
            deviations.append(None)
            counts.append(0)
            continue
        if len(values) != len(rows):
            raise BattleOutcomeLearningError(
                "usable candidate is missing from one RNG trial"
            )
        means.append(float(np.mean(values)))
        deviations.append(float(np.std(values)))
        counts.append(len(values))
    return BattleExpectedUtilityExample(
        root_lineage_id=first.root_lineage_id,
        initial_state_sha256=first.initial_state_sha256,
        partition=first.partition,
        features=first.features,
        expected_utilities=tuple(means),
        utility_standard_deviations=tuple(deviations),
        trial_counts=tuple(counts),
        pre_attack_frame_targets=frame_targets,
    )


def adapt_mlp_last_layer_from_expected_utilities(
    base_model: MaskedMLPMoveRanker,
    examples: Iterable[BattleExpectedUtilityExample],
    *,
    epochs: int = 100,
    learning_rate: float = 0.01,
    prior_l2: float = 0.1,
) -> BattleOutcomeUpdate:
    """Adapt the shared ranker to mean cartridge utility, not one RNG roll."""

    choices = tuple(examples)
    _require_training_examples(choices)
    _require_hyperparameters(epochs, learning_rate, prior_l2)
    if any(choice.features.feature_names != base_model.feature_names for choice in choices):
        raise BattleOutcomeLearningError(
            "expected-utility feature schema differs from the model"
        )
    payload = base_model.to_dict()
    input_weights = np.asarray(payload["input_weights"], dtype=np.float64)
    hidden_bias = np.asarray(payload["hidden_bias"], dtype=np.float64)
    prior_output = np.asarray(payload["output_weights"], dtype=np.float64)
    output = prior_output.copy()
    first_moment = np.zeros_like(output)
    second_moment = np.zeros_like(output)
    beta_one, beta_two, epsilon = 0.9, 0.999, 1e-8
    loss_before = _expected_utility_loss(base_model, choices)

    for step in range(1, epochs + 1):
        gradient = np.zeros_like(output)
        for example in choices:
            features = np.asarray(example.features.candidate_vectors, dtype=np.float64)
            hidden = np.tanh(features @ input_weights.T + hidden_bias)
            scores = hidden @ output
            usable = example.usable_mask
            probabilities = np.zeros(scores.shape[0], dtype=np.float64)
            shifted = scores[usable] - np.max(scores[usable])
            exponentials = np.exp(shifted)
            probabilities[usable] = exponentials / np.sum(exponentials)
            gradient += hidden.T @ (probabilities - example.target_distribution)
        gradient /= len(choices)
        gradient += prior_l2 * (output - prior_output)
        first_moment = beta_one * first_moment + (1.0 - beta_one) * gradient
        second_moment = beta_two * second_moment + (1.0 - beta_two) * gradient**2
        corrected_first = first_moment / (1.0 - beta_one**step)
        corrected_second = second_moment / (1.0 - beta_two**step)
        output -= learning_rate * corrected_first / (np.sqrt(corrected_second) + epsilon)

    updated = MaskedMLPMoveRanker(
        feature_names=base_model.feature_names,
        feature_schema_id=base_model.feature_schema_id,
        input_weights=input_weights,
        hidden_bias=hidden_bias,
        output_weights=output,
        output_bias=float(payload["output_bias"]),
        training_seed=base_model.training_seed,
    )
    loss_after = _expected_utility_loss(updated, choices)
    if not loss_after < loss_before:
        raise BattleOutcomeLearningError(
            "expected-utility update did not reduce training loss"
        )
    base_sha256 = _model_sha256(base_model)
    updated_sha256 = _model_sha256(updated)
    if updated_sha256 == base_sha256:
        raise BattleOutcomeLearningError("expected-utility update did not change the model")
    return BattleOutcomeUpdate(
        model=updated,
        report=BattleOutcomeUpdateReport(
            base_model_sha256=base_sha256,
            updated_model_sha256=updated_sha256,
            training_example_count=len(choices),
            training_root_lineage_ids=tuple(
                sorted({choice.root_lineage_id for choice in choices})
            ),
            training_state_sha256=tuple(
                sorted(choice.initial_state_sha256 for choice in choices)
            ),
            loss_before=loss_before,
            loss_after=loss_after,
            epochs=epochs,
            learning_rate=float(learning_rate),
            prior_l2=float(prior_l2),
        ),
    )


def expected_utility_record(
    example: BattleExpectedUtilityExample,
    *,
    capture_id: str,
    manifest_sha256: str,
) -> dict[str, object]:
    """Serialize an aggregate without ROM bytes, save bytes, or private paths."""

    if not isinstance(example, BattleExpectedUtilityExample):
        raise TypeError("example must be a BattleExpectedUtilityExample")
    if _SAFE_ID.fullmatch(capture_id) is None or _SHA256.fullmatch(manifest_sha256) is None:
        raise BattleOutcomeLearningError("expected-utility record identity is invalid")
    features = example.features
    return {
        "schema": EXPECTED_UTILITY_RECORD_SCHEMA,
        "capture_id": capture_id,
        "manifest_sha256": manifest_sha256,
        "root_lineage_id": example.root_lineage_id,
        "initial_state_sha256": example.initial_state_sha256,
        "partition": example.partition.value,
        "features": {
            "schema_id": features.schema_id,
            "feature_names": list(features.feature_names),
            "candidate_vectors": [list(row) for row in features.candidate_vectors],
            "legal_mask": list(features.legal_mask),
            "current_pp": list(features.current_pp),
            "slot_indices": list(features.slot_indices),
        },
        "expected_utilities": list(example.expected_utilities),
        "utility_standard_deviations": list(example.utility_standard_deviations),
        "trial_counts": list(example.trial_counts),
        "pre_attack_frame_targets": list(example.pre_attack_frame_targets),
        "best_candidate_indices": list(example.best_candidate_indices),
        "learner_update_eligible": example.learner_update_eligible,
        "private_path_fields": 0,
        "development_artifact": True,
        "sealed_evidence": False,
    }


def parse_expected_utility_record(value: object) -> BattleExpectedUtilityExample:
    """Strictly parse and rederive one path-free expected-utility record."""

    if not isinstance(value, dict) or set(value) != {
        "schema",
        "capture_id",
        "manifest_sha256",
        "root_lineage_id",
        "initial_state_sha256",
        "partition",
        "features",
        "expected_utilities",
        "utility_standard_deviations",
        "trial_counts",
        "pre_attack_frame_targets",
        "best_candidate_indices",
        "learner_update_eligible",
        "private_path_fields",
        "development_artifact",
        "sealed_evidence",
    }:
        raise BattleOutcomeLearningError("expected-utility record fields are invalid")
    if (
        value.get("schema") != EXPECTED_UTILITY_RECORD_SCHEMA
        or value.get("private_path_fields") != 0
        or value.get("development_artifact") is not True
        or value.get("sealed_evidence") is not False
        or _SAFE_ID.fullmatch(str(value.get("capture_id"))) is None
        or _SHA256.fullmatch(str(value.get("manifest_sha256"))) is None
    ):
        raise BattleOutcomeLearningError("expected-utility record contract is invalid")
    raw_features = value.get("features")
    if not isinstance(raw_features, dict) or set(raw_features) != {
        "schema_id",
        "feature_names",
        "candidate_vectors",
        "legal_mask",
        "current_pp",
        "slot_indices",
    }:
        raise BattleOutcomeLearningError("expected-utility feature fields are invalid")
    try:
        features = BattleFeatureBatch(
            schema_id=str(raw_features["schema_id"]),
            feature_names=tuple(str(item) for item in raw_features["feature_names"]),
            candidate_vectors=tuple(
                tuple(float(item) for item in row)
                for row in raw_features["candidate_vectors"]
            ),
            legal_mask=tuple(raw_features["legal_mask"]),
            current_pp=tuple(float(item) for item in raw_features["current_pp"]),
            slot_indices=tuple(raw_features["slot_indices"]),
        )
        example = BattleExpectedUtilityExample(
            root_lineage_id=str(value["root_lineage_id"]),
            initial_state_sha256=str(value["initial_state_sha256"]),
            partition=ScenarioPartition(str(value["partition"])),
            features=features,
            expected_utilities=tuple(
                None if item is None else float(item)
                for item in value["expected_utilities"]
            ),
            utility_standard_deviations=tuple(
                None if item is None else float(item)
                for item in value["utility_standard_deviations"]
            ),
            trial_counts=tuple(value["trial_counts"]),
            pre_attack_frame_targets=tuple(value["pre_attack_frame_targets"]),
        )
    except (KeyError, TypeError, ValueError):
        raise BattleOutcomeLearningError(
            "expected-utility record values are invalid"
        ) from None
    if (
        list(example.best_candidate_indices) != value["best_candidate_indices"]
        or example.learner_update_eligible is not value["learner_update_eligible"]
        or json.loads(json.dumps(expected_utility_record(
            example,
            capture_id=str(value["capture_id"]),
            manifest_sha256=str(value["manifest_sha256"]),
        )))
        != value
    ):
        raise BattleOutcomeLearningError("expected-utility record derivation differs")
    return example


def _require_training_examples(
    examples: tuple[BattleExpectedUtilityExample, ...],
) -> None:
    if not examples or any(
        not isinstance(value, BattleExpectedUtilityExample) for value in examples
    ):
        raise BattleOutcomeLearningError("expected-utility examples are invalid")
    if any(value.partition is not ScenarioPartition.TRAIN for value in examples):
        raise BattleOutcomeLearningError("expected-utility fit accepts train only")
    states = tuple(value.initial_state_sha256 for value in examples)
    if len(states) != len(set(states)):
        raise BattleOutcomeLearningError("expected-utility examples duplicate a state")
    if not any(value.learner_update_eligible for value in examples):
        raise BattleOutcomeLearningError(
            "expected-utility examples contain no preference signal"
        )


def _require_hyperparameters(
    epochs: int,
    learning_rate: float,
    prior_l2: float,
) -> None:
    if type(epochs) is not int or epochs < 1:  # noqa: E721
        raise BattleOutcomeLearningError("epochs must be a positive integer")
    for value, name, positive in (
        (learning_rate, "learning_rate", True),
        (prior_l2, "prior_l2", False),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or (float(value) <= 0 if positive else float(value) < 0)
        ):
            raise BattleOutcomeLearningError(f"{name} is invalid")


def _expected_utility_loss(
    model: MaskedMLPMoveRanker,
    examples: tuple[BattleExpectedUtilityExample, ...],
) -> float:
    losses = []
    for example in examples:
        probabilities = model.predict_proba(
            example.features.candidate_vectors,
            legal_mask=example.features.legal_mask,
            current_pp=example.features.current_pp,
        )
        target = example.target_distribution
        selected = target > 0
        losses.append(float(-np.sum(target[selected] * np.log(probabilities[selected]))))
    return float(np.mean(losses))


def _model_sha256(model: MaskedMLPMoveRanker) -> str:
    return hashlib.sha256(model.to_json().encode("ascii")).hexdigest()


__all__ = [
    "EXPECTED_UTILITY_RECORD_SCHEMA",
    "BattleExpectedUtilityExample",
    "adapt_mlp_last_layer_from_expected_utilities",
    "aggregate_battle_rng_trials",
    "expected_utility_record",
    "parse_expected_utility_record",
]
