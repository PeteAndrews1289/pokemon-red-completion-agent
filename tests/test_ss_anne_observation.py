from dataclasses import FrozenInstanceError, fields, replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.ss_anne as ss_anne
from pokemon_red_completion.observation import (
    RIVAL2_OPPONENT_ID,
    RIVAL2_TRAINER_CLASS_ID,
    SS_ANNE_RIVAL_ENGAGED_CLASS,
    SS_ANNE_RIVAL_ENGAGED_SET,
    SS_ANNE_RIVAL_TRAINER_NUMBER,
    WARTORTLE_SPECIES_ID,
    InputReadiness,
    MapId,
    SSAnnePhase,
    SSAnneProgressError,
    SSAnneProgressTracker,
    SSAnneState,
)

READY = InputReadiness(0, 0, 0, 0, 0, 0)


def _state(**changes: object) -> SSAnneState:
    state = SSAnneState(
        phase=SSAnnePhase.VERMILION_READY,
        controls=READY,
        local_script=0,
        current_map_script=0,
        prior_chapter_complete=True,
        rubbed_captains_back=False,
        got_hm01=False,
        hm01_in_bag=False,
        cut_fact=False,
        current_opponent=0,
        trainer_class=0,
        trainer_number=0,
        engaged_trainer_class=0,
        engaged_trainer_set=0,
        map_id=MapId.VERMILION_CITY,
        player_x=19,
        player_y=0,
        party_count=1,
        party_species_ids=(WARTORTLE_SPECIES_ID,),
        first_party_hp=69,
        first_party_max_hp=69,
        first_party_status=0,
        first_party_pp=(25, 30, 30, 25),
        battle_state=0,
        battle_result=0,
    )
    return replace(state, **changes)


def _ordered_states() -> tuple[SSAnneState, ...]:
    return (
        _state(),
        _state(
            phase=SSAnnePhase.HEALED,
            map_id=MapId.VERMILION_POKECENTER,
            player_x=3,
            player_y=3,
        ),
        _state(
            phase=SSAnnePhase.DOCK_REACHED,
            map_id=MapId.VERMILION_DOCK,
            player_x=14,
            player_y=0,
        ),
        _state(
            phase=SSAnnePhase.SHIP_1F_REACHED,
            map_id=MapId.SS_ANNE_1F,
            player_x=27,
            player_y=0,
        ),
        _state(
            phase=SSAnnePhase.SHIP_2F_REACHED,
            map_id=MapId.SS_ANNE_2F,
            player_x=2,
            player_y=4,
        ),
        _state(
            phase=SSAnnePhase.RIVAL_BATTLE,
            map_id=MapId.SS_ANNE_2F,
            player_x=36,
            player_y=8,
            local_script=2,
            battle_state=2,
            current_opponent=RIVAL2_OPPONENT_ID,
            trainer_class=RIVAL2_TRAINER_CLASS_ID,
            trainer_number=SS_ANNE_RIVAL_TRAINER_NUMBER,
            engaged_trainer_class=SS_ANNE_RIVAL_ENGAGED_CLASS,
            engaged_trainer_set=SS_ANNE_RIVAL_ENGAGED_SET,
        ),
        _state(
            phase=SSAnnePhase.RIVAL_DEFEATED,
            map_id=MapId.SS_ANNE_2F,
            player_x=36,
            player_y=8,
            local_script=4,
            first_party_hp=12,
            first_party_max_hp=71,
            first_party_pp=(14, 30, 30, 25),
        ),
        _state(
            phase=SSAnnePhase.CAPTAIN_ROOM_REACHED,
            map_id=MapId.SS_ANNE_CAPTAINS_ROOM,
            player_x=0,
            player_y=7,
            first_party_hp=12,
            first_party_max_hp=71,
            first_party_pp=(14, 30, 30, 25),
        ),
        _state(
            phase=SSAnnePhase.HM01_OBTAINED,
            map_id=MapId.SS_ANNE_CAPTAINS_ROOM,
            player_x=4,
            player_y=3,
            first_party_hp=12,
            first_party_max_hp=71,
            first_party_pp=(14, 30, 30, 25),
            rubbed_captains_back=True,
            got_hm01=True,
            hm01_in_bag=True,
            cut_fact=True,
        ),
    )


def test_tracker_accepts_all_nine_source_ordered_boundaries() -> None:
    tracker = SSAnneProgressTracker(SimpleNamespace(vermilion_snapshot=True))

    assert [tracker.observe(state) for state in _ordered_states()] == [
        state.phase for state in _ordered_states()
    ]
    assert tracker.saw_rival_battle


@pytest.mark.parametrize(
    ("changes", "missing"),
    (
        ({"got_hm01": False}, "got event"),
        ({"hm01_in_bag": False}, "bag item"),
        ({"cut_fact": False}, "semantic fact"),
        ({"rubbed_captains_back": False}, "rub event"),
    ),
)
def test_hm01_boundary_requires_all_four_concurrent_fields(
    changes: dict[str, object], missing: str
) -> None:
    final = replace(_ordered_states()[-1], **changes)

    assert not final.hm01_snapshot, missing


def test_rub_only_is_explicitly_not_an_hm01_boundary() -> None:
    rubbed_only = replace(
        _ordered_states()[-1],
        got_hm01=False,
        hm01_in_bag=False,
        cut_fact=False,
    )
    tracker = SSAnneProgressTracker(SimpleNamespace(vermilion_snapshot=True))
    for state in _ordered_states()[:-1]:
        tracker.observe(state)

    with pytest.raises(SSAnneProgressError, match="semantic snapshot"):
        tracker.observe(rubbed_only)


