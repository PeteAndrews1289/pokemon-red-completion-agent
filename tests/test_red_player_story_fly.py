from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_story_fly as s
from pokemon_red_completion.gen1_field_moves import Gen1FlyReceipt
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.observation import Badge, OverworldMovementMode
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError


def setup(monkeypatch, *, arrival=False):
    raw = N(
        map_id=10, player_y=5, player_x=6, party_count=1,
        party_species_ids=(151,), party_hp=(90,), party_max_hp=(90,),
        party_status=(0,), party_moves=((19, 16, 98, 0),), party_pp=((15, 35, 30, 0),),
        party_levels=(40,), bag_items=((1, 1), (3, 5)), player_money=365,
        badge_bits=int(Badge.THUNDER), event_flags=bytes(320), battle_state=0,
    )
    live = N(raw=raw, state=b"origin", ready=True, mode=OverworldMovementMode.WALKING,
             pending=None, menu=None, visited=(0, 1), failure=None, calls=0, plan_calls=[])
    objective = N(id="reach_pewter" if arrival else "obtain_secret_key",
                  completion_facts=frozenset({"native-fact"}))
    lesson = {"completed_objectives": ["receive_pokedex"]}
    world = N(
        macro_graph=object(), local_graphs={t: N(edges={(3, 4): ()}) for t in (0, 1)},
        object_blockers={t: frozenset() for t in (0, 1)},
    )

    def plan(start, target, *, goal_at):
        live.plan_calls.append((start, target, goal_at))
        if live.failure == "blocked_onward":
            raise RoutePlanningError("real trainer blocks the onward boundary")
        steps = () if start.map_id == target else (N(
            action_kind=s.MacroActionKind.MOVE, action="down",
            source_mode="land", expected_mode="land",
        ),)
        return N(terminal_map=target, terminal_at=goal_at, steps=steps, cost=9)

    world.plan_feasible_to_map = plan
    distances = {10: 8, 0: 1, 1: 4}
    monkeypatch.setattr(s, "find_macro_path",
                        lambda graph, source, target, **kw: N(edges=range(distances[source])))
    monkeypatch.setattr(s, "red_fly_landings", lambda rom: ((0, (3, 4)), (1, (3, 4))))
    monkeypatch.setattr(s, "_noncombat_fly_world", lambda w, r: w)
    monkeypatch.setattr(s, "story_frontier_target", lambda w, start, end:
                        (end, start.at) if start.map_id == end else (7, (2, 2)))
    monkeypatch.setattr(s, "_field_ready", lambda rt: live.ready)
    monkeypatch.setattr(s, "semantic_facts",
                        lambda r: frozenset() if live.failure == "no_fact" else objective.completion_facts)
    rt = N(
        emulator=N(frame_count=0, save_state_bytes=lambda: live.state),
        reader=N(
            read=lambda: live.raw,
            read_overworld_movement_mode=lambda: live.mode,
            read_pending_trainer_battle_identity=lambda: live.pending,
            read_fly_menu_state=lambda: live.menu,
            read_fly_destinations=lambda: live.visited,
        ),
        adapter=N(graph=N(objective=lambda _: objective)),
        observer=N(latch_verified_facts=lambda _: lesson["completed_objectives"].append(objective.id)),
    )
    actions = N(actions_executed=0)
    monkeypatch.setattr(s, "capture_player_lesson_snapshot",
                        lambda rt: (N(raw=live.raw), {k: list(v) for k, v in lesson.items()}))

    class Port:
        def __init__(self, limited, reader, emulator):
            pass

        def execute(self, action):
            live.calls += 1
            assert action.kind is s.MacroActionKind.FIELD_MOVE
            assert action.value == "fly:pallet_town"
            after = N(**vars(raw))
            after.map_id, after.player_y, after.player_x = 0, 3, 4
            if live.failure == "wrong_landing":
                after.player_y += 1
            elif live.failure == "story":
                after.event_flags = bytes([1]) + bytes(319)
            elif isinstance(live.failure, tuple):
                setattr(after, *live.failure)
            live.raw, live.state = after, b"landed"
            actions.actions_executed += 12
            rt.emulator.frame_count += 1500
            return Gen1FlyReceipt(10, 0, 0, 0, (0, 1), 1)

    monkeypatch.setattr(s, "Gen1FieldMovePort", Port)
    args = dict(
        objective_id=objective.id, final_destination=0 if arrival else 200,
        route=N(rom=b"rom", route_world=world),
        start=TraversalSnapshot(10, (5, 6), True, mode="land", last_outside_map=10),
        before=N(raw=raw), lesson={k: list(v) for k, v in lesson.items()},
        arrival_objective=arrival,
    )
    return rt, actions, args, live, world, distances, lesson


