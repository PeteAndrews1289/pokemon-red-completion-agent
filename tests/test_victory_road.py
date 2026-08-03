import pytest

import pokemon_red_completion.victory_road as victory_road
from pokemon_red_completion.battle_recovery import (
    PROTECTED_RECOVERY_MAX_ATTACK_PULSES,
    ProtectedRecoveryError,
)
from pokemon_red_completion.observation import EventFlag, ItemId, MapId, RawGameState
from pokemon_red_completion.victory_road import (
    BADGE_CHECK_EVENTS,
    CENTER_TO_ROUTE_22,
    COLLECTION_POKE_BALL_REMAINDER_BOUNDS,
    EARTH_APPROACH,
    INDIGO_FULL_RESTORE_RESERVE,
    INDIGO_X_SPECIAL_PURCHASE,
    INDIGO_X_SPECIAL_RESERVE,
    RIVAL_PARTY,
    RIVAL_POLICY,
    ROUTE_22_DEFAULT_HEAL_THRESHOLD,
    ROUTE_22_PROACTIVE_PIVOT_SPECIES,
    ROUTE_22_TO_GATE,
    ROUTE_22_TO_RIVAL,
    ROUTE_22_VENUSAUR_HEAL_THRESHOLD,
    ROUTE_23_TO_INDIGO,
    SAFFRON_TO_MART,
    VICTORY_ROAD_CHECKPOINT_COUNT,
    VICTORY_ROAD_INPUT_HYPER_POTION_BOUNDS,
    VICTORY_ROAD_MAX_REPEL_PURCHASE,
    VIRIDIAN_TO_ROUTE_22,
    VR1_TO_2F,
    VR2_FINAL_TO_3F,
    VR2_TO_3F,
    VR3_SOUTHEAST_TO_2F,
    VR3_SWITCH_TO_HOLE,
    RivalTurn,
    VictoryRoadChapterError,
    _battle_sacrifice,
    _encounter_party,
    _indigo_buy_entry_action,
    _rival_moves_valid,
    _route22_rival_move_slot,
    _validate_collection_poke_ball_remainder,
)


class _RecoveryReader:
    def __init__(self, raw: RawGameState) -> None:
        self.raw = raw

    def read(self) -> RawGameState:
        return self.raw


