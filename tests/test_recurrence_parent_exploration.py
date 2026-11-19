"""Synthetic policy safety and parity; no learning or native-success evidence."""
import copy
import json
from dataclasses import replace
from hashlib import sha256

import numpy as np
import pytest
from test_red_live_option_menu import _binding, _situation
from test_story_loop_safety import endpoint
from test_red_consequence_choice import progress_head
from test_consequence_v15_vertical import dispatch_head
from test_red_branch_recovery import greedy_native_args
from test_unique_observed_combat_association import fixture, choose
from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion import red_movement_recurrence as recurrence
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from pokemon_red_completion.living_dex_option_value import LivingDexOptionValueModel, option_feature_names
from pokemon_red_completion.player_option_story_unit import OptionStoryUnit
from pokemon_red_completion.red_live_option_menu import build_red_live_option_set, RedLiveOptionSelectionMode as Mode
from pokemon_red_completion.resource_economy_observation import EconomySnapshot
from pokemon_red_completion.player_readiness import PlayerReadiness, READINESS_NAMES
import pokemon_red_completion.red_consequence_choice as C
import pokemon_red_completion.red_native_player as native
from run_configured_red_player import declared_readiness_refinement


def observed_menu(*, seen, changed=None):
    width = len(option_feature_names(16)); weights = np.zeros((width, 9))
    weights[option_feature_names(16).index('kind.unlock_access'), 2] = 1
    model = LivingDexOptionValueModel(weights, np.zeros(9), np.zeros(width),
                np.ones(width), 'a'*64, 10, 0, .25, 4, feature_version=16)
    destination = endpoint(2); current = endpoint(1)
    memory = GoalSearchMemory()
    if seen: recurrence.observe_movement_boundary(memory, destination)
    if changed == 'cash': current['cash'] += 1
    elif changed == 'xp': current['player_lesson']['party'][0]['experience'] += 1
    elif changed == 'event': current['movement_event_flags'] = '0101'
    elif changed == 'item': current['diagnostics']['bag_items'] = [[4, 3]]
    elif changed == 'unknown': current['movement_coins'] = None
    move = replace(_binding(GoalKind.ADVANCE_STORY, binding_ref='move', calls=[]),
        story_objective_ref='private-travel-goal', story_approach_only=True,
        story_unit=OptionStoryUnit('movement', True),
        movement_endpoint_sha256=recurrence.movement_boundary(destination)[0],
        maximum_cash_debit=0)
    acquire = _binding(GoalKind.ACQUIRE_SPECIES, binding_ref='acquire', calls=[])
    options = build_red_live_option_set(situation=_situation(resources=.1, safety=0),
        binding_set=GoalBindingSet((move.opportunity, acquire.opportunity), (move, acquire)),
        supplements=(), model_feature_version=16, ordering_seed_sha256='b'*64,
        economy_snapshot=EconomySnapshot(100, ()), target_cash=0,
        readiness=PlayerReadiness(tuple(2/3 if n == 'current.hp_fraction' else 0
                        for n in READINESS_NAMES[1:]), history_observed=False))
    return model, recurrence.menu_with_movement_history(options, memory, current)


def select(model, options, **kw):
    return C.select_branch_recovery_live_option(model, options, dispatch_head(),
        objective_ref='absent-declared-combat', seed=17, greedy_selection=True,
        refine_preparation=True, **kw)


@pytest.mark.parametrize('changed', [None, 'cash', 'xp', 'event', 'item', 'unknown'])
def test_only_equivalent_observed_endpoint_can_trigger_escape(changed):
    model, options = observed_menu(seen=True, changed=changed)
    before = options.public_dict()
    old = select(model, options)
    choice = select(model, options, explore_on_movement_recurrence=True)
    receipt = choice.branch_recovery
    assert options.public_dict() == before and choice.options is options
    assert old.branch_recovery.parent.selected_binding.story_unit == OptionStoryUnit('movement', True)
    if changed is None:
        expected = C.select_red_live_option(model, options, seed=17, allow_earning_exploration=True)
        assert receipt.recurrence_parent.public_dict() == old.branch_recovery.parent.public_dict()
        assert receipt.parent.public_dict() == expected.public_dict()
        assert choice.selected_binding is expected.selected_binding
        assert choice.scores == expected.scores and choice.probabilities == expected.probabilities
        assert receipt.document()['model_queries'] == 2
    else:
        assert receipt.recurrence_parent is None
        assert receipt.parent.public_dict() == old.branch_recovery.parent.public_dict()
        assert choice.selected_binding is old.selected_binding
        assert choice.scores == old.scores and choice.probabilities == old.probabilities


def test_novel_endpoint_preserves_exact_greedy_choice():
    model, options = observed_menu(seen=False)
    old = select(model, options); new = select(model, options, explore_on_movement_recurrence=True)
    assert new.branch_recovery.recurrence_parent is None
    assert new.branch_recovery.parent.public_dict() == old.branch_recovery.parent.public_dict()
    assert new.selected_binding is old.selected_binding and new.scores == old.scores
    assert new.model_sha256 != old.model_sha256


