from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.observation import (
    BUG_CATCHER_OPPONENT_ID,
    BUG_CATCHER_TRAINER_CLASS_ID,
    EVENT_FLAG_BYTES,
    MT_MOON_REQUIRED_ROCKET_EVENT,
    MT_MOON_REQUIRED_ROCKET_TRAINER_INDEX,
    MT_MOON_REQUIRED_ROCKET_TRAINER_NUMBER,
    MT_MOON_REQUIRED_ROCKET_TRIGGER_X,
    MT_MOON_REQUIRED_ROCKET_TRIGGER_Y,
    MT_MOON_SUPER_NERD_OPPONENT_ID,
    MT_MOON_SUPER_NERD_TRAINER_NUMBER,
    ROCKET_OPPONENT_ID,
    ROCKET_TRAINER_CLASS_ID,
    ROUTE_3_REQUIRED_TRAINER_SPECS,
    SQUIRTLE_SPECIES_ID,
    SUPER_NERD_TRAINER_CLASS_ID,
    WARTORTLE_SPECIES_ID,
    Badge,
    CeruleanBoundary,
    CeruleanChapterState,
    CeruleanPhase,
    CeruleanProgressError,
    CeruleanProgressTracker,
    EventFlag,
    InputReadiness,
    ItemId,
    MapId,
    NorthboundPhase,
    PewterChapterState,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
    TravelBoundary,
)


class Memory:
    def __init__(self, values: dict[int, int]) -> None:
        self.values = values

    def read_u8(self, address: int) -> int:
        return self.values.get(int(address), 0)


def _events(*events: EventFlag) -> bytes:
    payload = bytearray(EVENT_FLAG_BYTES)
    for event in events:
        byte_index, bit = divmod(int(event), 8)
        payload[byte_index] |= 1 << bit
    return bytes(payload)


READY = InputReadiness(
    joy_ignore=0,
    simulated_joypad_index=0,
    npc_movement_script_table=0,
    player_moving_direction=0,
    status_flags_5=0,
    movement_flags=0,
)
ROUTE_3_DEFEATED = {
    "beat_route_3_trainer_0": True,
    "beat_route_3_trainer_1": True,
    "beat_route_3_trainer_3": True,
    "beat_route_3_trainer_6": True,
}


def _brock_victory() -> PewterChapterState:
    return PewterChapterState(
        phase=NorthboundPhase.BROCK_DEFEATED,
        boundary=TravelBoundary.UNKNOWN,
        controls=READY,
        local_script=0,
        current_map_script=0,
        oak_lab_script=18,
        got_oaks_parcel=True,
        oak_got_parcel=True,
        got_pokedex=True,
        parcel_in_bag=False,
        beat_brock=True,
        got_tm34=True,
        tm34_in_bag=True,
        boulder_badge=True,
        boulder_badge_mirror=True,
        current_opponent=0,
        trainer_class=0,
        engaged_trainer_class=0,
        gym_leader_number=1,
        map_id=MapId.PEWTER_GYM,
        player_x=4,
        player_y=2,
        party_count=1,
        first_party_species=SQUIRTLE_SPECIES_ID,
        first_party_hp=16,
        first_party_max_hp=33,
        first_party_level=12,
        battle_state=0,
        battle_result=0,
        first_party_status=0,
    )


def _chapter() -> CeruleanChapterState:
    return CeruleanChapterState(
        phase=CeruleanPhase.ROUTE_3_REACHED,
        boundary=CeruleanBoundary.ROUTE_3_WEST_ENTRY,
        controls=READY,
        local_script=0,
        current_map_script=0,
        beat_brock=True,
        got_tm34=True,
        boulder_badge=True,
        boulder_badge_mirror=True,
        beat_route_3_trainer_0=False,
        beat_route_3_trainer_1=False,
        beat_route_3_trainer_3=False,
        beat_route_3_trainer_6=False,
        beat_required_rocket=False,
        beat_super_nerd=False,
        got_dome_fossil=False,
        got_helix_fossil=False,
        dome_fossil_in_bag=False,
        helix_fossil_in_bag=False,
        current_opponent=0,
        trainer_class=0,
        trainer_number=0,
        engaged_trainer_class=0,
        engaged_trainer_set=0,
        map_id=MapId.ROUTE_3,
        player_x=0,
        player_y=9,
        party_count=1,
        party_species_ids=(WARTORTLE_SPECIES_ID,),
        first_party_hp=30,
        first_party_max_hp=35,
        first_party_status=0,
        battle_state=0,
        battle_result=0,
    )


