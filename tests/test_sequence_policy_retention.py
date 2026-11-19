"""Observed-kind continuation retention; synthetic data, no native admission."""
from dataclasses import replace
import pytest
from test_player_sequence_policy import setup
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.player_sequence_policy import SequenceChoiceContext,SequencePolicy

def fixture():
    model,options,prior,context,_=setup()
    params=list(prior.head.parameters);p=params[0];params[0]=(p[0]+.25,*p[1:])
    learned=replace(prior,head=replace(prior.head,parameters=tuple(params)))
    candidate=replace(options.menu.candidates[0],features=replace(options.menu.candidates[0].features,kind=LivingDexOptionKind.ACQUIRE))
    menu=replace(options.menu,candidates=(candidate,*options.menu.candidates[1:]))
    context=replace(context,menu_sha256=menu.policy_sha256)
    scoped=replace(learned,retained_policy=prior,supported_kinds=('unlock_access',),support_evidence_sha256='f'*64)
    return model,menu,context,prior,learned,scoped

def test_unobserved_kind_keeps_exact_prior_score_without_hiding_action():
    model,menu,context,prior,learned,scoped=fixture()
    old=prior.scores(model,menu,context);new=learned.scores(model,menu,context);actual=scoped.scores(model,menu,context)
    assert menu.available_indices==(0,1)
    assert actual[0]==old[0] and actual[1]==new[1] and new[0]!=old[0]
    assert actual[0]is not None and actual[1]is not None

def test_scope_roundtrip_and_legacy_identity_stay_exact():
    model,menu,context,prior,learned,scoped=fixture()
    for p in [prior,learned,scoped]:
        restored=SequencePolicy.from_document(p.document(),expected_sha256=p.model_sha256)
        assert restored.document()==p.document() and restored.scores(model,menu,context)==p.scores(model,menu,context)
    assert 'retained_sequence_scope'not in prior.document()
    assert scoped.model_sha256!=learned.model_sha256

@pytest.mark.parametrize('fault',['empty','unknown','duplicates','unsorted','missing-proof','changed-utility','nested-prior'])
def test_invalid_retention_scope_is_rejected(fault):
    *_,scoped=fixture()
    changes={'empty':dict(supported_kinds=()),'unknown':dict(supported_kinds=('private-goal',)),'duplicates':dict(supported_kinds=('unlock_access','unlock_access')),'unsorted':dict(supported_kinds=('unlock_access','acquire')),'missing-proof':dict(support_evidence_sha256=None),'changed-utility':dict(sequence_weight=scoped.sequence_weight+1),'nested-prior':dict(retained_policy=scoped)}[fault]
    with pytest.raises((ValueError,TypeError)):replace(scoped,**changes)

def test_retention_inputs_cannot_be_silently_ignored():
    *_,prior,learned,scoped=fixture()
    with pytest.raises(ValueError):replace(prior,supported_kinds=('unlock_access',))

def test_private_renaming_and_reordering_do_not_change_scores():
    model,menu,context,prior,learned,scoped=fixture();scores=scoped.scores(model,menu,context)
    renamed=replace(menu,candidates=tuple(replace(c,binding_ref='private-'+str(i))for i,c in enumerate(reversed(menu.candidates))))
    reverse=replace(context,menu_sha256=renamed.policy_sha256,histories=tuple(reversed(context.histories)))
    assert scoped.scores(model,renamed,reverse)==tuple(reversed(scores))
