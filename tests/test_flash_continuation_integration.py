"""Regression tests for independently reproduced Flash audit failures."""

import json
from dataclasses import replace

import pytest
from summarize_red_collection_campaign import summarize_red_collection_campaign
from test_collection_continuation_adversarial import _create_mock_campaign

from pokemon_red_completion.collection_continuation import (
    ContinuationBudgetCaps,
    ContinuationBudgetExhausted,
    ContinuationBudgetLedger,
    evaluate_semantic_progress,
)
from pokemon_red_completion.red_collection_continuation import (
    ContinuationChainIntegrityError,
    RedCollectionContinuationJournal,
    _write_atomic,
)


def rewrite(path, change):
    document = json.loads(path.read_text())
    change(document)
    path.write_text(json.dumps(document))


@pytest.mark.parametrize(
    "file,key,value",
    [
        ("dispatch.json", "before_state_sha256", "f" * 64),
        ("outcome.json", "before_state_sha256", "f" * 64),
        ("before.json", "state_sha256", "f" * 64),
        ("terminal.json", "state_sha256", "f" * 64),
        ("outcome.json", "safe_terminal", "false"),
        ("outcome.json", "goal_completed", True),
        ("outcome.json", "actions_executed", True),
        ("outcome.json", "encounters_seen", None),
        ("outcome.json", "frames_executed", -1),
        ("intent.json", "step_index", True),
        ("choice.json", "selected_binding_ref", "wrong"),
        ("choice.json", "model_queries", True),
    ],
)
def test_journal_rejects_inconsistent_receipt(tmp_path, file, key, value):
    root = _create_mock_campaign(tmp_path, step_count=2)
    rewrite(root / "step-000" / file, lambda doc: doc.update({key: value}))
    with pytest.raises(ContinuationChainIntegrityError):
        RedCollectionContinuationJournal(root).reconcile_campaign()


@pytest.mark.parametrize(
    "key,value",
    [
        ("parent_outcome_sha256", None),
        ("parent_terminal_sha256", "f" * 64),
        ("step_kind", "new_goal"),
    ],
)
def test_child_must_retain_exact_parent_identity(tmp_path, key, value):
    root = _create_mock_campaign(tmp_path, step_count=2)
    rewrite(root / "step-001/intent.json", lambda doc: doc.update({key: value}))
    with pytest.raises(ContinuationChainIntegrityError):
        RedCollectionContinuationJournal(root).reconcile_campaign()


def test_before_state_bytes_cannot_rewind(tmp_path):
    root = _create_mock_campaign(tmp_path, step_count=2)
    (root / "step-001/before.state").write_bytes(b"initial")
    with pytest.raises(ContinuationChainIntegrityError, match="before state"):
        RedCollectionContinuationJournal(root).reconcile_campaign()


def test_continuation_cannot_switch_goal(tmp_path):
    root = _create_mock_campaign(tmp_path, step_count=2)
    rewrite(
        root / "step-001/dispatch.json", lambda doc: doc.update(selected_binding_ref="another-goal")
    )
    with pytest.raises(ContinuationChainIntegrityError, match="changed selected goal"):
        RedCollectionContinuationJournal(root).reconcile_campaign()


def test_missing_step_cannot_hide_later_dispatch(tmp_path):
    root = _create_mock_campaign(tmp_path, step_count=2)
    (root / "step-001").rename(root / "step-002")
    with pytest.raises(ContinuationChainIntegrityError, match="sequence"):
        RedCollectionContinuationJournal(root).reconcile_campaign()


def test_summary_must_match_ledger_not_just_segment_sums(tmp_path):
    root = _create_mock_campaign(tmp_path, step_count=2)
    rewrite(root / "summary.json", lambda doc: doc["ledger_totals"].update(actions=0))
    with pytest.raises(ContinuationChainIntegrityError, match="ledger actions"):
        summarize_red_collection_campaign(root)


