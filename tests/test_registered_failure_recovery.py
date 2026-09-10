from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_paired_red_bounded_player_script import _observation
from test_private_artifacts import _make_store
from test_registered_learning_bridge import observations

from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.goal_manager_composition_runtime import CompositionBudgetCheckpoint
from pokemon_red_completion.goal_manager_context_catalog import parse_goal_manager_context_capture
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_failure_recovery import (
    RECOVERY_CHECKPOINT_SCHEMA,
    REGISTERED_RECOVERY_CHECKPOINT_SCHEMA,
    RedFailureRecoveryError,
    RedFailureRecoveryResult,
)
from pokemon_red_completion.red_player_checkpoint import (
    CHECKPOINT_KIND,
    REGISTERED_PLAYER_CHECKPOINT_SCHEMA,
    RedPlayerCheckpointError,
    capture_red_failure_state,
    capture_red_player_terminal,
    checkpoint_record_id,
    open_red_player_checkpoint,
    publish_red_player_checkpoint,
    recover_completed_red_player_checkpoint,
)
from pokemon_red_completion.red_recorded_support import RedRecordedSupportResult
from pokemon_red_completion.red_registered_observation import project_registered_observation
from pokemon_red_completion.red_registration_session import (
    observe_registration,
    validate_terminal_registration,
)
from pokemon_red_completion.registered_checkpoint import (
    REGISTERED_CHECKPOINT_SCHEMA,
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


@pytest.fixture
def case(tmp_path: Path):
    store_root = tmp_path / "root"
    store_root.mkdir(parents=True, exist_ok=True)
    _, _, store = _make_store(store_root)

    parent_bytes = b"original-training-state"
    envelope = CapturedProgressEnvelope(
        hashlib.sha256(parent_bytes).hexdigest(),
        "train-parent",
        "Inherited progress",
        1,
        9,
        ("verified-old-quest",),
    )
    parent = parse_goal_manager_context_capture(
        parent_bytes, json.dumps(envelope.to_dict()).encode("ascii")
    )

    _, before, _, policy = observations(tmp_path / "fixture")
    reg_checkpoint = project_registered_observation(before, policy).registered_checkpoint
    obs = replace(_observation(storage=4), collection=reg_checkpoint)

    failed_emulator = _Emulator()
    failed_emulator.state = b"exact-failed-battle-not-old-quantum"
    failed = capture_red_failure_state(emulator=failed_emulator, meter=_Meter())

    writer = store.begin_episode("failed-choice")
    writer.append(
        "episode",
        {
            "episode_id": "failed-choice",
            "metadata": {
                "state_sha256": parent.state_sha256,
                "envelope_sha256": parent.envelope_sha256,
                "profile_sha256": "5" * 64,
                "rom_sha256": "6" * 64,
                "context_origin": "training",
            },
        },
    )
    writer.append("failure_state", failed)
    writer.abort("unsafe_boundary")
    failed_manifest = store.open_failed_episode("failed-choice").manifest_sha256

    result = RedFailureRecoveryResult(
        "failed-choice",
        failed_manifest,
        failed["state_sha256"],
        failed_actions=2,
        failed_frames=37,
        actions=2,
        frames=37,
    )

    emulator, meter = _Emulator(), _Meter()
    arguments = dict(
        emulator=emulator,
        meter=meter,
        observe=lambda: obs,
        parent=parent,
        result=result,
        episode_id="registered-recovery-test",
        profile_sha256="5" * 64,
        rom_sha256="6" * 64,
        model_sha256="7" * 64,
        source_commit="8" * 40,
        source_bundle_sha256="9" * 64,
        context_origin="training",
    )
    return store, arguments, obs, policy, failed, failed_manifest


def _complete_registered_recovery(
    store,
    document,
    *,
    alter_header=None,
    alter_executions=None,
    alter_decisions=None,
    complete=True,
):
    writer = store.begin_episode(document["episode_id"])
    metadata = {
        name: document[key]
        for name, key in (
            ("state_sha256", "original_state_sha256"),
            ("envelope_sha256", "original_envelope_sha256"),
            *(
                (key, key)
                for key in (
                    "profile_sha256",
                    "rom_sha256",
                    "model_sha256",
                    "source_commit",
                    "source_bundle_sha256",
                    "context_origin",
                )
            ),
        )
    }
    if alter_header:
        metadata.update(alter_header)
    writer.append("episode", {"episode_id": document["episode_id"], "metadata": metadata})
    writer.append("checkpoint", document, durable=True)
    writer.append(
        "events",
        {
            "kind": "terminal",
            "payload": {
                "status": "complete",
                "bounded_player": document["terminal_result"],
            },
        },
        durable=True,
    )
    if alter_executions is not None:
        for row in alter_executions:
            writer.append("executions", row)
    else:
        writer.append("executions", {"frames": 17})
        writer.append("executions", {"frames": 20})
    if alter_decisions is not None:
        for row in alter_decisions:
            writer.append("decisions", row)
    if complete:
        writer.complete()
    return writer


@pytest.mark.parametrize('mutation', [None, 'state', 'execution'])
def test_settled_admission_requires_exact_failure_bytes_and_zero_inputs(case, mutation):
    import base64

    store, arguments, _, policy, failed, _ = case
    arguments['emulator'].state = (
        b'changed-state' if mutation == 'state'
        else base64.urlsafe_b64decode(failed['state_base64'])
    )
    arguments['meter'] = SimpleNamespace(
        checkpoint=lambda: CompositionBudgetCheckpoint(controller_actions=0, emulator_frames=0)
    )
    arguments['result'] = replace(arguments['result'], actions=0, frames=0, settled_admission=True)
    document = capture_red_player_terminal(**arguments)
    row = observe_registration(
        SimpleNamespace(collection_observation=policy.initial_collection),
        seen=frozenset(range(1, 152)), run_id=policy.run_id,
        rom_sha256=arguments['rom_sha256'], snapshot_sha256=document['state_sha256'], sequence=1,
    )
    document['registration_observation'] = row.document()
    _complete_registered_recovery(
        store, document, alter_executions=[{'frames': 0}] if mutation == 'execution' else [],
    )
    if mutation:
        with pytest.raises(ValueError):
            publish_red_player_checkpoint(store, document)
    else:
        summary = publish_red_player_checkpoint(store, document)
        assert summary['training_example'] is False
        assert document['terminal_result']['total_actions'] == 0
        assert document['terminal_result']['total_frames'] == 0
        assert document['state_sha256'] == failed['state_sha256']
        assert document['terminal_result']['failure_origin']['actions'] == 2


@pytest.mark.parametrize('mode,actions,frames', [
    (False, 0, 0), (True, 1, 0), (True, 0, 1), (True, False, 0), (1, 0, 0),
])
def test_settled_admission_cannot_relax_positive_cost_recovery(case, mode, actions, frames):
    _, arguments, *_ = case
    with pytest.raises(ValueError):
        replace(
            arguments['result'], settled_admission=mode, actions=actions, frames=frames,
        ).public_dict()


def test_registered_recovery_roundtrip_zero_model_decisions(case):
    store, arguments, observation, policy, _, _ = case
    document = capture_red_player_terminal(**arguments)
    assert document["schema"] == REGISTERED_RECOVERY_CHECKPOINT_SCHEMA

    row = observe_registration(
        SimpleNamespace(collection_observation=policy.initial_collection),
        seen=frozenset(range(1, 152)),
        run_id=policy.run_id,
        rom_sha256=arguments["rom_sha256"],
        snapshot_sha256=document["state_sha256"],
        sequence=1,
    )
    document["registration_observation"] = row.document()

    validated_row = validate_terminal_registration(
        document,
        policy,
        sequence=1,
        rom_sha256=arguments["rom_sha256"],
    )
    assert validated_row.snapshot_sha256 == document["state_sha256"]

    _complete_registered_recovery(store, document)

    summary = publish_red_player_checkpoint(store, document)
    assert summary["independent_root"] is False
    assert summary["training_example"] is False
    assert summary["automatic_resume_authorized"] is False

    record = store.find_sealed_record(
        checkpoint_record_id(arguments["episode_id"]),
        expected_kind=CHECKPOINT_KIND,
    )
    assert record is not None
    assert record.read()["schema"] == REGISTERED_RECOVERY_CHECKPOINT_SCHEMA

    checkpoint = open_red_player_checkpoint(
        store,
        episode_id=arguments["episode_id"],
        expected_record_sha256=summary["record_sha256"],
        original_parent=arguments["parent"],
        expected_profile_sha256=arguments["profile_sha256"],
        expected_rom_sha256=arguments["rom_sha256"],
        expected_context_origin="training",
    )
    assert checkpoint.collection["schema"] == REGISTERED_CHECKPOINT_SCHEMA
    assert document["terminal_result"]["decisions"] == 0
    assert document["terminal_result"]["authority_decisions"] == 0
    assert document["terminal_result"]["training_examples"] == 0
    assert document["terminal_result"]["steps"] == []

    republished = recover_completed_red_player_checkpoint(store, arguments["episode_id"])
    assert republished == summary


def test_registered_recovery_preserves_original_failure_immutability(case):
    store, arguments, observation, policy, failed, failed_manifest = case
    document = capture_red_player_terminal(**arguments)
    row = observe_registration(
        SimpleNamespace(collection_observation=policy.initial_collection),
        seen=frozenset(range(1, 152)),
        run_id=policy.run_id,
        rom_sha256=arguments["rom_sha256"],
        snapshot_sha256=document["state_sha256"],
        sequence=1,
    )
    document["registration_observation"] = row.document()
    _complete_registered_recovery(store, document)
    publish_red_player_checkpoint(store, document)

    failed_ep = store.open_failed_episode("failed-choice")
    assert failed_ep.manifest_sha256 == failed_manifest
    saved_states = list(failed_ep.iter_stream("failure_state"))
    assert len(saved_states) == 1
    assert saved_states[0]["state_sha256"] == failed["state_sha256"]
    assert saved_states[0]["safe_checkpoint"] is False
    assert saved_states[0]["admitted_continuation"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "manifest",
        "state",
        "costs_actions",
        "costs_frames",
        "model_decisions_value",
        "decisions_stream",
        "missing_row",
        "wrong_row_snapshot",
        "wrong_row_rom",
        "wrong_row_owned",
        "wrong_row_physical",
        "schema_player_terminal",
        "schema_forged_recovery_terminal",
        "schema_legacy_collection",
    ],
)
def test_registered_recovery_rejects_tampering_and_mismatches(case, mutation):
    store, arguments, observation, policy, _, _ = case
    document = capture_red_player_terminal(**arguments)
    row = observe_registration(
        SimpleNamespace(collection_observation=policy.initial_collection),
        seen=frozenset(range(1, 152)),
        run_id=policy.run_id,
        rom_sha256=arguments["rom_sha256"],
        snapshot_sha256=document["state_sha256"],
        sequence=1,
    )
    document["registration_observation"] = row.document()

    alter_executions = None
    alter_decisions = None

    if mutation == "manifest":
        document["terminal_result"]["failure_origin"]["manifest_sha256"] = "0" * 64
        document["terminal_result_sha256"] = canonical_sha256(document["terminal_result"])
    elif mutation == "state":
        document["terminal_result"]["failure_origin"]["state_sha256"] = "0" * 64
        document["terminal_result_sha256"] = canonical_sha256(document["terminal_result"])
    elif mutation == "costs_actions":
        document["terminal_result"]["total_actions"] = 1
        document["terminal_result_sha256"] = canonical_sha256(document["terminal_result"])
    elif mutation == "costs_frames":
        alter_executions = [{"frames": 10}, {"frames": 10}]
    elif mutation == "model_decisions_value":
        document["terminal_result"]["authority_decisions"] = 1
        document["terminal_result_sha256"] = canonical_sha256(document["terminal_result"])
    elif mutation == "decisions_stream":
        alter_decisions = [{"decision": 1}]
    elif mutation == "missing_row":
        del document["registration_observation"]
    elif mutation == "wrong_row_snapshot":
        document["registration_observation"]["snapshot_sha256"] = "0" * 64
    elif mutation == "wrong_row_rom":
        document["registration_observation"]["cartridge_sha256"] = "0" * 64
    elif mutation == "wrong_row_owned":
        current_owned = document["registration_observation"]["owned"]
        document["registration_observation"]["owned"] = [
            x for x in current_owned if x != current_owned[0]
        ]
    elif mutation == "wrong_row_physical":
        document["registration_observation"]["physical_counts"][0][1] += 10
    elif mutation == "schema_player_terminal":
        document["terminal_result"] = {
            "schema": "pokemon.core.bounded-player-episode-result.v1",
            "authority_id": "player",
            "status": "complete",
            "stop_reason": "completed",
            "steps": [],
            "completion_satisfied": False,
        }
        document["terminal_result_sha256"] = canonical_sha256(document["terminal_result"])
    elif mutation == "schema_forged_recovery_terminal":
        document["schema"] = REGISTERED_PLAYER_CHECKPOINT_SCHEMA
    elif mutation == "schema_legacy_collection":
        document["collection"] = _observation(storage=4).collection.public_dict()

    _complete_registered_recovery(
        store,
        document,
        alter_executions=alter_executions,
        alter_decisions=alter_decisions,
    )

    with pytest.raises((RedFailureRecoveryError, RedPlayerCheckpointError)):
        publish_red_player_checkpoint(store, document)


