"""ROM-free route-cost binding, knownness and purity checks."""

from dataclasses import replace
from types import SimpleNamespace as N

import pytest
import test_native_evolution_venue_model as fixtures
from test_native_evolution_venue_model import build

from pokemon_red_completion import red_native_venue_geometry as geometry
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.red_native_venue_geometry import NativeVenueGeometryQuote as Quote
from pokemon_red_completion.route_plan import RoutePlanningError


@pytest.fixture
def menu_case(monkeypatch):
    return fixtures.menu_case.__wrapped__(monkeypatch)


def test_existing_menu_default_and_explicit_unknown_are_feature_exact(menu_case):
    quotes = tuple(
        Quote(
            v.band.identity,
            menu_case.observation.raw,
            None,
            None,
            None,
            0,
            ("no compatible quote",),
        )
        for v in menu_case.venues
    )
    old = build(menu_case)
    unknown = build(menu_case, geometry_quotes=quotes)
    assert old.candidate_set == unknown.candidate_set
    assert old.semantic_snapshot_sha256 != unknown.semantic_snapshot_sha256


def test_native_geometry_enters_existing_workload_coordinates_and_permutes(menu_case):
    quotes = tuple(
        Quote(v.band.identity, menu_case.observation.raw, t, r, (v.map_id, (1, 1)), 0, ())
        for v, t, r in zip(menu_case.venues, (23, 91), (46, 182), strict=True)
    )
    menu = build(menu_case, geometry_quotes=quotes)
    columns = menu.candidate_set.feature_names
    for candidate, quote in zip(menu.candidate_set.candidates, quotes, strict=True):
        f = dict(zip(columns, candidate.features, strict=True))
        assert f["venue.travel_steps_known"] == f["venue.recovery_steps_known"] == 1
        assert f["venue.travel_steps"] == quote.travel_steps / 1_000_000
        assert f["venue.recovery_steps"] == quote.recovery_steps / 1_000_000
    permuted = build(menu_case, venues=menu_case.venues[::-1], geometry_quotes=quotes[::-1])
    assert [c.features for c in menu.candidate_set.candidates] == [
        c.features for c in permuted.candidate_set.candidates
    ][::-1]


@pytest.mark.parametrize("fault", ["swapped", "stale", "map", "length", "untyped"])
def test_geometry_cannot_silently_rebind_source_or_venue(menu_case, fault):
    quotes = tuple(
        Quote(v.band.identity, menu_case.observation.raw, 23, 46, (v.map_id, (1, 1)), 0, ())
        for v in menu_case.venues
    )
    if fault == "swapped":
        quotes = quotes[::-1]
    elif fault == "stale":
        quotes = (replace(quotes[0], source_raw=object()), quotes[1])
    elif fault == "map":
        quotes = (replace(quotes[0], planned_entry=(255, (1, 1))), quotes[1])
    elif fault == "length":
        quotes = quotes[:1]
    else:
        quotes = ({"travel_steps": 23}, quotes[1])
    with pytest.raises(ValueError):
        build(menu_case, geometry_quotes=quotes)


@pytest.mark.parametrize("value", [-1, True, 1.5, 1_000_001])
def test_geometry_counts_are_bounded_integers(value):
    with pytest.raises(ValueError):
        Quote(("bound", ()), object(), value, None, None, 0, ())


def quote_fixture(monkeypatch, *, fly=False, fail_leg=None, mutate=False):
    raw = N(battle_state=0)
    start = N(
        map_id=int(MapId.CINNABAR_POKECENTER),
        at=(3, 3),
        mode="land",
        ready=True,
        interruption=None,
        occupied=frozenset(),
        hazards=(),
        last_outside_map=int(MapId.CINNABAR_ISLAND),
    )
    # Use the actual immutable traversal dataclass so endpoint projections are real.
    import inspect

    from pokemon_red_completion.route_executor import TraversalSnapshot

    values = {
        name: getattr(start, name)
        for name in inspect.signature(TraversalSnapshot).parameters
        if hasattr(start, name)
    }
    start = TraversalSnapshot(**values)
    calls = []
    em = N(frame_count=0, pressed_buttons=frozenset())
    em.save_state_bytes = lambda: b"changed" if mutate and calls else b"same"
    rt = N(emulator=em, reader=N(read=lambda: raw, read_fly_destinations=lambda: (6, 8)))
    monkeypatch.setattr(geometry, "ground_route_capability_projector", lambda *a: lambda raw: ())
    monkeypatch.setattr(geometry, "Gen1TraversalObserver", lambda *a, **k: N(observe=lambda: start))
    monkeypatch.setattr(geometry, "_supported_plan", lambda *a, **k: True)
    monkeypatch.setattr(geometry, "red_training_fly_available", lambda raw: fly)
    monkeypatch.setattr(geometry, "red_fly_landings", lambda rom: ((6, (4, 11)), (8, (12, 11))))

    def plan(origin, destination, goal_at=None):
        calls.append((origin.map_id, destination, goal_at))
        if len(calls) == fail_leg:
            raise RoutePlanningError("fixture unavailable")
        return N(
            steps=(1, 2, 3),
            terminal_map=destination,
            terminal_at=goal_at or (9, 0),
            terminal_mode="land",
        )

    world = N(rom=b"fixture", plan_feasible_to_map=plan)
    world.with_current_observation = lambda reader: world
    return rt, world, N(raw=raw, input_ready=True), calls


def test_quote_counts_all_nurse_and_venue_legs_without_input(monkeypatch):
    rt, world, obs, calls = quote_fixture(monkeypatch)
    venue = N(map_id=int(MapId.POKEMON_MANSION_1F), band=N(identity=("mansion", ())))
    (q,) = geometry.quote_native_evolution_venue_geometry(rt, world, obs, (venue,))
    assert (q.travel_steps, q.recovery_steps, q.flight_count) == (6, 6, 0)
    assert q.unknown_reasons == () and len(calls) == 4
    assert rt.emulator.frame_count == 0 and not rt.emulator.pressed_buttons


def test_unavailable_travel_does_not_fabricate_free_cost_or_hide_recovery(monkeypatch):
    rt, world, obs, _ = quote_fixture(monkeypatch, fail_leg=1)
    venue = N(map_id=int(MapId.POKEMON_MANSION_1F), band=N(identity=("mansion", ())))
    (q,) = geometry.quote_native_evolution_venue_geometry(rt, world, obs, (venue,))
    assert q.travel_steps is None and q.recovery_steps == 6
    assert q.unknown_reasons[0].startswith("travel:")


def test_geometry_detects_state_changes_in_a_supposedly_pure_planner(monkeypatch):
    rt, world, obs, _ = quote_fixture(monkeypatch, mutate=True)
    venue = N(map_id=int(MapId.POKEMON_MANSION_1F), band=N(identity=("mansion", ())))
    with pytest.raises(ValueError, match="changed native"):
        geometry.quote_native_evolution_venue_geometry(rt, world, obs, (venue,))
