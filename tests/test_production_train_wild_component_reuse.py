"""No-ROM proof/codec/scope tests. Private immutable bytes are optional inputs.

POKEMON_PRODUCTION_WILD_COMPONENT is JSON with model/qualification paths.
POKEMON_PRODUCTION_TRAIN_COMPONENTS supplies state/envelope/progress/wild/story.
Tests use actual codecs and a fake native port; no inference, fit or emulator.
"""
from dataclasses import replace
from hashlib import sha256
import copy,json,os
from pathlib import Path
from types import SimpleNamespace as N
import pytest
from pokemon_red_completion import red_production_train_admission as a
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_development_preparation_scope import DevelopmentPreparationScope
from pokemon_red_completion.scenario_lab import ScenarioPartition
from test_production_train_admission import admitted,scope_and_actor

RAW="3b187fc6bfb46dd0fd062f0d14ff5fadffe353347d4e94a2124bdbaba988c4b3"
CONTENT="c9e129fd9413a1358c36801e1a0807b3af8187f1a30ab7af31a0b8f285fc1fb2"
QUAL="5773d5ac6989cce842b873a31c7449174bbe4fbfb95ba4c4e857fe70af8a1d0a"

@pytest.fixture(autouse=True)
def no_inference_fit_or_emulator(monkeypatch):
 from pokemon_red_completion.red_trainer_practice_head import TrainerHeadModel
 from pokemon_red_completion import red_trainer_practice_fit as fit
 from pokemon_red_completion.emulator import PyBoyAdapter
 def deny(*args,**kwargs):raise AssertionError("component qualification forbids inference, fitting and emulator construction")
 for name in("scores","probabilities","predict_index"):
  if hasattr(TrainerHeadModel,name):monkeypatch.setattr(TrainerHeadModel,name,deny)
 for name,value in tuple(vars(fit).items()):
  if name.startswith("fit_")and callable(value):monkeypatch.setattr(fit,name,deny)
 monkeypatch.setattr(PyBoyAdapter,"__init__",deny);monkeypatch.setattr(PyBoyAdapter,"load_state_bytes",deny)

@pytest.fixture
def material():
 spec=os.environ.get("POKEMON_PRODUCTION_WILD_COMPONENT")
 if spec is None:pytest.skip("immutable qualified wild component bytes not supplied; no ROM needed")
 paths=json.loads(spec);model=Path(paths["model"]).read_bytes();qualification=Path(paths["qualification"]).read_bytes()
 assert sha256(model).hexdigest()==RAW and sha256(qualification).hexdigest()==QUAL
 proof=a.authenticate_production_wild_component(model_bytes=model,qualification_bytes=qualification)
 return N(model=model,qualification=qualification,proof=proof)

def opted(proof):
 base=replace(admitted(),wild_component_proof=proof)
 payload=json.dumps(dict(partition="train",production_train_components=base.declaration()),sort_keys=True).encode()
 return replace(base,work_order_sha256=sha256(payload).hexdigest()),payload

def test_registered_tuple_is_finite_exact_and_story_legacy_stays_exact():
 assert a.QUALIFIED_WILD_COMPONENTS=={RAW:(CONTENT,QUAL)}
 assert a.WILD_MODEL=="720e9db864f3fefe2edfa27889203bd7c0fcbbd6968a65b960adcf1d57392161"
 assert a.STORY_MODEL=="29792a3292e8d5c103e39d5914d8b1c9388c65af107c989141331e14503712ad"

def test_legacy_documents_have_no_new_fields_or_identity_change():
 old=admitted();doc=old.document();decl=old.declaration()
 assert old.wild_component_proof is None and old.admission_schema==a.ADMISSION_SCHEMA
 assert set(doc)=={"schema","source_state_sha256","source_origin_sha256","source_commit","work_order_sha256","envelope_sha256","progress_sha256","source_partition","wild_model_sha256","story_model_sha256","wild_map_id","objective_id","fit_admission"}
 assert set(decl)=={"schema","source_state_sha256","source_envelope_sha256","assisted_progress_sha256","wild_model_sha256","story_model_sha256","wild_map_id","objective_id"}
 assert old.wild_model_sha256==a.WILD_MODEL and old.wild_model_content_sha256==a.WILD_CONTENT
 assert a.ProductionTrainAdmission.from_document(doc)==old and old.identity==canonical_sha256(doc)

def test_witness_cannot_be_constructed_from_unverified_claim():
 with pytest.raises(ValueError,match="actual model and qualification bytes"):
  a.VerifiedProductionWildComponent({"model_sha256":RAW})
 with pytest.raises(ValueError,match="verified wild component"):
  replace(admitted(),wild_component_proof={"model_sha256":RAW})

def test_actual_codec_creates_immutable_wild_only_witness(material):
 p=material.proof;doc=p.document();assert p.model_sha256==RAW and p.model_content_sha256==CONTENT and p.qualification_sha256==QUAL
 assert doc["role"]=="wild_only" and doc["wild_map_id"]==15 and not doc["fit_admission"]and not doc["global_adoption"]and not doc["trainer_deployment_qualified"]
 original=p.document();doc["role"]="story";assert p.document()==original
 assert p.identity==canonical_sha256(original)

