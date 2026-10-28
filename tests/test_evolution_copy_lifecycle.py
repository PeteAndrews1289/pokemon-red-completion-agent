from collections import Counter
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from types import SimpleNamespace as N
import json
import pytest
import run_configured_red_player as driver
import pokemon_red_completion.red_level_evolution_options as evolution
import pokemon_red_completion.red_player_party_loan as loans
from pokemon_red_completion.collection import CollectionLocation
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport,GoalVerification

@pytest.mark.parametrize('mode',['pass','fail','error','native_error'])
def test_evolution_copy_records_post_close_failure_and_costs(tmp_path,monkeypatch,capsys,mode):
 class Emulator:
  pressed_buttons=()
  def __enter__(self):self._backend=object();return self
  def __exit__(self,*args):self._backend=None;return False
  def load_state_bytes(self,payload):assert payload==b'source'
  def save_state_bytes(self):return b'terminal'
 @dataclass
 class World:
  full_event_offsets:bool=False
  observe_terrain:bool=False
  route_world:str='observed-world'
 rom=tmp_path/'fixture.rom';rom.write_bytes(b'fixture')
 guard=N(refs=('combat',),reader=N(preparation_specimen_refs=lambda:('combat',)),verify_active_roster_restored=lambda:None)
 observation=N(collection_observation=N(specimens=(N(species_ref='pokemon:national:013',location=CollectionLocation.BOX),)))
 runtime=N(adapter=N(party_guard=guard,observe=lambda:observation))
 state=N(stock=Counter({('precursor',88,18,7290):1,('combat',28,50,100000):1}))
 session=N(runtime=runtime,actions=N(observe_cash=lambda:1,observed_cash_debits=13,observed_cash_rewards=27,observed_cash_changes=3),recorder=N(enabled=False,trace=[1,2]),controller=N(input_enabled=True,frames_executed=7),wall=N(elapsed_seconds=.5),heals=1,training_healing_trips=1,support_restorations=0,training_restoration_overlaps=0)
 def execute():
  if mode=='native_error':raise RuntimeError('retained primary native failure')
  state.stock=Counter({('precursor',89,30,27000):1,('combat',28,50,100000):1})
  return GoalExecutionReport(2,7,dict(healing_trips=1,settlement_reserve_reached=True))
 choice=N(binding=N(binding_ref='pokemon.red:evolution:fixture',execute=execute,verify=lambda _:GoalVerification.succeeded()),execution_effort=.5)
 spec=N(parameters=dict(source_species_ref='pokemon:national:013'))
 holder=dict(plan=N(roster=(N(specimen_ref='combat',purpose=N(value='combat')),)),observe_history=lambda:None)
 monkeypatch.setattr(driver,'assemble_configured_player',lambda *a,**k:(b'source',lambda _:None,N(),holder,N()))
 monkeypatch.setattr(driver,'initialize_private_root',lambda *a,**k:N())
 monkeypatch.setattr(driver,'NativePlayerSession',lambda **k:session)
 monkeypatch.setattr(driver,'evolution_copy_choice',lambda *a:(choice,spec))
 monkeypatch.setattr(evolution,'enumerate_red_level_evolutions',lambda *a,**k:(choice,))
 monkeypatch.setattr(driver,'_field_ready',lambda _:True)
 monkeypatch.setattr(driver,'authenticate_parent',lambda *a:None)
 monkeypatch.setattr(driver,'verify_pins',lambda _:None)
 monkeypatch.setattr(loans,'_stock',lambda _:state.stock.copy())
 monkeypatch.setattr(driver,'capture_player_continuation',lambda *a,spent,**k:dict(spent=spent,state_sha256=sha256(b'terminal').hexdigest()))
 reload_calls=[]
 def reload(*args):
  reload_calls.append(args)
  if mode=='error':raise OSError('retained reload failure')
  return dict(passed=mode=='pass',inputs=0,frames=0)
 monkeypatch.setattr(driver,'verify_diagnostic_reload',reload)
 plan=dict(partition='development',diagnostic_only=True,actual_gameplay_resume_authorized=False,copy_back=False,fit_allowed=False,seed=11,protected={},objectives=['defeat_champion'],required_species=['pokemon:national:148'],cutoff_utc=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat())
 prior=dict(actions=10,frames=20,decisions=3,heals=1,seconds=2.,cash_debits=5)
 driver.verify_evolution_copy(N(seconds=10),plan,tmp_path,N(c=N(PyBoyAdapter=lambda _:Emulator(),ROM=rom,REPO=tmp_path,digest=lambda p:sha256(p.read_bytes()).hexdigest()),shared=N(RedVermilionGroundTransition=N(from_rom=lambda _:World()))),N(sha256='c'*64,goal_model_sha256='d'*64,to_dict=lambda:{}),tmp_path/'parent',dict(state_sha256='b'*64,spent=prior),dict(decisions=1,actions=100,frames=1000,heals=4,seconds=10))
 folder=next((tmp_path/'diagnostics').iterdir());native=json.loads((folder/'RESULT.json').read_text());final=json.loads((folder/'FINAL-RESULT.json').read_text());printed=json.loads(capsys.readouterr().out)
 assert native['passed']==(mode!='native_error') and 'reload_passed' not in native
 assert final['passed']==printed['passed']==(mode=='pass')
 assert native['checkpoint_lifecycle']['guest_backend_closed'] is False
 assert final['checkpoint_lifecycle']['guest_backend_closed'] is True
 assert not native['worker_stopped'] and final['worker_stopped']
 assert final['checkpoint_lifecycle']['host_process_exit_confirmed'] is False
 assert final['spent']==native['spent']==dict(actions=12,frames=27,decisions=4,heals=2,seconds=2.5,cash_debits=18)
 assert (folder/'terminal.state').read_bytes()==b'terminal'
 if mode=='native_error':
  assert reload_calls==[] and final['error']=='retained primary native failure'
  assert final['error_chain']==native['error_chain'] and final['error_chain'][0]['error_type']=='RuntimeError'
 else:assert len(reload_calls)==1
 if mode=='fail':assert final['reload_passed'] is False
 if mode=='error':assert final['reload_error']=='retained reload failure' and final['reload_error_chain'][0]['error_type']=='OSError'
