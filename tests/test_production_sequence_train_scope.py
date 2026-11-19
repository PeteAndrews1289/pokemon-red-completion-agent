"""Authenticate normal-player TRAIN reuse without a partition or selector swap."""
import json
from dataclasses import asdict,replace
from hashlib import sha256
from types import SimpleNamespace as N
import pytest
from test_league_funding_train_admission import source
from test_stable_sequence_selection import fixture
from pokemon_red_completion.red_native_player import NativePlayerLimits
from pokemon_red_completion.red_production_train_admission import LeagueFundingTrainAdmission
from pokemon_red_completion.red_scoped_train_composition import (
    ProductionSequenceTrainScope, production_sequence_train_declaration,
)


def prepared(source):
    model,_,policy,_=fixture(mode='stable_costly_recurrence')
    limits=NativePlayerLimits(decisions=4,actions=10000,frames=1000000,seconds=120,heals=100,cash_debits=None)
    recipe=dict(force_resource_safety=True,include_live_pp_readiness=True,
        allow_collection_restoration=True,story_kind_commitment=True,
        respect_combat_preparation_choice=True,movement_revisit_saturation=True)
    declaration=production_sequence_train_declaration(model,policy,limits,recipe)
    work=json.loads(source['work_order_bytes'])
    work.update(production_sequence=declaration,fit_allowed=False,campaign=False)
    args=dict(source,work_order_bytes=json.dumps(work).encode())
    admission=LeagueFundingTrainAdmission.authenticate(**args)
    context=json.dumps(dict(state_sha256=admission.source_state_sha256)).encode()
    inputs=dict(admission=admission,source_state=args['source_state'],context_bytes=context,
        work_order_bytes=args['work_order_bytes'],model=model,policy=policy,limits=limits,recipe=recipe)
    native_source=dict(partition='train',state_sha256=admission.source_state_sha256,
        origin_sha256=admission.source_origin_sha256,source_commit=admission.source_commit,
        experiment_sha256=admission.work_order_sha256)
    return inputs,native_source


def test_actual_authenticated_source_policy_and_recipe_are_required(source):
    inputs,native=prepared(source)
    scope=ProductionSequenceTrainScope.authenticate(**inputs)
    scope.require_policy(source=native,**{k:inputs[k] for k in ['model','policy','limits','recipe']})
    scope.require_session(source=native,execution=N(model_sha256=inputs['policy'].model_sha256),
        limits=inputs['limits'],recipe={k:v for k,v in inputs['recipe'].items() if k!='movement_revisit_saturation'})
    scope.require_assembly(payload=inputs['source_state'],context_bytes=inputs['context_bytes'],
        work_order_bytes=inputs['work_order_bytes'],origin_sha=scope.funding_admission.source_origin_sha256,
        origin_id=scope.funding_admission.root_lineage_id)
    d=scope.document()
    assert d['teacher_selection'] is False and d['full_normal_menu'] is True
    assert d['optimizer_admission'] is d['fit_admission'] is d['new_independent_origin'] is False
    with pytest.raises(ValueError,match='authenticated bytes'):
        ProductionSequenceTrainScope(d,inputs['admission'])


@pytest.mark.parametrize('fault',['state','context','work','model','policy','limits','recipe','source','partition'])
def test_swapped_bytes_source_or_selector_fail_closed(source,fault):
    inputs,native=prepared(source);scope=ProductionSequenceTrainScope.authenticate(**inputs)
    if fault in ['state','context','work']:
        field={'state':'source_state','context':'context_bytes','work':'work_order_bytes'}[fault]
        changed=dict(inputs,**{field:b'{}'})
        with pytest.raises((ValueError,KeyError)):
            ProductionSequenceTrainScope.authenticate(**changed)
        return
    selected={k:inputs[k] for k in ['model','policy','limits','recipe']}
    if fault=='source':native['state_sha256']='f'*64
    elif fault=='partition':native['partition']='development'
    elif fault=='model':selected['model']=None
    elif fault=='policy':selected['policy']=replace(inputs['policy'],sequence_weight=2.)
    elif fault=='limits':selected['limits']=replace(inputs['limits'],actions=20000)
    else:selected['recipe']=dict(inputs['recipe'],force_resource_safety=False)
    with pytest.raises(ValueError):scope.require_policy(source=native,**selected)
