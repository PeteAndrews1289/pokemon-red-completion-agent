"""Offer the existing metered Safari skill in the autonomous mixed menu."""

from typing import cast

from .executor import CountingExecutor, FrameBudgetController
from .living_dex_option_value import living_dex_option_context_from_goal_situation
from .red_collection import red_species_number
from .red_goal_context import RedGoalContextRuntime
from .red_goal_manager import RedGoalObservation
from .red_live_option_menu import RedLiveSupplementalOption
from .red_live_safari import build_red_live_safari_inventory
from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


def autonomous_safari_options(
    runtime: RedGoalContextRuntime,
    observation: RedGoalObservation,
    actions: CountingExecutor,
    world: StrategicScenarioRouteWorld,
) -> tuple[RedLiveSupplementalOption, ...]:
    """Expose one paid acquisition only if real cash and entry are qualified."""
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
    )
    after = actions.actions_executed, runtime.emulator.frame_count, runtime.reader.read()
    if after != before:
        raise ValueError("Safari option discovery changed the game")
    return inventory.supplements


__all__ = ["autonomous_safari_options"]
