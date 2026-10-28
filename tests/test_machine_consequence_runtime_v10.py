"""ROM-free V10 dispatch contracts; no native learning evidence or gameplay."""
from dataclasses import replace
import numpy as np
import pytest
from test_red_branch_recovery import menu, parent_choice
from test_red_consequence_choice import provisional_args
from test_red_player_owned_machines import fixture
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import option_feature_names, upgrade_option_value_model_for_move_change
from pokemon_red_completion.player_challenge_consequence import ChallengeConsequenceHead, PROGRESS_TARGET_NAMES
from pokemon_red_completion.red_player_owned_machines import owned_machine_options
from pokemon_red_completion.red_live_option_menu import RedLiveOptionSelectionMode
import pokemon_red_completion.red_consequence_choice as choice_module


def machine_options(tmp_path, monkeypatch):
    options, story, state, runtime = menu(tmp_path, monkeypatch)
    rt, actions, inputs = fixture(monkeypatch)
    rows = owned_machine_options(rt, actions, rom=b'fixture', include_move_change_facts=True)
    assert len(rows) == 2 and not inputs
    template = options.menu.candidates[story]
    keep = tuple(i for i,b in enumerate(options.bindings) if b.kind is not GoalKind.DEVELOP_TEAM)
    bindings = tuple(options.binding(i) for i in keep) + tuple(r.binding for r in rows)
    candidates = tuple(options.menu.candidates[i] for i in keep) + tuple(
        replace(r.candidate, challenge=template.challenge, readiness=template.readiness) for r in rows)
    updated = replace(options, bindings=bindings, menu=replace(options.menu,candidates=candidates),
        ordinary_binding_refs=options.ordinary_binding_refs & {b.binding_ref for b in bindings})
    story = next(i for i,b in enumerate(bindings) if b.story_objective_ref=='private-combat-goal')
    return updated, story, len(bindings)-2, rt, inputs


def v10_head(prefer='kind.develop', provenance='native_train'):
    names=option_feature_names(10); width=len(names)
    coefficients=np.zeros((width,len(PROGRESS_TARGET_NAMES)))
    coefficients[names.index(prefer),:2]=1
    return ChallengeConsequenceHead(coefficients,np.zeros(len(PROGRESS_TARGET_NAMES)),
        np.zeros(width),np.ones(width),'a'*64,2,1.,provenance,feedback_version=2,feature_version=10)


def test_real_owned_machine_candidates_are_scored_without_level_workloads(tmp_path, monkeypatch):
    options, story, machine, rt, inputs=machine_options(tmp_path,monkeypatch)
    indices=(story,machine,machine+1)
    subset=replace(options, bindings=tuple(options.binding(i) for i in indices),
        menu=replace(options.menu,candidates=tuple(options.menu.candidates[i] for i in indices)),
        ordinary_binding_refs=options.ordinary_binding_refs & {options.binding(i).binding_ref for i in indices})
    binding, receipt=choice_module.choose_consequence_binding(subset,v10_head(),challenge_refs=('one',)*3)
    assert binding is options.binding(machine)
    assert all(c.preparation is None and c.level_workload is None for c in subset.menu.candidates[1:])
    assert receipt['scores'][1] > receipt['scores'][0]
    assert not inputs and rt.emulator.state==b'source'


