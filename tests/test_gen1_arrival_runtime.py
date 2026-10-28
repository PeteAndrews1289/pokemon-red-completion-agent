from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_gen1_scripted_arrival import reentry_cartridge
from test_red_goal_skills import _raw

from pokemon_red_completion import gen1_scripted_arrival as grammar
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_arrival_runtime import ScriptedArrivalInterruptionHandler
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot


def setup(monkeypatch, column=4):
    monkeypatch.setattr(grammar, 'verify_rom_bytes', lambda _: None)
    rom, m, _ = reentry_cartridge()
    flags = bytes([4]) + bytes(319)
    arrival = grammar.trainer_room_arrival(rom, m, flags, allow_reentry=True)
    initial = replace(_raw(), map_id=1, event_flags=flags, battle_state=0)
    r = SimpleNamespace(raw=initial, visible=True, script=0, text=2, pending=None, active=False)
    r.read = lambda: r.raw
    r.read_bottom_dialogue_box_visible = lambda: r.visible
    r.read_current_map_script = lambda: r.script
    r.read_trainer_dialogue_context = lambda: (999, r.text)
    r.read_pending_trainer_battle_identity = lambda: r.pending
    r.trainer_engagement_active = lambda: r.active
    r.read_input_readiness = lambda: SimpleNamespace(ready=not r.visible and r.script == 0)
    actions = []
    def execute(action):
        actions.append(action)
        if action.kind == MacroActionKind.CONFIRM:
            r.raw = replace(r.raw, player_y=r.raw.player_y - 1)
            r.visible = r.raw.player_y > 9
    fallback = SimpleNamespace(handled_hazard_kinds=frozenset(),
                               handled_interruption_kinds=frozenset(),
                               handle=lambda _: 'fallback')
    h = ScriptedArrivalInterruptionHandler(
        rom, arrival, r, SimpleNamespace(execute=execute), fallback,
    )
    r.raw = replace(initial, map_id=m, player_y=11, player_x=column)
    interruption = TraversalSnapshot(m, (11, column), False, 'scripted_dialogue')
    return h, r, actions, interruption


@pytest.mark.parametrize('column', [4, 5])
def test_two_warnings_settle_once_with_no_direction_or_battle_actions(monkeypatch, column):
    h, r, actions, interruption = setup(monkeypatch, column)
    result = h.handle(interruption)
    assert result.resumed_at == (9, column)
    assert result.details == dict(
        source='cartridge_reentry', push_steps=2, confirmations=2, waits=1,
    )
    assert [a.kind for a in actions] == [MacroActionKind.CONFIRM] * 2 + [MacroActionKind.WAIT]
    with pytest.raises(RouteExecutionError):
        h.handle(interruption)
    assert len(actions) == 3


@pytest.mark.parametrize('change', ['text', 'battle', 'pending', 'active', 'script', 'money',
                                   'hp', 'flag', 'position', 'map'])
def test_unknown_lifecycle_never_gets_a_confirm(monkeypatch, change):
    h, r, actions, interruption = setup(monkeypatch)
    if change == 'text':
        r.text = 1
    elif change == 'pending':
        r.pending = (244, 1)
    elif change == 'active':
        r.active = True
    elif change == 'script':
        r.script = 1
    else:
        updates = {'battle': dict(battle_state=2), 'money': dict(player_money=99),
                   'hp': dict(party_hp=(1,)), 'flag': dict(event_flags=bytes(320)),
                   'position': dict(player_y=10), 'map': dict(map_id=2)}
        r.raw = replace(r.raw, **updates[change])
    with pytest.raises(RouteExecutionError):
        h.handle(interruption)
    assert not actions
    assert h.claimed


def test_stuck_warning_has_a_hard_cap_and_cannot_be_retried(monkeypatch):
    h, r, actions, interruption = setup(monkeypatch)
    h.actions.execute = actions.append
    with pytest.raises(RouteExecutionError, match='budget'):
        h.handle(interruption)
    assert len(actions) == 96
    with pytest.raises(RouteExecutionError):
        h.handle(interruption)
    assert len(actions) == 96


def test_other_map_delegation_does_not_consume_arrival(monkeypatch):
    h, r, actions, interruption = setup(monkeypatch)
    assert h.handle(replace(interruption, map_id=1)) == 'fallback'
    assert not h.claimed and not actions


def test_pending_movement_waits_without_pressing_directions(monkeypatch):
    h, r, actions, interruption = setup(monkeypatch)
    def execute(action):
        actions.append(action)
        if action.kind == MacroActionKind.CONFIRM:
            r.visible = False
            r.script = 3
        elif r.script == 3:
            r.raw = replace(r.raw, player_y=r.raw.player_y - 1)
            r.visible = r.raw.player_y > 9
            r.script = 0
    h.actions.execute = execute
    assert h.handle(interruption).resumed_at == (9, 4)
    assert sum(a.kind == MacroActionKind.WAIT for a in actions) == 3


def test_resource_change_during_movement_stops_before_next_input(monkeypatch):
    h, r, actions, interruption = setup(monkeypatch)
    def execute(action):
        actions.append(action)
        r.raw = replace(r.raw, player_money=99)
    h.actions.execute = execute
    with pytest.raises(RouteExecutionError, match='resources'):
        h.handle(interruption)
    assert len(actions) == 1
