from copy import deepcopy

import pytest
from run_configured_red_player import native_result_status


def receipt(**updates):
    value = dict(passed=True, error=None, field_ready=True, released=True,
                 episode=dict(stop_reason='decision_budget', outcomes=[]),
                 spent=dict(seconds=123.5))
    value.update(updates)
    return value


def test_returned_driver_does_not_hide_native_faint_error_or_mutate_receipt():
    value = receipt(field_ready=False, episode=dict(stop_reason='unsafe_terminal', outcomes=[
        dict(error_type='RouteExecutionError', error='active battler fainted',
             error_chain=[dict(error_type='BattleRuntimeError', error='hp=0/78')],
             ordinary_setback=False, verification=None)]))
    before = deepcopy(value)
    status = native_result_status(value)
    assert status['status'] == 'execution_error' and status['wrapper_returned']
    assert status['native_outcome_error_count'] == 1
    assert status['controls_released'] and not status['field_ready']
    assert not status['independent_completion_verification']
    assert value == before


@pytest.mark.parametrize('updates,expected', [
    ({}, 'settled_chunk'),
    ({'released': False}, 'controls_unreleased_or_unknown'),
    ({'field_ready': False}, 'control_recovery_required'),
    ({'checkpoint_export_error': {'error': 'failed'}}, 'execution_error'),
    ({'episode': {'admission_failure': {'error': 'scope'}}}, 'admission_error'),
    ({'episode': {'outcomes': [{'verification': 'failed', 'ordinary_setback': True}]}}, 'ordinary_setback'),
    ({'episode': {'outcomes': [{'verification': 'failed', 'ordinary_setback': False}]}}, 'verification_failure'),
    ({'episode': {'stop_reason': 'curriculum_complete'}}, 'curriculum_completion_reported'),
    ({'passed': False}, 'unverified'),
])
def test_native_status_keeps_setbacks_recovery_and_completion_distinct(updates, expected):
    status = native_result_status(receipt(**updates))
    assert status['status'] == expected and not status['independent_completion_verification']


def test_completion_label_does_not_override_execution_or_admission_failure():
    value = receipt(episode=dict(stop_reason='curriculum_complete', outcomes=[
        dict(error_type='ControllerFrameBudgetError', error='controller exhausted its hard frame budget')]))
    assert native_result_status(value)['status'] == 'execution_error'
    value['episode']['admission_failure'] = {'error_type': 'ValueError', 'error': 'bad'}
    assert native_result_status(value)['status'] == 'admission_error'
