"""Preserve real training errors and named custody without unsafe PC input."""
import ast
from pathlib import Path
from types import SimpleNamespace as N
import pytest
from pokemon_red_completion import red_native_boxed_evolution as module
from pokemon_red_completion import red_player_party_guard as guard_module

class Guard:
    loanable_refs=frozenset({'retained-original'})
    storage_reader=object()
    def verify_active_roster_restored(self):
        self.calls.append('verify-restored')

def fixture(monkeypatch,battle=1,ready=False):
    monkeypatch.setattr(guard_module,'RedPlayerPartyGuard',Guard)
    calls=[];guard=Guard();guard.calls=calls
    raw=N(battle_state=battle,bag_items=((1,1),),player_money=100)
    collection=N(owned_species=frozenset({'species:a'}),specimens=(N(species_ref='species:a'),))
    observation=N(raw=raw,input_ready=ready,collection_observation=collection,party=N(species_ids=lambda:(59,)))
    runtime=N(adapter=N(party_guard=guard,observe=lambda:observation),evolution_settlement=lambda port:calls.append(('settle',port)),emulator=N(frame_count=0))
    port=N(record_diagnostic_event=lambda kind,payload:calls.append((kind,payload)),actions_executed=0)
    return runtime,port,calls,observation

@pytest.mark.parametrize('battle,ready',[(1,False),(1,True),(0,False)])
@pytest.mark.parametrize('error',[RuntimeError('native faint'),KeyboardInterrupt()])
def test_actual_error_defers_unsettled_custody_without_calling_pc(monkeypatch,battle,ready,error):
    runtime,port,calls,_=fixture(monkeypatch,battle,ready)
    assert module.settle_native_evolution(runtime,port,training_error=error)=={'retained_active_roster_restoration_deferred':True}
    assert len(calls)==1 and calls[0][0]=='native_evolution_settlement_deferred'
    assert calls[0][1]['training_error_type']==type(error).__name__
    assert calls[0][1]['settlement_executed']is False and calls[0][1]['model_queries']==0

@pytest.mark.parametrize('battle,ready',[(1,False),(1,True),(0,False)])
def test_without_training_error_unsettled_boundary_stays_strict(monkeypatch,battle,ready):
    runtime,port,calls,_=fixture(monkeypatch,battle,ready)
    with pytest.raises(module.context.RedGoalContextError,match='settled field control'):
        module.settle_native_evolution(runtime,port)
    assert calls==[]

@pytest.mark.parametrize('bad',[None,False,'invented-proof'])
def test_deferral_cannot_bypass_named_custody(monkeypatch,bad):
    runtime,port,calls,_=fixture(monkeypatch)
    runtime.adapter.party_guard=bad
    with pytest.raises(module.context.RedGoalContextError,match='explicit guarded PC loan'):
        module.settle_native_evolution(runtime,port,training_error=RuntimeError('faint'))
    assert calls==[]

@pytest.mark.parametrize('bad',[False,1,'not an exception'])
def test_deferred_error_requires_real_exception(monkeypatch,bad):
    runtime,port,calls,_=fixture(monkeypatch)
    with pytest.raises(TypeError,match='actual training error'):
        module.settle_native_evolution(runtime,port,training_error=bad)
    assert calls==[]

@pytest.mark.parametrize('error',[None,RuntimeError('settled failure')])
def test_settled_error_and_success_keep_guarded_settlement(monkeypatch,error):
    runtime,port,calls,_=fixture(monkeypatch,0,True)
    assert module.settle_native_evolution(runtime,port,training_error=error)=={'retained_active_roster_restored':True}
    assert calls==[('settle',port),'verify-restored']

@pytest.mark.parametrize('error',[RuntimeError('native active faint'),KeyboardInterrupt()])
def test_real_resume_propagates_original_error_object_after_deferral(monkeypatch,error):
    runtime,port,calls,observation=fixture(monkeypatch,0,True)
    source=Path(module.__file__).read_text()
    node=next(n for n in ast.walk(ast.parse(source))if isinstance(n,ast.FunctionDef)and n.name=='resume'and n.args.args[0].arg=='source_id')
    def train(*args):
        observation.raw.battle_state=1;observation.input_ready=False
        raise error
    ns=dict(vars(module),runtime=runtime,readiness=lambda _:N(executable=True),spec=N(parameters={'source_species_ref':'pokemon:national:050','target_species_ref':'pokemon:national:051'}),train=train)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'actual-resume-function','exec'),ns)
    with pytest.raises(type(error))as raised:ns['resume'](59,118,port)
    assert raised.value is error and raised.value.__context__ is None
    assert len(calls)==1 and calls[0][0]=='native_evolution_settlement_deferred'
