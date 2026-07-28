from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, IntFlag, StrEnum
from typing import Protocol

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.referee import CHAMPION_DEFEATED_FACT
from pokemon_red_completion.route import HALL_OF_FAME_FACT


class ReadOnlyMemory(Protocol):
    """The deliberately non-mutating memory surface available to the adapter."""

    def read_u8(self, address: int) -> int: ...


class RamAddress(IntEnum):
    """Verified symbols for the supported US revision-zero ROM.

    Symbols originate from pret/pokered commit
    ``1e96034092686d006e863cace09e87273051a3d8`` and are valid only after the
    repository's exact ROM fingerprint gate passes.
    """

    JOY_IGNORE = 0xCD6B
    IS_IN_BATTLE = 0xD057
    PARTY_COUNT = 0xD163
    PARTY_SPECIES = 0xD164
    NUM_BAG_ITEMS = 0xD31D
    BAG_ITEMS = 0xD31E
    OBTAINED_BADGES = 0xD356
    CURRENT_MAP = 0xD35E
    PLAYER_Y = 0xD361
    PLAYER_X = 0xD362
    OAKS_LAB_SCRIPT = 0xD5F0
    PALLET_TOWN_SCRIPT = 0xD5F1
    REDS_HOUSE_2F_SCRIPT = 0xD60C
    STATUS_FLAGS_6 = 0xD732
    EVENT_FLAGS = 0xD747


class MapId(IntEnum):
    PALLET_TOWN = 0x00
    VIRIDIAN_CITY = 0x01
    PEWTER_CITY = 0x02
    CERULEAN_CITY = 0x03
    LAVENDER_TOWN = 0x04
    VERMILION_CITY = 0x05
    CELADON_CITY = 0x06
    FUCHSIA_CITY = 0x07
    CINNABAR_ISLAND = 0x08
    INDIGO_PLATEAU = 0x09
    SAFFRON_CITY = 0x0A
    REDS_HOUSE_1F = 0x25
    REDS_HOUSE_2F = 0x26
    OAKS_LAB = 0x28
    HALL_OF_FAME = 0x76
    CHAMPIONS_ROOM = 0x78
    INDIGO_PLATEAU_LOBBY = 0xAE


class EventFlag(IntEnum):
    FOLLOWED_OAK_INTO_LAB = 0x000
    FOLLOWED_OAK_INTO_LAB_2 = 0x020
    OAK_ASKED_TO_CHOOSE_MON = 0x021
    GOT_STARTER = 0x022
    BATTLED_RIVAL_IN_OAKS_LAB = 0x023
    GOT_POKEDEX = 0x025
    OAK_APPEARED_IN_PALLET = 0x027
    OAK_GOT_PARCEL = 0x038
    BEAT_VIRIDIAN_GYM_GIOVANNI = 0x051
    BEAT_BROCK = 0x077
    BEAT_MISTY = 0x0BF
    RESCUED_MR_FUJI = 0x117
    GOT_POKE_FLUTE = 0x128
    BEAT_LT_SURGE = 0x167
    BEAT_ERIKA = 0x1A9
    GOT_HM04 = 0x238
    BEAT_KOGA = 0x259
    BEAT_BLAINE = 0x299
    BEAT_SABRINA = 0x361
    GOT_SS_TICKET = 0x55C
    GOT_HM01 = 0x5E0
    BEAT_ROCKET_HIDEOUT_GIOVANNI = 0x6A7
    BEAT_SILPH_CO_GIOVANNI = 0x78F
    GOT_HM03 = 0x880
    BEAT_LORELEI = 0x8E1
    BEAT_BRUNO = 0x8E9
    BEAT_AGATHA = 0x8F1
    BEAT_LANCE = 0x8FE
    BEAT_CHAMPION_RIVAL = 0x901


class ItemId(IntEnum):
    SECRET_KEY = 0x2B
    SS_TICKET = 0x3F
    SILPH_SCOPE = 0x48
    POKE_FLUTE = 0x49
    HM01_CUT = 0xC4
    HM03_SURF = 0xC6
    HM04_STRENGTH = 0xC7


class Badge(IntFlag):
    BOULDER = 1 << 0
    CASCADE = 1 << 1
    THUNDER = 1 << 2
    RAINBOW = 1 << 3
    SOUL = 1 << 4
    MARSH = 1 << 5
    VOLCANO = 1 << 6
    EARTH = 1 << 7


GAME_TIMER_COUNTING_MASK = 0x01
REDS_HOUSE_2F_NOOP_SCRIPT = 1
OAKS_LAB_SELECTION_READY_SCRIPT = 6
OAKS_LAB_STARTER_OBTAINED_SCRIPT = 10
JOY_IGNORE_CONFIRM_MASK = 0x01
JOY_IGNORE_CANCEL_MASK = 0x02
JOY_IGNORE_MOVEMENT_MASK = 0xF0
SQUIRTLE_SPECIES_ID = 0xB1
PARTY_LIMIT = 6
MAX_BAG_ITEMS = 20
EVENT_FLAGS_END = 0xD886
EVENT_FLAG_BYTES = EVENT_FLAGS_END - int(RamAddress.EVENT_FLAGS)


