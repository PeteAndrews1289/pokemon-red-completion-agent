"""Opt-in Red preparation/story bindings; no policy, fit or automatic dispatch.

Caller authenticates the source and complete ledger, durably claims a fresh
packet, and retains every terminal. A quote is not native qualification or
permission to reuse a consumed packet. Existing models own battle choices;
trainee, venue and travel are explicitly disclosed support.
"""

from dataclasses import dataclass, replace

from .executor import CountingExecutor, WindowedFrameBudgetController
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import Gen1TrainerSightProjector
from .gen1_traversal import cut_capabilities
from .global_router import advance_macro_state
from .goal_manager import (
    GoalAvailability,
    GoalFailureReason,
    GoalKind,
    GoalOpportunity,
    GoalUnavailableReason,
)
from .goal_manager_composition_qualification import HardCompositionActionLimiter
from .goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from .hideout import DEFAULT_HIDEOUT_TIMING
from .objective_skills import ObjectiveSkillRegistry
from .observation import MapId
from .post_battle_strategy import PreparationCostTotals, build_post_battle_strategy_menu
from .provenance import canonical_sha256
from .red_goal_manager import RedStoryGoalBindingProvider
from .red_goal_skills import _POKEMON_CENTER_MAPS, _raw_party_fully_restored
from .red_learned_trainer import FROZEN_K_SHA256, K_QUALIFICATION_SHA256, FrozenTrainerBattler
from .red_living_dex_multifamily_curriculum import map_id_for_wild_source
from .red_living_dex_provider_curriculum import RedEncounterSourceTarget
from .red_living_dex_wild_corridor import derive_red_living_dex_wild_corridor
from .red_lorelei_story import FrozenLoreleiStoryController, LoreleiStoryBattleStopped
from .red_party_preparation import observe_preparation_members, preparation_trainee
from .red_trainer_evolution import RedTrainerEvolutionGuard
from .red_trainer_story import RedCartridgeLoreleiSkill
from .red_wild_preparation import execute_wild_preparation, wild_training_return_reason
from .route_plan import RoutePlanningError


@dataclass(frozen=True)
class PostBattlePacketLimits:
    """One selected excursion or story attempt; never a repeating run."""

    actions: int = 3000
    frames: int = 300000
    seconds: int = 60
    wild_battles: int = 8

    def __post_init__(self):
        for name, maximum in (
            ("actions", 6000),
            ("frames", 600000),
            ("seconds", 180),
            ("wild_battles", 8),
        ):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"invalid post-battle packet {name}")


@dataclass(frozen=True)
class PreparationRouteQuote:
    corridor: object
    approach_steps: int
    return_steps: int
    recovery_home_map: int


def projected_route_terminal(graph, start, plan):
    """Preserve the router's retained outside-map semantics across the approach."""
    state = (start.map_id, start.last_outside_map)
    for edge in plan.macro_path.edges:
        state = advance_macro_state(graph, state, edge)
        if state is None:
            raise RoutePlanningError("unresolved preparation return context")
    if state[0] != plan.terminal_map:
        raise RoutePlanningError("preparation terminal context differs")
    return replace(
        start,
        map_id=state[0],
        at=plan.terminal_at,
        mode=plan.terminal_mode,
        last_outside_map=state[1],
        occupied=frozenset(),
        hazards=(),
    )


def quote_preparation_route(route, reader, source_id, home):
    """Cartridge-derived encounter pair plus forward and recovery reachability.

    Return planning uses a projected route endpoint, not a played outcome or an
    assertion that dynamic hazards cannot change. Runtime replans and rechecks.
    The same excluded-map graph and Cut-only capability used by execution apply.
    """
    if type(home) is not int or home not in _POKEMON_CENTER_MAPS | {MapId.INDIGO_PLATEAU_LOBBY}:
        raise ValueError("supported recovery home required")
    if not route.full_event_offsets or not route.observe_terrain:
        raise ValueError("observed terrain and full trainer hazards required")
    target = int(map_id_for_wild_source(source_id))
    if target in route.excluded_maps or home in route.excluded_maps:
        raise ValueError("preparation destination excluded")
    world = route.route_world
    world = replace(
        world,
        macro_graph=replace(
            world.macro_graph,
            edges={
                m: tuple(e for e in edges if e.target_map not in route.excluded_maps)
                for m, edges in world.macro_graph.edges.items()
                if m not in route.excluded_maps
            },
        ),
    ).with_current_blocks(reader.read_current_map_blocks())
    observer = Gen1TraversalObserver(
        reader,
        Gen1TrainerSightProjector(route.rom, reader, full_event_offsets=True),
        capability_projector=cut_capabilities,
    )
    start = observer.observe()
    if not start.ready or start.interruption is not None:
        raise ValueError("preparation requires settled traversal")
    excluded = set(world.object_blockers[target])
    last_failure = "no candidate"
    for _ in range(80):
        corridor = derive_red_living_dex_wild_corridor(
            RedEncounterSourceTarget(source_id),
            world.terrain[target],
            world.local_graphs[target],
            cartridge=route.rom,
            excluded=excluded,
        )
        try:
            outward = world.plan_feasible_to_map(start, target, goal_at=corridor.origin_at)
            returned = world.plan_feasible_to_map(
                projected_route_terminal(world.macro_graph, start, outward),
                home,
                goal_at=(11, 7) if home == MapId.INDIGO_PLATEAU_LOBBY else (7, 3),
            )
            if len(outward.steps) > 256 or len(returned.steps) > 256:
                raise RoutePlanningError("preparation route exceeds quote bound")
            return PreparationRouteQuote(corridor, len(outward.steps), len(returned.steps), home)
        except RoutePlanningError as error:
            last_failure = str(error)
            excluded.update((corridor.origin_at, corridor.terminal_at))
    raise ValueError(f"no bounded round-trip preparation corridor: {last_failure}")


