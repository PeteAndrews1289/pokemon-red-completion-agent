from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion import red_badge_corridor as corridor
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.global_router import MacroEdge, MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError, plan_route
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


def cartridge():
    rom = bytearray(0x20000)
    rom[corridor.MAP_HEADER_BANKS + 193] = 3
    rom[corridor.MAP_HEADER_POINTERS + 386 : corridor.MAP_HEADER_POINTERS + 388] = b"\x00\x41"
    rom[0xC107:0xC109] = b"\x00\x42"
    entry = bytes.fromhex(
        "cd 3c 3c 21 00 43 fa 0e d6 cd 97 3d fa 61 d3 fe 04 3e 22 38 02 3e 21 ea 65 d3 c9"
    )
    rom[0xC200 : 0xC200 + len(entry)] = entry
    rom[0xC300:0xC302] = b"\x00\x44"
    body = bytes.fromhex("21 00 45 cd bf 34 d0 af e0 b4 3e 01 e0 8c c3 20 29")
    rom[0xC400 : 0xC400 + len(body)] = body
    rom[0xC500:0xC505] = bytes((2, 4, 2, 5, 255))
    return bytes(rom)


def test_gate_decoder_reads_conditional_destinations():
    assert corridor._gate_script(cartridge()) == (4, 34, 33, ((2, 4), (2, 5)))


@pytest.mark.parametrize(
    "address", [0xC200, 0xC20C, 0xC210, 0xC212, 0xC216, 0xC219, 0xC405, 0xC504]
)
def test_gate_decoder_rejects_changed_script(address):
    rom = bytearray(cartridge())
    rom[address] ^= 1
    with pytest.raises(CartridgeReadError):
        corridor._gate_script(bytes(rom))


def test_scope_keeps_center_return_and_resolves_both_sides(monkeypatch):
    monkeypatch.setattr(corridor, "verify_rom_bytes", lambda _: None)
    exits = tuple(
        MacroEdge(None, "return", at=at, destination_warp_index=idx)
        for at, idx in (((7, 4), 0), ((7, 5), 0), ((0, 4), 0), ((0, 5), 1))
    )
    graph = MacroGraph(
        {
            41: (MacroEdge(None, "return", at=(7, 3)),),
            193: exits,
            34: (MacroEdge(108), MacroEdge(194)),
            194: (),
        },
        warp_locations={33: ((5, 8),), 34: ((139, 7), (139, 8))},
        warp_arrivals={33: ((5, 8),), 34: ((139, 7), (139, 8))},
    )
    world = StrategicScenarioRouteWorld(graph, {}, cartridge(), {}, None, {}, frozenset(), {})
    full = corridor.qualified_badge_gate_world(world)
    assert set(full.macro_graph.edges) == set(graph.edges)
    assert full.macro_graph.edges[194] == graph.edges[194]
    assert full.macro_graph.edges[34] == graph.edges[34]
    assert full.local_graphs is world.local_graphs
    assert full.object_blockers is world.object_blockers
    assert full.macro_graph.warp_locations is graph.warp_locations
    assert full.macro_graph.warp_arrivals is graph.warp_arrivals
    assert corridor.qualified_badge_gate_world(full) == full
    result = corridor.corridor_world(world)
    assert result.macro_graph.edges[41] == graph.edges[41]
    assert 194 not in result.macro_graph.edges
    assert result.macro_graph.edges[34] == (MacroEdge(108),)
    assert [(e.target_map, e.arrival_at) for e in result.macro_graph.edges[193]] == [
        (33, (5, 8)),
        (33, (5, 8)),
        (34, (139, 7)),
        (34, (139, 8)),
    ]
    assert graph.edges[193] == exits


