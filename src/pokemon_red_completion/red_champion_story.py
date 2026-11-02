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
from .observation import (
    CurrentMapBlocks,
    EventFlag,
    FinalLeagueScene,
    MapId,
    RawGameState,
    event_flag_is_set,
)
from .quest import Specialist
from .red_dual_capability_curriculum_runtime import dependency_specimen_ledger
from .red_goal_manager import RedGoalObservation
from .red_learned_league import FrozenLeagueController
from .red_lorelei_story import FrozenLeagueChallengeStoryController, story_league_controller
from .red_routed_recovery import RecoveryRouteInterruptionHandler
from .red_trainer_control import RedTrainerPartyController
from .red_trainer_healing import bag_after_full_restores, require_story_recovery_stock
from .red_trainer_party import RedTrainerPartyPlan, plan_trainer_party, prepare_trainer_lead
from .red_trainer_survival import RedTrainerSurvivalController
from .referee import CHAMPION_DEFEATED_FACT, CompletionReferee
from .route import HALL_OF_FAME_FACT
from .route_executor import execute_route
from .route_plan import RoutePlan, RoutePlanningError, RouteStep

if TYPE_CHECKING:
    from .red_goal_context import RedGoalContextRuntime
    from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


class RedChampionStoryError(RuntimeError):
    """A qualified final-story attempt left its declared contract."""


