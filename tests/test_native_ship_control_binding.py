from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_gen1_ship_departure import setup, flags, INITIAL

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_indoor_departure_plan import native_ship_departure_binding
from pokemon_red_completion.route_executor import RouteExecutionError


@pytest.fixture
def scene(monkeypatch):
    import pokemon_red_completion.red_player_lesson as lesson
    reader, port, handler, observed, actions=setup()
    reader.read_pending_trainer_battle_identity=lambda:None
    reader.read_fly_menu_state=lambda:None
    frame=[0]
    def state():return repr((reader.raw,reader.ready,len(actions))).encode()
    em=N(frame_count=0,pressed_buttons=frozenset(),save_state_bytes=state)
    class Meter:
        actions_executed=0
        def execute(self,action):
            self.actions_executed+=1
            em.frame_count+=action.repeat
            return port.execute(action)
    meter=Meter()
    rt=N(reader=reader,emulator=em)
    snapshots=[dict(completed_objectives=['obtain_cut'],party=[dict(specimen_ref='one',experience=8004)])]
    monkeypatch.setattr(lesson,'capture_player_lesson_snapshot',lambda _:(N(raw=reader.raw),snapshots[0]))
    return N(rt=rt,reader=reader,port=port,actions=actions,meter=meter,snapshots=snapshots)


def test_pending_native_scene_is_wait_only_costed_once_and_returns_fresh_control(scene):
    s=scene
    binding=native_ship_departure_binding(s.rt,s.meter)
    assert binding.kind is GoalKind.RECOVER_CONTROL and binding.maximum_cash_debit==0
    assert binding.story_objective_ref is None and not s.actions
    result=binding.execute()
    assert result.actions_executed==2 and result.frames_executed==192
    assert result.evidence['model_queries']==0 and result.evidence['objective_completed']is False
    assert result.evidence['protected_resources_unchanged']is True
    assert binding.verify(result).status.value=='succeeded'
    assert len(s.actions)==2
    with pytest.raises(ValueError,match='consumed'):binding.execute()
    assert native_ship_departure_binding(s.rt,s.meter)is None


@pytest.mark.parametrize('fault',['flags','ready','textbox','trainer','buttons','unknown'])
def test_unrelated_or_unproved_scene_gets_no_binding_or_input(scene,fault):
    s=scene
    if fault=='flags':s.reader.raw=replace(s.reader.raw,event_flags=flags(*INITIAL[:2]))
    elif fault=='ready':s.reader.ready=True
    elif fault=='textbox':s.reader.dialogue_visible=True
    elif fault=='trainer':s.reader.trainer_engagement=True
    elif fault=='buttons':s.rt.emulator.pressed_buttons=frozenset({'a'})
    else:s.reader.raw=N(ss_anne_departure_pending=None)
    assert native_ship_departure_binding(s.rt,s.meter)is None
    assert not s.actions


@pytest.mark.parametrize('fault',['stale','experience','objective','wrong_report'])
def test_binding_preserves_identity_progress_and_exact_result(scene,fault):
    s=scene
    binding=native_ship_departure_binding(s.rt,s.meter)
    if fault=='stale':
        s.reader.raw=replace(s.reader.raw,player_money=s.reader.raw.player_money-1)
        with pytest.raises(ValueError,match='stale'):binding.execute()
        assert not s.actions
    elif fault=='wrong_report':
        result=binding.execute()
        assert binding.verify(replace(result,evidence=dict(result.evidence))).status.value=='failed'
    else:
        original=s.port.execute
        def execute(action):
            returned=original(action)
            if s.reader.ready:
                s.snapshots[0]=dict(completed_objectives=['obtain_cut','defeat_surge']if fault=='objective'else['obtain_cut'],
                    party=[dict(specimen_ref='one',experience=8005 if fault=='experience'else 8004)])
            return returned
        s.port.execute=execute
        with pytest.raises(RuntimeError,match='settled field control'):binding.execute()


