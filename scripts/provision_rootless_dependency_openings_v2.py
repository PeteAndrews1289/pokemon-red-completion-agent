#!/usr/bin/env python3
"""Preflight or provision one write-once fresh V2 dependency opening roster."""

# ruff: noqa: E402 -- script-local manifest helpers precede package imports.

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from pathlib import Path
from typing import Never

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

from freeze_rootless_execution_manifest import _current_public_bindings
from public_execution_manifest import read_public_manifest
from rootless_execution_manifest import (
    authenticate_rootless_execution_manifest,
    rootless_execution_invocation,
)

from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    read_root_claim,
    root_claim_is_available,
    write_root_claim,
)
from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    ROOTLESS_DEPENDENCY_EVALUATION_LANE_V2,
    RootlessDependencyEvaluationDesignV2,
    rootless_dependency_evaluation_blueprint_v2,
)
from pokemon_red_completion.living_dex_dependency_provision_v2 import (
    ROOTLESS_DEPENDENCY_V2_PROVISION_PLAN_ID,
    ROOTLESS_DEPENDENCY_V2_PROVISION_PLAN_KIND,
    provision_v2_development_commitments,
)
from pokemon_red_completion.private_artifacts import (
    PRIVATE_ROOT_SENTINEL,
    PrivateArtifactRoot,
    open_private_root,
)
from pokemon_red_completion.provenance import canonical_sha256

RUNNER_RELATIVE = "scripts/provision_rootless_dependency_openings_v2.py"
DEPENDENCIES = (
    "design_core=src/pokemon_red_completion/living_dex_dependency_evaluation_v2.py",
    "manifest_core=scripts/rootless_execution_manifest.py",
    "private_store=src/pokemon_red_completion/private_artifacts.py",
    "provision_core=src/pokemon_red_completion/living_dex_dependency_provision_v2.py",
)


