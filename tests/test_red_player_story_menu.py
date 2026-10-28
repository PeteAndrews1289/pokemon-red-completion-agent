from dataclasses import replace

import pytest
from test_red_live_option_menu import _binding, _ordinary_bindings, _situation

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_resource_quote import GoalResourceQuote, GoalResourceReserve
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.red_live_option_menu import build_red_live_option_set
from pokemon_red_completion.red_player_story_menu import (
    NativeStoryBranchInventory,
    _resource_peers_without_base_duplicates,
    merge_resource_observer_bindings,
    plural_resource_bindings,
    plural_story_bindings,
)
from pokemon_red_completion.resource_economy_observation import EconomySnapshot
from pokemon_red_completion.route_plan import _FROZEN_LOCAL_ROUTE_CACHE


@pytest.mark.parametrize("enabled", [False, True])
def test_route_reuse_is_explicit_and_only_active_inside_enumeration(monkeypatch, enabled):
    inventory = NativeStoryBranchInventory(lambda *args: None, lambda *args: (),
                                          reuse_local_route_queries=enabled)
    observed = []

    def inspect(*args):
        observed.append(_FROZEN_LOCAL_ROUTE_CACHE.get())
        return "same menu"

    monkeypatch.setattr(inventory, "_enumerate", inspect)
    assert inventory.enumerate(None, None, None) == "same menu"
    assert (observed[0] is not None) is enabled
    assert _FROZEN_LOCAL_ROUTE_CACHE.get() is None


def test_failed_inventory_clears_observed_binding_and_route_scope(monkeypatch):
    inventory = NativeStoryBranchInventory(lambda *args: None, lambda *args: (),
                                          reuse_local_route_queries=True)

    def fail(*args):
        inventory._observed = "must not survive"
        raise RuntimeError("observer failed")

    monkeypatch.setattr(inventory, "_enumerate", fail)
    with pytest.raises(RuntimeError, match="observer failed"):
        inventory.enumerate(None, None, None)
    assert inventory._observed is None and _FROZEN_LOCAL_ROUTE_CACHE.get() is None


def test_route_reuse_rejects_implicit_or_truthy_permission():
    with pytest.raises(TypeError, match="explicit boolean"):
        NativeStoryBranchInventory(lambda *args: None, lambda *args: (),
                                   reuse_local_route_queries=1)


def menu(branches):
    ordinary, extra = plural_story_bindings(_ordinary_bindings([]), branches, _situation())
    return ordinary, build_red_live_option_set(
        situation=_situation(),
        binding_set=ordinary,
        supplements=extra,
        model_feature_version=5,
        ordering_seed_sha256="a" * 64,
        economy_snapshot=EconomySnapshot(427, ()),
        target_cash=0,
    )


def branches():
    return tuple(
        _binding(GoalKind.ADVANCE_STORY, binding_ref=name, calls=[])
        for name in ("private:gym", "private:northern-route")
    )


def test_plural_story_keeps_resources_and_maps_both_executors():
    story = branches()
    ordinary, mixed = menu(story)
    assert len([b for b in ordinary.bindings if b.kind is GoalKind.ADVANCE_STORY]) == 1
    assert {b.kind for b in ordinary.bindings} >= {GoalKind.RESTORE_TEAM, GoalKind.RESUPPLY}
    assert all(any(b is s for b in mixed.bindings) for s in story)
    assert "private:" not in str(mixed.menu.policy_dict())


def test_equal_generic_story_costs_expose_v5_semantic_aliasing():
    story = branches()
    _, mixed = menu(story)
    vectors = [
        mixed.menu.candidates[i].vector(mixed.menu.context, feature_version=5)
        for i, b in enumerate(mixed.bindings)
        if b.kind is GoalKind.ADVANCE_STORY
    ]
    assert len(vectors) == 2 and vectors[0] == vectors[1]
    # Reversing bookkeeping roles cannot introduce objective identity features.
    _, reversed_menu = menu(tuple(reversed(story)))
    assert sorted(
        mixed.menu.candidate_vector(i, feature_version=5) for i in mixed.menu.available_indices
    ) == sorted(
        reversed_menu.menu.candidate_vector(i, feature_version=5)
        for i in reversed_menu.menu.available_indices
    )


