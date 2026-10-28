"""Tests for durable continuation journal, exclusive claims, and crash recovery."""

import hashlib
import json
from pathlib import Path

import pytest

from pokemon_red_completion.collection_continuation import (
    ContinuationBudgetCaps,
    ContinuationBudgetLedger,
    ContinuationDirective,
    ContinuationPolicy,
    ContinuationStopReason,
)
from pokemon_red_completion.red_collection_continuation import (
    CampaignClaimLease,
    ContinuationAmbiguityError,
    ContinuationChainIntegrityError,
    ContinuationClaimError,
    RedCollectionContinuationJournal,
)


def _caps() -> ContinuationBudgetCaps:
    return ContinuationBudgetCaps(
        maximum_decisions=2,
        maximum_continuation_chunks_per_goal=2,
        maximum_continuation_chunks_per_campaign=4,
        maximum_actions=1000,
        maximum_frames=10_000,
        maximum_cash_spend=500,
        maximum_consecutive_no_progress=2,
        maximum_wall_seconds=60.0,
    )


def _policy() -> ContinuationPolicy:
    return ContinuationPolicy(
        step_reserve=50,
        local_action_quantum=200,
        local_frame_quantum=2000,
        local_encounter_quantum=5,
    )


def test_exclusive_claim_prevents_concurrent_runs(tmp_path: Path) -> None:
    # E07: Two simultaneous campaign claims: at most one runs
    output_dir = tmp_path / "campaign-e07"
    lease1 = CampaignClaimLease(output_dir)
    lease1.acquire()

    lease2 = CampaignClaimLease(output_dir)
    with pytest.raises(ContinuationClaimError, match="already locked"):
        lease2.acquire()

    lease1.release_claim()
    # Now lease2 can acquire
    lease2.acquire()
    lease2.release_claim()


def test_existing_output_refused_without_explicit_resume(tmp_path: Path) -> None:
    # E14: Existing output directory refused unless explicit valid resume
    output_dir = tmp_path / "campaign-e14"
    output_dir.mkdir()
    journal = RedCollectionContinuationJournal(output_dir)
    time_val = 100.0

    journal.initialize_campaign(
        campaign_id="c1",
        run_id="r1",
        caps=_caps(),
        policy=_policy(),
        model_sha256="a" * 64,
        initial_state_sha256="b" * 64,
        provenance={"test": True},
        clock=lambda: time_val,
    )

    # Attempting to initialize again fails
    with pytest.raises(FileExistsError, match="already exists"):
        journal.initialize_campaign(
            campaign_id="c1",
            run_id="r1",
            caps=_caps(),
            policy=_policy(),
            model_sha256="a" * 64,
            initial_state_sha256="b" * 64,
            provenance={"test": True},
            clock=lambda: time_val,
        )


def test_resume_rejects_incompatible_policy_or_caps(tmp_path: Path) -> None:
    # E15: Resume with config policy changed requires explicit rejection
    output_dir = tmp_path / "campaign-e15"
    journal = RedCollectionContinuationJournal(output_dir)
    journal.initialize_campaign(
        campaign_id="c1",
        run_id="r1",
        caps=_caps(),
        policy=_policy(),
        model_sha256="a" * 64,
        initial_state_sha256="b" * 64,
        provenance={},
        clock=lambda: 100.0,
    )

    different_policy = ContinuationPolicy(step_reserve=100)
    with pytest.raises(ContinuationChainIntegrityError, match="incompatible policy change"):
        journal.read_and_validate_plan(expected_policy=different_policy)

    different_caps = ContinuationBudgetCaps(maximum_actions=9999)
    with pytest.raises(ContinuationChainIntegrityError, match="incompatible caps change"):
        journal.read_and_validate_plan(expected_caps=different_caps)


