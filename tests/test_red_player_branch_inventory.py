from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_red_live_option_menu import _binding, _ordinary_bindings, _situation

from pokemon_red_completion.goal_manager import GoalAvailability, GoalKind, GoalUnavailableReason
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory


def fixture():
    emulator = N(state=b"first")
    emulator.save_state_bytes = lambda: emulator.state
    rt = N(emulator=emulator)
    observation = N(situation=_situation())
    story = tuple(_binding(GoalKind.ADVANCE_STORY, binding_ref=x, calls=[])
                  for x in ("gym", "north"))
    pairs = tuple((b, OptionChallenge.from_levels(combat_levels=(17,), opponent_levels=(n,)))
                  for b, n in zip(story, (21, 18), strict=True))
    menu = NativeStoryBranchInventory(lambda *a: _ordinary_bindings([]), lambda *a: pairs)
    return menu, rt, observation, pairs


def test_all_callbacks_keep_exact_executors_and_semantic_challenges():
    menu, rt, observation, pairs = fixture()
    ordinary = menu.enumerate(rt, None, observation)
    extra = menu.supplements(rt, None, observation, ordinary)
    challenges = menu.challenges(rt, ordinary, extra, N(state=b"first"))
    assert challenges == {b.binding_ref: c for b, c in pairs}
    assert {b.kind for b in ordinary.bindings} >= {GoalKind.RESTORE_TEAM, GoalKind.RESUPPLY}
    assert any(b is pairs[0][0] for b in ordinary.bindings)
    assert extra[0].binding is pairs[1][0]
    # Budget filtering may remove recovery without invalidating story challenges.
    filtered = replace(ordinary,
        bindings=tuple(b for b in ordinary.bindings if b.kind is not GoalKind.RESTORE_TEAM),
        opportunities=tuple(replace(o, availability=GoalAvailability.UNAVAILABLE,
            unavailable_reason=GoalUnavailableReason.MISSING_RESOURCE,
            estimated_effort=None, estimated_risk=None, resource_quote=None)
            if o.kind is GoalKind.RESTORE_TEAM else o for o in ordinary.opportunities))
    assert menu.challenges(rt, filtered, extra, N(state=b"first")) == challenges


def test_stale_or_missing_inventory_must_reobserve():
    menu, rt, observation, _ = fixture()
    with pytest.raises(ValueError, match="absent or stale"):
        menu.supplements(rt, None, observation, None)
    ordinary = menu.enumerate(rt, None, observation)
    rt.emulator.state = b"after"
    with pytest.raises(ValueError, match="stale"):
        menu.supplements(rt, None, observation, ordinary)
    fresh = menu.enumerate(rt, None, observation)
    assert menu.supplements(rt, None, observation, fresh)


def test_rehashed_binding_reference_cannot_substitute_an_executor():
    menu, rt, observation, _ = fixture()
    ordinary = menu.enumerate(rt, None, observation)
    extra = menu.supplements(rt, None, observation, ordinary)
    changed = replace(ordinary, bindings=tuple(replace(b) for b in ordinary.bindings))
    with pytest.raises(ValueError, match="executors"):
        menu.challenges(rt, changed, extra, N(state=b"first"))
    with pytest.raises(ValueError, match="inventory"):
        menu.supplements(rt, None, observation, changed)


def test_mutating_observer_cannot_publish_cached_inventory():
    menu, rt, observation, pairs = fixture()
    def mutate(*args):
        rt.emulator.state = b"changed"
        return pairs
    menu.enumerate_branches = mutate
    with pytest.raises(ValueError, match="changed native state"):
        menu.enumerate(rt, None, observation)
    with pytest.raises(ValueError, match="absent"):
        menu.supplements(rt, None, observation, None)


def test_resource_callback_keeps_exact_story_descriptors_and_executors():
    menu, rt, observation, pairs = fixture()
    resources = tuple(_binding(GoalKind.RESUPPLY, binding_ref=f"medicine-{i}", calls=[])
                      for i in range(3))
    menu.enumerate_resources = lambda *_: resources
    ordinary = menu.enumerate(rt, None, observation)
    extra = menu.supplements(rt, None, observation, ordinary)
    assert {s.binding.binding_ref for s in extra} == {"north", "medicine-0",
                                                    "medicine-1", "medicine-2"}
    assert all(any(s.binding is b for s in extra) for b in resources)
    assert menu.challenges(rt, ordinary, extra, N(state=b"first")) == {
        b.binding_ref: c for b, c in pairs
    }
    assert rt.emulator.state == b"first"
    rt.emulator.state = b"later"
    with pytest.raises(ValueError, match="stale"):
        menu.supplements(rt, None, observation, ordinary)


def test_mutating_resource_callback_is_rejected_without_cached_menu():
    menu, rt, observation, _ = fixture()
    def mutate(*_):
        rt.emulator.state = b"changed"
        return ()
    menu.enumerate_resources = mutate
    with pytest.raises(ValueError, match="changed native state"):
        menu.enumerate(rt, None, observation)
    with pytest.raises(ValueError, match="absent"):
        menu.supplements(rt, None, observation, None)


def test_resource_callback_is_skipped_during_compulsory_control_recovery():
    menu, rt, observation, _ = fixture()
    control = _binding(GoalKind.RECOVER_CONTROL, binding_ref="control", calls=[])
    original = _ordinary_bindings([])
    base = replace(original, bindings=original.bindings+(control,),
                   opportunities=tuple(control.opportunity if o.kind is control.kind else o
                                       for o in original.opportunities))
    menu.enumerate_base = lambda *_: base
    def forbidden(*_):
        raise AssertionError("compulsory recovery queried optional resources")
    menu.enumerate_resources = forbidden
    ordinary = menu.enumerate(rt, None, observation)
    assert menu.supplements(rt, None, observation, ordinary) == ()
