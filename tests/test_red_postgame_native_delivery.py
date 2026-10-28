from types import SimpleNamespace as N

import pytest


@pytest.mark.parametrize('fault',[None,'map','defeated','missing_event','object','position','identity'])
def test_dojo_master_contract_authenticates_existing_script_not_a_sight_header(monkeypatch,fault):
    from pokemon_red_completion import red_scripted_story_trainer as m
    from pokemon_red_completion.observation import EventFlag
    flags=bytearray(320)
    if fault=='defeated':
        flags[int(EventFlag.BEAT_KARATE_MASTER)//8] |= 1 << (int(EventFlag.BEAT_KARATE_MASTER)%8)
    raw=N(map_id=171 if fault=='map' else 177,
          event_flags=None if fault=='missing_event' else bytes(flags))
    master=N(object_index=1,trainer_class=225 if fault=='identity' else 224,
             trainer_set=1,sprite_id=14,direction_or_range=208,
             at=(3,4) if fault=='position' else (3,5))
    calls=[]
    monkeypatch.setattr(m,'verify_rom_bytes',lambda rom:calls.append('rom'))
    monkeypatch.setattr(m,'map_object_events',lambda *a:() if fault=='object' else (master,))
    monkeypatch.setattr(m,'trainer_party_quote',lambda rom,cls,team:
        calls.append((cls,team)) or N(expected_victory_money=925))
    if fault:
        with pytest.raises(ValueError,match='Dojo Master'):
            m.dojo_master_contract(b'fixture',raw)
        assert calls==['rom']
    else:
        contract=m.dojo_master_contract(b'fixture',raw)
        assert contract.trainer_identity==(224,24,1)
        assert contract.defeated_event==int(EventFlag.BEAT_KARATE_MASTER)
        assert contract.objective_id=='postgame_collection' and contract.victory_money==925
        assert calls==['rom',(224,1)]


def test_retained_native_dojo_master_uses_scripted_contract_before_ordinary_headers(monkeypatch):
    from pokemon_red_completion import red_player_engaged_story as m,red_scripted_story_trainer as script
    raw=N(map_id=177,battle_state=2)
    reader=N(read=lambda:raw,read_active_trainer_identity=lambda:(224,24,1))
    contract=object()
    monkeypatch.setattr(script,'dojo_master_contract',lambda rom,r:contract)
    monkeypatch.setattr(m,'trainer_headers',lambda *a,**k:pytest.fail('Master has no sight header'))
    assert m.engaged_story_contract(reader,b'fixture',objective_id='postgame_collection') is contract


@pytest.mark.parametrize('fault',[None,'unverified','lost','negative','boolean','missing'])
def test_learned_route_income_requires_independently_verified_native_wins(fault):
    from pokemon_red_completion.red_player_engaged_story import EngagedStoryRouteHandler
    from pokemon_red_completion.route_executor import RouteExecutionError
    handler=EngagedStoryRouteHandler(N(handle=lambda x:None),object(),lambda:None)
    assert handler.verified_trainer_income==0
    battle=dict(outcome='lost' if fault=='lost' else 'won',
                money_delta=-1 if fault=='negative' else True if fault=='boolean' else 925)
    if fault=='missing':
        battle.pop('money_delta')
    handler.trainer_evidence.append(N(details=dict(verified=fault!='unverified',battle=battle)))
    if fault:
        with pytest.raises(RouteExecutionError,match='native win evidence'):
            _=handler.verified_trainer_income
    else:
        assert handler.verified_trainer_income==925
