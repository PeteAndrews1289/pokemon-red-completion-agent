"""Join the existing measured fishing skill to the autonomous mixed menu."""

from functools import partial
from collections import Counter
from hashlib import sha256
from typing import cast

from .executor import CountingExecutor, FrameBudgetController
from .gen1_field_moves import Gen1FieldMovePort
from .gen1_cartridge import EvolutionMethod, evolution_graph
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import Gen1TrainerSightProjector
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .living_dex_goal_policy import project_living_dex_goal_candidate
from .living_dex_option_value import living_dex_option_context_from_goal_situation
from .observation import ItemId
from .red_collection import red_species_number
from .red_acquisition import RED_ACQUISITION_CATALOG, RedAcquisitionKind
from .red_registration_policy import RedRegistrationPolicy
from .red_fishing_acquisition import red_super_rod_destination_offers
from .red_goal_context import RedGoalContextRuntime
from .red_goal_manager import RedGoalObservation
from .red_goal_skills import _ORDINARY_CAPTURE_ITEMS
from .red_live_fishing import build_red_live_fishing_inventory
from .red_live_option_menu import RedLiveSupplementalOption, supplemental_live_option
from .red_resource_goal_router import _supported_plan, collection_field_capabilities
from .red_safari_fishing import SAFARI_FISHING_MAPS, SafariFishingError, require_safari_session
from .red_super_rod_support import (
    SUPER_ROD_FACING,
    SUPER_ROD_HOUSE_MAP_ID,
    SUPER_ROD_STANCE_YX,
    RedAcquiredSuperRodDialogueSettlement,
    RedRoutedSuperRodSupport,
    observe_red_super_rod_support,
)
from .route_plan import RoutePlanningError
from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


def autonomous_fishing_prerequisite_option(
    runtime, observation, actions, world, *, interruption_handler_wrapper=None,
    maximum_actions=6000, maximum_frames=600000,
):
    """Offer the existing free rod as a resource peer, never a forced phase.

    The ordinary projection and model rank this tool alongside other goals.
    Cartridge-derived missing fishing credit establishes usefulness; the rod
    gift itself is not a registration or a learned menu-control skill.
    """
    if interruption_handler_wrapper is not None and not callable(interruption_handler_wrapper):
        raise TypeError("fishing prerequisite wrapper must be callable")
    if any(type(n) is not int or n < 1 for n in (maximum_actions, maximum_frames)):
        raise ValueError("fishing prerequisite bounds must be positive integers")
    if (runtime.registration_policy is None or observation.raw.battle_state
            or not observation.input_ready):
        return None
    initial = observe_red_super_rod_support(runtime.reader)
    if (initial.acquired or initial.dialogue_visible or initial.bag_slots >= 20
            or not initial.input_ready or initial.in_battle):
        return None
    dex_before = runtime.reader.read_pokedex_state().owned_species
    offers = red_super_rod_destination_offers(world.rom, dex_before)
    if not offers:
        return None
    observer = Gen1TraversalObserver(
        runtime.reader,
        capability_projector=partial(
            collection_field_capabilities, runtime.emulator, allow_cut=True, allow_surf=True,
        ),
    )
    try:
        plan = world.plan_feasible_to_map(
            observer.observe(), SUPER_ROD_HOUSE_MAP_ID, goal_at=SUPER_ROD_STANCE_YX,
        )
    except RoutePlanningError:
        return None
    if (len(plan.steps) > maximum_actions
            or not _supported_plan(plan, allow_cut=True, allow_surf=True)):
        return None
    raw = runtime.reader.read()
    source = runtime.emulator.save_state_bytes()
    expected_bag = dict(raw.bag_items)
    expected_bag[int(ItemId.SUPER_ROD)] = 1
    used, terminal, receipt = False, None, None

    def execute():
        nonlocal used, terminal, receipt
        if used or runtime.emulator.save_state_bytes() != source:
            raise ValueError("fishing prerequisite is stale or consumed")
        used = True
        a0, f0 = actions.actions_executed, runtime.emulator.frame_count
        result = RedRoutedSuperRodSupport(
            actions, runtime.reader, runtime.emulator, world,
            maximum_controller_actions=maximum_actions, maximum_emulator_frames=maximum_frames,
            interruption_handler_wrapper=interruption_handler_wrapper,
            maximum_gift_confirm_pulses=64,
        ).execute()
        after = runtime.reader.read()
        if (not observe_red_super_rod_support(runtime.reader).acquired
                or dict(after.bag_items or ()) != expected_bag
                or not set(dex_before) <= set(runtime.reader.read_pokedex_state().owned_species)
                or after.player_money < raw.player_money):
            raise ValueError("fishing prerequisite lost protected resources")
        # Route combat may earn ordinary payout/XP. The gift executor protects
        # its own exact pre/post state; retained roster verification stays live.
        runtime.adapter.party_guard.verify_active_roster_restored()
        terminal = runtime.emulator.save_state_bytes()
        receipt = GoalExecutionReport(
            actions.actions_executed - a0, runtime.emulator.frame_count - f0,
            dict(native_super_rod=result.public_dict(), selectable_resource_peer=True,
                 productive_fishing_destinations=len(offers), no_destination_selected=True,
                 learned_gift_controls=False, training_examples=0),
        )
        return receipt

    def verify(report):
        return (GoalVerification.succeeded()
                if receipt is not None and report is receipt
                and runtime.emulator.save_state_bytes() == terminal
                and runtime.reader.read_input_readiness().ready
                and not runtime.reader.read_bottom_dialogue_box_visible()
                and runtime.reader.read().battle_state == 0
                and observe_red_super_rod_support(runtime.reader).acquired
                else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED))

    binding = ExecutableGoalBinding(
        "pokemon.red:free-fishing-tool:" + sha256(source).hexdigest(), GoalKind.RESUPPLY,
        min(1.0, len(plan.steps) / maximum_actions), 0.08, execute, verify,
        maximum_cash_debit=0,
    )
    # Reuse the established identity-free resource projection; no hand-tuned
    # score, target identity, supplied rank or new feature is introduced.
    from .goal_manager import GoalAvailability, GoalOpportunity, GoalUnavailableReason
    from .goal_manager_runtime import GoalBindingSet

    mask = GoalOpportunity(
        "fishing-tool:projection-mask", GoalKind.EXPLORE, GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
    )
    question = GoalBindingSet((binding.opportunity, mask), (binding,)).question(
        observation.situation,
    )
    candidate = project_living_dex_goal_candidate(
        question, 0, feature_version=5, binding_ref=binding.binding_ref,
    )
    if candidate is None:
        raise ValueError("fishing prerequisite lacks its portable resource projection")
    return supplemental_live_option(binding, candidate)


