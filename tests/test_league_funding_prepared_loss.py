"""A funding loss must retain exactly its declared, validated opening swap."""
from dataclasses import replace
from types import SimpleNamespace as S
import pytest
from pokemon_red_completion.red_capture_lead import RedCaptureLeadPlan, RedCaptureLeadError
from pokemon_red_completion.red_league_funding_execution import run_retained_league_battle, RedLeagueFundingBattleLoss
from pokemon_red_completion.red_lorelei_story import LoreleiStoryBattleStopped
from test_league_funding_native_loss import fixture
from test_red_capture_lead import member, party

@pytest.mark.parametrize('index',range(6))
@pytest.mark.parametrize('duplicate',[False,True])
def test_exact_prepared_lead_swap_can_certify_native_loss(index,duplicate):
    ids=(28,114,167,125,166,28 if duplicate else 151)
    runtime,before,completion,doc,raw=fixture()
    before.party_species_ids=ids
    observed=party(*(member(i+1,species_id=s)for i,s in enumerate(ids)))
    runtime.adapter=S(observe=lambda:S(party=observed))
    runtime.reader.read=lambda:before
    expected=list(ids);expected[0],expected[index]=expected[index],expected[0]
    raw.party_species_ids=tuple(expected)
    original=LoreleiStoryBattleStopped('retained defeat_agatha outcome: lost')
    class Skill:
        prepared_lead_plan=RedCaptureLeadPlan(index,observed)
        def execute(self):
            runtime.reader.read=lambda:raw
            raise original
    with pytest.raises(RedLeagueFundingBattleLoss)as caught:
        run_retained_league_battle(runtime,Skill().execute,battle_owner=S(last_completion=completion),objective_id='defeat_agatha')
    assert caught.value.__cause__ is original
    assert caught.value.certificate['prepared_party_species_ids']==list(expected)
    assert caught.value.certificate['party_species_ids_before_preparation']==list(ids)

@pytest.mark.parametrize('damage',['wrong_swap','substitution','removal','duplicate_count','stale_party','wrong_type','raw_mismatch','no_plan'])
def test_unplanned_or_stale_roster_cannot_certify(damage):
    ids=(28,114,167,125,166,151)
    runtime,before,completion,doc,raw=fixture();before.party_species_ids=ids
    observed=party(*(member(i+1,species_id=s)for i,s in enumerate(ids)))
    runtime.adapter=S(observe=lambda:S(party=observed));runtime.reader.read=lambda:before
    raw.party_species_ids=(151,114,167,125,166,28)
    plan=RedCaptureLeadPlan(5,observed)
    if damage=='wrong_swap':raw.party_species_ids=(114,28,167,125,166,151)
    if damage=='substitution':raw.party_species_ids=(151,114,167,125,166,64)
    if damage=='removal':raw.party_species_ids=(151,114,167,125,166)
    if damage=='duplicate_count':raw.party_species_ids=(151,114,167,125,151,28)
    if damage=='stale_party':runtime.adapter=S(observe=lambda:S(party=replace(observed,members=(replace(observed.members[0],hp=49),*observed.members[1:]))))
    if damage=='wrong_type':plan=S(target_index=5,party=observed)
    if damage=='raw_mismatch':before.party_species_ids=(64,*ids[1:])
    if damage=='no_plan':plan=None
    original=LoreleiStoryBattleStopped('native loss');calls=[]
    class Skill:
        prepared_lead_plan=plan
        def execute(self):
            calls.append(True);runtime.reader.read=lambda:raw;raise original
    if damage in {'stale_party','wrong_type','raw_mismatch'}:
        with pytest.raises((ValueError,TypeError,RedCaptureLeadError)):
            run_retained_league_battle(runtime,Skill().execute,battle_owner=S(last_completion=completion),objective_id='defeat_agatha')
        assert not calls
    else:
        with pytest.raises(LoreleiStoryBattleStopped)as caught:
            run_retained_league_battle(runtime,Skill().execute,battle_owner=S(last_completion=completion),objective_id='defeat_agatha')
        assert caught.value is original

@pytest.mark.parametrize('champion',[False,True])
def test_story_skill_exposes_same_frozen_prepared_lead(champion):
    from pokemon_red_completion.red_champion_story import RedCartridgeChampionSkill
    from pokemon_red_completion.red_trainer_story import RedCartridgeLoreleiSkill
    cls=RedCartridgeChampionSkill if champion else RedCartridgeLoreleiSkill
    skill=object.__new__(cls);skill._prepared=None
    assert skill.prepared_lead_plan is None
    lead=object();prepared=S(lead=lead)
    skill._prepared=S(party=prepared)if champion else (object(),object(),prepared)
    assert skill.prepared_lead_plan is lead
