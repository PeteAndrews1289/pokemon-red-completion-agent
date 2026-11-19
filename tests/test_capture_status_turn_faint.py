"""A real helper faint preserves attempt/effect facts and catcher protection."""

from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_capture_status_runtime import setup

from pokemon_red_completion import red_capture_status_runtime as runtime


def prepare_faint(monkeypatch, *, executed=True, status=0, pp_drift=False, damage=None):
    world, prepare = setup(monkeypatch)
    switches = []

    def turn(*args, **kwargs):
        world.turns += 1
        helper, catcher = world.party.members
        spent = int(executed) + int(pp_drift)
        helper = replace(helper, hp=0, moves=(replace(helper.moves[0], current_pp=10 - spent),))
        world.party = replace(world.party, members=(helper, catcher))
        world.raw = replace(world.raw, active_party_hp=0)
        world.status = status
        if damage == "target":
            world.raw = replace(world.raw, enemy_hp=24)
        if damage == "bag":
            world.raw = replace(world.raw, bag_items=((4, 3),))
        return NS(move_executed=executed)

    def switch(_actions, _reader, _emulator, index, **kwargs):
        assert index == 1 and world.party.members[0].hp == 0
        switches.append(index)
        world.raw = replace(world.raw, active_party_index=index, active_party_hp=200)

    monkeypatch.setattr(runtime, "execute_bounded_battle_move_turn", turn)
    monkeypatch.setattr(runtime, "switch_active_battler", switch)
    return world, prepare, switches


@pytest.mark.parametrize("executed,status", [(True, 0), (False, 0), (True, 3)])
def test_faint_retains_observed_move_effect_and_returns_to_healthy_catcher(
    monkeypatch, executed, status
):
    world, prepare, switches = prepare_faint(monkeypatch, executed=executed, status=status)
    assert prepare() is True
    assert world.turns == prepare.attempts == 1 and switches == [1]
    assert world.party.members[0].hp == 0 and world.party.members[1].hp == 200
    assert world.boundaries == 1  # Forced replacement owns the unsettled faint menu.
    (report,) = prepare.reports
    assert report["helper_fainted"] and report["observed_faints"] == 1
    assert report["loss_coverage_complete"] is False
    assert report["move_executed"] is executed
    assert report["status_success"] is (executed and status == 3)
    assert prepare.throw_preparations[-1]["target_status"] == ("sleep" if status else "healthy")
    assert world.raw.enemy_hp == 25 and world.raw.bag_items == ((4, 4),)


def test_faint_does_not_excuse_unverified_move_pp(monkeypatch):
    _, prepare, switches = prepare_faint(monkeypatch, pp_drift=True)
    with pytest.raises(runtime.RedCaptureStatusError, match="PP differs"):
        prepare()
    assert switches == []


@pytest.mark.parametrize("damage", ["target", "bag"])
def test_faint_does_not_excuse_target_or_inventory_drift(monkeypatch, damage):
    _, prepare, switches = prepare_faint(monkeypatch, damage=damage)
    with pytest.raises(runtime.RedCaptureStatusError):
        prepare()
    assert switches == []
