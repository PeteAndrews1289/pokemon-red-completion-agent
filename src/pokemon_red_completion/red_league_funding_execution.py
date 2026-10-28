"""Bounded execution of one qualified Red League funding attempt.

The action-free qualifier owns eligibility, route and payout discovery.  This
module consumes that exact qualification once, composes existing navigation,
Fly and cartridge battle skills, and stops at concurrent Champion/Hall-of-Fame
evidence.  Credits and the postgame reset are intentionally a separate boundary.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, NoReturn

from .actions import MacroAction, MacroActionKind
from .executor import CountingExecutor, FrameSafeExecutor, WindowedFrameBudgetController
from .gen1_field_moves import Gen1FieldMovePort, Gen1FlyReceipt
from .gen1_route_runtime import Gen1TraversalObserver, Gen1WildFleeHandler
from .gen1_scripted_arrival import trainer_room_arrival
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_composition_qualification import HardCompositionActionLimiter
from .goal_manager_runtime import ExecutableGoalBinding, GoalVerification
from .goal_resource_quote import GoalResourceQuote
from .hideout import DEFAULT_HIDEOUT_TIMING
from .lavender import DEFAULT_LAVENDER_TIMING, _buy_mart_item, _close_menus
from .observation import RED_FLY_TOWN_NAMES, EventFlag, ItemId, MapId, event_flag_is_set
from .red_champion_story import RedCartridgeChampionSkill
from .red_dual_capability_curriculum_runtime import dependency_specimen_ledger
from .red_faint_recovery import RedFaintAwareFieldRestoreGoalProvider
from .red_league_funding import (
    RedLeagueFundingQualification,
    projected_fresh_league_events,
    qualify_red_league_funding,
)
from .red_learned_league import learned_league_controller
from .red_pc_storage import face_pc_boundary
from .red_resource_goal_router import _ROUTE_LIMITS
from .red_trainer_story import RedCartridgeLoreleiSkill
from .referee import CompletionReferee
from .route_executor import execute_route
from .victory_road import _indigo_buy_entry_action, _pulse, _select_cursor, _sell_bag_stack

if TYPE_CHECKING:
    from .red_goal_context import RedGoalContextRuntime
    from .red_goal_manager import RedGoalObservation
    from .red_player_lesson_runtime import _RecordedActions
    from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


class RedLeagueFundingExecutionError(RuntimeError):
    """A claimed rematch left its qualified route, battle or accounting boundary."""

    def __init__(
        self,
        reason: str,
        *,
        progress: RedLeagueFundingProgress | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.progress = progress


class RedLeagueFundingBattleLoss(RuntimeError):
    """Exact settled native loss, never a completed income cycle."""

    def __init__(self, certificate):
        super().__init__("verified native League funding loss")
        self.certificate = certificate


def native_league_loss_certificate(runtime, before, completion, objective_id, *, prepared_party_species_ids=None):
    """Authenticate the existing learned battle result against the live blackout."""
    from hashlib import sha256
    if completion is None or completion.outcome != "lost" or not completion.field_ready:
        return None
    expected_party = (before.party_species_ids if prepared_party_species_ids is None
                      else prepared_party_species_ids)
    outcome = completion.public_dict()
    after = runtime.reader.read()
    if (
        outcome.get("schema") != "pokemon.red.learned-trainer-completion.v1"
        or outcome.get("outcome") != "lost" or outcome.get("field_ready") is not True
        or after.battle_state or not runtime.reader.read_input_readiness().ready
        or runtime.emulator.pressed_buttons
        or type(before.player_money) is not int or type(after.player_money) is not int
        or after.player_money != before.player_money // 2
        or outcome.get("money_delta") != after.player_money - before.player_money
        or not isinstance(before.party_species_ids, tuple) or not 1 <= len(before.party_species_ids) <= 6
        or type(before.badge_bits) is not int
        or after.party_species_ids != expected_party
        or after.badge_bits != before.badge_bits
    ):
        return None
    return dict(schema="pokemon.red.league-funding-native-loss.v1",objective_id=objective_id,
                money_before_battle=before.player_money,ending_money=after.player_money,
                completion=outcome,
                party_species_ids_before_preparation=list(before.party_species_ids),
                prepared_party_species_ids=list(expected_party),
                terminal_sha256=sha256(runtime.emulator.save_state_bytes()).hexdigest())


def run_retained_league_battle(runtime, call, *, battle_owner, objective_id):
    """Run the existing battle and certify only its settled native loss."""
    from .red_lorelei_story import LoreleiStoryBattleStopped
    battle_before = runtime.reader.read()
    # The selected story skill may first swap its planned lead in the field.
    # Authenticate that exact frozen plan before input; never infer a permitted
    # permutation from the terminal party after a failed battle.
    lead_plan = getattr(getattr(call, "__self__", None), "prepared_lead_plan", None)
    expected_party = battle_before.party_species_ids
    if lead_plan is not None:
        from .red_capture_lead import RedCaptureLeadPlan
        if not isinstance(lead_plan, RedCaptureLeadPlan):
            raise TypeError("funding battle requires a typed prepared lead")
        lead_plan.require_current(runtime.adapter.observe().party)
        if lead_plan.party.species_ids() != expected_party:
            raise ValueError("funding battle raw party differs from prepared lead")
        expected = list(expected_party)
        target = lead_plan.target_index
        expected[0], expected[target] = expected[target], expected[0]
        expected_party = tuple(expected)
    try:
        return call()
    except LoreleiStoryBattleStopped as error:
        certificate = native_league_loss_certificate(runtime, battle_before, getattr(battle_owner, 'last_completion', None), objective_id, prepared_party_species_ids=expected_party)
        if certificate is None:
            raise
        raise RedLeagueFundingBattleLoss(certificate) from error


@dataclass(slots=True)
class RedLeagueFundingExecutionBinding:
    """One action-free exact-origin binding for one claimed funding attempt."""

    origin: RedGoalObservation
    qualification: RedLeagueFundingQualification
    claimed: bool = False


@dataclass(frozen=True)
class ScopedLeagueIncomeReuse:
    """Explicit DEVELOPMENT reuse of the existing exact-room story controllers.

    The K adapter still authenticates the original route/payout qualification;
    this port binds the declared learned component to each actual battle. It
    cannot replace the reader, action controller, party guard or native target.
    """

    model_sha256: str
    work_order_sha256: str
    bind_runtime: Callable
    observe_battle: Callable | None = None

    def __post_init__(self):
        for value in (self.model_sha256, self.work_order_sha256):
            if (type(value) is not str or len(value) != 64
                    or any(c not in '0123456789abcdef' for c in value)):
                raise ValueError('Scoped income reuse requires exact model/work-order hashes')
        if not callable(self.bind_runtime) or (
            self.observe_battle is not None and not callable(self.observe_battle)
        ):
            raise ValueError('Scoped income reuse requires explicit binding/observation ports')

    def public_dict(self):
        return dict(model_sha256=self.model_sha256, work_order_sha256=self.work_order_sha256,
                    scope='existing-native-room-development', new_model=False)

    def bind(self, runtime, actions, world, objective_id):
        from .red_lorelei_story import (
            ScopedAssistedChampionController,
            ScopedAssistedLeagueRetryController,
        )

        before = runtime.emulator.save_state_bytes()
        configured = self.bind_runtime(runtime, actions, world, objective_id)
        owner = getattr(configured, 'league_story_battle_controller', None)
        owner_type = (ScopedAssistedChampionController if objective_id == 'defeat_champion'
                      else ScopedAssistedLeagueRetryController)
        scope = getattr(getattr(owner, 'battler', None), 'development_story_scope', None)
        if (
            type(owner) is not owner_type
            or configured.emulator is not runtime.emulator
            or configured.reader is not runtime.reader
            or configured.adapter is not runtime.adapter
            or getattr(configured, 'league_battle_controller', None) is not None
            or owner.contract.objective_id != objective_id
            or owner.battler.model_sha256 != self.model_sha256
            or getattr(scope, 'work_order_sha256', None) != self.work_order_sha256
            or getattr(configured.trainer_battle_runner, '__self__', None) is not owner.battler
            or runtime.emulator.save_state_bytes() != before
        ):
            raise ValueError('Income battle reuse changed its exact native actor/boundary')
        owner.require_objective(objective_id, rematch=True)
        return configured


def bind_red_league_funding_execution(
    runtime: RedGoalContextRuntime,
    world: StrategicScenarioRouteWorld,
    *,
    expected_qualification: RedLeagueFundingQualification | None = None,
) -> RedLeagueFundingExecutionBinding:
    """Bind the complete observed origin without advancing the emulator."""
    origin = runtime.adapter.observe()
    kwargs = {"learned_development": True} if learned_league_controller(runtime) else {}
    qualification = qualify_red_league_funding(world.rom, origin, runtime.reader, world, **kwargs)
    if expected_qualification is not None and qualification != expected_qualification:
        raise RedLeagueFundingExecutionError("League funding qualification changed while binding")
    return RedLeagueFundingExecutionBinding(origin, qualification)


@dataclass(frozen=True, slots=True)
class RedLeagueFundingBattleResult:
    objective_id: str
    money_before: int
    money_after: int
    expected_money: int
    actions: int
    frames: int
    full_restores_spent: int = 0
    critical_exposures_claimed: int = 0
    controller_name: str | None = None
    model_sha256: str | None = None

    def public_dict(self) -> dict[str, object]:
        return {
            "objective_id": self.objective_id,
            "money_before": self.money_before,
            "money_after": self.money_after,
            "expected_money": self.expected_money,
            "actions": self.actions,
            "frames": self.frames,
            "full_restores_spent": self.full_restores_spent,
            "critical_exposures_claimed": self.critical_exposures_claimed,
            **({"controller_name": self.controller_name, "model_sha256": self.model_sha256}
               if self.controller_name is not None else {}),
        }


@dataclass(frozen=True, slots=True)
class RedLeagueFundingProgress:
    phase: str
    starting_money: int
    observed_money: int
    actions_attempted: int
    frames: int
    completed_battles: tuple[RedLeagueFundingBattleResult, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.repeatable-league-funding-progress.v1",
            "phase": self.phase,
            "starting_money": self.starting_money,
            "observed_money": self.observed_money,
            "observed_cash_delta": self.observed_money - self.starting_money,
            "actions_attempted": self.actions_attempted,
            "frames": self.frames,
            "completed_battles": [battle.public_dict() for battle in self.completed_battles],
            "completed_battle_count": len(self.completed_battles),
            "training_examples": 0,
            "retry_authorized": False,
        }


@dataclass(slots=True)
class _CampaignActionCompiler:
    """Use the bounded controller while preserving the caller's completed count."""

    caller: CountingExecutor
    bounded: FrameSafeExecutor
    through_caller: bool = False
    recorded_caller: _RecordedActions | None = None

    def execute(self, action: MacroAction) -> object:
        if self.recorded_caller is not None:
            # Keep the native player's durable input journal and its input gate
            # while ALSO applying this selected League goal's frame window.
            # Only the exact typed recorder is admitted below; no arbitrary
            # delegate traversal or unrecorded controller bypass is permitted.
            recorder = self.recorded_caller
            original = recorder.delegate
            recorder.delegate = self.bounded
            try:
                return self.caller.execute(action)
            finally:
                recorder.delegate = original
        if self.through_caller:
            return self.caller.execute(action)
        result = self.bounded.execute(action)
        self.caller.actions_executed += 1
        return result


