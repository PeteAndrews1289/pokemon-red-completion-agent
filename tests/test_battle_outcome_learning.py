from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_outcome_learning import (
    BattleOutcomeExample,
    BattleOutcomeLearningError,
    BattleTurnOutcome,
    adapt_mlp_last_layer_from_outcomes,
    compare_battle_outcome_preferences,
    evaluate_battle_outcome_preferences,
    run_battle_outcome_learning_curve,
    run_battle_outcome_learning_cycle,
)
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_ID,
    BattleFeatureBatch,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def _digest(character: str) -> str:
    return character * 64


def _features(*, scale: float = 1.0) -> BattleFeatureBatch:
    low = [0.0] * len(FEATURE_NAMES)
    high = [0.0] * len(FEATURE_NAMES)
    unavailable = [0.0] * len(FEATURE_NAMES)
    low[0] = -0.8 * scale
    high[0] = 0.8 * scale
    unavailable[0] = 0.2
    return BattleFeatureBatch(
        feature_names=FEATURE_NAMES,
        candidate_vectors=(tuple(low), tuple(high), tuple(unavailable)),
        legal_mask=(True, True, False),
        current_pp=(10.0, 10.0, 0.0),
        slot_indices=(0, 1, 2),
        schema_id=FEATURE_SCHEMA_ID,
    )


def _outcome(damage: float) -> BattleTurnOutcome:
    return BattleTurnOutcome(
        move_executed=True,
        opponent_damage_fraction=damage,
        player_damage_fraction=0.0,
        opponent_fainted=False,
        player_fainted=False,
        battle_exited=False,
        actions_executed=2,
        frames_executed=48,
    )


def _example(
    *,
    partition: ScenarioPartition,
    lineage: str,
    state_character: str,
    scale: float = 1.0,
) -> BattleOutcomeExample:
    return BattleOutcomeExample(
        root_lineage_id=lineage,
        initial_state_sha256=_digest(state_character),
        partition=partition,
        features=_features(scale=scale),
        outcomes=(_outcome(0.1), _outcome(0.8), None),
    )


def _model() -> MaskedMLPMoveRanker:
    input_weights = np.zeros((2, len(FEATURE_NAMES)), dtype=np.float64)
    input_weights[0, 0] = 1.0
    input_weights[1, 1] = 0.5
    return MaskedMLPMoveRanker(
        feature_names=FEATURE_NAMES,
        feature_schema_id=FEATURE_SCHEMA_ID,
        input_weights=input_weights,
        hidden_bias=np.zeros(2, dtype=np.float64),
        output_weights=np.asarray((-1.0, 0.25), dtype=np.float64),
        output_bias=0.0,
        training_seed=7,
    )


def test_last_layer_update_uses_outcomes_and_preserves_hidden_prior() -> None:
    base = _model()
    before = base.to_dict()
    training = _example(
        partition=ScenarioPartition.TRAIN,
        lineage="train-root-a",
        state_character="a",
    )

    update = adapt_mlp_last_layer_from_outcomes(
        base,
        (training,),
        epochs=200,
        learning_rate=0.03,
        prior_l2=0.01,
    )

    after = update.model.to_dict()
    assert after["input_weights"] == before["input_weights"]
    assert after["hidden_bias"] == before["hidden_bias"]
    assert after["output_weights"] != before["output_weights"]
    assert update.report.loss_after < update.report.loss_before
    assert update.report.base_model_sha256 != update.report.updated_model_sha256
    assert update.report.public_dict()["teacher_choice_targets"] == 0
    assert update.report.public_dict()["authority_promoted"] is False


def test_learning_cycle_evaluates_an_untouched_lineage_without_mutation() -> None:
    base = _model()
    training = _example(
        partition=ScenarioPartition.TRAIN,
        lineage="train-root-a",
        state_character="a",
    )
    development = _example(
        partition=ScenarioPartition.DEVELOPMENT,
        lineage="development-root-b",
        state_character="b",
        scale=0.75,
    )

    cycle = run_battle_outcome_learning_cycle(
        base,
        training_examples=(training,),
        development_examples=(development,),
        epochs=200,
        learning_rate=0.03,
        prior_l2=0.01,
    )

    assert cycle.base_development.correct_preferences == 0
    assert cycle.updated_development.correct_preferences == 1
    assert cycle.base_development.model_sha256 == cycle.update.report.base_model_sha256
    assert (
        cycle.updated_development.model_sha256
        == cycle.update.report.updated_model_sha256
    )
    assert cycle.public_dict()["lineage_partition_overlap"] == 0
    assert cycle.public_dict()["sealed_test_cases_opened"] == 0


