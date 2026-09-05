#!/usr/bin/env python3
"""Authenticate the exact five-root Red development batch without gameplay.

This command is deliberately separate from the historically qualified train
consumer.  It admits exactly two preserved historical development rows and the
three frozen supplement rows, authenticates the train-only model record, and
returns an aggregate receipt.  It has no ROM, controller, prediction, claim,
teacher, outcome, or fitting interface.
"""

# ruff: noqa: E402 -- pin the project source root before package imports.

from __future__ import annotations

import argparse
import json
import os
import re
import stat
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
from pokemon_red_completion.private_artifacts import PRIVATE_ROOT_SENTINEL, open_private_root
from pokemon_red_completion.red_living_dex_causal_invocation import (
    RedLivingDexCausalInvocationError,
    bind_red_living_dex_authenticated_consumer,
)
from pokemon_red_completion.red_living_dex_claim_first_invocation import (
    RedLivingDexCurrentConsumerBinding,
)
from pokemon_red_completion.red_living_dex_clustered_development_runner import (
    RedLivingDexClusteredDevelopmentRunnerError,
    load_red_living_dex_development_selection,
)
from pokemon_red_completion.red_living_dex_clustered_train_runner import (
    FROZEN_RED_LIVING_DEX_CLUSTERED_TRAIN_PLAN,
)
from pokemon_red_completion.red_living_dex_development_batch import (
    RED_LIVING_DEX_DEVELOPMENT_BATCH_PREFLIGHT_SCHEMA,
    RedLivingDexDevelopmentBatchAssignment,
    RedLivingDexDevelopmentBatchError,
    preflight_red_living_dex_development_batch,
)
from pokemon_red_completion.red_living_dex_development_supplement_reader import (
    FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT,
)
from pokemon_red_completion.red_living_dex_development_supply import (
    RedLivingDexDevelopmentSupplyError,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
    RedLivingDexSetupEffectMeter,
)

FAILURE_SCHEMA = "pokemon.red.living-dex-development-batch-preflight-failure.v1"
GITHUB_REPOSITORY = "PeteAndrews1289/pokemon-red-completion-agent"
GITHUB_WORKFLOW_NAME = "CI"
GITHUB_WORKFLOW_PATH = ".github/workflows/ci.yml"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MAXIMUM_COMMAND_OUTPUT = 2 * 1024 * 1024
_MAXIMUM_STATE_BYTES = 16 * 1024 * 1024
_MAXIMUM_ENVELOPE_BYTES = 4 * 1024 * 1024
_CASES = {
    "historical-10": (FROZEN_RED_LIVING_DEX_CLUSTERED_TRAIN_PLAN, 10),
    "historical-11": (FROZEN_RED_LIVING_DEX_CLUSTERED_TRAIN_PLAN, 11),
    "supplement-0": (FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT, 0),
    "supplement-1": (FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT, 1),
    "supplement-2": (FROZEN_RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT, 2),
}


