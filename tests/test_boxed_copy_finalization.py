from collections import Counter
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from types import SimpleNamespace as N
import json

import pytest
import run_configured_red_player as driver
import pokemon_red_completion.red_boxed_machine_options as options
import pokemon_red_completion.red_player_party_loan as loans
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification


@pytest.mark.parametrize('prepared',[False,True])
@pytest.mark.parametrize('reload_mode',['pass','fail','error','native_error'])
def test_successful_copy_retains_native_result_then_one_append_only_final_record(
        tmp_path,monkeypatch,capsys,prepared,reload_mode):
    class Emulator:
        pressed_buttons=()
        def __enter__(self):self._backend=object();return self
        def __exit__(self,*args):self._backend=None;return False
        def load_state_bytes(self,payload):assert payload==b'source'
        def save_state_bytes(self):return b'terminal'
    rom=tmp_path/'fixture.rom';rom.write_bytes(b'fixture')
    guard=N(refs=('combat',),reader=N(preparation_specimen_refs=lambda:('combat',)),
        verify_active_roster_restored=lambda:None)
    runtime=N(adapter=N(party_guard=guard,observe=lambda:N()))
    state=N(stock=Counter({('precursor',88,18,7290):1,('combat',28,50,100000):1}))
    before=state.stock.copy()
    session=N(runtime=runtime,actions=N(observe_cash=lambda:1,observed_cash_debits=13,
        observed_cash_rewards=27,observed_cash_changes=3),recorder=N(enabled=False,trace=[1,2]),
        controller=N(input_enabled=True,frames_executed=7),wall=N(elapsed_seconds=.5),
        heals=0,training_healing_trips=0,support_restorations=0,training_restoration_overlaps=0)
    def execute():
        if reload_mode=='native_error':raise RuntimeError('retained native failure')
        if prepared:state.stock=Counter({('precursor',89,30,27000):1,('combat',28,50,100000):1})
        return GoalExecutionReport(2,7,dict(healing_trips=0))
    row=N(binding=N(binding_ref='pokemon.red:prepared-evolution:fixture' if prepared else 'fixture',
        execute=execute,verify=lambda _:GoalVerification.succeeded()),
        candidate=N(features=N(dependency_unlock_gain=.5)))
    menu=N(enumerate_collection=lambda *a:(row,))
    holder=dict(plan=N(roster=(N(specimen_ref='combat',purpose=N(value='combat')),)),
        observe_history=lambda:None,configured_route=N(route_world='observed-world'))
    monkeypatch.setattr(driver,'assemble_configured_player',lambda *a,**k:
        (b'source',lambda _:None,menu,holder,N()))
    monkeypatch.setattr(driver,'connect_declared_machine_options',lambda *a,**k:None)
    monkeypatch.setattr(driver,'initialize_private_root',lambda *a,**k:N())
    monkeypatch.setattr(driver,'NativePlayerSession',lambda **k:session)
    monkeypatch.setattr(driver,'_field_ready',lambda _:True)
    monkeypatch.setattr(driver,'authenticate_parent',lambda *a:None)
    monkeypatch.setattr(driver,'verify_pins',lambda _:None)
    monkeypatch.setattr(loans,'_stock',lambda _:state.stock.copy())
    monkeypatch.setattr(options,'boxed_frontier_machine_options',lambda *a,**k:(row,))
    monkeypatch.setattr(driver,'capture_player_continuation',lambda *a,spent,**k:
        dict(spent=spent,state_sha256=sha256(b'terminal').hexdigest()))
    reload_calls=[]
    def reload(*args):
        reload_calls.append(args)
        if reload_mode=='error':raise OSError('native reload failure')
        return dict(passed=reload_mode=='pass',inputs=0,frames=0)
    monkeypatch.setattr(driver,'verify_diagnostic_reload',reload)
    plan=dict(partition='development',diagnostic_only=True,actual_gameplay_resume_authorized=False,
        copy_back=False,fit_allowed=False,seed=11,protected={},objectives=['defeat_champion'],
        required_species=['pokemon:national:148'],cutoff_utc=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),
        owned_machine_options=dict(mode='boxed_frontier_evolution_bundles_v3' if prepared else
            'boxed_frontier_attack_capacity_v2',reason='Bounded native copy qualification'))
    prior=dict(actions=10,frames=20,decisions=3,heals=1,seconds=2.,cash_debits=5)
    driver.verify_boxed_machine_copy(N(actions=100,frames=1000,seconds=10),plan,tmp_path,
        N(c=N(PyBoyAdapter=lambda _:Emulator(),ROM=rom,REPO=tmp_path,
            digest=lambda p:sha256(p.read_bytes()).hexdigest())),
        N(sha256='c'*64,goal_model_sha256='d'*64,to_dict=lambda:{}),
        tmp_path/'parent',dict(state_sha256='b'*64,spent=prior),
        dict(decisions=1,actions=100,frames=1000,heals=4,seconds=10),prepared_evolution=prepared)
    folder=next((tmp_path/'diagnostics').iterdir())
    native=json.loads((folder/'RESULT.json').read_text())
    final=json.loads((folder/'FINAL-RESULT.json').read_text())
    printed=json.loads(capsys.readouterr().out)
    assert native['passed']==(reload_mode!='native_error') and 'reload_passed' not in native
    assert final['passed']==printed['passed']==(reload_mode=='pass')
    assert final['spent']==native['spent']==dict(actions=12,frames=27,decisions=4,
        heals=1,seconds=2.5,cash_debits=18)
    assert final['released'] and final['worker_stopped'] and final['original_roles_restored']
    assert not native['worker_stopped'] and native['checkpoint_lifecycle']['guest_backend_closed'] is False
    assert final['checkpoint_lifecycle']['guest_backend_closed'] is True
    assert final['checkpoint_lifecycle']['host_process_exit_confirmed'] is False
    if reload_mode=='native_error':
        assert reload_calls==[]
        assert final['error']=='retained native failure' and final['error_chain'][0]['error_type']=='RuntimeError'
    else:
        assert len(reload_calls)==1 and reload_calls[0][-2]==state.stock
        assert reload_calls[0][-1]==native['spent']
    assert (folder/'terminal.state').read_bytes()==b'terminal'
    assert len(list(folder.glob('RESULT.json')))==len(list(folder.glob('FINAL-RESULT.json')))==1
    if prepared and reload_mode!='native_error':assert native['recovery_accounting']['passed'] and before!=state.stock
    if reload_mode=='error':
        assert final['reload_error_type']=='OSError'
        assert final['reload_error']=='native reload failure'
        assert final['reload_error_chain'][0]['error_type']=='OSError'
