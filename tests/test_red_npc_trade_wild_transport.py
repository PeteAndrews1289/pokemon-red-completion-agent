"""Trade travel reuses bounded escape, never implicit combat or unsafe success."""

from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_npc_trade import observation
from test_red_npc_trade_options import fixture

import pokemon_red_completion.gen1_route_runtime as routes
import pokemon_red_completion.red_npc_trade_options as trades
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot


@pytest.mark.parametrize(
    "fault", [None, "trainer_engagement", "scripted_dialogue", "drift", "limit",
              "unsettled", "escape_error"],
)
def test_trade_departure_wild_escape_preserves_fail_closed_boundaries(monkeypatch, fault):
    runtime, before, actions, world, calls = fixture(monkeypatch)
    current = [before]
    runtime.adapter.observe = lambda: current[0]
    runtime.reader.read = lambda: current[0].raw
    runtime.reader.trainer_engagement_active = lambda: False
    world.replanner = lambda: None
    monkeypatch.setattr(trades, "Gen1FieldMovePort", lambda *a, **k: NS(cut_receipts=()))
    escaped, exchanged = [], []

    def escape(executor, reader, encounter, **kwargs):
        assert executor is actions and reader is runtime.reader
        assert kwargs == dict(expected_map_id=48, route_name="NPC trade transport",
                              stabilization_frames=180, error_type=RouteExecutionError)
        if fault == "escape_error":
            raise RouteExecutionError("escape did not preserve resources")
        escaped.append(encounter)
        current[0].raw = replace(encounter, battle_state=0)
        return NS(map_id=48, player_y=2, player_x=4, verified=True,
                  public_dict=lambda: {"verified": True, "map_id": 48})

    monkeypatch.setattr(routes, "flee_wild", escape)

    def route(plan, port, observer, **kwargs):
        handler = kwargs["interruption_handler"]
        assert isinstance(handler, routes.Gen1WildFleeHandler)
        assert handler.maximum_flees == 16 and not handler.allow_party_faints
        current[0].raw = replace(current[0].raw, battle_state=1)
        kind = fault if fault in {"trainer_engagement", "scripted_dialogue"} else "wild_battle"
        if fault == "limit":
            handler.evidence.extend([None] * 16)
        interruption = TraversalSnapshot(49 if fault == "drift" else 48, (2, 4),
                                         False, interruption=kind)
        receipt = handler.handle(interruption)
        assert (receipt.resumed_map, receipt.resumed_at) == (48, (2, 4))
        return NS(passed=fault != "unsettled", executed_steps=())

    monkeypatch.setattr(trades, "execute_route", route)

    def exchange(*args, **kwargs):
        exchanged.append(True)
        current[0] = observation(True)
        runtime.reader.read_completed_npc_trades = lambda: frozenset({1})
        actions.actions_executed += 1
        runtime.emulator.frame_count += 180
        return {"received_level": 10}

    monkeypatch.setattr(trades, "execute_adjacent_trade", exchange)
    (binding,) = trades.npc_trade_bindings(runtime, before, actions, world)
    assert not calls and actions.actions_executed == runtime.emulator.frame_count == 0
    if fault is not None:
        with pytest.raises((RouteExecutionError, trades.RedNPCTradeError)):
            binding.execute()
        assert not exchanged
        with pytest.raises(trades.RedNPCTradeError, match="already consumed"):
            binding.execute()
    else:
        report = binding.execute()
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
        assert len(escaped) == 1
        assert report.evidence["wild_escape_receipts"] == [{"verified": True, "map_id": 48}]
        assert report.evidence["wild_escape_authority"] == "rule_based_execution_support"
        assert report.evidence["exchange_verified_at_npc"] is True
