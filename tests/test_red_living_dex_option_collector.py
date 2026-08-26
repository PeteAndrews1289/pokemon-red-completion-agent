from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace

import pytest
from test_red_living_dex_option_adapter import (
    ORDERING,
    PROBABILITY,
    SCENARIO,
    TARGETS,
    _budgets,
    _facts,
    _options,
    _snapshot,
)

from pokemon_red_completion.living_dex_option_value import (
    DEFAULT_MAX_IMPORTANCE_WEIGHT,
    LivingDexCensorReason,
    LivingDexObservedArmExample,
    LivingDexOutcomeStatus,
)
from pokemon_red_completion.red_collection import RED_SOLO_COLLECTION_CONTRACT
from pokemon_red_completion.red_living_dex_dependency_curriculum import (
    DependencySpecimenLedger,
)
from pokemon_red_completion.red_living_dex_option_adapter import (
    RedLivingDexAdaptedScenario,
    RedLivingDexOutcomeSnapshot,
    adapt_red_living_dex_options,
)
from pokemon_red_completion.red_living_dex_option_collector import (
    RedLivingDexBehaviorCommitment,
    RedLivingDexBehaviorDecision,
    RedLivingDexBehaviorIssuance,
    RedLivingDexExternalInterruption,
    RedLivingDexOptionCollectorError,
    collect_red_living_dex_observed_arm,
    issue_red_living_dex_behavior_commitment,
    red_living_dex_behavior_decision,
)


def _commitment(
    adapted: RedLivingDexAdaptedScenario,
    *,
    partition: str = "train",
    seed: str = PROBABILITY,
) -> RedLivingDexBehaviorCommitment:
    return RedLivingDexBehaviorCommitment(
        adapted.before.scenario_identity_sha256,
        partition,
        adapted.menu.policy_sha256,
        seed,
    )


def _adapt_with_calls(
    execute_calls: list[int],
    verify_calls: list[int],
) -> RedLivingDexAdaptedScenario:
    return adapt_red_living_dex_options(
        _snapshot(),
        _facts(),
        _budgets(),
        _options(execute_calls=execute_calls, verify_calls=verify_calls),
        ordering_seed_sha256=ORDERING,
    )


def _after(*, scenario: str = SCENARIO) -> RedLivingDexOutcomeSnapshot:
    return _snapshot(
        species=(TARGETS[0], TARGETS[1]),
        scenario=scenario,
        dependencies=3,
        consumables=8,
        health=70,
        irreversible=3,
        actions=350,
        frames=3_000,
        provenance="6" * 64,
    )


def _replace_option(
    adapted: RedLivingDexAdaptedScenario,
    index: int,
    *,
    execute: Callable[[], object] | None = None,
    verify_success: Callable[
        [DependencySpecimenLedger, DependencySpecimenLedger], bool
    ]
    | None = None,
) -> RedLivingDexAdaptedScenario:
    options = list(adapted.ordered_options)
    current = options[index]
    options[index] = replace(
        current,
        execute=current.execute if execute is None else execute,
        verify_success=(
            current.verify_success if verify_success is None else verify_success
        ),
    )
    return RedLivingDexAdaptedScenario(
        adapted.before,
        adapted.facts,
        adapted.budgets,
        adapted.provenance,
        adapted.menu,
        tuple(options),
        adapted.ordering_seed_sha256,
    )


def test_behavior_is_replayable_nonuniform_full_support_and_exercises_ips_cap() -> None:
    adapted = _adapt_with_calls([], [])

    first = red_living_dex_behavior_decision(
        adapted.menu,  # type: ignore[attr-defined]
        commitment=_commitment(adapted),
    )
    replay = red_living_dex_behavior_decision(
        adapted.menu,  # type: ignore[attr-defined]
        commitment=_commitment(adapted),
    )

    assert first == replay
    positive = [value for value in first.probabilities if value > 0.0]
    assert sorted(positive) == sorted((1 / 6, 2 / 6, 3 / 6))
    assert 1.0 / min(positive) > DEFAULT_MAX_IMPORTANCE_WEIGHT
    assert all(
        first.probabilities[index] == 0.0
        for index in range(len(first.probabilities))
        if index not in adapted.menu.available_indices  # type: ignore[attr-defined]
    )
    assert first.public_dict()["nonuniform"] is True


