import json
from hashlib import sha256
from types import SimpleNamespace as N

import pytest
from run_configured_red_player import (
    InspectionExecutor,
    authenticate_parent,
    configured_execution_limits,
    connect_owned_machine_options,
    declared_backend_sources,
    declared_goal_model,
    declared_greedy_selection,
    declared_input_recording,
    declared_owned_machine_options,
    declared_player_curriculum,
    declared_preparation_component,
    declared_readiness_refinement,
    diagnostic_spending,
    evolution_copy_choice,
    native_cash_deltas,
    native_checkpoint_facts,
    qualified_native_control_handoff,
    remaining_allowance,
    requires_compulsory_settlement,
    verify_loaded_backend_sources,
)


@pytest.mark.parametrize("fault", [None, "missing_reason", "wrong_error", "wrong_goal",
    "pressed", "stale", "prior_error", "extra_choice", "changed_during_inspection"])
def test_story_budget_handoff_requires_typed_censor_and_exact_unique_recovery(monkeypatch, fault):
    import run_configured_red_player as script
    from pokemon_red_completion.goal_manager import (
        GoalAvailability, GoalKind, GoalOpportunity, GoalUnavailableReason,
    )
    from pokemon_red_completion.goal_manager_runtime import (
        ExecutableGoalBinding, GoalBindingSet, GoalVerification,
    )
    payload = [b"exact-censored-story-battle"]
    digest = sha256(payload[0]).hexdigest()
    emulator = N(frame_count=80, pressed_buttons=set(), save_state_bytes=lambda: payload[0])
    runtime = N(emulator=emulator)
    last = dict(selected_kind=GoalKind.ADVANCE_STORY.value, failure_phase="execution",
        safe_terminal=False, error_type="StoryBattleDecisionBudgetReached",
        error="story battle reached its bounded decision limit", terminal_state_sha256=digest,
        error_chain=[dict(error_type="StoryBattleDecisionBudgetReached",
                          reason_code="story_battle_decision_budget")])
    result = dict(released=True, field_ready=False, state_sha256=digest,
                  episode=dict(stop_reason="execution_failed", outcomes=[last]))
    if fault == "missing_reason": last["error_chain"] = []
    if fault == "wrong_error": last["error_type"] = "RuntimeError"
    if fault == "wrong_goal": last["selected_kind"] = GoalKind.EVOLVE_SPECIES.value
    if fault == "pressed": emulator.pressed_buttons.add("a")
    if fault == "stale": payload[0] = b"other-state"
    if fault == "prior_error": result["episode"]["outcomes"].insert(0, dict(error_type="ValueError"))
    monkeypatch.setattr(script, "_field_ready", lambda _: False)
    calls = []

    def inventory():
        calls.append(True)
        binding = ExecutableGoalBinding("pokemon.red:retained-engagement:" + digest,
            GoalKind.RECOVER_CONTROL, 0., 0., lambda: pytest.fail("inspection must not execute"),
            lambda _: GoalVerification.succeeded())
        bindings = (binding,)
        if fault == "extra_choice":
            bindings += (ExecutableGoalBinding("other", GoalKind.EXPLORE, 0., 0.,
                lambda: pytest.fail("inspection must not execute"), lambda _: GoalVerification.succeeded()),)
        if fault == "changed_during_inspection": emulator.frame_count += 1
        blocked = GoalOpportunity("unavailable", GoalKind.EXPLORE, GoalAvailability.UNAVAILABLE,
                                  unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET)
        return GoalBindingSet((*tuple(b.opportunity for b in bindings), blocked), bindings)

    original = json.dumps(result, sort_keys=True)
    if fault == "changed_during_inspection":
        with pytest.raises(ValueError, match="changed state"):
            qualified_native_control_handoff(result, runtime=runtime, inspect_bindings=inventory)
    else:
        receipt = qualified_native_control_handoff(result, runtime=runtime, inspect_bindings=inventory)
        if fault is None:
            assert receipt["censored_story_battle"] and receipt["local_decision_limit_unchanged"]
            assert not receipt["aggregate_budget_reset"]
            assert receipt["inputs"] == receipt["frames"] == receipt["model_queries"] == 0
        else:
            assert receipt is None
    assert json.dumps(result, sort_keys=True) == original
    assert len(calls) == int(fault in {None, "extra_choice", "changed_during_inspection"})


@pytest.mark.parametrize("fault", [None, "different_error", "wrong_goal", "unsafe",
    "ready", "wrong_hash", "prior_error", "pressed", "no_contract", "mutated",
    "extra_binding", "wrong_kind", "wrong_ref"])
def test_native_control_handoff_requires_exact_error_terminal_and_contract(monkeypatch, fault):
    import run_configured_red_player as script

    from pokemon_red_completion.goal_manager import (
        GoalAvailability,
        GoalKind,
        GoalOpportunity,
        GoalUnavailableReason,
    )
    from pokemon_red_completion.goal_manager_runtime import (
        ExecutableGoalBinding,
        GoalBindingSet,
        GoalVerification,
    )
    payload = [b"retained-native-script"]
    emulator = N(frame_count=0, pressed_buttons=set(), save_state_bytes=lambda:payload[0])
    runtime = N(emulator=emulator, reader=N())
    state_sha = sha256(payload[0]).hexdigest()
    result = dict(released=True, field_ready=False, state_sha256=state_sha,
        episode=dict(stop_reason="execution_failed", outcomes=[dict(
            selected_kind=GoalKind.ADVANCE_STORY.value, failure_phase="execution",
            safe_terminal=True, error_type="RouteExecutionError",
            error="field dialogue lacks a newly poisoned member faint",
            terminal_state_sha256=state_sha)]))
    last = result["episode"]["outcomes"][-1]
    if fault == "different_error":
        last["error"] = "unknown dialogue"
    elif fault == "wrong_goal":
        last["selected_kind"] = "unknown_action"
    elif fault == "unsafe":
        last["safe_terminal"] = False
    elif fault == "ready":
        result["field_ready"] = True
    elif fault == "wrong_hash":
        result["state_sha256"] = last["terminal_state_sha256"] = "0" * 64
    elif fault == "prior_error":
        result["episode"]["outcomes"].insert(0, dict(error_type="ValueError"))
    elif fault == "pressed":
        emulator.pressed_buttons.add("a")
    monkeypatch.setattr(script, "_field_ready", lambda _:False)
    calls = []
    def contract():
        calls.append(True)
        if fault == "mutated":
            payload[0] = b"changed"
        if fault == "no_contract":
            return None
        binding = ExecutableGoalBinding(
            "pokemon.red:retained-engagement:" + ("0"*64 if fault == "wrong_ref" else state_sha),
            GoalKind.DEVELOP_TEAM if fault == "wrong_kind" else GoalKind.RECOVER_CONTROL,
            0.0, 0.0, lambda:pytest.fail("handoff inspection cannot execute"),
            lambda _:GoalVerification.succeeded(),
        )
        if fault == "extra_binding":
            extra = ExecutableGoalBinding("other", GoalKind.EXPLORE, 0.0, 0.0,
                lambda:pytest.fail("inspection cannot execute"),
                lambda _:GoalVerification.succeeded())
            return GoalBindingSet((binding.opportunity, extra.opportunity), (binding, extra))
        blocked = GoalOpportunity("missing", GoalKind.EXPLORE, GoalAvailability.UNAVAILABLE,
                                  unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET)
        return GoalBindingSet((binding.opportunity, blocked), (binding,))
    if fault == "mutated":
        with pytest.raises(ValueError, match="changed state"):
            qualified_native_control_handoff(result, runtime=runtime, inspect_bindings=contract)
    else:
        original = json.dumps(result, sort_keys=True)
        receipt = qualified_native_control_handoff(
            result, runtime=runtime, inspect_bindings=contract,
        )
        assert json.dumps(result, sort_keys=True) == original
        if fault is None:
            assert receipt["qualified"] and receipt["failed_transport_preserved"]
            assert receipt["inputs"] == receipt["frames"] == receipt["model_queries"] == 0
            assert not receipt["strategic_substitution"]
        else:
            assert receipt is None
        assert len(calls) == (
            1 if fault in {None,"no_contract","extra_binding","wrong_kind","wrong_ref"} else 0
        )


