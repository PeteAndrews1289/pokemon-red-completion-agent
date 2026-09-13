from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from dataclasses import replace

import pytest
from test_paired_red_bounded_player_script import _observation
from test_red_development_measured_choice import (
    _bootstrap_registered_model,
    _valid_choice,
    _valid_failed_fishing_choice,
)
from test_red_player_checkpoint import _complete

from pokemon_red_completion.bounded_player_episode import (
    BoundedPlayerResult,
    BoundedPlayerStopReason,
)
from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_composition_runtime import CompositionBudgetCheckpoint
from pokemon_red_completion.goal_manager_context_catalog import parse_goal_manager_context_capture
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_collection import RED_COLLECTION_GAME_ID
from pokemon_red_completion.red_development_measured_choice import (
    DEVELOPMENT_MEASURED_CHOICE_KIND,
    RedDevelopmentMeasuredChoice,
    RedDevelopmentMeasuredSegment,
    _replay_behavior,
    development_measured_choice_record_id,
    publish_development_measured_choice,
)
from pokemon_red_completion.red_player_checkpoint import (
    RedPlayerCheckpointError,
    capture_red_player_terminal,
    open_red_player_checkpoint,
    publish_red_player_checkpoint,
)
from pokemon_red_completion.red_player_incremental_fit import fit_incremental_measured_choice
from pokemon_red_completion.red_player_model import load_player_goal_model_record_bytes
from pokemon_red_completion.red_player_training_fit import fit_red_player_update
from pokemon_red_completion.red_recorded_support import (
    REGISTERED_MEASURED_CHECKPOINT_SCHEMA,
    REGISTERED_MEASURED_HEADER_SCHEMA,
    REGISTERED_SUPPORT_HEADER_SCHEMA,
    VERIFIED_SUPPORT_SEGMENT_SCHEMA,
    RedRecordedSupportError,
    RedRegisteredMeasuredTerminalResult,
    RedRegisteredRecordedSupportResult,
)
from pokemon_red_completion.red_registered_outcome import (
    red_registered_outcome_from_observations,
)
from pokemon_red_completion.registered_checkpoint import RegisteredCollectionCheckpoint
from pokemon_red_completion.registration_memory import RegistrationObservation


class _State:
    frame_count = 0
    pressed_buttons: frozenset[str] = frozenset()

    def __init__(self, state: bytes):
        self.state = state

    def save_state_bytes(self) -> bytes:
        return self.state


class _ZeroMeter:
    def checkpoint(self) -> CompositionBudgetCheckpoint:
        return CompositionBudgetCheckpoint(0, 0)


def _registered_observation(document):
    checkpoint = RegisteredCollectionCheckpoint.from_public(document)
    return replace(_observation(storage=4), collection=checkpoint)


def _registration_row(collection, state_sha256, sequence):
    owned = frozenset(int(species.rsplit(":", 1)[1]) for species in collection["local_species"])
    physical = {
        int(species.rsplit(":", 1)[1]): count for species, count in collection["specimen_counts"]
    }
    return RegistrationObservation(
        run_id="test-run",
        game_id=RED_COLLECTION_GAME_ID,
        adapter_id="red-registration-v1",
        cartridge_sha256="6" * 64,
        snapshot_sha256=state_sha256,
        sequence=sequence,
        seen=owned,
        owned=owned,
        physical_counts=physical,
    ).document()


def _write_measured_episode(store, document, segment, *, extra_stream=None):
    metadata = {
        name: document[key]
        for name, key in (
            ("state_sha256", "original_state_sha256"),
            ("envelope_sha256", "original_envelope_sha256"),
            ("profile_sha256", "profile_sha256"),
            ("rom_sha256", "rom_sha256"),
            ("model_sha256", "model_sha256"),
            ("source_commit", "source_commit"),
            ("source_bundle_sha256", "source_bundle_sha256"),
            ("context_origin", "context_origin"),
        )
    }
    metadata.update(
        schema=REGISTERED_MEASURED_HEADER_SCHEMA,
        training_eligible=False,
        split={"partition": "train", "root_lineage_id": "measured-root"},
        registration_session_record_id="registered-session",
    )
    writer = store.begin_episode(document["episode_id"])
    writer.append("episode", {"episode_id": document["episode_id"], "metadata": metadata})
    writer.append("checkpoint", document, durable=True)
    writer.append("recorded_support", segment)
    if extra_stream is not None:
        writer.append(extra_stream, {"invented": True})
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
    writer.complete()


