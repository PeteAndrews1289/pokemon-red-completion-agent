"""Synthetic composition tests,not native learning evidence."""

import json
from dataclasses import replace

import pytest
from test_native_challenge_consequence import harness, session
from test_red_consequence_choice import progress_head, provisional_args

import pokemon_red_completion.red_consequence_choice as composition
import pokemon_red_completion.red_native_player as native
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.red_live_option_menu import (
    RedLiveOptionChoice,
    RedLiveOptionSelectionMode,
)


def menu(tmp_path, monkeypatch):
    args, state = harness(tmp_path, monkeypatch, fault="win")
    runtime = session(args)
    options = runtime.observe(0)
    at = next(i for i, b in enumerate(options.bindings) if b.kind is GoalKind.ADVANCE_STORY)
    misty = replace(options.binding(at), story_objective_ref="private-combat-goal")
    bill = replace(
        misty, binding_ref="private-other-branch", story_objective_ref="private-travel-goal"
    )
    candidates = list(options.menu.candidates)
    candidates.append(
        replace(
            candidates[at],
            binding_ref=bill.binding_ref,
            challenge=OptionChallenge(False, False, 0.0, 0.0, 0.0),
        )
    )
    bindings = tuple(misty if i == at else b for i, b in enumerate(options.bindings)) + (bill,)
    restored = replace(
        misty,
        binding_ref="private-restoration",
        kind=GoalKind.RESTORE_TEAM,
        story_objective_ref=None,
    )
    candidates.append(
        replace(
            candidates[at],
            binding_ref=restored.binding_ref,
            features=replace(candidates[at].features, kind=LivingDexOptionKind.RESTORE),
            preparation=None,
        )
    )
    bindings += (restored,)
    return (
        replace(
            options, bindings=bindings, menu=replace(options.menu, candidates=tuple(candidates))
        ),
        at,
        state,
        runtime,
    )


def parent_choice(options, at, model, seed=1, mode=RedLiveOptionSelectionMode.MODEL_EXPLORATION):
    return RedLiveOptionChoice(
        options,
        at,
        mode,
        tuple(
            0.0 if mode is RedLiveOptionSelectionMode.MODEL_EXPLORATION
            else float(i == at) if mode is RedLiveOptionSelectionMode.MODEL_GREEDY
            else None
            for i, _ in enumerate(options.bindings)
        ),
        tuple(float(i == at) for i in range(len(options.bindings))),
        seed,
        model.model_sha256,
    )


@pytest.mark.parametrize(
    "feature,kind",
    [("kind.develop", GoalKind.DEVELOP_TEAM), ("kind.unlock_access", GoalKind.ADVANCE_STORY)],
)
def test_selected_combat_branch_is_refined_by_existing_head(tmp_path, monkeypatch, feature, kind):
    options, at, state, runtime = menu(tmp_path, monkeypatch)
    args, _ = provisional_args(tmp_path / "model", monkeypatch)
    calls = []

    def branch(model, observed, **kw):
        calls.append(observed)
        return parent_choice(observed, at, model, seed=kw["seed"])

    monkeypatch.setattr(composition, "select_red_live_option", branch)
    choice = composition.select_branch_recovery_live_option(
        args["model"], options, progress_head(feature), objective_ref="private-combat-goal", seed=1
    )
    assert calls == [options] and choice.selected_binding.kind is kind
    assert choice.branch_recovery.parent.selected_binding is options.binding(at)
    assert all(
        b.story_objective_ref != "private-travel-goal"
        for b in choice.branch_recovery.child.options.bindings
    )
    receipt = choice.public_dict()["branch_recovery"]
    assert receipt["model_queries"] == 2 and not receipt["score_blending"]
    assert "private-combat-goal" not in str(receipt)
    assert not runtime.recorder.trace and not state["trained"] and not state["challenge"]