@pytest.mark.parametrize('parent_machine', [False,True])
@pytest.mark.parametrize('refine', [False,True])
def test_machine_choice_uses_existing_exact_binding_and_explicit_parent_refinement(tmp_path, monkeypatch, parent_machine, refine):
    options, story, machine, rt, inputs=machine_options(tmp_path,monkeypatch)
    args,_=provisional_args(tmp_path/'model',monkeypatch)
    model=upgrade_option_value_model_for_move_change(args['model'])
    at=machine if parent_machine else story
    monkeypatch.setattr(choice_module,'select_red_live_option',lambda m,o,**kw:parent_choice(o,at,m,seed=kw['seed'],mode=RedLiveOptionSelectionMode.MODEL_GREEDY))
    head=v10_head('kind.unlock_access' if parent_machine else 'kind.develop')
    selected=choice_module.select_branch_recovery_live_option(model,options,head,
        objective_ref='private-combat-goal',seed=3,greedy_selection=True,refine_preparation=refine)
    expected=story if parent_machine and refine else machine
    assert selected.selected_binding is options.binding(expected)
    child=selected.branch_recovery.child
    assert (child is not None)==(not parent_machine or refine)
    if child is not None:
        assert options.binding(machine) in child.options.bindings
        assert all(b.story_objective_ref!='private-travel-goal' for b in child.options.bindings)
    assert not inputs and rt.emulator.state==b'source'
    assert 'private-combat-goal' not in str(selected.public_dict())


@pytest.mark.parametrize('fault',['outside_scope','ambiguous','unknown'])
def test_machine_parent_never_invents_a_challenge(tmp_path,monkeypatch,fault):
    options, story, machine, rt, inputs=machine_options(tmp_path,monkeypatch)
    args,_=provisional_args(tmp_path/'model',monkeypatch);model=upgrade_option_value_model_for_move_change(args['model'])
    candidates=list(options.menu.candidates);scope='private-combat-goal'
    if fault=='outside_scope':scope='not-present'
    elif fault=='ambiguous':
        other=next(i for i,b in enumerate(options.bindings) if b.story_objective_ref=='private-travel-goal')
        candidates[other]=replace(candidates[other],challenge=candidates[story].challenge)
    else:candidates[machine]=replace(candidates[machine],challenge=None)
    options=replace(options,menu=replace(options.menu,candidates=tuple(candidates)))
    monkeypatch.setattr(choice_module,'select_red_live_option',lambda m,o,**kw:parent_choice(o,machine,m,seed=kw['seed'],mode=RedLiveOptionSelectionMode.MODEL_GREEDY))
    selected=choice_module.select_branch_recovery_live_option(model,options,v10_head(),objective_ref=scope,seed=1,greedy_selection=True,refine_preparation=True)
    assert selected.selected_binding is options.binding(machine) and selected.branch_recovery.child is None
    assert not inputs


@pytest.mark.parametrize('fault',[None,'train','synthetic','version','no_scope'])
def test_v10_runtime_admission_retains_development_and_exact_model_scope(tmp_path,monkeypatch,fault):
    args,_=provisional_args(tmp_path,monkeypatch);model=upgrade_option_value_model_for_move_change(args['model'])
    head=v10_head();source={**args['source'],'experiment_sha256':'b'*64};scope='private-combat-goal'
    if fault=='train':source['partition']='train'
    elif fault=='synthetic':head=replace(head,provenance='synthetic')
    elif fault=='version':model=args['model']
    elif fault=='no_scope':scope=''
    kwargs=dict(allow=True,greedy_selection=True,source=source,model=model,head=head,objective_ref=scope,challenge_ref='same',refine_preparation=True)
    if fault is None:choice_module.validate_greedy_branch_recovery_scope(**kwargs)
    else:
        with pytest.raises(ValueError):choice_module.validate_greedy_branch_recovery_scope(**kwargs)


def test_move_specific_weights_distinguish_real_replacements(tmp_path,monkeypatch):
    options, story, machine, rt, inputs=machine_options(tmp_path,monkeypatch)
    candidates=options.menu.candidates[machine:machine+2]
    observed=replace(options.menu,candidates=candidates)
    head=v10_head('move_change.removed.power')
    scores=head.scores(observed,challenge_refs=('same','same'))
    assert scores[0] != scores[1]
    assert not inputs


