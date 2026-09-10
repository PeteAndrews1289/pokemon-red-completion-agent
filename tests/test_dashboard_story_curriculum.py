"""Guided outcomes must never become invented sampled choices in the overview."""

import json
from pathlib import Path

import pytest
from run_product_focus_dashboard import _native_training_projection

ROOT = Path(__file__).resolve().parents[1]


def _evidence():
    value = json.loads(
        (ROOT / "docs/evidence/red-bruno-support-2026-09-09-dashboard.json").read_text()
    )
    value["curriculum_contract"] = "forced-singleton-story-outcome-unit-weight-v1"
    episode, fit = value["completed_episode"], value["fit"]
    episode.update(sampled_choices=0, curriculum_outcomes=1)
    fit.update(
        curriculum_outcomes=1,
        comparative_choice_outcomes=77,
        curriculum_is_comparative_evidence=False,
    )
    fit["fit_report"]["objective"] = "selected-arm-ips-plus-unit-curriculum-multioutcome-ridge-v1"
    return value


def test_curriculum_counts_as_one_outcome_and_zero_sampled_choices():
    evidence = _evidence()
    state, component = _native_training_projection(evidence)
    assert state.newly_collected == 1
    assert state.samples_after == 78
    assert evidence["completed_episode"]["sampled_choices"] == 0
    assert "guided outcomes" in component.scope
    assert component.independent_validation_units == 0


def test_unperformed_choice_comparison_is_unknown_not_measured_zero():
    evidence = _evidence()
    evidence["in_sample_policy_replay"].update(performed=False, choices=[])
    state, _ = _native_training_projection(evidence)
    assert state.training_choice_changes is None
    assert state.public_dict()["training_choice_changes"] is None
    evidence["in_sample_policy_replay"]["choices"] = [{"prior_greedy": "a", "updated_greedy": "a"}]
    with pytest.raises(ValueError):
        _native_training_projection(evidence)


@pytest.mark.parametrize(
    "damage",
    ["double_count", "contract", "comparative", "total", "objective", "boolean", "missing_count"],
)
def test_curriculum_display_rejects_false_accounting(damage):
    evidence = _evidence()
    if damage == "double_count":
        evidence["completed_episode"]["sampled_choices"] = 1
    elif damage == "contract":
        evidence["curriculum_contract"] = "undeclared"
    elif damage == "comparative":
        evidence["fit"]["curriculum_is_comparative_evidence"] = True
    elif damage == "total":
        evidence["fit"]["comparative_choice_outcomes"] += 1
    elif damage == "objective":
        evidence["fit"]["fit_report"]["objective"] = "selected-arm-capped-ips-multioutcome-ridge-v1"
    elif damage == "boolean":
        evidence["completed_episode"]["curriculum_outcomes"] = True
    else:
        evidence["completed_episode"].pop("curriculum_outcomes")
    with pytest.raises(ValueError):
        _native_training_projection(evidence)
