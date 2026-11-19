"""Current-save connections around already implemented native acquisitions.

Preparation is controller support, not a new learner or a source of free items.
The Amber seam only adds real indoor departure/Fly before the existing compound
ingredient/revival executor. Its native verification remains authoritative.
"""

from contextlib import contextmanager
from dataclasses import replace
from functools import partial
from hashlib import sha256

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_field_moves import Gen1FieldMoveError, Gen1FieldMovePort, fly_menu_indices
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_composition_qualification import HardCompositionActionLimiter
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from pokemon_red_completion.observation import MAX_BAG_ITEMS, Badge, EventFlag, MapId, event_flag_is_set
from pokemon_red_completion.red_collection_fly import red_fly_landings
from pokemon_red_completion.red_fossil_acquisition import (
    FOSSIL_ITEMS, fossil_target_by_item, available_red_fossil_targets,
    RedFossilGoalProvider, RedRoutedFossilRevival,
)
from pokemon_red_completion.red_fossil_ingredient_goal import RedFossilIngredientGoalProvider
from pokemon_red_completion.red_indoor_departure_plan import bounded_indoor_departure
from pokemon_red_completion.red_npc_item_gift import old_amber_gift
from pokemon_red_completion.red_resource_goal_router import _supported_plan, collection_field_capabilities
from pokemon_red_completion.red_routed_recovery import guarded_collection_route_handler
from pokemon_red_completion.route_executor import execute_route
from pokemon_red_completion.route_plan import RoutePlanningError


def _museum_route_pair(world, start, gift):
    """Prove a supported there-and-back path, without pretending to be there."""
    for dy, dx in ((1, 0), (0, -1), (0, 1), (-1, 0)):
        at = gift.at[0] + dy, gift.at[1] + dx
        if min(at) < 0:
            continue
        try:
            outward = world.plan_feasible_to_map(start, gift.map_id, goal_at=at)
            projected = replace(start, map_id=gift.map_id, at=at, occupied=frozenset(), hazards=())
            back = world.plan_feasible_to_map(projected, start.map_id, goal_at=start.at)
        except RoutePlanningError:
            continue
        if all(len(p.steps) <= 400 and p.terminal_mode in (None, "land")
               and _supported_plan(p, allow_cut=True, allow_surf=False) for p in (outward, back)):
            return outward, back
    return None

def museum_route_available(world, start, gift):
    return _museum_route_pair(world, start, gift) is not None


