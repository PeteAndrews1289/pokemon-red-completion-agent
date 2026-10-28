"""Ordinary capture composes existing status and abstaining damage support."""

from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.red_acquisition import RedAreaExecutionError
from pokemon_red_completion.red_capture_weakening_runtime import CaptureWeakeningResult
from pokemon_red_completion.red_collection import red_internal_species_number, red_species_ref
from pokemon_red_completion.surge import DEFAULT_SURGE_TIMING, LiveWildEncounterExecutor


def capture_fixture(monkeypatch, *, enabled=True, escape=False, ended=False):
    import pokemon_red_completion.red_capture_status_runtime as status
    import pokemon_red_completion.red_capture_weakening_runtime as weakening
    import pokemon_red_completion.surge as surge

    w = NS(raw=RawGameState(True, 35, 5, 30, 1, 1,
        enemy_species_id=108, enemy_level=20, enemy_hp=100, enemy_max_hp=100), calls=[])
    w.read = lambda: w.raw
    w.read_enemy_capture_status = lambda: 0x40

    class Prepared:
        def __init__(self, *_args, **kwargs):
            assert kwargs["expected_original_species_id"] == 108
            self.reports = []
            self.throw_preparations = []
            self.bypassed_for_escape = escape

        def __call__(self):
            w.calls.append("status")
            if ended:
                return False
            self.throw_preparations.append(dict(target_hp=w.raw.enemy_hp,
                target_max_hp=w.raw.enemy_max_hp, target_status="paralysis"))
            return True

    def weaken(reader, actions, **kwargs):
        assert reader is w and kwargs == dict(internal_species=108, level=20, maximum_attempts=3)
        w.calls.append("weaken")
        w.raw = replace(w.raw, enemy_hp=80)
        return CaptureWeakeningResult(2, 20, "no_proven_nonlethal_move", ())

    def throw(*_args, before_throw, **_kwargs):
        for _ in range(2):
            if not before_throw():
                return False
            w.calls.append("ball")
        return True

    monkeypatch.setattr(status, "RedCaptureStatusPreparer", Prepared)
    monkeypatch.setattr(weakening, "prepare_nonlethal_capture", weaken)
    monkeypatch.setattr(surge, "_try_catch_wild", throw)
    live = LiveWildEncounterExecutor(object(), object(), w, DEFAULT_SURGE_TIMING,
        label="ordinary capture", capture_status_support=True,
        capture_weakening_support=enabled)
    target = red_species_ref(red_internal_species_number(108))
    return w, live, target


def test_one_finite_weakening_budget_per_encounter_and_actual_prethrow_hp(monkeypatch):
    w, live, target = capture_fixture(monkeypatch)
    assert live.capture_encounter(target)
    assert w.calls == ["status", "weaken", "ball", "status", "ball"]
    assert len(live.capture_weakening_reports) == 1
    assert live.capture_weakening_reports[0]["damage"] == 20
    assert [row["target_hp"] for row in live.capture_throw_preparations] == [80, 80]


def test_status_only_historical_capture_does_not_gain_damage_actions(monkeypatch):
    w, live, target = capture_fixture(monkeypatch, enabled=False)
    assert live.capture_encounter(target)
    assert w.calls == ["status", "ball", "status", "ball"]
    assert live.capture_weakening_reports == []
    assert [row["target_hp"] for row in live.capture_throw_preparations] == [100, 100]


def test_escape_risk_bypasses_weakening_as_well_as_status_setup(monkeypatch):
    w, live, target = capture_fixture(monkeypatch, escape=True)
    assert live.capture_encounter(target)
    assert "weaken" not in w.calls
    assert live.capture_escape_bypasses == 1


def test_ended_encounter_cannot_receive_weakening_or_a_ball(monkeypatch):
    w, live, target = capture_fixture(monkeypatch, ended=True)
    assert not live.capture_encounter(target)
    assert w.calls == ["status"]


def test_damage_guard_error_is_retained_not_converted_into_a_throw(monkeypatch):
    import pokemon_red_completion.red_capture_weakening_runtime as weakening
    w, live, target = capture_fixture(monkeypatch)

    def fail(*_args, **_kwargs):
        raise RuntimeError("protected capture drift")

    monkeypatch.setattr(weakening, "prepare_nonlethal_capture", fail)
    with pytest.raises(RuntimeError, match="protected capture drift"):
        live.capture_encounter(target)
    assert w.calls == ["status"]
    assert len(live.capture_throw_preparations) == 1


