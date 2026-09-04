# ruff: noqa: E402 -- standalone script is loaded after its local path setup.

from __future__ import annotations

import json
import runpy
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_red_living_dex_development_supplement_plan import _inputs, _plan

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

AUDITOR_PATH = SCRIPTS_ROOT / "audit_red_living_dex_development_supplement_capacity.py"
AUDITOR = runpy.run_path(
    str(AUDITOR_PATH),
    run_name="audit_red_living_dex_development_supplement_capacity_test",
)


def _args() -> list[str]:
    bindings = _plan().bindings
    return [
        "--expected-source-commit",
        bindings.source_commit,
        "--expected-source-bundle-sha256",
        bindings.source_bundle_sha256,
        "--registry-source-commit",
        "b" * 40,
        "--expected-registry-sha256",
        bindings.goal_registry_sha256,
        "--context-catalog",
        "/private/catalog.json",
        "--expected-context-catalog-sha256",
        bindings.context_catalog_sha256,
        "--context-plan",
        "/private/plan.json",
        "--expected-context-plan-sha256",
        bindings.context_plan_sha256,
        "--private-root",
        "/private/artifacts",
        "--rom",
        "/private/red.gb",
        "--expected-model-sha256",
        bindings.model_sha256,
        "--expected-model-record-sha256",
        bindings.model_record_sha256,
    ]


def test_parser_has_no_selection_publication_execution_or_retry_flags() -> None:
    parsed = AUDITOR["_parser"]().parse_args(_args())

    assert parsed.private_root == Path("/private/artifacts")
    for field in (
        "candidate_index",
        "execute",
        "fit",
        "publish",
        "retry",
        "speed",
        "watch",
    ):
        assert not hasattr(parsed, field)


def test_supply_audit_evidence_is_exactly_bound() -> None:
    AUDITOR["_authenticate_supply_audit_evidence"]()

    receipt = json.loads(AUDITOR["SUPPLY_AUDIT_EVIDENCE_PATH"].read_text())
    assert receipt["result"]["available_development_roots"] == 2
    assert receipt["result"]["minimum_new_roots_to_freeze"] == 3
    assert receipt["result"]["missing_option_kinds"] == ["manage_storage"]
    assert all(value == 0 for value in receipt["zero_effects"].values())


def test_main_rehearses_action_free_aggregate_census(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    capabilities, supply, _contexts, bindings = _inputs()
    contexts = tuple(
        SimpleNamespace(
            root_consumption_sha256=item.root.root.root_consumption_sha256,
            context_identity_sha256=f"context-{index}",
        )
        for index, item in enumerate(capabilities)
    )
    integrity_selected: tuple[object, ...] = ()

    def support(name: str):  # type: ignore[no-untyped-def]
        if name == "_authenticate_source":
            return lambda _args: (
                bindings.source_commit,
                bindings.source_bundle_sha256,
            )
        if name == "_authenticate_inputs":
            return lambda *_args: (
                Path("/private/red.gb"),
                bindings.rom_sha256,
                b"rom",
                contexts,
                bindings.context_catalog_sha256,
                bindings.context_plan_sha256,
            )
        if name == "_observe_candidates":
            return lambda *_args, **_kwargs: tuple(item.root for item in capabilities)
        if name == "_require_integrity":

            def integrity(*_args: object, **kwargs: object) -> None:
                nonlocal integrity_selected
                integrity_selected = kwargs["selected"]

            return integrity
        raise AssertionError(name)

    @contextmanager
    def lease(_registry: Path, *, exclusive: bool) -> Iterator[None]:
        assert exclusive is False
        yield

    state = SimpleNamespace(
        authenticated_contexts=0,
        controller_actions=0,
        emulator_frames=0,
        model_fits=0,
        model_predictions=0,
        provider_executions=0,
        root_claims=0,
        teacher_queries=0,
    )
    globals_ = AUDITOR["main"].__globals__
    monkeypatch.setitem(globals_, "_authenticate_supply_audit_evidence", lambda: None)
    monkeypatch.setitem(globals_, "_support", support)
    monkeypatch.setitem(globals_["_PROVIDER_SUPPORT"], "_DiagnosticState", lambda: state)
    monkeypatch.setitem(globals_, "open_private_root", lambda *_args, **_kwargs: object())
    monkeypatch.setitem(
        globals_,
        "inventory_red_living_dex_development_supply",
        lambda *_args, **_kwargs: supply,
    )
    monkeypatch.setitem(
        globals_,
        "build_runtime_identity",
        lambda: SimpleNamespace(sha256=bindings.runtime_identity_sha256),
    )
    monkeypatch.setitem(globals_, "require_pyboy_import_origins", lambda _runtime: None)
    monkeypatch.setitem(
        globals_,
        "load_strategic_navigation_scenario_registry",
        lambda _root: SimpleNamespace(registry_sha256=bindings.route_registry_sha256),
    )
    monkeypatch.setitem(
        globals_,
        "StrategicScenarioRouteWorld",
        SimpleNamespace(from_rom=lambda _rom: object()),
    )
    monkeypatch.setitem(globals_, "derive_red_living_dex_provider_corridors", lambda _world: ())
    checkpoint = object()
    monkeypatch.setitem(
        globals_,
        "RedLivingDexSetupEffectMeter",
        lambda: SimpleNamespace(checkpoint=lambda: checkpoint),
    )
    monkeypatch.setitem(globals_, "open_fixed_account_claim_registry", lambda: Path("claims"))
    monkeypatch.setitem(globals_, "fixed_account_claim_registry_lease", lease)
    monkeypatch.setitem(
        globals_,
        "enumerate_red_living_dex_causal_capabilities",
        lambda *_args, **_kwargs: capabilities,
    )

    assert AUDITOR["main"](_args()) == 0
    result = json.loads(capsys.readouterr().out)
    encoded = json.dumps(result, sort_keys=True)
    assert len(integrity_selected) == len(capabilities)
    assert result["selection_ready"] is True
    assert result["feasible_supplements"] > 0
    assert result["controller_actions"] == 0
    assert result["model_predictions"] == 0
    assert result["root_claims"] == 0
    assert "/private" not in encoded
    assert all(item.root.root.physical_root_sha256 not in encoded for item in capabilities)


def test_failure_receipt_sanitizes_private_exception(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setitem(
        AUDITOR["main"].__globals__,
        "_authenticate_supply_audit_evidence",
        lambda: (_ for _ in ()).throw(RuntimeError("/private/secret.json")),
    )

    assert AUDITOR["main"](_args()) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "failed_closed"
    assert result["stage"] == "supply_audit_evidence_authentication"
    assert result["controller_actions"] == 0
    assert result["model_predictions"] == 0
    assert "/private" not in json.dumps(result, sort_keys=True)


def test_source_contains_no_selector_publisher_controller_teacher_claim_or_fitter() -> None:
    source = AUDITOR_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "CompletionFirstGoalTeacher",
        "CountingExecutor",
        "execute_living_dex_policy_development",
        "fit_living_dex",
        "predict_living_dex",
        "publish_sealed_record",
        "select_living_dex_development_supplement",
        "write_root_claim",
    ):
        assert forbidden not in source
