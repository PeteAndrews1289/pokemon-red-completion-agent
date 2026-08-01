from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.runtime_identity import (
    PYBOY_INVENTORY_SCHEMA,
    RUNTIME_IDENTITY_SCHEMA,
)
from pokemon_red_completion.trajectory import (
    TRAJECTORY_SCHEMA_VERSION,
    DecisionContext,
    DecisionRecord,
    ExecutionRecord,
    ExecutionStatus,
    InMemoryTrajectorySink,
    RecordingExecutor,
    SemanticSnapshot,
    SparseEvent,
    TrajectorySinkClosedError,
    TrajectoryValidationError,
    canonical_json,
    canonical_sha256,
)


def _snapshot(
    *,
    mode: str = "overworld",
    location: str = "starter_town",
    hp: int = 20,
) -> SemanticSnapshot:
    return SemanticSnapshot(
        game_id="example_monsters_v1",
        mode=mode,
        location=location,
        facts=("party:starter", "story:intro_complete"),
        features={
            "party": [{"species": "starter", "hp": hp, "status": None}],
            "position": {"x": 4, "y": 7},
        },
    )


def test_semantic_snapshot_is_versioned_normalized_and_deeply_immutable() -> None:
    source_features = {
        "position": {"y": 7, "x": 4},
        "choices": ["fight", "item"],
    }
    snapshot = SemanticSnapshot(
        game_id="example",
        mode="battle",
        facts=("story:ready", "badge:first", "story:ready"),
        features=source_features,
    )

    source_features["position"]["x"] = 99
    source_features["choices"].append("run")

    assert snapshot.schema_version == TRAJECTORY_SCHEMA_VERSION
    assert snapshot.facts == ("badge:first", "story:ready")
    assert snapshot.features["position"] == {"x": 4, "y": 7}
    assert snapshot.features["choices"] == ("fight", "item")
    with pytest.raises(TypeError):
        snapshot.features["new"] = True  # type: ignore[index]
    with pytest.raises(TypeError):
        snapshot.features["position"]["x"] = 8  # type: ignore[index]
    assert snapshot.to_dict()["features"] == {
        "position": {"x": 4, "y": 7},
        "choices": ["fight", "item"],
    }


@pytest.mark.parametrize(
    ("unsafe", "message"),
    [
        (b"ROM bytes", "binary data"),
        (bytearray(b"save"), "binary data"),
        (memoryview(b"state"), "binary data"),
        (Path("/Users/example/private.gb"), "filesystem Path"),
        ("/Users/example/private.gb", "path-like text"),
        (r"C:\private\game.gb", "path-like text"),
        ("file:private-game", "path-like text"),
        (math.nan, "non-finite float"),
        (math.inf, "non-finite float"),
        (-math.inf, "non-finite float"),
        ({1: "not a string key"}, "non-string mapping key"),
    ],
)
def test_json_safety_rejects_unsafe_values_recursively(
    unsafe: object,
    message: str,
) -> None:
    with pytest.raises(TrajectoryValidationError, match=message):
        SemanticSnapshot(
            game_id="example",
            mode="overworld",
            features={"outer": [{"nested": unsafe}]},
        )


