from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCaptureAttestation,
    LivingDexCapturePartition,
    LivingDexCaptureSetupStatus,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    initialize_private_root,
)
from pokemon_red_completion.red_living_dex_capture_plan import (
    RED_LIVING_DEX_EXECUTOR_CAPABILITIES,
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_setup_campaign import (
    RED_LIVING_DEX_SETUP_PLAN_RECORD_ID,
    RedLivingDexControlledSetupFailure,
    RedLivingDexSetupBindingPlan,
    RedLivingDexSetupCampaignError,
    RedLivingDexSetupDisposition,
    RedLivingDexSetupExecution,
    RedLivingDexSetupOptionBinding,
    RedLivingDexSetupOptionProof,
    RedLivingDexSetupSlotBinding,
    RedLivingDexSetupTransportKind,
    build_red_living_dex_setup_binding_plan,
    run_red_living_dex_setup_campaign,
)
from pokemon_red_completion.routed_semantic_goal import (
    RoutedSemanticBudgetCheckpoint,
)


def _digest(value: object) -> str:
    return hashlib.sha256(str(value).encode("ascii")).hexdigest()


_CAPABILITY = {item.option_kind: item for item in RED_LIVING_DEX_EXECUTOR_CAPABILITIES}
_GOAL_KIND = {
    LivingDexOptionKind.ACQUIRE: GoalKind.ACQUIRE_SPECIES,
    LivingDexOptionKind.EVOLVE: GoalKind.EVOLVE_SPECIES,
    LivingDexOptionKind.DEVELOP: GoalKind.DEVELOP_TEAM,
    LivingDexOptionKind.MANAGE_STORAGE: GoalKind.MANAGE_STORAGE,
    LivingDexOptionKind.RESUPPLY: GoalKind.RESUPPLY,
    LivingDexOptionKind.UNLOCK_ACCESS: GoalKind.ADVANCE_STORY,
    LivingDexOptionKind.EXPLORE: GoalKind.EXPLORE,
}


def _provider_contract(kind: LivingDexOptionKind) -> str:
    provider = _CAPABILITY[kind].executor_types[0]
    return f"{provider.__module__}.{provider.__qualname__}"


def _binding(index: int) -> RedLivingDexSetupSlotBinding:
    slot = build_red_living_dex_prospective_capture_plan().slots[index]
    origin_state = _digest(("origin-state", index))
    origin_boundary = _digest(("origin-boundary", index))
    local = index == 0
    options = []
    for option_index, kind in enumerate(slot.available_option_kinds):
        suffix = (index, option_index, kind.value)
        options.append(
            RedLivingDexSetupOptionBinding(
                option_kind=kind,
                goal_kind=_GOAL_KIND[kind],
                transport_kind=(
                    RedLivingDexSetupTransportKind.LOCAL
                    if local
                    else RedLivingDexSetupTransportKind.ROUTED
                ),
                provider_contract_id=_provider_contract(kind),
                provider_capability_sha256=_CAPABILITY[kind].capability_sha256,
                origin_state_sha256=origin_state,
                origin_boundary_sha256=origin_boundary,
                destination_terminal_boundary_sha256=(
                    origin_boundary if local else _digest(("destination-boundary", *suffix))
                ),
                expected_fresh_observation_sha256=_digest(("fresh-observation", *suffix)),
                expected_provider_offer_sha256=_digest(("provider-offer", *suffix)),
                expected_executable_binding_sha256=_digest(("executable-binding", *suffix)),
                route_plan_sha256=(None if local else _digest(("route-plan", *suffix))),
                route_terminal_predicate_sha256=(
                    None if local else _digest(("route-terminal", *suffix))
                ),
                route_planner_binding_sha256=(
                    None if local else _digest(("route-planner", *suffix))
                ),
            )
        )
    return RedLivingDexSetupSlotBinding(
        slot_sha256=slot.slot_sha256,
        setup_plan_sha256=slot.setup.setup_plan_sha256,
        terminal_predicate_sha256=slot.setup.terminal_predicate_sha256,
        observer_contract_sha256=slot.setup.observer_contract_sha256,
        partition=slot.partition,
        available_option_kinds=slot.available_option_kinds,
        root_consumption_sha256=_digest(("root", index)),
        state_sha256=origin_state,
        origin_boundary_sha256=origin_boundary,
        envelope_sha256=_digest(("envelope", index)),
        menu_sha256=_digest(("menu", index)),
        observer_binding_sha256=_digest(("observer", index)),
        available_family_sha256s=tuple(
            _digest(("family", slot.family_scope_id, option_index, index))
            for option_index, _kind in enumerate(slot.available_option_kinds)
        ),
        location_sha256=_digest(("location", slot.location_scope_id)),
        option_bindings=tuple(options),
    )


def _plan() -> RedLivingDexSetupBindingPlan:
    return build_red_living_dex_setup_binding_plan(tuple(_binding(index) for index in range(15)))


def _store(tmp_path: Path) -> PrivateArtifactRoot:
    repository = tmp_path / "repository"
    root = tmp_path / "private"
    repository.mkdir()
    root.mkdir()

    def device_id(path: Path) -> int:
        return 2 if path == root.resolve() else 1

    return initialize_private_root(
        root,
        repository_root=repository,
        device_id=device_id,
        git_worktree_probe=lambda _path: False,
    )


class _Meter:
    def __init__(self) -> None:
        self.actions = 0
        self.frames = 0

    def checkpoint(self) -> RoutedSemanticBudgetCheckpoint:
        return RoutedSemanticBudgetCheckpoint(self.actions, self.frames)

    def spend(self, actions: int = 2, frames: int = 10) -> None:
        self.actions += actions
        self.frames += frames


def _execution(
    binding: RedLivingDexSetupSlotBinding,
    *,
    actions: int = 2,
    frames: int = 10,
) -> RedLivingDexSetupExecution:
    return RedLivingDexSetupExecution(
        slot_binding_sha256=binding.binding_sha256,
        capture_attestation=LivingDexCaptureAttestation(
            slot_sha256=binding.slot_sha256,
            setup_plan_sha256=binding.setup_plan_sha256,
            terminal_predicate_sha256=binding.terminal_predicate_sha256,
            observer_contract_sha256=binding.observer_contract_sha256,
            root_consumption_sha256=binding.root_consumption_sha256,
            state_sha256=binding.state_sha256,
            envelope_sha256=binding.envelope_sha256,
            menu_sha256=binding.menu_sha256,
            observer_binding_sha256=binding.observer_binding_sha256,
            available_option_kinds=binding.available_option_kinds,
            available_family_sha256s=binding.available_family_sha256s,
            location_sha256=binding.location_sha256,
            setup_controller_actions=actions,
            setup_emulator_frames=frames,
        ),
        option_proofs=tuple(
            RedLivingDexSetupOptionProof(
                option_binding_sha256=option.binding_sha256,
                fresh_observation_sha256=(option.expected_fresh_observation_sha256),
                provider_offer_sha256=option.expected_provider_offer_sha256,
                executable_binding_sha256=(option.expected_executable_binding_sha256),
            )
            for option in binding.option_bindings
        ),
    )


class _Executor:
    def __init__(
        self,
        store: PrivateArtifactRoot,
        meter: _Meter,
        *,
        fail_at: int | None = None,
        invalid_at: int | None = None,
    ) -> None:
        self.store = store
        self.meter = meter
        self.fail_at = fail_at
        self.invalid_at = invalid_at
        self.calls: list[str] = []

    def execute_setup(
        self,
        binding: RedLivingDexSetupSlotBinding,
    ) -> RedLivingDexSetupExecution:
        ordinal = next(
            index
            for index, slot in enumerate(build_red_living_dex_prospective_capture_plan().slots)
            if slot.slot_sha256 == binding.slot_sha256
        )
        self.calls.append(binding.binding_sha256)
        assert (
            self.store.find_sealed_record(
                RED_LIVING_DEX_SETUP_PLAN_RECORD_ID,
                expected_kind="red_living_dex_setup_plan",
            )
            is not None
        )
        episode_id = f"redldx-setup-{ordinal:02d}-{binding.binding_sha256[:32]}"
        assert self.store.inspect_episode_state(episode_id).status == "partial"
        self.meter.spend()
        if ordinal == self.fail_at:
            raise RedLivingDexControlledSetupFailure("fixture_setup_failed")
        execution = _execution(binding)
        if ordinal == self.invalid_at:
            wrong = replace(
                execution.option_proofs[0],
                option_binding_sha256="f" * 64,
            )
            execution = replace(
                execution,
                option_proofs=(wrong, *execution.option_proofs[1:]),
            )
        return execution


def test_exact_fifteen_slot_plan_is_complete_and_publicly_path_free() -> None:
    plan = _plan()
    public = plan.public_dict()
    encoded = json.dumps(public, sort_keys=True)

    assert public["slot_count"] == 15
    assert public["train_slots"] == 10
    assert public["development_slots"] == 5
    assert public["local_slots"] == 1
    assert public["routed_slots"] == 14
    assert public["provider_contracts_bound"] == 45
    assert public["runtime_private_bindings_authenticated"] is False
    assert public["runtime_private_routes_executed"] is False
    assert public["option_transport_counts"] == {"local": 3, "routed": 42}
    assert public["learner_behavior_draws"] == 0
    assert public["learner_labels_emitted"] == 0
    assert public["learner_outcomes_observed"] == 0
    for private in (
        plan.plan_sha256,
        plan.bindings[0].state_sha256,
        plan.bindings[1].option_bindings[0].route_plan_sha256,
        plan.bindings[2].observer_binding_sha256,
    ):
        assert private not in encoded


@pytest.mark.parametrize("mutation", ("missing", "reordered", "cross_join"))
def test_binding_plan_rejects_missing_reordered_or_cross_joined_slots(
    mutation: str,
) -> None:
    bindings = list(_plan().bindings)
    if mutation == "missing":
        bindings.pop()
    elif mutation == "reordered":
        bindings[0], bindings[1] = bindings[1], bindings[0]
    else:
        bindings[1] = replace(
            bindings[1],
            slot_sha256=bindings[2].slot_sha256,
        )

    with pytest.raises(
        RedLivingDexSetupCampaignError,
        match="every frozen slot|prospective slot",
    ):
        build_red_living_dex_setup_binding_plan(bindings)


def test_provider_contract_must_match_the_semantic_kind() -> None:
    binding = _binding(1)
    option = binding.option_bindings[0]

    with pytest.raises(
        RedLivingDexSetupCampaignError,
        match="provider contract",
    ):
        replace(
            option,
            provider_contract_id=_provider_contract(LivingDexOptionKind.MANAGE_STORAGE),
        )


def test_local_and_routed_slot_classification_cannot_be_erased() -> None:
    local = _binding(0)
    routed = _binding(1)
    local_option = local.option_bindings[0]
    routed_option = routed.option_bindings[0]
    routed_local = replace(
        routed_option,
        transport_kind=RedLivingDexSetupTransportKind.LOCAL,
        destination_terminal_boundary_sha256=routed.origin_boundary_sha256,
        route_plan_sha256=None,
        route_terminal_predicate_sha256=None,
        route_planner_binding_sha256=None,
    )
    all_local = replace(
        routed,
        option_bindings=tuple(
            replace(
                option,
                transport_kind=RedLivingDexSetupTransportKind.LOCAL,
                destination_terminal_boundary_sha256=routed.origin_boundary_sha256,
                route_plan_sha256=None,
                route_terminal_predicate_sha256=None,
                route_planner_binding_sha256=None,
            )
            for option in routed.option_bindings
        ),
    )

    with pytest.raises(
        RedLivingDexSetupCampaignError,
        match="unnecessarily routed",
    ):
        bindings = list(_plan().bindings)
        bindings[0] = replace(
            local,
            option_bindings=(
                replace(
                    local_option,
                    transport_kind=RedLivingDexSetupTransportKind.ROUTED,
                    destination_terminal_boundary_sha256=_digest("unnecessary-terminal"),
                    route_plan_sha256=_digest("unnecessary-route"),
                    route_terminal_predicate_sha256=_digest("unnecessary-route-terminal"),
                    route_planner_binding_sha256=_digest("unnecessary-route-planner"),
                ),
                *local.option_bindings[1:],
            ),
        )
        build_red_living_dex_setup_binding_plan(bindings)

    with pytest.raises(
        RedLivingDexSetupCampaignError,
        match="lacks a concrete route",
    ):
        bindings = list(_plan().bindings)
        bindings[1] = all_local
        build_red_living_dex_setup_binding_plan(bindings)
    assert routed_local.transport_kind is RedLivingDexSetupTransportKind.LOCAL


def test_runner_seals_and_claims_before_each_setup_port_call(tmp_path: Path) -> None:
    store = _store(tmp_path)
    plan = _plan()
    meter = _Meter()
    executor = _Executor(store, meter)

    result = run_red_living_dex_setup_campaign(
        store,
        plan,
        executor=executor,
        budget_meter=meter,
    )

    assert len(executor.calls) == 15
    assert len(result.receipts) == 15
    assert all(
        item.disposition is RedLivingDexSetupDisposition.EXECUTED_COMPLETE
        for item in result.receipts
    )
    public = result.public_dict()
    assert public["all_slots_terminal"] is True
    assert public["terminal_status_counts"] == {
        "complete": 15,
        "failed": 0,
        "interrupted": 0,
    }
    assert public["terminal_accounting_known"] == 15
    assert public["setup_controller_actions_known_total"] == 30
    assert public["setup_emulator_frames_known_total"] == 150
    assert public["inventory_qualification_available"] is True
    assert public["behavior_draws"] == 0
    assert public["learner_controller_actions"] == 0
    assert public["learner_labels_emitted"] == 0
    assert public["learner_outcomes_observed"] == 0
    assert public["model_predictions"] == 0
    assert public["model_fits"] == 0
    assert public["teacher_queries"] == 0

    inventory = result.qualified_inventory()
    assert inventory.public_dict()["all_slots_reconciled"] is True
    assert inventory.public_dict()["train_complete_count"] == 10
    assert inventory.public_dict()["development_complete_count"] == 5


def test_complete_slots_reload_without_reopening_the_setup_port(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    plan = _plan()
    meter = _Meter()
    first = _Executor(store, meter)
    run_red_living_dex_setup_campaign(
        store,
        plan,
        executor=first,
        budget_meter=meter,
    )
    second = _Executor(store, meter)

    recovered = run_red_living_dex_setup_campaign(
        store,
        plan,
        executor=second,
        budget_meter=meter,
    )

    assert second.calls == []
    assert all(
        item.disposition is RedLivingDexSetupDisposition.RECOVERED_COMPLETE
        for item in recovered.receipts
    )
    assert recovered.inventory_qualification_available is True


def test_controlled_failure_is_terminal_and_later_slots_continue(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    plan = _plan()
    meter = _Meter()
    first = _Executor(store, meter, fail_at=0)

    result = run_red_living_dex_setup_campaign(
        store,
        plan,
        executor=first,
        budget_meter=meter,
    )

    assert len(first.calls) == 15
    assert result.receipts[0].terminal.status is LivingDexCaptureSetupStatus.FAILED
    assert result.receipts[0].terminal.reason_code == "fixture_setup_failed"
    assert result.receipts[0].terminal.accounting_known is True
    assert result.receipts[0].disposition is (RedLivingDexSetupDisposition.EXECUTED_FAILED)
    assert result.inventory_qualification_available is True

    second = _Executor(store, meter)
    recovered = run_red_living_dex_setup_campaign(
        store,
        plan,
        executor=second,
        budget_meter=meter,
    )
    assert second.calls == []
    assert recovered.receipts[0].disposition is (RedLivingDexSetupDisposition.RECOVERED_FAILED)


def test_orphan_claim_is_interrupted_once_and_never_retried(tmp_path: Path) -> None:
    store = _store(tmp_path)
    plan = _plan()
    first_binding = plan.bindings[0]
    episode_id = f"redldx-setup-00-{first_binding.binding_sha256[:32]}"
    store.begin_episode(episode_id)
    meter = _Meter()
    executor = _Executor(store, meter)

    result = run_red_living_dex_setup_campaign(
        store,
        plan,
        executor=executor,
        budget_meter=meter,
    )

    assert len(executor.calls) == 14
    assert result.receipts[0].terminal.status is (LivingDexCaptureSetupStatus.INTERRUPTED)
    assert result.receipts[0].terminal.accounting_known is False
    assert result.receipts[0].disposition is (RedLivingDexSetupDisposition.RECOVERED_INTERRUPTED)
    assert result.inventory_qualification_available is False

    second = _Executor(store, meter)
    recovered = run_red_living_dex_setup_campaign(
        store,
        plan,
        executor=second,
        budget_meter=meter,
    )
    assert second.calls == []
    assert recovered.receipts[0].terminal.status is (LivingDexCaptureSetupStatus.INTERRUPTED)


def test_cross_joined_option_proof_fails_after_claim_and_cannot_retry(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    plan = _plan()
    meter = _Meter()
    invalid = _Executor(store, meter, invalid_at=0)

    with pytest.raises(
        RedLivingDexSetupCampaignError,
        match="failed after durable claim",
    ):
        run_red_living_dex_setup_campaign(
            store,
            plan,
            executor=invalid,
            budget_meter=meter,
        )

    assert len(invalid.calls) == 1
    resumed = _Executor(store, meter)
    result = run_red_living_dex_setup_campaign(
        store,
        plan,
        executor=resumed,
        budget_meter=meter,
    )
    assert len(resumed.calls) == 14
    assert result.receipts[0].terminal.status is LivingDexCaptureSetupStatus.FAILED
    assert result.receipts[0].terminal.reason_code == "setup_execution_failed"
    assert result.receipts[0].terminal.accounting_known is True


def test_over_budget_execution_is_retained_as_a_known_nonretryable_failure(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    plan = _plan()
    meter = _Meter()

    class OverBudget:
        def execute_setup(
            self,
            binding: RedLivingDexSetupSlotBinding,
        ) -> RedLivingDexSetupExecution:
            meter.spend(actions=100_001, frames=1)
            return _execution(binding, actions=100_001, frames=1)

    with pytest.raises(
        RedLivingDexSetupCampaignError,
        match="failed after durable claim",
    ):
        run_red_living_dex_setup_campaign(
            store,
            plan,
            executor=OverBudget(),
            budget_meter=meter,
        )

    resumed = _Executor(store, meter)
    result = run_red_living_dex_setup_campaign(
        store,
        plan,
        executor=resumed,
        budget_meter=meter,
    )
    first = result.receipts[0]
    assert len(resumed.calls) == 14
    assert first.terminal.status is LivingDexCaptureSetupStatus.FAILED
    assert first.terminal.setup_controller_actions == 100_001
    assert first.terminal.setup_emulator_frames == 1
    assert first.terminal.reason_code == "setup_execution_failed"
    assert result.inventory_qualification_available is False


def test_recovered_complete_artifact_must_contain_the_exact_durable_claim(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    plan = _plan()
    binding = plan.bindings[0]
    episode_id = f"redldx-setup-00-{binding.binding_sha256[:32]}"
    with store.begin_episode(episode_id) as writer:
        writer.append("claim", {"schema": "wrong-claim-v1"}, durable=True)
        writer.append("execution", _execution(binding).private_dict(), durable=True)
        writer.complete()
    meter = _Meter()
    executor = _Executor(store, meter)

    with pytest.raises(
        RedLivingDexSetupCampaignError,
        match="exact durable claim",
    ):
        run_red_living_dex_setup_campaign(
            store,
            plan,
            executor=executor,
            budget_meter=meter,
        )

    assert executor.calls == []


def test_a_different_private_plan_cannot_replace_the_sealed_campaign(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    plan = _plan()
    meter = _Meter()
    run_red_living_dex_setup_campaign(
        store,
        plan,
        executor=_Executor(store, meter),
        budget_meter=meter,
    )
    first = plan.bindings[0]
    changed_option = replace(
        first.option_bindings[0],
        expected_provider_offer_sha256=_digest("changed-provider-offer"),
    )
    changed_first = replace(
        first,
        option_bindings=(changed_option, *first.option_bindings[1:]),
    )
    changed_bindings = (changed_first, *plan.bindings[1:])
    changed = build_red_living_dex_setup_binding_plan(changed_bindings)
    blocked = _Executor(store, meter)

    with pytest.raises(
        RedLivingDexSetupCampaignError,
        match="different content",
    ):
        run_red_living_dex_setup_campaign(
            store,
            changed,
            executor=blocked,
            budget_meter=meter,
        )

    assert blocked.calls == []


def test_public_run_projection_contains_no_private_binding_identity(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    plan = _plan()
    meter = _Meter()
    result = run_red_living_dex_setup_campaign(
        store,
        plan,
        executor=_Executor(store, meter),
        budget_meter=meter,
    )
    encoded = json.dumps(result.public_dict(), sort_keys=True)

    for binding in plan.bindings:
        assert binding.binding_sha256 not in encoded
        assert binding.state_sha256 not in encoded
        assert binding.menu_sha256 not in encoded
        for option in binding.option_bindings:
            assert option.binding_sha256 not in encoded
            assert option.expected_provider_offer_sha256 not in encoded
            if option.route_plan_sha256 is not None:
                assert option.route_plan_sha256 not in encoded
    assert "redldx-setup-" not in encoded
    assert '"private_identity_fields": 0' in encoded
    assert '"private_path_fields": 0' in encoded


def test_canonical_red_plan_is_the_only_supported_prospective_schedule() -> None:
    prospective = build_red_living_dex_prospective_capture_plan()
    changed_slot = replace(
        prospective.slots[0],
        partition=LivingDexCapturePartition.DEVELOPMENT,
    )

    with pytest.raises(ValueError):
        build_red_living_dex_setup_binding_plan(
            _plan().bindings,
            prospective_plan=replace(
                prospective,
                slots=(changed_slot, *prospective.slots[1:]),
            ),
        )
