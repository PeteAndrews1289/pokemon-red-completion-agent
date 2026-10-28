"""Expose qualified renewable League income as one autonomous semantic option."""

from __future__ import annotations

from collections.abc import Callable

from .executor import CountingExecutor
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .goal_resource_quote import GoalResourceQuote
from .provenance import canonical_sha256
from .red_goal_context import RedGoalContextRuntime
from .red_league_funding import RedLeagueFundingError
from .red_league_funding_execution import (
    ScopedLeagueIncomeReuse,
    RedLeagueFundingExecutionError, RedLeagueFundingBattleLoss,
    bind_red_league_funding_execution,
    execute_red_league_funding,
)
from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


def level100_owned_income_reserve_targets(raw) -> tuple[int, int, int] | None:
    """Narrow DEVELOPMENT reserve for the measured six-member earned cohort.

    This is disclosed medicine support, not a battle-winning guarantee or a
    replacement for native income qualification. One retained copy won all five
    rooms with a level100 carry, reserves at least53, six Revives and one Full
    Heal, consuming two Revives/one Full Heal and no Full Restore.
    """
    levels = getattr(raw, "party_levels", None)
    if (
        not isinstance(levels, tuple)
        or len(levels) != 6
        or any(type(level) is not int or not 53 <= level <= 100 for level in levels)
        or max(levels) != 100
    ):
        return None
    return (0, 6, 1)


def bind_autonomous_league_funding(
    runtime: RedGoalContextRuntime,
    actions: CountingExecutor,
    world: StrategicScenarioRouteWorld,
    *,
    maximum_actions: int,
    maximum_frames: int,
    postgame_return: Callable[[], GoalExecutionReport] | None = None,
    development_reuse: ScopedLeagueIncomeReuse | None = None,
) -> ExecutableGoalBinding | None:
    """Return one cartridge-qualified repeatable income option, without input."""
    if postgame_return is not None and not callable(postgame_return):
        raise ValueError("League postgame return must be an explicit callable")
    if development_reuse is not None and type(development_reuse) is not ScopedLeagueIncomeReuse:
        raise TypeError('Income reuse requires its exact-room DEVELOPMENT declaration')
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
    completed_report = None
    returned = None
    lost_terminal = None

    def execute() -> GoalExecutionReport:
        nonlocal completed, completed_report, returned, lost_terminal
        first_actions = getattr(actions, "actions_executed", None)
        first_frames = getattr(getattr(runtime, "emulator", None), "frame_count", None)
        try:
            completed = execute_red_league_funding(
                runtime,
                actions,
                world,
                league,
                maximum_actions=maximum_actions,
                maximum_frames=maximum_frames,
                **({"development_reuse": development_reuse} if development_reuse is not None else {}),
            )
        except RedLeagueFundingExecutionError as error:
            from hashlib import sha256
            cause = error.__cause__
            if not isinstance(cause, RedLeagueFundingBattleLoss) or error.progress is None:
                raise
            if type(first_actions) is not int or type(first_frames) is not int:
                raise
            certificate = cause.certificate
            current = runtime.adapter.observe()
            lost_terminal = runtime.emulator.save_state_bytes()
            if (certificate.get("terminal_sha256") != sha256(lost_terminal).hexdigest()
                    or current.raw.battle_state or not current.input_ready
                    or runtime.emulator.pressed_buttons
                    or certificate.get("ending_money") != current.raw.player_money
                    or error.progress.phase != "battle:" + certificate.get("objective_id", "")):
                raise
            completed_report = GoalExecutionReport(
                actions.actions_executed - first_actions,
                runtime.emulator.frame_count - first_frames,
                dict(status="lost", no_income_credit=True, native_league_funding_loss=certificate,
                     league_progress=error.progress.public_dict(),
                     native_error_chain=[dict(error_type=type(error).__name__,error=str(error)),
                                         dict(error_type=type(cause).__name__,error=str(cause)),
                                         dict(error_type=type(cause.__cause__).__name__,error=str(cause.__cause__))]),
            )
            return completed_report
        evidence = {
            "finite_income": False,
            "renewable_income": True,
            "league_funding": completed.public_dict(),
        }
        if development_reuse is not None:
            evidence['development_battle_reuse'] = development_reuse.public_dict()
        extra_actions = extra_frames = 0
        if postgame_return is not None:
            before_actions, before_frames = actions.actions_executed, runtime.emulator.frame_count
            returned = postgame_return()
            extra_actions = actions.actions_executed - before_actions
            extra_frames = runtime.emulator.frame_count - before_frames
            if (not isinstance(returned, GoalExecutionReport)
                or returned.actions_executed != extra_actions
                or returned.frames_executed != extra_frames
                or returned.evidence.get("native_league_return_verified") is not True
                or extra_actions < 0 or extra_frames < 0):
                raise ValueError("League postgame return accounting or native proof differs")
            evidence["league_return"] = dict(returned.evidence)
            evidence["postgame_return_mechanics"] = "native Continue and verified field restoration"
        completed_report = GoalExecutionReport(
            completed.actions + extra_actions, completed.frames + extra_frames, evidence,
        )
        return completed_report

    def verify(report: GoalExecutionReport) -> GoalVerification:
        current = runtime.adapter.observe()
        if lost_terminal is not None:
            if (report is not completed_report or runtime.emulator.save_state_bytes() != lost_terminal
                    or current.raw.battle_state or not current.input_ready
                    or runtime.emulator.pressed_buttons
                    or report.evidence.get("status") != "lost"
                    or report.evidence.get("no_income_credit") is not True):
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            return GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
        if (
            completed is None
            or report is not completed_report
            or report.evidence.get("league_funding") != completed.public_dict()
            or (development_reuse is not None and report.evidence.get(
                'development_battle_reuse') != development_reuse.public_dict())
            or (postgame_return is not None and (returned is None
                or report.evidence.get("league_return") != dict(returned.evidence)))
            or current.raw.player_money != completed.ending_money
            or completed.observed_net_income != income
            or completed.observed_net_income - completed.field_item_replacement_cost <= 0
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
                **({"native_postgame_return": True} if postgame_return is not None else {}),
                **({"development_battle_reuse": development_reuse.public_dict()}
                   if development_reuse is not None else {}),
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


def compose_native_funding_loss(report, verdict, *, actions, frames, cash_before,
                                cash_after, purchase_cost, pre_entry_support):
    """Carry failed income through approved medicine support without win credit."""
    if (not isinstance(report, GoalExecutionReport)
            or verdict != GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
            or report.evidence.get("status") != "lost"
            or report.evidence.get("no_income_credit") is not True
            or not isinstance(report.evidence.get("native_league_funding_loss"), dict)):
        return None
    values = (actions, frames, cash_before, cash_after, purchase_cost)
    if (any(type(x) is not int or x < 0 for x in values)
            or actions < report.actions_executed or frames < report.frames_executed
            or purchase_cost > cash_before
            or report.evidence["native_league_funding_loss"].get("ending_money") != cash_after):
        raise ValueError("native funding loss support cost accounting differs")
    return GoalExecutionReport(actions, frames, dict(
        report.evidence, pre_entry_support=pre_entry_support,
        medicine_procurement_learned=False, pre_entry_purchase_cost=purchase_cost,
        observed_total_net_income=cash_after-cash_before,
        gross_battle_income=None, failed_funding=True,
        medicine_cost_already_in_net_cash=True,
    ))
