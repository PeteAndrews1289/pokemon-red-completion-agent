from dataclasses import replace
from types import SimpleNamespace as N
import json

import pytest
import pokemon_red_completion.red_field_carrier as mod
import pokemon_red_completion.red_player_party_loan as loan
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.party import PartyMemberObservation, PartyObservation, MoveObservation
from pokemon_red_completion.party_preparation import PreparationMember, PreparationPurpose, build_preparation_plan
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_field_carrier_custody import FieldCarrierCustody, active_carrier_preparation, settle_pending_field_carrier
from pokemon_red_completion.red_machine_teaching import RedMachineLesson
from pokemon_red_completion.red_player_party_guard import RedPlayerPartyGuard, retained_party_slot_is_depositable
from pokemon_red_completion.private_artifacts import validate_private_record


def case(monkeypatch, *, fault=None, known=False):
    refs = tuple('original-'+str(i) for i in range(6))
    target = 'owned-carrier'
    state = N(active=list(refs), box=[target], epoch=0, money=751, map=89, y=3,x=3,
              fault=fault, completed=set(), legal={'defeat_surge'}, bag=((196,1),), ready=True,pc_open=False)
    mons = {r: N(species=28+i, level=30, xp=27000, moves=(33,39,45,0), pp=(35,30,40,0)) for i,r in enumerate(refs)}
    mons[refs[0]].moves, mons[refs[0]].pp = (57,33,39,0),(15,35,30,0)
    mons[target] = N(species=88,level=18,xp=7290,moves=(15,43,0,0) if known else (35,43,0,0),pp=(30,30,0,0) if known else (20,30,0,0))
    def member(r,i):
        m=mons[r]
        return PartyMemberObservation(i,m.species,m.level,50,50,experience=m.xp,
            moves=tuple(MoveObservation(a,b) for a,b in zip(m.moves,m.pp) if a))
    party_reader=N(read=lambda:PartyObservation(tuple(member(r,i) for i,r in enumerate(state.active,1))),
                   preparation_specimen_refs=lambda:tuple(state.active))
    def identities():
        return tuple(N(preparation_ref=r,species_id=mons[r].species,level=mons[r].level,
                       experience=mons[r].xp,box_index=0,box_slot=i) for i,r in enumerate(state.box,1))
    def raw():
        ms=[mons[r] for r in state.active]
        return N(map_id=state.map,player_y=state.y,player_x=state.x,player_money=state.money,
                 party_count=len(ms),party_species_ids=tuple(m.species for m in ms),
                 party_moves=tuple(m.moves for m in ms),party_pp=tuple(m.pp for m in ms),
                 party_hp=(50,)*len(ms),party_status=(0,)*len(ms),bag_items=state.bag,
                 battle_state=0,badge_bits=3,event_flags=b'facts',game_started=True)
    reader=N(read=raw,read_box_specimen_identities=identities,
             read_all_box_states=lambda:N(counts=(len(state.box),)),read_current_box_state=lambda:N(box_index=0),
             read_box_move_members=lambda _:tuple(N(box_slot=i,moves=mons[r].moves,pp=mons[r].pp) for i,r in enumerate(state.box,1)),
             read_pokedex_state=lambda:('owned',),read_pc_items=lambda:(),
             read_bottom_dialogue_box_visible=lambda:False,read_input_readiness=lambda:N(ready=state.ready),
             read_generic_pc_session_active=lambda:state.pc_open)
    original=party_reader.read()
    guard=RedPlayerPartyGuard(party_reader,original,refs,frozenset(),reader,frozenset({refs[0]}))
    em=N(frame_count=0,pressed_buttons=(),save_state_bytes=lambda:str(state.epoch).encode())
    observation=N(game_state=None,collection_observation=N(box_capacity=20,box_counts=(1,),owned_species=frozenset(m.species for m in mons.values())))
    graph=N(available_objectives=lambda _: tuple(N(id=o) for o in state.legal-state.completed),completed_ids=lambda _:state.completed)
    runtime=N(reader=reader,emulator=em,adapter=N(party_guard=guard,graph=graph,
        observe=lambda:N(**vars(observation),raw=raw(),input_ready=state.ready)))
    def input(_):
        state.epoch+=1;em.frame_count+=1
    actions=CountingExecutor(N(execute=input))
    def pulse():actions.execute(MacroAction(MacroActionKind.WAIT))
    def walk(_rt,_actions,_world,map_id,at,**kw):
        pulse();state.map=map_id;state.y,state.x=at
    def deposit(_a,_r,*,party_slot,expected_species_id):
        assert mons[state.active[party_slot-1]].species==expected_species_id
        pulse();state.box.append(state.active.pop(party_slot-1));return N(passed=True)
    def withdraw(_a,_r,*,box_slot,expected_species_id):
        r=state.box[box_slot-1]
        if (state.fault in {'withdraw','both'} and r==target) or (state.fault=='both' and r!=target):
            raise RuntimeError('native withdrawal failure: '+r)
        pulse();state.active.append(state.box.pop(box_slot-1));return N(passed=True)
    def quote(_rom,*,bag_items,species_id,moves,item_id,party_slot,replace_slot):
        if species_id!=88 or replace_slot!=3 or item_id!=196 or 15 in moves or not dict(bag_items).get(196):
            raise ValueError('incompatible')
        return RedMachineLesson(item_id,party_slot,replace_slot,species_id,moves,15)
    def actual(_rom,_reader,**kw):
        m=mons[state.active[kw['party_slot']-1]]
        return quote(_rom,bag_items=raw().bag_items,species_id=m.species,moves=m.moves,**kw)
    def teach(_em,_a,_reader,lesson,**kw):
        pulse()
        if state.fault=='teach':raise RuntimeError('native teaching failure')
        m=mons[target];moves=list(m.moves);pps=list(m.pp);moves[lesson.replace_slot-1]=15;pps[lesson.replace_slot-1]=30
        m.moves,m.pp=tuple(moves),tuple(pps)
        if state.fault=='cash':state.money-=1
    for name,fn in [('deposit_party_member',deposit),('withdraw_box_member',withdraw),('_walk',walk)]:
        monkeypatch.setattr(mod,name,fn);monkeypatch.setattr(loan,name,fn)
    for m in (mod,loan):
        for name in ('face_pc_boundary','open_bills_pc','close_generic_pc_session'):
            monkeypatch.setattr(m,name,lambda *a,**k:None)
    def face(*a,**k):assert not state.pc_open
    def open_pc(*a,**k):
        assert not state.pc_open;state.pc_open=True
    def close_pc(*a,**k):state.pc_open=False
    import pokemon_red_completion.red_pc_storage as pc
    for m in (mod,loan):
        monkeypatch.setattr(m,'face_pc_boundary',face)
        monkeypatch.setattr(m,'open_bills_pc',open_pc)
        monkeypatch.setattr(m,'close_generic_pc_session',close_pc)
    monkeypatch.setattr(pc,'close_generic_pc_session',close_pc)
    monkeypatch.setattr(loan,'_reach_center',lambda *a,**kw:None)
    monkeypatch.setattr(mod,'_field_ready',lambda _:state.ready)
    monkeypatch.setattr(mod,'nearest_reachable_player_center',lambda *a,**k:89)
    from pokemon_red_completion.red_field_capability_demand import CutDependencyWitness
    monkeypatch.setattr(mod,'observed_cut_dependencies',lambda rt,obs,**kw:tuple(
        CutDependencyWitness(o.id,92,'a'*64,1)for o in rt.adapter.graph.available_objectives(obs.game_state)))
    monkeypatch.setattr(mod,'plan_observed_machine_lesson',quote)
    monkeypatch.setattr(mod,'plan_machine_lesson',actual)
    monkeypatch.setattr(mod,'execute_machine_lesson',teach)
    plan=build_preparation_plan(tuple(PreparationMember(r,m,PreparationPurpose.COMBAT,'declared combat') if i==0
        else PreparationMember(r,m) for i,(r,m) in enumerate(zip(refs,original.members))),())
    return N(state=state,mons=mons,refs=refs,target=target,runtime=runtime,guard=guard,actions=actions,
             observation=observation,route=N(route_world=object()),plan=plan)