def _raw_with_event(event: EventFlag) -> RawGameState:
    flags = bytearray(int(event) // 8 + 1)
    flags[int(event) // 8] |= 1 << (int(event) % 8)
    return RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_22,
        player_x=30,
        player_y=5,
        party_count=3,
        battle_state=0,
        event_flags=bytes(flags),
    )


def _failed_recovery(*_args, **_kwargs):
    raise ProtectedRecoveryError("Protected recovery left its trainer battle.")


def test_route22_recovery_accepts_verified_battle_ending_pivot(monkeypatch) -> None:
    quantities = iter((4, 3))
    monkeypatch.setattr(
        victory_road,
        "_bag",
        lambda _emulator: {ItemId.HYPER_POTION: next(quantities)},
    )
    monkeypatch.setattr(victory_road, "_party_hp", lambda _emulator: (120, 0, 90))
    monkeypatch.setattr(victory_road, "_party_max_hp", lambda _emulator: (180, 60, 90))
    monkeypatch.setattr(
        victory_road,
        "protected_lead_recovery",
        _failed_recovery,
    )

    assert _battle_sacrifice(
        object(),
        _RecoveryReader(_raw_with_event(EventFlag.BEAT_ROUTE_22_RIVAL_2ND_BATTLE)),
        object(),
        1,
        heal_lead=True,
    )


def test_route22_recovery_rejects_unverified_battle_exit(monkeypatch) -> None:
    quantities = iter((4, 4))
    monkeypatch.setattr(
        victory_road,
        "_bag",
        lambda _emulator: {ItemId.HYPER_POTION: next(quantities)},
    )
    monkeypatch.setattr(victory_road, "_party_hp", lambda _emulator: (120, 0, 90))
    monkeypatch.setattr(victory_road, "_party_max_hp", lambda _emulator: (180, 60, 90))
    monkeypatch.setattr(victory_road, "protected_lead_recovery", _failed_recovery)
    raw = _raw_with_event(EventFlag.BEAT_ROUTE_22_RIVAL_2ND_BATTLE)
    flags = bytearray(raw.event_flags)
    flags[int(EventFlag.BEAT_ROUTE_22_RIVAL_2ND_BATTLE) // 8] = 0

    with pytest.raises(VictoryRoadChapterError, match="protected recovery failed"):
        _battle_sacrifice(
            object(),
            _RecoveryReader(
                RawGameState(
                    game_started=True,
                    map_id=MapId.ROUTE_22,
                    player_x=30,
                    player_y=5,
                    party_count=3,
                    battle_state=0,
                    event_flags=bytes(flags),
                )
            ),
            object(),
            1,
            heal_lead=True,
        )


def test_victory_road_routes_are_live_qualified() -> None:
    assert VICTORY_ROAD_CHECKPOINT_COUNT == 9
    assert len(CENTER_TO_ROUTE_22) == 38
    assert len(ROUTE_22_TO_RIVAL) == 19
    assert len(SAFFRON_TO_MART) == 59
    assert len(VIRIDIAN_TO_ROUTE_22) == 33
    assert len(ROUTE_22_TO_GATE) == 66
    assert len(EARTH_APPROACH) == 34
    assert len(VR1_TO_2F) == 51
    assert len(VR2_TO_3F) == 56
    assert len(VR3_SWITCH_TO_HOLE) == 85
    assert len(VR2_FINAL_TO_3F) == 17
    assert len(VR3_SOUTHEAST_TO_2F) == 8
    assert len(ROUTE_23_TO_INDIGO) == 45
    assert VICTORY_ROAD_MAX_REPEL_PURCHASE == 2
    assert VICTORY_ROAD_INPUT_HYPER_POTION_BOUNDS == (0, 7)
    assert INDIGO_FULL_RESTORE_RESERVE == 6
    assert INDIGO_X_SPECIAL_RESERVE == 8
    assert INDIGO_X_SPECIAL_PURCHASE == 8
    assert COLLECTION_POKE_BALL_REMAINDER_BOUNDS == (0, 30)
    assert PROTECTED_RECOVERY_MAX_ATTACK_PULSES == 96


@pytest.mark.parametrize("quantity", (0, 1, 30))
def test_indigo_cleanup_accepts_every_bounded_capture_remainder(quantity: int) -> None:
    assert _validate_collection_poke_ball_remainder(quantity) == quantity


@pytest.mark.parametrize("quantity", (-1, 31))
def test_indigo_cleanup_rejects_out_of_contract_capture_remainder(quantity: int) -> None:
    with pytest.raises(VictoryRoadChapterError, match="zero to thirty"):
        _validate_collection_poke_ball_remainder(quantity)


def test_indigo_cleanup_opens_buy_from_the_zero_remainder_field_state() -> None:
    assert _indigo_buy_entry_action(0) is victory_road.MacroActionKind.INTERACT


@pytest.mark.parametrize("quantity", (1, 30))
def test_indigo_cleanup_returns_from_a_completed_sale_before_buying(quantity: int) -> None:
    assert _indigo_buy_entry_action(quantity) is victory_road.MacroActionKind.CANCEL


def test_victory_road_source_ids_are_exact() -> None:
    assert MapId.ROUTE_22 == 0x21
    assert MapId.ROUTE_23 == 0x22
    assert MapId.VICTORY_ROAD_1F == 0x6C
    assert MapId.VICTORY_ROAD_2F == 0xC2
    assert MapId.VICTORY_ROAD_3F == 0xC6
    assert MapId.INDIGO_PLATEAU_LOBBY == 0xAE
    assert EventFlag.BEAT_ROUTE_22_RIVAL_2ND_BATTLE == 0x526
    assert tuple(int(event) for event in BADGE_CHECK_EVENTS) == tuple(range(0x530, 0x537))
    assert EventFlag.VICTORY_ROAD_2F_BOULDER_ON_SWITCH_1 == 0x538
    assert EventFlag.VICTORY_ROAD_2F_BOULDER_ON_SWITCH_2 == 0x53F
    assert EventFlag.VICTORY_ROAD_3F_BOULDER_ON_SWITCH_1 == 0x660
    assert EventFlag.VICTORY_ROAD_3F_BOULDER_IN_HOLE == 0x666
    assert EventFlag.VICTORY_ROAD_1F_BOULDER_ON_SWITCH == 0x917
    assert ItemId.FULL_RESTORE == 0x10
    assert ItemId.REVIVE == 0x35
    assert ItemId.TM01_MEGA_PUNCH == 0xC9
    assert ItemId.TM09_TAKE_DOWN == 0xD1
    assert ItemId.TM17_SUBMISSION == 0xD9


def test_route22_rival_receipt_matches_source_party_and_policy() -> None:
    turns = tuple(
        RivalTurn(species, level, 1, 1, (1, 1, 1, 1), RIVAL_POLICY[species])
        for species, level in RIVAL_PARTY
    )
    assert _encounter_party(turns) == RIVAL_PARTY
    assert tuple(turn.move_slot for turn in turns) == (3, 4, 3, 4, 2, 3)
    assert _rival_moves_valid(turns)
    assert ROUTE_22_DEFAULT_HEAL_THRESHOLD == 100
    assert frozenset({0x9A}) == ROUTE_22_PROACTIVE_PIVOT_SPECIES
    assert ROUTE_22_VENUSAUR_HEAL_THRESHOLD == 120


def test_route22_rival_policy_uses_physical_alakazam_attack_and_disable_fallback() -> None:
    raw = RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_22,
        player_x=30,
        player_y=5,
        party_count=3,
        battle_state=2,
        enemy_species_id=0x95,
        first_party_pp=(10, 15, 10, 15),
    )
    assert _route22_rival_move_slot(raw) == 2
    disabled = RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_22,
        player_x=30,
        player_y=5,
        party_count=3,
        battle_state=2,
        enemy_species_id=0x95,
        first_party_pp=(10, 15, 10, 15),
        player_disabled_move_slot=2,
        player_disable_turns=3,
    )
    assert _route22_rival_move_slot(disabled) == 4
