#!/usr/bin/env python3
"""Collect authentic Red move outcomes for the rapid development loop."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_scenario_capture import (  # noqa: E402
    open_battle_scenario_capture,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.provenance import canonical_sha256  # noqa: E402
from pokemon_red_completion.red_battle_outcome_runtime import (  # noqa: E402
    collect_red_battle_outcome_example,
)
from pokemon_red_completion.repeatable_battle_dataset import (  # noqa: E402
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
    root_ids = tuple(capture.manifest.root_lineage_id for capture in captures)
    if len(state_ids) != len(set(state_ids)) or len(root_ids) != len(set(root_ids)):
        raise RepeatableBattleCollectionError("capture states and roots must be distinct")
    train_roots = {
        capture.manifest.root_lineage_id
        for capture in captures
        if capture.manifest.partition is ScenarioPartition.TRAIN
    }
    development_roots = set(root_ids) - train_roots
    if train_roots & development_roots:  # pragma: no cover - set construction invariant
        raise RepeatableBattleCollectionError("a root crosses train and development")

    records: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for ordinal, capture in enumerate(captures, start=1):
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
        records.append(
            repeatable_battle_outcome_record(
                collection.example,
                capture_id=collection.capture_id,
                manifest_sha256=collection.manifest_sha256,
            )
        )
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
    payload = "".join(
        json.dumps(record, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    ).encode("ascii")
    _write_exclusive(args.output, payload)
    failure_path = args.failure_report or args.output.with_suffix(".failures.json")
    _write_exclusive(
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


def _write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)


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
