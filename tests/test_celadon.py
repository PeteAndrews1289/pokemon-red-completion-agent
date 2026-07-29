from __future__ import annotations

from dataclasses import fields, replace

import pytest

import pokemon_red_completion.celadon as celadon_module
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.celadon import (
    BITE,
    CELADON_CHECKPOINT_COUNT,
    DEFAULT_CELADON_TIMING,
    PROTECTED_PARTY,
    CeladonChapterReport,
    CeladonCheckpoint,
    CeladonTiming,
    Route8TrainerEvidence,
)
from pokemon_red_completion.observation import EventFlag, MapId, RawGameState


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.CELADON_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=3,
        battle_state=0,
        party_species_ids=PROTECTED_PARTY,
        first_party_hp=81,
        first_party_max_hp=81,
        first_party_status=0,
        first_party_moves=(44, 39, 61, 55),
        first_party_pp=(20, 30, 20, 25),
    )


def _report() -> CeladonChapterReport:
    raw = _raw()
    return CeladonChapterReport(
        records=tuple(
            CeladonCheckpoint(f"gate_{index}", f"Gate {index}", raw)
            for index in range(CELADON_CHECKPOINT_COUNT)
        ),
        trainers=(
            Route8TrainerEvidence(
                "Route 8 Lass",
                MapId.ROUTE_8,
                EventFlag.BEAT_ROUTE_8_TRAINER_8,
                0xCB,
                0x03,
                16,
                BITE,
                5,
            ),
        ),
        wild_flees=(),
        route_8_events_before=(False,) * 9,
        route_8_events_after=(False,) * 8 + (True,),
        final_raw=raw,
        party_hp=(81, 52, 37),
        party_max_hp=(81, 52, 37),
        party_status=(0, 0, 0),
        super_potions_remaining=4,
        repels_remaining=0,
        money_remaining=14_631,
        frames_executed=100,
        actions_executed=50,
        controller_released=True,
    )


def test_celadon_timing_is_positive_and_bounded() -> None:
    assert CeladonTiming() == DEFAULT_CELADON_TIMING
    assert all(
        isinstance(getattr(DEFAULT_CELADON_TIMING, field.name), int)
        and getattr(DEFAULT_CELADON_TIMING, field.name) > 0
        for field in fields(CeladonTiming)
    )


@pytest.mark.parametrize("invalid", (0, -1, True, 1.5))
def test_celadon_timing_rejects_invalid_bounds(invalid: object) -> None:
    for field in fields(CeladonTiming):
        with pytest.raises(ValueError, match=f"{field.name} must be a positive integer"):
            replace(DEFAULT_CELADON_TIMING, **{field.name: invalid})


def test_celadon_report_requires_exact_trainer_resources_and_party_gates() -> None:
    report = _report()
    assert report.passed
    invalid = (
        replace(report, records=report.records[:-1]),
        replace(report, trainers=()),
        replace(report, route_8_events_before=(True,) + (False,) * 8),
        replace(report, route_8_events_after=(False,) * 9),
        replace(report, party_hp=(80, 52, 37)),
        replace(report, party_status=(0, 8, 0)),
        replace(report, super_potions_remaining=3),
        replace(report, money_remaining=14_630),
        replace(report, controller_released=False),
    )
    assert all(not candidate.passed for candidate in invalid)


def test_celadon_public_report_exposes_exact_route_evidence() -> None:
    public = _report().public_dict()
    assert public["status"] == "ok"
    assert public["route_8_trainers_bypassed"] == list(range(8))
    assert public["trainer_battles"] == [{
        "label": "Route 8 Lass",
        "map_id": MapId.ROUTE_8,
        "event": EventFlag.BEAT_ROUTE_8_TRAINER_8,
        "opponent": 0xCB,
        "class": 0x03,
        "set": 16,
        "move_id": BITE,
        "selected_pp_spent": 5,
    }]
    assert public["inventory"] == {
        "super_potions_remaining": 4,
        "repels_remaining": 0,
        "money_remaining": 14_631,
    }


def test_move_retries_the_same_step_after_a_no_movement_wild_flee(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Runtime:
        def __init__(self) -> None:
            self.raw = replace(
                _raw(), map_id=MapId.ROUTE_8, player_x=1, player_y=1, battle_state=0
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

        def read_input_readiness(self) -> object:
            return type("Ready", (), {"ready": True})()

    runtime = Runtime()

    def qualified_flee(*_args: object) -> None:
        runtime.raw = replace(runtime.raw, battle_state=0)

    monkeypatch.setattr(celadon_module, "_flee", qualified_flee)
    final = celadon_module._move(
        runtime,
        runtime,
        runtime,
        celadon_module._RunState([]),
        ("right",),
        CeladonTiming(movement_retries=2),
        "wild retry regression",
    )
    assert runtime.move_pulses == 2
    assert (final.player_x, final.player_y) == (2, 1)
