"""ROM-free native assembly tests, using the same input port as real runtimes."""

import json
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_live_option_menu import _binding, _model, _situation
from test_red_player_lesson_runtime import fixture

import pokemon_red_completion.red_native_player as native
import pokemon_red_completion.red_player_lesson_runtime as lesson
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import ControllerWallTimeBudgetExhausted
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalFailureReason,
    GoalKind,
    GoalOpportunity,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import (
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.living_dex_option_value import upgrade_option_value_model_for_readiness


def test_native_cash_meter_retains_purchases_and_loss_despite_net_income():
    cash=[100]

    class Port:
        def execute(self, change):
            cash[0]+=change
            if change == -65:
                raise ValueError('retained native failure')

    actions=native.NativePlayerActions(Port(),lambda: None,observe_cash=lambda: cash[0])
    actions.execute(-20)
    actions.execute(50)
    with pytest.raises(ValueError,match='retained native failure'):
        actions.execute(-65)
    assert cash[0] == 65
    assert actions.observed_cash_debits == 85
    assert actions.observed_cash_rewards == 50
    assert actions.observed_cash_changes == 3


def test_native_cash_observer_is_optional_and_never_an_input():
    calls=[]
    actions=native.NativePlayerActions(NS(execute=lambda a:calls.append(a)),lambda: None)
    actions.execute('normal')
    assert calls == ['normal'] and actions.observed_cash_changes == 0
    with pytest.raises(TypeError,match='callable'):
        native.NativePlayerActions(None,None,observe_cash=True)


def test_native_cash_meter_tolerates_unobserved_title_screen_cash():
    cash = [100]
    actions = native.NativePlayerActions(
        NS(execute=lambda value: cash.__setitem__(0, value)),
        lambda: None, observe_cash=lambda: cash[0],
    )
    actions.execute(None)
    actions.execute(100)
    actions.execute(80)
    assert actions.observed_cash_debits == 20
    assert actions.observed_cash_rewards == 0
    assert actions.observed_cash_changes == 1


@pytest.mark.parametrize("axis", [None, "actions", "frames", "seconds"])
def test_evolution_reserve_uses_each_current_meter_without_reset(axis):
    session = native.NativePlayerSession.__new__(native.NativePlayerSession)
    session.limits = native.NativePlayerLimits(actions=400, frames=4000, seconds=120)
    session.recorder = NS(trace=[None] * (300 if axis == "actions" else 1))
    session.controller = NS(frames_executed=3000 if axis == "frames" else 1)
    session.wall = NS(elapsed_seconds=90 if axis == "seconds" else 1)
    assert session.evolution_reserve_reached() is (axis is not None)
    assert len(session.recorder.trace) == (300 if axis == "actions" else 1)


@pytest.mark.parametrize("fails", [False, True])
def test_inner_evolution_nursing_counts_attempt_once_even_on_failure(tmp_path, monkeypatch, fails):
    session = native.NativePlayerSession.__new__(native.NativePlayerSession)
    session.allow_collection_restoration = True
    session.active_kind = GoalKind.EVOLVE_SPECIES
    session.limits = native.NativePlayerLimits(heals=1)
    session.heals = session.training_healing_trips = 0
    session.output = tmp_path
    session.runtime = NS(reader=object())
    session.recorder = NS(enabled=True, trace=[])
    session.controller = NS(frames_executed=0)
    session.actions = object()
    clock = iter((100.0, 102.5))
    monkeypatch.setattr(native.time, "monotonic", lambda: next(clock))

    def nurse(actions, reader, emulator):
        assert (actions, reader, emulator) == (
            session.actions,
            session.runtime.reader,
            session.controller,
        )
        session.recorder.trace.append("nurse input")
        session.controller.frames_executed += 7
        if fails:
            raise RuntimeError("native nurse failed")

    if fails:
        with pytest.raises(RuntimeError, match="native nurse failed"):
            session.execute_training_healing(nurse, session.runtime.reader, session.controller)
    else:
        session.execute_training_healing(nurse, session.runtime.reader, session.controller)
    assert session.heals == session.training_healing_trips == 1
    assert json.loads((tmp_path / "training-healing-001/result.json").read_text()) == dict(
        succeeded=not fails,
        error_type="RuntimeError" if fails else None,
        model_queries=0,
        actions=1,
        frames=7,
        seconds=2.5,
        timing_scope="healer_callback_including_travel_and_nested_nursing",
    )
    with pytest.raises(RuntimeError, match="restoration budget exhausted"):
        session.execute_training_healing(nurse, session.runtime.reader, session.controller)
    assert len(session.recorder.trace) == session.heals == 1


@pytest.mark.parametrize("fault", ["kind", "permission", "port", "reader", "enabled"])
def test_inner_nursing_rejects_unowned_input_before_spending(tmp_path, fault):
    session = native.NativePlayerSession.__new__(native.NativePlayerSession)
    session.allow_collection_restoration = fault != "permission"
    session.active_kind = GoalKind.DEVELOP_TEAM if fault == "kind" else GoalKind.EVOLVE_SPECIES
    session.recorder = NS(enabled=fault != "enabled")
    session.runtime = NS(reader=object())
    session.controller = object()
    with pytest.raises(ValueError, match="selected guarded evolution port"):
        session.execute_training_healing(
            lambda *_: pytest.fail("must not enter nursing"),
            object() if fault == "reader" else session.runtime.reader,
            object() if fault == "port" else session.controller,
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("fails", (False, True))
def test_acquisition_evolution_child_has_scoped_nurse_permission(tmp_path, fails):
    from pokemon_red_completion.goal_manager_runtime import (
        ExecutableGoalBinding,
        GoalExecutionReport,
    )

    session = native.NativePlayerSession.__new__(native.NativePlayerSession)
    session.allow_collection_restoration = True
    session.active_kind = GoalKind.ACQUIRE_SPECIES
    session.limits = native.NativePlayerLimits(heals=2)
    session.heals = session.training_healing_trips = 0
    session.output = tmp_path
    session.runtime = NS(reader=object())
    session.recorder = NS(enabled=True, trace=[])
    session.controller = NS(frames_executed=0)
    session.actions = object()

    def nurse(*_):
        session.recorder.trace.append("normal nurse")
        session.controller.frames_executed += 7

    def child():
        assert session.active_kind is GoalKind.ACQUIRE_SPECIES
        session.execute_training_healing(nurse, session.runtime.reader, session.controller)
        if fails:
            raise RuntimeError("retained child failure")
        return GoalExecutionReport(1, 7, {})

    binding = ExecutableGoalBinding("actual-evolution-child", GoalKind.EVOLVE_SPECIES,
        .1, .1, child, lambda _: None)
    with pytest.raises(ValueError, match="guarded evolution port"):
        session.execute_training_healing(nurse, session.runtime.reader, session.controller)
    if fails:
        with pytest.raises(RuntimeError, match="retained child failure"):
            session.execute_evolution_subgoal(binding)
    else:
        assert session.execute_evolution_subgoal(binding).actions_executed == 1
    assert session.heals == session.training_healing_trips == 1
    assert not session._evolution_subgoal_active
    with pytest.raises(ValueError, match="guarded evolution port"):
        session.execute_training_healing(nurse, session.runtime.reader, session.controller)


@pytest.mark.parametrize("fault", ("parent", "child", "type", "permission", "enabled", "nested"))
def test_evolution_delegation_rejects_unselected_or_recursive_child(fault):
    from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding

    session = native.NativePlayerSession.__new__(native.NativePlayerSession)
    session.allow_collection_restoration = fault != "permission"
    session.recorder = NS(enabled=fault != "enabled")
    session.active_kind = GoalKind.RESUPPLY if fault == "parent" else GoalKind.ACQUIRE_SPECIES
    session._evolution_subgoal_active = fault == "nested"
    binding = ExecutableGoalBinding("child", GoalKind.RESTORE_TEAM if fault == "child"
        else GoalKind.EVOLVE_SPECIES, .1, .1,
        lambda: pytest.fail("unowned child must not execute"), lambda _: None)
    with pytest.raises(ValueError, match="selected acquisition and typed child"):
        session.execute_evolution_subgoal(object() if fault == "type" else binding)


@pytest.mark.parametrize("cash", [None, 0, 2000])
def test_explicit_ordinary_economy_or_finite_cash_bound(cash):
    assert native.NativePlayerLimits(cash_debits=cash).cash_debits == cash


@pytest.mark.parametrize("field", ["force_resource_safety", "include_live_pp_readiness"])
@pytest.mark.parametrize("permission", [None, 0, 1, "yes"])
def test_native_resource_permissions_reject_coercion_before_claim(
    tmp_path,
    monkeypatch,
    field,
    permission,
):
    args, executed = setup(tmp_path, monkeypatch)
    args[field] = permission
    with pytest.raises(TypeError, match="permissions must be boolean"):
        native.run_native_continuous_player(**args)
    assert not executed and not args["output"].exists()


def test_model_resource_authority_cannot_expand_train_or_validation_scope(tmp_path, monkeypatch):
    args, executed = setup(tmp_path, monkeypatch)
    args["force_resource_safety"] = False
    with pytest.raises(ValueError, match="declared DEVELOPMENT scope"):
        native.run_native_continuous_player(**args)
    assert not executed and not args["output"].exists()


@pytest.mark.parametrize("cash", [True, -1, 1.5, "unlimited"])
def test_cash_bound_rejects_ambiguous_values(cash):
    with pytest.raises(ValueError):
        native.NativePlayerLimits(cash_debits=cash)


def setup(tmp_path, monkeypatch, *, fault=None, support=None, after_execute=None):
    store, emulator, kwargs = fixture(tmp_path, monkeypatch)
    original = lesson.capture_player_lesson_snapshot

    def capture(runtime):
        observation, snapshot = original(runtime)
        observation.input_ready = not (support == "control" and emulator.frame_count == 0)
        observation.raw.battle_state = 0
        observation.situation = _situation(resources=0.1)
        observation.collection_observation = NS(
            owned_species=("one",),
            specimens=(NS(species_ref="one"),),
        )
        return observation, snapshot

    monkeypatch.setattr(lesson, "capture_player_lesson_snapshot", capture)
    monkeypatch.setattr(native, "capture_player_lesson_snapshot", capture)
    executed = []

    def factory(controller):
        runtime = kwargs["runtime_factory"](controller)
        runtime.reader = NS(read_bottom_dialogue_box_visible=lambda: False)

        def enumerator(actions):
            if fault == "enumerate_input":
                actions.execute(MacroAction(MacroActionKind.WAIT))

            def execute():
                start_actions, start_frames = actions.actions_executed, controller.frames_executed
                if fault == "bypass":
                    controller.tick(1)
                if fault == "reset":
                    controller.load_state_bytes(b"bad")
                actions.execute(MacroAction(MacroActionKind.WAIT, repeat=2))
                executed.append(controller.frames_executed)
                if after_execute is not None:
                    after_execute()
                return GoalExecutionReport(
                    actions.actions_executed - start_actions,
                    controller.frames_executed - start_frames,
                    {},
                )

            def verify(report):
                if fault == "verify_action":
                    actions.execute(MacroAction(MacroActionKind.WAIT))
                if fault == "verify":
                    controller.press("a")
                return GoalVerification.succeeded()

            bindings = tuple(
                replace(
                    _binding(kind, binding_ref=kind.value, calls=[]),
                    execute=execute,
                    verify=verify,
                )
                for kind in (GoalKind.ADVANCE_STORY, GoalKind.DEVELOP_TEAM)
            )
            if support:
                kind = GoalKind.RECOVER_CONTROL if support == "control" else GoalKind.RESTORE_TEAM
                binding = replace(
                    _binding(kind, binding_ref=kind.value, calls=[]), execute=execute, verify=verify
                )
                blocked = GoalOpportunity(
                    "absent",
                    GoalKind.EXPLORE,
                    GoalAvailability.UNAVAILABLE,
                    unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
                )
                return NS(
                    enumerate=lambda _: GoalBindingSet(
                        (binding.opportunity, blocked),
                        (binding,),
                    )
                )
            return NS(
                enumerate=lambda _: GoalBindingSet(
                    tuple(b.opportunity for b in bindings),
                    bindings,
                )
            )

        runtime.enumerator = enumerator
        return runtime

    args = dict(
        store=store,
        emulator=emulator,
        runtime_factory=factory,
        source=kwargs["source"],
        output=tmp_path / "native",
        model=upgrade_option_value_model_for_readiness(_model()),
        seed=101,
        run_id="native-test",
        arm_id="candidate",
        combat_specimen_refs=kwargs["combat_specimen_refs"],
        battle_observer=lambda: kwargs["battle"],
        target_cash=3000,
        limits=native.NativePlayerLimits(decisions=3, actions=2, frames=20, cash_debits=3000),
    )
    return args, executed


def test_native_wrapper_uses_fresh_custom_bindings_on_guarded_port(tmp_path, monkeypatch):
    args, executed = setup(tmp_path, monkeypatch)
    frames = []

    def enumerate_bindings(runtime, actions, observation):
        frames.append(runtime.emulator.frame_count)
        return runtime.enumerator(actions).enumerate(observation)

    args["enumerate_bindings"] = enumerate_bindings
    args["limits"] = replace(args["limits"], actions=3, decisions=3)
    result = native.run_native_continuous_player(**args)
    assert result["successful_decisions"] == 3
    assert frames == [0, 2, 4] and executed == [2, 4, 6]
    assert not (args["output"] / "episode/sequence").exists()


def test_continuous_episode_keeps_one_port_across_twenty_one_choices(tmp_path, monkeypatch):
    args, executed = setup(tmp_path, monkeypatch)
    observed_frames = []

    def enumerate_bindings(runtime, actions, observation):
        observed_frames.append(runtime.emulator.frame_count)
        return runtime.enumerator(actions).enumerate(observation)

    args["enumerate_bindings"] = enumerate_bindings
    args["limits"] = replace(args["limits"], decisions=21, actions=21, frames=50)
    result = native.run_native_continuous_player(**args)
    assert result["model_decisions"] == result["successful_decisions"] == 21
    assert observed_frames == list(range(0, 42, 2))
    assert executed == list(range(2, 44, 2))
    costs = json.loads((args["output"] / "native-costs.json").read_text())
    assert costs["actions_completed"] == 21 and costs["frames"] == 42


@pytest.mark.parametrize("mix", [0, 0.25, 0.75, 1])
def test_native_development_loop_forwards_and_records_sampler_mix(tmp_path, monkeypatch, mix):
    import pokemon_red_completion.red_autonomous_player as autonomous

    args, executed = setup(tmp_path, monkeypatch)
    args["source"] = dict(args["source"], partition="development")
    args["limits"] = replace(args["limits"], actions=3)
    args["exploration_mix"] = mix
    original = autonomous.select_red_live_option
    calls = []

    def select(*positional, **options):
        calls.append(options["exploration_mix"])
        return original(*positional, **options)

    monkeypatch.setattr(autonomous, "select_red_live_option", select)
    result = native.run_native_continuous_player(**args)
    assert result["successful_decisions"] == len(executed) == 3
    assert calls == [mix] * 3
    plan = json.loads((args["output"] / "episode/plan.json").read_text())
    assert plan["exploration_mix"] == mix
    assert plan["model_sha256"] == args["model"].model_sha256
    assert plan["seed"] == args["seed"]


@pytest.mark.parametrize("fault", ["evaluation", "greedy", "sequence", "consequence",
    True, None, "0.75", -0.1, 1.1, float("nan"), float("inf")])
def test_native_custom_mix_rejects_invalid_or_other_scope_before_inputs(
    tmp_path, monkeypatch, fault
):
    args, executed = setup(tmp_path, monkeypatch)
    args["source"] = dict(args["source"], partition="development")
    args["exploration_mix"] = 0.75
    if fault == "evaluation":
        args["source"]["partition"] = "evaluation"
    elif fault == "greedy":
        args["greedy_selection"] = True
    elif fault == "sequence":
        args["sequence_horizon"] = object()
    elif fault == "consequence":
        args["consequence_spec"] = object()
    else:
        args["exploration_mix"] = fault
    with pytest.raises(ValueError, match="exploration"):
        native.run_native_continuous_player(**args)
    assert not executed and not args["output"].exists()


@pytest.mark.parametrize(
    "fault", [None, "wrong_kind", "failed_verifier", "unsettled", "trainer_loss"]
)
@pytest.mark.parametrize(
    "wild", [False, True, "capture", "capture_from_wild", "trainer", "trainer_intro", "motion", "field"]
)
@pytest.mark.parametrize("resume_refinement", [False, True])
def test_existing_blackout_preface_is_compulsory_metered_and_then_rejoins_model(
    tmp_path, monkeypatch, fault, wild, resume_refinement
):
    from pokemon_red_completion.player_readiness import CONTEXT_NAMES, PlayerReadiness
    from pokemon_red_completion.red_player_support import RedPlayerSupport

    args, executed = setup(tmp_path, monkeypatch)
    args["source"] = dict(args["source"], partition="development")
    capture_mode = wild in {"capture", "capture_from_wild"}
    trainer_mode = wild in {"trainer", "trainer_intro"}
    trainer_intro_mode = wild == "trainer_intro"
    motion_mode = wild == "motion"
    field_mode = wild == "field"
    setting = (
        "settle_existing_motion"
        if motion_mode
        else "settle_existing_trainer"
        if trainer_mode
        else "settle_existing_capture"
        if capture_mode and wild != "capture_from_wild"
        else "settle_existing_wild"
        if wild and not field_mode
        else "settle_existing_blackout"
    )
    args[setting] = True
    if trainer_intro_mode:
        args["settle_existing_motion"] = True
        if fault == "trainer_permission":
            args["settle_existing_trainer"] = False
    args["limits"] = replace(args["limits"], actions=3, decisions=3)
    recovered = [False]
    model_calls = []
    if resume_refinement:
        from test_red_consequence_choice import progress_head

        import pokemon_red_completion.red_consequence_choice as choice_module
        from pokemon_red_completion.living_dex_option_value import (
            upgrade_option_value_model_for_preparation,
        )

        args.update(
            model=upgrade_option_value_model_for_preparation(args["model"]),
            consequence_head=progress_head(),
            consequence_challenge_ref="declared-fixture-branch",
            consequence_objective_ref="declared-fixture-branch",
            resume_branch_refinement_after_settlement=True,
        )
        selector0 = choice_module.select_branch_recovery_live_option

        def select(*values, **kw):
            assert recovered[0], "head must not query before independent settlement"
            assert (args["output"] / "settled-branch-refinement.json").exists()
            model_calls.append(args["emulator"].frame_count)
            return selector0(*values, **kw)

        monkeypatch.setattr(choice_module, "select_branch_recovery_live_option", select)
    capture0 = native.capture_player_lesson_snapshot

    def capture(runtime):
        observation, snapshot = capture0(runtime)
        observation.raw.battle_state = (
            0 if recovered[0] or motion_mode or field_mode or trainer_intro_mode
            else 1 if wild and not trainer_mode else 2
        )
        observation.raw.party_hp = (
            (20,) if recovered[0] else (5,) if wild and not field_mode else (0,)
        )
        observation.input_ready = recovered[0]
        snapshot["in_battle"] = (
            not recovered[0] and not motion_mode and not field_mode and not trainer_intro_mode
        )
        return observation, snapshot

    monkeypatch.setattr(native, "capture_player_lesson_snapshot", capture)
    factory0 = args["runtime_factory"]

    def factory(controller):
        runtime = factory0(controller)
        runtime.reader.read = lambda: capture(runtime)[0].raw
        runtime.reader.read_input_readiness = lambda: NS(ready=recovered[0])
        runtime.reader.read_bottom_dialogue_box_visible = lambda: field_mode and not recovered[0]
        return runtime

    args["runtime_factory"] = factory
    observe0 = native.NativePlayerSession.observe

    def observe(session, ordinal):
        if recovered[0]:
            return observe0(session, ordinal)

        def execute():
            session.recorder.enabled = True
            try:
                session.actions.execute(MacroAction(MacroActionKind.WAIT, repeat=2))
                session.decisions += 1
                recovered[0] = fault != "unsettled"
                return GoalExecutionReport(
                    1,
                    2,
                    (
                        dict(battle=dict(outcome="lost", field_ready=True))
                        if fault == "trainer_loss"
                        else dict(blackout=True)
                    ),
                )
            finally:
                session.recorder.enabled = False

        kind = GoalKind.DEVELOP_TEAM if fault == "wrong_kind" else GoalKind.RECOVER_CONTROL
        reference = (
            "pokemon.red:retained-motion:"
            if motion_mode
            else "pokemon.red:retained-engagement:"
            if trainer_mode
            else "pokemon.red:retained-capture:"
            if capture_mode
            else "pokemon.red:interrupted-wild:"
            if wild and not field_mode
            else "pokemon.red:field-blackout:"
        )
        binding = replace(
            _binding(kind, binding_ref=reference + (
                "0" * 64 if fault == "wrong_ref" else session.snapshot().sha256
            ), calls=[]),
            execute=execute,
            verify=lambda _: (
                GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
                if fault == "failed_verifier"
                else GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
                if fault == "trainer_loss"
                else GoalVerification.succeeded()
            ),
        )
        blocked = GoalOpportunity(
            "missing",
            GoalKind.EXPLORE,
            GoalAvailability.UNAVAILABLE,
            unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
        )
        return RedPlayerSupport(
            GoalBindingSet((binding.opportunity, blocked), (binding,)),
            PlayerReadiness((0.0,) * len(CONTEXT_NAMES) + (1.0,) * 5, history_observed=False),
        )

    monkeypatch.setattr(native.NativePlayerSession, "observe", observe)
    accepted = fault is None or fault == "trainer_loss" and trainer_mode
    if accepted:
        result = native.run_native_continuous_player(**args)
        assert result["model_decisions"] == result["successful_decisions"] == 2
        key = (
            "supplied_motion_preface"
            if motion_mode
            else "supplied_trainer_preface"
            if trainer_mode
            else "supplied_capture_preface"
            if capture_mode
            else "supplied_wild_escape_preface"
            if wild and not field_mode
            else "supplied_blackout_preface"
        )
        assert not result[key]["learned"]
        assert result[key]["ordinary_setback"] is (fault == "trainer_loss")
        assert result[key]["verification"] == ("failed" if fault == "trainer_loss" else "succeeded")
        assert executed == [4, 6]
        directory = (
            "retained-motion-preface"
            if motion_mode
            else "retained-trainer-preface"
            if trainer_mode
            else "retained-capture-preface"
            if capture_mode
            else "wild-escape-preface"
            if wild and not field_mode
            else "blackout-preface"
        )
        assert (args["output"] / directory / "intent.json").exists()
        if resume_refinement:
            receipt = json.loads((args["output"] / "settled-branch-refinement.json").read_text())
            assert model_calls == [2, 4]
            assert receipt["goal_model_queries_before_settlement"] == 0
            assert receipt["head_sha256"] == args["consequence_head"].model_sha256
            assert receipt["settlement_terminal_sha256"] == result[key]["terminal_sha256"]
        else:
            assert not (args["output"] / "settled-branch-refinement.json").exists()
    else:
        with pytest.raises(ValueError, match="blackout"):
            native.run_native_continuous_player(**args)
        assert not executed
        assert not model_calls
    costs = json.loads((args["output"] / "native-costs.json").read_text())
    assert costs["actions_attempted"] == (
        3 if accepted else 0 if fault in {"wrong_kind", "wrong_ref", "trainer_permission"} else 1
    )
    assert costs["buttons_released"]


@pytest.mark.parametrize("resume_refinement", [False, True])
@pytest.mark.parametrize("fault", ["wrong_ref", "trainer_permission"])
def test_trainer_introduction_requires_its_exact_binding_and_explicit_permission(
    tmp_path, monkeypatch, fault, resume_refinement,
):
    test_existing_blackout_preface_is_compulsory_metered_and_then_rejoins_model(
        tmp_path, monkeypatch, fault, "trainer_intro", resume_refinement,
    )


@pytest.mark.parametrize("fault", [None, "train", "synthetic", "v1", "model_v5",
                                  "missing_objective", "different_challenge", "no_preface",
                                  "sequence", "recording", "not_bool"])
def test_settled_refinement_scope_is_explicit_and_preserves_historical_default(fault):
    from test_red_consequence_choice import head, progress_head

    from pokemon_red_completion.living_dex_option_value import (
        upgrade_option_value_model_for_preparation,
    )
    args = dict(allow=True, source={"partition": "development"},
                model=upgrade_option_value_model_for_preparation(_model()),
                head=progress_head(), objective_ref="declared", challenge_ref="declared",
                settlement_requested=True, sequence_horizon=None, sequence_policy=None,
                consequence_spec=None)
    if fault == "train":
        args["source"] = {"partition": "train"}
    elif fault == "synthetic":
        args["head"] = head()
    elif fault == "v1":
        args["head"] = replace(head(), provenance="native_train")
    elif fault == "model_v5":
        args["model"] = upgrade_option_value_model_for_readiness(_model())
    elif fault == "missing_objective":
        args["objective_ref"] = None
    elif fault == "different_challenge":
        args["challenge_ref"] = "different"
    elif fault == "no_preface":
        args["settlement_requested"] = False
    elif fault == "sequence":
        args["sequence_policy"] = object()
    elif fault == "recording":
        args["consequence_spec"] = object()
    elif fault == "not_bool":
        args["allow"] = 1
    if fault is None:
        assert native.validate_settlement_refinement_scope(**args)
    else:
        with pytest.raises(ValueError, match="settled branch refinement"):
            native.validate_settlement_refinement_scope(**args)
    assert native.validate_settlement_refinement_scope(**{**args, "allow": False}) is False


def test_absent_preface_cannot_activate_the_head_or_query_model(tmp_path, monkeypatch):
    from test_red_consequence_choice import progress_head

    from pokemon_red_completion.living_dex_option_value import (
        upgrade_option_value_model_for_preparation,
    )
    args, executed = setup(tmp_path, monkeypatch)
    args.update(source={**args["source"], "partition": "development"},
                model=upgrade_option_value_model_for_preparation(args["model"]),
                consequence_head=progress_head(), consequence_objective_ref="declared",
                consequence_challenge_ref="declared", settle_existing_wild=True,
                resume_branch_refinement_after_settlement=True)
    factory0 = args["runtime_factory"]

    def factory(controller):
        runtime = factory0(controller)
        runtime.reader.read = lambda: NS(battle_state=0, party_hp=(20,))
        return runtime

    args["runtime_factory"] = factory
    monkeypatch.setattr(native, "run_autonomous_options",
                        lambda **_: pytest.fail("must not query without a verified preface"))
    with pytest.raises(ValueError, match="no verified compulsory boundary"):
        native.run_native_continuous_player(**args)
    assert not executed and not (args["output"] / "settled-branch-refinement.json").exists()


def test_declared_branch_set_survives_compulsory_settlement_scope():
    from test_red_consequence_choice import progress_head

    from pokemon_red_completion.living_dex_option_value import (
        upgrade_option_value_model_for_preparation,
    )
    from pokemon_red_completion.red_consequence_choice import branch_recovery_scope_ref

    scope = ("defeat_misty", "help_bill")
    args = dict(allow=True, source={"partition": "development"},
                model=upgrade_option_value_model_for_preparation(_model()),
                head=progress_head(), objective_ref=scope,
                challenge_ref=branch_recovery_scope_ref(scope), settlement_requested=True,
                sequence_horizon=None, sequence_policy=None, consequence_spec=None)
    assert native.validate_settlement_refinement_scope(**args)
    with pytest.raises(ValueError, match="settled branch refinement"):
        native.validate_settlement_refinement_scope(**{**args, "challenge_ref": "help_bill"})


@pytest.mark.parametrize("fault", ["train", "one_decision", "not_bool"])
@pytest.mark.parametrize("wild", [False, True, "capture", "trainer", "motion"])
def test_blackout_preface_scope_rejected_before_any_input_or_claim(
    tmp_path, monkeypatch, fault, wild
):
    args, executed = setup(tmp_path, monkeypatch)
    args["source"] = dict(args["source"], partition="train" if fault == "train" else "development")
    setting = (
        "settle_existing_motion"
        if wild == "motion"
        else "settle_existing_trainer"
        if wild == "trainer"
        else "settle_existing_capture"
        if wild == "capture"
        else "settle_existing_wild"
        if wild
        else "settle_existing_blackout"
    )
    args[setting] = 1 if fault == "not_bool" else True
    if fault == "one_decision":
        args["limits"] = replace(args["limits"], decisions=1)
    with pytest.raises(ValueError, match="blackout preface"):
        native.run_native_continuous_player(**args)
    assert not executed and not args["output"].exists()


@pytest.mark.parametrize("limited", ["actions", "frames"])
def test_long_episode_still_stops_at_one_shared_native_budget(tmp_path, monkeypatch, limited):
    args, executed = setup(tmp_path, monkeypatch)
    args["limits"] = replace(
        args["limits"],
        decisions=21,
        actions=11 if limited == "actions" else 30,
        frames=22 if limited == "frames" else 100,
    )
    result = native.run_native_continuous_player(**args)
    assert result["model_decisions"] == result["successful_decisions"] == 11
    assert result["stop_reason"] == "menu_unavailable"
    assert executed == list(range(2, 24, 2))
    assert args["emulator"].frame_count == 22 and not args["emulator"].pressed_buttons


def test_zero_remaining_heals_preserves_strict_continuation_budget(tmp_path, monkeypatch):
    args, executed = setup(tmp_path, monkeypatch, support="restore")
    args["limits"] = replace(args["limits"], heals=0)
    result = native.run_native_continuous_player(**args)
    assert not executed
    assert result["model_decisions"] == 0
    cost = json.loads((args["output"] / "native-costs.json").read_text())
    assert cost["restore_attempts"] == cost["actions_attempted"] == 0


@pytest.mark.parametrize("heals", [-1, True, 0.5])
def test_invalid_heal_limits_fail(heals):
    with pytest.raises(ValueError):
        native.NativePlayerLimits(heals=heals)


def test_native_wrapper_opt_in_sequence_collection_preserves_guarded_costs(tmp_path, monkeypatch):
    args, executed = setup(tmp_path, monkeypatch)
    args["sequence_horizon"] = 2
    args["limits"] = replace(args["limits"], actions=3, decisions=3)
    result = native.run_native_continuous_player(**args)
    root = args["output"] / "episode/sequence"
    declaration = json.loads((root / "declaration.json").read_text())
    collected = json.loads((root / "result.json").read_text())
    assert declaration["source_sha256"] == args["source"]["state_sha256"]
    assert declaration["partition"] == args["source"]["partition"]
    assert result["successful_decisions"] == 3 and executed == [2, 4, 6]
    assert collected["projection_error"] is None
    windows = [json.loads(path.read_text()) for path in root.glob("window-*.json")]
    assert sum(row["measurement"]["actions"] for row in windows) == 3
    assert sum(row["measurement"]["frames"] for row in windows) == 6
    assert not collected["training_eligible"]


@pytest.mark.parametrize("horizon", [0, 5, True])
def test_native_invalid_sequence_horizon_precedes_claim_or_input(tmp_path, monkeypatch, horizon):
    args, executed = setup(tmp_path, monkeypatch)
    args["sequence_horizon"] = horizon
    with pytest.raises(ValueError, match="collection declaration"):
        native.run_native_continuous_player(**args)
    assert executed == [] and not args["output"].exists()
    identity = native.NativeExecutionIdentity(
        args["run_id"],
        args["arm_id"],
        args["model"].model_sha256,
        args["seed"],
    )
    assert args["store"].find_sealed_record(identity.claim_id) is None


def test_dynamic_story_supplements_are_fresh_and_metered(tmp_path, monkeypatch):
    from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate
    from pokemon_red_completion.red_live_option_menu import supplemental_live_option

    args, executed = setup(tmp_path, monkeypatch)
    observed = []
    selected = []
    from pokemon_red_completion.living_dex_option_value import LivingDexOptionValueModel

    monkeypatch.setattr(
        LivingDexOptionValueModel,
        "scores",
        lambda self, menu, utility: tuple(
            1000.0 if row.features.execution_effort == 0.9 else 0.0 for row in menu.candidates
        ),
    )

    def extra(runtime, actions, observation, bindings):
        observed.append(runtime.emulator.frame_count)
        first = bindings.bindings[0]

        def execute():
            selected.append("other-story")
            return first.execute()

        second = replace(first, binding_ref="other-story", estimated_effort=0.9, execute=execute)
        projected = GoalBindingSet(
            (second.opportunity, bindings.bindings[1].opportunity),
            (second, bindings.bindings[1]),
        ).question(observation.situation)
        candidate = project_living_dex_goal_candidate(
            projected, 0, feature_version=5, binding_ref=second.binding_ref
        )
        return (supplemental_live_option(second, candidate),)

    args["enumerate_supplements"] = extra
    args["limits"] = replace(args["limits"], actions=3, decisions=3)
    result = native.run_native_continuous_player(**args)
    assert observed == [0, 2, 4] and executed == [2, 4, 6]
    assert result["successful_decisions"] == 3
    assert result["model_decisions"] == 3
    assert selected == ["other-story"] * 3


def test_dynamic_inventory_cannot_consume_controller_input(tmp_path, monkeypatch):
    args, executed = setup(tmp_path, monkeypatch)

    def extra(runtime, actions, observation, bindings):
        actions.execute(MacroAction(MacroActionKind.WAIT))
        return ()

    args["enumerate_supplements"] = extra
    result = native.run_native_continuous_player(**args)
    assert result["stop_reason"] == "menu_unavailable"
    assert args["emulator"].frame_count == 0
    assert not executed


def test_control_recovery_does_not_enumerate_story_supplements(tmp_path, monkeypatch):
    args, executed = setup(tmp_path, monkeypatch, support="control")
    args["limits"] = replace(args["limits"], decisions=1)
    args["enumerate_supplements"] = lambda *a: pytest.fail("story during control recovery")
    result = native.run_native_continuous_player(**args)
    assert executed == [2] and result["support_decisions"] == 1


def test_dynamic_inventory_requires_immutable_tuple(tmp_path, monkeypatch):
    args, executed = setup(tmp_path, monkeypatch)
    args["enumerate_supplements"] = lambda *a: []
    result = native.run_native_continuous_player(**args)
    assert result["stop_reason"] == "menu_unavailable"
    assert not executed


def test_v6_challenge_observation_is_fresh_and_legacy_player_rejects_it(tmp_path, monkeypatch):
    from pokemon_red_completion.living_dex_option_value import (
        upgrade_option_value_model_for_challenge,
    )
    from pokemon_red_completion.player_option_challenge import OptionChallenge

    args, executed = setup(tmp_path, monkeypatch)
    seen = []

    def preview(runtime, bindings, supplements, boundary):
        seen.append(runtime.emulator.frame_count)
        return {
            bindings.bindings[0].binding_ref: OptionChallenge.from_levels(
                combat_levels=(17,), opponent_levels=(18, 21)
            )
        }

    args["observe_challenges"] = preview
    args["model"] = upgrade_option_value_model_for_challenge(args["model"])
    args["limits"] = replace(args["limits"], actions=3, decisions=3)
    result = native.run_native_continuous_player(**args)
    assert seen == [0, 2, 4] and executed == [2, 4, 6]
    assert result["successful_decisions"] == 3


def test_v5_does_not_silently_drop_challenge_preview(tmp_path, monkeypatch):
    from pokemon_red_completion.player_option_challenge import OptionChallenge

    args, executed = setup(tmp_path, monkeypatch)
    args["observe_challenges"] = lambda rt, bindings, supplements, boundary: {
        bindings.bindings[0].binding_ref: OptionChallenge(False, False, 0.0, 0.0, 0.0)
    }
    result = native.run_native_continuous_player(**args)
    assert result["stop_reason"] == "menu_unavailable" and not executed


@pytest.mark.parametrize("version", [6, 7])
def test_preparation_observer_reaches_native_loop_or_rejects_legacy(tmp_path, monkeypatch, version):
    from test_player_option_preparation import facts

    from pokemon_red_completion.living_dex_option_value import (
        upgrade_option_value_model_for_challenge,
        upgrade_option_value_model_for_preparation,
    )

    args, executed = setup(tmp_path, monkeypatch)
    seen = []

    def preview(runtime, bindings, supplements, boundary):
        seen.append(runtime.emulator.frame_count)
        return {
            b.binding_ref: facts() for b in bindings.bindings if b.kind is GoalKind.DEVELOP_TEAM
        }

    args["observe_preparations"] = preview
    upgrade = (
        upgrade_option_value_model_for_preparation
        if version == 7
        else upgrade_option_value_model_for_challenge
    )
    args["model"] = upgrade(args["model"])
    args["limits"] = replace(args["limits"], actions=3, decisions=3)
    result = native.run_native_continuous_player(**args)
    if version == 7:
        assert seen == [0, 2, 4] and executed == [2, 4, 6]
        assert result["successful_decisions"] == 3
    else:
        assert result["stop_reason"] == "menu_unavailable" and not executed


def test_native_replans_from_actual_new_battler_history(tmp_path, monkeypatch):
    from test_red_player_battle_history import battler, publish

    from pokemon_red_completion.post_battle_strategy import BattleResult
    from pokemon_red_completion.red_player_battle_history import NativeBattlerHistory

    directory = tmp_path / "battles"
    directory.mkdir()
    b = battler(directory)
    history = NativeBattlerHistory(b)
    observed = []
    original = native.observe_native_player_options

    def observe(*args, **kwargs):
        observed.append(kwargs["battle"])
        return original(*args, **kwargs)

    monkeypatch.setattr(native, "observe_native_player_options", observe)
    args, executed = setup(
        tmp_path, monkeypatch, after_execute=lambda: publish(b, unresolved=b.calls > 0)
    )
    args["battle_observer"] = history
    args["limits"] = replace(args["limits"], actions=3, decisions=3)
    result = native.run_native_continuous_player(**args)
    assert executed == [2, 4, 6] and result["successful_decisions"] == 3
    assert observed[0] is None
    assert [row.result for row in observed[1:]] == [BattleResult.LOST, BattleResult.UNRESOLVED]


@pytest.mark.parametrize("support", ["control", "singleton"])
def test_native_forced_support_is_executed_without_model_query(tmp_path, monkeypatch, support):
    import pokemon_red_completion.red_autonomous_player as runner

    args, executed = setup(tmp_path, monkeypatch, support=support)
    args["limits"] = replace(args["limits"], decisions=1)
    monkeypatch.setattr(
        runner, "select_red_live_option", lambda *a, **k: pytest.fail("model query")
    )
    result = native.run_native_continuous_player(**args)
    assert executed == [2] and result["successful_decisions"] == 1
    assert result["model_decisions"] == 0 and result["support_decisions"] == 1
    assert result["outcomes"][0]["support_role"] == (
        "deterministic_control_recovery" if support == "control" else "forced_singleton"
    )


def test_total_input_budget_and_real_fresh_budget_features_across_goals(tmp_path, monkeypatch):
    args, executed = setup(tmp_path, monkeypatch)
    result = native.run_native_continuous_player(**args)
    assert executed == [2, 4]
    assert result["executed_decisions"] == result["successful_decisions"] == 2
    assert result["stop_reason"] == "menu_unavailable"
    assert args["emulator"].frame_count == 4
    costs = json.loads((args["output"] / "native-costs.json").read_text())
    assert costs["actions_attempted"] == costs["actions_completed"] == 2
    assert costs["goal_attempts"] == 2 and costs["buttons_released"]
    menus = [
        json.loads((args["output"] / f"episode/step-{i:03d}/intent.json").read_text())
        for i in (0, 1)
    ]
    assert menus[0]["menu"]["menu_sha256"] != menus[1]["menu"]["menu_sha256"]
    assert (args["output"] / "terminal.state").read_bytes() == b"4"
    assert not costs["automatic_fit"] and costs["promotions"] == 0


@pytest.mark.parametrize("fault", ["bypass", "reset", "verify", "verify_action"])
def test_native_entry_rejects_input_outside_recorded_macros_and_retains_terminal(
    tmp_path,
    monkeypatch,
    fault,
):
    args, executed = setup(tmp_path, monkeypatch, fault=fault)
    result = native.run_native_continuous_player(**args)
    assert result["stop_reason"] == "execution_failed"
    assert args["emulator"].frame_count == (2 if fault in {"verify", "verify_action"} else 0)
    assert len(executed) == (1 if fault in {"verify", "verify_action"} else 0)
    assert (args["output"] / "terminal.state").exists()
    assert not args["emulator"].pressed_buttons


def test_menu_cannot_execute_through_the_recorded_action_port(tmp_path, monkeypatch):
    args, executed = setup(tmp_path, monkeypatch, fault="enumerate_input")
    result = native.run_native_continuous_player(**args)
    assert result["stop_reason"] == "menu_unavailable"
    assert not executed and args["emulator"].frame_count == 0


def test_frame_overrun_does_not_reset_budget_or_continue(tmp_path, monkeypatch):
    args, executed = setup(tmp_path, monkeypatch)
    args["limits"] = replace(args["limits"], frames=3)
    result = native.run_native_continuous_player(**args)
    costs = json.loads((args["output"] / "native-costs.json").read_text())
    assert result["stop_reason"] == "execution_failed"
    assert executed == [2]
    assert costs["frames"] == 2  # The whole next two-frame tick is refused.
    assert costs["actions_attempted"] == 2 and costs["actions_completed"] == 1
    assert result["outcomes"][1]["measured_cost"] is None
    assert result["outcomes"][1]["observed_cost"] == dict(
        actions=1, completed_actions=0, frames=0, cash_spent=0
    )


def test_failed_native_goal_keeps_costs_without_permitting_replanning(tmp_path, monkeypatch):
    money = [1500]

    def fail():
        money[0] -= 500
        raise RuntimeError("partial native action")

    args, executed = setup(tmp_path, monkeypatch, after_execute=fail)
    original = native.capture_player_lesson_snapshot

    def capture(runtime):
        observation, snapshot = original(runtime)
        observation.raw.player_money = money[0]
        return observation, snapshot

    monkeypatch.setattr(native, "capture_player_lesson_snapshot", capture)
    result = native.run_native_continuous_player(**args)
    assert result["stop_reason"] == "execution_failed" and executed == [2]
    row = result["outcomes"][0]
    assert row["verification"] is None and row["measured_cost"] is None
    assert row["observed_cost"] == dict(actions=1, completed_actions=1, frames=2, cash_spent=500)
    assert result["accounted_cash_spent"] == 500
    assert not row["ordinary_setback"] and result["successful_decisions"] == 0


def test_wall_deadline_prevents_input_but_preserves_endpoint(tmp_path, monkeypatch):
    args, _ = setup(tmp_path, monkeypatch)
    args["execution"] = native.NativeExecutionIdentity(
        args.pop("run_id"), args.pop("arm_id"), args.pop("model").model_sha256, args.pop("seed")
    )
    session = native.NativePlayerSession(**args)
    monkeypatch.setattr(
        native.MonotonicWallTimeBudgetController,
        "check_wall_time_budget",
        lambda _: (_ for _ in ()).throw(
            ControllerWallTimeBudgetExhausted(
                maximum_wall_seconds=300,
                elapsed_seconds=301,
            )
        ),
    )
    with pytest.raises(ControllerWallTimeBudgetExhausted):
        session.observe(0)
    assert session.controller.frames_executed == 0
    assert session.snapshot().state == b"0"


@pytest.mark.parametrize("source", [{"partition": "validation"}, {"state_sha256": "0" * 64}])
def test_invalid_source_never_creates_runtime_or_output(tmp_path, monkeypatch, source):
    args, _ = setup(tmp_path, monkeypatch)
    args["source"] = {**args["source"], **source}
    with pytest.raises(ValueError, match="authenticated declared source"):
        native.run_native_continuous_player(**args)
    assert args["emulator"].frame_count == 0 and not args["output"].exists()


@pytest.mark.parametrize("changed", ["run_id", "arm_id", "seed"])
def test_same_basename_divergent_executions_have_separate_action_records(
    tmp_path, monkeypatch, changed
):
    args, _ = setup(tmp_path, monkeypatch)
    args["limits"] = replace(args["limits"], decisions=1)
    repeat = [1]

    def bindings(rt, actions, boundary):
        original = rt.enumerator(actions).enumerate(boundary)

        def execute():
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=repeat[0]))
            return GoalExecutionReport(1, repeat[0], {})

        return replace(
            original, bindings=tuple(replace(b, execute=execute) for b in original.bindings)
        )

    args["enumerate_bindings"] = bindings
    plans = []
    for i in range(2):
        parent = tmp_path / f"arm-{i}"
        parent.mkdir()
        args["output"] = parent / "continuous"
        if i:
            args[changed] = 102 if changed == "seed" else "other"
            args["emulator"].frame_count = 0  # ROM-free identical-source fixture.
            repeat[0] = 2
        result = native.run_native_continuous_player(**args)
        assert result["successful_decisions"] == 1
        plans.append(json.loads((args["output"] / "native-plan.json").read_text()))
    declarations = [native.canonical_sha256(p) for p in plans]
    assert len(set(declarations)) == 2
    for declaration in declarations:
        record = args["store"].find_sealed_record(f"rnl-action-{declaration}-0")
        assert record is not None
        # Read-only, idempotent access does not replay the recorded action.
        assert (
            args["store"].find_sealed_record(f"rnl-action-{declaration}-0").summary
            == record.summary
        )


