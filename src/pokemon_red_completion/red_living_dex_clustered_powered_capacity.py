"""Red adapter for the title-neutral clustered powered capacity gate.

Only authenticated, still-unused action-free roots enter this adapter.  It
preserves each root's upstream train/development ownership and projects the
already-enumerated root/template compatibility edges into digest-only capacity
facts.  It does not choose behavior, claim a root, execute a provider, or read
an outcome.
"""

from __future__ import annotations

from typing import Literal

from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCapturePartition,
)
from pokemon_red_completion.living_dex_clustered_powered_capacity import (
    LivingDexClusteredPoweredCapacityAudit,
    LivingDexClusteredPoweredCapacityError,
    LivingDexClusteredPoweredLineageAllocation,
    LivingDexClusteredPoweredLineageCapacity,
    LivingDexClusteredPoweredScenarioCapability,
    audit_living_dex_clustered_powered_capacity,
)
from pokemon_red_completion.living_dex_clustered_powered_design import (
    LivingDexClusteredPoweredDesign,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexCausalRootCapability,
)
from pokemon_red_completion.red_living_dex_provider_plan import (
    RedLivingDexActionFreeRootObservation,
)


def adapt_red_living_dex_clustered_powered_capacity(
    roots: tuple[RedLivingDexActionFreeRootObservation, ...],
    capabilities: tuple[RedLivingDexCausalRootCapability, ...],
) -> tuple[LivingDexClusteredPoweredLineageCapacity, ...]:
    """Project private Red roots and compatibility edges without taking action."""

    if not isinstance(roots, tuple) or any(
        not isinstance(item, RedLivingDexActionFreeRootObservation) for item in roots
    ):
        raise TypeError("Red powered capacity roots differ")
    if not isinstance(capabilities, tuple) or any(
        not isinstance(item, RedLivingDexCausalRootCapability) for item in capabilities
    ):
        raise TypeError("Red powered capacity capabilities differ")
    for observed_root in roots:
        observed_root.__post_init__()
    for capability in capabilities:
        capability.__post_init__()

    root_by_physical = {root.root.physical_root_sha256: root for root in roots}
    if len(root_by_physical) != len(roots):
        raise LivingDexClusteredPoweredCapacityError("Red powered capacity repeats a physical root")
    grouped: dict[str, list[RedLivingDexCausalRootCapability]] = {
        identity: [] for identity in root_by_physical
    }
    seen_edges: set[tuple[str, int]] = set()
    for capability in capabilities:
        physical = capability.root.root.physical_root_sha256
        joined_root = root_by_physical.get(physical)
        if joined_root is None or joined_root != capability.root:
            raise LivingDexClusteredPoweredCapacityError(
                "Red powered capability names a root outside the census"
            )
        edge = (physical, capability.template_ordinal)
        if edge in seen_edges:
            raise LivingDexClusteredPoweredCapacityError(
                "Red powered capacity repeats a root-template edge"
            )
        seen_edges.add(edge)
        grouped[physical].append(capability)

    adapted: list[LivingDexClusteredPoweredLineageCapacity] = []
    for physical in sorted(root_by_physical):
        root = root_by_physical[physical]
        if (
            not root.prospective_independence_authenticated
            or root.independence_lineage_sha256 is None
            or root.option_context is None
            or root.cluster_partition not in {"train", "development"}
        ):
            continue
        partition: Literal["train", "development"] = (
            "train" if root.cluster_partition == "train" else "development"
        )
        scenario_capabilities: list[LivingDexClusteredPoweredScenarioCapability] = []
        for capability in sorted(
            grouped[physical],
            key=lambda item: item.template_ordinal,
        ):
            slot_partition = (
                "train"
                if capability.slot.partition is LivingDexCapturePartition.TRAIN
                else "development"
            )
            if slot_partition != partition:
                continue
            scenario_capabilities.append(
                LivingDexClusteredPoweredScenarioCapability(
                    template_sha256=capability.slot.slot_sha256,
                    location_sha256=canonical_sha256(
                        {
                            "location_scope_id": capability.slot.location_scope_id,
                            "schema": "pokemon.red.private-powered-capacity-location.v1",
                        }
                    ),
                    semantic_family_sha256s=tuple(
                        provider.expected_family_sha256 for provider in capability.recipe.providers
                    ),
                    option_kinds=capability.slot.available_option_kinds,
                )
            )
        context = root.option_context
        adapted.append(
            LivingDexClusteredPoweredLineageCapacity(
                physical_root_sha256=physical,
                independence_lineage_sha256=root.independence_lineage_sha256,
                partition=partition,
                pressure_vector=tuple(
                    float(getattr(context, name))
                    for name in (
                        "collection_pressure",
                        "dependency_pressure",
                        "access_pressure",
                        "resource_pressure",
                        "storage_pressure",
                        "party_pressure",
                        "knowledge_pressure",
                    )
                ),
                scenarios=tuple(scenario_capabilities),
                same_reset_policy_forks_feasible=bool(scenario_capabilities),
            )
        )
    return tuple(adapted)


def audit_red_living_dex_clustered_powered_capacity(
    roots: tuple[RedLivingDexActionFreeRootObservation, ...],
    capabilities: tuple[RedLivingDexCausalRootCapability, ...],
    *,
    allocation: tuple[LivingDexClusteredPoweredLineageAllocation, ...] | None = None,
    design: LivingDexClusteredPoweredDesign | None = None,
) -> LivingDexClusteredPoweredCapacityAudit:
    """Adapt Red facts and run the title-neutral path-free capacity audit."""

    return audit_living_dex_clustered_powered_capacity(
        adapt_red_living_dex_clustered_powered_capacity(roots, capabilities),
        allocation=allocation,
        design=design,
    )


__all__ = [
    "adapt_red_living_dex_clustered_powered_capacity",
    "audit_red_living_dex_clustered_powered_capacity",
]
