#!/usr/bin/env python3
"""Inspect the exact five Red development inputs without runtime or gameplay."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Never

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pokemon_red_completion.private_artifacts import (  # noqa: E402
    PrivateArtifactError,
    open_private_root,
)
from pokemon_red_completion.red_living_dex_clustered_development_runner import (  # noqa: E402
    RedLivingDexClusteredDevelopmentRunnerError,
)
from pokemon_red_completion.red_living_dex_development_batch import (  # noqa: E402
    RedLivingDexDevelopmentBatchError,
    inspect_red_living_dex_development_batch_inputs,
)
from pokemon_red_completion.red_living_dex_development_input import (  # noqa: E402
    RED_LIVING_DEX_DEVELOPMENT_INPUT_LABELS,
    RedLivingDexDevelopmentInputError,
    load_red_living_dex_development_batch_assignments,
    source_private_storage_is_separate,
)
from pokemon_red_completion.red_living_dex_development_supply import (  # noqa: E402
    RedLivingDexDevelopmentSupplyError,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (  # noqa: E402
    RedLivingDexSetupEffectMeter,
)

FAILURE_SCHEMA = "pokemon.red.repeatable-development-input-readiness-failure.v1"


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise RedLivingDexDevelopmentInputError("arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument(
        "--development-root",
        action="append",
        required=True,
        metavar="LABEL=STATE",
    )
    return parser


def _parse_roots(values: list[str]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    try:
        for value in values:
            label, raw_path = value.split("=", 1)
            path = Path(raw_path)
            if (
                label not in RED_LIVING_DEX_DEVELOPMENT_INPUT_LABELS
                or label in roots
                or not path.is_absolute()
            ):
                raise ValueError
            roots[label] = path
    except (AttributeError, TypeError, ValueError):
        raise RedLivingDexDevelopmentInputError("arguments") from None
    if set(roots) != set(RED_LIVING_DEX_DEVELOPMENT_INPUT_LABELS):
        raise RedLivingDexDevelopmentInputError("arguments")
    return roots


def main(argv: list[str] | None = None) -> int:
    stage = "arguments"
    meter = RedLivingDexSetupEffectMeter()
    try:
        args = _parser().parse_args(argv)
        roots = _parse_roots(args.development_root)
        stage = "source_private_storage_separation"
        if not source_private_storage_is_separate(PROJECT_ROOT, args.private_root):
            raise RedLivingDexDevelopmentInputError(stage)
        stage = "private_root_authentication"
        store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
        stage = "selected_root_authentication"
        assignments = load_red_living_dex_development_batch_assignments(
            store,
            private_root=args.private_root,
            roots=roots,
        )
        stage = "development_input_readiness"
        receipt = inspect_red_living_dex_development_batch_inputs(
            store,
            assignments=assignments,
            meter=meter,
        )
        if meter.checkpoint() != RedLivingDexSetupEffectMeter().checkpoint():
            raise RedLivingDexDevelopmentInputError("forbidden_effect")
        print(_encoded(receipt.public_dict()))
        return 0
    except RedLivingDexDevelopmentInputError as error:
        stage = error.stage
    except PrivateArtifactError:
        stage = "private_root_authentication"
    except RedLivingDexClusteredDevelopmentRunnerError:
        stage = "development_plan_authentication"
    except RedLivingDexDevelopmentSupplyError:
        stage = "development_model_authentication"
    except RedLivingDexDevelopmentBatchError:
        pass
    except BaseException:
        stage = "unexpected_failure"
    failure = {
        "controller_actions": 0,
        "development_outcomes_opened": 0,
        "emulator_frames": 0,
        "model_fits": 0,
        "model_predictions": 0,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "root_claims": 0,
        "schema": FAILURE_SCHEMA,
        "stage": stage if re.fullmatch(r"[a-z0-9_]+", stage) else "unexpected_failure",
        "status": "failed_closed",
        "teacher_queries": 0,
    }
    print(_encoded(failure))
    return 1


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