def _measured_checkpoint_case(tmp_path, monkeypatch):
    store, prior_model, request, behavior = _bootstrap_registered_model(tmp_path, monkeypatch)
    choice = _valid_choice(
        tmp_path, model_sha256=behavior.model.model_sha256, behavior=behavior.model
    )

    parent_state = b"registered-measured-parent"
    terminal_state = b"registered-measured-terminal"
    original_state = b"registered-measured-root"
    original_envelope = CapturedProgressEnvelope(
        hashlib.sha256(original_state).hexdigest(),
        "measured-root",
        "Measured restart test",
        1,
        9,
        ("verified-old-quest",),
    )
    original_parent = parse_goal_manager_context_capture(
        original_state, json.dumps(original_envelope.to_dict()).encode("ascii")
    )
    before_observation = _registered_observation(choice.before_observation["registration"])
    parent_document = capture_red_player_terminal(
        emulator=_State(parent_state),
        meter=_ZeroMeter(),
        observe=lambda: before_observation,
        parent=original_parent,
        result=BoundedPlayerResult(
            "model-under-test", BoundedPlayerStopReason.DECISION_LIMIT, (), False
        ),
        episode_id="measured-parent",
        profile_sha256="5" * 64,
        rom_sha256="6" * 64,
        model_sha256=behavior.model.model_sha256,
        source_commit="8" * 40,
        source_bundle_sha256="9" * 64,
        context_origin="training",
    )
    parent_document["registration_observation"] = _registration_row(
        parent_document["collection"], parent_document["state_sha256"], 5
    )
    _complete(
        store,
        parent_document,
        alter_header={
            "split": {"partition": "train", "root_lineage_id": "measured-root"},
            "registration_session_record_id": "registered-session",
        },
    )
    parent_summary = publish_red_player_checkpoint(store, parent_document)
    parent_checkpoint = open_red_player_checkpoint(
        store,
        episode_id="measured-parent",
        expected_record_sha256=parent_summary["record_sha256"],
        original_parent=original_parent,
        expected_profile_sha256="5" * 64,
        expected_rom_sha256="6" * 64,
        expected_context_origin="training",
    )

    declaration = {
        **choice.selection_declaration,
        "parent_checkpoint_sha256": parent_summary["record_sha256"],
    }
    declaration_sha = canonical_sha256(declaration)
    measured_segment = RedDevelopmentMeasuredSegment(
        pair_id=choice.segments[0].pair_id,
        declaration_sha256=declaration_sha,
        claim_sha256=choice.segments[0].claim_sha256,
        result_sha256=choice.segments[0].result_sha256,
        parent_state_sha256=hashlib.sha256(parent_state).hexdigest(),
        terminal_state_sha256=hashlib.sha256(terminal_state).hexdigest(),
        controller_actions=choice.controller_actions,
        emulator_frames=choice.emulator_frames,
        status=choice.segments[0].status,
    )
    choice = replace(
        choice,
        parent_episode_id="measured-parent",
        parent_checkpoint_sha256=parent_summary["record_sha256"],
        selection_declaration=declaration,
        selection_declaration_sha256=declaration_sha,
        parent_state_sha256=measured_segment.parent_state_sha256,
        terminal_state_sha256=measured_segment.terminal_state_sha256,
        segments=(measured_segment,),
        segments_sha256=canonical_sha256([measured_segment.public_dict()]),
    )
    measured_input = publish_development_measured_choice(store, choice, behavior)
    fit = fit_red_player_update(
        store,
        prior=behavior,
        episodes=(request,),
        measured_choices=(measured_input,),
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        registered_objective=True,
    )
    model_document = fit["model"]
    successor_sha = model_document["model_sha256"]
    successor_record = store.find_sealed_record(
        f"rpr-model-{successor_sha}", expected_kind="red_player_model"
    )
    assert successor_record is not None
    successor = load_player_goal_model_record_bytes(
        successor_record.read_bytes(), expected_model_sha256=successor_sha
    )

    support_segment = {
        "schema": VERIFIED_SUPPORT_SEGMENT_SCHEMA,
        "plan": {
            "parent_state_sha256": measured_segment.parent_state_sha256,
            "parent_episode": "measured-parent",
            "parent_checkpoint_sha256": parent_summary["record_sha256"],
            "diagnostic_only": True,
            "fit_admission": False,
            "action_trace_available": False,
            "source_commit": "8" * 40,
            "maximum_actions": 300,
            "maximum_frames": 3_000,
            "retained_declaration_sha256": measured_segment.declaration_sha256,
            "retained_claim_sha256": measured_segment.claim_sha256,
            "retained_result_sha256": measured_segment.result_sha256,
        },
        "state_base64": base64.urlsafe_b64encode(terminal_state).decode("ascii"),
        "audit": {
            "state_sha256": measured_segment.terminal_state_sha256,
            "audit_actions": 0,
            "audit_frames": 0,
            "actions": measured_segment.controller_actions,
            "frames": measured_segment.emulator_frames,
            "retry_authorized": False,
            "training_examples": 0,
            "status": "retained_success",
        },
    }
    result = RedRegisteredMeasuredTerminalResult(
        "measured-parent",
        parent_summary["record_sha256"],
        parent_summary["trajectory_manifest_sha256"],
        canonical_sha256([support_segment]),
        choice.controller_actions,
        choice.emulator_frames,
        choice.choice_id,
        measured_input.record_sha256,
        behavior.model.model_sha256,
        successor.model.model_sha256,
    )
    after_observation = _registered_observation(choice.after_observation["registration"])
    document = capture_red_player_terminal(
        emulator=_State(terminal_state),
        meter=_ZeroMeter(),
        observe=lambda: after_observation,
        parent=parent_checkpoint.capture,
        result=result,
        episode_id="measured-terminal-import",
        profile_sha256="5" * 64,
        rom_sha256="6" * 64,
        model_sha256=successor.model.model_sha256,
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        context_origin="training",
    )
    document["registration_observation"] = _registration_row(
        document["collection"], document["state_sha256"], 6
    )
    return (
        store,
        original_parent,
        parent_checkpoint,
        document,
        support_segment,
        terminal_state,
        prior_model,
    )


