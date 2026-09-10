from dataclasses import replace

import pytest
from test_routed_semantic_goal import _composer

from pokemon_red_completion.field_move_summary import FieldMoveSummary
from pokemon_red_completion.goal_manager import GoalFailureReason
from pokemon_red_completion.goal_manager_runtime import GoalVerification


@pytest.mark.parametrize("value", [True, -1, 10_001, 1.5, "1", None])
def test_counts_require_bounded_integers(value):
    with pytest.raises(ValueError, match="counts"):
        FieldMoveSummary.from_evidence({"field_moves":{"cuts":value,"surfs":0,"flights":0}})


def test_unknown_or_incomplete_receipt_fields_reject():
    assert FieldMoveSummary.from_evidence({}) is None
    for value in ({"cuts":1}, {"cuts":1,"surfs":0,"flights":0,"private_path":"secret"}, []):
        with pytest.raises(ValueError, match="fields"):
            FieldMoveSummary.from_evidence({"field_moves":value})


def test_composition_retains_disjoint_completed_macro_counts_without_private_fields():
    _, binding, _, _ = _composer(route_fields={"cuts":2,"surfs":1,"flights":1},
                                destination_fields={"cuts":0,"surfs":3,"flights":0})
    report = binding.execute()
    assert report.evidence["field_moves"] == {"cuts":2,"surfs":4,"flights":1}
    assert "private_route" not in report.evidence
    assert binding.verify(report).status.value == "succeeded"


def test_route_failure_does_not_credit_unexecuted_destination_macros():
    _, binding, _, _ = _composer(
        route_verification=GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED),
        route_fields={"cuts":1,"surfs":0,"flights":0},
        destination_fields={"cuts":9,"surfs":9,"flights":9},
    )
    report = binding.execute()
    assert report.evidence["field_moves"] == {"cuts":1,"surfs":0,"flights":0}
    assert binding.verify(report).status.value == "failed"


def test_historical_report_does_not_acquire_new_diagnostics():
    _, binding, _, _ = _composer()
    assert "field_moves" not in binding.execute().evidence


def test_step_public_projection_retains_only_typed_field_counts():
    from test_bounded_player_episode import _CountingAuthority, _observer, _trajectory

    from pokemon_red_completion.bounded_player_episode import run_bounded_player_episode
    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
    original, meter, state = _observer(fail_first=False)
    trajectory, _ = _trajectory()
    def with_summary(execute):
        def wrapped():
            report = execute()
            return replace(report, evidence={**report.evidence,
                "field_moves":{"cuts":1,"surfs":2,"flights":3}})
        return wrapped
    def observed():
        value = original()
        return replace(value, binding_set=GoalBindingSet(value.binding_set.opportunities, tuple(
            replace(b, execute=with_summary(b.execute)) for b in value.binding_set.bindings
        )))
    result = run_bounded_player_episode(
        observe=observed, authority=_CountingAuthority(), authority_id="field-summary-test",
        trajectory=trajectory, budget_meter=meter, completion_satisfied=lambda _:False,
        stop_requested=lambda _:state["actions"] >= 5,
    )
    step = result.steps[0]
    assert step.public_dict()["field_moves"] == {"cuts":1,"surfs":2,"flights":3}
    assert "field_moves" not in replace(step, field_moves=None).public_dict()
