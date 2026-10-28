from collections import Counter
from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding, GoalExecutionReport, GoalVerification,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionAvailability, LivingDexOptionCandidate, LivingDexOptionFeatures,
    LivingDexOptionKind,
)
from pokemon_red_completion.red_boxed_machine_options import BoxedMachineBundle, BoxedMachineChoice
from pokemon_red_completion.red_live_option_menu import supplemental_live_option
from pokemon_red_completion.red_machine_teaching import RedMachineLesson
import pokemon_red_completion.red_prepared_evolution_options as module


def fixture(monkeypatch, *, fault=None, partial=False):
    state=N(epoch=0,ready=True,stock=Counter({('precursor',88,18,7290):1,
        ('retained',28,50,100000):1}),events=[],lesson_verified=0,evolution_verified=0)
    actions=N(actions_executed=0)
    em=N(frame_count=0,save_state_bytes=lambda:str(state.epoch).encode())
    def pulse(name):
        state.events.append(name);state.epoch+=1
        actions.actions_executed+=1;em.frame_count+=10
    def guard_check():
        if fault=='custody' and 'evolution' in state.events:raise ValueError('lost custody')
    guard=N(edges=((88,89,30),),verify_active_roster_restored=guard_check)
    runtime=N(emulator=em,adapter=N(party_guard=guard,observe=lambda:N()))
    monkeypatch.setattr(module,'_stock',lambda _:state.stock.copy())
    monkeypatch.setattr(module,'_field_ready',lambda _:state.ready)
    def option(binding,kind,completion,gain):
        return supplemental_live_option(binding,LivingDexOptionCandidate(
            binding_ref=binding.binding_ref,availability=LivingDexOptionAvailability.AVAILABLE,
            features=LivingDexOptionFeatures(kind,completion,gain,.1,.2,.2,.1,.1,.1,.2)))
    def lesson():
        pulse('lesson')
        if fault=='lesson':raise OSError('native lesson error')
        if fault=='lesson_xp':
            state.stock=Counter({('precursor',88,19,8000):1,('retained',28,50,100000):1})
        return GoalExecutionReport(1,10,dict(machine='disclosed lesson'))
    def verify_lesson(_):
        state.lesson_verified+=1
        return (GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
                if fault=='lesson_verdict' else GoalVerification.succeeded())
    machine_binding=ExecutableGoalBinding('machine',GoalKind.DEVELOP_TEAM,.2,.1,
        lesson,verify_lesson,maximum_cash_debit=0)
    machine=BoxedMachineChoice(BoxedMachineBundle('precursor',0,1,'retained',1,
        RedMachineLesson(198,6,2,88,(35,43,86,97),57)),
        option(machine_binding,LivingDexOptionKind.DEVELOP,0.,.8))
    def evolution():
        pulse('evolution')
        if fault=='evolution':raise RuntimeError('native evolution error')
        state.stock=Counter({('precursor',88 if partial else 89,29 if partial else 30,
            24000 if partial else 27000):1,('retained',28,50,100000):1})
        if fault=='identity':state.stock[('other',28,20,8000)]+=1
        if fault=='xp':state.stock[('retained',28,50,100000)]-=1;state.stock[('retained',28,49,90000)]+=1
        return GoalExecutionReport(1,10,dict(evolution='partial' if partial else 'succeeded',
            partial_evolution=partial,healing_trips=0))
    def verify_evolution(_):
        state.evolution_verified+=1
        return (GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
                if partial else GoalVerification.succeeded())
    binding=ExecutableGoalBinding('pokemon.red:evolution:national-147-to-national-148',
        GoalKind.EVOLVE_SPECIES,.4,.2,evolution,verify_evolution,maximum_cash_debit=100)
    ordinary=option(binding,LivingDexOptionKind.EVOLVE,1.,.3)
    def collection(rt,act,observed):
        assert rt is runtime and act is actions
        if fault=='refresh_input':pulse('unrequested input')
        if fault=='missing':return ()
        if fault=='ambiguous':return (ordinary,ordinary)
        if fault=='cash':return (replace(ordinary,binding=replace(binding,maximum_cash_debit=101)),)
        return (ordinary,)
    admits=lambda _:not (fault=='excluded_after' and 'lesson' in state.events)
    def discover(**kwargs):
        options=dict(machine_choices=(machine,),evolution_options=(ordinary,),
            enumerate_collection=collection,admits=admits)
        options.update(kwargs)
        return module.prepared_evolution_options(runtime,actions,N(),**options)
    return state,actions,em,runtime,machine,ordinary,discover


