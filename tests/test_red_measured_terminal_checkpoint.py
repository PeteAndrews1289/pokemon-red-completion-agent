from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import replace

import pytest
from test_paired_red_bounded_player_script import _observation
from test_red_development_measured_choice import (
    _bootstrap_registered_model,
    _valid_choice,
)
from test_red_player_checkpoint import _complete

from pokemon_red_completion.bounded_player_episode import (
    BoundedPlayerResult,
    BoundedPlayerStopReason,
)
from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.goal_manager_composition_runtime import CompositionBudgetCheckpoint
from pokemon_red_completion.goal_manager_context_catalog import parse_goal_manager_context_capture
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_collection import RED_COLLECTION_GAME_ID
from pokemon_red_completion.red_development_measured_choice import (
    RedDevelopmentMeasuredSegment,
    publish_development_measured_choice,
)
from pokemon_red_completion.red_player_checkpoint import (
    RedPlayerCheckpointError,
    capture_red_player_terminal,
    open_red_player_checkpoint,
    publish_red_player_checkpoint,
)
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
        int(species.rsplit(":", 1)[1]): count
        for species, count in collection["specimen_counts"]
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
    store, _, request, behavior = _bootstrap_registered_model(tmp_path, monkeypatch)
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
    return store, original_parent, parent_checkpoint, document, support_segment, terminal_state


def test_measured_terminal_restart_roundtrip_is_zero_input_and_lower_trust(
    tmp_path, monkeypatch
):
    store, _, parent, document, segment, terminal_state = _measured_checkpoint_case(
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


def test_measured_terminal_can_anchor_one_later_registered_support_import(
    tmp_path, monkeypatch
):
    store, _, native_parent, measured, measured_segment, _ = _measured_checkpoint_case(
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


def test_measured_terminal_contract_cannot_be_captured_as_legacy_collection(
    tmp_path, monkeypatch
):
    store, _, parent, document, _, terminal_state = _measured_checkpoint_case(
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
                    "segments_sha256": document["terminal_result"]["origin"][
                        "segments_sha256"
                    ],
                    "historical_actions": document["terminal_result"][
                        "historical_support_actions"
                    ],
                    "historical_frames": document["terminal_result"][
                        "historical_support_frames"
                    ],
                    "choice_id": document["terminal_result"]["measured_choice"]["choice_id"],
                    "choice_record_sha256": document["terminal_result"]["measured_choice"][
                        "record_sha256"
                    ],
                    "behavior_model_sha256": document["terminal_result"]["measured_choice"][
                        "behavior_model_sha256"
                    ],
                    "continuation_model_sha256": document["terminal_result"][
                        "measured_choice"
                    ]["continuation_model_sha256"],
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
def test_measured_terminal_restart_rejects_broken_evidence_chain(
    tmp_path, monkeypatch, fault
):
    store, _, _, document, segment, _ = _measured_checkpoint_case(tmp_path, monkeypatch)
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
