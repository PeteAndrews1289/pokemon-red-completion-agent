"""Scope-dependent sampling admission and provenance; no learning evidence."""

import json
from dataclasses import replace
from hashlib import sha256

import pytest
from test_red_branch_recovery import menu, greedy_native_args
from test_red_consequence_choice import progress_head, provisional_args
from test_unique_observed_combat_association import fixture, choose

import pokemon_red_completion.red_consequence_choice as C
import pokemon_red_completion.red_native_player as native
from pokemon_red_completion.red_live_option_menu import RedLiveOptionSelectionMode as Mode
from run_configured_red_player import declared_readiness_refinement


@pytest.mark.parametrize("seed", [1, 17, 202610201042])
def test_absent_scope_keeps_exact_ordinary_sampler_and_full_menu(tmp_path, monkeypatch, seed):
    options, _, state, runtime = menu(tmp_path, monkeypatch)
    args, _ = provisional_args(tmp_path / "model", monkeypatch)
    model, head = args["model"], progress_head()
    expected = C.select_red_live_option(model, options, seed=seed, allow_earning_exploration=True)
    observed = C.select_branch_recovery_live_option(
        model, options, head, objective_ref="absent-declared-combat", seed=seed,
        greedy_selection=True, refine_preparation=True, explore_outside_scope=True,
    )
    assert observed.options is options and observed.branch_recovery.child is None
    parent = observed.branch_recovery.parent
    assert parent.options is options
    assert parent.public_dict() == expected.public_dict()
    assert observed.selected_binding is expected.selected_binding
    assert observed.probabilities == expected.probabilities
    assert observed.scores == expected.scores
    assert observed.mode is expected.mode
    doc = observed.branch_recovery.document()
    assert doc["child_scope_available"] is False
    assert doc["parent_selection_rule"] == "ordinary_exploration"
    assert doc["parent_authority"] == expected.mode.value
    assert not runtime.recorder.trace and not state["trained"]


@pytest.mark.parametrize("child_story", [False, True])
def test_available_scope_preserves_parent_and_child_exactly(tmp_path, monkeypatch, child_story):
    options, _, _, model, head, seen, runtime = fixture(
        tmp_path, monkeypatch, child_story=child_story
    )
    old = choose(options, model, head)
    new = choose(options, model, head, explore_outside_scope=True)
    assert new.branch_recovery.parent.public_dict() == old.branch_recovery.parent.public_dict()
    assert new.branch_recovery.child.public_dict() == old.branch_recovery.child.public_dict()
    assert new.branch_recovery.unique_combat_witness == old.branch_recovery.unique_combat_witness
    assert new.selected_binding is old.selected_binding
    assert new.scores == old.scores and new.probabilities == old.probabilities
    assert new.model_sha256 != old.model_sha256
    assert new.branch_recovery.document()["child_scope_available"] is True
    assert new.branch_recovery.document()["parent_selection_rule"] == "maximum_score_with_seeded_ties"
    assert seen == [options, options] and not runtime.recorder.trace
    forged = replace(new.branch_recovery.parent, mode=Mode.MODEL_EXPLORATION)
    with pytest.raises(ValueError, match="parent authority"):
        replace(new, branch_recovery=replace(new.branch_recovery, parent=forged))


def test_default_identity_is_preserved_and_opt_in_has_a_distinct_schema():
    args = ("a" * 64, "b" * 64, "observed-combat")
    old = C.branch_recovery_identity(*args, greedy_selection=True, refine_preparation=True)
    assert old == C.branch_recovery_identity(
        *args, greedy_selection=True, refine_preparation=True, explore_outside_scope=False
    )
    assert old != C.branch_recovery_identity(
        *args, greedy_selection=True, refine_preparation=True, explore_outside_scope=True
    )


@pytest.mark.parametrize("changes", [
    {"explore_outside_scope": 1}, {"greedy_selection": False},
    {"refine_preparation": False}, {"defer_unbound_preparation": True},
    {"allow_singleton_parent_support": True},
])
def test_invalid_sampler_composition_fails_before_parent_query(tmp_path, monkeypatch, changes):
    options, _, _, runtime = menu(tmp_path, monkeypatch)
    args, _ = provisional_args(tmp_path / "model", monkeypatch)
    monkeypatch.setattr(C, "select_red_live_option", lambda *a, **kw: pytest.fail("No query"))
    kw = dict(greedy_selection=True, refine_preparation=True, explore_outside_scope=True)
    kw.update(changes)
    with pytest.raises(ValueError):
        C.select_branch_recovery_live_option(
            args["model"], options, progress_head(), objective_ref="absent", seed=1, **kw
        )
    assert not runtime.recorder.trace


@pytest.mark.parametrize("fault", [None, "type", "partition", "mode", "refine", "defer"])
def test_driver_requires_explicit_unmasked_development_scope(tmp_path, fault):
    head = progress_head(); payload = json.dumps(head.document()).encode()
    path = tmp_path / "head.json"; path.write_bytes(payload)
    spec = dict(
        objective_ref="defeat_lorelei", head_path=str(path), head_sha256=head.model_sha256,
        content_sha256=sha256(payload).hexdigest(), reason="Explicit scoped sampler diagnostic.",
        refine_preparation=True, explore_outside_scope=True,
    )
    plan = dict(partition="development", objectives=["defeat_lorelei"],
                goal_selection=dict(mode="greedy", reason="Explicit composition"),
                readiness_refinement=spec)
    if fault == "type": spec["explore_outside_scope"] = 1
    elif fault == "partition": plan["partition"] = "train"
    elif fault == "mode": plan["goal_selection"]["mode"] = "exploration"
    elif fault == "refine": spec["refine_preparation"] = False
    elif fault == "defer": spec["defer_unbound_preparation"] = True
    if fault:
        with pytest.raises(ValueError): declared_readiness_refinement(plan)
    else:
        assert declared_readiness_refinement(plan)["explore_outside_scope"] is True


def test_native_session_and_intent_bind_the_sampler_authority(tmp_path, monkeypatch):
    args, state = greedy_native_args(tmp_path, monkeypatch)
    args.update(refine_preparation=True, explore_outside_scope=True)
    result = native.run_native_continuous_player(**args)
    plan = json.loads((args["output"] / "native-plan.json").read_bytes())
    intent = json.loads((args["output"] / "episode/step-000/intent.json").read_bytes())
    decision = json.loads((args["output"] / "episode/step-000/decision.json").read_bytes())
    assert plan["explore_outside_scope"] is True
    assert intent["private_branch_sampling_policy"]["explore_outside_scope"] is True
    assert decision["branch_recovery"]["explore_outside_scope"] is True
    assert result["model_sha256"] == C.branch_recovery_identity(
        args["model"].model_sha256, args["consequence_head"].model_sha256,
        args["consequence_objective_ref"], greedy_selection=True,
        refine_preparation=True, explore_outside_scope=True,
    )


@pytest.mark.parametrize("fault", ["permission", "train", "refine", "nonbool"])
def test_native_rejects_invalid_sampler_authority_before_guest_input(tmp_path, monkeypatch, fault):
    args, _ = greedy_native_args(tmp_path, monkeypatch)
    args.update(refine_preparation=True, explore_outside_scope=True)
    if fault == "permission": args["allow_greedy_branch_recovery"] = False
    elif fault == "train": args["source"]["partition"] = "train"
    elif fault == "refine": args["refine_preparation"] = False
    else: args["explore_outside_scope"] = 1
    with pytest.raises(ValueError): native.run_native_continuous_player(**args)
    assert not args["output"].exists() and args["emulator"].frame_count == 0
