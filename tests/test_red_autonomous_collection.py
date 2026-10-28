from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_goal_context import _ActionDelegate
from test_red_live_option_menu import _binding, _ordinary_bindings, _situation
from test_red_native_boxed_item_evolution import _runtime

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.observation import ItemId, MapId, RawGameState
from pokemon_red_completion.player_readiness import BUDGET_NAMES, CONTEXT_NAMES, PlayerReadiness
from pokemon_red_completion.red_autonomous_collection import (
    autonomous_capture_funding_target_cash,
    autonomous_collection_options,
)
from pokemon_red_completion.red_fishing_acquisition import red_fishing_destination_candidates
from pokemon_red_completion.red_goal_skills import RedMartPurchase, RedMartResupplyGoalProvider
from pokemon_red_completion.red_live_option_menu import supplemental_live_option
from pokemon_red_completion.resource_economy_observation import (
    EconomyMode,
    EconomyOffer,
    EconomySnapshot,
)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"include_coin_procurement": "yes"},
        {"include_coin_procurement": True, "include_game_corner": False},
        {"league_postgame_return": object()},
        {"league_postgame_return": lambda: None, "include_league_funding": False},
    ],
)
def test_resource_connection_scope_rejected_before_observation(kwargs):
    with pytest.raises(ValueError):
        autonomous_collection_options(
            None, None, None, model_feature_version=4, ordering_seed_sha256="a" * 64, **kwargs
        )


@pytest.mark.parametrize(
    ("cash", "balls", "expected_target"),
    [(1608, 9, 600), (228, 9, 600), (228, 0, 6000), (0, 10, 0)],
)
def test_autonomous_income_target_tracks_observed_capture_shortfall(cash, balls, expected_target):
    bag = ((int(ItemId.GREAT_BALL), balls),) if balls else ()
    observation = SimpleNamespace(
        raw=RawGameState(True, 154, 3, 3, 6, 0, player_money=cash, bag_items=bag),
        capture_item_count=balls,
    )
    provider = RedMartResupplyGoalProvider(
        map_id=MapId.FUCHSIA_MART,
        player_x=3,
        player_y=3,
        interaction_direction="up",
        purchases=(RedMartPurchase(0, ItemId.GREAT_BALL, 20, 600),),
        actions=None,
        reader=None,
        emulator=None,
        adapter=SimpleNamespace(config=SimpleNamespace(desired_capture_items=10)),
        affordable_ball_purchase=True,
    )
    runtime = SimpleNamespace(
        profile=SimpleNamespace(providers=(SimpleNamespace(kind=GoalKind.RESUPPLY),)),
        adapter=SimpleNamespace(observe=lambda: observation),
        provider_for=lambda _kind, _actions: provider,
    )
    economy = EconomySnapshot(
        cash,
        (("red-item-003", balls),) if balls else (),
    )
    assert (
        autonomous_capture_funding_target_cash(
            runtime, CountingExecutor(_ActionDelegate()), economy
        )
        == expected_target
    )


