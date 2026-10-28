"""The measured helper-only regime is durable without changing legacy players."""
import json
from dataclasses import replace
from types import SimpleNamespace as N
import pytest
from pokemon_red_completion import red_player_configuration as configuration
from pokemon_red_completion import red_native_boxed_evolution as native
from pokemon_red_completion import red_goal_context as context
from test_native_venue_player_bridge import model_record
from test_red_player_configuration import config


@pytest.mark.parametrize('route_work', [False, True])
def test_helper_configuration_roundtrip_keeps_mode_and_identity(model_record, route_work):
    original=replace(model_record.configuration, quote_capture_route_work=route_work)
    opted=replace(original,evolution_allow_direct_fights=False)
    document=json.loads(json.dumps(opted.to_dict()))
    assert document['schema']==configuration.HELPER_VENUE_SCHEMA
    assert document['evolution_allow_direct_fights'] is False
    restored=configuration.RedPlayerConfiguration.from_dict(document)
    assert restored==opted and restored.sha256==opted.sha256!=original.sha256
    policy=configuration._configured_native_venue_policy(restored,model_record.model)
    assert policy.allow_direct_evolution is False and policy.model_sha256==model_record.canonical
    assert replace(restored,evolution_allow_direct_fights=True).to_dict()==original.to_dict()


@pytest.mark.parametrize('bad',[None,0,1,'false'])
def test_helper_configuration_never_coerces_modes(model_record,bad):
    with pytest.raises(ValueError,match='explicit boolean'):
        replace(model_record.configuration,evolution_allow_direct_fights=bad)
    with pytest.raises(ValueError,match='explicit boolean'):
        native.NativeEvolutionVenuePolicy(model_record.model,model_record.canonical,
            (context.ROUTE_11_TRAINING_VENUE,context.DIGLETTS_CAVE_TRAINING_VENUE),bad)


@pytest.mark.parametrize('bad',[None,0,1,True,'false','missing'])
def test_version_four_requires_explicit_false(model_record,bad):
    document=replace(model_record.configuration,evolution_allow_direct_fights=False).to_dict()
    if bad=='missing':document.pop('evolution_allow_direct_fights')
    else:document['evolution_allow_direct_fights']=bad
    with pytest.raises(ValueError,match='schema'):
        configuration.RedPlayerConfiguration.from_dict(document)


@pytest.mark.parametrize('schema',[configuration.SCHEMA,configuration.ROUTE_WORK_SCHEMA,configuration.VENUE_SCHEMA])
def test_old_schema_cannot_hide_helper_mode(model_record,schema):
    document=replace(model_record.configuration,evolution_allow_direct_fights=False).to_dict()
    document['schema']=schema
    with pytest.raises(ValueError,match='schema'):
        configuration.RedPlayerConfiguration.from_dict(document)


def test_helper_mode_requires_a_declared_learned_venue_policy():
    with pytest.raises(ValueError,match='configured venue model'):
        replace(config(),evolution_allow_direct_fights=False)


@pytest.mark.parametrize('policy_direct,local_direct',[(True,True),(True,False),(False,True),(False,False)])
def test_policy_and_local_limits_reach_actual_trainer(tmp_path,monkeypatch,model_record,policy_direct,local_direct):
    from test_red_native_boxed_evolution import runtime_fixture
    from test_red_goal_context import _ActionDelegate
    from pokemon_red_completion.red_collection import RedCurrentBoxState,red_internal_species_id
    from pokemon_red_completion.red_team_training import EvolutionVenueExhausted
    from pokemon_red_completion.executor import CountingExecutor
    from pokemon_red_completion.observation import MapId
    runtime,reader,_=runtime_fixture(tmp_path)
    source,target=red_internal_species_id(77),red_internal_species_id(78)
    reader.raw=replace(reader.raw,party_species_ids=(*reader.raw.party_species_ids[:5],source),party_levels=(63,55,55,55,55,33))
    reader.boxes=replace(reader.boxes,boxes=(RedCurrentBoxState(0,(source,),(30,)),*reader.boxes.boxes[1:]))
    venues=(context.ROUTE_11_TRAINING_VENUE,context.DIGLETTS_CAVE_TRAINING_VENUE)
    runtime=replace(runtime,native_evolution_venue_policy=native.NativeEvolutionVenuePolicy(
        model_record.model,model_record.canonical,venues,policy_direct))
    calls=[]
    def train(actions,*args,**kwargs):
        calls.append(kwargs)
        raise EvolutionVenueExhausted(0,0)
    monkeypatch.setattr(context,'run_red_team_balancing',train)
    monkeypatch.setattr(native,'prepare_native_training_center',lambda *a:None)
    monkeypatch.setattr(native,'restore_native_center_party',lambda *a:0)
    monkeypatch.setattr(native,'PokemonRedPartyReader',lambda _:N(read=lambda:N(members=(N(species_id=source,experience=100),))))
    monkeypatch.setattr(native,'wild_tables',lambda _:{int(MapId.ROUTE_11):[(10,0x21)]})
    monkeypatch.setattr(native,'select_native_evolution_model_venue',lambda *a,**kw:venues[0])
    bound=native.bind_native_boxed_evolution(runtime,N(rom=b'fixture'),allow_direct_evolution=local_direct)
    actions=CountingExecutor(_ActionDelegate())
    report=bound.party_level_evolution_executor(source,target,actions)
    assert len(calls)==1 and calls[0]['allow_direct_evolution'] is (policy_direct and local_direct)
    assert calls[0]['collection_shared_experience'] is True
    assert report.evidence['evolution_partial'] is True
    assert actions.actions_executed==runtime.emulator.frame_count==0


@pytest.mark.parametrize('route_work',[False,True])
def test_fresh_realization_preserves_the_explicit_mode(model_record,route_work):
    import run_fresh_red_player as fresh
    configured=replace(model_record.configuration,evolution_allow_direct_fights=False,
        quote_capture_route_work=route_work)
    template=dict(configured.to_dict(),quote_capture_route_work=route_work)
    realized=fresh.realized_configuration(template,origin_sha256='d'*64,
        origin_id='unit-opening',starter_ref='unit-starter',teacher_profiles=())
    assert realized.evolution_allow_direct_fights is False
    assert realized.evolution_venue_model_sha256==model_record.canonical
    assert realized.evolution_venue_scope==configured.evolution_venue_scope
    assert configuration.RedPlayerConfiguration.from_dict(json.loads(json.dumps(realized.to_dict())))==realized
