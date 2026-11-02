"""Viridian is a parcel handoff, not an executable shop, before delivery."""
from dataclasses import replace

import pytest
from test_red_resource_goal_router import fixture as resource_fixture

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import EventFlag, MapId
from pokemon_red_completion.red_goal_skills import RedGoalSkillError
from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRoutingError

fixture = resource_fixture


@pytest.mark.parametrize("flags", [None, b"", bytes(320)])
@pytest.mark.parametrize("at_clerk", [False, True])
def test_missing_delivery_blocks_local_and_routed_shopping(fixture, flags, at_clerk):
    f = fixture
    f.reader.raw = replace(f.reader.raw, event_flags=flags, player_x=4 if at_clerk else 3)
    menu = f.router.enumerate(f.adapter.observe())
    assert not any(b.kind is GoalKind.RESUPPLY for b in menu.bindings)
    assert f.world.plans == [] and f.actions.actions_executed == 0


def test_pokedex_or_parcel_possession_is_not_delivery(fixture):
    f = fixture
    flags = bytearray(320)
    for flag in (EventFlag.GOT_POKEDEX, EventFlag.GOT_OAKS_PARCEL):
        flags[flag // 8] |= 1 << (flag % 8)
    f.reader.raw = replace(f.reader.raw, event_flags=bytes(flags))
    assert not f.provider.resource_availability(f.adapter.observe()).executable


def test_delivery_flag_is_checked_again_before_local_input(fixture):
    f = fixture
    f.reader.raw = replace(f.reader.raw, player_x=4)
    binding = f.provider.offer(f.adapter.observe()).binding
    assert binding is not None
    f.reader.raw = replace(f.reader.raw, event_flags=bytes(320))
    with pytest.raises(RedGoalSkillError, match="story prerequisite"):
        binding.execute()
    assert f.actions.actions_executed == 0


def test_other_mart_does_not_depend_on_viridian_parcel(fixture):
    f = fixture
    f.reader.raw = replace(f.reader.raw, event_flags=None)
    provider = replace(f.provider, map_id=MapId.PEWTER_MART)
    assert provider.resource_availability(f.adapter.observe()).executable


def test_revoked_delivery_invalidates_routed_quote_before_departure(fixture):
    f = fixture
    f.router.quote_resource_costs = True
    binding = next(b for b in f.router.enumerate(f.adapter.observe()).bindings
                   if b.kind is GoalKind.RESUPPLY)
    f.reader.raw = replace(f.reader.raw, event_flags=bytes(320))
    with pytest.raises((RedGoalSkillError, RedResourceGoalRoutingError)):
        binding.execute()
    assert f.actions.actions_executed == 0
