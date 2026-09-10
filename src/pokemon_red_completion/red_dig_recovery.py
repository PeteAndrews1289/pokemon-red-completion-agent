"""Opted-in legal escape followed by the existing fresh Center recovery skill."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from .actions import MacroAction, MacroActionKind
from .blaine import _field_dig
from .gen1_field_moves import DIG_MOVE_ID
from .gen1_route_runtime import Gen1TraversalObserver
from .goal_manager import GoalKind
from .goal_manager_composition_qualification import HardCompositionActionLimiter
from .goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from .observation import MapId, OverworldMovementMode
from .provenance import canonical_sha256
from .red_collection_fly import red_fly_landings
from .red_dual_capability_curriculum_runtime import dependency_specimen_ledger
from .red_goal_manager import RedGoalObservation
from .red_goal_skills import _POKEMON_CENTER_MAPS
from .red_training_transitions import RED_ESCAPE_WARP_TILESETS
from .route_executor import TraversalSnapshot
from .route_plan import RoutePlanningError

if TYPE_CHECKING:
    from .red_resource_goal_router import RedResourceGoalRouter


class RedDigRecoveryError(RuntimeError):
    """Escape cannot retain the declared recovery goal or its protected state."""


@dataclass(frozen=True)
class DigRecoveryPlan:
    anchor: int
    landing: tuple[int, int]
    holder: int
    tileset: int
    center: int
    steps: int


def plan_dig_recovery(
    router: RedResourceGoalRouter, observation: RedGoalObservation, start: TraversalSnapshot,
) -> DigRecoveryPlan | None:
    from .red_resource_goal_router import _walking_plan

    if not any(s.kind is GoalKind.RESTORE_TEAM and s.parameters.get("dig_recovery") is True
               for s in router.runtime.profile.providers):
        return None
    reader, raw = router.runtime.reader, observation.raw
    if (not observation.input_ready or raw.battle_state or not start.ready
            or start.interruption is not None or start.mode != "land"
            or reader.read_overworld_movement_mode() is not OverworldMovementMode.WALKING
            or reader.read_bottom_dialogue_box_visible()
            or reader.read_pending_trainer_battle_identity() is not None
            or reader.read_fly_menu_state() is not None):
        return None
    tileset, anchor = reader.read_current_map_tileset(), reader.read_last_blackout_map()
    hp, moves = raw.party_hp or (), raw.party_moves or ()
    if (tileset not in RED_ESCAPE_WARP_TILESETS or type(anchor) is not int
            or not 0 <= anchor <= 10 or raw.party_count != len(hp) or len(hp) != len(moves)):
        return None
    # The reused compiler selects the first holder. Never qualify a later living
    # member when that compiler would address a fainted earlier member instead.
    holder = next((i for i, known in enumerate(moves) if DIG_MOVE_ID in known), None)
    if holder is None or hp[holder] <= 0:
        return None
    landings = dict(red_fly_landings(router.world.rom))
    if anchor not in landings or anchor == start.map_id:
        return None
    landing = landings[anchor]
    graph = router.world.local_graphs.get(anchor)
    if (graph is None or landing not in graph.edges
            or landing in router.world.object_blockers[anchor]):
        return None
    projected = replace(start, map_id=anchor, at=landing, last_outside_map=anchor,
                        occupied=frozenset(), hazards=())
    routes = []
    for center in sorted(_POKEMON_CENTER_MAPS):
        try:
            route = router.world.plan_feasible_to_map(projected, int(center), goal_at=(7, 3))
        except RoutePlanningError:
            continue
        if route.steps and len(route.steps) <= 256 and _walking_plan(route):
            routes.append(route)
    if not routes:
        return None
    route = min(routes, key=lambda r: (len(r.steps), r.terminal_map))
    return DigRecoveryPlan(anchor, landing, holder, tileset, route.terminal_map, len(route.steps))


def bind_dig_recovery(
    router: RedResourceGoalRouter, bindings: GoalBindingSet, observation: RedGoalObservation,
    start: TraversalSnapshot, *, prepare_escort: Callable[[], None], require_pp_restore: bool,
) -> GoalBindingSet:
    plan = plan_dig_recovery(router, observation, start)
    if plan is None:
        return bindings
    reader, emulator, actions = router.runtime.reader, router.runtime.emulator, router.actions
    ledger = dependency_specimen_ledger(observation.collection_observation)
    claimed = False
    completed: list[tuple[ExecutableGoalBinding, GoalExecutionReport]] = []

    def execute() -> GoalExecutionReport:
        nonlocal claimed
        if claimed:
            raise RedDigRecoveryError("escape binding already consumed")
        claimed = True
        fresh = router.runtime.adapter.observe()
        traversal = Gen1TraversalObserver(reader).observe()
        if (fresh.raw != observation.raw or fresh.party != observation.party or traversal != start
                or dependency_specimen_ledger(fresh.collection_observation) != ledger
                or plan_dig_recovery(router, fresh, traversal) != plan):
            raise RedDigRecoveryError("escape origin or healing anchor changed before input")
        action_start, frame_start = actions.actions_executed, emulator.frame_count

        # The enclosing player owns the hard frame budget. Reserve every Dig
        # dispatch before delegation so even a partially failed input counts.
        bounded = HardCompositionActionLimiter(
            actions, maximum_actions_per_decision=128, maximum_episode_actions=128,
        )
        _field_dig(bounded, reader, emulator, expected_map=MapId(plan.anchor))
        for _ in range(60):
            if (reader.read_input_readiness().ready
                    and not reader.read_bottom_dialogue_box_visible()
                    and reader.read_overworld_movement_mode() is OverworldMovementMode.WALKING):
                break
            bounded.execute(MacroAction(MacroActionKind.WAIT, repeat=12))
        after = router.runtime.adapter.observe()
        landed = Gen1TraversalObserver(reader).observe()
        if (landed.map_id != plan.anchor or landed.at != plan.landing or not landed.ready
                or landed.interruption is not None or landed.mode != "land"
                or after.raw.battle_state or not after.input_ready
                or after.party != observation.party
                or after.raw.bag_items != observation.raw.bag_items
                or after.raw.player_money != observation.raw.player_money
                or dependency_specimen_ledger(after.collection_observation) != ledger):
            raise RedDigRecoveryError(
                "escape did not preserve its exact safe landing and collection",
            )
        escape_actions = actions.actions_executed-action_start
        escape_frames = emulator.frame_count-frame_start
        from .red_routed_recovery import bind_routed_center_recovery

        rebound = bind_routed_center_recovery(
            router, bindings, after, prepare_escort=prepare_escort,
            require_pp_restore=require_pp_restore,
        )
        selected = next((b for b in rebound.bindings if b.kind is GoalKind.RESTORE_TEAM), None)
        if selected is None:
            raise RedDigRecoveryError("escaped but no fresh recovery offer exists")
        report = selected.execute()
        completed.append((selected, report))
        return GoalExecutionReport(
            actions_executed=actions.actions_executed-action_start,
            frames_executed=emulator.frame_count-frame_start,
            evidence={**report.evidence, "dig_recovery": {
                "anchor_map": plan.anchor, "landing": list(plan.landing),
                "escape_actions": escape_actions, "escape_frames": escape_frames,
                "verified_escape": True,
            }},
        )

    def verify(_report: GoalExecutionReport) -> GoalVerification:
        if len(completed) != 1:
            raise RedDigRecoveryError("escape has no completed recovery")
        binding, report = completed[0]
        return binding.verify(report)

    binding = ExecutableGoalBinding(
        binding_ref="pokemon.red:recovery:dig:"+canonical_sha256({
            "anchor":plan.anchor, "landing":list(plan.landing), "center":plan.center,
        }), kind=GoalKind.RESTORE_TEAM, estimated_effort=min(1.0, 0.2+plan.steps/1000),
        estimated_risk=0.05, execute=execute, verify=verify,
    )
    return GoalBindingSet(
        tuple(o for o in bindings.opportunities if o.kind is not GoalKind.RESTORE_TEAM)
        +(binding.opportunity,),
        tuple(b for b in bindings.bindings if b.kind is not GoalKind.RESTORE_TEAM)+(binding,),
    )
