from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
)
from pokemon_red_completion.party_development_catalog import (
    PartyDevelopmentProspectiveBinding,
)
from pokemon_red_completion.party_development_outcomes import (
    PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE,
    PartyCompletionSnapshot,
    PartyDevelopmentOutcomeTrialV2,
    adapt_party_development_outcomes_v2,
)
from pokemon_red_completion.party_development_rank import (
    CandidateCompletionSemantics,
    EvolutionRouteKind,
    EvolutionSemantics,
    PartyDevelopmentContext,
    PartyDevelopmentGoal,
    VenueOperationalPrior,
    augment_training_candidate_set,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.scenario_outcomes import ScenarioOutcomeError
from pokemon_red_completion.team_training import (
    BalancedTeamPolicy,
    GrindingArea,
    TeamTrainingProgress,
)
from pokemon_red_completion.training_candidate_rank import project_venue_choice_set


def _member(slot: int, species: int, level: int, experience: int) -> PartyMemberObservation:
    return PartyMemberObservation(
        slot=slot,
        species_id=species,
        level=level,
        hp=100,
        max_hp=100,
        moves=(MoveObservation(species + 50, 15, 20),),
        experience=experience,
    )


def _before_party() -> PartyObservation:
    return PartyObservation(
        members=(
            _member(1, 10, 25, 1_000),
            _member(2, 20, 35, 2_000),
        )
    )


def _after_party(gain: int) -> PartyObservation:
    before = _before_party()
    first, second = before.members
    assert first.experience is not None
    return PartyObservation(members=(replace(first, experience=first.experience + gain), second))


def _candidate_set(goal: PartyDevelopmentGoal = PartyDevelopmentGoal.EVOLUTION):
    party = _before_party()
    areas = (
        GrindingArea("private-low-band", 12, 18, measured_samples=100),
        GrindingArea("private-high-band", 18, 24, measured_samples=100),
    )
    projected = project_venue_choice_set(
        party,
        party.members[0],
        BalancedTeamPolicy(minimum_level=50, required_size=2),
        areas,
    )
    assert projected is not None
    semantics = CandidateCompletionSemantics(
        evolution=EvolutionSemantics(
            required=True,
            stages_remaining=1,
            route_kind=EvolutionRouteKind.LEVEL,
            levels_to_next=1,
        ),
        registration_needed=True,
        living_target_needed=True,
        role_needed=True,
        projected_survival_margin=0.5,
    )
    context = PartyDevelopmentContext(
        goal=goal,
        party_size=2,
        below_floor_count=1,
        evolution_needed_count=1,
        registration_needed_count=1,
        living_needed_count=1,
        role_gap_count=1,
        registration_completion_ratio=0.5,
        living_completion_ratio=0.45,
        role_coverage_ratio=0.5,
        healthy_trainable_count=2,
        exhausted_count=0,
        fainted_count=0,
    )
    return augment_training_candidate_set(
        projected[1], context, (semantics, semantics), venue_priors=_venue_priors()
    )


def _venue_priors() -> tuple[VenueOperationalPrior, ...]:
    return tuple(
        VenueOperationalPrior(
            available=True,
            reliability=0.9 - index * 0.1,
            expected_yield=0.5 + index * 0.2,
            matchup_safety=0.8,
            travel_cost=0.2 + index * 0.1,
            recovery_cost=0.2,
            support_count=4,
            evidence_sha256=str(index + 1) * 64,
            frozen_before_scenario=True,
        )
        for index in range(2)
    )


def _binding(
    candidate_set,
    *,
    scenario_id: str,
    root_lineage_id: str,
    initial_state_sha256: str,
) -> PartyDevelopmentProspectiveBinding:
    return PartyDevelopmentProspectiveBinding.build(
        scenario_id=scenario_id,
        root_lineage_id=root_lineage_id,
        initial_state_sha256=initial_state_sha256,
        partition=ScenarioPartition.TRAIN,
        source_commit="1" * 40,
        source_bundle_sha256="2" * 64,
        semantic_snapshot_sha256="3" * 64,
        candidate_set=candidate_set,
        venue_priors=_venue_priors(),
        venue_prior_registry_sha256="4" * 64,
        outcome_objective_sha256=(PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE.objective_sha256),
    )


def _completion(
    *,
    registered: int = 10,
    living: int = 9,
    roles: int = 3,
    evolution_steps: int = 1,
    level_deficit: int = 25,
) -> PartyCompletionSnapshot:
    return PartyCompletionSnapshot(
        registered_target_count=registered,
        registration_target_total=20,
        living_target_count=living,
        living_target_total=20,
        role_coverage_count=roles,
        role_target_total=6,
        evolution_steps_remaining=evolution_steps,
        level_floor_deficit=level_deficit,
    )


def _trial(
    candidate_set,
    index: int,
    *,
    gain: int,
    frames: int,
    completion_after: PartyCompletionSnapshot,
    evolution_completed: bool = False,
    censored: bool = False,
) -> PartyDevelopmentOutcomeTrialV2:
    return PartyDevelopmentOutcomeTrialV2(
        candidate=candidate_set.candidates[index],
        target_slot=1,
        before_party=_before_party(),
        after_party=_after_party(gain),
        progress_before=TeamTrainingProgress(),
        progress_after=TeamTrainingProgress(battles_completed=2),
        completion_before=_completion(),
        completion_after=completion_after,
        frames_executed=frames,
        evolution_completed=evolution_completed,
        censored=censored,
    )


def test_completion_objective_prefers_evolution_progress_over_raw_xp_rate() -> None:
    candidates = _candidate_set()
    binding = _binding(
        candidates,
        scenario_id="completion-evolution",
        root_lineage_id="completion-root-a",
        initial_state_sha256="a" * 64,
    )
    result = adapt_party_development_outcomes_v2(
        candidates,
        (
            _trial(
                candidates,
                0,
                gain=800,
                frames=1_000,
                completion_after=_completion(level_deficit=24),
            ),
            _trial(
                candidates,
                1,
                gain=100,
                frames=2_000,
                completion_after=_completion(
                    registered=11,
                    living=10,
                    roles=4,
                    evolution_steps=0,
                    level_deficit=24,
                ),
                evolution_completed=True,
            ),
        ),
        scenario_id="completion-evolution",
        root_lineage_id="completion-root-a",
        initial_state_sha256="a" * 64,
        partition=ScenarioPartition.TRAIN,
        prospective_binding=binding,
    )

    assert result.best_candidate_indices == (1,)
    assert result.target_distribution.tolist() == [0.0, 1.0]
    assert result.learner_update_eligible
    assert result.public_dict()["teacher_choice_targets"] == 0
    assert result.public_dict()["schema"] == "pokemon.core.scenario-outcome-example.v2"
    assert result.prospective_binding_sha256 == binding.binding_sha256


def test_living_collection_regression_loses_before_efficiency_is_considered() -> None:
    candidates = _candidate_set()
    binding = _binding(
        candidates,
        scenario_id="living-retention",
        root_lineage_id="completion-root-b",
        initial_state_sha256="b" * 64,
    )
    safe = _trial(
        candidates,
        0,
        gain=50,
        frames=2_000,
        completion_after=_completion(level_deficit=24),
    )
    destructive = _trial(
        candidates,
        1,
        gain=2_000,
        frames=500,
        completion_after=_completion(living=8, evolution_steps=0, level_deficit=20),
        evolution_completed=True,
    )

    result = adapt_party_development_outcomes_v2(
        candidates,
        (safe, destructive),
        scenario_id="living-retention",
        root_lineage_id="completion-root-b",
        initial_state_sha256="b" * 64,
        partition=ScenarioPartition.TRAIN,
        prospective_binding=binding,
    )

    assert result.best_candidate_indices == (0,)
    assert result.outcomes[1] is not None
    assert result.outcomes[1].criterion_values[1] == 0.0


def test_censored_v2_trial_never_becomes_a_training_target() -> None:
    candidates = _candidate_set()
    binding = _binding(
        candidates,
        scenario_id="censored-completion",
        root_lineage_id="completion-root-c",
        initial_state_sha256="c" * 64,
    )
    result = adapt_party_development_outcomes_v2(
        candidates,
        (
            _trial(
                candidates,
                0,
                gain=100,
                frames=1_000,
                completion_after=_completion(level_deficit=24),
            ),
            _trial(
                candidates,
                1,
                gain=0,
                frames=500,
                completion_after=_completion(),
                censored=True,
            ),
        ),
        scenario_id="censored-completion",
        root_lineage_id="completion-root-c",
        initial_state_sha256="c" * 64,
        partition=ScenarioPartition.TRAIN,
        prospective_binding=binding,
    )

    assert not result.fully_measured
    assert not result.learner_update_eligible
    with pytest.raises(ScenarioOutcomeError, match="no preference distribution"):
        _ = result.target_distribution


def test_completion_targets_cannot_change_inside_a_trial() -> None:
    before = _completion()
    after = replace(_completion(), living_target_total=19)
    with pytest.raises(ScenarioOutcomeError, match="target changed"):
        PartyDevelopmentOutcomeTrialV2(
            candidate=_candidate_set().candidates[0],
            target_slot=1,
            before_party=_before_party(),
            after_party=_after_party(10),
            progress_before=TeamTrainingProgress(),
            progress_after=TeamTrainingProgress(battles_completed=1),
            completion_before=before,
            completion_after=after,
            frames_executed=1_000,
        )


def test_v2_outcome_requires_a_typed_prospective_binding() -> None:
    candidates = _candidate_set()
    with pytest.raises(TypeError, match="prospective_binding"):
        adapt_party_development_outcomes_v2(
            candidates,
            (),
            scenario_id="invalid-binding",
            root_lineage_id="invalid-binding-root",
            initial_state_sha256="a" * 64,
            partition=ScenarioPartition.TRAIN,
            prospective_binding="not-a-binding",  # type: ignore[arg-type]
        )
