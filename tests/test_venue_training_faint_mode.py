"""Teacher fitness costs retain actual faint counts;legacy mode remains strict."""

import pytest

from pokemon_red_completion.red_teacher_venue import (
    HIGH_LEVEL_SCHEMA,
    observed_training_faints,
    venue_training_faint_recovery,
)


def test_legacy_teacher_plan_does_not_enable_recovery():
    assert venue_training_faint_recovery({"schema": HIGH_LEVEL_SCHEMA}) is False


def test_only_explicit_workload_flag_enables_recovery():
    assert (
        venue_training_faint_recovery(
            {"schema": HIGH_LEVEL_SCHEMA, "recover_training_faints": True}
        )
        is True
    )


@pytest.mark.parametrize("value", [None, 1, "true"])
def test_recovery_scope_rejects_coercion(value):
    with pytest.raises(ValueError):
        venue_training_faint_recovery(
            {"schema": HIGH_LEVEL_SCHEMA, "recover_training_faints": value}
        )


def test_legacy_other_task_cannot_enable_workload_recovery():
    with pytest.raises(ValueError):
        venue_training_faint_recovery({"schema": "legacy", "recover_training_faints": True})


def test_faint_and_recovery_are_not_double_counted():
    events = [
        {"kind": "wild_training_faint", "payload": {"observed_faints": 1}},
        {"kind": "wild_training_faint_recovery", "payload": {"observed_faints": 1}},
    ]
    assert observed_training_faints(events) == 1
    assert observed_training_faints([]) == 0


@pytest.mark.parametrize("value", [0, 2, True, None])
def test_unverified_faint_counts_reject(value):
    with pytest.raises(ValueError):
        observed_training_faints(
            [{"kind": "wild_training_faint", "payload": {"observed_faints": value}}]
        )