def test_consumed_execution_cannot_restart_under_another_output(tmp_path, monkeypatch):
    args, _ = setup(tmp_path, monkeypatch)
    native.run_native_continuous_player(**args)
    args["emulator"].frame_count = 0
    args["output"] = tmp_path / "renamed"
    with pytest.raises(ValueError, match="already consumed"):
        native.run_native_continuous_player(**args)
    assert args["emulator"].frame_count == 0 and not args["output"].exists()


@pytest.mark.parametrize(
    "change",
    [
        {"run_id": "../private"},
        {"arm_id": ""},
        {"seed": True},
        {"seed": -1},
        {"model_sha256": "bad"},
    ],
)
def test_invalid_execution_identity_is_rejected(change):
    args = dict(run_id="run", arm_id="arm", model_sha256="a" * 64, seed=1)
    with pytest.raises(ValueError):
        native.NativeExecutionIdentity(**{**args, **change})


def test_model_is_part_of_execution_identity():
    a = native.NativeExecutionIdentity("run", "arm", "a" * 64, 1)
    b = replace(a, model_sha256="b" * 64)
    assert a.claim_id != b.claim_id


@pytest.mark.parametrize("receipt", [None, "bad", "g" * 64])
def test_train_collection_nursing_requires_explicit_valid_setup_before_input(
    tmp_path, monkeypatch, receipt,
):
    args,_=setup(tmp_path,monkeypatch)
    args.update(source=dict(args["source"],partition="train"),
                allow_collection_restoration=True,resource_setup_receipt=receipt)
    with pytest.raises(ValueError,match="TRAIN setup"):
        native.run_native_continuous_player(**args)
    assert args["emulator"].frame_count==0 and not args["output"].exists()


