import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from run_red_trainer_terminal_curriculum import (
    MOVES,
    StatDamageTeacher,
    compatible_resume_declaration,
    curriculum_cases,
    hard_curriculum_cases,
    terminal_anchor_targets,
)
from test_red_trainer_practice_fit import _target

from pokemon_red_completion.battle_actions import BattleActionKind
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog


def test_terminal_recipes_preserve_sources_and_reserve_distinct_variations():
    templates = []
    for species in MOVES:
        other = [value for value in MOVES if value != species][:2]
        templates.append(
            {
                "actor_species_ref": f"pokemon.red.gb.us.rev0:species:{species:03d}",
                "actor_hp": 50,
                "root_lineage_id": f"root-{species}",
                "party_reserves": [
                    {
                        "party_slot": i + 2,
                        "species_ref": f"pokemon.red.gb.us.rev0:species:{value:03d}",
                    }
                    for i, value in enumerate(other)
                ],
            }
        )
    original = deepcopy(templates)
    train = curriculum_cases(templates)
    reserved = curriculum_cases(templates, reserved=True)
    assert templates == original
    assert len(train) == 16 and len(reserved) == 8
    for root, foe, recipe in reserved:
        training = next(p for r, f, p in train if r == root and f == foe)
        assert recipe["actor_moves"] == list(reversed(training["actor_moves"]))
        assert recipe["opponent_level"] != training["opponent_level"]
        assert recipe["root_lineage_id"] == training["root_lineage_id"]
        assert recipe["opponent_party_count"] == 2
        assert len(recipe["party_reserves"]) == 2


def test_training_teacher_scores_legal_attacks_and_declines_prompts():
    observation = _target()["observation"]
    batch = BattleFeatureProjector(PokemonRedBattleCatalog()).project(observation)
    teacher = StatDamageTeacher()
    action = teacher.choose_main(
        observation, SimpleNamespace(features=batch, supported_candidate_mask=(True, False))
    )
    assert action.kind is BattleActionKind.SELECT_MOVE
    assert action.move_slot == 1
    assert teacher.choose_switch(observation, (2, 3), forced=False, may_decline=True) is None
    assert teacher.choose_switch(observation, (2,), forced=True, may_decline=False) == 2
    assert (
        json.loads(json.dumps(teacher.last_decision_diagnostics))
        == teacher.last_decision_diagnostics
    )


def test_hard_recipes_use_five_members_and_distinct_reserved_conditions():
    templates = [
        {
            "actor_species_ref": f"pokemon.red.gb.us.rev0:species:{s:03d}",
            "opponent_hp": 80,
            "actor_stats": {"attack": 999},
            "opponent_stats": {"attack": 999},
            "root_lineage_id": f"root-{s}",
        }
        for s in MOVES
    ]
    before = deepcopy(templates)
    train = hard_curriculum_cases(templates)
    reserved = hard_curriculum_cases(templates, reserved=True)
    assert templates == before
    assert len(train) == 16 and len(reserved) == 8
    for root, _foe, recipe in train + reserved:
        assert len(recipe["party_reserves"]) == 4
        assert len(recipe["opponent_reserves"]) == 4
        assert recipe["opponent_party_count"] == 5
        assert "actor_stats" not in recipe and "opponent_stats" not in recipe
        assert recipe["opponent_hp"] in (53, 55)
        assert recipe["root_lineage_id"] == templates[root]["root_lineage_id"]
        assert (
            len(
                {recipe["actor_species_ref"], *(m["species_ref"] for m in recipe["party_reserves"])}
            )
            == 5
        )
    for root, foe, recipe in reserved:
        training = next(p for r, f, p in train if r == root and f == foe)
        assert recipe["actor_moves"] == list(reversed(training["actor_moves"]))
        assert recipe["opponent_level"] != training["opponent_level"]
        assert recipe["actor_hp"] != training["actor_hp"]


def test_resume_keeps_experiment_fixed_while_retaining_prior_model_examples():
    previous = {
        "source_commit": "old",
        "continuation_code_sha256": "old",
        "epochs": 1200,
        "frozen_model": {"sha256": "same"},
        "training_recipes": ["fixed"],
    }
    current = {**previous, "source_commit": "new", "retained_terminal_anchor_ids": ["prior"]}
    assert compatible_resume_declaration(previous, current)
    assert not compatible_resume_declaration(previous, {**current, "epochs": 2400})
    assert not compatible_resume_declaration(previous, {**current, "training_recipes": ["new"]})
    assert not compatible_resume_declaration(
        current, {**current, "retained_terminal_anchor_ids": []}
    )
    assert not compatible_resume_declaration(
        previous, {**current, "frozen_model": {"sha256": "other"}}
    )


def test_terminal_anchors_fail_closed_when_a_prior_example_is_missing(tmp_path):
    with pytest.raises(ValueError, match="anchors are missing"):
        terminal_anchor_targets(tmp_path / "model.json", {"missing"})
