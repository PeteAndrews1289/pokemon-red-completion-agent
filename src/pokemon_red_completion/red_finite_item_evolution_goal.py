"""Opt-in observed finite-item procurement and boxed evolution as one goal.

Admission proves a current-map visible item and both sides of transport. It
does not invent remote availability or put a projected item in emulator RAM.
After native pickup, the existing held-stone provider is rebound on fresh state.
"""

from dataclasses import asdict, dataclass, replace
from hashlib import sha256

from .actions import MacroAction, MacroActionKind
from .executor import CountingExecutor
from .gen1_cartridge import level_up_learnsets
from .gen1_field_moves import Gen1FieldMoveError, Gen1FieldMovePort, fly_menu_indices
from .gen1_route_runtime import Gen1WildFleeHandler
from .goal_manager import GoalFailureReason, GoalKind, GoalUnavailableReason
from .goal_manager_composition_qualification import HardCompositionActionLimiter
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import MAX_BAG_ITEMS, Badge, EventFlag, MapId, event_flag_is_set
from .provenance import canonical_sha256
from .red_collection import red_species_number
from .red_collection_fly import red_fly_landings
from .red_field_item import RedFieldItem, collect_visible_field_item, red_field_items
from .red_goal_context import RedGoalContextError, _RedTeamGoalProvider
from .red_goal_manager import RedGoalBindingOffer
from .red_native_boxed_item_evolution import bind_native_boxed_item_evolution
from .red_pc_storage import face_pc_boundary
from .red_resource_goal_router import _supported_plan
from .route_executor import DEFAULT_ROUTE_EXECUTION_LIMITS, execute_route
from .route_plan import RoutePlanningError


