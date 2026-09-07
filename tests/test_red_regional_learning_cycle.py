import argparse
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
import run_red_regional_learning_cycle as cycle
from test_goal_resource_quote import _supply_model

from pokemon_red_completion.red_player_model import RedPlayerModelRecord


def harness(tmp_path, monkeypatch, *, failed=False, fit_fails=False, stop_after_first=False):
    base = _supply_model()
    records = [RedPlayerModelRecord(replace(base, settled_examples=base.settled_examples+i),
        'b'*64, 'e'*40, 'f'*64, 'a'*64, 'c'*64, ()) for i in range(3)]
    by_sha = {r.model.model_sha256: r for r in records}
    args = argparse.Namespace(learning_steps=2, train_player=True, decision_limit=1,
        completion_dose=True, pair_id='cycle-fixture', training_seed=10,
        out=tmp_path/'cycle.json', behavior_model_record=[], private_artifact_root=tmp_path,
        expected_living_dex_model_sha256=records[0].model.model_sha256,
        living_dex_model_record=tmp_path/'initial.json',
        continue_from_checkpoint=[['old-episode', 'a'*64]],
        regional_transitions=['wild:Route24:grass'])
    prepared, played, fits, files = [], [], [], {}
    def prepare(actual):
        prepared.append(deepcopy(vars(actual)))
        return SimpleNamespace(continuation=object(),
            causal_record=by_sha[actual.expected_living_dex_model_sha256],
            model_sha256=actual.expected_living_dex_model_sha256,
            output_path=actual.out, source_commit='e'*40, source_bundle_sha256='f'*64,
            private_root=object())
    monkeypatch.setattr(cycle.source.base, '_prepare', prepare)
    monkeypatch.setattr(cycle, 'load_prior_player_inventory', lambda *_: ((), ()))
    def inspect(_ready, **kwargs):
        assert kwargs == {'allow_no_choice': True}
        return object(), (() if stop_after_first and played else (object(), object())), None
    monkeypatch.setattr(cycle.source, 'inspect_sources', inspect)
    def run(actual):
        if any(row['pair_id'] == actual.pair_id for row in played):
            raise ValueError('episode already consumed')
        played.append(deepcopy(vars(actual)))
        return {'episode_id': f'{actual.pair_id}-causal',
            'checkpoint_sha256': str(len(played))*64, 'selected_source': 'wild:Route5:grass',
            'parent_episode': {'steps': [{'status': 'failed' if failed else 'succeeded'}]}}
    monkeypatch.setattr(cycle.source, '_run', run)
    def fit(_store, **kwargs):
        fits.append(kwargs)
        if fit_fails:
            raise ValueError('fit admission failed')
        return {'model': records[len(fits)].public_dict()}
    monkeypatch.setattr(cycle, 'fit_incremental_regional_result', fit)
    def write(path, data):
        if path in files:
            raise ValueError('output already exists')
        files[path] = deepcopy(data)
    monkeypatch.setattr(cycle.source.base, '_write_exclusive', write)
    return args, records, prepared, played, fits, files


def test_second_choice_uses_first_real_endpoint_and_updated_model(tmp_path, monkeypatch):
    args, records, _, played, fits, files = harness(tmp_path, monkeypatch)
    result = cycle._run(args)
    assert len(played) == len(fits) == len(result['steps']) == 2
    assert played[1]['expected_living_dex_model_sha256'] == records[1].model.model_sha256
    assert fits[1]['prior'] is records[1]
    assert played[1]['continue_from_checkpoint'] == [
        ['old-episode', 'a'*64], ['cycle-fixture-01-causal', '1'*64],
    ]
    assert played[1]['regional_transitions'] == [
        'wild:Route24:grass', 'wild:Route5:grass', 'discovery:wild:Route5:grass',
    ]
    assert [row['training_seed'] for row in played] == [10, 11]
    assert args.continue_from_checkpoint == [['old-episode', 'a'*64]]
    assert result['maximum_controller_actions'] == 60_000
    assert result['maximum_emulator_frames'] == 6_000_000
    assert result['stop_reason'] == 'step_limit' and not result['automatic_retry']
    assert args.out in files
    with pytest.raises(ValueError, match='consumed'):
        cycle._run(args)
    assert len(played) == 2


