"""Reusable in-battle recovery primitives for a protected party lead.

The Gen I item turn is not intrinsically safe: the opponent attacks after the
item is used.  A protected recovery therefore switches a living reserve into
the battle, heals the lead while that reserve absorbs the reply, and restores
the lead after the reserve faints.  The primitive is deliberately independent
of any route or opponent so later policies can learn *when* to invoke the same
game concept.
"""

from __future__ import annotations

from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.celadon import _bag, _party_hp
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    ItemId,
    PokemonRedStateReader,
    RamAddress,
)


class EmulatorState(Protocol):
    def read_u8(self, address: int) -> int: ...


class ActionExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class ProtectedRecoveryError(RuntimeError):
    """Raised when a protected lead recovery leaves its bounded battle state."""


PROTECTED_RECOVERY_MAX_ATTACK_PULSES = 96
PARTY_SUBMENU_SWITCH = 0


def first_living_reserve(party_hp: tuple[int, ...]) -> int | None:
    """Return the first living non-lead party slot, if one exists."""

    return next((index for index, hp in enumerate(party_hp[1:], start=1) if hp > 0), None)


def sole_living_switch_target(
    party_hp: tuple[int, ...],
    active_party_index: int | None,
) -> int | None:
    """Return the only legal living replacement, never a hidden strategic choice."""

    if (
        active_party_index is None
        or not 0 <= active_party_index < len(party_hp)
        or party_hp[active_party_index] > 0
    ):
        return None
    candidates = tuple(
        index
        for index, hp in enumerate(party_hp)
        if index != active_party_index and hp > 0
    )
    return candidates[0] if len(candidates) == 1 else None


def switch_active_battler(
    actions: ActionExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    party_index: int,
    *,
    expected_battle_state: int = 2,
    label: str,
    wait_frames: int = 180,
) -> None:
    """Switch to one living party member through a fully observed battle-menu gate."""

    raw = reader.read()
    party = raw.party_hp or _party_hp(emulator)
    if (
        not 0 <= party_index < len(party)
        or party[party_index] <= 0
        or raw.battle_state != expected_battle_state
    ):
        raise ProtectedRecoveryError(f"{label} lacks a living in-battle switch target.")
    if raw.active_party_index == party_index:
        return
    if (raw.battler_hp or 0) <= 0:
        _switch_forced_fainted_battler(
            actions,
            reader,
            emulator,
            party_index,
            expected_battle_state=expected_battle_state,
            label=label,
            wait_frames=wait_frames,
        )
        return

    _select_battle_main_command(actions, reader, 2, wait_frames)
    _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
    _select_cursor(actions, emulator, party_index, wait_frames)
    _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
    for _ in range(12):
        if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) == PARTY_SUBMENU_SWITCH:
            break
        _pulse(actions, MacroActionKind.MOVE, "up", 120, wait_frames)
    else:
        raise ProtectedRecoveryError(f"{label} could not select the party SWITCH command.")
    _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)

    for pulse_index in range(48):
        settled = reader.read()
        if _party_hp(emulator)[party_index] <= 0:
            raise ProtectedRecoveryError(f"{label} target fainted during the switch.")
        if settled.battle_state != expected_battle_state:
            raise ProtectedRecoveryError(f"{label} left its active battle during the switch.")
        if (
            settled.active_party_index == party_index
            and reader.read_battle_menu_state(settled).phase is BattleMenuPhase.MAIN
        ):
            return
        _pulse(
            actions,
            MacroActionKind.CANCEL if (pulse_index + 1) % 4 == 0 else MacroActionKind.CONFIRM,
            wait_frames=wait_frames,
        )
    raise ProtectedRecoveryError(f"{label} did not return to MAIN with its selected battler.")


def _switch_forced_fainted_battler(
    actions: ActionExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    party_index: int,
    *,
    expected_battle_state: int,
    label: str,
    wait_frames: int,
) -> None:
    """Advance faint dialogue, select the live forced-party cursor, and prove MAIN."""

    # Gen I leaves the party cursor bytes stale while faint text is visible.
    # Never interpret those bytes until the live cursor tile authenticates the
    # party screen.  This matters especially in wild battles: moving or
    # confirming against a transient ordinary battle menu can select RUN and
    # destroy the protected encounter.
    for pulse_index in range(64):
        settled = reader.read()
        party = settled.party_hp or _party_hp(emulator)
        if party[party_index] <= 0:
            raise ProtectedRecoveryError(f"{label} forced-switch target fainted.")
        if settled.battle_state != expected_battle_state:
            raise ProtectedRecoveryError(f"{label} left battle during its forced switch.")
        if (
            settled.active_party_index == party_index
            and (settled.battler_hp or 0) > 0
            and reader.read_battle_menu_state(settled).phase is BattleMenuPhase.MAIN
        ):
            return
        if (settled.battler_hp or 0) <= 0:
            menu_phase = reader.read_battle_menu_state(settled).phase
            if menu_phase is not BattleMenuPhase.UNKNOWN:
                actions.execute(MacroAction(MacroActionKind.WAIT, repeat=wait_frames))
                continue
            if not _forced_party_menu_ready(emulator, len(party)):
                _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
                continue
            cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
            _pulse(
                actions,
                MacroActionKind.CONFIRM if cursor == party_index else MacroActionKind.MOVE,
                None if cursor == party_index else ("down" if cursor < party_index else "up"),
                wait_frames=wait_frames,
            )
            continue
        _pulse(
            actions,
            MacroActionKind.CANCEL if (pulse_index + 1) % 4 == 0 else MacroActionKind.CONFIRM,
            wait_frames=wait_frames,
        )
    raise ProtectedRecoveryError(
        f"{label} did not restore MAIN after its forced switch: "
        f"active={reader.read().active_party_index}, party_hp={_party_hp(emulator)!r}, "
        f"cursor={emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)}."
    )


