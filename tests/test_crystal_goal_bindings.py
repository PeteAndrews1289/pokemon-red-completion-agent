from __future__ import annotations

import json

import pytest

from pokemon_crystal_completion.goal_bindings import (
    CapabilityBoundCrystalGoalProvider,
    CrystalGoalBindingError,
    CrystalGoalOpportunityEnumerator,
)
from pokemon_crystal_completion.goal_state import (
    CrystalCampaignSnapshot,
    CrystalCapability,
    CrystalCapabilityState,
    project_crystal_goal_state,
)
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalManagerQuestion,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.goal_manager_state import CompletionProgress
from pokemon_red_completion.party import PartyObservation


def _observation(capabilities: CrystalCapabilityState):
    return project_crystal_goal_state(
        CrystalCampaignSnapshot(
            story=CompletionProgress(0, 16),
            registered_collection=CompletionProgress(0, 250),
            living_collection=CompletionProgress(0, 250),
            level_collection=CompletionProgress(0, 250),
            evolution=CompletionProgress(0, 100),
            world_knowledge=CompletionProgress(0, 250),
            party=PartyObservation(),
            game_started=True,
            input_ready=True,
            capture_item_count=5,
            recovery_item_count=5,
            free_storage_slots=0,
            immediate_capture_slots=6,
            capabilities=capabilities,
        )
    )


def _binding(kind: GoalKind, suffix: str) -> ExecutableGoalBinding:
    return ExecutableGoalBinding(
        binding_ref=f"pokemon.crystal:private:{kind.value}:{suffix}",
        kind=kind,
        estimated_effort=0.2,
        estimated_risk=0.1,
        execute=lambda: GoalExecutionReport(0, 0, {}),
        verify=lambda _report: GoalVerification.succeeded(),
    )


def test_capability_masks_run_before_a_private_resolver() -> None:
    calls: list[GoalKind] = []

    def resolver(observation):  # type: ignore[no-untyped-def]
        del observation
        calls.append(GoalKind.ACQUIRE_SPECIES)
        return _binding(GoalKind.ACQUIRE_SPECIES, "capture")

    provider = CapabilityBoundCrystalGoalProvider(
        kind=GoalKind.ACQUIRE_SPECIES,
        required_capabilities=frozenset({CrystalCapability.CAPTURE}),
        resolver=resolver,
    )
    unknown = _observation(
        CrystalCapabilityState(
            available=frozenset(),
            unknown=frozenset({CrystalCapability.CAPTURE}),
        )
    )
    unavailable = _observation(CrystalCapabilityState(available=frozenset(), unknown=frozenset()))
    available = _observation(
        CrystalCapabilityState(
            available=frozenset({CrystalCapability.CAPTURE}),
            unknown=frozenset(),
        )
    )

    assert provider.offer(unknown).unavailable_reason is GoalUnavailableReason.WORLD_STATE_UNKNOWN
    assert (
        provider.offer(unavailable).unavailable_reason
        is GoalUnavailableReason.MISSING_CAPABILITY
    )
    assert calls == []
    assert provider.offer(available).binding is not None
    assert calls == [GoalKind.ACQUIRE_SPECIES]


def test_enumerator_exposes_all_kinds_but_policy_cannot_see_private_bindings() -> None:
    capabilities = CrystalCapabilityState(
        available=frozenset({CrystalCapability.BATTLE}),
        unknown=frozenset(),
    )
    providers = tuple(
        CapabilityBoundCrystalGoalProvider(
            kind=kind,
            required_capabilities=frozenset({CrystalCapability.BATTLE}),
            resolver=lambda _observation, selected=kind: _binding(selected, "bounded"),
        )
        for kind in (GoalKind.ADVANCE_STORY, GoalKind.RESTORE_TEAM)
    )
    observation = _observation(capabilities)
    binding_set = CrystalGoalOpportunityEnumerator(providers).enumerate(observation)
    question = GoalManagerQuestion(observation.situation, binding_set.opportunities)

    assert len(binding_set.opportunities) == len(GoalKind)
    assert {binding.kind for binding in binding_set.bindings} == {
        GoalKind.ADVANCE_STORY,
        GoalKind.RESTORE_TEAM,
    }
    assert sum(
        opportunity.availability is GoalAvailability.AVAILABLE
        for opportunity in binding_set.opportunities
    ) == 2
    encoded = json.dumps(
        {
            "candidates": [item.policy_dict() for item in question.opportunities],
            "situation": question.situation.policy_dict(),
        },
        sort_keys=True,
    )
    assert "pokemon.crystal" not in encoded
    assert "private" not in encoded
    assert "binding_ref" not in encoded


def test_enumerator_obeys_a_frozen_candidate_permutation() -> None:
    observation = _observation(CrystalCapabilityState(unknown=frozenset()))
    order = tuple(reversed(tuple(GoalKind)))
    binding_set = CrystalGoalOpportunityEnumerator(()).enumerate(
        observation,
        candidate_order=order,
    )

    assert tuple(item.kind for item in binding_set.opportunities) == order
    with pytest.raises(CrystalGoalBindingError, match="every goal kind"):
        CrystalGoalOpportunityEnumerator(()).enumerate(
            observation,
            candidate_order=order[:-1],
        )


def test_provider_explicitly_masks_a_context_even_when_capability_exists() -> None:
    observation = _observation(
        CrystalCapabilityState(
            available=frozenset({CrystalCapability.BATTLE}),
            unknown=frozenset(),
        )
    )
    provider = CapabilityBoundCrystalGoalProvider(
        kind=GoalKind.ADVANCE_STORY,
        required_capabilities=frozenset({CrystalCapability.BATTLE}),
        resolver=lambda _observation: GoalUnavailableReason.STORY_GATE_CLOSED,
    )
    offer = provider.offer(observation)

    assert offer.binding is None
    assert offer.unavailable_reason is GoalUnavailableReason.STORY_GATE_CLOSED


def test_enumerator_rejects_duplicate_kinds_or_wrong_resolver_kind() -> None:
    provider = CapabilityBoundCrystalGoalProvider(
        kind=GoalKind.ADVANCE_STORY,
        required_capabilities=frozenset(),
        resolver=lambda _observation: _binding(GoalKind.ADVANCE_STORY, "one"),
    )
    with pytest.raises(CrystalGoalBindingError, match="duplicate"):
        CrystalGoalOpportunityEnumerator((provider, provider))

    wrong = CapabilityBoundCrystalGoalProvider(
        kind=GoalKind.ADVANCE_STORY,
        required_capabilities=frozenset(),
        resolver=lambda _observation: _binding(GoalKind.EXPLORE, "wrong"),
    )
    with pytest.raises(CrystalGoalBindingError, match="different"):
        wrong.offer(_observation(CrystalCapabilityState(unknown=frozenset())))
