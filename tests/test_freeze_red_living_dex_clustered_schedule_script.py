# ruff: noqa: E402 -- standalone scripts are loaded after their local path setup.

from __future__ import annotations

import hashlib
import json
import runpy
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_red_living_dex_clustered_schedule_plan import _bindings, _plan

from pokemon_red_completion.private_artifacts import initialize_private_root
from pokemon_red_completion.red_living_dex_clustered_schedule_plan import (
    RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_ID,
    RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_KIND,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

FREEZER_PATH = SCRIPTS_ROOT / "freeze_red_living_dex_clustered_schedule.py"
VALIDATOR_PATH = SCRIPTS_ROOT / "validate_red_living_dex_clustered_schedule.py"
FREEZER = runpy.run_path(
    str(FREEZER_PATH),
    run_name="freeze_red_living_dex_clustered_schedule_test",
)
VALIDATOR = runpy.run_path(
    str(VALIDATOR_PATH),
    run_name="validate_red_living_dex_clustered_schedule_test",
)
QUALIFICATION_PATH = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-living-dex-clustered-schedule-freezer-local-qualification-v1-2026-08-29.json"
)
QUALIFICATION_SHA256 = "873d2317755705637a9405cd3c82451592019d275ff0cab316df33d295351e4f"


def _args() -> list[str]:
    bindings = _bindings()
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


def test_freezer_parser_has_no_execution_or_arm_selection_flags() -> None:
    parsed = FREEZER["_parser"]().parse_args(_args())

    assert parsed.private_root == Path("/private/artifacts")
    for field in (
        "watch",
        "speed",
        "retry",
        "candidate_index",
        "fit",
        "execute",
        "output",
    ):
        assert not hasattr(parsed, field)


def test_freezer_reproduces_the_tracked_census_binding() -> None:
    FREEZER["_authenticate_census_receipt"]()

    assert FREEZER["EXPECTED_SCHEDULE_SHA256"] == (
        "35c00f382b5cd0f52b5231f0114eee7f423beb49c9fe4235ffe840fcc51dc905"
    )
    assert _plan().schedule.policy.policy_sha256 == FREEZER["EXPECTED_POLICY_SHA256"]


def test_local_qualification_receipt_is_bound_and_does_not_overclaim() -> None:
    payload = QUALIFICATION_PATH.read_bytes()
    receipt = json.loads(payload)

    assert hashlib.sha256(payload).hexdigest() == QUALIFICATION_SHA256
    assert receipt["status"] == "locally_qualified_publication_and_exact_ci_pending"
    assert receipt["implementation"]["expected_schedule_sha256"] == (
        FREEZER["EXPECTED_SCHEDULE_SHA256"]
    )
    assert receipt["implementation"]["expected_policy_sha256"] == (
        FREEZER["EXPECTED_POLICY_SHA256"]
    )
    assert receipt["publication"] == {
        "exact_candidate_commit": None,
        "exact_candidate_ci": None,
        "status": "pending",
    }
    assert "private_schedule_frozen" in receipt["claim_boundary"]["unsupported"]
    assert "learner_training_began" in receipt["claim_boundary"]["unsupported"]
    assert receipt["protected_effects"]["collection_authorized"] is False
    assert all(
        value == 0
        for key, value in receipt["protected_effects"].items()
        if key != "collection_authorized"
    )
    encoded = payload.decode("utf-8")
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    assert "Pokemon Roms" not in encoded


def test_selected_capabilities_join_back_to_exact_private_contexts() -> None:
    plan = _plan()
    capabilities = tuple(reversed(tuple(item.capability for item in plan.assignments)))
    selected = FREEZER["_selected_capabilities"](plan.schedule, capabilities)
    contexts_by_root = {
        item.capability.root.root.root_consumption_sha256: SimpleNamespace(
            root_consumption_sha256=(item.capability.root.root.root_consumption_sha256),
            context_identity_sha256=item.context_identity_sha256,
            root_available=True,
        )
        for item in plan.assignments
    }
    contexts = tuple(contexts_by_root.values())
    frozen = FREEZER["_frozen_assignments"](
        plan.schedule,
        selected,
        contexts,
    )

    assert tuple(item.private_dict() for item in frozen) == tuple(
        item.private_dict() for item in plan.assignments
    )


def test_freezer_publishes_and_reopens_one_immutable_plan(tmp_path: Path) -> None:
    store = _store(tmp_path)
    plan = _plan()

    result = FREEZER["_publish_and_reopen"](
        store,
        plan=plan,
        bindings=_bindings(),
        expected_schedule_sha256=plan.schedule.schedule_sha256,
        expected_policy_sha256=plan.schedule.policy.policy_sha256,
    )
    record = store.find_sealed_record(
        RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_ID,
        expected_kind=RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_KIND,
    )

    assert record is not None
    assert result["private_plan_reopened"] is True
    assert result["private_plan_sha256"] == plan.private_plan_sha256
    assert result["plan_manifest_sha256"] == record.summary.manifest_sha256
    assert result["train_scenarios"] == 8
    assert result["development_scenarios"] == 4
    encoded = json.dumps(result, sort_keys=True)
    assert all(item.context_identity_sha256 not in encoded for item in plan.assignments)
    assert str(tmp_path) not in encoded


