from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_player_training_fit import _fit

import pokemon_red_completion.red_player_incremental_fit as incremental
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_player_model import load_player_goal_model_record_bytes


def native(tmp_path, monkeypatch):
    store, _, _, request, fitted = _fit(tmp_path, monkeypatch)
    sha = fitted['model']['model_sha256']
    record = store.find_sealed_record(f'rp-model-{sha}', expected_kind='red_player_model')
    prior = load_player_goal_model_record_bytes(record.read_bytes(), expected_model_sha256=sha)
    return store, prior, request


def test_prior_inventory_reconstructs_actual_manifest_plan_and_behavior(tmp_path, monkeypatch):
    store, prior, request = native(tmp_path, monkeypatch)
    episodes, regional = incremental.load_prior_player_inventory(
        store, prior, lambda sha: request.behavior_record,
    )
    assert episodes == (request,) and regional == ()
    with pytest.raises(ValueError, match='behavior model differs'):
        incremental.load_prior_player_inventory(store, prior, lambda sha: prior)


@pytest.mark.parametrize('damage', ['manifest', 'plan', 'duplicate', 'hash'])
def test_changed_prior_inventory_is_not_silently_rebuilt(tmp_path, monkeypatch, damage):
    store, prior, request = native(tmp_path, monkeypatch)
    document = deepcopy(store.find_sealed_record(
        f'rp-corpus-{prior.corpus_sha256}', expected_kind='red_player_training_corpus',
    ).read())
    if damage == 'manifest':
        document['episodes'][0]['manifest_sha256'] = '0'*64
    elif damage == 'plan':
        document['episodes'][0]['plan_sha256'] = '0'*64
    elif damage == 'duplicate':
        document['episodes'].append(dict(document['episodes'][0]))
    else:
        document['independent_evaluation'] = True
    sha = canonical_sha256(document)
    store.publish_sealed_record(f'rp-corpus-{sha}', kind='red_player_training_corpus',
                                record=document)
    changed = replace(prior, corpus_sha256=sha)
    with pytest.raises(ValueError):
        incremental.load_prior_player_inventory(store, changed, lambda _: request.behavior_record)


def result_for(prior, episode_id='new-source'):
    return {'schema': 'pokemon.red.regional-acquisition-result.v1',
        'model_sha256': prior.model.model_sha256, 'episode_id': episode_id,
        'eligible_examples': 1, 'parent_learning_examples': 0, 'independent_evaluation': False,
        'manifest_sha256': 'a'*64, 'choice_record_sha256': 'b'*64,
        'outcome_record_sha256': 'c'*64}


@pytest.mark.parametrize('field,value', [
    ('eligible_examples', 0), ('eligible_examples', True), ('parent_learning_examples', 1),
    ('model_sha256', '0'*64), ('independent_evaluation', True),
])
def test_only_new_actual_single_choice_may_enter_fit(tmp_path, monkeypatch, field, value):
    store, prior, request = native(tmp_path, monkeypatch)
    result = result_for(prior)
    result[field] = value
    monkeypatch.setattr(incremental, 'fit_red_player_update',
                        lambda *_a, **_k: pytest.fail('must reject before fitting'))
    with pytest.raises(ValueError, match='scope differs'):
        incremental.fit_incremental_regional_result(store, prior=prior, result=result,
            resolve=lambda _: request.behavior_record,
            source_commit='e'*40, source_bundle_sha256='f'*64)


def test_consumed_outcome_cannot_be_added_twice(tmp_path, monkeypatch):
    store, prior, request = native(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='already included'):
        incremental.fit_incremental_regional_result(store, prior=prior,
            result=result_for(prior, request.episode_id), resolve=lambda _: request.behavior_record,
            source_commit='e'*40, source_bundle_sha256='f'*64)