@pytest.mark.parametrize("fault", [None, "wrong_error", "wrong_parent", "trainer",
    "unguarded", "not_loanable", "no_outstanding_loan", "wrong_ref", "extra_binding", "mutated"])
@pytest.mark.parametrize("terminal_safe", (False, True))
def test_loan_wild_handoff_requires_exact_named_guard_and_compulsory_exit(
    monkeypatch, fault, terminal_safe
):
    import run_configured_red_player as script
    from test_red_player_party_loan import setup

    from pokemon_red_completion.goal_manager import (
        GoalAvailability,
        GoalKind,
        GoalOpportunity,
        GoalUnavailableReason,
    )
    from pokemon_red_completion.goal_manager_runtime import (
        ExecutableGoalBinding,
        GoalBindingSet,
        GoalVerification,
    )
    runtime, _, state, _ = setup(monkeypatch, already_restored=fault == "no_outstanding_loan")
    payload = [b"retained-evolution-loan-wild"]
    runtime.emulator = N(frame_count=0, pressed_buttons=(), save_state_bytes=lambda: payload[0])
    raw = runtime.reader.read()
    runtime.reader.read = lambda: N(**dict(vars(raw), battle_state=2 if fault == "trainer" else 1))
    if fault == "unguarded":
        runtime.adapter.party_guard = None
    elif fault == "not_loanable":
        from dataclasses import replace
        runtime.adapter.party_guard = replace(
            runtime.adapter.party_guard, loanable_refs=frozenset()
        )
    state_sha = sha256(payload[0]).hexdigest()
    result = dict(released=True, field_ready=False, state_sha256=state_sha,
        episode=dict(stop_reason="execution_failed", outcomes=[dict(
            selected_kind=GoalKind.ACQUIRE_SPECIES.value if fault == "wrong_parent" else
                GoalKind.EVOLVE_SPECIES.value,
            failure_phase="execution", safe_terminal=terminal_safe,
            error_type="RedGoalContextError",
            error="unrelated error" if fault == "wrong_error" else
                "PC loan settlement requires settled field control",
            terminal_state_sha256=state_sha)]))
    monkeypatch.setattr(script, "_field_ready", lambda _: False)
    calls = []

    def inventory():
        calls.append(True)
        if fault == "mutated":
            payload[0] = b"changed"
        ref = ("pokemon.red:retained-engagement:" if fault == "wrong_ref" else
            "pokemon.red:interrupted-wild:") + state_sha
        binding = ExecutableGoalBinding(ref, GoalKind.RECOVER_CONTROL, 0.0, 0.0,
            lambda: pytest.fail("inspection cannot execute"),
            lambda _: GoalVerification.succeeded())
        bindings = (binding,)
        if fault == "extra_binding":
            bindings += (ExecutableGoalBinding("other", GoalKind.EXPLORE, 0.0, 0.0,
                lambda: pytest.fail("inspection cannot execute"),
                lambda _: GoalVerification.succeeded()),)
        opportunities = tuple(b.opportunity for b in bindings)
        if len(opportunities) == 1:
            opportunities += (GoalOpportunity("blocked", GoalKind.EXPLORE,
                GoalAvailability.UNAVAILABLE,
                unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET),)
        return GoalBindingSet(opportunities, bindings)

    if fault == "mutated":
        with pytest.raises(ValueError, match="changed state"):
            qualified_native_control_handoff(result, runtime=runtime, inspect_bindings=inventory)
    else:
        receipt = qualified_native_control_handoff(
            result, runtime=runtime, inspect_bindings=inventory
        )
        if fault is None:
            assert receipt["retained_declared_loan"] and receipt["wild_exit_before_pc_return"]
            assert receipt["inputs"] == receipt["frames"] == receipt["model_queries"] == 0
        else:
            assert receipt is None
    assert calls == ([True] if fault in {None, "wrong_ref", "extra_binding", "mutated"} else [])
    assert state.cash == 100


@pytest.mark.parametrize("fault", [None, "wrong_error", "wrong_parent", "unsafe",
    "ready", "wrong_hash", "prior_error", "pressed", "unguarded", "active_battle",
    "no_dialogue", "start_menu", "fainted_party", "outstanding_loan", "wrong_ref", "wrong_kind",
    "extra_binding", "mutated", "advanced_frame"])
def test_static_transport_handoff_requires_exact_nonbattle_dialogue_and_custody(
    monkeypatch, fault
):
    import run_configured_red_player as script
    from test_red_player_party_loan import setup

    from pokemon_red_completion.goal_manager import (
        GoalAvailability,
        GoalKind,
        GoalOpportunity,
        GoalUnavailableReason,
    )
    from pokemon_red_completion.goal_manager_runtime import (
        ExecutableGoalBinding,
        GoalBindingSet,
        GoalVerification,
    )
    runtime, _, state, input_calls = setup(
        monkeypatch, already_restored=fault != "outstanding_loan"
    )
    payload = [b"retained-static-transport-dialogue"]
    runtime.emulator = N(frame_count=0, pressed_buttons=set(),
                         save_state_bytes=lambda: payload[0])
    runtime.reader.read_bottom_dialogue_box_visible = lambda: fault != "no_dialogue"
    runtime.reader.read_overworld_start_menu_visible = lambda: fault == "start_menu"
    raw = runtime.reader.read()
    runtime.reader.read = lambda: N(**dict(vars(raw), party_hp=tuple(
        0 if fault == "fainted_party" else m.hp for m in state.members),
                                          battle_state=2 if fault == "active_battle" else 0))
    if fault == "unguarded":
        runtime.adapter.party_guard = None
    state_sha = sha256(payload[0]).hexdigest()
    result = dict(released=True, field_ready=fault == "ready", state_sha256=state_sha,
        episode=dict(stop_reason="execution_failed", outcomes=[dict(
            selected_kind=(GoalKind.DEVELOP_TEAM if fault == "wrong_parent" else
                           GoalKind.ACQUIRE_SPECIES).value,
            failure_phase="execution", safe_terminal=fault != "unsafe",
            error_type="RouteExecutionError",
            error="unknown boundary" if fault == "wrong_error" else
                "selected static transport requires ordinary player settlement",
            terminal_state_sha256=state_sha)]))
    if fault == "wrong_hash":
        result["state_sha256"] = result["episode"]["outcomes"][-1]["terminal_state_sha256"] = "0" * 64
    elif fault == "prior_error":
        result["episode"]["outcomes"].insert(0, dict(error_type="ValueError"))
    elif fault == "pressed":
        runtime.emulator.pressed_buttons.add("a")
    monkeypatch.setattr(script, "_field_ready", lambda _: fault == "ready")
    inspected = []

    def inventory():
        inspected.append(True)
        if fault == "mutated":
            payload[0] = b"changed"
        elif fault == "advanced_frame":
            runtime.emulator.frame_count += 1
        binding = ExecutableGoalBinding(
            "pokemon.red:recovery:blocked-field-control" if fault == "wrong_ref" else
            "pokemon.red:retained-engagement:" + state_sha,
            GoalKind.EXPLORE if fault == "wrong_kind" else GoalKind.RECOVER_CONTROL,
            0.0, 0.0, lambda: pytest.fail("inspection cannot send inputs"),
            lambda _: GoalVerification.succeeded(),
        )
        bindings = (binding,)
        if fault == "extra_binding":
            bindings += (ExecutableGoalBinding("other", GoalKind.EXPLORE, 0.0, 0.0,
                lambda: pytest.fail("inspection cannot execute"),
                lambda _: GoalVerification.succeeded()),)
        opportunities = tuple(b.opportunity for b in bindings)
        if len(opportunities) == 1:
            opportunities += (GoalOpportunity("blocked", GoalKind.EXPLORE,
                GoalAvailability.UNAVAILABLE,
                unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED),)
        return GoalBindingSet(opportunities, bindings)

    original = json.dumps(result, sort_keys=True)
    if fault in {"mutated", "advanced_frame", "outstanding_loan"}:
        with pytest.raises(ValueError, match=("active party" if fault == "outstanding_loan"
                                             else "changed state")):
            qualified_native_control_handoff(result, runtime=runtime, inspect_bindings=inventory)
    else:
        receipt = qualified_native_control_handoff(
            result, runtime=runtime, inspect_bindings=inventory
        )
        if fault is None:
            assert receipt["retained_native_introduction"]
            assert receipt["retained_roster_restored"]
            assert receipt["failed_transport_preserved"]
            assert receipt["inputs"] == receipt["frames"] == receipt["model_queries"] == 0
            assert not receipt["strategic_substitution"]
        else:
            assert receipt is None
    assert json.dumps(result, sort_keys=True) == original
    assert input_calls == [] and state.cash == 100
    assert inspected == ([True] if fault in {
        None, "wrong_ref", "wrong_kind", "extra_binding", "mutated", "advanced_frame"
    } else [])


