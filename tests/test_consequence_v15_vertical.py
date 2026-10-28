"""ROM-free V15 consequence integration. Constructed weights are synthetic dispatch fixtures."""
from dataclasses import replace
import copy
import json
import numpy as np
import pytest

from test_native_challenge_consequence import harness, session
from test_red_branch_recovery import greedy_native_args
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionKind, LivingDexOptionValueModel, option_feature_names,
    upgrade_option_value_model_for_matchup, upgrade_option_value_model_for_level_workload,
)
from pokemon_red_completion.player_challenge_consequence import (
    ChallengeConsequenceHead, ConsequenceExample, PROGRESS_TARGET_NAMES,
)
from pokemon_red_completion.player_consequence_projection import (
    SHARED_CONTEXT, consequence_feature_names, project_consequence_features,
)
from pokemon_red_completion.player_option_matchup import OptionMatchup
from pokemon_red_completion.provenance import canonical_sha256
import pokemon_red_completion.red_challenge_consequence as recorder
import pokemon_red_completion.red_consequence_choice as composition
import pokemon_red_completion.red_native_player as native


def observed_matchups(runtime, bindings, *_):
    # Current, explicitly unknown descriptor. No fabricated post-dose stats.
    return {b.binding_ref: OptionMatchup((0.,) * 27) for b in bindings.bindings
            if b.kind is GoalKind.ADVANCE_STORY}


def upgrade_args(args):
    args["model"] = upgrade_option_value_model_for_matchup(args["model"])
    args["observe_matchups"] = observed_matchups
    return args


def dispatch_head(version=15, prefer="kind.develop", projection="identity"):
    width = len(consequence_feature_names(version, projection))
    names = consequence_feature_names(version, projection)
    weights = np.zeros((width, len(PROGRESS_TARGET_NAMES)))
    weights[names.index(prefer), :2] = 1.
    return ChallengeConsequenceHead(
        weights, np.zeros(len(PROGRESS_TARGET_NAMES)), np.zeros(width), np.ones(width),
        "a" * 64, 2, 1., "native_train", feedback_version=2,
        feature_version=version, context_projection=projection,
    )


@pytest.mark.parametrize("projection", ["identity", SHARED_CONTEXT])
def test_v15_head_codec_keeps_exact_full_width_and_shared_current_facts(projection):
    head = dispatch_head(projection=projection)
    doc = head.document()
    assert doc["schema"] == "pokemon.player.challenge-consequence-head.v8"
    assert doc["feature_version"] == 15
    assert len(doc["feature_names"]) == 506 + (34 if projection == SHARED_CONTEXT else 0)
    restored = ChallengeConsequenceHead.from_document(doc, expected_sha256=head.model_sha256)
    values = [0.] * 506
    values[option_feature_names(15).index("kind.develop")] = 1.
    assert restored.predict(values) == head.predict(values)
    with pytest.raises(ValueError):
        restored.predict(values[:len(option_feature_names(10))])
    projected = project_consequence_features(values, feature_version=15, context_projection=projection)
    assert projected[:506] == tuple(values)
    bad = copy.deepcopy(doc)
    bad["feature_names"][-1] = "invented.future_stats"
    with pytest.raises(ValueError):
        ChallengeConsequenceHead.from_document(bad, expected_sha256=canonical_sha256(bad))


@pytest.mark.parametrize("fault", [None, "win", "dose_failed", "exception"])
def test_v15_real_recorder_roundtrip_preserves_full_vector_costs_and_censoring(tmp_path, monkeypatch, fault):
    args, state = harness(tmp_path, monkeypatch, fault=fault)
    upgrade_args(args)
    s = session(args)
    options = s.observe(0)
    assert options.menu.feature_version == 15
    selected = next(b for b in options.bindings if b.kind is GoalKind.DEVELOP_TEAM)
    vector = options.menu.candidate_vector(options.bindings.index(selected), feature_version=15)
    plan = s.consequence.begin(options, selected, preflight_only=True)
    assert plan["schema"] == "pokemon.red.challenge-consequence-plan.v8"
    assert plan["feature_version"] == 15
    assert args["emulator"].frame_count == 0
    assert vector[-28:] == (0.,) * 28  # No future matchup invented for the dose.
    if fault == "exception":
        with pytest.raises(RuntimeError, match="interrupted"):
            selected.execute()
    else:
        selected.verify(selected.execute())
        if fault != "dose_failed":
            after = s.observe(1)
            challenge = next(b for b in after.bindings if b.kind is GoalKind.ADVANCE_STORY)
            challenge.verify(challenge.execute())
    result = s.consequence.finish()
    row = recorder.load_challenge_consequence(
        args["store"], declaration_sha256=result["declaration_sha256"],
        result_sha256=canonical_sha256(result),
    )
    assert row.feature_version == 15 and row.features == vector
    assert row.document()["schema"] == "pokemon.player.challenge-consequence.v5"
    assert ConsequenceExample.from_document(row.document()) == row
    if fault == "exception":
        assert row.outcome is None and row.censor_reason
    else:
        assert row.outcome.actions == (2 if fault == "dose_failed" else 3)
        assert row.outcome.frames == (4 if fault == "dose_failed" else 6)
        assert row.outcome.restorations == 1
        assert row.outcome.completed is (fault == "win")
    assert not args["emulator"].pressed_buttons


