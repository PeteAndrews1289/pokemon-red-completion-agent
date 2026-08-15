from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.battle_outcome_learning import (
    BattleOutcomeExample,
    BattleTurnOutcome,
)
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_ID,
    BattleFeatureBatch,
)
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
)
from pokemon_red_completion.scenario_lab import ScenarioFamily, ScenarioPartition
from pokemon_red_completion.scenario_outcome_adapters import (
    NavigationOutcomeTrial,
    PartyDevelopmentOutcomeTrial,
    adapt_battle_outcome_example,
    adapt_navigation_outcomes,
    adapt_party_development_outcomes,
)
from pokemon_red_completion.scenario_outcomes import (
    CandidateOutcome,
    OutcomeCandidate,
    OutcomeCriterion,
    OutcomeDirection,
    OutcomeEvidenceStatus,
    OutcomeObjective,
    ScenarioOutcomeCatalog,
    ScenarioOutcomeError,
    ScenarioOutcomeExample,
)
from pokemon_red_completion.strategic_navigation import (
    DestinationAvailability,
    NavigationDestinationCandidate,
    NavigationFailureReason,
    NavigationOutcomeStatus,
    StrategicNavigationDecision,
    StrategicNavigationOutcome,
    StrategicNavigationTag,
)
from pokemon_red_completion.strategic_navigation_dataset import (
    StrategicNavigationInferenceInput,
)
from pokemon_red_completion.team_training import (
    BalancedTeamPolicy,
    GrindingArea,
    TeamTrainingProgress,
)
from pokemon_red_completion.training_candidate_rank import (
    TrainingCandidateSet,
    project_trainee_candidates,
)


def _digest(character: str) -> str:
    return character * 64


def _battle_example() -> BattleOutcomeExample:
    vectors = tuple(tuple([value] + [0.0] * (len(FEATURE_NAMES) - 1)) for value in (-0.8, 0.8, 0.0))
    features = BattleFeatureBatch(
        feature_names=FEATURE_NAMES,
        candidate_vectors=vectors,
        legal_mask=(True, True, False),
        current_pp=(10.0, 10.0, 0.0),
        slot_indices=(0, 1, 2),
        schema_id=FEATURE_SCHEMA_ID,
    )

    def outcome(damage: float) -> BattleTurnOutcome:
        return BattleTurnOutcome(
            move_executed=True,
            opponent_damage_fraction=damage,
            player_damage_fraction=0.0,
            opponent_fainted=False,
            player_fainted=False,
            battle_exited=False,
            actions_executed=2,
            frames_executed=64,
        )

    return BattleOutcomeExample(
        root_lineage_id="battle-root",
        initial_state_sha256=_digest("a"),
        partition=ScenarioPartition.TRAIN,
        features=features,
        outcomes=(outcome(0.2), outcome(0.8), None),
    )


def _navigation_candidates() -> tuple[NavigationDestinationCandidate, ...]:
    return (
        NavigationDestinationCandidate(
            destination_ref="private-destination-a",
            semantic_tags=(StrategicNavigationTag.STORY_PROGRESS,),
            availability=DestinationAvailability.AVAILABLE,
            route_cost=12,
            route_steps=10,
            map_transitions=1,
            field_actions=0,
            mode_changes=0,
        ),
        NavigationDestinationCandidate(
            destination_ref="private-destination-b",
            semantic_tags=(StrategicNavigationTag.STORY_PROGRESS,),
            availability=DestinationAvailability.AVAILABLE,
            route_cost=8,
            route_steps=7,
            map_transitions=1,
            field_actions=0,
            mode_changes=0,
        ),
    )


def _navigation_decision(selected_index: int) -> StrategicNavigationDecision:
    candidates = _navigation_candidates()
    return StrategicNavigationDecision(
        episode_id="navigation-counterfactual-episode",
        decision_index=0,
        root_lineage_id="navigation-root",
        partition="train",
        actor="outcome-probe",
        policy_id="shared-navigation-probe-v1",
        semantic_need_tags=(StrategicNavigationTag.ADVANCE_STORY,),
        origin_semantic_tags=(StrategicNavigationTag.OVERWORLD,),
        origin_region_ref="private-origin",
        candidates=candidates,
        selected_destination_ref=candidates[selected_index].destination_ref,
    )


def _navigation_inference() -> StrategicNavigationInferenceInput:
    return StrategicNavigationInferenceInput(_navigation_decision(0).policy_input())


