"""ROM-free checks for the outcome-fitted damage adapter and public projection."""

from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest
from test_red_trainer_practice_fit import _target

from pokemon_red_completion.red_damage_interaction_head import (
    FEATURE_NAMES,
    RIDGE,
    DamageInteractionHead,
    fit_damage_interaction_head,
    project_damage_interactions,
)
from pokemon_red_completion.red_status_battle_features import (
    STATUS_MOVE_NAMES,
    expand_frozen_move,
    status_choice_slots,
)
from pokemon_red_completion.red_trainer_practice_features import (
    MOVE_FEATURE_NAMES,
    TrainerCandidateFeatures,
)
from pokemon_red_completion.red_trainer_practice_fit import (
    TrainerPracticeThreeHeadModel,
    fit_trainer_practice_three_heads,
)

SHA = "a" * 64
AT = {name: MOVE_FEATURE_NAMES.index(name) for name in MOVE_FEATURE_NAMES}


def candidate(
    *,
    physical: bool,
    power: float = 0.2,
    accuracy: float = 1.0,
    burn=False,
    attack_stage=0,
    defense_stage=0,
    special_stage=0,
    accuracy_stage=0,
):
    row = [0.0] * len(MOVE_FEATURE_NAMES)
    row[AT["move.category.physical" if physical else "move.category.special"]] = 1.0
    row[AT["move.effective_power_fraction"]] = power
    row[
        AT[
            "interaction.physical_attack_over_estimated_defense"
            if physical
            else "interaction.special_over_estimated_special"
        ]
    ] = 0.25
    row[AT["move.accuracy"]] = accuracy
    row[AT["move.pp_fraction"]] = 0.5
    row[AT["state.player_hp_ratio"]] = 0.8
    row[AT["state.opponent_hp_ratio"]] = 1.0
    row[AT["interaction.player_speed_over_estimated_speed"]] = 0.2
    row[AT["state.player_attack_stage_fraction"]] = attack_stage / 6
    row[AT["state.opponent_defense_stage_fraction"]] = defense_stage / 6
    row[AT["observable.player.special_stage"]] = special_stage / 6
    row[AT["state.player_accuracy_stage_fraction"]] = accuracy_stage / 6
    row[AT["interaction.physical_x_player_burn"]] = float(physical and burn)
    return tuple(row)


def test_mechanics_pressure_reacts_to_immunity_stages_burn_and_accuracy():
    physical = candidate(physical=True)
    special = candidate(physical=False)
    features = project_damage_interactions((physical, special))
    assert features.shape == (2, len(FEATURE_NAMES))
    assert features[0, 0] > 0 and features[0, 1] == 0
    assert features[1, 1] > 0 and features[1, 0] == 0
    immune = project_damage_interactions((candidate(physical=False, power=0.0),))[0]
    assert immune[0] == immune[1] == immune[2] == immune[3] == 0
    burned = project_damage_interactions((candidate(physical=True, burn=True),))[0]
    assert burned[0] < features[0, 0]
    assert burned[0] / (1 - burned[0]) == pytest.approx(0.5 * features[0, 0] / (1 - features[0, 0]))
    assert (
        project_damage_interactions((candidate(physical=True, attack_stage=2),))[0, 0]
        > features[0, 0]
    )
    assert (
        project_damage_interactions((candidate(physical=True, defense_stage=2),))[0, 0]
        < features[0, 0]
    )
    assert (
        project_damage_interactions((candidate(physical=False, special_stage=2),))[0, 1]
        > features[1, 1]
    )
    low_accuracy = project_damage_interactions((candidate(physical=True, accuracy=0.5),))[0]
    assert low_accuracy[0] == features[0, 0] and low_accuracy[2] == pytest.approx(
        features[0, 2] / 2
    )
    assert (
        project_damage_interactions((candidate(physical=True, accuracy_stage=-2),))[0, 2]
        < features[0, 2]
    )


@pytest.mark.parametrize(
    "edit",
    [
        lambda r: r[:-1],
        lambda r: [float("nan"), *r[1:]],
        lambda r: [1.1, *r[1:]],
        lambda r: [*r[: AT["move.category.special"]], 1.0, *r[AT["move.category.special"] + 1 :]],
        lambda r: [
            *r[: AT["state.player_attack_stage_fraction"]],
            0.12,
            *r[AT["state.player_attack_stage_fraction"] + 1 :],
        ],
    ],
)
def test_projection_rejects_bad_public_rows(edit):
    with pytest.raises(ValueError):
        project_damage_interactions((edit(list(candidate(physical=True))),))


