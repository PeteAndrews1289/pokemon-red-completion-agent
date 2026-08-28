from __future__ import annotations

import inspect
import json
from dataclasses import replace

import pytest

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_episode_lineage import (
    RED_LIVING_DEX_FRESH_EPISODE_FIRST_TRANCHE_TARGETS,
    RedLivingDexEpisodeLineageError,
    RedLivingDexFreshEpisodeAssignment,
    RedLivingDexFreshEpisodeFailureReceipt,
    RedLivingDexFreshEpisodeReceipt,
    admit_red_living_dex_fresh_episode_tranche,
    build_red_living_dex_fresh_episode_plan,
    compose_red_living_dex_fresh_episode_teacher_execution_sha256,
    derive_red_living_dex_initial_wait_frames,
    encode_red_living_dex_fresh_episode_plan,
    expected_red_living_dex_first_controller_input_frame,
    parse_red_living_dex_fresh_episode_plan,
    preflight_red_living_dex_fresh_episode_plan,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupProtectedEffectCheckpoint,
)


def _digest(label: str) -> str:
    return canonical_sha256({"label": label})


def _plan():  # type: ignore[no-untyped-def]
    source = _digest("source")
    generator = _digest("generator")
    return build_red_living_dex_fresh_episode_plan(
        source_commit="a" * 40,
        source_bundle_sha256=source,
        teacher_execution_sha256=(
            compose_red_living_dex_fresh_episode_teacher_execution_sha256(
                source_bundle_sha256=source,
                generator_execution_sha256=generator,
            )
        ),
        generator_execution_sha256=generator,
        capacity_evidence_sha256=_digest("capacity"),
    )


def _receipt(assignment, index: int):  # type: ignore[no-untyped-def]
    return RedLivingDexFreshEpisodeReceipt(
        assignment_id=assignment.assignment_id,
        plan_sha256=_plan().plan_sha256,
        assignment_claim_sha256=_digest(f"claim-{index}"),
        root_lineage_id=assignment.root_lineage_id,
        episode_id=assignment.episode_id,
        source_bundle_sha256=assignment.source_bundle_sha256,
        teacher_execution_sha256=assignment.teacher_execution_sha256,
        generator_execution_sha256=assignment.generator_execution_sha256,
        started_from_clean_power=True,
        distinct_process_episode=True,
        parent_state_sha256=None,
        parent_root_lineage_id=None,
        save_state_loads=0,
        terminal_state_saves=1,
        initial_wait_frames=assignment.initial_wait_frames,
        first_controller_input_frame=(
            expected_red_living_dex_first_controller_input_frame(
                assignment.initial_wait_frames
            )
        ),
        trajectory_prefix_sha256=_digest(f"trajectory-{index}"),
        target_template_ordinal=assignment.target_template_ordinal,
        compatible_template_ordinals=(assignment.target_template_ordinal,),
        observed_storage_pressure_millionths=(
            assignment.target_storage_pressure_millionths
        ),
        terminal_state_sha256=_digest(f"state-{index}"),
        terminal_envelope_sha256=_digest(f"envelope-{index}"),
        terminal_checkpoint_id=assignment.target_checkpoint_id,
        controller_actions=1_000 + index,
        emulator_frames=assignment.initial_wait_frames + 100_000 + index,
        setup_teacher_executions=1,
        learner_teacher_queries=0,
        learner_labels=0,
        learner_outcomes=0,
        model_predictions=0,
        model_fits=0,
    )


def _receipts():  # type: ignore[no-untyped-def]
    return tuple(
        _receipt(assignment, index)
        for index, assignment in enumerate(_plan().assignments)
    )


def _failure(assignment):  # type: ignore[no-untyped-def]
    plan = _plan()
    return RedLivingDexFreshEpisodeFailureReceipt(
        assignment_id=assignment.assignment_id,
        plan_sha256=plan.plan_sha256,
        source_bundle_sha256=assignment.source_bundle_sha256,
        teacher_execution_sha256=assignment.teacher_execution_sha256,
        generator_execution_sha256=assignment.generator_execution_sha256,
        assignment_claim_sha256=_digest("failed-claim"),
        failure_stage="fresh_episode_execution",
        effects_known=False,
        controller_actions=None,
        emulator_frames=None,
    )


