"""Different trainee workload reuses existing TRAIN custody and full-menu guards."""
import pytest
from test_venue_workload_teacher import setup_case

from pokemon_red_completion import red_teacher_venue as teacher


def test_default_diglett_and_validation_dragonair_keep_original_identities():
    assert teacher.workload_trainee_species({}, validation=False) == (59, 118)
    assert teacher.workload_trainee_species(
        {'trainee_profile': 'dragonair54_to55', 'fixture_level': 54}, validation=True
    ) == (89, 66)
    with pytest.raises(ValueError):
        teacher.workload_trainee_species(
            {'trainee_profile': 'dragonair54_to55', 'fixture_level': 54}, validation=False
        )


def test_new_profile_authenticates_through_original_full_train_source_path(tmp_path, monkeypatch):
    plan, _, capture = setup_case(tmp_path, monkeypatch)
    plan['sources'][0].update(trainee_profile='drowzee30_to31', fixture_level=30)
    assert teacher.workload_trainee_species(plan['sources'][0], validation=False) == (48, 129)
    observed, payload, proof = teacher.authenticate_venue_source(plan)
    assert observed is capture and payload == b'original authenticated TRAIN state'
    assert proof['partition'] == 'train' and not proof['independent_origin']


@pytest.mark.parametrize('level', [True, None, 29, 31, 54, 30.0])
def test_new_profile_rejects_other_levels_or_coercion(level):
    with pytest.raises(ValueError):
        teacher.workload_trainee_species(
            {'trainee_profile': 'drowzee30_to31', 'fixture_level': level}, validation=False
        )


@pytest.mark.parametrize('fault', ['partition', 'consumed', 'unbound', 'mode', 'copyback'])
def test_new_profile_cannot_bypass_existing_train_guards(tmp_path, monkeypatch, fault):
    plan, model, _ = setup_case(tmp_path, monkeypatch)
    item = plan['sources'][0]
    item.update(trainee_profile='drowzee30_to31', fixture_level=30)
    if fault == 'partition':
        item['execution_partition'] = 'development'
    elif fault == 'consumed':
        model.outcome_training_root_lineage_ids = ('train-root',)
    elif fault == 'unbound':
        plan['pins'].pop(plan['source_authentication'])
    elif fault == 'mode':
        item['venue_mode'] = 'model'
    else:
        plan['copy_back'] = True
    with pytest.raises(ValueError):
        teacher.authenticate_venue_source(plan)
