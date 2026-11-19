"""Fly wiring plus real existing recovery machinery; all native ports are fake."""
from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from test_red_collection_fly import scene
from test_wild_party_flee import state
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.observation import BattleMenuPhase
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot
from pokemon_red_completion.red_routed_recovery import (
    SettledNativeWildRecovery, guarded_collection_route_handler,
    settled_route_wild_recovery_evidence,
)


def fly_options(scene, monkeypatch):
    from pokemon_red_completion import red_routed_recovery as recovery
    seen = []
    original = recovery.guarded_collection_route_handler
    def capture(*args, **kwargs):
        seen.append(dict(kwargs))
        return original(*args, **kwargs)
    monkeypatch.setattr(recovery, "guarded_collection_route_handler", capture)
    scene.bind().execute()
    assert len(seen) == 1
    return seen[0]


def native_fixture(options, monkeypatch, fault=None):
    from pokemon_red_completion import battle_recovery

    initial = replace(state(), first_party_hp=10, active_party_hp=10,
                      party_hp=(10, 140, 27, 63), battle_state=0)
    class Game:
        raw = initial
        frame_count = 0
        pressed_buttons = ()
        buttons = []
        def execute(self, action):
            self.buttons.append(action.kind)
            self.frame_count += action.repeat
            if action.kind is MacroActionKind.CONFIRM:
                updates = dict(first_party_hp=0, active_party_hp=0, party_hp=(0, 140, 27, 63))
                if fault == "species": updates["party_species_ids"] = (1, 2, 4, 3)
                if fault == "pp": updates["party_pp"] = ((19, 20, 20, 20),) * 4
                if fault == "cash": updates["player_money"] = 4582
                if fault == "items": updates["bag_items"] = ((1, 1),)
                if fault == "events": updates["event_flags"] = bytes(319) + b"x"
                if fault == "blackout": updates["party_hp"] = (0, 0, 0, 0)
                self.raw = replace(self.raw, **updates)
            elif action.kind is MacroActionKind.CANCEL:
                self.raw = replace(self.raw, battle_state=0, battle_result=2)
        def save_state_bytes(self):
            return repr(self.raw).encode()
    game = Game()
    reader = N(
        read=lambda: game.raw, read_input_readiness=lambda: N(ready=game.raw.battle_state == 0),
        read_bottom_dialogue_box_visible=lambda: False, trainer_engagement_active=lambda: False,
        read_retained_wild_identity=lambda: N(original_species_id=131 if fault == "one_off" else 185),
        read_battle_menu_state=lambda raw: N(
            phase=BattleMenuPhase.MAIN if raw.active_party_hp else BattleMenuPhase.UNKNOWN,
            selected_main_command=3),
    )
    monkeypatch.setattr(battle_recovery, "_forced_party_menu_ready", lambda *_: False)
    actions = CountingExecutor(game)
    options = dict(options, emulator=game)
    handler = guarded_collection_route_handler(actions, reader, **options)
    game.raw = replace(initial, battle_state=2 if fault == "trainer" else 1)
    interruption = TraversalSnapshot(
        18 if fault == "wrong_map" else 17, (10, 14), False, interruption="wild_battle")
    return game, actions, handler, interruption


def test_actual_fly_options_route_run_ko_to_metered_recovery_without_healing(scene, monkeypatch):
    options = fly_options(scene, monkeypatch)
    game, actions, handler, interruption = native_fixture(options, monkeypatch)
    with pytest.raises(SettledNativeWildRecovery) as stopped:
        handler.handle(interruption)
    report = stopped.value.report
    assert settled_route_wild_recovery_evidence(report.evidence)
    assert report.evidence["party_hp_before"] == [10, 140, 27, 63]
    assert report.evidence["party_hp"] == [0, 140, 27, 63]
    assert report.evidence["new_fainted_slots"] == [1]
    assert report.evidence["wild_escape"]["run_attempts"] == 1
    assert report.evidence["cash_before"] == report.evidence["cash_after"] == 4583
    assert report.evidence["model_queries"] == 0
    assert report.actions_executed == actions.actions_executed > 0
    assert report.frames_executed == game.frame_count > 0
    assert game.raw.battle_state == 0 and game.raw.party_hp[0] == 0
    assert set(game.buttons) == {MacroActionKind.CONFIRM, MacroActionKind.CANCEL, MacroActionKind.WAIT}


@pytest.mark.parametrize("fault", ["wrong_map", "trainer", "one_off"])
def test_fly_options_reject_wrong_encounter_before_any_input(scene, monkeypatch, fault):
    options = fly_options(scene, monkeypatch)
    game, actions, handler, interruption = native_fixture(options, monkeypatch, fault)
    with pytest.raises((RouteExecutionError, RuntimeError)):
        handler.handle(interruption)
    assert actions.actions_executed == 0 and not game.buttons


@pytest.mark.parametrize("fault", ["species", "pp", "cash", "items", "events", "blackout"])
def test_fly_options_keep_protected_party_and_resource_failures_closed(scene, monkeypatch, fault):
    options = fly_options(scene, monkeypatch)
    game, actions, handler, interruption = native_fixture(options, monkeypatch, fault)
    with pytest.raises((RouteExecutionError, RuntimeError)):
        handler.handle(interruption)
    assert MacroActionKind.CANCEL not in game.buttons


def test_unopted_generic_default_still_refuses_run_induced_faint(monkeypatch):
    game, actions, handler, interruption = native_fixture(
        dict(route_name="unchanged generic default"), monkeypatch)
    with pytest.raises(RouteExecutionError, match="protected encounter boundary"):
        handler.handle(interruption)
    assert MacroActionKind.CANCEL not in game.buttons
