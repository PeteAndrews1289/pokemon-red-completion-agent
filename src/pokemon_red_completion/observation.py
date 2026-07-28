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

    NPC_MOVEMENT_SCRIPT_TABLE = 0xCC57
    ENGAGED_TRAINER_CLASS = 0xCD2D
    SIMULATED_JOYPAD_INDEX = 0xCD38
    JOY_IGNORE = 0xCD6B
    BATTLE_RESULT = 0xCF0B
    TRAINER_CLASS = 0xD031
    IS_IN_BATTLE = 0xD057
    CURRENT_OPPONENT = 0xD059
    GYM_LEADER_NUMBER = 0xD05C
    PARTY_COUNT = 0xD163
    PARTY_SPECIES = 0xD164
    PARTY_MON_1_HP = 0xD16C
    PARTY_MON_1_STATUS = 0xD16F
    PARTY_MON_1_MOVES = 0xD173
    PARTY_MON_1_PP = 0xD188
    PARTY_MON_1_LEVEL = 0xD18C
    PARTY_MON_1_MAX_HP = 0xD18D
    NUM_BAG_ITEMS = 0xD31D
    BAG_ITEMS = 0xD31E
    OBTAINED_BADGES = 0xD356
    CURRENT_MAP = 0xD35E
    PLAYER_Y = 0xD361
    PLAYER_X = 0xD362
    PLAYER_MOVING_DIRECTION = 0xD528
    OAKS_LAB_SCRIPT = 0xD5F0
    PALLET_TOWN_SCRIPT = 0xD5F1
    VIRIDIAN_CITY_SCRIPT = 0xD5F4
    PEWTER_CITY_SCRIPT = 0xD5F7
    PEWTER_GYM_SCRIPT = 0xD5FC
    REDS_HOUSE_2F_SCRIPT = 0xD60C
    VIRIDIAN_MART_SCRIPT = 0xD60D
    VIRIDIAN_FOREST_SCRIPT = 0xD618
    BEAT_GYM_FLAGS = 0xD72A
    STATUS_FLAGS_5 = 0xD730
    STATUS_FLAGS_6 = 0xD732
    MOVEMENT_FLAGS = 0xD736
    EVENT_FLAGS = 0xD747
    CURRENT_MAP_SCRIPT = 0xDA39


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
    ROUTE_1 = 0x0C
    ROUTE_2 = 0x0D
    REDS_HOUSE_1F = 0x25
    REDS_HOUSE_2F = 0x26
    OAKS_LAB = 0x28
    VIRIDIAN_POKECENTER = 0x29
    VIRIDIAN_MART = 0x2A
    VIRIDIAN_FOREST_NORTH_GATE = 0x2F
    ROUTE_2_GATE = 0x31
    VIRIDIAN_FOREST_SOUTH_GATE = 0x32
    VIRIDIAN_FOREST = 0x33
    PEWTER_GYM = 0x36
    PEWTER_POKECENTER = 0x3A
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
    GOT_OAKS_PARCEL = 0x039
    BEAT_VIRIDIAN_GYM_GIOVANNI = 0x051
    GOT_TM34 = 0x076
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
    OAKS_PARCEL = 0x46
    SILPH_SCOPE = 0x48
    POKE_FLUTE = 0x49
    HM01_CUT = 0xC4
    HM03_SURF = 0xC6
    HM04_STRENGTH = 0xC7
    TM34_BIDE = 0xEA


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
SCRIPTED_MOVEMENT_STATUS_MASK = (1 << 0) | (1 << 5) | (1 << 7)
EXITING_DOOR_MOVEMENT_MASK = 1 << 1
SQUIRTLE_SPECIES_ID = 0xB1
BUBBLE_MOVE_ID = 0x91
BROCK_OPPONENT_ID = 0xEA
BROCK_TRAINER_CLASS_ID = 0x22
BROCK_GYM_LEADER_NUMBER = 1
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
    first_party_level: int | None = None
    first_party_hp: int | None = None
    first_party_max_hp: int | None = None
    first_party_status: int | None = None
    battle_result: int | None = None
    first_party_moves: tuple[int, ...] | None = None
    first_party_pp: tuple[int, ...] | None = None


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


