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
    evaluate_battle_outcome_preferences,
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
