from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_routed_capture_storage as storage
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.red_acquisition import RedAreaExecutionPolicy
from pokemon_red_completion.red_goal_skills import RedAreaSurveyGoalProvider
from pokemon_red_completion.route_plan import RoutePlanningError


@dataclass
class Router:
    runtime: object
    actions: object
    world: object
    fresh: object
    prepare_capture_storage: bool = True
    prepare_capture_party: bool = False

    def enumerate(self, _observation):
        unavailable = GoalOpportunity('unavailable-supply', GoalKind.RESUPPLY,
            GoalAvailability.UNAVAILABLE, unavailable_reason=GoalUnavailableReason.MISSING_RESOURCE)
        bindings = GoalBindingSet((self.fresh.opportunity, unavailable), (self.fresh,))
        return (storage.bind_capture_storage_support(self, bindings, _observation)
                if self.prepare_capture_storage else bindings)

    def _replan(self, _request):
        pytest.fail("no replan in this fixture")

    def plan_feasible_to_map(self, *args, **kwargs):
        return self.world.plan_feasible_to_map(*args, **kwargs)


def fixture(monkeypatch):
    calls = []
    actions = SimpleNamespace(actions_executed=0)
    emulator = SimpleNamespace(frame_count=0)
    raw = SimpleNamespace(map_id=22, player_y=5, player_x=6, battle_state=0,
                          bag_items=((4, 2),), player_money=109)
    collection = SimpleNamespace(current_box_index=0, box_counts=(19, 3, 0) + (20,) * 9,
                                 box_capacity=20, specimens=('a', 'a', 'b'))
    observation = SimpleNamespace(raw=raw, input_ready=True, collection_observation=collection,
                                  immediate_capture_slots=1)
    traversal = SimpleNamespace(observe=lambda: (raw.map_id, raw.player_y, raw.player_x))
    reader = SimpleNamespace()
    adapter = SimpleNamespace(observe=lambda: observation)
    provider = RedAreaSurveyGoalProvider('wild:Route24:grass', SimpleNamespace(), actions,
                                        emulator, adapter,
                                        policy=RedAreaExecutionPolicy(capture_quota=1))
    runtime = SimpleNamespace(reader=reader, emulator=emulator, adapter=adapter,
                              provider_for=lambda *_: provider)
    route = SimpleNamespace(steps=(1, 2), terminal_map=64)
    world = SimpleNamespace(plan_feasible_to_map=lambda *_a, **_k: route)
    monkeypatch.setattr(storage, 'Gen1TraversalObserver', lambda _: traversal)
    monkeypatch.setattr(storage, '_POKEMON_CENTER_MAPS', (64,))
    monkeypatch.setattr(storage, 'dependency_specimen_ledger', lambda c: tuple(c.specimens))
    monkeypatch.setattr(storage, 'prepare_center_departure', lambda *_: None)
    monkeypatch.setattr(storage, 'Gen1RouteInterruptionHandler', lambda *_a, **_k: None)
    monkeypatch.setattr('pokemon_red_completion.red_resource_goal_router._walking_plan',
                        lambda _: True)

    def tick(action_count, frame_count):
        actions.actions_executed += action_count
        emulator.frame_count += frame_count

    def travel(*_a, **_k):
        calls.append('travel')
        tick(7, 50)
        raw.map_id, raw.player_y, raw.player_x = 64, 4, 13
        return SimpleNamespace(passed=True)

    def face(*_a):
        calls.append('face')
        tick(1, 1)

    def open_pc(*_a):
        calls.append('open')
        tick(1, 1)

    def switch(*_a, target_box_index):
        calls.append(('switch', target_box_index))
        tick(3, 30)
        collection.current_box_index = target_box_index
        observation.immediate_capture_slots = 20 - collection.box_counts[target_box_index]
        return SimpleNamespace(passed=True)

    def close(*_a):
        calls.append('close')
        tick(1, 1)

    def capture():
        calls.append('capture')
        tick(5, 30)
        observation.immediate_capture_slots -= 1
        return GoalExecutionReport(5, 30, {'captures': 1})

    def verify(report):
        calls.append('verify')
        assert (report.actions_executed, report.frames_executed) == (5, 30)
        return GoalVerification.succeeded()

    monkeypatch.setattr(storage, 'execute_route', travel)
    monkeypatch.setattr(storage, 'face_pc_boundary', face)
    monkeypatch.setattr(storage, 'open_bills_pc', open_pc)
    monkeypatch.setattr(storage, 'switch_box', switch)
    monkeypatch.setattr(storage, 'close_menu', close)
    original = ExecutableGoalBinding('old-origin', GoalKind.ACQUIRE_SPECIES, .2, .1,
        execute=lambda: pytest.fail('stale binding executed'), verify=verify,
        search_source_ref='pokemon.red:acquisition:wild:Route24:grass')
    fresh = replace(original, binding_ref='new-origin', execute=capture)
    other = ExecutableGoalBinding('evolution', GoalKind.EVOLVE_SPECIES, .3, .1,
                                 execute=lambda: pytest.fail('goal changed'), verify=verify)
    bindings = GoalBindingSet((original.opportunity, other.opportunity), (original, other))
    router = Router(runtime, actions, world, fresh)
    return SimpleNamespace(router=router, bindings=bindings, observation=observation,
                           collection=collection, raw=raw, calls=calls, provider=provider,
                           tick=tick, switch=switch)


