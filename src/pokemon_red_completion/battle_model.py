"""Game-neutral masked linear ranking for battle move candidates.

The model scores every move with the same linear function.  It therefore has no
slot-specific parameters and can rank a variable number of candidates.  Legal
moves with positive PP participate in the listwise softmax; every other move is
assigned zero probability.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, NoReturn, Protocol, runtime_checkable

import numpy as np
from numpy.typing import ArrayLike, NDArray

BATTLE_FEATURE_SCHEMA_ID = "pokemon.core.battle.move-ranker.v2"
CURRENT_BATTLE_FEATURE_SCHEMA_ID = "pokemon.core.battle.move-ranker.v3"
LEGACY_BATTLE_FEATURE_SCHEMA_ID = "pokemon.core.battle.move-ranker.v1"
SUPPORTED_BATTLE_FEATURE_SCHEMA_IDS = frozenset(
    {
        CURRENT_BATTLE_FEATURE_SCHEMA_ID,
        BATTLE_FEATURE_SCHEMA_ID,
        LEGACY_BATTLE_FEATURE_SCHEMA_ID,
    }
)
BATTLE_MODEL_ID = "pokemon.core.battle.masked-linear-ranker.v1"


@runtime_checkable
class BattleMoveScorer(Protocol):
    """Structural contract shared by linear and nonlinear candidate scorers."""

    @property
    def feature_names(self) -> tuple[str, ...]: ...

    def scores(self, candidate_features: ArrayLike) -> NDArray[np.float64]: ...

    def predict(
        self,
        candidate_features: ArrayLike,
        *,
        legal_mask: ArrayLike,
        current_pp: ArrayLike,
    ) -> int: ...
BATTLE_MODEL_FORMAT_VERSION = 1

_MODEL_FIELDS = frozenset(
    {
        "feature_names",
        "feature_schema_id",
        "format_version",
        "model_id",
        "training_seed",
        "weights",
    }
)
_FORBIDDEN_SLOT_FEATURES = frozenset(
    {
        "candidate_index",
        "move_slot",
        "move_slot_index",
        "position_index",
        "slot",
        "slot_index",
    }
)


class BattleModelValidationError(ValueError):
    """Raised when model inputs or serialized model data are invalid."""


@dataclass(eq=False, frozen=True, slots=True)
class BattleChoiceExample:
    """One demonstrated choice among a variable number of move candidates."""

    candidate_features: NDArray[np.float64]
    legal_mask: NDArray[np.bool_]
    current_pp: NDArray[np.float64]
    chosen_index: int

    def __init__(
        self,
        candidate_features: ArrayLike,
        legal_mask: ArrayLike,
        current_pp: ArrayLike,
        chosen_index: int,
    ) -> None:
        features = _feature_matrix(candidate_features)
        legal = _legal_mask(legal_mask, candidate_count=features.shape[0])
        pp = _pp_vector(current_pp, candidate_count=features.shape[0])
        chosen = _integer(chosen_index, label="chosen_index", minimum=0)
        if chosen >= features.shape[0]:
            raise BattleModelValidationError("chosen_index is outside the candidate range.")
        usable = legal & (pp > 0)
        if not np.any(usable):
            raise BattleModelValidationError(
                "A battle choice must contain at least one legal move with positive PP."
            )
        if not usable[chosen]:
            raise BattleModelValidationError("The chosen move must be legal and have positive PP.")

        features.setflags(write=False)
        legal.setflags(write=False)
        pp.setflags(write=False)
        object.__setattr__(self, "candidate_features", features)
        object.__setattr__(self, "legal_mask", legal)
        object.__setattr__(self, "current_pp", pp)
        object.__setattr__(self, "chosen_index", chosen)

    @property
    def usable_mask(self) -> NDArray[np.bool_]:
        """Return the combined legality and positive-PP mask."""

        return self.legal_mask & (self.current_pp > 0)


class MaskedLinearMoveRanker:
    """A shared linear scorer over legal move candidates."""

    def __init__(
        self,
        *,
        feature_names: Sequence[str],
        weights: ArrayLike,
        feature_schema_id: str = BATTLE_FEATURE_SCHEMA_ID,
        model_id: str = BATTLE_MODEL_ID,
        training_seed: int = 0,
    ) -> None:
        names = _feature_names(feature_names)
        coefficients = _weight_vector(weights, feature_count=len(names))
        if feature_schema_id not in SUPPORTED_BATTLE_FEATURE_SCHEMA_IDS:
            raise BattleModelValidationError("Unsupported battle feature schema ID.")
        if model_id != BATTLE_MODEL_ID:
            raise BattleModelValidationError("Unsupported battle model ID.")
        seed = _integer(training_seed, label="training_seed", minimum=0)
        if seed > np.iinfo(np.uint64).max:
            raise BattleModelValidationError(
                "training_seed must fit in an unsigned 64-bit integer."
            )

        coefficients.setflags(write=False)
        self._feature_names = names
        self._weights = coefficients
        self._feature_schema_id = feature_schema_id
        self._model_id = model_id
        self._training_seed = seed

    @property
    def feature_names(self) -> tuple[str, ...]:
        return self._feature_names

    @property
    def feature_schema_id(self) -> str:
        return self._feature_schema_id

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def training_seed(self) -> int:
        return self._training_seed

    @property
    def weights(self) -> NDArray[np.float64]:
        """Return a copy so callers cannot mutate the fitted model."""

        return self._weights.copy()

    def scores(self, candidate_features: ArrayLike) -> NDArray[np.float64]:
        """Score all candidates with the same learned coefficient vector."""

        features = _feature_matrix(
            candidate_features,
            expected_feature_count=len(self.feature_names),
        )
        with np.errstate(over="ignore", invalid="ignore"):
            scores = features @ self._weights
        if not np.all(np.isfinite(scores)):
            raise BattleModelValidationError("Candidate scores must be finite.")
        return np.asarray(scores, dtype=np.float64)

    def predict_proba(
        self,
        candidate_features: ArrayLike,
        *,
        legal_mask: ArrayLike,
        current_pp: ArrayLike,
    ) -> NDArray[np.float64]:
        """Return listwise probabilities, with unusable candidates fixed at zero."""

        scores = self.scores(candidate_features)
        usable = _usable_mask(
            legal_mask,
            current_pp,
            candidate_count=scores.shape[0],
        )
        return _masked_softmax(scores, usable)

    def predict(
        self,
        candidate_features: ArrayLike,
        *,
        legal_mask: ArrayLike,
        current_pp: ArrayLike,
    ) -> int:
        """Return the zero-based index of the highest-probability usable move."""

        probabilities = self.predict_proba(
            candidate_features,
            legal_mask=legal_mask,
            current_pp=current_pp,
        )
        return int(np.argmax(probabilities))

    @classmethod
    def fit(
        cls,
        *,
        feature_names: Sequence[str],
        examples: Iterable[BattleChoiceExample],
        seed: int = 0,
        epochs: int = 500,
        learning_rate: float = 0.03,
        l2: float = 1e-4,
        initialization_scale: float = 1e-3,
    ) -> MaskedLinearMoveRanker:
        """Fit listwise cross-entropy with deterministic full-batch Adam."""

        names = _feature_names(feature_names)
        choices = tuple(examples)
        if not choices:
            raise BattleModelValidationError("At least one battle choice is required for fitting.")
        if any(not isinstance(choice, BattleChoiceExample) for choice in choices):
            raise BattleModelValidationError("Every training item must be a BattleChoiceExample.")
        for choice in choices:
            if choice.candidate_features.shape[1] != len(names):
                raise BattleModelValidationError(
                    "Training feature count does not match feature_names."
                )

        validated_seed = _integer(seed, label="seed", minimum=0)
        if validated_seed > np.iinfo(np.uint64).max:
            raise BattleModelValidationError("seed must fit in an unsigned 64-bit integer.")
        validated_epochs = _integer(epochs, label="epochs", minimum=1)
        rate = _finite_scalar(learning_rate, label="learning_rate", positive=True)
        regularization = _finite_scalar(l2, label="l2", minimum=0.0)
        scale = _finite_scalar(initialization_scale, label="initialization_scale", minimum=0.0)

        generator = np.random.default_rng(validated_seed)
        weights = generator.normal(0.0, scale, size=len(names)).astype(np.float64)
        first_moment = np.zeros_like(weights)
        second_moment = np.zeros_like(weights)
        beta_one = 0.9
        beta_two = 0.999
        epsilon = 1e-8

        for step in range(1, validated_epochs + 1):
            gradient = np.zeros_like(weights)
            for choice in choices:
                usable = choice.usable_mask
                candidate_features = choice.candidate_features[usable]
                with np.errstate(over="ignore", invalid="ignore"):
                    usable_scores = candidate_features @ weights
                if not np.all(np.isfinite(usable_scores)):
                    raise BattleModelValidationError(
                        "Training produced non-finite candidate scores."
                    )
                probabilities = _softmax(usable_scores)
                gradient += candidate_features.T @ probabilities
                gradient -= choice.candidate_features[choice.chosen_index]

            gradient /= len(choices)
            gradient += regularization * weights
            if not np.all(np.isfinite(gradient)):
                raise BattleModelValidationError("Training produced a non-finite gradient.")

            first_moment = beta_one * first_moment + (1.0 - beta_one) * gradient
            second_moment = beta_two * second_moment + (1.0 - beta_two) * np.square(gradient)
            corrected_first = first_moment / (1.0 - beta_one**step)
            corrected_second = second_moment / (1.0 - beta_two**step)
            weights -= rate * corrected_first / (np.sqrt(corrected_second) + epsilon)
            if not np.all(np.isfinite(weights)):
                raise BattleModelValidationError("Training produced non-finite weights.")

        return cls(
            feature_names=names,
            weights=weights,
            feature_schema_id=CURRENT_BATTLE_FEATURE_SCHEMA_ID,
            training_seed=validated_seed,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe model payload with no executable serialization."""

        return {
            "feature_names": list(self.feature_names),
            "feature_schema_id": self.feature_schema_id,
            "format_version": BATTLE_MODEL_FORMAT_VERSION,
            "model_id": self.model_id,
            "training_seed": self.training_seed,
            "weights": [float(value) for value in self._weights],
        }

    def to_json(self) -> str:
        """Serialize the model to deterministic canonical JSON."""

        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> MaskedLinearMoveRanker:
        """Validate and load a model payload made only of JSON-compatible values."""

        if not isinstance(payload, Mapping):
            raise BattleModelValidationError("Battle model payload must be a JSON object.")
        if set(payload) != _MODEL_FIELDS:
            raise BattleModelValidationError("Battle model payload has missing or unknown fields.")
        if (
            not isinstance(payload["format_version"], int)
            or isinstance(payload["format_version"], bool)
            or payload["format_version"] != BATTLE_MODEL_FORMAT_VERSION
        ):
            raise BattleModelValidationError("Unsupported battle model format version.")
        feature_names = payload["feature_names"]
        weights = payload["weights"]
        if not isinstance(feature_names, list):
            raise BattleModelValidationError("feature_names must be a JSON array.")
        if not isinstance(weights, list):
            raise BattleModelValidationError("weights must be a JSON array.")

        return cls(
            feature_names=feature_names,
            weights=weights,
            feature_schema_id=payload["feature_schema_id"],
            model_id=payload["model_id"],
            training_seed=payload["training_seed"],
        )

    @classmethod
    def from_json(cls, payload: str | bytes | bytearray) -> MaskedLinearMoveRanker:
        """Load strict JSON, rejecting duplicate fields and non-finite constants."""

        if isinstance(payload, (bytes, bytearray)):
            try:
                text = bytes(payload).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise BattleModelValidationError("Battle model JSON must be UTF-8.") from exc
        elif isinstance(payload, str):
            text = payload
        else:
            raise BattleModelValidationError("Battle model JSON must be text or UTF-8 bytes.")

        try:
            decoded = json.loads(
                text,
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BattleModelValidationError("Battle model JSON is invalid.") from exc
        except BattleModelValidationError:
            raise
        return cls.from_dict(decoded)


def choice_accuracy(
    model: BattleMoveScorer,
    examples: Iterable[BattleChoiceExample],
) -> float:
    """Return exact selected-move accuracy over one or more choices."""

    choices = _metric_examples(model, examples)
    correct = sum(
        model.predict(
            choice.candidate_features,
            legal_mask=choice.legal_mask,
            current_pp=choice.current_pp,
        )
        == choice.chosen_index
        for choice in choices
    )
    return correct / len(choices)


def mean_listwise_cross_entropy(
    model: BattleMoveScorer,
    examples: Iterable[BattleChoiceExample],
) -> float:
    """Return mean negative log likelihood of demonstrated legal choices."""

    choices = _metric_examples(model, examples)
    losses: list[float] = []
    for choice in choices:
        scores = model.scores(choice.candidate_features)
        usable_scores = scores[choice.usable_mask]
        maximum = float(np.max(usable_scores))
        shifted = usable_scores - maximum
        chosen_shifted = scores[choice.chosen_index] - maximum
        loss = math.log(float(np.exp(shifted).sum())) - float(chosen_shifted)
        if not math.isfinite(loss):
            raise BattleModelValidationError("Cross-entropy must be finite.")
        losses.append(loss)
    return math.fsum(losses) / len(losses)


def _metric_examples(
    model: BattleMoveScorer,
    examples: Iterable[BattleChoiceExample],
) -> tuple[BattleChoiceExample, ...]:
    if not isinstance(model, BattleMoveScorer):
        raise BattleModelValidationError("Metrics require a battle move scorer.")
    choices = tuple(examples)
    if not choices:
        raise BattleModelValidationError("At least one battle choice is required.")
    for choice in choices:
        if not isinstance(choice, BattleChoiceExample):
            raise BattleModelValidationError("Every metric item must be a BattleChoiceExample.")
        if choice.candidate_features.shape[1] != len(model.feature_names):
            raise BattleModelValidationError(
                "Metric feature count does not match the battle model."
            )
    return choices


def _feature_names(feature_names: Sequence[str]) -> tuple[str, ...]:
    if isinstance(feature_names, (str, bytes)) or not isinstance(feature_names, Sequence):
        raise BattleModelValidationError("feature_names must be a sequence of names.")
    names = tuple(feature_names)
    if not names:
        raise BattleModelValidationError("At least one feature name is required.")
    if any(not isinstance(name, str) or not name or name.strip() != name for name in names):
        raise BattleModelValidationError("Feature names must be non-empty trimmed strings.")
    if len(set(names)) != len(names):
        raise BattleModelValidationError("Feature names must be unique.")
    for name in names:
        final_component = name.lower().replace("-", "_").split(".")[-1]
        if final_component in _FORBIDDEN_SLOT_FEATURES:
            raise BattleModelValidationError(
                "Slot or candidate position may not be used as a model feature."
            )
    return names


def _feature_matrix(
    values: ArrayLike,
    *,
    expected_feature_count: int | None = None,
) -> NDArray[np.float64]:
    raw = np.asarray(values)
    if raw.dtype.kind not in "iuf":
        raise BattleModelValidationError("Candidate features must be numeric.")
    features = np.array(raw, dtype=np.float64, copy=True)
    if features.ndim != 2 or features.shape[0] < 1 or features.shape[1] < 1:
        raise BattleModelValidationError(
            "Candidate features must be a non-empty two-dimensional matrix."
        )
    if expected_feature_count is not None and features.shape[1] != expected_feature_count:
        raise BattleModelValidationError("Candidate feature count does not match the battle model.")
    if not np.all(np.isfinite(features)):
        raise BattleModelValidationError("Candidate features must be finite.")
    return features


def _weight_vector(values: ArrayLike, *, feature_count: int) -> NDArray[np.float64]:
    raw = np.asarray(values)
    if raw.dtype.kind not in "iuf":
        raise BattleModelValidationError("Model weights must be numeric.")
    weights = np.array(raw, dtype=np.float64, copy=True)
    if weights.ndim != 1 or weights.shape[0] != feature_count:
        raise BattleModelValidationError("Model weights must match the feature count.")
    if not np.all(np.isfinite(weights)):
        raise BattleModelValidationError("Model weights must be finite.")
    return weights


def _legal_mask(values: ArrayLike, *, candidate_count: int) -> NDArray[np.bool_]:
    raw = np.asarray(values)
    if raw.dtype.kind != "b" or raw.ndim != 1 or raw.shape[0] != candidate_count:
        raise BattleModelValidationError(
            "legal_mask must be a boolean vector matching the candidates."
        )
    return np.array(raw, dtype=np.bool_, copy=True)


def _pp_vector(values: ArrayLike, *, candidate_count: int) -> NDArray[np.float64]:
    raw = np.asarray(values)
    if raw.dtype.kind not in "iuf":
        raise BattleModelValidationError("current_pp must be numeric.")
    pp = np.array(raw, dtype=np.float64, copy=True)
    if pp.ndim != 1 or pp.shape[0] != candidate_count:
        raise BattleModelValidationError("current_pp must match the candidates.")
    if not np.all(np.isfinite(pp)) or np.any(pp < 0) or np.any(pp != np.floor(pp)):
        raise BattleModelValidationError(
            "current_pp must contain finite non-negative whole numbers."
        )
    return pp


def _usable_mask(
    legal_mask: ArrayLike,
    current_pp: ArrayLike,
    *,
    candidate_count: int,
) -> NDArray[np.bool_]:
    legal = _legal_mask(legal_mask, candidate_count=candidate_count)
    pp = _pp_vector(current_pp, candidate_count=candidate_count)
    usable = legal & (pp > 0)
    if not np.any(usable):
        raise BattleModelValidationError("At least one legal move with positive PP is required.")
    return usable


def _softmax(scores: NDArray[np.float64]) -> NDArray[np.float64]:
    maximum = float(np.max(scores))
    shifted = scores - maximum
    exponentials = np.exp(shifted)
    total = float(exponentials.sum())
    if not math.isfinite(total) or total <= 0:
        raise BattleModelValidationError("Softmax normalization must be finite and positive.")
    return exponentials / total


def _masked_softmax(
    scores: NDArray[np.float64],
    usable: NDArray[np.bool_],
) -> NDArray[np.float64]:
    probabilities = np.zeros(scores.shape, dtype=np.float64)
    probabilities[usable] = _softmax(scores[usable])
    return probabilities


def _finite_scalar(
    value: float,
    *,
    label: str,
    positive: bool = False,
    minimum: float | None = None,
) -> float:
    if isinstance(value, bool):
        raise BattleModelValidationError(f"{label} must be a finite number.")
    try:
        converted = float(value)
    except (TypeError, ValueError) as exc:
        raise BattleModelValidationError(f"{label} must be a finite number.") from exc
    if not math.isfinite(converted):
        raise BattleModelValidationError(f"{label} must be a finite number.")
    if positive and converted <= 0:
        raise BattleModelValidationError(f"{label} must be greater than zero.")
    if minimum is not None and converted < minimum:
        raise BattleModelValidationError(f"{label} must be at least {minimum}.")
    return converted


def _integer(value: int, *, label: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise BattleModelValidationError(f"{label} must be an integer.")
    converted = int(value)
    if converted < minimum:
        raise BattleModelValidationError(f"{label} must be at least {minimum}.")
    return converted


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BattleModelValidationError("Battle model JSON contains a duplicate field.")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    raise BattleModelValidationError(f"Battle model JSON contains invalid constant {value}.")
