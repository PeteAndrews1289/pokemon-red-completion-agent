from __future__ import annotations

from copy import deepcopy

from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_trainer_practice_features import (
    MOVE_SCHEMA_ID,
    project_trainer_move_features,
    project_trainer_switch_features,
)


def _observation():
    def member(slot, species, stats):
        return {
            "party_index": slot, "species_ref": f"pokemon.red.gb.us.rev0:species:{species:03d}",
            "level": 32, "hp": 60, "max_hp": 70, "hp_ratio": 60 / 70,
            "status": None, "stats": dict(zip(
                ("attack", "defense", "speed", "special"), stats, strict=True,
            )),
            "moves": [{"slot_index": 0, "move_ref": "pokemon.red.gb.us.rev0:move:033", "pp": 20}],
        }
    members = [
        member(0, 84, (45, 29, 67, 42)),
        member(1, 177, (40, 54, 40, 50)),
        member(2, 28, (55, 50, 68, 40)),
    ]
    return {
        "mode": "battle", "features": {
            "menu": {"kind": "battle_main"},
            "party": {"count": 3, "active_index": 0, "lead": members[0], "members": members},
            "battle": {
                "active": True, "kind": "trainer",
                "opponent_species_ref": "pokemon.red.gb.us.rev0:species:177",
                "opponent_level": 32, "opponent_hp_ratio": 0.8,
                "opponent_public_base_stats": {
                    "hp": 44, "attack": 48, "defense": 65, "speed": 43, "special": 50,
                },
                "opponent_status": None,
                "player_attack_stage": 0, "player_special_stage": 0,
                "player_accuracy_stage": 0, "opponent_defense_stage": 0,
                "player_disabled_move_slot": None,
                "opponent_using_trapping_move": False,
            },
            "resources": {
                "healing_item_count": 0, "status_recovery_item_count": 0,
                "revive_item_count": 0, "accuracy_boost_count": 0,
                "attack_boost_count": 0, "special_boost_count": 0,
            },
            "progress": {"badge_count": 0},
        },
    }


def test_move_stat_features_separate_same_level_moveset_species():
    catalog = PokemonRedBattleCatalog()
    first = _observation()
    legacy = BattleFeatureProjector(catalog).project(first)
    richer = project_trainer_move_features(first, legacy)
    changed = deepcopy(first)
    changed["features"]["party"]["lead"]["stats"]["attack"] = 90
    changed["features"]["party"]["members"][0]["stats"]["attack"] = 90
    old_changed = BattleFeatureProjector(catalog).project(changed)
    rich_changed = project_trainer_move_features(changed, old_changed)
    assert legacy.candidate_vectors == old_changed.candidate_vectors
    assert richer.schema_id == MOVE_SCHEMA_ID
    assert richer.candidate_vectors != rich_changed.candidate_vectors


def test_switch_stat_features_follow_candidate_not_party_slot():
    catalog = PokemonRedBattleCatalog()
    first = _observation()
    initial = project_trainer_switch_features(first, catalog)
    swapped = deepcopy(first)
    members = swapped["features"]["party"]["members"]
    members[1], members[2] = members[2], members[1]
    members[1]["party_index"], members[2]["party_index"] = 1, 2
    revised = project_trainer_switch_features(swapped, catalog)
    assert initial.candidate_vectors == tuple(reversed(revised.candidate_vectors))
    assert initial.candidate_slots == revised.candidate_slots == (2, 3)
