from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_trainer_practice_fit import _target

from pokemon_red_completion.battle_actions import BattleActionKind
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_trainer_practice_features import project_trainer_move_features
from pokemon_red_completion.red_trainer_practice_fit import (
    TrainerPracticeFitError,
    TrainerPracticeThreeHeadModel,
    _append_examples,
    fit_trainer_practice_three_heads,
    refit_trainer_proposed_control,
    summarize_trainer_practice_training,
)
from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
)
from pokemon_red_completion.red_trainer_proposed_control import (
    PROPOSED_CONTROL_SCHEMA,
    estimated_finishing_features,
    proposed_control,
)


def setup_case():
    target = _target()
    target["heads"]["control"] = {
        "choice_refs": target["heads"]["move"]["choice_refs"]
        + target["heads"]["switch"]["choice_refs"],
        "returns": [0.8, 1.0, 0.4, 0.7],
        "best_indices": [1],
    }
    frozen = fit_trainer_practice_three_heads(
        [target], seed=31, require_corpus_floor=False, epochs=5
    )
    model = refit_trainer_proposed_control([target], frozen, seed=7, epochs=5)
    return target, frozen, model


def test_control_only_fit_round_trip_keeps_child_weights_and_legacy_model():
    _, frozen, model = setup_case()
    assert model.move is frozen.move and model.switch is frozen.switch
    assert model.control.schema_id == PROPOSED_CONTROL_SCHEMA
    assert TrainerPracticeThreeHeadModel.from_dict(model.to_dict()).to_dict() == model.to_dict()
    assert TrainerPracticeThreeHeadModel.from_dict(frozen.to_dict()).to_dict() == frozen.to_dict()
    with pytest.raises(TrainerPracticeFitError, match="fitted-component"):
        replace(model, control_target_mode="best_component")


@pytest.mark.parametrize("change", ["partition", "capture", "root", "duplicate"])
def test_control_fit_rejects_changed_lineage(change):
    target, frozen, _ = setup_case()
    records = [target]
    if change == "partition":
        target["partition"] = "development"
    elif change == "capture":
        target["capture_id"] = "other"
    elif change == "root":
        target["root_lineage_id"] = "other"
    else:
        records.append(deepcopy(target))
    with pytest.raises(TrainerPracticeFitError, match="TRAIN lineage"):
        refit_trainer_proposed_control(records, frozen, seed=1, epochs=1)


def test_fit_and_live_concrete_proposals_match_and_mask_is_respected():
    target, _, model = setup_case()
    observation = target["observation"]
    batch = BattleFeatureProjector(PokemonRedBattleCatalog()).project(observation)
    examples = {"move": [], "control": [], "switch": []}
    _append_examples(
        examples,
        target,
        PokemonRedBattleCatalog(),
        control_components=(model.move, model.switch),
        control_input_schema=model.control.schema_id,
    )
    policy = RedTrainerPracticeOutcomePolicy("test", "test", model)
    action = policy.choose_main(
        observation, SimpleNamespace(features=batch, supported_candidate_mask=batch.legal_mask)
    )
    diag = policy.last_decision_diagnostics
    assert diag["control_candidate_vectors"] == [
        list(row) for row in examples["control"][0].candidate_vectors
    ]
    assert (
        action.move_slot if action.kind == BattleActionKind.SELECT_MOVE else action.party_slot
    ) == diag[
        "proposed_move_slot"
        if action.kind == BattleActionKind.SELECT_MOVE
        else "proposed_switch_slot"
    ]
    policy = RedTrainerPracticeOutcomePolicy("test", "test", model)
    policy._unanswered_voluntary_switch_opponent = 0
    action = policy.choose_main(
        observation, SimpleNamespace(features=batch, supported_candidate_mask=batch.legal_mask)
    )
    assert action.kind == BattleActionKind.SELECT_MOVE
    assert policy.last_decision_diagnostics["control_candidate_vectors"] == []
    assert summarize_trainer_practice_training([target], model)["composed_action"]["examples"] == 1


def test_proposals_follow_legal_subset_and_prompt_has_no_invented_move():
    target, _, model = setup_case()
    obs = target["observation"]
    catalog = PokemonRedBattleCatalog()
    batch = BattleFeatureProjector(catalog).project(obs)
    first = proposed_control(
        obs,
        catalog=catalog,
        move_head=model.move,
        switch_head=model.switch,
        move_batch=batch,
        move_slots=(1,),
        switch_slots=(2,),
    )
    second = proposed_control(
        obs,
        catalog=catalog,
        move_head=model.move,
        switch_head=model.switch,
        move_batch=batch,
        move_slots=(2,),
        switch_slots=(3,),
    )
    assert (first.move_slot, first.switch_slot) == (1, 2)
    assert first.candidate_vectors != second.candidate_vectors
    prompt = proposed_control(
        obs,
        catalog=catalog,
        move_head=model.move,
        switch_head=model.switch,
        move_batch=None,
        move_slots=(),
        switch_slots=(2,),
    )
    assert prompt.move_slot is None
    policy = RedTrainerPracticeOutcomePolicy("test", "test", model)
    assert policy.choose_switch(obs, (2,), forced=False, may_decline=True) in (None, 2)


def test_finishing_estimate_uses_public_ratio_and_marks_unknown_effects():
    target, _, _ = setup_case()
    obs = target["observation"]
    batch = BattleFeatureProjector(PokemonRedBattleCatalog()).project(obs)
    features = project_trainer_move_features(obs, batch)
    row = features.candidate_vectors[1]
    initial = estimated_finishing_features(obs, row)
    changed = deepcopy(obs)
    changed["features"]["battle"]["opponent_hp_ratio"] = 0.05
    revised = estimated_finishing_features(changed, row)
    assert revised[2] > initial[2] and revised[2] > 0
    changed["features"]["battle"]["opponent_live_stats"] = {"defense": 999}
    assert estimated_finishing_features(changed, row) == revised
    unusual = list(row)
    unusual[features.feature_names.index("move.effect.fixed_damage")] = 1.0
    assert estimated_finishing_features(obs, tuple(unusual)) == (0, 0, 0)
    assert estimated_finishing_features(obs, None) == (0, 0, 0)


def test_fresh_comparison_recipe_does_not_mutate_original():
    from run_red_trainer_proposed_control import fresh_recipe

    original = {
        "practice": {
            "actor_hp": 45,
            "opponent_hp": 53,
            "opponent_level": 29,
            "opponent_reserves": [{"level": 29}],
        }
    }
    changed = fresh_recipe(original)
    assert original["practice"]["opponent_reserves"][0]["level"] == 29
    assert changed["practice"]["actor_hp"] == 42
    assert changed["practice"]["opponent_hp"] == 56
    assert changed["practice"]["opponent_reserves"][0]["level"] == 30