def _navigation_outcome(
    decision: StrategicNavigationDecision,
    *,
    succeeded: bool,
    movement_requests: int,
    acknowledged_steps: int,
) -> StrategicNavigationOutcome:
    return StrategicNavigationOutcome(
        decision_id=decision.decision_id,
        selected_destination_ref=decision.selected_destination_ref,
        status=(NavigationOutcomeStatus.SUCCEEDED if succeeded else NavigationOutcomeStatus.FAILED),
        terminal_reached=succeeded,
        movement_requests=movement_requests,
        acknowledged_steps=acknowledged_steps,
        wait_actions=0,
        failure_reason=(None if succeeded else NavigationFailureReason.WORLD_STATE_DIVERGED),
    )


def _member(slot: int, species: int, level: int, experience: int) -> PartyMemberObservation:
    return PartyMemberObservation(
        slot=slot,
        species_id=species,
        level=level,
        hp=100,
        max_hp=100,
        moves=(MoveObservation(species + 10, 20, 25),),
        experience=experience,
    )


def _party_candidates() -> tuple[PartyObservation, TrainingCandidateSet]:
    party = PartyObservation(
        members=(
            _member(1, 9, 30, 1_000),
            _member(2, 3, 32, 1_200),
        )
    )
    projected = project_trainee_candidates(
        party,
        BalancedTeamPolicy(minimum_level=50, required_size=2),
        (GrindingArea("portable-training-band", 20, 25, measured_samples=100),),
    )
    assert projected is not None
    return party, projected[2]


def _party_after(
    before: PartyObservation,
    *,
    first_gain: int,
    second_gain: int,
) -> PartyObservation:
    first, second = before.members
    assert first.experience is not None and second.experience is not None
    return PartyObservation(
        members=(
            replace(first, experience=first.experience + first_gain),
            replace(second, experience=second.experience + second_gain),
        )
    )


def test_battle_adapter_preserves_existing_outcome_preference_without_teacher_label() -> None:
    battle = _battle_example()

    shared = adapt_battle_outcome_example(battle, scenario_id="battle-scenario")

    assert shared.family is ScenarioFamily.BATTLE
    assert shared.available_candidate_indices == (0, 1)
    assert shared.best_candidate_indices == battle.best_candidate_indices == (1,)
    assert shared.target_distribution.tolist() == [0.0, 1.0, 0.0]
    assert shared.public_dict()["teacher_choice_targets"] == 0
    assert shared.public_dict()["candidate_feature_values_public"] is False
    assert shared.public_dict()["schema"] == "pokemon.core.scenario-outcome-example.v1"
    assert "prospective_binding_sha256" not in shared.public_dict()


def test_navigation_adapter_prefers_verified_arrival_over_a_shorter_failed_route() -> None:
    shared = adapt_navigation_outcomes(
        _navigation_inference(),
        (
            NavigationOutcomeTrial(
                _navigation_decision(0),
                _navigation_outcome(
                    _navigation_decision(0),
                    succeeded=True,
                    movement_requests=12,
                    acknowledged_steps=10,
                ),
                frames_executed=480,
            ),
            NavigationOutcomeTrial(
                _navigation_decision(1),
                _navigation_outcome(
                    _navigation_decision(1),
                    succeeded=False,
                    movement_requests=4,
                    acknowledged_steps=4,
                ),
            ),
        ),
        scenario_id="navigation-scenario",
        root_lineage_id="navigation-root",
        initial_state_sha256=_digest("b"),
        partition=ScenarioPartition.TRAIN,
    )

    assert shared.family is ScenarioFamily.NAVIGATION
    assert shared.best_candidate_indices == (0,)
    assert shared.learner_update_eligible
    assert shared.outcomes[0] is not None
    assert shared.outcomes[0].evidence_sha256 is not None
    assert shared.outcomes[0].frames_executed == 480


def test_navigation_adapter_rejects_a_relabelled_decision_outcome_binding() -> None:
    first = _navigation_decision(0)
    second = _navigation_decision(1)

    with pytest.raises(ScenarioOutcomeError, match="decision/outcome binding"):
        NavigationOutcomeTrial(
            first,
            _navigation_outcome(
                second,
                succeeded=True,
                movement_requests=8,
                acknowledged_steps=7,
            ),
        )


