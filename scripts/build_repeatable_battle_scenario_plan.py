#!/usr/bin/env python3
"""Inventory private Red sources and freeze a path-free repeatable battle plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.red_repeatable_battle_scenario_source import (  # noqa: E402
    inspect_repeatable_red_battle_source,
)
from pokemon_red_completion.repeatable_battle_scenario_factory import (  # noqa: E402
    RepeatableBattleScenarioCoverage,
    build_repeatable_battle_scenario_plan,
    require_repeatable_battle_scenario_coverage,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402

SOURCE_CATALOG_SCHEMA = "pokemon-private-repeatable-battle-source-catalog-v1"
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class RepeatableBattleScenarioPlanBuildError(RuntimeError):
    """Raised before a private prospective plan can be published."""


@dataclass(frozen=True, slots=True)
class _SourceSpec:
    source_id: str
    source_lineage_id: str
    partition: ScenarioPartition
    state_path: Path
    source_commit: str


@dataclass(frozen=True, slots=True)
class _Catalog:
    seed: int
    training_scenarios: int
    development_scenarios: int
    wait_frame_offsets: tuple[int, ...]
    train_minimum: RepeatableBattleScenarioCoverage
    development_minimum: RepeatableBattleScenarioCoverage
    sources: tuple[_SourceSpec, ...]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-catalog", type=Path, required=True)
    parser.add_argument("--private-plan", type=Path, required=True)
    parser.add_argument("--public-summary", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    catalog_payload = args.source_catalog.read_bytes()
    catalog = _parse_catalog(catalog_payload)
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    observations = []
    for spec in catalog.sources:
        try:
            state_bytes = spec.state_path.read_bytes()
        except OSError:
            raise RepeatableBattleScenarioPlanBuildError(
                "a private source state is unavailable"
            ) from None
        observations.append(
            inspect_repeatable_red_battle_source(
                state_bytes,
                source_id=spec.source_id,
                source_lineage_id=spec.source_lineage_id,
                partition=spec.partition,
                source_commit=spec.source_commit,
                session_factory=lambda: PyBoyAdapter(rom_path),
            )
        )
    plan = build_repeatable_battle_scenario_plan(
        tuple(observations),
        seed=catalog.seed,
        training_scenarios=catalog.training_scenarios,
        development_scenarios=catalog.development_scenarios,
        wait_frame_offsets=catalog.wait_frame_offsets,
    )
    require_repeatable_battle_scenario_coverage(
        plan,
        train_minimum=catalog.train_minimum,
        development_minimum=catalog.development_minimum,
    )
    plan_payload = _canonical_payload(plan.private_dict())
    summary = {
        **plan.public_dict(),
        "source_catalog_sha256": hashlib.sha256(catalog_payload).hexdigest(),
        "source_count": len(catalog.sources),
        "rom_sha256": rom.sha256,
        "minimum_coverage": {
            "train": catalog.train_minimum.public_dict(),
            "development": catalog.development_minimum.public_dict(),
        },
        "inventory_actions": 0,
        "inventory_frames": 0,
    }
    _write_new(args.private_plan, plan_payload, mode=0o600)
    try:
        _write_new(args.public_summary, _canonical_payload(summary), mode=0o644)
    except Exception:
        with suppress(OSError):
            args.private_plan.unlink()
        raise
    return summary


def _parse_catalog(payload: bytes) -> _Catalog:
    try:
        value = json.loads(payload.decode("utf-8"))
        if not isinstance(value, dict) or set(value) != {
            "schema",
            "seed",
            "training_scenarios",
            "development_scenarios",
            "wait_frame_offsets",
            "minimum_coverage",
            "sources",
        }:
            raise RepeatableBattleScenarioPlanBuildError(
                "source catalog fields are invalid"
            )
        if value["schema"] != SOURCE_CATALOG_SCHEMA:
            raise RepeatableBattleScenarioPlanBuildError(
                "source catalog schema is invalid"
            )
        minimum = value["minimum_coverage"]
        if not isinstance(minimum, dict) or set(minimum) != {"train", "development"}:
            raise RepeatableBattleScenarioPlanBuildError(
                "source catalog coverage requirements are invalid"
            )
        rows = value["sources"]
        if not isinstance(rows, list) or not rows:
            raise RepeatableBattleScenarioPlanBuildError(
                "source catalog has no source rows"
            )
        sources = tuple(_parse_source(row) for row in rows)
        source_ids = tuple(item.source_id for item in sources)
        if len(source_ids) != len(set(source_ids)):
            raise RepeatableBattleScenarioPlanBuildError(
                "source catalog identities repeat"
            )
        offsets = value["wait_frame_offsets"]
        if not isinstance(offsets, list):
            raise RepeatableBattleScenarioPlanBuildError(
                "source catalog timing offsets are invalid"
            )
        return _Catalog(
            seed=value["seed"],
            training_scenarios=value["training_scenarios"],
            development_scenarios=value["development_scenarios"],
            wait_frame_offsets=tuple(offsets),
            train_minimum=_parse_coverage(minimum["train"]),
            development_minimum=_parse_coverage(minimum["development"]),
            sources=sources,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        if isinstance(error, RepeatableBattleScenarioPlanBuildError):
            raise
        raise RepeatableBattleScenarioPlanBuildError(
            "source catalog is invalid"
        ) from error


def _parse_source(value: object) -> _SourceSpec:
    if not isinstance(value, dict) or set(value) != {
        "source_id",
        "source_lineage_id",
        "partition",
        "state_path",
        "source_commit",
    }:
        raise RepeatableBattleScenarioPlanBuildError("source row fields are invalid")
    for name in ("source_id", "source_lineage_id"):
        item = value[name]
        if not isinstance(item, str) or _SAFE_ID.fullmatch(item) is None:
            raise RepeatableBattleScenarioPlanBuildError(f"source row {name} is invalid")
    commit = value["source_commit"]
    if not isinstance(commit, str) or _GIT_COMMIT.fullmatch(commit) is None:
        raise RepeatableBattleScenarioPlanBuildError("source row commit is invalid")
    path = value["state_path"]
    if not isinstance(path, str) or not path:
        raise RepeatableBattleScenarioPlanBuildError("source row path is invalid")
    try:
        partition = ScenarioPartition(value["partition"])
    except ValueError:
        raise RepeatableBattleScenarioPlanBuildError(
            "source row partition is invalid"
        ) from None
    if partition not in {ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT}:
        raise RepeatableBattleScenarioPlanBuildError(
            "source row partition must be train or development"
        )
    return _SourceSpec(
        source_id=value["source_id"],
        source_lineage_id=value["source_lineage_id"],
        partition=partition,
        state_path=Path(path),
        source_commit=commit,
    )


def _parse_coverage(value: object) -> RepeatableBattleScenarioCoverage:
    fields = {
        "scenarios",
        "source_lineages",
        "source_states",
        "party_menus",
        "semantic_setups",
        "venues",
        "battle_kinds",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise RepeatableBattleScenarioPlanBuildError(
            "coverage requirement fields are invalid"
        )
    return RepeatableBattleScenarioCoverage(**value)


def _canonical_payload(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")


def _write_new(path: Path, payload: bytes, *, mode: int) -> None:
    if path.resolve().is_relative_to(PROJECT_ROOT.resolve()) and mode == 0o600:
        raise RepeatableBattleScenarioPlanBuildError(
            "private scenario plan must remain outside the repository"
        )
    if not path.parent.is_dir() or path.exists():
        raise RepeatableBattleScenarioPlanBuildError(
            "scenario plan output is unavailable or already exists"
        )
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            mode,
        )
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("output write made no progress")
            offset += written
        os.fsync(descriptor)
    except OSError:
        raise RepeatableBattleScenarioPlanBuildError(
            "scenario plan output could not be published"
        ) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def main() -> int:
    args = _parser().parse_args()
    try:
        summary = _run(args)
    except (RepeatableBattleScenarioPlanBuildError, ValueError) as error:
        print(json.dumps({"status": "failed", "reason": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
