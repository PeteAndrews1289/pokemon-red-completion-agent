from __future__ import annotations

import pytest
from test_red_living_dex_targeted_update_capacity import _repeatable_capabilities

from pokemon_red_completion.red_living_dex_causal_inventory import (
    freeze_red_living_dex_targeted_schedule,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupEffectMeter,
)
from pokemon_red_completion.red_living_dex_targeted_train_campaign import (
    RedLivingDexTargetedTrainCampaignError,
    run_red_living_dex_targeted_train_campaign,
)
from pokemon_red_completion.red_living_dex_targeted_train_runner import (
    RedLivingDexTargetedSetupStatus,
    RedLivingDexTargetedTrainReceipt,
)


def _binding():  # type: ignore[no-untyped-def]
    return freeze_red_living_dex_targeted_schedule(
        _repeatable_capabilities(),
        maximum_train_replays_per_context=5,
    )


def test_campaign_runs_only_train_slots_in_frozen_order_and_reports_progress() -> None:
    binding = _binding()
    meter = RedLivingDexSetupEffectMeter()
    executed: list[int] = []
    progress = []

    def execute(assignment):  # type: ignore[no-untyped-def]
        assert assignment.slot.partition == "train"
        executed.append(assignment.ordinal)
        return RedLivingDexTargetedTrainReceipt(
            assignment,
            RedLivingDexTargetedSetupStatus.INTERRUPTED,
            None,
        )

    receipts = run_red_living_dex_targeted_train_campaign(
        binding,
        source_commit="a" * 40,
        execute=execute,
        effects=meter.checkpoint,
        publish_progress=progress.append,
    )
    expected = [
        ordinal
        for ordinal, slot in enumerate(binding.schedule.slots)
        if slot.partition == "train"
    ]
    assert executed == expected
    assert len(receipts) == 10
    assert progress[0].status == "waiting"
    assert progress[-1].status == "passed"
    assert len(progress[-1].receipts) == 10
    assert all(
        item.active_assignment is None
        for item in progress
        if item.status == "passed"
    )


def test_campaign_stops_and_projects_the_exact_active_slot_on_exception() -> None:
    binding = _binding()
    progress = []

    def fail(assignment):  # type: ignore[no-untyped-def]
        raise RuntimeError(f"failed {assignment.ordinal}")

    with pytest.raises(RuntimeError, match="failed 0"):
        run_red_living_dex_targeted_train_campaign(
            binding,
            source_commit="a" * 40,
            execute=fail,
            effects=RedLivingDexSetupEffectMeter().checkpoint,
            publish_progress=progress.append,
        )
    assert progress[-1].status == "failed"
    assert progress[-1].active_assignment is not None
    assert progress[-1].active_assignment.ordinal == 0
    assert not progress[-1].receipts


def test_campaign_rejects_a_receipt_from_another_assignment() -> None:
    binding = _binding()

    def wrong(assignment):  # type: ignore[no-untyped-def]
        other = type(assignment)(binding, 1, "a" * 40)
        return RedLivingDexTargetedTrainReceipt(
            other,
            RedLivingDexTargetedSetupStatus.INTERRUPTED,
            None,
        )

    with pytest.raises(
        RedLivingDexTargetedTrainCampaignError,
        match="another assignment",
    ):
        run_red_living_dex_targeted_train_campaign(
            binding,
            source_commit="a" * 40,
            execute=wrong,
            effects=RedLivingDexSetupEffectMeter().checkpoint,
            publish_progress=lambda progress: None,
        )