def amber_bindings(runtime, observation, actions, world, *, carrier_route=None, carrier_preparation=None, before_revival=None, revival_party=None):
    if not runtime.scripted_gifts:
        return ()
    reader, raw, emulator = runtime.reader, observation.raw, runtime.emulator
    gift = old_amber_gift(world.rom)
    target = fossil_target_by_item(gift.item_id)
    owned = reader.read_pokedex_state().owned_species
    observer = Gen1TraversalObserver(reader, capability_projector=partial(
        collection_field_capabilities, emulator, allow_cut=True, allow_surf=False))
    origin = observer.observe()
    if (not raw.game_started or raw.battle_state or not observation.input_ready
            or not origin.ready or origin.interruption is not None or origin.mode != "land"
            or reader.read_bottom_dialogue_box_visible()
            or raw.event_flags is None or len(raw.event_flags) * 8 <= gift.event_flag
            or target.national_dex_number in owned or event_flag_is_set(raw.event_flags, gift.event_flag)
            or raw.bag_items is None or len(raw.bag_items) >= MAX_BAG_ITEMS
            or any(i in FOSSIL_ITEMS for i, _ in raw.bag_items)
            or any(event_flag_is_set(raw.event_flags, int(f)) for f in (
                EventFlag.GAVE_FOSSIL_TO_LAB, EventFlag.LAB_STILL_REVIVING_FOSSIL,
                EventFlag.LAB_HANDING_OVER_FOSSIL_MON))
            or not raw.party_hp or not any(raw.party_hp)):
        return ()
    boxes = reader.read_all_box_states()
    if raw.party_count == 6 and len(boxes.boxes[boxes.current_box_index].species_ids) >= 20:
        return ()
    towns = reader.read_fly_destinations()
    town = int(MapId.PEWTER_CITY)
    if town not in towns or int(MapId.CINNABAR_ISLAND) not in towns or not int(raw.badge_bits or 0) & int(Badge.THUNDER):
        return ()
    try:
        fly_menu_indices(raw)
    except Gen1FieldMoveError:
        return ()
    world = world.with_current_observation(reader)
    start, departure = origin, None
    if origin.map_id >= 0x25:
        departure = bounded_indoor_departure(origin, world)
        if departure is None or not _supported_plan(departure, allow_cut=True, allow_surf=False):
            return ()
        start = replace(origin, map_id=departure.terminal_map, at=departure.terminal_at, occupied=frozenset())
    flight = start.map_id != town
    landing = dict(red_fly_landings(world.rom))[town]
    if flight:
        start = replace(start, map_id=town, at=landing, last_outside_map=town, occupied=frozenset(), hazards=())
    if not museum_route_available(world, start, gift):
        if carrier_route is not None and carrier_preparation is not None and before_revival is None:
            return _amber_carrier_bindings(runtime, observation, actions, world, origin, start, gift, target, carrier_route, carrier_preparation)
        return ()
    original = emulator.save_state_bytes()
    before_actions, before_frames = actions.actions_executed, emulator.frame_count
    used, inner, inner_report, result, terminal = False, None, None, None, None

    def execute():
        nonlocal used, inner, inner_report, result, terminal
        if used:
            raise RuntimeError("Amber binding already attempted")
        used = True
        if (emulator.save_state_bytes() != original or runtime.adapter.observe() != observation
                or reader.read_all_box_states() != boxes
                or (actions.actions_executed, emulator.frame_count) != (before_actions, before_frames)):
            raise RuntimeError("Amber source changed before input")
        counted = CountingExecutor(HardCompositionActionLimiter(actions,
            maximum_actions_per_decision=1800, maximum_episode_actions=1800))
        port = Gen1FieldMovePort(counted, reader, emulator,
            cut_block_swaps={s.before: s.after for s in world.rules.cut_block_swaps})
        steps = 0
        if departure is not None:
            report = execute_route(departure, port, observer,
                interruption_handler=guarded_collection_route_handler(counted, reader,
                    route_name="Amber indoor departure", maximum_scripted_dialogues=4),
                replanner=world.with_current_observation(reader).replanner())
            if not report.passed:
                raise RuntimeError("Amber indoor departure did not settle")
            steps = len(report.executed_steps)
        if flight:
            port.execute(MacroAction(MacroActionKind.FIELD_MOVE, "fly:pewter_city"))
            actual = observer.observe()
            if not actual.ready or (actual.map_id, actual.at, actual.mode) != (town, landing, "land"):
                raise RuntimeError("Amber Fly landing differs")
        # The original provider is only offered at the real native outdoor state.
        offer = RedFossilIngredientGoalProvider(world.rom, runtime.adapter, reader, emulator,
            counted, world.with_current_observation(reader), observer,
            before_revival=before_revival, revival_party=revival_party).offer(runtime.adapter.observe())
        if offer.binding is None:
            raise RuntimeError(f"Amber native ingredient offer unavailable: {offer.unavailable_reason}")
        inner = offer.binding
        inner_report = inner.execute()
        if inner.verify(inner_report).status is not GoalDecisionOutcome.SUCCEEDED:
            raise RuntimeError("Amber ingredient/revival native outcome failed verification")
        runtime.adapter.party_guard.verify_active_roster_restored()
        result = GoalExecutionReport(actions.actions_executed - before_actions,
            emulator.frame_count - before_frames, dict(inner_report.evidence,
                preparation_route_steps=steps, preparation_fly_used=flight,
                ingredient_provider_reused=True, learned_preparation=False))
        terminal = emulator.save_state_bytes()
        return result

    def verify(report):
        if (result is None or report is not result or terminal != emulator.save_state_bytes()
                or inner is None or inner.verify(inner_report).status is not GoalDecisionOutcome.SUCCEEDED
                or reader.read().player_money != raw.player_money
                or reader.read().bag_items != raw.bag_items or emulator.pressed_buttons):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return (ExecutableGoalBinding(binding_ref=f"red-current-save-amber:{sha256(original).hexdigest()}",
        kind=GoalKind.ACQUIRE_SPECIES, estimated_effort=.5, estimated_risk=.12,
        execute=execute, verify=verify, search_source_ref=target.source_ref),)