@pytest.mark.parametrize("held_stone", [False, True])
@pytest.mark.parametrize("include_league", [False, True])
@pytest.mark.parametrize("funding_variants", [False, True])
@pytest.mark.parametrize("legacy_evolution", [False, True])
@pytest.mark.parametrize("gift_enabled", [False, True])
@pytest.mark.parametrize("continuous", [False, True])
def test_every_regional_route_keeps_its_own_executor_without_teacher_route_choice(
    tmp_path,
    monkeypatch,
    held_stone,
    include_league,
    funding_variants,
    legacy_evolution,
    gift_enabled,
    continuous,
):
    import pokemon_red_completion.red_autonomous_collection as module

    runtime, reader = _runtime(tmp_path, monkeypatch, source=58, target=59, item=ItemId.FIRE_STONE)
    if held_stone:
        reader.raw = replace(reader.raw, bag_items=((int(ItemId.FIRE_STONE), 1),))
    calls = []
    ordinary = _ordinary_bindings(calls)
    from pokemon_red_completion.goal_resource_quote import GoalResourceQuote, GoalResourceReserve

    purchase = _binding(
        GoalKind.RESUPPLY,
        binding_ref="private-mart",
        calls=calls,
        quote=GoalResourceQuote(58, 40, (GoalResourceReserve("capture", 0, 1, 1),)),
    )
    if funding_variants:
        ordinary = replace(
            ordinary,
            opportunities=(*ordinary.opportunities, purchase.opportunity),
            bindings=(*ordinary.bindings, purchase),
            allow_resource_variants=True,
        )
    evolution = _binding(GoalKind.EVOLVE_SPECIES, binding_ref="private-evolution", calls=calls)
    ordinary = replace(
        ordinary,
        opportunities=tuple(
            evolution.opportunity if op.kind is GoalKind.EVOLVE_SPECIES else op
            for op in ordinary.opportunities
        ),
        bindings=(*ordinary.bindings, evolution),
    )
    regional = tuple(
        SimpleNamespace(
            binding=_binding(
                GoalKind.ACQUIRE_SPECIES,
                binding_ref=f"private-destination-{index}",
                calls=calls,
            )
        )
        for index in range(3)
    )
    evolution_targets = tuple(
        SimpleNamespace(
            binding=_binding(
                GoalKind.EVOLVE_SPECIES, binding_ref=f"private-target-{i}", calls=calls
            ),
            economy_offer=EconomyOffer(
                EconomyMode.OTHER,
                planned_spend=0 if held_stone and i == 0 else 2100,
            ),
            execution_effort=0.12 if i == 1 else None,
        )
        for i in range(2)
    )
    from test_red_live_fishing import _offer

    fishing_candidates = red_fishing_destination_candidates(
        (_offer(23, (99,)), _offer(7, (119,))),
        route_steps=(10, 30),
        maximum_route_steps=30,
        free_storage_slots=2,
    )
    fishing = tuple(
        supplemental_live_option(
            _binding(GoalKind.ACQUIRE_SPECIES, binding_ref=c.binding_ref, calls=calls),
            c,
        )
        for c in fishing_candidates
    )
    monkeypatch.setattr(module, "autonomous_fishing_options", lambda *a: fishing)
    monkeypatch.setattr(module, "autonomous_safari_options", lambda *a: ())
    gift = _binding(GoalKind.ACQUIRE_SPECIES, binding_ref="private-gift", calls=calls)
    monkeypatch.setattr(
        module, "scripted_gift_bindings", lambda *a: (gift,) if gift_enabled else ()
    )
    monkeypatch.setattr(
        module,
        "enumerate_red_item_evolutions",
        lambda *args, **kwargs: evolution_targets[:1],
    )
    monkeypatch.setattr(
        module, "enumerate_red_level_evolutions", lambda *a, **k: evolution_targets[1:]
    )

    def derive_profile(profile, live, world, *, require_evolution):
        assert require_evolution is False
        providers = tuple(
            spec
            for spec in profile.providers
            if legacy_evolution or spec.kind is not GoalKind.EVOLVE_SPECIES
        )
        if not legacy_evolution:
            # The minimal native-evolution fixture has only three providers;
            # mixed-menu contexts retain other categories after exhaustion.
            from test_red_goal_context import _profile

            extra = next(
                spec
                for spec in _profile("mixed-test").providers
                if spec.kind not in {p.kind for p in profile.providers}
            )
            providers = tuple(
                sorted((*providers, extra), key=lambda p: tuple(GoalKind).index(p.kind))
            )
        return replace(profile, providers=providers)

    monkeypatch.setattr(module, "derive_direct_full_pokedex_profile", derive_profile)
    league_calls = []
    league = _binding(
        GoalKind.RESUPPLY,
        binding_ref="private-league",
        calls=calls,
        quote=GoalResourceQuote(58, 0, (), expected_income=29799),
    )
    monkeypatch.setattr(
        module,
        "bind_autonomous_league_funding",
        lambda *args, **kwargs: league_calls.append(True) or league,
    )
    monkeypatch.setattr(module, "bind_composable_trainer_funding_profile", lambda profile: profile)
    monkeypatch.setattr(module, "bind_mart_funding_departure_profile", lambda profile: profile)
    monkeypatch.setattr(module, "bind_funding_fly_profile", lambda profile: profile)
    native_calls = []

    def bind_native(*args, **kwargs):
        native_calls.append(True)
        return runtime

    monkeypatch.setattr(module, "bind_native_boxed_item_evolution", bind_native)
    monkeypatch.setattr(
        module,
        "bind_native_boxed_evolution",
        lambda *a, **k: pytest.fail("unexpected level binding"),
    )
    router_calls = []
    routed_kinds = []
    monkeypatch.setattr(
        module,
        "RedResourceGoalRouter",
        lambda *args, **kwargs: (
            router_calls.append(kwargs)
            or SimpleNamespace(
                enumerate=lambda _: ordinary,
                enumerate_routed_kinds=lambda _live, kinds: routed_kinds.append(kinds) or ordinary,
            )
        ),
    )
    monkeypatch.setattr(
        module,
        "RedBoundedPlayerObserver",
        lambda *args, **kwargs: (
            lambda: SimpleNamespace(
                situation=_situation(resources=0.1),
                binding_set=kwargs["enumerate_bindings"](None),
            )
        ),
    )
    monkeypatch.setattr(
        module, "enumerate_red_regional_acquisitions", lambda *args, **kwargs: regional
    )
    monkeypatch.setattr(module, "red_economy_snapshot", lambda _: EconomySnapshot(6528, ()))
    actions = CountingExecutor(_ActionDelegate())
    from pokemon_red_completion.red_regional_trainer_funding import FundingGateTransit

    gate_transit = FundingGateTransit(frozenset({1, 50}), frozenset({50})) if continuous else None
    readiness = (
        PlayerReadiness(
            (0.0,) * len(CONTEXT_NAMES) + (1.0,) * len(BUDGET_NAMES), history_observed=False
        )
        if continuous
        else None
    )
    options = autonomous_collection_options(
        runtime,
        actions,
        SimpleNamespace(),
        model_feature_version=7 if continuous else 4,
        ordering_seed_sha256="a" * 64,
        include_league_funding=include_league,
        funding_gate_transit=gate_transit,
        readiness=readiness,
        additional_acquisitions=(
            _binding(GoalKind.ACQUIRE_SPECIES, binding_ref="private-special-a", calls=calls),
            _binding(GoalKind.ACQUIRE_SPECIES, binding_ref="private-special-b", calls=calls),
        ),
    )
    assert router_calls[0]["funding_gate_transit"] is gate_transit
    assert routed_kinds == [
        frozenset(GoalKind) - {GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES}
    ]
    assert all(candidate.readiness == readiness for candidate in options.menu.candidates)
    assert league_calls == ([True] if include_league else [])
    assert native_calls == ([True] if legacy_evolution else [])
    assert len(options.bindings) == (
        11 + int(gift_enabled) + int(funding_variants) + int(include_league)
    )
    # Supplemental League income must coexist with finite income and a Mart
    # quote without changing the ordinary question's strict variant limits.
    assert options.original_bindings == replace(
        ordinary,
        opportunities=tuple(
            replace(
                op,
                availability=module.GoalAvailability.UNAVAILABLE,
                unavailable_reason=module.GoalUnavailableReason.NO_LEGAL_TARGET,
                estimated_effort=None,
                estimated_risk=None,
                resource_quote=None,
            )
            if op.kind in {GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES}
            else op
            for op in ordinary.opportunities
        ),
        bindings=tuple(
            b
            for b in ordinary.bindings
            if b.kind not in {GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES}
        ),
    )
    if include_league:
        i = next(i for i, b in enumerate(options.bindings) if b is league)
        assert options.menu.candidates[i].economy_offer.conditional_income == 29799
        options.binding(i).execute()
        assert calls[-1] == "private-league"
        assert "private-league" not in str(options.public_dict())
    if funding_variants:
        assert any(b is purchase for b in options.bindings)
    if gift_enabled:
        i = next(i for i, b in enumerate(options.bindings) if b.binding_ref == gift.binding_ref)
        assert options.menu.candidates[i].features.kind is LivingDexOptionKind.ACQUIRE
        options.binding(i).execute()
        assert calls[-1] == "private-gift"
        assert "private-gift" not in str(options.public_dict())
    assert evolution.binding_ref not in {b.binding_ref for b in options.bindings}
    for name in ("private-special-a", "private-special-b"):
        index = next(i for i, b in enumerate(options.bindings) if b.binding_ref == name)
        assert options.menu.candidates[index].features.kind is LivingDexOptionKind.ACQUIRE
        assert name not in str(options.public_dict())
        options.binding(index).execute()
        assert calls[-1] == name
    for target in evolution_targets:
        i = next(
            i for i, b in enumerate(options.bindings) if b.binding_ref == target.binding.binding_ref
        )
        assert options.menu.candidates[i].features.kind is LivingDexOptionKind.EVOLVE
        assert options.menu.candidates[i].economy_offer == target.economy_offer
        if target.execution_effort is not None:
            assert options.menu.candidates[i].features.execution_effort == target.execution_effort
        options.binding(i).execute()
        assert calls[-1] == target.binding.binding_ref
    calls.clear()
    assert calls == []
    assert actions.actions_executed == 0
    for destination in regional:
        index = next(
            i
            for i, b in enumerate(options.bindings)
            if b.binding_ref == destination.binding.binding_ref
        )
        options.binding(index).execute()
        assert calls[-1] == destination.binding.binding_ref
    assert "private-destination" not in str(options.public_dict())
    assert "private-target" not in str(options.public_dict())
    for supplement in fishing:
        index = next(
            i
            for i, b in enumerate(options.bindings)
            if b.binding_ref == supplement.binding.binding_ref
        )
        assert options.menu.candidates[index].features == supplement.candidate.features
        options.binding(index).execute()
        assert calls[-1] == supplement.binding.binding_ref
    assert "fishing-destination-private" not in str(options.public_dict())


