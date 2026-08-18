from __future__ import annotations

import argparse
import inspect
import json
import runpy
import traceback
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/run_fresh_goal_manager_composition.py"),
    run_name="fresh_composition_script_test",
)


def _args(*, preflight_only: bool) -> argparse.Namespace:
    return argparse.Namespace(
        preflight_only=preflight_only,
        execute=not preflight_only,
        expected_execution_identity_sha256="a" * 64,
    )


def test_parser_requires_an_explicit_safe_mode() -> None:
    parser = SCRIPT["_parser"]()
    option_strings = {option for action in parser._actions for option in action.option_strings}
    assert "--preflight-only" in option_strings
    assert "--execute" in option_strings
    assert "--expected-execution-identity-sha256" in option_strings
    assert "--expected-runtime-sha256" in option_strings


def test_execution_presentation_is_frozen_before_any_readiness_work() -> None:
    with pytest.raises(
        SCRIPT["FreshCompositionRunError"],
        match="headless",
    ):
        SCRIPT["_prepare_readiness"](argparse.Namespace(watch=True, speed=1))


def test_preflight_returns_before_any_claim_or_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_globals = SCRIPT["_run"].__globals__
    readiness = object()
    admission = object()
    expected = {"status": "zero_action_preflight"}
    monkeypatch.setitem(runtime_globals, "_prepare_readiness", lambda _args: readiness)
    monkeypatch.setitem(runtime_globals, "_admit_root", lambda _readiness: admission)
    monkeypatch.setitem(
        runtime_globals,
        "_preflight_receipt",
        lambda _readiness, _admission: expected,
    )

    def forbidden(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("preflight crossed the execution boundary")

    monkeypatch.setitem(runtime_globals, "_execute", forbidden)

    assert SCRIPT["_run"](_args(preflight_only=True)) == expected


@pytest.mark.parametrize(
    ("failed_stage", "expected_calls"),
    [
        ("readiness_authentication", ["readiness_authentication"]),
        (
            "action_free_admission",
            ["readiness_authentication", "action_free_admission"],
        ),
        (
            "success_receipt_construction",
            [
                "readiness_authentication",
                "action_free_admission",
                "success_receipt_construction",
            ],
        ),
    ],
)
def test_run_reduces_preclaim_failures_to_allowlisted_stages(
    monkeypatch: pytest.MonkeyPatch,
    failed_stage: str,
    expected_calls: list[str],
) -> None:
    runtime_globals = SCRIPT["_run"].__globals__
    calls: list[str] = []
    private_failure = RuntimeError("opaque-private-root-id must never escape")

    def step(stage: str, value: object) -> object:
        calls.append(stage)
        if stage == failed_stage:
            raise private_failure
        return value

    monkeypatch.setitem(
        runtime_globals,
        "_prepare_readiness",
        lambda _args: step("readiness_authentication", object()),
    )
    monkeypatch.setitem(
        runtime_globals,
        "_admit_root",
        lambda _readiness: step("action_free_admission", object()),
    )
    monkeypatch.setitem(
        runtime_globals,
        "_preflight_receipt",
        lambda _readiness, _admission: step("success_receipt_construction", {}),
    )

    with pytest.raises(SCRIPT["FreshCompositionPreclaimFailure"]) as raised:
        SCRIPT["_run"](_args(preflight_only=True))

    assert raised.value.stage == failed_stage
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True
    assert "opaque-private-root-id" not in "".join(traceback.format_exception(raised.value))
    assert calls == expected_calls


def test_execution_authorization_failure_is_observable_before_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_globals = SCRIPT["_execute"].__globals__
    claims = 0

    def forbidden_claim(*_args: object, **_kwargs: object) -> None:
        nonlocal claims
        claims += 1

    monkeypatch.setitem(runtime_globals, "write_root_claim", forbidden_claim)
    readiness = SimpleNamespace(
        rom_path=Path("private-rom"),
        source=SimpleNamespace(git_commit="1" * 40),
    )
    admission = SimpleNamespace(execution_identity_sha256="2" * 64)
    args = SimpleNamespace(expected_execution_identity_sha256="3" * 64)

    with pytest.raises(SCRIPT["FreshCompositionPreclaimFailure"]) as raised:
        SCRIPT["_execute"](args, readiness, admission)

    assert raised.value.stage == "execution_authorization"
    assert claims == 0


def test_late_execution_authorization_failure_still_precedes_identity_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_globals = SCRIPT["_execute"].__globals__
    claims = 0

    def forbidden_claim(*_args: object, **_kwargs: object) -> None:
        nonlocal claims
        claims += 1

    monkeypatch.setitem(runtime_globals, "write_root_claim", forbidden_claim)
    monkeypatch.setitem(
        runtime_globals,
        "rom_adjacent_artifacts",
        lambda _path: (_ for _ in ()).throw(RuntimeError("opaque-private-root-id")),
    )
    readiness = SimpleNamespace(
        rom_path=Path("private-rom"),
        source=SimpleNamespace(git_commit="1" * 40),
    )
    admission = SimpleNamespace(execution_identity_sha256="2" * 64)
    args = SimpleNamespace(expected_execution_identity_sha256="2" * 64)

    with pytest.raises(SCRIPT["FreshCompositionPreclaimFailure"]) as raised:
        SCRIPT["_execute"](args, readiness, admission)

    assert raised.value.stage == "execution_authorization"
    assert raised.value.__cause__ is None
    assert "opaque-private-root-id" not in "".join(traceback.format_exception(raised.value))
    assert claims == 0


def test_preclaim_failure_receipt_is_fixed_path_free_and_non_counting() -> None:
    assert SCRIPT["_PREFLIGHT_FAILURE_STAGES"] == {
        "action_free_admission",
        "execution_authorization",
        "readiness_authentication",
        "success_receipt_construction",
    }
    for stage in sorted(SCRIPT["_PREFLIGHT_FAILURE_STAGES"]):
        failure = SCRIPT["FreshCompositionPreclaimFailure"](stage)
        receipt = SCRIPT["_preclaim_failure_receipt"](failure)
        encoded = json.dumps(receipt, sort_keys=True)

        assert receipt["failure_stage"] == stage
        assert receipt["claim_written_by_this_invocation"] is False
        assert receipt["execution_identity_authorized"] is False
        assert receipt["admission_status"] == (
            "passed"
            if stage in {"execution_authorization", "success_receipt_construction"}
            else "not_attested"
        )
        assert receipt["protected_access_status"] == (
            "not_attested" if stage == "readiness_authentication" else "verified_absent"
        )
        assert set(receipt["counter_treatment"].values()) == {0}
        assert set(receipt["zero_effects"].values()) == {0}
        assert "sealed_red_accesses" not in receipt["zero_effects"]
        assert "crystal_accesses" not in receipt["zero_effects"]
        assert "/Volumes/" not in encoded
        assert "opaque-private-root-id" not in encoded

    with pytest.raises(ValueError, match="not allowlisted"):
        SCRIPT["FreshCompositionPreclaimFailure"]("private_dynamic_stage")


def test_main_emits_exactly_one_canonical_failure_envelope_and_returns_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime_globals = SCRIPT["main"].__globals__

    class Parser:
        @staticmethod
        def parse_args(_argv: list[str] | None) -> object:
            return object()

    monkeypatch.setitem(runtime_globals, "_parser", lambda: Parser())

    def failed(_args: object) -> dict[str, object]:
        error = RuntimeError("opaque-private-root-id")
        raise SCRIPT["FreshCompositionPreclaimFailure"]("readiness_authentication") from error

    monkeypatch.setitem(runtime_globals, "_run", failed)

    assert SCRIPT["main"]([]) == 2
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert len(lines) == 1
    assert captured.err == ""
    assert json.loads(lines[0]) == SCRIPT["_preclaim_failure_receipt"](
        SCRIPT["FreshCompositionPreclaimFailure"]("readiness_authentication")
    )
    assert lines[0] == json.dumps(
        json.loads(lines[0]),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert "opaque-private-root-id" not in lines[0]


def test_preflight_success_serialization_failure_uses_the_same_sanitized_stage(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime_globals = SCRIPT["main"].__globals__

    class Parser:
        @staticmethod
        def parse_args(_argv: list[str] | None) -> object:
            return SimpleNamespace(preflight_only=True)

    monkeypatch.setitem(runtime_globals, "_parser", lambda: Parser())
    monkeypatch.setitem(runtime_globals, "_run", lambda _args: {"invalid": object()})

    assert SCRIPT["main"]([]) == 2
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert len(lines) == 1
    receipt = json.loads(lines[0])
    assert receipt["failure_stage"] == "success_receipt_construction"
    assert receipt["admission_status"] == "passed"
    assert captured.err == ""


def test_live_source_orders_global_claim_before_local_claim_and_emulator() -> None:
    source = inspect.getsource(SCRIPT["_execute"])

    assert source.index("write_root_claim(") < source.index("begin_episode(")
    assert source.index("rom_adjacent_artifacts(") < source.index("write_root_claim(")
    assert source.index("try:") < source.index("begin_episode(")
    assert source.index("begin_episode(") < source.index("PyBoyAdapter(")
    assert source.index("durable=True") < source.index("PyBoyAdapter(")
    assert 'partition="unassigned"' in source
    assert "watch=False" in source
    assert "speed=None" in source


def test_preflight_receipt_is_path_free_and_advances_no_counter() -> None:
    source = SimpleNamespace(
        git_commit="1" * 40, public_dict=lambda: {"git_commit": "1" * 40, "worktree_dirty": False}
    )
    readiness = SimpleNamespace(
        source=source,
        design_sha256="2" * 64,
        runner_sha256="3" * 64,
        qualification_module_sha256="4" * 64,
        candidate=SimpleNamespace(
            plan=SimpleNamespace(
                plan_sha256="f" * 64,
                model_file_sha256="0" * 64,
                model_canonical_sha256="5" * 64,
            ),
            registry=SimpleNamespace(registry_sha256="1" * 64),
            catalog=SimpleNamespace(catalog_sha256="2" * 64),
            fit_summary_sha256="3" * 64,
        ),
        rom=SimpleNamespace(sha256="4" * 64),
        runtime=SimpleNamespace(
            sha256="5" * 64,
            public_dict=lambda: {"schema": "pokemon-red-runtime-identity-v1"},
        ),
        profile=SimpleNamespace(profile_sha256="5" * 64),
        skill_manifest={"manifest_sha256": "6" * 64},
        nonsealed_attestation_sha256="7" * 64,
        root_provenance_sha256="d" * 64,
        root_lineage_id=f"red-goal-root-{'e' * 64}",
    )
    admission = SimpleNamespace(
        binding_manifest_sha256="8" * 64,
        semantic_state_sha256="7" * 64,
        completion_contract_sha256="9" * 64,
        specimen_ledger_sha256="a" * 64,
        required_specimens_sha256="b" * 64,
        execution_identity_sha256="c" * 64,
        initial_available_goal_count=3,
        initial_available_goal_kinds=(
            "acquire_species",
            "restore_team",
            "explore",
        ),
    )

    receipt = SCRIPT["_preflight_receipt"](readiness, admission)
    encoded = json.dumps(receipt, sort_keys=True)

    assert receipt["zero_effects"]["model_predictions"] == 0
    assert receipt["zero_effects"]["composition_episodes"] == 0
    assert receipt["runner_and_one_shot"]["execution_identity_consumed"] is False
    assert receipt["root_admission"]["prior_contexts_checked"] == 81
    assert receipt["input_bindings"]["runtime_sha256"] == "5" * 64
    assert (
        receipt["durability"]["pre_writer_storage_failure_leaves_durable_root_consumption_claim"]
        is True
    )
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    assert "qual-acquisition" not in encoded


def test_execution_identity_binds_exact_source_runner_candidate_and_root() -> None:
    def readiness(**changes: str) -> SimpleNamespace:
        source_commit = changes.get("source_commit", "1" * 40)
        return SimpleNamespace(
            source=SimpleNamespace(git_commit=source_commit),
            root_consumption_sha256=changes.get("root", "2" * 64),
            runner_sha256=changes.get("runner", "3" * 64),
            qualification_module_sha256=changes.get("qualification", "4" * 64),
            design_sha256="5" * 64,
            nonsealed_attestation_sha256=changes.get("attestation", "6" * 64),
            root_provenance_sha256="7" * 64,
            rom=SimpleNamespace(sha256="8" * 64),
            runtime=SimpleNamespace(sha256=changes.get("runtime", "7" * 64)),
            candidate=SimpleNamespace(
                plan=SimpleNamespace(
                    plan_sha256=changes.get("plan", "9" * 64),
                    model_file_sha256="a" * 64,
                    model_canonical_sha256="b" * 64,
                ),
                registry=SimpleNamespace(registry_sha256="c" * 64),
                catalog=SimpleNamespace(catalog_sha256="d" * 64),
                fit_summary_sha256="e" * 64,
            ),
            profile=SimpleNamespace(profile_sha256="f" * 64),
            skill_manifest={"manifest_sha256": "0" * 64},
            root_lineage_id=f"red-goal-root-{'1' * 64}",
        )

    def identity(value: SimpleNamespace) -> str:
        return SCRIPT["_execution_identity_sha256"](
            value,
            binding_manifest_sha256="2" * 64,
            semantic_state_sha256="3" * 64,
            completion_contract_sha256="4" * 64,
            specimen_ledger_sha256="5" * 64,
            required_specimens_sha256="6" * 64,
        )

    baseline = identity(readiness())
    assert identity(readiness(source_commit="a" * 40)) != baseline
    assert identity(readiness(runner="a" * 64)) != baseline
    assert identity(readiness(qualification="a" * 64)) != baseline
    assert identity(readiness(attestation="a" * 64)) != baseline
    assert identity(readiness(runtime="a" * 64)) != baseline
    assert identity(readiness(plan="a" * 64)) != baseline
    assert identity(readiness(root="a" * 64)) != baseline


def test_admission_rejects_bindings_that_differ_from_historical_root() -> None:
    source = inspect.getsource(SCRIPT["_admit_root"])

    assert "readiness.historical_binding_manifest_sha256" in source
    assert "authenticated historical root" in source


def test_pre_writer_storage_failure_occurs_after_durable_global_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class OutputRoot:
        def begin_episode(self, _episode_id: str) -> object:
            events.append("begin")
            raise OSError("storage unavailable")

    readiness = SimpleNamespace(
        rom_path=Path("private-rom"),
        source=SimpleNamespace(git_commit="1" * 40),
        claim_registry=Path("fixed-account-registry"),
        root_consumption_sha256="2" * 64,
        runner_sha256="3" * 64,
        output_root=OutputRoot(),
        episode_id="episode",
    )
    admission = SimpleNamespace(execution_identity_sha256="4" * 64)
    args = SimpleNamespace(expected_execution_identity_sha256="4" * 64)
    runtime_globals = SCRIPT["_execute"].__globals__
    monkeypatch.setitem(
        runtime_globals,
        "rom_adjacent_artifacts",
        lambda _path: events.append("adjacent") or (),
    )
    monkeypatch.setitem(
        runtime_globals,
        "write_root_claim",
        lambda *_args, **_kwargs: events.append("claim"),
    )

    with pytest.raises(OSError, match="storage unavailable"):
        SCRIPT["_execute"](args, readiness, admission)

    assert events == ["adjacent", "claim", "begin"]


def test_nonsealed_attestation_is_exact_and_canonical(tmp_path: Path) -> None:
    document: dict[str, Any] = {
        "controller_actions_before_freeze": 0,
        "envelope_sha256": "b" * 64,
        "model_predictions_before_freeze": 0,
        "origin_class": "preexisting_nonsealed_goal_manager_qualification_capture",
        "partition": "fresh_nonsealed_red_development",
        "prior_root_lineage_id": f"red-goal-root-{'d' * 64}",
        "profile_sha256": "c" * 64,
        "root_provenance_sha256": "e" * 64,
        "schema": "pokemon.red.fresh-composition-nonsealed-root-attestation.v1",
        "sealed": False,
        "state_sha256": "a" * 64,
    }
    path = tmp_path / "attestation.json"
    path.write_text(
        json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="ascii",
    )
    capture = SimpleNamespace(state_sha256="a" * 64, envelope_sha256="b" * 64)

    SCRIPT["_require_nonsealed_attestation"](
        path,
        capture=capture,
        profile_sha256="c" * 64,
        expected_attestation_sha256=SCRIPT["hashlib"].sha256(path.read_bytes()).hexdigest(),
        root_provenance_sha256="e" * 64,
        root_lineage_id=f"red-goal-root-{'d' * 64}",
    )

    document["sealed"] = True
    path.write_text(
        json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="ascii",
    )
    with pytest.raises(SCRIPT["FreshCompositionRunError"], match="differs"):
        SCRIPT["_require_nonsealed_attestation"](
            path,
            capture=capture,
            profile_sha256="c" * 64,
            expected_attestation_sha256=SCRIPT["hashlib"].sha256(path.read_bytes()).hexdigest(),
            root_provenance_sha256="e" * 64,
            root_lineage_id=f"red-goal-root-{'d' * 64}",
        )


def test_root_provenance_authenticates_the_preexisting_lineage(tmp_path: Path) -> None:
    document = {
        "actions_executed": 0,
        "assignment_id": "967788b63a5045574a67fe59a59a2d9cbe2718ad9fad543e6e8199ceadd9320a",
        "available_goal_count": 3,
        "available_goal_kinds": ["acquire_species", "restore_team", "explore"],
        "available_menu_sha256": "cdbd9511f1fb64363ba57e875716bb62447c94cb2098764ef1be239ad8ca7b3e",
        "binding_manifest_sha256": (
            "358845e7abe5e5bb815ccdbd2d26195f9e29568fd52e0b9f55efd1370562b508"
        ),
        "candidate_goal_kinds": [
            "explore",
            "manage_storage",
            "evolve_species",
            "develop_team",
            "advance_story",
            "recover_control",
            "resupply",
            "restore_team",
            "acquire_species",
        ],
        "capture_id": "qual-acquisition-heavy-ae6f3bf",
        "collection_id": "red-goal-manager-v1",
        "envelope_sha256": "55a7ee55e57cd23b45ff8f1392f06df9106daf95baba8b829acf46655191d3e5",
        "episode_created": False,
        "focus_kind": "restore_team",
        "focus_pressure": 0.5745697896749522,
        "passed": True,
        "policy_context_sha256": "315f1be80b8cad208ccfc8f90c825ee5ac0735e91f2f9a4ebb7bcbbee6c5990e",
        "private_path_fields": 0,
        "question_sha256": "5422cf8e7e08aaa5943bf80124d0506b84e359512abd84fc3ffcde533025dcba",
        "registry_sha256": "b30328606fbdc383e52a49b3c9b7800ffa65f14099605aa7b99e827aa35dc1dc",
        "schema": "pokemon-red-goal-manager-context-preflight-v2",
        "selected_candidate_index": 7,
        "selected_kind": "restore_team",
        "slot_id": "red-goal-v1-038-restore_team-train-02",
        "source_bundle_sha256": "4e20e35e8286818461def89101cf25c761c35cc6736342e224896730c4814c64",
        "source_commit": "ae6f3bf07493a54c19d4899949f8c9bfcf706584",
        "state_sha256": "6434b96be928bba88c3242a7a3076c8f88ae2415331da42e28928a8464ecaaf4",
    }
    path = tmp_path / "provenance.json"
    path.write_text(
        json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="ascii",
    )
    digest = SCRIPT["hashlib"].sha256(path.read_bytes()).hexdigest()
    capture = SimpleNamespace(
        state_sha256=document["state_sha256"],
        envelope_sha256=document["envelope_sha256"],
        capture_id=document["capture_id"],
    )

    lineage, binding_manifest_sha256 = SCRIPT["_authenticate_root_provenance"](
        path,
        capture=capture,
        expected_sha256=digest,
    )

    assert lineage == f"red-goal-root-{document['assignment_id']}"
    assert binding_manifest_sha256 == document["binding_manifest_sha256"]

    path.write_text(json.dumps(document), encoding="ascii")
    changed_digest = SCRIPT["hashlib"].sha256(path.read_bytes()).hexdigest()
    with pytest.raises(
        SCRIPT["FreshCompositionRunError"],
        match="authenticated historical preflight",
    ):
        SCRIPT["_authenticate_root_provenance"](
            path,
            capture=capture,
            expected_sha256=changed_digest,
        )


def test_failure_terminal_is_durable_and_retains_a_sanitized_first_failure() -> None:
    events: list[tuple[str, object]] = []

    class Writer:
        def append(
            self,
            stream: str,
            record: object,
            *,
            durable: bool,
        ) -> None:
            events.append((stream, (record, durable)))

        def abort(self, reason: str) -> None:
            events.append(("abort", reason))

    SCRIPT["_retain_failure_terminal"](
        Writer(),
        sink=None,
        episode_id="episode",
        execution_identity_sha256="a" * 64,
        failure=SCRIPT["FreshCompositionRunError"]("private detail"),
    )

    record, durable = events[0][1]
    assert events[0][0] == "terminal"
    assert isinstance(record, dict)
    assert durable is True
    assert record["failure_phase"] == "runner_guard"
    assert record["failure_class"] == "runner_guard_error"
    assert "private detail" not in json.dumps(record)
    assert events[1] == ("abort", "composition_failed")


def test_failed_terminal_sync_is_not_retried_but_artifact_is_aborted() -> None:
    events: list[str] = []

    class Writer:
        def append(self, *_args: object, **_kwargs: object) -> None:
            events.append("direct_append")

        def abort(self, _reason: str) -> None:
            events.append("abort")

    class Sink:
        def record_event(self, _event: object) -> None:
            events.append("sink_append_attempt")
            raise OSError("fsync failed after a possible write")

    SCRIPT["_retain_failure_terminal"](
        Writer(),
        sink=Sink(),
        episode_id="episode",
        execution_identity_sha256="a" * 64,
        failure=RuntimeError("failed"),
    )

    assert events == ["sink_append_attempt", "abort"]
