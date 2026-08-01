from pokemon_red_completion.agatha import (
    AGATHA_APPROACH,
    AGATHA_CHECKPOINT_COUNT,
    AGATHA_ELIXIR_USE,
    AGATHA_PARTY,
    AGATHA_RNG_DELAY_FRAMES,
    AGATHA_SAFE_HP,
    AGATHA_SURF_RESERVE,
    AGATHA_X_SPECIAL_USE,
    AgathaTurn,
    _agatha_move_slot,
    _encounter_party,
    _turns_valid,
)
from pokemon_red_completion.observation import EventFlag, MapId, RawGameState


def test_agatha_source_contract_is_exact() -> None:
    assert AGATHA_CHECKPOINT_COUNT == 3
    assert AGATHA_APPROACH == ("right", "up", "up")
    assert AGATHA_RNG_DELAY_FRAMES == 85
    assert AGATHA_ELIXIR_USE == 1
    assert AGATHA_X_SPECIAL_USE == 1
    assert AGATHA_SURF_RESERVE == 1
    assert MapId.AGATHAS_ROOM == 0xF7
    assert MapId.LANCES_ROOM == 0x71
    assert EventFlag.BEAT_AGATHA == 0x8F1
    assert AGATHA_PARTY == (
        (0x0E, 56),
        (0x82, 56),
        (0x93, 55),
        (0x2D, 58),
        (0x0E, 60),
    )


def test_agatha_receipt_deduplicates_switches() -> None:
    identities = (
        (AGATHA_PARTY[0], 0),
        (AGATHA_PARTY[1], 1),
        (AGATHA_PARTY[0], 0),
        (AGATHA_PARTY[2], 2),
        (AGATHA_PARTY[3], 3),
        (AGATHA_PARTY[4], 4),
    )
    turns = tuple(
        AgathaTurn(
            species,
            level,
            1,
            AGATHA_SAFE_HP,
            0,
            (1, 1, 1, 1),
            3,
            party_position,
        )
        for (species, level), party_position in identities
    )
    assert _encounter_party(turns) == AGATHA_PARTY
    assert _turns_valid(turns)
    assert _turns_valid(
        (AgathaTurn(0x82, 56, 1, AGATHA_SAFE_HP, 0, (1, 0, 1, 1), 1),)
    )
    assert _turns_valid(
        (AgathaTurn(0x82, 56, 1, AGATHA_SAFE_HP, 0x40, (1, 0, 1, 1), 1),)
    )
    assert not _turns_valid((AgathaTurn(0x82, 56, 1, 0, 0, (1, 0, 1, 1), 1),))


def test_agatha_policy_uses_live_legal_pp_fallbacks() -> None:
    raw = RawGameState(
        game_started=True,
        map_id=MapId.AGATHAS_ROOM,
        player_x=4,
        player_y=3,
        party_count=3,
        battle_state=2,
        enemy_species_id=0x82,
        first_party_pp=(0, 5, 0, 0),
    )
    assert _agatha_move_slot(raw) == 2
    disabled = RawGameState(
        game_started=True,
        map_id=MapId.AGATHAS_ROOM,
        player_x=4,
        player_y=3,
        party_count=3,
        battle_state=2,
        enemy_species_id=0x2D,
        first_party_pp=(3, 5, 0, 0),
        player_disabled_move_slot=1,
        player_disable_turns=2,
    )
    assert _agatha_move_slot(disabled) == 2
    ghost = RawGameState(
        game_started=True,
        map_id=MapId.AGATHAS_ROOM,
        player_x=4,
        player_y=3,
        party_count=3,
        battle_state=2,
        enemy_species_id=0x0E,
        first_party_pp=(3, 5, 12, AGATHA_SURF_RESERVE + 1),
    )
    assert _agatha_move_slot(ghost) == 4
    reserve = RawGameState(
        game_started=True,
        map_id=MapId.AGATHAS_ROOM,
        player_x=4,
        player_y=3,
        party_count=3,
        battle_state=2,
        enemy_species_id=0x0E,
        first_party_pp=(3, 5, 12, AGATHA_SURF_RESERVE),
    )
    assert _agatha_move_slot(reserve) == 3
