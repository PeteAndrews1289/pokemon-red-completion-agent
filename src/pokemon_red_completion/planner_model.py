"""Small game-neutral listwise ranker for semantic objectives."""

from __future__ import annotations

import hashlib
import json
import math
import stat
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

import numpy as np
from numpy.typing import ArrayLike, NDArray

PLANNER_MODEL_ID = "pokemon.core.planning.masked-linear-ranker.v1"


class PlannerModelError(ValueError):
    pass


class ObjectiveRanker:
    def __init__(
        self,
        *,
        feature_names: Sequence[str],
        weights: ArrayLike,
        training_seed: int = 0,
    ) -> None:
        self.feature_names = tuple(feature_names)
        values = np.asarray(weights, dtype=np.float64)
        if values.shape != (len(self.feature_names),) or not np.all(np.isfinite(values)):
            raise PlannerModelError("planner weights do not match the feature schema")
        if type(training_seed) is not int or training_seed < 0:  # noqa: E721
            raise PlannerModelError("training seed must be a non-negative integer")
        values.setflags(write=False)
        self._weights = values
        self.training_seed = training_seed

    @property
    def weights(self) -> NDArray[np.float64]:
        return self._weights.copy()

    def probabilities(self, candidate_features: ArrayLike) -> NDArray[np.float64]:
        matrix = np.asarray(candidate_features, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[1] != len(self.feature_names):
            raise PlannerModelError("planner candidate matrix has an invalid shape")
        scores = matrix @ self._weights
        scores -= np.max(scores)
        probabilities = np.exp(scores)
        probabilities /= np.sum(probabilities)
        return probabilities

    def predict(self, candidate_features: ArrayLike) -> int:
        return int(np.argmax(self.probabilities(candidate_features)))

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": 1,
            "model_id": PLANNER_MODEL_ID,
            "training_seed": self.training_seed,
            "feature_names": list(self.feature_names),
            "weights": [float(value) for value in self._weights],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ObjectiveRanker:
        if (
            value.get("format_version") != 1
            or value.get("model_id") != PLANNER_MODEL_ID
        ):
            raise PlannerModelError("planner model identity is unsupported")
        try:
            return cls(
                feature_names=value["feature_names"],  # type: ignore[arg-type]
                weights=value["weights"],
                training_seed=value["training_seed"],  # type: ignore[arg-type]
            )
        except (KeyError, TypeError, ValueError) as error:
            raise PlannerModelError("planner model payload is invalid") from error

    @classmethod
    def fit(
        cls,
        *,
        feature_names: Sequence[str],
        examples: Iterable[tuple[ArrayLike, int]],
        seed: int = 0,
        epochs: int = 2500,
        learning_rate: float = 0.05,
        l2: float = 1e-4,
    ) -> ObjectiveRanker:
        rows = tuple(examples)
        if not rows:
            raise PlannerModelError("planner training requires examples")
        generator = np.random.default_rng(seed)
        weights = generator.normal(0.0, 1e-3, len(tuple(feature_names)))
        first = np.zeros_like(weights)
        second = np.zeros_like(weights)
        for epoch in range(1, epochs + 1):
            gradient = l2 * weights
            for candidate_features, chosen_index in rows:
                matrix = np.asarray(candidate_features, dtype=np.float64)
                if matrix.ndim != 2 or matrix.shape[1] != len(weights):
                    raise PlannerModelError("training matrix has an invalid shape")
                if not 0 <= chosen_index < matrix.shape[0]:
                    raise PlannerModelError("chosen objective index is invalid")
                scores = matrix @ weights
                scores -= np.max(scores)
                probabilities = np.exp(scores)
                probabilities /= np.sum(probabilities)
                probabilities[chosen_index] -= 1.0
                gradient += matrix.T @ probabilities / len(rows)
            first = 0.9 * first + 0.1 * gradient
            second = 0.999 * second + 0.001 * (gradient * gradient)
            corrected_first = first / (1.0 - math.pow(0.9, epoch))
            corrected_second = second / (1.0 - math.pow(0.999, epoch))
            weights -= learning_rate * corrected_first / (np.sqrt(corrected_second) + 1e-8)
        return cls(feature_names=feature_names, weights=weights, training_seed=seed)


def planner_accuracy(
    model: ObjectiveRanker,
    examples: Iterable[tuple[ArrayLike, int]],
) -> float:
    rows = tuple(examples)
    if not rows:
        raise PlannerModelError("planner evaluation requires examples")
    correct = sum(model.predict(features) == chosen for features, chosen in rows)
    return correct / len(rows)


def load_objective_model_artifact(
    artifact_directory: str | Path,
    *,
    expected_feature_names: Sequence[str],
    expected_objective_graph_sha256: str,
) -> ObjectiveRanker:
    """Authenticate a finalized private objective-model artifact."""

    root = Path(artifact_directory)
    manifest_path = root / "manifest.json"
    if root.is_symlink() or not root.is_dir() or manifest_path.is_symlink():
        raise PlannerModelError("planner model artifact is not a regular directory")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PlannerModelError("planner model manifest cannot be read") from error
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("format") != "pokemon-red-completion-private-artifact-jsonl"
        or manifest.get("kind") != "planner_model"
        or manifest.get("schema_version") != 1
        or manifest.get("status") != "complete"
    ):
        raise PlannerModelError("planner model artifact is not complete and typed")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise PlannerModelError("planner model file inventory is absent")
    entries = {
        str(entry.get("filename")): entry
        for entry in files
        if isinstance(entry, Mapping) and isinstance(entry.get("filename"), str)
    }
    expected_files = {"model.jsonl", "training.jsonl", "metrics.jsonl"}
    if set(entries) != expected_files or len(entries) != len(files):
        raise PlannerModelError("planner model file inventory is invalid")
    rows: dict[str, tuple[Mapping[str, object], ...]] = {}
    for filename, entry in entries.items():
        path = root / filename
        try:
            metadata = path.lstat()
            payload = path.read_bytes()
        except OSError as error:
            raise PlannerModelError("planner model stream cannot be read") from error
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or entry.get("bytes") != len(payload)
            or entry.get("sha256") != hashlib.sha256(payload).hexdigest()
        ):
            raise PlannerModelError("planner model stream failed authentication")
        parsed = _canonical_records(payload)
        if entry.get("records") != len(parsed):
            raise PlannerModelError("planner model record count is invalid")
        rows[filename] = parsed
    if any(len(value) != 1 for value in rows.values()):
        raise PlannerModelError("planner model streams must contain one record each")
    record = rows["model.jsonl"][0]
    model_payload = record.get("model")
    if (
        record.get("record_type") != "planner_model"
        or not isinstance(model_payload, Mapping)
        or record.get("model_sha256") != _canonical_sha256(model_payload)
        or record.get("objective_graph_sha256") != expected_objective_graph_sha256
    ):
        raise PlannerModelError("planner model record is invalid or graph-incompatible")
    model = ObjectiveRanker.from_dict(model_payload)
    if model.feature_names != tuple(expected_feature_names):
        raise PlannerModelError("planner model feature schema is incompatible")
    return model


def _canonical_records(payload: bytes) -> tuple[Mapping[str, object], ...]:
    try:
        text = payload.decode("ascii")
    except UnicodeError as error:
        raise PlannerModelError("planner model stream is not ASCII") from error
    if not text or not text.endswith("\n"):
        raise PlannerModelError("planner model stream is not canonical JSONL")
    result: list[Mapping[str, object]] = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise PlannerModelError("planner model stream contains invalid JSON") from error
        if not isinstance(value, Mapping) or line != json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ):
            raise PlannerModelError("planner model stream is not canonical JSONL")
        result.append(value)
    return tuple(result)


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    ).hexdigest()