def acquired_fishing_tool_dialogue_binding(runtime, actions, *, maximum_confirm_pulses=64):
    """Reuse exact acquired-rod text settlement as control support, not a gift.

    This never re-grants an item or chooses a fishing destination. All attempts
    and the original failed delivery remain in the player's native lineage.
    """
    if type(maximum_confirm_pulses) is not int or maximum_confirm_pulses < 1:
        raise ValueError("rod dialogue bound must be a positive integer")
    raw = runtime.reader.read()
    if (raw.map_id != SUPER_ROD_HOUSE_MAP_ID
            or (raw.player_y, raw.player_x) != SUPER_ROD_STANCE_YX):
        return None
    rod = observe_red_super_rod_support(runtime.reader)
    if (not rod.acquired or rod.map_id != SUPER_ROD_HOUSE_MAP_ID
            or rod.player_yx != SUPER_ROD_STANCE_YX or rod.facing != SUPER_ROD_FACING
            or rod.in_battle or not rod.input_ready or not rod.dialogue_visible):
        return None
    source = runtime.emulator.save_state_bytes()
    dex = runtime.reader.read_pokedex_state().owned_species
    used, terminal, receipt = False, None, None

    def execute():
        nonlocal used, terminal, receipt
        if used or runtime.emulator.save_state_bytes() != source:
            raise ValueError("acquired rod text binding is stale or consumed")
        used = True
        a0, f0 = actions.actions_executed, runtime.emulator.frame_count
        result = RedAcquiredSuperRodDialogueSettlement(
            actions, runtime.reader, runtime.emulator,
            maximum_confirm_pulses=maximum_confirm_pulses,
        ).execute()
        runtime.adapter.party_guard.verify_active_roster_restored()
        if runtime.reader.read_pokedex_state().owned_species != dex:
            raise ValueError("rod dialogue changed registrations")
        terminal = runtime.emulator.save_state_bytes()
        receipt = GoalExecutionReport(
            actions.actions_executed - a0, runtime.emulator.frame_count - f0,
            dict(native_acquired_rod_dialogue=result.public_dict(), supplied_not_learned=True,
                 new_acquisition=False, training_examples=0),
        )
        return receipt

    def verify(report):
        return (GoalVerification.succeeded()
                if receipt is not None and report is receipt
                and runtime.emulator.save_state_bytes() == terminal
                and runtime.reader.read_input_readiness().ready
                and not runtime.reader.read_bottom_dialogue_box_visible()
                and runtime.reader.read().battle_state == 0
                and observe_red_super_rod_support(runtime.reader).acquired
                else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED))

    return ExecutableGoalBinding(
        "pokemon.red:acquired-fishing-tool-text:" + sha256(source).hexdigest(),
        GoalKind.RECOVER_CONTROL, 0.01, 0.0, execute, verify, maximum_cash_debit=0,
    )


