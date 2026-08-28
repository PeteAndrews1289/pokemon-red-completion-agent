"""Red action-free adapter into the powered causal capacity contract.

The provider freezer already knows how to join an authenticated root, a
title-neutral prospective slot, and three genuine same-origin Red provider
recipes without pressing a button.  This adapter projects that joined object
into the shared capacity schema.  Concrete scope labels, root bytes, routes,
and family bindings remain private digests; the public audit receives counts.
"""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCapturePartition,
    LivingDexProspectiveCaptureSlot,
)
from pokemon_red_completion.living_dex_causal_curriculum import (
    LivingDexCausalCapacityAudit,
    LivingDexCausalCapacityContext,
    LivingDexCausalCurriculumDesign,
    audit_living_dex_causal_capacity,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_provider_plan import (
    RedLivingDexActionFreeRootObservation,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexSetupSlotRecipe,
)


class RedLivingDexCausalCapacityError(ValueError):
    """A Red action-free root cannot support its prospective causal slot."""


@dataclass(frozen=True, slots=True)
class RedLivingDexCausalCapacityAssignment:
    """One outcome-blind root-to-template assignment for capacity auditing."""

    slot: LivingDexProspectiveCaptureSlot
    recipe: RedLivingDexSetupSlotRecipe
    root: RedLivingDexActionFreeRootObservation
    focus_kind: LivingDexOptionKind
    assigned_candidate_index: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.slot, LivingDexProspectiveCaptureSlot):
            raise TypeError("Red causal capacity needs a prospective slot")
        if not isinstance(self.recipe, RedLivingDexSetupSlotRecipe):
            raise TypeError("Red causal capacity needs a provider recipe")
        if not isinstance(self.root, RedLivingDexActionFreeRootObservation):
            raise TypeError("Red causal capacity needs an action-free root")
        self.slot.__post_init__()
        self.recipe.__post_init__()
        self.root.__post_init__()
        if (
            self.slot.slot_sha256 != self.recipe.slot_sha256
            or self.slot.partition is not self.recipe.partition
            or self.slot.available_option_kinds != self.recipe.available_option_kinds
            or self.root.root.root_consumption_sha256 != self.recipe.root_consumption_sha256
            or self.root.root.state_sha256 != self.recipe.root_state_sha256
            or self.root.root.envelope_sha256 != self.recipe.root_envelope_sha256
        ):
            raise RedLivingDexCausalCapacityError(
                "Red causal capacity root recipe and slot do not join"
            )
        if self.root.option_context is None:
            raise RedLivingDexCausalCapacityError(
                "Red causal capacity lacks title-neutral pressure observation"
            )
        if self.root.independence_lineage_sha256 is None:
            raise RedLivingDexCausalCapacityError(
                "Red causal capacity lacks an authenticated lineage"
            )
        if not self.root.prospective_independence_authenticated:
            raise RedLivingDexCausalCapacityError(
                "Red causal capacity lineage is not prospectively authenticated"
            )
        if self.focus_kind not in self.slot.available_option_kinds:
            raise RedLivingDexCausalCapacityError(
                "Red causal capacity focus kind is absent from its menu"
            )
        if self.slot.partition is LivingDexCapturePartition.TRAIN:
            if (
                type(self.assigned_candidate_index) is not int  # noqa: E721
                or not 0 <= self.assigned_candidate_index < len(self.slot.available_option_kinds)
                or self.slot.available_option_kinds[self.assigned_candidate_index]
                is not self.focus_kind
            ):
                raise RedLivingDexCausalCapacityError("Red train capacity assignment differs")
        elif self.assigned_candidate_index is not None:
            raise RedLivingDexCausalCapacityError(
                "Red development capacity contains a premature policy choice"
            )

    def shared_context(self) -> LivingDexCausalCapacityContext:
        self.__post_init__()
        option_context = self.root.option_context
        lineage = self.root.independence_lineage_sha256
        assert option_context is not None
        assert lineage is not None
        semantic_families = tuple(
            provider.expected_family_sha256 for provider in self.recipe.providers
        )
        family_scope = canonical_sha256(
            {
                "family_scope_id": self.slot.family_scope_id,
                "schema": "pokemon.red.private-causal-family-scope.v1",
            }
        )
        location_scope = canonical_sha256(
            {
                "location_scope_id": self.slot.location_scope_id,
                "schema": "pokemon.red.private-causal-location-scope.v1",
            }
        )
        menu_shape = canonical_sha256(
            {
                "available_option_kinds": [kind.value for kind in self.slot.available_option_kinds],
                "option_context": option_context.policy_dict(),
                "origin_scope_sha256": self.recipe.location_sha256,
                "schema": "pokemon.red.private-action-free-causal-menu-shape.v1",
                "semantic_family_sha256s": list(semantic_families),
            }
        )
        context_identity = canonical_sha256(
            {
                "independence_lineage_sha256": lineage,
                "menu_shape_sha256": menu_shape,
                "physical_root_sha256": self.root.root.physical_root_sha256,
                "schema": "pokemon.red.private-action-free-causal-capacity-context.v1",
                "slot_sha256": self.slot.slot_sha256,
            }
        )
        return LivingDexCausalCapacityContext(
            context_identity_sha256=context_identity,
            physical_root_sha256=self.root.root.physical_root_sha256,
            independence_lineage_sha256=lineage,
            family_scope_sha256=family_scope,
            location_scope_sha256=location_scope,
            template_scope_sha256=self.slot.slot_sha256,
            menu_shape_sha256=menu_shape,
            semantic_family_sha256s=semantic_families,
            partition=(
                "train" if self.slot.partition is LivingDexCapturePartition.TRAIN else "development"
            ),
            option_kinds=self.slot.available_option_kinds,
            focus_kind=self.focus_kind,
            option_context=option_context,
            assigned_candidate_index=self.assigned_candidate_index,
            root_available=self.root.root_claim_available,
            same_reset_policy_forks_feasible=True,
        )


def audit_red_living_dex_causal_capacity(
    assignments: tuple[RedLivingDexCausalCapacityAssignment, ...],
    *,
    design: LivingDexCausalCurriculumDesign | None = None,
) -> LivingDexCausalCapacityAudit:
    """Project Red facts, then run the shared path-free capacity audit."""

    if not isinstance(assignments, tuple) or any(
        not isinstance(item, RedLivingDexCausalCapacityAssignment) for item in assignments
    ):
        raise TypeError("Red causal capacity assignments differ")
    return audit_living_dex_causal_capacity(
        tuple(item.shared_context() for item in assignments),
        design=design,
    )


__all__ = [
    "RedLivingDexCausalCapacityAssignment",
    "RedLivingDexCausalCapacityError",
    "audit_red_living_dex_causal_capacity",
]
