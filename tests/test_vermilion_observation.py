from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.observation import (
    CERULEAN_ROCKET_TRAINER_NUMBER,
    ROCKET_OPPONENT_ID,
    ROCKET_TRAINER_CLASS_ID,
    ROUTE_6_JR_TRAINER_F_CLASS_ID,
    ROUTE_6_JR_TRAINER_F_NUMBER,
    ROUTE_6_JR_TRAINER_F_OPPONENT_ID,
    ROUTE_6_JR_TRAINER_M_CLASS_ID,
    ROUTE_6_JR_TRAINER_M_NUMBER,
    ROUTE_6_JR_TRAINER_M_OPPONENT_ID,
    WARTORTLE_SPECIES_ID,
    CascadePhase,
    CascadeState,
    InputReadiness,
    MapId,
    VermilionPhase,
    VermilionProgressError,
    VermilionProgressTracker,
    VermilionState,
)

READY = InputReadiness(
    joy_ignore=0,
    simulated_joypad_index=0,
    npc_movement_script_table=0,
    player_moving_direction=0,
    status_flags_5=0,
    movement_flags=0,
)
NO_ROUTE_6_TRAINERS = (False, False, False, False, False, False)


def _misty_victory() -> CascadeState:
    return CascadeState(
        phase=CascadePhase.MISTY_DEFEATED,
        controls=READY,
        local_script=0,
        current_map_script=0,
        prior_chapter_complete=True,
        beat_cerulean_rival=True,
        route_24_trainer_events=(True, True, True, True, True),
        got_nugget=True,
        nugget_in_bag=True,
        beat_route_24_rocket=True,
        route_25_trainer_events=(True, True, True, True),
        bill_said_use_cell_separator=True,
        used_cell_separator_on_bill=True,
        met_bill=True,
        met_bill_2=True,
        got_ss_ticket=True,
        ss_ticket_in_bag=True,
        left_bills_house_after_helping=True,
        beat_cerulean_gym_trainer_0=True,
        beat_misty=True,
        got_tm11=True,
        tm11_in_bag=True,
        cascade_badge=True,
        cascade_badge_mirror=True,
        current_opponent=0,
        trainer_class=0,
        trainer_number=0,
        engaged_trainer_class=0,
        engaged_trainer_set=0,
        gym_leader_number=0,
        map_id=MapId.CERULEAN_GYM,
        player_x=5,
        player_y=2,
        party_count=1,
        party_species_ids=(WARTORTLE_SPECIES_ID,),
        first_party_hp=4,
        first_party_max_hp=66,
        first_party_status=0,
        battle_state=0,
        battle_result=0,
    )


def _vermilion(**changes: object) -> VermilionState:
    state = VermilionState(
        phase=VermilionPhase.MISTY_READY,
        controls=READY,
        local_script=0,
        current_map_script=0,
        prior_chapter_complete=True,
        beat_rocket_thief=False,
        tm28_in_bag=False,
        route_6_trainer_events=NO_ROUTE_6_TRAINERS,
        current_opponent=0,
        trainer_class=0,
        trainer_number=0,
        engaged_trainer_class=0,
        engaged_trainer_set=0,
        map_id=MapId.CERULEAN_GYM,
        player_x=5,
        player_y=2,
        party_count=1,
        party_species_ids=(WARTORTLE_SPECIES_ID,),
        first_party_hp=4,
        first_party_max_hp=66,
        first_party_status=0,
        battle_state=0,
        battle_result=0,
    )
    return replace(state, **changes)


