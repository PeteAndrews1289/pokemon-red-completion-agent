from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_goal_context_profile import _supply_transition_profile
from test_red_indoor_collection_departure import cartridge
from test_red_routed_recovery import make_fixture, make_real_route, make_test_party

import pokemon_red_completion.red_dig_recovery as dig
import pokemon_red_completion.red_routed_recovery as recovery
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import OverworldMovementMode
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    _thaw,
    bind_dig_recovery_profile,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError


def scene(monkeypatch):
    router, bindings, observe, state, ledger, calls = make_fixture(monkeypatch)
    state['raw'] = replace(state['raw'], map_id=161, party_hp=(30, 15),
                           party_moves=((1, 2), (91, 4)))
    state['party'] = make_test_party(30, 15)
    router.runtime.profile = bind_dig_recovery_profile(_supply_transition_profile())
    reader = router.runtime.reader
    reader.read_overworld_movement_mode = lambda: OverworldMovementMode.WALKING
    reader.read_pending_trainer_battle_identity = lambda: None
    reader.read_fly_menu_state = lambda: None
    reader.read_current_map_tileset = lambda: 17
    reader.read_last_blackout_map = lambda: 5
    router.world.rom = cartridge()
    router.world.local_graphs = {5: SimpleNamespace(edges={(6, 9): ()})}
    router.world.object_blockers = {5: frozenset()}

    def route(start, _map, goal_at):
        if start.map_id == 161:
            raise RoutePlanningError('no walk out')
        assert start.map_id == 5 and start.at == (6, 9)
        assert goal_at == (7, 3)
        return make_real_route()

    router.world.plan_feasible_to_map = route
    traversal = SimpleNamespace(observe=lambda: TraversalSnapshot(
        state['raw'].map_id, (state['raw'].player_y, state['raw'].player_x),
        True, mode='land',
    ))
    monkeypatch.setattr(dig, 'Gen1TraversalObserver', lambda _: traversal)
    monkeypatch.setattr(recovery, 'Gen1TraversalObserver', lambda _: traversal)
    monkeypatch.setattr(dig, '_POKEMON_CENTER_MAPS', frozenset({64}))
    monkeypatch.setattr(dig, 'dependency_specimen_ledger', lambda c: tuple(c.specimens))

    def escape(actions, _reader, _emulator, *, expected_map):
        assert expected_map == 5
        actions.execute(MacroAction(MacroActionKind.WAIT))
        state['raw'] = replace(state['raw'], map_id=5, player_y=6, player_x=9)
        calls.append('dig')

    monkeypatch.setattr(dig, '_field_dig', escape)
    return router, bindings, observe, state, ledger, calls


def bind(s):
    router, bindings, observe, *_ = s
    return recovery.bind_routed_center_recovery(
        router, bindings, observe(), prepare_escort=lambda: None,
    )


def test_escape_then_fresh_heal_retains_cost_and_does_not_execute_other_goal(monkeypatch):
    s = scene(monkeypatch)
    router, _, _, state, _, calls = s
    offer = bind(s)
    assert calls == [] and router.actions.actions_executed == 0
    selected = next(b for b in offer.bindings if b.kind is GoalKind.RESTORE_TEAM)
    report = selected.execute()
    assert calls == ['dig', 'transport']
    assert report.evidence['dig_recovery']['escape_actions'] == 1
    assert report.actions_executed == router.actions.actions_executed > 1
    assert selected.verify(report).status.value == 'succeeded'
    assert state['raw'].party_hp == (30, 30)
    with pytest.raises(dig.RedDigRecoveryError, match='consumed'):
        selected.execute()


@pytest.mark.parametrize('fault', ['flag', 'terrain', 'holder', 'anchor', 'pending', 'landing'])
def test_unavailable_escape_remains_unavailable_without_input(monkeypatch, fault):
    s = scene(monkeypatch)
    router, _, _, state, _, calls = s
    if fault == 'flag':
        router.runtime.profile = _supply_transition_profile()
    elif fault == 'terrain':
        router.runtime.reader.read_current_map_tileset = lambda: 0
    elif fault == 'holder':
        state['raw'] = replace(state['raw'], party_hp=(30, 0))
    elif fault == 'anchor':
        router.runtime.reader.read_last_blackout_map = lambda: 200
    elif fault == 'pending':
        router.runtime.reader.read_pending_trainer_battle_identity = lambda: (1, 2)
    else:
        router.world.object_blockers[5] = frozenset({(6, 9)})
    assert not any(b.kind is GoalKind.RESTORE_TEAM for b in bind(s).bindings)
    assert calls == [] and router.actions.actions_executed == 0


