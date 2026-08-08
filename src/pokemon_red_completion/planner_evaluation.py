"""Counterfactual evaluation for semantic objective rankers."""

from __future__ import annotations

import math
from collections import Counter, deque
from dataclasses import dataclass

import numpy as np

from pokemon_red_completion.planner_model import ObjectiveRanker
from pokemon_red_completion.planner_semantics import ObjectiveFeatureProjector
from pokemon_red_completion.quest import QuestGraph
from pokemon_red_completion.trajectory import canonical_sha256


class PlannerEvaluationError(ValueError):
    """Raised when a bounded counterfactual audit cannot be completed."""


@dataclass(frozen=True, slots=True)
class PlannerCounterfactualCase:
    completed_ids: frozenset[str]
    candidate_ids: tuple[str, ...]
    location: str | None
    selected_id: str
    confidence: float
    margin: float
    entropy: float

    def public_dict(self) -> dict[str, object]:
        return {
            "completed_ids": sorted(self.completed_ids),
            "candidate_ids": list(self.candidate_ids),
            "location": self.location,
            "selected_id": self.selected_id,
            "confidence": self.confidence,
            "margin": self.margin,
            "entropy": self.entropy,
        }


@dataclass(frozen=True, slots=True)
class PlannerCounterfactualReport:
    model_sha256: str
    reachable_states: int
    branching_states: int
    cases: tuple[PlannerCounterfactualCase, ...]
    location_sensitive_states: int
    local_target_selections: int
    local_target_opportunities: int

    @property
    def mean_confidence(self) -> float:
        return sum(case.confidence for case in self.cases) / len(self.cases) if self.cases else 0.0

    @property
    def mean_margin(self) -> float:
        return sum(case.margin for case in self.cases) / len(self.cases) if self.cases else 0.0

    @property
    def local_target_rate(self) -> float:
        return (
            self.local_target_selections / self.local_target_opportunities
            if self.local_target_opportunities
            else 0.0
        )

    def public_dict(self, *, include_cases: bool = False) -> dict[str, object]:
        selected = Counter(case.selected_id for case in self.cases)
        result: dict[str, object] = {
            "schema": "pokemon-objective-counterfactual-audit-v1",
            "model_sha256": self.model_sha256,
            "reachable_states": self.reachable_states,
            "branching_states": self.branching_states,
            "evaluations": len(self.cases),
            "location_sensitive_states": self.location_sensitive_states,
            "location_sensitivity_rate": (
                self.location_sensitive_states / self.branching_states
                if self.branching_states
                else 0.0
            ),
            "local_target_selections": self.local_target_selections,
            "local_target_opportunities": self.local_target_opportunities,
            "local_target_rate": self.local_target_rate,
            "mean_confidence": self.mean_confidence,
            "mean_margin": self.mean_margin,
            "selection_counts": dict(sorted(selected.items())),
        }
        if include_cases:
            result["cases"] = [case.public_dict() for case in self.cases]
        return result


def audit_objective_ranker(
    model: ObjectiveRanker,
    graph: QuestGraph,
    *,
    max_reachable_states: int = 20_000,
) -> PlannerCounterfactualReport:
    """Score every reachable branching state under neutral and candidate-local contexts."""

    if type(max_reachable_states) is not int or max_reachable_states <= 0:  # noqa: E721
        raise ValueError("max_reachable_states must be a positive integer")
    projector = ObjectiveFeatureProjector(graph)
    if model.feature_names != projector.feature_names:
        raise PlannerEvaluationError("planner model feature schema is incompatible")

    reachable = _reachable_completed_sets(graph, maximum=max_reachable_states)
    cases: list[PlannerCounterfactualCase] = []
    branching_states = 0
    location_sensitive_states = 0
    local_target_selections = 0
    local_target_opportunities = 0
    for completed_ids in reachable:
        facts = _completion_facts(graph, completed_ids)
        candidates = tuple(
            objective
            for objective in graph
            if objective.id not in completed_ids and objective.prerequisites.issubset(completed_ids)
        )
        if len(candidates) < 2:
            continue
        branching_states += 1
        locations: tuple[str | None, ...] = (
            None,
            *sorted(
                {
                    candidate.target_region
                    for candidate in candidates
                    if candidate.target_region is not None
                }
            ),
        )
        state_selections: set[str] = set()
        for location in locations:
            batch = projector.project(
                _snapshot(facts, location=location),
                candidates,
                objective_count=len(graph),
            )
            probabilities = model.probabilities(batch.candidate_vectors)
            selected_index = int(np.argmax(probabilities))
            ordered = np.sort(probabilities)
            confidence = float(ordered[-1])
            margin = float(ordered[-1] - ordered[-2])
            entropy = float(
                -sum(
                    probability * math.log(probability)
                    for probability in probabilities
                    if probability > 0.0
                )
            )
            selected_id = batch.candidate_ids[selected_index]
            state_selections.add(selected_id)
            if location is not None:
                local_target_opportunities += 1
                selected = graph.objective(selected_id)
                if selected.target_region == location:
                    local_target_selections += 1
            cases.append(
                PlannerCounterfactualCase(
                    completed_ids=completed_ids,
                    candidate_ids=batch.candidate_ids,
                    location=location,
                    selected_id=selected_id,
                    confidence=confidence,
                    margin=margin,
                    entropy=entropy,
                )
            )
        if len(state_selections) > 1:
            location_sensitive_states += 1

    return PlannerCounterfactualReport(
        model_sha256=canonical_sha256(model.to_dict()),
        reachable_states=len(reachable),
        branching_states=branching_states,
        cases=tuple(cases),
        location_sensitive_states=location_sensitive_states,
        local_target_selections=local_target_selections,
        local_target_opportunities=local_target_opportunities,
    )


def _reachable_completed_sets(
    graph: QuestGraph,
    *,
    maximum: int,
) -> tuple[frozenset[str], ...]:
    initial: frozenset[str] = frozenset()
    queue = deque((initial,))
    seen = {initial}
    while queue:
        completed = queue.popleft()
        available = tuple(
            objective
            for objective in graph
            if objective.id not in completed and objective.prerequisites.issubset(completed)
        )
        for objective in available:
            successor = completed.union((objective.id,))
            if successor in seen:
                continue
            if len(seen) >= maximum:
                raise PlannerEvaluationError("reachable-state audit exceeded its declared bound")
            seen.add(successor)
            queue.append(successor)
    return tuple(sorted(seen, key=lambda value: (len(value), tuple(sorted(value)))))


def _completion_facts(graph: QuestGraph, completed_ids: frozenset[str]) -> frozenset[str]:
    return frozenset(
        fact
        for objective_id in completed_ids
        for fact in graph.objective(objective_id).completion_facts
    )


def _snapshot(facts: frozenset[str], *, location: str | None) -> dict[str, object]:
    badge_count = sum(fact.startswith("badge:") for fact in facts)
    return {
        "game_id": "pokemon.counterfactual",
        "mode": "interactive",
        "location": (f"pokemon.counterfactual:area:{location}" if location is not None else None),
        "facts": sorted(facts),
        "features": {
            "progress": {"badge_count": badge_count},
            "world": {"area_kind": "counterfactual"},
        },
    }
