"""Bind the full Red Pokédex inventory to authenticated executable goals.

The 151-entry inventory is the authority for whether a registration is still
missing.  Goal profiles and their runtime bindings are only the authority for
what this exact cartridge state can execute.  This module joins those facts
without exposing species, source, profile, or binding identity to the policy.
"""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.red_acquisition import (
    RED_ACQUISITION_CATALOG,
    RedAcquisitionCatalog,
    RedAcquisitionKind,
)
from pokemon_red_completion.red_collection import red_species_number, red_species_ref
from pokemon_red_completion.red_full_pokedex import (
    RedFullPokedexInventory,
    RedFullPokedexResolutionKind,
)
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfile,
    RedGoalMechanic,
    RedGoalProviderSpec,
)


class RedFullPokedexGoalProposalError(ValueError):
    """The authenticated context cannot produce a diverse full-Pokédex menu."""


@dataclass(frozen=True, slots=True)
class RedFullPokedexGoalCandidate:
    """One private executable and the exact missing registrations it can advance."""

    acquisition_kind: RedAcquisitionKind
    option_kind: LivingDexOptionKind
    target_numbers: tuple[int, ...]
    binding: ExecutableGoalBinding

    def __post_init__(self) -> None:
        if not isinstance(self.acquisition_kind, RedAcquisitionKind):
            raise TypeError("acquisition_kind must be a RedAcquisitionKind")
        if not isinstance(self.option_kind, LivingDexOptionKind):
            raise TypeError("option_kind must be a LivingDexOptionKind")
        if not isinstance(self.binding, ExecutableGoalBinding):
            raise TypeError("binding must be an ExecutableGoalBinding")
        if (
            not self.target_numbers
            or tuple(sorted(set(self.target_numbers))) != self.target_numbers
            or any(
                type(number) is not int or not 1 <= number <= 151
                for number in self.target_numbers
            )
        ):
            raise RedFullPokedexGoalProposalError(
                "proposal targets must be unique ordered Red Pokédex numbers"
            )
        expected = (
            (GoalKind.ACQUIRE_SPECIES, LivingDexOptionKind.ACQUIRE)
            if self.acquisition_kind is RedAcquisitionKind.WILD
            else (GoalKind.EVOLVE_SPECIES, LivingDexOptionKind.EVOLVE)
            if self.acquisition_kind is RedAcquisitionKind.EVOLUTION
            else None
        )
        if expected is None or (self.binding.kind, self.option_kind) != expected:
            raise RedFullPokedexGoalProposalError(
                "acquisition family, executable goal, and portable option kind differ"
            )


@dataclass(frozen=True, slots=True)
class RedFullPokedexGoalProposal:
    """A policy-safe action-free gate over private full-Pokédex executors."""

    candidates: tuple[RedFullPokedexGoalCandidate, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.candidates, tuple)
            or any(
                not isinstance(candidate, RedFullPokedexGoalCandidate)
                for candidate in self.candidates
            )
        ):
            raise TypeError("proposal candidates differ")
        if len({candidate.binding.binding_ref for candidate in self.candidates}) != len(
            self.candidates
        ):
            raise RedFullPokedexGoalProposalError("proposal executors are duplicated")
        if self.acquisition_family_count < 2:
            raise RedFullPokedexGoalProposalError(
                "full-Pokédex proposal needs at least two executable acquisition families"
            )

    @property
    def acquisition_family_count(self) -> int:
        return len({candidate.acquisition_kind for candidate in self.candidates})

    def public_dict(self) -> dict[str, object]:
        """Expose diversity and authority, never private target or routing identity."""

        return {
            "schema": "pokemon.red.full-pokedex-goal-proposal.v1",
            "candidate_count": len(self.candidates),
            "acquisition_family_count": self.acquisition_family_count,
            "portable_option_kinds": sorted(
                {candidate.option_kind.value for candidate in self.candidates}
            ),
            "all_executors_profile_bound": True,
            "completion_authority": "local_red_registration_flags",
            "identity_fields_public": 0,
            "controller_actions": 0,
            "emulator_frames": 0,
        }


def _binding_for(
    profile: RedGoalContextProfile,
    spec: RedGoalProviderSpec,
    bindings: GoalBindingSet,
) -> ExecutableGoalBinding | None:
    matches = tuple(binding for binding in bindings.bindings if binding.kind is spec.kind)
    if not matches:
        return None
    if len(matches) != 1:
        raise RedFullPokedexGoalProposalError(
            "full-Pokédex goal kind has ambiguous executable bindings"
        )
    binding = matches[0]
    expected_suffix = (
        f":profile-{profile.profile_sha256}:config-{spec.configuration_sha256}"
    )
    if not binding.binding_ref.endswith(expected_suffix):
        raise RedFullPokedexGoalProposalError(
            "full-Pokédex executable is not authenticated by its profile declaration"
        )
    return binding