def test_duplicate_or_nonstory_binding_rejected():
    a, b = branches()
    with pytest.raises(ValueError, match="duplicate"):
        menu((a, a))
    with pytest.raises(ValueError, match="nonstory"):
        menu((a, replace(b, kind=GoalKind.DEVELOP_TEAM)))


def test_no_story_branch_is_not_manufactured():
    ordinary, extra = plural_story_bindings(_ordinary_bindings([]), (), _situation())
    assert not extra
    assert all(b.kind is not GoalKind.ADVANCE_STORY for b in ordinary.bindings)


def test_resource_orders_use_existing_mixed_seam_without_dropping_original_choices():
    calls = []
    base = _ordinary_bindings(calls)
    orders = tuple(_binding(GoalKind.RESUPPLY, binding_ref=f"private:medicine-{i}",
                            calls=calls) for i in range(4))
    ordinary, extra = plural_resource_bindings(base, orders, _situation())
    assert len([b for b in ordinary.bindings if b.kind is GoalKind.RESUPPLY]) == 1
    mixed = build_red_live_option_set(
        situation=_situation(), binding_set=ordinary, supplements=extra,
        model_feature_version=5, ordering_seed_sha256="a" * 64,
        economy_snapshot=EconomySnapshot(427, ()), target_cash=0,
        force_resource_safety=False,
    )
    assert {b.binding_ref for b in mixed.bindings} == {
        b.binding_ref for b in (*base.bindings, *orders)
    }
    assert len(extra) == 4 and calls == []
    assert "private:" not in str(mixed.menu.policy_dict())
    assert mixed.force_resource_safety is False


@pytest.mark.parametrize("invalid", [None, [], ("not a binding",)])
def test_resource_additions_require_immutable_typed_inventory(invalid):
    with pytest.raises((TypeError, ValueError)):
        plural_resource_bindings(_ordinary_bindings([]), invalid, _situation())


def test_resource_additions_reject_nonresource_and_duplicate_executors():
    base = _ordinary_bindings([])
    with pytest.raises(ValueError, match="nonresource"):
        plural_resource_bindings(base, branches(), _situation())
    supply = next(b for b in base.bindings if b.kind is GoalKind.RESUPPLY)
    with pytest.raises(ValueError, match="duplicate"):
        plural_resource_bindings(base, (supply,), _situation())
    with pytest.raises(TypeError, match="resource inventory"):
        NativeStoryBranchInventory(lambda *_: base, lambda *_: (), enumerate_resources=True)


def test_identical_resource_peer_keeps_base_executor_and_distinct_orders():
    calls = []
    base = _ordinary_bindings(calls)
    supply = next(b for b in base.bindings if b.kind is GoalKind.RESUPPLY)
    shadow = replace(supply, execute=lambda: calls.append("must not replace base"))
    other = replace(supply, binding_ref="private:other-shop")
    peers = _resource_peers_without_base_duplicates(base, (shadow, other))
    assert peers == (other,)
    ordinary, extra = plural_resource_bindings(base, peers, _situation())
    assert next(b for b in ordinary.bindings if b.kind is GoalKind.RESUPPLY) is supply
    assert len(extra) == 1 and calls == []


def test_independent_observers_share_one_income_executor_and_keep_shop_alternatives():
    calls = []
    income = _binding(GoalKind.RESUPPLY, binding_ref="private:earned-income", calls=calls)
    shop = replace(income, binding_ref="private:shop")
    duplicate = replace(income, execute=lambda: calls.append("duplicate"))
    merged = merge_resource_observer_bindings((income, shop, duplicate))
    assert merged == (income, shop)
    assert merged[0] is income and calls == []


