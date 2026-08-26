from __future__ import annotations

import json
from dataclasses import replace

import pytest
from test_red_living_dex_option_adapter import (
    TARGETS,
    _budgets,
    _facts,
    _options,
    _prospects,
    _snapshot,
)

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.red_living_dex_option_adapter import (
    adapt_red_living_dex_options,
    bind_red_goal_option,
)
from pokemon_red_completion.red_living_dex_option_calibration import (
    RedLivingDexCalibrationBatch,
    RedLivingDexCalibrationError,
    build_red_living_dex_calibration_batch,
)
from pokemon_red_completion.red_living_dex_option_collector import (
    RedLivingDexBehaviorCommitment,
    RedLivingDexCollectedExample,
    collect_red_living_dex_observed_arm,
    issue_red_living_dex_behavior_commitment,
)

_GOAL_KIND = {
    LivingDexOptionKind.ACQUIRE: GoalKind.ACQUIRE_SPECIES,
    LivingDexOptionKind.DEVELOP: GoalKind.DEVELOP_TEAM,
    LivingDexOptionKind.EVOLVE: GoalKind.EVOLVE_SPECIES,
    LivingDexOptionKind.MANAGE_STORAGE: GoalKind.MANAGE_STORAGE,
    LivingDexOptionKind.RESUPPLY: GoalKind.RESUPPLY,
}


def _collected(
    index: int,
    *,
    partition: str,
    kind: LivingDexOptionKind,
    family: str,
    location: str,
    censored: bool = False,
    authenticated: bool = True,
    authenticated_commitment: bool = True,
    scenario_identity_sha256: str | None = None,
) -> RedLivingDexCollectedExample:
    scenario = (
        f"{1_000 + index:064x}"
        if scenario_identity_sha256 is None
        else scenario_identity_sha256
    )
    prospects = list(_prospects())
    for prospect_index in range(3):
        prospects[prospect_index] = replace(
            prospects[prospect_index],
            kind=kind,
        )
    options = []
    for option_index, option in enumerate(
        _options(
            prefix=f"private.batch.{index}",
            prospects=tuple(prospects),
        )
    ):
        if authenticated and option.prospect.invariant_safe:
            goal_binding = ExecutableGoalBinding(
                binding_ref=option.binding_ref,
                kind=_GOAL_KIND[kind],
                estimated_effort=0.2,
                estimated_risk=0.1,
                execute=lambda: GoalExecutionReport(1, 1, {"bounded": True}),
                verify=lambda _report: GoalVerification.succeeded(),
            )
            options.append(
                bind_red_goal_option(
                    goal_binding,
                    option.prospect,
                    family_ref=f"private.family.{family}",
                    location_ref=f"private.location.{location}",
                    resource_pool_ref=option.resource_pool_ref,
                )
            )
        else:
            options.append(
                replace(
                    option,
                    binding_ref=f"private.batch.{index}.masked.{option_index}",
                    family_ref=f"private.family.{family}",
                    location_ref=f"private.location.{location}",
                )
            )
    adapted = adapt_red_living_dex_options(
        _snapshot(
            scenario=scenario,
            provenance=f"{2_000 + index:064x}",
        ),
        _facts(),
        _budgets(),
        tuple(options),
        ordering_seed_sha256=f"{3_000 + index:064x}",
    )
    commitment = (
        issue_red_living_dex_behavior_commitment(adapted, partition=partition)
        if authenticated_commitment
        else RedLivingDexBehaviorCommitment(
            adapted.before.scenario_identity_sha256,
            partition,
            adapted.menu.policy_sha256,
            f"{4_000 + index:064x}",
        )
    )

    def observe() -> object:
        if censored:
            raise RuntimeError("private observer failure")
        return _snapshot(
            species=(TARGETS[0], TARGETS[1]),
            scenario=scenario,
            dependencies=3,
            consumables=8,
            health=70,
            irreversible=3,
            actions=350,
            frames=3_000,
            provenance=f"{6_000 + index:064x}",
        )

    return collect_red_living_dex_observed_arm(
        adapted,
        commitment=commitment,
        observe_after=observe,  # type: ignore[arg-type]
    )


def _fit_ready_examples() -> tuple[RedLivingDexCollectedExample, ...]:
    train_kinds = (
        LivingDexOptionKind.ACQUIRE,
        LivingDexOptionKind.EVOLVE,
        LivingDexOptionKind.DEVELOP,
        LivingDexOptionKind.MANAGE_STORAGE,
        LivingDexOptionKind.RESUPPLY,
        LivingDexOptionKind.ACQUIRE,
        LivingDexOptionKind.EVOLVE,
        LivingDexOptionKind.DEVELOP,
    )
    train = tuple(
        _collected(
            index,
            partition="train",
            kind=kind,
            family=f"train-{index % 3}",
            location=f"train-{index % 2}",
        )
        for index, kind in enumerate(train_kinds)
    )
    development = tuple(
        _collected(
            100 + index,
            partition="development",
            kind=(
                LivingDexOptionKind.ACQUIRE
                if index % 2 == 0
                else LivingDexOptionKind.EVOLVE
            ),
            family=f"development-{index}",
            location=f"development-{index}",
        )
        for index in range(4)
    )
    return (*train, *development)


