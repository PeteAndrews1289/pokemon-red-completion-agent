"""Prospectively retire unopened evaluation roots into a smaller train update.

This is a title-neutral, action-free allocation boundary.  It makes the cost
explicit: roots moved into training permanently lose evaluation status.  The
remaining paired roots and reserves stay disjoint, and the resulting train
schedule must pass the independent-lineage/root diversity guard.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import combinations

from pokemon_red_completion.living_dex_targeted_update_capacity import (
    LivingDexTargetedCapacityContext,
    LivingDexTargetedCapacityError,
    LivingDexTargetedCapacityPolicy,
    LivingDexTargetedRootDiversityPolicy,
    LivingDexTargetedRootDiversityResult,
    LivingDexTargetedSchedule,
    freeze_living_dex_targeted_schedule,
    require_living_dex_targeted_schedule_root_diversity,
)
from pokemon_red_completion.provenance import canonical_sha256

LIVING_DEX_TARGETED_BANK_RETIREMENT_SCHEMA = (
    "pokemon.core.living-dex-targeted-bank-retirement.v1"
)


class LivingDexTargetedBankRetirementError(ValueError):
    """An unopened bank cannot support the declared retirement design."""


@dataclass(frozen=True, slots=True)
class LivingDexTargetedBankRetirementPlan:
    """One outcome-blind split into retired-train, paired, and reserve roots."""

    schedule: LivingDexTargetedSchedule
    diversity: LivingDexTargetedRootDiversityResult
    retired_train_contexts: tuple[LivingDexTargetedCapacityContext, ...]
    paired_development_contexts: tuple[LivingDexTargetedCapacityContext, ...]
    reserve_development_contexts: tuple[LivingDexTargetedCapacityContext, ...]

    def __post_init__(self) -> None:
        self.schedule.__post_init__()
        if not self.diversity.diversity_sufficient:
            raise LivingDexTargetedBankRetirementError(
                "retired bank schedule lacks root diversity"
            )
        groups = (
            self.retired_train_contexts,
            self.paired_development_contexts,
            self.reserve_development_contexts,
        )
        if any(
            not isinstance(group, tuple)
            or any(
                not isinstance(context, LivingDexTargetedCapacityContext)
                for context in group
            )
            for group in groups
        ):
            raise TypeError("targeted bank retirement contexts differ")
        for context in self.retired_train_contexts:
            if context.partition != "development":
                raise LivingDexTargetedBankRetirementError(
                    "retired train root was not formerly development"
                )
        for context in (
            *self.paired_development_contexts,
            *self.reserve_development_contexts,
        ):
            if context.partition != "development":
                raise LivingDexTargetedBankRetirementError(
                    "retained development root changed partition"
                )
        lineage_groups = tuple(
            {context.lineage_sha256 for context in group} for group in groups
        )
        physical_groups = tuple(
            {context.physical_root_sha256 for context in group} for group in groups
        )
        if (
            any(not group for group in lineage_groups)
            or any(
                left & right
                for index, left in enumerate(lineage_groups)
                for right in lineage_groups[index + 1 :]
            )
            or any(
                left & right
                for index, left in enumerate(physical_groups)
                for right in physical_groups[index + 1 :]
            )
        ):
            raise LivingDexTargetedBankRetirementError(
                "retired bank partitions overlap or lack a reserve"
            )
        train_slots = tuple(
            slot for slot in self.schedule.slots if slot.partition == "train"
        )
        development_slots = tuple(
            slot for slot in self.schedule.slots if slot.partition == "development"
        )
        if (
            {slot.lineage_sha256 for slot in train_slots} != lineage_groups[0]
            or {slot.lineage_sha256 for slot in development_slots}
            != lineage_groups[1]
        ):
            raise LivingDexTargetedBankRetirementError(
                "retired bank schedule differs from its root split"
            )

    @property
    def plan_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "paired_development_lineages": [
                context.lineage_sha256
                for context in self.paired_development_contexts
            ],
            "reserve_development_lineages": [
                context.lineage_sha256
                for context in self.reserve_development_contexts
            ],
            "retired_train_lineages": [
                context.lineage_sha256 for context in self.retired_train_contexts
            ],
            "schedule": self.schedule.private_dict(),
            "schema": LIVING_DEX_TARGETED_BANK_RETIREMENT_SCHEMA,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "bank_retirement_declared_before_outcomes": True,
            "controller_actions": 0,
            "diversity": self.diversity.public_dict(),
            "emulator_frames": 0,
            "evaluation_status_forfeited_roots": len(self.retired_train_contexts),
            "model_fits": 0,
            "model_predictions": 0,
            "outcomes_opened": 0,
            "paired_development_roots": len(self.paired_development_contexts),
            "plan_sha256": self.plan_sha256,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "reserve_development_roots": len(self.reserve_development_contexts),
            "schema": LIVING_DEX_TARGETED_BANK_RETIREMENT_SCHEMA,
            "teacher_queries": 0,
            "train_slots": sum(
                slot.partition == "train" for slot in self.schedule.slots
            ),
        }


def plan_living_dex_targeted_bank_retirement(
    contexts: tuple[LivingDexTargetedCapacityContext, ...],
    *,
    policy: LivingDexTargetedCapacityPolicy | None = None,
    retired_train_roots: int = 4,
    maximum_train_replays_per_context: int = 2,
) -> LivingDexTargetedBankRetirementPlan:
    """Find the first deterministic root-diverse split without opening outcomes."""

    if (
        not isinstance(contexts, tuple)
        or any(
            not isinstance(context, LivingDexTargetedCapacityContext)
            for context in contexts
        )
    ):
        raise TypeError("targeted bank retirement needs context tuples")
    ordered = tuple(
        sorted(
            contexts,
            key=lambda context: (
                context.lineage_sha256,
                context.physical_root_sha256,
            ),
        )
    )
    for context in ordered:
        context.__post_init__()
    active = LivingDexTargetedCapacityPolicy.retired_bank_v2() if policy is None else policy
    if not isinstance(active, LivingDexTargetedCapacityPolicy):
        raise TypeError("targeted bank retirement policy differs")
    active.__post_init__()
    if (
        any(context.partition != "development" for context in ordered)
        or len({context.lineage_sha256 for context in ordered}) != len(ordered)
        or len({context.physical_root_sha256 for context in ordered}) != len(ordered)
        or type(retired_train_roots) is not int  # noqa: E721
        or retired_train_roots < 4
        or retired_train_roots >= len(ordered)
        or type(maximum_train_replays_per_context) is not int  # noqa: E721
        or not 1 <= maximum_train_replays_per_context <= 3
    ):
        raise LivingDexTargetedBankRetirementError(
            "targeted bank retirement inputs differ"
        )

    for retired_indices in combinations(range(len(ordered)), retired_train_roots):
        retired_set = frozenset(retired_indices)
        candidate_contexts = tuple(
            replace(context, partition="train")
            if index in retired_set
            else context
            for index, context in enumerate(ordered)
        )
        try:
            schedule = freeze_living_dex_targeted_schedule(
                candidate_contexts,
                policy=active,
                maximum_train_replays_per_context=(
                    maximum_train_replays_per_context
                ),
                root_diversity_policy=LivingDexTargetedRootDiversityPolicy.v1(),
            )
            diversity = require_living_dex_targeted_schedule_root_diversity(
                schedule
            )
        except LivingDexTargetedCapacityError:
            continue
        train_lineages = {
            slot.lineage_sha256
            for slot in schedule.slots
            if slot.partition == "train"
        }
        paired_lineages = {
            slot.lineage_sha256
            for slot in schedule.slots
            if slot.partition == "development"
        }
        retired = tuple(
            context
            for context in ordered
            if context.lineage_sha256 in train_lineages
        )
        paired = tuple(
            context
            for context in ordered
            if context.lineage_sha256 in paired_lineages
        )
        reserve = tuple(
            context
            for context in ordered
            if context.lineage_sha256 not in train_lineages | paired_lineages
        )
        if reserve:
            return LivingDexTargetedBankRetirementPlan(
                schedule=schedule,
                diversity=diversity,
                retired_train_contexts=retired,
                paired_development_contexts=paired,
                reserve_development_contexts=reserve,
            )
    raise LivingDexTargetedBankRetirementError(
        "unopened bank cannot support a root-diverse retirement schedule"
    )


__all__ = [
    "LIVING_DEX_TARGETED_BANK_RETIREMENT_SCHEMA",
    "LivingDexTargetedBankRetirementError",
    "LivingDexTargetedBankRetirementPlan",
    "plan_living_dex_targeted_bank_retirement",
]
