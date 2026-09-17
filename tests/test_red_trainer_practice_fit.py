from __future__ import annotations

from copy import deepcopy

import pytest
from test_red_trainer_practice_features import _observation

from pokemon_red_completion.battle_scenario_capture import OBSERVATION_SCHEMA_V2
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_trainer_practice_fit import (
    CONTROL_ACTION_FEATURE_NAMES,
    CONTROL_ACTION_SCHEMA_ID,
    TrainerPracticeFitError,
    TrainerPracticeThreeHeadModel,
    control_action_candidates,
    fit_trainer_practice_three_heads,
)
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadExample, TrainerHeadModel
from pokemon_red_completion.red_trainer_practice_features import CONTROL_FEATURE_NAMES_V2


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
