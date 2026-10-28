"""Preparation quotes retain the ground executor's real Surf permission seam."""
from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.gen1_traversal import (
    CUT_CAPABILITY, SURF_CAPABILITY, STRENGTH_CAPABILITY, cut_capabilities,
)
from pokemon_red_completion.observation import Badge, MapId, RawGameState
from pokemon_red_completion.red_training_ground_route import ground_route_capability_projector


def raw():
    return RawGameState(
        True, MapId.INDIGO_PLATEAU_LOBBY, 7, 7, 1, 0,
        badge_bits=int(Badge.CASCADE | Badge.SOUL | Badge.RAINBOW),
        party_hp=(50,), party_moves=((15, 57, 70, 0),),
    )


@pytest.mark.parametrize("route", [N(), N(allow_surf=False), N(allow_surf=1)])
def test_legacy_land_quote_keeps_the_original_projector_and_does_not_read_memory(route):
    memory = N(read_u8=lambda _: pytest.fail("land quote read Surf permission"))
    projector = ground_route_capability_projector(route, memory)
    assert projector is cut_capabilities
    assert projector(raw()) == frozenset({CUT_CAPABILITY})


def test_explicit_route_can_quote_the_water_edge_its_executor_can_use():
    projector = ground_route_capability_projector(N(allow_surf=True), N(read_u8=lambda _: 0))
    assert projector(raw()) == frozenset({CUT_CAPABILITY, SURF_CAPABILITY})
    assert STRENGTH_CAPABILITY not in projector(raw())


@pytest.mark.parametrize("change", [
    {"party_hp": (0,)},
    {"badge_bits": int(Badge.CASCADE)},
    {"party_moves": ((15, 0, 0, 0),)},
    {"party_count": 2},
    {"party_hp": None},
    {"party_moves": None},
])
def test_surf_quote_does_not_invent_a_living_complete_badged_holder(change):
    projector = ground_route_capability_projector(N(allow_surf=True), N(read_u8=lambda _: 0))
    assert SURF_CAPABILITY not in projector(replace(raw(), **change))


def test_native_forced_bike_permission_still_closes_water_edges():
    projector = ground_route_capability_projector(N(allow_surf=True), N(read_u8=lambda _: 1 << 5))
    assert projector(raw()) == frozenset({CUT_CAPABILITY})


def test_unsettled_seafoam_story_permission_is_still_required():
    projector = ground_route_capability_projector(N(allow_surf=True), N(read_u8=lambda _: 0))
    blocked = replace(raw(), map_id=MapId.SEAFOAM_ISLANDS_B4F, event_flags=bytes(320))
    assert SURF_CAPABILITY not in projector(blocked)
