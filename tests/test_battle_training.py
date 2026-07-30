from __future__ import annotations

import hashlib

import pytest

from pokemon_red_completion.battle_dataset import (
    BattleDecisionExample,
    BattleEpisodeDataset,
)
from pokemon_red_completion.battle_semantics import FEATURE_NAMES, BattleFeatureBatch
from pokemon_red_completion.battle_training import (
    BattleTrainingConfig,
    BattleTrainingError,
    train_diagnostic_battle_ranker,
)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _dataset() -> BattleEpisodeDataset:
    signal_index = FEATURE_NAMES.index("move.effective_power_fraction")
    examples: list[BattleDecisionExample] = []
    for example_index in range(20):
        chosen = example_index % 4
        vectors: list[tuple[float, ...]] = []
        for candidate_index in range(4):
            vector = [0.0] * len(FEATURE_NAMES)
            vector[signal_index] = float(candidate_index == chosen)
            vectors.append(tuple(vector))
        batch = BattleFeatureBatch(
            feature_names=FEATURE_NAMES,
            candidate_vectors=tuple(vectors),
            legal_mask=(True, True, True, True),
            current_pp=(10.0, 10.0, 10.0, 10.0),
            slot_indices=(0, 1, 2, 3),
        )
        examples.append(
            BattleDecisionExample(
                decision_id=f"episode:decision:{example_index}",
                snapshot_sha256=_digest(f"snapshot-{example_index}"),
                step_index=example_index,
                group_id=_digest(f"group-{example_index}"),
                group_source="diagnostic_area_position",
                features=batch,
                chosen_candidate_index=chosen,
                policy_goal_observed=False,
            )
        )
    return BattleEpisodeDataset(
        episode_id="episode",
        game_id="pokemon.mainline:red",
        manifest_sha256="a" * 64,
        root_lineage_id="episode",
        partition="unassigned",
        regime="within_game",
        examples=tuple(examples),
        feature_names=FEATURE_NAMES,
        diagnostic_reasons=("unassigned_root_lineage",),
    )


def test_diagnostic_training_is_deterministic_grouped_and_never_promotable() -> None:
    config = BattleTrainingConfig(seed=1289, folds=5, epochs=80)

    first = train_diagnostic_battle_ranker(_dataset(), config=config)
    second = train_diagnostic_battle_ranker(_dataset(), config=config)

    assert first.model.to_json() == second.model.to_json()
    assert first.model_sha256 == second.model_sha256
    assert first.accuracy == 1.0
    assert first.training_accuracy == 1.0
    assert first.legal_choice_rate == 1.0
    assert first.accuracy > first.majority_accuracy
    assert first.promotion_eligible is False
    assert "grouped_cross_validation_is_not_held_out" in first.reasons
    assert "single_recorded_root_lineage" in first.reasons
    assert sum(fold.test_decisions for fold in first.folds) == 20
    assert all(fold.train_groups == 16 and fold.test_groups == 4 for fold in first.folds)

    receipt = first.public_receipt()
    assert receipt["qualification"]["held_out_evaluation"] is False
    assert receipt["qualification"]["learned_policy_rollout"] is False
    assert receipt["model"]["serialization"] == "canonical_json"
    assert receipt["scope"]["source_root_lineages"] == 1


@pytest.mark.parametrize(
    "arguments",
    [
        {"seed": -1},
        {"folds": 1},
        {"epochs": 0},
        {"learning_rate": 0.0},
        {"learning_rate": float("nan")},
        {"l2": -1.0},
    ],
)
def test_training_configuration_rejects_invalid_values(
    arguments: dict[str, object],
) -> None:
    with pytest.raises(BattleTrainingError):
        BattleTrainingConfig(**arguments)
