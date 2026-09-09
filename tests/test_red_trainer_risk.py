"""Explicit critical exposure is bounded support, not guaranteed survival."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_trainer_survival as survival
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleRuntimeError,
    BattleRuntimeTiming,
)
from pokemon_red_completion.observation import RawGameState, TrainerDamageObservation
from pokemon_red_completion.red_trainer_risk import RedTrainerRiskController, _StopOnFaintExecutor
from pokemon_red_completion.red_trainer_survival import NoTrainerSurvivalAction


def fixture(hp=100, budget=1, prior=0):
    raw = RawGameState(
        game_started=True, map_id=113, player_y=2, player_x=6, battle_state=2,
        party_count=2, party_species_ids=(28, 118), party_levels=(60, 55),
        party_hp=(hp, 1), party_max_hp=(200, 100), party_status=(0, 0),
        party_moves=((57, 58, 0, 0), (89, 0, 0, 0)),
        party_pp=((10, 10, 0, 0), (10, 0, 0, 0)),
        active_party_index=0, active_party_hp=hp, active_party_max_hp=200,
        active_party_species_id=28, active_party_moves=(57, 58, 0, 0),
        active_party_pp=(10, 10, 0, 0), enemy_species_id=66, enemy_level=50,
        enemy_hp=194, bag_items=((53, 3),),
    )
    reader = SimpleNamespace(raw=raw)
    reader.read = lambda: reader.raw
    reader.read_trainer_damage_observation = lambda observed: TrainerDamageObservation(
        observed, (63, 97, 112, 0), ('dragon', 'flying'), 100, 100, 100, 100,
        ((100, 100, 100, 100), (100, 100, 100, 100)), (('water',), ('ground',)),
    )
    return RedTrainerRiskController(
        reader, object(), (), 0, maximum_critical_exposures=budget,
        previous_critical_exposures=prior,
    )


def run(subject, executor):
    return subject.run(
        subject.reader, executor, lambda _: 2, expected_map=113,
        intent=BattleIntent('trainer_recovery', 'critical-exposure'),
        timing=BattleRuntimeTiming(), label='risk test',
        consume_battle_start_schedule=False, move_decision_guard=lambda _: None,
    )


def test_explicit_risk_is_distinct_from_default_full_bound():
    subject = fixture()
    strict = survival.RedTrainerSurvivalController(subject.reader, object(), (), 0)
    with pytest.raises(NoTrainerSurvivalAction):
        strict.decide(subject.reader.raw)
    decision = subject.decide(subject.reader.raw)
    assert (decision.kind, decision.party_index, decision.incoming_bound) == ('risk_attack', 0, 128)
    assert subject._ordinary_bound == 68 and subject.critical_exposures_claimed == 0
    assert fixture(hp=129).decide(fixture(hp=129).reader.raw).kind == 'attack'


@pytest.mark.parametrize('hp', [1, 68])
def test_ordinary_lethal_boundary_never_becomes_a_risk_permission(hp):
    subject = fixture(hp=hp)
    with pytest.raises(NoTrainerSurvivalAction):
        subject.decide(subject.reader.raw)
    assert not subject.reports and subject.critical_exposures_claimed == 0


@pytest.mark.parametrize('budget,prior', [(0, 0), (3, 0), (True, 0), (2, 1), (1, True)])
def test_budget_is_exact_and_prior_claims_cannot_be_refreshed(budget, prior):
    with pytest.raises(ValueError, match='nonrefreshed'):
        fixture(budget=budget, prior=prior)


def test_suppressed_no_pp_turn_consumes_intent_before_input_and_cannot_repeat(monkeypatch):
    subject = fixture(prior=1)
    inputs, receipts = [], []

    def sink(report):
        assert not inputs
        receipts.append(report)

    subject.decision_sink = sink
    executor = SimpleNamespace(execute=lambda action: inputs.append(action))

    def battle(reader, actions, policy, **_):
        assert policy(reader.read()) == 2
        assert subject.critical_exposures_claimed == 1  # before controls
        actions.execute(MacroAction(MacroActionKind.CONFIRM))
        # A no-PP turn still spends the intent. Repeated MAIN observation does
        # not authorize another attack or refund the first risk.
        assert reader.read().battler_pp == (10, 10, 0, 0)
        policy(reader.read())
        pytest.fail('a second risky intent was authorized')

    monkeypatch.setattr(survival, 'run_adaptive_trainer_battle', battle)
    with pytest.raises(NoTrainerSurvivalAction):
        run(subject, executor)
    assert len(inputs) == len(receipts) == 1
    assert receipts[0]['ordinary_incoming_bound'] == 68
    assert receipts[0]['incoming_bound'] == 128
    assert receipts[0]['critical_exposure_claim'] == 2
    assert receipts[0]['critical_faint_possible'] is True
    assert receipts[0]['risk_probability_estimated'] is False


def test_missing_durable_receipt_blocks_every_input(monkeypatch):
    subject = fixture()
    inputs = []

    def failed(_):
        raise OSError('durable record unavailable')

    subject.decision_sink = failed
    monkeypatch.setattr(survival, 'run_adaptive_trainer_battle',
                        lambda reader, actions, policy, **_: policy(reader.read()))
    with pytest.raises(OSError):
        run(subject, SimpleNamespace(execute=lambda a: inputs.append(a)))
    assert not inputs


@pytest.mark.parametrize('active_only', [False, True])
def test_faint_blocks_even_dialogue_before_the_next_main_policy(active_only):
    subject = fixture()
    inputs = []
    wrapped = _StopOnFaintExecutor(subject.reader, SimpleNamespace(execute=inputs.append))
    raw = subject.reader.raw
    subject.reader.raw = replace(
        raw, active_party_hp=0, **({} if active_only else {'party_hp': (0, 1)}),
    )
    with pytest.raises(BattleRuntimeError, match='faint boundary'):
        wrapped.execute(MacroAction(MacroActionKind.CONFIRM))
    assert not inputs


def test_controller_failure_retains_claim_and_forbids_reuse(monkeypatch):
    subject = fixture()

    def failed(_):
        raise RuntimeError('input uncertain')

    def battle(reader, actions, policy, **_):
        policy(reader.read())
        actions.execute(MacroAction(MacroActionKind.CONFIRM))

    monkeypatch.setattr(survival, 'run_adaptive_trainer_battle', battle)
    with pytest.raises(RuntimeError, match='input uncertain'):
        run(subject, SimpleNamespace(execute=failed))
    assert subject.critical_exposures_claimed == 1 and len(subject.reports) == 1
    with pytest.raises(BattleRuntimeError, match='consumed'):
        run(subject, SimpleNamespace(execute=failed))