@pytest.mark.parametrize("transit", [True, {}, "all-routes"])
def test_collection_rejects_untyped_funding_scope_before_observing(transit):
    with pytest.raises(ValueError, match="typed bounded inventory"):
        autonomous_collection_options(
            None,
            None,
            None,
            model_feature_version=7,
            ordering_seed_sha256="a" * 64,
            funding_gate_transit=transit,
        )


@pytest.mark.parametrize("extra", [[], (None,), ("unbound",)])
def test_additional_acquisitions_reject_untyped_mutable_inventory(extra):
    with pytest.raises(ValueError, match="immutable acquisition"):
        autonomous_collection_options(
            None,
            None,
            None,
            model_feature_version=7,
            ordering_seed_sha256="a" * 64,
            additional_acquisitions=extra,
        )


def test_additional_acquisitions_reject_nonacquisition_and_duplicate_executors():
    a = _binding(GoalKind.ACQUIRE_SPECIES, binding_ref="private:one", calls=[])
    b = _binding(GoalKind.RESTORE_TEAM, binding_ref="private:heal", calls=[])
    for extra, message in (((a, a), "distinct"), ((b,), "acquisition")):
        with pytest.raises(ValueError, match=message):
            autonomous_collection_options(
                None,
                None,
                None,
                model_feature_version=7,
                ordering_seed_sha256="a" * 64,
                additional_acquisitions=extra,
            )