@pytest.mark.parametrize(
    "kind", [GoalKind.ADVANCE_STORY, GoalKind.DEVELOP_TEAM, GoalKind.RESTORE_TEAM]
)
def test_other_branch_or_nonstory_selection_is_not_substituted(tmp_path, monkeypatch, kind):
    options, _, _, runtime = menu(tmp_path, monkeypatch)
    args, _ = provisional_args(tmp_path / "model", monkeypatch)
    at = (
        next(
            i
            for i, b in enumerate(options.bindings)
            if b.story_objective_ref == "private-travel-goal"
        )
        if kind is GoalKind.ADVANCE_STORY
        else next(i for i, b in enumerate(options.bindings) if b.kind is kind)
    )
    monkeypatch.setattr(
        composition,
        "select_red_live_option",
        lambda model, observed, **kw: parent_choice(observed, at, model),
    )
    choice = composition.select_branch_recovery_live_option(
        args["model"],
        options,
        progress_head("kind.develop"),
        objective_ref="private-combat-goal",
        seed=1,
    )
    assert choice.selected_binding is options.binding(at)
    assert choice.branch_recovery.child is None
    assert choice.public_dict()["branch_recovery"]["model_queries"] == 1
    assert not runtime.recorder.trace


def test_safety_remains_nonmodel_and_is_not_refined(tmp_path, monkeypatch):
    options, at, _, _ = menu(tmp_path, monkeypatch)
    args, _ = provisional_args(tmp_path / "model", monkeypatch)
    monkeypatch.setattr(
        composition,
        "select_red_live_option",
        lambda model, observed, **kw: parent_choice(
            observed, at, model, mode=RedLiveOptionSelectionMode.DETERMINISTIC_SAFETY
        ),
    )
    choice = composition.select_branch_recovery_live_option(
        args["model"], options, progress_head(), objective_ref="private-combat-goal", seed=1
    )
    assert choice.mode is RedLiveOptionSelectionMode.DETERMINISTIC_SAFETY
    assert choice.branch_recovery.child is None
    assert choice.public_dict()["branch_recovery"]["model_queries"] == 0


def test_no_local_recovery_alternative_keeps_learned_parent_choice(tmp_path, monkeypatch):
    options, _, _, _ = menu(tmp_path, monkeypatch)
    args, _ = provisional_args(tmp_path / "model", monkeypatch)
    indices = tuple(i for i, b in enumerate(options.bindings) if b.kind is GoalKind.ADVANCE_STORY)
    options = replace(
        options,
        menu=replace(options.menu, candidates=tuple(options.menu.candidates[i] for i in indices)),
        bindings=tuple(options.bindings[i] for i in indices),
        ordinary_binding_refs=options.ordinary_binding_refs
        & {options.bindings[i].binding_ref for i in indices},
    )
    at = next(
        i for i, b in enumerate(options.bindings) if b.story_objective_ref == "private-combat-goal"
    )
    monkeypatch.setattr(
        composition,
        "select_red_live_option",
        lambda model, observed, **kw: parent_choice(observed, at, model, seed=kw["seed"]),
    )
    monkeypatch.setattr(
        composition,
        "select_consequence_live_option",
        lambda *a, **kw: pytest.fail("No recovery comparison exists"),
    )
    choice = composition.select_branch_recovery_live_option(
        args["model"],
        options,
        progress_head("kind.develop"),
        objective_ref="private-combat-goal",
        seed=1,
    )
    assert choice.selected_binding is options.binding(at)
    assert choice.branch_recovery.child is None
    assert choice.public_dict()["branch_recovery"]["model_queries"] == 1


