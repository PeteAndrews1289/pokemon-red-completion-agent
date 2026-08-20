"""First bounded Crystal bindings over the shared closed-loop route executor.

This is deliberately a two-room vertical slice, not a Crystal walkthrough.
The map identifiers, coordinates, and binding references stay on the adapter
side.  The portable goal manager sees only normalized pressures, semantic goal
kinds, availability, effort, and risk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pokemon_crystal_completion.goal_bindings import (
    CapabilityBoundCrystalGoalProvider,
    CrystalGoalOpportunityEnumerator,
)
from pokemon_crystal_completion.goal_state import (
    CrystalCampaignSnapshot,
    CrystalCapability,
    CrystalCapabilityState,
    CrystalGoalObservation,
    project_crystal_goal_state,
)
from pokemon_crystal_completion.observation import read_crystal_observation_bundle
from pokemon_crystal_completion.qualification import (
    CrystalQualificationController,
    read_crystal_qualification_runtime,
)
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import ControllerTiming, ExecutedAction, FrameSafeExecutor
from pokemon_red_completion.global_router import MacroEdge, MacroGraph
from pokemon_red_completion.goal_manager import (
    GoalFailureReason,
    GoalKind,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.goal_manager_state import CompletionProgress
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_executor import (
    RouteExecutionLimits,
    RouteExecutionReport,
    TraversalSnapshot,
    execute_route,
)
from pokemon_red_completion.route_plan import RoutePlan, plan_route

CRYSTAL_MAP_NUMBER_BASE = 0x100
CRYSTAL_STORY_BADGE_TARGET = 16
CRYSTAL_SOURCE_MAP_TARGET = 388
CRYSTAL_ROUTE_EFFORT_REFERENCE_STEPS = 64

CRYSTAL_PLAYERS_HOUSE_1F = 24 * CRYSTAL_MAP_NUMBER_BASE + 6
CRYSTAL_PLAYERS_HOUSE_2F = 24 * CRYSTAL_MAP_NUMBER_BASE + 7
CRYSTAL_STARTING_BEDROOM_AT = (3, 3)
CRYSTAL_FIRST_FLOOR_ARRIVAL_AT = (9, 1)

CRYSTAL_ROUTE_TIMING = ControllerTiming(
    press_frames=6,
    release_frames=180,
    wait_frames=1,
)
CRYSTAL_ROUTE_LIMITS = RouteExecutionLimits(
    max_step_attempts=2,
    max_readiness_waits=4,
    max_interruptions=1,
    max_replans=1,
    max_resource_renewals=1,
    replan_after_unchanged=2,
    retry_wait_frames=24,
    readiness_wait_frames=24,
    transition_settle_frames=120,
)
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40,64}$")
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CrystalVerticalSliceError(RuntimeError):
    """Raised when the bounded Crystal slice cannot prove its live boundary."""


@dataclass(frozen=True, slots=True)
class CrystalStartingVerticalSliceQualification:
    """Path-free result of the two real, unscored starting bindings."""

    source_commit: str
    plan_sha256: str
    rom_sha1: str
    rom_sha256: str
    setup_transcript_sha256: str
    policy_question_sha256: str
    setup_actions: int
    menu_close_actions: int
    exploration_actions: int
    exploration_frames: int
    exploration_semantic_steps: int
    story_actions: int
    story_frames: int
    story_semantic_steps: int
    available_goal_kinds: tuple[GoalKind, ...]
    exploration_verified: bool
    story_verified: bool
    controller_released: bool
    rom_unchanged: bool

    def __post_init__(self) -> None:
        if not isinstance(self.source_commit, str) or _GIT_COMMIT.fullmatch(
            self.source_commit
        ) is None:
            raise CrystalVerticalSliceError("Crystal slice source commit is invalid")
        for name in (
            "plan_sha256",
            "rom_sha256",
            "setup_transcript_sha256",
            "policy_question_sha256",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise CrystalVerticalSliceError(f"Crystal slice {name} is invalid")
        if not isinstance(self.rom_sha1, str) or _SHA1.fullmatch(self.rom_sha1) is None:
            raise CrystalVerticalSliceError("Crystal slice ROM SHA-1 is invalid")
        for name in (
            "setup_actions",
            "menu_close_actions",
            "exploration_actions",
            "exploration_frames",
            "exploration_semantic_steps",
            "story_actions",
            "story_frames",
            "story_semantic_steps",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 1:  # noqa: E721
                raise CrystalVerticalSliceError(f"Crystal slice {name} is invalid")
        if self.menu_close_actions != 2:
            raise CrystalVerticalSliceError("Crystal slice menu-close action count differs")
        if self.available_goal_kinds != (GoalKind.ADVANCE_STORY, GoalKind.EXPLORE):
            raise CrystalVerticalSliceError("Crystal slice available goal menu differs")
        for name in (
            "exploration_verified",
            "story_verified",
            "controller_released",
            "rom_unchanged",
        ):
            if not isinstance(getattr(self, name), bool):
                raise CrystalVerticalSliceError(f"Crystal slice {name} is invalid")
        if not all(
            (
                self.exploration_verified,
                self.story_verified,
                self.controller_released,
                self.rom_unchanged,
            )
        ):
            raise CrystalVerticalSliceError("Crystal starting vertical slice did not qualify")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.crystal.starting-vertical-slice-qualification.v1",
            "status": "passed",
            "source_commit": self.source_commit,
            "plan_sha256": self.plan_sha256,
            "rom": {"sha1": self.rom_sha1, "sha256": self.rom_sha256},
            "setup": {
                "clean_power": True,
                "transcript_sha256": self.setup_transcript_sha256,
                "actions": self.setup_actions,
                "menu_close_actions": self.menu_close_actions,
                "actual_in_game_save": True,
            },
            "total_controller_actions": (
                self.setup_actions
                + self.menu_close_actions
                + self.exploration_actions
                + self.story_actions
            ),
            "policy_question_sha256": self.policy_question_sha256,
            "available_goal_kinds": [kind.value for kind in self.available_goal_kinds],
            "exploration_binding": {
                "verified": self.exploration_verified,
                "actions": self.exploration_actions,
                "frames": self.exploration_frames,
                "semantic_steps": self.exploration_semantic_steps,
                "returned_to_start": True,
            },
            "story_binding": {
                "verified": self.story_verified,
                "actions": self.story_actions,
                "frames": self.story_frames,
                "semantic_steps": self.story_semantic_steps,
                "changed_map": True,
            },
            "checks": {
                "controller_released": self.controller_released,
                "rom_unchanged": self.rom_unchanged,
            },
            "experiment": {
                "context_opened": False,
                "teacher_executed": False,
                "prediction_computed": False,
                "zero_shot_opened": 0,
                "adaptation_opened": 0,
                "sealed_test_opened": 0,
            },
            "imitation_target_created": False,
            "private_path_fields": 0,
            "private_location_identity_fields": 0,
            "raw_address_fields": 0,
        }


def crystal_map_id(group: int, number: int) -> int:
    """Pack public Crystal map group/number bytes for the generic router."""

    for name, value in (("group", group), ("number", number)):
        if type(value) is not int or not 1 <= value <= 0xFF:  # noqa: E721
            raise CrystalVerticalSliceError(f"Crystal map {name} is invalid")
    return group * CRYSTAL_MAP_NUMBER_BASE + number


def split_crystal_map_id(map_id: int) -> tuple[int, int]:
    if type(map_id) is not int or map_id <= CRYSTAL_MAP_NUMBER_BASE:  # noqa: E721
        raise CrystalVerticalSliceError("packed Crystal map id is invalid")
    group, number = divmod(map_id, CRYSTAL_MAP_NUMBER_BASE)
    if not 1 <= group <= 0xFF or not 1 <= number <= 0xFF:
        raise CrystalVerticalSliceError("packed Crystal map id is invalid")
    return group, number


@dataclass(slots=True)
class CrystalTraversalPort:
    """Crystal controller/observer adapter for the shared route executor."""

    controller: CrystalQualificationController
    timing: ControllerTiming = CRYSTAL_ROUTE_TIMING
    _executor: FrameSafeExecutor = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.timing, ControllerTiming):
            raise TypeError("timing must be ControllerTiming")
        self._executor = FrameSafeExecutor(self.controller, self.timing)

    def execute(self, action: MacroAction) -> ExecutedAction:
        if not isinstance(action, MacroAction):
            raise TypeError("action must be MacroAction")
        if action.kind not in {MacroActionKind.MOVE, MacroActionKind.WAIT}:
            raise CrystalVerticalSliceError("Crystal traversal accepts only movement and waits")
        return self._executor.execute(action)

    def observe(self) -> TraversalSnapshot:
        runtime = read_crystal_qualification_runtime(self.controller)
        interruption = "battle" if runtime.battle_mode else None
        return TraversalSnapshot(
            map_id=crystal_map_id(runtime.map_group, runtime.map_number),
            at=(runtime.x, runtime.y),
            ready=runtime.input_ready and interruption is None,
            interruption=interruption,
        )


def crystal_starting_navigation_graphs() -> tuple[MacroGraph, dict[int, LocalGraph]]:
    """Return only the source-derived corridor used by the first live slice."""

    upstairs_edges = (
        ((3, 3), (4, 3), "right"),
        ((4, 3), (5, 3), "right"),
        ((5, 3), (6, 3), "right"),
        ((6, 3), (7, 3), "right"),
        ((7, 3), (7, 2), "up"),
        ((7, 2), (7, 1), "up"),
        ((7, 1), (7, 0), "up"),
    )
    downstairs_edges = (((9, 1), (9, 0), "up"),)
    local_graphs = {
        CRYSTAL_PLAYERS_HOUSE_2F: _bidirectional_local_graph(upstairs_edges),
        CRYSTAL_PLAYERS_HOUSE_1F: _bidirectional_local_graph(downstairs_edges),
    }
    down = MacroEdge(
        CRYSTAL_PLAYERS_HOUSE_1F,
        kind="warp",
        at=(7, 0),
        arrival_at=CRYSTAL_FIRST_FLOOR_ARRIVAL_AT,
    )
    up = MacroEdge(
        CRYSTAL_PLAYERS_HOUSE_2F,
        kind="warp",
        at=(9, 0),
        arrival_at=(7, 1),
    )
    macro = MacroGraph(
        {
            CRYSTAL_PLAYERS_HOUSE_2F: (down,),
            CRYSTAL_PLAYERS_HOUSE_1F: (up,),
        },
        warp_locations={
            CRYSTAL_PLAYERS_HOUSE_2F: ((7, 0),),
            CRYSTAL_PLAYERS_HOUSE_1F: ((6, 7), (7, 7), (9, 0)),
        },
    )
    return macro, local_graphs


def plan_crystal_bedroom_descent() -> RoutePlan:
    macro, local = crystal_starting_navigation_graphs()
    return plan_route(
        macro,
        local,
        CRYSTAL_PLAYERS_HOUSE_2F,
        CRYSTAL_STARTING_BEDROOM_AT,
        CRYSTAL_PLAYERS_HOUSE_1F,
    )


def plan_crystal_bedroom_return() -> RoutePlan:
    macro, local = crystal_starting_navigation_graphs()
    return plan_route(
        macro,
        local,
        CRYSTAL_PLAYERS_HOUSE_1F,
        CRYSTAL_FIRST_FLOOR_ARRIVAL_AT,
        CRYSTAL_PLAYERS_HOUSE_2F,
        goal_at=CRYSTAL_STARTING_BEDROOM_AT,
    )


@dataclass(frozen=True, slots=True)
class CrystalStartingNavigationReport:
    outbound: RouteExecutionReport
    inbound: RouteExecutionReport
    frames_executed: int
    controller_released: bool

    def __post_init__(self) -> None:
        if not isinstance(self.outbound, RouteExecutionReport) or not self.outbound.passed:
            raise CrystalVerticalSliceError("Crystal outbound route did not pass")
        if not isinstance(self.inbound, RouteExecutionReport) or not self.inbound.passed:
            raise CrystalVerticalSliceError("Crystal inbound route did not pass")
        if type(self.frames_executed) is not int or self.frames_executed < 1:  # noqa: E721
            raise CrystalVerticalSliceError("Crystal route frame count is invalid")
        if self.inbound.terminal.map_id != CRYSTAL_PLAYERS_HOUSE_2F or (
            self.inbound.terminal.at != CRYSTAL_STARTING_BEDROOM_AT
        ):
            raise CrystalVerticalSliceError("Crystal round trip did not return to its start")
        if not self.controller_released:
            raise CrystalVerticalSliceError("Crystal route left a controller button pressed")

    @property
    def movement_requests(self) -> int:
        return self.outbound.movement_requests + self.inbound.movement_requests

    @property
    def semantic_steps(self) -> int:
        return len(self.outbound.executed_steps) + len(self.inbound.executed_steps)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.crystal.starting-navigation.v1",
            "status": "passed",
            "semantic_steps": self.semantic_steps,
            "movement_requests": self.movement_requests,
            "frames_executed": self.frames_executed,
            "map_transitions": 2,
            "returned_to_start": True,
            "controller_released": self.controller_released,
            "private_location_identity_fields": 0,
            "raw_address_fields": 0,
        }


def execute_crystal_starting_round_trip(
    controller: CrystalQualificationController,
) -> CrystalStartingNavigationReport:
    if controller.pressed_buttons:
        raise CrystalVerticalSliceError("Crystal route controller is not released")
    started = controller.frame_count
    port = CrystalTraversalPort(controller)
    outbound = execute_route(
        plan_crystal_bedroom_descent(),
        port,
        port,
        limits=CRYSTAL_ROUTE_LIMITS,
    )
    inbound = execute_route(
        plan_crystal_bedroom_return(),
        port,
        port,
        limits=CRYSTAL_ROUTE_LIMITS,
    )
    return CrystalStartingNavigationReport(
        outbound=outbound,
        inbound=inbound,
        frames_executed=controller.frame_count - started,
        controller_released=not controller.pressed_buttons,
    )


def observe_crystal_starting_goal_state(
    controller: CrystalQualificationController,
) -> CrystalGoalObservation:
    """Project the exact post-save starting boundary into portable pressures."""

    runtime = read_crystal_qualification_runtime(controller)
    bundle = read_crystal_observation_bundle(controller)
    if (
        crystal_map_id(runtime.map_group, runtime.map_number) != CRYSTAL_PLAYERS_HOUSE_2F
        or (runtime.x, runtime.y) != CRYSTAL_STARTING_BEDROOM_AT
        or not runtime.input_ready
    ):
        raise CrystalVerticalSliceError("Crystal starting goal boundary is not ready")
    if runtime.badge_count != 0 or bundle.party.size != 0:
        raise CrystalVerticalSliceError("Crystal starting goal boundary is not pristine")
    if (
        bundle.pokedex.registered.completed != 0
        or bundle.ownership.living.completed != 0
        or bundle.ownership.level_cap.completed != 0
    ):
        raise CrystalVerticalSliceError("Crystal starting collection boundary is not empty")
    available = frozenset(
        {
            CrystalCapability.OVERWORLD_MOVEMENT,
            CrystalCapability.INTERACTION,
        }
    )
    snapshot = CrystalCampaignSnapshot(
        story=CompletionProgress(runtime.badge_count, CRYSTAL_STORY_BADGE_TARGET),
        registered_collection=bundle.pokedex.registered,
        living_collection=bundle.ownership.living,
        level_collection=bundle.ownership.level_cap,
        evolution=CompletionProgress(0, bundle.pokedex.registered.target),
        world_knowledge=CompletionProgress(1, CRYSTAL_SOURCE_MAP_TARGET),
        party=bundle.party,
        game_started=True,
        input_ready=True,
        capture_item_count=bundle.inventory.capture_item_count,
        recovery_item_count=bundle.inventory.recovery_item_count,
        free_storage_slots=bundle.storage.free_slots,
        immediate_capture_slots=bundle.party.open_slots + bundle.storage.free_slots,
        capabilities=CrystalCapabilityState(
            available=available,
            unknown=frozenset(CrystalCapability) - available,
        ),
    )
    return project_crystal_goal_state(snapshot)


def build_crystal_starting_goal_bindings(
    observation: CrystalGoalObservation,
    controller: CrystalQualificationController,
    *,
    candidate_order: tuple[GoalKind, ...] = tuple(GoalKind),
) -> GoalBindingSet:
    """Bind one story step and one exploratory round trip at the fresh start."""

    if not isinstance(observation, CrystalGoalObservation):
        raise TypeError("observation must be CrystalGoalObservation")
    descent = plan_crystal_bedroom_descent()
    returning = plan_crystal_bedroom_return()
    providers = (
        CapabilityBoundCrystalGoalProvider(
            kind=GoalKind.ADVANCE_STORY,
            required_capabilities=frozenset({CrystalCapability.OVERWORLD_MOVEMENT}),
            resolver=lambda _observation: _story_binding(controller, descent),
        ),
        CapabilityBoundCrystalGoalProvider(
            kind=GoalKind.EXPLORE,
            required_capabilities=frozenset({CrystalCapability.OVERWORLD_MOVEMENT}),
            resolver=lambda _observation: _explore_binding(controller, descent, returning),
        ),
    )
    return CrystalGoalOpportunityEnumerator(providers).enumerate(
        observation,
        candidate_order=candidate_order,
    )


def _story_binding(
    controller: CrystalQualificationController,
    plan: RoutePlan,
) -> ExecutableGoalBinding:
    def execute() -> GoalExecutionReport:
        started = controller.frame_count
        port = CrystalTraversalPort(controller)
        report = execute_route(plan, port, port, limits=CRYSTAL_ROUTE_LIMITS)
        return GoalExecutionReport(
            actions_executed=report.movement_requests,
            frames_executed=controller.frame_count - started,
            evidence={
                "bounded": True,
                "route_passed": report.passed,
                "semantic_steps": len(report.executed_steps),
                "map_transitions": 1,
            },
        )

    def verify(report: GoalExecutionReport) -> GoalVerification:
        current = CrystalTraversalPort(controller).observe()
        if (
            report.evidence.get("route_passed") is True
            and current.map_id == CRYSTAL_PLAYERS_HOUSE_1F
            and current.at == CRYSTAL_FIRST_FLOOR_ARRIVAL_AT
            and current.ready
            and not controller.pressed_buttons
        ):
            return GoalVerification.succeeded()
        return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

    return ExecutableGoalBinding(
        binding_ref="pokemon.crystal:private:starting-story-descent",
        kind=GoalKind.ADVANCE_STORY,
        estimated_effort=_route_effort(plan),
        estimated_risk=0.0,
        execute=execute,
        verify=verify,
    )


def _explore_binding(
    controller: CrystalQualificationController,
    descent: RoutePlan,
    returning: RoutePlan,
) -> ExecutableGoalBinding:
    def execute() -> GoalExecutionReport:
        report = execute_crystal_starting_round_trip(controller)
        return GoalExecutionReport(
            actions_executed=report.movement_requests,
            frames_executed=report.frames_executed,
            evidence={
                "bounded": True,
                "route_passed": True,
                "semantic_steps": report.semantic_steps,
                "map_transitions": 2,
                "returned_to_start": True,
            },
        )

    def verify(report: GoalExecutionReport) -> GoalVerification:
        current = CrystalTraversalPort(controller).observe()
        if (
            report.evidence.get("route_passed") is True
            and report.evidence.get("returned_to_start") is True
            and current.map_id == CRYSTAL_PLAYERS_HOUSE_2F
            and current.at == CRYSTAL_STARTING_BEDROOM_AT
            and current.ready
            and not controller.pressed_buttons
        ):
            return GoalVerification.succeeded()
        return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

    return ExecutableGoalBinding(
        binding_ref="pokemon.crystal:private:starting-exploration-round-trip",
        kind=GoalKind.EXPLORE,
        estimated_effort=_route_effort(descent, returning),
        estimated_risk=0.0,
        execute=execute,
        verify=verify,
    )


def _route_effort(*plans: RoutePlan) -> float:
    steps = sum(len(plan.steps) for plan in plans)
    return min(1.0, steps / CRYSTAL_ROUTE_EFFORT_REFERENCE_STEPS)


def _bidirectional_local_graph(
    rows: tuple[tuple[tuple[int, int], tuple[int, int], str], ...],
) -> LocalGraph:
    reverse = {"up": "down", "right": "left", "down": "up", "left": "right"}
    edges: dict[tuple[int, int], list[LocalEdge]] = {}
    for source, target, action in rows:
        edges.setdefault(source, []).append(LocalEdge(target, action=action))
        edges.setdefault(target, []).append(LocalEdge(source, action=reverse[action]))
    return LocalGraph({source: tuple(outgoing) for source, outgoing in edges.items()})


__all__ = [
    "CRYSTAL_FIRST_FLOOR_ARRIVAL_AT",
    "CRYSTAL_PLAYERS_HOUSE_1F",
    "CRYSTAL_PLAYERS_HOUSE_2F",
    "CRYSTAL_ROUTE_LIMITS",
    "CRYSTAL_ROUTE_TIMING",
    "CRYSTAL_STARTING_BEDROOM_AT",
    "CrystalStartingNavigationReport",
    "CrystalStartingVerticalSliceQualification",
    "CrystalTraversalPort",
    "CrystalVerticalSliceError",
    "build_crystal_starting_goal_bindings",
    "crystal_map_id",
    "crystal_starting_navigation_graphs",
    "execute_crystal_starting_round_trip",
    "observe_crystal_starting_goal_state",
    "plan_crystal_bedroom_descent",
    "plan_crystal_bedroom_return",
    "split_crystal_map_id",
]
