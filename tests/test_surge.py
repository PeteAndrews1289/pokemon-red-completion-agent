from __future__ import annotations

from dataclasses import fields, replace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.observation import (
    Badge,
    BattleMenuPhase,
    BattleMenuState,
    MapId,
    RawGameState,
)
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.surge import (
    CATERPIE_SPECIES_ID,
    COLLECTION_POKE_BALL_TARGET,
    DEFAULT_SURGE_TIMING,
    DIG_MOVE_ID,
    DIGLETT_CAPTURE_LEVELS,
    DIGLETT_SEARCH_SEED_WAIT_FRAMES,
    DUX_NICKNAME,
    GYM_CAN_COORDINATES,
    KAKUNA_SPECIES_ID,
    LT_SURGE_OPPONENT_ID,
    LT_SURGE_TRAINER_CLASS_ID,
    LT_SURGE_TRAINER_SET,
    METAPOD_SPECIES_ID,
    PIDGEY_SPECIES_ID,
    PIKACHU_SPECIES_ID,
    RATTATA_SPECIES_ID,
    SPEAROW_CAPTURE_LEVELS,
    SPEAROW_CAPTURE_MOVE_ID,
    SPEAROW_CAPTURE_MOVE_SLOT,
    SPEAROW_WEAKEN_ATTEMPT_LIMIT,
    SURGE_CHECKPOINT_COUNT,
    VIRIDIAN_FOREST_MAX_SURVEY_LEGS,
    WILD_CAPTURE_DIRECT_THROW_SPECIES,
    WILD_CAPTURE_HIGH_RISK_HELPER_HP_RATIO,
    WILD_CAPTURE_HIGH_RISK_SPECIES,
    WILD_CAPTURE_MAX_WEAKENING_ATTACKS,
    WILD_CAPTURE_PASSIVE_POLICY,
    WILD_CAPTURE_PASSIVE_SPECIES,
    WILD_CAPTURE_POLICY,
    WILD_CAPTURE_THROWS_PER_ENCOUNTER,
    SurgeChapterReport,
    SurgeCheckpoint,
    SurgeTiming,
    _LiveWildCorridorSurveyExecutor,
    _navigate_to_gym_can,
    _party_moves_for_index,
    _plan_gym_can_path,
    _run_dig_battle,
    _select_wild_capture_helper,
    _wild_capture_policy,
    _wild_capture_weakening_budget,
    _wild_weakening_settle_action,
    _wild_weakening_turn_result,
)


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.VERMILION_GYM,
        player_x=5,
        player_y=2,
        party_count=2,
        battle_state=0,
        badge_bits=int(Badge.BOULDER | Badge.CASCADE | Badge.THUNDER),
        party_species_ids=(0xB3, 0x40),
        first_party_hp=48,
        first_party_max_hp=73,
        first_party_status=0,
        first_party_moves=(44, DIG_MOVE_ID, 145, 55),
        first_party_pp=(25, 7, 30, 25),
    )


def _report() -> SurgeChapterReport:
    raw = replace(_raw(), first_party_hp=73)
    records = tuple(
        SurgeCheckpoint(f"gate_{index}", f"Gate {index}", raw)
        for index in range(SURGE_CHECKPOINT_COUNT)
    )
    return SurgeChapterReport(
        records=records,
        final_raw=raw,
        beat_lt_surge=True,
        got_tm24=True,
        tm24_in_bag=True,
        badge_bits=int(Badge.BOULDER | Badge.CASCADE | Badge.THUNDER),
        badge_mirror_bits=int(Badge.BOULDER | Badge.CASCADE | Badge.THUNDER),
        dig_attacks=3,
        wrong_move_count=0,
        super_potion_used=True,
        final_lead_hp=73,
        final_lead_max_hp=73,
        frames_executed=100,
        actions_executed=20,
        controller_released=True,
    )


