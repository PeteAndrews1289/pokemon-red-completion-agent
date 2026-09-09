"""Actual arm-owner wiring with a real collector and the existing fake emulator."""

from inspect import getclosurevars
from types import SimpleNamespace

import pytest
from test_goal_resource_quote import _supply_model
from test_paired_red_bounded_player_script import _spent_arm_failure_harness
from test_red_forward_goal import champion_raw, choice, observation
from test_red_forward_runner import readiness as forward_readiness
from test_red_player_training import _plan

from pokemon_red_completion.forward_goal import ForwardGoalTerminal
from pokemon_red_completion.goal_manager_composition_runtime import CompositionBudgetCheckpoint
from pokemon_red_completion.living_dex_option_value import (
    upgrade_option_value_model_for_optional_recovery,
)
from pokemon_red_completion.red_forward_goal import RedForwardGoalCollector


def wired(monkeypatch, *, stage="verifier", complete=False, terminal_write_error=False):
    h = _spent_arm_failure_harness(monkeypatch, stage=stage)
    closure = getclosurevars(h.run).nonlocals
    ready, namespace = closure["readiness"], closure["run_arm"].__globals__
    model = upgrade_option_value_model_for_optional_recovery(_supply_model())
    ready.training_plan = _plan(model)
    ready.causal_record = SimpleNamespace(model=model)
    ready.decision_limit = 2
    ready.forward_story_objective = "defeat_champion"
    ready.forward_resource_budget = 2
    ready.profile = forward_readiness().profile
    ready.model_sha256 = model.model_sha256
    meter = namespace["CompositionIndependentBudgetMeter"]()
    meter.checkpoint = lambda: CompositionBudgetCheckpoint(
        h.emulator.inputs, h.emulator.frame_count
    )
    holder = [observation()]
    adapter = SimpleNamespace(observe=lambda: holder[0])
    monkeypatch.setitem(
        namespace, "build_red_goal_context_runtime", lambda **_: SimpleNamespace(adapter=adapter)
    )
    writer = ready.private_root.begin_episode("unused")
    original_append = writer.append
    forward_events, headers, collectors = [], [], []

    def append(stream, document, **kwargs):
        if stream == "forward_goal":
            assert not h.emulator.closed and kwargs == {"durable": True}
            if terminal_write_error and document.get("outcome") is not None:
                raise OSError("forward outcome append failed")
            h.order.append(document["kind"])
            forward_events.append(document)
            return
        return original_append(stream, document, **kwargs)

    writer.append = append
    sink = namespace["EpisodeTrajectorySink"]()
    sink.write_episode_header = lambda **kwargs: headers.append(kwargs["metadata"])

    def trajectory(**kwargs):
        collector = kwargs["forward"]
        assert isinstance(collector, RedForwardGoalCollector)
        assert kwargs["observe_training"] is adapter.observe
        assert kwargs["training_meter"] is meter
        assert kwargs["training_plan_sha256"] == ready.training_plan.plan_sha256
        assert h.emulator.inputs == 0
        assert [event["kind"] for event in forward_events] == ["forward_goal_declaration"]
        collectors.append(collector)
        return SimpleNamespace(forward=collector)

    monkeypatch.setitem(namespace, "RedForwardTrainingTrajectory", trajectory)
    original_player = namespace["run_bounded_player_episode"]

    def player(**kwargs):
        collector = kwargs["trajectory"].forward
        assert collector is collectors[0]
        assert kwargs["limits"].max_decisions == 2
        assert kwargs["completion_satisfied"](None) is False
        assert kwargs["stop_requested"](None) is False
        assert callable(kwargs["validate_choice_menu"])
        collector.anchor(choice(holder[0]))
        result = original_player(**kwargs)
        if complete:
            holder[0] = observation(champion_raw())
            collector.after_macro()
            assert kwargs["completion_satisfied"](None) is True
            assert kwargs["stop_requested"](None) is True
        return result

    monkeypatch.setitem(namespace, "run_bounded_player_episode", player)
    return h, ready, forward_events, headers, collectors


def test_run_arm_declares_before_input_and_censors_spent_failure_before_closing(monkeypatch):
    h, ready, events, headers, collectors = wired(monkeypatch)
    with pytest.raises(ValueError) as raised:
        h.run()
    assert raised.value is h.error
    assert h.order.index("forward_goal_declaration") < h.order.index("forward_goal_anchor")
    assert h.order.index("forward_goal_anchor") < h.order.index("input")
    assert h.order.index("forward_goal_observation") < h.order.index("capture_failure")
    assert h.order.index("failure_state") < h.order.index("close")
    assert events[-1]["outcome"]["target"] is None
    assert events[-1]["outcome"]["terminal"] == "interrupted"
    assert events[-1]["counters"] == {"actions": 1, "frames": 30, "resources": 0, "macros": 0}
    assert collectors[0].outcome.terminal is ForwardGoalTerminal.INTERRUPTED
    assert len(h.saved) == 1
    assert headers[0]["forward_goal_authority"] == "recording-only-existing-actor"
    assert headers[0]["player_training_plan"]["seed"] == 17
    assert headers[0]["player_training_plan_sha256"] == ready.training_plan.plan_sha256


