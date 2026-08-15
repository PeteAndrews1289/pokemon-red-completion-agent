from __future__ import annotations

import json
from dataclasses import replace

import pytest

from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
)
from pokemon_red_completion.party_development_rank import (
    PARTY_DEVELOPMENT_FEATURE_NAMES,
    CandidateCompletionSemantics,
    EvolutionRouteKind,
    EvolutionSemantics,
    PartyDevelopmentContext,
    PartyDevelopmentFeatureError,
    PartyDevelopmentGoal,
    VenueOperationalPrior,
    augment_training_candidate_set,
)
from pokemon_red_completion.team_training import BalancedTeamPolicy, GrindingArea
from pokemon_red_completion.training_candidate_rank import (
    TRAINING_CANDIDATE_FEATURE_NAMES,
    TrainingCandidateSet,
    TrainingChoiceKind,
    project_trainee_candidates,
    project_trainee_choice_set,
    project_venue_choice_set,
)


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


def _party() -> PartyObservation:
    return PartyObservation(
        members=(
            _member(1, 11, 30),
            _member(2, 22, 20),
            _member(3, 33, 20),
        )
    )


def _areas() -> tuple[GrindingArea, ...]:
    return (
        GrindingArea("private-route-a", 12, 18, measured_samples=100),
        GrindingArea("private-cave-b", 16, 22, measured_samples=100),
    )


def _context(
    goal: PartyDevelopmentGoal = PartyDevelopmentGoal.EVOLUTION,
) -> PartyDevelopmentContext:
    return PartyDevelopmentContext(
        goal=goal,
        party_size=3,
        below_floor_count=2,
        evolution_needed_count=2,
        registration_needed_count=1,
        living_needed_count=1,
        role_gap_count=1,
        registration_completion_ratio=0.5,
        living_completion_ratio=0.4,
        role_coverage_ratio=0.5,
        healthy_trainable_count=3,
        exhausted_count=0,
        fainted_count=0,
    )


def _semantics(count: int = 2) -> tuple[CandidateCompletionSemantics, ...]:
    values = (
        CandidateCompletionSemantics(
            evolution=EvolutionSemantics(
                required=True,
                stages_remaining=2,
                route_kind=EvolutionRouteKind.LEVEL,
                levels_to_next=4,
            ),
            registration_needed=True,
            living_target_needed=True,
            emergency_escort_required=True,
            projected_survival_margin=-0.25,
        ),
        CandidateCompletionSemantics(
            evolution=EvolutionSemantics(
                required=True,
                stages_remaining=1,
                route_kind=EvolutionRouteKind.ITEM,
                feasible_now=True,
            ),
            living_retention_risk=True,
            role_complete=True,
            projected_survival_margin=0.5,
        ),
        CandidateCompletionSemantics(
            evolution=EvolutionSemantics(False, 0, EvolutionRouteKind.NONE),
            role_needed=True,
            projected_survival_margin=0.75,
        ),
    )
    return values[:count]


def test_unlabelled_trainee_menu_survives_a_hidden_position_tie() -> None:
    policy = BalancedTeamPolicy(minimum_level=50, required_size=3)

    assert project_trainee_candidates(_party(), policy, _areas()) is None
    projected = project_trainee_choice_set(_party(), policy, _areas())

    assert projected is not None
    bindings, candidates = projected
    assert tuple(item.slot for item in bindings) == (1, 2, 3)
    assert len(candidates.candidates) == 3


def test_v2_preserves_the_frozen_v1_prefix_and_adds_completion_semantics() -> None:
    projected = project_trainee_choice_set(
        _party(),
        BalancedTeamPolicy(minimum_level=50, required_size=3),
        _areas(),
    )
    assert projected is not None
    base = projected[1]

    result = augment_training_candidate_set(base, _context(), _semantics(3))

    assert PARTY_DEVELOPMENT_FEATURE_NAMES[: len(TRAINING_CANDIDATE_FEATURE_NAMES)] == (
        TRAINING_CANDIDATE_FEATURE_NAMES
    )
    for old, new in zip(base.candidates, result.candidates, strict=True):
        assert new.features[: len(old.features)] == old.features
    first = dict(zip(PARTY_DEVELOPMENT_FEATURE_NAMES, result.candidates[0].features, strict=True))
    assert first["context.goal.evolution"] == 1.0
    assert first["candidate.evolution_required"] == 1.0
    assert first["candidate.registration_needed"] == 1.0
    assert first["candidate.projected_survival_margin"] == -0.25
    assert first["venue.prior_available"] == 0.0


