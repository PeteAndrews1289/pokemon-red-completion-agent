"""M0: a capture-status target-HP drift settles as an ordinary failed capture.

Observed TRAIN stop (opus55-session20 gen4-c004): during status preparation the
wild target lost 2 HP while map, party and bag were unchanged; the run stopped in
battle. The corridor survey (which already settles a lost catcher) now escapes
and records the drift instead, only while custody and the same live target hold.
ROM-free: no emulator, native input, model or fit.
"""

from dataclasses import replace

import pytest
from test_capture_health_stop import _ordinary_health_fixture
from test_red_capture_status_runtime import setup

import pokemon_red_completion.red_capture_status_runtime as status_runtime
import pokemon_red_completion.surge as surge
from pokemon_red_completion.red_capture_status_runtime import (
    CaptureStatusDrift,
    RedCaptureStatusError,
)
from pokemon_red_completion.red_collection import red_internal_species_number, red_species_ref


def _drift(monkeypatch, world, mutate=None):
    fault = RedCaptureStatusError(
        "capture status target HP changed", reason_code=CaptureStatusDrift.TARGET_HP
    )

    def fail(_self):
        world.raw = replace(world.raw, enemy_hp=world.raw.enemy_hp - 2)
        if mutate is not None:
            mutate(world)
        raise fault

    monkeypatch.setattr(status_runtime.RedCaptureStatusPreparer, "__call__", fail)
    return fault


def test_target_hp_drift_escapes_and_returns_ordinary_failed_capture(monkeypatch):
    world, live, target, bag, retained, calls = _ordinary_health_fixture(monkeypatch)
    before_bag = dict(bag)
    _drift(monkeypatch, world)

    def escape(*_args):
        calls.append("bounded_escape")
        world.raw = replace(world.raw, battle_state=0)

    monkeypatch.setattr(surge, "_flee", escape)
    assert live.capture_encounter(target) is False
    assert calls == ["bounded_escape"]
    assert live.capture_drift_settlements == 1
    assert live.capture_health_stopped is False
    assert world.raw.battle_state == 0 and retained == [2] and bag == before_bag
    assert live.capture_throw_preparations == []


@pytest.mark.parametrize(
    "fault",
    ["battle_ended", "target_fainted", "party_species", "bag", "map", "species"],
)
def test_target_hp_drift_without_custody_proof_still_stops(monkeypatch, fault):
    world, live, target, bag, _retained, calls = _ordinary_health_fixture(monkeypatch)

    def mutate(w):
        if fault == "battle_ended":
            w.raw = replace(w.raw, battle_state=0)
        elif fault == "target_fainted":
            w.raw = replace(w.raw, enemy_hp=0)
        elif fault == "party_species":
            w.raw = replace(w.raw, party_species_ids=(1, 2, 3))
        elif fault == "bag":
            w.raw = replace(w.raw, bag_items=((4, 1),))
        elif fault == "map":
            w.raw = replace(w.raw, map_id=(w.raw.map_id + 1) % 256)
        else:
            w.raw = replace(w.raw, enemy_species_id=w.raw.enemy_species_id + 1)

    raised = _drift(monkeypatch, world, mutate)
    monkeypatch.setattr(surge, "_flee", lambda *a: calls.append("must-not-escape"))
    with pytest.raises(RedCaptureStatusError) as caught:
        live.capture_encounter(target)
    assert caught.value is raised
    assert calls == [] and live.capture_drift_settlements == 0


def test_unopted_capture_users_keep_the_target_hp_stop(monkeypatch):
    world, _ = setup(monkeypatch)
    live = surge.LiveWildEncounterExecutor(
        object(),
        object(),
        world,
        surge.DEFAULT_SURGE_TIMING,
        label="unopted fishing or travel user",
        capture_status_support=True,
    )
    monkeypatch.setattr(surge, "_bag", lambda _: {4: 4})
    monkeypatch.setattr(surge, "_living_specimen_count", lambda _: 2)
    monkeypatch.setattr(surge, "_flee", lambda *a: pytest.fail("unopted user must not escape"))
    _drift(monkeypatch, world)
    target = red_species_ref(red_internal_species_number(world.raw.enemy_species_id))
    with pytest.raises(RedCaptureStatusError) as caught:
        live.capture_encounter(target)
    assert caught.value.reason_code == CaptureStatusDrift.TARGET_HP.value
    assert live.capture_drift_settlements == 0
