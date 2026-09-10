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
        'b'*64, 'e'*40, 'f'*64, 'a'*64, 'c'*64, ()) for i in range(17)]
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
        assert kwargs == {'allow_no_choice': True, 'include_menu': False}
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


def test_empty_native_inventory_closes_after_retained_fit_without_new_attempt(
    tmp_path, monkeypatch,
):
    args, records, _, played, fits, files = harness(tmp_path, monkeypatch, stop_after_first=True)
    args.automatic_goals = True

    def preflight(_ready):
        if played:
            raise cycle.RedNoAvailableGoalError("no available goal")
        return {"status": "ready", "available_goal_kinds": ["acquire_species"]}

    monkeypatch.setattr(cycle.source.base, "_action_free_preflight", preflight)
    result = cycle._run(args)
    assert result["stop_reason"] == "no_executable_native_goal"
    assert len(played) == len(fits) == len(result["steps"]) == 1
    assert result["steps"][0]["fit"]["model"] == records[1].public_dict()
    assert files[args.out] == result


def test_unrelated_preflight_errors_still_abort_without_reclassification(tmp_path, monkeypatch):
    from pokemon_red_completion.goal_manager import GoalManagerError
    args, _, _, played, fits, files = harness(tmp_path, monkeypatch)
    args.automatic_goals = True

    def preflight(_ready):
        raise GoalManagerError("malformed opportunity")

    monkeypatch.setattr(cycle.source.base, "_action_free_preflight", preflight)
    with pytest.raises(GoalManagerError, match="malformed opportunity"):
        cycle._run(args)
    assert not played and not fits and args.out not in files


def test_empty_old_source_does_not_hide_new_executable_regional_choices(tmp_path, monkeypatch):
    args, _, _, played, fits, _ = harness(tmp_path, monkeypatch)
    args.automatic_goals = True

    def preflight(_ready):
        raise cycle.RedNoAvailableGoalError("old source exhausted")

    monkeypatch.setattr(cycle.source.base, "_action_free_preflight", preflight)
    result = cycle._run(args)
    assert len(played) == len(fits) == 2
    assert all(row["selection_scope"] == "regional_destination" for row in result["steps"])
    assert result["stop_reason"] == "step_limit"


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


@pytest.mark.parametrize("fly", [False, True])
def test_owned_evolution_transition_precedes_choice_and_persists_in_actual_ancestry(
    tmp_path, monkeypatch, fly,
):
    import inspect_red_owned_evolution as owned

    args, _, _, played, fits, _ = harness(tmp_path, monkeypatch)
    args.automatic_goals = args.owned_evolution_objectives = True
    args.owned_evolution_fly_transport = fly
    original_prepare = cycle.source.base._prepare

    def prepare(actual):
        result = original_prepare(actual)
        result.registration_policy = object()
        return result

    monkeypatch.setattr(cycle.source.base, "_prepare", prepare)
    monkeypatch.setattr(cycle, "fit_incremental_registered_results",
                        cycle.fit_incremental_regional_result)
    monkeypatch.setattr(cycle.goal, "_run", cycle.source._run)
    monkeypatch.setattr(cycle.source.base, "_action_free_preflight", lambda ready: {
        "status": "ready", "available_goal_kinds": ["acquire_species", "evolve_species"],
    })
    transitions = iter(["evolution:48:49:31", "evolution:17:18:36"])
    def inspect(ready, **kwargs):
        assert kwargs == ({"fly_transport": True} if fly else {})
        return {"selected_transition": next(transitions), "controller_actions": 0}
    monkeypatch.setattr(owned, "inspect_owned_evolution", inspect)
    result = cycle._run(args)
    assert len(played) == len(fits) == 2
    transport = ["evolution-fly", "indoor-fly-departure"] if fly else []
    assert played[0]["regional_transitions"] == [
        "wild:Route24:grass", "evolution:48:49:31", *transport,
    ]
    assert played[1]["regional_transitions"] == [
        "wild:Route24:grass", "evolution:48:49:31", *transport,
        "warp-safe:wild:Route5:grass", "discovery:wild:Route5:grass", "evolution:17:18:36",
        *transport,
    ]
    assert played[1]["continue_from_checkpoint"][-1] == ["cycle-fixture-01-causal", "1" * 64]
    assert result["steps"][0]["owned_evolution_inventory"]["selected_transition"] == (
        "evolution:48:49:31"
    )
    assert all(row["selection_scope"] == "native_goal" for row in result["steps"])
    assert all(row["continuation_source_rule"] == "warp_safe_v1" for row in result["steps"])
    assert args.regional_transitions == ["wild:Route24:grass"]


@pytest.mark.parametrize("value", [True, 1, None, "yes"])
def test_owned_fly_requires_explicit_boolean_and_owned_objectives(tmp_path, monkeypatch, value):
    args, _, _, played, fits, _ = harness(tmp_path, monkeypatch)
    args.owned_evolution_fly_transport = value
    with pytest.raises(ValueError, match="owned evolution Fly"):
        cycle._run(args)
    assert played == fits == []


