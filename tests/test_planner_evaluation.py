from __future__ import annotations

import pytest

from pokemon_red_completion.planner_evaluation import (
    PlannerEvaluationError,
    audit_objective_ranker,
)
from pokemon_red_completion.planner_model import ObjectiveRanker
from pokemon_red_completion.planner_semantics import ObjectiveFeatureProjector
from pokemon_red_completion.quest import Objective, QuestGraph, Specialist


def _graph() -> QuestGraph:
    return QuestGraph(
        (
            Objective(
                id="start",
                title="Start",
                completion_facts=frozenset({"story:start"}),
                specialist=Specialist.INTERACTION,
                priority=0,
            ),
            Objective(
                id="east",
                title="East",
                completion_facts=frozenset({"story:east"}),
                specialist=Specialist.NAVIGATION,
                prerequisites=frozenset({"start"}),
                target_region="east",
            ),
            Objective(
                id="west",
                title="West",
                completion_facts=frozenset({"story:west"}),
                specialist=Specialist.NAVIGATION,
                prerequisites=frozenset({"start"}),
                target_region="west",
            ),
        )
    )


def test_counterfactual_audit_detects_location_sensitive_choices() -> None:
    graph = _graph()
    projector = ObjectiveFeatureProjector(graph)
    weights = [0.0] * len(projector.feature_names)
    weights[projector.feature_names.index("candidate_target_region_matches_current")] = 10.0
    model = ObjectiveRanker(feature_names=projector.feature_names, weights=weights)

    report = audit_objective_ranker(model, graph)

    assert report.reachable_states == 5
    assert report.branching_states == 1
    assert report.location_sensitive_states == 1
    assert report.local_target_selections == report.local_target_opportunities == 2
    assert report.public_dict()["location_sensitivity_rate"] == 1.0


def test_counterfactual_audit_exposes_context_insensitive_ranker() -> None:
    graph = _graph()
    projector = ObjectiveFeatureProjector(graph)
    model = ObjectiveRanker(
        feature_names=projector.feature_names,
        weights=[0.0] * len(projector.feature_names),
    )

    report = audit_objective_ranker(model, graph)

    assert report.location_sensitive_states == 0
    assert report.local_target_selections == 1
    assert report.local_target_opportunities == 2
    assert report.public_dict()["selection_counts"] == {"east": 3}


def test_counterfactual_audit_is_bounded() -> None:
    graph = _graph()
    projector = ObjectiveFeatureProjector(graph)
    model = ObjectiveRanker(
        feature_names=projector.feature_names,
        weights=[0.0] * len(projector.feature_names),
    )

    with pytest.raises(PlannerEvaluationError, match="exceeded"):
        audit_objective_ranker(model, graph, max_reachable_states=2)