def test_autonomous_menu_enables_storage_and_income_prerequisites(tmp_path, monkeypatch):
    import pokemon_red_completion.red_autonomous_collection as module

    runtime, _ = _runtime(tmp_path, monkeypatch, source=58, target=59, item=ItemId.FIRE_STONE)
    captured = {}
    ordinary = _ordinary_bindings([])

    def profile_step(profile):
        captured.setdefault("profile_steps", 0)
        captured["profile_steps"] += 1
        return profile

    class Router:
        def __init__(self, *args, **kwargs):
            captured["router"] = kwargs

        def enumerate(self, _):
            return None

    monkeypatch.setattr(
        module, "derive_direct_full_pokedex_profile", lambda *args, **kwargs: runtime.profile
    )
    monkeypatch.setattr(module, "bind_autonomous_league_funding", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "autonomous_safari_options", lambda *args: ())
    monkeypatch.setattr(module, "bind_composable_trainer_funding_profile", profile_step)
    monkeypatch.setattr(module, "bind_mart_funding_departure_profile", profile_step)
    monkeypatch.setattr(module, "bind_funding_fly_profile", profile_step)
    monkeypatch.setattr(module, "bind_native_boxed_item_evolution", lambda *args, **kwargs: runtime)
    monkeypatch.setattr(module, "RedResourceGoalRouter", Router)
    monkeypatch.setattr(
        module,
        "RedBoundedPlayerObserver",
        lambda *args, **kwargs: (
            lambda: SimpleNamespace(situation=_situation(resources=0.1), binding_set=ordinary)
        ),
    )
    monkeypatch.setattr(module, "enumerate_red_regional_acquisitions", lambda *args, **kwargs: ())
    monkeypatch.setattr(module, "enumerate_red_item_evolutions", lambda *args, **kwargs: ())
    monkeypatch.setattr(module, "enumerate_red_level_evolutions", lambda *args, **kwargs: ())
    monkeypatch.setattr(module, "red_economy_snapshot", lambda _: EconomySnapshot(6528, ()))

    autonomous_collection_options(
        runtime,
        CountingExecutor(_ActionDelegate()),
        SimpleNamespace(),
        model_feature_version=4,
        ordering_seed_sha256="a" * 64,
    )
    assert captured["profile_steps"] == 3
    assert (
        captured["router"]
        | {
            "routed_storage_relief": True,
            "routed_recovery": True,
            "include_recovery_offers": True,
            "trainer_funding": True,
            "regional_trainer_funding": True,
            "observed_trainer_funding": True,
            "trainer_funding_target_cash": 6_528,
        }
        == captured["router"]
    )