def test_reporting_error_preserves_first_durable_completion_and_stop_callbacks(monkeypatch):
    h, _, events, _, collectors = wired(monkeypatch, stage="terminal_capture", complete=True)
    with pytest.raises(ValueError) as raised:
        h.run()
    assert raised.value is h.error
    outcome = collectors[0].outcome
    assert outcome.terminal is ForwardGoalTerminal.REACHED
    assert outcome.target[0] == 1.0
    assert len(events) == 3  # No replacement interrupted event after known completion.
    assert events[-1]["outcome"]["observed_goal"] is True
    assert h.order.index("forward_goal_observation") < h.order.index("terminal_capture")
    assert len(h.saved) == 1 and h.order[-2:] == ["close", "abort"]


def test_normal_episode_stop_finalizes_known_failure_before_terminal_capture(monkeypatch):
    h, _, events, _, collectors = wired(monkeypatch, stage="terminal_capture")
    with pytest.raises(ValueError) as raised:
        h.run()
    assert raised.value is h.error
    assert collectors[0].outcome.terminal is ForwardGoalTerminal.STOPPED
    assert events[-1]["outcome"]["target"][0] == 0.0
    assert events[-1]["outcome"]["observed_goal"] is False
    assert len(events) == 3 and len(h.saved) == 1


def test_forward_append_failure_does_not_mask_original_or_prevent_failure_state(monkeypatch):
    h, _, events, _, collectors = wired(monkeypatch, terminal_write_error=True)
    with pytest.raises(ValueError) as raised:
        h.run()
    assert raised.value is h.error
    assert raised.value.__notes__ == ["forward-goal terminal unavailable: OSError"]
    assert collectors[0].outcome is None
    assert len(events) == 2 and len(h.saved) == 1
    assert h.order.index("failure_state") < h.order.index("close")


def test_actual_arm_passes_live_menu_guard_that_rejects_before_action(monkeypatch):
    from pokemon_red_completion.goal_manager import GoalKind
    from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding, GoalBindingSet

    h, _, _, _, _ = wired(monkeypatch)
    namespace = getclosurevars(h.run).nonlocals["run_arm"].__globals__
    original_player = namespace["run_bounded_player_episode"]
    checked = []

    def may_not_run(*_):
        pytest.fail("unsupported menu must not execute or verify")

    bindings = tuple(
        ExecutableGoalBinding(ref, kind, 0.1, 0.1, may_not_run, may_not_run)
        for ref, kind in (
            ("pokemon.red:recovery:routed-center:synthetic", GoalKind.RESTORE_TEAM),
            ("pokemon.red:funding:synthetic", GoalKind.RESUPPLY),
        )
    )
    unsupported = GoalBindingSet(tuple(b.opportunity for b in bindings), bindings)

    def inspect_callback(**kwargs):
        validate = kwargs["validate_choice_menu"]
        assert callable(validate) and h.emulator.inputs == 0
        with pytest.raises(RuntimeError, match="forward_goal_unsupported_binding"):
            validate(SimpleNamespace(binding_set=unsupported))
        checked.append(unsupported)
        assert h.emulator.inputs == 0 and unsupported.bindings == bindings
        # Catch only at this test boundary; the normal runtime does not swallow
        # validation exceptions. Continue to exercise the arm's existing shell.
        return original_player(**kwargs)

    monkeypatch.setitem(namespace, "run_bounded_player_episode", inspect_callback)
    with pytest.raises(ValueError) as raised:
        h.run()
    assert raised.value is h.error
    assert checked == [unsupported]


