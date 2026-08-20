from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.collection_protocol import (
    BATTLE_START_SCHEDULE_SCHEMA,
    POKEMON_RED_GAME_ID,
    BattleStartOffset,
    battle_start_offsets_sha256,
)
from pokemon_red_completion.executor import FrameSafeExecutor
from pokemon_red_completion.private_artifacts import initialize_private_root
from pokemon_red_completion.schedule_audit import (
    ScheduleAttestationError,
    audit_schedule_attestations,
)
from pokemon_red_completion.trajectory import (
    RecordingExecutor,
    SemanticSnapshot,
    SparseEvent,
    canonical_sha256,
)
from pokemon_red_completion.trajectory_io import EpisodeTrajectorySink


class _Reader:
    def __init__(self, header, events, executions, snapshots) -> None:
        self.header = header
        self.events = events
        self.executions = executions
        self.snapshots = snapshots

    def read_header(self):
        return deepcopy(self.header)

    def iter_stream(self, stream: str, *, max_records: int | None = None):
        values = {
            "events": self.events,
            "executions": self.executions,
            "snapshots": self.snapshots,
        }[stream]
        if max_records is not None and len(values) > max_records:
            raise AssertionError("fixture exceeded limit")
        yield from deepcopy(values)


class _Controller:
    def __init__(self) -> None:
        self.frames = 0

    def press(self, button: str) -> None:
        raise AssertionError(f"WAIT unexpectedly pressed {button}")

    def release(self, button: str) -> None:
        raise AssertionError(f"WAIT unexpectedly released {button}")

    def tick(self, frames: int) -> None:
        self.frames += frames


class _SnapshotProvider:
    def __init__(self, snapshot: SemanticSnapshot) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> SemanticSnapshot:
        return self._snapshot


def _production_episode(tmp_path: Path):
    episode_id = "episode-production-schedule"
    offsets = (BattleStartOffset("battle-001-production-test", 7),)
    schedule_sha256 = battle_start_offsets_sha256(offsets)
    repository = tmp_path / "repository"
    root = tmp_path / "private"
    repository.mkdir()
    root.mkdir()
    store = initialize_private_root(
        root,
        repository_root=repository,
        device_id=lambda path: 2 if path == root.resolve() else 1,
        git_worktree_probe=lambda path: False,
    )
    snapshot = SemanticSnapshot(
        game_id=POKEMON_RED_GAME_ID,
        mode="battle",
        location="pallet_town",
        features={"battle_ordinal": 1},
    )
    controller = _Controller()

    with store.begin_episode(episode_id) as writer:
        sink = EpisodeTrajectorySink(
            writer,
            episode_id=episode_id,
            game_id=POKEMON_RED_GAME_ID,
        )
        sink.write_episode_header(
            metadata={
                "configuration": {
                    "battle_start_schedule": {
                        "offsets": [offset.public_dict() for offset in offsets],
                        "schedule_sha256": schedule_sha256,
                        "schema": BATTLE_START_SCHEDULE_SCHEMA,
                    }
                }
            }
        )
        recorder = RecordingExecutor(
            delegate=FrameSafeExecutor(controller),
            snapshot_provider=_SnapshotProvider(snapshot),
            sink=sink,
            episode_id=episode_id,
        )
        executed = recorder.execute(MacroAction(MacroActionKind.WAIT, repeat=offsets[0].frames))
        sink.record_event(
            SparseEvent(
                event_id=f"{episode_id}:schedule:1",
                episode_id=episode_id,
                step_index=recorder.next_step_index,
                kind="battle_start_offset_applied",
                payload={
                    "after_snapshot_sha256": snapshot.sha256,
                    "battle_ordinal": 1,
                    "battle_plan_id": offsets[0].battle_plan_id,
                    "before_snapshot_sha256": snapshot.sha256,
                    "execution_step_index": 0,
                    "frames": offsets[0].frames,
                    "schedule_sha256": schedule_sha256,
                },
            )
        )
        sink.record_event(
            SparseEvent(
                event_id=f"{episode_id}:terminal",
                episode_id=episode_id,
                step_index=recorder.next_step_index + 1,
                kind="terminal",
                payload={
                    "status": "complete",
                    "game_complete": True,
                    "qualified_through": "enter_hall_of_fame",
                    "battle_start_schedule": {
                        "complete": True,
                        "expected_battles": 1,
                        "finished_battles": 1,
                        "schedule_sha256": schedule_sha256,
                    },
                },
            )
        )
        sink.finalize()

        assert executed.frames == offsets[0].frames
        assert controller.frames == offsets[0].frames
        assert recorder.recording_failures == 0
        assert sink.counts["snapshots"] == 1

    return (
        store.open_episode(episode_id),
        episode_id,
        offsets,
        schedule_sha256,
    )


