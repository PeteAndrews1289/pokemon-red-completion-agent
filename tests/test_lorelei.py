from dataclasses import replace
from inspect import getsource

from pokemon_red_completion.lorelei import (
    INDIGO_TO_LORELEI,
    LORELEI_APPROACH,
    LORELEI_BLASTOISE_TARGETS,
    LORELEI_CHECKPOINT_COUNT,
    LORELEI_JOLTEON_TARGETS,
    LORELEI_PARTY,
    LORELEI_RNG_DELAY_FRAMES,
    LORELEI_SAFE_HP,
    THUNDER_MOVE_ID,
    LoreleiTurn,
    _encounter_party,
    _lorelei_matchup_switch_target,
    _lorelei_move_slot,
    _lorelei_team_lesson_satisfied,
    _turns_valid,
    run_lorelei_chapter,
)
from pokemon_red_completion.observation import EventFlag, MapId, RawGameState


def test_lorelei_routes_are_live_qualified() -> None:
    assert LORELEI_CHECKPOINT_COUNT == 3
    assert LORELEI_RNG_DELAY_FRAMES == 119
    assert INDIGO_TO_LORELEI == (
        "up",
        "up",
        "up",
        "right",
        "right",
        "right",
        "right",
        "up",
        "right",
        "right",
        "up",
    )
    assert LORELEI_APPROACH == ("right", "up", "up")


def test_lorelei_source_ids_and_party_are_exact() -> None:
    assert MapId.LORELEIS_ROOM == 0xF5
    assert MapId.BRUNOS_ROOM == 0xF6
    assert EventFlag.BEAT_LORELEI == 0x8E1
    assert LORELEI_PARTY == (
        (0x78, 54),
        (0x8B, 53),
        (0x08, 54),
        (0x48, 56),
        (0x13, 56),
    )


def test_lorelei_receipt_reconstructs_party_and_rejects_unsafe_turns() -> None:
    turns = tuple(
        LoreleiTurn(species, level, 1, LORELEI_SAFE_HP, 0, (1, 1, 1, 1), 2)
        for species, level in LORELEI_PARTY
    )
    assert _encounter_party(turns) == LORELEI_PARTY
    assert _turns_valid(turns)
    assert not _turns_valid(
        (
            LoreleiTurn(
                LORELEI_PARTY[0][0],
                LORELEI_PARTY[0][1],
                1,
                LORELEI_SAFE_HP - 1,
                0,
                (1, 1, 1, 1),
                2,
            ),
        )
    )


def test_lorelei_matchup_switch_targets_living_roles_by_species() -> None:
    raw = RawGameState(
        game_started=True,
        map_id=MapId.LORELEIS_ROOM,
        player_x=5,
        player_y=3,
        party_count=6,
        battle_state=2,
        active_party_index=0,
        party_species_ids=(0x1C, 0x40, 0x76, 0x84, 0x68, 0x2B),
        party_hp=(202, 130, 120, 250, 125, 140),
    )

    assert _lorelei_matchup_switch_target(raw, 0x68) == 4
    assert (
        _lorelei_matchup_switch_target(
            replace(raw, party_hp=(202, 130, 120, 250, 0, 140)),
            0x68,
        )
        is None
    )


def test_lorelei_team_lesson_requires_both_declared_role_sets() -> None:
    reserve = tuple(
        LoreleiTurn(species, 54, 1, 120, 0, (1, 1, 1, 1), 1, 4)
        for species in LORELEI_JOLTEON_TARGETS
    )
    anchor = tuple(
        LoreleiTurn(species, 56, 1, 180, 0, (1, 1, 1, 1), 2, 0)
        for species in LORELEI_BLASTOISE_TARGETS
    )

    assert _lorelei_team_lesson_satisfied((*reserve, *anchor))
    assert not _lorelei_team_lesson_satisfied((*reserve[:-1], *anchor))
    assert not _lorelei_team_lesson_satisfied((*reserve, *anchor[:-1]))


def test_lorelei_jolteon_prefers_thunder_with_live_pp() -> None:
    raw = RawGameState(
        game_started=True,
        map_id=MapId.LORELEIS_ROOM,
        player_x=5,
        player_y=3,
        party_count=6,
        battle_state=2,
        active_party_index=4,
        active_party_species_id=0x68,
        active_party_moves=(THUNDER_MOVE_ID, 0x1C, 0x62, 0x54),
        active_party_pp=(10, 15, 30, 30),
        enemy_species_id=0x78,
    )

    assert _lorelei_move_slot(raw) == 1
    assert _lorelei_move_slot(replace(raw, active_party_pp=(0, 15, 30, 30))) == 4


def test_lorelei_switches_before_spending_its_accuracy_setup() -> None:
    source = getsource(run_lorelei_chapter)

    assert source.index("_lorelei_matchup_switch_target") < source.index(
        "if accuracy_used == 0"
    )
