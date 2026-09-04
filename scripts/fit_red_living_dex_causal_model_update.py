#!/usr/bin/env python3
"""Fit one immutable train-only causal model update from the full Red corpus.

The command authenticates a clean exact-main source and successful GitHub CI
run, opens one private artifact root, and emits only aggregate path-free
telemetry.  It accepts no ROM, development data, candidate filter, gameplay
target, controller, teacher, or authority switch.
"""

# ruff: noqa: E402 -- pin the project source root before package imports.

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Never

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
while str(SRC_ROOT) in sys.path:
    sys.path.remove(str(SRC_ROOT))
sys.path.insert(0, str(SRC_ROOT))

from pokemon_red_completion.collection_protocol import committed_source_bundle_sha256
from pokemon_red_completion.living_dex_causal_integration_fit import (
    LivingDexCausalIntegrationSource,
)
from pokemon_red_completion.living_dex_causal_model_update import (
    LIVING_DEX_CAUSAL_UPDATE_RESULT_SCHEMA,
    LivingDexCausalModelUpdateError,
    fit_living_dex_causal_model_update_from_store,
)
from pokemon_red_completion.private_artifacts import open_private_root

FAILURE_SCHEMA = "pokemon.red.living-dex-causal-model-update-failure.v1"
GITHUB_REPOSITORY = "PeteAndrews1289/pokemon-red-completion-agent"
GITHUB_WORKFLOW_NAME = "CI"
GITHUB_WORKFLOW_PATH = ".github/workflows/ci.yml"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MAXIMUM_COMMAND_OUTPUT = 2 * 1024 * 1024


class CausalModelUpdateCommandError(RuntimeError):
    """The command failed at one sanitized stage."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise CausalModelUpdateCommandError("arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--exact-ci-run", type=int, required=True)
    parser.add_argument("--exact-ci-attempt", type=int, required=True)
    return parser


def _run(command: tuple[str, ...]) -> bytes:
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise CausalModelUpdateCommandError("source_authentication") from None
    if (
        completed.returncode != 0
        or len(completed.stdout) > _MAXIMUM_COMMAND_OUTPUT
        or len(completed.stderr) > _MAXIMUM_COMMAND_OUTPUT
    ):
        raise CausalModelUpdateCommandError("source_authentication")
    return completed.stdout


def _authenticate_source(args: argparse.Namespace) -> LivingDexCausalIntegrationSource:
    commit = args.expected_source_commit
    bundle = args.expected_source_bundle_sha256
    run = args.exact_ci_run
    attempt = args.exact_ci_attempt
    if (
        not isinstance(commit, str)
        or _GIT_COMMIT.fullmatch(commit) is None
        or not isinstance(bundle, str)
        or _SHA256.fullmatch(bundle) is None
        or type(run) is not int  # noqa: E721
        or run <= 0
        or type(attempt) is not int  # noqa: E721
        or attempt <= 0
    ):
        raise CausalModelUpdateCommandError("source_authentication")
    head = _run(("git", "rev-parse", "--verify", "HEAD^{commit}"))
    origin_main = _run(
        ("git", "rev-parse", "--verify", "refs/remotes/origin/main^{commit}")
    )
    dirty = _run(("git", "status", "--porcelain=v1", "--untracked-files=all"))
    if (
        head.decode("ascii", errors="strict").strip() != commit
        or origin_main.decode("ascii", errors="strict").strip() != commit
        or dirty
        or committed_source_bundle_sha256(PROJECT_ROOT, revision=commit) != bundle
    ):
        raise CausalModelUpdateCommandError("source_authentication")
    payload = _run(
        (
            "gh",
            "api",
            f"repos/{GITHUB_REPOSITORY}/actions/runs/{run}/attempts/{attempt}",
        )
    )
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CausalModelUpdateCommandError("source_authentication") from None
    repository = document.get("repository") if isinstance(document, dict) else None
    if (
        not isinstance(document, dict)
        or document.get("id") != run
        or document.get("run_attempt") != attempt
        or document.get("head_sha") != commit
        or document.get("status") != "completed"
        or document.get("conclusion") != "success"
        or document.get("name") != GITHUB_WORKFLOW_NAME
        or document.get("path") != GITHUB_WORKFLOW_PATH
        or document.get("event") != "push"
        or document.get("head_branch") != "main"
        or document.get("html_url")
        != f"https://github.com/{GITHUB_REPOSITORY}/actions/runs/{run}"
        or not isinstance(repository, dict)
        or repository.get("full_name") != GITHUB_REPOSITORY
    ):
        raise CausalModelUpdateCommandError("source_authentication")
    return LivingDexCausalIntegrationSource(
        source_commit=commit,
        source_bundle_sha256=bundle,
        exact_ci_run=run,
        exact_ci_attempt=attempt,
    )


def main(argv: list[str] | None = None) -> int:
    stage = "arguments"
    fit_executions = 0
    private_fit_claims = 0
    try:
        args = _parser().parse_args(argv)
        stage = "source_authentication"
        source = _authenticate_source(args)
        stage = "private_root_authentication"
        store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
        stage = "train_only_model_update"
        result = fit_living_dex_causal_model_update_from_store(store, source=source)
        public = result.public_dict()
        if public.get("schema") != LIVING_DEX_CAUSAL_UPDATE_RESULT_SCHEMA:
            raise CausalModelUpdateCommandError("result_schema")
        print(json.dumps(public, allow_nan=False, separators=(",", ":"), sort_keys=True))
        return 0
    except LivingDexCausalModelUpdateError as error:
        stage = error.stage
        fit_executions = error.fit_executions
        private_fit_claims = error.private_fit_claims
    except CausalModelUpdateCommandError as error:
        stage = error.stage
    except BaseException:
        pass
    failure = {
        "authority_promotions": 0,
        "controller_actions": 0,
        "counterfactual_targets": 0,
        "crystal_accesses": 0,
        "development_examples_read": 0,
        "emulator_frames": 0,
        "fit_executions": fit_executions,
        "model_predictions": 0,
        "private_identity_fields": 0,
        "private_fit_claims": private_fit_claims,
        "private_path_fields": 0,
        "schema": FAILURE_SCHEMA,
        "stage": stage,
        "status": "failed_closed",
        "teacher_queries": 0,
        "unselected_action_targets": 0,
    }
    print(json.dumps(failure, allow_nan=False, separators=(",", ":"), sort_keys=True))
    return 1


if __name__ == "__main__":  # pragma: no cover - script boundary
    raise SystemExit(main())
