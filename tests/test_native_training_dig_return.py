"""Native venue recovery authenticates Dig before legacy outdoor transport."""

from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_dig_recovery import scene

from pokemon_red_completion import blaine as b
from pokemon_red_completion import red_dig_recovery as dig
from pokemon_red_completion import red_native_boxed_evolution as n
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.observation import Badge, MapId


def setup(monkeypatch, anchor=7, landing=(28, 19), *, fly=True):
    router, _, _, state, _, calls = scene(monkeypatch)
    reader = router.runtime.reader
    state["raw"] = replace(
        state["raw"],
        map_id=MapId.DIGLETTS_CAVE,
        badge_bits=int(Badge.THUNDER),
        party_moves=((19 if fly else 33, 2), (91, 4)),
    )
    reader.read_last_blackout_map = lambda: anchor
    reader.read_fly_destinations = lambda: (int(MapId.VERMILION_CITY),)
    monkeypatch.setattr(dig, "red_fly_landings", lambda _rom: ((anchor, landing),))
    router.world.local_graphs = {anchor: NS(edges={landing: ()})}
    router.world.object_blockers = {anchor: frozenset()}
    monkeypatch.setattr(n, "Gen1TraversalObserver", dig.Gen1TraversalObserver)

    def escape(actions, _reader, _emulator, *, expected_map):
        assert expected_map == anchor
        actions.execute(MacroAction(MacroActionKind.WAIT))
        state["raw"] = replace(
            state["raw"], map_id=anchor, player_y=landing[0], player_x=landing[1]
        )
        calls.append("dig")

    monkeypatch.setattr(dig, "_field_dig", escape)
    return router, state, calls


@pytest.mark.parametrize(
    "anchor,landing", [(7, (28, 19)), (1, (7, 4)), (8, (12, 11)), (5, (4, 11))]
)
def test_exact_escape_then_existing_generic_fly_and_local_healing(monkeypatch, anchor, landing):
    router, state, calls = setup(monkeypatch, anchor, landing, fly=anchor != 5)
    reader = router.runtime.reader

    def legacy_dig_forbidden(*a, **kw):
        raise AssertionError("legacy chapter town whitelist must not own this escape")

    def fly(actions, active_reader, emulator, destination, label):
        assert active_reader is reader and destination == MapId.VERMILION_CITY
        assert (reader.read().map_id, reader.read().player_y, reader.read().player_x) == (
            anchor,
            *landing,
        )
        calls.append("fly")
        state["raw"] = replace(state["raw"], map_id=MapId.VERMILION_CITY, player_x=11, player_y=4)

    def move(actions, active_reader, route, label, **kw):
        endpoints = {
            "team training Vermilion Center entry": (MapId.VERMILION_POKECENTER, 3, 7),
            "team training Vermilion nurse": (MapId.VERMILION_POKECENTER, 3, 3),
            "team training Vermilion Center exit": (MapId.VERMILION_CITY, 11, 4),
            "team training Route 11 return": (MapId.ROUTE_11, 8, 4),
        }
        m, x, y = endpoints[label]
        state["raw"] = replace(state["raw"], map_id=m, player_x=x, player_y=y)

    monkeypatch.setattr(b, "_field_dig", legacy_dig_forbidden)
    monkeypatch.setattr(b, "_fly_to_town", fly)
    monkeypatch.setattr(
        b,
        "_field_fly_to_vermilion_from_cinnabar",
        lambda a, r, e: fly(a, r, e, MapId.VERMILION_CITY, "cinnabar"),
    )
    monkeypatch.setattr(b, "_move", move)
    monkeypatch.setattr(b, "_heal", lambda *a: calls.append("heal"))
    monkeypatch.setattr(b, "_pulse", lambda *a, **kw: None)
    n._native_route_11_heal_and_return(
        router.actions,
        reader,
        router.runtime.emulator,
        world=router.world,
        ground_transition=object(),
    )
    assert calls == (["dig", "heal"] if anchor == 5 else ["dig", "fly", "heal"])
    assert reader.read().map_id == MapId.ROUTE_11


@pytest.mark.parametrize("fault", ["map", "position", "dialogue", "party_pp", "exception"])
def test_bad_native_escape_never_reaches_legacy_return(monkeypatch, fault):
    router, state, calls = setup(monkeypatch)
    original = dig._field_dig

    def broken(*a, **kw):
        original(*a, **kw)
        if fault == "exception":
            raise RuntimeError("retained native failure")
        if fault == "dialogue":
            router.runtime.reader.read_bottom_dialogue_box_visible = lambda: True
        else:
            changes = {
                "map": dict(map_id=8),
                "position": dict(player_x=18),
                "party_pp": dict(party_pp=((1, 1), (1, 1))),
            }
            state["raw"] = replace(state["raw"], **changes[fault])

    monkeypatch.setattr(dig, "_field_dig", broken)
    monkeypatch.setattr(n, "_route_11_heal_and_return", lambda *a, **kw: calls.append("legacy"))
    with pytest.raises(RuntimeError):
        n._native_route_11_heal_and_return(
            router.actions,
            router.runtime.reader,
            router.runtime.emulator,
            world=router.world,
            ground_transition=object(),
        )
    assert calls == ["dig"]


@pytest.mark.parametrize("fault", ["fly", "destination", "unsupported_anchor"])
def test_escape_without_onward_return_is_rejected_before_input(monkeypatch, fault):
    router, state, calls = setup(
        monkeypatch, anchor=0 if fault == "unsupported_anchor" else 7, fly=fault != "fly"
    )
    if fault == "destination":
        router.runtime.reader.read_fly_destinations = lambda: ()
    monkeypatch.setattr(n, "_route_11_heal_and_return", lambda *a, **kw: calls.append("legacy"))
    with pytest.raises(n.context.RedGoalContextError, match="onward training return"):
        n._native_route_11_heal_and_return(
            router.actions,
            router.runtime.reader,
            router.runtime.emulator,
            world=router.world,
            ground_transition=object(),
        )
    assert calls == [] and router.actions.actions_executed == 0


def test_no_dig_plan_preserves_the_existing_ground_fallback(monkeypatch):
    router, state, calls = setup(monkeypatch)
    state["raw"] = replace(state["raw"], party_moves=((19, 2), (33, 4)))
    ground = object()

    def legacy(*a, **kw):
        assert kw == dict(ground_transition=ground)
        assert state["raw"].map_id == MapId.DIGLETTS_CAVE
        calls.append("legacy-ground")

    monkeypatch.setattr(n, "_route_11_heal_and_return", legacy)
    n._native_route_11_heal_and_return(
        router.actions,
        router.runtime.reader,
        router.runtime.emulator,
        world=router.world,
        ground_transition=ground,
    )
    assert calls == ["legacy-ground"] and router.actions.actions_executed == 0


def test_canonical_route11_uses_the_same_recovery_seam(monkeypatch):
    world = NS(rom=b"rom")
    ground = object()
    calls = []
    ports = (object(), object(), object())
    monkeypatch.setattr(n, "RedVermilionGroundTransition", lambda **kw: ground)
    monkeypatch.setattr(
        n, "_native_route_11_heal_and_return", lambda *a, **kw: calls.append((a, kw))
    )
    base = n.context.ROUTE_11_TRAINING_VENUE
    wrapped = n._with_native_cave_ground_recovery(base, world)
    assert calls == [] and wrapped.band is base.band
    wrapped.heal_and_return(*ports)
    assert calls == [(ports, dict(world=world, ground_transition=ground))]
