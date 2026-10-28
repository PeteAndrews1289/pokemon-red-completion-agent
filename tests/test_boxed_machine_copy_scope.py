from datetime import datetime,timezone,timedelta
from types import SimpleNamespace as N
import json
import pytest
import run_configured_red_player as driver


def plan():
    return dict(partition='development',diagnostic_only=True,
        actual_gameplay_resume_authorized=False,copy_back=False,fit_allowed=False,
        cutoff_utc=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),
        owned_machine_options=dict(mode='boxed_frontier_attack_capacity_v2',reason='Native copy qualification'))


@pytest.mark.parametrize('changes',[
    dict(diagnostic_only=False),dict(actual_gameplay_resume_authorized=True),
    dict(copy_back=True),dict(fit_allowed=True),dict(partition='sealed'),
    dict(owned_machine_options=None),
    dict(owned_machine_options=dict(mode='direct_attack_capacity_v1',reason='Old party-only scope'))])
def test_operator_copy_cannot_enter_an_actual_or_undeclared_scope(tmp_path,changes):
    p=plan();p.update(changes)
    with pytest.raises(ValueError):
        driver.verify_boxed_machine_copy(N(),p,tmp_path,N(c=N()),N(),None,None,None)
    assert list(tmp_path.iterdir())==[]


def test_boxed_copy_retains_common_wiring_and_finite_clipped_limits(tmp_path,monkeypatch):
    class BeforeEmulator(Exception):pass
    seen={}
    def assemble(*a,plan_path,**k):
        seen.update(json.loads(plan_path.read_text()));raise BeforeEmulator
    monkeypatch.setattr(driver,'assemble_configured_player',assemble)
    p=plan()
    with pytest.raises(BeforeEmulator):
        driver.verify_boxed_machine_copy(N(actions=6000,frames=600000,seconds=180),p,
            tmp_path,N(c=N(digest=lambda _: 'd'*64)),
            N(sha256='c'*64,to_dict=lambda:dict(goal_model_sha256='e'*64)),
            tmp_path/'parent',dict(state_sha256='b'*64,spent={}),
            dict(decisions=1,actions=5000,frames=400000,seconds=120,heals=4))
    assert seen['owned_machine_options']==p['owned_machine_options']
    assert seen['configuration_sha256']=='c'*64
    assert seen['limits']['actions']==5000 and seen['limits']['frames']==400000
    assert seen['limits']['decisions']==1 and seen['limits']['seconds']==120
    assert seen['operator_diagnostic_choice'] and seen['goal_model_queries']==0
    assert seen['copy_back'] is False and seen['fit_allowed'] is False


