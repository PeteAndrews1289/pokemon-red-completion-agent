from dataclasses import replace
import pytest
from pokemon_red_completion import route_plan as routes
from pokemon_red_completion.global_router import MacroGraph,MacroEdge
from pokemon_red_completion.local_router import LocalGraph,LocalEdge

def world():
    graph=MacroGraph({1:(MacroEdge(2,kind='warp',at=(0,1),arrival_at=(0,0)),),2:(MacroEdge(3,kind='warp',at=(0,1),arrival_at=(0,0)),),3:()})
    local={m:LocalGraph({(0,0):(LocalEdge((0,1),action='right'),),(0,1):(LocalEdge((0,2),action='right'),),(0,2):()}) for m in (1,2,3)}
    return graph,local

def test_blocked_sibling_searches_preserve_routes_and_reuse_prefixes(monkeypatch):
    graph,local=world();blocked={m:frozenset({(0,2)}) for m in local}
    expected=[routes.plan_route(graph,local,1,(0,0),target,blocked=blocked) for target in (2,3)]
    original=routes.find_local_paths;calls=[]
    def measured(*args,**kwargs):calls.append(1);return original(*args,**kwargs)
    monkeypatch.setattr(routes,'find_local_paths',measured)
    with routes.frozen_local_route_inventory() as cache:
        assert [routes.plan_route(graph,local,1,(0,0),target,blocked=blocked) for target in (2,3)]==expected
        spent=len(calls)
        assert routes.plan_route(graph,local,1,(0,0),3,blocked=blocked)==expected[1]
        assert len(calls)==spent and cache.hits>0 and cache.projections
    assert cache.queries==cache.projections==cache.graphs=={}
    routes.plan_route(graph,local,1,(0,0),3,blocked=blocked)
    assert len(calls)>spent

def test_changed_blockers_do_not_reuse_an_open_route():
    graph,local=world()
    with routes.frozen_local_route_inventory() as cache:
        assert routes.plan_route(graph,local,1,(0,0),3,blocked={1:{(0,2)}}).terminal_map==3
        with pytest.raises(routes.RoutePlanningError):routes.plan_route(graph,local,1,(0,0),3,blocked={1:{(0,1)}})
        assert routes.plan_route(graph,local,1,(0,0),3,blocked={1:{(0,2)}}).terminal_map==3

def test_original_graph_edit_invalidates_cached_projection_even_if_reverted():
    graph,local=world();original=dict(local[1].edges)
    with pytest.raises(routes.RoutePlanningError,match='changed a local graph'):
        with routes.frozen_local_route_inventory() as cache:
            routes.plan_route(graph,local,1,(0,0),3,blocked={1:{(0,2)}})
            local[1].edges[(0,0)]=()
            with pytest.raises(routes.RoutePlanningError,match='changed a local graph'):
                routes.plan_route(graph,local,1,(0,0),3,blocked={1:{(0,2)}})
            local[1].edges.clear();local[1].edges.update(original)
    assert cache.projections==cache.graphs=={} and routes._FROZEN_LOCAL_ROUTE_CACHE.get() is None

def test_projected_graph_edit_cannot_survive_a_caught_error():
    _,local=world()
    with pytest.raises(routes.RoutePlanningError,match='changed a local graph'):
        with routes.frozen_local_route_inventory() as cache:
            projected=cache.project(local[1],{(0,2)})
            projected.edges[(0,0)]=()
            with pytest.raises(routes.RoutePlanningError,match='changed a local graph'):
                cache.project(local[1],{(0,2)})
    assert cache.projections=={}

def test_capabilities_and_modes_stay_distinct_with_a_shared_projection():
    graph,local=world();first=local[1]
    local[1]=LocalGraph({**first.edges,(0,0):(replace(first.edges[(0,0)][0],requirements=frozenset({'cut'}),required_mode='land'),)})
    with routes.frozen_local_route_inventory():
        with pytest.raises(routes.RoutePlanningError):routes.plan_route(graph,local,1,(0,0),3,blocked={1:{(0,2)}})
        assert routes.plan_route(graph,local,1,(0,0),3,blocked={1:{(0,2)}},capabilities=frozenset({'cut'}),start_mode='land').terminal_map==3
        with pytest.raises(routes.RoutePlanningError):routes.plan_route(graph,local,1,(0,0),3,blocked={1:{(0,2)}},capabilities=frozenset({'cut'}),start_mode='water')

def test_graph_limit_falls_back_without_retaining_projections():
    graph,local=world();expected=routes.plan_route(graph,local,1,(0,0),3,blocked={1:{(0,2)}})
    with routes.frozen_local_route_inventory() as cache:
        cache.graphs={i:(LocalGraph({}),{}) for i in range(2048)}
        assert routes.plan_route(graph,local,1,(0,0),3,blocked={1:{(0,2)}})==expected
        assert len(cache.graphs)==2048 and not cache.projections and not cache.queries

def test_observer_exception_discards_all_projection_state():
    _,local=world()
    with pytest.raises(RuntimeError,match='observer failed'):
        with routes.frozen_local_route_inventory() as cache:
            cache.project(local[1],{(0,2)})
            raise RuntimeError('observer failed')
    assert cache.projections==cache.graphs==cache.queries=={}

def test_equal_but_different_observation_graphs_are_not_aliased():
    _,local=world();first=local[1];second=LocalGraph(dict(first.edges))
    with routes.frozen_local_route_inventory() as cache:
        assert cache.project(first,{(0,2)}) is not cache.project(second,{(0,2)})