@dataclass(frozen=True, slots=True)
class RedFiniteItemEvolutionGoalProvider:
    runtime: object
    actions: object
    world: object
    traversal_observer: object
    target: RedFieldItem
    maximum_actions: int = 1600
    maximum_route_steps: int = 400
    maximum_flees: int = 8
    kind: GoalKind = GoalKind.EVOLVE_SPECIES

    def __post_init__(self):
        if self.kind is not GoalKind.EVOLVE_SPECIES:
            raise ValueError("finite evolution belongs to evolve_species")
        if self.target not in red_field_items(self.world.rom, self.target.item_id):
            raise ValueError("finite item differs from the cartridge")
        for key in ("maximum_actions", "maximum_route_steps", "maximum_flees"):
            if type(getattr(self, key)) is not int or getattr(self, key) <= 0:
                raise ValueError("finite evolution needs positive bounded limits")

    def offer(self, observation):
        runtime = self.runtime
        adapter, reader, emulator = runtime.adapter, runtime.reader, runtime.emulator
        if observation != adapter.observe():
            raise ValueError("finite evolution offered from stale observation")
        original = emulator.save_state_bytes()
        counters = self.actions.actions_executed, emulator.frame_count

        def unchanged():
            if (
                emulator.save_state_bytes() != original
                or (self.actions.actions_executed, emulator.frame_count) != counters
            ):
                raise RuntimeError("finite evolution offer changed game state")

        def unavailable(reason):
            unchanged()
            return RedGoalBindingOffer.unavailable(self.kind, reason)

        raw = observation.raw
        start = self.traversal_observer.observe()
        if (
            not observation.input_ready
            or raw.battle_state
            or not start.ready
            or start.interruption is not None
            or start.mode != "land"
            or not 0 <= start.map_id <= 0x24
            or start.map_id != self.target.map_id
            or reader.read_bottom_dialogue_box_visible()
            or emulator.pressed_buttons
        ):
            return unavailable(GoalUnavailableReason.TEMPORARILY_BLOCKED)
        objects = [
            o
            for o in reader.read_current_map_objects()
            if o.sprite_index == self.target.object_index
        ]
        if (
            len(objects) != 1
            or not objects[0].visible
            or objects[0].moving
            or (objects[0].picture_id, objects[0].at) != (self.target.sprite_id, self.target.at)
        ):
            return unavailable(GoalUnavailableReason.NO_LEGAL_TARGET)
        if (
            raw.bag_items is None
            or len(raw.bag_items) >= MAX_BAG_ITEMS
            or dict(raw.bag_items).get(self.target.item_id, 0) != 0
            or raw.player_money is None
            or not raw.party_hp
            or not any(raw.party_hp)
        ):
            return unavailable(GoalUnavailableReason.MISSING_RESOURCE)
        if (
            raw.event_flags is None
            or not event_flag_is_set(raw.event_flags, int(EventFlag.GOT_POKEDEX))
            or not int(raw.badge_bits or 0) & int(Badge.THUNDER)
            or int(MapId.CELADON_CITY) not in reader.read_fly_destinations()
        ):
            return unavailable(GoalUnavailableReason.MISSING_CAPABILITY)
        try:
            fly_menu_indices(raw)
        except Gen1FieldMoveError:
            return unavailable(GoalUnavailableReason.MISSING_CAPABILITY)
        # This validates the profile's actual cartridge edge and registration
        # contract. It neither executes nor supplies hypothetical inventory.
        native = bind_native_boxed_item_evolution(runtime, self.world, allow_cross_box=True)
        spec = next(s for s in native.profile.providers if s.kind is self.kind)
        if spec.parameters["item_id"] != self.target.item_id:
            raise ValueError("finite item does not supply the selected evolution")
        source_ref = spec.parameters["source_species_ref"]
        target_ref = spec.parameters["target_species_ref"]
        policy = native.registration_policy
        if not policy.evolution_allowed(observation.collection_observation, source_ref, target_ref):
            return unavailable(GoalUnavailableReason.NO_LEGAL_TARGET)
        try:
            request = _RedTeamGoalProvider(
                native, spec, self.actions
            )._boxed_item_evolution_request(observation)
        except RedGoalContextError:
            return unavailable(GoalUnavailableReason.STORAGE_BLOCKED)
        if any(
            level == request.precursor_level
            for level, _ in level_up_learnsets(self.world.rom).get(
                red_species_number(target_ref), ()
            )
        ):
            return unavailable(GoalUnavailableReason.MISSING_CAPABILITY)
        world = self.world.with_current_observation(reader)

        def supported(plan):
            return (
                len(plan.steps) <= self.maximum_route_steps
                and plan.terminal_mode in (None, "land")
                and _supported_plan(plan, allow_cut=True, allow_surf=False)
            )

        plans = []
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            at = self.target.at[0] + dy, self.target.at[1] + dx
            if min(at) < 0:
                continue
            try:
                plan = world.plan_feasible_to_map(start, self.target.map_id, goal_at=at)
            except RoutePlanningError:
                continue
            if supported(plan):
                plans.append(plan)
        if not plans:
            return unavailable(GoalUnavailableReason.MISSING_CAPABILITY)
        approach = min(plans, key=lambda p: (len(p.steps), p.terminal_at))
        landing = dict(red_fly_landings(world.rom))[int(MapId.CELADON_CITY)]
        projected = replace(
            start,
            map_id=int(MapId.CELADON_CITY),
            at=landing,
            last_outside_map=int(MapId.CELADON_CITY),
            occupied=frozenset(),
            hazards=(),
        )
        try:
            to_center = world.plan_feasible_to_map(
                projected, int(MapId.CELADON_POKECENTER), goal_at=(3, 3)
            )
            to_pc = world.plan_feasible_to_map(
                replace(projected, map_id=int(MapId.CELADON_POKECENTER), at=(3, 3)),
                int(MapId.CELADON_POKECENTER),
                goal_at=(4, 13),
            )
        except RoutePlanningError:
            return unavailable(GoalUnavailableReason.MISSING_CAPABILITY)
        if not supported(to_center) or not supported(to_pc):
            return unavailable(GoalUnavailableReason.MISSING_CAPABILITY)
        config = canonical_sha256(
            dict(
                target=asdict(self.target),
                profile=native.profile.profile_sha256,
                maximum_actions=self.maximum_actions,
                maximum_route_steps=self.maximum_route_steps,
                maximum_flees=self.maximum_flees,
                routes=[[asdict(step) for step in p.steps] for p in (approach, to_center, to_pc)],
            )
        )
        before_pc = reader.read_pc_items()
        used = False
        report = terminal = None
        component = None

        def execute():
            nonlocal used, report, terminal, component
            if used:
                raise RuntimeError("finite evolution binding already attempted")
            used = True
            unchanged()
            if adapter.observe() != observation or reader.read_pc_items() != before_pc:
                raise RuntimeError("finite evolution source changed before input")
            actions = CountingExecutor(
                HardCompositionActionLimiter(
                    self.actions,
                    maximum_actions_per_decision=self.maximum_actions,
                    maximum_episode_actions=self.maximum_actions,
                )
            )
            port = Gen1FieldMovePort(
                actions,
                reader,
                emulator,
                cut_block_swaps={s.before: s.after for s in world.rules.cut_block_swaps},
            )
            handler = Gen1WildFleeHandler(
                port, reader, self.maximum_flees, 120, "finite-item evolution"
            )
            live_world = world

            def route(plan):
                nonlocal live_world
                live_world = live_world.with_current_observation(reader)

                def replan(req):
                    replacement = live_world.with_current_observation(reader).replanner()(req)
                    if not supported(replacement):
                        raise RoutePlanningError("finite item replan needs unsupported mechanics")
                    return replacement

                result = execute_route(
                    plan,
                    port,
                    self.traversal_observer,
                    interruption_handler=handler,
                    replanner=replan,
                    limits=replace(
                        DEFAULT_ROUTE_EXECUTION_LIMITS,
                        max_replans=16,
                        max_interruptions=self.maximum_flees,
                    ),
                )
                if not result.passed:
                    raise RuntimeError("finite item route did not settle")
                return len(result.executed_steps)

            approach_steps = route(approach)
            at = self.traversal_observer.observe().at
            delta = self.target.at[0] - at[0], self.target.at[1] - at[1]
            face_pc_boundary(
                actions,
                reader,
                {(-1, 0): "up", (1, 0): "down", (0, -1): "left", (0, 1): "right"}[delta],
            )
            collect_visible_field_item(actions, reader, self.target)
            prepared = adapter.observe()
            if (
                dict(prepared.raw.bag_items or ()) != dict(raw.bag_items) | {self.target.item_id: 1}
                or prepared.collection_observation != observation.collection_observation
                or prepared.raw.player_money != raw.player_money
            ):
                raise RuntimeError("finite item preparation changed resources or collection")
            port.execute(MacroAction(MacroActionKind.FIELD_MOVE, "fly:celadon_city"))
            arrived = self.traversal_observer.observe()
            if not arrived.ready or (arrived.map_id, arrived.at) != (
                int(MapId.CELADON_CITY),
                landing,
            ):
                raise RuntimeError("finite evolution Fly landing differs")
            fresh_plan = live_world.with_current_observation(reader).plan_feasible_to_map(
                arrived, int(MapId.CELADON_POKECENTER), goal_at=(3, 3)
            )
            if not supported(fresh_plan):
                raise RuntimeError("finite evolution center approach changed")
            center_steps = route(fresh_plan)
            fresh = adapter.observe()
            rebound = bind_native_boxed_item_evolution(
                native, live_world.with_current_observation(reader), allow_cross_box=True
            )
            offer = rebound.provider_for(self.kind, actions).offer(fresh)
            if offer.binding is None:
                raise RuntimeError("prepared finite evolution is no longer executable")
            result = offer.binding.execute()
            component = offer.binding.verify(result)
            report = GoalExecutionReport(
                self.actions.actions_executed - counters[0],
                emulator.frame_count - counters[1],
                dict(
                    mechanic="finite_item_and_evolution",
                    approach_steps=approach_steps,
                    center_steps=center_steps,
                    item_acquired=self.target.item_id,
                    evolution=result.evidence,
                    component_verification=component.status.value,
                    learned_preparation=False,
                ),
            )
            terminal = emulator.save_state_bytes()
            return report

        def verify(candidate):
            if (
                candidate is not report
                or terminal is None
                or component is None
                or component.status.value != "succeeded"
                or emulator.save_state_bytes() != terminal
            ):
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            after = adapter.observe()
            if (
                not after.input_ready
                or after.raw.battle_state
                or emulator.pressed_buttons
                or reader.read_bottom_dialogue_box_visible()
                or after.raw.player_money != raw.player_money
                or dict(after.raw.bag_items or ()) != dict(raw.bag_items)
                or reader.read_pc_items() != before_pc
                or not policy.verify_evolution(
                    observation.collection_observation,
                    after.collection_observation,
                    source_ref,
                    target_ref,
                )
            ):
                return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            return GoalVerification.succeeded()

        unchanged()
        return RedGoalBindingOffer.available(
            ExecutableGoalBinding(
                binding_ref=f"red-finite-evolution:{sha256(original).hexdigest()}:{config}",
                kind=self.kind,
                estimated_effort=min(
                    1.0, (len(approach.steps) + len(to_center.steps) + 200) / 1000
                ),
                estimated_risk=0.10,
                execute=execute,
                verify=verify,
            )
        )