@pytest.mark.parametrize('fault', ['anchor', 'hp', 'bag', 'ledger'])
def test_stale_origin_rejected_before_dig(monkeypatch, fault):
    s = scene(monkeypatch)
    router, _, _, state, ledger, calls = s
    selected = next(b for b in bind(s).bindings if b.kind is GoalKind.RESTORE_TEAM)
    if fault == 'anchor':
        router.runtime.reader.read_last_blackout_map = lambda: 6
    elif fault == 'hp':
        state['raw'] = replace(state['raw'], party_hp=(30, 14))
    elif fault == 'bag':
        state['raw'] = replace(state['raw'], bag_items=())
    else:
        ledger.specimens = ('changed',)
    with pytest.raises(dig.RedDigRecoveryError, match='changed before input'):
        selected.execute()
    assert calls == []


@pytest.mark.parametrize('fault', ['map', 'position', 'bag', 'money', 'party', 'exception'])
def test_bad_escape_never_runs_healing_or_hides_failure(monkeypatch, fault):
    s = scene(monkeypatch)
    router, _, _, state, _, calls = s
    selected = next(b for b in bind(s).bindings if b.kind is GoalKind.RESTORE_TEAM)
    normal = dig._field_dig

    def broken(*args, **kwargs):
        normal(*args, **kwargs)
        if fault == 'exception':
            raise RuntimeError('failed after input')
        if fault == 'party':
            state['party'] = make_test_party(30, 14)
        else:
            changes = {'map': {'map_id': 6}, 'position': {'player_x': 8},
                       'bag': {'bag_items': ()}, 'money': {'player_money': 210}}
            state['raw'] = replace(state['raw'], **changes[fault])

    monkeypatch.setattr(dig, '_field_dig', broken)
    with pytest.raises(RuntimeError):
        selected.execute()
    assert calls == ['dig']
    with pytest.raises(dig.RedDigRecoveryError, match='consumed'):
        selected.execute()


def test_opt_in_preserves_other_mechanics_and_old_identity():
    before = _supply_transition_profile()
    after = bind_dig_recovery_profile(before)
    assert before.profile_sha256 != after.profile_sha256
    assert before.providers[0] == after.providers[0] and before.providers[2] == after.providers[2]
    assert after.providers[1].parameters['dig_recovery'] is True
    assert not before.providers[1].parameters
    assert bind_dig_recovery_profile(after) == after


def test_escape_dispatch_budget_stops_a_runaway_compiler(monkeypatch):
    from pokemon_red_completion.goal_manager_composition_qualification import (
        CompositionActionBudgetExhausted,
    )

    s = scene(monkeypatch)
    selected = next(b for b in bind(s).bindings if b.kind is GoalKind.RESTORE_TEAM)

    def runaway(actions, *_args, **_kwargs):
        for _ in range(129):
            actions.execute(MacroAction(MacroActionKind.WAIT))

    monkeypatch.setattr(dig, '_field_dig', runaway)
    with pytest.raises(CompositionActionBudgetExhausted):
        selected.execute()
    assert s[0].actions.actions_executed == 128
    assert s[-1] == []


def test_dig_option_is_an_ordered_prospective_transition():
    import run_red_regional_learning_cycle as cycle

    parser = cycle._parser()
    action = next(a for a in parser._actions if '--dig-recovery' in a.option_strings)
    assert action.dest == 'regional_transitions' and action.const == 'dig-recovery'


@pytest.mark.parametrize('bad', [False, 0, 1, 'true', None])
def test_dig_flag_requires_literal_true(bad):
    before = _supply_transition_profile()
    providers = [(s.kind, s.mechanic, {**_thaw(s.parameters), 'dig_recovery': bad}
                  if s.kind is GoalKind.RESTORE_TEAM else _thaw(s.parameters))
                 for s in before.providers]
    with pytest.raises(RedGoalContextProfileError):
        parse_red_goal_context_profile(build_red_goal_context_profile_payload(
            profile_id=before.profile_id, providers=tuple(providers),
        ))
