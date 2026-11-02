from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_acquisition import _observation as collection_observation
from test_red_goal_context import _ActionDelegate, _Emulator
from test_red_regional_acquisition import _candidate, _observation

import pokemon_red_completion.red_regional_acquisition as regional
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion.red_acquisition import summarize_red_area_survey
from pokemon_red_completion.red_collection import RED_SOLO_COLLECTION_CONTRACT, red_species_ref
from pokemon_red_completion.red_goal_context import (
    RedGoalContextRuntime,
    red_capture_source_catalog,
)
from pokemon_red_completion.red_goal_context_profile import (
    _thaw,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("map_id", 999),
        ("source_id", 42),
        ("player_x", "invalid"),
        ("label", 42),
        ("maximum_encounters", 0),
        ("maximum_seek_steps", 0),
    ],
)
def test_directly_constructed_malformed_profile_preserves_provider_failure(key, value):
    from pokemon_red_completion.red_goal_context_profile import _document_sha256

    runtime, observation, actions, _counts = fixture()
    specs = []
    for spec in runtime.profile.providers:
        if spec.kind is GoalKind.ACQUIRE_SPECIES:
            parameters = _thaw(spec.parameters)
            parameters[key] = value
            # Deliberately construct a digest-valid declaration without using
            # the parameter parser: this was the unsafe fast-path assumption.
            spec = replace(
                spec,
                parameters=parameters,
                configuration_sha256=_document_sha256(
                    {
                        "kind": spec.kind.value,
                        "mechanic": spec.mechanic.value,
                        "parameters": parameters,
                    }
                ),
            )
        specs.append(spec)
    runtime = replace(runtime, profile=replace(runtime.profile, providers=tuple(specs)))
    with pytest.raises(Exception) as original:
        runtime.provider_for(GoalKind.ACQUIRE_SPECIES, actions)
    with pytest.raises(type(original.value)) as proposed:
        regional._source_has_acquisition_demand(runtime, observation, actions)
    assert str(proposed.value) == str(original.value)
    assert actions.actions_executed == runtime.emulator.frame_count == 0


def test_observation_reuse_does_not_bypass_counted_action_validation():
    runtime, observation, _actions, _counts = fixture()
    with pytest.raises(TypeError, match="goal kind and counted actions"):
        regional._source_has_acquisition_demand(runtime, observation, None)


def test_new_optional_boundary_argument_requires_typed_observation():
    runtime, _observation, actions, _counts = fixture()
    with pytest.raises(TypeError, match="typed current boundary"):
        runtime.provider_for(GoalKind.ACQUIRE_SPECIES, actions, observation={})


def fixture(
    *, missing=(59,), stock=(), protected=0, offered=58, source="wild:Route7:grass", edges=()
):
    credited = frozenset(RED_SOLO_COLLECTION_CONTRACT.target_species) - {
        red_species_ref(n) for n in missing
    }
    observation = replace(
        _observation(),
        collection_observation=replace(collection_observation(*stock), owned_species=credited),
    )
    candidate = _candidate(source)
    providers = []
    for spec in candidate.profile.providers:
        params = _thaw(spec.parameters)
        if spec.kind is GoalKind.ACQUIRE_SPECIES:
            params["capture_species_numbers"] = [offered]
        providers.append((spec.kind, spec.mechanic, params))
    profile = parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id=candidate.profile.profile_id, providers=tuple(providers)
        )
    )
    counts = {"observe": 0, "policy_projection": 0}

    def observe():
        counts["observe"] += 1
        return observation

    def goal_registered(collection):
        counts["policy_projection"] += 1
        assert collection is observation.collection_observation
        return collection.owned_species

    policy = SimpleNamespace(
        goal_registered=goal_registered, protected_counts={red_species_ref(58): protected}
    )
    runtime = RedGoalContextRuntime(
        profile,
        None,
        _Emulator(),
        SimpleNamespace(),
        None,
        SimpleNamespace(observe=observe),
        remaining_acquisition_demand=True,
        registration_policy=policy,
        level_evolution_acquisition_edges=edges,
    )
    return (runtime, observation, CountingExecutor(_ActionDelegate()), counts)


@pytest.mark.parametrize(
    ("missing", "stock", "protected", "offered", "expected"),
    [
        ((), (), 0, 58, False),
        ((59,), (), 0, 58, True),
        ((59,), (58,), 0, 58, False),
        ((59,), (58,), 1, 58, True),
        ((58,), (), 0, 58, True),
        ((59,), (58,), 0, 59, True),
        ((99,), (), 0, 58, False),
    ],
)
def test_exact_provider_catalog_and_obligations_without_second_native_observation(
    missing, stock, protected, offered, expected
):
    runtime, observation, actions, counts = fixture(
        missing=missing, stock=stock, protected=protected, offered=offered
    )
    provider = runtime.provider_for(GoalKind.ACQUIRE_SPECIES, actions)
    assert counts["observe"] == 1
    expected_catalog = provider.catalog
    actual_catalog = red_capture_source_catalog(
        runtime, provider.source_id, (offered,), observation.collection_observation
    )
    assert actual_catalog == expected_catalog
    assert (
        bool(
            summarize_red_area_survey(
                provider.source_id, observation.collection_observation, expected_catalog
            ).missing_species_refs
        )
        is expected
    )
    assert regional._source_has_acquisition_demand(runtime, observation, actions) is expected
    assert counts["observe"] == 1
    assert counts["policy_projection"] == 3
    assert actions.actions_executed == runtime.emulator.frame_count == 0


