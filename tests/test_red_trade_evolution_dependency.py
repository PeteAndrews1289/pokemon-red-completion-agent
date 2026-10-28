from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_registered_runtime_binding import bound_fixture

from pokemon_red_completion.gen1_cartridge import EvolutionMethod
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_trade_evolution_dependency import bind_trade_evolution_dependency


@pytest.fixture
def dependency(tmp_path, monkeypatch):
    import pokemon_red_completion.red_trade_evolution_dependency as module

    runtime, reader, owned = bound_fixture(tmp_path, inherited=(78,))
    trade = SimpleNamespace(index=1, give=78, receive=124)
    edge = SimpleNamespace(method=EvolutionMethod.LEVEL, to_species=78, requirement=40)
    monkeypatch.setattr(module, "stationary_npc_trades", lambda _: (trade,))
    monkeypatch.setattr(module, "evolution_graph", lambda _: {77: (edge,)})
    monkeypatch.setattr(
        "pokemon_red_completion.red_native_boxed_evolution.wild_tables",
        lambda _: {22: [(10, 0x21), (15, 0x6C)]},
    )
    # This fixture's cartridge is deliberately a token. Supply its declared
    # evolution edge to the shared-XP helper exclusion reader as well.
    monkeypatch.setattr(
        "pokemon_red_completion.red_native_boxed_evolution.level_evolution_edges",
        lambda _: ((77, 78, 40),),
    )
    return runtime, reader, owned


def bind(runtime, current=None, **kw):
    return bind_trade_evolution_dependency(
        runtime.registration_policy,
        current or runtime.adapter.observe().collection_observation,
        b"fixture",
        trade_index=1,
        source_species=77,
        completed_trades=frozenset(),
        **kw,
    )


def test_registered_credit_unchanged_and_only_declared_edge_admitted(dependency):
    runtime, _, _ = dependency
    current = runtime.adapter.observe().collection_observation
    base = runtime.registration_policy
    scoped = bind(runtime)
    source, target = red_species_ref(77), red_species_ref(78)
    assert target in base.goal_registered(current)
    assert not base.evolution_allowed(current, source, target)
    assert scoped.evolution_allowed(current, source, target)
    assert scoped.goal_registered(current) == base.goal_registered(current)
    assert scoped.protected_counts == base.protected_counts
    assert scoped.sha256 != base.sha256
    assert not scoped.evolution_allowed(current, source, red_species_ref(79))
    assert scoped.document()["intermediate_is_acquisition_success"] is False


@pytest.mark.parametrize(
    "blocker",
    ["source_reserved", "physical_intermediate", "final_owned", "completed_trade", "wrong_edge"],
)
def test_dependency_fails_closed(dependency, monkeypatch, blocker):
    runtime, _, _ = dependency
    current = runtime.adapter.observe().collection_observation
    if blocker == "source_reserved":
        runtime = replace(
            runtime,
            registration_policy=replace(
                runtime.registration_policy, protected_counts={red_species_ref(77): 1}
            ),
        )
    if blocker == "physical_intermediate":
        source = next(s for s in current.specimens if s.species_ref == red_species_ref(77))
        current = replace(
            current,
            specimens=(*current.specimens, replace(source, species_ref=red_species_ref(78))),
            owned_species=current.owned_species | {red_species_ref(78)},
        )
    if blocker == "final_owned":
        current = replace(current, owned_species=current.owned_species | {red_species_ref(124)})
    if blocker == "wrong_edge":
        monkeypatch.setattr(
            "pokemon_red_completion.red_trade_evolution_dependency.evolution_graph", lambda _: {}
        )
    with pytest.raises(ValueError):
        bind_trade_evolution_dependency(
            runtime.registration_policy,
            current,
            b"fixture",
            trade_index=1,
            source_species=77,
            completed_trades=frozenset({1}) if blocker == "completed_trade" else frozenset(),
        )


def test_exact_intermediate_verifier_preserves_credit_and_stock(dependency):
    runtime, _, _ = dependency
    before = runtime.adapter.observe().collection_observation
    scoped = bind(runtime)
    source, target = red_species_ref(77), red_species_ref(78)
    after = replace(
        before,
        specimens=tuple(
            replace(s, species_ref=target, level=40) if s.species_ref == source else s
            for s in before.specimens
        ),
        owned_species=before.owned_species | {target},
    )
    assert scoped.verify_evolution(before, after, source, target)
    assert not scoped.evolution_allowed(after, source, target)
    assert not scoped.verify_evolution(
        before, replace(after, specimens=after.specimens[:-1]), source, target
    )


def test_scoped_native_readiness_can_offer_registered_intermediate(dependency):
    from pokemon_red_completion.executor import CountingExecutor
    from pokemon_red_completion.goal_manager import GoalKind
    from pokemon_red_completion.red_native_boxed_evolution import bind_native_boxed_evolution

    runtime, _, _ = dependency
    runtime = replace(runtime, registration_policy=bind(runtime))
    native = bind_native_boxed_evolution(runtime, SimpleNamespace(rom=b"fixture"))
    actions = CountingExecutor(SimpleNamespace(execute=lambda _: pytest.fail("unexpected input")))
    assert (
        native.provider_for(GoalKind.EVOLVE_SPECIES, actions)
        .offer(native.adapter.observe())
        .binding
        is not None
    )
    assert actions.actions_executed == 0