def test_behavior_issuer_uses_one_system_draw_and_binds_it_before_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapted = _adapt_with_calls([], [])
    draws: list[int] = []

    def token_hex(byte_count: int) -> str:
        draws.append(byte_count)
        return "a" * 64

    monkeypatch.setattr(
        "pokemon_red_completion.red_living_dex_option_collector.secrets.token_hex",
        token_hex,
    )
    commitment = issue_red_living_dex_behavior_commitment(
        adapted,
        partition="train",
    )
    decision = red_living_dex_behavior_decision(
        adapted.menu,
        commitment=commitment,
    )

    assert draws == [32]
    assert commitment.randomization_seed_sha256 == "a" * 64
    assert commitment.authenticated_issuance is True
    assert commitment.issuance_origin is RedLivingDexBehaviorIssuance.SYSTEM_CSPRNG
    assert commitment.menu_sha256 == adapted.menu.policy_sha256
    assert decision.commitment == commitment
    assert SCENARIO not in json.dumps(decision.public_dict(), sort_keys=True)

    wrong_scenario = replace(commitment, scenario_identity_sha256="9" * 64)
    with pytest.raises(RedLivingDexOptionCollectorError, match="scenario identity"):
        collect_red_living_dex_observed_arm(
            adapted,
            commitment=wrong_scenario,
            observe_after=_after,
        )
    assert not any(option.consumed for option in adapted.ordered_options)


def test_behavior_record_rejects_weight_and_draw_tampering() -> None:
    adapted = _adapt_with_calls([], [])
    decision = red_living_dex_behavior_decision(
        adapted.menu,
        commitment=_commitment(adapted),
    )
    reversed_weights = tuple(reversed(decision.integer_weights))
    total = sum(reversed_weights)
    reversed_probabilities = tuple(value / total for value in reversed_weights)
    with pytest.raises(RedLivingDexOptionCollectorError, match="weights do not replay"):
        RedLivingDexBehaviorDecision(
            decision.commitment,
            decision.available_indices,
            reversed_weights,
            reversed_probabilities,
            decision.selected_candidate_index,
        )

    wrong_selected = next(
        index
        for index in decision.available_indices
        if index != decision.selected_candidate_index
    )
    with pytest.raises(RedLivingDexOptionCollectorError, match="selection does not replay"):
        RedLivingDexBehaviorDecision(
            decision.commitment,
            decision.available_indices,
            decision.integer_weights,
            decision.probabilities,
            wrong_selected,
        )


def test_collected_example_rejects_a_behavior_record_bound_to_another_menu() -> None:
    adapted = _adapt_with_calls([], [])
    result = collect_red_living_dex_observed_arm(
        adapted,
        commitment=_commitment(adapted),
        observe_after=_after,
    )
    behavior = result.behavior
    other_menu_sha256 = "f" * 64
    tampered_commitment = replace(
        behavior.commitment,
        menu_sha256=other_menu_sha256,
    )
    tampered_behavior: RedLivingDexBehaviorDecision | None = None
    for selected_index in behavior.available_indices:
        try:
            tampered_behavior = RedLivingDexBehaviorDecision(
                tampered_commitment,
                behavior.available_indices,
                behavior.integer_weights,
                behavior.probabilities,
                selected_index,
            )
        except RedLivingDexOptionCollectorError:
            continue
        break
    assert tampered_behavior is not None
    tampered_example = LivingDexObservedArmExample(
        result.example.decision_sha256,
        result.example.partition,
        result.example.menu,
        tampered_behavior.selected_candidate_index,
        tampered_behavior.probabilities,
        result.example.outcome,
    )

    with pytest.raises(RedLivingDexOptionCollectorError, match="binding differs"):
        replace(
            result,
            behavior=tampered_behavior,
            example=tampered_example,
        )

