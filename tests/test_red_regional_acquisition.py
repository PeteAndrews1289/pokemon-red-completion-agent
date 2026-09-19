from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest
from test_goal_resource_quote import _supply_model
from test_red_goal_skills import _adapter, _raw, _Reader
from test_red_living_dex_wild_corridor import _local_discovery_profile

import pokemon_red_completion.red_regional_acquisition as regional
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_composition_qualification import (
    living_completion_checkpoint,
)
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding
from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion.living_dex_option_value import (
    upgrade_option_value_model_for_search_history,
)
from pokemon_red_completion.red_acquisition import RED_ACQUISITION_CATALOG, RedAcquisitionKind
from pokemon_red_completion.red_collection import RED_SOLO_COLLECTION_CONTRACT, red_species_ref
from pokemon_red_completion.red_goal_context_profile import (
    _thaw,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_goal_skills import RedAreaSurveyGoalProvider


def _candidate(source="wild:Route2:grass", effort=0.2):
    original = _local_discovery_profile()
    providers = []
    for spec in original.providers:
        params = _thaw(spec.parameters)
        if "source_id" in params:
            params["source_id"] = source
        providers.append((spec.kind, spec.mechanic, params))
    profile = parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id=original.profile_id,
            providers=tuple(providers),
        )
    )
    binding = ExecutableGoalBinding(
        "private:" + source,
        GoalKind.ACQUIRE_SPECIES,
        effort,
        0.1,
        lambda: pytest.fail("enumeration executed capture"),
        lambda _: pytest.fail("enumeration verified an unexecuted capture"),
        search_source_ref="pokemon.red:acquisition:" + source,
    )
    return regional.RedRegionalAcquisitionCandidate(source, profile, binding)


def _observation():
    return _adapter(_Reader(raw=_raw(), ready=True)).observe()


def test_cartridge_source_inventory_includes_noncanonical_locations_and_roundtrips(monkeypatch):
    from pokemon_red_completion.observation import MapId
    from pokemon_red_completion.red_living_dex_multifamily_curriculum import map_id_for_wild_source
    monkeypatch.setattr("pokemon_red_completion.gen1_cartridge.wild_tables",
        lambda rom, *, medium: {int(MapId.ROUTE_15): [(20, 1)],
            int(MapId.ROUTE_11): [(15, 2)], int(MapId.ROUTE_12): [], 9999: [(1, 1)]})
    sources = regional.cartridge_grass_sources(b"fixture")
    assert sources == ("wild:Route11:grass", "wild:Route15:grass")
    assert {int(map_id_for_wild_source(s)) for s in sources} == {
        int(MapId.ROUTE_11), int(MapId.ROUTE_15),
    }


def test_source_projection_excludes_identity_and_preserves_observed_history():
    first, second = _candidate(), _candidate("wild:Route11:grass", 0.7)
    observation = _observation()
    memory = GoalSearchMemory()
    memory.record(
        regional.regional_source_memory_key(first.source_id),
        living_completion_checkpoint(observation).required_specimens_sha256,
        exhausted=True,
        actions=71,
        frames=280,
    )
    menu = regional.regional_acquisition_menu(observation, (first, second), memory)
    assert menu.feature_version == 2
    assert menu.candidates[0].search_history.attempts == 1
    assert menu.candidates[1].search_history.attempts == 0
    assert menu.candidate_vector(0) != menu.candidate_vector(1)
    assert "Route" not in str(menu.policy_dict()) and "private:" not in str(menu.policy_dict())
    renamed = (replace(first, binding=replace(first.binding, binding_ref="renamed")), second)
    assert regional.regional_acquisition_menu(observation, renamed, memory).policy_dict() == (
        menu.policy_dict()
    )


def test_real_choice_needs_distinct_sources_and_distinguishable_features():
    first = _candidate()
    second = _candidate("wild:Route11:grass")
    for candidates in ((first,), (first, first)):
        with pytest.raises(ValueError, match="distinct executable"):
            regional.regional_acquisition_menu(_observation(), candidates, GoalSearchMemory())
    with pytest.raises(ValueError, match="distinguishable"):
        regional.regional_acquisition_menu(_observation(), (first, second), GoalSearchMemory())
    with pytest.raises(ValueError, match="source differs"):
        replace(first, source_id="foreign")
    with pytest.raises(ValueError, match="real capture"):
        replace(
            first, binding=replace(first.binding, kind=GoalKind.EXPLORE, search_source_ref=None)
        )


