"""Real graph/patch derivation with a synthetic skill, never live capture evidence."""
from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest
from test_red_goal_skills import _adapter, _raw, _Reader
from test_red_living_dex_wild_corridor import _graph, _local_discovery_profile, _terrain

import pokemon_red_completion.red_observed_local_capture as local
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalAvailability, GoalKind, GoalUnavailableReason
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.local_router import LocalGraph
from pokemon_red_completion.observation import CurrentMapBlocks, MapId
from pokemon_red_completion.red_goal_context_profile import bind_observed_local_capture_profile
from pokemon_red_completion.route_executor import TraversalSnapshot


@dataclass
class Runtime:
    profile: object
    reader: object
    adapter: object
    emulator: object
    registration_policy: object


@dataclass
class Router:
    runtime: Runtime
    world: object
    actions: CountingExecutor
    calls: list
    source_ref: str = 'pokemon.red:acquisition:wild:Route2:grass'
    prepare_capture_party: bool = True
    prepare_capture_storage: bool = True
    prepare_capture_escort: bool = True
    include_recovery_offers: bool = True

    def enumerate(self, observation):
        capture = self.runtime.profile.providers[0]
        assert 'observed_local_capture' not in capture.parameters
        assert not self.prepare_capture_party and not self.prepare_capture_storage
        assert not self.prepare_capture_escort and not self.include_recovery_offers
        self.calls.append(('qualified', capture.parameters, self.world))

        def execute():
            self.actions.execute(MacroAction(MacroActionKind.WAIT))
            self.runtime.emulator.frame_count += 60
            self.calls.append(('executed',))
            return GoalExecutionReport(1, 60, {'synthetic_skill': True})

        def verify(report):
            assert report.evidence['synthetic_skill'] is True
            self.calls.append(('verified',))
            return GoalVerification.succeeded()

        binding = ExecutableGoalBinding('synthetic-child', GoalKind.ACQUIRE_SPECIES,
            .2, .1, execute, verify, search_source_ref=self.source_ref)
        unavailable = replace(binding.opportunity, binding_ref='unavailable',
                              availability=GoalAvailability.UNAVAILABLE,
                              estimated_effort=None, estimated_risk=None,
                              unavailable_reason=GoalUnavailableReason.MISSING_CAPABILITY)
        return GoalBindingSet((binding.opportunity, unavailable), (binding,))


@pytest.fixture
def scene(monkeypatch):
    map_id = int(MapId.ROUTE_2)
    template = _adapter(_Reader(raw=_raw(), ready=True)).observe()
    observation = replace(template, raw=replace(template.raw,
        map_id=map_id, player_y=3, player_x=4), input_ready=True)
    state = SimpleNamespace(observation=observation,
        blocks=CurrentMapBlocks(map_id, ((1, 2, 3), (4, 5, 6), (7, 8, 9))),
        traversal=TraversalSnapshot(map_id, (3, 4), True, mode='land'))
    reader = SimpleNamespace(read_current_map_blocks=lambda: state.blocks)
    live = SimpleNamespace(terrain={map_id: _terrain()},
        local_graphs={map_id: _graph()}, object_blockers={map_id: frozenset()},
        macro_graph=SimpleNamespace(warp_locations={}), rom=b'no ROM decoder needed for Route2')
    blocks_read = []

    def overlay(blocks):
        blocks_read.append(blocks)
        return live

    world = SimpleNamespace(with_current_blocks=overlay, rom=live.rom)
    runtime = Runtime(bind_observed_local_capture_profile(_local_discovery_profile()),
        reader, SimpleNamespace(observe=lambda: state.observation),
        SimpleNamespace(frame_count=0), object())
    actions = CountingExecutor(SimpleNamespace(execute=lambda action: None))
    router = Router(runtime, world, actions, [])
    monkeypatch.setattr(local, 'Gen1TrainerSightProjector', lambda *_: object())
    monkeypatch.setattr(local, 'Gen1TraversalObserver',
        lambda *_a, **_k: SimpleNamespace(observe=lambda: state.traversal))

    def bind():
        return local.bind_observed_local_capture(
            router, runtime.profile.providers[0], state.observation)

    return SimpleNamespace(router=router, runtime=runtime, state=state,
        live=live, bind=bind, blocks_read=blocks_read, map_id=map_id)


