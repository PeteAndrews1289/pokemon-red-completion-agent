from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from pokemon_red_completion.observation import (
    BULBASAUR_SPECIES_ID,
    CERULEAN_GYM_REQUIRED_TRAINER_NUMBER,
    CERULEAN_RIVAL_TRAINER_NUMBER,
    EVENT_FLAG_BYTES,
    JR_TRAINER_F_OPPONENT_ID,
    JR_TRAINER_F_TRAINER_CLASS_ID,
    MISTY_GYM_LEADER_NUMBER,
    MISTY_OPPONENT_ID,
    MISTY_TRAINER_CLASS_ID,
    MISTY_TRAINER_NUMBER,
    RIVAL1_OPPONENT_ID,
    RIVAL1_TRAINER_CLASS_ID,
    ROCKET_OPPONENT_ID,
    ROCKET_TRAINER_CLASS_ID,
    ROUTE_24_REQUIRED_TRAINER_SPECS,
    ROUTE_24_ROCKET_TRAINER_NUMBER,
    ROUTE_25_REQUIRED_TRAINER_SPECS,
    WARTORTLE_SPECIES_ID,
    ZUBAT_SPECIES_ID,
    Badge,
    CascadePhase,
    CascadeProgressError,
    CascadeProgressTracker,
    CascadeState,
    CeruleanBoundary,
    CeruleanChapterState,
    CeruleanPhase,
    EventFlag,
    InputReadiness,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
    _ss_anne_prior_chapter_complete,
    location_label,
)


@dataclass
class Memory:
    values: dict[int, int]

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


def _verified_cerulean() -> CeruleanChapterState:
    return CeruleanChapterState(
        phase=CeruleanPhase.CERULEAN_REACHED,
        boundary=CeruleanBoundary.CERULEAN_WEST_ENTRY,
        controls=READY,
        local_script=0,
        current_map_script=0,
        beat_brock=True,
        got_tm34=True,
        boulder_badge=True,
        boulder_badge_mirror=True,
        beat_route_3_trainer_0=True,
        beat_route_3_trainer_1=True,
        beat_route_3_trainer_3=True,
        beat_route_3_trainer_6=True,
        beat_required_rocket=True,
        beat_super_nerd=True,
        got_dome_fossil=False,
        got_helix_fossil=True,
        dome_fossil_in_bag=False,
        helix_fossil_in_bag=True,
        current_opponent=0,
        trainer_class=0,
        trainer_number=0,
        engaged_trainer_class=0,
        engaged_trainer_set=0,
        map_id=MapId.CERULEAN_CITY,
        player_x=0,
        player_y=18,
        party_count=1,
        party_species_ids=(WARTORTLE_SPECIES_ID,),
        first_party_hp=23,
        first_party_max_hp=49,
        first_party_status=0,
        battle_state=0,
        battle_result=0,
    )


def _cascade(**changes: object) -> CascadeState:
    values: dict[str, object] = {
        "phase": CascadePhase.CERULEAN_READY,
        "controls": READY,
        "local_script": 0,
        "current_map_script": 0,
        "prior_chapter_complete": True,
        "beat_cerulean_rival": False,
        "route_24_trainer_events": (False, False, False, False, False),
        "got_nugget": False,
        "nugget_in_bag": False,
        "beat_route_24_rocket": False,
        "route_25_trainer_events": (False, False, False, False),
        "bill_said_use_cell_separator": False,
        "used_cell_separator_on_bill": False,
        "met_bill": False,
        "met_bill_2": False,
        "got_ss_ticket": False,
        "ss_ticket_in_bag": False,
        "left_bills_house_after_helping": False,
        "beat_cerulean_gym_trainer_0": False,
        "beat_misty": False,
        "got_tm11": False,
        "tm11_in_bag": False,
        "cascade_badge": False,
        "cascade_badge_mirror": False,
        "current_opponent": 0,
        "trainer_class": 0,
        "trainer_number": 0,
        "engaged_trainer_class": 0,
        "engaged_trainer_set": 0,
        "gym_leader_number": 0,
        "map_id": MapId.CERULEAN_CITY,
        "player_x": 0,
        "player_y": 18,
        "party_count": 1,
        "party_species_ids": (WARTORTLE_SPECIES_ID,),
        "first_party_hp": 23,
        "first_party_max_hp": 49,
        "first_party_status": 0,
        "battle_state": 0,
        "battle_result": 0,
    }
    values.update(changes)
    return CascadeState(**values)  # type: ignore[arg-type]