BOUNDARY_STATES = (
    (
        CeruleanBoundary.ROUTE_3_WEST_ENTRY,
        CeruleanPhase.ROUTE_3_REACHED,
        MapId.ROUTE_3,
        0,
        9,
    ),
    (
        CeruleanBoundary.ROUTE_4_WEST_ENTRY,
        CeruleanPhase.ROUTE_4_REACHED,
        MapId.ROUTE_4,
        9,
        17,
    ),
    (
        CeruleanBoundary.MT_MOON_1F_ENTRY,
        CeruleanPhase.MT_MOON_ENTERED,
        MapId.MT_MOON_1F,
        14,
        35,
    ),
    (
        CeruleanBoundary.MT_MOON_B1F_DESCENT,
        CeruleanPhase.MT_MOON_B1F_REACHED,
        MapId.MT_MOON_B1F,
        5,
        5,
    ),
    (
        CeruleanBoundary.MT_MOON_B2F_ENTRY,
        CeruleanPhase.MT_MOON_B2F_REACHED,
        MapId.MT_MOON_B2F,
        21,
        17,
    ),
)

POST_FOSSIL_BOUNDARY_STATES = (
    (
        CeruleanBoundary.MT_MOON_B1F_ASCENT,
        CeruleanPhase.MT_MOON_CLEARED,
        MapId.MT_MOON_B1F,
        23,
        3,
    ),
    (
        CeruleanBoundary.ROUTE_4_MT_MOON_EXIT,
        CeruleanPhase.MT_MOON_CLEARED,
        MapId.ROUTE_4,
        24,
        6,
    ),
    (
        CeruleanBoundary.CERULEAN_WEST_ENTRY,
        CeruleanPhase.CERULEAN_REACHED,
        MapId.CERULEAN_CITY,
        0,
        18,
    ),
)


def _at_boundary(
    state: CeruleanChapterState,
    spec: tuple[CeruleanBoundary, CeruleanPhase, MapId, int, int],
) -> CeruleanChapterState:
    boundary, phase, map_id, x, y = spec
    return replace(
        state,
        boundary=boundary,
        phase=phase,
        map_id=map_id,
        player_x=x,
        player_y=y,
    )


def _observe_route_3_trainers(
    tracker: CeruleanProgressTracker, state: CeruleanChapterState
) -> CeruleanChapterState:
    event_fields = (
        "beat_route_3_trainer_0",
        "beat_route_3_trainer_1",
        "beat_route_3_trainer_3",
        "beat_route_3_trainer_6",
    )
    defeated = [False, False, False, False]
    for position, (_, opponent, trainer_class, trainer_number) in enumerate(
        ROUTE_3_REQUIRED_TRAINER_SPECS
    ):
        event_values = dict(zip(event_fields, defeated, strict=True))
        battle = replace(
            state,
            phase=CeruleanPhase.ROUTE_3_TRAINER_BATTLE,
            boundary=CeruleanBoundary.UNKNOWN,
            map_id=MapId.ROUTE_3,
            battle_state=2,
            local_script=2,
            current_map_script=2,
            current_opponent=opponent,
            trainer_class=trainer_class,
            trainer_number=trainer_number,
            engaged_trainer_class=opponent,
            engaged_trainer_set=trainer_number,
            **event_values,
        )
        assert tracker.observe(battle) is CeruleanPhase.ROUTE_3_TRAINER_BATTLE
        defeated[position] = True
    return replace(
        state,
        phase=CeruleanPhase.ROUTE_3_REACHED,
        boundary=CeruleanBoundary.ROUTE_3_WEST_ENTRY,
        map_id=MapId.ROUTE_3,
        player_x=0,
        player_y=9,
        battle_state=0,
        local_script=0,
        current_map_script=0,
        current_opponent=0,
        trainer_class=0,
        trainer_number=0,
        engaged_trainer_class=0,
        engaged_trainer_set=0,
        **dict(zip(event_fields, defeated, strict=True)),
    )