@pytest.mark.parametrize("fault", ["target", "arrival", "mixed"])
def test_resolved_full_world_cannot_silently_repair_unqualified_exits(monkeypatch, fault):
    monkeypatch.setattr(corridor, "verify_rom_bytes", lambda _: None)
    exits = tuple(
        MacroEdge(None, "return", at=at, destination_warp_index=idx)
        for at, idx in (((7, 4), 0), ((7, 5), 0), ((0, 4), 0), ((0, 5), 1))
    )
    graph = MacroGraph(
        {193: exits, 33: (), 34: (), 145: ()},
        warp_locations={33: ((5, 8),), 34: ((139, 7), (139, 8))},
        warp_arrivals={33: ((6, 8),), 34: ((139, 7), (139, 8))},
    )
    world = StrategicScenarioRouteWorld(graph, {}, cartridge(), {}, None, {}, frozenset(), {})
    full = corridor.qualified_badge_gate_world(world)
    fixed = list(full.macro_graph.edges[193])
    fixed[0] = (
        replace(fixed[0], target_map=34) if fault == "target"
        else replace(fixed[0], arrival_at=(6, 8)) if fault == "arrival"
        else exits[0]
    )
    bad = replace(full, macro_graph=replace(full.macro_graph, edges={
        **full.macro_graph.edges, 193: tuple(fixed)}))
    with pytest.raises(CartridgeReadError):
        corridor.qualified_badge_gate_world(bad)
    assert full.macro_graph.edges[193][0].target_map == 33


def test_southern_exit_composes_raw_doorway_to_distinct_settled_arrival(monkeypatch):
    monkeypatch.setattr(corridor, "verify_rom_bytes", lambda _: None)
    exits = tuple(
        MacroEdge(
            None,
            "return",
            at=at,
            destination_warp_index=idx,
            exit_action="down" if at[0] == 7 else None,
        )
        for at, idx in (((7, 4), 0), ((7, 5), 0), ((0, 4), 0), ((0, 5), 1))
    )
    graph = MacroGraph(
        {193: exits, 33: (), 34: ()},
        warp_locations={193: tuple(e.at for e in exits), 33: ((5, 8),), 34: ((139, 7), (139, 8))},
        warp_arrivals={193: tuple(e.at for e in exits), 33: ((6, 8),), 34: ((139, 7), (139, 8))},
    )
    local = {
        193: LocalGraph(
            {
                (4, 4): (LocalEdge((5, 4), "down"),),
                (5, 4): (LocalEdge((6, 4), "down"),),
                (6, 4): (LocalEdge((7, 4), "down"),),
                (7, 4): (),
            }
        ),
        33: LocalGraph({(6, 8): (LocalEdge((7, 8), "down"),), (7, 8): ()}),
    }
    world = StrategicScenarioRouteWorld(graph, local, cartridge(), {}, None, {}, frozenset(), {})
    fixed = corridor.corridor_world(world)
    assert fixed.macro_graph.edges[193][0].arrival_at == (5, 8)
    route = plan_route(
        fixed.macro_graph,
        local,
        193,
        (4, 4),
        33,
        goal_at=(6, 8),
        start_mode="land",
        last_outside=33,
    )
    assert route.terminal_at == (6, 8)
    assert route.actions == ("down", "down", "down", "down")
    assert route.segments[0].transition.arrival_at == (6, 8)
    broken = replace(
        graph,
        edges={
            **graph.edges,
            193: tuple(
                replace(e, arrival_at=(6, 8)) if e.target_map == 33 else e
                for e in fixed.macro_graph.edges[193]
            ),
        },
    )
    with pytest.raises(RoutePlanningError):
        plan_route(
            broken, local, 193, (4, 4), 33, goal_at=(6, 8), start_mode="land", last_outside=33
        )


@pytest.mark.parametrize(
    "locations,arrivals",
    [
        ((), ((6, 8),)),
        (((5, 8),), ()),
        (((5, 8),), ((6, 8), (6, 9))),
        ((), ()),
    ],
)
def test_gate_destination_metadata_must_be_complete(monkeypatch, locations, arrivals):
    monkeypatch.setattr(corridor, "verify_rom_bytes", lambda _: None)
    exits = tuple(
        MacroEdge(None, "return", at=at, destination_warp_index=idx)
        for at, idx in (((7, 4), 0), ((7, 5), 0), ((0, 4), 0), ((0, 5), 1))
    )
    graph = MacroGraph(
        {193: exits},
        warp_locations={33: locations, 34: ((139, 7), (139, 8))},
        warp_arrivals={33: arrivals, 34: ((139, 7), (139, 8))},
    )
    world = StrategicScenarioRouteWorld(graph, {}, cartridge(), {}, None, {}, frozenset(), {})
    with pytest.raises(CartridgeReadError, match="destination rows are inconsistent"):
        corridor.corridor_world(world)