def test_collector_executes_and_verifies_only_selected_arm_then_logs_real_costs() -> None:
    execute_calls: list[int] = []
    verify_calls: list[int] = []
    adapted = _adapt_with_calls(execute_calls, verify_calls)
    observer_calls = 0

    def observe() -> RedLivingDexOutcomeSnapshot:
        nonlocal observer_calls
        observer_calls += 1
        return _after()

    result = collect_red_living_dex_observed_arm(
        adapted,  # type: ignore[arg-type]
        commitment=_commitment(adapted),
        observe_after=observe,  # type: ignore[arg-type]
    )
    selected_option = adapted.ordered_options[result.behavior.selected_candidate_index]  # type: ignore[attr-defined]

    assert execute_calls == [int(selected_option.binding_ref.rsplit(".", 1)[1])]
    assert verify_calls == execute_calls
    assert observer_calls == 1
    assert sum(option.consumed for option in adapted.ordered_options) == 1  # type: ignore[attr-defined]
    assert result.example.outcome.status is LivingDexOutcomeStatus.SETTLED
    assert result.example.outcome.verified_success is True
    assert result.example.outcome.completion_gain == 1.0
    assert result.example.outcome.dependency_unlock_gain == pytest.approx(0.1)
    assert result.example.outcome.action_cost == pytest.approx(0.25)
    assert result.example.outcome.frame_cost == pytest.approx(0.2)
    assert result.example.outcome.resource_cost == pytest.approx(
        0.2 if selected_option.resource_pool_ref is not None else 0.0
    )
    assert result.example.outcome.party_cost == pytest.approx(0.1)
    assert result.example.outcome.storage_cost == pytest.approx(1 / 45)
    assert result.example.outcome.irreversible_loss == pytest.approx(0.25)
    assert result.example.public_dict()["selected_candidate_target_only"] is True
    assert result.public_dict()["unselected_action_targets"] == 0
    public = json.dumps(result.public_dict(), sort_keys=True).lower()
    for forbidden in ("private.red", "binding_ref", "family_ref", "location_ref", SCENARIO):
        assert forbidden not in public
    private = result.private_dict()
    assert private["scenario_identity_sha256"] == SCENARIO
    assert private["after_observer_provenance_sha256"] == "6" * 64
    assert len(private["selected_family_sha256"]) == 64  # type: ignore[arg-type]
    assert "private.red" not in json.dumps(private, sort_keys=True).lower()


def test_realized_living_collection_loss_overrides_a_positive_private_verifier() -> None:
    adapted = _adapt_with_calls([], [])

    result = collect_red_living_dex_observed_arm(
        adapted,
        commitment=_commitment(adapted),
        observe_after=lambda: _snapshot(
            species=(),
            dependencies=2,
            consumables=10,
            health=80,
            irreversible=4,
            actions=200,
            frames=2_000,
            provenance="8" * 64,
        ),
    )

    assert result.example.outcome.status is LivingDexOutcomeStatus.SETTLED
    assert result.example.outcome.verified_success is False
    assert result.example.outcome.completion_gain == 0.0
    assert result.example.outcome.irreversible_loss == pytest.approx(1 / len(TARGETS))


def test_ordinary_executor_exception_is_observed_once_and_settled_as_failure() -> None:
    adapted = _adapt_with_calls([], [])
    behavior = red_living_dex_behavior_decision(
        adapted.menu,  # type: ignore[attr-defined]
        commitment=_commitment(adapted),
    )
    observer_calls = 0

    def fail() -> object:
        raise RuntimeError("private selected-skill failure")

    def reject(_before: object, _after: object) -> bool:
        return False

    def observe() -> RedLivingDexOutcomeSnapshot:
        nonlocal observer_calls
        observer_calls += 1
        return _snapshot(provenance="7" * 64)

    adapted = _replace_option(
        adapted,
        behavior.selected_candidate_index,
        execute=fail,
        verify_success=reject,
    )
    result = collect_red_living_dex_observed_arm(
        adapted,  # type: ignore[arg-type]
        commitment=_commitment(adapted),
        observe_after=observe,  # type: ignore[arg-type]
    )

    assert result.selected_execution_raised is True
    assert observer_calls == 1
    assert result.example.outcome.status is LivingDexOutcomeStatus.SETTLED
    assert result.example.outcome.verified_success is False
    assert result.example.outcome.target_vector is not None
    assert "private selected-skill failure" not in json.dumps(result.public_dict())