def test_cerulean_symbols_match_the_pinned_pokered_revision() -> None:
    assert RamAddress.ENGAGED_TRAINER_SET == 0xCD2E
    assert RamAddress.TRAINER_NUMBER == 0xD05D
    assert RamAddress.ROUTE_3_SCRIPT == 0xD5F8
    assert RamAddress.ROUTE_4_SCRIPT == 0xD5F9
    assert RamAddress.CERULEAN_GYM_SCRIPT == 0xD5FD
    assert RamAddress.MT_MOON_1F_SCRIPT == 0xD606
    assert RamAddress.MT_MOON_B2F_SCRIPT == 0xD607
    assert RamAddress.CERULEAN_CITY_SCRIPT == 0xD60F
    assert MapId.MT_MOON_B2F == 0x3D
    assert MapId.CERULEAN_GYM == 0x41
    assert EventFlag.BEAT_MT_MOON_EXIT_SUPER_NERD == 0x579
    assert EventFlag.BEAT_MT_MOON_3_TRAINER_0 == 0x57A
    assert MT_MOON_REQUIRED_ROCKET_EVENT is EventFlag.BEAT_MT_MOON_3_TRAINER_0
    assert MT_MOON_REQUIRED_ROCKET_TRAINER_INDEX == 0
    assert MT_MOON_REQUIRED_ROCKET_TRAINER_NUMBER == 1
    assert (
        MT_MOON_REQUIRED_ROCKET_TRIGGER_X,
        MT_MOON_REQUIRED_ROCKET_TRIGGER_Y,
    ) == (11, 19)
    assert EventFlag.GOT_DOME_FOSSIL == 0x57E
    assert EventFlag.GOT_HELIX_FOSSIL == 0x57F
    assert EventFlag.GOT_TM11 == 0x0BE
    assert EventFlag.BEAT_MISTY == 0x0BF
    assert ItemId.DOME_FOSSIL == 0x29
    assert ItemId.HELIX_FOSSIL == 0x2A
    assert ItemId.TM11_BUBBLEBEAM == 0xD3


def test_reader_recognizes_the_first_exact_route_3_trainer_identity() -> None:
    raw = RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_3,
        player_x=10,
        player_y=6,
        party_count=1,
        battle_state=2,
        badge_bits=int(Badge.BOULDER),
        bag_item_ids=(ItemId.TM34_BIDE,),
        event_flags=_events(EventFlag.GOT_TM34, EventFlag.BEAT_BROCK),
        party_species_ids=(WARTORTLE_SPECIES_ID,),
        first_party_hp=30,
        first_party_max_hp=35,
        first_party_status=0,
        battle_result=0,
    )
    memory = Memory(
        {
            RamAddress.ROUTE_3_SCRIPT: 2,
            RamAddress.CURRENT_MAP_SCRIPT: 2,
            RamAddress.BEAT_GYM_FLAGS: int(Badge.BOULDER),
            RamAddress.CURRENT_OPPONENT: BUG_CATCHER_OPPONENT_ID,
            RamAddress.TRAINER_CLASS: BUG_CATCHER_TRAINER_CLASS_ID,
            RamAddress.TRAINER_NUMBER: 4,
            RamAddress.ENGAGED_TRAINER_CLASS: BUG_CATCHER_OPPONENT_ID,
            RamAddress.ENGAGED_TRAINER_SET: 4,
        }
    )

    state = PokemonRedStateReader(memory).read_cerulean_chapter_state(raw)

    assert state.phase is CeruleanPhase.ROUTE_3_TRAINER_BATTLE
    assert state.route_3_trainer_battle_index == 0
    assert state.route_3_trainer_battle_snapshot


