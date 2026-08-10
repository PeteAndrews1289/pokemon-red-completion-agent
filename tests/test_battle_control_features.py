from __future__ import annotations

from copy import deepcopy

import pytest

from pokemon_red_completion.battle_actions import BattleAction, BattleBoostStat
from pokemon_red_completion.battle_control_features import (
    CONTROL_CLASS_REFS,
    CONTROL_FEATURE_NAMES,
    CONTROL_FEATURE_SCHEMA_ID,
    BattleControlFeatureError,
    BattleControlHistoryTracker,
    action_from_control_class_ref,
    control_class_ref,
    project_control_features,
)
from pokemon_red_completion.red_battle_catalog import (
    RED_BATTLE_CATALOG,
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)


def _observation() -> dict[str, object]:
    return {
        "features": {
            "progress": {"badge_count": 4},
            "party": {
                "count": 3,
                "active_index": 1,
                "lead": {
                    "species_ref": pokemon_red_species_ref(0x68),
                    "level": 40,
                    "hp": 25,
                    "max_hp": 100,
                    "hp_ratio": 0.25,
                    "status": "paralysis",
                },
                "members": [
                    {
                        "species_ref": pokemon_red_species_ref(0x1C),
                        "level": 42,
                        "hp": 100,
                        "max_hp": 100,
                        "hp_ratio": 1.0,
                        "status": None,
                        "moves": [
                            {
                                "slot_index": 0,
                                "move_ref": pokemon_red_move_ref(0x39),
                                "pp": 15,
                            }
                        ],
                    },
                    {
                        "species_ref": pokemon_red_species_ref(0x68),
                        "level": 40,
                        "hp": 25,
                        "max_hp": 100,
                        "hp_ratio": 0.25,
                        "status": "paralysis",
                        "moves": [
                            {
                                "slot_index": 0,
                                "move_ref": pokemon_red_move_ref(0x57),
                                "pp": 10,
                            }
                        ],
                    },
                    {
                        "species_ref": pokemon_red_species_ref(0x84),
                        "level": 38,
                        "hp": 0,
                        "max_hp": 100,
                        "hp_ratio": 0.0,
                        "status": None,
                        "moves": [
                            {
                                "slot_index": 0,
                                "move_ref": pokemon_red_move_ref(0x22),
                                "pp": 15,
                            }
                        ],
                    },
                ],
            },
            "resources": {
                "capture_item_count": 10,
                "healing_item_count": 4,
                "status_recovery_item_count": 2,
                "revive_item_count": 1,
                "accuracy_boost_count": 3,
                "attack_boost_count": 2,
                "special_boost_count": 1,
            },
            "battle": {
                "kind": "trainer",
                "opponent_species_ref": pokemon_red_species_ref(0x78),
                "opponent_level": 41,
                "opponent_hp_ratio": 0.5,
                "player_attack_stage": 2,
                "player_special_stage": 3,
                "player_accuracy_stage": -1,
                "opponent_defense_stage": 0,
                "player_disabled_move_slot": 3,
                "opponent_using_trapping_move": False,
            },
        }
    }


def test_control_projector_exposes_normalized_party_and_resource_state() -> None:
    vector = project_control_features(_observation(), catalog=RED_BATTLE_CATALOG)
    values = dict(zip(CONTROL_FEATURE_NAMES, vector, strict=True))

    assert vector.shape == (len(CONTROL_FEATURE_NAMES),)
    assert values["battle.is_trainer"] == 1.0
    assert values["player.hp_ratio"] == 0.25
    assert values["party.living_count"] == pytest.approx(2 / 6)
    assert values["party.fainted_count"] == pytest.approx(1 / 6)
    assert values["party.mean_level"] == pytest.approx(0.4)
    assert values["resources.healing_items"] == pytest.approx(0.2)
    assert values["progress.badge_count"] == 0.5
    assert CONTROL_FEATURE_SCHEMA_ID.endswith(".v4")
    assert values["party.reserve_matchup.available"] == 1.0
    assert values["party.reserve_matchup.candidate_count"] == pytest.approx(1 / 5)


