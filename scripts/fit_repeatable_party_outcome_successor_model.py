#!/usr/bin/env python3
"""Fit from one authenticated repeatable campaign plus its recovery successor.

The predecessor's measured outcomes remain the original evidence.  The
successor may contribute terminals only for the predecessor's declared invalid
assignments.  Training uses every complete joined train question; comparison
uses only development questions whose labels were incomplete before the
successor and became complete because of it.  These are newly completed labels,
not untouched roots: partial candidate outcomes existed before recovery.
Previously scored development questions are never reused for this comparison.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import stat
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.collection_protocol import (  # noqa: E402
    committed_source_bundle_sha256,
    working_source_bundle_sha256,
)
from pokemon_red_completion.party_development_catalog import (  # noqa: E402
    PartyDevelopmentProspectiveCatalog,
)
from pokemon_red_completion.party_development_outcome_dataset import (  # noqa: E402
    PartyDevelopmentReadinessPolicy,
    audit_party_development_outcome_catalog,
)
from pokemon_red_completion.party_development_outcome_learning import (  # noqa: E402
    canonical_party_development_outcome_model_sha256,
    load_party_development_outcome_model,
    run_party_development_outcome_learning_cycle,
)
from pokemon_red_completion.private_artifacts import open_private_root  # noqa: E402
from pokemon_red_completion.provenance import (  # noqa: E402
    SourceIdentity,
    canonical_sha256,
    detect_source_identity,
    require_published_source,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402
from pokemon_red_completion.scenario_outcomes import (  # noqa: E402
    CandidateOutcome,
    ScenarioOutcomeExample,
)

_FITTER = runpy.run_path(str(PROJECT_ROOT / "scripts" / "fit_repeatable_party_outcome_model.py"))
_SUCCESSOR = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "run_repeatable_party_outcome_successor.py")
)

_SUCCESSOR_KIND = "repeatable_party_outcome_development_successor"
_MODEL_KIND = "repeatable_party_outcome_model"
_FIT_EPOCHS = 200
_FIT_LEARNING_RATE = 0.01
_FIT_PRIOR_L2 = 0.1
_HEX = frozenset("0123456789abcdef")
_SUCCESSOR_RUNNER = PROJECT_ROOT / "scripts" / "run_repeatable_party_outcome_successor.py"
_DEVELOPMENT_RUNNER = PROJECT_ROOT / "scripts" / "run_repeatable_party_outcome_development.py"
_MODEL_STREAMS = frozenset({"learning.jsonl", "model.jsonl", "preregistration.jsonl"})
_RETENTION_RULE = {
    "accuracy_must_not_decrease": True,
    "cross_entropy_must_decrease": True,
    "mean_winner_probability_must_increase": True,
    "mixed_result_is_failure": True,
    "updated_paired_wins_must_exceed_base_wins": True,
}
_EXPECTED_TRAIN_KIND_COUNTS = {"trainee": 13, "venue": 9}
_EXPECTED_TRAIN_GOAL_COUNTS = {
    "balance": 13,
    "collection": 3,
    "evolution": 3,
    "role_coverage": 3,
}
_EXPECTED_NEW_DEVELOPMENT_KIND_COUNTS = {"trainee": 3, "venue": 2}
_EXPECTED_NEW_DEVELOPMENT_GOAL_COUNTS = {
    "balance": 1,
    "collection": 1,
    "evolution": 2,
    "role_coverage": 1,
}


class RepeatablePartyOutcomeSuccessorFitError(RuntimeError):
    """Raised when the joined lineage or comparison boundary cannot be proved."""


@dataclass(frozen=True, slots=True)
class _JoinedDataset:
    examples: tuple[ScenarioOutcomeExample, ...]
    training: tuple[ScenarioOutcomeExample, ...]
    newly_completed_development: tuple[ScenarioOutcomeExample, ...]
    previously_observed_development: tuple[ScenarioOutcomeExample, ...]
    prospective_catalog_sha256: str
    predecessor_manifest_sha256: str
    successor_manifest_sha256: str
    predecessor_plan_sha256: str
    successor_plan_sha256: str
    semantic_reconstruction_sha256: str
    collection_source_commit: str
    collection_source_bundle_sha256: str
    rom_sha256: str
    predecessor_measured_trials: int
    successor_measured_trials: int
    successor_invalid_trials: int
    training_kind_counts: tuple[tuple[str, int], ...]
    training_goal_counts: tuple[tuple[str, int], ...]
    newly_completed_development_kind_counts: tuple[tuple[str, int], ...]
    newly_completed_development_goal_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class _AuthenticatedModelArtifact:
    artifact: Path
    manifest_sha256: str
    preregistration: Mapping[str, object]
    learning: Mapping[str, object]
    model: Mapping[str, object]
    model_file_sha256: str


@dataclass(frozen=True, slots=True)
class _PlanOnlyPilot:
    plan_record: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _CollectionReadiness:
    reconstruction: Any
    predecessor_plan_record: Mapping[str, object]
    predecessor_plan: Mapping[str, object]
    predecessor_dose: Any
    successor_plan_record: Mapping[str, object]
    input_sha256: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _FitReadiness:
    source: SourceIdentity
    base_model: Any
    base_model_file_sha256: str
    base_model_canonical_sha256: str
    base_model_artifact_manifest_sha256: str
    prior_comparison_manifest_sha256: str
    prior_scored_development_roots: frozenset[str]
    prior_scored_development_states: frozenset[str]
    prior_scored_development_marginal_set_sha256: str
    comparison_claim_sha256: str
    artifact_id: str
    output_root: Any
    collection: _CollectionReadiness


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--venue-prior-registry", type=Path, required=True)
    parser.add_argument("--prior-reservation-plan", type=Path, required=True)
    parser.add_argument("--catalog-root", type=Path, required=True)
    parser.add_argument("--predecessor-artifact", type=Path, required=True)
    parser.add_argument("--successor-artifact", type=Path, required=True)
    parser.add_argument("--successor-frozen-plan", type=Path, required=True)
    parser.add_argument("--private-artifact-root", type=Path, required=True)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--base-model-artifact", type=Path, required=True)
    parser.add_argument("--base-pilot-artifact", type=Path, required=True)
    parser.add_argument("--previous-comparison-artifact", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--expected-predecessor-manifest-sha256", required=True)
    parser.add_argument("--expected-predecessor-plan-sha256", required=True)
    parser.add_argument("--expected-predecessor-source", required=True)
    parser.add_argument("--expected-predecessor-measured-trials", type=int, default=78)
    parser.add_argument("--expected-predecessor-invalid-trials", type=int, default=15)
    parser.add_argument("--expected-successor-manifest-sha256", required=True)
    parser.add_argument("--expected-successor-plan-sha256", required=True)
    parser.add_argument("--expected-successor-source", required=True)
    parser.add_argument("--expected-successor-source-bundle-sha256", required=True)
    parser.add_argument("--expected-successor-frozen-plan-file-sha256", required=True)
    parser.add_argument("--expected-successor-measured-trials", type=int, default=10)
    parser.add_argument("--expected-successor-invalid-trials", type=int, default=5)
    parser.add_argument("--expected-base-model-file-sha256", required=True)
    parser.add_argument("--expected-base-model-artifact-manifest-sha256", required=True)
    parser.add_argument("--expected-base-fit-identity-sha256", required=True)
    parser.add_argument("--expected-base-outcome-training-examples", type=int, default=8)
    parser.add_argument("--expected-base-pilot-manifest-sha256", required=True)
    parser.add_argument("--expected-base-pilot-plan-sha256", required=True)
    parser.add_argument("--expected-base-pilot-source", required=True)
    parser.add_argument("--expected-base-pilot-measured-trials", type=int, default=48)
    parser.add_argument("--expected-previous-comparison-manifest-sha256", required=True)
    parser.add_argument("--expected-previous-comparison-fit-identity-sha256", required=True)
    parser.add_argument("--expected-successor-runner-sha256", required=True)
    parser.add_argument("--expected-development-runner-sha256", required=True)
    parser.add_argument(
        "--base-training-protocol",
        choices=("none", *_FITTER["_BATTLE_CREDIT_PROTOCOL_IDS"]),
        default="switch-assisted-fixed-dose-v1",
    )
    parser.add_argument(
        "--base-scenario-selection-protocol",
        choices=_FITTER["REPEATABLE_PARTY_SELECTION_PROTOCOLS"],
        default=_FITTER["SEMANTIC_GREEDY_SELECTION_PROTOCOL"],
    )
    parser.add_argument(
        "--battle-credit-protocol",
        choices=_FITTER["_BATTLE_CREDIT_PROTOCOL_IDS"],
        default="direct-safe-else-switch-assisted-fixed-dose-v1",
    )
    parser.add_argument(
        "--scenario-selection-protocol",
        choices=_FITTER["REPEATABLE_PARTY_SELECTION_PROTOCOLS"],
        default="balanced-kind-goal-coverage-v2",
    )
    parser.add_argument("--train-count", type=int, default=24)
    parser.add_argument("--development-count", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20260816)
    parser.add_argument("--completed-battles", type=int, default=1)
    parser.add_argument("--maximum-timing-offset-frames", type=int, default=255)
    parser.add_argument("--expected-predecessor-complete-train-questions", type=int, default=18)
    parser.add_argument(
        "--expected-predecessor-complete-development-questions",
        type=int,
        default=6,
    )
    parser.add_argument("--expected-fit-train-questions", type=int, default=22)
    parser.add_argument("--expected-joined-development-questions", type=int, default=11)
    parser.add_argument(
        "--expected-newly-completed-development-questions",
        type=int,
        default=5,
    )
    parser.add_argument("--exclude-root-lineage-id", action="append", default=[])
    parser.add_argument(
        "--exclude-development-artifact",
        type=Path,
        action="append",
        default=[],
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="authenticate the joined split without fitting or writing an artifact",
    )
    return parser


def _require_sha256(value: object, *, subject: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX for character in value)
    ):
        raise RepeatablePartyOutcomeSuccessorFitError(f"{subject} is not a SHA-256 digest")
    return value


def _require_commit(value: object, *, subject: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or any(character not in _HEX for character in value)
    ):
        raise RepeatablePartyOutcomeSuccessorFitError(f"{subject} is not a Git commit")
    return value


def _git_blob_sha256(
    revision: str,
    relative_path: str,
    *,
    subject: str,
) -> str:
    commit = _require_commit(revision, subject=f"{subject} revision")
    try:
        completed = subprocess.run(
            [
                "git",
                "--no-replace-objects",
                "show",
                f"{commit}:{relative_path}",
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RepeatablePartyOutcomeSuccessorFitError(
            f"{subject} committed bytes are unavailable"
        ) from error
    if completed.returncode != 0 or not completed.stdout or len(completed.stdout) > 2**20:
        raise RepeatablePartyOutcomeSuccessorFitError(f"{subject} committed bytes are unavailable")
    return hashlib.sha256(completed.stdout).hexdigest()


def _require_historical_runner_bytes(args: argparse.Namespace) -> None:
    source_commit = _require_commit(
        args.expected_successor_source,
        subject="successor collection source",
    )
    for path, expected_value, subject in (
        (
            _SUCCESSOR_RUNNER,
            args.expected_successor_runner_sha256,
            "successor runner",
        ),
        (
            _DEVELOPMENT_RUNNER,
            args.expected_development_runner_sha256,
            "development runner",
        ),
    ):
        expected = _require_sha256(expected_value, subject=subject)
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        if (
            _git_blob_sha256(source_commit, relative, subject=subject) != expected
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise RepeatablePartyOutcomeSuccessorFitError(
                f"{subject} differs from the authenticated collection source"
            )


def _read_artifact_manifest(
    artifact_path: Path,
    *,
    expected_manifest_sha256: str,
    expected_kind: str,
    expected_streams: Mapping[str, int],
    subject: str,
) -> tuple[Path, Mapping[str, object], str]:
    artifact = _FITTER["_require_external"](artifact_path, subject=subject)
    try:
        metadata = artifact.lstat()
        entries = tuple(sorted(item.name for item in artifact.iterdir()))
    except OSError as error:
        raise RepeatablePartyOutcomeSuccessorFitError(f"{subject} is unavailable") from error
    if not stat.S_ISDIR(metadata.st_mode):
        raise RepeatablePartyOutcomeSuccessorFitError(f"{subject} is not a directory")
    if entries != tuple(sorted((*expected_streams, "manifest.json"))):
        raise RepeatablePartyOutcomeSuccessorFitError(f"{subject} stream inventory differs")
    payload = _FITTER["_read_regular_file"](
        artifact / "manifest.json",
        subject=f"{subject} manifest",
        maximum_bytes=_FITTER["_MAX_MANIFEST_BYTES"],
    )
    manifest_sha256 = hashlib.sha256(payload).hexdigest()
    if manifest_sha256 != _require_sha256(
        expected_manifest_sha256,
        subject=f"expected {subject} manifest",
    ):
        raise RepeatablePartyOutcomeSuccessorFitError(f"{subject} manifest failed authentication")
    (manifest,) = _FITTER["_decode_canonical_jsonl"](
        payload,
        subject=f"{subject} manifest",
        expected_records=1,
    )
    files = manifest.get("files")
    totals = manifest.get("totals")
    if (
        set(manifest)
        != {
            "artifact_id",
            "files",
            "format",
            "kind",
            "schema_version",
            "status",
            "totals",
        }
        or manifest.get("format") != _FITTER["PRIVATE_JSON_ARTIFACT_FORMAT"]
        or manifest.get("schema_version") != _FITTER["PRIVATE_ARTIFACT_SCHEMA_VERSION"]
        or manifest.get("kind") != expected_kind
        or manifest.get("status") != "complete"
        or manifest.get("artifact_id") != artifact.name
        or not isinstance(files, list)
        or not isinstance(totals, Mapping)
        or set(totals) != {"bytes", "files", "records"}
    ):
        raise RepeatablePartyOutcomeSuccessorFitError(f"{subject} manifest identity differs")
    declared: dict[str, tuple[int, int, str]] = {}
    for entry in files:
        if not isinstance(entry, Mapping) or set(entry) != {
            "bytes",
            "filename",
            "records",
            "sha256",
        }:
            raise RepeatablePartyOutcomeSuccessorFitError(f"{subject} stream declaration differs")
        filename = entry.get("filename")
        size = entry.get("bytes")
        records = entry.get("records")
        digest = entry.get("sha256")
        if (
            not isinstance(filename, str)
            or filename not in expected_streams
            or type(size) is not int  # noqa: E721
            or size <= 0
            or type(records) is not int  # noqa: E721
            or records != expected_streams[filename]
            or _require_sha256(digest, subject=f"{subject} stream") != digest
            or filename in declared
        ):
            raise RepeatablePartyOutcomeSuccessorFitError(f"{subject} stream declaration differs")
        declared[filename] = (size, records, digest)
    if set(declared) != set(expected_streams):
        raise RepeatablePartyOutcomeSuccessorFitError(f"{subject} stream declarations differ")
    if (
        totals.get("bytes") != sum(item[0] for item in declared.values())
        or totals.get("files") != len(declared)
        or totals.get("records") != sum(item[1] for item in declared.values())
    ):
        raise RepeatablePartyOutcomeSuccessorFitError(f"{subject} manifest totals differ")
    # Preflight authenticates the bytes without decoding outcome labels.  This
    # keeps the comparison blind while ensuring that a known-corrupt input
    # cannot consume the durable one-shot claim during the real fit.
    for filename, (size, _records, digest) in declared.items():
        stream = _FITTER["_read_regular_file"](
            artifact / filename,
            subject=f"{subject} stream",
            maximum_bytes=_FITTER["_MAX_STREAM_BYTES"],
        )
        if len(stream) != size or hashlib.sha256(stream).hexdigest() != digest:
            raise RepeatablePartyOutcomeSuccessorFitError(f"{subject} stream failed authentication")
    return artifact, manifest, manifest_sha256


def _read_authenticated_stream_record(
    artifact: Path,
    manifest: Mapping[str, object],
    *,
    filename: str,
    subject: str,
) -> Mapping[str, object]:
    files = manifest.get("files")
    entries = (
        tuple(
            item for item in files if isinstance(item, Mapping) and item.get("filename") == filename
        )
        if isinstance(files, list)
        else ()
    )
    if len(entries) != 1 or entries[0].get("records") != 1:
        raise RepeatablePartyOutcomeSuccessorFitError(f"{subject} declaration differs")
    payload = _FITTER["_read_regular_file"](
        artifact / filename,
        subject=subject,
        maximum_bytes=_FITTER["_MAX_STREAM_BYTES"],
    )
    entry = entries[0]
    if len(payload) != entry.get("bytes") or hashlib.sha256(payload).hexdigest() != entry.get(
        "sha256"
    ):
        raise RepeatablePartyOutcomeSuccessorFitError(f"{subject} failed authentication")
    (record,) = _FITTER["_decode_canonical_jsonl"](
        payload,
        subject=subject,
        expected_records=1,
    )
    return record


def _open_authenticated_model_artifact(
    artifact_path: Path,
    *,
    expected_manifest_sha256: str,
    subject: str,
) -> _AuthenticatedModelArtifact:
    streams = {filename: 1 for filename in _MODEL_STREAMS}
    artifact, manifest, manifest_sha256 = _read_artifact_manifest(
        artifact_path,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_kind=_MODEL_KIND,
        expected_streams=streams,
        subject=subject,
    )
    files = manifest["files"]
    if not isinstance(files, list):  # pragma: no cover - manifest gate establishes this
        raise AssertionError("authenticated manifest files are not a list")
    declared = {
        entry["filename"]: entry
        for entry in files
        if isinstance(entry, Mapping) and isinstance(entry.get("filename"), str)
    }
    records: dict[str, Mapping[str, object]] = {}
    for filename in sorted(_MODEL_STREAMS):
        entry = declared[filename]
        payload = _FITTER["_read_regular_file"](
            artifact / filename,
            subject=f"{subject} stream",
            maximum_bytes=_FITTER["_MAX_STREAM_BYTES"],
        )
        if len(payload) != entry["bytes"] or hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise RepeatablePartyOutcomeSuccessorFitError(f"{subject} stream failed authentication")
        (record,) = _FITTER["_decode_canonical_jsonl"](
            payload,
            subject=f"{subject} stream",
            expected_records=1,
        )
        records[filename] = record
    return _AuthenticatedModelArtifact(
        artifact=artifact,
        manifest_sha256=manifest_sha256,
        preregistration=records["preregistration.jsonl"],
        learning=records["learning.jsonl"],
        model=records["model.jsonl"],
        model_file_sha256=declared["model.jsonl"]["sha256"],
    )


def _comparison_marginals(
    value: object,
    *,
    subject: str,
) -> tuple[frozenset[str], frozenset[str]]:
    if not isinstance(value, Mapping):
        raise RepeatablePartyOutcomeSuccessorFitError(f"{subject} is invalid")
    roots = value.get("root_lineage_ids")
    states = value.get("state_sha256")
    if (
        not isinstance(roots, list)
        or not isinstance(states, list)
        or len(roots) != len(states)
        or len(roots) != 6
        or any(not isinstance(item, str) or not item for item in roots)
        or any(
            not isinstance(item, str)
            or len(item) != 64
            or any(character not in _HEX for character in item)
            for item in states
        )
    ):
        raise RepeatablePartyOutcomeSuccessorFitError(f"{subject} is invalid")
    root_set = frozenset(roots)
    state_set = frozenset(states)
    if len(root_set) != 6 or len(state_set) != 6:
        raise RepeatablePartyOutcomeSuccessorFitError(f"{subject} repeats a root or state")
    # The producer sorts roots and states independently.  Their positions do
    # not encode root/state associations, so authenticate the two exact
    # marginals and bind them to the reconstructed fixed plan after claim.
    return root_set, state_set


def _artifact_identity_is_available(root_path: Path, artifact_id: str) -> bool:
    return not any(
        os.path.lexists(root_path / f"{artifact_id}{suffix}")
        for suffix in ("", ".partial", ".failed.partial")
    )


def _comparison_claim_sha256(
    args: argparse.Namespace,
    *,
    prior_comparison_manifest_sha256: str,
) -> str:
    return canonical_sha256(
        {
            "schema": ("pokemon.red.repeatable-party-outcome-comparison-claim.v1"),
            "predecessor_manifest_sha256": (args.expected_predecessor_manifest_sha256),
            "predecessor_plan_sha256": args.expected_predecessor_plan_sha256,
            "successor_manifest_sha256": args.expected_successor_manifest_sha256,
            "successor_plan_sha256": args.expected_successor_plan_sha256,
            "prior_comparison_manifest_sha256": (prior_comparison_manifest_sha256),
            "comparison_partition": ScenarioPartition.DEVELOPMENT.value,
            "expected_newly_completed_development_questions": (
                args.expected_newly_completed_development_questions
            ),
            "candidate_count": 1,
            "retention_rule": _RETENTION_RULE,
        }
    )


def _prepare_fit_readiness(args: argparse.Namespace) -> _FitReadiness:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_published_source(PROJECT_ROOT, source)
    _require_historical_runner_bytes(args)

    predecessor_path, predecessor_manifest, _predecessor_manifest_sha256 = _read_artifact_manifest(
        args.predecessor_artifact,
        expected_manifest_sha256=args.expected_predecessor_manifest_sha256,
        expected_kind=_FITTER["_PILOT_KIND"],
        expected_streams={
            "evaluation.jsonl": 1,
            "failures.jsonl": args.expected_predecessor_invalid_trials,
            "outcomes.jsonl": args.expected_predecessor_measured_trials,
            "plan.jsonl": 1,
        },
        subject="predecessor artifact",
    )
    successor_path, successor_manifest, _successor_manifest_sha256 = _read_artifact_manifest(
        args.successor_artifact,
        expected_manifest_sha256=args.expected_successor_manifest_sha256,
        expected_kind=_SUCCESSOR_KIND,
        expected_streams={
            "evaluation.jsonl": 1,
            "failures.jsonl": args.expected_successor_invalid_trials,
            "outcomes.jsonl": args.expected_successor_measured_trials,
            "plan.jsonl": 1,
        },
        subject="successor artifact",
    )
    predecessor_plan_record = _read_authenticated_stream_record(
        predecessor_path,
        predecessor_manifest,
        filename="plan.jsonl",
        subject="predecessor plan stream",
    )
    successor_plan_record = _read_authenticated_stream_record(
        successor_path,
        successor_manifest,
        filename="plan.jsonl",
        subject="successor plan stream",
    )
    predecessor_plan, predecessor_inputs, predecessor_dose = _FITTER["_require_plan_record"](
        _PlanOnlyPilot(predecessor_plan_record),
        expected_plan_sha256=args.expected_predecessor_plan_sha256,
        expected_collection_source=args.expected_predecessor_source,
        expected_battle_credit_protocol=args.battle_credit_protocol,
        expected_selection_protocol=args.scenario_selection_protocol,
    )
    base_artifact = _open_authenticated_model_artifact(
        args.base_model_artifact,
        expected_manifest_sha256=(args.expected_base_model_artifact_manifest_sha256),
        subject="base model artifact",
    )
    base_path = _FITTER["_require_external"](
        args.base_model,
        subject="base model",
    )
    if base_path != base_artifact.artifact / "model.jsonl":
        raise RepeatablePartyOutcomeSuccessorFitError(
            "base model path is outside its authenticated artifact"
        )
    base_file_sha256 = _require_sha256(
        args.expected_base_model_file_sha256,
        subject="base model file",
    )
    if base_artifact.model_file_sha256 != base_file_sha256:
        raise RepeatablePartyOutcomeSuccessorFitError(
            "base model stream differs from its expected digest"
        )
    base_model = load_party_development_outcome_model(
        base_path,
        expected_sha256=base_file_sha256,
    )
    base_model_sha256 = canonical_party_development_outcome_model_sha256(base_model)
    if dict(base_artifact.model) != base_model.to_dict():
        raise RepeatablePartyOutcomeSuccessorFitError(
            "base model typed reload differs from its authenticated record"
        )
    base_preregistration = base_artifact.preregistration
    if (
        base_preregistration.get("schema")
        != "pokemon.red.repeatable-party-outcome-fit-preregistration.v1"
        or base_preregistration.get("fit_identity_sha256")
        != _require_sha256(
            args.expected_base_fit_identity_sha256,
            subject="base fit identity",
        )
        or base_preregistration.get("pilot_manifest_sha256")
        != args.expected_base_pilot_manifest_sha256
        or base_preregistration.get("plan_sha256") != args.expected_base_pilot_plan_sha256
        or base_preregistration.get("train_questions")
        != args.expected_base_outcome_training_examples
        or base_preregistration.get("development_questions") != 4
        or base_preregistration.get("development_used_for_tuning") is not False
        or base_preregistration.get("authority_promoted") is not False
    ):
        raise RepeatablePartyOutcomeSuccessorFitError("base model preregistration differs")
    base_updated_development = base_artifact.learning.get("updated_development")
    if (
        base_artifact.learning.get("schema")
        != "pokemon.core.party-development-outcome-learning-cycle.v2"
        or not isinstance(base_updated_development, Mapping)
        or base_updated_development.get("model_sha256") != base_model_sha256
        or base_updated_development.get("example_count") != 4
    ):
        raise RepeatablePartyOutcomeSuccessorFitError("base model learning record differs")
    base_pilot = _FITTER["_open_authenticated_pilot"](
        args.base_pilot_artifact,
        expected_manifest_sha256=args.expected_base_pilot_manifest_sha256,
        expected_measured_trials=args.expected_base_pilot_measured_trials,
        expected_invalid_trials=0,
    )
    _FITTER["_require_plan_record"](
        base_pilot,
        expected_plan_sha256=args.expected_base_pilot_plan_sha256,
        expected_collection_source=args.expected_base_pilot_source,
        expected_battle_credit_protocol=args.base_training_protocol,
        expected_selection_protocol=args.base_scenario_selection_protocol,
    )
    if (
        type(args.expected_base_outcome_training_examples) is not int  # noqa: E721
        or args.expected_base_outcome_training_examples != 8
        or base_model.outcome_training_examples != args.expected_base_outcome_training_examples
        or args.base_training_protocol == "none"
    ):
        raise RepeatablePartyOutcomeSuccessorFitError(
            "base model outcome-training provenance differs"
        )

    prior = _open_authenticated_model_artifact(
        args.previous_comparison_artifact,
        expected_manifest_sha256=(args.expected_previous_comparison_manifest_sha256),
        subject="previous comparison artifact",
    )
    previous = prior.preregistration
    if (
        previous.get("schema") != "pokemon.red.repeatable-party-outcome-fit-preregistration.v2"
        or previous.get("fit_identity_sha256")
        != _require_sha256(
            args.expected_previous_comparison_fit_identity_sha256,
            subject="previous comparison fit identity",
        )
        or previous.get("pilot_manifest_sha256") != args.expected_predecessor_manifest_sha256
        or previous.get("plan_sha256") != args.expected_predecessor_plan_sha256
        or previous.get("base_model_file_sha256") != base_file_sha256
        or previous.get("base_training_protocol") != args.base_training_protocol
        or previous.get("current_battle_credit_protocol") != args.battle_credit_protocol
        or previous.get("train_questions") != args.expected_predecessor_complete_train_questions
        or previous.get("development_questions")
        != args.expected_predecessor_complete_development_questions
        or previous.get("development_used_for_tuning") is not False
        or previous.get("authority_promoted") is not False
    ):
        raise RepeatablePartyOutcomeSuccessorFitError("previous comparison preregistration differs")
    learning = prior.learning
    base_development = learning.get("base_development")
    updated_development = learning.get("updated_development")
    paired_development = learning.get("paired_development")
    prior_roots, prior_states = _comparison_marginals(
        base_development,
        subject="previous comparison development set",
    )
    paired_roots = (
        paired_development.get("root_lineage_ids")
        if isinstance(paired_development, Mapping)
        else None
    )
    if (
        learning.get("schema") != "pokemon.core.party-development-outcome-learning-cycle.v2"
        or _comparison_marginals(
            updated_development,
            subject="previous updated development set",
        )
        != (prior_roots, prior_states)
        or not isinstance(base_development, Mapping)
        or not isinstance(paired_development, Mapping)
        or not isinstance(paired_roots, list)
        or any(not isinstance(item, str) or not item for item in paired_roots)
        or set(paired_roots) != prior_roots
        or paired_development.get("example_count")
        != args.expected_predecessor_complete_development_questions
        or base_development.get("model_sha256") != base_model_sha256
        or base_development.get("example_count")
        != args.expected_predecessor_complete_development_questions
    ):
        raise RepeatablePartyOutcomeSuccessorFitError("previous comparison learning set differs")

    root_path = _FITTER["_require_external"](
        args.private_artifact_root,
        subject="private artifact root",
    )
    shared_root_members = (
        base_artifact.artifact.parent,
        _FITTER["_require_external"](
            args.base_pilot_artifact,
            subject="base pilot artifact",
        ).parent,
        prior.artifact.parent,
        _FITTER["_require_external"](
            args.predecessor_artifact,
            subject="predecessor artifact",
        ).parent,
        _FITTER["_require_external"](
            args.successor_artifact,
            subject="successor artifact",
        ).parent,
    )
    if any(item != root_path for item in shared_root_members):
        raise RepeatablePartyOutcomeSuccessorFitError(
            "fit inputs and comparison claim do not share one private root"
        )
    output_root = open_private_root(
        root_path,
        repository_root=PROJECT_ROOT,
    )
    comparison_claim_sha256 = _comparison_claim_sha256(
        args,
        prior_comparison_manifest_sha256=prior.manifest_sha256,
    )
    artifact_id = f"repeatable-party-outcome-comparison-{comparison_claim_sha256[:32]}"
    if not _artifact_identity_is_available(root_path, artifact_id):
        raise RepeatablePartyOutcomeSuccessorFitError(
            "development comparison identity is already consumed"
        )
    marginal_digest = canonical_sha256(
        {
            "schema": "pokemon.red.party-development-marginal-set.v1",
            "root_lineage_ids": sorted(prior_roots),
            "state_sha256": sorted(prior_states),
        }
    )
    collection = _prepare_collection_readiness(
        args,
        predecessor_plan_record=predecessor_plan_record,
        predecessor_plan=predecessor_plan,
        predecessor_inputs=predecessor_inputs,
        predecessor_dose=predecessor_dose,
        successor_plan_record=successor_plan_record,
    )
    return _FitReadiness(
        source=source,
        base_model=base_model,
        base_model_file_sha256=base_file_sha256,
        base_model_canonical_sha256=base_model_sha256,
        base_model_artifact_manifest_sha256=base_artifact.manifest_sha256,
        prior_comparison_manifest_sha256=prior.manifest_sha256,
        prior_scored_development_roots=prior_roots,
        prior_scored_development_states=prior_states,
        prior_scored_development_marginal_set_sha256=marginal_digest,
        comparison_claim_sha256=comparison_claim_sha256,
        artifact_id=artifact_id,
        output_root=output_root,
        collection=collection,
    )


def _reconstruct_at_collection_source(
    args: argparse.Namespace,
    *,
    predecessor_plan: Mapping[str, object],
) -> Any:
    source_commit = _require_commit(
        args.expected_successor_source,
        subject="successor collection source",
    )
    expected_bundle = _require_sha256(
        args.expected_successor_source_bundle_sha256,
        subject="successor collection source bundle",
    )
    committed_bundle = committed_source_bundle_sha256(
        PROJECT_ROOT,
        revision=source_commit,
    )
    working_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    if committed_bundle != expected_bundle or working_bundle != expected_bundle:
        raise RepeatablePartyOutcomeSuccessorFitError(
            "fit executable package differs from the successor collection source"
        )

    collection_globals = _SUCCESSOR["_COLLECTION"]
    original_detector = collection_globals["detect_source_identity"]
    collection_globals["detect_source_identity"] = lambda *_args, **_kwargs: SourceIdentity(
        source_commit, False
    )
    try:
        return _SUCCESSOR["_reconstruct"](
            args,
            predecessor_plan=predecessor_plan,
        )
    finally:
        collection_globals["detect_source_identity"] = original_detector


def _prepare_collection_readiness(
    args: argparse.Namespace,
    *,
    predecessor_plan_record: Mapping[str, object],
    predecessor_plan: Mapping[str, object],
    predecessor_inputs: Mapping[str, object],
    predecessor_dose: Any,
    successor_plan_record: Mapping[str, object],
) -> _CollectionReadiness:
    frozen = _FITTER["_load_external_json"](
        args.successor_frozen_plan,
        subject="successor frozen plan",
        expected_sha256=_require_sha256(
            args.expected_successor_frozen_plan_file_sha256,
            subject="successor frozen-plan file",
        ),
    )
    reconstruction = _reconstruct_at_collection_source(
        args,
        predecessor_plan=predecessor_plan,
    )
    inputs = _SUCCESSOR["_input_sha256"](reconstruction)
    successor_plan = successor_plan_record.get("successor_plan")
    successor_plan_sha256 = _require_sha256(
        args.expected_successor_plan_sha256,
        subject="successor plan",
    )
    current_plan = reconstruction.plan.public_dict()
    current_plan_sha256 = reconstruction.plan.plan_sha256
    expected_source = {
        "git_commit": _require_commit(
            args.expected_successor_source,
            subject="successor source",
        ),
        "worktree_dirty": False,
    }
    expected_protocol = _SUCCESSOR["_COLLECTION"]["_battle_credit_protocol"](
        predecessor_dose.completed_battles,
        protocol_id=args.battle_credit_protocol,
    )
    plan_keys = {
        "battle_credit_protocol",
        "current_reconstruction_plan",
        "current_reconstruction_plan_sha256",
        "dose",
        "frozen_plan_document_sha256",
        "frozen_plan_file_sha256",
        "inputs",
        "predecessor_manifest_sha256",
        "predecessor_plan_sha256",
        "record_type",
        "rom_sha256",
        "scenario_selection_protocol",
        "sealed",
        "semantic_reconstruction_sha256",
        "source",
        "source_bundle_sha256",
        "successor_plan",
        "successor_plan_sha256",
    }
    if (
        set(successor_plan_record) != plan_keys
        or successor_plan_record.get("record_type") != "repeatable_party_development_successor_plan"
        or not isinstance(successor_plan, Mapping)
        or canonical_sha256(successor_plan) != successor_plan_sha256
        or successor_plan_record.get("successor_plan_sha256") != successor_plan_sha256
        or successor_plan_record.get("predecessor_manifest_sha256")
        != args.expected_predecessor_manifest_sha256
        or successor_plan_record.get("predecessor_plan_sha256")
        != args.expected_predecessor_plan_sha256
        or successor_plan_record.get("current_reconstruction_plan") != current_plan
        or successor_plan_record.get("current_reconstruction_plan_sha256") != current_plan_sha256
        or successor_plan_record.get("dose") != predecessor_dose.public_dict()
        or successor_plan_record.get("inputs") != inputs
        or predecessor_inputs != inputs
        or successor_plan_record.get("source") != expected_source
        or successor_plan_record.get("source_bundle_sha256") != reconstruction.source_bundle_sha256
        or successor_plan_record.get("rom_sha256") != reconstruction.fingerprint.sha256
        or successor_plan_record.get("battle_credit_protocol") != expected_protocol
        or successor_plan_record.get("scenario_selection_protocol")
        != args.scenario_selection_protocol
        or successor_plan_record.get("sealed") is not False
        or successor_plan_record.get("frozen_plan_file_sha256")
        != args.expected_successor_frozen_plan_file_sha256
        or successor_plan_record.get("frozen_plan_document_sha256") != canonical_sha256(frozen)
    ):
        raise RepeatablePartyOutcomeSuccessorFitError(
            "claim-safe reconstruction differs from the authenticated plans"
        )
    frozen_keys = {
        "active_lane",
        "authority_promoted",
        "candidate_trial_denominator",
        "claimed_trial_count",
        "controller_actions",
        "crystal_cases_opened",
        "full_game_replays",
        "input_file_sha256",
        "model_fits",
        "model_predictions",
        "private_path_fields",
        "question_count",
        "rom_sha256",
        "scenario_selection_protocol",
        "schema",
        "sealed_red_cases_opened",
        "source_bundle_sha256",
        "source_commit",
        "successor_plan",
        "successor_plan_sha256",
        "teacher_queries",
    }
    if (
        set(frozen) != frozen_keys
        or frozen.get("schema")
        != "pokemon.red.repeatable-party-development-successor-frozen-plan.v1"
        or frozen.get("active_lane") != "repeatable-party-outcome-learning-v1"
        or frozen.get("candidate_trial_denominator")
        != args.expected_predecessor_measured_trials + args.expected_predecessor_invalid_trials
        or frozen.get("claimed_trial_count") != args.expected_predecessor_invalid_trials
        or frozen.get("question_count") != args.train_count + args.development_count
        or frozen.get("input_file_sha256") != inputs
        or frozen.get("rom_sha256") != reconstruction.fingerprint.sha256
        or frozen.get("scenario_selection_protocol") != args.scenario_selection_protocol
        or frozen.get("source_bundle_sha256") != reconstruction.source_bundle_sha256
        or frozen.get("source_commit") != expected_source["git_commit"]
        or frozen.get("successor_plan") != successor_plan
        or frozen.get("successor_plan_sha256") != successor_plan_sha256
        or any(
            frozen.get(field) != expected
            for field, expected in {
                "authority_promoted": False,
                "controller_actions": 0,
                "crystal_cases_opened": 0,
                "full_game_replays": 0,
                "model_fits": 0,
                "model_predictions": 0,
                "private_path_fields": 0,
                "sealed_red_cases_opened": 0,
                "teacher_queries": 0,
            }.items()
        )
    ):
        raise RepeatablePartyOutcomeSuccessorFitError(
            "successor frozen plan differs from claim-safe reconstruction"
        )
    return _CollectionReadiness(
        reconstruction=reconstruction,
        predecessor_plan_record=predecessor_plan_record,
        predecessor_plan=predecessor_plan,
        predecessor_dose=predecessor_dose,
        successor_plan_record=successor_plan_record,
        input_sha256=inputs,
    )


def _expected_successor_plan_record(
    args: argparse.Namespace,
    reconstruction: Any,
    predecessor: Any,
) -> tuple[dict[str, object], str]:
    plan_core = _SUCCESSOR["_successor_plan_core"](
        args,
        reconstruction,
        predecessor,
    )
    plan_sha256 = canonical_sha256(plan_core)
    if plan_sha256 != _require_sha256(
        args.expected_successor_plan_sha256,
        subject="successor plan",
    ):
        raise RepeatablePartyOutcomeSuccessorFitError("reconstructed successor plan differs")
    frozen = _SUCCESSOR["_frozen_document"](
        args,
        reconstruction,
        predecessor,
        plan_core,
    )
    frozen_file = _FITTER["_load_external_json"](
        args.successor_frozen_plan,
        subject="successor frozen plan",
        expected_sha256=_require_sha256(
            args.expected_successor_frozen_plan_file_sha256,
            subject="successor frozen-plan file",
        ),
    )
    if frozen_file != frozen:
        raise RepeatablePartyOutcomeSuccessorFitError(
            "successor frozen plan differs from its reconstruction"
        )
    expected = {
        "record_type": "repeatable_party_development_successor_plan",
        "successor_plan": plan_core,
        "successor_plan_sha256": plan_sha256,
        "predecessor_manifest_sha256": predecessor.pilot.manifest_sha256,
        "predecessor_plan_sha256": args.expected_predecessor_plan_sha256,
        "current_reconstruction_plan": reconstruction.plan.public_dict(),
        "current_reconstruction_plan_sha256": reconstruction.plan.plan_sha256,
        "semantic_reconstruction_sha256": (predecessor.semantic_reconstruction_sha256),
        "dose": predecessor.dose.public_dict(),
        "source": reconstruction.source.public_dict(),
        "source_bundle_sha256": reconstruction.source_bundle_sha256,
        "rom_sha256": reconstruction.fingerprint.sha256,
        "inputs": _SUCCESSOR["_input_sha256"](reconstruction),
        "battle_credit_protocol": _SUCCESSOR["_COLLECTION"]["_battle_credit_protocol"](
            predecessor.dose.completed_battles,
            protocol_id=args.battle_credit_protocol,
        ),
        "scenario_selection_protocol": args.scenario_selection_protocol,
        "sealed": False,
        "frozen_plan_document_sha256": canonical_sha256(frozen),
        "frozen_plan_file_sha256": args.expected_successor_frozen_plan_file_sha256,
    }
    return expected, plan_sha256


def _joined_candidate_outcomes(
    predecessor: Any,
    successor_artifact: Any,
) -> dict[str, dict[int, CandidateOutcome]]:
    joined = {
        scenario_id: dict(outcomes)
        for scenario_id, outcomes in predecessor.inherited_outcomes.items()
    }
    expected = {
        predecessor.current_assignments[key].trial_id: (predecessor.current_assignments[key])
        for key in predecessor.claim_keys
    }
    seen: set[str] = set()
    for records, decoder in (
        (successor_artifact.outcome_records, _FITTER["_candidate_outcome"]),
        (successor_artifact.failure_records, _FITTER["_candidate_failure"]),
    ):
        for record in records:
            assignment = _FITTER["_record_assignment"](record)
            frozen = expected.get(assignment.trial_id)
            if frozen is None or assignment != frozen or assignment.trial_id in seen:
                raise RepeatablePartyOutcomeSuccessorFitError(
                    "successor terminal is outside or repeats its frozen claim set"
                )
            seen.add(assignment.trial_id)
            outcome = decoder(record, expected_assignment=frozen)
            scenario = joined.setdefault(assignment.scenario_id, {})
            if assignment.candidate_index in scenario:
                raise RepeatablePartyOutcomeSuccessorFitError(
                    "successor overwrites inherited measured evidence"
                )
            scenario[assignment.candidate_index] = outcome
    if seen != set(expected):
        raise RepeatablePartyOutcomeSuccessorFitError(
            "successor terminal set differs from its frozen claims"
        )
    return joined


def _eligible_partition_counts(
    examples: tuple[ScenarioOutcomeExample, ...],
) -> Counter[ScenarioPartition]:
    return Counter(item.partition for item in examples if item.learner_update_eligible)


def _example_composition(
    examples: tuple[ScenarioOutcomeExample, ...],
    *,
    bindings: Mapping[str, Any],
) -> tuple[tuple[tuple[str, int], ...], tuple[tuple[str, int], ...]]:
    try:
        selected = tuple(bindings[item.scenario_id] for item in examples)
    except KeyError as error:
        raise RepeatablePartyOutcomeSuccessorFitError(
            "learner example is absent from the reconstructed binding set"
        ) from error
    kind_counts = Counter(item.kind.value for item in selected)
    goal_counts = Counter(item.goal.value for item in selected)
    return tuple(sorted(kind_counts.items())), tuple(sorted(goal_counts.items()))


def _newly_completed_development_examples(
    before: tuple[ScenarioOutcomeExample, ...],
    joined: tuple[ScenarioOutcomeExample, ...],
) -> tuple[ScenarioOutcomeExample, ...]:
    before_by_scenario = {item.scenario_id: item for item in before}
    if len(before_by_scenario) != len(before):
        raise RepeatablePartyOutcomeSuccessorFitError("predecessor examples repeat a scenario")
    newly_completed = tuple(
        item
        for item in joined
        if item.partition is ScenarioPartition.DEVELOPMENT
        and item.learner_update_eligible
        and not before_by_scenario[item.scenario_id].learner_update_eligible
    )
    return newly_completed


def _reconstruct_joined_dataset(
    args: argparse.Namespace,
    readiness: _FitReadiness,
) -> _JoinedDataset:
    collection = readiness.collection
    predecessor_pilot = _FITTER["_open_authenticated_pilot"](
        args.predecessor_artifact,
        expected_manifest_sha256=args.expected_predecessor_manifest_sha256,
        expected_measured_trials=args.expected_predecessor_measured_trials,
        expected_invalid_trials=args.expected_predecessor_invalid_trials,
    )
    predecessor_plan, inputs, dose = _FITTER["_require_plan_record"](
        predecessor_pilot,
        expected_plan_sha256=args.expected_predecessor_plan_sha256,
        expected_collection_source=args.expected_predecessor_source,
        expected_battle_credit_protocol=args.battle_credit_protocol,
        expected_selection_protocol=args.scenario_selection_protocol,
    )
    if (
        dict(predecessor_pilot.plan_record) != dict(collection.predecessor_plan_record)
        or predecessor_plan != collection.predecessor_plan
        or inputs != collection.input_sha256
        or dose != collection.predecessor_dose
    ):
        raise RepeatablePartyOutcomeSuccessorFitError(
            "predecessor plan changed after claim-safe reconstruction"
        )
    reconstruction = collection.reconstruction
    predecessor = _SUCCESSOR["_bind_predecessor"](
        args,
        reconstruction,
        pilot=predecessor_pilot,
        old_plan=predecessor_plan,
        dose=dose,
    )
    successor_artifact = _FITTER["_open_authenticated_pilot"](
        args.successor_artifact,
        expected_manifest_sha256=args.expected_successor_manifest_sha256,
        expected_measured_trials=args.expected_successor_measured_trials,
        expected_invalid_trials=args.expected_successor_invalid_trials,
        expected_kind=_SUCCESSOR_KIND,
    )
    expected_plan_record, successor_plan_sha256 = _expected_successor_plan_record(
        args,
        reconstruction,
        predecessor,
    )
    if (
        dict(successor_artifact.plan_record) != dict(collection.successor_plan_record)
        or dict(successor_artifact.plan_record) != expected_plan_record
    ):
        raise RepeatablePartyOutcomeSuccessorFitError(
            "successor plan record differs from its authenticated reconstruction"
        )

    joined_outcomes = _joined_candidate_outcomes(predecessor, successor_artifact)
    before_examples = tuple(
        _SUCCESSOR["_COLLECTION"]["_assemble_examples"](
            reconstruction.selected,
            predecessor.inherited_outcomes,
        )
    )
    joined_examples = tuple(
        _SUCCESSOR["_COLLECTION"]["_assemble_examples"](
            reconstruction.selected,
            joined_outcomes,
        )
    )
    prospective = PartyDevelopmentProspectiveCatalog.freeze(
        tuple(item.binding_question.binding for item in reconstruction.selected)
    )
    audit = audit_party_development_outcome_catalog(
        joined_examples,
        prospective_catalog=prospective,
        policy=PartyDevelopmentReadinessPolicy(
            minimum_train_examples=args.train_count,
            minimum_development_examples=args.development_count,
            minimum_goals_per_partition=2,
            minimum_candidate_count_observed=3,
            minimum_health_bins=2,
            minimum_pp_bins=1,
            minimum_survival_bins=2,
            minimum_evolution_route_kinds=2,
            minimum_semantic_menus_per_partition=min(3, args.development_count),
            require_complete_venue_priors=False,
        ),
    )
    expected_evaluation = {
        "record_type": "repeatable_party_development_successor_audit",
        "audit": audit.public_dict(),
        "inherited_measured_trials": args.expected_predecessor_measured_trials,
        "claimed_trials": args.expected_predecessor_invalid_trials,
        "model_fit": False,
        "authority_promoted": False,
    }
    if dict(successor_artifact.evaluation_record) != expected_evaluation:
        raise RepeatablePartyOutcomeSuccessorFitError(
            "successor evaluation differs from joined outcomes"
        )

    before_counts = _eligible_partition_counts(before_examples)
    joined_counts = _eligible_partition_counts(joined_examples)
    training = tuple(
        item
        for item in joined_examples
        if item.partition is ScenarioPartition.TRAIN and item.learner_update_eligible
    )
    joined_development = tuple(
        item
        for item in joined_examples
        if item.partition is ScenarioPartition.DEVELOPMENT and item.learner_update_eligible
    )
    newly_completed_development = _newly_completed_development_examples(
        before_examples,
        joined_examples,
    )
    previous_development = tuple(
        item
        for item in joined_development
        if item.scenario_id
        not in {completed.scenario_id for completed in newly_completed_development}
    )
    bindings = {
        item.binding_question.scenario_id: item.binding_question.binding
        for item in reconstruction.selected
    }
    training_kind_counts, training_goal_counts = _example_composition(
        training,
        bindings=bindings,
    )
    (
        newly_completed_development_kind_counts,
        newly_completed_development_goal_counts,
    ) = _example_composition(
        newly_completed_development,
        bindings=bindings,
    )
    if (
        before_counts[ScenarioPartition.TRAIN] != args.expected_predecessor_complete_train_questions
        or before_counts[ScenarioPartition.DEVELOPMENT]
        != args.expected_predecessor_complete_development_questions
        or joined_counts[ScenarioPartition.TRAIN] != args.expected_fit_train_questions
        or joined_counts[ScenarioPartition.DEVELOPMENT]
        != args.expected_joined_development_questions
        or len(training) != args.expected_fit_train_questions
        or len(newly_completed_development) != args.expected_newly_completed_development_questions
        or len(previous_development) != args.expected_predecessor_complete_development_questions
        or dict(training_kind_counts) != _EXPECTED_TRAIN_KIND_COUNTS
        or dict(training_goal_counts) != _EXPECTED_TRAIN_GOAL_COUNTS
        or dict(newly_completed_development_kind_counts) != _EXPECTED_NEW_DEVELOPMENT_KIND_COUNTS
        or dict(newly_completed_development_goal_counts) != _EXPECTED_NEW_DEVELOPMENT_GOAL_COUNTS
    ):
        raise RepeatablePartyOutcomeSuccessorFitError(
            "joined or newly completed question counts differ from the preregistered fit gate"
        )
    return _JoinedDataset(
        examples=joined_examples,
        training=training,
        newly_completed_development=newly_completed_development,
        previously_observed_development=previous_development,
        prospective_catalog_sha256=prospective.catalog_sha256,
        predecessor_manifest_sha256=predecessor_pilot.manifest_sha256,
        successor_manifest_sha256=successor_artifact.manifest_sha256,
        predecessor_plan_sha256=args.expected_predecessor_plan_sha256,
        successor_plan_sha256=successor_plan_sha256,
        semantic_reconstruction_sha256=(predecessor.semantic_reconstruction_sha256),
        collection_source_commit=reconstruction.source.git_commit,
        collection_source_bundle_sha256=reconstruction.source_bundle_sha256,
        rom_sha256=reconstruction.fingerprint.sha256,
        predecessor_measured_trials=args.expected_predecessor_measured_trials,
        successor_measured_trials=args.expected_successor_measured_trials,
        successor_invalid_trials=args.expected_successor_invalid_trials,
        training_kind_counts=training_kind_counts,
        training_goal_counts=training_goal_counts,
        newly_completed_development_kind_counts=(newly_completed_development_kind_counts),
        newly_completed_development_goal_counts=(newly_completed_development_goal_counts),
    )


def _question_set_sha256(
    examples: tuple[ScenarioOutcomeExample, ...],
    *,
    role: str,
) -> str:
    return canonical_sha256(
        {
            "schema": "pokemon.red.repeatable-party-outcome-question-set.v1",
            "role": role,
            "questions": [
                {
                    "scenario_id": item.scenario_id,
                    "root_lineage_id": item.root_lineage_id,
                    "initial_state_sha256": item.initial_state_sha256,
                    "prospective_binding_sha256": item.prospective_binding_sha256,
                }
                for item in examples
            ],
        }
    )


def _require_previous_comparison_boundary(
    dataset: _JoinedDataset,
    readiness: _FitReadiness,
) -> None:
    reconstructed_roots = frozenset(
        item.root_lineage_id for item in dataset.previously_observed_development
    )
    reconstructed_states = frozenset(
        item.initial_state_sha256 for item in dataset.previously_observed_development
    )
    if (
        len(reconstructed_roots) != len(dataset.previously_observed_development)
        or len(reconstructed_states) != len(dataset.previously_observed_development)
        or reconstructed_roots != readiness.prior_scored_development_roots
        or reconstructed_states != readiness.prior_scored_development_states
    ):
        raise RepeatablePartyOutcomeSuccessorFitError(
            "previously scored development set differs from its authenticated fit"
        )


def _retention_decision(cycle: Any) -> dict[str, object]:
    base = cycle.base_development
    updated = cycle.updated_development
    paired = cycle.paired_development
    checks = {
        "accuracy_did_not_decrease": updated.accuracy >= base.accuracy,
        "cross_entropy_decreased": updated.cross_entropy < base.cross_entropy,
        "mean_winner_probability_increased": (paired.mean_winner_probability_delta > 0),
        "updated_paired_wins_exceeded_base_wins": (paired.updated_wins > paired.base_wins),
    }
    retained = all(checks.values())
    return {
        "candidate_retained_for_shadow_design": retained,
        "checks": checks,
        "decision": (
            "retain_for_separate_shadow_design" if retained else "reject_and_redesign_learner"
        ),
        "inferential_claim": False,
        "mixed_result_is_failure": True,
        "rule": _RETENTION_RULE,
    }


def _fit(args: argparse.Namespace) -> dict[str, object]:
    readiness = _prepare_fit_readiness(args)
    if args.preflight_only:
        return {
            "schema": ("pokemon.red.repeatable-party-outcome-successor-fit-preflight.v1"),
            "status": "ready_for_one_shot_comparison_claim",
            "source": readiness.source.public_dict(),
            "comparison_claim_sha256": readiness.comparison_claim_sha256,
            "predecessor_manifest_sha256": (args.expected_predecessor_manifest_sha256),
            "successor_manifest_sha256": args.expected_successor_manifest_sha256,
            "prior_comparison_manifest_sha256": (readiness.prior_comparison_manifest_sha256),
            "base_model_artifact_manifest_sha256": (readiness.base_model_artifact_manifest_sha256),
            "expected_questions": {
                "train": args.expected_fit_train_questions,
                "newly_completed_development": (
                    args.expected_newly_completed_development_questions
                ),
            },
            "candidate_count": 1,
            "retention_rule": _RETENTION_RULE,
            "comparison_identity_available": True,
            "claim_safe_reconstruction_complete": True,
            "input_sha256": dict(readiness.collection.input_sha256),
            "reconstruction_plan_sha256": (readiness.collection.reconstruction.plan.plan_sha256),
            "rom_sha256": readiness.collection.reconstruction.fingerprint.sha256,
            "joined_labels_decoded": 0,
            "candidate_trials_started": 0,
            "controller_actions": 0,
            "model_fits": 0,
            "model_updates": 0,
            "development_comparisons": 0,
            "teacher_queries": 0,
            "sealed_red_cases_opened": 0,
            "crystal_cases_opened": 0,
            "full_game_replays": 0,
            "authority_promoted": False,
            "private_path_fields": 0,
        }
    comparison_claim = {
        "schema": "pokemon.red.repeatable-party-outcome-comparison-claim.v1",
        "comparison_claim_sha256": readiness.comparison_claim_sha256,
        "source": readiness.source.public_dict(),
        "predecessor_manifest_sha256": args.expected_predecessor_manifest_sha256,
        "predecessor_plan_sha256": args.expected_predecessor_plan_sha256,
        "successor_manifest_sha256": args.expected_successor_manifest_sha256,
        "successor_plan_sha256": args.expected_successor_plan_sha256,
        "prior_comparison_manifest_sha256": (readiness.prior_comparison_manifest_sha256),
        "base_model_artifact_manifest_sha256": (readiness.base_model_artifact_manifest_sha256),
        "comparison_partition": ScenarioPartition.DEVELOPMENT.value,
        "expected_newly_completed_development_questions": (
            args.expected_newly_completed_development_questions
        ),
        "candidate_count": 1,
        "candidate_selection": "sole_fixed_hyperparameter_update",
        "retention_rule": _RETENTION_RULE,
        "labels_decoded_before_claim": False,
        "retry_with_changed_base_or_hyperparameters": False,
        "development_used_for_tuning": False,
        "sealed_red_cases_opened": 0,
        "crystal_cases_opened": 0,
        "full_game_replays": 0,
        "authority_promoted": False,
        "private_path_fields": 0,
    }
    writer = readiness.output_root.begin_artifact(
        readiness.artifact_id,
        kind=_MODEL_KIND,
    )
    with writer:
        writer.append("claim", comparison_claim, durable=True)
        dataset = _reconstruct_joined_dataset(args, readiness)
        _require_previous_comparison_boundary(dataset, readiness)
        training_set_sha256 = _question_set_sha256(dataset.training, role="train")
        newly_completed_development_set_sha256 = _question_set_sha256(
            dataset.newly_completed_development,
            role="newly_completed_development",
        )
        previously_scored_set_sha256 = _question_set_sha256(
            dataset.previously_observed_development,
            role="previously_scored_development_excluded",
        )
        fit_identity = canonical_sha256(
            {
                "schema": ("pokemon.red.repeatable-party-outcome-successor-fit-identity.v2"),
                "comparison_claim_sha256": readiness.comparison_claim_sha256,
                "base_model_file_sha256": readiness.base_model_file_sha256,
                "base_model_canonical_sha256": (readiness.base_model_canonical_sha256),
                "base_outcome_training_examples": (readiness.base_model.outcome_training_examples),
                "base_training_protocol": args.base_training_protocol,
                "current_battle_credit_protocol": args.battle_credit_protocol,
                "training_question_set_sha256": training_set_sha256,
                "newly_completed_development_question_set_sha256": (
                    newly_completed_development_set_sha256
                ),
                "previously_scored_development_excluded_sha256": (previously_scored_set_sha256),
                "hyperparameters": {
                    "epochs": _FIT_EPOCHS,
                    "learning_rate": _FIT_LEARNING_RATE,
                    "prior_l2": _FIT_PRIOR_L2,
                },
            }
        )
        preregistration = {
            "schema": ("pokemon.red.repeatable-party-outcome-successor-fit-preregistration.v2"),
            "comparison_claim_sha256": readiness.comparison_claim_sha256,
            "fit_identity_sha256": fit_identity,
            "source": readiness.source.public_dict(),
            "predecessor_manifest_sha256": dataset.predecessor_manifest_sha256,
            "successor_manifest_sha256": dataset.successor_manifest_sha256,
            "predecessor_plan_sha256": dataset.predecessor_plan_sha256,
            "successor_plan_sha256": dataset.successor_plan_sha256,
            "semantic_reconstruction_sha256": (dataset.semantic_reconstruction_sha256),
            "prospective_catalog_sha256": dataset.prospective_catalog_sha256,
            "collection_source_commit": dataset.collection_source_commit,
            "collection_source_bundle_sha256": (dataset.collection_source_bundle_sha256),
            "rom_sha256": dataset.rom_sha256,
            "base_model_file_sha256": readiness.base_model_file_sha256,
            "base_model_canonical_sha256": (readiness.base_model_canonical_sha256),
            "base_model_artifact_manifest_sha256": (readiness.base_model_artifact_manifest_sha256),
            "base_outcome_training_examples": (readiness.base_model.outcome_training_examples),
            "base_training_protocol": args.base_training_protocol,
            "current_battle_credit_protocol": args.battle_credit_protocol,
            "cross_protocol_sequential_update": (
                args.base_training_protocol != args.battle_credit_protocol
            ),
            "prior_comparison_manifest_sha256": (readiness.prior_comparison_manifest_sha256),
            "prior_scored_development_marginal_set_sha256": (
                readiness.prior_scored_development_marginal_set_sha256
            ),
            "training_question_set_sha256": training_set_sha256,
            "newly_completed_development_question_set_sha256": (
                newly_completed_development_set_sha256
            ),
            "previously_scored_development_excluded_sha256": (previously_scored_set_sha256),
            "train_questions": len(dataset.training),
            "newly_completed_development_questions": len(dataset.newly_completed_development),
            "newly_completed_labels_are_untouched_roots": False,
            "newly_completed_labels_previously_scored": False,
            "previously_scored_development_questions_excluded": len(
                dataset.previously_observed_development
            ),
            "training_kind_counts": dict(dataset.training_kind_counts),
            "training_goal_counts": dict(dataset.training_goal_counts),
            "newly_completed_development_kind_counts": dict(
                dataset.newly_completed_development_kind_counts
            ),
            "newly_completed_development_goal_counts": dict(
                dataset.newly_completed_development_goal_counts
            ),
            "predecessor_measured_trials": dataset.predecessor_measured_trials,
            "successor_measured_trials": dataset.successor_measured_trials,
            "successor_invalid_trials": dataset.successor_invalid_trials,
            "candidate_count": 1,
            "candidate_selection": "sole_fixed_hyperparameter_update",
            "retention_rule": _RETENTION_RULE,
            "epochs": _FIT_EPOCHS,
            "learning_rate": _FIT_LEARNING_RATE,
            "prior_l2": _FIT_PRIOR_L2,
            "fit_partition": ScenarioPartition.TRAIN.value,
            "comparison_partition": ScenarioPartition.DEVELOPMENT.value,
            "development_used_for_tuning": False,
            "retry_same_comparison_identity": False,
            "sealed_red_cases_opened": 0,
            "crystal_cases_opened": 0,
            "full_game_replays": 0,
            "authority_promoted": False,
            "private_path_fields": 0,
        }
        writer.append("preregistration", preregistration, durable=True)
        cycle = run_party_development_outcome_learning_cycle(
            readiness.base_model,
            training_examples=dataset.training,
            development_examples=dataset.newly_completed_development,
            epochs=_FIT_EPOCHS,
            learning_rate=_FIT_LEARNING_RATE,
            prior_l2=_FIT_PRIOR_L2,
        )
        writer.append("model", cycle.update.model.to_dict(), durable=True)
        writer.append("learning", cycle.public_dict(), durable=True)
        decision = _retention_decision(cycle)
        writer.append("decision", decision, durable=True)

    model_payload = _FITTER["_canonical_line"](cycle.update.model.to_dict())
    return {
        "schema": "pokemon.red.repeatable-party-outcome-successor-fit-receipt.v2",
        "status": "complete",
        "source": readiness.source.public_dict(),
        "comparison_claim_sha256": readiness.comparison_claim_sha256,
        "fit_identity_sha256": fit_identity,
        "predecessor_manifest_sha256": dataset.predecessor_manifest_sha256,
        "successor_manifest_sha256": dataset.successor_manifest_sha256,
        "predecessor_plan_sha256": dataset.predecessor_plan_sha256,
        "successor_plan_sha256": dataset.successor_plan_sha256,
        "semantic_reconstruction_sha256": dataset.semantic_reconstruction_sha256,
        "prospective_catalog_sha256": dataset.prospective_catalog_sha256,
        "base_model_file_sha256": readiness.base_model_file_sha256,
        "base_model_canonical_sha256": readiness.base_model_canonical_sha256,
        "base_model_artifact_manifest_sha256": (readiness.base_model_artifact_manifest_sha256),
        "base_outcome_training_examples": (readiness.base_model.outcome_training_examples),
        "base_training_protocol": args.base_training_protocol,
        "current_battle_credit_protocol": args.battle_credit_protocol,
        "cross_protocol_sequential_update": (
            args.base_training_protocol != args.battle_credit_protocol
        ),
        "training_question_set_sha256": training_set_sha256,
        "newly_completed_development_question_set_sha256": (newly_completed_development_set_sha256),
        "previously_scored_development_excluded_sha256": (previously_scored_set_sha256),
        "usable_questions": {
            "train": len(dataset.training),
            "newly_completed_development": len(dataset.newly_completed_development),
        },
        "excluded_previously_scored_development_questions": len(
            dataset.previously_observed_development
        ),
        "composition": {
            "train_kind": dict(dataset.training_kind_counts),
            "train_goal": dict(dataset.training_goal_counts),
            "newly_completed_development_kind": dict(
                dataset.newly_completed_development_kind_counts
            ),
            "newly_completed_development_goal": dict(
                dataset.newly_completed_development_goal_counts
            ),
        },
        "joined_questions": {
            "complete": sum(item.fully_measured for item in dataset.examples),
            "censored": sum(not item.fully_measured for item in dataset.examples),
        },
        "trials": {
            "predecessor_measured": dataset.predecessor_measured_trials,
            "successor_measured": dataset.successor_measured_trials,
            "successor_invalid": dataset.successor_invalid_trials,
        },
        "updated_model_file_sha256": hashlib.sha256(model_payload).hexdigest(),
        "updated_model_canonical_sha256": (
            canonical_party_development_outcome_model_sha256(cycle.update.model)
        ),
        "updated_outcome_training_examples": (cycle.update.model.outcome_training_examples),
        "model_artifact": writer.summary.public_dict(),
        "learning": _FITTER["_public_learning_summary"](cycle),
        "retention_decision": decision,
        "model_fits": 1,
        "model_updates": 1,
        "newly_completed_development_comparisons": 1,
        "development_used_for_tuning": False,
        "teacher_queries": 0,
        "teacher_choice_targets": 0,
        "sealed_red_cases_opened": 0,
        "crystal_cases_opened": 0,
        "full_game_replays": 0,
        "authority_promoted": False,
        "inferential_claim": False,
        "joined_labels_decoded_before_durable_comparison_claim": False,
        "private_identity_fields": 0,
        "private_path_fields": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        result = _fit(parser.parse_args(argv))
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        parser.error(f"repeatable party successor fit failed closed: {error}")
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
