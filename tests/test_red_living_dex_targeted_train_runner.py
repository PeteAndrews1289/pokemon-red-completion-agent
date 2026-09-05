from __future__ import annotations

from pathlib import Path

import pytest
from test_red_living_dex_targeted_update_capacity import _repeatable_capabilities

from pokemon_red_completion.red_living_dex_causal_inventory import (
    freeze_red_living_dex_targeted_schedule,
)
from pokemon_red_completion.red_living_dex_targeted_train_runner import (
    RED_LIVING_DEX_TARGETED_TRAIN_RUNNER_SHA256,
    RedLivingDexTargetedSetupStatus,
    RedLivingDexTargetedTrainAssignment,
    RedLivingDexTargetedTrainReceipt,
    RedLivingDexTargetedTrainRunnerError,
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