@pytest.mark.parametrize("keep_dose", [False, True])
def test_owned_move_without_dose_facts_stays_in_parent_not_level_head(
    tmp_path, monkeypatch, keep_dose,
):
    options, at, _, _ = menu(tmp_path, monkeypatch)
    args, _ = provisional_args(tmp_path / "model", monkeypatch)
    dose = next(i for i, b in enumerate(options.bindings) if b.kind is GoalKind.DEVELOP_TEAM)
    machine = replace(options.binding(dose), binding_ref="private-owned-machine")
    machine_candidate = replace(
        options.menu.candidates[dose], binding_ref=machine.binding_ref,
        preparation=None, challenge=OptionChallenge(False, False, 0.0, 0.0, 0.0),
    )
    indices = tuple(
        i for i, b in enumerate(options.bindings)
        if b.kind is GoalKind.ADVANCE_STORY or keep_dose and i == dose
    )
    options = replace(
        options,
        bindings=tuple(options.binding(i) for i in indices) + (machine,),
        menu=replace(options.menu, candidates=tuple(
            options.menu.candidates[i] for i in indices
        ) + (machine_candidate,)),
        ordinary_binding_refs=options.ordinary_binding_refs & {
            options.binding(i).binding_ref for i in indices
        },
    )
    at = next(i for i, b in enumerate(options.bindings)
              if b.story_objective_ref == "private-combat-goal")
    monkeypatch.setattr(composition, "select_red_live_option",
        lambda model, observed, **kw: parent_choice(observed, at, model, seed=kw["seed"]))
    choice = composition.select_branch_recovery_live_option(
        args["model"], options, progress_head("kind.develop"),
        objective_ref="private-combat-goal", seed=1,
    )
    assert machine in choice.branch_recovery.parent.options.bindings
    if keep_dose:
        assert choice.branch_recovery.child is not None
        assert machine not in choice.branch_recovery.child.options.bindings
        assert choice.selected_binding.kind is GoalKind.DEVELOP_TEAM
    else:
        assert choice.branch_recovery.child is None
        assert choice.selected_binding is options.binding(at)
    # If the full model selects the machine, the dose head never substitutes it.
    monkeypatch.setattr(composition, "select_red_live_option",
        lambda model, observed, **kw: parent_choice(
            observed, len(observed.bindings) - 1, model, seed=kw["seed"]))
    move_choice = composition.select_branch_recovery_live_option(
        args["model"], options, progress_head("kind.develop"),
        objective_ref="private-combat-goal", seed=2,
    )
    assert move_choice.selected_binding is machine
    assert move_choice.branch_recovery.child is None


def test_receipt_cannot_change_unselected_branch_or_scores(tmp_path, monkeypatch):
    options, at, _, _ = menu(tmp_path, monkeypatch)
    args, _ = provisional_args(tmp_path / "model", monkeypatch)
    monkeypatch.setattr(
        composition,
        "select_red_live_option",
        lambda model, observed, **kw: parent_choice(observed, at, model),
    )
    choice = composition.select_branch_recovery_live_option(
        args["model"],
        options,
        progress_head("kind.develop"),
        objective_ref="private-combat-goal",
        seed=1,
    )
    with pytest.raises(ValueError):
        replace(
            choice,
            selected_candidate_index=len(options.bindings) - 1,
            probabilities=tuple(
                float(i == len(options.bindings) - 1) for i in range(len(options.bindings))
            ),
        )
    with pytest.raises(ValueError, match="scores"):
        replace(choice, scores=tuple(0.0 for _ in options.bindings))


def test_native_branch_dispatch_records_both_model_queries(tmp_path, monkeypatch):
    args, state = provisional_args(tmp_path, monkeypatch)
    original = args["enumerate_bindings"]

    def enum(*a, **kw):
        observed = original(*a, **kw)
        return replace(
            observed,
            bindings=tuple(
                replace(b, story_objective_ref="private-combat-goal")
                if b.kind is GoalKind.ADVANCE_STORY
                else b
                for b in observed.bindings
            ),
        )

    args.update(enumerate_bindings=enum, consequence_objective_ref="private-combat-goal")
    monkeypatch.setattr(
        composition,
        "select_red_live_option",
        lambda model, observed, **kw: parent_choice(
            observed,
            next(i for i, b in enumerate(observed.bindings) if b.kind is GoalKind.ADVANCE_STORY),
            model,
            seed=kw["seed"],
        ),
    )
    result = native.run_native_continuous_player(**args)
    assert result["model_decisions"] == 1 and result["strategic_policy_queries"] == 2
    assert state["challenge"] and not state["trained"]
    assert result["teacher_actions"] == 0 and result[
        "model_sha256"
    ] == composition.branch_recovery_identity(
        args["model"].model_sha256, args["consequence_head"].model_sha256, "private-combat-goal"
    )


