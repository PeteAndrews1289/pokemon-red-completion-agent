from __future__ import annotations

import argparse
import ast
import json
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    GoalManagerCompositionObservation,
    LivingCollectionCheckpoint,
)
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_paired_red_bounded_player.py"


@pytest.mark.parametrize("probe_during_observation", [False, True])
def test_live_skill_has_real_limits_without_bypassing_observation_gate_or_total(
    monkeypatch, probe_during_observation,
):
    module = runpy.run_path(str(SCRIPT))
    observe_type = module["_LiveObserver"]
    namespace = observe_type.__call__.__globals__
    hard_type = module["HardCompositionActionLimiter"]
    count_type = module["CountingExecutor"]
    calls, skill_ports = [], []
    outer = hard_type(
        SimpleNamespace(execute=lambda action: calls.append(action)),
        maximum_actions_per_decision=1, maximum_episode_actions=1,
    )
    meter = SimpleNamespace(
        checkpoint=lambda: outer.attempted_actions,
        begin_decision_window=outer.begin_decision_window,
    )

    def player(_runtime, actions, *_args, completion_dose=False):
        assert completion_dose is False
        assert isinstance(actions.delegate, hard_type)
        skill_ports.append(actions)

        class Bridge:
            last_live_observation = None

            def __call__(self):
                if probe_during_observation:
                    with pytest.raises(module["PairedRedBoundedPlayerRunError"]):
                        actions.execute("must-not-reach-game")
                return _observation(storage=9)

        return Bridge()

    monkeypatch.setitem(namespace, "_player_observer", player)
    observer = observe_type(
        runtime=object(), actions=count_type(outer), meter=meter,
        maximum_actions_per_decision=1,
    )
    if probe_during_observation:
        with pytest.raises(module["PairedRedBoundedPlayerRunError"], match="action_free"):
            observer()
        assert calls == []
        assert outer.attempted_actions == 0
    else:
        observer()
        skill_ports[-1].execute("first")
        observer()  # a new local guard must not reset the episode total
        from pokemon_red_completion.goal_manager_composition_qualification import (
            CompositionActionBudgetExhausted,
        )
        with pytest.raises(CompositionActionBudgetExhausted):
            skill_ports[-1].execute("over-budget")
        assert calls == ["first"]
        assert outer.attempted_actions == 1


def _call_names() -> tuple[str, ...]:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.append(node.func.attr)
    return tuple(names)


def _collection(*, storage: int) -> LivingCollectionCheckpoint:
    return LivingCollectionCheckpoint(
        registered_species=10,
        living_species=10,
        required_specimens_remaining=5,
        retained_captures=3,
        storage_headroom=storage,
        undeclared_specimen_losses=0,
        completion_contract_sha256="1" * 64,
        specimen_ledger_sha256="2" * 64,
        required_specimens_sha256="3" * 64,
        specimen_counts=(("pokemon:red:living:starter", 10),),
    )


def _observation(*, storage: int) -> GoalManagerCompositionObservation:
    opportunities = tuple(
        GoalOpportunity(
            binding_ref=f"private:red:{kind.value}",
            kind=kind,
            availability=GoalAvailability.UNAVAILABLE,
            unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
        )
        for kind in GoalKind
    )
    return GoalManagerCompositionObservation(
        semantic_state_sha256="4" * 64,
        situation=GoalSituation(
            story_pressure=0.1,
            collection_pressure=0.1,
            team_pressure=0.1,
            evolution_pressure=0.1,
            safety_pressure=0.1,
            resource_pressure=0.1,
            storage_pressure=0.1,
            recovery_pressure=0.1,
            exploration_pressure=0.1,
        ),
        binding_set=GoalBindingSet(opportunities, ()),
        collection=_collection(storage=storage),
    )


def test_runner_uses_shared_player_and_frame_safe_controller_boundary() -> None:
    calls = _call_names()

    for required in (
        "require_clean_source",
        "require_published_source",
        "preflight_red_bounded_player",
        "run_bounded_player_episode",
        "FrameSafeExecutor",
        "HardCompositionActionLimiter",
        "EpisodeTrajectorySink",
        "compare_paired_bounded_player_arms",
        "load_living_dex_goal_model_record",
        "load_multi_goal_calibration_model",
        "_write_exclusive",
    ):
        assert required in calls
    assert "press" not in calls
    assert "release" not in calls
    assert "save_state" not in calls
    assert "save_state_bytes" not in calls
    assert "capture_red_player_terminal" in calls
    assert "publish_red_player_checkpoint" in calls