def _amber_carrier_bindings(runtime, observation, actions, world, origin, projected, gift, target, route, preparation):
    """Every quoted owned carrier/donor/lesson is a complete acquisition option."""
    from dataclasses import asdict
    from pokemon_red_completion.gen1_traversal import CUT_CAPABILITY
    from pokemon_red_completion.provenance import canonical_sha256
    from pokemon_red_completion.red_field_capability_demand import CutDependencyWitness
    from pokemon_red_completion.red_field_carrier import field_carrier_branches, _party_resources, FieldCarrierSettlementError
    from pokemon_red_completion.red_field_carrier_custody import settle_pending_field_carrier
    from pokemon_red_completion.red_player_party_loan import _stock, _walk
    if runtime.adapter.party_guard.field_carrier is not None:
        return ()
    conditional = replace(projected, capabilities=projected.capabilities | {CUT_CAPABILITY})
    pair = _museum_route_pair(world, conditional, gift)
    if pair is None:
        return ()
    count = sum(s.kind == "cut_mutation" for p in pair for s in p.steps)
    if not count:
        return ()
    witness = CutDependencyWitness(target.species_ref, gift.map_id,
        canonical_sha256([[asdict(s) for s in p.steps] for p in pair]), count)
    combat = frozenset(m.specimen_ref for m in preparation.roster if m.purpose.value == "combat")
    rows = field_carrier_branches(runtime, actions, observation, rom=world.rom,
        route=route, combat_refs=combat, preparation=preparation,
        dependency_witnesses=(witness,), include_other_boxes=True)
    source = runtime.emulator.save_state_bytes()
    original_party = runtime.reader.read().party_species_ids
    initial_stock, resources = _stock(runtime), _party_resources(runtime)
    initial_owned = runtime.reader.read_pokedex_state().owned_species
    initial = runtime.reader.read()

    def bind(carrier):
        used = False
        result = terminal = None
        def repay(counted, live_world, start):
            guard = runtime.adapter.party_guard
            custody = guard.field_carrier
            if custody is None or custody.phase != "active":
                raise RuntimeError("ingredient carrier custody is absent")
            runtime.adapter.party_guard = replace(guard, field_carrier=replace(custody, phase="pending"))
            settle_pending_field_carrier(runtime, counted, live_world)
            runtime.adapter.party_guard.verify_active_roster_restored()
            _walk(runtime, counted, live_world, start.map_id, start.at)
            return dict(original_roster_restored=True, individual_custody_verified=True,
                        learned=False, stock_conserved=True)
        def execute():
            nonlocal used,result,terminal
            if used or runtime.emulator.save_state_bytes() != source:
                raise RuntimeError("carrier ingredient acquisition is stale or consumed")
            used = True
            a,f = actions.actions_executed,runtime.emulator.frame_count
            try:
                borrow = carrier.execute()
                if carrier.verify(borrow).status is not GoalDecisionOutcome.SUCCEEDED:
                    raise RuntimeError("ingredient carrier exchange did not verify")
                offers = amber_bindings(runtime, runtime.adapter.observe(), actions,
                    world.with_current_observation(runtime.reader), before_revival=repay,
                    revival_party=original_party)
                if len(offers) != 1:
                    raise RuntimeError("native carrier did not unlock ingredient acquisition")
                inner = offers[0]; report = inner.execute()
                if inner.verify(report).status is not GoalDecisionOutcome.SUCCEEDED:
                    raise RuntimeError("carrier ingredient acquisition did not verify")
                runtime.adapter.party_guard.verify_active_roster_restored()
                after_stock = _stock(runtime)
                added = after_stock-initial_stock
                if (initial_stock-after_stock or sum(added.values()) != 1
                        or any(k[1] != target.internal_species_id for k in added)
                        or _party_resources(runtime) != resources
                        or runtime.reader.read().player_money != initial.player_money
                        or runtime.reader.read().bag_items != initial.bag_items
                        or runtime.reader.read_pokedex_state().owned_species != initial_owned | {target.national_dex_number}):
                    raise RuntimeError("carrier ingredient acquisition changed protected individuals/resources")
                result = GoalExecutionReport(actions.actions_executed-a,runtime.emulator.frame_count-f,
                    dict(report.evidence, owned_carrier_exchange=dict(borrow.evidence),
                         original_roster_restored=True, complete_acquisition_bundle=True,
                         carrier_and_lesson_selected_with_acquisition=True, learned_menu_execution=False))
                terminal = runtime.emulator.save_state_bytes()
                return result
            except BaseException as primary:
                guard = runtime.adapter.party_guard
                if guard.field_carrier is not None and guard.field_carrier.phase == "active":
                    try:
                        runtime.adapter.party_guard = replace(guard, field_carrier=replace(guard.field_carrier, phase="pending"))
                        settle_pending_field_carrier(runtime, actions, world)
                    except BaseException as secondary:
                        from pokemon_red_completion.red_autonomous_player import _exception_chain
                        failure = FieldCarrierSettlementError("ingredient carrier repayment failed")
                        failure.settlement_error_chain = _exception_chain(secondary)
                        raise failure from primary
                raise
        def verify(report):
            runtime.adapter.party_guard.verify_active_roster_restored()
            return (GoalVerification.succeeded() if result is not None and report is result
                and terminal == runtime.emulator.save_state_bytes() and not runtime.emulator.pressed_buttons
                else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED))
        return ExecutableGoalBinding("red-amber-owned-carrier:"+sha256(source).hexdigest()+":"+
            canonical_sha256(carrier.binding_ref),GoalKind.ACQUIRE_SPECIES,.8,.15,
            execute,verify,search_source_ref=target.source_ref)
    return tuple(bind(binding) for binding,_ in rows)