@pytest.mark.parametrize('mode',['ordinary','direct','branch'])
def test_v10_reaches_continuous_execution_through_all_runtime_adapters(tmp_path,monkeypatch,mode):
    import pokemon_red_completion.red_native_player as native
    from test_red_branch_recovery import greedy_native_args
    from pokemon_red_completion.living_dex_option_value import LivingDexOptionValueModel
    args,state=(greedy_native_args if mode=='branch' else provisional_args)(tmp_path,monkeypatch)
    args['model']=upgrade_option_value_model_for_move_change(args['model'])
    args['consequence_head']=v10_head('kind.unlock_access')
    if mode=='ordinary':
        args.pop('consequence_head');args.pop('consequence_challenge_ref');args['greedy_selection']=True
    monkeypatch.setattr(LivingDexOptionValueModel,'scores',lambda self,observed,utility:
        tuple(float(c.features.kind.value=='unlock_access') for c in observed.candidates))
    result=native.run_native_continuous_player(**args)
    assert result['executed_decisions']==result['model_decisions']==1
    assert state['challenge'] and not state['trained']
    assert not args['emulator'].pressed_buttons
    if mode=='branch':assert result['strategic_policy_queries']==2


@pytest.mark.parametrize('model_version,head_version',[(10,10),(9,10),(10,7)])
def test_v10_settlement_keeps_exact_scope_and_version(tmp_path,monkeypatch,model_version,head_version):
    import pokemon_red_completion.red_native_player as native
    from pokemon_red_completion.living_dex_option_value import upgrade_option_value_model_for_level_workload
    args,_=provisional_args(tmp_path,monkeypatch)
    model=(upgrade_option_value_model_for_move_change if model_version==10 else upgrade_option_value_model_for_level_workload)(args['model'])
    head=v10_head() if head_version==10 else args['consequence_head']
    kwargs=dict(allow=True,source=args['source'],model=model,head=head,objective_ref='one',challenge_ref='one',settlement_requested=True,sequence_horizon=None,sequence_policy=None,consequence_spec=None)
    if model_version==head_version:assert native.validate_settlement_refinement_scope(**kwargs)
    else:
        with pytest.raises(ValueError):native.validate_settlement_refinement_scope(**kwargs)
    assert args['emulator'].frame_count==0


def test_raw_machine_parent_with_no_observed_combat_context_stays_unmodified(tmp_path,monkeypatch):
    from pokemon_red_completion.player_option_challenge import OptionChallenge
    options,story,machine,rt,inputs=machine_options(tmp_path,monkeypatch)
    candidates=list(options.menu.candidates)
    candidates[machine]=replace(candidates[machine],challenge=OptionChallenge(False,False,0.,0.,0.))
    options=replace(options,menu=replace(options.menu,candidates=tuple(candidates)))
    args,_=provisional_args(tmp_path/'model',monkeypatch);model=upgrade_option_value_model_for_move_change(args['model'])
    monkeypatch.setattr(choice_module,'select_red_live_option',lambda m,o,**kw:parent_choice(o,machine,m,seed=kw['seed'],mode=RedLiveOptionSelectionMode.MODEL_GREEDY))
    selected=choice_module.select_branch_recovery_live_option(model,options,v10_head(),objective_ref='private-combat-goal',seed=1,greedy_selection=True,refine_preparation=True)
    assert selected.selected_binding is options.binding(machine) and selected.branch_recovery.child is None
    assert not inputs


def test_v10_economy_diagnostics_accept_machine_facts_and_keep_economy_prediction():
    from test_move_change_v10 import model,candidate,change,_context
    from pokemon_red_completion.living_dex_option_value import LivingDexOptionMenu,LivingDexOptionUtility
    from pokemon_red_completion.resource_economy_observation import EconomySnapshot
    baseline=model(True);upgraded=upgrade_option_value_model_for_move_change(baseline)
    context=replace(_context(),economy_snapshot=EconomySnapshot(100,()),target_cash=500)
    observed=LivingDexOptionMenu(context,(candidate(change()),candidate(change(44),binding='other')))
    from test_living_dex_option_value import _utility
    utility=_utility()
    result=upgraded.diagnose_menu(observed,utility,selected_index=0)
    assert result['score_margin_is_confidence'] is False
    for c in observed.candidates:
        assert upgraded.predict_economy_candidate(context,c)==baseline.predict_economy_candidate(context,replace(c,move_change=None))



