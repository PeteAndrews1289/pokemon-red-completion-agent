"""Opt-in finite trainer income for an otherwise unaffordable ball reserve.

One semantic RESUPPLY option earns funds through an ordinary trainer. It does
not pretend balls were purchased, choose a model action, or fit a support label.
Existing route/battle skills own controls; a fresh verifier owns success.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

from .battle_runtime import DEFAULT_BATTLE_RUNTIME_TIMING
from .gen1_route_runtime import Gen1TraversalObserver, Gen1WildFleeHandler
from .gen1_trainer_parties import trainer_party_quote
from .gen1_trainer_sight import (
    Gen1TrainerSightProjector,
    TrainerFacing,
    static_trainer_sight_zones,
    trainer_headers,
    trainer_sight_zones,
)
from .gen1_traversal import map_object_events
from .global_router import MacroPath
from .goal_manager import GoalAvailability, GoalFailureReason, GoalKind
from .goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from .goal_resource_quote import GoalResourceQuote
from .observation import PokemonRedStateReader, event_flag_is_set
from .provenance import canonical_sha256
from .red_capture_lead import RedCaptureLeadError, plan_capture_lead
from .red_capture_preparation import prepare_capture_escort
from .red_dual_capability_curriculum_runtime import dependency_specimen_ledger
from .red_goal_manager import RedGoalObservation
from .red_goal_skills import (
    _POKEMON_CENTER_MAPS,
    RedMartResupplyGoalProvider,
    prepare_center_departure,
)
from .red_pc_storage import ActionExecutor, RedPCStorageError, face_pc_boundary
from .red_regional_trainer_funding import (
    funding_scope,
    regional_trainer_funding_candidates,
)
from .red_routed_recovery import RecoveryRouteInterruptionHandler
from .red_trainer_funding import TrainerFundingCandidate, local_trainer_funding_candidates
from .route_executor import InterruptionReceipt, execute_route
from .route_plan import RoutePlan

if TYPE_CHECKING:
    from .red_funding_fly import FundingFlyCandidate
    from .red_resource_goal_router import RedResourceGoalRouter
    from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


class RedTrainerFundingError(RuntimeError):
    """A trainer income opportunity or its retained state is no longer valid."""


def _face_trainer_boundary(
    actions: ActionExecutor,
    reader: PokemonRedStateReader,
    direction: str,
) -> InterruptionReceipt | None:
    """Face an adjacent trainer, settling one wild encounter caused by the turn.

    Gen I may roll a grass encounter while a blocked directional input merely
    turns the player toward an occupied trainer tile.  The walking route has
    already ended at that point, so its interruption handler cannot own this
    final input.  Preserve the exact interaction square, flee once through the
    ordinary bounded mechanic, and prove that the intended facing survived.
    """

    before = reader.read()
    try:
        face_pc_boundary(actions, reader, direction)
    except RedPCStorageError as error:
        interruption = Gen1TraversalObserver(reader).observe()
        if (
            interruption.interruption != "wild_battle"
            or interruption.map_id != before.map_id
            or interruption.at != (before.player_y, before.player_x)
        ):
            raise RedTrainerFundingError(
                "trainer facing failed outside an unchanged wild interruption"
            ) from error
        receipt = Gen1WildFleeHandler(
            actions,
            reader,
            maximum_flees=1,
            stabilization_frames=180,
            route_name="ordinary trainer funding facing",
        ).handle(interruption)
        after = reader.read()
        if (
            receipt.kind != "wild_battle"
            or receipt.resumed_map != before.map_id
            or receipt.resumed_at != (before.player_y, before.player_x)
            or (after.map_id, after.player_y, after.player_x)
            != (before.map_id, before.player_y, before.player_x)
            or after.battle_state != 0
            or not reader.read_input_readiness().ready
            or reader.read_bottom_dialogue_box_visible()
            or reader.read_player_facing() != direction
        ):
            raise RedTrainerFundingError(
                "wild interruption did not restore the trainer interaction boundary"
            ) from error
        return receipt
    return None


def _funding_flights_enabled(router: RedResourceGoalRouter) -> bool:
    return getattr(router, "regional_trainer_funding", False) and any(
        spec.kind is GoalKind.RESUPPLY and spec.parameters.get("funding_fly_transport") is True
        for spec in router.runtime.profile.providers
    )


def _execute_funding_flight(
    router: RedResourceGoalRouter, selected: FundingFlyCandidate,
) -> None:
    """Recheck a frozen destination, then verify its landing before any onward walk."""
    from .actions import MacroAction, MacroActionKind
    from .gen1_field_moves import Gen1FieldMovePort
    from .goal_manager_composition_qualification import HardCompositionActionLimiter
    from .observation import RED_FLY_TOWN_NAMES, OverworldMovementMode
    from .red_funding_fly import funding_fly_candidates

    if selected not in funding_fly_candidates(router):
        raise RedTrainerFundingError("funding flight quote changed before input")
    actions = HardCompositionActionLimiter(
        router.actions,
        maximum_actions_per_decision=min(256, router.maximum_controller_actions),
        maximum_episode_actions=min(256, router.maximum_controller_actions),
    )
    runtime = router.runtime
    port = Gen1FieldMovePort(actions, runtime.reader, runtime.emulator)
    port.execute(MacroAction(
        MacroActionKind.FIELD_MOVE,
        "fly:" + RED_FLY_TOWN_NAMES[selected.town].lower().replace(" ", "_"),
    ))
    current = runtime.adapter.observe()
    if (
        len(port.fly_receipts) != 1 or not current.input_ready or current.raw.battle_state != 0
        or (current.raw.map_id, current.raw.player_y, current.raw.player_x)
        != (selected.town, *selected.landing)
        or runtime.reader.read_overworld_movement_mode() is not OverworldMovementMode.WALKING
        or runtime.reader.read_bottom_dialogue_box_visible()
        or runtime.reader.read_pending_trainer_battle_identity() is not None
    ):
        raise RedTrainerFundingError("funding Fly landing differs; no onward route permitted")


def active_trainer_funding_candidate(
    rom: bytes, reader: PokemonRedStateReader
) -> TrainerFundingCandidate:
    """Identify an already-active ordinary battle for zero-label failure recovery.

    This does not advertise a new player goal or move out of a trainer sight lane.
    Only a unique adjacent cartridge trainer matching stable combat identity fits.
    """
    raw = reader.read()
    if raw.battle_state != 2 or raw.map_id is None or raw.player_y is None or raw.player_x is None:
        raise RedTrainerFundingError("funding recovery requires an active trainer battle")
    opponent, trainer_class, trainer_set = reader.read_active_trainer_identity()
    if opponent != trainer_class + 200 or trainer_set <= 0:
        raise RedTrainerFundingError("active trainer identity is inconsistent")
    facing = TrainerFacing(reader.read_player_facing())
    dy, dx = facing.delta
    at = (raw.player_y, raw.player_x)
    zones = trainer_sight_zones(
        trainer_headers(rom, {raw.map_id}, full_event_offsets=True),
        map_object_events(rom, {raw.map_id}),
        raw,
        reader.read_current_map_objects(),
    )
    matches = tuple(
        z
        for z in zones
        if z.visible
        and not z.defeated
        and (z.trainer_class, z.trainer_set) == (opponent, trainer_set)
        and z.at == (at[0] + dy, at[1] + dx)
    )
    if len(matches) != 1:
        raise RedTrainerFundingError("active trainer has no unique adjacent cartridge binding")
    return TrainerFundingCandidate(
        matches[0],
        (
            trainer_party_quote(rom, opponent, trainer_set, allow_final_class=True)
            if opponent == 247
            else trainer_party_quote(rom, opponent, trainer_set)
        ),
        RoutePlan(MacroPath((raw.map_id,), ()), at, None, (), None, at, None),
        facing,
    )


def _candidates(
    router: RedResourceGoalRouter, *, world: StrategicScenarioRouteWorld | None = None,
) -> tuple[TrainerFundingCandidate, ...]:
    observed = world is None and getattr(router, "observed_trainer_funding", False)
    world = router.world if world is None else world
    reader, rom = router.runtime.reader, router.world.rom
    raw = reader.read()
    if raw.map_id is None:
        return ()
    regional = getattr(router, "regional_trainer_funding", False)
    headers = trainer_headers(rom, {raw.map_id}, full_event_offsets=regional)
    zones = trainer_sight_zones(
        headers,
        map_object_events(rom, {raw.map_id}),
        raw,
        reader.read_current_map_objects(),
    )
    if regional and len(zones) != len(headers):
        raise RedTrainerFundingError("regional funding lacks a complete live trainer inventory")
    pending = reader.read_pending_trainer_battle_identity()
    if pending is not None and router.trainer_pending_recovery:
        # Talking turns the trainer toward the player, so the retained square
        # is now inside its sight lane. Do not route out/re-enter or clear that
        # hazard: recover only the exact already-armed adjacent interaction.
        if raw.player_y is None or raw.player_x is None:
            return ()
        at = (raw.player_y, raw.player_x)
        facing = TrainerFacing(reader.read_player_facing())
        dy, dx = facing.delta
        matches = tuple(
            zone
            for zone in zones
            if (zone.trainer_class, zone.trainer_set) == pending
            and zone.visible
            and not zone.defeated
            and zone.at == (at[0] + dy, at[1] + dx)
        )
        if len(matches) != 1:
            return ()
        return (
            TrainerFundingCandidate(
                matches[0],
                trainer_party_quote(rom, *pending),
                RoutePlan(MacroPath((raw.map_id,), ()), at, None, (), None, at, None),
                facing,
            ),
        )
    start = Gen1TraversalObserver(
        reader, Gen1TrainerSightProjector(rom, reader, full_event_offsets=regional)
    ).observe()
    if observed:
        blocks = reader.read_current_map_blocks()
        if (
            blocks.map_id != raw.map_id or start.map_id != raw.map_id
            or start.at != (raw.player_y, raw.player_x)
            or not start.ready or start.interruption is not None
        ):
            raise RedTrainerFundingError("observed funding menu does not match active field")
        world = world.with_current_blocks(blocks)
        if reader.read() != raw or reader.read_current_map_blocks() != blocks:
            raise RedTrainerFundingError("funding menu state changed during terrain projection")
    if regional:
        if raw.event_flags is None:
            return ()
        indoor_exit = (
            start.last_outside_map if _indoor_funding_enabled(router)
            and raw.map_id in _POKEMON_CENTER_MAPS else None
        )
        if indoor_exit is None:
            from .red_declared_funding_departure import declared_mart_funding_exit

            indoor_exit = declared_mart_funding_exit(router.runtime.profile, start)
        maps = funding_scope(world.macro_graph, start, indoor_exit_map=indoor_exit)
        for map_id in sorted(maps - {raw.map_id}):
            zones += static_trainer_sight_zones(
                trainer_headers(rom, {map_id}, full_event_offsets=True),
                map_object_events(rom, {map_id}),
                raw.event_flags,
            )
        return regional_trainer_funding_candidates(
            rom,
            world,
            start,
            zones,
            inventoried_maps=maps,
            indoor_exit_map=indoor_exit,
            static_blockers=(
                {m: world.object_blockers[m] for m in maps}
                if _funding_flights_enabled(router) else None
            ),
        )
    return local_trainer_funding_candidates(rom, world, start, zones)


def _indoor_funding_enabled(router: RedResourceGoalRouter) -> bool:
    return any(
        spec.kind is GoalKind.RESUPPLY
        and spec.parameters.get("indoor_funding_departure") is True
        for spec in router.runtime.profile.providers
    )


def _observed_funding_target(
    router: RedResourceGoalRouter, target: TrainerFundingCandidate,
) -> TrainerFundingCandidate:
    """Requalify the same quoted trainer before input, keeping old menus stable."""
    reader = router.runtime.reader
    before = reader.read()
    blocks = reader.read_current_map_blocks()
    if before.map_id != blocks.map_id or before.battle_state != 0:
        raise RedTrainerFundingError("funding terrain does not match the active field")
    world = router.world.with_current_blocks(blocks)
    candidates = _candidates(router, world=world)
    if reader.read() != before or reader.read_current_map_blocks() != blocks:
        raise RedTrainerFundingError("funding observation changed during route qualification")
    matches = tuple(
        candidate for candidate in candidates
        if candidate.trainer == target.trainer and candidate.quote == target.quote
    )
    if len(matches) != 1:
        raise RedTrainerFundingError("quoted trainer has no unique observed-terrain approach")
    return matches[0]


def bind_local_trainer_funding(
    router: RedResourceGoalRouter,
    bindings: GoalBindingSet,
    observation: RedGoalObservation,
) -> GoalBindingSet:
    """Retain purchases; an explicit reserve mode may add a separate earning offer."""
    variants = any(
        s.kind is GoalKind.RESUPPLY and s.parameters.get("resource_choice_variants") is True
        for s in router.runtime.profile.providers
    )
    composable_income = any(
        s.kind is GoalKind.RESUPPLY
        and s.parameters.get("composable_trainer_funding") is True
        for s in router.runtime.profile.providers
    )
    purchases = tuple(b for b in bindings.bindings if b.kind is GoalKind.RESUPPLY)
    if bindings.allow_resource_variants or (purchases and not variants):
        return bindings
    if purchases and (
        len(purchases) != 1 or purchases[0].resource_quote is None
        or purchases[0].resource_quote.purchase_cost <= 0
        or purchases[0].resource_quote.expected_income != 0
    ):
        return bindings
    if not any(s.kind is GoalKind.RESUPPLY for s in router.runtime.profile.providers):
        return bindings
    if not any(o.kind is GoalKind.RESUPPLY for o in bindings.opportunities):
        return bindings
    provider = router.runtime.provider_for(GoalKind.RESUPPLY, router.actions)
    raw = observation.raw
    if (
        not isinstance(provider, RedMartResupplyGoalProvider)
        or not provider.affordable_ball_purchase
        or raw.battle_state != 0
        or not observation.input_ready
        or raw.player_money is None
        or raw.player_money < 0
        or raw.event_flags is None
        or raw.bag_items is None
        or not raw.party_hp
        or len(raw.party_hp) != observation.party.size
        or any(hp <= 0 for hp in raw.party_hp)
    ):
        return bindings
    if variants:
        from .red_capture_funding_budget import red_capture_funding_budget

        budget = red_capture_funding_budget(observation, provider)
        if budget is None or budget.shortfall == 0:
            return bindings
        if purchases:
            assert purchases[0].resource_quote is not None
            if purchases[0].resource_quote.available_funds != raw.player_money:
                return bindings
    elif raw.player_money >= provider.purchases[0].unit_price:
        return bindings
    try:
        escort = plan_capture_lead(observation.party)
    except RedCaptureLeadError:
        return bindings
    level = observation.party.members[escort.target_index].level
    pending_identity = (
        router.runtime.reader.read_pending_trainer_battle_identity()
        if router.trainer_pending_recovery
        else None
    )
    quoted: list[tuple[TrainerFundingCandidate, FundingFlyCandidate | None]] = [
        (candidate, None) for candidate in _candidates(router)
    ]
    if _funding_flights_enabled(router):
        from .red_funding_fly import funding_fly_candidates

        quoted.extend((flight.target, flight) for flight in funding_fly_candidates(router))
    candidates = tuple(
        (c, flight)
        for c, flight in quoted
        if level >= max(m.level for m in c.quote.party) + 10
        # Finite trainer rewards may need to compose before even one ball is
        # affordable.  Requiring every individual payout to cross the shop
        # threshold creates a deadlock when several safe, undefeated trainers
        # collectively cover the shortfall.  The active reserve budget above
        # proves that income is needed; this guard requires each selected
        # battle to make irreversible positive progress toward it.
        and (
            composable_income
            or c.quote.expected_money_after(raw.player_money)
            >= provider.purchases[0].unit_price
        )
        and c.quote.expected_money_after(raw.player_money) > raw.player_money
        and (
            pending_identity is None
            or (
                pending_identity == (c.trainer.trainer_class, c.trainer.trainer_set)
                and not c.approach.steps
                and c.approach.terminal_at == (raw.player_y, raw.player_x)
                and escort.target_index == 0
                and router.runtime.reader.read_player_facing() == c.interaction_facing.value
            )
        )
    )
    if not candidates:
        return bindings
    # Skill-internal selection, not learned trainer selection. The model's
    # prospective choice is whether to pursue funding versus another goal.
    target, selected_flight = max(
        candidates,
        key=lambda pair: (
            pair[0].quote.expected_victory_money / (
                len(pair[0].approach.steps) + 10 * len(pair[0].quote.party)
                + (32 if pair[1] is not None else 0)
            )
        ),
    )
    runtime, actions = router.runtime, router.actions
    ledger = dependency_specimen_ledger(observation.collection_observation)
    before_party, before_money, before_bag = observation.party, raw.player_money, raw.bag_items
    original_at = (raw.map_id, raw.player_y, raw.player_x)
    claimed = False
    completed_report: GoalExecutionReport | None = None
    final_party_species: tuple[int, ...] = ()

    def require_target(*, before_departure: bool = False) -> None:
        current = runtime.reader.read()
        t = target.trainer
        if (
            before_departure
            and getattr(router, "regional_trainer_funding", False)
            and current.map_id != t.map_id
        ):
            if current.event_flags is None:
                raise RedTrainerFundingError("remote trainer events are not observed")
            static = static_trainer_sight_zones(
                trainer_headers(router.world.rom, {t.map_id}, full_event_offsets=True),
                map_object_events(router.world.rom, {t.map_id}),
                current.event_flags,
            )
            if t not in static or t.defeated:
                raise RedTrainerFundingError("remote trainer quote changed before departure")
            if (
                trainer_party_quote(router.world.rom, t.trainer_class, t.trainer_set)
                != target.quote
            ):
                raise RedTrainerFundingError(
                    "remote trainer roster/reward changed before departure"
                )
            return
        if (
            current.map_id != t.map_id
            or current.event_flags is None
            or event_flag_is_set(current.event_flags, t.event_flag)
        ):
            raise RedTrainerFundingError("trainer map or defeated event changed before interaction")
        zones = trainer_sight_zones(
            # Fresh execution must check the real defeated bit even while old
            # checkpoint menus retain their historical decode. An aliased old
            # quote is rejected before input, never silently reinterpreted.
            trainer_headers(router.world.rom, {t.map_id}, full_event_offsets=True),
            map_object_events(router.world.rom, {t.map_id}),
            current,
            runtime.reader.read_current_map_objects(),
        )
        actual = next((z for z in zones if z.sprite_index == t.sprite_index), None)
        if actual is None or (
            actual.trainer_class,
            actual.trainer_set,
            actual.at,
            actual.event_flag,
            actual.defeated,
        ) != (t.trainer_class, t.trainer_set, t.at, t.event_flag, False):
            raise RedTrainerFundingError("trainer binding changed before interaction")
        if (
            current.player_y,
            current.player_x,
        ) == target.approach.terminal_at and not actual.visible:
            raise RedTrainerFundingError("trainer is not visible at interaction boundary")
        if (
            getattr(router, "regional_trainer_funding", False)
            and pending_identity is None
            and actual.active
            and (current.player_y, current.player_x) in actual.lane
        ):
            raise RedTrainerFundingError("trainer turned toward the reserved interaction boundary")
        if trainer_party_quote(router.world.rom, t.trainer_class, t.trainer_set) != target.quote:
            raise RedTrainerFundingError("trainer roster/reward changed before interaction")

    def execute() -> GoalExecutionReport:
        nonlocal claimed, completed_report, final_party_species, target
        if claimed:
            raise RedTrainerFundingError("trainer funding binding already consumed")
        claimed = True
        current = runtime.adapter.observe()
        if (
            current.party != before_party
            or current.raw.player_money != before_money
            or current.raw.bag_items != before_bag
            or (current.raw.map_id, current.raw.player_y, current.raw.player_x) != original_at
            or current.raw.battle_state != 0
            or not current.input_ready
            or dependency_specimen_ledger(current.collection_observation) != ledger
        ):
            raise RedTrainerFundingError("trainer funding origin changed before input")
        require_target(before_departure=True)
        action_start, frame_start = actions.actions_executed, runtime.emulator.frame_count
        if runtime.reader.read_pending_trainer_battle_identity() != pending_identity:
            raise RedTrainerFundingError("pending trainer transition changed before input")
        if pending_identity is None:
            if selected_flight is not None:
                _execute_funding_flight(router, selected_flight)
            target = _observed_funding_target(router, target)
            require_target(before_departure=True)
            if _indoor_funding_enabled(router):
                prepare_center_departure(actions, runtime.reader)
            prepare_capture_escort(runtime, actions)
        prepared_raw = runtime.reader.read()
        final_party_species = tuple(prepared_raw.party_species_ids or ())
        guard = RecoveryRouteInterruptionHandler(
            actions,
            runtime.reader,
            final_party_species,
            tuple(i for i, hp in enumerate(prepared_raw.party_hp or ()) if hp > 0),
            maximum_trainer_battles=0,
        )
        traversal = Gen1TraversalObserver(
            runtime.reader,
            Gen1TrainerSightProjector(
                router.world.rom,
                runtime.reader,
                full_event_offsets=getattr(router, "regional_trainer_funding", False),
            ),
        )
        from .red_resource_goal_router import _ROUTE_LIMITS

        if target.approach.steps:
            route_result = execute_route(
                target.approach,
                actions,
                traversal,
                limits=_ROUTE_LIMITS,
                interruption_handler=Gen1WildFleeHandler(
                    actions,
                    runtime.reader,
                    maximum_flees=8,
                    stabilization_frames=180,
                    route_name="ordinary trainer funding approach",
                ),
            )
            if not route_result.passed:
                raise RedTrainerFundingError("trainer funding approach failed")
        guard._require_preserved_living_slots(runtime.reader.read())
        require_target()
        facing_interruption = None
        if pending_identity is None:
            facing_interruption = _face_trainer_boundary(
                actions, runtime.reader, target.interaction_facing.value
            )
            require_target()
        from .red_trainer_funding_battle import run_prepared_trainer_funding

        receipt = run_prepared_trainer_funding(
            runtime.reader,
            actions,
            target=target,
            validate_target=require_target,
            move_slot_policy=guard._safe_trainer_move,
            timing=DEFAULT_BATTLE_RUNTIME_TIMING,
        )
        completed_report = GoalExecutionReport(
            actions.actions_executed - action_start,
            runtime.emulator.frame_count - frame_start,
            {
                "trainer_funding": {
                    "map_id": target.trainer.map_id,
                    "sprite_index": target.trainer.sprite_index,
                    "event_flag": target.trainer.event_flag,
                    "quote": asdict(target.quote),
                    "initial_money": receipt.initial_money,
                    "final_money": receipt.final_money,
                    "payout": receipt.payout,
                },
                "finite_income": True,
                "balls_purchased": 0,
                **({"funding_transport": {"verified_flights": 1}}
                   if selected_flight is not None else {}),
                **(
                    {
                        "funding_facing_interruption": {
                            "kind": facing_interruption.kind,
                            "resumed_map": facing_interruption.resumed_map,
                            "resumed_at": list(facing_interruption.resumed_at),
                            "details": dict(facing_interruption.details),
                        }
                    }
                    if facing_interruption is not None
                    else {}
                ),
            },
        )
        return completed_report

    def verify(report: GoalExecutionReport) -> GoalVerification:
        current = runtime.adapter.observe()
        final = current.raw
        t = target.trainer
        quote = trainer_party_quote(router.world.rom, t.trainer_class, t.trainer_set)
        if (
            completed_report is None
            or report is not completed_report
            or quote != target.quote
            or final.battle_state != 0
            or final.battle_result != 0
            or not current.input_ready
            or runtime.reader.read_bottom_dialogue_box_visible()
            or (final.map_id, final.player_y, final.player_x)
            != (t.map_id, *target.approach.terminal_at)
            or not event_flag_is_set(final.event_flags, t.event_flag)
            or final.player_money != quote.expected_money_after(before_money)
            or final.bag_items != before_bag
            or tuple(final.party_species_ids or ()) != final_party_species
            or not final.party_hp
            or len(final.party_hp) != len(final_party_species)
            or any(hp <= 0 for hp in final.party_hp)
            or dependency_specimen_ledger(current.collection_observation) != ledger
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    binding = ExecutableGoalBinding(
        binding_ref="red-trainer-funding:"
        + canonical_sha256(
            {
                "map": target.trainer.map_id,
                "event": target.trainer.event_flag,
                "money": before_money,
                "quote": asdict(target.quote),
                "origin": original_at,
                **({"fly_town": selected_flight.town, "fly_landing": selected_flight.landing}
                   if selected_flight is not None else {}),
            }
        ),
        kind=GoalKind.RESUPPLY,
        resource_quote=GoalResourceQuote(
            before_money,
            0,
            (),
            expected_income=target.quote.expected_money_after(before_money) - before_money,
        ),
        estimated_effort=min(1.0, 0.15 + len(target.approach.steps) / 256
                             + (0.2 if selected_flight is not None else 0)),
        estimated_risk=0.15,
        execute=execute,
        verify=verify,
    )
    return GoalBindingSet(
        (tuple(
            o for o in bindings.opportunities
            if o.kind is not GoalKind.RESUPPLY or o.availability is GoalAvailability.AVAILABLE
        ) + (binding.opportunity,)) if purchases else tuple(
            binding.opportunity if o.kind is GoalKind.RESUPPLY else o
            for o in bindings.opportunities
        ),
        (*bindings.bindings, binding),
        allow_resource_variants=bool(purchases),
    )