@dataclass(frozen=True, slots=True)
class RedLeagueFundingExecution:
    starting_money: int
    ending_money: int
    expected_gross_income: int
    actions: int
    frames: int
    exit_steps: int
    fly_destination: int
    battles: tuple[RedLeagueFundingBattleResult, ...]
    sale_proceeds: int
    purchase_cost: int
    full_restores_purchased: int
    full_restores_spent: int
    learned_battle_authority: bool = False
    field_items_spent: tuple[tuple[int, int], ...] = ()
    field_item_replacement_cost: int = 0

    @property
    def observed_gross_income(self) -> int:
        return sum(battle.money_after - battle.money_before for battle in self.battles)

    @property
    def observed_net_income(self) -> int:
        return self.ending_money - self.starting_money

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.repeatable-league-funding-execution.v2",
            "status": "hall_of_fame_verified_postgame_reset_pending",
            "starting_money": self.starting_money,
            "ending_money": self.ending_money,
            "expected_gross_income": self.expected_gross_income,
            "observed_gross_income": self.observed_gross_income,
            "observed_net_income": self.observed_net_income,
            "sale_proceeds": self.sale_proceeds,
            "purchase_cost": self.purchase_cost,
            "full_restores_purchased": self.full_restores_purchased,
            "full_restores_spent": self.full_restores_spent,
            "actions": self.actions,
            "frames": self.frames,
            "exit_steps": self.exit_steps,
            "fly_destination": self.fly_destination,
            "battles": [battle.public_dict() for battle in self.battles],
            "battle_count": len(self.battles),
            "learned_goal_authority": False,
            "learned_battle_authority": self.learned_battle_authority,
            "forced_support_step": True,
            "training_examples": 0,
            "field_items_spent": [list(row) for row in self.field_items_spent],
            "field_item_replacement_cost": self.field_item_replacement_cost,
            "net_after_field_item_replacement": (
                self.observed_net_income - self.field_item_replacement_cost
            ),
            "replacement_value_is_cash_spent": False,
            "concurrent_champion_and_hall_of_fame": True,
            "postgame_reset_proven": False,
            "capture_supply_restored": False,
        }


