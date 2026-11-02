from dataclasses import replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_live_fishing as live_fishing
from pokemon_red_completion.fishing import ShorelineStance
from pokemon_red_completion.gen1_cartridge import FishingSlot, RodKind
from pokemon_red_completion.gen1_traversal import Direction
from pokemon_red_completion.global_router import MacroEdge, MacroGraph
from pokemon_red_completion.living_dex_option_value import LivingDexOptionContext
from pokemon_red_completion.observation import Badge
from pokemon_red_completion.private_artifacts import validate_private_record
from pokemon_red_completion.red_dig_recovery import DigEscapePlan
from pokemon_red_completion.red_fishing_acquisition import RedFishingDestinationOffer
from pokemon_red_completion.red_fishing_capture import RedFishingCaptureReport
from pokemon_red_completion.red_resource_goal_router import _MAX_ROUTE_FLEES, _ROUTE_LIMITS
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError


def _slot(species: int) -> FishingSlot:
    return FishingSlot(15, species, RodKind.SUPER)


def _offer(map_id: int, species: tuple[int, ...]) -> RedFishingDestinationOffer:
    return RedFishingDestinationOffer(
        f"fishing-map-private-{map_id}",
        map_id,
        tuple(_slot(number) for number in species),
        tuple(sorted(set(species))),
    )


def _stance(y: int = 0) -> ShorelineStance:
    return ShorelineStance((y, 0), Direction.DOWN, (y + 1, 0))


def _traversal() -> TraversalSnapshot:
    return TraversalSnapshot(1, (0, 0), True, capabilities=frozenset({"surf"}))


def _context() -> LivingDexOptionContext:
    return LivingDexOptionContext(0.8, 0.2, 0.5, 0.4, 0.1, 0.3, 0.7)


@pytest.mark.parametrize("bounded", [False, True])
def test_bounded_discovery_stops_only_after_fully_verified_candidates(monkeypatch, bounded):
    offers = tuple(_offer(map_id, (119,)) for map_id in range(10, 15))
    monkeypatch.setattr(live_fishing, "red_super_rod_destination_offers", lambda *a: offers)
    monkeypatch.setattr(live_fishing, "fishable_shoreline_stances", lambda _: (_stance(),))
    monkeypatch.setattr(live_fishing, "_supported_plan", lambda plan, **kwargs: plan.supported)
    monkeypatch.setattr(live_fishing, "without_coordinates", lambda graph, _: graph)
    monkeypatch.setattr(live_fishing, "find_local_paths", lambda *a, **kwargs: {
        (_stance().at, None): SimpleNamespace(edges=())
    })
    queries = []

    def plan(start, target, *, goal_at=None):
        assert start == _traversal()
        queries.append((target, goal_at))
        if target == 10:
            raise RoutePlanningError("unreachable first offer")
        return SimpleNamespace(
            steps=(object(),), terminal_at=_stance().at, terminal_mode="land",
            cost=15 - target, supported=target != 11,
        )

    world = SimpleNamespace(
        terrain={offer.map_id: object() for offer in offers},
        local_graphs={offer.map_id: object() for offer in offers},
        object_blockers={}, macro_graph=SimpleNamespace(warp_locations={}),
        plan_feasible_to_map=plan,
    )
    found = live_fishing.discover_reachable_red_fishing_destinations(
        b"rom", set(), world=world, traversal=_traversal(), maximum_candidates=2,
        stop_when_full=bounded,
    )
    assert [item.offer.map_id for item in found] == ([13, 12] if bounded else [14, 13])
    assert queries[:6] == [
        (10, None), (11, None), (12, None), (12, _stance().at),
        (13, None), (13, _stance().at),
    ]
    assert len(queries) == (6 if bounded else 8)


@pytest.mark.parametrize("flag", [None, 0, 1, "true", ()])
def test_invalid_bounded_discovery_mode_fails_before_inventory_access(flag):
    with pytest.raises(ValueError, match="bounded discovery mode"):
        live_fishing.discover_reachable_red_fishing_destinations(
            b"rom", set(), world=None, traversal=None, stop_when_full=flag
        )


def test_fast_discovery_reuses_a_legal_nearby_flight_origin_without_world_walk(monkeypatch):
    landing = replace(_traversal(), map_id=3, last_outside_map=3)
    offer = _offer(23, (116,))
    monkeypatch.setattr(live_fishing, "red_super_rod_destination_offers", lambda *a: (offer,))
    monkeypatch.setattr(live_fishing, "fishable_shoreline_stances", lambda _: (_stance(),))
    monkeypatch.setattr(live_fishing, "_supported_plan", lambda *a, **k: True)
    monkeypatch.setattr(live_fishing, "without_coordinates", lambda graph, _: graph)
    monkeypatch.setattr(
        live_fishing,
        "find_local_paths",
        lambda *a, **k: {
            (_stance().at, None): SimpleNamespace(edges=()),
        },
    )
    queried = []

    def plan(start, target, *, goal_at=None):
        queried.append((start.map_id, target, goal_at))
        return SimpleNamespace(
            steps=(object(),), terminal_at=_stance().at, terminal_mode="land", cost=2
        )

    world = SimpleNamespace(
        terrain={23: object()},
        local_graphs={23: object()},
        object_blockers={},
        macro_graph=MacroGraph(
            {
                1: (MacroEdge(2),),
                2: (MacroEdge(23),),
                3: (MacroEdge(23),),
                23: (),
            }
        ),
        plan_feasible_to_map=plan,
    )
    found = live_fishing.discover_reachable_red_fishing_destinations(
        b"rom", set(), world=world, traversal=_traversal(), flight_origins=(landing,)
    )
    assert len(found) == 1 and found[0].flight_origin is landing
    assert queried == [(3, 23, None), (3, 23, _stance().at)]
    assert "flight_origin" not in found[0].public_dict()


