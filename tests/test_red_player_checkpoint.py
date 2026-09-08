from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_paired_red_bounded_player_script import _observation

from pokemon_red_completion.bounded_player_episode import (
    BoundedPlayerResult,
    BoundedPlayerStep,
    BoundedPlayerStopReason,
)
from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_composition_runtime import CompositionBudgetCheckpoint
from pokemon_red_completion.goal_manager_context_catalog import parse_goal_manager_context_capture
from pokemon_red_completion.goal_manager_runtime import GoalDecisionOutcome
from pokemon_red_completion.private_artifacts import PrivateArtifactError, initialize_private_root
from pokemon_red_completion.red_player_checkpoint import (
    LEGACY_CHECKPOINT_SCHEMA,
    MAXIMUM_STATE_BYTES,
    RedPlayerCheckpointError,
    capture_red_failure_state,
    capture_red_player_terminal,
    capture_red_skill_recovery,
    open_red_player_checkpoint,
    publish_red_player_checkpoint,
    recover_completed_red_player_checkpoint,
)


class _Emulator:
    frame_count = 37
    pressed_buttons = frozenset()
    state = b"actual-terminal-state"
    mutation = None

    def save_state_bytes(self):
        if self.mutation is not None:
            self.mutation()
        return self.state


class _Meter:
    actions = 2

    def checkpoint(self):
        return CompositionBudgetCheckpoint(self.actions, 37)


@pytest.mark.parametrize("mode", ["safe", "held", "frames", "actions", "buttons", "empty",
                                  "oversize"])
def test_failure_state_preserves_unsafe_input_without_certifying_a_checkpoint(mode):
    emulator, meter = _Emulator(), _Meter()
    if mode == "held":
        emulator.pressed_buttons = frozenset({"a", "left"})
    elif mode == "frames":
        emulator.mutation = lambda: setattr(emulator, "frame_count", 38)
    elif mode == "actions":
        emulator.mutation = lambda: setattr(meter, "actions", 3)
    elif mode == "buttons":
        emulator.mutation = lambda: setattr(emulator, "pressed_buttons", frozenset({"a"}))
    elif mode == "empty":
        emulator.state = b""
    elif mode == "oversize":
        emulator.state = b"x" * (MAXIMUM_STATE_BYTES + 1)
    if mode not in {"safe", "held"}:
        with pytest.raises(RedPlayerCheckpointError):
            capture_red_failure_state(emulator=emulator, meter=meter)
        return
    record = capture_red_failure_state(emulator=emulator, meter=meter)
    assert base64.urlsafe_b64decode(record["state_base64"]) == emulator.state
    assert record["state_sha256"] == hashlib.sha256(emulator.state).hexdigest()
    assert record["admitted_continuation"] is record["training_target"] is False
    assert record["safe_checkpoint"] is False
    assert record["held_buttons"] == (["a", "left"] if mode == "held" else [])
    assert record["emulator_frame_count"] == record["frames"] == 37
    assert record["actions"] == 2


def test_failure_state_is_durable_in_failed_private_episode_not_an_open_checkpoint(case, tmp_path):
    store, _, _ = case
    emulator = _Emulator()
    emulator.state = bytes(range(256))
    record = capture_red_failure_state(emulator=emulator, meter=_Meter())
    writer = store.begin_episode("failure-state-test")
    writer.append("episode", {"episode_id": "failure-state-test"})
    writer.append("failure_state", record, durable=True)
    writer.abort("test_failure")
    failed = tmp_path / "private" / "failure-state-test.failed.partial"
    saved = json.loads((failed / "failure_state.jsonl").read_text())
    assert base64.urlsafe_b64decode(saved["state_base64"]) == bytes(range(256))
    assert saved["safe_checkpoint"] is saved["admitted_continuation"] is False
    with pytest.raises(PrivateArtifactError):
        store.open_episode("failure-state-test")


