import json
from hashlib import sha256
from types import SimpleNamespace as N
import pytest
import pokemon_red_completion.red_production_train_admission as admission
import pokemon_red_completion.red_league_funding as league
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.red_player_league_options import LEAGUE_PLAYER_TARGETS

def packed(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()

@pytest.fixture
def source(monkeypatch):
 state=b'isolated-unit-test-TRAIN-source';s=sha256(state).hexdigest();envelope=dict(state_sha256=s)
 setup=dict(source_sha256=admission.SOURCE_ORIGIN);setup_bytes=packed(setup)
 progress=dict(partition='train',campaign_eligible=False,envelope=envelope,state_sha256=s,setup_receipt_sha256=sha256(setup_bytes).hexdigest())
 e,p=packed(envelope),packed(progress);model=packed(dict(schema='unit-test-model'))
 original=packed(dict(partition='train',development_outcomes=0,conditions={'lower-full':dict(source_sha256=s)}))
 pin=sha256(model).hexdigest();content=admission.canonical_sha256(json.loads(model))
 monkeypatch.setattr(admission,'LEAGUE_TRAIN_SOURCES',{s:('lower-full',sha256(e).hexdigest(),sha256(p).hexdigest())})
 monkeypatch.setattr(admission,'LEAGUE_TRAIN_MODEL',pin);monkeypatch.setattr(admission,'LEAGUE_TRAIN_CONTENT',content)
 d=dict(schema=admission.LEAGUE_TRAIN_SCHEMA,source_state_sha256=s,source_envelope_sha256=sha256(e).hexdigest(),assisted_progress_sha256=sha256(p).hexdigest(),setup_sha256=sha256(setup_bytes).hexdigest(),source_origin_sha256=admission.SOURCE_ORIGIN,model_sha256=pin,model_content_sha256=content,original_train_plan_sha256=sha256(original).hexdigest())
 work=packed(dict(partition='train',teacher_actions_allowed=True,league_funding_train_component=d))
 return dict(source_state=state,envelope_bytes=e,progress_bytes=p,setup_bytes=setup_bytes,original_train_plan_bytes=original,work_order_bytes=work,source_commit='a'*40,model_bytes=model)

def test_requires_actual_authenticated_bytes_not_metadata_only():
 with pytest.raises(ValueError):admission.LeagueFundingTrainAdmission({})

def test_authenticated_source_binds_exact_work_and_no_fit_authority(source):
 a=admission.LeagueFundingTrainAdmission.authenticate(**source)
 a.require_work_order(source['work_order_bytes'])
 assert a.document()['fit_admission']is False and a.document()['complete_genesis']is False
 with pytest.raises(ValueError):a.require_work_order(source['work_order_bytes']+b' ')

@pytest.mark.parametrize('field',['source_state','envelope_bytes','progress_bytes','setup_bytes','original_train_plan_bytes','model_bytes'])
def test_changed_source_model_or_work_is_rejected(source,field):
 source[field]=source[field]+b' '
 with pytest.raises(ValueError):admission.LeagueFundingTrainAdmission.authenticate(**source)

@pytest.mark.parametrize('partition',['development','benchmark','sealed'])
def test_cannot_relabel_work_as_train(source,partition):
 w=json.loads(source['work_order_bytes']);w['partition']=partition;source['work_order_bytes']=packed(w)
 with pytest.raises(ValueError):admission.LeagueFundingTrainAdmission.authenticate(**source)

def scope_actor(a):
 target=LEAGUE_PLAYER_TARGETS[0]
 scope=N(source_state_sha256=a.source_state_sha256,root_lineage_id=a.root_lineage_id,work_order_sha256=a.work_order_sha256,model_sha256=admission.LEAGUE_TRAIN_MODEL,model_content_sha256=admission.LEAGUE_TRAIN_CONTENT,contract=N(objective_id=target.objective_id,map_id=int(target.room),defeated_event=int(target.event),victory_items=(),victory_badge_bits=0),gym_reward=None,allow_learned_tactics=True,diagnostic_status_entry=True,screen_capped_status_moves=True,diagnostic_stay_when_productive=False,diagnostic_prompt_stay=False,diagnostic_status_release=False)
 actor=N(source_partition=ScenarioPartition.TRAIN,source_commit=a.source_commit,source_state_sha256=a.source_state_sha256,root_lineage_id=a.root_lineage_id,pp_depleted_switch_screen=True,mechanics_aware_tower_choices=False,diagnostic_tower_productive_stay=False)
 return scope,actor

def test_only_exact_train_story_actor_settings_admitted(source):
 a=admission.LeagueFundingTrainAdmission.authenticate(**source);scope,actor=scope_actor(a);a.require_actor(actor,scope,'story')
 for obj,key,val in [(actor,'source_partition',ScenarioPartition.DEVELOPMENT),(actor,'pp_depleted_switch_screen',False),(scope,'model_sha256','f'*64),(scope,'diagnostic_stay_when_productive',True),(scope.contract,'map_id',0),(scope.contract,'objective_id','defeat_misty')]:
  before=getattr(obj,key);setattr(obj,key,val)
  with pytest.raises(ValueError):a.require_actor(actor,scope,'story')
  setattr(obj,key,before)
 with pytest.raises(ValueError):a.require_actor(actor,scope,'wild')

def test_current_indigo_walk_does_not_need_a_fly_destination():
 league.require_indigo_fly_destination((),{9:(1,1)},fly_required=False)
 with pytest.raises(league.RedLeagueFundingError):league.require_indigo_fly_destination((),{9:(1,1)},fly_required=True)
 with pytest.raises(league.RedLeagueFundingError):league.require_indigo_fly_destination((9,),{},fly_required=False)
 league.require_indigo_fly_destination((9,),{9:(1,1)},fly_required=True)


def test_new_work_order_format_binds_its_own_exact_bytes(source):
 a=admission.LeagueFundingTrainAdmission.authenticate(**source)
 source['work_order_bytes']+=b' '
 b=admission.LeagueFundingTrainAdmission.authenticate(**source)
 assert a.identity!=b.identity
 with pytest.raises(ValueError):a.require_work_order(source['work_order_bytes'])
 b.require_work_order(source['work_order_bytes'])


def test_level_override_does_not_accept_metadata_lookalikes():
 from pokemon_red_completion.red_trainer_story import _funding_train_level_screen
 assert _funding_train_level_screen(None)is False
 assert _funding_train_level_screen(N(battler=N(source_partition=ScenarioPartition.TRAIN)))is False


@pytest.fixture
def resource_source(source,monkeypatch):
 parent=source['source_state'];parent_sha=sha256(parent).hexdigest();state=b'ROM-free derived resource TRAIN source';s=sha256(state).hexdigest();envelope=dict(state_sha256=s)
 setup=dict(source_sha256=admission.SOURCE_ORIGIN,resource_parent_state_sha256=parent_sha,intervention='cash8_remove_ordinary_balls_only',all_other_WRAM_unchanged=True,party_XP_HP_PP_events_dex_unchanged=True,inputs=0,frames=0);setup_bytes=packed(setup)
 progress=dict(partition='train',campaign_eligible=False,envelope=envelope,state_sha256=s,setup_receipt_sha256=sha256(setup_bytes).hexdigest());e,p=packed(envelope),packed(progress)
 monkeypatch.setattr(admission,'LEAGUE_TRAIN_SOURCES',{**admission.LEAGUE_TRAIN_SOURCES,s:('lower-full',sha256(e).hexdigest(),sha256(p).hexdigest())});monkeypatch.setattr(admission,'LEAGUE_TRAIN_RESOURCE_SETUPS',{s:dict(parent_state_sha256=parent_sha,setup_sha256=sha256(setup_bytes).hexdigest())})
 work=json.loads(source['work_order_bytes']);d=work['league_funding_train_component'];d.update(schema=admission.LEAGUE_TRAIN_RESOURCE_SCHEMA,source_state_sha256=s,source_envelope_sha256=sha256(e).hexdigest(),assisted_progress_sha256=sha256(p).hexdigest(),setup_sha256=sha256(setup_bytes).hexdigest(),resource_parent_state_sha256=parent_sha)
 return dict(source,source_state=state,envelope_bytes=e,progress_bytes=p,setup_bytes=setup_bytes,work_order_bytes=packed(work),resource_parent_state=parent)

def test_resource_source_binds_actual_original_TRAIN_parent_and_work(resource_source):
 a=admission.LeagueFundingTrainAdmission.authenticate(**resource_source);a.require_work_order(resource_source['work_order_bytes']);scope,actor=scope_actor(a);a.require_actor(actor,scope,'story')
 assert a.document()['schema']==admission.LEAGUE_TRAIN_RESOURCE_SCHEMA and a.document()['fit_admission']is False

@pytest.mark.parametrize('parent',[None,b'development source',b'arbitrary claimed TRAIN source'])
def test_resource_source_rejects_unknown_or_missing_parent_before_actor(resource_source,parent):
 resource_source['resource_parent_state']=parent
 with pytest.raises(ValueError):admission.LeagueFundingTrainAdmission.authenticate(**resource_source)

def test_original_fixture_cannot_claim_derived_resource_parent(source):
 source['resource_parent_state']=source['source_state']
 with pytest.raises(ValueError):admission.LeagueFundingTrainAdmission.authenticate(**source)

def test_resource_work_order_cannot_drop_parent_claim(resource_source):
 work=json.loads(resource_source['work_order_bytes']);work['league_funding_train_component'].pop('resource_parent_state_sha256');resource_source['work_order_bytes']=packed(work)
 with pytest.raises(ValueError):admission.LeagueFundingTrainAdmission.authenticate(**resource_source)
