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
from pokemon_red_completion.surge import (
    DEFAULT_SURGE_TIMING,
    DIG_MOVE_ID,
    DUX_NICKNAME,
    GYM_CAN_COORDINATES,
    LT_SURGE_OPPONENT_ID,
    LT_SURGE_TRAINER_CLASS_ID,
    LT_SURGE_TRAINER_SET,
    SURGE_CHECKPOINT_COUNT,
    SurgeChapterReport,
    SurgeCheckpoint,
    SurgeTiming,
    _plan_gym_can_path,
    _run_dig_battle,
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
    raw = _raw()
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
    assert DUX_NICKNAME == (0x83, 0x94, 0x97, 0x50)
    assert SURGE_CHECKPOINT_COUNT == 15


def test_surge_timing_is_positive_and_bounded() -> None:
    assert SurgeTiming() == DEFAULT_SURGE_TIMING
    assert all(
        isinstance(getattr(DEFAULT_SURGE_TIMING, field.name), int)
        and getattr(DEFAULT_SURGE_TIMING, field.name) > 0
        for field in fields(SurgeTiming)
    )


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
        replace(report, final_lead_hp=72),
        replace(report, controller_released=False),
    )
    assert all(not candidate.passed for candidate in invalid_reports)


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

    final, dig_attacks = _run_dig_battle(runtime, runtime, SurgeTiming())

    assert final.battle_state == 0
    assert dig_attacks == 0
    assert [
        action.kind for action in runtime.actions if action.kind is not MacroActionKind.WAIT
    ] == [MacroActionKind.CANCEL, MacroActionKind.CANCEL]


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