@pytest.mark.parametrize("mode", ["safe", "held", "frames", "actions", "empty", "oversize"])
def test_skill_recovery_is_read_only_and_not_an_admitted_checkpoint(mode):
    emulator, meter = _Emulator(), _Meter()
    if mode == "held":
        emulator.pressed_buttons = frozenset({"a"})
    elif mode == "frames":
        emulator.mutation = lambda: setattr(emulator, "frame_count", 38)
    elif mode == "actions":
        emulator.mutation = lambda: setattr(meter, "actions", 3)
    elif mode == "empty":
        emulator.state = b""
    elif mode == "oversize":
        emulator.state = b"x" * (MAXIMUM_STATE_BYTES + 1)
    if mode != "safe":
        with pytest.raises(RedPlayerCheckpointError):
            capture_red_skill_recovery(emulator=emulator, meter=meter)
        return
    record = capture_red_skill_recovery(emulator=emulator, meter=meter)
    assert base64.urlsafe_b64decode(record["state_base64"]) == emulator.state
    assert record["state_sha256"] == hashlib.sha256(emulator.state).hexdigest()
    assert record["admitted_continuation"] is record["training_target"] is False
    assert (record["actions"], record["frames"]) == (2, 37)


def test_skill_recovery_serializes_binary_state_through_real_private_writer(case):
    store, _, _ = case
    emulator = _Emulator()
    # Ordinary base64 produces '/' here. The actual private writer must accept
    # URL-safe encoding without weakening its unrelated filesystem-path guard.
    emulator.state = bytes(range(256))
    record = capture_red_skill_recovery(emulator=emulator, meter=_Meter())
    assert "/" not in record["state_base64"]
    with store.begin_episode("skill-recovery-test") as writer:
        writer.append("episode", {"episode_id": "skill-recovery-test"})
        writer.append("skill_recovery", record, durable=True)
    assert list(store.open_episode("skill-recovery-test").iter_stream("skill_recovery")) == [record]
    assert base64.urlsafe_b64decode(record["state_base64"]) == emulator.state


@pytest.fixture
def case(tmp_path: Path):
    repository, private = tmp_path / "repo", tmp_path / "private"
    repository.mkdir()
    private.mkdir()
    store = initialize_private_root(
        private, repository_root=repository,
        device_id=lambda path: 2 if path == private.resolve() else 1,
        git_worktree_probe=lambda path: False,
    )
    parent_bytes = b"original-training-state"
    envelope = CapturedProgressEnvelope(
        hashlib.sha256(parent_bytes).hexdigest(), "train-parent", "Inherited progress", 1, 9,
        ("verified-old-quest",),
    )
    parent = parse_goal_manager_context_capture(
        parent_bytes, json.dumps(envelope.to_dict()).encode("ascii")
    )
    observation = _observation(storage=4)
    step = BoundedPlayerStep(
        decision_ordinal=1, selected_kind=GoalKind.RESUPPLY,
        status=GoalDecisionOutcome.SUCCEEDED, failure_reason=None, recovery_attempt=False,
        available_goal_count=2, actions_executed=2, frames_executed=37,
        semantic_state_changed=True, policy_context_sha256="a" * 64,
        available_menu_sha256="b" * 64,
        collection_before=observation.collection, collection_after=observation.collection,
    )
    result = BoundedPlayerResult("actor", BoundedPlayerStopReason.DECISION_LIMIT, (step,), False)
    emulator, meter = _Emulator(), _Meter()
    arguments = dict(
        emulator=emulator, meter=meter, observe=lambda: observation, parent=parent,
        result=result, episode_id="continuation-test", profile_sha256="5" * 64,
        rom_sha256="6" * 64, model_sha256="7" * 64,
        source_commit="8" * 40, source_bundle_sha256="9" * 64, context_origin="training",
    )
    return store, arguments, observation