def branches(c,**kw):
    return mod.field_carrier_branches(c.runtime,c.actions,c.observation,rom=b'rom',route=c.route,
        combat_refs=frozenset({c.refs[0]}),preparation=c.plan,**kw)


def test_options_exclude_combat_and_preserve_field_transport_without_inputs(monkeypatch):
    c=case(monkeypatch);rows=branches(c)
    assert len(rows)==5 and c.actions.actions_executed==0
    assert all(b.maximum_cash_debit is None and b.story_unit.mode=='interaction' for b,_ in rows)
    assert all(b.story_approach_only for b,_ in rows)
    assert c.runtime.emulator.save_state_bytes()==b'0'


@pytest.mark.parametrize('known',[False,True])
def test_selected_carrier_remains_active_with_exact_original_baseline_and_usable_cut(monkeypatch,known):
    c=case(monkeypatch,known=known);saved=[]
    b=branches(c,on_commit=saved.append)[0][0]
    report=b.execute()
    assert b.verify(report).status.value=='succeeded'
    guard=c.runtime.adapter.party_guard;custody=guard.field_carrier
    assert custody.phase=='active' and c.target in c.state.active and custody.displaced_ref in c.state.box
    assert c.refs[0] in c.state.active and custody.displaced_ref!=c.refs[0]
    assert guard.before==c.guard.before and guard.refs==c.guard.refs
    assert report.evidence['objective_completed'] is False and not c.state.completed
    guard.verify_authorized_active_roster()
    with pytest.raises(ValueError,match='not been restored'):guard.verify_active_roster_restored()
    assert loan.party_loan_return_binding(c.runtime,c.actions,c.route.route_world) is None
    assert all(not retained_party_slot_is_depositable(c.runtime.adapter,i) for i in range(1,7))
    record=json.loads(json.dumps(custody.private_dict()))
    validate_private_record(record)
    assert FieldCarrierCustody.from_private_dict(record)==custody
    view=active_carrier_preparation(c.plan,c.runtime,custody)
    assert next(m for m in view.roster if m.specimen_ref==c.target).purpose is PreparationPurpose.FIELD_UTILITY
    assert next(m for m in view.roster if m.specimen_ref==c.refs[0]).purpose is PreparationPurpose.COMBAT
    assert custody.preparation_before==c.plan and saved==[custody]
    with pytest.raises(ValueError,match='stale or consumed'):b.execute()


