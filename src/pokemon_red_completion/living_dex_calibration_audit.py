"""Proper-score diagnostics for shadow living-Pokedex success predictions.

This module intentionally evaluates only already-recorded Bernoulli predictions.
It cannot choose an action, fit a model, manufacture a counterfactual target, or
promote authority.  The small reusable boundary lets development evidence expose
extreme confidence errors without coupling the calculation to Red or any private
scenario identity.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

DEFAULT_LOG_LOSS_EPSILON = 1e-15


class LivingDexCalibrationAuditError(ValueError):
    """Recorded success predictions cannot support a calibration diagnostic."""


@dataclass(frozen=True, slots=True)
class LivingDexSuccessPrediction:
    """One identity-free committed probability and its factual selected-arm result."""

    option_kind: str
    predicted_success: float
    verified_success: bool

    def __post_init__(self) -> None:
        if not isinstance(self.option_kind, str) or not self.option_kind:
            raise LivingDexCalibrationAuditError("option kind is invalid")
        if isinstance(self.predicted_success, bool) or not isinstance(
            self.predicted_success,
            (int, float),
        ):
            raise LivingDexCalibrationAuditError("success prediction is not numeric")
        probability = float(self.predicted_success)
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise LivingDexCalibrationAuditError("success prediction is outside [0, 1]")
        if type(self.verified_success) is not bool:  # noqa: E721
            raise LivingDexCalibrationAuditError("verified success is not boolean")
        object.__setattr__(self, "predicted_success", probability)


@dataclass(frozen=True, slots=True)
class LivingDexCalibrationMetrics:
    """Path-free proper scores for one fixed group of predictions."""

    observations: int
    successes: int
    mean_prediction: float
    observed_success_rate: float
    signed_calibration_error: float
    brier_score: float
    clipped_log_loss: float
    threshold_accuracy: float

    def public_dict(self) -> dict[str, object]:
        return {
            "brier_score": self.brier_score,
            "clipped_log_loss": self.clipped_log_loss,
            "mean_prediction": self.mean_prediction,
            "observations": self.observations,
            "observed_success_rate": self.observed_success_rate,
            "signed_calibration_error": self.signed_calibration_error,
            "successes": self.successes,
            "threshold_accuracy_at_0_5": self.threshold_accuracy,
        }


@dataclass(frozen=True, slots=True)
class LivingDexCalibrationAudit:
    """Overall and semantic-kind diagnostics over one immutable observation set."""

    overall: LivingDexCalibrationMetrics
    per_kind: tuple[tuple[str, LivingDexCalibrationMetrics], ...]
    log_loss_epsilon: float

    def public_dict(self) -> dict[str, object]:
        return {
            "log_loss_epsilon": self.log_loss_epsilon,
            "overall": self.overall.public_dict(),
            "per_option_kind": {
                kind: metrics.public_dict() for kind, metrics in self.per_kind
            },
        }


def audit_living_dex_success_predictions(
    observations: Iterable[LivingDexSuccessPrediction],
    *,
    log_loss_epsilon: float = DEFAULT_LOG_LOSS_EPSILON,
) -> LivingDexCalibrationAudit:
    """Calculate proper scores without interpreting a small sample as model quality."""

    rows = tuple(observations)
    if not rows:
        raise LivingDexCalibrationAuditError("calibration evidence is empty")
    if any(not isinstance(row, LivingDexSuccessPrediction) for row in rows):
        raise TypeError("calibration evidence rows differ")
    if isinstance(log_loss_epsilon, bool) or not isinstance(
        log_loss_epsilon,
        (int, float),
    ):
        raise LivingDexCalibrationAuditError("log-loss epsilon is not numeric")
    epsilon = float(log_loss_epsilon)
    if not math.isfinite(epsilon) or not 0.0 < epsilon < 0.5:
        raise LivingDexCalibrationAuditError("log-loss epsilon is invalid")

    grouped: dict[str, list[LivingDexSuccessPrediction]] = defaultdict(list)
    for row in rows:
        grouped[row.option_kind].append(row)
    return LivingDexCalibrationAudit(
        overall=_metrics(rows, epsilon=epsilon),
        per_kind=tuple(
            (kind, _metrics(tuple(grouped[kind]), epsilon=epsilon))
            for kind in sorted(grouped)
        ),
        log_loss_epsilon=epsilon,
    )


def _metrics(
    rows: tuple[LivingDexSuccessPrediction, ...],
    *,
    epsilon: float,
) -> LivingDexCalibrationMetrics:
    targets = tuple(float(row.verified_success) for row in rows)
    predictions = tuple(row.predicted_success for row in rows)
    count = len(rows)
    # ``math.fsum`` keeps the public evidence byte-stable across the supported
    # Python/macOS and Python/Linux runtimes.  Built-in ``sum`` can expose a
    # one-ULP platform difference for repeated probabilities such as 0.8.
    mean_prediction = math.fsum(predictions) / count
    observed_rate = math.fsum(targets) / count
    clipped = tuple(min(1.0 - epsilon, max(epsilon, value)) for value in predictions)
    log_loss = -math.fsum(
        target * math.log(probability)
        + (1.0 - target) * math.log(1.0 - probability)
        for target, probability in zip(targets, clipped, strict=True)
    ) / count
    return LivingDexCalibrationMetrics(
        observations=count,
        successes=int(math.fsum(targets)),
        mean_prediction=mean_prediction,
        observed_success_rate=observed_rate,
        signed_calibration_error=mean_prediction - observed_rate,
        brier_score=math.fsum(
            (prediction - target) ** 2
            for prediction, target in zip(predictions, targets, strict=True)
        )
        / count,
        clipped_log_loss=log_loss,
        threshold_accuracy=math.fsum(
            (prediction >= 0.5) == bool(target)
            for prediction, target in zip(predictions, targets, strict=True)
        )
        / count,
    )


__all__ = [
    "DEFAULT_LOG_LOSS_EPSILON",
    "LivingDexCalibrationAudit",
    "LivingDexCalibrationAuditError",
    "LivingDexCalibrationMetrics",
    "LivingDexSuccessPrediction",
    "audit_living_dex_success_predictions",
]