def test_lone_branch_dispatch_refuses_before_claim_or_input(tmp_path, monkeypatch):
    args, state = provisional_args(tmp_path, monkeypatch)
    args.update(
        consequence_head=None,
        consequence_challenge_ref=None,
        consequence_objective_ref="private-combat-goal",
    )
    with pytest.raises(ValueError, match="explicit consequence"):
        native.run_native_continuous_player(**args)
    assert not args["output"].exists() and args["emulator"].frame_count == 0
    assert not state["trained"] and not state["challenge"]


@pytest.mark.parametrize("feature", ["kind.develop", "kind.unlock_access"])
def test_highest_score_parent_can_refine_only_its_selected_combat_branch(
    tmp_path, monkeypatch, feature,
):
    options, at, _, runtime = menu(tmp_path, monkeypatch)
    args, _ = provisional_args(tmp_path / "model", monkeypatch)

    def branch(model, observed, **kw):
        assert kw["greedy_selection"] is True and observed is options
        return parent_choice(observed, at, model, seed=kw["seed"],
                             mode=RedLiveOptionSelectionMode.MODEL_GREEDY)

    monkeypatch.setattr(composition, "select_red_live_option", branch)
    choice = composition.select_branch_recovery_live_option(
        args["model"], options, progress_head(feature),
        objective_ref="private-combat-goal", seed=1, greedy_selection=True,
    )
    receipt = choice.public_dict()["branch_recovery"]
    assert receipt["branch"]["mode"] == "model_greedy"
    assert receipt["model_queries"] == 2 and not receipt["score_blending"]
    assert receipt["parent_selection_rule"] == "maximum_score_with_seeded_ties"
    assert choice.branch_recovery.child is not None
    assert choice.options is options and not runtime.recorder.trace
    assert all(b.story_objective_ref != "private-travel-goal"
               for b in choice.branch_recovery.child.options.bindings)
    assert choice.model_sha256 == composition.branch_recovery_identity(
        args["model"].model_sha256, progress_head(feature).model_sha256,
        "private-combat-goal", greedy_selection=True,
    )
    with pytest.raises(ValueError):
        replace(choice, branch_recovery=replace(choice.branch_recovery, greedy_selection=False))


@pytest.mark.parametrize("second", [False, True])
def test_declared_branch_set_refines_either_selected_combat_without_switching_branch(
    tmp_path, monkeypatch, second,
):
    options, first, _, runtime = menu(tmp_path, monkeypatch)
    other = next(i for i, b in enumerate(options.bindings)
                 if b.story_objective_ref == "private-travel-goal")
    second_ref = "private-second-combat-goal"
    bindings = tuple(replace(b, story_objective_ref=second_ref) if i == other else b
                     for i, b in enumerate(options.bindings))
    candidates = tuple(replace(c, challenge=options.menu.candidates[first].challenge)
                       if i == other else c for i, c in enumerate(options.menu.candidates))
    options = replace(options, bindings=bindings,
                      menu=replace(options.menu, candidates=candidates))
    args, _ = provisional_args(tmp_path / "model", monkeypatch)
    selected = other if second else first
    calls = []

    def branch(model, observed, **kw):
        calls.append(observed)
        return parent_choice(observed, selected, model, seed=kw["seed"],
                             mode=RedLiveOptionSelectionMode.MODEL_GREEDY)

    monkeypatch.setattr(composition, "select_red_live_option", branch)
    scope = ("private-combat-goal", second_ref)
    choice = composition.select_branch_recovery_live_option(
        args["model"], options, progress_head("kind.develop"),
        objective_ref=scope, seed=1, greedy_selection=True,
    )
    assert calls == [options]
    assert choice.selected_binding.kind is GoalKind.DEVELOP_TEAM
    receipt = choice.branch_recovery
    assert receipt.parent.selected_binding is options.binding(selected)
    assert receipt.child is not None
    assert [b for b in receipt.child.options.bindings if b.kind is GoalKind.ADVANCE_STORY] == [
        options.binding(selected)
    ]
    assert options.binding(first if second else other) in receipt.parent.options.bindings
    public = choice.public_dict()["branch_recovery"]
    assert public["model_queries"] == 2 and public["declared_branch_count"] == 2
    assert all(ref not in str(public) for ref in scope)
    assert not runtime.recorder.trace