class RedPostBattleProviders:
    """Bind both native skills once to the same authenticated field observation.

    authenticate() must reject any source, ledger, model or packet-identity drift.
    claim(kind) must durably create a fresh attempt and return exactly True.
    retain(kind, report, error) must save the actual terminal even after failure.
    These are caller-owned persistence hooks, not a model interface.
    """

    def __init__(
        self,
        *,
        runtime,
        actions,
        story_skill,
        wild_battler,
        route,
        source_id,
        recovery_home_map,
        plan,
        attempts,
        cumulative_costs,
        battle,
        authenticate,
        claim,
        retain,
        record,
        limits=None,
    ):
        limits = PostBattlePacketLimits() if limits is None else limits
        if not isinstance(limits, PostBattlePacketLimits):
            raise TypeError("typed packet limits required")
        if not isinstance(runtime.emulator, WindowedFrameBudgetController):
            raise TypeError("hard frame controller required")
        wall_limit = getattr(runtime.emulator, "maximum_wall_seconds", None)
        if type(wall_limit) is not int or not 0 < wall_limit <= limits.seconds:
            raise ValueError("outer cooperative wall-time bound required")
        if not isinstance(actions, CountingExecutor):
            raise TypeError("counted native action port required")
        if (
            not isinstance(story_skill, RedCartridgeLoreleiSkill)
            or story_skill.runtime is not runtime
            or story_skill.actions is not actions
            or not isinstance(runtime.league_story_battle_controller, FrozenLoreleiStoryController)
        ):
            raise ValueError("explicit first-Lorelei story skill required")
        actor = runtime.league_story_battle_controller
        actor.require_objective(story_skill.objective_id, rematch=story_skill.rematch)
        if actor.battler.session is not runtime.emulator:
            raise ValueError("story actor must use the bounded controller")
        if (
            not isinstance(wild_battler, FrozenTrainerBattler)
            or wild_battler.session is not runtime.emulator
            or (wild_battler.model_sha256, wild_battler.qualification_sha256)
            != (FROZEN_K_SHA256, K_QUALIFICATION_SHA256)
        ):
            raise ValueError("exact K on the bounded controller required")
        if any(not callable(h) for h in (authenticate, claim, retain, record)):
            raise TypeError("authentication, durable claim and retention hooks required")
        if not isinstance(cumulative_costs, PreparationCostTotals):
            raise TypeError("whole-envelope costs required")
        self.runtime, self.actions, self.story_skill = runtime, actions, story_skill
        self.wild_battler, self.route, self.source_id = wild_battler, route, source_id
        self.home, self.plan, self.attempts = recovery_home_map, plan, attempts
        self.costs, self.battle, self.limits = cumulative_costs, battle, limits
        self.authenticate, self.claim, self.retain, self.record = (
            authenticate,
            claim,
            retain,
            record,
        )
        self._used = False
        self._menu = None
        self.preparation_quote = None
        self.preparation_reason = None

    def _configuration(self):
        actor = self.runtime.league_story_battle_controller
        actor.require_objective(self.story_skill.objective_id, rematch=self.story_skill.rematch)
        return (
            self.limits,
            self.plan,
            self.attempts,
            self.costs,
            self.route,
            self.home,
            self.source_id,
            self.preparation_quote,
            id(self.runtime.emulator),
            id(self.actions),
            actor.binding_identity,
            id(self.wild_battler.session),
            self.wild_battler.model_sha256,
            self.wild_battler.qualification_sha256,
            canonical_sha256(self.wild_battler.model.to_dict()),
        )

    def quote(self):
        if self._used or self._menu is not None:
            raise ValueError("post-battle quote already bound or consumed")
        self.authenticate()
        r = self.runtime
        before_cost = (self.actions.actions_executed, r.emulator.frame_count)
        before = r.adapter.observe()
        if (
            not before.input_ready
            or before.raw.battle_state
            or r.emulator.pressed_buttons
            or not _raw_party_fully_restored(before.raw)
        ):
            raise ValueError("restored input-ready field required")
        members = observe_preparation_members(r.emulator, self.plan)
        story = RedStoryGoalBindingProvider(
            r.adapter.graph,
            ObjectiveSkillRegistry((self.story_skill,)),
            r.observer,
        ).offer(before)
        training = None
        try:
            preparation_trainee(self.plan, members, self.attempts)
            b, c, cap = self.plan.budget, self.costs, self.limits
            if (
                c.attempts >= b.max_attempts
                or c.heals >= b.max_heals
                or c.actions + cap.actions > b.max_actions
                or c.frames + cap.frames > b.max_frames
                or c.seconds + cap.seconds > b.max_seconds
            ):
                raise ValueError("remaining preparation envelope cannot cover packet")
            trainee = preparation_trainee(self.plan, members, self.attempts)
            stop = wild_training_return_reason(
                members,
                trainee.specimen_ref,
                dict(self.plan.targets)[trainee.specimen_ref],
                minimum_ready_members=min(2, len(members)),
            )
            if stop is not None:
                raise ValueError(stop)
            self.preparation_quote = quote_preparation_route(
                self.route, r.reader, self.source_id, self.home
            )
            training = ExecutableGoalBinding(
                "pokemon.red:bounded-wild-preparation",
                GoalKind.DEVELOP_TEAM,
                min(1.0, cap.actions / 5000),
                0.3,
                lambda: self._execute(GoalKind.DEVELOP_TEAM),
                lambda report: self._verify(GoalKind.DEVELOP_TEAM, report),
            )
        except (ValueError, RoutePlanningError) as error:
            self.preparation_reason = str(error)
        self._before, self._members = before, members
        self._boxes = r.reader.read_all_box_states()
        self._evolution = RedTrainerEvolutionGuard.from_rom(self.route.rom, r.emulator)
        self._completed = r.adapter.graph.completed_ids(before.game_state)
        self._story_binding = story.binding
        bound = tuple(b for b in (story.binding, training) if b is not None)
        if not bound:
            raise ValueError(
                "no executable post-battle alternatives; inspect provider availability"
            )
        bound = tuple(
            replace(
                b,
                execute=lambda kind=b.kind: self._execute(kind),
                verify=lambda report, kind=b.kind: self._verify(kind, report),
            )
            for b in bound
        )
        opportunities = tuple(
            next(
                (b.opportunity for b in bound if b.kind is kind),
                GoalOpportunity(
                    f"unavailable:{kind.value}",
                    kind,
                    GoalAvailability.UNAVAILABLE,
                    unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
                ),
            )
            for kind in (GoalKind.ADVANCE_STORY, GoalKind.DEVELOP_TEAM)
        )
        self._menu = build_post_battle_strategy_menu(
            bindings=GoalBindingSet(opportunities, bound),
            situation=before.situation,
            battle=self.battle,
            plan=self.plan,
            members=members,
            attempts=self.attempts,
            cumulative_costs=self.costs,
            field_ready=True,
        )
        if (
            r.adapter.observe() != before
            or (self.actions.actions_executed, r.emulator.frame_count) != before_cost
            or r.emulator.pressed_buttons
        ):
            raise ValueError("source changed while quoting alternatives")
        self.authenticate()
        self._bound_configuration = self._configuration()
        return self._menu

    def _execute(self, kind):
        r = self.runtime
        if self._used or self._menu is None:
            raise ValueError("post-battle attempt already consumed or not quoted")
        if not any(b.kind is kind for b in self._menu.bindings.bindings):
            raise ValueError("selected provider unavailable")
        self.authenticate()
        if self._configuration() != self._bound_configuration:
            raise ValueError("post-battle configuration changed after quote")
        if r.adapter.observe() != self._before or r.emulator.pressed_buttons:
            raise ValueError("quoted post-battle source changed")
        self._used = True  # Failed claims must not be silently retried in this instance.
        if self.claim(kind) is not True:
            raise ValueError("durable fresh attempt claim required before inputs")
        start_actions, start_frames = self.actions.actions_executed, r.emulator.frame_count
        limiter = HardCompositionActionLimiter(
            self.actions,
            maximum_actions_per_decision=self.limits.actions,
            maximum_episode_actions=self.limits.actions,
        )
        limited = CountingExecutor(limiter)
        start_seconds = r.emulator.elapsed_seconds
        error = None
        self._last_report = None
        try:
            with r.emulator.limit_additional_frames(self.limits.frames):
                r.emulator.check_wall_time_budget()
                if kind is GoalKind.DEVELOP_TEAM:
                    result = execute_wild_preparation(
                        rom=self.route.rom,
                        reader=r.reader,
                        actions=limited,
                        emulator=r.emulator,
                        battler=self.wild_battler,
                        adapter=r.adapter,
                        source_raw=self._before.raw,
                        plan=self.plan,
                        attempts=self.attempts,
                        record=self.record,
                        cost_snapshot=lambda: (
                            self.actions.actions_executed,
                            r.emulator.frame_count,
                        ),
                        hideout_timing=DEFAULT_HIDEOUT_TIMING,
                        route=self.route,
                        corridor=self.preparation_quote.corridor,
                        maximum_battles=self.limits.wild_battles,
                        minimum_ready_members=min(2, len(self._members)),
                        recovery_home_map=self.home,
                    )
                else:
                    # Reuse the original objective verifier; normalize only the
                    # declared settled loss, never arbitrary execution errors.
                    original = self.story_skill.actions
                    self.story_skill.actions = limited
                    try:
                        self._story_binding.execute()
                        result = {"status": "story_returned"}
                    except LoreleiStoryBattleStopped:
                        completion = r.league_story_battle_controller.last_completion
                        if (
                            completion is None
                            or completion.outcome != "lost"
                            or not completion.field_ready
                        ):
                            raise
                        result = {"status": "lost", "declared_outcome_stop": True}
                    finally:
                        self.story_skill.actions = original
            self._last_report = GoalExecutionReport(
                self.actions.actions_executed - start_actions,
                r.emulator.frame_count - start_frames,
                {"bounded": True, "kind": kind.value, **result},
            )
            return self._last_report
        except BaseException as caught:
            error = caught
            raise
        finally:
            try:
                self.record(
                    "post-battle-cost",
                    {
                        "kind": kind.value,
                        "actions": self.actions.actions_executed - start_actions,
                        "attempted_actions": limiter.attempted_actions,
                        "frames": r.emulator.frame_count - start_frames,
                        "seconds": r.emulator.elapsed_seconds - start_seconds,
                        "error_type": None if error is None else type(error).__name__,
                    },
                )
            finally:
                self.retain(kind, self._last_report, error)

    def _verify(self, kind, report):
        if not self._used or report is not getattr(self, "_last_report", None) or report is None:
            raise ValueError("verification requires this exact executed report")
        if report.evidence.get("kind") != kind.value:
            raise ValueError("report belongs to another selected goal")
        r = self.runtime
        after = r.adapter.observe()

        def failed():
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

        if (
            not after.input_ready
            or after.raw.battle_state
            or r.emulator.pressed_buttons
            or r.reader.read_all_box_states() != self._boxes
            or self._completed.difference(r.adapter.graph.completed_ids(after.game_state))
            or not self._before.collection_observation.owned_species.issubset(
                after.collection_observation.owned_species
            )
        ):
            return failed()
        if kind is GoalKind.ADVANCE_STORY:
            return (
                failed()
                if report.evidence.get("status") == "lost"
                else self._story_binding.verify(report)
            )
        live = observe_preparation_members(r.emulator, self.plan)
        old = {m.specimen_ref: m.observation for m in self._members}
        new = {m.specimen_ref: m.observation for m in live}
        if set(old) != set(new):
            return failed()
        for ref, previous in old.items():
            current = new[ref]
            if (
                current.experience is None
                or previous.experience is None
                or current.experience < previous.experience
                or current.level < previous.level
            ):
                return failed()
            if current.species_id != previous.species_id and not any(
                a == previous.species_id
                and b == current.species_id
                and previous.level < level <= current.level
                for a, b, level in self._evolution.level_edges
            ):
                return failed()
        reserve_gain = sum(
            new[ref].experience - old[ref].experience for ref, _ in self.plan.targets
        )
        if (
            reserve_gain <= 0
            or after.raw.player_money != self._before.raw.player_money
            or after.raw.bag_items != self._before.raw.bag_items
            or after.raw.map_id != self.home
            or not _raw_party_fully_restored(after.raw)
            or r.adapter.graph.completed_ids(after.game_state) != self._completed
        ):
            return failed()
        return GoalVerification.succeeded()
