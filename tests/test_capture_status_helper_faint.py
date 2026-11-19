"""An observed helper faint is retained while existing catcher mechanics settle."""

from dataclasses import replace

import pytest
from test_red_capture_status_runtime import setup

from pokemon_red_completion import red_capture_status_runtime as runtime


def prepare_switch(monkeypatch, *, end=False, drift=False):
    world, prepare = setup(monkeypatch)
    world.raw = replace(world.raw, active_party_index=1, active_party_hp=200)
    calls = []

    def switch(_actions, _reader, _emulator, index, **kwargs):
        calls.append((index, kwargs))
        if index == 0:
            assert kwargs["allow_faint_outcome"] is True
            helper, catcher = world.party.members
            world.party = replace(world.party, members=(replace(helper, hp=0), catcher))
            world.raw = replace(
                world.raw,
                active_party_index=0,
                active_party_hp=0,
                battle_state=0 if end else 1,
                bag_items=((4, 3),) if drift else world.raw.bag_items,
            )
        else:
            # Existing protected-catcher switch owns the forced replacement.
            assert world.party.members[0].hp == 0 and index == 1
            world.raw = replace(world.raw, active_party_index=1, active_party_hp=200)

    monkeypatch.setattr(runtime, "switch_active_battler", switch)
    return world, prepare, calls


def test_helper_faint_keeps_loss_and_uses_existing_healthy_catcher(monkeypatch):
    world, prepare, calls = prepare_switch(monkeypatch)
    assert prepare() is True
    assert [index for index, _ in calls] == [0, 1]
    assert world.party.members[0].hp == 0 and world.turns == 0
    assert prepare.reports == [] and prepare.attempts == 0
    assert prepare.throw_preparations[-1]["target_status"] == "healthy"
    assert world.raw.enemy_hp == 25 and world.raw.bag_items == ((4, 4),)


def test_ended_encounter_is_not_reported_as_capture_or_status(monkeypatch):
    world, prepare, calls = prepare_switch(monkeypatch, end=True)
    assert prepare() is False
    assert len(calls) == 1 and world.party.members[0].hp == 0
    assert prepare.reports == prepare.throw_preparations == []


def test_helper_faint_does_not_excuse_inventory_drift(monkeypatch):
    _, prepare, _ = prepare_switch(monkeypatch, drift=True)
    with pytest.raises(runtime.RedCaptureStatusError) as error:
        prepare()
    assert error.value.reason_code == runtime.CaptureStatusDrift.BAG_ITEMS.value
