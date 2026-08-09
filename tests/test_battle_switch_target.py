from __future__ import annotations

import numpy as np

from pokemon_red_completion.battle_switch_target import (
    SWITCH_TARGET_FEATURE_NAMES,
    BattleSwitchTargetCandidate,
    BattleSwitchTargetExample,
    BattleSwitchTargetSet,
    project_switch_target_candidates,
)
from pokemon_red_completion.battle_switch_target_model import (
    BattleSwitchTargetMLP,
    _plan_balanced_weights,
    evaluate_switch_target_model,
)
from pokemon_red_completion.red_battle_catalog import (
    RED_BATTLE_CATALOG,
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)


def _member(species_id: int, move_id: int, *, level: int = 50) -> dict[str, object]:
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
    return {
        "features": {
            "party": {
                "active_index": 0,
                "members": [
                    _member(0x1C, 0x39, level=60),
                    _member(0x68, 0x57),
                    _member(0x84, 0x22),
                ],
            },
            "battle": {
                "opponent_species_ref": pokemon_red_species_ref(0x78),
                "opponent_level": 54,
            },
        }
    }


def _candidate(value: float, slot: int) -> BattleSwitchTargetCandidate:
    return BattleSwitchTargetCandidate(
        party_slot=slot,
        features=(value, *(0.0 for _name in SWITCH_TARGET_FEATURE_NAMES[1:])),
    )


def _model() -> BattleSwitchTargetMLP:
    weights1 = np.zeros((len(SWITCH_TARGET_FEATURE_NAMES), 1))
    weights1[0, 0] = 1.0
    return BattleSwitchTargetMLP(
        weights1=weights1,
        bias1=np.zeros(1),
        weights2=np.ones(1),
        feature_mean=np.zeros(len(SWITCH_TARGET_FEATURE_NAMES)),
        feature_scale=np.ones(len(SWITCH_TARGET_FEATURE_NAMES)),
        training_seed=0,
    )


def test_projection_excludes_active_and_hides_party_identity() -> None:
    projected = project_switch_target_candidates(_observation(), RED_BATTLE_CATALOG)

    assert tuple(candidate.party_slot for candidate in projected.candidates) == (2, 3)
    assert all(
        len(candidate.features) == len(SWITCH_TARGET_FEATURE_NAMES)
        for candidate in projected.candidates
    )
    assert projected.candidates[0].features[5] > projected.candidates[1].features[5]


def test_projection_and_prediction_follow_reserve_permutation() -> None:
    original = project_switch_target_candidates(_observation(), RED_BATTLE_CATALOG)
    observation = _observation()
    members = observation["features"]["party"]["members"]  # type: ignore[index]
    observation["features"]["party"]["members"] = [  # type: ignore[index]
        members[0],
        members[2],
        members[1],
    ]
    permuted = project_switch_target_candidates(observation, RED_BATTLE_CATALOG)

    assert permuted.candidates[0].features == original.candidates[1].features
    assert permuted.candidates[1].features == original.candidates[0].features

    model = _model()
    synthetic = BattleSwitchTargetSet((_candidate(0.2, 2), _candidate(0.8, 3)))
    reversed_set = BattleSwitchTargetSet(tuple(reversed(synthetic.candidates)))
    assert model.predict_party_slot(synthetic) == 3
    assert model.predict_party_slot(reversed_set) == 3
    assert np.allclose(
        model.probabilities(reversed_set),
        model.probabilities(synthetic)[::-1],
    )


def test_small_ranker_fits_candidate_relative_choices_and_round_trips() -> None:
    examples = tuple(
        BattleSwitchTargetExample(
            observation=BattleSwitchTargetSet(
                (_candidate(0.1, 1), _candidate(0.9, 2), _candidate(0.4, 3))
            ),
            selected_candidate_index=1,
            battle_plan_id=f"battle-{index % 2}",
            decision_index=index + 1,
        )
        for index in range(20)
    )
    model = BattleSwitchTargetMLP.fit(
        examples,
        hidden_units=2,
        epochs=250,
        l2=0.001,
        seed=4,
    )
    restored = BattleSwitchTargetMLP.from_dict(model.to_dict())
    metrics = evaluate_switch_target_model(restored, examples)

    assert metrics.accuracy == 1.0
    assert restored.predict_party_slot(examples[0].observation) == 2
    assert dict(metrics.battle_plan_accuracy) == {"battle-0": 1.0, "battle-1": 1.0}


def test_plan_balanced_weights_prevent_long_trace_from_dominating() -> None:
    examples = tuple(
        BattleSwitchTargetExample(
            observation=BattleSwitchTargetSet((_candidate(0.1, 1), _candidate(0.9, 2))),
            selected_candidate_index=1,
            battle_plan_id="long-plan" if index < 3 else "short-plan",
            decision_index=index + 1,
        )
        for index in range(4)
    )

    weights = _plan_balanced_weights(examples)

    assert np.mean(weights) == 1.0
    assert np.sum(weights[:3]) == np.sum(weights[3:])
