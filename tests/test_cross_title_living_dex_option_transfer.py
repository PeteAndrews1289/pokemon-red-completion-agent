from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_crystal_completion.goal_state import (
    CrystalCampaignSnapshot,
    CrystalCapability,
    CrystalCapabilityState,
)
from pokemon_crystal_completion.living_dex_option_adapter import (
    CrystalLivingDexOptionProspect,
    project_crystal_living_dex_option_menu,
)
from pokemon_red_completion.goal_manager_state import (
    CompletionProgress,
    GoalStateEvidence,
    party_readiness_satisfaction,
    party_safety_satisfaction,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexObservedArmExample,
    LivingDexObservedOutcome,
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionKind,
    LivingDexOptionMenu,
    LivingDexOutcomeStatus,
    living_dex_option_context_from_goal_situation,
    uniform_behavior_probabilities,
)
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
)
from pokemon_red_completion.red_living_dex_option_adapter import (
    RedBoundLivingDexOption,
    RedLivingDexNormalizationProvenance,
    RedLivingDexOptionProspect,
)
from pokemon_red_completion.red_living_dex_option_adapter import (
    _candidate as project_red_candidate,
)


def _party() -> PartyObservation:
    return PartyObservation(
        tuple(
            PartyMemberObservation(
                slot=slot,
                species_id=151 + slot,
                level=40,
                hp=80,
                max_hp=80,
                moves=(
                    MoveObservation(
                        move_id=20 + slot,
                        current_pp=15,
                        max_pp=20,
                    ),
                ),
            )
            for slot in range(1, 7)
        )
    )


def _capabilities(*, complete: bool) -> CrystalCapabilityState:
    available = {
        CrystalCapability.CAPTURE,
        CrystalCapability.PC_STORAGE,
    }
    unknown: set[CrystalCapability] = set()
    if complete:
        available.update(
            {
                CrystalCapability.BREEDING,
                CrystalCapability.ITEM_EVOLUTION,
                CrystalCapability.TIME_EVOLUTION,
                CrystalCapability.TIME_OF_DAY_WAIT,
                CrystalCapability.TRADE,
                CrystalCapability.TRADE_EVOLUTION,
            }
        )
    else:
        unknown.add(CrystalCapability.BREEDING)
    return CrystalCapabilityState(
        available=frozenset(available),
        unknown=frozenset(unknown),
    )


def _snapshot(*, complete_capabilities: bool = True) -> CrystalCampaignSnapshot:
    return CrystalCampaignSnapshot(
        story=CompletionProgress(8, 16),
        registered_collection=CompletionProgress(200, 251),
        living_collection=CompletionProgress(180, 251),
        level_collection=CompletionProgress(20, 251),
        evolution=CompletionProgress(50, 100),
        world_knowledge=CompletionProgress(125, 250),
        party=_party(),
        game_started=True,
        input_ready=True,
        capture_item_count=5,
        recovery_item_count=8,
        free_storage_slots=280,
        immediate_capture_slots=4,
        capabilities=_capabilities(complete=complete_capabilities),
    )


def _crystal_prospect(
    binding_ref: str,
    kind: LivingDexOptionKind,
    *,
    unlocks: int,
    actions: int,
    required_capabilities: frozenset[CrystalCapability],
    completion_units: int = 1,
    required_resource_units: int = 0,
    available_resource_units: int = 0,
    net_storage_slots: int = 0,
    irreversible_constraints_exposed: int = 0,
    prerequisite_confidence: float = 1.0,
) -> CrystalLivingDexOptionProspect:
    return CrystalLivingDexOptionProspect(
        binding_ref=binding_ref,
        kind=kind,
        completion_units=completion_units,
        maximum_completion_units=1,
        immediate_dependency_unlocks=unlocks,
        incomplete_dependency_frontier=10,
        travel_action_estimate=actions,
        execution_action_estimate=actions,
        maximum_controller_actions=10,
        required_resource_units=required_resource_units,
        available_resource_units=available_resource_units,
        net_storage_slots=net_storage_slots,
        party_risk=0.1,
        irreversible_constraints_exposed=irreversible_constraints_exposed,
        irreversible_constraint_count=5,
        prerequisite_confidence=prerequisite_confidence,
        required_capabilities=required_capabilities,
    )


