"""Thin Pokémon Red observation bridge for the title-neutral bounded player.

This module does not choose a goal or send controller input.  It projects the
existing authenticated Red state adapter, goal binding enumerator and living-
collection ledger into the generic player observation consumed by
``run_bounded_player_episode``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace

from pokemon_red_completion.bounded_player_episode import _retaining_binding_set
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import (
    BoundGoalSelection,
    GoalKind,
    GoalManagerQuestion,
    bind_goal_selection,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    living_collection_checkpoint,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    CompositionBudgetMeter,
    GoalManagerCompositionObservation,
    LivingCollectionCheckpoint,
)
from pokemon_red_completion.goal_manager_runtime import (
    GoalBindingSet,
    GoalDecisionAuthority,
)
from pokemon_red_completion.goal_manager_trajectory import ordered_goal_manager_question
from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context import RedGoalContextRuntime
from pokemon_red_completion.red_goal_manager import RedGoalObservation


class RedBoundedPlayerError(RuntimeError):
    """Raised when Red cannot produce a truthful generic player observation."""


_PUBLIC_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


CollectionProjector = Callable[[RedGoalObservation], LivingCollectionCheckpoint]


@dataclass(slots=True)
class RedBoundedPlayerObserver:
    """Action-free callable bridge over the existing Red runtime context."""

    runtime: RedGoalContextRuntime
    actions: CountingExecutor
    collection_projector: CollectionProjector = living_collection_checkpoint
    enumerate_bindings: Callable[[RedGoalObservation], GoalBindingSet] | None = None
    search_memory: GoalSearchMemory | None = None
    last_live_observation: RedGoalObservation | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not callable(self.collection_projector):
            raise TypeError("collection_projector must be callable")
        if self.enumerate_bindings is not None and not callable(self.enumerate_bindings):
            raise TypeError("enumerate_bindings must be callable")

    def __call__(self) -> GoalManagerCompositionObservation:
        self.last_live_observation = None
        live = self.runtime.adapter.observe()
        if not isinstance(live, RedGoalObservation):
            raise RedBoundedPlayerError("Red adapter returned an invalid observation")
        binding_set = (
            self.runtime.enumerator(self.actions).enumerate(live)
            if self.enumerate_bindings is None
            else self.enumerate_bindings(live)
        )
        if not isinstance(binding_set, GoalBindingSet):
            raise RedBoundedPlayerError("Red enumerator returned an invalid binding set")
        collection = self.collection_projector(live)
        if not isinstance(collection, LivingCollectionCheckpoint):
            raise RedBoundedPlayerError("Red collection projector returned an invalid checkpoint")
        if self.search_memory is not None:
            bindings = tuple(
                replace(binding, search_history=self.search_memory.lookup(
                    binding.search_memory_source, collection.required_specimens_sha256,
                )) if binding.kind is GoalKind.ACQUIRE_SPECIES else binding
                for binding in binding_set.bindings
            )
            by_ref = {binding.binding_ref: binding.opportunity for binding in bindings}
            binding_set = GoalBindingSet(tuple(
                by_ref.get(opportunity.binding_ref, opportunity)
                for opportunity in binding_set.opportunities
            ), bindings)
        semantic_document = red_bounded_player_semantic_document(
            live=live,
            binding_set=binding_set,
            collection=collection,
        )
        result = GoalManagerCompositionObservation(
            semantic_state_sha256=canonical_sha256(semantic_document),
            situation=live.situation,
            binding_set=binding_set,
            collection=collection,
        )
        self.last_live_observation = live
        return result


@dataclass(frozen=True, slots=True)
class RedBoundedPlayerPreflightChoice:
    """One action-free authority commitment over the same semantic question."""

    authority_id: str
    selected_kind: GoalKind
    selected_candidate_index: int

    def public_dict(self) -> dict[str, object]:
        return {
            "authority_id": self.authority_id,
            "selected_candidate_index": self.selected_candidate_index,
            "selected_kind": self.selected_kind.value,
        }


@dataclass(frozen=True, slots=True)
class RedBoundedPlayerPreflight:
    """Path-free proof that one Red snapshot is ready for a paired episode."""

    assignment_id: str
    semantic_state_sha256: str
    policy_context_sha256: str
    available_menu_sha256: str
    available_goal_kinds: tuple[GoalKind, ...]
    collection: LivingCollectionCheckpoint
    choices: tuple[RedBoundedPlayerPreflightChoice, ...]

    @property
    def authority_disagreement(self) -> bool:
        return len({choice.selected_kind for choice in self.choices}) > 1

    def public_dict(self) -> dict[str, object]:
        return {
            "actions_executed": 0,
            "assignment_id": self.assignment_id,
            "authority_disagreement": self.authority_disagreement,
            "available_goal_count": len(self.available_goal_kinds),
            "available_goal_kinds": [kind.value for kind in self.available_goal_kinds],
            "available_menu_sha256": self.available_menu_sha256,
            "choices": [choice.public_dict() for choice in self.choices],
            "collection": self.collection.public_dict(),
            "emulator_frames": 0,
            "episode_created": False,
            "policy_context_sha256": self.policy_context_sha256,
            "private_binding_fields": 0,
            "private_path_fields": 0,
            "schema": "pokemon.red.bounded-player-preflight.v1",
            "semantic_state_sha256": self.semantic_state_sha256,
            "status": "ready",
        }


def preflight_red_bounded_player(
    *,
    observe: Callable[[], GoalManagerCompositionObservation],
    budget_meter: CompositionBudgetMeter,
    assignment_id: str,
    authorities: tuple[tuple[str, GoalDecisionAuthority], ...],
) -> RedBoundedPlayerPreflight:
    """Observe and compare authorities without executing a binding or opening an episode."""

    if not callable(observe):
        raise TypeError("observe must be callable")
    checkpoint = getattr(budget_meter, "checkpoint", None)
    if not callable(checkpoint):
        raise TypeError("budget_meter must expose checkpoint")
    if not isinstance(assignment_id, str) or _PUBLIC_ID.fullmatch(assignment_id) is None:
        raise RedBoundedPlayerError("assignment_id must be a path-free public identifier")
    if (
        not isinstance(authorities, tuple)
        or len(authorities) < 2
        or any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or _PUBLIC_ID.fullmatch(item[0]) is None
            or not callable(getattr(item[1], "select", None))
            for item in authorities
        )
        or len({item[0] for item in authorities}) != len(authorities)
    ):
        raise RedBoundedPlayerError("preflight needs distinct path-free authorities")
    initial_budget = checkpoint()
    observation = observe()
    if not isinstance(observation, GoalManagerCompositionObservation):
        raise RedBoundedPlayerError("preflight observer returned an invalid observation")
    if checkpoint() != initial_budget:
        raise RedBoundedPlayerError("preflight observation attempted emulator work")
    # Exercise the same metadata-preserving wrapper as real play, without
    # invoking a binding. This catches integration mismatches before an episode.
    _retaining_binding_set(observation.binding_set, budget_meter)
    question = ordered_goal_manager_question(
        assignment_id=assignment_id,
        decision_index=0,
        situation=observation.situation,
        opportunities=observation.binding_set.opportunities,
    )
    if len(question.available_indices) < 2:
        raise RedBoundedPlayerError("preflight snapshot lacks a genuine semantic choice")
    choices_list: list[RedBoundedPlayerPreflightChoice] = []
    for authority_id, authority in authorities:
        choices_list.append(_preflight_choice(authority_id, authority, question))
        if checkpoint() != initial_budget:
            raise RedBoundedPlayerError(
                f"preflight authority {authority_id!r} attempted emulator work"
            )
    choices = tuple(choices_list)
    return RedBoundedPlayerPreflight(
        assignment_id=assignment_id,
        semantic_state_sha256=observation.semantic_state_sha256,
        policy_context_sha256=question.policy_context_sha256,
        available_menu_sha256=question.available_menu_sha256,
        available_goal_kinds=tuple(
            question.opportunities[index].kind for index in question.available_indices
        ),
        collection=observation.collection,
        choices=choices,
    )


def _preflight_choice(
    authority_id: str,
    authority: GoalDecisionAuthority,
    question: GoalManagerQuestion,
) -> RedBoundedPlayerPreflightChoice:
    selected = authority.select(question)
    if isinstance(selected, BoundGoalSelection):
        rebound = bind_goal_selection(question, selected.selected_index)
        if rebound != selected:
            raise RedBoundedPlayerError(
                "preflight authority returned a choice for another question"
            )
        bound = selected
    elif type(selected) is int:  # noqa: E721
        bound = bind_goal_selection(question, selected)
    else:
        raise RedBoundedPlayerError("preflight authority returned an invalid choice")
    return RedBoundedPlayerPreflightChoice(
        authority_id=authority_id,
        selected_kind=bound.kind,
        selected_candidate_index=bound.selected_index,
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
    policy_input = {
        # A post-execution observation is evidence before it is a decision
        # menu.  A successful skill may settle at a controllable location where
        # every currently bound goal is unavailable.  Encoding that state must
        # not construct GoalManagerQuestion, whose stricter contract correctly
        # requires at least one selectable candidate when a policy is actually
        # asked to choose.
        "candidates": [item.policy_dict() for item in binding_set.opportunities],
        "schema": (
            "pokemon.core.goal-manager-input.v2"
            if any(item.resource_quote is not None for item in binding_set.opportunities)
            else "pokemon.core.goal-manager-input.v1"
        ),
        "situation": live.situation.policy_dict(),
    }
    return {
        "collection": collection.public_dict(),
        "goal_observation": live.public_dict(),
        "policy_input": policy_input,
        "schema": "pokemon.red.bounded-player-semantic-state.v1",
    }