def test_crash_intent_without_dispatch_is_ambiguous(tmp_path: Path) -> None:
    # E02 / E03: Intent written but no dispatch -> ambiguous stop
    output_dir = tmp_path / "campaign-e02"
    journal = RedCollectionContinuationJournal(output_dir)
    journal.initialize_campaign(
        campaign_id="c1",
        run_id="r1",
        caps=_caps(),
        policy=_policy(),
        model_sha256="a" * 64,
        initial_state_sha256="b" * 64,
        provenance={},
        clock=lambda: 100.0,
    )

    journal.record_step_intent(
        0,
        step_kind="new_goal",
        parent_terminal_sha256="b" * 64,
        parent_outcome_sha256=None,
        clock=lambda: 101.0,
    )
    # Crash happens here before dispatch!
    with pytest.raises(ContinuationAmbiguityError, match="without dispatch"):
        journal.reconcile_campaign()


def test_crash_dispatch_without_terminal_is_ambiguous(tmp_path: Path) -> None:
    # E04 / E05: Dispatch written but missing terminal / outcome -> ambiguous stop
    output_dir = tmp_path / "campaign-e04"
    journal = RedCollectionContinuationJournal(output_dir)
    journal.initialize_campaign(
        campaign_id="c1",
        run_id="r1",
        caps=_caps(),
        policy=_policy(),
        model_sha256="a" * 64,
        initial_state_sha256="b" * 64,
        provenance={},
        clock=lambda: 100.0,
    )

    step_dir = journal.record_step_intent(
        0,
        step_kind="new_goal",
        parent_terminal_sha256="b" * 64,
        parent_outcome_sha256=None,
        clock=lambda: 101.0,
    )
    journal.record_step_choice(
        step_dir,
        selected_kind="acquire_species",
        selected_binding_ref="pokemon.red:safari:center",
        menu_sha256="m" * 64,
        model_queries=1,
    )
    journal.record_step_dispatch(
        step_dir,
        selected_kind="acquire_species",
        selected_binding_ref="pokemon.red:safari:center",
        before_state_sha256="b" * 64,
        step_kind="new_goal",
        budget_snapshot={"actions_remaining": 1000},
    )
    # Crash happens here before terminal/outcome written!
    with pytest.raises(ContinuationAmbiguityError, match="missing terminal or outcome"):
        journal.reconcile_campaign()


def test_corrupted_or_truncated_records_fail_closed(tmp_path: Path) -> None:
    # E09: Partial/truncated/corrupt/wrong-hash records fail closed
    output_dir = tmp_path / "campaign-e09"
    journal = RedCollectionContinuationJournal(output_dir)
    journal.initialize_campaign(
        campaign_id="c1",
        run_id="r1",
        caps=_caps(),
        policy=_policy(),
        model_sha256="a" * 64,
        initial_state_sha256="b" * 64,
        provenance={},
        clock=lambda: 100.0,
    )

    step_dir = journal.record_step_intent(
        0,
        step_kind="new_goal",
        parent_terminal_sha256="b" * 64,
        parent_outcome_sha256=None,
        clock=lambda: 101.0,
    )
    # Corrupt intent.json
    (step_dir / "intent.json").write_text("{ incomplete json")
    with pytest.raises(ContinuationChainIntegrityError, match="corrupted JSON"):
        journal.reconcile_campaign()