def test_measured_terminal_restart_roundtrip_is_zero_input_and_lower_trust(tmp_path, monkeypatch):
    store, _, parent, document, segment, terminal_state, _ = _measured_checkpoint_case(
        tmp_path, monkeypatch
    )
    assert document["schema"] == REGISTERED_MEASURED_CHECKPOINT_SCHEMA
    terminal = document["terminal_result"]
    assert terminal["steps"] == []
    assert terminal["total_actions"] == terminal["training_examples"] == 0
    assert terminal["action_trace_available"] is False
    assert terminal["independent_evaluation"] is False
    assert terminal["authority_promotion_eligible"] is False

    _write_measured_episode(store, document, segment)
    summary = publish_red_player_checkpoint(store, document)
    opened = open_red_player_checkpoint(
        store,
        episode_id=document["episode_id"],
        expected_record_sha256=summary["record_sha256"],
        original_parent=parent.capture,
        expected_profile_sha256="5" * 64,
        expected_rom_sha256="6" * 64,
        expected_context_origin="training",
    )
    assert opened.capture.state_bytes == terminal_state
    assert opened.collection == document["collection"]


def test_measured_failure_can_directly_follow_an_authenticated_measured_terminal(
    tmp_path, monkeypatch
):
    (
        store,
        _,
        native_parent,
        measured,
        measured_segment,
        _,
        prior_model,
    ) = _measured_checkpoint_case(tmp_path, monkeypatch)
    _write_measured_episode(store, measured, measured_segment)
    measured_summary = publish_red_player_checkpoint(store, measured)
    measured_checkpoint = open_red_player_checkpoint(
        store,
        episode_id=measured["episode_id"],
        expected_record_sha256=measured_summary["record_sha256"],
        original_parent=native_parent.capture,
        expected_profile_sha256="5" * 64,
        expected_rom_sha256="6" * 64,
        expected_context_origin="training",
    )
    behavior_record = store.find_sealed_record(
        f"rpr-model-{measured['model_sha256']}", expected_kind="red_player_model"
    )
    assert behavior_record is not None
    behavior = load_player_goal_model_record_bytes(
        behavior_record.read_bytes(), expected_model_sha256=measured["model_sha256"]
    )
    failed = _valid_failed_fishing_choice(
        tmp_path / "consecutive", model_sha256=measured["model_sha256"], behavior=behavior.model
    )
    parent_state_sha256 = measured["state_sha256"]
    terminal_state = b"consecutive-measured-failure-terminal"
    terminal_state_sha256 = hashlib.sha256(terminal_state).hexdigest()
    declaration = {
        **failed.selection_declaration,
        "parent_episode": measured["episode_id"],
        "parent_checkpoint_sha256": measured_summary["record_sha256"],
        "parent_state_sha256": parent_state_sha256,
    }
    segment = replace(
        failed.segments[0],
        pair_id="consecutive-measured-failure",
        declaration_sha256=canonical_sha256(declaration),
        parent_state_sha256=parent_state_sha256,
        terminal_state_sha256=terminal_state_sha256,
    )
    before = deepcopy(failed.before_observation)
    before["registration"] = measured["collection"]
    before["semantic_observation"]["collection"]["registered"] = measured[
        "collection"
    ]["registered_species"]
    after = deepcopy(before)
    outcome = red_registered_outcome_from_observations(
        before,
        after,
        selected_kind=GoalKind.ACQUIRE_SPECIES,
        succeeded=False,
        actions=segment.controller_actions,
        frames=segment.emulator_frames,
        maximum_actions=30_000,
        maximum_frames=3_000_000,
    )
    failed = replace(
        failed,
        choice_id="consecutive-measured-failure",
        parent_episode_id=measured["episode_id"],
        parent_checkpoint_sha256=measured_summary["record_sha256"],
        selection_declaration=declaration,
        selection_declaration_sha256=canonical_sha256(declaration),
        before_observation=before,
        after_observation=after,
        before_observation_sha256=canonical_sha256(before),
        after_observation_sha256=canonical_sha256(after),
        parent_state_sha256=parent_state_sha256,
        terminal_state_sha256=terminal_state_sha256,
        segments=(segment,),
        segments_sha256=canonical_sha256([segment.public_dict()]),
        resource_costs={
            "irreversible_loss": outcome.irreversible_loss,
            "party_cost": outcome.party_cost,
            "resource_cost": outcome.resource_cost,
            "storage_cost": outcome.storage_cost,
        },
    )
    measured_input = publish_development_measured_choice(store, failed, behavior)

    def resolve(expected):
        if expected == prior_model.model.model_sha256:
            return prior_model
        record = store.find_sealed_record(
            f"rpr-model-{expected}", expected_kind="red_player_model"
        )
        assert record is not None
        return load_player_goal_model_record_bytes(
            record.read_bytes(), expected_model_sha256=expected
        )

    fit = fit_incremental_measured_choice(
        store,
        prior=behavior,
        measured_choice=measured_input,
        resolve=resolve,
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
    )
    successor_sha = fit["model"]["model_sha256"]
    support_segment = {
        "schema": VERIFIED_SUPPORT_SEGMENT_SCHEMA,
        "plan": {
            "parent_state_sha256": parent_state_sha256,
            "parent_episode": measured["episode_id"],
            "parent_checkpoint_sha256": measured_summary["record_sha256"],
            "diagnostic_only": True,
            "fit_admission": False,
            "action_trace_available": False,
            "source_commit": "a" * 40,
            "maximum_actions": 30_000,
            "maximum_frames": 3_000_000,
            "retained_declaration_sha256": segment.declaration_sha256,
            "retained_claim_sha256": segment.claim_sha256,
            "retained_result_sha256": segment.result_sha256,
        },
        "state_base64": base64.urlsafe_b64encode(terminal_state).decode("ascii"),
        "audit": {
            "state_sha256": terminal_state_sha256,
            "audit_actions": 0,
            "audit_frames": 0,
            "actions": segment.controller_actions,
            "frames": segment.emulator_frames,
            "retry_authorized": False,
            "training_examples": 0,
            "status": segment.status,
        },
    }
    result = RedRegisteredMeasuredTerminalResult(
        measured["episode_id"],
        measured_summary["record_sha256"],
        measured_summary["trajectory_manifest_sha256"],
        canonical_sha256([support_segment]),
        segment.controller_actions,
        segment.emulator_frames,
        failed.choice_id,
        measured_input.record_sha256,
        behavior.model.model_sha256,
        successor_sha,
    )
    document = capture_red_player_terminal(
        emulator=_State(terminal_state),
        meter=_ZeroMeter(),
        observe=lambda: _registered_observation(measured["collection"]),
        parent=measured_checkpoint.capture,
        result=result,
        episode_id="consecutive-measured-failure-terminal",
        profile_sha256="5" * 64,
        rom_sha256="6" * 64,
        model_sha256=successor_sha,
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        context_origin="training",
    )
    document["registration_observation"] = _registration_row(
        document["collection"], document["state_sha256"], 7
    )
    _write_measured_episode(store, document, support_segment)
    summary = publish_red_player_checkpoint(store, document)
    opened = open_red_player_checkpoint(
        store,
        episode_id=document["episode_id"],
        expected_record_sha256=summary["record_sha256"],
        original_parent=measured_checkpoint.capture,
        expected_profile_sha256="5" * 64,
        expected_rom_sha256="6" * 64,
        expected_context_origin="training",
    )
    assert opened.capture.state_bytes == terminal_state
    assert opened.collection == measured["collection"]


