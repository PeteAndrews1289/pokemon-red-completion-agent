from types import SimpleNamespace

import pytest
from run_paired_red_bounded_player import _player_limits
from test_red_player_training import _plan

from pokemon_red_completion.red_player_training_plan import (
    RedPlayerTrainingPlan,
    continue_red_player_training,
    declare_completion_dose,
)


def completion_plan():
    original = _plan(SimpleNamespace(model_sha256="1" * 64))
    continuation = continue_red_player_training(
        original,
        capture=SimpleNamespace(state_sha256="2" * 64, envelope_sha256="3" * 64),
        root_lineage_id="goal-root-1",
        episode_id="parent",
        checkpoint_sha256="4" * 64,
        restore_profile_sha256="5" * 64,
        execution_profile_sha256="6" * 64,
    )
    return original, continuation, declare_completion_dose(continuation)


def test_completion_dose_is_new_plan_and_preserves_old_normalization():
    original, continuation, complete = completion_plan()
    assert original.maximum_actions == continuation.maximum_actions == 6000
    assert original.maximum_frames == continuation.maximum_frames == 600000
    assert complete.maximum_actions == 30000
    assert complete.maximum_frames == 3000000
    assert len({p.plan_sha256 for p in (original, continuation, complete)}) == 3
    assert dict(complete.document)["continuation_checkpoint_sha256"] == "4" * 64
    with pytest.raises(ValueError, match="authenticated continuation"):
        declare_completion_dose(original)


@pytest.mark.parametrize(
    "field,value",
    [
        ("maximum_actions", 30001),
        ("maximum_actions", True),
        ("maximum_frames", 3000001),
        ("maximum_frames", 600000),
    ],
)
def test_completion_dose_rejects_forged_or_old_limits(field, value):
    _, _, complete = completion_plan()
    with pytest.raises(ValueError, match="dose differs"):
        RedPlayerTrainingPlan({**complete.document, field: value})


@pytest.mark.parametrize("count", [1, 2, 4])
def test_player_hard_limits_match_declared_completion_dose(count):
    original, _, complete = completion_plan()
    for plan, enabled in ((original, False), (complete, True)):
        limits = _player_limits(count, completion_dose=enabled)
        assert limits.max_actions_per_decision == plan.maximum_actions
        assert limits.max_frames_per_decision == plan.maximum_frames
        assert limits.max_total_actions == count * plan.maximum_actions
        assert limits.max_total_frames == count * plan.maximum_frames


@pytest.mark.parametrize("completion", [False, True])
def test_completion_plan_still_authenticates_its_parent_checkpoint(completion):
    from pokemon_red_completion.red_player_training_dataset import _require_continuation_origin

    _, continued, complete = completion_plan()
    plan = complete if completion else continued
    calls = []

    def find(*args, **kwargs):
        calls.append((args, kwargs))
        return None

    with pytest.raises(ValueError, match="checkpoint differs"):
        _require_continuation_origin(SimpleNamespace(find_sealed_record=find), plan)
    assert len(calls) == 1
