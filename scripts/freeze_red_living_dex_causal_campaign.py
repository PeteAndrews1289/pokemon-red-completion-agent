#!/usr/bin/env python3
"""Freeze one Red setup-to-causal-example campaign without opening a ROM.

The command reads one explicitly selected authenticated root, excludes every
declared retired physical root, reopens the immutable provider plan, and
publishes one private campaign commitment.  It has no execution mode, ROM
argument, emulator factory, behavior draw, controller, teacher, learner, or
model capability.
"""

# ruff: noqa: E402 -- establish the reviewed project import root first.

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Never

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
while str(SRC_ROOT) in sys.path:
    sys.path.remove(str(SRC_ROOT))
sys.path.insert(0, str(SRC_ROOT))

from pokemon_red_completion.claim_first_admission import ClaimFirstExecutionIdentity
from pokemon_red_completion.private_artifacts import open_private_root
from pokemon_red_completion.red_living_dex_causal_campaign import (
    freeze_red_living_dex_causal_campaign,
)
from pokemon_red_completion.red_living_dex_claim_first_campaign import (
    RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
)
from pokemon_red_completion.red_living_dex_claim_first_invocation import (
    RedLivingDexCurrentConsumerBinding,
    RedLivingDexFrozenProducerBinding,
    RedLivingDexLoadedProducerSlot,
    authenticate_red_living_dex_current_consumer,
    authenticate_red_living_dex_producer_slot,
)
from pokemon_red_completion.red_living_dex_runtime_contract import (
    RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
    RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
)
from pokemon_red_completion.red_living_dex_setup_admission import (
    authenticate_frozen_red_living_dex_setup_slot,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
)

RESULT_SCHEMA = "pokemon.red.living-dex-causal-campaign-freeze-result.v1"
FAILURE_SCHEMA = "pokemon.red.living-dex-causal-campaign-freeze-failure.v1"