def test_measured_terminal_can_anchor_one_later_registered_support_import(tmp_path, monkeypatch):
    store, _, native_parent, measured, measured_segment, _, _ = _measured_checkpoint_case(
        tmp_path, monkeypatch
    )
    _write_measured_episode(store, measured, measured_segment)
    measured_summary = publish_red_player_checkpoint(store, measured)
    measured_checkpoint = open_red_player_checkpoint(
        store,
        episode_id=measured["episode_id"],
        expected_record_sha256=measured_summary["record_sha256"],
        original_parent=native_parent.capture,
        expected_profile_sha256="5" * 64,
        expected_rom_sha256="6" * 64,
        expected_context_origin="training",
    )

    terminal_state = b"post-measured-native-support"
    support_segment = {
        "schema": VERIFIED_SUPPORT_SEGMENT_SCHEMA,
        "plan": {
            "parent_state_sha256": measured["state_sha256"],
            "parent_episode": measured["episode_id"],
            "parent_checkpoint_sha256": measured_summary["record_sha256"],
            "diagnostic_only": True,
            "fit_admission": False,
            "action_trace_available": False,
            "source_commit": "a" * 40,
            "maximum_actions": 500,
            "maximum_frames": 50_000,
            "retained_declaration_sha256": "1" * 64,
            "retained_claim_sha256": "2" * 64,
            "retained_result_sha256": "3" * 64,
        },
        "state_base64": base64.urlsafe_b64encode(terminal_state).decode("ascii"),
        "audit": {
            "state_sha256": hashlib.sha256(terminal_state).hexdigest(),
            "audit_actions": 0,
            "audit_frames": 0,
            "actions": 410,
            "frames": 42_000,
            "retry_authorized": False,
            "training_examples": 0,
            "status": "verified_super_rod_received",
        },
    }
    result = RedRegisteredRecordedSupportResult(
        measured["episode_id"],
        measured_summary["record_sha256"],
        measured_summary["trajectory_manifest_sha256"],
        canonical_sha256([support_segment]),
        410,
        42_000,
    )
    observation = _registered_observation(measured["collection"])
    document = capture_red_player_terminal(
        emulator=_State(terminal_state),
        meter=_ZeroMeter(),
        observe=lambda: observation,
        parent=measured_checkpoint.capture,
        result=result,
        episode_id="post-measured-support",
        profile_sha256="5" * 64,
        rom_sha256="6" * 64,
        model_sha256=measured["model_sha256"],
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        context_origin="training",
    )
    document["registration_observation"] = _registration_row(
        document["collection"], document["state_sha256"], 7
    )
    metadata = {
        name: document[key]
        for name, key in (
            ("state_sha256", "original_state_sha256"),
            ("envelope_sha256", "original_envelope_sha256"),
            ("profile_sha256", "profile_sha256"),
            ("rom_sha256", "rom_sha256"),
            ("model_sha256", "model_sha256"),
            ("source_commit", "source_commit"),
            ("source_bundle_sha256", "source_bundle_sha256"),
            ("context_origin", "context_origin"),
        )
    }
    metadata.update(
        schema=REGISTERED_SUPPORT_HEADER_SCHEMA,
        training_eligible=False,
        split={"partition": "train", "root_lineage_id": "measured-root"},
        registration_session_record_id="registered-session",
    )
    writer = store.begin_episode(document["episode_id"])
    writer.append("episode", {"episode_id": document["episode_id"], "metadata": metadata})
    writer.append("checkpoint", document, durable=True)
    writer.append("recorded_support", support_segment)
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
    writer.complete()
    summary = publish_red_player_checkpoint(store, document)
    opened = open_red_player_checkpoint(
        store,
        episode_id=document["episode_id"],
        expected_record_sha256=summary["record_sha256"],
        original_parent=measured_checkpoint.capture,
        expected_profile_sha256="5" * 64,
        expected_rom_sha256="6" * 64,
        expected_context_origin="training",
    )
    assert opened.capture.state_bytes == terminal_state
    assert opened.collection == measured["collection"]
    assert document["terminal_result"]["training_examples"] == 0


