"""ROM-free V9 consequence contracts; synthetic fits are not native evidence."""

import copy
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from test_challenge_consequence import documents
from test_native_challenge_consequence import harness, session
from test_red_consequence_choice import provisional_args

import pokemon_red_completion.red_challenge_consequence as consequence
import pokemon_red_completion.red_native_player as native
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import (
    option_feature_names,
    upgrade_option_value_model_for_level_workload,
)
from pokemon_red_completion.player_challenge_consequence import (
    ChallengeConsequenceHead,
    ConsequenceExample,
    fit_challenge_consequence,
)
from pokemon_red_completion.player_option_level_workload import OptionLevelWorkload
from pokemon_red_completion.provenance import canonical_sha256


def workload_documents(tmp_path, monkeypatch):
    plan, phases, menu = documents(tmp_path, monkeypatch)
    rows = tuple(replace(c, level_workload=OptionLevelWorkload(
        c.preparation.current_level, c.preparation.target_level, c.preparation.remaining_xp
    )) for c in menu.candidates)
    newer = replace(menu, candidates=rows)
    plan.update(schema="pokemon.red.challenge-consequence-plan.v5", feature_version=9,
                menu=newer.policy_dict())
    return plan, phases, newer, menu


def upgraded_head(head):
    """Declared synthetic fixture extension, never a production model upgrade."""
    extra = len(option_feature_names(9)) - len(option_feature_names(7))
    return replace(head, feature_version=9,
        coefficients=np.vstack((head.coefficients, np.zeros((extra, len(head.intercept))))),
        feature_mean=np.concatenate((head.feature_mean, np.zeros(extra))),
        feature_scale=np.concatenate((head.feature_scale, np.ones(extra))))


def test_v9_projection_keeps_the_exact_workload_and_legacy_prefix(tmp_path, monkeypatch):
    plan, phases, menu, older = workload_documents(tmp_path, monkeypatch)
    row = consequence.project_consequence(plan, phases)
    old_width = len(option_feature_names(7))
    assert row.feature_version == 9 and len(row.features) == len(option_feature_names(9))
    assert row.features == menu.candidate_vector(0, feature_version=9)
    assert row.features[:old_width] == older.candidate_vector(0, feature_version=7)
    assert row.features[-5] == 1.0
    assert row.features[-1] == menu.candidates[0].preparation.remaining_xp / 2_000_000
    assert row.outcome.actions == 120 and row.outcome.frames == 7000
    assert row.outcome.restorations == 1 and row.outcome.cash_debits == 750
    assert row.document()["schema"] == "pokemon.player.challenge-consequence.v3"
    assert ConsequenceExample.from_document(row.document()) == row


@pytest.mark.parametrize("fault", ["missing_version", "legacy_plan", "false_version", "wrong_version"])
def test_v9_plan_cannot_hide_observed_workload_from_admission(tmp_path, monkeypatch, fault):
    plan, phases, _, _ = workload_documents(tmp_path, monkeypatch)
    if fault == "missing_version":
        plan.pop("feature_version")
    elif fault == "legacy_plan":
        plan.pop("feature_version")
        plan["schema"] = "pokemon.red.challenge-consequence-plan.v1"
    else:
        plan["feature_version"] = False if fault == "false_version" else 7
    with pytest.raises(ValueError):
        consequence.project_consequence(plan, phases)


@pytest.mark.parametrize("field", ["missing", "current_level", "target_level", "remaining_xp"])
def test_v9_workload_must_match_the_observed_dose(tmp_path, monkeypatch, field):
    plan, phases, menu, _ = workload_documents(tmp_path, monkeypatch)
    candidate = menu.candidates[0]
    workload = candidate.level_workload
    if field == "missing":
        workload = None
    else:
        workload = replace(workload, **{field: getattr(workload, field) + 1})
    bad = replace(menu, candidates=(replace(candidate, level_workload=workload), *menu.candidates[1:]))
    plan["menu"] = bad.policy_dict()
    with pytest.raises(ValueError, match="workload"):
        consequence.project_consequence(plan, phases)


