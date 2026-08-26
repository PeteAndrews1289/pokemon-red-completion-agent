# ruff: noqa: E402 -- standalone runner is loaded after its script-local imports.

from __future__ import annotations

import hashlib
import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_freeze_red_living_dex_authentic_inventory_script import _args
from test_red_living_dex_option_adapter import _facts, _snapshot
from test_red_living_dex_option_inventory import (
    _bindings,
    _capture,
    _inventory_scenarios,
    _profile,
)

from pokemon_red_completion.private_artifacts import (
    PrivateArtifactError,
    initialize_private_root,
)
from pokemon_red_completion.red_living_dex_inventory_diagnostics import (
    RedLivingDexInventoryDiagnosticReason,
    RedLivingDexInventoryExclusion,
    validate_red_living_dex_inventory_diagnostic_receipt,
)
from pokemon_red_completion.red_living_dex_option_inventory import (
    RedLivingDexActionFreeInventory,
    diagnose_red_living_dex_action_free_coverage,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

SCRIPT_PATH = (
    PROJECT_ROOT / "scripts/freeze_red_living_dex_authentic_inventory_v2.py"
)
SCRIPT = runpy.run_path(
    str(SCRIPT_PATH),
    run_name="freeze_red_living_dex_authentic_inventory_v2_test",
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _ready_state() -> object:
    state = SCRIPT["_DiagnosticState"]()
    state.authenticated_input_contexts = 12
    state.contexts_considered = 12
    state.materializer_namespaces_authenticated = 12
    state.emulator_states_read = 12
    state.historical_replays_authenticated = 12
    state.scenario_projection_attempts = 12
    state.complete_menus_projected = 12
    state.zero_effect_checks = 12
    state.coverage_evaluations = 1
    state.ready_coverage_plans = 1
    return state


def _projected(state: object | None = None) -> object:
    scenarios = _inventory_scenarios()
    coverage, plan = diagnose_red_living_dex_action_free_coverage(scenarios)
    assert plan is not None
    ready = _ready_state() if state is None else state
    for name in (
        "authenticated_input_contexts",
        "contexts_considered",
        "materializer_namespaces_authenticated",
        "emulator_states_read",
        "historical_replays_authenticated",
        "scenario_projection_attempts",
        "complete_menus_projected",
        "zero_effect_checks",
        "coverage_evaluations",
        "ready_coverage_plans",
    ):
        setattr(
            ready,
            name,
            1 if name in {"coverage_evaluations", "ready_coverage_plans"} else 12,
        )
    rows = {
        scenario.scenario_identity_sha256: {
            "attestation": {"schema": "synthetic-private-attestation-v2"},
            "materialization_identity": scenario.private_identity_dict(),
            "partition": scenario.partition,
        }
        for scenario in plan.scenarios
    }
    return SCRIPT["_ProjectedInventory"](
        RedLivingDexActionFreeInventory(scenarios),
        plan,
        rows,
        coverage,
        ready,
    )


def test_v2_parser_has_new_identity_and_no_execution_flags() -> None:
    parsed = SCRIPT["_parser"]().parse_args(_args())

    assert parsed.expected_source_commit == "a" * 40
    assert parsed.private_root == Path("/protected/artifacts")
    assert SCRIPT["PLAN_RECORD_ID"].endswith("-v2")
    assert SCRIPT["PLAN_SCHEMA"].endswith(".v2")
    assert not hasattr(parsed, "watch")
    assert not hasattr(parsed, "speed")
    with pytest.raises(SCRIPT["_ArgumentError"]):
        SCRIPT["_parser"]().parse_args(_args()[:-4])


def test_v2_runner_contains_no_selection_execution_or_learning_authority() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    for forbidden in (
        "issue_red_living_dex_behavior_commitment",
        "run_red_living_dex_materialization_plan",
        "score_red_living_dex",
        "CompletionFirstGoalTeacher",
        "write_root_claim",
        ".press(",
        ".tick(",
    ):
        assert forbidden not in source
    assert "_ForbiddenActionPort" in source
    assert "RedLivingDexInventoryEffects" in source


def test_source_failure_stops_before_private_input_and_is_exact_path_free(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_calls = 0

    def private(*_args: object, **_kwargs: object) -> object:
        nonlocal private_calls
        private_calls += 1
        raise AssertionError("private input opened")

    globals_ = SCRIPT["main"].__globals__
    monkeypatch.setitem(
        globals_,
        "_authenticate_source",
        lambda _args: (_ for _ in ()).throw(
            SCRIPT["_InventoryStop"](
                RedLivingDexInventoryDiagnosticReason.SOURCE_AUTHENTICATION
            )
        ),
    )
    monkeypatch.setitem(globals_, "_authenticate_inputs", private)

    assert SCRIPT["main"](_args()) == 1

    result = json.loads(capsys.readouterr().out)
    validate_red_living_dex_inventory_diagnostic_receipt(result)
    assert private_calls == 0
    assert result["failure_reason"] == "source_authentication"
    assert result["aggregate_counts"]["authenticated_input_contexts"] == 0
    assert result["effects_verified_zero"] is True
    assert "/protected" not in json.dumps(result)


@pytest.mark.parametrize(
    "reason",
    (
        RedLivingDexInventoryDiagnosticReason.RUNTIME_AUTHENTICATION,
        RedLivingDexInventoryDiagnosticReason.MATERIALIZER_NAMESPACE_AUTHENTICATION,
        RedLivingDexInventoryDiagnosticReason.STATE_OBSERVATION,
        RedLivingDexInventoryDiagnosticReason.HISTORICAL_REPLAY,
        RedLivingDexInventoryDiagnosticReason.SCENARIO_PROJECTION,
        RedLivingDexInventoryDiagnosticReason.UNEXPECTED_FAILURE,
    ),
)
def test_private_stage_stop_retains_finite_reason(
    reason: RedLivingDexInventoryDiagnosticReason,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    globals_ = SCRIPT["main"].__globals__
    monkeypatch.setitem(
        globals_, "_authenticate_source", lambda _args: ("a" * 40, _sha("source"))
    )
    monkeypatch.setitem(
        globals_,
        "_authenticate_inputs",
        lambda *_args: (
            Path("/protected/red.gb"),
            _sha("rom"),
            b"rom",
            tuple(object() for _ in range(12)),
            _sha("catalog"),
            _sha("plan"),
        ),
    )
    monkeypatch.setitem(
        globals_,
        "_inventory",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            SCRIPT["_InventoryStop"](reason)
        ),
    )

    assert SCRIPT["main"](_args()) == 1

    result = json.loads(capsys.readouterr().out)
    validate_red_living_dex_inventory_diagnostic_receipt(result)
    assert result["failure_reason"] == reason.value
    assert result["aggregate_counts"]["authenticated_input_contexts"] == 12


def test_exact_coverage_stop_publishes_the_bounded_shortfall(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    coverage, plan = diagnose_red_living_dex_action_free_coverage(
        _inventory_scenarios()[:-1]
    )
    assert plan is None
    globals_ = SCRIPT["main"].__globals__
    monkeypatch.setitem(
        globals_, "_authenticate_source", lambda _args: ("a" * 40, _sha("source"))
    )
    monkeypatch.setitem(
        globals_,
        "_authenticate_inputs",
        lambda *_args: (
            Path("/protected/red.gb"),
            _sha("rom"),
            b"rom",
            tuple(object() for _ in range(11)),
            _sha("catalog"),
            _sha("plan"),
        ),
    )

    def inventory(*_args: object, **kwargs: object) -> object:
        state = kwargs["state"]
        for name in (
            "contexts_considered",
            "materializer_namespaces_authenticated",
            "emulator_states_read",
            "historical_replays_authenticated",
            "scenario_projection_attempts",
            "zero_effect_checks",
        ):
            setattr(state, name, 11)
        state.complete_menus_projected = 11
        state.coverage_evaluations = 1
        raise SCRIPT["_InventoryStop"](
            RedLivingDexInventoryDiagnosticReason.EXACT_COVERAGE,
            coverage=coverage,
        )

    monkeypatch.setitem(globals_, "_inventory", inventory)

    assert SCRIPT["main"](_args()) == 1

    result = json.loads(capsys.readouterr().out)
    validate_red_living_dex_inventory_diagnostic_receipt(result)
    assert result["failure_reason"] == "exact_coverage"
    assert result["coverage"]["status"] == "insufficient_development_scenarios"
    assert result["coverage"]["scenario_count"] == 11


def test_forbidden_controller_authority_is_counted_not_reported_as_false_zero() -> None:
    state = SCRIPT["_DiagnosticState"]()
    port = SCRIPT["_ForbiddenActionPort"](state)

    with pytest.raises(SCRIPT["_InventoryStop"]):
        port.execute(object())

    receipt = SCRIPT["_diagnostic_receipt"](
        state,
        RedLivingDexInventoryDiagnosticReason.ZERO_EFFECT_AUTHENTICATION,
        coverage=None,
    )
    assert receipt["effects"]["controller_authority_attempts"] == 1
    assert receipt["effects_verified_zero"] is False
    assert receipt["protected_effect_total"] == 1


def test_effect_measurement_retains_actions_frames_and_pressed_buttons() -> None:
    state = SCRIPT["_DiagnosticState"]()
    emulator = SimpleNamespace(frame_count=9, pressed_buttons=("a",))
    actions = SimpleNamespace(actions_executed=2)

    SCRIPT["_record_context_effects"](state, emulator, actions, 5)

    assert state.controller_actions == 3
    assert state.emulator_frames_advanced == 4
    assert state.zero_effect_checks == 1
    with pytest.raises(SCRIPT["_InventoryStop"]):
        SCRIPT["_raise_if_effect"](state)


@pytest.mark.parametrize(
    ("mode", "expected"),
    (
        ("runtime", RedLivingDexInventoryDiagnosticReason.RUNTIME_AUTHENTICATION),
        (
            "namespace",
            RedLivingDexInventoryDiagnosticReason.MATERIALIZER_NAMESPACE_AUTHENTICATION,
        ),
        ("state", RedLivingDexInventoryDiagnosticReason.STATE_OBSERVATION),
        ("history", RedLivingDexInventoryDiagnosticReason.HISTORICAL_REPLAY),
        ("projection", RedLivingDexInventoryDiagnosticReason.SCENARIO_PROJECTION),
        (
            "frame_effect",
            RedLivingDexInventoryDiagnosticReason.ZERO_EFFECT_AUTHENTICATION,
        ),
        (
            "authority_attempt",
            RedLivingDexInventoryDiagnosticReason.ZERO_EFFECT_AUTHENTICATION,
        ),
        ("coverage", RedLivingDexInventoryDiagnosticReason.EXACT_COVERAGE),
    ),
)
def test_inventory_runtime_maps_each_real_stage_and_retains_partial_counts(
    mode: str,
    expected: RedLivingDexInventoryDiagnosticReason,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _capture(900)
    profile = _profile(capture.capture_id)
    context = SimpleNamespace(
        assignment=SimpleNamespace(
            assignment_id="assignment",
            partition="train",
            slot_id="slot",
        ),
        catalog_entry=SimpleNamespace(context_id="context"),
        capture=capture,
        profile=profile,
        root_available=True,
        root_consumption_sha256=_sha("root"),
    )
    state = SCRIPT["_DiagnosticState"](authenticated_input_contexts=1)

    class FakeStore:
        def inspect_episode_state(self, _episode_id: str) -> object:
            return SimpleNamespace(status="invalid" if mode == "namespace" else "absent")

    class FakeEmulator:
        frame_count = 0
        pressed_buttons: tuple[object, ...] = ()

        def __enter__(self) -> FakeEmulator:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def load_state_bytes(self, _state: bytes) -> None:
            if mode == "frame_effect":
                self.frame_count += 1

    observation = SimpleNamespace(
        party=SimpleNamespace(members=(SimpleNamespace(),)),
    )

    def runtime(*, profile: object, **_kwargs: object) -> object:
        def enumerate_bindings(actions: object) -> object:
            if mode == "authority_attempt":
                actions.execute(object())
            return _bindings(profile)

        return SimpleNamespace(
            adapter=SimpleNamespace(
                observe=(
                    lambda: (_ for _ in ()).throw(RuntimeError("private state"))
                    if mode == "state"
                    else observation
                )
            ),
            enumerator=lambda _actions: SimpleNamespace(
                enumerate=lambda _observation: enumerate_bindings(_actions)
            ),
        )

    def before(capture: object, *_args: object, **_kwargs: object) -> object:
        return _snapshot(
            scenario=SCRIPT["red_living_dex_verified_capture_scenario_identity"](
                capture
            ),
            actions=0,
            frames=0,
            resource_pool_units=(("red.resource.capture-items", 10),),
        )

    globals_ = SCRIPT["_inventory"].__globals__
    monkeypatch.setitem(
        globals_,
        "build_runtime_identity",
        (
            lambda: (_ for _ in ()).throw(RuntimeError("runtime"))
            if mode == "runtime"
            else object()
        ),
    )
    monkeypatch.setitem(globals_, "require_pyboy_import_origins", lambda _value: None)
    monkeypatch.setitem(globals_, "open_private_root", lambda *_args, **_kwargs: FakeStore())
    monkeypatch.setitem(globals_, "PyBoyAdapter", lambda *_args, **_kwargs: FakeEmulator())
    monkeypatch.setitem(
        SCRIPT["_V1_SUPPORT"], "PokemonRedStateReader", lambda _emulator: object()
    )
    monkeypatch.setitem(globals_, "build_red_goal_context_runtime", runtime)
    monkeypatch.setitem(
        globals_,
        "_authenticate_historical_menu",
        (
            lambda *_args: (_ for _ in ()).throw(RuntimeError("private history"))
            if mode == "history"
            else None
        ),
    )
    monkeypatch.setitem(globals_, "_before_snapshot", before)
    monkeypatch.setitem(globals_, "_context_facts", lambda *_args: _facts())
    monkeypatch.setitem(globals_, "_location_ref", lambda _observation: "red.start-map.1")
    if mode == "projection":
        monkeypatch.setitem(
            globals_,
            "build_verified_red_living_dex_goal_scenario",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("private projection")
            ),
        )

    with pytest.raises(SCRIPT["_InventoryStop"]) as captured:
        SCRIPT["_inventory"](
            SimpleNamespace(private_root=Path("/protected/private")),
            rom_path=Path("/protected/red.gb"),
            contexts=(context,),
            source_bundle=_sha("source"),
            state=state,
        )

    assert captured.value.reason is expected
    if mode == "coverage":
        assert captured.value.coverage is not None
        assert captured.value.coverage.status.value == "insufficient_train_scenarios"
        assert state.coverage_evaluations == 1
        assert state.complete_menus_projected == 1
    if mode == "history":
        assert state.emulator_states_read == 1
        assert state.historical_replays_authenticated == 0
    if mode == "projection":
        assert state.historical_replays_authenticated == 1
        assert state.scenario_projection_attempts == 1
        assert state.complete_menus_projected == 0
    if mode == "frame_effect":
        assert state.emulator_frames_advanced == 1
    if mode == "authority_attempt":
        assert state.controller_authority_attempts == 1


@pytest.mark.parametrize(
    ("stage", "expected"),
    (
        ("encoding", "private_plan_encoding"),
        ("integrity", "protected_input_integrity"),
        ("publication", "private_plan_publication"),
    ),
)
def test_postinventory_failures_retain_the_exact_stage(
    stage: str,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    globals_ = SCRIPT["main"].__globals__
    monkeypatch.setitem(
        globals_, "_authenticate_source", lambda _args: ("a" * 40, _sha("source"))
    )
    monkeypatch.setitem(
        globals_,
        "_authenticate_inputs",
        lambda *_args: (
            Path("/protected/red.gb"),
            _sha("rom"),
            b"rom",
            tuple(object() for _ in range(12)),
            _sha("catalog"),
            _sha("plan"),
        ),
    )
    monkeypatch.setitem(
        globals_,
        "_inventory",
        lambda *_args, **kwargs: _projected(kwargs["state"]),
    )

    def encode(**_kwargs: object) -> tuple[dict[str, object], str]:
        if stage == "encoding":
            raise RuntimeError("private-/Users/value")
        return {"schema": "private-plan-v2"}, _sha("private-plan")

    def integrity(**_kwargs: object) -> None:
        if stage == "integrity":
            raise RuntimeError("private-/Users/value")

    def publish(*_args: object, **_kwargs: object) -> object:
        if stage == "publication":
            raise RuntimeError("private-/Users/value")
        return {"status": "published"}

    monkeypatch.setitem(globals_, "_private_plan_document", encode)
    monkeypatch.setitem(globals_, "_require_protected_input_integrity", integrity)
    monkeypatch.setitem(globals_, "_publish", publish)

    assert SCRIPT["main"](_args()) == 1

    result = json.loads(capsys.readouterr().out)
    validate_red_living_dex_inventory_diagnostic_receipt(result)
    assert result["failure_reason"] == expected
    assert "/Users/" not in json.dumps(result)


def test_success_path_builds_and_publishes_only_after_ready_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    published = {
        "schema": SCRIPT["RESULT_SCHEMA"],
        "status": "authenticated_action_free_8_plus_4_plan_frozen",
    }
    globals_ = SCRIPT["main"].__globals__
    monkeypatch.setitem(
        globals_, "_authenticate_source", lambda _args: ("a" * 40, _sha("source"))
    )
    monkeypatch.setitem(
        globals_,
        "_authenticate_inputs",
        lambda *_args: (
            Path("/protected/red.gb"),
            _sha("rom"),
            b"rom",
            tuple(object() for _ in range(12)),
            _sha("catalog"),
            _sha("plan"),
        ),
    )
    monkeypatch.setitem(
        globals_,
        "_inventory",
        lambda *_args, **kwargs: _projected(kwargs["state"]),
    )
    monkeypatch.setitem(
        globals_,
        "_private_plan_document",
        lambda **_kwargs: ({"schema": "private-plan-v2"}, _sha("private-plan")),
    )
    monkeypatch.setitem(
        globals_, "_require_protected_input_integrity", lambda **_kwargs: None
    )
    monkeypatch.setitem(globals_, "_publish", lambda *_args, **_kwargs: published)

    assert SCRIPT["main"](_args()) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema"] == published["schema"]
    assert result["status"] == published["status"]
    validate_red_living_dex_inventory_diagnostic_receipt(result["diagnostic"])
    assert result["diagnostic"]["aggregate_counts"][
        "private_plan_records_confirmed"
    ] == 1


def test_v2_private_plan_and_publication_are_exact_and_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projected = _projected()
    document, digest = SCRIPT["_private_plan_document"](
        source_commit="a" * 40,
        source_bundle=_sha("source"),
        rom_sha256=_sha("rom"),
        registry_sha256=_sha("registry"),
        catalog_sha256=_sha("catalog"),
        context_plan_sha256=_sha("context-plan"),
        projected=projected,
    )
    assert document["schema"].endswith(".v2")
    assert document["private_plan_sha256"] == digest
    assert document["coverage_diagnostic"]["status"] == "ready"
    assert "/protected" not in json.dumps(document)

    repository = tmp_path / "repository"
    root = tmp_path / "private"
    repository.mkdir()
    root.mkdir()

    def device_id(path: Path) -> int:
        return 2 if path == root.resolve() else 1

    store = initialize_private_root(
        root,
        repository_root=repository,
        device_id=device_id,
        git_worktree_probe=lambda _path: False,
    )
    monkeypatch.setitem(
        SCRIPT["_publish"].__globals__,
        "open_private_root",
        lambda *_args, **_kwargs: store,
    )
    args = SimpleNamespace(private_root=root)
    first = SCRIPT["_publish"](
        args,
        document=document,
        private_plan_sha256=digest,
        projected=projected,
    )
    second = SCRIPT["_publish"](
        args,
        document=document,
        private_plan_sha256=digest,
        projected=projected,
    )

    assert first == second
    assert first["schema"].endswith(".v2")
    assert first["private_path_fields"] == 0
    changed = {**document, "status": "changed"}
    with pytest.raises(PrivateArtifactError):
        SCRIPT["_publish"](
            args,
            document=changed,
            private_plan_sha256=digest,
            projected=projected,
        )


@pytest.mark.parametrize("status", ("invalid", "unknown", ""))
def test_invalid_materializer_namespace_is_terminal(status: str) -> None:
    store = SimpleNamespace(
        inspect_episode_state=lambda _episode_id: SimpleNamespace(status=status)
    )

    with pytest.raises(SCRIPT["_InventoryStop"]) as captured:
        SCRIPT["_materializer_episode_is_unclaimed"](store, "redldx-context")

    assert captured.value.reason is (
        RedLivingDexInventoryDiagnosticReason.MATERIALIZER_NAMESPACE_AUTHENTICATION
    )


def test_exclusion_vocabulary_is_fixed_and_complete() -> None:
    state = SCRIPT["_DiagnosticState"]()
    receipt = SCRIPT["_diagnostic_receipt"](
        state,
        RedLivingDexInventoryDiagnosticReason.SOURCE_AUTHENTICATION,
        coverage=None,
    )

    assert set(receipt["exclusions"]) == {
        item.value for item in RedLivingDexInventoryExclusion
    }
    assert set(receipt["exclusions"].values()) == {0}
