from types import SimpleNamespace
import pytest
from pokemon_red_completion.red_training_ground_route import RedVermilionGroundTransition
from pokemon_red_completion.route_executor import TraversalSnapshot,TraversalHazard
from pokemon_red_completion.route_plan import RoutePlanningError
from test_red_training_ground_route import _world

@pytest.mark.parametrize('factory',[True,1,'binding'])
def test_ground_rejects_noncallable_trainer_authority(factory):
    with pytest.raises(TypeError,match='binding factory'):
        RedVermilionGroundTransition(b'rom',_world(),trainer_binding_factory=factory)

@pytest.mark.parametrize('limit',[True,0,33])
def test_ground_rejects_unbounded_trainer_allowance(limit):
    with pytest.raises(ValueError,match='allowance'):
        RedVermilionGroundTransition(b'rom',_world(),maximum_learned_trainers=limit)

@pytest.mark.parametrize('options',[dict(require_cash_safe=True,maximum_flees=0)])
def test_ground_preserves_cash_safe_trainer_prohibition(options):
    with pytest.raises(ValueError,match='conflict'):
        RedVermilionGroundTransition(b'rom',_world(),trainer_binding_factory=lambda:None,**options)

def test_only_explicit_learned_factory_can_admit_sight_without_removing_other_constraints():
    start=TraversalSnapshot(20,(8,23),True,mode='land',occupied=frozenset({(7,24)}),hazards=(TraversalHazard((7,23),'trainer_sight'),TraversalHazard((8,22),'unsupported_hazard')),capabilities=frozenset({'move:cut'}))
    seen=[];answer=object()
    def bounded(*args,**kwargs):raise RoutePlanningError('no bounded corridor')
    def complete(*args,**kwargs):seen.append((args,kwargs));return answer
    world=SimpleNamespace(plan_feasible_to_map=bounded,_plan_candidate=complete)
    factory=lambda:None
    route=RedVermilionGroundTransition(b'rom',_world(),allow_complete_cut_search=True,trainer_binding_factory=factory)
    assert route._initial_plan(world,start)is answer
    assert seen[0][0][0]is start
    assert seen[0][1]['blocked']=={20:frozenset({(7,24),(8,22)})}
    assert route.trainer_binding_factory is factory and start.capabilities==frozenset({'move:cut'})

def test_ground_execution_uses_existing_exact_learned_handler_and_finite_allowance(monkeypatch):
    from pokemon_red_completion import red_training_ground_route as module
    from pokemon_red_completion.red_player_engaged_story import EngagedStoryRouteHandler
    from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld

    start = TraversalSnapshot(20, (8, 23), True)
    terminal = TraversalSnapshot(5, (4, 11), True)
    boundaries = iter((start, terminal))
    observer = SimpleNamespace(observe=lambda: next(boundaries))
    monkeypatch.setattr(module, 'Gen1TraversalObserver', lambda *a, **kw: observer)
    monkeypatch.setattr(module, 'Gen1TrainerSightProjector', lambda *a, **kw: object())
    monkeypatch.setattr(StrategicScenarioRouteWorld, 'plan_feasible_to_map', lambda *a, **kw: object())
    monkeypatch.setattr(StrategicScenarioRouteWorld, 'replanner', lambda *a: object())
    port = SimpleNamespace(execute=lambda action: pytest.fail('unexpected primitive input'))
    monkeypatch.setattr(module, 'Gen1FieldMovePort', lambda *a, **kw: port)
    monkeypatch.setattr(module, 'Gen1WildFleeHandler', lambda *a, **kw: object())
    bound = {}
    def ordinary(*args, **kwargs):
        bound.update(kwargs)
        return SimpleNamespace(
            handle=lambda value: pytest.fail('deterministic trainer fallback'),
            handled_hazard_kinds=frozenset({'trainer_sight'}),
            handled_interruption_kinds=frozenset({'battle:2', 'trainer_engagement'}),
        )
    monkeypatch.setattr(module, 'Gen1RouteInterruptionHandler', ordinary)
    factory = lambda: None
    reader = object()
    def execute(plan, actions, observed, *, interruption_handler, **kwargs):
        assert isinstance(interruption_handler, EngagedStoryRouteHandler)
        assert interruption_handler.binding_factory is factory
        assert interruption_handler.reader is reader
        assert interruption_handler.maximum_trainers == 3
        assert bound['maximum_trainer_battles'] == 3
        assert kwargs['limits'].max_interruptions == 35
        assert actions is port and observed is observer
    monkeypatch.setattr(module, 'execute_route', execute)
    module.RedVermilionGroundTransition(
        b'rom', _world(), trainer_binding_factory=factory, maximum_learned_trainers=3,
    )(port, reader, object())