class OaksErrandPhase(StrEnum):
    UNKNOWN = "unknown"
    STARTER_READY = "starter_ready"
    RIVAL_BATTLE = "rival_battle"
    RIVAL_DEFEATED = "rival_defeated"
    PARCEL_OBTAINED = "parcel_obtained"
    POKEDEX_OBTAINED = "pokedex_obtained"


@dataclass(frozen=True, slots=True)
class OaksErrandState:
    """Semantic controls and evidence for the bounded rival/parcel/Pokédex chapter."""

    phase: OaksErrandPhase
    joy_ignore: int
    lab_script: int
    mart_script: int
    battled_rival: bool
    got_oaks_parcel: bool
    oak_got_parcel: bool
    got_pokedex: bool
    parcel_in_bag: bool
    first_party_species: int | None
    first_party_level: int | None
    first_party_hp: int | None
    first_party_max_hp: int | None
    battle_result: int | None
    map_id: int | None = None
    battle_state: int | None = None

    @property
    def controls_ready(self) -> bool:
        return self.joy_ignore == 0

    @property
    def rival_victory_snapshot(self) -> bool:
        return (
            self.phase is OaksErrandPhase.RIVAL_DEFEATED
            and self.map_id == MapId.OAKS_LAB
            and self.battle_state == 0
            and self.lab_script == 18
            and self.controls_ready
            and self.battle_result == 0
            and self.battled_rival
            and self.first_party_species == SQUIRTLE_SPECIES_ID
            and self.first_party_level == 6
            and self.first_party_hp == 21
            and self.first_party_max_hp == 21
        )

    @property
    def parcel_snapshot(self) -> bool:
        return (
            self.phase is OaksErrandPhase.PARCEL_OBTAINED
            and self.map_id == MapId.VIRIDIAN_MART
            and self.battle_state == 0
            and self.mart_script == 2
            and self.controls_ready
            and self.got_oaks_parcel
            and self.parcel_in_bag
        )

    @property
    def pokedex_snapshot(self) -> bool:
        return (
            self.phase is OaksErrandPhase.POKEDEX_OBTAINED
            and self.map_id == MapId.OAKS_LAB
            and self.battle_state == 0
            and self.lab_script == 18
            and self.controls_ready
            and self.got_oaks_parcel
            and self.oak_got_parcel
            and self.got_pokedex
            and not self.parcel_in_bag
            and self.first_party_species == SQUIRTLE_SPECIES_ID
        )


class TravelBoundary(StrEnum):
    UNKNOWN = "unknown"
    PALLET_LAB_EXTERIOR = "pallet_lab_exterior"
    VIRIDIAN_SOUTH_EDGE = "viridian_south_edge"
    ROUTE_2_SOUTH_EDGE = "route_2_south_edge"
    FOREST_SOUTH_GATE = "forest_south_gate"
    FOREST_SOUTH_ENTRY = "forest_south_entry"
    FOREST_NORTH_GATE = "forest_north_gate"
    ROUTE_2_NORTH_RETURN = "route_2_north_return"
    PEWTER_SOUTH_EDGE = "pewter_south_edge"
    PEWTER_GYM_ENTRANCE = "pewter_gym_entrance"


class NorthboundPhase(StrEnum):
    UNKNOWN = "unknown"
    LAB_EXITED = "lab_exited"
    VIRIDIAN_REACHED = "viridian_reached"
    ROUTE_2_SOUTH_REACHED = "route_2_south_reached"
    FOREST_GATE_REACHED = "forest_gate_reached"
    FOREST_ENTERED = "forest_entered"
    FOREST_CLEARED = "forest_cleared"
    PEWTER_REACHED = "pewter_reached"
    PEWTER_GYM_ENTERED = "pewter_gym_entered"
    BROCK_BATTLE = "brock_battle"
    BROCK_DEFEATED = "brock_defeated"


