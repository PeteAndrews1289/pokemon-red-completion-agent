"""Prior preparation effort is observed history, never a goal-switch rule."""
from dataclasses import replace
import pytest
from test_red_sequence_receipts import episode, project
from test_player_sequence_policy import setup
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.player_sequence_policy import SequenceChoiceContext
from pokemon_red_completion.player_sequence_value import (
    SequenceRegressionRow, SequenceValueHead, fit_sequence_value,
)
from pokemon_red_completion.recorded_branch_history import (
    STORY_HISTORY, PREPARATION_HISTORY, RecordedBranchHistory, recorded_option_history,
)


def prep_history(projection,boundary,**kwargs):
    return recorded_option_history(projection,kind=GoalKind.DEVELOP_TEAM.value,
        objective_ref=None,history_contract=PREPARATION_HISTORY,
        boundary_sha256=boundary,expected_source_sha256=projection.source_sha256,
        expected_plan_sha256=projection.plan_sha256,**kwargs)


def test_prefix_preparation_counts_attempt_and_attached_support_once(episode):
    p=project(episode)
    p=replace(p,selected_kinds=(GoalKind.DEVELOP_TEAM.value,)*2,story_contexts=(None,None))
    first,second=p.choices
    assert prep_history(p,first.before_sha256).attempts==0
    h=prep_history(p,second.before_sha256)
    assert (h.attempts,h.actions,h.frames,h.observed_cash_debits)==(1,2,20,40)
    assert prep_history(p,second.after_sha256).attempts==2
    changed=replace(p,choices=(first,replace(second,actions=900,frames=90000,blackouts=7)))
    assert prep_history(changed,second.before_sha256)==h
    for field in ['source_sha256','plan_sha256']:
        with pytest.raises(ValueError,match='source/plan'):
            recorded_option_history(replace(p,**{field:'f'*64}),
                kind=GoalKind.DEVELOP_TEAM.value,objective_ref=None,
                history_contract=PREPARATION_HISTORY,boundary_sha256=second.before_sha256,
                expected_source_sha256=p.source_sha256,expected_plan_sha256=p.plan_sha256)


def test_legacy_contract_and_other_kinds_do_not_borrow_preparation_history(episode):
    p=project(episode);p=replace(p,selected_kinds=(GoalKind.DEVELOP_TEAM.value,)*2,story_contexts=(None,None))
    for kind,contract in [(GoalKind.DEVELOP_TEAM.value,STORY_HISTORY),(GoalKind.RESUPPLY.value,PREPARATION_HISTORY)]:
        h=recorded_option_history(p,kind=kind,objective_ref=None,history_contract=contract,
            boundary_sha256=p.choices[-1].before_sha256,
            expected_source_sha256=p.source_sha256,expected_plan_sha256=p.plan_sha256)
        assert h==RecordedBranchHistory(0,0,0,0,0,0,0,0)


def test_new_history_identity_roundtrip_and_legacy_score_retention():
    model,options,prior,old_context,_=setup()
    menu=replace(options.menu,candidates=tuple(replace(c,features=replace(c.features,
        kind=LivingDexOptionKind.DEVELOP)) for c in options.menu.candidates))
    context=replace(old_context,menu_sha256=menu.policy_sha256,history_contract=PREPARATION_HISTORY)
    assert SequenceChoiceContext.from_document(context.document())==context
    assert 'history_contract' not in old_context.document()
    legacy=context.for_history_contract(menu,STORY_HISTORY)
    assert all(not h.attempts for h in legacy.histories)
    assert legacy.history_contract==STORY_HISTORY
    candidate=replace(prior.head,history_contract=PREPARATION_HISTORY)
    assert candidate.model_sha256!=prior.head.model_sha256
    assert SequenceValueHead.from_document(candidate.document(),expected_sha256=candidate.model_sha256)==candidate
    assert 'history_contract' not in prior.head.document()
    with pytest.raises(ValueError,match='preparation history'):
        legacy.for_history_contract(menu,PREPARATION_HISTORY)
    with pytest.raises(ValueError,match='frozen policy'):
        prior.scores(model,menu,context)
    scoped=replace(prior,head=candidate,retained_policy=prior,
        supported_kinds=('unlock_access',),support_evidence_sha256='f'*64)
    assert scoped.scores(model,menu,context)==prior.scores(model,menu,legacy)


def test_fit_rejects_mixed_history_semantics():
    _,options,prior,context,_=setup()
    vector=context.vectors(options.menu)[0]
    rows=tuple(SequenceRegressionRow(f'{i:064x}',vector,(0.,)*7,'train',
        history_contract=contract) for i,contract in enumerate([STORY_HISTORY,PREPARATION_HISTORY]))
    with pytest.raises(ValueError,match='distinct TRAIN'):
        fit_sequence_value(rows,ridge=1.,horizon=4,behavior_model_sha256=prior.baseline_sha256)


def test_opt_in_history_runs_reconstructs_and_replays_through_existing_native_wrapper(tmp_path,monkeypatch):
    import test_red_native_sequence_policy as native
    from pokemon_red_completion.red_sequence_native_audit import audit_native_sequence_trace
    from pokemon_red_completion.player_sequence_reconstruction import reconstruct_sequence_candidates
    from pokemon_red_completion.provenance import canonical_sha256
    import json
    original=native.policy_setup
    def setup_with_history():
        values=list(original())
        values[2]=replace(values[2],head=replace(values[2].head,history_contract=PREPARATION_HISTORY))
        return tuple(values)
    monkeypatch.setattr(native,'policy_setup',setup_with_history)
    args,result,executed,audit_args=native.run(tmp_path,monkeypatch)
    assert executed==[2,4,6,8,10,12]
    assert audit_native_sequence_trace(args['output'],**audit_args).recorded_selector_and_binding_replayed==6
    root=args['output']/'episode'
    read=lambda name:json.loads((root/name).read_bytes())
    declaration=read('sequence/declaration.json')
    assert declaration['history_contract']==PREPARATION_HISTORY
    windows=reconstruct_sequence_candidates(root,source_sha256=args['source']['state_sha256'],
        partition=args['source']['partition'],expected_plan_sha256=canonical_sha256(read('plan.json')),
        expected_result_sha256=canonical_sha256(read('result.json')),
        expected_declaration_sha256=canonical_sha256(declaration))
    assert windows and not any(w.training_eligible for w in windows)
