from dataclasses import dataclass
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_hideout as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome


def flags(*events):
    result = bytearray(320)
    for event in events:
        result[event // 8] |= 1 << (event % 8)
    return bytes(result)


@pytest.mark.parametrize(
    "room,events,present,bag,phase",
    [
        (135, (), {11}, (), None),
        (135, (), set(), (), "poster"),
        (135, (441,), set(), (), None),
        (202, (1700,), {4}, (), "drop_key"),
        (202, (1700, 1702), {4, 9}, (), "lift_key"),
        (202, (1702,), {9}, ((74, 1),), None),
        (202, (1703,), {8}, (), "scope"),
        (202, (), {8}, (), None),
        (202, (1703,), {8}, ((72, 1),), None),
        (133, (), set(), (), None),
    ],
)
def test_phase_requires_native_prerequisites(room, events, present, bag, phase):
    raw = N(map_id=room, event_flags=flags(*events), bag_items=bag, battle_state=0)
    value = s.pending_hideout_interaction(raw, present)
    assert (None if value is None else value[0]) == phase
    raw.battle_state = 2
    assert s.pending_hideout_interaction(raw, present) is None


@pytest.mark.parametrize("fault", [None, "hp", "cash", "extra_event", "battle", "missing"])
def test_interaction_is_readonly_until_selected_and_checks_native_effects(monkeypatch, fault):
    raw = N(
        map_id=135,
        battle_state=0,
        event_flags=flags(),
        bag_items=(),
        party_hp=(20,),
        party_pp=((10, 10),),
        party_species_ids=(1,),
        party_status=(0,),
        player_money=100,
        badge_bits=15,
    )
    rt = N(
        reader=N(read=lambda: raw, read_current_map_objects=lambda: ()),
        emulator=N(
            frame_count=0, save_state_bytes=lambda: bytes((int(bool(raw.event_flags[55])),))
        ),
    )
    actions = N(actions_executed=0)
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(
        s,
        "capture_player_lesson_snapshot",
        lambda _: (N(raw=N(**raw.__dict__)), {"completed_objectives": ["reach_celadon"]}),
    )
    monkeypatch.setattr(s, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(s, "map_object_events", lambda *a: (N(object_index=11, at=(5, 9)),))
    monkeypatch.setattr(s, "Gen1TraversalObserver", lambda *a, **kw: N(observe=lambda: object()))
    monkeypatch.setattr(s, "Gen1TrainerSightProjector", lambda *a, **kw: None)
    monkeypatch.setattr(s, "face_pc_boundary", lambda *a: None)

    @dataclass
    class Route:
        rom: bytes = b"rom"
        destination_map: int = 135
        destination_at: tuple = (5, 9)

        @property
        def route_world(self):
            return N(plan_feasible_to_map=lambda *a, **k: N(cost=1, terminal_at=(5, 9)))

        def __call__(self, *a):
            pass

    def act(action):
        actions.actions_executed += 1
        if fault != "missing":
            raw.event_flags = flags(441, *((442,) if fault == "extra_event" else ()))
        if fault == "hp":
            raw.party_hp = (19,)
        if fault == "cash":
            raw.player_money = 99
        if fault == "battle":
            raw.battle_state = 2

    actions.execute = act
    binding = s.hideout_interaction_binding(rt, actions, route=Route())
    assert binding is not None and actions.actions_executed == 0
    if fault:
        with pytest.raises(ValueError):
            binding.execute()
    else:
        report = binding.execute()
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
        assert not report.evidence["learned"] and not report.evidence["objective_completed"]
        with pytest.raises(ValueError):
            binding.execute()


@pytest.mark.parametrize("floor", [199, 200, 202])
@pytest.mark.parametrize("fault", [None, "menu", "cash", "battle", "wrong_exit",
    "poison", "healthy_damage", "burn_damage", "heal", "new_status", "level", "moves"])
def test_keyed_elevator_requires_visible_menu_and_exact_preserved_terminal(
    monkeypatch, fault, floor
):
    from pokemon_red_completion import hideout

    raw = N(
        map_id=203,
        player_y=2,
        player_x=1,
        battle_state=0,
        bag_items=((74, 1),),
        player_money=100,
        party_species_ids=(1,),
        party_hp=(20,),
        party_levels=(20,),
        party_moves=((33,),),
        party_pp=((10,),),
        party_status=(8 if fault == "poison" else 16 if fault == "burn_damage" else 0,),
        badge_bits=15,
        event_flags=flags(1702),
    )
    current = N(**raw.__dict__)
    actions = N(actions_executed=0)
    rt = N(
        reader=N(
            read=lambda: N(**current.__dict__),
            read_screen_text_rows=lambda: ("B1F B2F B4F" if fault != "menu" else "no key",),
        ),
        emulator=N(frame_count=0, save_state_bytes=lambda: repr(current.__dict__).encode()),
    )
    monkeypatch.setattr(s, "_field_ready", lambda _: current.battle_state == 0)
    monkeypatch.setattr(s, "Gen1TraversalObserver", lambda *a, **k: N(observe=lambda: object()))
    monkeypatch.setattr(s, "Gen1TrainerSightProjector", lambda *a, **k: None)
    monkeypatch.setattr(s, "face_pc_boundary", lambda *a: None)
    monkeypatch.setattr(hideout, "_select_cursor", lambda a, e, i, t: None)

    @dataclass
    class Route:
        rom: bytes = b"rom"
        destination_map: int = 203
        destination_at: tuple = (2, 1)

        @property
        def route_world(self):
            return N(plan_feasible_to_map=lambda *a, **k: N(cost=0, terminal_at=(2, 1), steps=()))

        def __call__(self, *a):
            pass

    def act(action):
        actions.actions_executed += 1
        if action.kind is s.MacroActionKind.MOVE:
            if action.value == "right":
                current.player_x = 2
            elif action.value == "up":
                current.map_id, current.player_y, current.player_x = (
                    floor,
                    (15 if floor == 202 else 19),
                    25,
                )
                if fault == "wrong_exit":
                    current.player_x = 24
                if fault == "cash":
                    current.player_money -= 1
                if fault == "battle":
                    current.battle_state = 2
                if fault in {"poison", "healthy_damage", "burn_damage"}:
                    current.party_hp = (19,)
                if fault == "heal":
                    current.party_hp = (21,)
                if fault == "new_status":
                    current.party_status = (8,)
                if fault == "level":
                    current.party_levels = (21,)
                if fault == "moves":
                    current.party_moves = ((34,),)

    actions.execute = act
    binding = s.hideout_elevator_binding(rt, actions, route=Route(), destination_floor=floor)
    assert binding and actions.actions_executed == 0
    if fault and fault != "poison":
        with pytest.raises(ValueError):
            binding.execute()
    else:
        report = binding.execute()
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
        assert not report.evidence["learned"]
        assert report.evidence["field_poison_hp_loss"] == [1 if fault == "poison" else 0]
        with pytest.raises(ValueError):
            binding.execute()


@pytest.mark.parametrize("return_only", [False, True])
@pytest.mark.parametrize("fault", [None, "wrong_floor", "child_failure", "stale"])
def test_center_connection_uses_dynamic_lift_then_verified_center(monkeypatch, return_only, fault):
    from dataclasses import field

    from pokemon_red_completion import red_goal_skills, red_player_field_goals

    current = N(
        map_id=202,
        player_y=4,
        player_x=25,
        bag_items=((74, 1), (72, 1)),
        player_money=100,
        party_species_ids=(1,),
        party_hp=(20,),
        party_pp=((10,),),
        party_status=(0,),
        event_flags=flags(1703),
        badge_bits=15,
        restored=return_only,
    )
    rt = N(
        reader=N(read=lambda: N(**current.__dict__)),
        emulator=N(frame_count=0, save_state_bytes=lambda: repr(current.__dict__).encode()),
    )
    actions = N(actions_executed=0)
    phases = []
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(red_goal_skills, "_raw_party_fully_restored", lambda raw: raw.restored)

    @dataclass
    class Macro:
        edges: dict = field(default_factory=lambda: {200: (N(target_map=203), N(target_map=199))})

    @dataclass
    class World:
        macro_graph: Macro = field(default_factory=Macro)

        def with_current_observation(self, reader):
            return self

    @dataclass
    class Route:
        route_world: World = field(default_factory=World)
        excluded_maps: frozenset = frozenset()
        destination_map: int = 133
        destination_at: tuple = (3, 3)

        def __call__(self, *args):
            assert self.excluded_maps == frozenset({203})
            assert all(
                e.target_map != 203
                for es in self.route_world.macro_graph.edges.values()
                for e in es
            )
            current.map_id, current.player_y, current.player_x = 133, 3, 3
            actions.actions_executed += 1
            if fault == "child_failure":
                current.player_money -= 1

    def lift(*args, destination_floor, **kwargs):
        assert destination_floor == 200

        def execute():
            phases.append(current.map_id)
            current.map_id = (
                203 if current.map_id == 202 else (199 if fault == "wrong_floor" else 200)
            )
            actions.actions_executed += 1
            return s.GoalExecutionReport(1, 0, {})

        return N(execute=execute, verify=lambda _: s.GoalVerification.succeeded())

    def heal(runtime, port, *, home_map, route):
        assert current.map_id == 200 and home_map == 133 and 203 in route.excluded_maps

        def execute():
            current.map_id = 133
            current.restored = True
            return s.GoalExecutionReport(1, 0, {})

        return N(
            execute=execute,
            verify=lambda _: (
                s.GoalVerification.failed(s.GoalFailureReason.OUTCOME_NOT_VERIFIED)
                if fault == "child_failure"
                else s.GoalVerification.succeeded()
            ),
        )

    monkeypatch.setattr(s, "hideout_elevator_binding", lift)
    monkeypatch.setattr(red_player_field_goals, "routed_restoration_binding", heal)
    binding = s.hideout_restoration_binding(rt, actions, route=Route(), return_only=return_only)
    assert binding and not phases and actions.actions_executed == 0
    if fault == "stale":
        current.player_money += 1
    if fault in ("wrong_floor", "stale") or (return_only and fault == "child_failure"):
        with pytest.raises(ValueError):
            binding.execute()
    else:
        report = binding.execute()
        verdict = binding.verify(report)
        assert (verdict.status is GoalDecisionOutcome.SUCCEEDED) == (fault is None)
        assert phases == [202, 203]
        with pytest.raises(ValueError):
            binding.execute()
