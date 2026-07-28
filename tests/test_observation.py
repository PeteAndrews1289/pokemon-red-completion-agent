from __future__ import annotations

import pytest

from pokemon_red_completion.domain import GameMode
from pokemon_red_completion.observation import (
    EVENT_FLAG_BYTES,
    OAKS_LAB_SELECTION_READY_SCRIPT,
    OAKS_LAB_STARTER_OBTAINED_SCRIPT,
    REDS_HOUSE_2F_NOOP_SCRIPT,
    SQUIRTLE_SPECIES_ID,
    Badge,
    EventFlag,
    ItemId,
    MapId,
    OaksErrandPhase,
    OpeningPhase,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
    SemanticStateError,
    SemanticStateTracker,
    event_flag_is_set,
)
from pokemon_red_completion.referee import (
    CHAMPION_DEFEATED_FACT,
    CompletionReferee,
)
from pokemon_red_completion.route import HALL_OF_FAME_FACT


class RecordingMemory:
    def __init__(self, values: dict[int, int]) -> None:
        self.values = values
        self.reads: list[int] = []

    def read_u8(self, address: int) -> int:
        self.reads.append(int(address))
        return self.values.get(int(address), 0)


def _events(*events: EventFlag) -> bytes:
    payload = bytearray(EVENT_FLAG_BYTES)
    for event in events:
        byte_index, bit = divmod(int(event), 8)
        payload[byte_index] |= 1 << bit
    return bytes(payload)


def _raw(
    *,
    map_id: MapId = MapId.PALLET_TOWN,
    events: tuple[EventFlag, ...] = (),
    badges: Badge | None = None,
    party_count: int = 1,
    party_species_ids: tuple[int, ...] | None = None,
    battle_state: int = 0,
    player_x: int = 0,
    player_y: int = 0,
) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=int(map_id),
        player_x=player_x,
        player_y=player_y,
        party_count=party_count,
        battle_state=battle_state,
        badge_bits=int(badges or Badge(0)),
        bag_item_ids=(),
        event_flags=_events(*events),
        party_species_ids=party_species_ids,
    )


def test_reader_hides_pregame_scratch_state() -> None:
    memory = RecordingMemory(
        {
            RamAddress.STATUS_FLAGS_6: 0,
            RamAddress.CURRENT_MAP: MapId.HALL_OF_FAME,
        }
    )

    raw = PokemonRedStateReader(memory).read()

    assert raw == RawGameState(False, None, None, None, None, None)
    assert memory.reads == [RamAddress.STATUS_FLAGS_6]


def test_reader_extracts_bounded_bag_and_event_state() -> None:
    champion_byte, champion_bit = divmod(int(EventFlag.BEAT_CHAMPION_RIVAL), 8)
    memory = RecordingMemory(
        {
            RamAddress.STATUS_FLAGS_6: 1,
            RamAddress.CURRENT_MAP: MapId.CHAMPIONS_ROOM,
            RamAddress.PLAYER_X: 4,
            RamAddress.PLAYER_Y: 7,
            RamAddress.PARTY_COUNT: 9,
            RamAddress.PARTY_SPECIES: SQUIRTLE_SPECIES_ID,
            int(RamAddress.PARTY_SPECIES) + 1: 0xB0,
            int(RamAddress.PARTY_SPECIES) + 2: 0x15,
            int(RamAddress.PARTY_SPECIES) + 3: 0x54,
            int(RamAddress.PARTY_SPECIES) + 4: 0x99,
            int(RamAddress.PARTY_SPECIES) + 5: 0x01,
            RamAddress.IS_IN_BATTLE: 0,
            RamAddress.OBTAINED_BADGES: int(Badge.BOULDER | Badge.CASCADE),
            RamAddress.NUM_BAG_ITEMS: 2,
            RamAddress.BAG_ITEMS: 0x3F,
            int(RamAddress.BAG_ITEMS) + 2: 0x48,
            int(RamAddress.EVENT_FLAGS) + champion_byte: 1 << champion_bit,
        }
    )

    raw = PokemonRedStateReader(memory).read()

    assert raw.party_count == 6
    assert raw.party_species_ids == (
        SQUIRTLE_SPECIES_ID,
        0xB0,
        0x15,
        0x54,
        0x99,
        0x01,
    )
    assert raw.bag_item_ids == (0x3F, 0x48)
    assert event_flag_is_set(raw.event_flags, EventFlag.BEAT_CHAMPION_RIVAL)


