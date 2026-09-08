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
    trainer_headers,
    trainer_sight_zones,
)
from .gen1_traversal import map_object_events
from .global_router import MacroPath
from .goal_manager import GoalFailureReason, GoalKind
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
from .red_goal_skills import RedMartResupplyGoalProvider
from .red_pc_storage import face_pc_boundary
from .red_routed_recovery import RecoveryRouteInterruptionHandler
from .red_trainer_funding import TrainerFundingCandidate, local_trainer_funding_candidates
from .route_executor import execute_route
from .route_plan import RoutePlan

if TYPE_CHECKING:
    from .red_resource_goal_router import RedResourceGoalRouter


class RedTrainerFundingError(RuntimeError):
    """A trainer income opportunity or its retained state is no longer valid."""


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
        trainer_party_quote(rom, opponent, trainer_set),
        RoutePlan(MacroPath((raw.map_id,), ()), at, None, (), None, at, None),
        facing,
    )


def _candidates(router: RedResourceGoalRouter) -> tuple[TrainerFundingCandidate, ...]:
    reader, rom = router.runtime.reader, router.world.rom
    raw = reader.read()
    if raw.map_id is None:
        return ()
    zones = trainer_sight_zones(
        trainer_headers(rom, {raw.map_id}),
        map_object_events(rom, {raw.map_id}),
        raw,
        reader.read_current_map_objects(),
    )
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
    start = Gen1TraversalObserver(reader, Gen1TrainerSightProjector(rom, reader)).observe()
    return local_trainer_funding_candidates(rom, router.world, start, zones)


def bind_local_trainer_funding(
    router: RedResourceGoalRouter,
    bindings: GoalBindingSet,
    observation: RedGoalObservation,
) -> GoalBindingSet:
    """Replace only an unavailable cash-only Mart option; preserve all alternatives."""
    if any(b.kind is GoalKind.RESUPPLY for b in bindings.bindings):
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
        or not 0 <= raw.player_money < provider.purchases[0].unit_price
        or raw.event_flags is None
        or raw.bag_items is None
        or not raw.party_hp
        or len(raw.party_hp) != observation.party.size
        or any(hp <= 0 for hp in raw.party_hp)
    ):
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
    candidates = tuple(
        c
        for c in _candidates(router)
        if level >= max(m.level for m in c.quote.party) + 10
        and c.quote.expected_money_after(raw.player_money) >= provider.purchases[0].unit_price
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
    target = max(
        candidates,
        key=lambda c: (
            c.quote.expected_victory_money / (len(c.approach.steps) + 10 * len(c.quote.party))
        ),
    )
    runtime, actions = router.runtime, router.actions
    ledger = dependency_specimen_ledger(observation.collection_observation)
    before_party, before_money, before_bag = observation.party, raw.player_money, raw.bag_items
    original_at = (raw.map_id, raw.player_y, raw.player_x)
    claimed = False
    completed_report: GoalExecutionReport | None = None
    final_party_species: tuple[int, ...] = ()

    def require_target() -> None:
        current = runtime.reader.read()
        t = target.trainer
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
        if trainer_party_quote(router.world.rom, t.trainer_class, t.trainer_set) != target.quote:
            raise RedTrainerFundingError("trainer roster/reward changed before interaction")

    def execute() -> GoalExecutionReport:
        nonlocal claimed, completed_report, final_party_species
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
        require_target()
        action_start, frame_start = actions.actions_executed, runtime.emulator.frame_count
        if runtime.reader.read_pending_trainer_battle_identity() != pending_identity:
            raise RedTrainerFundingError("pending trainer transition changed before input")
        if pending_identity is None:
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
            runtime.reader, Gen1TrainerSightProjector(router.world.rom, runtime.reader)
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
        if pending_identity is None:
            face_pc_boundary(actions, runtime.reader, target.interaction_facing.value)
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
            }
        ),
        kind=GoalKind.RESUPPLY,
        resource_quote=GoalResourceQuote(
            before_money,
            0,
            (),
            expected_income=target.quote.expected_money_after(before_money) - before_money,
        ),
        estimated_effort=min(1.0, 0.15 + len(target.approach.steps) / 256),
        estimated_risk=0.15,
        execute=execute,
        verify=verify,
    )
    return GoalBindingSet(
        tuple(
            binding.opportunity if o.kind is GoalKind.RESUPPLY else o
            for o in bindings.opportunities
        ),
        (*bindings.bindings, binding),
    )
