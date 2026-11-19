import json
from hashlib import sha256
from types import SimpleNamespace as N
import pytest
import run_configured_red_player as driver


@pytest.mark.parametrize('error_class', [KeyboardInterrupt, SystemExit])
def test_interruption_preserves_closed_rows_costs_hashes_and_original_error(tmp_path, monkeypatch, error_class):
    payload = b'paid-tail'; digest = sha256(payload).hexdigest()
    native = tmp_path/'native'; native.mkdir()
    meter = dict(actions_attempted=2, actions_completed=2, frames=8, goal_attempts=2,
                 seconds=1.5, restore_attempts=0, control_recovery_cash_debits=0)
    (native/'native-costs.json').write_text(json.dumps(meter))
    rows = [dict(ordinal=i, before_state_sha256='a'*64, terminal_state_sha256=digest,
                 selected_kind='advance_story', before={'cash':100}, after={'cash':100},
                 verification='succeeded' if i==0 else None,
                 observed_cost=dict(actions=1,frames=4,cash_spent=0),
                 error_type=None if i==0 else error_class.__name__,
                 error_chain=None if i==0 else [{'error_type':error_class.__name__,'error':'interrupted'}])
            for i in range(2)]
    for i,row in enumerate(rows):
        step=native/'episode'/f'step-{i:03d}';step.mkdir(parents=True)
        (step/'outcome.json').write_text(json.dumps(row))
    def run(**kwargs): raise error_class('interrupted')
    monkeypatch.setattr(driver,'run_native_continuous_player',run)
    monkeypatch.setattr(driver,'native_player_options',lambda *args:
                        dict(greedy_selection=True,resume_branch_refinement_after_settlement=False))
    monkeypatch.setattr(driver,'player_wiring_declaration',lambda *args: {})
    monkeypatch.setattr(driver,'_field_ready',lambda *args: True)
    monkeypatch.setattr(driver,'native_checkpoint_facts',lambda *args: {})
    def capture(*args,spent,**kwargs):
        return dict(schema=driver.PLAYER_CONTINUATION_SCHEMA,state_sha256=digest,
                    lesson={'completed_objectives':[]},cash=100,bag=[],preparation=None,
                    battle=None,spent=spent,grants_new_budget=False,fit_allowed=False)
    monkeypatch.setattr(driver,'capture_player_continuation',capture)
    holder=dict(plan=N(roster=()),prior_spent=dict(decisions=0,actions=0,frames=0,
                seconds=0.,heals=0,cash_debits=0),observe_history=lambda **kw:None,
                runtime=N(reader=N(read=lambda:N(player_money=100,map_id=64,
                                                player_y=3,player_x=3,party_levels=(20,)))))
    result,context=driver.execute_player_chunk(plan={'seed':1},configuration=N(sha256='c'*64),
            c=N(digest=lambda p:sha256(p.read_bytes()).hexdigest()),
            emulator=N(frame_count=8,pressed_buttons=(),save_state_bytes=lambda:payload),
            factory=None,menu=None,holder=holder,source=None,output=tmp_path,
            model=N(model_sha256='d'*64),limits=driver.NativePlayerLimits(
                decisions=24,actions=24000,frames=2400000,seconds=600,heals=16,cash_debits=None),
            memory=None,store=None,ordinal=1)
    assert result['passed'] is False and result['error_type']==error_class.__name__
    assert result['error_chain']==[{'error_type':error_class.__name__,'error':'interrupted'}]
    assert result['episode']['outcomes']==rows and result['episode']['executed_decisions']==2
    assert result['episode']['complete_episode'] is False
    assert result['spent']==context['spent']==dict(decisions=2,actions=2,frames=8,
                                                  seconds=1.5,heals=0,cash_debits=0)
    assert result['paired_context_authenticated'] and result['released']
    assert driver.chunk_continuation_reason(result,source_sha256='a'*64)=='native_execution_error'
