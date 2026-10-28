from dataclasses import replace
from types import SimpleNamespace as S
import pytest
from pokemon_red_completion import red_mansion_training_recovery as m
from pokemon_red_completion import red_native_boxed_evolution as n
from pokemon_red_completion.observation import MapId, RawGameState

@pytest.mark.parametrize("start,at,can_fly,expected", [
    (MapId.VERMILION_POKECENTER,(3,3),True,["ground_out","fly","ground_nurse","legacy"]),
    (MapId.VERMILION_POKECENTER,(3,3),False,["ground_nurse","legacy"]),
    (MapId.VERMILION_CITY,(4,11),True,["fly","ground_nurse","legacy"]),
    (MapId.CINNABAR_POKECENTER,(3,3),True,["legacy"]),
    (MapId.CINNABAR_POKECENTER,(7,3),True,["ground_nurse","legacy"]),
    (MapId.CINNABAR_ISLAND,(4,11),True,["ground_nurse","legacy"]),
    (MapId.POKEMON_MANSION_1F,(27,5),False,["ground_nurse","legacy"]),
])
def test_native_return_no_dig_assumption(monkeypatch,start,at,can_fly,expected):
    reader=S(raw=RawGameState(True,start,at[1],at[0],6,0,party_moves=((33,),)*6))
    reader.read=lambda:reader.raw
    reader.read_input_readiness=lambda:S(ready=True)
    reader.read_fly_destinations=lambda:(int(MapId.CINNABAR_ISLAND),)
    calls=[];world=S(rom=b"rom")
    monkeypatch.setattr(m,"red_training_fly_available",lambda raw:can_fly)
    monkeypatch.setattr(m,"red_fly_landings",lambda rom:((int(MapId.VERMILION_CITY),(4,11)),))
    monkeypatch.setattr(m,"Gen1TraversalObserver",lambda r:S(observe=lambda:S(map_id=r.raw.map_id,last_outside_map=int(MapId.VERMILION_CITY))))
    def route(**kw):
        assert kw['route_world'] is world
        assert all(kw[k] is True for k in ['full_event_offsets','observe_terrain','allow_surf','allow_wild_faints','allow_field_faint_dialogue'])
        def run(a,r,e):
            calls.append('ground_nurse' if kw['destination_map']==MapId.CINNABAR_POKECENTER else 'ground_out')
            r.raw=replace(r.raw,map_id=kw['destination_map'],player_y=kw['destination_at'][0],player_x=kw['destination_at'][1])
        return run
    monkeypatch.setattr(m,"RedVermilionGroundTransition",route)
    def fly(action):
        assert action.value=='fly:cinnabar_island'
        calls.append('fly');reader.raw=replace(reader.raw,map_id=MapId.CINNABAR_ISLAND)
        return S(destination_map=int(MapId.CINNABAR_ISLAND),flight_confirmations=1)
    monkeypatch.setattr(m,"Gen1FieldMovePort",lambda *a:S(execute=fly))
    def legacy(a,r,e):
        assert (r.raw.map_id,r.raw.player_y,r.raw.player_x)==(MapId.CINNABAR_POKECENTER,3,3)
        calls.append('legacy');r.raw=replace(r.raw,map_id=MapId.POKEMON_MANSION_1F,player_y=27,player_x=5)
    m.mansion_native_heal_and_return(object(),reader,object(),world=world,legacy=legacy)
    assert calls==expected

@pytest.mark.parametrize('battle,ready',[(1,True),(2,True),(0,False)])
def test_unsettled_start_rejected_before_inputs(battle,ready):
    reader=S(read=lambda:S(battle_state=battle),read_input_readiness=lambda:S(ready=ready))
    with pytest.raises(ValueError,match='settled native field'):
        m.mansion_native_heal_and_return(object(),reader,object(),world=object(),legacy=lambda *a:pytest.fail('legacy'))

@pytest.mark.parametrize('bad',["ground","legacy"])
def test_wrong_native_boundary_rejected(monkeypatch,bad):
    raw=RawGameState(True,MapId.CINNABAR_POKECENTER,3,3,6,0)
    if bad=='ground':raw=replace(raw,player_y=7)
    reader=S(read=lambda:raw,read_input_readiness=lambda:S(ready=True))
    monkeypatch.setattr(m,'RedVermilionGroundTransition',lambda **kw:lambda *a:None)
    with pytest.raises(ValueError,match='Cinnabar nurse' if bad=='ground' else 'native venue boundary'):
        m.mansion_native_heal_and_return(object(),reader,object(),world=S(rom=b'rom'),legacy=lambda *a:None)