def test_extension_passes_all_retained_inputs_and_one_new_choice(tmp_path, monkeypatch):
    store, prior, request = native(tmp_path, monkeypatch)
    result = result_for(prior)
    reader = SimpleNamespace(manifest_sha256='a'*64,
        read_header=lambda: {'metadata': {'player_training_plan': dict(request.plan.document)}})
    # Existing fitter owns actual admission; this probe isolates inventory assembly.
    monkeypatch.setattr(incremental, 'load_prior_player_inventory',
                        lambda *_: ((request,), ()))
    fake_store = SimpleNamespace(open_episode=lambda _: reader)
    captured = {}
    def fit(_store, **kwargs):
        captured.update(kwargs)
        return {'new_settled_examples': 1, 'prior_rows_retained': True,
                'model': {'settled_examples': prior.model.settled_examples+1}}
    monkeypatch.setattr(incremental, 'fit_red_player_update', fit)
    incremental.fit_incremental_regional_result(fake_store, prior=prior, result=result,
        resolve=lambda _: request.behavior_record,
        source_commit='e'*40, source_bundle_sha256='f'*64)
    assert captured['episodes'][0] is request
    assert captured['episodes'][1].episode_id == 'new-source'
    assert len(captured['episodes']) == 2 and len(captured['regional_choices']) == 1
    assert captured['regional_choices'][0].behavior_record is prior


def goal_result(prior, episode_id='new-goal', count=1):
    return {
        'schema': 'pokemon.red.regional-goal-step-result.v1',
        'model_sha256': prior.model.model_sha256, 'episode_id': episode_id,
        'eligible_examples': count, 'eligible_source_examples': 0,
        'source_proposal_fitted': False, 'parent_overridden': False,
        'model_fitted': False, 'independent_evaluation': False, 'manifest_sha256': 'a'*64,
    }


def goal_inventory(tmp_path, monkeypatch):
    _, prior, request = native(tmp_path, monkeypatch)
    reader = SimpleNamespace(manifest_sha256='a'*64,
        read_header=lambda: {'metadata': {'player_training_plan': dict(request.plan.document)}})
    monkeypatch.setattr(incremental, 'load_prior_player_inventory',
                        lambda *_: ((request,), ()))
    return SimpleNamespace(open_episode=lambda _: reader), prior, request


@pytest.mark.parametrize('field,value', [
    ('eligible_examples', True), ('eligible_examples', 2), ('eligible_source_examples', 1),
    ('source_proposal_fitted', True), ('parent_overridden', True), ('model_fitted', True),
    ('independent_evaluation', True), ('model_sha256', '0'*64),
])
def test_native_result_scope_rejects_invented_authority(tmp_path, monkeypatch, field, value):
    store, prior, request = goal_inventory(tmp_path, monkeypatch)
    result = goal_result(prior)
    result[field] = value
    monkeypatch.setattr(incremental, 'fit_red_player_update',
                        lambda *_a, **_k: pytest.fail('invalid scope must not fit'))
    with pytest.raises(ValueError, match='scope differs'):
        incremental.fit_incremental_goal_results(store, prior=prior, results=(result,),
            resolve=lambda _: request.behavior_record,
            source_commit='e'*40, source_bundle_sha256='f'*64)


def test_native_fit_preserves_support_and_native_authority_without_source_credit(
    tmp_path, monkeypatch,
):
    store, prior, request = goal_inventory(tmp_path, monkeypatch)
    results = (goal_result(prior, 'support', 0), goal_result(prior, 'played', 1))
    admitted = []
    def load(_store, **kwargs):
        assert kwargs['behavior_model'] is prior.model
        admitted.append(kwargs['episode_id'])
        return SimpleNamespace(examples=() if kwargs['episode_id'] == 'support' else (object(),))
    monkeypatch.setattr(incremental, 'load_red_player_training_episode', load)
    def fit(_store, **kwargs):
        assert [e.episode_id for e in kwargs['episodes']] == [
            request.episode_id, 'support', 'played',
        ]
        assert kwargs['regional_choices'] == ()
        return {'new_settled_examples': 1, 'prior_rows_retained': True,
                'model': {'settled_examples': prior.model.settled_examples + 1}}
    monkeypatch.setattr(incremental, 'fit_red_player_update', fit)
    result = incremental.fit_incremental_goal_results(store, prior=prior, results=results,
        resolve=lambda _: request.behavior_record,
        source_commit='e'*40, source_bundle_sha256='f'*64)
    assert result['new_settled_examples'] == 1 and admitted == ['support', 'played']


