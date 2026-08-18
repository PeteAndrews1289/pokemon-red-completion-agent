#!/usr/bin/env python3
"""Freeze and action-free preflight the Red acquisition-replanning campaign."""

# ruff: noqa: E402 -- load the reviewed development runner before project imports

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_RUNNER_PATH = PROJECT_ROOT / "scripts/run_repeatable_goal_manager_development.py"


def _load_development_runner() -> ModuleType:
    name = "_pokemon_red_repeatable_goal_manager_development_runner"
    spec = importlib.util.spec_from_file_location(name, DEVELOPMENT_RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("development_runner_import")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


development_runner = _load_development_runner()

from pokemon_red_completion.acquisition_replanning_curriculum import (
    ACQUISITION_REPLANNING_EPISODES,
    ACQUISITION_REPLANNING_MAX_DECISIONS,
    ACQUISITION_REPLANNING_ROOTS,
    AcquisitionReplanningRunResult,
    acquisition_replanning_behavior_contract,
    acquisition_replanning_evidence_contract,
    load_acquisition_replanning_episode,
    run_acquisition_replanning_episode,
)
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_composition_qualification import (
    read_root_claim,
    root_claim_is_available,
    root_consumption_sha256,
    write_root_claim,
)
from pokemon_red_completion.provenance import canonical_sha256

CAMPAIGN_SCHEMA = "pokemon.red.acquisition-replanning-campaign.v1"
PROFILE_LINEAGE_SCHEMA = "pokemon.red.acquisition-replanning-profile-lineage.v1"
CLAIM_SCHEMA = "pokemon.red.acquisition-replanning-trial-claim.v1"
CAMPAIGN_CLAIM_SCHEMA = "pokemon.red.acquisition-replanning-root-set-claim.v1"
EXECUTION_SCHEMA = "pokemon.red.acquisition-replanning-execution-identity.v1"
MAX_ACTIONS_PER_DECISION = 6_000
MAX_FRAMES_PER_DECISION = 600_000
MAX_EPISODE_ACTIONS = 12_000
MAX_EPISODE_FRAMES = 1_200_000
SCHEDULE = (
    GoalKind.ACQUIRE_SPECIES,
    GoalKind.ACQUIRE_SPECIES,
    GoalKind.DEVELOP_TEAM,
    GoalKind.EXPLORE,
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_BYTES = 4 * 1024 * 1024


class AcquisitionReplanningRunError(RuntimeError):
    """Path-free failure at one declared campaign qualification stage."""

    def __init__(self, stage: str) -> None:
        super().__init__(stage)
        self.stage = stage


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("freeze", "preflight", "execute", "admit"),
        required=True,
    )
    parser.add_argument("--context-plan", type=Path, required=True)
    parser.add_argument("--profile-lineage", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--fit-summary", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--expected-runner-sha256", required=True)
    parser.add_argument("--expected-development-runner-sha256", required=True)
    parser.add_argument("--expected-runtime-sha256", required=True)
    parser.add_argument("--expected-numpy-runtime-sha256", required=True)
    parser.add_argument("--expected-skill-manifest-sha256", required=True)
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--expected-profile-lineage-sha256", required=True)
    parser.add_argument("--rom", type=Path, default=None)
    parser.add_argument("--campaign-plan", type=Path, required=True)
    parser.add_argument("--expected-campaign-sha256")
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--trial-index", type=int)
    parser.add_argument("--expected-execution-identity-sha256")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int)
    return parser


def _base_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        context_plan=args.context_plan,
        context_catalog=args.context_catalog,
        model=args.model,
        fit_summary=args.fit_summary,
        expected_source_commit=args.expected_source_commit,
        expected_source_bundle_sha256=args.expected_source_bundle_sha256,
        expected_runner_sha256=args.expected_development_runner_sha256,
        expected_runtime_sha256=args.expected_runtime_sha256,
        expected_numpy_runtime_sha256=args.expected_numpy_runtime_sha256,
        expected_skill_manifest_sha256=args.expected_skill_manifest_sha256,
        expected_context_plan_sha256=args.expected_context_plan_sha256,
        rom=args.rom,
    )


def _readiness(args: argparse.Namespace) -> tuple[Any, str, Mapping[str, object]]:
    runner_sha256 = _file_sha256(Path(__file__).resolve())
    if runner_sha256 != _sha(args.expected_runner_sha256, "runner"):
        raise AcquisitionReplanningRunError("external_executable_attestation")
    if _file_sha256(DEVELOPMENT_RUNNER_PATH) != _sha(
        args.expected_development_runner_sha256,
        "development runner",
    ):
        raise AcquisitionReplanningRunError("external_executable_attestation")
    try:
        readiness = development_runner._readiness(_base_args(args))
    except BaseException as error:
        stage = getattr(error, "stage", "development_readiness")
        raise AcquisitionReplanningRunError(str(stage)) from None
    lineage_path = development_runner._external_regular(
        args.profile_lineage,
        rom_path=readiness.rom_path,
    )
    payload = lineage_path.read_bytes()
    expected = _sha(args.expected_profile_lineage_sha256, "profile lineage")
    if hashlib.sha256(payload).hexdigest() != expected:
        raise AcquisitionReplanningRunError("profile_lineage_authentication")
    lineage = _canonical_document(payload, subject="profile lineage")
    _validate_profile_lineage(lineage, readiness)
    return readiness, runner_sha256, lineage


