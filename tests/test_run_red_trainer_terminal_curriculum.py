from copy import deepcopy
from types import SimpleNamespace

from run_red_trainer_terminal_curriculum import MOVES, StatDamageTeacher, curriculum_cases
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
