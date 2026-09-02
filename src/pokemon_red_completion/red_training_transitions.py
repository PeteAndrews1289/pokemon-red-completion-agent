"""Exact Red boundaries from which a bounded training venue is reachable.

The party learner consumes only a title-neutral transition verdict.  This
module keeps the Red-specific evidence behind that adapter and shares the same
finite set with the executor, so a prospective menu cannot claim travel that
the live route does not implement.
"""

from __future__ import annotations

from pokemon_red_completion.gen1_field_moves import DIG_MOVE_ID, FLY_MOVE_ID
from pokemon_red_completion.gen1_story_routing import (
    CERULEAN_ROBBED_HOUSE_OPEN,
    SAFFRON_GUARDS_OPEN,
    gen1_story_capabilities,
)
from pokemon_red_completion.gen1_traversal import CUT_CAPABILITY, cut_capabilities
from pokemon_red_completion.observation import Badge, MapId, RawGameState

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


def _living_move_holder(raw: RawGameState, move_id: int) -> bool:
    hp = raw.party_hp or ()
    moves = raw.party_moves or ()
    return (
        raw.party_count is not None
        and raw.party_count == len(hp) == len(moves)
        and any(
            current_hp > 0 and move_id in known
            for current_hp, known in zip(hp, moves, strict=True)
        )
    )


def red_training_fly_available(raw: RawGameState) -> bool:
    """Whether the live party can legally use Fly outside battle."""

    return bool(int(raw.badge_bits or 0) & int(Badge.THUNDER)) and _living_move_holder(
        raw,
        FLY_MOVE_ID,
    )


def red_training_ground_transition_available(raw: RawGameState) -> bool:
    """Whether a cartridge-composed ground route supports this exact boundary.

    These are the authenticated no-Fly starts recovered by the scale
    campaign.  Saffron can leave through an opened guard house.  Lavender and
    Celadon use cartridge-composed land routes after Bill's passage opens and
    require one explicit Cut; none relies on a handwritten arrow sequence.
    """

    if (raw.player_x, raw.player_y) != (3, 3):
        return False
    story = gen1_story_capabilities(raw)
    if raw.map_id == MapId.SAFFRON_POKECENTER:
        return SAFFRON_GUARDS_OPEN in story
    if raw.map_id in {MapId.LAVENDER_POKECENTER, MapId.CELADON_POKECENTER}:
        return (
            CERULEAN_ROBBED_HOUSE_OPEN in story
            and CUT_CAPABILITY in cut_capabilities(raw)
        )
    return False


def red_vermilion_training_transition_available(
    raw: RawGameState,
    last_blackout_map: int,
    current_map_tileset: int,
) -> bool:
    """Whether the bounded Red executor can reach the Vermilion venues.

    A healing anchor and field-move legality remain separate facts.  Air travel
    requires the Thunder Badge and a living Fly holder.  The two authenticated
    no-Fly Center boundaries are admitted only when their cartridge-composed
    ground routes' observed story and Cut predicates are satisfied.
    """

    if raw.battle_state or raw.map_id is None:
        return False
    position = (raw.player_x, raw.player_y)
    if raw.map_id == MapId.ROUTE_11:
        return True
    if raw.map_id == MapId.VERMILION_POKECENTER:
        return position in {(3, 3), (3, 7)}
    if raw.map_id == MapId.CINNABAR_POKECENTER:
        return position in {(3, 3), (13, 4)} and red_training_fly_available(raw)
    if raw.map_id in RED_TRAINING_FLY_CENTER_MAPS:
        return position == (3, 3) and (
            red_training_fly_available(raw)
            or red_training_ground_transition_available(raw)
        )
    if raw.map_id in RED_TRAINING_FLY_OUTDOOR_MAPS:
        if raw.map_id == MapId.VERMILION_CITY:
            return position == (11, 4)
        return red_training_fly_available(raw)
    if raw.map_id == MapId.CINNABAR_MART:
        return (
            position == RED_CINNABAR_MART_TRAINING_BOUNDARY
            and red_training_fly_available(raw)
        )
    if raw.map_id == MapId.INDIGO_PLATEAU_LOBBY:
        return (
            position == RED_INDIGO_LOBBY_TRAINING_BOUNDARY
            and red_training_fly_available(raw)
        )
    if (
        current_map_tileset not in RED_ESCAPE_WARP_TILESETS
        or not _living_move_holder(raw, DIG_MOVE_ID)
    ):
        return False
    if last_blackout_map == MapId.VERMILION_CITY:
        return True
    return last_blackout_map in {
        MapId.CELADON_CITY,
        MapId.CINNABAR_ISLAND,
        MapId.SAFFRON_CITY,
    } and red_training_fly_available(raw)


__all__ = [
    "RED_CINNABAR_MART_TRAINING_BOUNDARY",
    "RED_ESCAPE_WARP_TILESETS",
    "RED_INDIGO_LOBBY_TRAINING_BOUNDARY",
    "RED_TRAINING_FLY_CENTER_MAPS",
    "RED_TRAINING_FLY_OUTDOOR_MAPS",
    "red_training_fly_available",
    "red_training_ground_transition_available",
    "red_vermilion_training_transition_available",
]