def test_first_tranche_is_canonical_train_only_and_round_trips() -> None:
    plan = _plan()
    payload = encode_red_living_dex_fresh_episode_plan(plan)
    parsed = parse_red_living_dex_fresh_episode_plan(payload)

    assert parsed == plan
    assert len(plan.assignments) == 13
    assert {item.partition for item in plan.assignments} == {"train"}
    assert len({item.harness_seed for item in plan.assignments}) == 13
    assert len({item.initial_wait_frames for item in plan.assignments}) == 13
    assert len({item.root_lineage_id for item in plan.assignments}) == 13
    assert all(len(item.episode_id) <= 80 for item in plan.assignments)
    assert {
        item.target_storage_pressure_millionths
        for item in plan.assignments
        if item.target_storage_pressure_millionths is not None
    } == {625_000, 750_000, 875_000}
    assert {
        ordinal: sum(
            item.target_template_ordinal == ordinal for item in plan.assignments
        )
        for ordinal in RED_LIVING_DEX_FRESH_EPISODE_FIRST_TRANCHE_TARGETS
    } == dict(RED_LIVING_DEX_FRESH_EPISODE_FIRST_TRANCHE_TARGETS)
    assert b"/Users/" not in payload
    assert b"terminal_state_sha256" not in payload


def test_plan_builder_has_no_seed_or_schedule_choice_surface() -> None:
    parameters = inspect.signature(
        build_red_living_dex_fresh_episode_plan
    ).parameters

    assert tuple(parameters) == (
        "source_commit",
        "source_bundle_sha256",
        "teacher_execution_sha256",
        "generator_execution_sha256",
        "capacity_evidence_sha256",
    )


def test_assignment_lineage_is_committed_before_any_terminal_state() -> None:
    assignment = _plan().assignments[0]

    assert assignment.assignment_id == canonical_sha256(
        assignment._commitment_dict()
    )
    assert assignment.root_lineage_id.endswith(assignment.assignment_id)
    assert "state" not in assignment._commitment_dict()
    assert "rng" not in assignment._commitment_dict()

    with pytest.raises(
        RedLivingDexEpisodeLineageError,
        match="committed prospectively",
    ):
        replace(assignment, assignment_id=_digest("post-hoc"))


def test_plan_rejects_duplicate_wait_or_missing_scarce_target() -> None:
    plan = _plan()
    first = plan.assignments[0]
    original = plan.assignments[1]
    duplicate_seed = original.harness_seed + 1
    while derive_red_living_dex_initial_wait_frames(duplicate_seed) != (
        first.initial_wait_frames
    ):
        duplicate_seed += 1
    commitment = {
        **original._commitment_dict(),
        "harness_seed": duplicate_seed,
        "initial_wait_frames": first.initial_wait_frames,
    }
    assignment_id = canonical_sha256(commitment)
    duplicate_wait = RedLivingDexFreshEpisodeAssignment(
        campaign_id=original.campaign_id,
        run_id=original.run_id,
        ordinal=original.ordinal,
        declared_runs=original.declared_runs,
        partition=original.partition,
        harness_seed=duplicate_seed,
        initial_wait_frames=first.initial_wait_frames,
        target_template_ordinal=original.target_template_ordinal,
        target_active_box_count=original.target_active_box_count,
        target_checkpoint_id=original.target_checkpoint_id,
        source_bundle_sha256=original.source_bundle_sha256,
        teacher_execution_sha256=original.teacher_execution_sha256,
        generator_execution_sha256=original.generator_execution_sha256,
        capacity_evidence_sha256=original.capacity_evidence_sha256,
        assignment_id=assignment_id,
        root_lineage_id=f"red-living-dex-fresh-root-{assignment_id}",
        episode_id=f"red-ldx-fresh-{assignment_id}",
    )

    with pytest.raises(
        RedLivingDexEpisodeLineageError,
        match="seed and target schedule differs",
    ):
        replace(
            plan,
            assignments=(
                first,
                duplicate_wait,
                *plan.assignments[2:],
            ),
        )

    with pytest.raises(
        RedLivingDexEpisodeLineageError,
        match="seed and target schedule differs",
    ):
        last = plan.assignments[-1]
        changed_commitment = {
            **last._commitment_dict(),
            "target_active_box_count": 17,
            "target_template_ordinal": 2,
        }
        changed_id = canonical_sha256(changed_commitment)
        changed_target = RedLivingDexFreshEpisodeAssignment(
            campaign_id=last.campaign_id,
            run_id=last.run_id,
            ordinal=last.ordinal,
            declared_runs=last.declared_runs,
            partition=last.partition,
            harness_seed=last.harness_seed,
            initial_wait_frames=last.initial_wait_frames,
            target_template_ordinal=2,
            target_active_box_count=17,
            target_checkpoint_id=last.target_checkpoint_id,
            source_bundle_sha256=last.source_bundle_sha256,
            teacher_execution_sha256=last.teacher_execution_sha256,
            generator_execution_sha256=last.generator_execution_sha256,
            capacity_evidence_sha256=last.capacity_evidence_sha256,
            assignment_id=changed_id,
            root_lineage_id=f"red-living-dex-fresh-root-{changed_id}",
            episode_id=f"red-ldx-fresh-{changed_id}",
        )
        replace(plan, assignments=(*plan.assignments[:-1], changed_target))


