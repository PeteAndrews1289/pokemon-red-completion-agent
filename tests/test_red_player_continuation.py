from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import run_paired_red_bounded_player as runner
from test_red_player_checkpoint import _complete
from test_red_player_checkpoint import case as checkpoint_case

from pokemon_red_completion.executor import ReadOnlyController
from pokemon_red_completion.red_player_checkpoint import (
    RedPlayerCheckpointError,
    capture_red_player_terminal,
    publish_red_player_checkpoint,
)

case = checkpoint_case


@pytest.mark.parametrize("ready,battle,acts", [
    (True, False, False), (False, False, False), (True, True, False), (True, False, True),
])
def test_checkpoint_boundary_requires_action_free_ready_overworld(ready, battle, acts):
    count = [0]

    def observe():
        count[0] += int(acts)
        return SimpleNamespace(input_ready=ready, raw=SimpleNamespace(battle_state=battle))

    runtime = SimpleNamespace(adapter=SimpleNamespace(observe=observe))
    meter = SimpleNamespace(checkpoint=lambda: count[0])
    if ready and not battle and not acts:
        runner._require_safe_checkpoint_boundary(runtime, meter)
    else:
        with pytest.raises(runner.PairedRedBoundedPlayerRunError, match="unsafe_boundary"):
            runner._require_safe_checkpoint_boundary(runtime, meter)


def _readiness(store, arguments):
    return runner._Readiness(
        pair_id="continuation-child", source_commit="1" * 40,
        source_bundle_sha256="2" * 64, rom_path=Path("unused"),
        rom_sha256=arguments["rom_sha256"], capture=arguments["parent"],
        profile=SimpleNamespace(profile_sha256=arguments["profile_sha256"]),
        challenger_arm_id=runner.CAUSAL_ARM_ID, legacy_model=None, causal_record=None,
        calibration_record=None, model_file_sha256="3" * 64, model_sha256="4" * 64,
        decision_limit=4, private_root=store, output_path=Path("unused-output"),
        protected_paths=(), context_origin="training", save_terminal_checkpoints=True,
    )


def _completed(case, split=None):
    store, arguments, observation = case
    document = capture_red_player_terminal(**arguments)
    _complete(store, document, alter_header={"split": split or {
        "partition": "train", "root_lineage_id": "original-training-root",
    }})
    record = publish_red_player_checkpoint(store, document)
    return _readiness(store, arguments), (arguments["episode_id"], record["record_sha256"])


def test_continuation_changes_state_not_lineage_or_partition(case):
    readiness, ancestor = _completed(case)
    continued = runner._continue_readiness(readiness, (ancestor,))
    assert continued.capture.state_bytes == b"actual-terminal-state"
    assert continued.capture.state_bytes != readiness.capture.state_bytes
    assert continued.continuation_root_lineage_id == "original-training-root"
    assert continued.training_plan is None
    assert runner._continuation_header(continued) == {
        "continuation_chain": [{
            "episode_id": ancestor[0], "checkpoint_record_sha256": ancestor[1],
        }],
        "split": {"partition": "train", "root_lineage_id": "original-training-root"},
        "independent_root": False, "training_eligible": False,
    }
    continued.continuation.require_restored_observation(case[2])


@pytest.mark.parametrize("partition", ["development", "validation", "test", "unassigned"])
def test_continuation_never_relabels_other_partitions(case, partition):
    readiness, ancestor = _completed(case, {"partition": partition, "root_lineage_id": "foreign"})
    with pytest.raises(runner.PairedRedBoundedPlayerRunError, match="training_lineage"):
        runner._continue_readiness(readiness, (ancestor,))


def test_continuation_rejects_changed_hash_duplicate_and_wrong_parent(case):
    readiness, ancestor = _completed(case)
    with pytest.raises(RedPlayerCheckpointError, match="absent or changed"):
        runner._continue_readiness(readiness, ((ancestor[0], "0" * 64),))
    with pytest.raises(runner.PairedRedBoundedPlayerRunError, match="duplicate"):
        runner._continue_readiness(readiness, (ancestor, ancestor))
    continued = runner._continue_readiness(readiness, (ancestor,))
    with pytest.raises(RedPlayerCheckpointError, match="parent or scope"):
        runner._continue_readiness(continued, (ancestor,))


def test_two_saved_segments_retain_the_first_lineage(case):
    readiness, ancestor = _completed(case)
    first = runner._continue_readiness(readiness, (ancestor,))
    store, arguments, _ = case
    arguments["emulator"].state = b"second-terminal-state"
    second_document = capture_red_player_terminal(**{
        **arguments, "parent": first.capture, "episode_id": "second-parent",
    })
    _complete(store, second_document, alter_header=runner._continuation_header(first))
    second_record = publish_red_player_checkpoint(store, second_document)
    chain = (ancestor, ("second-parent", second_record["record_sha256"]))
    second = runner._continue_readiness(readiness, chain)
    assert second.capture.state_bytes == b"second-terminal-state"
    assert second.continuation_chain == chain
    assert second.continuation_root_lineage_id == "original-training-root"


