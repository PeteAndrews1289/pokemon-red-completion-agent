"""Offer the existing metered Safari skill in the autonomous mixed menu."""

from typing import cast

from .executor import CountingExecutor, FrameBudgetController
from .living_dex_option_value import living_dex_option_context_from_goal_situation
from .red_collection import red_species_number
from .red_goal_context import RedGoalContextRuntime
from .red_goal_manager import RedGoalObservation
from .red_live_option_menu import RedLiveSupplementalOption
from .red_live_safari import build_red_live_safari_inventory
from .red_safari_funding_budget import RedSafariFundingBudget, red_safari_funding_budget
from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


def autonomous_safari_options(
    runtime: RedGoalContextRuntime,
    observation: RedGoalObservation,
    actions: CountingExecutor,
    world: StrategicScenarioRouteWorld,
) -> tuple[RedLiveSupplementalOption, ...]:
    """Expose qualified area alternatives, each requiring one paid admission."""
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
