"""Opt-in cartridge-routed story battle, starting with the Lorelei objective.

Only the title adapter names the quest/map/event. The approach, roster, opening
party member and per-turn controls are observed or computed, not a walkthrough.
No availability claim is made outside the explicitly supported entry region.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .battle_runtime import (
    BattleIntent,
    BattleRuntimeTiming,
    BattleSwitchCapability,
    battle_policy_override_active,
)
from .domain import GameState
from .executor import CountingExecutor
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_parties import trainer_party_quote
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
from .observation import EventFlag, MapId
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
from .route_plan import RoutePlanningError

if TYPE_CHECKING:
    from .red_goal_context import RedGoalContextRuntime
    from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


class RedTrainerStoryError(RuntimeError):
    """The declared story target or its safe execution boundary changed."""


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

    def __post_init__(self) -> None:
        if self.objective_id not in {"defeat_lorelei", "defeat_bruno"}:
            raise RedTrainerStoryError("unsupported cartridge story objective")
        if self.objective_id == "defeat_bruno":
            self.expected_facts = frozenset({"league:bruno_defeated"})

    def _plan(self) -> tuple[RedGoalObservation, TrainerFundingCandidate, RedTrainerPartyPlan]:
        from .red_resource_goal_router import _walking_plan

        if self.world is None or battle_policy_override_active():
            raise RedTrainerStoryError("cartridge world or fixed battle authority unavailable")
        observation = self.runtime.adapter.observe()
        raw = observation.raw
        is_bruno = self.objective_id == "defeat_bruno"
        target_map = MapId.BRUNOS_ROOM if is_bruno else MapId.LORELEIS_ROOM
        target_event = EventFlag.BEAT_BRUNO if is_bruno else EventFlag.BEAT_LORELEI
        required_fact = "league:lorelei_defeated" if is_bruno else "story:victory_road_cleared"
        entry_maps = (
            {MapId.LORELEIS_ROOM, MapId.BRUNOS_ROOM} if is_bruno
            else {MapId.INDIGO_PLATEAU, MapId.INDIGO_PLATEAU_LOBBY, MapId.LORELEIS_ROOM}
        )
        if (
            not observation.input_ready or raw.battle_state != 0
            or raw.map_id not in entry_maps
            or required_fact not in observation.game_state.facts
            or self.expected_facts.intersection(observation.game_state.facts)
            or raw.event_flags is None
            or self.runtime.reader.read_bottom_dialogue_box_visible()
        ):
            raise RedTrainerStoryError("requires a settled, undefeated Indigo story boundary")
        headers = trainer_headers(self.world.rom, {target_map}, full_event_offsets=True)
        objects = map_object_events(self.world.rom, {target_map})
        zones = static_trainer_sight_zones(headers, objects, raw.event_flags)
        matches = tuple(z for z in zones if z.event_flag == target_event)
        if len(matches) != 1 or matches[0].defeated or matches[0].engage_distance != 0:
            raise RedTrainerStoryError("story trainer is not one undefeated interaction target")
        trainer = matches[0]
        quote = trainer_party_quote(self.world.rom, trainer.trainer_class, trainer.trainer_set)
        preparation = plan_trainer_party(observation.party, quote)
        start = Gen1TraversalObserver(self.runtime.reader, Gen1TrainerSightProjector(
            self.world.rom, self.runtime.reader, full_event_offsets=True,
        )).observe()
        approaches = []
        for facing in TrainerFacing:
            dy, dx = facing.delta
            at = (trainer.at[0] - dy, trainer.at[1] - dx)
            if min(at) < 0:
                continue
            try:
                plan = self.world.plan_feasible_to_map(start, int(trainer.map_id), goal_at=at)
            except RoutePlanningError:
                continue
            if len(plan.steps) <= 128 and _walking_plan(plan):
                approaches.append(TrainerFundingCandidate(trainer, quote, plan, facing))
        if not approaches:
            raise RedTrainerStoryError("no bounded walking approach to the story trainer")
        return observation, min(approaches, key=lambda item: len(item.approach.steps)), preparation

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        self._prepared = None
        if self._claimed:
            return ObjectiveSkillAvailability(False, "Story attempt already consumed.")
        try:
            prepared = self._plan()
        except (RedTrainerStoryError, ValueError, RoutePlanningError) as error:
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
        assert self.world is not None
        world = self.world
        reader = self.runtime.reader
        start_actions = self.actions.actions_executed
        start_frames = self.runtime.emulator.frame_count
        actions = CountingExecutor(HardCompositionActionLimiter(
            self.actions, maximum_actions_per_decision=self.max_actions,
            maximum_episode_actions=self.max_actions,
        ))
        quote = trainer_party_quote(
            self.world.rom, target.trainer.trainer_class, target.trainer.trainer_set,
        )
        prepare_trainer_lead(self.runtime, actions, preparation, current_quote=quote)
        prepared_raw = reader.read()
        guard = RecoveryRouteInterruptionHandler(
            actions, reader, tuple(prepared_raw.party_species_ids or ()),
            tuple(range(prepared_raw.party_count or 0)), maximum_flees=0, maximum_trainer_battles=0,
        )
        traversal = Gen1TraversalObserver(reader, Gen1TrainerSightProjector(
            self.world.rom, reader, full_event_offsets=True,
        ))
        route = execute_route(
            target.approach, actions, traversal, limits=_ROUTE_LIMITS,
            interruption_handler=guard, replanner=self.world.replanner(),
        )
        if not route.passed:
            raise RedTrainerStoryError("story approach did not reach its declared interaction")

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
                or trainer_party_quote(world.rom, actual.trainer_class, actual.trainer_set)
                != target.quote
            ):
                raise RedTrainerStoryError("story trainer identity or roster changed")
            guard._require_preserved_living_slots(current)

        require_target()
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
