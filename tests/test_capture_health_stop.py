"""ROM-free regressions for ordinary capture losing its usable catcher.

Retains the real status preparer, ordinary throw exit checks, area survey and
provider verifier. Hardware/escape input is replaced by explicit fixture state
transitions. No trained model, emulator load, native input, or fit is used.
"""

from dataclasses import replace

import pytest
from test_red_capture_status_runtime import setup
from test_red_goal_skills import _ActionPort, _adapter, _AreaExecutor, _raw, _Reader

import pokemon_red_completion.red_capture_status_runtime as status_runtime
import pokemon_red_completion.surge as surge
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalFailureReason
from pokemon_red_completion.party import MoveObservation
from pokemon_red_completion.red_acquisition import RedAreaExecutionPolicy
from pokemon_red_completion.red_capture_status_runtime import (
    CaptureStatusDrift,
    RedCaptureStatusError,
)
from pokemon_red_completion.red_collection import red_internal_species_number, red_species_ref
from pokemon_red_completion.red_goal_skills import RedAreaSurveyGoalProvider


def _depleted_capture_world(monkeypatch):
    world, prepare = setup(monkeypatch)
    world.party = replace(
        world.party,
        members=(
            replace(
                world.party.members[0], level=13, hp=10, max_hp=38, moves=(MoveObservation(33, 20),)
            ),
            replace(
                world.party.members[1], level=6, hp=10, max_hp=21, moves=(MoveObservation(33, 20),)
            ),
        ),
    )
    world.raw = replace(
        world.raw,
        party_hp=(10, 10),
        party_max_hp=(38, 21),
        party_status=(0, 0),
        active_party_hp=10,
        active_party_max_hp=38,
    )
    return world, prepare


def test_no_viable_catcher_has_specific_reason_without_a_damage_fallback(monkeypatch):
    world, prepare = _depleted_capture_world(monkeypatch)
    before = world.raw
    with pytest.raises(RedCaptureStatusError, match="no healthy catcher") as caught:
        prepare()
    assert caught.value.reason_code == CaptureStatusDrift.NO_HEALTHY_CATCHER.value
    assert world.turns == 0
    assert world.raw == before
    assert prepare.throw_preparations == []


def _ordinary_health_fixture(monkeypatch):
    world, _ = _depleted_capture_world(monkeypatch)
    bag = {1: 1, 4: 4}  # Master Ball plus four ordinary balls.
    retained = [2]
    calls = []
    monkeypatch.setattr(surge, "_bag", lambda _: bag)
    monkeypatch.setattr(surge, "_living_specimen_count", lambda _: retained[0])
    for name in ("_navigate_main", "_select_bag_item", "_pulse", "_weaken_wild_capture_once"):
        monkeypatch.setattr(
            surge,
            name,
            lambda *a, **k: pytest.fail(
                "depleted capture must settle instead of throwing or selecting damage"
            ),
        )
    live = surge.LiveWildEncounterExecutor(
        object(),
        object(),
        world,
        surge.DEFAULT_SURGE_TIMING,
        label="measured ordinary health stop",
        capture_status_support=True,
        settle_unavailable_catcher=True,
    )
    target = red_species_ref(red_internal_species_number(world.raw.enemy_species_id))
    return world, live, target, bag, retained, calls


def test_ordinary_capture_low_health_settles_before_false_return_without_spending_ball(monkeypatch):
    world, live, target, bag, retained, calls = _ordinary_health_fixture(monkeypatch)
    before = dict(bag)

    def escape(*_args):
        calls.append("bounded_escape")
        world.raw = replace(world.raw, battle_state=0)

    monkeypatch.setattr(surge, "_flee", escape)
    assert live.capture_encounter(target) is False
    assert calls == ["bounded_escape"]
    assert live.capture_health_stopped is True
    assert world.raw.battle_state == 0 and retained == [2]
    assert bag == before
    assert live.capture_throw_preparations == [] and live.capture_weakening_reports == []


@pytest.mark.parametrize(
    "reason",
    [
        None,
        CaptureStatusDrift.TARGET_HP,
        CaptureStatusDrift.ORIGINAL_SPECIES,
        CaptureStatusDrift.BAG_ITEMS,
    ],
)
def test_ordinary_health_stop_does_not_swallow_unknown_or_protected_state_errors(
    monkeypatch, reason
):
    world, live, target, bag, _retained, calls = _ordinary_health_fixture(monkeypatch)
    fault = RedCaptureStatusError("unrelated capture fault", reason_code=reason)

    def fail(_self):
        raise fault

    monkeypatch.setattr(status_runtime.RedCaptureStatusPreparer, "__call__", fail)
    monkeypatch.setattr(surge, "_flee", lambda *a: calls.append("must-not-escape"))
    with pytest.raises(RedCaptureStatusError) as caught:
        live.capture_encounter(target)
    assert caught.value is fault
    assert calls == [] and live.capture_health_stopped is False
    assert world.raw.battle_state == 1 and bag == {1: 1, 4: 4}


@pytest.mark.parametrize("fault", ["raises", "still_battle", "specimen", "ball"])
def test_ordinary_health_stop_requires_proven_escape_and_existing_custody_checks(
    monkeypatch, fault
):
    world, live, target, bag, retained, calls = _ordinary_health_fixture(monkeypatch)

    def escape(*_args):
        calls.append("bounded_escape")
        if fault == "raises":
            raise RuntimeError("bounded escape failed")
        if fault != "still_battle":
            world.raw = replace(world.raw, battle_state=0)
        if fault == "specimen":
            retained[0] += 1
        if fault == "ball":
            bag[4] -= 1

    monkeypatch.setattr(surge, "_flee", escape)
    with pytest.raises(RuntimeError):
        live.capture_encounter(target)
    assert calls == ["bounded_escape"]
    if fault == "raises":
        assert live.capture_health_stopped is False


