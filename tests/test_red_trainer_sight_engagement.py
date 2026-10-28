from dataclasses import dataclass, replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion import red_trainer_sight_engagement as sight
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_trainer_sight import TrainerFacing, TrainerSightZone
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.route_executor import TraversalHazard, TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError


def fixture(shift=0):
    prefix, trigger = (2 + shift, 3), (1 + shift, 3)
    zone = TrainerSightZone(45, 6, 231, 10, (1 + shift, 4),
                            TrainerFacing.LEFT, 2, 86, False, True)
    edge = LocalEdge(trigger, "up", required_mode="land")
    start = TraversalSnapshot(45, (3 + shift, 3), ready=True, mode="land", hazards=tuple(
        TraversalHazard(at, "trainer_sight") for at in zone.lane))

    class World:
        local_graphs = {45: LocalGraph({prefix: (edge,)})}

        def plan_feasible_to_map(self, observed, goal, *, goal_at):
            assert observed.hazards == start.hazards, "never remove hazards for the prefix"
            assert goal_at == prefix and goal == 45
            return NS(steps=(1,), segments=())

    return start, zone, World(), prefix, edge


@pytest.mark.parametrize("shift", [0, 5, 13])
def test_changed_layouts_keep_hazards_and_quote_one_edge(shift):
    start, zone, world, prefix, edge = fixture(shift)
    result = sight.plan_sight_approaches(world, start, (zone,), stationary_slots={6})
    assert result == (sight.TrainerSightApproach(zone, prefix, edge, 1),)


@pytest.mark.parametrize("fault", ["overlap", "moving", "defeated", "occupied", "prefix_hazard",
                                     "other_hazard", "forced", "warp", "mode", "capability",
                                     "blocked", "crossmap", "unready", "duplicate"])
def test_planning_rejects_unsafe_triggers(fault):
    start, zone, world, prefix, edge = fixture()
    zones, slots = (zone,), {6}
    if fault == "overlap":
        zones += (replace(zone, sprite_index=7),)
    elif fault == "moving":
        slots = set()
    elif fault == "defeated":
        zones = (replace(zone, defeated=True),)
    elif fault == "occupied":
        start = replace(start, occupied=frozenset({edge.target}))
    elif fault == "prefix_hazard":
        start = replace(start, hazards=(*start.hazards, TraversalHazard(prefix, "trainer_sight")))
    elif fault == "other_hazard":
        start = replace(start, hazards=(*start.hazards, TraversalHazard(edge.target, "script")))
    elif fault in {"forced", "warp", "mode", "capability"}:
        changed = {"forced": replace(edge, kind="forced_motion"),
                   "warp": replace(edge, kind="warp"),
                   "mode": replace(edge, result_mode="surf"),
                   "capability": replace(edge, requirements=frozenset({"missing"}))}[fault]
        world.local_graphs = {45: LocalGraph({prefix: (changed,)})}
    elif fault == "blocked":
        def blocked(*args, **kwargs):
            raise RoutePlanningError("no safe prefix")
        world.plan_feasible_to_map = blocked
    elif fault == "crossmap":
        world.plan_feasible_to_map = lambda *a, **k: NS(steps=(1,), segments=(1,))
    elif fault == "unready":
        start = replace(start, ready=False)
    elif fault == "duplicate":
        with pytest.raises(sight.TrainerSightEngagementError, match="duplicate"):
            sight.plan_sight_approaches(world, start, (zone, zone), stationary_slots=slots)
        return
    assert not sight.plan_sight_approaches(world, start, zones, stationary_slots=slots)


def execution_fixture(monkeypatch, fault=None, action_limit=999):
    start, zone, world, prefix, edge = fixture()
    state = NS(raw=RawGameState(game_started=True, party_count=1,
                               map_id=45, player_y=3, player_x=3, battle_state=0,
                               player_money=500, party_hp=(50,), event_flags=bytes(32)),
               phase=0, calls=[], routed=False)

    @dataclass
    class Route:
        destination_map: int = 45
        destination_at: tuple = ()

        def __call__(self, actions, reader, emulator):
            if fault == "prefix_failure":
                raise RuntimeError("prefix failed")
            state.raw = replace(state.raw, player_y=prefix[0], player_x=prefix[1])
            state.routed = True
            if fault == "resource":
                state.raw = replace(state.raw, player_money=499)

    def context(*args):
        target = replace(zone, visible=fault != "invisible")
        if state.routed and fault == "changed":
            target = replace(target, trainer_set=11)
        observed = replace(start, at=(state.raw.player_y, state.raw.player_x))
        return (Route(), NS(observe=lambda: observed), world, (target,),
                (NS(object_index=6, is_trainer=True, movement=255),),
                (NS(sprite_index=6, event_flag=86, address=1234),))

    monkeypatch.setattr(sight, "_context", context)

    def execute(action):
        if len(state.calls) >= action_limit:
            raise RuntimeError("shared action budget")
        state.calls.append(action)
        state.phase += 1
        if state.phase == 1:
            state.raw = replace(state.raw, player_y=edge.target[0], player_x=edge.target[1])
        if fault == "timeout":
            state.phase = 1
        if state.phase == 3:
            state.raw = replace(state.raw, battle_state=2)
        if fault == "displaced":
            state.raw = replace(state.raw, player_x=9)
        if fault == "wild":
            state.raw = replace(state.raw, battle_state=1)

    reader = NS(
        read=lambda: state.raw,
        read_pending_trainer_battle_identity=lambda: (
            (231, 11 if fault == "wrong_pending" else 10) if state.phase == 2 else None
        ),
        trainer_engagement_active=lambda: fault == "prearmed",
        read_active_trainer_identity=lambda: (231, 31, 11 if fault == "wrong_battle" else 10),
        read_bottom_dialogue_box_visible=lambda: state.phase == 1 and fault != "timeout",
        read_trainer_dialogue_context=lambda: (1234, 7 if fault == "wrong_dialogue" else 6),
    )
    return state, reader, NS(execute=execute), sight.TrainerSightApproach(zone, prefix, edge, 1)


