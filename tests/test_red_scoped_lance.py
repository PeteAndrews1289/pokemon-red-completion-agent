from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
import test_red_scoped_lorelei as lorelei

from pokemon_red_completion.observation import EventFlag, MapId
from pokemon_red_completion.red_lorelei_story import (
    ScopedAssistedLanceController,
    story_league_controller,
)


def controller(tmp_path):
    old = lorelei.controller(tmp_path)
    contract = replace(old.contract, objective_id="defeat_lance",
        map_id=int(MapId.LANCES_ROOM), trainer_identity=(247, 47, 1),
        defeated_event=int(EventFlag.BEAT_LANCES_ROOM_TRAINER), victory_money=6138)
    actor = old.battler
    actor.development_story_scope = replace(actor.development_story_scope, contract=contract)
    actor.qualification_sha256 = actor.development_story_scope.identity
    return ScopedAssistedLanceController(actor, contract, old.admission, 80)


@pytest.mark.parametrize("fault", [
    "source", "model", "work", "assistance", "contract", "partition", "budget",
])
def test_scoped_lance_rejects_changed_authority(tmp_path, monkeypatch, fault):
    base = lorelei.controller
    # Build before replacing the shared fixture to avoid recursive construction.
    ctl = controller(tmp_path)
    monkeypatch.setattr(lorelei, "controller", lambda _: ctl)
    lorelei.test_scoped_lorelei_rejects_changed_authority(tmp_path, fault)
    assert base is not lorelei.controller


@pytest.mark.parametrize("objective,rematch", [
    ("defeat_lorelei", False), ("defeat_bruno", False), ("defeat_agatha", False),
    ("defeat_lance", True),
])
def test_only_first_lance_scope_is_resolved(tmp_path, objective, rematch):
    ctl = controller(tmp_path)
    runtime = NS(league_story_battle_controller=ctl)
    assert story_league_controller(runtime, "defeat_lance") is ctl
    with pytest.raises(ValueError):
        story_league_controller(runtime, objective, rematch=rematch)


@pytest.mark.parametrize("changes", [
    {"trainer_identity": (244, 44, 1)}, {"map_id": int(MapId.BRUNOS_ROOM)},
    {"defeated_event": int(EventFlag.BEAT_LORELEI)},
])
def test_rehashed_scope_cannot_redirect_lance(tmp_path, changes):
    ctl = controller(tmp_path)
    ctl.contract = replace(ctl.contract, **changes)
    actor = ctl.battler
    actor.development_story_scope = replace(actor.development_story_scope, contract=ctl.contract)
    actor.qualification_sha256 = actor.development_story_scope.identity
    with pytest.raises(ValueError):
        ctl.require_identity()
    assert actor.calls == 0


@pytest.mark.parametrize("deficit,allowed", [(5, True), (7, True), (6, False), (100, False)])
def test_seven_level_screen_requires_exact_lance_scope(monkeypatch, tmp_path, deficit, allowed):
    from test_red_trainer_story import fixture

    from pokemon_red_completion.red_trainer_story import (
        RedCartridgeLoreleiSkill,
        RedTrainerStoryError,
    )

    skill, _, _, _, _ = fixture.__wrapped__(monkeypatch)
    ctl = controller(tmp_path)
    skill.runtime.league_story_battle_controller = ctl
    if allowed:
        skill = replace(skill, objective_id="defeat_lance",
            recovery_controller=ctl.controller_name, maximum_level_deficit=deficit)
        skill._require_controller_contract()
    else:
        with pytest.raises(RedTrainerStoryError, match="level-screen"):
            replace(skill, objective_id="defeat_lance",
                recovery_controller=ctl.controller_name, maximum_level_deficit=deficit)
    assert RedCartridgeLoreleiSkill.__dataclass_fields__["maximum_level_deficit"].default == 5


def test_changed_scope_blocks_seven_level_override_before_input(monkeypatch, tmp_path):
    from test_red_trainer_story import fixture

    skill, _, inputs, _, _ = fixture.__wrapped__(monkeypatch)
    ctl = controller(tmp_path)
    skill.runtime.league_story_battle_controller = ctl
    skill = replace(skill, objective_id="defeat_lance",
        recovery_controller=ctl.controller_name, maximum_level_deficit=7)
    skill._require_controller_contract()
    ctl.admission = b"mutated"
    with pytest.raises(ValueError):
        skill._require_controller_contract()
    assert not inputs


def test_prepared_seven_level_allowance_cannot_change_before_execution(monkeypatch, tmp_path):
    from test_red_trainer_story import fixture

    from pokemon_red_completion.red_trainer_story import RedTrainerStoryError

    skill, _, inputs, observe, _ = fixture.__wrapped__(monkeypatch)
    ctl = controller(tmp_path)
    skill.runtime.league_story_battle_controller = ctl
    skill = replace(skill, objective_id="defeat_lance",
        recovery_controller=ctl.controller_name, maximum_level_deficit=7)
    skill._prepared = (observe(), None, None)
    skill._prepared_budget = skill.maximum_full_restores
    skill._prepared_risk_budget = skill.maximum_critical_exposures
    skill._prepared_controller = skill.recovery_controller
    skill._prepared_objective_id = skill.objective_id
    skill._prepared_learned_controller = ctl
    skill._prepared_story_binding = ctl.binding_identity
    skill._prepared_rematch = skill.rematch
    skill._prepared_reentry = skill.allow_scripted_reentry
    skill._prepared_level_deficit = 7
    skill.maximum_level_deficit = 5
    with pytest.raises(RedTrainerStoryError, match="prepared level-screen"):
        skill.execute()
    assert not inputs
