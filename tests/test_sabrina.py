from dataclasses import replace

import pokemon_red_completion.sabrina as sabrina_module
from pokemon_red_completion.observation import ItemId, MapId, RawGameState
from pokemon_red_completion.sabrina import (
    ALAKAZAM_HYPER_POTION_THRESHOLD,
    CENTER_TO_GYM,
    CITY_TO_CENTER,
    GYM_TO_SABRINA,
    HYPER_POTION_THRESHOLD,
    MAX_SABRINA_HYPER_POTIONS,
    PC_DEPOSIT_ITEMS,
    POST_SURF_NO_STRENGTH_SABRINA_MOVES,
    POST_SURF_SABRINA_MOVES,
    PRE_SURF_SABRINA_MOVES,
    SABRINA_BATTLE_TIMING,
    SABRINA_PARTY,
    SABRINA_TO_CITY,
    SABRINA_X_SPECIAL_USES,
    SabrinaTurn,
    _confirm_selected_pc_deposit,
    _encounter_party,
    _sabrina_capacity_ready,
    _sabrina_move_slot,
    _sabrina_recovery_required,
    _sabrina_terminal_moves_ready,
)


def test_pc_deposit_confirmation_stops_at_the_requested_bag_transition(
    monkeypatch,
) -> None:
    confirmations: list[object] = []

    monkeypatch.setattr(
        sabrina_module,
        "_bag",
        lambda _emulator: {ItemId.SILPH_SCOPE: 1} if len(confirmations) < 2 else {},
    )
    monkeypatch.setattr(
        sabrina_module,
        "_pulse",
        lambda *args, **kwargs: confirmations.append((args, kwargs)),
    )

    _confirm_selected_pc_deposit(
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        ItemId.SILPH_SCOPE,
        sabrina_module.SilphTiming(),
    )

    assert len(confirmations) == 2


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
    assert SABRINA_X_SPECIAL_USES == 2
    assert PC_DEPOSIT_ITEMS == (ItemId.SILPH_SCOPE, ItemId.CARD_KEY)


def test_sabrina_capacity_accepts_a_consumed_recovery_stack() -> None:
    key_items = {item: 1 for item in PC_DEPOSIT_ITEMS}

    assert _sabrina_capacity_ready({**key_items, **{1000 + index: 1 for index in range(17)}})
    assert _sabrina_capacity_ready({**key_items, **{1000 + index: 1 for index in range(18)}})
    assert not _sabrina_capacity_ready(
        {**key_items, **{1000 + index: 1 for index in range(19)}}
    )
    assert not _sabrina_capacity_ready({ItemId.SILPH_SCOPE: 1})


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


def test_sabrina_protects_the_observed_alakazam_critical_damage_floor() -> None:
    assert HYPER_POTION_THRESHOLD == 70
    assert ALAKAZAM_HYPER_POTION_THRESHOLD == 95
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
    assert _sabrina_recovery_required(replace(raw, enemy_species_id=0x95))
    assert not _sabrina_recovery_required(
        replace(raw, enemy_species_id=0x95, first_party_hp=95)
    )
    assert _sabrina_recovery_required(
        replace(raw, enemy_species_id=0x95, first_party_hp=94)
    )


def test_sabrina_policy_avoids_a_live_disabled_move() -> None:
    raw = RawGameState(
        game_started=True,
        map_id=MapId.SAFFRON_GYM,
        player_x=9,
        player_y=8,
        party_count=3,
        battle_state=2,
        first_party_moves=POST_SURF_SABRINA_MOVES,
        first_party_pp=(15, 15, 10, 15),
        enemy_species_id=0x95,
        player_disabled_move_slot=2,
        player_disable_turns=3,
    )

    assert _sabrina_move_slot(raw) == 4


def test_sabrina_policy_qualifies_the_pre_surf_ice_beam_lineage() -> None:
    raw = RawGameState(
        game_started=True,
        map_id=MapId.SAFFRON_GYM,
        player_x=9,
        player_y=8,
        party_count=6,
        battle_state=2,
        first_party_moves=PRE_SURF_SABRINA_MOVES,
        first_party_pp=(25, 30, 10, 25),
        enemy_species_id=0x26,
    )

    assert _sabrina_move_slot(raw) == 3
    assert _sabrina_move_slot(
        replace(raw, player_disabled_move_slot=3, player_disable_turns=2)
    ) == 1
    assert _sabrina_terminal_moves_ready(raw)
    assert not _sabrina_terminal_moves_ready(
        replace(raw, first_party_pp=(24, 30, 10, 25))
    )


def test_sabrina_policy_qualifies_the_post_surf_no_strength_lineage() -> None:
    raw = RawGameState(
        game_started=True,
        map_id=MapId.SAFFRON_GYM,
        player_x=9,
        player_y=8,
        party_count=6,
        battle_state=2,
        first_party_moves=POST_SURF_NO_STRENGTH_SABRINA_MOVES,
        first_party_pp=(25, 30, 10, 15),
        enemy_species_id=0x77,
    )

    assert _sabrina_move_slot(raw) == 3
    assert _sabrina_move_slot(
        replace(raw, player_disabled_move_slot=3, player_disable_turns=2)
    ) == 2
    assert _sabrina_terminal_moves_ready(raw)