def _prospects(prefix: str) -> tuple[CrystalLivingDexOptionProspect, ...]:
    return (
        _crystal_prospect(
            f"{prefix}.wild-species-map",
            LivingDexOptionKind.ACQUIRE,
            unlocks=2,
            actions=3,
            net_storage_slots=1,
            required_capabilities=frozenset({CrystalCapability.CAPTURE}),
        ),
        _crystal_prospect(
            f"{prefix}.box-layout",
            LivingDexOptionKind.MANAGE_STORAGE,
            completion_units=0,
            unlocks=4,
            actions=1,
            required_capabilities=frozenset({CrystalCapability.PC_STORAGE}),
        ),
        _crystal_prospect(
            f"{prefix}.egg-parent-pair",
            LivingDexOptionKind.ACQUIRE,
            unlocks=6,
            actions=7,
            net_storage_slots=2,
            prerequisite_confidence=0.8,
            required_capabilities=frozenset({CrystalCapability.BREEDING}),
        ),
        _crystal_prospect(
            f"{prefix}.clock-evolution",
            LivingDexOptionKind.EVOLVE,
            unlocks=4,
            actions=5,
            prerequisite_confidence=0.9,
            required_capabilities=frozenset(
                {
                    CrystalCapability.TIME_EVOLUTION,
                    CrystalCapability.TIME_OF_DAY_WAIT,
                }
            ),
        ),
        _crystal_prospect(
            f"{prefix}.held-item-evolution",
            LivingDexOptionKind.EVOLVE,
            unlocks=3,
            actions=2,
            required_resource_units=1,
            available_resource_units=2,
            required_capabilities=frozenset({CrystalCapability.ITEM_EVOLUTION}),
        ),
        _crystal_prospect(
            f"{prefix}.link-trade-evolution",
            LivingDexOptionKind.TRADE,
            unlocks=8,
            actions=4,
            irreversible_constraints_exposed=1,
            prerequisite_confidence=0.9,
            required_capabilities=frozenset(
                {
                    CrystalCapability.TRADE,
                    CrystalCapability.TRADE_EVOLUTION,
                }
            ),
        ),
    )


def _red_prospect(
    kind: LivingDexOptionKind,
    *,
    unlocks: int,
    actions: int,
    completion_units: int = 1,
    required_resource_units: int = 0,
    net_storage_slots: int = 0,
    irreversible_constraints_exposed: int = 0,
    prerequisite_confidence: float = 1.0,
) -> RedLivingDexOptionProspect:
    return RedLivingDexOptionProspect(
        kind=kind,
        completion_units=completion_units,
        maximum_completion_units=1,
        immediate_dependency_unlocks=unlocks,
        travel_action_estimate=actions,
        execution_action_estimate=actions,
        required_consumable_units=required_resource_units,
        net_storage_slots=net_storage_slots,
        party_risk=0.1,
        irreversible_constraints_exposed=irreversible_constraints_exposed,
        irreversible_constraint_count=5,
        prerequisite_confidence=prerequisite_confidence,
    )


