from types import SimpleNamespace

from test_red_goal_context import _ActionDelegate
from test_red_live_option_menu import _binding, _ordinary_bindings, _situation
from test_red_native_boxed_item_evolution import _runtime

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import ItemId
from pokemon_red_completion.red_autonomous_collection import autonomous_collection_options
from pokemon_red_completion.resource_economy_observation import EconomySnapshot


def test_every_regional_route_keeps_its_own_executor_without_teacher_route_choice(
    tmp_path, monkeypatch
):
    import pokemon_red_completion.red_autonomous_collection as module

    runtime, _ = _runtime(tmp_path, monkeypatch, source=58, target=59, item=ItemId.FIRE_STONE)
    calls = []
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
    monkeypatch.setattr(module, "derive_direct_full_pokedex_profile", lambda *args: runtime.profile)
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
                binding_set=_ordinary_bindings(calls),
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
    assert len(options.bindings) == 5
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