@dataclass(frozen=True, slots=True)
class RawGameState:
    """Revision-specific state read from a single emulator observation."""

    game_started: bool
    map_id: int | None
    player_x: int | None
    player_y: int | None
    party_count: int | None
    battle_state: int | None
    badge_bits: int | None = None
    bag_item_ids: tuple[int, ...] | None = None
    event_flags: bytes | None = None
    party_species_ids: tuple[int, ...] | None = None


@dataclass(frozen=True, slots=True)
class BedroomInputState:
    joy_ignore: int
    map_script: int

    @property
    def ready(self) -> bool:
        return self.joy_ignore == 0 and self.map_script == REDS_HOUSE_2F_NOOP_SCRIPT


class OpeningPhase(StrEnum):
    UNKNOWN = "unknown"
    BEDROOM_READY = "bedroom_ready"
    DOWNSTAIRS = "downstairs"
    PALLET_FREE = "pallet_free"
    OAK_ESCORT = "oak_escort"
    STARTER_SELECTION_READY = "starter_selection_ready"
    STARTER_OBTAINED = "starter_obtained"


@dataclass(frozen=True, slots=True)
class OpeningControlState:
    phase: OpeningPhase
    confirm_allowed: bool
    cancel_allowed: bool
    movement_allowed: bool
    followed_oak_into_lab: bool
    asked_to_choose: bool
    starter_obtained: bool
    first_party_species: int | None

    @property
    def all_controls_allowed(self) -> bool:
        return self.confirm_allowed and self.cancel_allowed and self.movement_allowed


class PokemonRedStateReader:
    def __init__(self, memory: ReadOnlyMemory) -> None:
        self._memory = memory

    def read(self) -> RawGameState:
        status = self._memory.read_u8(RamAddress.STATUS_FLAGS_6)
        game_started = bool(status & GAME_TIMER_COUNTING_MASK)
        if not game_started:
            return RawGameState(False, None, None, None, None, None)

        bag_count = min(self._memory.read_u8(RamAddress.NUM_BAG_ITEMS), MAX_BAG_ITEMS)
        bag_items = tuple(
            self._memory.read_u8(int(RamAddress.BAG_ITEMS) + index * 2)
            for index in range(bag_count)
        )
        party_count = min(self._memory.read_u8(RamAddress.PARTY_COUNT), PARTY_LIMIT)
        party_species = tuple(
            self._memory.read_u8(int(RamAddress.PARTY_SPECIES) + index)
            for index in range(party_count)
        )
        events = bytes(
            self._memory.read_u8(int(RamAddress.EVENT_FLAGS) + index)
            for index in range(EVENT_FLAG_BYTES)
        )
        return RawGameState(
            game_started=True,
            map_id=self._memory.read_u8(RamAddress.CURRENT_MAP),
            player_x=self._memory.read_u8(RamAddress.PLAYER_X),
            player_y=self._memory.read_u8(RamAddress.PLAYER_Y),
            party_count=party_count,
            battle_state=self._memory.read_u8(RamAddress.IS_IN_BATTLE),
            badge_bits=self._memory.read_u8(RamAddress.OBTAINED_BADGES),
            bag_item_ids=bag_items,
            event_flags=events,
            party_species_ids=party_species,
        )

    def read_bedroom_input_state(self) -> BedroomInputState:
        """Read the two revision-specific input-readiness symbols for Red's bedroom."""
        return BedroomInputState(
            joy_ignore=self._memory.read_u8(RamAddress.JOY_IGNORE),
            map_script=self._memory.read_u8(RamAddress.REDS_HOUSE_2F_SCRIPT),
        )

    def read_opening_control_state(self, raw: RawGameState) -> OpeningControlState:
        """Translate opening scripts and event bits into a bounded semantic phase."""
        joy_ignore = self._memory.read_u8(RamAddress.JOY_IGNORE)
        lab_script = self._memory.read_u8(RamAddress.OAKS_LAB_SCRIPT)
        pallet_script = self._memory.read_u8(RamAddress.PALLET_TOWN_SCRIPT)
        confirm_allowed = not bool(joy_ignore & JOY_IGNORE_CONFIRM_MASK)
        cancel_allowed = not bool(joy_ignore & JOY_IGNORE_CANCEL_MASK)
        movement_allowed = not bool(joy_ignore & JOY_IGNORE_MOVEMENT_MASK)
        followed = _event(raw.event_flags, EventFlag.FOLLOWED_OAK_INTO_LAB)
        followed_2 = _event(raw.event_flags, EventFlag.FOLLOWED_OAK_INTO_LAB_2)
        asked = _event(raw.event_flags, EventFlag.OAK_ASKED_TO_CHOOSE_MON)
        starter = _event(raw.event_flags, EventFlag.GOT_STARTER)
        first_species = raw.party_species_ids[0] if raw.party_species_ids else None

        phase = OpeningPhase.UNKNOWN
        if (
            raw.map_id == MapId.OAKS_LAB
            and raw.player_x == 7
            and raw.player_y == 4
            and raw.party_count == 1
            and starter
            and lab_script == OAKS_LAB_STARTER_OBTAINED_SCRIPT
            and joy_ignore == 0
        ):
            phase = OpeningPhase.STARTER_OBTAINED
        elif (
            raw.map_id == MapId.OAKS_LAB
            and raw.player_x == 5
            and raw.player_y == 3
            and raw.party_count == 0
            and followed
            and followed_2
            and asked
            and not starter
            and lab_script == OAKS_LAB_SELECTION_READY_SCRIPT
            and joy_ignore == 0
        ):
            phase = OpeningPhase.STARTER_SELECTION_READY
        elif _event(raw.event_flags, EventFlag.OAK_APPEARED_IN_PALLET):
            phase = OpeningPhase.OAK_ESCORT
        elif raw.map_id == MapId.PALLET_TOWN and pallet_script == 0 and movement_allowed:
            phase = OpeningPhase.PALLET_FREE
        elif raw.map_id == MapId.REDS_HOUSE_1F and movement_allowed:
            phase = OpeningPhase.DOWNSTAIRS
        elif (
            raw.map_id == MapId.REDS_HOUSE_2F
            and movement_allowed
            and self._memory.read_u8(RamAddress.REDS_HOUSE_2F_SCRIPT) == REDS_HOUSE_2F_NOOP_SCRIPT
        ):
            phase = OpeningPhase.BEDROOM_READY

        return OpeningControlState(
            phase=phase,
            confirm_allowed=confirm_allowed,
            cancel_allowed=cancel_allowed,
            movement_allowed=movement_allowed,
            followed_oak_into_lab=followed and followed_2,
            asked_to_choose=asked,
            starter_obtained=starter,
            first_party_species=first_species,
        )