@pytest.mark.parametrize(
    ("player_x", "player_y", "expected_boundary"),
    [
        (21, 17, CeruleanBoundary.MT_MOON_B2F_ENTRY),
        (25, 9, CeruleanBoundary.UNKNOWN),
    ],
)
def test_reader_uses_the_collision_legal_b2f_arrival(
    player_x: int,
    player_y: int,
    expected_boundary: CeruleanBoundary,
) -> None:
    raw = RawGameState(
        game_started=True,
        map_id=MapId.MT_MOON_B2F,
        player_x=player_x,
        player_y=player_y,
        party_count=1,
        battle_state=0,
        badge_bits=int(Badge.BOULDER),
        bag_item_ids=(ItemId.TM34_BIDE,),
        event_flags=_events(
            EventFlag.GOT_TM34,
            EventFlag.BEAT_BROCK,
            EventFlag.BEAT_ROUTE_3_TRAINER_0,
            EventFlag.BEAT_ROUTE_3_TRAINER_1,
            EventFlag.BEAT_ROUTE_3_TRAINER_3,
            EventFlag.BEAT_ROUTE_3_TRAINER_6,
        ),
        party_species_ids=(WARTORTLE_SPECIES_ID,),
        first_party_hp=30,
        first_party_max_hp=35,
        first_party_status=0,
        battle_result=0,
    )
    memory = Memory({RamAddress.BEAT_GYM_FLAGS: int(Badge.BOULDER)})

    state = PokemonRedStateReader(memory).read_cerulean_chapter_state(raw)

    assert state.boundary is expected_boundary
    if expected_boundary is CeruleanBoundary.MT_MOON_B2F_ENTRY:
        assert state.phase is CeruleanPhase.MT_MOON_B2F_REACHED
        assert state.travel_boundary_snapshot
    else:
        assert state.phase is CeruleanPhase.UNKNOWN


@pytest.mark.parametrize(
    ("player_y", "expected_boundary"),
    [
        (5, CeruleanBoundary.UNKNOWN),
        (6, CeruleanBoundary.ROUTE_4_MT_MOON_EXIT),
    ],
    ids=["transient", "stable"],
)
def test_reader_accepts_only_stable_route_4_mt_moon_exit(
    player_y: int,
    expected_boundary: CeruleanBoundary,
) -> None:
    raw = RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_4,
        player_x=24,
        player_y=player_y,
        party_count=1,
        battle_state=0,
        badge_bits=int(Badge.BOULDER),
        bag_item_ids=(ItemId.TM34_BIDE, ItemId.DOME_FOSSIL),
        event_flags=_events(
            EventFlag.GOT_TM34,
            EventFlag.BEAT_BROCK,
            EventFlag.BEAT_ROUTE_3_TRAINER_0,
            EventFlag.BEAT_ROUTE_3_TRAINER_1,
            EventFlag.BEAT_ROUTE_3_TRAINER_3,
            EventFlag.BEAT_ROUTE_3_TRAINER_6,
            MT_MOON_REQUIRED_ROCKET_EVENT,
            EventFlag.BEAT_MT_MOON_EXIT_SUPER_NERD,
            EventFlag.GOT_DOME_FOSSIL,
        ),
        party_species_ids=(WARTORTLE_SPECIES_ID,),
        first_party_hp=30,
        first_party_max_hp=35,
        first_party_status=0,
        battle_result=0,
    )
    memory = Memory({RamAddress.BEAT_GYM_FLAGS: int(Badge.BOULDER)})

    state = PokemonRedStateReader(memory).read_cerulean_chapter_state(raw)

    assert state.boundary is expected_boundary
    if expected_boundary is CeruleanBoundary.ROUTE_4_MT_MOON_EXIT:
        assert state.phase is CeruleanPhase.MT_MOON_CLEARED
        assert state.travel_boundary_snapshot
    else:
        assert state.phase is CeruleanPhase.SUPER_NERD_DEFEATED
        assert not state.travel_boundary_snapshot


