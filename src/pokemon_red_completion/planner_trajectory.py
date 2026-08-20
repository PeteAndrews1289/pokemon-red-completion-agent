"""Game-neutral objective-selection supervision for whole-game planners."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.quest import QuestGraph
from pokemon_red_completion.trajectory import (
    DecisionContext,
    DecisionRecord,
    SemanticSnapshot,
    SnapshotProvider,
)

POKEMON_OBJECTIVE_SELECTION_SKILL_ID = "pokemon.core:planning:objective_selection"


class ObjectiveDecisionRecorder(Protocol):
    """Minimal recorder boundary needed by the game-neutral planner observer."""

    episode_id: str

    @property
    def next_step_index(self) -> int: ...

    def record_standalone_decision(self, decision: DecisionRecord) -> bool: ...


@dataclass(slots=True)
class SemanticObjectiveDecisionObserver:
    """Record teacher objective choices without leaking the teacher into inputs.

    The policy snapshot is the live game-neutral observation augmented only by
    cumulative completion facts that a runtime verifier has already established.
    Candidate objective IDs and the selected label live in context/action fields,
    which are supervision rather than policy features.
    """

    graph: QuestGraph
    snapshot_provider: SnapshotProvider
    recorder: ObjectiveDecisionRecorder
    policy_id: str
    actor: str = "deterministic_teacher"
    _completed_ids: set[str] = field(default_factory=set, init=False)
    _completion_facts: set[str] = field(default_factory=set, init=False)
    _active_objective_id: str | None = field(default=None, init=False)
    _next_decision_index: int = field(default=0, init=False)

    @property
    def completed_ids(self) -> frozenset[str]:
        return frozenset(self._completed_ids)

    @property
    def completion_facts(self) -> frozenset[str]:
        return frozenset(self._completion_facts)

    @property
    def active_objective_id(self) -> str | None:
        return self._active_objective_id

    def select(self, objective_id: str) -> bool:
        """Record one legal teacher choice at the current execution boundary."""

        if self._active_objective_id is not None:
            raise ValueError("an objective is already active")
        objective = self.graph.objective(objective_id)
        state = GameState(mode=GameMode.OVERWORLD, facts=self._completion_facts)
        available = self.graph.available_objectives(state)
        legal_ids = tuple(candidate.id for candidate in available)
        if objective_id not in legal_ids:
            raise ValueError(f"objective is not currently legal: {objective_id}")

        source = self.snapshot_provider.snapshot()
        snapshot = SemanticSnapshot(
            game_id=source.game_id,
            mode=source.mode,
            location=source.location,
            facts=tuple((*source.facts, *self._completion_facts)),
            features=source.features,
        )
        decision_index = self._next_decision_index
        recorded = self.recorder.record_standalone_decision(
            DecisionRecord(
                decision_id=(
                    f"{self.recorder.episode_id}:planner-decision:{decision_index}"
                ),
                episode_id=self.recorder.episode_id,
                step_index=self.recorder.next_step_index,
                snapshot=snapshot,
                context=DecisionContext(
                    objective_id=objective_id,
                    policy_id=self.policy_id,
                    actor=self.actor,
                    metadata={
                        "skill_id": POKEMON_OBJECTIVE_SELECTION_SKILL_ID,
                        "legal_objective_ids": legal_ids,
                    },
                ),
                decision_type="objective_selection",
                action={
                    "kind": "select_objective",
                    "objective_id": objective_id,
                    "specialist": objective.specialist.value,
                },
            )
        )
        self._next_decision_index += 1
        self._active_objective_id = objective_id
        return recorded

    def complete(self, objective_id: str) -> None:
        """Accept verifier evidence for the selected objective."""

        if objective_id != self._active_objective_id:
            raise ValueError(
                f"completed objective {objective_id!r} does not match active "
                f"objective {self._active_objective_id!r}"
            )
        objective = self.graph.objective(objective_id)
        self._completed_ids.add(objective_id)
        self._completion_facts.update(objective.completion_facts)
        self._active_objective_id = None
