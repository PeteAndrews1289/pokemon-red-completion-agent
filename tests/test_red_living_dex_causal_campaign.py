from __future__ import annotations

import copy
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

import pytest
from test_red_living_dex_setup_recipe import (
    _ArmFactory,
    _identity,
    _recipes,
    _root,
    _store,
)

from pokemon_red_completion.claim_first_admission import ClaimFirstExecutionIdentity
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCaptureSetupStatus,
)
from pokemon_red_completion.living_dex_causal_journal import (
    LivingDexCausalDisposition,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_causal_campaign import (
    RED_LIVING_DEX_CAUSAL_CAMPAIGN_RUNNER_SHA256,
    RedLivingDexCausalCampaignError,
    RedLivingDexCausalExecutionIdentity,
    freeze_red_living_dex_causal_campaign,
    load_red_living_dex_causal_campaign,
    run_red_living_dex_causal_campaign,
)
from pokemon_red_completion.red_living_dex_claim_first_campaign import (
    RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
    RedLivingDexResolvedSetupSlot,
)
from pokemon_red_completion.red_living_dex_setup_admission import (
    authenticate_frozen_red_living_dex_setup_slot,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexSetupEffectMeter,
    build_red_living_dex_setup_recipe_plan,
)


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _registry(tmp_path: Path) -> Path:
    path = tmp_path / "claims"
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def _fixture(tmp_path: Path, ordinal: int = 0):  # type: ignore[no-untyped-def]
    recipe_plan = build_red_living_dex_setup_recipe_plan(
        _recipes(),
        execution_identity=_identity(),
    )
    root = _root(ordinal)
    frozen = authenticate_frozen_red_living_dex_setup_slot(
        recipe_plan.private_dict(),
        expected_plan_sha256=recipe_plan.plan_sha256,
        ordinal=ordinal,
        root=root,
    )
    outer = ClaimFirstExecutionIdentity(
        source_commit="c" * 40,
        source_bundle_sha256=_sha("current-source"),
        exact_ci_run=12345,
        exact_ci_attempt=1,
        producer_execution_identity_sha256=(
            recipe_plan.execution_identity.identity_sha256
        ),
        producer_plan_sha256=recipe_plan.plan_sha256,
        producer_private_plan_sha256=_sha("producer-private-plan"),
        producer_manifest_sha256=_sha("producer-manifest"),
        slot_sha256=recipe_plan.recipes[ordinal].slot_sha256,
        recipe_sha256=recipe_plan.recipes[ordinal].recipe_sha256,
        logical_root_sha256=root.root_consumption_sha256,
        physical_root_sha256=root.physical_root_sha256,
        title_adapter_sha256=_sha("title-adapter"),
        runtime_factory_sha256=_sha("runtime-factory"),
        runner_sha256=RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
    )
    store = _store(tmp_path)
    registry = _registry(tmp_path)
    return recipe_plan, root, frozen, outer, store, registry


def _execution_identity(
    plan: Any,
    frozen_outer: ClaimFirstExecutionIdentity,
    *,
    source_commit: str = "d" * 40,
) -> RedLivingDexCausalExecutionIdentity:
    current = ClaimFirstExecutionIdentity(
        source_commit=source_commit,
        source_bundle_sha256=_sha("later-current-source"),
        exact_ci_run=23456,
        exact_ci_attempt=1,
        producer_execution_identity_sha256=(
            frozen_outer.producer_execution_identity_sha256
        ),
        producer_plan_sha256=frozen_outer.producer_plan_sha256,
        producer_private_plan_sha256=(
            frozen_outer.producer_private_plan_sha256
        ),
        producer_manifest_sha256=frozen_outer.producer_manifest_sha256,
        slot_sha256=frozen_outer.slot_sha256,
        recipe_sha256=frozen_outer.recipe_sha256,
        logical_root_sha256=frozen_outer.logical_root_sha256,
        physical_root_sha256=frozen_outer.physical_root_sha256,
        title_adapter_sha256=frozen_outer.title_adapter_sha256,
        runtime_factory_sha256=frozen_outer.runtime_factory_sha256,
        runner_sha256=RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256,
    )
    return RedLivingDexCausalExecutionIdentity(
        current,
        plan.campaign_sha256,
        plan.causal_runner_sha256,
    )


class _Resolver:
    def __init__(
        self,
        recipe_plan: Any,
        outer: ClaimFirstExecutionIdentity,
        factory: _ArmFactory,
        *,
        second_call_identity_drift: str | None = None,
    ) -> None:
        self.recipe_plan = recipe_plan
        self.outer = outer
        self.factory = factory
        self.second_call_identity_drift = second_call_identity_drift
        self.calls = 0

    def __call__(
        self,
        frozen: Any,
        root: Any,
        pair_claim: Any,
        *,
        meter: RedLivingDexSetupEffectMeter,
    ) -> AbstractContextManager[RedLivingDexResolvedSetupSlot]:
        del root, pair_claim, meter
        self.calls += 1
        title_adapter_sha256 = self.outer.title_adapter_sha256
        runtime_factory_sha256 = self.outer.runtime_factory_sha256
        if self.calls == 2 and self.second_call_identity_drift == "title_adapter":
            title_adapter_sha256 = _sha("different-title-adapter")
        if self.calls == 2 and self.second_call_identity_drift == "runtime_factory":
            runtime_factory_sha256 = _sha("different-runtime-factory")
        resolved = RedLivingDexResolvedSetupSlot(
            self.recipe_plan.recipes[frozen.ordinal],
            self.recipe_plan.execution_identity,
            self.factory,
            title_adapter_sha256,
            runtime_factory_sha256,
        )

        class Scope(AbstractContextManager[RedLivingDexResolvedSetupSlot]):
            def __enter__(self) -> RedLivingDexResolvedSetupSlot:
                return resolved

            def __exit__(self, *_args: object) -> None:
                return None

        return Scope()


class _ForbiddenResolver:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *_args: object, **_kwargs: object) -> Any:
        self.calls += 1
        raise AssertionError("terminal recovery constructed a Red runtime")


