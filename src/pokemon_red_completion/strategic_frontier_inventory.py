"""Path-free inventory of authenticated captures against learning scenarios."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.strategic_navigation_scenario_routes import (
    StrategicScenarioRouteCatalogError,
    require_objective_skill_materialization_step,
)
from pokemon_red_completion.strategic_navigation_scenarios import (
    StrategicNavigationScenarioRegistry,
)


def strategic_frontier_inventory(
    captures: Iterable[CapturedProgressEnvelope],
    registry: StrategicNavigationScenarioRegistry,
) -> dict[str, object]:
    """Compare authenticated objective frontiers without exposing capture identity.

    Only train and validation scenarios are accessed. One-skill transitions are
    logical construction candidates: live skill availability, terminal origin,
    and fresh objective observation still have to pass the cartridge materializer.
    """

    if not isinstance(registry, StrategicNavigationScenarioRegistry):
        raise TypeError("registry must be a strategic scenario registry")
    captured = tuple(captures)
    if any(not isinstance(item, CapturedProgressEnvelope) for item in captured):
        raise TypeError("captures must contain captured progress envelopes")

    learning = registry.learning_scenarios()
    frontiers = tuple(frozenset(item.verified_objective_ids) for item in captured)
    unique_frontiers = frozenset(frontiers)
    exact = tuple(
        scenario
        for scenario in learning
        if frozenset(scenario.completed_objective_ids) in unique_frontiers
    )
    exact_ids = frozenset(item.scenario_id for item in exact)

    transition_sources: dict[tuple[str, str], list[frozenset[str]]] = defaultdict(list)
    for source in frontiers:
        for target in learning:
            for objective in COMPLETION_QUEST:
                try:
                    require_objective_skill_materialization_step(
                        source,
                        target,
                        objective.id,
                    )
                except StrategicScenarioRouteCatalogError:
                    continue
                transition_sources[target.scenario_id, objective.id].append(source)

    candidates_by_target: dict[str, list[tuple[str, list[frozenset[str]]]]] = (
        defaultdict(list)
    )
    for (target_id, objective_id), sources in transition_sources.items():
        candidates_by_target[target_id].append((objective_id, sources))

    one_skill_targets = []
    for target_id in sorted(candidates_by_target):
        candidates = candidates_by_target[target_id]
        all_sources = [source for _, sources in candidates for source in sources]
        one_skill_targets.append(
            {
                "target_scenario_id": target_id,
                "already_exact": target_id in exact_ids,
                "objective_ids": sorted(objective_id for objective_id, _ in candidates),
                "authenticated_source_envelopes": len(all_sources),
                "unique_source_frontiers": len(set(all_sources)),
            }
        )

    return {
        "schema": "strategic-frontier-inventory-v1",
        "authenticated_capture_envelopes": len(captured),
        "unique_authenticated_frontiers": len(unique_frontiers),
        "learning_scenarios": len(learning),
        "exact_learning_scenario_count": len(exact),
        "exact_learning_scenario_ids": sorted(exact_ids),
        "missing_learning_scenario_count": len(learning) - len(exact),
        "missing_learning_scenario_ids": sorted(
            item.scenario_id for item in learning if item.scenario_id not in exact_ids
        ),
        "logical_one_skill_target_count": len(one_skill_targets),
        "logical_one_skill_targets": one_skill_targets,
        "claim_boundary": {
            "live_skill_availability_checked": False,
            "target_origin_checked": False,
            "fresh_terminal_frontier_checked": False,
            "test_scenarios_opened": 0,
        },
    }
