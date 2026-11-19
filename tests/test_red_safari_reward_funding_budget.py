from copy import deepcopy
from types import SimpleNamespace as N
import pytest
from pokemon_red_completion import red_player_safari_rewards as s


@pytest.mark.parametrize('place', ['city','center_entrance','center_stance'])
@pytest.mark.parametrize('fault', [None,'funds','bag','fulfilled','not_ready','no_objective','no_approach','wrong_map'])
def test_reward_admission_demand_requires_supported_nonmoney_path(monkeypatch,place,fault):
    raw=N(map_id=int(s.MapId.FUCHSIA_CITY) if place=='city' else int(s.MapId.FUCHSIA_POKECENTER),
        player_y=3 if place=='center_stance' else 4,player_x=3 if place=='center_stance' else 18,
        party_moves=((33,39,145,55),),player_money=157,event_flags=(),bag_items=((3,8),))
    if fault=='funds':raw.player_money=500
    if fault=='bag':raw.bag_items=tuple((i,1) for i in range(1,20))
    if fault=='fulfilled':raw.bag_items=((int(s.ItemId.HM04_STRENGTH),1),)
    if fault=='wrong_map':raw.map_id=0
    available=[] if fault=='no_objective' else [N(id='obtain_surf')]
    rt=N(reader=N(read=lambda:deepcopy(raw)),adapter=N(observe=lambda:N(game_state='observed'),
        graph=N(available_objectives=lambda state:available)))
    monkeypatch.setattr(s,'_field_ready',lambda rt:fault!='not_ready')
    monkeypatch.setattr(s,'event_flag_is_set',lambda flags,e:e in flags)
    calls=[];route=object();actions=N(execute=lambda _:pytest.fail('quote sent native input'))
    def quote(runtime,executor,**kw):
        assert runtime is rt and executor is actions and kw['route'] is route
        calls.append(kw)
        assert kw==dict(objective_id='obtain_surf',route=route,
            **({'route_destination_at':(3,3)} if place=='city' else {'destination_at':(3,3)}))
        return None if fault=='no_approach' else N(execute=lambda:pytest.fail('quote executed approach'))
    monkeypatch.setattr(s,'story_travel_binding',quote)
    before=deepcopy(raw)
    result=s.safari_reward_admission_funding_budget(rt,actions,route=route,party_slot=1,replace_slot=3)
    assert vars(raw)==vars(before)
    expected=fault is None or(fault=='no_approach'and place=='center_stance')
    if expected:
        assert(result.available_funds,result.cost,result.target_cash,result.shortfall)==(157,500,500,343)
        assert len(calls)==(0 if place=='center_stance' else 1)
    else:assert result is None


@pytest.mark.parametrize('party_slot,replace_slot',[(0,1),(2,1),(True,1),(1,0),(1,5),(1,True)])
def test_admission_demand_does_not_guess_missing_lesson_slots(monkeypatch,party_slot,replace_slot):
    raw=N(player_money=157,map_id=int(s.MapId.FUCHSIA_POKECENTER),bag_items=(),event_flags=(),party_moves=((33,39,145,55),))
    rt=N(reader=N(read=lambda:raw))
    monkeypatch.setattr(s,'_field_ready',lambda _:True)
    monkeypatch.setattr(s,'story_travel_binding',lambda *a,**k:pytest.fail('invalid lesson quoted approach'))
    assert s.safari_reward_admission_funding_budget(rt,None,route=None,party_slot=party_slot,replace_slot=replace_slot)is None
