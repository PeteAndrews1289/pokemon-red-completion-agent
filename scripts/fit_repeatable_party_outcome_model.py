#!/usr/bin/env python3
"""Fit one Red party-development model from one authenticated repeatable pilot.

The pilot artifact contains outcomes but deliberately omits private candidate
feature values.  This runner reconstructs the exact frozen menus from the
authenticated cartridge inputs, checks every trial assignment and evidence
digest, fits on train roots only, and compares the base and updated scorers once
on untouched development roots.  It never opens sealed Red or Crystal data and
never grants the fitted scorer live authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import runpy
import stat
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.party_development_catalog import (  # noqa: E402
    PartyDevelopmentProspectiveCatalog,
)
from pokemon_red_completion.party_development_inventory import (  # noqa: E402
    PartyDevelopmentCheckpointInventory,
)
from pokemon_red_completion.party_development_outcome_campaign import (  # noqa: E402
    PartyDevelopmentOutcomeDose,
    PartyDevelopmentOutcomeTrialAssignment,
)
from pokemon_red_completion.party_development_outcome_dataset import (  # noqa: E402
    PartyDevelopmentReadinessPolicy,
    audit_party_development_outcome_catalog,
)
from pokemon_red_completion.party_development_outcome_learning import (  # noqa: E402
    PartyDevelopmentOutcomeLearningCycle,
    canonical_party_development_outcome_model_sha256,
    load_party_development_outcome_model,
    run_party_development_outcome_learning_cycle,
)
from pokemon_red_completion.party_development_question_reservations import (  # noqa: E402
    PartyDevelopmentQuestionReservationPlan,
)
from pokemon_red_completion.party_development_scenarios import (  # noqa: E402
    select_repeatable_party_scenarios,
)
from pokemon_red_completion.party_development_venue_priors import (  # noqa: E402
    PartyDevelopmentVenuePriorRegistry,
)
from pokemon_red_completion.private_artifacts import (  # noqa: E402
    PRIVATE_ARTIFACT_SCHEMA_VERSION,
    PRIVATE_JSON_ARTIFACT_FORMAT,
    open_private_root,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    canonical_sha256,
    detect_source_identity,
    require_published_source,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402
from pokemon_red_completion.scenario_outcomes import (  # noqa: E402
    CandidateOutcome,
    OutcomeEvidenceStatus,
    ScenarioOutcomeExample,
)

_COLLECTION_RUNNER = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "run_repeatable_party_outcome_development.py")
)
_build_option_pool = _COLLECTION_RUNNER["_build_option_pool"]
_selected_runtimes = _COLLECTION_RUNNER["_selected_runtimes"]
_trial_assignments = _COLLECTION_RUNNER["_trial_assignments"]
_assemble_examples = _COLLECTION_RUNNER["_assemble_examples"]
_battle_credit_protocol = _COLLECTION_RUNNER["_battle_credit_protocol"]
_development_artifact_exclusion = _COLLECTION_RUNNER[
    "_development_artifact_exclusion"
]

_FIT_EPOCHS = 200
_FIT_LEARNING_RATE = 0.01
_FIT_PRIOR_L2 = 0.1
_MAXIMUM_TIMING_OFFSET_FRAMES = 255
_EXPECTED_TRAIN_QUESTIONS = 8
_EXPECTED_DEVELOPMENT_QUESTIONS = 4
_EXPECTED_OUTCOME_TRIALS = 48
_MAX_MANIFEST_BYTES = 1024 * 1024
_MAX_STREAM_BYTES = 16 * 1024 * 1024
_HEX = frozenset("0123456789abcdef")
_PILOT_KIND = "repeatable_party_outcome_development"
_MODEL_KIND = "repeatable_party_outcome_model"
_PILOT_STREAM_RECORDS = {
    "evaluation.jsonl": 1,
    "outcomes.jsonl": _EXPECTED_OUTCOME_TRIALS,
    "plan.jsonl": 1,
}


class RepeatablePartyOutcomeFitError(RuntimeError):
    """Raised when an offline fit cannot prove its dataset or split."""


@dataclass(frozen=True, slots=True)
class _AuthenticatedPilot:
    artifact_id: str
    manifest_sha256: str
    plan_record: Mapping[str, object]
    outcome_records: tuple[Mapping[str, object], ...]
    evaluation_record: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _ReconstructedDataset:
    examples: tuple[ScenarioOutcomeExample, ...]
    prospective_catalog_sha256: str
    plan_sha256: str
    source_commit: str
    source_bundle_sha256: str
    rom_sha256: str


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--venue-prior-registry", type=Path, required=True)
    parser.add_argument("--prior-reservation-plan", type=Path, required=True)
    parser.add_argument("--catalog-root", type=Path, required=True)
    parser.add_argument("--private-artifact-root", type=Path, required=True)
    parser.add_argument("--development-artifact", type=Path, required=True)
    parser.add_argument(
        "--exclude-development-artifact",
        type=Path,
        action="append",
        default=[],
    )
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--expected-collection-source", required=True)
    parser.add_argument("--expected-base-model-file-sha256", required=True)
    return parser


def _require_sha256(value: object, *, subject: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX for character in value)
    ):
        raise RepeatablePartyOutcomeFitError(f"{subject} digest is invalid")
    return value


def _require_commit(value: object, *, subject: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or any(character not in _HEX for character in value)
    ):
        raise RepeatablePartyOutcomeFitError(f"{subject} commit is invalid")
    return value


def _require_external(path: Path, *, subject: str) -> Path:
    try:
        if path.is_symlink():
            raise RepeatablePartyOutcomeFitError(f"{subject} cannot be a symlink")
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise RepeatablePartyOutcomeFitError(f"{subject} is unavailable") from error
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise RepeatablePartyOutcomeFitError(
            f"{subject} must remain outside the repository"
        )
    return resolved


def _read_regular_file(path: Path, *, subject: str, maximum_bytes: int) -> bytes:
    try:
        before = path.lstat()
    except OSError as error:
        raise RepeatablePartyOutcomeFitError(f"{subject} is unavailable") from error
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size <= 0
        or before.st_size > maximum_bytes
    ):
        raise RepeatablePartyOutcomeFitError(f"{subject} is not a bounded regular file")
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        payload = b""
        while len(payload) <= maximum_bytes:
            chunk = os.read(descriptor, min(1024 * 1024, maximum_bytes + 1 - len(payload)))
            if not chunk:
                break
            payload += chunk
        after = os.fstat(descriptor)
    except OSError as error:
        raise RepeatablePartyOutcomeFitError(f"{subject} cannot be read safely") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_opened = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if (
        identity_before != identity_opened
        or identity_opened != identity_after
        or len(payload) != before.st_size
        or len(payload) > maximum_bytes
    ):
        raise RepeatablePartyOutcomeFitError(f"{subject} changed while being read")
    return payload


def _canonical_line(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _decode_canonical_jsonl(
    payload: bytes,
    *,
    subject: str,
    expected_records: int,
) -> tuple[Mapping[str, object], ...]:
    if not payload.endswith(b"\n"):
        raise RepeatablePartyOutcomeFitError(f"{subject} is not canonical JSONL")
    lines = payload.splitlines(keepends=True)
    if len(lines) != expected_records:
        raise RepeatablePartyOutcomeFitError(f"{subject} record count differs")
    result: list[Mapping[str, object]] = []
    for line in lines:
        try:
            value = json.loads(line.decode("ascii"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RepeatablePartyOutcomeFitError(f"{subject} is invalid ASCII JSONL") from error
        if not isinstance(value, Mapping) or _canonical_line(value) != line:
            raise RepeatablePartyOutcomeFitError(f"{subject} is not canonical JSONL")
        result.append(value)
    return tuple(result)


def _open_authenticated_pilot(
    artifact_path: Path,
    *,
    expected_manifest_sha256: str,
) -> _AuthenticatedPilot:
    artifact = _require_external(artifact_path, subject="development artifact")
    try:
        artifact_metadata = artifact.lstat()
        entries = tuple(sorted(item.name for item in artifact.iterdir()))
    except OSError as error:
        raise RepeatablePartyOutcomeFitError("development artifact is unavailable") from error
    if not stat.S_ISDIR(artifact_metadata.st_mode):
        raise RepeatablePartyOutcomeFitError("development artifact is not a directory")
    expected_entries = tuple(sorted((*_PILOT_STREAM_RECORDS, "manifest.json")))
    if entries != expected_entries:
        raise RepeatablePartyOutcomeFitError("development artifact stream inventory differs")

    manifest_payload = _read_regular_file(
        artifact / "manifest.json",
        subject="development artifact manifest",
        maximum_bytes=_MAX_MANIFEST_BYTES,
    )
    manifest_sha256 = hashlib.sha256(manifest_payload).hexdigest()
    if manifest_sha256 != _require_sha256(
        expected_manifest_sha256,
        subject="expected development artifact manifest",
    ):
        raise RepeatablePartyOutcomeFitError("development artifact manifest failed authentication")
    (manifest,) = _decode_canonical_jsonl(
        manifest_payload,
        subject="development artifact manifest",
        expected_records=1,
    )
    if set(manifest) != {
        "artifact_id",
        "files",
        "format",
        "kind",
        "schema_version",
        "status",
        "totals",
    }:
        raise RepeatablePartyOutcomeFitError("development artifact manifest shape differs")
    artifact_id = manifest.get("artifact_id")
    files = manifest.get("files")
    totals = manifest.get("totals")
    if (
        manifest.get("format") != PRIVATE_JSON_ARTIFACT_FORMAT
        or manifest.get("schema_version") != PRIVATE_ARTIFACT_SCHEMA_VERSION
        or manifest.get("kind") != _PILOT_KIND
        or manifest.get("status") != "complete"
        or not isinstance(artifact_id, str)
        or artifact_id != artifact.name
        or not isinstance(files, list)
        or not isinstance(totals, Mapping)
        or set(totals) != {"bytes", "files", "records"}
    ):
        raise RepeatablePartyOutcomeFitError("development artifact manifest identity differs")

    file_payloads: dict[str, bytes] = {}
    declared_total_bytes = 0
    declared_total_records = 0
    declared_names: list[str] = []
    for entry in files:
        if not isinstance(entry, Mapping) or set(entry) != {
            "bytes",
            "filename",
            "records",
            "sha256",
        }:
            raise RepeatablePartyOutcomeFitError("development artifact file record differs")
        filename = entry.get("filename")
        size = entry.get("bytes")
        records = entry.get("records")
        declared_sha256 = entry.get("sha256")
        if (
            not isinstance(filename, str)
            or filename not in _PILOT_STREAM_RECORDS
            or type(size) is not int  # noqa: E721
            or size <= 0
            or type(records) is not int  # noqa: E721
            or records != _PILOT_STREAM_RECORDS[filename]
            or _require_sha256(declared_sha256, subject="development stream")
            != declared_sha256
        ):
            raise RepeatablePartyOutcomeFitError("development artifact file semantics differ")
        payload = _read_regular_file(
            artifact / filename,
            subject="development artifact stream",
            maximum_bytes=_MAX_STREAM_BYTES,
        )
        if len(payload) != size or hashlib.sha256(payload).hexdigest() != declared_sha256:
            raise RepeatablePartyOutcomeFitError(
                "development artifact stream failed authentication"
            )
        file_payloads[filename] = payload
        declared_names.append(filename)
        declared_total_bytes += size
        declared_total_records += records
    if (
        tuple(declared_names) != tuple(sorted(_PILOT_STREAM_RECORDS))
        or totals.get("bytes") != declared_total_bytes
        or totals.get("files") != len(_PILOT_STREAM_RECORDS)
        or totals.get("records") != declared_total_records
    ):
        raise RepeatablePartyOutcomeFitError("development artifact totals differ")

    (plan_record,) = _decode_canonical_jsonl(
        file_payloads["plan.jsonl"],
        subject="development plan stream",
        expected_records=1,
    )
    outcomes = _decode_canonical_jsonl(
        file_payloads["outcomes.jsonl"],
        subject="development outcome stream",
        expected_records=_EXPECTED_OUTCOME_TRIALS,
    )
    (evaluation_record,) = _decode_canonical_jsonl(
        file_payloads["evaluation.jsonl"],
        subject="development evaluation stream",
        expected_records=1,
    )
    return _AuthenticatedPilot(
        artifact_id=artifact_id,
        manifest_sha256=manifest_sha256,
        plan_record=plan_record,
        outcome_records=outcomes,
        evaluation_record=evaluation_record,
    )


def _load_external_json(
    path: Path,
    *,
    subject: str,
    expected_sha256: str,
) -> Mapping[str, object]:
    source = _require_external(path, subject=subject)
    payload = _read_regular_file(source, subject=subject, maximum_bytes=_MAX_STREAM_BYTES)
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise RepeatablePartyOutcomeFitError(f"{subject} failed authentication")
    try:
        value = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RepeatablePartyOutcomeFitError(f"{subject} is invalid JSON") from error
    if not isinstance(value, Mapping):
        raise RepeatablePartyOutcomeFitError(f"{subject} is not an object")
    return value


def _require_plan_record(
    pilot: _AuthenticatedPilot,
    *,
    expected_plan_sha256: str,
    expected_collection_source: str,
) -> tuple[Mapping[str, object], Mapping[str, object], PartyDevelopmentOutcomeDose]:
    record = pilot.plan_record
    if set(record) != {
        "battle_credit_protocol",
        "development_repeatable",
        "dose",
        "inputs",
        "plan",
        "plan_sha256",
        "record_type",
        "rom_sha256",
        "sealed",
        "source",
        "source_bundle_sha256",
    }:
        raise RepeatablePartyOutcomeFitError("development plan record shape differs")
    plan = record.get("plan")
    inputs = record.get("inputs")
    source = record.get("source")
    dose_value = record.get("dose")
    expected_plan = _require_sha256(expected_plan_sha256, subject="expected plan")
    expected_source = _require_commit(
        expected_collection_source,
        subject="expected collection source",
    )
    if (
        record.get("record_type") != "repeatable_party_development_plan"
        or not isinstance(plan, Mapping)
        or not isinstance(inputs, Mapping)
        or not isinstance(source, Mapping)
        or not isinstance(dose_value, Mapping)
        or record.get("plan_sha256") != expected_plan
        or canonical_sha256(plan) != expected_plan
        or source != {"git_commit": expected_source, "worktree_dirty": False}
        or record.get("development_repeatable") is not True
        or record.get("sealed") is not False
    ):
        raise RepeatablePartyOutcomeFitError("development plan binding differs")
    try:
        dose = PartyDevelopmentOutcomeDose(
            completed_battles=cast(int, dose_value["completed_battles"]),
            maximum_encounter_steps=cast(int, dose_value["maximum_encounter_steps"]),
            maximum_controller_actions=cast(int, dose_value["maximum_controller_actions"]),
            maximum_frames=cast(int, dose_value["maximum_frames"]),
            maximum_healing_trips=cast(int, dose_value["maximum_healing_trips"]),
            maximum_rotations=cast(int, dose_value["maximum_rotations"]),
            maximum_faints=cast(int, dose_value["maximum_faints"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RepeatablePartyOutcomeFitError("development dose is invalid") from error
    if (
        dose.public_dict() != dose_value
        or record.get("battle_credit_protocol")
        != _battle_credit_protocol(dose.completed_battles)
        or dose.completed_battles != 1
    ):
        raise RepeatablePartyOutcomeFitError("development intervention binding differs")
    return plan, inputs, dose


def _candidate_outcome(
    record: Mapping[str, object],
    *,
    expected_assignment: PartyDevelopmentOutcomeTrialAssignment,
) -> CandidateOutcome:
    if set(record) != {"assignment", "evidence", "outcome", "record_type"} or record.get(
        "record_type"
    ) != "repeatable_party_candidate_outcome":
        raise RepeatablePartyOutcomeFitError("candidate outcome record shape differs")
    assignment_value = record.get("assignment")
    evidence = record.get("evidence")
    outcome = record.get("outcome")
    try:
        assignment = PartyDevelopmentOutcomeTrialAssignment.from_private_dict(
            assignment_value
        )
    except (TypeError, ValueError) as error:
        raise RepeatablePartyOutcomeFitError("candidate assignment is invalid") from error
    if assignment != expected_assignment:
        raise RepeatablePartyOutcomeFitError("candidate assignment differs from reconstruction")
    if not isinstance(evidence, Mapping) or not isinstance(outcome, Mapping):
        raise RepeatablePartyOutcomeFitError("candidate evidence is invalid")
    if set(outcome) != {"criterion_values", "evidence_sha256", "status"}:
        raise RepeatablePartyOutcomeFitError("candidate outcome semantics differ")
    values = outcome.get("criterion_values")
    evidence_sha256 = outcome.get("evidence_sha256")
    if (
        outcome.get("status") != OutcomeEvidenceStatus.MEASURED.value
        or not isinstance(values, list)
        or not values
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in values
        )
        or _require_sha256(evidence_sha256, subject="candidate evidence")
        != evidence_sha256
        or canonical_sha256(evidence) != evidence_sha256
        or evidence.get("schema")
        != "pokemon.red.repeatable-party-development-trial-evidence.v1"
        or evidence.get("assignment_sha256") != assignment.assignment_sha256
        or evidence.get("trial_id") != assignment.trial_id
        or evidence.get("scenario_id") != assignment.scenario_id
        or evidence.get("candidate_index") != assignment.candidate_index
        or evidence.get("criterion_values") != values
        or evidence.get("teacher_queries") != 0
        or evidence.get("model_predictions") != 0
        or evidence.get("model_updates") != 0
        or evidence.get("private_path_fields") != 0
    ):
        raise RepeatablePartyOutcomeFitError("candidate evidence binding differs")
    return CandidateOutcome(
        OutcomeEvidenceStatus.MEASURED,
        criterion_values=tuple(float(value) for value in values),
        evidence_sha256=evidence_sha256,
    )


def _reconstruct_dataset(
    args: argparse.Namespace,
    pilot: _AuthenticatedPilot,
) -> _ReconstructedDataset:
    plan_document, inputs, dose = _require_plan_record(
        pilot,
        expected_plan_sha256=args.expected_plan_sha256,
        expected_collection_source=args.expected_collection_source,
    )
    expected_input_keys = {
        "context_catalog",
        "excluded_development_artifact_manifests",
        "inventory",
        "prior_reservation_plan",
        "venue_prior_registry",
    }
    if set(inputs) != expected_input_keys:
        raise RepeatablePartyOutcomeFitError("development input binding differs")
    digests = {
        name: _require_sha256(inputs.get(name), subject=f"development {name}")
        for name in expected_input_keys - {"excluded_development_artifact_manifests"}
    }
    excluded_manifest_values = inputs.get("excluded_development_artifact_manifests")
    if not isinstance(excluded_manifest_values, list) or any(
        _require_sha256(value, subject="excluded artifact manifest") != value
        for value in excluded_manifest_values
    ):
        raise RepeatablePartyOutcomeFitError("excluded artifact manifest binding differs")

    inventory_document = _load_external_json(
        args.inventory,
        subject="inventory",
        expected_sha256=digests["inventory"],
    )
    context_path = _require_external(args.context_catalog, subject="context catalog")
    context_payload = _read_regular_file(
        context_path,
        subject="context catalog",
        maximum_bytes=_MAX_STREAM_BYTES,
    )
    if hashlib.sha256(context_payload).hexdigest() != digests["context_catalog"]:
        raise RepeatablePartyOutcomeFitError("context catalog failed authentication")
    venue_document = _load_external_json(
        args.venue_prior_registry,
        subject="venue-prior registry",
        expected_sha256=digests["venue_prior_registry"],
    )
    prior_document = _load_external_json(
        args.prior_reservation_plan,
        subject="prior reservation plan",
        expected_sha256=digests["prior_reservation_plan"],
    )
    inventory = PartyDevelopmentCheckpointInventory.from_private_dict(inventory_document)
    venue_registry = PartyDevelopmentVenuePriorRegistry.from_private_dict(venue_document)
    prior_plan = PartyDevelopmentQuestionReservationPlan.from_private_dict(prior_document)
    exclusions = tuple(
        _development_artifact_exclusion(path)
        for path in args.exclude_development_artifact
    )
    if sorted(item.manifest_sha256 for item in exclusions) != sorted(
        cast(list[str], excluded_manifest_values)
    ):
        raise RepeatablePartyOutcomeFitError("excluded artifacts differ from the pilot")
    excluded_roots = frozenset(
        (
            *prior_plan.excluded_root_lineage_ids,
            *(root for item in exclusions for root in item.root_lineage_ids),
        )
    )
    excluded_states = frozenset(
        (
            *prior_plan.excluded_state_sha256,
            *(state for item in exclusions for state in item.initial_state_sha256),
        )
    )
    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    rom_sha256 = _require_sha256(
        pilot.plan_record.get("rom_sha256"),
        subject="pilot ROM",
    )
    if fingerprint.sha256 != rom_sha256:
        raise RepeatablePartyOutcomeFitError("Red cartridge differs from the pilot")
    source_commit = _require_commit(
        args.expected_collection_source,
        subject="collection source",
    )
    source_bundle_sha256 = _require_sha256(
        pilot.plan_record.get("source_bundle_sha256"),
        subject="collection source bundle",
    )
    pool, _capability_rejections = _build_option_pool(
        inventory=inventory,
        context_catalog_payload=context_payload,
        venue_registry=venue_registry,
        catalog_root=_require_external(args.catalog_root, subject="catalog root"),
        rom_path=rom_path,
        excluded_roots=excluded_roots,
        excluded_states=excluded_states,
        source_commit=source_commit,
        source_bundle_sha256=source_bundle_sha256,
        completed_battles=dose.completed_battles,
    )
    partition_counts = plan_document.get("partition_counts")
    seed = plan_document.get("seed")
    if (
        partition_counts
        != {
            ScenarioPartition.TRAIN.value: _EXPECTED_TRAIN_QUESTIONS,
            ScenarioPartition.DEVELOPMENT.value: _EXPECTED_DEVELOPMENT_QUESTIONS,
        }
        or type(seed) is not int  # noqa: E721
    ):
        raise RepeatablePartyOutcomeFitError("pilot split differs from the initial-fit gate")
    plan = select_repeatable_party_scenarios(
        tuple(item.option for item in pool),
        train_count=_EXPECTED_TRAIN_QUESTIONS,
        development_count=_EXPECTED_DEVELOPMENT_QUESTIONS,
        seed=seed,
        maximum_timing_offset_frames=_MAXIMUM_TIMING_OFFSET_FRAMES,
    )
    if (
        plan.plan_sha256 != args.expected_plan_sha256
        or plan.public_dict() != plan_document
    ):
        raise RepeatablePartyOutcomeFitError("pilot plan differs from reconstruction")
    selected = _selected_runtimes(plan, pool)
    assignments_by_scenario = _trial_assignments(selected)
    assignments = tuple(
        assignment
        for runtime in selected
        for assignment in assignments_by_scenario[
            runtime.binding_question.scenario_id
        ]
    )
    if len(assignments) != _EXPECTED_OUTCOME_TRIALS:
        raise RepeatablePartyOutcomeFitError("pilot trial denominator differs")
    outcomes_by_scenario: dict[str, dict[int, CandidateOutcome]] = {}
    for record, assignment in zip(pilot.outcome_records, assignments, strict=True):
        outcome = _candidate_outcome(record, expected_assignment=assignment)
        scenario = outcomes_by_scenario.setdefault(assignment.scenario_id, {})
        if assignment.candidate_index in scenario:
            raise RepeatablePartyOutcomeFitError("pilot repeats a candidate outcome")
        scenario[assignment.candidate_index] = outcome
    examples = cast(
        tuple[ScenarioOutcomeExample, ...],
        _assemble_examples(selected, outcomes_by_scenario),
    )
    prospective = PartyDevelopmentProspectiveCatalog.freeze(
        tuple(item.binding_question.binding for item in selected)
    )
    audit = audit_party_development_outcome_catalog(
        examples,
        prospective_catalog=prospective,
        policy=PartyDevelopmentReadinessPolicy(
            minimum_train_examples=_EXPECTED_TRAIN_QUESTIONS,
            minimum_development_examples=_EXPECTED_DEVELOPMENT_QUESTIONS,
            minimum_goals_per_partition=2,
            minimum_candidate_count_observed=3,
            minimum_health_bins=2,
            minimum_pp_bins=1,
            minimum_survival_bins=2,
            minimum_evolution_route_kinds=2,
            minimum_semantic_menus_per_partition=3,
            require_complete_venue_priors=False,
        ),
    )
    if (
        pilot.evaluation_record
        != {
            "record_type": "repeatable_party_development_audit",
            "audit": audit.public_dict(),
            "model_fit": False,
            "authority_promoted": False,
        }
        or not audit.initial_fit_ready
        or audit.learner_update_eligible_examples != len(examples)
    ):
        raise RepeatablePartyOutcomeFitError("pilot evaluation differs from reconstruction")
    return _ReconstructedDataset(
        examples=examples,
        prospective_catalog_sha256=prospective.catalog_sha256,
        plan_sha256=plan.plan_sha256,
        source_commit=source_commit,
        source_bundle_sha256=source_bundle_sha256,
        rom_sha256=rom_sha256,
    )


def _development_direction(cycle: PartyDevelopmentOutcomeLearningCycle) -> str:
    accuracy_delta = (
        cycle.updated_development.accuracy - cycle.base_development.accuracy
    )
    cross_entropy_delta = (
        cycle.updated_development.cross_entropy
        - cycle.base_development.cross_entropy
    )
    probability_delta = cycle.paired_development.mean_winner_probability_delta
    favorable = (accuracy_delta >= 0, cross_entropy_delta < 0, probability_delta > 0)
    unfavorable = (accuracy_delta < 0, cross_entropy_delta > 0, probability_delta < 0)
    if all(favorable):
        return "descriptively_improved"
    if all(unfavorable):
        return "descriptively_regressed"
    if accuracy_delta == 0 and cross_entropy_delta == 0 and probability_delta == 0:
        return "unchanged"
    return "mixed"


def _public_learning_summary(
    cycle: PartyDevelopmentOutcomeLearningCycle,
) -> dict[str, object]:
    return {
        "training": {
            "examples": cycle.update.report.training_example_count,
            "tied_targets": cycle.update.report.tied_target_examples,
            "loss_before": cycle.update.report.loss_before,
            "loss_after": cycle.update.report.loss_after,
            "epochs": cycle.update.report.epochs,
            "learning_rate": cycle.update.report.learning_rate,
            "prior_l2": cycle.update.report.prior_l2,
        },
        "development": {
            "examples": cycle.base_development.example_count,
            "base": {
                "correct_preferences": cycle.base_development.correct_preferences,
                "accuracy": cycle.base_development.accuracy,
                "cross_entropy": cycle.base_development.cross_entropy,
                "mean_winner_probability": (
                    cycle.base_development.mean_winner_probability
                ),
            },
            "updated": {
                "correct_preferences": cycle.updated_development.correct_preferences,
                "accuracy": cycle.updated_development.accuracy,
                "cross_entropy": cycle.updated_development.cross_entropy,
                "mean_winner_probability": (
                    cycle.updated_development.mean_winner_probability
                ),
            },
            "paired": {
                "updated_wins": cycle.paired_development.updated_wins,
                "base_wins": cycle.paired_development.base_wins,
                "correctness_ties": cycle.paired_development.correctness_ties,
                "discordant_pairs": (
                    cycle.paired_development.discordant_correctness_pairs
                ),
                "two_sided_exact_p": (
                    cycle.paired_development.paired_two_sided_exact_p
                ),
                "winner_probability_improvements": (
                    cycle.paired_development.winner_probability_improvements
                ),
                "winner_probability_regressions": (
                    cycle.paired_development.winner_probability_regressions
                ),
                "winner_probability_ties": (
                    cycle.paired_development.winner_probability_ties
                ),
                "mean_winner_probability_delta": (
                    cycle.paired_development.mean_winner_probability_delta
                ),
            },
            "direction": _development_direction(cycle),
            "descriptive_initial_curve": True,
            "inferential_claim": False,
        },
    }


def _fit(args: argparse.Namespace) -> dict[str, object]:
    pilot = _open_authenticated_pilot(
        args.development_artifact,
        expected_manifest_sha256=args.expected_manifest_sha256,
    )
    dataset = _reconstruct_dataset(args, pilot)
    base_path = _require_external(args.base_model, subject="base model")
    base_file_sha256 = _require_sha256(
        args.expected_base_model_file_sha256,
        subject="expected base model file",
    )
    base_model = load_party_development_outcome_model(
        base_path,
        expected_sha256=base_file_sha256,
    )
    if base_model.outcome_training_examples != 0:
        raise RepeatablePartyOutcomeFitError("initial fit requires the untouched teacher prior")
    base_model_sha256 = canonical_party_development_outcome_model_sha256(base_model)
    training = tuple(
        item
        for item in dataset.examples
        if item.partition is ScenarioPartition.TRAIN
    )
    development = tuple(
        item
        for item in dataset.examples
        if item.partition is ScenarioPartition.DEVELOPMENT
    )
    if (
        len(training) != _EXPECTED_TRAIN_QUESTIONS
        or len(development) != _EXPECTED_DEVELOPMENT_QUESTIONS
        or not all(item.learner_update_eligible for item in (*training, *development))
    ):
        raise RepeatablePartyOutcomeFitError("authenticated examples do not satisfy the fit gate")

    fit_identity = canonical_sha256(
        {
            "schema": "pokemon.red.repeatable-party-outcome-fit-identity.v1",
            "pilot_manifest_sha256": pilot.manifest_sha256,
            "plan_sha256": dataset.plan_sha256,
            "base_model_file_sha256": base_file_sha256,
            "base_model_canonical_sha256": base_model_sha256,
            "hyperparameters": {
                "epochs": _FIT_EPOCHS,
                "learning_rate": _FIT_LEARNING_RATE,
                "prior_l2": _FIT_PRIOR_L2,
            },
        }
    )
    artifact_id = f"repeatable-party-outcome-fit-{fit_identity[:32]}"
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_published_source(PROJECT_ROOT, source)
    output_root = open_private_root(
        _require_external(args.private_artifact_root, subject="private artifact root"),
        repository_root=PROJECT_ROOT,
    )
    writer = output_root.begin_artifact(artifact_id, kind=_MODEL_KIND)
    preregistration = {
        "schema": "pokemon.red.repeatable-party-outcome-fit-preregistration.v1",
        "fit_identity_sha256": fit_identity,
        "source": source.public_dict(),
        "pilot_manifest_sha256": pilot.manifest_sha256,
        "plan_sha256": dataset.plan_sha256,
        "prospective_catalog_sha256": dataset.prospective_catalog_sha256,
        "collection_source_commit": dataset.source_commit,
        "collection_source_bundle_sha256": dataset.source_bundle_sha256,
        "rom_sha256": dataset.rom_sha256,
        "base_model_file_sha256": base_file_sha256,
        "base_model_canonical_sha256": base_model_sha256,
        "train_questions": len(training),
        "development_questions": len(development),
        "epochs": _FIT_EPOCHS,
        "learning_rate": _FIT_LEARNING_RATE,
        "prior_l2": _FIT_PRIOR_L2,
        "fit_partition": ScenarioPartition.TRAIN.value,
        "comparison_partition": ScenarioPartition.DEVELOPMENT.value,
        "development_used_for_tuning": False,
        "retry_same_fit_identity": False,
        "sealed_red_cases_opened": 0,
        "crystal_cases_opened": 0,
        "full_game_replays": 0,
        "authority_promoted": False,
        "private_path_fields": 0,
    }
    with writer:
        writer.append("preregistration", preregistration, durable=True)
        cycle = run_party_development_outcome_learning_cycle(
            base_model,
            training_examples=training,
            development_examples=development,
            epochs=_FIT_EPOCHS,
            learning_rate=_FIT_LEARNING_RATE,
            prior_l2=_FIT_PRIOR_L2,
        )
        writer.append("model", cycle.update.model.to_dict(), durable=True)
        writer.append("learning", cycle.public_dict(), durable=True)

    model_payload = _canonical_line(cycle.update.model.to_dict())
    learning = _public_learning_summary(cycle)
    return {
        "schema": "pokemon.red.repeatable-party-outcome-fit-receipt.v1",
        "status": "complete",
        "source": source.public_dict(),
        "fit_identity_sha256": fit_identity,
        "pilot_manifest_sha256": pilot.manifest_sha256,
        "plan_sha256": dataset.plan_sha256,
        "prospective_catalog_sha256": dataset.prospective_catalog_sha256,
        "base_model_file_sha256": base_file_sha256,
        "base_model_canonical_sha256": base_model_sha256,
        "updated_model_file_sha256": hashlib.sha256(model_payload).hexdigest(),
        "updated_model_canonical_sha256": (
            canonical_party_development_outcome_model_sha256(cycle.update.model)
        ),
        "model_artifact": writer.summary.public_dict(),
        "learning": learning,
        "model_fits": 1,
        "model_updates": 1,
        "development_comparisons": 1,
        "development_used_for_tuning": False,
        "teacher_queries": 0,
        "teacher_choice_targets": 0,
        "sealed_red_cases_opened": 0,
        "crystal_cases_opened": 0,
        "full_game_replays": 0,
        "authority_promoted": False,
        "inferential_claim": False,
        "private_identity_fields": 0,
        "private_path_fields": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        result = _fit(parser.parse_args(argv))
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        parser.error(f"repeatable party outcome fit failed closed: {error}")
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