def test_plan_rejects_assignment_execution_binding_drift() -> None:
    plan = _plan()
    assignment = plan.assignments[0]

    for field in (
        "source_bundle_sha256",
        "teacher_execution_sha256",
        "generator_execution_sha256",
        "capacity_evidence_sha256",
    ):
        with pytest.raises(
            RedLivingDexEpisodeLineageError,
            match="teacher execution|committed prospectively",
        ):
            replace(assignment, **{field: _digest(f"changed-{field}")})


def test_non_storage_assignment_rejects_active_box_target() -> None:
    assignment = _plan().assignments[-1]

    with pytest.raises(
        RedLivingDexEpisodeLineageError,
        match="non-storage fresh episode",
    ):
        replace(assignment, target_active_box_count=17)


def test_complete_fresh_tranche_admits_only_pending_recensus() -> None:
    plan = _plan()
    admission = admit_red_living_dex_fresh_episode_tranche(plan, _receipts())
    public = admission.public_dict()

    assert admission.roots_admitted == 13
    assert admission.attempts_failed == 0
    assert admission.plan_sha256 == plan.plan_sha256
    assert public["recensus_required"] is True
    assert public["collection_authorized"] is False
    assert public["outcomes"] == 0
    assert public["model_fits"] == 0
    assert public["target_template_counts"] == {"2": 6, "3": 6, "5": 1}


def test_failed_assignment_does_not_poison_other_valid_roots() -> None:
    plan = _plan()
    receipts = _receipts()
    admission = admit_red_living_dex_fresh_episode_tranche(
        plan,
        receipts[:-1],
        (_failure(plan.assignments[-1]),),
    )

    assert admission.roots_admitted == 12
    assert admission.attempts_failed == 1
    assert admission.public_dict()["attempts_total"] == 13
    assert admission.public_dict()["recensus_required"] is True


def test_admission_requires_every_frozen_success_or_failure_disposition() -> None:
    plan = _plan()

    with pytest.raises(
        RedLivingDexEpisodeLineageError,
        match="disposition tranche is incomplete",
    ):
        admit_red_living_dex_fresh_episode_tranche(plan, _receipts()[:-1])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("attempt_consumed", False, "not terminal"),
        ("retry_allowed", True, "not terminal"),
        ("terminal_root_generated", True, "not terminal"),
        ("effects_known", True, "known effects"),
        ("failure_stage", "private/path", "stage is invalid"),
    ),
)
def test_failure_disposition_rejects_every_authority_overclaim(
    field: str,
    value: object,
    message: str,
) -> None:
    failure = _failure(_plan().assignments[-1])

    with pytest.raises(RedLivingDexEpisodeLineageError, match=message):
        replace(failure, **{field: value})


def test_admission_rejects_failure_binding_drift_or_duplicate_disposition() -> None:
    plan = _plan()
    receipts = _receipts()
    failure = _failure(plan.assignments[-1])

    with pytest.raises(
        RedLivingDexEpisodeLineageError,
        match="failure differs",
    ):
        admit_red_living_dex_fresh_episode_tranche(
            plan,
            receipts[:-1],
            (replace(failure, source_bundle_sha256=_digest("changed")),),
        )

    with pytest.raises(
        RedLivingDexEpisodeLineageError,
        match="disposition assignment is duplicated",
    ):
        admit_red_living_dex_fresh_episode_tranche(
            plan,
            receipts[:-1],
            (replace(failure, assignment_id=receipts[0].assignment_id),),
        )


def test_admission_rejects_duplicate_receipts() -> None:
    plan = _plan()
    receipts = _receipts()

    with pytest.raises(
        RedLivingDexEpisodeLineageError,
        match="assignment is duplicated",
    ):
        admit_red_living_dex_fresh_episode_tranche(
            plan,
            (receipts[0], receipts[0], *receipts[2:]),
        )


