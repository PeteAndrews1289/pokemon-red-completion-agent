"""Kind-level story commitment: keep the story objective under way instead of detouring (session 32)."""

from __future__ import annotations

import pytest
from test_story_branch_value import _index, _options, _parent, _story

from pokemon_red_completion import red_story_kind_commitment as kc
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.player_readiness import READINESS_NAMES, PlayerReadiness
from pokemon_red_completion.red_live_option_menu import RedLiveOptionChoice, RedLiveOptionSelectionMode
from pokemon_red_completion.red_story_kind_commitment import (
    StoryKindCommitment,
    commit_story_kind,
    commitment_after_choice,
    commitment_after_outcome,
    party_fit,
)


def readiness(**changes):
    values = dict.fromkeys(READINESS_NAMES[1:], 0.0)
    values.update({"current.hp_fraction": 1.0, "current.pp_known": 1.0, "current.pp_fraction": 1.0,
                   "recent.won": 1.0})
    values.update(changes)
    return PlayerReadiness(tuple(values[n] for n in READINESS_NAMES[1:]))


def menu():
    return _options([_story("s-fuji", "rescue_fuji"), _story("s-erika", "defeat_erika")])


def test_party_fit_needs_hp_no_faint_and_pp():
    assert party_fit(readiness())
    assert not party_fit(readiness(**{"current.hp_fraction": 0.4}))
    assert not party_fit(readiness(**{"current.fainted_fraction": 1 / 6}))
    assert not party_fit(readiness(**{"current.pp_fraction": 0.1}))
    assert party_fit(readiness(**{"current.pp_known": 0.0, "current.pp_fraction": 0.0}))
    assert not party_fit(None)


def test_detour_is_replaced_by_the_committed_story_executor(monkeypatch):
    monkeypatch.setattr(kc, "party_fit", lambda r: True)
    options = menu()
    parent = _parent(options, "private:restore")
    choice, receipt = commit_story_kind(parent, StoryKindCommitment("rescue_fuji"))
    assert isinstance(choice, RedLiveOptionChoice) and choice.mode is RedLiveOptionSelectionMode.MODEL_EXPLORATION
    assert choice.selected_candidate_index == _index(options, "s-fuji")
    assert choice.selected_binding.kind is GoalKind.ADVANCE_STORY
    assert choice.probabilities[choice.selected_candidate_index] == 1.0 and sum(choice.probabilities) == 1.0
    assert receipt["overridden"] and receipt["parent_selected_kind"] == GoalKind.RESTORE_TEAM.value
    assert receipt["goal_model_unchanged"] and not receipt["automatic_fit"]


def test_unfit_party_keeps_the_model_choice_and_says_so(monkeypatch):
    monkeypatch.setattr(kc, "party_fit", lambda r: False)
    options = menu()
    parent = _parent(options, "private:restore")
    choice, receipt = commit_story_kind(parent, StoryKindCommitment("rescue_fuji"))
    assert choice is parent and receipt["overridden"] is False and receipt["party_fit"] is False


def test_not_applicable_cases_pass_through(monkeypatch):
    monkeypatch.setattr(kc, "party_fit", lambda r: True)
    options = menu()
    story_parent = _parent(options, "s-erika")
    assert commit_story_kind(story_parent, StoryKindCommitment("rescue_fuji")) == (story_parent, None)
    detour = _parent(options, "private:restore")
    assert commit_story_kind(detour, None) == (detour, None)
    assert commit_story_kind(detour, StoryKindCommitment("not_offered")) == (detour, None)
    n = len(options.bindings)
    at = _index(options, "private:restore")
    safety = RedLiveOptionChoice(options, at, RedLiveOptionSelectionMode.DETERMINISTIC_SAFETY,
                                 tuple(None for _ in range(n)), tuple(float(i == at) for i in range(n)), 3, "b" * 64)
    assert commit_story_kind(safety, StoryKindCommitment("rescue_fuji")) == (safety, None)
    with pytest.raises(TypeError):
        commit_story_kind(detour, "rescue_fuji")


def test_scope_is_validated(tmp_path):
    from types import SimpleNamespace as N

    from pokemon_red_completion.red_autonomous_player import run_autonomous_options
    from pokemon_red_completion.red_story_kind_commitment import StoryKindCommitmentCarrier

    base = dict(model=N(feature_version=16), output=tmp_path / "out", snapshot=None, observe=None, seed=1,
                provenance=dict(source=dict(partition="development")), continuous_player=True)
    with pytest.raises(ValueError, match="kind-level story commitment requires milestone"):
        run_autonomous_options(**base, story_kind_commitment=True)
    with pytest.raises(ValueError, match="carrier requires the declared commitment"):
        run_autonomous_options(**base, story_milestone_commitment=True,
                               story_kind_commitment_carrier=StoryKindCommitmentCarrier())
    with pytest.raises(ValueError, match="carrier requires the declared commitment"):
        run_autonomous_options(**base, story_milestone_commitment=True, story_kind_commitment=True,
                               story_kind_commitment_carrier=object())
    assert not (tmp_path / "out").exists()


