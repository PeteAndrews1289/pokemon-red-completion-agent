from dataclasses import replace

import pytest

from pokemon_red_completion.observation import MapId, OaksErrandPhase, OaksErrandState


def source():
    return OaksErrandState(phase=OaksErrandPhase.UNKNOWN,joy_ignore=252,
        lab_script=16,mart_script=2,battled_rival=True,got_oaks_parcel=True,
        oak_got_parcel=False,got_pokedex=False,parcel_in_bag=False,
        first_party_species=177,first_party_level=6,first_party_hp=22,
        first_party_max_hp=22,battle_result=2,map_id=MapId.OAKS_LAB,battle_state=0)


def test_observed_boundary_is_continuation_not_completion():
    assert source().pokedex_departure_dialogue
    assert not source().pokedex_snapshot


@pytest.mark.parametrize("field,value", [
    ("map_id",MapId.VIRIDIAN_MART),("battle_state",1),("lab_script",18),
    ("lab_script",15),("joy_ignore",0),("battled_rival",False),
    ("got_oaks_parcel",False),("parcel_in_bag",True),("oak_got_parcel",True),
    ("got_pokedex",True),("first_party_species",153),
])
def test_contradictions_cannot_authorize_recovery(field,value):
    assert not replace(source(),**{field:value}).pokedex_departure_dialogue