def test_failed_choice_is_fitted_once_then_stops(tmp_path, monkeypatch):
    args, _, _, played, fits, _ = harness(tmp_path, monkeypatch, failed=True)
    result = cycle._run(args)
    assert len(played) == len(fits) == 1
    assert result['stop_reason'] == 'failed_step_retained_and_fitted'


@pytest.mark.parametrize("resource_state_changed", [False, True])
def test_opt_in_safe_search_failure_replans_from_actual_model_and_save(
    tmp_path, monkeypatch, resource_state_changed,
):
    args, records, _, played, fits, _ = harness(tmp_path, monkeypatch, failed=True)
    original = cycle.source._run
    def exhausted(actual):
        result = original(actual)
        result['parent_episode']['steps'][0].update(
            failure_reason='search_exhausted', semantic_state_changed=resource_state_changed,
            collection_before={'living_species': 21, 'undeclared_specimen_losses': 0},
            collection_after={'living_species': 21, 'undeclared_specimen_losses': 0},
        )
        return result
    monkeypatch.setattr(cycle.source, '_run', exhausted)
    args.continue_after_search_exhaustion = True
    result = cycle._run(args)
    assert len(played) == len(fits) == 2
    assert played[1]['expected_living_dex_model_sha256'] == records[1].model.model_sha256
    assert played[1]['continue_from_checkpoint'][-1] == ['cycle-fixture-01-causal', '1'*64]
    assert result['stop_reason'] == 'step_limit'
    assert result['automatic_retry'] is False


@pytest.mark.parametrize('change', [
    {'failure_reason': 'world_state_diverged'}, {'semantic_state_changed': None},
    {'semantic_state_changed': 1}, {'failure_reason': 'capture_items_exhausted'},
    {'collection_after': {'living_species': 20, 'undeclared_specimen_losses': 1}},
    {'collection_before': None},
    {'collection_before': {'undeclared_specimen_losses': True},
     'collection_after': {'undeclared_specimen_losses': True}},
])
def test_other_failed_states_never_qualify_for_automatic_replanning(change):
    step = {'status': 'failed', 'failure_reason': 'search_exhausted',
        'semantic_state_changed': False,
        'collection_before': {'living_species': 21, 'undeclared_specimen_losses': 0},
        'collection_after': {'living_species': 21, 'undeclared_specimen_losses': 0}}
    assert cycle._safe_exhausted_search({'steps': [step]})
    step.update(change)
    assert not cycle._safe_exhausted_search({'steps': [step]})


def test_opt_in_does_not_continue_other_failure(tmp_path, monkeypatch):
    args, _, _, played, fits, _ = harness(tmp_path, monkeypatch, failed=True)
    args.continue_after_search_exhaustion = True
    assert cycle._run(args)['stop_reason'] == 'failed_step_retained_and_fitted'
    assert len(played) == len(fits) == 1


def test_fit_error_preserves_source_receipt_and_never_continues(tmp_path, monkeypatch):
    args, _, _, played, fits, files = harness(tmp_path, monkeypatch, fit_fails=True)
    with pytest.raises(ValueError, match='fit admission'):
        cycle._run(args)
    assert len(played) == len(fits) == 1
    assert args.out.with_name('cycle-01-source.json') in files
    assert args.out not in files


def test_no_actual_next_alternatives_stops_without_inventing_a_choice(tmp_path, monkeypatch):
    args, _, _, played, fits, _ = harness(tmp_path, monkeypatch, stop_after_first=True)
    result = cycle._run(args)
    assert len(played) == len(fits) == 1
    assert result['stop_reason'] == 'no_genuine_source_choice'


@pytest.mark.parametrize('field,value', [
    ('learning_steps', True), ('learning_steps', 0), ('learning_steps', 5),
    ('train_player', False), ('decision_limit', 2), ('completion_dose', False),
])
def test_scope_and_dose_rejected_before_any_play(tmp_path, monkeypatch, field, value):
    args, _, _, played, fits, _ = harness(tmp_path, monkeypatch)
    setattr(args, field, value)
    with pytest.raises(ValueError):
        cycle._run(args)
    assert played == fits == []