def test_source_pinned_surge_identity_and_dux_constants() -> None:
    assert LT_SURGE_OPPONENT_ID == 0xEC
    assert LT_SURGE_TRAINER_CLASS_ID == 0x24
    assert LT_SURGE_TRAINER_SET == 1
    assert DIG_MOVE_ID == 0x5B
    assert frozenset({17, 18, 19, 20, 21, 22}) == DIGLETT_CAPTURE_LEVELS
    assert DIGLETT_SEARCH_SEED_WAIT_FRAMES == 199
    assert (SPEAROW_CAPTURE_MOVE_ID, SPEAROW_CAPTURE_MOVE_SLOT) == (0x37, 4)
    assert frozenset({17}) == SPEAROW_CAPTURE_LEVELS
    assert SPEAROW_WEAKEN_ATTEMPT_LIMIT == 12
    assert DUX_NICKNAME == (0x83, 0x94, 0x97, 0x50)
    assert SURGE_CHECKPOINT_COUNT == 15
    assert COLLECTION_POKE_BALL_TARGET == 30
    assert (
        CATERPIE_SPECIES_ID,
        METAPOD_SPECIES_ID,
        KAKUNA_SPECIES_ID,
        PIKACHU_SPECIES_ID,
    ) == (0x7B, 0x7C, 0x71, 0x54)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"label": " "}, "label must not be empty"),
        ({"forward_directions": ()}, "requires movement directions"),
        ({"starting_endpoint": "east"}, "must be south or north"),
        ({"max_legs": 0}, "must be a positive integer"),
        ({"max_legs": True}, "must be a positive integer"),
    ],
)
def test_live_wild_corridor_rejects_ambiguous_source_contracts(
    overrides: dict[str, object],
    message: str,
) -> None:
    arguments: dict[str, object] = {
        "label": "Viridian Forest",
        "forward_directions": ("up",),
        "starting_endpoint": "south",
        "max_legs": 64,
    }
    arguments.update(overrides)

    with pytest.raises(ValueError, match=message):
        _LiveWildCorridorSurveyExecutor(
            object(),
            object(),
            object(),
            DEFAULT_SURGE_TIMING,
            **arguments,
        )


class _PartyMoveMemory:
    def __init__(self) -> None:
        self.values = {
            0xD19F: 0x40,
            0xD1A0: 0x1C,
            0xD1A1: 0x0F,
            0xD1A2: 0x1F,
        }

    def read_u8(self, address: int) -> int:
        return self.values.get(address, 0)


def test_party_move_lookup_reads_dux_struct_instead_of_lead_moves() -> None:
    raw = replace(_raw(), first_party_moves=(44, 39, 61, 55))

    assert _party_moves_for_index(_PartyMoveMemory(), raw, 1) == (0x40, 0x1C, 0x0F, 0x1F)


def test_surge_timing_is_positive_and_bounded() -> None:
    assert SurgeTiming() == DEFAULT_SURGE_TIMING
    assert DEFAULT_SURGE_TIMING.encounter_steps == 1800
    assert DEFAULT_SURGE_TIMING.encounter_limit == 72
    assert DEFAULT_SURGE_TIMING.spearow_encounter_limit == 96
    assert WILD_CAPTURE_THROWS_PER_ENCOUNTER == 5
    assert WILD_CAPTURE_MAX_WEAKENING_ATTACKS == 8
    assert VIRIDIAN_FOREST_MAX_SURVEY_LEGS == 256
    assert frozenset({PIKACHU_SPECIES_ID}) == WILD_CAPTURE_DIRECT_THROW_SPECIES
    assert frozenset({PIKACHU_SPECIES_ID}) == WILD_CAPTURE_HIGH_RISK_SPECIES
    assert WILD_CAPTURE_HIGH_RISK_HELPER_HP_RATIO == 0.75
    assert frozenset({METAPOD_SPECIES_ID, KAKUNA_SPECIES_ID}) == WILD_CAPTURE_PASSIVE_SPECIES
    assert all(
        isinstance(getattr(DEFAULT_SURGE_TIMING, field.name), int)
        and getattr(DEFAULT_SURGE_TIMING, field.name) > 0
        for field in fields(SurgeTiming)
    )


