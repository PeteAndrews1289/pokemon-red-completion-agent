"""Title-adapter facts for safe Red battle-scenario source boundaries.

The learner and experiment layers reason about semantic venue identifiers.  Red
save states expose cartridge map numbers.  This module is the narrow join
between those two facts, shared by the materializer and the action-free source
inventory so they cannot silently classify the same bytes differently.
"""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.observation import MapId, RawGameState


class BattleScenarioSourceVenueError(ValueError):
    """Raised when a state is not a supported, safe materialization source."""


@dataclass(frozen=True, slots=True)
class BattleScenarioSourceVenue:
    """One loaded Red map bound to a measured semantic encounter venue."""

    source_location: str
    venue_id: str
    source_map: int
    encounter_map: int
    relocation_required: bool


_SOURCE_VENUES = {
    int(MapId.ROUTE_11): BattleScenarioSourceVenue(
        source_location="route_11",
        venue_id="route_11",
        source_map=int(MapId.ROUTE_11),
        encounter_map=int(MapId.ROUTE_11),
        relocation_required=False,
    ),
    int(MapId.DIGLETTS_CAVE): BattleScenarioSourceVenue(
        source_location="digletts_cave",
        venue_id="digletts_cave",
        source_map=int(MapId.DIGLETTS_CAVE),
        encounter_map=int(MapId.DIGLETTS_CAVE),
        relocation_required=False,
    ),
    int(MapId.POKEMON_MANSION_1F): BattleScenarioSourceVenue(
        source_location="mansion",
        venue_id="pokemon_mansion_1f",
        source_map=int(MapId.POKEMON_MANSION_1F),
        encounter_map=int(MapId.POKEMON_MANSION_1F),
        relocation_required=False,
    ),
    int(MapId.CINNABAR_POKECENTER): BattleScenarioSourceVenue(
        source_location="cinnabar_center",
        venue_id="pokemon_mansion_1f",
        source_map=int(MapId.CINNABAR_POKECENTER),
        encounter_map=int(MapId.POKEMON_MANSION_1F),
        relocation_required=True,
    ),
}


def battle_scenario_source_venue(
    raw: RawGameState,
) -> BattleScenarioSourceVenue:
    """Derive the measured venue from one loaded state without advancing it."""

    if not isinstance(raw, RawGameState):
        raise TypeError("battle source venue requires a raw Red state")
    if raw.battle_state != 0:
        raise BattleScenarioSourceVenueError("battle source is not at a safe non-battle boundary")
    map_id = raw.map_id
    if isinstance(map_id, bool) or not isinstance(map_id, int):
        raise BattleScenarioSourceVenueError("battle source is not at a measured source boundary")
    try:
        return _SOURCE_VENUES[map_id]
    except KeyError:
        raise BattleScenarioSourceVenueError(
            "battle source is not at a measured source boundary"
        ) from None


__all__ = [
    "BattleScenarioSourceVenue",
    "BattleScenarioSourceVenueError",
    "battle_scenario_source_venue",
]
