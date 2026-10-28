"""Separate masked continuation regression for the prospective sequence trial.

This numerical core is not native data admission or live policy activation.
The caller must independently authenticate sources and target channels before a
real fit. Reconstructed collector records alone are explicitly not sufficient.
Legacy immediate-outcome models, targets and economy heads are never modified.
"""

import math
from dataclasses import astuple, dataclass
from typing import Any

import numpy as np

from .living_dex_option_value import LivingDexOptionMenu, option_feature_names
from .player_sequence_targets import SEQUENCE_TARGET_CONTRACT, SEQUENCE_TARGET_NAMES
from .provenance import canonical_sha256
from .recorded_branch_history import RecordedBranchHistory

FEATURE_CONTRACT = "v6-candidate-plus-eight-observed-branch-history-values-v1"
FEATURE_WIDTH = len(option_feature_names(6)) + 8
TARGET_WIDTH = len(SEQUENCE_TARGET_NAMES)


def _vector(values: Any, width: int, *, bounded: bool = False,
            signed: bool = False) -> tuple[float, ...]:
    if (type(values) is not tuple or len(values) != width
        or any(type(v) not in (int, float) or not math.isfinite(v)
               or (bounded and not (-1 if signed else 0) <= v <= 1) for v in values)):
        raise ValueError("sequence numeric vector differs")
    return values


@dataclass(frozen=True)
class SequenceRegressionRow:
    """Numerical input with a checked partition, not an admission certificate."""

    window_sha256: str
    features: tuple[float, ...]
    targets: tuple[float | None, ...]
    partition: str

    def __post_init__(self) -> None:
        if (type(self.window_sha256) is not str or len(self.window_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.window_sha256)
            or self.partition not in {"train", "development"}):
            raise ValueError("sequence regression row identity differs")
        _vector(self.features, FEATURE_WIDTH, bounded=True, signed=True)
        if type(self.targets) is not tuple or len(self.targets) != TARGET_WIDTH:
            raise ValueError("sequence target width differs")
        _vector(tuple(v for v in self.targets if v is not None),
                sum(v is not None for v in self.targets), bounded=True)


@dataclass(frozen=True)
class SequenceValueHead:
    """Immutable per-channel parameters; unknown channels stay unknown."""

    parameters: tuple[tuple[float, ...] | None, ...]
    sample_counts: tuple[int, ...]
    dataset_sha256: str
    ridge: float
    horizon: int
    behavior_model_sha256: str

    def __post_init__(self) -> None:
        if (type(self.parameters) is not tuple or len(self.parameters) != TARGET_WIDTH
            or type(self.sample_counts) is not tuple or len(self.sample_counts) != TARGET_WIDTH
            or type(self.horizon) is not int or not 1 <= self.horizon <= 4
            or type(self.ridge) not in (int, float) or not math.isfinite(self.ridge)
            or self.ridge <= 0):
            raise ValueError("sequence value contract differs")
        for digest in (self.dataset_sha256, self.behavior_model_sha256):
            if type(digest) is not str or len(digest) != 64 or any(
                c not in "0123456789abcdef" for c in digest
            ):
                raise ValueError("sequence value identity differs")
        for row, n in zip(self.parameters, self.sample_counts, strict=True):
            if type(n) is not int or n < 0 or (row is None) != (n == 0) or n == 1:
                raise ValueError("sequence channel needs zero or at least two measured rows")
            if row is not None:
                _vector(row, FEATURE_WIDTH + 1)

    def document(self) -> dict[str, Any]:
        return dict(
            schema="pokemon.player.masked-sequence-value.v1", feature_contract=FEATURE_CONTRACT,
            target_contract=SEQUENCE_TARGET_CONTRACT, target_names=SEQUENCE_TARGET_NAMES,
            parameters=self.parameters, sample_counts=self.sample_counts,
            dataset_sha256=self.dataset_sha256, ridge=self.ridge, horizon=self.horizon,
            behavior_model_sha256=self.behavior_model_sha256,
            objective="observed-behavior-conditional-sequence-ridge-v1",
            native_admission_verified=False, live_policy_adopted=False,
        )

    @property
    def model_sha256(self) -> str:
        return canonical_sha256(self.document())

    @classmethod
    def from_document(
        cls, document: dict[str, Any], *, expected_sha256: str,
    ) -> "SequenceValueHead":
        """Reopen exact frozen parameters, not an adoption or provenance claim."""
        if type(document) is not dict or canonical_sha256(document) != expected_sha256:
            raise ValueError("sequence value document identity differs")
        head = cls(
            tuple(None if row is None else tuple(row) for row in document["parameters"]),
            tuple(document["sample_counts"]), document["dataset_sha256"], document["ridge"],
            document["horizon"], document["behavior_model_sha256"],
        )
        if canonical_sha256(head.document()) != expected_sha256:
            raise ValueError("sequence value document contract differs")
        return head

    def predict(self, features: tuple[float, ...]) -> tuple[float | None, ...]:
        _vector(features, FEATURE_WIDTH, bounded=True, signed=True)
        return tuple(None if row is None else max(0., min(1., row[0] + math.fsum(
            weight * value for weight, value in zip(row[1:], features, strict=True)
        ))) for row in self.parameters)

    def score(self, features: tuple[float, ...], *, utility: tuple[float, ...]) -> float:
        """Explicit prospective utility; never treat unknown losses as zero loss."""
        _vector(utility, TARGET_WIDTH)
        if not any(utility):
            raise ValueError("sequence utility must use a measured outcome")
        values = self.predict(features)
        if any(weight != 0 and value is None
               for weight, value in zip(utility, values, strict=True)):
            raise ValueError("sequence utility requires an unlearned outcome channel")
        return math.fsum(weight * value for weight, value in zip(utility, values, strict=True)
                         if value is not None)

    def score_menu(self, menu: LivingDexOptionMenu, *,
                   histories: tuple[RecordedBranchHistory, ...],
                   utility: tuple[float, ...]) -> tuple[float | None, ...]:
        """Action-free candidate scores, no sampling, forced action or live override."""
        if (not isinstance(menu, LivingDexOptionMenu) or type(histories) is not tuple
            or len(histories) != len(menu.candidates)
            or any(type(h) is not RecordedBranchHistory for h in histories)
            or any(type(n) is not int or n < 0 for h in histories for n in astuple(h))):
            raise ValueError("sequence scoring requires one pre-choice history per candidate")
        return tuple(self.score(
            candidate.vector(menu.context, feature_version=6) + history.vector(), utility=utility,
        ) if i in menu.available_indices else None
            for i, (candidate, history) in enumerate(zip(menu.candidates, histories, strict=True)))