@pytest.mark.parametrize("partition,receipt", [
    ("train", "bad"), ("train", "g" * 64), ("train", True),
    ("development", "a" * 64),
])
def test_collection_teacher_receipt_cannot_expand_evaluation_or_accept_invalid_setup(
    tmp_path, monkeypatch, partition, receipt,
):
    args, _ = setup(tmp_path, monkeypatch)
    args.update(
        source=dict(args["source"], partition=partition),
        collection_teacher_setup_receipt=receipt,
        allow_collection_restoration=True,
    )
    with pytest.raises(ValueError, match="declared TRAIN setup"):
        native.run_native_continuous_player(**args)
    assert args["emulator"].frame_count == 0 and not args["output"].exists()


@pytest.mark.parametrize(
    "fault", [None, "second_heal", "verification", "action_budget", "frame_budget",
              "unknown_budget_text", "verifier_budget_marker"]
)
@pytest.mark.parametrize(
    "selected_kind",
    [GoalKind.DEVELOP_TEAM, GoalKind.RESUPPLY, GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES],
)
def test_nested_restoration_uses_the_original_budget_and_retains_failure(
    tmp_path, monkeypatch, fault, selected_kind
):
    args, _ = setup(tmp_path, monkeypatch)
    if selected_kind in {GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES}:
        args["allow_collection_restoration"] = True
        args["source"] = dict(args["source"], partition="development")
    args["limits"] = replace(args["limits"], decisions=1, heals=1, actions=5, frames=20)
    if fault == "action_budget":
        args["limits"] = replace(args["limits"], actions=1)
    if fault == "frame_budget":
        args["limits"] = replace(args["limits"], frames=3)
    continued = []

    def bindings(rt, actions, boundary):
        def heal():
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=2))
            return GoalExecutionReport(1, 2, {"restore": True})

        restore = replace(
            _binding(
                GoalKind.RESTORE_TEAM,
                binding_ref=(
                    "pokemon.red:recovery:pokemon-center-pp"
                    if selected_kind is not GoalKind.DEVELOP_TEAM
                    else "nurse"
                ),
                calls=[],
            ),
            execute=heal,
            verify=lambda _: (
                GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
                if fault == "verification"
                else GoalVerification.succeeded()
            ),
        )

        def develop():
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=2))  # travel
            if fault == "unknown_budget_text":
                raise RuntimeError("native player restoration budget exhausted")
            actions.execute_restoration(restore)
            if fault == "second_heal":
                actions.execute_restoration(restore)
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=2))  # unchanged dose
            continued.append(True)
            return GoalExecutionReport(3, 6, {"target_unchanged": True})

        def verify(_):
            if fault == "verifier_budget_marker":
                from pokemon_red_completion.executor import RestorationBudgetExhausted
                raise RestorationBudgetExhausted(maximum_heals=1, restoration_attempts=1)
            return GoalVerification.succeeded()

        b = replace(
            _binding(selected_kind, binding_ref="selected-original", calls=[]),
            execute=develop,
            verify=verify,
        )
        blocked = GoalOpportunity(
            "absent",
            GoalKind.EXPLORE,
            GoalAvailability.UNAVAILABLE,
            unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
        )
        return GoalBindingSet((b.opportunity, blocked), (b,))

    args["enumerate_bindings"] = bindings
    result = native.run_native_continuous_player(**args)
    costs = json.loads((args["output"] / "native-costs.json").read_text())
    if fault == "unknown_budget_text":
        assert result["stop_reason"] == "execution_failed"
        assert costs["restore_attempts"] == costs["nested_restore_attempts"] == 0
        assert costs["frames"] == 2 and not continued
        assert not (args["output"] / "restoration-000").exists()
        return
    receipt = json.loads((args["output"] / "restoration-000/result.json").read_text())
    assert costs["restore_attempts"] == costs["nested_restore_attempts"] == 1
    assert costs["goal_attempts"] == 1 and result["model_decisions"] == 0
    assert continued == ([True] if fault in (None, "verifier_budget_marker") else [])
    expected_stop = (
        "decision_budget" if fault is None
        else "restoration_budget" if fault == "second_heal"
        else "execution_failed"
    )
    assert result["stop_reason"] == expected_stop
    if fault == "second_heal":
        outcome = json.loads((args["output"] / "episode/step-000/outcome.json").read_text())
        assert outcome["error_type"] == "RestorationBudgetExhausted"
        assert outcome["failure_reason"] == "execution_budget_exhausted"
        assert outcome["verification"] == "failed"
        assert outcome["evidence"] is None
    assert receipt["succeeded"] == (fault in (None, "second_heal", "verifier_budget_marker"))
    assert costs["frames"] == (
        6 if fault in (None, "verifier_budget_marker")
        else 2 if fault in ("action_budget", "frame_budget") else 4
    )
    assert receipt["model_queries"] == 0


