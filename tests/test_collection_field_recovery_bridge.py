from copy import deepcopy
from dataclasses import replace
from hashlib import sha256

import pytest

from test_gen1_route_runtime import FakeReader,reader_as_real
from test_red_routed_recovery import make_test_raw
from test_red_route_loss_recovery import route_loss
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
from pokemon_red_completion.global_router import MacroPath
from pokemon_red_completion.goal_manager import GoalKind,GoalFailureReason
from pokemon_red_completion.goal_manager_runtime import GoalVerification
from pokemon_red_completion.local_router import LocalPath,LocalEdge
from pokemon_red_completion.red_integrated_play import ordinary_player_setback
from pokemon_red_completion.red_routed_recovery import (
    SETTLED_ROUTE_FIELD_RECOVERY_SCHEMA,guarded_collection_route_handler,
)
from pokemon_red_completion.red_routed_semantic_goal import (
    RedSemanticTransportRoute,RedRoutedSemanticBudgetMeter,
)
from pokemon_red_completion.route_plan import RoutePlan
from pokemon_red_completion.routed_semantic_goal import (
    RoutedSemanticGoalComposer,RoutedSemanticGoalLimits,
)


def test_native_field_faint_crosses_route_and_goal_composition_without_destination():
    reader=FakeReader(make_test_raw(map_id=1,x=3,y=2,hp=(1,30),status=(8,0)))
    reader.read_all_box_states=lambda: ()
    reader.read_pokedex_state=lambda: ()

    class World:
        frame_count=0
        pressed_buttons=()
        def save_state_bytes(self):
            return repr((reader.raw,reader.dialogue_visible,reader.moving_direction)).encode()
        def execute(self,action):
            self.frame_count+=action.repeat
            if action.kind is MacroActionKind.MOVE:
                assert reader.raw.player_x==3
                reader.raw=replace(reader.raw,player_x=4,party_hp=(0,30),party_status=(0,0))
                reader.dialogue_visible=True;reader.moving_direction=4
            elif action.kind is MacroActionKind.CANCEL:
                reader.dialogue_visible=False;reader.moving_direction=0
            return action

    world=World();actions=CountingExecutor(world)
    plan=RoutePlan(macro_path=MacroPath((1,),()),start_at=(2,3),start_mode='land',segments=(),
        terminal_approach=LocalPath(((2,3),(2,4),(2,5)),
            (LocalEdge((2,4),'right'),LocalEdge((2,5),'right')),('land','land','land')),
        terminal_at=(2,5),terminal_mode='land')
    route=RedSemanticTransportRoute(binding_ref='copied:field-route',origin_observation_sha256='a'*64,
        planner_binding_sha256='b'*64,plan=plan,actions=actions,
        traversal_observer=Gen1TraversalObserver(reader_as_real(reader)),emulator=world,
        interruption_handler=guarded_collection_route_handler(actions,reader_as_real(reader),
            route_name='field-faint integration',allow_field_faints=True,emulator=world))
    def no_destination():raise AssertionError('Interrupted route must not execute its destination')
    binding=RoutedSemanticGoalComposer(binding_ref='copied:collection',destination_kind=GoalKind.ACQUIRE_SPECIES,
        estimated_effort=.1,estimated_risk=.1,route=route.route_binding(),
        bind_fresh_destination=no_destination,budget_meter=RedRoutedSemanticBudgetMeter(actions,world),
        limits=RoutedSemanticGoalLimits(100,1000)).binding()
    report=binding.execute()
    assert binding.verify(report)==GoalVerification.failed(GoalFailureReason.RECOVERY_REQUIRED)
    assert report.evidence['destination_executed'] is False
    stop=report.evidence['route_setback']
    assert stop['schema']==SETTLED_ROUTE_FIELD_RECOVERY_SCHEMA
    assert stop['terminal_sha256']==sha256(world.save_state_bytes()).hexdigest()
    assert stop['new_fainted_slots']==[1] and stop['party_hp']==[0,30]
    assert report.actions_executed==actions.actions_executed
    assert report.frames_executed==world.frame_count
    assert reader.raw.player_x==4 and reader.read_input_readiness().ready


@pytest.mark.parametrize('fault',[None,'terminal','hp','cash','custody','learned','model_query',
    'healthy','all_fainted','slots','duplicate_slots','missing','budget','destination',
    'exception','reason','census','unsettled'])
def test_continuous_player_admits_only_measured_field_recovery(monkeypatch,fault):
    _,before,after,report,binding=route_loss(monkeypatch)
    evidence=deepcopy(dict(report.evidence));facts=deepcopy(dict(after.facts))
    facts.setdefault('diagnostics',{})['party_hp']=[0,25]
    evidence['route_setback']=dict(schema=SETTLED_ROUTE_FIELD_RECOVERY_SCHEMA,
        verified=True,support='native_field_poison_faint',learned_recovery=False,
        protected_resources_verified=True,model_queries=0,source_sha256='a'*64,
        terminal_sha256=after.sha256,cash_before=945,cash_after=945,
        actions=2,frames=181,party_hp=[0,25],new_fainted_slots=[1])
    e=evidence['route_setback']
    if fault=='terminal':e['terminal_sha256']='b'*64
    elif fault=='hp':facts['diagnostics']['party_hp']=[0,24]
    elif fault=='cash':e['cash_before']=944
    elif fault=='custody':e['protected_resources_verified']=False
    elif fault=='learned':e['learned_recovery']=True
    elif fault=='model_query':e['model_queries']=1
    elif fault=='healthy':e['party_hp']=[20,25]
    elif fault=='all_fainted':e['party_hp']=[0,0]
    elif fault=='slots':e['new_fainted_slots']=[2]
    elif fault=='duplicate_slots':e['new_fainted_slots']=[1,1]
    elif fault=='missing':e.pop('source_sha256')
    elif fault=='budget':evidence['within_budget']=False
    elif fault=='destination':evidence['destination_executed']=True
    elif fault=='census':facts['specimen_counts']['pokemon:national:025']=1
    elif fault=='unsettled':facts['input_ready']=False
    error=RuntimeError('unknown')if fault=='exception'else None
    reason=GoalFailureReason.RESOURCE_LOST if fault=='reason'else GoalFailureReason.RECOVERY_REQUIRED
    after=replace(after,facts=facts)
    assert ordinary_player_setback(binding,before,after,replace(report,evidence=evidence),
        GoalVerification.failed(reason),error) is (fault is None)
