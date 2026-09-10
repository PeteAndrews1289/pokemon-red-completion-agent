"""A verified status-degraded exit ends the route; it never grants free walking."""
from dataclasses import replace
from types import SimpleNamespace

import pytest
import run_red_regional_learning_cycle as cycle

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.bounded_player_episode import _retain_executor_failure
from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_composition_runtime import CompositionBudgetCheckpoint
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalRecoveryRequired,
    GoalVerification,
)
from pokemon_red_completion.observation import BattleMenuPhase, BattleMenuState, RawGameState
from pokemon_red_completion.red_routed_recovery import RecoveryRouteInterruptionHandler
from pokemon_red_completion.route_1_wild import WildFleeStatusChange, flee_wild
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot


def encounter(status=0):
    return RawGameState(
        game_started=True, map_id=165, player_x=23, player_y=3, party_count=2,
        battle_state=1, party_species_ids=(41, 42), party_levels=(28, 31),
        party_hp=(93, 92), party_max_hp=(93, 92), party_status=(status, 0),
        party_moves=((2, 67, 43, 0), (113, 103, 49, 120)),
        party_pp=((25, 20, 30, 0), (30, 40, 20, 5)),
        first_party_level=28, first_party_hp=93, first_party_max_hp=93,
        first_party_status=status, first_party_pp=(25, 20, 30, 0),
        enemy_species_id=163, enemy_level=30, bag_items=((4, 6),),
        player_money=548, badge_bits=255, event_flags=b'\x00',
    )


def runtime(before, after, *, ready=True, drift=False):
    class Reader:
        raw = before

        def read(self):
            return self.raw

        def read_input_readiness(self):
            return SimpleNamespace(ready=ready)

        def read_battle_menu_state(self, _raw):
            return BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=3)

    reader = Reader()

    class Actions:
        calls = []

        def execute(self, action):
            self.calls.append(action)
            if action.kind is MacroActionKind.CONFIRM:
                reader.raw = after
            elif drift and action.kind is MacroActionKind.WAIT and action.repeat == 180:
                reader.raw = replace(after, player_x=24)

    return reader, Actions()


def call_flee(reader, actions, before):
    return flee_wild(actions, reader, before, expected_map_id=165,
                     route_name='test travel', stabilization_frames=180,
                     error_type=RouteExecutionError)


@pytest.mark.parametrize('status', [1, 7, 8, 16, 32, 64])
def test_new_status_qualifies_only_as_failure_cause(status):
    before = encounter()
    after = replace(before, battle_state=0, battle_result=2, first_party_hp=67,
                    party_hp=(67, 92), first_party_status=status, party_status=(status, 0))
    reader, actions = runtime(before, after)
    with pytest.raises(RouteExecutionError) as result:
        call_flee(reader, actions, before)
    assert isinstance(result.value.__cause__, WildFleeStatusChange)
    assert result.value.__cause__.after == after
    assert sum(a.kind is MacroActionKind.CONFIRM for a in actions.calls) == 1
    assert not any(a.kind is MacroActionKind.MOVE for a in actions.calls)


@pytest.mark.parametrize('status', [0, 16])
def test_unchanged_status_remains_ordinary_verified_escape(status):
    before = encounter(status)
    after = replace(before, battle_state=0, battle_result=2)
    reader, actions = runtime(before, after)
    assert call_flee(reader, actions, before).verified


@pytest.mark.parametrize('change', [
    {'player_x': 24}, {'map_id': 166}, {'battle_result': 0},
    {'first_party_pp': (24, 20, 30, 0)}, {'first_party_level': 29},
    {'first_party_max_hp': 94}, {'party_hp': (67, 0)}, {'party_hp': (67, 50)},
    {'party_pp': ((25, 20, 30, 0), (29, 40, 20, 5))},
    {'party_levels': (28, 32)}, {'party_species_ids': (41, 43)},
    {'party_status': (16, 8)}, {'party_status': None}, {'party_count': 1},
    {'first_party_status': 24, 'party_status': (24, 0)},
    {'player_money': 549}, {'bag_items': ((4, 5),)}, {'event_flags': b'\x01'},
])
def test_any_additional_boundary_change_is_not_recoverable(change):
    before = encounter()
    after = replace(before, battle_state=0, battle_result=2, first_party_hp=67,
                    party_hp=(67, 92), first_party_status=16, party_status=(16, 0))
    reader, actions = runtime(before, replace(after, **change))
    with pytest.raises(RouteExecutionError) as result:
        call_flee(reader, actions, before)
    assert not isinstance(result.value.__cause__, WildFleeStatusChange)


@pytest.mark.parametrize('ready,drift', [(False, False), (True, True)])
def test_control_and_post_settlement_position_remain_required(ready, drift):
    before = encounter()
    after = replace(before, battle_state=0, battle_result=2, first_party_hp=67,
                    party_hp=(67, 92), first_party_status=16, party_status=(16, 0))
    reader, actions = runtime(before, after, ready=ready, drift=drift)
    with pytest.raises(RouteExecutionError) as result:
        call_flee(reader, actions, before)
    assert not isinstance(result.value.__cause__, WildFleeStatusChange)


def test_collection_handler_rechecks_then_ends_goal_with_typed_failure():
    before = encounter()
    after = replace(before, battle_state=0, battle_result=2, first_party_hp=67,
                    party_hp=(67, 92), first_party_status=16, party_status=(16, 0))
    reader, actions = runtime(before, after)
    handler = RecoveryRouteInterruptionHandler(actions, reader, (41, 42), (0, 1))
    interruption = TraversalSnapshot(165, (3, 23), False, 'wild_battle')
    with pytest.raises(GoalRecoveryRequired):
        handler.handle(interruption)
    assert reader.raw == after
    assert not any(a.kind is MacroActionKind.MOVE for a in actions.calls)


def test_bounded_goal_retains_costs_and_typed_failure_without_success():
    state = {'actions': 0, 'frames': 0}

    def execute():
        state.update(actions=5, frames=240)
        raise GoalRecoveryRequired('private status transition')

    binding = ExecutableGoalBinding(
        binding_ref='private:status-fixture', kind=GoalKind.ACQUIRE_SPECIES,
        estimated_effort=0.2, estimated_risk=0.1,
        execute=execute, verify=lambda _: GoalVerification.succeeded(),
    )
    meter = SimpleNamespace(checkpoint=lambda: CompositionBudgetCheckpoint(
        controller_actions=state['actions'], emulator_frames=state['frames']))
    wrapped = _retain_executor_failure(binding, meter)
    report = wrapped.execute()
    assert report.actions_executed == 5 and report.frames_executed == 240
    assert wrapped.verify(report).failure_reason is GoalFailureReason.RECOVERY_REQUIRED


@pytest.mark.parametrize('reason,loss,expected', [
    ('recovery_required', False, True), ('binding_failed', False, False),
    ('recovery_required', True, False), ('search_exhausted', False, False),
])
def test_cycle_continuation_rejects_generic_errors_or_loss(reason, loss, expected):
    before = {'undeclared_specimen_losses': 0}
    after = dict(before, undeclared_specimen_losses=1) if loss else before.copy()
    parent = {'steps': [{'status': 'failed', 'failure_reason': reason,
                        'semantic_state_changed': True,
                        'collection_before': before, 'collection_after': after}]}
    assert cycle._safe_failed_terminal(parent, 'recovery_required') is expected