def _admission_readiness(
    args: argparse.Namespace,
) -> tuple[Any, str, tuple[Path, str, Mapping[str, object]]]:
    """Authenticate only immutable admission inputs, not spent live contexts."""

    runner_sha256 = _file_sha256(Path(__file__).resolve())
    if runner_sha256 != _sha(args.expected_runner_sha256, "runner") or (
        _file_sha256(DEVELOPMENT_RUNNER_PATH)
        != _sha(args.expected_development_runner_sha256, "development runner")
    ):
        raise AcquisitionReplanningRunError("external_executable_attestation")
    campaign_path = _admission_regular(args.campaign_plan)
    payload = campaign_path.read_bytes()
    campaign_sha256 = hashlib.sha256(payload).hexdigest()
    if campaign_sha256 != _sha(args.expected_campaign_sha256, "campaign"):
        raise AcquisitionReplanningRunError("campaign_authentication")
    campaign = _canonical_document(payload, subject="campaign")
    candidate_identity = _mapping(campaign.get("candidate"), "candidate")

    try:
        development_runner._require_project_import_origins()
        source = development_runner.detect_source_identity(
            development_runner.PROJECT_ROOT,
            include_untracked=True,
        )
        development_runner.require_clean_source(source)
        development_runner.require_published_source(
            development_runner.PROJECT_ROOT,
            source,
        )
        runtime = development_runner.build_runtime_identity()
        numpy_runtime_sha256 = (
            development_runner.goal_manager_development_numpy_runtime_sha256()
        )
        source_bundle_sha256 = development_runner.working_source_bundle_sha256(
            development_runner.PROJECT_ROOT
        )
        skill_manifest_sha256 = _sha(
            development_runner.composition_skill_manifest(
                development_runner.PROJECT_ROOT
            ).get("manifest_sha256"),
            "skill manifest",
        )
        if (
            source.git_commit != args.expected_source_commit
            or source_bundle_sha256
            != _sha(args.expected_source_bundle_sha256, "source bundle")
            or runtime.sha256 != _sha(args.expected_runtime_sha256, "runtime")
            or numpy_runtime_sha256
            != _sha(args.expected_numpy_runtime_sha256, "NumPy runtime")
            or skill_manifest_sha256
            != _sha(args.expected_skill_manifest_sha256, "skill manifest")
        ):
            raise AcquisitionReplanningRunError("external_executable_attestation")
        promotion, _promotion_commit = (
            development_runner.load_committed_goal_manager_promotion_plan(
                development_runner.PROJECT_ROOT
            )
        )
        context_catalog_path = _admission_regular(args.context_catalog)
        model_path = _admission_regular(args.model)
        fit_summary_path = _admission_regular(args.fit_summary)
        candidate = development_runner.authenticate_goal_manager_candidate(
            repository_root=development_runner.PROJECT_ROOT,
            plan=promotion,
            context_catalog_path=context_catalog_path,
            model_path=model_path,
            fit_summary_path=fit_summary_path,
        )
    except AcquisitionReplanningRunError:
        raise
    except BaseException as error:
        stage = getattr(error, "stage", "admission_readiness")
        raise AcquisitionReplanningRunError(str(stage)) from None

    raw_rom = args.rom or os.environ.get("POKEMON_RED_ROM")
    rom_path = (
        Path(raw_rom).expanduser().resolve()
        if raw_rom is not None
        else (PROJECT_ROOT / ".admission-rom-location-unavailable").resolve()
    )
    readiness = development_runner._Readiness(
        source=source,
        source_bundle_sha256=source_bundle_sha256,
        runner_sha256=_sha(
            args.expected_development_runner_sha256,
            "development runner",
        ),
        runtime=runtime,
        numpy_runtime_sha256=numpy_runtime_sha256,
        skill_manifest_sha256=skill_manifest_sha256,
        rom_path=rom_path,
        rom=SimpleNamespace(
            sha256=_sha(candidate_identity.get("rom_sha256"), "ROM")
        ),
        candidate=candidate,
        context_catalog_path=context_catalog_path,
        model_path=model_path,
        fit_summary_path=fit_summary_path,
        context_plan_path=Path(args.context_plan).expanduser().resolve(),
        context_plan_sha256=_sha(
            args.expected_context_plan_sha256,
            "context plan",
        ),
        entries=(),
    )
    return readiness, runner_sha256, (campaign_path, campaign_sha256, campaign)


