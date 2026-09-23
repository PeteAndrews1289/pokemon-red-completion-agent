import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_faint_recovery import fixture
from test_red_live_option_menu import _model

import pokemon_red_completion.red_recovery_intermission as module
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)


def setup(monkeypatch, tmp_path, *, select="advance_story"):
    recovery, reader, calls = fixture(monkeypatch)
    reader.raw = replace(reader.raw, player_money=3175)
    model = _model()
    advance_calls = []
    next_binding = ExecutableGoalBinding(
        "test-next",
        GoalKind.ADVANCE_STORY,
        0.3,
        0.1,
        lambda: (advance_calls.append(True), GoalExecutionReport(1, 1, {}))[1],
        lambda _: GoalVerification.succeeded(),
    )
    queries = []

    def choose(model, options, **kwargs):
        assert not advance_calls
        queries.append(options)
        index = next(i for i, b in enumerate(options.bindings) if b.kind.value == select)
        return SimpleNamespace(
            selected_candidate_index=index,
            public_dict=lambda: {"mode": "test-only-selection", "selected_candidate_index": index},
        )

    monkeypatch.setattr(module, "select_red_live_option", choose)
    params = dict(
        model=model,
        model_sha256=model.model_sha256,
        output=tmp_path / "run",
        recovery=recovery,
        next_goal=lambda _: next_binding,
        snapshot=lambda: json.dumps(
            {"hp": reader.raw.party_hp, "bag": reader.raw.bag_items}
        ).encode(),
        seed=12,
        maximum_items=2,
        target_cash=10000,
    )
    return params, reader, calls, advance_calls, queries, next_binding


def test_selected_next_returned_without_executing_or_healing(monkeypatch, tmp_path):
    params, reader, calls, advance, queries, binding = setup(monkeypatch, tmp_path)
    assert module.run_recovery_intermission(**params) is binding
    assert len(queries) == 1 and not calls and not advance
    assert (params["output"] / "step-00/selection.json").exists()
    assert (params["output"] / "terminal.state").read_bytes() == params["snapshot"]()
    with pytest.raises(FileExistsError):
        module.run_recovery_intermission(**params)


def test_selected_recovery_executes_once_then_rebuilds_actual_menu(monkeypatch, tmp_path):
    params, reader, calls, advance, queries, binding = setup(
        monkeypatch, tmp_path, select="restore_team"
    )
    params["maximum_items"] = 1
    with pytest.raises(module.RecoveryIntermissionError, match="budget exhausted"):
        module.run_recovery_intermission(**params)
    assert reader.raw.party_hp == (100, 50) and len(calls) == 3 and len(queries) == 1
    assert not advance
    report = json.loads((params["output"] / "step-00/outcome.json").read_bytes())
    assert report["verification"]["status"] == "succeeded"
    assert json.loads((params["output"] / "terminal.json").read_bytes())["verified_items"] == 1


def test_no_fake_competitor_or_singleton_learning(monkeypatch, tmp_path):
    params, reader, calls, advance, queries, _ = setup(monkeypatch, tmp_path)
    params["next_goal"] = lambda _: None
    with pytest.raises(module.RecoveryIntermissionError, match="competing"):
        module.run_recovery_intermission(**params)
    assert not calls and not queries


def test_no_recovery_stock_returns_unlearned_singleton(monkeypatch, tmp_path):
    params, reader, calls, advance, queries, binding = setup(monkeypatch, tmp_path)
    reader.raw = replace(reader.raw, bag_items=(), bag_item_ids=())
    assert module.run_recovery_intermission(**params) is binding
    assert not queries and not calls and not advance
    assert (
        json.loads((params["output"] / "step-00/selection.json").read_bytes())["model_queries"] == 0
    )


def test_observation_side_effect_stops_before_scoring(monkeypatch, tmp_path):
    params, reader, calls, advance, queries, binding = setup(monkeypatch, tmp_path)

    def mutate(_):
        reader.raw = replace(reader.raw, party_hp=(99, 0))
        return binding

    params["next_goal"] = mutate
    with pytest.raises(module.RecoveryIntermissionError, match="enumeration changed"):
        module.run_recovery_intermission(**params)
    assert not queries and not calls


def test_real_frozen_scorer_and_policy_mode_are_retained(monkeypatch, tmp_path):
    real = module.select_red_live_option
    params, reader, calls, advance, queries, binding = setup(monkeypatch, tmp_path)
    monkeypatch.setattr(module, "select_red_live_option", real)
    params["maximum_items"] = 1
    try:
        assert module.run_recovery_intermission(**params) is binding
    except module.RecoveryIntermissionError as error:
        assert "budget exhausted" in str(error)
    choice = json.loads((params["output"] / "step-00/selection.json").read_bytes())
    assert choice["model_sha256"] == params["model_sha256"]
    assert choice["mode"] in {"model_exploration", "equivalent_exploration", "deterministic_safety"}
    assert not advance


def test_missing_cash_stops_without_query_or_item_use(monkeypatch, tmp_path):
    params, reader, calls, advance, queries, _ = setup(monkeypatch, tmp_path)
    reader.raw = replace(reader.raw, player_money=None)
    with pytest.raises(module.RecoveryIntermissionError, match="observed cash"):
        module.run_recovery_intermission(**params)
    assert not queries and not calls and not advance


def test_economy_context_and_mechanic_are_actual_not_a_full_heal(monkeypatch, tmp_path):
    params, reader, calls, advance, queries, binding = setup(monkeypatch, tmp_path)
    module.run_recovery_intermission(**params)
    assert queries[0].menu.context.economy_snapshot.cash == 3175
    assert queries[0].menu.context.target_cash == 10000
    choice = json.loads((params["output"] / "step-00/selection.json").read_bytes())
    assert choice["recovery_mechanic"]["expected_hp"] == 50
    assert choice["recovery_mechanic"]["party_index"] == 1
    assert choice["replacement_cost_qualified"] is False


def test_selection_mutation_never_executes_either_goal(monkeypatch, tmp_path):
    params, reader, calls, advance, queries, binding = setup(monkeypatch, tmp_path)
    old_select = module.select_red_live_option

    def mutate(*args, **kwargs):
        choice = old_select(*args, **kwargs)
        reader.raw = replace(reader.raw, party_hp=(99, 0))
        return choice

    monkeypatch.setattr(module, "select_red_live_option", mutate)
    with pytest.raises(module.RecoveryIntermissionError, match="selection changed"):
        module.run_recovery_intermission(**params)
    assert not calls and not advance


@pytest.mark.parametrize(
    "change",
    [
        {"maximum_items": True},
        {"maximum_items": 13},
        {"seed": -1},
        {"model_sha256": "bad"},
        {"target_cash": True},
        {"target_cash": -1},
    ],
)
def test_bad_identity_or_budget_fails_before_output(monkeypatch, tmp_path, change):
    params, *_ = setup(monkeypatch, tmp_path)
    with pytest.raises(module.RecoveryIntermissionError):
        module.run_recovery_intermission(**(params | change))
    assert not params["output"].exists()
