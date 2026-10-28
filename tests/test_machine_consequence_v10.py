"""Synthetic recorder contracts; these tests produce no native TRAIN evidence."""
import copy
from dataclasses import replace

import numpy as np
import pytest
from test_challenge_consequence import documents
from test_move_change_v10 import change
from test_native_challenge_consequence import harness, session

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionMenu, option_feature_names, upgrade_option_value_model_for_move_change,
)
from pokemon_red_completion.player_challenge_consequence import (
    ChallengeConsequenceHead, ConsequenceExample, fit_challenge_consequence,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_challenge_consequence import (
    ChallengeConsequenceSpec, project_consequence,
)
from pokemon_red_completion.red_player_economy import snapshot_document
from pokemon_red_completion.resource_economy_observation import EconomySnapshot


def machine_documents(tmp_path, monkeypatch, slot=4):
    plan, _, old_menu = documents(tmp_path, monkeypatch)
    before = plan['before']
    moves = [44, 39, 61, 55]
    pp = [25, 30, 20, 25]
    before['lesson']['party'][0]['moves'] = [list(p) for p in zip(moves, pp, strict=True)]
    before['machine_boundary'] = dict(location=[0, 1, 1], badges=0, events='00',
        party_stats=[[100, 90, 80, 120] for _ in before['lesson']['party']],
        party_pp=[pp, *[[m[1] for m in member['moves']] for member in before['lesson']['party'][1:]]],
        protected_collection_sha256='c' * 64)
    before['economy'] = snapshot_document(EconomySnapshot(1500, (('red-item-213', 1),)))
    facts = change(moves[slot-1], recipient_attack=100, recipient_special_attack=120)
    # Fixture species is internal ID1 (Rhydon), so none of these moves has STAB.
    facts = replace(facts, removed_stab=False)
    lesson = dict(item_id=213, party_slot=1, replace_slot=slot, species_id=1,
        before_moves=moves, move_id=58)
    target = dict(lesson=lesson, move_change=facts.public_dict())
    binding = 'pokemon.red:owned-machine:' + before['state_sha256'] + ':' + canonical_sha256(lesson)
    candidate = replace(old_menu.candidates[0], binding_ref=binding,
        preparation=None, level_workload=None, move_change=facts)
    menu = LivingDexOptionMenu(old_menu.context, (candidate, *old_menu.candidates[1:]))
    spec = ChallengeConsequenceSpec(GoalKind.DEVELOP_TEAM,
        dict(kind='events', map_id=0, events=[1]), machine_lesson=target)
    plan.update(schema='pokemon.red.challenge-consequence-plan.v7', feature_version=10,
        spec=spec.document(), menu=menu.policy_dict(), binding_ref=binding)
    after = copy.deepcopy(before)
    after.update(state_sha256='a' * 64, actions=100, completed_actions=100, frames=6000)
    after['lesson']['party'][0]['moves'][slot-1] = [58, 10]
    after['machine_boundary']['party_pp'][0][slot-1] = 10
    after['economy']['inventory'] = []
    training = dict(ordinal=0, kind='develop_team', binding_ref=binding, before=before,
        after=after, interventions=[], error=None, verified=True, battle=None, cost_verified=True)
    terminal = copy.deepcopy(after)
    terminal.update(state_sha256='b' * 64, actions=120, completed_actions=120, frames=7000, cash=750)
    terminal['economy']['cash'] = 750
    challenge = dict(ordinal=1, kind='advance_story', binding_ref='challenge',
        before=copy.deepcopy(after), after=terminal, interventions=[], error=None,
        verified=False, battle='lost', cost_verified=True)
    return plan, [training, challenge], menu


@pytest.mark.parametrize('won', [False, True])
def test_v10_projects_legal_machine_then_real_challenge_with_complete_marginal_cost(tmp_path, monkeypatch, won):
    plan, phases, menu = machine_documents(tmp_path, monkeypatch)
    if won:
        phases[-1].update(verified=True, battle='won')
        phases[-1]['after']['endpoint']['events'] = [True]
    row = project_consequence(plan, phases)
    assert row.feature_version == 10 and len(row.features) == 468
    assert row.features == menu.candidate_vector(0, feature_version=10)
    assert row.outcome.completed is won and row.outcome.attempted
    assert row.outcome.actions == 120 and row.outcome.frames == 7000
    assert row.outcome.restorations == 0 and row.outcome.cash_debits == 750
    assert row.document()['schema'] == 'pokemon.player.challenge-consequence.v4'
    assert ConsequenceExample.from_document(row.document()) == row
    assert 'machine_lesson' not in str(row.document())
    assert ChallengeConsequenceSpec.from_document(plan['spec']).document() == plan['spec']


@pytest.mark.parametrize('fault', ['move', 'pp', 'xp', 'hp', 'other_member', 'cash', 'bag',
    'collection', 'stats', 'location', 'event', 'raw_pp', 'unconsumed'])
def test_machine_outcome_rejects_unverified_custody_changes(tmp_path, monkeypatch, fault):
    plan, phases, _ = machine_documents(tmp_path, monkeypatch)
    after = phases[0]['after']
    if fault == 'move': after['lesson']['party'][0]['moves'][3][0] = 55
    elif fault == 'pp': after['lesson']['party'][0]['moves'][3][1] = 9
    elif fault == 'xp': after['lesson']['party'][0]['experience'] += 1
    elif fault == 'hp': after['lesson']['party'][0]['hp'] += 1
    elif fault == 'other_member': after['lesson']['party'][1]['moves'][0][0] = 58
    elif fault == 'cash': after['cash'] -= 1
    elif fault == 'bag': after['economy']['inventory'] = [['red-item-001', 1]]
    elif fault == 'unconsumed': after['economy']['inventory'] = [['red-item-213', 1]]
    elif fault == 'collection': after['machine_boundary']['protected_collection_sha256'] = 'd' * 64
    elif fault == 'stats': after['machine_boundary']['party_stats'][0][0] += 1
    elif fault == 'location': after['machine_boundary']['location'][0] += 1
    elif fault == 'event': after['endpoint']['events'] = [True]
    elif fault == 'raw_pp': after['machine_boundary']['party_pp'][0][3] = 25
    phases[1]['before'] = copy.deepcopy(after)
    with pytest.raises(ValueError): project_consequence(plan, phases)


@pytest.mark.parametrize('fault', ['binding', 'source', 'version', 'schema', 'descriptor',
    'recipient', 'removed_pp', 'maximum_pp', 'stats', 'unowned'])
def test_machine_start_requires_exact_native_source_legal_lesson_and_semantic_facts(tmp_path, monkeypatch, fault):
    plan, phases, menu = machine_documents(tmp_path, monkeypatch)
    if fault == 'binding': plan['binding_ref'] = 'unbound'
    elif fault == 'source': plan['source']['state_sha256'] = 'f' * 64
    elif fault == 'version': plan['feature_version'] = 9
    elif fault == 'schema': plan['schema'] = 'pokemon.red.challenge-consequence-plan.v5'
    elif fault == 'descriptor':
        plan['menu'] = replace(menu, candidates=(replace(menu.candidates[0], move_change=None),
                                               *menu.candidates[1:])).policy_dict()
    elif fault == 'recipient': plan['before']['lesson']['party'][0]['species_id'] = 2
    elif fault == 'removed_pp': plan['before']['lesson']['party'][0]['moves'][3][1] = 24
    elif fault == 'maximum_pp': plan['before']['machine_boundary']['party_pp'][0][3] |= 64
    elif fault == 'stats': plan['before']['machine_boundary']['party_stats'][0][0] += 1
    elif fault == 'unowned': plan['before']['economy']['inventory'] = []
    with pytest.raises(ValueError): project_consequence(plan, phases)


def test_incomplete_challenge_is_censored_and_a_clean_failed_lesson_is_not_battle_loss(tmp_path, monkeypatch):
    plan, phases, _ = machine_documents(tmp_path, monkeypatch)
    row = project_consequence(plan, phases[:1])
    assert row.outcome is None and row.censor_reason == 'challenge_not_reached_before_stop'
    phases[0]['verified'] = False
    after = copy.deepcopy(plan['before'])
    after.update(state_sha256='a' * 64, actions=100, completed_actions=100, frames=6000)
    phases[0]['after'] = after
    row = project_consequence(plan, phases[:1])
    assert row.outcome is not None and not row.outcome.attempted


def test_new_learner_codec_retains_legacy_rows_and_distinguishes_native_shaped_replacements(tmp_path, monkeypatch):
    plan, phases, menu = machine_documents(tmp_path, monkeypatch, slot=4)
    water = replace(project_consequence(plan, phases), provenance='synthetic')
    other, other_phases, other_menu = machine_documents(tmp_path / 'other', monkeypatch, slot=1)
    bite = replace(project_consequence(other, other_phases), provenance='synthetic')
    assert water.features != bite.features
    # Numerical seam only: labels are explicitly synthetic, never admitted TRAIN data.
    bite = replace(bite, outcome=replace(bite.outcome, actions=300))
    head = fit_challenge_consequence((water, bite), feature_version=10)
    assert head.feature_version == 10 and head.coefficients.shape[0] == 468
    assert head.document()['schema'] == 'pokemon.player.challenge-consequence-head.v5'
    restored = ChallengeConsequenceHead.from_document(head.document(), expected_sha256=head.model_sha256)
    np.testing.assert_array_equal(restored.coefficients, head.coefficients)
    assert head.predict(water.features)[2] < head.predict(bite.features)[2]


def test_v10_native_session_claim_retains_explicit_version_and_unchanged_guarded_port(tmp_path, monkeypatch):
    args, _ = harness(tmp_path, monkeypatch, first=GoalKind.ADVANCE_STORY)
    args['model'] = upgrade_option_value_model_for_move_change(args['model'])
    s = session(args)
    assert s.model_feature_version == 10 and s.consequence is not None
    record = s.store.find_sealed_record(s.execution.claim_id,
        expected_kind='red_native_player_execution').read()
    assert record['consequence_feature_version'] == 10
    options = s.observe(0)
    story = next(b for b in options.bindings if b.kind is GoalKind.ADVANCE_STORY)
    prospective = s.consequence.begin(options, story, preflight_only=True)
    assert prospective['schema'] == 'pokemon.red.challenge-consequence-plan.v7'
    assert prospective['feature_version'] == 10
    assert s.controller.frames_executed == 0 and not s.recorder.trace


@pytest.mark.parametrize('field', ['item_id', 'party_slot', 'replace_slot', 'species_id', 'move_id'])
def test_machine_target_rejects_boolean_native_identifiers(tmp_path, monkeypatch, field):
    plan, _, _ = machine_documents(tmp_path, monkeypatch)
    target = plan['spec']['machine_lesson']
    target['lesson'][field] = True
    with pytest.raises(ValueError): ChallengeConsequenceSpec.from_document(plan['spec'])
