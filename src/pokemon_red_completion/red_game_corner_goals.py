"""Opt-in affordable prize and Coin Case offers through existing live interfaces."""

from dataclasses import replace
from functools import partial

from .gen1_acquisition import game_corner_prizes
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import Gen1TrainerSightProjector
from .goal_manager import (
    GoalAvailability,
    GoalFailureReason,
    GoalKind,
    GoalOpportunity,
    GoalUnavailableReason,
)
from .goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from .living_dex_goal_policy import project_living_dex_goal_candidate
from .observation import event_flag_is_set
from .red_game_corner_execution import (
    COIN_CASE,
    DINER,
    GAME_CORNER,
    PRIZE_ROOM,
    buy_coin_lot,
    coin_case_gift_contract,
    collect_coin_case,
    receive_pokemon_prize,
)
from .red_game_corner_resources import authenticate_coin_vendor, quote_game_corner_prize
from .red_live_option_menu import supplemental_live_option
from .red_pc_storage import face_pc_boundary
from .red_resource_goal_router import collection_field_capabilities
from .red_training_ground_route import RedVermilionGroundTransition
from .resource_economy_observation import EconomyMode, EconomyOffer
from .route_plan import RoutePlanningError


def game_corner_options(
    runtime,
    observation,
    actions,
    world,
    *,
    situation,
    model_feature_version,
    maximum_actions,
    maximum_frames,
    cash_reserve=0,
):
    """Observe feasibility without input; all targets remain executor-private.

    Coin Case is a free resource prerequisite, not a Pokemon registration.
    Prizes expose actual cash spending and a normalized secondary-currency cost
    through existing identity-free features; no fabricated cash/coin equivalence.
    """
    if type(cash_reserve) is not int or cash_reserve < 0:
        raise ValueError("Game Corner cash reserve must be a nonnegative integer")
    raw = observation.raw
    if (
        raw.battle_state != 0
        or not observation.input_ready
        or runtime.reader.read_bottom_dialogue_box_visible()
        or raw.bag_items is None
    ):
        return ()
    reader = runtime.reader
    case = dict(raw.bag_items).get(COIN_CASE, 0) == 1
    coins = reader.read_game_corner_coins()
    observer = Gen1TraversalObserver(
        reader,
        capability_projector=partial(
            collection_field_capabilities, runtime.emulator, allow_cut=True, allow_surf=False
        ),
        hazard_projector=Gen1TrainerSightProjector(world.rom, reader, full_event_offsets=True),
    )
    start = observer.observe()
    route = RedVermilionGroundTransition(
        rom=world.rom,
        route_world=world,
        full_event_offsets=True,
        observe_terrain=True,
        maximum_flees=16,
        allow_wild_faints=True,
        allow_field_faint_dialogue=True,
    )
    offers = []
    if not case:
        flag = coin_case_gift_contract(world.rom)
        if (
            len(dict(raw.bag_items)) >= 20
            or raw.event_flags is None
            or event_flag_is_set(raw.event_flags, flag)
        ):
            return ()
        try:
            plan = world.plan_feasible_to_map(start, DINER, goal_at=(1, 1))
        except RoutePlanningError:
            return ()
        offers.append((None, plan, None))
    else:
        boxes = reader.read_all_box_states()
        registered = reader.read_pokedex_state().owned_species
        if raw.party_count >= 6 and len(boxes.boxes[boxes.current_box_index].species_ids) >= 20:
            return ()
        for index, prize in enumerate(game_corner_prizes(world.rom)):
            if prize.species in registered:
                continue
            quote = quote_game_corner_prize(
                world.rom,
                species=prize.species,
                coins=coins,
                cash=raw.player_money,
                bag=raw.bag_items,
            )
            if quote is None or not quote.executable_now:
                continue
            if quote.cash_cost and raw.player_money - quote.cash_cost < cash_reserve:
                continue
            try:
                plan = world.plan_feasible_to_map(
                    start,
                    GAME_CORNER if quote.purchases else PRIZE_ROOM,
                    goal_at=(8, 5) if quote.purchases else (3, 2 + 2 * (index // 3)),
                )
                # The second leg is local Celadon access. It remains replanned
                # from actual post-purchase truth and may not teleport/reload.
            except RoutePlanningError:
                continue
            estimated = 2 * len(plan.steps) + 20 + quote.purchases * 8
            if estimated > maximum_actions or estimated * 200 > maximum_frames:
                continue
            offers.append((prize, plan, quote))
    result = []
    for prize, plan, quote in offers:
        source = runtime.emulator.save_state_bytes()

        def bind(prize=prize, plan=plan, quote=quote, source=source):
            used = False
            terminal = None

            def execute():
                nonlocal used, terminal
                if used or runtime.emulator.save_state_bytes() != source:
                    raise ValueError("Game Corner offer is stale or consumed")
                used = True
                before_actions, before_frames = (
                    actions.actions_executed,
                    runtime.emulator.frame_count,
                )
                before_cash = reader.read().player_money
                if prize is None:
                    replace(route, destination_map=DINER, destination_at=(1, 1))(
                        actions, reader, runtime.emulator
                    )
                    face_pc_boundary(actions, reader, "left")
                    receipt = collect_coin_case(actions, reader, rom=world.rom)
                else:
                    if quote.purchases:
                        replace(route, destination_map=GAME_CORNER, destination_at=(8, 5))(
                            actions, reader, runtime.emulator
                        )
                        face_pc_boundary(actions, reader, "up")
                        for _ in range(quote.purchases):
                            buy_coin_lot(actions, reader, rom=world.rom)
                    index = next(
                        i
                        for i, p in enumerate(game_corner_prizes(world.rom))
                        if p.species == prize.species
                    )
                    replace(
                        route, destination_map=PRIZE_ROOM, destination_at=(3, 2 + 2 * (index // 3))
                    )(actions, reader, runtime.emulator)
                    face_pc_boundary(actions, reader, "up")
                    receipt = receive_pokemon_prize(
                        actions, reader, rom=world.rom, species=prize.species
                    )
                debit = before_cash - reader.read().player_money
                if debit != (0 if quote is None else quote.cash_cost):
                    raise RuntimeError("Game Corner route/transaction cash accounting differs")
                terminal = runtime.emulator.save_state_bytes()
                return GoalExecutionReport(
                    actions.actions_executed - before_actions,
                    runtime.emulator.frame_count - before_frames,
                    dict(
                        mechanic="game_corner",
                        receipt=receipt,
                        cash_debit=debit,
                        execution_owner="deterministic_native_support",
                        learned_tactics=False,
                        disclosed_cash_reserve=cash_reserve,
                        cash_reserve_learned=False,
                    ),
                )

            def verify(report):
                if (
                    used
                    and terminal is not None
                    and runtime.emulator.save_state_bytes() == terminal
                    and report.actions_executed > 0
                    and reader.read_input_readiness().ready
                    and not reader.read_bottom_dialogue_box_visible()
                    and not runtime.emulator.pressed_buttons
                ):
                    return GoalVerification.succeeded()
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

            return ExecutableGoalBinding(
                binding_ref="red-game-corner:"
                + ("coin-case" if prize is None else str(prize.species)),
                kind=GoalKind.RESUPPLY if prize is None else GoalKind.ACQUIRE_SPECIES,
                estimated_effort=min(
                    1.0,
                    (2 * len(plan.steps) + 20 + (0 if quote is None else quote.purchases * 8))
                    / 1000,
                ),
                estimated_risk=0.0,
                execute=execute,
                verify=verify,
                maximum_cash_debit=0 if quote is None else quote.cash_cost,
                search_source_ref=None
                if prize is None
                else "pokemon.red:game-corner-prize:" + str(prize.species),
            )

        binding = bind()
        unavailable = GoalOpportunity(
            binding_ref="game-corner:other-kind",
            kind=GoalKind.EXPLORE,
            availability=GoalAvailability.UNAVAILABLE,
            unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
        )
        question = GoalBindingSet((binding.opportunity, unavailable), (binding,)).question(
            situation
        )
        candidate = project_living_dex_goal_candidate(
            question, 0, feature_version=model_feature_version, binding_ref=binding.binding_ref
        )
        if candidate is None:
            raise ValueError("Game Corner lacks portable projection")
        if prize is not None:
            candidate = replace(
                candidate,
                features=replace(
                    candidate.features,
                    resource_cost=min(1.0, prize.cost / max(1, quote.coins_after_purchase)),
                ),
                economy_offer=EconomyOffer(
                    mode=EconomyMode.PURCHASE if quote.cash_cost else EconomyMode.OTHER,
                    conditional_income=0,
                    planned_spend=quote.cash_cost,
                ),
            )
        result.append(supplemental_live_option(binding, candidate))
    return tuple(result)


def game_corner_funding_target_cash(runtime, world):
    """Actual cash liquidity for the least expensive missing native prize."""
    raw = runtime.reader.read()
    if raw.bag_items is None or dict(raw.bag_items).get(COIN_CASE, 0) != 1:
        return 0
    coins = runtime.reader.read_game_corner_coins()
    registered = runtime.reader.read_pokedex_state().owned_species
    costs = [
        quote.cash_cost
        for prize in game_corner_prizes(world.rom)
        if prize.species not in registered
        if (
            quote := quote_game_corner_prize(
                world.rom,
                species=prize.species,
                coins=coins,
                cash=raw.player_money,
                bag=raw.bag_items,
            )
        )
        is not None
    ]
    return min(costs, default=0)


def game_corner_coin_options(
    runtime,
    observation,
    actions,
    world,
    *,
    situation,
    model_feature_version,
    maximum_actions,
    maximum_frames,
    cash_reserve=0,
):
    """Offer affordable progress toward a real, currently unaffordable prize.

    No wager, cash/coin equivalence, or registration credit is invented. The
    model chooses the purchase goal; cartridge prices determine its quantity.
    Fully funded prizes remain in the ordinary acquisition inventory.
    """
    if type(cash_reserve) is not int or cash_reserve < 0:
        raise ValueError("Game Corner cash reserve must be a nonnegative integer")
    raw = observation.raw
    reader = runtime.reader
    if (
        raw.battle_state != 0
        or not observation.input_ready
        or reader.read_bottom_dialogue_box_visible()
        or raw.bag_items is None
        or dict(raw.bag_items).get(COIN_CASE, 0) != 1
    ):
        return ()
    _, lot, price, refusal, capacity = authenticate_coin_vendor(world.rom)
    coins = reader.read_game_corner_coins()
    if coins >= refusal or raw.player_money < price:
        return ()
    registered = reader.read_pokedex_state().owned_species
    unmet = []
    for prize in game_corner_prizes(world.rom):
        if prize.species in registered:
            continue
        quote = quote_game_corner_prize(
            world.rom, species=prize.species, coins=coins, cash=raw.player_money, bag=raw.bag_items
        )
        if quote is not None and not quote.executable_now:
            unmet.append(quote)
    if not unmet:
        return ()
    purchases = min(min(q.purchases for q in unmet), max(0, (raw.player_money-cash_reserve)//price))
    if purchases == 0:
        return ()
    cost = purchases * price
    expected_coins = min(capacity, coins + purchases * lot)
    observer = Gen1TraversalObserver(
        reader,
        capability_projector=partial(
            collection_field_capabilities, runtime.emulator, allow_cut=True, allow_surf=False
        ),
        hazard_projector=Gen1TrainerSightProjector(world.rom, reader, full_event_offsets=True),
    )
    try:
        plan = world.plan_feasible_to_map(observer.observe(), GAME_CORNER, goal_at=(8, 5))
    except RoutePlanningError:
        return ()
    effort = 2 * len(plan.steps) + 20 + purchases * 8
    if effort > maximum_actions or effort * 200 > maximum_frames:
        return ()
    route = RedVermilionGroundTransition(
        rom=world.rom,
        route_world=world,
        full_event_offsets=True,
        observe_terrain=True,
        maximum_flees=16,
        allow_wild_faints=True,
        allow_field_faint_dialogue=True,
        destination_map=GAME_CORNER,
        destination_at=(8, 5),
    )
    source = runtime.emulator.save_state_bytes()
    used, terminal, completed = False, None, None

    def execute():
        nonlocal used, terminal, completed
        if used or runtime.emulator.save_state_bytes() != source:
            raise ValueError("Game Corner coin offer is stale or consumed")
        used = True
        before_actions, before_frames = actions.actions_executed, runtime.emulator.frame_count
        route(actions, reader, runtime.emulator)
        face_pc_boundary(actions, reader, "up")
        for _ in range(purchases):
            buy_coin_lot(actions, reader, rom=world.rom)
        debit = raw.player_money - reader.read().player_money
        if debit != cost or reader.read_game_corner_coins() != expected_coins:
            raise RuntimeError("Game Corner partial purchase accounting differs")
        terminal = runtime.emulator.save_state_bytes()
        completed = GoalExecutionReport(
            actions.actions_executed - before_actions,
            runtime.emulator.frame_count - before_frames,
            dict(
                mechanic="game_corner_coin_procurement",
                purchases=purchases,
                cash_debit=debit,
                coins_before=coins,
                coins_after=expected_coins,
                registration_credit=False,
                actual_unfunded_prize=True,
                execution_owner="deterministic_native_support",
                learned_quantity=False,
                disclosed_cash_reserve=cash_reserve,
                cash_reserve_learned=False,
            ),
        )
        return completed

    def verify(report):
        if (
            used
            and completed is not None
            and report is completed
            and terminal == runtime.emulator.save_state_bytes()
            and report.actions_executed > 0
            and reader.read_input_readiness().ready
            and not reader.read_bottom_dialogue_box_visible()
            and not runtime.emulator.pressed_buttons
            and reader.read().player_money == raw.player_money - cost
            and reader.read().player_money >= cash_reserve
            and reader.read_game_corner_coins() == expected_coins
        ):
            return GoalVerification.succeeded()
        return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

    binding = ExecutableGoalBinding(
        binding_ref="red-game-corner:coin-procurement",
        kind=GoalKind.RESUPPLY,
        estimated_effort=min(1.0, effort / 1000),
        estimated_risk=0.0,
        execute=execute,
        verify=verify,
        maximum_cash_debit=cost,
    )
    unavailable = GoalOpportunity(
        binding_ref="coin-procurement:other-kind",
        kind=GoalKind.EXPLORE,
        availability=GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
    )
    question = GoalBindingSet((binding.opportunity, unavailable), (binding,)).question(situation)
    candidate = project_living_dex_goal_candidate(
        question, 0, feature_version=model_feature_version, binding_ref=binding.binding_ref
    )
    if candidate is None:
        raise ValueError("Coin procurement lacks portable projection")
    candidate = replace(
        candidate,
        economy_offer=EconomyOffer(
            mode=EconomyMode.PURCHASE, conditional_income=0, planned_spend=cost
        ),
    )
    return (supplemental_live_option(binding, candidate),)