def event_flag_is_set(event_flags: bytes | None, bit_index: int) -> bool:
    if bit_index < 0:
        raise ValueError("event bit index cannot be negative")
    if event_flags is None:
        return False
    byte_index, bit = divmod(bit_index, 8)
    return byte_index < len(event_flags) and bool(event_flags[byte_index] & (1 << bit))


class SemanticStateError(ValueError):
    """Raised when a run cannot establish a trustworthy semantic-state origin."""


class SemanticStateTracker:
    """Latch only verified semantic milestones observed within one clean run."""

    def __init__(self, initial_raw_state: RawGameState) -> None:
        if initial_raw_state.game_started:
            raise SemanticStateError(
                "A clean run must begin before the game timer starts; refusing adjacent state."
            )
        self._latched_facts: set[str] = {"system:clean_power_on"}

    @property
    def latched_facts(self) -> frozenset[str]:
        return frozenset(self._latched_facts)

    def observe(self, raw: RawGameState) -> GameState:
        observed = semantic_facts(raw)
        self._latched_facts.update(observed)
        return GameState(
            mode=game_mode(raw),
            facts=frozenset(self._latched_facts),
            location=location_label(raw.map_id),
        )


def game_mode(raw: RawGameState) -> GameMode:
    if not raw.game_started:
        return GameMode.BOOTING
    if raw.map_id == MapId.HALL_OF_FAME:
        return GameMode.HALL_OF_FAME
    if raw.battle_state in {1, 2}:
        return GameMode.BATTLE
    return GameMode.OVERWORLD


def location_label(map_id: int | None) -> str | None:
    if map_id is None:
        return None
    return {
        MapId.PALLET_TOWN: "pallet_town",
        MapId.VIRIDIAN_CITY: "viridian_city",
        MapId.PEWTER_CITY: "pewter_city",
        MapId.CERULEAN_CITY: "cerulean_city",
        MapId.LAVENDER_TOWN: "lavender_town",
        MapId.VERMILION_CITY: "vermilion_city",
        MapId.CELADON_CITY: "celadon_city",
        MapId.FUCHSIA_CITY: "fuchsia_city",
        MapId.CINNABAR_ISLAND: "cinnabar_island",
        MapId.INDIGO_PLATEAU: "indigo_plateau",
        MapId.SAFFRON_CITY: "saffron_city",
        MapId.REDS_HOUSE_1F: "reds_house_1f",
        MapId.REDS_HOUSE_2F: "reds_house_2f",
        MapId.OAKS_LAB: "oaks_lab",
        MapId.HALL_OF_FAME: "hall_of_fame",
        MapId.CHAMPIONS_ROOM: "champions_room",
        MapId.INDIGO_PLATEAU_LOBBY: "indigo_plateau_lobby",
    }.get(map_id, f"map_{map_id:02x}")


