from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import Mock

import pytest

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import (
    BoundGoalSelection,
    GoalAvailability,
    GoalKind,
    GoalManagerError,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
    bind_goal_selection,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    CompositionBudgetCheckpoint,
    GoalManagerCompositionObservation,
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
    preflight_red_bounded_player,
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


def _unavailable_binding_set() -> GoalBindingSet:
    return GoalBindingSet(
        tuple(
            GoalOpportunity(
                binding_ref=f"private:red:unavailable:{kind.value}",
                kind=kind,
                availability=GoalAvailability.UNAVAILABLE,
                unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
            )
            for kind in GoalKind
        ),
        (),
    )


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


@dataclass
class _Meter:
    state: dict[str, int]

    def checkpoint(self) -> CompositionBudgetCheckpoint:
        return CompositionBudgetCheckpoint(
            controller_actions=self.state["actions"],
            emulator_frames=self.state["frames"],
        )


@dataclass
class _SelectKind:
    kind: GoalKind
    state: dict[str, int] | None = None

    def select(self, question):
        if self.state is not None:
            self.state["actions"] += 1
        index = next(
            index
            for index in question.available_indices
            if question.opportunities[index].kind is self.kind
        )
        return bind_goal_selection(question, index)


def _composition_observation(
    *, available: set[GoalKind] | None = None
) -> GoalManagerCompositionObservation:
    binding_set = _binding_set()
    if available is not None:
        bindings = tuple(
            binding for binding in binding_set.bindings if binding.kind in available
        )
        by_kind = {binding.kind: binding for binding in bindings}
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
        binding_set = GoalBindingSet(opportunities, bindings)
    return GoalManagerCompositionObservation(
        semantic_state_sha256="4" * 64,
        situation=_situation(),
        binding_set=binding_set,
        collection=_collection(),
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


def test_observer_encodes_a_post_skill_state_without_available_goals() -> None:
    live = _live(story_completed=4)
    binding_set = _unavailable_binding_set()
    collection = _collection()
    enumerator = Mock()
    enumerator.enumerate.return_value = binding_set
    runtime = Mock(spec=RedGoalContextRuntime)
    runtime.adapter.observe.return_value = live
    runtime.enumerator.return_value = enumerator

    observation = RedBoundedPlayerObserver(
        runtime=runtime,
        actions=Mock(spec=CountingExecutor),
        collection_projector=Mock(return_value=collection),
    )()

    assert observation.binding_set is binding_set
    assert len(observation.semantic_state_sha256) == 64
    document = red_bounded_player_semantic_document(
        live=live,
        binding_set=binding_set,
        collection=collection,
    )
    policy_input = document["policy_input"]
    assert isinstance(policy_input, dict)
    candidates = policy_input["candidates"]
    assert isinstance(candidates, list)
    assert all(
        candidate["availability"] == "unavailable"
        for candidate in candidates
    )


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


def test_preflight_compares_two_authorities_without_emulator_work_or_private_data() -> None:
    state = {"actions": 0, "frames": 0}
    observation = _composition_observation()

    result = preflight_red_bounded_player(
        observe=lambda: observation,
        budget_meter=_Meter(state),
        assignment_id="red-player-preflight-001",
        authorities=(
            ("learned-goal-manager", _SelectKind(GoalKind.ACQUIRE_SPECIES)),
            ("completion-first-teacher", _SelectKind(GoalKind.ADVANCE_STORY)),
        ),
    )
    public = result.public_dict()
    encoded = json.dumps(public, sort_keys=True)

    assert result.authority_disagreement is True
    assert public["actions_executed"] == 0
    assert public["emulator_frames"] == 0
    assert public["episode_created"] is False
    assert public["available_goal_count"] == 2
    assert "private:red" not in encoded
    assert "binding_ref" not in encoded
    assert "/" not in result.assignment_id


@pytest.mark.parametrize("available", [set(), {GoalKind.ADVANCE_STORY}])
def test_continuation_preflight_never_queries_authority_for_forced_bridge(available):
    state = {"actions": 0, "frames": 0}
    authority = Mock()
    authority.select.side_effect = AssertionError("singleton is not learned")
    def check():
        return preflight_red_bounded_player(
            observe=lambda: _composition_observation(available=available),
            budget_meter=_Meter(state), assignment_id="continued-player",
            authorities=(("a", authority), ("b", authority)), allow_forced_bridge=True,
        )
    if available:
        result = check()
        assert result.choices == () and len(result.available_goal_kinds) == 1
    else:
        with pytest.raises(GoalManagerError, match="at least one available option"):
            check()
    authority.select.assert_not_called()
    assert state == {"actions": 0, "frames": 0}


def test_preflight_rejects_snapshot_without_a_genuine_choice() -> None:
    state = {"actions": 0, "frames": 0}
    with pytest.raises(RedBoundedPlayerError, match="genuine semantic choice"):
        preflight_red_bounded_player(
            observe=lambda: _composition_observation(
                available={GoalKind.ADVANCE_STORY}
            ),
            budget_meter=_Meter(state),
            assignment_id="red-player-preflight-001",
            authorities=(
                ("first", _SelectKind(GoalKind.ADVANCE_STORY)),
                ("second", _SelectKind(GoalKind.ADVANCE_STORY)),
            ),
        )


@pytest.mark.parametrize("mutation_site", ["observer", "authority"])
def test_preflight_rejects_any_emulator_work(mutation_site: str) -> None:
    state = {"actions": 0, "frames": 0}
    observation = _composition_observation()

    def observe() -> GoalManagerCompositionObservation:
        if mutation_site == "observer":
            state["frames"] += 1
        return observation

    first = _SelectKind(
        GoalKind.ACQUIRE_SPECIES,
        state=state if mutation_site == "authority" else None,
    )
    with pytest.raises(RedBoundedPlayerError, match="attempted emulator work"):
        preflight_red_bounded_player(
            observe=observe,
            budget_meter=_Meter(state),
            assignment_id="red-player-preflight-001",
            authorities=(
                ("first", first),
                ("second", _SelectKind(GoalKind.ADVANCE_STORY)),
            ),
        )


@pytest.mark.parametrize(
    ("assignment_id", "authority_id"),
    [
        ("private/path", "first"),
        ("red-player-preflight-001", "private/path"),
    ],
)
def test_preflight_rejects_path_bearing_public_ids(
    assignment_id: str, authority_id: str
) -> None:
    state = {"actions": 0, "frames": 0}
    with pytest.raises(RedBoundedPlayerError, match="path-free"):
        preflight_red_bounded_player(
            observe=_composition_observation,
            budget_meter=_Meter(state),
            assignment_id=assignment_id,
            authorities=(
                (authority_id, _SelectKind(GoalKind.ACQUIRE_SPECIES)),
                ("second", _SelectKind(GoalKind.ADVANCE_STORY)),
            ),
        )


def test_preflight_rejects_choice_bound_to_another_question() -> None:
    state = {"actions": 0, "frames": 0}

    class ForeignAuthority:
        def select(self, question) -> BoundGoalSelection:
            index = question.available_indices[0]
            return BoundGoalSelection(
                selected_index=index,
                binding_ref="private:red:foreign",
                kind=question.opportunities[index].kind,
            )

    with pytest.raises(RedBoundedPlayerError, match="another question"):
        preflight_red_bounded_player(
            observe=_composition_observation,
            budget_meter=_Meter(state),
            assignment_id="red-player-preflight-001",
            authorities=(
                ("foreign", ForeignAuthority()),
                ("second", _SelectKind(GoalKind.ADVANCE_STORY)),
            ),
        )
