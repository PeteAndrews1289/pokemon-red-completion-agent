from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace as NS

import pytest
import test_red_lorelei_story as original

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_development_story_scope import DevelopmentStoryScope
from pokemon_red_completion.red_learned_trainer import AGATHA_STORY_SHA256, FrozenTrainerBattler
from pokemon_red_completion.red_lorelei_story import (
    ScopedAssistedLoreleiController,
    story_league_controller,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def controller(tmp_path):
    admission = b"owner-approved exact Lorelei development work order"
    model = NS(to_dict=lambda: {"test": True})
    contract = original.contract()
    scope = DevelopmentStoryScope("b"*64, "root", AGATHA_STORY_SHA256,
        canonical_sha256(model.to_dict()), sha256(admission).hexdigest(), True, contract)
    actor = FrozenTrainerBattler(None, model, tmp_path, "a"*40, "root", "b"*64, {},
        model_sha256=AGATHA_STORY_SHA256, qualification_sha256=scope.identity,
        development_story_scope=scope)
    return ScopedAssistedLoreleiController(actor, contract, admission, 73)


@pytest.mark.parametrize("fault", [None, "partition", "model", "work", "source", "first_only"])
def test_retry_reentry_uses_exact_new_scope_without_widening_first_challenge(tmp_path, fault):
    from pokemon_red_completion.red_lorelei_story import ScopedAssistedLeagueRetryController
    from pokemon_red_completion.red_trainer_story import RedCartridgeLoreleiSkill

    ctl = controller(tmp_path)
    retry = ScopedAssistedLeagueRetryController(ctl.battler, ctl.contract, ctl.admission, 73)
    if fault == "partition":
        retry.battler.source_partition = ScenarioPartition.TRAIN
    if fault == "model":
        retry.battler.model = NS(to_dict=lambda: {"changed": True})
    if fault == "work":
        retry.admission = b"other work"
    if fault == "source":
        retry.battler.source_state_sha256 = "f"*64
    rt = NS(league_story_battle_controller=ctl if fault == "first_only" else retry)
    arguments = dict(recovery_controller=retry.controller_name, rematch=True,
                     development_retry_reentry=True)
    if fault is None:
        skill = RedCartridgeLoreleiSkill(rt, None, None, **arguments)
        assert skill.development_retry_reentry and not skill.allow_scripted_reentry
        assert retry.battler.calls == 0
    else:
        with pytest.raises(ValueError):
            RedCartridgeLoreleiSkill(rt, None, None, **arguments)
    assert not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("flag", [None, 1, "true"])
def test_retry_reentry_requires_boolean(monkeypatch, flag):
    from pokemon_red_completion.red_trainer_story import (
        RedCartridgeLoreleiSkill,
        RedTrainerStoryError,
    )

    with pytest.raises(RedTrainerStoryError, match="boolean"):
        RedCartridgeLoreleiSkill(NS(), None, None, development_retry_reentry=flag)


def test_no_stay_copy_requires_explicit_frozen_controller_declaration(tmp_path):
    ctl = controller(tmp_path)
    actor = ctl.battler
    actor.development_story_scope = replace(actor.development_story_scope,
        diagnostic_stay_when_productive=False)
    actor.qualification_sha256 = actor.development_story_scope.identity
    with pytest.raises(ValueError):
        ctl.require_identity()
    ctl.declared_stay_when_productive = False
    ctl.require_identity()
    before = ctl.binding_identity
    ctl.declared_stay_when_productive = True
    assert before != ctl.binding_identity
    with pytest.raises(ValueError):
        ctl.require_identity()
    assert actor.calls == 0


@pytest.mark.parametrize("fault", [
    None, "disabled", "partition", "source", "model", "receipt", "authority",
])
def test_pp_reentry_reuses_authenticated_scope_without_unscoped_admission(tmp_path, fault):
    ctl = controller(tmp_path)
    actor = ctl.battler
    authority = actor.story_authority()
    actor.pp_depleted_switch_screen = fault != "disabled"
    if fault == "partition":
        actor.source_partition = ScenarioPartition.TRAIN
    elif fault == "source":
        actor.source_state_sha256 = "e" * 64
    elif fault == "model":
        actor.model = NS(to_dict=lambda: {"changed": True})
    elif fault == "receipt":
        actor.qualification_sha256 = "f" * 64
    elif fault == "authority":
        authority = "frozen-k-story-development"
    if fault in (None, "disabled"):
        assert actor.pp_reentry_screen_active(authority) is (fault != "disabled")
        assert actor.forced_struggle_active(authority) is (fault != "disabled")
    else:
        with pytest.raises(ValueError):
            actor.pp_reentry_screen_active(authority)
    assert actor.calls == 0 and not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("declaration", [None, 0, 1, "false"])
def test_stay_declaration_requires_an_actual_boolean(tmp_path, declaration):
    ctl = controller(tmp_path)
    ctl.declared_stay_when_productive = declaration
    with pytest.raises(ValueError):
        ctl.require_identity()
    assert ctl.battler.calls == 0


def test_no_stay_declaration_cannot_expand_to_another_league_controller(tmp_path):
    from pokemon_red_completion.red_lorelei_story import ScopedAssistedBrunoController

    ctl = controller(tmp_path)
    actor = ctl.battler
    actor.development_story_scope = replace(actor.development_story_scope,
        diagnostic_stay_when_productive=False)
    actor.qualification_sha256 = actor.development_story_scope.identity
    with pytest.raises(ValueError):
        ScopedAssistedBrunoController(actor, ctl.contract, ctl.admission, 73,
            declared_stay_when_productive=False)
    assert actor.calls == 0


@pytest.mark.parametrize("fault", [None, "undeclared", "content", "source", "work", "partition"])
def test_new_composition_requires_explicit_declaration_and_actual_scope(tmp_path, fault):
    ctl = controller(tmp_path)
    actor = ctl.battler
    actor.model_sha256 = "f" * 64
    actor.development_story_scope = replace(actor.development_story_scope, model_sha256="f" * 64)
    actor.qualification_sha256 = actor.development_story_scope.identity
    ctl.declared_model_sha256 = "f" * 64
    if fault == "undeclared":
        ctl.declared_model_sha256 = AGATHA_STORY_SHA256
    if fault == "content":
        actor.model = NS(to_dict=lambda: {"changed": True})
    if fault == "source":
        actor.source_state_sha256 = "e" * 64
    if fault == "work":
        ctl.admission = b"other work"
    if fault == "partition":
        actor.source_partition = ScenarioPartition.TRAIN
    if fault is None:
        ctl.require_identity()
        assert ctl.binding_identity[-2:] == ("f" * 64, 5)
    else:
        with pytest.raises(ValueError):
            ctl.require_identity()
    assert actor.calls == 0 and not list(tmp_path.iterdir())


@pytest.mark.parametrize("deficit", [True, -1, 101, 9.5])
def test_invalid_declared_level_heuristic_fails_before_input(tmp_path, deficit):
    ctl = controller(tmp_path)
    ctl.declared_level_deficit = deficit
    with pytest.raises(ValueError):
        ctl.require_identity()
    assert ctl.battler.calls == 0


def test_current_scope_level_heuristic_is_exact_and_frozen(monkeypatch, tmp_path):
    skill, reader, inputs, observe, _ = original.story_fixture.__wrapped__(monkeypatch)
    ctl = controller(tmp_path)
    ctl.declared_level_deficit = 9
    skill.runtime.league_story_battle_controller = ctl
    skill.recovery_controller = ctl.controller_name
    skill.maximum_level_deficit = 8
    assert not skill.availability(observe().game_state).executable
    skill.maximum_level_deficit = 9
    assert skill.availability(observe().game_state).executable
    ctl.declared_level_deficit = 10
    with pytest.raises((ValueError, RuntimeError)):
        skill.execute()
    assert not inputs


@pytest.mark.parametrize("fault", [
    "source", "model", "work", "assistance", "contract", "partition", "budget",
])
def test_scoped_lorelei_rejects_changed_authority(tmp_path, fault):
    ctl = controller(tmp_path)
    actor = ctl.battler
    if fault == "source":
        actor.source_state_sha256 = "e"*64
    elif fault == "model":
        actor.model = NS(to_dict=lambda: {})
    elif fault == "work":
        ctl.admission = b"other"
    elif fault == "assistance":
        actor.development_story_scope = replace(actor.development_story_scope,
            diagnostic_stay_when_productive=False)
    elif fault == "contract":
        ctl.contract = replace(ctl.contract, victory_money=1)
    elif fault == "partition":
        actor.source_partition = ScenarioPartition.TRAIN
    else:
        ctl.maximum_decisions = 81
    with pytest.raises(ValueError):
        ctl.require_identity()
    assert actor.calls == 0 and not list(tmp_path.iterdir())


@pytest.mark.parametrize("objective,rematch", [("defeat_bruno", False), ("defeat_lance", False),
                                               ("defeat_lorelei", True)])
def test_scope_does_not_authorize_other_room_or_rematch(tmp_path, objective, rematch):
    ctl = controller(tmp_path)
    rt = NS(league_story_battle_controller=ctl)
    assert story_league_controller(rt, "defeat_lorelei") is ctl
    with pytest.raises(ValueError):
        story_league_controller(rt, objective, rematch=rematch)


def test_availability_freezes_scope_before_any_input(monkeypatch, tmp_path):
    skill, reader, inputs, observe, _ = original.story_fixture.__wrapped__(monkeypatch)
    ctl = controller(tmp_path)
    skill.runtime.league_story_battle_controller = ctl
    skill.recovery_controller = ctl.controller_name
    assert skill.availability(observe().game_state).executable
    ctl.admission = b"changed after preparation"
    with pytest.raises(ValueError):
        skill.execute()
    assert not inputs


@pytest.mark.parametrize("mode", ["won", "lost", "unresolved"])
def test_existing_native_lifecycle_is_reused_without_teacher(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(original, "controller", controller)
    original.test_real_story_lifecycle_retains_outcome_and_never_calls_teacher(
        tmp_path, monkeypatch, mode,
    )
