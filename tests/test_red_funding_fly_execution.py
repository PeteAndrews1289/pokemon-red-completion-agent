"""A quoted flight is not income: landing, onward route and payout must all verify."""
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_routed_trainer_funding import fixture

from pokemon_red_completion import red_routed_trainer_funding as funding
from pokemon_red_completion.gen1_trainer_sight import TrainerFacing
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.observation import OverworldMovementMode


def flight_fixture(monkeypatch, *, fault=None):
    from pokemon_red_completion import red_funding_fly as flights

    router, state, target, bindings, calls = fixture(monkeypatch)
    target = replace(target, trainer=replace(target.trainer, facing=TrainerFacing.RIGHT))
    monkeypatch.setattr(funding, "trainer_sight_zones", lambda *_: (target.trainer,))
    router.regional_trainer_funding = True
    router.maximum_controller_actions = 6000
    state.raw = replace(state.raw, map_id=32)
    router.runtime.profile.providers[0].parameters["funding_fly_transport"] = True
    selected = flights.FundingFlyCandidate(5, (8, 9), target)
    monkeypatch.setattr(funding, "_candidates", lambda _: ())
    monkeypatch.setattr(flights, "funding_fly_candidates", lambda _: (selected,))
    monkeypatch.setattr(funding, "static_trainer_sight_zones", lambda *_: (target.trainer,))
    router.runtime.reader.read_overworld_movement_mode = lambda: OverworldMovementMode.WALKING

    class FieldPort:
        def __init__(self, actions, reader, emulator):
            assert actions._maximum_actions_per_decision == 256
            assert actions._maximum_episode_actions == 256
            self.fly_receipts = []

        def execute(self, action):
            assert action.value == "fly:vermilion_city"
            calls.append("flight")
            router.actions.actions_executed += 7
            router.runtime.emulator.frame_count += 900
            state.raw = replace(state.raw, map_id=5, player_y=8, player_x=9)
            if fault == "landing":
                state.raw = replace(state.raw, player_x=10)
            if fault == "battle":
                state.raw = replace(state.raw, battle_state=1)
            if fault == "unready":
                state.input_ready = False
            if fault != "receipt":
                self.fly_receipts.append(object())

    monkeypatch.setattr("pokemon_red_completion.gen1_field_moves.Gen1FieldMovePort", FieldPort)

    def requalify(_router, quoted):
        assert quoted == target
        assert (state.raw.map_id, state.raw.player_y, state.raw.player_x) == (5, 8, 9)
        calls.append("observed_route")
        if fault == "onward":
            raise funding.RedTrainerFundingError("no unique observed-terrain approach")
        return target

    monkeypatch.setattr(funding, "_observed_funding_target", requalify)

    def travel(*_args, **_kwargs):
        calls.append("walk")
        router.actions.actions_executed += 3
        router.runtime.emulator.frame_count += 120
        state.raw = replace(state.raw, map_id=22, player_y=10, player_x=36)
        return SimpleNamespace(passed=True)

    monkeypatch.setattr(funding, "execute_route", travel)
    return router, state, bindings, calls, selected


def test_flight_then_fresh_route_then_actual_payout_preserves_choice_and_costs(monkeypatch):
    router, state, original, calls, _ = flight_fixture(monkeypatch)
    offered = funding.bind_local_trainer_funding(router, original, state)
    assert offered.bindings[0] is original.bindings[0]
    assert calls == []
    bound = offered.bindings[-1]
    assert bound.resource_quote.expected_income == 1050
    report = bound.execute()
    assert calls == ["flight", "observed_route", "escort", "walk", "face", "battle"]
    assert report.actions_executed == 13
    assert report.frames_executed == 1050
    assert report.evidence["funding_transport"] == {"verified_flights": 1}
    assert report.evidence["finite_income"] is True
    assert report.evidence["balls_purchased"] == 0
    assert bound.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    with pytest.raises(funding.RedTrainerFundingError, match="consumed"):
        bound.execute()


@pytest.mark.parametrize("fault", ["landing", "battle", "unready", "receipt", "onward"])
def test_bad_flight_or_unavailable_onward_route_never_fights_or_retries(monkeypatch, fault):
    router, state, original, calls, _ = flight_fixture(monkeypatch, fault=fault)
    bound = funding.bind_local_trainer_funding(router, original, state).bindings[-1]
    with pytest.raises(funding.RedTrainerFundingError):
        bound.execute()
    assert "flight" in calls
    assert not {"escort", "walk", "face", "battle"}.intersection(calls)
    with pytest.raises(funding.RedTrainerFundingError, match="consumed"):
        bound.execute()
    assert calls.count("flight") == 1


def test_quote_removed_before_flight_stops_without_any_controller_input(monkeypatch):
    from pokemon_red_completion import red_funding_fly as flights

    router, state, original, calls, _ = flight_fixture(monkeypatch)
    bound = funding.bind_local_trainer_funding(router, original, state).bindings[-1]
    monkeypatch.setattr(flights, "funding_fly_candidates", lambda _: ())
    with pytest.raises(funding.RedTrainerFundingError, match="quote changed"):
        bound.execute()
    assert calls == []


@pytest.mark.parametrize("cap", [11, 6000])
def test_flight_dispatch_uses_smaller_of_local_cap_and_256(monkeypatch, cap):
    from pokemon_red_completion.goal_manager_composition_qualification import (
        CompositionActionBudgetExhausted,
    )

    router, state, original, calls, _ = flight_fixture(monkeypatch)
    router.maximum_controller_actions = cap
    router.actions.execute = lambda action: calls.append("primitive")

    class NeverLandingPort:
        def __init__(self, actions, reader, emulator):
            self.actions = actions
            self.fly_receipts = []

        def execute(self, action):
            for _ in range(257):
                self.actions.execute(action)

    monkeypatch.setattr(
        "pokemon_red_completion.gen1_field_moves.Gen1FieldMovePort", NeverLandingPort,
    )
    bound = funding.bind_local_trainer_funding(router, original, state).bindings[-1]
    with pytest.raises(CompositionActionBudgetExhausted):
        bound.execute()
    assert calls == ["primitive"] * (11 if cap == 11 else 256)
    with pytest.raises(funding.RedTrainerFundingError, match="consumed"):
        bound.execute()


@pytest.mark.parametrize("flag", [None, False, 1, "true"])
def test_old_or_nonboolean_fly_flag_never_opens_remote_income(monkeypatch, flag):
    from pokemon_red_completion import red_funding_fly as flights

    router, state, original, calls, _ = flight_fixture(monkeypatch)
    router.runtime.profile.providers[0].parameters["funding_fly_transport"] = flag
    monkeypatch.setattr(flights, "funding_fly_candidates", lambda _: pytest.fail("legacy flight"))
    assert funding.bind_local_trainer_funding(router, original, state) is original
    assert calls == []