@pytest.mark.parametrize(
    "pp_restore,inherited,exhausted",
    [
        (False, False, False),
        (True, False, False),
        (False, True, False),
        (True, True, False),
        (False, True, True),
    ],
)
def test_actual_player_observer_supplies_story_world_without_routing_field_recovery(
    monkeypatch,
    pp_restore,
    inherited,
    exhausted,
):
    import runpy
    from dataclasses import replace

    from test_red_elixir_plan import state
    from test_red_forward_runner import SCRIPT
    from test_red_goal_skills import _adapter, _Reader

    import pokemon_red_completion.red_resource_goal_router as routing
    import pokemon_red_completion.red_routed_recovery as recovery
    from pokemon_red_completion.executor import CountingExecutor
    from pokemon_red_completion.goal_manager import GoalAvailability, GoalKind
    from pokemon_red_completion.red_goal_context import RedGoalContextRuntime
    from pokemon_red_completion.red_goal_context_profile import RedGoalMechanic
    from pokemon_red_completion.red_goal_skills import MapId
    from pokemon_red_completion.route_executor import TraversalSnapshot

    module = runpy.run_path(str(SCRIPT))
    ready = forward_readiness(
        recovery=RedGoalMechanic.FIELD_PP_RESTORE if pp_restore else RedGoalMechanic.FIELD_RESTORE,
        parameters={} if pp_restore else {"affordable_single_item": True},
    )
    ready.routed_resource_goals = True
    inherited_flags = {
        "routed_recovery": inherited,
        "trainer_funding": inherited,
        "trainer_pending_recovery": inherited,
        "regional_trainer_funding": inherited,
    }
    for name, value in inherited_flags.items():
        setattr(ready, name, value)
    # Providing cartridge routing data must be a legal opt-in, not buying authority.
    assert module["_forward_goal_plan"](ready) is not None
    raw = replace(
        state(), bag_items=(*state().bag_items, (18, 2)), bag_item_ids=(*state().bag_item_ids, 18)
    )
    if exhausted:
        # No HP item remains; real router can offer a nurse already in reach.
        raw = replace(state(), map_id=int(MapId.VIRIDIAN_POKECENTER), player_x=3, player_y=7)
    reader = _Reader(raw=raw, ready=True)
    adapter = replace(_adapter(reader), include_pp_restoration=True)
    current = adapter.observe()
    emulator = SimpleNamespace(frame_count=0, pressed_buttons=frozenset())
    actions = CountingExecutor(
        SimpleNamespace(
            execute=lambda _: pytest.fail("enumeration may not execute a macro"),
        )
    )
    runtime = RedGoalContextRuntime(
        ready.profile,
        None,
        emulator,
        reader,
        SimpleNamespace(observe=lambda: current.game_state),
        adapter,
    )
    world = SimpleNamespace(rom=b"synthetic route world; never decode a cartridge")
    monkeypatch.setattr(routing, "Gen1TrainerSightProjector", lambda *args: None)
    traversal = SimpleNamespace(
        observe=lambda: TraversalSnapshot(
            raw.map_id,
            (raw.player_y, raw.player_x),
            True,
            mode="land",
        ),
    )
    monkeypatch.setattr(routing, "Gen1TraversalObserver", lambda *args, **kwargs: traversal)
    monkeypatch.setattr(recovery, "Gen1TraversalObserver", lambda *args, **kwargs: traversal)
    monkeypatch.setattr(
        routing.RedResourceGoalRouter,
        "_plan",
        lambda *args: pytest.fail("direct story/field restore must not be routed"),
    )
    local_results = []
    original = RedGoalContextRuntime.enumerator

    def enumerator(self, counted):
        actual = original(self, counted)

        def enumerate_once(observed):
            local = actual.enumerate(observed)
            local_results.append(local)
            return local

        return SimpleNamespace(enumerate=enumerate_once)

    monkeypatch.setattr(RedGoalContextRuntime, "enumerator", enumerator)
    bridge = module["_player_observer"](runtime, actions, world, **inherited_flags)
    assert bridge.runtime.trainer_story_world is world
    assert runtime.trainer_story_world is None  # Original runtime is not mutated.
    story = bridge.runtime.provider_for(GoalKind.ADVANCE_STORY, actions)
    assert story.skills.get("defeat_champion").world is world
    router = bridge.enumerate_bindings.__self__
    assert router.runtime is bridge.runtime and router.world is world
    assert router.routed_recovery is inherited and router.trainer_funding is inherited
    assert router.prepare_capture_storage is False
    routed = bridge.enumerate_bindings(current)
    assert len(local_results) == 1
    if exhausted:
        assert not any(b.kind is GoalKind.RESTORE_TEAM for b in local_results[0].bindings)
        restores = [b for b in routed.bindings if b.kind is GoalKind.RESTORE_TEAM]
        assert len(restores) == 1
        assert restores[0].binding_ref.startswith("pokemon.red:recovery:routed-center:")
        with pytest.raises(RuntimeError, match="forward_goal_unsupported_binding"):
            module["_require_forward_binding_scope"](routed, ready.profile)
        # Preflight rejects the entire real menu, never filters the nurse away.
        guarded = module["_player_observer"](
            runtime,
            actions,
            world,
            forward_story_only=True,
            **inherited_flags,
        )
        with pytest.raises(RuntimeError, match="forward_goal_unsupported_binding"):
            guarded.enumerate_bindings(current)
        assert restores[0] in routed.bindings
    else:
        assert routed == local_results[0]  # Same direct skills, no transport wrappers.
        module["_require_forward_binding_scope"](routed, ready.profile)
    available = {
        item.kind
        for item in routed.opportunities
        if item.availability is GoalAvailability.AVAILABLE
    }
    assert GoalKind.RESTORE_TEAM in available
    assert GoalKind.RESUPPLY not in available
    assert available <= {GoalKind.ADVANCE_STORY, GoalKind.RESTORE_TEAM}
    assert actions.actions_executed == emulator.frame_count == 0
