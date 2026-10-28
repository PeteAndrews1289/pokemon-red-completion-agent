from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_red_live_option_menu import _binding, _ordinary_bindings, _situation

from pokemon_red_completion.goal_manager import GoalAvailability, GoalKind, GoalUnavailableReason
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification
from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory


def empty_base():
    base = _ordinary_bindings([])
    return replace(base, bindings=(), opportunities=tuple(replace(
        o, availability=GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
        estimated_effort=None, estimated_risk=None, resource_quote=None,
    ) for o in base.opportunities))


def recovery():
    return replace(_binding(GoalKind.RECOVER_CONTROL,
                    binding_ref='pokemon.red:empty-indoor-departure:source', calls=[]), maximum_cash_debit=0)


def test_empty_fallback_is_control_only_and_observed_before_any_input():
    calls = []
    rt = N(emulator=N(save_state_bytes=lambda: b'source'))
    inventory = NativeStoryBranchInventory(lambda *_: empty_base(), lambda *_: (),
        enumerate_empty_recovery=lambda *_: calls.append('quote') or recovery())
    ordinary = inventory.enumerate(rt, N(), N(situation=_situation()))
    assert calls == ['quote']
    assert len(ordinary.bindings) == 1 and ordinary.bindings[0].kind is GoalKind.RECOVER_CONTROL
    assert inventory.supplements(rt, N(), None, ordinary) == ()


@pytest.mark.parametrize('location', ['base', 'story', 'resource'])
def test_existing_candidates_prevent_empty_fallback(location):
    calls = []
    base = _ordinary_bindings([]) if location == 'base' else empty_base()
    branch = _binding(GoalKind.ADVANCE_STORY, binding_ref='existing:story', calls=[])
    resource = _binding(GoalKind.RESUPPLY, binding_ref='existing:resource', calls=[])
    inventory = NativeStoryBranchInventory(lambda *_: base,
        lambda *_: ((branch, __import__('pokemon_red_completion.player_option_challenge',
            fromlist=['OptionChallenge']).OptionChallenge(False, False, 0., 0., 0.)),)
            if location == 'story' else (),
        enumerate_resources=(lambda *_: (resource,)) if location == 'resource' else None,
        enumerate_empty_recovery=lambda *_: calls.append('must not quote') or recovery())
    inventory.enumerate(N(emulator=N(save_state_bytes=lambda: b'source')), N(), N(situation=_situation()))
    assert not calls


@pytest.mark.parametrize('fault', ['wrong_kind', 'spending', 'wrong_ref', 'changed_source'])
def test_empty_fallback_rejects_unqualified_or_mutating_quote(fault):
    state = [b'source']
    binding = recovery()
    if fault == 'wrong_kind':
        binding = replace(binding, kind=GoalKind.ADVANCE_STORY)
    elif fault == 'spending':
        binding = replace(binding, maximum_cash_debit=1)
    elif fault == 'wrong_ref':
        binding = replace(binding, binding_ref='not-an-indoor-exit')
    def callback(*_):
        if fault == 'changed_source':
            state[0] = b'changed'
        return binding
    inventory = NativeStoryBranchInventory(lambda *_: empty_base(), lambda *_: (),
                                          enumerate_empty_recovery=callback)
    with pytest.raises(ValueError):
        inventory.enumerate(N(emulator=N(save_state_bytes=lambda: state[0])), N(), N(situation=_situation()))


