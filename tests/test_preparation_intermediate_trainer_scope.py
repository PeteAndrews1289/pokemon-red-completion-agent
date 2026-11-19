import ast
from pathlib import Path
from dataclasses import dataclass, replace
from types import SimpleNamespace as N
import pytest
from pokemon_red_completion.local_router import LocalGraph, LocalEdge, LocalRouterError, find_local_path, without_coordinates


@dataclass(frozen=True)
class World:
    local_graphs: dict


def actual_quote(*, current=0, defeated=False):
    source=Path(__file__).resolve().parents[1]/"runtime_helpers/red_whole_player_inventory_20261006.py"
    tree=ast.parse(source.read_text())
    helper=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=="preparation_quote_world")
    preparation=next(n for n in ast.walk(tree)if isinstance(n,ast.FunctionDef)and n.name=="preparation")
    call=next(n.value for n in ast.walk(preparation)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=="quote_world"for t in n.targets))
    graph=LocalGraph({(0,0):(LocalEdge((0,1),"right"),),(0,1):(LocalEdge((0,2),"right"),),(0,2):()})
    original=World({0:graph,1:graph,2:graph})
    namespace=dict(replace=replace,without_coordinates=without_coordinates,
        trainer_headers=lambda rom,maps,**kw:maps,map_object_events=lambda rom,maps:maps,
        static_trainer_sight_zones=lambda headers,objects,events: [] if events==b"defeated"or 1 not in headers else [N(map_id=1,lane=((0,1),))],
        route=N(route_world=original),rom=b"fixture",raw=N(map_id=current,event_flags=b"defeated"if defeated else b"unbeaten"),
        map_id_for_wild_source=lambda source:2,sources=("venue",))
    exec(compile(ast.Module(body=[helper],type_ignores=[]),str(source),"exec"),namespace)
    quote=eval(compile(ast.Expression(call),str(source),"eval"),namespace)
    return original,quote


def test_actual_preparation_quote_rejects_unhandled_trainer_on_intermediate_map():
    original,quote=actual_quote()
    assert find_local_path(original.local_graphs[1],(0,0),(0,2)).coordinates[-1]==(0,2)
    with pytest.raises(LocalRouterError):find_local_path(quote.local_graphs[1],(0,0),(0,2))
    assert quote.local_graphs[0]is original.local_graphs[0]
    assert quote.local_graphs[2]is original.local_graphs[2]
    assert (0,1)in original.local_graphs[1].edges


def test_defeated_trainers_do_not_remove_legal_transit():
    original,quote=actual_quote(defeated=True)
    assert quote.local_graphs[1]is original.local_graphs[1]
    assert find_local_path(quote.local_graphs[1],(0,0),(0,2)).coordinates[-1]==(0,2)


def test_current_map_keeps_live_occupancy_and_sight_instead_of_static_prediction():
    original,quote=actual_quote(current=1)
    assert quote.local_graphs[1]is original.local_graphs[1]