def test_party_adapter_prefers_more_experience_without_a_center_visit() -> None:
    before, raw_candidates = _party_candidates()
    baseline = TeamTrainingProgress()
    shared = adapt_party_development_outcomes(
        raw_candidates,
        (
            PartyDevelopmentOutcomeTrial(
                candidate=raw_candidates.candidates[0],
                target_slot=1,
                before_party=before,
                after_party=_party_after(before, first_gain=120, second_gain=0),
                progress_before=baseline,
                progress_after=TeamTrainingProgress(battles_completed=1),
                frames_executed=2_000,
            ),
            PartyDevelopmentOutcomeTrial(
                candidate=raw_candidates.candidates[1],
                target_slot=2,
                before_party=before,
                after_party=_party_after(before, first_gain=0, second_gain=240),
                progress_before=baseline,
                progress_after=TeamTrainingProgress(battles_completed=1),
                frames_executed=2_000,
            ),
        ),
        scenario_id="party-scenario",
        root_lineage_id="party-root",
        initial_state_sha256=_digest("c"),
        partition=ScenarioPartition.TRAIN,
    )

    assert shared.family is ScenarioFamily.PARTY_DEVELOPMENT
    assert shared.best_candidate_indices == (1,)
    assert shared.learner_update_eligible
    assert shared.outcomes[1] is not None
    assert shared.outcomes[1].criterion_values[3] == pytest.approx(120.0)


def test_party_adapter_rejects_a_trial_bound_to_different_candidate_features() -> None:
    before, candidates = _party_candidates()
    altered = replace(
        candidates.candidates[0],
        features=tuple(-value for value in candidates.candidates[0].features),
    )
    trial = PartyDevelopmentOutcomeTrial(
        candidate=altered,
        target_slot=1,
        before_party=before,
        after_party=_party_after(before, first_gain=100, second_gain=0),
        progress_before=TeamTrainingProgress(),
        progress_after=TeamTrainingProgress(battles_completed=1),
        frames_executed=2_000,
    )

    with pytest.raises(ScenarioOutcomeError, match="candidate differs"):
        adapt_party_development_outcomes(
            candidates,
            (trial,),
            scenario_id="party-binding-falsifier",
            root_lineage_id="party-binding-root",
            initial_state_sha256=_digest("7"),
            partition=ScenarioPartition.TRAIN,
        )


def test_party_adapter_does_not_credit_a_candidate_for_training_someone_else() -> None:
    before, candidates = _party_candidates()
    shared = adapt_party_development_outcomes(
        candidates,
        (
            PartyDevelopmentOutcomeTrial(
                candidate=candidates.candidates[0],
                target_slot=1,
                before_party=before,
                after_party=_party_after(before, first_gain=100, second_gain=0),
                progress_before=TeamTrainingProgress(),
                progress_after=TeamTrainingProgress(battles_completed=1),
                frames_executed=2_000,
            ),
            PartyDevelopmentOutcomeTrial(
                candidate=candidates.candidates[1],
                target_slot=2,
                before_party=before,
                after_party=_party_after(before, first_gain=1_000, second_gain=0),
                progress_before=TeamTrainingProgress(),
                progress_after=TeamTrainingProgress(battles_completed=1),
                frames_executed=2_000,
            ),
        ),
        scenario_id="party-target-credit",
        root_lineage_id="party-target-credit-root",
        initial_state_sha256=_digest("8"),
        partition=ScenarioPartition.TRAIN,
    )

    assert shared.best_candidate_indices == (0,)
    assert shared.outcomes[1] is not None
    assert shared.outcomes[1].criterion_values[1] == 0.0
    assert shared.outcomes[1].criterion_values[4] == 0.0