def flags(*events):
    values = bytearray(320)
    for event in (1318, *events):
        values[event // 8] |= 1 << (event % 8)
    return bytes(values)


def test_retained_corridor_admission_is_explicit_and_keeps_earned_guards():
    raw = NS(map_id=34, badge_bits=255, battle_state=0, event_flags=flags())
    with pytest.raises(RouteExecutionError):
        corridor.require_corridor_start(raw, True)
    corridor.require_corridor_start(raw, True, allow_retained_boundary=True)
    for changes in (
        dict(badge_bits=127),
        dict(battle_state=2),
        dict(map_id=10),
        dict(event_flags=bytes(320)),
    ):
        with pytest.raises(RouteExecutionError):
            corridor.require_corridor_start(
                NS(**(vars(raw) | changes)), True, allow_retained_boundary=True
            )
    with pytest.raises(RouteExecutionError):
        corridor.require_corridor_start(raw, False, allow_retained_boundary=True)
    with pytest.raises(TypeError):
        corridor.require_corridor_start(raw, True, allow_retained_boundary=1)


def fixture(event=1328, fault=None):
    raw = RawGameState(
        True,
        34,
        7,
        136,
        5,
        0,
        badge_bits=255,
        event_flags=flags(),
        player_money=23138,
        party_moves=((70, 57, 58, 44),),
        party_species_ids=(28,),
        party_levels=(52,),
        party_hp=(100,),
        party_max_hp=(100,),
        party_status=(0,),
        party_pp=((15, 15, 10, 25),),
        bag_items=((19, 3),),
    )
    state = NS(raw=raw, ready=False, actions=[])

    def act(action):
        state.actions.append(action)
        state.raw = replace(state.raw, event_flags=flags(event))
        state.ready = True
        changes = {
            "money": {"player_money": 0},
            "moves": {"party_moves": ((1, 2, 3, 4),)},
            "species": {"party_species_ids": (1,)},
            "position": {"player_x": 9},
            "battle": {"battle_state": 2},
            "events": {"event_flags": flags(event, 100)},
            "hp": {"party_hp": (1,)},
            "pp": {"party_pp": ((0, 0, 0, 0),)},
        }
        if fault in changes:
            state.raw = replace(state.raw, **changes[fault])
        if fault == "no_event":
            state.raw = raw
        if fault == "never_ready":
            state.ready = False

    reader = NS(read=lambda: state.raw, read_input_readiness=lambda: NS(ready=state.ready))
    handler = corridor.BadgeCorridorInterruptions(
        NS(execute=act),
        reader,
        NS(handle=lambda i: "escaped"),
        ((2, 4), (2, 5)),
        {136: event},
        maximum_pulses=3,
    )
    snap = TraversalSnapshot(34, (136, 7), False, "scripted_dialogue")
    return state, handler, snap


def test_named_badge_settlement_preserves_resources_and_proves_event():
    state, handler, snap = fixture()
    result = handler.handle(snap)
    assert result.details["badge_event"] == 1328
    assert result.details["confirmations"] == 1
    assert [a.kind for a in state.actions] == [MacroActionKind.CONFIRM]
    assert handler.receipts == [result]
    with pytest.raises(RouteExecutionError, match="repeated"):
        handler.handle(snap)
    assert len(state.actions) == 1


@pytest.mark.parametrize(
    "fault",
    [
        "money",
        "moves",
        "species",
        "position",
        "battle",
        "events",
        "hp",
        "pp",
        "no_event",
        "never_ready",
    ],
)
def test_badge_settlement_fails_closed(fault):
    state, handler, snap = fixture(fault=fault)
    with pytest.raises(RouteExecutionError):
        handler.handle(snap)
    assert 1 <= len(state.actions) <= 3
    assert handler.receipts == []


@pytest.mark.parametrize(
    "fault", ["missing_badge", "rival", "stale", "unknown", "trainer", "east_earth"]
)
def test_unsupported_entry_never_inputs(fault):
    state, handler, snap = fixture()
    if fault == "missing_badge":
        state.raw = replace(state.raw, badge_bits=254)
    if fault == "rival":
        state.raw = replace(state.raw, event_flags=bytes(320))
    if fault == "stale":
        state.raw = replace(state.raw, player_x=8)
    if fault == "unknown":
        handler.guard_rows = {}
    if fault == "trainer":
        snap = replace(snap, interruption="trainer_battle")
    if fault == "east_earth":
        handler.guard_rows = {35: 1334}
        state.raw = replace(state.raw, player_y=35, player_x=14)
        snap = replace(snap, at=(35, 14))
    with pytest.raises(RouteExecutionError):
        handler.handle(snap)
    assert not state.actions


def test_boulder_check_needs_no_synthetic_persistent_event():
    state, handler, snap = fixture()
    state.raw = replace(state.raw, map_id=193, player_y=2, player_x=4)
    handler.actions.execute = lambda _: setattr(state, "ready", True)
    result = handler.handle(replace(snap, map_id=193, at=(2, 4)))
    assert result.details["badge_event"] is None
    assert state.raw.event_flags == flags()


def test_wild_delegates_and_does_not_choose_a_move():
    state, handler, snap = fixture()
    assert handler.handle(replace(snap, interruption="wild_battle")) == "escaped"
    assert state.actions == []


def test_opted_in_outside_badge_dialogue_uses_existing_faint_proof():
    state, handler, snap = fixture()
    state.raw = replace(state.raw, map_id=1, player_y=17, player_x=10)
    snap = replace(snap, map_id=1, at=(17, 10))
    calls = []
    receipt = NS(details={"native_field_faint": True})
    handler.wild.handle = lambda value: calls.append(value) or receipt
    handler.allow_field_faint_dialogue = True
    assert handler.handle(snap) is receipt
    assert calls == [snap]
    assert handler.receipts == [receipt]
    assert state.actions == []


def test_opted_in_unrelated_dialogue_preserves_existing_refusal():
    state, handler, snap = fixture()
    handler.guard_rows = {}
    handler.allow_field_faint_dialogue = True

    def refuse(_):
        raise RouteExecutionError("field dialogue lacks a newly poisoned member faint")

    handler.wild.handle = refuse
    with pytest.raises(RouteExecutionError, match="newly poisoned"):
        handler.handle(snap)
    assert handler.receipts == []
    assert state.actions == []


def test_named_badge_dialogue_remains_badge_owned_when_faint_opted_in():
    state, handler, snap = fixture()
    handler.allow_field_faint_dialogue = True
    handler.wild.handle = lambda _: pytest.fail("a named badge check is not a faint")
    assert handler.handle(snap).details["badge_event"] == 1328
    assert len(state.actions) == 1


@pytest.mark.parametrize("value", [None, 1, "yes"])
def test_badge_faint_opt_in_requires_boolean(value):
    with pytest.raises(TypeError):
        corridor.BadgeCorridorInterruptions(
            None, None, None, (), {}, allow_field_faint_dialogue=value,
        )


@pytest.mark.parametrize("cap", [0, 65, True, 1.5])
def test_invalid_dialogue_cap_refuses(cap):
    with pytest.raises(ValueError):
        corridor.BadgeCorridorInterruptions(None, None, None, (), {}, maximum_pulses=cap)


def test_guard_rows_come_from_cartridge_not_walkthrough(monkeypatch):
    monkeypatch.setattr(corridor, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(
        corridor,
        "map_object_events",
        lambda *a: tuple(NS(text_id=i, at=(10 * i, 2)) for i in range(1, 8)),
    )
    triggers, rows = corridor.badge_boundaries(cartridge())
    assert triggers == ((2, 4), (2, 5))
    assert rows == {10 * i: 1335 - i for i in range(1, 8)}
