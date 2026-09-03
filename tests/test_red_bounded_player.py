from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    LivingCollectionCheckpoint,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.red_bounded_player import (
    RedBoundedPlayerError,
    RedBoundedPlayerObserver,
    red_bounded_player_semantic_document,
)
from pokemon_red_completion.red_goal_context import RedGoalContextRuntime
from pokemon_red_completion.red_goal_manager import RedGoalObservation


def _situation() -> GoalSituation:
    return GoalSituation(
        story_pressure=0.8,
        collection_pressure=0.7,
        team_pressure=0.3,
        evolution_pressure=0.4,
        safety_pressure=0.2,
        resource_pressure=0.3,
        storage_pressure=0.1,
        recovery_pressure=0.0,
        exploration_pressure=0.5,
    )


def _live(*, story_completed: int = 4) -> RedGoalObservation:
    live = Mock(spec=RedGoalObservation)
    live.situation = _situation()
    live.public_dict.return_value = {
        "schema": "pokemon.red.goal-observation.v1",
        "story": {"completed": story_completed, "target": 36},
        "collection": {"registered": 10, "living": 10},
        "private_path_fields": 0,
    }
    return live


def _binding_set() -> GoalBindingSet:
    available = {GoalKind.ADVANCE_STORY, GoalKind.ACQUIRE_SPECIES}

    def binding(kind: GoalKind) -> ExecutableGoalBinding:
        return ExecutableGoalBinding(
            binding_ref=f"private:red:{kind.value}",
            kind=kind,
            estimated_effort=0.2,
            estimated_risk=0.1,
            execute=lambda: GoalExecutionReport(0, 0, {}),
            verify=lambda _report: GoalVerification.succeeded(),
        )

    bindings = tuple(binding(kind) for kind in GoalKind if kind in available)
    by_kind = {item.kind: item for item in bindings}
    opportunities = tuple(
        by_kind[kind].opportunity
        if kind in by_kind
        else GoalOpportunity(
            binding_ref=f"private:red:unavailable:{kind.value}",
            kind=kind,
            availability=GoalAvailability.UNAVAILABLE,
            unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
        )
        for kind in GoalKind
    )
    return GoalBindingSet(opportunities, bindings)


def _collection() -> LivingCollectionCheckpoint:
    return LivingCollectionCheckpoint(
        registered_species=10,
        living_species=10,
        required_specimens_remaining=5,
        retained_captures=3,
        storage_headroom=8,
        undeclared_specimen_losses=0,
        completion_contract_sha256="1" * 64,
        specimen_ledger_sha256="2" * 64,
        required_specimens_sha256="3" * 64,
        specimen_counts=(("pokemon:red:living:starter", 10),),
    )


def test_semantic_document_contains_policy_and_ledger_but_no_private_binding() -> None:
    document = red_bounded_player_semantic_document(
        live=_live(),
        binding_set=_binding_set(),
        collection=_collection(),
    )
    encoded = json.dumps(document, sort_keys=True)

    assert document["schema"] == "pokemon.red.bounded-player-semantic-state.v1"
    assert "policy_input" in document
    assert "collection" in document
    assert "private:red" not in encoded
    assert "binding_ref" not in encoded


def test_observer_uses_existing_adapter_enumerator_and_collection_projector() -> None:
    live = _live()
    binding_set = _binding_set()
    collection = _collection()
    enumerator = Mock()
    enumerator.enumerate.return_value = binding_set
    runtime = Mock(spec=RedGoalContextRuntime)
    runtime.adapter.observe.return_value = live
    runtime.enumerator.return_value = enumerator
    actions = Mock(spec=CountingExecutor)
    projector = Mock(return_value=collection)

    observation = RedBoundedPlayerObserver(
        runtime=runtime,
        actions=actions,
        collection_projector=projector,
    )()

    assert observation.situation == live.situation
    assert observation.binding_set is binding_set
    assert observation.collection is collection
    assert len(observation.semantic_state_sha256) == 64
    runtime.adapter.observe.assert_called_once_with()
    runtime.enumerator.assert_called_once_with(actions)
    enumerator.enumerate.assert_called_once_with(live)
    projector.assert_called_once_with(live)


def test_semantic_digest_changes_with_public_red_progress() -> None:
    binding_set = _binding_set()
    collection = _collection()
    first = red_bounded_player_semantic_document(
        live=_live(story_completed=4),
        binding_set=binding_set,
        collection=collection,
    )
    second = red_bounded_player_semantic_document(
        live=_live(story_completed=5),
        binding_set=binding_set,
        collection=collection,
    )

    assert first != second


def test_observer_rejects_an_invalid_collection_projection() -> None:
    runtime = Mock(spec=RedGoalContextRuntime)
    runtime.adapter.observe.return_value = _live()
    runtime.enumerator.return_value.enumerate.return_value = _binding_set()

    observer = RedBoundedPlayerObserver(
        runtime=runtime,
        actions=Mock(spec=CountingExecutor),
        collection_projector=lambda _live: object(),  # type: ignore[arg-type,return-value]
    )
    with pytest.raises(RedBoundedPlayerError, match="invalid checkpoint"):
        observer()
