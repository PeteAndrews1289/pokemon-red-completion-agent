"""Existing switch/shared-XP mode stays explicit through both adapters."""
from dataclasses import replace
import inspect
from types import SimpleNamespace as N
import pytest
from pokemon_red_completion import red_native_boxed_evolution as native
from pokemon_red_completion import red_level_evolution_options as options
from pokemon_red_completion.red_team_training import EvolutionVenueExhausted
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import MapId,ItemId
from pokemon_red_completion.red_collection import red_internal_species_id
from pokemon_red_completion.gen1_cartridge import Evolution,EvolutionMethod
from test_red_native_boxed_evolution import runtime_fixture
from test_red_goal_context import _ActionDelegate
from test_red_native_boxed_item_evolution import _runtime
from test_red_live_option_menu import _binding

@pytest.mark.parametrize('bad',[None,0,1,'false'])
def test_native_mode_rejects_non_boolean_before_runtime_access(bad):
    with pytest.raises(ValueError,match='explicit boolean'):
        native.bind_native_boxed_evolution(None,None,allow_direct_evolution=bad)

@pytest.mark.parametrize('bad',[None,0,1,'false'])
def test_enumeration_mode_rejects_non_boolean_before_runtime_access(bad):
    with pytest.raises(ValueError,match='explicit booleans'):
        options.enumerate_red_level_evolutions(None,None,None,None,maximum_actions=3000,maximum_frames=300000,allow_direct_evolution=bad)

def test_both_historical_defaults_are_direct_fight_enabled():
    for function in [native.bind_native_boxed_evolution,options.enumerate_red_level_evolutions]:
        assert inspect.signature(function).parameters['allow_direct_evolution'].default is True

@pytest.mark.parametrize('mode',[None,True,False])
def test_existing_native_training_receives_mode_and_shared_xp(tmp_path,monkeypatch,mode):
    runtime,reader,_=runtime_fixture(tmp_path)
    source,target=red_internal_species_id(77),red_internal_species_id(78)
    reader.raw=replace(reader.raw,party_species_ids=(*reader.raw.party_species_ids[:5],source),party_levels=(63,55,55,55,55,33))
    from pokemon_red_completion.red_collection import RedCurrentBoxState
    reader.boxes=replace(reader.boxes,boxes=(RedCurrentBoxState(0,(source,),(30,)),*reader.boxes.boxes[1:]))
    received=[]
    def train(actions,*args,**kwargs):
        received.append(kwargs)
        raise EvolutionVenueExhausted(0,0)
    monkeypatch.setattr(native.context,'run_red_team_balancing',train)
    monkeypatch.setattr(native,'prepare_native_training_center',lambda *args:None)
    monkeypatch.setattr(native,'restore_native_center_party',lambda *args:0)
    monkeypatch.setattr(native,'PokemonRedPartyReader',lambda _:N(read=lambda:N(members=(N(species_id=source,experience=100),))))
    monkeypatch.setattr(native,'wild_tables',lambda _:{int(MapId.ROUTE_11):[(10,0x21)]})
    bound=native.bind_native_boxed_evolution(runtime,N(rom=b'fixture'),**({}if mode is None else{'allow_direct_evolution':mode}))
    actions=CountingExecutor(_ActionDelegate())
    report=bound.party_level_evolution_executor(source,target,actions)
    assert len(received)==1 and received[0]['allow_direct_evolution']is(mode is not False)
    assert received[0]['collection_shared_experience']is True
    assert report.evidence['evolution_partial']is True
    assert actions.actions_executed==runtime.emulator.frame_count==0

@pytest.mark.parametrize('mode',[None,True,False])
def test_real_enumerator_forwards_opt_in_without_changing_default_kwargs(tmp_path,monkeypatch,mode):
    runtime,reader=_runtime(tmp_path,monkeypatch,source=58,target=59,item=ItemId.FIRE_STONE)
    from pokemon_red_completion.red_collection import RedCurrentBoxState
    reader.boxes=replace(reader.boxes,boxes=(RedCurrentBoxState(0,(red_internal_species_id(98),),(30,)),*reader.boxes.boxes[1:]))
    owned=reader.read_pokedex_state().owned_species|{98}
    reader.read_pokedex_state=lambda:N(seen_species=owned,owned_species=owned)
    observed=runtime.adapter.observe()
    monkeypatch.setattr(options,'evolution_graph',lambda _:{98:(Evolution(98,99,EvolutionMethod.LEVEL,28),)})
    received=[]
    def bind(actual,world,**kwargs):
        received.append(kwargs)
        return N(provider_for=lambda *args:N(offer=lambda _:N(binding=_binding(GoalKind.EVOLVE_SPECIES,binding_ref='copied-option',calls=[]),unavailable_reason=None)))
    monkeypatch.setattr(options,'bind_native_boxed_evolution',bind)
    actions=CountingExecutor(_ActionDelegate());before=reader.read()
    rows=options.enumerate_red_level_evolutions(runtime,observed,actions,N(rom=b'fixture'),maximum_actions=3000,maximum_frames=300000,**({}if mode is None else{'allow_direct_evolution':mode}))
    expected={'maximum_quanta':128,'allow_cross_box':True}
    if mode is False:expected['allow_direct_evolution']=False
    assert len(rows)==1 and received==[expected]
    assert reader.read()==before and actions.actions_executed==runtime.emulator.frame_count==0
