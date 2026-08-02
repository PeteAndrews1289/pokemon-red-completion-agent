from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from pokemon_red_completion.battle_dataset import (
    BattleDecisionExample,
    BattleEpisodeDataset,
)
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    BattleFeatureBatch,
    BattleMovePolicyContext,
)
from pokemon_red_completion.battle_training import (
    BattleTrainingConfig,
    BattleTrainingError,
    train_diagnostic_battle_ranker,
    train_preassigned_battle_ranker,
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


def _preassigned_dataset(partition: str, ordinal: int) -> BattleEpisodeDataset:
    diagnostic = _dataset()
    context = BattleMovePolicyContext(
        goal="win",
        move_policy="any_usable",
        required_move_ref=None,
    )
    episode_id = f"{partition}-{ordinal}"
    examples = tuple(
        BattleDecisionExample(
            decision_id=f"{episode_id}:decision:{index}",
            snapshot_sha256=_digest(f"{episode_id}:snapshot:{index}"),
            step_index=example.step_index,
            group_id=_digest(f"{episode_id}:group:{index}"),
            group_source="explicit_battle_instance",
            features=example.features,
            chosen_candidate_index=example.chosen_candidate_index,
            policy_goal_observed=True,
            policy_context=context,
        )
        for index, example in enumerate(diagnostic.examples)
    )
    return BattleEpisodeDataset(
        episode_id=episode_id,
        game_id=diagnostic.game_id,
        manifest_sha256=_digest(f"{episode_id}:manifest"),
        root_lineage_id=f"{episode_id}-root",
        partition=partition,
        regime="within_game",
        examples=examples,
        feature_names=diagnostic.feature_names,
        diagnostic_reasons=(),
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
    assert first.free_choice_decisions == 0
    assert first.forced_choice_decisions == 0
    assert first.unobserved_context_decisions == 20
    assert first.free_choice_accuracy is None
    assert first.forced_choice_accuracy is None
    assert "grouped_cross_validation_is_not_held_out" in first.reasons
    assert "single_recorded_root_lineage" in first.reasons
    assert sum(fold.test_decisions for fold in first.folds) == 20
    assert all(fold.train_groups == 16 and fold.test_groups == 4 for fold in first.folds)

    receipt = first.public_receipt()
    assert receipt["qualification"]["held_out_evaluation"] is False
    assert receipt["qualification"]["learned_policy_rollout"] is False
    assert receipt["model"]["serialization"] == "canonical_json"
    assert receipt["scope"]["source_root_lineages"] == 1
    assert receipt["scope"]["unobserved_context_decisions"] == 20


def test_preassigned_training_uses_train_and_validation_without_opening_test() -> None:
    train = tuple(_preassigned_dataset("train", index) for index in range(5))
    validation = tuple(
        _preassigned_dataset("validation", index) for index in range(2)
    )
    config = BattleTrainingConfig(seed=1289, folds=5, epochs=120)

    first = train_preassigned_battle_ranker(train, validation, config=config)
    second = train_preassigned_battle_ranker(train, validation, config=config)

    assert first.model.to_json() == second.model.to_json()
    assert first.model_sha256 == second.model_sha256
    assert first.train_episodes == first.train_root_lineages == 5
    assert first.validation_episodes == first.validation_root_lineages == 2
    assert first.train_decisions == 100
    assert first.validation_decisions == 40
    assert first.visible_snapshot_overlap_count == 0
    assert first.novel_visible_decisions == 40
    assert first.accuracy == first.free_choice_accuracy == 1.0
    assert first.accuracy > first.majority_accuracy
    assert first.cross_entropy < first.uniform_legal_cross_entropy
    assert first.legal_choice_rate == 1.0
    assert first.unobserved_context_decisions == 0
    assert first.confidence.eligible
    assert first.freeze_eligible
    assert first.reasons == ()

    receipt = first.public_receipt()
    assert receipt["schema"] == "battle-imitation-preassigned-validation-v1"
    assert receipt["training"]["split_unit"] == "preassigned_root_lineage"
    assert receipt["qualification"] == {
        "freeze_eligible": True,
        "held_out_validation": True,
        "test_partition_opened": False,
        "held_out_test_evaluation": False,
        "learned_policy_rollout": False,
        "promotion_eligible": False,
        "reasons": [],
    }


def test_preassigned_training_does_not_freeze_a_model_that_misses_validation() -> None:
    train = tuple(_preassigned_dataset("train", index) for index in range(5))
    validation = []
    for ordinal in range(2):
        dataset = _preassigned_dataset("validation", ordinal)
        validation.append(
            replace(
                dataset,
                examples=tuple(
                    replace(
                        example,
                        chosen_candidate_index=(example.chosen_candidate_index + 1) % 4,
                    )
                    for example in dataset.examples
                ),
            )
        )

    result = train_preassigned_battle_ranker(
        train,
        tuple(validation),
        config=BattleTrainingConfig(epochs=120),
    )

    assert result.accuracy == result.free_choice_accuracy == 0.0
    assert not result.confidence.eligible
    assert not result.freeze_eligible
    assert "validation_accuracy_not_above_majority" in result.reasons
    assert "validation_free_choice_not_above_majority" in result.reasons
    assert "validation_confidence_threshold_not_qualified" in result.reasons


@pytest.mark.parametrize(
    ("train", "validation", "message"),
    [
        ((), (_preassigned_dataset("validation", 0),), "requires train and validation"),
        (
            (_preassigned_dataset("test", 0),),
            (_preassigned_dataset("validation", 0),),
            "non-train episode",
        ),
        (
            (_preassigned_dataset("train", 0),),
            (_preassigned_dataset("test", 0),),
            "non-validation episode",
        ),
    ],
)
def test_preassigned_training_rejects_missing_or_wrong_partitions(
    train: tuple[BattleEpisodeDataset, ...],
    validation: tuple[BattleEpisodeDataset, ...],
    message: str,
) -> None:
    with pytest.raises(BattleTrainingError, match=message):
        train_preassigned_battle_ranker(train, validation)


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