def held_fossil_bindings(runtime, observation, actions, world):
    """Reuse held-item revival after one real indoor departure, not a new gift."""
    if (not runtime.scripted_gifts or not observation.input_ready
        or observation.raw.battle_state or runtime.reader.read_bottom_dialogue_box_visible()):
        return ()
    targets=tuple(t for t in available_red_fossil_targets(runtime.reader)
        if t.species_ref not in observation.collection_observation.owned_species)
    if not targets:
        return ()
    observer=Gen1TraversalObserver(runtime.reader)
    start=observer.observe()
    departure=None
    if start.map_id>=0x25:
        departure=bounded_indoor_departure(start,world.with_current_observation(runtime.reader))
        if departure is None or not _supported_plan(departure,allow_cut=False,allow_surf=False):
            return ()
    if int(MapId.CINNABAR_ISLAND) not in runtime.reader.read_fly_destinations():
        return ()
    origin=runtime.emulator.save_state_bytes()
    a,f=actions.actions_executed,runtime.emulator.frame_count
    def bind(target):
        used=False
        result=terminal=inner=inner_report=None
        def execute():
            nonlocal used,result,terminal,inner,inner_report
            if (used or origin!=runtime.emulator.save_state_bytes()
                or observation!=runtime.adapter.observe()
                or (a,f)!=(actions.actions_executed,runtime.emulator.frame_count)):
                raise RuntimeError("held fossil source changed before input")
            used=True
            if departure is not None:
                report=execute_route(departure,actions,observer,
                    interruption_handler=guarded_collection_route_handler(actions,runtime.reader,
                        route_name="held fossil indoor departure",maximum_scripted_dialogues=4),
                    replanner=world.with_current_observation(runtime.reader).replanner())
                if not report.passed:
                    raise RuntimeError("held fossil departure failed")
            fresh=runtime.adapter.observe()
            if target not in available_red_fossil_targets(runtime.reader):
                raise RuntimeError("held fossil target changed during departure")
            inner=RedFossilGoalProvider(target,runtime.adapter,runtime.reader,
                RedRoutedFossilRevival(actions,runtime.reader,runtime.emulator,
                    world.with_current_observation(runtime.reader))).binding(fresh)
            if inner is None:
                raise RuntimeError("held fossil native revival is unavailable")
            inner_report=inner.execute()
            if inner.verify(inner_report).status is not GoalDecisionOutcome.SUCCEEDED:
                raise RuntimeError("held fossil native revival did not verify")
            runtime.adapter.party_guard.verify_active_roster_restored()
            result=GoalExecutionReport(actions.actions_executed-a,runtime.emulator.frame_count-f,
                {**dict(inner_report.evidence),"held_fossil_provider_reused":True,
                 "indoor_departure_used":departure is not None,"learned_preparation":False})
            terminal=runtime.emulator.save_state_bytes()
            return result
        def verify(report):
            if (result is None or report is not result or terminal!=runtime.emulator.save_state_bytes()
                or inner is None or inner.verify(inner_report).status is not GoalDecisionOutcome.SUCCEEDED
                or runtime.reader.read().player_money!=observation.raw.player_money
                or runtime.emulator.pressed_buttons):
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            return GoalVerification.succeeded()
        return ExecutableGoalBinding("red-fossil:"+target.source_ref,GoalKind.ACQUIRE_SPECIES,
            .24,.08,execute,verify,search_source_ref=target.source_ref)
    return tuple(bind(t) for t in targets)


