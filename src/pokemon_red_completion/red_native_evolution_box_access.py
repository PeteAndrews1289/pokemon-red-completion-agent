"""Reach an owned precursor's actual box before the existing evolution engine.

All input is deterministic preparation inside the selected goal's original
budget. The returned boundary is observed after preparation, not a reset,
synthetic arrival, new lineage or additional learning example.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from pokemon_red_completion.collection import CollectionLocation
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_boxed_level_evolution import ObservedSemanticBoundaryBinding
from pokemon_red_completion.red_collection import red_internal_species_number, red_species_ref
from pokemon_red_completion.red_pc_storage import face_pc_boundary, open_bills_pc, switch_box
from pokemon_red_completion.red_team_training import close_menu
from pokemon_red_completion.route_executor import execute_route

if TYPE_CHECKING:
    from pokemon_red_completion.executor import CountingExecutor
    from pokemon_red_completion.red_goal_context import (
        RedBoxedLevelEvolutionGoalRequest,
        RedGoalContextRuntime,
    )
    from pokemon_red_completion.route_executor import ReplanRequest
    from pokemon_red_completion.route_plan import RoutePlan
    from pokemon_red_completion.strategic_navigation_scenario_runtime import (
        StrategicScenarioRouteWorld,
    )


class RedEvolutionBoxAccessError(RuntimeError):
    """The selected precursor cannot be reached with its collection preserved."""


def prepare_evolution_box(
    runtime: RedGoalContextRuntime,
    world: StrategicScenarioRouteWorld,
    actions: CountingExecutor,
    traversal: Gen1TraversalObserver,
    route: RoutePlan,
    request: RedBoxedLevelEvolutionGoalRequest,
) -> tuple[ObservedSemanticBoundaryBinding, dict[str, object]]:
    from pokemon_red_completion.red_resource_goal_router import _ROUTE_LIMITS, _walking_plan

    before = runtime.adapter.observe()
    collection = before.collection_observation
    target = request.current_box_index
    source = red_species_ref(red_internal_species_number(request.precursor_internal_species_id))
    specimen = next(
        (
            s
            for s in collection.specimens
            if (
                s.location is CollectionLocation.BOX
                and s.container_index == target
                and s.slot_index == request.precursor_box_slot - 1
            )
        ),
        None,
    )
    if (
        not runtime.boxed_level_evolution_cross_box
        or before.raw.battle_state
        or not before.input_ready
        or target == collection.current_box_index
        or not 0 <= target < len(collection.box_counts)
        or collection.box_counts[target] >= collection.box_capacity
        or specimen is None
        or specimen.species_ref != source
        or before.party.size != 6
        or before.party.members[request.deposit_party_slot - 1].species_id
        != request.deposit_internal_species_id
        or not _walking_plan(route)
        or route.terminal_at != (4, 13)
    ):
        raise RedEvolutionBoxAccessError("cross-box request is not executable before input")
    story = runtime.adapter.graph.completed_ids(before.game_state)
    action_start, frame_start = actions.actions_executed, runtime.emulator.frame_count

    def replan(request: ReplanRequest) -> RoutePlan:
        candidate = world.replanner()(request)
        if not _walking_plan(candidate):
            raise RedEvolutionBoxAccessError("cross-box replan requires unsupported field input")
        return candidate

    transport = execute_route(
        route,
        actions,
        traversal,
        replanner=replan,
        limits=_ROUTE_LIMITS,
    )
    at_pc = runtime.adapter.observe()
    if (
        not transport.passed
        or (at_pc.raw.map_id, at_pc.raw.player_y, at_pc.raw.player_x) != (route.terminal_map, 4, 13)
        or at_pc.raw.battle_state
        or not at_pc.input_ready
        or at_pc.collection_observation != collection
        or runtime.adapter.graph.completed_ids(at_pc.game_state) != story
    ):
        raise RedEvolutionBoxAccessError("cross-box PC approach or collection changed")
    bag, money = at_pc.raw.bag_items, at_pc.raw.player_money
    face_pc_boundary(actions, runtime.reader, "up")
    open_bills_pc(actions, runtime.reader)
    rotated = switch_box(actions, runtime.reader, target_box_index=target)
    close_menu(actions, runtime.reader)
    after = runtime.adapter.observe()
    observed = after.collection_observation
    live = traversal.observe()
    if (
        not rotated.passed
        or observed.current_box_index != target
        or observed != replace(collection, current_box_index=target)
        or after.party != before.party
        or after.raw.bag_items != bag
        or after.raw.player_money != money
        or after.raw.battle_state
        or not after.input_ready
        or runtime.adapter.graph.completed_ids(after.game_state) != story
        or live.map_id != route.terminal_map
        or live.at != (4, 13)
        or not live.ready
        or live.interruption is not None
    ):
        raise RedEvolutionBoxAccessError("cross-box rotation did not preserve the observed state")
    boundary = ObservedSemanticBoundaryBinding(
        live.map_id,
        live.at,
        canonical_sha256(
            {
                "schema": "pokemon.red.prepared-evolution-box-boundary.v1",
                "origin_state_sha256": runtime.capture.state_sha256,
                "profile_sha256": runtime.profile.profile_sha256,
                "target_box": target,
                "box_counts": list(observed.box_counts),
                "specimens": [
                    [s.species_ref, s.level, s.location.value, s.container_index, s.slot_index]
                    for s in observed.specimens
                ],
            }
        ),
    )
    return boundary, {
        "storage_preparation": {
            "box_rotations": 1,
            "collection_preserved": True,
            "setup_training_rows": 0,
            "actions_executed": actions.actions_executed - action_start,
            "frames_executed": runtime.emulator.frame_count - frame_start,
        }
    }
