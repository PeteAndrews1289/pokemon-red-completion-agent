from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest

from pokemon_crystal_completion.transfer_protocol_v3 import (
    CRYSTAL_TRANSFER_V3_PLAN_FILENAME,
    CRYSTAL_TRANSFER_V3_PRIMARY_DESIGN,
    CrystalTransferV3ProtocolError,
    canonical_crystal_transfer_v3_plan_bytes,
    parse_crystal_transfer_v3_plan,
)
from pokemon_red_completion.goal_manager import GoalKind

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = PROJECT_ROOT / "configs" / CRYSTAL_TRANSFER_V3_PLAN_FILENAME


def test_v3_plan_is_canonical_balanced_powered_and_still_review_gated() -> None:
    payload = PLAN_PATH.read_bytes()
    plan = parse_crystal_transfer_v3_plan(payload)

    assert payload == canonical_crystal_transfer_v3_plan_bytes()
    assert plan.plan_sha256 == hashlib.sha256(payload).hexdigest()
    assert len(plan.adaptation_slots) == 27
    assert len(plan.sealed_test_slots) == 54
    assert Counter(item.goal_kind for item in plan.adaptation_slots) == Counter(
        {kind: 3 for kind in GoalKind}
    )
    assert Counter(item.goal_kind for item in plan.sealed_test_slots) == Counter(
        {kind: 6 for kind in GoalKind}
    )
    assert Counter(item.fold for item in plan.adaptation_slots) == Counter(
        {fold: 3 for fold in range(9)}
    )
    assert Counter(item.fold for item in plan.sealed_test_slots) == Counter(
        {fold: 6 for fold in range(9)}
    )
    assert Counter(item.focus_candidate_index for item in plan.adaptation_slots) == Counter(
        {position: 3 for position in range(9)}
    )
    assert Counter(item.focus_candidate_index for item in plan.sealed_test_slots) == Counter(
        {position: 6 for position in range(9)}
    )
    assert CRYSTAL_TRANSFER_V3_PRIMARY_DESIGN.adequately_powered
    assert CRYSTAL_TRANSFER_V3_PRIMARY_DESIGN.minimum_contexts == 51
    assert not plan.authorized_for_private_context_access

    document = json.loads(payload)
    schedule = document["slot_schedule"]
    assert len(schedule["assignments"]) == 81
    assert schedule["adaptation_pairwise_order_reversals"] == 36
    assert schedule["sealed_test_pairwise_order_reversals"] == 36
    assert schedule["adaptation_focus_position_counts"] == {
        str(position): 3 for position in range(9)
    }
    assert schedule["sealed_test_focus_position_counts"] == {
        str(position): 6 for position in range(9)
    }
    assert all(
        len(assignment["candidate_goal_kinds"]) == len(GoalKind)
        for assignment in schedule["assignments"]
    )


def test_v3_retires_v2_at_zero_access_and_drops_the_zero_loss_conjunction() -> None:
    document = json.loads(PLAN_PATH.read_text(encoding="ascii"))

    assert document["supersedes"] == {
        "experiment_id": "red-to-crystal-goal-manager-v2",
        "reason": (
            "ordinary convex fine-tuning erased initialization and the zero-loss "
            "conjunction was underpowered"
        ),
        "v2_adaptation_examples_collected": 0,
        "v2_predictions_computed": 0,
        "v2_sealed_contexts_opened": 0,
        "v2_zero_shot_contexts_opened": 0,
    }
    endpoint = document["claims"]["primary_endpoint"]
    assert endpoint["test"] == (
        "one_sided_exact_sign_test_conditional_on_discordance"
    )
    assert "maximum_discordant_losses" not in endpoint
    assert endpoint["adequately_powered"] is True
    assert document["claims"]["assigned_goal_kind_is_expected_teacher_label"] is True
    assert document["claims"]["assigned_kind_mismatch_policy"] == {
        "applies_to": ["adaptation", "sealed_test"],
        "mismatch_count_and_partition_must_be_published": True,
        "replacement_or_resampling_forbidden": True,
        "result": "retire_without_scoring_or_transfer_claim",
    }
    assert document["claims"]["utility_gate"] == {
        "absolute_candidate_accuracy_floor": 0.5,
        "candidate_must_match_or_exceed_comparator_accuracy": True,
        "comparator_id": "highest_pressure_goal_index",
        "comparator_receives_same_identity_free_question": True,
        "minimum_candidate_correct": 27,
        "predictions_committed_before_any_sealed_label": True,
        "zero_weight_sign_test_alone_is_not_promotion_eligible": True,
    }


def test_v3_contains_no_capture_label_prediction_or_private_path() -> None:
    encoded = PLAN_PATH.read_text(encoding="ascii")
    for forbidden in (
        "/Users/",
        "/Volumes/",
        "selected_candidate_index",
        "teacher_choice_target",
        "prediction_sha256",
    ):
        assert forbidden not in encoded


def test_v3_parser_rejects_a_high_risk_endpoint_or_authorization_mutation() -> None:
    document = json.loads(PLAN_PATH.read_text(encoding="ascii"))
    mutations = []
    for path, value in (
        (("authorization", "private_context_access"), True),
        (("claims", "primary_endpoint", "target_power"), 0.50),
        (("claims", "primary_endpoint", "independent_contexts"), 27),
        (("claims", "primary_endpoint", "test"), "two_sided_exact"),
        (("claims", "utility_gate", "absolute_candidate_accuracy_floor"), 0.1),
        (("claims", "utility_gate", "comparator_id"), "lowest_effort_goal_index"),
        (("claims", "assigned_goal_kind_is_expected_teacher_label"), False),
        (
            ("claims", "assigned_kind_mismatch_policy", "replacement_or_resampling_forbidden"),
            False,
        ),
        (
            ("claims", "assigned_kind_mismatch_policy", "result"),
            "replace_until_balanced",
        ),
        (("adaptation", "only_differing_field"), "optimizer"),
        (("supersedes", "v2_sealed_contexts_opened"), 1),
    ):
        mutated = deepcopy(document)
        target = mutated[path[0]]
        assert isinstance(target, dict)
        for key in path[1:-1]:
            target = target[key]
            assert isinstance(target, dict)
        target[path[-1]] = value
        mutations.append(mutated)

    for mutated in mutations:
        payload = (
            json.dumps(mutated, separators=(",", ":"), sort_keys=True).encode("ascii")
            + b"\n"
        )
        with pytest.raises(CrystalTransferV3ProtocolError, match="preregistration"):
            parse_crystal_transfer_v3_plan(payload)


def test_v3_generator_check_accepts_the_committed_plan() -> None:
    subprocess.run(
        [sys.executable, "scripts/regenerate_crystal_transfer_plan_v3.py", "--check"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
