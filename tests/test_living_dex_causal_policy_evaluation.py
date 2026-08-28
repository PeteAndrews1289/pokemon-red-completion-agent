from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from pokemon_red_completion.living_dex_causal_curriculum import (
    RED_DIRECT_CAUSAL_OPTION_KINDS,
    LivingDexCausalCurriculumDesign,
)
from pokemon_red_completion.living_dex_causal_policy_evaluation import (
    LivingDexCausalBaseline,
    LivingDexCausalControlOutcome,
    LivingDexCausalPolicyContextResult,
    LivingDexCausalPolicyEvaluationError,
    LivingDexPairedDisposition,
    evaluate_living_dex_causal_policy,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexCensorReason,
    LivingDexObservedOutcome,
    LivingDexOutcomeStatus,
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _settled(success: bool) -> LivingDexObservedOutcome:
    return LivingDexObservedOutcome(
        status=LivingDexOutcomeStatus.SETTLED,
        verified_success=success,
        completion_gain=1.0 if success else 0.0,
        dependency_unlock_gain=1.0 if success else 0.0,
        action_cost=0.2,
        frame_cost=0.2,
        resource_cost=0.0,
        party_cost=0.0,
        storage_cost=0.0,
        irreversible_loss=0.0,
    )


def _censored() -> LivingDexObservedOutcome:
    return LivingDexObservedOutcome(
        status=LivingDexOutcomeStatus.CENSORED,
        censor_reason=LivingDexCensorReason.OBSERVATION_FAILED,
    )


def _context(
    ordinal: int,
    *,
    candidate_success: bool,
    baseline_success: bool,
) -> LivingDexCausalPolicyContextResult:
    focus = RED_DIRECT_CAUSAL_OPTION_KINDS[ordinal // 15]
    candidate = _settled(candidate_success)
    baseline = _settled(baseline_success)
    return LivingDexCausalPolicyContextResult(
        context_identity_sha256=_digest(f"context-{ordinal}"),
        physical_root_sha256=_digest(f"root-{ordinal}"),
        independence_lineage_sha256=_digest(f"lineage-{ordinal}"),
        same_reset_rng_sha256=_digest(f"reset-rng-{ordinal}"),
        menu_policy_sha256=_digest(f"menu-{ordinal}"),
        model_choice_commitment_sha256=_digest(f"model-choice-{ordinal}"),
        control_choice_commitment_sha256=_digest(f"controls-{ordinal}"),
        focus_kind=focus,
        candidate_index=0,
        candidate_outcome=candidate,
        controls=(
            LivingDexCausalControlOutcome(
                LivingDexCausalBaseline.FROZEN_RANDOM,
                1,
                baseline,
            ),
            LivingDexCausalControlOutcome(
                LivingDexCausalBaseline.COST_ONLY,
                2,
                baseline,
            ),
            LivingDexCausalControlOutcome(
                LivingDexCausalBaseline.MYOPIC_COMPLETION_GREEDY,
                1,
                baseline,
            ),
        ),
    )


def _passing_contexts() -> tuple[LivingDexCausalPolicyContextResult, ...]:
    rows: list[LivingDexCausalPolicyContextResult] = []
    for ordinal in range(105):
        if ordinal < 45:
            values = (True, False)
        elif ordinal < 60:
            values = (False, True)
        elif ordinal < 75:
            values = (True, True)
        else:
            values = (False, False)
        rows.append(
            _context(
                ordinal,
                candidate_success=values[0],
                baseline_success=values[1],
            )
        )
    return tuple(rows)


def _censor_context(
    context: LivingDexCausalPolicyContextResult,
) -> LivingDexCausalPolicyContextResult:
    censored = _censored()
    return replace(
        context,
        candidate_outcome=censored,
        controls=tuple(
            replace(control, outcome=censored) for control in context.controls
        ),
    )


def test_paired_envelope_gate_uses_realized_success_and_exact_test() -> None:
    evaluation = evaluate_living_dex_causal_policy(_passing_contexts())
    public = evaluation.public_dict()

    assert evaluation.complete_contexts == 105
    assert evaluation.candidate_wins == 45
    assert evaluation.candidate_losses == 15
    assert evaluation.complete_case_candidate_losses == 15
    assert evaluation.conservative_censored_losses == 0
    assert evaluation.ties == 45
    assert evaluation.candidate_successes == 60
    assert evaluation.baseline_envelope_successes == 30
    assert evaluation.exact_one_sided_p == pytest.approx(0.00006725704046424766)
    assert evaluation.adequate_complete_contexts
    assert evaluation.candidate_success_floor_passed
    assert evaluation.promotion_gate_passed
    assert public["training_targets_emitted"] == 0
    assert public["unexecuted_action_targets"] == 0
    assert public["model_fits"] == 0
    assert public["private_identity_fields"] == 0


def test_three_censors_are_forced_losses_and_four_fail_the_frozen_denominator() -> None:
    rows = list(_passing_contexts())
    for index in range(102, 105):
        rows[index] = _censor_context(rows[index])
    three = evaluate_living_dex_causal_policy(tuple(rows))
    assert three.complete_contexts == 102
    assert three.censored_contexts == 3
    assert three.candidate_losses == 18
    assert three.complete_case_candidate_losses == 15
    assert three.conservative_censored_losses == 3
    assert three.adequate_complete_contexts
    assert three.promotion_gate_passed

    rows[101] = _censor_context(rows[101])
    four = evaluate_living_dex_causal_policy(tuple(rows))
    assert four.complete_contexts == 101
    assert four.censored_contexts == 4
    assert not four.adequate_complete_contexts
    assert not four.promotion_gate_passed


def test_same_candidate_branch_cannot_report_two_different_outcomes() -> None:
    context = _passing_contexts()[0]
    controls = list(context.controls)
    controls[-1] = replace(controls[-1], outcome=_settled(True))
    with pytest.raises(
        LivingDexCausalPolicyEvaluationError,
        match="contradictory outcomes",
    ):
        replace(context, controls=tuple(controls))


def test_evaluator_rejects_reused_lineages_or_an_unbalanced_focus_schedule() -> None:
    rows = list(_passing_contexts())
    rows[1] = replace(
        rows[1],
        independence_lineage_sha256=rows[0].independence_lineage_sha256,
    )
    with pytest.raises(
        LivingDexCausalPolicyEvaluationError,
        match="repeats a lineage",
    ):
        evaluate_living_dex_causal_policy(tuple(rows))

    rows = list(_passing_contexts())
    rows[0] = replace(rows[0], focus_kind=RED_DIRECT_CAUSAL_OPTION_KINDS[1])
    with pytest.raises(
        LivingDexCausalPolicyEvaluationError,
        match="focus schedule",
    ):
        evaluate_living_dex_causal_policy(tuple(rows))


def test_candidate_success_floor_is_independent_of_significance() -> None:
    rows = tuple(
        _context(
            ordinal,
            candidate_success=ordinal < 45,
            baseline_success=45 <= ordinal < 60,
        )
        for ordinal in range(105)
    )
    evaluation = evaluate_living_dex_causal_policy(rows)

    assert evaluation.candidate_wins == 45
    assert evaluation.candidate_losses == 15
    assert evaluation.exact_one_sided_p < 0.05
    assert not evaluation.candidate_success_floor_passed
    assert not evaluation.promotion_gate_passed


def test_individual_controls_remain_descriptive_beneath_one_envelope_claim() -> None:
    evaluation = evaluate_living_dex_causal_policy(_passing_contexts())

    assert {row[0] for row in evaluation.per_control} == {
        item.value for item in LivingDexCausalBaseline
    }
    assert all(row[1:] == (45, 15, 45) for row in evaluation.per_control)
    assert LivingDexPairedDisposition.CANDIDATE_WIN.value == "candidate_win"
    assert evaluation.design_sha256 == LivingDexCausalCurriculumDesign().design_sha256
