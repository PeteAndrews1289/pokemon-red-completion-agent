#!/usr/bin/env python3
"""Run one frozen Red train-only party architecture-selection gate.

The gate authenticates the completed repeatable-outcome lineage while keeping
every consumed development outcome opaque. Before the durable claim it parses
only assignment headers, proves the exact 22-question train identity and
composition, pins the historical score-preserving zero-outcome prior, and
checks both local and fixed-host-account one-shot ledgers. After the claim it decodes
only train outcome payloads, runs a deterministic representation falsifier, and
fits at most one fixed residual-ranker design.

This is train-only architecture-selection evidence, not independent
generalization. It grants no Red authority, Crystal access, sealed evaluation,
development execution, or full-game replay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import runpy
import stat
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from protocol_consistent_party_learning import (  # noqa: E402
    PORTABLE_GROUP_NAMES,
    PROTOCOL_DESIGN_ID,
    PROTOCOL_NEWTON_STEPS,
    PROTOCOL_PAIRWISE_RIDGE,
    ProtocolPartyRanker,
    audit_protocol_party_representation,
    canonical_protocol_party_ranker_sha256,
    run_protocol_party_leave_one_root_out,
)

from pokemon_red_completion.party_development_outcome_campaign import (  # noqa: E402
    PartyDevelopmentOutcomeTrialAssignment,
)
from pokemon_red_completion.party_development_outcome_learning import (  # noqa: E402
    PartyDevelopmentOutcomeModel,
    canonical_party_development_outcome_model_sha256,
    load_party_development_outcome_model,
)
from pokemon_red_completion.private_artifacts import open_private_root  # noqa: E402
from pokemon_red_completion.provenance import (  # noqa: E402
    SourceIdentity,
    canonical_sha256,
    detect_source_identity,
    require_published_source,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402
from pokemon_red_completion.scenario_outcomes import ScenarioOutcomeExample  # noqa: E402

_JOINED_FIT = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "fit_repeatable_party_outcome_successor_model.py")
)
_FITTER = _JOINED_FIT["_FITTER"]
_SUCCESSOR = _JOINED_FIT["_SUCCESSOR"]
_COLLECTION = _SUCCESSOR["_COLLECTION"]

_KIND = "protocol_consistent_party_train_gate_v2"
_EXPECTED_TRAIN_QUESTIONS = 22
_EXPECTED_TRAINING_QUESTION_SET_SHA256 = (
    "b1949d0b2e0c429bc7c2b8389050499ac336b0c2f62dade7565e0471d28986fe"
)
_EXPECTED_TRAIN_OUTCOME_SUBSET_SHA256 = (
    "5b47b7f4872be02f566cd6e5321c868231aa0c705f1c3fb06f4e49e0b3ed8647"
)
_EXPECTED_TRAIN_KIND_COUNTS = {"trainee": 13, "venue": 9}
_EXPECTED_TRAIN_GOAL_COUNTS = {
    "balance": 13,
    "collection": 3,
    "evolution": 3,
    "role_coverage": 3,
}
_EXPECTED_TRAIN_ACTION_GOAL_COUNTS = {
    "trainee:balance": 13,
    "venue:collection": 3,
    "venue:evolution": 3,
    "venue:role_coverage": 3,
}
_EXPECTED_PREDECESSOR_COMPLETE = {"train": 18, "development": 6}
_EXPECTED_JOINED_COMPLETE = {"train": 22, "development": 11}
_EXPECTED_NEWLY_COMPLETED_DEVELOPMENT = 5

_PRIOR_FILE_SHA256 = "575b77d1f6448248c947fed0bf82296210d560df0dca8989505ffc5516507d06"
_PRIOR_CANONICAL_SHA256 = "583061b2b5e4579b246b75dddc896a842e65847696eaa43deb1000a58c156fa9"
_PRIOR_ATTESTATION = (
    PROJECT_ROOT / "docs" / "evidence" / "party-development-v2-prior-initialization-2026-08-15.json"
)
_PRIOR_ATTESTATION_SHA256 = "6ee20ab898f255c19af18364a11d82b6dab8e42deec3c92c2a92975b74a26daa"

_PASS_RULE = {
    "cross_entropy_must_decrease": True,
    "every_action_slice_must_not_regress": True,
    "every_goal_slice_must_not_regress": True,
    "mean_winner_probability_must_increase": True,
    "mixed_result_is_failure": True,
    "overall_accuracy_must_increase": True,
    "updated_paired_wins_must_exceed_base_wins": True,
}


class ProtocolPartyTrainGateError(RuntimeError):
    """Raised when the train-only gate cannot prove its boundary."""


@dataclass(frozen=True, slots=True)
class _RawTerminal:
    assignment: PartyDevelopmentOutcomeTrialAssignment
    record_type: str
    raw_line: bytes


@dataclass(frozen=True, slots=True)
class _TrainBoundary:
    selected: tuple[Any, ...]
    outcome_records: tuple[_RawTerminal, ...]
    training_question_set_sha256: str
    training_outcome_subset_sha256: str
    training_kind_counts: Mapping[str, int]
    training_goal_counts: Mapping[str, int]
    training_action_goal_counts: Mapping[str, int]
    authenticated_terminal_records: int
    development_assignment_headers_authenticated: int
    predecessor_complete_counts: Mapping[str, int]
    joined_complete_counts: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class _Readiness:
    source: SourceIdentity
    prior_model: PartyDevelopmentOutcomeModel
    predecessor_manifest_sha256: str
    successor_manifest_sha256: str
    gate_identity_sha256: str
    artifact_id: str
    output_root: Any
    boundary: _TrainBoundary
    claim_registry: Path
    runner_sha256: str
    learner_sha256: str


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
    parser.add_argument("--prior-model", type=Path, required=True)
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
    parser.add_argument("--expected-successor-runner-sha256", required=True)
    parser.add_argument("--expected-development-runner-sha256", required=True)
    parser.add_argument("--expected-executable-source", required=True)
    parser.add_argument("--expected-train-gate-runner-sha256", required=True)
    parser.add_argument("--expected-protocol-learner-sha256", required=True)
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
        help="authenticate every label-free prerequisite without claiming or fitting",
    )
    return parser


def _file_sha256(path: Path, *, subject: str) -> str:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError as error:
        raise ProtocolPartyTrainGateError(f"{subject} cannot be read") from error
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ProtocolPartyTrainGateError(f"{subject} must be a regular file")
    return hashlib.sha256(payload).hexdigest()


def _require_sha256(value: object, *, subject: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ProtocolPartyTrainGateError(f"{subject} is not a SHA-256 digest")
    return value


def _within_private_root(path: Path, root: Path, *, subject: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise ProtocolPartyTrainGateError(
            f"{subject} is outside the shared private root"
        ) from error
    return resolved


def _attest_prior(path: Path) -> PartyDevelopmentOutcomeModel:
    payload = _PRIOR_ATTESTATION.read_bytes()
    if hashlib.sha256(payload).hexdigest() != _PRIOR_ATTESTATION_SHA256:
        raise ProtocolPartyTrainGateError("tracked prior attestation differs")
    try:
        attestation = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolPartyTrainGateError("tracked prior attestation is invalid") from error
    completion = (
        attestation.get("completion_aware_v2_initialization")
        if isinstance(attestation, Mapping)
        else None
    )
    historical = (
        attestation.get("historical_v1_prior") if isinstance(attestation, Mapping) else None
    )
    if (
        not isinstance(attestation, Mapping)
        or attestation.get("schema")
        != "pokemon-party-development-v2-prior-initialization-evidence-v1"
        or attestation.get("status") != "authenticated_prior_initialized_no_outcome_training"
        or not isinstance(completion, Mapping)
        or completion.get("private_model_file_sha256") != _PRIOR_FILE_SHA256
        or completion.get("canonical_model_sha256") != _PRIOR_CANONICAL_SHA256
        or completion.get("score_preserving_v1_embedding") is not True
        or completion.get("new_completion_feature_weights_zero") is not True
        or completion.get("outcome_training_examples") != 0
        or not isinstance(historical, Mapping)
        or historical.get("outcome_trained") is not False
        or historical.get("teacher_derived") is not True
    ):
        raise ProtocolPartyTrainGateError("tracked prior attestation is not the frozen prior")
    model = load_party_development_outcome_model(path, expected_sha256=_PRIOR_FILE_SHA256)
    if (
        canonical_party_development_outcome_model_sha256(model) != _PRIOR_CANONICAL_SHA256
        or model.outcome_training_examples != 0
        or model.outcome_training_root_lineage_ids
        or model.outcome_training_state_sha256
        or model.teacher_prior.model_file_sha256 != historical.get("model_file_sha256")
        or model.teacher_prior.model_canonical_sha256 != historical.get("canonical_model_sha256")
        or model.teacher_prior.offline_evidence_sha256 != historical.get("offline_evidence_sha256")
    ):
        raise ProtocolPartyTrainGateError("private prior differs from its historical attestation")
    return model


def _manifest_entry(
    manifest: Mapping[str, object],
    filename: str,
) -> Mapping[str, object]:
    files = manifest.get("files")
    matches = (
        tuple(
            item for item in files if isinstance(item, Mapping) and item.get("filename") == filename
        )
        if isinstance(files, list)
        else ()
    )
    if len(matches) != 1:
        raise ProtocolPartyTrainGateError("authenticated stream declaration differs")
    return matches[0]


def _stream_lines(
    artifact: Path,
    manifest: Mapping[str, object],
    *,
    filename: str,
    expected_records: int,
) -> tuple[bytes, ...]:
    entry = _manifest_entry(manifest, filename)
    payload = _FITTER["_read_regular_file"](
        artifact / filename,
        subject=f"{filename} authenticated stream",
        maximum_bytes=_FITTER["_MAX_STREAM_BYTES"],
    )
    if (
        len(payload) != entry.get("bytes")
        or hashlib.sha256(payload).hexdigest() != entry.get("sha256")
        or not payload.endswith(b"\n")
    ):
        raise ProtocolPartyTrainGateError("authenticated stream bytes changed")
    lines = tuple(payload.splitlines(keepends=True))
    if len(lines) != expected_records or any(not line.endswith(b"\n") for line in lines):
        raise ProtocolPartyTrainGateError("authenticated stream record count differs")
    return lines


def _assignment_header(raw_line: bytes, *, record_type: str) -> _RawTerminal:
    prefix = b'{"assignment":'
    delimiter = b'},"evidence":'
    suffix = f',"record_type":"{record_type}"}}\n'.encode("ascii")
    boundary = raw_line.find(delimiter)
    if not raw_line.startswith(prefix) or boundary < len(prefix) or not raw_line.endswith(suffix):
        raise ProtocolPartyTrainGateError("terminal assignment header is invalid")
    assignment_payload = raw_line[len(prefix) : boundary + 1]
    try:
        value = json.loads(assignment_payload.decode("ascii"))
        assignment = PartyDevelopmentOutcomeTrialAssignment.from_private_dict(value)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise ProtocolPartyTrainGateError("terminal assignment header is invalid") from error
    return _RawTerminal(assignment=assignment, record_type=record_type, raw_line=raw_line)


def _artifact_terminals(
    artifact: Path,
    manifest: Mapping[str, object],
    *,
    measured_trials: int,
    invalid_trials: int,
) -> tuple[tuple[_RawTerminal, ...], tuple[_RawTerminal, ...]]:
    outcomes = tuple(
        _assignment_header(line, record_type="repeatable_party_candidate_outcome")
        for line in _stream_lines(
            artifact,
            manifest,
            filename="outcomes.jsonl",
            expected_records=measured_trials,
        )
    )
    failures = tuple(
        _assignment_header(line, record_type="repeatable_party_candidate_failure")
        for line in _stream_lines(
            artifact,
            manifest,
            filename="failures.jsonl",
            expected_records=invalid_trials,
        )
    )
    return outcomes, failures


def _trial_key(assignment: PartyDevelopmentOutcomeTrialAssignment) -> tuple[str, int]:
    return assignment.scenario_id, assignment.candidate_index


def _terminal_map(
    records: tuple[_RawTerminal, ...],
    *,
    subject: str,
) -> dict[tuple[str, int], _RawTerminal]:
    result: dict[tuple[str, int], _RawTerminal] = {}
    for record in records:
        key = _trial_key(record.assignment)
        if key in result:
            raise ProtocolPartyTrainGateError(f"{subject} repeats a candidate terminal")
        result[key] = record
    return result


def _question_set_sha256(selected: tuple[Any, ...]) -> str:
    return canonical_sha256(
        {
            "schema": "pokemon.red.repeatable-party-outcome-question-set.v1",
            "role": "train",
            "questions": [
                {
                    "scenario_id": item.binding_question.scenario_id,
                    "root_lineage_id": item.binding_question.binding.root_lineage_id,
                    "initial_state_sha256": item.binding_question.binding.initial_state_sha256,
                    "prospective_binding_sha256": (item.binding_question.binding.binding_sha256),
                }
                for item in selected
            ],
        }
    )


def _training_outcome_subset_sha256(records: tuple[_RawTerminal, ...]) -> str:
    return canonical_sha256(
        {
            "schema": "pokemon.red.protocol-party-train-raw-outcome-subset.v1",
            "records": [
                {
                    "assignment_sha256": item.assignment.assignment_sha256,
                    "raw_line_sha256": hashlib.sha256(item.raw_line).hexdigest(),
                }
                for item in records
            ],
        }
    )


def _complete_selected(
    selected: tuple[Any, ...],
    outcomes: Mapping[tuple[str, int], _RawTerminal],
) -> tuple[Any, ...]:
    complete: list[Any] = []
    for runtime in selected:
        question = runtime.binding_question
        required = {
            (question.scenario_id, item.candidate_index)
            for item in question.candidate_set.candidates
            if question.binding.candidate_available[item.candidate_index]
        }
        if required and required.issubset(outcomes):
            complete.append(runtime)
    return tuple(complete)


def _composition(
    selected: tuple[Any, ...],
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    kinds: Counter[str] = Counter()
    goals: Counter[str] = Counter()
    cross: Counter[str] = Counter()
    for item in selected:
        binding = item.binding_question.binding
        kinds[binding.kind.value] += 1
        goals[binding.goal.value] += 1
        cross[f"{binding.kind.value}:{binding.goal.value}"] += 1
    return dict(sorted(kinds.items())), dict(sorted(goals.items())), dict(sorted(cross.items()))


def _prepare_train_boundary(
    args: argparse.Namespace,
    *,
    collection: Any,
    predecessor_artifact: Path,
    predecessor_manifest: Mapping[str, object],
    successor_artifact: Path,
    successor_manifest: Mapping[str, object],
) -> _TrainBoundary:
    predecessor_outcomes, predecessor_failures = _artifact_terminals(
        predecessor_artifact,
        predecessor_manifest,
        measured_trials=args.expected_predecessor_measured_trials,
        invalid_trials=args.expected_predecessor_invalid_trials,
    )
    successor_outcomes, successor_failures = _artifact_terminals(
        successor_artifact,
        successor_manifest,
        measured_trials=args.expected_successor_measured_trials,
        invalid_trials=args.expected_successor_invalid_trials,
    )
    predecessor_outcome_map = _terminal_map(predecessor_outcomes, subject="predecessor")
    predecessor_failure_map = _terminal_map(predecessor_failures, subject="predecessor")
    successor_outcome_map = _terminal_map(successor_outcomes, subject="successor")
    successor_failure_map = _terminal_map(successor_failures, subject="successor")
    predecessor_all = {**predecessor_outcome_map, **predecessor_failure_map}
    if len(predecessor_all) != len(predecessor_outcome_map) + len(predecessor_failure_map):
        raise ProtocolPartyTrainGateError("predecessor terminal sets overlap")
    successor_all = {**successor_outcome_map, **successor_failure_map}
    if len(successor_all) != len(successor_outcome_map) + len(successor_failure_map):
        raise ProtocolPartyTrainGateError("successor terminal sets overlap")

    current_values = _SUCCESSOR["_flatten_assignments"](collection.reconstruction.assignments)
    current = {_trial_key(item): item for item in current_values}
    if (
        len(current) != len(current_values)
        or set(predecessor_all) != set(current)
        or set(successor_all) != set(predecessor_failure_map)
    ):
        raise ProtocolPartyTrainGateError("terminal assignment denominator differs")
    for key, record in (*predecessor_all.items(), *successor_all.items()):
        if record.assignment != current[key]:
            raise ProtocolPartyTrainGateError("terminal assignment differs from reconstruction")

    final_outcomes = {**predecessor_outcome_map, **successor_outcome_map}
    if len(final_outcomes) != len(predecessor_outcome_map) + len(successor_outcome_map):
        raise ProtocolPartyTrainGateError("successor overwrites measured evidence")
    selected = tuple(collection.reconstruction.selected)
    predecessor_complete = _complete_selected(selected, predecessor_outcome_map)
    joined_complete = _complete_selected(selected, final_outcomes)
    predecessor_counts = Counter(
        item.binding_question.binding.partition.value for item in predecessor_complete
    )
    joined_counts = Counter(
        item.binding_question.binding.partition.value for item in joined_complete
    )
    if (
        dict(predecessor_counts) != _EXPECTED_PREDECESSOR_COMPLETE
        or dict(joined_counts) != _EXPECTED_JOINED_COMPLETE
        or joined_counts["development"] - predecessor_counts["development"]
        != _EXPECTED_NEWLY_COMPLETED_DEVELOPMENT
    ):
        raise ProtocolPartyTrainGateError("question completion headers differ from the frozen gate")
    training = tuple(
        item
        for item in joined_complete
        if item.binding_question.binding.partition is ScenarioPartition.TRAIN
    )
    question_sha256 = _question_set_sha256(training)
    kind_counts, goal_counts, cross_counts = _composition(training)
    if (
        len(training) != _EXPECTED_TRAIN_QUESTIONS
        or question_sha256 != _EXPECTED_TRAINING_QUESTION_SET_SHA256
        or kind_counts != _EXPECTED_TRAIN_KIND_COUNTS
        or goal_counts != _EXPECTED_TRAIN_GOAL_COUNTS
        or cross_counts != _EXPECTED_TRAIN_ACTION_GOAL_COUNTS
    ):
        raise ProtocolPartyTrainGateError("training identity or composition differs")
    training_scenarios = {item.binding_question.scenario_id for item in training}
    retained = tuple(
        record for key, record in sorted(final_outcomes.items()) if key[0] in training_scenarios
    )
    outcome_subset_sha256 = _training_outcome_subset_sha256(retained)
    if any(record.assignment.partition is not ScenarioPartition.TRAIN for record in retained):
        raise ProtocolPartyTrainGateError("train-only terminal router crossed partitions")
    if outcome_subset_sha256 != _EXPECTED_TRAIN_OUTCOME_SUBSET_SHA256:
        raise ProtocolPartyTrainGateError("train outcome subset differs from the frozen gate")
    final_unique = {**final_outcomes, **successor_failure_map}
    development_headers = sum(
        record.assignment.partition is ScenarioPartition.DEVELOPMENT
        for record in final_unique.values()
    )
    return _TrainBoundary(
        selected=training,
        outcome_records=retained,
        training_question_set_sha256=question_sha256,
        training_outcome_subset_sha256=outcome_subset_sha256,
        training_kind_counts=kind_counts,
        training_goal_counts=goal_counts,
        training_action_goal_counts=cross_counts,
        authenticated_terminal_records=(
            len(predecessor_outcomes)
            + len(predecessor_failures)
            + len(successor_outcomes)
            + len(successor_failures)
        ),
        development_assignment_headers_authenticated=development_headers,
        predecessor_complete_counts=dict(predecessor_counts),
        joined_complete_counts=dict(joined_counts),
    )


def _gate_identity(
    *,
    training_outcome_subset_sha256: str,
) -> str:
    """Return a semantic claim key unaffected by documentation-only commits."""

    return canonical_sha256(
        {
            "schema": "pokemon.red.protocol-consistent-party-train-gate-identity.v2",
            "design_id": PROTOCOL_DESIGN_ID,
            "prior_attestation_sha256": _PRIOR_ATTESTATION_SHA256,
            "prior_model_canonical_sha256": _PRIOR_CANONICAL_SHA256,
            "training_question_set_sha256": _EXPECTED_TRAINING_QUESTION_SET_SHA256,
            "training_outcome_subset_sha256": training_outcome_subset_sha256,
            "training_action_goal_counts": _EXPECTED_TRAIN_ACTION_GOAL_COUNTS,
            "learner": {
                "action_heads": ["trainee", "venue"],
                "newton_steps": PROTOCOL_NEWTON_STEPS,
                "pairwise_menu_normalized": True,
                "portable_groups": list(PORTABLE_GROUP_NAMES),
                "ridge": PROTOCOL_PAIRWISE_RIDGE,
            },
            "evaluation": "deterministic_leave_one_root_out_train_roots_only",
            "pass_rule": _PASS_RULE,
        }
    )


def _claim_registry_root() -> Path:
    account_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    if sys.platform == "darwin":
        return (
            account_home
            / "Library"
            / "Application Support"
            / "pokemon-red-completion-agent"
            / "one-shot-claims-v1"
        )
    return account_home / ".local" / "state" / "pokemon-red-completion-agent" / "one-shot-claims-v1"


def _prepare_claim_registry() -> Path:
    root = _claim_registry_root()
    try:
        metadata = root.lstat()
        resolved = root.resolve(strict=True)
    except OSError as error:
        raise ProtocolPartyTrainGateError(
            "fixed-account claim registry must be provisioned before preflight"
        ) from error
    if (
        root.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise ProtocolPartyTrainGateError("fixed-account claim registry is invalid")
    return resolved


def _claim_marker(registry: Path, identity: str) -> Path:
    return registry / f"{_require_sha256(identity, subject='gate identity')}.json"


def _claim_identity_is_available(registry: Path, identity: str) -> bool:
    marker = _claim_marker(registry, identity)
    try:
        marker.lstat()
    except FileNotFoundError:
        return True
    except OSError as error:
        raise ProtocolPartyTrainGateError(
            "fixed-account claim marker cannot be inspected"
        ) from error
    return False


def _write_global_claim(readiness: _Readiness) -> None:
    marker = _claim_marker(readiness.claim_registry, readiness.gate_identity_sha256)
    payload = (
        json.dumps(
            {
                "schema": "pokemon.red.fixed-account-one-shot-claim.v1",
                "gate_identity_sha256": readiness.gate_identity_sha256,
                "design_id": PROTOCOL_DESIGN_ID,
                "source": readiness.source.public_dict(),
                "runner_sha256": readiness.runner_sha256,
                "learner_sha256": readiness.learner_sha256,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(marker, flags, 0o600)
        written = 0
        while written < len(payload):
            written += os.write(descriptor, payload[written:])
        os.fsync(descriptor)
        directory = os.open(readiness.claim_registry, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except FileExistsError as error:
        raise ProtocolPartyTrainGateError(
            "train-only semantic identity is already consumed"
        ) from error
    except OSError as error:
        raise ProtocolPartyTrainGateError(
            "fixed-account one-shot claim could not be retained"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _prepare_readiness(args: argparse.Namespace) -> _Readiness:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit != args.expected_executable_source:
        raise ProtocolPartyTrainGateError("executable source differs from external attestation")
    _JOINED_FIT["_require_historical_runner_bytes"](args)
    predecessor_path, predecessor_manifest, predecessor_manifest_sha256 = _JOINED_FIT[
        "_read_artifact_manifest"
    ](
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
    successor_path, successor_manifest, successor_manifest_sha256 = _JOINED_FIT[
        "_read_artifact_manifest"
    ](
        args.successor_artifact,
        expected_manifest_sha256=args.expected_successor_manifest_sha256,
        expected_kind=_JOINED_FIT["_SUCCESSOR_KIND"],
        expected_streams={
            "evaluation.jsonl": 1,
            "failures.jsonl": args.expected_successor_invalid_trials,
            "outcomes.jsonl": args.expected_successor_measured_trials,
            "plan.jsonl": 1,
        },
        subject="successor artifact",
    )
    predecessor_plan_record = _JOINED_FIT["_read_authenticated_stream_record"](
        predecessor_path,
        predecessor_manifest,
        filename="plan.jsonl",
        subject="predecessor plan stream",
    )
    successor_plan_record = _JOINED_FIT["_read_authenticated_stream_record"](
        successor_path,
        successor_manifest,
        filename="plan.jsonl",
        subject="successor plan stream",
    )
    plan_only = type("PlanOnly", (), {"plan_record": predecessor_plan_record})()
    predecessor_plan, predecessor_inputs, predecessor_dose = _FITTER["_require_plan_record"](
        plan_only,
        expected_plan_sha256=args.expected_predecessor_plan_sha256,
        expected_collection_source=args.expected_predecessor_source,
        expected_battle_credit_protocol=args.battle_credit_protocol,
        expected_selection_protocol=args.scenario_selection_protocol,
    )
    collection = _JOINED_FIT["_prepare_collection_readiness"](
        args,
        predecessor_plan_record=predecessor_plan_record,
        predecessor_plan=predecessor_plan,
        predecessor_inputs=predecessor_inputs,
        predecessor_dose=predecessor_dose,
        successor_plan_record=successor_plan_record,
    )
    root_path = _FITTER["_require_external"](
        args.private_artifact_root,
        subject="private artifact root",
    )
    prior_path = _FITTER["_require_external"](
        args.prior_model,
        subject="historical zero-outcome prior",
    )
    _within_private_root(prior_path, root_path, subject="historical zero-outcome prior")
    for path, subject in (
        (predecessor_path, "predecessor artifact"),
        (successor_path, "successor artifact"),
    ):
        _within_private_root(path, root_path, subject=subject)
    prior_model = _attest_prior(prior_path)
    boundary = _prepare_train_boundary(
        args,
        collection=collection,
        predecessor_artifact=predecessor_path,
        predecessor_manifest=predecessor_manifest,
        successor_artifact=successor_path,
        successor_manifest=successor_manifest,
    )
    runner_sha256 = _file_sha256(Path(__file__).resolve(), subject="train-gate runner")
    learner_sha256 = _file_sha256(
        Path(__file__).with_name("protocol_consistent_party_learning.py"),
        subject="protocol learner",
    )
    if runner_sha256 != _require_sha256(
        args.expected_train_gate_runner_sha256,
        subject="externally attested train-gate runner",
    ) or learner_sha256 != _require_sha256(
        args.expected_protocol_learner_sha256,
        subject="externally attested protocol learner",
    ):
        raise ProtocolPartyTrainGateError("executable bytes differ from external attestation")
    identity = _gate_identity(
        training_outcome_subset_sha256=boundary.training_outcome_subset_sha256,
    )
    artifact_id = f"protocol-party-train-gate-v2-{identity[:32]}"
    if not _JOINED_FIT["_artifact_identity_is_available"](root_path, artifact_id):
        raise ProtocolPartyTrainGateError("train-only semantic identity is already consumed")
    claim_registry = _prepare_claim_registry()
    if not _claim_identity_is_available(claim_registry, identity):
        raise ProtocolPartyTrainGateError("train-only semantic identity is already consumed")
    return _Readiness(
        source=source,
        prior_model=prior_model,
        predecessor_manifest_sha256=predecessor_manifest_sha256,
        successor_manifest_sha256=successor_manifest_sha256,
        gate_identity_sha256=identity,
        artifact_id=artifact_id,
        output_root=open_private_root(root_path, repository_root=PROJECT_ROOT),
        boundary=boundary,
        claim_registry=claim_registry,
        runner_sha256=runner_sha256,
        learner_sha256=learner_sha256,
    )


def _decode_training_examples(boundary: _TrainBoundary) -> tuple[ScenarioOutcomeExample, ...]:
    outcomes: dict[str, dict[int, Any]] = {}
    for terminal in boundary.outcome_records:
        if terminal.assignment.partition is not ScenarioPartition.TRAIN:
            raise ProtocolPartyTrainGateError("development payload reached the train decoder")
        try:
            record = json.loads(terminal.raw_line.decode("ascii"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProtocolPartyTrainGateError("train outcome payload is invalid") from error
        outcome = _FITTER["_candidate_outcome"](
            record,
            expected_assignment=terminal.assignment,
        )
        outcomes.setdefault(terminal.assignment.scenario_id, {})[
            terminal.assignment.candidate_index
        ] = outcome
    examples = tuple(_COLLECTION["_assemble_examples"](boundary.selected, outcomes))
    if (
        len(examples) != _EXPECTED_TRAIN_QUESTIONS
        or any(
            item.partition is not ScenarioPartition.TRAIN or not item.learner_update_eligible
            for item in examples
        )
        or _question_set_sha256(boundary.selected) != boundary.training_question_set_sha256
    ):
        raise ProtocolPartyTrainGateError("decoded train examples differ from the frozen boundary")
    return examples


def _preregistration(readiness: _Readiness) -> dict[str, object]:
    boundary = readiness.boundary
    return {
        "schema": "pokemon.red.protocol-consistent-party-train-gate-preregistration.v2",
        "gate_identity_sha256": readiness.gate_identity_sha256,
        "design_id": PROTOCOL_DESIGN_ID,
        "source": readiness.source.public_dict(),
        "runner_sha256": readiness.runner_sha256,
        "learner_sha256": readiness.learner_sha256,
        "predecessor_manifest_sha256": readiness.predecessor_manifest_sha256,
        "successor_manifest_sha256": readiness.successor_manifest_sha256,
        "prior_model_file_sha256": _PRIOR_FILE_SHA256,
        "prior_model_canonical_sha256": _PRIOR_CANONICAL_SHA256,
        "prior_attestation_sha256": _PRIOR_ATTESTATION_SHA256,
        "prior_outcome_training_examples": 0,
        "training_question_set_sha256": boundary.training_question_set_sha256,
        "training_outcome_subset_sha256": boundary.training_outcome_subset_sha256,
        "training_questions": _EXPECTED_TRAIN_QUESTIONS,
        "training_kind_counts": dict(boundary.training_kind_counts),
        "training_goal_counts": dict(boundary.training_goal_counts),
        "training_action_goal_counts": dict(boundary.training_action_goal_counts),
        "excluded_evidence": {
            "earlier_switch_assisted_outcome_questions": 8,
            "consumed_development_questions": 15,
        },
        "learner": {
            "action_heads": ["trainee", "venue"],
            "frozen_hidden_representation": True,
            "newton_steps": PROTOCOL_NEWTON_STEPS,
            "pairwise_menu_normalized": True,
            "portable_groups": list(PORTABLE_GROUP_NAMES),
            "prior_score_is_frozen_offset": True,
            "ridge": PROTOCOL_PAIRWISE_RIDGE,
        },
        "evaluation": "deterministic_leave_one_root_out_train_roots_only",
        "evidence_class": "train_only_architecture_selection_not_independent_generalization",
        "pass_rule": _PASS_RULE,
        "candidate_count": 1,
        "architecture_or_hyperparameter_sweep": False,
        "development_stream_bytes_authenticated": True,
        "development_label_free_questions_reconstructed": 12,
        "development_assignment_headers_authenticated": (
            boundary.development_assignment_headers_authenticated
        ),
        "development_outcome_payloads_decoded": 0,
        "development_outcome_examples_materialized": 0,
        "development_examples_passed_to_learner": 0,
        "development_metrics_computed": 0,
        "same_semantic_design_retry": False,
        "fixed_host_account_one_shot_claim": True,
        "support_limitations": {
            "action_and_goal_are_confounded_in_train": True,
            "mission_critical_absent_train_cells": [
                "trainee:collection",
                "trainee:evolution",
                "trainee:role_coverage",
            ],
            "pass_cannot_support_multi_goal_trainee_ranking": True,
        },
        "authority_promoted": False,
        "sealed_red_cases_opened": 0,
        "crystal_cases_opened": 0,
        "full_game_replays": 0,
        "private_path_fields": 0,
    }


def _decision(*, representation_passed: bool, evaluation_passed: bool | None) -> dict[str, object]:
    if not representation_passed:
        result = "stop_before_fit_and_audit_representation_collisions"
        retained = False
    elif evaluation_passed is True:
        result = "freeze_fresh_red_slice_design_for_missing_trainee_goal_cells"
        retained = True
    else:
        result = "reject_candidate_and_close_train_only_design"
        retained = False
    return {
        "schema": "pokemon.red.protocol-consistent-party-train-gate-decision.v2",
        "representation_audit_passed": representation_passed,
        "evaluation_passed": evaluation_passed,
        "result": result,
        "candidate_retained_for_development_design": retained,
        "candidate_has_shadow_authority": False,
        "candidate_has_live_authority": False,
        "development_execution_authorized": False,
        "crystal_execution_authorized": False,
        "sealed_red_execution_authorized": False,
        "full_game_replay_authorized": False,
        "pass_rule": _PASS_RULE,
    }


def _preflight_receipt(readiness: _Readiness) -> dict[str, object]:
    boundary = readiness.boundary
    return {
        "schema": "pokemon.red.protocol-consistent-party-train-gate-preflight.v2",
        "status": "ready_for_single_train_only_architecture_gate",
        "source": readiness.source.public_dict(),
        "gate_identity_sha256": readiness.gate_identity_sha256,
        "design_id": PROTOCOL_DESIGN_ID,
        "prior_model_canonical_sha256": _PRIOR_CANONICAL_SHA256,
        "prior_attestation_sha256": _PRIOR_ATTESTATION_SHA256,
        "predecessor_manifest_sha256": readiness.predecessor_manifest_sha256,
        "successor_manifest_sha256": readiness.successor_manifest_sha256,
        "training_question_set_sha256": boundary.training_question_set_sha256,
        "training_outcome_subset_sha256": boundary.training_outcome_subset_sha256,
        "training_questions": _EXPECTED_TRAIN_QUESTIONS,
        "training_action_goal_counts": dict(boundary.training_action_goal_counts),
        "authenticated_terminal_records": boundary.authenticated_terminal_records,
        "development_stream_bytes_authenticated": True,
        "development_label_free_questions_reconstructed": 12,
        "development_assignment_headers_authenticated": (
            boundary.development_assignment_headers_authenticated
        ),
        "development_outcome_payloads_decoded": 0,
        "development_outcome_examples_materialized": 0,
        "claim_safe_label_free_reconstruction_complete": True,
        "semantic_identity_available_locally": True,
        "semantic_identity_available_fixed_host_account": True,
        "runner_sha256": readiness.runner_sha256,
        "learner_sha256": readiness.learner_sha256,
        "support_limitations": {
            "action_and_goal_are_confounded_in_train": True,
            "pass_requires_fresh_missing_trainee_goal_cells": True,
        },
        "model_fits": 0,
        "controller_actions": 0,
        "teacher_queries": 0,
        "authority_promoted": False,
        "sealed_red_cases_opened": 0,
        "crystal_cases_opened": 0,
        "full_game_replays": 0,
        "private_path_fields": 0,
    }


def _run(args: argparse.Namespace) -> dict[str, object]:
    readiness = _prepare_readiness(args)
    if args.preflight_only:
        return _preflight_receipt(readiness)
    _write_global_claim(readiness)
    writer = readiness.output_root.begin_artifact(readiness.artifact_id, kind=_KIND)
    with writer:
        writer.append("preregistration", _preregistration(readiness), durable=True)
        training = _decode_training_examples(readiness.boundary)
        representation = audit_protocol_party_representation(readiness.prior_model, training)
        writer.append("representation_audit", representation.public_dict(), durable=True)
        if not representation.passed:
            decision = _decision(representation_passed=False, evaluation_passed=None)
            writer.append("decision", decision, durable=True)
            result = None
            model_sha256 = None
            model_fits = 0
        else:
            result = run_protocol_party_leave_one_root_out(readiness.prior_model, training)
            model_document = result.model.to_dict()
            reloaded = ProtocolPartyRanker.from_dict(
                json.loads(
                    json.dumps(
                        model_document,
                        ensure_ascii=True,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                )
            )
            model_sha256 = canonical_protocol_party_ranker_sha256(result.model)
            if canonical_protocol_party_ranker_sha256(reloaded) != model_sha256:
                raise ProtocolPartyTrainGateError("protocol model round-trip changed identity")
            writer.append("model", model_document, durable=True)
            writer.append("evaluation", result.evaluation.public_dict(), durable=True)
            decision = _decision(
                representation_passed=True,
                evaluation_passed=result.evaluation.passed,
            )
            writer.append("decision", decision, durable=True)
            model_fits = 1
    return {
        "schema": "pokemon.red.protocol-consistent-party-train-gate-receipt.v2",
        "status": "complete",
        "source": readiness.source.public_dict(),
        "gate_identity_sha256": readiness.gate_identity_sha256,
        "design_id": PROTOCOL_DESIGN_ID,
        "prior_model_file_sha256": _PRIOR_FILE_SHA256,
        "prior_model_canonical_sha256": _PRIOR_CANONICAL_SHA256,
        "prior_attestation_sha256": _PRIOR_ATTESTATION_SHA256,
        "training_question_set_sha256": readiness.boundary.training_question_set_sha256,
        "training_outcome_subset_sha256": (readiness.boundary.training_outcome_subset_sha256),
        "training_questions": _EXPECTED_TRAIN_QUESTIONS,
        "training_kind_counts": dict(readiness.boundary.training_kind_counts),
        "training_goal_counts": dict(readiness.boundary.training_goal_counts),
        "training_action_goal_counts": dict(readiness.boundary.training_action_goal_counts),
        "representation_audit": representation.public_dict(),
        "model_canonical_sha256": model_sha256,
        "model_artifact": writer.summary.public_dict(),
        "evaluation": result.evaluation.public_dict() if result is not None else None,
        "decision": decision,
        "development_stream_bytes_authenticated": True,
        "development_label_free_questions_reconstructed": 12,
        "development_assignment_headers_authenticated": (
            readiness.boundary.development_assignment_headers_authenticated
        ),
        "development_outcome_payloads_decoded": 0,
        "development_outcome_examples_materialized": 0,
        "development_examples_passed_to_learner": 0,
        "development_metrics_computed": 0,
        "fixed_host_account_one_shot_claim_retained": True,
        "model_fits": model_fits,
        "controller_actions": 0,
        "teacher_queries": 0,
        "authority_promoted": False,
        "sealed_red_cases_opened": 0,
        "crystal_cases_opened": 0,
        "full_game_replays": 0,
        "private_path_fields": 0,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(json.dumps(_run(args), allow_nan=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