@pytest.mark.parametrize("allow_support", (False, True))
def test_singleton_supply_reuses_exact_inventory_without_a_fake_model_choice(
    tmp_path,
    monkeypatch,
    allow_support,
):
    import pokemon_red_completion.red_autonomous_collection as module
    from pokemon_red_completion.goal_manager import GoalAvailability, GoalUnavailableReason
    from pokemon_red_completion.red_live_option_menu import RedLiveOptionMenuError
    from pokemon_red_completion.red_player_support import RedPlayerSupport

    runtime, _ = _runtime(tmp_path, monkeypatch, source=58, target=59, item=ItemId.FIRE_STONE)
    calls = []
    inventory = _ordinary_bindings(calls)
    binding = next(b for b in inventory.bindings if b.kind is GoalKind.RESUPPLY)
    inventory = replace(
        inventory,
        bindings=(binding,),
        opportunities=tuple(
            o
            if o.binding_ref == binding.binding_ref
            else replace(
                o,
                availability=GoalAvailability.UNAVAILABLE,
                unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
                estimated_effort=None,
                estimated_risk=None,
                resource_quote=None,
            )
            for o in inventory.opportunities
        ),
    )
    monkeypatch.setattr(
        module, "derive_direct_full_pokedex_profile", lambda *_a, **_k: runtime.profile
    )
    for name in (
        "bind_composable_trainer_funding_profile",
        "bind_mart_funding_departure_profile",
        "bind_funding_fly_profile",
    ):
        monkeypatch.setattr(module, name, lambda profile: profile)
    monkeypatch.setattr(module, "bind_native_boxed_item_evolution", lambda *_a, **_k: runtime)
    monkeypatch.setattr(
        module,
        "RedResourceGoalRouter",
        lambda *_a, **_k: SimpleNamespace(enumerate=lambda _: inventory),
    )
    monkeypatch.setattr(
        module,
        "RedBoundedPlayerObserver",
        lambda *_a, **_k: (
            lambda: SimpleNamespace(situation=_situation(resources=0.1), binding_set=inventory)
        ),
    )
    for name in (
        "enumerate_red_regional_acquisitions",
        "enumerate_red_item_evolutions",
        "enumerate_red_level_evolutions",
        "autonomous_fishing_options",
        "autonomous_safari_options",
        "scripted_gift_bindings",
        "npc_trade_dependency_bindings",
        "npc_trade_bindings",
    ):
        monkeypatch.setattr(module, name, lambda *_a, **_k: ())
    monkeypatch.setattr(module, "autonomous_safari_funding_quote", lambda *_a: None)
    monkeypatch.setattr(module, "red_economy_snapshot", lambda _: EconomySnapshot(6528, ()))
    readiness = PlayerReadiness(
        (0.0,) * len(CONTEXT_NAMES) + (1.0,) * len(BUDGET_NAMES), history_observed=False
    )
    actions = CountingExecutor(_ActionDelegate())
    arguments = dict(
        model_feature_version=7,
        ordering_seed_sha256="a" * 64,
        include_league_funding=False,
        allow_support=allow_support,
        readiness=readiness,
    )
    if not allow_support:
        with pytest.raises(RedLiveOptionMenuError, match="count=1"):
            autonomous_collection_options(runtime, actions, SimpleNamespace(), **arguments)
    else:
        support = autonomous_collection_options(runtime, actions, SimpleNamespace(), **arguments)
        assert isinstance(support, RedPlayerSupport) and support.binding is binding
        assert support.readiness is readiness
        assert support.public_dict()["model_queries"] == 0
        assert support.public_dict()["comparative_choice"] is False
        assert len(support.bindings.bindings) == 1
    assert actions.actions_executed == 0 and calls == []