def test_rotation_is_action_free_until_selected_and_preserves_goal_and_full_cost(monkeypatch):
    f = fixture(monkeypatch)
    result = storage.bind_capture_storage_support(f.router, f.bindings, f.observation)
    assert f.calls == [] and f.router.actions.actions_executed == 0
    assert result.bindings[1] is f.bindings.bindings[1]
    selected = result.bindings[0]
    assert selected.binding_ref != 'old-origin'
    assert selected.search_source_ref == 'pokemon.red:acquisition:wild:Route24:grass'
    report = selected.execute()
    assert (report.actions_executed, report.frames_executed) == (18, 113)
    assert report.evidence['storage_preparation'] == {
        'box_rotations': 1, 'initial_headroom': 1, 'prepared_headroom': 20,
        'collection_preserved': True, 'setup_training_rows': 0,
        'actions_executed': 13, 'frames_executed': 83}
    assert selected.verify(report).status.value == 'succeeded'
    assert f.calls == ['travel', 'face', 'open', ('switch', 2), 'close', 'capture', 'verify']
    with pytest.raises(storage.RedCaptureStorageError, match='consumed'):
        selected.execute()


def test_roomy_capture_does_not_visit_pc(monkeypatch):
    f = fixture(monkeypatch)
    f.observation.immediate_capture_slots = 2
    assert storage.bind_capture_storage_support(f.router, f.bindings, f.observation) is f.bindings
    assert not f.calls


@pytest.mark.parametrize('condition', ['full', 'no_target', 'quota', 'route', 'field_move'])
def test_unsupported_storage_masks_only_capture_before_input(monkeypatch, condition):
    f = fixture(monkeypatch)
    if condition == 'full':
        f.observation.immediate_capture_slots = 0
    elif condition == 'no_target':
        f.collection.box_counts = (19,) * 12
    elif condition == 'quota':
        f.router.runtime.provider_for = lambda *_: replace(
            f.provider, policy=RedAreaExecutionPolicy(capture_quota=2))
    elif condition == 'route':
        def blocked(*_a, **_k):
            raise RoutePlanningError('blocked')
        f.router.world.plan_feasible_to_map = blocked
    else:
        monkeypatch.setattr('pokemon_red_completion.red_resource_goal_router._walking_plan',
                            lambda _: False)
    result = storage.bind_capture_storage_support(f.router, f.bindings, f.observation)
    assert len(result.bindings) == 1 and result.bindings[0].kind is GoalKind.EVOLVE_SPECIES
    assert result.opportunities[0].availability.value == 'unavailable'
    assert not f.calls


@pytest.mark.parametrize('change', ['location', 'box', 'specimens', 'room'])
def test_stale_preparation_fails_before_any_input(monkeypatch, change):
    f = fixture(monkeypatch)
    binding = storage.bind_capture_storage_support(f.router, f.bindings, f.observation).bindings[0]
    if change == 'location':
        f.raw.player_x += 1
    elif change == 'box':
        f.collection.current_box_index = 1
    elif change == 'specimens':
        f.collection.specimens = ('a', 'b')
    else:
        f.observation.immediate_capture_slots = 2
    with pytest.raises(storage.RedCaptureStorageError, match='changed before input'):
        binding.execute()
    assert not f.calls


@pytest.mark.parametrize('change', ['loss', 'wrong_box', 'money', 'not_ready', 'false_report'])
def test_pc_mutation_never_becomes_a_capture_or_success(monkeypatch, change):
    f = fixture(monkeypatch)
    def corrupt(*args, **kwargs):
        result = f.switch(*args, **kwargs)
        if change == 'loss':
            f.collection.specimens = ('a', 'b')
        elif change == 'wrong_box':
            f.collection.current_box_index = 1
        elif change == 'money':
            f.raw.player_money -= 1
        elif change == 'not_ready':
            f.observation.input_ready = False
        else:
            result.passed = False
        return result
    monkeypatch.setattr(storage, 'switch_box', corrupt)
    binding = storage.bind_capture_storage_support(f.router, f.bindings, f.observation).bindings[0]
    with pytest.raises(storage.RedCaptureStorageError, match='not preserved'):
        binding.execute()
    assert 'capture' not in f.calls