def test_reader_translates_the_stable_pokedex_gate_from_pinned_symbols() -> None:
    events = _events(
        EventFlag.BATTLED_RIVAL_IN_OAKS_LAB,
        EventFlag.GOT_POKEDEX,
        EventFlag.OAK_GOT_PARCEL,
        EventFlag.GOT_OAKS_PARCEL,
    )
    values = {
        RamAddress.STATUS_FLAGS_6: 1,
        RamAddress.CURRENT_MAP: MapId.OAKS_LAB,
        RamAddress.PLAYER_X: 5,
        RamAddress.PLAYER_Y: 3,
        RamAddress.PARTY_COUNT: 1,
        RamAddress.PARTY_SPECIES: SQUIRTLE_SPECIES_ID,
        RamAddress.PARTY_MON_1_HP: 0,
        int(RamAddress.PARTY_MON_1_HP) + 1: 21,
        RamAddress.PARTY_MON_1_LEVEL: 6,
        RamAddress.PARTY_MON_1_MAX_HP: 0,
        int(RamAddress.PARTY_MON_1_MAX_HP) + 1: 21,
        RamAddress.NUM_BAG_ITEMS: 0,
        RamAddress.IS_IN_BATTLE: 0,
        RamAddress.BATTLE_RESULT: 0,
        RamAddress.JOY_IGNORE: 0,
        RamAddress.OAKS_LAB_SCRIPT: 18,
        RamAddress.VIRIDIAN_MART_SCRIPT: 2,
    }
    values.update(
        {
            int(RamAddress.EVENT_FLAGS) + index: value
            for index, value in enumerate(events)
            if value
        }
    )
    reader = PokemonRedStateReader(RecordingMemory(values))

    raw = reader.read()
    state = reader.read_oaks_errand_state(raw)

    assert RamAddress.VIRIDIAN_MART_SCRIPT == 0xD60D
    assert MapId.ROUTE_1 == 0x0C
    assert MapId.VIRIDIAN_MART == 0x2A
    assert EventFlag.GOT_OAKS_PARCEL == 0x039
    assert ItemId.OAKS_PARCEL == 0x46
    assert raw.first_party_level == 6
    assert raw.first_party_hp == raw.first_party_max_hp == 21
    assert state.phase is OaksErrandPhase.POKEDEX_OBTAINED
    assert state.pokedex_snapshot


def test_reader_encapsulates_bedroom_input_symbols() -> None:
    memory = RecordingMemory(
        {
            RamAddress.JOY_IGNORE: 0,
            RamAddress.REDS_HOUSE_2F_SCRIPT: REDS_HOUSE_2F_NOOP_SCRIPT,
        }
    )

    input_state = PokemonRedStateReader(memory).read_bedroom_input_state()

    assert input_state.ready
    assert memory.reads == [
        RamAddress.JOY_IGNORE,
        RamAddress.REDS_HOUSE_2F_SCRIPT,
    ]


@pytest.mark.parametrize(
    ("raw", "memory_values", "expected_phase"),
    (
        (
            _raw(
                map_id=MapId.REDS_HOUSE_2F,
                party_count=0,
                player_x=3,
                player_y=6,
            ),
            {
                RamAddress.JOY_IGNORE: 0,
                RamAddress.REDS_HOUSE_2F_SCRIPT: REDS_HOUSE_2F_NOOP_SCRIPT,
            },
            OpeningPhase.BEDROOM_READY,
        ),
        (
            _raw(
                map_id=MapId.REDS_HOUSE_1F,
                party_count=0,
                player_x=7,
                player_y=1,
            ),
            {RamAddress.JOY_IGNORE: 0},
            OpeningPhase.DOWNSTAIRS,
        ),
        (
            _raw(
                map_id=MapId.PALLET_TOWN,
                party_count=0,
                player_x=5,
                player_y=6,
            ),
            {
                RamAddress.JOY_IGNORE: 0,
                RamAddress.PALLET_TOWN_SCRIPT: 0,
            },
            OpeningPhase.PALLET_FREE,
        ),
        (
            _raw(
                map_id=MapId.PALLET_TOWN,
                events=(EventFlag.OAK_APPEARED_IN_PALLET,),
                party_count=0,
                player_x=10,
                player_y=1,
            ),
            {RamAddress.JOY_IGNORE: 0xFC},
            OpeningPhase.OAK_ESCORT,
        ),
        (
            _raw(
                map_id=MapId.OAKS_LAB,
                events=(
                    EventFlag.FOLLOWED_OAK_INTO_LAB,
                    EventFlag.FOLLOWED_OAK_INTO_LAB_2,
                    EventFlag.OAK_ASKED_TO_CHOOSE_MON,
                ),
                party_count=0,
                player_x=5,
                player_y=3,
            ),
            {
                RamAddress.JOY_IGNORE: 0,
                RamAddress.OAKS_LAB_SCRIPT: OAKS_LAB_SELECTION_READY_SCRIPT,
            },
            OpeningPhase.STARTER_SELECTION_READY,
        ),
        (
            _raw(
                map_id=MapId.OAKS_LAB,
                events=(EventFlag.GOT_STARTER,),
                party_count=1,
                party_species_ids=(SQUIRTLE_SPECIES_ID,),
                player_x=7,
                player_y=4,
            ),
            {
                RamAddress.JOY_IGNORE: 0,
                RamAddress.OAKS_LAB_SCRIPT: OAKS_LAB_STARTER_OBTAINED_SCRIPT,
            },
            OpeningPhase.STARTER_OBTAINED,
        ),
    ),
)
def test_opening_phase_translation_uses_semantic_gates(
    raw: RawGameState,
    memory_values: dict[int, int],
    expected_phase: OpeningPhase,
) -> None:
    control = PokemonRedStateReader(RecordingMemory(memory_values)).read_opening_control_state(raw)

    assert control.phase is expected_phase