def test_fit_rejects_development_examples_and_cross_partition_overlap() -> None:
    base = _model()
    development = _example(
        partition=ScenarioPartition.DEVELOPMENT,
        lineage="development-root",
        state_character="b",
    )
    with pytest.raises(BattleOutcomeLearningError, match="train partition"):
        adapt_mlp_last_layer_from_outcomes(base, (development,))

    training = replace(
        development,
        partition=ScenarioPartition.TRAIN,
    )
    with pytest.raises(BattleOutcomeLearningError, match="root lineage"):
        run_battle_outcome_learning_cycle(
            base,
            training_examples=(training,),
            development_examples=(development,),
        )


def test_evaluation_rejects_train_examples_and_does_not_change_model() -> None:
    model = _model()
    original = model.to_json()
    training = _example(
        partition=ScenarioPartition.TRAIN,
        lineage="train-root",
        state_character="c",
    )

    with pytest.raises(BattleOutcomeLearningError, match="development partition"):
        evaluate_battle_outcome_preferences(model, (training,))
    assert model.to_json() == original


def test_suppressed_move_cannot_become_a_target() -> None:
    suppressed = replace(_outcome(0.2), move_executed=False)
    with pytest.raises(BattleOutcomeLearningError, match="did not execute"):
        BattleOutcomeExample(
            root_lineage_id="train-root",
            initial_state_sha256=_digest("d"),
            partition=ScenarioPartition.TRAIN,
            features=_features(),
            outcomes=(suppressed, _outcome(0.8), None),
        )



def test_uninformative_tie_is_preserved_but_cannot_update_or_score() -> None:
    tied = _outcome(0.5)
    example = BattleOutcomeExample(
        root_lineage_id="train-root",
        initial_state_sha256=_digest("e"),
        partition=ScenarioPartition.TRAIN,
        features=_features(),
        outcomes=(tied, tied, None),
    )

    assert not example.learner_update_eligible
    with pytest.raises(BattleOutcomeLearningError, match="preference signal"):
        adapt_mlp_last_layer_from_outcomes(_model(), (example,))


def test_generic_outcome_allows_one_opponent_to_faint_before_battle_exit() -> None:
    outcome = replace(
        _outcome(1.0),
        opponent_fainted=True,
        battle_exited=False,
    )

    assert outcome.opponent_fainted
    assert not outcome.battle_exited


def test_partial_tie_splits_target_mass_across_all_best_candidates() -> None:
    vectors = tuple(
        tuple([value] + [0.0] * (len(FEATURE_NAMES) - 1))
        for value in (-0.5, 0.0, 0.5)
    )
    features = BattleFeatureBatch(
        feature_names=FEATURE_NAMES,
        candidate_vectors=vectors,
        legal_mask=(True, True, True),
        current_pp=(10.0, 10.0, 10.0),
        slot_indices=(0, 1, 2),
        schema_id=FEATURE_SCHEMA_ID,
    )
    example = BattleOutcomeExample(
        root_lineage_id="train-root-partial-tie",
        initial_state_sha256=_digest("f"),
        partition=ScenarioPartition.TRAIN,
        features=features,
        outcomes=(_outcome(0.1), _outcome(0.8), _outcome(0.8)),
    )

    assert example.best_candidate_indices == (1, 2)
    assert example.target_distribution.tolist() == [0.0, 0.5, 0.5]
    assert float(np.sum(example.target_distribution)) == 1.0


