#!/usr/bin/env python3
"""Freeze one authentic Red setup binding catalog without gameplay.

The catalog path and private artifact root remain process-local.  Output is an
aggregate, path-free result.  This command owns no ROM, emulator, controller,
teacher, behavior draw, outcome, model fit, or setup execution.
"""

# ruff: noqa: E402 -- establish the reviewed project import root first.

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Never

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
while str(SRC_ROOT) in sys.path:
    sys.path.remove(str(SRC_ROOT))
sys.path.insert(0, str(SRC_ROOT))

from pokemon_red_completion.private_artifacts import open_private_root
from pokemon_red_completion.red_living_dex_setup_materialization import (
    RedLivingDexSetupMaterializationCheckpoint,
    RedLivingDexSetupMaterializationError,
    materialize_red_living_dex_setup_bindings,
)
from pokemon_red_completion.red_living_dex_setup_source import (
    MAXIMUM_SOURCE_PAYLOAD_BYTES,
    RedLivingDexSetupCatalogSource,
    RedLivingDexSetupSourceError,
)

RESULT_SCHEMA = "pokemon.red.living-dex-setup-binding-freeze-result.v1"


class _ArgumentError(RuntimeError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise _ArgumentError


@dataclass(slots=True)
class _ZeroEffectMeter:
    controller_authority_attempts: int = 0
    controller_actions: int = 0
    emulator_frames: int = 0
    behavior_draws: int = 0
    learner_labels: int = 0
    learner_outcomes: int = 0
    model_predictions: int = 0
    model_fits: int = 0
    root_claims: int = 0
    teacher_queries: int = 0

    def checkpoint(self) -> RedLivingDexSetupMaterializationCheckpoint:
        return RedLivingDexSetupMaterializationCheckpoint(
            controller_authority_attempts=self.controller_authority_attempts,
            controller_actions=self.controller_actions,
            emulator_frames=self.emulator_frames,
            behavior_draws=self.behavior_draws,
            learner_labels=self.learner_labels,
            learner_outcomes=self.learner_outcomes,
            model_predictions=self.model_predictions,
            model_fits=self.model_fits,
            root_claims=self.root_claims,
            teacher_queries=self.teacher_queries,
        )


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--source-catalog", type=Path, required=True)
    parser.add_argument("--expected-source-catalog-sha256", required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    meter = _ZeroEffectMeter()
    stage = "argument_authentication"
    try:
        args = _parser().parse_args(argv)
        reader = _private_catalog_reader(args.source_catalog)
        stage = "private_store_authentication"
        store = open_private_root(
            args.private_root,
            repository_root=PROJECT_ROOT,
        )
        stage = "source_materialization"
        source = RedLivingDexSetupCatalogSource(
            reader,
            args.expected_source_catalog_sha256,
            meter,
        )
        result = materialize_red_living_dex_setup_bindings(
            store,
            source=source,
            effects_meter=meter,
        )
    except _ArgumentError:
        stage = "argument_authentication"
    except (RedLivingDexSetupMaterializationError, RedLivingDexSetupSourceError):
        pass
    except Exception:
        stage = "unexpected_failure"
    else:
        public = result.public_dict()
        public.update(
            {
                "result_schema": RESULT_SCHEMA,
                "status": "complete",
            }
        )
        print(_encoded(public))
        return 0

    print(_encoded(_failure(stage, meter)))
    return 1


def _private_catalog_reader(path: Path):
    if not isinstance(path, Path):
        raise _ArgumentError
    try:
        resolved = path.resolve(strict=True)
        if resolved.is_relative_to(PROJECT_ROOT.resolve()):
            raise _ArgumentError
    except (OSError, RuntimeError):
        raise _ArgumentError from None

    def read() -> bytes:
        descriptor = -1
        try:
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(resolved, flags)
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) & 0o077
                or metadata.st_size <= 0
                or metadata.st_size > MAXIMUM_SOURCE_PAYLOAD_BYTES
            ):
                raise RedLivingDexSetupSourceError(
                    "Red setup source catalog file authentication failed"
                )
            chunks: list[bytes] = []
            remaining = metadata.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 131_072))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            if len(payload) != metadata.st_size:
                raise RedLivingDexSetupSourceError(
                    "Red setup source catalog file authentication failed"
                )
            return payload
        except RedLivingDexSetupSourceError:
            raise
        except OSError:
            raise RedLivingDexSetupSourceError(
                "Red setup source catalog file authentication failed"
            ) from None
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    return read


def _failure(stage: str, meter: _ZeroEffectMeter) -> dict[str, object]:
    checkpoint = meter.checkpoint().private_dict()
    return {
        **checkpoint,
        "actionful_setup_execution_authorized": False,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "result_schema": RESULT_SCHEMA,
        "retry_allowed_only_if_effects_zero": not any(checkpoint.values()),
        "stage": stage,
        "status": "failed_closed",
    }


def _encoded(value: dict[str, object]) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
