from __future__ import annotations

from dataclasses import fields, replace

import pytest

import pokemon_red_completion.lavender as lavender_module
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    LAVENDER_CHECKPOINT_COUNT,
    PROTECTED_PARTY,
    LavenderChapterReport,
    LavenderCheckpoint,
    LavenderTiming,
    TrainerEvidence,
)
from pokemon_red_completion.observation import MapId, RawGameState


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.LAVENDER_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=3,
        battle_state=0,
        party_species_ids=PROTECTED_PARTY,
        first_party_hp=79,
        first_party_max_hp=79,
        first_party_status=0,
        first_party_moves=(44, 39, 61, 55),
        first_party_pp=(25, 30, 20, 25),
    )


def _report() -> LavenderChapterReport:
    raw = _raw()
    records = tuple(
        LavenderCheckpoint(f"gate_{index}", f"Gate {index}", raw)
        for index in range(LAVENDER_CHECKPOINT_COUNT)
    )
    trainers = tuple(
        TrainerEvidence(
            f"trainer {index}",
            MapId.ROCK_TUNNEL_1F,
            0x441 + index,
            0xCE,
            0x06,
            index + 1,
            44,
            1,
        )
        for index in range(11)
    )
    return LavenderChapterReport(
        records=records,
        trainers=trainers,
        wild_flees=(),
        final_raw=raw,
        party_hp=(79, 52, 37),
        party_max_hp=(79, 52, 37),
        party_status=(0, 0, 0),
        repels_purchased=4,
        repels_used=4,
        super_potions_purchased=8,
        super_potions_used=5,
        super_potions_remaining=4,
        purchase_cost=7000,
        money_remaining=1234,
        route_10_trainer_2_bypassed=True,
        frames_executed=100,
        actions_executed=50,
        controller_released=True,
    )


def test_lavender_timing_is_positive_and_bounded() -> None:
    assert LavenderTiming() == DEFAULT_LAVENDER_TIMING
    assert all(
        isinstance(getattr(DEFAULT_LAVENDER_TIMING, field.name), int)
        and getattr(DEFAULT_LAVENDER_TIMING, field.name) > 0
        for field in fields(LavenderTiming)
    )


@pytest.mark.parametrize("invalid", (0, -1, True, 1.5))
def test_lavender_timing_rejects_invalid_bounds(invalid: object) -> None:
    for field in fields(LavenderTiming):
        with pytest.raises(ValueError, match=f"{field.name} must be a positive integer"):
            replace(DEFAULT_LAVENDER_TIMING, **{field.name: invalid})


def test_lavender_report_requires_all_route_resource_and_party_gates() -> None:
    report = _report()
    assert report.passed

    invalid = (
        replace(report, records=report.records[:-1]),
        replace(report, trainers=report.trainers[:-1]),
        replace(report, trainers=report.trainers[:-1] + (report.trainers[0],)),
        replace(report, party_hp=(78, 52, 37)),
        replace(report, party_status=(0, 8, 0)),
        replace(report, repels_used=3),
        replace(report, super_potions_remaining=3),
        replace(report, purchase_cost=6999),
        replace(report, route_10_trainer_2_bypassed=False),
        replace(report, controller_released=False),
    )
    assert all(not candidate.passed for candidate in invalid)


def test_lavender_public_report_exposes_exact_resources_and_trainers() -> None:
    public = _report().public_dict()

    assert public["status"] == "ok"
    assert len(public["trainer_battles"]) == 11
    assert public["inventory"] == {
        "repels_purchased": 4,
        "repels_used": 4,
        "super_potions_purchased": 8,
        "super_potions_used": 5,
        "super_potions_remaining": 4,
        "purchase_cost": 7000,
        "money_remaining": 1234,
    }
    assert public["route_10_trainer_2_bypassed"] is True
    assert public["party"]["species"] == list(PROTECTED_PARTY)


def test_move_retries_the_same_step_after_a_no_movement_wild_flee(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Runtime:
        def __init__(self) -> None:
            self.raw = replace(
                _raw(),
                map_id=MapId.ROUTE_9,
                player_x=1,
                player_y=1,
                battle_state=0,
            )
            self.move_pulses = 0

        def execute(self, action: object) -> None:
            if getattr(action, "kind", None) is not MacroActionKind.MOVE:
                return
            self.move_pulses += 1
            if self.move_pulses == 1:
                self.raw = replace(self.raw, battle_state=1)
            else:
                self.raw = replace(self.raw, player_x=2)

        def read(self) -> RawGameState:
            return self.raw

    runtime = Runtime()

    def qualified_flee(*_args: object) -> None:
        runtime.raw = replace(runtime.raw, battle_state=0)

    monkeypatch.setattr(lavender_module, "_flee", qualified_flee)
    final = lavender_module._move(
        runtime,
        runtime,
        runtime,
        lavender_module._RunState([], []),
        ("right",),
        LavenderTiming(movement_retries=2),
        "wild retry regression",
    )

    assert runtime.move_pulses == 2
    assert (final.player_x, final.player_y) == (2, 1)