def test_observed_cash_debits_preserve_costs_inside_net_income_goal():
    outcomes=[{'before':{'cash':100},'after':{'cash':150}}]
    assert native_cash_deltas({'observed_cash_debits':20,
                               'control_recovery_cash_debits':10},outcomes) == (20,)
    assert native_cash_deltas({'control_recovery_cash_debits':10},outcomes) == (-50,10)


@pytest.mark.parametrize('partition,flag,valid', (
    ('development',True,True),('development',False,True),
    ('train',True,False),('development','true',False),
))
def test_owned_stock_income_permission_is_explicit_and_development_only(
    monkeypatch,partition,flag,valid,
):
    import run_configured_red_player as script
    for name in ('declared_greedy_selection','declared_readiness_refinement',
        'declared_preparation_component','declared_input_recording','declared_owned_machine_options',
        'declared_league_first_collection_scope'):
        monkeypatch.setattr(script,name,lambda _:None)
    plan=dict(partition=partition,owned_stock_income_bootstrap=flag)
    if valid:
        assert script.player_wiring_declaration(plan)['owned_stock_income_bootstrap'] is flag
    else:
        with pytest.raises(ValueError,match='DEVELOPMENT'):
            script.player_wiring_declaration(plan)


def _initial_work_order_wiring(plan):
    """Execute the production mapping expression and check its real spread site."""
    import ast
    from pathlib import Path
    import run_configured_red_player as script

    tree = ast.parse(Path(script.__file__).read_text())
    run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run")
    assignment = next(n for n in run.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "wiring" for t in n.targets))
    initial = next(n for n in ast.walk(run) if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "declaration" for t in n.targets)
        and isinstance(n.value, ast.Call)
        and any(k.arg == "partition" for k in n.value.keywords))
    spread = [k.value for k in initial.value.keywords if k.arg is None]
    assert len(spread) == 2
    assert isinstance(spread[0], ast.Name) and spread[0].id == "wiring"
    expected_identity = ast.parse(
        '{"goal_model_observation_identity": dict('
        'stored_model_sha256=configuration.goal_model_sha256, '
        'effective_model_sha256=model.model_sha256)} '
        'if "goal_model_observation_compatibility" in wiring else {}', mode="eval"
    ).body
    assert ast.dump(spread[1]) == ast.dump(expected_identity)
    assert not set(script.PLAYER_WIRING_FIELDS) & {k.arg for k in initial.value.keywords}
    wiring = eval(compile(ast.Expression(assignment.value), "work-order-wiring", "eval"),
        {"plan": plan, "player_wiring_declaration": script.player_wiring_declaration})
    stored, effective = "a" * 64, "b" * 64
    identity = eval(compile(ast.Expression(spread[1]), "compatibility-identity", "eval"),
        {"wiring": wiring, "configuration": N(goal_model_sha256=stored),
         "model": N(model_sha256=effective)})
    assert not set(wiring) & set(identity)
    assert identity == ({"goal_model_observation_identity": {
        "stored_model_sha256": stored, "effective_model_sha256": effective,
    }} if "goal_model_observation_compatibility" in wiring else {})
    return wiring


@pytest.mark.parametrize("flag", [False, True])
def test_actual_launch_declaration_forwards_owned_stock_permission_not_only_execution_log(flag):
    assert _initial_work_order_wiring(dict(partition="development",
        owned_stock_income_bootstrap=flag))["owned_stock_income_bootstrap"] is flag


@pytest.mark.parametrize("flag", [False, True])
def test_launch_identity_provenance_is_disjoint_from_owned_stock_permission(flag):
    compatibility = dict(
        schema="pokemon.red.goal-model-observation-compatibility.v1",
        mode="v9_to_v15_zero_extension_v1", source_model_sha256="a" * 64,
        target_model_sha256="b" * 64, reason="Explicit zero-extension test declaration",
    )
    wiring = _initial_work_order_wiring(dict(
        partition="development", owned_stock_income_bootstrap=flag,
        goal_model_record={"declared": True},
        goal_model_observation_compatibility=compatibility,
    ))
    assert wiring["owned_stock_income_bootstrap"] is flag
    assert wiring["goal_model_observation_compatibility"] == compatibility


@pytest.mark.parametrize("original,replacement", [
    ("**wiring,", "**{},"),
    ('**({"goal_model_observation_identity": dict(',
     '**({"owned_stock_income_bootstrap": dict('),
    ("stored_model_sha256=configuration.goal_model_sha256,",
     "stored_model_sha256=model.model_sha256,"),
    ("effective_model_sha256=model.model_sha256,",
     "effective_model_sha256=configuration.goal_model_sha256,"),
])
def test_launch_wiring_guard_rejects_permission_or_identity_drift(
    monkeypatch, tmp_path, original, replacement,
):
    from pathlib import Path
    import run_configured_red_player as script

    source = Path(script.__file__).read_text()
    assert original in source
    changed = tmp_path / "changed-declaration.py"
    changed.write_text(source.replace(original, replacement, 1))
    monkeypatch.setattr(script, "__file__", str(changed))
    with pytest.raises(AssertionError):
        _initial_work_order_wiring(dict(partition="development",
                                      owned_stock_income_bootstrap=True))


def test_actual_launch_forwards_distinct_snorlax_loan_without_reusing_bird_permission(monkeypatch):
    import run_configured_red_player as script
    import pokemon_red_completion.red_player_party_guard as guards

    monkeypatch.setattr(guards, "validate_bird_capture_loan_declaration", lambda value: None)
    monkeypatch.setattr(guards, "validate_snorlax_capture_loan_declaration", lambda value: None)
    bird, snorlax = {"distinct": "bird"}, {"distinct": "snorlax"}
    wiring = _initial_work_order_wiring(dict(partition="development",
        bird_capture_loan=bird, snorlax_capture_loan=snorlax))
    assert wiring["bird_capture_loan"] is bird
    assert wiring["snorlax_capture_loan"] is snorlax


