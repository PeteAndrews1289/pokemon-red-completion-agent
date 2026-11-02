from dataclasses import dataclass, field
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_tower as s
from pokemon_red_completion.local_router import LocalEdge, LocalGraph, without_coordinates


def test_ghost_trigger_guard_survives_observed_terrain_rebuild(monkeypatch):
    graph = LocalGraph({(16, 11): (LocalEdge((16, 10), "left"),), (16, 10): ()})
    checked = []

    @dataclass
    class World:
        local_graphs: dict
        object_blockers: dict

        def plan_feasible_to_map(self, origin, map_id, *, goal_at):
            assert goal_at == (16, 11)
            assert (16, 10) not in self.local_graphs[147].edges
            # Same blocker source used when the route rebuilds live terrain.
            rebuilt = without_coordinates(graph, self.object_blockers[147])
            assert (16, 10) not in rebuilt.edges and not rebuilt.edges[(16, 11)]
            checked.append(True)

    @dataclass
    class Route:
        route_world: World
        rom: bytes = b"rom"
        destination_map: int = 147
        destination_at: tuple = (16, 11)

    world = World({147: graph}, {147: frozenset({(3, 3)})})
    raw = N(
        map_id=147,
        player_y=14,
        player_x=11,
        battle_state=0,
        event_flags=flags(),
        bag_items=((72, 1),),
        player_money=100,
    )
    rt = N(reader=N(read=lambda: raw), emulator=N(save_state_bytes=lambda: b"state"))
    monkeypatch.setattr(s, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "_origin", lambda *a: None)
    actor = N(model_sha256=s.FROZEN_K_SHA256, qualification_sha256=s.K_QUALIFICATION_SHA256)
    assert s.marowak_binding(rt, None, route=Route(world), battler=actor) is not None
    assert checked == [True] and world.object_blockers[147] == frozenset({(3, 3)})
    assert (16, 10) in graph.edges


