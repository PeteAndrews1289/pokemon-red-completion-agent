"""Distinguish genuinely optional recovery and explicit successor objectives."""
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_optional_recovery_option_value import _model, _recovery_question
from test_red_goal_context_profile import _supply_transition_profile
from test_red_goal_skills import _ActionPort, _adapter, _raw, _Reader

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import CompletionFirstGoalTeacher
from pokemon_red_completion.living_dex_goal_policy import LivingDexGoalDecisionMode
from pokemon_red_completion.living_dex_option_value import (
    upgrade_option_value_model_for_optional_recovery,
)
from pokemon_red_completion.living_dex_player_exploration import ExploringLivingDexGoalPolicy
from pokemon_red_completion.observation import ItemId
from pokemon_red_completion.red_goal_context import _build_provider
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    bind_affordable_field_restore_profile,
    bind_cartridge_trainer_story_profile,
)
from pokemon_red_completion.red_goal_skills import RedFieldRestoreGoalProvider, RedGoalSkillError


@pytest.mark.parametrize("pressure", [0.3, 0.549999, 0.55, 0.8])
def test_teacher_healing_preference_is_not_itself_an_emergency(pressure):
    question = _recovery_question()
    question = replace(question, situation=replace(
        question.situation, safety_pressure=pressure, collection_pressure=0.0,
        evolution_pressure=0.0, story_pressure=0.0,
    ))
    # Essential falsifier: old tests only used a teacher that preferred the other option.
    assert CompletionFirstGoalTeacher().select(question).kind is GoalKind.RESTORE_TEAM
    policy = ExploringLivingDexGoalPolicy(
        upgrade_option_value_model_for_optional_recovery(_model()), seed=41,
    )
    choices = {policy.select(question).kind for _ in range(40)}
    if pressure < 0.55:
        assert choices == {GoalKind.RESTORE_TEAM, GoalKind.EVOLVE_SPECIES}
        assert policy.training_eligible
        assert all(p > 0 for p in policy.option_probabilities)
    else:
        assert choices == {GoalKind.RESTORE_TEAM}
        assert not policy.training_eligible
        assert policy.last_decision.mode is LivingDexGoalDecisionMode.DETERMINISTIC_SAFETY


def _single_provider(*, hp=100, maximum=180, status=0, inventory=((16, 3),), enabled=True):
    reader = _Reader(raw=replace(
        _raw(hp=hp), party_max_hp=(maximum,), party_status=(status,),
        bag_items=inventory, bag_item_ids=tuple(item for item, _ in inventory),
    ), ready=True)
    port = _ActionPort(reader)
    adapter = _adapter(reader)
    provider = RedFieldRestoreGoalProvider(
        CountingExecutor(port), reader, port, adapter, affordable_single_item=enabled,
    )
    return provider, reader


@pytest.mark.parametrize("hp,maximum,status,inventory,item", [
    (100, 180, 0, ((16, 3),), ItemId.FULL_RESTORE),
    (100, 180, 0, ((16, 3), (18, 1)), ItemId.HYPER_POTION),
    (100, 180, 8, ((16, 3), (18, 1)), ItemId.FULL_RESTORE),
    (100, 180, 8, ((18, 1), (52, 1)), None),
    (180, 180, 8, ((16, 3), (52, 1)), ItemId.FULL_HEAL),
    (10, 300, 0, ((16, 3), (18, 1)), ItemId.FULL_RESTORE),
    (10, 300, 0, ((18, 1),), None),
    (180, 180, 0, ((16, 3),), None),
    (0, 180, 0, ((16, 3), (53, 1)), None),
    (100, 180, 0, (), None),
])
def test_one_owned_item_must_fully_restore_a_living_target(hp, maximum, status, inventory, item):
    provider, _ = _single_provider(hp=hp, maximum=maximum, status=status, inventory=inventory)
    plan, unavailable = provider._plan(provider.adapter.observe(), affordable_single_item=True)
    if item is None:
        assert not plan and unavailable is not None
    else:
        assert plan == ((0, item),) and unavailable is None


def test_single_item_target_uses_health_fraction_not_party_order():
    provider, reader = _single_provider()
    reader.raw = replace(reader.raw, party_count=3, party_species_ids=(28, 104, 118),
                         party_levels=(66, 56, 55), party_hp=(100, 61, 12),
                         party_max_hp=(213, 172, 118), party_status=(0, 0, 0),
                         party_moves=((57, 0, 0, 0),) * 3, party_pp=((10, 0, 0, 0),) * 3)
    assert provider._plan(provider.adapter.observe(), affordable_single_item=True)[0] == (
        (2, ItemId.FULL_RESTORE),
    )


def test_legacy_profile_still_requires_its_original_complete_plan():
    provider, _ = _single_provider(enabled=False)
    assert provider.offer(provider.adapter.observe()).binding is None


def test_stale_healing_binding_refuses_before_any_input():
    provider, reader = _single_provider()
    binding = provider.offer(provider.adapter.observe()).binding
    reader.raw = replace(reader.raw, party_hp=(101,))
    with pytest.raises(RedGoalSkillError, match="origin changed"):
        binding.execute()
    assert provider.actions.actions_executed == 0


@pytest.mark.parametrize("fault", [None, "unhealed", "no_item_spent", "double_spend"])
def test_complete_healing_outcome_requires_hp_and_exact_item_cost(monkeypatch, fault):
    provider, reader = _single_provider()
    def recover(actions, _reader, _emulator, party_index, item):
        assert party_index == 0 and item is ItemId.FULL_RESTORE
        actions.execute(MacroAction(MacroActionKind.WAIT))
        quantity = 3 if fault == "no_item_spent" else 1 if fault == "double_spend" else 2
        reader.raw = replace(reader.raw,
            party_hp=(100 if fault == "unhealed" else 180,),
            bag_items=((16, quantity),),
        )
    monkeypatch.setattr("pokemon_red_completion.red_goal_skills.use_field_recovery_item", recover)
    binding = provider.offer(provider.adapter.observe()).binding
    assert binding.binding_ref == "pokemon.red:recovery:single-field-item"
    report = binding.execute()
    assert report.evidence["planned_recoveries"] == 1
    assert (binding.verify(report).status.value == "succeeded") == (fault is None)


def test_successor_and_single_item_profiles_reach_real_factories_without_legacy_fallback():
    original = _supply_transition_profile()
    lorelei = bind_cartridge_trainer_story_profile(original)
    bruno = bind_cartridge_trainer_story_profile(lorelei, objective_id="defeat_bruno")
    restored = bind_affordable_field_restore_profile(bruno)
    assert len({p.profile_sha256 for p in (original, lorelei, bruno, restored)}) == 4
    assert bruno.providers[1:] == lorelei.providers[1:]
    runtime = SimpleNamespace(trainer_story_world=None, observer=object(),
                              reader=object(), emulator=object(), adapter=object())
    for spec in restored.providers:
        if spec.kind not in {GoalKind.ADVANCE_STORY, GoalKind.RESTORE_TEAM}:
            continue
        provider = _build_provider(runtime, spec, CountingExecutor(object()))
        if spec.kind is GoalKind.ADVANCE_STORY:
            assert provider.skills.get("defeat_lorelei") is None
            assert provider.skills.get("defeat_agatha") is None
            assert provider.skills.get("defeat_bruno").expected_facts == frozenset({
                "league:bruno_defeated",
            })
        else:
            assert provider.affordable_single_item
    with pytest.raises(RedGoalContextProfileError):
        bind_cartridge_trainer_story_profile(original, objective_id="defeat_agatha")
