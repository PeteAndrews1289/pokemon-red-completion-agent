"""Actual selector/replay tests, with synthetic rows and no native adoption."""

import copy
import json
from dataclasses import replace

import pytest
from test_player_sequence_value import UTILITY, ZERO
from test_red_live_option_menu import (
    _binding,
    _model,
    _no_ordinary_bindings,
    _ordinary_bindings,
    _situation,
)

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionValueModel,
    upgrade_option_value_model_for_challenge,
    upgrade_option_value_model_for_readiness,
)
from pokemon_red_completion.player_sequence_policy import SequenceChoiceContext, SequencePolicy
from pokemon_red_completion.player_sequence_value import SequenceRegressionRow, fit_sequence_value
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.recorded_branch_history import RecordedBranchHistory
from pokemon_red_completion.red_live_option_menu import (
    RedLiveOptionSelectionMode,
    build_red_live_option_set,
    select_red_live_option,
)
from pokemon_red_completion.red_player_story_menu import plural_story_bindings
from pokemon_red_completion.red_recorded_selection_authority import (
    record_selection_authority,
    replay_selection_authority,
)
from pokemon_red_completion.resource_economy_observation import EconomySnapshot


def setup(*, safety=False):
    calls = []
    model = upgrade_option_value_model_for_challenge(
        upgrade_option_value_model_for_readiness(_model())
    )
    situation = _situation(resources=0.1, safety=0.99 if safety else 0.1)
    branches = tuple(
        _binding(GoalKind.ADVANCE_STORY, binding_ref=f"private-branch-{i}", calls=calls)
        for i in range(2)
    )
    ordinary, supplements = plural_story_bindings(
        _ordinary_bindings(calls) if safety else _no_ordinary_bindings(), branches, situation
    )
    options = build_red_live_option_set(
        situation=situation,
        binding_set=ordinary,
        supplements=supplements,
        model_feature_version=6,
        ordering_seed_sha256="a" * 64,
        economy_snapshot=EconomySnapshot(427, ()),
        target_cash=0,
    )
    histories = tuple(
        ZERO if i == 0 else RecordedBranchHistory(i, 100, 1000, 10, 0, 1, 0, 0)
        for i in range(len(options.bindings))
    )
    context = SequenceChoiceContext(options.menu.policy_sha256, "c" * 64, histories)
    rows = tuple(
        SequenceRegressionRow(f"{i:064x}", vector, (float(i > 0),) + (0.0,) * 5 + (None,), "train")
        for i, vector in enumerate(context.vectors(options.menu))
    )
    head = fit_sequence_value(rows, ridge=1.0, horizon=4, behavior_model_sha256=model.model_sha256)
    policy = SequencePolicy(model.model_sha256, head, UTILITY, 2.0)
    return model, options, policy, context, calls


def select(model, options, policy, context):
    return select_red_live_option(
        model, options, seed=23, sequence_policy=policy, sequence_context=context
    )


def test_history_changes_real_selector_probabilities_and_keeps_binding_ownership():
    model, options, policy, context, calls = setup()
    baseline = select_red_live_option(model, options, seed=23)
    choice = select(model, options, policy, context)
    assert baseline.mode is RedLiveOptionSelectionMode.EQUIVALENT_EXPLORATION
    assert baseline.probabilities == (0.5, 0.5)
    assert choice.mode is RedLiveOptionSelectionMode.MODEL_EXPLORATION
    assert choice.scores[1] > choice.scores[0]
    assert choice.probabilities[1] > 0.5 > choice.probabilities[0]
    assert choice.model_sha256 == policy.model_sha256 != baseline.model_sha256
    assert choice.selected_binding is options.binding(choice.selected_candidate_index)
    assert select(model, options, policy, context).public_dict() == choice.public_dict()
    assert not calls  # prediction/replay never executes any binding
    assert "private-branch" not in json.dumps(choice.public_dict())
    assert "sequence" not in baseline.public_dict()
    assert select_red_live_option(model, options, seed=23).public_dict() == baseline.public_dict()


def test_safety_remains_forced_without_querying_either_head(monkeypatch):
    model, options, policy, context, calls = setup(safety=True)

    def forbidden(*args, **kwargs):
        raise AssertionError("safety queried scores")

    monkeypatch.setattr(LivingDexOptionValueModel, "scores", forbidden)
    monkeypatch.setattr(SequencePolicy, "scores", forbidden)
    choice = select(model, options, policy, context)
    assert choice.mode is RedLiveOptionSelectionMode.DETERMINISTIC_SAFETY
    assert choice.selected_binding.kind is GoalKind.RESTORE_TEAM
    assert all(s is None for s in choice.scores) and not calls