def fit_sequence_value(rows: tuple[SequenceRegressionRow, ...], *, ridge: float,
                       horizon: int, behavior_model_sha256: str) -> SequenceValueHead:
    """Numerical TRAIN-only fit; native provenance/admission must precede this call.

    Fit each channel only on its measured rows. Censored/all-unknown rows never
    supply zeros or affect normalization. No importance/causal credit is claimed:
    continuations were observed under the separately pinned behavior policy.
    """
    if (type(rows) is not tuple or not rows
        or any(type(row) is not SequenceRegressionRow or row.partition != "train" for row in rows)
        or len({row.window_sha256 for row in rows}) != len(rows)
        or type(ridge) not in (int, float) or not math.isfinite(ridge) or ridge <= 0):
        raise ValueError("sequence fit requires distinct TRAIN windows and positive ridge")
    for row in rows:
        row.__post_init__()
    parameters: list[tuple[float, ...] | None] = []
    counts: list[int] = []
    for channel in range(TARGET_WIDTH):
        observed = tuple(row for row in rows if row.targets[channel] is not None)
        counts.append(len(observed))
        if not observed:
            parameters.append(None)
            continue
        if len(observed) < 2:
            raise ValueError("sequence channel has fewer than two measured rows")
        features = np.asarray([r.features for r in observed], dtype=np.float64)
        targets = np.asarray([r.targets[channel] for r in observed], dtype=np.float64)
        mean, scale = features.mean(axis=0), features.std(axis=0)
        scale = np.where(scale < 1e-12, 1., scale)
        normalized = (features - mean) / scale
        target_mean = float(targets.mean())
        # Dual ridge keeps a small bounded pilot's solve proportional to rows,
        # not the much larger feature width. The centered intercept is unpenalized.
        alpha = np.linalg.solve(normalized @ normalized.T + ridge * np.eye(len(observed)),
                                targets - target_mean)
        weights = (normalized.T @ alpha) / scale
        intercept = target_mean - float(mean @ weights)
        parameters.append((intercept, *(float(v) for v in weights)))
    if not any(counts):
        raise ValueError("sequence fit has no measured channels")
    dataset = canonical_sha256([dict(window=r.window_sha256, features=r.features,
                                    targets=r.targets, partition=r.partition) for r in rows])
    return SequenceValueHead(tuple(parameters), tuple(counts), dataset, float(ridge),
                             horizon, behavior_model_sha256)
