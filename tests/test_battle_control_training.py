from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_control_labels import (
    BattleControlDataset,
    BattleControlLabel,
)
from pokemon_red_completion.battle_control_model import BattleControlModelError
from pokemon_red_completion.battle_control_training import (
    control_examples,
    evaluate_switch_target_resolution,
    fit_group_heldout_control_candidate,
)


def _observation() -> dict[str, object]:
    members = [
        {
            "species_ref": "pokemon.red.gb.us.rev0:species:177",
            "level": 40,
            "hp": 100,
            "max_hp": 100,
            "hp_ratio": 1.0,
            "status": None,
            "moves": [
                {
                    "slot_index": 0,
                    "move_ref": "pokemon.red.gb.us.rev0:move:033",
                    "pp": 20,
                }
            ],
        }
        for _index in range(1, 4)
    ]
    return {
        "schema_version": 1,
        "game_id": "pokemon.mainline:red:gb:us:rev0",
        "mode": "battle",
        "location": "pokemon.red.gb.us.rev0:area:route_20",
        "facts": ["pokemon.core:battle:active"],
        "features": {
            "progress": {"badge_count": 4},
            "party": {
                "count": 3,
                "active_index": 0,
                "lead": {
                    **members[0],
                    "moves": [
                        {
                            "slot_index": 0,
                            "move_ref": "pokemon.red.gb.us.rev0:move:033",
                            "pp": 20,
                        }
                    ],
                },
                "members": members,
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
                "active": True,
                "kind": "trainer",
                "opponent_species_ref": "pokemon.red.gb.us.rev0:species:022",
                "opponent_level": 41,
                "opponent_hp_ratio": 0.5,
                "player_attack_stage": 0,
                "player_special_stage": 0,
                "player_accuracy_stage": 0,
                "opponent_defense_stage": 0,
                "player_disabled_move_slot": None,
                "opponent_using_trapping_move": False,
            },
            "menu": {"kind": "battle_main", "selected_command_index": 0},
        }
    }


def _dataset() -> BattleControlDataset:
    labels: list[BattleControlLabel] = []
    for index in range(1, 41):
        observation = _observation()
        features = observation["features"]
        party = features["party"]  # type: ignore[index]
        lead = party["lead"]  # type: ignore[index]
        action = BattleAction.move(1) if index % 2 else BattleAction.recovery()
        lead["hp_ratio"] = 0.8 if action.move_slot is not None else 0.1  # type: ignore[index]
        labels.append(
            BattleControlLabel(
                decision_index=index,
                battle_plan_id="validation" if index > 32 else f"train-{index % 4}",
                objective_id="test",
                observation=observation,
                teacher_action=action,
            )
        )
    return BattleControlDataset(
        artifact_id="control-test",
        manifest_sha256="a" * 64,
        source_model_sha256="b" * 64,
        labels=tuple(labels),
        game_complete=True,
    )


def test_group_heldout_candidate_has_disjoint_battle_identity() -> None:
    dataset = _dataset()
    candidate = fit_group_heldout_control_candidate(
        dataset,
        validation_battle_plan_ids=("validation",),
        seed=2,
        epochs=150,
    )

    assert len(control_examples(dataset)) == 40
    assert candidate.training.examples == 32
    assert candidate.validation.examples == 8
    assert candidate.validation.accuracy >= 0.75
    assert candidate.training_switch_targets.examples == 0
    assert candidate.validation_switch_targets.examples == 0
    assert candidate.validation_battle_plan_ids == ("validation",)


def test_group_holdout_rejects_validation_only_class() -> None:
    dataset = _dataset()
    labels = list(dataset.labels)
    labels[-1] = replace(labels[-1], teacher_action=BattleAction.flee())
    with pytest.raises(BattleControlModelError, match="absent from training"):
        fit_group_heldout_control_candidate(
            replace(dataset, labels=tuple(labels)),
            validation_battle_plan_ids=("validation",),
        )


def test_switch_target_metric_requires_the_resolved_member_to_match() -> None:
    observation = _observation()
    correct = BattleControlLabel(
        decision_index=1,
        battle_plan_id="switch-test",
        objective_id="test",
        observation=observation,
        teacher_action=BattleAction.switch(2),
    )
    wrong = replace(correct, decision_index=2, teacher_action=BattleAction.switch(3))

    metrics = evaluate_switch_target_resolution((correct, wrong))

    assert metrics.examples == 2
    assert metrics.correct == 1
    assert metrics.accuracy == 0.5


def test_switch_target_metric_accepts_but_does_not_score_legacy_generic_switch() -> None:
    generic = BattleControlLabel(
        decision_index=1,
        battle_plan_id="switch-test",
        objective_id="test",
        observation=_observation(),
        teacher_action=BattleAction.switch(),
    )

    metrics = evaluate_switch_target_resolution((generic,))

    assert metrics.examples == 0
    assert metrics.correct == 0
    assert metrics.accuracy is None
