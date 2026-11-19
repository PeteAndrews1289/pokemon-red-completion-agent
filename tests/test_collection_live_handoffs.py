from dataclasses import replace
from hashlib import sha256
import json
from types import SimpleNamespace as N

import pytest
import run_configured_red_player as driver
from pokemon_red_completion import red_player_configuration as configuration
from pokemon_red_completion.goal_manager import GoalAvailability, GoalKind, GoalOpportunity, GoalUnavailableReason
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from test_red_live_option_menu import _binding
from test_red_player_configuration import config
from test_red_player_live_loan_handoff import fixture


@pytest.mark.parametrize('fault', [None, 'stale', 'wrong_original', 'wrong_guest', 'changed_xp'])
def test_live_bird_loan_requires_witnessed_individual_and_guest(monkeypatch, fault):
    runtime, previous, context, old, boxed = fixture(monkeypatch)
    context['state_sha256'] = sha256(b'live').hexdigest()
    context['lesson'] = {'party': [{'specimen_ref': r} for r in old.reader.preparation_specimen_refs()]}
    observed = old.loanable_refs
    if fault == 'stale':
        context['state_sha256'] = '0' * 64
    elif fault == 'wrong_original':
        observed = frozenset({old.refs[0]})
    elif fault == 'wrong_guest':
        previous.emulator = N(_backend=object(), frame_count=100, save_state_bytes=lambda: b'live')
    elif fault == 'changed_xp':
        boxed.experience -= 1
    args = (runtime, previous, replace(config(), loanable_specimen_refs=('other-original',)), context)
    if fault is None:
        renewed = configuration._same_guest_pending_loan_guard(*args, observed_bird_refs=observed)
        assert renewed.before is old.before and renewed.loanable_refs == observed
        assert runtime.emulator.frame_count == 100
    else:
        with pytest.raises(ValueError):
            configuration._same_guest_pending_loan_guard(*args, observed_bird_refs=observed)


@pytest.mark.parametrize('fault', [None, 'uncertain_terminal', 'different_error', 'previous_error',
                                    'buttons', 'caught', 'stale_state', 'foreign_route', 'extra_choice',
                                    'wrong_successor', 'ticks'])
def test_funding_faint_requires_exact_unchanged_singleton(monkeypatch, tmp_path, fault):
    digest = sha256(b'held').hexdigest()
    error = "Gen I route cannot dismiss 'scripted_dialogue'"
    last = dict(selected_kind='resupply', error_type='RouteExecutionError', error=error,
                error_chain=[dict(error_type='RouteExecutionError', error=error, reason_code='world_state_diverged')],
                failure_phase='execution', safe_terminal=True, terminal_state_sha256=digest, ordinal=0,
                before_state_sha256='b' * 64, before={'owned_species': ['a']}, after={'owned_species': ['a']})
    outcomes = [last]
    emulator = N(frame_count=10, pressed_buttons=set(), save_state_bytes=lambda: b'held')
    runtime = N(emulator=emulator, reader=N(read=lambda: N(battle_state=0, party_hp=(0, 20))))
    result = dict(episode=dict(outcomes=outcomes, stop_reason='execution_failed'), released=True,
                  field_ready=False, paired_context_authenticated=True, state_sha256=digest)
    row = dict(selected_kind='resupply', state_sha256=last['before_state_sha256'], selected_binding_ref='red-trainer-funding:test')
    if fault == 'uncertain_terminal':
        last['safe_terminal'] = False
    elif fault == 'different_error':
        last['error_chain'][0]['reason_code'] = 'different'
    elif fault == 'previous_error':
        outcomes.insert(0, {'error_type': 'earlier-error'})
    elif fault == 'buttons':
        emulator.pressed_buttons.add('A')
    elif fault == 'caught':
        last['after']['owned_species'].append('b')
    elif fault == 'stale_state':
        result['state_sha256'] = 'c' * 64
    elif fault == 'foreign_route':
        row['selected_binding_ref'] = 'unrelated'
    step = tmp_path/'native/episode/step-000'
    step.mkdir(parents=True)
    (step/'execution-started.json').write_text(json.dumps(row))
    monkeypatch.setattr(driver, '_field_ready', lambda runtime: False)
    binding = _binding(GoalKind.RECOVER_CONTROL, binding_ref='pokemon.red:retained-motion:'+digest, calls=[])
    alternative = _binding(GoalKind.ADVANCE_STORY, binding_ref='other', calls=[])
    def inventory(*args, **kwargs):
        if fault == 'ticks':
            emulator.frame_count += 1
        rows = (alternative,) if fault == 'wrong_successor' else (binding, alternative) if fault == 'extra_choice' else (binding,)
        unavailable = GoalOpportunity('blocked', GoalKind.ADVANCE_STORY, GoalAvailability.UNAVAILABLE,
                                      unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED)
        return GoalBindingSet(tuple(b.opportunity for b in rows) + (unavailable,), rows)
    monkeypatch.setattr(configuration, '_retained_field_faint_inventory', inventory)
    if fault == 'ticks':
        with pytest.raises(ValueError, match='changed the held state'):
            driver.qualified_collection_field_handoff(result, runtime=runtime, menu=None, parent=tmp_path)
        return
    handoff = driver.qualified_collection_field_handoff(result, runtime=runtime, menu=None, parent=tmp_path)
    if fault is None:
        assert handoff['retained_funding_faint'] and handoff['failed_transport_preserved']
        assert handoff['inputs'] == handoff['frames'] == handoff['model_queries'] == 0
    else:
        assert handoff is None
