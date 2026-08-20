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
    INDIGO_FULL_HEAL_RESERVE,
    INDIGO_FULL_RESTORE_RESERVE,
    INDIGO_X_SPECIAL_PURCHASE,
    INDIGO_X_SPECIAL_RESERVE,
    RIVAL_PARTY,
    RIVAL_POLICY,
    ROUTE_22_DEFAULT_HEAL_THRESHOLD,
    ROUTE_22_MAX_TEAM_PIVOTS,
    ROUTE_22_PIVOT_MIN_HP_RATIO,
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
    _route22_battle_ready_pivot_target,
    _route22_fainted_pivot_target,
    _route22_recovery_pivot_target,
    _route22_rival_move_slot,
    _route22_switch_with_faint_continuation,
    _validate_collection_poke_ball_remainder,
)


def test_indigo_capacity_sale_uses_potions_when_tm21_was_sold_early() -> None:
    assert victory_road._indigo_capacity_sale_item(1, 5) == ItemId.TM21_MEGA_DRAIN
    assert victory_road._indigo_capacity_sale_item(0, 5) == ItemId.POTION
    with pytest.raises(VictoryRoadChapterError):
        victory_road._indigo_capacity_sale_item(0, 0)


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
    assert INDIGO_FULL_RESTORE_RESERVE == 7
    assert INDIGO_FULL_HEAL_RESERVE == 6
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
    assert frozenset() == ROUTE_22_PROACTIVE_PIVOT_SPECIES
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


def test_route22_rival_continues_with_a_living_balanced_team_member() -> None:
    fainted = RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_22,
        player_x=30,
        player_y=5,
        party_count=6,
        battle_state=2,
        active_party_index=0,
        active_party_hp=0,
        enemy_species_id=0x9A,
        enemy_hp=2,
    )

    assert _route22_fainted_pivot_target(fainted, (0, 57, 57, 139, 69, 70)) == 1
    assert _route22_fainted_pivot_target(fainted, (0, 0, 0, 0, 0, 0)) is None


def test_route22_recovery_skips_fainted_fixed_slot_and_wraps_to_living_reserve() -> None:
    raw = RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_22,
        player_x=30,
        player_y=5,
        party_count=6,
        party_hp=(150, 0, 57, 139, 0, 70),
        battle_state=2,
        active_party_index=0,
        active_party_hp=150,
    )

    assert _route22_recovery_pivot_target(raw, 1) == 2
    assert _route22_recovery_pivot_target(raw, 4) == 5
    assert _route22_recovery_pivot_target(raw, 6) == 2


def test_route22_switch_continues_when_incoming_reserve_faints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Reader:
        raw = RawGameState(
            game_started=True,
            map_id=MapId.ROUTE_22,
            player_x=30,
            player_y=5,
            party_count=6,
            battle_state=2,
            active_party_index=0,
            active_party_hp=80,
        )

        def read(self) -> RawGameState:
            return self.raw

    reader = Reader()
    party_hp = [80, 0, 57, 139, 69, 70]
    calls: list[int] = []

    def switch(
        _actions: object,
        _reader: object,
        _emulator: object,
        party_index: int,
        **_kwargs: object,
    ) -> None:
        calls.append(party_index)
        if len(calls) == 1:
            party_hp[party_index] = 0
            reader.raw = RawGameState(
                game_started=True,
                map_id=MapId.ROUTE_22,
                player_x=30,
                player_y=5,
                party_count=6,
                battle_state=2,
                active_party_index=party_index,
                active_party_hp=0,
            )
            raise ProtectedRecoveryError("target fainted during the switch")
        reader.raw = RawGameState(
            game_started=True,
            map_id=MapId.ROUTE_22,
            player_x=30,
            player_y=5,
            party_count=6,
            battle_state=2,
            active_party_index=party_index,
            active_party_hp=party_hp[party_index],
        )

    monkeypatch.setattr(victory_road, "switch_active_battler", switch)
    monkeypatch.setattr(victory_road, "_party_hp", lambda _emulator: tuple(party_hp))

    selected = _route22_switch_with_faint_continuation(
        object(),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        2,
        label="Route 22 test pivot",
    )

    assert selected == 0
    assert calls == [2, 0]


