import copy
import json
from dataclasses import replace

import numpy as np
import pytest
from test_red_movement_recurrence import facts
from test_red_live_option_menu import _binding, _fishing_candidate, _situation
from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion import red_movement_recurrence as recurrence
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet, GoalExecutionReport
from pokemon_red_completion.living_dex_option_value import LivingDexOptionValueModel, option_feature_names
from pokemon_red_completion.player_option_story_unit import OptionStoryUnit
from pokemon_red_completion.red_autonomous_player import AutonomousSnapshot, run_autonomous_options
from pokemon_red_completion.red_live_option_menu import build_red_live_option_set, supplemental_live_option
from pokemon_red_completion.resource_economy_observation import EconomySnapshot
from pokemon_red_completion.player_readiness import PlayerReadiness, READINESS_NAMES


def endpoint(map_id):
    f = facts()
    f['diagnostics']['map_id'] = map_id
    return f


def test_quoted_and_novel_endpoints_are_never_counted_as_returns():
    memory = GoalSearchMemory()
    a, b = endpoint(1), endpoint(2)
    recurrence.observe_movement_boundary(memory, a)
    assert recurrence.record_movement_return(memory, a, b) is None
    assert 'movement_returns' not in memory.private_dict()
    recurrence.observe_movement_boundary(memory, b)
    receipt = recurrence.record_movement_return(memory, b, a)
    assert receipt['equivalent_unchanged_returns'] == 1
    assert receipt['stop_required'] is False


def test_second_equivalent_paid_return_stops_across_checkpoint_renewal():
    memory = GoalSearchMemory()
    a, b = endpoint(1), endpoint(2)
    for f in (a, b): recurrence.observe_movement_boundary(memory, f)
    first = recurrence.record_movement_return(memory, a, b)
    prior = GoalSearchMemory.from_private_dict(memory.private_dict())
    restored = GoalSearchMemory.from_private_dict(memory.private_dict())
    second = recurrence.record_movement_return(restored, a, b)
    assert first['stop_required'] is False and second['stop_required'] is True
    assert second['goal_selected_or_masked'] is False
    restored.require_extension(prior)
    with pytest.raises(ValueError, match='lost a return'):
        prior.require_extension(restored)


@pytest.mark.parametrize('change', ['event', 'cash', 'xp', 'item', 'unknown'])
def test_real_observation_changes_or_unknowns_do_not_certify_an_identical_return(change):
    memory = GoalSearchMemory(); a, b = endpoint(1), endpoint(2)
    for f in (a, b): recurrence.observe_movement_boundary(memory, f)
    recurrence.record_movement_return(memory, a, b)
    b = copy.deepcopy(b)
    if change == 'event': b['movement_event_flags'] = '0101'
    elif change == 'cash': b['cash'] += 1
    elif change == 'xp': b['player_lesson']['party'][0]['experience'] += 1
    elif change == 'item': b['diagnostics']['bag_items'] = [[4, 3]]
    else: b['movement_coins'] = None
    assert recurrence.record_movement_return(memory, a, b) is None


@pytest.mark.parametrize('value', [True, 0, -1, 2**53, '2'])
def test_forged_persisted_return_counts_are_rejected(value):
    with pytest.raises(ValueError, match='return observations'):
        GoalSearchMemory.from_private_dict(dict(schema='pokemon.core.private-search-memory.v1',
                                               entries={}, movement_returns={'a'*64: value}))


def looping_player(tmp_path, *, enabled, chunk_size=20, memory=None, state=None):
    state = state or {'n': 0}
    memory = memory or GoalSearchMemory()
    width = len(option_feature_names(16)); coefficients = np.zeros((width, 9))
    coefficients[option_feature_names(16).index('kind.unlock_access'), 2] = 1
    model = LivingDexOptionValueModel(coefficients, np.zeros(9), np.zeros(width),
                                     np.ones(width), 'a'*64, 10, 0, .25, 4,
                                     feature_version=16)
    def snapshot():
        f = endpoint(1 + state['n'] % 2)
        f.update(actions=state['n'], completed_actions=state['n'], frames=state['n']*4,
                 battle_state=0, buttons_released=True, input_ready=True)
        return AutonomousSnapshot(str(state['n']).encode(), f, True)
    def observe(ordinal):
        def execute():
            state['n'] += 1
            return GoalExecutionReport(1, 4, {})
        move = replace(_binding(GoalKind.ADVANCE_STORY, binding_ref='move', calls=[]),
                       execute=execute, story_objective_ref='private-objective',
                       story_approach_only=True, story_unit=OptionStoryUnit('movement', True),
                       maximum_cash_debit=0)
        acquire = _binding(GoalKind.ACQUIRE_SPECIES, binding_ref='acquire', calls=[])
        return build_red_live_option_set(situation=_situation(resources=.1, safety=0),
                 binding_set=GoalBindingSet((move.opportunity, acquire.opportunity), (move, acquire)),
                 supplements=(),
                 model_feature_version=16, ordering_seed_sha256='b'*64,
                 economy_snapshot=EconomySnapshot(100, ()), target_cash=0,
                 readiness=PlayerReadiness(tuple(2/3 if n == 'current.hp_fraction' else 0
                                                 for n in READINESS_NAMES[1:]),
                                           history_observed=False))
    result = run_autonomous_options(model=model, output=tmp_path, snapshot=snapshot,
                observe=observe, seed=1, maximum_decisions=chunk_size, maximum_seconds=30,
                continuous_player=True, greedy_selection=True,
                provenance={'source': {'partition': 'development'}},
                initial_search_memory=memory, movement_revisit_saturation=enabled)
    return result, memory, state


@pytest.mark.parametrize('enabled', [False, True])
def test_paid_loop_keeps_real_model_choices_and_stops_only_with_enabled_guard(tmp_path, enabled):
    result, memory, state = looping_player(tmp_path/'episode', enabled=enabled, chunk_size=12)
    assert result['stop_reason'] == ('repeated_movement_without_progress' if enabled else 'decision_budget')
    assert result['executed_decisions'] == (4 if enabled else 12)
    assert result['model_decisions'] == result['executed_decisions']
    assert len(list((tmp_path/'episode').glob('step-*/outcome.json'))) == result['executed_decisions']
    if enabled:
        receipt = json.loads((tmp_path/'episode/step-003/movement-memory-after.json').read_text())
        assert receipt['recurrence']['stop_required'] and receipt['state_sha256']


def test_two_choice_chunk_renewal_does_not_reset_the_paid_loop_guard(tmp_path):
    first, memory, state = looping_player(tmp_path/'first', enabled=True, chunk_size=2)
    assert first['stop_reason'] == 'decision_budget'
    restored = GoalSearchMemory.from_private_dict(memory.private_dict())
    second, _, state = looping_player(tmp_path/'second', enabled=True, chunk_size=2,
                                     memory=restored, state=state)
    assert second['stop_reason'] == 'repeated_movement_without_progress'
    assert state['n'] == 4