class DevelopmentBatchCommandError(RuntimeError):
    """The command failed at one sanitized, action-free stage."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise DevelopmentBatchCommandError("arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--exact-ci-run", required=True, type=int)
    parser.add_argument("--exact-ci-attempt", required=True, type=int)
    parser.add_argument(
        "--development-root",
        action="append",
        required=True,
        metavar="LABEL=STATE",
    )
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
        raise DevelopmentBatchCommandError("source_authentication") from None
    if (
        completed.returncode != 0
        or len(completed.stdout) > _MAXIMUM_COMMAND_OUTPUT
        or len(completed.stderr) > _MAXIMUM_COMMAND_OUTPUT
    ):
        raise DevelopmentBatchCommandError("source_authentication")
    return completed.stdout


def _authenticate_source(args: argparse.Namespace) -> tuple[str, str, int, int]:
    identity = (
        args.expected_source_commit,
        args.expected_source_bundle_sha256,
        args.exact_ci_run,
        args.exact_ci_attempt,
    )
    commit, bundle, run, attempt = identity
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
        raise DevelopmentBatchCommandError("source_authentication")
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
        raise DevelopmentBatchCommandError("source_authentication")
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
        raise DevelopmentBatchCommandError("source_authentication") from None
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
        raise DevelopmentBatchCommandError("source_authentication")
    return identity


def _parse_roots(values: list[str]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    try:
        for value in values:
            label, raw_path = value.split("=", 1)
            path = Path(raw_path)
            if label not in _CASES or label in roots or not path.is_absolute():
                raise ValueError
            roots[label] = path
    except (AttributeError, TypeError, ValueError):
        raise DevelopmentBatchCommandError("arguments") from None
    if set(roots) != set(_CASES):
        raise DevelopmentBatchCommandError("arguments")
    return roots


def _private_regular(path: Path, *, private_root: Path) -> Path:
    try:
        root = private_root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        metadata = path.lstat()
        if (
            path.is_symlink()
            or resolved != path
            or not resolved.is_relative_to(root)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise OSError
        ancestor = resolved.parent
        while ancestor != root:
            if ancestor == ancestor.parent or not ancestor.is_relative_to(root):
                raise OSError
            if os.path.lexists(ancestor / PRIVATE_ROOT_SENTINEL):
                raise OSError
            ancestor = ancestor.parent
        return resolved
    except OSError:
        raise DevelopmentBatchCommandError("selected_root_authentication") from None


def _read_private(path: Path, *, maximum_bytes: int) -> bytes:
    descriptor = -1
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        named = path.lstat()
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            named.st_dev != opened.st_dev
            or named.st_ino != opened.st_ino
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != os.getuid()
            or stat.S_IMODE(opened.st_mode) & 0o077
            or not 0 < opened.st_size <= maximum_bytes
        ):
            raise OSError
        payload = os.read(descriptor, opened.st_size + 1)
        finished = os.fstat(descriptor)
        if (
            len(payload) != opened.st_size
            or finished.st_size != opened.st_size
            or finished.st_mtime_ns != opened.st_mtime_ns
            or finished.st_ctime_ns != opened.st_ctime_ns
        ):
            raise OSError
        return payload
    except OSError:
        raise DevelopmentBatchCommandError("selected_root_authentication") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _assignments(store, *, private_root: Path, roots: dict[str, Path]):  # type: ignore[no-untyped-def]
    assignments: list[RedLivingDexDevelopmentBatchAssignment] = []
    for label, (binding, ordinal) in _CASES.items():
        selection, _document = load_red_living_dex_development_selection(
            store, ordinal, binding=binding
        )
        state_path = _private_regular(roots[label], private_root=private_root)
        envelope_path = _private_regular(
            Path(f"{state_path}.json"), private_root=private_root
        )
        root = RedLivingDexAuthenticatedSetupRoot(
            root_consumption_sha256=selection.logical_root_sha256,
            state_bytes=_read_private(state_path, maximum_bytes=_MAXIMUM_STATE_BYTES),
            envelope_bytes=_read_private(
                envelope_path, maximum_bytes=_MAXIMUM_ENVELOPE_BYTES
            ),
        )
        if (
            root.physical_root_sha256 != selection.physical_root_sha256
            or root.state_sha256 != selection.root_state_sha256
            or root.envelope_sha256 != selection.root_envelope_sha256
        ):
            raise DevelopmentBatchCommandError("selected_root_authentication")
        assignments.append(RedLivingDexDevelopmentBatchAssignment(binding, ordinal, root))
    return tuple(assignments)


def main(argv: list[str] | None = None) -> int:
    stage = "arguments"
    meter = RedLivingDexSetupEffectMeter()
    try:
        args = _parser().parse_args(argv)
        roots = _parse_roots(args.development_root)
        stage = "source_authentication"
        identity = _authenticate_source(args)
        consumer = bind_red_living_dex_authenticated_consumer(
            RedLivingDexCurrentConsumerBinding(
                source_commit=identity[0],
                source_bundle_sha256=identity[1],
                exact_ci_run=identity[2],
                exact_ci_attempt=identity[3],
            ),
            bootstrap_identity=identity,
        )
        stage = "private_root_authentication"
        store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
        stage = "selected_root_authentication"
        assignments = _assignments(store, private_root=args.private_root, roots=roots)
        stage = "development_batch_preflight"
        receipt = preflight_red_living_dex_development_batch(
            PROJECT_ROOT,
            store,
            consumer=consumer,
            assignments=assignments,
            meter=meter,
        )
        if meter.checkpoint() != RedLivingDexSetupEffectMeter().checkpoint():
            raise DevelopmentBatchCommandError("forbidden_effect")
        public = receipt.public_dict()
        if public.get("schema") != RED_LIVING_DEX_DEVELOPMENT_BATCH_PREFLIGHT_SCHEMA:
            raise DevelopmentBatchCommandError("result_schema")
        print(json.dumps(public, allow_nan=False, separators=(",", ":"), sort_keys=True))
        return 0
    except DevelopmentBatchCommandError as error:
        stage = error.stage
    except (
        RedLivingDexCausalInvocationError,
        RedLivingDexClusteredDevelopmentRunnerError,
        RedLivingDexDevelopmentBatchError,
        RedLivingDexDevelopmentSupplyError,
    ):
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
        "stage": stage,
        "status": "failed_closed",
        "teacher_queries": 0,
    }
    print(json.dumps(failure, allow_nan=False, separators=(",", ":"), sort_keys=True))
    return 1


if __name__ == "__main__":  # pragma: no cover - script boundary
    raise SystemExit(main())
