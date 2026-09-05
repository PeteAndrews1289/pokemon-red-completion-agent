"""Ordered, train-only coordinator for the targeted Red outcome schedule."""

from __future__ import annotations

import re
from collections.abc import Callable

from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexTargetedScheduleBinding,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupProtectedEffectCheckpoint,
)
from pokemon_red_completion.red_living_dex_targeted_train_dashboard import (
    RedLivingDexTargetedTrainDashboardProgress,
)
from pokemon_red_completion.red_living_dex_targeted_train_runner import (
    RedLivingDexTargetedTrainAssignment,
    RedLivingDexTargetedTrainReceipt,
)

_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class RedLivingDexTargetedTrainCampaignError(RuntimeError):
    """The train-only coordinator crossed its frozen schedule boundary."""


RedLivingDexTargetedTrainExecutor = Callable[
    [RedLivingDexTargetedTrainAssignment],
    RedLivingDexTargetedTrainReceipt,
]
RedLivingDexTargetedTrainProgressSink = Callable[
    [RedLivingDexTargetedTrainDashboardProgress],
    None,
]
RedLivingDexTargetedTrainEffects = Callable[
    [],
    RedLivingDexSetupProtectedEffectCheckpoint,
]


def run_red_living_dex_targeted_train_campaign(
    binding: RedLivingDexTargetedScheduleBinding,
    *,
    source_commit: str,
    execute: RedLivingDexTargetedTrainExecutor,
    effects: RedLivingDexTargetedTrainEffects,
    publish_progress: RedLivingDexTargetedTrainProgressSink,
) -> tuple[RedLivingDexTargetedTrainReceipt, ...]:
    """Run or recover every train slot in frozen order, never development.

    The per-slot executor owns durable recovery and no-reroll semantics.  This
    coordinator owns only ordering and truthful progress.  An unexpected
    exception stops the campaign at that slot instead of silently advancing.
    """

    if not isinstance(binding, RedLivingDexTargetedScheduleBinding):
        raise TypeError("targeted train campaign needs its binding")
    binding.__post_init__()
    if not isinstance(source_commit, str) or _GIT_COMMIT.fullmatch(source_commit) is None:
        raise RedLivingDexTargetedTrainCampaignError(
            "targeted train campaign source commit differs"
        )
    if not callable(execute) or not callable(effects) or not callable(publish_progress):
        raise TypeError("targeted train campaign callbacks differ")

    train_ordinals = tuple(
        ordinal
        for ordinal, slot in enumerate(binding.schedule.slots)
        if slot.partition == "train"
    )
    receipts: list[RedLivingDexTargetedTrainReceipt] = []
    publish_progress(
        RedLivingDexTargetedTrainDashboardProgress(
            status="waiting",
            receipts=(),
            effects=_effects(effects),
        )
    )
    for ordinal in train_ordinals:
        assignment = RedLivingDexTargetedTrainAssignment(
            binding,
            ordinal,
            source_commit,
        )
        publish_progress(
            RedLivingDexTargetedTrainDashboardProgress(
                status="running",
                active_assignment=assignment,
                receipts=tuple(receipts),
                effects=_effects(effects),
            )
        )
        try:
            receipt = execute(assignment)
        except BaseException:
            publish_progress(
                RedLivingDexTargetedTrainDashboardProgress(
                    status="failed",
                    active_assignment=assignment,
                    receipts=tuple(receipts),
                    effects=_effects(effects),
                )
            )
            raise
        if (
            not isinstance(receipt, RedLivingDexTargetedTrainReceipt)
            or receipt.assignment != assignment
        ):
            raise RedLivingDexTargetedTrainCampaignError(
                "targeted train executor returned another assignment"
            )
        receipts.append(receipt)
        publish_progress(
            RedLivingDexTargetedTrainDashboardProgress(
                status="running",
                receipts=tuple(receipts),
                effects=_effects(effects),
            )
        )
    result = tuple(receipts)
    publish_progress(
        RedLivingDexTargetedTrainDashboardProgress(
            status="passed",
            receipts=result,
            effects=_effects(effects),
        )
    )
    return result


def _effects(
    callback: RedLivingDexTargetedTrainEffects,
) -> RedLivingDexSetupProtectedEffectCheckpoint:
    value = callback()
    if not isinstance(value, RedLivingDexSetupProtectedEffectCheckpoint):
        raise TypeError("targeted train campaign effect callback differs")
    value.__post_init__()
    return value


__all__ = [
    "RedLivingDexTargetedTrainCampaignError",
    "RedLivingDexTargetedTrainEffects",
    "RedLivingDexTargetedTrainExecutor",
    "RedLivingDexTargetedTrainProgressSink",
    "run_red_living_dex_targeted_train_campaign",
]