def test_action_free_freeze_excludes_retired_root_and_round_trips(
    tmp_path: Path,
) -> None:
    _recipe_plan, root, frozen, outer, store, registry = _fixture(tmp_path)
    retired = _sha("consumed-v2-physical-root")

    plan = freeze_red_living_dex_causal_campaign(
        store,
        frozen=frozen,
        outer_execution_identity=outer,
        retired_physical_root_sha256s=(retired,),
        claim_registry=registry,
    )
    assert load_red_living_dex_causal_campaign(store) == plan
    assert plan.causal_runner_sha256 == RED_LIVING_DEX_CAUSAL_CAMPAIGN_RUNNER_SHA256
    assert plan.public_dict() == {
        "action_free_freeze": True,
        "causal_examples": 0,
        "controller_actions": 0,
        "emulator_frames": 0,
        "exact_menu_bound_before_behavior": True,
        "learner_labels": 0,
        "model_fits": 0,
        "model_predictions": 0,
        "partition": "train",
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "provider_executions": 0,
        "retired_root_exclusions": 1,
        "root_claims": 0,
        "schema": "pokemon.red.private-living-dex-causal-campaign-plan.v1",
        "selected_slots": 1,
        "teacher_queries": 0,
    }

    other_root = tmp_path / "other"
    other_root.mkdir()
    other_store = _store(other_root)
    with pytest.raises(RedLivingDexCausalCampaignError, match="retired physical root"):
        freeze_red_living_dex_causal_campaign(
            other_store,
            frozen=frozen,
            outer_execution_identity=outer,
            retired_physical_root_sha256s=(root.physical_root_sha256,),
            claim_registry=registry,
        )


