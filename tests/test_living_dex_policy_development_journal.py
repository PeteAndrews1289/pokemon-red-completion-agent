from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from test_living_dex_causal_journal import _scenario, _store_and_registry
from test_living_dex_policy_development import _development_scenario, _model

from pokemon_red_completion.living_dex_causal_journal import LivingDexCausalScenario
from pokemon_red_completion.living_dex_goal_policy import (
    DEFAULT_LIVING_DEX_GOAL_UTILITY,
)
from pokemon_red_completion.living_dex_policy_development_journal import (
    LivingDexPolicyDevelopmentDisposition,
    LivingDexPolicyDevelopmentJournalError,
    LivingDexPolicyDevelopmentTerminalStatus,
    execute_living_dex_policy_development,
)


def test_settled_model_choice_recovers_without_second_runtime(
    tmp_path: Path,
) -> None:
    store, registry = _store_and_registry(tmp_path)
    scenario, harness = _development_scenario()
    model = _model()

    receipt = execute_living_dex_policy_development(
        scenario,
        model,
        utility=DEFAULT_LIVING_DEX_GOAL_UTILITY,
        expected_model_sha256=model.model_sha256,
        store=store,
        claim_registry=registry,
    )

    assert receipt.disposition is LivingDexPolicyDevelopmentDisposition.EXECUTED_SETTLED
    assert receipt.result is not None
    assert receipt.result.selected_candidate_index == receipt.decision.selected_candidate_index
    assert harness.resolver_calls == [receipt.decision.selected_candidate_index]
    assert harness.executions == [receipt.decision.selected_candidate_index]
    assert harness.observations == ["observed"]
    assert receipt.public_dict()["development_outcomes_opened"] == 1
    assert receipt.public_dict()["training_targets_emitted"] == 0

    recovered = execute_living_dex_policy_development(
        scenario,
        model,
        utility=DEFAULT_LIVING_DEX_GOAL_UTILITY,
        expected_model_sha256=model.model_sha256,
        store=store,
        claim_registry=registry,
    )
    assert recovered.disposition is LivingDexPolicyDevelopmentDisposition.RECOVERED_COMPLETE
    assert recovered.result == receipt.result
    assert harness.resolver_calls == [receipt.decision.selected_candidate_index]
    assert harness.executions == [receipt.decision.selected_candidate_index]


def test_release_interruption_is_terminal_and_never_reexecutes(tmp_path: Path) -> None:
    store, registry = _store_and_registry(tmp_path)
    scenario, harness = _development_scenario()
    model = _model()

    def failpoint(stage: str) -> None:
        if stage == "after_controller_release":
            raise RuntimeError("power loss")

    with pytest.raises(RuntimeError, match="power loss"):
        execute_living_dex_policy_development(
            scenario,
            model,
            utility=DEFAULT_LIVING_DEX_GOAL_UTILITY,
            expected_model_sha256=model.model_sha256,
            store=store,
            claim_registry=registry,
            failpoint=failpoint,
        )
    assert harness.executions == []

    recovered = execute_living_dex_policy_development(
        scenario,
        model,
        utility=DEFAULT_LIVING_DEX_GOAL_UTILITY,
        expected_model_sha256=model.model_sha256,
        store=store,
        claim_registry=registry,
    )
    assert recovered.disposition is (
        LivingDexPolicyDevelopmentDisposition.RECOVERED_INTERRUPTED
    )
    assert recovered.terminal.status is (
        LivingDexPolicyDevelopmentTerminalStatus.POSTRELEASE_INTERRUPTED
    )
    assert harness.resolver_calls == [recovered.decision.selected_candidate_index]
    assert harness.executions == []


def test_preinput_failure_is_terminal_without_outcome_or_retry(tmp_path: Path) -> None:
    store, registry = _store_and_registry(tmp_path)
    train, harness = _scenario("development-construction", resolver_failure=True)
    scenario = LivingDexCausalScenario(
        replace(train.identity, partition="development"),
        train.menu,
        train.binding_sha256s,
        train.origin_observation,
        train.effect_meter,
        train.resolve_selected,
        train.observe_after,
    )
    model = _model()

    failed = execute_living_dex_policy_development(
        scenario,
        model,
        utility=DEFAULT_LIVING_DEX_GOAL_UTILITY,
        expected_model_sha256=model.model_sha256,
        store=store,
        claim_registry=registry,
    )
    assert failed.disposition is (
        LivingDexPolicyDevelopmentDisposition.EXECUTED_PREINPUT_FAILED
    )
    assert failed.result is None
    assert failed.public_dict()["development_outcomes_opened"] == 0
    assert harness.resolver_calls == [failed.decision.selected_candidate_index]

    recovered = execute_living_dex_policy_development(
        scenario,
        model,
        utility=DEFAULT_LIVING_DEX_GOAL_UTILITY,
        expected_model_sha256=model.model_sha256,
        store=store,
        claim_registry=registry,
    )
    assert recovered.disposition is (
        LivingDexPolicyDevelopmentDisposition.RECOVERED_PREINPUT_FAILED
    )
    assert harness.resolver_calls == [failed.decision.selected_candidate_index]


def test_train_partition_fails_before_claim_or_model_execution(tmp_path: Path) -> None:
    store, registry = _store_and_registry(tmp_path)
    scenario, harness = _scenario("train-rejected")
    model = _model()

    with pytest.raises(
        LivingDexPolicyDevelopmentJournalError,
        match="another partition",
    ):
        execute_living_dex_policy_development(
            scenario,
            model,
            utility=DEFAULT_LIVING_DEX_GOAL_UTILITY,
            expected_model_sha256=model.model_sha256,
            store=store,
            claim_registry=registry,
        )
    assert harness.resolver_calls == []
    assert harness.executions == []
