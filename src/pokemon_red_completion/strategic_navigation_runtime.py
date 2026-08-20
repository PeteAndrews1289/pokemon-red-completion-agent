"""Execute one recorded strategic choice through the deterministic route stack."""

from __future__ import annotations

from pokemon_red_completion.route_executor import (
    DEFAULT_ROUTE_EXECUTION_LIMITS,
    InterruptionHandler,
    RouteActionPort,
    RouteExecutionError,
    RouteExecutionLimits,
    RouteExecutionReport,
    RouteReplanner,
    RouteResourceManager,
    TraversalObserver,
    execute_route,
)
from pokemon_red_completion.strategic_navigation import StrategicNavigationTag
from pokemon_red_completion.strategic_navigation_binding import DestinationRouteBinding
from pokemon_red_completion.strategic_navigation_trajectory import (
    StrategicNavigationTrajectoryObserver,
)


def execute_strategic_navigation_route(
    trajectory: StrategicNavigationTrajectoryObserver,
    *,
    semantic_need_tags: tuple[StrategicNavigationTag, ...],
    origin_semantic_tags: tuple[StrategicNavigationTag, ...],
    origin_region_ref: str,
    bindings: tuple[DestinationRouteBinding, ...],
    selected_destination_ref: str,
    actions: RouteActionPort,
    traversal_observer: TraversalObserver,
    interruption_handler: InterruptionHandler | None = None,
    replanner: RouteReplanner | None = None,
    resource_manager: RouteResourceManager | None = None,
    limits: RouteExecutionLimits = DEFAULT_ROUTE_EXECUTION_LIMITS,
) -> RouteExecutionReport:
    """Record-before-act and consume exactly one measured route outcome."""

    if not isinstance(trajectory, StrategicNavigationTrajectoryObserver):
        raise TypeError("trajectory must be a StrategicNavigationTrajectoryObserver")
    bound = trajectory.bind_decision(
        semantic_need_tags=semantic_need_tags,
        origin_semantic_tags=origin_semantic_tags,
        origin_region_ref=origin_region_ref,
        bindings=bindings,
        selected_destination_ref=selected_destination_ref,
    )
    try:
        report = execute_route(
            bound.selected_plan,
            actions,
            traversal_observer,
            interruption_handler=interruption_handler,
            replanner=replanner,
            resource_manager=resource_manager,
            limits=limits,
        )
    except RouteExecutionError as error:
        if error.failure is None:  # pragma: no cover - execute_route owns this invariant
            trajectory.recorder.note_instrumentation_failure()
            raise
        trajectory.record_outcome(bound.failed_route_record(error.failure))
        trajectory.require_settled()
        raise
    trajectory.record_outcome(bound.successful_record(report))
    trajectory.require_settled()
    return report