def unmet_prize_cash(runtime,economy,rom):
    """Quote the required, still-missing prize; never a standing cash reserve."""
    from pokemon_red_completion.red_game_corner_resources import quote_game_corner_prize
    if 137 in runtime.reader.read_pokedex_state().owned_species:
        return economy.cash
    quote=quote_game_corner_prize(rom,species=137,
        coins=runtime.reader.read_game_corner_coins(),cash=economy.cash,
        bag=runtime.reader.read().bag_items)
    return economy.cash if quote is None else max(economy.cash,quote.cash_cost)


@contextmanager
def existing_remaining_acquisitions(*, include_shared_player=False, allow_alternate_trade_transport=False):
    if type(allow_alternate_trade_transport) is not bool:
        raise TypeError('alternate trade transport requires explicit boolean permission')
    if type(include_shared_player) is not bool:
        raise TypeError('shared player alternatives require an explicit boolean')
    from pokemon_red_completion import red_autonomous_collection as collection
    from pokemon_red_completion import red_npc_trade_options as trades
    from pokemon_red_completion import red_item_evolution_options as stones
    from pokemon_red_completion import red_goal_context_profile as profiles
    from pokemon_red_completion import red_player_collection_options as player
    from red_farfetchd_trade_20261004 import farfetchd_trade
    from red_stone_alternatives_20261004 import alternate_stone_catalog, seed_stone_transport
    original = collection.scripted_gift_bindings
    original_funding = collection.autonomous_capture_funding_target_cash
    original_trades = trades.stationary_npc_trades
    original_stones = collection.enumerate_red_item_evolutions
    original_player_stones = player.enumerate_red_item_evolutions
    original_collection_trade_bindings = collection.npc_trade_bindings
    original_player_trade_bindings = player.npc_trade_bindings
    if allow_alternate_trade_transport:
        def alternate_trades(*args, **kwargs):
            return trades.npc_trade_bindings(*args, **dict(kwargs, allow_alternate_transport=True))
        collection.npc_trade_bindings = alternate_trades
        if include_shared_player:
            player.npc_trade_bindings = alternate_trades
    def enumerate_gifts(*args, **kwargs):
        from red_remaining_static_20261004 import local_static_bindings
        from red_dojo_gift_20261004 import local_dojo_gift_bindings
        return (original(*args, **kwargs) + amber_bindings(*args, **kwargs)
                + held_fossil_bindings(*args, **kwargs) + local_static_bindings(*args, **kwargs)
                + local_dojo_gift_bindings(*args, **kwargs))
    collection.scripted_gift_bindings = enumerate_gifts
    def funding_target(runtime,actions,economy):
        import overnight_red_player_20261004 as h
        return max(original_funding(runtime,actions,economy),
            unmet_prize_cash(runtime,economy,h.old.c.ROM.read_bytes()))
    collection.autonomous_capture_funding_target_cash = funding_target
    trades.stationary_npc_trades = lambda rom: original_trades(rom) + (farfetchd_trade(rom),)
    def enumerate_stones(runtime, observation, actions, world, **kwargs):
        original_catalog = stones.RED_ACQUISITION_CATALOG
        original_profile_catalog = profiles.RED_ACQUISITION_CATALOG
        catalog = alternate_stone_catalog(original_catalog, world.rom, observation)
        stones.RED_ACQUISITION_CATALOG = catalog
        # The profile validator checks the same immutable, cartridge-proven
        # alternative catalog,not a permissive parser or an invented edge.
        profiles.RED_ACQUISITION_CATALOG = catalog
        try:
            return original_stones(seed_stone_transport(runtime, observation, catalog),
                observation, actions, world, **kwargs)
        finally:
            stones.RED_ACQUISITION_CATALOG = original_catalog
            profiles.RED_ACQUISITION_CATALOG = original_profile_catalog
    collection.enumerate_red_item_evolutions = enumerate_stones
    if include_shared_player:
        player.enumerate_red_item_evolutions = enumerate_stones
    try:
        yield
    finally:
        collection.scripted_gift_bindings = original
        collection.autonomous_capture_funding_target_cash = original_funding
        trades.stationary_npc_trades = original_trades
        collection.enumerate_red_item_evolutions = original_stones
        player.enumerate_red_item_evolutions = original_player_stones
        collection.npc_trade_bindings = original_collection_trade_bindings
        player.npc_trade_bindings = original_player_trade_bindings
