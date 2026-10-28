"""Bounded, disclosed route support to Victory Road, never combat policy.

Geometry and badge-guard rows come from the cartridge. The pinned Red script
selects a different outside map on each side of Route22Gate; ordinary retained
outside routing cannot represent that selection. Resolve only those four warps
here. No direction string, purchase, move teaching or trainer actor is used.
"""

from dataclasses import dataclass, field, replace

from .actions import MacroAction, MacroActionKind
from .gen1_cartridge import CartridgeReadError, bank_offset
from .gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS, SCRIPT_POINTER_OFFSET
from .gen1_traversal import map_object_events
from .observation import EventFlag, MapId, event_flag_is_set
from .rom import verify_rom_bytes
from .route_executor import InterruptionReceipt, RouteExecutionError

CORRIDOR_MAPS = frozenset({41, 1, 33, 193, 34, 108})
BADGE_EVENTS = tuple(
    range(int(EventFlag.PASSED_CASCADE_BADGE_CHECK), int(EventFlag.PASSED_EARTH_BADGE_CHECK) + 1)
)


def _gate_script(rom):
    """Decode a bounded conditional wLastMap initializer and trigger table."""

    def require(ok):
        if not ok:
            raise CartridgeReadError("unsupported badge-gate script grammar")

    require(isinstance(rom, bytes) and len(rom) > MAP_HEADER_BANKS + 193)
    bank = rom[MAP_HEADER_BANKS + 193]

    def read(address, size):
        at = bank_offset(bank, address)
        require(address >= 0x4000 and address + size <= 0x8000 and at + size <= len(rom))
        return rom[at : at + size]

    header = int.from_bytes(rom[MAP_HEADER_POINTERS + 386 : MAP_HEADER_POINTERS + 388], "little")
    script = int.from_bytes(read(header + SCRIPT_POINTER_OFFSET, 2), "little")
    entry = read(script, 27)
    require(
        entry[:4] == bytes.fromhex("cd 3c 3c 21")
        and entry[6:17] == bytes.fromhex("fa 0e d6 cd 97 3d fa 61 d3 fe 04")
        and entry[17:] == bytes.fromhex("3e 22 38 02 3e 21 ea 65 d3 c9")
    )
    table = int.from_bytes(entry[4:6], "little")
    default = int.from_bytes(read(table, 2), "little")
    body = read(default, 17)
    require(
        body[0] == 0x21 and body[3:] == bytes.fromhex("cd bf 34 d0 af e0 b4 3e 01 e0 8c c3 20 29")
    )
    coordinates = read(int.from_bytes(body[1:3], "little"), 5)
    require(coordinates == bytes((2, 4, 2, 5, 255)))
    return entry[16], entry[18], entry[22], (tuple(coordinates[:2]), tuple(coordinates[2:4]))


def qualified_badge_gate_world(world):
    """Resolve only the cartridge's conditional gate,keeping the whole world.

    This is the same exit decoding used by the earned badge corridor. It
    neither clears a gate nor grants a capability; live traversal still proves
    every passage. Already-resolved exits must match the cartridge exactly.
    """
    verify_rom_bytes(world.rom)
    threshold, north, south, _ = _gate_script(world.rom)
    graph = world.macro_graph
    exits = graph.edges[int(MapId.ROUTE_22_GATE)]
    kinds = {e.kind for e in exits}
    if len(exits) != 4 or kinds not in ({"return"}, {"warp"}) or any(e.at is None for e in exits):
        raise CartridgeReadError("badge gate has unexpected exits")
    resolved = []
    for edge in exits:
        target = north if edge.at[0] < threshold else south
        if edge.destination_warp_index is None or graph.warp_arrivals is None:
            raise CartridgeReadError("badge-gate arrival is not qualified")
        locations = graph.warp_locations.get(target, ())
        arrivals = graph.warp_arrivals.get(target, ())
        if len(arrivals) != len(locations) or edge.destination_warp_index >= len(locations):
            raise CartridgeReadError("badge-gate destination rows are inconsistent")
        # MacroEdge names the raw doorway. The shared router applies the
        # separately qualified settled arrival exactly once (south steps out).
        arrival = locations[edge.destination_warp_index]
        qualified = replace(edge, kind="warp", target_map=target, arrival_at=arrival)
        if edge.kind == "warp" and qualified != edge:
            raise CartridgeReadError("resolved badge-gate exit differs from cartridge")
        resolved.append(qualified)
    return replace(world, macro_graph=replace(
        graph, edges={**graph.edges, int(MapId.ROUTE_22_GATE): tuple(resolved)}))


def corridor_world(world):
    """Restrict navigation to the earned approach and resolve its gate exits."""
    world = qualified_badge_gate_world(world)
    graph = world.macro_graph
    edges = {
        m: tuple(e for e in values if e.target_map is None or e.target_map in CORRIDOR_MAPS)
        for m, values in graph.edges.items()
        if m in CORRIDOR_MAPS
    }
    edges[int(MapId.ROUTE_22_GATE)] = graph.edges[int(MapId.ROUTE_22_GATE)]
    return replace(world, macro_graph=replace(graph, edges=edges))


