from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest
from test_red_status_battle_features import status_observation
from test_red_trainer_practice_fit import _target

from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_balanced_status_features import (
    BALANCED_STATUS_NAMES,
    BALANCED_STATUS_SCHEMA,
    COMPACT_STATUS_NAMES,
    project_balanced_status_moves,
)
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog, pokemon_red_move_ref
from pokemon_red_completion.red_status_battle_features import (
    STATUS_MOVE_NAMES,
    move_schema,
    project_for_head,
    project_status_moves,
    status_choice_slots,
)
from pokemon_red_completion.red_trainer_practice_features import MOVE_FEATURE_NAMES, MOVE_SCHEMA_ID
from pokemon_red_completion.red_trainer_practice_fit import (
    TrainerPracticeThreeHeadModel,
    fit_trainer_practice_three_heads,
)
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadModel


def projected(move=156, *, opponent_status=None, own_full=False, opponent=177):
    obs = status_observation()
    obs["features"]["battle"]["opponent_status"] = opponent_status
    obs["features"]["battle"]["opponent_species_ref"] = (
        f"pokemon.red.gb.us.rev0:species:{opponent:03d}")
    lead = obs["features"]["party"]["lead"]
    lead["moves"][1]["move_ref"] = pokemon_red_move_ref(move)
    if own_full:
        lead["hp"] = lead["max_hp"]
        lead["hp_ratio"] = 1.
    batch = BattleFeatureProjector(PokemonRedBattleCatalog()).project(obs)
    return obs, batch, project_balanced_status_moves(obs, batch)


def values(projected):
    return dict(zip(BALANCED_STATUS_NAMES, projected.candidate_vectors[-1], strict=True))


@pytest.mark.parametrize("move", [79, 86, 77])
def test_existing_status_interacts_only_with_inflicting_a_major_status(move):
    _, _, free = projected(move)
    _, _, occupied = projected(move, opponent_status="paralysis")
    assert values(free)["choice.major_status_occupied"] == 0
    assert values(occupied)["choice.major_status_occupied"] == 1
    _, _, confusion = projected(109, opponent_status="paralysis")
    assert values(confusion)["choice.major_status_occupied"] == 0


@pytest.mark.parametrize("move", [105, 156])
def test_recovery_missing_hp_is_distinct_from_full_hp(move):
    _, _, low = projected(move)
    _, _, full = projected(move, own_full=True)
    assert values(low)["choice.heal_missing_hp"] > 0
    assert values(low)["choice.heal_full_hp"] == 0
    assert values(full)["choice.heal_missing_hp"] == 0
    assert values(full)["choice.heal_full_hp"] == 1


def test_confusion_and_accuracy_floor_are_observed_not_hidden_duration():
    obs, batch, confused = projected(109)
    assert values(confused)["choice.already_confused"] == 1
    obs["features"]["battle"]["status_context"]["opponent_confused"] = False
    assert values(project_balanced_status_moves(obs, batch))["choice.already_confused"] == 0
    obs, batch, _ = projected(28)
    obs["features"]["battle"]["status_context"]["opponent_stages"][4] = -6
    assert values(project_balanced_status_moves(obs, batch))["choice.accuracy_floor"] == 1


def test_type_conditions_follow_gen_one_not_later_generation_rules():
    catalog = PokemonRedBattleCatalog()
    poison = next(i for i in catalog.species_ids if "poison" in catalog.resolve_species(
        f"pokemon.red.gb.us.rev0:species:{i:03d}").types)
    ground = next(i for i in catalog.species_ids if "ground" in catalog.resolve_species(
        f"pokemon.red.gb.us.rev0:species:{i:03d}").types)
    assert values(projected(77, opponent=poison)[2])["choice.poison_type_immune"] == 1
    assert values(projected(86, opponent=ground)[2])[
        "choice.electric_paralysis_type_immune"] == 1
    assert values(projected(78, opponent=ground)[2])[
        "choice.electric_paralysis_type_immune"] == 0  # Stun Spore is not electric


def test_prefix_identity_zero_damage_tail_and_no_new_oracle_inputs():
    obs, batch, view = projected()
    old = project_status_moves(obs, batch)
    prefix = tuple(r[:len(STATUS_MOVE_NAMES)] for r in view.candidate_vectors)
    assert prefix == old.candidate_vectors
    assert view.candidate_vectors[0][len(STATUS_MOVE_NAMES):] == (0.,)*len(COMPACT_STATUS_NAMES)
    changed = deepcopy(obs)
    changed["features"]["battle"].update({"enemy_stats": [999]*4, "rng": 234,
                                         "player_disable_turns": 7, "confusion_turns": 4})
    changed["features"]["world"] = {"map": "another-region"}
    assert project_balanced_status_moves(changed, batch) == view
    assert move_schema(BALANCED_STATUS_SCHEMA) == (BALANCED_STATUS_SCHEMA, BALANCED_STATUS_NAMES)


def test_v2_model_roundtrip_and_frozen_damage_selection_unchanged():
    frozen = fit_trainer_practice_three_heads([_target()], seed=3, epochs=1,
                                             require_corpus_floor=False)
    head = TrainerHeadModel(BALANCED_STATUS_SCHEMA, BALANCED_STATUS_NAMES,
                            np.zeros((len(BALANCED_STATUS_NAMES), 2)), np.zeros(2), np.ones(2), 4)
    candidate = replace(frozen, move=head, damage_reference=frozen.move)
    restored = TrainerPracticeThreeHeadModel.from_dict(candidate.to_dict())
    assert restored.to_dict() == candidate.to_dict()
    obs, batch, view = projected()
    assert project_for_head(obs, batch, head) == view
    assert status_choice_slots(view, (1, 3), frozen.move) == (1, 3)
    assert status_choice_slots(view, (1,), frozen.move) == (1,)
    assert frozen.move.schema_id == MOVE_SCHEMA_ID
    assert frozen.move.feature_names == MOVE_FEATURE_NAMES


def test_outcome_fit_rejects_heldout_and_cannot_fit_legacy_prefix():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from run_red_balanced_status_curriculum import fit_selector

    frozen = fit_trainer_practice_three_heads([_target()], seed=3, epochs=1,
                                             require_corpus_floor=False)
    _, _, view = projected()
    target = {"role": "holdout", "vectors": view.candidate_vectors, "returns": [0., 1.],
              "capture_id": "new-training-only-capture"}
    with pytest.raises(ValueError, match="withheld"):
        fit_selector([target], frozen)
    candidate, regrets = fit_selector([{**target, "role": "train"}], frozen)
    assert np.count_nonzero(candidate.move.weights1[:len(STATUS_MOVE_NAMES)]) == 0
    assert candidate.damage_reference.to_dict() == frozen.move.to_dict()
    assert regrets["candidate_regret"] < regrets["baseline_regret"]
