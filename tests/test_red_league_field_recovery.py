import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_faint_recovery import fixture
from test_red_live_option_menu import _model

import pokemon_red_completion.red_league_funding_execution as execution
import pokemon_red_completion.red_recovery_intermission as intermission
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.red_league_field_recovery import LeagueFieldRecovery
from pokemon_red_completion.red_learned_league import FrozenLeagueController
from pokemon_red_completion.red_learned_trainer import FROZEN_K_SHA256, K_QUALIFICATION_SHA256


def setup(monkeypatch, tmp_path, *, maximum=2):
    provider, reader, calls = fixture(monkeypatch)
    reader.raw = replace(reader.raw, player_money=3175)
    model = _model()
    session = LeagueFieldRecovery(
        model,
        model.model_sha256,
        tmp_path / "recovery",
        lambda: json.dumps({"hp": reader.raw.party_hp, "bag": reader.raw.bag_items}).encode(),
        10000,
        maximum_items=maximum,
    )
    actor = FrozenLeagueController(
        SimpleNamespace(model_sha256=FROZEN_K_SHA256, qualification_sha256=K_QUALIFICATION_SHA256),
        "league-profit-recovery-v1",
        field_recovery=session,
    )
    runtime = SimpleNamespace(
        adapter=provider.adapter,
        reader=reader,
        emulator=provider.emulator,
        league_battle_controller=actor,
    )
    return provider, reader, calls, session, runtime


def test_next_trainer_uses_real_binding_after_recovery_on_same_executor(monkeypatch, tmp_path):
    provider, reader, calls, session, runtime = setup(monkeypatch, tmp_path)
    session.claim()
    menus = []

    def choose(model, options, **kwargs):
        menus.append(options)
        kind = "restore_team" if len(menus) == 1 else "resupply"
        index = next(i for i, b in enumerate(options.bindings) if b.kind.value == kind)
        return SimpleNamespace(
            selected_candidate_index=index, public_dict=lambda: {"mode": "test-only-selection"}
        )

    monkeypatch.setattr(intermission, "select_red_live_option", choose)
    starts = []

    class Skill:
        def __init__(self, given_runtime, actions, world, **kwargs):
            assert actions is provider.actions and given_runtime is runtime

        def availability(self, state):
            return SimpleNamespace(executable=True)

        def execute(self):
            starts.append(reader.raw.party_hp)
            assert len(menus) == 2 and reader.raw.party_hp == (100, 50)
            reader.raw = replace(reader.raw, player_money=3375)
            return GoalExecutionReport(0, 0, {"bag_items_spent": 0})

    monkeypatch.setattr(execution, "RedCartridgeLoreleiSkill", Skill)
    result = execution._run_battle(
        runtime, provider.actions, object(), "defeat_bruno", 200, "frozen-k-development", 0
    )
    assert starts == [(100, 50)] and result.money_after == 3375
    assert result.actions == 0 and provider.actions.actions_executed == 3
    assert session.consumed == {53: 1} and session.replacement_cost == 1500
    assert session.expected_bag(((53, 2), (18, 1)), 0) == ((53, 1), (18, 1))
    for menu in menus:
        income = next(b for b in menu.bindings if b.kind.value == "resupply")
        assert income.resource_quote.expected_income == 200
        assert income.resource_quote.available_funds == 3175


def test_budget_shared_across_boundaries_and_failure_closes_campaign(monkeypatch, tmp_path):
    provider, reader, calls, session, runtime = setup(monkeypatch, tmp_path, maximum=1)
    session.claim()
    session._accept(GoalExecutionReport(1, 1, {"item_id": 53, "owned_items_consumed": 1}))
    from pokemon_red_completion.goal_manager import GoalKind
    from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding, GoalVerification

    next_binding = ExecutableGoalBinding(
        "next",
        GoalKind.RESUPPLY,
        0.5,
        0.5,
        lambda: pytest.fail("battle after budget exhausted"),
        lambda _: GoalVerification.succeeded(),
    )
    with pytest.raises(ValueError, match="budget exhausted"):
        session.choose(provider, lambda _: next_binding)
    assert session.failed and not calls
    with pytest.raises(ValueError, match="not active"):
        session.choose(provider, lambda _: next_binding)
    with pytest.raises(ValueError, match="already claimed"):
        session.claim()


def test_item_and_battle_consumption_both_subtract_without_mutating_supply(monkeypatch, tmp_path):
    *_, session, runtime = setup(monkeypatch, tmp_path)
    session._accept(GoalExecutionReport(1, 1, {"item_id": 16, "owned_items_consumed": 1}))
    supplied = ((16, 3), (53, 1), (3, 6))
    assert session.expected_bag(supplied, 1) == ((16, 1), (53, 1), (3, 6))
    assert supplied == ((16, 3), (53, 1), (3, 6))
    assert session.replacement_cost == 3000
    with pytest.raises(ValueError, match="exceeds owned"):
        session.expected_bag(((16, 1),), 1)


@pytest.mark.parametrize(
    "item,price", [(20, 300), (19, 700), (18, 1500), (16, 3000), (52, 600), (53, 1500)]
)
def test_native_buy_price_valuation_not_sale_proceeds(monkeypatch, tmp_path, item, price):
    *_, session, runtime = setup(monkeypatch, tmp_path)
    session._accept(GoalExecutionReport(1, 1, {"item_id": item, "owned_items_consumed": 1}))
    assert session.replacement_cost == price


@pytest.mark.parametrize(
    "changes",
    [{"maximum_items": True}, {"maximum_items": 0}, {"target_cash": True}, {"model_sha256": "bad"}],
)
def test_bad_configuration_before_any_output(monkeypatch, tmp_path, changes):
    model = _model()
    params = dict(
        model=model,
        model_sha256=model.model_sha256,
        output=tmp_path / "new",
        snapshot=lambda: b"state",
        target_cash=10000,
    )
    with pytest.raises(ValueError):
        LeagueFieldRecovery(**(params | changes))
    assert not (tmp_path / "new").exists()
