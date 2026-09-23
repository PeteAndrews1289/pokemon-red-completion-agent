"""Unit tests for title-neutral continuation boundaries and cumulative lifetime accounting."""

import pytest

from pokemon_red_completion.collection_continuation import (
    ContinuationBudgetCaps,
    ContinuationBudgetExhausted,
    ContinuationBudgetLedger,
    ContinuationPolicy,
    ContinuationStopReason,
    evaluate_semantic_progress,
)


def test_caps_validation_rejects_invalid_values() -> None:
    # Reject bool-as-int (B03)
    with pytest.raises(TypeError, match="must be an integer"):
        ContinuationBudgetCaps(maximum_decisions=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must be an integer"):
        ContinuationBudgetCaps(maximum_actions=False)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="cannot be a bool"):
        ContinuationBudgetCaps(maximum_wall_seconds=True)  # type: ignore[arg-type]

    # Reject negative values (B03)
    with pytest.raises(ValueError, match="must be positive"):
        ContinuationBudgetCaps(maximum_decisions=0)
    with pytest.raises(ValueError, match="must be positive"):
        ContinuationBudgetCaps(maximum_actions=-1)
    with pytest.raises(ValueError, match="must be non-negative"):
        ContinuationBudgetCaps(maximum_cash_spend=-10)

    # Reject non-finite wall time (B03)
    with pytest.raises(ValueError, match="must be positive and finite"):
        ContinuationBudgetCaps(maximum_wall_seconds=float("nan"))
    with pytest.raises(ValueError, match="must be positive and finite"):
        ContinuationBudgetCaps(maximum_wall_seconds=float("inf"))
    with pytest.raises(ValueError, match="must be positive and finite"):
        ContinuationBudgetCaps(maximum_wall_seconds=0.0)

    # Reject goal chunks > campaign chunks
    with pytest.raises(ValueError, match="chunks per goal cannot exceed chunks per campaign"):
        ContinuationBudgetCaps(
            maximum_continuation_chunks_per_goal=10,
            maximum_continuation_chunks_per_campaign=5,
        )