def test_v2_projection_is_equivariant_when_candidates_and_bindings_are_permuted() -> None:
    projected = project_venue_choice_set(
        _party(),
        _party().members[1],
        BalancedTeamPolicy(minimum_level=50, required_size=3),
        _areas(),
        require_healer=False,
    )
    assert projected is not None
    base = projected[1]
    semantics = _semantics()
    priors = (
        VenueOperationalPrior(
            available=True,
            reliability=0.8,
            expected_yield=0.4,
            matchup_safety=0.7,
            travel_cost=0.2,
            recovery_cost=0.1,
            support_count=8,
            evidence_sha256="a" * 64,
            frozen_before_scenario=True,
        ),
        VenueOperationalPrior(
            available=True,
            reliability=0.6,
            expected_yield=0.9,
            matchup_safety=0.5,
            travel_cost=0.7,
            recovery_cost=0.3,
            support_count=4,
            evidence_sha256="b" * 64,
            frozen_before_scenario=True,
        ),
    )
    forward = augment_training_candidate_set(base, _context(), semantics, venue_priors=priors)
    reversed_base = TrainingCandidateSet(
        TrainingChoiceKind.VENUE,
        tuple(
            replace(candidate, candidate_index=index)
            for index, candidate in enumerate(reversed(base.candidates))
        ),
    )

    reversed_result = augment_training_candidate_set(
        reversed_base,
        _context(),
        tuple(reversed(semantics)),
        venue_priors=tuple(reversed(priors)),
    )

    assert tuple(item.features for item in reversed_result.candidates) == tuple(
        item.features for item in reversed(forward.candidates)
    )


def test_venue_prior_digest_is_required_but_never_enters_public_features() -> None:
    projected = project_venue_choice_set(
        _party(),
        _party().members[1],
        BalancedTeamPolicy(minimum_level=50, required_size=3),
        _areas(),
        require_healer=False,
    )
    assert projected is not None
    digest = "d" * 64
    prior = VenueOperationalPrior(
        available=True,
        reliability=0.75,
        expected_yield=0.5,
        matchup_safety=0.8,
        travel_cost=0.25,
        recovery_cost=0.125,
        support_count=5,
        evidence_sha256=digest,
        frozen_before_scenario=True,
    )
    result = augment_training_candidate_set(
        projected[1],
        _context(),
        _semantics(),
        venue_priors=(prior, prior),
    )

    encoded = json.dumps(result.public_dict(), sort_keys=True)
    assert digest not in encoded
    assert "private-route-a" not in encoded
    assert "private-cave-b" not in encoded


def test_trainee_menu_may_repeat_one_shared_venue_prior_but_not_mix_priors() -> None:
    projected = project_trainee_choice_set(
        _party(),
        BalancedTeamPolicy(minimum_level=50, required_size=3),
        (_areas()[0],),
    )
    assert projected is not None
    shared = VenueOperationalPrior(
        available=True,
        reliability=0.75,
        expected_yield=0.5,
        matchup_safety=0.8,
        travel_cost=0.25,
        recovery_cost=0.125,
        support_count=5,
        evidence_sha256="d" * 64,
        frozen_before_scenario=True,
    )
    result = augment_training_candidate_set(
        projected[1],
        _context(),
        _semantics(3),
        venue_priors=(shared, shared, shared),
    )

    assert all(
        dict(zip(PARTY_DEVELOPMENT_FEATURE_NAMES, item.features, strict=True))[
            "venue.prior_available"
        ]
        == 1.0
        for item in result.candidates
    )

    with pytest.raises(PartyDevelopmentFeatureError, match="one repeated shared"):
        augment_training_candidate_set(
            projected[1],
            _context(),
            _semantics(3),
            venue_priors=(
                shared,
                replace(shared, evidence_sha256="e" * 64),
                shared,
            ),
        )


def test_unfrozen_or_impossible_semantics_fail_closed() -> None:
    with pytest.raises(PartyDevelopmentFeatureError, match="frozen independent"):
        VenueOperationalPrior(
            available=True,
            reliability=0.5,
            support_count=1,
            evidence_sha256="e" * 64,
        )
    with pytest.raises(PartyDevelopmentFeatureError, match="both missing and complete"):
        CandidateCompletionSemantics(
            evolution=EvolutionSemantics(False, 0, EvolutionRouteKind.NONE),
            role_needed=True,
            role_complete=True,
        )
    with pytest.raises(PartyDevelopmentFeatureError, match="counts overlap"):
        PartyDevelopmentContext(
            goal=PartyDevelopmentGoal.BALANCE,
            party_size=2,
            below_floor_count=2,
            evolution_needed_count=0,
            registration_needed_count=0,
            living_needed_count=0,
            role_gap_count=0,
            registration_completion_ratio=0.0,
            living_completion_ratio=0.0,
            role_coverage_ratio=0.0,
            healthy_trainable_count=2,
            exhausted_count=1,
            fainted_count=0,
        )