def _admission_regular(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        metadata = path.expanduser().lstat()
    except OSError:
        raise AcquisitionReplanningRunError("admission_input_authentication") from None
    if (
        path.expanduser().is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or resolved.is_relative_to(PROJECT_ROOT.resolve())
    ):
        raise AcquisitionReplanningRunError("admission_input_authentication")
    return resolved


def _validate_profile_lineage(lineage: Mapping[str, object], readiness: Any) -> None:
    expected_keys = {
        "builder_runner_sha256",
        "builder_source_bundle_sha256",
        "builder_source_commit",
        "context_catalog_sha256",
        "entries",
        "output_plan_sha256",
        "paired_plan_sha256",
        "prior_campaign_sha256",
        "schema",
        "source_profile_manifest_sha256",
        "source_plan_sha256",
    }
    rows = lineage.get("entries")
    if (
        set(lineage) != expected_keys
        or lineage.get("schema") != PROFILE_LINEAGE_SCHEMA
        or lineage.get("output_plan_sha256") != readiness.context_plan_sha256
        or lineage.get("context_catalog_sha256")
        != readiness.candidate.catalog.catalog_sha256
        or not isinstance(rows, list)
        or len(rows) != len(readiness.entries)
    ):
        raise AcquisitionReplanningRunError("profile_lineage_authentication")
    entries = {entry.slot_id: entry for entry in readiness.entries}
    seen: set[str] = set()
    transformed = 0
    for raw in rows:
        row = _mapping(raw, "profile lineage entry")
        if set(row) != {
            "envelope_file_sha256",
            "output_profile_sha256",
            "slot_id",
            "source_profile_sha256",
            "state_file_sha256",
            "transformed",
        }:
            raise AcquisitionReplanningRunError("profile_lineage_authentication")
        slot_id = _text(row.get("slot_id"), "profile lineage slot")
        if slot_id in seen or slot_id not in entries:
            raise AcquisitionReplanningRunError("profile_lineage_authentication")
        seen.add(slot_id)
        entry = entries[slot_id]
        if (
            _file_sha256(entry.state)
            != _sha(row.get("state_file_sha256"), "profile lineage state")
            or _file_sha256(entry.envelope)
            != _sha(row.get("envelope_file_sha256"), "profile lineage envelope")
            or _file_sha256(entry.profile)
            != _sha(row.get("output_profile_sha256"), "profile lineage profile")
        ):
            raise AcquisitionReplanningRunError("profile_lineage_authentication")
        _sha(row.get("source_profile_sha256"), "source profile")
        if type(row.get("transformed")) is not bool:  # noqa: E721
            raise AcquisitionReplanningRunError("profile_lineage_authentication")
        transformed += int(cast(bool, row.get("transformed")))
    if seen != set(entries) or transformed != ACQUISITION_REPLANNING_ROOTS:
        raise AcquisitionReplanningRunError("profile_lineage_authentication")


def _transformed_slots(lineage: Mapping[str, object]) -> tuple[str, ...]:
    rows = cast(list[Mapping[str, object]], lineage["entries"])
    return tuple(
        _text(row.get("slot_id"), "profile lineage slot")
        for row in rows
        if row["transformed"]
    )


def _inspect_declared_roots(
    readiness: Any,
    lineage: Mapping[str, object],
) -> tuple[Any, ...]:
    slots = _transformed_slots(lineage)
    lineage_by_slot = {
        _text(row.get("slot_id"), "profile lineage slot"): row
        for row in cast(list[Mapping[str, object]], lineage["entries"])
    }
    entry_indices = {entry.slot_id: index for index, entry in enumerate(readiness.entries)}
    registry = development_runner.open_fixed_account_claim_registry()
    roots: list[Any] = []
    for slot_id in slots:
        index = entry_indices[slot_id]
        entry = readiness.entries[index]
        assignment = readiness.candidate.registry.assignment(slot_id)
        if (
            assignment.partition != "train"
            or assignment.focus_kind is not GoalKind.ACQUIRE_SPECIES
            or not development_runner._historical_root_is_open(readiness, entry, registry)
        ):
            raise AcquisitionReplanningRunError("declared_root_admission")
        try:
            root = development_runner._inspect_root(
                readiness,
                entry,
                entry_index=index,
            )
        except BaseException:
            raise AcquisitionReplanningRunError("action_free_root_inventory") from None
        if root is None:
            raise AcquisitionReplanningRunError("action_free_root_inventory")
        lineage_row = lineage_by_slot[slot_id]
        if (
            root.state_file_sha256
            != _sha(lineage_row.get("state_file_sha256"), "profile lineage state")
            or root.envelope_file_sha256
            != _sha(
                lineage_row.get("envelope_file_sha256"),
                "profile lineage envelope",
            )
            or root.profile_file_sha256
            != _sha(
                lineage_row.get("output_profile_sha256"),
                "profile lineage profile",
            )
        ):
            raise AcquisitionReplanningRunError("profile_lineage_root_drift")
        kinds = tuple(root.available_goal_kinds)
        required = {
            GoalKind.ACQUIRE_SPECIES.value,
            GoalKind.DEVELOP_TEAM.value,
            GoalKind.EXPLORE.value,
        }
        if (
            len(kinds) < 3
            or not required.issubset(kinds)
            or GoalKind.EVOLVE_SPECIES.value in kinds
        ):
            raise AcquisitionReplanningRunError("action_free_root_inventory")
        roots.append(root)
    if len(roots) != ACQUISITION_REPLANNING_ROOTS:
        raise AcquisitionReplanningRunError("declared_root_admission")
    return tuple(roots)


def _freeze(
    args: argparse.Namespace,
    readiness: Any,
    runner_sha256: str,
    lineage: Mapping[str, object],
) -> dict[str, object]:
    if args.expected_campaign_sha256 is not None:
        raise AcquisitionReplanningRunError("mode_arguments")
    destination = development_runner._new_external_file(
        args.campaign_plan,
        rom_path=readiness.rom_path,
    )
    store, private_root_identity = development_runner._open_bound_private_root(
        args.private_root,
        rom_path=readiness.rom_path,
    )
    roots = _inspect_declared_roots(readiness, lineage)
    private_roots = [development_runner._private_root_record(root) for root in roots]
    campaign_claim = canonical_sha256(
        {
            "roots": [
                {
                    "envelope_sha256": root["envelope_sha256"],
                    "state_sha256": root["state_sha256"],
                }
                for root in private_roots
            ],
            "schema": CAMPAIGN_CLAIM_SCHEMA,
        }
    )
    trial_rows: list[dict[str, object]] = []
    for root_index in range(ACQUISITION_REPLANNING_ROOTS):
        for offset, assigned in enumerate(SCHEDULE):
            trial_rows.append(
                {
                    "assigned_intervention": assigned.value,
                    "maximum_decisions": ACQUISITION_REPLANNING_MAX_DECISIONS,
                    "root_index": root_index,
                    "seed": 20_000 + root_index * 100 + offset,
                    "trial_index": len(trial_rows),
                }
            )
    identity = {
        "behavior_contract": acquisition_replanning_behavior_contract(),
        "campaign_claim_sha256": campaign_claim,
        "candidate": development_runner._candidate_identity(readiness),
        "context_plan_sha256": readiness.context_plan_sha256,
        "development_runner_sha256": readiness.runner_sha256,
        "evidence_contract": acquisition_replanning_evidence_contract(),
        "execution_limits": _execution_limits(),
        "numpy_runtime_sha256": readiness.numpy_runtime_sha256,
        "private_root_identity_sha256": private_root_identity,
        "profile_lineage_manifest_sha256": _sha(
            args.expected_profile_lineage_sha256,
            "profile lineage",
        ),
        "roots": private_roots,
        "runner_sha256": runner_sha256,
        "runtime_sha256": readiness.runtime.sha256,
        "schema": CAMPAIGN_SCHEMA,
        "skill_manifest_sha256": readiness.skill_manifest_sha256,
        "source_bundle_sha256": readiness.source_bundle_sha256,
        "source_commit": readiness.source.git_commit,
        "trials": trial_rows,
    }
    campaign_id = canonical_sha256(identity)
    trials: list[dict[str, object]] = []
    for trial in trial_rows:
        trial_index = cast(int, trial["trial_index"])
        claim = canonical_sha256(
            {
                "campaign_id": campaign_id,
                "schema": CLAIM_SCHEMA,
                "trial_index": trial_index,
            }
        )
        execution = canonical_sha256(
            {
                "assigned_intervention": trial["assigned_intervention"],
                "campaign_id": campaign_id,
                "maximum_decisions": trial["maximum_decisions"],
                "model_canonical_sha256": readiness.candidate.plan.model_canonical_sha256,
                "root_index": trial["root_index"],
                "schema": EXECUTION_SCHEMA,
                "seed": trial["seed"],
                "trial_claim_sha256": claim,
                "trial_index": trial_index,
            }
        )
        episode_id = f"red-acq-{campaign_id}-{trial_index:02d}"
        if store.inspect_episode_state(episode_id).status != "absent":
            raise AcquisitionReplanningRunError("local_identity_collision")
        trials.append(
            {
                **trial,
                "episode_id": episode_id,
                "execution_identity_sha256": execution,
                "trial_claim_sha256": claim,
            }
        )
    registry = development_runner.open_fixed_account_claim_registry()
    if not development_runner._trial_claim_is_available(registry, campaign_claim):
        raise AcquisitionReplanningRunError("campaign_identity_collision")
    if any(
        not development_runner._trial_claim_is_available(
            registry,
            cast(str, trial["trial_claim_sha256"]),
        )
        for trial in trials
    ):
        raise AcquisitionReplanningRunError("global_identity_collision")
    plan = {**identity, "campaign_id": campaign_id, "trials": trials}
    payload = _canonical_line(plan)
    development_runner._write_exclusive(destination, payload)
    return _public_result(
        readiness,
        runner_sha256=runner_sha256,
        campaign_sha256=hashlib.sha256(payload).hexdigest(),
        campaign_claim_sha256=campaign_claim,
        profile_lineage_sha256=_sha(
            args.expected_profile_lineage_sha256,
            "profile lineage",
        ),
        status="campaign_frozen_without_prediction_or_action",
        available_trials=ACQUISITION_REPLANNING_EPISODES,
    )


def _preflight(
    args: argparse.Namespace,
    readiness: Any,
    runner_sha256: str,
    lineage: Mapping[str, object],
) -> dict[str, object]:
    if args.expected_campaign_sha256 is None:
        raise AcquisitionReplanningRunError("mode_arguments")
    store, private_root_identity = development_runner._open_bound_private_root(
        args.private_root,
        rom_path=readiness.rom_path,
    )
    payload = development_runner._external_regular(
        args.campaign_plan,
        rom_path=readiness.rom_path,
    ).read_bytes()
    expected_campaign = _sha(args.expected_campaign_sha256, "campaign")
    if hashlib.sha256(payload).hexdigest() != expected_campaign:
        raise AcquisitionReplanningRunError("campaign_authentication")
    plan = _canonical_document(payload, subject="campaign")
    _validate_campaign(
        plan,
        readiness=readiness,
        runner_sha256=runner_sha256,
        expected_profile_lineage_sha256=_sha(
            args.expected_profile_lineage_sha256,
            "profile lineage",
        ),
        expected_private_root_identity_sha256=private_root_identity,
    )
    inspected = _inspect_declared_roots(readiness, lineage)
    if [development_runner._private_root_record(root) for root in inspected] != list(
        _roots(plan)
    ):
        raise AcquisitionReplanningRunError("campaign_root_drift")
    registry = development_runner.open_fixed_account_claim_registry()
    campaign_claim = _sha(plan.get("campaign_claim_sha256"), "campaign claim")
    if not development_runner._trial_claim_is_available(registry, campaign_claim):
        raise AcquisitionReplanningRunError("campaign_identity_collision")
    available = 0
    for trial in _trials(plan):
        episode_id = _text(trial.get("episode_id"), "episode")
        claim = _sha(trial.get("trial_claim_sha256"), "claim")
        if (
            store.inspect_episode_state(episode_id).status == "absent"
            and development_runner._trial_claim_is_available(registry, claim)
        ):
            available += 1
    if available != ACQUISITION_REPLANNING_EPISODES:
        raise AcquisitionReplanningRunError("campaign_identity_collision")
    return _public_result(
        readiness,
        runner_sha256=runner_sha256,
        campaign_sha256=expected_campaign,
        campaign_claim_sha256=campaign_claim,
        profile_lineage_sha256=_sha(
            args.expected_profile_lineage_sha256,
            "profile lineage",
        ),
        status="training_ready_identity_unclaimed",
        available_trials=available,
    )


def _execute(
    args: argparse.Namespace,
    readiness: Any,
    runner_sha256: str,
    lineage: Mapping[str, object],
) -> dict[str, object]:
    if (
        args.expected_campaign_sha256 is None
        or args.expected_execution_identity_sha256 is None
        or type(args.trial_index) is not int  # noqa: E721
        or args.trial_index < 0
        or args.watch
        or args.speed is not None
    ):
        raise AcquisitionReplanningRunError("mode_arguments")
    store, private_root_identity = development_runner._open_bound_private_root(
        args.private_root,
        rom_path=readiness.rom_path,
    )
    campaign_path, campaign_sha256, plan = _authenticated_campaign(
        args,
        readiness=readiness,
        runner_sha256=runner_sha256,
        private_root_identity=private_root_identity,
    )
    trials = _trials(plan)
    if args.trial_index >= len(trials):
        raise AcquisitionReplanningRunError("trial_selection")
    trial = trials[args.trial_index]
    if trial.get("trial_index") != args.trial_index:
        raise AcquisitionReplanningRunError("trial_selection")
    execution_identity = _sha(
        trial.get("execution_identity_sha256"),
        "execution identity",
    )
    if execution_identity != _sha(
        args.expected_execution_identity_sha256,
        "expected execution identity",
    ):
        raise AcquisitionReplanningRunError("execution_authorization")
    roots = _roots(plan)
    root_index = _integer(trial.get("root_index"), "root index")
    if root_index >= len(roots):
        raise AcquisitionReplanningRunError("campaign_authentication")
    root_record = roots[root_index]
    entry_index = _integer(root_record.get("entry_index"), "entry index")
    if entry_index >= len(readiness.entries):
        raise AcquisitionReplanningRunError("campaign_authentication")
    entry = readiness.entries[entry_index]
    transformed_slots = _transformed_slots(lineage)
    if entry.slot_id != transformed_slots[root_index]:
        raise AcquisitionReplanningRunError("campaign_root_drift")
    registry = development_runner.open_fixed_account_claim_registry()
    campaign_id = _sha(plan.get("campaign_id"), "campaign identity")
    if not _root_is_available_or_reserved(
        registry,
        root_record,
        campaign_id=campaign_id,
        source_commit=readiness.source.git_commit or "",
        runner_sha256=runner_sha256,
    ):
        raise AcquisitionReplanningRunError("closed_root_collision")
    root = development_runner._open_frozen_root(
        readiness,
        entry,
        root_record,
        entry_index=entry_index,
    )
    episode_id = _text(trial.get("episode_id"), "episode")
    claim = _sha(trial.get("trial_claim_sha256"), "trial claim")
    seed = _integer(trial.get("seed"), "trial seed")
    assigned = _goal_kind(trial.get("assigned_intervention"))
    if store.inspect_episode_state(episode_id).status != "absent":
        raise AcquisitionReplanningRunError("trial_already_consumed")
    if not development_runner._trial_claim_is_available(registry, claim):
        raise AcquisitionReplanningRunError("trial_already_consumed")
    protected = development_runner._protected_digests(
        (
            readiness.context_plan_path,
            Path(args.profile_lineage),
            campaign_path,
            readiness.context_catalog_path,
            readiness.model_path,
            readiness.fit_summary_path,
            entry.state,
            entry.envelope,
            entry.profile,
            readiness.rom_path,
        )
    )
    adjacent_before = development_runner.rom_adjacent_artifacts(readiness.rom_path)
    campaign_claim = _sha(plan.get("campaign_claim_sha256"), "campaign claim")
    _ensure_campaign_root_reservations(
        registry,
        roots,
        campaign_id=campaign_id,
        source_commit=readiness.source.git_commit or "",
        runner_sha256=runner_sha256,
    )
    if development_runner._trial_claim_is_available(registry, campaign_claim):
        development_runner._write_trial_claim(
            registry,
            trial_claim_sha256=campaign_claim,
            execution_identity_sha256=campaign_id,
            source_commit=readiness.source.git_commit or "",
            runner_sha256=runner_sha256,
        )
    if development_runner._read_trial_claim(registry, campaign_claim) != {
        "execution_identity_sha256": campaign_id,
        "runner_sha256": runner_sha256,
        "schema": "pokemon.red.repeatable-goal-manager-trial-claim.v1",
        "source_commit": readiness.source.git_commit,
        "trial_claim_sha256": campaign_claim,
    }:
        raise AcquisitionReplanningRunError("campaign_claim_authentication")
    development_runner._write_trial_claim(
        registry,
        trial_claim_sha256=claim,
        execution_identity_sha256=execution_identity,
        source_commit=readiness.source.git_commit or "",
        runner_sha256=runner_sha256,
    )
    writer: Any | None = None
    sink: Any | None = None
    recorder: Any | None = None
    try:
        writer = store.begin_episode(episode_id)
        sink = development_runner.EpisodeTrajectorySink(
            writer,
            episode_id=episode_id,
            game_id="pokemon.mainline:red:gb:us:rev0",
            durable_writes=True,
        )
        sink.write_episode_header(
            metadata=_episode_metadata(
                readiness,
                plan=plan,
                root=root,
                assignment_id=claim,
                execution_identity_sha256=execution_identity,
                assigned_intervention=assigned,
            )
        )
        with development_runner.PyBoyAdapter(
            readiness.rom_path,
            watch=False,
            speed=None,
        ) as emulator:
            development_runner.require_pyboy_import_origins(readiness.runtime)
            emulator.load_state_bytes(root.capture.state_bytes)
            development_runner.require_pyboy_import_origins(readiness.runtime)
            frames = development_runner.WindowedFrameBudgetController(
                emulator,
                maximum_frames_per_window=MAX_FRAMES_PER_DECISION,
                maximum_total_frames=MAX_EPISODE_FRAMES,
            )
            reader = development_runner.PokemonRedStateReader(frames)
            runtime = development_runner.build_red_goal_context_runtime(
                profile=root.profile,
                capture=root.capture,
                emulator=frames,
                reader=reader,
            )
            frame_safe = development_runner.FrameSafeExecutor(
                frames,
                development_runner.DEFAULT_NEW_GAME_TIMING.controller_timing(),
            )
            snapshot_provider = (
                development_runner.PokemonRedObservationEncoder.from_state_reader(
                    reader
                )
            )
            recorder = development_runner.RecordingExecutor(
                delegate=frame_safe,
                snapshot_provider=snapshot_provider,
                sink=sink,
                episode_id=episode_id,
            )
            hard_actions = development_runner.HardCompositionActionLimiter(
                recorder,
                maximum_actions_per_decision=MAX_ACTIONS_PER_DECISION,
                maximum_episode_actions=MAX_EPISODE_ACTIONS,
            )
            actions = development_runner.CountingExecutor(hard_actions)
            meter = development_runner.CompositionIndependentBudgetMeter(
                hard_actions,
                frames,
            )
            trajectory = development_runner.GoalManagerTrajectoryObserver(
                episode_id=episode_id,
                root_lineage_id=root.assignment.root_lineage_id,
                partition="development",
                environment_id="pokemon.mainline:red:gb:us:rev0",
                actor="acquisition_replanning_mixed_policy",
                policy_id="red-acquisition-replanning-development-v1",
                collection_id=_text(plan.get("campaign_id"), "campaign identity"),
                assignment_id=claim,
                source_commit=readiness.source.git_commit or "",
                snapshot_provider=snapshot_provider,
                recorder=recorder,
                sink=sink,
                ordering_assignment_id=root.assignment.assignment_id,
            )
            policy = development_runner.ExploratoryGoalManagerPolicy(
                readiness.candidate.model,
                seed=seed,
            )
            observe = development_runner._live_observer(
                runtime=runtime,
                actions=actions,
                meter=meter,
                root=root,
            )
            result = run_acquisition_replanning_episode(
                observe=observe,
                assigned_intervention=assigned,
                policy=policy,
                trajectory=trajectory,
                budget_meter=meter,
            )
            if recorder.recording_failures:
                raise AcquisitionReplanningRunError("trajectory_durability")
            development_runner.require_pyboy_import_origins(readiness.runtime)
        development_runner.require_pyboy_import_origins(readiness.runtime)
        development_runner._require_unchanged(protected)
        if (
            development_runner.rom_adjacent_artifacts(readiness.rom_path)
            != adjacent_before
        ):
            raise AcquisitionReplanningRunError("protected_input_integrity")
        sink.record_event(
            development_runner.SparseEvent(
                event_id=f"{episode_id}:terminal",
                episode_id=episode_id,
                step_index=recorder.next_step_index,
                kind="terminal",
                payload={
                    "status": "complete",
                    "acquisition_replanning": cast(Any, result.public_dict()),
                },
            )
        )
        sink.finalize()
        summary = writer.complete()
        return {
            "schema": "pokemon.red.acquisition-replanning-execution-summary.v1",
            "status": "complete",
            "campaign_plan_sha256": campaign_sha256,
            "trial_index": args.trial_index,
            "assigned_intervention": assigned.value,
            "private_artifact": {
                "manifest_sha256": summary.manifest_sha256,
                "status": summary.status,
                "stream_records": dict(summary.stream_records),
                "total_records": summary.total_records,
            },
            "development": _public_development_summary(result),
            "teacher_queries": 0,
            "teacher_fallbacks": 0,
            "sealed_red_accesses": 0,
            "crystal_accesses": 0,
            "private_path_fields": 0,
        }
    except BaseException as error:
        if writer is not None:
            development_runner._retain_failure(
                writer,
                sink=sink,
                episode_id=episode_id,
                step_index=0 if recorder is None else recorder.next_step_index,
                failure_stage=(
                    error.stage
                    if isinstance(error, AcquisitionReplanningRunError)
                    else "acquisition_replanning_runtime"
                ),
            )
        raise


def _authenticated_campaign(
    args: argparse.Namespace,
    *,
    readiness: Any,
    runner_sha256: str,
    private_root_identity: str,
) -> tuple[Path, str, Mapping[str, object]]:
    campaign_path = development_runner._external_regular(
        args.campaign_plan,
        rom_path=readiness.rom_path,
    )
    payload = campaign_path.read_bytes()
    campaign_sha256 = hashlib.sha256(payload).hexdigest()
    if campaign_sha256 != _sha(args.expected_campaign_sha256, "campaign"):
        raise AcquisitionReplanningRunError("campaign_authentication")
    plan = _canonical_document(payload, subject="campaign")
    _validate_campaign(
        plan,
        readiness=readiness,
        runner_sha256=runner_sha256,
        expected_profile_lineage_sha256=_sha(
            args.expected_profile_lineage_sha256,
            "profile lineage",
        ),
        expected_private_root_identity_sha256=private_root_identity,
    )
    return campaign_path, campaign_sha256, plan


def _admit(
    args: argparse.Namespace,
    readiness: Any,
    runner_sha256: str,
    *,
    authenticated_campaign: tuple[Path, str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    if (
        args.expected_campaign_sha256 is None
        or args.expected_execution_identity_sha256 is not None
        or args.trial_index is not None
    ):
        raise AcquisitionReplanningRunError("mode_arguments")
    store, private_root_identity = development_runner._open_bound_private_root(
        args.private_root,
        rom_path=readiness.rom_path,
    )
    if authenticated_campaign is None:
        _campaign_path, campaign_sha256, plan = _authenticated_campaign(
            args,
            readiness=readiness,
            runner_sha256=runner_sha256,
            private_root_identity=private_root_identity,
        )
    else:
        _campaign_path, campaign_sha256, plan = authenticated_campaign
        _validate_campaign(
            plan,
            readiness=readiness,
            runner_sha256=runner_sha256,
            expected_profile_lineage_sha256=_sha(
                args.expected_profile_lineage_sha256,
                "profile lineage",
            ),
            expected_private_root_identity_sha256=private_root_identity,
        )
    registry = development_runner.open_fixed_account_claim_registry()
    campaign_claim = _sha(plan.get("campaign_claim_sha256"), "campaign claim")
    campaign_id = _sha(plan.get("campaign_id"), "campaign identity")
    if development_runner._read_trial_claim(registry, campaign_claim) != {
        "execution_identity_sha256": campaign_id,
        "runner_sha256": runner_sha256,
        "schema": "pokemon.red.repeatable-goal-manager-trial-claim.v1",
        "source_commit": readiness.source.git_commit,
        "trial_claim_sha256": campaign_claim,
    }:
        raise AcquisitionReplanningRunError("campaign_claim_authentication")
    roots = _roots(plan)
    _require_campaign_root_reservations(
        registry,
        roots,
        campaign_id=campaign_id,
        source_commit=readiness.source.git_commit or "",
        runner_sha256=runner_sha256,
    )
    complete = 0
    invalid = 0
    invalid_states: dict[str, int] = {}
    assigned_outcomes = 0
    learner_targets = 0
    primary_complete = 0
    verified_primary_replans = 0
    verified_primary_roots: set[int] = set()
    diagnostic_complete = 0
    manifests: set[str] = set()
    for expected_index, trial in enumerate(_trials(plan)):
        trial_index = _integer(trial.get("trial_index"), "trial index")
        if trial_index != expected_index:
            raise AcquisitionReplanningRunError("campaign_authentication")
        root_index = _integer(trial.get("root_index"), "root index")
        root = roots[root_index]
        claim = _sha(trial.get("trial_claim_sha256"), "trial claim")
        episode_id = _text(trial.get("episode_id"), "episode")
        execution = _sha(
            trial.get("execution_identity_sha256"),
            "execution identity",
        )
        claim_record = development_runner._read_trial_claim(registry, claim)
        if claim_record != {
            "execution_identity_sha256": execution,
            "runner_sha256": runner_sha256,
            "schema": "pokemon.red.repeatable-goal-manager-trial-claim.v1",
            "source_commit": readiness.source.git_commit,
            "trial_claim_sha256": claim,
        }:
            raise AcquisitionReplanningRunError("campaign_claim_authentication")
        state = store.inspect_episode_state(episode_id)
        if state.status != "complete":
            if state.status not in {
                "absent",
                "failed",
                "interrupted",
                "partial",
                "invalid",
            }:
                raise AcquisitionReplanningRunError(
                    "campaign_artifact_authentication"
                )
            invalid += 1
            invalid_states[state.status] = invalid_states.get(state.status, 0) + 1
            continue
        capture_id = _text(root.get("capture_id"), "capture identity")
        catalog_entry = readiness.candidate.catalog.entry(capture_id)
        assigned = _goal_kind(trial.get("assigned_intervention"))
        admitted = load_acquisition_replanning_episode(
            store.open_episode(episode_id),
            expected_campaign_id=_text(plan.get("campaign_id"), "campaign identity"),
            expected_trial_claim_sha256=claim,
            expected_episode_id=episode_id,
            expected_root_lineage_id=_text(
                root.get("root_lineage_id"),
                "root lineage",
            ),
            expected_seed=_integer(trial.get("seed"), "trial seed"),
            expected_execution_identity_sha256=execution,
            expected_context_catalog_sha256=(
                readiness.candidate.catalog.catalog_sha256
            ),
            expected_context_id=catalog_entry.context_id,
            expected_binding_manifest_sha256=_sha(
                root.get("binding_manifest_sha256"),
                "binding manifest",
            ),
            expected_state_sha256=_sha(root.get("state_sha256"), "state"),
            expected_envelope_sha256=_sha(
                root.get("envelope_sha256"),
                "envelope",
            ),
            expected_first_question_sha256=_sha(
                root.get("question_sha256"),
                "question",
            ),
            expected_first_policy_context_sha256=_sha(
                root.get("policy_context_sha256"),
                "policy context",
            ),
            expected_first_available_menu_sha256=_sha(
                root.get("available_menu_sha256"),
                "available menu",
            ),
            expected_assigned_intervention=assigned,
            expected_model=readiness.candidate.model,
            expected_source_commit=readiness.source.git_commit or "",
        )
        if admitted.dataset.manifest_sha256 in manifests:
            raise AcquisitionReplanningRunError("campaign_artifact_authentication")
        manifests.add(admitted.dataset.manifest_sha256)
        complete += 1
        assigned_outcomes += 1
        learner_targets += len(admitted.targets)
        if assigned is GoalKind.ACQUIRE_SPECIES:
            primary_complete += 1
            if (
                len(admitted.dataset.examples) == 2
                and admitted.dataset.examples[0].outcome_status.value == "succeeded"
                and admitted.dataset.examples[1].outcome_status.value == "succeeded"
                and admitted.dataset.examples[1].selected_kind
                is not GoalKind.ACQUIRE_SPECIES
                and admitted.dataset.examples[1].question.policy_context_sha256
                != admitted.dataset.examples[0].question.policy_context_sha256
                and admitted.dataset.examples[1].question.available_menu_sha256
                != admitted.dataset.examples[0].question.available_menu_sha256
            ):
                verified_primary_replans += 1
                verified_primary_roots.add(root_index)
        else:
            diagnostic_complete += 1
    if complete + invalid != ACQUISITION_REPLANNING_EPISODES:
        raise AcquisitionReplanningRunError("campaign_denominator_authentication")
    gate_passed = (
        primary_complete >= 4
        and verified_primary_replans >= 4
        and len(verified_primary_roots) >= 3
    )
    return {
        "schema": "pokemon.red.acquisition-replanning-admission.v1",
        "status": "fixed_denominator_admitted",
        "campaign_plan_sha256": campaign_sha256,
        "campaign_claim_sha256": campaign_claim,
        "planned_trials": 16,
        "complete_episodes": complete,
        "invalid_trials": invalid,
        "invalid_trial_states": dict(sorted(invalid_states.items())),
        "assigned_intervention_outcomes": assigned_outcomes,
        "learner_targets": learner_targets,
        "acquisition_first_complete_episodes": primary_complete,
        "verified_acquisition_replans": verified_primary_replans,
        "root_lineages_with_verified_acquisition_replan": len(
            verified_primary_roots
        ),
        "diagnostic_control_complete_episodes": diagnostic_complete,
        "diagnostic_controls_can_rescue_primary_gate": False,
        "feasibility_gate_passed": gate_passed,
        "unseen_comparison": False,
        "authority_promotion": False,
        "transfer_result": False,
        "teacher_queries": 0,
        "teacher_fallbacks": 0,
        "tracked_private_paths": 0,
        "tracked_private_identities": 0,
    }


def _root_consumption(root: Mapping[str, object]) -> str:
    return root_consumption_sha256(
        state_sha256=_sha(root.get("state_sha256"), "root state"),
        envelope_sha256=_sha(root.get("envelope_sha256"), "root envelope"),
    )


def _expected_root_claim(
    identity: str,
    *,
    campaign_id: str,
    source_commit: str,
    runner_sha256: str,
) -> dict[str, str]:
    return {
        "schema": "pokemon.red.fresh-composition-root-claim.v1",
        "root_consumption_sha256": identity,
        "execution_identity_sha256": campaign_id,
        "source_commit": source_commit,
        "runner_sha256": runner_sha256,
    }


def _root_is_available_or_reserved(
    registry: Path,
    root: Mapping[str, object],
    *,
    campaign_id: str,
    source_commit: str,
    runner_sha256: str,
) -> bool:
    identity = _root_consumption(root)
    if root_claim_is_available(registry, identity):
        return True
    try:
        claim = read_root_claim(registry, identity)
    except BaseException:
        return False
    return claim == _expected_root_claim(
        identity,
        campaign_id=campaign_id,
        source_commit=source_commit,
        runner_sha256=runner_sha256,
    )


def _ensure_campaign_root_reservations(
    registry: Path,
    roots: tuple[Mapping[str, object], ...],
    *,
    campaign_id: str,
    source_commit: str,
    runner_sha256: str,
) -> None:
    for root in roots:
        identity = _root_consumption(root)
        if root_claim_is_available(registry, identity):
            write_root_claim(
                registry,
                root_consumption_sha256=identity,
                execution_identity_sha256=campaign_id,
                source_commit=source_commit,
                runner_sha256=runner_sha256,
            )
        if read_root_claim(
            registry,
            identity,
        ) != _expected_root_claim(
            identity,
            campaign_id=campaign_id,
            source_commit=source_commit,
            runner_sha256=runner_sha256,
        ):
            raise AcquisitionReplanningRunError("root_claim_authentication")


def _require_campaign_root_reservations(
    registry: Path,
    roots: tuple[Mapping[str, object], ...],
    *,
    campaign_id: str,
    source_commit: str,
    runner_sha256: str,
) -> None:
    for root in roots:
        identity = _root_consumption(root)
        if read_root_claim(
            registry,
            identity,
        ) != _expected_root_claim(
            identity,
            campaign_id=campaign_id,
            source_commit=source_commit,
            runner_sha256=runner_sha256,
        ):
            raise AcquisitionReplanningRunError("root_claim_authentication")


def _episode_metadata(
    readiness: Any,
    *,
    plan: Mapping[str, object],
    root: Any,
    assignment_id: str,
    execution_identity_sha256: str,
    assigned_intervention: GoalKind,
) -> dict[str, object]:
    return {
        "policy": {
            "actor": "acquisition_replanning_mixed_policy",
            "policy_id": "red-acquisition-replanning-development-v1",
        },
        "split": {
            "partition": "development",
            "root_lineage_id": root.assignment.root_lineage_id,
        },
        "goal_manager": {
            "assignment_id": assignment_id,
            "binding_manifest_sha256": root.binding_manifest_sha256,
            "collection_id": _text(plan.get("campaign_id"), "campaign identity"),
            "context_catalog_sha256": readiness.candidate.catalog.catalog_sha256,
            "context_id": readiness.candidate.catalog.entry(
                root.entry.slot_id
            ).context_id,
            "envelope_sha256": root.capture.envelope_sha256,
            "execution_identity_sha256": execution_identity_sha256,
            "source_commit": readiness.source.git_commit,
            "state_sha256": root.capture.state_sha256,
        },
        "acquisition_replanning": {
            "assigned_intervention": assigned_intervention.value,
            "behavior_contract": acquisition_replanning_behavior_contract(),
            "first_decision_is_model_prediction": False,
            "learner_target_decision_indices": [1],
            "maximum_decisions": 2,
        },
    }


def _public_development_summary(
    result: AcquisitionReplanningRunResult,
) -> dict[str, object]:
    return {
        "schema": "pokemon.red.acquisition-replanning-public-summary.v1",
        "status": "durable_terminal",
        "assigned_intervention": result.assigned_intervention.value,
        "decisions": len(result.steps),
        "assigned_dispatches": min(1, len(result.steps)),
        "learner_targets": result.learner_targets,
        "actions_executed": sum(step.actions_executed for step in result.steps),
        "frames_executed": sum(step.frames_executed for step in result.steps),
        "model_sha256": result.model_sha256,
        "selected_goal_kinds": [step.selected_kind.value for step in result.steps],
        "stopped_reason": result.stopped_reason,
        "teacher_queries": 0,
        "teacher_fallbacks": 0,
        "tracked_private_paths": 0,
        "tracked_private_identities": 0,
    }


def _validate_campaign(
    plan: Mapping[str, object],
    *,
    readiness: Any,
    runner_sha256: str,
    expected_profile_lineage_sha256: str,
    expected_private_root_identity_sha256: str,
) -> None:
    expected_keys = {
        "behavior_contract",
        "campaign_claim_sha256",
        "campaign_id",
        "candidate",
        "context_plan_sha256",
        "development_runner_sha256",
        "evidence_contract",
        "execution_limits",
        "numpy_runtime_sha256",
        "private_root_identity_sha256",
        "profile_lineage_manifest_sha256",
        "roots",
        "runner_sha256",
        "runtime_sha256",
        "schema",
        "skill_manifest_sha256",
        "source_bundle_sha256",
        "source_commit",
        "trials",
    }
    if set(plan) != expected_keys or plan.get("schema") != CAMPAIGN_SCHEMA:
        raise AcquisitionReplanningRunError("campaign_authentication")
    identity = dict(plan)
    campaign_id = identity.pop("campaign_id", None)
    raw_trials = identity.get("trials")
    if not isinstance(raw_trials, list):
        raise AcquisitionReplanningRunError("campaign_authentication")
    stripped: list[dict[str, object]] = []
    for raw in raw_trials:
        trial = dict(_mapping(raw, "trial"))
        trial.pop("episode_id", None)
        trial.pop("execution_identity_sha256", None)
        trial.pop("trial_claim_sha256", None)
        stripped.append(trial)
    identity["trials"] = stripped
    if campaign_id != canonical_sha256(identity):
        raise AcquisitionReplanningRunError("campaign_authentication")
    if (
        plan.get("behavior_contract") != acquisition_replanning_behavior_contract()
        or plan.get("evidence_contract") != acquisition_replanning_evidence_contract()
        or plan.get("execution_limits") != _execution_limits()
        or plan.get("candidate") != development_runner._candidate_identity(readiness)
        or plan.get("context_plan_sha256") != readiness.context_plan_sha256
        or plan.get("development_runner_sha256") != readiness.runner_sha256
        or plan.get("numpy_runtime_sha256") != readiness.numpy_runtime_sha256
        or plan.get("private_root_identity_sha256")
        != expected_private_root_identity_sha256
        or plan.get("profile_lineage_manifest_sha256")
        != expected_profile_lineage_sha256
        or plan.get("runner_sha256") != runner_sha256
        or plan.get("runtime_sha256") != readiness.runtime.sha256
        or plan.get("skill_manifest_sha256") != readiness.skill_manifest_sha256
        or plan.get("source_bundle_sha256") != readiness.source_bundle_sha256
        or plan.get("source_commit") != readiness.source.git_commit
    ):
        raise AcquisitionReplanningRunError("campaign_authentication")
    roots = _roots(plan)
    trials = _trials(plan)
    if len(roots) != 4 or len(trials) != 16:
        raise AcquisitionReplanningRunError("campaign_authentication")
    derived_campaign_claim = canonical_sha256(
        {
            "roots": [
                {
                    "envelope_sha256": root.get("envelope_sha256"),
                    "state_sha256": root.get("state_sha256"),
                }
                for root in roots
            ],
            "schema": CAMPAIGN_CLAIM_SCHEMA,
        }
    )
    if plan.get("campaign_claim_sha256") != derived_campaign_claim:
        raise AcquisitionReplanningRunError("campaign_authentication")
    for index, validated_trial in enumerate(trials):
        root_index = index // 4
        offset = index % 4
        expected_assigned = SCHEDULE[offset].value
        claim = canonical_sha256(
            {"campaign_id": campaign_id, "schema": CLAIM_SCHEMA, "trial_index": index}
        )
        execution = canonical_sha256(
            {
                "assigned_intervention": expected_assigned,
                "campaign_id": campaign_id,
                "maximum_decisions": 2,
                "model_canonical_sha256": readiness.candidate.plan.model_canonical_sha256,
                "root_index": root_index,
                "schema": EXECUTION_SCHEMA,
                "seed": 20_000 + root_index * 100 + offset,
                "trial_claim_sha256": claim,
                "trial_index": index,
            }
        )
        if validated_trial != {
            "assigned_intervention": expected_assigned,
            "episode_id": f"red-acq-{campaign_id}-{index:02d}",
            "execution_identity_sha256": execution,
            "maximum_decisions": 2,
            "root_index": root_index,
            "seed": 20_000 + root_index * 100 + offset,
            "trial_claim_sha256": claim,
            "trial_index": index,
        }:
            raise AcquisitionReplanningRunError("campaign_authentication")


def _public_result(
    readiness: Any,
    *,
    runner_sha256: str,
    campaign_sha256: str,
    campaign_claim_sha256: str,
    profile_lineage_sha256: str,
    status: str,
    available_trials: int,
) -> dict[str, object]:
    return {
        "schema": "pokemon.red.acquisition-replanning-campaign-preflight.v1",
        "status": status,
        "campaign_plan_sha256": campaign_sha256,
        "campaign_claim_sha256": campaign_claim_sha256,
        "profile_lineage_manifest_sha256": profile_lineage_sha256,
        "source_commit": readiness.source.git_commit,
        "source_bundle_sha256": readiness.source_bundle_sha256,
        "runner_sha256": runner_sha256,
        "development_runner_sha256": readiness.runner_sha256,
        "runtime_sha256": readiness.runtime.sha256,
        "numpy_runtime_sha256": readiness.numpy_runtime_sha256,
        "skill_manifest_sha256": readiness.skill_manifest_sha256,
        "context_plan_sha256": readiness.context_plan_sha256,
        "model_canonical_sha256": readiness.candidate.plan.model_canonical_sha256,
        "model_file_sha256": readiness.candidate.plan.model_file_sha256,
        "fit_summary_file_sha256": readiness.candidate.fit_summary_sha256,
        "promotion_plan_sha256": readiness.candidate.plan.plan_sha256,
        "context_catalog_sha256": readiness.candidate.catalog.catalog_sha256,
        "registry_sha256": readiness.candidate.registry.registry_sha256,
        "rom_sha256": readiness.rom.sha256,
        "root_lineages": 4,
        "planned_trials": 16,
        "available_trials": available_trials,
        "root_ledger_identities_available": 4,
        "local_episode_identities_available": available_trials,
        "global_trial_identities_available": available_trials,
        "campaign_identity_available": True,
        "assigned_interventions": {
            "acquire_species": 8,
            "develop_team": 4,
            "explore": 4,
        },
        "maximum_controller_started_decisions_per_episode": 2,
        "maximum_actions_per_decision": MAX_ACTIONS_PER_DECISION,
        "maximum_frames_per_decision": MAX_FRAMES_PER_DECISION,
        "maximum_episode_actions": MAX_EPISODE_ACTIONS,
        "maximum_episode_frames": MAX_EPISODE_FRAMES,
        "first_decision_is_model_prediction": False,
        "learned_choice_decisions_after_intervention": 1,
        "root_selection_before_menu_inspection": True,
        "model_predictions": 0,
        "controller_actions": 0,
        "emulator_frames": 0,
        "episode_outcomes": 0,
        "model_fits": 0,
        "teacher_queries": 0,
        "teacher_fallbacks": 0,
        "sealed_red_accesses": 0,
        "crystal_accesses": 0,
        "tracked_private_paths": 0,
        "tracked_private_identities": 0,
    }


def _roots(plan: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    value = plan.get("roots")
    if not isinstance(value, list) or any(not isinstance(row, Mapping) for row in value):
        raise AcquisitionReplanningRunError("campaign_authentication")
    return tuple(cast(Mapping[str, object], row) for row in value)


def _trials(plan: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    value = plan.get("trials")
    if not isinstance(value, list) or any(not isinstance(row, Mapping) for row in value):
        raise AcquisitionReplanningRunError("campaign_authentication")
    return tuple(cast(Mapping[str, object], row) for row in value)


def _canonical_document(payload: bytes, *, subject: str) -> dict[str, object]:
    if not payload or len(payload) > _MAX_BYTES:
        raise AcquisitionReplanningRunError(f"{subject}_authentication")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise AcquisitionReplanningRunError(f"{subject}_authentication") from None
    if not isinstance(value, dict) or _canonical_line(value) != payload:
        raise AcquisitionReplanningRunError(f"{subject}_authentication")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _canonical_line(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "ascii"
    )


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AcquisitionReplanningRunError(f"{subject}_authentication")
    return cast(Mapping[str, object], value)


def _sha(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise AcquisitionReplanningRunError(f"{subject}_authentication")
    return value


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise AcquisitionReplanningRunError(f"{subject}_authentication")
    return value


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _execution_limits() -> dict[str, int]:
    return {
        "maximum_actions_per_decision": MAX_ACTIONS_PER_DECISION,
        "maximum_frames_per_decision": MAX_FRAMES_PER_DECISION,
        "maximum_episode_actions": MAX_EPISODE_ACTIONS,
        "maximum_episode_frames": MAX_EPISODE_FRAMES,
    }


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise AcquisitionReplanningRunError(f"{subject}_authentication")
    return value


def _goal_kind(value: object) -> GoalKind:
    if not isinstance(value, str):
        raise AcquisitionReplanningRunError("assigned_intervention_authentication")
    try:
        kind = GoalKind(value)
    except ValueError:
        raise AcquisitionReplanningRunError(
            "assigned_intervention_authentication"
        ) from None
    if kind not in set(SCHEDULE):
        raise AcquisitionReplanningRunError("assigned_intervention_authentication")
    return kind


def _failure(stage: str, *, mode: str) -> dict[str, object]:
    effects_not_attested = mode in {"execute", "admit"}
    result: dict[str, object] = {
        "schema": "pokemon.red.acquisition-replanning-campaign-preflight.v1",
        "status": (
            "execution_failed_effects_not_attested"
            if mode == "execute"
            else "admission_failed_offline_replay_not_attested"
            if mode == "admit"
            else "failed_without_prediction_or_action"
        ),
        "failed_stage": stage,
        "model_fits": 0,
        "teacher_queries": 0,
        "protected_access_status": "not_attested",
        "tracked_private_paths": 0,
        "tracked_private_identities": 0,
    }
    if not effects_not_attested:
        result.update(
            {
                "model_predictions": 0,
                "controller_actions": 0,
                "episode_outcomes": 0,
            }
        )
    elif mode == "admit":
        result["offline_policy_replays"] = "not_attested"
    return result


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        authenticated_campaign = None
        if args.mode == "admit":
            readiness, runner_sha256, authenticated_campaign = (
                _admission_readiness(args)
            )
            lineage: Mapping[str, object] = {}
        else:
            readiness, runner_sha256, lineage = _readiness(args)
        registry = development_runner.open_fixed_account_claim_registry()
        with development_runner.fixed_account_claim_registry_lease(
            registry,
            exclusive=args.mode == "execute",
        ):
            if args.mode == "freeze":
                result = _freeze(args, readiness, runner_sha256, lineage)
            elif args.mode == "preflight":
                result = _preflight(args, readiness, runner_sha256, lineage)
            elif args.mode == "execute":
                result = _execute(args, readiness, runner_sha256, lineage)
            else:
                result = _admit(
                    args,
                    readiness,
                    runner_sha256,
                    authenticated_campaign=authenticated_campaign,
                )
    except BaseException as error:
        stage = getattr(error, "stage", None)
        result = _failure(
            stage if isinstance(stage, str) and stage else "unexpected_failure",
            mode=args.mode,
        )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
