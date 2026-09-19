import copy
import json
from pathlib import Path

import pytest
from run_product_focus_dashboard import _native_training_projection

from pokemon_red_completion.progress_dashboard import ProgressDashboardError

ROOT = Path(__file__).resolve().parents[1]


def receipt():
    return json.loads((ROOT / "docs/evidence/red-model135-opportunity-discovery-2026-09-16.json")
                      .read_text())


def test_autonomous_receipt_retains_measured_not_native_or_replay_claims():
    evidence = receipt()
    original = copy.deepcopy(evidence)
    training, component = _native_training_projection(evidence)
    assert training.samples_after == 135 and training.newly_collected == 1
    assert training.training_choice_changes is None
    assert "no native action trace" in component.scope
    assert component.independent_validation_units == 0
    assert evidence == original


@pytest.mark.parametrize("path,value", [
    (("fit", "new_settled_examples"), 2),
    (("fit", "model", "source_commit"), "0" * 40),
    (("fit", "model", "source_bundle_sha256"), "0" * 64),
    (("autonomous_outcome", "choice", "model_sha256"), "0" * 64),
    (("autonomous_outcome", "choice", "teacher_labels"), 1),
    (("autonomous_outcome", "learning_eligible"), False),
    (("autonomous_outcome", "safe_terminal"), False),
    (("fit", "fit_report", "settled_examples"), 136),
    (("fit", "prior_rows_retained"), False),
    (("fit", "measured_evidence_action_trace_available"), True),
    (("boundaries", "independent_evaluation"), True),
])
def test_autonomous_projection_rejects_false_or_mismatched_claims(path, value):
    evidence = receipt()
    target = evidence
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ProgressDashboardError, match="boundary differs"):
        _native_training_projection(evidence)
