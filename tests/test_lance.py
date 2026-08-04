from pokemon_red_completion.lance import (
    LANCE_AERODACTYL_PIVOT_SPECIES,
    LANCE_APPROACH,
    LANCE_CHAMPION_FULL_RESTORE_RESERVE,
    LANCE_CHAMPION_SURF_RESERVE,
    LANCE_CHECKPOINT_COUNT,
    LANCE_HELPER_PIVOT_LIMIT,
    LANCE_PARTY,
    LANCE_RNG_DELAY_FRAMES,
    LANCE_SAFE_HP,
    LanceTurn,
    _encounter_party,
    _lance_field_recovery_item,
    _lance_move_slot,
    _lance_recovery_threshold,
    _next_lance_helper,
    _should_use_lance_helper_pivot,
    _turns_valid,
)
from pokemon_red_completion.observation import EventFlag, ItemId, MapId, RawGameState


def test_lance_source_contract_is_exact() -> None:
    assert LANCE_CHECKPOINT_COUNT == 3
    assert LANCE_RNG_DELAY_FRAMES == 40
    assert LANCE_AERODACTYL_PIVOT_SPECIES == 0xAB
    assert LANCE_SAFE_HP == 120
    assert LANCE_CHAMPION_FULL_RESTORE_RESERVE == 1
    assert LANCE_CHAMPION_SURF_RESERVE == 0
    assert LANCE_HELPER_PIVOT_LIMIT == 2
    assert LANCE_APPROACH == ("up",) * 9
    assert MapId.LANCES_ROOM == 0x71
    assert MapId.CHAMPIONS_ROOM == 0x78
    assert EventFlag.BEAT_LANCE == 0x8FE
    assert LANCE_PARTY == (
        (0x16, 58),
        (0x59, 56),
        (0x59, 56),
        (0xAB, 60),
        (0x42, 62),
    )


def test_lance_receipt_reconstructs_party_and_policy() -> None:
    turns = (
        LanceTurn(0x16, 58, 100, 110, 0, (1, 1, 0, 1), 2, 0),
        LanceTurn(0x59, 56, 100, 110, 0, (1, 1, 1, 1), 3, 1),
        LanceTurn(0x59, 56, 1, 110, 0, (1, 1, 1, 1), 3, 1),
        LanceTurn(0x59, 56, 100, 110, 0, (1, 1, 1, 1), 3, 2),
        LanceTurn(0xAB, 60, 100, 110, 0, (1, 1, 0, 1), 4, 3),
        LanceTurn(0x42, 62, 100, 110, 0, (1, 1, 1, 1), 3, 4),
    )
    assert _encounter_party(turns) == LANCE_PARTY
    assert _turns_valid(turns)


def test_lance_recovery_selects_any_living_helper() -> None:
    assert _next_lance_helper((80, 0, 39)) == 2
    assert _next_lance_helper((80, 25, 39)) == 1
    assert _next_lance_helper((80, 0, 0)) is None
    assert _next_lance_helper((180, 120, 140), (220, 174, 158)) is None


def test_lance_helper_pivots_cannot_exceed_the_two_revive_contract() -> None:
    state = RawGameState(
        game_started=True,
        map_id=MapId.LANCES_ROOM,
        player_x=6,
        player_y=2,
        party_count=6,
        battle_state=2,
        first_party_hp=165,
        first_party_max_hp=205,
        first_party_pp=(7, 0, 0, 0),
    )

    assert _should_use_lance_helper_pivot(
        state,
        helper_index=4,
        helper_pivots_used=1,
    )
    assert not _should_use_lance_helper_pivot(
        state,
        helper_index=4,
        helper_pivots_used=2,
    )


def test_lance_low_pp_finisher_requires_full_health() -> None:
    def raw(*, pp: tuple[int, int, int, int], max_hp: int) -> RawGameState:
        return RawGameState(
            game_started=True,
            map_id=MapId.LANCES_ROOM,
            player_x=6,
            player_y=11,
            party_count=3,
            battle_state=2,
            first_party_pp=pp,
            first_party_max_hp=max_hp,
        )

    assert (
        _lance_recovery_threshold(raw(pp=(14, 0, 0, 0), max_hp=171))
        == 171
    )
    assert (
        _lance_recovery_threshold(raw(pp=(14, 0, 1, 0), max_hp=171))
        == LANCE_SAFE_HP
    )
    assert (
        _lance_recovery_threshold(
            RawGameState(
                game_started=True,
                map_id=MapId.LANCES_ROOM,
                player_x=6,
                player_y=11,
                party_count=3,
                battle_state=2,
                enemy_species_id=0x16,
                first_party_pp=(14, 0, 1, 0),
                first_party_max_hp=171,
            )
        )
        == 171
    )


def test_lance_field_recovery_preserves_full_restore_for_champion() -> None:
    assert (
        _lance_field_recovery_item(
            hp=50,
            max_hp=170,
            status=0,
            inventory={ItemId.FULL_RESTORE: 2},
        )
        is None
    )
    assert (
        _lance_field_recovery_item(
            hp=50,
            max_hp=170,
            status=0,
            inventory={ItemId.HYPER_POTION: 1, ItemId.FULL_RESTORE: 2},
        )
        is ItemId.HYPER_POTION
    )


def test_lance_policy_prefers_accurate_and_type_advantaged_fallbacks() -> None:
    def raw(*, species: int, pp: tuple[int, int, int, int]) -> RawGameState:
        return RawGameState(
            game_started=True,
            map_id=MapId.LANCES_ROOM,
            player_x=6,
            player_y=11,
            party_count=3,
            battle_state=2,
            enemy_species_id=species,
            first_party_pp=pp,
        )

    assert _lance_move_slot(raw(species=0x16, pp=(10, 6, 8, 0))) == 1
    assert _lance_move_slot(raw(species=0xAB, pp=(10, 6, 8, 0))) == 3
    assert _lance_move_slot(raw(species=0x59, pp=(10, 6, 8, 0))) == 3
    assert _lance_move_slot(raw(species=0x59, pp=(10, 0, 0, 5))) == 1
    assert (
        _lance_move_slot(
            raw(
                species=0x42,
                pp=(10, 0, 0, LANCE_CHAMPION_SURF_RESERVE + 1),
            )
        )
        == 4
    )
    assert (
        _lance_move_slot(
            raw(species=0x42, pp=(10, 0, 0, LANCE_CHAMPION_SURF_RESERVE))
        )
        == 1
    )
