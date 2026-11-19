from dataclasses import replace
from types import SimpleNamespace as N
import pytest
from pokemon_red_completion import red_team_training as module
from pokemon_red_completion.party import PartyObservation,PartyMemberObservation,MoveObservation


def fixture(monkeypatch,fault=None):
    target=PartyMemberObservation(1,59,44,0,62,experience=85184,moves=(MoveObservation(91,8,10),))
    helper=PartyMemberObservation(2,28,51,100,144,experience=132999,moves=(MoveObservation(57,12,15),))
    state=N(party=PartyObservation((target,helper)),raw=N(battle_state=0,map_id=197,player_money=1234,bag_items=((4,3),)),ready=True,refs=('target','helper'))
    calls=[];events=[]
    class Reader:
        def __init__(self,em):pass
        def read(self):return state.party
        def preparation_specimen_refs(self):return state.refs
    monkeypatch.setattr(module,'PokemonRedPartyReader',Reader)
    def heal(*args):
        calls.append('heal');state.party=replace(state.party,members=tuple(replace(m,hp=m.max_hp)for m in state.party.members))
        if fault=='XP':state.party=replace(state.party,members=(replace(state.party.members[0],experience=85185),state.party.members[1]))
        if fault=='identity':state.party=replace(state.party,members=(replace(state.party.members[0],species_id=60),state.party.members[1]))
        if fault=='moves':state.party=replace(state.party,members=(replace(state.party.members[0],moves=()),state.party.members[1]))
        if fault=='cash':state.raw.player_money-=1
        if fault=='bag':state.raw.bag_items=()
        if fault=='map':state.raw.map_id=198
        if fault=='still_fainted':state.party=PartyObservation((target,helper))
        if fault=='unsettled':state.ready=False
    def metered(healer,reader,em):calls.append('meter');healer(None,reader,em)
    actions=N(execute_training_healing=metered,record_diagnostic_event=lambda kind,data:events.append((kind,data)))
    reader=N(read=lambda:state.raw,read_input_readiness=lambda:N(ready=state.ready))
    run=lambda:module.recover_completed_collection_training_faint(actions,reader,object(),recipient_species_id=59,heal_and_return=heal)
    return state,calls,events,run


def test_completed_wild_faint_uses_native_metered_healing_without_inventing_XP(monkeypatch):
    state,calls,events,run=fixture(monkeypatch);run()
    assert calls==['meter','heal']
    assert [(m.species_id,m.experience)for m in state.party.members]==[(59,85184),(28,132999)]
    assert not state.party.fainted_count
    assert [x[0]for x in events]==['wild_training_completed_faint','wild_training_completed_faint_recovery']
    assert all(x[1]['observed_faints']==1 and x[1]['training_win_inferred']is False for x in events)
    assert events[-1][1]['XP_change_during_recovery']==0


@pytest.mark.parametrize('fault',['XP','identity','moves','cash','bag','map','still_fainted','unsettled'])
def test_postbattle_recovery_drift_or_unsafe_terminal_stays_failure(monkeypatch,fault):
    state,calls,events,run=fixture(monkeypatch,fault)
    with pytest.raises(RuntimeError):run()
    assert calls==['meter','heal']
    assert not any(k=='wild_training_completed_faint_recovery'for k,d in events)


@pytest.mark.parametrize('fault',['wild','trainer','unready','no_faint','all_fainted','unknown_XP','duplicate_refs','missing_target'])
def test_unknown_or_unsettled_postbattle_faint_issues_no_inputs(monkeypatch,fault):
    state,calls,events,run=fixture(monkeypatch)
    if fault=='wild':state.raw.battle_state=1
    if fault=='trainer':state.raw.battle_state=2
    if fault=='unready':state.ready=False
    if fault=='no_faint':state.party=replace(state.party,members=tuple(replace(m,hp=10)for m in state.party.members))
    if fault=='all_fainted':state.party=replace(state.party,members=tuple(replace(m,hp=0)for m in state.party.members))
    if fault=='unknown_XP':state.party=replace(state.party,members=(replace(state.party.members[0],experience=None),state.party.members[1]))
    if fault=='duplicate_refs':state.refs=('same','same')
    if fault=='missing_target':state.party=replace(state.party,members=(replace(state.party.members[0],species_id=60),state.party.members[1]))
    with pytest.raises(RuntimeError):run()
    assert not calls and not events