def test_registered_support_can_anchor_one_later_measured_terminal(tmp_path, monkeypatch):
    (
        store,
        _,
        native_parent,
        measured,
        measured_segment,
        _,
        prior_model,
    ) = _measured_checkpoint_case(tmp_path, monkeypatch)
    _write_measured_episode(store, measured, measured_segment)
    measured_summary = publish_red_player_checkpoint(store, measured)
    measured_checkpoint = open_red_player_checkpoint(
        store,
        episode_id=measured["episode_id"],
        expected_record_sha256=measured_summary["record_sha256"],
        original_parent=native_parent.capture,
        expected_profile_sha256="5" * 64,
        expected_rom_sha256="6" * 64,
        expected_context_origin="training",
    )

    support_state = b"post-measured-support-before-second-choice"
    support_segment = {
        "schema": VERIFIED_SUPPORT_SEGMENT_SCHEMA,
        "plan": {
            "parent_state_sha256": measured["state_sha256"],
            "parent_episode": measured["episode_id"],
            "parent_checkpoint_sha256": measured_summary["record_sha256"],
            "diagnostic_only": True,
            "fit_admission": False,
            "action_trace_available": False,
            "source_commit": "a" * 40,
            "maximum_actions": 500,
            "maximum_frames": 50_000,
            "retained_declaration_sha256": "1" * 64,
            "retained_claim_sha256": "2" * 64,
            "retained_result_sha256": "3" * 64,
        },
        "state_base64": base64.urlsafe_b64encode(support_state).decode("ascii"),
        "audit": {
            "state_sha256": hashlib.sha256(support_state).hexdigest(),
            "audit_actions": 0,
            "audit_frames": 0,
            "actions": 410,
            "frames": 42_000,
            "retry_authorized": False,
            "training_examples": 0,
            "status": "verified_super_rod_received",
        },
    }
    support_result = RedRegisteredRecordedSupportResult(
        measured["episode_id"],
        measured_summary["record_sha256"],
        measured_summary["trajectory_manifest_sha256"],
        canonical_sha256([support_segment]),
        410,
        42_000,
    )
    support_observation = _registered_observation(measured["collection"])
    support = capture_red_player_terminal(
        emulator=_State(support_state),
        meter=_ZeroMeter(),
        observe=lambda: support_observation,
        parent=measured_checkpoint.capture,
        result=support_result,
        episode_id="support-before-second-measured",
        profile_sha256="5" * 64,
        rom_sha256="6" * 64,
        model_sha256=measured["model_sha256"],
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        context_origin="training",
    )
    support["registration_observation"] = _registration_row(
        support["collection"], support["state_sha256"], 7
    )
    support_metadata = {
        name: support[key]
        for name, key in (
            ("state_sha256", "original_state_sha256"),
            ("envelope_sha256", "original_envelope_sha256"),
            ("profile_sha256", "profile_sha256"),
            ("rom_sha256", "rom_sha256"),
            ("model_sha256", "model_sha256"),
            ("source_commit", "source_commit"),
            ("source_bundle_sha256", "source_bundle_sha256"),
            ("context_origin", "context_origin"),
        )
    }
    support_metadata.update(
        schema=REGISTERED_SUPPORT_HEADER_SCHEMA,
        training_eligible=False,
        split={"partition": "train", "root_lineage_id": "measured-root"},
        registration_session_record_id="registered-session",
    )
    writer = store.begin_episode(support["episode_id"])
    writer.append("episode", {"episode_id": support["episode_id"], "metadata": support_metadata})
    writer.append("checkpoint", support, durable=True)
    writer.append("recorded_support", support_segment)
    writer.append(
        "events",
        {
            "kind": "terminal",
            "payload": {
                "status": "complete",
                "bounded_player": support["terminal_result"],
            },
        },
        durable=True,
    )
    writer.complete()
    support_summary = publish_red_player_checkpoint(store, support)
    support_checkpoint = open_red_player_checkpoint(
        store,
        episode_id=support["episode_id"],
        expected_record_sha256=support_summary["record_sha256"],
        original_parent=measured_checkpoint.capture,
        expected_profile_sha256="5" * 64,
        expected_rom_sha256="6" * 64,
        expected_context_origin="training",
    )

    first_binding = measured["terminal_result"]["measured_choice"]
    first_record = store.find_sealed_record(
        development_measured_choice_record_id(first_binding["choice_id"]),
        expected_kind=DEVELOPMENT_MEASURED_CHOICE_KIND,
    )
    assert first_record is not None
    first_choice = RedDevelopmentMeasuredChoice.from_public(first_record.read())
    behavior_record = store.find_sealed_record(
        f"rpr-model-{measured['model_sha256']}", expected_kind="red_player_model"
    )
    assert behavior_record is not None
    behavior = load_player_goal_model_record_bytes(
        behavior_record.read_bytes(), expected_model_sha256=measured["model_sha256"]
    )
    old = RegisteredCollectionCheckpoint.from_public(support["collection"])
    species = next(item for item in old.target_species if item not in old.global_species)
    new_globals = tuple(sorted((*old.global_species, species)))
    new_locals = tuple(sorted((*old.local_species, species)))
    new_counts = tuple(sorted((*old.specimen_counts, (species, 1))))
    missing = tuple(sorted(set(old.target_species) - set(new_globals)))
    new = replace(
        old,
        registered_species=old.registered_species + 1,
        living_species=old.living_species + 1,
        required_specimens_remaining=old.required_specimens_remaining - 1,
        retained_captures=old.retained_captures + 1,
        storage_headroom=max(0, old.storage_headroom - 1),
        required_specimens_sha256=canonical_sha256(
            {"schema": "pokemon.core.missing-registrations.v1", "missing": missing}
        ),
        specimen_ledger_sha256=canonical_sha256(
            {
                "schema": "pokemon.core.registered-physical-ledger.v1",
                "counts": new_counts,
                "local": new_locals,
                "global": new_globals,
            }
        ),
        specimen_counts=new_counts,
        global_species=new_globals,
        local_species=new_locals,
    )
    before = dict(first_choice.after_observation)
    before["registration"] = old.public_dict()
    after = deepcopy(before)
    after["registration"] = new.public_dict()
    after["semantic_observation"]["collection"]["registered"] = new.registered_species
    seed = 1
    scores, probabilities, selected = _replay_behavior(behavior.model, first_choice.menu, seed=seed)
    declaration = {
        "schema": "pokemon.red.private-safari-outcome-declaration.v1",
        "pair_id": "second-measured-segment",
        "parent_checkpoint_sha256": support_summary["record_sha256"],
        "source_commit": "a" * 40,
        "source_bundle_sha256": "b" * 64,
        "model_sha256": behavior.model.model_sha256,
        "menu_sha256": first_choice.menu.policy_sha256,
        "seed": seed,
        "selected_candidate_index": selected,
        "maximum_semantic_actions": 300,
        "maximum_encounters": 40,
        "capture_quota": 1,
        "retry_allowed": False,
    }
    terminal_state = b"second-measured-terminal"
    measured_segment_2 = RedDevelopmentMeasuredSegment(
        pair_id="second-measured-segment",
        declaration_sha256=canonical_sha256(declaration),
        claim_sha256="4" * 64,
        result_sha256="5" * 64,
        parent_state_sha256=support["state_sha256"],
        terminal_state_sha256=hashlib.sha256(terminal_state).hexdigest(),
        controller_actions=25,
        emulator_frames=250,
        status="retained_success",
    )
    outcome = red_registered_outcome_from_observations(
        before,
        after,
        selected_kind=GoalKind.ACQUIRE_SPECIES,
        succeeded=True,
        actions=25,
        frames=250,
        maximum_actions=30_000,
        maximum_frames=3_000_000,
    )
    choice_2 = RedDevelopmentMeasuredChoice(
        choice_id="second-measured-after-support",
        parent_episode_id=support["episode_id"],
        parent_checkpoint_sha256=support_summary["record_sha256"],
        menu=first_choice.menu,
        selected_candidate_index=selected,
        behavior_probabilities=probabilities,
        scores=scores,
        selection_seed=seed,
        selection_declaration=declaration,
        selection_declaration_sha256=canonical_sha256(declaration),
        model_sha256=behavior.model.model_sha256,
        before_observation=before,
        after_observation=after,
        before_observation_sha256=canonical_sha256(before),
        after_observation_sha256=canonical_sha256(after),
        parent_state_sha256=support["state_sha256"],
        terminal_state_sha256=hashlib.sha256(terminal_state).hexdigest(),
        segments=(measured_segment_2,),
        segments_sha256=canonical_sha256([measured_segment_2.public_dict()]),
        controller_actions=25,
        emulator_frames=250,
        resource_costs={
            "irreversible_loss": outcome.irreversible_loss,
            "party_cost": outcome.party_cost,
            "resource_cost": outcome.resource_cost,
            "storage_cost": outcome.storage_cost,
        },
        observer_source_commit="a" * 40,
        observer_source_bundle_sha256="b" * 64,
    )
    measured_input = publish_development_measured_choice(store, choice_2, behavior)

    def resolve(expected):
        if expected == prior_model.model.model_sha256:
            return prior_model
        record = next(
            (
                found
                for prefix in ("rpr-model-", "rp-model-")
                if (
                    found := store.find_sealed_record(
                        f"{prefix}{expected}", expected_kind="red_player_model"
                    )
                )
                is not None
            ),
            None,
        )
        assert record is not None
        return load_player_goal_model_record_bytes(
            record.read_bytes(), expected_model_sha256=expected
        )

    fit = fit_incremental_measured_choice(
        store,
        prior=behavior,
        measured_choice=measured_input,
        resolve=resolve,
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
    )
    successor_sha = fit["model"]["model_sha256"]
    measured_support_segment = {
        "schema": VERIFIED_SUPPORT_SEGMENT_SCHEMA,
        "plan": {
            "parent_state_sha256": support["state_sha256"],
            "parent_episode": support["episode_id"],
            "parent_checkpoint_sha256": support_summary["record_sha256"],
            "diagnostic_only": True,
            "fit_admission": False,
            "action_trace_available": False,
            "source_commit": "a" * 40,
            "maximum_actions": 30_000,
            "maximum_frames": 3_000_000,
            "retained_declaration_sha256": measured_segment_2.declaration_sha256,
            "retained_claim_sha256": measured_segment_2.claim_sha256,
            "retained_result_sha256": measured_segment_2.result_sha256,
        },
        "state_base64": base64.urlsafe_b64encode(terminal_state).decode("ascii"),
        "audit": {
            "state_sha256": measured_segment_2.terminal_state_sha256,
            "audit_actions": 0,
            "audit_frames": 0,
            "actions": 25,
            "frames": 250,
            "retry_authorized": False,
            "training_examples": 0,
            "status": "retained_success",
        },
    }
    result_2 = RedRegisteredMeasuredTerminalResult(
        support["episode_id"],
        support_summary["record_sha256"],
        support_summary["trajectory_manifest_sha256"],
        canonical_sha256([measured_support_segment]),
        25,
        250,
        choice_2.choice_id,
        measured_input.record_sha256,
        behavior.model.model_sha256,
        successor_sha,
    )
    terminal_observation = _registered_observation(new.public_dict())
    document_2 = capture_red_player_terminal(
        emulator=_State(terminal_state),
        meter=_ZeroMeter(),
        observe=lambda: terminal_observation,
        parent=support_checkpoint.capture,
        result=result_2,
        episode_id="second-measured-terminal",
        profile_sha256="5" * 64,
        rom_sha256="6" * 64,
        model_sha256=successor_sha,
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        context_origin="training",
    )
    document_2["registration_observation"] = _registration_row(
        document_2["collection"], document_2["state_sha256"], 8
    )
    _write_measured_episode(store, document_2, measured_support_segment)
    summary_2 = publish_red_player_checkpoint(store, document_2)
    opened_2 = open_red_player_checkpoint(
        store,
        episode_id=document_2["episode_id"],
        expected_record_sha256=summary_2["record_sha256"],
        original_parent=support_checkpoint.capture,
        expected_profile_sha256="5" * 64,
        expected_rom_sha256="6" * 64,
        expected_context_origin="training",
    )
    assert opened_2.capture.state_bytes == terminal_state
    assert opened_2.collection == new.public_dict()


