from types import SimpleNamespace as NS

import pytest

import pokemon_red_completion.red_native_boxed_evolution as module
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_traversal import MapObjectEvent
from pokemon_red_completion.observation import CurrentMapObject
from pokemon_red_completion.route_executor import ReplanRequest, TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError


@pytest.mark.parametrize('movement,expected', [(0xFE, True), (0xFF, False), (0, False), (0xFD, False)])
def test_cartridge_walk_declaration_is_distinct_from_animation(movement, expected):
    event = MapObjectEvent(133, 16, 3, 7, movement, 2, 2, object_index=2)
    assert event.can_walk is expected
    assert not CurrentMapObject(2, 16, (3, 3), 2, 40).moving


@pytest.mark.parametrize('case', ['vacates', 'static', 'wrong_index', 'wrong_picture', 'missing', 'ambiguous', 'never_vacates', 'unsafe', 'visible_lag', 'logical_lag'])
def test_idle_center_walker_wait_preserves_goal_and_real_blockers(monkeypatch, case):
    map_id, standing, goal, other = 133, (4, 3), (3, 3), (2, 11)
    waits, delegated = [], []
    blocker = CurrentMapObject(2, 16, goal, 2, 40)
    stationary = CurrentMapObject(4, 42, other, 2, 255)
    event = MapObjectEvent(map_id, 17 if case == 'wrong_picture' else 16, 3, 7,
                           0xFF if case == 'static' else 0xFE, 2, 2,
                           object_index=3 if case == 'wrong_index' else 2)
    events = () if case == 'missing' else (event, event) if case == 'ambiguous' else (event,)
    monkeypatch.setattr(module, 'map_object_events', lambda rom, ids: events)

    def occupied():
        return not waits or case == 'never_vacates' or (case == 'logical_lag' and len(waits) < 2)

    def objects():
        return (stationary, blocker) if occupied() else (stationary,)

    def live():
        rendered = occupied() or (case == 'visible_lag' and len(waits) < 2)
        if case == 'logical_lag' and waits:
            rendered = False
        return TraversalSnapshot(map_id, standing, True, mode='land',
                                 occupied=frozenset({other, goal} if rendered else {other}))

    raw = NS(map_id=map_id, player_y=standing[0], player_x=standing[1],
             player_money=123, bag_items=((1, 1),), badge_bits=255,
             event_flags=b'', battle_state=0)

    def observe():
        values = vars(raw).copy()
        if case == 'unsafe' and waits:
            values['player_money'] = 124
        return NS(input_ready=True, raw=NS(**values), party='party', collection_observation='dex')

    def delegate(request):
        delegated.append(request)
        if goal in request.blocked[map_id]:
            raise RoutePlanningError('PC remains occupied')
        return 'same declared Center route'

    runtime = NS(reader=NS(read_current_map_objects=objects), adapter=NS(observe=observe))
    world = NS(rom=b'authenticated cartridge fixture', replanner=lambda: delegate)
    world.with_current_observation = lambda reader: world
    actions = NS(execute=lambda action: waits.append(action))
    monkeypatch.setattr(module, 'Gen1TraversalObserver', lambda reader: NS(observe=live))
    request = ReplanRequest(live(), map_id, goal, {map_id: frozenset({goal, other})}, 1)
    replan = module.native_evolution_pc_replanner(runtime, world, actions)
    if case in ('vacates', 'visible_lag', 'logical_lag'):
        assert replan(request) == 'same declared Center route'
        assert len(waits) == (2 if case in ('visible_lag', 'logical_lag') else 1)
        assert delegated[0].goal_map == map_id and delegated[0].goal_at == goal
        assert delegated[0].blocked[map_id] == frozenset({other})
        assert request.blocked[map_id] == frozenset({goal, other})
    elif case == 'never_vacates':
        with pytest.raises(module.context.RedGoalContextError, match='within its bound'):
            replan(request)
        assert len(waits) == 16 and not delegated
    elif case == 'unsafe':
        with pytest.raises(module.context.RedGoalContextError, match='protected native state'):
            replan(request)
        assert len(waits) == 1 and not delegated
    else:
        with pytest.raises(RoutePlanningError, match='occupied'):
            replan(request)
        assert not waits
    assert all(action.kind is MacroActionKind.WAIT and action.repeat == 120 for action in waits)


def test_idle_unknown_world_cannot_authorize_wait():
    blocker = CurrentMapObject(2, 16, (3, 3), 2, 40)
    assert not module._center_blocker_can_walk(blocker, NS(), 133)