@pytest.mark.parametrize('child_story', [False, True])
def test_normal_child_scope_keeps_exact_parent_and_child(tmp_path, monkeypatch, child_story):
    options, _, _, model, head, seen, runtime = fixture(tmp_path, monkeypatch, child_story=child_story)
    old=choose(options,model,head); new=choose(options,model,head,explore_on_movement_recurrence=True)
    assert old.branch_recovery.parent.public_dict()==new.branch_recovery.parent.public_dict()
    assert old.branch_recovery.child.public_dict()==new.branch_recovery.child.public_dict()
    assert old.selected_binding is new.selected_binding
    assert old.scores==new.scores and old.probabilities==new.probabilities
    assert new.branch_recovery.recurrence_parent is None
    assert seen==[options,options] and not runtime.recorder.trace


@pytest.mark.parametrize('fault', ['missing','seed','model','nonmovement'])
def test_recurrence_receipt_cannot_lose_or_forge_its_greedy_witness(fault):
    model, options=observed_menu(seen=True)
    choice=select(model,options,explore_on_movement_recurrence=True)
    receipt=choice.branch_recovery; prior=receipt.recurrence_parent
    if fault=='missing': prior=None
    elif fault=='seed': prior=replace(prior,seed=prior.seed+1)
    elif fault=='model': prior=replace(prior,model_sha256='c'*64)
    else:
        cs=tuple(replace(c,movement_revisit=False) for c in options.menu.candidates)
        prior=replace(prior,options=replace(options,menu=replace(options.menu,candidates=cs)))
    with pytest.raises(ValueError): replace(choice,branch_recovery=replace(receipt,recurrence_parent=prior))


@pytest.mark.parametrize('changes',[
    {'explore_on_movement_recurrence':1}, {'explore_outside_scope':True},
    {'greedy_selection':False}, {'refine_preparation':False},
    {'defer_unbound_preparation':True}, {'allow_singleton_parent_support':True}])
def test_invalid_composition_is_rejected_before_any_model_query(monkeypatch,changes):
    model,options=observed_menu(seen=True)
    monkeypatch.setattr(C,'select_red_live_option',lambda *a,**k:pytest.fail('unexpected query'))
    kw=dict(greedy_selection=True,refine_preparation=True,explore_on_movement_recurrence=True)
    kw.update(changes)
    with pytest.raises(ValueError): C.select_branch_recovery_live_option(model,options,progress_head(),objective_ref='absent',seed=1,**kw)


@pytest.mark.parametrize('fault',[None,'history','partition','broad','type'])
def test_plan_requires_explicit_history_and_development_admission(tmp_path,fault):
    head=progress_head(); payload=json.dumps(head.document()).encode();p=tmp_path/'head.json';p.write_bytes(payload)
    spec=dict(objective_ref='defeat_lorelei',head_path=str(p),head_sha256=head.model_sha256,
        content_sha256=sha256(payload).hexdigest(),reason='Explicit recurrence diagnostic',
        refine_preparation=True,explore_on_movement_recurrence=True)
    plan=dict(partition='development',objectives=['defeat_lorelei'],movement_revisit_saturation=True,
        goal_selection=dict(mode='greedy',reason='Explicit development'),readiness_refinement=spec)
    if fault=='history':plan['movement_revisit_saturation']=False
    elif fault=='partition':plan['partition']='train'
    elif fault=='broad':spec['explore_outside_scope']=True
    elif fault=='type':spec['explore_on_movement_recurrence']=1
    if fault:
        with pytest.raises(ValueError):declared_readiness_refinement(plan)
    else: assert declared_readiness_refinement(plan)['explore_on_movement_recurrence'] is True


def test_native_plan_intent_and_decision_bind_new_policy(tmp_path,monkeypatch):
    args,_=greedy_native_args(tmp_path,monkeypatch)
    args.update(refine_preparation=True,explore_on_movement_recurrence=True,movement_revisit_saturation=True)
    args['model'],_=observed_menu(seen=False)
    args['consequence_head']=dispatch_head()
    capture=native.capture_player_lesson_snapshot
    def snapshot(rt):
        observation,lesson=capture(rt)
        observation.raw.event_flags=None  # Explicitly unknown in this ROM-free fixture.
        return observation,lesson
    monkeypatch.setattr(native,'capture_player_lesson_snapshot',snapshot)
    result=native.run_native_continuous_player(**args)
    plan=json.loads((args['output']/'native-plan.json').read_bytes())
    intent=json.loads((args['output']/'episode/step-000/intent.json').read_bytes())
    decision=json.loads((args['output']/'episode/step-000/decision.json').read_bytes())
    assert plan['explore_on_movement_recurrence'] is True
    assert intent['private_recurrence_sampling_policy']['explore_on_movement_recurrence'] is True
    assert decision['branch_recovery']['explore_on_movement_recurrence'] is True
    assert result['model_sha256']==C.branch_recovery_identity(args['model'].model_sha256,
        args['consequence_head'].model_sha256,args['consequence_objective_ref'],
        greedy_selection=True,refine_preparation=True,explore_on_movement_recurrence=True)


@pytest.mark.parametrize('fault',['history','train','refine','nonbool'])
def test_invalid_native_authority_fails_before_guest_inputs(tmp_path,monkeypatch,fault):
    args,_=greedy_native_args(tmp_path,monkeypatch)
    args.update(refine_preparation=True,explore_on_movement_recurrence=True,movement_revisit_saturation=True)
    if fault=='history':args['movement_revisit_saturation']=False
    elif fault=='train':args['source']['partition']='train'
    elif fault=='refine':args['refine_preparation']=False
    else:args['explore_on_movement_recurrence']=1
    with pytest.raises(ValueError):native.run_native_continuous_player(**args)
    assert not args['output'].exists() and args['emulator'].frame_count==0
