from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_red_living_dex_causal_campaign import _registry
from test_red_living_dex_clustered_schedule_plan import _bindings
from test_red_living_dex_provider_plan import _root as _provider_root
from test_red_living_dex_setup_recipe import (
    _ArmFactory,
    _identity,
    _recipes,
    _store,
)
from test_red_living_dex_setup_recipe import _root as _setup_root

from pokemon_red_completion.claim_first_admission import ClaimFirstExecutionIdentity
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCapturePartition,
    LivingDexCaptureSetupStatus,
)
from pokemon_red_completion.living_dex_causal_journal import (
    LivingDexCausalDisposition,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_capture_plan import (
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexCausalRootCapability,
    schedule_red_living_dex_clustered_integration,
)
from pokemon_red_completion.red_living_dex_causal_invocation import (
    bind_red_living_dex_authenticated_consumer,
)
from pokemon_red_completion.red_living_dex_claim_first_campaign import (
    RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
    RedLivingDexResolvedSetupSlot,
)
from pokemon_red_completion.red_living_dex_claim_first_invocation import (
    RedLivingDexCurrentConsumerBinding,
)
from pokemon_red_completion.red_living_dex_clustered_schedule_plan import (
    RedLivingDexClusteredFrozenScenario,
    RedLivingDexClusteredPrivatePlan,
)
from pokemon_red_completion.red_living_dex_clustered_train_runner import (
    RED_LIVING_DEX_CLUSTERED_TRAIN_RUNNER_SHA256,
    RedLivingDexClusteredTrainPlanBinding,
    RedLivingDexClusteredTrainRunnerError,
    authenticate_red_living_dex_clustered_train_selection,
    preflight_red_living_dex_clustered_train_assignment,
    run_red_living_dex_clustered_train_assignment,
)
from pokemon_red_completion.red_living_dex_runtime_contract import (
    RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
    RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexSetupEffectMeter,
)


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _clustered_fixture() -> tuple[
    RedLivingDexClusteredPrivatePlan,
    RedLivingDexClusteredTrainPlanBinding,
]:
    identity = _identity()
    slots = build_red_living_dex_prospective_capture_plan().slots
    recipes = _recipes()
    capabilities: list[RedLivingDexCausalRootCapability] = []
    for ordinal, (slot, recipe) in enumerate(zip(slots, recipes, strict=True)):
        root = _setup_root(ordinal)
        partition = (
            "train"
            if slot.partition is LivingDexCapturePartition.TRAIN
            else "development"
        )
        observation = replace(
            _provider_root(ordinal),
            root=root,
            observed_state_sha256=root.state_sha256,
            independence_lineage_sha256=_sha(("lineage", ordinal)),
            cluster_partition=partition,
        )
        capabilities.append(
            RedLivingDexCausalRootCapability(
                root=observation,
                template_ordinal=ordinal,
                slot=slot,
                recipe=recipe,
            )
        )
    schedule = schedule_red_living_dex_clustered_integration(tuple(capabilities))
    by_scenario = {
        (
            item.root.root.physical_root_sha256,
            item.slot.slot_sha256,
        ): item
        for item in capabilities
    }
    frozen = tuple(
        RedLivingDexClusteredFrozenScenario(
            assignment=assignment,
            capability=by_scenario[
                (
                    assignment.capability.physical_root_sha256,
                    assignment.capability.template_sha256,
                )
            ],
            context_identity_sha256=_sha(("context", assignment.ordinal)),
        )
        for assignment in schedule.assignments
    )
    bindings = replace(
        _bindings(),
        source_commit=identity.source_commit,
        source_bundle_sha256=identity.source_bundle_sha256,
        rom_sha256=identity.rom_sha256,
        route_registry_sha256=identity.route_registry_sha256,
        runtime_identity_sha256=_sha("runtime-identity"),
    )
    plan = RedLivingDexClusteredPrivatePlan(
        bindings=bindings,
        schedule=schedule,
        assignments=frozen,
    )
    binding = RedLivingDexClusteredTrainPlanBinding(
        private_plan_sha256=plan.private_plan_sha256,
        plan_manifest_sha256=_sha("manifest"),
        plan_record_sha256=_sha("record"),
        schedule_sha256=plan.schedule.schedule_sha256,
        policy_sha256=plan.schedule.policy.policy_sha256,
    )
    return plan, binding


def _outer(selection: Any, identity: Any, binding: Any) -> ClaimFirstExecutionIdentity:
    return ClaimFirstExecutionIdentity(
        source_commit="d" * 40,
        source_bundle_sha256=_sha("current-source"),
        exact_ci_run=12345,
        exact_ci_attempt=1,
        producer_execution_identity_sha256=identity.identity_sha256,
        producer_plan_sha256=selection.private_plan_sha256,
        producer_private_plan_sha256=selection.private_plan_sha256,
        producer_manifest_sha256=binding.plan_manifest_sha256,
        slot_sha256=selection.slot_sha256,
        recipe_sha256=selection.recipe_sha256,
        logical_root_sha256=selection.logical_root_sha256,
        physical_root_sha256=selection.physical_root_sha256,
        title_adapter_sha256=RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
        runtime_factory_sha256=RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
        runner_sha256=RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
    )


class _Resolver:
    def __init__(self, recipe: Any, identity: Any, factory: Any) -> None:
        self.recipe = recipe
        self.identity = identity
        self.factory = factory
        self.calls = 0

    def __call__(self, *_args: object, **_kwargs: object) -> Any:
        self.calls += 1
        resolved = RedLivingDexResolvedSetupSlot(
            self.recipe,
            self.identity,
            self.factory,
            RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
            RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
        )

        class _Scope(AbstractContextManager[RedLivingDexResolvedSetupSlot]):
            def __enter__(self) -> RedLivingDexResolvedSetupSlot:
                return resolved

            def __exit__(self, *_values: object) -> None:
                return None

        return _Scope()


class _ForbiddenResolver:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *_args: object, **_kwargs: object) -> Any:
        self.calls += 1
        raise AssertionError("terminal recovery constructed a Red runtime")


