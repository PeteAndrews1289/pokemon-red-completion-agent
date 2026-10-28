from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.observation import EventFlag, MapId
from pokemon_red_completion.red_league_entry import (
    LeagueLobbyResetObserver,
    forecast_league_entry_events,
)
from pokemon_red_completion.red_league_funding import projected_fresh_league_events
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot


def test_projection_preserves_source_and_clears_latched_entrance_event():
    flags = bytearray(320)
    flags[2278 // 8] = 1 << (2278 % 8)
    source = bytes(flags)
    projected, changed = projected_fresh_league_events(source, challenge_started=True)
    assert changed and projected[2278 // 8] == 0 and source == bytes(flags)
    untouched, changed = projected_fresh_league_events(source, challenge_started=False)
    assert untouched == source and not changed


@pytest.mark.parametrize('location', [MapId.INDIGO_PLATEAU,MapId.INDIGO_PLATEAU_LOBBY,
                                      MapId.LORELEIS_ROOM,MapId.VIRIDIAN_CITY])
@pytest.mark.parametrize('permission', [False,True])
def test_forecast_requires_explicit_retry_and_observed_outside_reset(location,permission):
    flags=bytearray(320)
    flags[int(EventFlag.BEAT_LORELEI)//8]|=1<<(int(EventFlag.BEAT_LORELEI)%8)
    native=bytes(flags)
    observed=SimpleNamespace(map_id=location,battle_state=0,event_flags=native)
    result=forecast_league_entry_events(observed,development_retry_reentry=permission,
                                       challenge_started=True)
    assert (result!=native) is (permission and location==MapId.INDIGO_PLATEAU)
    assert observed.event_flags is native


@pytest.mark.parametrize('argument,value', [('development_retry_reentry',1),
    ('development_retry_reentry',None),('challenge_started',1),('challenge_started','yes')])
def test_forecast_rejects_coerced_permissions(argument,value):
    observed=SimpleNamespace(map_id=MapId.INDIGO_PLATEAU,battle_state=0,event_flags=bytes(320))
    with pytest.raises(TypeError):
        forecast_league_entry_events(observed,**{argument:value})


def fixture():
    state = SimpleNamespace(snapshot=TraversalSnapshot(9, (6, 9), True),
                            events=bytes(320), started=True)
    reader = SimpleNamespace(read=lambda: SimpleNamespace(event_flags=state.events),
                             read_league_challenge_started=lambda: state.started)
    observer = LeagueLobbyResetObserver(SimpleNamespace(observe=lambda: state.snapshot),
                                       reader, bytes(320))
    return state, observer


def test_only_settled_observed_reset_authorizes_room_transition():
    state, observer = fixture()
    observer.observe()
    assert not observer.verified
    state.snapshot = TraversalSnapshot(174, (11, 7), False)
    observer.observe()
    assert not observer.verified
    state.started = False
    state.snapshot = replace(state.snapshot, ready=True)
    observer.observe()
    assert observer.verified
    state.snapshot = TraversalSnapshot(245, (5, 4), True)
    assert observer.observe() == state.snapshot


@pytest.mark.parametrize('fault', ['events', 'latch', 'no_lobby'])
def test_forecast_is_not_a_substitute_for_actual_reset(fault):
    state, observer = fixture()
    state.started = fault == 'latch'
    state.events = bytes([1]) + bytes(319) if fault == 'events' else bytes(320)
    state.snapshot = TraversalSnapshot(245 if fault == 'no_lobby' else 174, (5, 4), True)
    with pytest.raises(RouteExecutionError):
        observer.observe()
    assert not observer.verified


def test_later_lobby_drift_is_not_hidden_by_prior_verification():
    state, observer = fixture()
    state.snapshot = TraversalSnapshot(174, (11, 7), True)
    state.started = False
    observer.observe()
    state.events = bytes([1]) + bytes(319)
    with pytest.raises(RouteExecutionError):
        observer.observe()
