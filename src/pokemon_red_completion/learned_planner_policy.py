"""Live authorization boundary for the learned semantic objective planner."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.planner_model import ObjectiveRanker
from pokemon_red_completion.planner_semantics import ObjectiveFeatureProjector
from pokemon_red_completion.quest import QuestGraph
from pokemon_red_completion.trajectory import (
    SemanticSnapshot,
    SnapshotProvider,
    canonical_sha256,
)


class LearnedPlannerPolicyError(RuntimeError):
    """Raised when the live model cannot authorize the next specialist."""


@dataclass(slots=True)
class ModelObjectivePolicy:
    """Let a learned ranker authorize each objective before its specialist runs."""

    model: ObjectiveRanker
    graph: QuestGraph
    snapshot_provider: SnapshotProvider
    confidence_threshold: float = 0.0
    projector: ObjectiveFeatureProjector = field(init=False)
    _completed_ids: set[str] = field(default_factory=set, init=False)
    _completion_facts: set[str] = field(default_factory=set, init=False)
    _active_objective_id: str | None = field(default=None, init=False)
    decisions: int = field(default=0, init=False)
    authorized_decisions: int = field(default=0, init=False)
    confidence_total: float = field(default=0.0, init=False)
    minimum_confidence: float = field(default=1.0, init=False)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between zero and one")
        self.projector = ObjectiveFeatureProjector(self.graph)
        if self.model.feature_names != self.projector.feature_names:
            raise LearnedPlannerPolicyError("planner model feature schema is incompatible")

    def authorize(self, expected_objective_id: str) -> str:
        """Predict from policy-visible state and authorize only the chosen specialist."""

        if self._active_objective_id is not None:
            raise LearnedPlannerPolicyError("a planner objective is already active")
        source = self.snapshot_provider.snapshot()
        snapshot = SemanticSnapshot(
            game_id=source.game_id,
            mode=source.mode,
            location=source.location,
            facts=tuple((*source.facts, *self._completion_facts)),
            features=source.features,
        )
        state = GameState(mode=GameMode.OVERWORLD, facts=self._completion_facts)
        legal = self.graph.available_objectives(state)
        batch = self.projector.project(
            snapshot.to_dict(),
            legal,
            objective_count=len(self.graph),
        )
        probabilities = self.model.probabilities(batch.candidate_vectors)
        predicted_index = int(np.argmax(probabilities))
        predicted_id = batch.candidate_ids[predicted_index]
        confidence = float(probabilities[predicted_index])
        self.decisions += 1
        self.confidence_total += confidence
        self.minimum_confidence = min(self.minimum_confidence, confidence)
        if confidence < self.confidence_threshold:
            raise LearnedPlannerPolicyError(
                f"planner confidence below threshold for {predicted_id}"
            )
        if predicted_id != expected_objective_id:
            raise LearnedPlannerPolicyError(
                "learned planner selected a different legal objective: "
                f"predicted={predicted_id}, specialist={legal[predicted_index].specialist.value}"
            )
        self.authorized_decisions += 1
        self._active_objective_id = predicted_id
        return predicted_id

    def complete(self, objective_id: str) -> None:
        """Advance only when the verifier completes the model-authorized objective."""

        if objective_id != self._active_objective_id:
            raise LearnedPlannerPolicyError("verifier completed an unauthorized objective")
        objective = self.graph.objective(objective_id)
        self._completed_ids.add(objective_id)
        self._completion_facts.update(objective.completion_facts)
        self._active_objective_id = None

    @property
    def completed_objective_count(self) -> int:
        return len(self._completed_ids)

    def public_dict(self) -> dict[str, object]:
        mean_confidence = self.confidence_total / self.decisions if self.decisions else 0.0
        return {
            "schema": "pokemon-semantic-objective-live-policy-v1",
            "model_id": "pokemon.core.planning.masked-linear-ranker.v1",
            "model_sha256": canonical_sha256(self.model.to_dict()),
            "decisions": self.decisions,
            "authorized_decisions": self.authorized_decisions,
            "completed_objectives": self.completed_objective_count,
            "mean_confidence": mean_confidence,
            "minimum_confidence": self.minimum_confidence if self.decisions else 0.0,
            "teacher_fallbacks": 0,
            "route_dispatch_mode": "model_authorized_fixed_specialists",
        }
