"""Exercise the staged actual shared chunk with fake bytes/ports only."""
import copy, json
from hashlib import sha256
from types import SimpleNamespace as NS
import pytest
import run_configured_red_player as driver
from test_configured_restoration_budget_censor import receipt

EXPORT_KEYS=('schema','state_sha256','lesson','cash','bag','preparation','battle','spent','grants_new_budget','fit_allowed')
@pytest.mark.parametrize('fault',[None,'tuple_bag','state','spent','new_budget','fit_allowed','disk_spent','disk_new_budget','disk_fit_allowed','disk_schema','disk_state']+['missing:'+k for k in EXPORT_KEYS])
def test_actual_chunk_binds_limits_and_pairs_export(tmp_path,monkeypatch,fault):
    r=receipt();payload=b'fake-port-terminal';state_sha=sha256(payload).hexdigest()
    r['state_sha256']=state_sha;r['episode']['outcomes'][-1]['terminal_state_sha256']=state_sha
    native=tmp_path/'native';native.mkdir()
    (native/'native-costs.json').write_text(json.dumps(r['chunk_costs']))
    prior=dict(decisions=0,actions=0,frames=0,seconds=0.,heals=0,cash_debits=0)
    raw=NS(player_money=3000,map_id=64,player_y=3,player_x=3,party_levels=(20,))
    em=NS(frame_count=0,pressed_buttons=(),save_state_bytes=lambda:payload)
    holder=dict(plan=NS(roster=()),prior_spent=prior,runtime=NS(reader=NS(read=lambda:raw)),observe_history=lambda **kw:None)
    seen=[]
    cap=driver.NativePlayerLimits(decisions=24,actions=24000,frames=2400000,seconds=600,heals=16,cash_debits=None)
    def fake_native(**kwargs):
        seen.append(kwargs['limits']);return copy.deepcopy(r['episode'])
    def capture(*args,spent,**kwargs):
        value=dict(schema=driver.PLAYER_CONTINUATION_SCHEMA,state_sha256=state_sha,spent=spent,fit_allowed=False,grants_new_budget=False,lesson=dict(completed_objectives=[]),cash=3000,bag=[],preparation=None,battle=None)
        if fault=='state':value['state_sha256']='c'*64
        elif fault=='spent':value['spent']=dict(spent,heals=0)
        elif fault=='new_budget':value['grants_new_budget']=True
        elif fault=='fit_allowed':value['fit_allowed']=True
        elif fault=='tuple_bag':value['bag']=((1,2),)
        elif fault and fault.startswith('missing:'):del value[fault.split(':',1)[1]]
        return value
    monkeypatch.setattr(driver,'run_native_continuous_player',fake_native)
    monkeypatch.setattr(driver,'native_player_options',lambda *a:dict(greedy_selection=True,resume_branch_refinement_after_settlement=False))
    monkeypatch.setattr(driver,'player_wiring_declaration',lambda *a:{})
    monkeypatch.setattr(driver,'_field_ready',lambda *a:True)
    monkeypatch.setattr(driver,'native_checkpoint_facts',lambda *a:{})
    monkeypatch.setattr(driver,'capture_player_continuation',capture)
    original_record=driver._record
    def record(path,value):
        if path.name=='CONTEXT.json' and fault and fault.startswith('disk_'):
            value=copy.deepcopy(value)
            if fault=='disk_spent':value['spent']['heals']=0
            elif fault=='disk_new_budget':value['grants_new_budget']=True
            elif fault=='disk_fit_allowed':value['fit_allowed']=True
            elif fault=='disk_schema':value['schema']='different'
            elif fault=='disk_state':value['state_sha256']='e'*64
        return original_record(path,value)
    monkeypatch.setattr(driver,'_record',record)
    def execute():
        return driver.execute_player_chunk(plan={'seed':1},configuration=NS(sha256='c'*64),
        c=NS(digest=lambda p:sha256(p.read_bytes()).hexdigest()),emulator=em,factory=None,
        menu=None,holder=holder,source=None,output=tmp_path,model=NS(model_sha256='d'*64),
        limits=cap,memory=None,store=None,ordinal=1)
    if fault=='missing:lesson':
        with pytest.raises(KeyError,match='lesson'):
            execute()
        assert seen==[cap]
        return
    result,exported=execute()
    assert seen==[cap] and seen[0] is cap
    assert result['passed'] is True
    assert result['episode']['outcomes'][-1]['verification']=='failed'
    assert result['episode']['outcomes'][-1]['error_type']=='RestorationBudgetExhausted'
    assert result['native_status']['native_outcome_error_count']==1
    assert result['paired_context_authenticated'] is (fault in (None,'tuple_bag'))
    assert result['native_status']['status']==('restoration_budget_censor' if fault in (None,'tuple_bag') else 'execution_error')
