"""Join the existing measured fishing skill to the autonomous mixed menu."""

from functools import partial
from typing import cast

from .executor import CountingExecutor, FrameBudgetController
from .gen1_field_moves import Gen1FieldMovePort
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import Gen1TrainerSightProjector
from .living_dex_option_value import living_dex_option_context_from_goal_situation
from .observation import ItemId
from .red_collection import red_species_number
from .red_goal_context import RedGoalContextRuntime
from .red_goal_manager import RedGoalObservation
from .red_goal_skills import _ORDINARY_CAPTURE_ITEMS
from .red_live_fishing import build_red_live_fishing_inventory
from .red_live_option_menu import RedLiveSupplementalOption
from .red_resource_goal_router import collection_field_capabilities
from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


def autonomous_fishing_options(
    runtime: RedGoalContextRuntime,
    observation: RedGoalObservation,
    actions: CountingExecutor,
    world: StrategicScenarioRouteWorld,
) -> tuple[RedLiveSupplementalOption, ...]:
    """Offer supported fishing with actual inventory and local registration.

    Reuse the caller's counted action and frame-budget chain. Discovery cannot
    move, buy supplies or fix storage; each admitted binding owns its route and
    bounded capture and verifies its actual registration result.
    """
    bag = dict(observation.raw.bag_items or ())
    if (
        observation.raw.battle_state
        or not observation.input_ready
        or bag.get(int(ItemId.SUPER_ROD), 0) < 1
        or not any(bag.get(int(item), 0) > 0 for item in _ORDINARY_CAPTURE_ITEMS)
        or observation.immediate_capture_slots < 1
    ):
        return ()
    if runtime.registration_policy is None:
        raise ValueError("autonomous fishing requires registered collection")
    before = actions.actions_executed, runtime.emulator.frame_count, runtime.reader.read()
    controller = cast(FrameBudgetController, runtime.emulator)
    observer = Gen1TraversalObserver(
        runtime.reader,
        hazard_projector=Gen1TrainerSightProjector(world.rom, runtime.reader),
        capability_projector=partial(
            collection_field_capabilities, controller, allow_cut=True, allow_surf=True,
        ),
    )
    field = Gen1FieldMovePort(
        actions, runtime.reader, controller,
        cut_block_swaps={s.before: s.after for s in world.rules.cut_block_swaps},
    )
    registered = runtime.registration_policy.goal_registered(observation.collection_observation)
    try:
        inventory = build_red_live_fishing_inventory(
            world.rom,
            frozenset(red_species_number(s) for s in registered),
            living_dex_option_context_from_goal_situation(observation.situation),
            free_storage_slots=observation.immediate_capture_slots,
            world=world,
            traversal=observer.observe(),
            observer=observer,
            field=field,
            controller=controller,
            actions=actions,
            reader=runtime.reader,
            emulator=controller,
            maximum_candidates=4,
            maximum_casts=24,
        )
    finally:
        if before != (
            actions.actions_executed, runtime.emulator.frame_count, runtime.reader.read(),
        ):
            raise ValueError("autonomous fishing inventory changed the game")
    return inventory.supplements
