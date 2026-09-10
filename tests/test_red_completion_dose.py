from types import SimpleNamespace

import pytest
from run_paired_red_bounded_player import _checkpoint_completion_dose, _player_limits
from test_red_player_training import _plan

from pokemon_red_completion.red_player_training_plan import (
    RedPlayerTrainingPlan,
    continue_red_player_training,
    declare_completion_dose,
)


def completion_plan(feature_version=1):
    original = _plan(SimpleNamespace(model_sha256="1" * 64, feature_version=feature_version))
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


@pytest.mark.parametrize("feature_version", [1, 2, 3])
def test_completion_dose_is_new_plan_and_preserves_old_normalization(feature_version):
    original, continuation, complete = completion_plan(feature_version)
    assert original.maximum_actions == continuation.maximum_actions == 6000
    assert original.maximum_frames == continuation.maximum_frames == 600000
    assert complete.maximum_actions == 30000
    assert complete.maximum_frames == 3000000
    assert len({p.plan_sha256 for p in (original, continuation, complete)}) == 3
    assert (
        original.document["behavior_policy_id"]
        == continuation.document["behavior_policy_id"]
        == complete.document["behavior_policy_id"]
    )
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


@pytest.mark.parametrize("feature_version", [1, 2, 3])
def test_restore_dose_comes_from_authenticated_parent_not_successor(feature_version):
    original, continued, completed = completion_plan(feature_version)
    for plan, expected in ((original, False), (continued, False), (completed, True)):
        assert _checkpoint_completion_dose({
            "metadata": {"player_training_plan": plan.document},
        }) is expected
    assert _checkpoint_completion_dose({"metadata": {}}) is False
    with pytest.raises(ValueError):
        _checkpoint_completion_dose({"metadata": {"player_training_plan": {
            **completed.document, "maximum_actions": 30001,
        }}})
    with pytest.raises(RuntimeError, match="continuation_parent_plan"):
        _checkpoint_completion_dose({"metadata": {"player_training_plan": "v4"}})


@pytest.mark.parametrize("parent_dose,successor_dose", [(False, True), (True, False)])
def test_restore_observer_uses_parent_dose_and_still_authenticates(
    monkeypatch, parent_dose, successor_dose,
):
    import run_paired_red_bounded_player as module

    calls = []
    expected = object()
    readiness = SimpleNamespace(
        continuation=SimpleNamespace(
            collection={}, search_memory=None,
            require_restored_observation=lambda observation: calls.append(observation),
        ),
        restore_profile=object(), profile=object(), capture=object(),
        quote_resource_costs=True, restore_completion_dose=parent_dose,
        completion_dose=successor_dose,
    )
    emulator = SimpleNamespace(frame_count=0, pressed_buttons=())
    monkeypatch.setattr(module, "build_red_goal_context_runtime", lambda **_kw: object())
    monkeypatch.setattr(module, "_route_world", lambda _ready: None)
    def observer(*_args, **kwargs):
        assert kwargs["completion_dose"] is parent_dose
        return lambda: expected
    monkeypatch.setattr(module, "_player_observer", observer)
    module._verify_continuation_restore(readiness, emulator)
    assert calls == [expected]


@pytest.mark.parametrize("parent_dose", [False, True])
def test_continuation_chain_carries_final_parent_observer_mode(monkeypatch, parent_dose):
    from dataclasses import MISSING, fields

    import run_paired_red_bounded_player as module

    _, continued, completed = completion_plan()
    plan = completed if parent_dose else continued
    profile = SimpleNamespace(profile_sha256="a" * 64)
    header = {"metadata": {
        "player_training_plan": plan.document, "profile_sha256": profile.profile_sha256,
        "split": {"partition": "train", "root_lineage_id": "one-root"},
    }}
    checkpoint = SimpleNamespace(capture=object(), search_memory=None)
    required = {
        f.name: None for f in fields(module._Readiness)
        if f.default is MISSING and f.default_factory is MISSING
    }
    ready = module._Readiness(**{
        **required, "profile": profile,
        "private_root": SimpleNamespace(open_episode=lambda _id: SimpleNamespace(
            read_header=lambda: header,
        )),
    }, completion_dose=not parent_dose)
    monkeypatch.setattr(module, "open_red_player_checkpoint", lambda *_a, **_k: checkpoint)
    continued_ready = module._continue_readiness(ready, (("parent", "b" * 64),))
    assert continued_ready.restore_completion_dose is parent_dose
    assert continued_ready.completion_dose is not parent_dose
    assert continued_ready.restore_profile is profile