@pytest.mark.parametrize(
    ("player_y", "expected_boundary"),
    [
        (18, CeruleanBoundary.CERULEAN_WEST_ENTRY),
        (11, CeruleanBoundary.UNKNOWN),
    ],
)
def test_reader_uses_the_live_proven_cerulean_arrival(
    player_y: int,
    expected_boundary: CeruleanBoundary,
) -> None:
    raw = RawGameState(
        game_started=True,
        map_id=MapId.CERULEAN_CITY,
        player_x=0,
        player_y=player_y,
        party_count=1,
        battle_state=0,
        badge_bits=int(Badge.BOULDER),
        bag_item_ids=(ItemId.TM34_BIDE, ItemId.HELIX_FOSSIL),
        event_flags=_events(
            EventFlag.GOT_TM34,
            EventFlag.BEAT_BROCK,
            EventFlag.BEAT_ROUTE_3_TRAINER_0,
            EventFlag.BEAT_ROUTE_3_TRAINER_1,
            EventFlag.BEAT_ROUTE_3_TRAINER_3,
            EventFlag.BEAT_ROUTE_3_TRAINER_6,
            MT_MOON_REQUIRED_ROCKET_EVENT,
            EventFlag.BEAT_MT_MOON_EXIT_SUPER_NERD,
            EventFlag.GOT_HELIX_FOSSIL,
        ),
        party_species_ids=(WARTORTLE_SPECIES_ID,),
        first_party_hp=30,
        first_party_max_hp=35,
        first_party_status=0,
        battle_result=0,
    )
    memory = Memory({RamAddress.BEAT_GYM_FLAGS: int(Badge.BOULDER)})

    state = PokemonRedStateReader(memory).read_cerulean_chapter_state(raw)

    assert state.boundary is expected_boundary
    if expected_boundary is CeruleanBoundary.CERULEAN_WEST_ENTRY:
        assert state.phase is CeruleanPhase.CERULEAN_REACHED
        assert state.cerulean_snapshot
    else:
        assert state.phase is not CeruleanPhase.CERULEAN_REACHED
        assert not state.cerulean_snapshot


def test_reader_requires_rocket1_identity_trigger_and_event() -> None:
    route_events = (
        EventFlag.GOT_TM34,
        EventFlag.BEAT_BROCK,
        EventFlag.BEAT_ROUTE_3_TRAINER_0,
        EventFlag.BEAT_ROUTE_3_TRAINER_1,
        EventFlag.BEAT_ROUTE_3_TRAINER_3,
        EventFlag.BEAT_ROUTE_3_TRAINER_6,
    )
    raw = RawGameState(
        game_started=True,
        map_id=MapId.MT_MOON_B2F,
        player_x=MT_MOON_REQUIRED_ROCKET_TRIGGER_X,
        player_y=MT_MOON_REQUIRED_ROCKET_TRIGGER_Y,
        party_count=1,
        battle_state=2,
        badge_bits=int(Badge.BOULDER),
        bag_item_ids=(ItemId.TM34_BIDE,),
        event_flags=_events(*route_events),
        party_species_ids=(WARTORTLE_SPECIES_ID,),
        first_party_hp=30,
        first_party_max_hp=35,
        first_party_status=0,
        battle_result=0,
    )
    values = {
        RamAddress.MT_MOON_B2F_SCRIPT: 2,
        RamAddress.CURRENT_MAP_SCRIPT: 2,
        RamAddress.BEAT_GYM_FLAGS: int(Badge.BOULDER),
        RamAddress.CURRENT_OPPONENT: ROCKET_OPPONENT_ID,
        RamAddress.TRAINER_CLASS: ROCKET_TRAINER_CLASS_ID,
        RamAddress.TRAINER_NUMBER: MT_MOON_REQUIRED_ROCKET_TRAINER_NUMBER,
        RamAddress.ENGAGED_TRAINER_CLASS: ROCKET_OPPONENT_ID,
        RamAddress.ENGAGED_TRAINER_SET: MT_MOON_REQUIRED_ROCKET_TRAINER_NUMBER,
    }

    live = PokemonRedStateReader(Memory(values)).read_cerulean_chapter_state(raw)

    assert live.phase is CeruleanPhase.REQUIRED_ROCKET_BATTLE
    assert live.required_rocket_battle_snapshot
    assert not live.beat_required_rocket

    no_engagement_at_y20 = PokemonRedStateReader(
        Memory(values)
    ).read_cerulean_chapter_state(replace(raw, player_y=20))
    assert no_engagement_at_y20.phase is CeruleanPhase.UNKNOWN
    assert not no_engagement_at_y20.required_rocket_battle_snapshot

    wrong_engaged_set = PokemonRedStateReader(
        Memory({**values, RamAddress.ENGAGED_TRAINER_SET: 4})
    ).read_cerulean_chapter_state(raw)
    assert wrong_engaged_set.phase is CeruleanPhase.UNKNOWN
    assert not wrong_engaged_set.required_rocket_battle_snapshot

    rocket4_event = PokemonRedStateReader(
        Memory(values)
    ).read_cerulean_chapter_state(
        replace(
            raw,
            battle_state=0,
            event_flags=_events(
                *route_events,
                EventFlag.BEAT_MT_MOON_3_TRAINER_3,
            ),
        )
    )
    assert rocket4_event.phase is CeruleanPhase.UNKNOWN
    assert not rocket4_event.beat_required_rocket

    defeated = PokemonRedStateReader(Memory(values)).read_cerulean_chapter_state(
        replace(
            raw,
            battle_state=0,
            event_flags=_events(*route_events, MT_MOON_REQUIRED_ROCKET_EVENT),
        )
    )
    assert defeated.phase is CeruleanPhase.REQUIRED_ROCKET_DEFEATED
    assert defeated.beat_required_rocket


