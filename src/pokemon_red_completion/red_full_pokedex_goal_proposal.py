"""Bind the full Red Pokédex inventory to authenticated executable goals.

The 151-entry inventory is the authority for whether a registration is still
missing.  Goal profiles and their runtime bindings are only the authority for
what this exact cartridge state can execute.  This module joins those facts
without exposing species, source, profile, or binding identity to the policy.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from functools import partial
from typing import cast

from pokemon_red_completion.executor import CountingExecutor, FrameBudgetController
from pokemon_red_completion.gen1_field_moves import Gen1FieldMovePort
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
from pokemon_red_completion.gen1_trainer_sight import Gen1TrainerSightProjector
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOptionKind,
    living_dex_option_context_from_goal_situation,
)
from pokemon_red_completion.red_acquisition import (
    RED_ACQUISITION_CATALOG,
    RedAcquisitionCatalog,
    RedAcquisitionKind,
    summarize_red_area_survey,
)
from pokemon_red_completion.red_bounded_player import RedBoundedPlayerObserver
from pokemon_red_completion.red_collection import red_species_number, red_species_ref
from pokemon_red_completion.red_full_pokedex import (
    RedFullPokedexInventory,
    RedFullPokedexResolutionKind,
    build_red_full_pokedex_inventory,
)
from pokemon_red_completion.red_goal_context import RedGoalContextRuntime
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic,
    RedGoalProviderSpec,
)
from pokemon_red_completion.red_goal_manager import RedGoalObservation
from pokemon_red_completion.red_goal_skills import RedAreaSurveyGoalProvider
from pokemon_red_completion.red_live_fishing import (
    RedLiveFishingInventory,
    build_red_live_fishing_inventory,
)
from pokemon_red_completion.red_native_boxed_evolution import bind_native_boxed_evolution
from pokemon_red_completion.red_registration_policy import RedRegistrationPolicy
from pokemon_red_completion.red_resource_goal_router import (
    RedResourceGoalRouter,
    collection_field_capabilities,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


class RedFullPokedexFamilyReason(StrEnum):
    """Identity-free reason one supported acquisition family is excluded."""

    READY = "ready"
    PROFILE_DECLARATION_MISSING = "profile_declaration_missing"
    TARGET_ALREADY_REGISTERED = "target_already_registered"
    NO_SOLO_CATALOG_TARGET = "no_solo_catalog_target"
    NO_MISSING_EXECUTABLE_TARGET = "no_missing_executable_target"
    PHYSICAL_PRECURSOR_MISSING = "physical_precursor_missing"
    PHYSICAL_PRECURSOR_PROTECTED = "physical_precursor_protected"
    ROUTER_BINDING_UNAVAILABLE = "router_binding_unavailable"


@dataclass(frozen=True, slots=True)
class RedFullPokedexFamilyDiagnostic:
    """Portable failure evidence with all target and routing identity removed."""

    acquisition_kind: RedAcquisitionKind
    reason: RedFullPokedexFamilyReason
    router_unavailable_reasons: tuple[GoalUnavailableReason, ...] = ()

    def __post_init__(self) -> None:
        if self.acquisition_kind not in {
            RedAcquisitionKind.WILD,
            RedAcquisitionKind.FISHING,
            RedAcquisitionKind.EVOLUTION,
        }:
            raise ValueError("diagnostic acquisition family is unsupported")
        if not isinstance(self.reason, RedFullPokedexFamilyReason):
            raise TypeError("diagnostic reason differs")
        if (
            not isinstance(self.router_unavailable_reasons, tuple)
            or any(
                not isinstance(reason, GoalUnavailableReason)
                for reason in self.router_unavailable_reasons
            )
            or tuple(sorted(set(self.router_unavailable_reasons), key=lambda reason: reason.value))
            != self.router_unavailable_reasons
        ):
            raise ValueError("router unavailable reasons differ")
        if self.reason is RedFullPokedexFamilyReason.READY and self.router_unavailable_reasons:
            raise ValueError("ready diagnostic cannot carry router failures")
        if (
            self.reason is RedFullPokedexFamilyReason.ROUTER_BINDING_UNAVAILABLE
            and not self.router_unavailable_reasons
        ):
            raise ValueError("router diagnostic needs an unavailable reason")

    @property
    def option_kind(self) -> LivingDexOptionKind:
        return (
            LivingDexOptionKind.ACQUIRE
            if self.acquisition_kind in {RedAcquisitionKind.WILD, RedAcquisitionKind.FISHING}
            else LivingDexOptionKind.EVOLVE
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.full-pokedex-family-diagnostic.v1",
            "portable_option_kind": self.option_kind.value,
            "availability": (
                GoalAvailability.AVAILABLE.value
                if self.reason is RedFullPokedexFamilyReason.READY
                else GoalAvailability.UNAVAILABLE.value
            ),
            "reason": self.reason.value,
            "router_unavailable_reasons": [
                reason.value for reason in self.router_unavailable_reasons
            ],
            "identity_fields_public": 0,
        }


class RedFullPokedexGoalProposalError(ValueError):
    """The authenticated context cannot produce a diverse full-Pokédex menu."""

    def __init__(
        self,
        message: str,
        *,
        family_diagnostics: tuple[RedFullPokedexFamilyDiagnostic, ...] = (),
    ) -> None:
        super().__init__(message)
        if not isinstance(family_diagnostics, tuple) or any(
            not isinstance(diagnostic, RedFullPokedexFamilyDiagnostic)
            for diagnostic in family_diagnostics
        ):
            raise TypeError("family diagnostics differ")
        self.family_diagnostics = family_diagnostics

    def public_family_diagnostics(self) -> list[dict[str, object]]:
        return [diagnostic.public_dict() for diagnostic in self.family_diagnostics]


@dataclass(slots=True)
class RedFullPokedexPlayerAttempt:
    """Episode-scoped authority shared by freshly gated observer instances."""

    attempted: bool = False


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
                type(number) is not int or not 1 <= number <= 151 for number in self.target_numbers
            )
        ):
            raise RedFullPokedexGoalProposalError(
                "proposal targets must be unique ordered Red Pokédex numbers"
            )
        expected = (
            (GoalKind.ACQUIRE_SPECIES, LivingDexOptionKind.ACQUIRE)
            if self.acquisition_kind in {RedAcquisitionKind.WILD, RedAcquisitionKind.FISHING}
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
    binding_set: GoalBindingSet
    family_diagnostics: tuple[RedFullPokedexFamilyDiagnostic, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.candidates, tuple) or any(
            not isinstance(candidate, RedFullPokedexGoalCandidate) for candidate in self.candidates
        ):
            raise TypeError("proposal candidates differ")
        if not isinstance(self.binding_set, GoalBindingSet) or any(
            not any(candidate.binding is binding for binding in self.binding_set.bindings)
            for candidate in self.candidates
        ):
            raise RedFullPokedexGoalProposalError("proposal differs from its player bindings")
        if len({candidate.binding.binding_ref for candidate in self.candidates}) != len(
            self.candidates
        ):
            raise RedFullPokedexGoalProposalError("proposal executors are duplicated")
        if (
            not isinstance(self.family_diagnostics, tuple)
            or any(
                not isinstance(diagnostic, RedFullPokedexFamilyDiagnostic)
                for diagnostic in self.family_diagnostics
            )
            or tuple(diagnostic.acquisition_kind for diagnostic in self.family_diagnostics)
            not in {
                (RedAcquisitionKind.WILD, RedAcquisitionKind.EVOLUTION),
                (RedAcquisitionKind.FISHING, RedAcquisitionKind.EVOLUTION),
            }
        ):
            raise RedFullPokedexGoalProposalError("proposal family diagnostics differ")
        if {
            diagnostic.acquisition_kind
            for diagnostic in self.family_diagnostics
            if diagnostic.reason is RedFullPokedexFamilyReason.READY
        } != {candidate.acquisition_kind for candidate in self.candidates}:
            raise RedFullPokedexGoalProposalError(
                "proposal candidate and diagnostic availability differ"
            )
        if self.acquisition_family_count < 2:
            raise RedFullPokedexGoalProposalError(
                "full-Pokédex proposal needs at least two executable acquisition families",
                family_diagnostics=self.family_diagnostics,
            )

    @property
    def acquisition_family_count(self) -> int:
        return len({candidate.acquisition_kind for candidate in self.candidates})

    def public_dict(self) -> dict[str, object]:
        """Expose diversity and authority, never private target or routing identity."""

        return {
            "schema": "pokemon.red.full-pokedex-goal-proposal.v3",
            "candidate_count": len(self.candidates),
            "player_binding_count": len(self.binding_set.bindings),
            "acquisition_family_count": self.acquisition_family_count,
            "portable_option_kinds": sorted(
                {candidate.option_kind.value for candidate in self.candidates}
            ),
            "family_diagnostics": [
                diagnostic.public_dict() for diagnostic in self.family_diagnostics
            ],
            "binding_authority": "live_resource_goal_router",
            "completion_authority": "local_red_registration_flags",
            "identity_fields_public": 0,
            "controller_actions": 0,
            "emulator_frames": 0,
        }


def _binding_for(
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
    return matches[0]


def _router_unavailable_reasons(
    kind: GoalKind,
    bindings: GoalBindingSet,
) -> tuple[GoalUnavailableReason, ...]:
    return tuple(
        sorted(
            {
                opportunity.unavailable_reason
                for opportunity in bindings.opportunities
                if opportunity.kind is kind
                and opportunity.availability is not GoalAvailability.AVAILABLE
                and opportunity.unavailable_reason is not None
            },
            key=lambda reason: reason.value,
        )
    )


def _wild_candidate(
    inventory: RedFullPokedexInventory,
    spec: RedGoalProviderSpec,
    bindings: GoalBindingSet,
    catalog: RedAcquisitionCatalog,
    executable_targets: frozenset[str],
) -> tuple[RedFullPokedexGoalCandidate | None, RedFullPokedexFamilyDiagnostic]:
    source_id = spec.parameters.get("source_id")
    if not isinstance(source_id, str):
        raise RedFullPokedexGoalProposalError("wild goal lacks a source identity")
    methods = catalog.methods_at_source(source_id)
    if any(method.kind is not RedAcquisitionKind.WILD for method in methods):
        raise RedFullPokedexGoalProposalError(
            "wild goal source contains a different acquisition family"
        )
    eligible_methods = tuple(
        method
        for method in methods
        if not inventory.target(red_species_number(method.species_ref)).locally_registered
        and inventory.target(red_species_number(method.species_ref)).resolution_kind
        is RedFullPokedexResolutionKind.SOLO_CATALOG_PLAN
    )
    if not eligible_methods:
        reason = (
            RedFullPokedexFamilyReason.TARGET_ALREADY_REGISTERED
            if methods
            and all(
                inventory.target(red_species_number(method.species_ref)).locally_registered
                for method in methods
            )
            else RedFullPokedexFamilyReason.NO_SOLO_CATALOG_TARGET
        )
        return None, RedFullPokedexFamilyDiagnostic(RedAcquisitionKind.WILD, reason)
    target_numbers = tuple(
        sorted(
            {
                red_species_number(method.species_ref)
                for method in eligible_methods
                if method.species_ref in executable_targets
            }
        )
    )
    if not target_numbers:
        return None, RedFullPokedexFamilyDiagnostic(
            RedAcquisitionKind.WILD,
            RedFullPokedexFamilyReason.NO_MISSING_EXECUTABLE_TARGET,
        )
    binding = _binding_for(spec, bindings)
    if binding is None:
        return None, RedFullPokedexFamilyDiagnostic(
            RedAcquisitionKind.WILD,
            RedFullPokedexFamilyReason.ROUTER_BINDING_UNAVAILABLE,
            _router_unavailable_reasons(GoalKind.ACQUIRE_SPECIES, bindings),
        )
    return (
        RedFullPokedexGoalCandidate(
            RedAcquisitionKind.WILD,
            LivingDexOptionKind.ACQUIRE,
            target_numbers,
            binding,
        ),
        RedFullPokedexFamilyDiagnostic(RedAcquisitionKind.WILD, RedFullPokedexFamilyReason.READY),
    )


def _evolution_candidate(
    inventory: RedFullPokedexInventory,
    spec: RedGoalProviderSpec,
    bindings: GoalBindingSet,
    catalog: RedAcquisitionCatalog,
    observation: RedGoalObservation,
    policy: RedRegistrationPolicy,
) -> tuple[RedFullPokedexGoalCandidate | None, RedFullPokedexFamilyDiagnostic]:
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
    if method.kind is not RedAcquisitionKind.EVOLUTION or method.consumes_species_ref != source_ref:
        raise RedFullPokedexGoalProposalError(
            "evolution goal differs from the pinned Red acquisition graph"
        )
    source_number = red_species_number(source_ref)
    target_number = red_species_number(target_ref)
    target = inventory.target(target_number)
    if target.locally_registered:
        return None, RedFullPokedexFamilyDiagnostic(
            RedAcquisitionKind.EVOLUTION,
            RedFullPokedexFamilyReason.TARGET_ALREADY_REGISTERED,
        )
    if target.resolution_kind is not RedFullPokedexResolutionKind.SOLO_CATALOG_PLAN:
        return None, RedFullPokedexFamilyDiagnostic(
            RedAcquisitionKind.EVOLUTION,
            RedFullPokedexFamilyReason.NO_SOLO_CATALOG_TARGET,
        )
    if not inventory.target(source_number).physical_specimen_present:
        return None, RedFullPokedexFamilyDiagnostic(
            RedAcquisitionKind.EVOLUTION,
            RedFullPokedexFamilyReason.PHYSICAL_PRECURSOR_MISSING,
            _router_unavailable_reasons(GoalKind.EVOLVE_SPECIES, bindings),
        )
    if not policy.evolution_allowed(observation.collection_observation, source_ref, target_ref):
        return None, RedFullPokedexFamilyDiagnostic(
            RedAcquisitionKind.EVOLUTION,
            RedFullPokedexFamilyReason.PHYSICAL_PRECURSOR_PROTECTED,
            _router_unavailable_reasons(GoalKind.EVOLVE_SPECIES, bindings),
        )
    binding = _binding_for(spec, bindings)
    if binding is None:
        return None, RedFullPokedexFamilyDiagnostic(
            RedAcquisitionKind.EVOLUTION,
            RedFullPokedexFamilyReason.ROUTER_BINDING_UNAVAILABLE,
            _router_unavailable_reasons(GoalKind.EVOLVE_SPECIES, bindings),
        )
    return (
        RedFullPokedexGoalCandidate(
            RedAcquisitionKind.EVOLUTION,
            LivingDexOptionKind.EVOLVE,
            (target_number,),
            binding,
        ),
        RedFullPokedexFamilyDiagnostic(
            RedAcquisitionKind.EVOLUTION, RedFullPokedexFamilyReason.READY
        ),
    )


def _fishing_candidate(
    inventory: RedFullPokedexInventory,
    fishing: RedLiveFishingInventory,
    catalog: RedAcquisitionCatalog,
) -> tuple[RedFullPokedexGoalCandidate | None, RedFullPokedexFamilyDiagnostic]:
    """Bind the best reachable cartridge fishing destination as acquisition."""

    if not fishing.destinations:
        return None, RedFullPokedexFamilyDiagnostic(
            RedAcquisitionKind.FISHING,
            RedFullPokedexFamilyReason.NO_MISSING_EXECUTABLE_TARGET,
        )
    if len(fishing.destinations) != 1 or len(fishing.supplements) != 1:
        raise RedFullPokedexGoalProposalError(
            "full-Pokédex fishing fallback needs one ranked destination"
        )
    destination = fishing.destinations[0]
    supplement = fishing.supplements[0]
    target_numbers = tuple(
        number
        for number in destination.offer.missing_species_numbers
        if not inventory.target(number).locally_registered
        and inventory.target(number).resolution_kind
        is RedFullPokedexResolutionKind.SOLO_CATALOG_PLAN
        and catalog.method_for(red_species_ref(number)).kind is RedAcquisitionKind.FISHING
    )
    if not target_numbers:
        return None, RedFullPokedexFamilyDiagnostic(
            RedAcquisitionKind.FISHING,
            RedFullPokedexFamilyReason.NO_MISSING_EXECUTABLE_TARGET,
        )
    if (
        supplement.binding.kind is not GoalKind.ACQUIRE_SPECIES
        or supplement.candidate.features.kind is not LivingDexOptionKind.ACQUIRE
    ):
        raise RedFullPokedexGoalProposalError(
            "fishing executor differs from its portable acquisition"
        )
    return (
        RedFullPokedexGoalCandidate(
            RedAcquisitionKind.FISHING,
            LivingDexOptionKind.ACQUIRE,
            target_numbers,
            supplement.binding,
        ),
        RedFullPokedexFamilyDiagnostic(
            RedAcquisitionKind.FISHING,
            RedFullPokedexFamilyReason.READY,
        ),
    )


def _propose_red_full_pokedex_goals(
    router: RedResourceGoalRouter,
    observation: RedGoalObservation,
    *,
    fishing_inventory: RedLiveFishingInventory | None = None,
) -> RedFullPokedexGoalProposal:
    """Build a same-departure menu through the actual registered runtime.

    Wild capture remains the preferred acquisition when it is executable. If it
    is not, one already-authenticated, ranked reachable fishing executor may
    supply the acquisition family. External trades, gifts, Safari, fossils,
    prizes, and static encounters remain absent until they have authenticated
    goal executors.

    This internal variant accepts the fishing inventory built by the live player
    observer. Public callers cannot supply bindings or inventories.
    """
    if not isinstance(router, RedResourceGoalRouter):
        raise TypeError("proposal requires the live Red resource router")
    if not isinstance(observation, RedGoalObservation):
        raise TypeError("proposal requires a Red goal observation")
    if fishing_inventory is not None and not isinstance(fishing_inventory, RedLiveFishingInventory):
        raise TypeError("proposal fishing inventory differs")
    runtime = router.runtime
    policy = runtime.registration_policy
    if policy is None or policy.completion_scope != "local_red":
        raise RedFullPokedexGoalProposalError("proposal requires explicit full-local Red policy")
    before = (router.actions.actions_executed, runtime.emulator.frame_count)
    profile = runtime.profile
    binding_identity = (profile.profile_sha256, policy.sha256)
    origin = (
        observation.raw,
        observation.collection_observation,
        observation.party,
        observation.game_state,
        observation.input_ready,
    )

    def require_origin() -> None:
        fresh = runtime.adapter.observe()
        if (
            (
                fresh.raw,
                fresh.collection_observation,
                fresh.party,
                fresh.game_state,
                fresh.input_ready,
            )
            != origin
            or (
                runtime.profile.profile_sha256,
                runtime.registration_policy.sha256
                if runtime.registration_policy is not None
                else None,
            )
            != binding_identity
            or (router.actions.actions_executed, runtime.emulator.frame_count) != before
        ):
            raise RedFullPokedexGoalProposalError("shared-departure state or policy changed")

    require_origin()
    current = observation.collection_observation
    inventory = build_red_full_pokedex_inventory(
        frozenset(map(red_species_number, current.owned_species)),
        shared_registered_numbers=frozenset(map(red_species_number, policy.registered(current))),
        physical_specimen_numbers=frozenset(
            red_species_number(s.species_ref) for s in current.specimens
        ),
    )
    bindings = router.enumerate(observation)
    candidates: list[RedFullPokedexGoalCandidate] = []
    diagnostics: dict[RedAcquisitionKind, RedFullPokedexFamilyDiagnostic] = {}
    for spec in profile.providers:
        if spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE:
            provider = runtime.provider_for(spec.kind, router.actions)
            if not isinstance(provider, RedAreaSurveyGoalProvider):
                raise RedFullPokedexGoalProposalError("wild runtime provider differs")
            targets = summarize_red_area_survey(
                provider.source_id,
                current,
                provider.catalog,
            ).missing_species_refs
            candidate, diagnostic = _wild_candidate(
                inventory,
                spec,
                bindings,
                RED_ACQUISITION_CATALOG,
                frozenset(targets),
            )
        elif spec.mechanic in {
            RedGoalMechanic.DIGLETT_EVOLUTION,
            RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
        }:
            candidate, diagnostic = _evolution_candidate(
                inventory, spec, bindings, RED_ACQUISITION_CATALOG, observation, policy
            )
        else:
            continue
        diagnostics[diagnostic.acquisition_kind] = diagnostic
        if candidate is not None:
            candidates.append(candidate)
    acquisition_kind = RedAcquisitionKind.WILD
    if (
        not any(candidate.acquisition_kind is RedAcquisitionKind.WILD for candidate in candidates)
        and fishing_inventory is not None
    ):
        fishing_candidate, fishing_diagnostic = _fishing_candidate(
            inventory, fishing_inventory, RED_ACQUISITION_CATALOG
        )
        if fishing_candidate is not None:
            acquisition_kind = RedAcquisitionKind.FISHING
            diagnostics[acquisition_kind] = fishing_diagnostic
            candidates.append(fishing_candidate)
            fishing_binding = fishing_candidate.binding
            bindings = GoalBindingSet(
                tuple(
                    fishing_binding.opportunity
                    if opportunity.kind is GoalKind.ACQUIRE_SPECIES
                    else opportunity
                    for opportunity in bindings.opportunities
                ),
                tuple(
                    binding
                    for binding in bindings.bindings
                    if binding.kind is not GoalKind.ACQUIRE_SPECIES
                )
                + (fishing_binding,),
                allow_resource_variants=bindings.allow_resource_variants,
            )
    for diagnostic_kind in (RedAcquisitionKind.WILD, RedAcquisitionKind.EVOLUTION):
        diagnostics.setdefault(
            diagnostic_kind,
            RedFullPokedexFamilyDiagnostic(
                diagnostic_kind,
                RedFullPokedexFamilyReason.PROFILE_DECLARATION_MISSING,
            ),
        )
    require_origin()
    consumed = False

    def guard(binding: ExecutableGoalBinding) -> ExecutableGoalBinding:
        def execute() -> GoalExecutionReport:
            nonlocal consumed
            if consumed:
                raise RedFullPokedexGoalProposalError("shared-departure menu already consumed")
            consumed = True
            require_origin()
            return binding.execute()

        return replace(binding, execute=execute)

    guarded = {binding.binding_ref: guard(binding) for binding in bindings.bindings}
    return RedFullPokedexGoalProposal(
        tuple(
            replace(candidate, binding=guarded[candidate.binding.binding_ref])
            for candidate in candidates
        ),
        GoalBindingSet(
            bindings.opportunities,
            tuple(guarded.values()),
            allow_resource_variants=bindings.allow_resource_variants,
        ),
        tuple(diagnostics[kind] for kind in (acquisition_kind, RedAcquisitionKind.EVOLUTION)),
    )


def propose_red_full_pokedex_goals(
    router: RedResourceGoalRouter,
    observation: RedGoalObservation,
) -> RedFullPokedexGoalProposal:
    """Build the public same-departure proposal from router-owned bindings only.

    Arbitrary bindings and caller-supplied inventories are deliberately not
    inputs: a profile-shaped string cannot authenticate a callback or stale
    ledger.
    """

    return _propose_red_full_pokedex_goals(router, observation)


def build_red_full_pokedex_player_observer(
    runtime: RedGoalContextRuntime,
    actions: CountingExecutor,
    world: StrategicScenarioRouteWorld,
    *,
    maximum_quanta: int = 1,
    maximum_controller_actions: int = 6_000,
    maximum_emulator_frames: int = 600_000,
    retain_quantum: Callable[[], None] | None = None,
    quote_resource_costs: bool = False,
    attempt: RedFullPokedexPlayerAttempt | None = None,
) -> RedBoundedPlayerObserver:
    """Wire one mixed-family choice and subsequent read-only terminal observations.

    No policy choice or input occurs here. The caller retains decision/outcome
    durability and the primitive hard budget, as for every bounded player episode.
    This is opt-in; a shared/legacy checkpoint is never silently reinterpreted.
    """
    if (
        runtime.registration_policy is None
        or runtime.registration_policy.completion_scope != "local_red"
    ):
        raise RedFullPokedexGoalProposalError("player requires explicit full-local Red policy")
    if not any(
        spec.mechanic is RedGoalMechanic.TARGETED_LEVEL_EVOLUTION
        for spec in runtime.profile.providers
    ):
        raise RedFullPokedexGoalProposalError(
            "player requires a native level-evolution declaration",
        )
    runtime = replace(
        runtime,
        adapter=replace(
            runtime.adapter,
            registration_policy=runtime.registration_policy,
        ),
    )
    native = bind_native_boxed_evolution(
        runtime,
        world,
        maximum_quanta=maximum_quanta,
        allow_cross_box=True,
        retain_quantum=retain_quantum,
    )
    router = RedResourceGoalRouter(
        native,
        actions,
        world,
        quote_resource_costs=quote_resource_costs,
        maximum_controller_actions=maximum_controller_actions,
        maximum_emulator_frames=maximum_emulator_frames,
        include_recovery_offers=False,
    )
    attempt = attempt or RedFullPokedexPlayerAttempt()

    def execute_once(binding: ExecutableGoalBinding) -> GoalExecutionReport:
        if attempt.attempted:
            raise RedFullPokedexGoalProposalError("shared-departure episode already attempted")
        attempt.attempted = True
        return binding.execute()

    def enumerate_bindings(observation: RedGoalObservation) -> GoalBindingSet:
        if attempt.attempted:
            # A successful acquisition may remove one family. Never rerun the
            # admission gate while retaining its fresh terminal ledger, or hand
            # controller authority to a second choice from a terminal observer.
            return GoalBindingSet(
                tuple(
                    GoalOpportunity(
                        binding_ref=f"red-departure-episode-consumed:{kind.value}",
                        kind=kind,
                        availability=GoalAvailability.UNAVAILABLE,
                        unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
                    )
                    for kind in GoalKind
                ),
                (),
            )
        try:
            proposed = propose_red_full_pokedex_goals(router, observation).binding_set
        except RedFullPokedexGoalProposalError as first_error:
            diagnostics = first_error.family_diagnostics
            if not (
                len(diagnostics) == 2
                and diagnostics[0].acquisition_kind is RedAcquisitionKind.WILD
                and diagnostics[0].reason is not RedFullPokedexFamilyReason.READY
                and diagnostics[1].acquisition_kind is RedAcquisitionKind.EVOLUTION
                and diagnostics[1].reason is RedFullPokedexFamilyReason.READY
            ):
                raise
            controller = cast(FrameBudgetController, native.emulator)
            traversal_observer = Gen1TraversalObserver(
                native.reader,
                hazard_projector=Gen1TrainerSightProjector(world.rom, native.reader),
                capability_projector=partial(
                    collection_field_capabilities,
                    controller,
                    allow_cut=True,
                    allow_surf=True,
                ),
            )
            field = Gen1FieldMovePort(
                actions,
                native.reader,
                controller,
                cut_block_swaps={swap.before: swap.after for swap in world.rules.cut_block_swaps},
            )
            fishing = build_red_live_fishing_inventory(
                world.rom,
                frozenset(
                    red_species_number(species)
                    for species in observation.collection_observation.owned_species
                ),
                living_dex_option_context_from_goal_situation(observation.situation),
                free_storage_slots=observation.free_storage_slots,
                world=world,
                traversal=traversal_observer.observe(),
                observer=traversal_observer,
                field=field,
                controller=controller,
                actions=actions,
                reader=native.reader,
                emulator=controller,
                maximum_candidates=1,
            )
            proposed = _propose_red_full_pokedex_goals(
                router,
                observation,
                fishing_inventory=fishing,
            ).binding_set
        return GoalBindingSet(
            proposed.opportunities,
            tuple(
                replace(binding, execute=partial(execute_once, binding))
                for binding in proposed.bindings
            ),
            allow_resource_variants=proposed.allow_resource_variants,
        )

    return RedBoundedPlayerObserver(
        native,
        actions,
        registered_objective=True,
        enumerate_bindings=enumerate_bindings,
    )


__all__ = [
    "RedFullPokedexFamilyDiagnostic",
    "RedFullPokedexFamilyReason",
    "RedFullPokedexGoalCandidate",
    "RedFullPokedexGoalProposal",
    "RedFullPokedexGoalProposalError",
    "RedFullPokedexPlayerAttempt",
    "propose_red_full_pokedex_goals",
    "build_red_full_pokedex_player_observer",
]
