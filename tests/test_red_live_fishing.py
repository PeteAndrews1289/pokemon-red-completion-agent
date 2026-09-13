from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_live_fishing as live_fishing
from pokemon_red_completion.fishing import ShorelineStance
from pokemon_red_completion.gen1_cartridge import FishingSlot, RodKind
from pokemon_red_completion.gen1_traversal import Direction
from pokemon_red_completion.living_dex_option_value import LivingDexOptionContext
from pokemon_red_completion.red_fishing_acquisition import RedFishingDestinationOffer
from pokemon_red_completion.red_fishing_capture import RedFishingCaptureReport
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

    assert live_fishing.discover_reachable_red_fishing_destinations(
        b"rom", set(), world=world, traversal=_traversal()
    ) == ()


def test_live_supplement_construction_is_action_free_and_identity_free():
    destinations = (
        live_fishing.RedReachableFishingDestination(_offer(23, (116,)), _stance(), 4, 5),
        live_fishing.RedReachableFishingDestination(
            _offer(24, (117, 118)), _stance(2), 12, 15
        ),
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


def test_inventory_composes_discovery_and_binding_without_input(monkeypatch):
    destinations = (
        live_fishing.RedReachableFishingDestination(_offer(23, (116,)), _stance(), 4, 5),
        live_fishing.RedReachableFishingDestination(
            _offer(24, (117, 118)), _stance(2), 12, 15
        ),
    )
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
    assert len(inventory.supplements) == 2
    assert actions.actions_executed == 0 and emulator.frame_count == 99


def test_selected_live_binding_replans_executes_verifies_and_cannot_retry(monkeypatch):
    destination = live_fishing.RedReachableFishingDestination(
        _offer(23, (116, 116)), _stance(), 4, 5
    )
    registered = {1}
    reader = SimpleNamespace(
        read_pokedex_state=lambda: SimpleNamespace(owned_species=frozenset(registered))
    )
    actions = SimpleNamespace(actions_executed=0)
    emulator = SimpleNamespace(frame_count=100, pressed_buttons=frozenset())
    route = SimpleNamespace(steps=(object(),), terminal_at=_stance().at, cost=4)
    world = SimpleNamespace(
        plan_feasible_to_map=lambda *_a, **_k: route,
        replanner=lambda: object(),
    )
    monkeypatch.setattr(live_fishing, "_supported_plan", lambda *_a, **_k: True)
    monkeypatch.setattr(live_fishing, "Gen1RouteInterruptionHandler", lambda *_a, **_k: object())

    def execute_route(*_args, **_kwargs):
        actions.actions_executed += 3
        emulator.frame_count += 30
        return SimpleNamespace(passed=True)

    monkeypatch.setattr(live_fishing, "execute_route", execute_route)
    monkeypatch.setattr(live_fishing, "LiveWildEncounterExecutor", lambda *_a, **_k: object())
    monkeypatch.setattr(live_fishing, "LiveRedFishingCapturePort", lambda *_a, **_k: object())

    def capture(*_args, **_kwargs):
        actions.actions_executed += 2
        emulator.frame_count += 20
        registered.add(116)
        return RedFishingCaptureReport(1, 1, 0, 1, 0, 0, 1, 0, 1, False)

    monkeypatch.setattr(live_fishing, "run_red_fishing_capture", capture)
    supplements = live_fishing.build_red_live_fishing_supplements(
        _context(),
        (
            destination,
            live_fishing.RedReachableFishingDestination(
                _offer(24, (117, 118)), _stance(2), 12, 15
            ),
        ),
        free_storage_slots=30,
        world=world,
        observer=SimpleNamespace(observe=lambda: _traversal()),
        field=SimpleNamespace(),
        controller=SimpleNamespace(),
        actions=actions,
        reader=reader,
        emulator=emulator,
    )
    binding = next(
        item.binding for item in supplements if item.binding.estimated_effort < 0.21
    )

    report = binding.execute()

    assert (report.actions_executed, report.frames_executed) == (5, 50)
    assert binding.verify(report).status.value == "succeeded"
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
            live_fishing.RedReachableFishingDestination(
                _offer(24, (117, 118)), _stance(2), 12, 15
            ),
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
    with pytest.raises(ValueError, match="two"):
        live_fishing.discover_reachable_red_fishing_destinations(
            b"rom", set(), world=SimpleNamespace(), traversal=_traversal(), maximum_candidates=1
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
