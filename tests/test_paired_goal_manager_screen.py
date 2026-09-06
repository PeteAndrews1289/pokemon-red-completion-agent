from __future__ import annotations

from pathlib import Path

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_protocol import (
    GOAL_MANAGER_REGISTRY_RELATIVE_PATH,
    GoalManagerAssignment,
    parse_goal_manager_registry,
)
from pokemon_red_completion.paired_goal_manager_screen import (
    PAIRED_SCREEN_SEED,
    PairedGoalManagerScreenError,
    adjudicate_paired_screen,
    paired_screen_arm_claim,
    paired_screen_arm_execution_identity,
    paired_screen_behavior_contract,
    paired_screen_endpoint_contract,
    paired_screen_execution_identity,
    select_development_outcome_unused_acquisition_root,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _assignments() -> tuple[GoalManagerAssignment, ...]:
    # This unit tests selection, not historical source authentication. The
    # frozen registry belongs to its original training revision, not each new
    # implementation HEAD. Production keeps the strict historical loader.
    registry = parse_goal_manager_registry(
        (PROJECT_ROOT / GOAL_MANAGER_REGISTRY_RELATIVE_PATH).read_bytes()
    )
    return tuple(registry.assignment(slot.slot_id) for slot in registry.slots)


def test_selection_uses_first_remaining_acquisition_train_assignment() -> None:
    acquisition = tuple(
        assignment
        for assignment in _assignments()
        if assignment.partition == "train"
        and assignment.focus_kind is GoalKind.ACQUIRE_SPECIES
    )
    excluded, expected = acquisition[:2]

    selected = select_development_outcome_unused_acquisition_root(
        _assignments(),
        excluded_root_lineages=frozenset({excluded.root_lineage_id}),
    )

    assert selected == expected


def test_selection_fails_without_searchable_replacement() -> None:
    assignments = _assignments()
    excluded = frozenset(
        assignment.root_lineage_id
        for assignment in assignments
        if assignment.partition == "train"
        and assignment.focus_kind is GoalKind.ACQUIRE_SPECIES
    )

    with pytest.raises(PairedGoalManagerScreenError, match="no development-outcome-unused"):
        select_development_outcome_unused_acquisition_root(
            assignments,
            excluded_root_lineages=excluded,
        )


def test_behavior_and_endpoint_contracts_are_bounded_and_descriptive() -> None:
    behavior = paired_screen_behavior_contract()
    endpoint = paired_screen_endpoint_contract()

    assert behavior["arm_order"] == ["base", "candidate"]
    assert behavior["seed"] == PAIRED_SCREEN_SEED
    assert behavior["maximum_decisions_per_arm"] == 3
    assert behavior["exploration_mix"] == 0.15
    assert behavior["retry_or_replacement_allowed"] is False
    assert endpoint["primary_endpoint"] == "safe_retained_acquisition"
    assert endpoint["unseen_comparison"] is False
    assert endpoint["promotion_authorized"] is False


@pytest.mark.parametrize(
    ("base", "candidate", "expected"),
    (
        (False, True, "win"),
        (True, False, "loss"),
        (True, True, "tie"),
        (False, False, "tie"),
        (None, True, "uninterpretable"),
        (False, None, "uninterpretable"),
    ),
)
def test_adjudication_uses_no_secondary_tie_breaker(
    base: bool | None,
    candidate: bool | None,
    expected: str,
) -> None:
    result = adjudicate_paired_screen(
        base_safe_retained_acquisition=base,
        candidate_safe_retained_acquisition=candidate,
    )

    assert result.result == expected


def test_arm_claim_binds_model_and_arm() -> None:
    base = paired_screen_arm_claim(
        screen_id="a" * 64,
        arm="base",
        model_canonical_sha256="b" * 64,
    )
    candidate = paired_screen_arm_claim(
        screen_id="a" * 64,
        arm="candidate",
        model_canonical_sha256="c" * 64,
    )

    assert base != candidate
    assert len(base) == 64
    assert len(candidate) == 64


def test_execution_identities_bind_successor_source_pair_and_arm() -> None:
    claims = ("a" * 64, "b" * 64)
    pair = paired_screen_execution_identity(
        screen_plan_sha256="c" * 64,
        screen_id="d" * 64,
        execution_source_commit="e" * 40,
        execution_runner_sha256="f" * 64,
        runtime_sha256="1" * 64,
        root_consumption_sha256="2" * 64,
        arm_claim_sha256=claims,
    )
    arm = paired_screen_arm_execution_identity(
        pair_execution_identity_sha256=pair,
        arm="base",
        model_canonical_sha256="3" * 64,
        arm_claim_sha256=claims[0],
        episode_id="red-pair-" + "a" * 64,
    )

    assert len(pair) == 64
    assert len(arm) == 64
    assert arm != paired_screen_arm_execution_identity(
        pair_execution_identity_sha256=pair,
        arm="candidate",
        model_canonical_sha256="3" * 64,
        arm_claim_sha256=claims[1],
        episode_id="red-pair-" + "b" * 64,
    )


def test_execution_identity_rejects_duplicate_arm_claims() -> None:
    with pytest.raises(PairedGoalManagerScreenError, match="arm claims"):
        paired_screen_execution_identity(
            screen_plan_sha256="c" * 64,
            screen_id="d" * 64,
            execution_source_commit="e" * 40,
            execution_runner_sha256="f" * 64,
            runtime_sha256="1" * 64,
            root_consumption_sha256="2" * 64,
            arm_claim_sha256=("a" * 64, "a" * 64),
        )
