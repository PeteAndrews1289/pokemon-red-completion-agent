from dataclasses import dataclass,replace
from types import SimpleNamespace as N
from pathlib import Path
import os

import pytest
from test_red_goal_skills import _adapter,_raw,_Reader
from test_red_live_option_menu import _binding

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from pokemon_red_completion.observation import ItemId,MapId
from pokemon_red_completion.red_goal_context_profile import RedGoalMechanic,build_red_goal_context_profile_payload,parse_red_goal_context_profile,_thaw
from pokemon_red_completion.red_goal_skills import RedMartPurchase,RedMartResupplyGoalProvider
from pokemon_red_completion.red_player_configuration import local_vermilion_ball_supply_profile,local_vermilion_ball_supply_peers


def origin_profile():
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id='original-regional-supply',providers=(
            (GoalKind.RESTORE_TEAM,RedGoalMechanic.FIELD_RESTORE,{}),
            (GoalKind.RESUPPLY,RedGoalMechanic.MART_RESUPPLY,dict(
                map_id=int(MapId.VIRIDIAN_MART),player_x=2,player_y=5,interaction_direction='left',
                purchases=[dict(absolute_index=0,item_id=4,quantity=5,unit_price=200)])),
            (GoalKind.RECOVER_CONTROL,RedGoalMechanic.CONTROL_RECOVERY,{}))))


def test_local_profile_retains_other_skills_and_exact_verified_ordinary_stock():
    original=origin_profile()
    local=local_vermilion_ball_supply_profile(original)
    assert [(p.kind,p.mechanic,p.parameters)for p in original.providers if p.kind is not GoalKind.RESUPPLY]==[
        (p.kind,p.mechanic,p.parameters)for p in local.providers if p.kind is not GoalKind.RESUPPLY]
    spec=next(p for p in local.providers if p.kind is GoalKind.RESUPPLY)
    params=_thaw(spec.parameters)
    assert params==dict(map_id=91,player_x=2,player_y=5,interaction_direction='left',
        purchases=[dict(absolute_index=0,item_id=4,quantity=5,unit_price=200)],
        affordable_ball_purchase=True,resource_choice_variants=True)
    assert original.profile_id=='original-regional-supply'


@pytest.mark.parametrize('cash,stock,expected',[(2446,0,5),(999,0,4),(200,0,1),(199,0,0),(0,0,0),(2446,5,5)])
def test_existing_native_provider_keeps_affordability_and_deficit_guards(cash,stock,expected):
    raw=replace(_raw(poke_balls=stock,hyper_potions=10),map_id=5,player_y=29,player_x=18,player_money=cash)
    reader=_Reader(raw=raw,ready=True)
    provider=RedMartResupplyGoalProvider(MapId.VERMILION_MART,2,5,'left',
        (RedMartPurchase(0,ItemId.POKE_BALL,5,200),),N(),reader,N(),_adapter(reader),affordable_ball_purchase=True)
    observed=N(raw=raw)
    fixed=provider.affordable_provider(observed)
    assert (0 if fixed is None else fixed.purchases[0].quantity)==expected
    if fixed:
        assert fixed.map_id==MapId.VERMILION_MART
        assert fixed.purchases[0].item is ItemId.POKE_BALL
        assert fixed.purchases[0].quantity*fixed.purchases[0].unit_price<=cash


@dataclass
class Runtime:
    profile:object
    reader:object
    adapter:object


@pytest.mark.parametrize('fault',[None,'other_town','balls','battle','unready'])
def test_only_local_supply_peer_is_quoted_and_existing_router_owns_admission(monkeypatch,fault):
    import pokemon_red_completion.red_resource_goal_router as module
    raw=replace(_raw(poke_balls=0,hyper_potions=10),map_id=5,player_y=29,player_x=18,player_money=2446)
    if fault=='other_town':raw=replace(raw,map_id=0)
    if fault=='balls':raw=replace(raw,bag_items=((4,1),))
    if fault=='battle':raw=replace(raw,battle_state=1)
    rt=Runtime(origin_profile(),N(read_retained_outside_map=lambda:5),
               N(graph=N(completed_ids=lambda _:())))
    observed=N(raw=raw,input_ready=fault!='unready',game_state=object())
    calls=[]
    binding=_binding(GoalKind.RESUPPLY,binding_ref='actual:local-supply',calls=[])
    class Router:
        def __init__(self,runtime,actions,world,**options):
            calls.append((runtime.profile,options,world))
        def enumerate_routed_kinds(self,current,kinds):
            assert current is observed and kinds==frozenset({GoalKind.RESUPPLY})
            return N(bindings=(binding,))
    monkeypatch.setattr(module,'RedResourceGoalRouter',Router)
    world=N(with_current_observation=lambda reader:'fresh-world')
    result=local_vermilion_ball_supply_peers(rt,N(),observed,world=world)
    assert result==((binding,)if fault is None else())
    assert bool(calls)is(fault is None)
    if calls:
        assert calls[0][2]=='fresh-world'
        assert calls[0][1]==dict(quote_resource_costs=True,prepare_capture_party=False,
            prepare_capture_escort=False,include_recovery_offers=False)
    assert rt.profile.profile_id=='original-regional-supply'


def test_actual_rom_stock_and_reachable_local_clerk_without_cut_or_fly():
    path=os.environ.get('POKEMON_TEST_ROM')
    if not path:pytest.skip('supported ROM needed for merchant regression')
    from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld
    from pokemon_red_completion.route_executor import TraversalSnapshot
    rom=Path(path).read_bytes()
    assert list(rom[0x2461:0x246a])==[254,6,4,19,13,14,15,30,255]
    world=StrategicScenarioRouteWorld.from_rom(rom)
    start=TraversalSnapshot(5,(29,18),True,mode='land',last_outside_map=5,
        occupied=frozenset({(30,19)}),capabilities=frozenset({
            'story:cerulean_robbed_house_open','story:pewter_east_exit_open'}))
    plan=world.plan_feasible_to_map(start,int(MapId.VERMILION_MART),goal_at=(5,2))
    assert plan.terminal_map==91 and plan.terminal_at==(5,2)
    assert plan.macro_path.maps==(5,91)
    assert all(s.kind in{'walk','warp','return'}for s in plan.steps)
    assert all(s.action in{'up','down','left','right'}for s in plan.steps)
