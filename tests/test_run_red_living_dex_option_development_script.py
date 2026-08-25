# ruff: noqa: E402 -- standalone runner is loaded after its script-local imports.

from __future__ import annotations

import hashlib
import json
import runpy
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

SCRIPT_PATH = PROJECT_ROOT / "scripts/run_red_living_dex_option_development.py"
SCRIPT = runpy.run_path(
    str(SCRIPT_PATH),
    run_name="run_red_living_dex_option_development_test",
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _args() -> list[str]:
    return [
        "--registry-source-commit",
        "a" * 40,
        "--expected-registry-sha256",
        _sha("registry"),
        "--context-catalog",
        "/protected/catalog.json",
        "--expected-context-catalog-sha256",
        _sha("catalog"),
        "--context-plan",
        "/protected/plan.json",
        "--expected-context-plan-sha256",
        _sha("plan"),
        "--slot-id",
        "red-goal-v1-999-evolve_species-train-99",
        "--expected-profile-sha256",
        _sha("profile"),
        "--private-root",
        "/protected/artifacts",
        "--rom",
        "/protected/red.gb",
    ]


def test_parser_requires_explicit_context_and_limits_watch_speed() -> None:
    parsed = SCRIPT["_parser"]().parse_args(_args())

    assert parsed.slot_id == "red-goal-v1-999-evolve_species-train-99"
    assert parsed.watch is False
    assert parsed.speed is None
    with pytest.raises(SCRIPT["RedLivingDexOptionRunError"]):
        SCRIPT["_parser"]().parse_args([*_args(), "--speed", "8"])


def test_public_failure_stops_before_private_read_and_stays_path_free(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_calls = 0

    def private(*args: object, **kwargs: object) -> object:
        nonlocal private_calls
        del args, kwargs
        private_calls += 1
        raise AssertionError("private readiness ran")

    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_development_gate",
        lambda: (_ for _ in ()).throw(
            SCRIPT["RedLivingDexOptionRunError"]("public_evidence_authentication")
        ),
    )
    monkeypatch.setattr(SCRIPT["support"], "_prepare_readiness", private)

    assert SCRIPT["main"](_args()) == 1

    result = json.loads(capsys.readouterr().out)
    assert private_calls == 0
    assert result["failure_stage"] == "public_evidence_authentication"
    assert result["teacher_queries"] == 0
    assert "/protected" not in json.dumps(result)


@pytest.mark.parametrize(("settled", "expected_exit"), ((True, 0), (False, 2)))
def test_main_reports_settled_or_censored_terminal_without_substitution(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    settled: bool,
    expected_exit: int,
) -> None:
    events: list[object] = []
    gate = object()
    readiness = SimpleNamespace(assignment=SimpleNamespace(slot_id="chosen"))
    result = SCRIPT["_ExecutionResult"](
        {
            "schema": SCRIPT["RESULT_SCHEMA"],
            "status": "settled" if settled else "interrupted",
            "private_path_fields": 0,
        },
        settled,
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_development_gate",
        lambda: (events.append("gate"), gate)[1],
    )

    def readiness_call(args: object, actual_gate: object, *, selected_slot_id: str) -> object:
        del args
        events.append(("readiness", actual_gate, selected_slot_id))
        return readiness

    monkeypatch.setattr(SCRIPT["support"], "_prepare_readiness", readiness_call)
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_excluded_v1_reset_states",
        lambda args, actual: (events.append(("exclude", args.slot_id, actual)), frozenset())[1],
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_execute",
        lambda args, actual, excluded: (
            events.append(("execute", args.slot_id, actual, excluded)),
            result,
        )[1],
    )

    assert SCRIPT["main"](_args()) == expected_exit

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == ("settled" if settled else "interrupted")
    assert events == [
        "gate",
        (
            "readiness",
            gate,
            "red-goal-v1-999-evolve_species-train-99",
        ),
        (
            "exclude",
            "red-goal-v1-999-evolve_species-train-99",
            readiness,
        ),
        (
            "execute",
            "red-goal-v1-999-evolve_species-train-99",
            readiness,
            frozenset(),
        ),
    ]


def test_retired_v1_slot_is_rejected_without_catalog_read() -> None:
    readiness = SimpleNamespace(
        assignment=SimpleNamespace(slot_id=SCRIPT["support"].SELECTED_SLOT_ID)
    )
    args = SimpleNamespace(registry_source_commit="a" * 40)

    with pytest.raises(
        SCRIPT["RedLivingDexOptionRunError"],
        match="retired_v1_context_reuse",
    ):
        SCRIPT["_excluded_v1_reset_states"](args, readiness)