def _red_candidates() -> tuple[LivingDexOptionCandidate, ...]:
    provenance = RedLivingDexNormalizationProvenance(
        living_target_count=502,
        retained_living_species_count=360,
        missing_living_species_count=142,
        incomplete_dependency_frontier=10,
        blocked_immediate_successors=5,
        access_blocked_targets=71,
        lower_bound_consumable_requirement=4,
        usable_consumable_units=2,
        usable_storage_capacity=560,
        usable_storage_headroom=280,
        party_readiness_requirement=5,
        current_party_readiness=4,
        unresolved_dependencies=5,
        maximum_controller_actions=10,
        maximum_emulator_frames=100,
    )
    before = SimpleNamespace(
        irreversible_constraints_remaining=5,
        usable_storage_headroom=280,
        resource_units_for=lambda ref: 2 if ref == "items" else 0,
    )
    prospects = (
        _red_prospect(
            LivingDexOptionKind.ACQUIRE,
            unlocks=2,
            actions=3,
            net_storage_slots=1,
        ),
        _red_prospect(
            LivingDexOptionKind.MANAGE_STORAGE,
            completion_units=0,
            unlocks=4,
            actions=1,
        ),
        _red_prospect(
            LivingDexOptionKind.ACQUIRE,
            unlocks=6,
            actions=7,
            net_storage_slots=2,
            prerequisite_confidence=0.8,
        ),
        _red_prospect(
            LivingDexOptionKind.EVOLVE,
            unlocks=4,
            actions=5,
            prerequisite_confidence=0.9,
        ),
        _red_prospect(
            LivingDexOptionKind.EVOLVE,
            unlocks=3,
            actions=2,
            required_resource_units=1,
        ),
        _red_prospect(
            LivingDexOptionKind.TRADE,
            unlocks=8,
            actions=4,
            irreversible_constraints_exposed=1,
            prerequisite_confidence=0.9,
        ),
    )
    options = tuple(
        RedBoundLivingDexOption(
            binding_ref=f"pokemon.red.other-private-identity.{index}",
            family_ref=f"private-family-{index}",
            location_ref=f"private-location-{index}",
            resource_pool_ref="items" if index == 4 else None,
            prospect=prospect,
            execute=lambda: None,
            verify_success=lambda _before, _after: True,
        )
        for index, prospect in enumerate(prospects)
    )
    return tuple(
        project_red_candidate(
            option,
            before=before,
            provenance=provenance,
        )
        for option in options
    )


def _outcome() -> LivingDexObservedOutcome:
    return LivingDexObservedOutcome(
        LivingDexOutcomeStatus.SETTLED,
        verified_success=True,
        completion_gain=0.5,
        dependency_unlock_gain=0.25,
        action_cost=0.2,
        frame_cost=0.3,
        resource_cost=0.1,
        party_cost=0.0,
        storage_cost=0.1,
        irreversible_loss=0.0,
    )


def test_typed_crystal_251_state_uses_shared_context_and_mechanic_masks() -> None:
    complete = project_crystal_living_dex_option_menu(
        _snapshot(),
        _prospects("pokemon.crystal.private"),
    )
    limited = project_crystal_living_dex_option_menu(
        _snapshot(complete_capabilities=False),
        _prospects("pokemon.crystal.private"),
    )

    assert complete.available_indices == (0, 1, 2, 3, 4, 5)
    assert limited.available_indices == (0, 1)
    assert limited.candidates[2].availability is LivingDexOptionAvailability.UNKNOWN
    assert all(
        candidate.availability is LivingDexOptionAvailability.UNAVAILABLE
        for candidate in limited.candidates[3:]
    )
    assert uniform_behavior_probabilities(limited) == pytest.approx(
        (0.5, 0.5, 0.0, 0.0, 0.0, 0.0)
    )
    assert complete.context == limited.context
    for index in (0, 1):
        assert (
            complete.candidates[index].policy_dict(complete.context)
            == limited.candidates[index].policy_dict(limited.context)
        )


