from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_game_corner_execution import Reader, raw
from test_red_live_option_menu import _situation

import pokemon_red_completion.red_game_corner_goals as module
import pokemon_red_completion.red_game_corner_resources as resources
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import (
    living_dex_option_context_from_goal_situation,
)
from pokemon_red_completion.resource_economy_observation import EconomyMode
from pokemon_red_completion.route_plan import RoutePlanningError


def environment(monkeypatch, *, case=True, cash=1000, coins=0, owned=(7,), reachable=True):
    reader = Reader(raw(case=case, money=cash), coins)
    reader.owned = set(owned)
    payload = [b"unchanged source"]
    runtime = NS(reader=reader, emulator=NS(save_state_bytes=lambda: payload[0]))
    observation = NS(
        raw=reader.state,
        input_ready=True,
        collection_observation=NS(
            owned_species=frozenset(f"pokemon:national:{s:03d}" for s in owned)
        ),
    )

    def plan(*a, **k):
        if not reachable:
            raise RoutePlanningError("No legal approach")
        return NS(steps=(None,) * 5)

    world = NS(rom=b"pinned fixture", plan_feasible_to_map=plan)
    prizes = (NS(species=63, level=9, cost=50), NS(species=137, level=26, cost=9999))
    monkeypatch.setattr(module, "game_corner_prizes", lambda _: prizes)
    monkeypatch.setattr(resources, "game_corner_prizes", lambda _: prizes)
    monkeypatch.setattr(resources, "authenticate_coin_vendor", lambda _: (69, 50, 1000, 9990, 9999))
    monkeypatch.setattr(module, "coin_case_gift_contract", lambda _: 480)
    monkeypatch.setattr(module, "Gen1TraversalObserver", lambda *a, **k: NS(observe=lambda: NS()))
    monkeypatch.setattr(module, "Gen1TrainerSightProjector", lambda *a, **k: NS())
    monkeypatch.setattr(module, "RedVermilionGroundTransition", lambda *a, **k: NS())
    actions = NS(actions_executed=0)
    return runtime, observation, actions, world, payload


def offers(env, **kwargs):
    return module.game_corner_options(
        *env[:4],
        situation=_situation(safety=0),
        model_feature_version=4,
        maximum_actions=kwargs.get("actions", 10000),
        maximum_frames=kwargs.get("frames", 1000000),
        cash_reserve=kwargs.get("reserve", 0),
    )


def test_free_coin_case_is_a_resource_prerequisite_not_registration(monkeypatch):
    env = environment(monkeypatch, case=False, cash=0)
    result = offers(env)
    assert len(result) == 1 and result[0].binding.kind is GoalKind.RESUPPLY
    assert result[0].binding.maximum_cash_debit == 0 and env[2].actions_executed == 0
    context = living_dex_option_context_from_goal_situation(_situation(safety=0))
    assert "coin-case" not in str(result[0].candidate.policy_dict(context))


def test_only_actual_affordable_missing_prize_is_offered(monkeypatch):
    env = environment(monkeypatch)
    result = offers(env)
    assert len(result) == 1 and result[0].binding.binding_ref == "red-game-corner:63"
    assert result[0].binding.maximum_cash_debit == 1000
    assert result[0].candidate.economy_offer.mode is EconomyMode.PURCHASE
    assert result[0].candidate.economy_offer.planned_spend == 1000
    assert env[2].actions_executed == 0


def test_native_coins_allow_a_prize_without_cash_purchase(monkeypatch):
    env = environment(monkeypatch, cash=0, coins=50)
    result = offers(env)
    assert len(result) == 1 and result[0].binding.maximum_cash_debit == 0
    assert result[0].candidate.economy_offer.mode is EconomyMode.OTHER


@pytest.mark.parametrize("change", ["owned", "cash", "route", "storage", "limit", "dialogue"])
def test_unavailable_prizes_do_not_emit_or_offer_inputs(monkeypatch, change):
    env = environment(
        monkeypatch,
        cash=0 if change == "cash" else 1000,
        owned=(7, 63) if change == "owned" else (7,),
        reachable=change != "route",
    )
    if change == "storage":
        env[1].raw = replace(env[1].raw, party_count=6)
        env[0].reader.boxes = NS(current_box_index=0, boxes=(NS(species_ids=(177,) * 20),))
    if change == "dialogue":
        env[0].reader.stage = "dialogue"
    assert offers(env, actions=1 if change == "limit" else 10000) == ()
    assert env[2].actions_executed == 0


