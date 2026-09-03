#!/usr/bin/env python3
"""Freeze the compact open-root Red calibration campaign without outcomes."""

# ruff: noqa: E402 -- attest and prefer the reviewed scripts directory first

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

import run_repeatable_goal_manager_development as development

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    root_consumption_sha256,
)
from pokemon_red_completion.multi_goal_calibration_plan import (
    CALIBRATION_ROOT_QUOTAS,
    CalibrationRootCandidate,
    MultiGoalCalibrationPlanError,
    MultiGoalCalibrationSchedule,
    build_multi_goal_calibration_schedule,
)
from pokemon_red_completion.provenance import canonical_sha256

CAMPAIGN_SCHEMA = "pokemon.red.multi-goal-calibration-campaign.v1"
CAMPAIGN_CONSUMPTION_SCHEMA = (
    "pokemon.red.multi-goal-calibration-campaign-consumption.v1"
)
TRIAL_CLAIM_SCHEMA = "pokemon.red.multi-goal-calibration-trial-claim.v1"
INVENTORY_RESULT_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-multi-goal-curriculum-lineage-inventory-2026-09-03.json"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class FreezeMultiGoalCalibrationError(RuntimeError):
    """A path-free failure while freezing the calibration denominator."""

    def __init__(self, stage: str) -> None:
        self.stage = stage if stage.replace("_", "").isalnum() else "unexpected_failure"
        super().__init__(self.stage)