def _complete(store, document, *, alter_header=None, terminal=None, complete=True):
    writer = store.begin_episode(document["episode_id"])
    metadata = {
        name: document[key] for name, key in (
            ("state_sha256", "original_state_sha256"),
            ("envelope_sha256", "original_envelope_sha256"),
            *((key, key) for key in (
                "profile_sha256", "rom_sha256", "model_sha256", "source_commit",
                "source_bundle_sha256", "context_origin",
            )),
        )
    }
    if alter_header:
        metadata.update(alter_header)
    writer.append("episode", {"episode_id": document["episode_id"], "metadata": metadata})
    writer.append("checkpoint", document, durable=True)
    writer.append("events", {
        "kind": "terminal", "payload": {
            "status": "complete", "bounded_player": terminal or document["terminal_result"],
        },
    }, durable=True)
    if complete:
        writer.complete()
    return writer


def _open(store, arguments, summary, **changes):
    keywords = dict(
        episode_id=arguments["episode_id"], expected_record_sha256=summary["record_sha256"],
        original_parent=arguments["parent"], expected_profile_sha256=arguments["profile_sha256"],
        expected_rom_sha256=arguments["rom_sha256"], expected_context_origin="training",
    )
    return open_red_player_checkpoint(store, **{**keywords, **changes})


def test_durable_state_round_trip_preserves_parent_scope_and_quest_claims(case):
    store, arguments, observation = case
    document = capture_red_player_terminal(**arguments)
    _complete(store, document)
    summary = recover_completed_red_player_checkpoint(store, arguments["episode_id"])
    checkpoint = _open(store, arguments, summary)
    assert checkpoint.capture.state_bytes == b"actual-terminal-state"
    assert checkpoint.capture.state_sha256 != arguments["parent"].state_sha256
    assert checkpoint.original_state_sha256 == arguments["parent"].state_sha256
    assert checkpoint.capture.envelope.verified_objective_ids == ("verified-old-quest",)
    checkpoint.require_restored_observation(observation)
    with pytest.raises(TypeError):
        checkpoint.collection["living_species"] = 999
    assert summary["independent_root"] is False
    assert summary["training_example"] is False
    assert summary["automatic_resume_authorized"] is False
    assert "state_base64" not in json.dumps(summary)
    # Recovery republishes identical durable bytes, never another emulator action.
    assert recover_completed_red_player_checkpoint(store, arguments["episode_id"]) == summary


@pytest.mark.parametrize("mutation", [None, "origin", "costs", "model", "type", "rewind"])
def test_separate_recovery_authenticates_failed_prefix_and_keeps_zero_labels(case, mutation):
    from pokemon_red_completion.provenance import canonical_sha256
    from pokemon_red_completion.red_failure_recovery import (
        RedFailureRecoveryError,
        RedFailureRecoveryResult,
    )

    store, arguments, observation = case
    failed_emulator = _Emulator()
    failed_emulator.state = b"exact-failed-battle-not-old-quantum"
    failed = capture_red_failure_state(emulator=failed_emulator, meter=_Meter())
    previous = {**failed, "state_sha256": "a" * 64}
    writer = store.begin_episode("failed-choice")
    writer.append("episode", {"episode_id": "failed-choice", "metadata": {
        "state_sha256": arguments["parent"].state_sha256,
        "envelope_sha256": arguments["parent"].envelope_sha256,
        "profile_sha256": arguments["profile_sha256"],
        "rom_sha256": arguments["rom_sha256"], "context_origin": "training",
    }})
    writer.append("skill_recovery", previous)
    writer.append("failure_state", failed)
    writer.abort("unsafe_boundary")
    failed_manifest = store.open_failed_episode("failed-choice").manifest_sha256
    result = RedFailureRecoveryResult(
        "failed-choice", failed_manifest, failed["state_sha256"], 2, 37, 2, 37,
    )
    arguments["result"] = result
    document = capture_red_player_terminal(**arguments)
    assert document["terminal_result"]["training_examples"] == 0
    assert document["terminal_result"]["authority_decisions"] == 0
    if mutation == "origin":
        document["terminal_result"]["failure_origin"]["manifest_sha256"] = "f" * 64
    elif mutation == "costs":
        document["terminal_result"]["total_actions"] = 1
    elif mutation == "model":
        document["terminal_result"]["authority_decisions"] = 1
    elif mutation == "type":
        document["terminal_result"]["schema"] = "pokemon.core.bounded-player-episode-result.v1"
    elif mutation == "rewind":
        document["terminal_result"]["failure_origin"]["state_sha256"] = "a" * 64
    document["terminal_result_sha256"] = canonical_sha256(document["terminal_result"])
    writer = _complete(store, document, complete=False)
    writer.append("executions", {"frames": 17})
    writer.append("executions", {"frames": 20})
    writer.complete()
    if mutation:
        with pytest.raises(RedFailureRecoveryError):
            publish_red_player_checkpoint(store, document)
        return
    summary = publish_red_player_checkpoint(store, document)
    checkpoint = _open(store, arguments, summary)
    checkpoint.require_restored_observation(observation)
    assert checkpoint.capture.envelope == replace(
        arguments["parent"].envelope, state_sha256=checkpoint.capture.state_sha256,
    )
    assert store.open_failed_episode("failed-choice").manifest_sha256 == failed_manifest


