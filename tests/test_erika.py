from dataclasses import fields, replace

import pytest

import pokemon_red_completion.erika as erika_module
from pokemon_red_completion.erika import (
    BLASTOISE_SPECIES_ID,
    DEFAULT_ERIKA_TIMING,
    ERIKA_CHECKPOINT_COUNT,
    ERIKA_CLASS,
    ERIKA_OPPONENT,
    MOVEMENT_RETRY_WAIT_FRAMES,
    STRENGTH,
    ErikaChapterReport,
    ErikaCheckpoint,
    ErikaTiming,
)
from pokemon_red_completion.observation import Badge, ItemId, MapId, RawGameState
from pokemon_red_completion.tower import TOWER_FINAL_PARTY


def _terminal() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.CELADON_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=3,
        battle_state=0,
        badge_bits=0x1F,
        party_species_ids=TOWER_FINAL_PARTY,
        first_party_level=42,
        first_party_hp=130,
        first_party_max_hp=130,
        first_party_status=0,
        first_party_moves=(0x82, STRENGTH, 0x3A, 0x39),
        first_party_pp=(15, 15, 10, 15),
    )


def test_erika_timing_is_positive_and_bounded() -> None:
    assert MOVEMENT_RETRY_WAIT_FRAMES == 12
    assert DEFAULT_ERIKA_TIMING.movement_retries == 16
    assert all(
        isinstance(getattr(DEFAULT_ERIKA_TIMING, field.name), int)
        and getattr(DEFAULT_ERIKA_TIMING, field.name) > 0
        for field in fields(ErikaTiming)
    )
    for field in fields(ErikaTiming):
        with pytest.raises(ValueError, match=field.name):
            replace(DEFAULT_ERIKA_TIMING, **{field.name: 0})


def test_erika_report_qualifies_tm40_move_learning_and_terminal() -> None:
    raw = _terminal()
    report = ErikaChapterReport(
        records=tuple(
            ErikaCheckpoint(str(index), str(index), raw) for index in range(ERIKA_CHECKPOINT_COUNT)
        ),
        final_raw=raw,
        erika_identity=(ERIKA_OPPONENT, ERIKA_CLASS, ERIKA_OPPONENT, 1),
        strength_pp_spent=0,
        ice_beam_pp_spent=3,
        got_tm13=True,
        tm13_transfer_before_event=True,
        moves_before=(0x2C, STRENGTH, 0x3D, 0x39),
        moves_after=(0x82, STRENGTH, 0x3A, 0x39),
        money_before=28_191,
        money_after=32_047,
        badge_bits=0x1F,
        beat_gym_flags=int(
            Badge.BOULDER | Badge.CASCADE | Badge.THUNDER | Badge.RAINBOW | Badge.SOUL
        ),
        got_tm21=True,
        beat_erika=True,
        gym_events_before=(False,) * 7,
        gym_events_after=(True,) * 7,
        optional_route_events_before=(False,) * 20,
        optional_route_events_after=(False,) * 20,
        final_bag=((int(ItemId.TM21_MEGA_DRAIN), 1),),
        party_hp=(130, 47, 40),
        party_max_hp=(130, 47, 40),
        party_status=(0, 0, 0),
        frames_executed=1,
        actions_executed=1,
        controller_released=True,
    )

    assert report.passed
    learning = report.public_dict()["erika"]["skull_bash_preparation"]
    assert learning == {
        "source": "Safari Zone North TM40",
        "slot": 1,
        "replaced_move_id": 0x2C,
        "learned_move_id": 0x82,
        "moves_before": [0x2C, STRENGTH, 0x3D, 0x39],
        "moves_after": [0x82, STRENGTH, 0x3A, 0x39],
        "learned_move_pp": 15,
    }


def test_erika_report_accepts_post_battle_level_and_rejects_incomplete_heal() -> None:
    raw = replace(
        _terminal(),
        first_party_level=43,
        first_party_hp=133,
        first_party_max_hp=133,
    )
    report = ErikaChapterReport(
        records=tuple(
            ErikaCheckpoint(str(index), str(index), raw) for index in range(ERIKA_CHECKPOINT_COUNT)
        ),
        final_raw=raw,
        erika_identity=(ERIKA_OPPONENT, ERIKA_CLASS, ERIKA_OPPONENT, 1),
        strength_pp_spent=0,
        ice_beam_pp_spent=3,
        got_tm13=True,
        tm13_transfer_before_event=True,
        moves_before=(0x2C, STRENGTH, 0x3D, 0x39),
        moves_after=(0x82, STRENGTH, 0x3A, 0x39),
        money_before=28_191,
        money_after=32_047,
        badge_bits=0x1F,
        beat_gym_flags=int(
            Badge.BOULDER | Badge.CASCADE | Badge.THUNDER | Badge.RAINBOW | Badge.SOUL
        ),
        got_tm21=True,
        beat_erika=True,
        gym_events_before=(False,) * 7,
        gym_events_after=(True,) * 7,
        optional_route_events_before=(False,) * 20,
        optional_route_events_after=(False,) * 20,
        final_bag=((int(ItemId.TM21_MEGA_DRAIN), 1),),
        party_hp=(133, 47, 40),
        party_max_hp=(133, 47, 40),
        party_status=(0, 0, 0),
        frames_executed=1,
        actions_executed=1,
        controller_released=True,
    )

    assert report.passed
    assert not replace(report, party_hp=(132, 47, 40)).passed


def test_erika_policy_falls_back_when_strength_is_disabled() -> None:
    raw = replace(
        _terminal(),
        battle_state=2,
        player_disabled_move_slot=2,
    )

    assert erika_module._erika_move_slot(raw) == 3


def test_route_training_handles_transformed_ditto_and_requires_safe_health() -> None:
    raw = replace(
        _terminal(),
        battle_state=1,
        enemy_species_id=BLASTOISE_SPECIES_ID,
        active_party_index=0,
        active_party_hp=93,
        active_party_max_hp=123,
        active_party_moves=(0x2C, STRENGTH, 0x3D, 0x39),
        active_party_pp=(25, 15, 20, 4),
    )

    assert erika_module._route_training_safe(raw)
    assert erika_module._route_training_move_slot(raw) == 2
    assert not erika_module._route_training_safe(replace(raw, active_party_hp=92))
