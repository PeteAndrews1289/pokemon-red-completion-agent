"""Proposed ROM-free V16 movement decoding/parity regression; Root executes it."""
from dataclasses import replace
import numpy as np
import pytest
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionAvailability, LivingDexOptionCandidate, LivingDexOptionContext,
    LivingDexOptionFeatures, LivingDexOptionKind, LivingDexOptionValueModel,
    option_feature_names, upgrade_option_value_model_for_story_unit,
)
from pokemon_red_completion.player_option_story_unit import OptionStoryUnit


@pytest.mark.parametrize("further", [False, True])
def test_movement_story_scope_numpy_vector_and_matrix_preserve_v15_outputs(further):
    names = option_feature_names(15)
    width = len(names)
    coefficients = np.zeros((width, 9), dtype=np.float64)
    coefficients[names.index("execution_effort")] = np.arange(9, dtype=np.float64) / 37
    original = LivingDexOptionValueModel(
        coefficients=coefficients,
        intercept=np.arange(9, dtype=np.float64) / 10,
        feature_mean=np.zeros(width, dtype=np.float64),
        feature_scale=np.ones(width, dtype=np.float64),
        train_dataset_sha256="a" * 64,
        settled_examples=2, censored_examples=0,
        ridge=.25, maximum_importance_weight=1., feature_version=15,
    )
    extended = upgrade_option_value_model_for_story_unit(original)
    old = LivingDexOptionCandidate(
        "test:ordinary-story",
        LivingDexOptionFeatures(LivingDexOptionKind.UNLOCK_ACCESS,
            0., .5, 0., .02, 0., 0., .15, 0., 0.),
        LivingDexOptionAvailability.AVAILABLE,
    )
    context = LivingDexOptionContext(.1, .2, .3, .4, .5, .6, .7)
    movement = replace(old, story_unit=OptionStoryUnit("movement", further))
    legacy = np.asarray(old.vector(context, feature_version=15), dtype=np.float64)
    vector = np.asarray(movement.vector(context, feature_version=16), dtype=np.float64)
    unknown = np.asarray(old.vector(context, feature_version=16), dtype=np.float64)
    assert vector.dtype == np.float64
    assert vector[-4:].tolist() == [1., 1., 0., float(further)]
    np.testing.assert_array_equal(vector[:-4], legacy)
    np.testing.assert_array_equal(unknown[:-4], legacy)
    # This calls the real NumPy scalar decoder path that previously rejected np.float64.
    np.testing.assert_array_equal(extended.raw_predictions(vector), original.raw_predictions(legacy))
    # The matrix path must decode each known/unknown row without dropping its type.
    actual = extended.raw_predictions(np.stack((vector, unknown)))
    expected = original.raw_predictions(np.stack((legacy, legacy)))
    np.testing.assert_array_equal(actual, expected)
    assert getattr(extended, "movement_success_head", None) is None
