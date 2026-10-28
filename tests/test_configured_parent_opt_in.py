"""ROM-free declared plan to actual continuous composition; no fit/native emulator."""
from dataclasses import replace
from hashlib import sha256
import json
from types import SimpleNamespace
import numpy as np
import pytest
import run_configured_red_player as launcher

from test_red_branch_recovery import greedy_native_args
from test_red_consequence_choice import progress_head
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionValueModel, option_feature_names, upgrade_option_value_model_for_matchup,
)
from pokemon_red_completion.player_option_matchup import OptionMatchup
import pokemon_red_completion.red_native_player as native


def plan_for_head(tmp_path, *, flags=None):
    head = progress_head("kind.develop")
    width = len(option_feature_names(15))
    extra = width - len(option_feature_names(7))
    head = replace(head, feature_version=15,
        coefficients=np.vstack((head.coefficients, np.zeros((extra, 9)))),
        feature_mean=np.concatenate((head.feature_mean, np.zeros(extra))),
        feature_scale=np.concatenate((head.feature_scale, np.ones(extra))))
    payload = json.dumps(head.document()).encode()
    path = tmp_path / "head.json"
    path.write_bytes(payload)
    spec = dict(objective_ref="private-combat-goal", head_path=str(path),
        head_sha256=head.model_sha256, content_sha256=sha256(payload).hexdigest(),
        reason="Explicit bounded diagnostic reuse, no fit or main activation.")
    if flags:
        spec.update(flags)
    return dict(partition="development", objectives=["private-combat-goal"],
        goal_selection=dict(mode="greedy", reason="Declared bounded composition."),
        readiness_refinement=spec)


def test_new_flags_are_absent_by_default_and_false_does_not_change_old_dispatch(tmp_path):
    assert launcher.declared_readiness_refinement({"objectives": []}) == {}
    plan = plan_for_head(tmp_path)
    old = launcher.declared_readiness_refinement(plan)
    assert "defer_unbound_preparation" not in old and "allow_singleton_parent_support" not in old
    plan["readiness_refinement"].update(defer_unbound_preparation=False, allow_singleton_parent_support=False)
    current = launcher.declared_readiness_refinement(plan)
    assert set(current) == set(old)
    assert current["consequence_head"].model_sha256 == old["consequence_head"].model_sha256


@pytest.mark.parametrize("fault", ["defer_type", "singleton_type", "missing_deferral", "partition",
    "exploration", "custom_mix", "extra", "bytes", "identity", "objective", "reason", "synthetic"])
def test_new_flags_preserve_exact_authority_schema_and_head_authentication(tmp_path, fault):
    plan = plan_for_head(tmp_path, flags=dict(defer_unbound_preparation=True, allow_singleton_parent_support=True))
    spec = plan["readiness_refinement"]
    if fault == "defer_type": spec["defer_unbound_preparation"] = 1
    elif fault == "singleton_type": spec["allow_singleton_parent_support"] = "true"
    elif fault == "missing_deferral": spec["defer_unbound_preparation"] = False
    elif fault == "partition": plan["partition"] = "train"
    elif fault == "exploration": plan["goal_selection"]["mode"] = "exploration"
    elif fault == "custom_mix": plan["goal_selection"].update(mode="exploration", exploration_mix=.75)
    elif fault == "extra": spec["forced_target"] = "defeat_misty"
    elif fault == "bytes": spec["content_sha256"] = "0" * 64
    elif fault == "identity": spec["head_sha256"] = "0" * 64
    elif fault == "objective": spec["objective_ref"] = "undeclared"
    elif fault == "reason": spec["reason"] = " "
    else:
        from pokemon_red_completion.player_challenge_consequence import ChallengeConsequenceHead
        head = launcher.declared_readiness_refinement(plan)["consequence_head"]
        head = replace(head, provenance="synthetic")
        payload = json.dumps(head.document()).encode()
        from pathlib import Path
        Path(spec["head_path"]).write_bytes(payload)
        spec.update(head_sha256=head.model_sha256, content_sha256=sha256(payload).hexdigest())
    with pytest.raises(ValueError):
        launcher.declared_readiness_refinement(plan)


def test_configured_plan_reaches_real_continuous_support_parent_and_learned_child(tmp_path, monkeypatch):
    plan = plan_for_head(tmp_path, flags=dict(defer_unbound_preparation=True, allow_singleton_parent_support=True))
    args, state = greedy_native_args(tmp_path / "native", monkeypatch)
    args["model"] = upgrade_option_value_model_for_matchup(args["model"])
    import pokemon_red_completion.red_player_lesson_runtime as lesson
    capture = lesson.capture_player_lesson_snapshot
    def complete_raw(runtime):
        observation, snapshot = capture(runtime)
        observation.raw.party_count = len(snapshot["party"])
        observation.raw.party_moves = tuple(tuple(move[0] for move in member["moves"])
                                            for member in snapshot["party"])
        observation.raw.party_pp = tuple(tuple(move[1] for move in member["moves"])
                                         for member in snapshot["party"])
        return observation, snapshot
    monkeypatch.setattr(lesson, "capture_player_lesson_snapshot", complete_raw)
    monkeypatch.setattr(native, "capture_player_lesson_snapshot", complete_raw)
    original = args["observe_challenges"]
    args["observe_challenges"] = lambda *a: {k: v for k, v in original(*a).items() if k != "train"}
    args["observe_matchups"] = lambda rt, bs, *_: {
        b.binding_ref: OptionMatchup((0.,) * 27) for b in bs.bindings if b.kind is GoalKind.ADVANCE_STORY}
    monkeypatch.setattr(launcher, "requires_compulsory_settlement", lambda _: False)
    monkeypatch.setattr(launcher, "declared_player_curriculum", lambda *_: None)
    options = launcher.native_player_options(plan, object(), args["combat_specimen_refs"],
                                             SimpleNamespace(native_callbacks=lambda: {}))
    assert options["defer_unbound_preparation"] is options["allow_singleton_parent_support"] is True
    args.update(options)
    monkeypatch.setattr(LivingDexOptionValueModel, "scores",
        lambda *a: pytest.fail("configured sole parent is support, zero parent queries"))
    result = native.run_native_continuous_player(**args)
    assert result["executed_decisions"] == result["model_decisions"] == result["strategic_policy_queries"] == 1
    assert state["trained"] and not state["challenge"]
    decision = json.loads((args["output"] / "episode/step-000/decision.json").read_text())
    receipt = decision["branch_recovery"]
    assert receipt["parent_authority"] == "forced_singleton_support"
    assert receipt["parent_model_queries"] == 0 and receipt["child_model_queries"] == 1
    assert not args["emulator"].pressed_buttons