def test_exact_trigger_dialogue_and_battle_without_combat(monkeypatch):
    state, reader, actions, approach = execution_fixture(monkeypatch)
    result = sight.engage_trainer_sight(None, reader, actions, rom=b"rom", approach=approach)
    assert result["trainer_identity"] == (231, 31, 10)
    assert result["transition_actions"] == 3 and result["combat_choices"] == 0
    assert [a.kind for a in state.calls] == [
        MacroActionKind.MOVE, MacroActionKind.INTERACT, MacroActionKind.WAIT,
    ]


@pytest.mark.parametrize("fault,maximum_calls", [
    ("prefix_failure", 0), ("resource", 0), ("changed", 0), ("invisible", 0),
    ("prearmed", 0), ("wrong_dialogue", 1), ("wrong_pending", 2),
    ("wrong_battle", 3), ("displaced", 1), ("wild", 1), ("timeout", 4),
])
def test_execution_stops_without_combat_or_trigger_retry(monkeypatch, fault, maximum_calls):
    state, reader, actions, approach = execution_fixture(monkeypatch, fault)
    with pytest.raises(RuntimeError):
        sight.engage_trainer_sight(None, reader, actions, rom=b"rom", approach=approach,
                                   maximum_transition_actions=4)
    assert len(state.calls) == maximum_calls
    assert sum(a.kind == MacroActionKind.MOVE for a in state.calls) <= 1
    assert all(a.kind in {MacroActionKind.MOVE, MacroActionKind.WAIT, MacroActionKind.INTERACT}
               for a in state.calls)


@pytest.mark.parametrize("budget", [0, -1, 161, True, 1.5])
def test_invalid_budget_rejects_before_prefix(monkeypatch, budget):
    state, reader, actions, approach = execution_fixture(monkeypatch)
    with pytest.raises(ValueError):
        sight.engage_trainer_sight(None, reader, actions, rom=b"rom", approach=approach,
                                   maximum_transition_actions=budget)
    assert not state.routed and not state.calls


def test_shared_action_cap_propagates_without_retry(monkeypatch):
    state, reader, actions, approach = execution_fixture(monkeypatch, action_limit=1)
    with pytest.raises(RuntimeError, match="shared action budget"):
        sight.engage_trainer_sight(None, reader, actions, rom=b"rom", approach=approach)
    assert len(state.calls) == 1


def test_table_pointer_during_box_draw_only_allows_neutral_wait(monkeypatch):
    state, reader, actions, approach = execution_fixture(monkeypatch)
    context = sight._context

    def with_table(*args):
        route, observer, world, zones, objects, headers = context(*args)
        return route, observer, world, zones, objects, (
            NS(sprite_index=2, event_flag=82, address=1200), *headers,
        )

    monkeypatch.setattr(sight, "_context", with_table)
    reader.read_trainer_dialogue_context = lambda: (1200 if state.phase == 1 else 1234, 6)
    reader.read_bottom_dialogue_box_visible = lambda: state.phase in {1, 2}
    result = sight.engage_trainer_sight(None, reader, actions, rom=b"rom", approach=approach)
    assert result["combat_choices"] == 0
    assert [a.kind for a in state.calls] == [
        MacroActionKind.MOVE, MacroActionKind.WAIT, MacroActionKind.INTERACT,
    ]


@pytest.mark.parametrize("fault", [None, "unarmed", "wrong_slot", "wrong_header", "wrong_at",
                                     "resource", "wrong_pending", "budget"])
def test_retained_trigger_settlement_never_repeats_walk(monkeypatch, fault):
    state, reader, actions, approach = execution_fixture(monkeypatch)
    before = state.raw
    state.phase = 1
    state.raw = replace(before, player_y=1, player_x=3)
    reader.trainer_engagement_active = lambda: fault != "unarmed"
    reader.read_trainer_dialogue_context = lambda: (
        999 if fault == "wrong_header" else 1234, 7 if fault == "wrong_slot" else 6,
    )
    if fault == "wrong_at":
        state.raw = replace(state.raw, player_x=9)
    if fault == "resource":
        state.raw = replace(state.raw, party_hp=(49,))
    if fault == "wrong_pending":
        reader.read_pending_trainer_battle_identity = lambda: (231, 11)
    monkeypatch.setattr(sight, "trainer_headers", lambda *a, **k: (
        NS(sprite_index=2, event_flag=82, address=1200),
        NS(sprite_index=6, event_flag=86, address=1234),
    ))
    kwargs = dict(rom=b"rom", approach=approach, before=before,
                  maximum_transition_actions=1 if fault == "budget" else 5)
    if fault:
        with pytest.raises(sight.TrainerSightEngagementError):
            sight.resume_trainer_sight(reader, actions, **kwargs)
        assert len(state.calls) == (1 if fault == "budget" else 0)
    else:
        assert sight.resume_trainer_sight(reader, actions, **kwargs)["transition_actions"] == 2
    assert all(a.kind != MacroActionKind.MOVE for a in state.calls)
