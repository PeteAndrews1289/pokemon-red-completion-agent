"""Static warp geometry must not fabricate healing behind a League exit script."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.gen1_story_routing import (
    LEAGUE_REVERSE_EXIT_REQUIREMENTS,
    LEAGUE_REVERSE_EXIT_SUPPORTED,
    apply_gen1_league_reverse_exit_requirements,
    gen1_story_capabilities,
)
from pokemon_red_completion.local_router import (
    LocalEdge,
    LocalGraph,
    LocalRouterError,
    find_local_path,
)
from pokemon_red_completion.observation import EventFlag, MapId, RawGameState


def room_graph():
    nodes=frozenset((row,col) for row in range(9,12) for col in (4,5))
    return LocalGraph({a:tuple(LocalEdge(b,'down' if b[0]>a[0] else 'up',cost=1)
        for b in nodes if abs(a[0]-b[0])+abs(a[1]-b[1])==1) for a in nodes})


@pytest.mark.parametrize('room,event',(
    (MapId.LORELEIS_ROOM,EventFlag.BEAT_LORELEI),
    (MapId.BRUNOS_ROOM,EventFlag.BEAT_BRUNO),
    (MapId.AGATHAS_ROOM,EventFlag.BEAT_AGATHA),
))
@pytest.mark.parametrize('won', (False,True))
def test_native_victory_does_not_unlock_a_reverse_nurse_route(room,event,won):
    flags=bytearray(0x120)
    if won:
        flags[int(event)//8]|=1<<(int(event)%8)
    raw=RawGameState(game_started=True,map_id=room,player_y=9,player_x=5,
        party_count=1,battle_state=0,event_flags=bytes(flags),status_flags_1=0)
    capabilities=gen1_story_capabilities(raw)
    assert LEAGUE_REVERSE_EXIT_SUPPORTED not in capabilities
    graph=apply_gen1_league_reverse_exit_requirements({int(room):room_graph()})[int(room)]
    with pytest.raises(LocalRouterError,match='no permitted local route'):
        find_local_path(graph,(9,5),(11,5),capabilities=capabilities)
    # Native forward entry and retreat from a rejected doorway remain possible.
    assert find_local_path(graph,(11,5),(9,5),capabilities=capabilities)
    assert find_local_path(graph,(10,5),(9,5),capabilities=capabilities)
    assert gen1_story_capabilities(replace(raw,event_flags=None)) <= capabilities


def test_all_three_scripts_cover_both_door_columns_and_allow_no_observed_service():
    assert len(LEAGUE_REVERSE_EXIT_REQUIREMENTS)==24
    assert {r.map_id for r in LEAGUE_REVERSE_EXIT_REQUIREMENTS}=={
        int(MapId.LORELEIS_ROOM),int(MapId.BRUNOS_ROOM),int(MapId.AGATHAS_ROOM)}
    assert all(r.predicate==LEAGUE_REVERSE_EXIT_SUPPORTED for r in LEAGUE_REVERSE_EXIT_REQUIREMENTS)
    assert all(sum(abs(a-b) for a,b in zip(r.source_at,r.target_at,strict=True))==1
               for r in LEAGUE_REVERSE_EXIT_REQUIREMENTS)


def test_other_maps_keep_their_existing_geometry():
    original=room_graph()
    assert apply_gen1_league_reverse_exit_requirements({int(MapId.INDIGO_PLATEAU_LOBBY):original})[
        int(MapId.INDIGO_PLATEAU_LOBBY)]==original


def test_live_terrain_rebuild_preserves_the_same_reverse_script_guard(monkeypatch):
    from pokemon_red_completion import gen1_seafoam
    from pokemon_red_completion import strategic_navigation_scenario_runtime as module

    room=int(MapId.LORELEIS_ROOM)
    original=room_graph()
    world=SimpleNamespace(rules=None,rom=b'fixture',object_blockers={room:frozenset()},
        forced_movements={},macro_graph=SimpleNamespace(warp_locations={}))
    monkeypatch.setattr(module,'surf_local_graph',lambda *a,**k:original)
    monkeypatch.setattr(gen1_seafoam,'apply_seafoam_hole_guards',lambda rom,graphs:graphs)
    graph=module.StrategicScenarioRouteWorld._graph_for_terrain(world,SimpleNamespace(map_id=room))
    with pytest.raises(LocalRouterError,match='no permitted local route'):
        find_local_path(graph,(9,5),(11,5),capabilities=frozenset())
    assert find_local_path(graph,(11,5),(9,5),capabilities=frozenset())
