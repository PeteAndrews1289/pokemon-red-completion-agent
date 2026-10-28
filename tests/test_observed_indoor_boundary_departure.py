from types import SimpleNamespace as N
import json
import os

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.red_indoor_departure_plan import bounded_indoor_boundary_departure
from pokemon_red_completion.route_plan import RoutePlanningError


@pytest.mark.parametrize('damage', [None, 'not_ready', 'water', 'outside', 'detour',
    'field_move', 'remote_action', 'multiple_maps', 'connection', 'too_long', 'other_outdoor'])
def test_prefix_is_only_one_current_map_warp_on_existing_corridor(monkeypatch, damage):
    import pokemon_red_completion.global_router as router
    start=N(ready=True, interruption=None, mode='land', map_id=101, last_outside_map=5)
    step=N(source_map=101, expected_map=96, kind='warp', action_kind=MacroActionKind.MOVE,
           action='down', source_mode='land', expected_mode='land')
    plan=N(macro_path=N(maps=(101,96)),steps=(step,),terminal_map=96,terminal_mode='land')
    corridor=N(maps=(101,96,95,94,5),edges=(N(kind='warp'),))
    if damage=='not_ready':start.ready=False
    elif damage=='water':start.mode='water'
    elif damage=='outside':start.last_outside_map=101
    elif damage=='detour':step.expected_map=5
    elif damage=='field_move':step.action_kind=MacroActionKind.FIELD_MOVE
    elif damage=='remote_action':step.source_map=96
    elif damage=='multiple_maps':plan.macro_path.maps=(101,96,95)
    elif damage=='connection':corridor.edges[0].kind='connection'
    elif damage=='other_outdoor':corridor.maps=(101,7,5)
    elif damage=='too_long':plan.steps=(step,)*129
    calls=[]
    monkeypatch.setattr(router,'find_macro_path',lambda *a,**k:corridor)
    world=N(macro_graph=object(),plan_feasible_to_map=lambda start,destination:
            calls.append(destination)or plan)
    result=bounded_indoor_boundary_departure(start,world)
    assert result is (plan if damage is None else None)
    assert all(destination==96 for destination in calls)


def test_actual_rom_prefix_does_not_remove_unobserved_rival(monkeypatch):
    from pokemon_red_completion.observation import CurrentMapBlocks
    from pokemon_red_completion.route_executor import TraversalSnapshot
    from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld
    source=os.environ.get('POKEMON_EGRESS_READBACK')
    rom_path=os.environ.get('POKEMON_TEST_ROM')
    if not source or not rom_path:
        pytest.skip('explicit closed readback and verified ROM needed for topology regression')
    from pathlib import Path
    q=json.loads(Path(source).read_bytes())
    assert q['passed']and q['state_unchanged']and q['frame_delta']==0
    t=q['traversal']
    assert t['hazards']==[]
    start=TraversalSnapshot(map_id=t['map_id'],at=tuple(t['at']),ready=t['ready'],
        interruption=t['interruption'],mode=t['mode'],last_outside_map=t['last_outside_map'],
        occupied=frozenset(map(tuple,t['occupied'])),capabilities=frozenset(t['capabilities']))
    world=StrategicScenarioRouteWorld.from_rom(Path(rom_path).read_bytes())
    with pytest.raises(RoutePlanningError):world.plan_feasible_to_map(start,start.last_outside_map)
    prefix=bounded_indoor_boundary_departure(start,world)
    assert prefix.macro_path.maps==(101,96)and len(prefix.steps)==8
    arrival=prefix.terminal_at
    assert arrival in world.object_blockers[96]
    assert not world.local_graphs[96].neighbors(arrival)
    # Simulated newly observed room: only the actual current-map table can
    # replace its original objects. This test does not assert a native visit.
    raw=N(game_started=True,battle_state=0,map_id=96)
    present=tuple(N(at=at,sprite_index=i)for i,at in enumerate(
        sorted(world.object_blockers[96]-{arrival}),1))
    reader=N(read=lambda:raw,read_input_readiness=lambda:N(ready=True),
        read_bottom_dialogue_box_visible=lambda:False,trainer_engagement_active=lambda:False,
        read_current_map_blocks=lambda:CurrentMapBlocks(96,world.terrain[96].blocks),
        read_current_map_objects=lambda:present)
    refreshed=world.with_current_observation(reader)
    assert arrival not in refreshed.object_blockers[96]
    assert refreshed.local_graphs[96].neighbors(arrival)
    assert world.object_blockers[96]!=refreshed.object_blockers[96]
    assert world.object_blockers[95]==refreshed.object_blockers[95]
