from __future__ import annotations

import hashlib
import json
import runpy
from collections.abc import Mapping
from pathlib import Path

import pytest

from pokemon_red_completion.party_development_outcome_campaign import (
    PartyDevelopmentOutcomeTrialAssignment,
)
from pokemon_red_completion.party_development_rank import PartyDevelopmentGoal
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "fit_repeatable_party_outcome_model.py")
)


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


def _pilot_artifact(root: Path) -> tuple[Path, str]:
    artifact = root / "repeatable-party-development-test"
    artifact.mkdir(parents=True)
    streams = {
        "evaluation.jsonl": _canonical_line({"record_type": "evaluation"}),
        "outcomes.jsonl": b"".join(
            _canonical_line({"ordinal": ordinal}) for ordinal in range(1, 49)
        ),
        "plan.jsonl": _canonical_line({"record_type": "plan"}),
    }
    files = []
    for filename, payload in sorted(streams.items()):
        (artifact / filename).write_bytes(payload)
        files.append(
            {
                "bytes": len(payload),
                "filename": filename,
                "records": 48 if filename == "outcomes.jsonl" else 1,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = {
        "artifact_id": artifact.name,
        "files": files,
        "format": "pokemon-red-completion-private-artifact-jsonl",
        "kind": "repeatable_party_outcome_development",
        "schema_version": 1,
        "status": "complete",
        "totals": {
            "bytes": sum(len(payload) for payload in streams.values()),
            "files": 3,
            "records": 50,
        },
    }
    manifest_payload = _canonical_line(manifest)
    (artifact / "manifest.json").write_bytes(manifest_payload)
    return artifact, hashlib.sha256(manifest_payload).hexdigest()


def _partial_pilot_artifact(root: Path) -> tuple[Path, str]:
    artifact = root / "repeatable-party-development-partial-test"
    artifact.mkdir(parents=True)
    streams = {
        "evaluation.jsonl": _canonical_line({"record_type": "evaluation"}),
        "failures.jsonl": _canonical_line({"ordinal": 3}),
        "outcomes.jsonl": b"".join(
            _canonical_line({"ordinal": ordinal}) for ordinal in range(1, 3)
        ),
        "plan.jsonl": _canonical_line({"record_type": "plan"}),
    }
    files = []
    for filename, payload in sorted(streams.items()):
        (artifact / filename).write_bytes(payload)
        files.append(
            {
                "bytes": len(payload),
                "filename": filename,
                "records": 2 if filename == "outcomes.jsonl" else 1,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = {
        "artifact_id": artifact.name,
        "files": files,
        "format": "pokemon-red-completion-private-artifact-jsonl",
        "kind": "repeatable_party_outcome_development",
        "schema_version": 1,
        "status": "complete",
        "totals": {
            "bytes": sum(len(payload) for payload in streams.values()),
            "files": 4,
            "records": 5,
        },
    }
    manifest_payload = _canonical_line(manifest)
    (artifact / "manifest.json").write_bytes(manifest_payload)
    return artifact, hashlib.sha256(manifest_payload).hexdigest()


def _assignment() -> PartyDevelopmentOutcomeTrialAssignment:
    return PartyDevelopmentOutcomeTrialAssignment.build(
        ordinal=1,
        scenario_id="repeatable-party-train-001",
        root_lineage_id="independent-root-001",
        initial_state_sha256="1" * 64,
        partition=ScenarioPartition.TRAIN,
        kind=TrainingChoiceKind.TRAINEE,
        goal=PartyDevelopmentGoal.COLLECTION,
        binding_sha256="2" * 64,
        candidate_index=0,
        candidate_sha256="3" * 64,
        candidate_feature_sha256="4" * 64,
    )


def _outcome_record(
    assignment: PartyDevelopmentOutcomeTrialAssignment,
) -> dict[str, object]:
    values = [1.0, 0.0]
    evidence = {
        "schema": "pokemon.red.repeatable-party-development-trial-evidence.v1",
        "assignment_sha256": assignment.assignment_sha256,
        "trial_id": assignment.trial_id,
        "scenario_id": assignment.scenario_id,
        "candidate_index": assignment.candidate_index,
        "criterion_values": values,
        "teacher_queries": 0,
        "model_predictions": 0,
        "model_updates": 0,
        "private_path_fields": 0,
    }
    return {
        "record_type": "repeatable_party_candidate_outcome",
        "assignment": assignment.private_dict(),
        "evidence": evidence,
        "outcome": {
            "status": "measured",
            "criterion_values": values,
            "evidence_sha256": canonical_sha256(evidence),
        },
    }


def _failure_record(
    assignment: PartyDevelopmentOutcomeTrialAssignment,
) -> dict[str, object]:
    message = "bounded recovery failed without a target"
    evidence = {
        "schema": "pokemon.red.repeatable-party-development-trial-failure.v1",
        "status": "invalid",
        "failure_type": "RuntimeError",
        "failure_message": message,
        "failure_message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
        "retryable_development_evidence": True,
        "teacher_queries": 0,
        "model_predictions": 0,
        "model_updates": 0,
        "private_path_fields": 0,
    }
    return {
        "record_type": "repeatable_party_candidate_failure",
        "assignment": assignment.private_dict(),
        "evidence": evidence,
    }


def test_pilot_reader_authenticates_every_declared_stream(tmp_path: Path) -> None:
    artifact, manifest_sha256 = _pilot_artifact(tmp_path)

    pilot = SCRIPT["_open_authenticated_pilot"](
        artifact,
        expected_manifest_sha256=manifest_sha256,
    )

    assert pilot.artifact_id == artifact.name
    assert len(pilot.outcome_records) == 48
    assert pilot.manifest_sha256 == manifest_sha256


def test_pilot_reader_rejects_stream_tampering_and_extra_files(tmp_path: Path) -> None:
    artifact, manifest_sha256 = _pilot_artifact(tmp_path)
    with (artifact / "outcomes.jsonl").open("ab") as output:
        output.write(b" ")

    with pytest.raises(RuntimeError, match="failed authentication"):
        SCRIPT["_open_authenticated_pilot"](
            artifact,
            expected_manifest_sha256=manifest_sha256,
        )


def test_partial_pilot_reader_authenticates_censored_failure_stream(
    tmp_path: Path,
) -> None:
    artifact, manifest_sha256 = _partial_pilot_artifact(tmp_path)

    pilot = SCRIPT["_open_authenticated_pilot"](
        artifact,
        expected_manifest_sha256=manifest_sha256,
        expected_measured_trials=2,
        expected_invalid_trials=1,
    )

    assert len(pilot.outcome_records) == 2
    assert len(pilot.failure_records) == 1

    with (artifact / "failures.jsonl").open("ab") as output:
        output.write(b" ")
    with pytest.raises(RuntimeError, match="failed authentication"):
        SCRIPT["_open_authenticated_pilot"](
            artifact,
            expected_manifest_sha256=manifest_sha256,
            expected_measured_trials=2,
            expected_invalid_trials=1,
        )

    artifact, manifest_sha256 = _pilot_artifact(tmp_path / "second")
    (artifact / "unexpected.jsonl").write_text("{}\n", encoding="ascii")
    with pytest.raises(RuntimeError, match="inventory differs"):
        SCRIPT["_open_authenticated_pilot"](
            artifact,
            expected_manifest_sha256=manifest_sha256,
        )


def test_candidate_outcome_binds_assignment_evidence_and_protected_counters() -> None:
    assignment = _assignment()
    record = _outcome_record(assignment)

    outcome = SCRIPT["_candidate_outcome"](
        record,
        expected_assignment=assignment,
    )

    assert outcome.measured
    assert outcome.criterion_values == (1.0, 0.0)

    changed = _outcome_record(assignment)
    evidence = changed["evidence"]
    assert isinstance(evidence, dict)
    evidence["model_predictions"] = 1
    changed_outcome = changed["outcome"]
    assert isinstance(changed_outcome, dict)
    changed_outcome["evidence_sha256"] = canonical_sha256(evidence)
    with pytest.raises(RuntimeError, match="evidence binding differs"):
        SCRIPT["_candidate_outcome"](
            changed,
            expected_assignment=assignment,
        )


def test_candidate_failure_is_authenticated_but_never_becomes_a_target() -> None:
    assignment = _assignment()
    record = _failure_record(assignment)

    outcome = SCRIPT["_candidate_failure"](
        record,
        expected_assignment=assignment,
    )

    assert not outcome.measured
    assert outcome.status.value == "invalid"
    assert outcome.criterion_values == ()

    changed = _failure_record(assignment)
    evidence = changed["evidence"]
    assert isinstance(evidence, dict)
    evidence["model_predictions"] = 1
    with pytest.raises(RuntimeError, match="failure evidence binding differs"):
        SCRIPT["_candidate_failure"](
            changed,
            expected_assignment=assignment,
        )


def test_fit_contract_is_fixed_before_development_comparison() -> None:
    assert SCRIPT["_FIT_EPOCHS"] == 200
    assert SCRIPT["_FIT_LEARNING_RATE"] == 0.01
    assert SCRIPT["_FIT_PRIOR_L2"] == 0.1
    assert SCRIPT["_EXPECTED_TRAIN_QUESTIONS"] == 8
    assert SCRIPT["_EXPECTED_DEVELOPMENT_QUESTIONS"] == 4
    assert SCRIPT["_EXPECTED_OUTCOME_TRIALS"] == 48