def test_observer_and_provenance_failures_are_distinct_target_free_censors() -> None:
    observer_failure = _adapt_with_calls([], [])
    observed = collect_red_living_dex_observed_arm(
        observer_failure,  # type: ignore[arg-type]
        commitment=_commitment(observer_failure),
        observe_after=lambda: (_ for _ in ()).throw(RuntimeError("private observer")),
    )

    assert observed.example.outcome.status is LivingDexOutcomeStatus.CENSORED
    assert observed.example.outcome.censor_reason is LivingDexCensorReason.OBSERVATION_FAILED
    assert observed.example.outcome.target_vector is None
    assert observed.independent_observer_calls == 1
    assert observed.after_observer_provenance_sha256 is None

    provenance_failure = _adapt_with_calls([], [])
    mismatched = collect_red_living_dex_observed_arm(
        provenance_failure,  # type: ignore[arg-type]
        commitment=_commitment(provenance_failure, partition="development"),
        observe_after=lambda: _after(scenario="9" * 64),  # type: ignore[arg-type]
    )

    assert mismatched.example.outcome.status is LivingDexOutcomeStatus.CENSORED
    assert mismatched.example.outcome.censor_reason is LivingDexCensorReason.PROVENANCE_FAILED
    assert mismatched.example.outcome.target_vector is None
    assert mismatched.after_observer_provenance_sha256 == "6" * 64


def test_explicit_external_interruption_is_censored_without_observation() -> None:
    adapted = _adapt_with_calls([], [])
    behavior = red_living_dex_behavior_decision(
        adapted.menu,  # type: ignore[attr-defined]
        commitment=_commitment(adapted),
    )
    observer_calls = 0

    def interrupt() -> object:
        raise RedLivingDexExternalInterruption("private power event")

    def observe() -> RedLivingDexOutcomeSnapshot:
        nonlocal observer_calls
        observer_calls += 1
        return _after()

    adapted = _replace_option(
        adapted,
        behavior.selected_candidate_index,
        execute=interrupt,
    )
    result = collect_red_living_dex_observed_arm(
        adapted,  # type: ignore[arg-type]
        commitment=_commitment(adapted),
        observe_after=observe,  # type: ignore[arg-type]
    )

    assert result.example.outcome.censor_reason is LivingDexCensorReason.EXTERNAL_INTERRUPTION
    assert result.example.outcome.target_vector is None
    assert result.independent_observer_calls == 0
    assert observer_calls == 0


def test_process_interruptions_remain_visible_and_consumed_bindings_cannot_retry() -> None:
    interrupted = _adapt_with_calls([], [])
    behavior = red_living_dex_behavior_decision(
        interrupted.menu,  # type: ignore[attr-defined]
        commitment=_commitment(interrupted),
    )
    interrupted = _replace_option(
        interrupted,
        behavior.selected_candidate_index,
        execute=lambda: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    with pytest.raises(KeyboardInterrupt):
        collect_red_living_dex_observed_arm(
            interrupted,  # type: ignore[arg-type]
            commitment=_commitment(interrupted),
            observe_after=lambda: _after(),  # type: ignore[arg-type]
        )

    completed = _adapt_with_calls([], [])
    collect_red_living_dex_observed_arm(
        completed,  # type: ignore[arg-type]
        commitment=_commitment(completed),
        observe_after=lambda: _after(),  # type: ignore[arg-type]
    )
    with pytest.raises(RedLivingDexOptionCollectorError, match="already-consumed"):
        collect_red_living_dex_observed_arm(
            completed,  # type: ignore[arg-type]
            commitment=_commitment(completed),
            observe_after=lambda: _after(),  # type: ignore[arg-type]
        )


def test_masked_option_never_executes_even_when_its_private_callable_would_raise() -> None:
    execute_calls: list[int] = []
    verify_calls: list[int] = []
    adapted = _adapt_with_calls(execute_calls, verify_calls)
    masked = next(
        option
        for index, option in enumerate(adapted.ordered_options)  # type: ignore[attr-defined]
        if index not in adapted.menu.available_indices  # type: ignore[attr-defined]
    )
    masked_index = adapted.ordered_options.index(masked)  # type: ignore[attr-defined]
    adapted = _replace_option(
        adapted,
        masked_index,
        execute=lambda: (_ for _ in ()).throw(AssertionError("masked action ran")),
    )
    masked = adapted.ordered_options[masked_index]

    result = collect_red_living_dex_observed_arm(
        adapted,  # type: ignore[arg-type]
        commitment=_commitment(adapted),
        observe_after=lambda: _after(),  # type: ignore[arg-type]
    )

    assert result.behavior.probabilities[
        adapted.ordered_options.index(masked)  # type: ignore[attr-defined]
    ] == 0.0
    assert masked.consumed is False
    assert len(execute_calls) == 1


def test_test_fixture_uses_the_declared_red_living_target_not_a_151_shortcut() -> None:
    assert RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species == TARGETS
    assert len(TARGETS) < 151