def test_support_alone_is_authenticated_but_not_fitted(tmp_path, monkeypatch):
    store, prior, request = goal_inventory(tmp_path, monkeypatch)
    calls = []
    def load(*_a, **kw):
        calls.append(kw['episode_id'])
        return SimpleNamespace(examples=())
    monkeypatch.setattr(incremental, 'load_red_player_training_episode', load)
    monkeypatch.setattr(incremental, 'fit_red_player_update',
                        lambda *_a, **_k: pytest.fail('support cannot fit'))
    result = incremental.fit_incremental_goal_results(store, prior=prior,
        results=(goal_result(prior, 'support', 0),), resolve=lambda _: request.behavior_record,
        source_commit='e'*40, source_bundle_sha256='f'*64)
    assert calls == ['support'] and result['model_fitted'] is False
    assert result['pending_support_episodes'] == ['support']
    assert result['new_settled_examples'] == 0


@pytest.mark.parametrize('damage', ['count', 'duplicate', 'previous', 'source', 'manifest'])
def test_native_fit_authenticates_counts_and_prevents_duplicate_or_source_credit(
    tmp_path, monkeypatch, damage,
):
    store, prior, request = goal_inventory(tmp_path, monkeypatch)
    result = goal_result(prior)
    if damage == 'previous':
        result['episode_id'] = request.episode_id
    if damage == 'manifest':
        result['manifest_sha256'] = '0'*64
    if damage == 'source':
        store.open_episode = lambda _: SimpleNamespace(manifest_sha256='a'*64,
            read_header=lambda: {'metadata': {'regional_choice_record_sha256': 'b'*64}})
    monkeypatch.setattr(incremental, 'load_red_player_training_episode',
                        lambda *_a, **_k: SimpleNamespace(examples=() if damage == 'count'
                                                           else (object(),)))
    monkeypatch.setattr(incremental, 'fit_red_player_update',
                        lambda *_a, **_k: pytest.fail('invalid evidence cannot fit'))
    with pytest.raises(ValueError):
        incremental.fit_incremental_goal_results(store, prior=prior,
            results=(result, result) if damage == 'duplicate' else (result,),
            resolve=lambda _: request.behavior_record,
            source_commit='e'*40, source_bundle_sha256='f'*64)


@pytest.mark.parametrize('support', [False, True])
def test_native_inventory_uses_real_recorded_episode_admission(tmp_path, monkeypatch, support):
    from test_red_player_training import _episode
    store, plan, model, completed = _episode(tmp_path, return_inputs=True, safety=support)
    prior = SimpleNamespace(model=model)
    monkeypatch.setattr(incremental, 'load_prior_player_inventory', lambda *_: ((), ()))
    calls = []
    def fit(_store, **kwargs):
        calls.append(kwargs)
        assert kwargs['episodes'][0].plan == plan
        assert kwargs['episodes'][0].manifest_sha256 == completed.manifest_sha256
        assert kwargs['regional_choices'] == ()
        return {'new_settled_examples': 1, 'prior_rows_retained': True,
                'model': {'settled_examples': model.settled_examples + 1}}
    monkeypatch.setattr(incremental, 'fit_red_player_update', fit)
    result = goal_result(prior, 'goal-episode-1', 0 if support else 1)
    result['manifest_sha256'] = completed.manifest_sha256
    actual = incremental.fit_incremental_goal_results(store, prior=prior, results=(result,),
        resolve=lambda _: pytest.fail('no earlier inventory in this isolated reader test'),
        source_commit='e'*40, source_bundle_sha256='f'*64)
    assert len(calls) == (0 if support else 1)
    assert actual['new_settled_examples'] == (0 if support else 1)
