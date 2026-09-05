from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

import pytest
from test_red_living_dex_causal_campaign import _registry
from test_red_living_dex_setup_recipe import _ArmFactory, _identity, _store
from test_red_living_dex_targeted_update_capacity import _repeatable_capabilities

from pokemon_red_completion.living_dex_causal_journal import (
    LivingDexCausalDisposition,
)
from pokemon_red_completion.red_living_dex_causal_inventory import (
    freeze_red_living_dex_targeted_schedule,
)
from pokemon_red_completion.red_living_dex_claim_first_campaign import (
    RedLivingDexResolvedSetupSlot,
)
from pokemon_red_completion.red_living_dex_production_runtime import (
    RedLivingDexProductionSetupResolver,
)
from pokemon_red_completion.red_living_dex_runtime_contract import (
    RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
    RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexSetupEffectMeter,
)
from pokemon_red_completion.red_living_dex_targeted_train_runner import (
    RED_LIVING_DEX_TARGETED_TRAIN_RUNNER_SHA256,
    RedLivingDexTargetedSetupStatus,
    RedLivingDexTargetedTrainAssignment,
    RedLivingDexTargetedTrainReceipt,
    RedLivingDexTargetedTrainRunnerError,
    run_red_living_dex_targeted_train_assignment,
)


def _binding():  # type: ignore[no-untyped-def]
    return freeze_red_living_dex_targeted_schedule(
        _repeatable_capabilities(),
        maximum_train_replays_per_context=5,
    )


def test_train_assignment_binds_focus_reset_and_shared_root_honestly() -> None:
    binding = _binding()
    assignment = RedLivingDexTargetedTrainAssignment(
        binding,
        0,
        "a" * 40,
    )

    assert assignment.slot.partition == "train"
    assert assignment.trial.reset_ordinal == assignment.slot.reset_ordinal
    assert (
        assignment.trial.reservation.physical_root_sha256
        == assignment.capability.root.root.physical_root_sha256
    )
    assert (
        assignment.trial.reservation.runner_sha256
        == RED_LIVING_DEX_TARGETED_TRAIN_RUNNER_SHA256
    )
    public = assignment.public_dict()
    assert public["shared_base_root_declared"] is True
    assert public["private_identity_fields"] == 0
    assert assignment.slot.lineage_sha256 not in str(public)


def test_train_runner_cannot_address_a_frozen_development_slot() -> None:
    binding = _binding()
    development_ordinal = next(
        index
        for index, slot in enumerate(binding.schedule.slots)
        if slot.partition == "development"
    )

    with pytest.raises(
        RedLivingDexTargetedTrainRunnerError,
        match="development slot",
    ):
        RedLivingDexTargetedTrainAssignment(
            binding,
            development_ordinal,
            "a" * 40,
        )


def test_complete_receipt_cannot_claim_success_without_a_causal_terminal() -> None:
    assignment = RedLivingDexTargetedTrainAssignment(
        _binding(),
        0,
        "a" * 40,
    )

    with pytest.raises(
        RedLivingDexTargetedTrainRunnerError,
        match="lacks its causal receipt",
    ):
        RedLivingDexTargetedTrainReceipt(
            assignment,
            RedLivingDexTargetedSetupStatus.COMPLETE,
            None,
        )


def test_runner_exposes_no_teacher_fit_or_development_execution_interface() -> None:
    source = Path(
        "src/pokemon_red_completion/red_living_dex_targeted_train_runner.py"
    ).read_text()

    for forbidden in (
        "fit_living_dex",
        "model.fit",
        "run_teacher",
        "teacher_policy",
        "run_development_assignment",
    ):
        assert forbidden not in source


class _SyntheticProductionResolver(RedLivingDexProductionSetupResolver):
    """Typed production seam backed by the existing deterministic test arms."""

    def __init__(self, recipe: Any, identity: Any, factory: Any) -> None:
        object.__setattr__(self, "rom_path", Path("/synthetic-red.gb"))
        object.__setattr__(self, "rom_bytes", b"synthetic")
        object.__setattr__(self, "producer_execution_identity", identity)
        object.__setattr__(self, "runtime_limits", None)
        object.__setattr__(self, "frame_observer", None)
        object.__setattr__(self, "recipe", recipe)
        object.__setattr__(self, "factory", factory)
        object.__setattr__(self, "calls", 0)

    def __post_init__(self) -> None:
        return None

    def __call__(self, *_args: object, **_kwargs: object) -> Any:
        object.__setattr__(self, "calls", self.calls + 1)  # type: ignore[attr-defined]
        resolved = RedLivingDexResolvedSetupSlot(
            self.recipe,  # type: ignore[attr-defined]
            self.producer_execution_identity,
            self.factory,  # type: ignore[attr-defined]
            RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
            RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
        )

        class _Scope(AbstractContextManager[RedLivingDexResolvedSetupSlot]):
            def __enter__(self) -> RedLivingDexResolvedSetupSlot:
                return resolved

            def __exit__(self, *_values: object) -> None:
                return None

        return _Scope()


def test_targeted_runner_executes_one_selected_arm_and_recovers_it(
    tmp_path: Path,
) -> None:
    binding = _binding()
    capability = binding.capabilities[0]
    identity = _identity()
    meter = RedLivingDexSetupEffectMeter()
    factory = _ArmFactory(identity, meter)
    resolver = _SyntheticProductionResolver(capability.recipe, identity, factory)
    store = _store(tmp_path)
    registry = _registry(tmp_path)
    assignment = RedLivingDexTargetedTrainAssignment(
        binding,
        0,
        identity.source_commit,
    )

    receipt = run_red_living_dex_targeted_train_assignment(
        assignment,
        store=store,
        claim_registry=registry,
        setup_execution_identity=identity,
        resolver=resolver,
        meter=meter,
    )

    assert receipt.setup_status is RedLivingDexTargetedSetupStatus.COMPLETE
    assert receipt.causal is not None
    assert receipt.causal.disposition is LivingDexCausalDisposition.EXECUTED_SETTLED
    assert receipt.causal.example is not None
    assert receipt.causal.example.partition == "train"
    assert receipt.causal.scenario.identity.repeatable_trial_claim_sha256 == (
        assignment.trial.trial_claim_sha256
    )
    assert receipt.causal.example.behavior_probabilities[
        receipt.causal.example.selected_candidate_index
    ] > 0.0
    assert resolver.calls == 2  # type: ignore[attr-defined]
    assert meter.provider_executions == 1

    recovered = run_red_living_dex_targeted_train_assignment(
        assignment,
        store=store,
        claim_registry=registry,
        setup_execution_identity=identity,
        resolver=resolver,
        meter=meter,
    )
    assert recovered.causal is not None
    assert recovered.causal.example == receipt.causal.example
    assert resolver.calls == 2  # type: ignore[attr-defined]
    assert meter.provider_executions == 1
