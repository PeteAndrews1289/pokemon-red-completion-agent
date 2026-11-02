from types import SimpleNamespace as N

import pytest
from test_red_live_option_menu import _binding

from pokemon_red_completion import red_player_field_goals as f
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from pokemon_red_completion.goal_resource_quote import GoalResourceQuote, GoalResourceReserve


@pytest.mark.parametrize("training", [False, True])
@pytest.mark.parametrize("story", [False, True])
def test_field_inventory_keeps_other_choices_and_forwards_declared_limits(
    monkeypatch, training, story
):
    kinds = (
        GoalKind.DEVELOP_TEAM,
        GoalKind.RESTORE_TEAM,
        GoalKind.ADVANCE_STORY,
        GoalKind.ACQUIRE_SPECIES,
    )
    original = tuple(_binding(k, binding_ref="original-" + k.value, calls=[]) for k in kinds)
    ordinary = GoalBindingSet(
        tuple(b.opportunity for b in original), original, allow_resource_variants=True
    )
    actions, observed, route, plan, battler = (object() for _ in range(5))
    runtime = N(enumerator=lambda a: N(enumerate=lambda o: ordinary))
    seen = []

    def offer(kind):
        def build(rt, a, **kwargs):
            assert rt is runtime and a is actions and kwargs["route"] is route
            if kind is GoalKind.DEVELOP_TEAM:
                assert kwargs["plan"] is plan and kwargs["battler"] is battler
                assert kwargs["maximum_battles"] == 7 and kwargs["maximum_recoveries"] == 2
            seen.append(kind)
            return _binding(kind, binding_ref="routed-" + kind.value, calls=[])

        return build

    monkeypatch.setattr(f, "routed_preparation_binding", offer(GoalKind.DEVELOP_TEAM))
    monkeypatch.setattr(f, "routed_restoration_binding", offer(GoalKind.RESTORE_TEAM))
    monkeypatch.setattr(f, "parcel_story_binding", offer(GoalKind.ADVANCE_STORY))
    configuration = dict(plan=plan, battler=battler, maximum_battles=7, maximum_recoveries=2)
    result = f.enumerate_routed_player_goals(
        runtime,
        actions,
        observed,
        home_map=41,
        route=route,
        preparation=configuration if training else None,
        include_parcel=story,
    )
    expected = {GoalKind.RESTORE_TEAM}
    if training:
        expected.add(GoalKind.DEVELOP_TEAM)
    if story:
        expected.add(GoalKind.ADVANCE_STORY)
    assert set(seen) == expected and len(result.bindings) == 4
    assert result.allow_resource_variants is True
    assert {b.kind for b in result.bindings} == set(kinds)
    assert all(
        b.binding_ref.startswith("routed-" if b.kind in expected else "original-")
        for b in result.bindings
    )
    assert configuration == dict(
        plan=plan, battler=battler, maximum_battles=7, maximum_recoveries=2
    )


def test_inventory_does_not_invent_undeclared_restoration_kind(monkeypatch):
    original = _binding(GoalKind.ACQUIRE_SPECIES, binding_ref="capture", calls=[])
    other = _binding(GoalKind.EXPLORE, binding_ref="explore", calls=[])
    rt = N(
        enumerator=lambda _: N(
            enumerate=lambda _: GoalBindingSet(
                (original.opportunity, other.opportunity), (original, other)
            )
        )
    )
    monkeypatch.setattr(
        f,
        "routed_restoration_binding",
        lambda *a, **k: _binding(GoalKind.RESTORE_TEAM, binding_ref="restore", calls=[]),
    )
    with pytest.raises(ValueError, match="outside the declared"):
        f.enumerate_routed_player_goals(rt, object(), object(), home_map=41, route=object())