def _rival_battle() -> CascadeState:
    return _cascade(
        phase=CascadePhase.RIVAL_BATTLE,
        local_script=2,
        battle_state=2,
        player_x=20,
        player_y=6,
        current_opponent=RIVAL1_OPPONENT_ID,
        trainer_class=RIVAL1_TRAINER_CLASS_ID,
        trainer_number=CERULEAN_RIVAL_TRAINER_NUMBER,
    )


def _rival_victory() -> CascadeState:
    return _cascade(
        phase=CascadePhase.RIVAL_DEFEATED,
        beat_cerulean_rival=True,
        player_x=20,
        player_y=6,
    )


def _route_24_battle(position: int) -> CascadeState:
    (
        _,
        _,
        opponent,
        trainer_class,
        trainer_number,
        player_x,
        player_y,
    ) = ROUTE_24_REQUIRED_TRAINER_SPECS[position]
    events = tuple(index < position for index in range(len(ROUTE_24_REQUIRED_TRAINER_SPECS)))
    return _cascade(
        phase=CascadePhase.ROUTE_24_TRAINER_BATTLE,
        beat_cerulean_rival=True,
        route_24_trainer_events=events,
        map_id=MapId.ROUTE_24,
        player_x=player_x,
        player_y=player_y,
        local_script=2,
        current_map_script=2,
        battle_state=2,
        current_opponent=opponent,
        trainer_class=trainer_class,
        trainer_number=trainer_number,
        engaged_trainer_class=opponent,
        engaged_trainer_set=trainer_number,
    )


ROUTE_24_ALL = (True, True, True, True, True)


def _nugget_rocket_battle() -> CascadeState:
    return _cascade(
        phase=CascadePhase.NUGGET_ROCKET_BATTLE,
        beat_cerulean_rival=True,
        route_24_trainer_events=ROUTE_24_ALL,
        got_nugget=True,
        nugget_in_bag=True,
        map_id=MapId.ROUTE_24,
        player_x=10,
        player_y=15,
        local_script=3,
        current_map_script=3,
        battle_state=2,
        current_opponent=ROCKET_OPPONENT_ID,
        trainer_class=ROCKET_TRAINER_CLASS_ID,
        trainer_number=ROUTE_24_ROCKET_TRAINER_NUMBER,
        engaged_trainer_class=ROCKET_OPPONENT_ID,
        engaged_trainer_set=ROUTE_24_ROCKET_TRAINER_NUMBER,
    )


def _nugget_rocket_victory() -> CascadeState:
    return replace(
        _nugget_rocket_battle(),
        phase=CascadePhase.NUGGET_ROCKET_DEFEATED,
        local_script=0,
        current_map_script=0,
        battle_state=0,
        beat_route_24_rocket=True,
    )


def _route_25_battle(position: int) -> CascadeState:
    (
        _,
        _,
        opponent,
        trainer_class,
        trainer_number,
        player_x,
        player_y,
    ) = ROUTE_25_REQUIRED_TRAINER_SPECS[position]
    events = tuple(index < position for index in range(len(ROUTE_25_REQUIRED_TRAINER_SPECS)))
    return _cascade(
        phase=CascadePhase.ROUTE_25_TRAINER_BATTLE,
        beat_cerulean_rival=True,
        route_24_trainer_events=ROUTE_24_ALL,
        got_nugget=True,
        nugget_in_bag=True,
        beat_route_24_rocket=True,
        route_25_trainer_events=events,
        map_id=MapId.ROUTE_25,
        player_x=player_x,
        player_y=player_y,
        local_script=2,
        current_map_script=2,
        battle_state=2,
        current_opponent=opponent,
        trainer_class=trainer_class,
        trainer_number=trainer_number,
        engaged_trainer_class=opponent,
        engaged_trainer_set=trainer_number,
    )


ROUTE_25_ALL = (True, True, True, True)


def _bill_state(phase: CascadePhase, **changes: object) -> CascadeState:
    values: dict[str, object] = {
        "phase": phase,
        "beat_cerulean_rival": True,
        "route_24_trainer_events": ROUTE_24_ALL,
        "got_nugget": True,
        "nugget_in_bag": True,
        "beat_route_24_rocket": True,
        "route_25_trainer_events": ROUTE_25_ALL,
        "map_id": MapId.BILLS_HOUSE,
        "player_x": 6,
        "player_y": 6,
    }
    values.update(changes)
    return _cascade(**values)