def test_measured_terminal_contract_cannot_be_captured_as_legacy_collection(tmp_path, monkeypatch):
    store, _, parent, document, _, terminal_state, _ = _measured_checkpoint_case(
        tmp_path, monkeypatch
    )
    del store
    with pytest.raises(RedPlayerCheckpointError, match="requires a registered collection"):
        capture_red_player_terminal(
            emulator=_State(terminal_state),
            meter=_ZeroMeter(),
            observe=lambda: _observation(storage=4),
            parent=parent.capture,
            result=RedRegisteredMeasuredTerminalResult(
                **{
                    "parent_episode_id": document["terminal_result"]["origin"]["episode_id"],
                    "parent_checkpoint_sha256": document["terminal_result"]["origin"][
                        "checkpoint_sha256"
                    ],
                    "parent_manifest_sha256": document["terminal_result"]["origin"][
                        "manifest_sha256"
                    ],
                    "segments_sha256": document["terminal_result"]["origin"]["segments_sha256"],
                    "historical_actions": document["terminal_result"]["historical_support_actions"],
                    "historical_frames": document["terminal_result"]["historical_support_frames"],
                    "choice_id": document["terminal_result"]["measured_choice"]["choice_id"],
                    "choice_record_sha256": document["terminal_result"]["measured_choice"][
                        "record_sha256"
                    ],
                    "behavior_model_sha256": document["terminal_result"]["measured_choice"][
                        "behavior_model_sha256"
                    ],
                    "continuation_model_sha256": document["terminal_result"]["measured_choice"][
                        "continuation_model_sha256"
                    ],
                }
            ),
            episode_id="legacy-measured-import",
            profile_sha256="5" * 64,
            rom_sha256="6" * 64,
            model_sha256=document["model_sha256"],
            source_commit="a" * 40,
            source_bundle_sha256="b" * 64,
            context_origin="training",
        )