def test_independent_validator_reopens_the_published_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = _store(tmp_path)
    plan = _plan()
    FREEZER["_publish_and_reopen"](
        store,
        plan=plan,
        bindings=_bindings(),
        expected_schedule_sha256=plan.schedule.schedule_sha256,
        expected_policy_sha256=plan.schedule.policy.policy_sha256,
    )
    record = store.find_sealed_record(
        RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_ID,
        expected_kind=RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_KIND,
    )
    assert record is not None
    bindings = _bindings()
    args = [
        "--private-root",
        "/private/artifacts",
        "--expected-private-plan-sha256",
        plan.private_plan_sha256,
        "--expected-plan-manifest-sha256",
        record.summary.manifest_sha256,
        "--expected-source-commit",
        bindings.source_commit,
        "--expected-source-bundle-sha256",
        bindings.source_bundle_sha256,
        "--expected-rom-sha256",
        bindings.rom_sha256,
        "--expected-goal-registry-sha256",
        bindings.goal_registry_sha256,
        "--expected-route-registry-sha256",
        bindings.route_registry_sha256,
        "--expected-context-catalog-sha256",
        bindings.context_catalog_sha256,
        "--expected-context-plan-sha256",
        bindings.context_plan_sha256,
        "--expected-runtime-identity-sha256",
        bindings.runtime_identity_sha256,
        "--expected-census-receipt-sha256",
        bindings.census_receipt_sha256,
    ]
    monkeypatch.setitem(
        VALIDATOR["main"].__globals__,
        "open_private_root",
        lambda *_args, **_kwargs: store,
    )
    monkeypatch.setitem(
        VALIDATOR["main"].__globals__,
        "EXPECTED_SCHEDULE_SHA256",
        plan.schedule.schedule_sha256,
    )
    monkeypatch.setitem(
        VALIDATOR["main"].__globals__,
        "EXPECTED_POLICY_SHA256",
        plan.schedule.policy.policy_sha256,
    )

    assert VALIDATOR["main"](args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "private_clustered_schedule_independently_validated"
    assert result["private_plan_reopened"] is True
    assert result["lineage_overlap"] == 0
    assert result["controller_actions"] == 0
    assert result["teacher_queries"] == 0
    assert str(tmp_path) not in json.dumps(result, sort_keys=True)


def test_main_rehearses_the_complete_zero_effect_freeze_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = _store(tmp_path)
    plan = _plan()
    bindings = _bindings()
    capabilities = tuple(item.capability for item in plan.assignments)
    roots_by_sha = {item.root.root.physical_root_sha256: item.root for item in capabilities}
    contexts_by_root = {
        item.capability.root.root.root_consumption_sha256: SimpleNamespace(
            root_consumption_sha256=(item.capability.root.root.root_consumption_sha256),
            context_identity_sha256=item.context_identity_sha256,
            root_available=True,
        )
        for item in plan.assignments
    }
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
                tuple(contexts_by_root.values()),
                bindings.context_catalog_sha256,
                bindings.context_plan_sha256,
            )
        if name == "_authenticate_supplemental_roots":
            return lambda *_args: ()
        if name == "_observe_candidates":
            return lambda *_args, **_kwargs: tuple(roots_by_sha.values())
        if name == "_observe_supplemental_candidates":
            return lambda *_args, **_kwargs: ()
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
        authenticated_supplemental_roots=0,
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
    monkeypatch.setitem(globals_, "_authenticate_census_receipt", lambda: None)
    monkeypatch.setitem(globals_, "_support", support)
    monkeypatch.setitem(
        globals_["_PROVIDER_SUPPORT"],
        "_DiagnosticState",
        lambda: state,
    )
    monkeypatch.setitem(globals_, "open_private_root", lambda *_args, **_kwargs: store)
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
    monkeypatch.setitem(
        globals_,
        "derive_red_living_dex_provider_corridors",
        lambda _world: (),
    )
    monkeypatch.setitem(
        globals_,
        "RedLivingDexSetupEffectMeter",
        lambda: SimpleNamespace(checkpoint=lambda: object()),
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
        "schedule_red_living_dex_clustered_integration",
        lambda _capabilities: plan.schedule,
    )
    monkeypatch.setitem(
        globals_,
        "EXPECTED_SCHEDULE_SHA256",
        plan.schedule.schedule_sha256,
    )
    monkeypatch.setitem(
        globals_,
        "EXPECTED_POLICY_SHA256",
        plan.schedule.policy.policy_sha256,
    )

    assert FREEZER["main"](_args()) == 0
    result = json.loads(capsys.readouterr().out)
    assert integrity_calls == 1
    assert result["status"] == "authenticated_action_free_clustered_schedule_frozen"
    assert result["private_plan_reopened"] is True
    assert result["train_scenarios"] == 8
    assert result["development_scenarios"] == 4
    assert result["controller_actions"] == 0
    assert result["outcomes_observed"] == 0
    assert "/private" not in json.dumps(result, sort_keys=True)


def test_failure_receipt_sanitizes_private_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setitem(
        FREEZER["main"].__globals__,
        "_authenticate_census_receipt",
        lambda: (_ for _ in ()).throw(RuntimeError("/private/secret.json")),
    )

    assert FREEZER["main"](_args()) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "failed_closed"
    assert result["stage"] == "census_evidence_authentication"
    assert result["controller_actions"] == 0
    assert result["outcomes_observed"] == 0
    assert "/private" not in json.dumps(result, sort_keys=True)


def test_freezer_and_validator_contain_no_controller_teacher_claim_or_fit_authority() -> None:
    for path in (FREEZER_PATH, VALIDATOR_PATH):
        source = path.read_text(encoding="utf-8")
        for forbidden in (
            "CountingExecutor",
            "write_root_claim",
            "CompletionFirstGoalTeacher",
            "issue_red_living_dex_behavior_commitment",
            ".press(",
            ".tick(",
            ".execute(",
            "model.fit(",
            "selected_candidate_index",
        ):
            assert forbidden not in source
