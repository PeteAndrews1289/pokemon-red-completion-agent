from __future__ import annotations

from copy import deepcopy

import pytest
from test_red_trainer_practice_features import _observation

from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_control_features import BattleControlHistoryTracker
from pokemon_red_completion.battle_scenario_capture import OBSERVATION_SCHEMA_V2
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_trainer_practice_features import (
    CONTROL_FEATURE_NAMES_V2,
    project_trainer_control_features,
)
from pokemon_red_completion.red_trainer_practice_fit import (
    CONTROL_ACTION_FEATURE_NAMES,
    CONTROL_ACTION_SCHEMA_ID,
    TRAINING_TARGET_SCHEMA_ID,
    TrainerPracticeFitError,
    TrainerPracticeThreeHeadModel,
    _append_examples,
    _combine_identical_inputs,
    _mean_action_returns,
    _observed_returns,
    _soft_return_target,
    control_action_candidates,
    fit_trainer_practice_three_heads,
    summarize_trainer_practice_training,
)
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadExample, TrainerHeadModel


def test_control_head_can_learn_opposite_choices_from_different_states():
    low_hp = [0.0] * len(CONTROL_FEATURE_NAMES_V2)
    high_hp = low_hp.copy()
    hp_index = CONTROL_FEATURE_NAMES_V2.index("player.hp_ratio")
    high_hp[hp_index] = 1.0
    low_rows = control_action_candidates(tuple(low_hp))
    high_rows = control_action_candidates(tuple(high_hp))
    assert len(low_rows[0]) == len(CONTROL_ACTION_FEATURE_NAMES)
    model = TrainerHeadModel.fit(
        schema_id=CONTROL_ACTION_SCHEMA_ID,
        feature_names=CONTROL_ACTION_FEATURE_NAMES,
        examples=(
            TrainerHeadExample(low_rows, (1,)),
            TrainerHeadExample(high_rows, (0,)),
        ),
        seed=12,
        epochs=300,
    )
    assert model.predict_index(low_rows) == 1
    assert model.predict_index(high_rows) == 0


def test_identical_inputs_combine_timing_uncertainty_once():
    candidates = ((0.0, 1.0), (1.0, 0.0))
    first = TrainerHeadExample(candidates, (0,), (0.8, 0.2))
    second = TrainerHeadExample(candidates, (1,), (0.2, 0.8))
    combined = _combine_identical_inputs([first, second])
    assert len(combined) == 1
    assert combined[0].target_probabilities == (0.5, 0.5)
    assert combined[0].best_indices == (0, 1)
    assert _soft_return_target(((1.0, 0.0), (0.0, 1.0))) == (0.5, 0.5)
    assert _soft_return_target(((1.0, 0.0),))[0] > 0.999


def test_target_softmax_preserves_mean_return_winner_and_combines_raw_returns():
    timings = ((2.0, 0.0), (2.0, 0.0), (-2.0, 1.0), (-2.0, 1.0), (-2.0, 1.0))
    assert _soft_return_target(timings)[1] > _soft_return_target(timings)[0]
    candidates = ((0.0, 1.0), (1.0, 0.0))
    cases = [
        TrainerHeadExample(candidates, (0,), (0.99, 0.01), (2.0, 0.0)),
        TrainerHeadExample(candidates, (1,), (0.01, 0.99), (-2.0, 1.0)),
        TrainerHeadExample(candidates, (1,), (0.01, 0.99), (-2.0, 1.0)),
    ]
    combined = _combine_identical_inputs(cases)[0]
    assert combined.mean_returns == (-2.0 / 3.0, 2.0 / 3.0)
    assert combined.best_indices == (1,)
    assert combined.target_probabilities[1] > combined.target_probabilities[0]
    assert TRAINING_TARGET_SCHEMA_ID.endswith(".v2")


def test_control_commits_to_one_reserve_before_hidden_timing():
    refs = [
        "pokemon.core:battle:move:1",
        "pokemon.core:battle:switch:2",
        "pokemon.core:battle:switch:3",
    ]
    timings = [[1.0, 2.0, -2.0], [1.0, 2.0, -2.0], *([[1.0, -2.0, 2.0]] * 3)]
    observed = _observed_returns("control", refs, [1.0, -0.4, 0.4], timings)
    assert _mean_action_returns("control", refs, observed) == (1.0, 0.4)
    target = _target()
    target["heads"]["control"] = {
        "choice_refs": refs,
        "returns": [1.0, -0.4, 0.4],
        "best_indices": [0],
        "timing_returns": timings,
    }
    examples = {"move": [], "control": [], "switch": []}
    _append_examples(examples, target, PokemonRedBattleCatalog())
    control = examples["control"][0]
    assert control.best_indices == (0,)
    assert control.mean_returns == (1.0, 0.4)
    assert control.target_probabilities[0] > control.target_probabilities[1]


