"""Bounded Generation I compilers for route-planner field actions.

The route executor is intentionally game-neutral: it can request a semantic
``field_move`` but must not know how Red's START, party, and member menus are
laid out.  This adapter owns that title-specific work and returns only after
live RAM acknowledges the exact coordinate and locomotion-mode transition.

Surf permission is deliberately conservative.  Forced Cycling Road state is
observed directly, while Seafoam B4 remains closed until its two-boulder story
predicate is modelled.  A topological water edge is never permission by itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.gen1_cut import CUT_PASSAGE_TILES
from pokemon_red_completion.gen1_traversal import (
    CUT_MOVE_ID,
    SURF_MOVE_ID,
    cut_capabilities,
    surf_capabilities,
)
from pokemon_red_completion.observation import (
    OverworldMovementMode,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
    ReadOnlyMemory,
)
from pokemon_red_completion.route_executor import RouteActionPort

FLY_MOVE_ID = 0x13
STRENGTH_MOVE_ID = 0x46
DIG_MOVE_ID = 0x5B
FLASH_MOVE_ID = 0x94
TELEPORT_MOVE_ID = 0x64
SOFTBOILED_MOVE_ID = 0x87

# Exact usable entries in Red/Blue's FieldMoveDisplayData.  The table also
# contains ANIM_B4, an unused id outside the real move catalogue.
GEN1_FIELD_MOVE_IDS = frozenset(
    {
        CUT_MOVE_ID,
        FLY_MOVE_ID,
        SURF_MOVE_ID,
        STRENGTH_MOVE_ID,
        FLASH_MOVE_ID,
        DIG_MOVE_ID,
        TELEPORT_MOVE_ID,
        SOFTBOILED_MOVE_ID,
    }
)

ALWAYS_ON_BIKE_MASK = 1 << 5
SEAFOAM_ISLANDS_B4F_MAP_ID = 0xA2
_DIRECTION_DELTAS = {
    "up": (-1, 0),
    "right": (0, 1),
    "down": (1, 0),
    "left": (0, -1),
}


class Gen1FieldMoveError(RuntimeError):
    """Raised when a field macro cannot prove its requested state change."""


@dataclass(frozen=True, slots=True)
class SurfPermission:
    allowed: bool
    reason: str

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("Surf permission needs an evidence reason")


@dataclass(frozen=True, slots=True)
class Gen1FieldMoveTiming:
    face_frames: int = 120
    menu_frames: int = 180
    settle_frames: int = 180
    max_menu_moves: int = 20
    max_confirmations: int = 10

    def __post_init__(self) -> None:
        for name, value in (
            ("face_frames", self.face_frames),
            ("menu_frames", self.menu_frames),
            ("settle_frames", self.settle_frames),
            ("max_menu_moves", self.max_menu_moves),
            ("max_confirmations", self.max_confirmations),
        ):
            if type(value) is not int or value <= 0:  # noqa: E721
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_GEN1_FIELD_MOVE_TIMING = Gen1FieldMoveTiming()


@dataclass(frozen=True, slots=True)
class Gen1SurfReceipt:
    source_map: int
    source_at: tuple[int, int]
    target_at: tuple[int, int]
    direction: str
    party_index: int
    submenu_row: int
    confirmation_count: int
    permission_reason: str


@dataclass(frozen=True, slots=True)
class Gen1CutReceipt:
    source_map: int
    source_at: tuple[int, int]
    target_at: tuple[int, int]
    direction: str
    party_index: int
    submenu_row: int
    confirmation_count: int
    target_tile_before: int
    target_tile_after: int
    block_at: tuple[int, int]
    block_before: int
    block_after: int


def surf_permission(memory: ReadOnlyMemory, raw: RawGameState) -> SurfPermission:
    """Observe the restrictions needed before the Surf menu may be opened."""

    if memory.read_u8(RamAddress.STATUS_FLAGS_6) & ALWAYS_ON_BIKE_MASK:
        return SurfPermission(False, "forced_bicycle_state")
    if raw.map_id == SEAFOAM_ISLANDS_B4F_MAP_ID:
        return SurfPermission(False, "seafoam_b4_story_gate_unmodelled")
    return SurfPermission(True, "no_observed_title_restriction")


def surf_menu_indices(raw: RawGameState) -> tuple[int, int]:
    """Return a living Surf holder and Surf's row among its field moves."""

    return _field_move_menu_indices(raw, SURF_MOVE_ID, "Surf")