@pytest.mark.parametrize("scope", [(), ("only",), ("z", "a"), ("a", "a"),
                                   ("a", " "), ["a", "b"], ("a", 1)])
def test_branch_set_rejects_noncanonical_or_untyped_scope(scope):
    with pytest.raises(ValueError):
        composition.branch_recovery_identity("0" * 64, "1" * 64, scope,
                                             greedy_selection=True)


def test_branch_set_cannot_silently_enable_exploration_or_unbound_challenge():
    scope = ("a", "b")
    with pytest.raises(ValueError, match="highest-score"):
        composition.branch_recovery_identity("0" * 64, "1" * 64, scope)
    assert composition.branch_recovery_scope_ref("a") == "a"
    assert composition.branch_recovery_scope_ref(scope).startswith("pokemon.red:readiness-scope:")


@pytest.mark.parametrize("kind", [GoalKind.DEVELOP_TEAM, GoalKind.RESTORE_TEAM,
                                  GoalKind.ADVANCE_STORY])
def test_highest_score_other_branches_keep_parent_choice_and_one_query(
    tmp_path, monkeypatch, kind,
):
    options, _, _, _ = menu(tmp_path, monkeypatch)
    args, _ = provisional_args(tmp_path / "model", monkeypatch)
    at = next(i for i, b in enumerate(options.bindings) if b.kind is kind
              and (kind is not GoalKind.ADVANCE_STORY
                   or b.story_objective_ref == "private-travel-goal"))
    monkeypatch.setattr(composition, "select_red_live_option", lambda model, observed, **kw:
                        parent_choice(observed, at, model, seed=kw["seed"],
                                      mode=RedLiveOptionSelectionMode.MODEL_GREEDY))
    choice = composition.select_branch_recovery_live_option(
        args["model"], options, progress_head(), objective_ref="private-combat-goal",
        seed=1, greedy_selection=True,
    )
    assert choice.selected_binding is options.binding(at)
    assert choice.mode is RedLiveOptionSelectionMode.MODEL_GREEDY
    assert choice.branch_recovery.child is None
    assert choice.public_dict()["branch_recovery"]["model_queries"] == 1


def test_highest_score_safety_is_not_a_model_query_or_child_selection(tmp_path, monkeypatch):
    options, at, _, _ = menu(tmp_path, monkeypatch)
    args, _ = provisional_args(tmp_path / "model", monkeypatch)
    monkeypatch.setattr(composition, "select_red_live_option", lambda model, observed, **kw:
                        parent_choice(observed, at, model, seed=kw["seed"],
                                      mode=RedLiveOptionSelectionMode.DETERMINISTIC_SAFETY))
    choice = composition.select_branch_recovery_live_option(
        args["model"], options, progress_head(), objective_ref="private-combat-goal",
        seed=1, greedy_selection=True,
    )
    assert choice.mode is RedLiveOptionSelectionMode.DETERMINISTIC_SAFETY
    assert choice.branch_recovery.child is None
    assert choice.public_dict()["branch_recovery"]["model_queries"] == 0


