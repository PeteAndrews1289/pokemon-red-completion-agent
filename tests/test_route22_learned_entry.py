"""Synthetic script operands and hostile transition sequences; no ROM/save."""

from dataclasses import dataclass, replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion import gen1_route22_script as script
from pokemon_red_completion import red_scripted_rival as entry
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.route_executor import TraversalHazard, TraversalSnapshot


@pytest.mark.parametrize("stage", range(8))
def test_route22_phase_reads_its_own_script(stage):
    from test_observation import RecordingMemory

    from pokemon_red_completion.observation import PokemonRedStateReader

    memory = RecordingMemory({0xD35E: 33, 0xD60A: stage, 0xDA39: 255})
    assert PokemonRedStateReader(memory).read_route22_script() == stage
    assert memory.reads == [0xD35E, 0xD60A]


@pytest.mark.parametrize("map_id,stage", [(34, 0), (33, 8), (33, 255)])
def test_wrong_map_or_phase_refuses(map_id, stage):
    from test_observation import RecordingMemory

    from pokemon_red_completion.observation import PokemonRedStateReader, SemanticStateError

    memory = RecordingMemory({0xD35E: map_id, 0xD60A: stage})
    with pytest.raises(SemanticStateError):
        PokemonRedStateReader(memory).read_route22_script()


def cartridge(bank=3, shift=0, triggers=(2, 8, 3, 8), starters=(7, 9, 11)):
    rom = bytearray(0x30000)

    def word(x):
        return (x + shift).to_bytes(2, "little")

    def put(x, data):
        at = (bank - 1) * 0x4000 + x + shift
        rom[at : at + len(data)] = data

    rom[script.MAP_HEADER_BANKS + 33] = bank
    rom[script.MAP_HEADER_POINTERS + 66 : script.MAP_HEADER_POINTERS + 68] = word(0x4100)
    put(0x4107, word(0x4200))
    put(0x4200, bytes.fromhex("cd 3c 3c 21") + word(0x4300) + bytes.fromhex("fa 0a d6 c3 97 3d"))
    put(
        0x4300,
        b"".join(word(x) for x in (0x4400, 0x4500, 0x4600, 0x4700, 0x4800, 0x4900, 0x4A00, 0x4B00)),
    )
    put(
        0x4400,
        bytes.fromhex("fa eb d7 cb 7f c8 21")
        + word(0x4C00)
        + bytes.fromhex(
            "cd bf 34 d0 fa 3d cd ea 0d cf af e0 b4 3e f0 ea 6b cd "
            "3e 02 ea 28 d5 fa eb d7 cb 47 20 0b cb 4f c2"
        )
        + word(0x4700)
        + b"\xc9",
    )
    put(0x4C00, bytes((*triggers, 255)))
    put(
        0x4800,
        bytes.fromhex("fa 30 d7 cb 47 c0 3e 02 e0 8c")
        + bytes(28)
        + bytes.fromhex("af ea 6b cd 3e 02 e0 8c cd 20 29 21 2d d7 cb f6 cb fe 21")
        + word(0x4D00)
        + b"\x11"
        + word(0x4D10)
        + bytes.fromhex("cd 54 33 3e f2 ea 59 d0 21")
        + word(0x4E00)
        + b"\xcd"
        + word(0x4F00)
        + bytes.fromhex("3e 05 ea 0a d6 c9"),
    )
    put(0x4E00, bytes((starters[0], 10, starters[1], 11, starters[2], 12)))
    put(0x4F00, bytes.fromhex("fa 15 d7 47 2a b8 28 03 23 18 f9 7e ea 5d d0 c9"))
    put(
        0x4900,
        bytes.fromhex("fa 57 d0 fe ff ca")
        + bytes(34)
        + bytes.fromhex("3e f0 ea 6b cd 21 eb d7 cb f6"),
    )
    put(
        0x4A00,
        bytes.fromhex(
            "fa 30 d7 cb 47 c0 af ea 6b cd 3e 23 ea 4d cc "
            "3e 11 cd 6d 3e cd 07 23 21 eb d7 cb 8e cb be 3e 07 ea 0a d6 c9"
        ),
    )
    return bytes(rom)