def test_public_weakening_counts_round_trip_without_private_target_or_move_fields():
    from pokemon_red_completion.capture_support import CaptureSupportSummary
    summary = CaptureSupportSummary(1, 1, prepared_throws=2, prepared_paralyzed=2,
        weakening_attempts=2, weakening_hp_removed=20, weakening_abstentions=1)
    assert CaptureSupportSummary.from_evidence(
        {"capture_support": summary.public_dict()}) == summary
    old = CaptureSupportSummary(1, 1).public_dict()
    assert "weakening_attempts" not in old
    assert CaptureSupportSummary.from_evidence(
        {"capture_support": old}) == CaptureSupportSummary(1, 1)
    for extra in ({"weakening_attempts": 2}, {"internal_species": 108},
                  {"weakening_attempts": True, "weakening_hp_removed": 0,
                   "weakening_abstentions": 0}):
        with pytest.raises(ValueError):
            CaptureSupportSummary.from_evidence({"capture_support": {**old, **extra}})


@pytest.mark.parametrize("value", [True, 1, None, "true"])
def test_weakening_requires_boolean_opt_in_and_status_support(value):
    with pytest.raises(ValueError, match="explicit status support"):
        LiveWildEncounterExecutor(object(), object(), object(), DEFAULT_SURGE_TIMING,
            label="guarded", capture_weakening_support=value)


def ordinary_fixture(monkeypatch, *, species=148, moves=(100, 0, 0, 0), caught=False):
    import pokemon_red_completion.surge as surge

    w = NS(raw=RawGameState(True, 36, 4, 5, 6, 1,
        enemy_species_id=species, enemy_level=10, enemy_hp=30, enemy_max_hp=30),
        events=[], throws=0, helpers=0)
    w.read = lambda: w.raw
    w.read_enemy_capture_moves = lambda: moves
    w.record_diagnostic_event = lambda kind, payload: w.events.append((kind, payload))
    live = LiveWildEncounterExecutor(object(), w, w, DEFAULT_SURGE_TIMING,
        label="ordinary capture", capture_status_support=False)
    live._party_reader = NS(read=lambda: NS(members=()))

    def helper(*_args, **_kwargs):
        w.helpers += 1
        return None

    def throw(*_args, **kwargs):
        assert kwargs == {"max_throws": surge.WILD_CAPTURE_THROWS_PER_ENCOUNTER}
        w.throws += 1
        return caught

    monkeypatch.setattr(surge, "_select_wild_capture_helper", helper)
    monkeypatch.setattr(surge, "_try_catch_wild", throw)
    return w, live, red_species_ref(red_internal_species_number(species))


@pytest.mark.parametrize("move", [18, 46, 100])
@pytest.mark.parametrize("species", [108, 148])
@pytest.mark.parametrize("caught", [False, True])
def test_ordinary_escape_capability_skips_helper_not_throw_proof(
    monkeypatch, move, species, caught,
):
    w, live, target = ordinary_fixture(monkeypatch, species=species,
        moves=(move, 0, 0, 0), caught=caught)
    assert live.capture_encounter(target) is caught
    assert w.helpers == 0 and w.throws == 1
    assert live.capture_escape_bypasses == 1
    kind, event = w.events[0]
    assert kind == "capture_preparation_bypassed"
    assert event["outcome"] == "live_target_can_end_encounter"
    assert event["selection_authority"] == "deterministic_capture_support"
    assert event["training_admission"] is False


@pytest.mark.parametrize("move", [33, 93, 144])
def test_ordinary_nonescape_moves_keep_helper_path_even_for_abra(monkeypatch, move):
    w, live, target = ordinary_fixture(monkeypatch, moves=(move, 0, 0, 0))
    assert not live.capture_encounter(target)
    assert w.helpers == 1 and w.throws == 1
    assert live.capture_escape_bypasses == 0 and not w.events


def test_ordinary_unknown_target_moves_reject_without_inputs(monkeypatch):
    w, live, target = ordinary_fixture(monkeypatch, moves=None)
    with pytest.raises(RedAreaExecutionError) as error:
        live.capture_encounter(target)
    assert error.value.reason_code == "capture_moves_evidence_missing"
    assert w.helpers == w.throws == 0 and not w.events


def test_escape_bypass_keeps_native_throw_guard_errors(monkeypatch):
    import pokemon_red_completion.surge as surge
    w, live, target = ordinary_fixture(monkeypatch)

    def bad_proof(*_args, **_kwargs):
        raise surge.SurgeChapterError("invalid ordinary-ball accounting")

    monkeypatch.setattr(surge, "_try_catch_wild", bad_proof)
    with pytest.raises(surge.SurgeChapterError, match="ordinary-ball accounting"):
        live.capture_encounter(target)
    assert w.helpers == 0 and live.capture_escape_bypasses == 1