def test_source_sampling_replays_full_support_without_turning_it_into_greedy_play():
    menu = regional.regional_acquisition_menu(
        _observation(),
        (_candidate(), _candidate("wild:Route11:grass", 0.7)),
        GoalSearchMemory(),
    )
    model = upgrade_option_value_model_for_search_history(_supply_model())
    choices = []
    for seed in range(30):
        first = regional.sample_regional_acquisition(model, menu, seed=seed)
        assert regional.sample_regional_acquisition(model, menu, seed=seed) == first
        assert sum(first["probabilities"]) == pytest.approx(1)
        assert min(first["probabilities"]) >= 0.125
        assert first["menu_sha256"] == menu.policy_sha256
        choices.append(first["selected_candidate_index"])
    assert set(choices) == {0, 1}
    for seed in (-1, True, 1.5):
        with pytest.raises(ValueError):
            regional.sample_regional_acquisition(model, menu, seed=seed)
    with pytest.raises(ValueError, match="feature version"):
        regional.sample_regional_acquisition(_supply_model(), menu, seed=3)


@dataclass
class _Runtime:
    profile: object
    emulator: object
    registration_policy: object = None
    reader: object = None


@pytest.mark.parametrize("registered", [False, True])
def test_enumeration_uses_only_real_wild_bindings_and_preserves_action_counters(
    monkeypatch, registered,
):
    monkeypatch.setattr(regional, "_source_has_acquisition_demand", lambda *a: True)
    items = [
        _candidate("wild:Route2:grass", 0.7),
        _candidate("wild:Route11:grass", 0.2),
        _candidate("wild:Route15:grass", 0.1),
    ]
    methods = [
        SimpleNamespace(source_id=item.source_id, kind=RedAcquisitionKind.WILD)
        for item in items[:2]
    ]
    methods.append(SimpleNamespace(source_id="safari:unsupported", kind=RedAcquisitionKind.SAFARI))
    monkeypatch.setattr(regional, "RED_ACQUISITION_CATALOG", SimpleNamespace(methods=methods))
    monkeypatch.setattr(regional, "map_id_for_wild_source", lambda source: 1)
    def derive(target, *args, **kwargs):
        assert kwargs["excluded"] == ({(4, 4), (2, 3)} if registered else {(4, 4)})
        assert ("cartridge" in kwargs) is registered
        return target
    monkeypatch.setattr(regional, "derive_red_living_dex_wild_corridor", derive)
    monkeypatch.setattr(
        regional, "cartridge_grass_sources", lambda rom: (items[2].source_id,)
    )
    def retarget(profile, target, *, rom):
        assert rom == b"fixture"
        return next(i.profile for i in items if i.source_id == target.source_id)
    monkeypatch.setattr(regional, "retarget_red_wild_profile", retarget)
    monkeypatch.setattr(regional, "bind_red_local_discovery_profile", lambda profile, *a: profile)
    opportunistic = []

    def bind_opportunistic(profile, rom):
        assert rom == b"fixture"
        opportunistic.append(profile)
        return profile

    monkeypatch.setattr(
        regional, "bind_red_opportunistic_capture_profile", bind_opportunistic
    )

    class Router:
        def __init__(self, runtime, *a, **kw):
            assert kw["include_recovery_offers"] is False
            assert kw["routed_recovery"] is True
            assert kw["prepare_capture_items"] is registered
            self.profile = runtime.profile

        def enumerate_routed_kinds(self, observation, routed_kinds):
            assert routed_kinds == frozenset({GoalKind.ACQUIRE_SPECIES})
            return SimpleNamespace(
                bindings=(next(i.binding for i in items if i.profile == self.profile),)
            )

    monkeypatch.setattr(regional, "RedResourceGoalRouter", Router)
    runtime = _Runtime(
        items[0].profile,
        SimpleNamespace(frame_count=0),
        reader=SimpleNamespace(read_retained_outside_map=lambda: None),
    )
    if registered:
        runtime.registration_policy = object()
    actions = SimpleNamespace(actions_executed=0)
    world = SimpleNamespace(
        terrain={1: object()},
        local_graphs={1: object()},
        object_blockers={1: {(4, 4)}},
        macro_graph=SimpleNamespace(warp_locations={1: ((2, 3),)}),
        rom=b"fixture",
    )
    result = regional.enumerate_red_regional_acquisitions(
        runtime,
        _observation(),
        actions,
        world,
        maximum_actions=30000,
        maximum_frames=3000000,
        routed_recovery=True,
    )
    expected = [items[2].source_id, items[1].source_id, items[0].source_id]
    if not registered:
        expected = expected[1:]
    assert [item.source_id for item in result] == expected
    assert len(opportunistic) == (3 if registered else 0)

    def moving(self, observation, routed_kinds):
        assert routed_kinds == frozenset({GoalKind.ACQUIRE_SPECIES})
        runtime.emulator.frame_count += 1
        return SimpleNamespace(bindings=())

    monkeypatch.setattr(Router, "enumerate_routed_kinds", moving)
    with pytest.raises(ValueError, match="changed the game"):
        regional.enumerate_red_regional_acquisitions(
            runtime,
            _observation(),
            actions,
            world,
            maximum_actions=30000,
            maximum_frames=3000000,
            routed_recovery=True,
        )


