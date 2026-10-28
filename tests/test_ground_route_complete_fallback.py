from dataclasses import replace
from types import SimpleNamespace
import pytest
from pokemon_red_completion.red_training_ground_route import RedVermilionGroundTransition
from pokemon_red_completion.route_executor import TraversalSnapshot,TraversalHazard
from pokemon_red_completion.route_plan import RoutePlanningError
from test_red_training_ground_route import _world

@pytest.mark.parametrize('invalid',[None,0,1,'yes',[]])
def test_complete_search_requires_explicit_boolean(invalid):
    with pytest.raises(TypeError,match='opt-in'):
        RedVermilionGroundTransition(b'rom',_world(),allow_complete_cut_search=invalid)

@pytest.mark.parametrize('enabled',[False,True])
def test_existing_success_avoids_broader_search(enabled):
    answer=object();start=TraversalSnapshot(133,(3,3),True)
    world=SimpleNamespace(plan_feasible_to_map=lambda *a,**kw:answer,_plan_candidate=lambda *a,**kw:pytest.fail('extra search'))
    assert RedVermilionGroundTransition(b'rom',_world(),allow_complete_cut_search=enabled)._initial_plan(world,start)is answer

def test_default_preserves_native_bounded_failure_object():
    error=RoutePlanningError('original bounded chain')
    def fail(*args,**kwargs):raise error
    world=SimpleNamespace(plan_feasible_to_map=fail,_plan_candidate=lambda *a,**kw:pytest.fail('not opted in'))
    with pytest.raises(RoutePlanningError)as caught:
        RedVermilionGroundTransition(b'rom',_world())._initial_plan(world,TraversalSnapshot(133,(3,3),True))
    assert caught.value is error

def test_opted_in_fallback_preserves_endpoint_actual_capabilities_and_hazards():
    start=TraversalSnapshot(133,(3,3),True,mode='land',occupied=frozenset({(1,3)}),hazards=(TraversalHazard((4,3),'trainer_sight'),),capabilities=frozenset({'move:cut'}))
    seen=[];answer=object()
    def bounded(*a,**kw):raise RoutePlanningError('short corridor unavailable')
    def complete(*a,**kw):seen.append((a,kw));return answer
    world=SimpleNamespace(plan_feasible_to_map=bounded,_plan_candidate=complete)
    route=RedVermilionGroundTransition(b'rom',_world(),destination_map=5,destination_at=(4,11),allow_complete_cut_search=True)
    assert route._initial_plan(world,start)is answer
    assert seen==[((start,5),dict(goal_at=(4,11),blocked={133:frozenset({(1,3),(4,3)})}))]
    assert start.capabilities==frozenset({'move:cut'})and start.occupied==frozenset({(1,3)})

@pytest.mark.parametrize('error',[ValueError('invalid world'),RuntimeError('native defect')])
def test_nonrouting_error_is_never_hidden_by_fallback(error):
    def fail(*a,**kw):raise error
    world=SimpleNamespace(plan_feasible_to_map=fail,_plan_candidate=lambda *a,**kw:pytest.fail('must retain error'))
    with pytest.raises(type(error))as caught:
        RedVermilionGroundTransition(b'rom',_world(),allow_complete_cut_search=True)._initial_plan(world,TraversalSnapshot(133,(3,3),True))
    assert caught.value is error

def test_failed_broader_search_retains_bounded_native_context():
    bounded=RoutePlanningError('bounded');complete=RoutePlanningError('complete')
    def first(*a,**kw):raise bounded
    def second(*a,**kw):raise complete
    with pytest.raises(RoutePlanningError)as caught:
        RedVermilionGroundTransition(b'rom',_world(),allow_complete_cut_search=True)._initial_plan(SimpleNamespace(plan_feasible_to_map=first,_plan_candidate=second),TraversalSnapshot(133,(3,3),True))
    assert caught.value is complete and complete.__context__ is bounded

