"""Finite TRAIN component reuse; source, policy flags and legacy K stay exact."""
from pathlib import Path
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace as N
import json
import pytest
from pokemon_red_completion import red_production_train_admission as a
from pokemon_red_completion import red_scoped_train_composition as c
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_story_battle import StoryTrainerContract
from pokemon_red_completion.red_learned_trainer import FROZEN_K_SHA256
from pokemon_red_completion.red_development_story_scope import DevelopmentStoryScope
from test_red_scoped_training_battlers import prototype


def setup(tmp_path,monkeypatch):
    state=b'source';origin='b'*64
    context=json.dumps(dict(state_sha256=sha256(state).hexdigest(),fit_allowed=False,grants_new_budget=False)).encode()
    def file(name,payload):
        p=tmp_path/name;p.write_bytes(payload)
        return dict(path=str(p),sha256=sha256(payload).hexdigest())
    raw=b'{"test":true}';digest=sha256(raw).hexdigest()
    monkeypatch.setattr(a,'SCOPED_STORY_MODELS',frozenset({digest}))
    from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
    monkeypatch.setattr(TrainerPracticeThreeHeadModel,'from_dict',lambda x:N(to_dict=lambda:x))
    registry=file('registry.json',b'{}');auth=file('auth.json',b'{}')
    chain=file('chain.json',json.dumps(dict(passed=True,original_assignment=dict(partition='train',assignment_id=origin,root_lineage_id='red-goal-root-'+origin),registry=registry,original_authentication=auth)).encode())
    model=file('model.json',raw)
    direct=StoryTrainerContract('defeat_erika','test',134,(219,19,1),86,330)
    field=replace(direct,battle_plan_id='field',map_id=19,defeated_event=87)
    routes={canonical_sha256(__import__('dataclasses').asdict(x)):v for x,v in [(direct,digest),(field,FROZEN_K_SHA256)]}
    work=dict(partition='train',fit_allowed=False,TRAIN_source_authentication=chain,
        production_story_components={digest:model},production_story_routes=routes,pins={x['path']:x['sha256']for x in (chain,model)})
    payload=json.dumps(work).encode()
    source=dict(partition='train',state_sha256=sha256(state).hexdigest(),origin_sha256=origin,source_commit='c'*40,experiment_sha256=sha256(payload).hexdigest())
    args=dict(source=source,state_bytes=state,context_bytes=context,work_order_bytes=payload,contracts=(direct,field))
    return args,work,digest


@pytest.mark.parametrize('fault',['partition','state','context','order','origin','missing_pin','changed_model','DEV_assignment','missing_contract','unknown_model'])
def test_bad_source_component_or_contract_refused_without_native_io(tmp_path,monkeypatch,fault):
    kw,work,digest=setup(tmp_path,monkeypatch)
    if fault=='partition':kw['source']['partition']='development'
    if fault=='state':kw['state_bytes']+=b'x'
    if fault=='context':kw['context_bytes']=b'{}'
    if fault=='order':kw['source']['experiment_sha256']='f'*64
    if fault=='origin':kw['source']['origin_sha256']='e'*64
    if fault=='missing_pin':work['pins']={}
    if fault=='changed_model':Path(work['production_story_components'][digest]['path']).write_bytes(b'changed')
    if fault=='DEV_assignment':
        p=Path(work['TRAIN_source_authentication']['path']);x=json.loads(p.read_bytes());x['original_assignment']['partition']='development';p.write_text(json.dumps(x));work['TRAIN_source_authentication']['sha256']=sha256(p.read_bytes()).hexdigest();work['pins'][str(p)]=sha256(p.read_bytes()).hexdigest()
    if fault=='missing_contract':work['production_story_routes'].pop(next(iter(work['production_story_routes'])))
    if fault=='unknown_model':work['production_story_components']={'f'*64:next(iter(work['production_story_components'].values()))}
    if fault in ['missing_pin','DEV_assignment','missing_contract','unknown_model']:
        kw['work_order_bytes']=json.dumps(work).encode();kw['source']['experiment_sha256']=sha256(kw['work_order_bytes']).hexdigest()
    with pytest.raises(ValueError):a.ScopedProductionStoryAdmission.authenticate(**kw)


def test_exact_story_reuse_keeps_wild_field_K_and_production_controls(tmp_path,monkeypatch):
    kw,work,digest=setup(tmp_path,monkeypatch);admission=a.ScopedProductionStoryAdmission.authenticate(**kw);d=admission.document()
    with pytest.raises(ValueError):a.ScopedProductionStoryAdmission(d,{}, {},{})
    with pytest.raises(AttributeError):admission._bytes=b'changed'
    class Readonly:frame_count=0
    monkeypatch.setattr(c,'ReadOnlyController',Readonly)
    spec=c.ScopedTrainComposition(d['source_state_sha256'],d['source_origin_sha256'],d['source_commit'],d['context_sha256'],d['work_order_sha256'],tmp_path/'native-plan.json',kw['contracts'],production_story_admission=admission)
    p=replace(prototype(tmp_path),session=Readonly(),source_commit=d['source_commit'],source_state_sha256=d['source_state_sha256'],root_lineage_id=d['root_lineage_id'],pp_depleted_switch_screen=True)
    group=spec.bind(p,source=kw['source'],output=tmp_path/'pools',initial=None)
    direct,field=kw['contracts'];actor=group.story(direct)
    assert actor.model_sha256==digest and group.story(field).model_sha256==FROZEN_K_SHA256
    assert group.wild.model_sha256==FROZEN_K_SHA256 and group.history()is None
    assert actor.pp_reentry_screen_active(actor.story_authority())
    scope=actor.development_story_scope
    assert scope.allow_learned_tactics and scope.diagnostic_status_entry and scope.screen_capped_status_moves
    doc=scope.document()
    with pytest.raises(ValueError):DevelopmentStoryScope.from_document(doc)
    restored=DevelopmentStoryScope.from_document(doc,train_admission=admission)
    assert restored.document()==doc
    for name in ['allow_learned_tactics','diagnostic_status_entry','screen_capped_status_moves']:
        with pytest.raises(ValueError):replace(scope,**{name:False})
    actor.model=N(to_dict=lambda:{'changed':True})
    with pytest.raises(ValueError):actor.require_train_story_scope()
    assert p.session.frame_count==0 and p.calls==0

