#!/usr/bin/env python3
"""Recover only invalid trials from one authenticated repeatable campaign.

The predecessor denominator is immutable.  This runner reconstructs all of
its questions under a new clean executable, proves that every identity-free
candidate row and permutation is unchanged, inherits measured outcomes, and
claims only predecessor failures.  A frozen successor is one-shot after any
controller input; it is never a retry of the consumed predecessor plan.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import permutations
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.party_development_outcome_campaign import (  # noqa: E402
    PartyDevelopmentOutcomeTrialAssignment,
)
from pokemon_red_completion.private_artifacts import open_private_root  # noqa: E402
from pokemon_red_completion.provenance import canonical_sha256  # noqa: E402
from pokemon_red_completion.scenario_outcomes import CandidateOutcome  # noqa: E402

_COLLECTION = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "run_repeatable_party_outcome_development.py")
)
_FITTER = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "fit_repeatable_party_outcome_model.py")
)

_SUCCESSOR_SCHEMA = "pokemon.red.repeatable-party-development-successor-frozen-plan.v1"
_SUCCESSOR_PLAN_SCHEMA = "pokemon.red.repeatable-party-development-successor-plan.v1"
_SUCCESSOR_KIND = "repeatable_party_outcome_development_successor"
_HEX = frozenset("0123456789abcdef")
_ASSIGNMENT_SEMANTIC_FIELDS = (
    "scenario_id",
    "root_lineage_id",
    "initial_state_sha256",
    "partition",
    "kind",
    "goal",
    "candidate_count",
    "candidate_order_sha256",
    "timing_offset_frames",
    "candidate_feature_values_public",
    "private_path_fields",
)


class RepeatablePartyOutcomeSuccessorError(RuntimeError):
    """Raised before a successor can change or repeat predecessor evidence."""


@dataclass(frozen=True, slots=True)
class _Reconstruction:
    source: Any
    source_bundle_sha256: str
    inventory_path: Path
    context_path: Path
    venue_path: Path
    prior_path: Path
    catalog_root: Path
    inventory_file_sha256: str
    context_file_sha256: str
    venue_file_sha256: str
    prior_file_sha256: str
    venue_registry: Any
    artifact_exclusions: tuple[Any, ...]
    rom_path: Path
    fingerprint: Any
    pool: tuple[Any, ...]
    capability_rejected_root_counts: Mapping[str, int]
    plan: Any
    selected: tuple[Any, ...]
    assignments: Mapping[str, tuple[PartyDevelopmentOutcomeTrialAssignment, ...]]


@dataclass(frozen=True, slots=True)
class _BoundPredecessor:
    pilot: Any
    plan: Mapping[str, object]
    dose: Any
    old_assignments: Mapping[tuple[str, int], PartyDevelopmentOutcomeTrialAssignment]
    current_assignments: Mapping[tuple[str, int], PartyDevelopmentOutcomeTrialAssignment]
    inherited_outcomes: Mapping[str, Mapping[int, CandidateOutcome]]
    claim_keys: tuple[tuple[str, int], ...]
    semantic_reconstruction_sha256: str


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--venue-prior-registry", type=Path, required=True)
    parser.add_argument("--prior-reservation-plan", type=Path, required=True)
    parser.add_argument("--catalog-root", type=Path, required=True)
    parser.add_argument("--predecessor-artifact", type=Path, required=True)
    parser.add_argument("--expected-predecessor-manifest-sha256", required=True)
    parser.add_argument("--expected-predecessor-plan-sha256", required=True)
    parser.add_argument("--expected-predecessor-source", required=True)
    parser.add_argument("--expected-predecessor-measured-trials", type=int, required=True)
    parser.add_argument("--expected-predecessor-invalid-trials", type=int, required=True)
    parser.add_argument("--private-artifact-root", type=Path, default=None)
    parser.add_argument("--out-plan", type=Path, default=None)
    parser.add_argument("--frozen-plan", type=Path, default=None)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--train-count", type=int, default=24)
    parser.add_argument("--development-count", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20260816)
    parser.add_argument("--completed-battles", type=int, default=1)
    parser.add_argument(
        "--battle-credit-protocol",
        choices=_COLLECTION["_BATTLE_CREDIT_PROTOCOL_IDS"],
        default=_COLLECTION["_HYBRID_BATTLE_CREDIT_PROTOCOL_ID"],
    )
    parser.add_argument(
        "--scenario-selection-protocol",
        choices=_COLLECTION["REPEATABLE_PARTY_SELECTION_PROTOCOLS"],
        default=_COLLECTION["BALANCED_KIND_GOAL_SELECTION_PROTOCOL"],
    )
    parser.add_argument("--maximum-timing-offset-frames", type=int, default=255)
    parser.add_argument(
        "--exclude-root-lineage-id",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--exclude-development-artifact",
        type=Path,
        action="append",
        default=[],
    )
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser


def _require_sha256(value: object, *, subject: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX for character in value)
    ):
        raise RepeatablePartyOutcomeSuccessorError(f"{subject} is not a SHA-256 digest")
    return value


def _trial_key(
    assignment: PartyDevelopmentOutcomeTrialAssignment,
) -> tuple[str, int]:
    return assignment.scenario_id, assignment.candidate_index


def _flatten_assignments(
    assignments: Mapping[str, tuple[PartyDevelopmentOutcomeTrialAssignment, ...]],
) -> tuple[PartyDevelopmentOutcomeTrialAssignment, ...]:
    return tuple(
        assignment
        for scenario_assignments in assignments.values()
        for assignment in scenario_assignments
    )


def _recover_candidate_order(
    candidate_count: int,
    expected_sha256: object,
) -> tuple[int, ...]:
    expected = _require_sha256(
        expected_sha256,
        subject="predecessor candidate-order digest",
    )
    matches = tuple(
        order
        for order in permutations(range(candidate_count))
        if canonical_sha256(list(order)) == expected
    )
    if len(matches) != 1:
        raise RepeatablePartyOutcomeSuccessorError(
            "predecessor candidate permutation is not uniquely recoverable"
        )
    return matches[0]


def _rebuild_predecessor_plan(
    args: argparse.Namespace,
    predecessor_plan: Mapping[str, object],
    pool: tuple[Any, ...],
) -> Any:
    old_assignments = predecessor_plan.get("assignments")
    seed = predecessor_plan.get("seed")
    if not isinstance(old_assignments, list) or type(seed) is not int:  # noqa: E721
        raise RepeatablePartyOutcomeSuccessorError(
            "predecessor semantic plan cannot be reconstructed"
        )
    partition_counts = Counter(
        item.get("partition") for item in old_assignments if isinstance(item, Mapping)
    )
    if (
        seed != args.seed
        or partition_counts
        != Counter(
            {
                "train": args.train_count,
                "development": args.development_count,
            }
        )
    ):
        raise RepeatablePartyOutcomeSuccessorError(
            "successor selection request differs from the predecessor"
        )
    rebuilt = []
    for old in old_assignments:
        if not isinstance(old, Mapping):
            raise RepeatablePartyOutcomeSuccessorError(
                "predecessor question is invalid"
            )
        candidate_count = old.get("candidate_count")
        timing = old.get("timing_offset_frames")
        if (
            type(candidate_count) is not int  # noqa: E721
            or candidate_count < 2
            or type(timing) is not int  # noqa: E721
            or not 0 <= timing <= args.maximum_timing_offset_frames
        ):
            raise RepeatablePartyOutcomeSuccessorError(
                "predecessor question randomization is invalid"
            )
        matches = tuple(
            item
            for item in pool
            if item.option.root_lineage_id == old.get("root_lineage_id")
            and item.option.initial_state_sha256 == old.get("initial_state_sha256")
            and item.option.partition.value == old.get("partition")
            and item.option.candidate_set.kind.value == old.get("kind")
            and item.option.candidate_set.goal.value == old.get("goal")
            and len(item.option.candidate_set.candidates) == candidate_count
        )
        if len(matches) != 1:
            raise RepeatablePartyOutcomeSuccessorError(
                "predecessor question "
                f"{old.get('scenario_id')!r} has {len(matches)} repaired-pool matches"
            )
        option = matches[0].option
        rebuilt.append(
            _COLLECTION["PartyDevelopmentScenarioAssignment"](
                scenario_id=old.get("scenario_id"),
                option_id=option.option_id,
                option_sha256=option.option_sha256,
                root_lineage_id=option.root_lineage_id,
                initial_state_sha256=option.initial_state_sha256,
                partition=option.partition,
                kind=option.candidate_set.kind,
                goal=option.candidate_set.goal,
                candidate_order=_recover_candidate_order(
                    candidate_count,
                    old.get("candidate_order_sha256"),
                ),
                timing_offset_frames=timing,
            )
        )
    return _COLLECTION["RepeatablePartyScenarioPlan"](
        seed=seed,
        assignments=tuple(rebuilt),
        selection_protocol=args.scenario_selection_protocol,
    )


def _reconstruct(
    args: argparse.Namespace,
    *,
    predecessor_plan: Mapping[str, object],
) -> _Reconstruction:
    source = _COLLECTION["detect_source_identity"](
        PROJECT_ROOT,
        include_untracked=True,
    )
    if source.git_commit is None:
        raise RepeatablePartyOutcomeSuccessorError(
            "successor reconstruction needs a committed source ancestor"
        )
    source_bundle = _COLLECTION["working_source_bundle_sha256"](PROJECT_ROOT)
    require_external = _COLLECTION["_require_external"]
    load_json = _COLLECTION["_load_json"]
    inventory_path = require_external(args.inventory, subject="inventory")
    context_path = require_external(args.context_catalog, subject="context catalog")
    venue_path = require_external(args.venue_prior_registry, subject="venue-prior registry")
    prior_path = require_external(args.prior_reservation_plan, subject="prior reservation plan")
    catalog_root = require_external(args.catalog_root, subject="catalog root")
    inventory_document, inventory_sha = load_json(inventory_path, subject="inventory")
    venue_document, venue_sha = load_json(venue_path, subject="venue-prior registry")
    prior_document, prior_sha = load_json(prior_path, subject="prior reservation plan")
    inventory = _COLLECTION["PartyDevelopmentCheckpointInventory"].from_private_dict(
        inventory_document
    )
    venue_registry = _COLLECTION[
        "PartyDevelopmentVenuePriorRegistry"
    ].from_private_dict(venue_document)
    prior_plan = _COLLECTION[
        "PartyDevelopmentQuestionReservationPlan"
    ].from_private_dict(prior_document)
    exclusions = tuple(
        _COLLECTION["_development_artifact_exclusion"](path)
        for path in args.exclude_development_artifact
    )
    rom_path = _COLLECTION["resolve_rom_path"](args.rom)
    fingerprint = _COLLECTION["verify_rom"](rom_path)
    artifact_roots = frozenset(
        root for exclusion in exclusions for root in exclusion.root_lineage_ids
    )
    excluded_roots = frozenset(
        (
            *prior_plan.excluded_root_lineage_ids,
            *args.exclude_root_lineage_id,
            *artifact_roots,
        )
    )
    excluded_states = frozenset(
        (
            *prior_plan.excluded_state_sha256,
            *(
                state
                for exclusion in exclusions
                for state in exclusion.initial_state_sha256
            ),
        )
    )
    pool, rejected = _COLLECTION["_build_option_pool"](
        inventory=inventory,
        context_catalog_payload=context_path.read_bytes(),
        venue_registry=venue_registry,
        catalog_root=catalog_root,
        rom_path=rom_path,
        excluded_roots=excluded_roots,
        excluded_states=excluded_states,
        source_commit=source.git_commit,
        source_bundle_sha256=source_bundle,
        completed_battles=args.completed_battles,
        battle_credit_protocol_id=args.battle_credit_protocol,
    )
    plan = _rebuild_predecessor_plan(args, predecessor_plan, pool)
    selected = _COLLECTION["_selected_runtimes"](plan, pool)
    assignments = _COLLECTION["_trial_assignments"](selected)
    return _Reconstruction(
        source=source,
        source_bundle_sha256=source_bundle,
        inventory_path=inventory_path,
        context_path=context_path,
        venue_path=venue_path,
        prior_path=prior_path,
        catalog_root=catalog_root,
        inventory_file_sha256=inventory_sha,
        context_file_sha256=hashlib.sha256(context_path.read_bytes()).hexdigest(),
        venue_file_sha256=venue_sha,
        prior_file_sha256=prior_sha,
        venue_registry=venue_registry,
        artifact_exclusions=exclusions,
        rom_path=rom_path,
        fingerprint=fingerprint,
        pool=pool,
        capability_rejected_root_counts=rejected,
        plan=plan,
        selected=selected,
        assignments=assignments,
    )


def _assignment_semantics(value: Mapping[str, object]) -> dict[str, object]:
    if any(field not in value for field in _ASSIGNMENT_SEMANTIC_FIELDS):
        raise RepeatablePartyOutcomeSuccessorError(
            "predecessor assignment lacks successor comparison fields"
        )
    return {field: value[field] for field in _ASSIGNMENT_SEMANTIC_FIELDS}


def _bind_predecessor(
    args: argparse.Namespace,
    reconstruction: _Reconstruction,
    *,
    pilot: Any,
    old_plan: Mapping[str, object],
    dose: Any,
) -> _BoundPredecessor:
    if dose.completed_battles != args.completed_battles:
        raise RepeatablePartyOutcomeSuccessorError(
            "successor changes the predecessor battle dose"
        )
    old_questions = old_plan.get("assignments")
    current_plan = reconstruction.plan.public_dict()
    current_questions = current_plan.get("assignments")
    if (
        not isinstance(old_questions, list)
        or not isinstance(current_questions, list)
        or len(old_questions) != len(current_questions)
    ):
        raise RepeatablePartyOutcomeSuccessorError(
            "successor question denominator differs from the predecessor"
        )
    for old, current in zip(old_questions, current_questions, strict=True):
        if not isinstance(old, Mapping) or not isinstance(current, Mapping):
            raise RepeatablePartyOutcomeSuccessorError(
                "successor predecessor question record is invalid"
            )
        old_semantics = _assignment_semantics(old)
        current_semantics = _assignment_semantics(current)
        if old_semantics != current_semantics:
            differing = tuple(
                field
                for field in _ASSIGNMENT_SEMANTIC_FIELDS
                if old_semantics[field] != current_semantics[field]
            )
            raise RepeatablePartyOutcomeSuccessorError(
                "successor changes predecessor question "
                f"{old.get('scenario_id')!r} fields {differing!r}"
            )

    old_assignments: dict[
        tuple[str, int], PartyDevelopmentOutcomeTrialAssignment
    ] = {}
    inherited: dict[str, dict[int, CandidateOutcome]] = {}
    claim_keys: list[tuple[str, int]] = []
    for record in pilot.outcome_records:
        old_assignment = _FITTER["_record_assignment"](record)
        key = _trial_key(old_assignment)
        if key in old_assignments:
            raise RepeatablePartyOutcomeSuccessorError(
                "predecessor repeats a candidate trial"
            )
        old_assignments[key] = old_assignment
        inherited.setdefault(key[0], {})[key[1]] = _FITTER["_candidate_outcome"](
            record,
            expected_assignment=old_assignment,
        )
    for record in pilot.failure_records:
        old_assignment = _FITTER["_record_assignment"](record)
        key = _trial_key(old_assignment)
        if key in old_assignments:
            raise RepeatablePartyOutcomeSuccessorError(
                "predecessor repeats a candidate trial"
            )
        old_assignments[key] = old_assignment
        _FITTER["_candidate_failure"](
            record,
            expected_assignment=old_assignment,
        )
        evidence = record.get("evidence")
        if not isinstance(evidence, Mapping) or evidence.get(
            "retryable_development_evidence"
        ) is not True:
            raise RepeatablePartyOutcomeSuccessorError(
                "predecessor failure is not declared recoverable development evidence"
            )
        claim_keys.append(key)

    current_values = _flatten_assignments(reconstruction.assignments)
    current_assignments = {_trial_key(item): item for item in current_values}
    expected_total = (
        args.expected_predecessor_measured_trials
        + args.expected_predecessor_invalid_trials
    )
    if (
        len(old_assignments) != expected_total
        or len(current_assignments) != expected_total
        or set(old_assignments) != set(current_assignments)
        or len(claim_keys) != args.expected_predecessor_invalid_trials
    ):
        raise RepeatablePartyOutcomeSuccessorError(
            "successor trial denominator differs from the predecessor"
        )

    semantic_rows = []
    for key in sorted(old_assignments):
        old = old_assignments[key]
        current = current_assignments[key]
        old_semantics = (
            old.ordinal,
            old.scenario_id,
            old.root_lineage_id,
            old.initial_state_sha256,
            old.partition,
            old.kind,
            old.goal,
            old.candidate_index,
            old.candidate_sha256,
            old.candidate_feature_sha256,
        )
        current_semantics = (
            current.ordinal,
            current.scenario_id,
            current.root_lineage_id,
            current.initial_state_sha256,
            current.partition,
            current.kind,
            current.goal,
            current.candidate_index,
            current.candidate_sha256,
            current.candidate_feature_sha256,
        )
        if old_semantics != current_semantics:
            raise RepeatablePartyOutcomeSuccessorError(
                "successor changes a predecessor candidate feature or identity"
            )
        semantic_rows.append(
            {
                "scenario_id": key[0],
                "candidate_index": key[1],
                "candidate_feature_sha256": current.candidate_feature_sha256,
                "predecessor_status": (
                    "invalid" if key in claim_keys else "measured"
                ),
            }
        )
    return _BoundPredecessor(
        pilot=pilot,
        plan=old_plan,
        dose=dose,
        old_assignments=old_assignments,
        current_assignments=current_assignments,
        inherited_outcomes=inherited,
        claim_keys=tuple(
            sorted(claim_keys, key=lambda key: current_assignments[key].ordinal)
        ),
        semantic_reconstruction_sha256=canonical_sha256(semantic_rows),
    )


def _input_sha256(reconstruction: _Reconstruction) -> dict[str, object]:
    return {
        "inventory": reconstruction.inventory_file_sha256,
        "context_catalog": reconstruction.context_file_sha256,
        "venue_prior_registry": reconstruction.venue_file_sha256,
        "prior_reservation_plan": reconstruction.prior_file_sha256,
        "excluded_development_artifact_manifests": sorted(
            item.manifest_sha256 for item in reconstruction.artifact_exclusions
        ),
    }


def _successor_plan_core(
    args: argparse.Namespace,
    reconstruction: _Reconstruction,
    predecessor: _BoundPredecessor,
) -> dict[str, object]:
    claims = [
        {
            "predecessor_assignment_sha256": (
                predecessor.old_assignments[key].assignment_sha256
            ),
            "predecessor_trial_id": predecessor.old_assignments[key].trial_id,
            "successor_assignment": predecessor.current_assignments[key].private_dict(),
        }
        for key in predecessor.claim_keys
    ]
    return {
        "schema": _SUCCESSOR_PLAN_SCHEMA,
        "predecessor_manifest_sha256": predecessor.pilot.manifest_sha256,
        "predecessor_plan_sha256": args.expected_predecessor_plan_sha256,
        "predecessor_source_commit": args.expected_predecessor_source,
        "predecessor_measured_trials": args.expected_predecessor_measured_trials,
        "predecessor_invalid_trials": args.expected_predecessor_invalid_trials,
        "predecessor_candidate_denominator": (
            args.expected_predecessor_measured_trials
            + args.expected_predecessor_invalid_trials
        ),
        "current_reconstruction_plan_sha256": reconstruction.plan.plan_sha256,
        "semantic_reconstruction_sha256": (
            predecessor.semantic_reconstruction_sha256
        ),
        "claimed_trial_count": len(claims),
        "claims": claims,
        "battle_credit_protocol": _COLLECTION["_battle_credit_protocol"](
            predecessor.dose.completed_battles,
            protocol_id=args.battle_credit_protocol,
        ),
        "dose": predecessor.dose.public_dict(),
        "teacher_queries": 0,
        "model_predictions": 0,
        "model_fits": 0,
        "retry_after_controller_input": False,
        "sealed_red_cases_opened": 0,
        "crystal_cases_opened": 0,
        "full_game_replays": 0,
        "private_path_fields": 0,
    }


def _frozen_document(
    args: argparse.Namespace,
    reconstruction: _Reconstruction,
    predecessor: _BoundPredecessor,
    plan_core: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema": _SUCCESSOR_SCHEMA,
        "active_lane": _COLLECTION["_DEVELOPMENT_LANE_ID"],
        "successor_plan": dict(plan_core),
        "successor_plan_sha256": canonical_sha256(plan_core),
        "source_commit": reconstruction.source.git_commit,
        "source_bundle_sha256": reconstruction.source_bundle_sha256,
        "rom_sha256": reconstruction.fingerprint.sha256,
        "input_file_sha256": _input_sha256(reconstruction),
        "scenario_selection_protocol": args.scenario_selection_protocol,
        "question_count": len(reconstruction.selected),
        "candidate_trial_denominator": sum(
            len(items) for items in reconstruction.assignments.values()
        ),
        "claimed_trial_count": len(predecessor.claim_keys),
        "controller_actions": 0,
        "teacher_queries": 0,
        "model_predictions": 0,
        "model_fits": 0,
        "authority_promoted": False,
        "sealed_red_cases_opened": 0,
        "crystal_cases_opened": 0,
        "full_game_replays": 0,
        "private_path_fields": 0,
    }


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.out_plan is not None and (args.frozen_plan is not None or args.execute):
        raise RepeatablePartyOutcomeSuccessorError(
            "successor writes its frozen plan separately from execution"
        )
    if args.execute and (args.frozen_plan is None or args.private_artifact_root is None):
        raise RepeatablePartyOutcomeSuccessorError(
            "successor execution needs a frozen plan and private artifact root"
        )
    if args.expected_predecessor_invalid_trials < 1:
        raise RepeatablePartyOutcomeSuccessorError(
            "successor needs at least one predecessor invalid trial"
        )
    pilot = _FITTER["_open_authenticated_pilot"](
        args.predecessor_artifact,
        expected_manifest_sha256=_require_sha256(
            args.expected_predecessor_manifest_sha256,
            subject="expected predecessor manifest",
        ),
        expected_measured_trials=args.expected_predecessor_measured_trials,
        expected_invalid_trials=args.expected_predecessor_invalid_trials,
    )
    old_plan, _old_inputs, dose = _FITTER["_require_plan_record"](
        pilot,
        expected_plan_sha256=_require_sha256(
            args.expected_predecessor_plan_sha256,
            subject="expected predecessor plan",
        ),
        expected_collection_source=args.expected_predecessor_source,
        expected_battle_credit_protocol=args.battle_credit_protocol,
        expected_selection_protocol=args.scenario_selection_protocol,
    )
    reconstruction = _reconstruct(args, predecessor_plan=old_plan)
    predecessor = _bind_predecessor(
        args,
        reconstruction,
        pilot=pilot,
        old_plan=old_plan,
        dose=dose,
    )
    plan_core = _successor_plan_core(args, reconstruction, predecessor)
    frozen = _frozen_document(args, reconstruction, predecessor, plan_core)
    frozen_document_sha256 = canonical_sha256(frozen)
    frozen_file_sha256: str | None = None
    if args.frozen_plan is not None:
        loaded, frozen_file_sha256 = _COLLECTION["_load_json"](
            _COLLECTION["_require_external"](
                args.frozen_plan,
                subject="successor frozen plan",
            ),
            subject="successor frozen plan",
        )
        if loaded != frozen:
            raise RepeatablePartyOutcomeSuccessorError(
                "successor reconstruction differs from its frozen plan"
            )
    if args.out_plan is not None:
        if reconstruction.source.worktree_dirty:
            raise RepeatablePartyOutcomeSuccessorError(
                "successor plan must be frozen from a clean published source"
            )
        frozen_file_sha256 = _COLLECTION["_write_frozen_plan"](
            args.out_plan,
            frozen,
        )
    receipt: dict[str, object] = {
        "schema": "pokemon.red.repeatable-party-development-successor-receipt.v1",
        "status": "ready" if not args.execute else "executing",
        "active_lane": _COLLECTION["_DEVELOPMENT_LANE_ID"],
        "source_commit": reconstruction.source.git_commit,
        "source_bundle_sha256": reconstruction.source_bundle_sha256,
        "rom": reconstruction.fingerprint.public_dict(),
        "input_file_sha256": _input_sha256(reconstruction),
        "predecessor_manifest_sha256": predecessor.pilot.manifest_sha256,
        "predecessor_plan_sha256": args.expected_predecessor_plan_sha256,
        "current_reconstruction_plan_sha256": reconstruction.plan.plan_sha256,
        "semantic_reconstruction_sha256": predecessor.semantic_reconstruction_sha256,
        "successor_plan_sha256": canonical_sha256(plan_core),
        "frozen_plan_document_sha256": frozen_document_sha256,
        "frozen_plan_file_sha256": frozen_file_sha256,
        "question_count": len(reconstruction.selected),
        "candidate_trial_denominator": len(predecessor.current_assignments),
        "inherited_measured_trials": args.expected_predecessor_measured_trials,
        "claimed_trial_count": len(predecessor.claim_keys),
        "scenario_pool": _COLLECTION["_pool_summary"](
            reconstruction.pool,
            capability_rejected_root_counts=(
                reconstruction.capability_rejected_root_counts
            ),
        ),
        "selection_summary": _COLLECTION["_selection_summary"](
            reconstruction.selected
        ),
        "battle_credit_protocol": _COLLECTION["_battle_credit_protocol"](
            predecessor.dose.completed_battles,
            protocol_id=args.battle_credit_protocol,
        ),
        "controller_actions": 0,
        "teacher_queries": 0,
        "model_predictions": 0,
        "model_fits": 0,
        "authority_promoted": False,
        "sealed_red_cases_opened": 0,
        "crystal_cases_opened": 0,
        "full_game_replays": 0,
        "private_path_fields": 0,
    }
    if not args.execute:
        receipt.update(
            {
                "successor_measured_trials": 0,
                "successor_invalid_trials": 0,
                "joined_complete_questions": 0,
                "joined_learner_update_eligible_questions": 0,
            }
        )
        return receipt
    if reconstruction.source.worktree_dirty:
        raise RepeatablePartyOutcomeSuccessorError(
            "successor execution requires its exact clean published source"
        )

    private_root = open_private_root(
        _COLLECTION["_require_external"](
            args.private_artifact_root,
            subject="successor artifact root",
        ),
        repository_root=PROJECT_ROOT,
    )
    # The plan digest owns one durable artifact namespace.  ``begin_artifact``
    # fsyncs that exclusive namespace before returning, so a process or power
    # interruption can never turn the same frozen successor into a second
    # controller attempt.
    artifact_id = (
        "repeatable-party-development-successor-"
        f"{canonical_sha256(plan_core)[:32]}"
    )
    writer = private_root.begin_artifact(artifact_id, kind=_SUCCESSOR_KIND)
    evolutions = _COLLECTION["evolution_graph"](reconstruction.rom_path.read_bytes())
    species_mapping = _COLLECTION["internal_to_dex"](
        reconstruction.rom_path.read_bytes()
    )
    outcomes_by_scenario = {
        scenario: dict(values)
        for scenario, values in predecessor.inherited_outcomes.items()
    }
    runtimes = {
        item.binding_question.scenario_id: item for item in reconstruction.selected
    }
    measured = invalid = controller_actions = frames_executed = 0
    with writer:
        writer.append(
            "plan",
            {
                "record_type": "repeatable_party_development_successor_plan",
                "successor_plan": dict(plan_core),
                "successor_plan_sha256": canonical_sha256(plan_core),
                "predecessor_manifest_sha256": predecessor.pilot.manifest_sha256,
                "predecessor_plan_sha256": args.expected_predecessor_plan_sha256,
                "current_reconstruction_plan": reconstruction.plan.public_dict(),
                "current_reconstruction_plan_sha256": reconstruction.plan.plan_sha256,
                "semantic_reconstruction_sha256": (
                    predecessor.semantic_reconstruction_sha256
                ),
                "dose": predecessor.dose.public_dict(),
                "source": reconstruction.source.public_dict(),
                "source_bundle_sha256": reconstruction.source_bundle_sha256,
                "rom_sha256": reconstruction.fingerprint.sha256,
                "inputs": _input_sha256(reconstruction),
                "battle_credit_protocol": _COLLECTION["_battle_credit_protocol"](
                    predecessor.dose.completed_battles,
                    protocol_id=args.battle_credit_protocol,
                ),
                "scenario_selection_protocol": args.scenario_selection_protocol,
                "sealed": False,
                "frozen_plan_document_sha256": frozen_document_sha256,
                "frozen_plan_file_sha256": frozen_file_sha256,
            },
            durable=True,
        )
        for key in predecessor.claim_keys:
            assignment = predecessor.current_assignments[key]
            runtime = runtimes.get(assignment.scenario_id)
            if runtime is None:
                raise RepeatablePartyOutcomeSuccessorError(
                    "successor claim lost its reconstructed question"
                )
            scenario_outcomes = outcomes_by_scenario.setdefault(
                assignment.scenario_id,
                {},
            )
            try:
                binding = _COLLECTION["bind_red_party_development_outcome_trial"](
                    runtime.binding_question,
                    runtime.menu,
                    assignment,
                    party=runtime.snapshot.party,
                    venue_question_trainee=runtime.venue_question_trainee,
                    training_venues=_COLLECTION["_TRAINING_VENUES"],
                    evolutions=evolutions,
                    internal_to_national=species_mapping,
                    dose=predecessor.dose,
                )
                measurement = _COLLECTION["_execute_trial"](
                    runtime=runtime,
                    assignment=assignment,
                    binding=binding,
                    rom_path=reconstruction.rom_path,
                    evolutions=evolutions,
                    venue_registry=reconstruction.venue_registry,
                    dose=predecessor.dose,
                    source_commit=reconstruction.source.git_commit,
                    source_bundle_sha256=reconstruction.source_bundle_sha256,
                    watch=args.watch,
                    battle_credit_protocol_id=args.battle_credit_protocol,
                )
                scenario_outcomes[assignment.candidate_index] = measurement.outcome
                measured += 1
                controller_actions += measurement.controller_actions
                frames_executed += measurement.frames_executed
                writer.append(
                    "outcomes",
                    {
                        "record_type": "repeatable_party_candidate_outcome",
                        "assignment": assignment.private_dict(),
                        "evidence": dict(measurement.private_evidence),
                        "outcome": {
                            "status": measurement.outcome.status.value,
                            "criterion_values": list(
                                measurement.outcome.criterion_values
                            ),
                            "evidence_sha256": measurement.outcome.evidence_sha256,
                        },
                    },
                )
            except Exception as error:
                failed, evidence = _COLLECTION["_invalid_outcome"](error)
                scenario_outcomes[assignment.candidate_index] = failed
                invalid += 1
                writer.append(
                    "failures",
                    {
                        "record_type": "repeatable_party_candidate_failure",
                        "assignment": assignment.private_dict(),
                        "evidence": evidence,
                    },
                )

        examples = _COLLECTION["_assemble_examples"](
            reconstruction.selected,
            outcomes_by_scenario,
        )
        prospective = _COLLECTION[
            "PartyDevelopmentProspectiveCatalog"
        ].freeze(
            tuple(item.binding_question.binding for item in reconstruction.selected)
        )
        audit = _COLLECTION["audit_party_development_outcome_catalog"](
            examples,
            prospective_catalog=prospective,
            policy=_COLLECTION["PartyDevelopmentReadinessPolicy"](
                minimum_train_examples=args.train_count,
                minimum_development_examples=args.development_count,
                minimum_goals_per_partition=2,
                minimum_candidate_count_observed=3,
                minimum_health_bins=2,
                minimum_pp_bins=1,
                minimum_survival_bins=2,
                minimum_evolution_route_kinds=2,
                minimum_semantic_menus_per_partition=min(
                    3,
                    args.development_count,
                ),
                require_complete_venue_priors=False,
            ),
        )
        writer.append(
            "evaluation",
            {
                "record_type": "repeatable_party_development_successor_audit",
                "audit": audit.public_dict(),
                "inherited_measured_trials": args.expected_predecessor_measured_trials,
                "claimed_trials": len(predecessor.claim_keys),
                "model_fit": False,
                "authority_promoted": False,
            },
        )

    complete_questions = sum(item.fully_measured for item in examples)
    eligible_questions = sum(item.learner_update_eligible for item in examples)
    partition_eligible = Counter(
        item.partition.value for item in examples if item.learner_update_eligible
    )
    receipt.update(
        {
            "status": "complete" if invalid == 0 else "complete_with_invalid_trials",
            "artifact": writer.summary.public_dict(),
            "dose": predecessor.dose.public_dict(),
            "successor_measured_trials": measured,
            "successor_invalid_trials": invalid,
            "joined_measured_trials": (
                args.expected_predecessor_measured_trials + measured
            ),
            "joined_complete_questions": complete_questions,
            "joined_learner_update_eligible_questions": eligible_questions,
            "joined_partition_eligible_questions": dict(
                sorted(partition_eligible.items())
            ),
            "controller_actions": controller_actions,
            "frames_executed": frames_executed,
            "audit": audit.public_dict(),
        }
    )
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        result = _run(parser.parse_args(argv))
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        parser.error(f"repeatable party successor failed closed: {error}")
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