def _bill_requested() -> CascadeState:
    return _bill_state(
        CascadePhase.BILL_REQUESTED_HELP,
        local_script=3,
        bill_said_use_cell_separator=True,
    )


def _bill_separator_used() -> CascadeState:
    return _bill_state(
        CascadePhase.BILL_CELL_SEPARATOR_USED,
        local_script=4,
        bill_said_use_cell_separator=True,
        used_cell_separator_on_bill=True,
        player_x=1,
        player_y=5,
    )


def _bill_restored() -> CascadeState:
    return _bill_state(
        CascadePhase.BILL_RESTORED,
        bill_said_use_cell_separator=True,
        used_cell_separator_on_bill=True,
        met_bill=True,
        met_bill_2=True,
        player_x=1,
        player_y=5,
    )


def _ticket_obtained() -> CascadeState:
    return replace(
        _bill_restored(),
        phase=CascadePhase.SS_TICKET_OBTAINED,
        got_ss_ticket=True,
        ss_ticket_in_bag=True,
        player_x=4,
    )


def _bills_house_left() -> CascadeState:
    return replace(
        _ticket_obtained(),
        phase=CascadePhase.BILLS_HOUSE_LEFT,
        map_id=MapId.ROUTE_25,
        player_x=45,
        player_y=4,
        left_bills_house_after_helping=True,
    )


def _misty_battle() -> CascadeState:
    return replace(
        _cerulean_gym_trainer_victory(),
        phase=CascadePhase.MISTY_BATTLE,
        map_id=MapId.CERULEAN_GYM,
        player_x=5,
        player_y=2,
        local_script=3,
        current_map_script=0,
        battle_state=2,
        beat_misty=False,
        got_tm11=False,
        tm11_in_bag=False,
        cascade_badge=False,
        cascade_badge_mirror=False,
        current_opponent=MISTY_OPPONENT_ID,
        trainer_class=MISTY_TRAINER_CLASS_ID,
        trainer_number=MISTY_TRAINER_NUMBER,
        engaged_trainer_class=MISTY_OPPONENT_ID,
        engaged_trainer_set=MISTY_TRAINER_NUMBER,
        gym_leader_number=MISTY_GYM_LEADER_NUMBER,
    )


def _cerulean_gym_trainer_battle() -> CascadeState:
    return replace(
        _bills_house_left(),
        phase=CascadePhase.CERULEAN_GYM_TRAINER_BATTLE,
        map_id=MapId.CERULEAN_GYM,
        player_x=5,
        player_y=3,
        local_script=2,
        current_map_script=2,
        battle_state=2,
        current_opponent=JR_TRAINER_F_OPPONENT_ID,
        trainer_class=JR_TRAINER_F_TRAINER_CLASS_ID,
        trainer_number=CERULEAN_GYM_REQUIRED_TRAINER_NUMBER,
        engaged_trainer_class=JR_TRAINER_F_OPPONENT_ID,
        engaged_trainer_set=CERULEAN_GYM_REQUIRED_TRAINER_NUMBER,
    )


def _cerulean_gym_trainer_victory() -> CascadeState:
    return replace(
        _cerulean_gym_trainer_battle(),
        phase=CascadePhase.CERULEAN_GYM_TRAINER_DEFEATED,
        local_script=0,
        current_map_script=0,
        battle_state=0,
        beat_cerulean_gym_trainer_0=True,
    )


def _misty_victory() -> CascadeState:
    return replace(
        _misty_battle(),
        phase=CascadePhase.MISTY_DEFEATED,
        local_script=0,
        current_map_script=0,
        battle_state=0,
        beat_misty=True,
        got_tm11=True,
        tm11_in_bag=True,
        cascade_badge=True,
        cascade_badge_mirror=True,
    )


def _advance_to_route_24(tracker: CascadeProgressTracker) -> None:
    tracker.observe(_rival_battle())
    tracker.observe(_rival_victory())


def _advance_to_route_25(tracker: CascadeProgressTracker) -> None:
    _advance_to_route_24(tracker)
    for position in range(len(ROUTE_24_REQUIRED_TRAINER_SPECS)):
        tracker.observe(_route_24_battle(position))
    tracker.observe(_nugget_rocket_battle())
    tracker.observe(_nugget_rocket_victory())


def _advance_to_bill(tracker: CascadeProgressTracker) -> None:
    _advance_to_route_25(tracker)
    for position in range(len(ROUTE_25_REQUIRED_TRAINER_SPECS)):
        tracker.observe(_route_25_battle(position))