def _live_champion_rematch_ready(raw: RawGameState) -> bool:
    return (
        raw.event_flags is not None
        and event_flag_is_set(raw.event_flags, EventFlag.BEAT_LANCE)
        and not event_flag_is_set(raw.event_flags, EventFlag.BEAT_CHAMPION_RIVAL)
    )


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
    maximum_full_restores: int = 0
    recovery_controller: str = "critical-inclusive"
    rematch: bool = False
    maximum_level_deficit: int = 5
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
    _prepared_budget: int | None = field(default=None, init=False)
    _prepared_controller: str = field(default="critical-inclusive", init=False)
    _prepared_rematch: bool = field(default=False, init=False)
    _prepared_learned_controller: (
        FrozenLeagueController | FrozenLeagueChallengeStoryController | None
    ) = field(default=None, init=False)
    _prepared_story_binding: object | None = field(default=None, init=False)
    _prepared_level_deficit: int | None = field(default=None, init=False)

    def _learned_controller(self):
        return story_league_controller(self.runtime, self.objective_id, rematch=self.rematch)

    def __post_init__(self) -> None:
        from .red_lorelei_story import ScopedAssistedChampionController
        from .scenario_lab import ScenarioPartition

        if type(self.rematch) is not bool:  # noqa: E721
            raise RedChampionStoryError("rematch must be a boolean")
        allowed = self.maximum_level_deficit == 5 or (
            self.maximum_level_deficit == 7
            and self.recovery_controller == "scoped-assisted-champion-development"
        )
        if (
            not allowed
            and self.runtime is not None
            and (self.recovery_controller == "scoped-assisted-champion-development")
        ):
            owner = self._learned_controller()
            allowed = (
                type(owner) is ScopedAssistedChampionController
                and owner.battler.source_partition is ScenarioPartition.DEVELOPMENT
                and self.maximum_level_deficit == owner.declared_level_deficit
            )
        if (
            type(self.maximum_level_deficit) is not int  # noqa: E721
            or not 0 <= self.maximum_level_deficit <= 100
            or not allowed
        ):
            raise RedChampionStoryError(
                "changed level-screen requires exact Champion development scope"
            )

    def _plan(self) -> _Prepared:
        from .red_resource_goal_router import _walking_plan

        self.__post_init__()
        if self.world is None or battle_policy_override_active():
            raise RedChampionStoryError("cartridge world or fixed battle authority unavailable")
        before = self.runtime.adapter.observe()
        if self.recovery_controller not in {
            "critical-inclusive",
            "ordinary-bounded-healing",
            "damage-bounded-zero-item",
            "frozen-k-development",
            "frozen-damage-league-challenge-development",
            "isolated-story-copy-development",
            "frozen-risk-cost-champion-development",
            "frozen-risk-cost-league-chain-development",
            "scoped-assisted-champion-development",
        }:
            raise RedChampionStoryError("unsupported recovery controller")
        learned = self._learned_controller()
        learned_mode = self.recovery_controller in {
            "frozen-k-development",
            "frozen-damage-league-challenge-development",
            "isolated-story-copy-development",
            "frozen-risk-cost-champion-development",
            "frozen-risk-cost-league-chain-development",
            "scoped-assisted-champion-development",
        }
        if learned_mode != (learned is not None) or (
            learned is not None
            and self.recovery_controller
            != getattr(learned, "controller_name", "frozen-k-development")
        ):
            raise RedChampionStoryError("explicit learned League binding differs")
        if learned is not None and self.maximum_full_restores:
            raise RedChampionStoryError("learned League qualification is zero-item")
        require_story_recovery_stock(before.raw, self.maximum_full_restores)
        reader = self.runtime.reader
        historical_boundary = (
            "league:lance_defeated" in before.game_state.facts
            and CHAMPION_DEFEATED_FACT not in before.game_state.facts
        )
        if (
            before.raw.map_id != MapId.LANCES_ROOM
            or before.raw.battle_state
            or not before.input_ready
            or self.runtime.emulator.pressed_buttons
            or reader.read_bottom_dialogue_box_visible()
            or reader.read_pending_trainer_battle_identity() is not None
            or not (
                _live_champion_rematch_ready(before.raw) if self.rematch else historical_boundary
            )
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
        if learned is not None and hasattr(learned, "require_champion_target"):
            learned.require_champion_target(script, quote)
        party = (
            plan_trainer_party(
                before.party,
                quote,
                minimum_hp_ratio=0.0,
                allow_fainted_reserves=True,
                maximum_level_deficit=self.maximum_level_deficit,
                **(
                    {"allow_status": True}
                    if getattr(
                        getattr(getattr(learned, "battler", None), "development_story_scope", None),
                        "diagnostic_status_entry",
                        False,
                    )
                    else {}
                ),
            )
            if learned is not None and learned.recovery_contract == "league-profit-recovery-v1"
            else plan_trainer_party(before.party, quote, minimum_hp_ratio=0.0)
            if self.recovery_controller == "damage-bounded-zero-item"
            else plan_trainer_party(before.party, quote)
        )
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
        self._prepared_budget = None
        if self._claimed:
            return ObjectiveSkillAvailability(False, "Final-story attempt already consumed.")
        try:
            prepared = self._plan()
        except (RedChampionStoryError, ValueError, CartridgeReadError, RoutePlanningError) as error:
            return ObjectiveSkillAvailability(False, str(error))
        if prepared.before.game_state != state:
            return ObjectiveSkillAvailability(False, "Final-story observation changed.")
        self._prepared = prepared
        self._prepared_budget = self.maximum_full_restores
        self._prepared_controller = self.recovery_controller
        self._prepared_rematch = self.rematch
        self._prepared_level_deficit = self.maximum_level_deficit
        self._prepared_learned_controller = self._learned_controller()
        self._prepared_story_binding = getattr(
            self._prepared_learned_controller, "binding_identity", None
        )
        return ObjectiveSkillAvailability(
            True, "Qualified final scene with observed party controls."
        )

    @property
    def prepared_lead_plan(self):
        """Read the already-bound opening swap without planning or input."""
        return None if self._prepared is None else self._prepared.party.lead

    def execute(self) -> ObjectiveSkillExecution:
        from .red_resource_goal_router import _ROUTE_LIMITS

        if self._claimed or self._prepared is None:
            raise RedChampionStoryError("final story requires an unconsumed availability binding")
        self._claimed = True
        prepared = self._prepared
        runtime, reader = self.runtime, self.runtime.reader
        if (
            runtime.adapter.observe() != prepared.before
            or self._prepared_budget != self.maximum_full_restores
            or self._prepared_controller != self.recovery_controller
            or self._prepared_rematch != self.rematch
            or self._prepared_level_deficit != self.maximum_level_deficit
            or self._prepared_learned_controller is not self._learned_controller()
            or self._prepared_story_binding
            != getattr(self._prepared_learned_controller, "binding_identity", None)
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
        recovery = (
            self._prepared_learned_controller is not None
            and self._prepared_learned_controller.recovery_contract == "league-profit-recovery-v1"
        )
        guard = RecoveryRouteInterruptionHandler(
            actions,
            reader,
            tuple(baseline.party_species_ids or ()),
            tuple(i for i, hp in enumerate(baseline.party_hp or ()) if hp > 0)
            if recovery
            else tuple(range(baseline.party_count or 0)),
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

        controller = (
            RedTrainerSurvivalController(reader, runtime.emulator, (), self.maximum_full_restores)
            if (
                self.maximum_full_restores or self.recovery_controller == "damage-bounded-zero-item"
            )
            else RedTrainerPartyController(reader, runtime.emulator)
        )

        if self.maximum_full_restores and self.recovery_controller == "ordinary-bounded-healing":
            controller = RedTrainerPartyController(
                reader,
                runtime.emulator,
                maximum_full_restores=self.maximum_full_restores,
            )
        controller = self._learned_controller() or controller

        def preserve(raw: RawGameState) -> None:
            if recovery:
                assert self._prepared_learned_controller is not None
                self._prepared_learned_controller.require_party_hp(raw)
            else:
                guard._require_preserved_living_slots(raw)
            spent = controller.heals_claimed if self.maximum_full_restores else 0
            expected_bag = (
                bag_after_full_restores(baseline.bag_items or (), spent)
                if self.maximum_full_restores
                else baseline.bag_items
            )
            if (
                raw.party_species_ids != baseline.party_species_ids
                or raw.bag_items != expected_bag
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

        def verify_battle_exit(raw: RawGameState) -> None:
            preserve(raw)
            completed_escort = (
                raw.map_id == MapId.HALL_OF_FAME
                and raw.event_flags is not None
                and event_flag_is_set(raw.event_flags, EventFlag.BEAT_CHAMPION_RIVAL)
            )
            if (
                raw.map_id != MapId.CHAMPIONS_ROOM
                and not completed_escort
                or raw.battle_state
                or raw.battle_result != 0
            ):
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
                require_move_between_switches=(
                    not self.maximum_full_restores
                    or self.recovery_controller == "ordinary-bounded-healing"
                ),
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
            live_champion_verified = after.raw.event_flags is not None and event_flag_is_set(
                after.raw.event_flags,
                EventFlag.BEAT_CHAMPION_RIVAL,
            )
            # Durable historical facts survive Continue. A new rematch must
            # finish its own native escort, not stop in Champion dialogue merely
            # because an older Hall-of-Fame fact is still in semantic memory.
            if (
                after.raw.map_id == MapId.HALL_OF_FAME
                and (CompletionReferee().inspect(after.game_state).complete)
                and (not self.rematch or live_champion_verified)
            ):
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
                        "authority": (
                            getattr(
                                self._prepared_learned_controller,
                                "controller_name",
                                "frozen-k-league-development",
                            )
                            if self._prepared_learned_controller
                            else "deterministic-trainer-controls"
                        ),
                        "learned_battle_authority": self._prepared_learned_controller is not None,
                        "rematch": self.rematch,
                        "concurrent_champion_and_hall_of_fame": True,
                        "bag_items_spent": (
                            controller.heals_claimed if self.maximum_full_restores else 0
                        ),
                        "maximum_full_restores": self.maximum_full_restores,
                        "battle_controller": (
                            getattr(
                                self._prepared_learned_controller,
                                "controller_name",
                                "frozen-k-development",
                            )
                            if self._prepared_learned_controller
                            else "ordinary-bounded-healing"
                            if self.maximum_full_restores
                            and self.recovery_controller == "ordinary-bounded-healing"
                            else "damage-aware"
                            if self.maximum_full_restores
                            else "ordinary"
                        ),
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