@pytest.mark.parametrize("bad_plan", [
    dict(partition="train", owned_stock_income_bootstrap=True),
    dict(partition="development", conserved_owned_medicine_income=True),
    dict(partition="development", owned_stock_income_bootstrap=1),
])
def test_actual_work_order_uses_the_common_permission_validator(bad_plan):
    with pytest.raises(ValueError, match="DEVELOPMENT"):
        _initial_work_order_wiring(bad_plan)


@pytest.mark.parametrize('debit', [-1, True, None, 1.5])
def test_invalid_observed_cash_debit_fails_closed(debit):
    with pytest.raises(ValueError,match='invalid'):
        native_cash_deltas({'observed_cash_debits':debit},[])


def test_old_backend_plans_remain_unbound():
    assert declared_backend_sources({}) == {}
    verify_loaded_backend_sources({}, "unused")


@pytest.mark.parametrize("fault", [None,"partition","mode","reason","extra","type"])
def test_league_first_task_scope_is_explicit_and_retained_in_wiring(fault):
    import run_configured_red_player as script

    spec=dict(mode="defer_eight_badge_collection_until_hof_v1",
        reason="Current League-first work order")
    plan=dict(partition="development",league_first_collection_scope=spec)
    if fault == "partition":
        plan["partition"]="sealed"
    elif fault == "mode":
        spec["mode"]="force_champion_win"
    elif fault == "reason":
        spec["reason"]=""
    elif fault == "extra":
        spec["reset_money"]=True
    elif fault == "type":
        plan["league_first_collection_scope"]=True
    if fault:
        with pytest.raises(ValueError,match="DEVELOPMENT"):
            script.declared_league_first_collection_scope(plan)
    else:
        assert script.declared_league_first_collection_scope(plan)==spec
        assert script.player_wiring_declaration(plan)["league_first_collection_scope"]==spec
        assert script.declared_league_first_collection_scope({}) is None


def test_frozen_configured_entry_binds_new_history_to_its_actual_output(tmp_path, monkeypatch):
    import run_configured_red_player as script

    import pokemon_red_completion.red_player_package as package
    from pokemon_red_completion.red_player_configuration import RedPlayerConfiguration
    config = N(sha256="b"*64)
    plan = dict(partition="development", fit_allowed=False, copy_back=False,
        configuration={}, configuration_sha256=config.sha256, protected={},
        helpers_root=str(tmp_path), backend_module="unused", parent=str(tmp_path / "old"),
        runtime_package=dict(path="frozen-manifest", sha256="a"*64))
    path = tmp_path / "PLAN.json"
    path.write_text(json.dumps(plan))
    monkeypatch.setattr(RedPlayerConfiguration, "from_dict", lambda _: config)
    monkeypatch.setattr(script, "verify_pins", lambda _: None)
    monkeypatch.setattr(script, "declared_backend_sources", lambda _: {})
    monkeypatch.setattr(script, "verify_loaded_backend_sources", lambda *a: None)
    backend_c = N(digest=lambda _: None)
    monkeypatch.setattr(script.importlib, "import_module", lambda _: N(c=backend_c))
    monkeypatch.setattr(script.sys, "path", script.sys.path[:])
    called = []
    monkeypatch.setattr(package, "bind_player_package", lambda *a, **k:
        called.append((a,k)) or dict(source_commit="c"*40))
    def stop(*args):
        assert called == [(('frozen-manifest', 'a'*64), dict(history_output=tmp_path.resolve()))]
        assert backend_c.FROZEN_SOURCE_COMMIT == "c"*40
        raise RuntimeError("stop before any emulator")
    monkeypatch.setattr(script, "authenticate_parent", stop)
    with pytest.raises(RuntimeError, match="stop before any emulator"):
        script.run(N(plan=path))


@pytest.mark.parametrize("fault", [None, "empty", "partition", "relative", "outside",
    "entrypoint", "suffix", "digest", "bytes", "type"])
def test_declared_backend_sources_bind_bytes_before_import(tmp_path, fault):
    root = tmp_path / "helpers"
    root.mkdir()
    path = root / "backend.py"
    path.write_text("sentinel = 1\n")
    sources = {str(path): sha256(path.read_bytes()).hexdigest()}
    plan = dict(partition="development", helpers_root=str(root),
                backend_module="backend", backend_sources=sources)
    if fault == "empty":
        plan["backend_sources"] = {}
    elif fault == "partition":
        plan["partition"] = "sealed"
    elif fault == "relative":
        sources["backend.py"] = sources.pop(str(path))
    elif fault == "outside":
        sources[str(tmp_path / "outside.py")] = "a"*64
    elif fault == "entrypoint":
        plan["backend_module"] = "omitted"
    elif fault == "suffix":
        sources[str(root / "data.json")] = "a"*64
    elif fault == "digest":
        sources[str(path)] = "G"*64
    elif fault == "bytes":
        path.write_text("sentinel = 2\n")
    elif fault == "type":
        sources[str(path)] = True
    if fault:
        with pytest.raises(ValueError):
            declared_backend_sources(plan)
    else:
        assert declared_backend_sources(plan) == sources


def test_loaded_backend_aliases_use_source_path_and_missing_dependencies_fail(
    tmp_path, monkeypatch
):
    import run_configured_red_player as module

    source = tmp_path / "backend.py"
    source.write_text("sentinel = 1\n")
    sources = {str(source): sha256(source.read_bytes()).hexdigest()}
    monkeypatch.setitem(module.sys.modules, "declared_backend_alias", N(__file__=str(source)))
    verify_loaded_backend_sources(sources, tmp_path)
    other = tmp_path / "missing.py"
    other.write_text("sentinel = 2\n")
    monkeypatch.setitem(module.sys.modules, "undeclared_backend_dependency", N(__file__=str(other)))
    with pytest.raises(ValueError, match="not declared"):
        verify_loaded_backend_sources(sources, tmp_path)


def test_inspection_quotes_are_read_only_diagnostics_not_actions():
    forwarded = []
    actions = InspectionExecutor(N(execute=lambda _a: pytest.fail("no inputs"),
        record_diagnostic_event=lambda kind, payload: forwarded.append((kind, payload))))
    actions.record_diagnostic_event("capture_route_work_quote", {"active_trainers": 6})
    assert actions.actions_executed == 0
    assert actions.diagnostics == [
        dict(kind="capture_route_work_quote", payload={"active_trainers": 6})
    ]
    assert forwarded == [("capture_route_work_quote", {"active_trainers": 6})]


def test_inspection_restoration_port_quotes_but_cannot_execute():
    actions = InspectionExecutor(N(execute=lambda _a: pytest.fail("no inputs")))
    binding = N(execute=lambda: pytest.fail("inspection must not run a nurse"))
    assert callable(actions.execute_restoration)
    with pytest.raises(RuntimeError, match="zero-input inspection cannot execute restoration"):
        actions.execute_restoration(binding)
    assert actions.actions_executed == 0
    assert actions.diagnostics == []