def test_completed_step_survives_later_preparation_failure(tmp_path, monkeypatch):
    args, _, _, played, fits, files = harness(tmp_path, monkeypatch)
    original = cycle.source.base._prepare
    def prepare(actual):
        if actual.pair_id.endswith("-02"):
            raise ValueError("later checkpoint rejected")
        return original(actual)
    monkeypatch.setattr(cycle.source.base,"_prepare",prepare)
    with pytest.raises(ValueError,match="later checkpoint rejected"):
        cycle._run(args)
    assert len(played) == len(fits) == 1
    step = files[tmp_path / "cycle-01-step.json"]
    assert step["ordinal"] == 1
    assert step["outcome"]["episode_id"] == "cycle-fixture-01-causal"
    assert "model" in step["fit"]
    assert args.out not in files


@pytest.mark.parametrize("value", [True, 1, "yes"])
def test_owned_options_never_activate_for_legacy_or_nonautomatic_cycle(
    tmp_path, monkeypatch, value,
):
    args, _, _, played, fits, _ = harness(tmp_path, monkeypatch)
    args.owned_evolution_objectives = value
    with pytest.raises(ValueError, match="automatic registered"):
        cycle._run(args)
    assert not played and not fits


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


@pytest.mark.parametrize('enabled', [False, True])
def test_status_replanning_is_opt_in_and_uses_actual_saved_model(tmp_path, monkeypatch, enabled):
    args, records, _, played, fits, _ = harness(tmp_path, monkeypatch, failed=True)
    args.automatic_goals = True
    args.continue_after_status_recovery = enabled
    monkeypatch.setattr(cycle.source.base, '_action_free_preflight', lambda _: {
        'status': 'ready', 'available_goal_kinds': ['acquire_species'],
    })
    original = cycle.source._run

    def degraded(actual):
        result = original(actual)
        result['parent_episode']['steps'][0].update(
            failure_reason='recovery_required', semantic_state_changed=True,
            collection_before={'living_species': 21, 'undeclared_specimen_losses': 0},
            collection_after={'living_species': 21, 'undeclared_specimen_losses': 0},
        )
        return result

    monkeypatch.setattr(cycle.source, '_run', degraded)
    result = cycle._run(args)
    assert len(played) == len(fits) == (2 if enabled else 1)
    assert result['automatic_retry'] is False
    if enabled:
        assert played[1]['expected_living_dex_model_sha256'] == records[1].model.model_sha256
        assert played[1]['continue_from_checkpoint'][-1] == ['cycle-fixture-01-causal', '1'*64]
        assert played[1]['pair_id'] != played[0]['pair_id']
        assert result['stop_reason'] == 'step_limit'
    else:
        assert result['stop_reason'] == 'failed_step_retained_and_fitted'


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
    ('learning_steps', True), ('learning_steps', 0), ('learning_steps', 17),
    ('train_player', False), ('decision_limit', 2), ('completion_dose', False),
])
def test_scope_and_dose_rejected_before_any_play(tmp_path, monkeypatch, field, value):
    args, _, _, played, fits, _ = harness(tmp_path, monkeypatch)
    setattr(args, field, value)
    with pytest.raises(ValueError):
        cycle._run(args)
    assert played == fits == []


def test_extended_cycle_retains_each_actual_model_and_checkpoint(tmp_path, monkeypatch):
    args, records, _, played, fits, _ = harness(tmp_path, monkeypatch)
    args.learning_steps = 16
    args.maximum_cycle_seconds = 3600
    result = cycle._run(args)
    assert len(played) == len(fits) == 16
    assert fits[-1]['prior'] is records[15]
    assert len(played[-1]['continue_from_checkpoint']) == 16
    assert len({row['pair_id'] for row in played}) == 16
    assert result['maximum_controller_actions'] == 480_000
    assert result['maximum_emulator_frames'] == 48_000_000
    assert result['maximum_cycle_seconds'] == 3600


@pytest.mark.parametrize('seconds', [None, True, 0, -1, 7201, 1.5])
def test_extended_cycle_requires_valid_declared_time_bound(tmp_path, monkeypatch, seconds):
    args, _, prepared, played, _, _ = harness(tmp_path, monkeypatch)
    args.learning_steps = 5
    args.maximum_cycle_seconds = seconds
    with pytest.raises(ValueError, match='time bound'):
        cycle._run(args)
    assert prepared == played == []


