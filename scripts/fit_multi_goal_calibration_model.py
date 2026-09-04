#!/usr/bin/env python3
"""Fit one Red semantic-goal update from the fixed calibration campaign."""

# ruff: noqa: E402 -- the reviewed scripts directory must win import resolution

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import uuid
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

import run_multi_goal_calibration_trial as trial_runner

from pokemon_red_completion.goal_manager import GoalKind, GoalManagerExample
from pokemon_red_completion.goal_manager_dataset import (
    load_assigned_goal_manager_episode,
)
from pokemon_red_completion.goal_manager_model import (
    GoalManagerLinearModel,
    canonical_goal_manager_model_sha256,
)
from pokemon_red_completion.goal_manager_outcome_learning import (
    outcome_update_configuration,
)
from pokemon_red_completion.goal_manager_trajectory import (
    load_goal_manager_episode,
)
from pokemon_red_completion.multi_goal_calibration_admission import (
    AdmittedMultiGoalCalibrationOutcome,
    admit_multi_goal_calibration_episode,
)
from pokemon_red_completion.multi_goal_calibration_learning import (
    admit_multi_goal_calibration_train_set,
    fit_multi_goal_calibration_train_set,
)
from pokemon_red_completion.provenance import canonical_sha256

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ELIGIBLE_TRIALS = (1, 2, 3, 4, 6, 7, 8)
_EXCLUDED_TRIALS = (0, 5)
_EXPECTED_KINDS = (
    GoalKind.DEVELOP_TEAM,
    GoalKind.DEVELOP_TEAM,
    GoalKind.ADVANCE_STORY,
    GoalKind.EVOLVE_SPECIES,
    GoalKind.MANAGE_STORAGE,
    GoalKind.ADVANCE_STORY,
    GoalKind.MANAGE_STORAGE,
)
_GUARD_KINDS = {
    GoalKind.ACQUIRE_SPECIES,
    GoalKind.EVOLVE_SPECIES,
    GoalKind.ADVANCE_STORY,
}