@pytest.mark.parametrize(
    ("mart_target", "has_safari_quote", "expected_target"),
    [
        (600, True, 600),  # Mart target 600 plus Safari cost 500 produces 600, not 1100
        (0, True, 500),  # Mart target 0 plus eligible Safari cost 500 produces 500
        (0, False, 0),  # No eligible Safari demand preserves Mart target (0) exactly
        (1000, True, 1000),  # Greater Mart target preserved
        (200, True, 500),  # Greater Safari admission cost used
        (6528, False, 6528),  # No Safari quote preserves existing Mart target exactly
    ],
)
def test_autonomous_collection_target_cash_liquidity_alternative(
    tmp_path, monkeypatch, mart_target, has_safari_quote, expected_target
):
    import pokemon_red_completion.red_autonomous_collection as module
    from pokemon_red_completion.red_safari_funding_budget import RedSafariFundingBudget

    runtime, _ = _runtime(tmp_path, monkeypatch, source=58, target=59, item=ItemId.FIRE_STONE)
    captured = {}
    ordinary = _ordinary_bindings([])

    class Router:
        def __init__(self, *args, **kwargs):
            captured["router"] = kwargs

        def enumerate(self, _):
            return None

    monkeypatch.setattr(
        module, "derive_direct_full_pokedex_profile", lambda *args, **kwargs: runtime.profile
    )
    monkeypatch.setattr(module, "bind_autonomous_league_funding", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "bind_composable_trainer_funding_profile", lambda p: p)
    monkeypatch.setattr(module, "bind_mart_funding_departure_profile", lambda p: p)
    monkeypatch.setattr(module, "bind_funding_fly_profile", lambda p: p)
    monkeypatch.setattr(module, "bind_native_boxed_item_evolution", lambda *args, **kwargs: runtime)
    monkeypatch.setattr(module, "RedResourceGoalRouter", Router)
    monkeypatch.setattr(
        module,
        "RedBoundedPlayerObserver",
        lambda *args, **kwargs: (
            lambda: SimpleNamespace(situation=_situation(resources=0.1), binding_set=ordinary)
        ),
    )
    monkeypatch.setattr(module, "enumerate_red_regional_acquisitions", lambda *args, **kwargs: ())
    monkeypatch.setattr(module, "enumerate_red_item_evolutions", lambda *args, **kwargs: ())
    monkeypatch.setattr(module, "enumerate_red_level_evolutions", lambda *args, **kwargs: ())
    monkeypatch.setattr(module, "red_economy_snapshot", lambda _: EconomySnapshot(198, ()))
    monkeypatch.setattr(module, "autonomous_safari_options", lambda *a: ())
    monkeypatch.setattr(module, "autonomous_capture_funding_target_cash", lambda *args: mart_target)

    quote = RedSafariFundingBudget(available_funds=198) if has_safari_quote else None
    monkeypatch.setattr(module, "autonomous_safari_funding_quote", lambda *args: quote)

    options = autonomous_collection_options(
        runtime,
        CountingExecutor(_ActionDelegate()),
        SimpleNamespace(rom=b"rom"),
        model_feature_version=4,
        ordering_seed_sha256="a" * 64,
    )
    assert captured["router"]["trainer_funding_target_cash"] == expected_target
    assert options.menu.context.target_cash == expected_target


