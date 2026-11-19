"""ROM-free capture/disk export mirror tests; semantic restore remains separate."""
from copy import deepcopy
import json

import pytest
from run_configured_red_player import PLAYER_CONTINUATION_SCHEMA, _paired_context_authenticated

OPTIONAL = {
    'search_memory': {'entries': {}, 'schema': 'opaque-already-captured-memory'},
    'field_carrier': {'carrier_ref': 'fixture:carrier', 'phase': 'active'},
    'story_kind_commitment': {'objective_ref': 'fixture:story'},
    'preparation_story_loss': {'losses': [], 'lineage': 'fixture:lineage'},
}
REQUIRED = ('schema','state_sha256','lesson','cash','bag','preparation','battle','spent','grants_new_budget','fit_allowed')


def capture():
    # The export gate compares already-captured JSON; this fixture does not
    # claim that arbitrary custody/party documents pass the full native restore.
    return dict(schema=PLAYER_CONTINUATION_SCHEMA,state_sha256='a'*64,
        lesson=dict(completed_objectives=['fixture:story'],party=[]),cash=1000,bag=[[1,2]],
        preparation=None,battle=None,spent=dict(actions=17,decisions=3,frames=240,heals=2,seconds=1.25,cash_debits=9),
        grants_new_budget=False,fit_allowed=False)


def result_for(document):
    return dict(state_sha256=document['state_sha256'],context_sha256='b'*64)


@pytest.mark.parametrize('mask',range(16))
def test_all_already_supported_optional_field_combinations_remain_paired(mask):
    fresh=capture()
    for n,(key,value) in enumerate(OPTIONAL.items()):
        if mask&(1<<n):fresh[key]=deepcopy(value)
    saved=json.loads(json.dumps(fresh))
    assert _paired_context_authenticated(fresh,saved,result_for(fresh),deepcopy(fresh['spent'])) is True


def test_capture_tuple_to_saved_JSON_list_uses_existing_canonical_equality():
    fresh=capture();fresh['bag']=((1,2),)
    saved=json.loads(json.dumps(fresh))
    assert fresh!=saved
    assert _paired_context_authenticated(fresh,saved,result_for(fresh),fresh['spent']) is True


@pytest.mark.parametrize('key',OPTIONAL)
def test_optional_payloads_are_compared_not_ignored(key):
    fresh=capture();fresh[key]=deepcopy(OPTIONAL[key]);saved=deepcopy(fresh)
    saved[key]['different']='stale-or-other-source'
    assert _paired_context_authenticated(fresh,saved,result_for(fresh),fresh['spent']) is False


@pytest.mark.parametrize('key',OPTIONAL)
def test_missing_optional_payload_on_either_side_is_not_a_paired_export(key):
    fresh=capture();fresh[key]=deepcopy(OPTIONAL[key]);saved=capture()
    assert _paired_context_authenticated(fresh,saved,result_for(fresh),fresh['spent']) is False
    assert _paired_context_authenticated(saved,fresh,result_for(fresh),fresh['spent']) is False


@pytest.mark.parametrize('key',REQUIRED)
def test_missing_required_key_on_matching_documents_still_refuses(key):
    fresh=capture();result=result_for(fresh);spent=deepcopy(fresh['spent']);fresh.pop(key)
    assert _paired_context_authenticated(fresh,deepcopy(fresh),result,spent) is False


def test_matching_unknown_extra_key_is_not_admitted():
    fresh=capture();fresh['unrecognized_future_metadata']={}
    assert _paired_context_authenticated(fresh,deepcopy(fresh),result_for(fresh),fresh['spent']) is False


@pytest.mark.parametrize('key,value',[('grants_new_budget',True),('grants_new_budget',0),('fit_allowed',True),('fit_allowed',0),('schema','wrong-schema')])
def test_matching_documents_cannot_grant_budget_fit_or_change_schema(key,value):
    fresh=capture();fresh[key]=value
    assert _paired_context_authenticated(fresh,deepcopy(fresh),result_for(fresh),fresh['spent']) is False


@pytest.mark.parametrize('fault',['state','spent','context_missing','export_error','cash_changed','bag_changed'])
def test_exact_source_counters_and_export_success_are_still_required(fault):
    fresh=capture();saved=deepcopy(fresh);result=result_for(fresh);spent=deepcopy(fresh['spent'])
    if fault=='state':result['state_sha256']='c'*64
    elif fault=='spent':spent['actions']+=1
    elif fault=='context_missing':result['context_sha256']=None
    elif fault=='export_error':result['checkpoint_export_error']='unable to export'
    elif fault=='cash_changed':saved['cash']+=1
    else:saved['bag'][0][1]+=1
    assert _paired_context_authenticated(fresh,saved,result,spent) is False


@pytest.mark.parametrize('bad',[None,[],(),42])
def test_non_dictionary_exports_are_refused(bad):
    fresh=capture()
    assert _paired_context_authenticated(bad,fresh,result_for(fresh),fresh['spent']) is False
    assert _paired_context_authenticated(fresh,bad,result_for(fresh),fresh['spent']) is False


def test_dictionary_subclass_does_not_relax_existing_exact_type_gate():
    class Other(dict):pass
    fresh=capture()
    assert _paired_context_authenticated(Other(fresh),fresh,result_for(fresh),fresh['spent']) is False
