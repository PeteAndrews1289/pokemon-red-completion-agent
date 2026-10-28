"""Synthetic dispatch checks; no native gameplay or training evidence."""

import json
from dataclasses import replace

import numpy as np
import pytest
from test_native_challenge_consequence import harness, session

import pokemon_red_completion.red_native_player as native
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import option_feature_names
from pokemon_red_completion.player_challenge_consequence import (
    PROGRESS_TARGET_NAMES,
    TARGET_NAMES,
    ChallengeConsequenceHead,
)
from pokemon_red_completion.red_consequence_choice import choose_consequence_binding


def head(prefer=None):
    width = len(option_feature_names(7))
    weights = np.zeros((width, len(TARGET_NAMES)))
    if prefer is not None:
        weights[option_feature_names(7).index(prefer), 0] = 1
        weights[option_feature_names(7).index(prefer), 1] = 1
    return ChallengeConsequenceHead(
        weights, np.zeros(len(TARGET_NAMES)), np.zeros(width), np.ones(width),
        "a" * 64, 2, 1.0, "synthetic",
    )


@pytest.mark.parametrize("kind,feature", [
    (GoalKind.DEVELOP_TEAM, "kind.develop"),
    (GoalKind.ADVANCE_STORY, "kind.unlock_access"),
])
def test_model_choice_controls_exact_native_binding(tmp_path, monkeypatch, kind, feature):
    args, state = harness(tmp_path, monkeypatch, first=kind, fault="win")
    s = session(args)
    options = s.observe(0)
    selected, receipt = choose_consequence_binding(
        options, head(feature), challenge_refs=("challenge",) * len(options.bindings),
    )
    assert selected is options.binding(receipt["selected_index"])
    assert selected.kind is kind and not receipt["teacher_selected"]
    assert not s.recorder.trace and not state["trained"] and not state["challenge"]
    selected.verify(selected.execute())
    assert state["trained"] == (kind is GoalKind.DEVELOP_TEAM)
    assert state["challenge"] == (kind is GoalKind.ADVANCE_STORY)
    assert s.consequence.plan["selected_index"] == receipt["selected_index"]
    assert s.consequence.plan["binding_ref"] == receipt["binding_ref"]


def test_exact_tie_uses_menu_order_and_never_executes(tmp_path, monkeypatch):
    args, _ = harness(tmp_path, monkeypatch)
    s = session(args)
    options = s.observe(0)
    _, receipt = choose_consequence_binding(
        options, head(), challenge_refs=("challenge",) * len(options.bindings),
    )
    assert receipt["selected_index"] == min(options.menu.available_indices)
    assert not s.recorder.trace
    with pytest.raises(ValueError, match="one explicit challenge"):
        choose_consequence_binding(options, head(), challenge_refs=("a", "b"))
    assert not s.recorder.trace


def test_mismatched_executable_kind_rejected(tmp_path, monkeypatch):
    args, _ = harness(tmp_path, monkeypatch)
    s = session(args)
    options = s.observe(0)
    invalid = replace(options, bindings=tuple(
        replace(b, kind=GoalKind.RESTORE_TEAM) for b in options.bindings
    ))
    with pytest.raises(ValueError, match="executable kind"):
        choose_consequence_binding(
            invalid, head(), challenge_refs=("same",) * len(options.bindings),
        )
    assert not s.recorder.trace


def progress_head(prefer="kind.unlock_access"):
    """Synthetic dispatch weights only; not native learning evidence."""
    width = len(option_feature_names(7))
    weights = np.zeros((width, len(PROGRESS_TARGET_NAMES)))
    weights[option_feature_names(7).index(prefer), 0:2] = 1
    return ChallengeConsequenceHead(
        weights, np.zeros(len(PROGRESS_TARGET_NAMES)), np.zeros(width), np.ones(width),
        "a" * 64, 2, 1.0, "native_train", feedback_version=2,
    )


def provisional_args(tmp_path, monkeypatch):
    args, state = harness(tmp_path, monkeypatch, fault="win")
    args.pop("consequence_spec")
    args.update(
        source={**args["source"], "partition": "development"},
        consequence_head=progress_head(), consequence_challenge_ref="observed-challenge",
        limits=replace(args["limits"], decisions=1),
    )
    return args, state


