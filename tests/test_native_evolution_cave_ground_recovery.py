from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion import blaine as b
from pokemon_red_completion import red_native_boxed_evolution as n
from pokemon_red_completion.observation import MapId, RawGameState


@pytest.mark.parametrize("start_map,has_dig,has_route,expected", [
    (MapId.DIGLETTS_CAVE, False, True, "ground"),
    (MapId.DIGLETTS_CAVE_ROUTE_11, False, True, "ground"),
    (MapId.DIGLETTS_CAVE_ROUTE_2, False, True, "ground"),
    (MapId.DIGLETTS_CAVE, True, True, "dig"),
    (MapId.DIGLETTS_CAVE, False, False, "dig"),
    (MapId.SAFFRON_CITY, False, True, "dig"),
])
def test_cave_without_dig_uses_available_ground_route(
    monkeypatch, start_map, has_dig, has_route, expected,
):
    class Reader:
        raw = RawGameState(
            True, start_map, 37, 30, 6, 0,
            party_moves=((b.DIG if has_dig else 33,),) * 6,
        )

        def read(self):
            return self.raw

    reader = Reader()
    calls = []

    def arrive(kind, active_reader):
        calls.append(kind)
        active_reader.raw = replace(
            active_reader.raw, map_id=MapId.VERMILION_CITY,
            player_x=11, player_y=4,
        )

    def ground(_actions, active_reader, _emulator):
        arrive("ground", active_reader)

    def dig(_actions, active_reader, _emulator):
        arrive("dig", active_reader)

    def move(_actions, active_reader, _route, label, **_kwargs):
        if label == "team training Vermilion Center entry":
            active_reader.raw = replace(
                active_reader.raw, map_id=MapId.VERMILION_POKECENTER,
                player_x=3, player_y=7,
            )
        elif label == "team training Vermilion nurse":
            active_reader.raw = replace(active_reader.raw, player_x=3, player_y=3)
        elif label == "team training Vermilion Center exit":
            active_reader.raw = replace(
                active_reader.raw, map_id=MapId.VERMILION_CITY,
                player_x=11, player_y=4,
            )
        elif label == "team training Route 11 return":
            active_reader.raw = replace(
                active_reader.raw, map_id=MapId.ROUTE_11,
                player_x=8, player_y=4,
            )

    monkeypatch.setattr(b, "_move", move)
    monkeypatch.setattr(b, "_heal", lambda *_args: None)
    monkeypatch.setattr(b, "_pulse", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(b, "_training_dig_to_vermilion", dig)
    b._route_11_heal_and_return(
        object(), reader, object(), ground_transition=ground if has_route else None,
    )
    assert calls == [expected]
    assert reader.read().map_id == MapId.ROUTE_11


def test_native_builtin_cave_binds_existing_router_to_recovery(monkeypatch):
    calls = []
    route = object()
    world = SimpleNamespace(rom=b"immutable-rom")

    def make_route(**kwargs):
        assert kwargs == dict(rom=world.rom, route_world=world)
        return route

    def cave(*args, **kwargs):
        calls.append((args, kwargs))

    base = replace(n.context.DIGLETTS_CAVE_TRAINING_VENUE, heal_and_return=cave)
    monkeypatch.setattr(n.context, "DIGLETTS_CAVE_TRAINING_VENUE", base)
    monkeypatch.setattr(n, "RedVermilionGroundTransition", make_route)
    candidate = n._with_native_cave_ground_recovery(base, world)
    assert calls == []
    assert candidate.band is base.band
    assert candidate.native_transport_ready is base.native_transport_ready
    ports = (object(), object(), object())
    candidate.heal_and_return(*ports)
    assert calls[0][0] == ports
    callback = calls[0][1]["route_11_recovery"]
    assert callback.func is n._route_11_heal_and_return
    assert callback.keywords == dict(ground_transition=route)


def test_explicit_custom_cave_recovery_is_preserved():
    base = n.context.DIGLETTS_CAVE_TRAINING_VENUE
    custom = replace(base, heal_and_return=lambda *_args: None)
    assert n._with_native_cave_ground_recovery(custom, object()) is custom


def test_other_venues_keep_their_exact_recovery():
    base = n.context.ROUTE_11_TRAINING_VENUE
    assert n._with_native_cave_ground_recovery(base, object()) is base


@pytest.mark.parametrize("initial_ready,after_ready,start_map,settled,mutation,expected", [
    (True, True, MapId.DIGLETTS_CAVE, True, None, 0),
    (False, True, MapId.DIGLETTS_CAVE, True, None, 1),
    (False, False, MapId.DIGLETTS_CAVE, True, None, "error"),
    (False, True, MapId.ROUTE_11, True, None, 0),
    (False, True, MapId.DIGLETTS_CAVE, False, None, "error"),
    (False, True, MapId.DIGLETTS_CAVE, True, "cash", "error"),
    (False, True, MapId.DIGLETTS_CAVE, True, "stock", "error"),
])
def test_cave_resource_recovery_uses_metered_existing_healer(
    monkeypatch, initial_ready, after_ready, start_map, settled, mutation, expected,
):
    from pokemon_red_completion import red_team_training as training
    before_party, after_party = object(), object()
    stock = object()
    raw = SimpleNamespace(map_id=start_map, battle_state=0, bag_items=((4, 2),), player_money=8005)
    after_raw = SimpleNamespace(map_id=MapId.DIGLETTS_CAVE, battle_state=0, bag_items=((4, 2),), player_money=8004 if mutation == "cash" else 8005)
    before = SimpleNamespace(raw=raw, party=before_party, input_ready=settled, collection_observation=stock)
    after = SimpleNamespace(raw=after_raw, party=after_party, input_ready=True, collection_observation=object() if mutation == "stock" else stock)
    state = [before]
    runtime = SimpleNamespace(adapter=SimpleNamespace(observe=lambda: state[0]), reader=object(), emulator=object())
    calls, coverage = [], []
    healer = object()
    cave = SimpleNamespace(map_id=int(MapId.DIGLETTS_CAVE), is_in_map=lambda raw: raw.map_id == MapId.DIGLETTS_CAVE, heal_and_return=healer)
    route11 = SimpleNamespace(map_id=int(MapId.ROUTE_11), is_in_map=lambda raw: raw.map_id == MapId.ROUTE_11)
    encounters = {cave.map_id: ((18, 59),), route11.map_id: ((12, 108),)}
    excluded = frozenset({1})

    def covered(party, source, policy, values, **kwargs):
        assert source == 21 and policy is n.context.MANSION_TEAM_POLICY
        assert kwargs['resources'] is True
        assert kwargs['excluded_helper_species'] == excluded
        coverage.append(values)
        return initial_ready if party is before_party else after_ready

    def heal(actions, reader, emulator, callback, *, metered):
        assert callback is healer and metered is True
        assert reader is runtime.reader and emulator is runtime.emulator
        calls.append(actions)
        state[0] = after

    monkeypatch.setattr(training, "collection_encounter_coverage", covered)
    monkeypatch.setattr(training, "execute_evolution_healing_trip", heal)
    actions = object()
    invoke = lambda: n._restore_native_cave_venue_resources(
        runtime, actions, source_id=21, venues=(route11, cave), encounters=encounters,
        excluded_helper_species=excluded,
    )
    if expected == "error":
        with pytest.raises(n.context.RedGoalContextError):
            invoke()
    else:
        assert invoke() == expected
    should_heal = start_map == MapId.DIGLETTS_CAVE and not initial_ready and settled
    assert calls == ([actions] if should_heal else [])
    if initial_ready:
        assert coverage == [encounters[route11.map_id], encounters[cave.map_id]]