def test_bill_and_cascade_symbols_match_the_pinned_pokered_revision() -> None:
    assert RamAddress.ENEMY_SPECIES == 0xCFE5
    assert RamAddress.ENEMY_HP == 0xCFE6
    assert RamAddress.ENEMY_LEVEL == 0xCFF3
    assert RamAddress.ENEMY_MAX_HP == 0xCFF4
    assert RamAddress.PLAYER_ACCURACY_STAGE == 0xCD1E
    assert BULBASAUR_SPECIES_ID == 0x99
    assert RamAddress.ROUTE_24_SCRIPT == 0xD602
    assert RamAddress.ROUTE_25_SCRIPT == 0xD603
    assert RamAddress.BILLS_HOUSE_SCRIPT == 0xD661
    assert MapId.ROUTE_24 == 0x23
    assert MapId.ROUTE_25 == 0x24
    assert MapId.BILLS_HOUSE == 0x58
    assert EventFlag.GOT_NUGGET == 0x540
    assert EventFlag.BEAT_ROUTE_24_ROCKET == 0x541
    assert tuple(
        EventFlag(int(EventFlag.BEAT_ROUTE_24_TRAINER_0) + index) for index in range(6)
    ) == (
        EventFlag.BEAT_ROUTE_24_TRAINER_0,
        EventFlag.BEAT_ROUTE_24_TRAINER_1,
        EventFlag.BEAT_ROUTE_24_TRAINER_2,
        EventFlag.BEAT_ROUTE_24_TRAINER_3,
        EventFlag.BEAT_ROUTE_24_TRAINER_4,
        EventFlag.BEAT_ROUTE_24_TRAINER_5,
    )
    assert EventFlag.NUGGET_REWARD_AVAILABLE == 0x549
    assert EventFlag.MET_BILL == 0x550
    assert tuple(
        EventFlag(int(EventFlag.BEAT_ROUTE_25_TRAINER_0) + index) for index in range(9)
    ) == (
        EventFlag.BEAT_ROUTE_25_TRAINER_0,
        EventFlag.BEAT_ROUTE_25_TRAINER_1,
        EventFlag.BEAT_ROUTE_25_TRAINER_2,
        EventFlag.BEAT_ROUTE_25_TRAINER_3,
        EventFlag.BEAT_ROUTE_25_TRAINER_4,
        EventFlag.BEAT_ROUTE_25_TRAINER_5,
        EventFlag.BEAT_ROUTE_25_TRAINER_6,
        EventFlag.BEAT_ROUTE_25_TRAINER_7,
        EventFlag.BEAT_ROUTE_25_TRAINER_8,
    )
    assert EventFlag.USED_CELL_SEPARATOR_ON_BILL == 0x55B
    assert EventFlag.GOT_SS_TICKET == 0x55C
    assert EventFlag.MET_BILL_2 == 0x55D
    assert EventFlag.BILL_SAID_USE_CELL_SEPARATOR == 0x55E
    assert EventFlag.LEFT_BILLS_HOUSE_AFTER_HELPING == 0x55F
    assert ItemId.NUGGET == 0x31
    assert ItemId.SS_TICKET == 0x3F


def test_reader_exposes_active_enemy_bytes_as_neutral_big_endian_observations() -> None:
    memory = Memory(
        {
            RamAddress.STATUS_FLAGS_6: 1,
            RamAddress.IS_IN_BATTLE: 0,
            RamAddress.ENEMY_SPECIES: BULBASAUR_SPECIES_ID,
            RamAddress.ENEMY_HP: 0x01,
            int(RamAddress.ENEMY_HP) + 1: 0x23,
            RamAddress.ENEMY_LEVEL: 0x2A,
            RamAddress.ENEMY_MAX_HP: 0x04,
            int(RamAddress.ENEMY_MAX_HP) + 1: 0x56,
        }
    )

    raw = PokemonRedStateReader(memory).read()

    assert raw.battle_state == 0
    assert raw.enemy_species_id == BULBASAUR_SPECIES_ID
    assert raw.enemy_hp == 0x0123
    assert raw.enemy_level == 0x2A
    assert raw.enemy_max_hp == 0x0456


