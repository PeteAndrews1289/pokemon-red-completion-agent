"""Live authorization boundary for the learned semantic objective planner."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.planner_model import ObjectiveRanker
from pokemon_red_completion.planner_semantics import ObjectiveFeatureProjector
from pokemon_red_completion.quest import Objective, QuestGraph
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
    selected_decisions: int = field(default=0, init=False)
    confidence_total: float = field(default=0.0, init=False)
    minimum_confidence: float = field(default=1.0, init=False)
    candidate_total: int = field(default=0, init=False)
    singleton_decisions: int = field(default=0, init=False)
    branching_decisions: int = field(default=0, init=False)
    branching_confidence_total: float = field(default=0.0, init=False)
    minimum_branching_confidence: float = field(default=1.0, init=False)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between zero and one")
        self.projector = ObjectiveFeatureProjector(self.graph)
        if self.model.feature_names != self.projector.feature_names:
            raise LearnedPlannerPolicyError("planner model feature schema is incompatible")

    def authorize(self, expected_objective_id: str) -> str:
        """Predict from policy-visible state and authorize only the chosen specialist."""

        state = GameState(mode=GameMode.OVERWORLD, facts=frozenset(self._completion_facts))
        return self._choose(state, expected_objective_id=expected_objective_id)

    def select(
        self,
        state: GameState,
        candidates: tuple[Objective, ...] | None = None,
    ) -> str:
        """Choose a legal objective without receiving the fixed route's expected answer."""

        if not isinstance(state, GameState):
            raise TypeError("state must be a GameState")
        selected = self._choose(
            state,
            expected_objective_id=None,
            candidates=candidates,
        )
        self.selected_decisions += 1
        return selected

    def _choose(
        self,
        state: GameState,
        *,
        expected_objective_id: str | None,
        candidates: tuple[Objective, ...] | None = None,
    ) -> str:
        """Rank the objectives available in authoritative semantic state."""

        if self._active_objective_id is not None:
            raise LearnedPlannerPolicyError("a planner objective is already active")
        source = self.snapshot_provider.snapshot()
        snapshot = SemanticSnapshot(
            game_id=source.game_id,
            mode=source.mode,
            location=source.location,
            facts=tuple(sorted(set(source.facts).union(state.facts, self._completion_facts))),
            features=source.features,
        )
        graph_legal = self.graph.available_objectives(state)
        if candidates is None:
            legal = graph_legal
        else:
            legal_by_id = {objective.id: objective for objective in graph_legal}
            if not candidates or len({objective.id for objective in candidates}) != len(candidates):
                raise LearnedPlannerPolicyError("planner candidates must be non-empty and unique")
            if any(
                objective.id not in legal_by_id or legal_by_id[objective.id] != objective
                for objective in candidates
            ):
                raise LearnedPlannerPolicyError("planner candidates are not graph-legal objectives")
            legal = candidates
        if not legal:
            raise LearnedPlannerPolicyError("no legal incomplete objective is available")
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
        self.candidate_total += len(legal)
        if len(legal) == 1:
            self.singleton_decisions += 1
        else:
            self.branching_decisions += 1
            self.branching_confidence_total += confidence
            self.minimum_branching_confidence = min(
                self.minimum_branching_confidence,
                confidence,
            )
        if confidence < self.confidence_threshold:
            raise LearnedPlannerPolicyError(
                f"planner confidence below threshold for {predicted_id}"
            )
        if expected_objective_id is not None and predicted_id != expected_objective_id:
            raise LearnedPlannerPolicyError(
                "learned planner selected a different legal objective: "
                f"predicted={predicted_id}, specialist={legal[predicted_index].specialist.value}"
            )
        if expected_objective_id is not None:
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

    def abandon(self, objective_id: str) -> None:
        """Return unfinished authority to the loop without fabricating completion."""

        if objective_id != self._active_objective_id:
            raise LearnedPlannerPolicyError("abandoned objective was not model-authorized")
        self._active_objective_id = None

    @property
    def completed_objective_count(self) -> int:
        return len(self._completed_ids)

    def public_dict(self) -> dict[str, object]:
        mean_confidence = self.confidence_total / self.decisions if self.decisions else 0.0
        mean_branching_confidence = (
            self.branching_confidence_total / self.branching_decisions
            if self.branching_decisions
            else 0.0
        )
        return {
            "schema": "pokemon-semantic-objective-live-policy-v1",
            "model_id": "pokemon.core.planning.masked-linear-ranker.v1",
            "model_sha256": canonical_sha256(self.model.to_dict()),
            "decisions": self.decisions,
            "authorized_decisions": self.authorized_decisions,
            "selected_decisions": self.selected_decisions,
            "completed_objectives": self.completed_objective_count,
            "mean_confidence": mean_confidence,
            "minimum_confidence": self.minimum_confidence if self.decisions else 0.0,
            "mean_candidate_count": (
                self.candidate_total / self.decisions if self.decisions else 0.0
            ),
            "singleton_decisions": self.singleton_decisions,
            "branching_decisions": self.branching_decisions,
            "mean_branching_confidence": mean_branching_confidence,
            "minimum_branching_confidence": (
                self.minimum_branching_confidence if self.branching_decisions else 0.0
            ),
            "teacher_fallbacks": 0,
            "route_dispatch_mode": (
                "model_selected_specialists"
                if self.selected_decisions
                else "model_authorized_fixed_specialists"
            ),
        }
