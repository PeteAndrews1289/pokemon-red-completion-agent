import pytest
from test_observation import RecordingMemory

from pokemon_red_completion.observation import PokemonRedStateReader, SemanticStateError


@pytest.mark.parametrize("stage", range(5))
def test_ship_rival_persistent_phase_is_read_even_outside_ship(stage):
    memory = RecordingMemory({0xD35E: 89, 0xD665: stage, 0xDA39: 255})
    assert PokemonRedStateReader(memory).read_ss_anne_rival_script() == stage
    assert memory.reads == [0xD665]


@pytest.mark.parametrize("stage", [5, 255])
def test_ship_rival_unknown_phase_is_not_a_victory(stage):
    with pytest.raises(SemanticStateError):
        PokemonRedStateReader(RecordingMemory({0xD665: stage})).read_ss_anne_rival_script()
