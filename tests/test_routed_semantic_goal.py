from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from pokemon_red_completion.goal_manager import (
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalKind,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.routed_semantic_goal import (
    FreshDestinationGoalOffer,
    RoutedSemanticBudgetCheckpoint,
    RoutedSemanticGoalComposer,
    RoutedSemanticGoalError,
    RoutedSemanticGoalLimits,
    RoutedSemanticRouteBinding,
)

ORIGIN = "a" * 64
TERMINAL = "b" * 64
FRESH = "c" * 64


@dataclass(slots=True)
class _Meter:
    actions: int = 0
    frames: int = 0

    def checkpoint(self) -> RoutedSemanticBudgetCheckpoint:
        return RoutedSemanticBudgetCheckpoint(self.actions, self.frames)

    def spend(self, actions: int, frames: int) -> None:
        self.actions += actions
        self.frames += frames


def _composer(
    *,
    route_verification: GoalVerification | None = None,
    destination_verification: GoalVerification | None = None,
    route_spend: tuple[int, int] = (3, 30),
    route_report: tuple[int, int] | None = None,
    destination_spend: tuple[int, int] = (2, 20),
    destination_report: tuple[int, int] | None = None,
    route_verifier_spend: tuple[int, int] = (0, 0),
    binder_spend: tuple[int, int] = (0, 0),
    destination_verifier_spend: tuple[int, int] = (0, 0),
    observation_sha256: str = FRESH,
    destination_boundary_sha256: str = TERMINAL,
    offered_kind: GoalKind = GoalKind.RESUPPLY,
    destination_ref: str = "private:destination",
    unavailable_reason: GoalUnavailableReason | None = None,
    limits: RoutedSemanticGoalLimits | None = None,
) -> tuple[
    RoutedSemanticGoalComposer,
    ExecutableGoalBinding,
    _Meter,
    list[str],
]:
    meter = _Meter()
    events: list[str] = []
    route_verdict = route_verification or GoalVerification.succeeded()
    destination_verdict = destination_verification or GoalVerification.succeeded()
    route_values = route_spend if route_report is None else route_report
    destination_values = (
        destination_spend if destination_report is None else destination_report
    )

    def execute_route() -> GoalExecutionReport:
        events.append("route_execute")
        meter.spend(*route_spend)
        return GoalExecutionReport(*route_values, {"private_route": True})

    def verify_route(_report: GoalExecutionReport) -> GoalVerification:
        events.append("route_verify")
        meter.spend(*route_verifier_spend)
        return route_verdict

    route = RoutedSemanticRouteBinding(
        binding_ref="private:transport",
        origin_observation_sha256=ORIGIN,
        terminal_boundary_sha256=TERMINAL,
        execute=execute_route,
        verify=verify_route,
    )

    def execute_destination() -> GoalExecutionReport:
        events.append("destination_execute")
        meter.spend(*destination_spend)
        return GoalExecutionReport(
            *destination_values,
            {"semantic_destination": offered_kind.value},
        )

    def verify_destination(_report: GoalExecutionReport) -> GoalVerification:
        events.append("destination_verify")
        meter.spend(*destination_verifier_spend)
        return destination_verdict

    destination = ExecutableGoalBinding(
        binding_ref=destination_ref,
        kind=offered_kind,
        estimated_effort=0.2,
        estimated_risk=0.1,
        execute=execute_destination,
        verify=verify_destination,
    )

    def bind_destination() -> FreshDestinationGoalOffer:
        events.append("fresh_bind")
        meter.spend(*binder_spend)
        if unavailable_reason is not None:
            return FreshDestinationGoalOffer.unavailable(
                observation_sha256=observation_sha256,
                terminal_boundary_sha256=destination_boundary_sha256,
                kind=offered_kind,
                reason=unavailable_reason,
            )
        return FreshDestinationGoalOffer.available(
            observation_sha256=observation_sha256,
            terminal_boundary_sha256=destination_boundary_sha256,
            binding=destination,
        )

    composer = RoutedSemanticGoalComposer(
        binding_ref="private:composite",
        destination_kind=GoalKind.RESUPPLY,
        estimated_effort=0.5,
        estimated_risk=0.2,
        route=route,
        bind_fresh_destination=bind_destination,
        budget_meter=meter,
        limits=limits or RoutedSemanticGoalLimits(10, 100),
    )
    return composer, composer.binding(), meter, events


def test_success_keeps_route_out_of_the_policy_kind_and_verifies_in_order() -> None:
    composer, binding, _meter, events = _composer()

    report = binding.execute()

    assert binding.kind is GoalKind.RESUPPLY
    assert report.actions_executed == 5
    assert report.frames_executed == 50
    assert report.evidence["route_verified"] is True
    assert report.evidence["destination_bound"] is True
    assert report.evidence["destination_executed"] is True
    assert report.evidence["destination_kind"] == "resupply"
    assert report.evidence["route_is_policy_kind"] is False
    assert events == [
        "route_execute",
        "route_verify",
        "fresh_bind",
        "destination_execute",
    ]

    assert binding.verify(report) == GoalVerification.succeeded()
    assert events[-1] == "destination_verify"
    public = composer.public_dict()
    encoded = json.dumps(public, sort_keys=True)
    assert public["destination_kind"] == "resupply"
    assert public["route_is_policy_kind"] is False
    assert public["teacher_route"] is False
    for private in ("private:transport", "private:destination", ORIGIN, TERMINAL):
        assert private not in encoded


def test_route_failure_never_binds_or_executes_the_destination() -> None:
    _composer_value, binding, _meter, events = _composer(
        route_verification=GoalVerification.failed(
            GoalFailureReason.OUTCOME_NOT_VERIFIED
        )
    )

    report = binding.execute()
    verdict = binding.verify(report)

    assert verdict == GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
    assert events == ["route_execute", "route_verify"]
    assert report.evidence["destination_bound"] is False


@pytest.mark.parametrize(
    ("observation", "boundary", "kind", "destination_ref", "message"),
    (
        (ORIGIN, TERMINAL, GoalKind.RESUPPLY, "private:destination", "origin observation"),
        (FRESH, "d" * 64, GoalKind.RESUPPLY, "private:destination", "boundary differs"),
        (FRESH, TERMINAL, GoalKind.EVOLVE_SPECIES, "private:destination", "goal kind"),
        (FRESH, TERMINAL, GoalKind.RESUPPLY, "private:transport", "masquerade"),
    ),
)
def test_fresh_destination_join_rejects_stale_or_drifted_identity(
    observation: str,
    boundary: str,
    kind: GoalKind,
    destination_ref: str,
    message: str,
) -> None:
    _composer_value, binding, _meter, events = _composer(
        observation_sha256=observation,
        destination_boundary_sha256=boundary,
        offered_kind=kind,
        destination_ref=destination_ref,
    )

    with pytest.raises(RoutedSemanticGoalError, match=message):
        binding.execute()

    assert events == ["route_execute", "route_verify", "fresh_bind"]


def test_unavailable_fresh_destination_settles_without_executing_an_alternate() -> None:
    _composer_value, binding, _meter, events = _composer(
        unavailable_reason=GoalUnavailableReason.MISSING_RESOURCE
    )

    report = binding.execute()

    assert binding.verify(report) == GoalVerification.failed(
        GoalFailureReason.BINDING_FAILED
    )
    assert events == ["route_execute", "route_verify", "fresh_bind"]
    assert report.evidence["destination_bound"] is False
    assert report.evidence["destination_executed"] is False


def test_route_self_report_must_match_the_independent_meter() -> None:
    _composer_value, binding, _meter, events = _composer(route_report=(2, 30))

    report = binding.execute()

    assert binding.verify(report) == GoalVerification.failed(
        GoalFailureReason.BINDING_FAILED
    )
    assert events == ["route_execute", "route_verify"]
    assert report.evidence["budget_reconciled"] is False


def test_route_verifier_must_be_action_free() -> None:
    _composer_value, binding, _meter, events = _composer(
        route_verifier_spend=(1, 1)
    )

    report = binding.execute()

    assert binding.verify(report) == GoalVerification.failed(
        GoalFailureReason.BINDING_FAILED
    )
    assert events == ["route_execute", "route_verify"]


def test_fresh_destination_binder_must_be_action_free() -> None:
    _composer_value, binding, _meter, events = _composer(binder_spend=(1, 1))

    report = binding.execute()

    assert binding.verify(report) == GoalVerification.failed(
        GoalFailureReason.BINDING_FAILED
    )
    assert events == ["route_execute", "route_verify", "fresh_bind"]


def test_destination_self_report_and_total_must_match_the_independent_meter() -> None:
    _composer_value, binding, _meter, events = _composer(
        destination_report=(1, 20)
    )

    report = binding.execute()

    assert binding.verify(report) == GoalVerification.failed(
        GoalFailureReason.BINDING_FAILED
    )
    assert events[-1] == "destination_verify"
    assert report.evidence["budget_reconciled"] is False


@pytest.mark.parametrize(
    "limits",
    (
        RoutedSemanticGoalLimits(2, 100),
        RoutedSemanticGoalLimits(10, 29),
    ),
)
def test_route_budget_exhaustion_stops_before_destination(
    limits: RoutedSemanticGoalLimits,
) -> None:
    _composer_value, binding, _meter, events = _composer(limits=limits)

    report = binding.execute()

    assert binding.verify(report) == GoalVerification.failed(
        GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED
    )
    assert events == ["route_execute", "route_verify"]


def test_whole_composite_budget_includes_destination_execution() -> None:
    _composer_value, binding, _meter, events = _composer(
        limits=RoutedSemanticGoalLimits(4, 100)
    )

    report = binding.execute()

    assert binding.verify(report) == GoalVerification.failed(
        GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED
    )
    assert events[-1] == "destination_verify"
    assert report.evidence["within_budget"] is False


def test_destination_verdict_remains_the_semantic_outcome() -> None:
    expected = GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
    _composer_value, binding, _meter, events = _composer(
        destination_verification=expected
    )

    report = binding.execute()

    assert binding.verify(report) == expected
    assert events[-1] == "destination_verify"


def test_destination_verifier_cannot_hide_controller_or_frame_effects() -> None:
    _composer_value, binding, _meter, _events = _composer(
        destination_verifier_spend=(1, 1)
    )

    report = binding.execute()

    assert binding.verify(report) == GoalVerification.failed(
        GoalFailureReason.WORLD_STATE_DIVERGED
    )


def test_external_budget_drift_between_execute_and_verify_fails_closed() -> None:
    _composer_value, binding, meter, _events = _composer()

    report = binding.execute()
    meter.spend(1, 1)

    assert binding.verify(report) == GoalVerification.failed(
        GoalFailureReason.WORLD_STATE_DIVERGED
    )


def test_execution_and_verification_are_each_single_use() -> None:
    composer, binding, _meter, _events = _composer()
    report = binding.execute()

    with pytest.raises(RoutedSemanticGoalError, match="already executed"):
        binding.execute()
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    with pytest.raises(RoutedSemanticGoalError, match="already verified"):
        binding.verify(report)
    with pytest.raises(RoutedSemanticGoalError, match="already constructed"):
        composer.binding()


def test_verifier_rejects_an_equal_but_unbound_report() -> None:
    _composer_value, binding, _meter, _events = _composer()
    report = binding.execute()
    substitute = GoalExecutionReport(
        report.actions_executed,
        report.frames_executed,
        dict(report.evidence),
    )

    with pytest.raises(RoutedSemanticGoalError, match="different report"):
        binding.verify(substitute)


def test_process_interruption_propagates_and_consumes_the_composer() -> None:
    meter = _Meter()
    route = RoutedSemanticRouteBinding(
        binding_ref="private:transport",
        origin_observation_sha256=ORIGIN,
        terminal_boundary_sha256=TERMINAL,
        execute=lambda: (_ for _ in ()).throw(KeyboardInterrupt()),
        verify=lambda _report: GoalVerification.succeeded(),
    )
    composer = RoutedSemanticGoalComposer(
        binding_ref="private:composite",
        destination_kind=GoalKind.RESUPPLY,
        estimated_effort=0.5,
        estimated_risk=0.2,
        route=route,
        bind_fresh_destination=lambda: pytest.fail("destination must stay untouched"),
        budget_meter=meter,
        limits=RoutedSemanticGoalLimits(10, 100),
    )
    binding = composer.binding()

    with pytest.raises(KeyboardInterrupt):
        binding.execute()
    with pytest.raises(RoutedSemanticGoalError, match="already executed"):
        binding.execute()
