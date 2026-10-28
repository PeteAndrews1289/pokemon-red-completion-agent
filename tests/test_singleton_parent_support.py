"""Explicit single observed combat-parent support; fake port, no fit/native gameplay."""
from dataclasses import replace
import json
import pytest

from test_consequence_v15_vertical import (
    dispatch_head, unbound_hierarchy_args,
)
from test_living_dex_option_value import _features
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionAvailability, LivingDexOptionCandidate,
    LivingDexOptionKind, LivingDexOptionValueModel,
)
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.red_live_option_menu import (
    RedLiveSupplementalOption, RedLiveOptionSelectionMode,
)
import pokemon_red_completion.red_consequence_choice as composition
import pokemon_red_completion.red_native_player as native


def four_dose_args(tmp_path, monkeypatch, *, prefer="kind.develop"):
    args, state = unbound_hierarchy_args(tmp_path, monkeypatch, second_parent=False)
    preparation = args["observe_preparations"]
    def supplements(rt, actions, observation, bindings):
        dose = next(b for b in bindings.bindings if b.kind is GoalKind.DEVELOP_TEAM)
        return tuple(RedLiveSupplementalOption(
            replace(dose, binding_ref="observed-dose-" + str(i)),
            LivingDexOptionCandidate("observed-dose-" + str(i),
                _features(LivingDexOptionKind.DEVELOP, completion=0, unlock=0, effort=.2 + i * .05),
                LivingDexOptionAvailability.AVAILABLE),
        ) for i in range(1, 4))
    def preparations(*a, **kw):
        facts = preparation(*a, **kw)["train"]
        return {"train": facts, **{"observed-dose-" + str(i): facts for i in range(1, 4)}}
    args.update(enumerate_supplements=supplements, observe_preparations=preparations,
        consequence_head=dispatch_head(prefer=prefer), allow_singleton_parent_support=True)
    return args, state


@pytest.mark.parametrize("prefer", ["kind.develop", "kind.unlock_access"])
def test_real_four_dose_one_combat_shape_has_support_parent_and_one_child_query(tmp_path, monkeypatch, prefer):
    args, state = four_dose_args(tmp_path, monkeypatch, prefer=prefer)
    monkeypatch.setattr(LivingDexOptionValueModel, "scores",
        lambda *a: pytest.fail("sole observed parent is support, never a model query"))
    choices = []
    select = composition.select_branch_recovery_live_option
    def capture(*a, **kw):
        choice = select(*a, **kw)
        choices.append(choice)
        return choice
    monkeypatch.setattr(composition, "select_branch_recovery_live_option", capture)
    result = native.run_native_continuous_player(**args)
    assert result["executed_decisions"] == result["model_decisions"] == 1
    assert result["strategic_policy_queries"] == 1
    choice = choices[0]
    assert len(choice.options.bindings) == 5
    assert sum(b.kind is GoalKind.DEVELOP_TEAM for b in choice.options.bindings) == 4
    assert sum(b.kind is GoalKind.ADVANCE_STORY for b in choice.options.bindings) == 1
    assert all(c.challenge is None and c.matchup is None
               for c in choice.options.menu.candidates if c.preparation is not None)
    parent = choice.branch_recovery.parent
    assert parent.mode is RedLiveOptionSelectionMode.FORCED_SINGLETON_SUPPORT
    assert parent.scores == (None,) * 5
    assert parent.selected_binding.story_objective_ref == "private-combat-goal"
    receipt = choice.public_dict()["branch_recovery"]
    assert receipt["parent_authority"] == "forced_singleton_support"
    assert receipt["parent_selection_rule"] == "forced_singleton_support"
    assert receipt["parent_model_queries"] == 0
    assert receipt["child_model_queries"] == receipt["model_queries"] == 1
    assert choice.branch_recovery.child is not None
    if prefer == "kind.develop":
        assert state["trained"] and not state["challenge"]
        assert composition.selected_preparation_parent(choice) is parent.selected_binding
    else:
        assert state["challenge"] and not state["trained"]
        assert composition.selected_preparation_parent(choice) is None
    plan = json.loads((args["output"] / "native-plan.json").read_text())
    assert plan["allow_singleton_parent_support"] is True
    decision = json.loads((args["output"] / "episode/step-000/decision.json").read_text())
    assert decision["branch_recovery"]["parent_model_queries"] == 0
    assert not args["emulator"].pressed_buttons