def _health_stop_provider():
    reader = _Reader(raw=_raw(poke_balls=20), ready=True)
    port = _ActionPort(reader)
    actions = CountingExecutor(port)
    calls = []

    class HealthExitArea(_AreaExecutor):
        capture_health_stopped = False

        def seek_encounter(self):
            calls.append("seek")
            assert calls.count("seek") == 1, "a latched health stop cannot start another search"
            super().seek_encounter()

        def capture_encounter(self, species_ref):
            assert species_ref == self.encountered
            calls.append("capture_ended_without_retention")
            self.actions.execute(MacroAction(MacroActionKind.WAIT))
            self.reader.raw = replace(self.reader.raw, party_hp=(50,))
            self.encountered = None
            self.capture_health_stopped = True
            return False

    area = HealthExitArea(reader, actions)
    provider = RedAreaSurveyGoalProvider(
        source_id="wild:Route1:grass",
        area_executor=area,
        actions=actions,
        emulator=port,
        adapter=_adapter(reader),
        policy=RedAreaExecutionPolicy(capture_quota=1),
        normalize_after_capture=lambda: pytest.fail("a health stop must not walk to normalize"),
    )
    binding = provider.offer(provider.adapter.observe()).binding
    assert binding is not None
    return reader, area, provider, binding, calls


def test_settled_capture_health_stop_returns_measured_failure_without_another_search():
    reader, area, _provider, binding, calls = _health_stop_provider()
    before_owned = reader.pokedex.owned_species
    report = binding.execute()
    assert calls == ["seek", "capture_ended_without_retention"]
    assert report.actions_executed == 2 and report.frames_executed > 0
    assert report.evidence["safety_stopped"] is True
    assert report.evidence["capture_health_stopped"] is True
    assert report.evidence["search_exhausted"] is False
    assert report.evidence["source_normalized"] is False
    assert report.evidence["captures"] == 0 and report.evidence["flees"] == 1
    assert report.evidence["capture_diagnostics"]["capture_attempts"] == 1
    assert report.evidence["capture_diagnostics"]["failed_capture_attempts"] == 1
    assert reader.pokedex.owned_species == before_owned
    assert area.capture_health_stopped is True
    assert binding.verify(report).failure_reason is GoalFailureReason.RESOURCE_LOST


@pytest.mark.parametrize(
    "fault",
    [
        "private_latch",
        "marker",
        "healed",
        "battle",
        "unready",
        "unbounded",
        "no_actions",
        "no_frames",
        "captures",
        "boolean_capture",
        "collection_drift",
    ],
)
def test_capture_health_marker_requires_private_execution_and_fresh_low_health_field_proof(fault):
    reader, area, _provider, binding, _calls = _health_stop_provider()
    report = binding.execute()
    assert binding.verify(report).failure_reason is GoalFailureReason.RESOURCE_LOST
    if fault == "private_latch":
        area.capture_health_stopped = False
    elif fault == "marker":
        report = replace(report, evidence={**report.evidence, "capture_health_stopped": False})
    elif fault == "healed":
        reader.raw = replace(reader.raw, party_hp=(180,))
    elif fault == "battle":
        reader.raw = replace(reader.raw, battle_state=1)
    elif fault == "unready":
        reader.ready = False
    elif fault == "unbounded":
        report = replace(report, evidence={**report.evidence, "bounded": False})
    elif fault == "no_actions":
        report = replace(report, actions_executed=0)
    elif fault == "no_frames":
        report = replace(report, frames_executed=0)
    elif fault in {"captures", "boolean_capture"}:
        report = replace(
            report,
            evidence={**report.evidence, "captures": True if fault == "boolean_capture" else 1},
        )
    elif fault == "collection_drift":
        reader.pokedex = replace(
            reader.pokedex, owned_species=frozenset({9, 16}), seen_species=frozenset({9, 16})
        )
    assert binding.verify(report).failure_reason is GoalFailureReason.OUTCOME_NOT_VERIFIED


def test_base_capture_users_do_not_silently_opt_into_corridor_settlement(monkeypatch):
    world, _ = _depleted_capture_world(monkeypatch)
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
    target = red_species_ref(red_internal_species_number(world.raw.enemy_species_id))
    with pytest.raises(RedCaptureStatusError) as caught:
        live.capture_encounter(target)
    assert caught.value.reason_code == CaptureStatusDrift.NO_HEALTHY_CATCHER.value
    assert not live.capture_health_stopped


def test_corridor_composition_consumes_health_stop_and_summary_remains_compatible(monkeypatch):
    from pokemon_red_completion.capture_survey import CaptureSurveySummary

    world, _ = _depleted_capture_world(monkeypatch)
    corridor = surge.LiveWildCorridorSurveyExecutor(
        object(),
        object(),
        world,
        surge.DEFAULT_SURGE_TIMING,
        label="corridor health settlement",
        forward_directions=("up",),
        starting_endpoint="south",
        max_legs=2,
        capture_status_support=True,
    )
    assert corridor._settle_unavailable_catcher is True
    _, _, _, binding, _ = _health_stop_provider()
    report = binding.execute()
    summary = CaptureSurveySummary.from_evidence(report.evidence)
    assert summary.safety_stopped and summary.captures == 0
