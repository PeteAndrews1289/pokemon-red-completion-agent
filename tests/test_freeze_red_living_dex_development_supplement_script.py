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
from test_red_living_dex_development_supplement_plan import _plan

from pokemon_red_completion.private_artifacts import initialize_private_root
from pokemon_red_completion.red_living_dex_development_supplement_plan import (
    RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_ID,
    RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_KIND,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

FREEZER_PATH = SCRIPTS_ROOT / "freeze_red_living_dex_development_supplement.py"
FREEZER = runpy.run_path(
    str(FREEZER_PATH),
    run_name="freeze_red_living_dex_development_supplement_test",
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


def _store(tmp_path: Path):  # type: ignore[no-untyped-def]
    repository = tmp_path / "repository"
    private = tmp_path / "private"
    repository.mkdir()
    private.mkdir()

    def device_id(path: Path) -> int:
        return 2 if path == private.resolve() else 1

    return initialize_private_root(
        private,
        repository_root=repository,
        device_id=device_id,
        git_worktree_probe=lambda _path: False,
    )


def test_parser_has_no_behavior_prediction_execution_or_retry_flags() -> None:
    parsed = FREEZER["_parser"]().parse_args(_args())

    assert parsed.private_root == Path("/private/artifacts")
    for field in (
        "candidate_index",
        "execute",
        "fit",
        "retry",
        "speed",
        "watch",
    ):
        assert not hasattr(parsed, field)


def test_supply_audit_evidence_is_exactly_bound() -> None:
    FREEZER["_authenticate_supply_audit_evidence"]()

    receipt = json.loads(FREEZER["SUPPLY_AUDIT_EVIDENCE_PATH"].read_text())
    assert receipt["result"]["available_development_roots"] == 2
    assert receipt["result"]["minimum_new_roots_to_freeze"] == 3
    assert receipt["result"]["missing_option_kinds"] == ["manage_storage"]
    assert all(value == 0 for value in receipt["zero_effects"].values())


def test_main_rehearses_complete_action_free_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = _plan()
    bindings = plan.bindings
    store = _store(tmp_path)
    contexts = tuple(
        SimpleNamespace(
            root_consumption_sha256=item.capability.root.root.root_consumption_sha256,
            context_identity_sha256=item.context_identity_sha256,
        )
        for item in plan.assignments
    )
    capabilities = tuple(item.capability for item in plan.assignments)
    integrity_calls = 0

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
            return lambda *_args, **_kwargs: tuple(
                item.capability.root for item in plan.assignments
            )
        if name == "_require_integrity":

            def integrity(*_args: object, **_kwargs: object) -> None:
                nonlocal integrity_calls
                integrity_calls += 1

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
        outcomes=0,
        provider_executions=0,
        root_claims=0,
        teacher_queries=0,
    )
    globals_ = FREEZER["main"].__globals__
    monkeypatch.setitem(globals_, "_authenticate_supply_audit_evidence", lambda: None)
    monkeypatch.setitem(globals_, "_support", support)
    monkeypatch.setitem(globals_["_PROVIDER_SUPPORT"], "_DiagnosticState", lambda: state)
    monkeypatch.setitem(globals_, "open_private_root", lambda *_args, **_kwargs: store)
    monkeypatch.setitem(
        globals_,
        "inventory_red_living_dex_development_supply",
        lambda *_args, **_kwargs: object(),
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
    monkeypatch.setitem(
        globals_,
        "freeze_red_living_dex_development_supplement_plan",
        lambda *_args, **_kwargs: plan,
    )

    assert FREEZER["main"](_args()) == 0
    result = json.loads(capsys.readouterr().out)
    assert integrity_calls == 1
    assert result["new_roots"] == 3
    assert result["private_plan_reopened"] is True
    assert result["controller_actions"] == 0
    assert result["model_predictions"] == 0
    assert result["training_targets"] == 0
    assert "/private" not in json.dumps(result, sort_keys=True)
    assert (
        store.find_sealed_record(
            RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_ID,
            expected_kind=RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_KIND,
        )
        is not None
    )


def test_failure_receipt_sanitizes_private_exception(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setitem(
        FREEZER["main"].__globals__,
        "_authenticate_supply_audit_evidence",
        lambda: (_ for _ in ()).throw(RuntimeError("/private/secret.json")),
    )

    assert FREEZER["main"](_args()) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "failed_closed"
    assert result["stage"] == "supply_audit_evidence_authentication"
    assert result["controller_actions"] == 0
    assert result["model_predictions"] == 0
    assert "/private" not in json.dumps(result, sort_keys=True)


def test_source_contains_no_controller_teacher_claim_scorer_or_fitter() -> None:
    source = FREEZER_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "CompletionFirstGoalTeacher",
        "CountingExecutor",
        "execute_living_dex_policy_development",
        "fit_living_dex",
        "predict_living_dex",
        "write_root_claim",
    ):
        assert forbidden not in source