@pytest.mark.parametrize('fault',['withdraw','teach','cash'])
def test_failure_repays_exact_originals_and_preserves_primary_error(monkeypatch,fault):
    c=case(monkeypatch,fault=fault);b=branches(c)[0][0]
    with pytest.raises((RuntimeError,ValueError)) as exc:b.execute()
    assert 'native' in str(exc.value) or 'protected' in str(exc.value)
    assert set(c.state.active)==set(c.refs) and c.target in c.state.box
    assert c.runtime.adapter.party_guard.field_carrier is None
    c.runtime.adapter.party_guard.verify_active_roster_restored()
    assert c.actions.actions_executed>0


def test_failed_settlement_retains_both_errors_and_pending_custody_for_later_recovery(monkeypatch):
    c=case(monkeypatch,fault='both');b=branches(c)[0][0]
    with pytest.raises(mod.FieldCarrierSettlementError) as exc:b.execute()
    assert isinstance(exc.value.__cause__,RuntimeError)
    from pokemon_red_completion.red_autonomous_player import _exception_chain
    chain=_exception_chain(exc.value)
    assert c.target in chain[1]['error']
    assert 'original-1' in chain[0]['settlement_error_chain'][0]['error']
    pending=c.runtime.adapter.party_guard.field_carrier
    assert pending.phase=='pending' and pending.displaced_ref in c.state.box
    assert FieldCarrierCustody.from_private_dict(json.loads(json.dumps(pending.private_dict())))==pending
    c.runtime.adapter.party_guard.verify()
    c.state.fault=None
    binding=loan.party_loan_return_binding(c.runtime,c.actions,c.route.route_world)
    assert binding is not None
    report=binding.execute()
    assert binding.verify(report).status.value=='succeeded'
    assert set(c.state.active)==set(c.refs) and c.runtime.adapter.party_guard.field_carrier is None


@pytest.mark.parametrize('mutation',['missing','duplicate','xp','cut','baseline'])
def test_committed_custody_fails_closed_on_tampering(monkeypatch,mutation):
    c=case(monkeypatch);branches(c)[0][0].execute();g=c.runtime.adapter.party_guard
    if mutation=='missing':c.state.active.remove(c.target)
    if mutation=='duplicate':c.state.box.append(c.target)
    if mutation=='xp':c.mons[c.target].xp-=1
    if mutation=='cut':c.mons[c.target].moves=(35,43,0,0)
    if mutation=='baseline':g=replace(g,refs=tuple(reversed(g.refs)))
    with pytest.raises(ValueError):g.verify_authorized_active_roster()