@pytest.mark.parametrize("safari", [False, True])
def test_transport_quotation_is_action_free_and_safari_never_escapes(monkeypatch, safari):
    from pokemon_red_completion.local_router import LocalGraph

    escape = DigEscapePlan(89, (0, 0), 0, (1, 1), 0, 17)
    traversal = replace(_traversal(), map_id=217 if safari else 89, mode="land")
    raw = SimpleNamespace(badge_bits=int(Badge.THUNDER))
    observed = {}
    monkeypatch.setattr(
        live_fishing,
        "plan_dig_escape",
        lambda *a: pytest.fail("Safari must not quote Dig") if safari else escape,
    )
    monkeypatch.setattr(live_fishing, "fly_menu_indices", lambda _: (0, 1))
    monkeypatch.setattr(live_fishing, "red_fly_landings", lambda _: ((0, (1, 1)), (5, (2, 2))))

    def discover(*a, **k):
        observed.update(k)
        return ()

    monkeypatch.setattr(live_fishing, "discover_reachable_red_fishing_destinations", discover)
    world = SimpleNamespace(local_graphs={5: LocalGraph({(2, 2): ()})}, object_blockers={})
    actions = SimpleNamespace(actions_executed=0)
    emulator = SimpleNamespace(frame_count=99)
    live_fishing.build_red_live_fishing_inventory(
        b"rom",
        set(),
        _context(),
        free_storage_slots=1,
        world=world,
        traversal=traversal,
        observer=object(),
        field=object(),
        controller=object(),
        actions=actions,
        reader=SimpleNamespace(read=lambda: raw, read_fly_destinations=lambda: (5,)),
        emulator=emulator,
        allow_fast_transport=True,
        safari_session_steps=20 if safari else None,
    )
    assert actions.actions_executed == 0 and emulator.frame_count == 99
    assert observed["dig_escape"] == (None if safari else escape)
    assert tuple(s.map_id for s in observed["flight_origins"]) == (() if safari else (5,))


def test_indoor_fishing_quotes_walking_departure_before_fly_without_input(monkeypatch):
    from pokemon_red_completion.local_router import LocalGraph

    traversal = replace(
        _traversal(),
        map_id=65,
        last_outside_map=3,
        mode="land",
        capabilities=frozenset({"move:surf", "story:door_open"}),
    )
    observed, plans = {}, []
    monkeypatch.setattr(live_fishing, "plan_dig_escape", lambda *a: None)
    monkeypatch.setattr(live_fishing, "fly_menu_indices", lambda _: (0, 1))
    monkeypatch.setattr(live_fishing, "red_fly_landings", lambda _: ((5, (2, 2)),))
    monkeypatch.setattr(live_fishing, "_supported_plan", lambda *a, **k: True)
    monkeypatch.setattr(
        live_fishing,
        "discover_reachable_red_fishing_destinations",
        lambda *a, **k: observed.update(k) or (),
    )

    def plan(start, target):
        plans.append((start, target))
        return SimpleNamespace(
            steps=(object(),) * 3,
            cost=4,
            terminal_map=3,
            terminal_at=(18, 30),
            terminal_mode="land",
        )

    world = SimpleNamespace(
        plan_feasible_to_map=plan, object_blockers={}, local_graphs={5: LocalGraph({(2, 2): ()})}
    )
    actions = SimpleNamespace(actions_executed=0)
    emulator = SimpleNamespace(frame_count=99)
    live_fishing.build_red_live_fishing_inventory(
        b"rom",
        set(),
        _context(),
        free_storage_slots=1,
        world=world,
        traversal=traversal,
        observer=object(),
        field=object(),
        controller=object(),
        actions=actions,
        reader=SimpleNamespace(
            read=lambda: SimpleNamespace(battle_state=0, badge_bits=int(Badge.THUNDER)),
            read_fly_destinations=lambda: (5,),
        ),
        emulator=emulator,
        allow_fast_transport=True,
    )
    assert plans[0][0].capabilities == frozenset({"story:door_open"})
    assert plans[0][1] == 3
    assert observed["departure_origin"].map_id == 3
    assert observed["departure_origin"].at == (18, 30)
    assert observed["departure_steps"] == 3 and observed["departure_cost"] == 4
    assert tuple(s.map_id for s in observed["flight_origins"]) == (5,)
    assert actions.actions_executed == 0 and emulator.frame_count == 99