_MAXIMUM_STATE_BYTES = 16 * 1024 * 1024
_MAXIMUM_ENVELOPE_BYTES = 4 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class CausalCampaignFreezeError(RuntimeError):
    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise CausalCampaignFreezeError("argument_authentication")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--exact-ci-run", required=True, type=int)
    parser.add_argument("--exact-ci-attempt", required=True, type=int)
    parser.add_argument("--expected-producer-plan-sha256", required=True)
    parser.add_argument("--expected-producer-private-plan-sha256", required=True)
    parser.add_argument("--expected-producer-manifest-sha256", required=True)
    parser.add_argument("--ordinal", required=True, type=int)
    parser.add_argument("--selected-state", required=True, type=Path)
    parser.add_argument("--selected-envelope", required=True, type=Path)
    parser.add_argument("--expected-selected-physical-root-sha256", required=True)
    parser.add_argument(
        "--retired-physical-root-sha256",
        action="append",
        required=True,
    )
    parser.add_argument("--claim-registry", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    stage = "argument_authentication"
    campaign_committed = False
    try:
        args = _parser().parse_args(argv)
        _require_arguments(args)
        stage = "current_source_authentication"
        _require_current_source(args)
        stage = "private_namespace_authentication"
        store = open_private_root(
            args.private_root,
            repository_root=PROJECT_ROOT,
        )
        state_path = _require_private_regular_path(
            args.selected_state,
            private_root=args.private_root,
        )
        envelope_path = _require_private_regular_path(
            args.selected_envelope,
            private_root=args.private_root,
        )
        if state_path == envelope_path:
            raise CausalCampaignFreezeError("selected_root_authentication")
        producer = RedLivingDexFrozenProducerBinding(
            producer_plan_sha256=args.expected_producer_plan_sha256,
            producer_private_plan_sha256=(
                args.expected_producer_private_plan_sha256
            ),
            producer_manifest_sha256=args.expected_producer_manifest_sha256,
            ordinal=args.ordinal,
        )
        stage = "selected_root_authentication"
        loaded, plan_document = authenticate_red_living_dex_producer_slot(
            producer,
            _selected_loader(
                store,
                producer=producer,
                state_path=state_path,
                envelope_path=envelope_path,
                expected_physical_root_sha256=(
                    args.expected_selected_physical_root_sha256
                ),
            ),
        )
        frozen = authenticate_frozen_red_living_dex_setup_slot(
            plan_document,
            expected_plan_sha256=producer.producer_plan_sha256,
            ordinal=producer.ordinal,
            root=loaded.root,
        )
        outer = ClaimFirstExecutionIdentity(
            source_commit=args.expected_source_commit,
            source_bundle_sha256=args.expected_source_bundle_sha256,
            exact_ci_run=args.exact_ci_run,
            exact_ci_attempt=args.exact_ci_attempt,
            producer_execution_identity_sha256=(
                frozen.producer_execution_identity_sha256
            ),
            producer_plan_sha256=frozen.producer_plan_sha256,
            producer_private_plan_sha256=(
                producer.producer_private_plan_sha256
            ),
            producer_manifest_sha256=producer.producer_manifest_sha256,
            slot_sha256=frozen.slot_sha256,
            recipe_sha256=frozen.recipe_sha256,
            logical_root_sha256=frozen.logical_root_sha256,
            physical_root_sha256=frozen.physical_root_sha256,
            title_adapter_sha256=RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
            runtime_factory_sha256=RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
            runner_sha256=RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
        )
        stage = "campaign_freeze"
        campaign = freeze_red_living_dex_causal_campaign(
            store,
            frozen=frozen,
            outer_execution_identity=outer,
            retired_physical_root_sha256s=tuple(
                args.retired_physical_root_sha256
            ),
            claim_registry=args.claim_registry,
        )
        campaign_committed = True
        stage = "post_freeze_source_authentication"
        try:
            _require_current_source(args)
        except CausalCampaignFreezeError:
            raise CausalCampaignFreezeError(
                "post_freeze_source_authentication"
            ) from None
    except CausalCampaignFreezeError as error:
        stage = error.stage
    except Exception:
        if stage not in {
            "argument_authentication",
            "current_source_authentication",
            "private_namespace_authentication",
            "selected_root_authentication",
            "campaign_freeze",
            "post_freeze_source_authentication",
        }:
            stage = "unexpected_failure"
    else:
        public = campaign.public_dict()
        public.update(
            {
                "current_source_bound": True,
                "exact_ci_identity_bound": True,
                "result_schema": RESULT_SCHEMA,
                "status": "one_action_free_train_campaign_frozen",
            }
        )
        print(_encoded(public))
        return 0

    print(_encoded(_failure(stage, campaign_committed=campaign_committed)))
    return 1


def _require_arguments(args: argparse.Namespace) -> None:
    for value in (
        args.expected_source_bundle_sha256,
        args.expected_producer_plan_sha256,
        args.expected_producer_private_plan_sha256,
        args.expected_producer_manifest_sha256,
        args.expected_selected_physical_root_sha256,
        *args.retired_physical_root_sha256,
    ):
        if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
            raise CausalCampaignFreezeError("argument_authentication")
    if (
        not isinstance(args.expected_source_commit, str)
        or _GIT_COMMIT.fullmatch(args.expected_source_commit) is None
        or type(args.exact_ci_run) is not int  # noqa: E721
        or args.exact_ci_run <= 0
        or type(args.exact_ci_attempt) is not int  # noqa: E721
        or args.exact_ci_attempt <= 0
        or type(args.ordinal) is not int  # noqa: E721
        or not 0 <= args.ordinal < 15
    ):
        raise CausalCampaignFreezeError("argument_authentication")


def _require_current_source(args: argparse.Namespace) -> None:
    try:
        authenticate_red_living_dex_current_consumer(
            PROJECT_ROOT,
            RedLivingDexCurrentConsumerBinding(
                source_commit=args.expected_source_commit,
                source_bundle_sha256=args.expected_source_bundle_sha256,
                exact_ci_run=args.exact_ci_run,
                exact_ci_attempt=args.exact_ci_attempt,
            ),
        )
    except Exception:
        raise CausalCampaignFreezeError("current_source_authentication") from None


def _selected_loader(
    store,  # type: ignore[no-untyped-def]
    *,
    producer: RedLivingDexFrozenProducerBinding,
    state_path: Path,
    envelope_path: Path,
    expected_physical_root_sha256: str,
):  # type: ignore[no-untyped-def]
    def load(ordinal: int) -> RedLivingDexLoadedProducerSlot:
        if ordinal != producer.ordinal:
            raise CausalCampaignFreezeError("selected_root_authentication")
        record = store.find_sealed_record(
            "red-living-dex-provider-plan-v1",
            expected_kind="red-living-dex-provider-plan-v1",
        )
        if record is None:
            raise CausalCampaignFreezeError("selected_root_authentication")
        document = record.read()
        recipe_plan = document.get("recipe_plan")
        if not isinstance(recipe_plan, dict):
            raise CausalCampaignFreezeError("selected_root_authentication")
        recipes = recipe_plan.get("recipes")
        if not isinstance(recipes, list) or not 0 <= ordinal < len(recipes):
            raise CausalCampaignFreezeError("selected_root_authentication")
        recipe = recipes[ordinal]
        if not isinstance(recipe, dict):
            raise CausalCampaignFreezeError("selected_root_authentication")
        logical_root = recipe.get("root_consumption_sha256")
        if not isinstance(logical_root, str) or _SHA256.fullmatch(logical_root) is None:
            raise CausalCampaignFreezeError("selected_root_authentication")
        root = RedLivingDexAuthenticatedSetupRoot(
            root_consumption_sha256=logical_root,
            state_bytes=_read_private_regular(
                state_path,
                maximum_bytes=_MAXIMUM_STATE_BYTES,
            ),
            envelope_bytes=_read_private_regular(
                envelope_path,
                maximum_bytes=_MAXIMUM_ENVELOPE_BYTES,
            ),
        )
        if root.physical_root_sha256 != expected_physical_root_sha256:
            raise CausalCampaignFreezeError("selected_root_authentication")
        return RedLivingDexLoadedProducerSlot(record, root)

    return load


def _require_private_regular_path(path: Path, *, private_root: Path) -> Path:
    try:
        root = private_root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        metadata = path.lstat()
        if (
            not path.is_absolute()
            or path.is_symlink()
            or resolved != path
            or not resolved.is_relative_to(root)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise OSError("private path differs")
        return resolved
    except OSError:
        raise CausalCampaignFreezeError("selected_root_authentication") from None


def _read_private_regular(path: Path, *, maximum_bytes: int) -> bytes:
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
            raise OSError("private file differs")
        payload = os.read(descriptor, opened.st_size + 1)
        finished = os.fstat(descriptor)
        if (
            len(payload) != opened.st_size
            or finished.st_size != opened.st_size
            or finished.st_mtime_ns != opened.st_mtime_ns
            or finished.st_ctime_ns != opened.st_ctime_ns
        ):
            raise OSError("private file changed")
        return payload
    except OSError:
        raise CausalCampaignFreezeError("selected_root_authentication") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _failure(stage: str, *, campaign_committed: bool = False) -> dict[str, object]:
    return {
        "behavior_draws": 0,
        "causal_examples": 0,
        "campaign_commitment_published": campaign_committed,
        "controller_actions": 0,
        "emulator_frames": 0,
        "model_fits": 0,
        "model_predictions": 0,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "provider_executions": 0,
        "result_schema": FAILURE_SCHEMA,
        "retry_allowed": False,
        "root_claims": 0,
        "stage": stage,
        "status": (
            "frozen_postcheck_failed" if campaign_committed else "failed_closed"
        ),
        "teacher_queries": 0,
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
