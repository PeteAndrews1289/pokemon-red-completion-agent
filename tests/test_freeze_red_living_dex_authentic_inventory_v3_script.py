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
from pokemon_red_completion.red_living_dex_exhaustive_inventory_diagnostics import (
    RedLivingDexExhaustiveInventoryExclusion,
    RedLivingDexExhaustiveInventoryReason,
    validate_red_living_dex_exhaustive_inventory_receipt,
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
    PROJECT_ROOT / "scripts/freeze_red_living_dex_authentic_inventory_v3.py"
)
SCRIPT = runpy.run_path(
    str(SCRIPT_PATH),
    run_name="freeze_red_living_dex_authentic_inventory_v3_test",
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _ready_state() -> object:
    state = SCRIPT["_DiagnosticState"]()
    state.authenticated_input_contexts = 12
    for name in (
        "contexts_considered",
        "materializer_namespaces_authenticated",
        "state_restore_attempts",
        "emulator_states_restored",
        "observation_attempts",
        "observations_completed",
        "binding_enumeration_attempts",
        "binding_enumerations_completed",
        "historical_replay_attempts",
        "historical_replays_authenticated",
        "scenario_projection_attempts",
        "complete_menus_projected",
        "zero_effect_checks",
    ):
        setattr(state, name, 12)
    state.coverage_evaluations = 1
    state.ready_coverage_plans = 1
    return state


def _projected(state: object | None = None) -> object:
    scenarios = _inventory_scenarios()
    coverage, plan = diagnose_red_living_dex_action_free_coverage(scenarios)
    assert plan is not None
    ready = _ready_state() if state is None else state
    ready.authenticated_input_contexts = 12
    for name in (
        "contexts_considered",
        "materializer_namespaces_authenticated",
        "state_restore_attempts",
        "emulator_states_restored",
        "observation_attempts",
        "observations_completed",
        "binding_enumeration_attempts",
        "binding_enumerations_completed",
        "historical_replay_attempts",
        "historical_replays_authenticated",
        "scenario_projection_attempts",
        "complete_menus_projected",
        "zero_effect_checks",
    ):
        setattr(ready, name, 12)
    ready.coverage_evaluations = 1
    ready.ready_coverage_plans = 1
    rows = {
        scenario.scenario_identity_sha256: {
            "attestation": {"schema": "synthetic-private-attestation-v3"},
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


def test_v3_parser_has_new_identity_and_no_execution_flags() -> None:
    parsed = SCRIPT["_parser"]().parse_args(_args())

    assert parsed.expected_source_commit == "a" * 40
    assert parsed.private_root == Path("/protected/artifacts")
    assert SCRIPT["PLAN_RECORD_ID"].endswith("-v3")
    assert SCRIPT["PLAN_SCHEMA"].endswith(".v3")
    assert not hasattr(parsed, "watch")
    assert not hasattr(parsed, "speed")
    with pytest.raises(SCRIPT["_ArgumentError"]):
        SCRIPT["_parser"]().parse_args(_args()[:-4])


def test_v3_runner_contains_no_selection_execution_or_learning_authority() -> None:
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
    assert "watch=False" in source
    assert "speed=None" in source


def test_source_failure_stops_before_private_input_and_is_path_free(
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
                RedLivingDexExhaustiveInventoryReason.SOURCE_AUTHENTICATION
            )
        ),
    )
    monkeypatch.setitem(globals_, "_authenticate_inputs", private)

    assert SCRIPT["main"](_args()) == 1
    result = json.loads(capsys.readouterr().out)
    validate_red_living_dex_exhaustive_inventory_receipt(result)
    assert private_calls == 0
    assert result["failure_reason"] == "source_authentication"
    assert result["protected_effect_total"] == 0
    assert "/protected" not in json.dumps(result)


@pytest.mark.parametrize(
    ("mode", "exclusion"),
    (
        (
            "restore",
            RedLivingDexExhaustiveInventoryExclusion.STATE_RESTORE_FAILURE,
        ),
        (
            "observe",
            RedLivingDexExhaustiveInventoryExclusion.STATE_OBSERVATION_FAILURE,
        ),
        (
            "enumerate",
            RedLivingDexExhaustiveInventoryExclusion.BINDING_ENUMERATION_FAILURE,
        ),
        (
            "history",
            RedLivingDexExhaustiveInventoryExclusion.HISTORICAL_REPLAY_FAILURE,
        ),
        (
            "projection",
            RedLivingDexExhaustiveInventoryExclusion.SCENARIO_PROJECTION_FAILURE,
        ),
        (
            "fewer",
            RedLivingDexExhaustiveInventoryExclusion.FEWER_THAN_THREE_MAPPED_OPTIONS,
        ),
        (
            "empty",
            RedLivingDexExhaustiveInventoryExclusion.EMPTY_PARTY_OBSERVATION,
        ),
    ),
)
def test_context_local_failure_is_finite_zero_effect_and_nonterminal(
    mode: str,
    exclusion: RedLivingDexExhaustiveInventoryExclusion,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = SCRIPT["_DiagnosticState"]()
    result = _run_project_context(mode, state, monkeypatch)

    assert result is None
    assert state.exclusions == {exclusion: 1}
    assert state.state_restore_attempts == 1
    assert state.zero_effect_checks == 1
    assert state.effects().total == 0


@pytest.mark.parametrize(
    "mode",
    ("fatal_restore", "fatal_observe", "fatal_history", "fatal_projection"),
)
def test_finite_global_stop_is_never_downgraded_to_a_local_exclusion(
    mode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = SCRIPT["_DiagnosticState"]()

    with pytest.raises(SCRIPT["_InventoryStop"]) as captured:
        _run_project_context(mode, state, monkeypatch)

    assert captured.value.reason is (
        RedLivingDexExhaustiveInventoryReason.PRIVATE_INPUT_AUTHENTICATION
    )
    assert sum(state.exclusions.values()) == 0
    assert state.zero_effect_checks == 1


def test_context_local_failure_does_not_abort_the_next_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = SCRIPT["_DiagnosticState"]()

    assert _run_project_context("observe", state, monkeypatch) is None
    projected = _run_project_context("success", state, monkeypatch)

    assert projected is not None
    assert state.exclusions[
        RedLivingDexExhaustiveInventoryExclusion.STATE_OBSERVATION_FAILURE
    ] == 1
    assert state.state_restore_attempts == 2
    assert state.complete_menus_projected == 1
    assert state.zero_effect_checks == 2
    assert state.effects().total == 0


def test_base_interruption_is_not_downgraded_to_a_context_exclusion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = SCRIPT["_DiagnosticState"]()

    with pytest.raises(SCRIPT["_InventoryStop"]) as captured:
        _run_project_context("interrupt", state, monkeypatch)

    assert captured.value.reason is (
        RedLivingDexExhaustiveInventoryReason.UNEXPECTED_FAILURE
    )
    assert sum(state.exclusions.values()) == 0
    assert state.zero_effect_checks == 1


def test_base_interruption_cannot_hide_a_frame_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = SCRIPT["_DiagnosticState"]()

    with pytest.raises(SCRIPT["_InventoryStop"]) as captured:
        _run_project_context("interrupt_effect", state, monkeypatch)

    assert captured.value.reason is (
        RedLivingDexExhaustiveInventoryReason.ZERO_EFFECT_AUTHENTICATION
    )
    assert state.emulator_frames_advanced == 1
    assert sum(state.exclusions.values()) == 0


@pytest.mark.parametrize("mode", ("frame_effect", "authority_attempt"))
def test_protected_effect_remains_global_and_cannot_be_an_exclusion(
    mode: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = SCRIPT["_DiagnosticState"]()

    with pytest.raises(SCRIPT["_InventoryStop"]) as captured:
        _run_project_context(mode, state, monkeypatch)

    assert captured.value.reason is (
        RedLivingDexExhaustiveInventoryReason.ZERO_EFFECT_AUTHENTICATION
    )
    assert state.effects().total > 0
    assert sum(state.exclusions.values()) == 0


def test_inventory_visits_every_context_after_local_exclusions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _capture(1200)
    profile = _profile(capture.capture_id)
    contexts = tuple(
        SimpleNamespace(
            assignment=SimpleNamespace(
                assignment_id=f"assignment-{index}",
                partition="train",
                slot_id=f"slot-{index}",
            ),
            catalog_entry=SimpleNamespace(context_id=f"context-{index}"),
            capture=capture,
            profile=profile,
            root_available=True,
            root_consumption_sha256=_sha(f"root-{index}"),
        )
        for index in range(3)
    )
    state = SCRIPT["_DiagnosticState"](authenticated_input_contexts=3)
    visits = 0

    class FakeStore:
        def inspect_episode_state(self, _episode_id: str) -> object:
            return SimpleNamespace(status="absent")

    def project(**kwargs: object) -> None:
        nonlocal visits
        visits += 1
        observed = kwargs["state"]
        observed.state_restore_attempts += 1
        observed.emulator_states_restored += 1
        observed.observation_attempts += 1
        observed.zero_effect_checks += 1
        observed.exclusions[
            RedLivingDexExhaustiveInventoryExclusion.STATE_OBSERVATION_FAILURE
        ] += 1
        return None

    globals_ = SCRIPT["_inventory"].__globals__
    monkeypatch.setitem(globals_, "build_runtime_identity", lambda: object())
    monkeypatch.setitem(globals_, "require_pyboy_import_origins", lambda _value: None)
    monkeypatch.setitem(
        globals_, "open_private_root", lambda *_args, **_kwargs: FakeStore()
    )
    monkeypatch.setitem(globals_, "_project_context", project)

    with pytest.raises(SCRIPT["_InventoryStop"]) as captured:
        SCRIPT["_inventory"](
            SimpleNamespace(private_root=Path("/protected/private")),
            rom_path=Path("/protected/red.gb"),
            contexts=contexts,
            source_bundle=_sha("source"),
            state=state,
        )

    assert captured.value.reason is RedLivingDexExhaustiveInventoryReason.EXACT_COVERAGE
    assert captured.value.coverage is not None
    assert captured.value.coverage.scenario_count == 0
    assert visits == 3
    assert state.contexts_considered == 3
    assert state.exclusions[
        RedLivingDexExhaustiveInventoryExclusion.STATE_OBSERVATION_FAILURE
    ] == 3
    receipt = SCRIPT["_diagnostic_receipt"](
        state,
        captured.value.reason,
        coverage=captured.value.coverage,
    )
    validate_red_living_dex_exhaustive_inventory_receipt(receipt)


def test_inventory_accounting_mismatch_stops_before_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _capture(1300)
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
            return SimpleNamespace(status="absent")

    globals_ = SCRIPT["_inventory"].__globals__
    monkeypatch.setitem(globals_, "build_runtime_identity", lambda: object())
    monkeypatch.setitem(globals_, "require_pyboy_import_origins", lambda _value: None)
    monkeypatch.setitem(
        globals_, "open_private_root", lambda *_args, **_kwargs: FakeStore()
    )
    monkeypatch.setitem(globals_, "_project_context", lambda **_kwargs: None)

    with pytest.raises(SCRIPT["_InventoryStop"]) as captured:
        SCRIPT["_inventory"](
            SimpleNamespace(private_root=Path("/protected/private")),
            rom_path=Path("/protected/red.gb"),
            contexts=(context,),
            source_bundle=_sha("source"),
            state=state,
        )

    assert captured.value.reason is (
        RedLivingDexExhaustiveInventoryReason.EXHAUSTIVE_ACCOUNTING
    )
    assert state.coverage_evaluations == 0


def test_forbidden_controller_authority_is_counted_not_falsely_zero() -> None:
    state = SCRIPT["_DiagnosticState"]()
    port = SCRIPT["_ForbiddenActionPort"](state)

    with pytest.raises(SCRIPT["_InventoryStop"]):
        port.execute(object())

    receipt = SCRIPT["_diagnostic_receipt"](
        state,
        RedLivingDexExhaustiveInventoryReason.ZERO_EFFECT_AUTHENTICATION,
        coverage=None,
    )
    assert receipt["effects"]["controller_authority_attempts"] == 1
    assert receipt["effects_verified_zero"] is False


def test_success_path_publishes_only_after_exhaustive_ready_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    published = {
        "schema": SCRIPT["RESULT_SCHEMA"],
        "status": "authenticated_action_free_exhaustive_8_plus_4_plan_frozen",
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
        globals_, "_inventory", lambda *_args, **kwargs: _projected(kwargs["state"])
    )
    monkeypatch.setitem(
        globals_,
        "_private_plan_document",
        lambda **_kwargs: ({"schema": "private-plan-v3"}, _sha("private-plan")),
    )
    monkeypatch.setitem(
        globals_, "_require_protected_input_integrity", lambda **_kwargs: None
    )
    monkeypatch.setitem(globals_, "_publish", lambda *_args, **_kwargs: published)

    assert SCRIPT["main"](_args()) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == published["status"]
    validate_red_living_dex_exhaustive_inventory_receipt(result["diagnostic"])
    assert result["diagnostic"]["aggregate_counts"][
        "private_plan_records_confirmed"
    ] == 1


def test_v3_private_plan_and_publication_are_exact_and_idempotent(
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
    assert document["schema"].endswith(".v3")
    assert document["private_plan_sha256"] == digest
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
    assert first["schema"].endswith(".v3")
    assert first["private_path_fields"] == 0
    with pytest.raises(PrivateArtifactError):
        SCRIPT["_publish"](
            args,
            document={**document, "status": "changed"},
            private_plan_sha256=digest,
            projected=projected,
        )


def _run_project_context(
    mode: str,
    state: object,
    monkeypatch: pytest.MonkeyPatch,
) -> object:
    capture = _capture(900)
    profile = _profile(capture.capture_id)

    class FakeEmulator:
        frame_count = 0
        pressed_buttons: tuple[object, ...] = ()

        def __enter__(self) -> FakeEmulator:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def load_state_bytes(self, _state: bytes) -> None:
            if mode == "restore":
                raise RuntimeError("private restore")
            if mode == "fatal_restore":
                raise SCRIPT["_InventoryStop"](
                    RedLivingDexExhaustiveInventoryReason.PRIVATE_INPUT_AUTHENTICATION
                )

    observation = SimpleNamespace(
        party=SimpleNamespace(
            members=() if mode == "empty" else (SimpleNamespace(),)
        ),
    )

    def runtime(*, profile: object, **_kwargs: object) -> object:
        def observe() -> object:
            if mode in {"interrupt", "interrupt_effect"}:
                if mode == "interrupt_effect":
                    emulator.frame_count += 1
                raise KeyboardInterrupt
            if mode == "fatal_observe":
                raise SCRIPT["_InventoryStop"](
                    RedLivingDexExhaustiveInventoryReason.PRIVATE_INPUT_AUTHENTICATION
                )
            if mode in {"observe", "frame_effect"}:
                if mode == "frame_effect":
                    emulator.frame_count += 1
                raise RuntimeError("private observation")
            return observation

        def enumerate_bindings(actions: object) -> object:
            if mode == "authority_attempt":
                actions.execute(object())
            if mode == "enumerate":
                raise RuntimeError("private enumeration")
            bindings = _bindings(profile)
            if mode == "fewer":
                return SimpleNamespace(bindings=bindings.bindings[:2])
            return bindings

        return SimpleNamespace(
            adapter=SimpleNamespace(observe=observe),
            enumerator=lambda actions: SimpleNamespace(
                enumerate=lambda _observation: enumerate_bindings(actions)
            ),
        )

    emulator = FakeEmulator()

    def before(capture: object, *_args: object, **_kwargs: object) -> object:
        return _snapshot(
            scenario=SCRIPT["red_living_dex_verified_capture_scenario_identity"](
                capture
            ),
            actions=0,
            frames=0,
            resource_pool_units=(("red.resource.capture-items", 10),),
        )

    globals_ = SCRIPT["_project_context"].__globals__
    monkeypatch.setitem(globals_, "PyBoyAdapter", lambda *_args, **_kwargs: emulator)
    monkeypatch.setitem(globals_, "require_pyboy_import_origins", lambda _value: None)
    monkeypatch.setitem(
        SCRIPT["_V2_SUPPORT"]["_V1_SUPPORT"],
        "PokemonRedStateReader",
        lambda _emulator: object(),
    )
    monkeypatch.setitem(globals_, "build_red_goal_context_runtime", runtime)
    monkeypatch.setitem(
        globals_,
        "_authenticate_historical_menu",
        (
            lambda *_args: (
                (_ for _ in ()).throw(RuntimeError("private history"))
                if mode == "history"
                else (_ for _ in ()).throw(
                    SCRIPT["_InventoryStop"](
                        RedLivingDexExhaustiveInventoryReason.PRIVATE_INPUT_AUTHENTICATION
                    )
                )
                if mode == "fatal_history"
                else None
            )
        ),
    )
    monkeypatch.setitem(globals_, "_before_snapshot", before)
    monkeypatch.setitem(globals_, "_context_facts", lambda *_args: _facts())
    monkeypatch.setitem(globals_, "_location_ref", lambda _observation: "red.start-map.1")
    if mode in {"projection", "fatal_projection"}:
        def fail_projection(*_args: object, **_kwargs: object) -> object:
            if mode == "projection":
                raise RuntimeError("private projection")
            raise SCRIPT["_InventoryStop"](
                RedLivingDexExhaustiveInventoryReason.PRIVATE_INPUT_AUTHENTICATION
            )

        monkeypatch.setitem(
            globals_,
            "build_verified_red_living_dex_goal_scenario",
            fail_projection,
        )

    return SCRIPT["_project_context"](
        assignment=SimpleNamespace(
            assignment_id="assignment",
            partition="train",
            slot_id="slot",
        ),
        budgets=SCRIPT["RedLivingDexScenarioBudgets"](5_000, 4_000_000),
        capture=capture,
        catalog_entry=SimpleNamespace(context_id="context"),
        physical_root_sha256=_sha("root"),
        profile=profile,
        rom_path=Path("/protected/red.gb"),
        runtime_identity=SimpleNamespace(),
        source_bundle=_sha("source"),
        state=state,
    )
