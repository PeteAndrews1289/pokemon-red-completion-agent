"""Path-free live projection for targeted Red causal data collection.

This view deliberately distinguishes outcome collection from model fitting.
It exposes campaign progress, reset clustering, protected effect counts, and
the still-closed development partition without publishing root identities or
private paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from pokemon_red_completion.living_dex_causal_journal import (
    LivingDexCausalTerminalStatus,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionKind,
    LivingDexOutcomeStatus,
)
from pokemon_red_completion.progress_dashboard import (
    DashboardExperimentState,
    DashboardModelState,
    DashboardSnapshot,
    DashboardWorkState,
)
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexTargetedScheduleBinding,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupProtectedEffectCheckpoint,
)
from pokemon_red_completion.red_living_dex_targeted_train_runner import (
    RedLivingDexTargetedSetupStatus,
    RedLivingDexTargetedTrainAssignment,
    RedLivingDexTargetedTrainReceipt,
)


class RedLivingDexTargetedTrainDashboardError(ValueError):
    """Targeted campaign progress cannot be projected safely."""


@dataclass(frozen=True, slots=True)
class RedLivingDexTargetedTrainDashboardProgress:
    """Identity-free progress supplied by the production campaign shell."""

    status: str = "waiting"
    active_assignment: RedLivingDexTargetedTrainAssignment | None = None
    receipts: tuple[RedLivingDexTargetedTrainReceipt, ...] = ()
    effects: RedLivingDexSetupProtectedEffectCheckpoint = (
        RedLivingDexSetupProtectedEffectCheckpoint()
    )

    def __post_init__(self) -> None:
        if self.status not in {"waiting", "running", "passed", "failed", "blocked"}:
            raise RedLivingDexTargetedTrainDashboardError(
                "targeted dashboard status differs"
            )
        if self.active_assignment is not None and not isinstance(
            self.active_assignment,
            RedLivingDexTargetedTrainAssignment,
        ):
            raise TypeError("targeted dashboard assignment differs")
        if not isinstance(self.receipts, tuple) or any(
            not isinstance(item, RedLivingDexTargetedTrainReceipt)
            for item in self.receipts
        ):
            raise TypeError("targeted dashboard receipts differ")
        if not isinstance(self.effects, RedLivingDexSetupProtectedEffectCheckpoint):
            raise TypeError("targeted dashboard effects differ")
        self.effects.__post_init__()


def red_living_dex_targeted_train_dashboard_snapshot(
    binding: RedLivingDexTargetedScheduleBinding,
    progress: RedLivingDexTargetedTrainDashboardProgress,
    *,
    updated_at: datetime | None = None,
) -> DashboardSnapshot:
    """Project one safe, descriptive campaign snapshot for the local dashboard."""

    if not isinstance(binding, RedLivingDexTargetedScheduleBinding):
        raise TypeError("targeted dashboard needs its schedule binding")
    binding.__post_init__()
    if not isinstance(progress, RedLivingDexTargetedTrainDashboardProgress):
        raise TypeError("targeted dashboard needs typed progress")
    progress.__post_init__()
    train_ordinals = tuple(
        ordinal
        for ordinal, slot in enumerate(binding.schedule.slots)
        if slot.partition == "train"
    )
    development_total = sum(
        slot.partition == "development" for slot in binding.schedule.slots
    )
    receipt_ordinals = tuple(item.assignment.ordinal for item in progress.receipts)
    if (
        len(receipt_ordinals) != len(set(receipt_ordinals))
        or any(ordinal not in train_ordinals for ordinal in receipt_ordinals)
        or any(item.assignment.binding != binding for item in progress.receipts)
    ):
        raise RedLivingDexTargetedTrainDashboardError(
            "targeted dashboard receipt roster differs"
        )
    active = progress.active_assignment
    if active is not None and (
        active.binding != binding
        or active.ordinal not in train_ordinals
        or active.ordinal in receipt_ordinals
    ):
        raise RedLivingDexTargetedTrainDashboardError(
            "targeted dashboard active slot differs"
        )
    if progress.status == "passed" and len(progress.receipts) != len(train_ordinals):
        raise RedLivingDexTargetedTrainDashboardError(
            "targeted dashboard cannot pass an incomplete campaign"
        )

    settled = sum(_settled_train_example(item) for item in progress.receipts)
    censored = len(progress.receipts) - settled
    setup_failed = sum(
        item.setup_status is RedLivingDexTargetedSetupStatus.FAILED
        for item in progress.receipts
    )
    setup_interrupted = sum(
        item.setup_status is RedLivingDexTargetedSetupStatus.INTERRUPTED
        for item in progress.receipts
    )
    causal_interrupted = sum(_causal_interrupted(item) for item in progress.receipts)
    current_number = (
        train_ordinals.index(active.ordinal) + 1 if active is not None else None
    )
    completed = len(progress.receipts)
    total = len(train_ordinals)
    base_clusters = len(
        {binding.schedule.slots[ordinal].lineage_sha256 for ordinal in train_ordinals}
    )
    focus_counts = _focus_counts(binding, train_ordinals)
    now = updated_at or datetime.now(UTC)
    if now.tzinfo is None:
        raise RedLivingDexTargetedTrainDashboardError(
            "targeted dashboard update time must be timezone-aware"
        )
    timestamp = now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    if active is not None:
        slot = active.slot
        stage = f"Train slot {current_number} of {total}: {slot.focus_kind.value}"
        message = (
            f"Executing reset {slot.reset_ordinal + 1} within one of "
            f"{base_clusters} declared base-state clusters. Only the selected "
            "factual arm can become a learner example."
        )
        current_step = (
            f"Authenticate setup, draw with full support, execute {slot.focus_kind.value}"
        )
        next_step = "Seal the factual outcome, then advance to the next train slot"
    elif progress.status == "passed":
        stage = "Targeted Red outcome collection complete"
        message = (
            f"All {total} train slots are terminal: {settled} settled learner "
            f"examples and {censored} censored or interrupted slots."
        )
        current_step = "Train outcome campaign sealed"
        next_step = "Audit sufficiency, then fit once from train examples only"
    else:
        stage = "Targeted Red outcome collection ready"
        message = (
            f"{completed} of {total} train slots are terminal. The development "
            "partition and model fitting remain closed."
        )
        current_step = "Authenticate the frozen schedule and next train slot"
        next_step = "Start or recover the next preregistered train reset"

    events = (
        "Mission: learn portable goal choice for story completion and a living Pokédex",
        f"Schedule: {total} train resets across {base_clusters} shared base-state clusters",
        "Behavior policy: 98:1 focus weighting with nonzero support for every legal option",
        f"Focus roster: {_format_focus_counts(focus_counts)}",
        f"Outcomes: {settled} settled; {censored} censored or interrupted",
        (
            f"Setup failures: {setup_failed}; setup interruptions: "
            f"{setup_interrupted}; causal interruptions: {causal_interrupted}"
        ),
        f"Development partition: 0 of {development_total} opened",
        "Model fits: 0; model predictions: 0; teacher queries: 0",
    )
    return DashboardSnapshot(
        game="Pokémon Red",
        run_status=progress.status,
        stage=stage,
        message=message,
        frame_count=progress.effects.emulator_frames,
        actions=progress.effects.controller_actions,
        stage_progress=completed / total if total else 0.0,
        collection_target=151,
        model=DashboardModelState(
            mode="waiting",
            candidate="Targeted living-Pokédex causal learner (not fitted yet)",
            choice=(
                f"Curriculum focus: {active.slot.focus_kind.value}"
                if active is not None
                else "No model decision—collecting causal outcomes"
            ),
        ),
        experiment=DashboardExperimentState(
            phase="training",
            zero_shot_completed=completed,
            zero_shot_total=total,
            adaptation_completed=0,
            adaptation_total=development_total,
            sealed_completed=0,
            sealed_total=1,
            heading="Red targeted learning gate",
            eyebrow="Causal data collection — not model play",
            counter_labels=(
                "Train slots terminal",
                "Development outcomes opened",
                "Model fits completed",
            ),
        ),
        work=DashboardWorkState(
            status=(
                "complete"
                if progress.status == "passed"
                else "blocked"
                if progress.status in {"failed", "blocked"}
                else "working"
                if progress.status == "running"
                else "waiting"
            ),
            headline="Collecting targeted Red decisions for the portable goal scorer",
            detail=(
                f"{settled} settled examples retained; {censored} slots censored. "
                "This campaign teaches option value, while deterministic skills "
                "continue to own movement, battles, capture, menus, and safety."
            ),
            current_step=current_step,
            next_step=next_step,
            completed_units=completed,
            total_units=total,
            updated_at_utc=timestamp,
        ),
        events=events,
    )


def _settled_train_example(receipt: RedLivingDexTargetedTrainReceipt) -> bool:
    causal = receipt.causal
    return bool(
        causal is not None
        and causal.example is not None
        and causal.example.outcome.status is LivingDexOutcomeStatus.SETTLED
    )


def _causal_interrupted(receipt: RedLivingDexTargetedTrainReceipt) -> bool:
    causal = receipt.causal
    return bool(
        causal is not None
        and causal.terminal is not None
        and causal.terminal.status
        is LivingDexCausalTerminalStatus.POSTRELEASE_INTERRUPTED
    )


def _focus_counts(
    binding: RedLivingDexTargetedScheduleBinding,
    train_ordinals: tuple[int, ...],
) -> tuple[tuple[LivingDexOptionKind, int], ...]:
    return tuple(
        (kind, sum(binding.schedule.slots[index].focus_kind is kind for index in train_ordinals))
        for kind in LivingDexOptionKind
        if any(binding.schedule.slots[index].focus_kind is kind for index in train_ordinals)
    )


def _format_focus_counts(counts: tuple[tuple[LivingDexOptionKind, int], ...]) -> str:
    return ", ".join(f"{kind.value} {count}" for kind, count in counts)


__all__ = [
    "RedLivingDexTargetedTrainDashboardError",
    "RedLivingDexTargetedTrainDashboardProgress",
    "red_living_dex_targeted_train_dashboard_snapshot",
]