def test_fossil_proof_requires_exactly_one_matching_event_and_item() -> None:
    valid = replace(
        _chapter(),
        phase=CeruleanPhase.FOSSIL_OBTAINED,
        boundary=CeruleanBoundary.UNKNOWN,
        map_id=MapId.MT_MOON_B2F,
        player_x=12,
        player_y=7,
        beat_required_rocket=True,
        beat_super_nerd=True,
        got_dome_fossil=True,
        dome_fossil_in_bag=True,
        **ROUTE_3_DEFEATED,
    )

    assert valid.fossil_snapshot
    assert not replace(valid, dome_fossil_in_bag=False).fossil_snapshot
    assert not replace(
        valid,
        got_helix_fossil=True,
        helix_fossil_in_bag=True,
    ).fossil_snapshot
    assert not replace(
        valid,
        got_dome_fossil=False,
        dome_fossil_in_bag=False,
    ).fossil_snapshot


def test_tracker_requires_ordered_live_battles_before_stable_cerulean() -> None:
    tracker = CeruleanProgressTracker(_brock_victory())
    state = _at_boundary(_chapter(), BOUNDARY_STATES[0])
    tracker.observe(state)
    state = _observe_route_3_trainers(tracker, state)

    for boundary_state in BOUNDARY_STATES[1:]:
        state = _at_boundary(state, boundary_state)
        tracker.observe(state)

    rocket = replace(
        state,
        phase=CeruleanPhase.REQUIRED_ROCKET_BATTLE,
        boundary=CeruleanBoundary.UNKNOWN,
        player_x=MT_MOON_REQUIRED_ROCKET_TRIGGER_X,
        player_y=MT_MOON_REQUIRED_ROCKET_TRIGGER_Y,
        battle_state=2,
        local_script=2,
        current_map_script=2,
        current_opponent=ROCKET_OPPONENT_ID,
        trainer_class=ROCKET_TRAINER_CLASS_ID,
        trainer_number=MT_MOON_REQUIRED_ROCKET_TRAINER_NUMBER,
        engaged_trainer_class=ROCKET_OPPONENT_ID,
        engaged_trainer_set=MT_MOON_REQUIRED_ROCKET_TRAINER_NUMBER,
    )
    assert tracker.observe(rocket) is CeruleanPhase.REQUIRED_ROCKET_BATTLE

    nerd = replace(
        rocket,
        phase=CeruleanPhase.SUPER_NERD_BATTLE,
        beat_required_rocket=True,
        local_script=3,
        current_map_script=3,
        current_opponent=MT_MOON_SUPER_NERD_OPPONENT_ID,
        trainer_class=SUPER_NERD_TRAINER_CLASS_ID,
        trainer_number=MT_MOON_SUPER_NERD_TRAINER_NUMBER,
        engaged_trainer_class=MT_MOON_SUPER_NERD_OPPONENT_ID,
        engaged_trainer_set=MT_MOON_SUPER_NERD_TRAINER_NUMBER,
    )
    assert tracker.observe(nerd) is CeruleanPhase.SUPER_NERD_BATTLE

    fossil = replace(
        nerd,
        phase=CeruleanPhase.FOSSIL_OBTAINED,
        battle_state=0,
        local_script=0,
        current_map_script=0,
        beat_super_nerd=True,
        got_helix_fossil=True,
        helix_fossil_in_bag=True,
    )
    assert tracker.observe(fossil) is CeruleanPhase.FOSSIL_OBTAINED

    state = fossil
    for boundary_state in POST_FOSSIL_BOUNDARY_STATES:
        state = _at_boundary(state, boundary_state)
        tracker.observe(state)

    assert state.cerulean_snapshot
    assert tracker.reached_boundaries[-2:] == (
        CeruleanBoundary.ROUTE_4_MT_MOON_EXIT,
        CeruleanBoundary.CERULEAN_WEST_ENTRY,
    )
    assert tracker.fossil_obtained


