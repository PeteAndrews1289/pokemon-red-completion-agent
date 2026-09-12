"""Import recorded development support without inventing decisions or replaying it.

This authenticates retained local evidence, not a retrospectively recorded native
trajectory. An import is administrative: zero new input and zero training rows.
Original support costs and incomplete reporting remain visible in its own stream.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .private_artifacts import PrivateArtifactRoot
from .provenance import canonical_sha256

SUPPORT_HEADER_SCHEMA = "pokemon.red.recorded-support-header.v1"
SUPPORT_TERMINAL_SCHEMA = "pokemon.red.recorded-support-terminal.v1"
SUPPORT_CHECKPOINT_SCHEMA = "pokemon.red.private-recorded-support-checkpoint.v1"
REGISTERED_SUPPORT_HEADER_SCHEMA = "pokemon.red.registered-recorded-support-header.v1"
REGISTERED_SUPPORT_TERMINAL_SCHEMA = "pokemon.red.registered-recorded-support-terminal.v1"
REGISTERED_SUPPORT_CHECKPOINT_SCHEMA = (
    "pokemon.red.private-registered-recorded-support-checkpoint.v1"
)
VERIFIED_SUPPORT_SEGMENT_SCHEMA = "pokemon.red.verified-support-segment.v1"


class RedRecordedSupportError(ValueError):
    """The retained support does not preserve its declared native predecessor."""


def _mapping(value: object) -> Mapping:
    if not isinstance(value, Mapping):
        raise RedRecordedSupportError("support object missing")
    return value


def support_costs(segments: Sequence[Mapping], parent_state: str) -> tuple[int, int, str]:
    """Check continuous exact saves and paired action traces, including failed support."""
    if not 1 <= len(segments) <= 8:
        raise RedRecordedSupportError("support chain bound differs")
    actions = frames = 0
    current = parent_state
    for segment in segments:
        if segment.get("schema") == VERIFIED_SUPPORT_SEGMENT_SCHEMA:
            plan, audit = _mapping(segment.get("plan")), _mapping(segment.get("audit"))
            if (
                plan.get("parent_state_sha256") != current
                or plan.get("diagnostic_only") is not True
                or plan.get("fit_admission") is not False
                or plan.get("action_trace_available") is not False
                or audit.get("audit_actions") != 0
                or audit.get("audit_frames") != 0
            ):
                raise RedRecordedSupportError("verified support scope differs")
            source = plan.get("source_commit")
            if not isinstance(source, str) or len(source) != 40 or any(
                c not in "0123456789abcdef" for c in source
            ):
                raise RedRecordedSupportError("support executable source missing")
            for name in (
                "retained_declaration_sha256",
                "retained_claim_sha256",
                "retained_result_sha256",
            ):
                value = plan.get(name)
                if not isinstance(value, str) or len(value) != 64 or any(
                    c not in "0123456789abcdef" for c in value
                ):
                    raise RedRecordedSupportError("verified support receipt identity differs")
            encoded = segment.get("state_base64")
            if not isinstance(encoded, str) or not 0 < len(encoded) <= 699052:
                raise RedRecordedSupportError("support state encoding differs")
            try:
                state = base64.b64decode(encoded, altchars=b"-_", validate=True)
            except ValueError as error:
                raise RedRecordedSupportError("support state encoding differs") from error
            current = hashlib.sha256(state).hexdigest()
            count, elapsed = audit.get("actions"), audit.get("frames")
            if (
                not state
                or current != audit.get("state_sha256")
                or type(count) is not int
                or type(elapsed) is not int
                or count < 0
                or elapsed < 0
                or count > plan.get("maximum_actions", -1)
                or elapsed > plan.get("maximum_frames", -1)
                or audit.get("retry_authorized") is not False
                or audit.get("training_examples") != 0
                or not isinstance(audit.get("status"), str)
                or not audit.get("status")
            ):
                raise RedRecordedSupportError("verified support audit differs")
            actions += count
            frames += elapsed
            continue
        plan, audit = _mapping(segment.get("plan")), _mapping(segment.get("audit"))
        if (
            plan.get("parent_state_sha256") != current
            or plan.get("diagnostic_only") is not True or plan.get("fit_admission") is not False
            or audit.get("audit_actions") != 0 or audit.get("audit_frames") != 0
        ):
            raise RedRecordedSupportError("support parent or no-learning declaration differs")
        source = plan.get("source_commit")
        if not isinstance(source, str) or len(source) != 40 or any(
            c not in "0123456789abcdef" for c in source
        ):
            raise RedRecordedSupportError("support executable source missing")
        encoded = segment.get("state_base64")
        if not isinstance(encoded, str) or not 0 < len(encoded) <= 699052:
            raise RedRecordedSupportError("support state encoding differs")
        try:
            state = base64.b64decode(encoded, altchars=b"-_", validate=True)
        except ValueError as error:
            raise RedRecordedSupportError("support state encoding differs") from error
        current = hashlib.sha256(state).hexdigest()
        if not state or current != audit.get("state_sha256", audit.get("terminal_state_sha256")):
            raise RedRecordedSupportError("support terminal audit and bytes differ")
        trace = segment.get("trace")
        if not isinstance(trace, list) or not trace or len(trace) % 2:
            raise RedRecordedSupportError("support has an incomplete action trace")
        previous = 0
        for index in range(0, len(trace), 2):
            before, after = _mapping(trace[index]), _mapping(trace[index + 1])
            frame = after.get("frame")
            if (
                before.get("frame_before") != previous
                or not isinstance(before.get("intent"), Mapping)
                or after.get("after") != index // 2 + 1
                or type(frame) is not int or frame <= previous
            ):
                raise RedRecordedSupportError("support action ordering or frame cost differs")
            previous = frame
        count = len(trace) // 2
        if count > plan.get("max_actions", plan.get("maximum_actions", 0)) or previous > plan.get(
            "max_frames", plan.get("maximum_frames", 0)
        ):
            raise RedRecordedSupportError("support exceeded its original budget")
        result = segment.get("result")
        accounting = _mapping(result) if result is not None else audit
        if accounting.get("actions") != count or accounting.get("frames") != previous:
            raise RedRecordedSupportError("support recorded costs disagree with trace")
        if result is not None and _mapping(result).get("terminal_state_sha256") != current:
            raise RedRecordedSupportError("support result terminal differs")
        actions += count
        frames += previous
    return actions, frames, current


@dataclass(frozen=True, slots=True)
class RedRecordedSupportResult:
    parent_episode_id: str
    parent_checkpoint_sha256: str
    parent_manifest_sha256: str
    segments_sha256: str
    historical_actions: int
    historical_frames: int

    @property
    def steps(self) -> tuple[()]:
        return ()

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": SUPPORT_TERMINAL_SCHEMA,
            "authority_id": "recorded-development-support-import",
            "status": "imported_retained_state",
            "steps": [], "authority_decisions": 0, "decisions": 0, "training_examples": 0,
            "completion_satisfied": False, "independent_root": False,
            "total_actions": 0, "total_frames": 0,
            "historical_support_actions": self.historical_actions,
            "historical_support_frames": self.historical_frames,
            "evidence_scope": "retained_local_diagnostic_records_not_native_gameplay",
            "origin": {
                "episode_id": self.parent_episode_id,
                "checkpoint_sha256": self.parent_checkpoint_sha256,
                "manifest_sha256": self.parent_manifest_sha256,
                "segments_sha256": self.segments_sha256,
            },
        }


@dataclass(frozen=True, slots=True)
class RedRegisteredRecordedSupportResult(RedRecordedSupportResult):
    """Zero-label admission of hash-chained guarded receipts to a registered lineage."""

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": REGISTERED_SUPPORT_TERMINAL_SCHEMA,
            "authority_id": "registered-recorded-support-import",
            "status": "imported_retained_state",
            "steps": [],
            "authority_decisions": 0,
            "decisions": 0,
            "training_examples": 0,
            "completion_satisfied": False,
            "independent_root": False,
            "total_actions": 0,
            "total_frames": 0,
            "historical_support_actions": self.historical_actions,
            "historical_support_frames": self.historical_frames,
            "evidence_scope": "hash_chained_guarded_receipts_without_action_trace",
            "origin": {
                "episode_id": self.parent_episode_id,
                "checkpoint_sha256": self.parent_checkpoint_sha256,
                "manifest_sha256": self.parent_manifest_sha256,
                "segments_sha256": self.segments_sha256,
            },
        }


def require_recorded_support_origin(store: PrivateArtifactRoot, document: Mapping) -> None:
    from .red_player_checkpoint import CHECKPOINT_KIND, checkpoint_record_id

    terminal = document.get("terminal_result")
    schema = document.get("schema")
    is_support = schema in {SUPPORT_CHECKPOINT_SCHEMA, REGISTERED_SUPPORT_CHECKPOINT_SCHEMA}
    if is_support != (
        isinstance(terminal, Mapping)
        and terminal.get("schema")
        == (
            REGISTERED_SUPPORT_TERMINAL_SCHEMA
            if schema == REGISTERED_SUPPORT_CHECKPOINT_SCHEMA
            else SUPPORT_TERMINAL_SCHEMA
        )
    ):
        raise RedRecordedSupportError("support checkpoint and terminal types differ")
    if not is_support:
        return
    terminal = _mapping(terminal)
    origin = _mapping(terminal.get("origin"))
    parent_id = origin.get("episode_id")
    if not isinstance(parent_id, str) or parent_id == document.get("episode_id"):
        raise RedRecordedSupportError("support predecessor identity differs")
    record = store.find_sealed_record(
        checkpoint_record_id(parent_id), expected_kind=CHECKPOINT_KIND,
    )
    if record is None or record.summary.record_sha256 != origin.get("checkpoint_sha256"):
        raise RedRecordedSupportError("support predecessor checkpoint differs")
    parent = record.read()
    parent_episode = store.open_episode(parent_id)
    if (
        parent.get("schema") in {SUPPORT_CHECKPOINT_SCHEMA, REGISTERED_SUPPORT_CHECKPOINT_SCHEMA}
        or parent_episode.manifest_sha256 != origin.get("manifest_sha256")
        or parent.get("trajectory_manifest_sha256") != parent_episode.manifest_sha256
        or list(parent_episode.iter_stream("checkpoint")) != [
            {k: v for k, v in parent.items() if k != "trajectory_manifest_sha256"}
        ]
    ):
        raise RedRecordedSupportError("support requires its original completed native predecessor")
    for key, original in (
        ("original_state_sha256", "state_sha256"),
        ("profile_sha256", "profile_sha256"), ("rom_sha256", "rom_sha256"),
        ("model_sha256", "model_sha256"), ("context_origin", "context_origin"),
        ("search_memory", "search_memory"),
    ):
        if document.get(key) != parent.get(original):
            raise RedRecordedSupportError("support changed inherited scope or search memory")
    if document.get("original_envelope_sha256") != hashlib.sha256(
        json.dumps(parent["envelope"]).encode("ascii")
    ).hexdigest():
        raise RedRecordedSupportError("support inherited envelope differs")
    old_collection, new_collection = _mapping(parent.get("collection")), _mapping(
        document.get("collection"),
    )
    for key in old_collection:
        if key != "storage_headroom" and new_collection.get(key) != old_collection[key]:
            raise RedRecordedSupportError("transport support changed the living collection")
    episode = store.open_episode(document["episode_id"])
    metadata = _mapping(episode.read_header().get("metadata"))
    previous = _mapping(parent_episode.read_header().get("metadata"))
    if (
        metadata.get("schema")
        != (
            REGISTERED_SUPPORT_HEADER_SCHEMA
            if schema == REGISTERED_SUPPORT_CHECKPOINT_SCHEMA
            else SUPPORT_HEADER_SCHEMA
        )
        or metadata.get("training_eligible") is not False
        or metadata.get("split") != previous.get("split")
        or metadata.get("player_training_plan") is not None
        or {"decisions", "executions"}.intersection(episode.stream_names)
    ):
        raise RedRecordedSupportError("support import changed partition or invented gameplay")
    split = _mapping(metadata.get("split"))
    if split.get("partition") != "train" or not isinstance(split.get("root_lineage_id"), str):
        raise RedRecordedSupportError("support requires an explicit training lineage")
    # Observer flags are inherited, not opportunities to revise historical menus.
    for flag in (
        "routed_recovery", "trainer_funding", "trainer_pending_recovery",
        "regional_trainer_funding", "observed_trainer_funding",
        "remaining_acquisition_demand", "level_evolution_acquisitions",
    ):
        if metadata.get(flag, False) != previous.get(flag, False):
            raise RedRecordedSupportError("support changed an inherited observer mode")
    segments = list(episode.iter_stream("recorded_support", max_records=8))
    actions, frames, final = support_costs(segments, document["original_state_sha256"])
    first_plan = _mapping(segments[0]["plan"])
    if (
        final != document.get("state_sha256")
        or first_plan.get("parent_episode") != parent_id
        or first_plan.get("parent_checkpoint_sha256") != origin["checkpoint_sha256"]
    ):
        raise RedRecordedSupportError("support terminal or first native anchor differs")
    result_type = (
        RedRegisteredRecordedSupportResult
        if schema == REGISTERED_SUPPORT_CHECKPOINT_SCHEMA
        else RedRecordedSupportResult
    )
    expected = result_type(
        parent_id, origin["checkpoint_sha256"], origin["manifest_sha256"],
        canonical_sha256(segments), actions, frames,
    ).public_dict()
    if terminal != expected:
        raise RedRecordedSupportError("support terminal scope or historical costs differ")