@pytest.mark.parametrize("changed", [
    {"estimated_risk": 0.95},
    {"maximum_cash_debit": 200},
    {"resource_quote": GoalResourceQuote(275, 0, (), expected_income=1800)},
])
def test_resource_observer_collision_with_different_contract_still_fails(changed):
    income = _binding(GoalKind.RESUPPLY, binding_ref="private:earned-income", calls=[])
    with pytest.raises(ValueError, match="conflict"):
        merge_resource_observer_bindings((income, replace(income, **changed)))


@pytest.mark.parametrize("rows", [[], (object(),)])
def test_resource_observer_merge_rejects_untyped_or_mutable_rows(rows):
    with pytest.raises((TypeError, ValueError)):
        merge_resource_observer_bindings(rows)


@pytest.mark.parametrize("field,value", [("estimated_effort", 0.95),
                                         ("estimated_risk", 0.95)])
def test_conflicting_resource_peer_still_fails_before_input(field, value):
    calls = []
    base = _ordinary_bindings(calls)
    supply = next(b for b in base.bindings if b.kind is GoalKind.RESUPPLY)
    with pytest.raises(ValueError, match="conflicts"):
        _resource_peers_without_base_duplicates(base, (replace(supply, **{field: value}),))
    assert calls == []


def test_duplicate_peers_without_base_identity_are_not_silently_removed():
    base = _ordinary_bindings([])
    other = _binding(GoalKind.RESUPPLY, binding_ref="private:new-order", calls=[])
    peers = _resource_peers_without_base_duplicates(base, (other, other))
    with pytest.raises(ValueError, match="duplicate resource"):
        plural_resource_bindings(base, peers, _situation())


def test_same_resource_identity_with_different_cash_quote_still_fails():
    base = _ordinary_bindings([])
    supply = next(b for b in base.bindings if b.kind is GoalKind.RESUPPLY)
    conflicting = replace(supply, resource_quote=GoalResourceQuote(
        1000, 200, (GoalResourceReserve("capture", 2, 3, 1),)
    ))
    with pytest.raises(ValueError, match="conflicts"):
        _resource_peers_without_base_duplicates(base, (conflicting,))


@pytest.mark.parametrize("invalid", [None, [], ("not a binding",)])
def test_resource_peer_normalization_rejects_invalid_observer_output(invalid):
    with pytest.raises(ValueError, match="immutable typed"):
        _resource_peers_without_base_duplicates(_ordinary_bindings([]), invalid)


@pytest.mark.parametrize('have_base_resource',[False,True])
def test_described_resource_preserves_real_spend_in_actual_mixed_inventory(have_base_resource):
    from types import SimpleNamespace as N
    from pokemon_red_completion.resource_economy_observation import EconomyMode,EconomyOffer
    from pokemon_red_completion.goal_manager import GoalAvailability,GoalOpportunity,GoalUnavailableReason
    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
    from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate
    from pokemon_red_completion.red_live_option_menu import supplemental_live_option
    base=_ordinary_bindings([])
    if not have_base_resource:
        base=replace(base,bindings=tuple(b for b in base.bindings if b.kind is not GoalKind.RESUPPLY),
            opportunities=tuple(replace(o,availability=GoalAvailability.UNAVAILABLE,
                unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
                estimated_effort=None,estimated_risk=None,resource_quote=None)
                if o.kind is GoalKind.RESUPPLY else o for o in base.opportunities))
    binding=_binding(GoalKind.RESUPPLY,binding_ref='private:coins',calls=[])
    masked=GoalOpportunity('mask',GoalKind.EXPLORE,GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET)
    q=GoalBindingSet((binding.opportunity,masked),(binding,)).question(_situation())
    candidate=project_living_dex_goal_candidate(q,0,feature_version=5,binding_ref=binding.binding_ref)
    candidate=replace(candidate,economy_offer=EconomyOffer(
        mode=EconomyMode.PURCHASE,planned_spend=5000,conditional_income=0))
    described=supplemental_live_option(binding,candidate)
    runtime=N(emulator=N(save_state_bytes=lambda:b'unchanged'))
    observed=N(situation=_situation())
    inventory=NativeStoryBranchInventory(lambda *_:base,lambda *_:(),
        enumerate_resources=lambda *_:(described,))
    ordinary=inventory.enumerate(runtime,N(),observed)
    extra=inventory.supplements(runtime,N(),observed,ordinary)
    assert described in extra and not any(b is binding for b in ordinary.bindings)
    mixed=build_red_live_option_set(situation=_situation(),binding_set=ordinary,
        supplements=extra,model_feature_version=5,ordering_seed_sha256='a'*64,
        economy_snapshot=EconomySnapshot(6000,()),target_cash=0,force_resource_safety=False)
    i=next(i for i,b in enumerate(mixed.bindings) if b is binding)
    assert mixed.menu.candidates[i].economy_offer is candidate.economy_offer
    assert mixed.menu.candidates[i].economy_offer.planned_spend==5000
    assert 'private:coins' not in str(mixed.menu.policy_dict())


