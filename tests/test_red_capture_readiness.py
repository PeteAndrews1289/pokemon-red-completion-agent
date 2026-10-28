from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.goal_manager import GoalKind, GoalSituation
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding
from pokemon_red_completion.observation import ItemId, MapId, RawGameState
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.red_capture_readiness import (
    CapturePreparationBudget,
    ReadinessGuardedCaptureProvider,
    assess_capture_readiness,
    capture_preparation_situation,
    capture_reserve_purchase,
)
from pokemon_red_completion.red_goal_manager import RedGoalBindingOffer
from pokemon_red_completion.red_goal_skills import RedMartPurchase, RedMartResupplyGoalProvider

BUDGET = CapturePreparationBudget(ItemId.ULTRA_BALL, 5, 20, True)


def observation(stock=10, pp=10, hp=100, slots=2, cash=30000):
    raw = RawGameState(
        True,
        1,
        1,
        1,
        1,
        0,
        bag_items=((1, 1),) + (((2, stock),) if stock else ()),
        player_money=cash,
    )
    member = PartyMemberObservation(
        1, 28, 50, hp, 100, StatusCondition.HEALTHY, (MoveObservation(86, pp),)
    )
    return NS(
        raw=raw,
        party=PartyObservation((member,)),
        immediate_capture_slots=slots,
        input_ready=True,
        situation=GoalSituation(0, 0.5, 0, 0, 0, 0, 0, 0, 0),
    )


@pytest.mark.parametrize(
    "stock,blocked,pressure", [(0, True, 1), (4, True, 0.8), (10, False, 0.5), (20, False, 0)]
)
def test_stock_and_master_are_distinct(stock, blocked, pressure):
    obs = observation(stock)
    r = assess_capture_readiness(obs, BUDGET, target_available=True)
    assert bool(r.hard_blocks) == blocked
    assert r.master_balls == 1 and r.selected_stock == stock
    assert capture_preparation_situation(obs, r).resource_pressure == pytest.approx(pressure)
    assert r.public_dict()["capture_guaranteed"] is False
    assert r.public_dict()["survivable_turns"] is None


@pytest.mark.parametrize(
    "pp,hp,ready", [(10, 100, True), (0, 100, False), (10, 0, False), (10, 50, False)]
)
def test_helper_pp_and_health_are_observed(pp, hp, ready):
    r = assess_capture_readiness(observation(pp=pp, hp=hp), BUDGET, target_available=True)
    assert r.usable_status == ready
    assert ("required_status_support_missing" in r.hard_blocks) != ready
    assert r.safe_weakening == "unknown_until_live_damage_check"
    assert r.status_options[0]["pp"] == pp


@pytest.mark.parametrize("stock,expected", [(0,None),(7,None),(8,8),(16,16),(24,24),(99,24)])
def test_static_allocation_uses_more_carried_stock_without_refilling(stock, expected):
    from pokemon_red_completion.red_capture_readiness import carried_static_capture_allocation
    bag = {int(ItemId.GREAT_BALL):stock}
    assert carried_static_capture_allocation(ItemId.GREAT_BALL,bag) == expected
    assert bag == {int(ItemId.GREAT_BALL):stock}


@pytest.mark.parametrize("stock", [True,-1,100,None])
def test_static_allocation_refuses_malformed_stock(stock):
    from pokemon_red_completion.red_capture_readiness import carried_static_capture_allocation
    with pytest.raises(ValueError):
        carried_static_capture_allocation(ItemId.GREAT_BALL,{int(ItemId.GREAT_BALL):stock})


def test_static_allocation_never_consumes_master_ball():
    from pokemon_red_completion.red_capture_readiness import carried_static_capture_allocation
    with pytest.raises(ValueError):
        carried_static_capture_allocation(ItemId.MASTER_BALL,{int(ItemId.MASTER_BALL):1})


def test_target_storage_and_inbattle_state_fail_closed():
    obs = observation(slots=0)
    assert (
        "storage_full" in assess_capture_readiness(obs, BUDGET, target_available=True).hard_blocks
    )
    for available, reason in [(None, "target_unknown"), (False, "target_unavailable")]:
        assert (
            reason in assess_capture_readiness(obs, BUDGET, target_available=available).hard_blocks
        )
    obs.raw = replace(obs.raw, battle_state=1)
    assert (
        "field_not_ready"
        in assess_capture_readiness(obs, BUDGET, target_available=True).hard_blocks
    )


def mart(obs):
    return RedMartResupplyGoalProvider(
        MapId.VIRIDIAN_MART,
        1,
        1,
        "up",
        (RedMartPurchase(0, ItemId.ULTRA_BALL, 20, 1200),),
        None,
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    "stock,cash,quantity,reason",
    [
        (0, 30000, 20, None),
        (10, 30000, 10, None),
        (20, 30000, 0, "reserve_satisfied"),
        (0, 1199, 0, "unaffordable"),
        (0, 2400, 2, None),
        (0, None, 0, "funds_unknown"),
    ],
)
def test_costed_reserve_never_uses_master_or_unearned_income(stock, cash, quantity, reason):
    obs = observation(stock, cash=cash)
    p, quote = capture_reserve_purchase(obs, BUDGET, mart(obs))
    assert quote["affordable_quantity"] == quantity
    assert quote["unavailable_reason"] == reason
    assert quote["reachability_proved"] is False
    if p:
        assert p.purchases[0].quantity == quantity
        assert p.reserve_targets == ((ItemId.ULTRA_BALL, stock + quantity),)
        assert p.funding_sale is None


