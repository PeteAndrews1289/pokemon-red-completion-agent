"""Declared medicine/capture demand bridge: pure quotes and inert observer fixtures."""
import ast
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.red_capture_readiness import CapturePreparationBudget
from pokemon_red_completion.red_goal_skills import RedMartPurchase, RedMartResupplyGoalProvider
from pokemon_red_completion.red_player_story_menu import DeclaredCashDemand, NativeStoryBranchInventory
from pokemon_red_completion.living_dex_option_value import pure_income_success_saturated
from test_parent_capture_cash_demand import funding
from test_living_dex_economy_head import _econ_context


def helper_callbacks(raw, *, capture_declared=True, include_rewards=True):
    """Real canonical helper function bodies, ordinary Mart quote, inert dependencies.

    This is not full package assembly/native qualification. The integration below
    invokes the real option observer after these exact helper callbacks execute.
    """
    helper = Path(__file__).resolve().parents[1] / "runtime_helpers/red_whole_player_inventory_20261006.py"
    tree = ast.parse(helper.read_text())
    names = ("income_reserve_cost", "observed_medicine_cash_target",
             "parent_capture_cash_target", "parent_cash_demand")
    functions = [next(node for node in ast.walk(tree)
                      if isinstance(node, ast.FunctionDef) and node.name == name) for name in names]
    budget = CapturePreparationBudget(ItemId.GREAT_BALL, 8, 8, require_status=True)
    mart = RedMartResupplyGoalProvider(MapId.VIRIDIAN_MART, 1, 1, "up",
        (RedMartPurchase(0, ItemId.GREAT_BALL, 8, 600),), None, None, None, None)
    logs = []
    scope = dict(ItemId=ItemId, GoalKind=GoalKind,
        observed_resource_runtime=lambda runtime: runtime,
        player_supply_reserve=lambda _: budget if capture_declared else None,
        include_rewards=include_rewards, record=lambda name, value: logs.append((name, value)))
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(helper), "exec"), scope)
    rt = NS(profile=object(), adapter=NS(observe=lambda: NS(raw=raw)),
            reader=NS(read=lambda: raw), provider_for=lambda *_: mart)
    return scope, rt, logs


def raw_state(*, cash=478, balls=8, full_restores=0, revives=0, full_heals=1,
              badges=255, known_stock=True):
    bag = tuple((int(item), quantity) for item, quantity in (
        (ItemId.GREAT_BALL, balls), (ItemId.FULL_RESTORE, full_restores),
        (ItemId.REVIVE, revives), (ItemId.FULL_HEAL, full_heals)) if quantity)
    return NS(player_money=cash, bag_items=bag if known_stock else None, badge_bits=badges)


@pytest.mark.parametrize("cash", [0, 478, 21600, 50000])
def test_existing_medicine_target_is_not_affordability_clamped(cash):
    raw = raw_state(cash=cash)
    scope, runtime, logs = helper_callbacks(raw)
    assert scope["income_reserve_cost"](raw) == 21600
    quote = scope["parent_cash_demand"](runtime, object())
    assert quote.components == (("capture", 0), ("recovery", 21600))
    assert quote.target_cash == 21600 and quote.known
    assert logs == [("parent-cash-demand", quote.public_dict())]
    context = NativeStoryBranchInventory(lambda *_: None, lambda *_: (),
        observe_cash_target=lambda *_: quote).cash_target_context(None, None, _econ_context(cash=cash))
    assert context.target_cash == 21600 and context.cash_target_known
    assert pure_income_success_saturated(context, funding()) is (cash >= 21600 and cash > 0)


def test_disjoint_missing_costs_added_once_not_shortfalls_or_affordable_lots():
    scope, runtime, _ = helper_callbacks(raw_state(balls=2, cash=478))
    quote = scope["parent_cash_demand"](runtime, None)
    assert quote.components == (("capture", 3600), ("recovery", 21600))
    assert quote.target_cash == 25200  # Current cash is compared once by the existing consumer.
    # The purchase shortage does not modify the real available cash or quote provider.
    assert runtime.reader.read().player_money == 478


def test_unknown_capture_keeps_positive_medicine_lower_bound_without_saturation_claim():
    scope, runtime, _ = helper_callbacks(raw_state(), capture_declared=False)
    quote = scope["parent_cash_demand"](runtime, None)
    assert quote.components == (("capture", None), ("recovery", 21600))
    assert quote.target_cash == 21600 and not quote.known
    context = NativeStoryBranchInventory(lambda *_: None, lambda *_: (),
        observe_cash_target=lambda *_: quote).cash_target_context(None, None, _econ_context(cash=50000))
    assert context.target_cash == 21600 and not context.cash_target_known
    assert not pure_income_success_saturated(context, funding())


