"""Expose qualified renewable League income as one autonomous semantic option."""

from __future__ import annotations

from .executor import CountingExecutor
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .goal_resource_quote import GoalResourceQuote
from .provenance import canonical_sha256
from .red_goal_context import RedGoalContextRuntime
from .red_league_funding import RedLeagueFundingError
from .red_league_funding_execution import (
    bind_red_league_funding_execution,
    execute_red_league_funding,
)
from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


def bind_autonomous_league_funding(
    runtime: RedGoalContextRuntime,
    actions: CountingExecutor,
    world: StrategicScenarioRouteWorld,
    *,
    maximum_actions: int,
    maximum_frames: int,
) -> ExecutableGoalBinding | None:
    """Return one cartridge-qualified repeatable income option, without input."""
    try:
        league = bind_red_league_funding_execution(runtime, world)
    except RedLeagueFundingError:
        return None
    qualification = league.qualification
    income = qualification.expected_net_income
    money = league.origin.raw.player_money
    if type(money) is not int or money < 0 or income <= 0:
        return None
    completed = None

    def execute() -> GoalExecutionReport:
        nonlocal completed
        completed = execute_red_league_funding(
            runtime,
            actions,
            world,
            league,
            maximum_actions=maximum_actions,
            maximum_frames=maximum_frames,
        )
        return GoalExecutionReport(
            completed.actions,
            completed.frames,
            {
                "finite_income": False,
                "renewable_income": True,
                "league_funding": completed.public_dict(),
            },
        )

    def verify(report: GoalExecutionReport) -> GoalVerification:
        current = runtime.adapter.observe()
        if (
            completed is None
            or report.actions_executed != completed.actions
            or report.frames_executed != completed.frames
            or report.evidence.get("league_funding") != completed.public_dict()
            or current.raw.player_money != completed.ending_money
            or completed.observed_net_income != income
            or current.raw.battle_state != 0
            or not current.input_ready
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding(
        binding_ref="pokemon.red:funding:repeatable-league:"
        + canonical_sha256(
            {
                "qualification": qualification.public_dict(),
                "origin_money": money,
                "maximum_actions": maximum_actions,
                "maximum_frames": maximum_frames,
            }
        ),
        kind=GoalKind.RESUPPLY,
        estimated_effort=1.0,
        estimated_risk=0.4,
        execute=execute,
        verify=verify,
        resource_quote=GoalResourceQuote(money, 0, (), expected_income=income),
    )


__all__ = ["bind_autonomous_league_funding"]