def test_equal_full_inputs_stay_equivalent_without_query(monkeypatch):
    model, options, policy, context, _ = setup()
    context = replace(context, histories=(ZERO, ZERO))

    def forbidden(*args, **kwargs):
        raise AssertionError("equivalent inputs queried scores")

    monkeypatch.setattr(SequencePolicy, "scores", forbidden)
    choice = select(model, options, policy, context)
    assert choice.mode is RedLiveOptionSelectionMode.EQUIVALENT_EXPLORATION
    assert choice.probabilities == (0.5, 0.5) and choice.model_sha256 == policy.model_sha256


def test_reordering_and_private_renaming_do_not_change_semantic_preferences():
    model, options, policy, context, _ = setup()
    menu = replace(
        options.menu,
        candidates=tuple(
            replace(c, binding_ref=f"renamed-{i}")
            for i, c in enumerate(reversed(options.menu.candidates))
        ),
    )
    reverse = replace(
        context, menu_sha256=menu.policy_sha256, histories=tuple(reversed(context.histories))
    )
    assert policy.scores(model, menu, reverse) == tuple(
        reversed(policy.scores(model, options.menu, context))
    )


@pytest.mark.parametrize(
    "fault",
    [
        "menu",
        "width",
        "negative",
        "bool",
        "prefix",
        "no_context",
        "no_policy",
        "baseline",
        "utility",
        "mix",
        "unknown_loss",
    ],
)
def test_mismatched_or_invalid_policy_inputs_reject_before_scoring(fault):
    model, options, policy, context, calls = setup()
    with pytest.raises(ValueError):
        if fault == "menu":
            context = replace(context, menu_sha256="f" * 64)
        elif fault == "width":
            context = replace(context, histories=context.histories[:1])
        elif fault in {"negative", "bool"}:
            context = replace(
                context,
                histories=(replace(ZERO, attempts=-1 if fault == "negative" else True), ZERO),
            )
        elif fault == "prefix":
            context = replace(context, prefix_sha256="bad")
        elif fault == "no_context":
            context = None
        elif fault == "no_policy":
            policy = None
        elif fault == "baseline":
            policy = replace(policy, baseline_sha256="d" * 64)
        elif fault == "utility":
            policy = replace(
                policy,
                immediate_utility=replace(policy.immediate_utility, action_cost_weight=123.0),
            )
        elif fault == "mix":
            policy = replace(policy, exploration_mix=0.9)
        else:
            policy = replace(policy, sequence_utility=(*UTILITY[:-1], -1.0))
        select(model, options, policy, context)
    assert not calls


def test_combined_policy_roundtrip_pins_weights_utility_and_both_models():
    model, options, policy, context, _ = setup()
    document = json.loads(json.dumps(policy.document()))
    restored = SequencePolicy.from_document(document, expected_sha256=policy.model_sha256)
    assert (
        select(model, options, restored, context).public_dict()
        == select(model, options, policy, context).public_dict()
    )
    assert replace(policy, sequence_weight=3.0).model_sha256 != policy.model_sha256
    assert replace(policy, exploration_mix=0.1).model_sha256 != policy.model_sha256
    document["live_policy_adopted"] = True
    with pytest.raises(ValueError):
        SequencePolicy.from_document(document, expected_sha256=canonical_sha256(document))
    with pytest.raises(ValueError):
        SequencePolicy.from_document(document, expected_sha256=policy.model_sha256)


def records():
    model, options, policy, context, calls = setup()
    choice = select(model, options, policy, context)
    intent = dict(
        menu=options.public_dict(),
        selection_seed=23,
        model_sha256=policy.model_sha256,
        sequence_context=context.document(),
        private_selection_authority=record_selection_authority(
            options, allow_earning_exploration=False
        ),
    )
    return model, policy, json.loads(json.dumps(intent)), choice, calls


def test_inert_replay_checks_frozen_composition_history_probabilities_and_executor():
    model, policy, intent, choice, calls = records()
    assert (
        replay_selection_authority(
            model,
            intent,
            choice.public_dict(),
            allow_earning_exploration=False,
            sequence_policy=policy,
        )
        == choice.selected_binding.binding_ref
    )
    assert not calls


@pytest.mark.parametrize(
    "fault", ["history", "prefix", "score", "probability", "identity", "policy", "baseline_only"]
)
def test_changed_composite_choice_or_history_cannot_replay_as_baseline(fault):
    model, policy, intent, choice, calls = records()
    decision = copy.deepcopy(choice.public_dict())
    if fault == "history":
        intent["sequence_context"]["histories"][0]["attempts"] += 1
    elif fault == "prefix":
        intent["sequence_context"]["prefix_sha256"] = "d" * 64
    elif fault == "score":
        decision["scores"][0] += 0.1
    elif fault == "probability":
        decision["probabilities"].reverse()
    elif fault == "identity":
        intent["model_sha256"] = model.model_sha256
    elif fault == "policy":
        policy = replace(policy, sequence_weight=3.0)
    else:
        policy = None
    with pytest.raises(ValueError):
        replay_selection_authority(
            model, intent, decision, allow_earning_exploration=False, sequence_policy=policy
        )
    assert not calls