def _ordered_states() -> tuple[VermilionState, ...]:
    return (
        _vermilion(),
        _vermilion(
            phase=VermilionPhase.TRASHED_HOUSE_ENTERED,
            map_id=MapId.CERULEAN_TRASHED_HOUSE,
            player_x=2,
            player_y=7,
        ),
        _vermilion(
            phase=VermilionPhase.ROBBERY_REAR_EXIT,
            map_id=MapId.CERULEAN_CITY,
            player_x=27,
            player_y=9,
        ),
        _vermilion(
            phase=VermilionPhase.ROCKET_THIEF_BATTLE,
            map_id=MapId.CERULEAN_CITY,
            player_x=30,
            player_y=9,
            local_script=4,
            battle_state=2,
            current_opponent=ROCKET_OPPONENT_ID,
            trainer_class=ROCKET_TRAINER_CLASS_ID,
            trainer_number=CERULEAN_ROCKET_TRAINER_NUMBER,
            engaged_trainer_class=ROCKET_OPPONENT_ID,
            engaged_trainer_set=CERULEAN_ROCKET_TRAINER_NUMBER,
        ),
        _vermilion(
            phase=VermilionPhase.TM28_OBTAINED,
            map_id=MapId.CERULEAN_CITY,
            player_x=30,
            player_y=9,
            beat_rocket_thief=True,
            tm28_in_bag=True,
        ),
        _vermilion(
            phase=VermilionPhase.ROUTE_5_REACHED,
            map_id=MapId.ROUTE_5,
            player_x=3,
            player_y=0,
            beat_rocket_thief=True,
            tm28_in_bag=True,
        ),
        _vermilion(
            phase=VermilionPhase.UNDERGROUND_NORTH_ENTRANCE,
            map_id=MapId.UNDERGROUND_PATH_ROUTE_5,
            player_x=3,
            player_y=7,
            beat_rocket_thief=True,
            tm28_in_bag=True,
        ),
        _vermilion(
            phase=VermilionPhase.UNDERGROUND_TUNNEL,
            map_id=MapId.UNDERGROUND_PATH_NORTH_SOUTH,
            player_x=5,
            player_y=4,
            beat_rocket_thief=True,
            tm28_in_bag=True,
        ),
        _vermilion(
            phase=VermilionPhase.UNDERGROUND_SOUTH_ENTRANCE,
            map_id=MapId.UNDERGROUND_PATH_ROUTE_6,
            player_x=4,
            player_y=4,
            beat_rocket_thief=True,
            tm28_in_bag=True,
        ),
        _vermilion(
            phase=VermilionPhase.ROUTE_6_REACHED,
            map_id=MapId.ROUTE_6,
            player_x=17,
            player_y=14,
            beat_rocket_thief=True,
            tm28_in_bag=True,
        ),
        _vermilion(
            phase=VermilionPhase.ROUTE_6_TRAINER_F_BATTLE,
            map_id=MapId.ROUTE_6,
            player_x=9,
            player_y=30,
            local_script=2,
            current_map_script=2,
            battle_state=2,
            beat_rocket_thief=True,
            tm28_in_bag=True,
            current_opponent=ROUTE_6_JR_TRAINER_F_OPPONENT_ID,
            trainer_class=ROUTE_6_JR_TRAINER_F_CLASS_ID,
            trainer_number=ROUTE_6_JR_TRAINER_F_NUMBER,
            engaged_trainer_class=ROUTE_6_JR_TRAINER_F_OPPONENT_ID,
            engaged_trainer_set=ROUTE_6_JR_TRAINER_F_NUMBER,
        ),
        _vermilion(
            phase=VermilionPhase.ROUTE_6_TRAINER_F_DEFEATED,
            map_id=MapId.ROUTE_6,
            player_x=9,
            player_y=30,
            beat_rocket_thief=True,
            tm28_in_bag=True,
            route_6_trainer_events=(False, False, False, False, True, False),
        ),
        _vermilion(
            phase=VermilionPhase.ROUTE_6_TRAINER_M_BATTLE,
            map_id=MapId.ROUTE_6,
            player_x=9,
            player_y=31,
            local_script=2,
            current_map_script=2,
            battle_state=2,
            beat_rocket_thief=True,
            tm28_in_bag=True,
            route_6_trainer_events=(False, False, False, False, True, False),
            current_opponent=ROUTE_6_JR_TRAINER_M_OPPONENT_ID,
            trainer_class=ROUTE_6_JR_TRAINER_M_CLASS_ID,
            trainer_number=ROUTE_6_JR_TRAINER_M_NUMBER,
            engaged_trainer_class=ROUTE_6_JR_TRAINER_M_OPPONENT_ID,
            engaged_trainer_set=ROUTE_6_JR_TRAINER_M_NUMBER,
        ),
        _vermilion(
            phase=VermilionPhase.ROUTE_6_TRAINER_M_DEFEATED,
            map_id=MapId.ROUTE_6,
            player_x=9,
            player_y=31,
            beat_rocket_thief=True,
            tm28_in_bag=True,
            route_6_trainer_events=(False, False, False, True, True, False),
        ),
        _vermilion(
            phase=VermilionPhase.VERMILION_REACHED,
            map_id=MapId.VERMILION_CITY,
            player_x=19,
            player_y=0,
            beat_rocket_thief=True,
            tm28_in_bag=True,
            route_6_trainer_events=(False, False, False, True, True, False),
        ),
    )