@pytest.mark.parametrize('reason',['full','no_hm','no_need','incompatible','field_transport','combat_only'])
def test_missing_evidence_or_unsafe_exchange_produces_no_offer(monkeypatch,reason):
    c=case(monkeypatch)
    if reason=='full':c.observation.collection_observation.box_capacity=1
    if reason=='no_hm':c.state.bag=()
    if reason=='no_need':c.runtime.adapter.graph.available_objectives=lambda _ : ()
    if reason=='incompatible':c.mons[c.target].species=99
    if reason=='field_transport':
        c.mons[c.refs[1]].moves=(19,33,0,0)
        # Some donors remain eligible; verify the unique Fly holder is never borrowed.
        for b,_ in branches(c):
            report=b.execute();assert c.refs[1] in c.state.active
            return
        pytest.fail('expected at least one eligible donor preserving the unique Fly holder')
    if reason=='combat_only':
        assert not mod.field_carrier_branches(c.runtime,c.actions,c.observation,rom=b'rom',route=c.route,
            combat_refs=frozenset(c.refs),preparation=c.plan)
        return
    assert not branches(c)


def test_return_is_separately_selected_only_after_dependency_completion(monkeypatch):
    c=case(monkeypatch);branches(c)[0][0].execute()
    assert mod.field_carrier_return_binding(c.runtime,c.actions,route=c.route) is None
    c.state.completed.add('defeat_surge')
    b=mod.field_carrier_return_binding(c.runtime,c.actions,route=c.route)
    assert b.kind.value=='manage_storage'
    report=b.execute();assert b.verify(report).status.value=='succeeded'
    assert set(c.state.active)==set(c.refs)


@pytest.mark.parametrize('phase',['active','pending'])
@pytest.mark.parametrize('plain_adapter',[False,True])
def test_custody_checkpoint_restores_into_original_source_runtime_without_inputs(monkeypatch,phase,plain_adapter):
    import pokemon_red_completion.red_player_continuation as cont
    import pokemon_red_completion.red_party as party
    import pokemon_red_completion.red_trainer_evolution as evo
    import pokemon_red_completion.rom as rom
    c=case(monkeypatch,fault='both' if phase=='pending' else None)
    if phase=='pending':
        with pytest.raises(mod.FieldCarrierSettlementError):branches(c)[0][0].execute()
        plan=c.plan
    else:
        branches(c)[0][0].execute()
        plan=active_carrier_preparation(c.plan,c.runtime,c.runtime.adapter.party_guard.field_carrier)
    expected=c.runtime.adapter.party_guard.field_carrier
    def snapshot(_):
        return N(raw=c.runtime.reader.read()),dict(completed_objectives=[],party=[dict(ref=r) for r in c.state.active])
    monkeypatch.setattr(cont,'capture_player_lesson_snapshot',snapshot)
    monkeypatch.setattr(cont,'PokemonRedPartyReader',lambda _:c.guard.reader)
    monkeypatch.setattr(party,'PokemonRedPartyReader',lambda _:c.guard.reader)
    monkeypatch.setattr(evo,'level_evolution_edges',lambda _:frozenset())
    monkeypatch.setattr(rom,'verify_rom_bytes',lambda _:None)
    c.runtime.observer=N(latch_verified_facts=lambda _:None)
    costs=dict(decisions=425,actions=247893,frames=20235037,seconds=3454.86,heals=240,cash_debits=15479)
    doc=cont.capture_player_continuation(c.runtime,preparation=plan,battle=None,spent=costs)
    c.runtime.adapter.party_guard=c.guard
    if plain_adapter:
        from dataclasses import dataclass
        @dataclass(slots=True)
        class PlainAdapter:
            graph: object
            observe: object
        c.runtime.adapter=PlainAdapter(c.runtime.adapter.graph,c.runtime.adapter.observe)
    before=c.runtime.emulator.save_state_bytes();actions=c.actions.actions_executed
    restored=cont.restore_player_continuation(c.runtime,json.loads(json.dumps(doc)),expected_sha256=canonical_sha256(doc),
        evolution_rom=b'rom',loanable_refs=c.guard.loanable_refs)
    assert restored.field_carrier==expected and restored.spent==costs
    if not plain_adapter:
        assert c.runtime.adapter.party_guard.field_carrier==expected
        c.runtime.adapter.party_guard.verify()
    assert before==c.runtime.emulator.save_state_bytes() and actions==c.actions.actions_executed


def test_preparation_callback_failure_does_not_commit_or_lose_original_roster(monkeypatch):
    c=case(monkeypatch)
    def fail(_):raise ValueError('preparation view invalid')
    b=branches(c,on_commit=fail)[0][0]
    with pytest.raises(ValueError,match='preparation view invalid'):b.execute()
    assert set(c.state.active)==set(c.refs) and c.runtime.adapter.party_guard.field_carrier is None


