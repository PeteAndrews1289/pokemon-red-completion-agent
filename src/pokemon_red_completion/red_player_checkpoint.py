"""Private, terminal-only continuation state for the bounded Red player.

A checkpoint is not a new independent root, a training example, or permission to
retry an episode. It is usable only after its original trajectory is complete.
The inherited quest envelope stays conservative; no new story claims are added.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Protocol

from pokemon_red_completion.bounded_player_episode import BoundedPlayerResult
from pokemon_red_completion.goal_manager_composition_runtime import (
    CompositionBudgetMeter,
    GoalManagerCompositionObservation,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCapture,
    parse_goal_manager_context_capture,
)
from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.provenance import canonical_sha256

CHECKPOINT_KIND = "red_bounded_player_checkpoint"
LEGACY_CHECKPOINT_SCHEMA = "pokemon.red.private-bounded-player-checkpoint.v1"
CHECKPOINT_SCHEMA = "pokemon.red.private-bounded-player-checkpoint.v2"
MEMORY_CHECKPOINT_SCHEMA = "pokemon.red.private-bounded-player-checkpoint.v3"
MAXIMUM_STATE_BYTES = 512 * 1024


class RedPlayerCheckpointError(ValueError):
    """The saved state cannot honestly continue its recorded parent episode."""


class _StateSource(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def save_state_bytes(self) -> bytes: ...


def checkpoint_record_id(episode_id: str) -> str:
    # Fixed-length IDs also work for the longest supported private episode IDs.
    # Keep the address stable when the payload encoding evolves.
    return "rpc-" + canonical_sha256({"episode_id": episode_id, "schema": LEGACY_CHECKPOINT_SCHEMA})


def capture_red_skill_recovery(
    *, emulator: _StateSource, meter: CompositionBudgetMeter,
) -> dict[str, object]:
    """Private diagnostic save, never an admitted continuation or training target.

    The caller has independently checked the completed quantum's safe boundary.
    Saving must not advance gameplay or controller state.
    """
    before = meter.checkpoint()
    frame_before = emulator.frame_count
    if emulator.pressed_buttons:
        raise RedPlayerCheckpointError("skill recovery has held input")
    state = emulator.save_state_bytes()
    if (
        meter.checkpoint() != before
        or emulator.frame_count != frame_before
        or emulator.pressed_buttons
    ):
        raise RedPlayerCheckpointError("skill recovery changed protected state")
    if not isinstance(state, bytes) or not 0 < len(state) <= MAXIMUM_STATE_BYTES:
        raise RedPlayerCheckpointError("skill recovery state size differs")
    return {
        "schema": "pokemon.red.private-skill-recovery.v1",
        "admitted_continuation": False,
        "training_target": False,
        "state_sha256": hashlib.sha256(state).hexdigest(),
        "state_base64": base64.b64encode(state).decode("ascii"),
        "actions": before.controller_actions,
        "frames": before.emulator_frames,
    }


def _sha(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RedPlayerCheckpointError("checkpoint identity differs")
    return value


def capture_red_player_terminal(
    *,
    emulator: _StateSource,
    meter: CompositionBudgetMeter,
    observe: Callable[[], GoalManagerCompositionObservation],
    parent: GoalManagerContextCapture,
    result: BoundedPlayerResult,
    episode_id: str,
    profile_sha256: str,
    rom_sha256: str,
    model_sha256: str,
    source_commit: str,
    source_bundle_sha256: str,
    context_origin: str,
    search_memory: GoalSearchMemory | None = None,
) -> dict[str, object]:
    """Capture without input; return private bytes pending trajectory completion."""
    if context_origin not in {"training", "development", "unspecified"}:
        raise RedPlayerCheckpointError("checkpoint context origin differs")
    before = meter.checkpoint()
    frame_before = emulator.frame_count
    if emulator.pressed_buttons:
        raise RedPlayerCheckpointError("checkpoint has held controller input")
    observation = observe()
    if result.steps and observation.collection != result.steps[-1].collection_after:
        raise RedPlayerCheckpointError("checkpoint terminal collection differs")
    state = emulator.save_state_bytes()
    after = observe()
    if (
        meter.checkpoint() != before
        or emulator.frame_count != frame_before
        or emulator.pressed_buttons
        or after.semantic_state_sha256 != observation.semantic_state_sha256
        or after.collection != observation.collection
    ):
        raise RedPlayerCheckpointError("checkpoint capture changed protected state")
    if not isinstance(state, bytes) or not 0 < len(state) <= MAXIMUM_STATE_BYTES:
        raise RedPlayerCheckpointError("checkpoint state size differs")
    state_sha256 = hashlib.sha256(state).hexdigest()
    envelope = replace(parent.envelope, state_sha256=state_sha256)
    return {
        "schema": MEMORY_CHECKPOINT_SCHEMA if search_memory is not None else CHECKPOINT_SCHEMA,
        **({"search_memory": search_memory.private_dict()} if search_memory is not None else {}),
        "episode_id": episode_id,
        "context_origin": context_origin,
        "original_state_sha256": parent.state_sha256,
        "original_envelope_sha256": parent.envelope_sha256,
        "profile_sha256": _sha(profile_sha256),
        "rom_sha256": _sha(rom_sha256),
        "model_sha256": _sha(model_sha256),
        "source_commit": source_commit,
        "source_bundle_sha256": _sha(source_bundle_sha256),
        "state_sha256": state_sha256,
        # Ordinary base64 can contain '/', which the path-free record boundary
        # correctly rejects. Change this encoding, not the global path guard.
        "state_base64": base64.urlsafe_b64encode(state).decode("ascii"),
        "envelope": envelope.to_dict(),
        "semantic_state_sha256": observation.semantic_state_sha256,
        "collection": observation.collection.public_dict(),
        "terminal_result_sha256": canonical_sha256(result.public_dict()),
        "terminal_result": result.public_dict(),
        "independent_root": False,
        "training_example": False,
        "automatic_resume_authorized": False,
    }


def _join_episode(store: PrivateArtifactRoot, document: Mapping[str, object]) -> str:
    episode_id = document.get("episode_id")
    if not isinstance(episode_id, str):
        raise RedPlayerCheckpointError("checkpoint episode identity differs")
    episode = store.open_episode(episode_id)
    captured = list(episode.iter_stream("checkpoint", max_records=1))
    expected_capture = {
        key: value for key, value in document.items() if key != "trajectory_manifest_sha256"
    }
    if captured != [expected_capture]:
        raise RedPlayerCheckpointError("checkpoint bytes differ from completed trajectory")
    header = episode.read_header()
    metadata = header.get("metadata")
    if not isinstance(metadata, Mapping) or header.get("episode_id") != episode_id:
        raise RedPlayerCheckpointError("checkpoint trajectory header differs")
    for name, key in (
        ("state_sha256", "original_state_sha256"),
        ("envelope_sha256", "original_envelope_sha256"),
        ("profile_sha256", "profile_sha256"),
        ("rom_sha256", "rom_sha256"),
        ("model_sha256", "model_sha256"),
        ("source_commit", "source_commit"),
        ("source_bundle_sha256", "source_bundle_sha256"),
        ("context_origin", "context_origin"),
    ):
        if metadata.get(name) != document.get(key):
            raise RedPlayerCheckpointError("checkpoint trajectory provenance differs")
    terminals = [row for row in episode.iter_stream("events") if row.get("kind") == "terminal"]
    if len(terminals) != 1:
        raise RedPlayerCheckpointError("checkpoint needs one completed terminal")
    payload = terminals[0].get("payload")
    if (
        not isinstance(payload, Mapping)
        or payload.get("status") != "complete"
        or payload.get("bounded_player") != document.get("terminal_result")
        or canonical_sha256(payload.get("bounded_player")) != document.get("terminal_result_sha256")
    ):
        raise RedPlayerCheckpointError("checkpoint trajectory terminal differs")
    return episode.manifest_sha256


def publish_red_player_checkpoint(
    store: PrivateArtifactRoot, captured: Mapping[str, object]
) -> dict[str, object]:
    """Publish only after all trajectory streams and the terminal authenticate."""
    manifest = _join_episode(store, captured)
    document = {**captured, "trajectory_manifest_sha256": manifest}
    episode_id = document["episode_id"]
    assert isinstance(episode_id, str)
    record = store.publish_sealed_record(
        checkpoint_record_id(episode_id), kind=CHECKPOINT_KIND, record=document
    )
    return {
        **record.summary.public_dict(),
        "state_sha256": document["state_sha256"],
        "trajectory_manifest_sha256": manifest,
        "context_origin": document["context_origin"],
        "independent_root": False,
        "training_example": False,
        "automatic_resume_authorized": False,
    }


def recover_completed_red_player_checkpoint(
    store: PrivateArtifactRoot, episode_id: str
) -> dict[str, object]:
    """Finish interrupted publication from durable bytes, with no controller access."""
    episode = store.open_episode(episode_id)
    captured = list(episode.iter_stream("checkpoint", max_records=1))
    if len(captured) != 1:
        raise RedPlayerCheckpointError("completed episode has no single terminal checkpoint")
    return publish_red_player_checkpoint(store, captured[0])


@dataclass(frozen=True, slots=True)
class RedPlayerCheckpoint:
    capture: GoalManagerContextCapture
    original_state_sha256: str
    original_envelope_sha256: str
    semantic_state_sha256: str
    collection: Mapping[str, object]
    record_sha256: str
    search_memory: Mapping[str, object] | None = None

    def require_restored_observation(self, observation: GoalManagerCompositionObservation) -> None:
        """Require a fresh adapter read before any future continuation may act."""
        if (
            observation.semantic_state_sha256 != self.semantic_state_sha256
            or observation.collection.public_dict() != self.collection
        ):
            raise RedPlayerCheckpointError("restored checkpoint semantic state differs")


def open_red_player_checkpoint(
    store: PrivateArtifactRoot,
    *,
    episode_id: str,
    expected_record_sha256: str,
    original_parent: GoalManagerContextCapture,
    expected_profile_sha256: str,
    expected_rom_sha256: str,
    expected_context_origin: str,
) -> RedPlayerCheckpoint:
    """Read only; never load an emulator, change a partition or issue a new claim."""
    record = store.find_sealed_record(
        checkpoint_record_id(episode_id), expected_kind=CHECKPOINT_KIND
    )
    if record is None or record.summary.record_sha256 != _sha(expected_record_sha256):
        raise RedPlayerCheckpointError("checkpoint record is absent or changed")
    document = record.read()
    expected = {
        "episode_id": episode_id,
        "original_state_sha256": original_parent.state_sha256,
        "original_envelope_sha256": original_parent.envelope_sha256,
        "profile_sha256": _sha(expected_profile_sha256),
        "rom_sha256": _sha(expected_rom_sha256),
        "context_origin": expected_context_origin,
        "independent_root": False,
        "training_example": False,
        "automatic_resume_authorized": False,
    }
    schema = document.get("schema")
    if schema not in {CHECKPOINT_SCHEMA, LEGACY_CHECKPOINT_SCHEMA, MEMORY_CHECKPOINT_SCHEMA} or any(
        document.get(key) != value for key, value in expected.items()
    ):
        raise RedPlayerCheckpointError("checkpoint parent or scope differs")
    if _join_episode(store, document) != document.get("trajectory_manifest_sha256"):
        raise RedPlayerCheckpointError("checkpoint trajectory identity differs")
    encoded = document.get("state_base64")
    if not isinstance(encoded, str) or len(encoded) > 4 * ((MAXIMUM_STATE_BYTES + 2) // 3):
        raise RedPlayerCheckpointError("checkpoint encoded state differs")
    try:
        state = base64.b64decode(
            encoded, altchars=b"-_" if schema != LEGACY_CHECKPOINT_SCHEMA else None, validate=True
        )
    except ValueError as error:
        raise RedPlayerCheckpointError("checkpoint encoded state differs") from error
    if not state or hashlib.sha256(state).hexdigest() != document.get("state_sha256"):
        raise RedPlayerCheckpointError("checkpoint state identity differs")
    envelope = document.get("envelope")
    if envelope != replace(
        original_parent.envelope, state_sha256=hashlib.sha256(state).hexdigest()
    ).to_dict():
        raise RedPlayerCheckpointError("checkpoint inherited quest claims differ")
    capture = parse_goal_manager_context_capture(state, json.dumps(envelope).encode("ascii"))
    collection = document.get("collection")
    if not isinstance(collection, Mapping):
        raise RedPlayerCheckpointError("checkpoint collection differs")
    terminal = document.get("terminal_result")
    steps = terminal.get("steps") if isinstance(terminal, Mapping) else None
    if not isinstance(steps, list) or (
        steps and (
            not isinstance(steps[-1], Mapping)
            or steps[-1].get("collection_after") != collection
        )
    ):
        raise RedPlayerCheckpointError("checkpoint final ledger differs")
    memory = None
    if schema == MEMORY_CHECKPOINT_SCHEMA:
        memory = GoalSearchMemory.from_private_dict(document.get("search_memory")).private_dict()
    elif "search_memory" in document:
        raise RedPlayerCheckpointError("legacy checkpoint cannot declare search memory")
    return RedPlayerCheckpoint(
        capture=capture,
        original_state_sha256=original_parent.state_sha256,
        original_envelope_sha256=original_parent.envelope_sha256,
        semantic_state_sha256=_sha(document.get("semantic_state_sha256")),
        collection=MappingProxyType(dict(collection)),
        record_sha256=record.summary.record_sha256,
        search_memory=memory,
    )
