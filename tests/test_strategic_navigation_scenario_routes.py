from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.observation import MapId
from pokemon_red_completion.strategic_navigation import StrategicNavigationTag
from pokemon_red_completion.strategic_navigation_scenario_routes import (
    STRATEGIC_SCENARIO_DESTINATIONS,
    STRATEGIC_SCENARIO_ORIGIN_MAPS,
    ScenarioObjectiveDestinationSpec,
    StrategicScenarioRouteCatalogError,
    require_navigation_materialization_step,
    require_objective_skill_materialization_step,
    require_scenario_origin,
    scenario_destination_specs,
    validate_scenario_route_catalog,
)
from pokemon_red_completion.strategic_navigation_scenarios import (
    StrategicScenarioProtocolError,
    load_strategic_navigation_scenario_registry,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_route_catalog_exactly_covers_preregistered_scenarios() -> None:
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)

    assert validate_scenario_route_catalog(registry) == {
        "candidate_objectives": 18,
        "destination_maps": 18,
        "origin_regions": 7,
    }
    for scenario in registry.learning_scenarios():
        specs = scenario_destination_specs(registry, scenario.scenario_id)
        assert tuple(item.objective_id for item in specs) == (
            scenario.candidate_objective_ids
        )
        assert specs[
            scenario.candidate_objective_ids.index(scenario.teacher_objective_id)
        ].objective_id == scenario.teacher_objective_id


def test_fuchsia_candidate_stops_at_its_authenticated_skill_boundary() -> None:
    spec = STRATEGIC_SCENARIO_DESTINATIONS["reach_fuchsia"]

    assert spec.goal_map is MapId.LAVENDER_POKECENTER
    assert spec.goal_map is not MapId.FUCHSIA_CITY


def test_route_catalog_kills_missing_key_and_mismatched_binding() -> None:
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    missing = dict(STRATEGIC_SCENARIO_DESTINATIONS)
    missing.pop("help_bill")
    with pytest.raises(StrategicScenarioRouteCatalogError, match="coverage differs"):
        validate_scenario_route_catalog(registry, catalog=missing)

    mismatched = dict(STRATEGIC_SCENARIO_DESTINATIONS)
    mismatched["help_bill"] = replace(
        mismatched["help_bill"], objective_id="wrong_objective"
    )
    with pytest.raises(StrategicScenarioRouteCatalogError, match="key differs"):
        validate_scenario_route_catalog(registry, catalog=mismatched)


def test_destination_spec_rejects_unknown_map_and_weak_tag_schema() -> None:
    with pytest.raises(StrategicScenarioRouteCatalogError, match="known Red map"):
        ScenarioObjectiveDestinationSpec(
            "help_bill",
            999,  # type: ignore[arg-type]
            (StrategicNavigationTag.STORY_PROGRESS,),
        )
    with pytest.raises(StrategicScenarioRouteCatalogError, match="unique and sorted"):
        ScenarioObjectiveDestinationSpec(
            "help_bill",
            MapId.BILLS_HOUSE,
            (
                StrategicNavigationTag.STORY_PROGRESS,
                StrategicNavigationTag.REMOVE_BLOCKER,
            ),
        )


def test_origin_preflight_accepts_only_declared_city_boundary() -> None:
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    scenario = next(
        item for item in registry.learning_scenarios() if item.origin_region == "cerulean"
    )

    assert require_scenario_origin(scenario, MapId.CERULEAN_POKECENTER) == (
        MapId.CERULEAN_POKECENTER
    )
    with pytest.raises(StrategicScenarioProtocolError, match="origin differs"):
        require_scenario_origin(scenario, MapId.CELADON_POKECENTER)
    with pytest.raises(StrategicScenarioProtocolError, match="known Red map"):
        require_scenario_origin(scenario, 999)


def test_origin_catalog_kills_missing_region_and_test_stays_sealed() -> None:
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    origins = dict(STRATEGIC_SCENARIO_ORIGIN_MAPS)
    origins.pop("cerulean")
    with pytest.raises(StrategicScenarioRouteCatalogError, match="origin coverage"):
        validate_scenario_route_catalog(registry, origin_maps=origins)

    test = next(item for item in registry.scenarios if item.partition == "test")
    with pytest.raises(StrategicScenarioProtocolError, match="must remain unopened"):
        scenario_destination_specs(registry, test.scenario_id)