def badge_boundaries(rom):
    """Bind dialogue to cartridge object rows and pinned Red event semantics."""
    verify_rom_bytes(rom)
    _, _, _, gate_triggers = _gate_script(rom)
    guards = map_object_events(rom, {int(MapId.ROUTE_23)})
    if len(guards) != 7 or len({g.text_id for g in guards}) != 7:
        raise CartridgeReadError("badge corridor guard inventory changed")
    rows = {}
    for guard in guards:
        if not 1 <= guard.text_id <= 7 or guard.at[0] in rows:
            raise CartridgeReadError("badge corridor guard identity changed")
        # Red's seven text IDs run Earth -> Cascade, opposite badge order.
        rows[guard.at[0]] = BADGE_EVENTS[7 - guard.text_id]
    return gate_triggers, rows


def require_corridor_source(raw):
    if (
        raw.map_id not in CORRIDOR_MAPS
        or raw.badge_bits != 255
        or raw.battle_state != 0
        or raw.event_flags is None
        or not event_flag_is_set(raw.event_flags, 1318)
    ):
        raise RouteExecutionError(
            "corridor requires eight earned badges and defeated Route22 rival"
        )


def _protected(raw):
    return tuple(
        getattr(raw, name)
        for name in (
            "party_species_ids",
            "party_levels",
            "party_hp",
            "party_max_hp",
            "party_status",
            "party_moves",
            "party_pp",
            "bag_items",
            "player_money",
            "badge_bits",
        )
    )


