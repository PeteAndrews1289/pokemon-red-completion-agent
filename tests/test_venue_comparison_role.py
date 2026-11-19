"""Rejected fits may be diagnosed without becoming accepted or admitted."""

import json
from hashlib import sha256

import pytest

from pokemon_red_completion.red_teacher_venue import _comparison_only_venue_fit


def fixture(tmp_path):
    fit = dict(passed=True, accepted=False, model_sha256="a" * 64)
    fp = tmp_path / "fit.json"
    fp.write_text(json.dumps(fit))
    scope = dict(
        schema="pokemon.red.venue-candidate-comparison-only.v1",
        fit_result_sha256=sha256(fp.read_bytes()).hexdigest(),
        model_sha256=fit["model_sha256"],
        source_state_sha256="b" * 64,
        training_accepted=False,
        broad_adoption=False,
        fitting_forbidden=True,
    )
    p = tmp_path / "comparison.json"
    p.write_text(json.dumps(scope))
    plan = dict(
        validation_role="exposed-TRAIN-component-comparison-only",
        comparison_authorization=str(p),
        pins={str(p): sha256(p.read_bytes()).hexdigest()},
        fit_allowed=False,
        party_venue_fit_eligible=False,
        diagnostic_only=True,
        copy_back=False,
        campaign_writes=False,
    )
    return plan, fp, fit, p, scope


def test_comparison_leaves_rejected_fit_and_admission_unchanged(tmp_path):
    plan, fp, fit, _, _ = fixture(tmp_path)
    before = fp.read_bytes()
    assert _comparison_only_venue_fit(plan, fp, fit, "b" * 64)
    assert (
        fp.read_bytes() == before and not fit["accepted"] and not plan["party_venue_fit_eligible"]
    )


def test_legacy_validation_does_not_gain_permission(tmp_path):
    plan, fp, fit, _, _ = fixture(tmp_path)
    plan["validation_role"] = "exposed-TRAIN-component-no-admission"
    assert _comparison_only_venue_fit(plan, fp, fit, "b" * 64) is False


@pytest.mark.parametrize(
    "fault",
    [
        "unpin",
        "source",
        "head",
        "adoption",
        "fit_permission",
        "admission",
        "copyback",
        "failed_fit",
    ],
)
def test_comparison_cannot_bypass_native_scope_or_fitting_guards(tmp_path, fault):
    plan, fp, fit, p, scope = fixture(tmp_path)
    if fault == "unpin":
        plan["pins"] = {}
    if fault == "source":
        scope["source_state_sha256"] = "c" * 64
    if fault == "head":
        scope["model_sha256"] = "c" * 64
    if fault == "adoption":
        scope["broad_adoption"] = True
    if fault == "fit_permission":
        plan["fit_allowed"] = True
    if fault == "admission":
        plan["party_venue_fit_eligible"] = True
    if fault == "copyback":
        plan["copy_back"] = True
    if fault == "failed_fit":
        fit["passed"] = False
    if fault not in ("unpin", "failed_fit"):
        p.write_text(json.dumps(scope))
        plan["pins"][str(p)] = sha256(p.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        _comparison_only_venue_fit(plan, fp, fit, "b" * 64)
