"""Opt-in cartridge-routed story battle, starting with the Lorelei objective.

Only the title adapter names the quest/map/event. The approach, roster, opening
party member and per-turn controls are observed or computed, not a walkthrough.
No availability claim is made outside the explicitly supported entry region.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from .actions import MacroAction, MacroActionKind
from .battle_runtime import (
    BattleIntent,
    BattleRuntimeTiming,
    BattleSwitchCapability,
    battle_policy_override_active,
)
from .domain import GameState
from .executor import CountingExecutor
from .gen1_cartridge import CartridgeReadError
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_dialogue import bind_scripted_trainer_dialogue
from .gen1_trainer_parties import TrainerPartyQuote, trainer_party_quote
from .gen1_trainer_sight import (
    Gen1TrainerSightProjector,
    TrainerFacing,
    static_trainer_sight_zones,
    trainer_headers,
    trainer_sight_zones,
)
from .gen1_traversal import map_object_events
from .goal_manager_composition_qualification import HardCompositionActionLimiter
from .objective_skills import ObjectiveSkillAvailability, ObjectiveSkillExecution
from .observation import CurrentMapBlocks, EventFlag, MapId
from .quest import Specialist
from .red_dual_capability_curriculum_runtime import dependency_specimen_ledger
from .red_goal_manager import RedGoalObservation
from .red_pc_storage import face_pc_boundary
from .red_routed_recovery import RecoveryRouteInterruptionHandler
from .red_trainer_control import RedTrainerPartyController
from .red_trainer_funding import TrainerFundingCandidate
from .red_trainer_funding_battle import run_prepared_trainer_funding
from .red_trainer_party import RedTrainerPartyPlan, plan_trainer_party, prepare_trainer_lead
from .route_executor import execute_route
from .route_plan import RoutePlan, RoutePlanningError

if TYPE_CHECKING:
    from .red_goal_context import RedGoalContextRuntime
    from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


class RedTrainerStoryError(RuntimeError):
    """The declared story target or its safe execution boundary changed."""


def _before_scripted_interaction(
    plan: RoutePlan, triggers: tuple[tuple[int, int], ...], facing: TrainerFacing,
) -> RoutePlan:
    """Leave the battle-starting last movement to the battle specialist.

    A navigation success must still mean settled traversal, not a silently
    ignored trainer dialogue. No earlier step may cross a script trigger.
    """
    steps = plan.steps
    local = plan.terminal_approach
    if (
        plan.terminal_at not in triggers or not steps or local is None or not local.edges
        or steps[-1].action != facing.value or steps[-1].kind != "walk"
        or not steps[-1].stays_on_map
        or any(step.expected_map == plan.terminal_map and step.expected_at in triggers
               for step in steps[:-1])
    ):
        raise RedTrainerStoryError("scripted interaction requires one final bound trigger step")
    return replace(
        plan, terminal_at=local.coordinates[-2], terminal_mode=local.modes[-2],
        terminal_approach=replace(
            local, coordinates=local.coordinates[:-1], edges=local.edges[:-1],
            modes=local.modes[:-1],
        ),
    )


@dataclass(slots=True)
class RedCartridgeLoreleiSkill:
    runtime: RedGoalContextRuntime
    actions: CountingExecutor
    world: StrategicScenarioRouteWorld | None
    objective_id: str = "defeat_lorelei"
    specialist: Specialist = field(default=Specialist.BATTLE, init=False)
    expected_facts: frozenset[str] = field(
        default=frozenset({"league:lorelei_defeated"}), init=False,
    )
    additional_effect_facts: frozenset[str] = field(default=frozenset(), init=False)
    max_actions: int = field(default=6000, init=False)
    max_frames: int = field(default=3000000, init=False)
    _prepared: (
        tuple[RedGoalObservation, TrainerFundingCandidate, RedTrainerPartyPlan] | None
    ) = field(
        default=None, init=False,
    )
    _claimed: bool = field(default=False, init=False)
    _prepared_world: StrategicScenarioRouteWorld | None = field(default=None, init=False)
    _prepared_blocks: CurrentMapBlocks | None = field(default=None, init=False)
    _arrival_steps: int = field(default=0, init=False)
    _scripted_triggers: tuple[tuple[int, int], ...] = field(default=(), init=False)

    def __post_init__(self) -> None:
        if self.objective_id not in {
            "defeat_lorelei", "defeat_bruno", "defeat_agatha", "defeat_lance",
        }:
            raise RedTrainerStoryError("unsupported cartridge story objective")
        if self.objective_id == "defeat_bruno":
            self.expected_facts = frozenset({"league:bruno_defeated"})
        elif self.objective_id == "defeat_agatha":
            self.expected_facts = frozenset({"league:agatha_defeated"})
        elif self.objective_id == "defeat_lance":
            self.expected_facts = frozenset({"league:lance_defeated"})

    def _quote(self, trainer_class: int, trainer_set: int) -> TrainerPartyQuote:
        assert self.world is not None
        if self.objective_id == "defeat_lance":
            return trainer_party_quote(
                self.world.rom, trainer_class, trainer_set, allow_final_class=True,
            )
        return trainer_party_quote(self.world.rom, trainer_class, trainer_set)

    def _plan(self) -> tuple[RedGoalObservation, TrainerFundingCandidate, RedTrainerPartyPlan]:
        from .red_resource_goal_router import _walking_plan

        if self.world is None or battle_policy_override_active():
            raise RedTrainerStoryError("cartridge world or fixed battle authority unavailable")
        observation = self.runtime.adapter.observe()
        raw = observation.raw
        is_bruno = self.objective_id == "defeat_bruno"
        is_agatha = self.objective_id == "defeat_agatha"
        is_lance = self.objective_id == "defeat_lance"
        target_map = MapId.BRUNOS_ROOM if is_bruno else MapId.LORELEIS_ROOM
        target_event = EventFlag.BEAT_BRUNO if is_bruno else EventFlag.BEAT_LORELEI
        required_fact = "league:lorelei_defeated" if is_bruno else "story:victory_road_cleared"
        entry_maps = (
            {MapId.LORELEIS_ROOM, MapId.BRUNOS_ROOM} if is_bruno
            else {MapId.INDIGO_PLATEAU, MapId.INDIGO_PLATEAU_LOBBY, MapId.LORELEIS_ROOM}
        )
        if is_agatha:
            target_map, target_event = MapId.AGATHAS_ROOM, EventFlag.BEAT_AGATHA
            required_fact = "league:bruno_defeated"
            entry_maps = {MapId.BRUNOS_ROOM, MapId.AGATHAS_ROOM}
        if is_lance:
            target_map, target_event = MapId.LANCES_ROOM, EventFlag.BEAT_LANCES_ROOM_TRAINER
            required_fact = "league:agatha_defeated"
            entry_maps = {MapId.AGATHAS_ROOM, MapId.LANCES_ROOM}
        if (
            not observation.input_ready or raw.battle_state != 0
            or raw.map_id not in entry_maps
            or required_fact not in observation.game_state.facts
            or self.expected_facts.intersection(observation.game_state.facts)
            or raw.event_flags is None
            or self.runtime.reader.read_bottom_dialogue_box_visible()
        ):
            raise RedTrainerStoryError("requires a settled, undefeated Indigo story boundary")
        world = self.world
        if is_lance:
            from .gen1_scripted_arrival import trainer_room_interaction_coordinates

            self._scripted_triggers = trainer_room_interaction_coordinates(
                world.rom, int(target_map),
            )
        blocks = None
        if is_bruno or is_agatha or is_lance:
            blocks = self.runtime.reader.read_current_map_blocks()
            if blocks.map_id != raw.map_id:
                raise RedTrainerStoryError("story map changed while reading its live terrain")
            world = world.with_current_blocks(blocks)
        if raw.map_id != target_map:
            from .gen1_scripted_arrival import (
                trainer_room_arrival,
                with_scripted_trainer_arrival,
            )

            arrival = trainer_room_arrival(world.rom, int(target_map), raw.event_flags)
            self._arrival_steps = arrival.steps if is_lance else 0
            world = replace(world, macro_graph=with_scripted_trainer_arrival(
                world.macro_graph, arrival,
            ))
        headers = trainer_headers(world.rom, {target_map}, full_event_offsets=True)
        objects = map_object_events(world.rom, {target_map})
        zones = static_trainer_sight_zones(headers, objects, raw.event_flags)
        matches = tuple(z for z in zones if z.event_flag == target_event)
        if len(matches) != 1 or matches[0].defeated or matches[0].engage_distance != 0:
            raise RedTrainerStoryError("story trainer is not one undefeated interaction target")
        trainer = matches[0]
        quote = self._quote(trainer.trainer_class, trainer.trainer_set)
        preparation = plan_trainer_party(observation.party, quote)
        start = Gen1TraversalObserver(self.runtime.reader, Gen1TrainerSightProjector(
            world.rom, self.runtime.reader, full_event_offsets=True,
        )).observe()
        approaches = []
        for facing in TrainerFacing:
            dy, dx = facing.delta
            at = (trainer.at[0] - dy, trainer.at[1] - dx)
            if min(at) < 0:
                continue
            try:
                plan = world.plan_feasible_to_map(start, int(trainer.map_id), goal_at=at)
                if self._scripted_triggers:
                    _before_scripted_interaction(plan, self._scripted_triggers, facing)
            except (RoutePlanningError, RedTrainerStoryError):
                continue
            if len(plan.steps) <= 128 and _walking_plan(plan):
                approaches.append(TrainerFundingCandidate(trainer, quote, plan, facing))
        if not approaches:
            raise RedTrainerStoryError("no bounded walking approach to the story trainer")
        self._prepared_world, self._prepared_blocks = world, blocks
        return observation, min(approaches, key=lambda item: len(item.approach.steps)), preparation

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        self._prepared = None
        self._prepared_world, self._prepared_blocks = None, None
        self._arrival_steps = 0
        self._scripted_triggers = ()
        if self._claimed:
            return ObjectiveSkillAvailability(False, "Story attempt already consumed.")
        try:
            prepared = self._plan()
        except (RedTrainerStoryError, ValueError, RoutePlanningError, CartridgeReadError) as error:
            return ObjectiveSkillAvailability(False, str(error))
        if prepared[0].game_state != state:
            return ObjectiveSkillAvailability(False, "Story observation changed during planning.")
        self._prepared = prepared
        return ObjectiveSkillAvailability(
            True, "Bounded cartridge trainer with observed party control.",
        )

    def execute(self) -> ObjectiveSkillExecution:
        from .red_resource_goal_router import _ROUTE_LIMITS

        if self._claimed or self._prepared is None:
            raise RedTrainerStoryError("story requires a fresh unconsumed availability binding")
        self._claimed = True
        before, target, preparation = self._prepared
        if self.runtime.adapter.observe() != before or battle_policy_override_active():
            raise RedTrainerStoryError("story origin or battle authority changed before input")
        if self._prepared_blocks is not None and (
            self.runtime.reader.read_current_map_blocks() != self._prepared_blocks
        ):
            raise RedTrainerStoryError("story terrain changed before input")
        assert self._prepared_world is not None
        world = self._prepared_world
        reader = self.runtime.reader
        start_actions = self.actions.actions_executed
        start_frames = self.runtime.emulator.frame_count
        actions = CountingExecutor(HardCompositionActionLimiter(
            self.actions, maximum_actions_per_decision=self.max_actions,
            maximum_episode_actions=self.max_actions,
        ))
        quote = self._quote(target.trainer.trainer_class, target.trainer.trainer_set)
        prepare_trainer_lead(self.runtime, actions, preparation, current_quote=quote)
        prepared_raw = reader.read()
        guard = RecoveryRouteInterruptionHandler(
            actions, reader, tuple(prepared_raw.party_species_ids or ()),
            tuple(range(prepared_raw.party_count or 0)), maximum_flees=0, maximum_trainer_battles=0,
        )
        traversal = Gen1TraversalObserver(reader, Gen1TrainerSightProjector(
            world.rom, reader, full_event_offsets=True,
        ))
        route_plan = target.approach
        if self._scripted_triggers:
            route_plan = _before_scripted_interaction(
                target.approach, self._scripted_triggers, target.interaction_facing,
            )
        route = execute_route(
            route_plan, actions, traversal,
            limits=replace(
                _ROUTE_LIMITS,
                transition_settle_frames=max(
                    _ROUTE_LIMITS.transition_settle_frames, self._arrival_steps * 24 + 120,
                ),
            ) if self._arrival_steps else _ROUTE_LIMITS,
            interruption_handler=guard, replanner=world.replanner(),
        )
        if not route.passed:
            raise RedTrainerStoryError("story approach did not reach its declared interaction")

        scripted_dialogue = None
        pending_dialogue = False
        if self._scripted_triggers:
            current = reader.read()
            if (
                current.map_id != target.trainer.map_id
                or (current.player_y, current.player_x) != route_plan.terminal_at
                or current.battle_state or not reader.read_input_readiness().ready
                or current.bag_items != before.raw.bag_items
                or current.player_money != before.raw.player_money
            ):
                raise RedTrainerStoryError("scripted trainer entry origin changed")
            guard._require_preserved_living_slots(current)
            qualified_dialogue = bind_scripted_trainer_dialogue(
                world.rom, reader, target, current, final_event_flag=int(EventFlag.BEAT_LANCE),
            )
            actions.execute(target.approach.steps[-1].macro_action)
            expected_pending = (target.trainer.trainer_class, target.trainer.trainer_set)
            # Wait only; the cartridge, not another directional input, owns
            # transition into its trainer dialogue. No retry of the entry step.
            for _ in range(24):
                current = reader.read()
                pending = reader.read_pending_trainer_battle_identity()
                if pending is not None and pending != expected_pending:
                    raise RedTrainerStoryError("scripted entry armed another trainer")
                if (
                    current.map_id != target.trainer.map_id or current.battle_state
                    or (current.player_y, current.player_x) not in {
                        route_plan.terminal_at, target.approach.terminal_at,
                    }
                ):
                    raise RedTrainerStoryError("scripted trainer entry left its declared boundary")
                if pending == expected_pending and (
                    current.player_y, current.player_x
                ) == target.approach.terminal_at:
                    pending_dialogue = True
                    break
                if reader.read_bottom_dialogue_box_visible() and (
                    current.player_y, current.player_x
                ) == target.approach.terminal_at:
                    qualified_dialogue()
                    scripted_dialogue = qualified_dialogue
                    break
                actions.execute(MacroAction(MacroActionKind.WAIT, repeat=12))
            else:
                raise RedTrainerStoryError("scripted trainer entry did not arm its declared target")

        def require_target() -> None:
            current = reader.read()
            if (
                current.map_id != target.trainer.map_id
                or (current.player_y, current.player_x) != target.approach.terminal_at
                or current.bag_items != before.raw.bag_items
                or current.player_money != before.raw.player_money
            ):
                raise RedTrainerStoryError("story interaction boundary or resources changed")
            zones = trainer_sight_zones(
                trainer_headers(world.rom, {target.trainer.map_id}, full_event_offsets=True),
                map_object_events(world.rom, {target.trainer.map_id}),
                current, reader.read_current_map_objects(),
            )
            matches = [z for z in zones if z.sprite_index == target.trainer.sprite_index]
            if len(matches) != 1:
                raise RedTrainerStoryError("story trainer disappeared")
            actual = matches[0]
            if (
                not actual.visible or actual.defeated or actual.at != target.trainer.at
                or actual.event_flag != target.trainer.event_flag
                or actual.trainer_class != target.trainer.trainer_class
                or actual.trainer_set != target.trainer.trainer_set
                or self._quote(actual.trainer_class, actual.trainer_set) != target.quote
            ):
                raise RedTrainerStoryError("story trainer identity or roster changed")
            guard._require_preserved_living_slots(current)

        require_target()
        if not self._scripted_triggers:
            face_pc_boundary(actions, reader, target.interaction_facing.value)
        controller = RedTrainerPartyController(reader, self.runtime.emulator)
        receipt = run_prepared_trainer_funding(
            reader, actions, target=target, validate_target=require_target,
            move_slot_policy=guard._safe_trainer_move,
            timing=BattleRuntimeTiming(max_runtime_pulses=1600),
            intent=BattleIntent(
                self.objective_id, battle_plan_id="cartridge-trainer-story",
                switch_capabilities=frozenset({BattleSwitchCapability.TEMPORARY_ROLE_PIVOT}),
                switch_limit=controller.maximum_switches, require_move_between_switches=True,
            ),
            battle_runner_override=controller.run,
            resume_pending_dialogue=pending_dialogue,
            validate_scripted_dialogue=scripted_dialogue,
        )
        after = self.runtime.adapter.observe()
        if (
            not after.input_ready or after.raw.battle_state
            or dependency_specimen_ledger(after.collection_observation)
            != dependency_specimen_ledger(before.collection_observation)
            or not self.expected_facts.issubset(after.game_state.facts)
            or after.raw.badge_bits != before.raw.badge_bits
            or after.raw.bag_items != before.raw.bag_items
        ):
            raise RedTrainerStoryError("story terminal lost collection, control or quest evidence")
        return ObjectiveSkillExecution(
            self.actions.actions_executed - start_actions,
            self.runtime.emulator.frame_count - start_frames,
            {"authority": "deterministic-trainer-controls", "story_event_verified": True,
             "route_steps": len(target.approach.steps), "switches": len(controller.switches),
             "moves_selected": controller.moves_selected, "victory_money": receipt.payout,
             "bag_items_spent": 0, "learned_battle_authority": False},
        )