def test_selection_rejects_every_development_ordinal_before_projection() -> None:
    plan, binding = _clustered_fixture()

    for ordinal in range(8, 12):
        with pytest.raises(
            RedLivingDexClusteredTrainRunnerError,
            match="structurally inaccessible",
        ):
            authenticate_red_living_dex_clustered_train_selection(
                plan.private_dict(),
                ordinal,
                binding=binding,
            )


def test_selection_binds_distinct_schedule_and_template_ordinals() -> None:
    plan, binding = _clustered_fixture()
    selection = authenticate_red_living_dex_clustered_train_selection(
        plan.private_dict(),
        0,
        binding=binding,
    )
    frozen = plan.assignments[0]

    assert selection.ordinal == frozen.assignment.ordinal
    assert selection.template_ordinal == frozen.capability.template_ordinal
    assert selection.upstream_lineage_sha256 == (
        frozen.assignment.capability.lineage_sha256
    )
    assert selection.public_dict()["development_accessible"] is False
    assert selection.context_identity_sha256 not in str(selection.public_dict())


def test_train_runner_records_only_selected_arm_under_upstream_lineage(
    tmp_path: Path,
) -> None:
    plan, binding = _clustered_fixture()
    selection = authenticate_red_living_dex_clustered_train_selection(
        plan.private_dict(),
        2,
        binding=binding,
    )
    capability = plan.assignments[2].capability
    root = capability.root.root
    identity = _identity()
    meter = RedLivingDexSetupEffectMeter()
    factory = _ArmFactory(identity, meter)
    resolver = _Resolver(capability.recipe, identity, factory)
    store = _store(tmp_path)
    registry = _registry(tmp_path)

    receipt = run_red_living_dex_clustered_train_assignment(
        selection=selection,
        store=store,
        plan_loader=lambda: plan.private_dict(),
        root=root,
        producer_execution_identity=identity,
        outer_execution_identity=_outer(selection, identity, binding),
        resolver=resolver,
        meter=meter,
        claim_registry=registry,
    )

    assert receipt.causal is not None
    assert receipt.causal.disposition is LivingDexCausalDisposition.EXECUTED_SETTLED
    assert receipt.causal.example is not None
    assert receipt.causal.example.partition == "train"
    assert receipt.causal.scenario.identity.lineage_sha256 == (
        selection.upstream_lineage_sha256
    )
    assert receipt.causal.scenario.identity.runner_sha256 == (
        RED_LIVING_DEX_CLUSTERED_TRAIN_RUNNER_SHA256
    )
    assert receipt.public_dict()["counterfactual_targets"] == 0
    assert receipt.public_dict()["development_outcomes_opened"] == 0
    assert receipt.public_dict()["unselected_action_targets"] == 0
    assert resolver.calls == 2
    assert meter.provider_executions == 1

    forbidden = _ForbiddenResolver()
    recovered = run_red_living_dex_clustered_train_assignment(
        selection=selection,
        store=store,
        plan_loader=lambda: plan.private_dict(),
        root=root,
        producer_execution_identity=identity,
        outer_execution_identity=_outer(selection, identity, binding),
        resolver=forbidden,
        meter=RedLivingDexSetupEffectMeter(),
        claim_registry=registry,
    )
    assert recovered.causal is not None
    assert recovered.causal.example == receipt.causal.example
    assert forbidden.calls == 0