def test_three_real_domain_types_share_one_catalog_without_sharing_raw_fields() -> None:
    battle = adapt_battle_outcome_example(
        _battle_example(),
        scenario_id="battle-scenario",
    )
    navigation = adapt_navigation_outcomes(
        _navigation_inference(),
        (
            NavigationOutcomeTrial(
                _navigation_decision(0),
                _navigation_outcome(
                    _navigation_decision(0),
                    succeeded=True,
                    movement_requests=12,
                    acknowledged_steps=10,
                ),
            ),
            NavigationOutcomeTrial(
                _navigation_decision(1),
                _navigation_outcome(
                    _navigation_decision(1),
                    succeeded=False,
                    movement_requests=4,
                    acknowledged_steps=4,
                ),
            ),
        ),
        scenario_id="navigation-scenario",
        root_lineage_id="navigation-root",
        initial_state_sha256=_digest("b"),
        partition=ScenarioPartition.TRAIN,
    )
    before, raw_candidates = _party_candidates()
    party = adapt_party_development_outcomes(
        raw_candidates,
        (
            PartyDevelopmentOutcomeTrial(
                raw_candidates.candidates[0],
                1,
                before,
                _party_after(before, first_gain=100, second_gain=0),
                TeamTrainingProgress(),
                TeamTrainingProgress(battles_completed=1),
                2_000,
            ),
            PartyDevelopmentOutcomeTrial(
                raw_candidates.candidates[1],
                2,
                before,
                _party_after(before, first_gain=0, second_gain=200),
                TeamTrainingProgress(),
                TeamTrainingProgress(battles_completed=1),
                2_000,
            ),
        ),
        scenario_id="party-scenario",
        root_lineage_id="party-root",
        initial_state_sha256=_digest("c"),
        partition=ScenarioPartition.TRAIN,
    )

    catalog = ScenarioOutcomeCatalog((battle, navigation, party))
    catalog.require_family_coverage()

    assert catalog.families == frozenset(ScenarioFamily)
    assert catalog.public_dict()["learner_update_eligible_examples"] == 3
    assert catalog.public_dict()["teacher_choice_targets"] == 0


def test_censored_candidate_cannot_quietly_become_a_preference_target() -> None:
    objective = OutcomeObjective(
        "navigation.test-objective.v1",
        ScenarioFamily.NAVIGATION,
        (OutcomeCriterion("navigation.success", OutcomeDirection.MAXIMIZE, 0),),
    )
    example = ScenarioOutcomeExample(
        scenario_id="censored-navigation",
        root_lineage_id="censored-root",
        initial_state_sha256=_digest("d"),
        partition=ScenarioPartition.TRAIN,
        objective=objective,
        feature_schema_id="portable.features.v1",
        feature_names=("candidate.signal",),
        candidates=(OutcomeCandidate(0, (0.0,)), OutcomeCandidate(1, (1.0,))),
        outcomes=(
            CandidateOutcome(OutcomeEvidenceStatus.MEASURED, (1.0,)),
            CandidateOutcome(OutcomeEvidenceStatus.CENSORED),
        ),
    )

    assert not example.fully_measured
    assert example.best_candidate_indices == ()
    assert not example.learner_update_eligible
    with pytest.raises(ScenarioOutcomeError, match="no preference distribution"):
        _ = example.target_distribution


def test_catalog_rejects_lineage_leakage_across_partitions() -> None:
    train = adapt_battle_outcome_example(
        _battle_example(),
        scenario_id="train-battle",
    )
    development = replace(
        train,
        scenario_id="development-battle",
        partition=ScenarioPartition.DEVELOPMENT,
        initial_state_sha256=_digest("e"),
    )

    with pytest.raises(ScenarioOutcomeError, match="root lineage crosses"):
        ScenarioOutcomeCatalog((train, development))


def test_rounded_equivalence_is_transitive_and_preserves_partial_ties() -> None:
    objective = OutcomeObjective(
        "battle.rounded-equivalence.v1",
        ScenarioFamily.BATTLE,
        (OutcomeCriterion("battle.score", OutcomeDirection.MAXIMIZE, 2),),
    )
    example = ScenarioOutcomeExample(
        scenario_id="rounded-tie",
        root_lineage_id="rounded-root",
        initial_state_sha256=_digest("f"),
        partition=ScenarioPartition.TRAIN,
        objective=objective,
        feature_schema_id="portable.features.v1",
        feature_names=("candidate.signal",),
        candidates=(
            OutcomeCandidate(0, (0.0,)),
            OutcomeCandidate(1, (0.5,)),
            OutcomeCandidate(2, (1.0,)),
        ),
        outcomes=(
            CandidateOutcome(OutcomeEvidenceStatus.MEASURED, (0.801,)),
            CandidateOutcome(OutcomeEvidenceStatus.MEASURED, (0.804,)),
            CandidateOutcome(OutcomeEvidenceStatus.MEASURED, (0.799,)),
        ),
    )

    assert example.best_candidate_indices == (0, 1, 2)
    assert example.target_distribution.tolist() == pytest.approx([1 / 3, 1 / 3, 1 / 3])
    assert not example.learner_update_eligible