@pytest.mark.parametrize("fault", ["truncate", "missing_version", "wrong_feedback"])
def test_v9_example_codec_rejects_inconsistent_documents(tmp_path, monkeypatch, fault):
    plan, phases, _, _ = workload_documents(tmp_path, monkeypatch)
    doc = consequence.project_consequence(plan, phases).document()
    if fault == "truncate":
        doc["features"] = doc["features"][:len(option_feature_names(7))]
    elif fault == "missing_version":
        doc.pop("feature_version")
    else:
        doc["feedback_version"] = 2
    with pytest.raises((KeyError, TypeError, ValueError)):
        ConsequenceExample.from_document(doc)


def test_new_fitter_retains_legacy_rows_and_learns_the_new_workload_column(tmp_path, monkeypatch):
    plan, phases, _, older = workload_documents(tmp_path, monkeypatch)
    legacy_plan = copy.deepcopy(plan)
    legacy_plan.update(schema="pokemon.red.challenge-consequence-plan.v1", menu=older.policy_dict())
    legacy_plan.pop("feature_version")
    legacy = replace(consequence.project_consequence(legacy_plan, phases), provenance="synthetic")
    frozen = copy.deepcopy(legacy.document())
    base = replace(consequence.project_consequence(plan, phases), provenance="synthetic")
    # Numerical seam: identical old inputs, distinct observed V9 cost coordinates.
    # These artificial matrices are deliberately not tagged as native TRAIN.
    index = option_feature_names(9).index("level_workload.remaining_xp")
    low, high = list(base.features), list(base.features)
    low[index], high[index] = .01, .5
    cheap = replace(base, declaration_sha256="d"*64, features=tuple(low),
                    outcome=replace(base.outcome, actions=50, frames=5000))
    costly = replace(base, declaration_sha256="e"*64, features=tuple(high),
                     outcome=replace(base.outcome, actions=4000, frames=400000))
    head = fit_challenge_consequence((legacy, cheap, costly))
    assert head.feature_version == 9 and head.examples == 3 and head.provenance == "synthetic"
    assert head.coefficients.shape[0] == len(option_feature_names(9))
    assert head.coefficients[index, 2] != 0
    assert head.predict(cheap.features)[2] < head.predict(costly.features)[2]
    assert legacy.document() == frozen and "feature_version" not in frozen
    restored = ChallengeConsequenceHead.from_document(head.document(), expected_sha256=head.model_sha256)
    assert restored.feature_version == 9
    assert np.array_equal(restored.coefficients, head.coefficients)
    assert restored.document() == head.document()
    assert head.document()["schema"] == "pokemon.player.challenge-consequence-head.v4"
    with pytest.raises(ValueError, match="truncate"):
        fit_challenge_consequence((cheap, costly), feature_version=7)
    with pytest.raises(ValueError):
        head.predict(legacy.features)


@pytest.mark.parametrize("fault", [None, "win", "dose_failed", "exception"])
def test_v9_continuous_recorder_retains_the_same_guarded_port(tmp_path, monkeypatch, fault):
    args, state = harness(tmp_path, monkeypatch, fault=fault)
    args["model"] = upgrade_option_value_model_for_level_workload(args["model"])
    s = session(args)
    options = s.observe(0)
    train = next(b for b in options.bindings if b.kind is GoalKind.DEVELOP_TEAM)
    index = options.bindings.index(train)
    vector = options.menu.candidate_vector(index, feature_version=9)
    before = s.consequence.begin(options, train, preflight_only=True)
    assert before["schema"] == "pokemon.red.challenge-consequence-plan.v5"
    assert before["feature_version"] == 9 and args["emulator"].frame_count == 0
    if fault == "exception":
        with pytest.raises(RuntimeError):
            train.execute()
    else:
        train.verify(train.execute())
        if fault != "dose_failed":
            choices = s.observe(1)
            story = next(b for b in choices.bindings if b.kind is GoalKind.ADVANCE_STORY)
            story.verify(story.execute())
    result = s.consequence.finish()
    row = consequence.load_challenge_consequence(args["store"],
        declaration_sha256=result["declaration_sha256"], result_sha256=canonical_sha256(result))
    assert row.feature_version == 9 and row.features == vector
    if fault == "exception":
        assert row.outcome is None and row.censor_reason
    else:
        assert row.outcome.actions == (2 if fault == "dose_failed" else 3)
        assert row.outcome.frames == (4 if fault == "dose_failed" else 6)
        assert row.outcome.completed is (fault == "win")
        assert row.outcome.restorations == 1
    assert not args["emulator"].pressed_buttons
    assert state["challenge"] is (fault not in {"dose_failed", "exception"})


