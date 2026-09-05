from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    PROJECT_ROOT / "scripts/audit_red_repeatable_living_dex_five_case_calibration.py"
)
EVIDENCE_PATH = (
    PROJECT_ROOT
    / "docs/evidence/red-repeatable-living-dex-five-case-calibration-audit-v1-2026-09-05.json"
)
SPEC = importlib.util.spec_from_file_location("five_case_calibration_audit_script", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(script)


def test_public_audit_reproduces_five_committed_outcomes() -> None:
    result = script.build_public_audit()

    assert result["status"] == "five_case_development_calibration_audited_action_free"
    assert [row["verified_success"] for row in result["cases"]] == [
        True,
        False,
        True,
        True,
        True,
    ]
    diagnostic = result["diagnostic"]
    assert diagnostic["overall"]["observations"] == 5
    assert diagnostic["overall"]["brier_score"] == pytest.approx(0.3978108626366309)
    assert diagnostic["overall"]["clipped_log_loss"] == pytest.approx(
        2.458978676252554
    )
    assert diagnostic["overall"]["threshold_accuracy_at_0_5"] == 0.6
    assert diagnostic["per_option_kind"]["develop_team"]["brier_score"] == pytest.approx(
        0.99793789331786
    )
    assert result["effects"] == {
        "authority_promotions": 0,
        "controller_actions": 0,
        "crystal_accesses": 0,
        "development_examples_read_for_fit": 0,
        "emulator_frames": 0,
        "model_fits": 0,
        "new_model_predictions": 0,
        "outcomes_opened": 0,
        "teacher_queries": 0,
        "training_targets_emitted": 0,
    }
    encoded = json.dumps(result, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_post_hoc_constant_is_never_claimed_as_a_control() -> None:
    result = script.build_public_audit()
    comparator = result["post_hoc_constant_rate_diagnostic"]

    assert comparator["probability"] == 0.8
    assert comparator["metrics"]["brier_score"] == pytest.approx(0.16)
    assert comparator["metrics"]["clipped_log_loss"] == pytest.approx(
        0.5004024235381879
    )
    assert not comparator["comparator_chosen_before_outcomes"]
    assert not comparator["eligible_for_advantage_claim"]


def test_public_audit_fails_closed_if_an_input_digest_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(script, "FIRST_TWO_SHA256", "0" * 64)

    with pytest.raises(script.FiveCaseCalibrationAuditError, match="identity"):
        script.build_public_audit()


def test_cli_emits_canonical_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert script.main([]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value == script.build_public_audit()


def test_tracked_evidence_exactly_matches_reproducible_audit() -> None:
    assert json.loads(EVIDENCE_PATH.read_text(encoding="ascii")) == (
        script.build_public_audit()
    )