class MultiGoalCalibrationFitRunError(RuntimeError):
    """A path-free failure while authenticating or fitting the campaign."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context-plan", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--fit-summary", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--expected-fit-runner-sha256", required=True)
    parser.add_argument("--expected-trial-runner-sha256", required=True)
    parser.add_argument("--expected-freezer-sha256", required=True)
    parser.add_argument("--expected-development-runner-sha256", required=True)
    parser.add_argument("--expected-runtime-sha256", required=True)
    parser.add_argument("--expected-numpy-runtime-sha256", required=True)
    parser.add_argument("--expected-skill-manifest-sha256", required=True)
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--expected-inventory-result-sha256", required=True)
    parser.add_argument("--expected-campaign-sha256", required=True)
    parser.add_argument("--rom", type=Path, default=None)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--campaign-plan", type=Path, required=True)
    parser.add_argument("--out-model", type=Path, required=True)
    parser.add_argument("--out-summary", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = _run(args)
    except BaseException as error:
        stage = (
            error.stage
            if isinstance(error, MultiGoalCalibrationFitRunError)
            else "unexpected_failure"
        )
        print(
            json.dumps(
                {
                    "schema": "pokemon.red.multi-goal-calibration-fit-failure.v1",
                    "status": "failed_closed",
                    "failure_stage": stage,
                    "model_fits": 0,
                    "authority_delta": 0,
                    "private_path_fields": 0,
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _run(args: argparse.Namespace) -> dict[str, object]:
    fit_runner_sha256 = _file_sha256(Path(__file__).resolve())
    trial_runner_path = SCRIPTS_ROOT / "run_multi_goal_calibration_trial.py"
    trial_runner_sha256 = _file_sha256(trial_runner_path)
    if (
        fit_runner_sha256 != _sha(args.expected_fit_runner_sha256)
        or trial_runner_sha256 != _sha(args.expected_trial_runner_sha256)
        or Path(trial_runner.__file__).resolve(strict=True)
        != trial_runner_path.resolve(strict=True)
    ):
        raise MultiGoalCalibrationFitRunError("executable_attestation")

    trial_args = argparse.Namespace(
        mode="admit",
        context_plan=args.context_plan,
        context_catalog=args.context_catalog,
        model=args.model,
        fit_summary=args.fit_summary,
        expected_source_commit=args.expected_source_commit,
        expected_source_bundle_sha256=args.expected_source_bundle_sha256,
        expected_runner_sha256=args.expected_trial_runner_sha256,
        expected_freezer_sha256=args.expected_freezer_sha256,
        expected_development_runner_sha256=args.expected_development_runner_sha256,
        expected_runtime_sha256=args.expected_runtime_sha256,
        expected_numpy_runtime_sha256=args.expected_numpy_runtime_sha256,
        expected_skill_manifest_sha256=args.expected_skill_manifest_sha256,
        expected_context_plan_sha256=args.expected_context_plan_sha256,
        expected_inventory_result_sha256=args.expected_inventory_result_sha256,
        expected_campaign_sha256=args.expected_campaign_sha256,
        rom=args.rom,
        private_root=args.private_root,
        campaign_plan=args.campaign_plan,
        trial_ordinal=0,
    )
    readiness = trial_runner._readiness(trial_args)
    _campaign_path, campaign, store = trial_runner._load_campaign(trial_args, readiness)
    if (
        len(campaign.trials) != 9
        or tuple(campaign.trials[index].selected_goal_kind for index in _ELIGIBLE_TRIALS)
        != _EXPECTED_KINDS
    ):
        raise MultiGoalCalibrationFitRunError("campaign_denominator")

    model_destination = _new_private_output(args.out_model, args.private_root)
    summary_destination = _new_private_output(args.out_summary, args.private_root)
    if model_destination == summary_destination:
        raise MultiGoalCalibrationFitRunError("output_collision")

    registry_path = trial_runner.open_fixed_account_claim_registry()
    with trial_runner.fixed_account_claim_registry_lease(registry_path, exclusive=True):
        outcomes = tuple(
            _admit_outcome(
                trial_args,
                readiness,
                registry_path,
                trial_ordinal=trial_ordinal,
            )
            for trial_ordinal in _ELIGIBLE_TRIALS
        )
        train_set = admit_multi_goal_calibration_train_set(outcomes)
        guard_winners, guard_menus, guard_roster_sha256 = _guard_sets(
            readiness,
            store,
        )
        fitted = fit_multi_goal_calibration_train_set(
            readiness.development.candidate.model,
            train_set,
            guard_winners=guard_winners,
            guard_menus=guard_menus,
        )

    model_payload = _canonical_line(fitted.update.model.to_dict())
    reloaded = GoalManagerLinearModel.from_dict(json.loads(model_payload))
    if reloaded.to_dict() != fitted.update.model.to_dict():
        raise MultiGoalCalibrationFitRunError("model_round_trip")
    candidate_sha256 = canonical_goal_manager_model_sha256(reloaded)
    campaign_roster_sha256 = canonical_sha256(
        {
            "schema": "pokemon.red.multi-goal-calibration-fit-roster.v1",
            "eligible_trials": list(_ELIGIBLE_TRIALS),
            "excluded_trials": list(_EXCLUDED_TRIALS),
            "episode_manifest_sha256s": list(train_set.manifest_sha256s),
        }
    )
    summary = {
        "schema": "pokemon.red.multi-goal-calibration-fit-summary.v1",
        "status": "train_only_calibration_fit_complete",
        "source_commit": readiness.development.source.git_commit,
        "source_bundle_sha256": readiness.development.source_bundle_sha256,
        "fit_runner_sha256": fit_runner_sha256,
        "trial_runner_sha256": trial_runner_sha256,
        "campaign_plan_sha256": campaign.plan_sha256,
        "campaign_roster_sha256": campaign_roster_sha256,
        "base_model_canonical_sha256": canonical_goal_manager_model_sha256(
            readiness.development.candidate.model
        ),
        "candidate_model_canonical_sha256": candidate_sha256,
        "candidate_model_file_sha256": hashlib.sha256(model_payload).hexdigest(),
        "configuration": outcome_update_configuration(),
        "fit": fitted.public_dict(),
        "guard_roster_sha256": guard_roster_sha256,
        "same_bank_calibration_only": True,
        "promotion_authorized": False,
        "authority_delta": 0,
        "crystal_accesses": 0,
        "teacher_queries": 0,
        "private_path_fields": 0,
    }
    summary_payload = _canonical_line(summary)
    _publish_private(model_destination, model_payload)
    _publish_private(summary_destination, summary_payload)
    return {
        "schema": "pokemon.red.multi-goal-calibration-fit-result.v1",
        "status": "train_only_calibration_fit_complete",
        "campaign_plan_sha256": campaign.plan_sha256,
        "campaign_roster_sha256": campaign_roster_sha256,
        "base_model_canonical_sha256": summary["base_model_canonical_sha256"],
        "candidate_model_canonical_sha256": candidate_sha256,
        "targets": len(train_set.rows),
        "roots": len(train_set.root_lineages),
        "positive_targets": 4,
        "negative_targets": 3,
        "training_loss_before": fitted.update.before.weighted_binary_cross_entropy,
        "training_loss_after": fitted.update.after.weighted_binary_cross_entropy,
        "maximum_guard_menu_kl": fitted.maximum_guard_menu_kl,
        "promotion_authorized": False,
        "authority_delta": 0,
        "crystal_accesses": 0,
        "teacher_queries": 0,
        "private_path_fields": 0,
    }


def _admit_outcome(
    args: argparse.Namespace,
    readiness: trial_runner._Readiness,
    registry_path: Path,
    *,
    trial_ordinal: int,
) -> AdmittedMultiGoalCalibrationOutcome:
    args.trial_ordinal = trial_ordinal
    receipt = trial_runner._admit(args, readiness, registry_path)
    _campaign_path, campaign, store = trial_runner._load_campaign(args, readiness)
    trial = campaign.trials[trial_ordinal]
    root_record = campaign.roots[trial.root_ordinal].record
    entry_index = root_record.get("entry_index")
    if type(entry_index) is not int or not 0 <= entry_index < len(readiness.development.entries):
        raise MultiGoalCalibrationFitRunError("campaign_authentication")
    entry = readiness.development.entries[entry_index]
    context_entry = readiness.development.candidate.catalog.entry(entry.slot_id)
    claim = trial_runner.development._read_trial_claim(
        registry_path,
        trial.trial_claim_sha256,
    )
    claim_source_commit = claim.get("source_commit")
    claim_runner_sha256 = claim.get("runner_sha256")
    if not isinstance(claim_source_commit, str) or not isinstance(claim_runner_sha256, str):
        raise MultiGoalCalibrationFitRunError("trial_claim_authentication")
    admitted = admit_multi_goal_calibration_episode(
        store.open_episode(trial.episode_id),
        expected_episode_id=trial.episode_id,
        expected_campaign_id=campaign.campaign_id,
        expected_trial_claim_sha256=trial.trial_claim_sha256,
        expected_execution_identity_sha256=campaign.trial_execution_identity(
            trial_ordinal,
            claim_runner_sha256,
        ),
        expected_root_lineage_id=str(root_record["root_lineage_id"]),
        expected_context_catalog_sha256=(
            readiness.development.candidate.catalog.catalog_sha256
        ),
        expected_context_id=context_entry.context_id,
        expected_binding_manifest_sha256=str(root_record["binding_manifest_sha256"]),
        expected_state_sha256=str(root_record["state_sha256"]),
        expected_envelope_sha256=str(root_record["envelope_sha256"]),
        expected_question_sha256=str(root_record["question_sha256"]),
        expected_policy_context_sha256=str(root_record["policy_context_sha256"]),
        expected_available_menu_sha256=str(root_record["available_menu_sha256"]),
        expected_selected_available_ordinal=trial.selected_candidate_index,
        expected_selected_goal_kind=trial.selected_goal_kind,
        expected_source_commit=claim_source_commit,
        expected_trial_ordinal=trial_ordinal,
    )
    public = receipt.get("admitted_outcome")
    if not isinstance(public, Mapping) or public != admitted.public_dict():
        raise MultiGoalCalibrationFitRunError("admission_reconstruction")
    loaded = load_goal_manager_episode(store.open_episode(trial.episode_id))
    if loaded != admitted.dataset:
        raise MultiGoalCalibrationFitRunError("admission_reconstruction")
    return admitted


def _guard_sets(
    readiness: trial_runner._Readiness,
    store: object,
) -> tuple[tuple[GoalManagerExample, ...], tuple[GoalManagerExample, ...], str]:
    registry = readiness.development.candidate.registry
    catalog = readiness.development.candidate.catalog
    winners: list[GoalManagerExample] = []
    menus: list[GoalManagerExample] = []
    manifests: list[str] = []
    open_episode = getattr(store, "open_episode", None)
    if not callable(open_episode):
        raise MultiGoalCalibrationFitRunError("guard_set_authentication")
    for slot in registry.slots:
        if slot.partition != "train":
            continue
        assignment = registry.assignment(slot.slot_id)
        reader = open_episode(assignment.episode_id)
        loaded = load_assigned_goal_manager_episode(
            reader,
            assignment,
            context_catalog=catalog,
        )
        manifests.append(reader.manifest_sha256)
        menus.extend(loaded.examples)
        if slot.focus_kind in _GUARD_KINDS:
            winners.extend(loaded.examples)
    if (
        len(menus) != 54
        or len(winners) != 18
        or len(manifests) != 54
        or len(set(manifests)) != 54
    ):
        raise MultiGoalCalibrationFitRunError("guard_set_authentication")
    return (
        tuple(winners),
        tuple(menus),
        canonical_sha256(
            {
                "schema": "pokemon.red.multi-goal-calibration-guard-roster.v1",
                "episode_manifest_sha256s": manifests,
            }
        ),
    )


def _new_private_output(path: Path, root: Path) -> Path:
    resolved_root = root.resolve(strict=True)
    resolved = path.resolve(strict=False)
    if resolved.parent != resolved_root or resolved.exists():
        raise MultiGoalCalibrationFitRunError("private_output")
    return resolved


def _publish_private(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.partial")
    descriptor = -1
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        if os.write(descriptor, payload) != len(payload):
            raise OSError("short write")
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.link(temporary, path, follow_symlinks=False)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        raise MultiGoalCalibrationFitRunError("private_output") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        with suppress(FileNotFoundError):
            temporary.unlink()


def _file_sha256(path: Path) -> str:
    try:
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise OSError
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        raise MultiGoalCalibrationFitRunError("executable_attestation") from None


def _sha(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise MultiGoalCalibrationFitRunError("executable_attestation")
    return value


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