@pytest.mark.parametrize("fault", [None, "stale_departure", "wrong_boundary"])
@pytest.mark.parametrize('wrapped', [False, True])
def test_selected_indoor_fishing_verifies_exit_before_flight_and_capture(
    monkeypatch, fault, wrapped
):
    outside = replace(_traversal(), map_id=3, at=(18, 30), mode="land", last_outside_map=3)
    landing = replace(outside, map_id=5, at=(2, 2), last_outside_map=5)
    destination = live_fishing.RedReachableFishingDestination(
        _offer(23, (116,)), _stance(), 3, 4, flight_origin=landing, departure_origin=outside
    )
    location = [
        replace(
            outside, map_id=65, at=(1, 1), last_outside_map=0 if fault == "stale_departure" else 3
        )
    ]
    registered, phases = {1}, []
    wrapped_handlers = []
    def wrapper(inner):
        handler = SimpleNamespace(inner=inner)
        wrapped_handlers.append(handler)
        return handler
    actions = SimpleNamespace(actions_executed=0)
    emulator = SimpleNamespace(frame_count=100, pressed_buttons=frozenset())
    reader = SimpleNamespace(
        read=lambda: SimpleNamespace(battle_state=0, badge_bits=int(Badge.THUNDER)),
        read_bottom_dialogue_box_visible=lambda: False,
        read_pending_trainer_battle_identity=lambda: None,
        read_fly_menu_state=lambda: None,
        read_fly_destinations=lambda: (5,),
        read_pokedex_state=lambda: SimpleNamespace(owned_species=frozenset(registered)),
    )

    def plan(start, target, *, goal_at):
        phases.append("plan_departure" if start.map_id == 65 else "plan_shoreline")
        assert (target, goal_at) == ((3, outside.at) if start.map_id == 65 else (23, _stance().at))
        return SimpleNamespace(steps=(object(),), cost=1, departure=start.map_id == 65)

    def route(plan, *a, **k):
        assert k["limits"] is _ROUTE_LIMITS
        if wrapped:
            assert k['interruption_handler'] is wrapped_handlers[-1]
        phases.append("depart" if plan.departure else "route")
        actions.actions_executed += 2
        emulator.frame_count += 20
        if plan.departure:
            location[0] = replace(outside, at=(9, 9)) if fault == "wrong_boundary" else outside
        return SimpleNamespace(passed=True)

    def fly(action):
        assert location[0] == outside and action.value == "fly:vermilion_city"
        phases.append("fly")
        actions.actions_executed += 3
        emulator.frame_count += 30
        location[0] = landing

    def capture(*a, **k):
        phases.append("capture")
        registered.add(116)
        return RedFishingCaptureReport(1, 1, 0, 1, 0, 0, 1, 0, 1, False)

    monkeypatch.setattr(live_fishing, "red_fly_landings", lambda _: ((5, landing.at),))
    monkeypatch.setattr(live_fishing, "fly_menu_indices", lambda _: (0, 1))
    monkeypatch.setattr(live_fishing, "_supported_plan", lambda *a, **k: True)
    monkeypatch.setattr(live_fishing, "Gen1RouteInterruptionHandler", lambda *a, **k: object())
    monkeypatch.setattr(live_fishing, "execute_route", route)
    monkeypatch.setattr(live_fishing, "LiveWildEncounterExecutor", lambda *a, **k: object())
    monkeypatch.setattr(live_fishing, "LiveRedFishingCapturePort", lambda *a, **k: object())
    monkeypatch.setattr(live_fishing, "run_red_fishing_capture", capture)
    binding = live_fishing.build_red_live_fishing_supplements(
        _context(),
        (destination,),
        free_storage_slots=1,
        world=SimpleNamespace(rom=b"rom", plan_feasible_to_map=plan, replanner=lambda: object()),
        observer=SimpleNamespace(observe=lambda: location[0]),
        field=SimpleNamespace(execute=fly),
        controller=object(),
        actions=actions,
        reader=reader,
        emulator=emulator,
        interruption_handler_wrapper=wrapper if wrapped else None,
    )[0].binding
    assert wrapped_handlers == []
    if fault:
        with pytest.raises(live_fishing.RedLiveFishingError):
            binding.execute()
        assert "fly" not in phases and "capture" not in phases
        assert actions.actions_executed == (0 if fault == "stale_departure" else 2)
    else:
        report = binding.execute()
        assert report.actions_executed == 7 and report.frames_executed == 70
        assert phases == ["plan_departure", "depart", "fly", "plan_shoreline", "route", "capture"]
        assert report.evidence["transport"]["indoor_departure"]["verified_departures"] == 1
        assert binding.verify(report).status.value == "succeeded"
    assert len(wrapped_handlers) == (0 if not wrapped or fault == 'stale_departure'
                                     else 1 if fault else 2)


