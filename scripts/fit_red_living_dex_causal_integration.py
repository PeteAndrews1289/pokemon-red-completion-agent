#!/usr/bin/env python3
"""Fit and privately byte-reload the one non-authoritative Red integration model.

The command has only a published-source binding and one validated private-root
input.  It cannot accept a ROM, state, development schedule, teacher, gameplay
target, candidate selection, output file, retry switch, or authority flag.
"""

# ruff: noqa: E402 -- pin the project source root before package imports.

from __future__ import annotations

import argparse
import hashlib
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

from pokemon_red_completion.collection_protocol import (
    committed_source_bundle_sha256,
)
from pokemon_red_completion.living_dex_causal_integration_fit import (
    LIVING_DEX_CAUSAL_INTEGRATION_READINESS_RESULT_SHA256,
    LivingDexCausalIntegrationFitError,
    LivingDexCausalIntegrationSource,
    fit_living_dex_causal_integration_from_store,
)
from pokemon_red_completion.private_artifacts import open_private_root

FAILURE_SCHEMA = "pokemon.red.living-dex-causal-integration-fit-failure.v1"
READINESS_RESULT_PATH = (
    PROJECT_ROOT
    / "docs/evidence/red-living-dex-causal-integration-readiness-result-v1-2026-08-30.json"
)
READINESS_PUBLIC_SCHEMA = (
    "pokemon.red.living-dex-causal-integration-readiness-public-result.v1"
)
READINESS_PUBLIC_STATUS = (
    "eight_example_train_only_integration_readiness_passed_non_authoritative_fit_next"
)
READINESS_IMPLEMENTATION_PATH = (
    SRC_ROOT / "pokemon_red_completion/living_dex_causal_integration_readiness.py"
)
READINESS_IMPLEMENTATION_SHA256 = (
    "26ef82122926df816b0ba1a67db3d5a6f40a80ab4b129a0eb3e16955fb8a41d3"
)
GITHUB_REPOSITORY = "PeteAndrews1289/pokemon-red-completion-agent"
GITHUB_WORKFLOW_NAME = "CI"
GITHUB_WORKFLOW_PATH = ".github/workflows/ci.yml"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MAXIMUM_COMMAND_OUTPUT = 2 * 1024 * 1024
_MAXIMUM_READINESS_RESULT = 128 * 1024


class IntegrationFitCommandError(RuntimeError):
    """The command failed at one sanitized stage."""

    def __init__(
        self,
        stage: str,
        *,
        fit_executions: int = 0,
        private_fit_claims: int = 0,
    ) -> None:
        self.stage = stage
        self.fit_executions = fit_executions
        self.private_fit_claims = private_fit_claims
        super().__init__(stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise IntegrationFitCommandError("arguments")


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
        raise IntegrationFitCommandError("source_authentication") from None
    if (
        completed.returncode != 0
        or len(completed.stdout) > _MAXIMUM_COMMAND_OUTPUT
        or len(completed.stderr) > _MAXIMUM_COMMAND_OUTPUT
    ):
        raise IntegrationFitCommandError("source_authentication")
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
        raise IntegrationFitCommandError("source_authentication")
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
        raise IntegrationFitCommandError("source_authentication")
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
        raise IntegrationFitCommandError("source_authentication") from None
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
        raise IntegrationFitCommandError("source_authentication")
    return LivingDexCausalIntegrationSource(
        source_commit=commit,
        source_bundle_sha256=bundle,
        exact_ci_run=run,
        exact_ci_attempt=attempt,
    )


def _authenticate_readiness_proof() -> str:
    try:
        payload = READINESS_RESULT_PATH.read_bytes()
        implementation = READINESS_IMPLEMENTATION_PATH.read_bytes()
    except OSError:
        raise IntegrationFitCommandError("readiness_proof") from None
    digest = hashlib.sha256(payload).hexdigest()
    if (
        not payload
        or len(payload) > _MAXIMUM_READINESS_RESULT
        or digest != LIVING_DEX_CAUSAL_INTEGRATION_READINESS_RESULT_SHA256
        or hashlib.sha256(implementation).hexdigest()
        != READINESS_IMPLEMENTATION_SHA256
    ):
        raise IntegrationFitCommandError("readiness_proof")
    try:
        document = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise IntegrationFitCommandError("readiness_proof") from None
    audit = document.get("audit") if isinstance(document, dict) else None
    if (
        not isinstance(document, dict)
        or document.get("schema") != READINESS_PUBLIC_SCHEMA
        or document.get("status") != READINESS_PUBLIC_STATUS
        or not isinstance(audit, dict)
        or audit.get("authentic_examples") != 8
        or audit.get("train_examples") != 8
        or audit.get("development_examples") != 0
        or audit.get("settled_examples") != 8
        or audit.get("censored_examples") != 0
        or audit.get("integration_fit_allowed") is not True
        or audit.get("reason_codes") != []
    ):
        raise IntegrationFitCommandError("readiness_proof")
    return digest


def main(argv: list[str] | None = None) -> int:
    stage = "arguments"
    fit_executions = 0
    private_fit_claims = 0
    try:
        args = _parser().parse_args(argv)
        stage = "source_authentication"
        source = _authenticate_source(args)
        stage = "readiness_proof"
        readiness_result_sha256 = _authenticate_readiness_proof()
        stage = "private_root_authentication"
        store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
        stage = "non_authoritative_integration_fit"
        result = fit_living_dex_causal_integration_from_store(
            store,
            source=source,
            readiness_result_sha256=readiness_result_sha256,
        )
        print(
            json.dumps(
                result.public_dict(),
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0
    except LivingDexCausalIntegrationFitError as error:
        stage = error.stage
        fit_executions = error.fit_executions
        private_fit_claims = error.private_fit_claims
    except IntegrationFitCommandError as error:
        stage = error.stage
        fit_executions = error.fit_executions
        private_fit_claims = error.private_fit_claims
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
        "gameplay_model_predictions": 0,
        "private_causal_identity_fields": 0,
        "private_fit_claims": private_fit_claims,
        "private_path_fields": 0,
        "root_claims": 0,
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
