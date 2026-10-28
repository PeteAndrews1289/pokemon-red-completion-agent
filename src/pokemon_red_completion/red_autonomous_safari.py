"""Offer the existing metered Safari skill in the autonomous mixed menu."""

from collections import Counter
from dataclasses import replace
from typing import cast

from .executor import CountingExecutor, FrameBudgetController
from .living_dex_option_value import living_dex_option_context_from_goal_situation
from .red_acquisition import RED_ACQUISITION_CATALOG
from .red_collection import RED_SOLO_COLLECTION_CONTRACT, red_species_number
from .red_registration_policy import RedRegistrationPolicy
from .red_goal_context import RedGoalContextRuntime
from .red_goal_manager import RedGoalObservation
from .red_live_option_menu import RedLiveSupplementalOption
from .red_live_safari import build_red_live_safari_inventory
from .red_safari_funding_budget import RedSafariFundingBudget, red_safari_funding_budget
from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


def _safari_physical_demand(runtime, observation):
    """Reuse real unreserved stock and downstream registration dependencies."""
    policy = runtime.registration_policy
    if not isinstance(policy, RedRegistrationPolicy):
        return {}
    stock = observation.collection_observation
    catalog = replace(RED_ACQUISITION_CATALOG, remaining_demand=True,
        registered_species=policy.goal_registered(stock),
        protected_counts=tuple(sorted(policy.protected_counts.items())),
        level_evolution_edges=runtime.level_evolution_acquisition_edges)
    counts = Counter(s.species_ref for s in stock.specimens)
    requirements = catalog.alternative_capture_holdings(
        stock, tuple(sorted(RED_SOLO_COLLECTION_CONTRACT.target_species)))
    return dict(acquisition_catalog=catalog, required_capture_numbers=frozenset(
        red_species_number(s) for s, n in requirements.items() if n > counts[s]))
def autonomous_safari_options(
    runtime: RedGoalContextRuntime,
    observation: RedGoalObservation,
    actions: CountingExecutor,
    world: StrategicScenarioRouteWorld,
    *,
    include_capture_invocation: bool = False,
) -> tuple[RedLiveSupplementalOption, ...]:
    """Expose qualified area alternatives, each requiring one paid admission."""
    if type(include_capture_invocation) is not bool:
        raise ValueError("Safari invocation observation must be an explicit boolean")
    if runtime.registration_policy is None:
        raise ValueError("autonomous Safari needs registered collection")
    before = actions.actions_executed, runtime.emulator.frame_count, runtime.reader.read()
    registered = frozenset(
        red_species_number(species)
        for species in observation.collection_observation.owned_species
    )
    inventory = build_red_live_safari_inventory(
        world.rom,
        registered,
        living_dex_option_context_from_goal_situation(observation.situation),
        free_storage_slots=observation.free_storage_slots,
        world=world,
        controller=cast(FrameBudgetController, runtime.emulator),
        actions=actions,
        reader=runtime.reader,
        expose_all_areas=True,
        complete_paid_session=getattr(runtime, "safari_complete_paid_session", False),
        **({"include_capture_invocation": True} if include_capture_invocation else {}),
        **_safari_physical_demand(runtime, observation),
    )
    if not inventory.supplements and getattr(runtime, "safari_indoor_departure", False):
        from .red_indoor_safari import indoor_safari_inventory

        inventory = indoor_safari_inventory(
            world.rom, registered,
            living_dex_option_context_from_goal_situation(observation.situation),
            free_storage_slots=observation.free_storage_slots, world=world,
            controller=runtime.emulator, actions=actions, reader=runtime.reader,
            event_sink=getattr(runtime, "trainer_funding_event_sink", None),
            expose_all_areas=True,
            complete_paid_session=getattr(runtime, "safari_complete_paid_session", False),
            departure_recovery=getattr(runtime, "safari_departure_recovery", False),
            dig_departure=getattr(runtime, "collection_dig_departure", False),
            **({"include_capture_invocation": True} if include_capture_invocation else {}),
            **_safari_physical_demand(runtime, observation),
        )
    after = actions.actions_executed, runtime.emulator.frame_count, runtime.reader.read()
    if after != before:
        raise ValueError("Safari option discovery changed the game")
    return inventory.supplements


def autonomous_safari_funding_quote(
    runtime: RedGoalContextRuntime,
    observation: RedGoalObservation,
    world: StrategicScenarioRouteWorld,
) -> RedSafariFundingBudget | None:
    """Derive one paid Safari admission quote without controller input."""
    if runtime.registration_policy is None:
        return None
    rom = getattr(world, "rom", None)
    if not isinstance(rom, bytes):
        return None
    registered = frozenset(
        red_species_number(species)
        for species in observation.collection_observation.owned_species
    )
    before = runtime.emulator.frame_count, runtime.reader.read()
    budget = red_safari_funding_budget(
        rom,
        registered,
        free_storage_slots=observation.free_storage_slots,
        world=world,
        reader=runtime.reader,
    )
    after = runtime.emulator.frame_count, runtime.reader.read()
    if after != before:
        raise ValueError("Safari funding quote changed the game")
    return budget


autonomous_safari_funding_budget = autonomous_safari_funding_quote

__all__ = [
    "autonomous_safari_funding_budget",
    "autonomous_safari_funding_quote",
    "autonomous_safari_options",
]
