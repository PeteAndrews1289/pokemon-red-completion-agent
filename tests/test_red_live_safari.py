"""Action-free coverage for the ranked live Safari acquisition."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.collection import CollectionObservation
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_story_routing import apply_gen1_safari_admission_requirement
from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.gen1_traversal import TraversalRules, surf_local_graph
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind, GoalSituation
from pokemon_red_completion.living_dex_option_value import (
    living_dex_option_context_from_goal_situation,
)
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.observation import (
    Badge,
    MapId,
    OverworldMovementMode,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
    RedSafariSessionState,
)
from pokemon_red_completion.red_acquisition import (
    RED_ACQUISITION_CATALOG,
    RedAreaExecutionError,
    RedAreaExecutionReport,
    summarize_red_area_survey,
)
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_live_safari import (
    RedLiveSafariError,
    RedReachableSafariArea,
    RedSafariEntryMode,
    _live_safari_binding,
    _registered_safari_catalog,
    build_red_live_safari_inventory,
    discover_eligible_red_safari_areas,
    discover_reachable_red_safari_areas,
    quote_red_safari_funding,
    resolve_red_safari_entry_mode,
)
from pokemon_red_completion.red_safari_acquisition import (
    RedSafariPatrolPlan,
    RedSafariZoneOffer,
    enter_red_safari_area_from_gate,
    plan_red_safari_gate_approach,
)


def _area(source: str, map_id: int, productive_slots: int, route_steps: int):
    slots = tuple((25, 111 if index < productive_slots else 30) for index in range(10))
    offer = RedSafariZoneOffer(source, map_id, slots, (111,))
    start = {
        int(MapId.SAFARI_ZONE_CENTER): (25, 15),
        int(MapId.SAFARI_ZONE_NORTH): (31, 39),
    }[map_id]
    patrol = RedSafariPatrolPlan(
        source,
        map_id,
        start,
        ("up",),
        (start[0] - 1, start[1]),
        (start[0] - 2, start[1]),
        2,
        "up",
        "down",
    )
    return RedReachableSafariArea(offer, patrol, route_steps)


def pilot_binding(search_actions=None, **overrides):
    args = dict(
        area=_area("wild:SafariZoneCenter:grass", int(MapId.SAFARI_ZONE_CENTER), 3, 4),
        mode=RedSafariEntryMode.GATE, bound_map_id=156, bound_coords=(3, 4),
        free_storage_slots=2, controller=SimpleNamespace(), actions=SimpleNamespace(),
        reader=SimpleNamespace(), maximum_encounters=6, maximum_search_actions=search_actions,
    )
    args.update(overrides)
    return _live_safari_binding(**args)


def test_search_target_identity_ignores_origin_and_dose_but_tracks_remaining_targets():
    area = _area("wild:SafariZoneCenter:grass", int(MapId.SAFARI_ZONE_CENTER), 3, 4)
    binding = pilot_binding(area=area)
    moved = pilot_binding(128, area=area, bound_coords=(4, 4))
    assert binding.search_objective_sha256 == moved.search_objective_sha256
    two_targets = replace(area, offer=replace(area.offer, missing_species_numbers=(30, 111)))
    changed = pilot_binding(area=two_targets)
    assert binding.search_objective_sha256 != changed.search_objective_sha256
    reordered = replace(two_targets, offer=replace(
        two_targets.offer, slots=tuple(reversed(two_targets.offer.slots))))
    assert changed.search_objective_sha256 == pilot_binding(
        area=reordered).search_objective_sha256


@pytest.mark.parametrize("captured", [True, False])
def test_complete_paid_session_reserves_exit_and_keeps_capture_verdict(monkeypatch, captured):
    import pokemon_red_completion.red_paid_safari_departure as departure

    world, _ = _real_gate_safari_fixture(monkeypatch, cash=500, player_x=3, player_y=4)
    sim = _LiveGateExecutionController(initial_money=500)
    actions = CountingExecutor(sim)
    calls = []
    monkeypatch.setattr(departure, "paid_search_step_reserve", lambda *_: 70)

    def survey(*args, **kwargs):
        calls.append("search")
        assert kwargs["policy"].max_actions > 66
        assert kwargs["capture_resources_available"]()
        sim.safari_steps = 70
        assert not kwargs["capture_resources_available"]()
        sim.safari_steps = 71
        sim.safari_balls = 8
        assert not kwargs["capture_resources_available"]()
        sim.safari_balls = 9
        assert kwargs["capture_resources_available"]()
        if captured:
            sim.owned.add(30)
        return RedAreaExecutionReport("wild:SafariZoneCenter:grass", (), (), 100, 4,
                                      int(captured), 3, 0, search_exhausted=not captured)

    def exit_search(*args):
        calls.append("exit")
        assert args[1] is actions
        actions.actions_executed += 10
        sim.frame_count += 50
        return {"passed": True}

    monkeypatch.setattr("pokemon_red_completion.red_live_safari.run_red_area_survey", survey)
    monkeypatch.setattr(departure, "exit_paid_search", exit_search)
    inventory = build_red_live_safari_inventory(
        b"rom", frozenset({30}),
        living_dex_option_context_from_goal_situation(
            GoalSituation(0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)),
        free_storage_slots=2, world=world, controller=sim, actions=actions,
        reader=sim, complete_paid_session=True,
    )
    binding = inventory.supplements[0].binding
    report = binding.execute()
    assert calls == ["search", "exit"]
    assert report.actions_executed == actions.actions_executed
    assert report.frames_executed == sim.frame_count
    assert report.evidence["paid_session_departure"] == {"passed": True}
    assert report.evidence["reserved_exit_steps"] == 70
    assert (binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED) is captured
    assert sim.money == 0  # Exactly one payment, despite search+exit composition.


def test_complete_paid_session_cannot_rewrite_fixed_training_probe():
    with pytest.raises(ValueError, match="training probe"):
        pilot_binding(100, complete_paid_session=True, world=object())


@pytest.mark.parametrize("limit", [True, False, 0, -1, 257, 1.0, "128"])
def test_pilot_search_bound_rejects_invalid_limit(limit):
    with pytest.raises(ValueError, match="search action bound"):
        pilot_binding(limit)


def test_pilot_search_bound_is_in_binding_identity_without_changing_default():
    from pokemon_red_completion.provenance import canonical_sha256
    area = _area("wild:SafariZoneCenter:grass", int(MapId.SAFARI_ZONE_CENTER), 3, 4)
    legacy = "pokemon.red:safari-live:" + canonical_sha256(dict(
        source=area.offer.source_id, missing=area.offer.missing_species_numbers,
        patrol=area.patrol.public_dict(), maximum_encounters=6))
    assert pilot_binding().binding_ref == legacy
    assert len({pilot_binding(n).binding_ref for n in [None, 1, 128, 256]}) == 4


def test_pilot_search_dose_stops_between_encounters_not_during_battle(monkeypatch):
    import pokemon_red_completion.red_live_safari as safari
    raw = SimpleNamespace(map_id=156, player_x=3, player_y=4, player_money=3000,
                          battle_state=0)
    reader = SimpleNamespace(read=lambda: raw,
                             read_pokedex_state=lambda: SimpleNamespace(owned_species=()))
    report = SimpleNamespace(public_dict=lambda: {}, continuation=None)
    monkeypatch.setattr(safari, "resolve_red_safari_entry_mode", lambda *a, **k:
                        RedSafariEntryMode.GATE)
    monkeypatch.setattr(safari, "prepare_red_safari_gate_origin", lambda *a: report)
    monkeypatch.setattr(safari, "enter_red_safari_area_from_gate", lambda *a, **k: report)

    def encounter():
        raw.battle_state = 1

    monkeypatch.setattr(safari, "LiveSafariPatrol", lambda *a: SimpleNamespace(
        enter=lambda: None, seek_step=encounter))
    monkeypatch.setattr(safari, "LiveSafariAreaExecutor", lambda *a, **k: SimpleNamespace(
        seek_step=k["seek_step"], safari_balls_available=lambda: True))

    def survey(source, port, *, policy, safety_check, **kwargs):
        assert policy.max_actions == 128 and policy.max_encounters == 6
        for i in range(6):
            assert safety_check()
            port.seek_step()
            assert safety_check()  # allow settling the current encounter
            raw.battle_state = 0
            assert safety_check() is (i < 5)
        return RedAreaExecutionReport(source, (), (), 12, 6, 0, 6, 0, True)

    monkeypatch.setattr(safari, "run_red_area_survey", survey)
    binding = pilot_binding(128, reader=reader, world=SimpleNamespace(),
                            controller=SimpleNamespace(frame_count=0, pressed_buttons=()),
                            actions=SimpleNamespace(actions_executed=0))
    execution = binding.execute()
    assert execution.evidence["encounters_seen"] == 6
    assert execution.evidence["captures"] == 0


@pytest.mark.parametrize("expose_all_areas", [False, True])
def test_live_safari_builds_ranked_bindings_without_input(monkeypatch, expose_all_areas) -> None:
    monkeypatch.setattr(
        "pokemon_red_completion.red_live_safari.resolve_red_safari_entry_mode",
        lambda *_args, **_kwargs: RedSafariEntryMode.OUTDOOR_FLY,
    )
    center = _area(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        3,
        4,
    )
    north = _area(
        "wild:SafariZoneNorth:grass",
        int(MapId.SAFARI_ZONE_NORTH),
        2,
        2,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_live_safari.discover_reachable_red_safari_areas",
        lambda *_args, **_kwargs: (center, north),
    )
    controller = SimpleNamespace(frame_count=0, pressed_buttons=frozenset())
    actions = CountingExecutor(
        SimpleNamespace(execute=lambda _action: (_ for _ in ()).throw(AssertionError("input")))
    )
    reader = SimpleNamespace(read=lambda: SimpleNamespace(player_money=706))
    situation = GoalSituation(
        story_pressure=0.0,
        collection_pressure=1.0,
        team_pressure=0.0,
        evolution_pressure=1.0,
        safety_pressure=0.0,
        resource_pressure=0.0,
        storage_pressure=0.0,
        recovery_pressure=0.0,
        exploration_pressure=0.0,
    )

    inventory = build_red_live_safari_inventory(
        b"rom",
        frozenset(),
        living_dex_option_context_from_goal_situation(situation),
        free_storage_slots=2,
        world=SimpleNamespace(),
        controller=controller,
        actions=actions,
        reader=reader,
        expose_all_areas=expose_all_areas,
    )

    assert inventory.areas == (center, north)
    assert len(inventory.supplements) == (2 if expose_all_areas else 1)
    assert len({s.binding.binding_ref for s in inventory.supplements}) == len(inventory.supplements)
    if expose_all_areas:
        assert (
            inventory.supplements[0].candidate.features
            != inventory.supplements[1].candidate.features
        )
    assert inventory.supplements[0].binding.kind is GoalKind.ACQUIRE_SPECIES
    assert inventory.supplements[0].candidate.binding_ref == (
        inventory.supplements[0].binding.binding_ref
    )
    assert actions.actions_executed == controller.frame_count == 0
    assert inventory.public_dict()["identity_fields_public"] == 0


def test_live_safari_empty_inventory_has_no_executor(monkeypatch) -> None:
    monkeypatch.setattr(
        "pokemon_red_completion.red_live_safari.discover_reachable_red_safari_areas",
        lambda *_args, **_kwargs: (),
    )
    actions = CountingExecutor(SimpleNamespace(execute=lambda _action: None))
    inventory = build_red_live_safari_inventory(
        b"rom",
        frozenset(),
        living_dex_option_context_from_goal_situation(
            GoalSituation(0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        ),
        free_storage_slots=1,
        world=SimpleNamespace(),
        controller=SimpleNamespace(frame_count=0, pressed_buttons=frozenset()),
        actions=actions,
        reader=SimpleNamespace(read=lambda: None),
    )
    assert inventory.areas == inventory.supplements == ()
    assert actions.actions_executed == 0


def test_live_safari_single_area_still_builds_top_level_acquisition(monkeypatch) -> None:
    monkeypatch.setattr(
        "pokemon_red_completion.red_live_safari.resolve_red_safari_entry_mode",
        lambda *_args, **_kwargs: RedSafariEntryMode.OUTDOOR_FLY,
    )
    center = _area(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        3,
        4,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_live_safari.discover_reachable_red_safari_areas",
        lambda *_args, **_kwargs: (center,),
    )
    controller = SimpleNamespace(frame_count=0, pressed_buttons=frozenset())
    actions = CountingExecutor(SimpleNamespace(execute=lambda _action: None))
    inventory = build_red_live_safari_inventory(
        b"rom",
        frozenset(),
        living_dex_option_context_from_goal_situation(
            GoalSituation(0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        ),
        free_storage_slots=1,
        world=SimpleNamespace(),
        controller=controller,
        actions=actions,
        reader=SimpleNamespace(read=lambda: SimpleNamespace(player_money=706)),
    )
    assert inventory.areas == (center,)
    assert len(inventory.supplements) == 1
    assert actions.actions_executed == 0


def test_live_safari_execution_catalog_excludes_registered_living_demand() -> None:
    center = _area(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        3,
        4,
    )
    catalog = _registered_safari_catalog(center, frozenset({48}))
    observation = CollectionObservation(
        owned_species=frozenset({red_species_ref(48)}),
        specimens=(),
        party_size=0,
        party_limit=6,
        box_counts=(0,),
        current_box_index=0,
        box_capacity=20,
    )

    survey = summarize_red_area_survey(center.offer.source_id, observation, catalog)

    assert (
        red_species_ref(48)
        in summarize_red_area_survey(
            center.offer.source_id,
            observation,
            RED_ACQUISITION_CATALOG,
        ).missing_species_refs
    )
    assert survey.missing_species_refs == (red_species_ref(111),)
    assert red_species_ref(48) not in survey.missing_species_refs


def test_discover_reachable_requires_actual_admission_cash(monkeypatch):
    from pokemon_red_completion.observation import RawGameState
    from pokemon_red_completion.red_live_safari import (
        discover_reachable_red_safari_areas,
    )

    center = _area("wild:SafariZoneCenter:grass", int(MapId.SAFARI_ZONE_CENTER), 3, 4)
    monkeypatch.setattr(
        "pokemon_red_completion.red_live_safari.discover_eligible_red_safari_areas",
        lambda *_args, **_kwargs: (center,),
    )

    for cash, expected in [
        (198, False),
        (499, False),
        (500, True),
        (501, True),
        (None, False),
        (True, False),
        (False, False),
        (-1, False),
        ("500", False),
    ]:
        raw = RawGameState(True, int(MapId.CELADON_CITY), 10, 10, 1, 0, player_money=cash)
        reader = SimpleNamespace(read=lambda r=raw: r)
        areas = discover_reachable_red_safari_areas(
            b"rom", frozenset(), free_storage_slots=2, world=SimpleNamespace(), reader=reader
        )
        if expected:
            assert areas == (center,), f"expected reachable for cash={cash}"
        else:
            assert areas == (), f"expected blocked for cash={cash}"


def test_quote_available_when_execution_blocked_by_cash(monkeypatch):
    import pokemon_red_completion.red_safari_acquisition as safari_acq
    from pokemon_red_completion.actions import MacroActionKind
    from pokemon_red_completion.gen1_terrain import Terrain
    from pokemon_red_completion.local_router import LocalEdge, LocalGraph
    from pokemon_red_completion.observation import Badge, OverworldMovementMode, RawGameState
    from pokemon_red_completion.red_live_safari import (
        discover_reachable_red_safari_areas,
        quote_red_safari_funding,
    )

    # Low-level cartridge decoding stubs
    monkeypatch.setattr(safari_acq, "internal_to_dex", lambda _rom: {10: 111, 11: 30})
    monkeypatch.setattr(
        safari_acq,
        "wild_tables",
        lambda _rom, **_kwargs: {
            int(MapId.SAFARI_ZONE_CENTER): [(25, 10)] * 3 + [(25, 11)] * 7,
        },
    )

    height, width = 30, 30
    grass = [[False] * width for _ in range(height)]
    grass[23][15] = True
    walkable = tuple(tuple(True for _ in range(width)) for _ in range(height))
    terrain = Terrain(
        map_id=int(MapId.SAFARI_ZONE_CENTER),
        tileset=0,
        walkable=walkable,
        grass=tuple(tuple(r) for r in grass),
        water=tuple(tuple(False for _ in range(width)) for _ in range(height)),
        tiles=tuple(tuple(0 for _ in range(width)) for _ in range(height)),
    )
    edges = {
        (25, 15): (
            LocalEdge((24, 15), "up", required_mode="land", action_kind=MacroActionKind.MOVE),
        ),
        (24, 15): (
            LocalEdge((23, 15), "up", required_mode="land", action_kind=MacroActionKind.MOVE),
            LocalEdge((25, 15), "down", required_mode="land", action_kind=MacroActionKind.MOVE),
        ),
        (23, 15): (
            LocalEdge((24, 15), "down", required_mode="land", action_kind=MacroActionKind.MOVE),
        ),
    }
    graph = LocalGraph(edges)
    world = SimpleNamespace(
        rom=b"rom",
        terrain={int(MapId.SAFARI_ZONE_CENTER): terrain},
        local_graphs={int(MapId.SAFARI_ZONE_CENTER): graph},
        object_blockers={int(MapId.SAFARI_ZONE_CENTER): frozenset()},
        macro_graph=SimpleNamespace(warp_locations={int(MapId.SAFARI_ZONE_CENTER): ()}),
    )

    raw = RawGameState(
        game_started=True,
        map_id=int(MapId.CELADON_CITY),
        player_x=10,
        player_y=10,
        party_count=1,
        battle_state=0,
        player_money=198,
        badge_bits=int(Badge.THUNDER),
        party_hp=(50,),
        party_moves=((0x13, 0, 0, 0),),
    )
    reader = SimpleNamespace(
        read=lambda: raw,
        read_input_readiness=lambda: SimpleNamespace(ready=True),
        read_overworld_movement_mode=lambda: OverworldMovementMode.WALKING,
        read_bottom_dialogue_box_visible=lambda: False,
        read_pending_trainer_battle_identity=lambda: None,
        read_fly_destinations=lambda: (int(MapId.FUCHSIA_CITY),),
    )

    # Executable discovery returns empty tuple because 198 < 500
    areas = discover_reachable_red_safari_areas(
        b"rom", frozenset({30}), free_storage_slots=2, world=world, reader=reader
    )
    assert areas == ()

    # Real quote through real discover_eligible_red_safari_areas returns cost 500 / shortfall 302
    quote = quote_red_safari_funding(
        b"rom", frozenset({30}), free_storage_slots=2, world=world, reader=reader
    )
    assert quote is not None
    assert quote.cost == 500
    assert quote.shortfall == 302


def test_safari_gate_map_156_unsupported_without_readiness_or_graphs() -> None:
    # Map 156 (Safari gate) without readiness, event flags, or gate graphs must be blocked
    raw = RawGameState(True, 156, 3, 4, 1, 0, player_money=1000)
    reader = SimpleNamespace(read=lambda: raw)

    assert (
        discover_eligible_red_safari_areas(
            b"rom", frozenset(), free_storage_slots=2, world=SimpleNamespace(), reader=reader
        )
        == ()
    )
    assert (
        discover_reachable_red_safari_areas(
            b"rom", frozenset(), free_storage_slots=2, world=SimpleNamespace(), reader=reader
        )
        == ()
    )


def _real_gate_safari_fixture(
    monkeypatch,
    *,
    cash: object = 198,
    player_x: int = 3,
    player_y: int = 4,
    map_id: int = int(MapId.SAFARI_ZONE_GATE),
    badge_bits: int = 0,
    party_count: int = 6,
    party_species: tuple[int, ...] = (99, 64, 120, 118, 28, 128),
    battle_state: int = 0,
    event_flags: bytes | None = b"\x00" * 320,
    safari_balls: int = 0,
    safari_steps: int = 0,
    gate_script: object = 0,
    input_ready: bool = True,
    movement_mode: OverworldMovementMode = OverworldMovementMode.WALKING,
    dialogue_visible: bool = False,
    pending_trainer: object = None,
    with_gate_terrain: bool = True,
    with_gate_graph: bool = True,
    blocked_gate_coords: frozenset[tuple[int, int]] = frozenset(),
):
    import pokemon_red_completion.red_safari_acquisition as safari_acq

    monkeypatch.setattr(safari_acq, "internal_to_dex", lambda _rom: {10: 111, 11: 30})
    monkeypatch.setattr(
        safari_acq,
        "wild_tables",
        lambda _rom, **_kwargs: {
            int(MapId.SAFARI_ZONE_CENTER): [(25, 10)] * 3 + [(25, 11)] * 7,
        },
    )

    height, width = 30, 30
    grass = [[False] * width for _ in range(height)]
    grass[23][15] = True
    walkable = tuple(tuple(True for _ in range(width)) for _ in range(height))
    terrain_center = Terrain(
        map_id=int(MapId.SAFARI_ZONE_CENTER),
        tileset=0,
        walkable=walkable,
        grass=tuple(tuple(r) for r in grass),
        water=tuple(tuple(False for _ in range(width)) for _ in range(height)),
        tiles=tuple(tuple(0 for _ in range(width)) for _ in range(height)),
    )
    edges_center = {
        (25, 15): (
            LocalEdge((24, 15), "up", action_kind=MacroActionKind.MOVE),
        ),
        (24, 15): (
            LocalEdge((23, 15), "up", action_kind=MacroActionKind.MOVE),
            LocalEdge((25, 15), "down", action_kind=MacroActionKind.MOVE),
        ),
        (23, 15): (
            LocalEdge((24, 15), "down", action_kind=MacroActionKind.MOVE),
        ),
    }
    graph_center = LocalGraph(edges_center)

    terrain_gate = Terrain(
        map_id=int(MapId.SAFARI_ZONE_GATE),
        tileset=0,
        walkable=tuple(tuple(2 <= y <= 5 and x in (3, 4) for x in range(width))
                       for y in range(height)),
        grass=tuple(tuple(False for _ in range(width)) for _ in range(height)),
        water=tuple(tuple(False for _ in range(width)) for _ in range(height)),
        tiles=tuple(tuple(0 for _ in range(width)) for _ in range(height)),
    )
    graph_gate = apply_gen1_safari_admission_requirement({
        int(MapId.SAFARI_ZONE_GATE): surf_local_graph(
            terrain_gate, TraversalRules((), (), (), (), ())
        ),
    })[int(MapId.SAFARI_ZONE_GATE)]

    terrain_dict = {int(MapId.SAFARI_ZONE_CENTER): terrain_center}
    if with_gate_terrain:
        terrain_dict[int(MapId.SAFARI_ZONE_GATE)] = terrain_gate
    graphs_dict = {int(MapId.SAFARI_ZONE_CENTER): graph_center}
    if with_gate_graph:
        graphs_dict[int(MapId.SAFARI_ZONE_GATE)] = graph_gate

    world = SimpleNamespace(
        rom=b"rom",
        terrain=terrain_dict,
        local_graphs=graphs_dict,
        object_blockers={
            int(MapId.SAFARI_ZONE_CENTER): frozenset(),
            int(MapId.SAFARI_ZONE_GATE): blocked_gate_coords,
        },
        macro_graph=SimpleNamespace(warp_locations={int(MapId.SAFARI_ZONE_CENTER): ()}),
    )

    raw = RawGameState(
        game_started=True,
        map_id=map_id,
        player_x=player_x,
        player_y=player_y,
        party_count=party_count,
        battle_state=battle_state,
        player_money=cash,  # type: ignore[arg-type]
        badge_bits=badge_bits,
        party_species_ids=party_species,
        event_flags=event_flags,
    )

    class GateReader:
        def read_safari_zone_gate_script(self):
            return gate_script

        def __init__(self, raw_state: RawGameState):
            self.raw = raw_state
            self.safari_balls = safari_balls
            self.safari_steps = safari_steps

        def read(self) -> RawGameState:
            return self.raw

        def read_u8(self, address: int) -> int:
            if address == int(RamAddress.SAFARI_BALLS):
                return self.safari_balls
            if address == int(RamAddress.SAFARI_STEPS):
                return (self.safari_steps >> 8) & 0xFF
            if address == int(RamAddress.SAFARI_STEPS) + 1:
                return self.safari_steps & 0xFF
            return 0

        def read_input_readiness(self) -> SimpleNamespace:
            return SimpleNamespace(ready=input_ready)

        def read_overworld_movement_mode(self) -> OverworldMovementMode:
            return movement_mode

        def read_bottom_dialogue_box_visible(self) -> bool:
            return dialogue_visible

        def read_pending_trainer_battle_identity(self) -> object:
            return pending_trainer

        def read_fly_destinations(self) -> tuple[int, ...]:
            return ()

        def read_pokedex_state(self) -> SimpleNamespace:
            return SimpleNamespace(owned_species=())

        def read_safari_session_state(self) -> RedSafariSessionState:
            flags = self.raw.event_flags or b""
            in_safari = False
            game_over = False
            if len(flags) > 73:
                in_safari = bool(flags[73] & (1 << 7))
                game_over = bool(flags[73] & (1 << 6))
            return RedSafariSessionState(
                safari_balls=self.safari_balls,
                safari_steps=self.safari_steps,
                in_safari_zone=in_safari,
                safari_game_over=game_over,
            )

    return world, GateReader(raw)


@pytest.mark.parametrize("balls,steps", [(0, 0), (28, 473), (5, 0), (0, 10)])
@pytest.mark.parametrize("lane", [3, 4])
def test_gate_truthful_quote_at_198_cash_and_zero_executable_acquisition(
    monkeypatch, balls, steps, lane
) -> None:
    world, reader = _real_gate_safari_fixture(
        monkeypatch, cash=198, player_x=lane, player_y=4,
        safari_balls=balls, safari_steps=steps,
    )
    controller = SimpleNamespace(frame_count=0, pressed_buttons=frozenset())
    actions = CountingExecutor(SimpleNamespace(execute=lambda _a: None))

    # Truthful quote through discover_eligible_red_safari_areas
    quote = quote_red_safari_funding(
        b"rom", frozenset({30}), free_storage_slots=2, world=world, reader=reader
    )
    assert quote is not None
    assert quote.available_cash == 198
    assert quote.cost == 500
    assert quote.shortfall == 302
    assert quote.target_cash == 500

    # Executable reachable areas is empty because 198 < 500
    reachable = discover_reachable_red_safari_areas(
        b"rom", frozenset({30}), free_storage_slots=2, world=world, reader=reader
    )
    assert reachable == ()

    # Inventory builds 0 areas and 0 supplements without executing controller inputs
    inventory = build_red_live_safari_inventory(
        b"rom",
        frozenset({30}),
        living_dex_option_context_from_goal_situation(
            GoalSituation(0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        ),
        free_storage_slots=2,
        world=world,
        controller=controller,
        actions=actions,
        reader=reader,
    )
    assert inventory.areas == ()
    assert inventory.supplements == ()
    assert actions.actions_executed == 0
    assert controller.frame_count == 0


@pytest.mark.parametrize("balls,steps", [(0, 0), (28, 473)])
def test_gate_threshold_499_blocked_500_executable(monkeypatch, balls, steps) -> None:
    world, reader_499 = _real_gate_safari_fixture(
        monkeypatch, cash=499, player_x=3, player_y=4, safari_balls=balls, safari_steps=steps
    )
    assert (
        discover_reachable_red_safari_areas(
            b"rom", frozenset({30}), free_storage_slots=2, world=world, reader=reader_499
        )
        == ()
    )

    world, reader_500 = _real_gate_safari_fixture(
        monkeypatch, cash=500, player_x=3, player_y=4, safari_balls=balls, safari_steps=steps
    )
    reachable = discover_reachable_red_safari_areas(
        b"rom", frozenset({30}), free_storage_slots=2, world=world, reader=reader_500
    )
    assert len(reachable) == 1
    assert reachable[0].offer.source_id == "wild:SafariZoneCenter:grass"

    controller = SimpleNamespace(frame_count=0, pressed_buttons=frozenset())
    actions = CountingExecutor(SimpleNamespace(execute=lambda _a: None))
    inventory = build_red_live_safari_inventory(
        b"rom",
        frozenset({30}),
        living_dex_option_context_from_goal_situation(
            GoalSituation(0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        ),
        free_storage_slots=2,
        world=world,
        controller=controller,
        actions=actions,
        reader=reader_500,
    )
    assert len(inventory.areas) == 1
    assert len(inventory.supplements) == 1
    assert inventory.supplements[0].binding.kind is GoalKind.ACQUIRE_SPECIES
    assert actions.actions_executed == 0
    assert controller.frame_count == 0


class _LiveGateExecutionController:
    def __init__(
        self,
        initial_money: int = 500,
        player_x: int = 3,
        player_y: int = 4,
        clerk_dialogue: bool = False,
        gate_script: int = 0,
        player_facing: str = "down",
    ) -> None:
        self.frame_count = 0
        self.pressed_buttons: frozenset[str] = frozenset()
        self.money = initial_money
        self.safari_balls = 0
        self.safari_steps = 0
        self.dialogue_confirms = 0
        self.clerk_dialogue = clerk_dialogue
        self.gate_script = gate_script
        self.player_facing = player_facing
        self.lateral_step_done = False
        self.owned: set[int] = set()
        self.raw = RawGameState(
            game_started=True,
            map_id=int(MapId.SAFARI_ZONE_GATE),
            player_x=player_x,
            player_y=player_y,
            party_count=6,
            battle_state=0,
            party_species_ids=(99, 64, 120, 118, 28, 128),
            event_flags=b"\x00" * 320,
            player_money=initial_money,
        )

    def read_u8(self, address: int) -> int:
        if address == RamAddress.CURRENT_MAP:
            return int(self.raw.map_id)
        if address == RamAddress.TRAINER_TEXT_SPRITE_INDEX:
            return 3 if self.gate_script == 0 else 4
        s = f"{max(0, min(999999, self.money)):06d}"
        bcd = (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
        if address == int(RamAddress.PLAYER_MONEY):
            return bcd[0]
        if address == int(RamAddress.PLAYER_MONEY) + 1:
            return bcd[1]
        if address == int(RamAddress.PLAYER_MONEY) + 2:
            return bcd[2]
        if address == int(RamAddress.SAFARI_BALLS):
            return self.safari_balls
        if address == int(RamAddress.SAFARI_STEPS):
            return (self.safari_steps >> 8) & 0xFF
        if address == int(RamAddress.SAFARI_STEPS) + 1:
            return self.safari_steps & 0xFF
        if address == int(RamAddress.SAFARI_ZONE_GATE_SCRIPT):
            return self.gate_script
        if address == int(RamAddress.PLAYER_FACING_DIRECTION):
            return {"down": 0, "up": 4, "left": 8, "right": 12}.get(self.player_facing, 0)
        return 0

    def execute(self, action: MacroAction) -> None:
        if action.kind is MacroActionKind.WAIT:
            self.frame_count += action.repeat
            return
        if action.kind is MacroActionKind.MOVE:
            delta_y = {"up": -1, "down": 1}.get(str(action.value), 0)
            delta_x = {"left": -1, "right": 1}.get(str(action.value), 0)
            cur_x = int(self.raw.player_x or 0)
            cur_y = int(self.raw.player_y or 0)
            new_x = cur_x + delta_x
            new_y = cur_y + delta_y
            self.raw = replace(
                self.raw,
                player_x=new_x,
                player_y=new_y,
            )
            if self.raw.map_id == MapId.SAFARI_ZONE_CENTER:
                self.safari_steps = max(0, self.safari_steps - 1)
            elif (
                self.raw.map_id == MapId.SAFARI_ZONE_GATE
                and (new_x, new_y) in {(3, 2), (4, 2)}
            ):
                self.clerk_dialogue = True
                self.gate_script = 0
                self.player_facing = str(action.value)
        elif action.kind is MacroActionKind.CONFIRM:
            self.dialogue_confirms += 1
            if (
                self.raw.map_id == MapId.SAFARI_ZONE_GATE
                and (self.raw.player_x, self.raw.player_y) in {(3, 2), (4, 2)}
            ):
                if self.gate_script == 0:
                    self.player_facing = "right"
                    if (self.raw.player_x, self.raw.player_y) == (3, 2):
                        self.lateral_step_done = True
                        self.gate_script = 1
                        self.raw = replace(self.raw, player_x=4, player_y=2)
                    else:
                        self.gate_script = 2
                elif self.gate_script in {1, 2}:
                    self.money = max(0, self.money - 500)
                    self.safari_balls = 30
                    self.safari_steps = 500
                    flags = bytearray(self.raw.event_flags or b"\x00" * 320)
                    flags[73] |= 1 << 7
                    self.gate_script = 3
                    self.raw = replace(
                        self.raw,
                        map_id=MapId.SAFARI_ZONE_CENTER,
                        player_x=15,
                        player_y=25,
                        player_money=self.money,
                        event_flags=bytes(flags),
                    )
                    self.clerk_dialogue = False
                    self.gate_script = 0
                elif not self.clerk_dialogue and self.dialogue_confirms >= 2:
                    self.money = max(0, self.money - 500)
                    self.safari_balls = 30
                    self.safari_steps = 500
                    flags = bytearray(self.raw.event_flags or b"\x00" * 320)
                    flags[73] |= 1 << 7
                    self.raw = replace(
                        self.raw,
                        map_id=MapId.SAFARI_ZONE_CENTER,
                        player_x=15,
                        player_y=25,
                        player_money=self.money,
                        event_flags=bytes(flags),
                    )

    def read(self) -> RawGameState:
        return self.raw

    def read_safari_session_state(self) -> RedSafariSessionState:
        flags = self.raw.event_flags or b""
        in_safari = False
        game_over = False
        if len(flags) > 73:
            in_safari = bool(flags[73] & (1 << 7))
            game_over = bool(flags[73] & (1 << 6))
        return RedSafariSessionState(
            safari_balls=self.safari_balls,
            safari_steps=self.safari_steps,
            in_safari_zone=in_safari,
            safari_game_over=game_over,
        )

    def read_input_readiness(self) -> SimpleNamespace:
        return SimpleNamespace(ready=not self.clerk_dialogue)

    def read_overworld_movement_mode(self) -> OverworldMovementMode:
        return OverworldMovementMode.WALKING

    def read_bottom_dialogue_box_visible(self) -> bool:
        return self.clerk_dialogue

    def read_safari_zone_gate_script(self) -> int:
        return self.gate_script

    def read_safari_clerk_dialogue(self) -> str | None:
        return PokemonRedStateReader(self).read_safari_clerk_dialogue()

    def read_player_facing(self) -> str:
        return self.player_facing

    def read_pending_trainer_battle_identity(self) -> object:
        return None

    def read_fly_destinations(self) -> tuple[int, ...]:
        return ()

    def read_pokedex_state(self) -> SimpleNamespace:
        return SimpleNamespace(owned_species=tuple(self.owned))


@pytest.mark.parametrize("balls,steps", [(0, 0), (28, 473)])
def test_gate_origin_full_binding_execution_at_500_cash(monkeypatch, balls, steps) -> None:
    world, _ = _real_gate_safari_fixture(monkeypatch, cash=500, player_x=3, player_y=4)
    sim = _LiveGateExecutionController(initial_money=500)
    sim.safari_balls = balls
    sim.safari_steps = steps
    actions = CountingExecutor(sim)

    # Monkeypatch run_red_area_survey to complete bounded capture
    def mock_survey(*_args, **_kwargs) -> RedAreaExecutionReport:
        sim.owned.add(30)
        return RedAreaExecutionReport(
            source_id="wild:SafariZoneCenter:grass",
            initial_missing_species_refs=("Nidorina",),
            final_missing_species_refs=(),
            actions_executed=5,
            encounters_seen=1,
            captures=1,
            flees=0,
            box_switches=0,
            search_exhausted=False,
        )

    monkeypatch.setattr(
        "pokemon_red_completion.red_live_safari.run_red_area_survey",
        mock_survey,
    )

    inventory = build_red_live_safari_inventory(
        b"rom",
        frozenset({30}),
        living_dex_option_context_from_goal_situation(
            GoalSituation(0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        ),
        free_storage_slots=2,
        world=world,
        controller=sim,  # type: ignore[arg-type]
        actions=actions,
        reader=sim,  # type: ignore[arg-type]
    )

    assert len(inventory.supplements) == 1
    binding = inventory.supplements[0].binding

    report = binding.execute()

    # Transport details
    transport = report.evidence["transport"]
    assert isinstance(transport, dict)
    assert transport["entry_mode"] == "gate"
    assert transport["verified_fly_receipts"] == 0
    assert transport["status"] == "ok"

    # Admission details
    admission = report.evidence["admission"]
    assert isinstance(admission, dict)
    assert admission["single_admission"] is True
    assert admission["status"] == "ok"
    assert admission["safari_balls_remaining"] == 30

    # Verification
    verification = binding.verify(report)
    assert verification.status is GoalDecisionOutcome.SUCCEEDED
    assert verification.failure_reason is None
    assert not sim.pressed_buttons


@pytest.mark.parametrize(
    "invalid_kwargs",
    [
        {"battle_state": 1},
        {"input_ready": False},
        {"dialogue_visible": True},
        {"pending_trainer": "trainer_1"},
        {"movement_mode": OverworldMovementMode.SURFING},
        {"event_flags": None},
        {"gate_script": 1},
        {"gate_script": 2},
        {"gate_script": 3},
        {"gate_script": 4},
        {"gate_script": 5},
        {"gate_script": 6},
        {"gate_script": None},
        {"gate_script": False},
        {"gate_script": "0"},
        {"with_gate_terrain": False},
        {"with_gate_graph": False},
        {"blocked_gate_coords": frozenset({(2, 3), (2, 4)})},
        {"player_x": 1, "player_y": 1},
        {"map_id": 150},
    ],
)
def test_gate_rejects_unready_ambiguous_and_active_states(monkeypatch, invalid_kwargs) -> None:
    world, reader = _real_gate_safari_fixture(monkeypatch, cash=500, **invalid_kwargs)
    assert resolve_red_safari_entry_mode(reader, world, free_storage_slots=2) is None
    assert (
        discover_eligible_red_safari_areas(
            b"rom", frozenset({30}), free_storage_slots=2, world=world, reader=reader
        )
        == ()
    )


@pytest.mark.parametrize("missing", [True, False])
def test_gate_quote_rejects_unreadable_phase(monkeypatch, missing) -> None:
    world, reader = _real_gate_safari_fixture(monkeypatch, safari_balls=28, safari_steps=473)

    def unreadable():
        raise ValueError("unreadable phase")

    reader.read_safari_zone_gate_script = None if missing else unreadable
    assert resolve_red_safari_entry_mode(reader, world) is None
    assert quote_red_safari_funding(
        b"rom", frozenset({30}), free_storage_slots=2, world=world, reader=reader
    ) is None


def test_preserved_outdoor_fly_mode_and_contrast_with_gate(monkeypatch) -> None:
    # Outdoor Celadon origin requires Thunder badge and Fly move
    raw_outdoor = RawGameState(
        game_started=True,
        map_id=int(MapId.CELADON_CITY),
        player_x=10,
        player_y=10,
        party_count=1,
        battle_state=0,
        player_money=500,
        badge_bits=int(Badge.THUNDER),
        party_hp=(50,),
        party_moves=((0x13, 0, 0, 0),),
    )
    outdoor_reader = SimpleNamespace(
        read=lambda: raw_outdoor,
        read_input_readiness=lambda: SimpleNamespace(ready=True),
        read_overworld_movement_mode=lambda: OverworldMovementMode.WALKING,
        read_bottom_dialogue_box_visible=lambda: False,
        read_pending_trainer_battle_identity=lambda: None,
        read_fly_destinations=lambda: (int(MapId.FUCHSIA_CITY),),
    )
    assert (
        resolve_red_safari_entry_mode(outdoor_reader, SimpleNamespace(), free_storage_slots=2)
        is RedSafariEntryMode.OUTDOOR_FLY
    )

    # Without Thunder badge, outdoor fly is rejected
    outdoor_no_badge = replace(raw_outdoor, badge_bits=0)
    reader_no_badge = SimpleNamespace(
        read=lambda: outdoor_no_badge,
        read_input_readiness=lambda: SimpleNamespace(ready=True),
        read_overworld_movement_mode=lambda: OverworldMovementMode.WALKING,
        read_bottom_dialogue_box_visible=lambda: False,
        read_pending_trainer_battle_identity=lambda: None,
        read_fly_destinations=lambda: (int(MapId.FUCHSIA_CITY),),
    )
    assert (
        resolve_red_safari_entry_mode(reader_no_badge, SimpleNamespace(), free_storage_slots=2)
        is None
    )

    # In contrast, gate mode does NOT require Thunder badge, fly move, or fly destinations
    world_gate, reader_gate = _real_gate_safari_fixture(
        monkeypatch, cash=500, badge_bits=0, player_x=3, player_y=4
    )
    assert (
        resolve_red_safari_entry_mode(reader_gate, world_gate, free_storage_slots=2)
        is RedSafariEntryMode.GATE
    )


def test_discriminating_probe_disabling_gate_eligibility_fails_named_regression(
    monkeypatch,
) -> None:
    world, reader = _real_gate_safari_fixture(monkeypatch, cash=198, player_x=3, player_y=4)

    # Baseline: valid gate origin produces quote of 500 cost / 302 shortfall
    baseline_quote = quote_red_safari_funding(
        b"rom", frozenset({30}), free_storage_slots=2, world=world, reader=reader
    )
    assert baseline_quote is not None
    assert baseline_quote.cost == 500
    assert baseline_quote.shortfall == 302

    # Discriminating mutation: disable gate eligibility in resolve_red_safari_entry_mode
    monkeypatch.setattr(
        "pokemon_red_completion.red_live_safari.resolve_red_safari_entry_mode",
        lambda _reader, _world, free_storage_slots=1: None,
    )

    # Under mutation, gate quote must fail closed (return None) and areas must be empty
    mutated_quote = quote_red_safari_funding(
        b"rom", frozenset({30}), free_storage_slots=2, world=world, reader=reader
    )
    assert mutated_quote is None
    assert (
        discover_eligible_red_safari_areas(
            b"rom", frozenset({30}), free_storage_slots=2, world=world, reader=reader
        )
        == ()
    )


def test_discriminating_probe_bypassing_exact_charge_fails_named_regression() -> None:
    offer = RedSafariZoneOffer(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        tuple((25, 30) for _ in range(10)),
        (30,),
    )
    # Under mutation where clerk charges 400 instead of 500, admission must fail closed
    simulation = _LiveGateExecutionController(initial_money=500)
    simulation.raw = replace(simulation.raw, player_x=3, player_y=2)

    # Tampered execute charging 400
    def tampered_execute(action: MacroAction) -> None:
        if action.kind is MacroActionKind.WAIT:
            simulation.frame_count += action.repeat
            return
        if action.kind is MacroActionKind.CONFIRM:
            simulation.money = 100  # 400 fee instead of 500
            simulation.safari_balls = 30
            simulation.safari_steps = 500
            simulation.raw = replace(
                simulation.raw,
                map_id=MapId.SAFARI_ZONE_CENTER,
                player_x=15,
                player_y=25,
                player_money=100,
            )

    simulation.execute = tampered_execute  # type: ignore[method-assign]

    with pytest.raises(RedAreaExecutionError) as err:
        enter_red_safari_area_from_gate(
            simulation,  # type: ignore[arg-type]
            CountingExecutor(simulation),
            simulation,  # type: ignore[arg-type]
            offer,
        )
    assert err.value.reason_code == "safari_admission_resources_changed"


def test_finding_1_production_graph_builder_resolves_gate_at_x3_y4(monkeypatch) -> None:
    world, reader = _real_gate_safari_fixture(monkeypatch, cash=500, player_x=3, player_y=4)
    gate_graph = world.local_graphs[int(MapId.SAFARI_ZONE_GATE)]
    assert (3, 3) in gate_graph.edges
    assert any(edge.required_mode == "land" for edge in gate_graph.edges[(3, 3)])

    mode = resolve_red_safari_entry_mode(reader, world, free_storage_slots=2)
    assert mode is RedSafariEntryMode.GATE

    reachable = discover_reachable_red_safari_areas(
        b"rom", frozenset({30}), free_storage_slots=2, world=world, reader=reader
    )
    assert len(reachable) == 1
    assert reachable[0].offer.source_id == "wild:SafariZoneCenter:grass"


def test_finding_2_unauthenticated_session_state_and_truncated_flags_rejected(
    monkeypatch,
) -> None:
    world, reader_empty = _real_gate_safari_fixture(monkeypatch, cash=500, event_flags=b"")
    assert resolve_red_safari_entry_mode(reader_empty, world, free_storage_slots=2) is None

    world, reader_short = _real_gate_safari_fixture(
        monkeypatch, cash=500, event_flags=b"\x00" * 73
    )
    assert resolve_red_safari_entry_mode(reader_short, world, free_storage_slots=2) is None

    world, reader_base = _real_gate_safari_fixture(monkeypatch, cash=500)

    class ReaderNoSessionState:
        def __init__(self, inner: object) -> None:
            self._inner = inner

        def read(self) -> RawGameState:
            return self._inner.read()  # type: ignore[attr-defined]

        def read_input_readiness(self) -> SimpleNamespace:
            return self._inner.read_input_readiness()  # type: ignore[attr-defined]

        def read_overworld_movement_mode(self) -> OverworldMovementMode:
            return self._inner.read_overworld_movement_mode()  # type: ignore[attr-defined]

        def read_bottom_dialogue_box_visible(self) -> bool:
            return self._inner.read_bottom_dialogue_box_visible()  # type: ignore[attr-defined]

        def read_pending_trainer_battle_identity(self) -> object:
            return self._inner.read_pending_trainer_battle_identity()  # type: ignore[attr-defined]

    assert (
        resolve_red_safari_entry_mode(
            ReaderNoSessionState(reader_base), world, free_storage_slots=2
        )
        is None
    )

    class ReaderRaisingSessionState(ReaderNoSessionState):
        def read_safari_session_state(self) -> RedSafariSessionState:
            raise RuntimeError("WRAM observation failed")

    assert (
        resolve_red_safari_entry_mode(
            ReaderRaisingSessionState(reader_base), world, free_storage_slots=2
        )
        is None
    )

    world, reader_balls = _real_gate_safari_fixture(monkeypatch, cash=500, safari_balls=30)
    assert (
        resolve_red_safari_entry_mode(reader_balls, world, free_storage_slots=2)
        is RedSafariEntryMode.GATE
    )

    world, reader_steps = _real_gate_safari_fixture(monkeypatch, cash=500, safari_steps=500)
    assert (
        resolve_red_safari_entry_mode(reader_steps, world, free_storage_slots=2)
        is RedSafariEntryMode.GATE
    )

    flags_in_safari = bytearray(b"\x00" * 320)
    flags_in_safari[73] |= 1 << 7
    world, reader_in_safari = _real_gate_safari_fixture(
        monkeypatch, cash=500, event_flags=bytes(flags_in_safari)
    )
    assert resolve_red_safari_entry_mode(reader_in_safari, world, free_storage_slots=2) is None

    flags_game_over = bytearray(b"\x00" * 320)
    flags_game_over[73] |= 1 << 6
    world, reader_game_over = _real_gate_safari_fixture(
        monkeypatch, cash=500, event_flags=bytes(flags_game_over)
    )
    assert resolve_red_safari_entry_mode(reader_game_over, world, free_storage_slots=2) is None


def test_finding_3_destination_blocking_regression(monkeypatch) -> None:
    terrain = Terrain(
        map_id=int(MapId.SAFARI_ZONE_GATE),
        tileset=0,
        walkable=tuple(tuple(True for _ in range(10)) for _ in range(10)),
        grass=tuple(tuple(False for _ in range(10)) for _ in range(10)),
        water=tuple(tuple(False for _ in range(10)) for _ in range(10)),
        tiles=tuple(tuple(0 for _ in range(10)) for _ in range(10)),
    )
    gate_graph = surf_local_graph(terrain, TraversalRules((), (), (), (), ()))

    assert plan_red_safari_gate_approach(gate_graph, (4, 3), (2, 3), frozenset({(2, 3)})) is None
    row3_blockers = frozenset({(3, x) for x in range(10)})
    assert plan_red_safari_gate_approach(gate_graph, (4, 3), (2, 3), row3_blockers) is None
    approach_start_blocked = plan_red_safari_gate_approach(
        gate_graph, (4, 3), (2, 3), frozenset({(4, 3)})
    )
    assert approach_start_blocked is not None and len(approach_start_blocked.edges) == 2
    approach_same_coord = plan_red_safari_gate_approach(gate_graph, (2, 3), (2, 3), frozenset())
    assert approach_same_coord is not None and approach_same_coord.edges == ()
    assert plan_red_safari_gate_approach(gate_graph, (2, 3), (2, 3), frozenset({(2, 3)})) is None

    world, reader_blocked_counters = _real_gate_safari_fixture(
        monkeypatch,
        cash=500,
        player_x=3,
        player_y=4,
        blocked_gate_coords=frozenset({(2, 3), (2, 4)}),
    )
    assert (
        resolve_red_safari_entry_mode(
            reader_blocked_counters, world, free_storage_slots=2
        )
        is None
    )

    world, reader_at_counter = _real_gate_safari_fixture(
        monkeypatch,
        cash=500,
        player_x=3,
        player_y=2,
    )
    assert (
        resolve_red_safari_entry_mode(reader_at_counter, world, free_storage_slots=2)
        is RedSafariEntryMode.GATE
    )


def test_finding_4_stale_cash_and_precondition_revalidation_fails_closed(monkeypatch) -> None:
    world, _ = _real_gate_safari_fixture(monkeypatch, cash=500, player_x=3, player_y=4)
    sim = _LiveGateExecutionController(initial_money=500)
    actions = CountingExecutor(sim)

    inventory = build_red_live_safari_inventory(
        b"rom",
        frozenset({30}),
        living_dex_option_context_from_goal_situation(
            GoalSituation(0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        ),
        free_storage_slots=2,
        world=world,
        controller=sim,  # type: ignore[arg-type]
        actions=actions,
        reader=sim,  # type: ignore[arg-type]
    )
    assert len(inventory.supplements) == 1
    binding = inventory.supplements[0].binding

    sim.money = 198
    sim.raw = replace(sim.raw, player_money=198)

    with pytest.raises(RedLiveSafariError, match="insufficient for Safari admission"):
        binding.execute()

    assert actions.actions_executed == 0
    assert sim.frame_count == 0

    sim_dirty = _LiveGateExecutionController(initial_money=500)
    sim_dirty.raw = replace(sim_dirty.raw, player_x=3, player_y=2)
    sim_dirty.pressed_buttons = frozenset({"A"})
    offer = RedSafariZoneOffer(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        tuple((25, 30) for _ in range(10)),
        (30,),
    )
    with pytest.raises(RedAreaExecutionError) as err_pressed:
        enter_red_safari_area_from_gate(
            sim_dirty,  # type: ignore[arg-type]
            CountingExecutor(sim_dirty),
            sim_dirty,  # type: ignore[arg-type]
            offer,
        )
    assert err_pressed.value.reason_code == "safari_admission_controller_held"
    assert sim_dirty.frame_count == 0

    sim_unready = _LiveGateExecutionController(initial_money=500)
    sim_unready.raw = replace(sim_unready.raw, player_x=3, player_y=2)
    sim_unready.read_input_readiness = lambda: SimpleNamespace(ready=False)  # type: ignore[method-assign]
    with pytest.raises(RedAreaExecutionError) as err_unready:
        enter_red_safari_area_from_gate(
            sim_unready,  # type: ignore[arg-type]
            CountingExecutor(sim_unready),
            sim_unready,  # type: ignore[arg-type]
            offer,
        )
    assert err_unready.value.reason_code == "safari_admission_origin_unready"
    assert sim_unready.frame_count == 0

    sim_active = _LiveGateExecutionController(initial_money=500)
    sim_active.raw = replace(sim_active.raw, player_x=3, player_y=2)
    sim_active.safari_balls = 30
    sim_active.read_safari_session_state = lambda: RedSafariSessionState(30, 0, True, False)
    with pytest.raises(RedAreaExecutionError) as err_active:
        enter_red_safari_area_from_gate(
            sim_active,  # type: ignore[arg-type]
            CountingExecutor(sim_active),
            sim_active,  # type: ignore[arg-type]
            offer,
        )
    assert err_active.value.reason_code == "safari_admission_session_state_active"
    assert sim_active.frame_count == 0


def test_finding_5_zero_route_admission_party_and_pokedex_verification() -> None:
    offer = RedSafariZoneOffer(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        tuple((25, 30) for _ in range(10)),
        (30,),
    )

    class ZeroRouteMutatePartySim(_LiveGateExecutionController):
        def execute(self, action: MacroAction) -> None:
            super().execute(action)
            if action.kind is MacroActionKind.CONFIRM and self.dialogue_confirms >= 1:
                self.raw = replace(self.raw, party_species_ids=(25, 64, 120, 118, 28, 128))

    sim_party = ZeroRouteMutatePartySim(initial_money=500)
    sim_party.raw = replace(sim_party.raw, player_x=3, player_y=2)
    with pytest.raises(RedAreaExecutionError) as err_party:
        enter_red_safari_area_from_gate(
            sim_party,  # type: ignore[arg-type]
            CountingExecutor(sim_party),
            sim_party,  # type: ignore[arg-type]
            offer,
        )
    assert err_party.value.reason_code == "safari_admission_party_invalid"

    class ZeroRouteLostPokedexSim(_LiveGateExecutionController):
        def __init__(self) -> None:
            super().__init__(initial_money=500)
            self.owned = {1, 2, 3}

        def execute(self, action: MacroAction) -> None:
            super().execute(action)
            if action.kind is MacroActionKind.CONFIRM and self.dialogue_confirms >= 1:
                self.owned = {1, 2}

    sim_pokedex = ZeroRouteLostPokedexSim()
    sim_pokedex.raw = replace(sim_pokedex.raw, player_x=3, player_y=2)
    with pytest.raises(RedAreaExecutionError) as err_dex:
        enter_red_safari_area_from_gate(
            sim_pokedex,  # type: ignore[arg-type]
            CountingExecutor(sim_pokedex),
            sim_pokedex,  # type: ignore[arg-type]
            offer,
        )
    assert err_dex.value.reason_code == "safari_admission_pokedex_invalid"


def test_correction_b_gate_binding_rejects_changed_coordinates_within_gate(monkeypatch) -> None:
    world, _ = _real_gate_safari_fixture(monkeypatch, cash=500, player_x=3, player_y=4)
    sim = _LiveGateExecutionController(initial_money=500, player_x=3, player_y=4)
    actions = CountingExecutor(sim)

    inventory = build_red_live_safari_inventory(
        b"rom",
        frozenset({30}),
        living_dex_option_context_from_goal_situation(
            GoalSituation(0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        ),
        free_storage_slots=2,
        world=world,
        controller=sim,  # type: ignore[arg-type]
        actions=actions,
        reader=sim,  # type: ignore[arg-type]
    )
    assert len(inventory.supplements) == 1
    binding = inventory.supplements[0].binding

    # Change simulated raw position to (4, 4) within GATE mode
    sim.raw = replace(sim.raw, player_x=4, player_y=4)

    with pytest.raises(RedLiveSafariError, match="does not match bound origin"):
        binding.execute()

    # Assert against the exercised input port, frame counter, and funds: ZERO executed
    assert actions.actions_executed == 0
    assert sim.frame_count == 0
    assert sim.money == 500


def test_correction_b_gate_binding_rejects_changed_map_or_mode(monkeypatch) -> None:
    world, _ = _real_gate_safari_fixture(monkeypatch, cash=500, player_x=3, player_y=4)
    sim = _LiveGateExecutionController(initial_money=500, player_x=3, player_y=4)
    actions = CountingExecutor(sim)

    inventory = build_red_live_safari_inventory(
        b"rom",
        frozenset({30}),
        living_dex_option_context_from_goal_situation(
            GoalSituation(0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        ),
        free_storage_slots=2,
        world=world,
        controller=sim,  # type: ignore[arg-type]
        actions=actions,
        reader=sim,  # type: ignore[arg-type]
    )
    assert len(inventory.supplements) == 1
    binding = inventory.supplements[0].binding

    # Change simulated map to PALLET_TOWN
    sim.raw = replace(sim.raw, map_id=int(MapId.PALLET_TOWN))

    with pytest.raises(RedLiveSafariError):
        binding.execute()

    assert actions.actions_executed == 0
    assert sim.frame_count == 0
    assert sim.money == 500


def test_correction_b_rebuilt_binding_at_new_origin_succeeds(monkeypatch) -> None:
    world, _ = _real_gate_safari_fixture(monkeypatch, cash=500, player_x=4, player_y=4)
    sim = _LiveGateExecutionController(initial_money=500, player_x=4, player_y=4)
    actions = CountingExecutor(sim)

    def mock_survey(*_args, **_kwargs) -> RedAreaExecutionReport:
        sim.owned.add(30)
        return RedAreaExecutionReport(
            source_id="wild:SafariZoneCenter:grass",
            initial_missing_species_refs=("Nidorina",),
            final_missing_species_refs=(),
            actions_executed=5,
            encounters_seen=1,
            captures=1,
            flees=0,
            box_switches=0,
            search_exhausted=False,
        )

    monkeypatch.setattr(
        "pokemon_red_completion.red_live_safari.run_red_area_survey",
        mock_survey,
    )

    inventory = build_red_live_safari_inventory(
        b"rom",
        frozenset({30}),
        living_dex_option_context_from_goal_situation(
            GoalSituation(0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        ),
        free_storage_slots=2,
        world=world,
        controller=sim,  # type: ignore[arg-type]
        actions=actions,
        reader=sim,  # type: ignore[arg-type]
    )
    assert len(inventory.supplements) == 1
    binding = inventory.supplements[0].binding

    report = binding.execute()
    assert report.evidence["encounters_seen"] == 1
    assert report.evidence["captures"] == 1
    assert sim.money == 0
    assert sim.safari_balls == 30
    assert not sim.lateral_step_done


def test_correction_b_unchanged_origin_succeeds(monkeypatch) -> None:
    world, _ = _real_gate_safari_fixture(monkeypatch, cash=500, player_x=3, player_y=4)
    sim = _LiveGateExecutionController(initial_money=500, player_x=3, player_y=4)
    actions = CountingExecutor(sim)

    def mock_survey(*_args, **_kwargs) -> RedAreaExecutionReport:
        sim.owned.add(30)
        return RedAreaExecutionReport(
            source_id="wild:SafariZoneCenter:grass",
            initial_missing_species_refs=("Nidorina",),
            final_missing_species_refs=(),
            actions_executed=5,
            encounters_seen=1,
            captures=1,
            flees=0,
            box_switches=0,
            search_exhausted=False,
        )

    monkeypatch.setattr(
        "pokemon_red_completion.red_live_safari.run_red_area_survey",
        mock_survey,
    )

    inventory = build_red_live_safari_inventory(
        b"rom",
        frozenset({30}),
        living_dex_option_context_from_goal_situation(
            GoalSituation(0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        ),
        free_storage_slots=2,
        world=world,
        controller=sim,  # type: ignore[arg-type]
        actions=actions,
        reader=sim,  # type: ignore[arg-type]
    )
    binding = inventory.supplements[0].binding

    report = binding.execute()
    assert report.evidence["encounters_seen"] == 1
    assert report.evidence["captures"] == 1


@pytest.mark.parametrize("player_x", [3, 4])
def test_gate_quote_and_preparation_share_alternate_lane(monkeypatch, player_x) -> None:
    from pokemon_red_completion.red_safari_acquisition import prepare_red_safari_gate_origin

    world, reader = _real_gate_safari_fixture(
        monkeypatch, cash=500, player_x=player_x, player_y=4,
        blocked_gate_coords=frozenset({(2, player_x)}),
    )
    assert resolve_red_safari_entry_mode(reader, world) is RedSafariEntryMode.GATE
    assert quote_red_safari_funding(
        b"rom", frozenset({30}), free_storage_slots=2, world=world, reader=reader,
    ) is not None
    sim = _LiveGateExecutionController(500, player_x=player_x, player_y=4)
    prep = prepare_red_safari_gate_origin(sim, CountingExecutor(sim), sim, world)
    assert prep.passed and prep.final_position == (3 if player_x == 4 else 4, 2)


def test_inventory_does_not_guess_fly_when_entry_becomes_unknown(monkeypatch) -> None:
    world, reader = _real_gate_safari_fixture(monkeypatch, cash=500)
    import pokemon_red_completion.red_live_safari as safari

    real_resolver = safari.resolve_red_safari_entry_mode
    calls = 0

    def changing_resolver(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_resolver(*args, **kwargs) if calls == 1 else None

    monkeypatch.setattr(safari, "resolve_red_safari_entry_mode", changing_resolver)
    inventory = build_red_live_safari_inventory(
        b"rom", frozenset({30}),
        living_dex_option_context_from_goal_situation(
            GoalSituation(0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        ),
        free_storage_slots=2, world=world,
        controller=SimpleNamespace(frame_count=0, pressed_buttons=frozenset()),
        actions=CountingExecutor(
            SimpleNamespace(execute=lambda _: pytest.fail("unexpected input"))
        ),
        reader=reader,
    )
    assert calls == 2 and inventory.supplements == ()
