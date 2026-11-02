from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest
from test_red_status_readout_learning import problem_inputs

from pokemon_red_completion.red_balanced_status_features import (
    BALANCED_STATUS_NAMES as N,
)
from pokemon_red_completion.red_balanced_status_features import COMPACT_STATUS_NAMES as C
from pokemon_red_completion.red_effect_selector_head import (
    EffectSelectorHead,
    augment_head,
    effect_values,
)
from pokemon_red_completion.red_effect_selector_learning import (
    fit_combination,
    prepare_combination,
)
from pokemon_red_completion.red_status_win_conditioned_returns import RETURN_SCHEMA
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadError, TrainerHeadModel


def effect():
    w = np.zeros(1+len(C))
    w[0] = 2.
    w[1+C.index("choice.heal_full_hp")] = -4.
    return {"weights": w.tolist()}


def candidates():
    rows = np.zeros((5, len(N)))
    rows[0:2, N.index("choice.effect.heal")] = 1.
    rows[1, N.index("choice.heal_full_hp")] = 1.
    rows[2, N.index("choice.effect.disable")] = 1.
    rows[3, N.index("choice.effect.sleep")] = 1.
    return rows.tolist()


def test_only_declared_effects_get_auxiliary_values_without_bans():
    rows = candidates()
    values = effect_values(rows, effect()["weights"])
    assert values[:, 0].tolist() == [1., 1., 0., 0., 0.]
    assert values[0, 1] > .8 and values[1, 1] < .2
    assert not values[2:].any()
    # Conditional prediction is not changed into an execution predictor when asleep.
    rows[0][N.index("choice.player_asleep")] = 1.
    assert effect_values(rows, effect()["weights"])[0, 1] == values[0, 1]


def test_zero_start_and_serialized_model_keep_exact_scores_and_legal_candidates():
    frozen, initial, _ = problem_inputs()
    head = augment_head(initial.move, effect()["weights"], "a"*64)
    rows = candidates()
    assert np.array_equal(head.scores(rows), initial.move.scores(rows))
    head = replace(head, effect_readout=(-.4, 1.3))
    actor = replace(initial, move=head, damage_reference=frozen.move)
    data = actor.to_dict()
    assert data["move"]["format_version"] == 2
    restored = TrainerPracticeThreeHeadModel.from_dict(data)
    assert isinstance(restored.move, EffectSelectorHead)
    assert restored.to_dict() == data
    assert np.array_equal(restored.move.scores(rows), head.scores(rows))
    assert np.isfinite(restored.move.probabilities(rows)).all()
    assert len(restored.move.probabilities(rows)) == 5
    assert np.array_equal(head.scores(rows)[2:], initial.move.scores(rows)[2:])


@pytest.mark.parametrize("change", ["version", "drop", "family", "conditional", "weights", "sha"])
def test_checkpoint_cannot_silently_drop_or_reinterpret_effect_component(change):
    _, initial, _ = problem_inputs()
    data = augment_head(initial.move, effect()["weights"], "a"*64).to_dict()
    if change == "version":
        data["format_version"] = 1
    elif change == "drop":
        del data["auxiliary_effect"]
    elif change == "family":
        data["auxiliary_effect"]["families"].append("disable")
    elif change == "conditional":
        data["auxiliary_effect"]["conditional_on_execution"] = False
    elif change == "weights":
        data["auxiliary_effect"]["weights"][0] = float("nan")
    else:
        data["auxiliary_effect"]["source_fit_sha256"] = "invalid"
    with pytest.raises(TrainerHeadError):
        TrainerHeadModel.from_dict(data, schema_id=initial.move.schema_id,
                                   feature_names=initial.move.feature_names)


def test_combined_fit_preserves_constraints_and_frozen_subcomponents():
    frozen, initial, old = problem_inputs()
    for group in old:
        group[0]["vectors"][1][N.index("choice.effect.heal")] = 1.
    old[0][0]["vectors"][1][N.index("choice.heal_full_hp")] = 1.
    revised = deepcopy(old)
    for g in revised:
        g[0]["return_schema"] = RETURN_SCHEMA
    p = prepare_combination(revised, initial, frozen, initial, old, effect())
    assert len(p.anchor) == initial.move.weights2.size + 2
    assert p.anchor[-2:].tolist() == [0., 0.]
    eps = 1e-6
    x = p.anchor + .1
    gradient = [(p.objective(x+eps*e)[0]-p.objective(x-eps*e)[0])/(2*eps)
                for e in np.eye(len(x))]
    assert p.objective(x)[1] == pytest.approx(gradient, abs=1e-8)
    candidate, report = fit_combination(revised, initial, frozen, initial, old, effect(), "a"*64)
    assert report["solver_success"] and report["retention_regressions"] == 0
    assert report["protected_preferences"] == 1
    assert candidate.move.predict_index(old[0][0]["vectors"]) == 0
    assert candidate.move.effect_weights == tuple(effect()["weights"])
    assert candidate.control.to_dict() == initial.control.to_dict()
    assert candidate.switch.to_dict() == initial.switch.to_dict()
    assert np.array_equal(candidate.move.weights1, initial.move.weights1)


def test_invalid_family_flags_and_nested_augmentation_rejected():
    rows = candidates()
    rows[0][N.index("choice.effect.rest")] = 1.
    with pytest.raises(TrainerHeadError):
        effect_values(rows, effect()["weights"])
    _, initial, _ = problem_inputs()
    head = augment_head(initial.move, effect()["weights"], "a"*64)
    with pytest.raises(TrainerHeadError, match="stack"):
        augment_head(head, effect()["weights"], "a"*64)
