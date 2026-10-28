from dataclasses import replace
from types import SimpleNamespace as N
from pathlib import Path
import os

import pytest
from test_local_vermilion_supply import Runtime, origin_profile
from test_red_goal_skills import _adapter, _raw, _Reader
from test_red_live_option_menu import _binding
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.red_goal_context_profile import _thaw
from pokemon_red_completion.red_goal_skills import RedMartPurchase, RedMartResupplyGoalProvider
from pokemon_red_completion.red_player_configuration import (
    local_ordinary_ball_supply_peers, local_ordinary_ball_supply_profile,
)


@pytest.mark.parametrize('mart',[int(MapId.CERULEAN_MART),int(MapId.VERMILION_MART)])
def test_verified_catalog_profile_preserves_other_skills_and_ordinary_order(mart):
    original=origin_profile(); actual=local_ordinary_ball_supply_profile(original,mart)
    assert [x for x in actual.providers if x.kind is not GoalKind.RESUPPLY]==[
        x for x in original.providers if x.kind is not GoalKind.RESUPPLY]
    p=_thaw(next(x.parameters for x in actual.providers if x.kind is GoalKind.RESUPPLY))
    assert p==dict(map_id=mart,player_x=2,player_y=5,interaction_direction='left',
        purchases=[dict(absolute_index=0,item_id=4,quantity=5,unit_price=200)],
        affordable_ball_purchase=True,resource_choice_variants=True)


@pytest.mark.parametrize('mart',[0,3,5,68,999,True,'67'])
def test_unsupported_or_unverified_store_cannot_supply_a_profile(mart):
    with pytest.raises(ValueError,match='verified clerk catalog'):
        local_ordinary_ball_supply_profile(origin_profile(),mart)


@pytest.mark.parametrize('town',[3,5,4,12,17])
def test_all_verified_suppliers_reach_actual_router_from_any_observed_locality(monkeypatch,town):
    import pokemon_red_completion.red_resource_goal_router as module
    raw=replace(_raw(poke_balls=0,hyper_potions=10),map_id=town,player_money=1446)
    rt=Runtime(origin_profile(),N(read_retained_outside_map=lambda:town),N(graph=N(completed_ids=lambda _:())))
    observed=N(raw=raw,input_ready=True,game_state=object());calls=[]
    class Router:
        def __init__(self,runtime,actions,world,**options):
            self.mart=_thaw(next(x.parameters for x in runtime.profile.providers if x.kind is GoalKind.RESUPPLY))['map_id']
            calls.append((self.mart,world,options))
        def enumerate_routed_kinds(self,current,kinds):
            assert current is observed and kinds==frozenset({GoalKind.RESUPPLY})
            # A real route quote owns availability; a rejected clerk contributes nothing.
            return N(bindings=(() if self.mart==91 else (_binding(GoalKind.RESUPPLY,binding_ref='quoted:67',calls=[]),)))
    monkeypatch.setattr(module,'RedResourceGoalRouter',Router)
    world=N(with_current_observation=lambda reader:'fresh-current-world')
    rows=local_ordinary_ball_supply_peers(rt,N(),observed,world=world)
    assert len(rows)==1 and rows[0].binding_ref=='quoted:67'
    assert [x[0]for x in calls]==[67,91]
    assert all(x[1]=='fresh-current-world' for x in calls)
    assert all(x[2]==dict(quote_resource_costs=True,prepare_capture_party=False,
        prepare_capture_escort=False,include_recovery_offers=False)for x in calls)


@pytest.mark.parametrize('fault',['battle','unready','stock'])
def test_generic_catalog_keeps_original_deficit_and_safety_gates(monkeypatch,fault):
    import pokemon_red_completion.red_resource_goal_router as module
    raw=replace(_raw(poke_balls=0,hyper_potions=10),map_id=3,player_money=1446)
    if fault=='battle':raw=replace(raw,battle_state=1)
    if fault=='stock':raw=replace(raw,bag_items=((4,1),))
    monkeypatch.setattr(module,'RedResourceGoalRouter',lambda *a,**k:pytest.fail('unqualified supplier quoted'))
    rt=Runtime(origin_profile(),N(read_retained_outside_map=lambda:3),N(graph=N(completed_ids=lambda _:())))
    assert local_ordinary_ball_supply_peers(rt,N(),N(raw=raw,input_ready=fault!='unready',game_state=object()),world=N())==()


@pytest.mark.parametrize('mart',[MapId.CERULEAN_MART,MapId.VERMILION_MART])
@pytest.mark.parametrize('cash,quantity',[(1446,5),(999,4),(200,1),(199,0),(0,0)])
def test_both_catalog_entries_keep_existing_native_affordability(mart,cash,quantity):
    raw=replace(_raw(poke_balls=0,hyper_potions=10),map_id=3,player_money=cash)
    reader=_Reader(raw=raw,ready=True)
    provider=RedMartResupplyGoalProvider(mart,2,5,'left',
        (RedMartPurchase(0,ItemId.POKE_BALL,5,200),),N(),reader,N(),_adapter(reader),affordable_ball_purchase=True)
    actual=provider.affordable_provider(N(raw=raw))
    assert (actual.purchases[0].quantity if actual else 0)==quantity


def test_supported_rom_catalog_stock_and_routes_from_both_closed_city_sources():
    path=os.environ.get('POKEMON_TEST_ROM')
    if not path:pytest.skip('supported ROM required for exact stock and route regression')
    from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld
    from pokemon_red_completion.route_executor import TraversalSnapshot
    rom=Path(path).read_bytes()
    assert list(rom[0x2453:0x245d])==[254,7,4,20,30,11,12,14,15,255]
    assert list(rom[0x2461:0x246a])==[254,6,4,19,13,14,15,30,255]
    world=StrategicScenarioRouteWorld.from_rom(rom)
    caps=frozenset({'story:cerulean_robbed_house_open','story:pewter_east_exit_open'})
    for city,at in [(3,(19,18)),(3,(18,19)),(5,(29,18))]:
        start=TraversalSnapshot(city,at,True,mode='land',last_outside_map=city,capabilities=caps)
        reached=[]
        for mart in (67,91):
            try:plan=world.plan_feasible_to_map(start,mart,goal_at=(5,2))
            except Exception as exc:
                # Only the existing route planner may reject a remote supplier.
                from pokemon_red_completion.route_planner import RoutePlanningError
                assert isinstance(exc,RoutePlanningError)
                continue
            assert plan.terminal_map==mart and plan.terminal_at==(5,2)
            from pokemon_red_completion.red_resource_goal_router import _supported_plan
            assert _supported_plan(plan)
            assert all(s.action in{'up','down','left','right'}for s in plan.steps)
            reached.append(mart)
        assert (67 if city==3 else 91)in reached