def test_behavior_selection_survives_crash_before_runtime_construction(
    tmp_path: Path,
) -> None:
    plan, binding = _clustered_fixture()
    selection = authenticate_red_living_dex_clustered_train_selection(
        plan.private_dict(),
        2,
        binding=binding,
    )
    capability = plan.assignments[2].capability
    root = capability.root.root
    identity = _identity()
    meter = RedLivingDexSetupEffectMeter()
    factory = _ArmFactory(identity, meter)
    resolver = _Resolver(capability.recipe, identity, factory)
    store = _store(tmp_path)
    registry = _registry(tmp_path)
    stages: list[str] = []

    def crash(stage: str) -> None:
        stages.append(stage)
        if stage == "after_behavior_selection":
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_red_living_dex_clustered_train_assignment(
            selection=selection,
            store=store,
            plan_loader=lambda: plan.private_dict(),
            root=root,
            producer_execution_identity=identity,
            outer_execution_identity=_outer(selection, identity, binding),
            resolver=resolver,
            meter=meter,
            claim_registry=registry,
            causal_failpoint=crash,
        )

    setup_arm_count = len(factory.arms)
    assert stages[-1] == "after_behavior_selection"
    assert meter.provider_executions == 0

    recovered = run_red_living_dex_clustered_train_assignment(
        selection=selection,
        store=store,
        plan_loader=lambda: plan.private_dict(),
        root=root,
        producer_execution_identity=identity,
        outer_execution_identity=_outer(selection, identity, binding),
        resolver=resolver,
        meter=meter,
        claim_registry=registry,
    )
    assert recovered.causal is not None
    assert recovered.causal.example is not None
    assert len(factory.arms) == setup_arm_count + 1
    assert factory.arms[-1].ordinal == (
        recovered.causal.example.selected_candidate_index
    )
    assert meter.provider_executions == 1


@pytest.mark.parametrize("cutpoint", ("after_pair_claim", "after_local_claim"))
def test_clustered_setup_claim_cutpoints_close_without_runtime_or_retry(
    tmp_path: Path,
    cutpoint: str,
) -> None:
    plan, binding = _clustered_fixture()
    selection = authenticate_red_living_dex_clustered_train_selection(
        plan.private_dict(),
        2,
        binding=binding,
    )
    root = plan.assignments[2].capability.root.root
    identity = _identity()
    store = _store(tmp_path)
    registry = _registry(tmp_path)
    meter = RedLivingDexSetupEffectMeter()

    def crash(stage: str, _frozen: object) -> None:
        if stage == cutpoint:
            raise RuntimeError("synthetic clustered setup power loss")

    with pytest.raises(RuntimeError, match="power loss"):
        run_red_living_dex_clustered_train_assignment(
            selection=selection,
            store=store,
            plan_loader=lambda: plan.private_dict(),
            root=root,
            producer_execution_identity=identity,
            outer_execution_identity=_outer(selection, identity, binding),
            resolver=_ForbiddenResolver(),
            meter=meter,
            claim_registry=registry,
            setup_failpoint=crash,
        )

    forbidden = _ForbiddenResolver()
    recovered = run_red_living_dex_clustered_train_assignment(
        selection=selection,
        store=store,
        plan_loader=lambda: plan.private_dict(),
        root=root,
        producer_execution_identity=identity,
        outer_execution_identity=_outer(selection, identity, binding),
        resolver=forbidden,
        meter=meter,
        claim_registry=registry,
    )
    assert recovered.setup.terminal.status is LivingDexCaptureSetupStatus.INTERRUPTED
    assert recovered.setup.terminal.retry_allowed is False
    assert recovered.causal is None
    assert forbidden.calls == 0
    assert meter.controller_actions == 0
    assert meter.emulator_frames == 0


