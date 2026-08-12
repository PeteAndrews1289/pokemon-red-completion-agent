"""Reviewed Red approach boundaries for preregistered strategic scenarios.

The scenario registry says *which objective* is a candidate.  This module is
the separate title adapter that says where Red's deterministic route planner
may safely hand control to that objective's bounded skill.  Reaching one of
these maps is an approach outcome; it never claims the objective was completed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pokemon_red_completion.observation import MapId, location_label
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.strategic_navigation import StrategicNavigationTag
from pokemon_red_completion.strategic_navigation_scenarios import (
    StrategicNavigationScenario,
    StrategicNavigationScenarioRegistry,
    StrategicScenarioProtocolError,
)


class StrategicScenarioRouteCatalogError(RuntimeError):
    """Raised when an objective cannot be mapped to a truthful approach."""


def _tags(*values: StrategicNavigationTag) -> tuple[StrategicNavigationTag, ...]:
    return tuple(sorted(values, key=lambda item: item.value))


@dataclass(frozen=True, slots=True)
class ScenarioObjectiveDestinationSpec:
    """One private Red destination and its portable candidate semantics."""

    objective_id: str
    goal_map: MapId
    semantic_tags: tuple[StrategicNavigationTag, ...]

    def __post_init__(self) -> None:
        if not self.objective_id or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789_"
            for character in self.objective_id
        ):
            raise StrategicScenarioRouteCatalogError(
                "scenario route objective identity is invalid"
            )
        if not isinstance(self.goal_map, MapId):
            raise StrategicScenarioRouteCatalogError(
                "scenario route goal must be a known Red map"
            )
        if (
            not self.semantic_tags
            or any(
                not isinstance(item, StrategicNavigationTag)
                for item in self.semantic_tags
            )
            or self.semantic_tags
            != tuple(sorted(set(self.semantic_tags), key=lambda item: item.value))
        ):
            raise StrategicScenarioRouteCatalogError(
                "scenario route semantic tags must be unique and sorted"
            )

    @property
    def destination_ref(self) -> str:
        return f"pokemon.red:objective:{self.objective_id}:approach"


_REACH_TAGS = _tags(
    StrategicNavigationTag.REACH_NEXT_CHALLENGE,
    StrategicNavigationTag.STORY_PROGRESS,
    StrategicNavigationTag.TRANSIT,
)
_BATTLE_TAGS = _tags(
    StrategicNavigationTag.CHALLENGE,
    StrategicNavigationTag.STORY_PROGRESS,
)
_RESOURCE_TAGS = _tags(
    StrategicNavigationTag.ACQUIRE_RESOURCE,
    StrategicNavigationTag.REMOVE_BLOCKER,
    StrategicNavigationTag.STORY_PROGRESS,
)
_BLOCKER_TAGS = _tags(
    StrategicNavigationTag.REMOVE_BLOCKER,
    StrategicNavigationTag.STORY_PROGRESS,
)
_CHALLENGE_BLOCKER_TAGS = _tags(
    StrategicNavigationTag.CHALLENGE,
    StrategicNavigationTag.REMOVE_BLOCKER,
    StrategicNavigationTag.STORY_PROGRESS,
)
_PUZZLE_RESOURCE_TAGS = _tags(
    StrategicNavigationTag.ACQUIRE_RESOURCE,
    StrategicNavigationTag.PUZZLE,
    StrategicNavigationTag.REMOVE_BLOCKER,
)


STRATEGIC_SCENARIO_DESTINATIONS: Mapping[str, ScenarioObjectiveDestinationSpec] = {
    item.objective_id: item
    for item in (
        ScenarioObjectiveDestinationSpec("help_bill", MapId.BILLS_HOUSE, _BLOCKER_TAGS),
        ScenarioObjectiveDestinationSpec("defeat_misty", MapId.CERULEAN_GYM, _BATTLE_TAGS),
        ScenarioObjectiveDestinationSpec(
            "reach_vermilion", MapId.VERMILION_CITY, _REACH_TAGS
        ),
        ScenarioObjectiveDestinationSpec("obtain_cut", MapId.SS_ANNE_1F, _RESOURCE_TAGS),
        ScenarioObjectiveDestinationSpec(
            "clear_rocket_hideout", MapId.GAME_CORNER, _CHALLENGE_BLOCKER_TAGS
        ),
        ScenarioObjectiveDestinationSpec(
            "rescue_fuji", MapId.POKEMON_TOWER_1F, _CHALLENGE_BLOCKER_TAGS
        ),
        ScenarioObjectiveDestinationSpec(
            "reach_fuchsia", MapId.FUCHSIA_CITY, _REACH_TAGS
        ),
        ScenarioObjectiveDestinationSpec(
            "obtain_surf", MapId.SAFARI_ZONE_GATE, _RESOURCE_TAGS
        ),
        ScenarioObjectiveDestinationSpec(
            "obtain_strength", MapId.WARDENS_HOUSE, _RESOURCE_TAGS
        ),
        ScenarioObjectiveDestinationSpec("defeat_koga", MapId.FUCHSIA_GYM, _BATTLE_TAGS),
        ScenarioObjectiveDestinationSpec("defeat_erika", MapId.CELADON_GYM, _BATTLE_TAGS),
        # The gate is the bounded Saffron-access skill's honest handoff point.
        ScenarioObjectiveDestinationSpec(
            "reach_saffron", MapId.ROUTE_7_GATE, _REACH_TAGS
        ),
        ScenarioObjectiveDestinationSpec(
            "liberate_silph", MapId.SILPH_CO_1F, _CHALLENGE_BLOCKER_TAGS
        ),
        ScenarioObjectiveDestinationSpec(
            "defeat_sabrina", MapId.SAFFRON_GYM, _BATTLE_TAGS
        ),
        ScenarioObjectiveDestinationSpec(
            "reach_cinnabar", MapId.CINNABAR_POKECENTER, _REACH_TAGS
        ),
        ScenarioObjectiveDestinationSpec(
            "obtain_secret_key", MapId.POKEMON_MANSION_1F, _PUZZLE_RESOURCE_TAGS
        ),
        ScenarioObjectiveDestinationSpec("defeat_blaine", MapId.CINNABAR_GYM, _BATTLE_TAGS),
        ScenarioObjectiveDestinationSpec(
            "defeat_giovanni", MapId.VIRIDIAN_GYM, _BATTLE_TAGS
        ),
    )
}


STRATEGIC_SCENARIO_ORIGIN_MAPS: Mapping[str, frozenset[MapId]] = {
    "celadon": frozenset({MapId.CELADON_CITY, MapId.CELADON_POKECENTER}),
    "cerulean": frozenset({MapId.CERULEAN_CITY, MapId.CERULEAN_POKECENTER}),
    "cinnabar": frozenset({MapId.CINNABAR_ISLAND, MapId.CINNABAR_POKECENTER}),
    "fuchsia": frozenset({MapId.FUCHSIA_CITY, MapId.FUCHSIA_POKECENTER}),
    "lavender": frozenset({MapId.LAVENDER_TOWN, MapId.LAVENDER_POKECENTER}),
    "saffron": frozenset({MapId.SAFFRON_CITY, MapId.SAFFRON_POKECENTER}),
    "vermilion": frozenset({MapId.VERMILION_CITY, MapId.VERMILION_POKECENTER}),
}


def validate_scenario_route_catalog(
    registry: StrategicNavigationScenarioRegistry,
    *,
    catalog: Mapping[str, ScenarioObjectiveDestinationSpec] = (
        STRATEGIC_SCENARIO_DESTINATIONS
    ),
    origin_maps: Mapping[str, frozenset[MapId]] = STRATEGIC_SCENARIO_ORIGIN_MAPS,
) -> dict[str, int]:
    """Require exact coverage of every public scenario objective and origin."""

    if not isinstance(registry, StrategicNavigationScenarioRegistry):
        raise TypeError("registry must be a StrategicNavigationScenarioRegistry")
    objective_ids = frozenset(
        objective_id
        for scenario in registry.scenarios
        for objective_id in scenario.candidate_objective_ids
    )
    if frozenset(catalog) != objective_ids:
        raise StrategicScenarioRouteCatalogError(
            "scenario route catalog objective coverage differs"
        )
    if any(key != value.objective_id for key, value in catalog.items()):
        raise StrategicScenarioRouteCatalogError(
            "scenario route catalog key differs from its objective"
        )
    origins = frozenset(item.origin_region for item in registry.scenarios)
    if frozenset(origin_maps) != origins:
        raise StrategicScenarioRouteCatalogError(
            "scenario route catalog origin coverage differs"
        )
    if any(
        not maps or any(not isinstance(map_id, MapId) for map_id in maps)
        for maps in origin_maps.values()
    ):
        raise StrategicScenarioRouteCatalogError(
            "scenario origin map coverage is invalid"
        )
    return {
        "candidate_objectives": len(objective_ids),
        "destination_maps": len({item.goal_map for item in catalog.values()}),
        "origin_regions": len(origins),
    }


def scenario_destination_specs(
    registry: StrategicNavigationScenarioRegistry,
    scenario_id: str,
) -> tuple[ScenarioObjectiveDestinationSpec, ...]:
    """Return candidate bindings in preregistered order without opening test."""

    validate_scenario_route_catalog(registry)
    scenario = registry.scenario(scenario_id)
    return tuple(
        STRATEGIC_SCENARIO_DESTINATIONS[objective_id]
        for objective_id in scenario.candidate_objective_ids
    )


def require_navigation_materialization_step(
    source: StrategicNavigationScenario,
    target: StrategicNavigationScenario,
    objective_id: str,
    *,
    catalog: Mapping[str, ScenarioObjectiveDestinationSpec] = (
        STRATEGIC_SCENARIO_DESTINATIONS
    ),
) -> ScenarioObjectiveDestinationSpec:
    """Authorize one approach whose observed location creates the target frontier.

    Most destination approaches do *not* complete their objective: arriving at a
    Gym is not defeating its leader.  This narrow seam accepts only a one-objective
    registry transition whose completion fact is exactly the destination map's
    live location and whose target origin includes that map.
    """

    if not isinstance(source, StrategicNavigationScenario) or not isinstance(
        target, StrategicNavigationScenario
    ):
        raise TypeError("materialization scenarios must be strategic scenarios")
    if objective_id not in source.candidate_objective_ids:
        raise StrategicScenarioRouteCatalogError(
            "materialized objective is not a source-scenario candidate"
        )
    source_completed = frozenset(source.completed_objective_ids)
    target_completed = frozenset(target.completed_objective_ids)
    if objective_id in source_completed or target_completed != source_completed.union(
        (objective_id,)
    ):
        raise StrategicScenarioRouteCatalogError(
            "materialization must add exactly one incomplete candidate objective"
        )
    try:
        spec = catalog[objective_id]
    except KeyError as error:
        raise StrategicScenarioRouteCatalogError(
            "materialized objective lacks a destination binding"
        ) from error
    if spec.objective_id != objective_id:
        raise StrategicScenarioRouteCatalogError(
            "materialized objective binding identity differs"
        )
    live_location = location_label(spec.goal_map)
    expected_fact = None if live_location is None else f"location:{live_location}"
    if COMPLETION_QUEST.objective(objective_id).completion_facts != frozenset(
        {expected_fact}
    ):
        raise StrategicScenarioRouteCatalogError(
            "materialized approach does not itself complete a location objective"
        )
    target_origins = STRATEGIC_SCENARIO_ORIGIN_MAPS.get(target.origin_region)
    if target_origins is None or spec.goal_map not in target_origins:
        raise StrategicScenarioRouteCatalogError(
            "materialized destination differs from the target scenario origin"
        )
    return spec


def require_scenario_origin(
    scenario: StrategicNavigationScenario,
    observed_map_id: int,
) -> MapId:
    """Authenticate the live capture's coarse origin before any planning."""

    if not isinstance(scenario, StrategicNavigationScenario):
        raise TypeError("scenario must be a StrategicNavigationScenario")
    try:
        map_id = MapId(observed_map_id)
    except (TypeError, ValueError) as error:
        raise StrategicScenarioProtocolError(
            "scenario capture map is not a known Red map"
        ) from error
    allowed = STRATEGIC_SCENARIO_ORIGIN_MAPS.get(scenario.origin_region)
    if allowed is None or map_id not in allowed:
        raise StrategicScenarioProtocolError(
            "scenario capture origin differs from strategic scenario"
        )
    return map_id
