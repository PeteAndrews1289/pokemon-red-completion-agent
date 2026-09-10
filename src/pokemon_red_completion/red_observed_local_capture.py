"""Observe changed layout and bind reachable local encounter corridors.

Mission check:
- Reusable capability: observe changed layout and find a reachable encounter
  patch within the same model-selected area.
- Learned authority: stays source choice; local routing is deterministic with
  no setup labels.
- Transfer test: vary blocks, disconnected grass, occupied tiles, one-way edges,
  wrong active map, and changed blocks before input.
- Cheapest falsifier: disconnected canonical lane is excluded; accessible
  reversible pair chosen with zero input.
- Time box: 8 min draft + Codex 1 hour integration; stop on handcoded
  coordinates/species, invented states, resource resets.
- Maintenance: unblocks next model 27 acquisition, not an independent
  learning success.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
from pokemon_red_completion.gen1_trainer_sight import Gen1TrainerSightProjector
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
)
from pokemon_red_completion.local_router import (
    Coordinate,
    LocalEdge,
    LocalGraph,
    find_local_paths,
)
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfile,
    RedGoalMechanic,
    RedGoalProviderSpec,
    _thaw,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_living_dex_multifamily_curriculum import (
    map_id_for_wild_source,
)
from pokemon_red_completion.red_living_dex_provider_curriculum import (
    RedEncounterSourceTarget,
)
from pokemon_red_completion.red_living_dex_wild_corridor import (
    RedLivingDexWildCorridorError,
    derive_red_living_dex_wild_corridor,
    retarget_red_wild_profile,
)

if TYPE_CHECKING:
    from pokemon_red_completion.red_goal_manager import RedGoalObservation
    from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter

_CARDINAL_ACTIONS = frozenset({"up", "down", "left", "right"})


class RedObservedLocalCaptureError(RuntimeError):
    """Raised when an observed local capture encounters stale state or layout changes."""


def _strip_observed_local_capture_flag(
    profile: RedGoalContextProfile,
) -> RedGoalContextProfile:
    providers = []
    for spec in profile.providers:
        parameters = _thaw(spec.parameters)
        assert isinstance(parameters, dict)
        if spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE:
            parameters.pop("observed_local_capture", None)
        providers.append((spec.kind, spec.mechanic, parameters))
    return parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id=profile.profile_id,
            providers=tuple(providers),
        )
    )


def bind_observed_local_capture(
    router: RedResourceGoalRouter,
    spec: RedGoalProviderSpec,
    observation: RedGoalObservation,
) -> ExecutableGoalBinding | None:
    """Bind an authenticated local encounter corridor from current map blocks.

    Only applies when spec is WILD_CORRIDOR_CAPTURE, observed_local_capture is True,
    the active map equals the source map, registration_policy exists, and the game
    is input_ready, nonbattle, and in land movement mode. Genuine absence of a
    reachable reversible corridor returns None. Mismatched active observations
    fail closed.
    """
    if spec.mechanic is not RedGoalMechanic.WILD_CORRIDOR_CAPTURE:
        return None
    if spec.parameters.get("observed_local_capture") is not True:
        return None
    if getattr(router.runtime, "registration_policy", None) is None:
        return None
    if not observation.input_ready or bool(observation.raw.battle_state):
        return None

    source_id = str(spec.parameters.get("source_id", ""))
    if not source_id:
        return None
    source_map = spec.parameters.get("map_id")
    if source_map is None:
        source_map = int(map_id_for_wild_source(source_id))
    assert isinstance(source_map, int)

    actual_map = observation.raw.map_id
    if actual_map != source_map:
        return None

    traversal_observer = Gen1TraversalObserver(
        router.runtime.reader,
        hazard_projector=Gen1TrainerSightProjector(router.world.rom, router.runtime.reader),
    )
    start_snapshot = traversal_observer.observe()
    if start_snapshot.mode != "land":
        return None
    if (
        start_snapshot.map_id != source_map
        or start_snapshot.at != (observation.raw.player_y, observation.raw.player_x)
        or not start_snapshot.ready or start_snapshot.interruption is not None
    ):
        raise RedObservedLocalCaptureError(
            "traversal observer differs from the qualified active state"
        )

    current_blocks = router.runtime.reader.read_current_map_blocks()
    if current_blocks.map_id != source_map:
        raise RedObservedLocalCaptureError(
            f"observed map blocks for {current_blocks.map_id} do not match active map {source_map}"
        )

    try:
        live_world = router.world.with_current_blocks(current_blocks)
    except Exception as exc:
        raise RedObservedLocalCaptureError(
            "failed to derive world with current map blocks"
        ) from exc

    if source_map not in live_world.terrain or source_map not in live_world.local_graphs:
        raise RedObservedLocalCaptureError(f"map {source_map} missing from current world")

    current_terrain = live_world.terrain[source_map]
    raw_graph = live_world.local_graphs[source_map]

    start_at = start_snapshot.at
    start_occupied = start_snapshot.occupied
    capabilities = start_snapshot.capabilities
    object_blockers = frozenset(live_world.object_blockers.get(source_map, ()))
    warp_locations = frozenset(live_world.macro_graph.warp_locations.get(source_map, ()))
    blocked_tiles = frozenset(start_occupied) | object_blockers | warp_locations

    walking_edges: dict[Coordinate, list[LocalEdge]] = {}
    for source, outgoing in raw_graph.edges.items():
        if source in blocked_tiles and source != start_at:
            continue
        valid_outgoing = []
        for edge in outgoing:
            if (
                edge.action_kind is MacroActionKind.MOVE
                and edge.action in _CARDINAL_ACTIONS
                and edge.permits_mode("land")
                and edge.result_mode in (None, "land")
                and edge.requirements.issubset(capabilities)
                and edge.target not in blocked_tiles
                and edge.transient not in blocked_tiles
            ):
                valid_outgoing.append(edge)
        if valid_outgoing:
            walking_edges[source] = valid_outgoing

    walking_graph = LocalGraph({k: tuple(v) for k, v in walking_edges.items()})

    goals = {
        ((y, x), "land")
        for y in range(current_terrain.height)
        for x in range(current_terrain.width)
    }
    paths = find_local_paths(
        walking_graph,
        start_at,
        goals,
        capabilities=capabilities,
        start_mode="land",
    )
    reachable_coords = {goal[0] for goal in paths}
    unreachable_coords = {
        (y, x)
        for y in range(current_terrain.height)
        for x in range(current_terrain.width)
        if (y, x) not in reachable_coords
    }
    excluded_coordinates = unreachable_coords | blocked_tiles

    try:
        corridor = derive_red_living_dex_wild_corridor(
            RedEncounterSourceTarget(source_id),
            current_terrain,
            walking_graph,
            excluded=excluded_coordinates,
            cartridge=live_world.rom,
        )
    except RedLivingDexWildCorridorError:
        return None

    unflagged_profile = _strip_observed_local_capture_flag(router.runtime.profile)
    execution_profile = retarget_red_wild_profile(
        unflagged_profile,
        corridor,
        rom=live_world.rom,
    )
    ephemeral_runtime = replace(router.runtime, profile=execution_profile)
    ephemeral_router = replace(
        router,
        runtime=ephemeral_runtime,
        world=live_world,
        prepare_capture_party=False,
        prepare_capture_storage=False,
        prepare_capture_escort=False,
        include_recovery_offers=False,
    )

    binding_set = ephemeral_router.enumerate(observation)
    underlying_binding = next(
        (binding for binding in binding_set.bindings if binding.kind is spec.kind),
        None,
    )
    if underlying_binding is None:
        return None
    expected_source = f"pokemon.red:acquisition:{source_id}"
    if not (
        underlying_binding.search_source_ref == expected_source
        or (underlying_binding.search_source_ref is None and (
            underlying_binding.binding_ref == expected_source
            or underlying_binding.binding_ref.startswith(expected_source + ":profile-")
        ))
    ):
        raise RedObservedLocalCaptureError("observed capture changed its selected source")

    qualified_observation = observation
    qualified_blocks = current_blocks
    executed = False

    def wrapped_execute() -> GoalExecutionReport:
        nonlocal executed
        if executed:
            raise RedObservedLocalCaptureError(
                "observed local capture binding has already been executed"
            )
        fresh_obs = router.runtime.adapter.observe()
        if fresh_obs != qualified_observation:
            raise RedObservedLocalCaptureError(
                "fresh observation does not match qualified observation before execution"
            )
        fresh_blocks = router.runtime.reader.read_current_map_blocks()
        if fresh_blocks != qualified_blocks:
            raise RedObservedLocalCaptureError(
                "current map blocks changed before execution"
            )
        executed = True
        return underlying_binding.execute()

    return replace(
        underlying_binding,
        execute=wrapped_execute,
        search_source_ref=expected_source,
    )


__all__ = [
    "RedObservedLocalCaptureError",
    "bind_observed_local_capture",
]