@dataclass(frozen=True, slots=True)
class _Readiness:
    development: Any
    runner_sha256: str
    development_runner_sha256: str


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context-plan", type=Path, required=True)
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
    parser.add_argument("--expected-inventory-result-sha256", required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--campaign-plan", type=Path, required=True)
    return parser


def _readiness(args: argparse.Namespace) -> _Readiness:
    runner_path = Path(__file__).resolve()
    runner_sha256 = development._file_sha256(runner_path)
    development_path = (
        SCRIPTS_ROOT / "run_repeatable_goal_manager_development.py"
    ).resolve()
    raw_development_path = getattr(development, "__file__", None)
    if (
        runner_path.parent != SCRIPTS_ROOT.resolve()
        or runner_sha256 != _sha(args.expected_runner_sha256, "runner")
        or not isinstance(raw_development_path, str)
        or Path(raw_development_path).resolve(strict=True) != development_path
    ):
        raise FreezeMultiGoalCalibrationError("executable_attestation")
    development_sha256 = development._file_sha256(development_path)
    if development_sha256 != _sha(
        args.expected_development_runner_sha256,
        "development runner",
    ):
        raise FreezeMultiGoalCalibrationError("development_runner_attestation")
    inherited = development._readiness(
        argparse.Namespace(
            context_plan=args.context_plan,
            context_catalog=args.context_catalog,
            model=args.model,
            fit_summary=args.fit_summary,
            expected_source_commit=args.expected_source_commit,
            expected_source_bundle_sha256=args.expected_source_bundle_sha256,
            expected_runner_sha256=development_sha256,
            expected_runtime_sha256=args.expected_runtime_sha256,
            expected_numpy_runtime_sha256=args.expected_numpy_runtime_sha256,
            expected_skill_manifest_sha256=args.expected_skill_manifest_sha256,
            expected_context_plan_sha256=args.expected_context_plan_sha256,
            rom=args.rom,
        )
    )
    return _Readiness(
        development=inherited,
        runner_sha256=runner_sha256,
        development_runner_sha256=development_sha256,
    )


def _freeze(args: argparse.Namespace, readiness: _Readiness) -> dict[str, object]:
    inventory_result_sha256 = _sha(
        args.expected_inventory_result_sha256,
        "inventory result",
    )
    try:
        observed_inventory_sha256 = development._file_sha256(INVENTORY_RESULT_PATH)
    except OSError as error:
        raise FreezeMultiGoalCalibrationError("inventory_result_attestation") from error
    if observed_inventory_sha256 != inventory_result_sha256:
        raise FreezeMultiGoalCalibrationError("inventory_result_attestation")
    destination = development._new_external_file(
        args.campaign_plan,
        rom_path=readiness.development.rom_path,
    )
    _store, private_root_identity = development._open_bound_private_root(
        args.private_root,
        rom_path=readiness.development.rom_path,
    )
    claim_registry = open_fixed_account_claim_registry()
    inspected_by_slot: dict[str, Any] = {}
    candidates: list[CalibrationRootCandidate] = []
    target_kinds = {kind for kind, _count in CALIBRATION_ROOT_QUOTAS}
    adjacent_before = development.rom_adjacent_artifacts(
        readiness.development.rom_path
    )
    try:
        with fixed_account_claim_registry_lease(claim_registry, exclusive=False):
            for entry_index, entry in enumerate(readiness.development.entries):
                assignment = readiness.development.candidate.registry.assignment(
                    entry.slot_id
                )
                if assignment.partition != "train" or assignment.focus_kind not in target_kinds:
                    continue
                is_open = development._historical_root_is_open(
                    readiness.development,
                    entry,
                    claim_registry,
                )
                if not is_open:
                    continue
                inspected = development._inspect_root(
                    readiness.development,
                    entry,
                    entry_index=entry_index,
                )
                if inspected is None:
                    continue
                candidate = _candidate_from_root(inspected, claim_available=is_open)
                candidates.append(candidate)
                inspected_by_slot[candidate.slot_id] = inspected
    finally:
        if (
            development.rom_adjacent_artifacts(readiness.development.rom_path)
            != adjacent_before
            or development._file_sha256(INVENTORY_RESULT_PATH)
            != inventory_result_sha256
        ):
            raise FreezeMultiGoalCalibrationError("protected_input_integrity")

    try:
        schedule = build_multi_goal_calibration_schedule(tuple(candidates))
    except MultiGoalCalibrationPlanError as error:
        raise FreezeMultiGoalCalibrationError("action_free_root_inventory") from error
    selected_roots = tuple(inspected_by_slot[root.slot_id] for root in schedule.roots)
    plan = _compose_plan(
        readiness,
        schedule,
        selected_roots=selected_roots,
        private_root_identity=private_root_identity,
        inventory_result_sha256=inventory_result_sha256,
    )
    payload = development._canonical_line(plan)
    try:
        development._write_exclusive(destination, payload)
    except Exception as error:
        raise FreezeMultiGoalCalibrationError("campaign_freeze_write") from error
    return {
        **schedule.public_dict(),
        "schema": "pokemon.red.multi-goal-calibration-freeze.v1",
        "status": "compact_train_calibration_campaign_frozen",
        "campaign_plan_sha256": hashlib.sha256(payload).hexdigest(),
        "source_commit": readiness.development.source.git_commit,
        "source_bundle_sha256": readiness.development.source_bundle_sha256,
        "runner_sha256": readiness.runner_sha256,
        "inventory_result_sha256": inventory_result_sha256,
    }


def _candidate_from_root(
    root: Any,
    *,
    claim_available: bool,
) -> CalibrationRootCandidate:
    try:
        return CalibrationRootCandidate(
            slot_id=root.entry.slot_id,
            focus_kind=root.assignment.focus_kind,
            state_sha256=root.capture.state_sha256,
            envelope_sha256=root.capture.envelope_sha256,
            profile_sha256=root.profile_file_sha256,
            physical_root_sha256=root_consumption_sha256(
                state_sha256=root.capture.state_sha256,
                envelope_sha256=root.capture.envelope_sha256,
            ),
            available_goal_kinds=tuple(
                GoalKind(kind) for kind in root.available_goal_kinds
            ),
            claim_available=claim_available,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise FreezeMultiGoalCalibrationError("root_projection") from error


def _compose_plan(
    readiness: _Readiness,
    schedule: MultiGoalCalibrationSchedule,
    *,
    selected_roots: tuple[Any, ...],
    private_root_identity: str,
    inventory_result_sha256: str,
) -> dict[str, object]:
    if len(selected_roots) != len(schedule.roots):
        raise FreezeMultiGoalCalibrationError("schedule_root_join")
    roots = []
    for candidate, root in zip(schedule.roots, selected_roots, strict=True):
        if root.entry.slot_id != candidate.slot_id:
            raise FreezeMultiGoalCalibrationError("schedule_root_join")
        roots.append(
            {
                "partition": "train",
                "physical_root_sha256": candidate.physical_root_sha256,
                "root": development._private_root_record(root),
            }
        )
    base = readiness.development
    identity = {
        "candidate": development._candidate_identity(base),
        "context_plan_sha256": base.context_plan_sha256,
        "development_runner_sha256": readiness.development_runner_sha256,
        "inventory_result_sha256": inventory_result_sha256,
        "numpy_runtime_sha256": base.numpy_runtime_sha256,
        "outcome_objective": "selected-semantic-option-multioutcome-calibration-v1",
        "private_root_identity_sha256": private_root_identity,
        "roots": roots,
        "runner_sha256": readiness.runner_sha256,
        "runtime_sha256": base.runtime.sha256,
        "schedule_sha256": schedule.schedule_sha256,
        "schema": CAMPAIGN_SCHEMA,
        "skill_manifest_sha256": base.skill_manifest_sha256,
        "source_bundle_sha256": base.source_bundle_sha256,
        "source_commit": base.source.git_commit,
        "trials": [trial.private_dict() for trial in schedule.trials],
    }
    campaign_id = canonical_sha256(identity)
    return {
        **identity,
        "campaign_id": campaign_id,
        "campaign_consumption_sha256": canonical_sha256(
            {"campaign_id": campaign_id, "schema": CAMPAIGN_CONSUMPTION_SCHEMA}
        ),
        "trials": [
            {
                **trial.private_dict(),
                "episode_id": (
                    f"red-multigoal-cal-{campaign_id[:32]}-{trial.trial_ordinal:02d}"
                ),
                "trial_claim_sha256": canonical_sha256(
                    {
                        "campaign_id": campaign_id,
                        "schema": TRIAL_CLAIM_SCHEMA,
                        "trial_ordinal": trial.trial_ordinal,
                    }
                ),
            }
            for trial in schedule.trials
        ],
    }


def _sha(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise FreezeMultiGoalCalibrationError(f"{subject.replace(' ', '_')}_attestation")
    return value


def main() -> int:
    try:
        args = _parser().parse_args()
        result = _freeze(args, _readiness(args))
    except Exception as error:
        stage = (
            error.stage
            if isinstance(error, FreezeMultiGoalCalibrationError)
            else "unexpected_failure"
        )
        print(
            json.dumps(
                {
                    "schema": "pokemon.red.multi-goal-calibration-freeze-failure.v1",
                    "status": "failed_closed",
                    "failure_stage": stage,
                    "effects": "not_attested_on_failure",
                    "private_path_fields": 0,
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