@pytest.mark.parametrize("indigo", [False, True])
def test_inspection_can_quote_recoverable_preparation_without_inputs(monkeypatch, indigo):
    from test_red_player_preparation_binding import setup

    from pokemon_red_completion import red_player_preparation_binding as preparation
    from pokemon_red_completion.observation import MapId

    rt, _, kwargs, _ = setup(monkeypatch)
    if indigo:
        raw = rt.reader.read()
        raw.map_id = int(MapId.INDIGO_PLATEAU_LOBBY)
        raw.player_y = raw.player_x = 7
    actions = InspectionExecutor(N(execute=lambda _a: pytest.fail("no inputs")))
    binding = preparation.preparation_binding(
        rt, actions, maximum_battles=2, maximum_recoveries=1,
        include_indigo_lobby=indigo, **kwargs,
    )
    assert binding is not None
    assert actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize('explicit',[False,True])
def test_configured_chunks_are_explicit_and_never_reset_aggregate_costs(explicit):
    args=N(decisions=24,seconds=1800)
    if explicit:
        args.actions,args.frames=150000,15000000
    left=dict(decisions=17,actions=100000,frames=12000000,seconds=1600,heals=81)
    limits=configured_execution_limits(args,left,1500)
    assert (limits.decisions,limits.seconds,limits.heals,limits.cash_debits)==(17,1500,81,None)
    assert (limits.actions,limits.frames)==((100000,12000000) if explicit else (30000,2500000))


@pytest.mark.parametrize('name,value',[('actions',True),('frames',0),('seconds',-1),('decisions',1.5)])
def test_configured_chunks_reject_nonfinite_or_invalid_requests(name,value):
    args=N(decisions=24,actions=150000,frames=15000000,seconds=1800)
    setattr(args,name,value)
    with pytest.raises(ValueError,match='positive integer'):
        configured_execution_limits(args,dict(decisions=24,actions=150000,
            frames=15000000,seconds=1800,heals=81),1800)


def test_goal_model_default_keeps_original_loader_and_rejects_a_config_mismatch():
    model = N(model_sha256="a"*64)
    backend = N(d=N(prior=N(models=lambda: (model, object()))))
    configuration = N(goal_model_sha256=model.model_sha256)
    assert declared_goal_model({}, configuration, backend) is model
    with pytest.raises(ValueError, match="configured goal model differs"):
        declared_goal_model({}, N(goal_model_sha256="b"*64), backend)


@pytest.mark.parametrize("fault", [None, "partition", "bytes", "identity", "objective",
    "corpus", "reason", "extra", "type", "raw_model", "digest", "path"])
def test_stored_goal_model_uses_authenticated_record_without_calling_legacy_loader(tmp_path, fault):
    from test_red_live_option_menu import _model

    from pokemon_red_completion.registered_collection import REGISTERED_OBJECTIVE

    model = _model()
    document = dict(schema="pokemon.red.registered-player-model.v1",
        authority="bounded_development_only", objective=REGISTERED_OBJECTIVE,
        model=model.to_dict(), model_sha256=model.model_sha256,
        source_commit="1"*40, source_bundle_sha256="2"*64,
        corpus_sha256="3"*64, prior_model_sha256="4"*64,
        retained_example_sha256=[f"{i:064x}" for i in
            range(model.settled_examples+model.censored_examples)])
    if fault == "objective":
        document["objective"] = "wrong"
    if fault == "corpus":
        document["retained_example_sha256"] = []
    if fault == "raw_model":
        document = model.to_dict()
    path = tmp_path / "record.json"
    path.write_text(json.dumps(document))
    spec = dict(path=str(path), content_sha256=sha256(path.read_bytes()).hexdigest(),
                reason="A useful retained student capture, not an official promotion.")
    if fault == "bytes":
        path.write_text("{}")
    if fault == "reason":
        spec["reason"] = " "
    if fault == "extra":
        spec["force_kind"] = "capture"
    if fault == "type":
        spec = True
    if fault == "digest":
        spec["content_sha256"] = "G"*64
    if fault == "path":
        spec["path"] = " "
    plan = dict(partition="sealed" if fault == "partition" else "development",
                goal_model_record=spec)
    backend = N(d=N(prior=N(models=lambda: pytest.fail("must not load hardcoded parent"))))
    configuration = N(goal_model_sha256="b"*64 if fault == "identity" else model.model_sha256)
    if fault:
        with pytest.raises(ValueError):
            declared_goal_model(plan, configuration, backend)
    else:
        child = declared_goal_model(plan, configuration, backend)
        assert child.to_dict() == model.to_dict()


@pytest.mark.parametrize("badge", [0, 255])
@pytest.mark.parametrize("previous", [False, True])
def test_owned_tm_connection_preserves_field_dependency_observer(monkeypatch, badge, previous):
    import run_configured_red_player as module
    calls = []
    rt = N(reader=N(read=lambda: N(badge_bits=badge)))
    menu = N(enumerate_owned_machines=(
        (lambda *_: calls.append("field") or ("fly",)) if previous else None))
    monkeypatch.setattr(module, "owned_machine_options",
                        lambda *_a, **_kw: calls.append("tm") or ("tm",))
    connect_owned_machine_options(menu, rom=b"fixture")
    assert menu.enumerate_owned_machines(rt, None, None) == (
        (("fly",) if previous else ()) + (("tm",) if badge == 255 else ()))
    assert calls == (["field"] if previous else []) + (["tm"] if badge == 255 else [])


def test_owned_machine_options_are_default_off():
    assert declared_owned_machine_options({}) is False


@pytest.mark.parametrize("fault", [None, "partition", "mode", "reason", "extra", "type"])
def test_machine_options_require_a_prospective_development_declaration(fault):
    spec = dict(mode="direct_attack_capacity_v1",
                reason="Owned capacity lessons, not manual teaching.")
    plan = dict(partition="development", owned_machine_options=spec)
    if fault == "partition":
        plan["partition"] = "sealed"
    elif fault == "mode":
        spec["mode"] = "force_bubblebeam"
    elif fault == "reason":
        spec["reason"] = ""
    elif fault == "extra":
        spec["recipient"] = 1
    elif fault == "type":
        plan["owned_machine_options"] = True
    if fault:
        with pytest.raises(ValueError, match="ordinary DEVELOPMENT"):
            declared_owned_machine_options(plan)
    else:
        assert declared_owned_machine_options(plan) is True


@pytest.mark.parametrize("start,ready,expected", [(True, True, False),
    (True, False, False), (False, True, False), (False, False, True)])
def test_start_menu_does_not_defer_head_for_a_nonexistent_battle_preface(start, ready, expected):
    rt = N(reader=N(read=lambda: N(game_started=True, battle_state=0),
        read_input_readiness=lambda: N(ready=ready),
        read_overworld_start_menu_visible=lambda: start,
        read_bottom_dialogue_box_visible=lambda: False), emulator=N(pressed_buttons=()))
    assert requires_compulsory_settlement(rt) is expected


def test_existing_greedy_selection_remains_the_default():
    assert declared_greedy_selection({}) is True


@pytest.mark.parametrize("mix", [0, 0.25, 0.75, 1])
def test_declared_development_exploration_forwards_existing_sampler_knob(mix, monkeypatch):
    import run_configured_red_player as script

    plan = dict(partition="development", goal_selection=dict(
        mode="exploration", reason="Target-neutral kind exploration.", exploration_mix=mix))
    assert script.declared_exploration_mix(plan) == mix
    assert not declared_greedy_selection(plan)
    monkeypatch.setattr(script, "requires_compulsory_settlement", lambda _: False)
    monkeypatch.setattr(script, "declared_player_curriculum", lambda *_: None)
    options = script.native_player_options(plan, object(), [object()],
        N(native_callbacks=lambda: {}), refinement={})
    assert options["exploration_mix"] == mix
    assert options["greedy_selection"] is False
    assert script.declared_exploration_mix({}) == 0.25


