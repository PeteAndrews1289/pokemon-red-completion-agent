"""Numerical learning falsifiers; these fixtures are not native training data."""

import json
from dataclasses import replace

import numpy as np
import pytest
from test_red_live_option_menu import _binding, _no_ordinary_bindings, _situation

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.player_sequence_value import (
    FEATURE_WIDTH,
    SequenceRegressionRow,
    SequenceValueHead,
    fit_sequence_value,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.recorded_branch_history import RecordedBranchHistory
from pokemon_red_completion.red_live_option_menu import build_red_live_option_set
from pokemon_red_completion.red_player_story_menu import plural_story_bindings
from pokemon_red_completion.resource_economy_observation import EconomySnapshot

ZERO = RecordedBranchHistory(0, 0, 0, 0, 0, 0, 0, 0)
BEHAVIOR = "b" * 64
UTILITY = (1., 2., -.1, -.1, -.5, .5, 0.)


def row(i, x, y, *, targets=None):
    return SequenceRegressionRow(f"{i:064x}", (x,) + (0.,) * (FEATURE_WIDTH - 1),
                                 (y, y, 0., 0., 0., 0., None) if targets is None else targets,
                                 "train")


def fit(rows, **kwargs):
    return fit_sequence_value(rows, ridge=1., horizon=4, behavior_model_sha256=BEHAVIOR,
                              **kwargs)


def test_observed_continuation_changes_scores_without_zero_filling_unknown_losses():
    rows = tuple(row(i, x, y) for i, (x, y) in enumerate(((0., 0.), (.2, .2), (.8, .8), (1., 1.))))
    head = fit(rows)
    assert head.sample_counts == (4,) * 6 + (0,)
    predictions = tuple(head.predict(r.features) for r in rows)
    before = sum((r.targets[0] - .5) ** 2 for r in rows)
    after = sum((r.targets[0] - p[0]) ** 2 for r, p in zip(rows, predictions, strict=True))
    assert after < before / 10
    assert head.score(rows[-1].features, utility=UTILITY) > head.score(
        rows[0].features, utility=UTILITY,
    )
    assert all(p[-1] is None for p in predictions)
    with pytest.raises(ValueError, match="unlearned"):
        head.score(rows[0].features, utility=(*UTILITY[:-1], -1.))
    assert head.document()["native_admission_verified"] is False
    assert head.document()["live_policy_adopted"] is False


def test_censored_rows_never_change_channel_normalization_or_coefficients():
    rows = (row(0, 0., 0.), row(1, 1., 1.))
    head = fit(rows)
    censored = row(2, .8, 0., targets=(None,) * 7)
    with_censored = fit((*rows, censored))
    assert with_censored.parameters == head.parameters
    assert with_censored.sample_counts == head.sample_counts
    assert with_censored.dataset_sha256 != head.dataset_sha256


def test_identical_inputs_cannot_invent_a_branch_distinction():
    rows = (row(0, .5, 0.), row(1, .5, 1.))
    head = fit(rows)
    assert head.predict(rows[0].features)[0] == pytest.approx(.5)
    assert head.score(rows[0].features, utility=UTILITY) == head.score(
        rows[1].features, utility=UTILITY,
    )


def test_each_channel_uses_only_its_own_observed_labels():
    rows = (row(0, 0., 0., targets=(0., None, None, None, None, None, None)),
            row(1, 1., 0., targets=(1., None, None, None, None, None, None)),
            row(2, .5, 0., targets=(None, .4, None, None, None, None, None)),
            row(3, .8, 0., targets=(None, .4, None, None, None, None, None)))
    head = fit(rows)
    assert head.sample_counts == (2, 2, 0, 0, 0, 0, 0)
    assert head.parameters[0] == fit(rows[:2]).parameters[0]
    assert head.predict(rows[0].features)[1] == pytest.approx(.4)


def test_signed_level_gap_is_preserved_and_negative_target_is_not_accepted():
    rows = (row(0, -.5, .8), row(1, .5, .2))
    head = fit(rows)
    assert head.predict(rows[0].features)[0] > head.predict(rows[1].features)[0]
    with pytest.raises(ValueError):
        row(2, -.5, -.1)


def test_frozen_parameter_roundtrip_does_not_grant_native_admission():
    head = fit((row(0, 0., 0.), row(1, 1., 1.)))
    document = json.loads(json.dumps(head.document()))
    restored = SequenceValueHead.from_document(document, expected_sha256=head.model_sha256)
    assert restored == head
    document["native_admission_verified"] = True
    with pytest.raises(ValueError, match="contract"):
        SequenceValueHead.from_document(document, expected_sha256=canonical_sha256(document))
    with pytest.raises(ValueError, match="identity"):
        SequenceValueHead.from_document(document, expected_sha256=head.model_sha256)


@pytest.mark.parametrize("fault", ["development", "duplicate", "unknown", "one_label"])
def test_invalid_training_input_is_rejected(fault):
    rows = (row(0, 0., 0.), row(1, 1., 1.))
    if fault == "development":
        rows = (replace(rows[0], partition="development"), rows[1])
    elif fault == "duplicate":
        rows = (rows[0], rows[0])
    elif fault == "unknown":
        rows = tuple(replace(r, targets=(None,) * 7) for r in rows)
    else:
        rows = (rows[0], replace(rows[1], targets=(None,) * 7))
    with pytest.raises(ValueError):
        fit(rows)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), -1.1, 1.1])