def test_semantic_red_crystal_twins_share_vectors_targets_and_weights() -> None:
    crystal = project_crystal_living_dex_option_menu(
        _snapshot(),
        _prospects("pokemon.crystal.secret-species-map-route"),
    )
    party = _party()
    situation = GoalStateEvidence(
        story=CompletionProgress(8, 16),
        registered_collection=CompletionProgress(200, 251),
        living_collection=CompletionProgress(180, 251),
        level_collection=CompletionProgress(20, 251),
        team_readiness=party_readiness_satisfaction(
            party,
            required_size=6,
            required_level=50,
        ),
        evolution=CompletionProgress(50, 100),
        safety=party_safety_satisfaction(party),
        resources=0.5,
        storage=0.5,
        control=1.0,
        world_knowledge=CompletionProgress(125, 250),
    ).situation()
    red = LivingDexOptionMenu(
        living_dex_option_context_from_goal_situation(situation),
        _red_candidates(),
    )
    probabilities = uniform_behavior_probabilities(red)
    red_example = LivingDexObservedArmExample(
        "a" * 64,
        "train",
        red,
        2,
        probabilities,
        _outcome(),
    )
    crystal_example = LivingDexObservedArmExample(
        "b" * 64,
        "train",
        crystal,
        2,
        uniform_behavior_probabilities(crystal),
        _outcome(),
    )

    assert red.policy_dict() == crystal.policy_dict()
    assert red.policy_sha256 == crystal.policy_sha256
    assert red_example.selected_vector == crystal_example.selected_vector
    assert red_example.outcome.target_vector == crystal_example.outcome.target_vector
    assert red_example.importance_weight() == crystal_example.importance_weight()
    encoded = json.dumps(crystal_example.public_dict(), sort_keys=True)
    for private_identity in (
        "pokemon.crystal",
        "secret-species",
        "map-route",
        "egg-parent-pair",
        "held-item",
    ):
        assert private_identity not in encoded


def test_crystal_mechanic_facts_change_policy_rows_without_identity_features() -> None:
    baseline_prospects = _prospects("private.baseline")
    baseline = project_crystal_living_dex_option_menu(
        _snapshot(),
        baseline_prospects,
    )
    mutations = {
        1: replace(baseline_prospects[1], net_storage_slots=999),
        2: replace(baseline_prospects[2], prerequisite_confidence=0.2),
        3: replace(baseline_prospects[3], execution_action_estimate=9),
        4: replace(baseline_prospects[4], available_resource_units=0),
        5: replace(baseline_prospects[5], irreversible_constraints_exposed=2),
    }

    for index, mutation in mutations.items():
        prospects = tuple(
            mutation if candidate_index == index else prospect
            for candidate_index, prospect in enumerate(baseline_prospects)
        )
        changed = project_crystal_living_dex_option_menu(_snapshot(), prospects)
        assert changed.policy_sha256 != baseline.policy_sha256
        assert changed.candidate_vector(index) != baseline.candidate_vector(index)

    storage_blocked = project_crystal_living_dex_option_menu(
        _snapshot(),
        tuple(
            mutations[1] if index == 1 else prospect
            for index, prospect in enumerate(baseline_prospects)
        ),
    )
    missing_item = project_crystal_living_dex_option_menu(
        _snapshot(),
        tuple(
            mutations[4] if index == 4 else prospect
            for index, prospect in enumerate(baseline_prospects)
        ),
    )
    assert (
        storage_blocked.candidates[1].availability
        is LivingDexOptionAvailability.UNAVAILABLE
    )
    assert (
        missing_item.candidates[4].availability
        is LivingDexOptionAvailability.UNAVAILABLE
    )


def test_distinct_crystal_storage_states_do_not_alias_one_learner_state() -> None:
    roomy = project_crystal_living_dex_option_menu(
        _snapshot(),
        _prospects("private.roomy"),
    )
    blocked = project_crystal_living_dex_option_menu(
        replace(_snapshot(), immediate_capture_slots=0),
        _prospects("private.blocked"),
    )

    assert roomy.context.storage_pressure == pytest.approx(0.5)
    assert blocked.context.storage_pressure == pytest.approx(1.0)
    assert roomy.policy_sha256 != blocked.policy_sha256
    assert roomy.candidate_vector(0) != blocked.candidate_vector(0)
