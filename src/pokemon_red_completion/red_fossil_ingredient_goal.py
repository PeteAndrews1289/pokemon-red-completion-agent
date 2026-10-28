"""Opt-in missing-ingredient plus revival acquisition, bound before any input.

The qualified ingredient is a cartridge-authenticated one-time NPC gift. The
policy selects the complete acquisition, not a hidden operator-prepared item.
Routes, gift interaction, Fly and revival remain mechanical support. No new
default profile, free item, reset, trainer fallback or puzzle bypass is added.
"""

from collections import Counter
from dataclasses import asdict, dataclass, replace
from hashlib import sha256

from .executor import CountingExecutor
from .gen1_field_moves import Gen1FieldMoveError, Gen1FieldMovePort, fly_menu_indices
from .gen1_route_runtime import Gen1WildFleeHandler
from .goal_manager import GoalFailureReason, GoalKind, GoalUnavailableReason
from .goal_manager_composition_qualification import HardCompositionActionLimiter
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import MAX_BAG_ITEMS, Badge, EventFlag, event_flag_is_set
from .provenance import canonical_sha256
from .red_fossil_acquisition import (
    FOSSIL_ITEMS,
    RedFossilTiming,
    RedRoutedFossilRevival,
    fossil_target_by_item,
)
from .red_goal_manager import RedGoalBindingOffer
from .red_npc_item_gift import collect_npc_item_gift, old_amber_gift
from .red_pc_storage import face_pc_boundary
from .red_resource_goal_router import _supported_plan
from .route_executor import DEFAULT_ROUTE_EXECUTION_LIMITS, execute_route
from .route_plan import RoutePlanningError