@pytest.mark.parametrize("raw", [raw_state(known_stock=False), raw_state(cash=None)])
def test_missing_observation_is_unknown_not_a_zero_demand_certificate(raw):
    scope, runtime, _ = helper_callbacks(raw)
    quote = scope["parent_cash_demand"](runtime, None)
    assert quote.components == (("capture", None), ("recovery", None))
    assert quote.target_cash == 0 and not quote.known


def test_unknown_badges_keeps_capture_cost_but_recovery_scope_unknown():
    scope, runtime, _ = helper_callbacks(raw_state(balls=0, badges=None))
    quote = scope["parent_cash_demand"](runtime, None)
    assert quote.components == (("capture", 4800), ("recovery", None))
    assert quote.target_cash == 4800 and not quote.known


@pytest.mark.parametrize("kwargs", [dict(include_rewards=False), dict()])
def test_inactive_medicine_scope_is_explicit_zero(kwargs):
    raw = raw_state(badges=255 if kwargs else 127, balls=2)
    scope, runtime, _ = helper_callbacks(raw, **kwargs)
    quote = scope["parent_cash_demand"](runtime, None)
    assert quote.components == (("capture", 3600), ("recovery", 0)) and quote.known


def test_bag_full_does_not_erase_observed_capture_need():
    raw = raw_state(balls=0, full_restores=4, revives=6, full_heals=2)
    # Capture provider's bag-full admission stays blocked; demand is still measurable.
    raw.bag_items = raw.bag_items + tuple((item, 1) for item in range(100, 117))
    scope, runtime, _ = helper_callbacks(raw)
    quote = scope["parent_cash_demand"](runtime, None)
    assert len(raw.bag_items) == 20
    assert quote.components == (("capture", 4800), ("recovery", 0)) and quote.known


def test_full_declared_stocks_are_known_zero_but_not_all_future_expenses():
    scope, runtime, _ = helper_callbacks(raw_state(full_restores=4, revives=6, full_heals=2))
    quote = scope["parent_cash_demand"](runtime, None)
    assert quote.target_cash == 0 and quote.known
    assert quote.public_dict()["all_future_expenses_known"] is False


@pytest.mark.parametrize("components", [[], (), (("capture", -1),), (("capture", True),),
    (("capture", 1.2),), (("capture", 1), ("capture", 2)), (("safari", 500),)])
def test_typed_quote_refuses_malformed_or_overlapping_scopes(components):
    with pytest.raises(ValueError): DeclaredCashDemand(components)


def test_real_helper_callbacks_then_real_observer_preserve_bindings_and_parent_control(tmp_path, monkeypatch):
    from test_red_player_lesson_runtime import fixture
    from test_red_live_option_menu import _ordinary_bindings, _situation
    import pokemon_red_completion.red_player_lesson_runtime as lesson
    _, emulator, kwargs = fixture(tmp_path, monkeypatch)
    runtime = kwargs["runtime_factory"](emulator)
    raw = raw_state()
    scope, quote_runtime, logs = helper_callbacks(raw)
    original_capture = lesson.capture_player_lesson_snapshot
    def capture(rt):
        observation, snapshot = original_capture(rt)
        observation.situation = _situation(resources=1.0)
        observation.raw.player_money = raw.player_money
        observation.raw.bag_items = raw.bag_items
        return observation, snapshot
    monkeypatch.setattr(lesson, "capture_player_lesson_snapshot", capture)
    calls = []; ordinary = _ordinary_bindings(calls)
    base = lambda *_: ordinary
    original_inventory = NativeStoryBranchInventory(base, lambda *_: ())
    inventory = NativeStoryBranchInventory(base, lambda *_: (),
        observe_cash_target=lambda *_: scope["parent_cash_demand"](quote_runtime, None))
    args = {name: kwargs[name] for name in ("battle", "combat_specimen_refs", "remaining_budget")}
    def observe(inv):
        return lesson.observe_native_player_options(runtime, object(), **args, target_cash=0,
            ordering_seed_sha256="a"*64, model_feature_version=16, force_resource_safety=False,
            **inv.native_callbacks())
    state = emulator.save_state_bytes()
    old, new = observe(original_inventory), observe(inventory)
    assert new.bindings == old.bindings
    assert new.menu.candidates == old.menu.candidates
    assert new.menu.available_indices == old.menu.available_indices
    assert new.menu.context == replace(old.menu.context, target_cash=21600, cash_target_known=True)
    assert not pure_income_success_saturated(new.menu.context, funding())
    assert emulator.save_state_bytes() == state and emulator.frame_count == 0
    assert not emulator.pressed_buttons and not calls and len(logs) == 1
