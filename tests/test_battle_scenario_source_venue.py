from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.battle_scenario_source_venue import (
    BattleScenarioSourceVenueError,
    battle_scenario_reachable_venues,
)
from pokemon_red_completion.gen1_field_moves import CUT_MOVE_ID, FLY_MOVE_ID
from pokemon_red_completion.gen1_story_routing import EventFlag
from pokemon_red_completion.observation import Badge, MapId, RawGameState


def _raw(map_id: MapId, **changes: object) -> RawGameState:
    raw = RawGameState(
        game_started=True,
        map_id=map_id,
        player_x=3,
        player_y=3,
        party_count=1,
        party_hp=(40,),
        party_moves=((1, 2, 0, 0),),
        battle_state=0,
    )
    return replace(raw, **changes)


def test_route_11_source_can_use_both_existing_vermilion_venues() -> None:
    venues = battle_scenario_reachable_venues(
        _raw(MapId.ROUTE_11, player_x=12, player_y=9),
        last_blackout_map=int(MapId.VERMILION_CITY),
        current_map_tileset=0,
    )

    assert tuple(item.venue_id for item in venues) == ("digletts_cave", "route_11")
    assert next(item for item in venues if item.venue_id == "route_11").relocation_required is False
    assert (
        next(item for item in venues if item.venue_id == "digletts_cave").relocation_required
        is True
    )


def test_cinnabar_center_can_reach_mansion_and_vermilion_venues_with_fly() -> None:
    raw = _raw(
        MapId.CINNABAR_POKECENTER,
        party_moves=((1, 2, FLY_MOVE_ID, 0),),
        badge_bits=int(Badge.THUNDER),
    )

    venues = battle_scenario_reachable_venues(
        raw,
        last_blackout_map=int(MapId.CINNABAR_ISLAND),
        current_map_tileset=6,
    )

    assert tuple(item.venue_id for item in venues) == (
        "digletts_cave",
        "pokemon_mansion_1f",
        "route_11",
    )


def test_cinnabar_pc_counter_does_not_claim_unimplemented_mansion_relocation() -> None:
    raw = _raw(
        MapId.CINNABAR_POKECENTER,
        player_x=13,
        player_y=4,
        party_moves=((1, 2, FLY_MOVE_ID, 0),),
        badge_bits=int(Badge.THUNDER),
    )

    venues = battle_scenario_reachable_venues(
        raw,
        last_blackout_map=int(MapId.CINNABAR_ISLAND),
        current_map_tileset=6,
    )

    assert tuple(item.venue_id for item in venues) == ("digletts_cave", "route_11")


def test_celadon_center_can_reach_both_vermilion_venues_by_ground() -> None:
    event_flags = bytearray(int(EventFlag.LEFT_BILLS_HOUSE_AFTER_HELPING) // 8 + 1)
    byte, bit = divmod(int(EventFlag.LEFT_BILLS_HOUSE_AFTER_HELPING), 8)
    event_flags[byte] |= 1 << bit
    raw = _raw(
        MapId.CELADON_POKECENTER,
        badge_bits=int(Badge.CASCADE),
        event_flags=bytes(event_flags),
        party_moves=((1, CUT_MOVE_ID, 0, 0),),
    )

    venues = battle_scenario_reachable_venues(
        raw,
        last_blackout_map=int(MapId.CELADON_CITY),
        current_map_tileset=6,
    )

    assert tuple(item.venue_id for item in venues) == ("digletts_cave", "route_11")
    assert all(item.relocation_required for item in venues)


def test_direct_mansion_source_does_not_invent_unqualified_travel() -> None:
    venues = battle_scenario_reachable_venues(
        _raw(MapId.POKEMON_MANSION_1F, player_x=5, player_y=27),
        last_blackout_map=int(MapId.CINNABAR_ISLAND),
        current_map_tileset=17,
    )

    assert tuple(item.venue_id for item in venues) == ("pokemon_mansion_1f",)


def test_reachable_venue_adapter_rejects_battle_and_unsupported_boundaries() -> None:
    with pytest.raises(BattleScenarioSourceVenueError, match="non-battle"):
        battle_scenario_reachable_venues(
            _raw(MapId.ROUTE_11, battle_state=1),
            last_blackout_map=int(MapId.VERMILION_CITY),
            current_map_tileset=0,
        )
    with pytest.raises(BattleScenarioSourceVenueError, match="no qualified"):
        battle_scenario_reachable_venues(
            _raw(MapId.PALLET_TOWN, player_x=5, player_y=6),
            last_blackout_map=int(MapId.PALLET_TOWN),
            current_map_tileset=0,
        )
