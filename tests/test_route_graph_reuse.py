from dataclasses import replace

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.local_router import LocalEdge, LocalGraph, find_local_paths
from pokemon_red_completion import route_plan as s


def graph():
    return LocalGraph({(0,0):(LocalEdge((0,1),'right'),LocalEdge((1,0),'down')),
                       (0,1):(LocalEdge((1,1),'down'),),
                       (1,0):(LocalEdge((1,1),'right'),),(1,1):()})


def test_equal_reconstructed_graphs_share_search_and_match_stateless_tie_order():
    a,b=graph(),graph();goal={((1,1),None)}
    with s.frozen_local_route_inventory()as c:
        _,first=c.paths(a,(),(0,0),goal,frozenset(),None)
        _,second=c.paths(b,(),(0,0),goal,frozenset(),None)
        assert first==second==find_local_paths(b,(0,0),goal)
        assert c.hits==1 and c.canonical_graph(b)is a
    assert not c.equivalent_graphs and not c.canonical_by_identity


@pytest.mark.parametrize('which',[0,1])
def test_both_canonical_and_equal_original_mutations_are_rejected(which):
    graphs=[graph(),graph()]
    with pytest.raises(s.RoutePlanningError,match='changed a local graph'):
        with s.frozen_local_route_inventory()as c:
            assert c.canonical_graph(graphs[0])is c.canonical_graph(graphs[1])
            graphs[which].edges[(0,0)]=()


@pytest.mark.parametrize('field,value',[
    ('action','left'),('cost',2),('requirements',frozenset({'cut'})),
    ('required_mode','water'),('result_mode','land'),
    ('transient',(0,2)),('action_kind',MacroActionKind.INTERACT),
])
def test_all_edge_semantics_remain_in_graph_equivalence(field,value):
    a,b=graph(),graph();b.edges[(0,0)]=(replace(b.edges[(0,0)][0],**{field:value}),*b.edges[(0,0)][1:])
    with s.frozen_local_route_inventory()as c:
        assert c.canonical_graph(a)is a
        assert c.canonical_graph(b)is b


def test_outgoing_edge_order_and_frontier_ties_are_not_collapsed():
    a,b=graph(),graph();b.edges[(0,0)]=tuple(reversed(b.edges[(0,0)]));goal={((1,1),None)}
    with s.frozen_local_route_inventory()as c:
        assert c.canonical_graph(a)is a and c.canonical_graph(b)is b
        _,pa=c.paths(a,(),(0,0),goal,frozenset(),None)
        _,pb=c.paths(b,(),(0,0),goal,frozenset(),None)
        assert pa!=pb and pb==find_local_paths(b,(0,0),goal)


def test_subclass_and_dynamic_mapping_keep_identity_and_new_scope_has_no_old_answer():
    class DynamicGraph(LocalGraph):pass
    class DynamicEdges(dict):pass
    a=graph();b=DynamicGraph(dict(a.edges));d=LocalGraph(DynamicEdges(a.edges))
    with s.frozen_local_route_inventory()as c:
        assert c.canonical_graph(a)is a
        assert c.canonical_graph(b)is b and c.canonical_graph(d)is d
    a.edges[(0,0)]=()
    with s.frozen_local_route_inventory()as new:
        assert new.canonical_graph(a)is a and len(new.equivalent_graphs)==1


def test_full_retention_budget_falls_back_without_new_identity_aliases():
    a=graph()
    with s.frozen_local_route_inventory()as c:
        c.graphs={i:(LocalGraph({}),{})for i in range(2048)}
        assert c.canonical_graph(a)is a
        assert not c.equivalent_graphs and not c.canonical_by_identity
