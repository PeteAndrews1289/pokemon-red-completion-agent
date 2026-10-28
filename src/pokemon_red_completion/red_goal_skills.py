"""Reusable bounded Red skills exposed to the portable goal manager.

The manager sees only semantic goal kinds and normalized cost.  This module
keeps cartridge-specific controller bindings on the executor side, observes a
fresh post-action state, and turns that independent observation into the only
success label that may enter a goal-manager episode.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.domain import GameMode
from pokemon_red_completion.encounter_source_development import (
    EncounterSourceDevelopmentProvider,
    EncounterSourceDevelopmentSnapshot,
)
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.field_recovery import (
    FieldRecoveryError,
    plan_party_recovery,
    use_field_recovery_item,
)
from pokemon_red_completion.goal_manager import (
    GoalDecisionOutcome,
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
from pokemon_red_completion.goal_resource_quote import GoalResourceQuote, GoalResourceReserve
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    _buy_mart_item,
    _close_menus,
    _sell_mart_item_stack,
)
from pokemon_red_completion.observation import (
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
    event_flag_is_set,
)
from pokemon_red_completion.red_acquisition import (
    RED_ACQUISITION_CATALOG,
    RedAcquisitionCatalog,
    RedAreaExecutionError,
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
class RedEncounterSourceDevelopmentGoalProvider:
    """Bind the portable local-development contract to one Red encounter source.

    The provider receives an already bounded source-local executor.  It neither
    navigates to a venue nor embeds map coordinates, so a later title can bind
    the same semantic contract through its own encounter-source adapter.
    """

    source_ref: str
    binding_ref: str
    adapter: PokemonRedGoalStateAdapter
    boundary: GoalAvailabilityCheck
    executor: GoalSkillExecutor
    estimated_effort: float = 0.30
    estimated_risk: float = 0.15
    kind: GoalKind = GoalKind.DEVELOP_TEAM

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        availability = self.boundary(observation)
        if not isinstance(availability, RedGoalSkillAvailability):
            raise RedGoalSkillError(
                "encounter-source development returned invalid boundary evidence"
            )
        if not availability.executable:
            assert availability.unavailable_reason is not None
            return RedGoalBindingOffer.unavailable(
                self.kind,
                availability.unavailable_reason,
            )

        def observe_after() -> EncounterSourceDevelopmentSnapshot:
            current = self.adapter.observe()
            current_boundary = self.boundary(current)
            if not isinstance(current_boundary, RedGoalSkillAvailability):
                raise RedGoalSkillError(
                    "encounter-source development returned invalid fresh boundary evidence"
                )
            return red_encounter_source_development_snapshot(
                current,
                source_ref=self.source_ref,
                local_encounters_available=current_boundary.executable,
            )

        provider = EncounterSourceDevelopmentProvider(
            binding_ref=self.binding_ref,
            observer=observe_after,
            executor=self.executor,
            estimated_effort=self.estimated_effort,
            estimated_risk=self.estimated_risk,
        )
        offered = provider.offer(
            red_encounter_source_development_snapshot(
                observation,
                source_ref=self.source_ref,
                local_encounters_available=True,
            )
        )
        if offered.binding is None:
            assert offered.unavailable_reason is not None
            return RedGoalBindingOffer.unavailable(
                self.kind,
                offered.unavailable_reason,
            )
        return RedGoalBindingOffer.available(offered.binding)


def red_encounter_source_development_snapshot(
    observation: RedGoalObservation,
    *,
    source_ref: str,
    local_encounters_available: bool,
) -> EncounterSourceDevelopmentSnapshot:
    """Project one coherent Red observation into the portable verifier input."""

    if not isinstance(observation, RedGoalObservation):
        raise TypeError("observation must be a RedGoalObservation")
    living = observation.evidence.living_collection
    return EncounterSourceDevelopmentSnapshot(
        source_ref=source_ref,
        team_readiness=observation.evidence.team_readiness,
        living_specimens=len(observation.collection_observation.specimens),
        required_specimens_remaining=max(0, living.target - living.completed),
        fainted_party_members=observation.party.fainted_count,
        input_ready=observation.input_ready,
        in_battle=bool(observation.raw.battle_state),
        local_encounters_available=local_encounters_available,
    )


@dataclass(frozen=True, slots=True)
class RedFieldRestoreGoalProvider:
    """Recover damaged, living party members with observed field items."""

    actions: CountingExecutor
    reader: PokemonRedStateReader
    emulator: RedGoalSkillEmulator
    adapter: PokemonRedGoalStateAdapter
    kind: GoalKind = GoalKind.RESTORE_TEAM
    affordable_single_item: bool = False
    reserve_last_full_restore: bool = False

    def __post_init__(self) -> None:
        if type(self.reserve_last_full_restore) is not bool:
            raise RedGoalSkillError("restoration reserve must be an explicit boolean")
        if self.reserve_last_full_restore and not self.affordable_single_item:
            raise RedGoalSkillError("restoration reserve requires single-item recovery")

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        plan, unavailable = self._plan(
            observation,
            affordable_single_item=self.affordable_single_item,
            reserve_last_full_restore=self.reserve_last_full_restore,
        )
        if unavailable is not None:
            return RedGoalBindingOffer.unavailable(self.kind, unavailable)
        assert plan
        before_actions = self.actions.actions_executed
        before_frames = self.emulator.frame_count

        def execute() -> GoalExecutionReport:
            if self.affordable_single_item and self.adapter.observe() != observation:
                raise RedGoalSkillError("field restoration origin changed before input")
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
                binding_ref=(
                    "pokemon.red:recovery:single-field-item"
                    if self.affordable_single_item
                    else "pokemon.red:recovery:field-items"
                ),
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
        *,
        affordable_single_item: bool = False,
        reserve_last_full_restore: bool = False,
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
        if affordable_single_item:
            # Fully recover one affordable target, not a fictitious whole-party heal.
            # Prefer the narrow item when it suffices; reserve Full Restore as fallback.
            candidates = []
            for index, preferred in plan:
                items = (
                    (preferred, ItemId.MAX_POTION, ItemId.FULL_RESTORE)
                    if not status[index]
                    else (preferred, ItemId.FULL_RESTORE)
                )
                for item in dict.fromkeys(items):
                    if inventory.get(int(item), 0) <= 0:
                        continue
                    # A prospective resource constraint, not a learned preference.
                    # Keep the final broad restorative for status or sub-readiness
                    # recovery; do not block narrower affordable items or emergencies.
                    if (
                        reserve_last_full_restore
                        and item is ItemId.FULL_RESTORE
                        and inventory[int(item)] == 1
                        and not status[index]
                        and hp[index] * 2 >= maximum[index]
                    ):
                        continue
                    if item is ItemId.HYPER_POTION and maximum[index] - hp[index] > 200:
                        continue
                    candidates.append((index, item))
                    break
            if not candidates:
                return (), GoalUnavailableReason.MISSING_RESOURCE
            selected = min(
                candidates,
                key=lambda pair: (
                    hp[pair[0]] / maximum[pair[0]],
                    -int(bool(status[pair[0]])),
                    pair[0],
                ),
            )
            return (selected,), None
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
        ItemId.MAX_POTION,
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
class RedMartSurplusSale:
    """Finite liquidity bridge; never sell unique assets or the recovery floor.

    Hyper Potions retain the historical eight-item floor. Full Restores have a
    separately declared six-item floor (one per party slot); neither rule permits
    spending the last healing stock. Prices are pinned in data/items/prices.asm.
    """

    item: ItemId
    quantity: int
    minimum_retained: int

    def __post_init__(self) -> None:
        floors = {ItemId.HYPER_POTION: 8, ItemId.FULL_RESTORE: 6}
        if not isinstance(self.item, ItemId) or self.item not in floors:
            raise ValueError("surplus sale item is protected or unsupported")
        if type(self.quantity) is not int or not 1 <= self.quantity <= 99:
            raise ValueError("surplus sale quantity differs")
        if (
            type(self.minimum_retained) is not int
            or not floors[self.item] <= self.minimum_retained <= 99
        ):
            raise ValueError("surplus sale violates the item-specific recovery reserve")

    @property
    def proceeds(self) -> int:
        return self.quantity * (1500 if self.item is ItemId.FULL_RESTORE else 750)


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
    funding_sale: RedMartSurplusSale | None = None
    affordable_ball_purchase: bool = False
    # Explicit inventory targets, not a bypass of the legacy aggregate reserve.
    # An order must exactly fill each declared deficit; satisfied targets mask it.
    reserve_targets: tuple[tuple[ItemId, int], ...] = ()

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
        if self.funding_sale is not None and (
            not isinstance(self.funding_sale, RedMartSurplusSale)
            or any(p.item is self.funding_sale.item for p in self.purchases)
        ):
            raise ValueError("Mart cannot sell and rebuy the same resource")
        if type(self.wait_frames) is not int or self.wait_frames <= 0:  # noqa: E721
            raise ValueError("Mart wait_frames must be a positive integer")
        if type(self.affordable_ball_purchase) is not bool or (
            self.affordable_ball_purchase
            and (
                len(self.purchases) != 1
                or self.purchases[0].item not in _ORDINARY_CAPTURE_ITEMS
                or self.funding_sale is not None
            )
        ):
            raise ValueError("affordable Mart support needs one ordinary ball and no sale")
        if type(self.reserve_targets) is not tuple:
            raise ValueError("exact Mart reserves must be an immutable tuple")
        if self.reserve_targets and (
            any(type(row) is not tuple or len(row) != 2 for row in self.reserve_targets)
            or any(
                not isinstance(item, ItemId)
                or item not in _CAPTURE_ITEMS | _RECOVERY_ITEMS
                or type(target) is not int
                or not 1 <= target <= 99
                for item, target in self.reserve_targets
            )
            or len(dict(self.reserve_targets)) != len(self.reserve_targets)
            or set(dict(self.reserve_targets)) != {p.item for p in self.purchases}
            or self.funding_sale is not None
            or self.affordable_ball_purchase
        ):
            raise ValueError("exact Mart reserves require unique supported targets and no sale")

    def affordable_provider(
        self,
        observation: RedGoalObservation,
    ) -> RedMartResupplyGoalProvider | None:
        """Freeze an exact purchase before transport; never increase it on arrival."""
        if not self.affordable_ball_purchase:
            return self
        from pokemon_red_completion.goal_resource_quote import affordable_purchase_quantity

        money = observation.raw.player_money
        if money is None:
            return None
        purchase = self.purchases[0]
        deficit = self._ordinary_ball_deficit(observation)
        if not deficit:
            return None
        quantity = affordable_purchase_quantity(
            available_funds=money,
            unit_price=purchase.unit_price,
            maximum_quantity=purchase.quantity,
            current_stock=dict(observation.raw.bag_items or ()).get(int(purchase.item), 0),
            stack_limit=99,
        )
        return (
            None
            if not quantity
            else replace(
                self,
                purchases=(replace(purchase, quantity=quantity),),
                affordable_ball_purchase=False,
                # A ball-only purchase must not depend on the aggregate minimum of
                # capture AND medicine stock. Reuse the existing exact-target proof;
                # do not relax the legacy non-opted-in provider or protected ball.
                reserve_targets=(
                    (
                        purchase.item,
                        dict(observation.raw.bag_items or ()).get(int(purchase.item), 0) + quantity,
                    ),
                ),
            )
        )

    def _ordinary_ball_deficit(self, observation: RedGoalObservation) -> int:
        stock = sum(
            n for item, n in (observation.raw.bag_items or ()) if item in _ORDINARY_CAPTURE_ITEMS
        )
        return max(0, self.adapter.config.desired_capture_items - stock)

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        if self.affordable_ball_purchase:
            fixed = self.affordable_provider(observation)
            return (
                RedGoalBindingOffer.unavailable(self.kind, GoalUnavailableReason.MISSING_RESOURCE)
                if fixed is None and self._ordinary_ball_deficit(observation)
                else RedGoalBindingOffer.unavailable(
                    self.kind, GoalUnavailableReason.NO_LEGAL_TARGET
                )
                if fixed is None
                else fixed.offer(observation)
            )
        start = observation.raw

        def boundary(current: RedGoalObservation) -> RedGoalSkillAvailability:
            raw = current.raw
            if raw.battle_state or not current.input_ready:
                return RedGoalSkillAvailability.unavailable(
                    GoalUnavailableReason.TEMPORARILY_BLOCKED
                )
            if (
                raw.map_id != self.map_id
                or raw.player_x != self.player_x
                or raw.player_y != self.player_y
            ):
                return RedGoalSkillAvailability.unavailable(
                    GoalUnavailableReason.MISSING_CAPABILITY
                )
            return self.resource_availability(current)

        before_actions = self.actions.actions_executed
        before_frames = self.emulator.frame_count
        before_inventory = dict(start.bag_items or ())
        before_money = start.player_money
        total_cost = sum(purchase.quantity * purchase.unit_price for purchase in self.purchases)
        funding = self._required_funding(observation)

        def execute() -> GoalExecutionReport:
            if before_money is None:
                raise RedGoalSkillError("Mart resupply lacks money evidence")
            if not self._native_purchase_unlocked(self.reader.read()):
                raise RedGoalSkillError("Mart native story prerequisite is incomplete")
            if self.reserve_targets and (
                self.reader.read() != start or not boundary(self.adapter.observe()).executable
            ):
                raise RedGoalSkillError("exact Mart reserve origin changed before input")
            if funding is not None:
                fresh = self.reader.read()
                if (
                    dict(fresh.bag_items or ()) != before_inventory
                    or fresh.player_money != before_money
                    or fresh.party_species_ids != start.party_species_ids
                    or fresh.party_hp != start.party_hp
                ):
                    raise RedGoalSkillError("Mart funding resources changed before sale")
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
            if funding is not None:
                if (
                    dict(approached.bag_items or ()) != before_inventory
                    or approached.player_money != before_money
                    or approached.party_species_ids != start.party_species_ids
                    or approached.party_hp != start.party_hp
                ):
                    raise RedGoalSkillError("Mart funding resources changed before sale")
                _sell_mart_item_stack(
                    self.actions,
                    self.reader,
                    self.emulator,
                    DEFAULT_LAVENDER_TIMING,
                    funding.item,
                    quantity=funding.quantity,
                    expected_proceeds=funding.proceeds,
                )
                sold = self.reader.read()
                expected_sold = dict(before_inventory)
                expected_sold[int(funding.item)] -= funding.quantity
                if (
                    dict(sold.bag_items or ()) != expected_sold
                    or sold.player_money != before_money + funding.proceeds
                    or sold.party_species_ids != start.party_species_ids
                    or sold.party_hp != start.party_hp
                    or (sold.map_id, sold.player_x, sold.player_y)
                    != (start.map_id, start.player_x, start.player_y)
                    or sold.battle_state
                ):
                    raise RedGoalSkillError(
                        "Mart funding sale changed protected inventory or party"
                    )
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
            if funding is not None:
                expected_inventory[int(funding.item)] -= funding.quantity
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
                or after.player_money
                != before_money + (funding.proceeds if funding else 0) - total_cost
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
                    **(
                        {"sale_proceeds": funding.proceeds, "surplus_units_sold": funding.quantity}
                        if funding
                        else {}
                    ),
                },
            )

        purchase_ref = "-".join(f"{int(item.item):02x}x{item.quantity}" for item in self.purchases)
        if self.reserve_targets:
            targets = dict(self.reserve_targets)

            def verify_reserves(before, after, report):
                expected = dict(before.raw.bag_items or ())
                for purchase in self.purchases:
                    expected[int(purchase.item)] = targets[purchase.item]
                protected = (
                    "map_id",
                    "player_x",
                    "player_y",
                    "party_count",
                    "party_species_ids",
                    "party_levels",
                    "party_hp",
                    "party_max_hp",
                    "party_status",
                    "party_moves",
                    "party_pp",
                )
                if (
                    report.actions_executed <= 0
                    or after.raw.battle_state
                    or not after.input_ready
                    or dict(after.raw.bag_items or ()) != expected
                    or after.raw.player_money != before.raw.player_money - total_cost
                    or any(getattr(before.raw, key) != getattr(after.raw, key) for key in protected)
                    or before.collection_observation != after.collection_observation
                    or self.adapter.graph.completed_ids(before.game_state)
                    != self.adapter.graph.completed_ids(after.game_state)
                ):
                    return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
                return GoalVerification.succeeded()

            target_ref = "-".join(f"{int(i):02x}to{n}" for i, n in self.reserve_targets)
            return RedObservedGoalSkillProvider(
                kind=self.kind,
                binding_ref=f"pokemon.red:resupply:mart-{int(self.map_id):02x}-{purchase_ref}-{target_ref}",
                adapter=self.adapter,
                availability=boundary,
                executor=execute,
                verifier=verify_reserves,
                estimated_effort=min(1.0, 0.04 + 0.02 * len(self.purchases)),
                estimated_risk=0.02,
            ).offer(observation)
        return RedProgressGoalProvider(
            kind=self.kind,
            binding_ref=(f"pokemon.red:resupply:mart-{int(self.map_id):02x}-{purchase_ref}"),
            adapter=self.adapter,
            boundary=boundary,
            executor=execute,
            estimated_effort=min(1.0, 0.04 + 0.02 * len(self.purchases)),
            estimated_risk=0.02,
        ).offer(observation)

    def resource_availability(self, observation: RedGoalObservation) -> RedGoalSkillAvailability:
        """Check actual resources without claiming the player is at the clerk."""

        if not self._native_purchase_unlocked(observation.raw):
            return RedGoalSkillAvailability.unavailable(GoalUnavailableReason.MISSING_CAPABILITY)
        if self.affordable_ball_purchase:
            fixed = self.affordable_provider(observation)
            return (
                RedGoalSkillAvailability.unavailable(GoalUnavailableReason.MISSING_RESOURCE)
                if fixed is None and self._ordinary_ball_deficit(observation)
                else RedGoalSkillAvailability.unavailable(GoalUnavailableReason.NO_LEGAL_TARGET)
                if fixed is None
                else fixed.resource_availability(observation)
            )
        inventory = dict(observation.raw.bag_items or ())
        new_slots = sum(purchase.item not in inventory for purchase in self.purchases)
        if len(inventory) + new_slots > 20:
            return RedGoalSkillAvailability.unavailable(GoalUnavailableReason.MISSING_CAPABILITY)
        cost = sum(purchase.quantity * purchase.unit_price for purchase in self.purchases)
        funding = self._required_funding(observation)
        proceeds = funding.proceeds if funding else 0
        if observation.raw.player_money is None or observation.raw.player_money + proceeds < cost:
            return RedGoalSkillAvailability.unavailable(GoalUnavailableReason.MISSING_RESOURCE)
        if self.reserve_targets:
            targets = dict(self.reserve_targets)
            if any(
                targets[p.item] - inventory.get(int(p.item), 0) != p.quantity
                for p in self.purchases
            ):
                return RedGoalSkillAvailability.unavailable(GoalUnavailableReason.NO_LEGAL_TARGET)
            return RedGoalSkillAvailability.available()
        capture, recovery = self._projected_resources(observation)
        projected = min(
            headroom_satisfaction(
                capture, self.adapter.config.desired_capture_items, subject="capture item"
            ),
            headroom_satisfaction(
                recovery, self.adapter.config.desired_recovery_items, subject="recovery item"
            ),
        )
        if projected <= observation.evidence.resources:
            return RedGoalSkillAvailability.unavailable(GoalUnavailableReason.NO_LEGAL_TARGET)
        return RedGoalSkillAvailability.available()

    def _native_purchase_unlocked(self, raw: RawGameState) -> bool:
        # Viridian's clerk offers the parcel dialogue until Oak receives it.
        # The destination fact is required before transport as well as at input.
        return self.map_id is not MapId.VIRIDIAN_MART or event_flag_is_set(
            raw.event_flags, EventFlag.OAK_GOT_PARCEL
        )

    def resource_quote(self, observation: RedGoalObservation) -> GoalResourceQuote:
        """Quote the exact fixed purchase using fresh funds and reserve counts.

        This neither changes quantities nor sends input. Execution still checks
        exact bag and money deltas independently at the actual clerk boundary.
        """
        if self.affordable_ball_purchase:
            fixed = self.affordable_provider(observation)
            if fixed is None:
                raise RedGoalSkillError("no affordable Mart purchase can be quoted")
            return fixed.resource_quote(observation)
        funds = observation.raw.player_money
        if funds is None or not self.resource_availability(observation).executable:
            raise RedGoalSkillError("cannot quote an unavailable Mart purchase")
        if any(item.item not in _CAPTURE_ITEMS | _RECOVERY_ITEMS for item in self.purchases):
            raise RedGoalSkillError("Mart quote has an unsupported resource class")
        reserves = []
        for resource, items, count, target in (
            (
                "capture",
                _CAPTURE_ITEMS,
                observation.capture_item_count,
                self.adapter.config.desired_capture_items,
            ),
            (
                "recovery",
                _RECOVERY_ITEMS,
                observation.recovery_item_count,
                self.adapter.config.desired_recovery_items,
            ),
        ):
            purchased = sum(item.quantity for item in self.purchases if item.item in items)
            if purchased:
                if self.reserve_targets:
                    inventory = dict(observation.raw.bag_items or ())
                    count = sum(
                        inventory.get(int(i), 0) for i, _ in self.reserve_targets if i in items
                    )
                    target = sum(n for i, n in self.reserve_targets if i in items)
                reserves.append(GoalResourceReserve(resource, count, target, purchased))
        funding = self._required_funding(observation)
        return GoalResourceQuote(
            available_funds=funds,
            purchase_cost=sum(item.quantity * item.unit_price for item in self.purchases),
            reserves=tuple(reserves),
            funding_proceeds=funding.proceeds if funding else 0,
        )

    def _required_funding(self, observation: RedGoalObservation) -> RedMartSurplusSale | None:
        funds = observation.raw.player_money
        cost = sum(p.quantity * p.unit_price for p in self.purchases)
        sale = self.funding_sale
        if funds is None or funds >= cost or sale is None:
            return None
        available = dict(observation.raw.bag_items or ()).get(int(sale.item), 0)
        return sale if available - sale.quantity >= sale.minimum_retained else None

    def _projected_resources(
        self,
        observation: RedGoalObservation,
    ) -> tuple[int, int]:
        capture = observation.capture_item_count
        recovery = observation.recovery_item_count
        funding = self._required_funding(observation)
        if funding is not None:
            recovery -= funding.quantity
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


def prepare_center_departure(actions: CountingExecutor, reader: PokemonRedStateReader) -> None:
    """Settle nurse/PC interactions before transport at their known boundaries."""
    raw = reader.read()
    if raw.map_id in _POKEMON_CENTER_MAPS and (raw.player_x, raw.player_y) == (13, 4):
        from pokemon_red_completion.red_pc_storage import close_generic_pc_session

        close_generic_pc_session(actions, reader)
    if (
        raw.map_id in _POKEMON_CENTER_MAPS
        and (raw.player_x, raw.player_y) == (3, 3)
        and reader.read_bottom_dialogue_box_visible()
    ):
        finish_center_dialogue(actions, reader)


def finish_center_dialogue(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    *,
    maximum_attempts: int = 16,
    settle_frames: int = 120,
    include_indigo_lobby: bool = False,
) -> None:
    """Leave an already-healed nurse interaction without guessing walk inputs.

    Only a verified Center/nurse boundary may use this recovery. CANCEL advances
    farewell text without starting another healing interaction after it closes.
    A missing text frame is necessary, not sufficient: movement flags must also
    settle and the restored party and position must remain unchanged.
    """
    if maximum_attempts <= 0 or settle_frames <= 0:
        raise ValueError("Center dialogue bounds must be positive")
    start = reader.read()
    if type(include_indigo_lobby) is not bool:
        raise TypeError("Indigo recovery opt-in must be boolean")
    indigo = include_indigo_lobby and start.map_id == MapId.INDIGO_PLATEAU_LOBBY
    if (
        (start.map_id not in _POKEMON_CENTER_MAPS and not indigo)
        or (start.player_y, start.player_x) != ((7, 7) if indigo else (3, 3))
        or start.battle_state != 0
        or not _raw_party_restored(start)
    ):
        raise RedGoalSkillError("Center dialogue recovery requires a healed nurse boundary")
    for attempt in range(maximum_attempts + 1):
        raw = reader.read()
        if (
            (raw.map_id, raw.player_x, raw.player_y)
            != (start.map_id, start.player_x, start.player_y)
            or raw.battle_state != 0
            or raw.party_species_ids != start.party_species_ids
            or not _raw_party_restored(raw)
        ):
            raise RedGoalSkillError("Center dialogue recovery changed its safe boundary")
        visible = reader.read_bottom_dialogue_box_visible()
        if not visible and reader.read_input_readiness().ready:
            return
        if attempt == maximum_attempts:
            break
        if visible:
            actions.execute(MacroAction(MacroActionKind.CANCEL))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=settle_frames))
    raise RedGoalSkillError("Center farewell did not release overworld control")


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
    require_pp_restore: bool = False
    require_full_pp_restore: bool = False
    include_indigo_lobby: bool = False
    require_indigo_checkpoint: bool = False

    def __post_init__(self) -> None:
        if type(self.require_indigo_checkpoint) is not bool:
            raise TypeError("Indigo checkpoint requirement must be boolean")
        if self.require_indigo_checkpoint and not (
            self.include_indigo_lobby and self.require_full_pp_restore
        ):
            raise ValueError("Indigo checkpoint requires explicit lobby and full-party recovery")
        if type(self.include_indigo_lobby) is not bool:
            raise TypeError("Indigo recovery opt-in must be boolean")
        if type(self.require_pp_restore) is not bool:
            raise ValueError("explicit Center PP recovery mode must be boolean")
        if type(self.require_full_pp_restore) is not bool:
            raise ValueError("explicit full Center PP recovery mode must be boolean")
        for name in ("movement_attempts", "dialogue_attempts", "settle_frames"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:  # noqa: E721
                raise ValueError(f"{name} must be a positive integer")

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        start = observation.raw
        indigo = self.include_indigo_lobby and start.map_id == MapId.INDIGO_PLATEAU_LOBBY
        # Indigo's nurse is behind a counter: object(5,7), counter(6,7),
        # player interaction boundary(7,7), not the adjacent counter tile.
        nurse_y, nurse_x, entry_y = (7, 7, 11) if indigo else (3, 3, 7)
        restored = (
            _raw_party_fully_restored if self.require_full_pp_restore else _raw_party_restored
        )

        def boundary(current: RedGoalObservation) -> RedGoalSkillAvailability:
            raw = current.raw
            if self.require_indigo_checkpoint and not indigo:
                return RedGoalSkillAvailability.unavailable(
                    GoalUnavailableReason.MISSING_CAPABILITY
                )
            if raw.battle_state or not current.input_ready:
                return RedGoalSkillAvailability.unavailable(
                    GoalUnavailableReason.TEMPORARILY_BLOCKED
                )
            if current.evidence.safety >= 1.0 and not (
                (self.require_pp_restore or self.require_full_pp_restore)
                and not restored(raw)
                or self.require_full_pp_restore
                and (raw.player_y, raw.player_x) != (nurse_y, nurse_x)
                or self.require_indigo_checkpoint
                and self.reader.read_last_blackout_map() != int(MapId.INDIGO_PLATEAU)
            ):
                return RedGoalSkillAvailability.unavailable(GoalUnavailableReason.NO_LEGAL_TARGET)
            if (
                (raw.map_id not in _POKEMON_CENTER_MAPS and not indigo)
                or raw.map_id != start.map_id
                or raw.player_x != nurse_x
                or raw.player_y is None
                or not nurse_y <= raw.player_y <= entry_y
            ):
                return RedGoalSkillAvailability.unavailable(
                    GoalUnavailableReason.MISSING_CAPABILITY
                )
            return RedGoalSkillAvailability.available()

        def execute() -> GoalExecutionReport:
            # A caller may perform separately metered facing support after
            # quotation. Charge this receipt only for nursing execution;
            # outer accounting still retains all earlier inputs.
            before_actions = self.actions.actions_executed
            before_frames = self.emulator.frame_count
            assert start.player_y is not None
            for target_y in range(start.player_y - 1, nurse_y - 1, -1):
                for _ in range(self.movement_attempts):
                    before = self.reader.read()
                    self.actions.execute(MacroAction(MacroActionKind.MOVE, "up"))
                    self._settle()
                    after = self.reader.read()
                    if after.battle_state:
                        raise RedGoalSkillError("Center approach entered an unexpected battle")
                    if (
                        after.map_id == before.map_id
                        and after.player_x == nurse_x
                        and after.player_y == target_y
                    ):
                        break
                else:
                    raise RedGoalSkillError("Center approach failed bounded movement")
            # Routing can reach the interaction tile from either side. Being
            # on that tile does not imply that the player faces the nurse.
            if self.reader.read_player_facing() != "up":
                before = self.reader.read()
                self.actions.execute(MacroAction(MacroActionKind.MOVE, "up"))
                self._settle()
                after = self.reader.read()
                if (
                    (after.map_id, after.player_y, after.player_x)
                    != (start.map_id, nurse_y, nurse_x)
                    or after.battle_state
                    or self.reader.read_player_facing() != "up"
                    or after.party_hp != before.party_hp
                    or after.party_pp != before.party_pp
                    or after.party_status != before.party_status
                    or after.bag_items != before.bag_items
                    or after.player_money != before.player_money
                ):
                    raise RedGoalSkillError("Center nurse facing changed its safe boundary")
            for _ in range(self.dialogue_attempts):
                self.actions.execute(MacroAction(MacroActionKind.CONFIRM))
                self._settle()
                raw = self.reader.read()
                if raw.map_id != start.map_id:
                    raise RedGoalSkillError("Center recovery changed maps")
                if (restored(raw) and self.reader.read_input_readiness().ready
                        and (not self.require_indigo_checkpoint
                             or self.reader.read_last_blackout_map()
                             == int(MapId.INDIGO_PLATEAU))):
                    break
            else:
                raise RedGoalSkillError("Center recovery did not restore the party")
            finish_center_dialogue(
                self.actions,
                self.reader,
                maximum_attempts=self.dialogue_attempts,
                settle_frames=self.settle_frames,
                include_indigo_lobby=self.include_indigo_lobby,
            )
            return GoalExecutionReport(
                actions_executed=self.actions.actions_executed - before_actions,
                frames_executed=self.emulator.frame_count - before_frames,
                evidence={"bounded": True, "whole_party_restore": True},
            )

        if self.require_pp_restore or self.require_full_pp_restore:

            def verify_restore(before, after, report):
                if (
                    report.actions_executed <= 0
                    or after.raw.battle_state
                    or not after.input_ready
                    or after.raw.map_id != before.raw.map_id
                    or not restored(after.raw)
                    or restored(before.raw)
                    and not self.require_full_pp_restore
                    or self.require_full_pp_restore
                    and (after.raw.player_y, after.raw.player_x) != (nurse_y, nurse_x)
                    or self.require_indigo_checkpoint
                    and self.reader.read_last_blackout_map() != int(MapId.INDIGO_PLATEAU)
                    or before.raw.bag_items != after.raw.bag_items
                    or before.raw.player_money != after.raw.player_money
                    or before.raw.party_species_ids != after.raw.party_species_ids
                    or before.raw.party_levels != after.raw.party_levels
                    or before.raw.party_moves != after.raw.party_moves
                    or before.collection_observation != after.collection_observation
                    or self.adapter.graph.completed_ids(before.game_state)
                    != self.adapter.graph.completed_ids(after.game_state)
                ):
                    return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
                return GoalVerification.succeeded()

            return RedObservedGoalSkillProvider(
                kind=self.kind,
                binding_ref="pokemon.red:recovery:pokemon-center-pp",
                adapter=self.adapter,
                availability=boundary,
                executor=execute,
                verifier=verify_restore,
                estimated_effort=0.04,
                estimated_risk=0.01,
            ).offer(observation)

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
    settle_dialogue: bool = False

    def __post_init__(self) -> None:
        if type(self.settle_dialogue) is not bool:
            raise TypeError("dialogue settlement permission must be a boolean")
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
        if observation.input_ready and not self._dialogue_blocked():
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.NO_LEGAL_TARGET,
            )
        before_actions = self.actions.actions_executed
        before_frames = self.emulator.frame_count
        before_story = self.adapter.graph.completed_ids(observation.game_state)
        preserved = {
            name: getattr(observation.raw, name)
            for name in ("player_money", "bag_items", "party_species_ids", "party_levels",
                         "party_hp", "party_max_hp", "party_status", "party_moves", "party_pp",
                         "badge_bits")
        } if self.settle_dialogue else {}

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
            if (report.actions_executed <= 0 or after.raw.battle_state or not after.input_ready
                    or self._dialogue_blocked()
                    or any(getattr(after.raw, name) != value for name, value in preserved.items())):
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            if self._start_menu_visible():
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
        start_menu_recovery = self._start_menu_visible()
        for _ in range(self.wait_attempts):
            if self.reader.read().battle_state:
                raise RedGoalSkillError("control recovery entered battle; learned handoff required")
            if self._field_control_ready():
                return attempts
            self._settle()
            attempts += 1
        for kind, maximum in (
            (MacroActionKind.CANCEL, self.cancel_attempts),
            (MacroActionKind.CONFIRM, self.confirm_attempts),
        ):
            if kind is MacroActionKind.CONFIRM and start_menu_recovery:
                # Never choose an item/save entry while attempting to close Start.
                break
            for _ in range(maximum):
                if self.reader.read().battle_state:
                    raise RedGoalSkillError(
                        "control recovery entered battle; learned handoff required"
                    )
                if self._field_control_ready():
                    return attempts
                self.actions.execute(MacroAction(kind))
                self._settle()
                attempts += 1
        if self._field_control_ready():
            return attempts
        raise RedGoalSkillError("bounded control recovery did not restore input")

    def _start_menu_visible(self) -> bool:
        return bool(getattr(self.reader, "read_overworld_start_menu_visible", lambda: False)())

    def _field_control_ready(self) -> bool:
        return (self.reader.read_input_readiness().ready and not self._start_menu_visible()
                and not self._dialogue_blocked())

    def _dialogue_blocked(self) -> bool:
        return self.settle_dialogue and bool(
            getattr(self.reader, "read_bottom_dialogue_box_visible", lambda: False)()
        )

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
    source_species_numbers: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id:
            raise RedGoalSkillError("encounter-discovery source identity is absent")
        for name in ("maximum_seek_steps", "maximum_encounters"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:  # noqa: E721
                raise ValueError(f"{name} must be a positive integer")
        if self.boundary is not None and not callable(self.boundary):
            raise RedGoalSkillError("encounter-discovery boundary must be callable")
        if self.source_species_numbers is not None and (
            not isinstance(self.source_species_numbers, tuple)
            or not self.source_species_numbers
            or any(
                type(number) is not int or not 1 <= number <= 151
                for number in self.source_species_numbers
            )
            or self.source_species_numbers != tuple(sorted(set(self.source_species_numbers)))
        ):
            raise RedGoalSkillError("encounter-discovery local species are invalid")

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        def boundary(current: RedGoalObservation) -> RedGoalSkillAvailability:
            if current.raw.battle_state or not current.input_ready:
                return RedGoalSkillAvailability.unavailable(
                    GoalUnavailableReason.TEMPORARILY_BLOCKED
                )
            if current.evidence.world_knowledge.satisfaction >= 1.0:
                return RedGoalSkillAvailability.unavailable(GoalUnavailableReason.NO_LEGAL_TARGET)
            if self.source_species_numbers is not None and set(
                self.source_species_numbers
            ).issubset(current.collection.pokedex.seen_target_numbers):
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

            def exhausted(reason: str) -> GoalExecutionReport:
                return GoalExecutionReport(
                    actions_executed=self.actions.actions_executed - before_actions,
                    frames_executed=self.emulator.frame_count - before_frames,
                    evidence={
                        "bounded": True,
                        "encounters_seen": encounters,
                        "new_sighting_count": 0,
                        "captures": 0,
                        "search_exhausted": True,
                        "search_stop_reason": reason,
                    },
                )

            for _ in range(self.maximum_seek_steps):
                encountered = self.area_executor.encountered_species_ref()
                if encountered is None:
                    try:
                        self.area_executor.seek_encounter()
                    except RedAreaExecutionError as error:
                        if (
                            error.reason_code != "survey_leg_limit_exceeded"
                            or self.area_executor.encountered_species_ref() is not None
                        ):
                            raise
                        return exhausted(error.reason_code)
                    encountered = self.area_executor.encountered_species_ref()
                    if encountered is None:
                        continue
                encounters += 1
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
                if encounters >= self.maximum_encounters:
                    return exhausted("encounter_limit_reached")
            return exhausted("seek_step_limit_reached")

        offer = RedProgressGoalProvider(
            kind=self.kind,
            binding_ref=f"pokemon.red:explore:{self.source_id}",
            adapter=self.adapter,
            boundary=boundary,
            executor=execute,
            estimated_effort=min(1.0, self.maximum_encounters / 500),
            estimated_risk=0.10,
        ).offer(observation)
        if offer.binding is None:
            return offer
        binding = offer.binding

        def verify(report: GoalExecutionReport) -> GoalVerification:
            verdict = binding.verify(report)
            if report.evidence.get("search_exhausted") is not True:
                return verdict
            after = self.adapter.observe()
            if (
                verdict.status is GoalDecisionOutcome.FAILED
                and verdict.failure_reason is GoalFailureReason.OUTCOME_NOT_VERIFIED
                and report.evidence.get("bounded") is True
                and type(report.evidence.get("new_sighting_count")) is int
                and report.evidence["new_sighting_count"] == 0
                and type(report.evidence.get("captures")) is int
                and report.evidence["captures"] == 0
                and report.evidence.get("search_stop_reason") in {
                    "survey_leg_limit_exceeded",
                    "encounter_limit_reached",
                    "seek_step_limit_reached",
                }
                and report.actions_executed > 0
                and report.frames_executed > 0
                and not after.raw.battle_state
                and after.input_ready
                and not after.party.fainted_count
                and frozenset(after.collection.pokedex.seen_target_numbers) == initially_seen
            ):
                return GoalVerification.failed(GoalFailureReason.SEARCH_EXHAUSTED)
            return (
                GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
                if verdict.status is GoalDecisionOutcome.SUCCEEDED else verdict
            )

        return replace(offer, binding=replace(binding, verify=verify))


@dataclass(frozen=True, slots=True)
class RedAreaSurveyGoalProvider:
    """Expose one bounded encounter-source survey as species acquisition."""

    source_id: str
    area_executor: RedAreaExecutor
    actions: CountingExecutor
    emulator: RedGoalSkillEmulator
    adapter: PokemonRedGoalStateAdapter
    boundary: GoalAvailabilityCheck | None = None
    normalize_after_capture: Callable[[], None] | None = None
    policy: RedAreaExecutionPolicy = RedAreaExecutionPolicy()
    catalog: RedAcquisitionCatalog = RED_ACQUISITION_CATALOG
    kind: GoalKind = GoalKind.ACQUIRE_SPECIES
    required_capture_items: tuple[ItemId, ...] = ()
    search_effort_surcharge: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id:
            raise RedGoalSkillError("area-survey source identity is absent")
        if self.boundary is not None and not callable(self.boundary):
            raise RedGoalSkillError("area-survey boundary must be callable")
        if self.normalize_after_capture is not None and not callable(self.normalize_after_capture):
            raise RedGoalSkillError("area-survey normalizer must be callable")
        if (
            type(self.search_effort_surcharge) not in (int, float)
            or not 0 <= self.search_effort_surcharge <= 1
        ):
            raise RedGoalSkillError("area-survey search effort surcharge is invalid")

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        availability = self.resource_availability(observation)
        if not availability.executable:
            assert availability.unavailable_reason is not None
            return RedGoalBindingOffer.unavailable(self.kind, availability.unavailable_reason)
        return self._offer_at_source(observation)

    def resource_availability(self, observation: RedGoalObservation) -> RedGoalSkillAvailability:
        """Check source needs and real inventory without inventing a source location."""

        if observation.raw.battle_state or not observation.input_ready:
            return RedGoalSkillAvailability.unavailable(
                GoalUnavailableReason.TEMPORARILY_BLOCKED,
            )
        survey = summarize_red_area_survey(
            self.source_id,
            observation.collection_observation,
            self.catalog,
        )
        if not survey.missing_species_refs:
            return RedGoalSkillAvailability.unavailable(
                GoalUnavailableReason.NO_LEGAL_TARGET,
            )
        inventory = dict(observation.raw.bag_items or ())
        if any(inventory.get(int(item), 0) <= 0 for item in self.required_capture_items):
            return RedGoalSkillAvailability.unavailable(
                GoalUnavailableReason.MISSING_RESOURCE,
            )
        if sum(inventory.get(int(item), 0) for item in _ORDINARY_CAPTURE_ITEMS) <= 0:
            return RedGoalSkillAvailability.unavailable(
                GoalUnavailableReason.MISSING_RESOURCE,
            )
        if observation.immediate_capture_slots <= 0:
            return RedGoalSkillAvailability.unavailable(
                GoalUnavailableReason.STORAGE_BLOCKED,
            )
        return RedGoalSkillAvailability.available()

    def _offer_at_source(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        survey = summarize_red_area_survey(
            self.source_id, observation.collection_observation, self.catalog
        )
        initial_missing_specimens = survey.missing_specimen_count
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

        # Bind the existing native guard to the actual individuals at this
        # source. A no-catch survey may still earn a legal level evolution.
        # Species/count equality alone cannot explain that custody change.
        from .red_player_party_guard import RedPlayerPartyGuard

        guard = getattr(self.adapter, "party_guard", None)
        survey_guard = (
            replace(
                guard, before=guard.reader.read(),
                refs=guard.reader.preparation_specimen_refs(), loanable_refs=frozenset(),
            )
            if isinstance(guard, RedPlayerPartyGuard) else None
        )

        def evolution_census(observed):
            if survey_guard is None:
                return None
            collection = observed.collection_observation
            return {
                "owned_species": sorted(collection.owned_species),
                "specimen_counts": dict(Counter(s.species_ref for s in collection.specimens)),
                "retained_party_continuation": survey_guard.continuation_evidence(
                    collection, include_unreserved_additions=True,
                ),
            }

        before_census = evolution_census(observation)

        def execute() -> GoalExecutionReport:
            from .red_player_lesson_runtime import (
                player_control_diagnostics,
                player_diagnostic_state,
            )

            def observe_diagnostics():
                counters = self.actions.actions_executed, self.emulator.frame_count
                facts = player_diagnostic_state(self.adapter.observe())
                facts.update(native_actions=counters[0], native_frames=counters[1])
                search = getattr(self.area_executor, "search_diagnostics", None)
                facts["search_exposure"] = search() if callable(search) else None
                reader = getattr(self.adapter, "reader", None)
                if reader is not None:
                    facts["control"] = player_control_diagnostics(reader)
                    mode = getattr(reader, "read_overworld_movement_mode", None)
                    facts["movement_mode"] = mode() if callable(mode) else None
                if counters != (self.actions.actions_executed, self.emulator.frame_count):
                    raise RedGoalSkillError("capture diagnostics advanced native execution")
                return facts

            report = run_red_area_survey(
                self.source_id,
                self.area_executor,
                policy=self.policy,
                catalog=self.catalog,
                safety_check=lambda: all(
                    member.hp > 0 for member in self.adapter.observe().party.members
                ),
                capture_resources_available=lambda: any(
                    quantity > 0 and item in _ORDINARY_CAPTURE_ITEMS
                    for item, quantity in (self.adapter.observe().raw.bag_items or ())
                ),
                record_diagnostic_event=getattr(self.actions, "record_diagnostic_event", None),
                observe_diagnostics=observe_diagnostics,
            )
            source_normalized = False
            if not report.safety_stopped and self.normalize_after_capture is not None:
                normalize = bool(report.captures)
                if not normalize and report.capture_items_exhausted:
                    # An unsuccessful last-ball attempt still needs the same
                    # exact source exit. Do not bypass that verifier or send
                    # return-route input into combat/unsettled control.
                    exhausted = self.adapter.observe()
                    normalize = (
                        not exhausted.raw.battle_state
                        and exhausted.input_ready
                        and all(member.hp > 0 for member in exhausted.party.members)
                        and not any(
                            dict(exhausted.raw.bag_items or ()).get(int(item), 0) > 0
                            for item in _ORDINARY_CAPTURE_ITEMS
                        )
                    )
                if normalize:
                    self.normalize_after_capture()
                    source_normalized = True
            final_survey = summarize_red_area_survey(
                self.source_id,
                self.area_executor.read_collection(),
                self.catalog,
            )
            status_reports = tuple(getattr(self.area_executor, "capture_status_reports", ()))
            throw_preparations = tuple(
                getattr(self.area_executor, "capture_throw_preparations", ())
            )
            escape_bypasses = getattr(self.area_executor, "capture_escape_bypasses", 0)
            weakening_reports = tuple(getattr(self.area_executor, "capture_weakening_reports", ()))
            survey_evidence = {
                "semantic_actions": report.actions_executed,
                "encounters_seen": report.encounters_seen,
                "captures": report.captures,
                "flees": report.flees,
                "search_exhausted": report.search_exhausted,
                "safety_stopped": report.safety_stopped,
                **({"capture_items_exhausted": True} if report.capture_items_exhausted else {}),
                **(
                    {"search_stop_reason": report.search_stop_reason}
                    if report.search_stop_reason is not None
                    else {}
                ),
            }
            return GoalExecutionReport(
                actions_executed=self.actions.actions_executed - before_actions,
                frames_executed=self.emulator.frame_count - before_frames,
                evidence={
                    "bounded": True,
                    **survey_evidence,
                    "capture_survey": survey_evidence,
                    "capture_diagnostics": dict(
                        schema="pokemon.red.capture-survey-diagnostics.v1",
                        diagnostic_only=True,
                        flees_includes_failed_capture_attempts=True,
                        direct_flees=report.direct_flees,
                        capture_attempts=report.capture_attempts,
                        failed_capture_attempts=report.failed_capture_attempts,
                        events=list(report.diagnostic_events),
                    ),
                    "source_normalized": source_normalized,
                    "initial_missing": len(report.initial_missing_species_refs),
                    "final_missing": len(report.final_missing_species_refs),
                    "initial_missing_specimens": initial_missing_specimens,
                    "final_missing_specimens": final_survey.missing_specimen_count,
                    **(
                        {"capture_weakening_reports": weakening_reports}
                        if weakening_reports
                        else {}
                    ),
                    **(
                        {"capture_throw_preparations": throw_preparations}
                        if throw_preparations
                        else {}
                    ),
                    **(
                        {
                            "capture_status_reports": status_reports,
                            "capture_support": {
                                "status_attempts": len(status_reports),
                                "verified_status_observations": sum(
                                    row.get("status_success") is True for row in status_reports
                                ),
                                "party_preparations": 0,
                                **(
                                    {
                                        "weakening_attempts": sum(
                                            row["attempts"] for row in weakening_reports
                                        ),
                                        "weakening_hp_removed": sum(
                                            row["damage"] for row in weakening_reports
                                        ),
                                        "weakening_abstentions": sum(
                                            row["attempts"] == 0 for row in weakening_reports
                                        ),
                                    }
                                    if weakening_reports
                                    else {}
                                ),
                                **(
                                    {"escape_setup_bypasses": escape_bypasses}
                                    if escape_bypasses
                                    else {}
                                ),
                                **(
                                    {
                                        "prepared_throws": len(throw_preparations),
                                        "prepared_asleep": sum(
                                            row.get("target_status") == "sleep"
                                            for row in throw_preparations
                                        ),
                                        "prepared_paralyzed": sum(
                                            row.get("target_status") == "paralysis"
                                            for row in throw_preparations
                                        ),
                                        "prepared_full_hp": sum(
                                            type(row.get("target_hp")) is int
                                            and row["target_hp"] == row.get("target_max_hp")
                                            and row["target_hp"] > 0
                                            for row in throw_preparations
                                        ),
                                    }
                                    if throw_preparations
                                    else {}
                                ),
                            },
                        }
                        if status_reports or escape_bypasses or throw_preparations
                        else {}
                    ),
                },
            )

        initial_missing = set(survey.missing_species_refs)
        before_owned = observation.collection.collection.pokedex_owned_count
        before_living = observation.collection.collection.living_count

        def verified_incidental_evolution(after):
            from .red_integrated_play import _retained_evolution_census

            after_census = evolution_census(after)
            return (
                before_census is not None
                and after_census is not None
                and _retained_evolution_census(
                    before_census, after_census, require_exact_owned=True,
                )
            )

        def verify(report: GoalExecutionReport) -> GoalVerification:
            after = self.adapter.observe()
            after_story = self.adapter.graph.completed_ids(after.game_state)
            if before_story.difference(after_story):
                return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            if report.evidence.get("safety_stopped") is True:
                return GoalVerification.failed(
                    GoalFailureReason.RESOURCE_LOST
                    if not after.raw.battle_state
                    and any(member.hp <= 0 for member in after.party.members)
                    else GoalFailureReason.OUTCOME_NOT_VERIFIED
                )
            if self.boundary is not None:
                normalized_boundary = self.boundary(after)
                if not isinstance(normalized_boundary, RedGoalSkillAvailability):
                    raise RedGoalSkillError(
                        "area-survey boundary returned invalid post-capture evidence"
                    )
                if not normalized_boundary.executable:
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
                (
                    report.evidence.get("search_exhausted") is True
                    or (
                        report.evidence.get("capture_items_exhausted") is True
                        and not any(
                            dict(after.raw.bag_items or ()).get(int(item), 0) > 0
                            for item in _ORDINARY_CAPTURE_ITEMS
                        )
                    )
                )
                and type(captures) is int  # noqa: E721
                and captures == 0
                and remaining == initial_missing
                and remaining_specimens == initial_missing_specimens
                and (
                    (
                        after.collection.collection.pokedex_owned_count == before_owned
                        and after.collection.collection.living_count == before_living
                        and after.collection_observation.owned_species
                        == observation.collection_observation.owned_species
                        and Counter(s.species_ref for s in after.collection_observation.specimens)
                        == Counter(
                            s.species_ref for s in observation.collection_observation.specimens
                        )
                    )
                    or verified_incidental_evolution(after)
                )
                and report.actions_executed > 0
                and not after.raw.battle_state
                and after.input_ready
                and all(member.hp > 0 for member in after.party.members)
                and report.evidence.get("initial_missing_specimens") == initial_missing_specimens
                and report.evidence.get("final_missing_specimens") == remaining_specimens
            ):
                return GoalVerification.failed(
                    GoalFailureReason.CAPTURE_ITEMS_EXHAUSTED
                    if not any(
                        dict(after.raw.bag_items or ()).get(int(item), 0) > 0
                        for item in _ORDINARY_CAPTURE_ITEMS
                    )
                    else GoalFailureReason.SEARCH_EXHAUSTED
                )
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
                estimated_effort=min(
                    1.0,
                    0.12 * len(survey.missing_species_refs) + self.search_effort_surcharge,
                ),
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


def _raw_party_fully_restored(raw: RawGameState) -> bool:
    """Strict whole-party HP/status/PP, including packed PP Up capacities."""
    from .red_party_pp import RedPartyPpError, decode_red_party_pp

    try:
        if not _raw_party_restored(raw):
            return False
        if raw.party_moves is None or raw.party_pp is None:
            return False
        return all(
            all(slot.current_pp == slot.maximum_pp for slot in decode_red_party_pp(moves, pp).moves)
            for moves, pp in zip(raw.party_moves, raw.party_pp, strict=True)
        )
    except (ValueError, TypeError, RedPartyPpError):
        return False
