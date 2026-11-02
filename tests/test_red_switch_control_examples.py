from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_trainer_proposed_control import setup_case

from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_status_battle_features import expand_frozen_move
from pokemon_red_completion.red_switch_control_examples import build_switch_control_examples
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeFitError
from pokemon_red_completion.red_trainer_practice_outcome_policy import (
    RedTrainerPracticeOutcomePolicy,
)


def composed_case():
    target, frozen, model = setup_case()
    target["observation"]["features"]["battle"]["status_context"] = {
        "schema": "pokemon.core.battle.status-context.v1",
        "player_confused": False,
        "opponent_confused": False,
        "player_stages": [0] * 6,
        "opponent_stages": [0] * 6,
    }
    # The damage shortlist deliberately disagrees with the status head's
    # all-damage ranking, exposing the legacy compiler's missing composition.
    damage = replace(frozen.move, weights2=-frozen.move.weights2)
    model = replace(model, move=expand_frozen_move(frozen.move), damage_reference=damage)
    return target, model


def test_rows_and_measured_child_returns_match_live_damage_status_composition():
    target, model = composed_case()
    original, weights = deepcopy(target), model.to_dict()
    rows = build_switch_control_examples([target], model)
    assert set(rows) == {"switch", "control"} and len(rows["control"]) == 1
    catalog = PokemonRedBattleCatalog()
    batch = BattleFeatureProjector(catalog).project(target["observation"])
    policy = RedTrainerPracticeOutcomePolicy("test", "test", model)
    policy.choose_main(
        target["observation"],
        SimpleNamespace(features=batch, supported_candidate_mask=batch.legal_mask),
    )
    diag = policy.last_decision_diagnostics
    row = rows["control"][0]
    assert [list(r) for r in row.candidate_vectors] == diag["control_candidate_vectors"]
    refs = target["heads"]["control"]["choice_refs"]
    returns = target["heads"]["control"]["returns"]
    selected = [
        f"pokemon.core:battle:move:{diag['proposed_move_slot']}",
        f"pokemon.core:battle:switch:{diag['proposed_switch_slot']}",
    ]
    assert row.mean_returns == tuple(returns[refs.index(ref)] for ref in selected)
    other = replace(model, damage_reference=None)
    assert build_switch_control_examples([target], other)["control"][0] != row
    assert target == original and model.to_dict() == weights


def test_control_rows_must_be_recompiled_after_the_switch_head_changes():
    target, baseline = composed_case()
    candidate = replace(
        baseline, switch=replace(baseline.switch, weights2=-baseline.switch.weights2)
    )
    original = build_switch_control_examples([target], baseline)
    rebuilt = build_switch_control_examples([target], candidate)
    assert original["switch"] == rebuilt["switch"]
    assert original["control"] != rebuilt["control"]
    batch = BattleFeatureProjector(PokemonRedBattleCatalog()).project(target["observation"])
    policy = RedTrainerPracticeOutcomePolicy("test", "test", candidate)
    policy.choose_main(
        target["observation"],
        SimpleNamespace(features=batch, supported_candidate_mask=batch.legal_mask),
    )
    diag = policy.last_decision_diagnostics
    row = rebuilt["control"][0]
    assert diag["control_candidate_vectors"] == [list(r) for r in row.candidate_vectors]
    head = target["heads"]["control"]
    ref = f"pokemon.core:battle:switch:{diag['proposed_switch_slot']}"
    assert row.mean_returns[1] == head["returns"][head["choice_refs"].index(ref)]


def test_prompt_decline_has_no_fabricated_move_and_forced_rows_need_no_move_head():
    target, model = composed_case()
    target["legacy_model_input"] = None
    target["heads"] = {
        "control": {
            "choice_refs": ["pokemon.core:battle:decline-switch", "pokemon.core:battle:switch:2"],
            "returns": [2.0, -1.0],
            "best_indices": [0],
        }
    }
    row = build_switch_control_examples([target], model)["control"][0]
    assert row.mean_returns == (2.0, -1.0) and row.best_indices == (0,)
    target, model = composed_case()
    target["legacy_model_input"] = None
    target["heads"] = {"switch": target["heads"]["switch"]}
    rows = build_switch_control_examples([target], model)
    assert len(rows["switch"]) == 1 and rows["control"] == []