@pytest.mark.parametrize(
    ("map_id", "address", "value", "label"),
    [
        (MapId.ROUTE_24, RamAddress.ROUTE_24_SCRIPT, 2, "route_24"),
        (MapId.ROUTE_25, RamAddress.ROUTE_25_SCRIPT, 1, "route_25"),
        (MapId.BILLS_HOUSE, RamAddress.BILLS_HOUSE_SCRIPT, 5, "bills_house"),
    ],
)
def test_reader_routes_new_local_scripts_through_the_observation_adapter(
    map_id: MapId,
    address: RamAddress,
    value: int,
    label: str,
) -> None:
    reader = PokemonRedStateReader(Memory({address: value}))

    assert reader._local_script(map_id) == value
    assert location_label(map_id) == label


def test_selected_trainer_specs_match_the_collision_qualified_source_route() -> None:
    assert tuple(spec[0] for spec in ROUTE_24_REQUIRED_TRAINER_SPECS) == (
        5,
        4,
        3,
        2,
        1,
    )
    assert tuple(spec[1] for spec in ROUTE_24_REQUIRED_TRAINER_SPECS) == (
        EventFlag.BEAT_ROUTE_24_TRAINER_5,
        EventFlag.BEAT_ROUTE_24_TRAINER_4,
        EventFlag.BEAT_ROUTE_24_TRAINER_3,
        EventFlag.BEAT_ROUTE_24_TRAINER_2,
        EventFlag.BEAT_ROUTE_24_TRAINER_1,
    )
    assert tuple(spec[0] for spec in ROUTE_25_REQUIRED_TRAINER_SPECS) == (
        8,
        3,
        2,
        5,
    )
    assert tuple(spec[1] for spec in ROUTE_25_REQUIRED_TRAINER_SPECS) == (
        EventFlag.BEAT_ROUTE_25_TRAINER_8,
        EventFlag.BEAT_ROUTE_25_TRAINER_3,
        EventFlag.BEAT_ROUTE_25_TRAINER_2,
        EventFlag.BEAT_ROUTE_25_TRAINER_5,
    )


def test_cascade_tracker_qualifies_the_complete_ordered_evidence_chain() -> None:
    tracker = CascadeProgressTracker(_verified_cerulean())

    assert tracker.observe(_cascade()) is CascadePhase.CERULEAN_READY
    assert tracker.observe(_rival_battle()) is CascadePhase.RIVAL_BATTLE
    assert tracker.observe(_rival_battle()) is CascadePhase.RIVAL_BATTLE
    assert tracker.observe(_rival_victory()) is CascadePhase.RIVAL_DEFEATED

    for position in range(len(ROUTE_24_REQUIRED_TRAINER_SPECS)):
        assert tracker.observe(_route_24_battle(position)) is CascadePhase.ROUTE_24_TRAINER_BATTLE
    assert tracker.observed_route_24_trainers == (5, 4, 3, 2, 1)

    assert tracker.observe(_nugget_rocket_battle()) is CascadePhase.NUGGET_ROCKET_BATTLE
    assert tracker.observe(_nugget_rocket_victory()) is CascadePhase.NUGGET_ROCKET_DEFEATED

    for position in range(len(ROUTE_25_REQUIRED_TRAINER_SPECS)):
        assert tracker.observe(_route_25_battle(position)) is CascadePhase.ROUTE_25_TRAINER_BATTLE
    assert tracker.observed_route_25_trainers == (8, 3, 2, 5)

    assert tracker.observe(_bill_requested()) is CascadePhase.BILL_REQUESTED_HELP
    assert tracker.observe(_bill_separator_used()) is CascadePhase.BILL_CELL_SEPARATOR_USED
    assert tracker.observe(_bill_separator_used()) is CascadePhase.BILL_CELL_SEPARATOR_USED
    assert tracker.observe(_bill_restored()) is CascadePhase.BILL_RESTORED
    assert tracker.observe(_ticket_obtained()) is CascadePhase.SS_TICKET_OBTAINED
    assert tracker.observe(_bills_house_left()) is CascadePhase.BILLS_HOUSE_LEFT
    assert (
        tracker.observe(_cerulean_gym_trainer_battle()) is CascadePhase.CERULEAN_GYM_TRAINER_BATTLE
    )
    assert (
        tracker.observe(_cerulean_gym_trainer_victory())
        is CascadePhase.CERULEAN_GYM_TRAINER_DEFEATED
    )
    assert tracker.observe(_misty_battle()) is CascadePhase.MISTY_BATTLE
    assert tracker.observe(_misty_victory()) is CascadePhase.MISTY_DEFEATED

    assert tracker.saw_rival_battle
    assert tracker.rival_defeated
    assert tracker.saw_nugget_rocket_battle
    assert tracker.nugget_rocket_defeated
    assert tracker.bills_house_left
    assert tracker.saw_cerulean_gym_trainer_battle
    assert tracker.cerulean_gym_trainer_defeated
    assert tracker.saw_misty_battle
    assert tracker.misty_defeated