def protected_lead_recovery(
    actions: ActionExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    party_index: int,
    *,
    heal_lead: bool = True,
    preserve_reserve: bool = False,
    healing_item: ItemId,
    wait_frames: int = 180,
) -> bool:
    """Pivot through one reserve and optionally heal the protected lead.

    Returns whether exactly one healing item was spent. A reserve can faint on
    the switch-in before the item turn; a reserve that survives the bounded
    attack window is switched back out instead of being required to faint.
    """

    party = _party_hp(emulator)
    if not 0 < party_index < len(party) or party[party_index] <= 0:
        raise ProtectedRecoveryError("The protected-recovery reserve is not alive.")

    _select_battle_main_command(actions, reader, 2, wait_frames)
    _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
    _select_cursor(actions, emulator, party_index, wait_frames)
    _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
    _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)

    pivot_ready = False
    for pulse_index in range(24):
        if _party_hp(emulator)[party_index] == 0:
            break
        raw = reader.read()
        if (
            raw.battle_state == 2
            and reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN
        ):
            pivot_ready = True
            break
        _pulse(
            actions,
            MacroActionKind.CANCEL if pulse_index % 4 == 3 else MacroActionKind.CONFIRM,
            wait_frames=wait_frames,
        )

    potion_spent = False
    if heal_lead and pivot_ready:
        _select_battle_main_command(actions, reader, 1, wait_frames)
        _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
        before = _bag(emulator).get(healing_item, 0)
        _select_bag_item(actions, emulator, healing_item, wait_frames)
        _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
        _select_cursor(actions, emulator, 0, wait_frames)
        _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
        for _ in range(24):
            if _party_hp(emulator)[party_index] == 0:
                break
            raw = reader.read()
            if (
                raw.battle_state == 2
                and reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN
            ):
                break
            _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
        if before - _bag(emulator).get(healing_item, 0) != 1:
            raise ProtectedRecoveryError(
                "Protected lead recovery did not spend exactly one healing item."
            )
        potion_spent = True

    if preserve_reserve and _party_hp(emulator)[party_index] > 0:
        _restore_lead_after_surviving_pivot(
            actions,
            reader,
            emulator,
            party_index,
            wait_frames,
        )
        return potion_spent

    # The original single-carry route used deliberately weak reserves that
    # fainted quickly. Balanced-team reserves can survive substantially longer;
    # keep the operation bounded, but give a healthy teammate enough turns to
    # absorb the same recovery sequence without a false timeout.
    for pulse_index in range(PROTECTED_RECOVERY_MAX_ATTACK_PULSES):
        if _party_hp(emulator)[party_index] == 0:
            break
        raw = reader.read()
        if raw.battle_state != 2:
            raise ProtectedRecoveryError("Protected recovery left its trainer battle.")
        menu = reader.read_battle_menu_state(raw)
        if menu.phase is BattleMenuPhase.MAIN:
            _select_battle_main_command(actions, reader, 0, wait_frames)
            _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
            _select_cursor(actions, emulator, 1, wait_frames)
            _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
        else:
            _pulse(
                actions,
                MacroActionKind.CANCEL if pulse_index % 4 == 3 else MacroActionKind.CONFIRM,
                wait_frames=wait_frames,
            )
    else:
        _restore_lead_after_surviving_pivot(
            actions,
            reader,
            emulator,
            party_index,
            wait_frames,
        )
        return potion_spent

    for _ in range(24):
        if _forced_party_menu_ready(emulator, len(_party_hp(emulator))):
            break
        _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
    else:
        raise ProtectedRecoveryError("Forced-switch party menu did not settle.")
    _select_cursor(actions, emulator, 0, wait_frames)
    _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
    for _ in range(24):
        raw = reader.read()
        if (
            raw.battle_state == 2
            and reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN
        ):
            return potion_spent
        _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
    raise ProtectedRecoveryError("Protected recovery did not restore the lead battler.")