def test_registered_support_import_remains_forbidden(case):
    _, arguments, observation, _, _, _ = case
    arguments["result"] = RedRecordedSupportResult("parent", "a" * 64, "b" * 64, "c" * 64, 2, 37)
    arguments["emulator"].frame_count = 0
    arguments["meter"] = SimpleNamespace(checkpoint=lambda: CompositionBudgetCheckpoint(0, 0))
    with pytest.raises(RedPlayerCheckpointError, match="declared contract"):
        capture_red_player_terminal(**arguments)


def test_legacy_recovery_behavior_preserved(case):
    store, arguments, _, _, _, _ = case
    legacy_obs = _observation(storage=4)
    arguments["observe"] = lambda: legacy_obs
    document = capture_red_player_terminal(**arguments)
    assert document["schema"] == RECOVERY_CHECKPOINT_SCHEMA

    _complete_registered_recovery(store, document)
    summary = publish_red_player_checkpoint(store, document)
    assert summary["independent_root"] is False

    record = store.find_sealed_record(
        checkpoint_record_id(arguments["episode_id"]),
        expected_kind=CHECKPOINT_KIND,
    )
    assert record is not None
    assert record.read()["schema"] == RECOVERY_CHECKPOINT_SCHEMA

    checkpoint = open_red_player_checkpoint(
        store,
        episode_id=arguments["episode_id"],
        expected_record_sha256=summary["record_sha256"],
        original_parent=arguments["parent"],
        expected_profile_sha256=arguments["profile_sha256"],
        expected_rom_sha256=arguments["rom_sha256"],
        expected_context_origin="training",
    )
    assert checkpoint.collection == legacy_obs.collection.public_dict()


def test_legacy_recovery_checkpoint_cannot_carry_registered_collection(case):
    store, arguments, obs, _, _, _ = case
    legacy_obs = _observation(storage=4)
    arguments["observe"] = lambda: legacy_obs
    document = capture_red_player_terminal(**arguments)
    document["collection"] = obs.collection.public_dict()
    _complete_registered_recovery(store, document)
    with pytest.raises(
        RedFailureRecoveryError, match="legacy recovery checkpoint cannot carry registered"
    ):
        publish_red_player_checkpoint(store, document)


def test_registered_runtime_binding_with_actual_dataclass(tmp_path):
    import run_paired_red_bounded_player as runner

    runtime, _, _, policy = observations(tmp_path)
    runtime_without = replace(
        runtime,
        registration_policy=None,
        adapter=replace(runtime.adapter, registration_policy=None),
    )

    legacy_ready = SimpleNamespace()
    bound_legacy = runner._registered_runtime(legacy_ready, runtime_without)
    assert bound_legacy.registration_policy is None

    registered_ready = SimpleNamespace(registration_policy=policy)
    bound_registered = runner._registered_runtime(registered_ready, runtime_without)
    assert bound_registered.registration_policy == policy
    assert bound_registered.adapter.registration_policy == policy