def test_cascade_tracker_requires_the_verified_cerulean_origin() -> None:
    with pytest.raises(CascadeProgressError, match="verified Cerulean"):
        CascadeProgressTracker(
            replace(
                _verified_cerulean(),
                boundary=CeruleanBoundary.UNKNOWN,
                player_x=1,
            )
        )


def test_rival_victory_cannot_qualify_without_live_identity() -> None:
    tracker = CascadeProgressTracker(_verified_cerulean())

    with pytest.raises(CascadeProgressError, match="observed live battle"):
        tracker.observe(_rival_victory())

    wrong_rival = replace(_rival_battle(), current_opponent=0xD9)
    with pytest.raises(CascadeProgressError, match="source-pinned"):
        tracker.observe(wrong_rival)


def test_rival_victory_accepts_only_the_exact_reserve_led_terminal() -> None:
    reserve_led = replace(
        _rival_victory(),
        party_count=2,
        party_species_ids=(WARTORTLE_SPECIES_ID, ZUBAT_SPECIES_ID),
        first_party_hp=0,
    )

    assert not reserve_led.stable_snapshot
    assert reserve_led.rival_victory_snapshot
    assert not replace(
        reserve_led,
        party_species_ids=(ZUBAT_SPECIES_ID, WARTORTLE_SPECIES_ID),
    ).rival_victory_snapshot
    assert not replace(reserve_led, party_count=1).rival_victory_snapshot
    assert not replace(reserve_led, first_party_max_hp=0).rival_victory_snapshot
    assert not replace(reserve_led, beat_cerulean_rival=False).rival_victory_snapshot
    assert not replace(reserve_led, battle_result=1).rival_victory_snapshot


def test_route_24_battles_fail_closed_on_reordering_and_unflipped_events() -> None:
    tracker = CascadeProgressTracker(_verified_cerulean())
    _advance_to_route_24(tracker)

    with pytest.raises(CascadeProgressError, match="skipped or reordered"):
        tracker.observe(_route_24_battle(1))

    tracker.observe(_route_24_battle(0))
    missing_prior_event = replace(
        _route_24_battle(1),
        route_24_trainer_events=(False, False, False, False, False),
    )
    with pytest.raises(CascadeProgressError, match="did not flip"):
        tracker.observe(missing_prior_event)


def test_nugget_and_rocket_are_one_concurrent_live_gate() -> None:
    tracker = CascadeProgressTracker(_verified_cerulean())
    _advance_to_route_24(tracker)
    for position in range(len(ROUTE_24_REQUIRED_TRAINER_SPECS)):
        tracker.observe(_route_24_battle(position))

    no_nugget_item = replace(_nugget_rocket_battle(), nugget_in_bag=False)
    with pytest.raises(CascadeProgressError, match="source-pinned"):
        tracker.observe(no_nugget_item)

    with pytest.raises(CascadeProgressError, match="observed live Rocket"):
        tracker.observe(_nugget_rocket_victory())


def test_route_25_selected_battles_are_ordered_not_all_nine_trainers() -> None:
    tracker = CascadeProgressTracker(_verified_cerulean())
    _advance_to_route_25(tracker)

    assert tracker.observe(_route_25_battle(0)) is CascadePhase.ROUTE_25_TRAINER_BATTLE
    with pytest.raises(CascadeProgressError, match="skipped or reordered"):
        tracker.observe(_route_25_battle(2))

    wrong_optional_hiker = replace(
        _route_25_battle(1),
        current_opponent=ROUTE_25_REQUIRED_TRAINER_SPECS[0][2],
        trainer_class=ROUTE_25_REQUIRED_TRAINER_SPECS[0][3],
        trainer_number=3,
        engaged_trainer_class=ROUTE_25_REQUIRED_TRAINER_SPECS[0][2],
        engaged_trainer_set=3,
    )
    with pytest.raises(CascadeProgressError, match="source-pinned"):
        tracker.observe(wrong_optional_hiker)


