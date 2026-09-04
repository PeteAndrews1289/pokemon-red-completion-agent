from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from test_living_dex_causal_journal import _scenario

from pokemon_red_completion.living_dex_causal_journal import LivingDexCausalScenario
from pokemon_red_completion.living_dex_goal_policy import (
    DEFAULT_LIVING_DEX_GOAL_UTILITY,
)
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_FEATURE_NAMES,
    LIVING_DEX_OPTION_OUTCOME_NAMES,
    LivingDexOptionCandidate,
    LivingDexOptionContext,
    LivingDexOptionValueModel,
    LivingDexPredictedOutcome,
)
from pokemon_red_completion.living_dex_policy_development import (
    LivingDexPolicyDevelopmentError,
    commit_living_dex_policy_development_decision,
)


def _model() -> LivingDexOptionValueModel:
    width = len(LIVING_DEX_OPTION_FEATURE_NAMES)
    targets = len(LIVING_DEX_OPTION_OUTCOME_NAMES)
    return LivingDexOptionValueModel(
        coefficients=np.zeros((width, targets), dtype=np.float64),
        intercept=np.asarray([0.8, 0.6, 0.4, 0.1, 0.1, 0.1, 0.1, 0.1, 0.0]),
        feature_mean=np.zeros(width),
        feature_scale=np.ones(width),
        train_dataset_sha256="a" * 64,
        settled_examples=18,
        censored_examples=0,
        ridge=0.25,
        maximum_importance_weight=4.0,
    )


def _development_scenario() -> tuple[LivingDexCausalScenario, object]:
    scenario, harness = _scenario("policy-development")
    identity = replace(scenario.identity, partition="development")
    return (
        LivingDexCausalScenario(
            identity,
            scenario.menu,
            scenario.binding_sha256s,
            scenario.origin_observation,
            scenario.effect_meter,
            scenario.resolve_selected,
            scenario.observe_after,
        ),
        harness,
    )


def test_decision_scores_complete_held_menu_without_runtime_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario, harness = _development_scenario()
    model = _model()
    original = LivingDexOptionValueModel.predict_candidate
    predictions = 0

    def counted_prediction(
        self: LivingDexOptionValueModel,
        context: LivingDexOptionContext,
        candidate: LivingDexOptionCandidate,
    ) -> LivingDexPredictedOutcome:
        nonlocal predictions
        predictions += 1
        return original(self, context, candidate)

    monkeypatch.setattr(
        LivingDexOptionValueModel,
        "predict_candidate",
        counted_prediction,
    )

    decision = commit_living_dex_policy_development_decision(
        scenario,
        model,
        utility=DEFAULT_LIVING_DEX_GOAL_UTILITY,
        expected_model_sha256=model.model_sha256,
    )

    assert decision.selected_candidate_index == 0
    assert decision.candidate_scores[2] is None
    assert decision.predicted_outcomes[2] is None
    assert predictions == len(scenario.menu.available_indices)
    assert decision.public_dict()["training_targets_emitted"] == 0
    assert decision.public_dict()["teacher_queries"] == 0
    assert harness.resolver_calls == []
    assert harness.executions == []
    assert harness.observations == []
    assert harness.meter.controller_actions == 0
    assert harness.meter.emulator_frames == 0


def test_decision_rejects_train_partition_or_another_model_identity() -> None:
    train, _harness = _scenario("policy-train")
    model = _model()

    with pytest.raises(
        LivingDexPolicyDevelopmentError,
        match="another partition",
    ):
        commit_living_dex_policy_development_decision(
            train,
            model,
            utility=DEFAULT_LIVING_DEX_GOAL_UTILITY,
            expected_model_sha256=model.model_sha256,
        )
    with pytest.raises(
        LivingDexPolicyDevelopmentError,
        match="model identity",
    ):
        commit_living_dex_policy_development_decision(
            _development_scenario()[0],
            model,
            utility=DEFAULT_LIVING_DEX_GOAL_UTILITY,
            expected_model_sha256="f" * 64,
        )


def test_decision_mutation_and_private_binding_leak_fail_closed() -> None:
    scenario, _harness = _development_scenario()
    model = _model()
    decision = commit_living_dex_policy_development_decision(
        scenario,
        model,
        utility=DEFAULT_LIVING_DEX_GOAL_UTILITY,
        expected_model_sha256=model.model_sha256,
    )

    with pytest.raises(
        LivingDexPolicyDevelopmentError,
        match="does not replay",
    ):
        replace(decision, selected_candidate_index=1)
    encoded = str(decision.public_dict())
    assert "private.policy-development" not in encoded
    assert all(binding not in encoded for binding in scenario.binding_sha256s)
