from __future__ import annotations

from copy import deepcopy

import pytest

from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_trainer_practice_features import (
    MOVE_SCHEMA_ID,
    TrainerStatFeatureError,
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


def _six_party_observation(*, active_slot: int = 1, living_slots=range(1, 7)):
    observation = _observation()
    members = []
    for index in range(6):
        slot = index + 1
        members.append(
            {
                "party_index": index,
                "species_ref": f"pokemon.red.gb.us.rev0:species:{slot + 20:03d}",
                "level": 25 + slot,
                "hp": 40 + slot if slot in living_slots else 0,
                "max_hp": 60 + slot,
                "hp_ratio": (40 + slot) / (60 + slot) if slot in living_slots else 0.0,
                "status": None,
                "stats": {
                    "attack": 30 + slot,
                    "defense": 40 + slot,
                    "speed": 50 + slot,
                    "special": 60 + slot,
                },
                "moves": [
                    {
                        "slot_index": 0,
                        "move_ref": "pokemon.red.gb.us.rev0:move:033",
                        "pp": 10 + slot,
                    }
                ],
            }
        )
    party = observation["features"]["party"]
    party.update(
        count=6,
        active_index=active_slot - 1,
        lead=deepcopy(members[active_slot - 1]),
        members=members,
    )
    return observation


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


@pytest.mark.parametrize("active_slot", range(1, 7))
def test_six_party_projection_retains_every_living_non_active_slot(active_slot):
    projected = project_trainer_switch_features(
        _six_party_observation(active_slot=active_slot), PokemonRedBattleCatalog()
    )
    assert projected.candidate_slots == tuple(
        slot for slot in range(1, 7) if slot != active_slot
    )
    assert len(projected.candidate_vectors) == 5


@pytest.mark.parametrize("target_slot", (4, 5, 6))
def test_six_party_projection_keeps_the_only_living_late_reserve(target_slot):
    projected = project_trainer_switch_features(
        _six_party_observation(active_slot=1, living_slots={1, target_slot}),
        PokemonRedBattleCatalog(),
    )
    assert projected.candidate_slots == (target_slot,)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda party: party.update(count=5), "party count"),
        (lambda party: party.update(active_index=6), "active index"),
        (lambda party: party["members"].pop(), "party count"),
        (lambda party: party["members"][3].update(party_index=2), "party index"),
    ),
)
def test_trainer_projection_rejects_malformed_party_arrays(mutation, message):
    observation = _six_party_observation()
    mutation(observation["features"]["party"])
    with pytest.raises(TrainerStatFeatureError, match=message):
        project_trainer_switch_features(observation, PokemonRedBattleCatalog())
