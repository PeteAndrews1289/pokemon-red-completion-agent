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
@pytest.mark.parametrize("legacy_evolution", [False, True])
@pytest.mark.parametrize("gift_enabled", [False, True])
def test_every_regional_route_keeps_its_own_executor_without_teacher_route_choice(
    tmp_path, monkeypatch, held_stone, include_league, legacy_evolution, gift_enabled
):
    import pokemon_red_completion.red_autonomous_collection as module

    runtime, reader = _runtime(tmp_path, monkeypatch, source=58, target=59, item=ItemId.FIRE_STONE)
    if held_stone:
        reader.raw = replace(reader.raw, bag_items=((int(ItemId.FIRE_STONE), 1),))
    calls = []
    ordinary = _ordinary_bindings(calls)
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
        route_steps=(10, 30), maximum_route_steps=30, free_storage_slots=2,
    )
    fishing = tuple(
        supplemental_live_option(
            _binding(GoalKind.ACQUIRE_SPECIES, binding_ref=c.binding_ref, calls=calls), c,
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
    monkeypatch.setattr(module, "enumerate_red_level_evolutions",
                        lambda *a, **k: evolution_targets[1:])
    def derive_profile(profile, live, world, *, require_evolution):
        assert require_evolution is False
        providers = tuple(
            spec for spec in profile.providers
            if legacy_evolution or spec.kind is not GoalKind.EVOLVE_SPECIES
        )
        if not legacy_evolution:
            # The minimal native-evolution fixture has only three providers;
            # mixed-menu contexts retain other categories after exhaustion.
            from test_red_goal_context import _profile
            extra = next(spec for spec in _profile("mixed-test").providers
                         if spec.kind not in {p.kind for p in profile.providers})
            providers = tuple(sorted((*providers, extra),
                                     key=lambda p: tuple(GoalKind).index(p.kind)))
        return replace(profile, providers=providers)
    monkeypatch.setattr(module, "derive_direct_full_pokedex_profile", derive_profile)
    league_calls = []
    monkeypatch.setattr(module, "bind_autonomous_league_funding",
                        lambda *args, **kwargs: league_calls.append(True))
    monkeypatch.setattr(module, "bind_composable_trainer_funding_profile", lambda profile: profile)
    monkeypatch.setattr(module, "bind_mart_funding_departure_profile", lambda profile: profile)
    monkeypatch.setattr(module, "bind_funding_fly_profile", lambda profile: profile)
    native_calls = []
    def bind_native(*args, **kwargs):
        native_calls.append(True)
        return runtime
    monkeypatch.setattr(module, "bind_native_boxed_item_evolution", bind_native)
    monkeypatch.setattr(module, "bind_native_boxed_evolution",
                        lambda *a, **k: pytest.fail("unexpected level binding"))
    monkeypatch.setattr(
        module,
        "RedResourceGoalRouter",
        lambda *args, **kwargs: SimpleNamespace(
            enumerate=lambda _: None,
        ),
    )
    monkeypatch.setattr(
        module,
        "RedBoundedPlayerObserver",
        lambda *args, **kwargs: (
            lambda: SimpleNamespace(
                situation=_situation(resources=0.1),
                binding_set=ordinary,
            )
        ),
    )
    monkeypatch.setattr(
        module, "enumerate_red_regional_acquisitions", lambda *args, **kwargs: regional
    )
    monkeypatch.setattr(module, "red_economy_snapshot", lambda _: EconomySnapshot(6528, ()))
    actions = CountingExecutor(_ActionDelegate())
    options = autonomous_collection_options(
        runtime,
        actions,
        SimpleNamespace(),
        model_feature_version=4,
        ordering_seed_sha256="a" * 64,
        include_league_funding=include_league,
    )
    assert league_calls == ([True] if include_league else [])
    assert native_calls == ([True] if legacy_evolution else [])
    assert len(options.bindings) == 9 + int(gift_enabled)
    if gift_enabled:
        i = next(i for i, b in enumerate(options.bindings) if b.binding_ref == gift.binding_ref)
        assert options.menu.candidates[i].features.kind is LivingDexOptionKind.ACQUIRE
        options.binding(i).execute()
        assert calls[-1] == "private-gift"
        assert "private-gift" not in str(options.public_dict())
    assert evolution.binding_ref not in {b.binding_ref for b in options.bindings}
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
            i for i, b in enumerate(options.bindings)
            if b.binding_ref == supplement.binding.binding_ref
        )
        assert options.menu.candidates[index].features == supplement.candidate.features
        options.binding(index).execute()
        assert calls[-1] == supplement.binding.binding_ref
    assert "fishing-destination-private" not in str(options.public_dict())


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

    monkeypatch.setattr(module, "derive_direct_full_pokedex_profile",
                        lambda *args, **kwargs: runtime.profile)
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


@pytest.mark.parametrize(
    ("mart_target", "has_safari_quote", "expected_target"),
    [
        (600, True, 600),   # Mart target 600 plus Safari cost 500 produces 600, not 1100
        (0, True, 500),     # Mart target 0 plus eligible Safari cost 500 produces 500
        (0, False, 0),      # No eligible Safari demand preserves Mart target (0) exactly
        (1000, True, 1000), # Greater Mart target preserved
        (200, True, 500),   # Greater Safari admission cost used
        (6528, False, 6528),# No Safari quote preserves existing Mart target exactly
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

    monkeypatch.setattr(module, "derive_direct_full_pokedex_profile",
                        lambda *args, **kwargs: runtime.profile)
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

    monkeypatch.setattr(module, "derive_direct_full_pokedex_profile",
                        lambda *args, **kwargs: runtime.profile)
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
        lambda *args, **kwargs: (lambda: goal_obs),
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
        b for b in options.bindings
        if b.kind is GoalKind.ACQUIRE_SPECIES and "safari" in b.binding_ref
    ]
    assert safari_bindings == []
    # 3. Actions executed is zero; model selection/executor not invoked during discovery.
    assert executor.actions_executed == 0