def test_catalog_carries_additional_evolution_edges_and_exact_protection():
    edges = ((red_species_ref(16), red_species_ref(17)), (red_species_ref(17), red_species_ref(18)))
    runtime, obs, actions, counts = fixture(missing=(17, 18), stock=(16,), offered=16, edges=edges)
    provider = runtime.provider_for(GoalKind.ACQUIRE_SPECIES, actions)
    assert provider.catalog.level_evolution_edges == edges
    projected = red_capture_source_catalog(
        runtime, provider.source_id, (16,), obs.collection_observation
    )
    assert projected == provider.catalog
    assert projected.protected_counts == ((red_species_ref(58), 0),)
    assert regional._source_has_acquisition_demand(runtime, obs, actions) == bool(
        summarize_red_area_survey(
            provider.source_id, obs.collection_observation, provider.catalog
        ).missing_species_refs
    )
    assert counts["observe"] == 1


def test_new_boundary_is_used_no_persistent_demand_cache():
    runtime, obs, actions, counts = fixture(missing=(59,), offered=58)
    assert regional._source_has_acquisition_demand(runtime, obs, actions)
    after = replace(
        obs,
        collection_observation=replace(
            obs.collection_observation,
            owned_species=frozenset(RED_SOLO_COLLECTION_CONTRACT.target_species),
        ),
    )
    runtime = replace(
        runtime,
        registration_policy=SimpleNamespace(
            goal_registered=lambda o: o.owned_species, protected_counts={}
        ),
    )
    assert not regional._source_has_acquisition_demand(runtime, after, actions)
    assert counts["observe"] == 0


def test_unknown_provider_contract_keeps_established_fallback():
    runtime, obs, actions, counts = fixture()
    provider = runtime.provider_for(GoalKind.ACQUIRE_SPECIES, actions)
    calls = []
    unknown = SimpleNamespace(provider_for=lambda kind, actions: calls.append(kind) or provider)
    assert regional._source_has_acquisition_demand(unknown, obs, actions)
    assert calls == [GoalKind.ACQUIRE_SPECIES]
    bad = SimpleNamespace(provider_for=lambda kind, actions: object())
    with pytest.raises(ValueError, match="real area-survey provider"):
        regional._source_has_acquisition_demand(bad, obs, actions)


def test_nonregistered_catalog_does_not_require_live_collection_read():
    runtime, obs, actions, counts = fixture()
    runtime = replace(runtime, registration_policy=None)
    provider = runtime.provider_for(GoalKind.ACQUIRE_SPECIES, actions)
    actual = red_capture_source_catalog(runtime, provider.source_id, (58,), None)
    assert actual == provider.catalog
    assert counts["observe"] == 0


def test_regional_full_menu_projection_unchanged_against_provider_path(monkeypatch):
    runtime, obs, actions, counts = fixture(missing=(59,), stock=(9,), offered=58)
    first = _candidate("wild:Route7:grass", 0.2)
    second = _candidate("wild:Route11:grass", 0.7)
    profiles = {
        first.source_id: runtime.profile,
        second.source_id: fixture(source=second.source_id)[0].profile,
    }
    runtime = replace(runtime, reader=SimpleNamespace(read_retained_outside_map=lambda: None))
    monkeypatch.setattr(
        regional,
        "_rank_regional_sources",
        lambda *a, **kw: ((first.source_id, 1), (second.source_id, 2)),
    )
    monkeypatch.setattr(regional, "cartridge_grass_sources", lambda rom: ())
    monkeypatch.setattr(regional, "closed_remote_cave_entry", lambda *a, **kw: False)
    monkeypatch.setattr(
        regional, "derive_red_living_dex_wild_corridor", lambda target, *a, **kw: target
    )
    monkeypatch.setattr(
        regional, "retarget_red_wild_profile", lambda p, target, **kw: profiles[target.source_id]
    )
    monkeypatch.setattr(regional, "bind_red_local_discovery_profile", lambda p, *a: p)
    monkeypatch.setattr(regional, "bind_red_opportunistic_capture_profile", lambda p, *a: p)

    class Router:
        def __init__(self, rt, *a, **kw):
            self.binding = (
                first.binding if rt.profile == profiles[first.source_id] else second.binding
            )

        def enumerate_routed_kinds(self, *a):
            return SimpleNamespace(bindings=(self.binding,))

    monkeypatch.setattr(regional, "RedResourceGoalRouter", Router)
    world = SimpleNamespace(
        rom=b"fixture",
        terrain={1: None, 2: None},
        local_graphs={1: None, 2: None},
        object_blockers={1: frozenset(), 2: frozenset()},
        macro_graph=SimpleNamespace(warp_locations={}),
    )

    def enumerate_rows():
        return regional.enumerate_red_regional_acquisitions(
            runtime, obs, actions, world, maximum_actions=1000, maximum_frames=100000
        )

    fast = enumerate_rows()
    assert counts["observe"] == 0

    def legacy(rt, observation, executor):
        provider = rt.provider_for(GoalKind.ACQUIRE_SPECIES, executor)
        return bool(
            summarize_red_area_survey(
                provider.source_id, observation.collection_observation, provider.catalog
            ).missing_species_refs
        )

    monkeypatch.setattr(regional, "_source_has_acquisition_demand", legacy)
    old = enumerate_rows()
    assert counts["observe"] == 2
    assert fast == old
    assert (
        regional.regional_acquisition_menu(obs, fast, GoalSearchMemory()).policy_dict()
        == regional.regional_acquisition_menu(obs, old, GoalSearchMemory()).policy_dict()
    )
    assert actions.actions_executed == runtime.emulator.frame_count == 0
