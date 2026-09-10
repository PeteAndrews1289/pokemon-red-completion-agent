"""Literal live-address fixtures for final-room scene observation only."""

from dataclasses import FrozenInstanceError

import pytest
from test_observation import RecordingMemory

from pokemon_red_completion.observation import (
    FinalLeagueScene,
    PokemonRedStateReader,
    SemanticStateError,
)


def memory(*, map_id=120, champion=2, hall=1, starter=153, queue=7, flags=0):
    return RecordingMemory({
        0xD35E: map_id, 0xD64C: champion, 0xD64B: hall, 0xDA39: 255,
        0xD715: starter, 0xCD38: queue, 0xD730: flags,
        0xCC57: 255, 0xD057: 255, 0xD059: 201,
    })


@pytest.mark.parametrize("map_id,address,expected", [
    (120, 0xD64C, 2), (118, 0xD64B, 1), (113, 0xD64C, 2),
])
def test_map_selects_its_own_script_not_ordinary_trainer_alias(map_id, address, expected):
    source = memory(map_id=map_id, flags=0x20)
    scene = PokemonRedStateReader(source).read_final_league_scene()
    assert scene == FinalLeagueScene(map_id, expected, 153, 7, True)
    assert source.reads == [0xD35E, address, 0xD715, 0xCD38, 0xD730]
    assert 0xDA39 not in source.reads
    with pytest.raises(FrozenInstanceError):
        scene.script_stage = 0


@pytest.mark.parametrize("map_id,stage", [(120, 0), (120, 10), (118, 0), (118, 3), (113, 10)])
def test_map_specific_stage_endpoints_are_admitted(map_id, stage):
    source = memory(map_id=map_id, champion=stage, hall=stage)
    assert PokemonRedStateReader(source).read_final_league_scene().script_stage == stage


@pytest.mark.parametrize("map_id,stage", [(120, 11), (120, 255), (118, 4), (118, 255), (113, 11)])
def test_unrecognized_stage_refuses_without_interpreting_queue(map_id, stage):
    source = memory(map_id=map_id, champion=stage, hall=stage)
    with pytest.raises(SemanticStateError, match="fields"):
        PokemonRedStateReader(source).read_final_league_scene()
    assert 0xCD38 not in source.reads and 0xD730 not in source.reads


@pytest.mark.parametrize("map_id", [0, 112, 114, 117, 119, 121, 255])
def test_other_maps_never_read_a_final_scene_stage(map_id):
    source = memory(map_id=map_id)
    with pytest.raises(SemanticStateError, match="maps"):
        PokemonRedStateReader(source).read_final_league_scene()
    assert source.reads == [0xD35E]


@pytest.mark.parametrize("starter", [0, 191, 255])
def test_invalid_starter_refuses(starter):
    with pytest.raises(SemanticStateError):
        PokemonRedStateReader(memory(starter=starter)).read_final_league_scene()


@pytest.mark.parametrize("starter", [1, 153, 176, 190])
@pytest.mark.parametrize("queue", [0, 1, 100])
def test_starter_and_queue_are_observed_without_stage_or_victory_inference(starter, queue):
    scene = PokemonRedStateReader(memory(starter=starter, queue=queue)).read_final_league_scene()
    assert scene.rival_starter == starter and scene.queued_movement == queue
    assert scene.script_stage == 2 and scene.npc_moving is False


@pytest.mark.parametrize("flags,moving", [
    (0, False), (1, True), (0x20, True), (0x80, True),
    (0xA1, True), (2, False), (0x40, False), (0x5E, False),
])
def test_only_declared_scripted_movement_bits_mark_npc_moving(flags, moving):
    scene = PokemonRedStateReader(memory(flags=flags, queue=0)).read_final_league_scene()
    assert scene.npc_moving is moving
    assert scene.queued_movement == 0
