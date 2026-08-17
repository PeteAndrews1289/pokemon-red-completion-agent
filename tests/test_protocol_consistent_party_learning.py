from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import protocol_consistent_party_learning as protocol  # noqa: E402
from protocol_consistent_party_learning import (  # noqa: E402
    PROTOCOL_PAIRWISE_RIDGE,
    ProtocolMetricPair,
    ProtocolMetrics,
    ProtocolPartyLearningError,
    ProtocolPartyRanker,
    audit_protocol_party_representation,
    canonical_protocol_party_ranker_sha256,
    run_protocol_party_leave_one_root_out,
)

from pokemon_red_completion.party_development_outcome_learning import (  # noqa: E402
    PartyDevelopmentTeacherPrior,
    initialize_from_teacher_model,
)
from pokemon_red_completion.party_development_outcomes import (  # noqa: E402
    PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE,
)
from pokemon_red_completion.party_development_rank import (  # noqa: E402
    PARTY_DEVELOPMENT_FEATURE_NAMES,
    PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
    PartyDevelopmentGoal,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402
from pokemon_red_completion.scenario_outcomes import (  # noqa: E402
    CandidateOutcome,
    OutcomeCandidate,
    OutcomeEvidenceStatus,
    ScenarioOutcomeExample,
)
from pokemon_red_completion.training_candidate_model import (  # noqa: E402
    TrainingCandidateMLP,
    canonical_training_candidate_model_sha256,
)
from pokemon_red_completion.training_candidate_rank import (  # noqa: E402
    TRAINING_CANDIDATE_FEATURE_NAMES,
    TrainingChoiceKind,
)


def _prior_model():
    width = len(TRAINING_CANDIDATE_FEATURE_NAMES)
    teacher = TrainingCandidateMLP(
        weights1=np.zeros((width, 3), dtype=np.float64),
        bias1=np.zeros(3, dtype=np.float64),
        weights2=np.zeros(3, dtype=np.float64),
        feature_mean=np.zeros(width, dtype=np.float64),
        feature_scale=np.ones(width, dtype=np.float64),
        training_seed=20260817,
    )
    prior = PartyDevelopmentTeacherPrior(
        model_file_sha256="a" * 64,
        model_canonical_sha256=canonical_training_candidate_model_sha256(teacher),
        offline_evidence_sha256="b" * 64,
        training_root_lineage_ids=("historical-train",),
        training_state_sha256=("c" * 64,),
        evaluation_root_lineage_ids=("historical-development",),
        evaluation_state_sha256=("d" * 64,),
    )
    return initialize_from_teacher_model(teacher, teacher_prior=prior)


def _outcome_values(rank: int) -> tuple[float, ...]:
    values = [0.0] * len(PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE.criteria)
    values[0] = 1.0
    values[1] = 1.0
    values[2] = float(rank)
    values[-1] = 1_000.0
    return tuple(values)


def _example(
    index: int,
    *,
    kind: TrainingChoiceKind,
    goal: PartyDevelopmentGoal,
    partition: ScenarioPartition = ScenarioPartition.TRAIN,
    qualities: tuple[float, ...] = (0.0, 0.5, 1.0),
) -> ScenarioOutcomeExample:
    rows: list[OutcomeCandidate] = []
    outcomes: list[CandidateOutcome] = []
    for candidate_index, quality in enumerate(qualities):
        features = [0.0] * len(PARTY_DEVELOPMENT_FEATURE_NAMES)
        features[PARTY_DEVELOPMENT_FEATURE_NAMES.index("choice.trainee")] = float(
            kind is TrainingChoiceKind.TRAINEE
        )
        features[PARTY_DEVELOPMENT_FEATURE_NAMES.index(f"context.goal.{goal.value}")] = 1.0
        if kind is TrainingChoiceKind.TRAINEE:
            if goal is PartyDevelopmentGoal.BALANCE:
                features[PARTY_DEVELOPMENT_FEATURE_NAMES.index("candidate.level_floor_deficit")] = (
                    quality
                )
            elif goal is PartyDevelopmentGoal.COLLECTION:
                features[PARTY_DEVELOPMENT_FEATURE_NAMES.index("candidate.registration_needed")] = (
                    quality
                )
                features[
                    PARTY_DEVELOPMENT_FEATURE_NAMES.index("candidate.living_target_needed")
                ] = quality
            elif goal is PartyDevelopmentGoal.EVOLUTION:
                features[PARTY_DEVELOPMENT_FEATURE_NAMES.index("candidate.evolution_required")] = (
                    quality
                )
                features[
                    PARTY_DEVELOPMENT_FEATURE_NAMES.index("candidate.evolution_stages_remaining")
                ] = quality
                features[
                    PARTY_DEVELOPMENT_FEATURE_NAMES.index("candidate.evolution_feasible_now")
                ] = quality
            else:
                features[PARTY_DEVELOPMENT_FEATURE_NAMES.index("candidate.role_needed")] = quality
                features[PARTY_DEVELOPMENT_FEATURE_NAMES.index("candidate.role_complete")] = (
                    1.0 - quality
                )
        else:
            for name in (
                "venue.fightable_share",
                "venue.has_nearby_healer",
                "venue.prior_reliability",
                "venue.prior_expected_yield",
                "venue.prior_matchup_safety",
            ):
                features[PARTY_DEVELOPMENT_FEATURE_NAMES.index(name)] = quality
            for name in (
                "venue.prior_travel_cost",
                "venue.prior_recovery_cost",
            ):
                features[PARTY_DEVELOPMENT_FEATURE_NAMES.index(name)] = 1.0 - quality
        rows.append(OutcomeCandidate(candidate_index, tuple(features)))
        outcomes.append(
            CandidateOutcome(
                status=OutcomeEvidenceStatus.MEASURED,
                criterion_values=_outcome_values(candidate_index),
            )
        )
    return ScenarioOutcomeExample(
        scenario_id=f"protocol-scenario-{index}",
        root_lineage_id=f"protocol-root-{index}",
        initial_state_sha256=f"{index:064x}",
        partition=partition,
        objective=PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE,
        feature_schema_id=PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
        feature_names=PARTY_DEVELOPMENT_FEATURE_NAMES,
        candidates=tuple(rows),
        outcomes=tuple(outcomes),
    )


def _training_examples() -> tuple[ScenarioOutcomeExample, ...]:
    trainee = tuple(
        _example(
            index,
            kind=TrainingChoiceKind.TRAINEE,
            goal=PartyDevelopmentGoal.BALANCE,
        )
        for index in range(1, 5)
    )
    venue_goals = (
        PartyDevelopmentGoal.COLLECTION,
        PartyDevelopmentGoal.EVOLUTION,
        PartyDevelopmentGoal.ROLE_COVERAGE,
    )
    venue = tuple(
        _example(
            index,
            kind=TrainingChoiceKind.VENUE,
            goal=venue_goals[(index - 5) % len(venue_goals)],
        )
        for index in range(5, 11)
    )
    return (*trainee, *venue)


def test_train_only_protocol_improves_every_frozen_metric_and_fits_separate_heads() -> None:
    base = _prior_model()

    result = run_protocol_party_leave_one_root_out(base, _training_examples())

    evaluation = result.evaluation
    assert evaluation.passed is True
    assert evaluation.overall.base.accuracy == 0.0
    assert evaluation.overall.updated.accuracy == 1.0
    assert evaluation.overall.updated.cross_entropy < evaluation.overall.base.cross_entropy
    assert (
        evaluation.overall.updated.mean_winner_probability
        > evaluation.overall.base.mean_winner_probability
    )
    assert evaluation.updated_wins == 10
    assert evaluation.base_wins == 0
    assert set(evaluation.by_action) == {"trainee", "venue"}
    assert set(evaluation.by_goal) == {
        "balance",
        "collection",
        "evolution",
        "role_coverage",
    }
    assert evaluation.by_goal["collection"].updated.accuracy == 1.0
    assert evaluation.by_goal["evolution"].updated.accuracy == 1.0
    assert not np.array_equal(
        result.model.trainee_weights,
        result.model.venue_weights,
    )
    assert result.model.ridge == PROTOCOL_PAIRWISE_RIDGE
    assert len(result.model.training_lineages) == 10
    serialized = result.model.to_dict()
    reloaded = ProtocolPartyRanker.from_dict(serialized)
    assert reloaded.to_dict() == serialized
    assert canonical_protocol_party_ranker_sha256(
        reloaded
    ) == canonical_protocol_party_ranker_sha256(result.model)
    assert canonical_protocol_party_ranker_sha256(result.model) == (
        "33d2092b9a5e056cb27d84b5b0c51341f02ebee80411c4914f3f382996e1a378"
    )
    wrong_names = json.loads(json.dumps(serialized))
    wrong_names["representation_names"][0] = "fabricated.position"
    with pytest.raises(ProtocolPartyLearningError, match="identity"):
        ProtocolPartyRanker.from_dict(wrong_names)
    integer_weights = json.loads(json.dumps(serialized))
    integer_weights["trainee_weights"][0] = 1
    with pytest.raises(ProtocolPartyLearningError, match="weights"):
        ProtocolPartyRanker.from_dict(integer_weights)
    public = evaluation.public_dict()
    assert "development_labels_opened" not in public
    assert public["evaluation"] == "deterministic_leave_one_root_out_train_roots_only"
    assert public["evidence_class"] == (
        "train_only_architecture_selection_not_independent_generalization"
    )
    assert result.representation_audit.passed is True
    assert result.representation_audit.action_goal_counts == {
        "trainee:balance": 4,
        "venue:collection": 2,
        "venue:evolution": 2,
        "venue:role_coverage": 2,
    }


def test_protocol_rejects_the_old_outcome_trained_base_model() -> None:
    base = _prior_model()
    outcome_trained = replace(
        base,
        outcome_training_examples=1,
        outcome_training_root_lineage_ids=("old-outcome-root",),
        outcome_training_state_sha256=("e" * 64,),
    )

    with pytest.raises(ProtocolPartyLearningError, match="exclude every earlier"):
        run_protocol_party_leave_one_root_out(outcome_trained, _training_examples())


def test_protocol_rejects_development_labels_before_any_fit() -> None:
    examples = list(_training_examples())
    examples[0] = replace(examples[0], partition=ScenarioPartition.DEVELOPMENT)

    with pytest.raises(ProtocolPartyLearningError, match="development labels"):
        run_protocol_party_leave_one_root_out(_prior_model(), examples)


def test_protocol_rejects_repeated_roots_and_missing_action_head() -> None:
    examples = list(_training_examples())
    examples[1] = replace(
        examples[1],
        root_lineage_id=examples[0].root_lineage_id,
    )
    with pytest.raises(ProtocolPartyLearningError, match="repeats a root"):
        run_protocol_party_leave_one_root_out(_prior_model(), examples)

    trainee_only = tuple(
        _example(
            index,
            kind=TrainingChoiceKind.TRAINEE,
            goal=PartyDevelopmentGoal.COLLECTION,
        )
        for index in range(1, 5)
    )
    with pytest.raises(ProtocolPartyLearningError, match="both action heads"):
        run_protocol_party_leave_one_root_out(_prior_model(), trainee_only)


def test_protocol_model_is_permutation_equivariant() -> None:
    base = _prior_model()
    result = run_protocol_party_leave_one_root_out(base, _training_examples())
    original = _training_examples()[0]
    order = (2, 0, 1)
    permuted = replace(
        original,
        candidates=tuple(
            replace(original.candidates[source], candidate_index=target)
            for target, source in enumerate(order)
        ),
        outcomes=tuple(original.outcomes[source] for source in order),
    )

    original_scores = result.model.scores(base, original)
    permuted_scores = result.model.scores(base, permuted)

    assert permuted_scores.tolist() == pytest.approx([original_scores[source] for source in order])
    assert int(np.argmax(permuted_scores)) == 0


def test_representation_audit_requires_each_goal_conditioned_venue_component() -> None:
    examples = list(_training_examples())
    cost_indices = tuple(
        PARTY_DEVELOPMENT_FEATURE_NAMES.index(name)
        for name in ("venue.prior_travel_cost", "venue.prior_recovery_cost")
    )
    for target_index in (4, 7):
        broken = examples[target_index]
        examples[target_index] = replace(
            broken,
            candidates=tuple(
                replace(
                    candidate,
                    features=tuple(
                        0.0 if index in cost_indices else value
                        for index, value in enumerate(candidate.features)
                    ),
                )
                for candidate in broken.candidates
            ),
        )

    audit = audit_protocol_party_representation(_prior_model(), examples)

    assert audit.passed is False
    assert audit.venue_interaction_variance["venue:collection:cost"] is False


def test_every_goal_slice_is_an_independent_nonregression_gate() -> None:
    improved = ProtocolMetricPair(
        base=ProtocolMetrics(3, 1, 1.0, 0.3),
        updated=ProtocolMetrics(3, 2, 0.8, 0.5),
    )
    regressed = ProtocolMetricPair(
        base=ProtocolMetrics(3, 1, 1.0, 0.3),
        updated=ProtocolMetrics(3, 1, 1.1, 0.2),
    )

    assert (
        protocol._evaluation_passed(
            improved,
            {"trainee": improved, "venue": improved},
            {"collection": regressed, "evolution": improved},
            (1, 0, 2, 2, 1, 0),
        )
        is False
    )


def test_unequal_menu_widths_receive_equal_total_pairwise_weight() -> None:
    examples = (
        _example(
            31,
            kind=TrainingChoiceKind.TRAINEE,
            goal=PartyDevelopmentGoal.BALANCE,
        ),
        _example(
            32,
            kind=TrainingChoiceKind.TRAINEE,
            goal=PartyDevelopmentGoal.BALANCE,
            qualities=(0.0, 0.33, 0.66, 1.0),
        ),
    )

    _rows, _offsets, _targets, weights = protocol._pairwise_rows(
        _prior_model(),
        examples,
    )

    assert float(np.sum(weights[:3])) == pytest.approx(0.5)
    assert float(np.sum(weights[3:])) == pytest.approx(0.5)
    assert weights[:3].tolist() == pytest.approx([1.0 / 6.0] * 3)
    assert weights[3:].tolist() == pytest.approx([1.0 / 12.0] * 6)


def test_each_leave_one_root_out_fit_excludes_the_held_out_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    examples = _training_examples()
    ordered = tuple(sorted(examples, key=lambda item: item.root_lineage_id))
    calls: list[tuple[str, ...]] = []
    original = protocol._fit_protocol_ranker

    def recording_fit(base: object, fold: object) -> object:
        fold_examples = tuple(fold)
        calls.append(tuple(item.root_lineage_id for item in fold_examples))
        return original(base, fold_examples)

    monkeypatch.setattr(protocol, "_fit_protocol_ranker", recording_fit)
    run_protocol_party_leave_one_root_out(_prior_model(), examples)

    assert len(calls) == len(ordered) + 1
    for held_out, roots in zip(ordered, calls[: len(ordered)], strict=True):
        assert held_out.root_lineage_id not in roots
        assert len(roots) == len(ordered) - 1
    assert set(calls[-1]) == {item.root_lineage_id for item in ordered}


def test_optimizer_nonconvergence_fails_closed() -> None:
    examples = tuple(item for item in _training_examples() if item.candidates[0].features[0] == 1.0)
    rows, offsets, targets, weights = protocol._pairwise_rows(_prior_model(), examples)

    with pytest.raises(ProtocolPartyLearningError, match="did not converge"):
        protocol._fit_pairwise_residual(
            rows,
            offsets,
            targets,
            weights,
            maximum_steps=1,
        )
