from __future__ import annotations

import json
from dataclasses import replace

import pytest

from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
)
from pokemon_red_completion.party_development_adapter import (
    PartyDevelopmentAdapterError,
    PartyDevelopmentCapabilityState,
    PartyDevelopmentExecutionCapability,
    PartyDevelopmentMemberProfile,
    PartyDevelopmentSemanticSnapshot,
)
from pokemon_red_completion.party_development_catalog import (
    PartyDevelopmentUnavailableReason,
)
from pokemon_red_completion.party_development_rank import (
    PARTY_DEVELOPMENT_FEATURE_NAMES,
    EvolutionRouteKind,
    EvolutionSemantics,
    PartyDevelopmentGoal,
    VenuePriorFeatureMode,
)
from pokemon_red_completion.party_development_venue_priors import (
    PartyDevelopmentVenuePriorError,
    PartyDevelopmentVenuePriorRegistry,
    VenuePriorEvidence,
    VenuePriorUnitRatio,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.team_training import BalancedTeamPolicy, GrindingArea
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind


def _member(slot: int, species: int, level: int) -> PartyMemberObservation:
    return PartyMemberObservation(
        slot=slot,
        species_id=species,
        level=level,
        hp=80,
        max_hp=100,
        moves=(MoveObservation(species + 100, 20, 25),),
        experience=1_000 + species,
    )


def _areas() -> tuple[GrindingArea, ...]:
    return (
        GrindingArea("private-route-a", 12, 18, measured_samples=50),
        GrindingArea("private-cave-b", 18, 24, measured_samples=50),
        GrindingArea("private-tower-c", 20, 26, measured_samples=50),
    )


def _evidence(
    venue: GrindingArea, *, evidence_id: str, root: str, digest_character: str
) -> VenuePriorEvidence:
    return VenuePriorEvidence(
        evidence_id=evidence_id,
        venue=venue,
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        measurement_contract_sha256="0" * 64,
        operational_contract_sha256="6" * 64,
        source_compatibility_sha256="5" * 64,
        support_root_lineage_ids=(root,),
        support_state_sha256=(digest_character * 64,),
        outcome_receipt_sha256=(("f" if digest_character != "f" else "e") * 64,),
        reliability=VenuePriorUnitRatio(9, 10),
        expected_yield=VenuePriorUnitRatio(3, 4),
        matchup_safety=VenuePriorUnitRatio(19, 20),
        travel_cost=VenuePriorUnitRatio(1, 4),
        recovery_cost=VenuePriorUnitRatio(1, 5),
    )


def _snapshot(
    goal: PartyDevelopmentGoal = PartyDevelopmentGoal.EVOLUTION,
    *,
    partition: ScenarioPartition = ScenarioPartition.TRAIN,
    root_lineage_id: str = "fresh-root",
    initial_state_sha256: str = "9" * 64,
    venue_prior_feature_mode: VenuePriorFeatureMode = VenuePriorFeatureMode.CALIBRATED,
) -> PartyDevelopmentSemanticSnapshot:
    party = PartyObservation(
        members=(
            _member(1, 11, 30),
            _member(2, 22, 24),
            _member(3, 33, 22),
        )
    )
    areas = _areas()
    ready = tuple(PartyDevelopmentExecutionCapability.ready() for _ in areas)
    profiles = (
        PartyDevelopmentMemberProfile(
            member=party.members[0],
            evolution=EvolutionSemantics(False, 0, EvolutionRouteKind.NONE),
            execution_capabilities_by_venue=ready,
            role_complete=True,
            projected_survival_by_venue=(0.9, 0.7, 0.5),
        ),
        PartyDevelopmentMemberProfile(
            member=party.members[1],
            evolution=EvolutionSemantics(
                True,
                2,
                EvolutionRouteKind.LEVEL,
                levels_to_next=4,
            ),
            execution_capabilities_by_venue=ready,
            registration_needed=True,
            living_target_needed=True,
            emergency_escort_required=True,
            projected_survival_by_venue=(0.8, 0.55, 0.25),
        ),
        PartyDevelopmentMemberProfile(
            member=party.members[2],
            evolution=EvolutionSemantics(
                True,
                1,
                EvolutionRouteKind.ITEM,
                feasible_now=True,
            ),
            execution_capabilities_by_venue=ready,
            role_needed=True,
            projected_survival_by_venue=(0.75, 0.45, 0.1),
        ),
    )
    registry = PartyDevelopmentVenuePriorRegistry.freeze(
        source_commit="1" * 40,
        source_bundle_sha256="2" * 64,
        entries=(
            _evidence(
                areas[0],
                evidence_id="prior-a",
                root="prior-root-a",
                digest_character="c",
            ),
            _evidence(
                areas[1],
                evidence_id="prior-b",
                root="prior-root-b",
                digest_character="d",
            ),
        ),
    )
    return PartyDevelopmentSemanticSnapshot(
        root_lineage_id=root_lineage_id,
        initial_state_sha256=initial_state_sha256,
        partition=partition,
        source_commit="3" * 40,
        source_bundle_sha256="4" * 64,
        party=party,
        policy=BalancedTeamPolicy(minimum_level=50, required_size=3),
        areas=areas,
        goal=goal,
        member_profiles=profiles,
        venue_prior_registry=registry,
        venue_operational_contract_sha256=("6" * 64,) * len(areas),
        registration_owned_count=80,
        registration_target_count=124,
        living_unique_count=70,
        living_target_count=108,
        role_coverage_count=2,
        role_target_count=3,
        venue_prior_feature_mode=venue_prior_feature_mode,
    )


def _feature(candidate: object, name: str) -> float:
    features = candidate.features  # type: ignore[attr-defined]
    return features[PARTY_DEVELOPMENT_FEATURE_NAMES.index(name)]


def test_trainee_adapter_binds_one_shared_prior_without_identity_leakage() -> None:
    snapshot = _snapshot()
    menu = snapshot.trainee_menu(snapshot.areas[0])

    assert menu is not None
    assert menu.candidate_set.kind is TrainingChoiceKind.TRAINEE
    assert len(menu.bindings) == 3
    assert menu.shared_venue_prior is not None
    assert menu.shared_venue_prior.available
    assert all(prior == menu.shared_venue_prior for prior in menu.venue_priors)
    assert all(menu.candidate_available)
    assert menu.candidate_unavailable_reasons == (None, None, None)
    assert _feature(menu.candidate_set.candidates[1], "venue.prior_available") == 1.0
    assert _feature(menu.candidate_set.candidates[1], "context.goal.evolution") == 1.0
    assert _feature(menu.candidate_set.candidates[1], "candidate.evolution_required") == 1.0
    assert (
        _feature(
            menu.candidate_set.candidates[1],
            "candidate.projected_survival_margin",
        )
        == 0.8
    )
    encoded = json.dumps(menu.candidate_set.public_dict(), sort_keys=True)
    assert "private-route-a" not in encoded
    assert "private-cave-b" not in encoded
    assert "private-tower-c" not in encoded
    assert '"species_id"' not in encoded

    binding = snapshot.freeze_binding(
        menu,
        scenario_id="party-train-001",
    )
    assert binding.shared_venue_prior_evidence_sha256 is not None
    assert binding.venue_prior_evidence_sha256 == (None, None, None)
    assert binding.venue_prior_registry_sha256 == snapshot.venue_prior_registry.registry_sha256


def test_venue_adapter_marks_missing_prior_unavailable_and_binds_exact_hashes() -> None:
    snapshot = _snapshot(
        partition=ScenarioPartition.DEVELOPMENT,
        root_lineage_id="fresh-venue-root",
        initial_state_sha256="8" * 64,
    )
    menu = snapshot.venue_menu(snapshot.party.members[1])

    assert menu is not None
    assert menu.candidate_set.kind is TrainingChoiceKind.VENUE
    assert len(menu.bindings) == 3
    assert menu.candidate_available == (True, True, False)
    assert menu.candidate_unavailable_reasons == (
        None,
        None,
        PartyDevelopmentUnavailableReason.INSUFFICIENT_VENUE_EVIDENCE,
    )
    assert tuple(prior.available for prior in menu.venue_priors) == (
        True,
        True,
        False,
    )
    assert _feature(menu.candidate_set.candidates[0], "venue.prior_available") == 1.0
    assert _feature(menu.candidate_set.candidates[2], "venue.prior_available") == 0.0

    binding = snapshot.freeze_binding(
        menu,
        scenario_id="party-venue-001",
    )
    assert binding.shared_venue_prior_evidence_sha256 is None
    assert binding.venue_prior_evidence_sha256[0] is not None
    assert binding.venue_prior_evidence_sha256[1] is not None
    assert binding.venue_prior_evidence_sha256[2] is None
    assert binding.candidate_available == (True, True, False)
    assert binding.candidate_unavailable_reasons == (
        None,
        None,
        PartyDevelopmentUnavailableReason.INSUFFICIENT_VENUE_EVIDENCE,
    )


def test_execution_capabilities_mask_before_selection_with_portable_reasons() -> None:
    snapshot = _snapshot()
    baseline_menu = snapshot.trainee_menu(snapshot.areas[0])
    transition_blocked = PartyDevelopmentExecutionCapability(
        PartyDevelopmentCapabilityState.BLOCKED,
        PartyDevelopmentCapabilityState.READY,
        PartyDevelopmentCapabilityState.READY,
    )
    battle_blocked = PartyDevelopmentExecutionCapability(
        PartyDevelopmentCapabilityState.READY,
        PartyDevelopmentCapabilityState.BLOCKED,
        PartyDevelopmentCapabilityState.READY,
    )
    changed_profiles = (
        replace(
            snapshot.member_profiles[0],
            execution_capabilities_by_venue=(
                transition_blocked,
                *snapshot.member_profiles[0].execution_capabilities_by_venue[1:],
            ),
        ),
        snapshot.member_profiles[1],
        snapshot.member_profiles[2],
    )
    changed = replace(snapshot, member_profiles=changed_profiles)

    menu = changed.trainee_menu(changed.areas[0])

    assert baseline_menu is not None
    assert menu is not None
    assert menu.candidate_set == baseline_menu.candidate_set
    assert menu.candidate_available == (False, True, True)
    assert menu.candidate_unavailable_reasons == (
        PartyDevelopmentUnavailableReason.TRANSITION_UNAVAILABLE,
        None,
        None,
    )
    assert (
        battle_blocked.unavailable_reason
        is PartyDevelopmentUnavailableReason.BATTLE_POLICY_INCOMPATIBLE
    )


def test_execution_capability_reports_known_blocker_before_unknown_state() -> None:
    capability = PartyDevelopmentExecutionCapability(
        PartyDevelopmentCapabilityState.UNKNOWN,
        PartyDevelopmentCapabilityState.READY,
        PartyDevelopmentCapabilityState.BLOCKED,
    )
    unknown_only = PartyDevelopmentExecutionCapability(
        PartyDevelopmentCapabilityState.READY,
        PartyDevelopmentCapabilityState.UNKNOWN,
        PartyDevelopmentCapabilityState.READY,
    )

    assert not capability.available
    assert (
        capability.unavailable_reason
        is PartyDevelopmentUnavailableReason.INSUFFICIENT_RECOVERY_CAPACITY
    )
    assert unknown_only.unavailable_reason is PartyDevelopmentUnavailableReason.WORLD_STATE_UNKNOWN


def test_venue_context_selects_unique_weakest_goal_relevant_trainee() -> None:
    snapshot = _snapshot()

    selected = snapshot.unique_weakest_goal_relevant_venue_trainee()

    assert selected == snapshot.party.members[2]


def test_venue_context_refuses_a_hidden_identity_tie_break() -> None:
    snapshot = _snapshot()
    tied_member = replace(snapshot.party.members[1], level=22)
    tied_party = replace(
        snapshot.party,
        members=(snapshot.party.members[0], tied_member, snapshot.party.members[2]),
    )
    tied_profiles = (
        snapshot.member_profiles[0],
        replace(snapshot.member_profiles[1], member=tied_member),
        snapshot.member_profiles[2],
    )
    tied = replace(snapshot, party=tied_party, member_profiles=tied_profiles)

    with pytest.raises(
        PartyDevelopmentAdapterError,
        match="not semantically unique",
    ):
        tied.unique_weakest_goal_relevant_venue_trainee()


def test_shared_venue_without_prior_cannot_become_a_trainee_outcome_menu() -> None:
    snapshot = _snapshot()

    with pytest.raises(PartyDevelopmentAdapterError, match="lacks frozen"):
        snapshot.trainee_menu(snapshot.areas[2])


def test_uncalibrated_protocol_masks_prior_features_without_gating_execution() -> None:
    snapshot = _snapshot(
        venue_prior_feature_mode=VenuePriorFeatureMode.MASKED_UNCALIBRATED,
    )

    trainee_menu = snapshot.trainee_menu(snapshot.areas[0])
    venue_menu = snapshot.venue_menu(snapshot.party.members[1])

    assert trainee_menu is not None
    assert venue_menu is not None
    assert trainee_menu.shared_venue_prior is None
    assert all(not prior.available for prior in trainee_menu.venue_priors)
    assert all(not prior.available for prior in venue_menu.venue_priors)
    assert all(trainee_menu.candidate_available)
    assert all(venue_menu.candidate_available)
    assert all(
        _feature(candidate, "venue.prior_available") == 0.0
        for candidate in (
            *trainee_menu.candidate_set.candidates,
            *venue_menu.candidate_set.candidates,
        )
    )

    trainee_binding = snapshot.freeze_binding(
        trainee_menu,
        scenario_id="masked-trainee-001",
    )
    venue_binding = snapshot.freeze_binding(
        venue_menu,
        scenario_id="masked-venue-001",
    )
    assert trainee_binding.venue_prior_feature_mode is VenuePriorFeatureMode.MASKED_UNCALIBRATED
    assert venue_binding.venue_prior_feature_mode is VenuePriorFeatureMode.MASKED_UNCALIBRATED
    assert trainee_binding.shared_venue_prior_evidence_sha256 is None
    assert all(value is None for value in venue_binding.venue_prior_evidence_sha256)
    assert (
        trainee_binding.public_dict()["venue_prior_feature_mode"]
        == "masked_uncalibrated"
    )


def test_adapter_rejects_goal_permutations_that_cannot_reduce_pressure() -> None:
    snapshot = _snapshot(PartyDevelopmentGoal.ROLE_COVERAGE)

    with pytest.raises(PartyDevelopmentAdapterError, match="cannot reduce"):
        snapshot.venue_menu(snapshot.party.members[1])


def test_profiles_must_match_the_exact_observed_party_and_venue_width() -> None:
    snapshot = _snapshot()
    changed_profile = replace(
        snapshot.member_profiles[0],
        member=replace(snapshot.party.members[0], hp=79),
    )

    with pytest.raises(PartyDevelopmentAdapterError, match="align exactly"):
        replace(
            snapshot,
            member_profiles=(changed_profile, *snapshot.member_profiles[1:]),
        )


def test_prior_support_cannot_be_reused_as_a_candidate_scenario() -> None:
    snapshot = _snapshot(
        root_lineage_id="prior-root-a",
        initial_state_sha256="7" * 64,
    )
    menu = snapshot.trainee_menu(snapshot.areas[0])
    assert menu is not None

    with pytest.raises(PartyDevelopmentVenuePriorError, match="root already supports"):
        snapshot.freeze_binding(
            menu,
            scenario_id="party-train-overlap",
        )


def test_menu_cannot_be_rebound_to_a_different_semantic_snapshot() -> None:
    first = _snapshot()
    menu = first.trainee_menu(first.areas[0])
    assert menu is not None
    second = _snapshot(
        root_lineage_id="other-root",
        initial_state_sha256="8" * 64,
    )

    with pytest.raises(PartyDevelopmentAdapterError, match="different semantic"):
        second.freeze_binding(menu, scenario_id="wrong-snapshot")