def test_native_flight_is_only_a_prefix_of_the_selected_objective(monkeypatch):
    rt, actions, args, live, world, distances, lesson = setup(monkeypatch)
    binding = s.story_fly_binding(rt, actions, **args)
    assert live.calls == actions.actions_executed == 0 and live.state == b"origin"
    assert binding.story_objective_ref == "obtain_secret_key"
    assert binding.story_approach_only and binding.maximum_cash_debit == 0
    assert live.plan_calls[0][0].hazards == ()  # no stale source-map hazards
    report = binding.execute()
    assert (report.actions_executed, report.frames_executed) == (12, 1500)
    assert report.evidence["support"] == "native_fly_story_prefix"
    assert report.evidence["objective_completed"] is False
    assert report.evidence["native_fly"]["destination_map"] == 0
    assert report.evidence["automatic_objectives"] == []
    assert report.evidence["topology_ground_edges"] == 8
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert lesson["completed_objectives"] == ["receive_pokedex"]
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


@pytest.mark.parametrize("case", [
    "not_ready", "interrupted", "indoors", "unused_map", "water", "bicycle",
    "no_badge", "fainted", "no_fly", "pending_trainer", "open_fly_menu",
    "unvisited", "incomplete_party", "missing_cash",
])
def test_illegal_flight_absent_without_any_input(monkeypatch, case):
    rt, actions, args, live, world, distances, lesson = setup(monkeypatch)
    raw = args["before"].raw
    if case == "not_ready": live.ready = False
    elif case == "interrupted": args["start"] = replace(args["start"], interruption="battle")
    elif case == "indoors": args["start"] = replace(args["start"], map_id=47)
    elif case == "unused_map": args["start"] = replace(args["start"], map_id=11)
    elif case == "water": args["start"] = replace(args["start"], mode="water")
    elif case == "bicycle": live.mode = OverworldMovementMode.SURFING
    elif case == "no_badge": raw.badge_bits = 0
    elif case == "fainted": raw.party_hp = (0,)
    elif case == "no_fly": raw.party_moves = ((16, 98, 33, 0),)
    elif case == "pending_trainer": live.pending = object()
    elif case == "open_fly_menu": live.menu = object()
    elif case == "unvisited": live.visited = ()
    elif case == "incomplete_party": raw.party_count = 2
    elif case == "missing_cash": raw.player_money = None
    assert s.story_fly_binding(rt, actions, **args) is None
    assert live.calls == actions.actions_executed == 0 and live.state == b"origin"


@pytest.mark.parametrize("case", ["equal_distance", "worse_distance", "blocked_landing",
                                "blocked_onward", "unsupported_onward", "no_onward"])
def test_topology_alone_is_never_permission_to_fly(monkeypatch, case):
    rt, actions, args, live, world, distances, lesson = setup(monkeypatch)
    if case == "equal_distance": distances.update({0: 7, 1: 7})
    elif case == "worse_distance": distances.update({0: 9, 1: 9})
    elif case == "blocked_landing": world.object_blockers = {0: frozenset({(3, 4)}), 1: frozenset({(3, 4)})}
    elif case == "blocked_onward": live.failure = case
    elif case == "unsupported_onward": monkeypatch.setattr(s, "_supported_plan", lambda *a, **k: False)
    elif case == "no_onward":
        world.plan_feasible_to_map = lambda start, target, goal_at: N(
            terminal_map=target, terminal_at=goal_at, steps=(), cost=0)
    assert s.story_fly_binding(rt, actions, **args) is None
    assert live.calls == actions.actions_executed == 0


