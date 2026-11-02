"""Target mathematics are synthetic; coverage claims never admit native rows."""

from dataclasses import replace

import pytest
from test_player_short_sequence import measure, step

from pokemon_red_completion.player_sequence_targets import SEQUENCE_TARGET_NAMES, sequence_targets
from pokemon_red_completion.player_short_sequence import SequenceEnd, measure_sequence

ALL = frozenset(SEQUENCE_TARGET_NAMES)


def test_unknown_is_not_a_zero_cost_or_no_loss_label():
    targets = sequence_targets(measure(step(0, blackouts=2, cash_debits=214)))
    assert targets.values == (None,) * 7
    assert not any(targets.known)
    assert targets.raw == (0, 0, 10, 100, 214, 0, 2)


def test_complete_covered_targets_use_fixed_normalization():
    measured = measure(step(
        0, progress=("trainer",), quests=("ticket",), actions=1000, frames=60000,
        cash_debits=1000, cash_credits=1000, blackouts=1,
    ))
    assert sequence_targets(measured, covered=ALL).values == (0.5,) * 7


def test_each_channel_requires_its_own_coverage_including_known_zero():
    targets = sequence_targets(measure(step(0)), covered=frozenset({"completed_quests", "frames"}))
    assert targets.values == (None, 0.0, None, 100 / 60100, None, None, None)
    assert targets.known == (False, True, False, True, False, False, False)


def test_short_prefix_masks_even_verified_observed_failure_and_cost():
    measured = measure_sequence(
        (step(0, blackouts=1, cash_debits=214),), horizon=4, end=SequenceEnd.INTERRUPTED,
    )
    targets = sequence_targets(measured, covered=ALL)
    assert targets.values == (None,) * 7
    assert targets.raw[-1] == 1 and targets.raw[4] == 214


def test_travel_success_cannot_become_quest_or_progress_reward():
    targets = sequence_targets(measure(step(0), step(1)), covered=ALL)
    assert targets.values[:2] == (0.0, 0.0)
    assert targets.values[2] > 0


@pytest.mark.parametrize("covered", [{"actions"}, frozenset({"unknown"}), ("actions",)])
def test_coverage_contract_is_strict(covered):
    with pytest.raises(ValueError):
        sequence_targets(measure(step(0)), covered=covered)


@pytest.mark.parametrize("changes", [
    {"actions": True}, {"frames": 0}, {"cash_credits": -1}, {"blackouts": 0.5},
    {"observed_steps": 0}, {"horizon": 5}, {"horizon": 2}, {"end": "horizon"},
    {"first_decision_sha256": "wrong"}, {"completed_quests": False},
])
def test_fabricated_measurement_cannot_bypass_step_validation(changes):
    with pytest.raises(ValueError):
        replace(measure(step(0)), **changes)
