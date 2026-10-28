from dataclasses import replace
from collections import Counter
from types import SimpleNamespace as N
import pytest

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.red_machine_teaching import RedMachineLesson
import pokemon_red_completion.red_boxed_machine_options as module


def setup(monkeypatch, *, item=198, fault=None):
    original_refs=tuple('retained-'+str(i) for i in range(6))
    target_ref='observed-boxed-precursor'
    members={ref:N(ref=ref,species=28,level=30,experience=27000,
        moves=(70,39,145,57),pp=(15,30,30,15),status=0,hp=100) for ref in original_refs}
    members[target_ref]=N(ref=target_ref,species=88,level=18,experience=7290,
        moves=(35,43,86,97),pp=(16,30,20,30),status=0,hp=50)
    state=N(active=list(original_refs),box=[target_ref],items={item:2},
        map=89,x=3,y=3,money=25000,ready=True,epoch=0,inputs=[],repay_calls=0)
    em=N(frame_count=0,pressed_buttons=())
    em.save_state_bytes=lambda: str(state.epoch).encode()
    def pulse():
        state.epoch+=1;em.frame_count+=1
    actions=CountingExecutor(N(execute=lambda a:(state.inputs.append(a),pulse())))
    def raw():
        ms=[members[r] for r in state.active]
        return N(map_id=state.map,player_x=state.x,player_y=state.y,
            player_money=state.money,badge_bits=255,event_flags=b'flags',battle_state=0,
            party_count=len(ms),party_species_ids=tuple(m.species for m in ms),
            party_moves=tuple(m.moves for m in ms),party_pp=tuple(m.pp for m in ms),
            party_status=tuple(m.status for m in ms),party_hp=tuple(m.hp for m in ms),
            bag_items=tuple(sorted(state.items.items())))
    def identities():
        return tuple(N(preparation_ref=ref,species_id=members[ref].species,level=members[ref].level,
            experience=members[ref].experience,box_index=3,box_slot=i+1)
            for i,ref in enumerate(state.box))
    def box_moves(_):
        return tuple(N(box_slot=i+1,moves=members[r].moves,pp=members[r].pp)
                     for i,r in enumerate(state.box))
    reader=N(read=raw,read_all_box_states=lambda:N(counts=(0,0,0,len(state.box))),
        read_current_box_state=lambda:N(box_index=3),read_box_specimen_identities=identities,
        read_box_move_members=box_moves,read_pokedex_state=lambda:('owned-flags',),read_pc_items=lambda:())
    state_reader=reader
    class Guard:
        refs=original_refs
        loanable_refs=frozenset((original_refs[-1],))
        storage_reader=state_reader
        edges=frozenset(((88,89,30),))
        reader=N(preparation_specimen_refs=lambda:tuple(state.active))
        def verify(self):
            assert set(self.refs)<=set(state.active+state.box)
        def verify_active_roster_restored(self):
            self.verify();assert set(self.refs)<=set(state.active)
    guard=Guard()
    monkeypatch.setattr(module,'RedPlayerPartyGuard',Guard)
    runtime=N(reader=reader,emulator=em,adapter=N(party_guard=guard),
        registration_policy=N(evolution_allowed=lambda *a:True))
    observation=N(collection_observation=N(box_capacity=20))
    monkeypatch.setattr(module,'_field_ready',lambda _:state.ready and not em.pressed_buttons)
    def stock(_):
        return Counter((r,members[r].species,members[r].level,members[r].experience)
                       for r in state.active+state.box)
    monkeypatch.setattr(module,'_stock',stock)
    def quote(_rom,*,bag_items,species_id,moves,item_id,party_slot,replace_slot):
        if replace_slot not in (2,3) or species_id!=88 or item_id!=item:
            raise ValueError('incompatible')
        return RedMachineLesson(item_id,party_slot,replace_slot,species_id,moves,57)
    monkeypatch.setattr(module,'plan_observed_machine_lesson',quote)
    def actual(_rom,received,*,item_id,party_slot,replace_slot):
        assert received is reader
        member=members[state.active[party_slot-1]]
        return quote(_rom,bag_items=raw().bag_items,species_id=member.species,
            moves=member.moves,item_id=item_id,party_slot=party_slot,replace_slot=replace_slot)
    monkeypatch.setattr(module,'plan_machine_lesson',actual)
    def walk(_rt,_actions,_world,map_id,at):
        _actions.execute(MacroAction(MacroActionKind.WAIT));state.map=map_id;state.y,state.x=at
    monkeypatch.setattr(module,'_walk',walk)
    for name in ('face_pc_boundary','open_bills_pc','close_generic_pc_session'):
        monkeypatch.setattr(module,name,lambda *a,**k:None)
    def deposit(_actions,_reader,*,party_slot,expected_species_id):
        assert members[state.active[party_slot-1]].species==expected_species_id
        _actions.execute(MacroAction(MacroActionKind.WAIT))
        state.box.append(state.active.pop(party_slot-1));return N(passed=True)
    def withdraw(_actions,_reader,*,box_slot,expected_species_id):
        assert members[state.box[box_slot-1]].species==expected_species_id
        _actions.execute(MacroAction(MacroActionKind.WAIT))
        state.active.append(state.box.pop(box_slot-1));return N(passed=True)
    monkeypatch.setattr(module,'deposit_party_member',deposit)
    monkeypatch.setattr(module,'withdraw_box_member',withdraw)
    def teach(_em,_actions,_reader,lesson,*,rom):
        _actions.execute(MacroAction(MacroActionKind.WAIT))
        if fault=='input':raise RuntimeError('native teaching failure')
        m=members[state.active[lesson.party_slot-1]];moves=list(m.moves);pp=list(m.pp)
        moves[lesson.replace_slot-1]=57;pp[lesson.replace_slot-1]=15
        m.moves,m.pp=tuple(moves),tuple(pp)
        if item>=201:state.items[item]-=1
        if fault=='cash':state.money-=1
        if fault=='xp':m.experience+=1
        if fault=='original_pp':members[original_refs[0]].pp=(14,30,30,15)
    monkeypatch.setattr(module,'execute_machine_lesson',teach)
    def repay(_rt,_actions,_world):
        state.repay_calls+=1
        if fault=='settlement':raise RuntimeError('native return failure')
        _actions.execute(MacroAction(MacroActionKind.WAIT))
        if target_ref in state.active:state.active.remove(target_ref);state.box.append(target_ref)
        if original_refs[-1] in state.box:state.box.remove(original_refs[-1]);state.active.append(original_refs[-1])
        return True
    monkeypatch.setattr(module,'restore_guarded_party_loan',repay)
    return runtime,actions,observation,state,members


