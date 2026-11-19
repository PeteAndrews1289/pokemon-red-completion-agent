from dataclasses import replace
from types import SimpleNamespace as N
import pytest
import pokemon_red_completion.red_field_carrier as carrier
import pokemon_red_completion.red_pc_storage as pc
import pokemon_red_completion.red_npc_trade_options as trade_module
import test_red_field_carrier as fc
import test_red_fossil_ingredient_goal as fg
import test_red_npc_trade_options as nt
from pokemon_red_completion.red_field_capability_demand import CutDependencyWitness
from pokemon_red_completion.route_plan import RoutePlanningError
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.actions import MacroAction,MacroActionKind

def witness():return CutDependencyWitness('pokemon:national:142',52,'a'*64,1)

def test_explicit_collection_dependency_preserves_default_story_gate(monkeypatch):
    c=fc.case(monkeypatch);c.state.legal=set()
    assert fc.branches(c)==()
    rows=fc.branches(c,dependency_witnesses=(witness(),))
    assert len(rows)==5 and c.actions.actions_executed==0
    assert all(c.refs[0]not in b.binding_ref for b,_ in rows)

@pytest.mark.parametrize('bad',[(),[],(N(cut_count=1),),(replace(witness(),cut_count=0),)])
def test_explicit_dependency_rejects_untyped_or_empty_witness(monkeypatch,bad):
    c=fc.case(monkeypatch)
    with pytest.raises(ValueError,match='witnesses'):fc.branches(c,dependency_witnesses=bad)
    assert c.actions.actions_executed==0

def test_other_box_carrier_quote_then_real_switch_preserves_original_custody(monkeypatch):
    c=fc.case(monkeypatch);r=c.runtime.reader;selected=[1];original_moves=r.read_box_move_members
    r.read_current_box_state=lambda:N(box_index=selected[0])
    r.read_all_box_states=lambda:N(counts=(len(c.state.box),0))
    r.read_box_move_members=lambda i:original_moves(i)if i==0 else()
    assert fc.branches(c)==()
    rows=fc.branches(c,include_other_boxes=True)
    assert len(rows)==5 and not c.actions.actions_executed and selected==[1]
    switches=[]
    def switch(a,reader,*,target_box_index):
        switches.append(target_box_index);a.execute(MacroAction(MacroActionKind.WAIT));selected[0]=target_box_index;return N(passed=True)
    monkeypatch.setattr(pc,'switch_box',switch)
    b=rows[0][0];report=b.execute()
    assert b.verify(report).status.value=='succeeded' and switches==[0]
    guard=c.runtime.adapter.party_guard;assert guard.field_carrier.phase=='active'
    assert guard.field_carrier.carrier_ref==c.target and c.refs[0]in c.state.active
    assert c.actions.actions_executed>0

def test_other_box_permission_rejects_truthy_integer(monkeypatch):
    c=fc.case(monkeypatch)
    with pytest.raises(ValueError,match='permission'):fc.branches(c,include_other_boxes=1)

def callback_case(monkeypatch,fault=None):
    w,p=fg.fixture(monkeypatch)
    original=(28,29,30,31,32,33)
    w.raw=replace(w.raw,party_species_ids=(28,29,30,31,32,99));w.boxes=(33,)
    def returned(actions,world,start):
        w.phases.append('carrier_return');actions.execute(MacroAction(MacroActionKind.WAIT,repeat=10))
        w.raw=replace(w.raw,party_species_ids=(33,28,29,30,31,32));w.boxes=(99,)
        if fault=='cash':w.raw=replace(w.raw,player_money=999)
        if fault=='bag':w.raw=replace(w.raw,bag_items=((3,10),))
        if fault=='dex':w.owned|={1}
        if fault=='stock':w.boxes=()
        if fault=='party':w.raw=replace(w.raw,party_species_ids=(99,)*6)
        if fault=='position':w.raw=replace(w.raw,player_x=5)
        if fault=='ready':w.ready=False
        return dict(original_roster_restored=fault!='receipt')
    return w,replace(p,before_revival=returned,revival_party=original)

