import copy
from dataclasses import replace
from types import SimpleNamespace
import pytest
from test_story_unit_v16 import candidate,context
from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion.player_option_story_unit import OptionStoryUnit
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionMenu,LivingDexOptionUtility,LivingDexPredictedOutcome,
    _score_with_income_saturation)
from pokemon_red_completion.living_dex_policy_codec import restore_living_dex_policy_menu
from pokemon_red_completion.red_movement_recurrence import (
    movement_boundary,observe_movement_boundary,menu_with_movement_history)

def facts():
    return dict(cash=100,owned_species=['a'],specimen_counts={'a':1},
        completed_objectives=['start'],movement_event_flags='0001',movement_coins=0,
        diagnostics=dict(map_id=3,player_y=2,player_x=1,bag_items=[[4,2]],badge_bits=1),
        player_lesson=dict(party=[dict(specimen_ref='private',species_id=7,level=12,
            experience=100,hp=20,max_hp=30,status='none',moves=[[1,5]])]),
        frames=10,actions=2,raw_state_sha256='a'*64,budget=99)

def test_only_observed_endpoints_visited_and_checkpoint_preserves_them():
    f=facts();memory=GoalSearchMemory();a=observe_movement_boundary(memory,f)
    assert a and memory.movement_endpoint_seen(*a)
    other=copy.deepcopy(f);other['diagnostics']['map_id']=65;b=movement_boundary(other)
    assert a[1]==b[1]and a[0]!=b[0]and not memory.movement_endpoint_seen(*b)
    restored=GoalSearchMemory.from_private_dict(memory.private_dict());restored.require_extension(memory)
    assert restored.movement_endpoint_seen(*a)
    with pytest.raises(ValueError,match='lost an observation'):
        GoalSearchMemory().require_extension(restored)

@pytest.mark.parametrize('field',['cash','owned_species','completed_objectives','specimen_counts','movement_event_flags','bag','badge','xp','hp','pp','roster'])
def test_real_progress_or_resources_reopen_an_endpoint(field):
    f=facts();old=movement_boundary(f)
    if field=='cash':f['cash']+=1
    elif field=='owned_species':f[field].append('b')
    elif field=='completed_objectives':f[field].append('trainer')
    elif field=='specimen_counts':f[field]['b']=1
    elif field=='movement_event_flags':f[field]='0101'
    elif field=='bag':f['diagnostics']['bag_items']=[[4,1]]
    elif field=='badge':f['diagnostics']['badge_bits']=3
    elif field=='xp':f['player_lesson']['party'][0]['experience']+=1
    elif field=='hp':f['player_lesson']['party'][0]['hp']+=1
    elif field=='pp':f['player_lesson']['party'][0]['moves'][0][1]+=1
    else:f['player_lesson']['party'][0]['specimen_ref']='other'
    assert movement_boundary(f)[0]==old[0]and movement_boundary(f)[1]!=old[1]

def test_rng_time_actions_and_budget_do_not_fabricate_progress():
    f=facts();old=movement_boundary(f)
    f.update(frames=100,actions=999,raw_state_sha256='b'*64,budget=3)
    assert movement_boundary(f)==old

@pytest.mark.parametrize('missing',['movement_event_flags','player_lesson','diagnostics','cash'])
def test_unknown_history_is_not_certified_repeat(missing):
    f=facts();del f[missing];assert movement_boundary(f)is None

@pytest.mark.parametrize('unit',[None,OptionStoryUnit('interaction',True),OptionStoryUnit('movement',False),OptionStoryUnit('movement',True)])
@pytest.mark.parametrize('revisit',[None,False,True])
def test_saturation_changes_only_known_noncompleting_repeat_utility(unit,revisit):
    c=replace(candidate(),story_unit=unit,movement_revisit=revisit)
    utility=LivingDexOptionUtility(4,3,2,1,1,1,1,1,4);prediction=LivingDexPredictedOutcome.from_vector([.8,.1,.2,.3,.4,.2,.1,.1,.1])
    score,_,_=_score_with_income_saturation(context(),c,utility,prediction)
    expected=utility.score(prediction)
    if revisit is True and unit==OptionStoryUnit('movement',True):expected-=utility.success_weight*.8
    assert score==pytest.approx(expected)
    assert prediction.verified_success==.8