def test_vermilion_tracker_accepts_the_complete_ordered_chain() -> None:
    tracker = VermilionProgressTracker(_misty_victory())

    for state in _ordered_states():
        assert tracker.observe(state) is state.phase

    assert tracker.saw_rocket_battle


def test_vermilion_tracker_rejects_a_skipped_boundary() -> None:
    tracker = VermilionProgressTracker(_misty_victory())
    tracker.observe(_ordered_states()[0])

    with pytest.raises(VermilionProgressError, match="skipped"):
        tracker.observe(_ordered_states()[2])


def test_vermilion_tracker_requires_the_live_rocket_battle() -> None:
    tracker = VermilionProgressTracker(_misty_victory())
    for state in _ordered_states()[:3]:
        tracker.observe(state)

    with pytest.raises(VermilionProgressError, match="skipped"):
        tracker.observe(_ordered_states()[4])


@pytest.mark.parametrize(
    "changes",
    (
        {"local_script": 0},
        {"current_map_script": 4},
        {"battle_state": 0},
        {"player_x": 29},
        {"player_y": 8},
        {"current_opponent": 0},
        {"trainer_class": 0},
        {"trainer_number": 4},
        {"engaged_trainer_class": 0},
        {"engaged_trainer_set": 4},
        {"beat_rocket_thief": True},
        {"tm28_in_bag": True},
    ),
)
def test_rocket_battle_requires_exact_live_identity(changes: dict[str, object]) -> None:
    battle = _ordered_states()[3]
    assert not replace(battle, **changes).rocket_thief_battle_snapshot


def test_tm28_requires_persistent_victory_and_inventory_evidence() -> None:
    obtained = _ordered_states()[4]

    assert obtained.tm28_snapshot
    assert not replace(obtained, beat_rocket_thief=False).tm28_snapshot
    assert not replace(obtained, tm28_in_bag=False).tm28_snapshot


def test_route_5_requires_the_live_cerulean_connection_coordinate() -> None:
    reached = _ordered_states()[5]

    assert reached.route_5_snapshot
    assert not replace(reached, player_x=10).route_5_snapshot
    assert not replace(reached, player_y=1).route_5_snapshot


def test_route_6_rejects_an_unexpected_trainer_event() -> None:
    reached = _ordered_states()[9]

    assert reached.route_6_snapshot
    assert not replace(
        reached,
        route_6_trainer_events=(True, False, False, False, False, False),
    ).route_6_snapshot


def test_route_6_battles_require_exact_live_identity_and_ordered_events() -> None:
    trainer_f = _ordered_states()[10]
    trainer_m = _ordered_states()[12]

    assert trainer_f.route_6_trainer_f_battle_snapshot
    assert not replace(
        trainer_f,
        trainer_number=ROUTE_6_JR_TRAINER_M_NUMBER,
    ).route_6_trainer_f_battle_snapshot
    assert trainer_m.route_6_trainer_m_battle_snapshot
    assert not replace(
        trainer_m,
        route_6_trainer_events=NO_ROUTE_6_TRAINERS,
    ).route_6_trainer_m_battle_snapshot


def test_vermilion_requires_stable_southbound_arrival() -> None:
    reached = _ordered_states()[-1]

    assert reached.vermilion_snapshot
    assert not replace(reached, map_id=MapId.ROUTE_6).vermilion_snapshot
    assert not replace(reached, player_y=1).vermilion_snapshot
    assert not replace(reached, battle_state=1).vermilion_snapshot


def test_vermilion_tracker_requires_verified_misty_start() -> None:
    with pytest.raises(VermilionProgressError, match="Misty victory"):
        VermilionProgressTracker(
            replace(_misty_victory(), cascade_badge_mirror=False)
        )
