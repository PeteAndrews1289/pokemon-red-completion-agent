"""ROM-free Fly dependency options; no selection hidden in execution."""
from dataclasses import dataclass, replace
from types import SimpleNamespace as N

import pytest
from test_red_goal_skills import _raw, _Reader

import pokemon_red_completion.red_player_fly as module
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.observation import EventFlag
from pokemon_red_completion.route_plan import RoutePlanningError


def fixture(monkeypatch, *, prefix=False, fault=None):
    raw = replace(_raw(), map_id=171, bag_items=((1, 1),), badge_bits=255,
                  event_flags=bytes(400))
    reader = _Reader(raw=raw, ready=True)
    dex = N(owned_species=frozenset({9}), seen_species=frozenset({9}))
    reader.read_pokedex_state = lambda: dex
    reader.read_all_box_states = lambda: ()
    reader.read_pc_items = lambda: ()
    em = N(state=b"source", frame_count=0, pressed_buttons=())
    em.save_state_bytes = lambda: em.state
    rt = N(reader=reader, emulator=em)
    actions = N(actions_executed=0)
    seen = []

    class World:
        def with_current_observation(self, _reader):
            return self

        def plan_feasible_to_map(self, start, target, *, goal_at=None):
            if fault == "unreachable" or (prefix and start.map_id == 171 and target == 188):
                raise RoutePlanningError("not reachable")
            return N(cost=10, terminal_map=target, terminal_at=goal_at)

    @dataclass
    class Route:
        rom: bytes = b"fixture"
        route_world: object = None
        allow_surf: bool = True
        destination_map: int = 188
        destination_at: tuple = (4, 2)

        def __call__(self, _actions, received, _em):
            assert received is reader
            seen.append((self.destination_map, self.destination_at))
            actions.actions_executed += 1
            em.frame_count += 120
            if fault != "stuck":
                reader.raw = replace(reader.raw, map_id=self.destination_map,
                                     player_y=self.destination_at[0],
                                     player_x=self.destination_at[1])
            em.state += b"route"

    monkeypatch.setattr(module, "RedPracticeCartridge",
                        lambda _: N(species=lambda _: N(tmhm_moves=(19,))))
    monkeypatch.setattr(module, "_noncombat_fly_world", lambda world, raw: world)
    monkeypatch.setattr(module, "map_object_events",
                        lambda *_: (N(object_index=1, at=(3, 2), y=3, x=2,
                                      movement=255, text_id=1),))
    monkeypatch.setattr(module, "Gen1TraversalObserver",
                        lambda *_args, **_kw: N(observe=lambda: N(map_id=reader.raw.map_id)))
    monkeypatch.setattr(module, "Gen1TrainerSightProjector", lambda *_args, **_kw: None)
    monkeypatch.setattr(module, "settle_story_interaction", lambda *_: None)
    monkeypatch.setattr(module, "approach_npc", lambda *_args, **_kw: None)

    def reward(*_, item, events):
        flags = bytearray(reader.raw.event_flags)
        flags[events[0]//8] |= 1 << (events[0]%8)
        reader.raw = replace(reader.raw, bag_items=reader.raw.bag_items+((item, 1),),
                             event_flags=bytes(flags))
        em.state += b"reward"
        if fault == "cash":
            reader.raw = replace(reader.raw, player_money=1)
        if fault == "stock":
            reader.raw = replace(reader.raw, bag_items=((item, 1),))
        if fault == "box":
            reader.read_all_box_states = lambda: ("lost-specimen",)
        if fault == "flag":
            reader.raw = replace(reader.raw, event_flags=bytes(400))
    monkeypatch.setattr(module, "collect_hm_reward", reward)
    return rt, actions, Route(route_world=World()), seen


def test_read_only_reward_with_actual_dependency(monkeypatch):
    rt, actions, route, seen = fixture(monkeypatch)
    row = module.fly_reward_option(rt, actions, route=route)
    assert row is not None and not seen
    assert row.candidate.features.dependency_unlock_gain == 1
    assert row.candidate.features.completion_gain == 0
    assert actions.actions_executed == rt.emulator.frame_count == 0
    report = row.binding.execute()
    assert row.binding.verify(report).status.value == "succeeded"
    assert report.evidence["complete_delivery"] and report.evidence["quantity"] == 1
    assert dict(rt.reader.raw.bag_items) == {1: 1, 197: 1}
    with pytest.raises(ValueError, match="stale or consumed"):
        row.binding.execute()
    rt.emulator.state = b"other"
    assert row.binding.verify(report).status.value == "failed"


def test_prefix_only_route_cannot_advertise_complete_fly(monkeypatch):
    rt, actions, route, seen = fixture(monkeypatch, prefix=True)
    assert module.fly_reward_option(rt, actions, route=route) is None
    assert seen == [] and actions.actions_executed == rt.emulator.frame_count == 0
    assert not dict(rt.reader.raw.bag_items).get(197)


@pytest.mark.parametrize("defeated", [False, True])
def test_future_trainer_lane_stays_in_graph_and_cut_rebuild_blockers(monkeypatch, defeated):
    """A noncombat quote cannot advertise a future fight as a legal walk."""
    from pokemon_red_completion.gen1_trainer_sight import TrainerFacing, TrainerSightZone

    @dataclass
    class World:
        rom: bytes
        terrain: dict
        local_graphs: dict
        object_blockers: dict

    lane, occupied = (2, 1), (4, 4)
    graph = LocalGraph({(1, 1): (LocalEdge(lane, "down"),), lane: (), occupied: ()})
    world = World(b"fixture", {82: None, 20: None}, {82: graph, 20: graph},
                  {82: frozenset({occupied}), 20: frozenset()})
    zones = (TrainerSightZone(82, 1, 1, 1, (3, 1), TrainerFacing.UP, 1, 9,
                             defeated, False),
             TrainerSightZone(20, 1, 1, 1, (3, 1), TrainerFacing.UP, 1, 10,
                             False, True))
    monkeypatch.setattr(module, "_fly_trainer_tables", lambda rom, ids: ((), ()))
    seen = []
    monkeypatch.setattr(module, "static_trainer_sight_zones",
                        lambda headers, events, flags: seen.append(flags) or zones)
    result = module._noncombat_fly_world(world, N(map_id=20, event_flags=b"native-flags"))
    assert seen == [b"native-flags"]
    assert result.local_graphs[20] is graph  # Current sight comes from the live observer.
    assert world.object_blockers[82] == frozenset({occupied})
    assert lane in world.local_graphs[82].edges  # Never mutate the retained world.
    assert occupied in result.object_blockers[82]
    assert (lane in result.local_graphs[82].edges) is defeated
    assert (lane in result.object_blockers[82]) is (not defeated)


def test_future_trainers_use_full_event_offsets_without_caching_event_state(monkeypatch):
    module._fly_trainer_tables.cache_clear()
    calls = []
    monkeypatch.setattr(module, "trainer_headers", lambda rom, ids, **kw:
                        calls.append((rom, ids, kw)) or ())
    monkeypatch.setattr(module, "map_object_events", lambda rom, ids: ())
    assert module._fly_trainer_tables(b"tables", (20, 82)) == ((), ())
    assert module._fly_trainer_tables(b"tables", (20, 82)) == ((), ())
    assert calls == [(b"tables", (20, 82), {"full_event_offsets": True})]
    module._fly_trainer_tables.cache_clear()


@pytest.mark.parametrize("badges", [4, 47, 63, 255])
def test_dependency_menu_offers_legal_fly_before_eight_badges(monkeypatch, badges):
    import pokemon_red_completion.red_player_owned_machines as machines

    rt, actions, route, seen = fixture(monkeypatch)
    rt.reader.raw = replace(rt.reader.raw, badge_bits=badges)
    called = []
    monkeypatch.setattr(machines, "owned_machine_options", lambda *args, **kwargs:
                        called.append(kwargs) or ())
    rows = module.fly_dependency_options(rt, actions, route=route)
    assert len(rows) == 1
    assert called == [dict(rom=route.rom, include_fly_lesson=True,
                           include_attack_lessons=False)]
    assert not seen and actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize("badges", [0, 1, 2, 43])
def test_dependency_menu_cannot_bypass_thunder_badge(monkeypatch, badges):
    import pokemon_red_completion.red_player_owned_machines as machines

    rt, actions, route, seen = fixture(monkeypatch)
    rt.reader.raw = replace(rt.reader.raw, badge_bits=badges)
    monkeypatch.setattr(machines, "owned_machine_options", lambda *args, **kwargs: ())
    assert module.fly_dependency_options(rt, actions, route=route) == ()
    assert not seen and actions.actions_executed == rt.emulator.frame_count == 0


def test_dependency_menu_keeps_all_existing_lesson_choices(monkeypatch):
    import pokemon_red_completion.red_player_owned_machines as machines

    rt, actions, route, seen = fixture(monkeypatch)
    rt.reader.raw = replace(rt.reader.raw, badge_bits=47, bag_items=((197, 1),))
    lessons = (N(binding="first"), N(binding="second"))
    monkeypatch.setattr(machines, "owned_machine_options", lambda *args, **kwargs: lessons)
    assert module.fly_dependency_options(rt, actions, route=route) == lessons
    assert not seen and actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize("fault", ["cash", "stock", "box", "flag", "stuck"])
def test_false_or_stuck_reward_is_not_retried(monkeypatch, fault):
    rt, actions, route, seen = fixture(monkeypatch, fault=fault)
    row = module.fly_reward_option(rt, actions, route=route)
    with pytest.raises(RuntimeError):
        row.binding.execute()
    with pytest.raises(ValueError, match="stale or consumed"):
        row.binding.execute()
    assert len(seen) <= 2


@pytest.mark.parametrize("reason", ["owned", "claimed", "badge", "unready", "held", "unreachable",
                                   "incompatible", "full", "surf"])
def test_unavailable_dependency_remains_absent(monkeypatch, reason):
    rt, actions, route, seen = fixture(monkeypatch, fault=reason)
    if reason == "owned":
        rt.reader.raw = replace(rt.reader.raw, bag_items=((197, 1),))
    elif reason == "claimed":
        flags = bytearray(rt.reader.raw.event_flags)
        event = int(EventFlag.GOT_HM02)
        flags[event//8] |= 1 << (event%8)
        rt.reader.raw = replace(rt.reader.raw, event_flags=bytes(flags))
    elif reason == "badge":
        rt.reader.raw = replace(rt.reader.raw, badge_bits=0)
    elif reason == "unready":
        rt.reader.ready = False
    elif reason == "held":
        rt.emulator.pressed_buttons = ("a",)
    elif reason == "incompatible":
        monkeypatch.setattr(module, "RedPracticeCartridge",
                            lambda _: N(species=lambda _: N(tmhm_moves=())))
    elif reason == "full":
        rt.reader.raw = replace(rt.reader.raw, bag_items=tuple((i, 1) for i in range(1, 21)))
    elif reason == "surf":
        route = replace(route, allow_surf=False)
    assert module.fly_reward_option(rt, actions, route=route) is None
    assert not seen and actions.actions_executed == 0