def test_training_diagnostics_report_unique_inputs_and_simple_baseline():
    first = _target()
    second = deepcopy(first)
    second["capture_id"] = "unit-capture-two"
    second["heads"]["move"]["returns"] = [1.0, 0.8]
    second["heads"]["move"]["best_indices"] = [0]
    model = fit_trainer_practice_three_heads(
        [first, second], seed=22, require_corpus_floor=False, epochs=10
    )
    report = summarize_trainer_practice_training([first, second], model)
    assert report["move"]["examples"] == 2
    assert report["move"]["unique_candidate_matrices"] == 1
    assert report["move"]["conflicting_winner_groups"] == 1
    assert report["move"]["first_candidate_mean_train_regret"] == 0.1
    assert report["composed_action"]["examples"] == 2


def test_stateless_control_projection_matches_live_history_contract():
    observation = _target()["observation"]
    catalog = PokemonRedBattleCatalog()
    batch = BattleFeatureProjector(catalog).project(observation)
    tracker = BattleControlHistoryTracker()
    tracker.before("unit", observation)
    tracker.advance(BattleAction.move(1), observation)
    projected = project_trainer_control_features(observation, catalog=catalog, move_batch=batch)
    assert not any(name.startswith("history.") for name in CONTROL_FEATURE_NAMES_V2)
    assert len(projected) == len(CONTROL_FEATURE_NAMES_V2)


def _target():
    observation = _observation()
    moves = observation["features"]["party"]["lead"]["moves"]
    moves.append(
        {
            "slot_index": 1,
            "move_ref": "pokemon.red.gb.us.rev0:move:085",
            "pp": 10,
        }
    )
    batch = BattleFeatureProjector(PokemonRedBattleCatalog()).project(observation)
    return {
        "schema": "pokemon.red.trainer-practice-three-head-targets.v1",
        "partition": "train",
        "scenario_count": 1,
        "observation_schema": OBSERVATION_SCHEMA_V2,
        "capture_id": "unit-capture",
        "root_lineage_id": "unit-root",
        "observation": observation,
        "legacy_model_input": {
            "feature_names": list(batch.feature_names),
            "candidate_vectors": [list(row) for row in batch.candidate_vectors],
            "candidate_move_slots": [slot + 1 for slot in batch.slot_indices],
            "legal_mask": list(batch.legal_mask),
            "current_pp": list(batch.current_pp),
        },
        "heads": {
            "move": {
                "choice_refs": ["pokemon.core:battle:move:1", "pokemon.core:battle:move:2"],
                "returns": [0.8, 1.0],
                "best_indices": [1],
            },
            "switch": {
                "choice_refs": ["pokemon.core:battle:switch:2", "pokemon.core:battle:switch:3"],
                "returns": [0.4, 0.7],
                "best_indices": [1],
            },
            "control": {
                "choice_refs": ["pokemon.core:battle:move:2", "pokemon.core:battle:switch:3"],
                "returns": [1.0, 0.7],
                "best_indices": [0],
            },
        },
    }


def test_train_only_three_head_fit_round_trip_and_corpus_floor():
    target = _target()
    with pytest.raises(TrainerPracticeFitError, match="balanced independent"):
        fit_trainer_practice_three_heads([target], seed=12)
    model = fit_trainer_practice_three_heads(
        [target],
        seed=12,
        require_corpus_floor=False,
        epochs=40,
    )
    restored = TrainerPracticeThreeHeadModel.from_dict(model.to_dict())
    assert restored.train_capture_ids == ("unit-capture",)
    assert restored.move.feature_names == model.move.feature_names
    target["partition"] = "development"
    with pytest.raises(TrainerPracticeFitError, match="TRAIN"):
        fit_trainer_practice_three_heads([target], seed=12, require_corpus_floor=False)


def test_move_continuation_requires_same_train_capture_and_root():
    target = _target()
    old = fit_trainer_practice_three_heads(
        [target], seed=12, require_corpus_floor=False, epochs=10
    )
    new_target = deepcopy(target)
    new_target["capture_id"] = "second-train-capture"
    fitted = fit_trainer_practice_three_heads(
        [target, new_target], seed=12, require_corpus_floor=False,
        epochs=100, warm_start_move=old, warm_start_move_epochs=100,
    )
    assert len(fitted.train_capture_ids) == 2
    unrelated = deepcopy(target)
    unrelated["capture_id"] = "unrelated"
    with pytest.raises(TrainerPracticeFitError, match="warm-start move lineage"):
        fit_trainer_practice_three_heads(
            [unrelated], seed=12, require_corpus_floor=False,
            epochs=100, warm_start_move=old, warm_start_move_epochs=100,
        )


def test_fit_floor_rejects_contextless_or_unbalanced_scenario_supply():
    records = []
    for root in range(4):
        for scenario in range(4):
            record = deepcopy(_target())
            record["root_lineage_id"] = f"root-{root}"
            record["capture_id"] = f"capture-{root}-{scenario}"
            record["timing_count"] = 5
            record["decision_context"] = "main"
            record["attack_depleted"] = False
            records.append(record)
    with pytest.raises(TrainerPracticeFitError, match="contexts required"):
        fit_trainer_practice_three_heads(records, seed=12)
    extra = deepcopy(records[0])
    extra["capture_id"] = "unbalanced-extra"
    with pytest.raises(TrainerPracticeFitError, match="balanced independent"):
        fit_trainer_practice_three_heads([*records, extra], seed=12)
