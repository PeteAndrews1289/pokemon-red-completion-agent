from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import replace

import pytest

from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_episode_lineage import (
    expected_red_living_dex_first_controller_input_frame,
)
from pokemon_red_completion.red_living_dex_powered_lineage_supply import (
    RED_LIVING_DEX_POWERED_SUPPLY_ASSIGNMENTS,
    RED_LIVING_DEX_POWERED_SUPPLY_CAPACITY_RESULT_SHA256,
    RED_LIVING_DEX_POWERED_SUPPLY_DEFICITS,
    RED_LIVING_DEX_POWERED_SUPPLY_DESIGN_SHA256,
    RedLivingDexPoweredSupplyError,
    RedLivingDexPoweredSupplyFailure,
    RedLivingDexPoweredSupplyPlan,
    RedLivingDexPoweredSupplyReceipt,
    admit_red_living_dex_powered_supply_tranche,
    build_red_living_dex_powered_supply_plan,
    compose_red_living_dex_powered_supply_generator_sha256,
    compose_red_living_dex_powered_supply_teacher_sha256,
    encode_red_living_dex_powered_supply_admission,
    encode_red_living_dex_powered_supply_failure,
    encode_red_living_dex_powered_supply_plan,
    encode_red_living_dex_powered_supply_receipt,
    parse_red_living_dex_powered_supply_admission,
    parse_red_living_dex_powered_supply_failure,
    parse_red_living_dex_powered_supply_plan,
    parse_red_living_dex_powered_supply_receipt,
    preflight_red_living_dex_powered_supply_plan,
    terminal_physical_root_sha256,
)


def _sha(label: str, ordinal: int = 0) -> str:
    return hashlib.sha256(f"{label}:{ordinal}".encode()).hexdigest()


def _plan() -> RedLivingDexPoweredSupplyPlan:
    source = _sha("source")
    runner = _sha("generator-runner")
    conditioner = _sha("conditioner-runner")
    generator = compose_red_living_dex_powered_supply_generator_sha256(
        source_bundle_sha256=source,
        generator_runner_sha256=runner,
        conditioner_runner_sha256=conditioner,
    )
    return build_red_living_dex_powered_supply_plan(
        source_commit="a" * 40,
        source_bundle_sha256=source,
        teacher_execution_sha256=(
            compose_red_living_dex_powered_supply_teacher_sha256(
                source_bundle_sha256=source,
                generator_execution_sha256=generator,
            )
        ),
        generator_execution_sha256=generator,
        generator_runner_sha256=runner,
        conditioner_runner_sha256=conditioner,
        runtime_identity_sha256=_sha("runtime"),
    )


def _receipt(
    plan: RedLivingDexPoweredSupplyPlan,
    ordinal: int,
) -> RedLivingDexPoweredSupplyReceipt:
    assignment = plan.assignments[ordinal - 1]
    state_sha256 = _sha("state", ordinal)
    envelope_sha256 = _sha("envelope", ordinal)
    return RedLivingDexPoweredSupplyReceipt(
        assignment_id=assignment.assignment_id,
        plan_sha256=plan.plan_sha256,
        assignment_claim_sha256=_sha("claim", ordinal),
        role=assignment.role,
        partition=assignment.partition,
        root_lineage_id=assignment.root_lineage_id,
        episode_id=assignment.episode_id,
        source_bundle_sha256=assignment.source_bundle_sha256,
        teacher_execution_sha256=assignment.teacher_execution_sha256,
        generator_execution_sha256=assignment.generator_execution_sha256,
        runtime_identity_sha256=assignment.runtime_identity_sha256,
        started_from_clean_power=True,
        distinct_process_episode=True,
        save_state_loads=0,
        terminal_state_saves=1,
        initial_wait_frames=assignment.initial_wait_frames,
        first_controller_input_frame=(
            expected_red_living_dex_first_controller_input_frame(assignment.initial_wait_frames)
        ),
        trajectory_prefix_sha256=_sha("trajectory", ordinal),
        conditioning_profile_id=assignment.conditioning_profile_id,
        target_template_ordinal=assignment.target_template_ordinal,
        compatible_template_ordinals=(assignment.target_template_ordinal,),
        observed_pressure_millionths=tuple(((ordinal + axis) % 11) * 100_000 for axis in range(7)),
        root_consumption_sha256=root_consumption_sha256(
            state_sha256=state_sha256,
            envelope_sha256=envelope_sha256,
        ),
        physical_root_sha256=terminal_physical_root_sha256(
            state_sha256=state_sha256,
            envelope_sha256=envelope_sha256,
        ),
        terminal_state_sha256=state_sha256,
        terminal_envelope_sha256=envelope_sha256,
        terminal_checkpoint_id=assignment.target_checkpoint_id,
        controller_actions=10_000 + ordinal,
        emulator_frames=1_000_000 + ordinal,
        setup_teacher_executions=1,
        learner_teacher_queries=0,
        learner_labels=0,
        learner_outcomes=0,
        model_predictions=0,
        model_fits=0,
    )