def test_autonomous_collection_funds_eligible_safari_admission_integration(tmp_path, monkeypatch):
    """Integration test: real autonomous_safari_funding_quote and autonomous_safari_options.

    Neither the quote nor its consumer is mocked away. Proves that an otherwise-valid
    state at 198 cash derives a 500 funding target (shortfall 302) for trainer funding,
    while executable Safari discovery remains blocked (< 500 cash).
    """
    import pokemon_red_completion.red_autonomous_collection as module
    import pokemon_red_completion.red_safari_acquisition as safari_acq
    from pokemon_red_completion.actions import MacroActionKind
    from pokemon_red_completion.gen1_terrain import Terrain
    from pokemon_red_completion.local_router import LocalEdge, LocalGraph
    from pokemon_red_completion.observation import Badge, OverworldMovementMode
    from pokemon_red_completion.red_collection import red_species_ref

    runtime, reader = _runtime(tmp_path, monkeypatch, source=58, target=59, item=ItemId.FIRE_STONE)
    captured = {}
    ordinary = _ordinary_bindings([])

    class Router:
        def __init__(self, *args, **kwargs):
            captured["router"] = kwargs

        def enumerate(self, _):
            return None

    monkeypatch.setattr(
        module, "derive_direct_full_pokedex_profile", lambda *args, **kwargs: runtime.profile
    )
    monkeypatch.setattr(module, "bind_autonomous_league_funding", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "bind_composable_trainer_funding_profile", lambda p: p)
    monkeypatch.setattr(module, "bind_mart_funding_departure_profile", lambda p: p)
    monkeypatch.setattr(module, "bind_funding_fly_profile", lambda p: p)
    monkeypatch.setattr(module, "bind_native_boxed_item_evolution", lambda *args, **kwargs: runtime)
    monkeypatch.setattr(module, "RedResourceGoalRouter", Router)

    situation = _situation(resources=0.1)
    collection_obs = SimpleNamespace(owned_species=frozenset({red_species_ref(30)}))
    goal_obs = SimpleNamespace(
        situation=situation,
        binding_set=ordinary,
        collection_observation=collection_obs,
        free_storage_slots=2,
    )
    monkeypatch.setattr(
        module,
        "RedBoundedPlayerObserver",
        lambda *args, **kwargs: lambda: goal_obs,
    )
    monkeypatch.setattr(module, "enumerate_red_regional_acquisitions", lambda *args, **kwargs: ())
    monkeypatch.setattr(module, "enumerate_red_item_evolutions", lambda *args, **kwargs: ())
    monkeypatch.setattr(module, "enumerate_red_level_evolutions", lambda *args, **kwargs: ())

    # Player has 198 cash. Mart needs 0 funding (e.g. bag has enough capture items).
    monkeypatch.setattr(module, "autonomous_capture_funding_target_cash", lambda *args: 0)

    # Low-level cartridge decoding stubs: Safari Zone Center offers missing species 111
    monkeypatch.setattr(safari_acq, "internal_to_dex", lambda _rom: {10: 111, 11: 30})
    monkeypatch.setattr(
        safari_acq,
        "wild_tables",
        lambda _rom, **_kwargs: {
            int(MapId.SAFARI_ZONE_CENTER): [(25, 10)] * 3 + [(25, 11)] * 7,
        },
    )

    # Real terrain and local_graph for MapId.SAFARI_ZONE_CENTER
    height, width = 30, 30
    grass = [[False] * width for _ in range(height)]
    grass[23][15] = True
    walkable = tuple(tuple(True for _ in range(width)) for _ in range(height))
    terrain = Terrain(
        map_id=int(MapId.SAFARI_ZONE_CENTER),
        tileset=0,
        walkable=walkable,
        grass=tuple(tuple(r) for r in grass),
        water=tuple(tuple(False for _ in range(width)) for _ in range(height)),
        tiles=tuple(tuple(0 for _ in range(width)) for _ in range(height)),
    )
    edges = {
        (25, 15): (
            LocalEdge((24, 15), "up", required_mode="land", action_kind=MacroActionKind.MOVE),
        ),
        (24, 15): (
            LocalEdge((23, 15), "up", required_mode="land", action_kind=MacroActionKind.MOVE),
            LocalEdge((25, 15), "down", required_mode="land", action_kind=MacroActionKind.MOVE),
        ),
        (23, 15): (
            LocalEdge((24, 15), "down", required_mode="land", action_kind=MacroActionKind.MOVE),
        ),
    }
    graph = LocalGraph(edges)

    world = SimpleNamespace(
        rom=b"rom",
        terrain={int(MapId.SAFARI_ZONE_CENTER): terrain},
        local_graphs={int(MapId.SAFARI_ZONE_CENTER): graph},
        object_blockers={int(MapId.SAFARI_ZONE_CENTER): frozenset()},
        macro_graph=SimpleNamespace(warp_locations={int(MapId.SAFARI_ZONE_CENTER): ()}),
    )

    # Reader setup: Celadon City origin, living Fly member, Thunder Badge, Fuchsia destination
    reader.raw = replace(
        reader.raw,
        map_id=int(MapId.CELADON_CITY),
        player_money=198,
        badge_bits=int(Badge.THUNDER),
        party_hp=(50,) + reader.raw.party_hp[1:],
        party_moves=((0x13, 0, 0, 0),) + reader.raw.party_moves[1:],
    )
    reader.read_fly_destinations = lambda: (int(MapId.FUCHSIA_CITY),)
    reader.read_overworld_movement_mode = lambda: OverworldMovementMode.WALKING
    reader.read_input_readiness = lambda: SimpleNamespace(ready=True)
    reader.read_bottom_dialogue_box_visible = lambda: False
    reader.read_pending_trainer_battle_identity = lambda: None

    executor = CountingExecutor(_ActionDelegate())
    # REAL autonomous_collection_options, REAL autonomous_safari_funding_quote,
    # REAL red_safari_funding_budget, REAL discover_eligible_red_safari_areas!
    options = autonomous_collection_options(
        runtime,
        executor,
        world,
        model_feature_version=4,
        ordering_seed_sha256="a" * 64,
    )

    # 1. Target cash is 500 (liquidity for the 500 admission, shortfall 302 against 198).
    assert captured["router"]["trainer_funding_target_cash"] == 500
    assert options.menu.context.target_cash == 500
    # 2. But NO executable Safari acquisition is offered in bindings because 198 < 500.
    safari_bindings = [
        b
        for b in options.bindings
        if b.kind is GoalKind.ACQUIRE_SPECIES and "safari" in b.binding_ref
    ]
    assert safari_bindings == []
    # 3. Actions executed is zero; model selection/executor not invoked during discovery.
    assert executor.actions_executed == 0