@pytest.mark.parametrize("enabled", [False, True])
def test_checkpoint_is_opt_in_and_durable_before_emulator_closes(monkeypatch, enabled):
    from pokemon_red_completion.bounded_player_episode import (
        BoundedPlayerResult,
        BoundedPlayerStopReason,
    )

    module = runpy.run_path(str(SCRIPT))
    run_arm = module["_run_arm"]
    namespace = run_arm.__globals__
    order = []
    observation = _observation(storage=4)
    result = BoundedPlayerResult(
        module["CAUSAL_ARM_ID"], BoundedPlayerStopReason.DECISION_LIMIT, (), False,
    )

    class Emulator:
        def __enter__(self):
            order.append("open")
            return self

        def __exit__(self, *_args):
            order.append("close")

        def load_state_bytes(self, _state):
            order.append("restore")

    def append(stream, record, **kwargs):
        assert stream == "checkpoint" and record == {"captured": True}
        assert kwargs == {"durable": True}
        assert "close" not in order
        order.append("durable_state")

    def complete():
        assert "close" in order
        order.append("trajectory_complete")
        return SimpleNamespace(manifest_sha256="9" * 64)

    writer = SimpleNamespace(append=append, complete=complete, abort=lambda _reason: None)
    sink = SimpleNamespace(
        write_episode_header=lambda **_kwargs: None,
        record_event=lambda _event: None, finalize=lambda: None,
    )
    for name in (
        "WindowedFrameBudgetController", "PokemonRedStateReader",
        "build_red_goal_context_runtime", "FrameSafeExecutor", "HardCompositionActionLimiter",
        "CountingExecutor", "CompositionIndependentBudgetMeter", "ViewerGoalTrajectory",
    ):
        monkeypatch.setitem(namespace, name, lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setitem(namespace, "_LiveObserver", lambda **_kwargs: SimpleNamespace(
        starting_observation=observation,
    ))
    monkeypatch.setitem(namespace, "PyBoyAdapter", lambda *_args, **_kwargs: Emulator())
    monkeypatch.setitem(namespace, "EpisodeTrajectorySink", lambda *_args, **_kwargs: sink)
    monkeypatch.setitem(namespace, "RecordingExecutor", lambda **_kwargs: SimpleNamespace(
        next_step_index=0, recording_failures=(),
    ))
    monkeypatch.setitem(namespace, "PokemonRedObservationEncoder", SimpleNamespace(
        from_state_reader=lambda _reader: None,
    ))
    monkeypatch.setitem(namespace, "run_bounded_player_episode", lambda **_kwargs: result)
    monkeypatch.setitem(namespace, "build_red_goal_context_runtime", lambda **_kwargs:
        SimpleNamespace(adapter=SimpleNamespace(observe=lambda: SimpleNamespace(
            input_ready=True, raw=SimpleNamespace(battle_state=False),
        )))
    )
    monkeypatch.setitem(namespace, "CompositionIndependentBudgetMeter", lambda *_a, **_k:
        SimpleNamespace(checkpoint=lambda: (0, 0))
    )

    def capture(**kwargs):
        assert "close" not in order and kwargs["result"] is result
        assert kwargs["context_origin"] == "training"
        order.append("capture")
        return {"captured": True}

    def publish(_store, document):
        assert order[-1] == "trajectory_complete" and document == {"captured": True}
        order.append("publish")

    monkeypatch.setitem(namespace, "capture_red_player_terminal", capture)
    monkeypatch.setitem(namespace, "publish_red_player_checkpoint", publish)
    readiness = SimpleNamespace(
        pair_id="checkpoint-wire", decision_limit=4, context_origin="training",
        source_commit="1" * 40, source_bundle_sha256="2" * 64, rom_sha256="3" * 64,
        model_sha256="4" * 64, rom_path=Path("unused-rom"),
        capture=SimpleNamespace(
            state_sha256="5" * 64, envelope_sha256="6" * 64, state_bytes=b"authenticated",
        ),
        profile=SimpleNamespace(profile_sha256="7" * 64),
        private_root=SimpleNamespace(begin_episode=lambda _id: writer),
        challenger_arm_id=module["CAUSAL_ARM_ID"], continue_after_progress=True,
        routed_resource_goals=False, save_terminal_checkpoints=enabled,
        quote_resource_costs=False, training_plan=None, continuation=None, completion_dose=False,
    )
    arm = run_arm(readiness, arm_id=module["CAUSAL_ARM_ID"], authority=object())
    assert arm.episode is result
    assert order == (
        ["open", "restore", "capture", "durable_state", "close", "trajectory_complete", "publish"]
        if enabled else ["open", "restore", "close", "trajectory_complete"]
    )


def test_runner_help_names_the_repeatable_pair_inputs() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--pair-id" in result.stdout
    assert "--private-artifact-root" in result.stdout
    assert "--model" in result.stdout
    assert "--challenger" in result.stdout
    assert "--living-dex-model-record" in result.stdout
    assert "--expected-living-dex-model-sha256" in result.stdout
    assert "--calibration-model" in result.stdout
    assert "--calibration-fit-summary" in result.stdout
    assert "--expected-calibration-model-file-sha256" in result.stdout
    assert "--expected-calibration-summary-file-sha256" in result.stdout
    assert "--decision-limit" in result.stdout
    assert "--out" in result.stdout
    assert "--save-terminal-checkpoints" in result.stdout


def test_challenger_arguments_keep_legacy_and_causal_models_disjoint() -> None:
    module = runpy.run_path(str(SCRIPT))
    arguments = module["_challenger_arguments"]
    learned_id = module["LEARNED_ARM_ID"]
    causal_id = module["CAUSAL_ARM_ID"]
    legacy = Path("legacy.json")
    causal = Path("causal.json")

    common = {
        "calibration_model": None,
        "calibration_fit_summary": None,
        "expected_calibration_model_file_sha256": None,
        "expected_calibration_summary_file_sha256": None,
    }
    assert arguments(
        argparse.Namespace(
            challenger=learned_id,
            model=legacy,
            living_dex_model_record=None,
            expected_living_dex_model_sha256=None,
            **common,
        )
    ) == (legacy, None, None, None)
    assert arguments(
        argparse.Namespace(
            challenger=causal_id,
            model=None,
            living_dex_model_record=causal,
            expected_living_dex_model_sha256="a" * 64,
            **common,
        )
    ) == (causal, None, "a" * 64, None)
    with pytest.raises(RuntimeError, match="challenger_model_arguments"):
        arguments(
            argparse.Namespace(
                challenger=causal_id,
                model=legacy,
                living_dex_model_record=causal,
                expected_living_dex_model_sha256="a" * 64,
                **common,
            )
        )


def test_challenger_arguments_require_the_complete_calibration_bundle() -> None:
    module = runpy.run_path(str(SCRIPT))
    arguments = module["_challenger_arguments"]
    calibration_id = module["CALIBRATION_ARM_ID"]
    model = Path("calibration-model.json")
    summary = Path("calibration-summary.json")

    assert arguments(
        argparse.Namespace(
            challenger=calibration_id,
            model=None,
            living_dex_model_record=None,
            expected_living_dex_model_sha256=None,
            calibration_model=model,
            calibration_fit_summary=summary,
            expected_calibration_model_file_sha256="b" * 64,
            expected_calibration_summary_file_sha256="c" * 64,
        )
    ) == (model, summary, "b" * 64, "c" * 64)
    with pytest.raises(RuntimeError, match="challenger_model_arguments"):
        arguments(
            argparse.Namespace(
                challenger=calibration_id,
                model=None,
                living_dex_model_record=None,
                expected_living_dex_model_sha256=None,
                calibration_model=model,
                calibration_fit_summary=None,
                expected_calibration_model_file_sha256="b" * 64,
                expected_calibration_summary_file_sha256="c" * 64,
            )
        )


def test_episode_identity_distinguishes_both_learned_challengers() -> None:
    module = runpy.run_path(str(SCRIPT))
    episode_id = module["_episode_id"]

    assert episode_id("pair", module["LEARNED_ARM_ID"]) == "pair-learned"
    assert episode_id("pair", module["CAUSAL_ARM_ID"]) == "pair-causal"
    assert episode_id("pair", module["CALIBRATION_ARM_ID"]) == "pair-calibration"
    assert episode_id("pair", module["BASELINE_ARM_ID"]) == "pair-baseline"
    with pytest.raises(RuntimeError, match="arm_identity"):
        episode_id("pair", "unknown")


def test_policy_identity_never_labels_the_causal_challenger_as_baseline() -> None:
    module = runpy.run_path(str(SCRIPT))
    policy_id = module["_policy_id"]
    causal_id = module["CAUSAL_ARM_ID"]
    baseline_id = module["BASELINE_ARM_ID"]
    readiness = SimpleNamespace(
        challenger_arm_id=causal_id,
        model_sha256="b" * 64,
        quote_resource_costs=False, training_plan=None, continuation=None, completion_dose=False,
    )

    assert policy_id(readiness, causal_id) == "living-dex-goal-bbbbbbbbbbbbbbbb"
    assert policy_id(readiness, baseline_id) == baseline_id
    readiness.quote_resource_costs = True
    assert policy_id(readiness, causal_id) == "living-dex-goal-bbbbbbbbbbbbbbbb-economics-v1"


def test_one_to_four_decisions_scale_episode_budgets_and_replans() -> None:
    module = runpy.run_path(str(SCRIPT))
    limits = module["_player_limits"](1)

    assert limits.max_decisions == 1
    assert limits.max_replans == 0
    assert limits.max_total_actions == limits.max_actions_per_decision == 6_000
    assert limits.max_total_frames == limits.max_frames_per_decision == 600_000
    four = module["_player_limits"](4)
    assert four.max_decisions == 4
    assert four.max_replans == 3
    assert four.max_total_actions == 24_000
    assert four.max_total_frames == 2_400_000
    with pytest.raises(RuntimeError, match="decision_limit"):
        module["_player_limits"](5)


def test_progress_predicate_uses_a_fresh_verified_collection_delta() -> None:
    module = runpy.run_path(str(SCRIPT))
    predicate = module["_ProgressPredicate"]()

    assert predicate(_observation(storage=2)) is False
    assert predicate(_observation(storage=2)) is False
    assert predicate(_observation(storage=3)) is True


@pytest.mark.parametrize("continue_chain,expected", [(False, 2), (True, 3)])
def test_declared_chain_keeps_playing_after_progress_without_changing_default(
    continue_chain: bool,
    expected: int,
) -> None:
    from test_bounded_player_episode import _CountingAuthority, _observer, _trajectory

    from pokemon_red_completion.bounded_player_episode import (
        BoundedPlayerLimits,
        run_bounded_player_episode,
    )

    module = runpy.run_path(str(SCRIPT))
    readiness = SimpleNamespace(
        challenger_arm_id=module["CAUSAL_ARM_ID"],
        continue_after_progress=continue_chain,
    )
    observe, meter, state = _observer(fail_first=False)
    trajectory, _sink = _trajectory()
    authority = _CountingAuthority()
    result = run_bounded_player_episode(
        observe=observe,
        authority=authority,
        authority_id="synthetic-chain-check",
        trajectory=trajectory,
        budget_meter=meter,
        completion_satisfied=module["_completion_predicate"](readiness),
        limits=BoundedPlayerLimits(max_decisions=3, max_replans=2),
    )
    assert len(result.steps) == authority.calls == expected
    assert state["observations"] == expected + 1
    assert state["actions"] == expected * 5
    assert all(step.semantic_state_changed for step in result.steps)


def test_calibration_rehearsal_stops_only_on_living_dex_completion() -> None:
    module = runpy.run_path(str(SCRIPT))
    predicate = module["_LivingDexCompletionPredicate"]()

    assert predicate(_observation(storage=2)) is False
    complete = _observation(storage=2)
    complete = GoalManagerCompositionObservation(
        semantic_state_sha256=complete.semantic_state_sha256,
        situation=complete.situation,
        binding_set=complete.binding_set,
        collection=LivingCollectionCheckpoint(
            registered_species=151,
            living_species=151,
            required_specimens_remaining=0,
            retained_captures=151,
            storage_headroom=1,
            undeclared_specimen_losses=0,
            completion_contract_sha256="1" * 64,
            specimen_ledger_sha256="2" * 64,
            required_specimens_sha256="3" * 64,
            specimen_counts=(("pokemon:red:living:starter", 151),),
        ),
    )
    assert predicate(complete) is True


def test_read_only_meter_rejects_a_regressing_frame_counter() -> None:
    module = runpy.run_path(str(SCRIPT))
    meter_type = module["_ReadOnlyBudgetMeter"]

    class Actions:
        actions_executed = 0

    class Emulator:
        frame_count = 9

    meter = meter_type(Actions(), Emulator(), 10)
    with pytest.raises(RuntimeError, match="frame_counter_regressed"):
        meter.checkpoint()


def test_deferred_executor_refuses_observation_time_input_then_enables() -> None:
    module = runpy.run_path(str(SCRIPT))
    deferred_type = module["_DeferredActionExecutor"]

    class Delegate:
        def execute(self, action: object) -> object:
            return action

    deferred = deferred_type(Delegate())
    with pytest.raises(RuntimeError, match="action_free_observation"):
        deferred.execute("move")
    assert deferred.attempted_while_disabled == 1
    deferred.enable()
    assert deferred.execute("move") == "move"


def test_public_output_must_be_new_external_and_not_rom_adjacent(tmp_path: Path) -> None:
    module = runpy.run_path(str(SCRIPT))
    output = module["_new_external_output"]
    rom_dir = tmp_path / "roms"
    result_dir = tmp_path / "results"
    rom_dir.mkdir()
    result_dir.mkdir()
    rom = rom_dir / "red.gb"
    rom.write_bytes(b"rom")

    assert output(result_dir / "pair.json", rom_path=rom) == (result_dir / "pair.json").resolve()
    with pytest.raises(RuntimeError, match="output_isolation"):
        output(rom_dir / "pair.json", rom_path=rom)
    existing = result_dir / "existing.json"
    existing.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="output_isolation"):
        output(existing, rom_path=rom)