@pytest.mark.parametrize('expire_during', ['inventory', 'inspection', 'fit'])
def test_deadline_stops_before_next_input_but_preserves_inflight_fit(
    tmp_path, monkeypatch, expire_during,
):
    args, _, _, played, fits, files = harness(tmp_path, monkeypatch)
    args.maximum_cycle_seconds = 60
    clock = [100.0]
    monkeypatch.setattr(cycle.time, 'monotonic', lambda: clock[0])
    owner, method = {
        'inventory': (cycle, 'load_prior_player_inventory'),
        'inspection': (cycle.source, 'inspect_sources'),
        'fit': (cycle, 'fit_incremental_regional_result'),
    }[expire_during]
    original = getattr(owner, method)
    def expire(*args, **kwargs):
        result = original(*args, **kwargs)
        clock[0] = 160.0
        return result
    monkeypatch.setattr(owner, method, expire)
    result = cycle._run(args)
    assert len(played) == len(fits) == (1 if expire_during == 'fit' else 0)
    assert result['stop_reason'] == 'time_limit_before_next_step'
    assert result['elapsed_seconds'] == 60
    assert args.out in files
    if expire_during == 'fit':
        assert args.out.with_name('cycle-01-fit.json') in files


def test_automatic_cycle_switches_native_goal_to_destination_and_carries_fit(tmp_path, monkeypatch):
    args, records, _, played, fits, _ = harness(tmp_path, monkeypatch)
    args.automatic_goals = True
    monkeypatch.setattr(cycle.source.base, '_action_free_preflight', lambda _: {
        'status': 'ready', 'available_goal_kinds':
        ['restore_party', 'acquire_species'] if not played else ['acquire_species'],
    })
    run = cycle.source._run
    def native(actual):
        result = run(actual)
        result['proposed_source'] = result.pop('selected_source')
        return result
    monkeypatch.setattr(cycle.goal, '_run', native)
    def native_fit(store, *, results, **kw):
        assert len(results) == 1 and 'proposed_source' in results[0]
        return cycle.fit_incremental_regional_result(store, result=results[0], **kw)
    monkeypatch.setattr(cycle, 'fit_incremental_goal_results', native_fit)
    result = cycle._run(args)
    assert [step['selection_scope'] for step in result['steps']] == [
        'native_goal', 'regional_destination',
    ]
    assert len(played) == len(fits) == 2
    assert played[1]['expected_living_dex_model_sha256'] == records[1].model.model_sha256
    assert played[1]['regional_transitions'][-2:] == [
        'wild:Route5:grass', 'discovery:wild:Route5:grass',
    ]


def test_automatic_support_advances_save_without_inventing_a_fit(tmp_path, monkeypatch):
    args, records, _, played, _, _ = harness(tmp_path, monkeypatch)
    args.automatic_goals = True
    monkeypatch.setattr(cycle.source.base, '_action_free_preflight', lambda _: {
        'status': 'ready_for_forced_bridge', 'available_goal_kinds': ['resupply'],
    })
    run = cycle.source._run
    def native(actual):
        result = run(actual)
        result['proposed_source'] = None
        del result['selected_source']
        return result
    monkeypatch.setattr(cycle.goal, '_run', native)
    batches = []
    def fit(_store, *, results, **kw):
        batches.append(results)
        if len(results) == 1:
            return {'status': 'support_retained_without_fit', 'new_settled_examples': 0}
        assert kw['prior'] is records[0]
        return {'model': records[1].public_dict()}
    monkeypatch.setattr(cycle, 'fit_incremental_goal_results', fit)
    result = cycle._run(args)
    assert [len(batch) for batch in batches] == [1, 2]
    assert played[1]['expected_living_dex_model_sha256'] == records[0].model.model_sha256
    assert played[1]['continue_from_checkpoint'][-1] == ['cycle-fixture-01-causal', '1'*64]
    assert played[1]['regional_transitions'] == args.regional_transitions
    assert result['pending_support_episode_ids'] == []


@pytest.mark.parametrize('kinds,status,candidates,reason', [
    (['advance_story', 'acquire_species'], 'ready', (1, 2), 'story_outside_collection_scope'),
    ([], 'not_ready', (), 'no_executable_collection_or_support_goal'),
])
def test_automatic_collection_cannot_launch_story_or_empty_boundary(
    tmp_path, monkeypatch, kinds, status, candidates, reason,
):
    args, _, _, played, fits, _ = harness(tmp_path, monkeypatch)
    args.automatic_goals = True
    monkeypatch.setattr(cycle.source.base, '_action_free_preflight', lambda _: {
        'status': status, 'available_goal_kinds': kinds,
    })
    monkeypatch.setattr(cycle.source, 'inspect_sources',
                        lambda *_a, **_kw: (None, candidates, None))
    assert cycle._run(args)['stop_reason'] == reason
    assert played == fits == []


def test_automatic_flag_rejects_non_boolean_before_prepare(tmp_path, monkeypatch):
    args, _, prepared, played, _, _ = harness(tmp_path, monkeypatch)
    args.automatic_goals = 1
    with pytest.raises(ValueError, match='automatic goal'):
        cycle._run(args)
    assert prepared == played == []