@pytest.mark.parametrize(
    ("skipped_state", "message"),
    [
        (_bill_separator_used(), "skipped the help request"),
        (_bill_restored(), "before the cell separator"),
        (_ticket_obtained(), "before Bill was restored"),
        (_bills_house_left(), "before the S.S. Ticket"),
    ],
)
def test_bill_event_transitions_cannot_be_skipped(
    skipped_state: CascadeState, message: str
) -> None:
    tracker = CascadeProgressTracker(_verified_cerulean())
    _advance_to_bill(tracker)

    with pytest.raises(CascadeProgressError, match=message):
        tracker.observe(skipped_state)


def test_misty_requires_bill_exit_live_identity_and_exact_rewards() -> None:
    tracker = CascadeProgressTracker(_verified_cerulean())
    _advance_to_bill(tracker)
    tracker.observe(_bill_requested())
    tracker.observe(_bill_separator_used())
    tracker.observe(_bill_restored())
    tracker.observe(_ticket_obtained())
    tracker.observe(_bills_house_left())

    with pytest.raises(CascadeProgressError, match="required Cerulean Gym trainer"):
        tracker.observe(_misty_battle())

    tracker.observe(_cerulean_gym_trainer_battle())
    tracker.observe(_cerulean_gym_trainer_victory())

    wrong_misty = replace(_misty_battle(), gym_leader_number=1)
    with pytest.raises(CascadeProgressError, match="source-pinned"):
        tracker.observe(wrong_misty)

    with pytest.raises(CascadeProgressError, match="observed live battle"):
        tracker.observe(_misty_victory())

    tracker.observe(_misty_battle())
    no_tm_item = replace(_misty_victory(), tm11_in_bag=False)
    with pytest.raises(CascadeProgressError, match="source-pinned"):
        tracker.observe(no_tm_item)


FOUNDATION_EVENTS = (
    EventFlag.GOT_TM34,
    EventFlag.BEAT_BROCK,
    EventFlag.BEAT_ROUTE_3_TRAINER_0,
    EventFlag.BEAT_ROUTE_3_TRAINER_1,
    EventFlag.BEAT_ROUTE_3_TRAINER_3,
    EventFlag.BEAT_ROUTE_3_TRAINER_6,
    EventFlag.BEAT_MT_MOON_3_TRAINER_0,
    EventFlag.BEAT_MT_MOON_EXIT_SUPER_NERD,
    EventFlag.GOT_HELIX_FOSSIL,
)


def _raw(
    *,
    map_id: MapId,
    player_x: int,
    player_y: int,
    battle_state: int,
    events: tuple[EventFlag, ...] = FOUNDATION_EVENTS,
    items: tuple[ItemId, ...] = (ItemId.HELIX_FOSSIL,),
    badges: Badge = Badge.BOULDER,
) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=map_id,
        player_x=player_x,
        player_y=player_y,
        party_count=1,
        battle_state=battle_state,
        badge_bits=int(badges),
        bag_item_ids=items,
        event_flags=_events(*events),
        party_species_ids=(WARTORTLE_SPECIES_ID,),
        first_party_hp=23,
        first_party_max_hp=49,
        first_party_status=0,
        battle_result=0,
    )


def test_reader_detects_the_live_cerulean_rival_without_trusting_stale_engagement() -> None:
    memory = Memory(
        {
            RamAddress.BEAT_GYM_FLAGS: int(Badge.BOULDER),
            RamAddress.CERULEAN_CITY_SCRIPT: 2,
            RamAddress.CURRENT_OPPONENT: RIVAL1_OPPONENT_ID,
            RamAddress.TRAINER_CLASS: RIVAL1_TRAINER_CLASS_ID,
            RamAddress.TRAINER_NUMBER: CERULEAN_RIVAL_TRAINER_NUMBER,
            # The custom rival script does not populate these generic fields.
            RamAddress.ENGAGED_TRAINER_CLASS: 0xD0,
            RamAddress.ENGAGED_TRAINER_SET: 2,
        }
    )
    raw = _raw(
        map_id=MapId.CERULEAN_CITY,
        player_x=20,
        player_y=6,
        battle_state=2,
    )

    state = PokemonRedStateReader(memory).read_cascade_state(raw)

    assert state.phase is CascadePhase.RIVAL_BATTLE
    assert state.rival_battle_snapshot


