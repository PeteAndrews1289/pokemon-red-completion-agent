import pytest
from test_red_live_option_menu import _binding, _ordinary_bindings, _situation

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from pokemon_red_completion.red_player_story_menu import (
    NativeStoryBranchInventory,
    SafeStopSuppression,
    plural_story_bindings,
)


def _menu():
    story = tuple(
        _binding(GoalKind.ADVANCE_STORY, binding_ref=name, calls=[])
        for name in ("private:gym", "private:northern-route")
    )
    return plural_story_bindings(_ordinary_bindings([]), story, _situation())


def _kinds(ordinary, extra):
    return {b.kind for b in ordinary.bindings} | {s.binding.kind for s in extra}


def test_hold_withholds_one_kind_for_a_finite_number_of_menus():
    ordinary, extra = _menu()
    assert GoalKind.ADVANCE_STORY in _kinds(ordinary, extra)
    hold = SafeStopSuppression()
    hold.hold(GoalKind.ADVANCE_STORY, 2)
    for _ in range(2):
        kept, kept_extra = hold.apply(ordinary, extra)
        assert GoalKind.ADVANCE_STORY not in _kinds(kept, kept_extra)
        assert _kinds(kept, kept_extra) == _kinds(ordinary, extra) - {GoalKind.ADVANCE_STORY}
        assert len(kept.opportunities) == len(ordinary.opportunities)
        blocked = [
            o
            for o in kept.opportunities
            if o.kind is GoalKind.ADVANCE_STORY and o.availability is GoalAvailability.UNAVAILABLE
        ]
        assert blocked
        assert all(
            o.unavailable_reason is GoalUnavailableReason.TEMPORARILY_BLOCKED
            for o in blocked
            if o.binding_ref in {b.binding_ref for b in ordinary.bindings}
        )
        # Kept executors are the identical observed objects, never rebuilt.
        assert all(any(b is o for o in ordinary.bindings) for b in kept.bindings)
    assert hold.apply(ordinary, extra) == (ordinary, extra)
    assert hold.remaining == {} and hold.withheld_menus == 2
    assert hold.public_dict()["withheld_executors"] == 2 * 2


def test_hold_never_empties_a_menu():
    ordinary, extra = _menu()
    hold = SafeStopSuppression()
    for kind in _kinds(ordinary, extra):
        hold.hold(kind, 3)
    assert hold.apply(ordinary, extra) == (ordinary, extra)
    assert hold.withheld_menus == 0


def test_hold_never_touches_control_recovery():
    recovery = _binding(GoalKind.RECOVER_CONTROL, binding_ref="pokemon.red:retained-x", calls=[])
    story = _binding(GoalKind.ADVANCE_STORY, binding_ref="private:gym", calls=[])
    opportunities = tuple(
        {GoalKind.RECOVER_CONTROL: recovery, GoalKind.ADVANCE_STORY: story}[kind].opportunity
        if kind in (GoalKind.RECOVER_CONTROL, GoalKind.ADVANCE_STORY)
        else GoalOpportunity(
            f"private:masked:{kind.value}",
            kind,
            GoalAvailability.UNAVAILABLE,
            unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
        )
        for kind in GoalKind
    )
    ordinary = GoalBindingSet(opportunities, (recovery, story))
    hold = SafeStopSuppression()
    hold.hold(GoalKind.ADVANCE_STORY, 1)
    assert hold.apply(ordinary, ()) == (ordinary, ())
    assert hold.remaining == {GoalKind.ADVANCE_STORY: 1}


@pytest.mark.parametrize(
    "kind, menus",
    [
        (GoalKind.RECOVER_CONTROL, 2),
        ("advance_story", 2),
        (GoalKind.ADVANCE_STORY, 0),
        (GoalKind.ADVANCE_STORY, 17),
        (GoalKind.ADVANCE_STORY, True),
    ],
)
def test_hold_rejects_control_untyped_or_unbounded_spans(kind, menus):
    with pytest.raises(ValueError, match="finite span"):
        SafeStopSuppression().hold(kind, menus)


def test_inventory_applies_typed_hold_only():
    ordinary, extra = _menu()
    inventory = NativeStoryBranchInventory(lambda *a: ordinary, lambda *a: ())
    assert inventory.safe_stop_suppression is None
    inventory.safe_stop_suppression = object()

    class Emulator:
        def save_state_bytes(self):
            return b"s"

    class Runtime:
        emulator = Emulator()

    class Observation:
        situation = _situation()

    with pytest.raises(TypeError, match="typed runner suppression"):
        inventory.enumerate(Runtime(), None, Observation())
    hold = SafeStopSuppression()
    hold.hold(GoalKind.RESUPPLY, 1)
    inventory.safe_stop_suppression = hold
    result = inventory.enumerate(Runtime(), None, Observation())
    assert GoalKind.RESUPPLY not in {b.kind for b in result.bindings}
    assert hold.withheld_menus == 1
    assert GoalKind.RESUPPLY in {b.kind for b in inventory.enumerate(Runtime(), None, Observation()).bindings}
