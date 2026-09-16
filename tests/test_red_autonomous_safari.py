"""Autonomous Safari exposure remains paid, action-free, and identity-free."""

from types import SimpleNamespace

import pytest

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalSituation
from pokemon_red_completion.red_autonomous_safari import autonomous_safari_options
from pokemon_red_completion.red_collection import red_species_ref


def _inputs():
    raw = object()
    reader = SimpleNamespace(read=lambda: raw)
    runtime = SimpleNamespace(
        registration_policy=object(),
        emulator=SimpleNamespace(frame_count=0),
        reader=reader,
    )
    observation = SimpleNamespace(
        collection_observation=SimpleNamespace(
            owned_species=frozenset({red_species_ref(25)})
        ),
        situation=GoalSituation(0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        free_storage_slots=2,
    )
    actions = CountingExecutor(
        SimpleNamespace(execute=lambda _action: pytest.fail("inventory sent input"))
    )
    return runtime, observation, actions, SimpleNamespace(rom=b"rom")


def test_autonomous_safari_passes_real_cash_qualified_inventory(monkeypatch):
    import pokemon_red_completion.red_autonomous_safari as module

    runtime, observation, actions, world = _inputs()
    supplement = object()
    seen = {}

    def inventory(rom, registered, context, **kwargs):
        seen.update(rom=rom, registered=registered, context=context, kwargs=kwargs)
        return SimpleNamespace(supplements=(supplement,))

    monkeypatch.setattr(module, "build_red_live_safari_inventory", inventory)
    assert autonomous_safari_options(runtime, observation, actions, world) == (supplement,)
    assert seen["rom"] == b"rom"
    assert seen["registered"] == frozenset({25})
    assert seen["kwargs"]["free_storage_slots"] == 2
    assert actions.actions_executed == 0


def test_autonomous_safari_rejects_mutating_inventory(monkeypatch):
    import pokemon_red_completion.red_autonomous_safari as module

    runtime, observation, actions, world = _inputs()

    def inventory(*_args, **_kwargs):
        runtime.emulator.frame_count += 1
        return SimpleNamespace(supplements=())

    monkeypatch.setattr(module, "build_red_live_safari_inventory", inventory)
    with pytest.raises(ValueError, match="changed the game"):
        autonomous_safari_options(runtime, observation, actions, world)
