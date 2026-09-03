"""Thin Pokémon Red observation bridge for the title-neutral bounded player.

This module does not choose a goal or send controller input.  It projects the
existing authenticated Red state adapter, goal binding enumerator and living-
collection ledger into the generic player observation consumed by
``run_bounded_player_episode``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalManagerQuestion
from pokemon_red_completion.goal_manager_composition_qualification import (
    living_collection_checkpoint,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    GoalManagerCompositionObservation,
    LivingCollectionCheckpoint,
)
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context import RedGoalContextRuntime
from pokemon_red_completion.red_goal_manager import RedGoalObservation


class RedBoundedPlayerError(RuntimeError):
    """Raised when Red cannot produce a truthful generic player observation."""


CollectionProjector = Callable[[RedGoalObservation], LivingCollectionCheckpoint]


@dataclass(slots=True)
class RedBoundedPlayerObserver:
    """Action-free callable bridge over the existing Red runtime context."""

    runtime: RedGoalContextRuntime
    actions: CountingExecutor
    collection_projector: CollectionProjector = living_collection_checkpoint

    def __post_init__(self) -> None:
        if not callable(self.collection_projector):
            raise TypeError("collection_projector must be callable")

    def __call__(self) -> GoalManagerCompositionObservation:
        live = self.runtime.adapter.observe()
        if not isinstance(live, RedGoalObservation):
            raise RedBoundedPlayerError("Red adapter returned an invalid observation")
        binding_set = self.runtime.enumerator(self.actions).enumerate(live)
        if not isinstance(binding_set, GoalBindingSet):
            raise RedBoundedPlayerError("Red enumerator returned an invalid binding set")
        collection = self.collection_projector(live)
        if not isinstance(collection, LivingCollectionCheckpoint):
            raise RedBoundedPlayerError("Red collection projector returned an invalid checkpoint")
        semantic_document = red_bounded_player_semantic_document(
            live=live,
            binding_set=binding_set,
            collection=collection,
        )
        return GoalManagerCompositionObservation(
            semantic_state_sha256=canonical_sha256(semantic_document),
            situation=live.situation,
            binding_set=binding_set,
            collection=collection,
        )


def red_bounded_player_semantic_document(
    *,
    live: RedGoalObservation,
    binding_set: GoalBindingSet,
    collection: LivingCollectionCheckpoint,
) -> Mapping[str, object]:
    """Return the public, binding-free state whose digest drives replanning."""

    if not isinstance(live, RedGoalObservation):
        raise TypeError("live must be a RedGoalObservation")
    if not isinstance(binding_set, GoalBindingSet):
        raise TypeError("binding_set must be a GoalBindingSet")
    if not isinstance(collection, LivingCollectionCheckpoint):
        raise TypeError("collection must be a LivingCollectionCheckpoint")
    question = GoalManagerQuestion(
        situation=live.situation,
        opportunities=binding_set.opportunities,
    )
    policy_input = {
        "candidates": [item.policy_dict() for item in question.opportunities],
        "schema": "pokemon.core.goal-manager-input.v1",
        "situation": question.situation.policy_dict(),
    }
    return {
        "collection": collection.public_dict(),
        "goal_observation": live.public_dict(),
        "policy_input": policy_input,
        "schema": "pokemon.red.bounded-player-semantic-state.v1",
    }