def test_initial_learning_curve_fits_frozen_prefixes_from_the_same_prior() -> None:
    base = _model()
    training = tuple(
        _example(
            partition=ScenarioPartition.TRAIN,
            lineage=f"train-root-{index}",
            state_character=character,
            scale=1.0 - index * 0.1,
        )
        for index, character in enumerate(("1", "2", "3", "4"))
    )
    development = tuple(
        _example(
            partition=ScenarioPartition.DEVELOPMENT,
            lineage=f"development-root-{index}",
            state_character=character,
            scale=0.5 + index * 0.1,
        )
        for index, character in enumerate(("5", "6"))
    )

    curve = run_battle_outcome_learning_curve(
        base,
        training_examples=training,
        development_examples=development,
        training_sizes=(1, 2, 4),
        epochs=100,
        learning_rate=0.03,
        prior_l2=0.01,
    )

    assert curve.training_sizes == (1, 2, 4)
    assert curve.training_order_state_sha256 == tuple(
        example.initial_state_sha256 for example in training
    )
    assert all(point.update is not None for point in curve.points)
    assert all(
        point.base_development.model_sha256
        == curve.points[0].base_development.model_sha256
        for point in curve.points
    )
    assert all(
        point.paired_development.example_count == len(development)
        and point.paired_development.updated_wins
        + point.paired_development.base_wins
        + point.paired_development.equivalent_choices
        == len(development)
        for point in curve.points
    )
    public = curve.public_dict()
    assert public["development_reused_for_fitting"] is False
    assert public["descriptive_initial_curve"] is True
    assert public["inferential_claim"] is False
    assert public["authority_promoted"] is False

    with pytest.raises(BattleOutcomeLearningError, match="training states"):
        replace(
            curve.points[-1],
            training_state_sha256=curve.points[-1].training_state_sha256[:-1],
        )
    with pytest.raises(BattleOutcomeLearningError, match="development catalog"):
        replace(
            curve,
            development_root_lineage_ids=("different-development-root",) * 2,
        )


def test_flat_prefix_remains_a_no_update_curve_point_instead_of_being_replaced() -> None:
    tied = _outcome(0.5)
    first = replace(
        _example(
            partition=ScenarioPartition.TRAIN,
            lineage="flat-root",
            state_character="7",
        ),
        outcomes=(tied, tied, None),
    )
    training = (
        first,
        _example(
            partition=ScenarioPartition.TRAIN,
            lineage="signal-root-a",
            state_character="8",
        ),
        _example(
            partition=ScenarioPartition.TRAIN,
            lineage="signal-root-b",
            state_character="9",
        ),
    )
    development = (
        _example(
            partition=ScenarioPartition.DEVELOPMENT,
            lineage="development-root-a",
            state_character="a",
        ),
        _example(
            partition=ScenarioPartition.DEVELOPMENT,
            lineage="development-root-b",
            state_character="b",
        ),
    )

    curve = run_battle_outcome_learning_curve(
        _model(),
        training_examples=training,
        development_examples=development,
        training_sizes=(1, 2, 3),
        epochs=50,
        learning_rate=0.03,
        prior_l2=0.01,
    )

    assert curve.points[0].update is None
    assert curve.points[0].status == "insufficient_preference_signal"
    assert curve.points[0].paired_development.updated_wins == 0
    assert curve.points[0].paired_development.base_wins == 0
    assert curve.points[0].paired_development.equivalent_choices == 2
    assert curve.points[1].update is not None
    assert curve.points[2].update is not None


def test_learning_curve_rejects_dependent_roots_and_optional_final_prefix() -> None:
    training = tuple(
        _example(
            partition=ScenarioPartition.TRAIN,
            lineage=f"root-{index}",
            state_character=character,
        )
        for index, character in enumerate(("c", "d", "e", "f"))
    )
    development = (
        _example(
            partition=ScenarioPartition.DEVELOPMENT,
            lineage="development-one",
            state_character="0",
        ),
        _example(
            partition=ScenarioPartition.DEVELOPMENT,
            lineage="development-two",
            state_character="1",
        ),
    )

    with pytest.raises(BattleOutcomeLearningError, match="complete training catalog"):
        run_battle_outcome_learning_curve(
            _model(),
            training_examples=training,
            development_examples=development,
            training_sizes=(1, 2, 3),
        )
    dependent = replace(training[1], root_lineage_id=training[0].root_lineage_id)
    with pytest.raises(BattleOutcomeLearningError, match="independent training root"):
        run_battle_outcome_learning_curve(
            _model(),
            training_examples=(training[0], dependent, training[2]),
            development_examples=development,
            training_sizes=(1, 2, 3),
        )


def test_paired_comparison_uses_selected_utility_and_preserves_equivalence() -> None:
    example = _example(
        partition=ScenarioPartition.DEVELOPMENT,
        lineage="paired-development-root",
        state_character="2",
    )
    base = _model()

    paired = compare_battle_outcome_preferences(base, base, (example,))

    assert paired.updated_wins == 0
    assert paired.base_wins == 0
    assert paired.equivalent_choices == 1
    assert paired.discordant_examples == 0
    assert paired.updated_better_one_sided_exact_p == 1.0
    assert paired.public_dict()["inferential_claim"] is False
