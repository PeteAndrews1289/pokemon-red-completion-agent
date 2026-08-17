"""Exact Red boundaries from which a bounded training venue is reachable.

The party learner consumes only a title-neutral transition verdict.  This
module keeps the Red-specific evidence behind that adapter and shares the same
finite set with the executor, so a prospective menu cannot claim travel that
the live route does not implement.
"""

from __future__ import annotations

from pokemon_red_completion.observation import MapId, RawGameState

# Red's field-Dig implementation accepts exactly these cartridge tilesets.
RED_ESCAPE_WARP_TILESETS = frozenset({3, 15, 16, 17, 22})

# Every listed Center uses the common nurse-facing (3, 3) boundary and the
# common five-step exit.  The executor validates the exact coordinate before
# touching the controller.
RED_TRAINING_FLY_CENTER_MAPS = frozenset(
    {
        MapId.VIRIDIAN_POKECENTER,
        MapId.PEWTER_POKECENTER,
        MapId.CERULEAN_POKECENTER,
        MapId.VERMILION_POKECENTER,
        MapId.LAVENDER_POKECENTER,
        MapId.FUCHSIA_POKECENTER,
        MapId.CELADON_POKECENTER,
        MapId.SAFFRON_POKECENTER,
        MapId.CINNABAR_POKECENTER,
    }
)

RED_TRAINING_FLY_OUTDOOR_MAPS = frozenset(
    {
        MapId.VIRIDIAN_CITY,
        MapId.PEWTER_CITY,
        MapId.CERULEAN_CITY,
        MapId.LAVENDER_TOWN,
        MapId.VERMILION_CITY,
        MapId.CELADON_CITY,
        MapId.FUCHSIA_CITY,
        MapId.CINNABAR_ISLAND,
        MapId.SAFFRON_CITY,
    }
)

RED_CINNABAR_MART_TRAINING_BOUNDARY = (2, 5)
RED_INDIGO_LOBBY_TRAINING_BOUNDARY = (2, 5)


def red_vermilion_training_transition_available(
    raw: RawGameState,
    last_blackout_map: int,
    current_map_tileset: int,
) -> bool:
    """Whether the bounded Red executor can reach the Vermilion venues.

    A healing anchor and field-Dig legality remain separate facts.  The
    explicit Fly boundaries are late-game, authenticated contexts whose party
    already carries the field-move users required by the executor; the live
    route still discovers those users from memory and fails closed if either
    move is absent.
    """

    if raw.battle_state or raw.map_id is None:
        return False
    position = (raw.player_x, raw.player_y)
    if raw.map_id == MapId.ROUTE_11:
        return True
    if raw.map_id == MapId.VERMILION_POKECENTER:
        return position in {(3, 3), (3, 7)}
    if raw.map_id == MapId.CINNABAR_POKECENTER:
        return position in {(3, 3), (13, 4)}
    if raw.map_id in RED_TRAINING_FLY_CENTER_MAPS:
        return position == (3, 3)
    if raw.map_id in RED_TRAINING_FLY_OUTDOOR_MAPS:
        return raw.map_id != MapId.VERMILION_CITY or position == (11, 4)
    if raw.map_id == MapId.CINNABAR_MART:
        return position == RED_CINNABAR_MART_TRAINING_BOUNDARY
    if raw.map_id == MapId.INDIGO_PLATEAU_LOBBY:
        return position == RED_INDIGO_LOBBY_TRAINING_BOUNDARY
    return current_map_tileset in RED_ESCAPE_WARP_TILESETS and last_blackout_map in {
        MapId.CINNABAR_ISLAND,
        MapId.SAFFRON_CITY,
        MapId.VERMILION_CITY,
    }


__all__ = [
    "RED_CINNABAR_MART_TRAINING_BOUNDARY",
    "RED_ESCAPE_WARP_TILESETS",
    "RED_INDIGO_LOBBY_TRAINING_BOUNDARY",
    "RED_TRAINING_FLY_CENTER_MAPS",
    "RED_TRAINING_FLY_OUTDOOR_MAPS",
    "red_vermilion_training_transition_available",
]