def _money(runtime: RedGoalContextRuntime) -> int:
    value = runtime.adapter.observe().raw.player_money
    if type(value) is not int or value < 0:  # noqa: E721
        raise RedLeagueFundingExecutionError("League funding lacks observed money")
    return value


def _progress(
    runtime: RedGoalContextRuntime,
    limiter: HardCompositionActionLimiter,
    *,
    phase: str,
    starting_money: int,
    starting_frames: int,
    battles: list[RedLeagueFundingBattleResult],
) -> RedLeagueFundingProgress:
    try:
        observed = runtime.reader.read().player_money
    except Exception:
        observed = None
    if type(observed) is not int or observed < 0:  # noqa: E721
        observed = battles[-1].money_after if battles else starting_money
    try:
        frame = runtime.emulator.frame_count
    except Exception:
        frame = None
    if type(frame) is not int or frame < starting_frames:  # noqa: E721
        frame = starting_frames
    return RedLeagueFundingProgress(
        phase,
        starting_money,
        observed,
        limiter.attempted_actions,
        frame - starting_frames,
        tuple(battles),
    )


def _run_battle(
    runtime: RedGoalContextRuntime,
    actions: CountingExecutor,
    world: StrategicScenarioRouteWorld,
    objective_id: str,
    expected_money: int,
    recovery_controller: str,
    maximum_full_restores: int,
    maximum_critical_exposures: int = 0,
    development_reuse: ScopedLeagueIncomeReuse | None = None,
) -> RedLeagueFundingBattleResult:
    before_money = _money(runtime)
    before_actions = actions.actions_executed
    before_frames = runtime.emulator.frame_count
    before_restores = dict(runtime.adapter.observe().raw.bag_items or ()).get(
        int(ItemId.FULL_RESTORE),
        0,
    )
    battle_owner = None
    def make_skill():
        nonlocal battle_owner
        configured = (runtime if development_reuse is None else
                      development_reuse.bind(runtime, actions, world, objective_id))
        battle_owner = getattr(configured, "league_story_battle_controller", None)
        mode = (recovery_controller if development_reuse is None else
                configured.league_story_battle_controller.controller_name)
        readiness = ({} if development_reuse is None else {
            'maximum_level_deficit': (
                configured.league_story_battle_controller.declared_level_deficit),
        })
        if objective_id == 'defeat_champion':
            return RedCartridgeChampionSkill(configured, actions, world,
                recovery_controller=mode, maximum_full_restores=maximum_full_restores,
                rematch=True, **readiness)
        return RedCartridgeLoreleiSkill(configured, actions, world,
            objective_id=objective_id, recovery_controller=mode,
            maximum_full_restores=maximum_full_restores,
            maximum_critical_exposures=maximum_critical_exposures, rematch=True, **readiness)

    def run_retained(call):
        def observe():
            if development_reuse is not None and development_reuse.observe_battle is not None:
                development_reuse.observe_battle(objective_id)
        try:
            report = run_retained_league_battle(
                runtime, call, battle_owner=battle_owner, objective_id=objective_id,
            )
        except BaseException as native_error:
            try:
                observe()
            except BaseException as observation_error:
                # An unfinished native battle has no completed outcome file.
                # Preserve its actual error (or certified loss) as the cause.
                native_error.add_note(
                    "Battle-history observation also failed: "
                    f"{type(observation_error).__name__}: {observation_error}"
                )
            raise
        observe()  # A successful battle still requires valid history evidence.
        return report

    if objective_id == "defeat_champion" and maximum_critical_exposures:
        raise RedLeagueFundingExecutionError(
            "Champion battle does not support a critical-exposure budget"
        )
    learned = learned_league_controller(runtime)
    field_recovery = learned.field_recovery if learned is not None else None
    if field_recovery is None:
        skill = make_skill()
        availability = skill.availability(runtime.adapter.observe().game_state)
        if not availability.executable:
            raise RedLeagueFundingExecutionError(
                f"{objective_id} became unavailable: {availability.reason}"
            )
        report = run_retained(skill.execute)
    else:

        def next_goal(observation):
            skill = make_skill()
            if not skill.availability(observation.game_state).executable:
                return None

            def verify(_report):
                after = runtime.adapter.observe()
                return (
                    GoalVerification.succeeded()
                    if after.raw.player_money == before_money + expected_money
                    and after.raw.battle_state == 0
                    else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
                )

            return ExecutableGoalBinding(
                binding_ref="pokemon.red:league-income:" + objective_id,
                kind=GoalKind.RESUPPLY,
                estimated_effort=0.5,
                estimated_risk=0.5,
                execute=skill.execute,
                verify=verify,
                resource_quote=GoalResourceQuote(
                    before_money, 0, (), expected_income=expected_money
                ),
            )

        recovery = RedFaintAwareFieldRestoreGoalProvider(
            actions,
            runtime.reader,
            runtime.emulator,
            runtime.adapter,
        )
        selected = field_recovery.choose(recovery, next_goal)
        # Battle accounting excludes separately recorded field recovery. Both still
        # consume the caller's same campaign action/frame limits.
        before_actions = actions.actions_executed
        before_frames = runtime.emulator.frame_count
        before_restores = dict(runtime.adapter.observe().raw.bag_items or ()).get(
            int(ItemId.FULL_RESTORE),
            0,
        )
        report = run_retained(selected.execute)
        if selected.verify(report).status.value != "succeeded":
            raise RedLeagueFundingExecutionError("selected next battle failed verification")
    after_money = _money(runtime)
    after_restores = dict(runtime.adapter.observe().raw.bag_items or ()).get(
        int(ItemId.FULL_RESTORE),
        0,
    )
    spent = before_restores - after_restores
    critical_claimed = report.evidence.get("critical_exposures_claimed", 0)
    if (
        after_money - before_money != expected_money
        or report.actions_executed != actions.actions_executed - before_actions
        or report.frames_executed != runtime.emulator.frame_count - before_frames
        or not 0 <= spent <= maximum_full_restores
        or report.evidence.get("bag_items_spent") != spent
        or report.evidence.get("maximum_critical_exposures", 0) != maximum_critical_exposures
        or type(critical_claimed) is not int
        or not 0 <= critical_claimed <= maximum_critical_exposures
    ):
        raise RedLeagueFundingExecutionError(
            f"{objective_id} payout or execution accounting differs"
        )
    return RedLeagueFundingBattleResult(
        objective_id,
        before_money,
        after_money,
        expected_money,
        report.actions_executed,
        report.frames_executed,
        spent,
        critical_claimed,
        (None if development_reuse is None else
         ('scoped-assisted-champion-development' if objective_id == 'defeat_champion'
          else 'scoped-assisted-league-retry-development')),
        None if development_reuse is None else development_reuse.model_sha256,
    )