def test_opening_selection_gate_requires_both_follow_events_and_exact_script() -> None:
    events_without_second_follow = (
        EventFlag.FOLLOWED_OAK_INTO_LAB,
        EventFlag.OAK_ASKED_TO_CHOOSE_MON,
    )
    raw = _raw(
        map_id=MapId.OAKS_LAB,
        events=events_without_second_follow,
        party_count=0,
        player_x=5,
        player_y=3,
    )
    memory = RecordingMemory(
        {
            RamAddress.JOY_IGNORE: 0,
            RamAddress.OAKS_LAB_SCRIPT: OAKS_LAB_SELECTION_READY_SCRIPT,
        }
    )

    control = PokemonRedStateReader(memory).read_opening_control_state(raw)

    assert control.phase is OpeningPhase.UNKNOWN
    assert not control.followed_oak_into_lab
    assert control.asked_to_choose


@pytest.mark.parametrize(
    ("player_x", "joy_ignore", "lab_script"),
    (
        (6, 0, OAKS_LAB_SELECTION_READY_SCRIPT),
        (5, 0xF0, OAKS_LAB_SELECTION_READY_SCRIPT),
        (5, 0, OAKS_LAB_SELECTION_READY_SCRIPT - 1),
    ),
)
def test_opening_selection_gate_rejects_near_misses(
    player_x: int,
    joy_ignore: int,
    lab_script: int,
) -> None:
    raw = _raw(
        map_id=MapId.OAKS_LAB,
        events=(
            EventFlag.FOLLOWED_OAK_INTO_LAB,
            EventFlag.FOLLOWED_OAK_INTO_LAB_2,
            EventFlag.OAK_ASKED_TO_CHOOSE_MON,
        ),
        party_count=0,
        player_x=player_x,
        player_y=3,
    )
    memory = RecordingMemory(
        {
            RamAddress.JOY_IGNORE: joy_ignore,
            RamAddress.OAKS_LAB_SCRIPT: lab_script,
        }
    )

    control = PokemonRedStateReader(memory).read_opening_control_state(raw)

    assert control.phase is OpeningPhase.UNKNOWN


def test_opening_control_mask_is_translated_without_exposing_button_logic() -> None:
    raw = _raw(
        events=(EventFlag.OAK_APPEARED_IN_PALLET,),
        party_count=0,
        player_x=10,
        player_y=1,
    )

    control = PokemonRedStateReader(
        RecordingMemory({RamAddress.JOY_IGNORE: 0xFC})
    ).read_opening_control_state(raw)

    assert control.phase is OpeningPhase.OAK_ESCORT
    assert control.confirm_allowed
    assert control.cancel_allowed
    assert not control.movement_allowed
    assert not control.all_controls_allowed


def test_semantic_tracker_requires_and_preserves_clean_run_evidence() -> None:
    with pytest.raises(SemanticStateError, match="clean run"):
        SemanticStateTracker(_raw())

    tracker = SemanticStateTracker(RawGameState(False, None, None, None, None, None))
    pewter = tracker.observe(
        _raw(
            map_id=MapId.PEWTER_CITY,
            events=(EventFlag.GOT_STARTER, EventFlag.GOT_POKEDEX),
            badges=Badge.BOULDER,
        )
    )
    later = tracker.observe(_raw(map_id=MapId.CERULEAN_CITY))

    assert {
        "system:clean_power_on",
        "story:adventure_begun",
        "party:starter_obtained",
        "story:pokedex_received",
        "location:pewter_city",
        "badge:boulder",
    } <= pewter.facts
    assert "location:pewter_city" in later.facts
    assert later.location == "cerulean_city"


def test_completion_requires_champion_event_and_hall_map_together() -> None:
    referee = CompletionReferee()

    map_only_tracker = SemanticStateTracker(RawGameState(False, None, None, None, None, None))
    map_only = map_only_tracker.observe(_raw(map_id=MapId.HALL_OF_FAME))
    assert map_only.mode is GameMode.HALL_OF_FAME
    assert HALL_OF_FAME_FACT not in map_only.facts
    assert not referee.inspect(map_only).complete

    tracker = SemanticStateTracker(RawGameState(False, None, None, None, None, None))
    champion_room = tracker.observe(
        _raw(
            map_id=MapId.CHAMPIONS_ROOM,
            events=(EventFlag.BEAT_CHAMPION_RIVAL,),
        )
    )
    assert CHAMPION_DEFEATED_FACT in champion_room.facts
    assert HALL_OF_FAME_FACT not in champion_room.facts
    assert not referee.inspect(champion_room).complete

    hall = tracker.observe(
        _raw(
            map_id=MapId.HALL_OF_FAME,
            events=(EventFlag.BEAT_CHAMPION_RIVAL,),
        )
    )
    assert referee.inspect(hall).complete


def test_event_lookup_rejects_negative_and_short_buffers() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        event_flag_is_set(b"", -1)
    assert not event_flag_is_set(b"\x01", EventFlag.BEAT_CHAMPION_RIVAL)