@pytest.mark.parametrize("fault", [None, "lost_flight", "wrong_landing", "stale_escape"])
def test_selected_fast_fishing_rechecks_transport_and_counts_all_actual_inputs(monkeypatch, fault):
    escape = DigEscapePlan(89, (0, 0), 0, (1, 1), 0, 17)
    landing = replace(_traversal(), map_id=5, at=(2, 2), mode="land", last_outside_map=5)
    destination = live_fishing.RedReachableFishingDestination(
        _offer(23, (116,)), _stance(), 1, 2, escape, landing
    )
    location = [replace(_traversal(), map_id=89, mode="land")]
    registered = {1}
    actions = SimpleNamespace(actions_executed=0)
    emulator = SimpleNamespace(frame_count=100, pressed_buttons=frozenset())
    reader = SimpleNamespace(
        read=lambda: SimpleNamespace(battle_state=0, badge_bits=int(Badge.THUNDER)),
        read_bottom_dialogue_box_visible=lambda: False,
        read_pending_trainer_battle_identity=lambda: None,
        read_fly_menu_state=lambda: None,
        read_fly_destinations=lambda: () if fault == "lost_flight" else (5,),
        read_pokedex_state=lambda: SimpleNamespace(owned_species=frozenset(registered)),
    )
    phases = []

    def dig(*a):
        if fault == "stale_escape":
            raise RuntimeError("escape origin changed before input")
        phases.append("dig")
        actions.actions_executed += 2
        emulator.frame_count += 20
        location[0] = replace(location[0], map_id=0, at=(1, 1), last_outside_map=0)
        return {"verified_escape": True}

    def fly(action):
        assert action.value == "fly:vermilion_city"
        phases.append("fly")
        actions.actions_executed += 3
        emulator.frame_count += 30
        location[0] = replace(landing, at=(9, 9)) if fault == "wrong_landing" else landing

    def plan(start, *a, **k):
        assert start == landing and phases == ["dig", "fly"]
        phases.append("plan")
        return SimpleNamespace(steps=(), cost=0)

    def route(*a, **k):
        phases.append("route")
        actions.actions_executed += 4
        emulator.frame_count += 40
        return SimpleNamespace(passed=True)

    def capture(*a, **k):
        phases.append("capture")
        actions.actions_executed += 5
        emulator.frame_count += 50
        registered.add(116)
        return RedFishingCaptureReport(1, 1, 0, 1, 0, 0, 1, 0, 1, False)

    monkeypatch.setattr(live_fishing, "execute_dig_escape", dig)
    monkeypatch.setattr(live_fishing, "red_fly_landings", lambda _: ((5, (2, 2)),))
    monkeypatch.setattr(live_fishing, "fly_menu_indices", lambda _: (0, 1))
    monkeypatch.setattr(live_fishing, "_supported_plan", lambda *a, **k: True)
    monkeypatch.setattr(live_fishing, "Gen1RouteInterruptionHandler", lambda *a, **k: object())
    monkeypatch.setattr(live_fishing, "execute_route", route)
    monkeypatch.setattr(live_fishing, "LiveWildEncounterExecutor", lambda *a, **k: object())
    monkeypatch.setattr(live_fishing, "LiveRedFishingCapturePort", lambda *a, **k: object())
    monkeypatch.setattr(live_fishing, "run_red_fishing_capture", capture)
    binding = live_fishing.build_red_live_fishing_supplements(
        _context(),
        (destination,),
        free_storage_slots=1,
        world=SimpleNamespace(rom=b"rom", plan_feasible_to_map=plan, replanner=lambda: object()),
        observer=SimpleNamespace(observe=lambda: location[0]),
        field=SimpleNamespace(execute=fly),
        controller=object(),
        actions=actions,
        reader=reader,
        emulator=emulator,
    )[0].binding
    if fault:
        with pytest.raises(RuntimeError):
            binding.execute()
        assert "route" not in phases and "capture" not in phases
        assert actions.actions_executed == (
            0 if fault == "stale_escape" else 2 if fault == "lost_flight" else 5
        )
    else:
        report = binding.execute()
        assert report.actions_executed == 14 and report.frames_executed == 140
        assert phases == ["dig", "fly", "plan", "route", "capture"]
        assert report.evidence["transport"]["dig"]["verified_escape"]
        assert report.evidence["transport"]["fly"]["verified_flights"] == 1
        assert binding.verify(report).status.value == "succeeded"


@pytest.mark.parametrize("map_id", sorted(live_fishing._SAFARI_FISHING_MAPS))
@pytest.mark.parametrize("blocked", ["origin", "destination"])
def test_ordinary_fishing_never_offers_safari_controls(monkeypatch, map_id, blocked):
    monkeypatch.setattr(
        live_fishing,
        "red_super_rod_destination_offers",
        lambda *_: (_offer(map_id, (147,)),),
    )
    traversal = TraversalSnapshot(map_id, (0, 0), True) if blocked == "origin" else _traversal()
    # No world access is needed: rule out incompatible battle semantics first.
    assert (
        live_fishing.discover_reachable_red_fishing_destinations(
            b"rom",
            set(),
            world=SimpleNamespace(),
            traversal=traversal,
        )
        == ()
    )


