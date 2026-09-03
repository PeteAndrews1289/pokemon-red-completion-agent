#!/usr/bin/env python3
"""Commit Red development predictions without executing a controller action."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_outcome_batch import (  # noqa: E402
    battle_outcome_fixed_heuristic_choice,
    battle_outcome_model_sha256,
)
from pokemon_red_completion.battle_scenario_capture import (  # noqa: E402
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
    prepare_red_battle_outcome_capture,
)
from pokemon_red_completion.repeatable_battle_evaluation import (  # noqa: E402
    load_repeatable_battle_model,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402


class RepeatableBattlePredictionCommitmentError(RuntimeError):
    """Raised when prospective development choices cannot be bound safely."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--updated-model", type=Path, required=True)
    parser.add_argument("--capture-dir", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    _require_private_output(args.output)
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - clean source owns this
        raise AssertionError("published prediction source lacks a commit")

    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    base_model, base_file_sha256 = load_repeatable_battle_model(args.base_model)
    updated_model, updated_file_sha256 = load_repeatable_battle_model(
        args.updated_model
    )
    if base_model.feature_names != updated_model.feature_names:
        raise RepeatableBattlePredictionCommitmentError(
            "base and updated model feature contracts differ"
        )

    captures = tuple(
        open_battle_scenario_capture(state, manifest)
        for state, manifest in _capture_pairs(args.capture_dir)
    )
    if any(
        capture.manifest.partition is not ScenarioPartition.DEVELOPMENT
        for capture in captures
    ):
        raise RepeatableBattlePredictionCommitmentError(
            "prediction commitment accepts development captures only"
        )
    capture_ids = tuple(capture.manifest.capture_id for capture in captures)
    state_ids = tuple(capture.manifest.state_sha256 for capture in captures)
    if len(capture_ids) != len(set(capture_ids)) or len(state_ids) != len(
        set(state_ids)
    ):
        raise RepeatableBattlePredictionCommitmentError(
            "development capture identities must be distinct"
        )

    commitments: list[dict[str, object]] = []
    for ordinal, capture in enumerate(captures, start=1):
        prepared = prepare_red_battle_outcome_capture(
            capture,
            session_factory=lambda: PyBoyAdapter(rom_path),
        )
        features = prepared.features
        commitments.append(
            {
                "ordinal": ordinal,
                "capture_id": capture.manifest.capture_id,
                "manifest_sha256": capture.manifest_sha256,
                "state_sha256": capture.manifest.state_sha256,
                "root_lineage_id": capture.manifest.root_lineage_id,
                "initial_observation_sha256": prepared.initial_observation_sha256,
                "base_candidate_index": base_model.predict(
                    features.candidate_vectors,
                    legal_mask=features.legal_mask,
                    current_pp=features.current_pp,
                ),
                "updated_candidate_index": updated_model.predict(
                    features.candidate_vectors,
                    legal_mask=features.legal_mask,
                    current_pp=features.current_pp,
                ),
                "fixed_heuristic_candidate_index": (
                    battle_outcome_fixed_heuristic_choice(features)
                ),
            }
        )

    report = {
        "schema": "pokemon.core.battle.repeatable-development-predictions.v1",
        "collector_source_commit": source.git_commit,
        "rom_sha256": rom.sha256,
        "base_model_file_sha256": base_file_sha256,
        "base_model_sha256": battle_outcome_model_sha256(base_model),
        "updated_model_file_sha256": updated_file_sha256,
        "updated_model_sha256": battle_outcome_model_sha256(updated_model),
        "capture_count": len(commitments),
        "commitments_sha256": canonical_sha256(commitments),
        "commitments": commitments,
        "development_outcomes_opened": 0,
        "controller_actions": 0,
        "teacher_queries": 0,
        "authority_promoted": False,
        "sealed_evidence": False,
        "private_path_fields": 0,
    }
    _write_new_atomic(
        args.output,
        (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("ascii"),
    )
    return report


def _capture_pairs(directories: list[Path]) -> tuple[tuple[Path, Path], ...]:
    pairs: list[tuple[Path, Path]] = []
    for directory in directories:
        if not directory.is_dir():
            raise RepeatableBattlePredictionCommitmentError(
                "capture directory is unavailable"
            )
        for manifest in sorted(directory.glob("*.state.json")):
            state = manifest.with_suffix("")
            if not state.is_file():
                raise RepeatableBattlePredictionCommitmentError(
                    "capture state is unavailable"
                )
            pairs.append((state, manifest))
    if not pairs:
        raise RepeatableBattlePredictionCommitmentError(
            "no battle captures were discovered"
        )
    return tuple(pairs)


def _require_private_output(path: Path) -> None:
    if path.exists() or not path.parent.is_dir():
        raise RepeatableBattlePredictionCommitmentError(
            "prediction output is unavailable or already exists"
        )
    if path.resolve().is_relative_to(PROJECT_ROOT.resolve()):
        raise RepeatableBattlePredictionCommitmentError(
            "prediction output must remain outside the repository"
        )


def _write_new_atomic(path: Path, payload: bytes) -> None:
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


def main() -> int:
    try:
        result = _run(_parser().parse_args())
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        print(f"repeatable prediction commitment failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