def test_one_fit_matches_independent_ridge_solve_and_can_reverse_category():
    examples = [
        (
            (
                candidate(physical=True, power=0.4),
                candidate(physical=False, power=0.05),
                candidate(physical=True, power=0.3),
                candidate(physical=False, power=0.1),
            ),
            (0.6, 0.1, 0.5, 0.15),
        ),
        (
            (
                candidate(physical=True, power=0.05),
                candidate(physical=False, power=0.5),
                candidate(physical=True, power=0.1),
                candidate(physical=False, power=0.4),
            ),
            (0.1, 0.7, 0.15, 0.6),
        ),
    ]
    head = fit_damage_interaction_head(examples, train_dataset_sha256=SHA)
    pairs, targets = [], []
    for vectors, values in examples:
        rows = project_damage_interactions(vectors)
        for i in range(4):
            for j in range(i + 1, 4):
                pairs.append(rows[i] - rows[j])
                targets.append(values[i] - values[j])
    x = np.vstack(pairs)
    expected = np.linalg.lstsq(
        np.vstack((x / np.sqrt(len(x)), np.sqrt(RIDGE) * np.eye(len(FEATURE_NAMES)))),
        np.concatenate((np.asarray(targets) / np.sqrt(len(x)), np.zeros(len(FEATURE_NAMES)))),
        rcond=None,
    )[0]
    np.testing.assert_allclose(head.coefficients, expected, atol=1e-10)
    assert head.predict_index(examples[0][0]) == 0
    assert head.predict_index(examples[1][0]) == 1
    assert head.to_dict() == DamageInteractionHead.from_dict(head.to_dict()).to_dict()
    assert sum(head.probabilities(examples[0][0])) == pytest.approx(1)


def test_strict_serialization_and_legacy_three_head_compatibility():
    target = _target()
    legacy = fit_trainer_practice_three_heads(
        [target], seed=9, require_corpus_floor=False, epochs=2
    )
    restored = TrainerPracticeThreeHeadModel.from_dict(legacy.to_dict())
    assert restored.to_dict() == legacy.to_dict()
    head = DamageInteractionHead(np.zeros(len(FEATURE_NAMES)), SHA)
    candidate_model = replace(legacy, move=expand_frozen_move(legacy.move), damage_reference=head)
    assert (
        TrainerPracticeThreeHeadModel.from_dict(candidate_model.to_dict()).to_dict()
        == candidate_model.to_dict()
    )
    bad = deepcopy(candidate_model.to_dict())
    bad["damage_reference"]["interaction_feature_names"].reverse()
    with pytest.raises(ValueError):
        DamageInteractionHead.from_dict(bad["damage_reference"])
    with pytest.raises(ValueError):
        TrainerPracticeThreeHeadModel.from_dict(bad)
    bad = head.to_dict()
    bad["nested_adapter"] = {}
    with pytest.raises(ValueError):
        DamageInteractionHead.from_dict(bad)


def test_status_shortlist_uses_interaction_head_and_slot_permutation():
    head = DamageInteractionHead(np.asarray((1.0, 1.0, 0.1, 0.1, 0.0, 0.0, 0.0, 0.0)), SHA)
    rows = (
        candidate(physical=True, power=0.1),
        candidate(physical=False, power=0.4),
        candidate(physical=True, power=0.3),
        candidate(physical=False, power=0.05),
    )
    padded = tuple(tuple(row) + (0.0,) * (len(STATUS_MOVE_NAMES) - len(row)) for row in rows)
    view = TrainerCandidateFeatures("status", STATUS_MOVE_NAMES, padded, (3, 1, 4, 2))
    assert status_choice_slots(view, (3, 1, 4, 2), head) == (1,)
    assert status_choice_slots(view, (4, 3), head) == (4,)


def test_rejects_ungated_ratio_and_out_of_range_damage_labels():
    malformed = list(candidate(physical=True))
    malformed[AT["interaction.special_over_estimated_special"]] = 0.1
    with pytest.raises(ValueError, match="category gated"):
        project_damage_interactions((malformed,))
    rows = (candidate(physical=True),) * 4
    with pytest.raises(ValueError, match="native returns"):
        fit_damage_interaction_head([(rows, (1.01, 0.0, 0.0, 0.0))], train_dataset_sha256=SHA)


def test_mixed_status_menu_keeps_status_choice_and_ranks_only_damage():
    head = DamageInteractionHead(np.ones(len(FEATURE_NAMES)), SHA)
    status = [0.0] * len(STATUS_MOVE_NAMES)
    status[AT["move.category.status"]] = 1.0
    damage = candidate(physical=True) + (0.0,) * (len(STATUS_MOVE_NAMES) - len(MOVE_FEATURE_NAMES))
    view = TrainerCandidateFeatures("status", STATUS_MOVE_NAMES, (tuple(status), damage), (2, 4))
    assert status_choice_slots(view, (2, 4), head) == (2, 4)


@pytest.mark.parametrize("field,value", [("format_version", True), ("coefficients", [False] * 8)])
def test_strict_loader_rejects_boolean_numeric_fields(field, value):
    document = DamageInteractionHead(np.zeros(8), SHA).to_dict()
    document[field] = value
    with pytest.raises(ValueError, match="serialized schema"):
        DamageInteractionHead.from_dict(document)
