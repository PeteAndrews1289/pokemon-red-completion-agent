from dataclasses import replace

from pokemon_red_completion.champion import (
    CHAMPION_ARCANINE_FINISH_SAFE_HP,
    CHAMPION_CHECKPOINT_COUNT,
    CHAMPION_FORCED_SWITCH_LIMIT,
    CHAMPION_FULL_RESTORE_INPUT_RESERVE,
    CHAMPION_GYARADOS_FINISH_SAFE_HP,
    CHAMPION_PARTY,
    CHAMPION_RHYDON_SAFE_HP,
    CHAMPION_RNG_DELAY_FRAMES,
    CHAMPION_SAFE_HP,
    ChampionChapterReport,
    ChampionCheckpoint,
    ChampionTurn,
    _champion_forced_switch_target,
    _champion_move_slot,
    _champion_recovery_available,
    _champion_recovery_threshold,
    _encounter_party,
    _select_recovery_item,
    _turns_valid,
)
from pokemon_red_completion.observation import EventFlag, ItemId, MapId, RawGameState


def _events(*flags: EventFlag) -> bytes:
    result = bytearray((max(int(flag) for flag in flags) // 8) + 1)
    for flag in flags:
        result[int(flag) // 8] |= 1 << (int(flag) % 8)
    return bytes(result)


def test_champion_source_contract_is_exact() -> None:
    assert CHAMPION_CHECKPOINT_COUNT == 3
    assert CHAMPION_RNG_DELAY_FRAMES == 150
    assert CHAMPION_SAFE_HP == 90
    assert CHAMPION_FULL_RESTORE_INPUT_RESERVE == 2
    assert CHAMPION_FORCED_SWITCH_LIMIT == 5
    assert CHAMPION_RHYDON_SAFE_HP == 50
    assert MapId.CHAMPIONS_ROOM == 0x78
    assert MapId.HALL_OF_FAME == 0x76
    assert EventFlag.BEAT_CHAMPION_RIVAL == 0x901
    assert CHAMPION_PARTY == (
        (0x97, 61),
        (0x95, 59),
        (0x01, 61),
        (0x16, 61),
        (0x14, 63),
        (0x9A, 65),
    )


def test_champion_receipt_reconstructs_party_and_policy() -> None:
    turns = tuple(
        ChampionTurn(
            species,
            level,
            100,
            CHAMPION_SAFE_HP,
            0,
            (1, 1, 0, 1),
            4 if species in {0x01, 0x14} else 1,
            position,
        )
        for position, (species, level) in enumerate(CHAMPION_PARTY)
    )
    assert _encounter_party(turns) == CHAMPION_PARTY
    assert _turns_valid(turns)


def test_champion_status_recovery_falls_back_to_full_restore() -> None:
    assert (
        _select_recovery_item(
            CHAMPION_SAFE_HP,
            1,
            {ItemId.FULL_RESTORE: 2},
        )
        is ItemId.FULL_RESTORE
    )
    assert (
        _select_recovery_item(
            CHAMPION_SAFE_HP,
            1,
            {ItemId.FULL_HEAL: 1, ItemId.FULL_RESTORE: 2},
        )
        is ItemId.FULL_HEAL
    )


def test_champion_move_ranking_distinguishes_late_matchups() -> None:
    def raw(
        species: int,
        *,
        enemy_hp: int = 100,
        pp: tuple[int, int, int, int] = (5, 15, 15, 0),
        active_party_index: int | None = 0,
        active_party_pp: tuple[int, int, int, int] | None = None,
    ) -> RawGameState:
        return RawGameState(
            game_started=True,
            map_id=MapId.CHAMPIONS_ROOM,
            player_x=4,
            player_y=3,
            party_count=3,
            battle_state=2,
            enemy_species_id=species,
            enemy_hp=enemy_hp,
            first_party_pp=pp,
            first_party_max_hp=171,
            active_party_index=active_party_index,
            active_party_pp=active_party_pp,
        )

    assert _champion_move_slot(raw(0x97, pp=(5, 10, 5, 0))) == 3
    assert _champion_move_slot(raw(0x97, pp=(5, 10, 0, 0))) == 2
    assert _champion_move_slot(raw(0x95)) == 2
    assert _champion_move_slot(raw(0x01, pp=(5, 10, 15, 3))) == 4
    assert _champion_move_slot(raw(0x14, pp=(5, 15, 15, 3))) == 4
    assert _champion_move_slot(raw(0x14, pp=(5, 0, 0, 0))) == 1
    assert _champion_move_slot(raw(0x16, enemy_hp=31, pp=(5, 15, 15, 3))) == 2
    assert _champion_move_slot(raw(0x16, enemy_hp=196, pp=(5, 15, 15, 3))) == 2
    assert _champion_move_slot(raw(0x9A, pp=(5, 15, 15, 3))) == 3
    assert (
        _champion_move_slot(
            replace(
                raw(0x9A, pp=(5, 15, 15, 3)),
                player_disabled_move_slot=3,
                player_disable_turns=2,
            )
        )
        == 2
    )
    assert (
        _champion_move_slot(
            raw(
                0x9A,
                pp=(18, 11, 0, 11),
                active_party_index=3,
                active_party_pp=(14, 20, 10, 0),
            )
        )
        == 1
    )
    assert _champion_recovery_threshold(raw(0x01)) == CHAMPION_RHYDON_SAFE_HP
    assert _champion_recovery_threshold(raw(0x14)) == CHAMPION_SAFE_HP
    assert _champion_recovery_threshold(raw(0x16, enemy_hp=31)) == CHAMPION_GYARADOS_FINISH_SAFE_HP
    assert _champion_recovery_threshold(raw(0x16, enemy_hp=196)) == 171
    assert _champion_recovery_threshold(raw(0x9A)) == 171
    assert _champion_recovery_threshold(raw(0x14, enemy_hp=24)) == CHAMPION_ARCANINE_FINISH_SAFE_HP


def test_champion_only_requests_available_recovery() -> None:
    assert not _champion_recovery_available(0, {})
    assert not _champion_recovery_available(0, {ItemId.FULL_HEAL: 3})
    assert _champion_recovery_available(1, {ItemId.FULL_HEAL: 1})
    assert _champion_recovery_available(0, {ItemId.FULL_RESTORE: 1})


def test_champion_forced_switch_chooses_the_healthiest_living_teammate() -> None:
    assert _champion_forced_switch_target((0, 0, 0, 140, 73, 70), 0) == 3
    assert _champion_forced_switch_target((0, 0, 0), 0) is None


def test_champion_receipt_accepts_live_low_hp_decision() -> None:
    turns = tuple(
        ChampionTurn(species, level, 1, 1, 0, (1, 1, 1, 1), 1, position)
        for position, (species, level) in enumerate(CHAMPION_PARTY)
    )
    assert _turns_valid(turns)
    assert not _turns_valid((ChampionTurn(0x97, 61, 1, 0, 0, (1, 1, 1, 1), 1, 0),))


def test_champion_completion_is_distinct_from_teacher_strategy_evidence() -> None:
    final = RawGameState(
        game_started=True,
        map_id=MapId.HALL_OF_FAME,
        player_x=4,
        player_y=3,
        party_count=6,
        battle_state=0,
        party_species_ids=(0x1C, 0x40, 0x76, 0x84, 0x68, 0x2B),
        event_flags=_events(EventFlag.BEAT_CHAMPION_RIVAL),
    )
    report = ChampionChapterReport(
        records=tuple(
            ChampionCheckpoint(str(index), str(index), final)
            for index in range(CHAMPION_CHECKPOINT_COUNT)
        ),
        final_raw=final,
        turns=(),
        party=(),
        hyper_potions_used=0,
        full_restores_used=1,
        full_heals_used=0,
        x_accuracy_used=1,
        x_specials_used=4,
        party_hp=(178, 120, 100, 90, 80, 70),
        party_status=(0, 0, 0, 0, 0, 0),
        frames_executed=1,
        actions_executed=1,
        controller_released=True,
        require_teacher_strategy_evidence=False,
    )

    assert report.completion_evidence_passed
    assert not report.teacher_strategy_evidence_passed
    assert report.passed
    assert not replace(report, require_teacher_strategy_evidence=True).passed