@pytest.mark.parametrize('fault',['duplicate','nonresource','list','control'])
def test_described_resources_keep_duplicate_and_control_guards(fault):
    from types import SimpleNamespace as N
    from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate
    from pokemon_red_completion.red_live_option_menu import supplemental_live_option
    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
    base=_ordinary_bindings([])
    binding=_binding(GoalKind.ACQUIRE_SPECIES if fault=='nonresource' else GoalKind.RESUPPLY,
        binding_ref='private:described',calls=[])
    question=GoalBindingSet((binding.opportunity,base.bindings[0].opportunity),
        (binding,base.bindings[0])).question(_situation())
    candidate=project_living_dex_goal_candidate(question,0,feature_version=5,
        binding_ref=binding.binding_ref)
    row=supplemental_live_option(binding,candidate)
    resources=[row] if fault=='list' else ((row,row) if fault=='duplicate' else (row,))
    calls=[]
    if fault=='control':
        control=_binding(GoalKind.RECOVER_CONTROL,binding_ref='control',calls=[])
        base=GoalBindingSet((control.opportunity,base.bindings[0].opportunity),(control,base.bindings[0]))
    def provider(*a):
        calls.append(True)
        return resources
    runtime=N(emulator=N(save_state_bytes=lambda:b'unchanged'))
    inventory=NativeStoryBranchInventory(lambda *_:base,lambda *_:(),enumerate_resources=provider)
    if fault=='control':
        inventory.enumerate(runtime,N(),N(situation=_situation()))
        assert calls==[]
    else:
        with pytest.raises(ValueError,match='resource'):
            inventory.enumerate(runtime,N(),N(situation=_situation()))
        assert inventory._observed is None


def test_collection_stays_a_peer_of_story_not_a_phase_switch():
    from types import SimpleNamespace as N

    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
    from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate
    from pokemon_red_completion.red_live_option_menu import supplemental_live_option
    base = _ordinary_bindings([])
    story = branches()
    acquisition = _binding(GoalKind.ACQUIRE_SPECIES,binding_ref='collection:grass',calls=[])
    question = GoalBindingSet((acquisition.opportunity,base.bindings[0].opportunity),
        (acquisition,base.bindings[0])).question(_situation())
    candidate = project_living_dex_goal_candidate(question,0,feature_version=5,
        binding_ref=acquisition.binding_ref)
    supplement = supplemental_live_option(acquisition,candidate)
    runtime = N(emulator=N(save_state_bytes=lambda:b'unchanged'))
    inventory = NativeStoryBranchInventory(lambda *_:base,
        lambda *_:tuple((b,OptionChallenge(False,False,0.,0.,0.)) for b in story),
        enumerate_collection=lambda *_:(supplement,))
    observed = N(situation=_situation())
    ordinary = inventory.enumerate(runtime,N(),observed)
    extra = inventory.supplements(runtime,N(),observed,ordinary)
    assert {s.binding.binding_ref for s in extra} >= {'collection:grass',story[1].binding_ref}
    assert any(b is story[0] for b in ordinary.bindings)
    assert supplement is extra[-1]
    with pytest.raises(TypeError,match='collection inventory'):
        NativeStoryBranchInventory(lambda *_:base,lambda *_:(),enumerate_collection=True)