@pytest.mark.parametrize("mix", [True, None, "0.75", -0.1, 1.1,
                                  float("nan"), float("inf")])
def test_invalid_exploration_mix_is_rejected_before_launch(mix):
    from run_configured_red_player import declared_exploration_mix

    with pytest.raises(ValueError, match="custom exploration"):
        declared_exploration_mix(dict(partition="development", goal_selection=dict(
            mode="exploration", reason="Declared test.", exploration_mix=mix)))


@pytest.mark.parametrize("fault", ["greedy", "refinement", "evaluation"])
def test_custom_exploration_cannot_expand_other_policy_scopes(fault):
    from run_configured_red_player import declared_exploration_mix

    plan = dict(partition="development", goal_selection=dict(
        mode="exploration", reason="Declared test.", exploration_mix=0.75))
    if fault == "greedy":
        plan["goal_selection"]["mode"] = "greedy"
    elif fault == "refinement":
        plan["readiness_refinement"] = {}
    else:
        plan["partition"] = "evaluation"
    with pytest.raises(ValueError, match="DEVELOPMENT"):
        declared_exploration_mix(plan)


def test_input_recording_keeps_original_probe_by_default():
    assert declared_input_recording({}) == {}


@pytest.mark.parametrize('key,value', [
    ('native_input_storage', 'sample'), ('native_input_storage', True),
    ('isolation_report', 'counts_only'), ('isolation_report', True),
])
def test_recording_declaration_rejects_lossy_or_unknown_formats(key, value):
    spec = dict(git_worktree_probe='gitless_fast_path_v1', reason='Preserve complete evidence.',
                native_input_storage='flat_sealed_v1', isolation_report='gzip_json_v1')
    spec[key] = value
    with pytest.raises(ValueError, match='ordinary DEVELOPMENT'):
        declared_input_recording(dict(partition='development', input_recording=spec))


def test_compact_recording_only_forwards_the_store_option():
    spec = dict(git_worktree_probe='gitless_fast_path_v1', reason='Preserve complete evidence.',
                native_input_storage='flat_sealed_v1', isolation_report='gzip_json_v1')
    options = declared_input_recording(dict(partition='development', input_recording=spec))
    assert options['native_input_storage'] == 'flat_sealed_v1'
    assert 'isolation_report' not in options


@pytest.mark.parametrize("fault", [None, "mode", "reason", "partition", "extra", "type"])
def test_fast_input_recording_requires_development_declaration(fault):
    from pokemon_red_completion.private_artifacts import gitless_fast_path_worktree_probe

    spec = dict(
        git_worktree_probe="gitless_fast_path_v1",
        reason="Measured per-input subprocess overhead.",
    )
    plan = dict(partition="development", input_recording=spec)
    if fault == "mode":
        spec["git_worktree_probe"] = "disable_checks"
    elif fault == "reason":
        spec["reason"] = " "
    elif fault == "partition":
        plan["partition"] = "sealed"
    elif fault == "extra":
        spec["skip_durability"] = True
    elif fault == "type":
        plan["input_recording"] = []
    if fault:
        with pytest.raises(ValueError, match="ordinary DEVELOPMENT"):
            declared_input_recording(plan)
    else:
        assert declared_input_recording(plan) == dict(
            git_worktree_probe=gitless_fast_path_worktree_probe,
        )


@pytest.mark.parametrize("mode,expected", [("greedy", True), ("exploration", False)])
def test_existing_goal_selection_requires_a_declared_development_mode(mode, expected):
    assert declared_greedy_selection(dict(
        partition="development", goal_selection=dict(mode=mode, reason="Bounded policy reuse.")
    )) is expected


@pytest.mark.parametrize("fault", ["mode", "reason", "extra", "partition", "type"])
def test_selection_declaration_refuses_undeclared_or_evaluation_changes(fault):
    spec = dict(mode="exploration", reason="Bounded policy reuse.")
    plan = dict(partition="development", goal_selection=spec)
    if fault == "mode":
        spec["mode"] = "forced_pp_pickup"
    elif fault == "reason":
        spec["reason"] = " "
    elif fault == "extra":
        spec["forced_kind"] = "resupply"
    elif fault == "partition":
        plan["partition"] = "sealed"
    elif fault == "type":
        plan["goal_selection"] = []
    with pytest.raises(ValueError, match="ordinary DEVELOPMENT"):
        declared_greedy_selection(plan)


@pytest.mark.parametrize("mode", [None, [], {}, 0, True])
def test_selection_declaration_rejects_nonstring_modes(mode):
    with pytest.raises(ValueError, match="ordinary DEVELOPMENT"):
        declared_greedy_selection(dict(
            partition="development", goal_selection=dict(mode=mode, reason="Bounded reuse.")
        ))


def test_preparation_component_is_default_off():
    assert declared_preparation_component({}) is None


@pytest.mark.parametrize("fault", [None, "bytes", "reason", "extra", "type"])
def test_preparation_component_carries_only_exact_declared_bytes(tmp_path, fault):
    path = tmp_path / "battler.json"
    path.write_bytes(b"native-train-component")
    spec = dict(
        path=str(path),
        sha256=sha256(path.read_bytes()).hexdigest(),
        reason="One verified wild preparation copy; provisional reuse only.",
    )
    if fault == "bytes":
        spec["sha256"] = "0" * 64
    elif fault == "reason":
        spec["reason"] = " "
    elif fault == "extra":
        spec["forced_target"] = 100
    elif fault == "type":
        spec = []
    if fault:
        with pytest.raises(ValueError):
            declared_preparation_component(dict(preparation_battle_component=spec))
    else:
        result = declared_preparation_component(dict(preparation_battle_component=spec))
        assert result == spec and result is not spec


def test_readiness_refinement_is_default_off():
    assert declared_readiness_refinement(dict(objectives=["cross_victory_road"])) == {}


@pytest.mark.parametrize("fault", [None, "false", "type", "partition", "exploration"])
def test_preparation_refinement_requires_declared_greedy_development(tmp_path, fault):
    from test_red_consequence_choice import progress_head

    head = progress_head()
    path = tmp_path / "head.json"
    payload = json.dumps(head.document()).encode()
    path.write_bytes(payload)
    spec = dict(objective_ref="defeat_lorelei", head_path=str(path),
                head_sha256=head.model_sha256, content_sha256=sha256(payload).hexdigest(),
                reason="Refine observed preparation without replacing parent recovery.",
                refine_preparation=True)
    plan = dict(partition="development", objectives=["defeat_lorelei"],
                goal_selection=dict(mode="greedy", reason="Bounded copied development."),
                readiness_refinement=spec)
    if fault == "false":
        spec["refine_preparation"] = False
    elif fault == "type":
        spec["refine_preparation"] = 1
    elif fault == "partition":
        plan["partition"] = "train"
    elif fault == "exploration":
        plan["goal_selection"]["mode"] = "exploration"
    if fault in {"type", "partition", "exploration"}:
        with pytest.raises(ValueError):
            declared_readiness_refinement(plan)
    else:
        result = declared_readiness_refinement(plan)
        assert result.get("refine_preparation", False) is (fault != "false")
        assert ("refine_preparation" in result) is (fault != "false")
        assert result["consequence_head"].model_sha256 == head.model_sha256


