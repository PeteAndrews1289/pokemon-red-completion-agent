import pokemon_red_completion.agatha as agatha_module
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.agatha import (
    AGATHA_APPROACH,
    AGATHA_CHECKPOINT_COUNT,
    AGATHA_ELIXIR_USE,
    AGATHA_FORCED_SWITCH_LIMIT,
    AGATHA_PARTY,
    AGATHA_RNG_DELAY_FRAMES,
    AGATHA_SAFE_HP,
    AGATHA_SURF_RESERVE,
    AGATHA_X_SPECIAL_USE,
    AgathaTurn,
    _agatha_forced_switch_target,
    _agatha_move_slot,
    _battle_x_special,
    _encounter_party,
    _observed_party_valid,
    _post_agatha_recovery_item,
    _turns_valid,
)
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    BattleMenuState,
    EventFlag,
    ItemId,
    MapId,
    RawGameState,
)


def test_agatha_source_contract_is_exact() -> None:
    assert AGATHA_CHECKPOINT_COUNT == 3
    assert AGATHA_APPROACH == ("right", "up", "up")
    assert AGATHA_RNG_DELAY_FRAMES == 85
    assert AGATHA_ELIXIR_USE == 1
    assert AGATHA_X_SPECIAL_USE == 1
    assert AGATHA_FORCED_SWITCH_LIMIT == 5
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


def test_post_agatha_recovery_falls_back_to_full_restore_for_status() -> None:
    assert (
        _post_agatha_recovery_item(
            hp=160,
            max_hp=209,
            status=0x08,
            full_heals=2,
            full_restores=4,
        )
        == ItemId.FULL_RESTORE
    )
    assert (
        _post_agatha_recovery_item(
            hp=208,
            max_hp=208,
            status=0x08,
            full_heals=0,
            full_restores=5,
        )
        == ItemId.FULL_RESTORE
    )
    assert (
        _post_agatha_recovery_item(
            hp=180,
            max_hp=208,
            status=0,
            full_heals=0,
            full_restores=5,
        )
        == ItemId.FULL_RESTORE
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
    assert _observed_party_valid(turns)
    assert _turns_valid(turns)
    assert _turns_valid((AgathaTurn(0x82, 56, 1, AGATHA_SAFE_HP, 0, (1, 0, 1, 1), 1),))
    assert _turns_valid((AgathaTurn(0x82, 56, 1, AGATHA_SAFE_HP, 0x40, (1, 0, 1, 1), 1),))
    assert not _turns_valid((AgathaTurn(0x82, 56, 1, 0, 0, (1, 0, 1, 1), 1),))


def test_agatha_receipt_accepts_switch_in_ko_between_decisions() -> None:
    turns = tuple(
        AgathaTurn(
            *AGATHA_PARTY[party_position],
            enemy_hp=1,
            lead_hp=AGATHA_SAFE_HP,
            lead_status=0,
            pp=(1, 1, 1, 1),
            move_slot=3,
            party_position=party_position,
        )
        for party_position in (0, 0, 2, 3, 4)
    )
    assert _encounter_party(turns) == (
        AGATHA_PARTY[0],
        AGATHA_PARTY[2],
        AGATHA_PARTY[3],
        AGATHA_PARTY[4],
    )
    assert _observed_party_valid(turns)


def test_agatha_receipt_rejects_wrong_or_missing_terminal_opponents() -> None:
    wrong_identity = (
        AgathaTurn(0x82, 55, 1, AGATHA_SAFE_HP, 0, (1, 1, 1, 1), 3, 1),
        AgathaTurn(*AGATHA_PARTY[4], 1, AGATHA_SAFE_HP, 0, (1, 1, 1, 1), 3, 4),
    )
    missing_final = (
        AgathaTurn(*AGATHA_PARTY[0], 1, AGATHA_SAFE_HP, 0, (1, 1, 1, 1), 3, 0),
        AgathaTurn(*AGATHA_PARTY[3], 1, AGATHA_SAFE_HP, 0, (1, 1, 1, 1), 3, 3),
    )
    assert not _observed_party_valid(wrong_identity)
    assert not _observed_party_valid(missing_final)


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


def test_agatha_reserve_uses_live_active_moves_and_pp() -> None:
    reserve = RawGameState(
        game_started=True,
        map_id=MapId.AGATHAS_ROOM,
        player_x=4,
        player_y=3,
        party_count=6,
        battle_state=2,
        active_party_index=3,
        enemy_species_id=0x0E,
        first_party_pp=(15, 15, 10, 10),
        active_party_moves=(0, 84, 85, 0),
        active_party_pp=(0, 12, 8, 0),
        player_disabled_move_slot=2,
        player_disable_turns=2,
    )

    assert _agatha_move_slot(reserve) == 3


def test_agatha_forced_switch_prefers_live_matchup_coverage() -> None:
    party = (0x1C, 0x40, 0x76, 0x84, 0x68, 0x2B)
    hp = (0, 31, 92, 150, 74, 55)

    assert _agatha_forced_switch_target(hp, party, 0, 0x0E) == 2
    assert _agatha_forced_switch_target(hp, party, 0, 0x82) == 4
    assert _agatha_forced_switch_target((0, 0, 0, 0, 0, 0), party, 0, 0x0E) is None


def test_battle_x_item_reselects_after_unconsumed_turn(monkeypatch) -> None:
    state = {
        "at_main": True,
        "item_selected": False,
        "attempts": 0,
        "quantity": 8,
        "text_advances": [],
    }

    class Reader:
        def read(self) -> RawGameState:
            return RawGameState(
                game_started=True,
                map_id=MapId.AGATHAS_ROOM,
                player_x=5,
                player_y=3,
                party_count=3,
                battle_state=2,
            )

        def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
            del raw
            return BattleMenuState(
                BattleMenuPhase.MAIN if state["at_main"] else BattleMenuPhase.UNKNOWN
            )

    class Emulator:
        pass

    def select_item(*args) -> None:
        del args
        state["item_selected"] = True

    def pulse(*args, **kwargs) -> None:
        del kwargs
        if state["item_selected"]:
            state["item_selected"] = False
            state["attempts"] += 1
            state["at_main"] = False
            if state["attempts"] == 2:
                state["quantity"] -= 1
        elif not state["at_main"]:
            state["text_advances"].append(args[1])
            state["at_main"] = True

    monkeypatch.setattr(
        agatha_module,
        "_bag",
        lambda emulator: {ItemId.X_SPECIAL: state["quantity"]},
    )
    monkeypatch.setattr(agatha_module, "_select_battle_main_command", lambda *args: None)
    monkeypatch.setattr(agatha_module, "_select_bag_item", select_item)
    monkeypatch.setattr(agatha_module, "_pulse", pulse)

    _battle_x_special(Reader(), object(), Emulator())

    assert state["attempts"] == 2
    assert state["quantity"] == 7
    assert state["text_advances"] == [MacroActionKind.CANCEL, MacroActionKind.CANCEL]
