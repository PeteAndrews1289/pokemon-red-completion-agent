import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_red_damage_ranking_diagnostic import ablate_type_identity, score_contributions

from pokemon_red_completion.red_trainer_practice_head import TrainerHeadModel


def head():
    return TrainerHeadModel(
        "test",
        (
            "move.type.normal",
            "move.type.electric",
            "move.type_effectiveness_fraction",
            "move.category.special",
        ),
        np.arange(12).reshape(4, 3) / 10,
        np.array([0.0, 0.2, -0.1]),
        np.array([1.0, -2.0, 3.0]),
        1,
    )


def test_ablation_preserves_mechanics_and_original():
    original = head()
    changed = ablate_type_identity(original)
    assert not changed.weights1[:2].any()
    np.testing.assert_array_equal(changed.weights1[2:], original.weights1[2:])
    np.testing.assert_array_equal(original.weights1, np.arange(12).reshape(4, 3) / 10)
    np.testing.assert_array_equal(changed.bias1, original.bias1)
    np.testing.assert_array_equal(changed.weights2, original.weights2)


@pytest.mark.parametrize("seed", range(5))
def test_attribution_sums_to_score_difference(seed):
    model = head()
    a, b = np.random.default_rng(seed).uniform(-1, 1, (2, 4))
    scores = model.scores((a, b))
    assert sum(score_contributions(model, a, b)) == pytest.approx(scores[0] - scores[1])


def test_identical_rows_have_zero_attribution():
    assert not score_contributions(head(), [0] * 4, [0] * 4).any()


def test_nonfinite_rejected():
    with pytest.raises(ValueError):
        score_contributions(head(), [float("nan")] * 4, [0] * 4)