def test_root_claim_is_durable_exact_and_precedes_prediction_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    claim: dict[str, str] = {}
    readiness = SimpleNamespace(
        gate=SimpleNamespace(
            public_bindings={
                "source_commit": "a" * 40,
                "source_bundle_sha256": _sha("source"),
                "runner_sha256": _sha("runner"),
            }
        ),
        context_identity_sha256=_sha("context"),
        authenticated_fit=SimpleNamespace(model_sha256=_sha("model")),
    )
    globals_ = SCRIPT["_claim_development_root"].__globals__
    monkeypatch.setitem(
        globals_,
        "open_fixed_account_claim_registry",
        lambda: Path("/account-claim-registry"),
    )
    monkeypatch.setitem(
        globals_,
        "fixed_account_claim_registry_lease",
        lambda registry, *, exclusive: (
            events.append(("lease", registry, exclusive)),
            nullcontext(),
        )[1],
    )
    monkeypatch.setattr(
        SCRIPT["support"],
        "_require_fit_claim",
        lambda registry: events.append(("fit", registry)),
    )
    monkeypatch.setitem(
        globals_,
        "root_claim_is_available",
        lambda registry, identity: (
            events.append(("available", registry, identity)),
            True,
        )[1],
    )

    def write(registry: Path, **fields: str) -> None:
        events.append(("write", registry))
        claim.update(
            {
                "schema": "pokemon.red.fresh-composition-root-claim.v1",
                **fields,
            }
        )

    monkeypatch.setitem(globals_, "write_root_claim", write)
    monkeypatch.setitem(
        globals_,
        "read_root_claim",
        lambda registry, identity: (
            events.append(("read", registry, identity)),
            dict(claim),
        )[1],
    )

    identity = SCRIPT["_claim_development_root"](
        readiness,
        physical_root=_sha("physical"),
        preparation_sha256=_sha("preparation"),
    )

    assert identity == claim["execution_identity_sha256"]
    assert claim["root_consumption_sha256"] == _sha("physical")
    assert claim["source_commit"] == "a" * 40
    assert claim["runner_sha256"] == _sha("runner")
    assert [event[0] for event in events] == [
        "lease",
        "fit",
        "available",
        "write",
        "read",
    ]


def test_consumed_root_refuses_before_claim_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes = 0
    readiness = SimpleNamespace(
        gate=SimpleNamespace(
            public_bindings={
                "source_commit": "a" * 40,
                "source_bundle_sha256": _sha("source"),
                "runner_sha256": _sha("runner"),
            }
        ),
        context_identity_sha256=_sha("context"),
        authenticated_fit=SimpleNamespace(model_sha256=_sha("model")),
    )
    globals_ = SCRIPT["_claim_development_root"].__globals__
    monkeypatch.setitem(
        globals_, "open_fixed_account_claim_registry", lambda: Path("/claim-registry")
    )
    monkeypatch.setitem(
        globals_,
        "fixed_account_claim_registry_lease",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setattr(SCRIPT["support"], "_require_fit_claim", lambda registry: None)
    monkeypatch.setitem(globals_, "root_claim_is_available", lambda *args: False)

    def write(*args: object, **kwargs: object) -> None:
        nonlocal writes
        del args, kwargs
        writes += 1

    monkeypatch.setitem(globals_, "write_root_claim", write)

    with pytest.raises(
        SCRIPT["RedLivingDexOptionRunError"],
        match="development_root_already_consumed",
    ):
        SCRIPT["_claim_development_root"](
            readiness,
            physical_root=_sha("physical"),
            preparation_sha256=_sha("preparation"),
        )
    assert writes == 0


def test_runner_orders_one_claim_prediction_start_record_and_selected_execution() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    execution = source[source.index("def _execute(") : source.index("def _claim_development_root(")]

    prepare = execution.index("prepared = prepare_red_living_dex_option(")
    claim = execution.index("execution_identity = _claim_development_root(")
    score = execution.index("decision = score_red_living_dex_option(")
    start = execution.index("start_record = readiness.store.publish_sealed_record(")
    selected = execution.index("episode = execute_red_living_dex_option(")
    terminal = execution.index("terminal_record = readiness.store.publish_sealed_record(")
    assert prepare < claim < score < start < selected < terminal
    assert execution.count("score_red_living_dex_option(") == 1
    assert execution.count("execute_red_living_dex_option(") == 1
    assert SCRIPT["_MAX_CONTROLLER_ACTIONS"] > 0
    assert SCRIPT["_MAX_CONTROLLER_FRAMES"] > 0
    assert "teacher_choice" not in source
    assert "teacher_fallback" not in source


def test_failure_receipt_never_echoes_private_details() -> None:
    result = SCRIPT["_failure_receipt"]("private_readiness_authentication")

    assert result["status"] == "failed_closed"
    assert result["teacher_queries"] == 0
    assert result["private_path_fields"] == 0
    assert "/protected" not in json.dumps(result)