@pytest.mark.parametrize("explore", [False, True])
@pytest.mark.parametrize("fault", [None, "bytes", "identity", "objective", "reason", "synthetic"])
def test_readiness_reuse_requires_exact_declared_native_train_head(tmp_path, fault, explore):
    from dataclasses import replace

    from test_red_consequence_choice import progress_head

    head = progress_head()
    if fault == "synthetic":
        head = replace(head, provenance="synthetic")
    path = tmp_path / "head.json"
    payload = json.dumps(head.document()).encode()
    path.write_bytes(payload)
    spec = dict(
        objective_ref="cross_victory_road",
        head_path=str(path),
        head_sha256=head.model_sha256,
        content_sha256=sha256(payload).hexdigest(),
        reason="Explicit adaptive reuse; no fit or broad qualification.",
    )
    if fault == "bytes":
        spec["content_sha256"] = "0" * 64
    if fault == "identity":
        spec["head_sha256"] = "0" * 64
    if fault == "objective":
        spec["objective_ref"] = "defeat_lorelei"
    if fault == "reason":
        spec["reason"] = " "
    plan = dict(objectives=["cross_victory_road"], readiness_refinement=spec)
    if explore:
        plan.update(partition="development",
                    goal_selection=dict(mode="exploration", reason="Bounded policy reuse."))
    if fault:
        with pytest.raises(ValueError):
            declared_readiness_refinement(plan)
    else:
        options = declared_readiness_refinement(plan)
        assert options["consequence_head"].model_sha256 == head.model_sha256
        assert options["consequence_objective_ref"] == "cross_victory_road"
        assert options["allow_greedy_branch_recovery"] is (not explore)


@pytest.mark.parametrize("fault", [None, "duplicate", "order", "unknown", "both",
                                  "exploration", "partition", "list_type"])
def test_readiness_reuse_can_bind_multiple_known_declared_branches(tmp_path, fault):
    from test_red_consequence_choice import progress_head

    from pokemon_red_completion.red_consequence_choice import branch_recovery_scope_ref

    head = progress_head()
    path = tmp_path / "head.json"
    payload = json.dumps(head.document()).encode()
    path.write_bytes(payload)
    spec = dict(objective_refs=["defeat_misty", "help_bill"], head_path=str(path),
                head_sha256=head.model_sha256, content_sha256=sha256(payload).hexdigest(),
                reason="Keep readiness attached when the parent changes its chosen battle.")
    plan = dict(partition="development", objectives=["defeat_misty", "help_bill"],
                goal_selection=dict(mode="greedy", reason="Declared retained-save test."),
                readiness_refinement=spec)
    if fault == "duplicate":
        spec["objective_refs"] = ["help_bill", "help_bill"]
    elif fault == "order":
        spec["objective_refs"].reverse()
    elif fault == "unknown":
        spec["objective_refs"] = ["defeat_lorelei", "help_bill"]
    elif fault == "both":
        spec["objective_ref"] = "help_bill"
    elif fault == "exploration":
        plan["goal_selection"]["mode"] = "exploration"
    elif fault == "partition":
        plan["partition"] = "train"
    elif fault == "list_type":
        spec["objective_refs"] = tuple(spec["objective_refs"])
    if fault:
        with pytest.raises(ValueError):
            declared_readiness_refinement(plan)
    else:
        result = declared_readiness_refinement(plan)
        scope = ("defeat_misty", "help_bill")
        assert result["consequence_objective_ref"] == scope
        assert result["consequence_challenge_ref"] == branch_recovery_scope_ref(scope)
        assert result["allow_greedy_branch_recovery"] is True
        assert result["consequence_head"].model_sha256 == head.model_sha256


def test_full_save_order_reuses_registered_species_curriculum():
    from pokemon_red_completion.red_player_curriculum import NativeResourceCurriculum

    curriculum = declared_player_curriculum(
        dict(
            objectives=["enter_hall_of_fame"],
            required_species=["pokemon:national:007", "pokemon:national:009"],
        ),
        "original-combat-member",
    )
    assert isinstance(curriculum, NativeResourceCurriculum)
    assert curriculum.required_species == ("pokemon:national:007", "pokemon:national:009")
    assert curriculum.target_levels == (("original-combat-member", 1),)


def test_old_story_order_keeps_its_original_completion_contract():
    from pokemon_red_completion.red_player_curriculum import NativePlayerCurriculum

    curriculum = declared_player_curriculum(
        dict(objectives=["defeat_giovanni"]), "original-combat-member"
    )
    assert type(curriculum) is NativePlayerCurriculum
    assert curriculum.objectives == ("defeat_giovanni",)


@pytest.mark.parametrize("with_species", [False, True])
def test_resource_order_reuses_physical_stock_curriculum(with_species):
    from pokemon_red_completion.red_player_curriculum import NativeResourceCurriculum

    plan = dict(objectives=["rescue_fuji"], required_stock=[[48, 1], [73, 1]])
    if with_species:
        plan["required_species"] = ["pokemon:national:007"]
    curriculum = declared_player_curriculum(plan, "original-combat-member")
    assert isinstance(curriculum, NativeResourceCurriculum)
    assert curriculum.required_stock == ((48, 1), (73, 1))
    assert curriculum.required_species == (
        ("pokemon:national:007",) if with_species else ()
    )
    assert curriculum.objectives == ("rescue_fuji",)
    assert curriculum.target_levels == (("original-combat-member", 1),)


@pytest.mark.parametrize("stock", [
    [], (), None, "card_key", [[48]], [[48, 1, 2]], [(48, 1)],
    [[48, 1], [48, 1]], [[0, 1]], [[256, 1]], [[48, 0]], [[48, 100]],
    [[True, 1]], [[48, True]], [[48, "1"]],
])
def test_resource_order_rejects_invalid_or_ambiguous_physical_stock(stock):
    with pytest.raises(ValueError):
        declared_player_curriculum(
            dict(objectives=["rescue_fuji"], required_stock=stock), "original"
        )


@pytest.mark.parametrize("species", [[], (), None, "pokemon:national:007", ["x", "x"]])
def test_full_save_order_does_not_silently_drop_invalid_collection_targets(species):
    with pytest.raises(ValueError):
        declared_player_curriculum(
            dict(objectives=["enter_hall_of_fame"], required_species=species), "original"
        )


def test_resume_keeps_lifetime_costs_and_does_not_renew_allowance():
    baseline = dict(decisions=842, actions=138872, frames=10724154, seconds=20917.5, heals=140)
    allowance = dict(decisions=2000, actions=400000, frames=32000000, seconds=9000, heals=100000)
    current = {key: value + 10 for key, value in baseline.items()}
    assert remaining_allowance(current, baseline, allowance) == {
        k: v - 10 for k, v in allowance.items()
    }
    current["actions"] -= 11
    with pytest.raises(ValueError, match="lost costs"):
        remaining_allowance(current, baseline, allowance)


@pytest.mark.parametrize("outer", [False, True])
@pytest.mark.parametrize("message,expected", [
    ("controller exhausted its hard frame budget", "automatic_budget_recovery"),
    ("controller frame_count is invalid", "native_execution_error"),
    ("other frame failure", "native_execution_error"),
    (None, "native_execution_error"),
])
def test_aggregate_frame_checkpoint_requires_the_actual_budget_message(outer, message, expected):
    from run_configured_red_player import chunk_continuation_reason

    error = dict(error_type="ControllerFrameBudgetError", error=message)
    result = dict(released=True, state_sha256="b" * 64,
        chunk_costs=dict(actions_attempted=1, frames=16),
        episode=dict(stop_reason="unsafe_terminal", outcomes=[] if outer else [error]))
    if outer:
        result.update(error)
    assert chunk_continuation_reason(result, source_sha256="a" * 64) == expected


