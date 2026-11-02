"""Synthetic falsifiers only: no cartridge, native TRAIN rows or model adoption."""

from dataclasses import replace

import pytest

from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.player_short_sequence import (
    SEQUENCE_FEATURE_NAMES,
    MeasuredSequenceStep,
    SequenceEnd,
    SequencePreview,
    measure_sequence,
)

TRAVEL = OptionChallenge(False, False, 0.0, 0.0, 0.0)
FIGHT = OptionChallenge.from_levels(combat_levels=(17,), opponent_levels=(18, 21))


def step(index, **changes):
    return replace(MeasuredSequenceStep(
        decision_sha256=f"{100 + index:064x}", behavior_model_sha256="a" * 64,
        before_sha256=f"{index:064x}", after_sha256=f"{index + 1:064x}",
        actions=10, frames=100, cash_debits=0, blackouts=0,
    ), **changes)


def measure(*steps, **kwargs):
    return measure_sequence(tuple(steps), horizon=len(steps), end=SequenceEnd.HORIZON, **kwargs)


def test_later_known_challenge_distinguishes_equal_immediate_travel():
    fight = SequencePreview((TRAVEL, FIGHT), True)
    travel = SequencePreview((TRAVEL, TRAVEL), True)
    assert fight.vector()[2:8] == travel.vector()[2:8]
    assert fight.vector() != travel.vector()
    assert len(fight.vector()) == len(SEQUENCE_FEATURE_NAMES) == 26


def test_unknown_cannot_become_an_easy_route_or_an_invented_difference():
    unknown = SequencePreview((TRAVEL, None), True)
    assert unknown.vector() != SequencePreview((TRAVEL, TRAVEL), True).vector()
    assert unknown.vector() == SequencePreview((TRAVEL, None), True).vector()
    assert unknown.vector() != SequencePreview((TRAVEL,), True).vector()
    assert unknown.vector() != SequencePreview((TRAVEL, None), False).vector()


def test_private_names_and_menu_order_cannot_enter_preview():
    a, b = SequencePreview((TRAVEL, FIGHT), True), SequencePreview((TRAVEL, TRAVEL), True)
    menu = {"Misty": a, "Bill": b}
    renamed = {"unseen quest Y": b, "unseen quest X": a}
    assert [p.vector() for p in menu.values()] == [p.vector() for p in reversed(renamed.values())]
    assert all(isinstance(x, float) for x in a.vector())


@pytest.mark.parametrize("stages,tail", [
    ((), True), ((TRAVEL,) * 5, True), ([TRAVEL], True),
    (("Misty",), True), ((TRAVEL,), 1),
])
def test_preview_rejects_identity_and_bad_bounds(stages, tail):
    with pytest.raises(ValueError):
        SequencePreview(stages, tail)


def test_loss_then_heal_keeps_full_cost_despite_healthy_final_state():
    result = measure(step(0, cash_debits=214, blackouts=1), step(1))
    assert result.complete_window
    totals = (result.cash_debits, result.blackouts, result.actions, result.frames)
    assert totals == (214, 1, 20, 200)
    assert result.completed_quests == result.new_progress == 0
    assert result.first_decision_sha256 == step(0).decision_sha256


def test_progress_later_in_window_is_visible_without_rewarding_cheap_travel():
    useful = measure(step(0), step(1, progress=("trainer",)), step(2, quests=("ticket",)))
    travel = measure(step(0), step(1), step(2))
    assert useful.new_progress == useful.completed_quests == 1
    assert travel.new_progress == travel.completed_quests == 0
    assert useful.actions == travel.actions


def test_progress_is_deduplicated_and_existing_credit_excluded():
    result = measure(
        step(0, progress=("old", "new"), quests=("old quest",)),
        step(1, progress=("new",), quests=("old quest", "new quest")),
        initial_progress=("old",), initial_quests=("old quest",),
    )
    assert result.new_progress == result.completed_quests == 1


def test_renaming_private_proof_ids_does_not_change_measured_counts():
    a = measure(step(0, progress=("event152",), quests=("Bill",)))
    b = measure(step(0, progress=("unseen event",), quests=("different title quest",)))
    assert a == b


def test_interrupted_prefix_keeps_costs_but_is_not_complete_target():
    result = measure_sequence(
        (step(0, blackouts=1, cash_debits=214),), horizon=4, end=SequenceEnd.INTERRUPTED,
    )
    assert not result.complete_window
    assert result.blackouts == 1 and result.cash_debits == 214
    with pytest.raises(ValueError, match="partial"):
        measure_sequence((step(0),), horizon=4, end=SequenceEnd.HORIZON)


@pytest.mark.parametrize("changes,error", [
    ({"before_sha256": "b" * 64}, "continuity"),
    ({"decision_sha256": step(0).decision_sha256}, "repeats"),
    ({"behavior_model_sha256": "c" * 64}, "policy"),
])
def test_splicing_repetition_and_policy_changes_are_rejected(changes, error):
    with pytest.raises(ValueError, match=error):
        measure(step(0), step(1, **changes))


@pytest.mark.parametrize("field,value", [
    ("actions", True), ("frames", -1), ("cash_debits", -1), ("blackouts", 1.5),
    ("decision_sha256", "not a digest"), ("progress", ("same", "same")),
    ("quests", ["mutable"]), ("quests", ("",)),
])
def test_invalid_evidence_rejected(field, value):
    with pytest.raises(ValueError):
        step(0, **{field: value})


@pytest.mark.parametrize("horizon", [0, 5, True, 1.5])
def test_horizon_is_bounded_integer(horizon):
    with pytest.raises(ValueError):
        measure_sequence((step(0),), horizon=horizon, end=SequenceEnd.HORIZON)


def test_empty_or_oversized_window_cannot_get_a_target():
    with pytest.raises(ValueError):
        measure_sequence((), horizon=1, end=SequenceEnd.INTERRUPTED)
    with pytest.raises(ValueError):
        measure_sequence((step(0), step(1)), horizon=1, end=SequenceEnd.HORIZON)


def test_prototype_does_not_convert_to_existing_single_option_training_example():
    result = measure(step(0))
    assert not hasattr(result, "target_vector")
    assert not hasattr(result, "partition")
