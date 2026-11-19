"""Retained native TRAIN terminals keep their exact parent and audit identity."""
import json
from hashlib import sha256
import pytest
from test_league_funding_train_admission import source,packed
import pokemon_red_completion.red_production_train_admission as m


def checkpoint(source,monkeypatch):
    terminal=b'unit-test-native-terminal';terminal_sha=sha256(terminal).hexdigest()
    parent_sha=sha256(source['source_state']).hexdigest();case='unit-test-funding-checkpoint'
    phase=dict(ordinal=0,before_sha256=parent_sha,after_state=dict(sha256=terminal_sha),
        after=dict(battle_state=0,input_ready=True,buttons_released=True))
    result=packed(dict(phase_results=[phase],guest_closed=True,original_source_unchanged=True))
    authority=packed(dict(passed=True,rows=[dict(case=case,partition='train',teacher_selected=True,
        result=dict(sha256=sha256(result).hexdigest()),phases=[dict(before_state=dict(sha256=parent_sha),
        after_state=dict(sha256=terminal_sha))])]))
    monkeypatch.setattr(m,'NATIVE_FUNDING_CHECKPOINTS',{case:(parent_sha,terminal_sha)})
    monkeypatch.setattr(m,'NATIVE_FUNDING_CHECKPOINT_AUTH',sha256(authority).hexdigest())
    args=dict(case_id=case,source_state=terminal,authority_bytes=authority,result_bytes=result)
    declaration=m.retained_funding_checkpoint_declaration(**args)
    work=packed(dict(partition='train',teacher_actions_allowed=True,league_funding_train_component=declaration))
    return dict(args,work_order_bytes=work,source_commit=source['source_commit'],model_bytes=source['model_bytes'])


def test_known_native_terminal_is_a_correlated_training_source_not_a_new_origin(source,monkeypatch):
    args=checkpoint(source,monkeypatch)
    a=m.LeagueFundingTrainAdmission.authenticate_retained_checkpoint(**args)
    a.require_work_order(args['work_order_bytes'])
    assert a.document()['schema']==m.NATIVE_FUNDING_CHECKPOINT_SCHEMA
    assert a.document()['fit_admission'] is a.document()['new_independent_origin'] is False
    assert a.source_state_sha256==sha256(args['source_state']).hexdigest()
    assert a.source_origin_sha256==m.SOURCE_ORIGIN


@pytest.mark.parametrize('field',['case_id','source_state','authority_bytes','result_bytes','work_order_bytes','model_bytes'])
def test_arbitrary_checkpoint_or_changed_proof_cannot_be_enrolled(source,monkeypatch,field):
    args=checkpoint(source,monkeypatch)
    args[field]='unknown-case' if field=='case_id' else b'{}'
    with pytest.raises(ValueError):m.LeagueFundingTrainAdmission.authenticate_retained_checkpoint(**args)