def _restore_lead_after_surviving_pivot(
    actions: ActionExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    party_index: int,
    wait_frames: int,
) -> None:
    """Return a still-living reserve to the party after bounded recovery."""

    for pulse_index in range(32):
        raw = reader.read()
        if raw.battle_state != 2:
            raise ProtectedRecoveryError(
                "Surviving recovery pivot left its trainer battle."
            )
        if reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN:
            break
        _pulse(
            actions,
            MacroActionKind.CANCEL if pulse_index % 4 == 3 else MacroActionKind.CONFIRM,
            wait_frames=wait_frames,
        )
    else:
        raise ProtectedRecoveryError("Surviving recovery pivot did not reach MAIN.")

    _select_battle_main_command(actions, reader, 2, wait_frames)
    _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
    _select_cursor(actions, emulator, 0, wait_frames)
    _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
    _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
    for _ in range(32):
        raw = reader.read()
        if raw.battle_state != 2:
            raise ProtectedRecoveryError(
                "Battle ended while restoring the lead after a surviving pivot."
            )
        if _party_hp(emulator)[0] == 0:
            raise ProtectedRecoveryError(
                "Protected lead fainted while returning after a surviving pivot."
            )
        if (
            emulator.read_u8(RamAddress.PLAYER_MON_NUMBER) == 0
            and reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN
        ):
            return
        _pulse(actions, MacroActionKind.CONFIRM, wait_frames=wait_frames)
    raise ProtectedRecoveryError(
        "Protected recovery did not switch back from its surviving reserve: "
        f"party_index={party_index}, party_hp={_party_hp(emulator)!r}."
    )


def _select_battle_main_command(
    actions: ActionExecutor,
    reader: PokemonRedStateReader,
    target: int,
    wait_frames: int,
) -> None:
    coordinates = {0: (0, 0), 1: (0, 1), 2: (1, 0), 3: (1, 1)}
    for pulse_index in range(24):
        menu = reader.read_battle_menu_state(reader.read())
        if menu.phase is not BattleMenuPhase.MAIN:
            _pulse(
                actions,
                MacroActionKind.CANCEL if pulse_index % 4 == 3 else MacroActionKind.CONFIRM,
                wait_frames=wait_frames,
            )
            continue
        current = menu.selected_main_command
        if current == target:
            return
        if current not in coordinates:
            raise ProtectedRecoveryError("Battle command cursor is invalid.")
        x, y = coordinates[current]
        target_x, target_y = coordinates[target]
        direction = (
            "right"
            if x < target_x
            else "left"
            if x > target_x
            else "down"
            if y < target_y
            else "up"
        )
        _pulse(actions, MacroActionKind.MOVE, direction, 120, wait_frames)
    raise ProtectedRecoveryError("Battle command cursor did not settle.")


def _select_bag_item(
    actions: ActionExecutor,
    emulator: EmulatorState,
    item: ItemId,
    wait_frames: int,
) -> None:
    for _ in range(24):
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        items = tuple(_bag(emulator))
        if item not in items:
            raise ProtectedRecoveryError(f"Healing item {item.name} is unavailable.")
        if absolute < len(items) and items[absolute] == item:
            return
        target = items.index(item)
        _pulse(
            actions,
            MacroActionKind.MOVE,
            "down" if absolute < target else "up",
            120,
            wait_frames,
        )
    raise ProtectedRecoveryError(f"Could not select healing item {item.name}.")


def _select_cursor(
    actions: ActionExecutor,
    emulator: EmulatorState,
    target: int,
    wait_frames: int,
) -> None:
    for _ in range(12):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == target:
            return
        _pulse(
            actions,
            MacroActionKind.MOVE,
            "down" if cursor < target else "up",
            min(wait_frames, 120),
            wait_frames,
        )
    raise ProtectedRecoveryError(f"Menu cursor could not select party slot {target}.")


def _menu_cursor_active(emulator: EmulatorState) -> bool:
    address = emulator.read_u8(RamAddress.MENU_CURSOR_LOCATION)
    address |= emulator.read_u8(int(RamAddress.MENU_CURSOR_LOCATION) + 1) << 8
    tile_map = int(RamAddress.TILE_MAP)
    return tile_map <= address < tile_map + 360 and emulator.read_u8(address) == 0xED


def _forced_party_menu_ready(emulator: EmulatorState, party_size: int) -> bool:
    """Recognize any valid live-party cursor, including balanced-team slots 3–5."""

    cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
    return cursor < party_size and _menu_cursor_active(emulator)


def _pulse(
    actions: ActionExecutor,
    kind: MacroActionKind,
    value: str | None = None,
    frames: int | None = None,
    wait_frames: int = 180,
) -> None:
    actions.execute(MacroAction(kind, value))
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames or wait_frames))