@pytest.mark.parametrize("fault", ["flag", "parent_index", "child_omitted", "scope", "parent_mode", "seed", "binding_object"])
def test_forced_parent_receipt_cannot_be_relabelled_or_rebound(tmp_path, monkeypatch, fault):
    args, _ = four_dose_args(tmp_path, monkeypatch)
    choices = []
    select = composition.select_branch_recovery_live_option
    def capture(*a, **kw):
        choice = select(*a, **kw)
        choices.append(choice)
        return choice
    monkeypatch.setattr(composition, "select_branch_recovery_live_option", capture)
    native.run_native_continuous_player(**args)
    choice = choices[0]
    receipt = choice.branch_recovery
    with pytest.raises(ValueError):
        if fault == "flag":
            replace(choice, branch_recovery=replace(receipt, allow_singleton_parent_support=False))
        elif fault == "parent_index":
            dose = next(i for i, b in enumerate(choice.options.bindings) if b.kind is GoalKind.DEVELOP_TEAM)
            parent = replace(receipt.parent, selected_candidate_index=dose,
                probabilities=tuple(float(i == dose) for i in range(5)))
            replace(choice, branch_recovery=replace(receipt, parent=parent))
        elif fault == "child_omitted":
            replace(choice, branch_recovery=replace(receipt, child=None))
        elif fault == "scope":
            replace(choice, branch_recovery=replace(receipt, objective_ref="wrong-combat"))
        elif fault == "parent_mode":
            replace(choice, branch_recovery=replace(receipt, parent=replace(
                receipt.parent, mode=RedLiveOptionSelectionMode.DETERMINISTIC_SAFETY)))
        elif fault == "seed":
            replace(choice, branch_recovery=replace(receipt, parent=replace(
                receipt.parent, seed=receipt.parent.seed + 1)))
        else:
            at = receipt.parent.selected_candidate_index
            copied = replace(receipt.parent.selected_binding)
            parent_options = replace(receipt.parent.options, bindings=tuple(
                copied if i == at else b for i, b in enumerate(receipt.parent.options.bindings)))
            replace(choice, branch_recovery=replace(receipt, parent=replace(
                receipt.parent, options=parent_options)))


@pytest.mark.parametrize("fault", ["noncombat", "unobserved", "opposition_unknown", "wrong_scope"])
def test_singleton_support_refuses_missing_actual_observed_combat(tmp_path, monkeypatch, fault):
    args, state = four_dose_args(tmp_path, monkeypatch)
    observe = args["observe_challenges"]
    def challenges(*a, **kw):
        data = observe(*a, **kw)
        if fault == "unobserved":
            return {}
        if fault == "noncombat":
            return {key: OptionChallenge(False, False, 0., 0., 0.) for key in data}
        return {key: OptionChallenge(True, False, 0., 0., 0.) for key in data}
    if fault != "wrong_scope":
        args["observe_challenges"] = challenges
        args["observe_matchups"] = None
    else:
        args["consequence_objective_ref"] = "wrong-combat"
        args["consequence_challenge_ref"] = "wrong-combat"
    monkeypatch.setattr(LivingDexOptionValueModel, "scores",
        lambda *a: pytest.fail("unsupported parent must not query model"))
    result = native.run_native_continuous_player(**args)
    assert result["executed_decisions"] == 0
    assert result["stop_reason"] == "consequence_context_unavailable"
    assert not state["trained"] and not state["challenge"]
    assert args["emulator"].frame_count == 0


@pytest.mark.parametrize("fault", ["untyped", "no_deferral", "no_permission", "train", "no_head"])
def test_singleton_support_needs_explicit_prospective_authority(tmp_path, monkeypatch, fault):
    args, state = four_dose_args(tmp_path, monkeypatch)
    if fault == "untyped":
        args["allow_singleton_parent_support"] = 1
    elif fault == "no_deferral":
        args["defer_unbound_preparation"] = False
    elif fault == "no_permission":
        args["allow_greedy_branch_recovery"] = False
    elif fault == "train":
        args["source"]["partition"] = "train"
    else:
        args["consequence_head"] = None
    with pytest.raises((TypeError, ValueError)):
        native.run_native_continuous_player(**args)
    assert args["emulator"].frame_count == 0
    assert not state["trained"] and not state["challenge"]


def test_default_real_menu_still_refuses_without_new_support_opt_in(tmp_path, monkeypatch):
    args, state = four_dose_args(tmp_path, monkeypatch)
    args["allow_singleton_parent_support"] = False
    result = native.run_native_continuous_player(**args)
    assert result["executed_decisions"] == 0 and result["strategic_policy_queries"] == 0
    assert args["emulator"].frame_count == 0
    assert not state["trained"] and not state["challenge"]




