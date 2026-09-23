"""Small schema-bound listwise head for outcome-trained trainer choices."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


class TrainerHeadError(ValueError):
    """A head, example, or serialized checkpoint is incompatible."""


@dataclass(frozen=True, slots=True)
class TrainerHeadExample:
    candidate_vectors: tuple[tuple[float, ...], ...]
    best_indices: tuple[int, ...]
    target_probabilities: tuple[float, ...] | None = None
    mean_returns: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        if (
            len(self.candidate_vectors) < 2
            or not self.best_indices
            or len(set(self.best_indices)) != len(self.best_indices)
            or any(
                type(index) is not int or not 0 <= index < len(self.candidate_vectors)
                for index in self.best_indices
            )
        ):
            raise TrainerHeadError("listwise target is invalid")
        width = len(self.candidate_vectors[0])
        if not width or any(
            len(row) != width
            or any(not math.isfinite(value) or not -1.0 <= value <= 1.0 for value in row)
            for row in self.candidate_vectors
        ):
            raise TrainerHeadError("listwise feature matrix is invalid")
        if self.target_probabilities is not None and (
            len(self.target_probabilities) != len(self.candidate_vectors)
            or any(not math.isfinite(value) or value < 0 for value in self.target_probabilities)
            or not math.isclose(sum(self.target_probabilities), 1.0, abs_tol=1e-8)
        ):
            raise TrainerHeadError("soft listwise target differs")
        if self.mean_returns is not None and (
            len(self.mean_returns) != len(self.candidate_vectors)
            or any(not math.isfinite(value) for value in self.mean_returns)
        ):
            raise TrainerHeadError("mean return inventory differs")


@dataclass(frozen=True, slots=True)
class TrainerHeadModel:
    schema_id: str
    feature_names: tuple[str, ...]
    weights1: NDArray[np.float64]
    bias1: NDArray[np.float64]
    weights2: NDArray[np.float64]
    training_seed: int
    training_objective: str = "cross_entropy"

    def __post_init__(self) -> None:
        if self.training_objective not in {"cross_entropy", "expected_regret", "pairwise_regret"}:
            raise TrainerHeadError("head training objective differs")
        if (
            not self.schema_id
            or not self.feature_names
            or len(set(self.feature_names)) != len(self.feature_names)
        ):
            raise TrainerHeadError("head schema is invalid")
        width = len(self.feature_names)
        if (
            self.weights1.ndim != 2
            or self.weights1.shape[0] != width
            or self.weights1.shape[1] < 2
            or self.bias1.shape != (self.weights1.shape[1],)
            or self.weights2.shape != (self.weights1.shape[1],)
            or any(
                not np.all(np.isfinite(value))
                for value in (
                    self.weights1,
                    self.bias1,
                    self.weights2,
                )
            )
            or type(self.training_seed) is not int
            or self.training_seed < 0  # noqa: E721
        ):
            raise TrainerHeadError("head parameters are invalid")
        for name in ("weights1", "bias1", "weights2"):
            detached = np.asarray(getattr(self, name), dtype=np.float64).copy()
            detached.setflags(write=False)
            object.__setattr__(self, name, detached)

    def scores(self, candidates: tuple[tuple[float, ...], ...]) -> NDArray[np.float64]:
        features = np.asarray(candidates, dtype=np.float64)
        if (
            features.ndim != 2
            or features.shape[1] != len(self.feature_names)
            or features.shape[0] < 1
            or not np.all(np.isfinite(features))
        ):
            raise TrainerHeadError("head input differs from its schema")
        hidden = np.tanh(features @ self.weights1 + self.bias1)
        return np.asarray(hidden @ self.weights2, dtype=np.float64)

    def probabilities(self, candidates: tuple[tuple[float, ...], ...]) -> NDArray[np.float64]:
        scores = self.scores(candidates)
        shifted = scores - np.max(scores)
        probabilities = np.exp(shifted)
        return probabilities / np.sum(probabilities)

    def predict_index(self, candidates: tuple[tuple[float, ...], ...]) -> int:
        return int(np.argmax(self.probabilities(candidates)))

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": 1,
            "model_id": "pokemon.core.battle.trainer-head.v1",
            "schema_id": self.schema_id,
            "feature_names": list(self.feature_names),
            "weights1": self.weights1.tolist(),
            "bias1": self.bias1.tolist(),
            "weights2": self.weights2.tolist(),
            "training_seed": self.training_seed,
            **(
                {"training_objective": self.training_objective}
                if self.training_objective != "cross_entropy"
                else {}
            ),
        }

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, object],
        *,
        schema_id: str,
        feature_names: tuple[str, ...],
    ) -> TrainerHeadModel:
        if (
            value.get("format_version") != (2 if "auxiliary_effect" in value else 1)
            or value.get("model_id") != "pokemon.core.battle.trainer-head.v1"
            or value.get("schema_id") != schema_id
            or value.get("feature_names") != list(feature_names)
        ):
            raise TrainerHeadError("head checkpoint schema is incompatible")
        try:
            head = cls(
                schema_id=schema_id,
                feature_names=feature_names,
                weights1=np.asarray(value["weights1"], dtype=np.float64),
                bias1=np.asarray(value["bias1"], dtype=np.float64),
                weights2=np.asarray(value["weights2"], dtype=np.float64),
                training_seed=value["training_seed"],  # type: ignore[arg-type]
                training_objective=value.get("training_objective", "cross_entropy"),  # type: ignore[arg-type]
            )
            if "auxiliary_effect" in value:
                from .red_effect_selector_head import restore_effect
                return restore_effect(head, value["auxiliary_effect"])
            return head
        except (KeyError, TypeError, ValueError) as error:
            raise TrainerHeadError("head checkpoint parameters are invalid") from error

    @classmethod
    def fit(
        cls,
        *,
        schema_id: str,
        feature_names: tuple[str, ...],
        examples: Iterable[TrainerHeadExample],
        seed: int,
        hidden_units: int = 16,
        epochs: int = 300,
        learning_rate: float = 0.02,
        initial_model: TrainerHeadModel | None = None,
        training_objective: str = "cross_entropy",
    ) -> TrainerHeadModel:
        cases = tuple(examples)
        if not cases or any(len(case.candidate_vectors[0]) != len(feature_names) for case in cases):
            raise TrainerHeadError("head fit has no compatible examples")
        if not 2 <= hidden_units <= 128 or epochs < 1 or learning_rate <= 0:
            raise TrainerHeadError("head optimizer configuration differs")
        if training_objective not in {"cross_entropy", "expected_regret"} or (
            training_objective == "expected_regret"
            and any(case.mean_returns is None for case in cases)
        ):
            raise TrainerHeadError("expected-regret training requires measured returns")
        if initial_model is not None:
            if (
                initial_model.schema_id != schema_id
                or initial_model.feature_names != feature_names
                or initial_model.weights1.shape != (len(feature_names), hidden_units)
            ):
                raise TrainerHeadError("warm-start head is incompatible")
            w1 = initial_model.weights1.copy()
            b1 = initial_model.bias1.copy()
            w2 = initial_model.weights2.copy()
        else:
            rng = np.random.default_rng(seed)
            w1 = rng.normal(0, 0.04, size=(len(feature_names), hidden_units))
            b1 = np.zeros(hidden_units)
            w2 = rng.normal(0, 0.04, size=hidden_units)
        # A tiny full-batch learner keeps this first bounded fit inspectable.
        for _ in range(epochs):
            g1 = np.zeros_like(w1)
            gb = np.zeros_like(b1)
            g2 = np.zeros_like(w2)
            for case in cases:
                x = np.asarray(case.candidate_vectors, dtype=np.float64)
                h = np.tanh(x @ w1 + b1)
                scores = h @ w2
                shifted = scores - np.max(scores)
                p = np.exp(shifted)
                p /= np.sum(p)
                if case.target_probabilities is None:
                    target = np.zeros(len(case.candidate_vectors))
                    target[list(case.best_indices)] = 1.0 / len(case.best_indices)
                else:
                    target = np.asarray(case.target_probabilities, dtype=np.float64)
                residual = p - target
                if training_objective == "expected_regret":
                    assert case.mean_returns is not None
                    _, residual = expected_regret_loss_gradient(p, case.mean_returns)
                g2 += h.T @ residual
                dh = np.outer(residual, w2) * (1.0 - h * h)
                g1 += x.T @ dh
                gb += np.sum(dh, axis=0)
            rate = learning_rate / len(cases)
            w1 -= rate * np.clip(g1, -10, 10)
            b1 -= rate * np.clip(gb, -10, 10)
            w2 -= rate * np.clip(g2, -10, 10)
        return cls(schema_id, feature_names, w1, b1, w2, seed, training_objective)


def expected_regret_loss_gradient(
    probabilities: NDArray[np.float64],
    returns: tuple[float, ...],
) -> tuple[float, NDArray[np.float64]]:
    """Expected return shortfall and its derivative with respect to logits."""
    rewards = np.asarray(returns, dtype=np.float64)
    if rewards.shape != probabilities.shape or not np.all(np.isfinite(rewards)):
        raise TrainerHeadError("return-loss inventory differs")
    regret = np.max(rewards) - rewards
    loss = float(np.dot(probabilities, regret))
    return loss, probabilities * (regret - loss)