def test_passive_cocoons_receive_deeper_bounded_weakening_policy() -> None:
    assert _wild_capture_policy(METAPOD_SPECIES_ID) is WILD_CAPTURE_PASSIVE_POLICY
    assert _wild_capture_policy(KAKUNA_SPECIES_ID) is WILD_CAPTURE_PASSIVE_POLICY
    assert WILD_CAPTURE_PASSIVE_POLICY.throw_at_or_below_hp_ratio == 0.30
    assert WILD_CAPTURE_POLICY.throw_at_or_below_hp_ratio == 0.65
    assert _wild_capture_policy(CATERPIE_SPECIES_ID) is WILD_CAPTURE_POLICY
    assert _wild_capture_policy(PIKACHU_SPECIES_ID) is WILD_CAPTURE_POLICY


def test_weakening_budget_covers_one_damage_cocoon_hits() -> None:
    assert _wild_capture_weakening_budget(METAPOD_SPECIES_ID, 15, 18) == 10
    assert _wild_capture_weakening_budget(KAKUNA_SPECIES_ID, 18, 18) == 13
    assert _wild_capture_weakening_budget(CATERPIE_SPECIES_ID, 18, 18) == 8


def test_weakening_settle_cancels_a_returned_move_menu() -> None:
    assert (
        _wild_weakening_settle_action(BattleMenuPhase.MOVE, 0)
        is MacroActionKind.CANCEL
    )
    assert (
        _wild_weakening_settle_action(BattleMenuPhase.UNKNOWN, 0)
        is MacroActionKind.CONFIRM
    )


def test_weakening_miss_settles_without_requesting_another_attack() -> None:
    common = {
        "expected_species_id": KAKUNA_SPECIES_ID,
        "before_enemy_hp": 22,
        "current_species_id": KAKUNA_SPECIES_ID,
        "pp_spent": True,
        "phase": BattleMenuPhase.MAIN,
    }

    assert _wild_weakening_turn_result(current_enemy_hp=22, **common) is False
    assert _wild_weakening_turn_result(current_enemy_hp=20, **common) is True
    assert (
        _wild_weakening_turn_result(
            current_enemy_hp=22,
            **{**common, "phase": BattleMenuPhase.MOVE},
        )
        is None
    )


def test_wild_capture_helper_prefers_safe_rattata_tackle() -> None:
    party = PartyObservation(
        (
            PartyMemberObservation(
                slot=1,
                species_id=0xB3,
                level=26,
                hp=70,
                max_hp=70,
                moves=(MoveObservation(0x2C, 25),),
            ),
            PartyMemberObservation(
                slot=2,
                species_id=PIDGEY_SPECIES_ID,
                level=4,
                hp=16,
                max_hp=16,
                moves=(MoveObservation(0x10, 35),),
            ),
            PartyMemberObservation(
                slot=3,
                species_id=RATTATA_SPECIES_ID,
                level=3,
                hp=15,
                max_hp=15,
                moves=(MoveObservation(0x21, 35),),
            ),
        )
    )

    assert _select_wild_capture_helper(party) == (2, 0)


def test_wild_capture_helper_rejects_unsafe_or_unusable_members() -> None:
    party = PartyObservation(
        (
            PartyMemberObservation(
                slot=1,
                species_id=RATTATA_SPECIES_ID,
                level=3,
                hp=4,
                max_hp=15,
                moves=(MoveObservation(0x21, 35),),
            ),
            PartyMemberObservation(
                slot=2,
                species_id=PIDGEY_SPECIES_ID,
                level=4,
                hp=16,
                max_hp=16,
                status=StatusCondition.PARALYSIS,
                moves=(MoveObservation(0x10, 35),),
            ),
            PartyMemberObservation(
                slot=3,
                species_id=CATERPIE_SPECIES_ID,
                level=3,
                hp=15,
                max_hp=15,
                moves=(MoveObservation(0x21, 0),),
            ),
        )
    )

    assert _select_wild_capture_helper(party) is None


