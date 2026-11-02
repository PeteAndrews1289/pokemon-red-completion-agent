"""Inference-only child compatibility; constructed forecasts are synthetic tests."""

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_consequence_v15_vertical import dispatch_head, upgrade_args
from test_red_branch_recovery import greedy_native_args, menu

import pokemon_red_completion.red_consequence_choice as composition
import pokemon_red_completion.red_native_player as native
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionKind,
    LivingDexOptionValueModel,
    upgrade_option_value_model_for_story_unit,
)
from pokemon_red_completion.player_challenge_consequence import (
    ChallengeConsequenceHead,
    ConsequenceExample,
    consequence_candidate_vector,
    consequence_feature_versions_compatible,
)
from pokemon_red_completion.player_consequence_projection import PROSPECTIVE_CONTEXT, SHARED_CONTEXT
from pokemon_red_completion.player_option_level_workload import OptionLevelWorkload
from pokemon_red_completion.player_option_matchup import OptionMatchup
from pokemon_red_completion.player_option_story_unit import OptionStoryUnit
from pokemon_red_completion.player_preparation_party_context import (
    PARTY_PROJECTION,
    PreparationPartyCounts,
)


def paired_menus(tmp_path, monkeypatch):
    options, story, _, _ = menu(tmp_path, monkeypatch)
    challenge = options.menu.candidates[story].challenge
    kept = [
        i for i, b in enumerate(options.bindings) if b.kind is GoalKind.DEVELOP_TEAM or i == story
    ]
    candidates = []
    for i in kept:
        c = options.menu.candidates[i]
        p = c.preparation
        candidates.append(
            replace(
                c,
                challenge=challenge,
                level_workload=None
                if p is None
                else OptionLevelWorkload(p.current_level, p.target_level, p.remaining_xp),
                matchup=OptionMatchup((0.0,) * 27) if i == story else None,
            )
        )
    old = replace(options.menu, candidates=tuple(candidates))
    fresh = replace(
        old,
        candidates=tuple(
            replace(c, story_unit=OptionStoryUnit("interaction", False))
            if c.features.kind is LivingDexOptionKind.UNLOCK_ACCESS
            else c
            for c in old.candidates
        ),
    )
    assert old.feature_version == 15 and fresh.feature_version == 16
    return old, fresh


@pytest.mark.parametrize(
    "head,parent,allowed",
    [
        (15, 16, True),
        (15, 15, True),
        (7, 7, True),
        (9, 16, False),
        (10, 16, False),
        (16, 15, False),
        (15, 17, False),
        (True, True, False),
    ],
)
def test_only_exact_additive_compatibility(head, parent, allowed):
    assert consequence_feature_versions_compatible(head, parent) is allowed


@pytest.mark.parametrize(
    "projection", ["identity", SHARED_CONTEXT, PROSPECTIVE_CONTEXT, PARTY_PROJECTION]
)
def test_v16_child_projection_keeps_exact_old_scores_and_identity(
    tmp_path, monkeypatch, projection
):
    old, fresh = paired_menus(tmp_path, monkeypatch)
    head = dispatch_head(projection=projection)
    before = head.document()
    identity = head.model_sha256
    kw = (
        dict(party_context=PreparationPartyCounts(6, 2, 1))
        if projection == PARTY_PROJECTION
        else {}
    )
    for i in old.available_indices:
        assert consequence_candidate_vector(fresh, i, feature_version=15) == old.candidate_vector(
            i, feature_version=15
        )
    assert head.scores(fresh, challenge_refs=("same", "same"), **kw) == head.scores(
        old, challenge_refs=("same", "same"), **kw
    )
    assert (
        head.document() == before and head.model_sha256 == identity and head.feature_version == 15
    )
    if projection == PARTY_PROJECTION:
        with pytest.raises(ValueError, match="party-count"):
            head.scores(fresh, challenge_refs=("same", "same"))
    # Full parent observation and its identity remain unmodified.
    assert fresh.candidates[-1].story_unit == OptionStoryUnit("interaction", False)
    assert fresh.policy_sha256 != old.policy_sha256


def test_descriptor_only_difference_is_not_child_information(tmp_path, monkeypatch):
    _, fresh = paired_menus(tmp_path, monkeypatch)
    c = fresh.candidates[-1]
    duplicate = replace(
        fresh,
        candidates=(
            replace(c, binding_ref="one"),
            replace(c, binding_ref="two", story_unit=OptionStoryUnit("movement", True)),
        ),
    )
    assert duplicate.candidate_vector(0, feature_version=16) != duplicate.candidate_vector(
        1, feature_version=16
    )
    assert consequence_candidate_vector(
        duplicate, 0, feature_version=15
    ) == consequence_candidate_vector(duplicate, 1, feature_version=15)
    # Exercise the production distinct-child-input guard, before dispatch.
    with pytest.raises(ValueError, match="distinct semantic inputs"):
        composition.select_consequence_live_option(
            SimpleNamespace(menu=duplicate), dispatch_head(), challenge_ref="same", seed=0
        )


