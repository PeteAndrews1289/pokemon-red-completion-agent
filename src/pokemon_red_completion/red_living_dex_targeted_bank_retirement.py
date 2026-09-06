"""Bind an explicit unopened-bank retirement plan to real Red setup recipes."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCapturePartition,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.living_dex_targeted_bank_retirement import (
    LivingDexTargetedBankRetirementPlan,
    plan_living_dex_targeted_bank_retirement,
)
from pokemon_red_completion.living_dex_targeted_update_capacity import (
    LivingDexTargetedCapacityContext,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexCausalInventoryError,
    RedLivingDexCausalRootCapability,
    RedLivingDexTargetedScheduleBinding,
)

RED_LIVING_DEX_TARGETED_BANK_RETIREMENT_SCHEMA = (
    "pokemon.red.living-dex-targeted-bank-retirement-binding.v1"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RedLivingDexTargetedBankRetirementError(ValueError):
    """The Red capability bank cannot support the declared retirement."""


@dataclass(frozen=True, slots=True)
class RedLivingDexTargetedBankRetirementBinding:
    """One title-neutral retirement schedule joined to exact Red recipes."""

    retirement: LivingDexTargetedBankRetirementPlan
    binding: RedLivingDexTargetedScheduleBinding

    def __post_init__(self) -> None:
        self.retirement.__post_init__()
        self.binding.__post_init__()
        if self.binding.schedule != self.retirement.schedule:
            raise RedLivingDexTargetedBankRetirementError(
                "retired Red binding changed its schedule"
            )
        retired = {
            context.lineage_sha256
            for context in self.retirement.retired_train_contexts
        }
        paired = {
            context.lineage_sha256
            for context in self.retirement.paired_development_contexts
        }
        for slot, capability in zip(
            self.binding.schedule.slots,
            self.binding.capabilities,
            strict=True,
        ):
            lineage = capability.root.independence_lineage_sha256
            if (
                capability.root.cluster_partition != "development"
                or lineage is None
                or (slot.partition == "train" and lineage not in retired)
                or (slot.partition == "development" and lineage not in paired)
            ):
                raise RedLivingDexTargetedBankRetirementError(
                    "retired Red recipe lost its original development provenance"
                )

    @property
    def binding_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "red_binding": self.binding.private_dict(),
            "retirement": self.retirement.private_dict(),
            "schema": RED_LIVING_DEX_TARGETED_BANK_RETIREMENT_SCHEMA,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            **self.retirement.public_dict(),
            "binding_sha256": self.binding_sha256,
            "cartridge_specific_policy_features": 0,
            "red_recipes_bound": len(self.binding.capabilities),
            "source_partition_preserved_as_provenance": True,
            "source_partition_retained_for_evaluation": False,
            "schema": RED_LIVING_DEX_TARGETED_BANK_RETIREMENT_SCHEMA,
        }


def plan_red_living_dex_targeted_bank_retirement(
    capabilities: tuple[RedLivingDexCausalRootCapability, ...],
    *,
    excluded_lineages: frozenset[str] = frozenset(),
    excluded_physical_roots: frozenset[str] = frozenset(),
) -> RedLivingDexTargetedBankRetirementBinding:
    """Retire four unopened Red development roots before reading any outcome."""

    if not isinstance(capabilities, tuple) or any(
        not isinstance(capability, RedLivingDexCausalRootCapability)
        for capability in capabilities
    ):
        raise TypeError("Red bank retirement needs capability tuples")
    for excluded in (excluded_lineages, excluded_physical_roots):
        if not isinstance(excluded, frozenset) or any(
            not isinstance(value, str) or _SHA256.fullmatch(value) is None
            for value in excluded
        ):
            raise RedLivingDexTargetedBankRetirementError(
                "Red bank retirement exclusions differ"
            )
    grouped: dict[
        tuple[str, str],
        tuple[set[LivingDexOptionKind], set[LivingDexOptionKind]],
    ] = {}
    for capability in capabilities:
        capability.__post_init__()
        root = capability.root
        lineage = root.independence_lineage_sha256
        physical = root.root.physical_root_sha256
        if (
            lineage is None
            or lineage in excluded_lineages
            or physical in excluded_physical_roots
            or root.cluster_partition != "development"
            or not root.prospective_independence_authenticated
            or not root.root_claim_available
        ):
            continue
        train, development = grouped.setdefault((lineage, physical), (set(), set()))
        target = (
            train
            if capability.slot.partition is LivingDexCapturePartition.TRAIN
            else development
        )
        target.update(capability.slot.available_option_kinds)
    contexts = tuple(
        LivingDexTargetedCapacityContext(
            lineage_sha256=lineage,
            physical_root_sha256=physical,
            partition="development",
            available_option_kinds=tuple(
                kind
                for kind in LivingDexOptionKind
                if kind in train and kind in development
            ),
        )
        for (lineage, physical), (train, development) in sorted(grouped.items())
        if len(train & development) >= 2
    )
    retirement = plan_living_dex_targeted_bank_retirement(contexts)
    selected: list[RedLivingDexCausalRootCapability] = []
    for slot in retirement.schedule.slots:
        compatible = tuple(
            capability
            for capability in capabilities
            if capability.root.independence_lineage_sha256 == slot.lineage_sha256
            and capability.root.root.physical_root_sha256
            == slot.physical_root_sha256
            and slot.focus_kind in capability.slot.available_option_kinds
            and (
                "train"
                if capability.slot.partition is LivingDexCapturePartition.TRAIN
                else "development"
            )
            == slot.partition
        )
        if not compatible:
            raise RedLivingDexCausalInventoryError(
                "retired Red schedule lacks a compatible exact recipe"
            )
        selected.append(
            min(
                compatible,
                key=lambda capability: (
                    capability.template_ordinal,
                    capability.recipe.recipe_sha256,
                ),
            )
        )
    return RedLivingDexTargetedBankRetirementBinding(
        retirement=retirement,
        binding=RedLivingDexTargetedScheduleBinding(
            schedule=retirement.schedule,
            capabilities=tuple(selected),
        ),
    )


__all__ = [
    "RED_LIVING_DEX_TARGETED_BANK_RETIREMENT_SCHEMA",
    "RedLivingDexTargetedBankRetirementBinding",
    "RedLivingDexTargetedBankRetirementError",
    "plan_red_living_dex_targeted_bank_retirement",
]
