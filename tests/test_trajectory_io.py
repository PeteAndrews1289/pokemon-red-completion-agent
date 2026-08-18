from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest

from pokemon_red_completion.private_artifacts import (
    EpisodeWriter,
    initialize_private_root,
)
from pokemon_red_completion.runtime_identity import (
    PYBOY_INVENTORY_SCHEMA,
    RuntimeFileIdentity,
    RuntimeIdentity,
)
from pokemon_red_completion.trajectory import (
    DecisionContext,
    DecisionRecord,
    ExecutionRecord,
    SemanticSnapshot,
    SparseEvent,
    TrajectorySinkClosedError,
    TrajectoryValidationError,
)
from pokemon_red_completion.trajectory_io import EpisodeTrajectorySink

EPISODE_ID = "episode-001"
GAME_ID = "pokemon.mainline:red"


@dataclass
class _MemoryWriter:
    records: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def append(self, stream: str, record: Mapping[str, object]) -> None:
        self.records.append((stream, dict(record)))


@dataclass
class _DurableMemoryWriter:
    records: list[tuple[str, dict[str, object], bool]] = field(default_factory=list)

    def append(
        self,
        stream: str,
        record: Mapping[str, object],
        *,
        durable: bool = False,
    ) -> None:
        self.records.append((stream, dict(record), durable))


def _sink(writer: _MemoryWriter | None = None) -> EpisodeTrajectorySink:
    memory_writer = writer if writer is not None else _MemoryWriter()
    return EpisodeTrajectorySink(
        cast(EpisodeWriter, memory_writer),
        episode_id=EPISODE_ID,
        game_id=GAME_ID,
    )


