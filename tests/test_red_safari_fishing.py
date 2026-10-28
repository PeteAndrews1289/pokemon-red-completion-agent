"""Paid-session controls must never fall back to ordinary battles or admission."""

from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

import pokemon_red_completion.red_safari_fishing as mod
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.observation import RawGameState, RedSafariSessionState
from pokemon_red_completion.route_executor import TraversalSnapshot


def inputs():
    raw = RawGameState(
        True,
        217,
        9,
        11,
        6,
        0,
        player_money=17468,
        bag_items=(),
        party_hp=(100,),
        party_pp=((10, 10, 0, 0),),
    )
    state = NS(raw=raw, session=RedSafariSessionState(29, 129, True, False), actions=0)
    reader = NS(
        read=lambda: state.raw,
        read_safari_session_state=lambda: state.session,
        read_input_readiness=lambda: NS(ready=True),
    )
    return state, reader


@pytest.mark.parametrize("fault", ["inactive", "over", "balls", "steps", "map", "battle", "ready"])
def test_session_gate_refuses_incompatible_state(fault):
    state, reader = inputs()
    if fault == "inactive":
        state.session = replace(state.session, in_safari_zone=False)
    elif fault == "over":
        state.session = replace(state.session, safari_game_over=True)
    elif fault == "balls":
        state.session = replace(state.session, safari_balls=1)
    elif fault == "steps":
        state.session = replace(state.session, safari_steps=16)
    elif fault == "map":
        state.raw = replace(state.raw, map_id=5)
    elif fault == "battle":
        state.raw = replace(state.raw, battle_state=1)
    else:
        reader.read_input_readiness = lambda: NS(ready=False)
    with pytest.raises(mod.SafariFishingError, match="active, funded, ready"):
        mod.require_safari_session(reader)


def route(steps=2, **changes):
    row = dict(
        source_map=217,
        expected_map=218,
        kind="warp",
        action_kind=MacroActionKind.MOVE,
        source_mode="land",
        expected_mode="land",
    )
    row.update(changes)
    return NS(steps=(NS(**row),) * steps, terminal_map=218, terminal_mode="land")


@pytest.mark.parametrize("remaining,expected", [(18, True), (17, False), (16, False)])
def test_route_keeps_a_paid_step_reserve(remaining, expected):
    assert mod.safari_route_supported(route(), remaining) is expected


@pytest.mark.parametrize(
    "change",
    [
        {"source_map": 5},
        {"expected_map": 156},
        {"kind": "surf"},
        {"action_kind": MacroActionKind.CONFIRM},
        {"expected_mode": "surf"},
    ],
)
def test_route_cannot_leave_session_or_use_unsupported_transport(change):
    assert not mod.safari_route_supported(route(**change), 129)


def test_guarded_route_checks_actual_remaining_steps_before_each_input():
    state, reader = inputs()
    calls = []
    port = mod.SafariFishingRoutePort(NS(execute=calls.append), reader)
    port.execute(MacroAction(MacroActionKind.MOVE, "up"))
    state.session = replace(state.session, safari_steps=16)
    with pytest.raises(mod.SafariFishingError):
        port.execute(MacroAction(MacroActionKind.MOVE, "up"))
    assert len(calls) == 1


@pytest.mark.parametrize("ready", [False, True])
def test_safari_interruption_uses_run_and_preserves_session(monkeypatch, ready):
    state, reader = inputs()
    state.raw = replace(state.raw, battle_state=1)
    reader.read_input_readiness = lambda: NS(ready=ready)
    calls = []

    def flee():
        calls.append("Safari RUN")
        state.raw = replace(state.raw, battle_state=0)

    monkeypatch.setattr(mod, "safari_encounters", lambda *_: NS(flee_encounter=flee))
    handler = mod.SafariFishingInterruptionHandler(object(), object(), reader)
    result = handler.handle(TraversalSnapshot(217, (11, 9), True, interruption="wild_battle"))
    assert calls == ["Safari RUN"] and result.kind == "wild_battle"
    assert handler.flees == 1 and state.session.safari_steps == 129


@pytest.mark.parametrize("fault", ["trainer", "drift", "limit", "changed_balls"])
def test_safari_interruption_refuses_wrong_boundary_or_resource_change(monkeypatch, fault):
    state, reader = inputs()
    state.raw = replace(state.raw, battle_state=1)
    handler = mod.SafariFishingInterruptionHandler(object(), object(), reader)
    snapshot = TraversalSnapshot(217, (11, 9), True, interruption="wild_battle")
    if fault == "trainer":
        snapshot = replace(snapshot, interruption="trainer_battle")
    elif fault == "drift":
        snapshot = replace(snapshot, at=(0, 0))
    elif fault == "limit":
        handler.flees = 16

    def flee():
        assert fault == "changed_balls"
        state.raw = replace(state.raw, battle_state=0)
        state.session = replace(state.session, safari_balls=28)

    monkeypatch.setattr(mod, "safari_encounters", lambda *_: NS(flee_encounter=flee))
    with pytest.raises(mod.SafariFishingError):
        handler.handle(snapshot)


@pytest.mark.parametrize("balls,throws", [(29, 8), (5, 4), (2, 1)])
def test_capture_keeps_last_ball_in_paid_session(monkeypatch, balls, throws):
    state, reader = inputs()
    state.session = replace(state.session, safari_balls=balls)
    monkeypatch.setattr(mod, "LiveSafariAreaExecutor", lambda *a, **kw: kw)
    assert (
        mod.safari_encounters(object(), object(), reader)["maximum_throws_per_encounter"] == throws
    )


def test_selected_fishing_composes_safari_route_and_capture(monkeypatch):
    state, reader = inputs()
    calls = []
    planned = route()
    destination = NS(offer=NS(map_id=218), stance=NS(at=(1, 2)))
    world = NS(plan_feasible_to_map=lambda *a, **kw: planned)
    observer = NS(observe=lambda: object())
    controller = NS(pressed_buttons=frozenset())

    def execute(plan, port, passed_observer, **kwargs):
        assert plan is planned and passed_observer is observer
        assert isinstance(port, mod.SafariFishingRoutePort)
        assert isinstance(kwargs["interruption_handler"], mod.SafariFishingInterruptionHandler)
        calls.append("route")
        state.raw = replace(state.raw, map_id=218, player_y=1, player_x=2)
        state.session = replace(state.session, safari_steps=127)
        return NS(passed=True)

    monkeypatch.setattr(mod, "execute_route", execute)
    monkeypatch.setattr(mod, "safari_encounters", lambda *_: object())
    expected = object()

    def capture(offer, port, **kwargs):
        assert offer is destination.offer and isinstance(port, mod.SafariFishingCapturePort)
        assert kwargs["maximum_casts"] == 24
        calls.append("capture")
        state.session = replace(state.session, safari_balls=28)
        return expected

    monkeypatch.setattr(mod, "run_red_fishing_capture", capture)
    actual = mod.run_safari_fishing(
        destination,
        world=world,
        observer=observer,
        controller=controller,
        actions=object(),
        reader=reader,
        maximum_casts=24,
    )
    assert actual is expected and calls == ["route", "capture"]