@pytest.mark.parametrize("kind,feature", [
    (GoalKind.ADVANCE_STORY, "kind.unlock_access"),
    (GoalKind.DEVELOP_TEAM, "kind.develop"),
])
def test_provisional_head_owns_ordinary_continuous_choice(
    tmp_path, monkeypatch, kind, feature,
):
    args, state = provisional_args(tmp_path, monkeypatch)
    args["consequence_head"] = progress_head(feature)
    result = native.run_native_continuous_player(**args)
    decision = json.loads((args["output"] / "episode/step-000/decision.json").read_text())
    plan = json.loads((args["output"] / "native-plan.json").read_text())
    costs = json.loads((args["output"] / "native-costs.json").read_text())
    assert result["model_decisions"] == result["executed_decisions"] == 1
    assert decision["policy_id"] == "red-live-challenge-consequence-v2"
    assert decision["consequence"]["provisional"]
    assert plan["execution"]["model_sha256"] == args["consequence_head"].model_sha256
    assert plan["consequence_policy"]["head_sha256"] == args["consequence_head"].model_sha256
    assert plan["source"]["partition"] == "development" and not plan["automatic_fit"]
    assert state["challenge"] == (kind is GoalKind.ADVANCE_STORY)
    assert state["trained"] == (kind is GoalKind.DEVELOP_TEAM)
    assert costs["actions_attempted"] == (1 if kind is GoalKind.ADVANCE_STORY else 2)
    assert not args["emulator"].pressed_buttons


@pytest.mark.parametrize("fault", ["train", "legacy_head", "no_context", "sequence", "recording"])
def test_provisional_scope_rejects_before_claim_or_input(tmp_path, monkeypatch, fault):
    args, state = provisional_args(tmp_path, monkeypatch)
    if fault == "train":
        args["source"]["partition"] = "train"
    elif fault == "legacy_head":
        args["consequence_head"] = head()
    elif fault == "no_context":
        args["consequence_challenge_ref"] = None
    elif fault == "sequence":
        args["sequence_horizon"] = 2
    else:
        from pokemon_red_completion.red_challenge_consequence import ChallengeConsequenceSpec
        args["consequence_spec"] = ChallengeConsequenceSpec(
            GoalKind.ADVANCE_STORY, dict(kind="events", map_id=0, events=[1]), None,
        )
    with pytest.raises(ValueError):
        native.run_native_continuous_player(**args)
    assert not args["output"].exists() and args["emulator"].frame_count == 0
    assert not state["trained"] and not state["challenge"]
    identity = native.NativeExecutionIdentity(
        args["run_id"], args["arm_id"], args["consequence_head"].model_sha256, args["seed"],
    )
    assert args["store"].find_sealed_record(identity.claim_id) is None


def test_missing_challenge_context_refuses_without_teacher_fallback(tmp_path, monkeypatch):
    args, state = provisional_args(tmp_path, monkeypatch)
    args["observe_challenges"] = lambda *_: {}
    result = native.run_native_continuous_player(**args)
    failure = json.loads((args["output"] / "episode/step-000/selection-failure.json").read_text())
    assert result["stop_reason"] == "consequence_context_unavailable"
    assert result["executed_decisions"] == result["model_decisions"] == 0
    assert not failure["teacher_fallback"] and failure["actions_executed"] == 0
    assert args["emulator"].frame_count == 0
    assert not state["trained"] and not state["challenge"]


def test_compulsory_restoration_stays_labelled_nonmodel_support(tmp_path, monkeypatch):
    from test_red_native_player import setup

    from pokemon_red_completion.living_dex_option_value import (
        upgrade_option_value_model_for_preparation,
    )

    args, executed = setup(tmp_path, monkeypatch, support="restore")
    args.update(
        source={**args["source"], "partition": "development"},
        model=upgrade_option_value_model_for_preparation(args["model"]),
        consequence_head=progress_head(), consequence_challenge_ref="observed-challenge",
        limits=replace(args["limits"], decisions=1),
    )
    result = native.run_native_continuous_player(**args)
    assert result["model_decisions"] == 0 and executed == [2]
    decision = json.loads((args["output"] / "episode/step-000/decision.json").read_text())
    assert "consequence" not in decision