@pytest.mark.parametrize("fault", ["version", "missing_matchup", "frames"])
def test_v15_readback_does_not_accept_rehashed_feature_or_input_omission(tmp_path, monkeypatch, fault):
    args, _ = harness(tmp_path, monkeypatch, fault="win")
    upgrade_args(args)
    s = session(args)
    for ordinal, kind in enumerate((GoalKind.DEVELOP_TEAM, GoalKind.ADVANCE_STORY)):
        options = s.observe(ordinal)
        b = next(b for b in options.bindings if b.kind is kind)
        b.verify(b.execute())
    result = copy.deepcopy(s.consequence.finish())
    if fault == "version":
        result["row"]["feature_version"] = 10
    elif fault == "missing_matchup":
        result["row"]["features"] = result["row"]["features"][:-28]
    else:
        result["phases"][-1]["after"]["frames"] += 1
    digest = canonical_sha256(result)
    args["store"].publish_sealed_record("rcc-result-" + digest,
        kind="red_challenge_consequence_result", record=result)
    with pytest.raises(ValueError):
        recorder.load_challenge_consequence(args["store"],
            declaration_sha256=result["declaration_sha256"], result_sha256=digest)


@pytest.mark.parametrize("prefer", ["kind.develop", "kind.unlock_access"])
def test_v15_composed_continuous_player_uses_real_parent_child_and_exact_witness(tmp_path, monkeypatch, prefer):
    args, state = greedy_native_args(tmp_path, monkeypatch)
    upgrade_args(args)
    args["consequence_head"] = dispatch_head(prefer=prefer)
    monkeypatch.setattr(LivingDexOptionValueModel, "scores",
        lambda self, observed, utility: tuple(float(c.features.kind is LivingDexOptionKind.UNLOCK_ACCESS)
                                             for c in observed.candidates))
    observed_choices = []
    select = composition.select_branch_recovery_live_option

    def capture_choice(*a, **kw):
        choice = select(*a, **kw)
        observed_choices.append(choice)
        return choice
    monkeypatch.setattr(composition, "select_branch_recovery_live_option", capture_choice)
    result = native.run_native_continuous_player(**args)
    assert result["executed_decisions"] == 1
    assert result["strategic_policy_queries"] == 2
    choice = observed_choices[0]
    assert choice.branch_recovery.parent.selected_binding.kind is GoalKind.ADVANCE_STORY
    assert choice.branch_recovery.parent.options.menu.feature_version == 15
    assert choice.branch_recovery.child is not None
    parent = composition.selected_preparation_parent(choice)
    if prefer == "kind.develop":
        assert state["trained"] and not state["challenge"]
        assert parent is choice.branch_recovery.parent.selected_binding
        assert parent.story_objective_ref == "private-combat-goal"
        assert choice.options.menu.candidates[choice.selected_candidate_index].matchup is None
    else:
        assert state["challenge"] and not state["trained"] and parent is None
    plan = json.loads((args["output"] / "native-plan.json").read_text())
    assert plan["consequence_feature_version"] == 15
    assert not args["emulator"].pressed_buttons


def test_v11_is_derived_model_version_not_observed_menu_or_raw_record(tmp_path, monkeypatch):
    args, _ = harness(tmp_path, monkeypatch)
    # V11 is derived from the V9 workload-bearing observed menu.
    args['model'] = upgrade_option_value_model_for_level_workload(args['model'])
    options = session(args).observe(0)
    head = dispatch_head(version=11)
    assert options.menu.feature_version == 9
    assert all(np.isfinite(s) for s in head.scores(
        options.menu, challenge_refs=("same",) * len(options.bindings)))
    with pytest.raises(ValueError, match="raw V11"):
        ConsequenceExample("a" * 64, "b" * 64, (0.,) * len(option_feature_names(11)),
                           None, "synthetic censor", feature_version=11)




