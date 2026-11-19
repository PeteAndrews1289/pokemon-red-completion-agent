"""Postgame Dojo intro reuses the exact decoder and normal learned entry."""
from types import SimpleNamespace as N
from dataclasses import replace
import pytest
from pokemon_red_completion import red_player_engaged_story as engaged
from pokemon_red_completion import red_scripted_story_trainer as scripted
from pokemon_red_completion import red_story_battle as story
from pokemon_red_completion.goal_manager import GoalKind,GoalFailureReason,GoalDecisionOutcome
from pokemon_red_completion.actions import MacroActionKind
from test_red_story_battle import actor

EVENTS=(scripted.EventFlag.BEAT_FIGHTING_DOJO_TRAINER_0,scripted.EventFlag.BEAT_FIGHTING_DOJO_TRAINER_1,
 scripted.EventFlag.BEAT_FIGHTING_DOJO_TRAINER_2,scripted.EventFlag.BEAT_FIGHTING_DOJO_TRAINER_3)

def fixture(monkeypatch,fault=None):
 flags=bytearray(320)
 for event in EVENTS:
  if fault=="student_missing"and event==EVENTS[-1]:continue
  flags[int(event)//8]|=1<<(int(event)%8)
 if fault=="won":
  e=int(scripted.EventFlag.BEAT_KARATE_MASTER);flags[e//8]|=1<<(e%8)
 raw=N(map_id=178 if fault=="map"else 177,player_y=4 if fault=="position"else 3,player_x=4,
  badge_bits=127 if fault=="badge"else 255,battle_state=1 if fault=="wild"else 0,event_flags=bytes(flags),
  player_money=14568,party_count=1,party_species_ids=(35,),party_levels=(63,),party_hp=(188,),
  party_max_hp=(188,),party_status=(0,),party_moves=((64,),),party_pp=((35,),),bag_items=((4,10),),
  active_party_index=0,battler_hp=188,enemy_hp=100)
 obj=N(sprite_index=1,visible=fault!="object_hidden",at=(2,5)if fault=="object_wrong"else(3,5))
 state=N(raw=raw,dialogue=fault!="dialogue",facing="left"if fault=="facing"else"right",
  objects=(obj,obj)if fault=="object_duplicate"else(obj,),identity=(224,24,1))
 reader=N(read=lambda:state.raw,read_bottom_dialogue_box_visible=lambda:state.dialogue,
  read_player_facing=lambda:state.facing,read_current_map_objects=lambda:state.objects,
  trainer_engagement_active=lambda:False,read_active_trainer_identity=lambda:state.identity,
  read_input_readiness=lambda:N(ready=not state.dialogue),trainer_switch_prompt_visible=lambda raw:False)
 contract=story.StoryTrainerContract("postgame_collection","scripted-dojo-master",177,(224,24,1),
  int(scripted.EventFlag.BEAT_KARATE_MASTER),925)
 calls=[]
 monkeypatch.setattr(scripted,"dojo_master_contract",lambda rom,raw:calls.append((rom,raw))or contract)
 return state,reader,contract,calls

@pytest.mark.parametrize("fault",[None,"map","position","badge","wild","dialogue","facing","student_missing","won","object_hidden","object_wrong","object_duplicate"])
def test_postgame_contract_reuses_every_unchanged_native_intro_check(monkeypatch,fault):
 state,reader,contract,calls=fixture(monkeypatch,fault)
 got=engaged.engaged_story_contract(reader,b"rom",objective_id="postgame_collection")
 assert got is(contract if fault is None else None)
 assert bool(calls)is(fault is None)

def test_other_dojo_student_falls_through_when_intro_does_not_match(monkeypatch):
 state,reader,contract,calls=fixture(monkeypatch,"position")
 reader.trainer_engagement_active=lambda:True
 reader.read_trainer_battle_identity=lambda:(0,0,224,2)
 expected=object();seen=[]
 monkeypatch.setattr(engaged,"_ordinary_sight_contract",lambda rom,raw,identity,objective:
  seen.append((identity,objective))or expected)
 assert engaged.engaged_story_contract(reader,b"rom",objective_id="postgame_collection")is expected
 assert seen==[((224,24,2),"postgame_collection")]and not calls

def test_live_master_path_and_wild_refusal_are_unchanged(monkeypatch):
 state,reader,contract,calls=fixture(monkeypatch)
 state.raw.battle_state=2
 assert engaged.engaged_story_contract(reader,b"rom",objective_id="postgame_collection")is contract
 assert len(calls)==1
 state.raw.battle_state=1
 assert engaged.engaged_story_contract(reader,b"rom",objective_id="postgame_collection")is None

@pytest.mark.parametrize("fault",["default","no_champion","no_hall","wrong_label"])
def test_binding_requires_explicit_postgame_opt_in_and_completed_story(monkeypatch,fault):
 state,reader,contract,calls=fixture(monkeypatch)
 completed={"defeat_champion","enter_hall_of_fame"}
 if fault=="no_champion":completed.remove("defeat_champion")
 if fault=="no_hall":completed.remove("enter_hall_of_fame")
 rt=N(reader=reader,adapter=N(observe=lambda:N(game_state=object()),graph=N(
  available_objectives=lambda _:(),completed_ids=lambda _:completed)))
 binding=engaged.engaged_story_binding(rt,object(),rom=b"rom",battler=object(),
  objective_id="unavailable_chapter"if fault=="wrong_label"else"postgame_collection",
  allow_postgame_collection=fault!="default")
 assert binding is None and not calls

def bound(monkeypatch,tmp_path,*,outcome="won",wrong_live=False):
 state,reader,contract,calls=fixture(monkeypatch)
 em=N(state=b"original81",frame_count=0);em.save_state_bytes=lambda:em.state
 controls=[];learned=[]
 def execute(action):
  controls.append(action.kind);em.frame_count+=action.repeat or 1;em.state=b"live battle"
  state.raw.battle_state=2;state.dialogue=False
  if wrong_live:state.identity=(224,24,2)
 actions=N(actions_executed=0)
 def counted(action):actions.actions_executed+=1;execute(action)
 actions.execute=counted
 rt=N(reader=reader,emulator=em,adapter=N(observe=lambda:N(game_state=object()),graph=N(
  available_objectives=lambda _:(),completed_ids=lambda _:{"defeat_champion","enter_hall_of_fame"})))
 monkeypatch.setattr(engaged,"_field_ready",lambda runtime:state.raw.battle_state==0 and not state.dialogue)
 original=story.FrozenStoryBattleController
 monkeypatch.setattr(engaged,"FrozenStoryBattleController",lambda actor,contracts,**kwargs:
  original(actor,contracts,evolution_rom=None))
 monkeypatch.setattr(story,"advance_battle_to_policy_boundary",lambda *a,**k:None)
 def continue_battle(*args,**kwargs):
  learned.append(kwargs);state.raw.battle_state=0;state.dialogue=False;em.state=b"settled"
  before=state.raw.player_money
  if outcome=="won":
   flags=bytearray(state.raw.event_flags);e=int(scripted.EventFlag.BEAT_KARATE_MASTER)
   flags[e//8]|=1<<(e%8);state.raw.event_flags=bytes(flags);state.raw.player_money+=925
  else:state.raw.player_money//=2
  return N(outcome=outcome,field_ready=True,money_delta=state.raw.player_money-before,
   public_dict=lambda:dict(schema="pokemon.red.learned-trainer-completion.v1",outcome=outcome,field_ready=True,money_delta=state.raw.player_money-before))
 monkeypatch.setattr(story,"continue_learned_trainer_battle",continue_battle)
 binding=engaged.engaged_story_binding(rt,actions,rom=b"rom",battler=actor(tmp_path),
  objective_id="postgame_collection",allow_postgame_collection=True)
 return binding,state,controls,learned

@pytest.mark.parametrize("outcome",["won","lost"])
def test_bound_intro_uses_existing_controller_and_preserves_win_or_loss(monkeypatch,tmp_path,outcome):
 b,state,controls,learned=bound(monkeypatch,tmp_path,outcome=outcome)
 assert b.kind is GoalKind.RECOVER_CONTROL and not controls and not learned
 report=b.execute();verdict=b.verify(report)
 assert len(learned)==1 and learned[0]["trainer_identity"]==(224,24,1)and learned[0]["story_authority"]is True
 assert report.evidence["objective_completed"]is False and report.evidence["reward"]is None
 assert report.evidence["progress_objective"]=="postgame_collection"
 assert verdict.status is(GoalDecisionOutcome.SUCCEEDED if outcome=="won"else GoalDecisionOutcome.FAILED)
 if outcome=="lost":assert verdict.failure_reason is GoalFailureReason.RESOURCE_LOST

def test_exact_live_identity_still_checked_before_learned_combat(monkeypatch,tmp_path):
 b,state,controls,learned=bound(monkeypatch,tmp_path,wrong_live=True)
 with pytest.raises(ValueError,match="identity or event"):b.execute()
 assert controls and not learned

def test_intro_revalidated_before_any_new_input(monkeypatch,tmp_path):
 b,state,controls,learned=bound(monkeypatch,tmp_path)
 state.facing="left"
 with pytest.raises(ValueError,match="identity changed"):b.execute()
 assert not controls and not learned