def test_unreachable_canonical_patch_is_replaced_only_inside_the_same_source(scene):
    declared = scene.runtime.profile
    assert declared.providers[0].parameters['player_x'] == 1
    binding = scene.bind()
    assert binding is not None and scene.router.actions.actions_executed == 0
    params = scene.router.calls[0][1]
    assert (params['player_y'], params['player_x']) == (3, 4)
    assert params['source_id'] == 'wild:Route2:grass'
    assert params['maximum_encounters'] == declared.providers[0].parameters['maximum_encounters']
    assert scene.runtime.profile is declared
    assert scene.blocks_read == [scene.state.blocks]
    report = binding.execute()
    assert (report.actions_executed, report.frames_executed) == (1, 60)
    assert binding.verify(report).status.value == 'succeeded'
    assert [x[0] for x in scene.router.calls] == ['qualified', 'executed', 'verified']
    with pytest.raises(local.RedObservedLocalCaptureError, match='already'):
        binding.execute()


@pytest.mark.parametrize('available', [False, True])
def test_real_resource_router_never_reinstates_static_capture(scene, monkeypatch, available):
    import pokemon_red_completion.red_resource_goal_router as routing

    child = scene.bind()
    assert child is not None
    other = replace(child.opportunity, binding_ref='unavailable-other',
                    kind=GoalKind.RESTORE_TEAM, availability=GoalAvailability.UNAVAILABLE,
                    estimated_effort=None, estimated_risk=None,
                    unavailable_reason=GoalUnavailableReason.MISSING_CAPABILITY)
    old = GoalBindingSet((child.opportunity, other), (child,))
    scene.runtime.enumerator = lambda _: SimpleNamespace(enumerate=lambda _: old)
    monkeypatch.setattr(routing, 'Gen1TraversalObserver',
                        lambda *_a, **_k: SimpleNamespace(observe=lambda: scene.state.traversal))
    monkeypatch.setattr(routing, 'Gen1TrainerSightProjector', lambda *_: object())
    monkeypatch.setattr(
        routing, 'red_living_dex_setup_fresh_observation_sha256', lambda _: '0' * 64)
    monkeypatch.setattr(local, 'bind_observed_local_capture',
                        lambda *_: child if available else None)
    router = routing.RedResourceGoalRouter(
        runtime=scene.runtime, world=scene.router.world, actions=scene.router.actions,
        prepare_capture_storage=False, prepare_capture_party=False,
        prepare_capture_escort=False, include_recovery_offers=False)
    result = router.enumerate(scene.state.observation)
    assert result.bindings == ((child,) if available else ())
    assert result.opportunities[1] == other
    assert result.opportunities[0].availability is (
        GoalAvailability.AVAILABLE if available else GoalAvailability.UNAVAILABLE)
    assert scene.router.actions.actions_executed == 0


def test_profile_transition_and_retarget_preserve_history():
    from pokemon_red_completion.red_living_dex_provider_curriculum import RedEncounterSourceTarget
    from pokemon_red_completion.red_living_dex_wild_corridor import (
        derive_red_living_dex_wild_corridor,
        retarget_red_wild_profile,
    )

    old = _local_discovery_profile()
    enabled = bind_observed_local_capture_profile(old)
    assert 'observed_local_capture' not in old.providers[0].parameters
    assert enabled.profile_sha256 != old.profile_sha256
    corridor = derive_red_living_dex_wild_corridor(
        RedEncounterSourceTarget('wild:Route2:grass'), _terrain(), _graph())
    assert retarget_red_wild_profile(enabled, corridor).providers[0].parameters[
        'observed_local_capture'] is True