def test_quote_is_read_only_identity_free_and_preserves_original_candidate(monkeypatch):
    state,actions,em,_,_,ordinary,discover=fixture(monkeypatch)
    before=ordinary.candidate
    row,=discover()
    assert not state.events and actions.actions_executed==em.frame_count==0
    assert ordinary.candidate is before
    assert row.candidate.features.completion_gain==before.features.completion_gain
    assert row.candidate.features.execution_effort==pytest.approx(.4)
    assert row.candidate.features.dependency_unlock_gain==.8
    assert row.binding.maximum_cash_debit==100
    assert 'precursor' not in repr(row.candidate.features)


def test_selected_recipe_verifies_both_components_once_and_all_costs(monkeypatch):
    state,_,_,_,_,_,discover=fixture(monkeypatch)
    row,=discover();report=row.binding.execute()
    assert state.events==['lesson','evolution']
    assert (report.actions_executed,report.frames_executed)==(2,20)
    assert report.evidence['prepared_evolution']['exact_selected_evolution_refreshed']
    assert row.binding.verify(report).status.value=='succeeded'
    assert row.binding.verify(report).status.value=='succeeded'
    assert (state.lesson_verified,state.evolution_verified)==(1,1)
    assert row.binding.verify(replace(report)).status.value=='failed'
    with pytest.raises(ValueError,match='consumed'):row.binding.execute()


def test_safe_partial_is_retained_and_cannot_be_promoted_by_successful_lesson(monkeypatch):
    state,_,_,_,_,_,discover=fixture(monkeypatch,partial=True)
    row,=discover();report=row.binding.execute()
    assert report.evidence['partial_evolution']
    assert report.evidence['evolution']=='partial'
    assert row.binding.verify(report).status.value=='failed'
    assert state.evolution_verified==1


@pytest.mark.parametrize('fault,events',[
    ('lesson',['lesson']),('lesson_verdict',['lesson']),('lesson_xp',['lesson']),
    ('missing',['lesson']),('ambiguous',['lesson']),('cash',['lesson']),
    ('excluded_after',['lesson']),('refresh_input',['lesson','unrequested input']),
    ('evolution',['lesson','evolution']),('identity',['lesson','evolution']),
    ('xp',['lesson','evolution']),('custody',['lesson','evolution'])])
def test_failures_retain_the_tail_and_never_choose_an_alternate_goal(monkeypatch,fault,events):
    state,actions,em,_,_,_,discover=fixture(monkeypatch,fault=fault)
    row,=discover()
    with pytest.raises((ValueError,RuntimeError,OSError)):row.binding.execute()
    assert state.events==events
    assert actions.actions_executed==len(events) and em.frame_count==10*len(events)
    assert row.binding.verify(GoalExecutionReport(0,0,{})).status.value=='failed'
    with pytest.raises(ValueError,match='consumed'):row.binding.execute()


@pytest.mark.parametrize('case',['duplicate_species','wrong_ref','no_evolution','duplicate_evolution',
                                'excluded','wrong_kind','no_machines','not_ready'])
def test_no_recipe_for_an_ambiguous_or_unadmitted_existing_evolution(monkeypatch,case):
    state,_,_,_,machine,ordinary,discover=fixture(monkeypatch)
    kwargs={}
    if case=='duplicate_species':state.stock[('other-precursor',88,18,7290)]+=1
    elif case=='wrong_ref':kwargs['machine_choices']=(replace(machine,bundle=replace(machine.bundle,target_ref='different')),)
    elif case=='no_evolution':kwargs['evolution_options']=()
    elif case=='duplicate_evolution':kwargs['evolution_options']=(ordinary,ordinary)
    elif case=='excluded':kwargs['admits']=lambda _:False
    elif case=='wrong_kind':kwargs['evolution_options']=(replace(ordinary,binding=replace(ordinary.binding,kind=GoalKind.ACQUIRE_SPECIES)),)
    elif case=='no_machines':kwargs['machine_choices']=()
    elif case=='not_ready':state.ready=False
    assert discover(**kwargs)==() and not state.events


def test_stale_recipe_rejects_before_any_input_and_terminal_tampering_fails(monkeypatch):
    state,_,_,_,_,_,discover=fixture(monkeypatch)
    row,=discover();state.epoch+=1
    with pytest.raises(ValueError,match='stale'):row.binding.execute()
    assert not state.events
    row,=discover();report=row.binding.execute();state.epoch+=1
    assert row.binding.verify(report).status.value=='failed'


def test_progress_retains_duplicate_multiplicity_and_each_xp_floor():
    old=Counter({('same',28,10,1000):1,('same',28,11,1200):1})
    good=Counter({('same',28,11,1100):1,('same',28,12,1500):1})
    assert all(module.prepared_stock_progress(old,good).values())
    assert not all(module.prepared_stock_progress(old,Counter({('same',28,12,2000):1})).values())
    bad=Counter({('same',28,9,900):1,('same',28,12,2000):1})
    assert not module.prepared_stock_progress(old,bad)['earned_xp_retained']
