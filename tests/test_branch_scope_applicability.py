"""Dynamic declared-head applicability; no model queries, training or native inputs."""
from dataclasses import replace
import json
import os
from pathlib import Path
from types import SimpleNamespace as N

import pytest
from test_red_branch_recovery import menu, parent_choice
from test_red_consequence_choice import progress_head, provisional_args
import pokemon_red_completion.red_consequence_choice as composition
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_live_option_menu import RedLiveOptionSelectionMode


def singleton_and_dose(tmp_path, monkeypatch, *, in_scope=False, malformed=False):
    options, story, state, runtime = menu(tmp_path, monkeypatch)
    dose = next(i for i, b in enumerate(options.bindings) if b.kind is GoalKind.DEVELOP_TEAM)
    selected_story = options.binding(story)
    if not in_scope:
        selected_story = replace(selected_story, story_objective_ref="other-story-goal")
    candidates = (replace(options.menu.candidates[dose], challenge=None),
        replace(options.menu.candidates[story], challenge=None) if malformed else options.menu.candidates[story])
    bindings = (options.binding(dose), selected_story)
    options = replace(options, bindings=bindings,
        ordinary_binding_refs=options.ordinary_binding_refs & {b.binding_ref for b in bindings},
        menu=replace(options.menu, candidates=candidates))
    args, _ = provisional_args(tmp_path / "model", monkeypatch)
    return args["model"], options, state, runtime


def no_child(monkeypatch):
    monkeypatch.setattr(composition, "select_consequence_live_option",
        lambda *a, **kw: pytest.fail("Out-of-scope head must not be queried"))
    monkeypatch.setattr(composition, "select_red_live_safety_option", lambda *a, **kw: None)


def test_absent_declared_branch_uses_original_unfiltered_parent(tmp_path, monkeypatch):
    model, options, state, runtime = singleton_and_dose(tmp_path, monkeypatch)
    calls = []
    def parent(m, observed, **kw):
        calls.append((observed, kw))
        return parent_choice(observed, 1, m, seed=kw["seed"], mode=RedLiveOptionSelectionMode.MODEL_GREEDY)
    monkeypatch.setattr(composition, "select_red_live_option", parent)
    monkeypatch.setattr(composition, "_sole_observed_combat_parent",
        lambda *a, **kw: pytest.fail("Out-of-scope singleton restriction must not apply"))
    no_child(monkeypatch)
    choice = composition.select_branch_recovery_live_option(model, options, progress_head(),
        objective_ref="private-combat-goal", seed=17, greedy_selection=True,
        refine_preparation=True, defer_unbound_preparation=True, allow_singleton_parent_support=True)
    assert calls[0][0] is options and len(calls[0][0].bindings) == 2
    assert choice.selected_binding is options.binding(1)
    assert choice.mode is RedLiveOptionSelectionMode.MODEL_GREEDY
    assert choice.branch_recovery.child is None
    assert choice.branch_recovery.head_sha256 == progress_head().model_sha256
    assert not runtime.recorder.trace and not state["trained"] and not state["challenge"]


def test_completed_or_unavailable_scope_does_not_activate_head(tmp_path, monkeypatch):
    model, options, _, _ = singleton_and_dose(tmp_path, monkeypatch)
    assert not composition._branch_scope_available(options, ("completed-misty",))
    # An unavailable index cannot make a declared target applicable.
    inactive = N(menu=N(available_indices=(0,)), binding=lambda i:
        N(kind=GoalKind.ADVANCE_STORY, story_objective_ref="completed-misty" if i == 1 else "other"))
    assert not composition._branch_scope_available(inactive, ("completed-misty",))


def test_in_scope_malformed_combat_keeps_existing_fail_closed_guard(tmp_path, monkeypatch):
    model, options, state, runtime = singleton_and_dose(tmp_path, monkeypatch, in_scope=True, malformed=True)
    no_child(monkeypatch)
    monkeypatch.setattr(composition, "select_red_live_option",
        lambda *a, **kw: pytest.fail("Malformed in-scope singleton must fail before a model query"))
    with pytest.raises(ValueError, match="exact observed combat and bounded doses"):
        composition.select_branch_recovery_live_option(model, options, progress_head(),
            objective_ref="private-combat-goal", seed=17, greedy_selection=True,
            refine_preparation=True, defer_unbound_preparation=True, allow_singleton_parent_support=True)
    assert not runtime.recorder.trace


def test_valid_in_scope_singleton_keeps_disclosed_support_and_child(tmp_path, monkeypatch):
    model, options, _, runtime = singleton_and_dose(tmp_path, monkeypatch, in_scope=True)
    sentinel = []
    def existing_parent(*args, **kwargs):
        sentinel.append(kwargs)
        return parent_choice(options, 1, model, mode=RedLiveOptionSelectionMode.FORCED_SINGLETON_SUPPORT)
    monkeypatch.setattr(composition, "_select_preparation_parent", existing_parent)
    # No actual child query: stop at its existing dispatch seam.
    monkeypatch.setattr(composition, "select_consequence_live_option",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("existing in-scope child dispatched")))
    with pytest.raises(RuntimeError, match="in-scope child dispatched"):
        composition.select_branch_recovery_live_option(model, options, progress_head(),
            objective_ref="private-combat-goal", seed=17, greedy_selection=True,
            refine_preparation=True, defer_unbound_preparation=True, allow_singleton_parent_support=True)
    assert sentinel[0]["defer_unbound_preparation"] is True
    assert sentinel[0]["allow_singleton_parent_support"] is True
    assert not runtime.recorder.trace


def test_invalid_declaration_still_fails_before_parent_selection(tmp_path, monkeypatch):
    model, options, _, _ = singleton_and_dose(tmp_path, monkeypatch)
    monkeypatch.setattr(composition, "select_red_live_option", lambda *a, **kw: pytest.fail("No invalid scope fallback"))
    with pytest.raises(ValueError):
        composition.select_branch_recovery_live_option(model, options, progress_head(),
            objective_ref=(), seed=17, greedy_selection=True,
            refine_preparation=True, defer_unbound_preparation=True, allow_singleton_parent_support=True)


def test_retained_stopped_menu_is_outside_scope_without_repairing_it():
    path = os.environ.get("POKEMON_RETAINED_BRANCH_INTENT")
    if not path:
        pytest.skip("Retained private receipt is supplied by the local qualification command")
    intent = json.loads(Path(path).read_text())
    candidates = intent["menu"]["menu"]["candidates"]
    contexts = {row["binding_ref"]: row["objective_ref"] for row in intent["private_story_contexts"]}
    refs = [row["binding_ref"] for row in intent["private_selection_authority"]["live_bindings"]]
    available = tuple(i for i, row in enumerate(candidates) if row["availability"] == "available")
    bindings = tuple(N(kind=GoalKind.ADVANCE_STORY if row["features"]["kind"] == "unlock_access"
        else GoalKind.DEVELOP_TEAM, story_objective_ref=contexts[ref]) for row, ref in zip(candidates, refs))
    observed = N(menu=N(available_indices=available), binding=lambda i: bindings[i])
    assert len(candidates) == len(refs) == 13
    assert [b.story_objective_ref for b in bindings if b.kind is GoalKind.ADVANCE_STORY] == ["obtain_cut"]
    assert not composition._branch_scope_available(observed, ("defeat_misty",))
