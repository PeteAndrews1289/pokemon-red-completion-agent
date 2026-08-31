from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_red_living_dex_fresh_episode_runtime import (
    _FakeEmulator,
    _powered_conditioner,
    _powered_plan,
    _powered_teacher,
    _powered_verifier,
    _registry,
    _store,
)

from pokemon_red_completion import red_living_dex_fresh_episode_runtime as runtime
from pokemon_red_completion.private_artifacts import PrivateArtifactError
from pokemon_red_completion.red_living_dex_fresh_episode_runtime import (
    RedLivingDexFreshEpisodeExecutionFailure,
    execute_red_living_dex_powered_supply_episode,
    issue_red_living_dex_fresh_episode_process_authority,
)
from pokemon_red_completion.red_living_dex_powered_lineage_supply import (
    powered_supply_collection_id,
)
from pokemon_red_completion.red_living_dex_powered_supply_admission import (
    RedLivingDexPoweredSupplyAdmissionError,
    authenticate_red_living_dex_powered_supply_private_tranche,
)


def _generate(
    tmp_path: Path,
    *,
    successful_ordinals: set[int],
):  # type: ignore[no-untyped-def]
    plan = _powered_plan()
    store = _store(tmp_path)
    registry = _registry(tmp_path)
    for ordinal, assignment in enumerate(plan.assignments, start=1):
        if ordinal not in successful_ordinals:
            continue
        runtime._PROCESS_AUTHORITY_ISSUED = False
        with store.collection_session(
            powered_supply_collection_id(plan.plan_sha256)
        ) as collection_session:
            execute_red_living_dex_powered_supply_episode(
                plan,
                assignment.assignment_id,
                source_commit=plan.source_commit,
                source_bundle_sha256=plan.source_bundle_sha256,
                generator_execution_sha256=plan.generator_execution_sha256,
                runner_sha256=plan.generator_runner_sha256,
                runtime_identity_sha256=plan.runtime_identity_sha256,
                process_authority=issue_red_living_dex_fresh_episode_process_authority(),
                private_store=store,
                collection_session=collection_session,
                claim_registry=registry,
                emulator_factory=_FakeEmulator,
                setup_teacher=_powered_teacher,
                condition_target=_powered_conditioner,
                verify_target=_powered_verifier,
                post_close_verify=lambda: None,
            )
    return plan, store, registry


def _fail_assignment(
    plan,  # type: ignore[no-untyped-def]
    assignment,  # type: ignore[no-untyped-def]
    store,  # type: ignore[no-untyped-def]
    registry: Path,
) -> None:
    def fail_conditioning(*_args: object) -> None:
        raise RuntimeError("private diagnostic only")

    runtime._PROCESS_AUTHORITY_ISSUED = False
    with (
        store.collection_session(
            powered_supply_collection_id(plan.plan_sha256)
        ) as collection_session,
        pytest.raises(RedLivingDexFreshEpisodeExecutionFailure),
    ):
        execute_red_living_dex_powered_supply_episode(
            plan,
            assignment.assignment_id,
            source_commit=plan.source_commit,
            source_bundle_sha256=plan.source_bundle_sha256,
            generator_execution_sha256=plan.generator_execution_sha256,
            runner_sha256=plan.generator_runner_sha256,
            runtime_identity_sha256=plan.runtime_identity_sha256,
            process_authority=issue_red_living_dex_fresh_episode_process_authority(),
            private_store=store,
            collection_session=collection_session,
            claim_registry=registry,
            emulator_factory=_FakeEmulator,
            setup_teacher=_powered_teacher,
            condition_target=fail_conditioning,
            verify_target=_powered_verifier,
            post_close_verify=lambda: None,
        )


def test_complete_private_tranche_admits_all_roots_without_emulator_restore(
    tmp_path: Path,
) -> None:
    plan, store, registry = _generate(
        tmp_path,
        successful_ordinals=set(range(1, 13)),
    )

    bundle = authenticate_red_living_dex_powered_supply_private_tranche(
        plan,
        private_store=store,
        claim_registry=registry,
        recover_interrupted=True,
    )

    assert bundle.admission.qualification_passed is True
    assert bundle.admission.roots_admitted == 12
    assert bundle.failures == ()
    assert len({item.receipt.root_lineage_id for item in bundle.roots}) == 12
    assert len({item.root.physical_root_sha256 for item in bundle.roots}) == 12
    public = bundle.public_dict()
    assert public["controller_actions"] == 0
    assert public["emulator_frames"] == 0
    assert public["root_state_restores"] == 0
    assert public["root_claims"] == 0
    assert public["population_scale_authorized"] is False
    assert "/private" not in str(public)


def test_one_terminal_train_failure_remains_in_denominator_and_can_pass(
    tmp_path: Path,
) -> None:
    plan, store, registry = _generate(
        tmp_path,
        successful_ordinals=set(range(2, 13)),
    )
    _fail_assignment(plan, plan.assignments[0], store, registry)

    bundle = authenticate_red_living_dex_powered_supply_private_tranche(
        plan,
        private_store=store,
        claim_registry=registry,
        recover_interrupted=True,
    )

    assert bundle.admission.roots_admitted == 11
    assert bundle.admission.attempts_failed == 1
    assert bundle.admission.qualification_passed is True
    assert bundle.failures[0].assignment_id == plan.assignments[0].assignment_id
    assert bundle.failures[0].retry_allowed is False
    assert bundle.failures[0].effects_known is False