@pytest.mark.parametrize("failure", [
    "wrong_landing", "story", ("player_money", 0), ("bag_items", ()),
    ("party_species_ids", (1,)), ("party_hp", (89,)), ("party_pp", ((0, 0, 0, 0),)),
    ("party_moves", ((0, 0, 0, 0),)), ("badge_bits", 255),
])
def test_bad_native_landing_cannot_be_verified_or_award_story_credit(monkeypatch, failure):
    rt, actions, args, live, world, distances, lesson = setup(monkeypatch)
    binding = s.story_fly_binding(rt, actions, **args)
    live.failure = failure
    with pytest.raises(RuntimeError, match="not verified"):
        binding.execute()
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED
    assert lesson["completed_objectives"] == ["receive_pokedex"]
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


def test_stale_flight_rejected_before_input(monkeypatch):
    rt, actions, args, live, world, distances, lesson = setup(monkeypatch)
    binding = s.story_fly_binding(rt, actions, **args)
    live.state = b"changed"
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    assert live.calls == actions.actions_executed == 0


@pytest.mark.parametrize("native_fact", [True, False])
def test_arrival_credit_requires_native_fact_even_after_verified_flight(monkeypatch, native_fact):
    rt, actions, args, live, world, distances, lesson = setup(monkeypatch, arrival=True)
    binding = s.story_fly_binding(rt, actions, **args)
    assert not binding.story_approach_only
    if not native_fact:
        live.failure = "no_fact"
        with pytest.raises(RuntimeError, match="not verified"):
            binding.execute()
        assert lesson["completed_objectives"] == ["receive_pokedex"]
    else:
        report = binding.execute()
        assert report.evidence["objective_completed"]
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
        assert lesson["completed_objectives"][-1] == args["objective_id"]


def test_existing_story_entrypoint_uses_flight_without_replacing_objective(monkeypatch):
    from test_red_player_story_travel import setup as ground_setup
    from pokemon_red_completion import red_player_story_travel as travel
    from pokemon_red_completion import red_training_ground_route as ground
    from pokemon_red_completion import red_player_fly
    rt, actions, route, raw, lesson = ground_setup(monkeypatch)
    monkeypatch.setattr(ground, "RedVermilionGroundTransition", type(route))
    monkeypatch.setattr(red_player_fly, "_noncombat_fly_world", lambda w, r: w)
    # The property-only test route cannot be replaced with a projected world;
    # boundary mode retains it and still takes the new flight prefix.
    calls = []
    binding = object()
    monkeypatch.setattr(s, "story_fly_binding", lambda *a, **k: calls.append(k) or binding)
    got = travel.story_travel_binding(
        rt, actions, objective_id="reach_pewter", route=route, stop_at_map_boundary=True,
    )
    assert got is binding and calls[0]["objective_id"] == "reach_pewter"
    assert actions.actions_executed == 0


