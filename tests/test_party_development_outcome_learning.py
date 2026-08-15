from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import numpy as np
import pytest

from pokemon_red_completion.party_development_outcome_learning import (
    PartyDevelopmentOutcomeLearningError,
    PartyDevelopmentPairedEvaluation,
    PartyDevelopmentTeacherPrior,
    adapt_party_development_model_from_outcomes,
    bind_teacher_prior_from_offline_evidence,
    canonical_party_development_outcome_model_sha256,
    evaluate_party_development_outcomes,
    initialize_from_teacher_model,
    load_party_development_outcome_model,
    run_party_development_outcome_learning_cycle,
)
from pokemon_red_completion.party_development_outcomes import (
    PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE,
)
from pokemon_red_completion.party_development_rank import (
    PARTY_DEVELOPMENT_FEATURE_NAMES,
    PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
    CandidateCompletionSemantics,
    EvolutionRouteKind,
    EvolutionSemantics,
    PartyDevelopmentContext,
    PartyDevelopmentGoal,
    augment_training_candidate_set,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.scenario_outcomes import (
    CandidateOutcome,
    OutcomeCandidate,
    OutcomeEvidenceStatus,
    ScenarioOutcomeExample,
)
from pokemon_red_completion.training_candidate_model import (
    TrainingCandidateMLP,
    canonical_training_candidate_model_sha256,
)
from pokemon_red_completion.training_candidate_rank import (
    TRAINING_CANDIDATE_FEATURE_NAMES,
    TrainingCandidate,
    TrainingCandidateSet,
    TrainingChoiceKind,
)


def _teacher_model() -> TrainingCandidateMLP:
    random = np.random.default_rng(20260814)
    width = len(TRAINING_CANDIDATE_FEATURE_NAMES)
    hidden = 4
    return TrainingCandidateMLP(
        weights1=random.normal(0.0, 0.2, (width, hidden)),
        bias1=np.asarray((0.2, -0.1, 0.05, 0.3), dtype=np.float64),
        weights2=np.asarray((0.5, -0.2, 0.3, 0.4), dtype=np.float64),
        feature_mean=np.zeros(width, dtype=np.float64),
        feature_scale=np.ones(width, dtype=np.float64),
        training_seed=20260814,
    )


def _teacher_prior(teacher: TrainingCandidateMLP) -> PartyDevelopmentTeacherPrior:
    return PartyDevelopmentTeacherPrior(
        model_file_sha256="d" * 64,
        model_canonical_sha256=canonical_training_candidate_model_sha256(teacher),
        offline_evidence_sha256="e" * 64,
        training_root_lineage_ids=("teacher-prior-train",),
        training_state_sha256=("8" * 64,),
        evaluation_root_lineage_ids=("teacher-prior-evaluation",),
        evaluation_state_sha256=("9" * 64,),
    )


def _initialized_model():
    teacher = _teacher_model()
    return initialize_from_teacher_model(
        teacher,
        teacher_prior=_teacher_prior(teacher),
    )


def _v1_candidates() -> TrainingCandidateSet:
    rows = []
    for index, level in enumerate((0.2, 0.6)):
        features = [0.0] * len(TRAINING_CANDIDATE_FEATURE_NAMES)
        features[TRAINING_CANDIDATE_FEATURE_NAMES.index("candidate.level")] = level
        features[TRAINING_CANDIDATE_FEATURE_NAMES.index("venue.fightable_share")] = (
            0.8 - level / 2
        )
        rows.append(TrainingCandidate(index, tuple(features)))
    return TrainingCandidateSet(TrainingChoiceKind.VENUE, tuple(rows))


def _v2_candidates():
    base = _v1_candidates()
    context = PartyDevelopmentContext(
        goal=PartyDevelopmentGoal.COLLECTION,
        party_size=2,
        below_floor_count=2,
        evolution_needed_count=1,
        registration_needed_count=1,
        living_needed_count=1,
        role_gap_count=0,
        registration_completion_ratio=0.5,
        living_completion_ratio=0.4,
        role_coverage_ratio=1.0,
        healthy_trainable_count=2,
        exhausted_count=0,
        fainted_count=0,
    )
    semantics = tuple(
        CandidateCompletionSemantics(
            evolution=EvolutionSemantics(
                required=True,
                stages_remaining=1,
                route_kind=EvolutionRouteKind.LEVEL,
                levels_to_next=3,
            ),
            registration_needed=index == 1,
            living_target_needed=index == 1,
            projected_survival_margin=0.4,
        )
        for index in range(2)
    )
    return augment_training_candidate_set(base, context, semantics)


def _criterion_values(*, winner: bool) -> tuple[float, ...]:
    values = [0.0] * len(PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE.criteria)
    values[0] = 1.0
    values[1] = 1.0
    values[2] = float(winner)
    values[-1] = 1_000.0
    return tuple(values)


def _example(
    *,
    scenario: str,
    root: str,
    digest_character: str,
    partition: ScenarioPartition,
    winner_index: int,
    tied: bool = False,
    censored_index: int | None = None,
) -> ScenarioOutcomeExample:
    registration_index = PARTY_DEVELOPMENT_FEATURE_NAMES.index(
        "candidate.registration_needed"
    )
    goal_index = PARTY_DEVELOPMENT_FEATURE_NAMES.index("context.goal.collection")
    rows: list[OutcomeCandidate] = []
    outcomes: list[CandidateOutcome] = []
    for index in range(2):
        features = [0.0] * len(PARTY_DEVELOPMENT_FEATURE_NAMES)
        features[goal_index] = 1.0
        features[registration_index] = float(index == winner_index)
        rows.append(OutcomeCandidate(index, tuple(features)))
        if index == censored_index:
            outcomes.append(CandidateOutcome(OutcomeEvidenceStatus.CENSORED))
        else:
            outcomes.append(
                CandidateOutcome(
                    OutcomeEvidenceStatus.MEASURED,
                    _criterion_values(winner=tied or index == winner_index),
                )
            )
    return ScenarioOutcomeExample(
        scenario_id=scenario,
        root_lineage_id=root,
        initial_state_sha256=digest_character * 64,
        partition=partition,
        objective=PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE,
        feature_schema_id=PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
        feature_names=PARTY_DEVELOPMENT_FEATURE_NAMES,
        candidates=tuple(rows),
        outcomes=tuple(outcomes),
    )


def test_teacher_initialization_is_exact_on_the_frozen_v1_feature_prefix() -> None:
    teacher = _teacher_model()
    base = _v1_candidates()
    v2 = _v2_candidates()
    initialized = initialize_from_teacher_model(
        teacher,
        teacher_prior=_teacher_prior(teacher),
    )

    assert initialized.training_target == "teacher_initialization"
    assert initialized.outcome_training_examples == 0
    assert initialized.scores(v2).tolist() == pytest.approx(teacher.scores(base).tolist())
    assert initialized.probabilities(v2).tolist() == pytest.approx(
        teacher.probabilities(base).tolist()
    )
    assert np.count_nonzero(
        initialized.weights1[len(TRAINING_CANDIDATE_FEATURE_NAMES) :]
    ) == 0
    assert initialized.teacher_prior.training_root_lineage_ids == (
        "teacher-prior-train",
    )
    assert initialized.teacher_prior.evaluation_root_lineage_ids == (
        "teacher-prior-evaluation",
    )


def test_teacher_initialization_rejects_a_model_outside_bound_provenance() -> None:
    teacher = _teacher_model()
    mismatched = PartyDevelopmentTeacherPrior(
        model_file_sha256="d" * 64,
        model_canonical_sha256="f" * 64,
        offline_evidence_sha256="e" * 64,
        training_root_lineage_ids=("teacher-prior-train",),
        training_state_sha256=("8" * 64,),
        evaluation_root_lineage_ids=("teacher-prior-evaluation",),
        evaluation_state_sha256=("9" * 64,),
    )

    with pytest.raises(PartyDevelopmentOutcomeLearningError, match="authenticated"):
        initialize_from_teacher_model(teacher, teacher_prior=mismatched)


def test_teacher_prior_requires_canonical_lineage_pairs() -> None:
    teacher = _teacher_model()

    with pytest.raises(PartyDevelopmentOutcomeLearningError, match="canonical order"):
        PartyDevelopmentTeacherPrior(
            model_file_sha256="d" * 64,
            model_canonical_sha256=canonical_training_candidate_model_sha256(teacher),
            offline_evidence_sha256="e" * 64,
            training_root_lineage_ids=("teacher-train-b", "teacher-train-a"),
            training_state_sha256=("2" * 64, "1" * 64),
            evaluation_root_lineage_ids=("teacher-evaluation",),
            evaluation_state_sha256=("3" * 64,),
        )


def test_historical_offline_receipt_binds_train_and_opened_validation_roots() -> None:
    teacher = _teacher_model()
    document = {
        "schema": "pokemon-training-candidate-offline-receipt-v1",
        "status": "offline_candidate_eligible",
        "candidate_model_file_sha256": "d" * 64,
        "candidate_model_canonical_sha256": canonical_training_candidate_model_sha256(
            teacher
        ),
        "lineages": [
            {
                "lineage_id": "teacher-train-b",
                "partition": "train",
                "root_sha256": "2" * 64,
            },
            {
                "lineage_id": "teacher-validation",
                "partition": "validation",
                "root_sha256": "3" * 64,
            },
            {
                "lineage_id": "teacher-train-a",
                "partition": "train",
                "root_sha256": "1" * 64,
            },
        ],
        "offline_candidate_eligible": True,
        "private_artifacts_tracked": False,
    }
    payload = json.dumps(document).encode("ascii")
    digest = hashlib.sha256(payload).hexdigest()

    prior = bind_teacher_prior_from_offline_evidence(
        teacher,
        model_file_sha256="d" * 64,
        evidence_payload=payload,
        expected_evidence_sha256=digest,
    )

    assert prior.training_root_lineage_ids == (
        "teacher-train-a",
        "teacher-train-b",
    )
    assert prior.training_state_sha256 == ("1" * 64, "2" * 64)
    assert prior.evaluation_root_lineage_ids == ("teacher-validation",)
    assert prior.evaluation_state_sha256 == ("3" * 64,)
    with pytest.raises(PartyDevelopmentOutcomeLearningError, match="authentication"):
        bind_teacher_prior_from_offline_evidence(
            teacher,
            model_file_sha256="d" * 64,
            evidence_payload=payload,
            expected_evidence_sha256="f" * 64,
        )


def test_outcome_update_learns_new_completion_semantics_and_soft_targets() -> None:
    base = _initialized_model()
    training = (
        _example(
            scenario="train-a",
            root="train-root-a",
            digest_character="a",
            partition=ScenarioPartition.TRAIN,
            winner_index=1,
        ),
        _example(
            scenario="train-b",
            root="train-root-b",
            digest_character="b",
            partition=ScenarioPartition.TRAIN,
            winner_index=0,
        ),
        _example(
            scenario="train-tie",
            root="train-root-tie",
            digest_character="c",
            partition=ScenarioPartition.TRAIN,
            winner_index=0,
            tied=True,
        ),
    )

    update = adapt_party_development_model_from_outcomes(
        base,
        training,
        epochs=300,
        learning_rate=0.02,
        prior_l2=0.01,
    )

    assert update.report.loss_after < update.report.loss_before
    assert update.report.tied_target_examples == 1
    assert update.model.training_target == "verified_outcome_preference"
    assert update.model.outcome_training_examples == 3
    assert set(update.model.outcome_training_root_lineage_ids) == {
        "train-root-a",
        "train-root-b",
        "train-root-tie",
    }
    assert update.report.public_dict()["teacher_choice_targets"] == 0
    assert update.report.public_dict()["authority_promoted"] is False
    with pytest.raises(PartyDevelopmentOutcomeLearningError, match="already consumed"):
        adapt_party_development_model_from_outcomes(update.model, training)


def test_learning_cycle_uses_untouched_development_roots_and_beats_its_prior() -> None:
    base = _initialized_model()
    training = (
        _example(
            scenario="cycle-train-a",
            root="cycle-train-root-a",
            digest_character="1",
            partition=ScenarioPartition.TRAIN,
            winner_index=0,
        ),
        _example(
            scenario="cycle-train-b",
            root="cycle-train-root-b",
            digest_character="2",
            partition=ScenarioPartition.TRAIN,
            winner_index=1,
        ),
    )
    development = (
        _example(
            scenario="cycle-development",
            root="cycle-development-root",
            digest_character="3",
            partition=ScenarioPartition.DEVELOPMENT,
            winner_index=1,
        ),
    )

    cycle = run_party_development_outcome_learning_cycle(
        base,
        training_examples=training,
        development_examples=development,
        epochs=300,
        learning_rate=0.02,
        prior_l2=0.01,
    )

    assert cycle.update.report.loss_after < cycle.update.report.loss_before
    assert cycle.updated_development.cross_entropy < cycle.base_development.cross_entropy
    assert cycle.updated_development.mean_winner_probability > (
        cycle.base_development.mean_winner_probability
    )
    assert cycle.paired_development.winner_probability_improvements == 1
    assert cycle.paired_development.winner_probability_regressions == 0
    assert cycle.paired_development.mean_winner_probability_delta > 0
    assert cycle.paired_development.paired_two_sided_exact_p == 1.0
    assert cycle.public_dict()["sealed_test_cases_opened"] == 0
    assert cycle.public_dict()["authority_promoted"] is False


def test_censored_evidence_and_partition_overlap_fail_closed() -> None:
    base = _initialized_model()
    censored = _example(
        scenario="censored-train",
        root="censored-root",
        digest_character="4",
        partition=ScenarioPartition.TRAIN,
        winner_index=0,
        censored_index=1,
    )
    with pytest.raises(PartyDevelopmentOutcomeLearningError, match="cannot become a target"):
        adapt_party_development_model_from_outcomes(base, (censored,))

    train = _example(
        scenario="overlap-train",
        root="overlap-root",
        digest_character="5",
        partition=ScenarioPartition.TRAIN,
        winner_index=0,
    )
    development = _example(
        scenario="overlap-development",
        root="overlap-root",
        digest_character="6",
        partition=ScenarioPartition.DEVELOPMENT,
        winner_index=1,
    )
    with pytest.raises(PartyDevelopmentOutcomeLearningError, match="crosses train"):
        run_party_development_outcome_learning_cycle(
            base,
            training_examples=(train,),
            development_examples=(development,),
        )


def test_teacher_prior_roots_cannot_reappear_in_outcome_training_or_development() -> None:
    base = _initialized_model()
    reused_train_root = _example(
        scenario="prior-overlap-train",
        root="teacher-prior-train",
        digest_character="4",
        partition=ScenarioPartition.TRAIN,
        winner_index=0,
    )
    reused_evaluation_state = _example(
        scenario="prior-overlap-development",
        root="fresh-development-root",
        digest_character="9",
        partition=ScenarioPartition.DEVELOPMENT,
        winner_index=1,
    )

    with pytest.raises(PartyDevelopmentOutcomeLearningError, match="teacher-prior"):
        adapt_party_development_model_from_outcomes(base, (reused_train_root,))
    with pytest.raises(PartyDevelopmentOutcomeLearningError, match="teacher-prior"):
        evaluate_party_development_outcomes(base, (reused_evaluation_state,))

    with pytest.raises(PartyDevelopmentOutcomeLearningError, match="teacher-prior"):
        replace(
            base,
            outcome_training_examples=1,
            outcome_training_root_lineage_ids=("teacher-prior-train",),
            outcome_training_state_sha256=("4" * 64,),
        )


def test_model_round_trip_is_authenticated(tmp_path) -> None:
    model = _initialized_model()
    path = tmp_path / "party-development-v2.json"
    payload = json.dumps(model.to_dict(), sort_keys=True, separators=(",", ":")).encode(
        "ascii"
    )
    path.write_bytes(payload)
    file_sha256 = hashlib.sha256(payload).hexdigest()

    loaded = load_party_development_outcome_model(path, expected_sha256=file_sha256)

    assert canonical_party_development_outcome_model_sha256(loaded) == (
        canonical_party_development_outcome_model_sha256(model)
    )
    assert loaded.to_dict() == model.to_dict()
    with pytest.raises(PartyDevelopmentOutcomeLearningError, match="authentication"):
        load_party_development_outcome_model(path, expected_sha256="f" * 64)


def test_evaluation_refuses_training_examples() -> None:
    model = _initialized_model()
    training = _example(
        scenario="wrong-eval-partition",
        root="wrong-eval-root",
        digest_character="7",
        partition=ScenarioPartition.TRAIN,
        winner_index=0,
    )

    with pytest.raises(PartyDevelopmentOutcomeLearningError, match="partition"):
        evaluate_party_development_outcomes(model, (training,))


def test_paired_exact_test_uses_only_discordant_decisions() -> None:
    comparison = PartyDevelopmentPairedEvaluation(
        base_model_sha256="a" * 64,
        updated_model_sha256="b" * 64,
        example_count=10,
        updated_wins=6,
        base_wins=0,
        correctness_ties=4,
        winner_probability_improvements=8,
        winner_probability_regressions=1,
        winner_probability_ties=1,
        mean_winner_probability_delta=0.2,
        root_lineage_ids=tuple(f"paired-root-{index}" for index in range(10)),
    )

    assert comparison.discordant_correctness_pairs == 6
    assert comparison.paired_two_sided_exact_p == pytest.approx(0.03125)
