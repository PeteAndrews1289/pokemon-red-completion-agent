from __future__ import annotations

import argparse
import json
import os
import pwd
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.party_development_outcome_campaign import (
    PartyDevelopmentOutcomeTrialAssignment,
)
from pokemon_red_completion.party_development_rank import PartyDevelopmentGoal
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "run_protocol_consistent_party_train_gate.py")
)


def _args(*, preflight: bool) -> argparse.Namespace:
    return argparse.Namespace(preflight_only=preflight)


def _boundary(*, outcomes: tuple[object, ...] = ()) -> object:
    return RUNNER["_TrainBoundary"](
        selected=tuple(object() for _index in range(22)),
        outcome_records=outcomes,
        training_question_set_sha256=RUNNER["_EXPECTED_TRAINING_QUESTION_SET_SHA256"],
        training_outcome_subset_sha256=RUNNER["_EXPECTED_TRAIN_OUTCOME_SUBSET_SHA256"],
        training_kind_counts={"trainee": 13, "venue": 9},
        training_goal_counts={
            "balance": 13,
            "collection": 3,
            "evolution": 3,
            "role_coverage": 3,
        },
        training_action_goal_counts={
            "trainee:balance": 13,
            "venue:collection": 3,
            "venue:evolution": 3,
            "venue:role_coverage": 3,
        },
        authenticated_terminal_records=108,
        development_assignment_headers_authenticated=29,
        predecessor_complete_counts={"train": 18, "development": 6},
        joined_complete_counts={"train": 22, "development": 11},
    )


def _source() -> object:
    return SimpleNamespace(
        git_commit="a" * 40,
        public_dict=lambda: {"git_commit": "a" * 40, "worktree_dirty": False},
    )


def _readiness(*, output_root: object = object(), claim_registry: Path = Path("/tmp")) -> object:
    return RUNNER["_Readiness"](
        source=_source(),
        prior_model=object(),
        predecessor_manifest_sha256="6" * 64,
        successor_manifest_sha256="7" * 64,
        gate_identity_sha256="8" * 64,
        artifact_id="protocol-party-train-gate-test",
        output_root=output_root,
        boundary=_boundary(),
        claim_registry=claim_registry,
        runner_sha256="9" * 64,
        learner_sha256="a" * 64,
    )


def _assignment(
    *,
    partition: ScenarioPartition,
    binding_sha256: str = "2" * 64,
    candidate_feature_sha256: str = "4" * 64,
) -> PartyDevelopmentOutcomeTrialAssignment:
    return PartyDevelopmentOutcomeTrialAssignment.build(
        ordinal=1,
        scenario_id="protocol-test-scenario",
        root_lineage_id="protocol-test-root",
        initial_state_sha256="1" * 64,
        partition=partition,
        kind=TrainingChoiceKind.TRAINEE,
        goal=PartyDevelopmentGoal.BALANCE,
        binding_sha256=binding_sha256,
        candidate_index=0,
        candidate_sha256="3" * 64,
        candidate_feature_sha256=candidate_feature_sha256,
    )


def test_parser_pins_the_single_design_prior_and_train_identity() -> None:
    parser = RUNNER["_parser"]()
    destinations = {action.dest for action in parser._actions}

    assert "ridge" not in destinations
    assert "newton_steps" not in destinations
    assert "portable_groups" not in destinations
    assert "expected_prior_model_file_sha256" not in destinations
    assert "expected_prior_model_canonical_sha256" not in destinations
    assert "expected_training_question_set_sha256" not in destinations
    assert "expected_executable_source" in destinations
    assert "expected_train_gate_runner_sha256" in destinations
    assert "expected_protocol_learner_sha256" in destinations
    assert RUNNER["_EXPECTED_TRAIN_QUESTIONS"] == 22
    assert RUNNER["_PRIOR_FILE_SHA256"] == (
        "575b77d1f6448248c947fed0bf82296210d560df0dca8989505ffc5516507d06"
    )
    assert RUNNER["_PRIOR_CANONICAL_SHA256"] == (
        "583061b2b5e4579b246b75dddc896a842e65847696eaa43deb1000a58c156fa9"
    )
    assert RUNNER["PROTOCOL_PAIRWISE_RIDGE"] == 4.0
    assert RUNNER["PROTOCOL_NEWTON_STEPS"] == 64


def test_gate_identity_is_semantic_and_ignores_repository_provenance() -> None:
    identity = RUNNER["_gate_identity"](
        training_outcome_subset_sha256="1" * 64,
    )
    same = RUNNER["_gate_identity"](
        training_outcome_subset_sha256="1" * 64,
    )
    changed = RUNNER["_gate_identity"](
        training_outcome_subset_sha256="2" * 64,
    )

    assert len(identity) == 64
    assert identity == same
    assert identity != changed
    assert "source_commit" not in RUNNER["_gate_identity"].__code__.co_varnames
    assert "runner_sha256" not in RUNNER["_gate_identity"].__code__.co_varnames


