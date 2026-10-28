from dataclasses import replace
from types import SimpleNamespace
import pytest
from test_red_party import memory_with
from test_red_player_member_preparation import roster,offers
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.red_party import PokemonRedPartyReader,PartyReadError,party_observation_from_raw
from pokemon_red_completion.red_party_pp import decode_red_party_pp

def raw(moves=(33,0,0,0),pp=(7,0,0,0)):
    return RawGameState(game_started=True,map_id=1,player_x=0,player_y=0,party_count=1,battle_state=0,
        party_species_ids=(165,),party_levels=(17,),party_hp=(40,),party_max_hp=(40,),party_status=(0,),
        party_moves=(moves,),party_pp=(pp,))

@pytest.mark.parametrize('ups',range(4))
def test_both_party_adapters_preserve_pp_up_capacity_and_current_pp(ups):
    packed=(ups<<6)|7
    expected=decode_red_party_pp((33,0,0,0),(packed,0,0,0)).moves[0]
    direct=PokemonRedPartyReader(memory_with(dict(species_id=165,level=17,hp=40,max_hp=40,
        moves=(33,0,0,0),pp=(packed,0,0,0),experience=17**3))).read().members[0]
    projected=party_observation_from_raw(raw(pp=(packed,0,0,0))).members[0]
    assert direct.moves==projected.moves
    assert direct.moves[0].current_pp==7 and direct.moves[0].max_pp==expected.maximum_pp
    assert all(m.move_id==0 and m.current_pp==0 and m.max_pp is None for m in direct.moves[1:])

def test_maximum_61_is_not_clipped_to_ordinary_remaining_pp_ceiling():
    member=party_observation_from_raw(raw(moves=(45,0,0,0),pp=(0xfd,0,0,0))).members[0]
    assert (member.moves[0].current_pp,member.moves[0].max_pp)==(61,61)

def test_unknown_move_retains_current_pp_without_invented_max_and_known_siblings_stay_known():
    member=party_observation_from_raw(raw(moves=(33,255,0,0),pp=(7,0xc9,0,0))).members[0]
    assert (member.moves[0].current_pp,member.moves[0].max_pp)==(7,35)
    assert member.moves[1].move_id==255 and member.moves[1].current_pp==9 and member.moves[1].max_pp is None

@pytest.mark.parametrize('moves,pp',[((),()),((33,),(0xc7,)),((33,0),(0xc7,0))])
def test_legacy_short_semantic_move_tuples_keep_their_shape(moves,pp):
    member=party_observation_from_raw(raw(moves=moves,pp=pp)).members[0]
    assert len(member.moves)==len(moves)
    if moves:assert (member.moves[0].current_pp,member.moves[0].max_pp)==(7,56)

@pytest.mark.parametrize('moves,pp',[
    ((33,0,0,0),(36,0,0,0)),((33,0,0,0),(7,1,0,0)),
    ((33,0,0,0),(7,0,0)),((33,0,0,0),(-1,0,0,0)),
])
def test_incoherent_pp_fails_at_adapter_boundary(moves,pp):
    with pytest.raises(PartyReadError):party_observation_from_raw(raw(moves=moves,pp=pp))

def test_real_preparation_descriptor_now_observes_fraction_without_new_resolver_or_memory_reads():
    mon=PokemonRedPartyReader(memory_with(dict(species_id=165,level=17,hp=40,max_hp=40,
        moves=(33,0,0,0),pp=(0xc7,0,0,0),experience=17**3))).read().members[0]
    members=roster();members=(replace(members[0],observation=mon),*members[1:])
    _,choices=offers(members)
    descriptor=next(descriptor for intent,descriptor in choices if intent.targets[0][0]==members[0].specimen_ref)
    assert descriptor.pp_fraction==7/56