@pytest.mark.parametrize(
    "fault",
    [
        "state",
        "collection",
        "model",
        "choice",
        "cost",
        "segment",
        "receipt",
        "registration",
        "decisions",
    ],
)
def test_measured_terminal_restart_rejects_broken_evidence_chain(tmp_path, monkeypatch, fault):
    store, _, _, document, segment, _, _ = _measured_checkpoint_case(tmp_path, monkeypatch)
    if fault == "state":
        document["state_sha256"] = "f" * 64
    elif fault == "collection":
        document["collection"] = dict(document["collection"])
        document["collection"]["registered_species"] -= 1
    elif fault == "model":
        document["model_sha256"] = document["terminal_result"]["measured_choice"][
            "behavior_model_sha256"
        ]
    elif fault == "choice":
        document["terminal_result"]["measured_choice"]["record_sha256"] = "f" * 64
        document["terminal_result_sha256"] = canonical_sha256(document["terminal_result"])
    elif fault == "cost":
        document["terminal_result"]["historical_support_actions"] += 1
        document["terminal_result_sha256"] = canonical_sha256(document["terminal_result"])
    elif fault == "segment":
        segment["audit"]["frames"] += 1
    elif fault == "receipt":
        segment["plan"]["retained_result_sha256"] = "f" * 64
    elif fault == "registration":
        document["registration_observation"]["sequence"] += 1
    _write_measured_episode(
        store,
        document,
        segment,
        extra_stream="decisions" if fault == "decisions" else None,
    )
    with pytest.raises((RedRecordedSupportError, ValueError)):
        publish_red_player_checkpoint(store, document)