def test_full_bag_or_unknown_inventory_is_not_a_cash_solution():
    obs = observation(0)
    obs.raw = replace(obs.raw, bag_items=tuple((i, 1) for i in range(20, 40)))
    assert capture_reserve_purchase(obs, BUDGET, mart(obs))[1]["unavailable_reason"] == "bag_full"
    obs.raw = replace(obs.raw, bag_items=None)
    assert capture_reserve_purchase(obs, BUDGET, mart(obs))[0] is None
    with pytest.raises(ValueError, match="observed inventory"):
        assess_capture_readiness(obs, BUDGET)


def test_unreachable_shop_remains_unavailable_after_resource_quote():
    obs = observation()
    p, quote = capture_reserve_purchase(obs, BUDGET, mart(obs))
    # Resource affordability is not evidence of the actual clerk boundary.
    p = replace(
        p,
        actions=NS(actions_executed=0),
        emulator=NS(frame_count=0),
        adapter=NS(observe=lambda: obs),
    )
    assert quote["purchase_cost"] == 12000
    assert p.offer(obs).binding is None


def test_guard_does_not_spend_input_or_replace_missing_capture_with_teacher():
    obs = observation(0)
    state = NS(obs=obs, executed=0)
    adapter = NS(observe=lambda: state.obs)

    def execute():
        state.executed += 1

    binding = ExecutableGoalBinding(
        "test:capture", GoalKind.ACQUIRE_SPECIES, 0.1, 0.2, execute, lambda r: None
    )
    provider = NS(offer=lambda o: RedGoalBindingOffer.available(binding))
    guarded = ReadinessGuardedCaptureProvider(
        provider, adapter, lambda o: assess_capture_readiness(o, BUDGET, target_available=True)
    )
    assert guarded.offer(obs).binding is None and state.executed == 0
    state.obs = observation(20)
    b = guarded.offer(state.obs).binding
    state.obs = observation(4)  # resources changed during travel/preparation
    with pytest.raises(ValueError, match="changed"):
        b.execute()
    assert state.executed == 0
    state.obs = observation(20)
    guarded.offer(state.obs).binding.execute()
    assert state.executed == 1


@pytest.mark.parametrize(
    "changes", [{"ball": ItemId.MASTER_BALL}, {"throws": 0}, {"reserve": 100}, {"throws": 21}]
)
def test_bad_or_unbounded_allocations_rejected(changes):
    with pytest.raises(ValueError):
        replace(BUDGET, **changes)


def test_capture_pressure_does_not_count_master_or_general_potion_deficit():
    obs = observation(0)
    obs.situation = replace(obs.situation, resource_pressure=1, safety_pressure=0.6)
    obs.raw = replace(obs.raw, bag_items=((1, 1), (3, 10)))
    r = assess_capture_readiness(obs, BUDGET, target_available=True)
    situation = capture_preparation_situation(obs, r)
    assert situation.resource_pressure == 0.5
    assert situation.safety_pressure == 0.6  # Health safety remains unchanged.
    assert "allocated_ball_stock_missing" in r.hard_blocks  # Cannot throw absent Ultras.
    obs.raw = replace(obs.raw, bag_items=((1, 1),))
    r = assess_capture_readiness(obs, BUDGET, target_available=True)
    assert capture_preparation_situation(obs, r).resource_pressure == 1


@pytest.mark.parametrize("stock,forced", [(0, True), (5, True), (10, False), (20, False)])
def test_preparation_menu_retains_existing_safety_thresholds(stock, forced):
    import json

    from test_red_live_option_menu import _model, _ordinary_bindings

    from pokemon_red_completion.red_capture_readiness import build_capture_preparation_options
    from pokemon_red_completion.red_live_option_menu import select_red_live_option
    from pokemon_red_completion.resource_economy_observation import EconomySnapshot

    obs = observation(stock, cash=58)
    obs.economy_snapshot = lambda: EconomySnapshot(58, (("capture", stock),) if stock else ())
    readiness = assess_capture_readiness(obs, BUDGET, target_available=True)
    calls = []
    options = build_capture_preparation_options(
        obs, readiness, _ordinary_bindings(calls), model_feature_version=4,
        ordering_seed_sha256="a" * 64,
    )
    choice = select_red_live_option(_model(), options, seed=123, exploration_mix=0)
    assert (choice.mode.value == "deterministic_safety") == forced
    assert calls == []
    projection = json.dumps(options.menu.policy_dict())
    for forbidden in ("private:red", "master_balls", "species_id", "move_id", "map_id"):
        assert forbidden not in projection