@pytest.mark.parametrize("blocked", ["origin", "destination"])
def test_ordinary_fishing_rechecks_safari_boundary_before_input(blocked):
    safari_map = min(live_fishing._SAFARI_FISHING_MAPS)
    destination = live_fishing.RedReachableFishingDestination(
        _offer(safari_map if blocked == "destination" else 23, (147,)),
        _stance(),
        1,
        1,
    )
    origin = TraversalSnapshot(safari_map, (0, 0), True) if blocked == "origin" else _traversal()
    options = live_fishing.build_red_live_fishing_supplements(
        _context(),
        (destination,),
        free_storage_slots=2,
        world=SimpleNamespace(),
        observer=SimpleNamespace(observe=lambda: origin),
        field=SimpleNamespace(),
        controller=SimpleNamespace(),
        actions=SimpleNamespace(actions_executed=0),
        reader=SimpleNamespace(),
        emulator=SimpleNamespace(frame_count=0),
    )
    with pytest.raises(live_fishing.RedLiveFishingError, match="Safari battle controls"):
        options[0].binding.execute()


def test_discovery_is_action_free_filters_unreachable_and_sorts_by_effort(monkeypatch):
    offers = (_offer(23, (116,)), _offer(24, (117, 118)), _offer(25, (119,)))
    monkeypatch.setattr(
        live_fishing,
        "red_super_rod_destination_offers",
        lambda _rom, _registered: offers,
    )
    monkeypatch.setattr(
        live_fishing,
        "fishable_shoreline_stances",
        lambda terrain: (_stance(terrain.map_id - 23),),
    )
    monkeypatch.setattr(live_fishing, "_supported_plan", lambda *_a, **_k: True)

    def plan(_start, map_id, **_kwargs):
        if map_id == 25:
            raise RoutePlanningError("unreachable")
        return SimpleNamespace(
            steps=(object(),) * ({23: 6, 24: 2}[map_id]),
            terminal_at=(9, 9),
            terminal_mode=None,
            cost={23: 9, 24: 3}[map_id],
        )

    world = SimpleNamespace(
        terrain={number: SimpleNamespace(map_id=number) for number in (23, 24, 25)},
        local_graphs={number: object() for number in (23, 24, 25)},
        object_blockers={number: frozenset() for number in (23, 24, 25)},
        macro_graph=SimpleNamespace(warp_locations={}),
        plan_feasible_to_map=plan,
    )
    monkeypatch.setattr(
        live_fishing,
        "find_local_paths",
        lambda _graph, _start, goals, **_kwargs: {
            goal: SimpleNamespace(edges=(SimpleNamespace(cost=1),) * 2) for goal in goals
        },
    )
    monkeypatch.setattr(live_fishing, "without_coordinates", lambda graph, _blocked: graph)

    found = live_fishing.discover_reachable_red_fishing_destinations(
        b"rom",
        {1},
        world=world,
        traversal=_traversal(),
    )

    assert [item.offer.map_id for item in found] == [24, 23]
    assert [(item.route_steps, item.route_cost) for item in found] == [(2, 3), (6, 9)]
    assert all(item.offer.map_id != 25 for item in found)
    assert all("116" not in str(item.public_dict()) for item in found)
    assert all("24" not in str(item.public_dict()) for item in found)


@pytest.mark.parametrize("reason", ("no_shoreline", "occupied", "warp"))
@pytest.mark.parametrize("flying", (False, True))
def test_discovery_rejects_impossible_shoreline_before_any_route_query(
    monkeypatch, reason, flying,
):
    stance = _stance()
    monkeypatch.setattr(
        live_fishing, "red_super_rod_destination_offers", lambda *_a: (_offer(23, (116,)),)
    )
    monkeypatch.setattr(
        live_fishing, "fishable_shoreline_stances",
        lambda _terrain: () if reason == "no_shoreline" else (stance,),
    )
    monkeypatch.setattr(
        live_fishing, "find_macro_path",
        lambda *_a, **_k: pytest.fail("an impossible shoreline needs no topology search"),
    )
    world = SimpleNamespace(
        terrain={23: object()}, local_graphs={23: object()},
        object_blockers={23: frozenset({stance.at}) if reason == "occupied" else frozenset()},
        macro_graph=SimpleNamespace(warp_locations={23: (stance.at,) if reason == "warp" else ()}),
        plan_feasible_to_map=lambda *_a, **_k: pytest.fail(
            "an impossible shoreline needs no feasible-route search"
        ),
    )
    assert live_fishing.discover_reachable_red_fishing_destinations(
        b"rom", set(), world=world, traversal=_traversal(),
        flight_origins=(_traversal(),) if flying else (),
    ) == ()


