from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
import test_red_scoped_lorelei as lorelei

from pokemon_red_completion.observation import EventFlag, MapId
from pokemon_red_completion.red_lorelei_story import (
    ScopedAssistedBrunoController,
    story_league_controller,
)


def controller(tmp_path):
    old = lorelei.controller(tmp_path)
    contract = replace(old.contract, objective_id="defeat_bruno",
        map_id=int(MapId.BRUNOS_ROOM), trainer_identity=(233, 33, 1),
        defeated_event=int(EventFlag.BEAT_BRUNO), victory_money=5742)
    actor = old.battler
    actor.development_story_scope = replace(actor.development_story_scope, contract=contract)
    actor.qualification_sha256 = actor.development_story_scope.identity
    return ScopedAssistedBrunoController(actor, contract, old.admission, 80)


@pytest.mark.parametrize("fault", [
    "source", "model", "work", "assistance", "contract", "partition", "budget",
])
def test_scoped_bruno_rejects_changed_authority(tmp_path, monkeypatch, fault):
    base = lorelei.controller
    # Build before replacing the shared fixture to avoid recursive construction.
    ctl = controller(tmp_path)
    monkeypatch.setattr(lorelei, "controller", lambda _: ctl)
    lorelei.test_scoped_lorelei_rejects_changed_authority(tmp_path, fault)
    assert base is not lorelei.controller


@pytest.mark.parametrize("objective,rematch", [
    ("defeat_lorelei", False), ("defeat_agatha", False), ("defeat_lance", False),
    ("defeat_bruno", True),
])
def test_only_first_bruno_scope_is_resolved(tmp_path, objective, rematch):
    ctl = controller(tmp_path)
    runtime = NS(league_story_battle_controller=ctl)
    assert story_league_controller(runtime, "defeat_bruno") is ctl
    with pytest.raises(ValueError):
        story_league_controller(runtime, objective, rematch=rematch)


@pytest.mark.parametrize("changes", [
    {"trainer_identity": (244, 44, 1)}, {"map_id": int(MapId.AGATHAS_ROOM)},
    {"defeated_event": int(EventFlag.BEAT_LORELEI)},
])
def test_rehashed_scope_cannot_redirect_bruno(tmp_path, changes):
    ctl = controller(tmp_path)
    ctl.contract = replace(ctl.contract, **changes)
    actor = ctl.battler
    actor.development_story_scope = replace(actor.development_story_scope, contract=ctl.contract)
    actor.qualification_sha256 = actor.development_story_scope.identity
    with pytest.raises(ValueError):
        ctl.require_identity()
    assert actor.calls == 0