def _fixture():
    episode_id = "episode-schedule"
    offsets = (
        BattleStartOffset("battle-001-test", 7),
        BattleStartOffset("battle-002-test", 0),
    )
    schedule_sha256 = battle_start_offsets_sha256(offsets)
    before_document = {"mode": "battle", "ordinal": 1}
    before = canonical_sha256(before_document)
    after = before
    zero = canonical_sha256({"mode": "battle", "ordinal": 2})
    header = {
        "record_type": "episode",
        "trajectory_schema": "pokemon.trajectory.v1",
        "episode_id": episode_id,
        "game_id": POKEMON_RED_GAME_ID,
        "metadata": {
            "configuration": {
                "battle_start_schedule": {
                    "offsets": [offset.public_dict() for offset in offsets],
                    "schedule_sha256": schedule_sha256,
                    "schema": BATTLE_START_SCHEDULE_SCHEMA,
                }
            }
        },
    }
    events = [
        {
            "record_type": "event",
            "schema_version": 1,
            "event_id": f"{episode_id}:schedule:1",
            "episode_id": episode_id,
            "step_index": 12,
            "kind": "battle_start_offset_applied",
            "payload": {
                "after_snapshot_sha256": after,
                "battle_ordinal": 1,
                "battle_plan_id": offsets[0].battle_plan_id,
                "before_snapshot_sha256": before,
                "execution_step_index": 11,
                "frames": 7,
                "schedule_sha256": schedule_sha256,
            },
        },
        {
            "record_type": "event",
            "schema_version": 1,
            "event_id": f"{episode_id}:schedule:2",
            "episode_id": episode_id,
            "step_index": 20,
            "kind": "battle_start_offset_applied",
            "payload": {
                "after_snapshot_sha256": zero,
                "battle_ordinal": 2,
                "battle_plan_id": offsets[1].battle_plan_id,
                "before_snapshot_sha256": zero,
                "execution_step_index": None,
                "frames": 0,
                "schedule_sha256": schedule_sha256,
            },
        },
        {
            "record_type": "event",
            "schema_version": 1,
            "event_id": f"{episode_id}:terminal",
            "episode_id": episode_id,
            "step_index": 100,
            "kind": "terminal",
            "payload": {
                "status": "complete",
                "game_complete": True,
                "qualified_through": "enter_hall_of_fame",
                "battle_start_schedule": {
                    "complete": True,
                    "expected_battles": 2,
                    "finished_battles": 2,
                    "schedule_sha256": schedule_sha256,
                },
            },
        },
    ]
    executions = [
        {
            "record_type": "execution",
            "schema_version": 1,
            "execution_id": f"{episode_id}:execution:11",
            "episode_id": episode_id,
            "step_index": 11,
            "decision_id": None,
            "action": {"kind": "wait", "value": None, "repeat": 7},
            "before_sha256": before,
            "after_sha256": after,
            "buttons": [],
            "frames": 7,
            "status": "success",
            "error_type": None,
        }
    ]
    snapshots = [
        {
            "record_type": "snapshot",
            "snapshot_sha256": before,
            "snapshot": before_document,
        }
    ]
    return (
        episode_id,
        offsets,
        schedule_sha256,
        header,
        events,
        executions,
        snapshots,
    )