def test_discovery_rejects_unsupported_routes_and_blocked_stances(monkeypatch):
    offers = (_offer(23, (116,)), _offer(24, (117,)))
    monkeypatch.setattr(
        live_fishing,
        "red_super_rod_destination_offers",
        lambda _rom, _registered: offers,
    )
    monkeypatch.setattr(live_fishing, "fishable_shoreline_stances", lambda _terrain: (_stance(),))
    monkeypatch.setattr(
        live_fishing,
        "_supported_plan",
        lambda plan, **_kwargs: plan.map_id != 23,
    )
    world = SimpleNamespace(
        terrain={23: object(), 24: object()},
        local_graphs={23: object(), 24: object()},
        object_blockers={23: frozenset(), 24: frozenset({_stance().at})},
        macro_graph=SimpleNamespace(warp_locations={}),
        plan_feasible_to_map=lambda _start, map_id: SimpleNamespace(
            map_id=map_id,
            steps=(object(),),
            terminal_at=(0, 0),
            terminal_mode=None,
            cost=1,
        ),
    )
    monkeypatch.setattr(
        live_fishing,
        "find_local_paths",
        lambda *_a, **_k: pytest.fail("blocked or unsupported destinations need no local search"),
    )

    assert (
        live_fishing.discover_reachable_red_fishing_destinations(
            b"rom", set(), world=world, traversal=_traversal()
        )
        == ()
    )


def test_live_supplement_construction_is_action_free_and_identity_free():
    destinations = (
        live_fishing.RedReachableFishingDestination(_offer(23, (116,)), _stance(), 4, 5),
        live_fishing.RedReachableFishingDestination(_offer(24, (117, 118)), _stance(2), 12, 15),
    )
    actions = SimpleNamespace(actions_executed=0)
    emulator = SimpleNamespace(frame_count=99, pressed_buttons=frozenset())

    supplements = live_fishing.build_red_live_fishing_supplements(
        _context(),
        destinations,
        free_storage_slots=30,
        world=SimpleNamespace(),
        observer=SimpleNamespace(),
        field=SimpleNamespace(),
        controller=SimpleNamespace(),
        actions=actions,
        reader=SimpleNamespace(),
        emulator=emulator,
    )

    assert len(supplements) == 2
    assert actions.actions_executed == 0 and emulator.frame_count == 99
    assert all(row.binding.binding_ref == row.candidate.binding_ref for row in supplements)
    public = [row.candidate.policy_dict(_context()) for row in supplements]
    assert "fishing-map-private" not in str(public)
    assert "116" not in str(public)

    inventory = live_fishing.RedLiveFishingInventory(destinations, supplements)
    assert inventory.public_dict()["candidate_count"] == 2
    assert "fishing-map-private" not in str(inventory.public_dict())


@pytest.mark.parametrize("outcome", ("reachable", "unreachable", "unsupported"))
def test_discovery_checks_bounded_exact_shorelines_when_first_entry_is_disconnected(
    monkeypatch,
    outcome,
):
    from pokemon_red_completion.local_router import LocalGraph

    offer = _offer(23, (119,))
    stances = tuple(_stance(y) for y in range(1, 9))
    monkeypatch.setattr(live_fishing, "red_super_rod_destination_offers", lambda *a: (offer,))
    monkeypatch.setattr(live_fishing, "fishable_shoreline_stances", lambda _: stances)
    monkeypatch.setattr(live_fishing, "_supported_plan", lambda plan, **k: plan.supported)
    calls = []

    def plan(start, destination, *, goal_at=None):
        assert start == _traversal() and destination == 23
        calls.append(goal_at)
        if goal_at is not None and outcome == "unreachable":
            raise RoutePlanningError("no alternate passage")
        return SimpleNamespace(
            steps=(object(),) * (2 if goal_at is None else 12),
            terminal_at=(0, 0) if goal_at is None else goal_at,
            terminal_mode=None,
            cost=2 if goal_at is None else 15,
            supported=goal_at is None or outcome != "unsupported",
        )

    world = SimpleNamespace(
        terrain={23: object()},
        local_graphs={23: LocalGraph({(0, 0): ()})},
        object_blockers={23: frozenset()},
        macro_graph=SimpleNamespace(warp_locations={}),
        plan_feasible_to_map=plan,
    )
    found = live_fishing.discover_reachable_red_fishing_destinations(
        b"rom",
        set(),
        world=world,
        traversal=_traversal(),
    )
    if outcome == "reachable":
        assert len(found) == 1 and found[0].stance == stances[0]
        assert (found[0].route_steps, found[0].route_cost) == (12, 15)
        assert calls == [None, stances[0].at]
    else:
        assert found == ()
        assert calls == [None, *(s.at for s in stances[:4])]


@pytest.mark.parametrize("destination_count", (0, 1))
def test_live_fishing_degrades_action_free_for_zero_or_one_destination(
    destination_count,
):
    destinations = (
        live_fishing.RedReachableFishingDestination(_offer(23, (116,)), _stance(), 4, 5),
    )[:destination_count]
    actions = SimpleNamespace(actions_executed=0)
    emulator = SimpleNamespace(frame_count=99, pressed_buttons=frozenset())

    supplements = live_fishing.build_red_live_fishing_supplements(
        _context(),
        destinations,
        free_storage_slots=30,
        world=SimpleNamespace(),
        observer=SimpleNamespace(),
        field=SimpleNamespace(),
        controller=SimpleNamespace(),
        actions=actions,
        reader=SimpleNamespace(),
        emulator=emulator,
    )
    inventory = live_fishing.RedLiveFishingInventory(destinations, supplements)

    assert len(supplements) == destination_count
    assert inventory.public_dict()["candidate_count"] == destination_count
    assert actions.actions_executed == 0 and emulator.frame_count == 99
    assert "fishing-map-private" not in str(inventory.public_dict())
    assert "116" not in str(inventory.public_dict())
    if supplements:
        assert supplements[0].candidate.features.travel_effort == 0.004


