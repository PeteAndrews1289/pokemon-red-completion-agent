"""Same-guest custody survives logical chunk renewal without weakening reload ancestry."""
from dataclasses import replace
from types import SimpleNamespace as N
import hashlib,json
import pytest
from test_red_player_configuration import config
from test_red_live_option_menu import _binding
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.party import PartyMemberObservation,PartyObservation
from pokemon_red_completion.red_player_party_guard import RedPlayerPartyGuard
from pokemon_red_completion import red_player_configuration as module

def fixture(monkeypatch):
    backend=object();em=N(_backend=backend,frame_count=100,pressed_buttons=frozenset(),save_state_bytes=lambda:b"live")
    refs=tuple([*(f"retained-{i}"for i in range(5)),"reserve-individual"])
    before=PartyObservation(tuple(PartyMemberObservation(i+1,i+1,17,40,40,experience=5000)for i in range(6)))
    guest=PartyMemberObservation(6,7,18,0,42,experience=5500)
    active=PartyObservation(before.members[:5]+(guest,));active_refs=refs[:5]+("guest",)
    reader=N(memory=em,read=lambda:active,preparation_specimen_refs=lambda:active_refs)
    boxed=N(preparation_ref=refs[-1],species_id=6,level=17,experience=5000)
    storage=N(read_box_specimen_identities=lambda:(boxed,),read=lambda:N(battle_state=0))
    guard=RedPlayerPartyGuard(reader,before,refs,frozenset(),storage,frozenset({refs[-1]}))
    previous=N(emulator=em,adapter=N(party_guard=guard));runtime=N(emulator=em,reader=storage,adapter=N(party_guard=guard))
    monkeypatch.setattr('pokemon_red_completion.red_party.PokemonRedPartyReader',lambda controller:reader)
    context=dict(preparation=dict(roster=[dict(specimen_ref=r)for r in refs]))
    return runtime,previous,context,guard,boxed

@pytest.mark.parametrize("fault",[None,"other_guest","foreign_reader","wrong_refs","duplicate_refs","wrong_loan","held_input","xp_loss","lost_box","mutating_reader"])
def test_live_loan_keeps_baseline_and_requires_same_guest_custody(monkeypatch,fault):
    runtime,previous,context,old,boxed=fixture(monkeypatch)
    if fault=='other_guest':previous=N(emulator=N(_backend=object(),frame_count=100,save_state_bytes=lambda:b"live"),adapter=previous.adapter)
    if fault=='foreign_reader':old.reader.memory=N(_backend=object())
    if fault=='wrong_refs':context['preparation']['roster'][-1]['specimen_ref']='foreign'
    if fault=='duplicate_refs':context['preparation']['roster'][-1]['specimen_ref']='retained-0'
    if fault=='wrong_loan':previous.adapter.party_guard=replace(old,loanable_refs=frozenset({'retained-0'}))
    if fault=='held_input':runtime.emulator.pressed_buttons=frozenset({'a'})
    if fault=='xp_loss':boxed.experience=4999
    if fault=='lost_box':runtime.reader.read_box_specimen_identities=lambda:()
    if fault=='mutating_reader':
        def census():
            runtime.emulator.frame_count+=1
            return(boxed,)
        runtime.reader.read_box_specimen_identities=census
    if fault:
        with pytest.raises(ValueError):module._same_guest_pending_loan_guard(runtime,previous,config(),context)
    else:
        guard=module._same_guest_pending_loan_guard(runtime,previous,config(),context)
        assert guard is not old and guard.before is old.before and guard.refs==old.refs
        assert guard.loanable_refs==old.loanable_refs and guard.storage_reader is runtime.reader
        assert runtime.emulator.frame_count==100 and not runtime.emulator.pressed_buttons
        assert boxed.experience==5000