def test_v9_progress_feedback_still_requires_verified_battle_evidence(tmp_path, monkeypatch):
    from test_red_post_battle_strategy import episode

    args, _ = harness(tmp_path, monkeypatch)
    args["model"] = upgrade_option_value_model_for_level_workload(args["model"])
    args["consequence_spec"] = replace(args["consequence_spec"], feedback_version=2)
    original = args["enumerate_bindings"]

    def enumerate_bindings(*arguments):
        bindings = original(*arguments)
        result = []
        for binding in bindings.bindings:
            if binding.kind is GoalKind.ADVANCE_STORY:
                execute = binding.execute

                def challenge(execute=execute):
                    report = execute()
                    return replace(report, evidence={"battle": {"outcome": "lost", "episode": episode()}})

                binding = replace(binding, execute=challenge)
            result.append(binding)
        return replace(bindings, bindings=tuple(result))

    args["enumerate_bindings"] = enumerate_bindings
    s = session(args)
    for ordinal, kind in enumerate([GoalKind.DEVELOP_TEAM, GoalKind.ADVANCE_STORY]):
        options = s.observe(ordinal)
        selected = next(b for b in options.bindings if b.kind is kind)
        selected.verify(selected.execute())
    result = s.consequence.finish()
    row = consequence.load_challenge_consequence(args["store"],
        declaration_sha256=result["declaration_sha256"], result_sha256=canonical_sha256(result))
    assert row.feature_version == 9 and row.feedback_version == 2
    assert row.outcome.attempted and not row.outcome.completed
    assert row.outcome.challenge_progress == pytest.approx(.495)
    assert row.outcome.actions == 3 and row.outcome.restorations == 1


@pytest.mark.parametrize("fault", ["claim_version", "frames", "omitted_later_input"])
def test_v9_loader_still_authenticates_session_version_and_every_native_input(tmp_path, monkeypatch, fault):
    args, _ = harness(tmp_path, monkeypatch)
    args["model"] = upgrade_option_value_model_for_level_workload(args["model"])
    s = session(args)
    for ordinal, kind in enumerate([GoalKind.DEVELOP_TEAM, GoalKind.ADVANCE_STORY]):
        options = s.observe(ordinal)
        binding = next(b for b in options.bindings if b.kind is kind)
        binding.verify(binding.execute())
    result = s.consequence.finish()
    if fault == "claim_version":
        store_type = type(args["store"])
        original = store_type.find_sealed_record

        def find(store, identifier, **kwargs):
            record = original(store, identifier, **kwargs)
            if store is args["store"] and identifier == s.execution.claim_id:
                document = {**record.read(), "consequence_feature_version": 7}
                return SimpleNamespace(read=lambda: document)
            return record

        monkeypatch.setattr(store_type, "find_sealed_record", find)
        digest = canonical_sha256(result)
    else:
        result = copy.deepcopy(result)
        if fault == "frames":
            result["phases"][-1]["after"]["frames"] += 1
        else:
            result["phases"] = result["phases"][:1]
            result["phases"][0]["verified"] = False
        result["row"] = consequence.project_consequence(s.consequence.plan, result["phases"]).document()
        digest = canonical_sha256(result)
        args["store"].publish_sealed_record("rcc-result-"+digest,
            kind="red_challenge_consequence_result", record=result)
    with pytest.raises(ValueError):
        consequence.load_challenge_consequence(args["store"],
            declaration_sha256=result["declaration_sha256"], result_sha256=digest)


def test_v9_head_owns_the_existing_provisional_continuous_choice(tmp_path, monkeypatch):
    args, state = provisional_args(tmp_path, monkeypatch)
    args["model"] = upgrade_option_value_model_for_level_workload(args["model"])
    args["consequence_head"] = upgraded_head(args["consequence_head"])
    result = native.run_native_continuous_player(**args)
    assert result["executed_decisions"] == result["model_decisions"] == 1
    assert state["challenge"] and not state["trained"]
    assert not args["emulator"].pressed_buttons