def test_reader_requires_all_misty_rewards_and_both_badge_mirrors() -> None:
    completed_events = FOUNDATION_EVENTS + (
        EventFlag.BEAT_CERULEAN_RIVAL,
        EventFlag.BEAT_ROUTE_24_TRAINER_5,
        EventFlag.BEAT_ROUTE_24_TRAINER_4,
        EventFlag.BEAT_ROUTE_24_TRAINER_3,
        EventFlag.BEAT_ROUTE_24_TRAINER_2,
        EventFlag.BEAT_ROUTE_24_TRAINER_1,
        EventFlag.GOT_NUGGET,
        EventFlag.BEAT_ROUTE_24_ROCKET,
        EventFlag.BEAT_ROUTE_25_TRAINER_8,
        EventFlag.BEAT_ROUTE_25_TRAINER_3,
        EventFlag.BEAT_ROUTE_25_TRAINER_2,
        EventFlag.BEAT_ROUTE_25_TRAINER_5,
        EventFlag.BILL_SAID_USE_CELL_SEPARATOR,
        EventFlag.USED_CELL_SEPARATOR_ON_BILL,
        EventFlag.MET_BILL,
        EventFlag.MET_BILL_2,
        EventFlag.GOT_SS_TICKET,
        EventFlag.LEFT_BILLS_HOUSE_AFTER_HELPING,
        EventFlag.BEAT_CERULEAN_GYM_TRAINER_0,
        EventFlag.BEAT_MISTY,
        EventFlag.GOT_TM11,
    )
    raw = _raw(
        map_id=MapId.CERULEAN_GYM,
        player_x=4,
        player_y=3,
        battle_state=0,
        events=completed_events,
        items=(
            ItemId.HELIX_FOSSIL,
            ItemId.NUGGET,
            ItemId.SS_TICKET,
            ItemId.TM11_BUBBLEBEAM,
        ),
        badges=Badge.BOULDER | Badge.CASCADE,
    )
    memory = Memory(
        {
            RamAddress.BEAT_GYM_FLAGS: int(Badge.BOULDER | Badge.CASCADE),
            RamAddress.CERULEAN_GYM_SCRIPT: 0,
        }
    )

    state = PokemonRedStateReader(memory).read_cascade_state(raw)
    assert state.phase is CascadePhase.MISTY_DEFEATED
    assert state.misty_victory_snapshot

    missing_tm = replace(
        raw,
        bag_item_ids=(
            ItemId.HELIX_FOSSIL,
            ItemId.NUGGET,
            ItemId.SS_TICKET,
        ),
    )
    assert (
        PokemonRedStateReader(memory).read_cascade_state(missing_tm).phase is CascadePhase.UNKNOWN
    )

    one_badge_mirror = Memory(
        {
            RamAddress.BEAT_GYM_FLAGS: int(Badge.BOULDER),
            RamAddress.CERULEAN_GYM_SCRIPT: 0,
        }
    )
    assert (
        PokemonRedStateReader(one_badge_mirror).read_cascade_state(raw).phase
        is CascadePhase.UNKNOWN
    )


def test_ss_anne_foundation_accepts_tm11_consumed_into_bubblebeam() -> None:
    events = FOUNDATION_EVENTS + (
        EventFlag.BEAT_CERULEAN_RIVAL,
        EventFlag.GOT_NUGGET,
        EventFlag.BEAT_ROUTE_24_ROCKET,
        EventFlag.BILL_SAID_USE_CELL_SEPARATOR,
        EventFlag.USED_CELL_SEPARATOR_ON_BILL,
        EventFlag.MET_BILL,
        EventFlag.MET_BILL_2,
        EventFlag.GOT_SS_TICKET,
        EventFlag.LEFT_BILLS_HOUSE_AFTER_HELPING,
        EventFlag.BEAT_CERULEAN_GYM_TRAINER_0,
        EventFlag.GOT_TM11,
        EventFlag.BEAT_MISTY,
        EventFlag.BEAT_CERULEAN_ROCKET_THIEF,
        EventFlag.BEAT_ROUTE_6_TRAINER_3,
        EventFlag.BEAT_ROUTE_6_TRAINER_4,
    )
    raw = replace(
        _raw(
            map_id=MapId.VERMILION_DOCK,
            player_x=14,
            player_y=0,
            battle_state=0,
            events=events,
            items=(ItemId.HELIX_FOSSIL, ItemId.SS_TICKET, ItemId.TM28_DIG),
            badges=Badge.BOULDER | Badge.CASCADE,
        ),
        first_party_moves=(0x2C, 0x27, 0x3D, 0x37),
    )

    assert _ss_anne_prior_chapter_complete(
        raw,
        set(raw.bag_item_ids or ()),
        int(Badge.BOULDER | Badge.CASCADE),
    )