def semantic_facts(raw: RawGameState) -> frozenset[str]:
    if not raw.game_started:
        return frozenset()

    facts: set[str] = {"story:adventure_begun"}
    events = raw.event_flags
    items = set(raw.bag_item_ids or ())
    badges = Badge(raw.badge_bits or 0)

    if (raw.party_count or 0) > 0 or _event(events, EventFlag.GOT_STARTER):
        facts.add("party:starter_obtained")
    if _event(events, EventFlag.FOLLOWED_OAK_INTO_LAB):
        facts.add("story:oak_lab_reached")
    if _event(events, EventFlag.OAK_ASKED_TO_CHOOSE_MON):
        facts.add("story:starter_selection_ready")
    if _event(events, EventFlag.GOT_POKEDEX):
        facts.add("story:pokedex_received")

    map_facts = {
        MapId.PEWTER_CITY: "location:pewter_city",
        MapId.CERULEAN_CITY: "location:cerulean_city",
        MapId.LAVENDER_TOWN: "location:lavender_town",
        MapId.VERMILION_CITY: "location:vermilion_city",
        MapId.CELADON_CITY: "location:celadon_city",
        MapId.FUCHSIA_CITY: "location:fuchsia_city",
        MapId.CINNABAR_ISLAND: "location:cinnabar_island",
        MapId.SAFFRON_CITY: "location:saffron_city",
    }
    if raw.map_id in map_facts:
        facts.add(map_facts[MapId(raw.map_id)])
    if raw.map_id in {MapId.INDIGO_PLATEAU, MapId.INDIGO_PLATEAU_LOBBY}:
        facts.add("story:victory_road_cleared")

    for badge, fact in {
        Badge.BOULDER: "badge:boulder",
        Badge.CASCADE: "badge:cascade",
        Badge.THUNDER: "badge:thunder",
        Badge.RAINBOW: "badge:rainbow",
        Badge.SOUL: "badge:soul",
        Badge.MARSH: "badge:marsh",
        Badge.VOLCANO: "badge:volcano",
        Badge.EARTH: "badge:earth",
    }.items():
        if badges & badge:
            facts.add(fact)

    _add_if_event(facts, events, EventFlag.GOT_SS_TICKET, "item:ss_ticket")
    _add_if_event(
        facts,
        events,
        EventFlag.BEAT_ROCKET_HIDEOUT_GIOVANNI,
        "story:rocket_hideout_cleared",
    )
    _add_if_event(facts, events, EventFlag.BEAT_SILPH_CO_GIOVANNI, "story:silph_co_liberated")
    _add_if_event(facts, events, EventFlag.BEAT_LORELEI, "league:lorelei_defeated")
    _add_if_event(facts, events, EventFlag.BEAT_BRUNO, "league:bruno_defeated")
    _add_if_event(facts, events, EventFlag.BEAT_AGATHA, "league:agatha_defeated")
    _add_if_event(facts, events, EventFlag.BEAT_LANCE, "league:lance_defeated")
    _add_if_event(facts, events, EventFlag.BEAT_CHAMPION_RIVAL, CHAMPION_DEFEATED_FACT)

    if ItemId.SS_TICKET in items:
        facts.add("item:ss_ticket")
    if ItemId.SILPH_SCOPE in items:
        facts.add("item:silph_scope")
    if ItemId.POKE_FLUTE in items or _event(events, EventFlag.GOT_POKE_FLUTE):
        facts.add("item:poke_flute")
    if ItemId.SECRET_KEY in items:
        facts.add("item:secret_key")
    if ItemId.HM01_CUT in items or _event(events, EventFlag.GOT_HM01):
        facts.add("move:cut_available")
    if ItemId.HM03_SURF in items or _event(events, EventFlag.GOT_HM03):
        facts.add("move:surf_available")
    if ItemId.HM04_STRENGTH in items or _event(events, EventFlag.GOT_HM04):
        facts.add("move:strength_available")

    if raw.map_id == MapId.HALL_OF_FAME and _event(events, EventFlag.BEAT_CHAMPION_RIVAL):
        facts.add(HALL_OF_FAME_FACT)
    return frozenset(facts)


def _event(events: bytes | None, event: EventFlag) -> bool:
    return event_flag_is_set(events, int(event))


def _add_if_event(
    facts: set[str],
    events: bytes | None,
    event: EventFlag,
    fact: str,
) -> None:
    if _event(events, event):
        facts.add(fact)
