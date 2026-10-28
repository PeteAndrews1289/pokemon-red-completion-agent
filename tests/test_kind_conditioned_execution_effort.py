"""Projection contracts and synthetic learner checks, not cartridge evidence."""

import copy
from dataclasses import replace

import numpy as np
import pytest
from test_living_dex_goal_policy import _model, _question
from test_living_dex_option_value import _example, _menu, _settled

from pokemon_red_completion.living_dex_goal_policy import LivingDexGoalShadowPolicy
from pokemon_red_completion.living_dex_option_value import (
    LivingDexCurriculumOutcomeExample,
    LivingDexOptionKind,
    LivingDexOptionValueError,
    LivingDexOptionValueModel,
    curriculum_features,
    fit_living_dex_option_value,
    kind_execution_effort_feature_names,
    living_dex_option_train_dataset_sha256,
    option_feature_names,
    upgrade_option_value_model_for_kind_effort,
    upgrade_option_value_model_for_preparation,
)
from pokemon_red_completion.provenance import canonical_sha256


def candidate(kind, effort=.2):
    row = _menu().candidates[0]
    return replace(row, features=replace(row.features, kind=kind, execution_effort=effort))


CASES = [(kind, version) for kind in LivingDexOptionKind for version in range(1, 8)
         if kind is not LivingDexOptionKind.RESTORE or version >= 3]


@pytest.mark.parametrize('kind,version', CASES)
def test_old_rows_derive_only_known_products_without_rewriting_or_readiness(kind, version):
    row = candidate(kind)
    vector = row.vector(_menu().context, feature_version=version)
    example = LivingDexCurriculumOutcomeExample(
        'a' * 64, 'train', version, vector,
        _settled(success=True, completion=.1, unlock=0, action_cost=.2),
    )
    before = copy.deepcopy(example.public_dict())
    fingerprint = canonical_sha256(before)
    projected = curriculum_features(example, 8)
    assert projected[:len(vector)] == vector
    assert projected[len(vector):len(option_feature_names(7))] == (0.,) * (
        len(option_feature_names(7)) - len(vector))
    assert projected[-9:] == tuple(.2 if kind is k else 0. for k in LivingDexOptionKind)
    assert example.public_dict() == before and canonical_sha256(example.public_dict()) == fingerprint
    assert row.vector(_menu().context, feature_version=8)[:len(vector)] == vector
    assert projected[-9:] == row.vector(_menu().context, feature_version=8)[-9:]


@pytest.mark.parametrize('kind', list(LivingDexOptionKind))
@pytest.mark.parametrize('effort', [0., .1, 1.])
def test_zero_upgrade_preserves_old_predictions_and_model_bytes(kind, effort):
    old = upgrade_option_value_model_for_preparation(_model())
    before = copy.deepcopy(old.to_dict())
    new = upgrade_option_value_model_for_kind_effort(old)
    assert new.feature_version == 8 and new.settled_examples == old.settled_examples
    assert old.to_dict() == before and new.train_dataset_sha256 == old.train_dataset_sha256
    assert not np.any(new.coefficients[-9:])
    np.testing.assert_array_equal(new.coefficients[:-9], old.coefficients)
    row = candidate(kind, effort)
    np.testing.assert_allclose(new.predict_candidate(_menu().context, row).vector(),
                               old.predict_candidate(_menu().context, row).vector(), rtol=0, atol=1e-12)
    assert LivingDexOptionValueModel.from_dict(new.to_dict()).model_sha256 == new.model_sha256


def test_version8_products_roundtrip_and_do_not_add_identity_or_observation_fields():
    names = option_feature_names(8)
    assert names[:356] == option_feature_names(7) and len(names) == 365
    assert names[-9:] == kind_execution_effort_feature_names()
    assert not any(word in name for name in names[-9:] for word in ('species', 'route', 'seed', 'identity'))
    vector = candidate(LivingDexOptionKind.EVOLVE).vector(_menu().context, feature_version=8)
    row = LivingDexCurriculumOutcomeExample(
        'b' * 64, 'train', 8, vector,
        _settled(success=True, completion=.1, unlock=0, action_cost=.2),
    )
    assert curriculum_features(row, 8) == vector
    with pytest.raises(LivingDexOptionValueError):
        curriculum_features(row, 7)


@pytest.mark.parametrize('version', [True, 0, 16, '8'])
def test_unknown_versions_remain_rejected(version):
    with pytest.raises(LivingDexOptionValueError):
        option_feature_names(version)


def test_existing_learner_can_fit_different_kind_slopes_from_unchanged_synthetic_rows():
    rows = []
    for i, (kind, effort, target) in enumerate([
        (LivingDexOptionKind.ACQUIRE, .1, .1), (LivingDexOptionKind.ACQUIRE, .2, .2),
        (LivingDexOptionKind.EVOLVE, .1, .1), (LivingDexOptionKind.EVOLVE, .2, .4),
    ]):
        rows.append(LivingDexCurriculumOutcomeExample(
            f'{i + 1:064x}', 'train', 4,
            candidate(kind, effort).vector(_menu().context, feature_version=4),
            _settled(success=True, completion=.1, unlock=0, action_cost=target),
        ))
    before = [copy.deepcopy(row.public_dict()) for row in rows]
    # Keep the existing nonempty observed-evidence contract; curriculum is not
    # a substitute for an admitted selected-arm denominator.
    anchor = _example(99, selected=0, outcome=rows[0].outcome)
    anchor_menu = replace(_menu(), candidates=(
        candidate(LivingDexOptionKind.ACQUIRE, .1), _menu().candidates[1]))
    base = (replace(anchor, menu=anchor_menu, behavior_probabilities=(.5, .5)),)
    assert base[0].menu.candidate_vector(0, feature_version=8) == curriculum_features(rows[0], 8)
    assert base[0].outcome.public_dict() == rows[0].outcome.public_dict()
    old = fit_living_dex_option_value(base, feature_version=7, curriculum_examples=rows, ridge=1e-8)
    new = fit_living_dex_option_value(base, feature_version=8, curriculum_examples=rows, ridge=1e-8)
    assert new.report.weighted_mse_after < old.report.weighted_mse_after / 1000
    assert new.model.train_dataset_sha256 == old.model.train_dataset_sha256
    assert living_dex_option_train_dataset_sha256(base, curriculum_examples=rows) == old.model.train_dataset_sha256
    assert [row.public_dict() for row in rows] == before


def test_goal_policy_uses_version8_without_a_new_strategic_preference():
    old = upgrade_option_value_model_for_preparation(_model())
    new = upgrade_option_value_model_for_kind_effort(old)
    assert LivingDexGoalShadowPolicy(old).select(_question()).kind == LivingDexGoalShadowPolicy(new).select(_question()).kind
