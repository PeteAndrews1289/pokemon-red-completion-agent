"""Verify the real postgame provider forwards its existing medicine quote."""
import ast,os
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from pokemon_red_completion.observation import ItemId

def callbacks(raw, enabled=True):
    source=Path(os.environ.get('POKEMON_CORNER_HELPER_SOURCE',Path(__file__).resolve().parents[1]/'runtime_helpers/red_whole_player_inventory_20261006.py'))
    names={'income_reserve_cost','postgame_corner_reserve_cost','postgame_corner_options'}
    funcs=[node for node in ast.parse(source.read_text()).body if isinstance(node,ast.FunctionDef)and node.name in names]
    calls=[]
    def provider(*args,**kwargs):calls.append(kwargs);return ()
    scope=dict(ItemId=ItemId,game_corner_options=provider,game_corner_coin_options=provider)
    exec(compile(ast.Module(body=funcs,type_ignores=[]),str(source),'exec'),scope)
    runtime=NS(reader=NS(read=lambda:raw),adapter=NS(observe=lambda:NS(raw=raw)),league_battle_controller=None if enabled is None else NS(income_owned_stock_bootstrap=enabled))
    return scope,runtime,calls

def raw(fr=0,revives=0,cures=1,badges=255):
    return NS(badge_bits=badges,player_money=27335,bag_items=tuple((int(i),q)for i,q in ((ItemId.FULL_RESTORE,fr),(ItemId.REVIVE,revives),(ItemId.FULL_HEAL,cures))if q))

@pytest.mark.parametrize('stock,expected',[((0,0,1),10500),((1,2,0),5100),((2,3,1),0),((0,0,0),11100)])
def test_existing_entry_reserve_reaches_both_real_provider_calls(stock,expected):
    scope,rt,calls=callbacks(raw(*stock))
    assert scope['postgame_corner_options'](rt,object(),NS(situation=object()),object())==()
    assert len(calls)==2
    assert all(call['cash_reserve']==expected for call in calls)

@pytest.mark.parametrize('enabled',[False,None,0])
def test_ordinary_profiles_preserve_zero_reserve(enabled):
    scope,rt,calls=callbacks(raw(),enabled)
    scope['postgame_corner_options'](rt,object(),NS(situation=object()),object())
    assert len(calls)==2 and all(call['cash_reserve']==0 for call in calls)

def test_earlier_story_is_unchanged():
    scope,rt,calls=callbacks(raw(badges=127))
    assert scope['postgame_corner_options'](rt,object(),NS(situation=object()),object())==()
    assert not calls
