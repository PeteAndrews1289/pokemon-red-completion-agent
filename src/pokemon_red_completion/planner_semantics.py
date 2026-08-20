"""Portable semantic features for ranking whole-game objectives."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.quest import Objective, QuestGraph

PLANNER_FEATURE_SCHEMA_ID = "pokemon.core.planning.objective-ranker.v1"
_SPECIALISTS = (
    "bootstrap",
    "navigation",
    "interaction",
    "menu",
    "battle",
    "recovery",
    "verification",
)
_FACT_KINDS = (
    "system",
    "story",
    "party",
    "location",
    "badge",
    "item",
    "move",
    "league",
    "game",
    "other",
)


class PlannerFeatureError(ValueError):
    """Raised when a planner example cannot be projected safely."""


@dataclass(frozen=True, slots=True)
class ObjectiveFeatureBatch:
    feature_names: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    candidate_vectors: NDArray[np.float64]

    def __post_init__(self) -> None:
        if self.candidate_vectors.shape != (len(self.candidate_ids), len(self.feature_names)):
            raise PlannerFeatureError("objective feature matrix has an invalid shape")
        if not np.all(np.isfinite(self.candidate_vectors)):
            raise PlannerFeatureError("objective features must be finite")
        self.candidate_vectors.setflags(write=False)


class ObjectiveFeatureProjector:
    """Project state/objective pairs without game IDs or objective-ID features."""

    def __init__(self, graph: QuestGraph) -> None:
        if not isinstance(graph, QuestGraph):
            raise TypeError("graph must be a QuestGraph")
        self._graph = graph

    @property
    def feature_names(self) -> tuple[str, ...]:
        names = [
            "bias",
            "candidate_priority",
            "candidate_prerequisite_count",
            "candidate_direct_dependant_count",
        ]
        names.extend(f"specialist:{name}" for name in _SPECIALISTS)
        names.extend(f"completion_kind:{name}" for name in _FACT_KINDS)
        names.extend(f"progress_x_specialist:{name}" for name in _SPECIALISTS)
        names.extend(f"badges_x_completion_kind:{name}" for name in _FACT_KINDS)
        names.extend(
            (
                "candidate_target_region_matches_current",
                "candidate_is_next_league_stage",
            )
        )
        return tuple(names)

    def project(
        self,
        snapshot: Mapping[str, object],
        candidates: Sequence[Objective],
        *,
        objective_count: int,
    ) -> ObjectiveFeatureBatch:
        if not candidates:
            raise PlannerFeatureError("objective projection requires legal candidates")
        if type(objective_count) is not int or objective_count < 1:  # noqa: E721
            raise PlannerFeatureError("objective_count must be positive")
        facts = _string_sequence(snapshot.get("facts"), subject="snapshot facts")
        features = _mapping(snapshot.get("features"), subject="snapshot features")
        progress = _mapping(features.get("progress"), subject="progress features")
        badge_count = progress.get("badge_count", 0)
        badge_target = progress.get("badge_target", 8)
        if type(badge_target) is not int or badge_target < 1:  # noqa: E721
            raise PlannerFeatureError("badge_target must be a positive integer")
        if (  # noqa: E721
            type(badge_count) is not int or not 0 <= badge_count <= badge_target
        ):
            raise PlannerFeatureError("badge_count must fit the declared badge target")
        world = _mapping(features.get("world"), subject="world features")
        area_kind = world.get("area_kind")
        if area_kind is not None and not isinstance(area_kind, str):
            raise PlannerFeatureError("area_kind must be a string or null")
        completed_objective_facts = tuple(
            fact for fact in facts if not fact.startswith("pokemon.core:")
        )
        progress_fraction = min(1.0, len(completed_objective_facts) / objective_count)
        badge_fraction = badge_count / badge_target

        rows: list[list[float]] = []
        candidate_ids: list[str] = []
        for candidate in candidates:
            specialist = candidate.specialist.value
            completion_kinds = {_fact_kind(fact) for fact in candidate.completion_facts}
            row: list[float] = [
                1.0,
                min(candidate.priority, 1000) / 1000.0,
                min(len(candidate.prerequisites), 8) / 8.0,
                min(self._graph.direct_dependant_count(candidate.id), 8) / 8.0,
            ]
            row.extend(float(specialist == name) for name in _SPECIALISTS)
            row.extend(float(name in completion_kinds) for name in _FACT_KINDS)
            row.extend(progress_fraction * float(specialist == name) for name in _SPECIALISTS)
            row.extend(badge_fraction * float(name in completion_kinds) for name in _FACT_KINDS)
            row.append(
                float(
                    candidate.target_region is not None
                    and _region_matches(snapshot.get("location"), candidate.target_region)
                )
            )
            row.append(float("league" in completion_kinds))
            rows.append(row)
            candidate_ids.append(candidate.id)
        return ObjectiveFeatureBatch(
            feature_names=self.feature_names,
            candidate_ids=tuple(candidate_ids),
            candidate_vectors=np.asarray(rows, dtype=np.float64),
        )


def _fact_kind(fact: str) -> str:
    prefix = fact.partition(":")[0]
    return prefix if prefix in _FACT_KINDS[:-1] else "other"


def _region_matches(location: object, target_region: str) -> bool:
    if not isinstance(location, str):
        return False
    area = location.rpartition(":")[2]
    return target_region in area.split("_")


def _mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise PlannerFeatureError(f"{subject} must be a mapping")
    return value


def _string_sequence(value: object, *, subject: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise PlannerFeatureError(f"{subject} must be a sequence")
    if any(not isinstance(item, str) or not item for item in value):
        raise PlannerFeatureError(f"{subject} must contain non-empty strings")
    return tuple(value)