def _failure(
    plan: RedLivingDexPoweredSupplyPlan,
    ordinal: int,
) -> RedLivingDexPoweredSupplyFailure:
    assignment = plan.assignments[ordinal - 1]
    return RedLivingDexPoweredSupplyFailure(
        assignment_id=assignment.assignment_id,
        plan_sha256=plan.plan_sha256,
        role=assignment.role,
        partition=assignment.partition,
        source_bundle_sha256=assignment.source_bundle_sha256,
        teacher_execution_sha256=assignment.teacher_execution_sha256,
        generator_execution_sha256=assignment.generator_execution_sha256,
        assignment_claim_sha256=_sha("failed-claim", ordinal),
        failure_stage="fresh_episode_execution",
        effects_known=True,
        controller_actions=ordinal,
        emulator_frames=ordinal * 100,
    )


def test_plan_freezes_exact_census_bound_multi_partition_tranche() -> None:
    plan = _plan()

    assert len(plan.assignments) == RED_LIVING_DEX_POWERED_SUPPLY_ASSIGNMENTS == 12
    assert Counter(item.role for item in plan.assignments) == {
        "train": 3,
        "development": 8,
        "contingency": 1,
    }
    assert {
        item.target_template_ordinal for item in plan.assignments if item.partition == "train"
    } == {
        0,
        4,
        8,
    }
    assert {
        item.target_template_ordinal for item in plan.assignments if item.partition == "development"
    } == {10, 11, 12, 13, 14}
    assert len({item.conditioning_profile_id for item in plan.assignments}) == 10
    assert len({item.initial_wait_frames for item in plan.assignments}) == 12
    assert plan.capacity_result_sha256 == RED_LIVING_DEX_POWERED_SUPPLY_CAPACITY_RESULT_SHA256
    assert plan.powered_design_sha256 == RED_LIVING_DEX_POWERED_SUPPLY_DESIGN_SHA256
    assert RED_LIVING_DEX_POWERED_SUPPLY_DEFICITS == {
        "train_lineages": 22,
        "development_lineages": 78,
        "contingency_lineages": 3,
        "train_attempts": 44,
        "total_lineages": 103,
    }
    public = plan.public_dict()
    assert public["outcome_collection_authorized"] is False
    assert public["population_scale_authorized"] is False
    assert public["failure_disposition"] == {
        "all_assignments_require_terminal_disposition": True,
        "failed_attempts_retained": True,
        "replacement_inside_tranche_allowed": False,
        "retry_after_consumption": False,
    }


def test_plan_encoding_and_preflight_are_deterministic_and_effect_free() -> None:
    first = _plan()
    second = _plan()

    assert first == second
    assert encode_red_living_dex_powered_supply_plan(first) == (
        encode_red_living_dex_powered_supply_plan(second)
    )
    assert (
        parse_red_living_dex_powered_supply_plan(encode_red_living_dex_powered_supply_plan(first))
        == first
    )
    assert hashlib.sha256(encode_red_living_dex_powered_supply_plan(first)).hexdigest()
    preflight = preflight_red_living_dex_powered_supply_plan(first).public_dict()
    assert preflight["assignments"] == 12
    assert preflight["role_counts"] == {
        "train": 3,
        "development": 8,
        "contingency": 1,
    }
    assert preflight["target_template_count"] == 8
    assert preflight["conditioning_profile_count"] == 10
    assert all(
        preflight[key] == 0
        for key in (
            "behavior_draws",
            "controller_actions",
            "emulator_frames",
            "learner_labels",
            "learner_outcomes",
            "model_fits",
            "model_predictions",
            "provider_executions",
            "root_claims",
            "root_generation_executions",
            "teacher_queries",
        )
    )


