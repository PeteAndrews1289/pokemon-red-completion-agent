"""Reusable Red fossil revival behind one semantic acquisition goal.

The high-level policy chooses ``acquire_species``.  This adapter derives the
available fossil from observed inventory, uses cartridge routing to reach the
laboratory, and proves the resulting Pokédex registration independently.  It
does not encode a route for Omanyte, Kabuto, or Aerodactyl individually.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from functools import partial
from typing import Protocol, cast

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_field_moves import Gen1FieldMovePort, fly_menu_indices
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.observation import (
    CurrentMapObject,
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RawGameState,
    ReadOnlyMemory,
    RedCurrentBoxState,
    RedPokedexState,
    event_flag_is_set,
)
from pokemon_red_completion.red_collection import (
    red_internal_species_id,
    red_species_ref,
)
from pokemon_red_completion.red_collection_fly import red_fly_landings
from pokemon_red_completion.red_goal_manager import (
    PokemonRedGoalStateAdapter,
    RedGoalObservation,
)
from pokemon_red_completion.red_resource_goal_router import (
    _supported_plan,
    collection_field_capabilities,
)
from pokemon_red_completion.route_executor import (
    DEFAULT_ROUTE_EXECUTION_LIMITS,
    RouteExecutionLimits,
    execute_route,
)
from pokemon_red_completion.route_plan import RoutePlanningError
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
)

CINNABAR_FOSSIL_SCIENTIST_YX = (3, 5)
CINNABAR_ISLAND_MAP_ID = int(MapId.CINNABAR_ISLAND)
FOSSIL_ROOM_MAP_ID = int(MapId.CINNABAR_LAB_FOSSIL_ROOM)
FOSSIL_SCIENTIST_SPRITE_INDEX = 1
FOSSIL_SCIENTIST_PICTURE_ID = 0x20
FOSSIL_REVIVAL_LEVEL = 30
FOSSIL_ITEMS = frozenset(
    {int(ItemId.DOME_FOSSIL), int(ItemId.HELIX_FOSSIL), int(ItemId.OLD_AMBER)}
)


class RedFossilAcquisitionError(RuntimeError):
    """A fossil goal lost a prerequisite or failed its observed transition."""


class RedFossilPhase(StrEnum):
    READY_TO_SUBMIT = "ready_to_submit"
    WAITING_FOR_OUTSIDE = "waiting_for_outside"
    READY_TO_COLLECT = "ready_to_collect"
    COMPLETE = "complete"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class RedFossilTarget:
    """One cartridge mechanic parameter, independent of route or policy row."""

    item_id: ItemId
    national_dex_number: int
    internal_species_id: int

    def __post_init__(self) -> None:
        if self.item_id not in {ItemId.DOME_FOSSIL, ItemId.HELIX_FOSSIL, ItemId.OLD_AMBER}:
            raise ValueError("fossil target needs a fossil item")
        if self.internal_species_id != red_internal_species_id(self.national_dex_number):
            raise ValueError("fossil target internal and National species identities differ")

    @property
    def species_ref(self) -> str:
        return red_species_ref(self.national_dex_number)

    @property
    def source_ref(self) -> str:
        return f"pokemon.red:fossil-revival:{int(self.item_id):02x}"


RED_FOSSIL_TARGETS = (
    RedFossilTarget(ItemId.DOME_FOSSIL, 140, red_internal_species_id(140)),
    RedFossilTarget(ItemId.HELIX_FOSSIL, 138, red_internal_species_id(138)),
    RedFossilTarget(ItemId.OLD_AMBER, 142, red_internal_species_id(142)),
)


def _adjacent_facing(
    player_at: tuple[int, int],
    target_at: tuple[int, int],
) -> str | None:
    delta = target_at[0] - player_at[0], target_at[1] - player_at[1]
    return {
        (-1, 0): "up",
        (1, 0): "down",
        (0, -1): "left",
        (0, 1): "right",
    }.get(delta)


class RedFossilStateReader(Protocol):
    def read(self) -> RawGameState: ...

    def read_pokedex_state(self) -> RedPokedexState: ...

    def read_current_box_state(self) -> RedCurrentBoxState: ...

    def read_fossil_reviver_identity(self) -> tuple[int, int]: ...

    def read_input_readiness(self) -> object: ...

    def read_bottom_dialogue_box_visible(self) -> bool: ...

    def read_player_facing(self) -> str: ...

    def read_current_map_objects(self) -> tuple[CurrentMapObject, ...]: ...


@dataclass(frozen=True, slots=True)
class RedFossilObservation:
    target: RedFossilTarget
    phase: RedFossilPhase
    map_id: int
    player_yx: tuple[int, int]
    item_quantity: int
    pending_item_id: int
    pending_internal_species_id: int
    registered: bool
    party_size: int
    current_box_size: int
    input_ready: bool
    in_battle: bool

    @property
    def has_immediate_storage(self) -> bool:
        return self.party_size < 6 or self.current_box_size < 20

    @property
    def executable(self) -> bool:
        return (
            self.phase
            in {
                RedFossilPhase.READY_TO_SUBMIT,
                RedFossilPhase.WAITING_FOR_OUTSIDE,
                RedFossilPhase.READY_TO_COLLECT,
            }
            and self.has_immediate_storage
            and self.input_ready
            and not self.in_battle
        )


def observe_red_fossil(
    reader: RedFossilStateReader,
    target: RedFossilTarget,
) -> RedFossilObservation:
    """Read the complete fossil boundary without controller input or inference."""

    raw = reader.read()
    if (
        not raw.game_started
        or raw.map_id is None
        or raw.player_x is None
        or raw.player_y is None
        or raw.party_count is None
        or raw.battle_state is None
        or raw.event_flags is None
    ):
        raise RedFossilAcquisitionError("fossil observation is incomplete")
    inventory = dict(raw.bag_items or ())
    quantity = inventory.get(int(target.item_id), 0)
    owned = target.national_dex_number in reader.read_pokedex_state().owned_species
    pending_item, pending_species = reader.read_fossil_reviver_identity()
    gave = event_flag_is_set(raw.event_flags, int(EventFlag.GAVE_FOSSIL_TO_LAB))
    waiting = event_flag_is_set(
        raw.event_flags,
        int(EventFlag.LAB_STILL_REVIVING_FOSSIL),
    )
    handing = event_flag_is_set(
        raw.event_flags,
        int(EventFlag.LAB_HANDING_OVER_FOSSIL_MON),
    )
    pending_matches = (
        pending_item == int(target.item_id)
        and pending_species == target.internal_species_id
    )
    if owned:
        phase = RedFossilPhase.COMPLETE
    elif gave and pending_matches and waiting:
        phase = RedFossilPhase.WAITING_FOR_OUTSIDE
    elif gave and pending_matches and not waiting and not handing:
        phase = RedFossilPhase.READY_TO_COLLECT
    elif (
        not gave
        and not waiting
        and not handing
        and quantity == 1
        and sum(inventory.get(item, 0) for item in FOSSIL_ITEMS) == 1
    ):
        phase = RedFossilPhase.READY_TO_SUBMIT
    else:
        phase = RedFossilPhase.UNAVAILABLE
    return RedFossilObservation(
        target=target,
        phase=phase,
        map_id=raw.map_id,
        player_yx=(raw.player_y, raw.player_x),
        item_quantity=quantity,
        pending_item_id=pending_item,
        pending_internal_species_id=pending_species,
        registered=owned,
        party_size=raw.party_count,
        current_box_size=len(reader.read_current_box_state().species_ids),
        input_ready=bool(getattr(reader.read_input_readiness(), "ready", False)),
        in_battle=bool(raw.battle_state),
    )


def available_red_fossil_targets(
    reader: RedFossilStateReader,
) -> tuple[RedFossilTarget, ...]:
    """Enumerate executable item-derived targets; this function is action-free."""

    return tuple(
        target
        for target in RED_FOSSIL_TARGETS
        if observe_red_fossil(reader, target).executable
    )


@dataclass(frozen=True, slots=True)
class RedFossilTiming:
    wait_frames: int = 180
    npc_poll_frames: int = 30
    maximum_dialogue_pulses: int = 20
    maximum_npc_replans: int = 12
    maximum_controller_actions: int = 512
    maximum_emulator_frames: int = 180_000

    def __post_init__(self) -> None:
        for name in (
            "wait_frames",
            "npc_poll_frames",
            "maximum_dialogue_pulses",
            "maximum_npc_replans",
            "maximum_controller_actions",
            "maximum_emulator_frames",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:  # noqa: E721
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_FOSSIL_TIMING = RedFossilTiming()


@dataclass(frozen=True, slots=True)
class RedFossilExecution:
    target: RedFossilTarget
    initial: RedFossilObservation
    final: RedFossilObservation
    actions_executed: int
    frames_executed: int
    fly_used: bool
    route_steps: int
    refresh_steps: int

    @property
    def passed(self) -> bool:
        item_transition = (
            self.initial.item_quantity == 1 and self.final.item_quantity == 0
            if self.initial.phase is RedFossilPhase.READY_TO_SUBMIT
            else self.initial.item_quantity == self.final.item_quantity == 0
        )
        return (
            self.initial.phase
            in {
                RedFossilPhase.READY_TO_SUBMIT,
                RedFossilPhase.WAITING_FOR_OUTSIDE,
                RedFossilPhase.READY_TO_COLLECT,
            }
            and self.final.phase is RedFossilPhase.COMPLETE
            and item_transition
            and self.final.registered
            and self.actions_executed > 0
            and self.frames_executed > 0
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.fossil-acquisition.v1",
            "source_kind": "fossil",
            "national_dex_number": self.target.national_dex_number,
            "revival_level": FOSSIL_REVIVAL_LEVEL,
            "initial_phase": self.initial.phase.value,
            "final_phase": self.final.phase.value,
            "item_consumed": self.initial.item_quantity - self.final.item_quantity == 1,
            "item_previously_committed": self.initial.item_quantity == 0,
            "registration_added": not self.initial.registered and self.final.registered,
            "fly_used": self.fly_used,
            "route_steps": self.route_steps,
            "refresh_steps": self.refresh_steps,
            "actions_executed": self.actions_executed,
            "frames_executed": self.frames_executed,
            "species_specific_route_steps": 0,
        }


@dataclass(slots=True)
class RedRoutedFossilRevival:
    """Execute the common lab protocol from a live, qualified Red boundary."""

    actions: CountingExecutor
    reader: PokemonRedStateReader
    emulator: object
    world: StrategicScenarioRouteWorld
    timing: RedFossilTiming = DEFAULT_FOSSIL_TIMING
    route_limits: RouteExecutionLimits = DEFAULT_ROUTE_EXECUTION_LIMITS

    def execute(self, target: RedFossilTarget) -> RedFossilExecution:
        before_actions = self.actions.actions_executed
        before_frames = self._frame_count()
        initial = observe_red_fossil(self.reader, target)
        if not initial.executable:
            raise RedFossilAcquisitionError("fossil target is not executable")
        field_actions, observer = self._ports()
        fly_used = self._reach_cinnabar(field_actions, observer)
        route_steps = self._route(
            field_actions,
            observer,
            FOSSIL_ROOM_MAP_ID,
        )
        current = observe_red_fossil(self.reader, target)
        if current.phase is RedFossilPhase.READY_TO_SUBMIT:
            route_steps += self._advance_scientist_until(
                field_actions,
                observer,
                target,
                RedFossilPhase.WAITING_FOR_OUTSIDE,
            )
            self._settle_dialogue()
            current = observe_red_fossil(self.reader, target)
        refresh_steps = 0
        if current.phase is RedFossilPhase.WAITING_FOR_OUTSIDE:
            refresh_steps += self._route(field_actions, observer, CINNABAR_ISLAND_MAP_ID)
            outside = observe_red_fossil(self.reader, target)
            if outside.phase is not RedFossilPhase.READY_TO_COLLECT:
                raise RedFossilAcquisitionError("leaving the lab did not finish revival")
            refresh_steps += self._route(
                field_actions,
                observer,
                FOSSIL_ROOM_MAP_ID,
            )
            current = observe_red_fossil(self.reader, target)
        if current.phase is RedFossilPhase.READY_TO_COLLECT:
            refresh_steps += self._advance_scientist_until(
                field_actions,
                observer,
                target,
                RedFossilPhase.COMPLETE,
            )
            self._settle_dialogue()
        final = observe_red_fossil(self.reader, target)
        result = RedFossilExecution(
            target=target,
            initial=initial,
            final=final,
            actions_executed=self.actions.actions_executed - before_actions,
            frames_executed=self._frame_count() - before_frames,
            fly_used=fly_used,
            route_steps=route_steps,
            refresh_steps=refresh_steps,
        )
        if not result.passed:
            raise RedFossilAcquisitionError("fossil execution lacked its exact transition")
        self._check_budget(before_actions, before_frames)
        return result

    def _ports(self) -> tuple[Gen1FieldMovePort, Gen1TraversalObserver]:
        field_actions = Gen1FieldMovePort(
            self.actions,
            self.reader,
            self.emulator,  # type: ignore[arg-type]
            cut_block_swaps={
                swap.before: swap.after for swap in self.world.rules.cut_block_swaps
            },
        )
        observer = Gen1TraversalObserver(
            self.reader,
            capability_projector=partial(
                collection_field_capabilities,
                cast(ReadOnlyMemory, self.emulator),
                allow_cut=True,
                allow_surf=True,
            ),
        )
        return field_actions, observer

    def _reach_cinnabar(
        self,
        actions: Gen1FieldMovePort,
        observer: Gen1TraversalObserver,
    ) -> bool:
        start = observer.observe()
        if start.map_id in {
            CINNABAR_ISLAND_MAP_ID,
            int(MapId.CINNABAR_LAB),
            FOSSIL_ROOM_MAP_ID,
        }:
            return False
        raw = self.reader.read()
        if (
            not 0 <= start.map_id <= int(MapId.ROUTE_25)
            or start.map_id == 0x0B
            or CINNABAR_ISLAND_MAP_ID not in self.reader.read_fly_destinations()
        ):
            raise RedFossilAcquisitionError("fossil transport needs outdoor Cinnabar Fly access")
        fly_menu_indices(raw)
        actions.execute(MacroAction(MacroActionKind.FIELD_MOVE, "fly:cinnabar_island"))
        expected = dict(red_fly_landings(self.world.rom))[CINNABAR_ISLAND_MAP_ID]
        landed = observer.observe()
        if (
            landed.map_id != CINNABAR_ISLAND_MAP_ID
            or landed.at != expected
            or not landed.ready
        ):
            raise RedFossilAcquisitionError("Cinnabar Fly landing was not verified")
        return True

    def _route(
        self,
        actions: Gen1FieldMovePort,
        observer: Gen1TraversalObserver,
        destination_map: int,
        *,
        goal_at: tuple[int, int] | None = None,
    ) -> int:
        start = observer.observe()
        if start.map_id == destination_map and (goal_at is None or start.at == goal_at):
            return 0
        try:
            plan = self.world.plan_feasible_to_map(start, destination_map, goal_at=goal_at)
        except RoutePlanningError as error:
            self._recover_to_routable_neighbor(
                actions,
                observer,
                destination_map,
                goal_at=goal_at,
                original_error=error,
            )
            start = observer.observe()
            try:
                plan = self.world.plan_feasible_to_map(
                    start,
                    destination_map,
                    goal_at=goal_at,
                )
            except RoutePlanningError as retry_error:
                raise RedFossilAcquisitionError(
                    "no cartridge route reaches the fossil boundary"
                ) from retry_error
        if not _supported_plan(plan, allow_cut=True, allow_surf=True):
            raise RedFossilAcquisitionError("fossil route needs an unsupported field mechanic")
        report = execute_route(
            plan,
            actions,
            observer,
            replanner=self.world.replanner(),
            limits=self.route_limits,
        )
        if not report.passed:
            raise RedFossilAcquisitionError("fossil route did not reach its declared boundary")
        return len(report.executed_steps)

    def _recover_to_routable_neighbor(
        self,
        actions: Gen1FieldMovePort,
        observer: Gen1TraversalObserver,
        destination_map: int,
        *,
        goal_at: tuple[int, int] | None,
        original_error: RoutePlanningError,
    ) -> None:
        """Leave one transient off-graph square using a verified local move."""

        current = observer.observe()
        if not current.ready:
            raise RedFossilAcquisitionError(
                "no cartridge route reaches the fossil boundary"
            ) from original_error
        directions = (
            ("down", (1, 0)),
            ("up", (-1, 0)),
            ("right", (0, 1)),
            ("left", (0, -1)),
        )
        candidates = []
        for order, (direction, (delta_y, delta_x)) in enumerate(directions):
            candidate = (current.at[0] + delta_y, current.at[1] + delta_x)
            if candidate in current.occupied:
                continue
            projected = replace(current, at=candidate)
            try:
                plan = self.world.plan_feasible_to_map(
                    projected,
                    destination_map,
                    goal_at=goal_at,
                )
            except RoutePlanningError:
                continue
            if _supported_plan(plan, allow_cut=True, allow_surf=True):
                candidates.append((plan.cost, len(plan.steps), order, direction, candidate))
        if not candidates:
            raise RedFossilAcquisitionError(
                "no cartridge route reaches the fossil boundary"
            ) from original_error
        _, _, _, direction, expected = min(candidates, key=lambda row: row[:3])
        actions.execute(MacroAction(MacroActionKind.MOVE, direction))
        settled = observer.observe()
        if (
            settled.map_id != current.map_id
            or settled.at != expected
            or not settled.ready
        ):
            raise RedFossilAcquisitionError(
                "local fossil route recovery did not reach its predicted tile"
            ) from original_error

    def _scientist(self) -> CurrentMapObject:
        matches = tuple(
            item
            for item in self.reader.read_current_map_objects()
            if item.sprite_index == FOSSIL_SCIENTIST_SPRITE_INDEX
            and item.picture_id == FOSSIL_SCIENTIST_PICTURE_ID
        )
        # ``CurrentMapObject`` is map-wide: image_index 0xFF means merely that
        # the object is outside the current viewport, not that the object is
        # absent.  Its toggle-present identity and coordinates remain valid
        # inputs to cartridge routing.
        if len(matches) != 1:
            raise RedFossilAcquisitionError("fossil scientist is not uniquely present")
        return matches[0]

    def _route_to_scientist(
        self,
        actions: Gen1FieldMovePort,
        observer: Gen1TraversalObserver,
        scientist_at: tuple[int, int],
    ) -> int | None:
        current = observer.observe()
        candidates = (
            (scientist_at[0] + 1, scientist_at[1]),
            (scientist_at[0], scientist_at[1] - 1),
            (scientist_at[0], scientist_at[1] + 1),
            (scientist_at[0] - 1, scientist_at[1]),
        )
        plans = []
        for order, candidate in enumerate(candidates):
            if candidate in current.occupied:
                continue
            try:
                plan = self.world.plan_feasible_to_map(
                    current,
                    FOSSIL_ROOM_MAP_ID,
                    goal_at=candidate,
                )
            except RoutePlanningError:
                continue
            if _supported_plan(plan, allow_cut=True, allow_surf=True):
                plans.append((plan.cost, len(plan.steps), order, plan))
        if not plans:
            return None
        plan = min(plans, key=lambda row: row[:3])[3]
        report = execute_route(
            plan,
            actions,
            observer,
            replanner=self.world.replanner(),
            limits=self.route_limits,
        )
        if not report.passed:
            raise RedFossilAcquisitionError("live scientist approach did not settle")
        return len(report.executed_steps)

    def _position_and_face_scientist(
        self,
        actions: Gen1FieldMovePort,
        observer: Gen1TraversalObserver,
    ) -> int:
        route_steps = 0
        for _ in range(self.timing.maximum_npc_replans):
            raw = self.reader.read()
            if (
                raw.map_id != FOSSIL_ROOM_MAP_ID
                or raw.player_y is None
                or raw.player_x is None
                or raw.battle_state
                or not bool(getattr(self.reader.read_input_readiness(), "ready", False))
            ):
                raise RedFossilAcquisitionError("scientist interaction boundary differs")
            player = (raw.player_y, raw.player_x)
            scientist = self._scientist()
            facing = _adjacent_facing(player, scientist.at)
            if facing is None:
                approached = self._route_to_scientist(actions, observer, scientist.at)
                if approached is None:
                    # The scientist roams horizontally behind a counter.  Some
                    # live positions have no standable adjacent tile, so wait
                    # for a bounded poll interval instead of inventing a route
                    # through furniture or treating normal NPC motion as fatal.
                    self.actions.execute(
                        MacroAction(
                            MacroActionKind.WAIT,
                            repeat=self.timing.npc_poll_frames,
                        )
                    )
                    continue
                route_steps += approached
                continue
            if self.reader.read_player_facing() != facing:
                # Do not use ``_pulse`` here: its dialogue settle wait gives a
                # roaming NPC time to leave the interaction boundary between
                # the facing input and the immediately following A press.
                self.actions.execute(MacroAction(MacroActionKind.MOVE, facing))
                after = self.reader.read()
                if (
                    after.map_id != FOSSIL_ROOM_MAP_ID
                    or after.player_y is None
                    or after.player_x is None
                    or after.battle_state
                ):
                    raise RedFossilAcquisitionError("scientist-facing input left the boundary")
                # The scientist may move between observation and input. Moving
                # into the vacated tile is a recoverable race, not proof that
                # the route or mechanic failed.
                if (after.player_y, after.player_x) != player:
                    continue
            latest = self.reader.read()
            if latest.player_y is None or latest.player_x is None:
                raise RedFossilAcquisitionError("scientist-facing position is unavailable")
            latest_facing = _adjacent_facing(
                (latest.player_y, latest.player_x),
                self._scientist().at,
            )
            if latest_facing is not None and self.reader.read_player_facing() == latest_facing:
                return route_steps
        raise RedFossilAcquisitionError("fossil scientist did not hold an interaction boundary")

    def _advance_scientist_until(
        self,
        actions: Gen1FieldMovePort,
        observer: Gen1TraversalObserver,
        target: RedFossilTarget,
        phase: RedFossilPhase,
    ) -> int:
        route_steps = 0
        for _ in range(self.timing.maximum_npc_replans):
            route_steps += self._position_and_face_scientist(actions, observer)
            self._pulse(MacroActionKind.INTERACT)
            dialogue_started = False
            for _ in range(self.timing.maximum_dialogue_pulses):
                if self.reader.read_bottom_dialogue_box_visible():
                    # Fossil handover writes the box's species index before it
                    # asks about a nickname and only then shifts/writes the full
                    # Pokémon structures.  Once the target's Pokédex bit is set,
                    # B both declines that two-option prompt and avoids entering
                    # the naming screen.  Reading collection state before that
                    # transition completes would observe legitimate non-atomic
                    # RAM, not a corrupt box.
                    dialogue_started = True
                    owned = target.national_dex_number in (
                        self.reader.read_pokedex_state().owned_species
                    )
                    self._pulse(
                        MacroActionKind.CANCEL if owned else MacroActionKind.CONFIRM
                    )
                    continue
                if observe_red_fossil(self.reader, target).phase is phase:
                    return route_steps
                if dialogue_started:
                    raise RedFossilAcquisitionError(
                        f"fossil dialogue ended before {phase.value}"
                    )
                break
        raise RedFossilAcquisitionError(f"fossil dialogue did not reach {phase.value}")

    def _settle_dialogue(self) -> None:
        for _ in range(self.timing.maximum_dialogue_pulses + 1):
            ready = bool(getattr(self.reader.read_input_readiness(), "ready", False))
            if ready and not self.reader.read_bottom_dialogue_box_visible():
                return
            self._pulse(MacroActionKind.CONFIRM)
        raise RedFossilAcquisitionError("fossil dialogue did not return field control")

    def _pulse(self, kind: MacroActionKind, value: str | None = None) -> None:
        self.actions.execute(MacroAction(kind, value))
        self.actions.execute(MacroAction(MacroActionKind.WAIT, repeat=self.timing.wait_frames))

    def _frame_count(self) -> int:
        value = getattr(self.emulator, "frame_count", None)
        if type(value) is not int or value < 0:  # noqa: E721
            raise RedFossilAcquisitionError("fossil emulator frame count is invalid")
        return value

    def _check_budget(self, before_actions: int, before_frames: int) -> None:
        if (
            self.actions.actions_executed - before_actions > self.timing.maximum_controller_actions
            or self._frame_count() - before_frames > self.timing.maximum_emulator_frames
        ):
            raise RedFossilAcquisitionError("fossil execution exceeded its declared budget")


@dataclass(frozen=True, slots=True)
class RedFossilGoalProvider:
    """Bind one observed fossil target to the existing acquisition policy kind."""

    target: RedFossilTarget
    adapter: PokemonRedGoalStateAdapter
    reader: RedFossilStateReader
    executor: RedRoutedFossilRevival
    estimated_effort: float = 0.24
    estimated_risk: float = 0.08

    def binding(self, observation: RedGoalObservation) -> ExecutableGoalBinding | None:
        before = observe_red_fossil(self.reader, self.target)
        if (
            not before.executable
            or self.target.species_ref in observation.collection_observation.owned_species
        ):
            return None
        registered_before = observation.collection_observation.owned_species
        living_before = frozenset(
            specimen.species_ref for specimen in observation.collection_observation.specimens
        )

        def execute() -> GoalExecutionReport:
            result = self.executor.execute(self.target)
            return GoalExecutionReport(
                result.actions_executed,
                result.frames_executed,
                result.public_dict(),
            )

        def verify(report: GoalExecutionReport) -> GoalVerification:
            after = self.adapter.observe()
            fossil_after = observe_red_fossil(self.reader, self.target)
            living_after = frozenset(
                specimen.species_ref for specimen in after.collection_observation.specimens
            )
            if (
                not registered_before <= after.collection_observation.owned_species
                or not living_before <= living_after
            ):
                return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            if (
                report.actions_executed <= 0
                or fossil_after.phase is not RedFossilPhase.COMPLETE
                or self.target.species_ref not in after.collection_observation.owned_species
                or self.target.species_ref not in living_after
                or after.raw.battle_state
                or not after.input_ready
            ):
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            return GoalVerification.succeeded()

        return ExecutableGoalBinding(
            binding_ref=f"red-fossil:{self.target.source_ref}",
            kind=GoalKind.ACQUIRE_SPECIES,
            estimated_effort=self.estimated_effort,
            estimated_risk=self.estimated_risk,
            execute=execute,
            verify=verify,
            search_source_ref=self.target.source_ref,
        )


def fossil_target_by_item(item_id: int) -> RedFossilTarget:
    """Resolve an observed fossil item without species-specific caller logic."""

    by_item: Mapping[int, RedFossilTarget] = {
        int(target.item_id): target for target in RED_FOSSIL_TARGETS
    }
    try:
        return by_item[item_id]
    except KeyError:
        raise RedFossilAcquisitionError("unsupported fossil item") from None


def bind_available_fossil_acquisition(
    binding_set: GoalBindingSet,
    binding: ExecutableGoalBinding | None,
) -> GoalBindingSet:
    """Replace only a masked acquisition slot with one observed fossil skill.

    An already executable capture remains authoritative. Destination selection
    belongs below the high-level goal model, so this helper never creates two
    ``acquire_species`` candidates in the same policy menu.
    """

    if binding is None:
        return binding_set
    indices = tuple(
        index
        for index, opportunity in enumerate(binding_set.opportunities)
        if opportunity.kind is GoalKind.ACQUIRE_SPECIES
    )
    if len(indices) != 1:
        raise RedFossilAcquisitionError("goal menu lacks one acquisition slot")
    index = indices[0]
    existing = binding_set.opportunities[index]
    if existing.availability.value == "available":
        return binding_set
    opportunities = list(binding_set.opportunities)
    opportunities[index] = binding.opportunity
    bindings = tuple(
        row for row in binding_set.bindings if row.kind is not GoalKind.ACQUIRE_SPECIES
    ) + (binding,)
    return GoalBindingSet(
        tuple(opportunities),
        bindings,
        allow_resource_variants=binding_set.allow_resource_variants,
    )