def test_storage_success_cannot_cover_a_failed_capture_or_wrong_source(monkeypatch):
    f = fixture(monkeypatch)
    f.router.fresh = replace(f.router.fresh, search_source_ref='pokemon.red:acquisition:elsewhere')
    binding = storage.bind_capture_storage_support(f.router, f.bindings, f.observation).bindings[0]
    with pytest.raises(storage.RedCaptureStorageError, match='selected source'):
        binding.execute()
    assert 'capture' not in f.calls


def test_failed_capture_verdict_is_not_replaced_by_successful_storage(monkeypatch):
    from pokemon_red_completion.goal_manager import GoalFailureReason

    f = fixture(monkeypatch)
    f.router.fresh = replace(f.router.fresh, verify=lambda _: GoalVerification.failed(
        GoalFailureReason.OUTCOME_NOT_VERIFIED))
    binding = storage.bind_capture_storage_support(f.router, f.bindings, f.observation).bindings[0]
    result = binding.execute()
    assert result.evidence['storage_preparation']['collection_preserved'] is True
    assert binding.verify(result).status.value == 'failed'


def test_capture_must_leave_the_reserved_active_slot(monkeypatch):
    f = fixture(monkeypatch)
    binding = storage.bind_capture_storage_support(f.router, f.bindings, f.observation).bindings[0]
    result = binding.execute()
    f.observation.immediate_capture_slots = 0
    assert binding.verify(result).status.value == 'failed'


def test_mismatched_original_source_is_not_silently_replaced(monkeypatch):
    f = fixture(monkeypatch)
    wrong = replace(f.bindings.bindings[0], search_source_ref='pokemon.red:acquisition:elsewhere')
    other = f.bindings.bindings[1]
    bindings = GoalBindingSet((wrong.opportunity, other.opportunity), (wrong, other))
    result = storage.bind_capture_storage_support(f.router, bindings, f.observation)
    assert result.bindings == (other,)
    assert not f.calls


def test_capture_helper_is_retrieved_before_storage_and_rebound_capture(monkeypatch):
    from test_red_capture_party import box, party

    import pokemon_red_completion.red_routed_capture_support as support

    f = fixture(monkeypatch)
    f.observation.party = party()
    f.router.prepare_capture_party = True
    runtime = f.router.runtime
    runtime.profile = SimpleNamespace(providers=(SimpleNamespace(kind=GoalKind.ACQUIRE_SPECIES,
        parameters={'source_id': 'wild:Route24:grass'}),))
    runtime.reader.read_current_box_state = lambda: SimpleNamespace(box_index=0)
    runtime.reader.read_current_box_move_members = box
    monkeypatch.setattr(support, 'Gen1TraversalObserver', storage.Gen1TraversalObserver)
    monkeypatch.setattr(support, '_POKEMON_CENTER_MAPS', (64,))
    monkeypatch.setattr(support, 'dependency_specimen_ledger', storage.dependency_specimen_ledger)
    monkeypatch.setattr(support, 'prepare_center_departure', lambda *_: None)
    monkeypatch.setattr(support, 'PokemonRedPartyReader',
                        lambda _: SimpleNamespace(read=party))
    monkeypatch.setattr(support, 'Gen1RouteInterruptionHandler', lambda *_a, **_k: None)
    monkeypatch.setattr(support, 'execute_route', storage.execute_route)

    def retrieve(*_args, **_kwargs):
        assert f.collection.current_box_index == 0
        f.calls.append('retrieve-helper')
        f.tick(2, 10)
        return {'capture_party_prepared': True, 'setup_training_rows': 0}

    monkeypatch.setattr(support, 'execute_capture_party_at_pc', retrieve)
    inner = storage.bind_capture_storage_support(f.router, f.bindings, f.observation)
    binding = support.bind_capture_party_support(f.router, inner, f.observation).bindings[0]
    result = binding.execute()
    assert binding.verify(result).status.value == 'succeeded'
    assert f.calls == ['travel', 'retrieve-helper', 'travel', 'face', 'open',
                       ('switch', 2), 'close', 'capture', 'verify']
    assert (result.actions_executed, result.frames_executed) == (27, 173)
    assert result.evidence['storage_preparation']['setup_training_rows'] == 0
    assert result.evidence['capture_support']['party_preparations'] == 1
