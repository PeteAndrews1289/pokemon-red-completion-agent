from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_autonomous_league_funding as funding
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport


@pytest.mark.parametrize("levels,expected", [
    ((56, 56, 63, 53, 64, 100), (0, 6, 1)),
    ((100, 56, 56, 63, 53, 64), (0, 6, 1)),
    ((100, 56, 56, 63, 52, 64), None),
    ((99, 56, 56, 63, 53, 64), None),
    ((101, 56, 56, 63, 53, 64), None),
    ((100, 56, 56, 63, 53), None),
    ((100, 56, 56, 63, 53, True), None),
    (None, None),
    ([100, 56, 56, 63, 53, 64], None),
])
def test_owned_stock_income_reserve_is_narrow_observational_support(levels, expected):
    assert funding.level100_owned_income_reserve_targets(
        SimpleNamespace(party_levels=levels)) == expected


@pytest.mark.parametrize("replacement_cost", [0, 300, 1500, 3000])
def test_qualified_renewable_income_becomes_one_verified_model_option(
    monkeypatch,
    replacement_cost,
):
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
        field_item_replacement_cost=replacement_cost,
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
    assert binding.verify(report).status is (
        GoalDecisionOutcome.SUCCEEDED if replacement_cost < 1500 else GoalDecisionOutcome.FAILED
    )


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


@pytest.mark.parametrize("fault", [None, "actions", "frames", "proof", "cash", "field"])
def test_explicit_native_return_is_counted_and_verified_not_a_teacher_goal(monkeypatch, fault):
    qualification = SimpleNamespace(
        expected_net_income=1500, public_dict=lambda: {"schema": "qualification"}
    )
    origin = SimpleNamespace(raw=SimpleNamespace(player_money=228))
    league = SimpleNamespace(origin=origin, qualification=qualification)
    current = SimpleNamespace(
        raw=SimpleNamespace(player_money=1728, battle_state=0), input_ready=True
    )
    runtime = SimpleNamespace(
        adapter=SimpleNamespace(observe=lambda: current), emulator=SimpleNamespace(frame_count=0)
    )
    actions = SimpleNamespace(actions_executed=0)
    execution = SimpleNamespace(
        actions=40,
        frames=500,
        ending_money=1728,
        observed_net_income=1500,
        field_item_replacement_cost=0,
        public_dict=lambda: {"schema": "execution"},
    )
    monkeypatch.setattr(funding, "bind_red_league_funding_execution", lambda *_: league)

    def earn(*_a, **_k):
        actions.actions_executed += 40
        runtime.emulator.frame_count += 500
        return execution

    monkeypatch.setattr(funding, "execute_red_league_funding", earn)
    calls = []

    def return_to_field():
        calls.append("native-return")
        actions.actions_executed += 3
        runtime.emulator.frame_count += 30
        if fault == "cash":
            current.raw.player_money -= 1
        if fault == "field":
            current.input_ready = False
        return GoalExecutionReport(
            4 if fault == "actions" else 3,
            31 if fault == "frames" else 30,
            {"native_league_return_verified": fault != "proof", "nurse_visits": 1},
        )

    binding = funding.bind_autonomous_league_funding(
        runtime,
        actions,
        SimpleNamespace(),
        maximum_actions=1000,
        maximum_frames=10000,
        postgame_return=return_to_field,
    )
    assert not calls and actions.actions_executed == 0
    if fault in {"actions", "frames", "proof"}:
        with pytest.raises(ValueError, match="accounting or native proof"):
            binding.execute()
    else:
        report = binding.execute()
        assert report.actions_executed == 43 and report.frames_executed == 530
        assert report.evidence["league_return"]["nurse_visits"] == 1
        assert binding.verify(report).status is (
            GoalDecisionOutcome.FAILED if fault else GoalDecisionOutcome.SUCCEEDED
        )
        forged = GoalExecutionReport(
            report.actions_executed, report.frames_executed, dict(report.evidence)
        )
        assert binding.verify(forged).status is GoalDecisionOutcome.FAILED
    assert calls == ["native-return"]


def test_non_callable_native_return_fails_without_observation():
    with pytest.raises(ValueError, match="explicit callable"):
        funding.bind_autonomous_league_funding(
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            maximum_actions=1000,
            maximum_frames=10000,
            postgame_return=True,
        )