def test_navigation_materialization_requires_one_live_location_transition() -> None:
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    source = registry.scenario("red-strategic-scenario-v2-002-train")
    target = registry.scenario("red-strategic-scenario-v2-003-validation")

    spec = require_navigation_materialization_step(
        source,
        target,
        "reach_vermilion",
    )

    assert spec.objective_id == "reach_vermilion"
    assert spec.goal_map is MapId.VERMILION_CITY


def test_navigation_materialization_rejects_approach_or_frontier_overclaims() -> None:
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    source = registry.scenario("red-strategic-scenario-v2-001-train")
    target = registry.scenario("red-strategic-scenario-v2-002-train")

    with pytest.raises(
        StrategicScenarioRouteCatalogError,
        match="does not itself complete",
    ):
        require_navigation_materialization_step(source, target, "help_bill")
    with pytest.raises(StrategicScenarioRouteCatalogError, match="not a source"):
        require_navigation_materialization_step(source, target, "reach_vermilion")

    valid_source = target
    valid_target = registry.scenario("red-strategic-scenario-v2-003-validation")
    with pytest.raises(StrategicScenarioRouteCatalogError, match="add exactly one"):
        require_navigation_materialization_step(
            valid_source,
            replace(
                valid_target,
                completed_objective_ids=(
                    *valid_target.completed_objective_ids,
                    "obtain_cut",
                ),
            ),
            "reach_vermilion",
        )
    with pytest.raises(StrategicScenarioRouteCatalogError, match="target scenario origin"):
        require_navigation_materialization_step(
            valid_source,
            replace(valid_target, origin_region="celadon"),
            "reach_vermilion",
        )


def test_objective_skill_materialization_accepts_exact_non_registry_source() -> None:
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    target = registry.scenario("red-strategic-scenario-v2-043-validation")
    source_completed = frozenset(target.completed_objective_ids).difference(
        {"reach_saffron"}
    )

    assert require_objective_skill_materialization_step(
        source_completed,
        target,
        "reach_saffron",
    ) == frozenset({"reach_saffron"})


def test_objective_skill_materialization_accepts_automatic_effects() -> None:
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    target = registry.scenario("red-strategic-scenario-v2-007-validation")
    source_completed = frozenset(target.completed_objective_ids).difference(
        {"clear_rocket_hideout", "obtain_silph_scope"}
    )

    assert require_objective_skill_materialization_step(
        source_completed,
        target,
        "clear_rocket_hideout",
    ) == frozenset({"clear_rocket_hideout", "obtain_silph_scope"})


def test_objective_skill_materialization_rejects_extra_target_progress() -> None:
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    target = registry.scenario("red-strategic-scenario-v2-047-validation")
    source_completed = frozenset(target.completed_objective_ids).difference(
        {"liberate_silph", "defeat_erika"}
    )

    with pytest.raises(
        StrategicScenarioRouteCatalogError,
        match="target frontier exactly",
    ):
        require_objective_skill_materialization_step(
            source_completed,
            target,
            "liberate_silph",
        )


def test_objective_skill_materialization_rejects_invalid_source_frontier() -> None:
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    target = registry.scenario("red-strategic-scenario-v2-043-validation")
    valid_source = frozenset(target.completed_objective_ids).difference(
        {"reach_saffron"}
    )

    with pytest.raises(
        StrategicScenarioRouteCatalogError,
        match="unknown objective",
    ):
        require_objective_skill_materialization_step(
            valid_source.union({"not_a_real_objective"}),
            target,
            "reach_saffron",
        )

    with pytest.raises(
        StrategicScenarioRouteCatalogError,
        match="violates objective prerequisites",
    ):
        require_objective_skill_materialization_step(
            valid_source.difference({"reach_lavender"}),
            target,
            "reach_saffron",
        )