@pytest.mark.parametrize("upgrade_model", [True, False])
def test_mismatched_head_and_parent_versions_refuse_before_input(tmp_path, monkeypatch, upgrade_model):
    args, state = provisional_args(tmp_path, monkeypatch)
    if upgrade_model:
        args["model"] = upgrade_option_value_model_for_level_workload(args["model"])
    else:
        args["consequence_head"] = upgraded_head(args["consequence_head"])
    with pytest.raises(ValueError):
        native.run_native_continuous_player(**args)
    assert not args["output"].exists() and args["emulator"].frame_count == 0
    assert not state["trained"] and not state["challenge"]


def test_legacy_head_cannot_silently_score_a_v9_menu(tmp_path, monkeypatch):
    args, _ = provisional_args(tmp_path, monkeypatch)
    legacy = args["consequence_head"]
    args["model"] = upgrade_option_value_model_for_level_workload(args["model"])
    args.pop("consequence_head")
    args.pop("consequence_challenge_ref")
    s = session(args)
    options = s.observe(0)
    with pytest.raises(ValueError):
        legacy.scores(options.menu, challenge_refs=("same",) * len(options.bindings))
    assert not s.recorder.trace and args["emulator"].frame_count == 0


def test_legacy_session_claim_is_not_rewritten_with_new_version_metadata(tmp_path, monkeypatch):
    args, _ = harness(tmp_path, monkeypatch)
    s = session(args)
    record = args["store"].find_sealed_record(s.execution.claim_id).read()
    assert "consequence_feature_version" not in record
    assert s.model_feature_version == 7 and args["emulator"].frame_count == 0


@pytest.mark.parametrize("feature,kind", [
    ("kind.develop", GoalKind.DEVELOP_TEAM),
    ("kind.unlock_access", GoalKind.ADVANCE_STORY),
])
def test_v9_child_refines_only_the_parent_selected_combat_branch(tmp_path, monkeypatch, feature, kind):
    from test_red_branch_recovery import menu, parent_choice
    from test_red_consequence_choice import progress_head
    import pokemon_red_completion.red_consequence_choice as composition

    options, at, state, runtime = menu(tmp_path, monkeypatch)
    candidates = tuple(replace(c, level_workload=OptionLevelWorkload(
        c.preparation.current_level, c.preparation.target_level, c.preparation.remaining_xp
    )) if c.features.kind.value == "develop" else c for c in options.menu.candidates)
    options = replace(options, menu=replace(options.menu, candidates=candidates))
    args, _ = provisional_args(tmp_path / "model", monkeypatch)
    model = upgrade_option_value_model_for_level_workload(args["model"])
    monkeypatch.setattr(composition, "select_red_live_option",
        lambda model, observed, **kwargs: parent_choice(observed, at, model, seed=kwargs["seed"]))
    choice = composition.select_branch_recovery_live_option(model, options,
        upgraded_head(progress_head(feature)), objective_ref="private-combat-goal", seed=1)
    assert choice.selected_binding.kind is kind
    child = choice.branch_recovery.child
    assert child is not None and child.options.menu.feature_version == 9
    assert all(b.story_objective_ref != "private-travel-goal" for b in child.options.bindings)
    assert all(len(child.options.menu.candidate_vector(i, feature_version=9)) == 370
               for i in child.options.menu.available_indices)
    assert not runtime.recorder.trace and not state["trained"] and not state["challenge"]


@pytest.mark.parametrize("model_version,head_version", [(9, 9), (7, 9), (9, 7)])
def test_v9_settled_refinement_keeps_the_declared_matching_scope(tmp_path, monkeypatch, model_version, head_version):
    args, _ = provisional_args(tmp_path, monkeypatch)
    model, head = args["model"], args["consequence_head"]
    if model_version == 9:
        model = upgrade_option_value_model_for_level_workload(model)
    if head_version == 9:
        head = upgraded_head(head)
    kwargs = dict(allow=True, source=args["source"], model=model, head=head,
        objective_ref="private-combat-goal", challenge_ref="private-combat-goal",
        settlement_requested=True, sequence_horizon=None,
        sequence_policy=None, consequence_spec=None)
    if model_version == head_version:
        assert native.validate_settlement_refinement_scope(**kwargs)
    else:
        with pytest.raises(ValueError):
            native.validate_settlement_refinement_scope(**kwargs)
    assert args["emulator"].frame_count == 0