def test_frozen_campaign_runs_setup_then_exactly_one_randomized_arm(
    tmp_path: Path,
) -> None:
    recipe_plan, root, frozen, outer, store, registry = _fixture(tmp_path)
    plan = freeze_red_living_dex_causal_campaign(
        store,
        frozen=frozen,
        outer_execution_identity=outer,
        retired_physical_root_sha256s=(_sha("consumed-v2-physical-root"),),
        claim_registry=registry,
    )
    meter = RedLivingDexSetupEffectMeter()
    factory = _ArmFactory(recipe_plan.execution_identity, meter)
    resolver = _Resolver(recipe_plan, outer, factory)
    execution_identity = _execution_identity(plan, outer)
    document = recipe_plan.private_dict()

    receipt = run_red_living_dex_causal_campaign(
        plan,
        execution_identity=execution_identity,
        store=store,
        plan_loader=lambda: copy.deepcopy(document),
        frozen=frozen,
        root=root,
        resolver=resolver,
        meter=meter,
        claim_registry=registry,
    )
    assert receipt.setup.terminal.status is LivingDexCaptureSetupStatus.COMPLETE
    assert receipt.causal is not None
    assert receipt.causal.disposition is LivingDexCausalDisposition.EXECUTED_SETTLED
    assert receipt.causal.example is not None
    assert receipt.causal.example.partition == "train"
    assert receipt.public_dict()["causal_train_example_recorded"] is True
    assert receipt.public_dict()["setup_proof_runtimes_constructed"] == (
        receipt.setup.capture.origin_restore_count
    )
    assert receipt.public_dict()["setup_provider_outcomes"] == 0
    assert receipt.public_dict()["causal_selected_runtime_constructions"] == (
        receipt.causal.construction_attempts
    )
    assert receipt.public_dict()["causal_unselected_runtime_constructions"] == 0
    assert receipt.plan.causal_source_commit == "c" * 40
    assert receipt.causal.scenario.identity.source_commit == "d" * 40
    assert receipt.causal.scenario.identity.runner_sha256 == (
        execution_identity.causal_runner_sha256
    )
    assert resolver.calls == 2
    assert meter.provider_executions == 1
    assert receipt.setup.capture is not None
    setup_proof_arms = receipt.setup.capture.origin_restore_count
    assert len(factory.arms) == setup_proof_arms + 1
    assert factory.arms[-1].purpose == "candidate"
    assert factory.arms[-1].ordinal == (
        receipt.causal.example.selected_candidate_index
    )

    forbidden = _ForbiddenResolver()
    recovered = run_red_living_dex_causal_campaign(
        plan,
        execution_identity=execution_identity,
        store=store,
        plan_loader=lambda: copy.deepcopy(document),
        frozen=frozen,
        root=root,
        resolver=forbidden,
        meter=RedLivingDexSetupEffectMeter(),
        claim_registry=registry,
    )
    assert recovered.causal is not None
    assert recovered.causal.example == receipt.causal.example
    assert forbidden.calls == 0
    assert recovered.public_dict()["setup_proof_runtimes_constructed"] == (
        receipt.setup.capture.origin_restore_count
    )
    assert recovered.public_dict()["causal_selected_runtime_constructions"] == (
        receipt.causal.construction_attempts
    )
    assert recovered.public_dict()["causal_unselected_runtime_constructions"] == 0


def test_freeze_rejects_non_train_recipe_before_publication(tmp_path: Path) -> None:
    _recipe_plan, _root_value, frozen, outer, store, registry = _fixture(
        tmp_path,
        ordinal=14,
    )
    with pytest.raises(RedLivingDexCausalCampaignError, match="non-train"):
        freeze_red_living_dex_causal_campaign(
            store,
            frozen=frozen,
            outer_execution_identity=outer,
            retired_physical_root_sha256s=(_sha("retired"),),
            claim_registry=registry,
        )