@dataclass(frozen=True, slots=True)
class InputReadiness:
    joy_ignore: int
    simulated_joypad_index: int
    npc_movement_script_table: int
    player_moving_direction: int
    status_flags_5: int
    movement_flags: int = 0

    @property
    def ready(self) -> bool:
        return (
            self.joy_ignore == 0
            and self.simulated_joypad_index == 0
            and self.npc_movement_script_table == 0
            and self.player_moving_direction == 0
            and not bool(self.status_flags_5 & SCRIPTED_MOVEMENT_STATUS_MASK)
            and not bool(self.movement_flags & EXITING_DOOR_MOVEMENT_MASK)
        )


@dataclass(frozen=True, slots=True)
class PewterChapterState:
    """Revision-bound semantic evidence for travel to Pewter and Brock."""

    phase: NorthboundPhase
    boundary: TravelBoundary
    controls: InputReadiness
    local_script: int
    current_map_script: int
    oak_lab_script: int
    got_oaks_parcel: bool
    oak_got_parcel: bool
    got_pokedex: bool
    parcel_in_bag: bool
    beat_brock: bool
    got_tm34: bool
    tm34_in_bag: bool
    boulder_badge: bool
    boulder_badge_mirror: bool
    current_opponent: int
    trainer_class: int
    engaged_trainer_class: int
    gym_leader_number: int
    map_id: int | None
    player_x: int | None
    player_y: int | None
    party_count: int | None
    first_party_species: int | None
    first_party_hp: int | None
    first_party_max_hp: int | None
    first_party_level: int | None
    battle_state: int | None
    battle_result: int | None
    first_party_status: int | None = None
    first_party_moves: tuple[int, ...] | None = None
    first_party_pp: tuple[int, ...] | None = None

    @property
    def post_pokedex_invariants(self) -> bool:
        return (
            self.got_oaks_parcel
            and self.oak_got_parcel
            and self.got_pokedex
            and not self.parcel_in_bag
            and self.oak_lab_script == 18
            and self.party_count == 1
            and self.first_party_species == SQUIRTLE_SPECIES_ID
            and (self.first_party_hp or 0) > 0
        )

    @property
    def stable_travel_snapshot(self) -> bool:
        return (
            self.unbeaten_brock_invariants
            and self.battle_state == 0
            and self.controls.ready
            and self.current_map_script == 0
        )

    @property
    def unbeaten_brock_invariants(self) -> bool:
        return (
            self.post_pokedex_invariants
            and self.first_party_status == 0
            and not self.beat_brock
            and not self.got_tm34
            and not self.tm34_in_bag
            and not self.boulder_badge
            and not self.boulder_badge_mirror
        )

    @property
    def pewter_snapshot(self) -> bool:
        return (
            self.phase is NorthboundPhase.PEWTER_REACHED
            and self.boundary is TravelBoundary.PEWTER_SOUTH_EDGE
            and self.stable_travel_snapshot
            and self.local_script == 0
            and not self.beat_brock
            and not self.boulder_badge
            and not self.boulder_badge_mirror
        )

    @property
    def travel_boundary_snapshot(self) -> bool:
        if self.boundary is TravelBoundary.UNKNOWN or not self.stable_travel_snapshot:
            return False
        expected_script = {
            TravelBoundary.PALLET_LAB_EXTERIOR: 5,
            TravelBoundary.VIRIDIAN_SOUTH_EDGE: 0,
            TravelBoundary.ROUTE_2_SOUTH_EDGE: 0,
            TravelBoundary.FOREST_SOUTH_GATE: 0,
            TravelBoundary.FOREST_SOUTH_ENTRY: 0,
            TravelBoundary.FOREST_NORTH_GATE: 0,
            TravelBoundary.ROUTE_2_NORTH_RETURN: 0,
            TravelBoundary.PEWTER_SOUTH_EDGE: 0,
            TravelBoundary.PEWTER_GYM_ENTRANCE: 0,
        }[self.boundary]
        return self.local_script == expected_script

    @property
    def brock_battle_snapshot(self) -> bool:
        return (
            self.phase is NorthboundPhase.BROCK_BATTLE
            and self.map_id == MapId.PEWTER_GYM
            and self.unbeaten_brock_invariants
            and self.battle_state == 2
            and self.local_script == 3
            and self.current_map_script == 3
            and self.current_opponent == BROCK_OPPONENT_ID
            and self.trainer_class == BROCK_TRAINER_CLASS_ID
            and self.engaged_trainer_class == BROCK_OPPONENT_ID
            and self.gym_leader_number == BROCK_GYM_LEADER_NUMBER
        )

    @property
    def brock_ready_snapshot(self) -> bool:
        """Require a healthy, battle-capable Squirtle before challenging Brock."""
        moves = self.first_party_moves or ()
        pp = self.first_party_pp or ()
        try:
            bubble_slot = moves.index(BUBBLE_MOVE_ID)
        except ValueError:
            return False
        bubble_pp = pp[bubble_slot] & 0x3F if bubble_slot < len(pp) else 0
        return (
            self.phase is NorthboundPhase.PEWTER_GYM_ENTERED
            and self.boundary is TravelBoundary.PEWTER_GYM_ENTRANCE
            and self.travel_boundary_snapshot
            and not self.beat_brock
            and not self.boulder_badge
            and not self.boulder_badge_mirror
            and self.first_party_status == 0
            and (self.first_party_level or 0) >= 9
            and (self.first_party_hp or 0) >= 19
            and (self.first_party_max_hp or 0) >= (self.first_party_hp or 0)
            and bubble_pp >= 4
        )

    @property
    def brock_victory_snapshot(self) -> bool:
        return (
            self.phase is NorthboundPhase.BROCK_DEFEATED
            and self.map_id == MapId.PEWTER_GYM
            and self.post_pokedex_invariants
            and self.battle_state == 0
            and self.battle_result == 0
            and self.beat_brock
            and self.got_tm34
            and self.tm34_in_bag
            and self.boulder_badge
            and self.boulder_badge_mirror
            and self.local_script == 0
            and self.current_map_script == 0
            and self.controls.ready
            and self.first_party_status == 0
        )