def test_discovery_has_no_inputs_and_exposes_distinct_model_bundles(monkeypatch):
    rt,actions,observation,state,_=setup(monkeypatch)
    rows=module.boxed_frontier_machine_options(rt,actions,observation,rom=b'fixture',world=N())
    assert len(rows)==2 and not state.inputs and rt.emulator.save_state_bytes()==b'0'
    assert len({r.binding.binding_ref for r in rows})==2
    assert all(r.candidate.features.completion_gain==0 for r in rows)
    assert all(r.binding.maximum_cash_debit==0 for r in rows)


@pytest.mark.parametrize('item,consumed',[(198,0),(211,1)])
def test_selected_native_lesson_repays_the_declared_loan(monkeypatch,item,consumed):
    rt,actions,observation,state,members=setup(monkeypatch,item=item)
    row=module.boxed_frontier_machine_options(rt,actions,observation,rom=b'fixture',world=N())[0]
    report=row.binding.execute()
    assert row.binding.verify(report).status.value=='succeeded'
    assert report.evidence['machine_consumed']==consumed
    assert report.evidence['xp_gained']==report.evidence['registrations_gained']==0
    assert state.items[item]==2-consumed and state.repay_calls==1
    assert 'observed-boxed-precursor' in state.box
    assert members['observed-boxed-precursor'].moves==(35,57,86,97)
    assert actions.actions_executed>0
    before=actions.actions_executed
    with pytest.raises(ValueError,match='stale or consumed'):row.binding.execute()
    assert actions.actions_executed==before


@pytest.mark.parametrize('fault',['cash','xp','original_pp','input','settlement'])
def test_failure_keeps_attempts_and_never_reuses_the_bundle(monkeypatch,fault):
    rt,actions,observation,state,_=setup(monkeypatch,fault=fault)
    row=module.boxed_frontier_machine_options(rt,actions,observation,rom=b'fixture',world=N())[0]
    with pytest.raises(RuntimeError):row.binding.execute()
    count=actions.actions_executed
    assert count>0 and state.repay_calls==1
    with pytest.raises(ValueError):row.binding.execute()
    assert actions.actions_executed==count


@pytest.mark.parametrize('fault',['outside','not_ready','no_loan','no_frontier','full_box','ambiguous'])
def test_unproved_boxed_readiness_never_admits_a_bundle(monkeypatch,fault):
    rt,actions,observation,state,_=setup(monkeypatch)
    if fault=='outside':state.map=0
    elif fault=='not_ready':state.ready=False
    elif fault=='no_loan':rt.adapter.party_guard.loanable_refs=frozenset()
    elif fault=='no_frontier':rt.registration_policy.evolution_allowed=lambda *a:False
    elif fault=='full_box':observation.collection_observation.box_capacity=1
    else:state.box.append(state.box[0])
    assert module.boxed_frontier_machine_options(rt,actions,observation,rom=b'fixture',world=N())==()
    assert not state.inputs


def test_stale_native_source_cannot_spend_an_input(monkeypatch):
    rt,actions,observation,state,_=setup(monkeypatch)
    row=module.boxed_frontier_machine_options(rt,actions,observation,rom=b'fixture',world=N())[0]
    state.epoch+=1
    with pytest.raises(ValueError,match='stale'):row.binding.execute()
    assert not state.inputs