def test_declared_kind_commitment_requires_milestone_commitment_and_is_forwarded(monkeypatch):
    from types import SimpleNamespace as N

    import run_configured_red_player as script

    plan = dict(partition="development", goal_selection=dict(
        mode="greedy", reason="M0 kind commitment.", story_milestone_commitment=True, story_kind_commitment=True))
    assert script.declared_story_kind_commitment(plan) is True
    monkeypatch.setattr(script, "requires_compulsory_settlement", lambda _: False)
    monkeypatch.setattr(script, "declared_player_curriculum", lambda *_: None)
    options = script.native_player_options(plan, object(), [object()], N(native_callbacks=lambda: {}), refinement={})
    assert options["story_kind_commitment"] is True and options["story_milestone_commitment"] is True
    plan["goal_selection"]["story_kind_commitment"] = False
    off = script.native_player_options(plan, object(), [object()], N(native_callbacks=lambda: {}), refinement={})
    assert "story_kind_commitment" not in off
    assert script.declared_story_kind_commitment({}) is False
    for bad in (1, "yes", None):
        plan["goal_selection"]["story_kind_commitment"] = bad
        with pytest.raises(ValueError, match="explicit boolean"):
            script.declared_story_kind_commitment(plan)
    plan["goal_selection"].update(story_kind_commitment=True, story_milestone_commitment=False)
    with pytest.raises(ValueError, match="requires milestone"):
        script.declared_story_kind_commitment(plan)
    plan["goal_selection"]["story_milestone_commitment"] = True
    plan["partition"] = "train"
    with pytest.raises(ValueError, match="DEVELOPMENT"):
        script.declared_story_kind_commitment(plan)
    holder = {}
    carrier = script._story_kind_commitment_carrier(holder)
    assert script._story_kind_commitment_carrier(holder) is carrier and carrier.current is None
    carrier.current = StoryKindCommitment("rescue_fuji")
    assert carrier.document()["objective_ref"] == "rescue_fuji"


def outcome(ok=True, completed=()):
    return dict(verification="succeeded" if ok else "failed", error_type=None if ok else "RouteExecutionError",
                after=dict(completed_objectives=list(completed)))


def test_lifecycle_starts_on_success_resets_and_releases_after_two_failures():
    options = menu()
    fuji = options.bindings[_index(options, "s-fuji")]
    heal = options.bindings[_index(options, "private:restore")]
    assert commitment_after_outcome(None, fuji, outcome(ok=False)) is None
    c = commitment_after_outcome(None, fuji, outcome())
    assert c == StoryKindCommitment("rescue_fuji")
    assert commitment_after_outcome(c, heal, outcome()) == c
    c1 = commitment_after_outcome(c, fuji, outcome(ok=False))
    assert c1.consecutive_failures == 1
    assert commitment_after_outcome(c1, fuji, outcome()).consecutive_failures == 0
    assert commitment_after_outcome(c1, fuji, outcome(ok=False)) is None
    assert commitment_after_outcome(c, fuji, outcome(completed=["rescue_fuji"])) is None
    assert commitment_after_outcome(c, heal, outcome(completed=["rescue_fuji"])) is None
    erika = options.bindings[_index(options, "s-erika")]
    assert commitment_after_outcome(c, erika, outcome()) == StoryKindCommitment("defeat_erika")
    assert commitment_after_outcome(c, erika, outcome(ok=False)) == c
    assert commitment_after_choice(c, dict(overridden=True)).overrides == 1
    assert commitment_after_choice(c, dict(overridden=False)) == c
    with pytest.raises(ValueError):
        StoryKindCommitment("x", consecutive_failures=2)


def test_verified_story_battle_loss_releases_support_despite_healed_blackout():
    options=menu();fuji=options.bindings[_index(options,"s-fuji")]
    c=StoryKindCommitment("rescue_fuji",overrides=7)
    loss=dict(verification="failed",error_type=None,ordinary_setback=True,failure_reason="resource_lost",
              evidence=dict(battle=dict(episode=dict(battle_won=False))),after=dict(completed_objectives=[]))
    assert commitment_after_outcome(c,fuji,loss) is None
    # With no support commitment, the very next model choice stays authoritative.
    parent=_parent(options,"private:restore")
    assert commit_story_kind(parent,None)==(parent,None)
    erika=options.bindings[_index(options,"s-erika")]
    assert commitment_after_outcome(c,erika,loss)==c

@pytest.mark.parametrize("change", [dict(ordinary_setback=False),dict(error_type="UnknownNativeFailure"),
                                   dict(verification="succeeded"),dict(failure_reason="no_progress"),
                                   dict(evidence={}),dict(evidence=dict(battle=dict(episode=dict(battle_won=True))))])
def test_incomplete_or_nonloss_evidence_does_not_trigger_blackout_release(change):
    options=menu();fuji=options.bindings[_index(options,"s-fuji")]
    loss=dict(verification="failed",error_type=None,ordinary_setback=True,failure_reason="resource_lost",
              evidence=dict(battle=dict(episode=dict(battle_won=False))),after=dict(completed_objectives=[]))
    assert commitment_after_outcome(StoryKindCommitment("rescue_fuji"),fuji,{**loss,**change}) is not None