def flags(*events):
    result = bytearray(320)
    for event in events:
        result[event // 8] |= 1 << (event % 8)
    return bytes(result)


@pytest.mark.parametrize(
    "room,events,bag,phase",
    [
        (148, (271, 273, 274, 275), (), "rescue"),
        (148, (271, 273, 274), (), None),
        (148, (271, 273, 274, 275, 279), (), None),
        (149, (279, 1231), (), "flute"),
        (149, (279,), (), None),
        (149, (279, 1231, 296), (), None),
        (149, (279, 1231), ((73, 1),), None),
        (149, (279, 1231), tuple((i, 1) for i in range(20)), None),
        (141, (279, 1231), (), None),
    ],
)
def test_fuji_requires_each_native_prerequisite(room, events, bag, phase):
    raw = N(map_id=room, event_flags=flags(*events), bag_items=bag, battle_state=0)
    result = s.fuji_phase(raw)
    assert (None if result is None else result[0]) == phase
    raw.battle_state = 2
    assert s.fuji_phase(raw) is None


@pytest.mark.parametrize("fault", [None, "event", "map", "scope", "short"])
def test_marowak_pending_exact_state(fault):
    raw = N(
        map_id=146 if fault == "map" else 147,
        event_flags=bytes(1) if fault == "short" else flags(*((271,) if fault == "event" else ())),
        bag_items=() if fault == "scope" else ((72, 1),),
    )
    assert s.marowak_pending(raw) is (fault is None)


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "actor",
        "enemy",
        "level",
        "event",
        "cash",
        "loss",
        "ordinary_before_ghost",
    ],
)
def test_ghost_uses_existing_actor_and_verifies_native_outcome(monkeypatch, fault):
    raw = N(
        map_id=147,
        player_y=16,
        player_x=10,
        battle_state=1,
        event_flags=flags(),
        bag_items=((72, 1),),
        enemy_species_id={"enemy": 144, "ordinary_before_ghost": 25}.get(fault, 145),
        enemy_level={"level": 29, "ordinary_before_ghost": 22}.get(fault, 30),
        party_species_ids=(9,),
        player_money=100,
        party_hp=(20,),
    )
    rt = N(
        reader=N(read=lambda: N(**raw.__dict__)),
        emulator=N(
            frame_count=0, save_state_bytes=lambda: bytes((raw.battle_state, raw.player_money))
        ),
    )
    ordinary = []

    def act(action):
        if ordinary and raw.battle_state == 0:
            raw.battle_state, raw.enemy_species_id, raw.enemy_level = 1, 145, 30

    actions = N(actions_executed=0, execute=act)
    monkeypatch.setattr(s, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(s, "_field_ready", lambda _: raw.battle_state == 0)
    monkeypatch.setattr(s, "advance_battle_to_policy_boundary", lambda *a, **k: None)
    monkeypatch.setattr(s, "wild_tables", lambda _: {147: [(22, 25)]})

    def flee(*args, **kwargs):
        assert kwargs["maximum_flees"] == 2 and kwargs["allow_party_faints"] is True

        def handle(snapshot):
            assert (raw.enemy_species_id, raw.enemy_level) == (25, 22)
            assert snapshot.at == (16, 10)
            ordinary.append(snapshot)
            raw.battle_state = 0

        return N(handle=handle)

    monkeypatch.setattr(s, "Gen1WildFleeHandler", flee)
    monkeypatch.setattr(
        s.RedTrainerEvolutionGuard, "from_rom", lambda *a: N(matches=lambda *a: True)
    )
    calls = []

    def run(reader, executor, **kw):
        calls.append(kw)
        kw["decision_guard"](reader.read())
        if fault == "loss":
            raw.party_hp = (0,)
            return N(stop_reason="party_defeated", battle_won=False)
        raw.battle_state = 0
        raw.event_flags = flags() if fault == "event" else flags(271)
        if fault == "cash":
            raw.player_money = 99
        return N(stop_reason="battle_won", battle_won=True)

    def blackout(*a):
        assert raw.party_hp == (0,)
        raw.battle_state = 0
        raw.map_id = 141
        raw.player_money = 50
        raw.party_hp = (20,)

    monkeypatch.setattr(s, "settle_red_blackout", blackout)
    actor = N(
        model_sha256="bad" if fault == "actor" else s.FROZEN_K_SHA256,
        qualification_sha256=s.K_QUALIFICATION_SHA256,
        run_wild_training=run,
    )

    @dataclass
    class World:
        local_graphs: dict
        object_blockers: dict = field(default_factory=lambda: {147: frozenset()})

    @dataclass
    class Route:
        route_world: World
        rom: bytes = b"rom"
        destination_map: int = 147
        destination_at: tuple = (16, 11)

    if fault == "actor":
        with pytest.raises(ValueError):
            s.marowak_binding(rt, actions, route=Route(World({147: LocalGraph({})})), battler=actor)
        assert not calls
        return
    binding = s.marowak_binding(
        rt, actions, route=Route(World({147: LocalGraph({})})), battler=actor
    )
    assert not calls
    if fault not in (None, "loss", "ordinary_before_ghost"):
        with pytest.raises(ValueError):
            binding.execute()
    else:
        report = binding.execute()
        assert report.evidence["learned_combat"] and not report.evidence["fit"]
        assert binding.verify(report).status.value == ("failed" if fault == "loss" else "succeeded")
        with pytest.raises(ValueError):
            binding.execute()
    assert len(calls) == (0 if fault in ("enemy", "level") else 1)
    assert len(ordinary) == (1 if fault == "ordinary_before_ghost" else 0)


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "no_exit",
        "ready_exit",
        "enemy",
        "level",
        "map",
        "tile",
        "event",
        "scope",
        "cash",
        "pp",
        "stats",
        "enemy_hp",
        "result",
        "blackout",
        "heal",
    ],
)
def test_incidental_escape_hands_only_the_exact_new_ghost_to_its_owner(fault):
    from pokemon_red_completion.actions import MacroAction, MacroActionKind

    initial = N(
        map_id=147,
        player_y=16,
        player_x=10,
        battle_state=1,
        battle_result=0,
        enemy_species_id=25,
        enemy_level=21,
        enemy_hp=46,
        enemy_max_hp=46,
        event_flags=flags(),
        bag_items=((72, 1),),
        player_money=100,
        badge_bits=15,
        party_count=2,
        party_species_ids=(9, 1),
        party_levels=(37, 18),
        party_hp=(80, 20),
        party_max_hp=(125, 57),
        party_moves=((55, 0, 0, 0),) * 2,
        party_pp=((25, 0, 0, 0),) * 2,
        party_status=(0, 0),
        party_stats=((80, 80, 80, 80), (20, 20, 20, 20)),
    )
    escaped = N(**{**initial.__dict__, "battle_state": 0, "battle_result": 2})
    ghost = N(
        **{
            **initial.__dict__,
            "enemy_species_id": 145,
            "enemy_level": 30,
            "enemy_hp": 77,
            "enemy_max_hp": 77,
        }
    )
    changes = {
        "enemy": {"enemy_species_id": 144},
        "level": {"enemy_level": 29},
        "map": {"map_id": 146},
        "tile": {"player_x": 11},
        "event": {"event_flags": flags(271)},
        "scope": {"bag_items": ()},
        "cash": {"player_money": 101},
        "pp": {"party_pp": ((24, 0, 0, 0),) * 2},
        "stats": {"party_stats": ((81, 80, 80, 80), (20, 20, 20, 20))},
        "enemy_hp": {"enemy_hp": 0},
        "result": {"battle_result": 2},
        "blackout": {"party_hp": (0, 0)},
        "heal": {"party_hp": (81, 20)},
    }
    ghost.__dict__.update(changes.get(fault, {}))
    live, calls = [initial], []

    def execute(action):
        calls.append(action)
        live[0] = ghost if fault == "no_exit" or len(calls) == 2 else escaped

    reader = N(
        read=lambda: N(**live[0].__dict__),
        read_input_readiness=lambda: N(ready=fault == "ready_exit"),
    )
    wrapper = s._MarowakEscapeExecutor(N(execute=execute), reader)
    error = s._MarowakEscapeHandoff if fault is None else ValueError
    with pytest.raises(error):
        wrapper.execute(MacroAction(MacroActionKind.WAIT, repeat=24))
        wrapper.execute(MacroAction(MacroActionKind.WAIT, repeat=24))
    assert len(calls) == (1 if fault == "no_exit" else 2)
    assert all(action.kind is MacroActionKind.WAIT for action in calls)
    assert not any(action.kind is MacroActionKind.CONFIRM for action in calls)
    if fault is None:
        assert wrapper.escaped.battle_state == 0 and wrapper.escaped.battle_result == 2
        assert live[0].battle_state == 1 and live[0].enemy_hp > 0