def _wild_candidate(
    inventory: RedFullPokedexInventory,
    profile: RedGoalContextProfile,
    spec: RedGoalProviderSpec,
    bindings: GoalBindingSet,
    catalog: RedAcquisitionCatalog,
) -> RedFullPokedexGoalCandidate | None:
    source_id = spec.parameters.get("source_id")
    if not isinstance(source_id, str):
        raise RedFullPokedexGoalProposalError("wild goal lacks a source identity")
    methods = catalog.methods_at_source(source_id)
    if any(method.kind is not RedAcquisitionKind.WILD for method in methods):
        raise RedFullPokedexGoalProposalError(
            "wild goal source contains a different acquisition family"
        )
    target_numbers = tuple(
        sorted(
            red_species_number(method.species_ref)
            for method in methods
            if not inventory.target(red_species_number(method.species_ref)).locally_registered
            and inventory.target(red_species_number(method.species_ref)).resolution_kind
            is RedFullPokedexResolutionKind.SOLO_CATALOG_PLAN
        )
    )
    if not target_numbers:
        return None
    binding = _binding_for(profile, spec, bindings)
    if binding is None:
        return None
    return RedFullPokedexGoalCandidate(
        RedAcquisitionKind.WILD,
        LivingDexOptionKind.ACQUIRE,
        target_numbers,
        binding,
    )


def _evolution_candidate(
    inventory: RedFullPokedexInventory,
    profile: RedGoalContextProfile,
    spec: RedGoalProviderSpec,
    bindings: GoalBindingSet,
    catalog: RedAcquisitionCatalog,
) -> RedFullPokedexGoalCandidate | None:
    if spec.mechanic is RedGoalMechanic.DIGLETT_EVOLUTION:
        source_ref, target_ref = red_species_ref(50), red_species_ref(51)
    else:
        source_value = spec.parameters.get("source_species_ref")
        target_value = spec.parameters.get("target_species_ref")
        if not isinstance(source_value, str) or not isinstance(target_value, str):
            raise RedFullPokedexGoalProposalError(
                "targeted evolution lacks exact source and target identity"
            )
        source_ref, target_ref = source_value, target_value
    try:
        method = catalog.method_for(target_ref)
    except ValueError as error:
        raise RedFullPokedexGoalProposalError(
            "evolution target is absent from the pinned Red acquisition graph"
        ) from error
    if (
        method.kind is not RedAcquisitionKind.EVOLUTION
        or method.consumes_species_ref != source_ref
    ):
        raise RedFullPokedexGoalProposalError(
            "evolution goal differs from the pinned Red acquisition graph"
        )
    source_number = red_species_number(source_ref)
    target_number = red_species_number(target_ref)
    target = inventory.target(target_number)
    if (
        target.locally_registered
        or target.resolution_kind is not RedFullPokedexResolutionKind.SOLO_CATALOG_PLAN
        or not inventory.target(source_number).physical_specimen_present
    ):
        return None
    binding = _binding_for(profile, spec, bindings)
    if binding is None:
        return None
    return RedFullPokedexGoalCandidate(
        RedAcquisitionKind.EVOLUTION,
        LivingDexOptionKind.EVOLVE,
        (target_number,),
        binding,
    )


def propose_red_full_pokedex_goals(
    inventory: RedFullPokedexInventory,
    profile: RedGoalContextProfile,
    bindings: GoalBindingSet,
    *,
    catalog: RedAcquisitionCatalog = RED_ACQUISITION_CATALOG,
) -> RedFullPokedexGoalProposal:
    """Join locally missing targets to this state's authenticated executors.

    Only the currently implemented wild-capture and level-evolution families
    are admitted.  External trades, gifts, fishing, Safari, fossils, prizes,
    and static encounters remain absent until they have their own authenticated
    goal executors.
    """

    if not isinstance(inventory, RedFullPokedexInventory):
        raise TypeError("inventory must be a RedFullPokedexInventory")
    if not isinstance(profile, RedGoalContextProfile):
        raise TypeError("profile must be a RedGoalContextProfile")
    if not isinstance(bindings, GoalBindingSet):
        raise TypeError("bindings must be a GoalBindingSet")
    if not isinstance(catalog, RedAcquisitionCatalog):
        raise TypeError("catalog must be a RedAcquisitionCatalog")

    candidates: list[RedFullPokedexGoalCandidate] = []
    for spec in profile.providers:
        if spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE:
            candidate = _wild_candidate(inventory, profile, spec, bindings, catalog)
        elif spec.mechanic in {
            RedGoalMechanic.DIGLETT_EVOLUTION,
            RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
        }:
            candidate = _evolution_candidate(
                inventory, profile, spec, bindings, catalog
            )
        else:
            continue
        if candidate is not None:
            candidates.append(candidate)
    return RedFullPokedexGoalProposal(tuple(candidates))


__all__ = [
    "RedFullPokedexGoalCandidate",
    "RedFullPokedexGoalProposal",
    "RedFullPokedexGoalProposalError",
    "propose_red_full_pokedex_goals",
]
