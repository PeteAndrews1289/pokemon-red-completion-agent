"""The already active rival may precede the full Fuji quest prerequisite."""

from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_engaged_story as story
from pokemon_red_completion.red_story_battle import StoryTrainerContract
from pokemon_red_completion.goal_manager import GoalKind


def fixture(monkeypatch, *, available=False, map_id=143, battle_state=2):
    contract = StoryTrainerContract('rescue_fuji', 'tower-rival', 143, (242, 42, 5), 239, 1000)
    raw = N(map_id=map_id, battle_state=battle_state)
    runtime = N(
        adapter=N(observe=lambda: N(game_state=object()), graph=N(
            available_objectives=lambda _: (N(id='rescue_fuji'),) if available else ())),
        reader=N(read=lambda: raw, read_active_trainer_identity=lambda: (242, 42, 5)),
        emulator=N(save_state_bytes=lambda: b'earned-failed-tail'))
    calls = []
    monkeypatch.setattr(story, 'engaged_story_contract', lambda *a, **k: contract)
    actor = object()
    monkeypatch.setattr(story, 'FrozenStoryBattleController',
                        lambda actual, contracts, **k: calls.append((actual, contracts)) or object())
    return runtime, actor, contract, calls


@pytest.mark.parametrize('available', [False, True])
def test_compulsory_tower_admission_reuses_same_actor_without_quest_credit(monkeypatch, available):
    runtime, actor, contract, calls = fixture(monkeypatch, available=available)
    binding = story.engaged_story_binding(runtime, object(), rom=b'rom', battler=actor,
                                         objective_id='rescue_fuji', allow_retained_tower=True)
    assert binding.kind is GoalKind.RECOVER_CONTROL
    assert calls == [(actor, (contract,))]


def test_default_still_requires_available_story_context(monkeypatch):
    runtime, actor, _, calls = fixture(monkeypatch)
    assert story.engaged_story_binding(runtime, object(), rom=b'rom', battler=actor,
                                      objective_id='rescue_fuji') is None
    assert not calls


@pytest.mark.parametrize('map_id,battle_state', [(142, 2), (144, 2), (143, 0), (143, 1)])
def test_opt_in_never_starts_or_approaches_a_battle(monkeypatch, map_id, battle_state):
    runtime, actor, _, calls = fixture(monkeypatch, map_id=map_id, battle_state=battle_state)
    assert story.engaged_story_binding(runtime, object(), rom=b'rom', battler=actor,
                                      objective_id='rescue_fuji', allow_retained_tower=True) is None
    assert not calls


@pytest.mark.parametrize('fault', ['trainer', 'event', 'plan', 'context', 'not_bool'])
def test_opt_in_rejects_other_contracts_and_ambiguous_contexts(monkeypatch, fault):
    runtime, actor, contract, calls = fixture(monkeypatch)
    if fault == 'trainer':
        runtime.reader.read_active_trainer_identity = lambda: (242, 42, 4)
    elif fault == 'event':
        monkeypatch.setattr(story, 'engaged_story_contract',
                            lambda *a, **k: replace(contract, defeated_event=238))
    elif fault == 'plan':
        monkeypatch.setattr(story, 'engaged_story_contract',
                            lambda *a, **k: replace(contract, battle_plan_id='other'))
    with pytest.raises(ValueError, match='Tower'):
        story.engaged_story_binding(runtime, object(), rom=b'rom', battler=actor,
                                   objective_id='help_bill' if fault == 'context' else 'rescue_fuji',
                                   allow_retained_tower=1 if fault == 'not_bool' else True)
    assert not calls