@pytest.mark.parametrize("fault", ["other_goal", "other_restore", "paid_restore"])
def test_income_nested_nurse_does_not_admit_arbitrary_goals_or_paid_recovery(
    tmp_path,
    monkeypatch,
    fault,
):
    from types import SimpleNamespace

    # Exercise the executor admission itself, not a malformed one-kind menu.
    session = object.__new__(native.NativePlayerSession)
    session.recorder = SimpleNamespace(enabled=True)
    session.active_kind = GoalKind.ADVANCE_STORY if fault == "other_goal" else GoalKind.RESUPPLY
    session.heals = session.support_restorations = 0
    restore = replace(
        _binding(
            GoalKind.RESTORE_TEAM,
            binding_ref=(
                "arbitrary"
                if fault == "other_restore"
                else "pokemon.red:recovery:pokemon-center-pp"
            ),
            calls=[],
        ),
        maximum_cash_debit=1 if fault == "paid_restore" else 0,
        execute=lambda: pytest.fail("invalid nested nurse executed"),
    )
    with pytest.raises(ValueError, match="selected development or free income nursing"):
        session.execute_restoration(restore)
    assert session.heals == session.support_restorations == 0


@pytest.mark.parametrize("fault", ["default_off", "other_goal", "other_restore", "paid_restore"])
@pytest.mark.parametrize("kind", [GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES])
def test_collection_nested_nurse_is_default_off_and_exactly_scoped(fault, kind):
    from types import SimpleNamespace

    session = object.__new__(native.NativePlayerSession)
    session.recorder = SimpleNamespace(enabled=True)
    session.allow_collection_restoration = fault != "default_off"
    session.active_kind = GoalKind.EXPLORE if fault == "other_goal" else kind
    session.heals = session.support_restorations = 0
    restore = replace(
        _binding(
            GoalKind.RESTORE_TEAM,
            binding_ref="arbitrary"
            if fault == "other_restore"
            else "pokemon.red:recovery:pokemon-center-pp",
            calls=[],
        ),
        maximum_cash_debit=1 if fault == "paid_restore" else 0,
        execute=lambda: pytest.fail("unauthorized collection nurse input"),
    )
    with pytest.raises(ValueError, match="nested restoration"):
        session.execute_restoration(restore)
    assert session.heals == session.support_restorations == 0


