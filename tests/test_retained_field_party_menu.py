from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_gen1_route_runtime import raw

from pokemon_red_completion import red_player_forced_motion as motion
from pokemon_red_completion.actions import MacroActionKind


def setup(monkeypatch,*,fault=None,signature=('party',0)):
    initial=replace(raw(),battle_state=0,party_count=1,party_hp=(5,),party_max_hp=(5,),
                    party_pp=((5,),),party_moves=((1,),),party_status=(0,),player_money=1053)
    live=dict(raw=initial,party=True,start=False,actions=[],custody=('unchanged',),extra=False)
    def save():return repr((live['raw'],live['party'],live['start'],live['extra'])).encode()
    emulator=SimpleNamespace(frame_count=0,pressed_buttons=(),save_state_bytes=save)
    reader=SimpleNamespace(read=lambda:live['raw'],read_npc_trade_input=lambda:signature if live['party']else None,
        read_bottom_dialogue_box_visible=lambda:live['party'],trainer_engagement_active=lambda:False)
    class Actions:
        actions_executed=0
        def execute(self,action):
            assert action.kind in {MacroActionKind.CANCEL,MacroActionKind.WAIT}
            self.actions_executed+=1;live['actions'].append(action.kind);emulator.frame_count+=1
            if action.kind is MacroActionKind.CANCEL:
                if fault=='bound':return
                if live['party']:live['party'],live['start']=False,True
                else:live['start']=False
                if fault=='cash':live['raw']=replace(initial,player_money=1054)
                if fault=='pp':live['raw']=replace(initial,party_pp=((4,),))
                if fault=='relocation':live['raw']=replace(initial,player_x=initial.player_x+1)
                if fault=='custody':live['custody']=('changed',)
    monkeypatch.setattr(motion,'_field_ready',lambda rt:not live['party']and not live['start'])
    monkeypatch.setattr(motion,'capture_player_lesson_snapshot',lambda rt:(None,dict(objectives=['same'])))
    monkeypatch.setattr(motion,'_purified_message_custody',lambda rt:live['custody'])
    rt=SimpleNamespace(reader=reader,emulator=emulator);return rt,Actions(),live


def test_retained_field_party_cancel_is_exact_once_and_never_selects_member(monkeypatch):
    rt,actions,live=setup(monkeypatch)
    binding=motion.interrupted_motion_binding(rt,actions,rom=b'rom',maximum_waits=4)
    assert binding.binding_ref.startswith('pokemon.red:retained-motion:')
    report=binding.execute();assert binding.verify(report).status.value=='succeeded'
    assert report.evidence['confirms']==report.evidence['model_queries']==0
    assert live['actions']==[MacroActionKind.CANCEL,MacroActionKind.WAIT]*2
    with pytest.raises(ValueError,match='stale or consumed'):binding.execute()


@pytest.mark.parametrize('fault',['cash','pp','relocation','custody','bound'])
def test_cancel_rejects_unexpected_changes_or_unclosed_menu(monkeypatch,fault):
    rt,actions,live=setup(monkeypatch,fault=fault)
    binding=motion.interrupted_motion_binding(rt,actions,rom=b'rom',maximum_waits=4)
    with pytest.raises(RuntimeError):binding.execute()


@pytest.mark.parametrize('signature',[None,('offer',0),('party',True),('party',-1),('party',1)])
def test_only_real_bounded_party_chooser_signature_is_admitted(monkeypatch,signature):
    rt,actions,live=setup(monkeypatch,signature=signature)
    assert motion._interrupted_field_party_menu_binding(rt,actions,maximum_cancels=4,settle_frames=30)is None
    assert not live['actions']


def test_stale_source_rejects_before_input(monkeypatch):
    rt,actions,live=setup(monkeypatch)
    binding=motion.interrupted_motion_binding(rt,actions,rom=b'rom')
    live['extra']=True
    with pytest.raises(ValueError,match='stale'):binding.execute()
    assert not live['actions']
