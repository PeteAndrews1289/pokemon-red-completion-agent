from dataclasses import replace

import pytest
from test_bounded_player_episode import _complete, _Meter, _observer, _trajectory
from test_routed_semantic_goal import _composer

from pokemon_red_completion.bounded_player_episode import run_bounded_player_episode
from pokemon_red_completion.goal_manager_runtime import CompletionFirstGoalTeacher
from pokemon_red_completion.storage_preparation import StoragePreparationSummary

SUMMARY = {
    "box_rotations": 1,
    "collection_preserved": True,
    "setup_training_rows": 0,
    "actions_executed": 1,
    "frames_executed": 10,
    "initial_headroom": 1,
    "prepared_headroom": 20,
}


def test_summary_preserves_old_absent_costs_without_inventing_zero():
    old = {k: v for k, v in SUMMARY.items() if k not in {"actions_executed", "frames_executed"}}
    assert (
        StoragePreparationSummary.from_evidence({"storage_preparation": old}).public_dict() == old
    )
    assert StoragePreparationSummary.from_evidence({}) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("box_rotations", True),
        ("box_rotations", 2),
        ("setup_training_rows", 1),
        ("collection_preserved", False),
        ("collection_preserved", 1),
        ("actions_executed", -1),
        ("frames_executed", True),
        ("prepared_headroom", 27),
        ("private_path", "/private/location"),
        ("actions_executed", None),
    ],
)
def test_summary_rejects_untrusted_or_misleading_fields(field, value):
    with pytest.raises(ValueError):
        StoragePreparationSummary.from_evidence({"storage_preparation": {**SUMMARY, field: value}})


def test_routing_preserves_only_typed_storage_diagnostics_and_original_total_cost():
    _, binding, _, _ = _composer(storage_preparation=SUMMARY)
    report = binding.execute()
    assert report.evidence["storage_preparation"] == SUMMARY
    assert (report.actions_executed, report.frames_executed) == (5, 50)
    assert "private_route" not in report.evidence
    _, binding, _, _ = _composer(storage_preparation={**SUMMARY, "path": "/private/location"})
    with pytest.raises(ValueError):
        binding.execute()


def test_bounded_player_retains_storage_cost_without_an_extra_decision():
    observe, meter, state = _observer(fail_first=False)

    def enriched():
        observation = observe()
        bindings = []
        for binding in observation.binding_set.bindings:

            def execute(original=binding.execute):
                report = original()
                return replace(report, evidence={**report.evidence, "storage_preparation": SUMMARY})

            bindings.append(replace(binding, execute=execute))
        return replace(
            observation, binding_set=replace(observation.binding_set, bindings=tuple(bindings))
        )

    trajectory, _ = _trajectory()
    result = run_bounded_player_episode(
        authority=CompletionFirstGoalTeacher(),
        authority_id="storage-support-test",
        observe=enriched,
        budget_meter=_Meter(state),
        trajectory=trajectory,
        completion_satisfied=_complete,
    )
    assert len(result.steps) == 2
    for step in result.steps:
        assert step.public_dict()["storage_preparation"] == SUMMARY
        assert (step.actions_executed, step.frames_executed) == (5, 50)
