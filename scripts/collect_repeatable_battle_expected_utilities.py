#!/usr/bin/env python3
"""Collect multi-RNG Red battle trials and publish expected-utility targets."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_expected_utility import (  # noqa: E402
    aggregate_battle_rng_trials,
    expected_utility_record,
)
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

DEFAULT_FRAME_TARGETS = (2_048, 2_063, 2_101, 2_161, 2_251, 2_377, 2_539)


class RepeatableBattleExpectedUtilityCollectionError(RuntimeError):
    """Raised when a multi-RNG collection cannot retain its frozen identity."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--capture-dir", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--journal-dir", type=Path, required=True)
    parser.add_argument("--failure-report", type=Path, required=True)
    parser.add_argument(
        "--frame-target",
        type=int,
        action="append",
        default=None,
        help="repeat for a custom prospective schedule",
    )
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    targets = _frame_targets(args.frame_target)
    _require_output(args.output, subject="expected-utility dataset")
    _require_output(args.failure_report, subject="failure report")
    if args.output.resolve() == args.failure_report.resolve():
        raise RepeatableBattleExpectedUtilityCollectionError(
            "dataset and failure outputs must differ"
        )
    if args.journal_dir.exists() and not args.journal_dir.is_dir():
        raise RepeatableBattleExpectedUtilityCollectionError(
            "journal path is not a directory"
        )
    if args.journal_dir.resolve().is_relative_to(PROJECT_ROOT.resolve()):
        raise RepeatableBattleExpectedUtilityCollectionError(
            "journal must remain outside the repository"
        )

    pairs = _capture_pairs(args.capture_dir)
    captures = tuple(open_battle_scenario_capture(*pair) for pair in pairs)
    if any(capture.manifest.partition is ScenarioPartition.TEST for capture in captures):
        raise RepeatableBattleExpectedUtilityCollectionError(
            "sealed test captures are not expected-utility inputs"
        )
    if len({capture.manifest.capture_id for capture in captures}) != len(captures):
        raise RepeatableBattleExpectedUtilityCollectionError(
            "capture identities must be distinct"
        )
    if len({capture.manifest.state_sha256 for capture in captures}) != len(captures):
        raise RepeatableBattleExpectedUtilityCollectionError(
            "capture states must be distinct"
        )
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
        raise RepeatableBattleExpectedUtilityCollectionError(
            "a root crosses train and development"
        )

    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - source guard owns this
        raise AssertionError("published collector source lacks a commit")
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    header: dict[str, object] = {
        "schema": "pokemon.core.battle.expected-utility-journal.v1",
        "collector_source_commit": source.git_commit,
        "rom_sha256": rom.sha256,
        "frame_targets": list(targets),
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
    _prepare_journal(args.journal_dir, header)
    _require_completed_journal_for_existing_outputs(
        args,
        captures=captures,
        targets=targets,
    )

    trials_by_capture: dict[str, list[dict[str, object]]] = defaultdict(list)
    trial_failures: list[dict[str, object]] = []
    total_trials = len(captures) * len(targets)
    completed_trials = 0
    for capture_ordinal, capture in enumerate(captures, start=1):
        for frame_target in targets:
            capture_digest = canonical_sha256(capture.manifest.capture_id)[:12]
            identity = f"{capture_ordinal:04d}-{frame_target}-{capture_digest}"
            claim_path = args.journal_dir / f"{identity}.claim.json"
            terminal_path = args.journal_dir / f"{identity}.terminal.json"
            terminal = _read_terminal(
                terminal_path,
                capture=capture,
                capture_ordinal=capture_ordinal,
                frame_target=frame_target,
            )
            if terminal is None and claim_path.exists():
                _read_claim(
                    claim_path,
                    capture=capture,
                    capture_ordinal=capture_ordinal,
                    frame_target=frame_target,
                )
                terminal = _quarantined_terminal(
                    capture,
                    capture_ordinal=capture_ordinal,
                    frame_target=frame_target,
                    error_type="InterruptedTrial",
                    reason="trial was claimed before input but produced no terminal",
                )
                _write_json_new_atomic(terminal_path, terminal)
            elif terminal is None:
                _write_json_new_atomic(
                    claim_path,
                    _claim(
                        capture,
                        capture_ordinal=capture_ordinal,
                        frame_target=frame_target,
                    ),
                )
                try:
                    collection = collect_red_battle_outcome_example(
                        capture,
                        session_factory=lambda: PyBoyAdapter(rom_path),
                        minimum_pre_attack_frames=frame_target,
                    )
                    record = repeatable_battle_outcome_record(
                        collection.example,
                        capture_id=collection.capture_id,
                        manifest_sha256=collection.manifest_sha256,
                    )
                    terminal = {
                        "schema": "pokemon.core.battle.expected-utility-trial-terminal.v1",
                        "capture_ordinal": capture_ordinal,
                        "capture_id": capture.manifest.capture_id,
                        "manifest_sha256": capture.manifest_sha256,
                        "frame_target": frame_target,
                        "status": "complete",
                        "record": record,
                        "failure": None,
                    }
                except RuntimeError as error:
                    terminal = _quarantined_terminal(
                        capture,
                        capture_ordinal=capture_ordinal,
                        frame_target=frame_target,
                        error_type=type(error).__name__,
                        reason=_bounded_reason(error),
                    )
                _write_json_new_atomic(terminal_path, terminal)
            completed_trials += 1
            if terminal["status"] == "complete":
                terminal_record = terminal["record"]
                if not isinstance(  # pragma: no cover - reader owns this
                    terminal_record,
                    dict,
                ):
                    raise AssertionError("complete trial lacks a record")
                trials_by_capture[capture.manifest.capture_id].append(terminal_record)
            else:
                failure = terminal["failure"]
                if not isinstance(failure, dict):  # pragma: no cover - reader owns this
                    raise AssertionError("failed trial lacks a failure")
                trial_failures.append(failure)
            print(
                json.dumps(
                    {
                        "event": "expected_utility_trial_terminal",
                        "completed_trials": completed_trials,
                        "total_trials": total_trials,
                        "capture_id": capture.manifest.capture_id,
                        "frame_target": frame_target,
                        "status": terminal["status"],
                    },
                    sort_keys=True,
                ),
                flush=True,
            )

    aggregate_records = []
    excluded_captures = []
    for capture in captures:
        trial_records = trials_by_capture[capture.manifest.capture_id]
        if len(trial_records) != len(targets):
            excluded_captures.append(
                {
                    "capture_id": capture.manifest.capture_id,
                    "complete_trials": len(trial_records),
                    "required_trials": len(targets),
                    "reason": "incomplete prospective RNG schedule",
                }
            )
            continue
        examples = tuple(parse_repeatable_battle_outcome_record(row) for row in trial_records)
        aggregate = aggregate_battle_rng_trials(examples)
        aggregate_records.append(
            expected_utility_record(
                aggregate,
                capture_id=capture.manifest.capture_id,
                manifest_sha256=capture.manifest_sha256,
            )
        )
    if not aggregate_records:
        raise RepeatableBattleExpectedUtilityCollectionError(
            "no complete expected-utility examples were collected"
        )
    dataset_payload = "".join(
        json.dumps(record, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        for record in aggregate_records
    ).encode("ascii")
    failure_payload = _json_line(
        {
            "schema": "pokemon.core.battle.expected-utility-failures.v1",
            "trial_failures": trial_failures,
            "excluded_captures": excluded_captures,
        }
    )
    _write_or_verify_atomic(args.output, dataset_payload)
    _write_or_verify_atomic(args.failure_report, failure_payload)
    return {
        "schema": "pokemon.core.battle.expected-utility-collection.v1",
        "collector_source_commit": source.git_commit,
        "rom_sha256": rom.sha256,
        "frame_targets": list(targets),
        "captures_presented": len(captures),
        "trials_presented": total_trials,
        "trials_complete": total_trials - len(trial_failures),
        "trials_quarantined": len(trial_failures),
        "examples": len(aggregate_records),
        "captures_excluded": len(excluded_captures),
        "informative_examples": sum(
            record["learner_update_eligible"] is True for record in aggregate_records
        ),
        "dataset_sha256": canonical_sha256(aggregate_records),
        "controller_actions_per_trial": "one_counterfactual_per_usable_candidate",
        "teacher_queries": 0,
        "authority_promoted": False,
        "sealed_test_cases_opened": 0,
        "private_path_fields": 0,
    }


def _frame_targets(value: list[int] | None) -> tuple[int, ...]:
    targets = DEFAULT_FRAME_TARGETS if value is None else tuple(value)
    if (
        len(targets) < 2
        or targets != tuple(sorted(set(targets)))
        or any(type(item) is not int or item < 2_048 for item in targets)  # noqa: E721
    ):
        raise RepeatableBattleExpectedUtilityCollectionError(
            "frame targets must be unique, increasing, and at least 2048"
        )
    return targets


def _capture_pairs(directories: list[Path]) -> tuple[tuple[Path, Path], ...]:
    pairs = []
    for directory in directories:
        if not directory.is_dir():
            raise RepeatableBattleExpectedUtilityCollectionError(
                "capture directory is unavailable"
            )
        for manifest in sorted(directory.glob("*.state.json")):
            state = manifest.with_suffix("")
            if not state.is_file():
                raise RepeatableBattleExpectedUtilityCollectionError(
                    "capture state is unavailable"
                )
            pairs.append((state, manifest))
    if not pairs:
        raise RepeatableBattleExpectedUtilityCollectionError(
            "no battle captures were discovered"
        )
    return tuple(pairs)


def _claim(
    capture: BattleScenarioCapture,
    *,
    capture_ordinal: int,
    frame_target: int,
) -> dict[str, object]:
    return {
        "schema": "pokemon.core.battle.expected-utility-trial-claim.v1",
        "capture_ordinal": capture_ordinal,
        "capture_id": capture.manifest.capture_id,
        "manifest_sha256": capture.manifest_sha256,
        "state_sha256": capture.manifest.state_sha256,
        "frame_target": frame_target,
        "status": "started",
    }


def _quarantined_terminal(
    capture: BattleScenarioCapture,
    *,
    capture_ordinal: int,
    frame_target: int,
    error_type: str,
    reason: str,
) -> dict[str, object]:
    return {
        "schema": "pokemon.core.battle.expected-utility-trial-terminal.v1",
        "capture_ordinal": capture_ordinal,
        "capture_id": capture.manifest.capture_id,
        "manifest_sha256": capture.manifest_sha256,
        "frame_target": frame_target,
        "status": "quarantined",
        "record": None,
        "failure": {
            "capture_id": capture.manifest.capture_id,
            "partition": capture.manifest.partition.value,
            "frame_target": frame_target,
            "error_type": error_type,
            "reason": reason,
        },
    }


def _read_claim(
    path: Path,
    *,
    capture: BattleScenarioCapture,
    capture_ordinal: int,
    frame_target: int,
) -> dict[str, object]:
    value = _read_json(path, subject="trial claim")
    if value != _claim(
        capture,
        capture_ordinal=capture_ordinal,
        frame_target=frame_target,
    ):
        raise RepeatableBattleExpectedUtilityCollectionError("trial claim differs")
    return value


def _read_terminal(
    path: Path,
    *,
    capture: BattleScenarioCapture,
    capture_ordinal: int,
    frame_target: int,
) -> dict[str, object] | None:
    if not path.exists():
        return None
    value = _read_json(path, subject="trial terminal")
    if (
        set(value)
        != {
            "schema",
            "capture_ordinal",
            "capture_id",
            "manifest_sha256",
            "frame_target",
            "status",
            "record",
            "failure",
        }
        or value.get("schema")
        != "pokemon.core.battle.expected-utility-trial-terminal.v1"
        or value.get("capture_ordinal") != capture_ordinal
        or value.get("capture_id") != capture.manifest.capture_id
        or value.get("manifest_sha256") != capture.manifest_sha256
        or value.get("frame_target") != frame_target
        or value.get("status") not in {"complete", "quarantined"}
    ):
        raise RepeatableBattleExpectedUtilityCollectionError("trial terminal differs")
    if value["status"] == "complete":
        record = value["record"]
        if not isinstance(record, dict) or value["failure"] is not None:
            raise RepeatableBattleExpectedUtilityCollectionError(
                "complete trial terminal is invalid"
            )
        example = parse_repeatable_battle_outcome_record(record)
        frames = {
            outcome.pre_attack_frames
            for outcome in example.outcomes
            if outcome is not None
        }
        if (
            record.get("capture_id") != capture.manifest.capture_id
            or record.get("manifest_sha256") != capture.manifest_sha256
            or example.initial_state_sha256 != capture.manifest.state_sha256
            or example.root_lineage_id != capture.manifest.root_lineage_id
            or example.partition is not capture.manifest.partition
            or frames != {frame_target}
        ):
            raise RepeatableBattleExpectedUtilityCollectionError(
                "complete trial binding differs"
            )
    elif value["record"] is not None or not isinstance(value["failure"], dict):
        raise RepeatableBattleExpectedUtilityCollectionError(
            "quarantined trial terminal is invalid"
        )
    return value


def _prepare_journal(path: Path, header: dict[str, object]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    manifest = path / "manifest.json"
    payload = _json_line(header)
    if manifest.exists():
        if manifest.read_bytes() != payload:
            raise RepeatableBattleExpectedUtilityCollectionError(
                "expected-utility journal belongs to different inputs"
            )
        return
    _write_new_atomic(manifest, payload)


def _require_output(path: Path, *, subject: str) -> None:
    if not path.parent.is_dir() or (path.exists() and not path.is_file()):
        raise RepeatableBattleExpectedUtilityCollectionError(
            f"{subject} is unavailable"
        )
    if path.resolve().is_relative_to(PROJECT_ROOT.resolve()):
        raise RepeatableBattleExpectedUtilityCollectionError(
            f"{subject} must remain outside the repository"
        )


def _bounded_reason(error: Exception) -> str:
    reason = str(error) or type(error).__name__
    if len(reason) > 1_024 or "\n" in reason or "\r" in reason:
        return "invalid or oversized runtime failure message"
    return reason


def _read_json(path: Path, *, subject: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text("ascii"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise RepeatableBattleExpectedUtilityCollectionError(
            f"{subject} is invalid"
        ) from None
    if not isinstance(value, dict):
        raise RepeatableBattleExpectedUtilityCollectionError(f"{subject} is invalid")
    return value


def _json_line(value: object) -> bytes:
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
    _write_new_atomic(path, _json_line(value))


def _write_or_verify_atomic(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise RepeatableBattleExpectedUtilityCollectionError(
                "existing final output differs from completed journal"
            )
        return
    _write_new_atomic(path, payload)


def _require_completed_journal_for_existing_outputs(
    args: argparse.Namespace,
    *,
    captures: tuple[BattleScenarioCapture, ...],
    targets: tuple[int, ...],
) -> None:
    if not args.output.exists() and not args.failure_report.exists():
        return
    expected = {
        (
            f"{capture_ordinal:04d}-{frame_target}-"
            f"{canonical_sha256(capture.manifest.capture_id)[:12]}.terminal.json"
        )
        for capture_ordinal, capture in enumerate(captures, start=1)
        for frame_target in targets
    }
    observed = {path.name for path in args.journal_dir.glob("*.terminal.json")}
    if observed != expected:
        raise RepeatableBattleExpectedUtilityCollectionError(
            "existing final output lacks one exact completed journal"
        )


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
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def main() -> int:
    try:
        result = _run(_parser().parse_args())
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        print(f"expected-utility collection failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
