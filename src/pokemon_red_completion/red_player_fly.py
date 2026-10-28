"""Model-owned Fly dependency, using existing route, reward and lesson mechanics."""

from dataclasses import replace
from functools import lru_cache
from hashlib import sha256

from .gen1_field_moves import gen1_field_capabilities
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import (
    Gen1TrainerSightProjector,
    static_trainer_sight_zones,
    trainer_headers,
)
from .gen1_traversal import map_object_events
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .living_dex_option_value import (
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionFeatures,
    LivingDexOptionKind,
)
from .local_router import without_coordinates
from .observation import Badge, EventFlag, ItemId, MapId, event_flag_is_set
from .player_option_challenge import OptionChallenge
from .red_battle_practice_cartridge import RedPracticeCartridge
from .red_live_option_menu import supplemental_live_option
from .red_npc_approach import approach_npc
from .red_player_field_goals import _field_ready
from .red_player_field_item import settle_story_interaction
from .red_player_safari_rewards import collect_hm_reward, reward_bag
from .route_plan import RoutePlanningError


@lru_cache(maxsize=2)
def _fly_trainer_tables(rom, map_ids):
    """Cache immutable cartridge tables, never mutable defeated-event state."""
    return (trainer_headers(rom, map_ids, full_event_offsets=True),
            map_object_events(rom, map_ids))


def _noncombat_fly_world(world, raw):
    """Reserve future trainer lanes for this noncombat dependency's whole route.

    Reuse the preparation-walk projection: native defeated events can release
    a lane, while current-map objects and sight remain live. Keep the lanes in
    both graphs and blockers so a later staged Cut rebuild cannot erase them.
    No trainer is fought and no story objective is selected by this quote.
    """
    headers, events = _fly_trainer_tables(world.rom, tuple(sorted(world.terrain)))
    zones = static_trainer_sight_zones(headers, events, raw.event_flags)
    blocked = {}
    for zone in zones:
        if zone.map_id != raw.map_id and zone.lane:
            blocked.setdefault(zone.map_id, set()).update(zone.lane)
    if not blocked:
        return world
    graphs, objects = dict(world.local_graphs), dict(world.object_blockers)
    for map_id, lanes in blocked.items():
        graphs[map_id] = without_coordinates(graphs[map_id], lanes)
        objects[map_id] = objects[map_id] | frozenset(lanes)
    return replace(world, local_graphs=graphs, object_blockers=objects)


def fly_dependency_options(runtime, actions, *, route):
    """Expose legal Fly dependencies before the League, without selecting one.

    The existing reward and lesson ports check the real badge, native stock,
    compatibility and fresh route. Eight badges are not a Fly requirement.
    """
    from .red_player_owned_machines import owned_machine_options

    reward = fly_reward_option(runtime, actions, route=route)
    lessons = owned_machine_options(
        runtime, actions, rom=route.rom,
        include_fly_lesson=True, include_attack_lessons=False,
    )
    return (() if reward is None else (reward,)) + lessons