def test_plan_or_outer_substitution_fails_before_claim(tmp_path: Path) -> None:
    plan, binding = _clustered_fixture()
    selection = authenticate_red_living_dex_clustered_train_selection(
        plan.private_dict(),
        0,
        binding=binding,
    )
    capability = plan.assignments[0].capability
    root = capability.root.root
    identity = _identity()
    meter = RedLivingDexSetupEffectMeter()
    resolver = _Resolver(
        capability.recipe,
        identity,
        _ArmFactory(identity, meter),
    )
    substituted = _outer(selection, identity, binding)
    object.__setattr__(substituted, "recipe_sha256", _sha("other-recipe"))
    registry = _registry(tmp_path)

    with pytest.raises(
        RedLivingDexClusteredTrainRunnerError,
        match="execution identity differs",
    ):
        run_red_living_dex_clustered_train_assignment(
            selection=selection,
            store=_store(tmp_path),
            plan_loader=lambda: plan.private_dict(),
            root=root,
            producer_execution_identity=identity,
            outer_execution_identity=substituted,
            resolver=resolver,
            meter=meter,
            claim_registry=registry,
        )
    assert tuple(registry.glob("claim-pair-v1-*.json")) == ()
    assert resolver.calls == 0
    assert meter.root_claims == 0


def test_preflight_is_rom_free_and_leaves_every_effect_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pokemon_red_completion.red_living_dex_clustered_train_runner as runner

    plan, binding = _clustered_fixture()
    selection = authenticate_red_living_dex_clustered_train_selection(
        plan.private_dict(),
        0,
        binding=binding,
    )
    root = plan.assignments[0].capability.root.root
    identity = _identity()
    current = RedLivingDexCurrentConsumerBinding(
        source_commit="d" * 40,
        source_bundle_sha256=_sha("current-source"),
        exact_ci_run=12345,
        exact_ci_attempt=1,
    )
    consumer = bind_red_living_dex_authenticated_consumer(
        current,
        bootstrap_identity=(
            current.source_commit,
            current.source_bundle_sha256,
            current.exact_ci_run,
            current.exact_ci_attempt,
        ),
    )
    store = _store(tmp_path)
    registry = _registry(tmp_path)
    meter = RedLivingDexSetupEffectMeter()
    roots_loaded = 0

    def load_root(selected: Any) -> Any:
        nonlocal roots_loaded
        roots_loaded += 1
        assert selected == selection
        return root

    monkeypatch.setattr(
        runner,
        "_reopen_clustered_train_plan",
        lambda *_args, **_kwargs: (selection, object(), plan.private_dict()),
    )
    monkeypatch.setattr(
        runner,
        "authenticate_red_living_dex_execution_runtime",
        lambda *_args, **_kwargs: SimpleNamespace(
            sha256=plan.bindings.runtime_identity_sha256
        ),
    )
    monkeypatch.setattr(
        runner,
        "compose_red_living_dex_setup_execution_identity",
        lambda **_kwargs: identity,
    )
    monkeypatch.setattr(
        runner,
        "fixed_account_claim_registry_root",
        lambda: registry,
    )
    monkeypatch.setattr(
        runner,
        "observe_claim_first_pair_availability",
        lambda path, logical, physical: (
            path == registry
            and logical == selection.logical_root_sha256
            and physical == selection.physical_root_sha256
        ),
    )

    receipt = preflight_red_living_dex_clustered_train_assignment(
        tmp_path,
        store,
        consumer=consumer,
        ordinal=0,
        root_loader=load_root,
        meter=meter,
        binding=binding,
    )

    assert roots_loaded == 1
    assert receipt.public_dict()["status"] == (
        "one_train_assignment_ready_before_claim_or_emulator"
    )
    assert receipt.public_dict()["development_outcomes_opened"] == 0
    assert receipt.public_dict()["root_claims"] == 0
    assert meter.checkpoint().root_claims == 0
    assert meter.checkpoint().controller_actions == 0
    assert meter.checkpoint().emulator_frames == 0
