"""Portable workload/compatibility contracts, not native or learned-gain claims."""

import copy
from dataclasses import replace

import numpy as np
import pytest
from test_living_dex_goal_policy import _model
from test_living_dex_option_value import _menu, _settled

from pokemon_red_completion.living_dex_option_value import (
    LivingDexCurriculumOutcomeExample,
    LivingDexOptionKind,
    LivingDexOptionValueError,
    LivingDexOptionValueModel,
    curriculum_features,
    option_feature_names,
    upgrade_option_value_model_for_kind_effort,
    upgrade_option_value_model_for_level_workload,
)
from pokemon_red_completion.living_dex_policy_codec import (
    LivingDexPolicyCodecError,
    restore_living_dex_policy_menu,
)
from pokemon_red_completion.player_option_level_workload import OptionLevelWorkload
from pokemon_red_completion.provenance import canonical_sha256


def candidate(workload=None):
    base = _menu().candidates[0]
    return replace(base, features=replace(base.features, kind=LivingDexOptionKind.EVOLVE,
                                         execution_effort=8 / 99), level_workload=workload)


def test_three_real_workload_facts_no_longer_alias_but_keep_exact_old_prefix():
    # These prospective measurements come from the separate zero-input native
    # check; these assertions test representation, not completion cost labels.
    workloads = [OptionLevelWorkload(28, 36, 22765), OptionLevelWorkload(13, 21, 5197),
                 OptionLevelWorkload(30, 38, 27872)]
    old = candidate().vector(_menu().context, feature_version=8)
    vectors = [candidate(w).vector(_menu().context, feature_version=9) for w in workloads]
    assert len(set(vectors)) == 3
    assert all(v[:365] == old and len(v) == 370 for v in vectors)
    assert vectors[1][-1] < vectors[0][-1] < vectors[2][-1]
    assert all(v[-2] == .08 for v in vectors)
    assert not any(s in n for n in option_feature_names(9)[-5:]
                   for s in ('species', 'identity', 'route', 'seed', 'box'))


@pytest.mark.parametrize('values', [
    (True, 20, 100), (0, 20, 100), (19, True, 100), (19, 19, 100),
    (20, 19, 100), (99, 101, 100), (19, 20, True), (19, 20, 0),
    (19, 20, -1), (19, 20, 2_000_001), (19, 20, None), (19, 20, float('nan')),
])
def test_unmeasured_or_invalid_work_never_becomes_a_native_fact(values):
    with pytest.raises(ValueError):
        OptionLevelWorkload(*values)


@pytest.mark.parametrize('version', range(1, 9))
def test_old_curriculum_stays_byte_exact_and_workload_unknown(version):
    row = LivingDexCurriculumOutcomeExample(
        'c' * 64, 'train', version,
        candidate().vector(_menu().context, feature_version=version),
        _settled(success=True, completion=.1, unlock=0, action_cost=.2),
    )
    before = copy.deepcopy(row.public_dict())
    digest = canonical_sha256(before)
    view = curriculum_features(row, 9)
    assert view[:len(row.features)] == row.features
    assert view[-5:] == (0.,) * 5
    assert view[:365] == curriculum_features(row, 8)
    assert row.public_dict() == before and canonical_sha256(row.public_dict()) == digest


@pytest.mark.parametrize('workload', [None, OptionLevelWorkload(19, 20, 1),
                                   OptionLevelWorkload(30, 38, 27872)])
def test_zero_influence_upgrade_retains_predictions_and_frozen_model(workload):
    old = upgrade_option_value_model_for_kind_effort(_model())
    before = copy.deepcopy(old.to_dict())
    new = upgrade_option_value_model_for_level_workload(old)
    assert new.feature_version == 9
    assert old.to_dict() == before and new.train_dataset_sha256 == old.train_dataset_sha256
    np.testing.assert_array_equal(new.coefficients[:365], old.coefficients)
    assert not np.any(new.coefficients[365:])
    np.testing.assert_allclose(new.predict_candidate(_menu().context, candidate(workload)).vector(),
                               old.predict_candidate(_menu().context, candidate()).vector(),
                               rtol=0, atol=1e-12)
    assert LivingDexOptionValueModel.from_dict(new.to_dict()).model_sha256 == new.model_sha256
    assert upgrade_option_value_model_for_level_workload(new) is new


def test_v9_menu_roundtrip_and_legacy_menu_remains_exact():
    base = _menu()
    old_doc = copy.deepcopy(base.policy_dict())
    assert restore_living_dex_policy_menu(old_doc).policy_dict() == old_doc
    menu = replace(base, candidates=(candidate(OptionLevelWorkload(13, 21, 5197)),
                                    base.candidates[1]))
    document = menu.policy_dict()
    assert menu.feature_version == 9
    assert document['schema'].endswith('.v9')
    restored = restore_living_dex_policy_menu(document)
    assert restored.policy_dict() == document
    assert restored.candidate_vector(0) == menu.candidate_vector(0)
    assert base.policy_dict() == old_doc and 'level_workload' not in old_doc['candidates'][0]
    for version in range(1, 9):
        with pytest.raises(LivingDexOptionValueError, match='legacy scorer'):
            menu.candidate_vector(0, feature_version=version)


@pytest.mark.parametrize('fault', ['extra', 'missing', 'invalid', 'old_schema'])
def test_workload_menu_rejects_tampered_or_disguised_facts(fault):
    menu = replace(_menu(), candidates=(candidate(OptionLevelWorkload(13, 21, 5197)),
                                       _menu().candidates[1]))
    doc = menu.policy_dict()
    data = doc['candidates'][0]['level_workload']
    if fault == 'extra':
        data['species'] = 'private'
    elif fault == 'missing':
        del data['remaining_xp']
    elif fault == 'invalid':
        data['remaining_xp'] = 0
    else:
        doc['schema'] = 'pokemon.core.living-dex-option-menu.v7'
    with pytest.raises(LivingDexPolicyCodecError):
        restore_living_dex_policy_menu(doc)


@pytest.mark.parametrize('kind', [k for k in LivingDexOptionKind
                                  if k not in (LivingDexOptionKind.EVOLVE, LivingDexOptionKind.DEVELOP)])
def test_training_workload_cannot_masquerade_as_another_mechanic(kind):
    with pytest.raises(LivingDexOptionValueError, match='level-training'):
        replace(candidate(OptionLevelWorkload(13, 21, 5197)),
                features=replace(candidate().features, kind=kind))


def test_unknown_is_distinct_from_measured_tiny_positive_work():
    unknown = candidate().vector(_menu().context, feature_version=9)[-5:]
    known = candidate(OptionLevelWorkload(19, 20, 1)).vector(_menu().context, feature_version=9)[-5:]
    assert unknown == (0.,) * 5 and known[0] == 1. and known[-1] > 0
