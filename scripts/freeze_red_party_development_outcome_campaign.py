#!/usr/bin/env python3
"""Freeze the exact Red 14-question / 55-trial campaign outside Git."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.party_development_frozen_catalog import (  # noqa: E402
    PartyDevelopmentFrozenCatalog,
)
from pokemon_red_completion.party_development_outcome_campaign import (  # noqa: E402
    RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_COUNT,
    PartyDevelopmentOutcomeCampaignPlan,
    PartyDevelopmentOutcomeCampaignPredecessor,
    PartyDevelopmentOutcomeInheritedTerminal,
    freeze_party_development_outcome_campaign,
)
from pokemon_red_completion.party_development_outcome_lineage import (  # noqa: E402
    inspect_predecessor_campaign,
)
from pokemon_red_completion.private_artifacts import (  # noqa: E402
    PrivateArtifactRoot,
    open_private_root,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)

_MAX_JSON_BYTES = 8 * 1024 * 1024
_GITHUB_REPOSITORY = "PeteAndrews1289/pokemon-red-completion-agent"
_CI_WORKFLOW_NAME = "CI"
_CI_RUN_JSON_FIELDS = "attempt,conclusion,databaseId,event,headSha,status,url,workflowName"
_RUNNER = PROJECT_ROOT / "scripts" / "run_red_party_development_outcome_campaign.py"
_AUDIT_ACCEPTANCE_KEYS = frozenset(
    {
        "all_candidate_menus_reconstructed",
        "all_capture_envelope_joins_reconstructed",
        "all_reservation_joins_reconstructed",
        "all_root_lineages_reconstructed",
        "all_source_profile_joins_reconstructed",
        "committed_catalog_source_reproduced",
        "input_files_unchanged",
        "path_and_target_scan_clean",
        "rom_adjacent_artifacts_unchanged",
    }
)
_AUDIT_PROTECTED_COUNT_KEYS = frozenset(
    {
        "answers_selected",
        "controller_actions",
        "crystal_cases_opened",
        "model_predictions",
        "model_updates",
        "outcomes_opened",
        "sealed_red_cases_opened",
        "teacher_queries",
    }
)


class RedPartyDevelopmentOutcomeFreezeError(RuntimeError):
    """Raised before a prospective campaign can misstate its provenance."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-catalog", type=Path, required=True)
    parser.add_argument("--frozen-catalog-file-sha256", required=True)
    parser.add_argument("--input-audit-receipt", type=Path, required=True)
    parser.add_argument("--input-audit-receipt-file-sha256", required=True)
    parser.add_argument("--predecessor-campaign-plan", type=Path, default=None)
    parser.add_argument(
        "--predecessor-campaign-plan-file-sha256",
        default=None,
    )
    parser.add_argument("--private-artifact-root", type=Path, default=None)
    parser.add_argument("--exact-ci-run", type=int, required=True)
    parser.add_argument("--exact-ci-attempt", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _require_external(path: Path, *, subject: str) -> Path:
    resolved = path.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise RedPartyDevelopmentOutcomeFreezeError(
            f"private {subject} must remain outside the repository"
        )
    return resolved


def _load_private_json(
    path: Path,
    *,
    expected_sha256: str,
    subject: str,
    external: bool = True,
) -> tuple[Mapping[str, object], bytes]:
    resolved = (
        _require_external(path, subject=subject) if external else path.resolve()
    )
    metadata = resolved.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise RedPartyDevelopmentOutcomeFreezeError(
            f"private {subject} must be a regular file"
        )
    payload = resolved.read_bytes()
    if (
        not payload
        or len(payload) > _MAX_JSON_BYTES
        or hashlib.sha256(payload).hexdigest() != expected_sha256
    ):
        raise RedPartyDevelopmentOutcomeFreezeError(
            f"private {subject} file digest or size differs"
        )
    try:
        value = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise RedPartyDevelopmentOutcomeFreezeError(
            f"private {subject} is not valid ASCII JSON"
        ) from error
    if not isinstance(value, Mapping):
        raise RedPartyDevelopmentOutcomeFreezeError(
            f"private {subject} is not an object"
        )
    return value, payload


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON object key")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> object:
    del value
    raise ValueError("non-finite JSON number")


def _require_exact_green_ci_run(
    exact_ci_run: int,
    exact_ci_attempt: int,
    *,
    source_commit: str,
) -> None:
    if (
        type(exact_ci_run) is not int  # noqa: E721
        or exact_ci_run <= 0
        or type(exact_ci_attempt) is not int  # noqa: E721
        or exact_ci_attempt <= 0
        or not isinstance(source_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
    ):
        raise RedPartyDevelopmentOutcomeFreezeError(
            "campaign freeze CI identity is invalid"
        )
    command = (
        "gh",
        "run",
        "view",
        str(exact_ci_run),
        "--repo",
        _GITHUB_REPOSITORY,
        "--json",
        _CI_RUN_JSON_FIELDS,
    )
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env={**os.environ, "GH_PROMPT_DISABLED": "1"},
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RedPartyDevelopmentOutcomeFreezeError(
            "campaign freeze could not authenticate exact CI"
        ) from error
    if completed.returncode != 0:
        raise RedPartyDevelopmentOutcomeFreezeError(
            "campaign freeze could not authenticate exact CI"
        )
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RedPartyDevelopmentOutcomeFreezeError(
            "campaign freeze CI evidence is invalid"
        ) from error
    expected_url = f"https://github.com/{_GITHUB_REPOSITORY}/actions/runs/{exact_ci_run}"
    if (
        not isinstance(document, Mapping)
        or document.get("databaseId") != exact_ci_run
        or document.get("headSha") != source_commit
        or document.get("status") != "completed"
        or document.get("conclusion") != "success"
        or document.get("workflowName") != _CI_WORKFLOW_NAME
        or document.get("event") != "pull_request"
        or document.get("url") != expected_url
        or document.get("attempt") != exact_ci_attempt
    ):
        raise RedPartyDevelopmentOutcomeFreezeError(
            "campaign freeze CI is not the exact successful source-bound run"
        )


def _validate_input_audit(
    document: Mapping[str, object],
    *,
    catalog: PartyDevelopmentFrozenCatalog,
    catalog_file_sha256: str,
) -> None:
    catalog_receipt = document.get("catalog")
    source_receipt = document.get("catalog_source")
    acceptance = document.get("acceptance")
    protected = document.get("protected_access")
    if (
        document.get("schema")
        != "pokemon.red.party-development-frozen-input-catalog-v1-audit.v1"
        or document.get("status") != "input_integrity_verified_outcomes_closed"
        or not isinstance(catalog_receipt, Mapping)
        or catalog_receipt.get("catalog_file_sha256") != catalog_file_sha256
        or catalog_receipt.get("catalog_sha256") != catalog.catalog_sha256
        or catalog_receipt.get("prospective_catalog_sha256")
        != catalog.prospective_catalog_sha256
        or catalog_receipt.get("question_count") != 14
        or catalog_receipt.get("candidate_row_count")
        != RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_COUNT
        or not isinstance(source_receipt, Mapping)
        or source_receipt.get("source_commit") != catalog.source_commit
        or source_receipt.get("source_bundle_sha256")
        != catalog.source_bundle_sha256
        or not isinstance(acceptance, Mapping)
        or set(acceptance) != _AUDIT_ACCEPTANCE_KEYS
        or any(acceptance.get(key) is not True for key in _AUDIT_ACCEPTANCE_KEYS)
        or not isinstance(protected, Mapping)
        or set(protected)
        != _AUDIT_PROTECTED_COUNT_KEYS | {"authority_promoted"}
        or any(
            type(protected.get(key)) is not int  # noqa: E721
            or protected.get(key) != 0
            for key in _AUDIT_PROTECTED_COUNT_KEYS
        )
        or protected.get("authority_promoted") is not False
    ):
        raise RedPartyDevelopmentOutcomeFreezeError(
            "campaign freeze input-audit receipt does not verify its catalog"
        )


def _write_exclusive(path: Path, payload: bytes) -> None:
    resolved = _require_external(path, subject="campaign-plan output")
    parent = resolved.parent
    metadata = parent.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise RedPartyDevelopmentOutcomeFreezeError(
            "campaign-plan output directory is invalid"
        )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(resolved, flags, 0o600)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        parent_descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    except FileExistsError:
        raise RedPartyDevelopmentOutcomeFreezeError(
            "campaign-plan output already exists; refusing to replace it"
        ) from None
    except OSError as error:
        raise RedPartyDevelopmentOutcomeFreezeError(
            "unable to publish the private campaign plan"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _require_protected_inputs_unchanged(
    protected_files: Mapping[Path, str],
) -> None:
    try:
        observed = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in protected_files
        }
    except OSError as error:
        raise RedPartyDevelopmentOutcomeFreezeError(
            "campaign freeze could not recheck a protected input"
        ) from error
    if observed != protected_files:
        raise RedPartyDevelopmentOutcomeFreezeError(
            "campaign freeze changed or raced a protected input"
        )


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:
        raise AssertionError("published campaign freeze lost its source commit")
    source_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    _require_exact_green_ci_run(
        args.exact_ci_run,
        args.exact_ci_attempt,
        source_commit=source.git_commit,
    )
    catalog_document, catalog_payload = _load_private_json(
        args.frozen_catalog,
        expected_sha256=args.frozen_catalog_file_sha256,
        subject="frozen catalog",
    )
    catalog = PartyDevelopmentFrozenCatalog.from_private_dict(catalog_document)
    audit_document, audit_payload = _load_private_json(
        args.input_audit_receipt,
        expected_sha256=args.input_audit_receipt_file_sha256,
        subject="input-audit receipt",
        external=False,
    )
    _validate_input_audit(
        audit_document,
        catalog=catalog,
        catalog_file_sha256=args.frozen_catalog_file_sha256,
    )
    predecessor_requested = any(
        value is not None
        for value in (
            args.predecessor_campaign_plan,
            args.predecessor_campaign_plan_file_sha256,
            args.private_artifact_root,
        )
    )
    predecessor_plan: PartyDevelopmentOutcomeCampaignPlan | None = None
    predecessor: PartyDevelopmentOutcomeCampaignPredecessor | None = None
    inherited_terminals: tuple[PartyDevelopmentOutcomeInheritedTerminal, ...] = ()
    predecessor_path: Path | None = None
    lineage_store: PrivateArtifactRoot | None = None
    if predecessor_requested:
        if (
            not isinstance(args.predecessor_campaign_plan, Path)
            or not isinstance(
                args.predecessor_campaign_plan_file_sha256, str
            )
            or re.fullmatch(
                r"[0-9a-f]{64}",
                args.predecessor_campaign_plan_file_sha256,
            )
            is None
            or not isinstance(args.private_artifact_root, Path)
        ):
            raise RedPartyDevelopmentOutcomeFreezeError(
                "successor freeze needs the exact predecessor plan and private root"
            )
        predecessor_path = _require_external(
            args.predecessor_campaign_plan,
            subject="predecessor campaign plan",
        )
        predecessor_document, _ = _load_private_json(
            predecessor_path,
            expected_sha256=args.predecessor_campaign_plan_file_sha256,
            subject="predecessor campaign plan",
        )
        predecessor_plan = PartyDevelopmentOutcomeCampaignPlan.from_private_dict(
            predecessor_document
        )
        if (
            predecessor_plan.frozen_catalog_file_sha256
            != args.frozen_catalog_file_sha256
            or predecessor_plan.frozen_catalog_sha256 != catalog.catalog_sha256
            or predecessor_plan.prospective_catalog_sha256
            != catalog.prospective_catalog_sha256
            or predecessor_plan.frozen_catalog_source_commit
            != catalog.source_commit
            or predecessor_plan.frozen_catalog_source_bundle_sha256
            != catalog.source_bundle_sha256
            or predecessor_plan.rom_sha256 != catalog.rom_sha256
            or predecessor_plan.input_audit_receipt_file_sha256
            != args.input_audit_receipt_file_sha256
            or predecessor_plan.input_audit_result_sha256
            != canonical_sha256(audit_document)
        ):
            raise RedPartyDevelopmentOutcomeFreezeError(
                "successor predecessor differs from the frozen catalog"
            )
        private_root_path = _require_external(
            args.private_artifact_root,
            subject="private artifact root",
        )
        lineage_store = open_private_root(
            private_root_path,
            repository_root=PROJECT_ROOT,
        )
        predecessor, inherited_terminals = inspect_predecessor_campaign(
            predecessor_plan,
            predecessor_plan_file_sha256=(
                args.predecessor_campaign_plan_file_sha256
            ),
            store=lineage_store,
        )
    runner_sha256 = hashlib.sha256(_RUNNER.read_bytes()).hexdigest()
    plan = freeze_party_development_outcome_campaign(
        catalog,
        source_commit=source.git_commit,
        source_bundle_sha256=source_bundle,
        runner_source_sha256=runner_sha256,
        exact_ci_run=args.exact_ci_run,
        exact_ci_attempt=args.exact_ci_attempt,
        frozen_catalog_file_sha256=args.frozen_catalog_file_sha256,
        input_audit_receipt_file_sha256=args.input_audit_receipt_file_sha256,
        input_audit_result_sha256=canonical_sha256(audit_document),
        predecessor=predecessor,
        inherited_terminals=inherited_terminals,
    )
    payload = (
        json.dumps(
            plan.private_dict(),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    protected_files = {
        _require_external(args.frozen_catalog, subject="frozen catalog"):
        args.frozen_catalog_file_sha256,
        args.input_audit_receipt.resolve(): args.input_audit_receipt_file_sha256,
    }
    if predecessor_path is not None:
        protected_files[predecessor_path] = (
            args.predecessor_campaign_plan_file_sha256
        )
    _require_protected_inputs_unchanged(protected_files)
    _write_exclusive(args.output, payload)
    _require_protected_inputs_unchanged(protected_files)
    if predecessor_plan is not None:
        assert lineage_store is not None
        observed_predecessor, observed_terminals = inspect_predecessor_campaign(
            predecessor_plan,
            predecessor_plan_file_sha256=(
                args.predecessor_campaign_plan_file_sha256
            ),
            store=lineage_store,
        )
        if (
            observed_predecessor != predecessor
            or observed_terminals != inherited_terminals
        ):
            raise RedPartyDevelopmentOutcomeFreezeError(
                "successor lineage changed while its plan was frozen"
            )
    # Retain the bytes used for typed parsing as part of the same consistency
    # assertion; this also makes a future loader refactor fail closed.
    if (
        hashlib.sha256(catalog_payload).hexdigest()
        != args.frozen_catalog_file_sha256
        or hashlib.sha256(audit_payload).hexdigest()
        != args.input_audit_receipt_file_sha256
    ):
        raise RedPartyDevelopmentOutcomeFreezeError(
            "campaign freeze parsed different protected input bytes"
        )
    return {
        **plan.public_summary(),
        "status": "private_plan_frozen_exact_authorization_required",
        "campaign_plan_file_sha256": hashlib.sha256(payload).hexdigest(),
        "output_written_exclusively": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        result = _run(parser.parse_args(argv))
    except (OSError, RuntimeError, TypeError, ValueError):
        parser.error(
            "Red party-development campaign freeze failed closed; private paths were withheld."
        )
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
