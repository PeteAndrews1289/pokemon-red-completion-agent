from hashlib import sha256
from types import SimpleNamespace as NS
import sys
import pytest
from test_red_live_option_menu import _binding
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_player_configuration import _retained_capture_inventory


def fixture(tmp_path,monkeypatch,*,battle=1,state=b"exact",journal=True):
    (tmp_path/'terminal.state').write_bytes(b"exact")
    if journal:
        d=tmp_path/'snorlax-original/001-paused';d.mkdir(parents=True)
        (d/'receipt.json').write_text('{}')
    rt=NS(reader=NS(read=lambda:NS(battle_state=battle)),
          emulator=NS(save_state_bytes=lambda:state))
    calls=[]
    binding=_binding(GoalKind.RECOVER_CONTROL,
        binding_ref='pokemon.red:retained-capture:'+sha256(state).hexdigest(),calls=[])
    def restore(runtime,actions,*,parent,output):
        calls.append((runtime,actions,parent,output));return binding
    module=NS(retained_capture_binding=restore)
    monkeypatch.setitem(sys.modules,'red_earned_run_completion_20261005',module)
    return rt,calls,binding,module


def test_exact_retained_journal_precedes_ordinary_escape_without_execution(tmp_path,monkeypatch):
    rt,calls,binding,_=fixture(tmp_path,monkeypatch)
    actions=object()
    result=_retained_capture_inventory(rt,actions,parent=tmp_path,output=tmp_path/'out')
    assert result.bindings==(binding,)
    assert len(result.opportunities)==2
    assert len(calls)==1 and calls[0][0]is rt and calls[0][1]is actions


@pytest.mark.parametrize('battle,state,journal',[(0,b'exact',True),(2,b'exact',True),(1,b'different',True),(1,b'exact',False)])
def test_unrelated_state_or_absent_journal_never_invokes_capture(tmp_path,monkeypatch,battle,state,journal):
    rt,calls,_,_=fixture(tmp_path,monkeypatch,battle=battle,state=state,journal=journal)
    assert _retained_capture_inventory(rt,object(),parent=tmp_path,output=tmp_path/'out')is None
    assert not calls


@pytest.mark.parametrize('fault',['none','kind','reference'])
def test_capture_callback_cannot_replace_exact_retained_binding(tmp_path,monkeypatch,fault):
    rt,_,_,module=fixture(tmp_path,monkeypatch)
    binding=None if fault=='none'else _binding(
        GoalKind.ACQUIRE_SPECIES if fault=='kind'else GoalKind.RECOVER_CONTROL,
        binding_ref='pokemon.red:retained-capture:'+('0'*64 if fault=='reference'else sha256(b'exact').hexdigest()),calls=[])
    module.retained_capture_binding=lambda *a,**kw:binding
    with pytest.raises(ValueError,match='exact verified binding'):
        _retained_capture_inventory(rt,object(),parent=tmp_path,output=tmp_path/'out')


def test_receipt_authentication_error_propagates_without_escape_fallback(tmp_path,monkeypatch):
    rt,_,_,module=fixture(tmp_path,monkeypatch)
    def invalid(*a,**kw):raise ValueError('capture allocation mismatch')
    module.retained_capture_binding=invalid
    with pytest.raises(ValueError,match='allocation mismatch'):
        _retained_capture_inventory(rt,object(),parent=tmp_path,output=tmp_path/'out')