@pytest.mark.parametrize(
    "fault", [None, "target", "injury", "objective", "malformed", "menu_input"]
)
def test_empty_menu_completes_only_the_explicit_observed_curriculum(tmp_path, monkeypatch, fault):
    import pokemon_red_completion.red_player_curriculum as curriculum

    args, _ = setup(tmp_path, monkeypatch)
    _, snapshot = native.capture_player_lesson_snapshot(None)
    member = snapshot["party"][0]
    objectives = tuple(snapshot["completed_objectives"])
    args["curriculum"] = curriculum.NativePlayerCurriculum(
        # Unfinished packets must still reject unsafe/malformed inventories.
        # Completed packets now stop before asking for any further menu.
        objectives + ("missing",)
        if fault in {"objective", "malformed", "menu_input"}
        else objectives,
        ((member["specimen_ref"], member["level"] + (1 if fault == "target" else 0)),),
    )
    monkeypatch.setattr(curriculum, "_raw_party_fully_restored", lambda _: fault != "injury")

    def empty(rt, actions, boundary):
        if fault == "malformed":
            raise ValueError("broken inventory")
        if fault == "menu_input":
            actions.execute(MacroAction(MacroActionKind.WAIT))
        unavailable = tuple(
            GoalOpportunity(
                k.value,
                k,
                GoalAvailability.UNAVAILABLE,
                unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
            )
            for k in (GoalKind.ADVANCE_STORY, GoalKind.DEVELOP_TEAM)
        )
        return GoalBindingSet(unavailable, ())

    args["enumerate_bindings"] = empty
    result = native.run_native_continuous_player(**args)
    assert result["stop_reason"] == ("curriculum_complete" if fault is None else "menu_unavailable")
    assert result["model_decisions"] == result["executed_decisions"] == 0
    assert args["emulator"].frame_count == 0
    assert (args["output"] / "episode/step-000/curriculum-complete.json").exists() == (
        fault is None
    )



@pytest.mark.parametrize("resume_refinement", [False, True])
def test_wild_capture_refinement_requires_exact_retained_binding(tmp_path, monkeypatch, resume_refinement):
    test_existing_blackout_preface_is_compulsory_metered_and_then_rejoins_model(
        tmp_path, monkeypatch, "wrong_ref", "capture_from_wild", resume_refinement,
    )