def indoor_setup(monkeypatch, *, outside=10):
    from pokemon_red_completion import red_player_story_travel as travel
    from pokemon_red_completion.goal_manager_runtime import (
        ExecutableGoalBinding, GoalExecutionReport, GoalVerification,
    )
    rt, actions, args, live, world, distances, lesson = setup(monkeypatch)
    raw = args['before'].raw
    raw.map_id, raw.player_y, raw.player_x = 172, 5, 2
    args['start'] = TraversalSnapshot(172, (5, 2), True, mode='land', last_outside_map=outside)
    args['objective_id'] = rt.adapter.graph.objective(None).id = 'defeat_giovanni'
    args['final_destination'] = 45
    live.visited = (1,)
    distances[1] = 1
    live.walk_calls, live.walk_quotes, live.walk_failure = 0, [], None
    live.departure_failure = None
    onward = world.plan_feasible_to_map

    def local_plan(start, target, **kwargs):
        if start.map_id != 172:
            return onward(start, target, **kwargs)
        live.plan_calls.append((start, target, kwargs.get('goal_at')))
        if target != outside:
            raise RoutePlanningError('Surf unavailable on distant ground route')
        if live.departure_failure == 'blocked_exit':
            raise RoutePlanningError('Observed indoor object blocks exit')
        step = N(source_map=172, expected_map=outside, expected_at=(6, 7),
                 kind='warp', action_kind=s.MacroActionKind.MOVE, action='down',
                 source_mode='land', expected_mode='land')
        if live.departure_failure == 'unsupported_exit':
            step.action_kind = s.MacroActionKind.FIELD_MOVE
        return N(terminal_map=outside, terminal_at=(6, 7), terminal_mode='land',
                 steps=(step,), macro_path=N(maps=(172, outside)), cost=1)

    world.plan_feasible_to_map = local_plan
    def walk_binding(runtime, executor, **kwargs):
        live.walk_quotes.append(kwargs)
        assert runtime is rt and executor is actions
        assert kwargs['objective_id'] == 'defeat_giovanni'
        assert kwargs['intermediate_map'] == outside and not kwargs['stop_at_map_boundary']
        state, consumed, report = live.state, False, None
        def execute():
            nonlocal consumed, report
            if consumed or live.state != state:
                raise ValueError('stale or consumed walking prefix')
            consumed = True
            live.walk_calls += 1
            after = N(**vars(raw))
            after.map_id, after.player_y, after.player_x = outside, 6, 7
            if live.walk_failure == 'wrong_arrival':
                after.player_x += 1
            elif live.walk_failure == 'story':
                after.event_flags = bytes([1]) + bytes(319)
            elif isinstance(live.walk_failure, tuple):
                setattr(after, *live.walk_failure)
            live.raw, live.state = after, b'outside'
            actions.actions_executed += 3
            rt.emulator.frame_count += 48
            report = GoalExecutionReport(3, 48, dict(objective_completed=False))
            return report
        def verify(value):
            return GoalVerification.succeeded() if value is report else GoalVerification.failed(
                s.GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return ExecutableGoalBinding('qualified-walk', s.GoalKind.ADVANCE_STORY,
            .01, .01, execute, verify, maximum_cash_debit=None if live.walk_failure=='uncertified' else 0,
            story_objective_ref='defeat_giovanni', story_approach_only=True)

    monkeypatch.setattr(travel, 'story_travel_binding', walk_binding)
    return rt, actions, args, live, world, distances, lesson


def test_indoor_story_departure_needs_only_local_walk_and_qualified_onward_fly(monkeypatch):
    rt, actions, args, live, world, distances, lesson = indoor_setup(monkeypatch)
    binding = s.story_fly_binding(rt, actions, **args)
    assert binding is not None
    assert binding.story_approach_only and binding.story_objective_ref=='defeat_giovanni'
    assert binding.maximum_cash_debit==0
    assert live.walk_calls==live.calls==actions.actions_executed==0
    assert all(target==10 for start,target,_ in live.plan_calls if start.map_id==172)
    report = binding.execute()
    assert (live.raw.map_id,live.raw.player_y,live.raw.player_x)==(10,6,7)
    assert live.walk_calls==1 and live.calls==0
    assert (report.actions_executed,report.frames_executed)==(3,48)
    assert report.evidence['objective_completed'] is False
    assert report.evidence['support']=='native_indoor_story_fly_departure'
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert lesson['completed_objectives']==['receive_pokedex']
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED
    with pytest.raises(ValueError,match='consumed'):
        binding.execute()


@pytest.mark.parametrize('failure', ['blocked_exit','unsupported_exit','unknown_outside',
    'no_fly','no_badge','unvisited','blocked_onward','uncertified','incoherent_origin'])
def test_indoor_departure_refuses_unknown_or_unexecutable_prefix(monkeypatch,failure):
    rt,actions,args,live,world,distances,lesson=indoor_setup(monkeypatch)
    if failure in ('blocked_exit','unsupported_exit'):live.departure_failure=failure
    elif failure=='unknown_outside':args['start']=replace(args['start'],last_outside_map=None)
    elif failure=='no_fly':args['before'].raw.party_moves=((16,98,33,0),)
    elif failure=='no_badge':args['before'].raw.badge_bits=0
    elif failure=='unvisited':live.visited=()
    elif failure=='blocked_onward':live.failure='blocked_onward'
    elif failure=='uncertified':live.walk_failure='uncertified'
    elif failure=='incoherent_origin':args['start']=replace(args['start'],at=(1,1))
    assert s.story_fly_binding(rt,actions,**args) is None
    assert live.walk_calls==live.calls==actions.actions_executed==0


@pytest.mark.parametrize('failure', ['wrong_arrival','story',('player_money',0),
    ('party_hp',(89,)),('party_pp',((0,0,0,0),)),('party_moves',((0,0,0,0),)),
    ('bag_items',()),('badge_bits',255)])
def test_indoor_departure_verifies_exact_arrival_and_protected_facts(monkeypatch,failure):
    rt,actions,args,live,world,distances,lesson=indoor_setup(monkeypatch)
    binding=s.story_fly_binding(rt,actions,**args)
    assert binding is not None
    live.walk_failure=failure
    with pytest.raises(RuntimeError,match='departure'):
        binding.execute()
    assert binding.verify(None).status is GoalDecisionOutcome.FAILED
    assert lesson['completed_objectives']==['receive_pokedex'] and live.calls==0


def test_indoor_departure_stale_source_rejected_before_input(monkeypatch):
    rt,actions,args,live,world,distances,lesson=indoor_setup(monkeypatch)
    binding=s.story_fly_binding(rt,actions,**args)
    assert binding is not None
    live.state=b'changed'
    with pytest.raises(ValueError,match='stale'):
        binding.execute()
    assert live.walk_calls==live.calls==actions.actions_executed==0


def test_story_entrypoint_exits_indoor_origin_before_retrying_actual_fly(monkeypatch):
    from pokemon_red_completion import red_player_story_travel as travel
    from pokemon_red_completion import red_training_ground_route as ground
    entry = travel.story_travel_binding
    rt,actions,args,live,world,distances,lesson=indoor_setup(monkeypatch)
    objective=rt.adapter.graph.objective(None)
    rt.adapter.graph.available_objectives=lambda _: (objective,)
    monkeypatch.setattr(travel,'_field_ready',lambda _: live.ready)
    monkeypatch.setattr(travel,'capture_player_lesson_snapshot',lambda _: (
        N(raw=live.raw,game_state=object()),{k:list(v)for k,v in lesson.items()}))
    monkeypatch.setattr(travel,'Gen1TraversalObserver',lambda *a,**k: N(observe=lambda:args['start']))
    monkeypatch.setattr(travel,'Gen1TrainerSightProjector',lambda *a,**k:object())
    monkeypatch.setattr(ground,'RedVermilionGroundTransition',type(args['route']))
    def unavailable_ground(*a,**k):
        raise RoutePlanningError('Full ground route needs unavailable Surf')
    monkeypatch.setattr(travel,'story_frontier_target',unavailable_ground)
    binding=entry(rt,actions,objective_id='defeat_giovanni',route=args['route'],
                  frontier=True,stop_at_map_boundary=True)
    assert binding is not None and binding.story_approach_only
    assert live.walk_calls==live.calls==actions.actions_executed==0
    report=binding.execute()
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert live.walk_calls==1 and live.calls==0 and live.raw.map_id==10
    assert lesson['completed_objectives']==['receive_pokedex']


@pytest.mark.parametrize('active,script',[(True,0),(False,1),(True,1)])
def test_indoor_story_departure_never_bypasses_paid_safari_exit(monkeypatch,active,script):
    rt,actions,args,live,world,distances,lesson=indoor_setup(monkeypatch)
    args['before'].raw.map_id=int(s.MapId.SAFARI_ZONE_GATE)
    args['start']=replace(args['start'],map_id=int(s.MapId.SAFARI_ZONE_GATE))
    rt.reader.read_safari_session_state=lambda:N(has_active_session=active)
    rt.reader.read_safari_zone_gate_script=lambda:script
    assert s.story_fly_binding(rt,actions,**args) is None
    assert live.walk_calls==live.calls==actions.actions_executed==0


@pytest.mark.parametrize('objective,destination',[('defeat_giovanni',45),('defeat_lorelei',9)])
@pytest.mark.parametrize('multifloor', [False,True])
@pytest.mark.parametrize('status', [0,8,None])
def test_real_story_walker_reaches_certified_outdoor_endpoint(monkeypatch,multifloor,status,objective,destination):
    from dataclasses import dataclass
    from pokemon_red_completion import red_player_story_travel as travel
    from pokemon_red_completion import red_training_ground_route as ground
    from pokemon_red_completion import red_player_fly
    rt,actions,args,live,world,distances,lesson=setup(monkeypatch)
    raw=args['before'].raw
    raw.party_status=None if status is None else (status,)
    raw.map_id,raw.player_y,raw.player_x=172,5,2
    args['start']=TraversalSnapshot(172,(5,2),True,mode='land',last_outside_map=10)
    args['objective_id']=rt.adapter.graph.objective(None).id=objective
    args['final_destination']=destination
    live.visited=(1,);distances[1]=1
    original_plan=world.plan_feasible_to_map
    maps=(172,171,10)if multifloor else(172,10)
    def plan(start,target,**kwargs):
        if start.map_id!=172:
            return original_plan(start,target,**kwargs)
        if target not in maps[1:]:
            raise RoutePlanningError('Full terrestrial route requires unavailable Surf')
        endpoint=maps.index(target)
        steps=tuple(N(source_map=a,expected_map=b,expected_at=(6,7),kind='warp',
            action_kind=s.MacroActionKind.MOVE,action='down',source_mode='land',expected_mode='land')
            for a,b in zip(maps[:endpoint],maps[1:endpoint+1]))
        return N(steps=steps,terminal_map=target,terminal_at=(6,7),terminal_mode='land',
                 macro_path=N(maps=maps[:endpoint+1]),cost=len(steps))
    world.plan_feasible_to_map=plan
    @dataclass
    class Route:
        rom: bytes=b'rom'
        route_world: object=None
        destination_map: int=0
        destination_at: tuple=(0,0)
        require_cash_safe: bool=False
        maximum_flees: int=0
        maximum_scripted_dialogues: int=0
        def __call__(self,*unused):
            assert self.require_cash_safe and self.maximum_flees==self.maximum_scripted_dialogues==0
            live.walk_calls+=1
            after=N(**vars(raw))
            after.map_id=self.destination_map
            after.player_y,after.player_x=self.destination_at
            live.raw,live.state=after,b'walked'
            actions.actions_executed+=3
            rt.emulator.frame_count+=48
    args['route']=Route(route_world=world);live.walk_calls=0
    declared_objective=rt.adapter.graph.objective(None)
    rt.adapter.graph.available_objectives=lambda _:(declared_objective,)
    monkeypatch.setattr(ground,'RedVermilionGroundTransition',Route)
    monkeypatch.setattr(red_player_fly,'_noncombat_fly_world',lambda w,r:w)
    monkeypatch.setattr(travel,'_field_ready',lambda _:live.ready)
    monkeypatch.setattr(travel,'capture_player_lesson_snapshot',lambda _:(
        N(raw=live.raw,game_state=object()),{k:list(v)for k,v in lesson.items()}))
    monkeypatch.setattr(travel,'Gen1TraversalObserver',lambda *a,**k:N(observe=lambda:args['start']))
    monkeypatch.setattr(travel,'Gen1TrainerSightProjector',lambda *a,**k:object())
    monkeypatch.setattr(travel,'find_macro_path',lambda *a,**k:N(maps=(*maps,1,destination)))
    from pokemon_red_completion import red_player_cash_exposure as cash
    monkeypatch.setattr(cash,'encounter_free_maps',lambda rom:frozenset(maps))
    def distant_ground_blocked(*a,**k):
        raise RoutePlanningError('Full ground route needs Surf')
    monkeypatch.setattr(travel,'story_frontier_target',distant_ground_blocked)
    binding=travel.story_travel_binding(rt,actions,objective_id=objective,
        route=args['route'],frontier=True,stop_at_map_boundary=True)
    assert live.walk_calls==live.calls==actions.actions_executed==0
    if status != 0:
        assert binding is None
        return
    assert binding is not None and binding.story_approach_only
    assert binding.story_objective_ref==objective
    assert objective not in travel.ARRIVAL_OBJECTIVES
    report=binding.execute()
    assert (live.raw.map_id,live.raw.player_y,live.raw.player_x)==(10,6,7)
    assert live.walk_calls==1 and live.calls==0
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert lesson['completed_objectives']==['receive_pokedex']


def test_indoor_departure_accepts_only_native_seven_badge_viridian_unlock(monkeypatch):
    from pokemon_red_completion.observation import EventFlag
    rt,actions,args,live,world,distances,lesson=indoor_setup(monkeypatch,outside=1)
    raw=args['before'].raw
    raw.badge_bits=0xff ^ int(Badge.EARTH)
    live.visited=(0,);distances.update({1:8,0:1})
    expected=bytearray(raw.event_flags)
    event=int(EventFlag.VIRIDIAN_GYM_OPEN)
    expected[event//8]|=1 << (event%8)
    binding=s.story_fly_binding(rt,actions,**args)
    assert binding is not None
    live.walk_failure=('event_flags',bytes(expected))
    report=binding.execute()
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert live.raw.map_id==1 and live.calls==0
    assert lesson['completed_objectives']==['receive_pokedex']
