from __future__ import annotations

import math

import pytest

from pokemon_red_completion.living_dex_calibration_audit import (
    LivingDexCalibrationAuditError,
    LivingDexSuccessPrediction,
    audit_living_dex_success_predictions,
)


def test_audits_overall_and_per_kind_proper_scores() -> None:
    audit = audit_living_dex_success_predictions(
        (
            LivingDexSuccessPrediction("acquire", 0.9, True),
            LivingDexSuccessPrediction("acquire", 0.8, False),
            LivingDexSuccessPrediction("develop", 0.2, True),
        )
    )

    assert audit.overall.observations == 3
    assert audit.overall.successes == 2
    assert audit.overall.mean_prediction == pytest.approx(1.9 / 3.0)
    assert audit.overall.observed_success_rate == pytest.approx(2.0 / 3.0)
    assert audit.overall.signed_calibration_error == pytest.approx(-1.0 / 30.0)
    assert audit.overall.brier_score == pytest.approx(0.43)
    assert audit.overall.threshold_accuracy == pytest.approx(1.0 / 3.0)
    assert audit.overall.clipped_log_loss == pytest.approx(
        -(math.log(0.9) + math.log(0.2) + math.log(0.2)) / 3.0
    )
    by_kind = dict(audit.per_kind)
    assert tuple(by_kind) == ("acquire", "develop")
    assert by_kind["acquire"].observations == 2
    assert by_kind["develop"].brier_score == pytest.approx(0.64)


def test_exact_endpoint_probability_uses_declared_log_loss_clip() -> None:
    audit = audit_living_dex_success_predictions(
        (LivingDexSuccessPrediction("acquire", 1.0, False),),
        log_loss_epsilon=1e-6,
    )

    assert audit.overall.brier_score == 1.0
    assert audit.overall.clipped_log_loss == pytest.approx(-math.log(1e-6))
    assert audit.log_loss_epsilon == 1e-6


@pytest.mark.parametrize("value", (-0.1, 1.1, math.inf, math.nan, True))
def test_rejects_invalid_probabilities(value: float) -> None:
    with pytest.raises(LivingDexCalibrationAuditError):
        LivingDexSuccessPrediction("acquire", value, True)


def test_rejects_empty_or_invalid_audit_inputs() -> None:
    with pytest.raises(LivingDexCalibrationAuditError, match="empty"):
        audit_living_dex_success_predictions(())
    with pytest.raises(TypeError, match="rows differ"):
        audit_living_dex_success_predictions((object(),))  # type: ignore[arg-type]
    with pytest.raises(LivingDexCalibrationAuditError, match="epsilon"):
        audit_living_dex_success_predictions(
            (LivingDexSuccessPrediction("acquire", 0.5, True),),
            log_loss_epsilon=0.5,
        )