@pytest.mark.parametrize('fault',['no_descriptor','mixed_preparation','mixed_workload','legacy7','legacy9'])
def test_machine_scoring_rejects_unrepresented_or_conflicting_preparation(tmp_path,monkeypatch,fault):
    from pokemon_red_completion.player_option_level_workload import OptionLevelWorkload
    from test_red_consequence_choice import progress_head
    from test_consequence_workload_v9 import upgraded_head
    options,story,machine,rt,inputs=machine_options(tmp_path,monkeypatch)
    candidate=options.menu.candidates[machine];head=v10_head()
    if fault=='no_descriptor':candidate=replace(candidate,move_change=None)
    elif fault=='mixed_preparation':
        other,_,_,_=menu(tmp_path/'dose',monkeypatch)
        prep=next(c.preparation for c in other.menu.candidates if c.preparation is not None)
        candidate=replace(candidate,preparation=prep)
    elif fault=='mixed_workload':candidate=replace(candidate,level_workload=OptionLevelWorkload(20,22,2648))
    elif fault=='legacy7':head=progress_head()
    else:head=upgraded_head(progress_head())
    observed=replace(options.menu,candidates=(candidate,options.menu.candidates[story]))
    with pytest.raises(ValueError):head.scores(observed,challenge_refs=('same','same'))
    assert not inputs