@pytest.fixture
def departure(monkeypatch):
    import pokemon_red_completion.red_indoor_departure_plan as module
    import pokemon_red_completion.gen1_route_runtime as traversal
    import pokemon_red_completion.gen1_trainer_sight as sight
    import pokemon_red_completion.red_player_field_goals as field
    import pokemon_red_completion.red_player_lesson as lesson
    import pokemon_red_completion.red_player_cash_exposure as cash
    import pokemon_red_completion.red_routed_semantic_goal as transport
    from pokemon_red_completion.observation import OverworldMovementMode
    raw = N(map_id=101, player_y=3, player_x=4, party_species_ids=(1,), party_levels=(25,),
            party_hp=(60,), party_max_hp=(60,), party_stats=((1,),), party_status=(0,),
            party_moves=((1, 0, 0, 0),), party_pp=((35, 0, 0, 0),), bag_items=((196, 1),),
            player_money=2446, badge_bits=3)
    state = [b'source']
    ready = [True]
    lessons = [dict(completed_objectives=['obtain_cut'], party=[dict(specimen_ref='one', experience=8004)])]
    plan = N(steps=(1, 2), terminal_map=5, terminal_at=(11, 7))
    captured = []
    observer = N(observe=lambda: N(map_id=101, last_outside_map=5))
    reader = N(read=lambda: raw, read_overworld_movement_mode=lambda: OverworldMovementMode.WALKING,
               read_pending_trainer_battle_identity=lambda: None, read_fly_menu_state=lambda: None)
    rt = N(reader=reader, emulator=N(save_state_bytes=lambda: state[0],frame_count=0))
    monkeypatch.setattr(field, '_field_ready', lambda _: ready[0])
    monkeypatch.setattr(lesson, 'capture_player_lesson_snapshot', lambda _: (N(raw=raw), lessons[0]))
    monkeypatch.setattr(traversal, 'Gen1TraversalObserver', lambda *a, **k: observer)
    monkeypatch.setattr(sight, 'Gen1TrainerSightProjector', lambda *a, **k: None)
    monkeypatch.setattr(module, 'bounded_indoor_departure', lambda *_: plan)
    monkeypatch.setattr(cash, 'require_cash_safe_plan', lambda *a: None)
    def make_transport(**kwargs):
        captured.append(kwargs)
        def execute():
            raw.map_id, raw.player_y, raw.player_x = plan.terminal_map, *plan.terminal_at
            state[0] = b'terminal'
            kwargs['actions'].actions_executed+=2
            rt.emulator.frame_count+=48
            return GoalExecutionReport(2, 48, {})
        verified = []
        def verify(_):
            assert not verified, 'underlying transport verification is one-shot'
            verified.append(True)
            return GoalVerification.succeeded()
        return N(route_binding=lambda: N(execute=execute, verify=verify))
    monkeypatch.setattr(transport, 'RedSemanticTransportRoute', make_transport)
    route = N(rom=b'ROM', route_world=N(with_current_observation=lambda _: 'observed_world'))
    return N(module=module, rt=rt, route=route, raw=raw, state=state, ready=ready,
             lessons=lessons, captured=captured, plan=plan)


def test_departure_reuses_exact_plan_without_flight_replan_fieldmove_or_goal(departure):
    d = departure
    binding = d.module.indoor_departure_binding(d.rt, N(actions_executed=0), route=d.route)
    assert binding.kind is GoalKind.RECOVER_CONTROL and binding.maximum_cash_debit == 0
    assert d.state[0] == b'source' and d.captured[0]['plan'] is d.plan
    assert not {'replanner', 'field_actions'} & d.captured[0].keys()
    assert d.captured[0]['interruption_handler'].handled_interruption_kinds==frozenset({'native_ship_departure'})
    assert not d.captured[0]['interruption_handler'].handled_hazard_kinds
    result = binding.execute()
    assert result.actions_executed == 2 and result.frames_executed == 48
    assert result.evidence['objective_completed'] is False
    assert result.evidence['requires_fresh_outdoor_observation'] is True
    assert binding.verify(result).status.value == 'succeeded'
    with pytest.raises(ValueError, match='consumed'):
        binding.execute()


@pytest.mark.parametrize('fault', ['stale', 'cash', 'party', 'objective', 'experience', 'unsafe'])
def test_departure_preserves_source_and_terminal_resources(departure, fault):
    d = departure
    binding = d.module.indoor_departure_binding(d.rt, N(actions_executed=0), route=d.route)
    if fault == 'stale':
        d.state[0] = b'wrong'
        with pytest.raises(ValueError, match='stale'):
            binding.execute()
        return
    # Capture source uses immutable RawGameState in production; replace this spy
    # object at the reader, rather than mutating both the source and current view.
    current = N(**vars(d.raw))
    d.rt.reader.read = lambda: current
    if fault == 'cash':
        current.player_money -= 1
    elif fault == 'party':
        current.party_hp = (59,)
    elif fault == 'objective':
        d.lessons[0] = dict(completed_objectives=['obtain_cut', 'defeat_surge'], party=d.lessons[0]['party'])
    elif fault == 'experience':
        d.lessons[0] = dict(completed_objectives=['obtain_cut'], party=[dict(specimen_ref='one', experience=8005)])
    else:
        d.ready[0] = False
    if fault == 'unsafe':
        with pytest.raises(ValueError):
            binding.execute()
    else:
        with pytest.raises(RuntimeError, match='protected'):
            binding.execute()


def test_whole_binding_falls_back_to_first_boundary_and_demands_fresh_observation(departure,monkeypatch):
    d=departure
    calls=[]
    d.plan.terminal_map=96
    monkeypatch.setattr(d.module,'bounded_indoor_departure',lambda *_:None)
    monkeypatch.setattr(d.module,'bounded_indoor_boundary_departure',lambda *_:calls.append('prefix')or d.plan)
    binding=d.module.indoor_departure_binding(d.rt,N(actions_executed=0),route=d.route)
    assert calls==['prefix']and d.state[0]==b'source'
    result=binding.execute()
    assert result.evidence['requires_fresh_boundary_observation']is True
    assert result.evidence['requires_fresh_outdoor_observation']is False
    assert result.evidence['objective_completed']is False
    assert binding.verify(result).status.value=='succeeded'