def test_indoor_route_handles_native_warp_in_process_without_retarget_or_reload(monkeypatch,scene):
    import pokemon_red_completion.red_indoor_departure_plan as module
    import pokemon_red_completion.gen1_route_runtime as traversal
    import pokemon_red_completion.gen1_trainer_sight as sight
    import pokemon_red_completion.red_player_cash_exposure as cash
    import pokemon_red_completion.red_routed_semantic_goal as transport
    from pokemon_red_completion.observation import MapId
    from pokemon_red_completion.route_executor import TraversalSnapshot
    s=scene
    initial=s.reader.raw
    s.reader.ready=True
    s.reader.raw=replace(initial,map_id=95,player_y=0,player_x=26)
    start=N(map_id=95,last_outside_map=5)
    step=N(expected_map=94,expected_at=(2,14))
    plan=N(steps=(step,),terminal_map=5,terminal_at=(31,18))
    monkeypatch.setattr(traversal,'Gen1TraversalObserver',lambda *a,**k:N(observe=lambda:start))
    monkeypatch.setattr(sight,'Gen1TrainerSightProjector',lambda *a,**k:None)
    monkeypatch.setattr(module,'bounded_indoor_departure',lambda *_:plan)
    monkeypatch.setattr(cash,'require_cash_safe_plan',lambda *_:None)
    verifies=[]
    def make_transport(**kw):
        def execute():
            s.meter.actions_executed+=1
            s.rt.emulator.frame_count+=24
            s.reader.raw=initial
            s.reader.ready=False
            kw['interruption_handler'].handle(TraversalSnapshot(94,(2,14),False,'native_ship_departure',mode='land'))
            raise AssertionError('settled native handoff must return to full menu')
        return N(route_binding=lambda:N(execute=execute,verify=lambda _:verifies.append('must not verify partial quote')))
    monkeypatch.setattr(transport,'RedSemanticTransportRoute',make_transport)
    route=N(rom=b'ROM',route_world=N(with_current_observation=lambda _:object()))
    binding=module.indoor_departure_binding(s.rt,s.meter,route=route)
    result=binding.execute()
    assert not verifies and result.actions_executed==3 and result.frames_executed==216
    assert result.evidence['automatic_native_handoff']is True
    assert result.evidence['quoted_route_completed']is False
    assert binding.verify(result).status.value=='succeeded'
    assert s.reader.raw.map_id==MapId.VERMILION_CITY and(s.reader.raw.player_y,s.reader.raw.player_x)==(29,18)


@pytest.mark.parametrize('old_reference',[False,True])
def test_genuine_native_session_preface_uses_ship_motion_owner_before_any_model_query(tmp_path,monkeypatch,old_reference):
    import json
    from test_red_native_player import setup as native_setup
    import pokemon_red_completion.red_native_player as native
    import pokemon_red_completion.red_player_lesson as lesson_module
    import pokemon_red_completion.red_indoor_departure_plan as departure_module
    from pokemon_red_completion.actions import MacroAction,MacroActionKind
    from pokemon_red_completion.goal_manager import GoalOpportunity,GoalAvailability,GoalUnavailableReason
    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet

    args,ordinary_executed=native_setup(tmp_path,monkeypatch)
    args['source']=dict(args['source'],partition='development')
    args['settle_existing_motion']=True
    args['limits']=replace(args['limits'],actions=2,frames=500,decisions=3)
    reader,ship_port,_,_,waits=setup()
    reader.read_pending_trainer_battle_identity=lambda:None
    reader.read_fly_menu_state=lambda:None
    emulator=args['emulator']
    tick0=emulator.tick
    def tick(frames):
        tick0(frames)
        assert frames==96
        ship_port.execute(MacroAction(MacroActionKind.WAIT,repeat=96))
    monkeypatch.setattr(emulator,'tick',tick)
    capture0=native.capture_player_lesson_snapshot
    def capture(runtime):
        observed,document=capture0(runtime)
        observed.raw=reader.raw
        observed.input_ready=reader.ready
        document['in_battle']=False
        return observed,document
    monkeypatch.setattr(native,'capture_player_lesson_snapshot',capture)
    monkeypatch.setattr(lesson_module,'capture_player_lesson_snapshot',capture)
    factory0=args['runtime_factory']
    def factory(controller):
        runtime=factory0(controller)
        runtime.reader=reader
        return runtime
    args['runtime_factory']=factory
    query_calls=[]
    def deny_query(*a,**k):
        query_calls.append(True)
        raise AssertionError('mandatory motion cannot query the model')
    for name in ('scores','predict','predict_outcomes','probabilities'):
        if hasattr(type(args['model']),name):monkeypatch.setattr(type(args['model']),name,deny_query)
    observed_refs=[]
    def enumerate_bindings(runtime,actions,observed):
        binding=departure_module.native_ship_departure_binding(runtime,actions)
        assert binding is not None
        if old_reference:
            binding=replace(binding,binding_ref='pokemon.red:native-ship-departure:'+binding.binding_ref.rsplit(':',1)[-1])
        observed_refs.append(binding.binding_ref)
        blocked=GoalOpportunity('ship:settlement-only',GoalKind.ADVANCE_STORY,
            GoalAvailability.UNAVAILABLE,unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED)
        return GoalBindingSet((binding.opportunity,blocked),(binding,))
    args['enumerate_bindings']=enumerate_bindings
    if old_reference:
        with pytest.raises(ValueError,match='one mandatory executor'):
            native.run_native_continuous_player(**args)
        assert emulator.frame_count==0 and not waits
    else:
        result=native.run_native_continuous_player(**args)
        preface=result['supplied_motion_preface']
        assert preface['actions']==2 and preface['frames']==192
        assert preface['verification']=='succeeded'and preface['learned']is False
        assert preface['operator_relaunch']is False
        assert len(waits)==2 and reader.ready
        intent=json.loads((args['output']/'retained-motion-preface/intent.json').read_bytes())
        assert intent['model_queries']==0 and intent['comparative_choice']is False
        assert intent['binding_ref']=='pokemon.red:retained-motion:'+intent['source_sha256']
    assert not ordinary_executed and not query_calls