def test_topology_rank_is_nearby_first_and_keeps_unreachable_sources_last(monkeypatch):
    sources = ("wild:Far:grass", "wild:Lost:grass", "wild:Here:grass")
    map_ids = {sources[0]: 3, sources[1]: 4, sources[2]: 1}
    monkeypatch.setattr(regional, "map_id_for_wild_source", map_ids.__getitem__)

    def topology(_graph, start, goal, *, last_outside):
        assert (start, last_outside) == (1, 7)
        if goal == 4:
            raise regional.GlobalRouterError("disconnected")
        costs = {1: (), 3: (SimpleNamespace(cost=5),)}
        return SimpleNamespace(edges=costs[goal])

    monkeypatch.setattr(regional, "find_macro_path", topology)
    world = SimpleNamespace(
        macro_graph=object(),
        terrain={1: object(), 3: object(), 4: object()},
        local_graphs={1: object(), 3: object(), 4: object()},
    )
    assert regional._rank_regional_sources(
        sources, world, current_map=1, last_outside_map=7
    ) == ((sources[2], 1), (sources[0], 3), (sources[1], 4))


def test_topology_rank_accounts_for_observed_fly_origins(monkeypatch):
    sources = ("wild:WalkNear:grass", "wild:FlyNear:grass")
    map_ids = {sources[0]: 2, sources[1]: 3}
    monkeypatch.setattr(regional, "map_id_for_wild_source", map_ids.__getitem__)

    def topology(_graph, start, goal, *, last_outside):
        assert last_outside in {7, 5}
        costs = {(100, 2): 3, (100, 3): 8, (5, 2): 5, (5, 3): 0}
        return SimpleNamespace(
            edges=tuple(SimpleNamespace(cost=1) for _ in range(costs[start, goal]))
        )

    monkeypatch.setattr(regional, "find_macro_path", topology)
    world = SimpleNamespace(
        macro_graph=object(),
        terrain={2: object(), 3: object()},
        local_graphs={2: object(), 3: object()},
    )
    assert regional._rank_regional_sources(
        sources,
        world,
        current_map=100,
        last_outside_map=7,
        fly_origins=(5,),
    ) == ((sources[1], 3), (sources[0], 2))