def test_assignment_header_parser_never_decodes_the_outcome_tail() -> None:
    assignment = _assignment(partition=ScenarioPartition.DEVELOPMENT)
    assignment_bytes = json.dumps(
        assignment.private_dict(),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    raw = (
        b'{"assignment":'
        + assignment_bytes
        + b',"evidence":THIS_IS_NOT_JSON,"outcome":DO_NOT_OPEN,'
        + b'"record_type":"repeatable_party_candidate_outcome"}\n'
    )

    terminal = RUNNER["_assignment_header"](
        raw,
        record_type="repeatable_party_candidate_outcome",
    )

    assert terminal.assignment == assignment
    assert terminal.raw_line is raw


def test_terminal_join_preserves_old_binding_but_rejects_semantic_drift() -> None:
    predecessor_assignment = _assignment(partition=ScenarioPartition.TRAIN)
    current_assignment = _assignment(
        partition=ScenarioPartition.TRAIN,
        binding_sha256="5" * 64,
    )
    key = (predecessor_assignment.scenario_id, predecessor_assignment.candidate_index)
    predecessor_terminal = RUNNER["_RawTerminal"](
        assignment=predecessor_assignment,
        record_type="repeatable_party_candidate_outcome",
        raw_line=b"predecessor\n",
    )
    current_terminal = RUNNER["_RawTerminal"](
        assignment=current_assignment,
        record_type="repeatable_party_candidate_outcome",
        raw_line=b"successor\n",
    )
    differing = {
        field
        for field, value in predecessor_assignment.private_dict().items()
        if value != current_assignment.private_dict()[field]
    }
    assert differing == {"assignment_sha256", "binding_sha256", "trial_id"}

    RUNNER["_require_terminal_assignment_join"](
        predecessor={key: predecessor_terminal},
        successor={},
        current={key: current_assignment},
    )
    RUNNER["_require_terminal_assignment_join"](
        predecessor={},
        successor={key: current_terminal},
        current={key: current_assignment},
    )

    changed_semantics = _assignment(
        partition=ScenarioPartition.TRAIN,
        binding_sha256="5" * 64,
        candidate_feature_sha256="6" * 64,
    )
    changed_terminal = RUNNER["_RawTerminal"](
        assignment=changed_semantics,
        record_type="repeatable_party_candidate_outcome",
        raw_line=b"changed\n",
    )
    with pytest.raises(
        RUNNER["ProtocolPartyTrainGateError"],
        match="candidate semantics",
    ):
        RUNNER["_require_terminal_assignment_join"](
            predecessor={key: changed_terminal},
            successor={},
            current={key: current_assignment},
        )
    with pytest.raises(
        RUNNER["ProtocolPartyTrainGateError"],
        match="successor terminal assignment",
    ):
        RUNNER["_require_terminal_assignment_join"](
            predecessor={},
            successor={key: predecessor_terminal},
            current={key: current_assignment},
        )


def test_train_decoder_rejects_development_before_json_or_outcome_decode() -> None:
    assignment = _assignment(partition=ScenarioPartition.DEVELOPMENT)
    terminal = RUNNER["_RawTerminal"](
        assignment=assignment,
        record_type="repeatable_party_candidate_outcome",
        raw_line=b"not-json\n",
    )
    boundary = _boundary(outcomes=(terminal,))
    decoder = RUNNER["_decode_training_examples"]
    globals_ = decoder.__globals__
    original = globals_["_FITTER"]["_candidate_outcome"]
    calls = 0

    def forbidden(*_args: object, **_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("development outcome payload was decoded")

    globals_["_FITTER"]["_candidate_outcome"] = forbidden
    try:
        with pytest.raises(RUNNER["ProtocolPartyTrainGateError"], match="development payload"):
            decoder(boundary)
    finally:
        globals_["_FITTER"]["_candidate_outcome"] = original

    assert calls == 0


def test_preflight_claims_nothing_and_reports_the_opaque_boundary() -> None:
    run = RUNNER["_run"]
    globals_ = run.__globals__
    original_prepare = globals_["_prepare_readiness"]
    original_claim = globals_["_write_global_claim"]
    claim_calls = 0

    def forbidden_claim(_readiness: object) -> None:
        nonlocal claim_calls
        claim_calls += 1
        raise AssertionError("preflight wrote the one-shot claim")

    globals_["_prepare_readiness"] = lambda _args: _readiness()
    globals_["_write_global_claim"] = forbidden_claim
    try:
        receipt = run(_args(preflight=True))
    finally:
        globals_["_prepare_readiness"] = original_prepare
        globals_["_write_global_claim"] = original_claim

    assert claim_calls == 0
    assert receipt["status"] == "ready_for_single_train_only_architecture_gate"
    assert receipt["claim_safe_label_free_reconstruction_complete"] is True
    assert receipt["development_stream_bytes_authenticated"] is True
    assert receipt["development_outcome_payloads_decoded"] == 0
    assert receipt["development_label_free_questions_reconstructed"] == 12
    assert receipt["development_outcome_examples_materialized"] == 0
    assert receipt["model_fits"] == 0
    assert (
        "_reconstruct_joined_dataset"
        not in (
            PROJECT_ROOT / "scripts" / "run_protocol_consistent_party_train_gate.py"
        ).read_text()
    )


def test_fixed_account_claim_is_exclusive_and_durable(tmp_path: Path) -> None:
    readiness = _readiness(claim_registry=tmp_path)

    RUNNER["_write_global_claim"](readiness)

    marker = tmp_path / f"{'8' * 64}.json"
    assert marker.is_file()
    assert json.loads(marker.read_text())["gate_identity_sha256"] == "8" * 64
    with pytest.raises(RUNNER["ProtocolPartyTrainGateError"], match="already consumed"):
        RUNNER["_write_global_claim"](readiness)


def test_claim_registry_ignores_home_and_preflight_validation_is_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "redirected-home"))
    account_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    assert RUNNER["_claim_registry_root"]().is_relative_to(account_home)

    prepare = RUNNER["_prepare_claim_registry"]
    globals_ = prepare.__globals__
    original = globals_["_claim_registry_root"]
    missing = tmp_path / "missing" / "one-shot-claims-v1"
    globals_["_claim_registry_root"] = lambda: missing
    try:
        with pytest.raises(
            RUNNER["ProtocolPartyTrainGateError"],
            match="must be provisioned",
        ):
            prepare()
        assert not missing.exists()
        missing.mkdir(parents=True, mode=0o700)
        missing.chmod(0o700)
        assert prepare() == missing.resolve()
        missing.chmod(0o755)
        with pytest.raises(RUNNER["ProtocolPartyTrainGateError"], match="invalid"):
            prepare()
    finally:
        globals_["_claim_registry_root"] = original


