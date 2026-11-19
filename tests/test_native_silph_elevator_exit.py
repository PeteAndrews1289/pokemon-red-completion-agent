from types import SimpleNamespace as N
from dataclasses import replace
import pytest
import pokemon_red_completion.strategic_navigation_scenario_runtime as world
from pokemon_red_completion.global_router import MacroGraph,MacroEdge
from pokemon_red_completion.gen1_maps import MapNode,Passage,PassageKind
from pokemon_red_completion.observation import RetainedMapWarp


def fixture(monkeypatch):
    lift=MapNode(236,4,4,(Passage(None,PassageKind.SCRIPTED,at=(3,1),exit_action=None),Passage(None,PassageKind.SCRIPTED,at=(3,2),exit_action=None)),warp_locations=((3,1),(3,2)),warp_arrivals=((2,1),(2,2)))
    floor=MapNode(181,4,4,(Passage(236,PassageKind.WARP,at=(0,2),arrival_at=(2,1)),),warp_locations=((0,2),),warp_arrivals=((1,2),))
    maps={236:lift,181:floor};monkeypatch.setattr(world,"map_graph",lambda rom:maps)
    graph=MacroGraph(edges={236:(),181:(MacroEdge(236,"warp",at=(0,2),arrival_at=(2,1)),)},outside_nodes=frozenset())
    rows=(RetainedMapWarp((3,1),0,181),RetainedMapWarp((3,2),0,181))
    return graph,maps,rows

@pytest.mark.parametrize("fault",[None,"missing","duplicate","geometry","split_floor","wrong_map","wrong_index","not_reciprocal"])
def test_only_native_reciprocal_lift_return_is_projected(monkeypatch,fault):
    graph,maps,rows=fixture(monkeypatch)
    if fault=="missing":rows=rows[:1]
    if fault=="duplicate":rows=(rows[0],rows[0])
    if fault=="geometry":rows=(replace(rows[0],at=(2,1)),rows[1])
    if fault=="split_floor":rows=(rows[0],replace(rows[1],destination_map=182))
    if fault=="wrong_map":rows=tuple(replace(x,destination_map=1)for x in rows)
    if fault=="wrong_index":rows=tuple(replace(x,destination_warp_index=1)for x in rows)
    if fault=="not_reciprocal":maps[181]=replace(maps[181],passages=())
    reader=N(read_retained_warp_entries=lambda:rows)
    if fault:
        with pytest.raises(ValueError):world._native_silph_elevator_exit(graph,b"rom",reader,N(map_id=236))
        assert graph.edges[236]==()
        return
    projected=world._native_silph_elevator_exit(graph,b"rom",reader,N(map_id=236))
    assert len(projected.edges[236])==2
    assert all(e.target_map==181 and e.arrival_at==(0,2)and e.kind=="warp" for e in projected.edges[236])
    assert graph.edges[236]==()and projected.edges[181]==graph.edges[181]
    cleared=world._native_silph_elevator_exit(projected,b"rom",N(),N(map_id=181))
    assert cleared.edges[236]==()and projected.edges[236]


def test_normal_context_has_identical_graph_and_does_not_read_scripted_state(monkeypatch):
    graph,_,_=fixture(monkeypatch)
    monkeypatch.setattr(world,"map_graph",lambda _:(_ for _ in()).throw(AssertionError("No ROM projection in normal room")))
    assert world._native_silph_elevator_exit(graph,b"rom",N(),N(map_id=1))is graph


def test_projected_graph_still_rejects_invalid_planning_start_before_reading_it(monkeypatch):
    graph,_,rows=fixture(monkeypatch)
    graph=world._native_silph_elevator_exit(graph,b"rom",N(read_retained_warp_entries=lambda:rows),N(map_id=236))
    instance=world.StrategicScenarioRouteWorld(graph,{},b"rom",{},None,{},frozenset(),{})
    with pytest.raises(TypeError,match="traversal snapshot"):
        instance._bounded_single_cut_plan(None,181)


def test_projected_exit_composes_through_decoded_floor_arrival(monkeypatch):
    from pokemon_red_completion.local_router import LocalGraph, LocalEdge
    from pokemon_red_completion.route_plan import plan_route
    graph,maps,rows=fixture(monkeypatch)
    graph=replace(graph,warp_locations={236:((3,1),(3,2)),181:((0,2),)},warp_arrivals={236:((2,1),(2,2)),181:((1,2),)})
    projected=world._native_silph_elevator_exit(graph,b"rom",N(read_retained_warp_entries=lambda:rows),N(map_id=236))
    local=LocalGraph({(1,1):(LocalEdge((2,1),"down","walk"),),(2,1):(LocalEdge((3,1),"down","walk"),),(3,1):()})
    floor=LocalGraph({(0,2):(LocalEdge((1,2),"down","walk"),),(1,2):()})
    route=plan_route(projected,{236:local,181:floor},236,(1,1),181)
    assert route.macro_path.maps==(236,181) and route.terminal_at==(1,2)


def test_scripted_exit_keeps_boundary_input_until_automatic_tile_clears_it():
    from pokemon_red_completion.gen1_maps import _assemble, _with_automatic_warp_triggers
    header=N(height=2,width=2,connections={})
    rows=[N(at=(3,1),destination_map=254,destination_warp_index=0)]
    passage=_assemble({236:header},{236:rows})[236][0]
    assert passage.kind is PassageKind.SCRIPTED and passage.exit_action=="down"
    node=MapNode(236,2,2,(passage,),tileset=18,warp_locations=((3,1),))
    tiles=((0,0,0,0),)*4
    ordinary=_with_automatic_warp_triggers({236:node},{236:tiles},{18:frozenset({7})})
    assert ordinary[236].passages[0].exit_action=="down"
    automatic=_with_automatic_warp_triggers({236:node},{236:tiles},{18:frozenset({0})})
    assert automatic[236].passages[0].exit_action is None
