from dataclasses import replace
from types import SimpleNamespace as N
import pytest
from test_red_player_owned_machines import fixture
import pokemon_red_completion.red_player_owned_machines as m
from pokemon_red_completion.red_machine_teaching import RedMachineLesson
from pokemon_red_completion.actions import MacroAction,MacroActionKind

def cut_fixture(monkeypatch,fault=None):
    rt,actions,seen=fixture(monkeypatch)
    rt.reader.raw=replace(rt.reader.raw,bag_items=((196,1),(4,3)),badge_bits=255)
    def plan(rom,reader,*,item_id,party_slot,replace_slot):
        if item_id!=196 or party_slot!=1 or replace_slot not in(2,3):raise ValueError('incompatible/HM')
        return RedMachineLesson(item_id,party_slot,replace_slot,28,reader.raw.party_moves[0],15)
    monkeypatch.setattr(m,'plan_machine_lesson',plan)
    def execute(em,executor,reader,lesson,*,rom):
        executor.execute(MacroAction(MacroActionKind.WAIT));moves=list(reader.raw.party_moves[0]);pp=list(reader.raw.party_pp[0]);moves[lesson.replace_slot-1]=15;pp[lesson.replace_slot-1]=30
        reader.raw=replace(reader.raw,party_moves=(tuple(moves),),party_pp=(tuple(pp),));em.state=b'cut-terminal'
        if fault=='cash':reader.raw=replace(reader.raw,player_money=123)
        if fault=='bag':reader.raw=replace(reader.raw,bag_items=((4,3),))
        if fault=='experience':em.exp+=1
        if fault=='hp':reader.raw=replace(reader.raw,party_hp=(0,))
        if fault=='dex':reader.read_pokedex_state=lambda:'changed'
        if fault=='boxes':reader.read_all_box_states=lambda:'changed'
    monkeypatch.setattr(m,'execute_machine_lesson',execute)
    return rt,actions,seen

def test_default_off_complete_legal_bundle_inventory_and_exact_teaching(monkeypatch):
    rt,a,seen=cut_fixture(monkeypatch)
    assert m.owned_machine_options(rt,a,rom=b'fixture',include_fly_lesson=True)==()
    rows=m.owned_machine_options(rt,a,rom=b'fixture',include_cut_lesson=True,include_attack_lessons=False)
    assert len(rows)==2 and not seen and rt.emulator.state==b'source'
    assert len({r.binding.binding_ref for r in rows})==2
    assert all(r.candidate.features.dependency_unlock_gain==1 for r in rows)
    report=rows[0].binding.execute();assert rows[0].binding.verify(report).status.value=='succeeded'
    assert report.evidence['machine_consumed']==report.evidence['cash_debit']==report.evidence['xp_gained']==report.evidence['registrations_gained']==0
    assert report.evidence['field_move_unlocked']==15 and report.evidence['capacity_proxy']=='missing_Cut_dependency_not_attack_gain'
    assert dict(rt.reader.raw.bag_items)=={196:1,4:3} and rt.reader.raw.party_moves==((70,15,145,57),)
    assert m.owned_machine_options(rt,a,rom=b'fixture',include_cut_lesson=True)==()

@pytest.mark.parametrize('fault',['cash','bag','experience','hp','dex','boxes'])
def test_cut_lesson_preserves_protected_native_state(monkeypatch,fault):
    rt,a,_=cut_fixture(monkeypatch,fault)
    row=m.owned_machine_options(rt,a,rom=b'fixture',include_cut_lesson=True)[0]
    with pytest.raises(RuntimeError,match='protected'):row.binding.execute()

@pytest.mark.parametrize('missing',['badge','hm','holder','already_cut','unready','fainted'])
def test_cut_eligibility_requires_actual_owned_capability(monkeypatch,missing):
    rt,a,seen=cut_fixture(monkeypatch)
    if missing=='badge':rt.reader.raw=replace(rt.reader.raw,badge_bits=8)
    if missing=='hm':rt.reader.raw=replace(rt.reader.raw,bag_items=((4,3),))
    if missing=='holder':monkeypatch.setattr(m,'plan_machine_lesson',lambda *a,**k:(_ for _ in()).throw(ValueError('incompatible')))
    if missing=='already_cut':rt.reader.raw=replace(rt.reader.raw,party_moves=((70,15,145,57),))
    if missing=='unready':rt.reader.ready=False
    if missing=='fainted':rt.reader.raw=replace(rt.reader.raw,party_hp=(0,))
    assert m.owned_machine_options(rt,a,rom=b'fixture',include_cut_lesson=True)==() and not seen

def test_cut_permission_is_boolean(monkeypatch):
    rt,a,_=cut_fixture(monkeypatch)
    with pytest.raises(ValueError,match='permissions'):m.owned_machine_options(rt,a,rom=b'fixture',include_cut_lesson=1)

def test_cut_opt_in_does_not_change_existing_tm_rows(monkeypatch):
    rt,a,_=fixture(monkeypatch)
    before=m.owned_machine_options(rt,a,rom=b'fixture');after=m.owned_machine_options(rt,a,rom=b'fixture',include_cut_lesson=True)
    assert [(r.binding.binding_ref,r.candidate)for r in before]==[(r.binding.binding_ref,r.candidate)for r in after]


@pytest.mark.parametrize('hof,registered,policy,expected',[
    (True,{'one'},True,True),(True,{'one','two'},True,False),
    (False,{'one'},True,False),(True,set(),False,False)])
def test_real_postgame_callback_uses_target_set_completion(hof,registered,policy,expected):
    import ast
    from pathlib import Path
    source=(Path(__file__).parents[1]/'runtime_helpers/red_whole_player_inventory_20261006.py').read_text()
    node=next(n for n in ast.walk(ast.parse(source))if isinstance(n,ast.FunctionDef)and n.name=='field_dependencies')
    called=[];route=object();ns=dict(route=route,fly_dependency_options=lambda *a,**k:called.append(k)or())
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'actual_postgame_callback','exec'),ns)
    rp=N(targets=frozenset({'one','two'}),goal_registered=lambda _:frozenset(registered))if policy else None
    rt=N(adapter=N(graph=N(completed_ids=lambda _:{'enter_hall_of_fame'}if hof else set())),registration_policy=rp)
    assert ns['field_dependencies'](rt,object(),N(game_state=object(),collection_observation=object()))==()
    assert called==[dict(route=route,include_cut_lesson=expected)]

def test_dependency_connector_forwards_explicit_cut_permission(monkeypatch):
    import pokemon_red_completion.red_player_fly as f
    import test_red_player_fly as t
    rt,a,route,_=t.fixture(monkeypatch);called=[]
    monkeypatch.setattr(m,'owned_machine_options',lambda *a,**k:called.append(k)or())
    f.fly_dependency_options(rt,a,route=route,include_cut_lesson=True)
    assert called==[dict(rom=route.rom,include_fly_lesson=True,include_attack_lessons=False,include_cut_lesson=True)]
