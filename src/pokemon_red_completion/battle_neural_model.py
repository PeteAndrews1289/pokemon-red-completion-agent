"""Small shared nonlinear ranker for context-dependent battle move choices."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

from pokemon_red_completion.battle_model import (
    BATTLE_MODEL_FORMAT_VERSION,
    CURRENT_BATTLE_FEATURE_SCHEMA_ID,
    BattleChoiceExample,
    BattleModelValidationError,
    MaskedLinearMoveRanker,
)

BATTLE_MLP_MODEL_ID = "pokemon.core.battle.masked-mlp-ranker.v1"


class MaskedMLPMoveRanker:
    """One-hidden-layer candidate scorer with legality-masked listwise output."""

    def __init__(
        self,
        *,
        feature_names: Sequence[str],
        input_weights: ArrayLike,
        hidden_bias: ArrayLike,
        output_weights: ArrayLike,
        output_bias: float,
        feature_schema_id: str = CURRENT_BATTLE_FEATURE_SCHEMA_ID,
        training_seed: int = 0,
    ) -> None:
        names = tuple(feature_names)
        if not names or len(set(names)) != len(names):
            raise BattleModelValidationError("MLP feature names are invalid.")
        first = np.asarray(input_weights, dtype=np.float64)
        bias = np.asarray(hidden_bias, dtype=np.float64)
        second = np.asarray(output_weights, dtype=np.float64)
        if first.ndim != 2 or first.shape[1] != len(names) or first.shape[0] < 1:
            raise BattleModelValidationError("MLP input weights have the wrong shape.")
        if bias.shape != (first.shape[0],) or second.shape != (first.shape[0],):
            raise BattleModelValidationError("MLP hidden parameters have the wrong shape.")
        if not all(np.all(np.isfinite(value)) for value in (first, bias, second)):
            raise BattleModelValidationError("MLP parameters must be finite.")
        if not math.isfinite(float(output_bias)):
            raise BattleModelValidationError("MLP output bias must be finite.")
        if feature_schema_id != CURRENT_BATTLE_FEATURE_SCHEMA_ID:
            raise BattleModelValidationError("Unsupported MLP feature schema ID.")
        if type(training_seed) is not int or training_seed < 0:  # noqa: E721
            raise BattleModelValidationError("MLP training seed is invalid.")
        self._feature_names = names
        self._input_weights = first.copy()
        self._hidden_bias = bias.copy()
        self._output_weights = second.copy()
        self._output_bias = float(output_bias)
        self._feature_schema_id = feature_schema_id
        self._training_seed = training_seed

    @property
    def feature_names(self) -> tuple[str, ...]:
        return self._feature_names

    @property
    def feature_schema_id(self) -> str:
        return self._feature_schema_id

    @property
    def model_id(self) -> str:
        return BATTLE_MLP_MODEL_ID

    @property
    def training_seed(self) -> int:
        return self._training_seed

    def scores(self, candidate_features: ArrayLike) -> NDArray[np.float64]:
        hidden = self.hidden_embeddings(candidate_features)
        scores = hidden @ self._output_weights + self._output_bias
        if not np.all(np.isfinite(scores)):
            raise BattleModelValidationError("MLP candidate scores must be finite.")
        return np.asarray(scores, dtype=np.float64)

    def hidden_embeddings(self, candidate_features: ArrayLike) -> NDArray[np.float64]:
        """Project candidates through the frozen representation before ranking."""

        features = np.asarray(candidate_features, dtype=np.float64)
        if features.ndim != 2 or features.shape[1] != len(self.feature_names):
            raise BattleModelValidationError("MLP candidate features have the wrong shape.")
        hidden = np.tanh(features @ self._input_weights.T + self._hidden_bias)
        if not np.all(np.isfinite(hidden)):
            raise BattleModelValidationError("MLP hidden embeddings must be finite.")
        return np.asarray(hidden, dtype=np.float64)

    def predict_proba(
        self,
        candidate_features: ArrayLike,
        *,
        legal_mask: ArrayLike,
        current_pp: ArrayLike,
    ) -> NDArray[np.float64]:
        scores = self.scores(candidate_features)
        legal = np.asarray(legal_mask, dtype=np.bool_)
        pp = np.asarray(current_pp, dtype=np.float64)
        if legal.shape != scores.shape or pp.shape != scores.shape:
            raise BattleModelValidationError("MLP candidate metadata has the wrong shape.")
        usable = legal & (pp > 0)
        if not np.any(usable):
            raise BattleModelValidationError("MLP prediction has no usable candidate.")
        shifted = scores[usable] - np.max(scores[usable])
        exp = np.exp(shifted)
        result = np.zeros_like(scores)
        result[usable] = exp / np.sum(exp)
        return result

    def predict(
        self,
        candidate_features: ArrayLike,
        *,
        legal_mask: ArrayLike,
        current_pp: ArrayLike,
    ) -> int:
        return int(
            np.argmax(
                self.predict_proba(
                    candidate_features,
                    legal_mask=legal_mask,
                    current_pp=current_pp,
                )
            )
        )

    @classmethod
    def fit(
        cls,
        *,
        feature_names: Sequence[str],
        examples: Iterable[BattleChoiceExample],
        seed: int = 0,
        hidden_units: int = 16,
        epochs: int = 300,
        learning_rate: float = 0.01,
        l2: float = 1e-4,
    ) -> MaskedMLPMoveRanker:
        choices = tuple(examples)
        names = tuple(feature_names)
        if not names or not choices:
            raise BattleModelValidationError("MLP training inputs are invalid.")
        if type(seed) is not int or not 0 <= seed <= np.iinfo(np.uint64).max:  # noqa: E721
            raise BattleModelValidationError("MLP training seed is invalid.")
        if type(hidden_units) is not int or not 2 <= hidden_units <= 128:  # noqa: E721
            raise BattleModelValidationError("MLP training inputs are invalid.")
        if type(epochs) is not int or epochs < 1:  # noqa: E721
            raise BattleModelValidationError("MLP epochs are invalid.")
        if not math.isfinite(learning_rate) or learning_rate <= 0:
            raise BattleModelValidationError("MLP learning rate is invalid.")
        if not math.isfinite(l2) or l2 < 0:
            raise BattleModelValidationError("MLP regularization is invalid.")
        for choice in choices:
            if choice.candidate_features.shape[1] != len(names):
                raise BattleModelValidationError("MLP example feature count is invalid.")
        rng = np.random.default_rng(seed)
        w1 = rng.normal(0.0, 0.03, size=(hidden_units, len(names)))
        b1 = np.zeros(hidden_units, dtype=np.float64)
        w2 = rng.normal(0.0, 0.03, size=hidden_units)
        b2 = 0.0
        parameters = [w1, b1, w2]
        first_moments = [np.zeros_like(value) for value in parameters]
        second_moments = [np.zeros_like(value) for value in parameters]
        beta1, beta2, epsilon = 0.9, 0.999, 1e-8
        for step in range(1, epochs + 1):
            gradients = [np.zeros_like(value) for value in parameters]
            for choice in choices:
                x = choice.candidate_features
                hidden = np.tanh(x @ w1.T + b1)
                scores = hidden @ w2 + b2
                usable = choice.usable_mask
                shifted = scores[usable] - np.max(scores[usable])
                probabilities = np.zeros_like(scores)
                exp = np.exp(shifted)
                probabilities[usable] = exp / np.sum(exp)
                probabilities[choice.chosen_index] -= 1.0
                gradients[2] += hidden.T @ probabilities
                hidden_gradient = np.outer(probabilities, w2) * (1.0 - hidden**2)
                gradients[0] += hidden_gradient.T @ x
                gradients[1] += np.sum(hidden_gradient, axis=0)
            for index, (parameter, gradient) in enumerate(
                zip(parameters, gradients, strict=True)
            ):
                gradient /= len(choices)
                if index in {0, 2}:
                    gradient += l2 * parameter
                first_moments[index] *= beta1
                first_moments[index] += (1.0 - beta1) * gradient
                second_moments[index] *= beta2
                second_moments[index] += (1.0 - beta2) * gradient**2
                corrected_first = first_moments[index] / (1.0 - beta1**step)
                corrected_second = second_moments[index] / (1.0 - beta2**step)
                parameter -= learning_rate * corrected_first / (
                    np.sqrt(corrected_second) + epsilon
                )
        return cls(
            feature_names=names,
            input_weights=w1,
            hidden_bias=b1,
            output_weights=w2,
            output_bias=b2,
            training_seed=seed,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_names": list(self.feature_names),
            "feature_schema_id": self.feature_schema_id,
            "format_version": BATTLE_MODEL_FORMAT_VERSION,
            "model_id": self.model_id,
            "training_seed": self.training_seed,
            "input_weights": self._input_weights.tolist(),
            "hidden_bias": self._hidden_bias.tolist(),
            "output_weights": self._output_weights.tolist(),
            "output_bias": self._output_bias,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> MaskedMLPMoveRanker:
        if value.get("model_id") != BATTLE_MLP_MODEL_ID:
            raise BattleModelValidationError("Unsupported MLP model ID.")
        if value.get("format_version") != BATTLE_MODEL_FORMAT_VERSION:
            raise BattleModelValidationError("Unsupported MLP model format version.")
        try:
            return cls(
                feature_names=value["feature_names"],  # type: ignore[arg-type]
                feature_schema_id=str(value["feature_schema_id"]),
                input_weights=value["input_weights"],
                hidden_bias=value["hidden_bias"],
                output_weights=value["output_weights"],
                output_bias=float(value["output_bias"]),
                training_seed=int(value["training_seed"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise BattleModelValidationError("MLP model payload is invalid.") from error


BattleMoveRanker = MaskedLinearMoveRanker | MaskedMLPMoveRanker