def test_schedule_audit_authenticates_positive_and_zero_offsets() -> None:
    episode_id, offsets, digest, header, events, executions, snapshots = _fixture()

    receipt = audit_schedule_attestations(
        _Reader(header, events, executions, snapshots),
        episode_id=episode_id,
        offsets=offsets,
        schedule_sha256=digest,
    )

    assert receipt.public_dict() == {
        "schema": "pokemon-red-schedule-attestation-audit-v1",
        "schedule_sha256": digest,
        "expected_battles": 2,
        "attested_battles": 2,
        "positive_offsets": 1,
        "zero_offsets": 1,
        "complete": True,
    }


def test_schedule_audit_accepts_production_trajectory_evidence(tmp_path: Path) -> None:
    reader, episode_id, offsets, digest = _production_episode(tmp_path)

    receipt = audit_schedule_attestations(
        reader,
        episode_id=episode_id,
        offsets=offsets,
        schedule_sha256=digest,
    )

    assert receipt.attested_battles == receipt.expected_battles == 1
    assert receipt.positive_offsets == 1
    assert (
        list(reader.iter_stream("snapshots"))[0]["snapshot_sha256"]
        == next(reader.iter_stream("executions"))["before_sha256"]
    )


@pytest.mark.parametrize("mutation", ("non_production_schema", "missing_snapshot"))
def test_schedule_audit_rejects_tampered_production_trajectory_evidence(
    tmp_path: Path,
    mutation: str,
) -> None:
    reader, episode_id, offsets, digest = _production_episode(tmp_path)
    header = reader.read_header()
    events = list(reader.iter_stream("events"))
    executions = list(reader.iter_stream("executions"))
    snapshots = list(reader.iter_stream("snapshots"))

    if mutation == "non_production_schema":
        executions[0]["schema_version"] = 0
    else:
        unrelated = SemanticSnapshot(
            game_id=POKEMON_RED_GAME_ID,
            mode="overworld",
            location="pallet_town",
        )
        snapshots[:] = [
            {
                "record_type": "snapshot",
                "snapshot_sha256": unrelated.sha256,
                "snapshot": unrelated.to_dict(),
            }
        ]

    with pytest.raises(ScheduleAttestationError):
        audit_schedule_attestations(
            _Reader(header, events, executions, snapshots),
            episode_id=episode_id,
            offsets=offsets,
            schedule_sha256=digest,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_event",
        "wrong_frame",
        "fake_zero_execution",
        "wrong_wait",
        "wrong_snapshot_link",
        "incomplete_terminal",
        "header_mismatch",
    ),
)
def test_schedule_audit_rejects_incomplete_or_forged_evidence(mutation: str) -> None:
    episode_id, offsets, digest, header, events, executions, snapshots = _fixture()
    if mutation == "missing_event":
        events.pop(1)
    elif mutation == "wrong_frame":
        events[0]["payload"]["frames"] = 8
    elif mutation == "fake_zero_execution":
        events[1]["payload"]["execution_step_index"] = 19
    elif mutation == "wrong_wait":
        executions[0]["action"]["kind"] = "move"
    elif mutation == "wrong_snapshot_link":
        executions[0]["after_sha256"] = "d" * 64
    elif mutation == "incomplete_terminal":
        events[-1]["payload"]["battle_start_schedule"]["finished_battles"] = 1
    else:
        header["metadata"]["configuration"]["battle_start_schedule"]["schedule_sha256"] = "e" * 64

    with pytest.raises(ScheduleAttestationError):
        audit_schedule_attestations(
            _Reader(header, events, executions, snapshots),
            episode_id=episode_id,
            offsets=offsets,
            schedule_sha256=digest,
        )