def test_displaced_original_moves_are_reobserved_before_commit(monkeypatch):
    c=case(monkeypatch)
    old=mod.withdraw_box_member
    def corrupt(*a,**kw):
        result=old(*a,**kw)
        c.mons[c.refs[1]].pp=(1,30,40,0)
        return result
    monkeypatch.setattr(mod,'withdraw_box_member',corrupt)
    with pytest.raises(ValueError,match='protected stock'):branches(c)[0][0].execute()
    assert c.runtime.adapter.party_guard.field_carrier is None


def test_center_quote_uses_real_route_helper_integer_inventory_contract(monkeypatch):
    import pokemon_red_completion.red_player_field_goals as fields
    c=case(monkeypatch)
    monkeypatch.setattr(mod,'nearest_reachable_player_center',fields.nearest_reachable_player_center)
    monkeypatch.setattr(fields,'_field_ready',lambda _:False)
    assert branches(c)==()  # Valid inventory reaches field-readiness guard, without route/input.
    assert c.actions.actions_executed==0


@pytest.mark.parametrize('level',[10,18])
def test_selected_field_purpose_does_not_create_optional_combat_training(monkeypatch,level):
    from pokemon_red_completion.red_player_member_preparation import member_preparation_plans
    c=case(monkeypatch);c.mons[c.target].level=level;c.mons[c.target].xp=level**3
    branches(c)[0][0].execute()
    custody=c.runtime.adapter.party_guard.field_carrier
    plan=active_carrier_preparation(c.plan,c.runtime,custody)
    def offers(p):
        return member_preparation_plans(p,p.roster,opponent_levels=(24,),forecast_ref='observed-opponent',
            cartridge=N(species=lambda _:N(experience_at_level=lambda l:l**3)),evolutions={})
    assert offers(plan)==()
    undecided=replace(plan,roster=tuple(replace(m,purpose=PreparationPurpose.UNDECIDED,purpose_reason='')
        if m.specimen_ref==c.target else m for m in plan.roster))
    assert offers(undecided)  # Same inventory/opposition;the incorrect prior role creates work.


def test_existing_exact_cut_receipt_is_retained_in_existing_private_diagnostics():
    from pokemon_red_completion.red_training_ground_route import record_verified_field_cuts
    from pokemon_red_completion.gen1_field_moves import Gen1CutReceipt
    events=[]
    receipt=Gen1CutReceipt(5,(9,8),(9,9),'right',5,1,1,61,61,(4,4),7,9)
    actions=N(record_diagnostic_event=lambda kind,payload:events.append((kind,payload)))
    record_verified_field_cuts(actions,N(cut_receipts=[receipt]))
    assert len(events)==1 and events[0][0]=='native_verified_field_cut'
    validate_private_record(events[0][1])
    assert events[0][1]['receipt']['block_before']==7 and events[0][1]['receipt']['block_after']==9


def test_absent_cut_receipts_do_not_invent_a_success_event():
    from pokemon_red_completion.red_training_ground_route import record_verified_field_cuts
    events=[]
    record_verified_field_cuts(N(record_diagnostic_event=lambda *r:events.append(r)),N(cut_receipts=[]))
    record_verified_field_cuts(N(),N(cut_receipts=[]))
    assert events==[]


def test_later_legal_cut_dependency_reopens_exchange_without_a_surge_special_case(monkeypatch):
    c=case(monkeypatch);c.state.completed.add('defeat_surge');c.state.legal={'reach_lavender'}
    choices=branches(c)
    assert choices and all(b.story_objective_ref=='reach_lavender'for b,_ in choices)
    report=choices[0][0].execute();assert report.evidence['objective_completed']is False
    assert c.runtime.adapter.party_guard.field_carrier.objective_ref=='reach_lavender'


def test_multiple_private_dependencies_do_not_multiply_mechanical_choices(monkeypatch):
    c=case(monkeypatch);single=branches(c);c.state.legal.add('reach_lavender');multiple=branches(c)
    assert len(single)==len(multiple)==5
    assert {(b.kind,b.estimated_effort,b.estimated_risk,b.story_unit)for b,_ in single}=={(b.kind,b.estimated_effort,b.estimated_risk,b.story_unit)for b,_ in multiple}


def test_return_preserves_cut_for_a_different_currently_legal_dependency(monkeypatch):
    c=case(monkeypatch);branches(c)[0][0].execute();custody=c.runtime.adapter.party_guard.field_carrier
    c.state.completed.add('defeat_surge');c.state.legal={'reach_lavender'}
    assert mod.field_carrier_return_binding(c.runtime,c.actions,route=c.route)is None
    assert c.runtime.adapter.party_guard.field_carrier==custody
