#!/usr/bin/env python3
"""Freeze, preflight, execute, or admit the fixed rootless dependency campaign."""

# ruff: noqa: E402 -- script-local manifest modules must precede package imports.

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Never

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

from freeze_rootless_execution_manifest import _bindings, _current_public_bindings
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
from pokemon_red_completion.living_dex_dependency_curriculum import (
    DevelopmentCommitmentRoster,
    DevelopmentCommitmentRow,
    RootlessLivingDexDependencyDesign,
    build_rootless_living_dex_dependency_design,
    materialize_train_dependency_outcome,
)
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot, open_private_root
from pokemon_red_completion.provenance import canonical_sha256

LANE_ID = "rootless-living-dex-dependency-curriculum-v1"
CAMPAIGN_PLAN_SCHEMA = "pokemon.private.rootless-dependency-campaign-plan.v1"
CAMPAIGN_TERMINAL_SCHEMA = "pokemon.private.rootless-dependency-campaign-terminal.v1"
TRAIN_ADMISSION_SCHEMA = "pokemon.private.rootless-dependency-train-admission.v1"
PUBLIC_ROSTER_SCHEMA = "pokemon.core.rootless-dependency-development-roster.v1"
CAMPAIGN_PLAN_KIND = "rootless-dependency-campaign-plan"
OUTCOME_KIND = "rootless-dependency-train-outcome"
CAMPAIGN_TERMINAL_KIND = "rootless-dependency-campaign-terminal"
TRAIN_ADMISSION_KIND = "rootless-dependency-train-admission"
OPENING_KIND = "rootless-dependency-development-opening"
RUNNER_RELATIVE = "scripts/run_rootless_living_dex_dependency_campaign.py"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RootlessCampaignError(RuntimeError):
    """The frozen rootless campaign failed closed."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise RootlessCampaignError("arguments")


@dataclass(frozen=True, slots=True)
class _Gate:
    execution_manifest_sha256: str
    public_bindings: dict[str, str]
    semantic_bindings: dict[str, str]


@dataclass(frozen=True, slots=True)
class _Campaign:
    design: RootlessLivingDexDependencyDesign
    public_roster_sha256: str
    campaign_sha256: str
    plan_record_id: str
    plan: dict[str, object]


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("freeze", "preflight", "execute", "admit"), required=True
    )
    parser.add_argument("--execution-manifest", type=Path, required=True)
    parser.add_argument("--expected-execution-manifest-sha256", required=True)
    parser.add_argument("--dependency", action="append", required=True)
    parser.add_argument("--semantic-binding", action="append", required=True)
    parser.add_argument("--private-input-role", action="append", required=True)
    parser.add_argument("--public-roster", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--expected-campaign-sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    stage = "arguments"
    try:
        args = _parser().parse_args(argv)
        if (args.mode == "freeze") != (args.expected_campaign_sha256 is None):
            raise RootlessCampaignError("arguments")
        stage = "public_manifest_authentication"
        gate = _public_gate(args)
        stage = "public_roster_authentication"
        roster_document, roster_sha = _load_public_roster(args.public_roster)
        expected_roster = gate.semantic_bindings.get("development_roster_sha256")
        if roster_sha != expected_roster:
            raise RootlessCampaignError(stage)
        stage = "private_store_authentication"
        store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
        stage = "campaign_reconstruction"
        campaign = _reconstruct_campaign(store, roster_document, roster_sha, gate)
        if args.expected_campaign_sha256 is not None and (
            args.expected_campaign_sha256 != campaign.campaign_sha256
        ):
            raise RootlessCampaignError(stage)
        if args.mode == "freeze":
            stage = "campaign_freeze_write"
            result = _freeze(store, campaign, gate)
        elif args.mode == "preflight":
            stage = "campaign_preflight"
            result = _preflight(store, campaign, gate)
        elif args.mode == "execute":
            stage = "train_campaign_execution"
            result = _execute(store, campaign, gate)
        else:
            stage = "train_outcome_admission"
            result = _admit(store, campaign, gate)
        print(json.dumps(result, allow_nan=False, sort_keys=True))
        return 0
    except Exception:
        print(
            json.dumps(
                {
                    "schema": "pokemon.core.rootless-dependency-campaign-failure.v1",
                    "status": "failed_closed",
                    "failure_stage": stage,
                    "development_opening_payloads_disclosed_to_stage": 0,
                    "predictions": 0,
                    "rom_accesses": 0,
                    "controller_actions": 0,
                    "teacher_queries": 0,
                    "synthetic_rootless_train_outcomes_added": 0,
                    "synthetic_rootless_atomic_goal_episodes_added": 0,
                    "private_path_fields": 0,
                },
                sort_keys=True,
            )
        )
        return 1


def _public_gate(args: argparse.Namespace) -> _Gate:
    semantic = _bindings(args.semantic_binding)
    public = _current_public_bindings(
        lane_id=LANE_ID,
        runner=RUNNER_RELATIVE,
        dependencies=args.dependency,
    )
    invocation = rootless_execution_invocation(
        lane_id=LANE_ID,
        operation=args.mode,
        semantic_bindings=semantic,
        public_bindings=public,
        private_input_roles=tuple(sorted(args.private_input_role)),
    )
    payload = read_public_manifest(
        args.execution_manifest,
        repository_root=PROJECT_ROOT,
        forbidden_aliases=(args.public_roster,),
    )
    authenticate_rootless_execution_manifest(
        payload,
        expected_manifest_sha256=args.expected_execution_manifest_sha256,
        invocation=invocation,
        current_public_bindings=public,
    )
    return _Gate(args.expected_execution_manifest_sha256, public, semantic)


def _load_public_roster(path: Path) -> tuple[dict[str, object], str]:
    expected_path = PROJECT_ROOT / "configs" / "rootless-dependency-development-roster-v1.json"
    try:
        named = path.lstat()
        resolved = path.resolve(strict=True)
        payload = path.read_bytes()
    except OSError:
        raise RootlessCampaignError("public_roster_authentication") from None
    if (
        path.is_symlink()
        or not stat.S_ISREG(named.st_mode)
        or named.st_nlink != 1
        or resolved != expected_path.resolve(strict=True)
        or not 1 <= len(payload) <= 64 * 1024
    ):
        raise RootlessCampaignError("public_roster_authentication")
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RootlessCampaignError("public_roster_authentication") from None
    if not isinstance(document, dict) or _line(document) != payload:
        raise RootlessCampaignError("public_roster_authentication")
    _roster_rows(document)
    return document, hashlib.sha256(payload).hexdigest()


def _roster_rows(document: dict[str, object]) -> tuple[dict[str, str], ...]:
    if set(document) != {
        "private_path_fields",
        "provision_record_sha256",
        "row_count",
        "rows",
        "schema",
    } or (
        document.get("schema") != PUBLIC_ROSTER_SCHEMA
        or document.get("row_count") != 4
        or document.get("private_path_fields") != 0
        or not _is_sha(document.get("provision_record_sha256"))
    ):
        raise RootlessCampaignError("public_roster_authentication")
    raw_rows = document.get("rows")
    if not isinstance(raw_rows, list) or len(raw_rows) != 4:
        raise RootlessCampaignError("public_roster_authentication")
    rows: list[dict[str, str]] = []
    for raw in raw_rows:
        if not isinstance(raw, dict) or set(raw) != {
            "opening_sha256",
            "record_manifest_sha256",
            "scenario_id",
        }:
            raise RootlessCampaignError("public_roster_authentication")
        if not all(isinstance(raw[key], str) for key in raw):
            raise RootlessCampaignError("public_roster_authentication")
        row = {key: raw[key] for key in raw}
        if not _is_sha(row["opening_sha256"]) or not _is_sha(row["record_manifest_sha256"]):
            raise RootlessCampaignError("public_roster_authentication")
        rows.append(row)
    if len({row["scenario_id"] for row in rows}) != 4:
        raise RootlessCampaignError("public_roster_authentication")
    return tuple(rows)


def _reconstruct_campaign(
    store: PrivateArtifactRoot,
    roster_document: dict[str, object],
    roster_sha: str,
    gate: _Gate,
) -> _Campaign:
    rows = _roster_rows(roster_document)
    commitments: list[DevelopmentCommitmentRow] = []
    summaries: list[dict[str, str]] = []
    for row in rows:
        record = store.find_sealed_record(
            row["scenario_id"],
            expected_kind=OPENING_KIND,
        )
        if record is None or (
            record.summary.record_sha256 != row["opening_sha256"]
            or record.summary.manifest_sha256 != row["record_manifest_sha256"]
        ):
            raise RootlessCampaignError("campaign_reconstruction")
        commitments.append(DevelopmentCommitmentRow(row["scenario_id"], row["opening_sha256"]))
        summaries.append(row)
    design = build_rootless_living_dex_dependency_design(
        DevelopmentCommitmentRoster(tuple(commitments))
    )
    semantic = {
        "schema": "pokemon.core.rootless-dependency-campaign-identity.v1",
        "design_sha256": design.design_sha256,
        "development_roster_sha256": roster_sha,
        "train_scenario_ids": [row.scenario_id for row in design.train_scenarios],
        "assigned_actions": [row.assigned_action.value for row in design.train_scenarios],
    }
    campaign_sha = canonical_sha256(semantic)
    plan_id = f"rootless-dependency-plan-{campaign_sha[:24]}"
    freeze_execution_manifest_sha256 = gate.semantic_bindings.get(
        "freeze_execution_manifest_sha256",
        gate.execution_manifest_sha256,
    )
    if not _is_sha(freeze_execution_manifest_sha256):
        raise RootlessCampaignError("campaign_reconstruction")
    plan = {
        "schema": CAMPAIGN_PLAN_SCHEMA,
        "campaign_sha256": campaign_sha,
        "design_sha256": design.design_sha256,
        "development_roster_sha256": roster_sha,
        "freeze_execution_manifest_sha256": freeze_execution_manifest_sha256,
        "source_commit": gate.public_bindings["source_commit"],
        "source_bundle_sha256": gate.public_bindings["source_bundle_sha256"],
        "runner_sha256": gate.public_bindings["runner_sha256"],
        "train_scenario_ids": [row.scenario_id for row in design.train_scenarios],
        "assigned_actions": [row.assigned_action.value for row in design.train_scenarios],
        "development_commitments": summaries,
        "predictions_planned": 0,
        "synthetic_transitions_planned": 8,
        "private_path_fields": 0,
    }
    return _Campaign(design, roster_sha, campaign_sha, plan_id, plan)


def _freeze(store: PrivateArtifactRoot, campaign: _Campaign, gate: _Gate) -> dict[str, object]:
    record = store.publish_sealed_record(
        campaign.plan_record_id,
        kind=CAMPAIGN_PLAN_KIND,
        record=campaign.plan,
    )
    return {
        "schema": "pokemon.core.rootless-dependency-campaign-freeze.v1",
        "status": "campaign_frozen_zero_action",
        "campaign_sha256": campaign.campaign_sha256,
        "design_sha256": campaign.design.design_sha256,
        "development_roster_sha256": campaign.public_roster_sha256,
        "campaign_plan_record_sha256": record.summary.record_sha256,
        "campaign_plan_manifest_sha256": record.summary.manifest_sha256,
        "execution_manifest_sha256": gate.execution_manifest_sha256,
        "train_scenarios": 8,
        "development_commitments": 4,
        **_zero_effects(),
    }


def _preflight(store: PrivateArtifactRoot, campaign: _Campaign, gate: _Gate) -> dict[str, object]:
    _require_plan(store, campaign)
    registry = open_fixed_account_claim_registry()
    identities = _campaign_claim_identities(campaign)
    with fixed_account_claim_registry_lease(registry, exclusive=False):
        availability = [root_claim_is_available(registry, identity) for identity in identities]
    if not all(availability):
        raise RootlessCampaignError("campaign_preflight")
    return {
        "schema": "pokemon.core.rootless-dependency-campaign-preflight.v1",
        "status": "training_ready",
        "campaign_sha256": campaign.campaign_sha256,
        "design_sha256": campaign.design.design_sha256,
        "development_roster_sha256": campaign.public_roster_sha256,
        "execution_manifest_sha256": gate.execution_manifest_sha256,
        "train_scenarios": 8,
        "available_train_identities": 8,
        "available_campaign_identities": len(identities),
        "development_commitments": 4,
        "claim_boundary": (
            "fixed synthetic train campaign ready; no outcome, fit, gameplay, authority, "
            "or transfer result"
        ),
        **_zero_effects(),
    }


def _execute(store: PrivateArtifactRoot, campaign: _Campaign, gate: _Gate) -> dict[str, object]:
    _require_plan(store, campaign)
    registry = open_fixed_account_claim_registry()
    lane_identity, campaign_identity, *scenario_identities, terminal_identity = (
        _campaign_claim_identities(campaign)
    )
    execution_identity = _execution_identity(
        campaign,
        gate,
        execution_manifest_sha256=gate.execution_manifest_sha256,
    )
    outcomes: list[str] = []
    settled_outcomes = 0
    interrupted_outcomes = 0
    with fixed_account_claim_registry_lease(registry, exclusive=True):
        for identity in (lane_identity, campaign_identity):
            _claim_or_authenticate(registry, identity, execution_identity, gate)
        for scenario, identity in zip(
            campaign.design.train_scenarios,
            scenario_identities,
            strict=True,
        ):
            record_id = _outcome_record_id(scenario.scenario_id)
            existing = store.find_sealed_record(record_id, expected_kind=OUTCOME_KIND)
            if root_claim_is_available(registry, identity):
                write_root_claim(
                    registry,
                    root_consumption_sha256=identity,
                    execution_identity_sha256=execution_identity,
                    source_commit=gate.public_bindings["source_commit"],
                    runner_sha256=gate.public_bindings["runner_sha256"],
                )
                if existing is not None:
                    raise RootlessCampaignError("train_campaign_execution")
                outcome = materialize_train_dependency_outcome(scenario)
                store.publish_sealed_record(
                    record_id,
                    kind=OUTCOME_KIND,
                    record=outcome.public_dict(),
                )
            else:
                _require_claim(registry, identity, execution_identity)
                if existing is None:
                    interrupted = materialize_train_dependency_outcome(
                        scenario,
                        interrupted=True,
                    )
                    store.publish_sealed_record(
                        record_id,
                        kind=OUTCOME_KIND,
                        record=interrupted.public_dict(),
                    )
            outcome_record = store.find_sealed_record(record_id, expected_kind=OUTCOME_KIND)
            if outcome_record is None:
                raise RootlessCampaignError("train_campaign_execution")
            actual = outcome_record.read()
            settled = materialize_train_dependency_outcome(scenario).public_dict()
            interrupted = materialize_train_dependency_outcome(
                scenario,
                interrupted=True,
            ).public_dict()
            if actual == settled:
                settled_outcomes += 1
            elif actual == interrupted:
                interrupted_outcomes += 1
            else:
                raise RootlessCampaignError("train_campaign_execution")
            outcomes.append(outcome_record.summary.record_sha256)
        _claim_or_authenticate(registry, terminal_identity, execution_identity, gate)
        terminal = {
            "schema": CAMPAIGN_TERMINAL_SCHEMA,
            "status": "completed",
            "campaign_sha256": campaign.campaign_sha256,
            "design_sha256": campaign.design.design_sha256,
            "train_outcome_record_sha256": outcomes,
            "settled_outcomes": settled_outcomes,
            "interrupted_outcomes": interrupted_outcomes,
        }
        terminal_record = store.publish_sealed_record(
            _terminal_record_id(campaign),
            kind=CAMPAIGN_TERMINAL_KIND,
            record=terminal,
        )
    return {
        "schema": "pokemon.core.rootless-dependency-campaign-execution.v1",
        "status": (
            "train_campaign_completed_pending_admission"
            if interrupted_outcomes == 0
            else "train_campaign_closed_with_censored_outcomes"
        ),
        "campaign_sha256": campaign.campaign_sha256,
        "settled_outcomes": settled_outcomes,
        "interrupted_outcomes": interrupted_outcomes,
        "campaign_terminal_sha256": terminal_record.summary.record_sha256,
        "synthetic_rootless_train_outcomes_added": 0,
        "synthetic_rootless_atomic_goal_episodes_added": 0,
        "development_opening_payloads_disclosed_to_stage": 0,
        "predictions": 0,
        "rom_accesses": 0,
        "controller_actions": 0,
        "teacher_queries": 0,
        "private_path_fields": 0,
    }


def _admit(store: PrivateArtifactRoot, campaign: _Campaign, gate: _Gate) -> dict[str, object]:
    _require_plan(store, campaign)
    registry = open_fixed_account_claim_registry()
    identities = _campaign_claim_identities(campaign)
    execute_execution_manifest_sha256 = gate.semantic_bindings.get(
        "execute_execution_manifest_sha256"
    )
    if not isinstance(execute_execution_manifest_sha256, str) or not _is_sha(
        execute_execution_manifest_sha256
    ):
        raise RootlessCampaignError("train_outcome_admission")
    execution_identity = _execution_identity(
        campaign,
        gate,
        execution_manifest_sha256=execute_execution_manifest_sha256,
    )
    outcome_hashes: list[str] = []
    rewards: list[int] = []
    with fixed_account_claim_registry_lease(registry, exclusive=False):
        for identity in identities:
            _require_claim(registry, identity, execution_identity)
        terminal_record = store.find_sealed_record(
            _terminal_record_id(campaign),
            expected_kind=CAMPAIGN_TERMINAL_KIND,
        )
        if terminal_record is None:
            raise RootlessCampaignError("train_outcome_admission")
        for scenario in campaign.design.train_scenarios:
            record = store.find_sealed_record(
                _outcome_record_id(scenario.scenario_id),
                expected_kind=OUTCOME_KIND,
            )
            expected_outcome = materialize_train_dependency_outcome(scenario)
            if record is None or record.read() != expected_outcome.public_dict():
                raise RootlessCampaignError("train_outcome_admission")
            outcome_hashes.append(record.summary.record_sha256)
            if expected_outcome.reward is None:
                raise RootlessCampaignError("train_outcome_admission")
            rewards.append(expected_outcome.reward)
        expected_terminal = {
            "schema": CAMPAIGN_TERMINAL_SCHEMA,
            "status": "completed",
            "campaign_sha256": campaign.campaign_sha256,
            "design_sha256": campaign.design.design_sha256,
            "train_outcome_record_sha256": outcome_hashes,
            "settled_outcomes": 8,
            "interrupted_outcomes": 0,
        }
        if terminal_record.read() != expected_terminal or sorted(rewards) != [-1] * 4 + [1] * 4:
            raise RootlessCampaignError("train_outcome_admission")
        dataset_sha = canonical_sha256(
            {
                "schema": "pokemon.core.rootless-dependency-admitted-dataset.v1",
                "campaign_sha256": campaign.campaign_sha256,
                "outcome_record_sha256": outcome_hashes,
            }
        )
        admission = {
            "schema": TRAIN_ADMISSION_SCHEMA,
            "status": "admitted",
            "campaign_sha256": campaign.campaign_sha256,
            "design_sha256": campaign.design.design_sha256,
            "train_dataset_sha256": dataset_sha,
            "outcome_record_sha256": outcome_hashes,
            "settled_outcomes": 8,
            "positive_outcomes": 4,
            "negative_outcomes": 4,
            "development_opening_payloads_disclosed_to_stage": 0,
        }
        admission_record = store.publish_sealed_record(
            _admission_record_id(campaign),
            kind=TRAIN_ADMISSION_KIND,
            record=admission,
        )
    return {
        "schema": "pokemon.core.rootless-dependency-campaign-admission.v1",
        "status": "eight_synthetic_train_outcomes_admitted",
        "campaign_sha256": campaign.campaign_sha256,
        "design_sha256": campaign.design.design_sha256,
        "train_dataset_sha256": dataset_sha,
        "train_admission_record_sha256": admission_record.summary.record_sha256,
        "synthetic_rootless_train_outcomes_added": 8,
        "synthetic_rootless_atomic_goal_episodes_added": 8,
        "legacy_outcome_questions_added": 0,
        "causal_train_examples_added": 0,
        "model_fits_added": 0,
        "unseen_comparisons_added": 0,
        "authority_promotions_added": 0,
        "transfer_results_added": 0,
        "development_opening_payloads_disclosed_to_stage": 0,
        "predictions": 0,
        "rom_accesses": 0,
        "controller_actions": 0,
        "teacher_queries": 0,
        "private_path_fields": 0,
    }


def _require_plan(store: PrivateArtifactRoot, campaign: _Campaign) -> None:
    record = store.find_sealed_record(
        campaign.plan_record_id,
        expected_kind=CAMPAIGN_PLAN_KIND,
    )
    if record is None or record.read() != campaign.plan:
        raise RootlessCampaignError("campaign_authentication")


def _campaign_claim_identities(campaign: _Campaign) -> tuple[str, ...]:
    identities = [
        _claim_identity("lane", campaign.campaign_sha256, None),
        _claim_identity("campaign", campaign.campaign_sha256, None),
    ]
    identities.extend(
        _claim_identity("scenario", campaign.campaign_sha256, scenario.scenario_id)
        for scenario in campaign.design.train_scenarios
    )
    identities.append(_claim_identity("terminal", campaign.campaign_sha256, None))
    return tuple(identities)


def _claim_identity(kind: str, campaign_sha256: str, scenario_id: str | None) -> str:
    return canonical_sha256(
        {
            "schema": "pokemon.core.rootless-dependency-one-shot-claim.v1",
            "kind": kind,
            "campaign_sha256": campaign_sha256,
            "scenario_id": scenario_id,
        }
    )


def _execution_identity(
    campaign: _Campaign,
    gate: _Gate,
    *,
    execution_manifest_sha256: str,
) -> str:
    if not _is_sha(execution_manifest_sha256):
        raise RootlessCampaignError("claim_authentication")
    return canonical_sha256(
        {
            "schema": "pokemon.core.rootless-dependency-execution-identity.v1",
            "campaign_sha256": campaign.campaign_sha256,
            "execution_manifest_sha256": execution_manifest_sha256,
            "source_commit": gate.public_bindings["source_commit"],
            "runner_sha256": gate.public_bindings["runner_sha256"],
        }
    )


def _claim_or_authenticate(
    registry: Path,
    identity: str,
    execution_identity: str,
    gate: _Gate,
) -> None:
    if root_claim_is_available(registry, identity):
        write_root_claim(
            registry,
            root_consumption_sha256=identity,
            execution_identity_sha256=execution_identity,
            source_commit=gate.public_bindings["source_commit"],
            runner_sha256=gate.public_bindings["runner_sha256"],
        )
    else:
        _require_claim(registry, identity, execution_identity)


def _require_claim(registry: Path, identity: str, execution_identity: str) -> None:
    claim = read_root_claim(registry, identity)
    if claim.get("execution_identity_sha256") != execution_identity:
        raise RootlessCampaignError("claim_authentication")


def _outcome_record_id(scenario_id: str) -> str:
    return f"rootless-dep-outcome-{scenario_id}"


def _terminal_record_id(campaign: _Campaign) -> str:
    return f"rootless-dependency-terminal-{campaign.campaign_sha256[:24]}"


def _admission_record_id(campaign: _Campaign) -> str:
    return f"rootless-dependency-admission-{campaign.campaign_sha256[:24]}"


def _zero_effects() -> dict[str, int]:
    return {
        "development_opening_payloads_disclosed_to_stage": 0,
        "predictions": 0,
        "synthetic_transitions": 0,
        "admitted_train_outcomes": 0,
        "model_fits": 0,
        "development_comparisons": 0,
        "rom_accesses": 0,
        "controller_actions": 0,
        "teacher_queries": 0,
        "synthetic_rootless_train_outcomes_added": 0,
        "synthetic_rootless_atomic_goal_episodes_added": 0,
        "private_path_fields": 0,
    }


def _line(document: dict[str, object]) -> bytes:
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


if __name__ == "__main__":
    raise SystemExit(main())