def test_carrier_return_occurs_before_revival_and_all_actions_charged(monkeypatch):
    w,p=callback_case(monkeypatch);b=p.offer(p.adapter.observe()).binding;report=b.execute()
    assert w.phases==['route','gift','route','carrier_return','revival']
    assert report.actions_executed==4 and report.frames_executed==40
    assert b.verify(report).status.value=='succeeded' and report.evidence['carrier_return']['original_roster_restored']

@pytest.mark.parametrize('fault',['cash','bag','dex','stock','party','position','ready','receipt'])
def test_bad_carrier_return_cannot_begin_fossil_revival(monkeypatch,fault):
    w,p=callback_case(monkeypatch,fault);b=p.offer(p.adapter.observe()).binding
    with pytest.raises(RuntimeError,match='protected stock or arrival'):b.execute()
    assert 'gift'in w.phases and 'revival'not in w.phases and 142 not in w.owned
    assert p.actions.actions_executed==3

@pytest.mark.parametrize('kwargs',[dict(revival_party=(28,)*6),dict(before_revival=True,revival_party=(28,)*6),dict(before_revival=lambda *a:None,revival_party=(28,))])
def test_callback_and_observed_roster_must_be_declared_together(monkeypatch,kwargs):
    _,p=fg.fixture(monkeypatch)
    with pytest.raises(ValueError):replace(p,**kwargs)

def test_optional_trade_transport_leaves_valid_existing_binding_identical(monkeypatch):
    rt,o,a,w,calls=nt.fixture(monkeypatch)
    monkeypatch.setattr(trade_module,'_alternate_trade_transport',lambda *a:(_ for _ in()).throw(AssertionError('unnecessary fallback')))
    base=trade_module.npc_trade_bindings(rt,o,a,w);opt=trade_module.npc_trade_bindings(rt,o,a,w,allow_alternate_transport=True)
    assert [(b.binding_ref,b.kind,b.estimated_effort)for b in base]==[(b.binding_ref,b.kind,b.estimated_effort)for b in opt]and not calls

def test_alternate_quote_uses_known_native_landings_bounded_return_and_original_trade(monkeypatch):
    rt,o,a,w,calls=nt.fixture(monkeypatch);o.raw=replace(o.raw,badge_bits=4)
    rt.reader.read_fly_destinations=lambda:(2,5)
    monkeypatch.setattr(trade_module,'fly_menu_indices',lambda _:())
    monkeypatch.setattr(trade_module,'red_fly_landings',lambda _:((2,(26,13)),(5,(4,11))))
    import pokemon_red_completion.red_goal_skills as skills
    monkeypatch.setattr(skills,'_POKEMON_CENTER_MAPS',frozenset({58,89}))
    start=TraversalSnapshot(6,(10,41),True,mode='land')
    def plan(s,target,*,goal_at):
        if (s.map_id,target)in((5,89),(48,89)):
            return N(steps=(1,)*3,cost=3,terminal_at=goal_at)
        raise RoutePlanningError('blocked')
    w.plan_feasible_to_map=plan
    monkeypatch.setattr(trade_module,'_approach',lambda world,s,t:N(steps=(1,)*10,cost=10,terminal_at=(1,3))if s.map_id==89 else None)
    original=nt.TRADE
    assert trade_module._alternate_trade_transport(rt,o,w,start,original)==(5,89)
    assert original is nt.TRADE and not calls
    rt.reader.read_fly_destinations=lambda:(2,)
    assert trade_module._alternate_trade_transport(rt,o,w,start,original)is None
    rt.reader.read_fly_destinations=lambda:(2,5);rt.emulator.pressed_buttons=('a',)
    assert trade_module._alternate_trade_transport(rt,o,w,start,original)is None

def test_alternate_permission_rejects_integer_before_observation():
    with pytest.raises(TypeError,match='explicit boolean'):trade_module.npc_trade_bindings(N(),None,None,None,allow_alternate_transport=1)