@pytest.mark.parametrize('invalid', [1, 'true', None])
def test_profile_rejects_non_boolean_observed_capture(invalid):
    import json

    from pokemon_red_completion.red_goal_context_profile import (
        RedGoalContextProfileError,
        build_red_goal_context_profile_payload,
        parse_red_goal_context_profile,
    )

    old = _local_discovery_profile()
    payload = json.loads(build_red_goal_context_profile_payload(
        profile_id=old.profile_id,
        providers=tuple((s.kind, s.mechanic, dict(s.parameters)) for s in old.providers)))
    payload['providers'][0]['parameters']['observed_local_capture'] = invalid
    with pytest.raises(RedGoalContextProfileError, match='must be a boolean'):
        parse_red_goal_context_profile(
            (json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n').encode())


@pytest.mark.parametrize('barrier', ['disconnected', 'one_way', 'occupied', 'object', 'warp',
                                     'requirement', 'water', 'transient'])
def test_unavailable_current_patch_never_falls_back_across_the_barrier(scene, barrier):
    graph = scene.live.local_graphs[scene.map_id]
    edges = dict(graph.edges)
    if barrier == 'disconnected':
        scene.state.traversal = replace(scene.state.traversal, at=(0, 0))
        scene.state.observation = replace(scene.state.observation,
            raw=replace(scene.state.observation.raw, player_y=0, player_x=0))
    elif barrier == 'one_way':
        edges.pop((2, 4))
    elif barrier == 'occupied':
        scene.state.traversal = replace(scene.state.traversal, occupied=frozenset({(2, 4)}))
    elif barrier == 'object':
        scene.live.object_blockers[scene.map_id] = frozenset({(2, 4)})
    elif barrier == 'warp':
        scene.live.macro_graph.warp_locations[scene.map_id] = ((2, 4),)
    elif barrier == 'requirement':
        edges[(3, 4)] = tuple(replace(e, requirements=frozenset({'unavailable'}))
                               for e in edges[(3, 4)])
    elif barrier == 'water':
        edges[(3, 4)] = tuple(replace(e, result_mode='water') for e in edges[(3, 4)])
    else:
        edges[(3, 4)] = tuple(replace(e, transient=(1, 4)) for e in edges[(3, 4)])
        scene.state.traversal = replace(scene.state.traversal, occupied=frozenset({(1, 4)}))
    scene.live.local_graphs[scene.map_id] = LocalGraph(edges)
    assert scene.bind() is None
    assert scene.router.calls == [] and scene.router.actions.actions_executed == 0


@pytest.mark.parametrize('change', ['blocks', 'observation'])
def test_stale_qualified_state_stops_before_inner_input(scene, change):
    binding = scene.bind()
    if change == 'blocks':
        scene.state.blocks = CurrentMapBlocks(scene.map_id, ((9, 9), (9, 9)))
    else:
        scene.state.observation = replace(scene.state.observation,
            raw=replace(scene.state.observation.raw, player_money=1))
    with pytest.raises(local.RedObservedLocalCaptureError):
        binding.execute()
    assert scene.router.actions.actions_executed == 0
    assert [x[0] for x in scene.router.calls] == ['qualified']


def test_wrong_underlying_source_is_not_silently_relabelled(scene):
    scene.router.source_ref = 'pokemon.red:acquisition:wild:Route11:grass'
    with pytest.raises(local.RedObservedLocalCaptureError, match='selected source'):
        scene.bind()
    assert scene.router.actions.actions_executed == 0


@pytest.mark.parametrize('change', ['position', 'readiness', 'interruption', 'blocks_map'])
def test_incoherent_readers_fail_closed(scene, change):
    if change == 'position':
        scene.state.traversal = replace(scene.state.traversal, at=(2, 4))
    elif change == 'readiness':
        scene.state.traversal = replace(scene.state.traversal, ready=False)
    elif change == 'interruption':
        scene.state.traversal = replace(scene.state.traversal, interruption='battle')
    else:
        scene.state.blocks = CurrentMapBlocks(1, scene.state.blocks.rows)
    with pytest.raises(local.RedObservedLocalCaptureError):
        scene.bind()
    assert scene.router.actions.actions_executed == 0 and scene.router.calls == []


@pytest.mark.parametrize('change', ['legacy', 'nonregistered', 'battle', 'unready', 'remote'])
def test_scope_is_explicit_and_actual_current_map_only(scene, change):
    if change == 'legacy':
        scene.runtime.profile = _local_discovery_profile()
    elif change == 'nonregistered':
        scene.runtime.registration_policy = None
    elif change == 'battle':
        scene.state.observation = replace(scene.state.observation,
            raw=replace(scene.state.observation.raw, battle_state=1))
    elif change == 'unready':
        scene.state.observation = replace(scene.state.observation, input_ready=False)
    else:
        scene.state.observation = replace(scene.state.observation,
            raw=replace(scene.state.observation.raw, map_id=1))
    assert scene.bind() is None and scene.router.actions.actions_executed == 0