@pytest.mark.parametrize("with_sink", (False, True))
def test_failed_arm_retains_a_path_safe_private_cause(tmp_path: Path, with_sink: bool) -> None:
    module = runpy.run_path(str(SCRIPT))
    documents = []
    aborted = []
    finalized = []
    writer = SimpleNamespace(
        append=lambda _name, value, **_kwargs: documents.append(value),
        abort=lambda reason: aborted.append(reason),
    )
    sink = SimpleNamespace(
        record_event=lambda event: documents.append(event.payload),
        finalize=lambda: finalized.append(True),
    )
    private_path = str(tmp_path / "unpublished-capture")
    try:
        raise RuntimeError(f"capture unavailable: {private_path}")
    except RuntimeError as error:
        module["_retain_failure"](
            writer,
            sink=sink if with_sink else None,
            recorder=SimpleNamespace(next_step_index=7),
            episode_id="bounded-diagnostic",
            error=error,
        )
    assert aborted == ["paired_arm_failed"]
    assert finalized == ([True] if with_sink else [])
    assert len(documents) == 1
    document = documents[0]
    assert document["failure_class"] == "bounded_player_failure"
    diagnostic = document["private_diagnostic"]
    assert diagnostic["exception_type"] == "RuntimeError"
    assert diagnostic["frames"][-1]["function"] == (
        "test_failed_arm_retains_a_path_safe_private_cause"
    )
    assert diagnostic["message_sha256"]
    assert private_path not in json.dumps(document, default=dict)


