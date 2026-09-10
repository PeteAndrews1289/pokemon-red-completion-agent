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
from pokemon_red_completion.red_acquisition import RedAcquisitionKind
from pokemon_red_completion.red_goal_context_profile import (
    _thaw,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)


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


def test_enumeration_uses_only_real_wild_bindings_and_preserves_action_counters(monkeypatch):
    items = [_candidate("wild:Route2:grass", 0.7), _candidate("wild:Route11:grass", 0.2)]
    methods = [
        SimpleNamespace(source_id=item.source_id, kind=RedAcquisitionKind.WILD) for item in items
    ]
    methods.append(SimpleNamespace(source_id="safari:unsupported", kind=RedAcquisitionKind.SAFARI))
    monkeypatch.setattr(regional, "RED_ACQUISITION_CATALOG", SimpleNamespace(methods=methods))
    monkeypatch.setattr(regional, "map_id_for_wild_source", lambda source: 1)
    monkeypatch.setattr(
        regional, "derive_red_living_dex_wild_corridor", lambda target, *a, **k: target
    )
    def retarget(profile, target, *, rom):
        assert rom == b"fixture"
        return next(i.profile for i in items if i.source_id == target.source_id)
    monkeypatch.setattr(regional, "retarget_red_wild_profile", retarget)
    monkeypatch.setattr(regional, "bind_red_local_discovery_profile", lambda profile, *a: profile)

    class Router:
        def __init__(self, runtime, *a, **kw):
            assert kw["include_recovery_offers"] is False
            assert kw["routed_recovery"] is True
            self.profile = runtime.profile

        def enumerate(self, observation):
            return SimpleNamespace(
                bindings=(next(i.binding for i in items if i.profile == self.profile),)
            )

    monkeypatch.setattr(regional, "RedResourceGoalRouter", Router)
    runtime = _Runtime(items[0].profile, SimpleNamespace(frame_count=0))
    actions = SimpleNamespace(actions_executed=0)
    world = SimpleNamespace(
        terrain={1: object()},
        local_graphs={1: object()},
        object_blockers={1: set()},
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
    assert [item.source_id for item in result] == [items[1].source_id, items[0].source_id]

    def moving(self, observation):
        runtime.emulator.frame_count += 1
        return SimpleNamespace(bindings=())

    monkeypatch.setattr(Router, "enumerate", moving)
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