@pytest.mark.parametrize("fault",[None,"legacy_stopped","schema","state","binding","unqualified","not_loan","not_field","input","frames","queries","substitution","unknown_reason"])
def test_next_chunk_admits_only_exact_qualified_live_faint(tmp_path,monkeypatch,fault):
    runtime,previous,context,guard,boxed=fixture(monkeypatch)
    state=b'live';digest=hashlib.sha256(state).hexdigest();(tmp_path/'terminal.state').write_bytes(state)
    handoff=dict(schema='pokemon.red.qualified-native-control-handoff.v1',qualified=True,retained_declared_loan=True,field_faint_before_pc_return=True,state_sha256=digest,binding_ref='pokemon.red:retained-motion:'+digest,strategic_substitution=False,inputs=0,frames=0,model_queries=0)
    result=dict(worker_stopped=False,live_driver_running=True,state_sha256=digest,continuation_reason='automatic_control_recovery',released=True,checkpoint_lifecycle=dict(schema='pokemon.red.checkpoint-quiescence.v1',scope='live_chunk',chunk_complete=True,inputs_released=True,guest_backend_closed=False,unexpected_guest_closure=False,host_process_exit_confirmed=False),episode=dict(outcomes=[dict(selected_kind='evolve_species',error_type='RedGoalContextError',error='PC loan settlement requires settled field control')]),qualified_native_control_handoff=handoff)
    if fault=='legacy_stopped':result.update(continuation_reason='native_execution_error',qualified_native_control_handoff=None)
    for name,key,val in [('schema','schema','unknown'),('state','state_sha256','0'*64),('binding','binding_ref','foreign'),('unqualified','qualified',False),('not_loan','retained_declared_loan',False),('not_field','field_faint_before_pc_return',False),('input','inputs',1),('frames','frames',1),('queries','model_queries',1),('substitution','strategic_substitution',True)]:
        if fault==name:handoff[key]=val
    if fault=='unknown_reason':result['continuation_reason']='generic_resume'
    (tmp_path/'RESULT.json').write_text(json.dumps(result));(tmp_path/'native').mkdir();(tmp_path/'native/diagnostic-events.json').write_text(json.dumps(dict(events=[])));(tmp_path/'native/native-costs.json').write_text(json.dumps(dict(frames=5)))
    seen=[];binding=_binding(GoalKind.RECOVER_CONTROL,binding_ref='pokemon.red:retained-motion:'+digest,calls=[])
    monkeypatch.setattr('pokemon_red_completion.red_player_forced_motion.retained_field_faint_binding',lambda *a,**k:seen.append(k)or binding)
    inventory=module._retained_field_faint_inventory(runtime,N(),parent=tmp_path)
    if fault in(None,'legacy_stopped'):
        assert inventory.bindings==(binding,)and len(seen)==1
        assert seen[0]['prior_native_boundary']['named_loan_verified']is True
    else:assert inventory is None and not seen


def test_live_loan_accepts_restricted_native_ports_without_exposing_backend(monkeypatch):
    from pokemon_red_completion.executor import NativeLessonController,MonotonicWallTimeBudgetController,ReadOnlyController
    runtime,previous,context,guard,boxed=fixture(monkeypatch)
    raw=runtime.emulator
    native=NativeLessonController(MonotonicWallTimeBudgetController(raw,maximum_wall_seconds=30),maximum_frames=1000)
    readonly=ReadOnlyController(raw)
    previous.emulator=native;guard.reader.memory=native;runtime.emulator=readonly
    with pytest.raises(AttributeError):getattr(native,'_backend')
    renewed=module._same_guest_pending_loan_guard(runtime,previous,config(),context)
    assert renewed.before is guard.before and renewed.refs==guard.refs
    assert raw.frame_count==100 and not raw.pressed_buttons


@pytest.mark.parametrize('fault',[None,'different_guest','closed','unknown_wrapper','cycle'])
def test_controller_guest_identity_compares_owners_not_identical_states(fault):
    from pokemon_red_completion.executor import ReadOnlyController,NativeLessonController,MonotonicWallTimeBudgetController,shares_live_controller_guest
    raw=N(_backend=object(),frame_count=0,pressed_buttons=frozenset(),save_state_bytes=lambda:b'same')
    left=ReadOnlyController(raw);right=NativeLessonController(MonotonicWallTimeBudgetController(raw,maximum_wall_seconds=30),maximum_frames=100)
    if fault=='different_guest':right=ReadOnlyController(N(_backend=object(),frame_count=0,save_state_bytes=lambda:b'same'))
    if fault=='closed':raw._backend=None
    if fault=='unknown_wrapper':right=N(_delegate=raw)
    if fault=='cycle':right=ReadOnlyController(raw);right._delegate=right
    assert shares_live_controller_guest(left,right)is(fault is None)