@pytest.mark.parametrize("bank,shift,triggers", [(3, 0, (2, 8, 3, 8)), (7, 256, (9, 5, 10, 5))])
@pytest.mark.parametrize("starter,number", [(7, 10), (9, 11), (11, 12)])
def test_relocated_operands_and_all_starter_branches(bank, shift, triggers, starter, number):
    b = script._decode(cartridge(bank, shift, triggers), starter)
    assert b.identity == (242, 42, number) and b.defeated_event == 1318
    assert b.triggers == (triggers[:2], triggers[2:])


@pytest.mark.parametrize(
    "at",
    [
        0x4207,
        0x4403,
        0x4409,
        0x4804,
        0x482A,
        0x4843,
        0x484D,
        0x4930,
        0x4931,
        0x4A1B,
        0x4C04,
        0x4F0B,
    ],
)
def test_unsupported_script_fails_closed(at):
    rom = bytearray(cartridge())
    rom[0x8000 + at] = 0
    with pytest.raises(CartridgeReadError):
        script._decode(bytes(rom), 7)


@pytest.mark.parametrize("starter", [True, 0, 190, 8])
def test_unknown_selector_rejected(starter):
    with pytest.raises(CartridgeReadError):
        script._decode(cartridge(), starter)


def test_public_decoder_does_not_admit_synthetic_cartridge():
    with pytest.raises(Exception, match="(?i)(rom|checksum|size|sha)"):
        script.route22_script_binding(cartridge(), 7)


def available():
    flags = bytearray(320)
    flags[0xA4] = 0x82
    return RawGameState(
        game_started=True,
        party_count=1,
        map_id=33,
        player_y=3,
        player_x=9,
        battle_state=0,
        badge_bits=255,
        event_flags=bytes(flags),
    )


@pytest.mark.parametrize("bit", [0, 1, 6, 7])
def test_consumed_ambiguous_or_missing_events_refuse(bit):
    raw = available()
    flags = bytearray(raw.event_flags)
    flags[0xA4] ^= 1 << bit
    with pytest.raises(ValueError):
        script._decode(cartridge(), 7).require_available(replace(raw, event_flags=bytes(flags)))


def fixture():
    b = script._decode(cartridge(), 7)
    edge = LocalEdge((3, 8), "left", required_mode="land")
    start = TraversalSnapshot(
        33,
        (3, 9),
        ready=True,
        mode="land",
        hazards=tuple(TraversalHazard(at, "scripted_rival") for at in b.triggers),
    )

    class World:
        local_graphs = {33: LocalGraph({(3, 9): (edge,)})}

        def plan_feasible_to_map(self, observed, goal, *, goal_at):
            assert observed.hazards == start.hazards
            return NS(steps=(), segments=())

    return b, edge, start, World()


def test_prefix_planning_keeps_every_trigger_blocked():
    b, edge, start, world = fixture()
    assert entry.plan_scripted_approaches(world, start, b.triggers) == (
        entry.ScriptedApproach((3, 9), edge, 0),
    )
    with pytest.raises(entry.ScriptedRivalError):
        entry.plan_scripted_approaches(world, replace(start, hazards=()), b.triggers)


@pytest.mark.parametrize(
    "fault", ["occupied", "other_hazard", "forced", "mode", "unready", "crossmap"]
)
def test_unsafe_prefix_refuses(fault):
    b, edge, start, world = fixture()
    if fault == "occupied":
        start = replace(start, occupied=frozenset({edge.target}))
    if fault == "other_hazard":
        start = replace(
            start, hazards=(*start.hazards, TraversalHazard(edge.target, "trainer_sight"))
        )
    if fault == "forced":
        world.local_graphs = {33: LocalGraph({(3, 9): (replace(edge, kind="forced_motion"),)})}
    if fault == "mode":
        start = replace(start, mode="surf")
    if fault == "unready":
        start = replace(start, ready=False)
    if fault == "crossmap":
        world.plan_feasible_to_map = lambda *a, **k: NS(steps=(), segments=(1,))
    assert not entry.plan_scripted_approaches(world, start, b.triggers)


