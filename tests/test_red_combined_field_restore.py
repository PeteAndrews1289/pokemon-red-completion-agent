from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_field_pp_restore import fixture
from test_red_goal_context_profile import _payload, _provider, _supply_transition_profile

from pokemon_red_completion.goal_manager import GoalKind, GoalUnavailableReason
from pokemon_red_completion.red_field_pp_restore import RedCombinedFieldRestoreGoalProvider
from pokemon_red_completion.red_goal_context import _build_provider
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    RedGoalMechanic,
    bind_combined_field_restore_profile,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_goal_manager import RedGoalBindingOffer
from pokemon_red_completion.red_goal_skills import RedFieldRestoreGoalProvider


def test_literal_lance_resource_transition_exposes_hp_then_pp(monkeypatch):
    pp, reader, adapter, inputs, _ = fixture(monkeypatch)
    reader.raw = replace(
        reader.raw, party_count=6, party_species_ids=(28, 104, 141, 118, 48, 64),
        party_levels=(68, 56, 30, 55, 13, 55),
        party_hp=(162, 61, 71, 118, 34, 139),
        party_max_hp=(220, 172, 89, 118, 39, 139), party_status=(0,) * 6,
        party_moves=((66, 70, 58, 57), (87, 28, 98, 84), (33, 103, 49, 120),
                     (91, 10, 28, 89), (1, 95, 50, 0), (15, 19, 31, 14)),
        party_pp=((20, 12, 3, 0), (4, 15, 30, 30), (30, 40, 15, 5),
                  (9, 35, 10, 10), (35, 19, 20, 0), (20, 15, 20, 15)),
        first_party_level=68, first_party_hp=162, first_party_max_hp=220,
        first_party_moves=(66, 70, 58, 57), first_party_pp=(20, 12, 3, 0),
        bag_items=((16, 2), (82, 1)), bag_item_ids=(16, 82),
    )
    hp = RedFieldRestoreGoalProvider(pp.actions, reader, pp.emulator, adapter,
                                    affordable_single_item=True, reserve_last_full_restore=True)
    combined = RedCombinedFieldRestoreGoalProvider(hp, pp)
    before = adapter.observe()
    assert hp._plan(before, affordable_single_item=True, reserve_last_full_restore=True) == (
        ((1, 16),), None,
    )
    assert combined.offer(before).binding.binding_ref == 'pokemon.red:recovery:single-field-item'
    # Literal observed effect of one Full Restore, not the planner reimplemented.
    reader.raw = replace(reader.raw, party_hp=(162, 172, 71, 118, 34, 139),
                         bag_items=((16, 1), (82, 1)))
    after = adapter.observe()
    assert hp.offer(after).unavailable_reason is GoalUnavailableReason.MISSING_RESOURCE
    binding = combined.offer(after).binding
    assert binding is not None and 'elixir' in binding.binding_ref
    assert not inputs  # Offer composition never executes either skill.


@pytest.mark.parametrize('reason', list(GoalUnavailableReason))
def test_fallback_only_for_legal_target_or_resource_absence(reason):
    calls = []
    hp_offer = RedGoalBindingOffer.unavailable(GoalKind.RESTORE_TEAM, reason)
    pp_offer = RedGoalBindingOffer.unavailable(GoalKind.RESTORE_TEAM,
                                               GoalUnavailableReason.NO_LEGAL_TARGET)
    hp = SimpleNamespace(kind=GoalKind.RESTORE_TEAM, offer=lambda _: hp_offer)
    pp = SimpleNamespace(kind=GoalKind.RESTORE_TEAM,
                         offer=lambda _: (calls.append('pp'), pp_offer)[1])
    got = RedCombinedFieldRestoreGoalProvider(hp, pp).offer(object())
    allowed = reason in {
        GoalUnavailableReason.NO_LEGAL_TARGET, GoalUnavailableReason.MISSING_RESOURCE,
    }
    assert got is (pp_offer if allowed else hp_offer)
    assert calls == (['pp'] if allowed else [])


def test_available_binding_and_execution_error_never_switch_provider(monkeypatch):
    pp, _, adapter, _, _ = fixture(monkeypatch, fault='input_error')
    original = pp.offer(adapter.observe())
    calls = []
    hp = SimpleNamespace(kind=GoalKind.RESTORE_TEAM, offer=lambda _: original)
    fallback = SimpleNamespace(kind=GoalKind.RESTORE_TEAM, offer=lambda _: calls.append('pp'))
    combined = RedCombinedFieldRestoreGoalProvider(hp, fallback)
    assert combined.offer(adapter.observe()) is original
    with pytest.raises(RuntimeError, match='controller failed'):
        original.binding.execute()
    assert not calls


def test_profile_opt_in_builds_composition_and_leaves_old_profile_unchanged(monkeypatch):
    pp, reader, adapter, _, _ = fixture(monkeypatch)
    original = _supply_transition_profile()
    bound = bind_combined_field_restore_profile(original)
    assert bound.providers[0] == original.providers[0]
    assert bound.providers[2:] == original.providers[2:]
    assert original.providers[1].parameters == {}
    assert bound.providers[1].parameters == {
        'affordable_single_item': True, 'reserve_last_full_restore': True,
        'include_pp_fallback': True,
    }
    runtime = SimpleNamespace(reader=reader, emulator=pp.emulator, adapter=adapter)
    result = _build_provider(runtime, bound.providers[1], pp.actions)
    assert isinstance(result, RedCombinedFieldRestoreGoalProvider)


@pytest.mark.parametrize('changes', [
    {'include_pp_fallback': False}, {'include_pp_fallback': 1},
    {'reserve_last_full_restore': False}, {'affordable_single_item': False},
])
def test_ambiguous_combined_profile_refuses(changes):
    params = {'include_pp_fallback': True, 'reserve_last_full_restore': True,
              'affordable_single_item': True, **changes}
    with pytest.raises(RedGoalContextProfileError):
        parse_red_goal_context_profile(_payload(
            _provider(GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_RESTORE, params),
        ))
