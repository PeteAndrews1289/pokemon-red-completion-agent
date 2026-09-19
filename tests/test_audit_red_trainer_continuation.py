import pytest
from audit_red_trainer_continuation import preference_comparison


def target(returns, refs=("move1", "switch2")):
    return {
        "capture_id": "train-case",
        "heads": {"control": {"returns": returns, "choice_refs": refs}},
    }


def test_continuation_diagnostic_preserves_ties_and_detects_reversal():
    assert preference_comparison(target([2.0, 1.0]), target([1.0, 2.0]))["best_sets_disjoint"]
    assert not preference_comparison(target([2.0, 2.0]), target([1.0, 2.0]))["best_sets_disjoint"]
    with pytest.raises(ValueError, match="inventory"):
        preference_comparison(target([2.0, 1.0]), target([1.0, 2.0], ("switch2", "move1")))