def test_feature_and_target_bounds_are_strict(value):
    with pytest.raises(ValueError):
        row(0, value, .5)
    with pytest.raises(ValueError):
        row(0, .5, value)


def test_dual_ridge_matches_primal_centered_reference():
    rows = tuple(row(i, x, y) for i, (x, y) in enumerate(((0., .2), (.2, .8), (.8, .4), (1., .9))))
    head = fit(rows)
    x = np.asarray([r.features for r in rows])
    y = np.asarray([r.targets[0] for r in rows])
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale = np.where(scale < 1e-12, 1., scale)
    z = (x - mean) / scale
    weights = np.linalg.solve(z.T @ z + np.eye(FEATURE_WIDTH), z.T @ (y - y.mean())) / scale
    expected = (float(y.mean() - mean @ weights), *map(float, weights))
    assert head.parameters[0] == pytest.approx(expected, abs=1e-10)


def test_real_menu_features_history_and_permutation_use_same_learned_scores():
    calls = []
    bindings = tuple(_binding(GoalKind.ADVANCE_STORY, binding_ref=name, calls=calls)
                     for name in ("private-misty", "private-bill"))
    # Same immediate input; only measured prior history differentiates them.
    situation = _situation(resources=.1)
    ordinary, extras = plural_story_bindings(_no_ordinary_bindings(), bindings, situation)
    options = build_red_live_option_set(
        situation=situation,
        binding_set=ordinary, supplements=extras,
        model_feature_version=6, ordering_seed_sha256="a" * 64,
        economy_snapshot=EconomySnapshot(427, ()), target_cash=0,
    )
    menu = options.menu
    histories = (ZERO, RecordedBranchHistory(2, 100, 1000, 10, 0, 1, 0, 0))
    rows = tuple(SequenceRegressionRow(f"{i:064x}", c.vector(menu.context, feature_version=6)
                                     + h.vector(), (float(i),) + (0.,) * 5 + (None,), "train")
                 for i, (c, h) in enumerate(zip(menu.candidates, histories, strict=True)))
    head = fit(rows)
    scores = head.score_menu(menu, histories=histories, utility=UTILITY)
    assert scores[1] > scores[0]
    reverse = replace(menu, candidates=tuple(replace(c, binding_ref=f"renamed-{i}")
                                            for i, c in enumerate(reversed(menu.candidates))))
    assert head.score_menu(reverse, histories=tuple(reversed(histories)), utility=UTILITY) == (
        tuple(reversed(scores))
    )
    assert not calls and "private-misty" not in json.dumps(head.document())