@pytest.mark.parametrize("field",["model_bytes","qualification_bytes"])
def test_byte_identity_tampering_refused_before_authority(material,field):
 kw=dict(model_bytes=material.model,qualification_bytes=material.qualification);kw[field]+=b"\n"
 with pytest.raises(ValueError,match="bytes differ"):a.authenticate_production_wild_component(**kw)

@pytest.mark.parametrize("field",["model_bytes","qualification_bytes"])
def test_mutable_input_type_is_rejected(material,field):
 kw=dict(model_bytes=material.model,qualification_bytes=material.qualification);kw[field]=bytearray(kw[field])
 with pytest.raises(ValueError,match="immutable"):a.authenticate_production_wild_component(**kw)

@pytest.mark.parametrize("field",["passed","wild_preparation_core_native_qualified","all801_numeric_bounds_passed","healthy_and_sand_nidoran_endpoints_exact","unused_configuration_retained","whole_preparation_retained"])
def test_negative_qualification_flags_cannot_supply_reuse(material,monkeypatch,field):
 q=json.loads(material.qualification);q[field]=False;payload=json.dumps(q,sort_keys=True).encode()
 monkeypatch.setattr(a,"QUALIFIED_WILD_COMPONENTS",{RAW:(CONTENT,sha256(payload).hexdigest())})
 with pytest.raises(ValueError,match="wild-only qualification"):a.authenticate_production_wild_component(model_bytes=material.model,qualification_bytes=payload)

def test_codec_content_mismatch_rejected(material,monkeypatch):
 monkeypatch.setattr(a,"QUALIFIED_WILD_COMPONENTS",{RAW:("f"*64,QUAL)})
 with pytest.raises(ValueError,match="codec or canonical content"):a.authenticate_production_wild_component(model_bytes=material.model,qualification_bytes=material.qualification)

def test_opt_in_v2_requires_exact_proof_for_decoder_and_work_order(material):
 admission,payload=opted(material.proof);doc=admission.document()
 assert admission.admission_schema==a.ADMISSION_COMPONENT_SCHEMA and admission.wild_model_sha256==RAW
 assert doc["wild_component_proof_sha256"]==material.proof.identity and doc["wild_model_content_sha256"]==CONTENT and doc["wild_qualification_sha256"]==QUAL
 assert doc["story_model_sha256"]==a.STORY_MODEL and doc["fit_admission"]is False
 admission.require_work_order(payload)
 assert a.ProductionTrainAdmission.from_document(doc,wild_component_proof=material.proof)==admission
 with pytest.raises(ValueError):a.ProductionTrainAdmission.from_document(doc)
 with pytest.raises(ValueError):a.ProductionTrainAdmission.from_document(admitted().document(),wild_component_proof=material.proof)
 for key in("wild_model_sha256","wild_model_content_sha256","wild_qualification_sha256","wild_component_proof_sha256"):
  changed=dict(doc);changed[key]="f"*64
  with pytest.raises(ValueError):a.ProductionTrainAdmission.from_document(changed,wild_component_proof=material.proof)

def test_new_wild_scope_and_actor_match_with_unchanged_story(material):
 admission,_=opted(material.proof);_,s,actor=scope_and_actor();s.work_order_sha256=admission.work_order_sha256;s.model_sha256=RAW;s.model_content_sha256=CONTENT
 admission.require_scope(s,"wild");admission.require_actor(actor,s,"wild")
 typed=DevelopmentPreparationScope(admission.source_state_sha256,admission.root_lineage_id,RAW,CONTENT,admission.work_order_sha256,15,train_admission=admission)
 assert typed.document()["train_admission"]==admission.document()
 _,story,storyactor=scope_and_actor("story");story.work_order_sha256=admission.work_order_sha256
 admission.require_scope(story,"story");admission.require_actor(storyactor,story,"story")
 story.model_sha256=RAW;story.model_content_sha256=CONTENT
 with pytest.raises(ValueError,match="model/settings/target"):admission.require_scope(story,"story")

@pytest.mark.parametrize("field,value",[("model_sha256",a.WILD_MODEL),("model_content_sha256",a.WILD_CONTENT),("map_id",22),("source_state_sha256","f"*64),("work_order_sha256","f"*64)])
def test_wrong_component_or_source_cannot_borrow_v2(material,field,value):
 admission,_=opted(material.proof);_,s,actor=scope_and_actor();s.work_order_sha256=admission.work_order_sha256;s.model_sha256=RAW;s.model_content_sha256=CONTENT;setattr(s,field,value)
 with pytest.raises(ValueError):admission.require_actor(actor,s,"wild")

def test_wrong_actor_partition_and_pp_guard_remain_rejected(material):
 admission,_=opted(material.proof);_,s,actor=scope_and_actor();s.work_order_sha256=admission.work_order_sha256;s.model_sha256=RAW;s.model_content_sha256=CONTENT
 for field,value in(("source_partition",ScenarioPartition.DEVELOPMENT),("pp_depleted_switch_screen",True),("mechanics_aware_tower_choices",True)):
  changed=copy.copy(actor);setattr(changed,field,value)
  with pytest.raises(ValueError,match="actor source/settings"):admission.require_actor(changed,s,"wild")

