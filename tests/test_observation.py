from __future__ import annotations

import pytest

from pokemon_red_completion.domain import GameMode
from pokemon_red_completion.observation import (
    EVENT_FLAG_BYTES,
    REDS_HOUSE_2F_NOOP_SCRIPT,
    Badge,
    EventFlag,
    MapId,
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
    battle_state: int = 0,
) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=int(map_id),
        player_x=0,
        player_y=0,
        party_count=party_count,
        battle_state=battle_state,
        badge_bits=int(badges or Badge(0)),
        bag_item_ids=(),
        event_flags=_events(*events),
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
    assert raw.bag_item_ids == (0x3F, 0x48)
    assert event_flag_is_set(raw.event_flags, EventFlag.BEAT_CHAMPION_RIVAL)


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

    map_only_tracker = SemanticStateTracker(
        RawGameState(False, None, None, None, None, None)
    )
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