def test_singleton_opt_in_keeps_mandatory_safety_before_any_parent_or_child_query(tmp_path, monkeypatch):
    from test_red_branch_recovery import menu, greedy_native_args
    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
    from pokemon_red_completion.player_challenge_consequence import ChallengeConsequenceHead
    options, _, _, runtime = menu(tmp_path, monkeypatch)
    keep = tuple(i for i, b in enumerate(options.bindings)
                 if b.kind in (GoalKind.DEVELOP_TEAM, GoalKind.RESTORE_TEAM))
    bindings = tuple(options.bindings[i] for i in keep)
    options = replace(options,
        original_bindings=GoalBindingSet(tuple(b.opportunity for b in bindings), bindings),
        situation=replace(options.situation, safety_pressure=1.),
        menu=replace(options.menu, candidates=tuple(
            replace(options.menu.candidates[i], challenge=None) if options.bindings[i].kind is GoalKind.DEVELOP_TEAM
            else options.menu.candidates[i] for i in keep)),
        bindings=bindings, ordinary_binding_refs=frozenset(b.binding_ref for b in bindings))
    args, _ = greedy_native_args(tmp_path / "model", monkeypatch)
    monkeypatch.setattr(LivingDexOptionValueModel, "scores",
        lambda *a: pytest.fail("mandatory safety must precede parent support"))
    monkeypatch.setattr(ChallengeConsequenceHead, "scores",
        lambda *a, **kw: pytest.fail("mandatory safety must precede child model"))
    choice = composition.select_branch_recovery_live_option(
        args["model"], options, args["consequence_head"], objective_ref="private-combat-goal",
        seed=1, greedy_selection=True, defer_unbound_preparation=True,
        allow_singleton_parent_support=True)
    receipt = choice.public_dict()["branch_recovery"]
    assert choice.mode is RedLiveOptionSelectionMode.DETERMINISTIC_SAFETY
    assert choice.selected_binding.kind is GoalKind.RESTORE_TEAM
    assert receipt["parent_authority"] == "deterministic_safety"
    assert receipt["parent_model_queries"] == receipt["child_model_queries"] == receipt["model_queries"] == 0
    assert not runtime.recorder.trace


def test_support_validator_refuses_two_available_parents_instead_of_guessing(tmp_path, monkeypatch):
    from test_red_branch_recovery import menu
    options, at, _, runtime = menu(tmp_path, monkeypatch)
    other = next(i for i, b in enumerate(options.bindings)
                 if b.story_objective_ref == "private-travel-goal")
    options = replace(options, menu=replace(options.menu, candidates=tuple(
        replace(c, challenge=options.menu.candidates[at].challenge) if i == other
        else replace(c, challenge=None) if c.preparation is not None else c
        for i, c in enumerate(options.menu.candidates))))
    with pytest.raises(ValueError, match="exactly one"):
        composition._sole_observed_combat_parent(options,
            ("private-combat-goal", "private-travel-goal"))
    assert not runtime.recorder.trace



def test_forced_receipt_cannot_omit_direct_while_retaining_four_valid_doses(tmp_path, monkeypatch):
    args, _ = four_dose_args(tmp_path, monkeypatch)
    choices = []
    select = composition.select_branch_recovery_live_option
    def capture(*a, **kw):
        choice = select(*a, **kw)
        choices.append(choice)
        return choice
    monkeypatch.setattr(composition, "select_branch_recovery_live_option", capture)
    native.run_native_continuous_player(**args)
    choice = choices[0]
    receipt = choice.branch_recovery
    original_child = receipt.child
    keep = tuple(i for i, b in enumerate(original_child.options.bindings)
                 if b.kind is GoalKind.DEVELOP_TEAM)
    assert len(keep) == 4
    bindings = tuple(original_child.options.bindings[i] for i in keep)
    omitted = replace(original_child.options, bindings=bindings,
        menu=replace(original_child.options.menu, candidates=tuple(
            original_child.options.menu.candidates[i] for i in keep)),
        ordinary_binding_refs=original_child.options.ordinary_binding_refs & {
            b.binding_ref for b in bindings})
    # Build a valid numerical child with consistent recomputed scores. This
    # bypasses no identity/kind/workload checks, but loses the direct alternative.
    child = composition.select_consequence_live_option(omitted, args["consequence_head"],
        challenge_ref=receipt.parent.selected_binding.story_objective_ref, seed=choice.seed)
    scores = {b.binding_ref: score for b, score in zip(child.options.bindings, child.scores, strict=True)}
    with pytest.raises(ValueError, match="incomparable challenge contexts"):
        replace(choice,
            selected_candidate_index=next(i for i, b in enumerate(choice.options.bindings)
                                          if b is child.selected_binding),
            scores=tuple(scores.get(b.binding_ref) for b in choice.options.bindings),
            probabilities=tuple(float(b is child.selected_binding) for b in choice.options.bindings),
            branch_recovery=replace(receipt, child=child))

