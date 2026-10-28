"""Funding approach evidence survives both completed routes and failed prefixes."""

from types import SimpleNamespace

import pytest
from test_red_regional_trainer_funding import candidates, region  # noqa: F401

from pokemon_red_completion import red_routed_trainer_funding as funding
from pokemon_red_completion.route_executor import (
    ExecutedRouteStep,
    RouteExecutionError,
    RouteExecutionFailureReason,
    RouteExecutionFailureReport,
    RouteExecutionReport,
    TraversalSnapshot,
)


@pytest.mark.parametrize("failed", [False, True])
def test_route_log_records_plan_and_acknowledged_prefix(region, monkeypatch, failed):  # noqa: F811
    plan = candidates(region)[0].approach
    receipts = (ExecutedRouteStep(plan.steps[0], 1, 0),)
    terminal = TraversalSnapshot(plan.terminal_map, plan.terminal_at, True, mode="land")
    records = []
    router = SimpleNamespace(runtime=SimpleNamespace(trainer_funding_event_sink=records.append))
    report = RouteExecutionReport(plan, terminal, receipts, (), (), 1, 0)
    error = RouteExecutionError("blocked")
    error.attach_failure(
        RouteExecutionFailureReport(
            plan,
            RouteExecutionFailureReason.WORLD_STATE_DIVERGED,
            terminal,
            receipts,
            (),
            (),
            1,
            0,
        )
    )

    def execute(*args, **kwargs):
        if failed:
            raise error
        return report

    monkeypatch.setattr(funding, "execute_route", execute)
    if failed:
        with pytest.raises(RouteExecutionError) as caught:
            funding._execute_recorded_route(router, "trainer_approach", plan)
        assert caught.value is error
        assert len(records[-1]["acknowledged_steps"]) == 1
    else:
        assert funding._execute_recorded_route(router, "trainer_approach", plan) is report
        assert records[-1]["report"]["acknowledged_steps"] == 1
    assert records[0]["event"] == "route_started"
    assert records[0]["steps"][0]["expected_at"] == plan.steps[0].expected_at
    assert records[-1]["event"] == ("route_failed" if failed else "route_finished")
