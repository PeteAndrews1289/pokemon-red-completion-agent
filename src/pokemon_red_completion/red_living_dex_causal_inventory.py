"""Action-free Red compatibility inventory and clustered integration adapter.

The historical provider freezer proved fifteen genuine three-option menus.  A
powered fit and paired policy test require many more independent contexts.  A
raw root count is not enough: a root may be unable to reach a particular
origin or satisfy that menu's mechanical preconditions.  This module tests
every available root against every frozen Red template.  The historical
one-root-per-context matching remains available as a diagnostic, but it is no
longer the training-capacity rule.  The clustered adapter locks each upstream
lineage to one partition and permits a bounded number of short scenarios
inside that lineage.

The result is deliberately action-free.  It does not freeze behavior
permutations, execute a provider, observe an outcome, fit a model, or authorize
collection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCapturePartition,
    LivingDexProspectiveCaptureSlot,
)
from pokemon_red_completion.living_dex_causal_capacity_schedule import (
    LivingDexCausalCapacitySlot,
    build_living_dex_causal_capacity_schedule,
)
from pokemon_red_completion.living_dex_causal_curriculum import (
    LivingDexCausalCurriculumDesign,
)
from pokemon_red_completion.living_dex_clustered_curriculum import (
    LivingDexClusteredCurriculumPolicy,
    LivingDexClusteredCurriculumSchedule,
    LivingDexClusteredScenarioCapability,
    LivingDexClusterPartition,
    schedule_living_dex_clustered_curriculum,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.living_dex_targeted_update_capacity import (
    LivingDexTargetedCapacityContext,
    LivingDexTargetedCapacityPolicy,
    LivingDexTargetedCapacityResult,
    audit_living_dex_targeted_update_capacity,
)
from pokemon_red_completion.red_living_dex_capture_plan import (
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_provider_plan import (
    RedLivingDexActionFreeRootObservation,
    RedLivingDexProviderPlanError,
    RedLivingDexProviderRouteWorld,
    build_red_living_dex_provider_recipe_for_action_free_root,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexSetupSlotRecipe,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupProtectedEffectCheckpoint,
)
from pokemon_red_completion.red_living_dex_wild_corridor import (
    RedLivingDexWildCorridor,
)

RED_LIVING_DEX_CAUSAL_INVENTORY_SCHEMA = (
    "pokemon.red.living-dex-causal-action-free-inventory.v1"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RedLivingDexCausalInventoryError(ValueError):
    """The inventory contains a duplicate, fabricated, or effectful row."""


@dataclass(frozen=True, slots=True)
class RedLivingDexCausalRootCapability:
    """One authentic root can construct one frozen menu template."""

    root: RedLivingDexActionFreeRootObservation
    template_ordinal: int
    slot: LivingDexProspectiveCaptureSlot
    recipe: RedLivingDexSetupSlotRecipe

    def __post_init__(self) -> None:
        if not isinstance(self.root, RedLivingDexActionFreeRootObservation):
            raise TypeError("causal inventory capability needs an action-free root")
        if not isinstance(self.slot, LivingDexProspectiveCaptureSlot):
            raise TypeError("causal inventory capability needs a Red template")
        if not isinstance(self.recipe, RedLivingDexSetupSlotRecipe):
            raise TypeError("causal inventory capability needs a provider recipe")
        self.root.__post_init__()
        self.slot.__post_init__()
        self.recipe.__post_init__()
        canonical = build_red_living_dex_prospective_capture_plan().slots
        if (
            type(self.template_ordinal) is not int  # noqa: E721
            or not 0 <= self.template_ordinal < len(canonical)
            or canonical[self.template_ordinal].slot_sha256 != self.slot.slot_sha256
            or self.recipe.slot_sha256 != self.slot.slot_sha256
            or self.recipe.root_state_sha256 != self.root.root.state_sha256
            or self.recipe.root_envelope_sha256 != self.root.root.envelope_sha256
            or self.recipe.root_consumption_sha256
            != self.root.root.root_consumption_sha256
        ):
            raise RedLivingDexCausalInventoryError(
                "causal inventory capability does not join its root and template"
            )


@dataclass(frozen=True, slots=True)
class RedLivingDexCausalInventoryAudit:
    """Path-free root compatibility bound; never a collection authorization."""

    design_sha256: str
    capacity_schedule_sha256: str
    roots_observed: int
    distinct_physical_roots: int
    distinct_independence_lineages: int
    independence_qualified_roots: int
    unqualified_lineage_roots: int
    roots_with_any_compatible_template: int
    roots_without_compatible_template: int
    compatibility_edges: int
    train_template_compatible_root_counts: tuple[int, ...]
    development_template_compatible_root_counts: tuple[int, ...]
    train_maximum_matching: int
    development_maximum_matching: int
    combined_maximum_matching: int
    train_context_deficit: int
    development_context_deficit: int
    combined_context_deficit: int
    pressure_value_counts: tuple[int, ...]
    reasons: tuple[str, ...]

    @property
    def inventory_sufficient(self) -> bool:
        return not self.reasons

    def public_dict(self) -> dict[str, object]:
        return {
            "behavior_commitments": 0,
            "capacity_schedule_sha256": self.capacity_schedule_sha256,
            "collection_authorized": False,
            "combined_context_deficit": self.combined_context_deficit,
            "combined_maximum_matching": self.combined_maximum_matching,
            "compatibility_edges": self.compatibility_edges,
            "controller_actions": 0,
            "design_sha256": self.design_sha256,
            "development_context_deficit": self.development_context_deficit,
            "development_maximum_matching": self.development_maximum_matching,
            "development_template_compatible_root_counts": list(
                self.development_template_compatible_root_counts
            ),
            "distinct_independence_lineages": self.distinct_independence_lineages,
            "distinct_physical_roots": self.distinct_physical_roots,
            "emulator_frames": 0,
            "full_capacity_audits": 0,
            "independence_qualified_roots": self.independence_qualified_roots,
            "inventory_sufficient": self.inventory_sufficient,
            "minimum_new_independent_roots_lower_bound": self.combined_context_deficit,
            "model_fits": 0,
            "model_predictions": 0,
            "outcomes": 0,
            "pressure_value_counts": list(self.pressure_value_counts),
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "provider_executions": 0,
            "reasons": list(self.reasons),
            "root_claims": 0,
            "roots_observed": self.roots_observed,
            "roots_with_any_compatible_template": (
                self.roots_with_any_compatible_template
            ),
            "roots_without_compatible_template": (
                self.roots_without_compatible_template
            ),
            "schema": RED_LIVING_DEX_CAUSAL_INVENTORY_SCHEMA,
            "teacher_queries": 0,
            "train_context_deficit": self.train_context_deficit,
            "train_maximum_matching": self.train_maximum_matching,
            "train_template_compatible_root_counts": list(
                self.train_template_compatible_root_counts
            ),
            "unqualified_lineage_roots": self.unqualified_lineage_roots,
        }


def census_red_living_dex_causal_inventory(
    roots: tuple[RedLivingDexActionFreeRootObservation, ...],
    *,
    world: RedLivingDexProviderRouteWorld,
    corridors: tuple[RedLivingDexWildCorridor, ...],
    effects_before: RedLivingDexSetupProtectedEffectCheckpoint,
    effects_after: RedLivingDexSetupProtectedEffectCheckpoint,
    design: LivingDexCausalCurriculumDesign | None = None,
) -> RedLivingDexCausalInventoryAudit:
    """Read no new bytes; enumerate exact menu compatibility and match capacity."""

    capabilities = enumerate_red_living_dex_causal_capabilities(
        roots,
        world=world,
        corridors=corridors,
        effects_before=effects_before,
        effects_after=effects_after,
    )
    return audit_red_living_dex_causal_inventory(
        roots,
        capabilities,
        design=design,
    )


def enumerate_red_living_dex_causal_capabilities(
    roots: tuple[RedLivingDexActionFreeRootObservation, ...],
    *,
    world: RedLivingDexProviderRouteWorld,
    corridors: tuple[RedLivingDexWildCorridor, ...],
    effects_before: RedLivingDexSetupProtectedEffectCheckpoint,
    effects_after: RedLivingDexSetupProtectedEffectCheckpoint,
) -> tuple[RedLivingDexCausalRootCapability, ...]:
    """Return exact root-template edges without action, claim, or partition choice."""

    if not isinstance(roots, tuple) or any(
        not isinstance(item, RedLivingDexActionFreeRootObservation) for item in roots
    ):
        raise TypeError("Red causal inventory needs an ordered root tuple")
    for root in roots:
        root.__post_init__()
    for checkpoint in (effects_before, effects_after):
        if not isinstance(checkpoint, RedLivingDexSetupProtectedEffectCheckpoint):
            raise TypeError("Red causal inventory needs protected-effect checkpoints")
        checkpoint.__post_init__()
    if effects_before != effects_after:
        raise RedLivingDexCausalInventoryError(
            "Red causal inventory crossed a protected effect"
        )
    _require_unique_roots_and_lineages(roots)
    plan = build_red_living_dex_prospective_capture_plan()
    qualified_roots = tuple(
        root for root in roots if root.prospective_independence_authenticated
    )
    capabilities: list[RedLivingDexCausalRootCapability] = []
    for root in sorted(
        qualified_roots,
        key=lambda item: item.root.physical_root_sha256,
    ):
        for template_ordinal, slot in enumerate(plan.slots):
            try:
                recipe = build_red_living_dex_provider_recipe_for_action_free_root(
                    slot,
                    root,
                    world=world,
                    corridors=corridors,
                )
            except RedLivingDexProviderPlanError:
                continue
            capabilities.append(
                RedLivingDexCausalRootCapability(
                    root=root,
                    template_ordinal=template_ordinal,
                    slot=slot,
                    recipe=recipe,
                )
            )
    return tuple(capabilities)


def schedule_red_living_dex_clustered_integration(
    capabilities: tuple[RedLivingDexCausalRootCapability, ...],
    *,
    policy: LivingDexClusteredCurriculumPolicy | None = None,
) -> LivingDexClusteredCurriculumSchedule:
    """Adapt Red root-template edges into the title-neutral cluster contract.

    The root's upstream catalog partition is immutable provenance.  Train
    roots may expose only train templates and development roots only
    development templates; unmatched edges remain inventory information but
    cannot cross the generalization wall.
    """

    if not isinstance(capabilities, tuple) or any(
        not isinstance(item, RedLivingDexCausalRootCapability)
        for item in capabilities
    ):
        raise TypeError("Red clustered integration needs capability tuples")
    adapted: list[LivingDexClusteredScenarioCapability] = []
    for capability in capabilities:
        capability.__post_init__()
        root = capability.root
        if (
            root.cluster_partition is None
            or root.independence_lineage_sha256 is None
            or not root.prospective_independence_authenticated
        ):
            continue
        slot_partition: LivingDexClusterPartition = (
            "train"
            if capability.slot.partition is LivingDexCapturePartition.TRAIN
            else "development"
        )
        if root.cluster_partition != slot_partition:
            continue
        adapted.append(
            LivingDexClusteredScenarioCapability(
                lineage_sha256=root.independence_lineage_sha256,
                physical_root_sha256=root.root.physical_root_sha256,
                partition=slot_partition,
                template_sha256=capability.slot.slot_sha256,
                available_option_kinds=capability.slot.available_option_kinds,
            )
        )
    return schedule_living_dex_clustered_curriculum(
        tuple(adapted),
        policy=policy,
    )


def red_living_dex_targeted_capacity_contexts(
    capabilities: tuple[RedLivingDexCausalRootCapability, ...],
    *,
    excluded_lineages: frozenset[str] = frozenset(),
    excluded_physical_roots: frozenset[str] = frozenset(),
) -> tuple[LivingDexTargetedCapacityContext, ...]:
    """Collapse exact Red root-template edges into untouched shared contexts."""

    if not isinstance(capabilities, tuple) or any(
        not isinstance(item, RedLivingDexCausalRootCapability)
        for item in capabilities
    ):
        raise TypeError("Red targeted capacity capabilities differ")
    for excluded in (excluded_lineages, excluded_physical_roots):
        if not isinstance(excluded, frozenset) or any(
            not isinstance(item, str) or _SHA256.fullmatch(item) is None
            for item in excluded
        ):
            raise RedLivingDexCausalInventoryError(
                "Red targeted capacity exclusions differ"
            )
    grouped: dict[tuple[str, str, str], set[LivingDexOptionKind]] = {}
    for capability in capabilities:
        capability.__post_init__()
        root = capability.root
        lineage = root.independence_lineage_sha256
        partition = root.cluster_partition
        slot_partition = (
            "train"
            if capability.slot.partition is LivingDexCapturePartition.TRAIN
            else "development"
        )
        if (
            lineage is None
            or partition not in {"train", "development"}
            or partition != slot_partition
            or not root.prospective_independence_authenticated
            or not root.root_claim_available
            or lineage in excluded_lineages
            or root.root.physical_root_sha256 in excluded_physical_roots
        ):
            continue
        key = (lineage, root.root.physical_root_sha256, partition)
        grouped.setdefault(key, set()).update(capability.slot.available_option_kinds)
    contexts = tuple(
        LivingDexTargetedCapacityContext(
            lineage_sha256=lineage,
            physical_root_sha256=physical,
            partition=partition,  # type: ignore[arg-type]
            available_option_kinds=tuple(
                kind for kind in LivingDexOptionKind if kind in kinds
            ),
        )
        for (lineage, physical, partition), kinds in sorted(grouped.items())
        if len(kinds) >= 2
    )
    if len({item.lineage_sha256 for item in contexts}) != len(contexts):
        raise RedLivingDexCausalInventoryError(
            "Red targeted capacity repeats an upstream lineage"
        )
    return contexts


def audit_red_living_dex_targeted_update_capacity(
    capabilities: tuple[RedLivingDexCausalRootCapability, ...],
    *,
    excluded_lineages: frozenset[str] = frozenset(),
    excluded_physical_roots: frozenset[str] = frozenset(),
    policy: LivingDexTargetedCapacityPolicy | None = None,
    maximum_train_replays_per_context: int = 1,
) -> LivingDexTargetedCapacityResult:
    """Audit the post-five-case Red bank without choosing, claiming, or executing."""

    return audit_living_dex_targeted_update_capacity(
        red_living_dex_targeted_capacity_contexts(
            capabilities,
            excluded_lineages=excluded_lineages,
            excluded_physical_roots=excluded_physical_roots,
        ),
        policy=policy,
        maximum_train_replays_per_context=maximum_train_replays_per_context,
    )


def audit_red_living_dex_causal_inventory(
    roots: tuple[RedLivingDexActionFreeRootObservation, ...],
    capabilities: tuple[RedLivingDexCausalRootCapability, ...],
    *,
    design: LivingDexCausalCurriculumDesign | None = None,
) -> RedLivingDexCausalInventoryAudit:
    """Compute aggregate matching bounds from already enumerated capabilities."""

    active_design = LivingDexCausalCurriculumDesign() if design is None else design
    if not isinstance(active_design, LivingDexCausalCurriculumDesign):
        raise TypeError("Red causal inventory needs its frozen design")
    active_design.__post_init__()
    if not isinstance(roots, tuple) or any(
        not isinstance(item, RedLivingDexActionFreeRootObservation) for item in roots
    ):
        raise TypeError("Red causal inventory needs an ordered root tuple")
    if not isinstance(capabilities, tuple) or any(
        not isinstance(item, RedLivingDexCausalRootCapability) for item in capabilities
    ):
        raise TypeError("Red causal inventory capabilities differ")
    for root in roots:
        root.__post_init__()
    for capability in capabilities:
        capability.__post_init__()
    _require_unique_roots_and_lineages(roots)
    qualified_roots = tuple(
        root for root in roots if root.prospective_independence_authenticated
    )
    physical_roots = tuple(
        root.root.physical_root_sha256 for root in qualified_roots
    )
    root_set = set(physical_roots)
    if any(
        capability.root.root.physical_root_sha256 not in root_set
        for capability in capabilities
    ):
        raise RedLivingDexCausalInventoryError(
            "causal capability names a root outside the census"
        )
    if any(
        not capability.root.prospective_independence_authenticated
        for capability in capabilities
    ):
        raise RedLivingDexCausalInventoryError(
            "causal capability uses an unqualified independence lineage"
        )
    capability_keys = tuple(
        (item.root.root.physical_root_sha256, item.template_ordinal)
        for item in capabilities
    )
    if len(set(capability_keys)) != len(capability_keys):
        raise RedLivingDexCausalInventoryError(
            "causal inventory repeats a root-template capability"
        )

    plan = build_red_living_dex_prospective_capture_plan()
    train_slots = tuple(
        slot for slot in plan.slots if slot.partition is LivingDexCapturePartition.TRAIN
    )
    development_slots = tuple(
        slot
        for slot in plan.slots
        if slot.partition is LivingDexCapturePartition.DEVELOPMENT
    )
    if plan.slots != (*train_slots, *development_slots):
        raise RedLivingDexCausalInventoryError(
            "causal inventory template partitions are not contiguous"
        )
    schedule = build_living_dex_causal_capacity_schedule(
        tuple(slot.available_option_kinds for slot in train_slots),
        tuple(slot.available_option_kinds for slot in development_slots),
        design=active_design,
    )
    compatible_by_template: dict[int, set[str]] = {
        index: set() for index in range(len(plan.slots))
    }
    for capability in capabilities:
        compatible_by_template[capability.template_ordinal].add(
            capability.root.root.physical_root_sha256
        )

    logical_train = tuple(item for item in schedule.slots if item.partition == "train")
    logical_development = tuple(
        item for item in schedule.slots if item.partition == "development"
    )
    train_matching = _maximum_matching(
        logical_train,
        compatible_by_template,
        physical_roots,
        development_template_offset=0,
    )
    development_matching = _maximum_matching(
        logical_development,
        compatible_by_template,
        physical_roots,
        development_template_offset=len(train_slots),
    )
    combined_matching = _maximum_matching(
        schedule.slots,
        compatible_by_template,
        physical_roots,
        development_template_offset=len(train_slots),
    )
    roots_with_edges = {
        root
        for roots_for_template in compatible_by_template.values()
        for root in roots_for_template
    }
    pressure_counts = _pressure_value_counts(qualified_roots)
    train_deficit = active_design.prospective_train_contexts - train_matching
    development_deficit = (
        active_design.prospective_development_contexts - development_matching
    )
    combined_required = (
        active_design.prospective_train_contexts
        + active_design.prospective_development_contexts
    )
    combined_deficit = combined_required - combined_matching
    reasons: list[str] = []
    if train_deficit:
        reasons.append("insufficient_train_root_compatibility")
    if development_deficit:
        reasons.append("insufficient_development_root_compatibility")
    if combined_deficit:
        reasons.append("insufficient_disjoint_combined_root_compatibility")
    if any(not compatible_by_template[index] for index in range(len(plan.slots))):
        reasons.append("uncovered_menu_template")
    if any(
        count < active_design.minimum_train_pressure_values_per_axis
        for count in pressure_counts
    ):
        reasons.append("insufficient_observed_pressure_variation")

    return RedLivingDexCausalInventoryAudit(
        design_sha256=active_design.design_sha256,
        capacity_schedule_sha256=schedule.schedule_sha256,
        roots_observed=len(roots),
        distinct_physical_roots=len(
            {root.root.physical_root_sha256 for root in roots}
        ),
        distinct_independence_lineages=len(
            {root.independence_lineage_sha256 for root in qualified_roots}
        ),
        independence_qualified_roots=len(qualified_roots),
        unqualified_lineage_roots=len(roots) - len(qualified_roots),
        roots_with_any_compatible_template=len(roots_with_edges),
        roots_without_compatible_template=(
            len(qualified_roots) - len(roots_with_edges)
        ),
        compatibility_edges=len(capabilities),
        train_template_compatible_root_counts=tuple(
            len(compatible_by_template[index]) for index in range(len(train_slots))
        ),
        development_template_compatible_root_counts=tuple(
            len(compatible_by_template[index])
            for index in range(len(train_slots), len(plan.slots))
        ),
        train_maximum_matching=train_matching,
        development_maximum_matching=development_matching,
        combined_maximum_matching=combined_matching,
        train_context_deficit=train_deficit,
        development_context_deficit=development_deficit,
        combined_context_deficit=combined_deficit,
        pressure_value_counts=pressure_counts,
        reasons=tuple(sorted(set(reasons))),
    )


def _maximum_matching(
    logical_slots: tuple[LivingDexCausalCapacitySlot, ...],
    compatible_by_template: dict[int, set[str]],
    physical_roots: tuple[str, ...],
    *,
    development_template_offset: int,
) -> int:
    """Return the exact maximum one-root-per-logical-context cardinality."""

    root_to_slot: dict[str, int] = {}

    def template_index(slot: LivingDexCausalCapacitySlot) -> int:
        return slot.template_ordinal + (
            development_template_offset if slot.partition == "development" else 0
        )

    ordered_slot_indices = tuple(
        sorted(
            range(len(logical_slots)),
            key=lambda index: (
                len(compatible_by_template[template_index(logical_slots[index])]),
                logical_slots[index].partition,
                logical_slots[index].template_ordinal,
                logical_slots[index].repetition_ordinal,
            ),
        )
    )

    def augment(slot_index: int, seen_roots: set[str]) -> bool:
        slot = logical_slots[slot_index]
        options = compatible_by_template[template_index(slot)]
        for root in physical_roots:
            if root not in options or root in seen_roots:
                continue
            seen_roots.add(root)
            prior = root_to_slot.get(root)
            if prior is None or augment(prior, seen_roots):
                root_to_slot[root] = slot_index
                return True
        return False

    return sum(augment(slot_index, set()) for slot_index in ordered_slot_indices)


def _pressure_value_counts(
    roots: tuple[RedLivingDexActionFreeRootObservation, ...],
) -> tuple[int, ...]:
    contexts = tuple(root.option_context for root in roots)
    if any(context is None for context in contexts):
        raise RedLivingDexCausalInventoryError(
            "causal inventory root lacks its title-neutral pressure observation"
        )
    names = (
        "collection_pressure",
        "dependency_pressure",
        "access_pressure",
        "resource_pressure",
        "storage_pressure",
        "party_pressure",
        "knowledge_pressure",
    )
    return tuple(
        len({float(getattr(context, name)) for context in contexts})
        for name in names
    )


def _require_unique_roots_and_lineages(
    roots: tuple[RedLivingDexActionFreeRootObservation, ...],
) -> None:
    for values, subject in (
        ((root.root.physical_root_sha256 for root in roots), "physical root"),
        ((root.root.state_sha256 for root in roots), "state"),
        ((root.root.envelope_sha256 for root in roots), "envelope"),
    ):
        materialized = tuple(values)
        if len(set(materialized)) != len(materialized):
            raise RedLivingDexCausalInventoryError(
                f"Red causal inventory repeats a {subject}"
            )
    qualified_lineages = tuple(
        root.independence_lineage_sha256
        for root in roots
        if root.prospective_independence_authenticated
    )
    if None in qualified_lineages or len(set(qualified_lineages)) != len(
        qualified_lineages
    ):
        raise RedLivingDexCausalInventoryError(
            "Red causal inventory repeats an independence lineage"
        )


__all__ = [
    "RED_LIVING_DEX_CAUSAL_INVENTORY_SCHEMA",
    "RedLivingDexCausalInventoryAudit",
    "RedLivingDexCausalInventoryError",
    "RedLivingDexCausalRootCapability",
    "audit_red_living_dex_causal_inventory",
    "audit_red_living_dex_targeted_update_capacity",
    "census_red_living_dex_causal_inventory",
    "red_living_dex_targeted_capacity_contexts",
]