def test_new_metadata_roundtrips_without_identity_or_feature_change():
    old=replace(candidate(),story_unit=OptionStoryUnit('movement',True))
    new=replace(old,movement_revisit=True)
    assert old.vector(context(),feature_version=16)==new.vector(context(),feature_version=16)
    menu=LivingDexOptionMenu(context(),(new,replace(old,binding_ref='other')))
    doc=menu.policy_dict();assert 'private-id'not in str(doc)
    assert restore_living_dex_policy_menu(doc).policy_dict()==doc
    with pytest.raises(ValueError):replace(new,movement_revisit=1)

def test_public_menu_does_not_mark_a_quoted_future_as_visited():
    from pokemon_red_completion.red_live_option_menu import RedLiveOptionSet
    # The adapter only needs frozen bindings beside the unchanged typed menu.
    from dataclasses import dataclass
    @dataclass(frozen=True)
    class Options:
        menu:object
        bindings:tuple
    f=facts();mem=GoalSearchMemory();current=movement_boundary(f)
    future=copy.deepcopy(f);future['diagnostics']['map_id']=65;end=movement_boundary(future)
    c=replace(candidate(),story_unit=OptionStoryUnit('movement',True))
    binds=(SimpleNamespace(movement_endpoint_sha256=current[0],story_unit=c.story_unit),
           SimpleNamespace(movement_endpoint_sha256=end[0],story_unit=c.story_unit))
    options=Options(LivingDexOptionMenu(context(),(c,replace(c,binding_ref='other'))),binds)
    result=menu_with_movement_history(options,mem,f)
    assert [c.movement_revisit for c in result.menu.candidates]==[True,False]
    assert result.bindings is options.bindings
    assert not mem.movement_endpoint_seen(*end)

@pytest.mark.parametrize('field',['cash','bag','party','coins','badge','xp','pp'])
def test_null_physical_values_do_not_certify_recurrence(field):
    f=facts()
    if field=='cash':f['cash']=None
    elif field=='bag':f['diagnostics']['bag_items']=None
    elif field=='party':f['player_lesson']['party']=None
    elif field=='coins':f['movement_coins']=None
    elif field=='badge':f['diagnostics']['badge_bits']=None
    elif field=='xp':f['player_lesson']['party'][0]['experience']=None
    else:f['player_lesson']['party'][0]['moves'][0][1]=None
    assert movement_boundary(f)is None

def test_coin_progress_reopens_destination_without_wallet_or_bag_change():
    f=facts();old=movement_boundary(f);f['movement_coins']=50
    assert movement_boundary(f)[1]!=old[1]

@pytest.mark.parametrize('flag',[False,True])
def test_fresh_and_configured_shared_wiring_retains_policy_identity(flag):
    import run_configured_red_player as configured
    import run_fresh_red_player as fresh
    assert fresh.execute_player_chunk is configured.execute_player_chunk
    plan=dict(partition='development',movement_revisit_saturation=flag)
    assert configured.player_wiring_declaration(plan)['movement_revisit_saturation']is flag
    assert 'movement_revisit_saturation'in configured.PLAYER_WIRING_FIELDS

@pytest.mark.parametrize('flag',[1,'true',None])
def test_policy_identity_rejects_coerced_or_unknown_flag(flag):
    import run_configured_red_player as configured
    with pytest.raises(ValueError,match='movement recurrence'):
        configured.player_wiring_declaration(dict(partition='development',movement_revisit_saturation=flag))