@pytest.mark.parametrize("observed_debits",[0,13])
@pytest.mark.parametrize("prepared_evolution",[False,True])
def test_boxed_copy_constructs_real_curriculum_and_retains_execution_failure(tmp_path,monkeypatch,observed_debits,prepared_evolution):
    from hashlib import sha256
    import pokemon_red_completion.red_boxed_machine_options as options
    import pokemon_red_completion.red_player_party_loan as loans

    class Emulator:
        pressed_buttons=set()
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def load_state_bytes(self,payload):assert payload==b"source"
        def save_state_bytes(self):return b"exact-tail"

    rom=tmp_path/'fixture.rom';rom.write_bytes(b'fixture-only')
    guard=N(refs=('combat',),reader=N(preparation_specimen_refs=lambda:('combat',)),
        verify_active_roster_restored=lambda:None)
    runtime=N(adapter=N(party_guard=guard,observe=lambda:N()))
    session=N(runtime=runtime,actions=N(observe_cash=lambda:1,observed_cash_debits=observed_debits,
        observed_cash_rewards=27,observed_cash_changes=3),recorder=N(enabled=False,trace=[1,2]),
        controller=N(input_enabled=True,frames_executed=7),wall=N(elapsed_seconds=.5),
        heals=0,training_healing_trips=0,support_restorations=0)
    holder=dict(plan=N(roster=(N(specimen_ref='combat',purpose=N(value='combat')),)),
        observe_history=lambda:None,configured_route=N(route_world='observed-world'))
    monkeypatch.setattr(driver,'assemble_configured_player',lambda *a,**k:
        (b'source',lambda _:None,None,holder,N()))
    monkeypatch.setattr(driver,'initialize_private_root',lambda *a,**k:N())
    constructed={}
    def build(**kwargs):constructed.update(kwargs);return session
    monkeypatch.setattr(driver,'NativePlayerSession',build)
    connected={}
    def connect(menu,plan,**kwargs):
        connected.update(plan)
        assert prepared_evolution
    monkeypatch.setattr(driver,'connect_declared_machine_options',connect)
    monkeypatch.setattr(driver,'_field_ready',lambda _:True)
    monkeypatch.setattr(driver,'authenticate_parent',lambda *a:None)
    monkeypatch.setattr(driver,'verify_pins',lambda _:None)
    monkeypatch.setattr(loans,'_stock',lambda _:('unchanged-stock',))
    def failed_lesson():
        try:raise OSError('native typed cause')
        except OSError as cause:raise RuntimeError('native lesson failure') from cause
    row=N(binding=N(binding_ref='pokemon.red:prepared-evolution:fixture' if prepared_evolution else 'fixture',execute=failed_lesson),
        candidate=N(features=N(dependency_unlock_gain=.5)))
    monkeypatch.setattr(options,'boxed_frontier_machine_options',lambda *a,**k:(row,))
    monkeypatch.setattr(driver,'capture_player_continuation',lambda *a,spent,**k:
        dict(spent=spent,state_sha256=sha256(b'exact-tail').hexdigest()))
    if prepared_evolution:
        monkeypatch.setattr(driver,'assemble_configured_player',lambda *a,**k:
            (b'source',lambda _:None,N(enumerate_collection=lambda *a:(row,)),holder,N()))
    p=plan()
    if prepared_evolution:
        p['owned_machine_options']['mode']='boxed_frontier_evolution_bundles_v3'
    p.update(objectives=['defeat_champion'],required_species=['pokemon:national:147'],
        seed=11,protected={})
    prior=dict(actions=10,frames=20,decisions=3,heals=1,seconds=2.,cash_debits=5)
    driver.verify_boxed_machine_copy(N(actions=100,frames=1000,seconds=10),p,tmp_path,
        N(c=N(PyBoyAdapter=lambda _:Emulator(),ROM=rom,REPO=tmp_path,
            digest=lambda q:sha256(q.read_bytes()).hexdigest())),
        N(sha256='c'*64,goal_model_sha256='d'*64,to_dict=lambda:{}),
        tmp_path/'parent',dict(state_sha256='b'*64,spent=prior),
        dict(decisions=1,actions=100,frames=1000,heals=4,seconds=10),
        prepared_evolution=prepared_evolution)
    assert bool(connected)==prepared_evolution
    assert constructed['combat_specimen_refs']==('combat',)
    assert constructed['curriculum'].required_species==('pokemon:national:147',)
    folder=next(tmp_path.glob('diagnostics/prepared-evolution-*' if prepared_evolution else 'diagnostics/boxed-machine-*'))
    result=json.loads((folder/'RESULT.json').read_text())
    assert not result['passed'] and result['error']=='native lesson failure'
    assert [x['error_type'] for x in result['error_chain']]==['RuntimeError','OSError']
    assert result['model_queries']==0 and result['actions']==2 and result['frames']==7
    assert result['spent']==dict(actions=12,frames=27,decisions=4,heals=1,seconds=2.5,cash_debits=5+observed_debits)
    assert result['released'] and result['original_roles_restored']
    assert not session.controller.input_enabled and not session.recorder.enabled
    assert (folder/'terminal.state').read_bytes()==b'exact-tail'
