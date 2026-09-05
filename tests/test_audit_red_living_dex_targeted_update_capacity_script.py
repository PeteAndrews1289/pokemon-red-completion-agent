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
from test_red_living_dex_clustered_train_runner import _successor_clustered_fixture
from test_red_living_dex_development_supplement_plan import _inputs, _plan

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

AUDITOR_PATH = SCRIPTS_ROOT / "audit_red_living_dex_targeted_update_capacity.py"
AUDITOR = runpy.run_path(
    str(AUDITOR_PATH),
    run_name="audit_red_living_dex_targeted_update_capacity_test",
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


def test_parser_has_inventory_inputs_but_no_action_or_fit_controls() -> None:
    parsed = AUDITOR["_parser"]().parse_args(_args())

    assert parsed.private_root == Path("/private/artifacts")
    for field in (
        "candidate_index",
        "execute",
        "fit",
        "outcome",
        "publish",
        "retry",
        "seed",
        "watch",
    ):
        assert not hasattr(parsed, field)


def test_main_emits_only_aggregate_targeted_capacity(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan, _binding = _successor_clustered_fixture()
    capabilities = tuple(item.capability for item in plan.assignments)
    _candidate_capabilities, supply, _contexts, bindings = _inputs()
    exclusions = SimpleNamespace(
        excluded_lineages=frozenset({"a" * 64}),
        development_physical_roots=frozenset({"b" * 64}),
        public_dict=lambda: {
            "train_lineages_excluded": 18,
            "development_lineages_excluded": 7,
            "private_identity_fields": 0,
            "outcomes_opened": 0,
        },
    )
    result = SimpleNamespace(
        capacity_sufficient=False,
        public_dict=lambda: {
            "capacity_sufficient": False,
            "train_maximum_matching": 10,
            "development_maximum_matching": 4,
            "controller_actions": 0,
            "outcomes_opened": 0,
            "private_identity_fields": 0,
            "root_claims": 0,
        },
    )
    integrity_selected: tuple[object, ...] = ()

    def support(name: str):  # type: ignore[no-untyped-def]
        if name == "_authenticate_source":
            return lambda _args: (bindings.source_commit, bindings.source_bundle_sha256)
        if name == "_authenticate_inputs":
            return lambda *_args: (
                Path("/private/red.gb"),
                bindings.rom_sha256,
                b"rom",
                tuple(range(20)),
                bindings.context_catalog_sha256,
                bindings.context_plan_sha256,
            )
        if name == "_authenticate_supplemental_roots":
            return lambda *_args: ()
        if name == "_observe_candidates":
            return lambda *_args, **_kwargs: tuple(item.root for item in capabilities)
        if name == "_observe_supplemental_candidates":
            return lambda *_args, **_kwargs: ()
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
        authenticated_supplemental_roots=0,
        controller_actions=0,
        emulator_frames=0,
        model_fits=0,
        model_predictions=0,
        provider_executions=0,
        root_claims=0,
        teacher_queries=0,
    )
    globals_ = AUDITOR["main"].__globals__
    monkeypatch.setitem(globals_, "_support", support)
    monkeypatch.setitem(globals_["_PROVIDER_SUPPORT"], "_DiagnosticState", lambda: state)
    monkeypatch.setitem(globals_, "open_private_root", lambda *_args, **_kwargs: object())
    monkeypatch.setitem(
        globals_,
        "inventory_red_living_dex_development_supply",
        lambda *_args, **_kwargs: supply,
    )
    monkeypatch.setitem(
        globals_, "load_red_living_dex_development_supplement", lambda _store: _plan().supplement
    )
    monkeypatch.setitem(
        globals_, "build_red_living_dex_targeted_exclusions", lambda *_args: exclusions
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
        globals_, "audit_red_living_dex_targeted_update_capacity", lambda *_args, **_kwargs: result
    )

    assert AUDITOR["main"](_args()) == 0
    document = json.loads(capsys.readouterr().out)
    encoded = json.dumps(document, sort_keys=True)
    assert len(integrity_selected) == len(capabilities)
    assert document["status"] == "targeted_update_capacity_insufficient"
    assert document["train_maximum_matching"] == 10
    assert document["development_maximum_matching"] == 4
    assert document["exclusions"]["train_lineages_excluded"] == 18
    assert document["controller_actions"] == 0
    assert document["outcomes_opened"] == 0
    assert document["provider_executions"] == 0
    assert "/private" not in encoded
    assert "a" * 64 not in encoded
    assert "b" * 64 not in encoded


def test_failure_receipt_sanitizes_private_exception(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setitem(
        AUDITOR["main"].__globals__,
        "_support",
        lambda _name: (_ for _ in ()).throw(RuntimeError("/private/secret.json")),
    )

    assert AUDITOR["main"](_args()) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "failed_closed"
    assert result["stage"] == "source_authentication"
    assert result["controller_actions"] == 0
    assert result["outcomes_opened"] == 0
    assert "/private" not in json.dumps(result, sort_keys=True)


def test_source_has_no_selector_publisher_controller_teacher_outcome_or_fitter() -> None:
    source = AUDITOR_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "CompletionFirstGoalTeacher",
        "CountingExecutor",
        "execute_living_dex",
        "fit_living_dex",
        "predict_living_dex",
        "publish_sealed_record",
        "select_living_dex",
        "write_root_claim",
        ".press(",
        ".tick(",
    ):
        assert forbidden not in source