@pytest.mark.parametrize("destination_count", (0, 1, 2))
def test_inventory_composes_discovery_and_binding_without_input(monkeypatch, destination_count):
    destinations = (
        live_fishing.RedReachableFishingDestination(_offer(23, (116,)), _stance(), 4, 5),
        live_fishing.RedReachableFishingDestination(_offer(24, (117, 118)), _stance(2), 12, 15),
    )[:destination_count]
    actions = SimpleNamespace(actions_executed=0)
    emulator = SimpleNamespace(frame_count=99, pressed_buttons=frozenset())
    monkeypatch.setattr(
        live_fishing,
        "discover_reachable_red_fishing_destinations",
        lambda *_a, **_k: destinations,
    )

    inventory = live_fishing.build_red_live_fishing_inventory(
        b"rom",
        {1},
        _context(),
        free_storage_slots=30,
        world=SimpleNamespace(),
        traversal=_traversal(),
        observer=SimpleNamespace(),
        field=SimpleNamespace(),
        controller=SimpleNamespace(),
        actions=actions,
        reader=SimpleNamespace(),
        emulator=emulator,
    )

    assert inventory.destinations == destinations
    assert len(inventory.supplements) == destination_count
    assert actions.actions_executed == 0 and emulator.frame_count == 99


@pytest.mark.parametrize('wrapped', [False, True])
@pytest.mark.parametrize("physical_stock", [None, 0, 2])
def test_selected_live_binding_replans_executes_verifies_and_cannot_retry(
    monkeypatch, wrapped, physical_stock
):
    physical = physical_stock is not None
    offer = _offer(23, (116, 116))
    if physical:
        offer = replace(offer, physical_species_numbers=(116,))
    destination = live_fishing.RedReachableFishingDestination(
        offer, _stance(), 4, 5
    )
    registered = {1, 116} if physical else {1}
    stock = [physical_stock]
    reader = SimpleNamespace(
        read_pokedex_state=lambda: SimpleNamespace(owned_species=frozenset(registered)),
        read=lambda: SimpleNamespace(
            battle_state=0, map_id=23, player_x=0, player_y=0,
            repel_remaining_steps=0, party_levels=(15,), player_money=1000,
            bag_items=((4, 2),),
        ),
        read_overworld_movement_mode=lambda: 0,
    )
    diagnostics = []

    def record_diagnostic(kind, payload):
        validate_private_record(dict(kind=kind, payload=payload))
        diagnostics.append(payload)

    actions = SimpleNamespace(actions_executed=0, record_diagnostic_event=record_diagnostic)
    emulator = SimpleNamespace(
        frame_count=100, pressed_buttons=frozenset(), save_state_bytes=lambda: b"observed",
    )
    route = SimpleNamespace(steps=(object(),), terminal_at=_stance().at, cost=4)
    world = SimpleNamespace(
        plan_feasible_to_map=lambda *_a, **_k: route,
        replanner=lambda: object(),
    )
    monkeypatch.setattr(live_fishing, "_supported_plan", lambda *_a, **_k: True)
    handler_kwargs = {}
    inner = object()
    wrapped_handler = object()
    wrap_calls = []
    def wrapper(handler):
        assert handler is inner
        wrap_calls.append(handler)
        return wrapped_handler

    def interruption_handler(*_args, **kwargs):
        handler_kwargs.update(kwargs)
        return inner

    monkeypatch.setattr(live_fishing, "Gen1RouteInterruptionHandler", interruption_handler)

    def execute_route(*_args, **_kwargs):
        assert _kwargs["limits"] is _ROUTE_LIMITS
        assert _kwargs['interruption_handler'] is (wrapped_handler if wrapped else inner)
        actions.actions_executed += 3
        emulator.frame_count += 30
        return SimpleNamespace(passed=True)

    monkeypatch.setattr(live_fishing, "execute_route", execute_route)
    monkeypatch.setattr(live_fishing, "LiveWildEncounterExecutor", lambda *_a, **_k: object())
    monkeypatch.setattr(
        live_fishing, "LiveRedFishingCapturePort", lambda *_a, **_k: SimpleNamespace(
            registered_species_numbers=lambda: frozenset(registered),
            physical_species_count=lambda number: stock[0],
        ),
    )

    def capture(*_args, **_kwargs):
        counters = actions.actions_executed, emulator.frame_count
        facts = _kwargs["observe_diagnostics"]()
        assert counters == (actions.actions_executed, emulator.frame_count)
        _kwargs["record_diagnostic_event"]("fishing_cast_observed", dict(state=facts))
        assert facts["physical_target_stock"] == ({"116": physical_stock} if physical else {})
        actions.actions_executed += 2
        emulator.frame_count += 20
        registered.add(116)
        if physical:
            stock[0] += 1
        return RedFishingCaptureReport(
            1, 1, 0, 1, 0, 0, 1, 0, int(not physical), False,
            physical_acquisitions=int(physical),
        )

    monkeypatch.setattr(live_fishing, "run_red_fishing_capture", capture)
    supplements = live_fishing.build_red_live_fishing_supplements(
        _context(),
        (
            destination,
            live_fishing.RedReachableFishingDestination(_offer(24, (117, 118)), _stance(2), 12, 15),
        ),
        free_storage_slots=30,
        world=world,
        observer=SimpleNamespace(observe=lambda: _traversal()),
        field=SimpleNamespace(),
        controller=SimpleNamespace(),
        actions=actions,
        reader=reader,
        emulator=emulator,
        interruption_handler_wrapper=wrapper if wrapped else None,
    )
    assert wrap_calls == []
    binding = next(item.binding for item in supplements if item.binding.estimated_effort < 0.21)

    report = binding.execute()

    assert (report.actions_executed, report.frames_executed) == (5, 50)
    assert handler_kwargs["maximum_scripted_dialogues"] == 4
    assert handler_kwargs["maximum_flees"] == _MAX_ROUTE_FLEES
    assert handler_kwargs['maximum_trainer_battles'] == 0
    assert wrap_calls == ([inner] if wrapped else [])
    assert binding.verify(report).status.value == "succeeded"
    assert len(diagnostics) == 1
    with pytest.raises(live_fishing.RedLiveFishingError, match="consumed"):
        binding.execute()


