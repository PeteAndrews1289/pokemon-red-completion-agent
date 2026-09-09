"""One prospective final-story option: computed entry and observed party combat.

No legacy fixed Champion recipe, RNG schedule, resource replenishment, or
learned-battle promotion. The cartridge owns its automatic scene movement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
from .gen1_champion_script import ChampionScriptBinding, champion_script_binding
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_parties import trainer_party_quote
from .gen1_trainer_sight import Gen1TrainerSightProjector
from .goal_manager_composition_qualification import HardCompositionActionLimiter
from .objective_skills import ObjectiveSkillAvailability, ObjectiveSkillExecution
from .observation import CurrentMapBlocks, FinalLeagueScene, MapId, RawGameState, event_flag_is_set
from .quest import Specialist
from .red_dual_capability_curriculum_runtime import dependency_specimen_ledger
from .red_goal_manager import RedGoalObservation
from .red_routed_recovery import RecoveryRouteInterruptionHandler
from .red_trainer_control import RedTrainerPartyController
from .red_trainer_party import RedTrainerPartyPlan, plan_trainer_party, prepare_trainer_lead
from .referee import CHAMPION_DEFEATED_FACT, CompletionReferee
from .route import HALL_OF_FAME_FACT
from .route_executor import execute_route
from .route_plan import RoutePlan, RoutePlanningError, RouteStep

if TYPE_CHECKING:
    from .red_goal_context import RedGoalContextRuntime
    from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


class RedChampionStoryError(RuntimeError):
    """A qualified final-story attempt left its declared contract."""


@dataclass(frozen=True, slots=True)
class _Prepared:
    before: RedGoalObservation
    script: ChampionScriptBinding
    party: RedTrainerPartyPlan
    blocks: CurrentMapBlocks
    world: StrategicScenarioRouteWorld
    approach: RoutePlan
    entry: RouteStep
    scene: FinalLeagueScene


@dataclass(slots=True)
class RedCartridgeChampionSkill:
    runtime: RedGoalContextRuntime
    actions: CountingExecutor
    world: StrategicScenarioRouteWorld | None
    objective_id: str = field(default="defeat_champion", init=False)
    specialist: Specialist = field(default=Specialist.BATTLE, init=False)
    expected_facts: frozenset[str] = field(
        default=frozenset({CHAMPION_DEFEATED_FACT}),
        init=False,
    )
    additional_effect_facts: frozenset[str] = field(
        default=frozenset({HALL_OF_FAME_FACT}),
        init=False,
    )
    max_actions: int = field(default=6000, init=False)
    max_frames: int = field(default=3000000, init=False)
    _prepared: _Prepared | None = field(default=None, init=False)
    _claimed: bool = field(default=False, init=False)

    def _plan(self) -> _Prepared:
        from .red_resource_goal_router import _walking_plan

        if self.world is None or battle_policy_override_active():
            raise RedChampionStoryError("cartridge world or fixed battle authority unavailable")
        before = self.runtime.adapter.observe()
        reader = self.runtime.reader
        if (
            before.raw.map_id != MapId.LANCES_ROOM
            or before.raw.battle_state
            or not before.input_ready
            or self.runtime.emulator.pressed_buttons
            or reader.read_bottom_dialogue_box_visible()
            or reader.read_pending_trainer_battle_identity() is not None
            or "league:lance_defeated" not in before.game_state.facts
            or CHAMPION_DEFEATED_FACT in before.game_state.facts
        ):
            raise RedChampionStoryError("requires the living, settled post-Lance field boundary")
        scene = reader.read_final_league_scene()
        if scene.map_id != before.raw.map_id or scene.script_stage not in {0, 1}:
            raise RedChampionStoryError("next room scene was already advanced")
        script = champion_script_binding(self.world.rom, scene.rival_starter)
        if script.event_flag != 2305 or event_flag_is_set(
            before.raw.event_flags, script.event_flag
        ):
            raise RedChampionStoryError("final-story event is mismatched or already consumed")
        quote = trainer_party_quote(self.world.rom, script.opponent, script.trainer_set)
        party = plan_trainer_party(before.party, quote)
        blocks = reader.read_current_map_blocks()
        if blocks.map_id != before.raw.map_id:
            raise RedChampionStoryError("field map changed during terrain observation")
        world = self.world.with_current_blocks(blocks)
        start = Gen1TraversalObserver(
            reader,
            Gen1TrainerSightProjector(
                world.rom,
                reader,
                full_event_offsets=True,
            ),
        ).observe()
        full = world.plan_feasible_to_map(start, int(MapId.CHAMPIONS_ROOM))
        if not full.steps or len(full.steps) > 64 or not _walking_plan(full):
            raise RedChampionStoryError("no bounded walking final-room entry")
        entry = full.steps[-1]
        if (
            entry.source_map != before.raw.map_id
            or entry.expected_map != MapId.CHAMPIONS_ROOM
            or entry.kind != "warp"
            or entry.action_kind is not MacroActionKind.MOVE
            or any(not step.stays_on_map for step in full.steps[:-1])
        ):
            raise RedChampionStoryError("final-story route must end at its sole entry warp")
        approach = world.plan_feasible_to_map(start, before.raw.map_id, goal_at=entry.source_at)
        if approach.steps != full.steps[:-1]:
            raise RedChampionStoryError("final-story walking prefix differs from its entry plan")
        return _Prepared(before, script, party, blocks, world, approach, entry, scene)

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        self._prepared = None
        if self._claimed:
            return ObjectiveSkillAvailability(False, "Final-story attempt already consumed.")
        try:
            prepared = self._plan()
        except (RedChampionStoryError, ValueError, CartridgeReadError, RoutePlanningError) as error:
            return ObjectiveSkillAvailability(False, str(error))
        if prepared.before.game_state != state:
            return ObjectiveSkillAvailability(False, "Final-story observation changed.")
        self._prepared = prepared
        return ObjectiveSkillAvailability(
            True, "Qualified final scene with observed party controls."
        )

    def execute(self) -> ObjectiveSkillExecution:
        from .red_resource_goal_router import _ROUTE_LIMITS

        if self._claimed or self._prepared is None:
            raise RedChampionStoryError("final story requires an unconsumed availability binding")
        self._claimed = True
        prepared = self._prepared
        runtime, reader = self.runtime, self.runtime.reader
        if (
            runtime.adapter.observe() != prepared.before
            or battle_policy_override_active()
            or reader.read_current_map_blocks() != prepared.blocks
            or runtime.emulator.pressed_buttons
            or reader.read_bottom_dialogue_box_visible()
            or not reader.read_input_readiness().ready
            or reader.read_final_league_scene() != prepared.scene
            or reader.read_pending_trainer_battle_identity() is not None
        ):
            raise RedChampionStoryError("final-story origin or authority changed")
        if (
            champion_script_binding(
                prepared.world.rom, reader.read_final_league_scene().rival_starter
            )
            != prepared.script
        ):
            raise RedChampionStoryError("final trainer roster selector changed")
        initial_actions, initial_frames = (
            self.actions.actions_executed,
            runtime.emulator.frame_count,
        )
        actions = CountingExecutor(
            HardCompositionActionLimiter(
                self.actions,
                maximum_actions_per_decision=self.max_actions,
                maximum_episode_actions=self.max_actions,
            )
        )
        quote = trainer_party_quote(
            prepared.world.rom,
            prepared.script.opponent,
            prepared.script.trainer_set,
        )
        prepare_trainer_lead(runtime, actions, prepared.party, current_quote=quote)
        baseline = reader.read()
        guard = RecoveryRouteInterruptionHandler(
            actions,
            reader,
            tuple(baseline.party_species_ids or ()),
            tuple(range(baseline.party_count or 0)),
            maximum_flees=0,
            maximum_trainer_battles=0,
        )
        traversal = Gen1TraversalObserver(
            reader,
            Gen1TrainerSightProjector(
                prepared.world.rom,
                reader,
                full_event_offsets=True,
            ),
        )
        route = execute_route(
            prepared.approach,
            actions,
            traversal,
            limits=_ROUTE_LIMITS,
            interruption_handler=guard,
            replanner=prepared.world.replanner(),
        )
        current = reader.read()
        if (
            not route.passed
            or current.map_id != prepared.entry.source_map
            or (current.player_y, current.player_x) != prepared.entry.source_at
            or not reader.read_input_readiness().ready
            or current.battle_state
        ):
            raise RedChampionStoryError("final-story approach did not reach its entry boundary")

        def preserve(raw: RawGameState) -> None:
            guard._require_preserved_living_slots(raw)
            if (
                raw.party_species_ids != baseline.party_species_ids
                or raw.bag_items != baseline.bag_items
                or raw.badge_bits != baseline.badge_bits
            ):
                raise RedChampionStoryError("final scene changed protected party or resources")

        preserve(current)
        actions.execute(prepared.entry.macro_action)  # owned once, never route-retried
        for _ in range(160):
            current = reader.read()
            preserve(current)
            if current.map_id not in {prepared.entry.source_map, MapId.CHAMPIONS_ROOM}:
                raise RedChampionStoryError("final entry reached another map")
            if current.battle_state:
                if (
                    current.battle_state != 2
                    or reader.read_active_trainer_identity() != prepared.script.active_identity
                ):
                    raise RedChampionStoryError("final entry armed another opponent")
                break
            if current.player_money != baseline.player_money:
                raise RedChampionStoryError("final entry changed money before combat")
            kind = MacroActionKind.WAIT
            if current.map_id == MapId.CHAMPIONS_ROOM:
                scene = reader.read_final_league_scene()
                if scene.script_stage not in {1, 2, 3}:
                    raise RedChampionStoryError("unexpected pre-battle final scene stage")
                if reader.read_bottom_dialogue_box_visible() and not scene.queued_movement:
                    kind = MacroActionKind.CONFIRM
            if kind is MacroActionKind.CONFIRM:
                actions.execute(MacroAction(MacroActionKind.CONFIRM))
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=30))
        else:
            raise RedChampionStoryError("final entry did not reach its declared trainer")

        def combat_guard(raw: RawGameState) -> None:
            preserve(raw)
            if (
                raw.battle_state == 2
                and reader.read_active_trainer_identity() != prepared.script.active_identity
            ):
                raise RedChampionStoryError("active final trainer identity changed")

        controller = RedTrainerPartyController(reader, runtime.emulator)

        def verify_battle_exit(raw: RawGameState) -> None:
            preserve(raw)
            if raw.map_id != MapId.CHAMPIONS_ROOM or raw.battle_state or raw.battle_result != 0:
                raise RedChampionStoryError("final combat exit is not a field victory")

        controller.run(
            reader,
            actions,
            guard._safe_trainer_move,
            expected_map=int(MapId.CHAMPIONS_ROOM),
            intent=BattleIntent(
                self.objective_id,
                battle_plan_id="cartridge-final-story",
                switch_capabilities=frozenset({BattleSwitchCapability.TEMPORARY_ROLE_PIVOT}),
                switch_limit=controller.maximum_switches,
                require_move_between_switches=True,
            ),
            timing=BattleRuntimeTiming(max_runtime_pulses=1600),
            label="observed final trainer",
            consume_battle_start_schedule=False,
            move_decision_guard=combat_guard,
            battle_exit_guard=verify_battle_exit,
        )
        for _ in range(600):
            after = runtime.adapter.observe()
            preserve(after.raw)
            if after.raw.battle_state or after.raw.battle_result != 0:
                raise RedChampionStoryError("final battle did not end in victory")
            if (
                baseline.player_money is None
                or after.raw.player_money
                != quote.expected_money_after(
                    baseline.player_money,
                )
            ):
                raise RedChampionStoryError("final battle payout differs from the cartridge quote")
            if CompletionReferee().inspect(after.game_state).complete:
                if runtime.emulator.pressed_buttons or dependency_specimen_ledger(
                    after.collection_observation,
                ) != dependency_specimen_ledger(prepared.before.collection_observation):
                    raise RedChampionStoryError(
                        "completion lost living specimens or released controls"
                    )
                return ObjectiveSkillExecution(
                    self.actions.actions_executed - initial_actions,
                    runtime.emulator.frame_count - initial_frames,
                    {
                        "authority": "deterministic-trainer-controls",
                        "learned_battle_authority": False,
                        "concurrent_champion_and_hall_of_fame": True,
                        "bag_items_spent": 0,
                        "switches": len(controller.switches),
                        "moves_selected": controller.moves_selected,
                        "scene_movement_authority": "cartridge",
                        "victory_money": quote.expected_victory_money,
                    },
                )
            if after.raw.map_id != MapId.CHAMPIONS_ROOM:
                raise RedChampionStoryError("epilogue left without concurrent completion evidence")
            scene = reader.read_final_league_scene()
            if not 3 <= scene.script_stage <= 10:
                raise RedChampionStoryError("unexpected final epilogue stage")
            kind = MacroActionKind.WAIT
            if (
                reader.read_bottom_dialogue_box_visible()
                and not scene.queued_movement
                and not scene.npc_moving
            ):
                kind = MacroActionKind.CONFIRM
            if kind is MacroActionKind.CONFIRM:
                actions.execute(MacroAction(MacroActionKind.CONFIRM))
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=12))
        raise RedChampionStoryError("final epilogue exhausted its bound")