@pytest.mark.parametrize("completed_sources", [0, 10])
def test_enumeration_stops_after_target_or_fixed_routed_source_bound(
    monkeypatch, completed_sources,
):
    items = tuple(
        _candidate(f"wild:Route{number}:grass", effort=number / 40)
        for number in range(2, 12 + completed_sources)
    )
    monkeypatch.setattr(
        regional,
        "RED_ACQUISITION_CATALOG",
        SimpleNamespace(
            methods=tuple(
                SimpleNamespace(source_id=item.source_id, kind=RedAcquisitionKind.WILD)
                for item in items
            )
        ),
    )
    ranked = tuple((item.source_id, index + 1) for index, item in enumerate(reversed(items)))
    completed = {source for source, _map_id in ranked[:completed_sources]}
    demand_checked = []

    def has_demand(runtime, observation, actions):
        item = next(item for item in items if item.profile == runtime.profile)
        demand_checked.append(item.source_id)
        return item.source_id not in completed

    monkeypatch.setattr(regional, "_source_has_acquisition_demand", has_demand)
    monkeypatch.setattr(regional, "_rank_regional_sources", lambda *a, **k: ranked)
    monkeypatch.setattr(
        regional, "derive_red_living_dex_wild_corridor", lambda target, *a, **k: target
    )
    monkeypatch.setattr(
        regional,
        "retarget_red_wild_profile",
        lambda profile, target, *, rom: next(
            item.profile for item in items if item.source_id == target.source_id
        ),
    )
    monkeypatch.setattr(
        regional, "bind_red_local_discovery_profile", lambda profile, *a: profile
    )
    evaluated = []

    class Router:
        include_bindings = True

        def __init__(self, runtime, *a, **kw):
            self.profile = runtime.profile

        def enumerate_routed_kinds(self, observation, routed_kinds):
            item = next(item for item in items if item.profile == self.profile)
            evaluated.append(item.source_id)
            return SimpleNamespace(bindings=(item.binding,) if self.include_bindings else ())

    monkeypatch.setattr(regional, "RedResourceGoalRouter", Router)
    runtime = _Runtime(
        items[0].profile,
        SimpleNamespace(frame_count=0),
        reader=SimpleNamespace(read_retained_outside_map=lambda: 7),
    )
    world = SimpleNamespace(
        terrain={index + 1: object() for index in range(len(items))},
        local_graphs={index + 1: object() for index in range(len(items))},
        object_blockers={index + 1: frozenset() for index in range(len(items))},
        macro_graph=SimpleNamespace(warp_locations={}),
        rom=b"fixture",
    )
    result = regional.enumerate_red_regional_acquisitions(
        runtime,
        _observation(),
        SimpleNamespace(actions_executed=0),
        world,
        maximum_actions=30000,
        maximum_frames=3000000,
    )
    assert evaluated == [
        source for source, _map_id in ranked[completed_sources:completed_sources + 4]
    ]
    assert demand_checked == [source for source, _map_id in ranked[:completed_sources + 4]]
    assert len(result) == regional.TARGET_SOURCE_CANDIDATES

    Router.include_bindings = False
    evaluated.clear()
    result = regional.enumerate_red_regional_acquisitions(
        runtime,
        _observation(),
        SimpleNamespace(actions_executed=0),
        world,
        maximum_actions=30000,
        maximum_frames=3000000,
    )
    assert result == ()
    assert evaluated == [
        source
        for source, _map_id in ranked[
            completed_sources:completed_sources + regional.MAXIMUM_ROUTED_SOURCE_EVALUATIONS
        ]
    ]

    completed.update(source for source, _map_id in ranked)
    evaluated.clear()
    assert regional.enumerate_red_regional_acquisitions(
        runtime, _observation(), SimpleNamespace(actions_executed=0), world,
        maximum_actions=30000, maximum_frames=3000000,
    ) == ()
    assert evaluated == []


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
def test_source_prefilter_reuses_registered_precursor_demand(
    missing, stock, protected, offered, expected,
):
    from test_red_acquisition import _observation as collection_observation

    source = "wild:Route7:grass"
    credited = frozenset(RED_SOLO_COLLECTION_CONTRACT.target_species) - {
        red_species_ref(n) for n in missing
    }
    catalog = replace(
        RED_ACQUISITION_CATALOG,
        remaining_demand=True,
        registered_species=credited,
        protected_counts=((red_species_ref(58), protected),),
        wild_source_species=((source, (red_species_ref(offered),)),),
    )
    provider = RedAreaSurveyGoalProvider(
        source, None, None, None, None, catalog=catalog,
    )
    observation = replace(
        _observation(),
        collection_observation=replace(
            collection_observation(*stock), owned_species=credited,
        ),
    )
    runtime = SimpleNamespace(provider_for=lambda _kind, _actions: provider)
    assert regional._source_has_acquisition_demand(runtime, observation, None) is expected