def test_policy_validation_rejects_invalid_values() -> None:
    with pytest.raises(TypeError):
        ContinuationPolicy(step_reserve=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ContinuationPolicy(step_reserve=0)
    with pytest.raises(ValueError):
        ContinuationPolicy(local_action_quantum=-100)


def test_budget_ledger_conserves_and_tracks_resources() -> None:
    current_time = 1000.0
    caps = ContinuationBudgetCaps(
        maximum_decisions=2,
        maximum_continuation_chunks_per_goal=2,
        maximum_continuation_chunks_per_campaign=3,
        maximum_actions=1000,
        maximum_frames=50_000,
        maximum_cash_spend=1000,
        maximum_consecutive_no_progress=2,
        maximum_wall_seconds=60.0,
    )
    ledger = ContinuationBudgetLedger(caps, clock=lambda: current_time)

    # B05: Distinct units
    assert ledger.actions_spent == 0
    assert ledger.frames_spent == 0
    assert ledger.encounters_seen == 0
    assert ledger.cash_spent == 0

    # Admit decision 1
    ledger.admit_decision()
    assert ledger.decisions_used == 1
    assert ledger.goal_continuation_chunks == 0

    # Admit continuation chunks
    ledger.admit_continuation_chunk()
    assert ledger.goal_continuation_chunks == 1
    assert ledger.campaign_continuation_chunks == 1

    ledger.admit_continuation_chunk()
    assert ledger.goal_continuation_chunks == 2
    assert ledger.campaign_continuation_chunks == 2

    # Goal chunk cap reached
    with pytest.raises(ContinuationBudgetExhausted) as exc:
        ledger.admit_continuation_chunk()
    assert exc.value.reason == ContinuationStopReason.CHUNK_BUDGET_EXHAUSTED

    # Action reservation and settlement
    # B01 / B02: Shared allowance, not renewable per chunk
    allocated = ledger.reserve_actions(600)
    assert allocated == 600
    ledger.settle_actions(attempted=500, completed=500, frames=20_000)
    assert ledger.actions_spent == 500
    assert ledger.frames_spent == 20_000

    # Second allocation cannot exceed remaining global allowance (1000 - 500 = 500)
    allocated2 = ledger.reserve_actions(600)
    assert allocated2 == 500
    ledger.settle_actions(attempted=500, completed=500, frames=25_000)
    assert ledger.actions_spent == 1000

    # Next attempt to reserve fails: 0 remaining
    with pytest.raises(ContinuationBudgetExhausted) as exc:
        ledger.reserve_actions(1)
    assert exc.value.reason == ContinuationStopReason.GLOBAL_ACTION_BUDGET_EXHAUSTED


def test_cash_spending_is_actual_delta_conserved_across_segments() -> None:
    # B04: Cash spend is actual delta, conserved across segments; fees never double-counted
    caps = ContinuationBudgetCaps(maximum_cash_spend=500)
    ledger = ContinuationBudgetLedger(caps, clock=lambda: 100.0)

    ledger.record_cash_spend(500)
    assert ledger.cash_spent == 500
    assert ledger.remaining_budgets()["cash"] == 0

    with pytest.raises(ContinuationBudgetExhausted) as exc:
        ledger.record_cash_spend(1)
    assert exc.value.reason == ContinuationStopReason.CASH_BUDGET_EXHAUSTED


def test_wall_time_and_conservative_clock_rollback() -> None:
    # B08: Resume inherits remaining deadline/budgets;
    # clock injection handles rollback conservatively
    time_holder = [1000.0]
    caps = ContinuationBudgetCaps(maximum_wall_seconds=30.0)
    ledger = ContinuationBudgetLedger(caps, clock=lambda: time_holder[0])

    time_holder[0] = 1010.0
    assert ledger.elapsed_seconds == 10.0
    assert ledger.remaining_wall_seconds == 20.0
    assert not ledger.is_wall_time_exhausted

    # Clock rollback: time should not decrease!
    time_holder[0] = 950.0
    assert ledger.elapsed_seconds == 10.0  # rollback handled conservatively

    time_holder[0] = 1030.0
    assert ledger.elapsed_seconds == 30.0
    assert ledger.is_wall_time_exhausted
    assert ledger.remaining_wall_seconds == 0.0

    with pytest.raises(ContinuationBudgetExhausted) as exc:
        ledger.admit_decision()
    assert exc.value.reason == ContinuationStopReason.WALL_TIME_EXHAUSTED


def test_no_progress_limit() -> None:
    # B09: No-progress limit stops repeated unchanged/meaninglessly changed snapshots
    caps = ContinuationBudgetCaps(maximum_consecutive_no_progress=2)
    ledger = ContinuationBudgetLedger(caps, clock=lambda: 100.0)

    ledger.record_progress(False)
    assert ledger.consecutive_no_progress == 1
    assert ledger.check_preflight_budget() is None

    ledger.record_progress(False)
    assert ledger.consecutive_no_progress == 2
    assert ledger.check_preflight_budget() == ContinuationStopReason.NO_PROGRESS_LIMIT_EXHAUSTED

    with pytest.raises(ContinuationBudgetExhausted) as exc:
        ledger.admit_continuation_chunk()
    assert exc.value.reason == ContinuationStopReason.NO_PROGRESS_LIMIT_EXHAUSTED

    # Reset upon actual progress
    ledger.record_progress(True)
    assert ledger.consecutive_no_progress == 0
    assert ledger.check_preflight_budget() is None


def test_ledger_inheritance_preserves_accumulated_costs() -> None:
    # B08: Resume inherits remaining deadline/budgets
    caps = ContinuationBudgetCaps(
        maximum_decisions=3,
        maximum_actions=10_000,
        maximum_wall_seconds=100.0,
    )
    time_holder = [100.0]
    ledger1 = ContinuationBudgetLedger(caps, clock=lambda: time_holder[0])
    ledger1.admit_decision()
    ledger1.settle_actions(attempted=3000, completed=3000, frames=50_000)
    ledger1.record_cash_spend(500)
    time_holder[0] = 140.0  # 40s elapsed

    persisted = ledger1.to_dict()

    # Create new ledger inheriting from persisted
    time_holder[0] = 200.0  # new session starts at t=200
    ledger2 = ContinuationBudgetLedger.inherit_from(
        persisted, caps, clock=lambda: time_holder[0], downtime_seconds=60
    )

    assert ledger2.decisions_used == 1
    assert ledger2.actions_spent == 3000
    assert ledger2.cash_spent == 500
    assert ledger2.elapsed_seconds == 100.0
    assert ledger2.remaining_wall_seconds == 0.0

    # Advance 20s in second session
    time_holder[0] = 220.0
    assert ledger2.elapsed_seconds == 120.0
    assert ledger2.remaining_wall_seconds == 0.0


def test_evaluate_semantic_progress_distinguishes_real_from_fake_changes() -> None:
    # D04: Reordering/evolution does not fabricate XP loss/gain or success from byte changes alone
    # Unchanged
    assert not evaluate_semantic_progress(
        {"registered_species": 10, "specimens": 5},
        {"registered_species": 10, "specimens": 5},
    )

    # Party reordering without XP change is NOT progress
    before_party = {"party_training": [[0, 25, 1000], [1, 9, 2000]]}
    reordered_party = {"party_training": [[0, 9, 2000], [1, 25, 1000]]}
    assert not evaluate_semantic_progress(before_party, reordered_party)

    # Experience decrease or unequal slots is NOT progress
    decreased_party = {"party_training": [[0, 25, 900], [1, 9, 2000]]}
    assert not evaluate_semantic_progress(before_party, decreased_party)

    # Legitimate experience gain IS progress
    increased_party = {"party_training": [[0, 25, 1200], [1, 9, 2000]]}
    assert evaluate_semantic_progress(before_party, increased_party)

    # Registration increase IS progress
    assert evaluate_semantic_progress(
        {"registered_species": 10},
        {"registered_species": 11},
    )

    # Specimen increase IS progress
    assert evaluate_semantic_progress(
        {"specimens": 5},
        {"specimens": 6},
    )