def test_coin_case_consumed_flag_or_full_bag_blocks_its_offer(monkeypatch):
    env = environment(monkeypatch, case=False)
    flags = bytearray(319)
    flags[480 // 8] = 1
    env[1].raw = replace(env[1].raw, event_flags=bytes(flags))
    assert offers(env) == ()
    env[1].raw = replace(
        env[1].raw, event_flags=bytes(319), bag_items=tuple((i, 1) for i in range(1, 21))
    )
    assert offers(env) == ()


def test_source_bound_prize_rejects_stale_state_before_input(monkeypatch):
    env = environment(monkeypatch)
    binding = offers(env)[0].binding
    env[4][0] = b"changed source"
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    assert env[2].actions_executed == 0


def coin_offers(env, **kwargs):
    return module.game_corner_coin_options(
        *env[:4],
        situation=_situation(safety=0),
        model_feature_version=4,
        maximum_actions=kwargs.get("actions", 10000),
        maximum_frames=kwargs.get("frames", 1000000),
        cash_reserve=kwargs.get("reserve", 0),
    )


@pytest.mark.parametrize(
    "coins,cash,owned,target",
    [
        (20, 5029, (7, 63), 200000),
        (270, 29, (7, 63), 195000),
        (20, 5029, (7, 63, 137), 0),
        (9990, 5029, (7, 63), 0),
    ],
)
def test_native_prize_shortfall_is_not_zero_capture_ball_target(
    monkeypatch, coins, cash, owned, target
):
    env = environment(monkeypatch, cash=cash, coins=coins, owned=owned)
    assert module.game_corner_funding_target_cash(env[0], env[3]) == target
    assert env[2].actions_executed == 0


def test_partial_coin_offer_is_real_purchase_not_prize_credit(monkeypatch):
    env = environment(monkeypatch, cash=5029, coins=20, owned=(7, 63))
    monkeypatch.setattr(module, "authenticate_coin_vendor", resources.authenticate_coin_vendor)
    result = coin_offers(env)
    assert len(result) == 1
    binding, candidate = result[0].binding, result[0].candidate
    assert binding.kind is GoalKind.RESUPPLY and binding.maximum_cash_debit == 5000
    assert candidate.economy_offer.mode is EconomyMode.PURCHASE
    assert candidate.economy_offer.planned_spend == 5000
    assert env[2].actions_executed == 0 and env[4][0] == b"unchanged source"
    env[4][0] = b"different source"
    with pytest.raises(ValueError, match="stale"):
        binding.execute()


@pytest.mark.parametrize("change", ["owned", "funded", "cash", "case", "route", "limit", "refusal"])
def test_no_partial_purchase_without_actual_executable_progress(monkeypatch, change):
    env = environment(
        monkeypatch,
        cash=200000 if change == "funded" else 999 if change == "cash" else 5029,
        coins=9990 if change == "refusal" else 20,
        case=change != "case",
        owned=(7, 63, 137) if change == "owned" else (7, 63),
        reachable=change != "route",
    )
    monkeypatch.setattr(module, "authenticate_coin_vendor", resources.authenticate_coin_vendor)
    assert coin_offers(env, actions=1 if change == "limit" else 10000) == ()
    assert env[2].actions_executed == 0


def test_disclosed_cash_reserve_bounds_coin_quantity_not_a_supplied_goal(monkeypatch):
    env = environment(monkeypatch, cash=5029, coins=20, owned=(7, 63))
    monkeypatch.setattr(module, "authenticate_coin_vendor", resources.authenticate_coin_vendor)
    result = coin_offers(env, reserve=2100)
    assert len(result) == 1
    assert result[0].binding.maximum_cash_debit == 2000
    assert result[0].candidate.economy_offer.planned_spend == 2000
    assert coin_offers(env, reserve=5030) == ()
    assert env[0].reader.state.player_money == 5029 and env[2].actions_executed == 0


def test_cash_purchase_prize_cannot_spend_reserve_but_owned_coins_still_work(monkeypatch):
    env = environment(monkeypatch, cash=1000, coins=0)
    assert offers(env, reserve=1) == ()
    env = environment(monkeypatch, cash=0, coins=50)
    assert len(offers(env, reserve=11100)) == 1


@pytest.mark.parametrize("reserve", [-1, True, 1.5, "600"])
def test_reserve_cannot_be_an_untyped_or_negative_quota(monkeypatch, reserve):
    env = environment(monkeypatch)
    for build in (offers, coin_offers):
        with pytest.raises(ValueError, match="nonnegative integer"):
            build(env, reserve=reserve)


def test_partial_purchase_exact_receipt_and_terminal_identity(monkeypatch):
    env = environment(monkeypatch, cash=5029, coins=20, owned=(7, 63))
    monkeypatch.setattr(module, "authenticate_coin_vendor", resources.authenticate_coin_vendor)
    runtime, _, actions, _, payload = env
    runtime.emulator.frame_count = 0
    runtime.emulator.pressed_buttons = ()
    monkeypatch.setattr(module, "RedVermilionGroundTransition", lambda **_: lambda *_: None)
    monkeypatch.setattr(module, "face_pc_boundary", lambda *_: None)

    def buy(*_, **__):
        runtime.reader.state = replace(
            runtime.reader.state, player_money=runtime.reader.state.player_money - 1000
        )
        runtime.reader.coins += 50
        actions.actions_executed += 8
        runtime.emulator.frame_count += 80
        payload[0] += b"lot"

    monkeypatch.setattr(module, "buy_coin_lot", buy)
    binding = coin_offers(env)[0].binding
    report = binding.execute()
    assert report.actions_executed == 40 and report.frames_executed == 400
    assert report.evidence["purchases"] == 5
    assert report.evidence["coins_after"] == 270 and not report.evidence["registration_credit"]
    assert binding.verify(report).status.value == "succeeded"
    from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport

    assert (
        binding.verify(GoalExecutionReport(40, 400, dict(report.evidence))).status.value == "failed"
    )
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()
    payload[0] += b"unrelated input"
    assert binding.verify(report).status.value == "failed"