def fly_reward_option(runtime, actions, *, route):
    """No input while quoting. A prefix never counts as the obtained machine."""
    if not _field_ready(runtime) or getattr(route, "allow_surf", False) is not True:
        return None
    raw = runtime.reader.read()
    item, target = int(ItemId.HM02_FLY), int(MapId.ROUTE_16_FLY_HOUSE)
    event = int(EventFlag.GOT_HM02)
    if (raw.bag_items is None or raw.party_species_ids is None or raw.party_hp is None
            or dict(raw.bag_items).get(item)
            or event_flag_is_set(raw.event_flags, event)
            or not int(raw.badge_bits or 0) & int(Badge.THUNDER)
            or not any(raw.party_hp)
            or not any(19 in RedPracticeCartridge(route.rom).species(s).tmhm_moves
                       for s, hp in zip(raw.party_species_ids, raw.party_hp, strict=True) if hp)):
        return None
    try:
        expected_bag = reward_bag(raw.bag_items, item=item)
    except ValueError:
        return None
    # Revision-qualified NPC identity, not a recorded movement recipe.
    objects = [o for o in map_object_events(route.rom, {target}) if o.object_index == 1]
    if len(objects) != 1 or (objects[0].at, objects[0].movement, objects[0].text_id) != (
        (3, 2), 255, 1
    ):
        raise ValueError("Fly reward cartridge NPC differs")
    obj = objects[0]

    def quote():
        current = runtime.reader.read()
        world = _noncombat_fly_world(
            route.route_world.with_current_observation(runtime.reader), current)
        fresh_route = replace(route, route_world=world)
        start = Gen1TraversalObserver(runtime.reader,
            capability_projector=lambda r: gen1_field_capabilities(runtime.emulator, r),
            hazard_projector=Gen1TrainerSightProjector(route.rom, runtime.reader,
                                                       full_event_offsets=True)).observe()
        choices = []
        for dy, dx in ((1, 0), (0, -1), (0, 1), (-1, 0)):
            at = obj.y + dy, obj.x + dx
            if min(at) < 0:
                continue
            try:
                plan = world.plan_feasible_to_map(start, target, goal_at=at)
            except RoutePlanningError:
                continue
            choices.append((plan.cost, fresh_route, target, at, True))
        if choices:
            return min(choices, key=lambda row: row[0])
        # A reachable first passage is not evidence that this noncombat
        # dependency can cross the trainer corridor beyond it. Leave ordinary
        # story travel available; only advertise the complete Fly delivery.
        return None

    initial = quote()
    if initial is None:
        return None
    source = runtime.emulator.save_state_bytes()
    dex, boxes, pc = (runtime.reader.read_pokedex_state(), runtime.reader.read_all_box_states(),
                       runtime.reader.read_pc_items())
    used, terminal, receipt = False, None, None

    def execute():
        nonlocal used, terminal, receipt
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("Fly reward option is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        visited, transitions = set(), 0
        for _ in range(32):
            current = runtime.reader.read()
            boundary = current.map_id, current.player_y, current.player_x, current.event_flags
            if not _field_ready(runtime) or boundary in visited:
                raise RuntimeError("Fly reward delivery did not advance a ready boundary")
            visited.add(boundary)
            quoted = quote()
            if quoted is None:
                raise RuntimeError("Fly reward delivery has no fresh executable route")
            _, fresh_route, destination, at, final = quoted
            replace(fresh_route, destination_map=destination, destination_at=at)(
                actions, runtime.reader, runtime.emulator)
            transitions += 1
            settle_story_interaction(runtime, actions)
            if final:
                approach_npc(runtime.emulator, runtime.reader, actions, rom=route.rom,
                             map_id=target, object_index=1)
                collect_hm_reward(runtime, actions, item=item, events=(event,))
                break
        else:
            raise RuntimeError("Fly reward exceeded its finite transition allowance")
        after = runtime.reader.read()
        after_dex = runtime.reader.read_pokedex_state()
        if (not _field_ready(runtime) or after.map_id != target
                or dict(after.bag_items or ()) != expected_bag
                or after.player_money != raw.player_money
                or after.badge_bits != raw.badge_bits
                or after.party_species_ids != raw.party_species_ids
                or after_dex.owned_species != dex.owned_species
                or not dex.seen_species <= after_dex.seen_species
                or runtime.reader.read_all_box_states() != boxes
                or runtime.reader.read_pc_items() != pc
                or not event_flag_is_set(after.event_flags, event)):
            raise RuntimeError("Fly reward resources or native outcome differ")
        terminal = runtime.emulator.save_state_bytes()
        receipt = GoalExecutionReport(actions.actions_executed-a, runtime.emulator.frame_count-f,
            dict(mechanic="native_Fly_reward_dependency", item_id=item, quantity=1,
                 event_verified=True, complete_delivery=True, transitions=transitions,
                 selection_authority="ordinary_model_goal", navigation_learned=False,
                 reward_interaction_learned=False, lesson_completed=False, cash_debit=0,
                 objective_completed=False, registrations_gained=0))
        return receipt

    def verify(report):
        return (GoalVerification.succeeded()
            if receipt is not None and report is receipt and terminal ==
               runtime.emulator.save_state_bytes() and _field_ready(runtime)
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED))

    effort = min(1.0, initial[0] / 3000)
    binding = ExecutableGoalBinding("pokemon.red:fly-reward:"+sha256(source).hexdigest(),
        GoalKind.DEVELOP_TEAM, effort, 0.04, execute, verify, maximum_cash_debit=0)
    candidate = LivingDexOptionCandidate(binding_ref=binding.binding_ref,
        availability=LivingDexOptionAvailability.AVAILABLE,
        features=LivingDexOptionFeatures(LivingDexOptionKind.DEVELOP, 0.0, 1.0,
            0.0, effort, 0.04, 0.0, 0.0, 0.2, 0.5),
        challenge=OptionChallenge(False, False, 0.0, 0.0, 0.0))
    return supplemental_live_option(binding=binding, candidate=candidate)