def test_incidental_escape_cannot_begin_in_the_one_off_ghost():
    raw = N(
        map_id=147,
        player_y=16,
        player_x=10,
        battle_state=1,
        enemy_species_id=145,
        enemy_level=30,
        event_flags=flags(),
        bag_items=((72, 1),),
    )
    with pytest.raises(ValueError, match="ordinary Tower escape"):
        s._MarowakEscapeExecutor(N(), N(read=lambda: raw))


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "two_encounters",
        "budget",
        "wrong_tile",
        "wrong_map",
        "wrong_enemy",
        "ghost_at_approach",
        "scope_lost",
        "event_set",
        "escape_drift",
        "escape_unready",
    ],
)
def test_ordinary_wild_can_interrupt_the_final_step_before_the_ghost(monkeypatch, fault):
    from pokemon_red_completion.actions import MacroActionKind

    raw = N(
        map_id=147,
        player_y=7,
        player_x=6,
        battle_state=0,
        event_flags=flags(),
        bag_items=((72, 1),),
        player_money=100,
        party_species_ids=(9,),
        party_hp=(80,),
        enemy_species_id=25,
        enemy_level=21,
    )
    moves, escapes, battles = [], [], []
    rt = N(
        reader=N(read=lambda: N(**raw.__dict__)),
        emulator=N(
            frame_count=0,
            save_state_bytes=lambda: bytes((raw.player_y, raw.player_x, raw.battle_state)),
        ),
    )
    monkeypatch.setattr(s, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(s, "_origin", lambda *a: None)
    monkeypatch.setattr(
        s,
        "_field_ready",
        lambda _: raw.battle_state == 0 and fault != "escape_unready" or not moves,
    )
    monkeypatch.setattr(s, "advance_battle_to_policy_boundary", lambda *a, **k: None)
    monkeypatch.setattr(s, "wild_tables", lambda _: {147: [(21, 25)]})
    monkeypatch.setattr(
        s.RedTrainerEvolutionGuard, "from_rom", lambda *a: N(matches=lambda *a: True)
    )

    @dataclass
    class World:
        local_graphs: dict = field(default_factory=lambda: {147: LocalGraph({})})
        object_blockers: dict = field(default_factory=lambda: {147: frozenset()})

        def plan_feasible_to_map(self, *a, **k):
            return None

    @dataclass
    class Route:
        route_world: World
        destination_map: int = 147
        destination_at: tuple = (16, 11)
        rom: bytes = b"rom"

        def __call__(self, *a):
            raw.player_y, raw.player_x = self.destination_at

    count = 3 if fault == "budget" else 2 if fault == "two_encounters" else 1

    def act(action):
        if action.kind is MacroActionKind.MOVE:
            assert action.value == "left"
            moves.append(action)
            raw.battle_state = 1
            if len(moves) > count:
                raw.player_x, raw.enemy_species_id, raw.enemy_level = 10, 145, 30
            if fault == "wrong_tile":
                raw.player_x = 12
            if fault == "wrong_map":
                raw.map_id = 146
            if fault == "wrong_enemy":
                raw.enemy_species_id = 144
            if fault == "ghost_at_approach":
                raw.enemy_species_id, raw.enemy_level = 145, 30
            if fault == "scope_lost":
                raw.bag_items = ()
            if fault == "event_set":
                raw.event_flags = flags(271)

    actions = N(actions_executed=0, execute=act)

    def handler(executor, reader, **kwargs):
        assert kwargs["maximum_flees"] == 2 and kwargs["allow_party_faints"]

        def handle(snapshot):
            if len(escapes) >= kwargs["maximum_flees"]:
                raise RuntimeError("two-flee budget")
            assert snapshot.at == (16, 11)
            assert (raw.enemy_species_id, raw.enemy_level) == (25, 21)
            escapes.append(snapshot)
            raw.battle_state = 0
            if fault == "escape_drift":
                raw.player_x = 12

        return N(executor=executor, handle=handle)

    monkeypatch.setattr(s, "Gen1WildFleeHandler", handler)

    def run(reader, executor, **kwargs):
        assert (raw.player_y, raw.player_x, raw.enemy_species_id, raw.enemy_level) == (
            16,
            10,
            145,
            30,
        )
        kwargs["decision_guard"](reader.read())
        battles.append(True)
        raw.battle_state, raw.event_flags = 0, flags(271)
        return N(stop_reason="battle_won", battle_won=True)

    actor = N(
        model_sha256=s.FROZEN_K_SHA256,
        qualification_sha256=s.K_QUALIFICATION_SHA256,
        run_wild_training=run,
    )
    binding = s.marowak_binding(rt, actions, route=Route(World()), battler=actor)
    assert binding is not None and not moves and not escapes and not battles
    if fault in (None, "two_encounters"):
        report = binding.execute()
        assert binding.verify(report).status.value == "succeeded"
        assert len(escapes) == count and len(moves) == count + 1 and battles == [True]
    else:
        with pytest.raises((ValueError, RuntimeError)):
            binding.execute()
        assert not battles


@pytest.mark.parametrize("phase", ["rescue", "flute"])
@pytest.mark.parametrize("fault", [None, "missing", "cash", "hp", "bag", "object"])
def test_fuji_interaction_readonly_admission_and_exact_outcome(monkeypatch, phase, fault):
    index = 4 if phase == "rescue" else 5
    raw = N(
        map_id=148 if phase == "rescue" else 149,
        battle_state=0,
        event_flags=flags(*((271, 273, 274, 275) if phase == "rescue" else (279, 1231))),
        bag_items=((72, 1),),
        party_hp=(20,),
        party_pp=((10,),),
        party_status=(0,),
        party_species_ids=(9,),
        player_money=100,
        badge_bits=15,
    )
    rt = N(
        reader=N(
            read=lambda: N(**raw.__dict__),
            read_current_map_objects=lambda: (
                N(sprite_index=index, picture_id=23 if fault == "object" else 22, at=(1, 3)),
            ),
        ),
        emulator=N(
            frame_count=0,
            save_state_bytes=lambda: bytes((raw.map_id, len(raw.bag_items), raw.player_money)),
        ),
    )
    actions = N(actions_executed=0)
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(
        s,
        "map_object_events",
        lambda *a: (N(object_index=index, sprite_id=22, at=(1, 3), y=1, x=3),),
    )
    monkeypatch.setattr(s, "_origin", lambda *a: None)
    monkeypatch.setattr(s, "face_pc_boundary", lambda *a: None)
    monkeypatch.setattr(s, "capture_player_lesson_snapshot", lambda *a: None)

    @dataclass
    class Route:
        rom: bytes = b"rom"
        destination_map: int = 148
        destination_at: tuple = (2, 3)

        @property
        def route_world(self):
            return N(plan_feasible_to_map=lambda *a, **k: N(cost=1, terminal_at=(2, 3)))

        def __call__(self, *a):
            pass

    def act(action):
        actions.actions_executed += 1
        if fault != "missing":
            raw.map_id = 149
            raw.event_flags = flags(
                271, 273, 274, 275, 279, 1231, *((296,) if phase == "flute" else ())
            )
            if phase == "flute":
                raw.bag_items = ((72, 1), (73, 1))
        if fault == "cash":
            raw.player_money = 99
        if fault == "hp":
            raw.party_hp = (19,)
        if fault == "bag":
            raw.bag_items = ((72, 1), (73, 1), (1, 1))

    actions.execute = act
    if fault == "object":
        with pytest.raises(ValueError):
            s.fuji_binding(rt, actions, route=Route())
        assert actions.actions_executed == 0
        return
    binding = s.fuji_binding(rt, actions, route=Route())
    assert actions.actions_executed == 0
    if fault:
        with pytest.raises(ValueError):
            binding.execute()
    else:
        report = binding.execute()
        assert binding.verify(report).status.value == "succeeded"
        assert report.evidence["objective_completed"] == (phase == "flute")
        assert not report.evidence["learned"]
        with pytest.raises(ValueError):
            binding.execute()