def test_high_risk_capture_helper_requires_a_large_hp_reserve() -> None:
    party = PartyObservation(
        (
            PartyMemberObservation(
                slot=1,
                species_id=RATTATA_SPECIES_ID,
                level=3,
                hp=11,
                max_hp=15,
                moves=(MoveObservation(0x21, 35),),
            ),
            PartyMemberObservation(
                slot=2,
                species_id=CATERPIE_SPECIES_ID,
                level=3,
                hp=15,
                max_hp=15,
                moves=(MoveObservation(0x21, 35),),
            ),
        )
    )

    assert _select_wild_capture_helper(party) == (0, 0)
    assert _select_wild_capture_helper(party, minimum_hp_ratio=0.75) == (1, 0)


@pytest.mark.parametrize("invalid", (0, -1, True, 1.5))
def test_surge_timing_rejects_invalid_bounds(invalid: object) -> None:
    for field in fields(SurgeTiming):
        with pytest.raises(ValueError, match=f"{field.name} must be a positive integer"):
            replace(DEFAULT_SURGE_TIMING, **{field.name: invalid})


def test_surge_report_requires_every_terminal_reward_gate() -> None:
    report = _report()
    assert report.passed

    invalid_reports = (
        replace(report, records=report.records[:-1]),
        replace(report, beat_lt_surge=False),
        replace(report, got_tm24=False),
        replace(report, tm24_in_bag=False),
        replace(report, badge_bits=int(Badge.BOULDER | Badge.CASCADE)),
        replace(report, badge_mirror_bits=int(Badge.BOULDER | Badge.CASCADE)),
        replace(report, dig_attacks=2),
        replace(report, wrong_move_count=1),
        replace(report, final_raw=replace(report.final_raw, battle_state=2)),
        replace(report, final_raw=replace(report.final_raw, first_party_status=4)),
        replace(report, final_lead_hp=0),
        replace(report, final_lead_hp=74),
        replace(report, controller_released=False),
    )
    assert all(not candidate.passed for candidate in invalid_reports)


def test_surge_report_allows_safe_damage_for_immediate_center_recovery() -> None:
    report = _report()
    damaged = replace(
        report,
        final_raw=replace(report.final_raw, first_party_hp=21),
        final_lead_hp=21,
        super_potion_used=False,
    )

    assert damaged.passed


def test_surge_public_report_exposes_zero_wrong_moves() -> None:
    public = _report().public_dict()

    assert public["status"] == "ok"
    assert public["battle"] == {"dig_attacks": 3, "wrong_move_count": 0}
    assert public["reward"] == {
        "beat_lt_surge": True,
        "got_tm24": True,
        "tm24_in_bag": True,
        "thunder_badge": True,
        "thunder_badge_mirror": True,
    }
    assert public["recovery"] == {
        "super_potion_used": True,
        "lead_hp": 73,
        "lead_max_hp": 73,
        "status": 0,
    }


class _PositiveHpSwitchPrompt:
    def __init__(self) -> None:
        self.raw = replace(_raw(), battle_state=2, enemy_hp=0)
        self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
        self.actions: list[MacroAction] = []
        self.cancel_count = 0

    def read(self) -> RawGameState:
        return self.raw

    def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
        assert raw is self.raw
        return self.menu

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)
        if action.kind is not MacroActionKind.CANCEL:
            return
        self.cancel_count += 1
        if self.cancel_count == 1:
            self.raw = replace(self.raw, enemy_hp=43)
        else:
            self.raw = replace(self.raw, battle_state=0)


def test_post_ko_positive_enemy_hp_prompt_is_cancel_only() -> None:
    runtime = _PositiveHpSwitchPrompt()

    final, dig_attacks, super_potion_used = _run_dig_battle(runtime, runtime, SurgeTiming())

    assert final.battle_state == 0
    assert dig_attacks == 0
    assert super_potion_used is False
    assert [
        action.kind for action in runtime.actions if action.kind is not MacroActionKind.WAIT
    ] == [MacroActionKind.CANCEL, MacroActionKind.CANCEL]