def test_live_binding_verification_fails_closed_on_collection_drift(monkeypatch):
    destination = live_fishing.RedReachableFishingDestination(
        _offer(23, (116, 116)), _stance(), 4, 5
    )
    registered = {1}
    reader = SimpleNamespace(
        read_pokedex_state=lambda: SimpleNamespace(owned_species=frozenset(registered))
    )
    actions = SimpleNamespace(actions_executed=0)
    emulator = SimpleNamespace(frame_count=100, pressed_buttons=frozenset())
    world = SimpleNamespace(
        plan_feasible_to_map=lambda *_a, **_k: SimpleNamespace(steps=(), cost=0),
        replanner=lambda: object(),
    )
    monkeypatch.setattr(live_fishing, "_supported_plan", lambda *_a, **_k: True)
    monkeypatch.setattr(live_fishing, "Gen1RouteInterruptionHandler", lambda *_a, **_k: object())
    monkeypatch.setattr(
        live_fishing, "execute_route", lambda *_a, **_k: SimpleNamespace(passed=True)
    )
    monkeypatch.setattr(live_fishing, "LiveWildEncounterExecutor", lambda *_a, **_k: object())
    monkeypatch.setattr(live_fishing, "LiveRedFishingCapturePort", lambda *_a, **_k: object())

    def capture(*_args, **_kwargs):
        registered.update({116, 117})
        return RedFishingCaptureReport(1, 1, 0, 1, 0, 0, 1, 0, 1, False)

    monkeypatch.setattr(live_fishing, "run_red_fishing_capture", capture)
    binding = live_fishing.build_red_live_fishing_supplements(
        _context(),
        (
            destination,
            live_fishing.RedReachableFishingDestination(_offer(24, (117, 118)), _stance(2), 12, 15),
        ),
        free_storage_slots=30,
        world=world,
        observer=SimpleNamespace(observe=lambda: _traversal()),
        field=SimpleNamespace(),
        controller=SimpleNamespace(),
        actions=actions,
        reader=reader,
        emulator=emulator,
    )[0].binding
    report = binding.execute()

    assert binding.verify(report).failure_reason.value == "outcome_not_verified"


def test_live_fishing_validates_bounds():
    with pytest.raises(ValueError, match="one"):
        live_fishing.discover_reachable_red_fishing_destinations(
            b"rom", set(), world=SimpleNamespace(), traversal=_traversal(), maximum_candidates=0
        )
    with pytest.raises(ValueError, match="cast"):
        live_fishing.build_red_live_fishing_supplements(
            _context(),
            (),
            free_storage_slots=1,
            world=SimpleNamespace(),
            observer=SimpleNamespace(),
            field=SimpleNamespace(),
            controller=SimpleNamespace(),
            actions=SimpleNamespace(),
            reader=SimpleNamespace(),
            emulator=SimpleNamespace(),
            maximum_casts=0,
        )
    with pytest.raises(TypeError, match="destinations"):
        live_fishing.RedLiveFishingInventory([], ())
    with pytest.raises(TypeError, match="supplements"):
        live_fishing.RedLiveFishingInventory((), [])
    with pytest.raises(TypeError, match="option-value context"):
        live_fishing.build_red_live_fishing_supplements(
            object(),
            (),
            free_storage_slots=1,
            world=SimpleNamespace(),
            observer=SimpleNamespace(),
            field=SimpleNamespace(),
            controller=SimpleNamespace(),
            actions=SimpleNamespace(),
            reader=SimpleNamespace(),
            emulator=SimpleNamespace(),
        )
