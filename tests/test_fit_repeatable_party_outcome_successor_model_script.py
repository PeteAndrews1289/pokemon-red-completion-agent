from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.party_development_outcome_campaign import (
    PartyDevelopmentOutcomeTrialAssignment,
)
from pokemon_red_completion.party_development_rank import PartyDevelopmentGoal
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind

SCRIPT = runpy.run_path("scripts/fit_repeatable_party_outcome_successor_model.py")


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _manifest_only_pilot(root: Path) -> tuple[Path, str]:
    artifact = root / "repeatable-party-successor-test"
    artifact.mkdir()
    streams = {
        "evaluation.jsonl": _canonical_line({"record_type": "evaluation"}),
        "failures.jsonl": _canonical_line({"ordinal": 2}),
        "outcomes.jsonl": _canonical_line({"ordinal": 1}),
        "plan.jsonl": _canonical_line({"record_type": "plan"}),
    }
    files = []
    for filename, payload in sorted(streams.items()):
        (artifact / filename).write_bytes(payload)
        files.append(
            {
                "bytes": len(payload),
                "filename": filename,
                "records": 1,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = {
        "artifact_id": artifact.name,
        "files": files,
        "format": "pokemon-red-completion-private-artifact-jsonl",
        "kind": "repeatable_party_outcome_development_successor",
        "schema_version": 1,
        "status": "complete",
        "totals": {
            "bytes": sum(len(payload) for payload in streams.values()),
            "files": 4,
            "records": 4,
        },
    }
    manifest_payload = _canonical_line(manifest)
    (artifact / "manifest.json").write_bytes(manifest_payload)
    return artifact, hashlib.sha256(manifest_payload).hexdigest()


def _assignment(*, candidate_index: int) -> PartyDevelopmentOutcomeTrialAssignment:
    return PartyDevelopmentOutcomeTrialAssignment.build(
        ordinal=candidate_index + 1,
        scenario_id="repeatable-party-development-001",
        root_lineage_id="independent-root-001",
        initial_state_sha256="1" * 64,
        partition=ScenarioPartition.DEVELOPMENT,
        kind=TrainingChoiceKind.TRAINEE,
        goal=PartyDevelopmentGoal.COLLECTION,
        binding_sha256="2" * 64,
        candidate_index=candidate_index,
        candidate_sha256=str(candidate_index + 3) * 64,
        candidate_feature_sha256=str(candidate_index + 5) * 64,
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
    message = "bounded recovery remained unavailable"
    evidence = {
        "schema": "pokemon.red.repeatable-party-development-trial-failure.v1",
        "status": "invalid",
        "failure_type": "RuntimeError",
        "failure_message": message,
        "failure_message_sha256": hashlib.sha256(message.encode()).hexdigest(),
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


def test_newly_completed_comparison_excludes_previously_scored_development() -> None:
    before = (
        SimpleNamespace(
            scenario_id="old-development",
            partition=ScenarioPartition.DEVELOPMENT,
            learner_update_eligible=True,
        ),
        SimpleNamespace(
            scenario_id="new-development",
            partition=ScenarioPartition.DEVELOPMENT,
            learner_update_eligible=False,
        ),
        SimpleNamespace(
            scenario_id="new-train",
            partition=ScenarioPartition.TRAIN,
            learner_update_eligible=False,
        ),
    )
    joined = (
        SimpleNamespace(
            scenario_id="old-development",
            partition=ScenarioPartition.DEVELOPMENT,
            learner_update_eligible=True,
        ),
        SimpleNamespace(
            scenario_id="new-development",
            partition=ScenarioPartition.DEVELOPMENT,
            learner_update_eligible=True,
        ),
        SimpleNamespace(
            scenario_id="new-train",
            partition=ScenarioPartition.TRAIN,
            learner_update_eligible=True,
        ),
    )

    newly_completed = SCRIPT["_newly_completed_development_examples"](
        before,
        joined,
    )

    assert [item.scenario_id for item in newly_completed] == ["new-development"]


def test_newly_completed_comparison_rejects_duplicate_predecessor_scenarios() -> None:
    duplicate = SimpleNamespace(
        scenario_id="duplicate",
        partition=ScenarioPartition.DEVELOPMENT,
        learner_update_eligible=False,
    )

    with pytest.raises(RuntimeError, match="repeat a scenario"):
        SCRIPT["_newly_completed_development_examples"](
            (duplicate, duplicate),
            (duplicate,),
        )


def test_join_accepts_only_the_successor_claim_set_and_never_overwrites() -> None:
    first = _assignment(candidate_index=0)
    second = _assignment(candidate_index=1)
    predecessor = SimpleNamespace(
        inherited_outcomes={},
        claim_keys=((first.scenario_id, 0), (second.scenario_id, 1)),
        current_assignments={
            (first.scenario_id, 0): first,
            (second.scenario_id, 1): second,
        },
    )
    successor = SimpleNamespace(
        outcome_records=(_outcome_record(first),),
        failure_records=(_failure_record(second),),
    )

    joined = SCRIPT["_joined_candidate_outcomes"](predecessor, successor)

    assert joined[first.scenario_id][0].measured
    assert not joined[first.scenario_id][1].measured

    predecessor.inherited_outcomes[first.scenario_id] = {0: joined[first.scenario_id][0]}
    with pytest.raises(RuntimeError, match="overwrites inherited"):
        SCRIPT["_joined_candidate_outcomes"](predecessor, successor)


def test_join_rejects_an_omitted_successor_terminal() -> None:
    first = _assignment(candidate_index=0)
    predecessor = SimpleNamespace(
        inherited_outcomes={},
        claim_keys=((first.scenario_id, 0),),
        current_assignments={(first.scenario_id, 0): first},
    )
    successor = SimpleNamespace(outcome_records=(), failure_records=())

    with pytest.raises(RuntimeError, match="differs from its frozen claims"):
        SCRIPT["_joined_candidate_outcomes"](predecessor, successor)


def test_parser_pins_the_joined_denominator_and_label_boundary() -> None:
    parser = SCRIPT["_parser"]()

    assert parser.get_default("preflight_only") is False
    assert parser.get_default("expected_successor_measured_trials") == 10
    assert parser.get_default("expected_successor_invalid_trials") == 5
    assert parser.get_default("expected_fit_train_questions") == 22
    assert parser.get_default("expected_joined_development_questions") == 11
    assert parser.get_default("expected_newly_completed_development_questions") == 5


def test_manifest_preflight_hashes_streams_without_decoding_them(
    tmp_path: Path,
) -> None:
    artifact, manifest_sha256 = _manifest_only_pilot(tmp_path)

    SCRIPT["_read_artifact_manifest"](
        artifact,
        expected_manifest_sha256=manifest_sha256,
        expected_kind="repeatable_party_outcome_development_successor",
        expected_streams={
            "evaluation.jsonl": 1,
            "failures.jsonl": 1,
            "outcomes.jsonl": 1,
            "plan.jsonl": 1,
        },
        subject="successor artifact",
    )
    (artifact / "outcomes.jsonl").write_bytes(b"tampered\n")

    with pytest.raises(RuntimeError, match="stream failed authentication"):
        SCRIPT["_read_artifact_manifest"](
            artifact,
            expected_manifest_sha256=manifest_sha256,
            expected_kind="repeatable_party_outcome_development_successor",
            expected_streams={
                "evaluation.jsonl": 1,
                "failures.jsonl": 1,
                "outcomes.jsonl": 1,
                "plan.jsonl": 1,
            },
            subject="successor artifact",
        )


def test_comparison_claim_cannot_change_with_base_or_hyperparameter_metadata() -> None:
    args = SimpleNamespace(
        expected_predecessor_manifest_sha256="1" * 64,
        expected_predecessor_plan_sha256="2" * 64,
        expected_successor_manifest_sha256="3" * 64,
        expected_successor_plan_sha256="4" * 64,
        expected_newly_completed_development_questions=5,
        expected_base_model_file_sha256="5" * 64,
        base_training_protocol="switch-assisted-fixed-dose-v1",
    )
    claim = SCRIPT["_comparison_claim_sha256"](
        args,
        prior_comparison_manifest_sha256="6" * 64,
    )
    args.expected_base_model_file_sha256 = "7" * 64
    args.base_training_protocol = "direct-safe-else-switch-assisted-fixed-dose-v1"

    assert (
        SCRIPT["_comparison_claim_sha256"](
            args,
            prior_comparison_manifest_sha256="6" * 64,
        )
        == claim
    )


def test_comparison_identity_collision_covers_complete_and_failed_attempts(
    tmp_path: Path,
) -> None:
    available = SCRIPT["_artifact_identity_is_available"]
    artifact_id = "repeatable-party-outcome-comparison-" + "1" * 32

    assert available(tmp_path, artifact_id)
    (tmp_path / f"{artifact_id}.failed.partial").mkdir()
    assert not available(tmp_path, artifact_id)


def test_previous_comparison_boundary_matches_independent_root_and_state_sets() -> None:
    dataset = SimpleNamespace(
        previously_observed_development=(
            SimpleNamespace(root_lineage_id="root-a", initial_state_sha256="1" * 64),
            SimpleNamespace(root_lineage_id="root-b", initial_state_sha256="2" * 64),
        )
    )
    readiness = SimpleNamespace(
        prior_scored_development_roots=frozenset({"root-a", "root-b"}),
        prior_scored_development_states=frozenset({"1" * 64, "2" * 64}),
    )

    SCRIPT["_require_previous_comparison_boundary"](dataset, readiness)
    readiness.prior_scored_development_roots = frozenset({"root-a", "root-c"})
    with pytest.raises(RuntimeError, match="previously scored"):
        SCRIPT["_require_previous_comparison_boundary"](dataset, readiness)


def test_previous_comparison_marginals_do_not_invent_root_state_pairs() -> None:
    roots = [f"root-{index}" for index in range(6)]
    states = [str(index + 1) * 64 for index in range(6)]

    first = SCRIPT["_comparison_marginals"](
        {"root_lineage_ids": roots, "state_sha256": states},
        subject="prior comparison",
    )
    second = SCRIPT["_comparison_marginals"](
        {"root_lineage_ids": roots, "state_sha256": list(reversed(states))},
        subject="prior comparison",
    )

    assert first == second


def test_training_and_new_label_composition_is_distinguishable() -> None:
    examples = (
        SimpleNamespace(scenario_id="a"),
        SimpleNamespace(scenario_id="b"),
        SimpleNamespace(scenario_id="c"),
    )
    bindings = {
        "a": SimpleNamespace(
            kind=TrainingChoiceKind.TRAINEE,
            goal=PartyDevelopmentGoal.COLLECTION,
        ),
        "b": SimpleNamespace(
            kind=TrainingChoiceKind.VENUE,
            goal=PartyDevelopmentGoal.EVOLUTION,
        ),
        "c": SimpleNamespace(
            kind=TrainingChoiceKind.VENUE,
            goal=PartyDevelopmentGoal.COLLECTION,
        ),
    }

    kinds, goals = SCRIPT["_example_composition"](examples, bindings=bindings)

    assert dict(kinds) == {"trainee": 1, "venue": 2}
    assert dict(goals) == {"collection": 2, "evolution": 1}


def test_comparison_claim_is_durable_before_joined_labels_are_decoded() -> None:
    events: list[object] = []

    class Writer:
        def __enter__(self) -> Writer:
            return self

        def __exit__(self, *args: object) -> bool:
            events.append("exit")
            return False

        def append(
            self,
            stream: str,
            record: object,
            *,
            durable: bool = False,
        ) -> None:
            events.append((stream, durable, record))

    class Root:
        def begin_artifact(self, artifact_id: str, *, kind: str) -> Writer:
            events.append(("begin", artifact_id, kind))
            return Writer()

    readiness = SimpleNamespace(
        source=SimpleNamespace(public_dict=lambda: {"git_commit": "1" * 40}),
        comparison_claim_sha256="2" * 64,
        prior_comparison_manifest_sha256="3" * 64,
        base_model_artifact_manifest_sha256="4" * 64,
        artifact_id="repeatable-party-outcome-comparison-" + "2" * 32,
        output_root=Root(),
    )
    args = SimpleNamespace(
        preflight_only=False,
        expected_predecessor_manifest_sha256="5" * 64,
        expected_predecessor_plan_sha256="6" * 64,
        expected_successor_manifest_sha256="7" * 64,
        expected_successor_plan_sha256="8" * 64,
        expected_newly_completed_development_questions=5,
    )
    fit = SCRIPT["_fit"]
    globals_ = fit.__globals__
    original_prepare = globals_["_prepare_fit_readiness"]
    original_reconstruct = globals_["_reconstruct_joined_dataset"]

    def fail_after_claim(_args: object, _readiness: object) -> None:
        assert events[0][0] == "begin"  # type: ignore[index]
        assert events[1][0:2] == ("claim", True)  # type: ignore[index]
        raise RuntimeError("labels would decode here")

    globals_["_prepare_fit_readiness"] = lambda _args: readiness
    globals_["_reconstruct_joined_dataset"] = fail_after_claim
    try:
        with pytest.raises(RuntimeError, match="labels would decode"):
            fit(args)
    finally:
        globals_["_prepare_fit_readiness"] = original_prepare
        globals_["_reconstruct_joined_dataset"] = original_reconstruct

    assert events[-1] == "exit"


def test_readiness_preflight_never_reconstructs_joined_labels() -> None:
    readiness = SimpleNamespace(
        source=SimpleNamespace(public_dict=lambda: {"git_commit": "1" * 40}),
        comparison_claim_sha256="2" * 64,
        prior_comparison_manifest_sha256="3" * 64,
        base_model_artifact_manifest_sha256="4" * 64,
        collection=SimpleNamespace(
            input_sha256={"inventory": "7" * 64},
            reconstruction=SimpleNamespace(
                plan=SimpleNamespace(plan_sha256="8" * 64),
                fingerprint=SimpleNamespace(sha256="9" * 64),
            ),
        ),
    )
    args = SimpleNamespace(
        preflight_only=True,
        expected_predecessor_manifest_sha256="5" * 64,
        expected_successor_manifest_sha256="6" * 64,
        expected_fit_train_questions=22,
        expected_newly_completed_development_questions=5,
    )
    fit = SCRIPT["_fit"]
    globals_ = fit.__globals__
    original_prepare = globals_["_prepare_fit_readiness"]
    original_reconstruct = globals_["_reconstruct_joined_dataset"]
    globals_["_prepare_fit_readiness"] = lambda _args: readiness
    globals_["_reconstruct_joined_dataset"] = lambda _args: pytest.fail(
        "preflight decoded joined labels"
    )
    try:
        result = fit(args)
    finally:
        globals_["_prepare_fit_readiness"] = original_prepare
        globals_["_reconstruct_joined_dataset"] = original_reconstruct

    assert result["status"] == "ready_for_one_shot_comparison_claim"
    assert result["joined_labels_decoded"] == 0


def test_retention_rule_rejects_a_mixed_result() -> None:
    improved = SimpleNamespace(
        base_development=SimpleNamespace(accuracy=0.4, cross_entropy=1.0),
        updated_development=SimpleNamespace(accuracy=0.6, cross_entropy=0.8),
        paired_development=SimpleNamespace(
            mean_winner_probability_delta=0.1,
            updated_wins=3,
            base_wins=1,
        ),
    )
    mixed = SimpleNamespace(
        base_development=SimpleNamespace(accuracy=0.4, cross_entropy=1.0),
        updated_development=SimpleNamespace(accuracy=0.6, cross_entropy=1.1),
        paired_development=SimpleNamespace(
            mean_winner_probability_delta=0.1,
            updated_wins=3,
            base_wins=1,
        ),
    )

    assert SCRIPT["_retention_decision"](improved)["candidate_retained_for_shadow_design"]
    assert not SCRIPT["_retention_decision"](mixed)["candidate_retained_for_shadow_design"]


def test_historical_runner_authentication_rejects_current_or_committed_drift() -> None:
    args = SimpleNamespace(
        expected_successor_source="f17b7a16d791014195d9840339bd211b04931dfa",
        expected_successor_runner_sha256="0" * 64,
        expected_development_runner_sha256=(
            "29c6e2c4cfcd39f8dc0fcbe22627ddf496565c25473aa82e5995ead6b7339cc8"
        ),
    )

    with pytest.raises(RuntimeError, match="successor runner differs"):
        SCRIPT["_require_historical_runner_bytes"](args)