def test_control_action_classes_drop_game_specific_targets() -> None:
    assert control_class_ref(BattleAction.move(4)) == CONTROL_CLASS_REFS[0]
    assert control_class_ref(BattleAction.switch(6)) == CONTROL_CLASS_REFS[5]
    assert control_class_ref(BattleAction.capture()) == CONTROL_CLASS_REFS[6]
    assert control_class_ref(BattleAction.flee()) == CONTROL_CLASS_REFS[7]
    assert (
        control_class_ref(BattleAction.boost(BattleBoostStat.SPECIAL))
        == "pokemon.core:battle:boost:special"
    )


def test_control_classes_expand_to_typed_actions() -> None:
    assert action_from_control_class_ref(CONTROL_CLASS_REFS[1]) == BattleAction.recovery()
    assert action_from_control_class_ref(CONTROL_CLASS_REFS[5]) == BattleAction.switch()
    assert action_from_control_class_ref(CONTROL_CLASS_REFS[6]) == BattleAction.capture()
    assert action_from_control_class_ref(CONTROL_CLASS_REFS[7]) == BattleAction.flee()
    with pytest.raises(BattleControlFeatureError):
        action_from_control_class_ref(CONTROL_CLASS_REFS[0])


def test_control_projector_rejects_missing_or_impossible_state() -> None:
    missing = deepcopy(_observation())
    del missing["features"]["resources"]  # type: ignore[index]
    with pytest.raises(BattleControlFeatureError):
        project_control_features(missing, catalog=RED_BATTLE_CATALOG)

    impossible = deepcopy(_observation())
    impossible["features"]["party"]["members"][0]["hp_ratio"] = 2.0  # type: ignore[index]
    with pytest.raises(BattleControlFeatureError):
        project_control_features(impossible, catalog=RED_BATTLE_CATALOG)


def test_control_projector_without_catalog_marks_matchup_unavailable() -> None:
    vector = project_control_features(_observation())
    values = dict(zip(CONTROL_FEATURE_NAMES, vector, strict=True))

    assert values["party.reserve_matchup.available"] == 0.0
    assert values["party.reserve_matchup.advantage.score"] == 0.0


def test_control_schema_contains_no_party_or_opponent_identity_shortcut() -> None:
    assert not any(
        token in name
        for name in CONTROL_FEATURE_NAMES
        for token in ("species", "move_ref", "party_slot", "opponent_id", "map")
    )


def test_control_history_tracks_causal_actions_and_opponent_changes() -> None:
    tracker = BattleControlHistoryTracker()
    observation = _observation()

    initial = tracker.before("battle-one", observation)
    tracker.advance(BattleAction.recovery(), observation)
    second = tracker.before("battle-one", observation)
    observation["features"]["battle"]["opponent_species_ref"] = (  # type: ignore[index]
        "pokemon:test:opponent-two"
    )
    next_opponent = tracker.before("battle-one", observation)

    assert initial.battle_turn == 0
    assert second.battle_turn == 1
    assert second.previous_class_index == 1
    assert second.action_counts[1] == 1
    assert next_opponent.opponent_index == 1
    assert next_opponent.opponent_turn == 0


def test_control_history_does_not_treat_opponent_healing_as_a_transition() -> None:
    tracker = BattleControlHistoryTracker()
    observation = _observation()
    observation["features"]["battle"]["opponent_hp_ratio"] = 0.2  # type: ignore[index]

    tracker.before("battle-one", observation)
    tracker.advance(BattleAction.move(1), observation)
    observation["features"]["battle"]["opponent_hp_ratio"] = 1.0  # type: ignore[index]
    healed = tracker.before("battle-one", observation)

    assert healed.battle_turn == 1
    assert healed.opponent_index == 0
    assert healed.opponent_turn == 1