def test_compatibility_does_not_admit_v16_training_rows():
    with pytest.raises(ValueError, match="features"):
        ConsequenceExample(
            "a" * 64, "b" * 64, (0.0,) * 510, None, "synthetic censor", feature_version=16
        )


def test_bad_v16_suffix_is_refused():
    fake = SimpleNamespace(
        feature_version=16, candidate_vector=lambda *a, **k: (0.0,) * 506 + (1.0, 1.0, 1.0, 1.0)
    )
    with pytest.raises(ValueError, match="story unit vector"):
        consequence_candidate_vector(fake, 0, feature_version=15)


def test_continuous_runtime_admits_pair_and_records_child_version(tmp_path, monkeypatch):
    args, state = greedy_native_args(tmp_path, monkeypatch)
    upgrade_args(args)
    args["model"] = upgrade_option_value_model_for_story_unit(args["model"])
    args["consequence_head"] = dispatch_head(prefer="kind.unlock_access")
    monkeypatch.setattr(
        LivingDexOptionValueModel,
        "scores",
        lambda self, observed, utility: tuple(
            float(c.features.kind is LivingDexOptionKind.UNLOCK_ACCESS) for c in observed.candidates
        ),
    )
    result = native.run_native_continuous_player(**args)
    assert result["executed_decisions"] == 1 and state["challenge"]
    plan = json.loads((args["output"] / "native-plan.json").read_text())
    assert plan["consequence_feature_version"] == 15
    assert plan["consequence_input_projection"]["observed_feature_version"] == 16
    assert (
        plan["consequence_input_projection"]["child_model_sha256"]
        == args["consequence_head"].model_sha256
    )
    assert not args["emulator"].pressed_buttons


def test_actual_frozen_pair_loader_and_scope_before_guest(monkeypatch):
    # Optional fixture is an immutable existing job PLAN, never a save/emulator.
    name = os.environ.get("POKEMON_V16_COMPAT_PLAN")
    if name is None:
        pytest.skip("set POKEMON_V16_COMPAT_PLAN for real frozen assembly admission")
    import run_configured_red_player as configured

    from pokemon_red_completion.red_player_model import load_player_goal_model_record_bytes

    plan_path = Path(name)
    payload = plan_path.read_bytes()
    plan = json.loads(payload)
    model_ref = plan["goal_model_record"]
    model_bytes = Path(model_ref["path"]).read_bytes()
    assert hashlib.sha256(model_bytes).hexdigest() == model_ref["content_sha256"]
    model = load_player_goal_model_record_bytes(
        model_bytes, expected_model_sha256=plan["configuration"]["goal_model_sha256"]
    ).model
    refinement = configured.declared_readiness_refinement(plan)
    head = refinement["consequence_head"]
    spec = plan["readiness_refinement"]
    assert model.feature_version == 16 and head.feature_version == 15 and head.examples == 13
    assert head.model_sha256 == spec["head_sha256"] and head.provenance == "native_train"
    # Any accidental inference in this assembly-only qualification fails.
    for cls, names in [
        (LivingDexOptionValueModel, ("scores", "raw_predictions", "_base_raw_predictions")),
        (ChallengeConsequenceHead, ("scores", "predict")),
    ]:
        for method in names:
            monkeypatch.setattr(
                cls,
                method,
                lambda *a, **k: pytest.fail(
                    "no prediction authorized for assembled-pair admission"
                ),
            )
    source = dict(
        partition=plan["partition"],
        state_sha256=plan["source_sha256"],
        experiment_sha256=hashlib.sha256(payload).hexdigest(),
    )
    kw = dict(
        allow=refinement["allow_greedy_branch_recovery"],
        greedy_selection=configured.declared_greedy_selection(plan),
        source=source,
        model=model,
        head=head,
        objective_ref=refinement["consequence_objective_ref"],
        challenge_ref=refinement["consequence_challenge_ref"],
        refine_preparation=refinement.get("refine_preparation", False),
        defer_unbound_preparation=refinement.get("defer_unbound_preparation", False),
        allow_singleton_parent_support=refinement.get("allow_singleton_parent_support", False),
    )
    composition.validate_greedy_branch_recovery_scope(**kw)
    for bad in [
        dict(source={**source, "partition": "train"}),
        dict(head=replace(head, provenance="synthetic")),
    ]:
        with pytest.raises(ValueError, match="exact declared DEVELOPMENT scope"):
            composition.validate_greedy_branch_recovery_scope(**{**kw, **bad})
    assert (
        native.validate_settlement_refinement_scope(
            allow=True,
            source=source,
            model=model,
            head=head,
            objective_ref=kw["objective_ref"],
            challenge_ref=kw["challenge_ref"],
            settlement_requested=True,
            sequence_horizon=None,
            sequence_policy=None,
            consequence_spec=None,
        )
        is True
    )