def test_batch_opens_train_only_fit_after_exact_coverage_and_disjointness() -> None:
    batch = build_red_living_dex_calibration_batch(_fit_ready_examples())

    assert batch.fit_ready is True
    assert len(batch.train_fit_examples()) == 8
    assert all(example.partition == "train" for example in batch.train_fit_examples())
    assert len(batch.development_evaluation_examples()) == 4
    assert all(
        example.partition == "development"
        for example in batch.development_evaluation_examples()
    )
    public = batch.public_dict()
    assert public["settled_counts"] == {"development": 4, "train": 8}
    assert public["train_selected_option_kind_count"] == 5
    assert public["train_family_count"] == 3
    assert public["development_family_count"] == 4
    assert public["development_location_count"] == 4
    assert public["family_overlap"] == 0
    assert public["location_overlap"] == 0
    assert public["context_sampling_propensity_correction"] is False
    assert public["unselected_action_targets"] == 0
    assert public["menu_sampling"]["available_width_counts"] == {"3": 12}  # type: ignore[index]
    assert "private." not in json.dumps(public, sort_keys=True).lower()
    assert "private.batch" not in json.dumps(batch.private_dict(), sort_keys=True).lower()


def test_batch_does_not_require_success_failure_balance() -> None:
    batch = RedLivingDexCalibrationBatch(_fit_ready_examples())

    assert batch.fit_ready is True
    assert all(
        example.example.outcome.verified_success is True
        for example in batch.examples
    )


def test_synthetic_selected_executor_cannot_open_the_fit_gate() -> None:
    ready = list(_fit_ready_examples())
    ready[0] = _collected(
        500,
        partition="train",
        kind=LivingDexOptionKind.ACQUIRE,
        family="train-synthetic",
        location="train-synthetic",
        authenticated=False,
    )
    batch = RedLivingDexCalibrationBatch(tuple(ready))

    assert batch.fit_ready is False
    assert batch.public_dict()["authenticated_executor_counts"] == {
        "development": 4,
        "train": 7,
    }
    with pytest.raises(RedLivingDexCalibrationError, match="not ready"):
        batch.train_fit_examples()


def test_synthetic_randomization_commitment_cannot_open_the_fit_gate() -> None:
    ready = list(_fit_ready_examples())
    ready[0] = _collected(
        501,
        partition="train",
        kind=LivingDexOptionKind.ACQUIRE,
        family="train-synthetic-randomization",
        location="train-synthetic-randomization",
        authenticated_commitment=False,
    )
    batch = RedLivingDexCalibrationBatch(tuple(ready))

    assert batch.fit_ready is False
    assert batch.public_dict()["authenticated_randomization_counts"] == {
        "development": 4,
        "train": 7,
    }
    with pytest.raises(RedLivingDexCalibrationError, match="not ready"):
        batch.train_fit_examples()


def test_partial_or_censored_coverage_cannot_open_fitting() -> None:
    ready = _fit_ready_examples()
    partial = RedLivingDexCalibrationBatch((*ready[:7], *ready[8:]))

    assert partial.fit_ready is False
    with pytest.raises(RedLivingDexCalibrationError, match="not ready"):
        partial.train_fit_examples()

    censored = _collected(
        200,
        partition="train",
        kind=LivingDexOptionKind.RESUPPLY,
        family="train-censored",
        location="train-censored",
        censored=True,
    )
    with_censor = RedLivingDexCalibrationBatch((*ready[:7], censored, *ready[8:]))
    diagnostic = with_censor.public_dict()["censoring_diagnostic"]

    assert with_censor.fit_ready is False
    assert with_censor.public_dict()["censored_counts"] == {
        "development": 0,
        "train": 1,
    }
    assert isinstance(diagnostic, dict)
    censored_counts = []
    for row in diagnostic.values():
        assert isinstance(row, dict)
        value = row["censored"]
        assert isinstance(value, int)
        censored_counts.append(value)
    assert sum(censored_counts) == 1


def test_family_or_location_overlap_fails_the_fit_gate_without_hiding_examples() -> None:
    ready = list(_fit_ready_examples())
    ready[-1] = _collected(
        300,
        partition="development",
        kind=LivingDexOptionKind.ACQUIRE,
        family="train-0",
        location="train-0",
    )
    batch = RedLivingDexCalibrationBatch(tuple(ready))

    assert batch.fit_ready is False
    assert batch.public_dict()["family_overlap"] == 1
    assert batch.public_dict()["location_overlap"] == 1
    assert batch.public_dict()["partition_attempt_counts"] == {
        "development": 4,
        "train": 8,
    }


def test_repeated_decision_or_scenario_identity_is_rejected() -> None:
    example = _fit_ready_examples()[0]

    with pytest.raises(RedLivingDexCalibrationError, match="decision identity"):
        RedLivingDexCalibrationBatch((example, example))

    other = _collected(
        400,
        partition="train",
        kind=LivingDexOptionKind.ACQUIRE,
        family="other",
        location="other",
        scenario_identity_sha256=example.adapted.before.scenario_identity_sha256,
    )
    with pytest.raises(RedLivingDexCalibrationError, match="scenario identity"):
        RedLivingDexCalibrationBatch((example, other))
