"""A resumed capture is the same allocation, not a new bag of attempts."""
from dataclasses import replace

import pytest
from test_red_one_off_capture import Sim

import pokemon_red_completion.battle_recovery as recovery
from pokemon_red_completion.observation import BattleMenuPhase, ItemId
from pokemon_red_completion.red_one_off_capture import (
    OneOffCaptureBudget,
    OneOffCapturePaused,
    OneOffCaptureRequest,
)

REQUEST = OneOffCaptureRequest(75, 50, ItemId.GREAT_BALL)


def two_members(s):
    s.raw = replace(s.raw, party_count=2, party_species_ids=(28, 101),
                    party_pp=((15, 10, 15, 25), (10, 10, 10, 10)),
                    party_hp=(206, 100), active_party_index=0)


def fake_switch(monkeypatch, s, mutate=lambda: None):
    def switch(_ex, _reader, _em, slot, **kwargs):
        assert kwargs['expected_battle_state'] == 1
        assert slot == 1
        s.raw = replace(s.raw, active_party_index=slot, active_party_hp=s.raw.party_hp[slot])
        s.phase = BattleMenuPhase.MAIN
        mutate()
    monkeypatch.setattr(recovery, 'switch_active_battler', switch)


def test_faint_then_resume_keeps_exact_budget_and_logs_total_ordinal(monkeypatch):
    s = Sim(monkeypatch, capture=False)
    two_members(s)
    budget = OneOffCaptureBudget(REQUEST, 3, 3)
    def faint():
        s.raw = replace(s.raw, active_party_hp=0, party_hp=(0, 100))
        s.phase = BattleMenuPhase.UNKNOWN
    s.after_throw = faint
    with pytest.raises(OneOffCapturePaused, match='fainted'):
        s.run(budget=budget)
    assert budget.throws_committed == 1 and s.bag[ItemId.GREAT_BALL] == 2
    s.after_throw = lambda: None
    fake_switch(monkeypatch, s)
    rows = []
    with pytest.raises(OneOffCapturePaused, match='budget exhausted'):
        s.run(budget=budget, replacement=lambda raw: 1, log=rows.append)
    assert budget.throws_committed == s.spends == 3
    assert [row['throw'] for row in rows if row['directive'] == 'throw_ball'] == [2, 3]
    assert rows[0]['directive'] == 'replace_fainted_catcher'
    count = s.executor.actions_executed
    with pytest.raises(OneOffCapturePaused, match='budget exhausted'):
        s.run(budget=budget, replacement=lambda _: pytest.fail('exhausted'))
    assert s.executor.actions_executed == count


def test_mid_call_faint_recovers_and_captures_without_attack(monkeypatch):
    s = Sim(monkeypatch, capture=False)
    two_members(s)
    budget = OneOffCaptureBudget(REQUEST, 3, 3)
    def faint_once():
        if s.spends == 1:
            s.raw = replace(s.raw, active_party_hp=0, party_hp=(0, 100))
            s.capture = True
    s.after_throw = faint_once
    fake_switch(monkeypatch, s)
    assert s.run(budget=budget, replacement=lambda raw: 1)
    assert s.spends == budget.throws_committed == 2
    assert s.bag[ItemId.MASTER_BALL] == 1 and s.commands == [1, 1]


@pytest.mark.parametrize('slot', [True, -1, 2, 0, None])
def test_invalid_replacement_issues_no_input(monkeypatch, slot):
    s = Sim(monkeypatch)
    two_members(s)
    s.raw = replace(s.raw, active_party_hp=0, party_hp=(0, 100))
    with pytest.raises(OneOffCapturePaused, match='living reserve'):
        s.run(replacement=lambda _: slot)
    assert s.executor.actions_executed == 0


@pytest.mark.parametrize('fault', ['hp', 'pp', 'money', 'bag', 'identity', 'collection'])
def test_replacement_drift_stops_before_next_ball(monkeypatch, fault):
    s = Sim(monkeypatch)
    two_members(s)
    s.raw = replace(s.raw, active_party_hp=0, party_hp=(0, 100))
    def corrupt():
        if fault == 'hp':
            s.raw = replace(s.raw, enemy_hp=149)
        elif fault == 'pp':
            s.raw = replace(s.raw, party_pp=((1, 1, 1, 1), (10, 10, 10, 10)))
        elif fault == 'money':
            s.raw = replace(s.raw, player_money=0)
        elif fault == 'bag':
            s.bag[ItemId.MASTER_BALL] = 0
        elif fault == 'identity':
            s.raw = replace(s.raw, enemy_species_id=74)
        else:
            s.owned |= {145}
    fake_switch(monkeypatch, s, corrupt)
    with pytest.raises(OneOffCapturePaused):
        s.run(replacement=lambda _: 1)
    assert s.spends == 0


@pytest.mark.parametrize('fault', ['count', 'max', 'ball', 'level', 'species'])
def test_resume_mismatch_zero_input(monkeypatch, fault):
    s = Sim(monkeypatch, balls=2)
    request = REQUEST
    if fault == 'ball':
        request = replace(request, ball=ItemId.MASTER_BALL)
    elif fault == 'level':
        request = replace(request, level=49)
    elif fault == 'species':
        request = replace(request, internal_species=74)
    budget = OneOffCaptureBudget(request, 4 if fault == 'max' else 3, 3,
                                 0 if fault == 'count' else 1)
    with pytest.raises(OneOffCapturePaused):
        s.run(budget=budget)
    assert s.executor.actions_executed == 0


def test_last_allowed_throw_does_not_start_recovery(monkeypatch):
    s = Sim(monkeypatch, capture=False)
    s.after_throw = lambda: setattr(s, 'raw', replace(s.raw, active_party_hp=0))
    with pytest.raises(OneOffCapturePaused, match='budget exhausted'):
        s.run(throws=1, replacement=lambda _: pytest.fail('no more balls authorized'))
    assert s.spends == 1


def test_interrupted_selection_does_not_grant_free_retry(monkeypatch):
    s = Sim(monkeypatch)
    budget = OneOffCaptureBudget(REQUEST, 3, 3)
    def interrupt(*_args):
        raise RuntimeError('selection interrupted')
    import pokemon_red_completion.surge as surge
    monkeypatch.setattr(surge, '_navigate_main', interrupt)
    with pytest.raises(RuntimeError, match='interrupted'):
        s.run(budget=budget)
    assert budget.throws_committed == 1 and s.spends == 0
    with pytest.raises(OneOffCapturePaused, match='retained allocation'):
        s.run(budget=budget)


@pytest.mark.parametrize('changes', [{'max_throws': True}, {'initial_ball_count': -1},
                                    {'throws_committed': True}, {'throws_committed': 4}])
def test_invalid_budget(changes):
    with pytest.raises(ValueError):
        OneOffCaptureBudget(**{'request': REQUEST, 'max_throws': 3,
                               'initial_ball_count': 3, **changes})