class ProvisionRootlessDependencyV2Error(RuntimeError):
    """The public gate or one-shot provisioning boundary failed closed."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise ProvisionRootlessDependencyV2Error("arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--mode", choices=("preflight", "provision"), required=True)
    parser.add_argument("--execution-manifest", type=Path, required=True)
    parser.add_argument("--expected-execution-manifest-sha256", required=True)
    parser.add_argument("--design-qualification-sha256", required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    stage = "public_manifest_authentication"
    try:
        args = _parser().parse_args(argv)
        public_bindings = _current_public_bindings(
            lane_id=ROOTLESS_DEPENDENCY_EVALUATION_LANE_V2,
            runner=RUNNER_RELATIVE,
            dependencies=list(DEPENDENCIES),
        )
        blueprint_sha256 = canonical_sha256(rootless_dependency_evaluation_blueprint_v2())
        semantic_bindings = {
            "design_blueprint_sha256": blueprint_sha256,
            "design_qualification_sha256": _sha(
                args.design_qualification_sha256,
                "design qualification",
            ),
        }
        invocation = rootless_execution_invocation(
            lane_id=ROOTLESS_DEPENDENCY_EVALUATION_LANE_V2,
            operation="provision",
            semantic_bindings=semantic_bindings,
            public_bindings=public_bindings,
            private_input_roles=("claim_registry", "private_artifact_root"),
        )
        manifest_payload = read_public_manifest(
            args.execution_manifest,
            repository_root=PROJECT_ROOT,
        )
        authenticate_rootless_execution_manifest(
            manifest_payload,
            expected_manifest_sha256=args.expected_execution_manifest_sha256,
            invocation=invocation,
            current_public_bindings=public_bindings,
        )
        manifest_sha256 = hashlib.sha256(manifest_payload).hexdigest()
        provision_claim_sha256 = canonical_sha256(
            {
                "schema": "pokemon.core.rootless-dependency-provision-claim.v2",
                "lane_id": ROOTLESS_DEPENDENCY_EVALUATION_LANE_V2,
                **semantic_bindings,
                "replacement_allowed": False,
            }
        )
        stage = "private_store_authentication"
        store, private_root_identity_sha256 = _open_bound_private_root(args.private_root)
        execution_identity_sha256 = canonical_sha256(
            {
                "schema": "pokemon.core.rootless-dependency-provision-execution.v2",
                "provision_claim_sha256": provision_claim_sha256,
                "execution_manifest_sha256": manifest_sha256,
                "source_commit": public_bindings["source_commit"],
                "runner_sha256": public_bindings["runner_sha256"],
                "private_root_identity_sha256": private_root_identity_sha256,
            }
        )
        stage = "provision_claim"
        registry = open_fixed_account_claim_registry()
        with fixed_account_claim_registry_lease(
            registry,
            exclusive=args.mode == "provision",
        ):
            available = root_claim_is_available(registry, provision_claim_sha256)
            local_plan = store.inspect_sealed_record_metadata(
                ROOTLESS_DEPENDENCY_V2_PROVISION_PLAN_ID,
                expected_kind=ROOTLESS_DEPENDENCY_V2_PROVISION_PLAN_KIND,
            )
            if args.mode == "preflight":
                if not available or local_plan is not None:
                    raise ProvisionRootlessDependencyV2Error("provision_claim")
                result = {
                    "schema": "pokemon.core.rootless-dependency-provision-preflight.v2",
                    "status": "ready_identity_unclaimed",
                    "execution_manifest_sha256": manifest_sha256,
                    "provision_claim_sha256": provision_claim_sha256,
                    "execution_identity_sha256": execution_identity_sha256,
                    "development_openings_provisioned": 0,
                    "development_payloads_opened": 0,
                    "model_fits": 0,
                    "comparisons": 0,
                }
            else:
                if available:
                    if local_plan is not None:
                        raise ProvisionRootlessDependencyV2Error("provision_claim")
                    write_root_claim(
                        registry,
                        root_consumption_sha256=provision_claim_sha256,
                        execution_identity_sha256=execution_identity_sha256,
                        source_commit=public_bindings["source_commit"],
                        runner_sha256=public_bindings["runner_sha256"],
                    )
                else:
                    expected = {
                        "schema": "pokemon.red.fresh-composition-root-claim.v1",
                        "root_consumption_sha256": provision_claim_sha256,
                        "execution_identity_sha256": execution_identity_sha256,
                        "source_commit": public_bindings["source_commit"],
                        "runner_sha256": public_bindings["runner_sha256"],
                    }
                    if read_root_claim(registry, provision_claim_sha256) != expected:
                        raise ProvisionRootlessDependencyV2Error("provision_claim")
                stage = "private_provision"
                provisioned = provision_v2_development_commitments(store)
                design = RootlessDependencyEvaluationDesignV2(provisioned.roster)
                result = {
                    "schema": "pokemon.core.rootless-dependency-provision-result.v2",
                    "status": "four_openings_provisioned_once",
                    "execution_manifest_sha256": manifest_sha256,
                    "provision_claim_sha256": provision_claim_sha256,
                    "execution_identity_sha256": execution_identity_sha256,
                    "design": design.public_dict(),
                    "design_sha256": design.design_sha256,
                    "development_roster_sha256": provisioned.roster.roster_sha256,
                    "development_openings_provisioned": 4,
                    "development_payloads_disclosed_publicly": 0,
                    "model_fits": 0,
                    "comparisons": 0,
                }
        print(json.dumps({**result, "private_path_fields": 0}, sort_keys=True))
        return 0
    except Exception:
        print(
            json.dumps(
                {
                    "schema": "pokemon.core.rootless-dependency-provision-failure.v2",
                    "status": "failed_closed",
                    "failure_stage": stage,
                    "effects": "not_attested",
                    "private_path_fields": 0,
                },
                sort_keys=True,
            )
        )
        return 1


def _sha(value: object, subject: str) -> str:
    del subject
    if not isinstance(value, str) or len(value) != 64:
        raise ProvisionRootlessDependencyV2Error("public_manifest_authentication")
    try:
        int(value, 16)
    except ValueError:
        raise ProvisionRootlessDependencyV2Error("public_manifest_authentication") from None
    return value


def _open_bound_private_root(path: Path) -> tuple[PrivateArtifactRoot, str]:
    """Open one exact private store and derive a non-public resume binding."""

    try:
        resolved = path.resolve(strict=True)
        before = path.lstat()
        store = open_private_root(path, repository_root=PROJECT_ROOT)
        sentinel = resolved / PRIVATE_ROOT_SENTINEL
        sentinel_before = sentinel.lstat()
        sentinel_payload = sentinel.read_bytes()
        sentinel_after = sentinel.lstat()
        after = resolved.lstat()
    except (OSError, RuntimeError):
        raise ProvisionRootlessDependencyV2Error("private_store_authentication") from None
    if (
        path.is_symlink()
        or not stat.S_ISDIR(before.st_mode)
        or not stat.S_ISDIR(after.st_mode)
        or before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or not stat.S_ISREG(sentinel_before.st_mode)
        or sentinel_before.st_dev != sentinel_after.st_dev
        or sentinel_before.st_ino != sentinel_after.st_ino
        or sentinel_before.st_size != sentinel_after.st_size
    ):
        raise ProvisionRootlessDependencyV2Error("private_store_authentication")
    return store, canonical_sha256(
        {
            "schema": "pokemon.core.rootless-dependency-private-store-binding.v2",
            "device": before.st_dev,
            "inode": before.st_ino,
            "resolved_path": str(resolved),
            "sentinel_sha256": hashlib.sha256(sentinel_payload).hexdigest(),
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