def test_missing_status_observation_is_not_silently_replaced_with_healthy_defaults():
    target, model = composed_case()
    del target["observation"]["features"]["battle"]["status_context"]
    with pytest.raises(ValueError, match="status context"):
        build_switch_control_examples([target], model)


def test_masked_moves_cannot_supply_a_concrete_child_proposal():
    target, model = composed_case()
    target["legacy_model_input"]["legal_mask"][0] = False
    with pytest.raises(TrainerPracticeFitError, match="illegal retained move"):
        build_switch_control_examples([target], model)


def test_control_returns_average_timing_before_forming_a_target():
    target, model = composed_case()
    refs = target["heads"]["control"]["choice_refs"]
    target["heads"]["control"]["timing_returns"] = [
        [2.0] * len(refs),
        [-4.0] * len(refs),
        [5.0] * len(refs),
    ]
    row = build_switch_control_examples([target], model)["control"][0]
    assert row.mean_returns == (1.0, 1.0)
    assert row.best_indices == (0, 1) and row.target_probabilities == (0.5, 0.5)


def test_status_move_remains_in_the_same_live_and_training_shortlist():
    target, model = composed_case()
    observation = target["observation"]
    observation["features"]["party"]["lead"]["moves"].append(
        {"slot_index": 2, "move_ref": "pokemon.red.gb.us.rev0:move:156", "pp": 10}
    )
    batch = BattleFeatureProjector(PokemonRedBattleCatalog()).project(observation)
    target["legacy_model_input"] = {
        "feature_names": list(batch.feature_names),
        "candidate_vectors": [list(row) for row in batch.candidate_vectors],
        "candidate_move_slots": [slot + 1 for slot in batch.slot_indices],
        "legal_mask": list(batch.legal_mask),
        "current_pp": list(batch.current_pp),
    }
    head = target["heads"]["control"]
    head["choice_refs"].append("pokemon.core:battle:move:3")
    head["returns"].append(0.5)
    row = build_switch_control_examples([target], model)["control"][0]
    policy = RedTrainerPracticeOutcomePolicy("test", "test", model)
    policy.choose_main(
        observation, SimpleNamespace(features=batch, supported_candidate_mask=batch.legal_mask)
    )
    assert policy.last_decision_diagnostics["control_candidate_vectors"] == [
        list(r) for r in row.candidate_vectors
    ]


@pytest.mark.parametrize(
    "fault", ["development", "root", "duplicate", "schema", "bool_count", "empty", "no_heads"]
)
def test_refuses_bad_or_unmeasured_training_identity(fault):
    target, model = composed_case()
    targets = [target]
    if fault == "development":
        target["partition"] = "development"
    elif fault == "root":
        target["root_lineage_id"] = "unregistered"
    elif fault == "duplicate":
        targets.append(deepcopy(target))
    elif fault == "schema":
        target["observation_schema"] = "unknown"
    elif fault == "bool_count":
        target["scenario_count"] = True
    elif fault == "empty":
        targets = []
    elif fault == "no_heads":
        target["heads"] = {}
    with pytest.raises(TrainerPracticeFitError):
        build_switch_control_examples(targets, model)


@pytest.mark.parametrize(
    "refs",
    [
        ["pokemon.core:battle:move:1", "pokemon.core:battle:move:2"],
        ["pokemon.core:battle:switch:2", "pokemon.core:battle:switch:3"],
        ["pokemon.core:battle:move:01", "pokemon.core:battle:switch:2"],
        ["pokemon.core:battle:move:1", "pokemon.core:battle:move:1"],
        ["pokemon.core:battle:move:5", "pokemon.core:battle:switch:2"],
        [
            "pokemon.core:battle:decline-switch",
            "pokemon.core:battle:move:1",
            "pokemon.core:battle:switch:2",
        ],
        [[], "pokemon.core:battle:switch:2"],
    ],
)
def test_refuses_malformed_concrete_choice_inventory(refs):
    target, model = composed_case()
    target["heads"]["control"]["choice_refs"] = refs
    with pytest.raises(TrainerPracticeFitError):
        build_switch_control_examples([target], model)
