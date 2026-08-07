import pytest

from pokemon_red_completion.global_router import (
    BASIC_KANTO_GRAPH,
    GlobalRouterError,
    find_macro_route,
)
from pokemon_red_completion.observation import MapId


def test_find_macro_route_direct():
    route = find_macro_route(BASIC_KANTO_GRAPH, MapId.PALLET_TOWN, MapId.ROUTE_1)
    assert route == (MapId.PALLET_TOWN, MapId.ROUTE_1)


def test_find_macro_route_multi_hop():
    route = find_macro_route(BASIC_KANTO_GRAPH, MapId.PALLET_TOWN, MapId.VIRIDIAN_POKECENTER)
    assert route == (
        MapId.PALLET_TOWN,
        MapId.ROUTE_1,
        MapId.VIRIDIAN_CITY,
        MapId.VIRIDIAN_POKECENTER,
    )


def test_find_macro_route_no_path():
    with pytest.raises(GlobalRouterError):
        find_macro_route(BASIC_KANTO_GRAPH, MapId.PALLET_TOWN, MapId.SAFFRON_CITY)
