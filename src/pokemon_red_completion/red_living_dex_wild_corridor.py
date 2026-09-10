"""Cartridge-derived reversible encounter corridors for living-dex lessons.

The option learner chooses a semantic source, never a direction sequence.  A
Red provider still needs a small, bounded local mechanic for seeking an
encounter.  This module derives that mechanic from the cartridge's grass grid
and directed traversal graph: two adjacent grass squares with plain walk edges
in both directions.  No root, slot, policy choice, outcome, or teacher route
participates in the derivation.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_indoor_encounters import (
    FIRST_INDOOR_MAP,
    FOREST_TILESET,
)
from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.local_router import Coordinate, LocalEdge, LocalGraph
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_acquisition import RED_ACQUISITION_CATALOG
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfile,
    RedGoalMechanic,
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

RED_LIVING_DEX_WILD_CORRIDOR_SCHEMA = (
    "pokemon.red.private-living-dex-wild-corridor.v1"
)


def bind_red_capture_search_budget_profile(profile: RedGoalContextProfile) -> RedGoalContextProfile:
    """Opt future captures into up to160legs; all other existing caps survive.

    The explicit marker carries this allowance through destination enumeration.
    Legacy derived corridors and checkpoint profiles retain their64-leg default.
    """
    providers = []
    found = False
    for spec in profile.providers:
        parameters = _thaw(spec.parameters)
        assert isinstance(parameters, dict)
        if spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE:
            parameters["capture_search_budget"] = "bounded-search-v1"
            # One encounter can consume a non-displacing seek plus a flee.
            # Leave room for both for every permitted encounter and terminal
            # exhaustion; use an even number so ordinary exhaustion ends home.
            actions, encounters = parameters["maximum_seek_steps"], parameters["maximum_encounters"]
            assert isinstance(actions, int) and isinstance(encounters, int)
            legs = min(160, actions - 2 * encounters - 2)
            if legs < 2:
                raise RedLivingDexWildCorridorError("search budget has no safe patrol allowance")
            parameters["maximum_legs"] = legs - legs % 2
            found = True
        providers.append((spec.kind, spec.mechanic, parameters))
    if not found:
        raise RedLivingDexWildCorridorError("search budget needs an existing corridor capture")
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id, providers=tuple(providers),
    ))


def bind_red_capture_status_profile(profile: RedGoalContextProfile) -> RedGoalContextProfile:
    """Explicitly opt into bounded, observed sleep/paralysis preparation.

    Historical profiles remain byte-for-byte unchanged. This is deterministic
    execution support, not an additional learned decision or training target.
    """
    providers = []
    found = False
    for spec in profile.providers:
        parameters = _thaw(spec.parameters)
        assert isinstance(parameters, dict)
        if spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE:
            parameters["capture_status_support"] = True
            found = True
        providers.append((spec.kind, spec.mechanic, parameters))
    if not found:
        raise RedLivingDexWildCorridorError("capture status needs an existing corridor capture")
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id, providers=tuple(providers),
    ))


def bind_red_local_discovery_profile(
    profile: RedGoalContextProfile, source_id: str, rom: bytes,
) -> RedGoalContextProfile:
    """Declare local sighting coverage from all cartridge slots, not canonical targets.

    The explicit profile transition leaves historical observations unchanged.
    Grass slots alone supply this walking corridor. Unseen water encounters
    cannot keep an exhausted grass survey incorrectly available.
    """
    from pokemon_red_completion.gen1_cartridge import internal_to_dex, wild_tables
    from pokemon_red_completion.red_collection import (
        RED_SOLO_COLLECTION_CONTRACT,
        red_species_number,
    )

    from .goal_manager import GoalKind

    discovery = next((spec for spec in profile.providers if spec.kind is GoalKind.EXPLORE), None)
    if discovery is None or discovery.mechanic is not RedGoalMechanic.WILD_CORRIDOR_DISCOVERY:
        raise RedLivingDexWildCorridorError("local discovery needs the existing corridor skill")
    map_id = int(map_id_for_wild_source(source_id))
    if discovery.parameters["source_id"] != source_id or discovery.parameters["map_id"] != map_id:
        raise RedLivingDexWildCorridorError("local discovery source differs from its profile")
    dex = internal_to_dex(rom)
    # The verifier measures this contract's seen numbers, not excluded species.
    targets = {red_species_number(ref) for ref in RED_SOLO_COLLECTION_CONTRACT.target_species}
    slots = wild_tables(rom, medium="grass").get(map_id, ())
    numbers = sorted({dex[species] for _, species in slots} & targets)
    if not numbers:
        raise RedLivingDexWildCorridorError("local discovery source has no target encounters")
    providers = []
    for spec in profile.providers:
        parameters = _thaw(spec.parameters)
        assert isinstance(parameters, dict)
        if spec.kind is GoalKind.EXPLORE:
            parameters["source_species_numbers"] = numbers
        providers.append((spec.kind, spec.mechanic, parameters))
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id, providers=tuple(providers),
    ))


def bind_red_opportunistic_capture_profile(
    profile: RedGoalContextProfile, rom: bytes,
) -> RedGoalContextProfile:
    """Bind all local cartridge grass offers without changing canonical dependencies."""
    from pokemon_red_completion.gen1_cartridge import internal_to_dex, wild_tables
    from pokemon_red_completion.red_collection import (
        RED_SOLO_COLLECTION_CONTRACT,
        red_species_number,
    )

    targets = {red_species_number(ref) for ref in RED_SOLO_COLLECTION_CONTRACT.target_species}
    dex = internal_to_dex(rom)
    tables = wild_tables(rom, medium="grass")
    providers = []
    found = False
    for spec in profile.providers:
        parameters = _thaw(spec.parameters)
        assert isinstance(parameters, dict)
        if spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE:
            map_id = int(map_id_for_wild_source(str(parameters["source_id"])))
            if parameters["map_id"] != map_id:
                raise RedLivingDexWildCorridorError("capture source differs from its map")
            numbers = sorted({dex[species] for _, species in tables.get(map_id, ())} & targets)
            if not numbers:
                raise RedLivingDexWildCorridorError("capture source has no target grass encounters")
            parameters["capture_species_numbers"] = numbers
            found = True
        providers.append((spec.kind, spec.mechanic, parameters))
    if not found:
        raise RedLivingDexWildCorridorError("opportunistic capture needs a corridor capture")
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id, providers=tuple(providers),
    ))


def retarget_red_wild_profile(
    profile: RedGoalContextProfile, corridor: RedLivingDexWildCorridor,
    *, rom: bytes | None = None,
) -> RedGoalContextProfile:
    """Move capture/discovery together, preserving every other skill and bound.

    The caller derives the corridor from the authenticated cartridge. This is
    an explicit execution-profile transition, never a rewrite of an old save.
    """
    if not isinstance(profile, RedGoalContextProfile) or not isinstance(
        corridor, RedLivingDexWildCorridor
    ):
        raise TypeError("regional retargeting needs a profile and derived corridor")
    wild = {
        RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
        RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,
    }
    if not wild.issubset({spec.mechanic for spec in profile.providers}):
        raise RedLivingDexWildCorridorError("regional profile needs capture and discovery")
    if any(spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_DEVELOPMENT
           for spec in profile.providers):
        raise RedLivingDexWildCorridorError("regional profile cannot move venue-bound development")
    providers = []
    for spec in profile.providers:
        parameters = _thaw(spec.parameters)
        assert isinstance(parameters, dict)
        if spec.mechanic in wild:
            derived = corridor.profile_parameters()
            if parameters.get("capture_search_budget") == "bounded-search-v1":
                derived["capture_search_budget"] = "bounded-search-v1"
                derived["maximum_legs"] = 160
            # Location changes cannot silently increase the old survey budget.
            for key in ("maximum_legs", "maximum_seek_steps", "maximum_encounters"):
                old_bound, new_bound = parameters[key], derived[key]
                assert isinstance(old_bound, int) and isinstance(new_bound, int)
                derived[key] = min(new_bound, old_bound)
            if "capture_status_support" in parameters:
                derived["capture_status_support"] = parameters["capture_status_support"]
            if "cut_transport" in parameters:
                derived["cut_transport"] = parameters["cut_transport"]
            if "fly_transport" in parameters:
                derived["fly_transport"] = parameters["fly_transport"]
            if "indoor_fly_departure" in parameters:
                derived["indoor_fly_departure"] = parameters["indoor_fly_departure"]
            if "travel_capture" in parameters:
                derived["travel_capture"] = parameters["travel_capture"]
            if "observed_local_capture" in parameters:
                derived["observed_local_capture"] = parameters["observed_local_capture"]
            if "capture_access_requirements" in parameters:
                derived["capture_access_requirements"] = parameters["capture_access_requirements"]
            parameters = derived
        providers.append((spec.kind, spec.mechanic, parameters))
    result = parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=profile.profile_id, providers=tuple(providers),
    ))
    if any("capture_species_numbers" in spec.parameters for spec in profile.providers):
        if rom is None:
            raise RedLivingDexWildCorridorError("opportunistic retargeting requires cartridge data")
        return bind_red_opportunistic_capture_profile(result, rom)
    return result


class RedLivingDexWildCorridorError(ValueError):
    """A source cannot supply a reversible cartridge-derived encounter lane."""


@dataclass(frozen=True, slots=True)
class RedLivingDexWildCorridor:
    """One two-tile, bidirectional grass lane used by an existing provider."""

    source_id: str
    map_id: int
    origin_at: Coordinate
    terminal_at: Coordinate
    forward_directions: tuple[str, ...] = ("up",)
    starting_endpoint: str = "south"
    maximum_legs: int = 64
    maximum_seek_steps: int = 256
    maximum_encounters: int = 32

    def __post_init__(self) -> None:
        target = RedEncounterSourceTarget(self.source_id)
        if int(map_id_for_wild_source(target.source_id)) != self.map_id:
            raise RedLivingDexWildCorridorError(
                "encounter corridor map differs from its wild source"
            )
        if (
            self.origin_at[0] - 1 != self.terminal_at[0]
            or self.origin_at[1] != self.terminal_at[1]
            or self.forward_directions != ("up",)
            or self.starting_endpoint != "south"
        ):
            raise RedLivingDexWildCorridorError(
                "encounter corridor is not the canonical north-south pair"
            )
        for value, subject in (
            (self.maximum_legs, "legs"),
            (self.maximum_seek_steps, "seek steps"),
            (self.maximum_encounters, "encounters"),
        ):
            if type(value) is not int or value <= 0:  # noqa: E721
                raise RedLivingDexWildCorridorError(
                    f"encounter corridor {subject} bound differs"
                )

    @property
    def binding_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "forward_directions": list(self.forward_directions),
            "map_id": self.map_id,
            "maximum_encounters": self.maximum_encounters,
            "maximum_legs": self.maximum_legs,
            "maximum_seek_steps": self.maximum_seek_steps,
            "origin_at": list(self.origin_at),
            "schema": RED_LIVING_DEX_WILD_CORRIDOR_SCHEMA,
            "source_id": self.source_id,
            "starting_endpoint": self.starting_endpoint,
            "terminal_at": list(self.terminal_at),
        }

    def profile_parameters(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "label": "cartridge-derived reversible encounter corridor",
            "map_id": self.map_id,
            "player_x": self.origin_at[1],
            "player_y": self.origin_at[0],
            "forward_directions": list(self.forward_directions),
            "starting_endpoint": self.starting_endpoint,
            "maximum_legs": self.maximum_legs,
            "maximum_seek_steps": self.maximum_seek_steps,
            "maximum_encounters": self.maximum_encounters,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "bidirectional_walk_edges": 2,
            "cartridge_derived": True,
            "encounter_tiles": 2,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "provider_local_direction_steps": len(self.forward_directions),
            "raw_teacher_direction_steps": 0,
            "schema": RED_LIVING_DEX_WILD_CORRIDOR_SCHEMA,
            "teacher_route": False,
        }


def derive_red_living_dex_wild_corridor(
    target: RedEncounterSourceTarget,
    terrain: Terrain,
    graph: LocalGraph,
    *,
    excluded: Collection[Coordinate] = (),
    cartridge: bytes | None = None,
) -> RedLivingDexWildCorridor:
    """Choose a reversible land-encounter pair; cartridge indoor support is explicit."""

    if not isinstance(target, RedEncounterSourceTarget):
        raise TypeError("wild corridor derivation needs an encounter target")
    if not isinstance(terrain, Terrain) or not isinstance(graph, LocalGraph):
        raise TypeError("wild corridor derivation needs cartridge terrain and graph")
    map_id = int(map_id_for_wild_source(target.source_id))
    if terrain.map_id != map_id:
        raise RedLivingDexWildCorridorError(
            "wild corridor terrain differs from its source map"
        )
    if not any(
        method.source_id == target.source_id
        for method in RED_ACQUISITION_CATALOG.methods
    ):
        from pokemon_red_completion.gen1_cartridge import wild_tables
        from pokemon_red_completion.observation import MapId

        if (cartridge is None or "SAFARI" in MapId(map_id).name
                or not wild_tables(cartridge, medium="grass").get(map_id)):
            raise RedLivingDexWildCorridorError(
                "wild corridor source has no authenticated ordinary encounter table"
            )
    blocked = frozenset(excluded)
    if any(
        not isinstance(coordinate, tuple)
        or len(coordinate) != 2
        or any(type(value) is not int or value < 0 for value in coordinate)  # noqa: E721
        for coordinate in blocked
    ):
        raise RedLivingDexWildCorridorError(
            "wild corridor exclusions contain an invalid coordinate"
        )

    encounter_grid = terrain.grass
    if (cartridge is not None and terrain.map_id >= FIRST_INDOOR_MAP
            and terrain.tileset != FOREST_TILESET):
        from pokemon_red_completion.gen1_indoor_encounters import indoor_land_encounter_mask

        # Do not relabel Terrain.grass: indoor land encounters are a separate
        # cartridge rule. Legacy no-cartridge callers keep their exact behavior.
        encounter_grid = indoor_land_encounter_mask(cartridge, terrain)

    candidates: list[tuple[int, int, int, Coordinate, Coordinate]] = []
    for south_y in range(1, terrain.height):
        for x in range(terrain.width):
            south = (south_y, x)
            north = (south_y - 1, x)
            if (
                south in blocked
                or north in blocked
                or not encounter_grid[south[0]][south[1]]
                or not encounter_grid[north[0]][north[1]]
                or not _plain_land_walk(graph, south, north, "up")
                or not _plain_land_walk(graph, north, south, "down")
            ):
                continue
            perimeter_clearance = min(
                north[0],
                terrain.height - 1 - south[0],
                x,
                terrain.width - 1 - x,
            )
            exclusion_clearance = min(
                (
                    abs(south[0] - other[0]) + abs(south[1] - other[1])
                    for other in blocked
                ),
                default=terrain.height + terrain.width,
            )
            candidates.append(
                (
                    -perimeter_clearance,
                    -exclusion_clearance,
                    south_y,
                    south,
                    north,
                )
            )
    if not candidates:
        raise RedLivingDexWildCorridorError(
            "wild source has no unobstructed reversible grass pair"
        )
    _clearance, _excluded_clearance, _row, south, north = min(candidates)
    return RedLivingDexWildCorridor(
        source_id=target.source_id,
        map_id=map_id,
        origin_at=south,
        terminal_at=north,
    )


def _plain_land_walk(
    graph: LocalGraph,
    source: Coordinate,
    target: Coordinate,
    action: str,
) -> bool:
    return any(
        _is_plain_land_walk(edge, target, action)
        for edge in graph.neighbors(source)
    )


def _is_plain_land_walk(edge: LocalEdge, target: Coordinate, action: str) -> bool:
    return (
        edge.target == target
        and edge.action == action
        and edge.kind == "walk"
        and not edge.requirements
        and edge.action_kind is MacroActionKind.MOVE
        and edge.required_mode in {None, "land"}
        and edge.result_mode is None
        and edge.transient is None
    )


__all__ = [
    "RED_LIVING_DEX_WILD_CORRIDOR_SCHEMA",
    "RedLivingDexWildCorridor",
    "RedLivingDexWildCorridorError",
    "derive_red_living_dex_wild_corridor",
]