@pytest.mark.parametrize(
    "drift",
    ["title_adapter", "runtime_factory"],
)
def test_post_selection_runtime_identity_drift_is_target_free(
    tmp_path: Path,
    drift: str,
) -> None:
    recipe_plan, root, frozen, outer, store, registry = _fixture(tmp_path)
    plan = freeze_red_living_dex_causal_campaign(
        store,
        frozen=frozen,
        outer_execution_identity=outer,
        retired_physical_root_sha256s=(_sha("consumed-v2-physical-root"),),
        claim_registry=registry,
    )
    meter = RedLivingDexSetupEffectMeter()
    factory = _ArmFactory(recipe_plan.execution_identity, meter)
    resolver = _Resolver(
        recipe_plan,
        outer,
        factory,
        second_call_identity_drift=drift,
    )
    execution_identity = _execution_identity(plan, outer)

    receipt = run_red_living_dex_causal_campaign(
        plan,
        execution_identity=execution_identity,
        store=store,
        plan_loader=lambda: copy.deepcopy(recipe_plan.private_dict()),
        frozen=frozen,
        root=root,
        resolver=resolver,
        meter=meter,
        claim_registry=registry,
    )

    assert receipt.setup.terminal.status is LivingDexCaptureSetupStatus.COMPLETE
    assert receipt.setup.capture is not None
    assert receipt.causal is not None
    assert receipt.causal.disposition is LivingDexCausalDisposition.PREINPUT_RETRYABLE
    assert receipt.causal.example is None
    assert receipt.causal.retry_allowed
    assert resolver.calls == 2
    assert len(factory.arms) == receipt.setup.capture.origin_restore_count
    assert meter.provider_executions == 0


def test_runner_rejects_a_plan_from_another_private_store_before_claim(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "first"
    second_path = tmp_path / "second"
    first_path.mkdir()
    second_path.mkdir()
    _first_recipes, _first_root, first_frozen, first_outer, first_store, first_registry = (
        _fixture(first_path)
    )
    first_plan = freeze_red_living_dex_causal_campaign(
        first_store,
        frozen=first_frozen,
        outer_execution_identity=first_outer,
        retired_physical_root_sha256s=(_sha("first-retired-root"),),
        claim_registry=first_registry,
    )
    recipe_plan, root, frozen, outer, second_store, second_registry = _fixture(
        second_path,
        ordinal=1,
    )
    second_plan = freeze_red_living_dex_causal_campaign(
        second_store,
        frozen=frozen,
        outer_execution_identity=outer,
        retired_physical_root_sha256s=(_sha("second-retired-root"),),
        claim_registry=second_registry,
    )
    meter = RedLivingDexSetupEffectMeter()
    resolver = _Resolver(
        recipe_plan,
        outer,
        _ArmFactory(recipe_plan.execution_identity, meter),
    )

    with pytest.raises(RedLivingDexCausalCampaignError, match="immutable stored plan"):
        run_red_living_dex_causal_campaign(
            second_plan,
            execution_identity=_execution_identity(second_plan, outer),
            store=first_store,
            plan_loader=lambda: copy.deepcopy(recipe_plan.private_dict()),
            frozen=frozen,
            root=root,
            resolver=resolver,
            meter=meter,
            claim_registry=second_registry,
        )
    assert load_red_living_dex_causal_campaign(first_store) == first_plan
    assert resolver.calls == 0
    assert meter.root_claims == 0


def test_current_execution_identity_substitution_fails_before_claim_or_behavior(
    tmp_path: Path,
) -> None:
    recipe_plan, root, frozen, outer, store, registry = _fixture(tmp_path)
    plan = freeze_red_living_dex_causal_campaign(
        store,
        frozen=frozen,
        outer_execution_identity=outer,
        retired_physical_root_sha256s=(_sha("retired"),),
        claim_registry=registry,
    )
    meter = RedLivingDexSetupEffectMeter()
    resolver = _Resolver(
        recipe_plan,
        outer,
        _ArmFactory(recipe_plan.execution_identity, meter),
    )
    substituted = _execution_identity(plan, outer)
    object.__setattr__(substituted, "campaign_sha256", _sha("other-campaign"))

    with pytest.raises(
        RedLivingDexCausalCampaignError,
        match="current execution identity differs",
    ):
        run_red_living_dex_causal_campaign(
            plan,
            execution_identity=substituted,
            store=store,
            plan_loader=lambda: copy.deepcopy(recipe_plan.private_dict()),
            frozen=frozen,
            root=root,
            resolver=resolver,
            meter=meter,
            claim_registry=registry,
        )

    assert resolver.calls == 0
    assert meter.root_claims == 0
    assert tuple(registry.glob("claim-pair-v1-*.json")) == ()