def test_rival_victory_cannot_be_inferred_without_live_battle() -> None:
    tracker = SSAnneProgressTracker(SimpleNamespace(vermilion_snapshot=True))
    for state in _ordered_states()[:5]:
        tracker.observe(state)

    with pytest.raises(SSAnneProgressError, match="skipped"):
        tracker.observe(_ordered_states()[6])


@pytest.mark.parametrize(
    ("species", "slot"),
    (
        (ss_anne.PIDGEOTTO_SPECIES_ID, 3),
        (ss_anne.RATICATE_SPECIES_ID, 4),
        (ss_anne.KADABRA_SPECIES_ID, 1),
        (ss_anne.IVYSAUR_SPECIES_ID, 3),
    ),
)
def test_ss_anne_rival_policy_uses_the_live_qualified_species_mapping(
    species: int,
    slot: int,
) -> None:
    state = ss_anne.RawGameState(
        game_started=True,
        map_id=MapId.SS_ANNE_2F,
        player_x=36,
        player_y=8,
        party_count=1,
        battle_state=2,
        enemy_species_id=species,
        first_party_moves=(0x2C, 0x27, 0x05, 0x37),
        first_party_pp=(25, 30, 20, 25),
    )

    assert ss_anne._choose_ss_anne_rival_move(state) == slot


def test_ss_anne_rival_policy_rejects_missing_move_evidence() -> None:
    state = ss_anne.RawGameState(
        game_started=True,
        map_id=MapId.SS_ANNE_2F,
        player_x=36,
        player_y=8,
        party_count=1,
        battle_state=2,
        enemy_species_id=ss_anne.RATICATE_SPECIES_ID,
        first_party_moves=(0x21, 0x27, 0, 0),
        first_party_pp=(35, 30, 20, 0),
    )

    with pytest.raises(ss_anne.SSAnneChapterError, match="usable ranked attack"):
        ss_anne._choose_ss_anne_rival_move(state)


@pytest.mark.parametrize(
    ("species", "disabled_slot", "fallback_slot"),
    (
        (ss_anne.PIDGEOTTO_SPECIES_ID, 3, 4),
        (ss_anne.RATICATE_SPECIES_ID, 4, 3),
        (ss_anne.KADABRA_SPECIES_ID, 1, 3),
        (ss_anne.IVYSAUR_SPECIES_ID, 3, 1),
    ),
)
def test_ss_anne_rival_policy_falls_back_from_a_disabled_preferred_move(
    species: int,
    disabled_slot: int,
    fallback_slot: int,
) -> None:
    state = ss_anne.RawGameState(
        game_started=True,
        map_id=MapId.SS_ANNE_2F,
        player_x=36,
        player_y=8,
        party_count=1,
        battle_state=2,
        enemy_species_id=species,
        first_party_moves=(0x2C, 0x27, 0x05, 0x37),
        first_party_pp=(25, 30, 20, 25),
        player_disabled_move_slot=disabled_slot,
        player_disable_turns=4,
    )

    assert ss_anne._choose_ss_anne_rival_move(state) == fallback_slot


def test_live_route_constants_preserve_only_confirmed_corridors() -> None:
    assert ss_anne._directions("DDDLDDLLLLLLLUU") == ss_anne.VERMILION_TO_CENTER_DIRECTIONS
    assert ss_anne._directions(
        "D" * 7 + "R" + "D" + "R" * 31 + "U" * 2 + "R" * 2 + "U" * 2
    ) == ss_anne.SHIP_2F_TO_RIVAL_DIRECTIONS
    assert ss_anne._directions("UUUU") == ss_anne.RIVAL_TO_CAPTAIN_ROOM_DIRECTIONS
    assert ss_anne._directions("UUURRRUR") == ss_anne.CAPTAIN_APPROACH_DIRECTIONS


def test_ss_anne_timing_is_positive_bounded_and_immutable() -> None:
    timing = ss_anne.DEFAULT_SS_ANNE_TIMING

    assert timing == ss_anne.SSAnneTiming()
    for field in fields(ss_anne.SSAnneTiming):
        if field.name == "battle_runtime":
            continue
        value = getattr(timing, field.name)
        assert isinstance(value, int) and not isinstance(value, bool) and value > 0
    with pytest.raises(FrozenInstanceError):
        timing.rival_intro_pulses = 0  # type: ignore[misc]


@pytest.mark.parametrize("invalid", (0, -1, True, 1.5))
def test_ss_anne_timing_rejects_unbounded_values(invalid: object) -> None:
    for field in fields(ss_anne.SSAnneTiming):
        if field.name == "battle_runtime":
            continue
        with pytest.raises(ValueError, match=f"{field.name} must be a positive integer"):
            replace(
                ss_anne.DEFAULT_SS_ANNE_TIMING,
                **{field.name: invalid},
            )


def test_report_requires_all_records_rival_latch_and_released_controller() -> None:
    final_evidence = _ordered_states()[-1]
    raw = ss_anne.RawGameState(
        True,
        MapId.SS_ANNE_CAPTAINS_ROOM,
        4,
        3,
        1,
        0,
    )
    records = tuple(
        ss_anne.SSAnneCheckpoint(str(index), str(index), raw, final_evidence)
        for index in range(ss_anne.SS_ANNE_CHECKPOINT_COUNT)
    )
    report = ss_anne.SSAnneChapterReport(
        records=records,
        final_raw=raw,
        final_evidence=final_evidence,
        saw_rival_battle=True,
        frames_executed=29_005,
        actions_executed=410,
        controller_released=True,
    )

    assert report.passed
    assert not replace(report, saw_rival_battle=False).passed
    assert not replace(report, controller_released=False).passed
    assert not replace(report, records=records[:-1]).passed
