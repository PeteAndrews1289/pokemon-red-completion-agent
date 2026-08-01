from dataclasses import replace

from pokemon_red_completion.observation import ItemId, MapId, RawGameState
from pokemon_red_completion.sabrina import (
    ALAKAZAM_HYPER_POTION_THRESHOLD,
    CENTER_TO_GYM,
    CITY_TO_CENTER,
    GYM_TO_SABRINA,
    MAX_SABRINA_HYPER_POTIONS,
    PC_DEPOSIT_ITEMS,
    SABRINA_BATTLE_TIMING,
    SABRINA_PARTY,
    SABRINA_TO_CITY,
    SabrinaTurn,
    _encounter_party,
    _sabrina_move_slot,
    _sabrina_recovery_required,
)


def test_sabrina_routes_are_source_and_live_stable() -> None:
    assert GYM_TO_SABRINA == (
        "right",
        "right",
        "right",
        "up",
        "up",
        "left",
        "left",
        "left",
        "left",
        "down",
        "left",
        "down",
        "left",
        "left",
        "left",
        "up",
        "up",
        "down",
        "left",
        "down",
        "left",
        "left",
        "left",
        "up",
        "up",
        "left",
        "left",
    )
    assert len(CENTER_TO_GYM) == 84
    assert len(SABRINA_TO_CITY) == 19
    assert len(CITY_TO_CENTER) == 62
    assert SABRINA_BATTLE_TIMING.max_attack_confirmation_pulses == 6
    assert SABRINA_BATTLE_TIMING.max_pp_confirmation_pulses == 12
    assert MAX_SABRINA_HYPER_POTIONS == 7
    assert PC_DEPOSIT_ITEMS == (ItemId.SILPH_SCOPE, ItemId.CARD_KEY)


def test_sabrina_turn_receipts_preserve_party_transitions() -> None:
    turns = (
        SabrinaTurn(0x26, 38, 84, 139, 0, (15, 15, 10, 15), 2),
        SabrinaTurn(0x2A, 37, 82, 139, 0, (15, 14, 10, 15), 2),
        SabrinaTurn(0x77, 38, 107, 139, 0, (15, 13, 10, 15), 3),
        SabrinaTurn(0x77, 38, 63, 139, 0, (15, 13, 9, 15), 3),
        SabrinaTurn(0x77, 38, 13, 139, 0, (15, 13, 8, 15), 3),
        SabrinaTurn(0x95, 43, 107, 139, 0, (15, 13, 7, 15), 2),
    )
    assert _encounter_party(turns) == SABRINA_PARTY
    assert tuple(turn.move_slot for turn in turns) == (2, 2, 3, 3, 3, 2)


def test_sabrina_uses_a_larger_observed_safety_margin_for_alakazam() -> None:
    assert ALAKAZAM_HYPER_POTION_THRESHOLD == 110
    raw = RawGameState(
        game_started=True,
        map_id=MapId.SAFFRON_GYM,
        player_x=9,
        player_y=8,
        party_count=3,
        battle_state=2,
        first_party_hp=90,
    )
    assert not _sabrina_recovery_required(
        replace(raw, enemy_species_id=0x26)
    )
    assert _sabrina_recovery_required(
        replace(raw, enemy_species_id=0x95)
    )


def test_sabrina_policy_avoids_a_live_disabled_move() -> None:
    raw = RawGameState(
        game_started=True,
        map_id=MapId.SAFFRON_GYM,
        player_x=9,
        player_y=8,
        party_count=3,
        battle_state=2,
        first_party_moves=(0x82, 0x46, 0x3A, 0x39),
        first_party_pp=(15, 15, 10, 15),
        enemy_species_id=0x95,
        player_disabled_move_slot=2,
        player_disable_turns=3,
    )

    assert _sabrina_move_slot(raw) == 4