def test_tracker_rejects_a_reordered_route_3_trainer_identity() -> None:
    tracker = CeruleanProgressTracker(_brock_victory())
    state = _chapter()
    tracker.observe(state)
    _, opponent, trainer_class, trainer_number = ROUTE_3_REQUIRED_TRAINER_SPECS[1]
    reordered = replace(
        state,
        phase=CeruleanPhase.ROUTE_3_TRAINER_BATTLE,
        boundary=CeruleanBoundary.UNKNOWN,
        battle_state=2,
        local_script=2,
        current_map_script=2,
        current_opponent=opponent,
        trainer_class=trainer_class,
        trainer_number=trainer_number,
        engaged_trainer_class=opponent,
        engaged_trainer_set=trainer_number,
    )

    with pytest.raises(CeruleanProgressError, match="skipped or reordered"):
        tracker.observe(reordered)


def test_tracker_rejects_destination_only_and_unlatched_fossil_evidence() -> None:
    tracker = CeruleanProgressTracker(_brock_victory())
    cerulean = replace(
        _chapter(),
        phase=CeruleanPhase.CERULEAN_REACHED,
        boundary=CeruleanBoundary.CERULEAN_WEST_ENTRY,
        map_id=MapId.CERULEAN_CITY,
        player_x=0,
        player_y=18,
        beat_required_rocket=True,
        beat_super_nerd=True,
        got_dome_fossil=True,
        dome_fossil_in_bag=True,
        **ROUTE_3_DEFEATED,
    )
    with pytest.raises(CeruleanProgressError, match="skipped"):
        tracker.observe(cerulean)

    state = _at_boundary(_chapter(), BOUNDARY_STATES[0])
    tracker.observe(state)
    state = _observe_route_3_trainers(tracker, state)
    for boundary_state in BOUNDARY_STATES[1:]:
        state = _at_boundary(state, boundary_state)
        tracker.observe(state)
    fossil = replace(
        _chapter(),
        phase=CeruleanPhase.FOSSIL_OBTAINED,
        boundary=CeruleanBoundary.UNKNOWN,
        map_id=MapId.MT_MOON_B2F,
        player_x=12,
        player_y=7,
        beat_required_rocket=True,
        beat_super_nerd=True,
        got_dome_fossil=True,
        dome_fossil_in_bag=True,
        **ROUTE_3_DEFEATED,
    )
    with pytest.raises(CeruleanProgressError, match="Super Nerd"):
        tracker.observe(fossil)
