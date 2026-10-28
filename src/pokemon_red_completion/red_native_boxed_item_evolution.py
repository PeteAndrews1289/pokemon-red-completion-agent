"""Native typed composition for boxed item evolution after model selection.

Readiness proves the entire Mart -> PC -> item-use pipeline without controller
input.  Procurement remains a distinct first stage and is executed only by the
selected evolution binding; constructing or rejecting the option never spends
money or advances the emulator.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import cast

from . import red_goal_context as context
from .executor import CountingExecutor
from .gen1_cartridge import EvolutionMethod, evolution_graph, level_up_learnsets
from .gen1_route_runtime import Gen1TraversalObserver, Gen1WildFleeHandler
from .goal_manager import GoalKind, GoalUnavailableReason
from .goal_manager_runtime import GoalExecutionReport
from .observation import MAX_BAG_ITEMS, ItemId, MapId
from .red_evolution_stones import BUYABLE_EVOLUTION_STONES, EVOLUTION_STONE_ITEMS
from .red_goal_skills import prepare_center_departure
from .red_native_boxed_evolution import restore_native_center_party, settle_native_evolution
from .red_party_item_evolution import (
    RedPartyItemEvolutionExecutor,
    RedPartyItemEvolutionRequest,
)
from .red_pc_storage import (
    close_generic_pc_session,
    deposit_party_member,
    face_pc_boundary,
    open_bills_pc,
    switch_box,
    withdraw_box_member,
)
from .route_executor import execute_route
from .route_plan import RoutePlanningError
from .saffron import DEFAULT_SAFFRON_TIMING, purchase_celadon_evolution_stone
from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


def _withdrawn_precursor_slot(party, withdrawn, species_id):
    """Bind the exact appended specimen, not another party member of its species."""
    if (
        not withdrawn.passed
        or withdrawn.species_id != species_id
        or len(withdrawn.party_before) != 5
        or tuple(party) != withdrawn.party_after
        or withdrawn.party_after != (*withdrawn.party_before, species_id)
    ):
        raise context.RedGoalContextError("item evolution lost its withdrawn precursor")
    return len(withdrawn.party_before)


def _native_item_transport(runtime, world, actions, traversal, destination, *, goal_at):
    """Use live geometry and the existing blocked-step replan for Mart/PC walks."""
    from .red_resource_goal_router import _ROUTE_LIMITS

    current = world.with_current_observation(runtime.reader)
    plan = current.plan_feasible_to_map(traversal.observe(), destination, goal_at=goal_at)
    # Local Mart/PC walking can expose a native poison faint after a prior
    # learned transport battle. Reuse the strict existing message handler;
    # this allows no wild escape, arbitrary dialogue, healing or replacement.
    handler = Gen1WildFleeHandler(
        actions, runtime.reader, maximum_flees=0, stabilization_frames=120,
        allow_party_faints=True, emulator=runtime.emulator,
        allow_field_faint_dialogue=True, route_name="local item evolution transport",
        field_faint_warps=tuple(
            (segment.source_map, segment.transition.exit_at,
             segment.target_map, segment.transition.arrival_at)
            for segment in plan.segments if segment.passage_kind == "warp"
            and segment.source_map != segment.target_map
        ),
    )
    return execute_route(plan, actions, traversal,
        limits=_ROUTE_LIMITS, replanner=current.replanner(), interruption_handler=handler)


def bind_native_boxed_item_evolution(
    runtime: context.RedGoalContextRuntime,
    world: StrategicScenarioRouteWorld,
    *,
    allow_cross_box: bool = True,
    allow_move_learning_preservation: bool = False,
) -> context.RedGoalContextRuntime:
    """Bind held-stone use, with procurement only for genuine shop offers."""

    if type(allow_cross_box) is not bool:
        raise TypeError("boxed item evolution cross-box mode differs")
    if type(allow_move_learning_preservation) is not bool:
        raise TypeError("boxed item move preservation mode differs")
    specs = tuple(
        spec
        for spec in runtime.profile.providers
        if spec.kind is GoalKind.EVOLVE_SPECIES
        and spec.mechanic is context.RedGoalMechanic.TARGETED_ITEM_EVOLUTION
    )
    if len(specs) != 1:
        raise context.RedGoalContextError(
            "native item evolution needs one targeted item declaration"
        )
    spec = specs[0]
    source_ref = cast(str, spec.parameters["source_species_ref"])
    target_ref = cast(str, spec.parameters["target_species_ref"])
    item_id = cast(int, spec.parameters["item_id"])
    if item_id not in EVOLUTION_STONE_ITEMS:
        raise context.RedGoalContextError("unsupported evolution stone")
    offer = BUYABLE_EVOLUTION_STONES.get(item_id)
    source_national = context.red_species_number(source_ref)
    target_national = context.red_species_number(target_ref)
    edges = evolution_graph(world.rom).get(source_national, ())
    if not any(
        edge.to_species == target_national
        and edge.method is EvolutionMethod.STONE
        and edge.requirement == item_id
        for edge in edges
    ):
        raise context.RedGoalContextError(
            "item evolution declaration differs from the loaded cartridge"
        )
    runtime = replace(runtime, boxed_item_evolution_cross_box=allow_cross_box)
    registration = runtime.registration_policy
    if registration is None:
        raise context.RedGoalContextError(
            "native item evolution requires an explicit registration policy"
        )

    def request_for(
        observation: context.RedGoalObservation,
    ) -> context.RedBoxedItemEvolutionGoalRequest:
        return context._RedTeamGoalProvider(
            runtime,
            spec,
            CountingExecutor(  # noqa: SLF001
                _NoopActionDelegate()
            ),
        )._boxed_item_evolution_request(observation)  # noqa: SLF001

    def plans_available(observation: context.RedGoalObservation, *, needs_shop: bool) -> bool:
        if observation.raw.battle_state or not observation.input_ready:
            return False
        traversal = Gen1TraversalObserver(runtime.reader)
        start = traversal.observe()
        try:
            if needs_shop:
                to_mart = world.plan_feasible_to_map(
                    start,
                    int(MapId.CELADON_MART_4F),
                    goal_at=(2, 12),
                )
                mart_start = replace(start, map_id=int(MapId.CELADON_MART_4F), at=(2, 12))
                to_pc = world.plan_feasible_to_map(
                    mart_start,
                    int(MapId.CELADON_POKECENTER),
                    goal_at=(4, 13),
                )
                return bool(to_mart.steps and to_pc.steps)
            to_pc = world.plan_feasible_to_map(
                start,
                int(MapId.CELADON_POKECENTER),
                goal_at=(4, 13),
            )
            return bool(to_pc.steps)
        except RoutePlanningError:
            return False

    def readiness(
        observation: context.RedGoalObservation,
    ) -> context.RedGoalSkillAvailability:
        before_frames = runtime.emulator.frame_count
        try:
            request = request_for(observation)
        except context.RedGoalContextError:
            return context.RedGoalSkillAvailability.unavailable(
                GoalUnavailableReason.NO_LEGAL_TARGET
            )
        if registration is not None and not registration.evolution_allowed(
            observation.collection_observation,
            source_ref,
            target_ref,
        ):
            return context.RedGoalSkillAvailability.unavailable(
                GoalUnavailableReason.NO_LEGAL_TARGET
            )
        raw = observation.raw
        bag = dict(raw.bag_items or ())
        stone_count = bag.get(item_id, 0)
        needs_shop = stone_count == 0
        prompt_moves = tuple(
            move
            for level, move in level_up_learnsets(world.rom).get(target_national, ())
            if level == request.precursor_level
        )
        prompt_supported = not prompt_moves
        if prompt_moves and allow_move_learning_preservation:
            detector = getattr(runtime.reader, "read_move_learning_prompt", None)
            box_reader = getattr(runtime.reader, "read_box_move_members", None)
            members = box_reader(request.source_box_index) if callable(box_reader) else ()
            source_moves = tuple(m for m in members if (
                m.box_slot == request.precursor_box_slot
                and m.species_id == request.precursor_internal_species_id
                and m.level == request.precursor_level
            ))
            prompt_supported = (
                callable(detector) and len(source_moves) == 1
                and len(source_moves[0].moves) == 4
                and all(1 <= move <= 165 for move in source_moves[0].moves)
            )
        if (
            raw.bag_items is None
            or raw.player_money is None
            or not 0 <= stone_count <= 99
            or (
                needs_shop
                and (
                    offer is None
                    or len(raw.bag_items) >= MAX_BAG_ITEMS
                    or raw.player_money < offer.price
                )
            )
            or not prompt_supported
            or not plans_available(observation, needs_shop=needs_shop)
        ):
            return context.RedGoalSkillAvailability.unavailable(
                GoalUnavailableReason.MISSING_CAPABILITY
            )
        if runtime.emulator.frame_count != before_frames:
            raise context.RedGoalContextError("item evolution readiness advanced the emulator")
        return context.RedGoalSkillAvailability.available()

    def execute(
        request: context.RedBoxedItemEvolutionGoalRequest,
        actions: CountingExecutor,
    ) -> GoalExecutionReport:
        before = runtime.adapter.observe()
        if request_for(before) != request or not readiness(before).executable:
            raise context.RedGoalContextError(
                "boxed item evolution binding changed before controller input"
            )
        action_start = actions.actions_executed
        frame_start = runtime.emulator.frame_count
        money_before = before.raw.player_money
        assert money_before is not None
        bag_before = dict(before.raw.bag_items or ())
        needs_shop = bag_before.get(item_id, 0) == 0
        traversal = Gen1TraversalObserver(runtime.reader)
        # Transport battles can leave an unhealed party at the nurse stance.
        # Preserve the existing dialogue guard, then reuse level evolution's
        # counted free recovery. The unchanged independent outcome verifier
        # requires a usable party; procurement never secretly skips that guard.
        prepare_center_departure(actions, runtime.reader)
        restorations = restore_native_center_party(runtime, actions)
        prepare_center_departure(actions, runtime.reader)
        if needs_shop:
            if offer is None:
                raise context.RedGoalContextError("finite evolution stone has no shop")
            if not _native_item_transport(runtime, world, actions, traversal,
                    int(MapId.CELADON_MART_4F), goal_at=(2, 12)).passed:
                raise context.RedGoalContextError("stone procurement route failed")
            purchase_celadon_evolution_stone(
                actions,
                runtime.reader,
                runtime.emulator,
                DEFAULT_SAFFRON_TIMING,
                item=ItemId(item_id),
                absolute_index=offer.mart_absolute_index,
                price=offer.price,
            )
        if not _native_item_transport(runtime, world, actions, traversal,
                int(MapId.CELADON_POKECENTER), goal_at=(4, 13)).passed:
            raise context.RedGoalContextError("item evolution PC route failed")
        face_pc_boundary(actions, runtime.reader, "up")
        open_bills_pc(actions, runtime.reader)
        deposited = deposit_party_member(
            actions,
            runtime.reader,
            party_slot=request.deposit_party_slot,
            expected_species_id=request.deposit_internal_species_id,
        )
        switched = False
        if request.source_box_index != runtime.reader.read_current_box_state().box_index:
            switch_box(actions, runtime.reader, target_box_index=request.source_box_index)
            switched = True
        withdrawn = withdraw_box_member(
            actions,
            runtime.reader,
            box_slot=request.precursor_box_slot,
            expected_species_id=request.precursor_internal_species_id,
        )
        close_generic_pc_session(actions, runtime.reader)
        party = tuple(runtime.reader.read().party_species_ids or ())
        source_slot = _withdrawn_precursor_slot(
            party,
            withdrawn,
            request.precursor_internal_species_id,
        )
        result = RedPartyItemEvolutionExecutor(
            runtime.reader,
            runtime.emulator,
            registration,
            lambda: runtime.adapter.observe().collection_observation,
            **({"allow_move_learning_preservation": True}
               if allow_move_learning_preservation else {}),
        ).execute(
            actions,
            RedPartyItemEvolutionRequest(
                rom=world.rom,
                party_slot=source_slot,
                source_national=source_national,
                target_national=target_national,
                item_id=item_id,
            ),
        )
        after = runtime.adapter.observe()
        if (
            not deposited.passed
            or not withdrawn.passed
            or not result.success
            or after.raw.player_money
            != money_before - (offer.price if needs_shop and offer is not None else 0)
            or dict(after.raw.bag_items or ()).get(item_id, 0)
            != max(0, bag_before.get(item_id, 0) - 1)
        ):
            raise context.RedGoalContextError("boxed item evolution pipeline failed verification")
        if registration is not None and not registration.verify_evolution(
            before.collection_observation,
            after.collection_observation,
            source_ref,
            target_ref,
        ):
            raise context.RedGoalContextError("item evolution violated registration policy")
        before_counts = Counter(
            specimen.species_ref for specimen in before.collection_observation.specimens
        )
        after_counts = Counter(
            specimen.species_ref for specimen in after.collection_observation.specimens
        )
        expected = before_counts.copy()
        expected[source_ref] -= 1
        if expected[source_ref] == 0:
            del expected[source_ref]
        expected[target_ref] += 1
        if after_counts != expected:
            raise context.RedGoalContextError("item evolution collection delta differs")
        settlement = settle_native_evolution(runtime, actions)
        return GoalExecutionReport(
            actions_executed=actions.actions_executed - action_start,
            frames_executed=runtime.emulator.frame_count - frame_start,
            evidence={
                **settlement,
                "bounded": True,
                "typed_stages": ("procurement", "storage", "item_use"),
                "procurement_executed": needs_shop,
                "money_spent": offer.price if needs_shop and offer is not None else 0,
                "healing_trips": restorations,
                "storage_deposit_passed": deposited.passed,
                "storage_box_switch_performed": switched,
                "storage_withdraw_passed": withdrawn.passed,
                "stone_consumed": True,
                "registration_policy_sha256": (
                    registration.sha256 if registration is not None else None
                ),
            },
        )

    return replace(
        runtime,
        boxed_item_evolution_executor=execute,
        boxed_item_evolution_readiness=readiness,
    )


class _NoopActionDelegate:
    def execute(self, action: object) -> None:
        raise context.RedGoalContextError("readiness attempted controller input")


__all__ = ("bind_native_boxed_item_evolution",)
