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
from pokemon_red_completion.red_goal_skills import RedMartPurchase, RedMartResupplyGoalProvider
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
def test_every_regional_route_keeps_its_own_executor_without_teacher_route_choice(
    tmp_path, monkeypatch, held_stone
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
        )
        for i in range(2)
    )
    monkeypatch.setattr(
        module,
        "enumerate_red_item_evolutions",
        lambda *args, **kwargs: evolution_targets,
    )
    monkeypatch.setattr(module, "derive_direct_full_pokedex_profile", lambda *args: runtime.profile)
    monkeypatch.setattr(module, "bind_autonomous_league_funding", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "bind_composable_trainer_funding_profile", lambda profile: profile)
    monkeypatch.setattr(module, "bind_mart_funding_departure_profile", lambda profile: profile)
    monkeypatch.setattr(module, "bind_funding_fly_profile", lambda profile: profile)
    monkeypatch.setattr(module, "bind_native_boxed_item_evolution", lambda *args, **kwargs: runtime)
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
    )
    assert len(options.bindings) == 7
    assert evolution.binding_ref not in {b.binding_ref for b in options.bindings}
    for target in evolution_targets:
        i = next(
            i for i, b in enumerate(options.bindings) if b.binding_ref == target.binding.binding_ref
        )
        assert options.menu.candidates[i].features.kind is LivingDexOptionKind.EVOLVE
        assert options.menu.candidates[i].economy_offer == target.economy_offer
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

    monkeypatch.setattr(module, "derive_direct_full_pokedex_profile", lambda *args: runtime.profile)
    monkeypatch.setattr(module, "bind_autonomous_league_funding", lambda *args, **kwargs: None)
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
