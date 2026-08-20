from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_control_labels import (
    BattleControlDataset,
    BattleControlLabel,
)
from pokemon_red_completion.battle_switch_target_model import BattleSwitchTargetModelError
from pokemon_red_completion.battle_switch_target_training import (
    evaluate_deterministic_switch_target_baseline,
    fit_preassigned_switch_target_candidate,
    switch_target_examples,
)
from pokemon_red_completion.red_battle_catalog import (
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)


def _member(species_id: int, move_id: int, *, level: int) -> dict[str, object]:
    return {
        "species_ref": pokemon_red_species_ref(species_id),
        "level": level,
        "hp": 100,
        "max_hp": 100,
        "hp_ratio": 1.0,
        "status": None,
        "moves": [
            {
                "slot_index": 0,
                "move_ref": pokemon_red_move_ref(move_id),
                "pp": 10,
            }
        ],
    }


def _observation() -> dict[str, object]:
    members = [
        _member(0x1C, 0x39, level=60),
        _member(0x68, 0x57, level=50),
        _member(0x84, 0x22, level=50),
    ]
    return {
        "schema_version": 1,
        "game_id": "pokemon.mainline:red:gb:us:rev0",
        "mode": "battle",
        "location": "pokemon.red.gb.us.rev0:area:route_20",
        "facts": ["pokemon.core:battle:active"],
        "features": {
            "party": {
                "active_index": 0,
                "lead": members[0],
                "members": members,
            },
            "battle": {
                "opponent_species_ref": pokemon_red_species_ref(0x78),
                "opponent_level": 54,
            },
        },
    }


def _dataset(artifact_id: str, manifest: str, plan: str) -> BattleControlDataset:
    return BattleControlDataset(
        artifact_id=artifact_id,
        manifest_sha256=manifest,
        source_model_sha256="c" * 64,
        labels=tuple(
            BattleControlLabel(
                decision_index=index,
                battle_plan_id=plan,
                objective_id="portable-switch-test",
                observation=_observation(),
                teacher_action=BattleAction.switch(2),
            )
            for index in range(1, 9)
        ),
        game_complete=True,
    )


def test_preassigned_candidate_reports_model_and_deployed_baseline_separately() -> None:
    training = _dataset("switch-train", "a" * 64, "train-battle")
    validation = _dataset("switch-validation", "b" * 64, "validation-battle")

    candidate = fit_preassigned_switch_target_candidate(
        (training,),
        (validation,),
        epochs=250,
        l2=0.001,
        seed=3,
    )
    summary = candidate.public_summary()

    assert len(switch_target_examples((training,))) == 8
    assert candidate.training.accuracy == 1.0
    assert candidate.validation.accuracy == 1.0
    assert candidate.validation_baseline.accuracy == 1.0
    assert summary["deployment_authority"] is False
    assert summary["training_artifact_ids"] == ["switch-train"]
    assert summary["validation_artifact_ids"] == ["switch-validation"]


def test_lineage_split_rejects_overlap_and_different_source_models() -> None:
    training = _dataset("switch-train", "a" * 64, "train-battle")
    validation = _dataset("switch-validation", "b" * 64, "validation-battle")

    with pytest.raises(BattleSwitchTargetModelError, match="disjoint"):
        fit_preassigned_switch_target_candidate((training,), (training,), epochs=1)
    with pytest.raises(BattleSwitchTargetModelError, match="different move models"):
        fit_preassigned_switch_target_candidate(
            (training,),
            (replace(validation, source_model_sha256="d" * 64),),
            epochs=1,
        )


def test_baseline_requires_explicit_switch_targets() -> None:
    dataset = _dataset("switch-train", "a" * 64, "train-battle")
    labels = tuple(
        replace(label, teacher_action=BattleAction.move(1)) for label in dataset.labels
    )

    with pytest.raises(BattleSwitchTargetModelError, match="no explicit labels"):
        evaluate_deterministic_switch_target_baseline((replace(dataset, labels=labels),))