def _write_header(sink: EpisodeTrajectorySink) -> None:
    files = (
        RuntimeFileIdentity("console_scripts/up-3/pyboy", 7, "b" * 64),
        RuntimeFileIdentity(
            "pyboy-2.7.0.dist-info/licenses/LICENSE.md",
            13,
            "d" * 64,
        ),
        RuntimeFileIdentity("pyboy/api/constants.py", 11, "c" * 64),
    )
    inventory = {
        "schema": PYBOY_INVENTORY_SCHEMA,
        "distribution_name": "pyboy",
        "distribution_version": "2.7.0",
        "files": [file.public_dict() for file in files],
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
    runtime = RuntimeIdentity(
        python_implementation="CPython",
        python_version="3.14.3",
        python_executable_sha256="a" * 64,
        pyboy_distribution_name="pyboy",
        pyboy_distribution_version="2.7.0",
        pyboy_files=files,
        pyboy_inventory_sha256=inventory_sha256,
    )
    sink.write_episode_header(
        metadata={
            "adapter_id": "pokemon.red.v1",
            "ontology_id": "pokemon.core.v1",
            "policy": {
                "actor": "deterministic_teacher",
                "policy_id": "teacher.v0.2.0",
                "source_version": "0.2.0",
            },
            "collection": {
                "assistance_class": "teacher",
                "start_type": "clean_power_on",
            },
            "runtime": runtime.public_dict(),
        }
    )


def test_episode_sink_opts_every_record_into_durable_writes() -> None:
    writer = _DurableMemoryWriter()
    sink = EpisodeTrajectorySink(
        cast(EpisodeWriter, writer),
        episode_id=EPISODE_ID,
        game_id=GAME_ID,
        durable_writes=True,
    )
    _write_header(sink)
    sink.record_decision(_decision())
    sink.record_event(_event())
    sink.record_event(_event(event_id="terminal", step_index=1, kind="terminal"))

    assert writer.records
    assert all(durable for _stream, _record, durable in writer.records)


def _snapshot(*, game_id: str = GAME_ID, mode: str = "overworld") -> SemanticSnapshot:
    return SemanticSnapshot(
        game_id=game_id,
        mode=mode,
        location="pokemon.red:area:pallet_town",
    )


def _decision(
    *,
    decision_id: str = "decision-0",
    episode_id: str = EPISODE_ID,
    snapshot: SemanticSnapshot | None = None,
    step_index: int = 0,
) -> DecisionRecord:
    return DecisionRecord(
        decision_id=decision_id,
        episode_id=episode_id,
        step_index=step_index,
        snapshot=snapshot or _snapshot(),
        context=DecisionContext(actor="teacher"),
        decision_type="act",
        action={"domain": "navigation", "verb": "step", "direction": "up"},
    )


def _execution(
    *,
    execution_id: str = "execution-0",
    episode_id: str = EPISODE_ID,
    step_index: int = 0,
    decision_id: str | None = None,
    before_snapshot: SemanticSnapshot | None = None,
    after_snapshot: SemanticSnapshot | None = None,
) -> ExecutionRecord:
    return ExecutionRecord(
        execution_id=execution_id,
        episode_id=episode_id,
        step_index=step_index,
        decision_id=decision_id,
        action={"kind": "move", "value": "up"},
        before_snapshot=before_snapshot or _snapshot(),
        after_snapshot=after_snapshot or _snapshot(),
        buttons=("up",),
        frames=2,
    )


def _event(
    *,
    event_id: str = "event-0",
    episode_id: str = EPISODE_ID,
    step_index: int = 0,
    kind: str = "checkpoint",
) -> SparseEvent:
    return SparseEvent(
        event_id=event_id,
        episode_id=episode_id,
        step_index=step_index,
        kind=kind,
        payload={"checkpoint_id": "outside"} if kind != "terminal" else {},
    )


def test_episode_sink_writes_content_addressed_path_free_streams(tmp_path: Path) -> None:
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
    snapshot = _snapshot()

    with store.begin_episode(EPISODE_ID) as writer:
        sink = EpisodeTrajectorySink(
            writer,
            episode_id=EPISODE_ID,
            game_id=GAME_ID,
        )
        _write_header(sink)
        decision = _decision(snapshot=snapshot)
        sink.record_decision(decision)
        sink.record_execution(
            _execution(
                decision_id=decision.decision_id,
                before_snapshot=snapshot,
                after_snapshot=snapshot,
            )
        )
        sink.record_event(_event())
        sink.record_event(_event(event_id="event-terminal", step_index=1, kind="terminal"))
        assert sink.counts == {
            "decisions": 1,
            "executions": 1,
            "events": 2,
            "snapshots": 1,
        }
        sink.finalize()

    final = root / EPISODE_ID
    assert {path.name for path in final.iterdir()} == {
        "decisions.jsonl",
        "episode.jsonl",
        "events.jsonl",
        "executions.jsonl",
        "manifest.json",
        "snapshots.jsonl",
    }
    header = json.loads((final / "episode.jsonl").read_text(encoding="ascii"))
    assert header["episode_id"] == EPISODE_ID
    assert header["game_id"] == GAME_ID
    assert header["metadata"]["policy"]["policy_id"] == "teacher.v0.2.0"
    assert [
        file["name"] for file in header["metadata"]["runtime"]["pyboy"]["files"]
    ] == [
        "console_scripts/up-3/pyboy",
        "pyboy-2.7.0.dist-info/licenses/LICENSE.md",
        "pyboy/api/constants.py",
    ]

    decision_row = json.loads((final / "decisions.jsonl").read_text(encoding="ascii"))
    execution_row = json.loads((final / "executions.jsonl").read_text(encoding="ascii"))
    snapshot_row = json.loads((final / "snapshots.jsonl").read_text(encoding="ascii"))
    assert "snapshot" not in decision_row
    assert "before_snapshot" not in execution_row
    assert "after_snapshot" not in execution_row
    assert decision_row["snapshot_sha256"] == snapshot_row["snapshot_sha256"]
    assert execution_row["before_sha256"] == snapshot_row["snapshot_sha256"]
    assert execution_row["after_sha256"] == snapshot_row["snapshot_sha256"]

    serialized = "".join(
        path.read_text(encoding="ascii") for path in final.iterdir() if path.is_file()
    )
    assert str(tmp_path) not in serialized


@pytest.mark.parametrize("field_name", ["episode_id", "game_id"])
def test_sink_requires_bound_non_empty_identity(field_name: str) -> None:
    arguments = {"episode_id": EPISODE_ID, "game_id": GAME_ID}
    arguments[field_name] = " "
    with pytest.raises(TrajectoryValidationError, match=field_name):
        EpisodeTrajectorySink(
            cast(EpisodeWriter, _MemoryWriter()),
            **arguments,
        )


@pytest.mark.parametrize(
    "record_call",
    [
        lambda sink: sink.record_decision(_decision()),
        lambda sink: sink.record_execution(_execution()),
        lambda sink: sink.record_event(_event()),
    ],
)
def test_records_require_header(
    record_call: Callable[[EpisodeTrajectorySink], None],
) -> None:
    sink = _sink()
    with pytest.raises(TrajectoryValidationError, match="header"):
        record_call(sink)


def test_header_is_exactly_once_and_metadata_is_validated() -> None:
    sink = _sink()
    with pytest.raises(TypeError, match="mapping"):
        sink.write_episode_header(metadata=cast(Mapping[str, object], "invalid"))
    _write_header(sink)
    with pytest.raises(TrajectoryValidationError, match="already"):
        _write_header(sink)

    unsafe_sink = _sink()
    with pytest.raises(TrajectoryValidationError, match="filesystem Path"):
        unsafe_sink.write_episode_header(metadata={"data_path": Path("/private/data")})


@pytest.mark.parametrize(
    ("method_name", "value", "message"),
    [
        ("record_decision", object(), "DecisionRecord"),
        ("record_execution", object(), "ExecutionRecord"),
        ("record_event", object(), "SparseEvent"),
    ],
)
def test_record_methods_preserve_typed_input_validation(
    method_name: str,
    value: object,
    message: str,
) -> None:
    sink = _sink()
    _write_header(sink)

    method = getattr(sink, method_name)
    with pytest.raises(TypeError, match=message):
        method(value)
    assert sink.counts == {
        "decisions": 0,
        "executions": 0,
        "events": 0,
        "snapshots": 0,
    }


@pytest.mark.parametrize(
    "record_call",
    [
        lambda sink: sink.record_decision(_decision(episode_id="wrong-episode")),
        lambda sink: sink.record_execution(_execution(episode_id="wrong-episode")),
        lambda sink: sink.record_event(_event(episode_id="wrong-episode")),
    ],
)
def test_all_records_must_match_bound_episode(
    record_call: Callable[[EpisodeTrajectorySink], None],
) -> None:
    sink = _sink()
    _write_header(sink)
    with pytest.raises(TrajectoryValidationError, match="episode_id"):
        record_call(sink)


def test_all_snapshots_must_match_bound_game() -> None:
    sink = _sink()
    _write_header(sink)
    wrong = _snapshot(game_id="pokemon.mainline:yellow")

    with pytest.raises(TrajectoryValidationError, match="game_id"):
        sink.record_decision(_decision(snapshot=wrong))
    with pytest.raises(TrajectoryValidationError, match="game_id"):
        sink.record_execution(_execution(before_snapshot=wrong))
    with pytest.raises(TrajectoryValidationError, match="game_id"):
        sink.record_execution(_execution(after_snapshot=wrong))
    assert sink.counts["snapshots"] == 0


def test_record_ids_are_unique_across_all_streams() -> None:
    sink = _sink()
    _write_header(sink)
    sink.record_decision(_decision(decision_id="shared-id"))

    with pytest.raises(TrajectoryValidationError, match="duplicate"):
        sink.record_event(_event(event_id="shared-id"))
    assert sink.counts["events"] == 0


def test_execution_indices_are_strictly_monotonic() -> None:
    sink = _sink()
    _write_header(sink)
    sink.record_execution(_execution(execution_id="execution-2", step_index=2))

    with pytest.raises(TrajectoryValidationError, match="strictly greater"):
        sink.record_execution(_execution(execution_id="execution-equal", step_index=2))
    with pytest.raises(TrajectoryValidationError, match="strictly greater"):
        sink.record_execution(_execution(execution_id="execution-lower", step_index=1))
    sink.record_execution(_execution(execution_id="execution-4", step_index=4))
    assert sink.counts["executions"] == 2


def test_non_null_decision_reference_must_already_exist() -> None:
    sink = _sink()
    _write_header(sink)

    with pytest.raises(TrajectoryValidationError, match="unknown decision"):
        sink.record_execution(_execution(decision_id="decision-0"))
    sink.record_decision(_decision())
    sink.record_execution(_execution(decision_id="decision-0"))
    sink.record_execution(
        _execution(execution_id="execution-unlinked", step_index=1, decision_id=None)
    )
    assert sink.counts["executions"] == 2


@pytest.mark.parametrize(
    "record_call",
    [
        lambda sink: sink.record_decision(_decision()),
        lambda sink: sink.record_execution(_execution()),
        lambda sink: sink.record_event(_event(event_id="late-event")),
    ],
)
def test_no_records_are_accepted_after_terminal(
    record_call: Callable[[EpisodeTrajectorySink], None],
) -> None:
    sink = _sink()
    _write_header(sink)
    sink.record_event(_event(event_id="terminal", kind="terminal"))

    with pytest.raises(TrajectoryValidationError, match="after the terminal"):
        record_call(sink)
    assert sink.counts == {
        "decisions": 0,
        "executions": 0,
        "events": 1,
        "snapshots": 0,
    }


def test_finalize_requires_one_header_and_exactly_one_terminal() -> None:
    sink = _sink()
    with pytest.raises(TrajectoryValidationError, match="header"):
        sink.finalize()

    _write_header(sink)
    with pytest.raises(TrajectoryValidationError, match="terminal"):
        sink.finalize()

    sink.record_event(_event(event_id="terminal", kind="terminal"))
    with pytest.raises(TrajectoryValidationError, match="after the terminal"):
        sink.record_event(_event(event_id="second-terminal", kind="terminal"))
    sink.finalize()

    with pytest.raises(TrajectorySinkClosedError, match="finalized"):
        sink.finalize()
    with pytest.raises(TrajectorySinkClosedError, match="finalized"):
        sink.record_event(_event(event_id="after-finalize"))


def test_path_like_metadata_is_rejected_without_advancing_header() -> None:
    writer = _MemoryWriter()
    sink = _sink(writer)

    with pytest.raises(TrajectoryValidationError, match="path-like text"):
        sink.write_episode_header(metadata={"source": "/private/data"})
    assert writer.records == []

    _write_header(sink)
    assert len(writer.records) == 1