def test_safe_failed_goal_retains_exact_state_without_becoming_a_success_or_label(case):
    store, arguments, observation = case
    previous = arguments["result"]
    failed = replace(previous.steps[0], selected_kind=GoalKind.ACQUIRE_SPECIES,
                     status=GoalDecisionOutcome.FAILED,
                     failure_reason=GoalFailureReason.BINDING_FAILED)
    arguments["result"] = replace(previous, steps=(failed,),
                                  stop_reason=BoundedPlayerStopReason.VERIFIED_FAILURE)
    document = capture_red_player_terminal(**arguments)
    _complete(store, document)
    summary = publish_red_player_checkpoint(store, document)
    restored = _open(store, arguments, summary)
    restored.require_restored_observation(observation)
    assert restored.capture.state_bytes == b"actual-terminal-state"
    assert document["terminal_result"]["steps"][0]["status"] == "failed"
    assert document["terminal_result"]["steps"][0]["failure_reason"] == "binding_failed"
    assert document["terminal_result"]["stop_reason"] == "verified_failure"
    assert summary["training_example"] is summary["automatic_resume_authorized"] is False


def test_binary_save_with_path_like_base64_round_trips_through_real_private_store(case):
    store, arguments, _ = case
    state = b"\xff" * 32
    assert b"/" in base64.b64encode(state)
    arguments["emulator"].state = state
    document = capture_red_player_terminal(**arguments)
    assert "/" not in document["state_base64"]
    _complete(store, document)
    summary = publish_red_player_checkpoint(store, document)
    checkpoint = _open(store, arguments, summary)
    assert checkpoint.capture.state_bytes == state
    assert checkpoint.capture.state_sha256 == hashlib.sha256(state).hexdigest()


def test_settled_unsuccessful_search_retains_negative_outcome_and_safe_checkpoint(case):
    store, arguments, observation = case
    result = arguments["result"]
    arguments["result"] = replace(
        result,
        stop_reason=BoundedPlayerStopReason.RECOVERY_GOAL_REPEATED,
        steps=(replace(
            result.steps[0], selected_kind=GoalKind.ACQUIRE_SPECIES,
            status=GoalDecisionOutcome.FAILED,
            failure_reason=GoalFailureReason.SEARCH_EXHAUSTED,
        ),),
    )
    document = capture_red_player_terminal(**arguments)
    _complete(store, document)
    summary = recover_completed_red_player_checkpoint(store, arguments["episode_id"])
    checkpoint = _open(store, arguments, summary)
    checkpoint.require_restored_observation(observation)
    assert checkpoint.capture.state_bytes == b"actual-terminal-state"
    terminal = document["terminal_result"]
    assert terminal["completion_satisfied"] is False
    assert terminal["stop_reason"] == "recovery_goal_repeated"
    assert terminal["total_actions"] == 2
    assert terminal["total_frames"] == 37
    assert terminal["steps"][0]["status"] == "failed"
    assert terminal["steps"][0]["failure_reason"] == "search_exhausted"
    assert summary["training_example"] is False


