from __future__ import annotations

import numpy as np
import pytest

from pokemon_red_completion.battle_expected_utility import (
    adapt_mlp_last_layer_from_expected_utilities,
    aggregate_battle_rng_trials,
    expected_utility_record,
    parse_expected_utility_record,
)
from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_outcome_learning import (
    BattleOutcomeExample,
    BattleOutcomeLearningError,
    BattleTurnOutcome,
)
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_ID,
    BattleFeatureBatch,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def _features() -> BattleFeatureBatch:
    power = FEATURE_NAMES.index("move.accuracy_weighted_effective_power_fraction")
    rows = [[0.0] * len(FEATURE_NAMES) for _ in range(2)]
    rows[0][power] = 0.2
    rows[1][power] = 0.8
    return BattleFeatureBatch(
        feature_names=FEATURE_NAMES,
        candidate_vectors=tuple(tuple(row) for row in rows),
        legal_mask=(True, True),
        current_pp=(10.0, 10.0),
        slot_indices=(0, 1),
    )


def _outcome(utility: float, frames: int) -> BattleTurnOutcome:
    if utility >= 2.0:
        opponent_fainted = True
        opponent_damage = utility - 2.0
        player_damage = 0.0
    elif utility >= 0.0:
        opponent_fainted = False
        opponent_damage = utility
        player_damage = 0.0
    else:
        opponent_fainted = False
        opponent_damage = 0.0
        player_damage = -utility
    return BattleTurnOutcome(
        move_executed=True,
        opponent_damage_fraction=opponent_damage,
        player_damage_fraction=player_damage,
        opponent_fainted=opponent_fainted,
        player_fainted=False,
        battle_exited=False,
        actions_executed=1,
        frames_executed=frames + 100,
        pre_attack_frames=frames,
    )


def _trial(frames: int, utilities: tuple[float, float]) -> BattleOutcomeExample:
    return BattleOutcomeExample(
        root_lineage_id="root-a",
        initial_state_sha256="a" * 64,
        partition=ScenarioPartition.TRAIN,
        features=_features(),
        outcomes=tuple(_outcome(value, frames) for value in utilities),
    )


def _model() -> MaskedMLPMoveRanker:
    power = FEATURE_NAMES.index("move.accuracy_weighted_effective_power_fraction")
    weights = np.zeros((1, len(FEATURE_NAMES)), dtype=np.float64)
    weights[0, power] = 1.0
    return MaskedMLPMoveRanker(
        feature_names=FEATURE_NAMES,
        feature_schema_id=FEATURE_SCHEMA_ID,
        input_weights=weights,
        hidden_bias=np.zeros(1, dtype=np.float64),
        output_weights=np.asarray((-1.0,), dtype=np.float64),
        output_bias=0.0,
        training_seed=7,
    )


def test_aggregates_distinct_rng_trials_into_expected_utility() -> None:
    example = aggregate_battle_rng_trials(
        (
            _trial(2_048, (0.8, 0.0)),
            _trial(2_061, (0.2, 3.0)),
            _trial(2_079, (0.5, 0.0)),
        )
    )

    assert example.expected_utilities == pytest.approx((0.5, 1.0))
    assert example.utility_standard_deviations[0] == pytest.approx(
        np.std((0.8, 0.2, 0.5))
    )
    assert example.trial_counts == (3, 3)
    assert example.pre_attack_frame_targets == (2_048, 2_061, 2_079)
    assert example.best_candidate_indices == (1,)
    assert example.learner_update_eligible is True


def test_aggregation_rejects_repeated_rng_frame_target() -> None:
    with pytest.raises(BattleOutcomeLearningError, match="frame targets repeat"):
        aggregate_battle_rng_trials(
            (_trial(2_048, (0.8, 0.0)), _trial(2_048, (0.2, 3.0)))
        )


def test_expected_utility_record_round_trips_and_rederives() -> None:
    example = aggregate_battle_rng_trials(
        (_trial(2_048, (0.8, 0.0)), _trial(2_061, (0.2, 3.0)))
    )
    record = expected_utility_record(
        example,
        capture_id="capture-a",
        manifest_sha256="b" * 64,
    )

    assert parse_expected_utility_record(record) == example

    record["best_candidate_indices"] = [0]
    with pytest.raises(BattleOutcomeLearningError, match="derivation differs"):
        parse_expected_utility_record(record)


def test_expected_utility_fit_learns_mean_winner() -> None:
    example = aggregate_battle_rng_trials(
        (
            _trial(2_048, (0.8, 0.0)),
            _trial(2_061, (0.2, 3.0)),
            _trial(2_079, (0.5, 0.0)),
        )
    )
    base = _model()
    assert base.predict(
        example.features.candidate_vectors,
        legal_mask=example.features.legal_mask,
        current_pp=example.features.current_pp,
    ) == 0

    update = adapt_mlp_last_layer_from_expected_utilities(
        base,
        (example,),
        epochs=200,
        learning_rate=0.1,
        prior_l2=0.0,
    )

    assert update.model.predict(
        example.features.candidate_vectors,
        legal_mask=example.features.legal_mask,
        current_pp=example.features.current_pp,
    ) == 1
    assert update.report.loss_after < update.report.loss_before
    assert update.report.public_dict()["teacher_choice_targets"] == 0


def test_expected_utility_fit_rejects_development() -> None:
    train = aggregate_battle_rng_trials(
        (_trial(2_048, (0.8, 0.0)), _trial(2_061, (0.2, 3.0)))
    )
    development = type(train)(
        root_lineage_id=train.root_lineage_id,
        initial_state_sha256=train.initial_state_sha256,
        partition=ScenarioPartition.DEVELOPMENT,
        features=train.features,
        expected_utilities=train.expected_utilities,
        utility_standard_deviations=train.utility_standard_deviations,
        trial_counts=train.trial_counts,
        pre_attack_frame_targets=train.pre_attack_frame_targets,
    )

    with pytest.raises(BattleOutcomeLearningError, match="accepts train only"):
        adapt_mlp_last_layer_from_expected_utilities(_model(), (development,))
