#!/usr/bin/env python3
"""Collect authentic Red move outcomes for the rapid development loop."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_scenario_capture import (  # noqa: E402
    BattleScenarioCapture,
    open_battle_scenario_capture,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.provenance import (  # noqa: E402
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_battle_outcome_runtime import (  # noqa: E402
    collect_red_battle_outcome_example,
)
from pokemon_red_completion.repeatable_battle_dataset import (  # noqa: E402
    parse_repeatable_battle_outcome_record,
    repeatable_battle_outcome_record,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402


class RepeatableBattleCollectionError(RuntimeError):
    """Raised when the development collection cannot remain well formed."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--capture-dir", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--journal-dir",
        type=Path,
        default=None,
        help="durable per-capture journal; defaults beside --output",
    )
    parser.add_argument(
        "--failure-report",
        type=Path,
        default=None,
        help="defaults beside --output",
    )
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    pairs = _capture_pairs(args.capture_dir)
    captures = tuple(open_battle_scenario_capture(state, manifest) for state, manifest in pairs)
    if any(capture.manifest.partition is ScenarioPartition.TEST for capture in captures):
        raise RepeatableBattleCollectionError("sealed test captures are not development inputs")
    state_ids = tuple(capture.manifest.state_sha256 for capture in captures)
    if len(state_ids) != len(set(state_ids)):
        raise RepeatableBattleCollectionError("capture states must be distinct")
    train_roots = {
        capture.manifest.root_lineage_id
        for capture in captures
        if capture.manifest.partition is ScenarioPartition.TRAIN
    }
    development_roots = {
        capture.manifest.root_lineage_id
        for capture in captures
        if capture.manifest.partition is ScenarioPartition.DEVELOPMENT
    }
    if train_roots & development_roots:
        raise RepeatableBattleCollectionError("a root crosses train and development")

    source_identity = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source_identity)
    require_published_source(PROJECT_ROOT, source_identity)
    if source_identity.git_commit is None:  # pragma: no cover - clean source owns this
        raise AssertionError("published collector source lacks a commit")

    journal_dir = args.journal_dir or args.output.with_name(f"{args.output.name}.journal")
    journal_header = {
        "schema": "pokemon.core.battle.repeatable-collection-journal.v2",
        "collector_source_commit": source_identity.git_commit,
        "rom_sha256": rom.sha256,
        "captures": [
            {
                "ordinal": ordinal,
                "capture_id": capture.manifest.capture_id,
                "manifest_sha256": capture.manifest_sha256,
                "state_sha256": capture.manifest.state_sha256,
                "root_lineage_id": capture.manifest.root_lineage_id,
                "partition": capture.manifest.partition.value,
            }
            for ordinal, capture in enumerate(captures, start=1)
        ],
    }
    _prepare_journal(journal_dir, journal_header)

    records: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for ordinal, capture in enumerate(captures, start=1):
        terminal_path = _terminal_path(journal_dir, ordinal, capture.manifest.capture_id)
        claim_path = _claim_path(journal_dir, ordinal, capture.manifest.capture_id)
        retained = _read_terminal(terminal_path, capture=capture, ordinal=ordinal)
        if retained is not None:
            if not claim_path.exists():
                raise RepeatableBattleCollectionError(
                    "collection terminal has no durable input claim"
                )
            _read_claim(claim_path, capture=capture, ordinal=ordinal)
            if retained["status"] == "complete":
                record = retained["record"]
                if not isinstance(record, dict):  # pragma: no cover - reader invariant
                    raise AssertionError("complete journal terminal has no record")
                records.append(record)
            else:
                failure = retained["failure"]
                if not isinstance(failure, dict):  # pragma: no cover - reader invariant
                    raise AssertionError("failed journal terminal has no failure")
                failures.append(failure)
            print(
                json.dumps(
                    {
                        "event": "capture_recovered",
                        "completed": ordinal,
                        "total": len(captures),
                        "capture_id": capture.manifest.capture_id,
                        "status": retained["status"],
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            continue
        if claim_path.exists():
            _read_claim(claim_path, capture=capture, ordinal=ordinal)
            failure = {
                "capture_id": capture.manifest.capture_id,
                "partition": capture.manifest.partition.value,
                "error_type": "InterruptedCapture",
                "reason": "capture was claimed before input but produced no terminal record",
            }
            failures.append(failure)
            _write_json_new_atomic(
                terminal_path,
                {
                    "schema": "pokemon.core.battle.repeatable-collection-terminal.v1",
                    "ordinal": ordinal,
                    "capture_id": capture.manifest.capture_id,
                    "manifest_sha256": capture.manifest_sha256,
                    "status": "quarantined",
                    "record": None,
                    "failure": failure,
                },
            )
            print(
                json.dumps(
                    {
                        "event": "capture_interruption_quarantined",
                        "completed": ordinal,
                        "total": len(captures),
                        **failure,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            continue
        _write_json_new_atomic(
            claim_path,
            {
                "schema": "pokemon.core.battle.repeatable-collection-claim.v1",
                "ordinal": ordinal,
                "capture_id": capture.manifest.capture_id,
                "manifest_sha256": capture.manifest_sha256,
                "state_sha256": capture.manifest.state_sha256,
                "status": "started",
            },
        )
        try:
            collection = collect_red_battle_outcome_example(
                capture,
                session_factory=lambda: PyBoyAdapter(rom_path),
            )
        except RuntimeError as error:
            failure: dict[str, object] = {
                "capture_id": capture.manifest.capture_id,
                "partition": capture.manifest.partition.value,
                "error_type": type(error).__name__,
                "reason": str(error),
            }
            failures.append(failure)
            _write_json_new_atomic(
                terminal_path,
                {
                    "schema": "pokemon.core.battle.repeatable-collection-terminal.v1",
                    "ordinal": ordinal,
                    "capture_id": capture.manifest.capture_id,
                    "manifest_sha256": capture.manifest_sha256,
                    "status": "quarantined",
                    "record": None,
                    "failure": failure,
                },
            )
            print(
                json.dumps(
                    {
                        "event": "capture_quarantined",
                        "completed": ordinal,
                        "total": len(captures),
                        **failure,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            continue
        record = repeatable_battle_outcome_record(
            collection.example,
            capture_id=collection.capture_id,
            manifest_sha256=collection.manifest_sha256,
        )
        _write_json_new_atomic(
            terminal_path,
            {
                "schema": "pokemon.core.battle.repeatable-collection-terminal.v1",
                "ordinal": ordinal,
                "capture_id": capture.manifest.capture_id,
                "manifest_sha256": capture.manifest_sha256,
                "status": "complete",
                "record": record,
                "failure": None,
            },
        )
        records.append(record)
        print(
            json.dumps(
                {
                    "event": "capture_complete",
                    "completed": ordinal,
                    "total": len(captures),
                    "capture_id": collection.capture_id,
                    "partition": collection.example.partition.value,
                    "informative": collection.example.learner_update_eligible,
                },
                sort_keys=True,
            ),
            flush=True,
        )

    if not records:
        raise RepeatableBattleCollectionError("no complete battle outcomes were collected")
    examples = tuple(parse_repeatable_battle_outcome_record(record) for record in records)
    train_clusters = {
        example.semantic_cluster_sha256
        for example in examples
        if example.partition is ScenarioPartition.TRAIN
    }
    development_clusters = {
        example.semantic_cluster_sha256
        for example in examples
        if example.partition is ScenarioPartition.DEVELOPMENT
    }
    if train_clusters & development_clusters:
        raise RepeatableBattleCollectionError(
            "semantic battle cluster crosses train and development"
        )
    payload = "".join(
        json.dumps(record, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    ).encode("ascii")
    _publish_idempotent(args.output, payload)
    failure_path = args.failure_report or args.output.with_suffix(".failures.json")
    _publish_idempotent(
        failure_path,
        (
            json.dumps(
                {
                    "schema": "pokemon.core.battle.repeatable-collection-failures.v1",
                    "failures": failures,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("ascii"),
    )
    summary = {
        "schema": "pokemon.core.battle.repeatable-outcome-collection.v1",
        "dataset_sha256": canonical_sha256(records),
        "rom_sha256": rom.sha256,
        "collector_source_commit": source_identity.git_commit,
        "examples": len(records),
        "training_examples": sum(
            record["partition"] == ScenarioPartition.TRAIN.value for record in records
        ),
        "development_examples": sum(
            record["partition"] == ScenarioPartition.DEVELOPMENT.value
            for record in records
        ),
        "informative_examples": sum(
            record["learner_update_eligible"] is True for record in records
        ),
        "training_semantic_clusters": len(train_clusters),
        "development_semantic_clusters": len(development_clusters),
        "semantic_duplicate_examples": len(examples)
        - len(train_clusters)
        - len(development_clusters),
        "semantic_partition_overlap": 0,
        "quarantined_captures": len(failures),
        "private_path_fields": 0,
        "sealed_test_cases_opened": 0,
        "development_artifact": True,
    }
    return summary


def _capture_pairs(directories: list[Path]) -> tuple[tuple[Path, Path], ...]:
    pairs: list[tuple[Path, Path]] = []
    for directory in directories:
        if not directory.is_dir():
            raise RepeatableBattleCollectionError("capture directory is unavailable")
        for manifest in sorted(directory.glob("*.state.json")):
            state = manifest.with_suffix("")
            if not state.is_file():
                raise RepeatableBattleCollectionError("capture state is unavailable")
            pairs.append((state, manifest))
    if not pairs:
        raise RepeatableBattleCollectionError("no battle captures were discovered")
    return tuple(pairs)


def _terminal_path(journal_dir: Path, ordinal: int, capture_id: str) -> Path:
    identity = canonical_sha256(capture_id)[:16]
    return journal_dir / f"{ordinal:04d}-{identity}.terminal.json"


def _claim_path(journal_dir: Path, ordinal: int, capture_id: str) -> Path:
    identity = canonical_sha256(capture_id)[:16]
    return journal_dir / f"{ordinal:04d}-{identity}.claim.json"


def _prepare_journal(journal_dir: Path, header: dict[str, object]) -> None:
    journal_dir.mkdir(parents=True, exist_ok=True)
    header_path = journal_dir / "manifest.json"
    payload = _canonical_json_line(header)
    if header_path.exists():
        if header_path.read_bytes() != payload:
            raise RepeatableBattleCollectionError(
                "collection journal belongs to different inputs"
            )
        return
    _write_new_atomic(header_path, payload)


def _read_terminal(
    path: Path,
    *,
    capture: BattleScenarioCapture,
    ordinal: int,
) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text("ascii"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise RepeatableBattleCollectionError(
            "collection journal terminal is invalid"
        ) from None
    manifest = capture.manifest
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "schema",
            "ordinal",
            "capture_id",
            "manifest_sha256",
            "status",
            "record",
            "failure",
        }
        or value.get("schema")
        != "pokemon.core.battle.repeatable-collection-terminal.v1"
        or value.get("ordinal") != ordinal
        or value.get("capture_id") != manifest.capture_id
        or value.get("manifest_sha256") != capture.manifest_sha256
        or value.get("status") not in {"complete", "quarantined"}
    ):
        raise RepeatableBattleCollectionError("collection journal terminal is invalid")
    if value["status"] == "complete":
        record = value["record"]
        if not isinstance(record, dict) or value["failure"] is not None:
            raise RepeatableBattleCollectionError("collection journal terminal is invalid")
        parsed = parse_repeatable_battle_outcome_record(record)
        if (
            record.get("capture_id") != manifest.capture_id
            or record.get("manifest_sha256") != capture.manifest_sha256
            or parsed.root_lineage_id != manifest.root_lineage_id
            or parsed.initial_state_sha256 != manifest.state_sha256
            or parsed.partition is not manifest.partition
        ):
            raise RepeatableBattleCollectionError("collection journal record binding is invalid")
    elif not isinstance(value["failure"], dict) or value["record"] is not None:
        raise RepeatableBattleCollectionError("collection journal terminal is invalid")
    return value


def _read_claim(
    path: Path,
    *,
    capture: BattleScenarioCapture,
    ordinal: int,
) -> dict[str, object]:
    try:
        value = json.loads(path.read_text("ascii"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise RepeatableBattleCollectionError(
            "collection journal claim is invalid"
        ) from None
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "schema",
            "ordinal",
            "capture_id",
            "manifest_sha256",
            "state_sha256",
            "status",
        }
        or value.get("schema")
        != "pokemon.core.battle.repeatable-collection-claim.v1"
        or value.get("ordinal") != ordinal
        or value.get("capture_id") != capture.manifest.capture_id
        or value.get("manifest_sha256") != capture.manifest_sha256
        or value.get("state_sha256") != capture.manifest.state_sha256
        or value.get("status") != "started"
    ):
        raise RepeatableBattleCollectionError("collection journal claim is invalid")
    return value


def _canonical_json_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("ascii")


def _write_json_new_atomic(path: Path, value: object) -> None:
    _write_new_atomic(path, _canonical_json_line(value))


def _publish_idempotent(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise FileExistsError(path)
        return
    _write_new_atomic(path, payload)


def _write_new_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            raise FileExistsError(path)
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        os.close(descriptor)
        if temporary.exists():
            temporary.unlink()


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def main() -> int:
    try:
        result = _run(_parser().parse_args())
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        print(f"repeatable battle collection failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
