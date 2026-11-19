from hashlib import sha256
import json
from types import SimpleNamespace as Namespace
import pytest
import run_configured_red_player as driver
from pokemon_red_completion import red_player_configuration as config
from pokemon_red_completion import red_player_field_blackout as provider
from pokemon_red_completion.goal_manager import GoalKind
from test_red_live_option_menu import _binding


@pytest.mark.parametrize('fault', [None, 'survivor', 'battle', 'foreign_route', 'wrong_checkpoint',
                                    'uncertain', 'wrong_reason', 'unreleased', 'buttons', 'claimed_credit',
                                    'wrong_receipt', 'different_guest', 'stale_marker', 'prior_error'])
def test_routed_field_loss_requires_a_witnessed_unchanged_singleton(monkeypatch,tmp_path,fault):
    state=b'held blackout'
    digest=sha256(state).hexdigest()
    error='observed all-party field poison faint requires native blackout'
    last=dict(selected_kind='restore_team',error_type='Gen1FieldBlackoutPending',error=error,
              error_chain=[dict(error_type='Gen1FieldBlackoutPending',error=error,reason_code='world_state_diverged')],
              ordinal=0,before_state_sha256='a'*64,terminal_state_sha256=digest,safe_terminal=True,failure_phase='execution')
    result=dict(episode=dict(outcomes=[last],stop_reason='execution_failed'),field_ready=False,released=True,
                worker_stopped=True,paired_context_authenticated=True,state_sha256=digest)
    choice=dict(selected_kind='restore_team',selected_binding_ref='pokemon.red:routed-restoration:held',state_sha256='a'*64)
    em=Namespace(save_state_bytes=lambda:state,frame_count=42,pressed_buttons=set())
    raw=Namespace(party_hp=(0,),battle_state=0)
    runtime=Namespace(emulator=em,reader=Namespace(read=lambda:raw))
    if fault=='survivor':raw.party_hp=(0,27)
    if fault=='battle':raw.battle_state=1
    if fault=='foreign_route':choice['selected_binding_ref']='different'
    if fault=='wrong_checkpoint':choice['state_sha256']='b'*64
    if fault=='uncertain':last['safe_terminal']=False
    if fault=='wrong_reason':last['error_chain'][0]['reason_code']='other'
    if fault=='unreleased':result['released']=False
    if fault=='buttons':em.pressed_buttons.add('A')
    if fault=='prior_error':result['episode']['outcomes'].insert(0,{'error_type':'unrelated'})
    root=tmp_path/'native/episode/step-000';root.mkdir(parents=True)
    (root/'execution-started.json').write_text(json.dumps(choice))
    (tmp_path/'terminal.state').write_bytes(b'foreign state' if fault=='different_guest' else state)
    monkeypatch.setattr(driver,'_field_ready',lambda runtime:False)
    binding=_binding(GoalKind.RECOVER_CONTROL,binding_ref='pokemon.red:field-blackout:'+digest,calls=[])
    monkeypatch.setattr(provider,'field_blackout_binding',lambda runtime,actions:binding)
    plan=dict(partition='development',official_acceptance=False,fit_allowed=False,copy_back=False,force_resource_safety=True,
              diagnostic_only=True,new_campaign=False)
    receipt=driver.qualified_menu_control_handoff(result,runtime=runtime,menu=None,retained_parent=tmp_path,
                                                   catcher_plan=plan,failure_reason='native_execution_error')
    if fault not in (None,'claimed_credit','wrong_receipt','stale_marker'):
        assert receipt is None
        return
    assert receipt['retained_field_blackout'] and receipt['failed_transport_preserved']
    assert receipt['inputs']==receipt['frames']==receipt['model_queries']==0 and em.frame_count==42
    if fault=='claimed_credit':receipt['strategic_substitution']=True
    if fault=='wrong_receipt':receipt['failed_outcome_sha256']='0'*64
    if fault=='stale_marker':receipt['state_sha256']='f'*64
    result.update(continuation_reason='automatic_control_recovery',qualified_native_control_handoff=receipt)
    (tmp_path/'RESULT.json').write_text(json.dumps(result))
    inventory=config._retained_field_blackout_inventory(runtime,None,parent=tmp_path)
    if fault is None:
        assert inventory.bindings==(binding,)
    else:
        assert inventory is None
