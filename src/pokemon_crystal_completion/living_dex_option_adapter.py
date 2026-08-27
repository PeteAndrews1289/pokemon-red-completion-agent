"""ROM-free Crystal projection into the shared living-Dex option contract.

This module is intentionally not a Crystal executor.  It consumes the typed
semantic snapshot produced by the revision-specific reader, maps its portable
goal pressures through the same core function Red uses, and converts
adapter-private mechanic requirements into a hard availability mask.  Species,
map, route, item, time, egg, and trade identities remain in ``binding_ref`` and
never enter the learner-facing menu.
"""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_crystal_completion.goal_state import (
    CrystalCampaignSnapshot,
    CrystalCapability,
    project_crystal_goal_state,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionKind,
    LivingDexOptionMenu,
    LivingDexOptionUnavailableReason,
    living_dex_option_context_from_goal_situation,
    living_dex_option_features_from_semantic_facts,
)


class CrystalLivingDexOptionAdapterError(ValueError):
    """Typed Crystal facts cannot produce an honest generic option menu."""


@dataclass(frozen=True, slots=True)
class CrystalLivingDexOptionProspect:
    """Typed prospective Crystal facts beside one private mechanic binding."""

    binding_ref: str
    kind: LivingDexOptionKind
    completion_units: int
    maximum_completion_units: int
    immediate_dependency_unlocks: int
    incomplete_dependency_frontier: int
    travel_action_estimate: int
    execution_action_estimate: int
    maximum_controller_actions: int
    required_resource_units: int
    available_resource_units: int
    net_storage_slots: int
    party_risk: float
    irreversible_constraints_exposed: int
    irreversible_constraint_count: int
    prerequisite_confidence: float
    required_capabilities: frozenset[CrystalCapability] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.binding_ref, str) or not self.binding_ref:
            raise CrystalLivingDexOptionAdapterError(
                "Crystal option needs a private binding reference"
            )
        if not isinstance(self.kind, LivingDexOptionKind):
            raise CrystalLivingDexOptionAdapterError(
                "Crystal option kind differs"
            )
        if not isinstance(self.required_capabilities, frozenset) or any(
            not isinstance(item, CrystalCapability)
            for item in self.required_capabilities
        ):
            raise CrystalLivingDexOptionAdapterError(
                "Crystal option capabilities must be a typed frozenset"
            )
        try:
            living_dex_option_features_from_semantic_facts(
                kind=self.kind,
                completion_units=self.completion_units,
                maximum_completion_units=self.maximum_completion_units,
                immediate_dependency_unlocks=self.immediate_dependency_unlocks,
                incomplete_dependency_frontier=self.incomplete_dependency_frontier,
                travel_action_estimate=self.travel_action_estimate,
                execution_action_estimate=self.execution_action_estimate,
                maximum_controller_actions=self.maximum_controller_actions,
                required_resource_units=self.required_resource_units,
                available_resource_units=self.available_resource_units,
                net_storage_slots=self.net_storage_slots,
                storage_headroom=1,
                party_risk=self.party_risk,
                irreversible_constraints_exposed=(
                    self.irreversible_constraints_exposed
                ),
                irreversible_constraint_count=self.irreversible_constraint_count,
                prerequisite_confidence=self.prerequisite_confidence,
            )
        except (TypeError, ValueError) as error:
            raise CrystalLivingDexOptionAdapterError(str(error)) from None


def project_crystal_living_dex_option_menu(
    snapshot: CrystalCampaignSnapshot,
    prospects: tuple[CrystalLivingDexOptionProspect, ...],
) -> LivingDexOptionMenu:
    """Build one complete generic menu without executing a Crystal mechanic."""

    if not isinstance(snapshot, CrystalCampaignSnapshot):
        raise TypeError("Crystal option projection needs a campaign snapshot")
    if (
        not isinstance(prospects, tuple)
        or len(prospects) < 2
        or any(
            not isinstance(item, CrystalLivingDexOptionProspect)
            for item in prospects
        )
        or len({item.binding_ref for item in prospects}) != len(prospects)
    ):
        raise CrystalLivingDexOptionAdapterError(
            "Crystal option projection needs distinct typed prospects"
        )
    observation = project_crystal_goal_state(snapshot)
    context = living_dex_option_context_from_goal_situation(
        observation.situation
    )
    candidates = tuple(
        _candidate(prospect, snapshot=snapshot) for prospect in prospects
    )
    try:
        return LivingDexOptionMenu(context, candidates)
    except (TypeError, ValueError) as error:
        raise CrystalLivingDexOptionAdapterError(str(error)) from None


def _candidate(
    prospect: CrystalLivingDexOptionProspect,
    *,
    snapshot: CrystalCampaignSnapshot,
) -> LivingDexOptionCandidate:
    required = prospect.required_capabilities
    known_missing = required & snapshot.capabilities.unavailable
    unresolved = required & snapshot.capabilities.unknown
    if known_missing:
        availability = LivingDexOptionAvailability.UNAVAILABLE
        reason = LivingDexOptionUnavailableReason.MISSING_CAPABILITY
    elif unresolved:
        availability = LivingDexOptionAvailability.UNKNOWN
        reason = LivingDexOptionUnavailableReason.WORLD_STATE_UNKNOWN
    elif prospect.required_resource_units > prospect.available_resource_units:
        availability = LivingDexOptionAvailability.UNAVAILABLE
        reason = LivingDexOptionUnavailableReason.MISSING_RESOURCE
    elif prospect.net_storage_slots > snapshot.free_storage_slots:
        availability = LivingDexOptionAvailability.UNAVAILABLE
        reason = LivingDexOptionUnavailableReason.STORAGE_BLOCKED
    else:
        availability = LivingDexOptionAvailability.AVAILABLE
        reason = None
    features = living_dex_option_features_from_semantic_facts(
        kind=prospect.kind,
        completion_units=prospect.completion_units,
        maximum_completion_units=prospect.maximum_completion_units,
        immediate_dependency_unlocks=prospect.immediate_dependency_unlocks,
        incomplete_dependency_frontier=prospect.incomplete_dependency_frontier,
        travel_action_estimate=prospect.travel_action_estimate,
        execution_action_estimate=prospect.execution_action_estimate,
        maximum_controller_actions=prospect.maximum_controller_actions,
        required_resource_units=prospect.required_resource_units,
        available_resource_units=prospect.available_resource_units,
        net_storage_slots=prospect.net_storage_slots,
        storage_headroom=snapshot.free_storage_slots,
        party_risk=prospect.party_risk,
        irreversible_constraints_exposed=prospect.irreversible_constraints_exposed,
        irreversible_constraint_count=prospect.irreversible_constraint_count,
        prerequisite_confidence=prospect.prerequisite_confidence,
    )
    return LivingDexOptionCandidate(
        prospect.binding_ref,
        features,
        availability,
        reason,
    )


__all__ = [
    "CrystalLivingDexOptionAdapterError",
    "CrystalLivingDexOptionProspect",
    "project_crystal_living_dex_option_menu",
]
