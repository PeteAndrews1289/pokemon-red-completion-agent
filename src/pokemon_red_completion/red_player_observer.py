"""Pokémon Red semantic observer for authenticated captured-state replay."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.domain import GameState
from pokemon_red_completion.observation import (
    RawGameState,
    game_mode,
    location_label,
    semantic_facts,
)
from pokemon_red_completion.quest import QuestGraph


class ResumedStateError(ValueError):
    """Raised when captured progress cannot establish trustworthy planner state."""


class RawStateReader(Protocol):
    def read(self) -> RawGameState: ...


@dataclass(slots=True)
class CapturedPokemonRedObserver:
    """Latch live Red facts on top of a state-digest-bound objective history."""

    reader: RawStateReader
    graph: QuestGraph
    envelope: CapturedProgressEnvelope
    _latched_facts: set[str] = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        completed = frozenset(self.envelope.verified_objective_ids)
        known = frozenset(objective.id for objective in self.graph)
        unknown = completed.difference(known)
        if unknown:
            raise ResumedStateError(
                "capture progress contains unknown objectives: " + ", ".join(sorted(unknown))
            )
        inconsistent = tuple(
            objective.id
            for objective in self.graph
            if objective.id in completed and not objective.prerequisites.issubset(completed)
        )
        if inconsistent:
            raise ResumedStateError(
                "capture progress violates objective prerequisites: " + ", ".join(inconsistent)
            )
        self._latched_facts.update(
            fact
            for objective_id in completed
            for fact in self.graph.objective(objective_id).completion_facts
        )

    def observe(self) -> GameState:
        raw = self.reader.read()
        live_facts = semantic_facts(raw)
        state = GameState(
            mode=game_mode(raw),
            facts=frozenset(self._latched_facts.union(live_facts)),
            location=location_label(raw.map_id),
        )
        completed = self.graph.completed_ids(state)
        inconsistent = tuple(
            objective.id
            for objective in self.graph
            if objective.id in completed and not objective.prerequisites.issubset(completed)
        )
        if inconsistent:
            raise ResumedStateError(
                "live captured state exposes out-of-order objective evidence: "
                + ", ".join(inconsistent)
            )
        self._latched_facts.update(
            fact
            for objective_id in completed
            for fact in self.graph.objective(objective_id).completion_facts
        )
        return GameState(
            mode=state.mode,
            facts=frozenset(self._latched_facts.union(live_facts)),
            location=state.location,
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-red-captured-semantic-observer-v1",
            "checkpoint_id": self.envelope.checkpoint_id,
            "checkpoints_completed": self.envelope.checkpoints_completed,
            "verified_objectives": list(self.envelope.verified_objective_ids),
            "latched_fact_count": len(self._latched_facts),
        }