def test_real_machine_runs_through_native_branch_wrapper(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace as N
    from test_red_branch_recovery import greedy_native_args
    from test_red_goal_skills import _raw, _Reader
    import pokemon_red_completion.red_native_player as native
    import pokemon_red_completion.red_player_owned_machines as machines
    from pokemon_red_completion.actions import MacroAction, MacroActionKind
    from pokemon_red_completion.red_machine_teaching import RedMachineLesson
    from pokemon_red_completion.living_dex_option_value import LivingDexOptionValueModel

    args, state = greedy_native_args(tmp_path, monkeypatch)
    args['model'] = upgrade_option_value_model_for_move_change(args['model'])
    args['consequence_head'] = v10_head('move_change.removed.power')
    held = {}
    factory = args['runtime_factory']

    def runtime_factory(controller):
        runtime = factory(controller)
        reader = _Reader(raw=replace(_raw(), player_money=3000,
            bag_items=((211, 2), (4, 3)), bag_item_ids=(211, 4),
            party_moves=((70, 39, 145, 57),), party_pp=((15, 30, 30, 1),)), ready=True)
        reader.read_pc_items = lambda: ()
        runtime.reader = reader
        held.update(runtime=runtime, reader=reader)
        return runtime

    def plan(rom, reader, *, item_id, party_slot, replace_slot):
        assert rom == b'fixture' and reader is held['reader']
        if item_id != 211 or party_slot != 1 or replace_slot not in (2, 3):
            raise ValueError('fixture incompatible lesson')
        return RedMachineLesson(item_id, party_slot, replace_slot, 28, reader.raw.party_moves[0], 61)

    def execute(emulator, executor, reader, lesson, *, rom):
        assert emulator is held['runtime'].emulator
        assert executor is held['actions'] and executor.delegate.enabled
        assert rom == b'fixture' and reader is held['reader']
        executor.execute(MacroAction(MacroActionKind.WAIT, repeat=2))
        moves, pp = list(reader.raw.party_moves[0]), list(reader.raw.party_pp[0])
        moves[lesson.replace_slot - 1], pp[lesson.replace_slot - 1] = 61, 20
        reader.raw = replace(reader.raw, party_moves=(tuple(moves),), party_pp=(tuple(pp),),
            bag_items=((211, 1), (4, 3)))
        held['executed_lesson'] = lesson

    monkeypatch.setattr(machines, 'plan_machine_lesson', plan)
    monkeypatch.setattr(machines, 'execute_machine_lesson', execute)
    monkeypatch.setattr(machines, 'PokemonRedPartyReader',
        lambda em: N(read=lambda: N(members=(N(experience=12345),))))

    def supplements(runtime, actions, observation, bindings):
        assert runtime is held['runtime'] and isinstance(actions, native.NativePlayerActions)
        held['actions'] = actions
        rows = machines.owned_machine_options(runtime, actions, rom=b'fixture', include_move_change_facts=True)
        held['rows'] = rows
        return rows

    real_select = choice_module.select_branch_recovery_live_option
    def select(*a, **kw):
        selected = real_select(*a, **kw)
        held['choice'] = selected
        return selected

    args.update(runtime_factory=runtime_factory, enumerate_supplements=supplements)
    monkeypatch.setattr(choice_module, 'select_branch_recovery_live_option', select)
    monkeypatch.setattr(LivingDexOptionValueModel, 'scores',
        lambda self, menu, utility: tuple(float(c.features.kind.value == 'unlock_access') for c in menu.candidates))
    result = native.run_native_continuous_player(**args)
    selected = held['choice']
    assert selected.selected_binding is selected.branch_recovery.child.selected_binding
    assert selected.selected_binding is selected.options.binding(selected.selected_candidate_index)
    candidate = selected.options.menu.candidates[selected.selected_candidate_index]
    assert candidate.move_change is not None and candidate.preparation is candidate.level_workload is None
    assert selected.selected_binding.binding_ref in {row.binding.binding_ref for row in held['rows']}
    assert held['executed_lesson'].replace_slot == 3
    assert held['reader'].raw.party_moves == ((70, 39, 61, 57),)
    assert dict(held['reader'].raw.bag_items) == {211: 1, 4: 3}
    assert result['executed_decisions'] == result['successful_decisions'] == 1
    assert result['strategic_policy_queries'] == 2
    assert not state['trained'] and not state['challenge']
    outcome = json.loads((args['output'] / 'episode/step-000/outcome.json').read_text())
    costs = json.loads((args['output'] / 'native-costs.json').read_text())
    assert outcome['verification'] == 'succeeded'
    assert outcome['evidence']['machine_consumed'] == 1
    assert costs['actions_attempted'] == held['actions'].actions_executed == 1
    assert args['emulator'].frame_count == 2 and not args['emulator'].pressed_buttons


def test_native_machine_custody_hash_handles_real_pokedex_sets_and_preserves_collection():
    from types import SimpleNamespace as N
    from pokemon_red_completion.observation import RedPokedexState, RedCurrentBoxState
    from pokemon_red_completion.red_challenge_consequence import _capture_machine_boundary
    from pokemon_red_completion.provenance import canonical_sha256
    raw=N(map_id=134,player_y=4,player_x=3,badge_bits=7,event_flags=b'\x00\x02',
          party_stats=((100,90,80,120),),party_pp=((25,30,20,25),))
    owned=frozenset([9,1,3]);seen=frozenset([3,9,1,4]);boxes=(RedCurrentBoxState(0,(28,),(30,)),)
    dex=RedPokedexState(owned,seen);reader=N(read=lambda:raw,read_all_box_states=lambda:boxes,
        read_pokedex_state=lambda:dex,read_pc_items=lambda:((213,1),))
    observed=_capture_machine_boundary(N(reader=reader))
    assert observed['protected_collection_sha256']==canonical_sha256(dict(
        boxes=[dict(box_index=0,species_ids=[28],levels=[30])],
        dex=dict(owned_species=[1,3,9],seen_species=[1,3,4,9]),pc=[[213,1]]))
    assert dex.owned_species is owned and dex.seen_species is seen
    reader.read_pokedex_state=lambda:RedPokedexState(owned|{4},seen)
    assert _capture_machine_boundary(N(reader=reader))['protected_collection_sha256']!=observed['protected_collection_sha256']
