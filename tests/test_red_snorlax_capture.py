from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_snorlax_capture as s
from pokemon_red_completion.gen1_traversal import MapObjectEvent
from pokemon_red_completion.observation import ItemId
from pokemon_red_completion.red_one_off_capture import OneOffCaptureBudget, OneOffCaptureRequest
from pokemon_red_completion.red_static_capture import RedStaticCaptureTarget


@pytest.mark.parametrize("fault", [None, "missing", "duplicate", "level", "coordinate"])
def test_route12_source_is_cartridge_bound(monkeypatch, fault):
    s.route12_snorlax_target.cache_clear()
    entry = N(
        species=143,
        map_id=23,
        level=31 if fault == "level" else 30,
        at=(61, 10) if fault == "coordinate" else (62, 10),
    )
    obj = MapObjectEvent(23, 67, 62, 10, 255, 208, 1, 1)
    monkeypatch.setattr(s, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(s, "static_encounters", lambda _: [entry])
    monkeypatch.setattr(
        s,
        "map_object_events",
        lambda *a: [] if fault == "missing" else [obj, obj] if fault == "duplicate" else [obj],
    )
    if fault:
        with pytest.raises(ValueError):
            s.route12_snorlax_target(b"rom")
    else:
        t = s.route12_snorlax_target(b"rom")
        assert (t.species_number, t.internal_species, t.level, t.event_flag) == (143, 132, 30, 1167)
    s.route12_snorlax_target.cache_clear()


@pytest.mark.parametrize("flute,battle", [(False, 0), (True, 1)])
def test_activation_refuses_missing_flute_or_engaged_battle(flute, battle):
    reader = N(read=lambda: N(battle_state=battle, bag_items=((73, 1),) if flute else ()))
    with pytest.raises(ValueError):
        s.activate_snorlax(None, reader, None)


def test_activation_uses_held_flute_not_object_interaction(monkeypatch):
    from pokemon_red_completion import lavender, surge

    calls = []
    monkeypatch.setattr(lavender, "_open_bag", lambda *a: calls.append("bag"))
    monkeypatch.setattr(lavender, "_select_bag_item", lambda *a: calls.append(a[2]))
    monkeypatch.setattr(surge, "_pulse", lambda *a, **k: calls.append(a[1].value))
    s.activate_snorlax(None, N(read=lambda: N(battle_state=0, bag_items=((73, 1),))), None)
    assert calls == ["bag", ItemId.POKE_FLUTE, "confirm"]


@pytest.mark.parametrize("allow", [False, True])
def test_snorlax_runtime_requires_explicit_optin_then_flute(monkeypatch, allow):
    from test_red_static_capture_runtime import World

    from pokemon_red_completion import red_static_capture_runtime as r

    target = RedStaticCaptureTarget(143, 132, 30, 23, 1, 67, (62, 10), 1167)
    request = OneOffCaptureRequest(132, 30, ItemId.GREAT_BALL)
    w = World()
    w.raw = replace(w.raw, map_id=23, player_x=10, player_y=61, bag_items=((3, 20), (73, 1)))
    monkeypatch.setattr(r, "red_static_capture_targets", lambda _: ())
    monkeypatch.setattr(s, "route12_snorlax_target", lambda _: target)
    monkeypatch.setattr(r, "require_static_capture_admission", lambda *a, **k: None)
    activated = []

    def activate(*args):
        activated.append(True)
        raise RuntimeError("Flute activation reached")

    monkeypatch.setattr(s, "activate_snorlax", activate)
    with pytest.raises(RuntimeError if allow else ValueError):
        r.execute_static_capture(
            w,
            w,
            w,
            target,
            request,
            rom=b"rom",
            budget=OneOffCaptureBudget(request, 20, 20),
            allow_snorlax=allow,
        )
    assert bool(activated) == allow and not w.calls