def test_admission_error_is_retained_before_the_no_progress_classification():
    from run_configured_red_player import chunk_continuation_reason
    result = dict(released=True, state_sha256="a" * 64,
                  episode=dict(admission_failure=dict(error_type="ValueError", error="")),
                  chunk_costs=dict(actions_attempted=0, frames=0))
    assert chunk_continuation_reason(result, source_sha256="a" * 64) == "native_admission_error"


def test_diagnostic_costs_remain_separate_and_include_failed_attempts(tmp_path):
    for ordinal, (passed, actions, frames, seconds) in enumerate(
        ((False, 0, 0, 1.13), (True, 121, 7536, 12.40))
    ):
        node = tmp_path / "diagnostics" / f"loan-{ordinal}"
        node.mkdir(parents=True)
        (node / "RESULT.json").write_text(
            json.dumps(
                dict(
                    passed=passed,
                    worker_stopped=True,
                    released=True,
                    copy_back=False,
                    actions=actions,
                    frames=frames,
                    seconds=seconds,
                )
            )
        )
    spent = diagnostic_spending(tmp_path)
    assert spent == dict(
        decisions=2, actions=121, frames=7536, seconds=pytest.approx(13.53), heals=0
    )


def test_incomplete_diagnostic_must_not_reset_consumed_allowance(tmp_path):
    (tmp_path / "diagnostics" / "loan-interrupted").mkdir(parents=True)
    with pytest.raises(ValueError, match="reconcile before resuming"):
        diagnostic_spending(tmp_path)


def test_diagnostic_counts_inner_nursing_including_a_failed_copy(tmp_path):
    node = tmp_path / "diagnostics" / "evolution-failed"
    node.mkdir(parents=True)
    (node / "RESULT.json").write_text(
        json.dumps(
            dict(
                passed=False,
                worker_stopped=True,
                released=True,
                copy_back=False,
                actions=42,
                frames=2560,
                seconds=12.5,
                heals=3,
            )
        )
    )
    assert diagnostic_spending(tmp_path) == dict(
        decisions=1,
        actions=42,
        frames=2560,
        seconds=12.5,
        heals=3,
    )


def test_evolution_diagnostic_uses_a_real_boxed_unquarantined_alternative():
    from pokemon_red_completion.collection import CollectionLocation
    from pokemon_red_completion.goal_manager import GoalKind

    observation = N(
        collection_observation=N(
            specimens=(
                N(species_ref="boxed", location=CollectionLocation.BOX),
                N(species_ref="party", location=CollectionLocation.PARTY),
            )
        )
    )

    def option(source, effort, admitted=True):
        return N(
            execution_effort=effort,
            binding=N(binding_ref=str(effort), admitted=admitted),
            profile=N(
                providers=(
                    N(kind=GoalKind.EVOLVE_SPECIES, parameters={"source_species_ref": source}),
                )
            ),
        )

    expected = option("boxed", 0.3)
    configuration = N(admits=lambda binding: binding.admitted)
    alternatives = (option("party", 0.9), option("boxed", 0.8, False), expected)
    assert evolution_copy_choice(alternatives, observation, configuration)[0] is expected
    assert evolution_copy_choice(alternatives[:2], observation, configuration)[0] is alternatives[0]
    with pytest.raises(ValueError, match="no admitted level"):
        evolution_copy_choice(alternatives[1:2], observation, configuration)


@pytest.mark.parametrize("pp,restored", [(35, True), (34, False)])
def test_native_reward_inspection_reads_cartridge_facts_and_exact_pp(pp, restored):
    raw = N(
        badge_bits=0x7F,
        event_flags=b"\x01\x80",
        bag_items=((1, 1), (246, 1)),
        player_money=13342,
        party_levels=(37,),
        party_hp=(100,),
        party_max_hp=(100,),
        party_status=(0,),
        party_moves=((33, 0, 0, 0),),
        party_pp=((pp, 0, 0, 0),),
    )
    runtime = N(reader=N(read=lambda: raw, read_pokedex_state=lambda: N(owned_species={1, 2, 3})))
    facts = native_checkpoint_facts(runtime)
    assert facts == dict(
        badge_bits=0x7F,
        badges=7,
        event_flags_hex="0180",
        bag_stock=((1, 1), (246, 1)),
        registrations=3,
        cash=13342,
        party_levels=(37,),
        whole_party_restored=restored,
    )


@pytest.mark.parametrize("fault", [None, "terminal", "context", "costs", "running", "buttons"])
def test_resume_authenticates_source_and_context_before_player_input(tmp_path, fault):
    payload = b"authenticated native terminal"
    (tmp_path / "terminal.state").write_bytes(payload)
    context = dict(state_sha256=sha256(payload).hexdigest(), spent={"actions": 17})
    data = json.dumps(context).encode()
    (tmp_path / "CONTEXT.json").write_bytes(data)
    result = dict(
        state_sha256=context["state_sha256"],
        context_sha256=sha256(data).hexdigest(),
        spent=context["spent"],
        worker_stopped=True,
        released=True,
    )
    if fault == "terminal":
        result["state_sha256"] = "0" * 64
    elif fault == "context":
        result["context_sha256"] = "0" * 64
    elif fault == "costs":
        result["spent"] = {"actions": 0}
    elif fault == "running":
        result["worker_stopped"] = False
    elif fault == "buttons":
        result["released"] = False
    (tmp_path / "RESULT.json").write_text(json.dumps(result))
    if fault:
        with pytest.raises(ValueError, match="authenticated stopped checkpoint"):
            authenticate_parent(tmp_path, lambda p: sha256(p.read_bytes()).hexdigest())
    else:
        assert (
            authenticate_parent(tmp_path, lambda p: sha256(p.read_bytes()).hexdigest()) == context
        )


@pytest.mark.parametrize("accepted", [False, True])
def test_shared_menu_handoff_delegates_to_exact_guard_without_inputs(monkeypatch, accepted):
    import run_configured_red_player as script

    emulator = N(frame_count=0, pressed_buttons=set(), save_state_bytes=lambda: b"unchanged")
    observation, inventory = object(), object()
    runtime = N(emulator=emulator, adapter=N(observe=lambda: observation))
    inspections = []

    def enumerate_base(rt, actions, observed):
        assert rt is runtime and observed is observation
        assert actions.actions_executed == 0
        inspections.append(True)
        return inventory

    result = {"unchanged_failure": True}
    receipt = {"qualified": True} if accepted else None

    def exact_guard(row, *, runtime, inspect_bindings):
        assert row is result
        if accepted:
            assert inspect_bindings() is inventory
        return receipt

    monkeypatch.setattr(script, "qualified_native_control_handoff", exact_guard)
    assert script.qualified_menu_control_handoff(
        result, runtime=runtime, menu=N(enumerate_base=enumerate_base)
    ) is receipt
    assert result == {"unchanged_failure": True}
    assert inspections == ([True] if accepted else [])
    assert emulator.frame_count == 0 and not emulator.pressed_buttons


@pytest.mark.parametrize("decisions", [0, 4, -1, True, 1.5])
def test_diagnostic_uses_retained_goal_count_without_resetting_failed_copy(tmp_path, decisions):
    node = tmp_path / "diagnostics" / "retained-failed-copy"
    node.mkdir(parents=True)
    (node / "RESULT.json").write_text(json.dumps(dict(
        passed=False, worker_stopped=True, released=True, copy_back=False,
        decisions=decisions, actions=1319, frames=83748, seconds=32.7, heals=1,
    )))
    if type(decisions) is int and decisions >= 0:
        assert diagnostic_spending(tmp_path) == dict(
            decisions=decisions, actions=1319, frames=83748, seconds=32.7, heals=1,
        )
    else:
        with pytest.raises(ValueError, match="decision costs"):
            diagnostic_spending(tmp_path)