def test_legacy_checkpoint_payload_remains_readable_at_original_address(case):
    store, arguments, _ = case
    document = capture_red_player_terminal(**arguments)
    document["schema"] = LEGACY_CHECKPOINT_SCHEMA
    document["state_base64"] = base64.b64encode(arguments["emulator"].state).decode("ascii")
    _complete(store, document)
    checkpoint = _open(store, arguments, publish_red_player_checkpoint(store, document))
    assert checkpoint.capture.state_bytes == arguments["emulator"].state


@pytest.mark.parametrize("field,value", [
    ("expected_record_sha256", "0" * 64),
    ("expected_profile_sha256", "0" * 64),
    ("expected_rom_sha256", "0" * 64),
    ("expected_context_origin", "development"),
])
def test_reopen_rejects_relabeling_or_changed_identity(case, field, value):
    store, arguments, _ = case
    document = capture_red_player_terminal(**arguments)
    _complete(store, document)
    summary = publish_red_player_checkpoint(store, document)
    with pytest.raises(RedPlayerCheckpointError):
        _open(store, arguments, summary, **{field: value})


@pytest.mark.parametrize("mutation", ["frames", "actions", "buttons", "semantic", "oversize"])
def test_capture_rejects_hidden_effects_or_oversize_state(case, mutation):
    _, arguments, observation = case
    emulator, meter = arguments["emulator"], arguments["meter"]
    if mutation == "semantic":
        observations = iter((observation, replace(observation, semantic_state_sha256="f" * 64)))
        arguments["observe"] = lambda: next(observations)
    elif mutation == "oversize":
        emulator.state = b"x" * (MAXIMUM_STATE_BYTES + 1)
    else:
        target, field, value = {
            "frames": (emulator, "frame_count", 38),
            "actions": (meter, "actions", 3),
            "buttons": (emulator, "pressed_buttons", frozenset({"a"})),
        }[mutation]
        emulator.mutation = lambda: setattr(target, field, value)
    with pytest.raises(RedPlayerCheckpointError):
        capture_red_player_terminal(**arguments)


def test_incomplete_episode_cannot_publish_a_usable_checkpoint(case):
    store, arguments, _ = case
    document = capture_red_player_terminal(**arguments)
    writer = _complete(store, document, complete=False)
    try:
        with pytest.raises(PrivateArtifactError):
            recover_completed_red_player_checkpoint(store, arguments["episode_id"])
    finally:
        writer.abort("test_interruption")


@pytest.mark.parametrize("mismatch", ["header", "terminal", "capture"])
def test_checkpoint_authenticates_independent_completed_trajectory(case, mismatch):
    store, arguments, _ = case
    document = capture_red_player_terminal(**arguments)
    _complete(
        store, document,
        alter_header={"model_sha256": "0" * 64} if mismatch == "header" else None,
        terminal={"status": "different"} if mismatch == "terminal" else None,
    )
    if mismatch == "capture":
        document["semantic_state_sha256"] = "0" * 64
    with pytest.raises(RedPlayerCheckpointError):
        publish_red_player_checkpoint(store, document)


def test_fresh_restored_observation_must_match_both_semantics_and_ledger(case):
    store, arguments, observation = case
    document = capture_red_player_terminal(**arguments)
    _complete(store, document)
    checkpoint = _open(store, arguments, publish_red_player_checkpoint(store, document))
    for changed in (
        replace(observation, semantic_state_sha256="0" * 64),
        replace(observation, collection=replace(observation.collection, storage_headroom=3)),
    ):
        with pytest.raises(RedPlayerCheckpointError, match="restored"):
            checkpoint.require_restored_observation(changed)