def test_only_canonical_mansion_callback_is_wrapped():
    base=n.context.MANSION_TRAINING_VENUE;world=object()
    wrapped=n._with_native_cave_ground_recovery(base,world)
    assert wrapped.band is base.band
    assert wrapped.native_transport_ready is base.native_transport_ready
    assert wrapped.heal_and_return.func is m.mansion_native_heal_and_return
    assert wrapped.heal_and_return.keywords==dict(world=world,legacy=base.heal_and_return)
    custom=replace(base,heal_and_return=lambda *a:None)
    assert n._with_native_cave_ground_recovery(custom,world) is custom


def transport_fixture(monkeypatch, *, blocked=False, visited=True, ready=True, error=None):
    from pokemon_red_completion.route_executor import TraversalSnapshot
    from pokemon_red_completion.route_plan import RoutePlanningError
    from pokemon_red_completion import red_resource_goal_router as router
    from pokemon_red_completion import red_training_ground_route as ground
    raw=RawGameState(True,MapId.VERMILION_POKECENTER,3,3,2,0,
        party_species_ids=(28,21),party_hp=(50,40),
        party_moves=((55,0,0,0),(19,33,0,0)),badge_bits=4)
    reader=S(read=lambda:raw,read_fly_destinations=lambda:((8,)if visited else()))
    party=S(size=2,members=(S(species_id=28,hp=50,moves=(S(move_id=55),)),
                            S(species_id=21,hp=40,moves=(S(move_id=19),S(move_id=33)))))
    calls=[];world=S(rom=b"qualified-rom")
    world.with_current_observation=lambda r:world
    def plan(start,destination,goal_at):
        calls.append((start.map_id,destination,goal_at))
        if error:raise error
        if blocked and start.map_id!=8:raise RoutePlanningError("field move absent")
        return S(terminal_map=destination,terminal_at=goal_at,terminal_mode="land")
    world.plan_feasible_to_map=plan
    monkeypatch.setattr(m,"red_fly_landings",lambda rom:((5,(4,11)),(8,(4,11))))
    monkeypatch.setattr(m,"red_training_fly_available",lambda observed:any(
        hp>0 and 19 in moves for hp,moves in zip(observed.party_hp,observed.party_moves)))
    monkeypatch.setattr(ground,"ground_route_capability_projector",lambda route,memory:lambda observed:frozenset())
    monkeypatch.setattr(m,"Gen1TraversalObserver",lambda r,capability_projector:S(observe=lambda:TraversalSnapshot(
        raw.map_id,(3,3),ready,mode="land",last_outside_map=5,capabilities=capability_projector(raw))))
    monkeypatch.setattr(router,"_supported_plan",lambda *a,**k:True)
    return S(reader=reader,emulator=object()),world,party,calls,raw


def test_transport_quote_rejects_unvisited_remote_venue_without_input(monkeypatch):
    rt,world,party,calls,raw=transport_fixture(monkeypatch,blocked=True,visited=False)
    assert not m.mansion_native_transport_ready(rt,world,party)
    assert calls==[(89,171,(3,3))] and rt.reader.read()==raw


def test_transport_quote_uses_observed_fly_departure_and_exact_native_return(monkeypatch):
    rt,world,party,calls,raw=transport_fixture(monkeypatch)
    assert m.mansion_native_transport_ready(rt,world,party)
    assert calls==[(89,5,(4,11)),(8,171,(3,3)),(171,165,(27,5))]
    assert rt.reader.read()==raw


def test_transport_quote_does_not_borrow_a_removed_field_helper(monkeypatch):
    rt,world,party,calls,raw=transport_fixture(monkeypatch,blocked=True)
    retained=S(size=1,members=(party.members[0],))
    assert not m.mansion_native_transport_ready(rt,world,retained)
    assert calls==[(89,171,(3,3))] and rt.reader.read()==raw


def test_transport_quote_keeps_unexpected_adapter_error_typed(monkeypatch):
    rt,world,party,calls,_=transport_fixture(monkeypatch,error=RuntimeError("adapter defect"))
    with pytest.raises(RuntimeError,match="adapter defect"):
        m.mansion_native_transport_ready(rt,world,party)


def test_transport_quote_rejects_unready_state_before_planning(monkeypatch):
    rt,world,party,calls,_=transport_fixture(monkeypatch,ready=False)
    assert not m.mansion_native_transport_ready(rt,world,party) and not calls


def test_transport_quote_rejects_unexecutable_plan(monkeypatch):
    from pokemon_red_completion import red_resource_goal_router as router
    rt,world,party,calls,_=transport_fixture(monkeypatch)
    monkeypatch.setattr(router,"_supported_plan",lambda *a,**k:False)
    assert not m.mansion_native_transport_ready(rt,world,party)