class PewterProgressError(ValueError):
    """Raised when northbound evidence skips or contradicts a required boundary."""


class PewterProgressTracker:
    """Latch one ordered post-Pokédex proof without trusting a destination alone."""

    _BOUNDARIES = (
        TravelBoundary.PALLET_LAB_EXTERIOR,
        TravelBoundary.VIRIDIAN_SOUTH_EDGE,
        TravelBoundary.ROUTE_2_SOUTH_EDGE,
        TravelBoundary.FOREST_SOUTH_GATE,
        TravelBoundary.FOREST_SOUTH_ENTRY,
        TravelBoundary.FOREST_NORTH_GATE,
        TravelBoundary.ROUTE_2_NORTH_RETURN,
        TravelBoundary.PEWTER_SOUTH_EDGE,
        TravelBoundary.PEWTER_GYM_ENTRANCE,
    )

    def __init__(self, pokedex_state: OaksErrandState) -> None:
        if not pokedex_state.pokedex_snapshot:
            raise PewterProgressError(
                "Northbound qualification must begin at the verified Pokédex boundary."
            )
        self._boundary_index = -1
        self._saw_brock_ready = False
        self._saw_brock_battle = False
        self._brock_defeated = False

    @property
    def reached_boundaries(self) -> tuple[TravelBoundary, ...]:
        return self._BOUNDARIES[: self._boundary_index + 1]

    @property
    def saw_brock_battle(self) -> bool:
        return self._saw_brock_battle

    @property
    def saw_brock_ready(self) -> bool:
        return self._saw_brock_ready

    @property
    def brock_defeated(self) -> bool:
        return self._brock_defeated

    def observe(self, state: PewterChapterState) -> NorthboundPhase:
        if state.brock_victory_snapshot:
            if not self._saw_brock_battle:
                raise PewterProgressError(
                    "Brock victory cannot qualify without the observed live battle."
                )
            self._brock_defeated = True
            return NorthboundPhase.BROCK_DEFEATED

        if state.brock_battle_snapshot:
            if (
                self._boundary_index != len(self._BOUNDARIES) - 1
                or not self._saw_brock_ready
            ):
                raise PewterProgressError(
                    "Brock battle appeared before the battle-ready gym-entry proof."
                )
            self._saw_brock_battle = True
            return NorthboundPhase.BROCK_BATTLE

        if state.boundary is TravelBoundary.UNKNOWN:
            return state.phase
        if not state.travel_boundary_snapshot:
            raise PewterProgressError("Travel boundary failed its stable semantic snapshot.")

        expected_index = self._boundary_index + 1
        if (
            self._boundary_index >= 0
            and state.boundary is self._BOUNDARIES[self._boundary_index]
        ):
            return state.phase
        if expected_index >= len(self._BOUNDARIES):
            raise PewterProgressError("Unexpected travel boundary after Pewter Gym entry.")
        if state.boundary is not self._BOUNDARIES[expected_index]:
            raise PewterProgressError("Northbound evidence skipped a required travel boundary.")
        if (
            state.boundary is TravelBoundary.PEWTER_GYM_ENTRANCE
            and not state.brock_ready_snapshot
        ):
            raise PewterProgressError(
                "Pewter Gym entry failed the healthy Bubble-readiness gate."
            )
        self._boundary_index = expected_index
        if state.boundary is TravelBoundary.PEWTER_GYM_ENTRANCE:
            self._saw_brock_ready = True
        return state.phase


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
        first_party_level = (
            self._memory.read_u8(RamAddress.PARTY_MON_1_LEVEL) if party_count else None
        )
        first_party_hp = (
            self._read_u16_be(RamAddress.PARTY_MON_1_HP) if party_count else None
        )
        first_party_max_hp = (
            self._read_u16_be(RamAddress.PARTY_MON_1_MAX_HP) if party_count else None
        )
        first_party_status = (
            self._memory.read_u8(RamAddress.PARTY_MON_1_STATUS)
            if party_count
            else None
        )
        first_party_moves = (
            tuple(
                self._memory.read_u8(int(RamAddress.PARTY_MON_1_MOVES) + index)
                for index in range(4)
            )
            if party_count
            else None
        )
        first_party_pp = (
            tuple(
                self._memory.read_u8(int(RamAddress.PARTY_MON_1_PP) + index)
                for index in range(4)
            )
            if party_count
            else None
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
            first_party_level=first_party_level,
            first_party_hp=first_party_hp,
            first_party_max_hp=first_party_max_hp,
            first_party_status=first_party_status,
            battle_result=self._memory.read_u8(RamAddress.BATTLE_RESULT),
            first_party_moves=first_party_moves,
            first_party_pp=first_party_pp,
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

    def read_oaks_errand_state(self, raw: RawGameState) -> OaksErrandState:
        """Translate pinned script, event, inventory, and party state into one phase."""
        joy_ignore = self._memory.read_u8(RamAddress.JOY_IGNORE)
        lab_script = self._memory.read_u8(RamAddress.OAKS_LAB_SCRIPT)
        mart_script = self._memory.read_u8(RamAddress.VIRIDIAN_MART_SCRIPT)
        battled_rival = _event(raw.event_flags, EventFlag.BATTLED_RIVAL_IN_OAKS_LAB)
        got_oaks_parcel = _event(raw.event_flags, EventFlag.GOT_OAKS_PARCEL)
        oak_got_parcel = _event(raw.event_flags, EventFlag.OAK_GOT_PARCEL)
        got_pokedex = _event(raw.event_flags, EventFlag.GOT_POKEDEX)
        parcel_in_bag = ItemId.OAKS_PARCEL in set(raw.bag_item_ids or ())
        first_species = raw.party_species_ids[0] if raw.party_species_ids else None

        phase = OaksErrandPhase.UNKNOWN
        if (
            raw.map_id == MapId.OAKS_LAB
            and raw.battle_state == 0
            and lab_script == 18
            and joy_ignore == 0
            and got_oaks_parcel
            and oak_got_parcel
            and got_pokedex
            and not parcel_in_bag
            and first_species == SQUIRTLE_SPECIES_ID
        ):
            phase = OaksErrandPhase.POKEDEX_OBTAINED
        elif (
            raw.map_id == MapId.VIRIDIAN_MART
            and raw.battle_state == 0
            and mart_script == 2
            and joy_ignore == 0
            and got_oaks_parcel
            and parcel_in_bag
        ):
            phase = OaksErrandPhase.PARCEL_OBTAINED
        elif (
            raw.map_id == MapId.OAKS_LAB
            and raw.battle_state == 0
            and lab_script == 18
            and joy_ignore == 0
            and battled_rival
            and first_species == SQUIRTLE_SPECIES_ID
        ):
            phase = OaksErrandPhase.RIVAL_DEFEATED
        elif (
            raw.map_id == MapId.OAKS_LAB
            and raw.battle_state == 2
            and lab_script == 12
        ):
            phase = OaksErrandPhase.RIVAL_BATTLE
        elif (
            raw.map_id == MapId.OAKS_LAB
            and raw.party_count == 1
            and first_species == SQUIRTLE_SPECIES_ID
            and lab_script == OAKS_LAB_STARTER_OBTAINED_SCRIPT
        ):
            phase = OaksErrandPhase.STARTER_READY

        return OaksErrandState(
            phase=phase,
            joy_ignore=joy_ignore,
            lab_script=lab_script,
            mart_script=mart_script,
            battled_rival=battled_rival,
            got_oaks_parcel=got_oaks_parcel,
            oak_got_parcel=oak_got_parcel,
            got_pokedex=got_pokedex,
            parcel_in_bag=parcel_in_bag,
            first_party_species=first_species,
            first_party_level=raw.first_party_level,
            first_party_hp=raw.first_party_hp,
            first_party_max_hp=raw.first_party_max_hp,
            battle_result=raw.battle_result,
            map_id=raw.map_id,
            battle_state=raw.battle_state,
        )

    def read_input_readiness(self) -> InputReadiness:
        return InputReadiness(
            joy_ignore=self._memory.read_u8(RamAddress.JOY_IGNORE),
            simulated_joypad_index=self._memory.read_u8(
                RamAddress.SIMULATED_JOYPAD_INDEX
            ),
            npc_movement_script_table=self._memory.read_u8(
                RamAddress.NPC_MOVEMENT_SCRIPT_TABLE
            ),
            player_moving_direction=self._memory.read_u8(
                RamAddress.PLAYER_MOVING_DIRECTION
            ),
            status_flags_5=self._memory.read_u8(RamAddress.STATUS_FLAGS_5),
            movement_flags=self._memory.read_u8(RamAddress.MOVEMENT_FLAGS),
        )

    def read_pewter_chapter_state(self, raw: RawGameState) -> PewterChapterState:
        """Translate route, script, battle, and badge evidence into one phase."""
        controls = self.read_input_readiness()
        got_oaks_parcel = _event(raw.event_flags, EventFlag.GOT_OAKS_PARCEL)
        oak_got_parcel = _event(raw.event_flags, EventFlag.OAK_GOT_PARCEL)
        got_pokedex = _event(raw.event_flags, EventFlag.GOT_POKEDEX)
        beat_brock = _event(raw.event_flags, EventFlag.BEAT_BROCK)
        got_tm34 = _event(raw.event_flags, EventFlag.GOT_TM34)
        parcel_in_bag = ItemId.OAKS_PARCEL in set(raw.bag_item_ids or ())
        tm34_in_bag = ItemId.TM34_BIDE in set(raw.bag_item_ids or ())
        local_script = self._local_script(raw.map_id)
        current_map_script = self._memory.read_u8(RamAddress.CURRENT_MAP_SCRIPT)
        badge_bits = raw.badge_bits or 0
        badge_mirror = self._memory.read_u8(RamAddress.BEAT_GYM_FLAGS)
        boundary = _travel_boundary(raw)

        phase = NorthboundPhase.UNKNOWN
        if (
            raw.map_id == MapId.PEWTER_GYM
            and raw.battle_state == 0
            and raw.battle_result == 0
            and beat_brock
            and got_tm34
            and tm34_in_bag
            and bool(badge_bits & Badge.BOULDER)
            and bool(badge_mirror & Badge.BOULDER)
            and local_script == 0
            and current_map_script == 0
            and controls.ready
        ):
            phase = NorthboundPhase.BROCK_DEFEATED
        elif (
            raw.map_id == MapId.PEWTER_GYM
            and raw.battle_state == 2
            and local_script == 3
            and current_map_script == 3
            and self._memory.read_u8(RamAddress.CURRENT_OPPONENT)
            == BROCK_OPPONENT_ID
            and self._memory.read_u8(RamAddress.TRAINER_CLASS)
            == BROCK_TRAINER_CLASS_ID
            and self._memory.read_u8(RamAddress.ENGAGED_TRAINER_CLASS)
            == BROCK_OPPONENT_ID
            and self._memory.read_u8(RamAddress.GYM_LEADER_NUMBER)
            == BROCK_GYM_LEADER_NUMBER
        ):
            phase = NorthboundPhase.BROCK_BATTLE
        elif boundary is TravelBoundary.PEWTER_GYM_ENTRANCE:
            phase = NorthboundPhase.PEWTER_GYM_ENTERED
        elif boundary is TravelBoundary.PEWTER_SOUTH_EDGE:
            phase = NorthboundPhase.PEWTER_REACHED
        elif boundary in {
            TravelBoundary.ROUTE_2_NORTH_RETURN,
            TravelBoundary.FOREST_NORTH_GATE,
        }:
            phase = NorthboundPhase.FOREST_CLEARED
        elif boundary is TravelBoundary.FOREST_SOUTH_ENTRY:
            phase = NorthboundPhase.FOREST_ENTERED
        elif boundary is TravelBoundary.FOREST_SOUTH_GATE:
            phase = NorthboundPhase.FOREST_GATE_REACHED
        elif boundary is TravelBoundary.ROUTE_2_SOUTH_EDGE:
            phase = NorthboundPhase.ROUTE_2_SOUTH_REACHED
        elif boundary is TravelBoundary.VIRIDIAN_SOUTH_EDGE:
            phase = NorthboundPhase.VIRIDIAN_REACHED
        elif boundary is TravelBoundary.PALLET_LAB_EXTERIOR:
            phase = NorthboundPhase.LAB_EXITED

        return PewterChapterState(
            phase=phase,
            boundary=boundary,
            controls=controls,
            local_script=local_script,
            current_map_script=current_map_script,
            oak_lab_script=self._memory.read_u8(RamAddress.OAKS_LAB_SCRIPT),
            got_oaks_parcel=got_oaks_parcel,
            oak_got_parcel=oak_got_parcel,
            got_pokedex=got_pokedex,
            parcel_in_bag=parcel_in_bag,
            beat_brock=beat_brock,
            got_tm34=got_tm34,
            tm34_in_bag=tm34_in_bag,
            boulder_badge=bool(badge_bits & Badge.BOULDER),
            boulder_badge_mirror=bool(badge_mirror & Badge.BOULDER),
            current_opponent=self._memory.read_u8(RamAddress.CURRENT_OPPONENT),
            trainer_class=self._memory.read_u8(RamAddress.TRAINER_CLASS),
            engaged_trainer_class=self._memory.read_u8(
                RamAddress.ENGAGED_TRAINER_CLASS
            ),
            gym_leader_number=self._memory.read_u8(RamAddress.GYM_LEADER_NUMBER),
            map_id=raw.map_id,
            player_x=raw.player_x,
            player_y=raw.player_y,
            party_count=raw.party_count,
            first_party_species=(
                raw.party_species_ids[0] if raw.party_species_ids else None
            ),
            first_party_hp=raw.first_party_hp,
            first_party_max_hp=raw.first_party_max_hp,
            first_party_level=raw.first_party_level,
            first_party_status=raw.first_party_status,
            battle_state=raw.battle_state,
            battle_result=raw.battle_result,
            first_party_moves=raw.first_party_moves,
            first_party_pp=raw.first_party_pp,
        )

    def _local_script(self, map_id: int | None) -> int:
        address = {
            MapId.OAKS_LAB: RamAddress.OAKS_LAB_SCRIPT,
            MapId.PALLET_TOWN: RamAddress.PALLET_TOWN_SCRIPT,
            MapId.VIRIDIAN_CITY: RamAddress.VIRIDIAN_CITY_SCRIPT,
            MapId.VIRIDIAN_FOREST: RamAddress.VIRIDIAN_FOREST_SCRIPT,
            MapId.PEWTER_CITY: RamAddress.PEWTER_CITY_SCRIPT,
            MapId.PEWTER_GYM: RamAddress.PEWTER_GYM_SCRIPT,
        }.get(map_id)
        return self._memory.read_u8(address) if address is not None else 0

    def _read_u16_be(self, address: int) -> int:
        return (self._memory.read_u8(address) << 8) | self._memory.read_u8(address + 1)


def _travel_boundary(raw: RawGameState) -> TravelBoundary:
    position = (raw.map_id, raw.player_x, raw.player_y)
    if position == (MapId.PALLET_TOWN, 12, 12):
        return TravelBoundary.PALLET_LAB_EXTERIOR
    if position == (MapId.VIRIDIAN_CITY, 21, 35):
        return TravelBoundary.VIRIDIAN_SOUTH_EDGE
    if (
        raw.map_id == MapId.ROUTE_2
        and raw.player_x in {7, 8, 9}
        and raw.player_y == 71
    ):
        return TravelBoundary.ROUTE_2_SOUTH_EDGE
    if position == (MapId.VIRIDIAN_FOREST_SOUTH_GATE, 4, 7):
        return TravelBoundary.FOREST_SOUTH_GATE
    if (
        raw.map_id == MapId.VIRIDIAN_FOREST
        and raw.player_x in {16, 17}
        and raw.player_y == 47
    ):
        return TravelBoundary.FOREST_SOUTH_ENTRY
    if raw.map_id == MapId.VIRIDIAN_FOREST_NORTH_GATE:
        return TravelBoundary.FOREST_NORTH_GATE
    if position == (MapId.ROUTE_2, 3, 11):
        return TravelBoundary.ROUTE_2_NORTH_RETURN
    if (
        raw.map_id == MapId.PEWTER_CITY
        and raw.player_x in {18, 19}
        and raw.player_y == 35
    ):
        return TravelBoundary.PEWTER_SOUTH_EDGE
    if position == (MapId.PEWTER_GYM, 4, 13):
        return TravelBoundary.PEWTER_GYM_ENTRANCE
    return TravelBoundary.UNKNOWN


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
        MapId.ROUTE_1: "route_1",
        MapId.ROUTE_2: "route_2",
        MapId.REDS_HOUSE_1F: "reds_house_1f",
        MapId.REDS_HOUSE_2F: "reds_house_2f",
        MapId.OAKS_LAB: "oaks_lab",
        MapId.VIRIDIAN_POKECENTER: "viridian_pokecenter",
        MapId.VIRIDIAN_MART: "viridian_mart",
        MapId.VIRIDIAN_FOREST_NORTH_GATE: "viridian_forest_north_gate",
        MapId.ROUTE_2_GATE: "route_2_gate",
        MapId.VIRIDIAN_FOREST_SOUTH_GATE: "viridian_forest_south_gate",
        MapId.VIRIDIAN_FOREST: "viridian_forest",
        MapId.PEWTER_GYM: "pewter_gym",
        MapId.PEWTER_POKECENTER: "pewter_pokecenter",
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
