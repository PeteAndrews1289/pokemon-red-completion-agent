"""Prospective resource reserve, without rewriting old healing behavior."""
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_goal_context_profile import _supply_transition_profile
from test_red_native_choice_integration import _single_provider

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import ItemId
from pokemon_red_completion.red_goal_context import _build_provider
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    bind_affordable_field_restore_profile,
)
from pokemon_red_completion.red_goal_skills import RedGoalSkillError


@pytest.mark.parametrize("hp,status,stock,expected", [
    (99, 0, 1, True), (100, 0, 1, False), (101, 0, 1, False),
    (190, 0, 1, False), (190, 8, 1, True), (190, 0, 2, True),
    (99, 0, 0, False), (0, 0, 1, False),
])
def test_reserve_readiness_boundary_and_status_exception(hp, status, stock, expected):
    provider, _ = _single_provider(hp=hp, maximum=200, status=status, inventory=((16, stock),))
    reserved = replace(provider, reserve_last_full_restore=True)
    assert (reserved.offer(reserved.adapter.observe()).binding is not None) is expected
    if hp > 0 and stock:
        assert provider.offer(provider.adapter.observe()).binding is not None


def test_reserve_does_not_block_a_narrower_owned_item():
    provider, _ = _single_provider(hp=190, maximum=200, inventory=((16, 1), (18, 1)))
    plan, unavailable = provider._plan(provider.adapter.observe(),
        affordable_single_item=True, reserve_last_full_restore=True)
    assert plan == ((0, ItemId.HYPER_POTION),) and unavailable is None


def test_reserve_does_not_hide_another_members_urgent_recovery():
    provider, reader = _single_provider(hp=190, maximum=200, inventory=((16, 1),))
    reader.raw = replace(reader.raw, party_count=2, party_species_ids=(28, 104),
        party_levels=(55, 55), party_hp=(190, 40), party_max_hp=(200, 100),
        party_status=(0, 0), party_moves=((57, 0, 0, 0),) * 2,
        party_pp=((10, 0, 0, 0),) * 2)
    plan, unavailable = provider._plan(provider.adapter.observe(),
        affordable_single_item=True, reserve_last_full_restore=True)
    assert plan == ((1, ItemId.FULL_RESTORE),) and unavailable is None


def test_reserve_binding_rechecks_inventory_before_input():
    provider, reader = _single_provider(hp=190, maximum=200, inventory=((16, 2),))
    reserved = replace(provider, reserve_last_full_restore=True)
    binding = reserved.offer(reserved.adapter.observe()).binding
    reader.raw = replace(reader.raw, bag_items=((16, 1),))
    with pytest.raises(RedGoalSkillError, match="origin changed"):
        binding.execute()
    assert reserved.actions.actions_executed == 0


def test_reserve_profile_is_explicit_preserves_other_goals_and_reaches_runtime():
    original = _supply_transition_profile()
    legacy = bind_affordable_field_restore_profile(original)
    reserved = bind_affordable_field_restore_profile(original, reserve_last_full_restore=True)
    assert legacy.profile_sha256 != reserved.profile_sha256
    assert reserved.providers[0] == legacy.providers[0]
    assert reserved.providers[2:] == legacy.providers[2:]
    spec = next(s for s in reserved.providers if s.kind is GoalKind.RESTORE_TEAM)
    runtime = SimpleNamespace(reader=object(), emulator=object(), adapter=object())
    provider = _build_provider(runtime, spec, CountingExecutor(object()))
    assert provider.affordable_single_item and provider.reserve_last_full_restore
    with pytest.raises(RedGoalContextProfileError, match="explicit boolean"):
        bind_affordable_field_restore_profile(original, reserve_last_full_restore=1)
    with pytest.raises(RedGoalSkillError, match="single-item"):
        replace(provider, affordable_single_item=False)
