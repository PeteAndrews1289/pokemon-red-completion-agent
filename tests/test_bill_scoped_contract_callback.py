"""ROM-free exact-contract dispatch for Bill; fixture contracts are not native proof."""
from dataclasses import dataclass, replace
from types import SimpleNamespace as N

import pytest
from pokemon_red_completion import red_player_cerulean_branches as bill
from pokemon_red_completion import red_player_early_story_options as early
from pokemon_red_completion.red_learned_trainer import (
    FrozenTrainerBattler, FROZEN_K_SHA256, K_QUALIFICATION_SHA256,
)
from pokemon_red_completion.red_scoped_training_battlers import (
    ScopedTrainingBattlers, resolve_story_battler,
)
from pokemon_red_completion.red_story_battle import StoryTrainerContract, FrozenStoryBattleController
from pokemon_red_completion.scenario_lab import ScenarioPartition

MISTY = StoryTrainerContract('defeat_misty', 'defeat_misty', 65, (235, 35, 1), 191, 2079, ((211, 1),), 2)
RIVAL = StoryTrainerContract('help_bill', 'cerulean-rival-gate', 3, (225, 25, 8), 152, 595)

@dataclass(frozen=True)
class Binding:
    label: str
    story_objective_ref: object = None


def prototype(tmp_path, partition=ScenarioPartition.TRAIN):
    return FrozenTrainerBattler(N(frame_count=0), None, tmp_path/'unused', 'a'*40,
        'train-root', 'b'*64, {}, model_sha256=FROZEN_K_SHA256,
        qualification_sha256=K_QUALIFICATION_SHA256, source_partition=partition)


def pool(tmp_path, contracts):
    actor = prototype(tmp_path)
    group = ScopedTrainingBattlers(actor, contracts=contracts, output=tmp_path/'pool', experiment_sha256='c'*64)
    return actor, group


def quote(monkeypatch, actor, callback=None):
    raw = N(map_id=3, event_flags=bytes(512))
    before = N(raw=raw, game_state=None)
    rt = N(reader=N(), adapter=N(observe=lambda: before, graph=N(
        available_objectives=lambda _: (N(id='help_bill'), N(id='defeat_misty')))))
    def rival(*args, **kwargs):
        exact = resolve_story_battler(kwargs['battler'], RIVAL)
        FrozenStoryBattleController(exact, (RIVAL,))
        return Binding('same-rival-public-binding')
    monkeypatch.setattr(bill, '_field_ready', lambda _: True)
    monkeypatch.setattr(bill, 'cerulean_rival_binding', rival)
    monkeypatch.setattr(bill, 'cerulean_rival_contract', lambda *args: RIVAL)
    monkeypatch.setattr(bill, 'trainer_party_quote', lambda *args: N(party=tuple(
        N(level=x) for x in (18, 15, 15, 17))))
    return bill.cerulean_bill_story_option(rt, object(), route=N(rom=b'no-ROM'),
        battler=actor, combat_levels=(21, 17, 18, 8), trainer_battler_for_contract=callback)


def test_generic_train_actor_still_requires_its_declared_contract(tmp_path, monkeypatch):
    actor = prototype(tmp_path)
    with pytest.raises(ValueError, match='TRAIN story requires a declared contract'):
        quote(monkeypatch, actor)
    assert actor.calls == actor.session.frame_count == 0


def test_existing_default_development_quote_is_unchanged(tmp_path, monkeypatch):
    actor = prototype(tmp_path, ScenarioPartition.DEVELOPMENT)
    row = quote(monkeypatch, actor)
    assert row.binding.label == 'same-rival-public-binding'
    assert row.binding.story_objective_ref == 'help_bill'
    assert row.challenge.opponent_fraction == 4/6
    assert actor.calls == actor.session.frame_count == 0


def test_exact_prospective_train_callback_quotes_without_input(tmp_path, monkeypatch):
    actor, group = pool(tmp_path, (MISTY, RIVAL))
    seen = []
    def resolve(contract):
        seen.append(contract)
        return group.story(contract)
    row = quote(monkeypatch, actor, resolve)
    assert seen == [RIVAL] and row.binding.story_objective_ref == 'help_bill'
    assert group.story(RIVAL).train_story_contract == RIVAL
    assert actor.calls == actor.session.frame_count == 0
    assert not tuple((tmp_path/'pool').glob('battle-*'))


def test_missing_or_wrong_contract_never_falls_back(tmp_path, monkeypatch):
    actor, group = pool(tmp_path, (MISTY,))
    with pytest.raises(ValueError, match='undeclared TRAIN story contract'):
        quote(monkeypatch, actor, group.story)
    with pytest.raises(ValueError):
        quote(monkeypatch, actor, lambda _: group.story(MISTY))
    assert actor.calls == actor.session.frame_count == 0


@pytest.mark.parametrize('bad', [replace(RIVAL, victory_money=1), replace(RIVAL, trainer_identity=(225,25,7))])
def test_altered_native_reward_or_identity_is_not_an_alias(tmp_path, monkeypatch, bad):
    actor, group = pool(tmp_path, (MISTY, RIVAL))
    with pytest.raises(ValueError, match='undeclared TRAIN story contract'):
        quote(monkeypatch, actor, lambda _: group.story(bad))
    assert actor.calls == actor.session.frame_count == 0


def test_invalid_callback_is_rejected_before_observation(monkeypatch):
    monkeypatch.setattr(bill, '_field_ready', lambda _: pytest.fail('unexpected observation'))
    with pytest.raises(TypeError, match='dispatch must be callable'):
        bill.cerulean_bill_story_option(N(), N(), route=N(), battler=N(),
            combat_levels=(), trainer_battler_for_contract={})


def test_early_wrapper_preserves_the_exact_callback(monkeypatch):
    callback = lambda contract: contract
    seen = []
    monkeypatch.setattr(early, '_legal', lambda *args: True)
    def capture(*args, **kwargs):
        seen.append(kwargs)
        return N(binding='same', challenge='same-challenge')
    monkeypatch.setattr(early, 'cerulean_bill_story_option', capture)
    assert early.bill_story_option(N(), N(), route='route', battler='wild', combat_levels=(17,),
        trainer_battler_for_contract=callback) == ('same', 'same-challenge')
    assert seen[0]['trainer_battler_for_contract'] is callback


def test_future_obstruction_contract_stays_strictly_undeclared(tmp_path, monkeypatch):
    actor, group = pool(tmp_path, (MISTY, RIVAL))
    raw = N(map_id=35, event_flags=bytes(512))
    before = N(raw=raw, game_state=None)
    rt = N(reader=N(), adapter=N(observe=lambda: before, graph=N(
        available_objectives=lambda _: (N(id='help_bill'),))))
    further = StoryTrainerContract('help_bill', 'observed-story-obstruction', 35, (201,1,1), 900, 140)
    monkeypatch.setattr(bill, '_field_ready', lambda _: True)
    monkeypatch.setattr(bill, 'story_travel_binding', lambda *args, **kwargs: None)
    def obstruction(*args, **kwargs):
        return kwargs['trainer_battler_for_contract'](further)
    monkeypatch.setattr(bill, 'obstructing_story_battle_binding', obstruction)
    with pytest.raises(ValueError, match='undeclared TRAIN story contract'):
        bill.cerulean_bill_story_option(rt, N(), route=N(), battler=actor,
            combat_levels=(17,), trainer_battler_for_contract=group.story)
    assert actor.calls == actor.session.frame_count == 0
