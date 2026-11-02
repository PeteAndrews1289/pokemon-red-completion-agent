"""Pure quote/context integration: no model prediction, fitted labels or native input."""

import ast
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from test_living_dex_economy_head import _candidate, _econ_context

from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionKind,
    LivingDexOptionMenu,
    pure_income_success_saturated,
)
from pokemon_red_completion.living_dex_policy_codec import restore_living_dex_policy_menu
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.red_capture_readiness import CapturePreparationBudget
from pokemon_red_completion.red_goal_skills import RedMartPurchase, RedMartResupplyGoalProvider
from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory
from pokemon_red_completion.resource_economy_observation import EconomyMode, EconomyOffer


def funding():
    return _candidate(
        "funding",
        LivingDexOptionKind.RESUPPLY,
        offer=EconomyOffer(EconomyMode.EARN, conditional_income=1680),
    )


def real_helper_target(stock, cash, *, declared=True, known_stock=True):
    helper = (
        Path(__file__).resolve().parents[1]
        / "runtime_helpers/red_whole_player_inventory_20261006.py"
    )
    tree = ast.parse(helper.read_text())
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "parent_capture_cash_target"
    )
    budget = CapturePreparationBudget(ItemId.GREAT_BALL, 8, 8, require_status=True)
    mart = RedMartResupplyGoalProvider(
        MapId.VIRIDIAN_MART,
        1,
        1,
        "up",
        (RedMartPurchase(0, ItemId.GREAT_BALL, 8, 600),),
        None,
        None,
        None,
        None,
    )
    raw = NS(bag_items=((1, 1), (3, stock)) if known_stock else None, player_money=cash)
    runtime = NS(
        profile=object(), adapter=NS(observe=lambda: NS(raw=raw)), provider_for=lambda *_: mart
    )
    from pokemon_red_completion.goal_manager import GoalKind

    scope = dict(
        observed_resource_runtime=lambda value: value,
        player_supply_reserve=lambda _: budget if declared else None,
        GoalKind=GoalKind,
    )
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(helper), "exec"), scope)
    return scope["parent_capture_cash_target"](runtime, None)


@pytest.mark.parametrize(
    "stock,cash,target", [(0, 107, 4800), (2, 707, 3600), (0, 5000, 4800), (8, 107, 0)]
)
def test_actual_declared_reserve_cost_is_not_affordability_clamped(stock, cash, target):
    assert real_helper_target(stock, cash) == target


@pytest.mark.parametrize("kwargs", [dict(declared=False), dict(known_stock=False)])
def test_missing_declared_or_observed_inventory_is_unknown(kwargs):
    assert real_helper_target(0, 107, **kwargs) is None


def test_unknown_cash_is_unknown():
    assert real_helper_target(0, None) is None


@pytest.mark.parametrize(
    "cash,target,saturated",
    [(107, 4800, False), (5000, 4800, True), (107, 0, True), (107, None, False)],
)
def test_known_quote_reaches_exact_income_predicate_without_model(cash, target, saturated):
    inventory = NativeStoryBranchInventory(
        lambda *_: None, lambda *_: (), observe_cash_target=lambda *_: target
    )
    old = _econ_context(cash=cash, target_cash=0)
    new = inventory.cash_target_context(None, None, old)
    assert new.target_cash == (0 if target is None else target)
    assert new.cash_target_known is (target is not None)
    assert pure_income_success_saturated(new, funding()) is saturated
    assert old.target_cash == 0 and old.cash_target_known is False


def test_legacy_unknown_context_policy_and_vectors_roundtrip_unchanged():
    old = _econ_context(cash=107, target_cash=0)
    known = replace(old, cash_target_known=True)
    candidate = funding()
    second = _candidate(
        "other", LivingDexOptionKind.RESUPPLY, offer=EconomyOffer(EconomyMode.OTHER)
    )
    menu = LivingDexOptionMenu(old, (candidate, second))
    assert "cash_target_known" not in old.policy_dict()
    restored = restore_living_dex_policy_menu(menu.policy_dict(), binding_refs=("funding", "other"))
    assert restored.policy_dict() == menu.policy_dict()
    assert candidate.vector(old, feature_version=16) == candidate.vector(known, feature_version=16)
    known_menu = replace(menu, context=known)
    assert (
        restore_living_dex_policy_menu(
            known_menu.policy_dict(), binding_refs=("funding", "other")
        ).policy_dict()
        == known_menu.policy_dict()
    )


@pytest.mark.parametrize("invalid", [1, "true", None])
def test_knownness_requires_literal_boolean(invalid):
    with pytest.raises(ValueError):
        replace(_econ_context(), cash_target_known=invalid)


@pytest.mark.parametrize("invalid", [-1, True, 1.5, "0"])
def test_cash_target_observer_rejects_invalid_amount(invalid):
    inventory = NativeStoryBranchInventory(
        lambda *_: None, lambda *_: (), observe_cash_target=lambda *_: invalid
    )
    with pytest.raises(ValueError):
        inventory.cash_target_context(None, None, _econ_context())


def test_metadata_application_preserves_exact_offers_and_ownership():
    import pokemon_red_completion.red_player_lesson_runtime as runtime_module

    tree = ast.parse(Path(runtime_module.__file__).read_text())
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "observe_native_player_options"
    )
    block = next(
        n
        for n in fn.body
        if isinstance(n, ast.If)
        and isinstance(n.test, ast.Call)
        and isinstance(n.test.func, ast.Name)
        and n.test.func.id == "isinstance"
        and isinstance(n.test.args[0], ast.Name)
        and n.test.args[0].id == "inventory"
    )

    @dataclass(frozen=True)
    class Options:
        menu: object
        bindings: tuple
        ownership: str

    candidates = (
        funding(),
        _candidate("other", LivingDexOptionKind.RESUPPLY, offer=EconomyOffer(EconomyMode.OTHER)),
    )
    before = Options(
        LivingDexOptionMenu(_econ_context(cash=107, target_cash=0), candidates),
        (object(), object()),
        "model",
    )
    inventory = NativeStoryBranchInventory(
        lambda *_: None, lambda *_: (), observe_cash_target=lambda *_: 4800
    )
    scope = dict(
        inventory=inventory,
        NativeStoryBranchInventory=NativeStoryBranchInventory,
        runtime=None,
        actions=None,
        options=before,
        replace=replace,
    )
    exec(
        compile(
            ast.Module(body=[block], type_ignores=[]),
            "exact-post-enumeration-metadata-block",
            "exec",
        ),
        scope,
    )
    after = scope["options"]
    assert after.bindings is before.bindings and after.menu.candidates is before.menu.candidates
    assert after.ownership == before.ownership
    assert after.menu.context.target_cash == 4800 and after.menu.context.cash_target_known
    assert before.menu.context.resource_pressure == after.menu.context.resource_pressure
