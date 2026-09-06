"""One factual campaign-admission decision for both display and fitting."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from pokemon_red_completion.living_dex_causal_journal import (
    LivingDexCausalTerminalStatus,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionKind,
    LivingDexOutcomeStatus,
)
from pokemon_red_completion.living_dex_targeted_update_capacity import (
    LivingDexTargetedCapacityPolicy,
    audit_living_dex_targeted_schedule_root_diversity,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexTargetedScheduleBinding,
)
from pokemon_red_completion.red_living_dex_targeted_train_runner import (
    RedLivingDexTargetedSetupStatus,
    RedLivingDexTargetedTrainReceipt,
)


@dataclass(frozen=True, slots=True)
class RedLivingDexTargetedTrainReadiness:
    """Path-free counts, never a replacement for authenticated corpus loading."""

    train_slots: int
    terminal_slots: int
    settled_examples: int
    setup_censors: int
    settled_by_kind: tuple[tuple[LivingDexOptionKind, int], ...]
    settled_root_count: int
    reasons: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.reasons

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.targeted-train-factual-readiness.v1",
            "ready": self.ready,
            "train_slots": self.train_slots,
            "terminal_slots": self.terminal_slots,
            "settled_examples": self.settled_examples,
            "setup_censors": self.setup_censors,
            "settled_by_actual_kind": {
                kind.value: count for kind, count in self.settled_by_kind
            },
            "settled_root_count": self.settled_root_count,
            "reasons": list(self.reasons),
        }

    @property
    def readiness_sha256(self) -> str:
        return canonical_sha256(self.public_dict())


def targeted_receipt_has_settled_example(
    receipt: RedLivingDexTargetedTrainReceipt,
) -> bool:
    causal = receipt.causal
    return bool(
        causal is not None
        and causal.example is not None
        and causal.example.partition == "train"
        and causal.example.outcome.status is LivingDexOutcomeStatus.SETTLED
        and causal.terminal is not None
        and causal.terminal.status is LivingDexCausalTerminalStatus.COMPLETE
    )


def audit_red_living_dex_targeted_train_readiness(
    binding: RedLivingDexTargetedScheduleBinding,
    receipts: tuple[RedLivingDexTargetedTrainReceipt, ...],
) -> RedLivingDexTargetedTrainReadiness:
    """Keep failed factual actions; censor missing outcomes, not failures."""

    binding.__post_init__()
    train_ordinals = {
        ordinal for ordinal, slot in enumerate(binding.schedule.slots)
        if slot.partition == "train"
    }
    seen: set[int] = set()
    sources: set[str] = set()
    actual: Counter[LivingDexOptionKind] = Counter()
    roots: set[str] = set()
    terminal_slots = 0
    setup_censors = 0
    for receipt in receipts:
        receipt.__post_init__()
        assignment = receipt.assignment
        if (
            assignment.binding != binding
            or assignment.ordinal not in train_ordinals
            or assignment.ordinal in seen
        ):
            raise ValueError("targeted readiness receipt roster differs")
        seen.add(assignment.ordinal)
        sources.add(assignment.source_commit)
        if receipt.setup_status is not RedLivingDexTargetedSetupStatus.COMPLETE:
            setup_censors += 1
            terminal_slots += 1
        elif receipt.causal is not None and receipt.causal.terminal is not None:
            terminal_slots += 1
        if targeted_receipt_has_settled_example(receipt):
            assert receipt.causal is not None and receipt.causal.example is not None
            example = receipt.causal.example
            actual[example.menu.candidates[example.selected_candidate_index].features.kind] += 1
            roots.add(assignment.slot.physical_root_sha256)
    if len(sources) > 1:
        raise ValueError("targeted readiness source identities differ")
    policy = binding.schedule.policy
    reasons: list[str] = []
    if terminal_slots != len(train_ordinals):
        reasons.append("incomplete_train_denominator")
    if setup_censors > policy.maximum_train_setup_censors:
        reasons.append("setup_censor_limit")
    if sum(actual.values()) < policy.minimum_settled_train:
        reasons.append("insufficient_settled_examples")
    for kind, minimum in policy.minimum_settled_train_by_kind:
        if actual[kind] < minimum:
            reasons.append(f"insufficient_actual_{kind.value}")
    if not audit_living_dex_targeted_schedule_root_diversity(
        binding.schedule
    ).diversity_sufficient:
        reasons.append("schedule_root_diversity")
    if (
        policy == LivingDexTargetedCapacityPolicy.retired_bank_v2()
        and binding.schedule.maximum_train_replays_per_context != 2
    ):
        reasons.append("retired_bank_reset_cap")
    return RedLivingDexTargetedTrainReadiness(
        train_slots=len(train_ordinals),
        terminal_slots=terminal_slots,
        settled_examples=sum(actual.values()),
        setup_censors=setup_censors,
        settled_by_kind=tuple((kind, actual[kind]) for kind in LivingDexOptionKind),
        settled_root_count=len(roots),
        reasons=tuple(reasons),
    )