def test_inventory_does_not_swallow_unexpected_capability_error(monkeypatch):
    originals = tuple(
        _binding(k, binding_ref=k.value, calls=[])
        for k in (GoalKind.RESTORE_TEAM, GoalKind.EXPLORE)
    )
    rt = N(
        enumerator=lambda _: N(
            enumerate=lambda _: GoalBindingSet(tuple(b.opportunity for b in originals), originals)
        )
    )

    def broken(*a, **k):
        raise RuntimeError("unreadable route")

    monkeypatch.setattr(f, "routed_restoration_binding", broken)
    with pytest.raises(RuntimeError, match="unreadable route"):
        f.enumerate_routed_player_goals(rt, object(), object(), home_map=41, route=object())


def test_inventory_refuses_to_collapse_multiple_restoration_alternatives(monkeypatch):
    originals = tuple(
        _binding(GoalKind.RESTORE_TEAM, binding_ref=name, calls=[])
        for name in ("center", "owned-item")
    )
    ordinary = GoalBindingSet(tuple(b.opportunity for b in originals), originals)
    rt = N(enumerator=lambda _: N(enumerate=lambda _: ordinary))
    monkeypatch.setattr(
        f,
        "routed_restoration_binding",
        lambda *a, **k: _binding(GoalKind.RESTORE_TEAM, binding_ref="routed", calls=[]),
    )
    with pytest.raises(ValueError, match="ambiguous existing alternatives"):
        f.enumerate_routed_player_goals(rt, object(), object(), home_map=41, route=object())


@pytest.mark.parametrize("restore_available", [False, True])
@pytest.mark.parametrize("routed_base", [False, True])
def test_routed_inventory_preserves_earning_purchase_and_capture_alternatives(
    monkeypatch, restore_available, routed_base
):
    calls = []
    earn = _binding(
        GoalKind.RESUPPLY,
        binding_ref="earned-trainer-income",
        calls=calls,
        quote=GoalResourceQuote(3000, 0, (), expected_income=200),
    )
    buy = _binding(
        GoalKind.RESUPPLY,
        binding_ref="affordable-balls",
        calls=calls,
        quote=GoalResourceQuote(3000, 1000, (GoalResourceReserve("capture", 0, 5, 5),)),
    )
    capture = _binding(GoalKind.ACQUIRE_SPECIES, binding_ref="wild-capture", calls=calls)
    heal = _binding(GoalKind.RESTORE_TEAM, binding_ref="ordinary-heal", calls=calls)
    original = (earn, buy, capture, heal)
    ordinary = GoalBindingSet(
        tuple(b.opportunity for b in original), original, allow_resource_variants=True
    )
    runtime = N(enumerator=lambda _: N(enumerate=lambda _: ordinary))
    actions, observation = object(), object()
    base_calls = []

    def base(rt, a, obs):
        assert rt is runtime and a is actions and obs is observation
        base_calls.append(True)
        return ordinary

    if routed_base:
        runtime.enumerator = lambda _: pytest.fail("must not silently revert to local inventory")
    replacement = _binding(GoalKind.RESTORE_TEAM, binding_ref="routed-heal", calls=calls)
    monkeypatch.setattr(
        f, "routed_restoration_binding", lambda *a, **k: replacement if restore_available else None
    )
    result = f.enumerate_routed_player_goals(
        runtime,
        actions,
        observation,
        home_map=41,
        route=object(),
        enumerate_base=base if routed_base else None,
    )
    assert calls == []
    assert base_calls == ([True] if routed_base else [])
    assert result.allow_resource_variants is True
    for binding in (earn, buy, capture):
        assert result.require(binding.binding_ref) is binding
        assert binding.opportunity in result.opportunities
    assert len(result.bindings) == len(result.opportunities) == 4
    expected_heal = replacement if restore_available else heal
    assert result.require(expected_heal.binding_ref) is expected_heal


def test_invalid_base_inventory_does_not_fall_back_or_execute():
    with pytest.raises(TypeError, match="base inventory"):
        f.enumerate_routed_player_goals(
            object(), object(), object(), home_map=41, route=object(), enumerate_base=True
        )
