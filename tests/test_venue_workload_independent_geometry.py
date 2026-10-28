"""ROM-free independent review tests; copy into Code/tests only under root's lock.

Uses existing test_party_development_workload and outcome-learning fixtures.
No optimizer, native runtime, cartridge, external data or model file is loaded.
"""
from dataclasses import asdict
import json

import numpy as np
import pytest

from pokemon_red_completion.party_development_catalog import (
    PartyDevelopmentCatalogError, PartyDevelopmentProspectiveBinding)
from pokemon_red_completion.party_development_outcome_learning import (
    PartyDevelopmentOutcomeModel, upgrade_party_development_model_for_workload)
from pokemon_red_completion.party_development_outcomes import PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE
from pokemon_red_completion.party_development_rank import (
    PARTY_DEVELOPMENT_WORKLOAD_FEATURE_SCHEMA_ID, PartyDevelopmentCandidateSet,
    PartyDevelopmentFeatureError, VenueTrainingWorkload)
from pokemon_red_completion.provenance import canonical_sha256

from test_party_development_workload import _project, _binding
from test_party_development_outcome_learning import _initialized_model


@pytest.mark.parametrize('share,xp,travel,recovery,expected', [
    (None, None, None, None, (0., 0., 0., 0., 0., 0., 0.)),
    (None, None, 0, None, (0., 0., 0., 1., 0., 0., 0.)),
    (None, None, None, 0, (0., 0., 0., 0., 0., 1., 0.)),
    (None, None, 48, 96, (0., 0., 0., 1., .000048, 1., .000096)),
    (0, 0, 0, None, (1., 0., 0., 1., 0., 0., 0.)),
    (.9, 50, None, 17, (1., .9, .0005, 0., 0., 1., .000017)),
])
def test_independent_known_groups_have_exact_vectors(share, xp, travel, recovery, expected):
    work = VenueTrainingWorkload(share, xp, travel, recovery)
    assert work.vector() == expected


@pytest.mark.parametrize('share,xp', [(None, 0), (0, None), (None, 5), (.5, None)])
def test_half_known_yield_pair_is_rejected(share, xp):
    with pytest.raises(PartyDevelopmentFeatureError):
        VenueTrainingWorkload(share, xp, travel_steps=17)


@pytest.mark.parametrize('share,xp', [
    (True, 1), (.5, True), (float('nan'), 1), (.5, float('nan')),
    (float('inf'), 1), (.5, float('inf')), (-.1, 1), (1.1, 1),
    (.5, -1), (.5, 100001), (0, 1), ('unknown', 1), (.5, 'unknown'),
])
def test_known_yield_validation_is_not_weakened(share, xp):
    with pytest.raises(PartyDevelopmentFeatureError):
        VenueTrainingWorkload(share, xp)


@pytest.mark.parametrize('field,value', [
    ('travel_steps', True), ('recovery_steps', False),
    ('travel_steps', -1), ('recovery_steps', 1000001),
    ('travel_steps', 1.), ('recovery_steps', float('nan')),
])
def test_unknown_yield_does_not_bypass_geometry_validation(field, value):
    with pytest.raises(PartyDevelopmentFeatureError):
        VenueTrainingWorkload(None, None, **{field: value})


def test_missing_yield_is_not_fabricated_known_zero_or_implicit_default():
    unknown = VenueTrainingWorkload(None, None, travel_steps=0)
    unusable = VenueTrainingWorkload(0, 0, travel_steps=0)
    assert unknown.vector()[0] == 0 and unusable.vector()[0] == 1
    assert asdict(unknown) == dict(useful_encounter_share=None,
        expected_recipient_xp_per_encounter=None, travel_steps=0, recovery_steps=None)
    assert VenueTrainingWorkload(**json.loads(json.dumps(asdict(unknown)))) == unknown
    with pytest.raises(TypeError):
        VenueTrainingWorkload(travel_steps=0)


def test_all_unknown_payload_preserves_original_unknown_public_vector():
    absent = _project()
    explicit = _project(venues=(VenueTrainingWorkload(None, None),)*2)
    assert absent.public_dict() == explicit.public_dict()
    assert explicit.feature_schema_id == PARTY_DEVELOPMENT_WORKLOAD_FEATURE_SCHEMA_ID


def test_geometry_only_codec_and_prospective_binding_remain_exact():
    work = (VenueTrainingWorkload(None, None, 48, 96),
            VenueTrainingWorkload(None, None, 201, 55))
    menu = _project(venues=work)
    restored = PartyDevelopmentCandidateSet.from_public_dict(
        json.loads(json.dumps(menu.public_dict())))
    assert restored == menu
    binding = _binding(menu, PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE)
    decoded = PartyDevelopmentProspectiveBinding.from_public_dict(binding.public_dict())
    assert decoded == binding
    decoded.require_candidate_set(restored)
    with pytest.raises(PartyDevelopmentCatalogError, match='features differ'):
        decoded.require_candidate_set(_project())
    for candidate in menu.candidates:
        fields = dict(zip(menu.feature_names, candidate.features, strict=True))
        assert fields['venue.useful_encounters_known'] == 0
        assert fields['venue.useful_encounter_share'] == 0
        assert fields['venue.expected_recipient_xp_per_encounter'] == 0
        assert fields['venue.travel_steps_known'] == fields['venue.recovery_steps_known'] == 1


def test_frozen_p161_fully_known_menu_and_model_identity_are_retained():
    # Captured from P161 by pure fixture projection before this patch; no fit.
    work = (VenueTrainingWorkload(.9, 50, travel_steps=0, recovery_steps=17),
            VenueTrainingWorkload(.2, 5, travel_steps=123, recovery_steps=None))
    assert asdict(work[0]) == dict(useful_encounter_share=.9,
        expected_recipient_xp_per_encounter=50, travel_steps=0, recovery_steps=17)
    menu = _project(venues=work)
    assert canonical_sha256(menu.public_dict()) == '6912a886523afcfbc007ab3fe839c48efdf5948c90ef90ae25a0c7d50ae63057'
    model = upgrade_party_development_model_for_workload(_initialized_model())
    assert canonical_sha256(model.to_dict()) == 'f0e636280a66acfd29defb25b9653ebfb9ed96190ccc9fa3d513ef0c67f6f1ec'
    restored = PartyDevelopmentOutcomeModel.from_dict(json.loads(json.dumps(model.to_dict())))
    assert restored.to_dict() == model.to_dict()
    np.testing.assert_array_equal(restored.scores(menu), model.scores(menu))


def test_explicit_zero_extension_has_no_implicit_learning_or_adoption():
    parent = _initialized_model()
    parent_document = parent.to_dict()
    old_menu = _project(include_workload=False)
    geometry_menu = _project(venues=(VenueTrainingWorkload(None, None, 48, 96),
                                    VenueTrainingWorkload(None, None, 201, 55)))
    upgraded = upgrade_party_development_model_for_workload(parent)
    np.testing.assert_array_equal(parent.scores(old_menu), upgraded.scores(geometry_menu))
    assert parent.to_dict() == parent_document
    assert parent.outcome_training_examples == upgraded.outcome_training_examples == 0
    assert parent.outcome_training_root_lineage_ids == upgraded.outcome_training_root_lineage_ids