def test_runtime_identity_changes_the_plan_and_every_assignment_identity() -> None:
    first = _plan()
    second = build_red_living_dex_powered_supply_plan(
        source_commit=first.source_commit,
        source_bundle_sha256=first.source_bundle_sha256,
        teacher_execution_sha256=first.teacher_execution_sha256,
        generator_execution_sha256=first.generator_execution_sha256,
        generator_runner_sha256=first.generator_runner_sha256,
        conditioner_runner_sha256=first.conditioner_runner_sha256,
        runtime_identity_sha256=_sha("another-runtime"),
    )

    assert first.plan_sha256 != second.plan_sha256
    assert first.runtime_identity_sha256 != second.runtime_identity_sha256
    assert {item.assignment_id for item in first.assignments}.isdisjoint(
        item.assignment_id for item in second.assignments
    )
    assert {item.episode_id for item in first.assignments}.isdisjoint(
        item.episode_id for item in second.assignments
    )


def test_plan_parser_rejects_noncanonical_unknown_and_mutated_authority() -> None:
    payload = encode_red_living_dex_powered_supply_plan(_plan())
    with pytest.raises(RedLivingDexPoweredSupplyError):
        parse_red_living_dex_powered_supply_plan(payload.rstrip())
    with pytest.raises(RedLivingDexPoweredSupplyError):
        parse_red_living_dex_powered_supply_plan(payload.replace(b"{", b'{"x":1,', 1))
    with pytest.raises(RedLivingDexPoweredSupplyError):
        parse_red_living_dex_powered_supply_plan(
            payload.replace(
                b'"population_scale_authorized":false',
                b'"population_scale_authorized":true',
            )
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("role", "development"),
        ("partition", "development"),
        ("target_template_ordinal", 10),
        ("conditioning_profile_id", "not-frozen"),
        ("capacity_result_sha256", _sha("another-capacity")),
        ("powered_design_sha256", _sha("another-design")),
        ("generator_runner_sha256", _sha("another-generator-runner")),
        ("conditioner_runner_sha256", _sha("another-conditioner-runner")),
        ("runtime_identity_sha256", _sha("another-runtime")),
        ("initial_wait_frames", 999),
    ),
)
def test_assignment_mutations_fail_closed(field: str, value: object) -> None:
    assignment = _plan().assignments[0]
    with pytest.raises(RedLivingDexPoweredSupplyError):
        replace(assignment, **{field: value})


def test_schedule_reordering_and_duplicate_lineage_fail_closed() -> None:
    plan = _plan()
    with pytest.raises(RedLivingDexPoweredSupplyError):
        replace(plan, assignments=(plan.assignments[1], plan.assignments[0], *plan.assignments[2:]))
    with pytest.raises(RedLivingDexPoweredSupplyError):
        replace(
            plan,
            assignments=(
                plan.assignments[0],
                replace(
                    plan.assignments[1],
                    root_lineage_id=plan.assignments[0].root_lineage_id,
                ),
                *plan.assignments[2:],
            ),
        )


def test_complete_success_tranche_passes_but_never_authorizes_scale() -> None:
    plan = _plan()
    receipts = tuple(_receipt(plan, ordinal) for ordinal in range(1, 13))
    admission = admit_red_living_dex_powered_supply_tranche(plan, receipts, ())

    assert admission.qualification_passed is True
    assert admission.roots_admitted == 12
    assert admission.attempts_failed == 0
    public = admission.public_dict()
    assert public["qualification_passed"] is True
    assert public["recensus_required"] is True
    assert public["population_scale_authorized"] is False
    assert public["collection_authorized"] is False


def test_declared_nine_of_twelve_role_floor_is_the_minimum_pass() -> None:
    plan = _plan()
    # One train and two development failures retain 2/6/1 admitted roots.
    failed_ordinals = {1, 4, 5}
    receipts = tuple(
        _receipt(plan, ordinal) for ordinal in range(1, 13) if ordinal not in failed_ordinals
    )
    failures = tuple(_failure(plan, ordinal) for ordinal in sorted(failed_ordinals))

    admission = admit_red_living_dex_powered_supply_tranche(plan, receipts, failures)

    assert admission.roots_admitted == 9
    assert admission.attempts_failed == 3
    assert dict(admission.admitted_role_counts) == {
        "contingency": 1,
        "development": 6,
        "train": 2,
    }
    assert admission.qualification_passed is True


