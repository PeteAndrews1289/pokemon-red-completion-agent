import copy,json
from hashlib import sha256
from types import SimpleNamespace as N
import pytest
import run_configured_red_player as driver
from pokemon_red_completion.red_player_configuration import checkpoint_quiescent,player_lifecycle_fields

def live():
 return dict(released=True,**player_lifecycle_fields(scope="live_chunk",released=True,guest_backend_closed=False))

@pytest.mark.parametrize("guest,scope",[(False,"live_chunk"),(None,"live_chunk"),(True,"driver_terminal"),(None,"driver_terminal"),(None,"prelaunch_failure")])
def test_quiescence_does_not_require_guest_or_host_exit(guest,scope):
 result=dict(released=True,**player_lifecycle_fields(scope=scope,released=True,guest_backend_closed=guest))
 assert checkpoint_quiescent(result)
 assert result['worker_stopped'] is (guest is True)
 assert result['checkpoint_lifecycle']['host_process_exit_confirmed'] is False

@pytest.mark.parametrize("fault",['held','missing_release','incomplete','missing_life_controls','life_held','fake_exit','flag_conflict','scope','schema','extra','guest_type','life_type'])
def test_bad_new_lifecycle_cannot_fall_back_to_legacy_true(fault):
 result=live();life=result['checkpoint_lifecycle']
 if fault=='held':result['released']=False
 if fault=='missing_release':result.pop('released')
 if fault=='incomplete':life['chunk_complete']=False
 if fault=='missing_life_controls':life.pop('inputs_released')
 if fault=='life_held':life['inputs_released']=False
 if fault=='fake_exit':life['host_process_exit_confirmed']=True
 if fault=='flag_conflict':result['worker_stopped']=True
 if fault=='scope':life['scope']='arbitrary'
 if fault=='schema':life['schema']='old'
 if fault=='extra':life['hidden_override']=True
 if fault=='guest_type':life['guest_backend_closed']=0
 if fault=='life_type':result['checkpoint_lifecycle']=True
 assert not checkpoint_quiescent(result)

def test_legacy_checkpoint_retains_original_compatibility_only():
 assert checkpoint_quiescent(dict(worker_stopped=True,released=True))
 assert not checkpoint_quiescent(dict(worker_stopped=False,released=True))
 assert not checkpoint_quiescent(dict(worker_stopped=True,released=False))

@pytest.mark.parametrize('budget_stop',[False,True])
def test_actual_chunk_export_then_live_parent_auth_preserves_costs(tmp_path,monkeypatch,budget_stop):
 import test_red_player_entry_continuity as fixture
 real=driver.execute_player_chunk
 def recorded(**kwargs):
  result,context=real(**kwargs)
  driver._record(kwargs['output']/'RESULT.json',result)
  return result,context
 monkeypatch.setattr(driver,'execute_player_chunk',recorded)
 fixture.test_shared_native_call_preserves_partial_costs_and_censored_history(tmp_path,monkeypatch,budget_stop)
 parent=tmp_path/'runs/segment-001';row=json.loads((parent/'RESULT.json').read_text())
 assert row['worker_stopped'] is False and checkpoint_quiescent(row)
 original=driver.authenticate_parent(parent,lambda p:sha256(p.read_bytes()).hexdigest())
 assert original['spent']['actions']==201 and original['spent']['cash_debits']==135
 row['checkpoint_lifecycle']['chunk_complete']=False;(parent/'RESULT.json').write_text(json.dumps(row))
 with pytest.raises(ValueError):driver.authenticate_parent(parent,lambda p:sha256(p.read_bytes()).hexdigest())

def test_valid_faint_recovery_keeps_live_quiescent_parent(monkeypatch,tmp_path):
 import test_retained_field_faint as fixture
 from pokemon_red_completion import red_player_configuration as config
 rt,actions,state,proof,calls=fixture.environment(monkeypatch)
 result=fixture.write_parent(tmp_path,state,proof);result.update(live())
 (tmp_path/'RESULT.json').write_text(json.dumps(result))
 assert config._retained_field_faint_inventory(rt,actions,parent=tmp_path) is not None
 assert not calls

def test_new_prelaunch_failure_is_not_host_exit_and_hides_no_inputs(tmp_path):
 parent=tmp_path/'runs/segment-001';parent.mkdir(parents=True);(parent/'PLAN.json').write_text('{}')
 row=dict(phase='before_emulator',released=True,state_loads=0,inputs=0,frames=0,passed=False,
 **player_lifecycle_fields(scope='prelaunch_failure',released=True,guest_backend_closed=None))
 (parent/'PRELAUNCH-ERROR.json').write_text(json.dumps(row))
 assert driver.configured_run_nodes(tmp_path)==([],2)
 row['inputs']=1;(parent/'PRELAUNCH-ERROR.json').write_text(json.dumps(row))
 with pytest.raises(ValueError):driver.configured_run_nodes(tmp_path)

def test_unexpected_guest_close_is_retained_without_masking_primary_error():
 result=dict(released=True,error_type='NativePrimaryError',error='native failure')
 result.update(player_lifecycle_fields(scope='live_chunk',released=True,guest_backend_closed=True))
 assert result['error_type']=='NativePrimaryError' and result['error']=='native failure'
 assert result['checkpoint_lifecycle']['unexpected_guest_closure'] is True
 assert checkpoint_quiescent(result)
 assert result['checkpoint_lifecycle']['host_process_exit_confirmed'] is False
