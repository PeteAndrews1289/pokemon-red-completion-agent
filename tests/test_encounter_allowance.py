from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.encounter_allowance import (
    HUNTING_ENCOUNTER_CEILING,
    TRAVEL_ENCOUNTER_CEILING,
    EncounterAllowance,
    EncounterLimitedMovementPort,
)


def test_profiles_and_prior_costs():
    assert TRAVEL_ENCOUNTER_CEILING == 512
    assert HUNTING_ENCOUNTER_CEILING == 4096
    budget = EncounterAllowance(TRAVEL_ENCOUNTER_CEILING, 16)
    assert budget.remaining == 496
    budget.require_capacity(495)
    with pytest.raises(ValueError, match="exhausted"):
        budget.require_capacity(496)
    with pytest.raises(ValueError, match="exhausted"):
        budget.require_capacity(497)


@pytest.mark.parametrize(
    "maximum,prior", [(0, 0), (-1, 0), (True, 0), (1.5, 0), (2, -1), (2, 3), (2, True), (2, 0.5)]
)
def test_invalid_allowances(maximum, prior):
    with pytest.raises(ValueError):
        EncounterAllowance(maximum, prior)


@pytest.mark.parametrize("count", [-1, True, 1.5])
def test_invalid_current_cost(count):
    with pytest.raises(ValueError):
        EncounterAllowance(512).require_capacity(count)


def test_guard_stops_movement_but_allows_settlement_and_shares_leg_costs():
    seen, receipts = [], []
    delegate = SimpleNamespace(execute=lambda action: seen.append(action) or "forwarded")
    allowance = EncounterAllowance(512, 510)
    port = EncounterLimitedMovementPort(delegate, allowance, lambda: len(receipts))
    move = MacroAction(MacroActionKind.MOVE, "up")
    assert port.execute(move) == "forwarded"
    receipts.append(object())
    port.execute(move)
    receipts.append(object())
    with pytest.raises(ValueError, match="exhausted"):
        port.execute(move)
    another_leg = EncounterLimitedMovementPort(delegate, allowance, lambda: len(receipts))
    with pytest.raises(ValueError, match="exhausted"):
        another_leg.execute(move)
    assert len(seen) == 2
    wait = MacroAction(MacroActionKind.WAIT, "settle")
    assert port.execute(wait) == "forwarded"
    assert seen[-1] == wait


def test_delegate_resource_or_action_failure_is_not_swallowed():
    def fail(action):
        raise RuntimeError("resource/action/frame safeguard")

    port = EncounterLimitedMovementPort(
        SimpleNamespace(execute=fail), EncounterAllowance(512), lambda: 0
    )
    with pytest.raises(RuntimeError, match="safeguard"):
        port.execute(MacroAction(MacroActionKind.MOVE, "up"))


def test_consumed_allowance_stops_before_any_movement():
    with pytest.raises(ValueError, match="exhausted"):
        EncounterAllowance(512, 512).require_capacity(0)