def test_total_yield_cannot_hide_a_missing_contingency_role() -> None:
    plan = _plan()
    receipts = tuple(_receipt(plan, ordinal) for ordinal in range(1, 12))
    failures = (_failure(plan, 12),)

    admission = admit_red_living_dex_powered_supply_tranche(plan, receipts, failures)

    assert admission.roots_admitted == 11
    assert admission.qualification_passed is False
    assert admission.public_dict()["status"] == (
        "bounded_yield_qualification_failed_population_closed"
    )


def test_incomplete_replacement_or_duplicate_disposition_fails_closed() -> None:
    plan = _plan()
    receipts = tuple(_receipt(plan, ordinal) for ordinal in range(1, 12))
    with pytest.raises(RedLivingDexPoweredSupplyError):
        admit_red_living_dex_powered_supply_tranche(plan, receipts, ())
    with pytest.raises(RedLivingDexPoweredSupplyError):
        admit_red_living_dex_powered_supply_tranche(
            plan,
            (*receipts, receipts[0]),
            (_failure(plan, 12),),
        )


@pytest.mark.parametrize(
    "clone_field",
    (
        "physical_root_sha256",
        "trajectory_prefix_sha256",
        "terminal_state_sha256",
        "terminal_envelope_sha256",
    ),
)
def test_cloned_success_evidence_never_counts_twice(clone_field: str) -> None:
    plan = _plan()
    receipts = list(_receipt(plan, ordinal) for ordinal in range(1, 13))
    source = receipts[0]
    target = receipts[1]
    if clone_field == "physical_root_sha256":
        # Preserve internal digest coherence while duplicating the byte root.
        target = replace(
            target,
            terminal_state_sha256=source.terminal_state_sha256,
            terminal_envelope_sha256=source.terminal_envelope_sha256,
            physical_root_sha256=source.physical_root_sha256,
            root_consumption_sha256=source.root_consumption_sha256,
        )
    elif clone_field == "terminal_state_sha256":
        target = replace(
            target,
            terminal_state_sha256=source.terminal_state_sha256,
            physical_root_sha256=terminal_physical_root_sha256(
                state_sha256=source.terminal_state_sha256,
                envelope_sha256=target.terminal_envelope_sha256,
            ),
            root_consumption_sha256=root_consumption_sha256(
                state_sha256=source.terminal_state_sha256,
                envelope_sha256=target.terminal_envelope_sha256,
            ),
        )
    elif clone_field == "terminal_envelope_sha256":
        target = replace(
            target,
            terminal_envelope_sha256=source.terminal_envelope_sha256,
            physical_root_sha256=terminal_physical_root_sha256(
                state_sha256=target.terminal_state_sha256,
                envelope_sha256=source.terminal_envelope_sha256,
            ),
            root_consumption_sha256=root_consumption_sha256(
                state_sha256=target.terminal_state_sha256,
                envelope_sha256=source.terminal_envelope_sha256,
            ),
        )
    else:
        target = replace(
            target,
            trajectory_prefix_sha256=source.trajectory_prefix_sha256,
        )
    receipts[1] = target

    with pytest.raises(RedLivingDexPoweredSupplyError):
        admit_red_living_dex_powered_supply_tranche(plan, tuple(receipts), ())


def test_receipt_rejects_missing_target_cross_partition_and_learner_effects() -> None:
    receipt = _receipt(_plan(), 1)
    with pytest.raises(RedLivingDexPoweredSupplyError):
        replace(receipt, compatible_template_ordinals=(4,))
    with pytest.raises(RedLivingDexPoweredSupplyError):
        replace(receipt, compatible_template_ordinals=(0, 10))
    with pytest.raises(RedLivingDexPoweredSupplyError):
        replace(receipt, learner_outcomes=1)
    with pytest.raises(RedLivingDexPoweredSupplyError):
        replace(receipt, model_predictions=1)
    with pytest.raises(RedLivingDexPoweredSupplyError):
        replace(receipt, save_state_loads=1)