def _runtime_metadata(inventory_name: str) -> dict[str, object]:
    files = [
        {
            "name": inventory_name,
            "bytes": 7,
            "sha256": "a" * 64,
        }
    ]
    inventory = {
        "schema": PYBOY_INVENTORY_SCHEMA,
        "distribution_name": "pyboy",
        "distribution_version": "2.7.0",
        "files": files,
    }
    inventory_sha256 = hashlib.sha256(
        (
            json.dumps(
                inventory,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("ascii")
    ).hexdigest()
    return {
        "runtime": {
            "schema": RUNTIME_IDENTITY_SCHEMA,
            "python": {
                "implementation": "CPython",
                "version": "3.14.3",
                "executable_sha256": "b" * 64,
            },
            "pyboy": {
                "distribution_name": "pyboy",
                "distribution_version": "2.7.0",
                "files": files,
                "inventory_sha256": inventory_sha256,
            },
        }
    }


def test_json_safety_accepts_only_canonical_runtime_inventory_logical_names() -> None:
    metadata = _runtime_metadata("pyboy/api/constants.py")

    assert json.loads(canonical_json(metadata)) == metadata


@pytest.mark.parametrize(
    "inventory_name",
    (
        "/Users/example/pyboy.py",
        r"C:\Users\example\pyboy.py",
        "~/pyboy.py",
        "file:pyboy/runtime.py",
        "../pyboy/runtime.py",
        "pyboy/../runtime.py",
        "pyboy/./runtime.py",
        "pyboy//runtime.py",
        r"pyboy\private.py",
        "pyboy/runtimé.py",
        "Users/example/Downloads/private.gb",
        "private/api-token.txt",
    ),
)
def test_json_safety_rejects_unsafe_runtime_inventory_names(
    inventory_name: str,
) -> None:
    with pytest.raises(TrajectoryValidationError, match="path-like text"):
        canonical_json(_runtime_metadata(inventory_name))


def test_json_safety_keeps_relative_paths_strict_outside_runtime_inventory() -> None:
    with pytest.raises(TrajectoryValidationError, match="path-like text"):
        canonical_json({"source": "pyboy/runtime.py"})

    with pytest.raises(TrajectoryValidationError, match="path-like text"):
        canonical_json(
            {
                "runtime.pyboy.files[0].name": "pyboy/runtime.py",
            }
        )

    with pytest.raises(TrajectoryValidationError, match="path-like text"):
        canonical_json(
            {
                "runtime": {
                    "pyboy": {
                        "files": [
                            {
                                "name": "pyboy/runtime.py",
                            }
                        ]
                    }
                }
            }
        )


@pytest.mark.parametrize(
    "key",
    [
        "rom_path",
        "ROM-PATH",
        "save_state",
        "apiKey",
        "access-token",
        "database_password",
        "session_secret",
        "auth_token",
        "raw_memory",
        "screenshot_path",
    ],
)
def test_reserved_sensitive_keys_are_rejected_at_any_depth(key: str) -> None:
    with pytest.raises(TrajectoryValidationError, match="reserved sensitive key"):
        SemanticSnapshot(
            game_id="example",
            mode="overworld",
            features={"safe": [{"still_safe": {key: "must never be recorded"}}]},
        )


def test_recursive_containers_and_non_json_objects_are_rejected() -> None:
    recursive: dict[str, object] = {}
    recursive["loop"] = recursive

    with pytest.raises(TrajectoryValidationError, match="recursive mapping"):
        canonical_json(recursive)
    with pytest.raises(TrajectoryValidationError, match="unsupported JSON value"):
        canonical_json({"set": {"unordered"}})


def test_canonical_json_and_sha256_are_deterministic_and_ascii() -> None:
    first = {
        "z": [3, 2, 1],
        "a": {"unicode": "フシギダネ", "enabled": True},
    }
    second = {
        "a": MappingProxyType({"enabled": True, "unicode": "フシギダネ"}),
        "z": (3, 2, 1),
    }

    encoded = canonical_json(first)

    assert encoded == canonical_json(second)
    assert encoded == (
        '{"a":{"enabled":true,"unicode":"\\u30d5\\u30b7\\u30ae\\u30c0\\u30cd"},"z":[3,2,1]}'
    )
    assert canonical_sha256(first) == canonical_sha256(second)
    assert len(canonical_sha256(first)) == 64
    assert json.loads(encoded) == first


def test_string_enums_are_serialized_as_their_portable_value() -> None:
    assert canonical_json({"kind": MacroActionKind.MOVE}) == '{"kind":"move"}'


def test_snapshot_hash_changes_only_with_semantic_content() -> None:
    first = _snapshot(hp=20)
    equivalent = SemanticSnapshot(
        game_id="example_monsters_v1",
        mode="overworld",
        location="starter_town",
        facts=("story:intro_complete", "party:starter"),
        features={
            "position": {"y": 7, "x": 4},
            "party": [{"status": None, "hp": 20, "species": "starter"}],
        },
    )

    assert first.sha256 == equivalent.sha256
    assert first.sha256 != _snapshot(hp=19).sha256


def test_decision_and_execution_records_link_exact_snapshots() -> None:
    before = _snapshot(hp=20)
    after = _snapshot(hp=14)
    context = DecisionContext(
        objective_id="win_first_battle",
        policy_id="teacher-v1",
        actor="battle",
        metadata={"legal_actions": [1, 2]},
    )
    decision = DecisionRecord(
        decision_id="episode-1:decision:4",
        episode_id="episode-1",
        step_index=4,
        snapshot=before,
        context=context,
        decision_type="act",
        action={"kind": "battle_move", "slot": 1},
    )
    execution = ExecutionRecord(
        execution_id="episode-1:execution:4",
        episode_id="episode-1",
        step_index=4,
        decision_id=decision.decision_id,
        action={"kind": "battle_move", "slot": 1},
        before_snapshot=before,
        after_snapshot=after,
        buttons=("a",),
        frames=2,
    )

    assert decision.snapshot_sha256 == before.sha256
    assert execution.before_sha256 == before.sha256
    assert execution.after_sha256 == after.sha256
    assert execution.to_dict()["decision_id"] == decision.decision_id
    assert execution.to_dict()["status"] == "success"
    assert canonical_sha256(execution) == canonical_sha256(execution.to_dict())


def test_record_schemas_reject_invalid_versions_and_inconsistent_errors() -> None:
    with pytest.raises(TrajectoryValidationError, match="schema_version"):
        SemanticSnapshot(
            game_id="example",
            mode="overworld",
            schema_version=2,
        )

    with pytest.raises(TrajectoryValidationError, match="cannot contain error_type"):
        ExecutionRecord(
            execution_id="execution-1",
            episode_id="episode-1",
            step_index=0,
            action={"kind": "wait"},
            before_snapshot=_snapshot(),
            after_snapshot=_snapshot(),
            error_type="RuntimeError",
        )

    with pytest.raises(TrajectoryValidationError, match="sanitized class name"):
        ExecutionRecord(
            execution_id="execution-1",
            episode_id="episode-1",
            step_index=0,
            action={"kind": "wait"},
            before_snapshot=_snapshot(),
            after_snapshot=_snapshot(),
            status=ExecutionStatus.ERROR,
            error_type="RuntimeError: secret detail",
        )


def test_sparse_events_and_in_memory_sink_are_typed_and_finalize_cleanly() -> None:
    sink = InMemoryTrajectorySink()
    snapshot = _snapshot()
    decision = DecisionRecord(
        decision_id="decision-0",
        episode_id="episode-1",
        step_index=0,
        snapshot=snapshot,
        context=DecisionContext(actor="teacher"),
        decision_type="act",
        action={"kind": "move", "direction": "up"},
    )
    execution = ExecutionRecord(
        execution_id="execution-0",
        episode_id="episode-1",
        step_index=0,
        decision_id=decision.decision_id,
        action={"kind": "move", "direction": "up"},
        before_snapshot=snapshot,
        after_snapshot=snapshot,
        buttons=("up",),
        frames=2,
    )
    event = SparseEvent(
        event_id="event-0",
        episode_id="episode-1",
        step_index=0,
        kind="objective_completed",
        payload={"objective_id": "leave_home"},
    )

    sink.record_decision(decision)
    sink.record_execution(execution)
    sink.record_event(event)

    assert sink.decisions == (decision,)
    assert sink.executions == (execution,)
    assert sink.events == (event,)
    with pytest.raises(TrajectoryValidationError, match="duplicate"):
        sink.record_event(event)

    sink.finalize()
    sink.finalize()
    assert sink.finalized
    with pytest.raises(TrajectorySinkClosedError, match="finalized"):
        sink.record_execution(execution)


@dataclass(frozen=True)
class FakeAction:
    kind: str
    value: int
    repeat: int = 1


@dataclass(frozen=True)
class FakeResult:
    buttons: tuple[str, ...]
    frames: int


class SequencedSnapshots:
    def __init__(self, *snapshots: SemanticSnapshot) -> None:
        self._snapshots = list(snapshots)
        self.calls = 0

    def snapshot(self) -> SemanticSnapshot:
        snapshot = self._snapshots[self.calls]
        self.calls += 1
        return snapshot


class SuccessfulExecutor:
    def __init__(self, result: FakeResult) -> None:
        self.result = result
        self.actions: list[FakeAction] = []

    def execute(self, action: FakeAction) -> FakeResult:
        self.actions.append(action)
        return self.result


def test_recording_executor_decorates_without_changing_successful_behavior() -> None:
    before = _snapshot(hp=20)
    after = _snapshot(hp=14)
    snapshots = SequencedSnapshots(before, after)
    result = FakeResult(("a",), 3)
    delegate = SuccessfulExecutor(result)
    sink = InMemoryTrajectorySink()
    recorder = RecordingExecutor(
        delegate=delegate,
        snapshot_provider=snapshots,
        sink=sink,
        episode_id="episode-1",
        start_step_index=7,
    )
    action = FakeAction("battle_move", 1)

    returned = recorder.execute(action, decision_id="decision-7")

    assert returned is result
    assert delegate.actions == [action]
    assert snapshots.calls == 2
    assert recorder.next_step_index == 8
    assert len(sink.executions) == 1
    record = sink.executions[0]
    assert record.execution_id == "episode-1:execution:7"
    assert record.decision_id == "decision-7"
    assert record.action == {"kind": "battle_move", "value": 1, "repeat": 1}
    assert record.before_snapshot is before
    assert record.after_snapshot is after
    assert record.buttons == ("a",)
    assert record.frames == 3
    assert record.status is ExecutionStatus.SUCCESS
    assert record.error_type is None


class PrivateFailure(RuntimeError):
    pass


class FailingExecutor:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def execute(self, action: FakeAction) -> FakeResult:
        raise self.error


def test_recording_executor_reraises_same_error_and_records_only_sanitized_type() -> None:
    before = _snapshot(hp=20)
    after = _snapshot(hp=1)
    snapshots = SequencedSnapshots(before, after)
    error = PrivateFailure("secret ROM path: /Users/example/Downloads/game.gb; token=do-not-record")
    sink = InMemoryTrajectorySink()
    recorder = RecordingExecutor(
        delegate=FailingExecutor(error),
        snapshot_provider=snapshots,
        sink=sink,
        episode_id="episode-private-error",
    )

    with pytest.raises(PrivateFailure) as caught:
        recorder.execute(FakeAction("confirm", 1))

    assert caught.value is error
    assert snapshots.calls == 2
    assert recorder.next_step_index == 1
    assert len(sink.executions) == 1
    record = sink.executions[0]
    assert record.status is ExecutionStatus.ERROR
    assert record.error_type == "PrivateFailure"
    serialized = canonical_json(record)
    assert "secret ROM path" not in serialized
    assert "/Users/example" not in serialized
    assert "do-not-record" not in serialized


class BrokenSink(InMemoryTrajectorySink):
    def record_execution(self, record: ExecutionRecord) -> None:
        raise RuntimeError("storage unavailable")


def test_recording_failures_do_not_change_delegate_results_or_errors() -> None:
    result = FakeResult(("up",), 2)
    successful = RecordingExecutor(
        delegate=SuccessfulExecutor(result),
        snapshot_provider=SequencedSnapshots(_snapshot(), _snapshot()),
        sink=BrokenSink(),
        episode_id="episode-success",
    )

    assert successful.execute(FakeAction("move", 1)) is result
    assert successful.recording_failures == 1
    assert successful.recording_failure_reasons == {"execution_success_record": 1}

    original = PrivateFailure("controller failure")
    failing = RecordingExecutor(
        delegate=FailingExecutor(original),
        snapshot_provider=SequencedSnapshots(_snapshot(), _snapshot()),
        sink=BrokenSink(),
        episode_id="episode-error",
    )
    with pytest.raises(PrivateFailure) as caught:
        failing.execute(FakeAction("confirm", 1))
    assert caught.value is original
    assert failing.recording_failures == 1
    assert failing.recording_failure_reasons == {"execution_error_record": 1}


def test_decision_scope_records_once_and_links_every_execution_in_the_span() -> None:
    first = _snapshot(hp=20)
    second = _snapshot(hp=18)
    third = _snapshot(hp=14)
    fourth = _snapshot(hp=13)
    snapshots = SequencedSnapshots(first, second, second, third, third, fourth)
    result = FakeResult(("a",), 3)
    sink = InMemoryTrajectorySink()
    recorder = RecordingExecutor(
        delegate=SuccessfulExecutor(result),
        snapshot_provider=snapshots,
        sink=sink,
        episode_id="episode-scoped",
        start_step_index=4,
    )
    decision = DecisionRecord(
        decision_id="episode-scoped:decision:0",
        episode_id="episode-scoped",
        step_index=4,
        snapshot=first,
        context=DecisionContext(actor="teacher"),
        decision_type="battle_move_selection",
        action={"kind": "select_move", "slot_index": 0},
    )

    with recorder.decision_scope(decision):
        recorder.execute(FakeAction("confirm", 1))
        recorder.execute(FakeAction("move", 1))
    recorder.execute(FakeAction("wait", 1))

    assert sink.decisions == (decision,)
    assert [record.decision_id for record in sink.executions] == [
        decision.decision_id,
        decision.decision_id,
        None,
    ]
    assert recorder.recording_failures == 0


def test_decision_scope_resets_after_controller_exception() -> None:
    before = _snapshot(hp=20)
    after = _snapshot(hp=19)
    sink = InMemoryTrajectorySink()
    recorder = RecordingExecutor(
        delegate=SuccessfulExecutor(FakeResult(("a",), 1)),
        snapshot_provider=SequencedSnapshots(before, after),
        sink=sink,
        episode_id="episode-reset",
    )
    decision = DecisionRecord(
        decision_id="episode-reset:decision:0",
        episode_id="episode-reset",
        step_index=0,
        snapshot=before,
        context=DecisionContext(actor="teacher"),
        decision_type="battle_move_selection",
        action={"kind": "select_move", "slot_index": 0},
    )

    with pytest.raises(PrivateFailure), recorder.decision_scope(decision):
        raise PrivateFailure("controller stopped before execution")

    recorder.execute(FakeAction("confirm", 1))
    assert sink.executions[0].decision_id is None
    assert recorder.recording_failures == 1


class BrokenDecisionSink(InMemoryTrajectorySink):
    def record_decision(self, record: DecisionRecord) -> None:
        raise RuntimeError("decision storage unavailable")


def test_broken_decision_recording_is_fail_open_but_blocks_promotion() -> None:
    before = _snapshot(hp=20)
    after = _snapshot(hp=19)
    result = FakeResult(("a",), 1)
    sink = BrokenDecisionSink()
    recorder = RecordingExecutor(
        delegate=SuccessfulExecutor(result),
        snapshot_provider=SequencedSnapshots(before, after),
        sink=sink,
        episode_id="episode-broken-decision",
    )

    with recorder.decision_scope(
        lambda: DecisionRecord(
            decision_id="episode-broken-decision:decision:0",
            episode_id="episode-broken-decision",
            step_index=0,
            snapshot=before,
            context=DecisionContext(actor="teacher"),
            decision_type="battle_move_selection",
            action={"kind": "select_move", "slot_index": 0},
        )
    ):
        returned = recorder.execute(FakeAction("confirm", 1))

    assert returned is result
    assert sink.executions[0].decision_id is None
    assert recorder.recording_failures == 1


def test_decision_scope_rejects_a_changed_first_execution_observation() -> None:
    decision_snapshot = _snapshot(hp=20)
    changed_before = _snapshot(hp=19)
    changed_after = _snapshot(hp=18)
    result = FakeResult(("a",), 1)
    sink = InMemoryTrajectorySink()
    recorder = RecordingExecutor(
        delegate=SuccessfulExecutor(result),
        snapshot_provider=SequencedSnapshots(changed_before, changed_after),
        sink=sink,
        episode_id="episode-changed-observation",
    )
    decision = DecisionRecord(
        decision_id="episode-changed-observation:decision:0",
        episode_id="episode-changed-observation",
        step_index=0,
        snapshot=decision_snapshot,
        context=DecisionContext(actor="teacher"),
        decision_type="battle_move_selection",
        action={"kind": "select_move", "slot_index": 0},
    )

    with recorder.decision_scope(decision):
        returned = recorder.execute(FakeAction("confirm", 1))

    assert returned is result
    assert sink.decisions == (decision,)
    assert sink.executions == ()
    assert recorder.recording_failures == 1