@pytest.mark.parametrize(
    "key,value",
    [
        ("actions_spent", True),
        ("decisions_used", "1"),
        ("frames_spent", -1),
        ("elapsed_seconds", False),
        ("elapsed_seconds", float("nan")),
    ],
)
def test_ledger_resume_does_not_coerce_invalid_counters(key, value):
    caps = ContinuationBudgetCaps()
    saved = ContinuationBudgetLedger(caps, clock=lambda: 0).to_dict()
    saved[key] = value
    with pytest.raises((TypeError, ValueError)):
        ContinuationBudgetLedger.inherit_from(saved, caps, clock=lambda: 0, downtime_seconds=0)


@pytest.mark.parametrize("missing", ["actions_spent", "elapsed_seconds", "caps", "schema"])
def test_ledger_resume_never_defaults_missing_values_to_zero(missing):
    caps = ContinuationBudgetCaps()
    saved = ContinuationBudgetLedger(caps, clock=lambda: 0).to_dict()
    saved.pop(missing)
    with pytest.raises(ValueError):
        ContinuationBudgetLedger.inherit_from(saved, caps, clock=lambda: 0, downtime_seconds=0)


def test_ledger_resume_rejects_changed_limits():
    caps = ContinuationBudgetCaps()
    saved = ContinuationBudgetLedger(caps, clock=lambda: 0).to_dict()
    with pytest.raises(ValueError, match="caps"):
        ContinuationBudgetLedger.inherit_from(
            saved,
            replace(caps, maximum_actions=caps.maximum_actions + 1),
            clock=lambda: 0,
            downtime_seconds=0,
        )


def test_observed_budget_overrun_is_retained_and_reported():
    ledger = ContinuationBudgetLedger(
        ContinuationBudgetCaps(maximum_actions=10, maximum_frames=20), clock=lambda: 0
    )
    ledger.reserve_actions(5)
    with pytest.raises(ContinuationBudgetExhausted, match="overrun"):
        ledger.settle_actions(attempted=20, completed=20, frames=50)
    assert ledger.actions_spent == 20 and ledger.frames_spent == 50
    with pytest.raises(ContinuationBudgetExhausted):
        ledger.reserve_actions(1)


def test_cash_overrun_is_not_erased():
    ledger = ContinuationBudgetLedger(
        ContinuationBudgetCaps(maximum_cash_spend=10), clock=lambda: 0
    )
    with pytest.raises(ContinuationBudgetExhausted):
        ledger.record_cash_spend(20)
    assert ledger.cash_spent == 20


def test_zero_cash_cap_still_allows_free_work():
    ledger = ContinuationBudgetLedger(ContinuationBudgetCaps(maximum_cash_spend=0), clock=lambda: 0)
    ledger.admit_decision()
    assert ledger.reserve_actions(1) == 1
    with pytest.raises(ValueError, match="unsettled"):
        ledger.to_dict()


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_nonfinite_clock_cannot_disable_deadline(value):
    clock = [0]
    ledger = ContinuationBudgetLedger(ContinuationBudgetCaps(), clock=lambda: clock[0])
    clock[0] = value
    with pytest.raises(ValueError, match="clock"):
        ledger.admit_decision()


def test_missing_or_boolean_progress_does_not_fabricate_gain():
    assert not evaluate_semantic_progress({}, {"registered_species": 101})
    assert not evaluate_semantic_progress(
        {"registered_species": False}, {"registered_species": True}
    )
    assert not evaluate_semantic_progress(
        {"party_training": [[1, 2, "100"]]}, {"party_training": [[1, 2, "200"]]}
    )


def test_actual_record_writer_never_overwrites_existing_evidence(tmp_path):
    path = tmp_path / "record"
    _write_atomic(path, b"first")
    with pytest.raises(FileExistsError):
        _write_atomic(path, b"second")
    assert path.read_bytes() == b"first"
