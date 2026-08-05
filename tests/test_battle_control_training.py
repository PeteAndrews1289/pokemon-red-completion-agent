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
    fit_group_heldout_control_candidate,
)
from tests.test_battle_control_features import _observation


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
