"""Bounded fishing-candidate foundation for Generation I planning.

Provides strict mapping from observed bag entries to available :class:`RodKind`
values without inventing ownership, and derives deterministic fishable shoreline
stances from :class:`Terrain`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.gen1_cartridge import RodKind
from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.gen1_traversal import Direction
from pokemon_red_completion.observation import (
    InputReadiness,
    ItemId,
    MenuCursorState,
    RawGameState,
)

#: Mapping from rod ItemId to RodKind.
ROD_ITEM_TO_KIND: Mapping[int, RodKind] = {
    ItemId.OLD_ROD: RodKind.OLD,
    ItemId.GOOD_ROD: RodKind.GOOD,
    ItemId.SUPER_ROD: RodKind.SUPER,
}

#: Reverse mapping from RodKind to ItemId.
ROD_KIND_TO_ITEM: Mapping[RodKind, ItemId] = {
    RodKind.OLD: ItemId.OLD_ROD,
    RodKind.GOOD: ItemId.GOOD_ROD,
    RodKind.SUPER: ItemId.SUPER_ROD,
}

_ROD_ORDER: tuple[RodKind, ...] = (
    RodKind.OLD,
    RodKind.GOOD,
    RodKind.SUPER,
)

_CANONICAL_DIRECTIONS: tuple[Direction, ...] = (
    Direction.DOWN,
    Direction.UP,
    Direction.LEFT,
    Direction.RIGHT,
)


def rod_kind_for_item(item_id: int | ItemId) -> RodKind | None:
    """Return the :class:`RodKind` corresponding to a rod item ID, or None."""
    if not isinstance(item_id, int) or isinstance(item_id, bool):
        raise TypeError(f"item_id must be an integer, got {item_id!r}")
    return ROD_ITEM_TO_KIND.get(int(item_id))


def item_for_rod_kind(rod_kind: RodKind) -> ItemId:
    """Return the :class:`ItemId` corresponding to a :class:`RodKind`."""
    if not isinstance(rod_kind, RodKind):
        raise TypeError(f"rod_kind must be a RodKind instance, got {rod_kind!r}")
    return ROD_KIND_TO_ITEM[rod_kind]


def available_rod_kinds(
    bag_entries: (
        RawGameState
        | Mapping[Any, int]
        | Iterable[tuple[int | ItemId, int]]
        | None
    ),
) -> tuple[RodKind, ...]:
    """Map observed bag entries to available :class:`RodKind` values.

    Ownership is never invented: missing, empty, or zero-quantity entries
    mean no rod is available. Malformed entries raise TypeError or ValueError.

    Returns available rods in canonical order: (OLD, GOOD, SUPER).
    """
    if bag_entries is None:
        return ()

    if isinstance(bag_entries, RawGameState):
        if bag_entries.bag_items is None:
            return ()
        raw_entries: Iterable[Any] = bag_entries.bag_items
    elif isinstance(bag_entries, Mapping):
        raw_entries = bag_entries.items()
    elif isinstance(bag_entries, Iterable):
        raw_entries = bag_entries
    else:
        raise TypeError(
            f"bag_entries must be an iterable of entries, a mapping, RawGameState, or None; "
            f"got {type(bag_entries).__name__}"
        )

    available: set[RodKind] = set()
    for entry in raw_entries:
        if not isinstance(entry, (tuple, list)):
            raise TypeError(
                f"each bag entry must be a 2-tuple (item_id, quantity), "
                f"got {type(entry).__name__}: {entry!r}"
            )
        if len(entry) != 2:
            raise ValueError(
                f"each bag entry must have exactly 2 elements (item_id, quantity), "
                f"got {len(entry)}: {entry!r}"
            )
        item_raw, quantity_raw = entry
        if not isinstance(item_raw, int) or isinstance(item_raw, bool):
            raise TypeError(
                f"bag entry item_id must be an integer, got {type(item_raw).__name__}: {item_raw!r}"
            )
        if not isinstance(quantity_raw, int) or isinstance(quantity_raw, bool):
            raise TypeError(
                f"bag entry quantity must be an integer, "
                f"got {type(quantity_raw).__name__}: {quantity_raw!r}"
            )
        if quantity_raw < 0:
            raise ValueError(
                f"bag entry quantity cannot be negative, got {quantity_raw}"
            )
        if quantity_raw > 0:
            rod = ROD_ITEM_TO_KIND.get(int(item_raw))
            if rod is not None:
                available.add(rod)

    return tuple(rod for rod in _ROD_ORDER if rod in available)


@dataclass(frozen=True, slots=True)
class ShorelineStance:
    """A standable land coordinate facing an orthogonally adjacent water coordinate."""

    at: tuple[int, int]
    direction: Direction
    water_at: tuple[int, int]

    def __post_init__(self) -> None:
        if not (
            isinstance(self.at, tuple)
            and len(self.at) == 2
            and isinstance(self.at[0], int)
            and not isinstance(self.at[0], bool)
            and isinstance(self.at[1], int)
            and not isinstance(self.at[1], bool)
        ):
            raise TypeError("stance coordinate 'at' must be a tuple of two integers (y, x)")
        if not isinstance(self.direction, Direction):
            raise TypeError(
                f"stance direction must be a Direction instance, "
                f"got {type(self.direction).__name__}"
            )
        if not (
            isinstance(self.water_at, tuple)
            and len(self.water_at) == 2
            and isinstance(self.water_at[0], int)
            and not isinstance(self.water_at[0], bool)
            and isinstance(self.water_at[1], int)
            and not isinstance(self.water_at[1], bool)
        ):
            raise TypeError(
                "water coordinate 'water_at' must be a tuple of two integers (y, x)"
            )
        dy, dx = self.direction.delta
        expected_water = (self.at[0] + dy, self.at[1] + dx)
        if self.water_at != expected_water:
            raise ValueError(
                f"water coordinate {self.water_at} does not match "
                f"facing {self.direction.value} from {self.at} (expected {expected_water})"
            )


def fishable_shoreline_stances(terrain: Terrain) -> tuple[ShorelineStance, ...]:
    """Derive deterministic candidate shoreline stances from Terrain.

    Geometry alone does not prove that a cast succeeds. A candidate is a
    standable land coordinate facing orthogonally adjacent water, in canonical
    row-major and direction order, with out-of-bounds coordinates excluded.
    """
    if not isinstance(terrain, Terrain):
        raise TypeError(
            f"terrain must be a Terrain instance, got {type(terrain).__name__}"
        )

    stances: list[ShorelineStance] = []
    height = terrain.height
    width = terrain.width

    for y in range(height):
        for x in range(width):
            if not terrain.can_stand(y, x) or terrain.can_surf(y, x):
                continue
            for direction in _CANONICAL_DIRECTIONS:
                dy, dx = direction.delta
                water_y = y + dy
                water_x = x + dx
                if not (0 <= water_y < height and 0 <= water_x < width):
                    continue
                if terrain.can_surf(water_y, water_x):
                    stances.append(
                        ShorelineStance(
                            at=(y, x),
                            direction=direction,
                            water_at=(water_y, water_x),
                        )
                    )
    return tuple(stances)


class FishingCastError(RuntimeError):
    """A fishing cast failed, was unavailable, or lost its verified boundary."""


class FishingCastOutcome(StrEnum):
    """Semantic outcome of one bounded fishing cast."""

    NO_BITE = "no_bite"
    WILD_ENCOUNTER = "wild_encounter"


@dataclass(frozen=True, slots=True)
class FishingTiming:
    """Frame waits and bounded pulse limits for fishing cast execution."""

    menu_wait_frames: int = 180
    cursor_wait_frames: int = 120
    dialogue_wait_frames: int = 180
    max_menu_moves: int = 32
    max_settle_pulses: int = 16

    def __post_init__(self) -> None:
        for name in (
            "menu_wait_frames",
            "cursor_wait_frames",
            "dialogue_wait_frames",
            "max_menu_moves",
            "max_settle_pulses",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer, got {value!r}")


class ActionExecutor(Protocol):
    """Minimal interface for executing macro actions."""

    def execute(self, action: MacroAction) -> object: ...


class FishingCastReader(Protocol):
    """Observation interface required for fishing cast execution."""

    def read(self) -> RawGameState: ...

    def read_input_readiness(self) -> InputReadiness: ...

    def read_player_facing(self) -> str: ...

    def read_bottom_dialogue_box_visible(self) -> bool: ...

    def read_menu_cursor_state(self) -> MenuCursorState: ...


@dataclass(frozen=True, slots=True)
class FishingCastResult:
    """Bounded, identity-free receipt for one executed fishing cast."""

    outcome: FishingCastOutcome
    rod_kind: RodKind
    actions: int
    frames: int
    facing_action_used: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, FishingCastOutcome):
            raise TypeError(
                f"outcome must be a FishingCastOutcome instance, got {type(self.outcome).__name__}"
            )
        if not isinstance(self.rod_kind, RodKind):
            raise TypeError(
                f"rod_kind must be a RodKind instance, got {type(self.rod_kind).__name__}"
            )
        if type(self.actions) is not int or self.actions < 0:
            raise ValueError(f"actions must be a non-negative integer, got {self.actions!r}")
        if type(self.frames) is not int or self.frames < 0:
            raise ValueError(f"frames must be a non-negative integer, got {self.frames!r}")
        if type(self.facing_action_used) is not bool:
            raise TypeError("facing_action_used must be a bool")

    def public_dict(self) -> dict[str, object]:
        """Return public dictionary without map, coordinate, or species identity."""
        return {
            "schema": "pokemon.red.fishing-cast.v1",
            "status": self.outcome.value,
            "rod_kind": self.rod_kind.value,
            "actions": self.actions,
            "frames": self.frames,
            "wild_encounter": self.outcome is FishingCastOutcome.WILD_ENCOUNTER,
            "no_bite": self.outcome is FishingCastOutcome.NO_BITE,
            "facing_action_used": self.facing_action_used,
            "forced_support_step": False,
            "learned_goal_authority": False,
            "training_examples": 0,
        }


def _protected_state(raw: RawGameState) -> tuple[object, ...]:
    return (
        raw.game_started,
        raw.map_id,
        raw.player_x,
        raw.player_y,
        raw.badge_bits,
        raw.event_flags,
        raw.status_flags_1,
        raw.party_count,
        raw.party_species_ids,
        raw.party_levels,
        raw.party_hp,
        raw.party_max_hp,
        raw.party_status,
        raw.party_moves,
        raw.party_pp,
        raw.player_money,
        raw.bag_items,
    )


def _require_protected_state(initial: RawGameState, current: RawGameState) -> None:
    if _protected_state(current) != _protected_state(initial):
        raise FishingCastError("fishing cast altered protected game state")


@dataclass(slots=True)
class FishingCastExecutor:
    """Execute one bounded Gen I fishing cast at an already-reached shoreline candidate."""

    actions: ActionExecutor
    reader: FishingCastReader
    emulator: object = None
    timing: FishingTiming = field(default_factory=FishingTiming)
    _internal_actions_count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.timing, FishingTiming):
            raise TypeError(
                f"timing must be a FishingTiming instance, got {type(self.timing).__name__}"
            )

    def execute(
        self,
        stance: ShorelineStance,
        *,
        rod: RodKind | None = None,
    ) -> FishingCastResult:
        """Execute a fishing cast at the given shoreline candidate stance."""
        if not isinstance(stance, ShorelineStance):
            raise TypeError(
                f"stance must be a ShorelineStance instance, got {type(stance).__name__}"
            )
        if rod is not None and not isinstance(rod, RodKind):
            raise TypeError(f"rod must be a RodKind instance or None, got {type(rod).__name__}")

        initial = self.reader.read()
        if (
            not initial.game_started
            or initial.map_id is None
            or initial.player_x is None
            or initial.player_y is None
            or initial.battle_state != 0
            or initial.bag_items is None
            or not self.reader.read_input_readiness().ready
            or self.reader.read_bottom_dialogue_box_visible()
        ):
            raise FishingCastError("fishing cast starting gate is invalid or not ready")

        if (initial.player_y, initial.player_x) != stance.at:
            raise FishingCastError("player position does not match shoreline candidate stance")

        before_actions = self._get_actions_executed()
        before_frames = self._get_frame_count()

        # Turn player to face shoreline water if needed
        facing_action_used = False
        current_facing = self.reader.read_player_facing()
        if current_facing != stance.direction.value:
            facing_action_used = True
            self._pulse(
                MacroActionKind.MOVE,
                stance.direction.value,
                frames=self.timing.cursor_wait_frames,
            )
            faced = self.reader.read()
            _require_protected_state(initial, faced)
            if (
                (faced.player_y, faced.player_x) != stance.at
                or self.reader.read_player_facing() != stance.direction.value
                or faced.battle_state != 0
                or not self.reader.read_input_readiness().ready
            ):
                raise FishingCastError("failed to face shoreline candidate direction")
            initial = faced

        # Choose and verify rod from bag
        available = available_rod_kinds(initial)
        if not available:
            raise FishingCastError("no fishing rod observed in bag")

        if rod is not None:
            if rod not in available:
                raise FishingCastError(f"requested rod {rod.name} is not in observed bag")
            chosen_rod = rod
        else:
            chosen_rod = available[-1]

        target_item = item_for_rod_kind(chosen_rod)
        bag_items = initial.bag_items
        assert bag_items is not None
        try:
            bag_index = next(
                idx
                for idx, (item_id, qty) in enumerate(bag_items)
                if item_id == int(target_item) and qty > 0
            )
        except StopIteration:
            raise FishingCastError(
                f"rod item {target_item.name} not found with positive quantity in bag"
            ) from None

        # 1. Open START menu
        self._pulse(MacroActionKind.OPEN_MENU, frames=self.timing.menu_wait_frames)

        # 2. Select ITEM in START menu (row 2)
        item_row = 2
        for _ in range(self.timing.max_menu_moves):
            try:
                cursor = self.reader.read_menu_cursor_state()
            except Exception as error:
                raise FishingCastError("unknown UI during Start menu navigation") from error
            if cursor.selected_visible_index == item_row:
                break
            direction = "down" if cursor.selected_visible_index < item_row else "up"
            self._pulse(MacroActionKind.MOVE, direction, frames=self.timing.cursor_wait_frames)
        else:
            raise FishingCastError("could not select ITEM in Start menu")

        self._pulse(MacroActionKind.CONFIRM, frames=self.timing.menu_wait_frames)

        # 3. Select rod item in Bag menu
        for _ in range(self.timing.max_menu_moves):
            try:
                cursor = self.reader.read_menu_cursor_state()
            except Exception as error:
                raise FishingCastError("unknown UI during bag menu navigation") from error
            curr_index = cursor.selected_absolute_index
            if curr_index == bag_index:
                break
            direction = "down" if curr_index < bag_index else "up"
            self._pulse(MacroActionKind.MOVE, direction, frames=self.timing.cursor_wait_frames)
        else:
            raise FishingCastError(f"could not select rod at bag index {bag_index}")

        self._pulse(MacroActionKind.CONFIRM, frames=self.timing.menu_wait_frames)

        # 4. Select USE in item submenu (row 0)
        use_row = 0
        for _ in range(self.timing.max_menu_moves):
            try:
                cursor = self.reader.read_menu_cursor_state()
            except Exception as error:
                raise FishingCastError("unknown UI during item submenu navigation") from error
            if cursor.selected_visible_index == use_row:
                break
            self._pulse(MacroActionKind.MOVE, "up", frames=self.timing.cursor_wait_frames)
        else:
            raise FishingCastError("could not select USE in item submenu")

        # 5. Confirm USE to cast the rod!
        self._pulse(MacroActionKind.CONFIRM, frames=self.timing.menu_wait_frames)

        # 6. Settlement: distinguish wild encounter from no-bite dialogue
        for pulse in range(self.timing.max_settle_pulses + 1):
            current = self.reader.read()
            _require_protected_state(initial, current)

            if current.battle_state == 1:
                return FishingCastResult(
                    outcome=FishingCastOutcome.WILD_ENCOUNTER,
                    rod_kind=chosen_rod,
                    actions=self._action_count(before_actions),
                    frames=self._frame_count(before_frames),
                    facing_action_used=facing_action_used,
                )
            elif current.battle_state == 0:
                dialogue_visible = self.reader.read_bottom_dialogue_box_visible()
                input_ready = self.reader.read_input_readiness().ready
                if not dialogue_visible and input_ready:
                    return FishingCastResult(
                        outcome=FishingCastOutcome.NO_BITE,
                        rod_kind=chosen_rod,
                        actions=self._action_count(before_actions),
                        frames=self._frame_count(before_frames),
                        facing_action_used=facing_action_used,
                    )
                if pulse < self.timing.max_settle_pulses:
                    self._pulse(
                        MacroActionKind.CONFIRM,
                        frames=self.timing.dialogue_wait_frames,
                    )
            else:
                raise FishingCastError(
                    f"fishing cast encountered unexpected battle state: {current.battle_state}"
                )

        raise FishingCastError("fishing cast dialogue did not settle within bounded pulses")

    def _send_action(self, action: MacroAction) -> None:
        self._internal_actions_count += 1
        self.actions.execute(action)

    def _pulse(
        self,
        kind: MacroActionKind,
        value: str | int | None = None,
        *,
        frames: int,
    ) -> None:
        self._send_action(MacroAction(kind, value))
        self._send_action(MacroAction(MacroActionKind.WAIT, repeat=frames))

    def _get_actions_executed(self) -> int:
        val = getattr(self.actions, "actions_executed", None)
        if isinstance(val, int) and not isinstance(val, bool):
            return val
        return self._internal_actions_count

    def _action_count(self, before_actions: int) -> int:
        current = self._get_actions_executed()
        return current - before_actions

    def _get_frame_count(self) -> int:
        if self.emulator is None:
            return 0
        val = getattr(self.emulator, "frame_count", None)
        if type(val) is not int or val < 0:
            raise FishingCastError("emulator lacks integer frame_count")
        return val

    def _frame_count(self, before_frames: int) -> int:
        return self._get_frame_count() - before_frames


def execute_fishing_cast(
    actions: ActionExecutor,
    reader: FishingCastReader,
    stance: ShorelineStance,
    *,
    rod: RodKind | None = None,
    emulator: object = None,
    timing: FishingTiming | None = None,
) -> FishingCastResult:
    """Execute one bounded Gen I fishing cast at an already-reached shoreline candidate."""
    executor = FishingCastExecutor(
        actions=actions,
        reader=reader,
        emulator=emulator,
        timing=timing or FishingTiming(),
    )
    return executor.execute(stance, rod=rod)