def cut_menu_indices(raw: RawGameState) -> tuple[int, int]:
    """Return a living Cut holder and Cut's row among its field moves."""

    return _field_move_menu_indices(raw, CUT_MOVE_ID, "Cut")


def _field_move_menu_indices(
    raw: RawGameState,
    move_id: int,
    label: str,
) -> tuple[int, int]:
    hp = raw.party_hp or ()
    moves = raw.party_moves or ()
    if raw.party_count is None or raw.party_count != len(hp) or len(hp) != len(moves):
        raise Gen1FieldMoveError(f"{label} menu selection lacks a complete observed party")
    for party_index, (current_hp, known) in enumerate(zip(hp, moves, strict=True)):
        if current_hp <= 0 or move_id not in known:
            continue
        field_moves = tuple(move for move in known if move in GEN1_FIELD_MOVE_IDS)
        return party_index, field_moves.index(move_id)
    raise Gen1FieldMoveError(f"no living party member knows {label}")


@dataclass(slots=True)
class Gen1FieldMovePort:
    """Compile supported field macros and delegate ordinary route actions."""

    delegate: RouteActionPort
    reader: PokemonRedStateReader
    memory: ReadOnlyMemory
    timing: Gen1FieldMoveTiming = DEFAULT_GEN1_FIELD_MOVE_TIMING
    cut_block_swaps: Mapping[int, int] = field(default_factory=dict)
    receipts: list[Gen1SurfReceipt] = field(default_factory=list, init=False)
    cut_receipts: list[Gen1CutReceipt] = field(default_factory=list, init=False)

    def execute(self, action: MacroAction) -> object:
        if action.kind is not MacroActionKind.FIELD_MOVE:
            return self.delegate.execute(action)
        if not isinstance(action.value, str):
            raise Gen1FieldMoveError("a Gen I field action needs a semantic value")
        move, separator, direction = action.value.partition(":")
        if separator != ":" or direction not in _DIRECTION_DELTAS:
            raise Gen1FieldMoveError(f"unsupported Gen I field action {action.value!r}")
        if action.repeat != 1:
            raise Gen1FieldMoveError("a field action cannot be repeated implicitly")
        if move == "surf":
            surf_receipt = self._surf(direction)
            self.receipts.append(surf_receipt)
            return surf_receipt
        if move == "cut":
            cut_receipt = self._cut(direction)
            self.cut_receipts.append(cut_receipt)
            return cut_receipt
        raise Gen1FieldMoveError(f"unsupported Gen I field action {action.value!r}")

    def _surf(self, direction: str) -> Gen1SurfReceipt:
        before = self.reader.read()
        source_map, source_at = _require_overworld(before, "Surf source")
        permission = surf_permission(self.memory, before)
        if not permission.allowed:
            raise Gen1FieldMoveError(f"Surf is closed by {permission.reason}")
        if not surf_capabilities(before, surf_allowed=True):
            raise Gen1FieldMoveError("Surf requires Soul Badge and a living move holder")
        if self.reader.read_overworld_movement_mode() is OverworldMovementMode.SURFING:
            raise Gen1FieldMoveError("Surf boarding cannot begin in water mode")
        party_index, submenu_row = surf_menu_indices(before)
        dy, dx = _DIRECTION_DELTAS[direction]
        target_at = source_at[0] + dy, source_at[1] + dx

        # A blocked directional press establishes facing without inventing a
        # direct controller primitive outside the shared action vocabulary.
        self._pulse(MacroAction(MacroActionKind.MOVE, direction), self.timing.face_frames)
        faced = self.reader.read()
        if _overworld_position(faced) != (source_map, source_at):
            raise Gen1FieldMoveError("Surf facing input moved away from its planned source")
        if self.reader.read_overworld_movement_mode() is OverworldMovementMode.SURFING:
            raise Gen1FieldMoveError("Surf mode changed before the field move was selected")

        self._pulse(MacroAction(MacroActionKind.OPEN_MENU), self.timing.menu_frames)
        self._select_cursor(1, "START-menu POKEMON")
        self._pulse(MacroAction(MacroActionKind.CONFIRM), self.timing.menu_frames)
        self._select_cursor(party_index, "party Surf holder")
        self._pulse(MacroAction(MacroActionKind.CONFIRM), self.timing.menu_frames)
        self._select_cursor(submenu_row, "Surf field command")
        self._pulse(MacroAction(MacroActionKind.CONFIRM), self.timing.settle_frames)

        for confirmations in range(self.timing.max_confirmations + 1):
            after = self.reader.read()
            if after.battle_state not in {0, None}:
                raise Gen1FieldMoveError("Surf field macro entered a battle")
            mode = self.reader.read_overworld_movement_mode()
            if (
                _overworld_position(after) == (source_map, target_at)
                and mode is OverworldMovementMode.SURFING
            ):
                _require_protected_surf_state(before, after)
                return Gen1SurfReceipt(
                    source_map=source_map,
                    source_at=source_at,
                    target_at=target_at,
                    direction=direction,
                    party_index=party_index,
                    submenu_row=submenu_row,
                    confirmation_count=confirmations,
                    permission_reason=permission.reason,
                )
            if _overworld_position(after) != (source_map, source_at):
                raise Gen1FieldMoveError(
                    "Surf changed position without entering its planned water square"
                )
            if confirmations == self.timing.max_confirmations:
                break
            self._pulse(MacroAction(MacroActionKind.CONFIRM), self.timing.settle_frames)
        raise Gen1FieldMoveError("Surf did not acknowledge the planned water-mode transition")

    def _cut(self, direction: str) -> Gen1CutReceipt:
        before = self.reader.read()
        source_map, source_at = _require_overworld(before, "Cut source")
        if not cut_capabilities(before):
            raise Gen1FieldMoveError("Cut requires Cascade Badge and a living move holder")
        if self.reader.read_overworld_movement_mode() is not OverworldMovementMode.WALKING:
            raise Gen1FieldMoveError("Cut requires ordinary walking mode")
        party_index, submenu_row = cut_menu_indices(before)
        dy, dx = _DIRECTION_DELTAS[direction]
        target_at = source_at[0] + dy, source_at[1] + dx

        self._pulse(MacroAction(MacroActionKind.MOVE, direction), self.timing.face_frames)
        faced = self.reader.read()
        if _overworld_position(faced) != (source_map, source_at):
            raise Gen1FieldMoveError("Cut facing input moved away from its planned source")
        tileset = self.memory.read_u8(RamAddress.CURRENT_MAP_TILESET)
        target_tile_before = self.memory.read_u8(RamAddress.TILE_IN_FRONT_OF_PLAYER)
        if target_tile_before not in CUT_PASSAGE_TILES.get(tileset, frozenset()):
            raise Gen1FieldMoveError(
                f"Cut target tile {target_tile_before:#04x} is not a passage tree "
                f"for tileset {tileset}"
            )
        blocks_before = self.reader.read_current_map_blocks()
        if blocks_before.map_id != source_map:
            raise Gen1FieldMoveError("Cut block buffer does not match the observed map")
        block_at = target_at[0] // 2, target_at[1] // 2
        if not (
            0 <= block_at[0] < blocks_before.height
            and 0 <= block_at[1] < blocks_before.width
        ):
            raise Gen1FieldMoveError("Cut target falls outside the current block buffer")
        block_before = blocks_before.at(*block_at)
        block_after = self.cut_block_swaps.get(block_before)
        if block_after is None:
            raise Gen1FieldMoveError(
                f"Cut target block {block_before:#04x} has no decoded replacement"
            )
        expected_rows = [list(row) for row in blocks_before.rows]
        expected_rows[block_at[0]][block_at[1]] = block_after
        expected_blocks_after = tuple(tuple(row) for row in expected_rows)

        self._pulse(MacroAction(MacroActionKind.OPEN_MENU), self.timing.menu_frames)
        self._select_cursor(1, "START-menu POKEMON")
        self._pulse(MacroAction(MacroActionKind.CONFIRM), self.timing.menu_frames)
        self._select_cursor(party_index, "party Cut holder")
        self._pulse(MacroAction(MacroActionKind.CONFIRM), self.timing.menu_frames)
        self._select_cursor(submenu_row, "Cut field command")
        self._pulse(MacroAction(MacroActionKind.CONFIRM), self.timing.settle_frames)

        for confirmations in range(self.timing.max_confirmations + 1):
            after = self.reader.read()
            if after.battle_state not in {0, None}:
                raise Gen1FieldMoveError("Cut field macro entered a battle")
            if _overworld_position(after) != (source_map, source_at):
                raise Gen1FieldMoveError("Cut changed the player's planned source position")
            blocks_after = self.reader.read_current_map_blocks()
            target_tile_after = self.memory.read_u8(RamAddress.TILE_IN_FRONT_OF_PLAYER)
            if (
                blocks_after.map_id == source_map
                and blocks_after.rows == expected_blocks_after
                and target_tile_after != target_tile_before
                and self.reader.read_input_readiness().ready
            ):
                _require_protected_field_state("Cut", before, after)
                return Gen1CutReceipt(
                    source_map=source_map,
                    source_at=source_at,
                    target_at=target_at,
                    direction=direction,
                    party_index=party_index,
                    submenu_row=submenu_row,
                    confirmation_count=confirmations,
                    target_tile_before=target_tile_before,
                    target_tile_after=target_tile_after,
                    block_at=block_at,
                    block_before=block_before,
                    block_after=block_after,
                )
            if blocks_after.map_id != source_map:
                raise Gen1FieldMoveError("Cut changed maps without acknowledging its mutation")
            if blocks_after.rows != blocks_before.rows and (
                blocks_after.rows != expected_blocks_after
            ):
                raise Gen1FieldMoveError("Cut changed a block other than its exact replacement")
            if confirmations == self.timing.max_confirmations:
                break
            self._pulse(MacroAction(MacroActionKind.CONFIRM), self.timing.settle_frames)
        raise Gen1FieldMoveError("Cut did not acknowledge its exact block and tile mutation")

    def _select_cursor(self, target: int, label: str) -> None:
        for _ in range(self.timing.max_menu_moves):
            current = self.memory.read_u8(RamAddress.CURRENT_MENU_ITEM)
            maximum = self.memory.read_u8(RamAddress.MAX_MENU_ITEM)
            if current <= maximum and target <= maximum:
                if current == target:
                    return
                direction = "down" if current < target else "up"
                self._pulse(MacroAction(MacroActionKind.MOVE, direction), self.timing.menu_frames)
                continue
            self.delegate.execute(MacroAction(MacroActionKind.WAIT, repeat=self.timing.menu_frames))
        raise Gen1FieldMoveError(
            f"could not select {label}: target={target}, "
            f"current={self.memory.read_u8(RamAddress.CURRENT_MENU_ITEM)}, "
            f"maximum={self.memory.read_u8(RamAddress.MAX_MENU_ITEM)}"
        )

    def _pulse(self, action: MacroAction, frames: int) -> None:
        self.delegate.execute(action)
        self.delegate.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))


def _require_overworld(raw: RawGameState, label: str) -> tuple[int, tuple[int, int]]:
    position = _overworld_position(raw)
    if not raw.game_started or position is None or raw.battle_state != 0:
        raise Gen1FieldMoveError(f"{label} is not a complete controllable overworld state")
    return position


def _overworld_position(raw: RawGameState) -> tuple[int, tuple[int, int]] | None:
    if raw.map_id is None or raw.player_y is None or raw.player_x is None:
        return None
    return raw.map_id, (raw.player_y, raw.player_x)


def _require_protected_surf_state(before: RawGameState, after: RawGameState) -> None:
    _require_protected_field_state("Surf", before, after)


def _require_protected_field_state(
    field_label: str,
    before: RawGameState,
    after: RawGameState,
) -> None:
    for state_label, before_value, after_value in (
        ("party count", before.party_count, after.party_count),
        ("party HP", before.party_hp, after.party_hp),
        ("party status", before.party_status, after.party_status),
        ("party moves", before.party_moves, after.party_moves),
        ("party PP", before.party_pp, after.party_pp),
        ("bag", before.bag_items, after.bag_items),
    ):
        if before_value != after_value:
            raise Gen1FieldMoveError(
                f"field {field_label} changed protected {state_label}"
            )
