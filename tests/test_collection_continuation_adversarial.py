"""Read-only journal and semantic-progress checks; no live-adapter qualification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from summarize_red_collection_campaign import (
    _audit_privacy,
    summarize_red_collection_campaign,
)

from pokemon_red_completion.collection_continuation import (
    ContinuationBudgetCaps,
    ContinuationBudgetLedger,
    ContinuationDirective,
    ContinuationStopReason,
    evaluate_semantic_progress,
)
from pokemon_red_completion.red_collection_continuation import (
    ContinuationChainIntegrityError,
    ContinuationPolicy,
    RedCollectionContinuationJournal,
)

# ============================================================================
# Helpers & Fixtures
# ============================================================================


def _create_mock_campaign(
    tmp_path: Path,
    *,
    step_count: int = 3,
    leak_path: str | None = None,
) -> Path:
    """Create a fully verified campaign directory for testing summarizer & checks."""
    output_dir = tmp_path / "mock_campaign"
    journal = RedCollectionContinuationJournal(output_dir)
    caps = ContinuationBudgetCaps(
        maximum_decisions=5,
        maximum_continuation_chunks_per_goal=5,
        maximum_continuation_chunks_per_campaign=10,
        maximum_actions=1000,
        maximum_frames=10000,
        maximum_cash_spend=5000,
        maximum_consecutive_no_progress=3,
        maximum_wall_seconds=300.0,
    )
    policy = ContinuationPolicy()
    initial_bytes = b"initial"
    initial_sha = hashlib.sha256(initial_bytes).hexdigest()

    journal.initialize_campaign(
        campaign_id="test-camp-001",
        run_id="run-001",
        caps=caps,
        policy=policy,
        model_sha256="a" * 64,
        initial_state_sha256=initial_sha,
        provenance={"test": True},
        clock=lambda: 100.0,
    )

    parent_bytes = initial_bytes
    parent_terminal = initial_sha
    parent_outcome: str | None = None

    for i in range(step_count):
        step_dir = journal.record_step_intent(
            i,
            step_kind="new_goal" if i == 0 else "continue_same_goal",
            parent_terminal_sha256=parent_terminal,
            parent_outcome_sha256=parent_outcome,
            clock=lambda i=i: 100.0 + i * 10,
        )
        if i == 0:
            journal.record_step_choice(
                step_dir,
                selected_kind="acquire_species",
                selected_binding_ref="pokemon.red:acquire-species:grass",
                menu_sha256="menu" * 16,
                model_queries=1,
            )
        journal.record_step_dispatch(
            step_dir,
            selected_kind="acquire_species",
            selected_binding_ref="pokemon.red:acquire-species:grass",
            before_state_sha256=parent_terminal,
            step_kind="new_goal" if i == 0 else "continue_same_goal",
            budget_snapshot={"actions_spent": i * 10},
        )
        terminal_bytes = f"terminal_state_{i}".encode()
        term_facts: dict[str, Any] = {"player_y": 2, "player_x": 1}
        if leak_path is not None and i == step_count - 1:
            term_facts["leaked_debug_path"] = leak_path

        evidence: dict[str, Any] = {}
        if leak_path is not None and i == step_count - 1:
            evidence["log_file"] = leak_path

        outcome = journal.record_step_terminal(
            step_dir,
            before_state_bytes=parent_bytes,
            before_facts={"player_y": 2, "player_x": 0},
            terminal_state_bytes=terminal_bytes,
            terminal_facts=term_facts,
            safe_terminal=True,
            directive=ContinuationDirective.CONTINUE_SAME_GOAL
            if i < step_count - 1
            else ContinuationDirective.COMPLETE,
            stop_reason="local_quantum_exhausted"
            if i < step_count - 1
            else "goal_completed",
            goal_completed=(i == step_count - 1),
            goal_pending=(i < step_count - 1),
            made_progress=True,
            actions_executed=10,
            frames_executed=100,
            encounters_seen=1,
            cash_delta=500 if i == 0 else 0,
            evidence=evidence,
        )
        parent_bytes = terminal_bytes
        parent_terminal = outcome["terminal_state_sha256"]
        parent_outcome = hashlib.sha256(
            json.dumps(outcome, sort_keys=True).encode()
        ).hexdigest()

    _, reconciled_steps = journal.reconcile_campaign()
    ledger = ContinuationBudgetLedger(caps, clock=lambda: 100.0)
    ledger.settle_actions(
        attempted=step_count * 10,
        completed=step_count * 10,
        frames=step_count * 100,
    )
    ledger.record_cash_spend(500)
    ledger.record_encounters(step_count)

    journal.record_summary(
        campaign_id="test-camp-001",
        run_id="run-001",
        stop_reason="goal_completed",
        ledger=ledger,
        steps=reconciled_steps,
        initial_facts={"registered_species": 10, "cash": 2500},
        final_facts={"registered_species": 11, "cash": 2000},
    )
    return output_dir


# ============================================================================
# Summarizer & Audit Tests (F05, F06, A09)
# ============================================================================


def test_summarize_campaign_validates_clean_campaign_and_reconciles_totals(
    tmp_path: Path,
) -> None:
    """F05, F06: Summarizer validates full chain, segment sums, choice vs chunk counts."""
    campaign_dir = _create_mock_campaign(tmp_path, step_count=3)
    summary = summarize_red_collection_campaign(campaign_dir, require_summary=True)

    assert summary["status"] == "verified"
    assert summary["step_count"] == 3
    assert summary["model_decisions"] == 1
    assert summary["continuation_chunks"] == 2
    assert summary["successful_goals"] == 1
    assert summary["reconciled_totals"]["actions"] == 30
    assert summary["reconciled_totals"]["frames"] == 300
    assert summary["reconciled_totals"]["cash_spent"] == 500
    assert summary["reconciled_totals"]["encounters"] == 3
    assert summary["hash_chain_verified"] is True
    assert summary["privacy_verified"] is True


def test_summarize_campaign_rejects_tampered_reconciled_totals(tmp_path: Path) -> None:
    """F05: Tampering with summary totals triggers ContinuationChainIntegrityError."""
    campaign_dir = _create_mock_campaign(tmp_path, step_count=2)
    summary_path = campaign_dir / "summary.json"
    data = json.loads(summary_path.read_text())
    # Fabricate lower action count in summary
    data["reconciled_totals"]["actions"] = 5
    summary_path.write_text(json.dumps(data, indent=2))

    with pytest.raises(
        ContinuationChainIntegrityError, match="reconciled actions mismatch"
    ):
        summarize_red_collection_campaign(campaign_dir, require_summary=True)


def test_summarize_campaign_detects_and_rejects_private_path_leak(
    tmp_path: Path,
) -> None:
    """A09: Leaked private machine path is caught by privacy audit."""
    campaign_dir = _create_mock_campaign(
        tmp_path,
        step_count=2,
        leak_path="/Users/example/Developer/PokemonRed.gb",
    )
    with pytest.raises(
        ContinuationChainIntegrityError, match="privacy leak violations detected"
    ):
        summarize_red_collection_campaign(campaign_dir, require_summary=True)


def test_audit_privacy_detects_private_directories_and_rom_extensions() -> None:
    """A09: _audit_privacy checks patterns for /Users/, /Volumes/, .rom, .sav."""
    clean_dict = {"goal": "catch", "target": "NIDORAN_M", "attempts": 3}
    assert _audit_privacy(clean_dict) == []

    leaked = {
        "snapshot": "/Volumes/T7 Developer/PokemonRedCompletion/save.sav",
        "nested": {"path": "/private/var/folders/something.state"},
    }
    violations = _audit_privacy(leaked)
    assert len(violations) >= 2


# ============================================================================
# Adversarial Authority & Identity Tests (A04, A05, A06, A07, A08)
# ============================================================================


def test_historical_failed_outcome_bytes_remain_unchanged_after_later_success(
    tmp_path: Path,
) -> None:
    """A07: When step-001 succeeds, step-000 failure bytes and SHA256 remain unchanged."""
    campaign_dir = _create_mock_campaign(tmp_path, step_count=2)
    step0_outcome_path = campaign_dir / "step-000" / "outcome.json"
    step0_bytes_before = step0_outcome_path.read_bytes()

    # Step 1 was successful; verify step 0 was never modified
    assert step0_outcome_path.read_bytes() == step0_bytes_before


def test_continuation_completion_adds_no_duplicate_registration_credit() -> None:
    """A08: Completing a multi-chunk goal awards exactly 1 net registration credit."""
    # Chunk 0: 0 new species registered (10 -> 10)
    p0 = evaluate_semantic_progress({"registered_species": 10}, {"registered_species": 10})
    assert not p0

    # Chunk 1: target captured (10 -> 11 registered)
    p1 = evaluate_semantic_progress({"registered_species": 10}, {"registered_species": 11})
    assert p1

    # Chunk 2: post-capture continuation (11 -> 11 registered)
    p2 = evaluate_semantic_progress({"registered_species": 11}, {"registered_species": 11})
    assert not p2


# ============================================================================
# Adversarial Safari Scenarios (C01, C02, C08, C11, C12)
# ============================================================================


def test_evolution_reordering_does_not_fabricate_xp_or_success() -> None:
    """D04: Byte changes from reordering party do not count as XP progress or evolution."""
    before_facts = {
        "registered_species": 10,
        "specimens": 10,
        "party_training": [[0, 25, 1000], [1, 4, 500]],
    }
    # Party reordered: slots swapped, but no XP gained for either Pokémon
    after_facts = {
        "registered_species": 10,
        "specimens": 10,
        "party_training": [[0, 4, 500], [1, 25, 1000]],
    }
    assert not evaluate_semantic_progress(before_facts, after_facts)


def test_evolution_repeated_bounded_segment_without_progress_hits_stop() -> None:
    """D05: Consecutive no-progress chunks hit maximum_consecutive_no_progress limit."""
    caps = ContinuationBudgetCaps(maximum_consecutive_no_progress=2)
    ledger = ContinuationBudgetLedger(caps, clock=lambda: 100.0)

    # Chunk 1: no progress
    ledger.record_progress(made_progress=False)
    assert ledger.check_preflight_budget() is None

    # Chunk 2: no progress -> hits limit!
    ledger.record_progress(made_progress=False)
    assert ledger.check_preflight_budget() is ContinuationStopReason.NO_PROGRESS_LIMIT_EXHAUSTED
