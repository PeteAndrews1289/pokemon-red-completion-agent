from types import SimpleNamespace

import pokemon_red_completion.red_autonomous_league_funding as funding
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind


def test_qualified_renewable_income_becomes_one_verified_model_option(monkeypatch):
    qualification = SimpleNamespace(
        expected_net_income=1500,
        public_dict=lambda: {"schema": "qualification"},
    )
    origin = SimpleNamespace(raw=SimpleNamespace(player_money=228))
    league = SimpleNamespace(origin=origin, qualification=qualification)
    current = SimpleNamespace(
        raw=SimpleNamespace(player_money=1728, battle_state=0),
        input_ready=True,
    )
    runtime = SimpleNamespace(adapter=SimpleNamespace(observe=lambda: current))
    execution = SimpleNamespace(
        actions=40,
        frames=500,
        ending_money=1728,
        observed_net_income=1500,
        public_dict=lambda: {"schema": "execution"},
    )
    monkeypatch.setattr(funding, "bind_red_league_funding_execution", lambda *_: league)
    monkeypatch.setattr(funding, "execute_red_league_funding", lambda *_a, **_k: execution)

    binding = funding.bind_autonomous_league_funding(
        runtime,
        SimpleNamespace(),
        SimpleNamespace(),
        maximum_actions=30_000,
        maximum_frames=3_000_000,
    )

    assert binding is not None
    assert binding.kind is GoalKind.RESUPPLY
    assert binding.resource_quote.expected_income == 1500
    report = binding.execute()
    assert report.actions_executed == 40
    assert report.frames_executed == 500
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


def test_unqualified_league_income_is_not_advertised(monkeypatch):
    def unavailable(*_):
        raise funding.RedLeagueFundingError("not ready")

    monkeypatch.setattr(funding, "bind_red_league_funding_execution", unavailable)
    assert (
        funding.bind_autonomous_league_funding(
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            maximum_actions=30_000,
            maximum_frames=3_000_000,
        )
        is None
    )
