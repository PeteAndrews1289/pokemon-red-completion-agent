from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_native_evolution_venue_model import menu_case, select
from test_red_native_boxed_evolution import runtime_fixture
from pokemon_red_completion import red_native_boxed_evolution as native
from pokemon_red_completion import red_party_development_adapter as adapter
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.red_collection import RedCurrentBoxState, red_internal_species_id
from pokemon_red_completion.red_team_training import EvolutionTrainingPaused


@pytest.mark.parametrize('field,value', [('source_id', 1), ('target_id', 2),
    ('model_sha256', 'b'*64), ('allow_direct_evolution', True)])
def test_expired_venue_still_authenticates_same_action(menu_case, field, value):
    calls=[];events=[];state={}
    model=SimpleNamespace(predict=lambda menu: calls.append(menu) or 0)
    select(menu_case, model, state, events)
    state.pop('venue_identity')
    with pytest.raises(native.context.RedGoalContextError, match='another action'):
        select(menu_case, model, state, events, **{field:value})
    assert len(calls)==len(events)==1


def test_cache_without_scope_is_rejected(menu_case):
    with pytest.raises(native.context.RedGoalContextError, match='another action'):
        select(menu_case, SimpleNamespace(predict=lambda _: pytest.fail('no query')),
            {'venue_identity':menu_case.venues[0].band.identity}, [])


@pytest.mark.parametrize('mode', ['same_level','growth','no_xp','fainted','lost','exception','complete'])
def test_committed_outer_action_refreshes_only_safe_level_growth(tmp_path, monkeypatch, mode):
    runtime,reader,_=runtime_fixture(tmp_path, count=1)
    source,target=red_internal_species_id(77),red_internal_species_id(78)
    venues=(native.context.ROUTE_11_TRAINING_VENUE,native.context.DIGLETTS_CAVE_TRAINING_VENUE)
    reader.raw=replace(reader.raw,map_id=venues[0].map_id,
        party_species_ids=(*reader.raw.party_species_ids[:5],source),
        party_levels=(*reader.raw.party_levels[:5],35))
    progress={'xp':1000,'calls':0};queries=[];geometries=[];state_objects=[];training=[];retained=[]
    def party():
        observed=runtime.adapter.observe().party
        return replace(observed,members=tuple(replace(m,experience=progress['xp'])for m in observed.members))
    monkeypatch.setattr(native,'PokemonRedPartyReader',lambda _:SimpleNamespace(read=party))
    monkeypatch.setattr(native,'wild_tables',lambda _: {v.map_id:((10,165),)for v in venues})
    monkeypatch.setattr(native,'collection_finisher',lambda *a,**k:party().members[0])
    monkeypatch.setattr(native,'native_evolution_encounter_supported',lambda *a,**k:True)
    monkeypatch.setattr(native,'prepare_native_training_center',lambda *a,**k:None)
    monkeypatch.setattr(native,'restore_native_center_party',lambda *a,**k:0)
    monkeypatch.setattr(native,'_restore_native_cave_venue_resources',lambda *a,**k:0)
    from test_party_development_outcome_learning import _initialized_model
    from pokemon_red_completion.party_development_outcome_learning import (
        upgrade_party_development_model_for_workload,
        canonical_party_development_outcome_model_sha256,
    )
    model=upgrade_party_development_model_for_workload(_initialized_model())
    model_sha=canonical_party_development_outcome_model_sha256(model)
    def predict(self,candidates):
        queries.append((candidates.level,candidates.bindings))
        return 0 if len(queries)==1 else 1
    monkeypatch.setattr(type(model),'predict',predict)
    def menu(observation,**kw):
        bindings=tuple(v.band for v in kw['venues'])
        candidate=SimpleNamespace(level=observation.party.members[-1].level,bindings=bindings,
            public_dict=lambda:{'unit_fixture':True,'candidates':list(range(len(bindings)))})
        return SimpleNamespace(bindings=bindings,candidate_set=candidate,
            candidate_available=(True,)*len(bindings),semantic_snapshot_sha256='c'*64)
    monkeypatch.setattr(adapter,'build_native_evolution_venue_menu',menu)
    from pokemon_red_completion import red_native_venue_geometry as geometry
    def quote(actual_runtime,world,observation,actual_venues):
        geometries.append((observation.party.members[-1].level,tuple(v.map_id for v in actual_venues)))
        return tuple(SimpleNamespace(public_dict=lambda:{'unit_fixture':True})for _ in actual_venues)
    monkeypatch.setattr(geometry,'quote_native_evolution_venue_geometry',quote)
    original_select=native.select_native_evolution_model_venue
    def capture(observation,**kw):
        state=kw['choice_state'];state_objects.append(state)
        state.setdefault('helper_xp_admission_seen','preserve-helper-certificate')
        selected=original_select(observation,**kw)
        assert state['trainee_initial_xp']==1000
        assert state['helper_xp_admission_seen']=='preserve-helper-certificate'
        assert state['action_scope']==(source,target,model_sha,True)
        return selected
    monkeypatch.setattr(native,'select_native_evolution_model_venue',capture)
    def train(actions,*args,**kw):
        progress['calls']+=1;training.append(tuple(v.map_id for v in kw['venues']))
        assert kw['evolution_target']==(source,target)
        actions.execute(MacroAction(MacroActionKind.WAIT))
        if mode=='exception':raise RuntimeError('retained component failure')
        if mode=='fainted':reader.raw=replace(reader.raw,party_hp=(*reader.raw.party_hp[:5],0))
        if mode=='lost':reader.boxes=replace(reader.boxes,boxes=(RedCurrentBoxState(0,(),()),*reader.boxes.boxes[1:]))
        if mode!='no_xp':progress['xp']+=200
        if mode=='growth':reader.raw=replace(reader.raw,party_levels=(*reader.raw.party_levels[:5],36))
        if mode=='complete':
            reader.raw=replace(reader.raw,party_species_ids=(*reader.raw.party_species_ids[:5],target))
            return None,4,0
        raise EvolutionTrainingPaused(4,0)
    monkeypatch.setattr(native.context,'run_red_team_balancing',train)
    bound=native.bind_native_boxed_evolution(runtime,SimpleNamespace(rom=b'unit-fixture'),
        maximum_quanta=2,training_venues=venues,venue_model=model,venue_model_sha256=model_sha,
        retain_quantum=lambda:retained.append(progress['calls']))
    actions=CountingExecutor(SimpleNamespace(execute=lambda action:action))
    if mode in {'no_xp','fainted','lost','exception'}:
        with pytest.raises(RuntimeError):bound.party_level_evolution_executor(source,target,actions)
        assert progress['calls']==len(queries)==len(geometries)==1
        assert retained==[]
    else:
        report=bound.party_level_evolution_executor(source,target,actions)
        expected=2 if mode=='growth' else 1
        assert len(queries)==len(geometries)==expected
        if mode=='growth':
            assert [q[0]for q in queries]==[35,36]
            assert training==[(venues[0].map_id,),(venues[1].map_id,)]
        elif mode=='same_level':assert training==[(venues[0].map_id,)]*2
        else:assert progress['calls']==1 and 'evolution_partial'not in report.evidence
        assert retained==list(range(1,progress['calls']+1))
    assert actions.actions_executed==progress['calls']
    assert all(s is state_objects[0]for s in state_objects)
    assert all(q[1]==tuple(v.band for v in venues)for q in queries)
    assert all(q[1]==tuple(v.map_id for v in venues)for q in geometries)
    # Existing PC custody contains the unselected precursor throughout.
    if mode!='lost':assert reader.boxes.boxes[0].species_ids==(source,)
