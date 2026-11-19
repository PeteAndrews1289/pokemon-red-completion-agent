"""A zero-contribution head must preserve the declared baseline sampler."""

from dataclasses import replace

import pytest
from test_red_live_option_menu import _mixed, _model, _situation

from pokemon_red_completion.living_dex_option_value import (
    upgrade_option_value_model_for_challenge,
    upgrade_option_value_model_for_readiness,
)
from pokemon_red_completion.player_sequence_policy import SequenceChoiceContext, SequencePolicy
from pokemon_red_completion.player_sequence_value import SequenceValueHead, sequence_feature_width
from pokemon_red_completion.recorded_branch_history import RecordedBranchHistory
from pokemon_red_completion.red_live_option_menu import (
    RedLiveOptionMenuError,
    RedLiveOptionSelectionMode,
    select_red_live_option,
)

ZERO = RecordedBranchHistory(0, 0, 0, 0, 0, 0, 0, 0)


def case(copies=1):
    model = upgrade_option_value_model_for_challenge(
        upgrade_option_value_model_for_readiness(_model())
    )
    old = replace(_mixed([]), situation=_situation(resources=0.1, safety=0.1))
    candidates = []
    bindings = []
    exemplar = old.menu.candidates[0].features.kind
    for c, b in zip(old.menu.candidates, old.bindings, strict=True):
        for _i in range(copies if c.features.kind == exemplar else 1):
            ref = f"opaque-{len(candidates)}"
            candidates.append(replace(c, binding_ref=ref))
            bindings.append(replace(b, binding_ref=ref))
    options = replace(
        old,
        menu=replace(old.menu, candidates=tuple(candidates)),
        bindings=tuple(bindings),
        ordinary_binding_refs=frozenset(),
    )
    head = SequenceValueHead(
        ((0.0,) * (sequence_feature_width(6) + 1),) + (None,) * 6,
        (2,) + (0,) * 6,
        "c" * 64,
        1.0,
        4,
        model.model_sha256,
    )
    policy = SequencePolicy(
        model.model_sha256,
        head,
        (1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        1.0,
        kind_balanced_exploration=True,
    )
    context = SequenceChoiceContext(options.menu.policy_sha256, "b" * 64, (ZERO,) * len(candidates))
    return model, options, policy, context


@pytest.mark.parametrize("copies", [1, 2, 8])
@pytest.mark.parametrize("seed", [0, 17, 31])
def test_zero_head_preserves_exact_mixed_family_probabilities_and_choice(copies, seed):
    model, options, policy, context = case(copies)
    baseline = select_red_live_option(model, options, seed=seed, allow_earning_exploration=True)
    candidate = select_red_live_option(
        model,
        options,
        seed=seed,
        allow_earning_exploration=True,
        sequence_policy=policy,
        sequence_context=context,
    )
    assert baseline.mode is candidate.mode is RedLiveOptionSelectionMode.MODEL_EXPLORATION
    assert baseline.scores == candidate.scores and baseline.probabilities == candidate.probabilities
    assert baseline.selected_candidate_index == candidate.selected_candidate_index
    assert candidate.kind_balanced_exploration
    assert candidate.public_dict()["policy_id"] == "red-live-kind-balanced-sequence-option-v1"
    assert (
        candidate.public_dict()["sampling_rule"] == "mean_exponential_weight_per_public_option_kind"
    )


def test_opt_in_has_distinct_identity_and_legacy_document_stays_exact():
    _, _, policy, _ = case()
    legacy = replace(policy, kind_balanced_exploration=False)
    assert "kind_balanced_exploration" not in legacy.document()
    assert legacy.model_sha256 != policy.model_sha256
    assert (
        SequencePolicy.from_document(policy.document(), expected_sha256=policy.model_sha256)
        == policy
    )
    assert (
        SequencePolicy.from_document(legacy.document(), expected_sha256=legacy.model_sha256)
        == legacy
    )


@pytest.mark.parametrize("value", [None, 0, 1, "yes"])
def test_sampler_declaration_requires_real_boolean(value):
    _, _, policy, _ = case()
    with pytest.raises(ValueError):
        replace(policy, kind_balanced_exploration=value)


def test_declared_balancing_cannot_be_silently_disabled_at_selection():
    model, options, policy, context = case()
    with pytest.raises(RedLiveOptionMenuError, match="sampler differs"):
        select_red_live_option(
            model,
            options,
            seed=1,
            allow_earning_exploration=True,
            sequence_policy=policy,
            sequence_context=context,
            kind_balanced_exploration=False,
        )