def test_admission_rejects_a_receipt_from_another_runtime() -> None:
    plan = _plan()
    receipts = tuple(_receipt(plan, ordinal) for ordinal in range(1, 13))
    changed = replace(receipts[0], runtime_identity_sha256=_sha("other-runtime"))

    with pytest.raises(
        RedLivingDexPoweredSupplyError,
        match="missed its prospective target",
    ):
        admit_red_living_dex_powered_supply_tranche(
            plan,
            (changed, *receipts[1:]),
            (),
        )


def test_two_successes_cannot_share_one_assignment_claim() -> None:
    plan = _plan()
    receipts = list(_receipt(plan, ordinal) for ordinal in range(1, 13))
    receipts[1] = replace(
        receipts[1],
        assignment_claim_sha256=receipts[0].assignment_claim_sha256,
    )

    with pytest.raises(
        RedLivingDexPoweredSupplyError,
        match="assignment claim",
    ):
        admit_red_living_dex_powered_supply_tranche(plan, tuple(receipts), ())


def test_physical_root_derivation_matches_the_authenticated_root_contract() -> None:
    state = _sha("physical-state")
    envelope = _sha("physical-envelope")
    assert terminal_physical_root_sha256(
        state_sha256=state,
        envelope_sha256=envelope,
    ) == canonical_sha256(
        {
            "envelope_sha256": envelope,
            "schema": "pokemon.red.private-physical-setup-root.v1",
            "state_sha256": state,
        }
    )


def test_success_failure_and_admission_documents_round_trip_canonically() -> None:
    plan = _plan()
    receipt = _receipt(plan, 1)
    failure = _failure(plan, 4)
    receipts = tuple(_receipt(plan, ordinal) for ordinal in range(1, 13))
    admission = admit_red_living_dex_powered_supply_tranche(plan, receipts, ())

    assert parse_red_living_dex_powered_supply_receipt(
        encode_red_living_dex_powered_supply_receipt(receipt)
    ) == receipt
    assert parse_red_living_dex_powered_supply_failure(
        encode_red_living_dex_powered_supply_failure(failure)
    ) == failure
    assert parse_red_living_dex_powered_supply_admission(
        encode_red_living_dex_powered_supply_admission(admission)
    ) == admission


@pytest.mark.parametrize(
    ("encoder", "parser", "value"),
    (
        (
            encode_red_living_dex_powered_supply_receipt,
            parse_red_living_dex_powered_supply_receipt,
            "receipt",
        ),
        (
            encode_red_living_dex_powered_supply_failure,
            parse_red_living_dex_powered_supply_failure,
            "failure",
        ),
        (
            encode_red_living_dex_powered_supply_admission,
            parse_red_living_dex_powered_supply_admission,
            "admission",
        ),
    ),
)
def test_disposition_parsers_reject_unknown_fields_and_authority_mutations(
    encoder: object,
    parser: object,
    value: str,
) -> None:
    plan = _plan()
    target: object
    if value == "receipt":
        target = _receipt(plan, 1)
        needle = b'"started_from_clean_power":true'
        replacement = b'"started_from_clean_power":false'
    elif value == "failure":
        target = _failure(plan, 1)
        needle = b'"retry_allowed":false'
        replacement = b'"retry_allowed":true'
    else:
        target = admit_red_living_dex_powered_supply_tranche(
            plan,
            tuple(_receipt(plan, ordinal) for ordinal in range(1, 13)),
            (),
        )
        needle = b'"population_scale_authorized":false'
        replacement = b'"population_scale_authorized":true'
    encode = encoder  # keep the parametrized contract visually explicit
    parse = parser
    payload = encode(target)  # type: ignore[operator]

    with pytest.raises(RedLivingDexPoweredSupplyError):
        parse(payload.replace(b"{", b'{"unknown":0,', 1))  # type: ignore[operator]
    with pytest.raises(RedLivingDexPoweredSupplyError):
        parse(payload.replace(needle, replacement))  # type: ignore[operator]


def test_admission_object_cannot_overstate_yield_or_pass_decision() -> None:
    plan = _plan()
    receipts = tuple(_receipt(plan, ordinal) for ordinal in range(1, 13))
    admission = admit_red_living_dex_powered_supply_tranche(plan, receipts, ())

    with pytest.raises(RedLivingDexPoweredSupplyError):
        replace(admission, roots_admitted=11)
    with pytest.raises(RedLivingDexPoweredSupplyError):
        replace(admission, qualification_passed=False)
