from types import SimpleNamespace as N
import pytest
from pokemon_red_completion import blaine
from pokemon_red_completion.observation import MapId


class Healed(Exception):
    pass


def setup_return(monkeypatch):
    raw = N(map_id=MapId.ROUTE_11, player_x=23, player_y=14, battle_state=0)
    reader = N(read=lambda: raw)
    calls = []

    def pulse(*args):
        raw.map_id = MapId.VERMILION_CITY

    def move(actions, reader, route, label):
        calls.append(label)
        if label == 'team training Vermilion Center return':
            raise blaine.BlaineChapterError('legacy path blocked by a live town object')
        if label == 'team training Vermilion Center entry':
            raw.map_id, raw.player_x, raw.player_y = MapId.VERMILION_POKECENTER, 3, 7
        elif label == 'team training Vermilion nurse':
            raw.player_y = 3

    def heal(*args):
        assert raw.map_id == MapId.VERMILION_POKECENTER
        assert (raw.player_x, raw.player_y) == (3, 3)
        raise Healed

    monkeypatch.setattr(blaine, '_pulse', pulse)
    monkeypatch.setattr(blaine, '_move', move)
    monkeypatch.setattr(blaine, '_heal', heal)
    return raw, reader, calls


def test_route11_uses_existing_live_ground_return_when_supplied(monkeypatch):
    raw, reader, calls = setup_return(monkeypatch)
    actions, emulator = object(), object()
    routed = []

    def ground(a, r, e):
        assert (a, r, e) == (actions, reader, emulator)
        assert raw.map_id == MapId.VERMILION_CITY
        routed.append(True)
        raw.player_x, raw.player_y = 11, 4

    with pytest.raises(Healed):
        blaine._route_11_heal_and_return(actions, reader, emulator, ground_transition=ground)
    assert routed == [True]
    assert 'team training Vermilion Center return' not in calls


def test_no_ground_capability_keeps_the_original_legacy_default(monkeypatch):
    _, reader, calls = setup_return(monkeypatch)
    with pytest.raises(blaine.BlaineChapterError, match='legacy path blocked'):
        blaine._route_11_heal_and_return(object(), reader, object())
    assert 'team training Vermilion Center return' in calls
