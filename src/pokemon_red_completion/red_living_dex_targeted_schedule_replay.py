"""Rejoin a frozen targeted schedule to freshly derived Red capabilities."""

from __future__ import annotations

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexCausalRootCapability,
    RedLivingDexTargetedScheduleBinding,
)
from pokemon_red_completion.red_living_dex_targeted_schedule_reader import (
    RedLivingDexTargetedScheduleDescriptor,
)


class RedLivingDexTargetedScheduleReplayError(ValueError):
    """Freshly observed Red mechanics differ from the frozen schedule."""


def rebind_red_living_dex_targeted_schedule(
    descriptor: RedLivingDexTargetedScheduleDescriptor,
    capabilities: tuple[RedLivingDexCausalRootCapability, ...],
) -> RedLivingDexTargetedScheduleBinding:
    """Select each frozen row from fresh, action-free Red capability edges.

    Extra freshly observed edges are harmless inventory.  Every scheduled row
    must have exactly one matching physical root, lineage, template, slot, and
    recipe identity.  This prevents the hash-authenticated descriptor from
    becoming execution authority by itself.
    """

    if not isinstance(descriptor, RedLivingDexTargetedScheduleDescriptor):
        raise TypeError("targeted replay needs its descriptor")
    descriptor.__post_init__()
    if not isinstance(capabilities, tuple) or any(
        not isinstance(item, RedLivingDexCausalRootCapability)
        for item in capabilities
    ):
        raise TypeError("targeted replay needs Red capabilities")
    for item in capabilities:
        item.__post_init__()

    selected: list[RedLivingDexCausalRootCapability] = []
    for slot, frozen in zip(
        descriptor.schedule.slots,
        descriptor.capabilities,
        strict=True,
    ):
        matches = tuple(
            capability
            for capability in capabilities
            if capability.root.root.physical_root_sha256
            == slot.physical_root_sha256
            and capability.root.independence_lineage_sha256 == slot.lineage_sha256
            and capability.template_ordinal == frozen.template_ordinal
            and canonical_sha256(capability.recipe.private_dict())
            == frozen.recipe_sha256
        )
        if len(matches) != 1:
            raise RedLivingDexTargetedScheduleReplayError(
                "targeted scheduled capability did not replay exactly once"
            )
        selected.append(matches[0])
    binding = RedLivingDexTargetedScheduleBinding(
        descriptor.schedule,
        tuple(selected),
    )
    if binding.binding_sha256 != descriptor.binding_sha256:
        raise RedLivingDexTargetedScheduleReplayError(
            "targeted Red binding did not replay"
        )
    return binding


__all__ = [
    "RedLivingDexTargetedScheduleReplayError",
    "rebind_red_living_dex_targeted_schedule",
]