def test_reconciled_steps_allow_clean_resume(tmp_path: Path) -> None:
    # E06: Complete terminal/outcome permits explicit resume
    output_dir = tmp_path / "campaign-e06"
    journal = RedCollectionContinuationJournal(output_dir)
    initial_state = b"initial-state-bytes"
    initial_sha = hashlib.sha256(initial_state).hexdigest()

    journal.initialize_campaign(
        campaign_id="c1",
        run_id="r1",
        caps=_caps(),
        policy=_policy(),
        model_sha256="a" * 64,
        initial_state_sha256=initial_sha,
        provenance={},
        clock=lambda: 100.0,
    )

    # Step 0: completed successfully
    step0_dir = journal.record_step_intent(
        0,
        step_kind="new_goal",
        parent_terminal_sha256=initial_sha,
        parent_outcome_sha256=None,
        clock=lambda: 101.0,
    )
    journal.record_step_choice(
        step0_dir,
        selected_kind="acquire_species",
        selected_binding_ref="ref:1",
        menu_sha256="m" * 64,
        model_queries=1,
    )
    journal.record_step_dispatch(
        step0_dir,
        selected_kind="acquire_species",
        selected_binding_ref="ref:1",
        before_state_sha256=initial_sha,
        step_kind="new_goal",
        budget_snapshot={},
    )
    term0_bytes = b"term0-state-bytes"
    term0_sha = hashlib.sha256(term0_bytes).hexdigest()
    journal.record_step_terminal(
        step0_dir,
        before_state_bytes=initial_state,
        before_facts={"cash": 1000},
        terminal_state_bytes=term0_bytes,
        terminal_facts={"cash": 500},
        safe_terminal=True,
        directive=ContinuationDirective.CONTINUE_SAME_GOAL,
        stop_reason=ContinuationStopReason.LOCAL_QUANTUM_EXHAUSTED.value,
        actions_executed=100,
        frames_executed=1000,
        encounters_seen=2,
        cash_delta=500,
        made_progress=False,
        goal_completed=False,
        goal_pending=True,
    )

    # Reconcile should succeed with 1 step
    plan, steps = journal.reconcile_campaign()
    assert len(steps) == 1
    assert steps[0].terminal_state_sha256 == term0_sha
    assert steps[0].safe_terminal is True


def test_duplicate_parent_terminal_rejected(tmp_path: Path) -> None:
    # E08: Same parent terminal cannot spawn two children after restart
    output_dir = tmp_path / "campaign-e08"
    journal = RedCollectionContinuationJournal(output_dir)
    initial_sha = hashlib.sha256(b"b").hexdigest()

    journal.initialize_campaign(
        campaign_id="c1",
        run_id="r1",
        caps=_caps(),
        policy=_policy(),
        model_sha256="a" * 64,
        initial_state_sha256=initial_sha,
        provenance={},
        clock=lambda: 100.0,
    )

    # Step 0 with parent = initial_sha
    s0 = journal.record_step_intent(
        0, step_kind="new_goal", parent_terminal_sha256=initial_sha,
        parent_outcome_sha256=None, clock=lambda: 101.0,
    )
    journal.record_step_dispatch(
        s0, selected_kind="k", selected_binding_ref="r", before_state_sha256=initial_sha,
        step_kind="new_goal", budget_snapshot={},
    )
    journal.record_step_choice(s0, selected_kind="k", selected_binding_ref="r",
                               menu_sha256="a" * 64, model_queries=1)
    term0 = b"t0"
    journal.record_step_terminal(
        s0, before_state_bytes=b"b", before_facts={}, terminal_state_bytes=term0,
        terminal_facts={}, safe_terminal=True, directive=ContinuationDirective.REPLAN,
        stop_reason="done", actions_executed=10, frames_executed=10, encounters_seen=0,
        cash_delta=0, made_progress=True, goal_completed=True, goal_pending=False,
    )

    # Step 1 also claims parent = initial_sha (invalid branch / duplicate child!)
    s1 = journal.record_step_intent(
        1, step_kind="new_goal", parent_terminal_sha256=initial_sha,
        parent_outcome_sha256=None, clock=lambda: 102.0,
    )
    journal.record_step_dispatch(
        s1, selected_kind="k", selected_binding_ref="r", before_state_sha256=initial_sha,
        step_kind="new_goal", budget_snapshot={},
    )
    journal.record_step_terminal(
        s1, before_state_bytes=b"b", before_facts={}, terminal_state_bytes=b"t1",
        terminal_facts={}, safe_terminal=True, directive=ContinuationDirective.REPLAN,
        stop_reason="done", actions_executed=10, frames_executed=10, encounters_seen=0,
        cash_delta=0, made_progress=True, goal_completed=True, goal_pending=False,
    )

    match_pattern = r"parent terminal .* != expected|already has a child"
    with pytest.raises(ContinuationChainIntegrityError, match=match_pattern):
        journal.reconcile_campaign()