@dataclass(frozen=True, slots=True)
class RedFossilIngredientGoalProvider:
    rom: bytes
    adapter: object
    reader: object
    emulator: object
    actions: object
    world: object
    traversal_observer: object
    maximum_actions: int = 1200
    maximum_route_steps: int = 400
    maximum_flees: int = 8
    estimated_effort: float = 0.4
    estimated_risk: float = 0.12
    kind: GoalKind = GoalKind.ACQUIRE_SPECIES

    def __post_init__(self):
        old_amber_gift(self.rom)
        if self.kind is not GoalKind.ACQUIRE_SPECIES:
            raise ValueError("fossil ingredient belongs to acquisition")
        for key in ("maximum_actions", "maximum_route_steps", "maximum_flees"):
            if type(getattr(self, key)) is not int or getattr(self, key) <= 0:
                raise ValueError("ingredient acquisition requires finite positive limits")

    def offer(self, observation):
        if observation != self.adapter.observe():
            raise ValueError("ingredient acquisition offered from stale observation")
        original = self.emulator.save_state_bytes()
        counters = self.actions.actions_executed, self.emulator.frame_count
        gift = old_amber_gift(self.rom)
        target = fossil_target_by_item(gift.item_id)
        raw = self.reader.read()
        start = self.traversal_observer.observe()
        owned = self.reader.read_pokedex_state().owned_species

        def unavailable(reason):
            return RedGoalBindingOffer.unavailable(self.kind, reason)

        if target.national_dex_number in owned or event_flag_is_set(
            raw.event_flags, gift.event_flag
        ):
            return unavailable(GoalUnavailableReason.NO_LEGAL_TARGET)
        if (
            not raw.game_started
            or raw.battle_state
            or not observation.input_ready
            or not start.ready
            or start.interruption is not None
            or start.mode != "land"
            or not 0 <= start.map_id <= 0x24
            or start.map_id == 0x0B
            or self.reader.read_bottom_dialogue_box_visible()
            or raw.event_flags is None
            or len(raw.event_flags) * 8 <= gift.event_flag
        ):
            return unavailable(GoalUnavailableReason.TEMPORARILY_BLOCKED)
        if (
            raw.bag_items is None
            or len(raw.bag_items) >= MAX_BAG_ITEMS
            or any(i in FOSSIL_ITEMS for i, _ in raw.bag_items)
            or any(
                event_flag_is_set(raw.event_flags, int(flag))
                for flag in (
                    EventFlag.GAVE_FOSSIL_TO_LAB,
                    EventFlag.LAB_STILL_REVIVING_FOSSIL,
                    EventFlag.LAB_HANDING_OVER_FOSSIL_MON,
                )
            )
            or not raw.party_hp
            or not any(raw.party_hp)
        ):
            return unavailable(GoalUnavailableReason.MISSING_RESOURCE)
        boxes = self.reader.read_all_box_states()
        if raw.party_count == 6 and len(boxes.boxes[boxes.current_box_index].species_ids) >= 20:
            return unavailable(GoalUnavailableReason.STORAGE_BLOCKED)
        if (
            not int(raw.badge_bits or 0) & int(Badge.THUNDER)
            or 8 not in self.reader.read_fly_destinations()
        ):
            return unavailable(GoalUnavailableReason.MISSING_CAPABILITY)
        try:
            fly_menu_indices(raw)
        except Gen1FieldMoveError:
            return unavailable(GoalUnavailableReason.MISSING_CAPABILITY)
        world = self.world.with_current_observation(self.reader)

        def supported(plan):
            return (
                len(plan.steps) <= self.maximum_route_steps
                and plan.terminal_mode in (None, "land")
                and _supported_plan(plan, allow_cut=True, allow_surf=False)
            )

        plans = []
        for dy, dx in ((1, 0), (0, -1), (0, 1), (-1, 0)):
            at = gift.at[0] + dy, gift.at[1] + dx
            if min(at) < 0:
                continue
            try:
                plan = world.plan_feasible_to_map(start, gift.map_id, goal_at=at)
                projected = replace(
                    start, map_id=gift.map_id, at=at, occupied=frozenset(), hazards=()
                )
                back = world.plan_feasible_to_map(projected, start.map_id, goal_at=start.at)
            except RoutePlanningError:
                continue
            if supported(plan) and supported(back):
                plans.append((plan, back))
        if not plans:
            return unavailable(GoalUnavailableReason.MISSING_CAPABILITY)
        outward, returning = min(
            plans, key=lambda ps: (sum(len(p.steps) for p in ps), ps[0].terminal_at)
        )
        origin = sha256(original).hexdigest()
        config = canonical_sha256(
            dict(
                gift=asdict(gift),
                maximum_actions=self.maximum_actions,
                maximum_route_steps=self.maximum_route_steps,
                maximum_flees=self.maximum_flees,
                plans=[[asdict(step) for step in p.steps] for p in (outward, returning)],
            )
        )
        initial_bag = dict(raw.bag_items)
        initial_specimens = Counter(raw.party_species_ids or ()) + Counter(
            s for box in boxes.boxes for s in box.species_ids
        )
        expected_party = raw.party_species_ids
        if raw.party_count is not None and raw.party_count < 6 and expected_party is not None:
            expected_party += (target.internal_species_id,)
        used = False
        report = None
        terminal = None

        def execute():
            nonlocal used, report, terminal
            if used:
                raise RuntimeError("ingredient acquisition binding already attempted")
            used = True
            if (
                self.emulator.save_state_bytes() != original
                or (self.actions.actions_executed, self.emulator.frame_count) != counters
                or observation != self.adapter.observe()
            ):
                raise RuntimeError("ingredient acquisition source changed before input")
            limiter = HardCompositionActionLimiter(
                self.actions,
                maximum_actions_per_decision=self.maximum_actions,
                maximum_episode_actions=self.maximum_actions,
            )
            actions = CountingExecutor(limiter)
            port = Gen1FieldMovePort(
                actions,
                self.reader,
                self.emulator,
                cut_block_swaps={s.before: s.after for s in world.rules.cut_block_swaps},
            )
            handler = Gen1WildFleeHandler(
                port, self.reader, self.maximum_flees, 120, "fossil ingredient acquisition"
            )
            live_world = world

            def route(plan):
                nonlocal live_world
                live_world = live_world.with_current_observation(self.reader)

                def replan(request):
                    nonlocal live_world
                    live_world = live_world.with_current_observation(self.reader)
                    revised = live_world.replanner()(request)
                    if not supported(revised):
                        raise RoutePlanningError("ingredient replan needs unsupported mechanics")
                    return revised

                result = execute_route(
                    plan,
                    port,
                    self.traversal_observer,
                    replanner=replan,
                    interruption_handler=handler,
                    limits=replace(
                        DEFAULT_ROUTE_EXECUTION_LIMITS,
                        max_replans=16,
                        max_interruptions=self.maximum_flees,
                    ),
                )
                if not result.passed:
                    raise RuntimeError("ingredient route did not reach its boundary")
                return len(result.executed_steps)

            outward_steps = route(outward)
            at = self.traversal_observer.observe().at
            direction = {(-1, 0): "up", (1, 0): "down", (0, -1): "left", (0, 1): "right"}[
                (gift.at[0] - at[0], gift.at[1] - at[1])
            ]
            face_pc_boundary(actions, self.reader, direction)
            gift_report = collect_npc_item_gift(actions, self.reader, gift, rom=self.rom)
            # Replan from the observed gift terminal. Admission's return plan
            # proved feasibility, not permission to trust stale map occupancy.
            live_world = live_world.with_current_observation(self.reader)
            return_plan = live_world.plan_feasible_to_map(
                self.traversal_observer.observe(), start.map_id, goal_at=start.at
            )
            if not supported(return_plan):
                raise RuntimeError("ingredient return lost its supported route")
            return_steps = route(return_plan)
            revival = RedRoutedFossilRevival(
                actions,
                self.reader,
                self.emulator,
                live_world.with_current_observation(self.reader),
                timing=RedFossilTiming(maximum_controller_actions=self.maximum_actions),
            ).execute(target)
            report = GoalExecutionReport(
                self.actions.actions_executed - counters[0],
                self.emulator.frame_count - counters[1],
                dict(
                    mechanic="ingredient_and_fossil_revival",
                    gift=gift_report,
                    revival=revival.public_dict(),
                    outward_steps=outward_steps,
                    return_steps=return_steps,
                    learned_preparation=False,
                ),
            )
            terminal = self.emulator.save_state_bytes()
            return report

        def verify(candidate):
            if (
                candidate is not report
                or terminal is None
                or self.emulator.save_state_bytes() != terminal
            ):
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            after = self.adapter.observe()
            actual = self.reader.read()
            actual_specimens = Counter(actual.party_species_ids or ()) + Counter(
                s for box in self.reader.read_all_box_states().boxes for s in box.species_ids
            )
            if (
                not after.input_ready
                or actual.battle_state
                or self.emulator.pressed_buttons
                or actual.player_money != raw.player_money
                or dict(actual.bag_items or ()) != initial_bag
                or actual.party_species_ids != expected_party
                or actual_specimens != initial_specimens + Counter({target.internal_species_id: 1})
                or self.reader.read_pokedex_state().owned_species
                != owned | {target.national_dex_number}
                or not event_flag_is_set(actual.event_flags, gift.event_flag)
            ):
                return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            return GoalVerification.succeeded()

        if (
            self.emulator.save_state_bytes() != original
            or (self.actions.actions_executed, self.emulator.frame_count) != counters
        ):
            raise RuntimeError("ingredient offer changed game state")
        return RedGoalBindingOffer.available(
            ExecutableGoalBinding(
                binding_ref=f"red-fossil-ingredient:{origin}:{config}",
                kind=self.kind,
                estimated_effort=self.estimated_effort,
                estimated_risk=self.estimated_risk,
                execute=execute,
                verify=verify,
                search_source_ref=target.source_ref,
            )
        )
