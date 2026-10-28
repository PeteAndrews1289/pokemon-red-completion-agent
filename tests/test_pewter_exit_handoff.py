"""Pewter's guide is a native prerequisite, never a dialogue-check waiver."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.gen1_story_routing import (
    PEWTER_EAST_EXIT_OPEN,
    PEWTER_EAST_EXIT_TRIGGERS,
    apply_gen1_pewter_exit_requirement,
    gen1_story_capabilities,
    observe_gen1_story_predicates,
)
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import (
    LocalEdge,
    LocalGraph,
    LocalRouterError,
    find_local_path,
)
from pokemon_red_completion.observation import EventFlag, MapId, RawGameState
from pokemon_red_completion.semantic_traversal import PredicateState


def state(*, events=None, started=True, badges=0):
    return RawGameState(
        game_started=started, map_id=MapId.PEWTER_CITY, player_x=34,
        player_y=17, party_count=1, battle_state=0, status_flags_1=0,
        event_flags=events, badge_bits=badges,
    )


def events(*flags):
    payload = bytearray(320)
    for event in flags:
        payload[int(event) // 8] |= 1 << (int(event) % 8)
    return bytes(payload)


@pytest.mark.parametrize("observed, expected", (
    (state(), PredicateState.UNKNOWN),
    (state(events=events()), PredicateState.UNSATISFIED),
    (state(events=events(), badges=255), PredicateState.UNSATISFIED),
    (state(events=events(EventFlag.GOT_TM34)), PredicateState.UNSATISFIED),
    (state(events=events(EventFlag.BEAT_BROCK)), PredicateState.SATISFIED),
    (state(events=events(EventFlag.BEAT_BROCK), started=False), PredicateState.UNKNOWN),
))
def test_exit_uses_only_observed_native_brock_event(observed, expected):
    predicates = {p.name: p.state for p in observe_gen1_story_predicates(observed)}
    assert predicates[PEWTER_EAST_EXIT_OPEN] is expected
    assert (PEWTER_EAST_EXIT_OPEN in gen1_story_capabilities(observed)) is (
        expected is PredicateState.SATISFIED
    )


@pytest.mark.parametrize("trigger", sorted(PEWTER_EAST_EXIT_TRIGGERS))
@pytest.mark.parametrize("delta", ((-1, 0), (1, 0), (0, -1), (0, 1)))
def test_every_incoming_trigger_direction_requires_brock_but_egress_remains(trigger, delta):
    source = (trigger[0] + delta[0], trigger[1] + delta[1])
    original = LocalGraph({
        source: (LocalEdge(trigger, "incoming", requirements=frozenset({"old"})),),
        trigger: (LocalEdge(source, "outgoing"),),
    })
    graph = apply_gen1_pewter_exit_requirement({int(MapId.PEWTER_CITY): original})[
        int(MapId.PEWTER_CITY)
    ]
    assert graph.edges[source][0].requirements == {"old", PEWTER_EAST_EXIT_OPEN}
    with pytest.raises(LocalRouterError, match="no permitted local route"):
        find_local_path(graph, source, trigger, capabilities=frozenset({"old"}))
    assert find_local_path(graph, source, trigger, capabilities=frozenset({
        "old", PEWTER_EAST_EXIT_OPEN,
    })).coordinates == (source, trigger)
    if source not in PEWTER_EAST_EXIT_TRIGGERS:
        assert find_local_path(graph, trigger, source).coordinates == (trigger, source)
    assert original.edges[source][0].requirements == {"old"}


def test_overlay_never_adds_maps_or_wall_edges_and_leaves_other_maps_unchanged():
    original = LocalGraph({(0, 0): ()})
    untouched = int(MapId.CERULEAN_CITY)
    projected = apply_gen1_pewter_exit_requirement({untouched: original})
    assert projected[untouched] is original
    assert apply_gen1_pewter_exit_requirement({}) == {}
    projected = apply_gen1_pewter_exit_requirement({int(MapId.PEWTER_CITY): original})
    assert projected[int(MapId.PEWTER_CITY)].edges == original.edges


def test_live_terrain_rebuild_retains_the_exit_guard(monkeypatch):
    import pokemon_red_completion.strategic_navigation_scenario_runtime as runtime

    trigger, source = (17, 35), (17, 34)
    graph = LocalGraph({source: (LocalEdge(trigger, "right"),), trigger: ()})
    world = runtime.StrategicScenarioRouteWorld(
        macro_graph=MacroGraph({}), local_graphs={}, rom=b"test", terrain={}, rules=None,
        tilesets={}, water_tilesets=frozenset(),
        object_blockers={int(MapId.PEWTER_CITY): frozenset()},
        forced_movements={int(MapId.PEWTER_CITY): {}},
    )
    monkeypatch.setattr(runtime, "surf_local_graph", lambda *a, **k: graph)
    import pokemon_red_completion.gen1_seafoam as seafoam
    monkeypatch.setattr(seafoam, "apply_seafoam_hole_guards", lambda rom, graphs: graphs)

    rebuilt = world._graph_for_terrain(SimpleNamespace(map_id=int(MapId.PEWTER_CITY)))
    assert rebuilt.edges[source][0].requirements == {PEWTER_EAST_EXIT_OPEN}
    with pytest.raises(LocalRouterError, match="no permitted local route"):
        find_local_path(rebuilt, source, trigger)
    assert find_local_path(rebuilt, source, trigger, capabilities=gen1_story_capabilities(
        replace(state(), event_flags=events(EventFlag.BEAT_BROCK))
    )).coordinates == (source, trigger)