def test_representation_failure_stops_before_model_fit() -> None:
    events: list[str] = []

    class Summary:
        def public_dict(self) -> dict[str, object]:
            return {"status": "complete", "manifest_sha256": "b" * 64}

    class Writer:
        summary = Summary()

        def __enter__(self) -> Writer:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def append(self, stream: str, _record: object, *, durable: bool) -> None:
            assert durable is True
            events.append(stream)

    class Root:
        def begin_artifact(self, artifact_id: str, *, kind: str) -> Writer:
            assert artifact_id == "protocol-party-train-gate-test"
            assert kind == "protocol_consistent_party_train_gate_v2"
            return Writer()

    readiness = _readiness(output_root=Root())
    representation = SimpleNamespace(
        passed=False,
        public_dict=lambda: {"passed": False},
    )
    run = RUNNER["_run"]
    globals_ = run.__globals__
    originals = {
        "prepare": globals_["_prepare_readiness"],
        "claim": globals_["_write_global_claim"],
        "decode": globals_["_decode_training_examples"],
        "audit": globals_["audit_protocol_party_representation"],
        "fit": globals_["run_protocol_party_leave_one_root_out"],
    }
    globals_["_prepare_readiness"] = lambda _args: readiness
    globals_["_write_global_claim"] = lambda _readiness: events.append("global_claim")
    globals_["_decode_training_examples"] = lambda _boundary: tuple(
        object() for _index in range(22)
    )
    globals_["audit_protocol_party_representation"] = lambda _prior, _training: representation
    globals_["run_protocol_party_leave_one_root_out"] = lambda *_args: pytest.fail(
        "representation failure started a model fit"
    )
    try:
        receipt = run(_args(preflight=False))
    finally:
        globals_["_prepare_readiness"] = originals["prepare"]
        globals_["_write_global_claim"] = originals["claim"]
        globals_["_decode_training_examples"] = originals["decode"]
        globals_["audit_protocol_party_representation"] = originals["audit"]
        globals_["run_protocol_party_leave_one_root_out"] = originals["fit"]

    assert events == ["global_claim", "preregistration", "representation_audit", "decision"]
    assert receipt["model_fits"] == 0
    assert receipt["evaluation"] is None
    assert receipt["decision"]["result"] == ("stop_before_fit_and_audit_representation_collisions")
    assert receipt["development_outcome_payloads_decoded"] == 0
    assert receipt["authority_promoted"] is False


def test_fit_result_can_only_design_fresh_development_not_execute_it() -> None:
    decision = RUNNER["_decision"](
        representation_passed=True,
        evaluation_passed=True,
    )

    assert decision["result"] == ("freeze_fresh_red_slice_design_for_missing_trainee_goal_cells")
    assert decision["candidate_retained_for_development_design"] is True
    assert decision["candidate_has_shadow_authority"] is False
    assert decision["candidate_has_live_authority"] is False
    assert decision["development_execution_authorized"] is False
    assert decision["crystal_execution_authorized"] is False
    assert decision["sealed_red_execution_authorized"] is False
    assert decision["full_game_replay_authorized"] is False
