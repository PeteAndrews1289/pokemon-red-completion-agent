from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_red_live_option_menu import _binding

from pokemon_red_completion import red_player_cash_exposure as c
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalManagerRuntimeError
from pokemon_red_completion.route_executor import RouteExecutionError


def test_only_explicit_zero_rates_certify_maps(monkeypatch):
    monkeypatch.setattr(c, "verify_rom_bytes", lambda _: None)
    rom = bytearray(0x10000)
    for i, pointer in enumerate((0x4000, 0x4010, 0x4020, 0, 0x8000)):
        at = c.WILD_POINTER_ARRAY + i * 2
        rom[at : at + 2] = pointer.to_bytes(2, "little")
    rom[c.bank_offset(3, 0x4010)] = 10
    rom[c.bank_offset(3, 0x4020) + 1] = 10
    c.encounter_free_maps.cache_clear()
    assert c.encounter_free_maps(bytes(rom)) == frozenset({0})
    c.encounter_free_maps.cache_clear()


@pytest.mark.parametrize("fault", [None, "poison", "unknown", "wild", "field_move", "all_fainted"])
def test_cash_safe_plan_fails_closed(monkeypatch, fault):
    monkeypatch.setattr(c, "encounter_free_maps", lambda _: frozenset({3, 65, 64}))
    raw = N(party_hp=(20,), party_status=(0,))
    plan = N(macro_path=N(maps=(65, 3, 64)), steps=(N(action_kind=MacroActionKind.MOVE),))
    if fault == "poison":
        raw.party_status = (8,)
    elif fault == "unknown":
        raw.party_status = None
    elif fault == "wild":
        plan.macro_path.maps = (65, 3, 12, 64)
    elif fault == "field_move":
        plan.steps = (N(action_kind=MacroActionKind.INTERACT),)
    elif fault == "all_fainted":
        raw.party_hp = (0,)
    if fault:
        with pytest.raises(RouteExecutionError):
            c.require_cash_safe_plan(b"rom", raw, plan)
    else:
        c.require_cash_safe_plan(b"rom", raw, plan)


@pytest.mark.parametrize("cash,bound", [(0, 0), (1, 1), (427, 214), (507, 254), (508, 254)])
def test_single_blackout_uses_ceiling_of_half_wallet(cash, bound):
    assert c.single_blackout_cash_bound(N(player_money=cash), object()) == bound
    assert c.single_blackout_cash_bound(N(player_money=cash), None) is None


@pytest.mark.parametrize("invalid", [-1, True, 1.5, 1000000])
def test_binding_rejects_invalid_bound(invalid):
    binding = _binding(GoalKind.RESTORE_TEAM, binding_ref="restore", calls=[])
    with pytest.raises(GoalManagerRuntimeError):
        replace(binding, maximum_cash_debit=invalid)


def test_bound_is_private_and_cannot_conflict_with_quote():
    binding = _binding(GoalKind.RESTORE_TEAM, binding_ref="restore", calls=[])
    assert replace(binding, maximum_cash_debit=0).opportunity == binding.opportunity
    with pytest.raises(GoalManagerRuntimeError):
        replace(binding, maximum_cash_debit=0, resource_quote=N())
    assert c.certified_cash_safe_transition(N(), N(), N()) is None


@pytest.mark.parametrize("unsafe_replan", [False, True])
def test_live_cash_safe_route_revalidates_replans(monkeypatch, unsafe_replan):
    from test_red_training_ground_route import _world

    from pokemon_red_completion import red_training_ground_route as g
    from pokemon_red_completion.strategic_navigation_scenario_runtime import (
        StrategicScenarioRouteWorld,
    )

    world = _world()
    initial, replacement = object(), object()
    start = N(map_id=3, at=(1, 1), ready=True, interruption=None)
    end = N(map_id=64, at=(3, 3), ready=True, interruption=None)
    observations = iter((start, end))
    monkeypatch.setattr(
        g, "Gen1TraversalObserver", lambda *a, **k: N(observe=lambda: next(observations))
    )
    monkeypatch.setattr(g, "Gen1TrainerSightProjector", lambda *a, **k: None)
    monkeypatch.setattr(g, "Gen1FieldMovePort", lambda *a, **k: object())
    monkeypatch.setattr(
        StrategicScenarioRouteWorld, "plan_feasible_to_map", lambda *a, **k: initial
    )
    monkeypatch.setattr(
        StrategicScenarioRouteWorld, "replanner", lambda _: lambda request: replacement
    )
    checked = []

    def check(rom, raw, plan):
        checked.append(plan)
        if plan is replacement and unsafe_replan:
            raise RouteExecutionError("uncertified replan")

    monkeypatch.setattr(c, "require_cash_safe_plan", check)

    def execute(plan, actions, observer, **kwargs):
        assert kwargs["interruption_handler"].maximum_flees == 0
        assert kwargs["replanner"](object()) is replacement

    monkeypatch.setattr(g, "execute_route", execute)
    route = g.RedVermilionGroundTransition(
        b"rom",
        world,
        destination_map=64,
        destination_at=(3, 3),
        maximum_flees=0,
        require_cash_safe=True,
    )
    if unsafe_replan:
        with pytest.raises(RouteExecutionError, match="uncertified replan"):
            route(N(execute=lambda _: None), N(read=lambda: N()), object())
    else:
        route(N(execute=lambda _: None), N(read=lambda: N()), object())
    assert checked == [initial, replacement]