@pytest.mark.parametrize(
    "fault",
    [None, "identity", "pending", "map", "money", "phase", "dialogue", "budget", "action_failure"],
)
def test_transition_never_selects_combat_or_retriggers(fault):
    b, edge, _, _ = fixture()
    before = available()
    calls = []
    state = NS(raw=replace(before, player_x=8), phase=4)
    reader = NS(
        read=lambda: state.raw,
        read_route22_script=lambda: state.phase,
        read_active_trainer_identity=lambda: (242, 42, 9) if fault == "identity" else b.identity,
        read_pending_trainer_battle_identity=lambda: (242, 9) if fault == "pending" else None,
        read_bottom_dialogue_box_visible=lambda: True,
    )
    if fault == "map":
        state.raw = replace(state.raw, map_id=34)
    if fault == "money":
        state.raw = replace(state.raw, player_money=999)
    if fault == "phase":
        state.phase = 1
    if fault == "dialogue":
        state.phase = 0

    def execute(action):
        calls.append(action)
        if fault == "action_failure":
            raise RuntimeError("retained hardware failure")
        state.raw = replace(state.raw, battle_state=2)
        state.phase = 5

    kwargs = dict(
        binding=b,
        before=before,
        approach=entry.ScriptedApproach((3, 9), edge, 0),
        maximum_actions=0 if fault == "budget" else 2,
    )
    if fault:
        with pytest.raises(RuntimeError):
            entry.await_scripted_rival(reader, NS(execute=execute), **kwargs)
    else:
        assert (
            entry.await_scripted_rival(reader, NS(execute=execute), **kwargs)["combat_choices"] == 0
        )
    assert all(a.kind == MacroActionKind.INTERACT for a in calls) and len(calls) <= 1


def test_composed_entry_installs_existing_wild_escape_before_trigger(monkeypatch):
    """Regression: native approach must not strand the player in wild battle."""
    b, edge, start, original = fixture()
    state = NS(raw=available(), phase=0, calls=[])

    @dataclass
    class Graph:
        edges: dict

    @dataclass
    class World:
        macro_graph: object
        local_graphs: dict

        def with_current_blocks(self, blocks):
            return self

        def plan_feasible_to_map(self, observed, goal, *, goal_at):
            return original.plan_feasible_to_map(observed, goal, goal_at=goal_at)

    world = World(Graph({33: ()}), original.local_graphs)
    monkeypatch.setattr(entry, "StrategicScenarioRouteWorld", NS(from_rom=lambda rom: world))
    monkeypatch.setattr(entry, "route22_script_binding", lambda rom, starter: b)
    monkeypatch.setattr(
        entry, "Gen1TrainerSightProjector", lambda *a, **k: NS(observe_hazards=lambda raw: ())
    )
    monkeypatch.setattr(entry, "Gen1TraversalObserver", lambda *a: NS(observe=lambda: start))
    reader = NS(
        read=lambda: state.raw,
        read_route22_script=lambda: state.phase,
        read_rival_starter=lambda: 7,
        read_pending_trainer_battle_identity=lambda: None,
        read_active_trainer_identity=lambda: b.identity,
        read_input_readiness=lambda: NS(ready=True),
        read_bottom_dialogue_box_visible=lambda: state.phase == 4,
        read_current_map_blocks=lambda: None,
    )

    def execute(action):
        state.calls.append(action.kind)
        if action.kind == MacroActionKind.MOVE:
            state.raw = replace(state.raw, player_x=8)
            state.phase = 4
        elif action.kind == MacroActionKind.INTERACT:
            state.raw = replace(state.raw, battle_state=2)
            state.phase = 5
        else:
            pytest.fail("unexpected input")

    actions = NS(execute=execute)

    def route(plan, port, observer, *, interruption_handler, **kwargs):
        assert port is actions and interruption_handler.executor is actions
        assert interruption_handler.reader is reader
        assert interruption_handler.maximum_flees == 4
        assert not state.calls, "wild escape must be wired before any trigger input"

    monkeypatch.setattr(entry, "execute_route", route)
    result = entry.engage_scripted_rival(None, reader, actions, rom=b"fixture", binding=b)
    assert result["combat_choices"] == 0 and result["transition_actions"] == 2
    assert state.calls == [MacroActionKind.MOVE, MacroActionKind.INTERACT]