def test_action_free_preflight_has_no_generation_or_learning_effect() -> None:
    zero = RedLivingDexSetupProtectedEffectCheckpoint()
    preflight = preflight_red_living_dex_fresh_episode_plan(
        _plan(),
        effects_before=zero,
        effects_after=zero,
    ).public_dict()

    assert preflight["assignments"] == 13
    assert preflight["root_generation_executions"] == 0
    assert preflight["controller_actions"] == 0
    assert preflight["emulator_frames"] == 0
    assert preflight["learner_outcomes"] == 0
    assert preflight["model_fits"] == 0
    assert preflight["target_template_counts"] == {"2": 6, "3": 6, "5": 1}

    with pytest.raises(
        RedLivingDexEpisodeLineageError,
        match="protected effect",
    ):
        preflight_red_living_dex_fresh_episode_plan(
            _plan(),
            effects_before=zero,
            effects_after=replace(zero, controller_actions=1),
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("started_from_clean_power", False, "clean power"),
        ("distinct_process_episode", False, "emulator process"),
        ("parent_state_sha256", "f" * 64, "checkpoint or parent"),
        ("save_state_loads", 1, "state loads"),
        ("terminal_state_saves", 2, "terminal state saves"),
        ("learner_teacher_queries", 1, "learner teacher queries"),
        ("learner_labels", 1, "learner labels"),
        ("learner_outcomes", 1, "learner outcomes"),
        ("model_predictions", 1, "model predictions"),
        ("model_fits", 1, "model fits"),
    ),
)
def test_receipt_rejects_checkpoint_or_learner_effects(
    field: str,
    value: object,
    message: str,
) -> None:
    receipt = _receipts()[0]

    with pytest.raises(RedLivingDexEpisodeLineageError, match=message):
        replace(receipt, **{field: value})


@pytest.mark.parametrize("delta", (-1, 1))
def test_receipt_rejects_first_controller_input_timing_drift(delta: int) -> None:
    receipt = _receipts()[0]

    with pytest.raises(
        RedLivingDexEpisodeLineageError,
        match="diverge before first controller input",
    ):
        replace(
            receipt,
            first_controller_input_frame=(
                receipt.first_controller_input_frame + delta
            ),
        )


def test_admission_rejects_cloned_or_rehashed_roots() -> None:
    plan = _plan()
    receipts = _receipts()

    cloned_state = (
        receipts[0],
        replace(
            receipts[1],
            terminal_state_sha256=receipts[0].terminal_state_sha256,
        ),
        *receipts[2:],
    )
    with pytest.raises(
        RedLivingDexEpisodeLineageError,
        match="terminal state",
    ):
        admit_red_living_dex_fresh_episode_tranche(plan, cloned_state)

    cloned_trajectory = (
        receipts[0],
        replace(
            receipts[1],
            trajectory_prefix_sha256=receipts[0].trajectory_prefix_sha256,
        ),
        *receipts[2:],
    )
    with pytest.raises(
        RedLivingDexEpisodeLineageError,
        match="trajectory prefix",
    ):
        admit_red_living_dex_fresh_episode_tranche(plan, cloned_trajectory)

    rehashed = (
        replace(
            receipts[0],
            root_lineage_id=(
                f"red-living-dex-fresh-root-{receipts[0].terminal_state_sha256}"
            ),
        ),
        *receipts[1:],
    )
    with pytest.raises(
        RedLivingDexEpisodeLineageError,
        match="pre-controller assignment",
    ):
        admit_red_living_dex_fresh_episode_tranche(plan, rehashed)


def test_receipt_rejects_off_target_template_or_pressure() -> None:
    receipt = _receipts()[0]

    with pytest.raises(
        RedLivingDexEpisodeLineageError,
        match="authentic train template",
    ):
        replace(receipt, compatible_template_ordinals=(0,))

    plan = _plan()
    receipts = _receipts()
    wrong_pressure = (
        replace(receipts[0], observed_storage_pressure_millionths=500_000),
        *receipts[1:],
    )
    with pytest.raises(
        RedLivingDexEpisodeLineageError,
        match="pre-controller assignment",
    ):
        admit_red_living_dex_fresh_episode_tranche(plan, wrong_pressure)


def test_parser_rejects_authority_or_noncanonical_drift() -> None:
    payload = encode_red_living_dex_fresh_episode_plan(_plan())
    document = json.loads(payload)
    document["development_materialized"] = True
    drifted = (
        json.dumps(document, separators=(",", ":"), sort_keys=True).encode("ascii")
        + b"\n"
    )

    with pytest.raises(
        RedLivingDexEpisodeLineageError,
        match="authority boundary",
    ):
        parse_red_living_dex_fresh_episode_plan(drifted)
    with pytest.raises(
        RedLivingDexEpisodeLineageError,
        match="canonical ASCII JSON",
    ):
        parse_red_living_dex_fresh_episode_plan(payload.rstrip())
