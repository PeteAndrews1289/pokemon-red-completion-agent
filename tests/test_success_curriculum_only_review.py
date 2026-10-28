"""New-only curriculum success updates retain inherited-head provenance.

Copy into Code/tests.  All evidence and models are existing synthetic fixtures.
No old observed-arm row is inserted just to make an otherwise empty choice
inventory acceptable, and no inherited sample count is added to the new corpus.
"""

from dataclasses import replace

import numpy as np
import pytest

import pokemon_red_completion.living_dex_option_value as m
from test_success_head_retention import parent, samples


def _new_curriculum():
    return tuple(m.LivingDexCurriculumOutcomeExample(
        row.decision_sha256, 'train', 9,
        row.menu.candidate_vector(row.selected_candidate_index, feature_version=9),
        row.outcome,
    ) for row in samples())


def _fit(base, curriculum):
    return m.fit_living_dex_option_value(
        (), feature_version=9, curriculum_examples=curriculum,
        frozen_success_base=base,
    )


def test_curriculum_only_success_update_has_exactly_its_new_corpus_denominator():
    base = parent()
    curriculum = _new_curriculum()
    result = _fit(base, curriculum)
    expected_digest = m.living_dex_option_train_dataset_sha256(
        (), curriculum_examples=curriculum)

    assert result.model.settled_examples == 6
    assert result.model.censored_examples == 0
    assert result.report.total_examples == result.report.settled_examples == 6
    assert result.report.successful_examples == 3
    assert result.model.train_dataset_sha256 == expected_digest
    assert result.report.train_dataset_sha256 == expected_digest
    assert result.report.public_dict()['frozen_parent_model_sha256'] == base.model_sha256
    assert result.model.objective == m.LIVING_DEX_SUCCESS_RESIDUAL_OBJECTIVE


def test_inherited_economy_evidence_count_does_not_expand_or_reject_new_success_corpus():
    initial = parent()
    economy = replace(initial.economy_head, qualified_examples=13)
    base = replace(initial, settled_examples=20, economy_head=economy)
    before = base.to_dict()
    result = _fit(base, _new_curriculum())
    model = result.model

    # These are two separately authenticated evidence inventories.  The success
    # update fitted six rows; the retained economy head still describes thirteen.
    assert model.settled_examples == 6
    assert result.report.total_examples == 6
    assert model.economy_head is economy
    assert model.economy_head.qualified_examples == 13
    assert model.economy_head.evidence_digest == economy.evidence_digest
    assert model.economy_head.to_dict() == economy.to_dict()
    assert base.to_dict() == before
    np.testing.assert_array_equal(model.feature_mean, base.feature_mean)
    np.testing.assert_array_equal(model.feature_scale, base.feature_scale)
    np.testing.assert_array_equal(model.coefficients[:, 1:], base.coefficients[:, 1:])
    np.testing.assert_array_equal(model.intercept[1:], base.intercept[1:])

    restored = m.LivingDexOptionValueModel.from_dict(model.to_dict())
    assert restored.model_sha256 == model.model_sha256
    assert restored.settled_examples == 6
    assert restored.economy_head.to_dict() == economy.to_dict()

    # The exception belongs to the explicit retained-head mode.  It must not
    # weaken the legacy same-corpus economy count contract.
    legacy_document = model.to_dict()
    legacy_document['objective'] = m.LIVING_DEX_OPTION_OBJECTIVE
    with pytest.raises(m.LivingDexOptionValueError):
        m.LivingDexOptionValueModel.from_dict(legacy_document)
    with pytest.raises(m.LivingDexOptionValueError):
        replace(model, objective=m.LIVING_DEX_OPTION_OBJECTIVE)


@pytest.mark.parametrize('case', ['empty', 'all_success', 'all_failure', 'duplicate'])
def test_invalid_curriculum_only_updates_refuse_before_optimizer(monkeypatch, case):
    curriculum = _new_curriculum()
    if case == 'empty':
        curriculum = ()
    elif case == 'duplicate':
        curriculum = (*curriculum, curriculum[0])
    else:
        curriculum = tuple(replace(row, outcome=replace(
            row.outcome, verified_success=(case == 'all_success')))
            for row in curriculum)
    monkeypatch.setattr(np.linalg, 'solve', lambda *a, **k: pytest.fail('optimizer ran'))
    with pytest.raises(m.LivingDexOptionValueError):
        _fit(parent(), curriculum)


def test_censored_curriculum_is_identity_only_not_an_extra_success_target():
    curriculum = _new_curriculum()
    censored = replace(curriculum[0], decision_sha256='f' * 64,
        outcome=m.LivingDexObservedOutcome(m.LivingDexOutcomeStatus.CENSORED,
            censor_reason=m.LivingDexCensorReason.EXTERNAL_INTERRUPTION))
    base = parent()
    one = _fit(base, curriculum)
    two = _fit(base, (*curriculum, censored))
    np.testing.assert_array_equal(one.model.coefficients, two.model.coefficients)
    np.testing.assert_array_equal(one.model.intercept, two.model.intercept)
    assert two.model.settled_examples == 6 and two.model.censored_examples == 1
    assert two.report.total_examples == 7
    assert two.model.train_dataset_sha256 != one.model.train_dataset_sha256