def unbound_hierarchy_args(tmp_path, monkeypatch, *, second_parent=True):
    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
    from pokemon_red_completion.player_option_challenge import OptionChallenge
    args, state = greedy_native_args(tmp_path, monkeypatch)
    upgrade_args(args)
    original = args["enumerate_bindings"]
    challenge = args["observe_challenges"]

    def bindings(*a, **kw):
        result = original(*a, **kw)
        if not second_parent:
            return result
        combat = next(b for b in result.bindings if b.kind is GoalKind.ADVANCE_STORY)
        other = replace(combat, kind=GoalKind.EXPLORE, binding_ref="other-real-explore",
                        story_objective_ref=None)
        return GoalBindingSet(result.opportunities + (other.opportunity,),
                              result.bindings + (other,))

    def challenges(*a, **kw):
        result = dict(challenge(*a, **kw))
        result.pop("train", None)  # Global level dose has no declared parent.
        if second_parent:
            result["other-real-explore"] = OptionChallenge(False, False, 0., 0., 0.)
        return result

    args["enumerate_bindings"] = bindings
    args["observe_challenges"] = challenges
    args["observe_matchups"] = lambda rt, bs, *_: {
        b.binding_ref: OptionMatchup((0.,) * 27) for b in bs.bindings
        if b.kind is GoalKind.ADVANCE_STORY and b.binding_ref != "other-real-explore"}
    args["consequence_head"] = dispatch_head()
    args["defer_unbound_preparation"] = True
    return args, state


def test_opt_in_hierarchy_uses_observed_model_parent_and_preserves_unbound_dose(tmp_path, monkeypatch):
    args, state = unbound_hierarchy_args(tmp_path, monkeypatch)
    scored = []

    def score(self, observed, utility):
        scored.append(observed)
        return tuple(float(c.challenge is not None and c.challenge.combat_required)
                     if i in observed.available_indices else None
                     for i, c in enumerate(observed.candidates))

    monkeypatch.setattr(LivingDexOptionValueModel, "scores", score)
    choices = []
    select = composition.select_branch_recovery_live_option
    def capture(*a, **kw):
        chosen = select(*a, **kw)
        choices.append(chosen)
        return chosen
    monkeypatch.setattr(composition, "select_branch_recovery_live_option", capture)
    result = native.run_native_continuous_player(**args)
    assert result["executed_decisions"] == 1 and result["strategic_policy_queries"] == 2
    assert state["trained"] and not state["challenge"]
    choice = choices[0]
    dose = next(i for i, b in enumerate(choice.options.bindings)
                if b.kind is GoalKind.DEVELOP_TEAM)
    assert choice.options.menu.candidates[dose].challenge is None
    assert choice.branch_recovery.parent.probabilities[dose] == 0.
    assert choice.branch_recovery.parent.scores[dose] is None
    assert all(scored[0].candidates[i].preparation is None for i in scored[0].available_indices)
    assert "other-real-explore" in {b.binding_ref for b in choice.branch_recovery.parent.options.bindings}
    parent = composition.selected_preparation_parent(choice)
    assert parent is choice.branch_recovery.parent.selected_binding
    assert parent.story_objective_ref == "private-combat-goal"
    assert choice.branch_recovery.child.selected_binding is choice.options.binding(dose)
    assert choice.public_dict()["branch_recovery"]["defer_unbound_preparation"] is True
    plan = json.loads((args["output"] / "native-plan.json").read_text())
    assert plan["defer_unbound_preparation"] is True
    assert not args["emulator"].pressed_buttons


def test_opt_in_hierarchy_refuses_sole_parent_without_input_or_hidden_fallback(tmp_path, monkeypatch):
    args, state = unbound_hierarchy_args(tmp_path, monkeypatch, second_parent=False)
    result = native.run_native_continuous_player(**args)
    assert result["executed_decisions"] == 0
    assert result["stop_reason"] == "consequence_context_unavailable"
    assert not state["trained"] and not state["challenge"]
    assert args["emulator"].frame_count == 0
    assert not args["emulator"].pressed_buttons


def test_default_unbound_preparation_keeps_missing_parent_instead_of_inferring(tmp_path, monkeypatch):
    args, state = unbound_hierarchy_args(tmp_path, monkeypatch)
    args["defer_unbound_preparation"] = False
    monkeypatch.setattr(LivingDexOptionValueModel, "scores",
        lambda self, observed, utility: tuple(float(c.features.kind is LivingDexOptionKind.DEVELOP)
                                             for c in observed.candidates))
    choices = []
    select = composition.select_branch_recovery_live_option
    def capture(*a, **kw):
        choice = select(*a, **kw)
        choices.append(choice)
        return choice
    monkeypatch.setattr(composition, "select_branch_recovery_live_option", capture)
    result = native.run_native_continuous_player(**args)
    assert result["executed_decisions"] == 1 and result["strategic_policy_queries"] == 1
    assert state["trained"] and not state["challenge"]
    assert choices[0].branch_recovery.child is None
    assert composition.selected_preparation_parent(choices[0]) is None