def stone_precursor_fishing_demand(runtime, observation, rom):
    """Actual physical demand for unfinished stone edges, without deleting credit.

    The selected destination still comes from the real cartridge fishing table.
    A spare is useful only when a missing target cannot consume existing stock.
    This does not impose a living quota or claim the precursor is a new entry.
    """
    policy = runtime.registration_policy
    if not isinstance(policy, RedRegistrationPolicy):
        return ()
    collection = observation.collection_observation
    registered = policy.goal_registered(collection)
    counts = Counter(s.species_ref for s in collection.specimens)
    edges = evolution_graph(rom)
    needed = set()
    for method in RED_ACQUISITION_CATALOG.methods:
        source = method.consumes_species_ref
        if (method.kind is not RedAcquisitionKind.EVOLUTION or source is None
                or method.required_item_ref is None or method.species_ref not in policy.targets
                or method.species_ref in registered or source not in registered
                or source not in collection.owned_species
                or counts[source] > policy.protected_counts.get(source, 0)):
            continue
        source_number = red_species_number(source)
        target_number = red_species_number(method.species_ref)
        if any(e.method is EvolutionMethod.STONE and e.to_species == target_number
               for e in edges.get(source_number, ())):
            needed.add(source_number)
    return tuple(sorted(needed))


def autonomous_fishing_options(
    runtime: RedGoalContextRuntime,
    observation: RedGoalObservation,
    actions: CountingExecutor,
    world: StrategicScenarioRouteWorld,
    *,
    allow_fast_transport: bool = False,
    interruption_handler_wrapper=None,
) -> tuple[RedLiveSupplementalOption, ...]:
    """Offer supported fishing with actual inventory and local registration.

    Reuse the caller's counted action and frame-budget chain. Discovery cannot
    move, buy supplies or fix storage; each admitted binding owns its route and
    bounded capture and verifies its actual registration result.
    """
    if interruption_handler_wrapper is not None and not callable(interruption_handler_wrapper):
        raise TypeError("fishing interruption wrapper must be callable")
    bag = dict(observation.raw.bag_items or ())
    safari_steps = None
    if getattr(observation.raw, "map_id", None) in SAFARI_FISHING_MAPS:
        try:
            safari_steps = require_safari_session(runtime.reader).safari_steps
        except SafariFishingError:
            return ()
    if (
        observation.raw.battle_state
        or not observation.input_ready
        or bag.get(int(ItemId.SUPER_ROD), 0) < 1
        or (
            safari_steps is None
            and not any(bag.get(int(item), 0) > 0 for item in _ORDINARY_CAPTURE_ITEMS)
        )
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
            collection_field_capabilities,
            controller,
            allow_cut=True,
            allow_surf=True,
        ),
    )
    field = Gen1FieldMovePort(
        actions,
        runtime.reader,
        controller,
        cut_block_swaps={s.before: s.after for s in world.rules.cut_block_swaps},
    )
    registered = runtime.registration_policy.goal_registered(observation.collection_observation)
    physical = (() if safari_steps is not None else
                stone_precursor_fishing_demand(runtime, observation, world.rom))
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
            safari_session_steps=safari_steps,
            **({"physical_demand": physical} if physical else {}),
            **({} if not allow_fast_transport else {"allow_fast_transport": True}),
            **({} if interruption_handler_wrapper is None else {
                "interruption_handler_wrapper": interruption_handler_wrapper,
            }),
        )
    finally:
        if before != (
            actions.actions_executed,
            runtime.emulator.frame_count,
            runtime.reader.read(),
        ):
            raise ValueError("autonomous fishing inventory changed the game")
    return inventory.supplements
