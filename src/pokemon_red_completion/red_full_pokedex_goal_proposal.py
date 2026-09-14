"""Bind the full Red Pokédex inventory to authenticated executable goals.

The 151-entry inventory is the authority for whether a registration is still
missing.  Goal profiles and their runtime bindings are only the authority for
what this exact cartridge state can execute.  This module joins those facts
without exposing species, source, profile, or binding identity to the policy.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import partial

from pokemon_red_completion.executor import CountingExecutor
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
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
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
from pokemon_red_completion.red_native_boxed_evolution import bind_native_boxed_evolution
from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


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
    binding_set: GoalBindingSet

    def __post_init__(self) -> None:
        if (
            not isinstance(self.candidates, tuple)
            or any(
                not isinstance(candidate, RedFullPokedexGoalCandidate)
                for candidate in self.candidates
            )
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
            "schema": "pokemon.red.full-pokedex-goal-proposal.v2",
            "candidate_count": len(self.candidates),
            "player_binding_count": len(self.binding_set.bindings),
            "acquisition_family_count": self.acquisition_family_count,
            "portable_option_kinds": sorted(
                {candidate.option_kind.value for candidate in self.candidates}
            ),
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


def _wild_candidate(
    inventory: RedFullPokedexInventory,
    spec: RedGoalProviderSpec,
    bindings: GoalBindingSet,
    catalog: RedAcquisitionCatalog,
    executable_targets: frozenset[str],
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
            and method.species_ref in executable_targets
            and inventory.target(red_species_number(method.species_ref)).resolution_kind
            is RedFullPokedexResolutionKind.SOLO_CATALOG_PLAN
        )
    )
    if not target_numbers:
        return None
    binding = _binding_for(spec, bindings)
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
    binding = _binding_for(spec, bindings)
    if binding is None:
        return None
    return RedFullPokedexGoalCandidate(
        RedAcquisitionKind.EVOLUTION,
        LivingDexOptionKind.EVOLVE,
        (target_number,),
        binding,
    )


def propose_red_full_pokedex_goals(
    router: RedResourceGoalRouter,
    observation: RedGoalObservation,
) -> RedFullPokedexGoalProposal:
    """Build a same-departure menu through the actual registered runtime.

    Only the currently implemented wild-capture and level-evolution families
    are admitted.  External trades, gifts, fishing, Safari, fossils, prizes,
    and static encounters remain absent until they have their own authenticated
    goal executors.

    Arbitrary bindings and caller-supplied inventories are deliberately not inputs:
    a profile-shaped string cannot authenticate a callback or a stale ledger.
    """
    if not isinstance(router, RedResourceGoalRouter):
        raise TypeError("proposal requires the live Red resource router")
    if not isinstance(observation, RedGoalObservation):
        raise TypeError("proposal requires a Red goal observation")
    runtime = router.runtime
    policy = runtime.registration_policy
    if policy is None or policy.completion_scope != "local_red":
        raise RedFullPokedexGoalProposalError("proposal requires explicit full-local Red policy")
    before = (router.actions.actions_executed, runtime.emulator.frame_count)
    profile = runtime.profile
    binding_identity = (profile.profile_sha256, policy.sha256)
    origin = (observation.raw, observation.collection_observation, observation.party,
              observation.game_state,
              observation.input_ready)

    def require_origin() -> None:
        fresh = runtime.adapter.observe()
        if ((fresh.raw, fresh.collection_observation, fresh.party, fresh.game_state,
             fresh.input_ready) != origin
                or (runtime.profile.profile_sha256, runtime.registration_policy.sha256
                    if runtime.registration_policy is not None else None) != binding_identity
                or (router.actions.actions_executed, runtime.emulator.frame_count) != before):
            raise RedFullPokedexGoalProposalError("shared-departure state or policy changed")

    require_origin()
    current = observation.collection_observation
    inventory = build_red_full_pokedex_inventory(
        frozenset(map(red_species_number, current.owned_species)),
        shared_registered_numbers=frozenset(map(red_species_number, policy.registered(current))),
        physical_specimen_numbers=frozenset(red_species_number(s.species_ref)
                                            for s in current.specimens),
    )
    bindings = router.enumerate(observation)
    candidates: list[RedFullPokedexGoalCandidate] = []
    for spec in profile.providers:
        if spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE:
            provider = runtime.provider_for(spec.kind, router.actions)
            if not isinstance(provider, RedAreaSurveyGoalProvider):
                raise RedFullPokedexGoalProposalError("wild runtime provider differs")
            targets = summarize_red_area_survey(
                provider.source_id, current, provider.catalog,
            ).missing_species_refs
            candidate = _wild_candidate(
                inventory, spec, bindings, RED_ACQUISITION_CATALOG, frozenset(targets),
            )
        elif spec.mechanic in {
            RedGoalMechanic.DIGLETT_EVOLUTION,
            RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
        }:
            candidate = _evolution_candidate(
                inventory, spec, bindings, RED_ACQUISITION_CATALOG
            )
        else:
            continue
        if candidate is not None:
            candidates.append(candidate)
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
        tuple(replace(candidate, binding=guarded[candidate.binding.binding_ref])
              for candidate in candidates),
        GoalBindingSet(bindings.opportunities, tuple(guarded.values()),
                       allow_resource_variants=bindings.allow_resource_variants),
    )


def build_red_full_pokedex_player_observer(
    runtime: RedGoalContextRuntime,
    actions: CountingExecutor,
    world: StrategicScenarioRouteWorld,
    *,
    maximum_quanta: int = 1,
    maximum_controller_actions: int = 6_000,
    maximum_emulator_frames: int = 600_000,
    retain_quantum: Callable[[], None] | None = None,
) -> RedBoundedPlayerObserver:
    """Wire one mixed-family choice and subsequent read-only terminal observations.

    No policy choice or input occurs here. The caller retains decision/outcome
    durability and the primitive hard budget, as for every bounded player episode.
    This is opt-in; a shared/legacy checkpoint is never silently reinterpreted.
    """
    if (runtime.registration_policy is None
            or runtime.registration_policy.completion_scope != "local_red"):
        raise RedFullPokedexGoalProposalError("player requires explicit full-local Red policy")
    if not any(spec.mechanic is RedGoalMechanic.TARGETED_LEVEL_EVOLUTION
               for spec in runtime.profile.providers):
        raise RedFullPokedexGoalProposalError(
            "player requires a native level-evolution declaration",
        )
    runtime = replace(runtime, adapter=replace(
        runtime.adapter, registration_policy=runtime.registration_policy,
    ))
    native = bind_native_boxed_evolution(
        runtime, world, maximum_quanta=maximum_quanta,
        allow_cross_box=True, retain_quantum=retain_quantum,
    )
    router = RedResourceGoalRouter(
        native, actions, world,
        maximum_controller_actions=maximum_controller_actions,
        maximum_emulator_frames=maximum_emulator_frames,
        include_recovery_offers=False,
    )
    attempted = False

    def execute_once(binding: ExecutableGoalBinding) -> GoalExecutionReport:
        nonlocal attempted
        if attempted:
            raise RedFullPokedexGoalProposalError("shared-departure episode already attempted")
        attempted = True
        return binding.execute()

    def enumerate_bindings(observation: RedGoalObservation) -> GoalBindingSet:
        if attempted:
            # A successful acquisition may remove one family. Never rerun the
            # admission gate while retaining its fresh terminal ledger, or hand
            # controller authority to a second choice from a terminal observer.
            return GoalBindingSet(tuple(
                GoalOpportunity(
                    binding_ref=f"red-departure-episode-consumed:{kind.value}",
                    kind=kind, availability=GoalAvailability.UNAVAILABLE,
                    unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
                ) for kind in GoalKind
            ), ())
        proposed = propose_red_full_pokedex_goals(router, observation).binding_set
        return GoalBindingSet(
            proposed.opportunities,
            tuple(replace(binding, execute=partial(execute_once, binding))
                  for binding in proposed.bindings),
            allow_resource_variants=proposed.allow_resource_variants,
        )

    return RedBoundedPlayerObserver(
        native, actions, registered_objective=True,
        enumerate_bindings=enumerate_bindings,
    )


__all__ = [
    "RedFullPokedexGoalCandidate",
    "RedFullPokedexGoalProposal",
    "RedFullPokedexGoalProposalError",
    "propose_red_full_pokedex_goals",
    "build_red_full_pokedex_player_observer",
]
