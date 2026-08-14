"""Reusable bounded Red skills exposed to the portable goal manager.

The manager sees only semantic goal kinds and normalized cost.  This module
keeps cartridge-specific controller bindings on the executor side, observes a
fresh post-action state, and turns that independent observation into the only
success label that may enter a goal-manager episode.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.domain import GameMode
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.field_recovery import (
    FieldRecoveryError,
    plan_party_recovery,
    use_field_recovery_item,
)
from pokemon_red_completion.goal_manager import (
    GoalFailureReason,
    GoalKind,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.goal_manager_state import headroom_satisfaction
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    _buy_mart_item,
    _close_menus,
)
from pokemon_red_completion.observation import (
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.red_acquisition import (
    RED_ACQUISITION_CATALOG,
    RedAcquisitionCatalog,
    RedAreaExecutionPolicy,
    RedAreaExecutor,
    run_red_area_survey,
    summarize_red_area_survey,
)
from pokemon_red_completion.red_goal_manager import (
    PokemonRedGoalStateAdapter,
    RedGoalBindingOffer,
    RedGoalObservation,
)
from pokemon_red_completion.red_pc_storage import open_bills_pc, switch_box
from pokemon_red_completion.route_executor import (
    DEFAULT_ROUTE_EXECUTION_LIMITS,
    InterruptionHandler,
    RouteExecutionLimits,
    RouteReplanner,
    RouteResourceManager,
    TraversalObserver,
    execute_route,
)
from pokemon_red_completion.route_plan import RoutePlan


class RedGoalSkillError(RuntimeError):
    """Raised when a Red skill cannot preserve its declared boundary."""


class RedGoalSkillEmulator(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


@dataclass(frozen=True, slots=True)
class RedGoalSkillAvailability:
    """One truthful availability verdict for a bounded cartridge skill."""

    executable: bool
    unavailable_reason: GoalUnavailableReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.executable, bool):
            raise TypeError("goal skill availability must be a boolean")
        if self.executable:
            if self.unavailable_reason is not None:
                raise RedGoalSkillError("an executable goal skill cannot have a block reason")
        elif not isinstance(self.unavailable_reason, GoalUnavailableReason):
            raise RedGoalSkillError("a blocked goal skill needs a portable reason")

    @classmethod
    def available(cls) -> RedGoalSkillAvailability:
        return cls(True)

    @classmethod
    def unavailable(
        cls,
        reason: GoalUnavailableReason,
    ) -> RedGoalSkillAvailability:
        return cls(False, reason)


GoalAvailabilityCheck = Callable[[RedGoalObservation], RedGoalSkillAvailability]
GoalSkillExecutor = Callable[[], GoalExecutionReport]
GoalSkillVerifier = Callable[
    [RedGoalObservation, RedGoalObservation, GoalExecutionReport],
    GoalVerification,
]


_PROGRESS_FIELD = {
    GoalKind.DEVELOP_TEAM: "team_readiness",
    GoalKind.EVOLVE_SPECIES: "evolution",
    GoalKind.RESTORE_TEAM: "safety",
    GoalKind.RESUPPLY: "resources",
    GoalKind.EXPLORE: "world_knowledge",
}


@dataclass(frozen=True, slots=True)
class RedObservedGoalSkillProvider:
    """Bind any existing Red mechanic behind one fresh-state verifier."""

    kind: GoalKind
    binding_ref: str
    adapter: PokemonRedGoalStateAdapter
    availability: GoalAvailabilityCheck
    executor: GoalSkillExecutor
    verifier: GoalSkillVerifier
    estimated_effort: float
    estimated_risk: float

    def __post_init__(self) -> None:
        if not isinstance(self.kind, GoalKind):
            raise RedGoalSkillError("observed goal skill kind is invalid")
        if not isinstance(self.binding_ref, str) or not self.binding_ref:
            raise RedGoalSkillError("observed goal skill binding is absent")
        for name in ("availability", "executor", "verifier"):
            if not callable(getattr(self, name)):
                raise RedGoalSkillError(f"observed goal skill {name} must be callable")

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        availability = self.availability(observation)
        if not isinstance(availability, RedGoalSkillAvailability):
            raise RedGoalSkillError("goal skill returned an invalid availability verdict")
        if not availability.executable:
            assert availability.unavailable_reason is not None
            return RedGoalBindingOffer.unavailable(
                self.kind,
                availability.unavailable_reason,
            )
        before = observation

        def verify(report: GoalExecutionReport) -> GoalVerification:
            after = self.adapter.observe()
            result = self.verifier(before, after, report)
            if not isinstance(result, GoalVerification):
                raise RedGoalSkillError("goal skill verifier returned an invalid verdict")
            return result

        return RedGoalBindingOffer.available(
            ExecutableGoalBinding(
                binding_ref=self.binding_ref,
                kind=self.kind,
                estimated_effort=self.estimated_effort,
                estimated_risk=self.estimated_risk,
                execute=self.executor,
                verify=verify,
            )
        )


@dataclass(frozen=True, slots=True)
class RedProgressGoalProvider:
    """Wrap a bounded mechanic that must improve one independently read need."""

    kind: GoalKind
    binding_ref: str
    adapter: PokemonRedGoalStateAdapter
    boundary: GoalAvailabilityCheck
    executor: GoalSkillExecutor
    estimated_effort: float
    estimated_risk: float

    def __post_init__(self) -> None:
        if self.kind not in _PROGRESS_FIELD:
            raise RedGoalSkillError("progress provider received an unsupported goal kind")
        if not isinstance(self.binding_ref, str) or not self.binding_ref:
            raise RedGoalSkillError("progress provider binding identity is absent")
        if not callable(self.boundary) or not callable(self.executor):
            raise RedGoalSkillError("progress provider callbacks must be callable")

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        if observation.raw.battle_state or not observation.input_ready:
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.TEMPORARILY_BLOCKED,
            )
        boundary = self.boundary(observation)
        if not isinstance(boundary, RedGoalSkillAvailability):
            raise RedGoalSkillError("progress provider returned invalid boundary evidence")
        if not boundary.executable:
            assert boundary.unavailable_reason is not None
            return RedGoalBindingOffer.unavailable(self.kind, boundary.unavailable_reason)
        before_progress = _goal_progress(observation, self.kind)
        if before_progress >= 1.0:
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.NO_LEGAL_TARGET,
            )
        before_story = self.adapter.graph.completed_ids(observation.game_state)
        before_party = observation.party.species_ids()
        before_owned = observation.collection.collection.pokedex_owned_count
        before_living = observation.collection.collection.living_count

        def verify(report: GoalExecutionReport) -> GoalVerification:
            after = self.adapter.observe()
            after_story = self.adapter.graph.completed_ids(after.game_state)
            if before_story.difference(after_story):
                return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            if (
                after.collection.collection.pokedex_owned_count < before_owned
                or after.collection.collection.living_count < before_living
            ):
                return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            if self.kind is not GoalKind.EVOLVE_SPECIES:
                if before_party != after.party.species_ids():
                    return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            elif observation.party.size != after.party.size:
                return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            if (
                report.actions_executed <= 0
                or after.raw.battle_state
                or not after.input_ready
                or _goal_progress(after, self.kind) <= before_progress
            ):
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            if self.kind is GoalKind.DEVELOP_TEAM and after.party.fainted_count:
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            return GoalVerification.succeeded()

        return RedGoalBindingOffer.available(
            ExecutableGoalBinding(
                binding_ref=self.binding_ref,
                kind=self.kind,
                estimated_effort=self.estimated_effort,
                estimated_risk=self.estimated_risk,
                execute=self.executor,
                verify=verify,
            )
        )


@dataclass(frozen=True, slots=True)
class RedFieldRestoreGoalProvider:
    """Recover damaged, living party members with observed field items."""

    actions: CountingExecutor
    reader: PokemonRedStateReader
    emulator: RedGoalSkillEmulator
    adapter: PokemonRedGoalStateAdapter
    kind: GoalKind = GoalKind.RESTORE_TEAM

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        plan, unavailable = self._plan(observation)
        if unavailable is not None:
            return RedGoalBindingOffer.unavailable(self.kind, unavailable)
        assert plan
        before_actions = self.actions.actions_executed
        before_frames = self.emulator.frame_count

        def execute() -> GoalExecutionReport:
            for party_index, item in plan:
                use_field_recovery_item(
                    self.actions,
                    self.reader,
                    self.emulator,
                    party_index,
                    item,
                )
            return GoalExecutionReport(
                actions_executed=self.actions.actions_executed - before_actions,
                frames_executed=self.emulator.frame_count - before_frames,
                evidence={
                    "bounded": True,
                    "planned_recoveries": len(plan),
                },
            )

        before_story = self.adapter.graph.completed_ids(observation.game_state)
        before_inventory = dict(observation.raw.bag_items or ())

        def verify(report: GoalExecutionReport) -> GoalVerification:
            after = self.adapter.observe()
            after_story = self.adapter.graph.completed_ids(after.game_state)
            if before_story.difference(after_story):
                return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            if observation.party.species_ids() != after.party.species_ids():
                return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            after_inventory = dict(after.raw.bag_items or ())
            used = Counter(item for _, item in plan)
            if any(
                after_inventory.get(int(item), 0) != before_inventory.get(int(item), 0) - quantity
                for item, quantity in used.items()
            ):
                return GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
            for party_index, _item in plan:
                member = after.party.members[party_index]
                if member.hp != member.max_hp or member.status.value != "healthy":
                    return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            if report.actions_executed <= 0 or not after.input_ready:
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            return GoalVerification.succeeded()

        return RedGoalBindingOffer.available(
            ExecutableGoalBinding(
                binding_ref="pokemon.red:recovery:field-items",
                kind=self.kind,
                estimated_effort=min(1.0, 0.08 * len(plan)),
                estimated_risk=0.03,
                execute=execute,
                verify=verify,
            )
        )

    @staticmethod
    def _plan(
        observation: RedGoalObservation,
    ) -> tuple[
        tuple[tuple[int, ItemId], ...],
        GoalUnavailableReason | None,
    ]:
        raw = observation.raw
        if raw.battle_state or not observation.input_ready:
            return (), GoalUnavailableReason.TEMPORARILY_BLOCKED
        hp = tuple(raw.party_hp or ())
        maximum = tuple(raw.party_max_hp or ())
        status = tuple(raw.party_status or ())
        if any(value <= 0 for value in hp):
            return (), GoalUnavailableReason.MISSING_CAPABILITY
        try:
            plan = plan_party_recovery(hp, maximum, status)
        except FieldRecoveryError:
            return (), GoalUnavailableReason.WORLD_STATE_UNKNOWN
        if not plan:
            return (), GoalUnavailableReason.NO_LEGAL_TARGET
        inventory = dict(raw.bag_items or ())
        required = Counter(item for _, item in plan)
        if any(inventory.get(int(item), 0) < quantity for item, quantity in required.items()):
            return (), GoalUnavailableReason.MISSING_RESOURCE
        return plan, None


_POKEMON_CENTER_MAPS = frozenset(
    {
        MapId.VIRIDIAN_POKECENTER,
        MapId.PEWTER_POKECENTER,
        MapId.CERULEAN_POKECENTER,
        MapId.MT_MOON_POKECENTER,
        MapId.VERMILION_POKECENTER,
        MapId.ROCK_TUNNEL_POKECENTER,
        MapId.LAVENDER_POKECENTER,
        MapId.FUCHSIA_POKECENTER,
        MapId.CELADON_POKECENTER,
        MapId.SAFFRON_POKECENTER,
        MapId.CINNABAR_POKECENTER,
    }
)


_CAPTURE_ITEMS = frozenset(
    {
        ItemId.POKE_BALL,
        ItemId.GREAT_BALL,
        ItemId.ULTRA_BALL,
        ItemId.MASTER_BALL,
    }
)
_ORDINARY_CAPTURE_ITEMS = frozenset(
    {
        ItemId.POKE_BALL,
        ItemId.GREAT_BALL,
        ItemId.ULTRA_BALL,
    }
)
_RECOVERY_ITEMS = frozenset(
    {
        ItemId.POTION,
        ItemId.SUPER_POTION,
        ItemId.HYPER_POTION,
        ItemId.FULL_RESTORE,
        ItemId.ANTIDOTE,
        ItemId.AWAKENING,
        ItemId.PARLYZ_HEAL,
        ItemId.FULL_HEAL,
        ItemId.REVIVE,
    }
)


@dataclass(frozen=True, slots=True)
class RedMartPurchase:
    """One exact, source-known entry in a Generation-I Mart inventory."""

    absolute_index: int
    item: ItemId
    quantity: int
    unit_price: int

    def __post_init__(self) -> None:
        if type(self.absolute_index) is not int or self.absolute_index < 0:  # noqa: E721
            raise ValueError("Mart inventory index must be a non-negative integer")
        if not isinstance(self.item, ItemId):
            raise TypeError("Mart purchase item must be an ItemId")
        for name in ("quantity", "unit_price"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:  # noqa: E721
                raise ValueError(f"Mart purchase {name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class RedMartResupplyGoalProvider:
    """Buy an exact ball-and-recovery reserve from a verified clerk stance."""

    map_id: MapId
    player_x: int
    player_y: int
    interaction_direction: str
    purchases: tuple[RedMartPurchase, ...]
    actions: CountingExecutor
    reader: PokemonRedStateReader
    emulator: RedGoalSkillEmulator
    adapter: PokemonRedGoalStateAdapter
    wait_frames: int = DEFAULT_LAVENDER_TIMING.wait_frames
    kind: GoalKind = GoalKind.RESUPPLY

    def __post_init__(self) -> None:
        if not isinstance(self.map_id, MapId):
            raise TypeError("Mart boundary map must be a MapId")
        for name in ("player_x", "player_y"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:  # noqa: E721
                raise ValueError(f"Mart boundary {name} must be non-negative")
        if self.interaction_direction not in {"up", "right", "down", "left"}:
            raise ValueError("Mart interaction direction is invalid")
        if not self.purchases:
            raise ValueError("Mart resupply needs at least one purchase")
        if len({purchase.item for purchase in self.purchases}) != len(self.purchases):
            raise ValueError("Mart resupply cannot purchase an item twice")
        if type(self.wait_frames) is not int or self.wait_frames <= 0:  # noqa: E721
            raise ValueError("Mart wait_frames must be a positive integer")

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        start = observation.raw
        projected_capture, projected_recovery = self._projected_resources(observation)

        def boundary(current: RedGoalObservation) -> RedGoalSkillAvailability:
            raw = current.raw
            if (
                raw.map_id != self.map_id
                or raw.player_x != self.player_x
                or raw.player_y != self.player_y
            ):
                return RedGoalSkillAvailability.unavailable(
                    GoalUnavailableReason.MISSING_CAPABILITY
                )
            inventory = dict(raw.bag_items or ())
            new_slots = sum(purchase.item not in inventory for purchase in self.purchases)
            if len(inventory) + new_slots > 20:
                return RedGoalSkillAvailability.unavailable(
                    GoalUnavailableReason.MISSING_CAPABILITY
                )
            cost = sum(purchase.quantity * purchase.unit_price for purchase in self.purchases)
            if raw.player_money is None or raw.player_money < cost:
                return RedGoalSkillAvailability.unavailable(GoalUnavailableReason.MISSING_RESOURCE)
            projected = min(
                headroom_satisfaction(
                    projected_capture,
                    self.adapter.config.desired_capture_items,
                    subject="capture item",
                ),
                headroom_satisfaction(
                    projected_recovery,
                    self.adapter.config.desired_recovery_items,
                    subject="recovery item",
                ),
            )
            if projected <= current.evidence.resources:
                return RedGoalSkillAvailability.unavailable(GoalUnavailableReason.NO_LEGAL_TARGET)
            return RedGoalSkillAvailability.available()

        before_actions = self.actions.actions_executed
        before_frames = self.emulator.frame_count
        before_inventory = dict(start.bag_items or ())
        before_money = start.player_money
        total_cost = sum(purchase.quantity * purchase.unit_price for purchase in self.purchases)

        def execute() -> GoalExecutionReport:
            if before_money is None:
                raise RedGoalSkillError("Mart resupply lacks money evidence")
            self.actions.execute(MacroAction(MacroActionKind.MOVE, self.interaction_direction))
            self._settle()
            approached = self.reader.read()
            if (
                approached.map_id != self.map_id
                or approached.player_x != self.player_x
                or approached.player_y != self.player_y
                or approached.battle_state
            ):
                raise RedGoalSkillError("Mart clerk interaction moved off its boundary")
            self._open_buy_list()
            for purchase in self.purchases:
                target = before_inventory.get(int(purchase.item), 0) + purchase.quantity
                _buy_mart_item(
                    self.actions,
                    self.emulator,
                    DEFAULT_LAVENDER_TIMING,
                    absolute_index=purchase.absolute_index,
                    item=int(purchase.item),
                    quantity=purchase.quantity,
                    target_bag_quantity=target,
                )
            _close_menus(self.actions, self.reader, DEFAULT_LAVENDER_TIMING)
            after = self.reader.read()
            after_inventory = dict(after.bag_items or ())
            expected_inventory = dict(before_inventory)
            for purchase in self.purchases:
                expected_inventory[int(purchase.item)] = (
                    expected_inventory.get(int(purchase.item), 0) + purchase.quantity
                )
            if (
                after.map_id != self.map_id
                or after.player_x != self.player_x
                or after.player_y != self.player_y
                or after.battle_state
                or after_inventory != expected_inventory
                or after.player_money != before_money - total_cost
                or not self.reader.read_input_readiness().ready
            ):
                raise RedGoalSkillError("Mart resupply failed its inventory/economy proof")
            return GoalExecutionReport(
                actions_executed=self.actions.actions_executed - before_actions,
                frames_executed=self.emulator.frame_count - before_frames,
                evidence={
                    "bounded": True,
                    "purchase_count": len(self.purchases),
                    "quantity_purchased": sum(purchase.quantity for purchase in self.purchases),
                    "money_spent": total_cost,
                },
            )

        purchase_ref = "-".join(f"{int(item.item):02x}x{item.quantity}" for item in self.purchases)
        return RedProgressGoalProvider(
            kind=self.kind,
            binding_ref=(f"pokemon.red:resupply:mart-{int(self.map_id):02x}-{purchase_ref}"),
            adapter=self.adapter,
            boundary=boundary,
            executor=execute,
            estimated_effort=min(1.0, 0.04 + 0.02 * len(self.purchases)),
            estimated_risk=0.02,
        ).offer(observation)

    def _projected_resources(
        self,
        observation: RedGoalObservation,
    ) -> tuple[int, int]:
        capture = observation.capture_item_count
        recovery = observation.recovery_item_count
        for purchase in self.purchases:
            if purchase.item in _CAPTURE_ITEMS:
                capture += purchase.quantity
            if purchase.item in _RECOVERY_ITEMS:
                recovery += purchase.quantity
        return capture, recovery

    def _open_buy_list(self) -> None:
        for _ in range(8):
            if (
                self.emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
                self.emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
            ) == (5, 4):
                return
            self.actions.execute(MacroAction(MacroActionKind.CONFIRM))
            self._settle()
        raise RedGoalSkillError("Mart dialogue did not reach the priced item list")

    def _settle(self) -> None:
        self.actions.execute(MacroAction(MacroActionKind.WAIT, repeat=self.wait_frames))


@dataclass(frozen=True, slots=True)
class RedCenterRestoreGoalProvider:
    """Heal the whole party from a verified Generation-I Center boundary."""

    actions: CountingExecutor
    reader: PokemonRedStateReader
    emulator: RedGoalSkillEmulator
    adapter: PokemonRedGoalStateAdapter
    movement_attempts: int = 4
    dialogue_attempts: int = 32
    settle_frames: int = 120
    kind: GoalKind = GoalKind.RESTORE_TEAM

    def __post_init__(self) -> None:
        for name in ("movement_attempts", "dialogue_attempts", "settle_frames"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:  # noqa: E721
                raise ValueError(f"{name} must be a positive integer")

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        start = observation.raw

        def boundary(current: RedGoalObservation) -> RedGoalSkillAvailability:
            raw = current.raw
            if current.evidence.safety >= 1.0:
                return RedGoalSkillAvailability.unavailable(GoalUnavailableReason.NO_LEGAL_TARGET)
            if (
                raw.map_id not in _POKEMON_CENTER_MAPS
                or raw.player_x != 3
                or raw.player_y is None
                or not 3 <= raw.player_y <= 7
            ):
                return RedGoalSkillAvailability.unavailable(
                    GoalUnavailableReason.MISSING_CAPABILITY
                )
            return RedGoalSkillAvailability.available()

        before_actions = self.actions.actions_executed
        before_frames = self.emulator.frame_count

        def execute() -> GoalExecutionReport:
            assert start.player_y is not None
            for target_y in range(start.player_y - 1, 2, -1):
                for _ in range(self.movement_attempts):
                    before = self.reader.read()
                    self.actions.execute(MacroAction(MacroActionKind.MOVE, "up"))
                    self._settle()
                    after = self.reader.read()
                    if after.battle_state:
                        raise RedGoalSkillError("Center approach entered an unexpected battle")
                    if (
                        after.map_id == before.map_id
                        and after.player_x == 3
                        and after.player_y == target_y
                    ):
                        break
                else:
                    raise RedGoalSkillError("Center approach failed bounded movement")
            for _ in range(self.dialogue_attempts):
                self.actions.execute(MacroAction(MacroActionKind.CONFIRM))
                self._settle()
                raw = self.reader.read()
                if raw.map_id != start.map_id:
                    raise RedGoalSkillError("Center recovery changed maps")
                if _raw_party_restored(raw) and self.reader.read_input_readiness().ready:
                    break
            else:
                raise RedGoalSkillError("Center recovery did not restore the party")
            return GoalExecutionReport(
                actions_executed=self.actions.actions_executed - before_actions,
                frames_executed=self.emulator.frame_count - before_frames,
                evidence={"bounded": True, "whole_party_restore": True},
            )

        return RedProgressGoalProvider(
            kind=self.kind,
            binding_ref="pokemon.red:recovery:pokemon-center",
            adapter=self.adapter,
            boundary=boundary,
            executor=execute,
            estimated_effort=0.04,
            estimated_risk=0.01,
        ).offer(observation)

    def _settle(self) -> None:
        self.actions.execute(MacroAction(MacroActionKind.WAIT, repeat=self.settle_frames))


@dataclass(frozen=True, slots=True)
class RedControlRecoveryGoalProvider:
    """Bounded wait/cancel/confirm recovery for non-battle blocked control."""

    actions: CountingExecutor
    reader: PokemonRedStateReader
    emulator: RedGoalSkillEmulator
    adapter: PokemonRedGoalStateAdapter
    wait_attempts: int = 4
    cancel_attempts: int = 8
    confirm_attempts: int = 8
    settle_frames: int = 30
    kind: GoalKind = GoalKind.RECOVER_CONTROL

    def __post_init__(self) -> None:
        for name in (
            "wait_attempts",
            "cancel_attempts",
            "confirm_attempts",
            "settle_frames",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:  # noqa: E721
                raise ValueError(f"{name} must be a positive integer")

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        if not observation.raw.game_started:
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.TEMPORARILY_BLOCKED,
            )
        if observation.game_state.mode is GameMode.HALL_OF_FAME:
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.NO_LEGAL_TARGET,
            )
        if observation.raw.battle_state:
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.MISSING_CAPABILITY,
            )
        if observation.input_ready:
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.NO_LEGAL_TARGET,
            )
        before_actions = self.actions.actions_executed
        before_frames = self.emulator.frame_count
        before_story = self.adapter.graph.completed_ids(observation.game_state)

        def execute() -> GoalExecutionReport:
            attempts = self._recover()
            return GoalExecutionReport(
                actions_executed=self.actions.actions_executed - before_actions,
                frames_executed=self.emulator.frame_count - before_frames,
                evidence={"bounded": True, "recovery_attempts": attempts},
            )

        def verify(report: GoalExecutionReport) -> GoalVerification:
            after = self.adapter.observe()
            after_story = self.adapter.graph.completed_ids(after.game_state)
            if before_story.difference(after_story):
                return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            if observation.party.species_ids() != after.party.species_ids():
                return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            if report.actions_executed <= 0 or after.raw.battle_state or not after.input_ready:
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            return GoalVerification.succeeded()

        return RedGoalBindingOffer.available(
            ExecutableGoalBinding(
                binding_ref="pokemon.red:recovery:blocked-field-control",
                kind=self.kind,
                estimated_effort=0.04,
                estimated_risk=0.02,
                execute=execute,
                verify=verify,
            )
        )

    def _recover(self) -> int:
        attempts = 0
        for _ in range(self.wait_attempts):
            if self.reader.read_input_readiness().ready:
                return attempts
            self._settle()
            attempts += 1
        for kind, maximum in (
            (MacroActionKind.CANCEL, self.cancel_attempts),
            (MacroActionKind.CONFIRM, self.confirm_attempts),
        ):
            for _ in range(maximum):
                if self.reader.read_input_readiness().ready:
                    return attempts
                self.actions.execute(MacroAction(kind))
                self._settle()
                attempts += 1
        raise RedGoalSkillError("bounded control recovery did not restore input")

    def _settle(self) -> None:
        self.actions.execute(MacroAction(MacroActionKind.WAIT, repeat=self.settle_frames))


@dataclass(frozen=True, slots=True)
class RedEncounterDiscoveryGoalProvider:
    """Seek and safely leave one genuinely new Pokédex sighting."""

    source_id: str
    area_executor: RedAreaExecutor
    actions: CountingExecutor
    emulator: RedGoalSkillEmulator
    adapter: PokemonRedGoalStateAdapter
    boundary: GoalAvailabilityCheck | None = None
    maximum_seek_steps: int = 2_000
    maximum_encounters: int = 72
    kind: GoalKind = GoalKind.EXPLORE

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id:
            raise RedGoalSkillError("encounter-discovery source identity is absent")
        for name in ("maximum_seek_steps", "maximum_encounters"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:  # noqa: E721
                raise ValueError(f"{name} must be a positive integer")
        if self.boundary is not None and not callable(self.boundary):
            raise RedGoalSkillError("encounter-discovery boundary must be callable")

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        def boundary(current: RedGoalObservation) -> RedGoalSkillAvailability:
            if current.raw.battle_state or not current.input_ready:
                return RedGoalSkillAvailability.unavailable(
                    GoalUnavailableReason.TEMPORARILY_BLOCKED
                )
            if current.evidence.world_knowledge.satisfaction >= 1.0:
                return RedGoalSkillAvailability.unavailable(GoalUnavailableReason.NO_LEGAL_TARGET)
            if self.boundary is not None:
                result = self.boundary(current)
                if not isinstance(result, RedGoalSkillAvailability):
                    raise RedGoalSkillError(
                        "encounter-discovery boundary returned invalid evidence"
                    )
                return result
            return RedGoalSkillAvailability.available()

        before_actions = self.actions.actions_executed
        before_frames = self.emulator.frame_count
        initially_seen = frozenset(observation.collection.pokedex.seen_target_numbers)

        def execute() -> GoalExecutionReport:
            encounters = 0
            for _ in range(self.maximum_seek_steps):
                encountered = self.area_executor.encountered_species_ref()
                if encountered is None:
                    self.area_executor.seek_encounter()
                    encountered = self.area_executor.encountered_species_ref()
                    if encountered is None:
                        continue
                encounters += 1
                if encounters > self.maximum_encounters:
                    break
                observed = self.adapter.observe()
                newly_seen = frozenset(observed.collection.pokedex.seen_target_numbers).difference(
                    initially_seen
                )
                self.area_executor.flee_encounter()
                settled = self.adapter.observe()
                if any(member.hp <= 0 for member in settled.party.members):
                    raise RedGoalSkillError(
                        "encounter discovery could not preserve the living party"
                    )
                if newly_seen:
                    return GoalExecutionReport(
                        actions_executed=(self.actions.actions_executed - before_actions),
                        frames_executed=self.emulator.frame_count - before_frames,
                        evidence={
                            "bounded": True,
                            "encounters_seen": encounters,
                            "new_sighting_count": len(newly_seen),
                            "captures": 0,
                        },
                    )
            raise RedGoalSkillError(
                "encounter discovery exhausted its bounded search without a new sighting"
            )

        return RedProgressGoalProvider(
            kind=self.kind,
            binding_ref=f"pokemon.red:explore:{self.source_id}",
            adapter=self.adapter,
            boundary=boundary,
            executor=execute,
            estimated_effort=min(1.0, self.maximum_encounters / 500),
            estimated_risk=0.10,
        ).offer(observation)


@dataclass(frozen=True, slots=True)
class RedAreaSurveyGoalProvider:
    """Expose one bounded encounter-source survey as species acquisition."""

    source_id: str
    area_executor: RedAreaExecutor
    actions: CountingExecutor
    emulator: RedGoalSkillEmulator
    adapter: PokemonRedGoalStateAdapter
    boundary: GoalAvailabilityCheck | None = None
    policy: RedAreaExecutionPolicy = RedAreaExecutionPolicy()
    catalog: RedAcquisitionCatalog = RED_ACQUISITION_CATALOG
    kind: GoalKind = GoalKind.ACQUIRE_SPECIES

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id:
            raise RedGoalSkillError("area-survey source identity is absent")
        if self.boundary is not None and not callable(self.boundary):
            raise RedGoalSkillError("area-survey boundary must be callable")

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        if observation.raw.battle_state or not observation.input_ready:
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.TEMPORARILY_BLOCKED,
            )
        survey = summarize_red_area_survey(
            self.source_id,
            observation.collection_observation,
            self.catalog,
        )
        if not survey.missing_species_refs:
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.NO_LEGAL_TARGET,
            )
        inventory = dict(observation.raw.bag_items or ())
        if sum(inventory.get(int(item), 0) for item in _ORDINARY_CAPTURE_ITEMS) <= 0:
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.MISSING_RESOURCE,
            )
        if observation.immediate_capture_slots <= 0:
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.STORAGE_BLOCKED,
            )
        if self.boundary is not None:
            boundary = self.boundary(observation)
            if not isinstance(boundary, RedGoalSkillAvailability):
                raise RedGoalSkillError("area-survey boundary returned invalid evidence")
            if not boundary.executable:
                assert boundary.unavailable_reason is not None
                return RedGoalBindingOffer.unavailable(
                    self.kind,
                    boundary.unavailable_reason,
                )
        before_actions = self.actions.actions_executed
        before_frames = self.emulator.frame_count
        before_story = self.adapter.graph.completed_ids(observation.game_state)
        initial_missing_specimens = survey.missing_specimen_count

        def execute() -> GoalExecutionReport:
            report = run_red_area_survey(
                self.source_id,
                self.area_executor,
                policy=self.policy,
                catalog=self.catalog,
            )
            final_survey = summarize_red_area_survey(
                self.source_id,
                self.area_executor.read_collection(),
                self.catalog,
            )
            return GoalExecutionReport(
                actions_executed=self.actions.actions_executed - before_actions,
                frames_executed=self.emulator.frame_count - before_frames,
                evidence={
                    "bounded": True,
                    "semantic_actions": report.actions_executed,
                    "encounters_seen": report.encounters_seen,
                    "captures": report.captures,
                    "flees": report.flees,
                    "initial_missing": len(report.initial_missing_species_refs),
                    "final_missing": len(report.final_missing_species_refs),
                    "initial_missing_specimens": initial_missing_specimens,
                    "final_missing_specimens": final_survey.missing_specimen_count,
                },
            )

        initial_missing = set(survey.missing_species_refs)
        before_owned = observation.collection.collection.pokedex_owned_count
        before_living = observation.collection.collection.living_count

        def verify(report: GoalExecutionReport) -> GoalVerification:
            after = self.adapter.observe()
            after_story = self.adapter.graph.completed_ids(after.game_state)
            if before_story.difference(after_story):
                return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            after_survey = summarize_red_area_survey(
                self.source_id,
                after.collection_observation,
                self.catalog,
            )
            remaining = set(after_survey.missing_species_refs)
            remaining_specimens = after_survey.missing_specimen_count
            captures = report.evidence.get("captures")
            if (
                not remaining <= initial_missing
                or remaining_specimens >= initial_missing_specimens
                or after.collection.collection.pokedex_owned_count < before_owned
                or after.collection.collection.living_count < before_living
                or report.actions_executed <= 0
                or after.raw.battle_state
                or not after.input_ready
                or any(member.hp <= 0 for member in after.party.members)
                or type(captures) is not int  # noqa: E721
                or captures <= 0
                or initial_missing_specimens - remaining_specimens != captures
                or report.evidence.get("initial_missing_specimens") != initial_missing_specimens
                or report.evidence.get("final_missing_specimens") != remaining_specimens
            ):
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            return GoalVerification.succeeded()

        return RedGoalBindingOffer.available(
            ExecutableGoalBinding(
                binding_ref=f"pokemon.red:acquisition:{self.source_id}",
                kind=self.kind,
                estimated_effort=min(1.0, 0.12 * len(survey.missing_species_refs)),
                estimated_risk=0.18,
                execute=execute,
                verify=verify,
            )
        )


@dataclass(frozen=True, slots=True)
class RedBoxSwitchGoalProvider:
    """Rotate from a constrained active box without changing the collection."""

    target_box_index: int
    pc_boundary: Callable[[RedGoalObservation], bool]
    actions: CountingExecutor
    reader: PokemonRedStateReader
    emulator: RedGoalSkillEmulator
    adapter: PokemonRedGoalStateAdapter
    kind: GoalKind = GoalKind.MANAGE_STORAGE

    def __post_init__(self) -> None:
        if type(self.target_box_index) is not int or not 0 <= self.target_box_index < 12:
            raise ValueError("target_box_index must identify one of Red's twelve boxes")
        if not callable(self.pc_boundary):
            raise RedGoalSkillError("box-switch provider needs a PC boundary predicate")

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        if observation.raw.battle_state or not observation.input_ready:
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.TEMPORARILY_BLOCKED,
            )
        if not self.pc_boundary(observation):
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.MISSING_CAPABILITY,
            )
        current = observation.collection_observation.current_box_index
        counts = observation.collection_observation.box_counts
        if self.target_box_index == current or counts[self.target_box_index] >= 20:
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.NO_LEGAL_TARGET,
            )
        current_room = 20 - counts[current]
        target_room = 20 - counts[self.target_box_index]
        if target_room <= current_room:
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.NO_LEGAL_TARGET,
            )
        before_actions = self.actions.actions_executed
        before_frames = self.emulator.frame_count
        before_story = self.adapter.graph.completed_ids(observation.game_state)
        before_specimens = Counter(
            specimen.species_ref for specimen in observation.collection_observation.specimens
        )

        def execute() -> GoalExecutionReport:
            open_bills_pc(self.actions, self.reader)
            report = switch_box(
                self.actions,
                self.reader,
                target_box_index=self.target_box_index,
            )
            _close_menus(self.actions, self.reader, DEFAULT_LAVENDER_TIMING)
            return GoalExecutionReport(
                actions_executed=self.actions.actions_executed - before_actions,
                frames_executed=self.emulator.frame_count - before_frames,
                evidence={
                    "bounded": True,
                    "collection_preserved": report.passed,
                    "headroom_gained": target_room - current_room,
                },
            )

        def verify(report: GoalExecutionReport) -> GoalVerification:
            after = self.adapter.observe()
            after_story = self.adapter.graph.completed_ids(after.game_state)
            after_specimens = Counter(
                specimen.species_ref for specimen in after.collection_observation.specimens
            )
            if before_story.difference(after_story) or before_specimens != after_specimens:
                return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            if (
                after.collection_observation.current_box_index != self.target_box_index
                or after.immediate_capture_slots <= observation.immediate_capture_slots
                or report.evidence.get("collection_preserved") is not True
                or not after.input_ready
            ):
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            return GoalVerification.succeeded()

        return RedGoalBindingOffer.available(
            ExecutableGoalBinding(
                binding_ref=f"pokemon.red:storage:switch-box-{self.target_box_index + 1}",
                kind=self.kind,
                estimated_effort=0.08,
                estimated_risk=0.03,
                execute=execute,
                verify=verify,
            )
        )


@dataclass(frozen=True, slots=True)
class RedRouteGoalProvider:
    """Expose one already-planned, closed-loop route as semantic exploration."""

    destination_ref: str
    plan: RoutePlan
    actions: CountingExecutor
    traversal_observer: TraversalObserver
    emulator: RedGoalSkillEmulator
    adapter: PokemonRedGoalStateAdapter
    interruption_handler: InterruptionHandler | None = None
    replanner: RouteReplanner | None = None
    resource_manager: RouteResourceManager | None = None
    limits: RouteExecutionLimits = DEFAULT_ROUTE_EXECUTION_LIMITS
    kind: GoalKind = GoalKind.EXPLORE

    def __post_init__(self) -> None:
        if not isinstance(self.destination_ref, str) or not self.destination_ref:
            raise RedGoalSkillError("route goal destination identity is absent")
        if not isinstance(self.plan, RoutePlan):
            raise RedGoalSkillError("route goal plan is invalid")
        if self.kind is not GoalKind.EXPLORE:
            raise RedGoalSkillError(
                "a route can verify exploration but not acquisition or resupply"
            )

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        current = self.traversal_observer.observe()
        expected_map = self.plan.macro_path.maps[0]
        if (
            observation.raw.battle_state
            or not observation.input_ready
            or not current.ready
            or current.interruption is not None
        ):
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.TEMPORARILY_BLOCKED,
            )
        if (
            current.map_id != expected_map
            or current.at != self.plan.start_at
            or current.mode != self.plan.start_mode
        ):
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.WORLD_STATE_UNKNOWN,
            )
        before_actions = self.actions.actions_executed
        before_frames = self.emulator.frame_count
        before_story = self.adapter.graph.completed_ids(observation.game_state)
        before_party = observation.party.species_ids()
        before_knowledge = observation.evidence.world_knowledge.satisfaction

        def execute() -> GoalExecutionReport:
            route = execute_route(
                self.plan,
                self.actions,
                self.traversal_observer,
                interruption_handler=self.interruption_handler,
                replanner=self.replanner,
                resource_manager=self.resource_manager,
                limits=self.limits,
            )
            return GoalExecutionReport(
                actions_executed=self.actions.actions_executed - before_actions,
                frames_executed=self.emulator.frame_count - before_frames,
                evidence={
                    "bounded": True,
                    "route_passed": route.passed,
                    "acknowledged_steps": len(route.executed_steps),
                    "movement_requests": route.movement_requests,
                    "interruptions": len(route.interruptions),
                    "replans": len(route.replans),
                },
            )

        def verify(report: GoalExecutionReport) -> GoalVerification:
            terminal = self.traversal_observer.observe()
            after = self.adapter.observe()
            after_story = self.adapter.graph.completed_ids(after.game_state)
            if before_story.difference(after_story) or before_party != after.party.species_ids():
                return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            if (
                terminal.map_id != self.plan.terminal_map
                or terminal.at != self.plan.terminal_at
                or terminal.mode != self.plan.terminal_mode
                or terminal.interruption is not None
                or report.evidence.get("route_passed") is not True
                or after.evidence.world_knowledge.satisfaction <= before_knowledge
                or not after.input_ready
            ):
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            return GoalVerification.succeeded()

        return RedGoalBindingOffer.available(
            ExecutableGoalBinding(
                binding_ref=f"pokemon.red:route:{self.destination_ref}",
                kind=self.kind,
                estimated_effort=min(1.0, max(0.01, self.plan.cost / 500)),
                estimated_risk=min(0.50, 0.02 + len(self.plan.steps) / 2_000),
                execute=execute,
                verify=verify,
            )
        )


def _goal_progress(observation: RedGoalObservation, kind: GoalKind) -> float:
    field = _PROGRESS_FIELD[kind]
    value = getattr(observation.evidence, field)
    satisfaction = getattr(value, "satisfaction", value)
    if isinstance(satisfaction, bool) or not isinstance(satisfaction, (int, float)):
        raise RedGoalSkillError("goal progress evidence is not numeric")
    result = float(satisfaction)
    if not 0.0 <= result <= 1.0:
        raise RedGoalSkillError("goal progress evidence is outside the unit interval")
    return result


def _raw_party_restored(raw: RawGameState) -> bool:
    hp = tuple(raw.party_hp or ())
    maximum = tuple(raw.party_max_hp or ())
    statuses = tuple(raw.party_status or ())
    moves = tuple(raw.party_moves or ())
    pp = tuple(raw.party_pp or ())
    if (
        not hp
        or len(hp) != len(maximum)
        or hp != maximum
        or len(statuses) != len(hp)
        or any(status != 0 for status in statuses)
        or len(moves) != len(hp)
        or len(pp) != len(hp)
    ):
        return False
    return all(
        all((value & 0x3F) > 0 for move, value in zip(member_moves, member_pp, strict=True) if move)
        for member_moves, member_pp in zip(moves, pp, strict=True)
    )