def test_summary_telemetry_reconciles_truthfully(tmp_path: Path) -> None:
    # F05 / F06: Reconciled totals equal segment sums; original choices distinct from segments
    output_dir = tmp_path / "campaign-f05"
    journal = RedCollectionContinuationJournal(output_dir)
    initial_state = b"init"
    initial_sha = hashlib.sha256(initial_state).hexdigest()

    journal.initialize_campaign(
        campaign_id="c1",
        run_id="r1",
        caps=_caps(),
        policy=_policy(),
        model_sha256="a" * 64,
        initial_state_sha256=initial_sha,
        provenance={},
        clock=lambda: 100.0,
    )

    # Step 0: Model choice (decision 1)
    s0 = journal.record_step_intent(
        0, step_kind="new_goal", parent_terminal_sha256=initial_sha,
        parent_outcome_sha256=None, clock=lambda: 101.0,
    )
    journal.record_step_choice(
        s0, selected_kind="acquire_species", selected_binding_ref="ref:safari",
        menu_sha256="m0", model_queries=1,
    )
    journal.record_step_dispatch(
        s0, selected_kind="acquire_species", selected_binding_ref="ref:safari",
        before_state_sha256=initial_sha, step_kind="new_goal", budget_snapshot={},
    )
    t0_bytes = b"t0"
    t0_sha = hashlib.sha256(t0_bytes).hexdigest()
    journal.record_step_terminal(
        s0, before_state_bytes=initial_state, before_facts={"cash": 1000, "registered_species": 5},
        terminal_state_bytes=t0_bytes, terminal_facts={"cash": 500, "registered_species": 5},
        safe_terminal=True, directive=ContinuationDirective.CONTINUE_SAME_GOAL,
        stop_reason=ContinuationStopReason.LOCAL_QUANTUM_EXHAUSTED.value,
        actions_executed=50, frames_executed=500, encounters_seen=2, cash_delta=500,
        made_progress=False, goal_completed=False, goal_pending=True,
    )

    # Step 1: Same goal continuation (0 model queries!)
    s1 = journal.record_step_intent(
        1, step_kind="continue_same_goal", parent_terminal_sha256=t0_sha,
        parent_outcome_sha256=hashlib.sha256(json.dumps(
            json.loads((s0 / "outcome.json").read_text()), sort_keys=True
        ).encode()).hexdigest(), clock=lambda: 102.0,
    )
    # No choice.json for continuation! (A05)
    journal.record_step_dispatch(
        s1, selected_kind="acquire_species", selected_binding_ref="ref:safari",
        before_state_sha256=t0_sha, step_kind="continue_same_goal", budget_snapshot={},
    )
    t1_bytes = b"t1"
    journal.record_step_terminal(
        s1, before_state_bytes=t0_bytes, before_facts={"cash": 500, "registered_species": 5},
        terminal_state_bytes=t1_bytes, terminal_facts={"cash": 500, "registered_species": 6},
        safe_terminal=True, directive=ContinuationDirective.COMPLETE,
        stop_reason=ContinuationStopReason.GOAL_COMPLETED.value,
        actions_executed=30, frames_executed=300, encounters_seen=1, cash_delta=0,
        made_progress=True, goal_completed=True, goal_pending=False,
    )

    plan, steps = journal.reconcile_campaign()
    assert len(steps) == 2

    ledger = ContinuationBudgetLedger(
        _caps(), clock=lambda: 120.0, actions_spent=80, frames_spent=800,
        cash_spent=500, encounters_seen=3, decisions_used=1,
    )
    summary = journal.record_summary(
        campaign_id="c1",
        run_id="r1",
        stop_reason="campaign_completed",
        ledger=ledger,
        steps=steps,
        initial_facts={"registered_species": 5, "specimens": 3, "cash": 1000},
        final_facts={"registered_species": 6, "specimens": 4, "cash": 500},
    )

    assert summary["model_decisions"] == 1
    assert summary["continuation_chunks"] == 1
    assert summary["step_count"] == 2
    assert summary["successful_goals"] == 1
    assert summary["reconciled_totals"]["actions"] == 80
    assert summary["reconciled_totals"]["frames"] == 800
    assert summary["reconciled_totals"]["cash_spent"] == 500
    assert summary["reconciled_totals"]["encounters"] == 3
    assert summary["native_qualification"] == "NOT RUN"
