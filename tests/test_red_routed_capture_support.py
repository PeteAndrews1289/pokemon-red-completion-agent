from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from test_red_capture_party import box, party

import pokemon_red_completion.red_routed_capture_support as support
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)


@dataclass
class Router:
    runtime: object
    actions: object
    world: object
    fresh_binding: object
    prepare_capture_party: bool = True

    def enumerate(self, _observation):
        assert not self.prepare_capture_party
        return GoalBindingSet(
            (self.fresh_binding.opportunity, unavailable()), (self.fresh_binding,),
        )

    def _replan(self, _request):
        raise AssertionError('not needed by this bounded transport')


def unavailable():
    from pokemon_red_completion.goal_manager import (
        GoalAvailability,
        GoalOpportunity,
        GoalUnavailableReason,
    )
    return GoalOpportunity('resupply', GoalKind.RESUPPLY, GoalAvailability.UNAVAILABLE,
                           unavailable_reason=GoalUnavailableReason.MISSING_RESOURCE)


def fixture(monkeypatch):
    calls = []
    actions = SimpleNamespace(actions_executed=0)
    emulator = SimpleNamespace(frame_count=0)
    observation = SimpleNamespace(party=party(), collection_observation='all eight specimens')
    reader = SimpleNamespace(
        read_current_box_state=lambda: SimpleNamespace(box_index=0),
        read_current_box_move_members=box,
    )
    runtime = SimpleNamespace(
        reader=reader, emulator=emulator,
        profile=SimpleNamespace(providers=(SimpleNamespace(kind=GoalKind.ACQUIRE_SPECIES,
            parameters={'source_id': 'wild:Route24:grass'}),)),
        adapter=SimpleNamespace(observe=lambda: observation),
    )
    route = SimpleNamespace(steps=(), terminal_map=64)
    world = SimpleNamespace(plan_feasible_to_map=lambda *_a, **_k: route)
    monkeypatch.setattr(support, 'Gen1TraversalObserver',
                        lambda _: SimpleNamespace(observe=lambda: object()))
    monkeypatch.setattr(support, '_POKEMON_CENTER_MAPS', (64,))
    monkeypatch.setattr(support, 'dependency_specimen_ledger', lambda value: value)
    monkeypatch.setattr(support, 'prepare_center_departure', lambda *_: None)
    monkeypatch.setattr(support, 'PokemonRedPartyReader',
                        lambda _: SimpleNamespace(read=lambda: party()))
    monkeypatch.setattr(support, 'Gen1RouteInterruptionHandler', lambda *_a, **_k: object())
    def travel(*_args, **_kwargs):
        calls.append('travel')
        actions.actions_executed += 7
        emulator.frame_count += 50
        return SimpleNamespace(passed=True)
    def pc(plan, *_args, **_kwargs):
        calls.append(('pc', plan.helper.box_slot, plan.deposit_party_slot))
        actions.actions_executed += 3
        emulator.frame_count += 20
        return {'capture_party_prepared': True, 'setup_training_rows': 0}
    monkeypatch.setattr(support, 'execute_route', travel)
    monkeypatch.setattr(support, 'execute_capture_party_at_pc', pc)
    def capture():
        calls.append('capture')
        actions.actions_executed += 5
        emulator.frame_count += 30
        return GoalExecutionReport(5, 30, {'capture_support': {
            'status_attempts': 3, 'verified_status_observations': 1, 'party_preparations': 0}})
    def verify(report):
        assert report.actions_executed == 5 and report.frames_executed == 30
        calls.append('verify')
        return GoalVerification.succeeded()
    original = ExecutableGoalBinding('pokemon.red:acquisition:wild:Route24:grass:profile-old',
        GoalKind.ACQUIRE_SPECIES, .2, .1,
        execute=lambda: pytest.fail('must not execute stale-origin binding'), verify=verify)
    fresh = ExecutableGoalBinding('routed-from-PC', GoalKind.ACQUIRE_SPECIES, .2, .1,
        execute=capture, verify=verify,
        search_source_ref='pokemon.red:acquisition:wild:Route24:grass')
    router = Router(runtime, actions, world, fresh)
    bindings = GoalBindingSet((original.opportunity, unavailable()), (original,))
    return router, bindings, observation, calls


def test_pc_setup_preserves_selected_source_and_meters_every_action(monkeypatch):
    router, bindings, observation, calls = fixture(monkeypatch)
    result = support.bind_capture_party_support(router, bindings, observation)
    assert calls == [] and router.actions.actions_executed == 0
    binding = result.bindings[0]
    assert binding.binding_ref != bindings.bindings[0].binding_ref
    assert result.opportunities[0] == binding.opportunity
    assert binding.estimated_effort > bindings.bindings[0].estimated_effort
    report = binding.execute()
    assert (report.actions_executed, report.frames_executed) == (15, 100)
    assert report.evidence['setup_training_rows'] == 0
    assert report.evidence['capture_support'] == {
        'status_attempts': 3, 'verified_status_observations': 1, 'party_preparations': 1}
    assert binding.verify(report).status.value == 'succeeded'
    assert calls == ['travel', ('pc', 2, 6), 'capture', 'verify']
    with pytest.raises(support.RedCapturePartyError, match='consumed'):
        binding.execute()


def test_rebinding_cannot_silently_change_the_destination(monkeypatch):
    from dataclasses import replace
    router, bindings, observation, calls = fixture(monkeypatch)
    router.fresh_binding = replace(router.fresh_binding, search_source_ref='different-source')
    binding = support.bind_capture_party_support(router, bindings, observation).bindings[0]
    with pytest.raises(support.RedCapturePartyError, match='selected source'):
        binding.execute()
    assert 'capture' not in calls
    with pytest.raises(support.RedCapturePartyError, match='consumed'):
        binding.execute()


def test_absent_helper_masks_only_capture_without_input(monkeypatch):
    router, bindings, observation, calls = fixture(monkeypatch)
    router.runtime.reader.read_current_box_move_members = lambda: (box()[0],)
    result = support.bind_capture_party_support(router, bindings, observation)
    assert result.bindings == () and calls == []
    assert result.opportunities[0].availability.value == 'unavailable'
    assert result.opportunities[1] == bindings.opportunities[1]
