from dataclasses import replace
from types import SimpleNamespace
import pytest
from test_current_route_terrain import _world
from test_red_super_rod_support import (
    _Reader,_Emulator,_RoutedGiftActions,_patch_routed_dependencies,
)
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.observation import CurrentMapBlocks
from pokemon_red_completion.route_executor import TraversalSnapshot,TraversalHazard
import pokemon_red_completion.red_super_rod_support as support

def scene(monkeypatch,*,extra_hazards=(),occupied=None):
    monkeypatch.setattr(support,"SUPER_ROD_HOUSE_MAP_ID",0)
    monkeypatch.setattr(support,"SUPER_ROD_STANCE_YX",(0,3))
    world=_world().with_current_blocks(CurrentMapBlocks(0,((0,0),)))
    current=TraversalSnapshot(0,(0,0),True,mode="land",
        occupied=frozenset({(1,1),(1,2),(1,3)})if occupied is None else occupied,
        hazards=(TraversalHazard((0,1),"trainer_sight"),*extra_hazards),
        capabilities=frozenset({"story:unchanged"}),last_outside_map=0)
    actions=CountingExecutor(SimpleNamespace(execute=lambda a:pytest.fail("unexpected input")))
    executor=support.RedRoutedSuperRodSupport(actions,object(),SimpleNamespace(frame_count=0),world)
    return executor,SimpleNamespace(observe=lambda:current),current

def quote(executor,observer,handler=None):
    return executor._plan_to_super_rod(observer,unavailable="unavailable",
        unsupported="unsupported",interruption_handler=handler)

def test_execution_plan_matches_existing_explicit_trainer_hazard_authority(monkeypatch):
    executor,observer,current=scene(monkeypatch)
    # Discovery's hazard-free snapshot admits the same selected destination.
    assert executor.world.plan_feasible_to_map(replace(current,hazards=()),0,
        goal_at=(0,3)).terminal_at==(0,3)
    with pytest.raises(support.RedSuperRodSupportError,match="unavailable"):
        quote(executor,observer)
    handler=SimpleNamespace(handled_hazard_kinds=frozenset({"trainer_sight"}))
    plan=quote(executor,observer,handler)
    assert plan.terminal_at==(0,3)and plan.actions==("right","right","right")
    # The full live observation remains intact for the real route executor.
    assert observer.observe()is current
    assert current.hazards==(TraversalHazard((0,1),"trainer_sight"),)
    assert current.capabilities==frozenset({"story:unchanged"})
    assert current.occupied=={(1,1),(1,2),(1,3)}
    assert executor.actions.actions_executed==0

@pytest.mark.parametrize("kinds",[None,frozenset(),["trainer_sight"],{"trainer_sight"}])
def test_default_or_untyped_handler_does_not_clear_hazard(monkeypatch,kinds):
    executor,observer,current=scene(monkeypatch)
    handler=SimpleNamespace(handled_hazard_kinds=kinds)
    with pytest.raises(support.RedSuperRodSupportError,match="unavailable"):
        quote(executor,observer,handler)
    assert executor.actions.actions_executed==0

def test_explicit_trainer_support_keeps_unknown_hazard_blocked(monkeypatch):
    executor,observer,current=scene(monkeypatch,
        extra_hazards=(TraversalHazard((0,2),"unsupported_script"),))
    handler=SimpleNamespace(handled_hazard_kinds=frozenset({"trainer_sight","unsupported_script"}))
    with pytest.raises(support.RedSuperRodSupportError,match="unavailable"):
        quote(executor,observer,handler)
    assert executor.actions.actions_executed==0

def test_trainer_support_never_clears_solid_occupancy(monkeypatch):
    executor,observer,current=scene(monkeypatch,
        occupied=frozenset({(0,2),(1,1),(1,2),(1,3)}))
    handler=SimpleNamespace(handled_hazard_kinds=frozenset({"trainer_sight"}))
    with pytest.raises(support.RedSuperRodSupportError,match="unavailable"):
        quote(executor,observer,handler)
    assert current.occupied=={(0,2),(1,1),(1,2),(1,3)}
    assert executor.actions.actions_executed==0

def test_plan_rechecks_unchanged_supported_mechanics(monkeypatch):
    executor,observer,current=scene(monkeypatch)
    monkeypatch.setattr(support,"_supported_plan",lambda *a,**k:False)
    with pytest.raises(support.RedSuperRodSupportError,match="unsupported"):
        quote(executor,observer,SimpleNamespace(
            handled_hazard_kinds=frozenset({"trainer_sight"})))
    assert executor.actions.actions_executed==0

def test_normal_execute_passes_its_actual_wrapped_handler_to_planning(monkeypatch):
    reader,emulator=_Reader(),_Emulator()
    runtime,world=_patch_routed_dependencies(monkeypatch,reader)
    wrapped=SimpleNamespace(handle=lambda request:None,
        handled_hazard_kinds=frozenset({"trainer_sight"}))
    seen=[];original=support.RedRoutedSuperRodSupport._plan_to_super_rod
    def plan(self,observer,**kwargs):
        seen.append(kwargs["interruption_handler"])
        return original(self,observer,**kwargs)
    monkeypatch.setattr(support.RedRoutedSuperRodSupport,"_plan_to_super_rod",plan)
    delegate=_RoutedGiftActions(reader,emulator,acquire_on=3,settle_on=4)
    result=support.RedRoutedSuperRodSupport(
        CountingExecutor(delegate),reader,emulator,world,
        interruption_handler_wrapper=lambda inner:wrapped).execute()
    assert seen==[wrapped]and result.gift.actions==4