def test_default_policy_identity_stays_exact_and_greedy_rule_is_distinct():
    from pokemon_red_completion.provenance import canonical_sha256

    old = composition.branch_recovery_identity("a" * 64, "b" * 64, "private-goal")
    assert old == canonical_sha256(dict(schema="pokemon.red.branch-recovery-policy.v1",
        branch_sha256="a" * 64, head_sha256="b" * 64, objective_ref="private-goal"))
    assert old != composition.branch_recovery_identity(
        "a" * 64, "b" * 64, "private-goal", greedy_selection=True)


def greedy_native_args(tmp_path, monkeypatch):
    args, state = provisional_args(tmp_path, monkeypatch)
    old = args["enumerate_bindings"]

    def enum(*a, **kw):
        observed = old(*a, **kw)
        return replace(observed, bindings=tuple(
            replace(b, story_objective_ref="private-combat-goal")
            if b.kind is GoalKind.ADVANCE_STORY else b for b in observed.bindings))

    args.update(enumerate_bindings=enum, consequence_objective_ref="private-combat-goal",
                greedy_selection=True, allow_greedy_branch_recovery=True,
                source={**args["source"], "experiment_sha256": "b" * 64})
    return args, state


def preparation_parent_menu(tmp_path, monkeypatch):
    options, story, state, runtime = menu(tmp_path, monkeypatch)
    dose = next(i for i, b in enumerate(options.bindings) if b.kind is GoalKind.DEVELOP_TEAM)
    candidates = tuple(
        replace(c, challenge=options.menu.candidates[story].challenge) if i == dose else c
        for i, c in enumerate(options.menu.candidates)
    )
    options = replace(options, menu=replace(options.menu, candidates=candidates))
    args, _ = provisional_args(tmp_path / "model", monkeypatch)
    monkeypatch.setattr(composition, "select_red_live_option", lambda model, observed, **kw:
                        parent_choice(observed, dose, model, seed=kw["seed"],
                                      mode=RedLiveOptionSelectionMode.MODEL_GREEDY))
    return args["model"], options, dose, story, state, runtime


@pytest.mark.parametrize("enabled", [False, True])
def test_preparation_refinement_is_explicit_and_binds_the_existing_branch(
    tmp_path, monkeypatch, enabled,
):
    model, options, dose, story, state, runtime = preparation_parent_menu(tmp_path, monkeypatch)
    choice = composition.select_branch_recovery_live_option(
        model, options, progress_head(), objective_ref="private-combat-goal", seed=1,
        greedy_selection=True, refine_preparation=enabled,
    )
    assert choice.branch_recovery.parent.selected_binding is options.binding(dose)
    assert choice.selected_binding is options.binding(story if enabled else dose)
    assert (choice.branch_recovery.child is not None) is enabled
    assert choice.public_dict()["branch_recovery"]["model_queries"] == (2 if enabled else 1)
    assert not runtime.recorder.trace and not state["trained"] and not state["challenge"]
    if enabled:
        assert choice.public_dict()["branch_recovery"]["refine_preparation"] is True
        with pytest.raises(ValueError):
            replace(choice, branch_recovery=replace(choice.branch_recovery,
                                                   refine_preparation=False))


def test_preparation_refinement_keeps_the_parents_recovery_decision(tmp_path, monkeypatch):
    model, options, _, _, _, runtime = preparation_parent_menu(tmp_path, monkeypatch)
    restore = next(i for i, b in enumerate(options.bindings) if b.kind is GoalKind.RESTORE_TEAM)
    monkeypatch.setattr(composition, "select_red_live_option", lambda m, observed, **kw:
                        parent_choice(observed, restore, m, seed=kw["seed"],
                                      mode=RedLiveOptionSelectionMode.MODEL_GREEDY))
    monkeypatch.setattr(composition, "select_consequence_live_option",
                        lambda *a, **kw: pytest.fail("Recovery belongs to the parent"))
    choice = composition.select_branch_recovery_live_option(
        model, options, progress_head(), objective_ref="private-combat-goal", seed=1,
        greedy_selection=True, refine_preparation=True,
    )
    assert choice.selected_binding is options.binding(restore)
    assert choice.branch_recovery.child is None
    assert choice.public_dict()["branch_recovery"]["model_queries"] == 1
    assert not runtime.recorder.trace