def test_route22_rival_reserve_uses_observed_active_moves() -> None:
    reserve = RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_22,
        player_x=30,
        player_y=5,
        party_count=6,
        battle_state=2,
        active_party_index=1,
        active_party_hp=57,
        active_party_moves=(0x00, 0x21, 0x2D, 0x00),
        active_party_pp=(0, 0, 7, 0),
        enemy_species_id=0x9A,
        enemy_hp=2,
    )

    assert _route22_rival_move_slot(reserve) == 3


def test_route22_rival_fainted_continuation_uses_shared_switch_timing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Reader:
        raw = RawGameState(
            game_started=True,
            map_id=MapId.ROUTE_22,
            player_x=30,
            player_y=5,
            party_count=6,
            battle_state=2,
            active_party_index=0,
            active_party_hp=0,
            enemy_species_id=0x95,
            enemy_hp=2,
        )

        def read(self) -> RawGameState:
            return self.raw

    reader = Reader()
    calls = 0
    switches: list[tuple[int, int]] = []

    def run_battle(*_args: object, **_kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            try:
                raise victory_road.BattleRuntimeError("active battler fainted")
            except victory_road.BattleRuntimeError as cause:
                raise victory_road.BattleRuntimeError("runtime failed") from cause
        reader.raw = RawGameState(
            game_started=True,
            map_id=MapId.ROUTE_22,
            player_x=30,
            player_y=5,
            party_count=6,
            battle_state=0,
        )

    def switch(
        _actions: object,
        _reader: object,
        _emulator: object,
        party_index: int,
        *,
        label: str,
        wait_frames: int,
    ) -> None:
        assert label == "Route 22 rival fainted-member continuation"
        switches.append((party_index, wait_frames))
        reader.raw = RawGameState(
            game_started=True,
            map_id=MapId.ROUTE_22,
            player_x=30,
            player_y=5,
            party_count=6,
            battle_state=2,
            active_party_index=1,
            active_party_hp=57,
            enemy_species_id=0x95,
            enemy_hp=2,
        )

    monkeypatch.setattr(victory_road, "_pulse", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(victory_road, "_settle_confirm", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(victory_road, "run_adaptive_trainer_battle", run_battle)
    monkeypatch.setattr(victory_road, "switch_active_battler", switch)
    monkeypatch.setattr(victory_road, "_party_hp", lambda _emulator: (0, 57, 57, 139, 69, 70))
    monkeypatch.setattr(victory_road, "_bag", lambda _emulator: {ItemId.HYPER_POTION: 1})

    turns, potions = victory_road._defeat_route22_rival(
        object(),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
    )

    assert turns == ()
    assert potions == 0
    assert switches == [(1, victory_road.DEFAULT_HIDEOUT_TIMING.wait_frames)]


def test_route22_venusaur_keeps_trained_workhorse_instead_of_sacrificing_team(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Reader:
        raw = RawGameState(
            game_started=True,
            map_id=MapId.ROUTE_22,
            player_x=30,
            player_y=5,
            party_count=6,
            party_hp=(150, 0, 57, 139, 69, 70),
            battle_state=2,
            active_party_index=0,
            active_party_hp=100,
            first_party_pp=(10, 10, 10, 10),
            enemy_species_id=0x9A,
            enemy_hp=40,
        )

        def read(self) -> RawGameState:
            return self.raw

    reader = Reader()
    calls = 0
    switches: list[int] = []
    heals = 0

    def run_battle(_reader, _actions, policy, **_kwargs) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            try:
                policy(reader.raw)
            except Exception as cause:
                raise victory_road.BattleRuntimeError("runtime boundary") from cause
        reader.raw = RawGameState(
            game_started=True,
            map_id=MapId.ROUTE_22,
            player_x=30,
            player_y=5,
            party_count=6,
            party_hp=(150, 0, 57, 139, 69, 70),
            battle_state=0,
        )

    def switch(
        _actions: object,
        _reader: object,
        _emulator: object,
        party_index: int,
        **_kwargs: object,
    ) -> None:
        switches.append(party_index)
        reader.raw = RawGameState(
            game_started=True,
            map_id=MapId.ROUTE_22,
            player_x=30,
            player_y=5,
            party_count=6,
            party_hp=(150, 0, 57, 139, 69, 70),
            battle_state=2,
            active_party_index=party_index,
            active_party_hp=57,
            enemy_species_id=0x9A,
            enemy_hp=40,
        )

    def heal(*_args: object, **_kwargs: object) -> None:
        nonlocal heals
        heals += 1
        reader.raw = RawGameState(
            game_started=True,
            map_id=MapId.ROUTE_22,
            player_x=30,
            player_y=5,
            party_count=6,
            party_hp=(150, 0, 57, 139, 69, 70),
            battle_state=2,
            active_party_index=0,
            active_party_hp=150,
            first_party_pp=(10, 10, 10, 10),
            enemy_species_id=0x9A,
            enemy_hp=40,
        )

    monkeypatch.setattr(victory_road, "_pulse", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(victory_road, "_settle_confirm", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(victory_road, "run_adaptive_trainer_battle", run_battle)
    monkeypatch.setattr(victory_road, "switch_active_battler", switch)
    monkeypatch.setattr(victory_road, "_battle_hyper_potion", heal)
    monkeypatch.setattr(victory_road, "_party_hp", lambda _emulator: (150, 0, 57, 139, 69, 70))
    monkeypatch.setattr(victory_road, "_bag", lambda _emulator: {ItemId.HYPER_POTION: 1})
    monkeypatch.setattr(
        victory_road,
        "_battle_sacrifice",
        lambda *_args, **_kwargs: pytest.fail("balanced-team pivot used sacrifice recovery"),
    )

    _, potions = victory_road._defeat_route22_rival(
        object(),  # type: ignore[arg-type]
        reader,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
    )

    assert frozenset() == victory_road.ROUTE_22_PROACTIVE_PIVOT_SPECIES
    assert switches == []
    assert heals == 1
    assert potions == 1


def _route22_party(
    party_hp: tuple[int, ...],
    party_max_hp: tuple[int, ...],
    active_party_index: int = 0,
) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_22,
        player_x=30,
        player_y=5,
        party_count=len(party_hp),
        party_hp=party_hp,
        party_max_hp=party_max_hp,
        battle_state=2,
        active_party_index=active_party_index,
        active_party_hp=party_hp[active_party_index],
    )


def test_battle_ready_pivot_rejects_reserves_that_would_only_absorb_damage() -> None:
    """A living-but-fragile reserve is damage padding, not a strategic switch."""

    raw = _route22_party(
        party_hp=(150, 5, 12, 4, 3, 2),
        party_max_hp=(150, 100, 100, 100, 100, 100),
    )
    assert _route22_battle_ready_pivot_target(raw, 1) is None


def test_battle_ready_pivot_selects_a_healthy_reserve_at_or_after_the_request() -> None:
    raw = _route22_party(
        party_hp=(150, 10, 90, 95, 5, 80),
        party_max_hp=(150, 100, 100, 100, 100, 100),
    )
    assert _route22_battle_ready_pivot_target(raw, 1) == 2
    assert _route22_battle_ready_pivot_target(raw, 3) == 3
    # A request past every candidate wraps to the first healthy reserve rather
    # than falling through to a fragile one.
    assert _route22_battle_ready_pivot_target(raw, 6) == 2


def test_battle_ready_pivot_never_returns_the_lead_or_the_active_member() -> None:
    raw = _route22_party(
        party_hp=(150, 100, 100, 0, 0, 0),
        party_max_hp=(150, 100, 100, 100, 100, 100),
        active_party_index=1,
    )
    chosen = _route22_battle_ready_pivot_target(raw, 1)
    assert chosen == 2
    assert chosen != 0


def test_battle_ready_pivot_ignores_members_without_a_known_maximum() -> None:
    raw = _route22_party(
        party_hp=(150, 90, 90),
        party_max_hp=(150, 0, 100),
    )
    assert _route22_battle_ready_pivot_target(raw, 1) == 2


def test_route22_pivot_budget_permits_a_decision_not_a_sacrifice_loop() -> None:
    """One switch is a strategic choice; walking six members is the V35 wipe."""

    assert ROUTE_22_MAX_TEAM_PIVOTS == 1
    assert 0 < ROUTE_22_PIVOT_MIN_HP_RATIO < 1
    assert frozenset() == ROUTE_22_PROACTIVE_PIVOT_SPECIES