def test_routed_mode_uses_the_same_observer_hook_instead_of_local_only(monkeypatch):
    module = runpy.run_path(str(SCRIPT))
    factory = module["_player_observer"]
    sentinel = object()
    router = SimpleNamespace(enumerate=lambda _live: sentinel)
    received = []
    def build_router(*args, **kwargs):
        received.append(kwargs)
        return router
    monkeypatch.setitem(factory.__globals__, "RedResourceGoalRouter", build_router)
    monkeypatch.setitem(
        factory.__globals__, "RedBoundedPlayerObserver", lambda **kwargs: kwargs,
    )
    local = factory(object(), object(), None)
    routed = factory(SimpleNamespace(profile=SimpleNamespace(providers=())), object(), object())
    assert local["enumerate_bindings"] is None
    assert routed["enumerate_bindings"](object()) is sentinel
    factory(SimpleNamespace(profile=SimpleNamespace(providers=())), object(), object(), True)
    assert received == [{"quote_resource_costs": False}, {"quote_resource_costs": True}]


def test_routing_world_rejects_changed_cartridge_before_decode(monkeypatch, tmp_path):
    module = runpy.run_path(str(SCRIPT))
    factory = module["_route_world"]
    decoded = []
    path = tmp_path / "synthetic.gb"
    path.write_bytes(b"synthetic")
    monkeypatch.setitem(
        factory.__globals__, "StrategicScenarioRouteWorld",
        SimpleNamespace(from_rom=decoded.append),
    )
    with pytest.raises(module["PairedRedBoundedPlayerRunError"], match="cartridge_identity"):
        factory(SimpleNamespace(routed_resource_goals=True, rom_path=path, rom_sha256="0" * 64))
    assert not decoded
    assert factory(SimpleNamespace(routed_resource_goals=False)) is None


