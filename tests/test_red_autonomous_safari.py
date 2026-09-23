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
        collection_observation=SimpleNamespace(owned_species=frozenset({red_species_ref(25)})),
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


def test_autonomous_safari_indoor_fallback_requires_explicit_runtime_opt_in(monkeypatch):
    import pokemon_red_completion.red_autonomous_safari as module
    import pokemon_red_completion.red_indoor_safari as indoor

    runtime, observation, actions, world = _inputs()
    monkeypatch.setattr(
        module, "build_red_live_safari_inventory", lambda *_a, **_k: SimpleNamespace(supplements=())
    )
    calls = []

    def fallback(*_a, **_k):
        calls.append(True)
        return SimpleNamespace(supplements=("paid",))

    monkeypatch.setattr(indoor, "indoor_safari_inventory", fallback)
    assert autonomous_safari_options(runtime, observation, actions, world) == ()
    assert not calls
    runtime.safari_indoor_departure = True
    assert autonomous_safari_options(runtime, observation, actions, world) == ("paid",)
    assert calls == [True] and actions.actions_executed == 0


def test_autonomous_safari_funding_quote_success(monkeypatch):
    import pokemon_red_completion.red_autonomous_safari as module
    from pokemon_red_completion.red_safari_funding_budget import RedSafariFundingBudget

    runtime, observation, actions, world = _inputs()
    seen = {}

    start_frames = runtime.emulator.frame_count
    start_obs = runtime.reader.read()

    def fake_budget(rom, registered, *, free_storage_slots, world, reader):
        seen.update(
            rom=rom,
            registered=registered,
            free_storage_slots=free_storage_slots,
            world=world,
            reader=reader,
        )
        return RedSafariFundingBudget(available_funds=198)

    monkeypatch.setattr(module, "red_safari_funding_budget", fake_budget)
    quote = module.autonomous_safari_funding_quote(runtime, observation, world)
    assert quote is not None
    assert quote.available_funds == 198
    assert quote.admission_cost == 500
    assert quote.shortfall == 302
    assert seen["rom"] == b"rom"
    assert seen["registered"] == frozenset({25})
    assert seen["free_storage_slots"] == 2
    # Frame count, reader observation, and actions executed are strictly preserved
    assert runtime.emulator.frame_count == start_frames
    assert runtime.reader.read() is start_obs
    assert actions.actions_executed == 0


@pytest.mark.parametrize("mutation_type", ["frame", "reader_state"])
def test_autonomous_safari_funding_quote_rejects_mutating_read(monkeypatch, mutation_type):
    import pokemon_red_completion.red_autonomous_safari as module
    from pokemon_red_completion.red_safari_funding_budget import RedSafariFundingBudget

    runtime, observation, _actions, world = _inputs()

    def mutating_budget(*_args, **_kwargs):
        if mutation_type == "frame":
            runtime.emulator.frame_count += 1
        else:
            runtime.reader.read = lambda: object()
        return RedSafariFundingBudget(available_funds=198)

    monkeypatch.setattr(module, "red_safari_funding_budget", mutating_budget)
    with pytest.raises(ValueError, match="Safari funding quote changed the game"):
        module.autonomous_safari_funding_quote(runtime, observation, world)


def test_autonomous_safari_funding_quote_requires_registration_policy():
    import pokemon_red_completion.red_autonomous_safari as module

    runtime, observation, _actions, world = _inputs()
    runtime.registration_policy = None
    assert module.autonomous_safari_funding_quote(runtime, observation, world) is None
