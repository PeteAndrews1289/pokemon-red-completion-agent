import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_route_executor import FakeWorld
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge,LocalGraph
from pokemon_red_completion.route_plan import RoutePlanningError,plan_route
from pokemon_red_completion.route_executor import (
    RouteExecutionError,RouteExecutionFailureReason,execute_route)
import pokemon_red_completion.red_super_rod_support as support
_private_record=support._private_route_trace
def recording_execute_route(delegate):
    def execute(plan,actions,observer,**kwargs):
        journal=getattr(getattr(actions,"delegate",None),"record_diagnostic_event",None)
        return support._recording_execute_route(delegate,journal)(plan,actions,observer,**kwargs)
    return execute

def scene(success=False):
    local=LocalGraph({(0,0):(LocalEdge((0,1),"right"),),(0,1):()})
    plan=plan_route(MacroGraph({1:()}),{1:local},1,(0,0),1,goal_at=(0,1))
    world=FakeWorld(transitions={(1,(0,0),"right"):(1,(0,1))}if success else{})
    events=[]
    port=SimpleNamespace(execute=world.execute,
        delegate=SimpleNamespace(record_diagnostic_event=lambda k,v:events.append((k,v))))
    return plan,world,port,events

def fail_replan(request):
    raise RoutePlanningError("retained exact planner failure")

def test_real_failure_retains_full_existing_trace_and_exact_blocker_request():
    plan,world,port,events=scene()
    with pytest.raises(RouteExecutionError)as caught:
        recording_execute_route(execute_route)(plan,port,world,replanner=fail_replan)
    error=caught.value
    assert error.reason is RouteExecutionFailureReason.PLANNER_NO_ROUTE
    assert isinstance(error.__cause__,RoutePlanningError)
    assert str(error.__cause__)=="retained exact planner failure"
    assert [k for k,v in events]==["diagnostic_route_replan_request",
        "diagnostic_route_execution_failure"]
    request=events[0][1]["request"]
    assert request["goal_map"]==1 and request["goal_at"]==[0,1]
    assert request["blocked"]=={"1":[[0,1]]} and request["ordinal"]==1
    assert request["current"]["at"]==[0,0]
    assert events[1][1]["failure"]==_private_record(error.failure)
    assert error.failure.initial_plan is plan
    assert error.failure.movement_requests==2
    assert len(world.actions)==4

def test_recording_does_not_change_default_failure_controls_trace_or_typed_error():
    plan,a,port,events=scene()
    with pytest.raises(RouteExecutionError)as recorded:
        recording_execute_route(execute_route)(plan,port,a,replanner=fail_replan)
    _,b,_,_=scene()
    with pytest.raises(RouteExecutionError)as ordinary:
        execute_route(plan,b,b,replanner=fail_replan)
    assert a.actions==b.actions
    assert _private_record(recorded.value.failure)==_private_record(ordinary.value.failure)
    assert type(recorded.value)is type(ordinary.value)
    assert str(recorded.value)==str(ordinary.value)

def test_success_keeps_delegate_result_actions_and_no_failure_records():
    plan,world,port,events=scene(success=True)
    report=recording_execute_route(execute_route)(plan,port,world)
    assert report.passed and len(world.actions)==1 and events==[]

def test_request_and_every_delegate_argument_are_forwarded_exactly():
    plan,world,port,events=scene()
    request=SimpleNamespace()
    from pokemon_red_completion.route_executor import ReplanRequest
    request=ReplanRequest(world.observe(),1,(0,1),{1:frozenset({(3,4)})},3)
    seen=[];result=object();handler=object();limits=object()
    def replan(actual):
        assert actual is request
        seen.append(actual)
        return result
    def delegate(p,a,o,**kwargs):
        assert p is plan and a is port and o is world
        assert kwargs["interruption_handler"]is handler and kwargs["limits"]is limits
        return kwargs["replanner"](request)
    assert recording_execute_route(delegate)(plan,port,world,replanner=replan,
        interruption_handler=handler,limits=limits)is result
    assert seen==[request]and request.blocked=={1:frozenset({(3,4)})}
    assert len(events)==1 and events[0][1]["request"]["blocked"]=={"1":[[3,4]]}
    assert world.actions==[]

def test_unrelated_error_is_unchanged_and_not_reclassified():
    plan,world,port,events=scene();error=ValueError("same unrelated failure")
    def fail(*args,**kwargs):raise error
    with pytest.raises(ValueError)as caught:
        recording_execute_route(fail)(plan,port,world)
    assert caught.value is error and events==[]

def test_missing_existing_journal_fails_before_delegate_or_input():
    plan,world,_,_=scene()
    port=SimpleNamespace(execute=world.execute,delegate=object())
    with pytest.raises(ValueError,match="existing counted journal"):
        recording_execute_route(lambda*a,**k:pytest.fail("delegate ran"))(plan,port,world)
    assert world.actions==[]

def test_recording_error_does_not_hide_original_native_failure():
    plan,world,port,events=scene()
    error=RouteExecutionError("original native failure")
    def fail(*args,**kwargs):raise error
    def broken(*args):raise OSError("journal unavailable")
    port.delegate.record_diagnostic_event=broken
    with pytest.raises(RouteExecutionError)as caught:
        recording_execute_route(fail)(plan,port,world)
    assert caught.value is error
    assert any("journal unavailable"in q for q in error.__notes__)

def test_recording_factory_does_not_mutate_ordinary_executor_or_module_alias():
    original=support.execute_route
    plan,world,port,events=scene(success=True)
    wrapper=recording_execute_route(execute_route)
    assert support.execute_route is original
    assert wrapper(plan,port,world).passed
    assert support.execute_route is original