@pytest.mark.parametrize("fault", ["ambiguous", "ambiguous_outside_scope",
                                   "no_matching_branch", "no_dose", "unknown"])
def test_preparation_refinement_does_not_guess_a_combat_branch(tmp_path, monkeypatch, fault):
    model, options, dose, story, _, runtime = preparation_parent_menu(tmp_path, monkeypatch)
    scope = "private-combat-goal"
    candidates = list(options.menu.candidates)
    if fault in {"ambiguous", "ambiguous_outside_scope"}:
        other = next(i for i, b in enumerate(options.bindings)
                     if b.story_objective_ref == "private-travel-goal")
        candidates[other] = replace(candidates[other], challenge=candidates[story].challenge)
        if fault == "ambiguous":
            scope = ("private-combat-goal", "private-travel-goal")
    elif fault == "no_matching_branch":
        scope = "private-different-goal"
    elif fault == "no_dose":
        candidates[dose] = replace(candidates[dose], preparation=None)
    else:
        candidates[dose] = replace(candidates[dose],
                                   challenge=OptionChallenge(False, False, 0.0, 0.0, 0.0))
    options = replace(options, menu=replace(options.menu, candidates=tuple(candidates)))
    monkeypatch.setattr(composition, "select_consequence_live_option",
                        lambda *a, **kw: pytest.fail("No unique declared question exists"))
    choice = composition.select_branch_recovery_live_option(
        model, options, progress_head(), objective_ref=scope, seed=1,
        greedy_selection=True, refine_preparation=True,
    )
    assert choice.selected_binding is options.binding(dose)
    assert choice.branch_recovery.child is None and not runtime.recorder.trace


def test_preparation_refinement_identity_does_not_change_default_dispatch():
    args = ("a" * 64, "b" * 64, "private-goal")
    old = composition.branch_recovery_identity(*args, greedy_selection=True)
    assert old == composition.branch_recovery_identity(
        *args, greedy_selection=True, refine_preparation=False)
    assert old != composition.branch_recovery_identity(
        *args, greedy_selection=True, refine_preparation=True)
    with pytest.raises(ValueError):
        composition.branch_recovery_identity(*args, refine_preparation=True)


def test_native_preparation_refinement_forwards_authority_and_counts_two_queries(
    tmp_path, monkeypatch,
):
    from pokemon_red_completion.living_dex_option_value import LivingDexOptionValueModel

    args, state = greedy_native_args(tmp_path, monkeypatch)
    args["refine_preparation"] = True
    monkeypatch.setattr(LivingDexOptionValueModel, "scores", lambda self, observed, utility:
                        tuple(float(c.features.kind is LivingDexOptionKind.DEVELOP)
                              for c in observed.candidates))
    result = native.run_native_continuous_player(**args)
    plan = json.loads((args["output"] / "native-plan.json").read_text())
    decision = json.loads((args["output"] / "episode/step-000/decision.json").read_text())
    assert plan["refine_preparation"] is True
    assert decision["branch_recovery"]["refine_preparation"] is True
    assert result["strategic_policy_queries"] == 2 and result["model_decisions"] == 1
    assert state["challenge"] and not state["trained"]
    assert result["model_sha256"] == composition.branch_recovery_identity(
        args["model"].model_sha256, args["consequence_head"].model_sha256,
        args["consequence_objective_ref"], greedy_selection=True, refine_preparation=True,
    )


