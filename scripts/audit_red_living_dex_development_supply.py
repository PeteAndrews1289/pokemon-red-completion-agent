#!/usr/bin/env python3
"""Audit reusable held Red development roots without gameplay or outcomes.

This command authenticates exact published source and successful main-push CI,
then opens only the complete train corpus, its exact shadow model, two frozen
schedule records, and the account-wide claim ledger.  It has no ROM argument,
controller, teacher, outcome reader, scorer, fitter, or claim writer.
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
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_root,
)
from pokemon_red_completion.private_artifacts import open_private_root
from pokemon_red_completion.red_living_dex_development_supply import (
    RED_LIVING_DEX_DEVELOPMENT_SUPPLY_RESULT_SCHEMA,
    RedLivingDexDevelopmentSupplyError,
    audit_red_living_dex_development_supply,
)

FAILURE_SCHEMA = "pokemon.red.living-dex-development-supply-audit-failure.v1"
GITHUB_REPOSITORY = "PeteAndrews1289/pokemon-red-completion-agent"
GITHUB_WORKFLOW_NAME = "CI"
GITHUB_WORKFLOW_PATH = ".github/workflows/ci.yml"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MAXIMUM_COMMAND_OUTPUT = 2 * 1024 * 1024


class DevelopmentSupplyCommandError(RuntimeError):
    """The command failed at one sanitized action-free stage."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise DevelopmentSupplyCommandError("arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--exact-ci-run", type=int, required=True)
    parser.add_argument("--exact-ci-attempt", type=int, required=True)
    parser.add_argument("--expected-model-sha256", required=True)
    parser.add_argument("--expected-model-record-sha256", required=True)
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
        raise DevelopmentSupplyCommandError("source_authentication") from None
    if (
        completed.returncode != 0
        or len(completed.stdout) > _MAXIMUM_COMMAND_OUTPUT
        or len(completed.stderr) > _MAXIMUM_COMMAND_OUTPUT
    ):
        raise DevelopmentSupplyCommandError("source_authentication")
    return completed.stdout


def _authenticate_source(args: argparse.Namespace) -> None:
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
        raise DevelopmentSupplyCommandError("source_authentication")
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
        raise DevelopmentSupplyCommandError("source_authentication")
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
        raise DevelopmentSupplyCommandError("source_authentication") from None
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
        raise DevelopmentSupplyCommandError("source_authentication")


def main(argv: list[str] | None = None) -> int:
    stage = "arguments"
    try:
        args = _parser().parse_args(argv)
        stage = "source_authentication"
        _authenticate_source(args)
        stage = "private_root_authentication"
        store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
        stage = "development_supply_authentication"
        result = audit_red_living_dex_development_supply(
            store,
            claim_registry=fixed_account_claim_registry_root(),
            expected_model_sha256=args.expected_model_sha256,
            expected_model_record_sha256=args.expected_model_record_sha256,
        )
        public = result.public_dict()
        if public.get("schema") != RED_LIVING_DEX_DEVELOPMENT_SUPPLY_RESULT_SCHEMA:
            raise DevelopmentSupplyCommandError("result_schema")
        print(json.dumps(public, allow_nan=False, separators=(",", ":"), sort_keys=True))
        return 0
    except RedLivingDexDevelopmentSupplyError:
        stage = "development_supply_authentication"
    except DevelopmentSupplyCommandError as error:
        stage = error.stage
    except BaseException:
        pass
    failure = {
        "authority_promotions": 0,
        "controller_actions": 0,
        "crystal_accesses": 0,
        "development_examples_read": 0,
        "development_outcomes_opened": 0,
        "emulator_frames": 0,
        "model_fits": 0,
        "model_predictions": 0,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "root_claims": 0,
        "schema": FAILURE_SCHEMA,
        "stage": stage,
        "status": "failed_closed",
        "teacher_queries": 0,
    }
    print(json.dumps(failure, allow_nan=False, separators=(",", ":"), sort_keys=True))
    return 1


if __name__ == "__main__":  # pragma: no cover - script boundary
    raise SystemExit(main())