@pytest.mark.parametrize("fault", ["not_boolean", "no_permission", "not_greedy", "no_head"])
def test_opt_in_hierarchy_rejects_incomplete_authority_before_input(tmp_path, monkeypatch, fault):
    args, state = unbound_hierarchy_args(tmp_path, monkeypatch)
    if fault == "not_boolean":
        args["defer_unbound_preparation"] = 1
    elif fault == "no_permission":
        args["allow_greedy_branch_recovery"] = False
    elif fault == "not_greedy":
        args["greedy_selection"] = False
    else:
        args["consequence_head"] = None
    with pytest.raises((TypeError, ValueError)):
        native.run_native_continuous_player(**args)
    assert args["emulator"].frame_count == 0
    assert not state["trained"] and not state["challenge"]




def test_opt_in_preserves_mandatory_safety_even_when_deferral_would_leave_one_parent(tmp_path, monkeypatch):
    from test_red_branch_recovery import menu
    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
    options, _, _, runtime = menu(tmp_path, monkeypatch)
    keep = tuple(i for i, b in enumerate(options.bindings)
                 if b.kind in (GoalKind.DEVELOP_TEAM, GoalKind.RESTORE_TEAM))
    bindings = tuple(options.bindings[i] for i in keep)
    original = GoalBindingSet(tuple(b.opportunity for b in bindings), bindings)
    options = replace(options, original_bindings=original,
        situation=replace(options.situation, safety_pressure=1.),
        menu=replace(options.menu, candidates=tuple(
            replace(options.menu.candidates[i], challenge=None) if options.bindings[i].kind is GoalKind.DEVELOP_TEAM
            else options.menu.candidates[i] for i in keep)),
        bindings=bindings, ordinary_binding_refs=frozenset(b.binding_ref for b in bindings))
    args, _ = greedy_native_args(tmp_path / "model", monkeypatch)
    # Retain the existing V7 head; this test isolates unchanged safety authority.
    monkeypatch.setattr(LivingDexOptionValueModel, "scores",
        lambda *a: pytest.fail("mandatory safety must precede model selection"))
    monkeypatch.setattr(ChallengeConsequenceHead, "scores",
        lambda *a, **kw: pytest.fail("mandatory safety must precede consequence selection"))
    choice = composition.select_branch_recovery_live_option(
        args["model"], options, args["consequence_head"], objective_ref="private-combat-goal",
        seed=1, greedy_selection=True, defer_unbound_preparation=True)
    assert choice.selected_binding.kind is GoalKind.RESTORE_TEAM
    assert choice.public_dict()["branch_recovery"]["model_queries"] == 0
    assert composition.selected_preparation_parent(choice) is None
    assert not runtime.recorder.trace


def test_exact_witness_keeps_model_selected_binding_when_two_challenges_have_equal_facts(tmp_path, monkeypatch):
    from test_red_branch_recovery import menu
    from pokemon_red_completion.player_option_level_workload import OptionLevelWorkload
    options, first, _, runtime = menu(tmp_path, monkeypatch)
    second = next(i for i, b in enumerate(options.bindings)
                  if b.story_objective_ref == "private-travel-goal")
    bindings = tuple(replace(b, story_objective_ref="private-second-combat")
                     if i == second else b for i, b in enumerate(options.bindings))
    candidates = []
    for i, c in enumerate(options.menu.candidates):
        if c.preparation is not None:
            c = replace(c, challenge=None, level_workload=OptionLevelWorkload(
                c.preparation.current_level, c.preparation.target_level, c.preparation.remaining_xp))
        if i in (first, second):
            c = replace(c, challenge=options.menu.candidates[first].challenge,
                        matchup=OptionMatchup((0.,) * 27))
        candidates.append(c)
    options = replace(options, bindings=bindings,
                      menu=replace(options.menu, candidates=tuple(candidates)))
    args, _ = greedy_native_args(tmp_path / "model", monkeypatch)
    upgrade_args(args)
    monkeypatch.setattr(LivingDexOptionValueModel, "scores",
        lambda self, observed, utility: tuple(float(i == second) if i in observed.available_indices else None
                                             for i, _ in enumerate(observed.candidates)))
    choice = composition.select_branch_recovery_live_option(
        args["model"], options, dispatch_head(), objective_ref=("private-combat-goal", "private-second-combat"),
        seed=1, greedy_selection=True, defer_unbound_preparation=True)
    witness = composition.selected_preparation_parent(choice)
    assert witness is options.binding(second)
    assert witness is not options.binding(first)
    assert choice.branch_recovery.child is not None
    assert [b for b in choice.branch_recovery.child.options.bindings
            if b.kind is GoalKind.ADVANCE_STORY] == [options.binding(second)]
    assert not runtime.recorder.trace