def test_full_actual_source_authentication_and_pool_codec(material,tmp_path,monkeypatch):
 spec=os.environ.get("POKEMON_PRODUCTION_TRAIN_COMPONENTS")
 if spec is None:pytest.skip("immutable source/story bytes not supplied; fake controller needs no ROM")
 paths={k:Path(v)for k,v in json.loads(spec).items()};state,envelope,progress=(paths[k].read_bytes()for k in("state","envelope","progress"))
 from pokemon_red_completion.executor import NativeLessonController
 from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
 from pokemon_red_completion.red_learned_trainer import FrozenTrainerBattler
 from pokemon_red_completion.red_development_story_scope import DevelopmentStoryScope
 from pokemon_red_completion.red_gym_reward import MISTY_REWARD
 from pokemon_red_completion.red_scoped_training_battlers import ScopedTrainingBattlers
 from pokemon_red_completion.red_story_battle import StoryTrainerContract
 from pokemon_red_completion.red_production_train_readback import read_production_train_pool
 base=a.ProductionTrainAdmission(sha256(state).hexdigest(),a.SOURCE_ORIGIN,"a"*40,"b"*64,sha256(envelope).hexdigest(),sha256(progress).hexdigest(),wild_component_proof=material.proof)
 plan=json.dumps(dict(partition="train",production_train_components=base.declaration()),sort_keys=True).encode()
 admission=a.ProductionTrainAdmission.authenticate(source_state=state,envelope_bytes=envelope,progress_bytes=progress,plan_bytes=plan,source_commit="a"*40,wild_component_proof=material.proof)
 with pytest.raises(ValueError):a.ProductionTrainAdmission.authenticate(source_state=state,envelope_bytes=envelope,progress_bytes=progress,plan_bytes=plan,source_commit="a"*40)
 model=TrainerPracticeThreeHeadModel.from_dict(json.loads(material.model));storymodel=TrainerPracticeThreeHeadModel.from_dict(json.loads(paths["story"].read_bytes()))
 assert canonical_sha256(storymodel.to_dict())==a.STORY_CONTENT
 delegate=N(frame_count=0,save_state_bytes=lambda:state);port=NativeLessonController(delegate,maximum_frames=1000);reader=N(read=lambda:N(map_id=65,battle_state=0))
 scope=DevelopmentPreparationScope(admission.source_state_sha256,admission.root_lineage_id,RAW,CONTENT,admission.work_order_sha256,15,train_admission=admission)
 contract=StoryTrainerContract("defeat_misty","defeat_misty",65,(235,35,1),191,2079,((211,1),),2)
 ss=DevelopmentStoryScope(admission.source_state_sha256,admission.root_lineage_id,a.STORY_MODEL,a.STORY_CONTENT,admission.work_order_sha256,contract=contract,gym_reward=MISTY_REWARD,allow_learned_tactics=True,diagnostic_status_entry=True,screen_capped_status_moves=True,train_admission=admission)
 wild=FrozenTrainerBattler(port,model,tmp_path/"wild","a"*40,admission.root_lineage_id,admission.source_state_sha256,{},model_sha256=RAW,qualification_sha256=scope.identity,source_partition=ScenarioPartition.TRAIN,development_preparation_scope=scope)
 story=replace(wild,model=storymodel,model_sha256=a.STORY_MODEL,qualification_sha256=ss.identity,development_preparation_scope=None,development_story_scope=ss,pp_depleted_switch_screen=True,output=tmp_path/"story")
 source=dict(partition="train",state_sha256=admission.source_state_sha256,origin_sha256=admission.source_origin_sha256,source_commit=admission.source_commit,experiment_sha256=admission.work_order_sha256)
 pool=ScopedTrainingBattlers.for_production_source(wild,story,admission=admission,source=source,output=tmp_path/"pool",reader=reader)
 rb=read_production_train_pool(pool.output,expected_declaration_sha256=pool.declaration_sha256,expected_admission=admission,source=source,expected_story_calls=0)
 assert not rb.episodes and delegate.frame_count==0 and wild.calls==story.calls==0
 assert rb.declaration["actors"][1]["model_sha256"]==RAW and rb.declaration["actors"][0]["model_sha256"]==a.STORY_MODEL
 from test_production_train_pool import publish,play_wild,play_story
 monkeypatch.setattr(FrozenTrainerBattler,"_play",publish)
 context=N(reader=reader,contract=contract)
 play_wild(pool,context);play_story(pool,context)
 complete=read_production_train_pool(pool.output,expected_declaration_sha256=pool.declaration_sha256,expected_admission=admission,source=source,expected_story_calls=1)
 assert [e["scope"]for e in complete.episodes]==["wild","story"]and delegate.frame_count==20
 assert complete.declaration["actors"][1]["model_sha256"]==RAW