def test_missing_assignment_never_becomes_an_implicit_failure(
    tmp_path: Path,
) -> None:
    plan, store, registry = _generate(
        tmp_path,
        successful_ordinals=set(range(1, 12)),
    )

    with pytest.raises(
        RedLivingDexPoweredSupplyAdmissionError,
        match="denominator is incomplete",
    ):
        authenticate_red_living_dex_powered_supply_private_tranche(
            plan,
            private_store=store,
            claim_registry=registry,
            recover_interrupted=True,
        )


def test_success_without_its_durable_claim_is_rejected(
    tmp_path: Path,
) -> None:
    plan, store, registry = _generate(
        tmp_path,
        successful_ordinals=set(range(1, 13)),
    )
    marker = registry / (
        f"fresh-episode-assignment-{plan.assignments[0].assignment_id}.json"
    )
    marker.unlink()

    with pytest.raises(
        RedLivingDexPoweredSupplyAdmissionError,
        match="claim is absent",
    ):
        authenticate_red_living_dex_powered_supply_private_tranche(
            plan,
            private_store=store,
            claim_registry=registry,
            recover_interrupted=True,
        )


def test_missing_contingency_root_closes_population_scale(
    tmp_path: Path,
) -> None:
    plan, store, registry = _generate(
        tmp_path,
        successful_ordinals=set(range(1, 12)),
    )
    _fail_assignment(plan, plan.assignments[11], store, registry)

    bundle = authenticate_red_living_dex_powered_supply_private_tranche(
        plan,
        private_store=store,
        claim_registry=registry,
        recover_interrupted=True,
    )

    assert bundle.admission.roots_admitted == 11
    assert bundle.admission.qualification_passed is False
    assert bundle.public_dict()["status"] == (
        "bounded_yield_qualification_failed_population_closed"
    )


def test_interrupted_namespace_recovery_is_terminal_and_record_reproducible(
    tmp_path: Path,
) -> None:
    plan, store, registry = _generate(
        tmp_path,
        successful_ordinals=set(range(2, 13)),
    )
    store.begin_episode(plan.assignments[0].episode_id)

    recovered = authenticate_red_living_dex_powered_supply_private_tranche(
        plan,
        private_store=store,
        claim_registry=registry,
        recover_interrupted=True,
    )
    reopened = authenticate_red_living_dex_powered_supply_private_tranche(
        plan,
        private_store=store,
        claim_registry=registry,
        recover_interrupted=False,
    )

    assert recovered.recovered_episode_namespaces == 1
    assert reopened.recovered_episode_namespaces == 0
    assert recovered.failures[0].failure_stage == "private_episode_interrupted"
    assert recovered.admission.qualification_passed is True
    assert recovered.private_dict() == reopened.private_dict()


def test_admission_cannot_recover_a_partial_while_generation_holds_the_plan_lock(
    tmp_path: Path,
) -> None:
    plan, store, registry = _generate(
        tmp_path,
        successful_ordinals=set(range(2, 13)),
    )
    assignment = plan.assignments[0]
    store.begin_episode(assignment.episode_id)

    with store.collection_session(
        powered_supply_collection_id(plan.plan_sha256)
    ), pytest.raises(PrivateArtifactError, match="collection is already active"):
        authenticate_red_living_dex_powered_supply_private_tranche(
            plan,
            private_store=store,
            claim_registry=registry,
            recover_interrupted=True,
        )

    assert store.inspect_episode_state(assignment.episode_id).status == "partial"


def test_present_malformed_failure_claim_is_never_treated_as_absent(
    tmp_path: Path,
) -> None:
    plan, store, registry = _generate(
        tmp_path,
        successful_ordinals=set(range(2, 13)),
    )
    assignment = plan.assignments[0]
    _fail_assignment(plan, assignment, store, registry)
    marker = registry / f"fresh-episode-assignment-{assignment.assignment_id}.json"
    marker.write_bytes(b'{"schema":"corrupt"}\n')

    with pytest.raises(
        RedLivingDexPoweredSupplyAdmissionError,
        match="claim cannot be authenticated",
    ):
        authenticate_red_living_dex_powered_supply_private_tranche(
            plan,
            private_store=store,
            claim_registry=registry,
            recover_interrupted=True,
        )


def test_failure_claim_from_another_runtime_is_rejected(
    tmp_path: Path,
) -> None:
    plan, store, registry = _generate(
        tmp_path,
        successful_ordinals=set(range(2, 13)),
    )
    assignment = plan.assignments[0]
    _fail_assignment(plan, assignment, store, registry)
    marker = registry / f"fresh-episode-assignment-{assignment.assignment_id}.json"
    claim = json.loads(marker.read_bytes())
    claim["runtime_identity_sha256"] = "f" * 64
    marker.write_bytes(
        json.dumps(claim, allow_nan=False, separators=(",", ":"), sort_keys=True).encode(
            "ascii"
        )
        + b"\n"
    )

    with pytest.raises(
        RedLivingDexPoweredSupplyAdmissionError,
        match="assignment claim differs",
    ):
        authenticate_red_living_dex_powered_supply_private_tranche(
            plan,
            private_store=store,
            claim_registry=registry,
            recover_interrupted=True,
        )