def _bag_after_supply(
    starting: tuple[tuple[int, int], ...],
    qualification: RedLeagueFundingQualification,
) -> tuple[tuple[int, int], ...]:
    quantities = dict(starting)
    order = [item for item, _ in starting]
    for sale in qualification.supply.sales:
        quantities[int(sale.item)] -= sale.quantity
    restore = int(ItemId.FULL_RESTORE)
    if qualification.supply.full_restores_purchased:
        quantities[restore] = (
            quantities.get(restore, 0) + qualification.supply.full_restores_purchased
        )
        if restore not in order:
            order.append(restore)
    return tuple((item, quantities[item]) for item in order if quantities[item] > 0)


def _execute_supply(
    runtime: RedGoalContextRuntime,
    actions: CountingExecutor,
    qualification: RedLeagueFundingQualification,
) -> None:
    """Execute only the frozen Indigo sale and Full Restore purchase."""

    sales = qualification.supply.sales
    quantity = qualification.supply.full_restores_purchased
    if not sales and not quantity:
        return
    # The route binds the clerk-adjacent coordinate, not the player's facing.
    # Establish and verify the exact interaction direction before the first
    # irreversible sale input.
    face_pc_boundary(actions, runtime.reader, "left")
    for index, sale in enumerate(sales):
        _sell_bag_stack(
            actions,
            runtime.emulator,
            sale.item,
            sale.quantity,
        )
        if index + 1 < len(sales):
            _close_menus(actions, runtime.reader, DEFAULT_LAVENDER_TIMING)
    _pulse(actions, _indigo_buy_entry_action(1 if sales else 0))
    _select_cursor(actions, runtime.emulator, 0, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    if quantity:
        before = dict(runtime.reader.read().bag_items or ()).get(int(ItemId.FULL_RESTORE), 0)
        _buy_mart_item(
            actions,
            runtime.emulator,
            DEFAULT_LAVENDER_TIMING,
            absolute_index=2,
            item=ItemId.FULL_RESTORE,
            quantity=quantity,
            target_bag_quantity=before + quantity,
        )
    _close_menus(actions, runtime.reader, DEFAULT_LAVENDER_TIMING)


def execute_red_league_funding(
    runtime: RedGoalContextRuntime,
    actions: CountingExecutor,
    world: StrategicScenarioRouteWorld,
    binding: RedLeagueFundingExecutionBinding,
    *,
    maximum_actions: int = 40_000,
    maximum_frames: int = 15_000_000,
    development_reuse: ScopedLeagueIncomeReuse | None = None,
) -> RedLeagueFundingExecution:
    """Consume one exact qualification and stop at verified Hall-of-Fame evidence.

    The caller must own durable claim/checkpoint handling.  An exception may
    follow real partial gameplay and must never be handled by silently retrying
    this claimed attempt.
    """

    if development_reuse is not None and type(development_reuse) is not ScopedLeagueIncomeReuse:
        raise TypeError('Income reuse requires the explicit exact-room DEVELOPMENT port')
    for name, value in (("maximum_actions", maximum_actions), ("maximum_frames", maximum_frames)):
        if type(value) is not int or value <= 0:  # noqa: E721
            raise ValueError(f"{name} must be a positive integer")
    from .red_native_player import NativePlayerActions
    from .red_player_lesson_runtime import _RecordedActions

    delegate = actions.delegate
    recorded = isinstance(actions, NativePlayerActions) and isinstance(delegate, _RecordedActions)
    nested = isinstance(delegate, HardCompositionActionLimiter)
    frame_safe = delegate.delegate if recorded or nested else delegate
    if (
        not isinstance(frame_safe, FrameSafeExecutor)
        or frame_safe.controller is not runtime.emulator
        or (recorded and delegate.controller is not runtime.emulator)
    ):
        raise TypeError("League funding requires one direct frame-safe controller chain")
    if not isinstance(binding, RedLeagueFundingExecutionBinding):
        raise TypeError("League funding requires an exact execution binding")
    if binding.claimed:
        raise RedLeagueFundingExecutionError("League funding execution binding is already claimed")
    binding.claimed = True
    qualification = binding.qualification
    before = runtime.adapter.observe()
    if before != binding.origin:
        raise RedLeagueFundingExecutionError("League funding exact origin changed before input")
    learned = learned_league_controller(runtime)
    if development_reuse is not None and learned is None:
        raise ValueError('Scoped income reuse requires the existing learned route qualification')
    field_recovery = learned.field_recovery if learned is not None else None
    if field_recovery is not None:
        field_recovery.claim()
    kwargs = {"learned_development": True} if learned else {}
    repeated = qualify_red_league_funding(world.rom, before, runtime.reader, world, **kwargs)
    if repeated != qualification:
        raise RedLeagueFundingExecutionError("League funding qualification changed before input")
    if runtime.emulator.pressed_buttons:
        raise RedLeagueFundingExecutionError("League funding starts with pressed controls")
    starting_money = _money(runtime)
    starting_bag = before.raw.bag_items
    if starting_bag is None:
        raise RedLeagueFundingExecutionError("League funding lacks its bound bag")
    starting_badges = before.raw.badge_bits
    starting_party = before.raw.party_species_ids
    starting_party_hp = before.raw.party_hp
    starting_party_pp = before.raw.party_pp
    starting_party_status = before.raw.party_status
    starting_ledger = dependency_specimen_ledger(before.collection_observation)
    starting_frames = runtime.emulator.frame_count
    if before.raw.event_flags is None:
        raise RedLeagueFundingExecutionError("League funding lost its bound event flags")
    expected_supply_events = before.raw.event_flags
    if qualification.reset_stale_league_events:
        expected_supply_events, reset_required = projected_fresh_league_events(
            before.raw.event_flags,
            challenge_started=runtime.reader.read_league_challenge_started() if learned else None,
        )
        if not reset_required:
            raise RedLeagueFundingExecutionError(
                "League funding lost its bound pre-entry event reset"
            )
    league_arrival = trainer_room_arrival(
        world.rom,
        int(MapId.LORELEIS_ROOM),
        expected_supply_events,
    )
    entry_limits = replace(
        _ROUTE_LIMITS,
        transition_settle_frames=max(
            _ROUTE_LIMITS.transition_settle_frames,
            league_arrival.steps * 24 + 120,
        ),
    )

    frame_limiter = WindowedFrameBudgetController(
        runtime.emulator,
        maximum_frames_per_window=maximum_frames,
        maximum_total_frames=maximum_frames,
    )
    limiter = HardCompositionActionLimiter(
        _CampaignActionCompiler(
            actions,
            FrameSafeExecutor(frame_limiter, frame_safe.timing),
            through_caller=nested or recorded,
            recorded_caller=delegate if recorded else None,
        ),
        maximum_actions_per_decision=maximum_actions,
        maximum_episode_actions=maximum_actions,
    )
    bounded_actions = CountingExecutor(limiter)
    results: list[RedLeagueFundingBattleResult] = []

    def fail(phase: str, reason: str, cause: BaseException | None = None) -> NoReturn:
        if field_recovery is not None and not isinstance(cause, RedLeagueFundingBattleLoss):
            field_recovery.failed = True
        error = RedLeagueFundingExecutionError(
            reason,
            progress=_progress(
                runtime,
                limiter,
                phase=phase,
                starting_money=starting_money,
                starting_frames=starting_frames,
                battles=results,
            ),
        )
        if cause is None:
            raise error
        raise error from cause

    try:
        if qualification.exit_plan is not None:
            # Indoor departures can cross real encounter tiles. Escaping is
            # transport support, not an income battle or a replacement goal.
            # Any HP/PP/resource change still fails the existing supply-boundary
            # checks below; no payout or qualification is fabricated.
            escape = Gen1WildFleeHandler(
                bounded_actions, runtime.reader, maximum_flees=16,
                stabilization_frames=120, route_name="League income indoor departure",
            )
            route = execute_route(
                qualification.exit_plan,
                bounded_actions,
                Gen1TraversalObserver(runtime.reader),
                interruption_handler=escape,
                replanner=world.replanner(),
            )
            if not route.passed:
                fail("center_exit", "League funding exit route failed")
    except RedLeagueFundingExecutionError as error:
        if error.progress is not None:
            raise
        fail("center_exit", error.reason, error)
    except Exception as error:
        fail("center_exit", "League funding exit route raised", error)
    try:
        if qualification.fly_required:
            port = Gen1FieldMovePort(bounded_actions, runtime.reader, runtime.emulator)
            town = RED_FLY_TOWN_NAMES[qualification.fly_town].lower().replace(" ", "_")
            receipt = port.execute(MacroAction(MacroActionKind.FIELD_MOVE, "fly:" + town))
            landed = runtime.reader.read()
            if (
                not isinstance(receipt, Gen1FlyReceipt)
                or receipt.destination_map != qualification.fly_town
                or (landed.player_y, landed.player_x) != qualification.fly_landing
            ):
                fail("fly", "League funding Fly landing changed")
        else:
            walking_origin = runtime.adapter.observe()
            if (
                walking_origin.raw.map_id != qualification.fly_town
                or (walking_origin.raw.player_y, walking_origin.raw.player_x)
                != qualification.fly_landing
                or walking_origin.raw.battle_state
                or not walking_origin.input_ready
            ):
                fail("fly", "League funding already-at-Indigo walking origin changed")
    except RedLeagueFundingExecutionError as error:
        if error.progress is not None:
            raise
        fail("fly", error.reason, error)
    except Exception as error:
        fail("fly", "League funding Fly raised", error)
    try:
        supply_route = execute_route(
            qualification.supply.route,
            bounded_actions,
            Gen1TraversalObserver(runtime.reader),
            replanner=world.replanner(),
        )
        if not supply_route.passed:
            fail("supply_route", "League funding supply route failed")
        supply_boundary = runtime.adapter.observe()
        if (
            supply_boundary.raw.map_id != MapId.INDIGO_PLATEAU_LOBBY
            or (supply_boundary.raw.player_y, supply_boundary.raw.player_x) != (5, 2)
            or supply_boundary.raw.battle_state
            or not supply_boundary.input_ready
            or supply_boundary.raw.player_money != starting_money
            or supply_boundary.raw.bag_items != starting_bag
            or supply_boundary.raw.party_species_ids != starting_party
            or supply_boundary.raw.party_hp != starting_party_hp
            or supply_boundary.raw.party_pp != starting_party_pp
            or supply_boundary.raw.party_status != starting_party_status
            or supply_boundary.raw.badge_bits != starting_badges
            or supply_boundary.raw.event_flags != expected_supply_events
            or dependency_specimen_ledger(supply_boundary.collection_observation) != starting_ledger
        ):
            fail("supply_route", "League funding supply route changed its bound state")
        _execute_supply(runtime, bounded_actions, qualification)
        supplied = runtime.adapter.observe()
        if (
            supplied.raw.bag_items != _bag_after_supply(starting_bag, qualification)
            or supplied.raw.player_money
            != starting_money
            + qualification.supply.sale_proceeds
            - qualification.supply.purchase_cost
            or supplied.raw.party_species_ids != starting_party
            or supplied.raw.party_hp != starting_party_hp
            or supplied.raw.party_pp != starting_party_pp
            or supplied.raw.party_status != starting_party_status
            or supplied.raw.badge_bits != starting_badges
            or supplied.raw.event_flags != expected_supply_events
            or dependency_specimen_ledger(supplied.collection_observation) != starting_ledger
        ):
            fail("supply", "League funding supply accounting changed")
    except RedLeagueFundingExecutionError as error:
        if error.progress is not None:
            raise
        fail("supply", error.reason, error)
    except Exception as error:
        fail("supply", "League funding supply raised", error)
    try:
        entry = execute_route(
            qualification.entry_plan,
            bounded_actions,
            Gen1TraversalObserver(runtime.reader),
            limits=entry_limits,
            replanner=world.replanner(),
        )
        if not entry.passed:
            fail("league_entry", "League funding entry route failed")
    except RedLeagueFundingExecutionError as error:
        if error.progress is not None:
            raise
        fail("league_entry", error.reason, error)
    except Exception as error:
        fail("league_entry", "League funding entry route raised", error)

    remaining_full_restores = qualification.maximum_campaign_full_restores
    for quote in qualification.battles:
        try:
            battle_restore_budget = min(
                quote.maximum_full_restores,
                remaining_full_restores,
            )
            recovery_controller = quote.recovery_controller
            if recovery_controller == "ordinary-bounded-healing" and not battle_restore_budget:
                recovery_controller = "damage-bounded-zero-item"
            results.append(
                _run_battle(
                    runtime,
                    bounded_actions,
                    world,
                    quote.objective_id,
                    quote.expected_money,
                    recovery_controller,
                    battle_restore_budget,
                    quote.maximum_critical_exposures,
                    **({'development_reuse': development_reuse}
                       if development_reuse is not None else {}),
                )
            )
            remaining_full_restores -= results[-1].full_restores_spent
        except Exception as error:
            fail("battle:" + quote.objective_id, quote.objective_id + " failed", error)
    try:
        after = runtime.adapter.observe()
        frames = runtime.emulator.frame_count - starting_frames
        ending_money = _money(runtime)
        if len(results) != 5:
            fail("terminal", "League funding terminal has an incomplete battle sequence")
        if after.raw.map_id != MapId.HALL_OF_FAME:
            fail("terminal", "League funding terminal lacks current-cycle Hall-of-Fame arrival")
        if not CompletionReferee().inspect(after.game_state).complete:
            fail("terminal", "League funding terminal lacks concurrent completion")
        if after.raw.event_flags is None or not all(
            event_flag_is_set(after.raw.event_flags, flag)
            for flag in (
                EventFlag.BEAT_LORELEI,
                EventFlag.BEAT_BRUNO,
                EventFlag.BEAT_AGATHA,
                EventFlag.BEAT_LANCES_ROOM_TRAINER,
                EventFlag.BEAT_LANCE,
                EventFlag.BEAT_CHAMPION_RIVAL,
            )
        ):
            fail("terminal", "League funding terminal lacks current-cycle cartridge events")
        if runtime.emulator.pressed_buttons:
            fail("terminal", "League funding terminal retained pressed controls")
        restore_spent = sum(result.full_restores_spent for result in results)
        if restore_spent > qualification.maximum_campaign_full_restores:
            fail("terminal", "League funding exceeded its campaign recovery budget")
        supplied_bag = _bag_after_supply(starting_bag, qualification)
        expected_bag = tuple(
            (item, remaining)
            for item, quantity in supplied_bag
            if (remaining := quantity - (restore_spent if item == int(ItemId.FULL_RESTORE) else 0))
            > 0
        )
        if field_recovery is not None:
            expected_bag = field_recovery.expected_bag(supplied_bag, restore_spent)
        if after.raw.bag_items != expected_bag:
            fail("terminal", "League funding terminal bag differs from supplied use")
        if after.raw.badge_bits != starting_badges:
            fail("terminal", "League funding terminal changed badges")
        if Counter(after.raw.party_species_ids or ()) != Counter(starting_party or ()):
            fail("terminal", "League funding terminal changed party membership")
        if dependency_specimen_ledger(after.collection_observation) != starting_ledger:
            fail("terminal", "League funding terminal changed the specimen ledger")
        if ending_money != starting_money + qualification.expected_net_income:
            fail("terminal", "League funding terminal money differs from quoted net")
        if frames > maximum_frames:
            fail("terminal", "League funding terminal exceeded its frame bound")
        return RedLeagueFundingExecution(
            starting_money,
            ending_money,
            qualification.expected_gross_income,
            bounded_actions.actions_executed,
            frames,
            0 if qualification.exit_plan is None else len(qualification.exit_plan.steps),
            qualification.fly_town,
            tuple(results),
            qualification.supply.sale_proceeds,
            qualification.supply.purchase_cost,
            qualification.supply.full_restores_purchased,
            restore_spent,
            learned is not None,
            tuple(sorted(field_recovery.consumed.items())) if field_recovery else (),
            field_recovery.replacement_cost if field_recovery else 0,
        )
    except RedLeagueFundingExecutionError as error:
        if error.progress is not None:
            raise
        fail("terminal", error.reason, error)
    except Exception as error:
        fail("terminal", "League funding terminal observation failed", error)


__all__ = [
    "RedLeagueFundingExecutionBinding",
    "RedLeagueFundingBattleResult",
    "RedLeagueFundingExecution",
    "RedLeagueFundingExecutionError",
    "RedLeagueFundingProgress",
    "ScopedLeagueIncomeReuse",
    "bind_red_league_funding_execution",
    "execute_red_league_funding",
]