def test_low_hp_main_gate_uses_one_bounded_surge_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _PositiveHpSwitchPrompt()
    runtime.raw = replace(runtime.raw, enemy_hp=43, first_party_hp=10)
    runtime.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)
    calls: list[int] = []

    def recover(executor, reader, emulator, timing) -> None:
        assert executor is runtime
        assert reader is runtime
        calls.append(runtime.raw.first_party_hp or 0)
        runtime.raw = replace(runtime.raw, first_party_hp=30, battle_state=0)

    monkeypatch.setattr("pokemon_red_completion.surge._use_surge_super_potion", recover)

    final, dig_attacks, super_potion_used = _run_dig_battle(
        runtime, runtime, SurgeTiming(), emulator=object()
    )

    assert final.battle_state == 0
    assert dig_attacks == 0
    assert super_potion_used is True
    assert calls == [10]


def _route_end(
    start: tuple[int, int],
    route: tuple[str, ...],
) -> tuple[int, int]:
    coordinate = start
    deltas = {
        "up": (0, -1),
        "down": (0, 1),
        "left": (-1, 0),
        "right": (1, 0),
    }
    for direction in route:
        dx, dy = deltas[direction]
        coordinate = (coordinate[0] + dx, coordinate[1] + dy)
    return coordinate


@pytest.mark.parametrize(("first", "second"), ((12, 0), (12, 13), (6, 7)))
def test_gym_planner_supports_variable_switch_pairs(first: int, second: int) -> None:
    start = (4, 17)
    first_route, first_facing = _plan_gym_can_path(start, first)
    first_stance = _route_end(start, first_route)
    second_route, second_facing = _plan_gym_can_path(first_stance, second)
    second_stance = _route_end(first_stance, second_route)
    deltas = {
        "up": (0, -1),
        "down": (0, 1),
        "left": (-1, 0),
        "right": (1, 0),
    }

    first_delta = deltas[first_facing]
    second_delta = deltas[second_facing]
    assert (
        first_stance[0] + first_delta[0],
        first_stance[1] + first_delta[1],
    ) == GYM_CAN_COORDINATES[first]
    assert (
        second_stance[0] + second_delta[0],
        second_stance[1] + second_delta[1],
    ) == GYM_CAN_COORDINATES[second]


class _GymCollisionRuntime:
    def __init__(self) -> None:
        self.coordinate = (4, 17)
        self.hit_dynamic_block = False

    def read(self) -> RawGameState:
        return replace(
            _raw(),
            map_id=MapId.VERMILION_GYM,
            player_x=self.coordinate[0],
            player_y=self.coordinate[1],
            battle_state=0,
        )

    def execute(self, action: MacroAction) -> None:
        if action.kind is not MacroActionKind.MOVE or action.value is None:
            return
        deltas = {
            "up": (0, -1),
            "down": (0, 1),
            "left": (-1, 0),
            "right": (1, 0),
        }
        dx, dy = deltas[action.value]
        candidate = (self.coordinate[0] + dx, self.coordinate[1] + dy)
        if candidate == (3, 14):
            self.hit_dynamic_block = True
            return
        if candidate in GYM_CAN_COORDINATES:
            return
        self.coordinate = candidate


def test_gym_can_navigation_discovers_collision_and_replans() -> None:
    runtime = _GymCollisionRuntime()

    final = _navigate_to_gym_can(
        runtime,  # type: ignore[arg-type]
        runtime,  # type: ignore[arg-type]
        6,
        SurgeTiming(),
    )

    target = GYM_CAN_COORDINATES[6]
    assert runtime.hit_dynamic_block
    assert abs((final.player_x or 0) - target[0]) + abs((final.player_y or 0) - target[1]) == 1