@pytest.mark.parametrize("fault", ["not_greedy", "not_admitted", "untyped"])
def test_native_preparation_refinement_rejects_unbound_authority_before_input(
    tmp_path, monkeypatch, fault,
):
    args, state = greedy_native_args(tmp_path, monkeypatch)
    args["refine_preparation"] = True
    if fault == "not_greedy":
        args["greedy_selection"] = False
    elif fault == "not_admitted":
        args["allow_greedy_branch_recovery"] = False
    else:
        args["refine_preparation"] = 1
    with pytest.raises(ValueError):
        native.run_native_continuous_player(**args)
    assert not args["output"].exists() and args["emulator"].frame_count == 0
    assert not state["trained"] and not state["challenge"]


@pytest.mark.parametrize("plural", [False, True])
def test_native_highest_score_composition_binds_rule_and_counts_both_queries(
    tmp_path, monkeypatch, plural,
):
    from pokemon_red_completion.living_dex_option_value import LivingDexOptionValueModel

    args, state = greedy_native_args(tmp_path, monkeypatch)
    if plural:
        scope = ("private-combat-goal", "private-second-combat-goal")
        args.update(consequence_objective_ref=scope,
                    consequence_challenge_ref=composition.branch_recovery_scope_ref(scope))
    monkeypatch.setattr(LivingDexOptionValueModel, "scores", lambda self, observed, utility:
                        tuple(float(c.features.kind is LivingDexOptionKind.UNLOCK_ACCESS)
                              for c in observed.candidates))
    result = native.run_native_continuous_player(**args)
    plan = json.loads((args["output"] / "native-plan.json").read_text())
    decision = json.loads((args["output"] / "episode/step-000/decision.json").read_text())
    intent = json.loads((args["output"] / "episode/step-000/intent.json").read_text())
    assert plan["allow_greedy_branch_recovery"] and plan["greedy_selection"]
    assert intent["private_selection_authority"]["greedy_selection"]
    assert decision["branch_recovery"]["branch"]["mode"] == "model_greedy"
    assert result["strategic_policy_queries"] == 2 and result["model_decisions"] == 1
    assert state["challenge"] and not state["trained"]
    assert result["model_sha256"] == composition.branch_recovery_identity(
        args["model"].model_sha256, args["consequence_head"].model_sha256,
        args["consequence_objective_ref"], greedy_selection=True,
    )


@pytest.mark.parametrize("fault", ["no_opt_in", "not_greedy", "no_objective", "no_context",
                                   "no_head", "train", "benchmark", "sealed",
                                   "no_work_order", "bad_work_order", "wrong_state",
                                   "legacy_head", "sequence", "bad_permission"])
def test_highest_score_child_scope_rejects_before_claim_or_input(tmp_path, monkeypatch, fault):
    args, state = greedy_native_args(tmp_path, monkeypatch)
    if fault == "no_opt_in":
        args["allow_greedy_branch_recovery"] = False
    elif fault == "not_greedy":
        args["greedy_selection"] = False
    elif fault == "no_objective":
        args["consequence_objective_ref"] = None
    elif fault == "no_context":
        args["consequence_challenge_ref"] = None
    elif fault == "no_head":
        args["consequence_head"] = None
    elif fault in {"train", "benchmark", "sealed"}:
        args["source"]["partition"] = fault
    elif fault == "no_work_order":
        del args["source"]["experiment_sha256"]
    elif fault == "bad_work_order":
        args["source"]["experiment_sha256"] = "not-a-digest"
    elif fault == "wrong_state":
        args["source"]["state_sha256"] = "f" * 64
    elif fault == "legacy_head":
        args["consequence_head"] = replace(args["consequence_head"], provenance="synthetic")
    elif fault == "sequence":
        args["sequence_horizon"] = 2
    else:
        args["allow_greedy_branch_recovery"] = 1
    with pytest.raises(ValueError):
        native.run_native_continuous_player(**args)
    assert not args["output"].exists() and args["emulator"].frame_count == 0
    assert not state["trained"] and not state["challenge"]