@pytest.mark.parametrize("damage", [None, "semantics", "frames", "held"])
def test_actual_restore_is_checked_through_readonly_controls(case, monkeypatch, damage):
    readiness, ancestor = _completed(case)
    readiness = runner._continue_readiness(readiness, (ancestor,))
    emulator = SimpleNamespace(frame_count=12, pressed_buttons=frozenset())
    seen = []

    def runtime(**kwargs):
        assert isinstance(kwargs["emulator"], ReadOnlyController)
        seen.append("readonly")
        return object()

    def observe():
        seen.append("observe")
        if damage == "frames":
            emulator.frame_count += 1
        if damage == "held":
            emulator.pressed_buttons = frozenset({"a"})
        return (
            replace(case[2], semantic_state_sha256="0" * 64)
            if damage == "semantics" else case[2]
        )

    monkeypatch.setattr(runner, "build_red_goal_context_runtime", runtime)
    monkeypatch.setattr(runner, "_route_world", lambda _: None)
    monkeypatch.setattr(runner, "_player_observer", lambda *_: observe)
    if damage is None:
        runner._verify_continuation_restore(readiness, emulator)
    else:
        with pytest.raises((RedPlayerCheckpointError, runner.PairedRedBoundedPlayerRunError)):
            runner._verify_continuation_restore(readiness, emulator)
    assert seen == ["readonly", "observe"]


@pytest.mark.parametrize("override", [
    {"train_player": True}, {"context_origin": "development"},
    {"save_terminal_checkpoints": False}, {"challenger": runner.BASELINE_ARM_ID},
])
def test_unsupported_continuation_scope_fails_before_source_or_rom(override):
    args = SimpleNamespace(
        pair_id="new-continuation", continue_from_checkpoint=[("old", "a" * 64)],
        **{
            "train_player": False, "context_origin": "training",
            "save_terminal_checkpoints": True, "challenger": runner.CAUSAL_ARM_ID,
            **override,
        },
    )
    with pytest.raises(runner.PairedRedBoundedPlayerRunError, match="continuation_scope"):
        runner._prepare(args)


def test_continuation_executes_only_one_arm_without_fit_or_comparison(case, monkeypatch):
    readiness, ancestor = _completed(case)
    readiness = runner._continue_readiness(readiness, (ancestor,))
    arm_calls, writes = [], []
    # Checkpoint publishing itself is covered by the live-arm wiring test.
    readiness = replace(readiness, save_terminal_checkpoints=False)
    monkeypatch.setattr(runner, "_prepare", lambda _: readiness)
    monkeypatch.setattr(runner, "rom_adjacent_artifacts", lambda _: {})
    monkeypatch.setattr(runner, "_action_free_preflight", lambda _: {"actions": 0})
    monkeypatch.setattr(runner, "_challenger_authority", lambda _: object())

    def execute(_readiness, *, arm_id, **_kwargs):
        arm_calls.append(arm_id)
        return SimpleNamespace(
            trajectory_manifest_sha256="a" * 64,
            episode=SimpleNamespace(public_dict=lambda: {"completed_test_steps": 4}),
        )

    monkeypatch.setattr(runner, "_run_arm", execute)
    monkeypatch.setattr(runner, "compare_paired_bounded_player_arms", lambda **_: pytest.fail(
        "continuation unexpectedly compared against a replay"
    ))
    monkeypatch.setattr(runner, "_write_exclusive", lambda _, value: writes.append(value))
    result = runner._run(SimpleNamespace())
    assert arm_calls == [runner.CAUSAL_ARM_ID]
    assert result["model_fitted"] is False
    assert result["training_eligible"] is False
    assert result["independent_evaluation"] is False
    assert result["split"]["root_lineage_id"] == "original-training-root"
    assert writes == [result]


def test_live_arm_refuses_input_on_restore_mismatch(case, monkeypatch):
    readiness, ancestor = _completed(case)
    readiness = runner._continue_readiness(readiness, (ancestor,))
    order = []

    class Emulator:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            order.append("closed")

        def load_state_bytes(self, state):
            assert state == b"actual-terminal-state"
            order.append("loaded")

    def reject(_readiness, _emulator):
        order.append("verified")
        raise RedPlayerCheckpointError("restored checkpoint semantic state differs")

    monkeypatch.setattr(runner, "PyBoyAdapter", lambda *_a, **_k: Emulator())
    monkeypatch.setattr(runner, "_verify_continuation_restore", reject)
    monkeypatch.setattr(runner, "WindowedFrameBudgetController", lambda *_a, **_k: pytest.fail(
        "controller became available before checkpoint agreement"
    ))
    with pytest.raises(RedPlayerCheckpointError, match="semantic state differs"):
        runner._run_arm(readiness, arm_id=runner.CAUSAL_ARM_ID, authority=object())
    assert order == ["loaded", "verified", "closed"]
    state = readiness.private_root.inspect_episode_state("continuation-child-causal")
    assert state.status != "absent"