@dataclass
class BadgeCorridorInterruptions:
    """Accept only eight named checks and bounded native wild escapes."""

    actions: object
    reader: object
    wild: object
    gate_triggers: tuple
    guard_rows: dict
    maximum_pulses: int = 32
    allow_field_faint_dialogue: bool = False
    receipts: list = field(default_factory=list, init=False)
    _seen: set = field(default_factory=set, init=False)

    def __post_init__(self):
        if type(self.maximum_pulses) is not int or not 1 <= self.maximum_pulses <= 64:
            raise ValueError("badge dialogue pulse cap must be1..64")
        if type(self.allow_field_faint_dialogue) is not bool:
            raise TypeError("badge field faint dialogue opt-in must be boolean")

    @classmethod
    def from_rom(cls, rom, actions, reader, wild, *, allow_field_faint_dialogue=False):
        triggers, rows = badge_boundaries(rom)
        return cls(actions, reader, wild, triggers, rows,
                   allow_field_faint_dialogue=allow_field_faint_dialogue)

    def handle(self, interruption):
        if interruption.interruption == "wild_battle":
            result = self.wild.handle(interruption)
            self.receipts.append(result)
            return result
        if interruption.interruption != "scripted_dialogue":
            raise RouteExecutionError(
                "badge route refuses unrelated interruption or trainer combat"
            )
        before = self.reader.read()
        require_corridor_source(before)
        if (before.map_id, (before.player_y, before.player_x)) != (
            interruption.map_id,
            interruption.at,
        ):
            raise RouteExecutionError("badge dialogue source drifted")
        event = None
        if before.map_id == int(MapId.ROUTE_22_GATE) and interruption.at in self.gate_triggers:
            key = "boulder"
        elif before.map_id == int(MapId.ROUTE_23) and before.player_y in self.guard_rows:
            event = self.guard_rows[before.player_y]
            if event == BADGE_EVENTS[-1] and before.player_x >= 14:
                raise RouteExecutionError("not the Earth badge trigger")
            key = event
        else:
            if self.allow_field_faint_dialogue:
                # Reuse the ordinary-route handler's newly poisoned faint
                # proof and exact resource/location guards. It refuses other
                # scripts; a badge handler must never dismiss them generally.
                result = self.wild.handle(interruption)
                self.receipts.append(result)
                return result
            raise RouteExecutionError("dialogue is outside declared badge boundaries")
        if key in self._seen:
            raise RouteExecutionError("badge dialogue repeated after settlement")
        self._seen.add(key)
        protected = _protected(before)
        for pulse in range(self.maximum_pulses + 1):
            after = self.reader.read()
            require_corridor_source(after)
            if _protected(after) != protected or (after.map_id, after.player_y, after.player_x) != (
                before.map_id,
                before.player_y,
                before.player_x,
            ):
                raise RouteExecutionError("badge dialogue changed location or protected resources")
            expected = bytearray(before.event_flags)
            if event is not None:
                expected[event // 8] |= 1 << (event % 8)
            if after.event_flags not in (before.event_flags, bytes(expected)):
                raise RouteExecutionError("badge dialogue changed unrelated events")
            complete = event is None or event_flag_is_set(after.event_flags, event)
            if complete and self.reader.read_input_readiness().ready:
                result = InterruptionReceipt(
                    "scripted_dialogue",
                    after.map_id,
                    interruption.at,
                    {
                        "badge_event": event,
                        "confirmations": pulse,
                        "authority": "disclosed badge dialogue support",
                        "resources_preserved": True,
                    },
                )
                self.receipts.append(result)
                return result
            if pulse < self.maximum_pulses:
                self.actions.execute(MacroAction(MacroActionKind.CONFIRM))
        raise RouteExecutionError("badge dialogue did not settle within its cap")


def require_corridor_start(raw, ready, *, allow_retained_boundary=False):
    """Admit an earned partial corridor only when explicitly resuming it."""
    if type(allow_retained_boundary) is not bool:
        raise TypeError("retained corridor admission requires an explicit boolean")
    require_corridor_source(raw)
    allowed = CORRIDOR_MAPS if allow_retained_boundary else {int(MapId.VIRIDIAN_POKECENTER)}
    if raw.map_id not in allowed or not ready:
        raise RouteExecutionError("corridor must start at a declared ready earned boundary")


def quote_badge_corridor(rom, reader, memory):
    """Read-only feasible route using the same living field holders as execution."""
    from .gen1_field_moves import gen1_field_capabilities
    from .gen1_route_runtime import Gen1TraversalObserver
    from .gen1_trainer_sight import Gen1TrainerSightProjector
    from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld

    require_corridor_source(reader.read())
    world = corridor_world(StrategicScenarioRouteWorld.from_rom(rom)).with_current_blocks(
        reader.read_current_map_blocks()
    )
    observer = Gen1TraversalObserver(
        reader,
        Gen1TrainerSightProjector(rom, reader, full_event_offsets=True),
        lambda raw: gen1_field_capabilities(memory, raw),
    )
    return world.plan_feasible_to_map(observer.observe(), int(MapId.VICTORY_ROAD_1F))


def traverse_badge_corridor(
    rom,
    reader,
    memory,
    actions,
    *,
    record,
    maximum_flees=8,
    allow_retained_boundary=False,
    allow_party_faints=False,
    allow_field_faint_dialogue=False,
):
    """One shared-router journey; retain receipts even on a partial failure.

    Caller owns source authentication, total action/frame/time caps and final
    state retention. No trainer combat is authorized by this navigation API.
    """
    from .gen1_field_moves import Gen1FieldMovePort, gen1_field_capabilities
    from .gen1_route_runtime import Gen1TraversalObserver, Gen1WildFleeHandler
    from .gen1_trainer_sight import Gen1TrainerSightProjector
    from .route_executor import DEFAULT_ROUTE_EXECUTION_LIMITS, execute_route
    from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld

    before = reader.read()
    require_corridor_start(
        before,
        reader.read_input_readiness().ready,
        allow_retained_boundary=allow_retained_boundary,
    )
    world = corridor_world(StrategicScenarioRouteWorld.from_rom(rom))
    observer = Gen1TraversalObserver(
        reader,
        Gen1TrainerSightProjector(rom, reader, full_event_offsets=True),
        lambda raw: gen1_field_capabilities(memory, raw),
    )

    def current_world():
        return world.with_current_blocks(reader.read_current_map_blocks())

    plan = current_world().plan_to_map(observer.observe(), int(MapId.VICTORY_ROAD_1F))
    port = Gen1FieldMovePort(actions, reader, memory)
    wild = Gen1WildFleeHandler(
        port, reader, maximum_flees, stabilization_frames=120, route_name="earned badge corridor",
        allow_party_faints=allow_party_faints, emulator=memory,
        allow_field_faint_dialogue=allow_field_faint_dialogue,
    )
    handler = BadgeCorridorInterruptions.from_rom(
        rom, port, reader, wild, allow_field_faint_dialogue=allow_field_faint_dialogue,
    )
    record("planned-route", plan)
    try:
        report = execute_route(
            plan,
            port,
            observer,
            interruption_handler=handler,
            replanner=lambda request: current_world().replanner()(request),
            limits=replace(
                DEFAULT_ROUTE_EXECUTION_LIMITS,
                max_interruptions=8 + maximum_flees + (6 if allow_field_faint_dialogue else 0),
                max_replans=16,
                max_readiness_waits=100,
            ),
        )
        terminal = observer.observe()
        after = reader.read()
        if (
            terminal.map_id != int(MapId.VICTORY_ROAD_1F)
            or not terminal.ready
            or terminal.interruption is not None
            or not all(event_flag_is_set(after.event_flags, flag) for flag in BADGE_EVENTS)
        ):
            raise RouteExecutionError("badge corridor did not prove entrance and all seven checks")
        for name in (
            "party_species_ids",
            "party_moves",
            "party_levels",
            "bag_items",
            "player_money",
        ):
            if getattr(before, name) != getattr(after, name):
                raise RouteExecutionError("corridor changed protected party or inventory")
        record("route-result", report)
        return terminal
    finally:
        record("interruptions", tuple(handler.receipts))
        record("wild-escapes", tuple(wild.evidence))
        record("field-faint-settlement", tuple(wild.field_faint_evidence))
        record("field-moves", {"surf": port.receipts})
