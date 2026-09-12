"""Bounded execution of one qualified Red League funding attempt.

The action-free qualifier owns eligibility, route and payout discovery.  This
module consumes that exact qualification once, composes existing navigation,
Fly and cartridge battle skills, and stops at concurrent Champion/Hall-of-Fame
evidence.  Credits and the postgame reset are intentionally a separate boundary.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, NoReturn

from .actions import MacroAction, MacroActionKind
from .executor import CountingExecutor, FrameSafeExecutor, WindowedFrameBudgetController
from .gen1_field_moves import Gen1FieldMovePort, Gen1FlyReceipt
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_scripted_arrival import trainer_room_arrival
from .goal_manager_composition_qualification import HardCompositionActionLimiter
from .hideout import DEFAULT_HIDEOUT_TIMING
from .lavender import DEFAULT_LAVENDER_TIMING, _buy_mart_item, _close_menus
from .observation import RED_FLY_TOWN_NAMES, EventFlag, ItemId, MapId, event_flag_is_set
from .red_champion_story import RedCartridgeChampionSkill
from .red_dual_capability_curriculum_runtime import dependency_specimen_ledger
from .red_league_funding import (
    RedLeagueFundingQualification,
    qualify_red_league_funding,
)
from .red_pc_storage import face_pc_boundary
from .red_resource_goal_router import _ROUTE_LIMITS
from .red_trainer_story import RedCartridgeLoreleiSkill
from .referee import CompletionReferee
from .route_executor import execute_route
from .victory_road import _indigo_buy_entry_action, _pulse, _select_cursor, _sell_bag_stack

if TYPE_CHECKING:
    from .red_goal_context import RedGoalContextRuntime
    from .red_goal_manager import RedGoalObservation
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


@dataclass(slots=True)
class RedLeagueFundingExecutionBinding:
    """One action-free exact-origin binding for one claimed funding attempt."""

    origin: RedGoalObservation
    qualification: RedLeagueFundingQualification
    claimed: bool = False


def bind_red_league_funding_execution(
    runtime: RedGoalContextRuntime,
    world: StrategicScenarioRouteWorld,
    *,
    expected_qualification: RedLeagueFundingQualification | None = None,
) -> RedLeagueFundingExecutionBinding:
    """Bind the complete observed origin without advancing the emulator."""
    origin = runtime.adapter.observe()
    qualification = qualify_red_league_funding(world.rom, origin, runtime.reader, world)
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

    def execute(self, action: MacroAction) -> object:
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
            "learned_battle_authority": False,
            "forced_support_step": True,
            "training_examples": 0,
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
) -> RedLeagueFundingBattleResult:
    before_money = _money(runtime)
    before_actions = actions.actions_executed
    before_frames = runtime.emulator.frame_count
    before_restores = dict(runtime.adapter.observe().raw.bag_items or ()).get(
        int(ItemId.FULL_RESTORE), 0,
    )
    skill: RedCartridgeChampionSkill | RedCartridgeLoreleiSkill
    if objective_id == "defeat_champion":
        if maximum_critical_exposures:
            raise RedLeagueFundingExecutionError(
                "Champion battle does not support a critical-exposure budget"
            )
        skill = RedCartridgeChampionSkill(
            runtime,
            actions,
            world,
            recovery_controller=recovery_controller,
            maximum_full_restores=maximum_full_restores,
            rematch=True,
        )
    else:
        skill = RedCartridgeLoreleiSkill(
            runtime,
            actions,
            world,
            objective_id=objective_id,
            recovery_controller=recovery_controller,
            maximum_full_restores=maximum_full_restores,
            maximum_critical_exposures=maximum_critical_exposures,
            rematch=True,
        )
    availability = skill.availability(runtime.adapter.observe().game_state)
    if not availability.executable:
        raise RedLeagueFundingExecutionError(
            f"{objective_id} became unavailable: {availability.reason}"
        )
    report = skill.execute()
    after_money = _money(runtime)
    after_restores = dict(runtime.adapter.observe().raw.bag_items or ()).get(
        int(ItemId.FULL_RESTORE), 0,
    )
    spent = before_restores - after_restores
    critical_claimed = report.evidence.get("critical_exposures_claimed", 0)
    if (
        after_money - before_money != expected_money
        or report.actions_executed != actions.actions_executed - before_actions
        or report.frames_executed != runtime.emulator.frame_count - before_frames
        or not 0 <= spent <= maximum_full_restores
        or report.evidence.get("bag_items_spent") != spent
        or report.evidence.get("maximum_critical_exposures", 0)
        != maximum_critical_exposures
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
) -> RedLeagueFundingExecution:
    """Consume one exact qualification and stop at verified Hall-of-Fame evidence.

    The caller must own durable claim/checkpoint handling.  An exception may
    follow real partial gameplay and must never be handled by silently retrying
    this claimed attempt.
    """

    for name, value in (("maximum_actions", maximum_actions), ("maximum_frames", maximum_frames)):
        if type(value) is not int or value <= 0:  # noqa: E721
            raise ValueError(f"{name} must be a positive integer")
    if (
        not isinstance(actions.delegate, FrameSafeExecutor)
        or actions.delegate.controller is not runtime.emulator
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
    repeated = qualify_red_league_funding(world.rom, before, runtime.reader, world)
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
    starting_events = before.raw.event_flags
    starting_ledger = dependency_specimen_ledger(before.collection_observation)
    starting_frames = runtime.emulator.frame_count
    if before.raw.event_flags is None:
        raise RedLeagueFundingExecutionError("League funding lost its bound event flags")
    league_arrival = trainer_room_arrival(
        world.rom, int(MapId.LORELEIS_ROOM), before.raw.event_flags,
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
            FrameSafeExecutor(frame_limiter, actions.delegate.timing),
        ),
        maximum_actions_per_decision=maximum_actions,
        maximum_episode_actions=maximum_actions,
    )
    bounded_actions = CountingExecutor(limiter)
    results: list[RedLeagueFundingBattleResult] = []

    def fail(phase: str, reason: str, cause: BaseException | None = None) -> NoReturn:
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
            route = execute_route(
                qualification.exit_plan,
                bounded_actions,
                Gen1TraversalObserver(runtime.reader),
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
            or supply_boundary.raw.event_flags != starting_events
            or dependency_specimen_ledger(supply_boundary.collection_observation)
            != starting_ledger
        ):
            fail("supply_route", "League funding supply route changed its bound state")
        _execute_supply(runtime, bounded_actions, qualification)
        supplied = runtime.adapter.observe()
        if (
            supplied.raw.bag_items != _bag_after_supply(starting_bag, qualification)
            or supplied.raw.player_money
            != starting_money + qualification.supply.sale_proceeds
            - qualification.supply.purchase_cost
            or supplied.raw.party_species_ids != starting_party
            or supplied.raw.party_hp != starting_party_hp
            or supplied.raw.party_pp != starting_party_pp
            or supplied.raw.party_status != starting_party_status
            or supplied.raw.badge_bits != starting_badges
            or supplied.raw.event_flags != starting_events
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

    for quote in qualification.battles:
        try:
            results.append(
                _run_battle(
                    runtime,
                    bounded_actions,
                    world,
                    quote.objective_id,
                    quote.expected_money,
                    quote.recovery_controller,
                    quote.maximum_full_restores,
                    quote.maximum_critical_exposures,
                )
            )
        except Exception as error:
            fail("battle:" + quote.objective_id, quote.objective_id + " failed", error)
    try:
        after = runtime.adapter.observe()
        frames = runtime.emulator.frame_count - starting_frames
        ending_money = _money(runtime)
        if len(results) != 5:
            fail("terminal", "League funding terminal has an incomplete battle sequence")
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
        if restore_spent > sum(
            quote.maximum_full_restores for quote in qualification.battles
        ):
            fail("terminal", "League funding exceeded its campaign recovery budget")
        supplied_bag = _bag_after_supply(starting_bag, qualification)
        expected_bag = tuple(
            (item, remaining)
            for item, quantity in supplied_bag
            if (remaining := quantity - (
                restore_spent if item == int(ItemId.FULL_RESTORE) else 0
            )) > 0
        )
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
    "bind_red_league_funding_execution",
    "execute_red_league_funding",
]