@pytest.mark.parametrize("origin", ("training", "development", "unspecified"))
def test_input_provenance_never_becomes_an_independence_claim(origin: str) -> None:
    module = runpy.run_path(str(SCRIPT))
    scope = module["_context_scope"](SimpleNamespace(context_origin=origin, training_plan=None))
    assert scope == {
        "context_origin": origin,
        "evidence_scope": (
            "training_context_integration_only"
            if origin == "training"
            else "descriptive_development_only"
        ),
        "independent_generalization_claim": False,
    }


def test_live_arm_wires_private_component_failure_before_recovery(monkeypatch) -> None:
    module = runpy.run_path(str(SCRIPT))
    run_arm = module["_run_arm"]
    namespace = run_arm.__globals__
    events = []
    headers = []
    aborted = []
    writer = SimpleNamespace(abort=aborted.append)
    sink = SimpleNamespace(
        write_episode_header=lambda **kwargs: headers.append(kwargs),
        record_event=events.append,
        finalize=lambda: None,
    )

    class Emulator:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def load_state_bytes(self, state):
            assert state == b"authenticated-test-state"

    for name in (
        "WindowedFrameBudgetController", "PokemonRedStateReader",
        "build_red_goal_context_runtime", "FrameSafeExecutor", "HardCompositionActionLimiter",
        "CountingExecutor", "CompositionIndependentBudgetMeter", "_LiveObserver",
        "ViewerGoalTrajectory",
    ):
        monkeypatch.setitem(namespace, name, lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setitem(namespace, "PyBoyAdapter", lambda *_args, **_kwargs: Emulator())
    monkeypatch.setitem(namespace, "EpisodeTrajectorySink", lambda *_args, **_kwargs: sink)
    monkeypatch.setitem(
        namespace, "RecordingExecutor",
        lambda **_kwargs: SimpleNamespace(next_step_index=7),
    )
    monkeypatch.setitem(
        namespace, "PokemonRedObservationEncoder",
        SimpleNamespace(from_state_reader=lambda _reader: None),
    )

    def player(**kwargs):
        try:
            raise RuntimeError("provider readiness disappeared")
        except RuntimeError as error:
            kwargs["failure_observer"](error)
        raise KeyboardInterrupt

    monkeypatch.setitem(namespace, "run_bounded_player_episode", player)
    readiness = SimpleNamespace(
        pair_id="private-failure-wire", decision_limit=4, context_origin="training",
        source_commit="1" * 40, source_bundle_sha256="2" * 64, rom_sha256="3" * 64,
        model_sha256="4" * 64, rom_path=Path("unused-rom"),
        capture=SimpleNamespace(
            state_sha256="5" * 64, envelope_sha256="6" * 64,
            state_bytes=b"authenticated-test-state",
        ),
        profile=SimpleNamespace(profile_sha256="7" * 64),
        private_root=SimpleNamespace(begin_episode=lambda _id: writer),
        challenger_arm_id=module["CAUSAL_ARM_ID"], continue_after_progress=True,
        routed_resource_goals=False, save_terminal_checkpoints=False,
        quote_resource_costs=False, training_plan=None, continuation=None, completion_dose=False,
    )
    with pytest.raises(KeyboardInterrupt):
        run_arm(readiness, arm_id=module["CAUSAL_ARM_ID"], authority=object())
    assert headers[0]["metadata"]["evidence_scope"] == "training_context_integration_only"
    assert [event.kind for event in events] == ["component_failure", "terminal"]
    diagnostic = events[0].payload["private_diagnostic"]
    assert diagnostic["exception_type"] == "RuntimeError"
    assert diagnostic["message"] == "provider readiness disappeared"
    assert events[0].step_index == 7
    assert events[1].payload["private_diagnostic"]["exception_type"] == "KeyboardInterrupt"
    assert aborted == ["paired_arm_failed"]
