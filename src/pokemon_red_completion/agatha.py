"""Qualified Agatha chapter for the pinned Pokémon Red runtime."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_actions import (
    BattleAction,
    BattleBoostStat,
    BattleControlRequest,
    control_request_matches,
    recovery_request_matches,
)
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleRecoveryCapability,
    BattleResourcePolicy,
    BattleRuntimeError,
    BattleRuntimeTiming,
    note_observed_trainer_battle_exit,
    recovery_action_due,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.blaine import _select_cursor
from pokemon_red_completion.celadon import (
    _bag,
    _party_hp,
    _party_max_hp,
    _party_status,
)
from pokemon_red_completion.hideout import DEFAULT_HIDEOUT_TIMING
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    _close_menus,
    _open_bag,
    _select_bag_item,
    _use_bag_item,
)
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.silph import (
    DEFAULT_SILPH_TIMING,
    SilphChapterError,
    _battle_healing_item,
)
from pokemon_red_completion.tower import party_core_intact
from pokemon_red_completion.victory_road import (
    INDIGO_X_SPECIAL_RESERVE,
    _CountingExecutor,
    _event,
    _menu_cursor_active,
    _move,
    _pulse,
    _select_battle_main_command,
    _settle_confirm,
)

AGATHA_CHECKPOINT_COUNT = 3
AGATHA_RNG_DELAY_FRAMES = 85
AGATHA_SAFE_HP = 100
AGATHA_PARTY = (
    (0x0E, 56),
    (0x82, 56),
    (0x93, 55),
    (0x2D, 58),
    (0x0E, 60),
)
AGATHA_APPROACH = ("right", "up", "up")
# Surf and Ice Beam are the only attacks in the League set that can damage
# Agatha's Ghost-types.  Preserve a single Surf for Lance's Aerodactyl and
# spend the rest here so Ice Beam remains available for Lance's dragons.
AGATHA_SURF_RESERVE = 1
AGATHA_X_SPECIAL_USE = 1
AGATHA_ELIXIR_USE = 1


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class AgathaChapterError(RuntimeError):
    """Raised when the Agatha evidence contract fails."""


@dataclass(frozen=True, slots=True)
class AgathaProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[AgathaProgress], None]


@dataclass(frozen=True, slots=True)
class AgathaCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class AgathaTurn:
    species: int
    level: int
    enemy_hp: int
    lead_hp: int
    lead_status: int
    pp: tuple[int, int, int, int]
    move_slot: int
    party_position: int = 0


@dataclass(frozen=True, slots=True)
class AgathaChapterReport:
    records: tuple[AgathaCheckpoint, ...]
    final_raw: RawGameState
    turns: tuple[AgathaTurn, ...]
    party: tuple[tuple[int, int], ...]
    hyper_potions_used: int
    full_restores_used: int
    x_specials_used: int
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == AGATHA_CHECKPOINT_COUNT
            and self.party == _encounter_party(self.turns)
            and _observed_party_valid(self.turns)
            and _turns_valid(self.turns)
            and self.x_specials_used == AGATHA_X_SPECIAL_USE
            and _event(self.final_raw, EventFlag.BEAT_AGATHA)
            and self.final_raw.map_id == MapId.LANCES_ROOM
            and party_core_intact(self.final_raw.party_species_ids)
            and self.party_hp == self.party_max_hp
            and all(status == 0 for status in self.party_status)
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "defeat_agatha",
            "source_party": [list(item) for item in AGATHA_PARTY],
            # Gen I trainers may switch a fresh party member into an attack that
            # was selected against another opponent.  Such a member can faint
            # before the teacher receives another decision boundary, so keep
            # the policy-visible subset distinct from the declared roster.
            "party": [list(item) for item in self.party],
            "turns": [
                {
                    "species": item.species,
                    "level": item.level,
                    "enemy_hp": item.enemy_hp,
                    "lead_hp": item.lead_hp,
                    "lead_status": item.lead_status,
                    "pp": list(item.pp),
                    "move_slot": item.move_slot,
                    "party_position": item.party_position,
                }
                for item in self.turns
            ],
            "recovery": {
                "hyper_potions_used": self.hyper_potions_used,
                "full_restores_used": self.full_restores_used,
                "x_specials_used": self.x_specials_used,
            },
            "terminal": {
                "map": int(self.final_raw.map_id),
                "position": [self.final_raw.player_x, self.final_raw.player_y],
                "party_hp": list(self.party_hp),
                "party_max_hp": list(self.party_max_hp),
                "party_status": list(self.party_status),
                "moves": list(self.final_raw.first_party_moves or ()),
                "pp": list(self.final_raw.first_party_pp or ()),
            },
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


def run_agatha_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    progress: ProgressSink | None = None,
) -> AgathaChapterReport:
    start_frames = emulator.frame_count
    actions = _CountingExecutor(executor)
    records: list[AgathaCheckpoint] = []
    initial = reader.read()
    if (
        initial.map_id != MapId.AGATHAS_ROOM
        or (initial.player_x, initial.player_y) != (4, 5)
        or not party_core_intact(initial.party_species_ids)
        or not _event(initial, EventFlag.BEAT_BRUNO)
        or _event(initial, EventFlag.BEAT_AGATHA)
        or _bag(emulator).get(ItemId.X_SPECIAL, 0) != INDIGO_X_SPECIAL_RESERVE
    ):
        raise AgathaChapterError("Agatha input boundary is not qualified.")
    _checkpoint(records, progress, emulator, initial, "agatha_ready", "Agatha room ready")
    _use_field_elixir(actions, reader, emulator)
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=AGATHA_RNG_DELAY_FRAMES))

    _move(actions, reader, AGATHA_APPROACH, "Agatha approach")
    _pulse(actions, MacroActionKind.INTERACT)
    for _ in range(40):
        if reader.read().battle_state == 2:
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise AgathaChapterError("Agatha battle did not start.")
    _checkpoint(records, progress, emulator, reader.read(), "agatha_engaged", "Engaged Agatha")

    turns: list[AgathaTurn] = []

    class _HealBoundary(BattleControlRequest):
        default_action = BattleAction.recovery()

    class _BoostBoundary(BattleControlRequest):
        default_action = BattleAction.boost(BattleBoostStat.SPECIAL)

    last_recovery_turn = -1
    boosts_used = 0

    def policy(raw: RawGameState) -> int:
        if boosts_used < AGATHA_X_SPECIAL_USE:
            raise _BoostBoundary
        hp = raw.first_party_hp or 0
        status = raw.first_party_status or 0
        if recovery_action_due(
            hp=hp,
            status=status,
            safe_hp=AGATHA_SAFE_HP,
            decisions_made=len(turns),
            last_recovery_decision=last_recovery_turn,
        ):
            raise _HealBoundary
        species = raw.enemy_species_id or 0
        pp = raw.first_party_pp or (0, 0, 0, 0)
        slot = _agatha_move_slot(raw)
        turns.append(
            AgathaTurn(
                species,
                raw.enemy_level or 0,
                raw.enemy_hp or 0,
                hp,
                status,
                pp,
                slot,
                emulator.read_u8(RamAddress.ENEMY_MON_PARTY_POS),
            )
        )
        return slot

    hyper_before = _bag(emulator).get(ItemId.HYPER_POTION, 0)
    restore_before = _bag(emulator).get(ItemId.FULL_RESTORE, 0)
    x_special_before = _bag(emulator).get(ItemId.X_SPECIAL, 0)
    battle_intent = BattleIntent(
        "defeat_agatha",
        battle_plan_id=RedBattlePlanId.LEAGUE_AGATHA,
        resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
        recovery_capabilities=frozenset(
            {
                BattleRecoveryCapability.RESTORE_HP,
                BattleRecoveryCapability.CURE_ANY_STATUS,
            }
        ),
    )
    while reader.read().battle_state:
        try:
            run_adaptive_trainer_battle(
                reader,
                actions,
                policy,
                expected_map=MapId.AGATHAS_ROOM,
                intent=battle_intent,
                timing=BattleRuntimeTiming(
                    max_runtime_pulses=2000,
                    max_sleep_recovery_pulses=96,
                    max_post_attack_transition_pulses=30,
                ),
                label="Agatha",
            )
        except BattleRuntimeError as error:
            if control_request_matches(error.__cause__, _BoostBoundary.default_action):
                _battle_x_special(reader, actions, emulator)
                boosts_used += 1
                continue
            if not recovery_request_matches(error.__cause__, _HealBoundary):
                raise AgathaChapterError("Agatha battle runtime failed.") from error
            raw = reader.read()
            if (
                (raw.first_party_status or 0)
                and (raw.first_party_hp or 0) >= 120
                and _bag(emulator).get(ItemId.FULL_HEAL, 0)
            ):
                item = ItemId.FULL_HEAL
            elif raw.first_party_status or 0:
                item = ItemId.FULL_RESTORE
            else:
                item = (
                    ItemId.HYPER_POTION
                    if _bag(emulator).get(ItemId.HYPER_POTION, 0)
                    else ItemId.FULL_RESTORE
                )
            if _bag(emulator).get(item, 0) == 0:
                raise AgathaChapterError("Agatha exhausted the recovery reserve.") from error
            try:
                terminal_exit = _battle_healing_item(
                    reader,
                    actions,
                    emulator,
                    DEFAULT_SILPH_TIMING,
                    item,
                )
            except SilphChapterError as healing_error:
                current = reader.read()
                raise AgathaChapterError(
                    "Agatha recovery failed: "
                    f"party_hp={_party_hp(emulator)!r}, "
                    f"enemy={(current.enemy_species_id, current.enemy_hp, current.enemy_level)!r}, "
                    f"lead_status={current.first_party_status!r}, "
                    f"pp={current.first_party_pp!r}, bag={_bag(emulator)!r}."
                ) from healing_error
            if terminal_exit:
                note_observed_trainer_battle_exit(battle_intent)
            last_recovery_turn = len(turns)

    for _ in range(20):
        _pulse(actions, MacroActionKind.CANCEL)
    _settle_confirm(actions, reader, 40)
    if _party_hp(emulator) != _party_max_hp(emulator) or any(
        status != 0 for status in _party_status(emulator)
    ):
        try:
            item = _post_agatha_recovery_item(
                hp=_party_hp(emulator)[0],
                max_hp=_party_max_hp(emulator)[0],
                status=_party_status(emulator)[0],
                full_heals=_bag(emulator).get(ItemId.FULL_HEAL, 0),
                full_restores=_bag(emulator).get(ItemId.FULL_RESTORE, 0),
            )
            _use_bag_item(
                actions,
                reader,
                emulator,
                DEFAULT_LAVENDER_TIMING,
                item,
            )
        except Exception as error:
            raise AgathaChapterError(
                "Post-Agatha recovery failed: "
                f"hp={_party_hp(emulator)!r}, status={_party_status(emulator)!r}, "
                f"bag={_bag(emulator)!r}, cause={error}."
            ) from error
    defeated = reader.read()
    if not _event(defeated, EventFlag.BEAT_AGATHA):
        raise AgathaChapterError("Agatha event did not set after battle.")
    _checkpoint(records, progress, emulator, defeated, "agatha_defeated", "Defeated Agatha")
    _teach_take_down(actions, reader, emulator)
    _move(actions, reader, ("left", "up", "up", "up", "up"), "Lance room entry")
    final = reader.read()

    report = AgathaChapterReport(
        records=tuple(records),
        final_raw=final,
        turns=tuple(turns),
        party=_encounter_party(turns),
        hyper_potions_used=hyper_before - _bag(emulator).get(ItemId.HYPER_POTION, 0),
        full_restores_used=restore_before - _bag(emulator).get(ItemId.FULL_RESTORE, 0),
        x_specials_used=x_special_before - _bag(emulator).get(ItemId.X_SPECIAL, 0),
        party_hp=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise AgathaChapterError(f"Agatha terminal evidence failed: {report!r}.")
    return report


def _post_agatha_recovery_item(
    *,
    hp: int,
    max_hp: int,
    status: int,
    full_heals: int,
    full_restores: int,
) -> ItemId:
    """Choose one item that leaves the lead Lance-ready when possible."""

    if status:
        # A Full Heal alone is insufficient when the lead is also damaged;
        # prefer the single Full Restore that proves both terminal invariants.
        if hp < max_hp and full_restores > 0:
            return ItemId.FULL_RESTORE
        if full_heals > 0:
            return ItemId.FULL_HEAL
        if full_restores > 0:
            return ItemId.FULL_RESTORE
    elif hp < max_hp and full_restores > 0:
        return ItemId.FULL_RESTORE
    raise AgathaChapterError("Agatha lacks a legal post-battle recovery item.")


def _checkpoint(
    records: list[AgathaCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(AgathaCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            AgathaProgress(
                checkpoint_id,
                label,
                len(records),
                AGATHA_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )


def _encounter_party(turns: Iterable[AgathaTurn]) -> tuple[tuple[int, int], ...]:
    positions: dict[int, tuple[int, int]] = {}
    for turn in turns:
        positions.setdefault(turn.party_position, (turn.species, turn.level))
    return tuple(positions[position] for position in sorted(positions))


def _observed_party_valid(turns: Iterable[AgathaTurn]) -> bool:
    """Validate every policy-visible opponent against Agatha's source roster.

    The opening and final opponents must be visible.  Middle positions may be
    absent when Agatha switches one into an already-selected attack and it
    faints before the next policy decision.
    """

    items = tuple(turns)
    if not items:
        return False
    positions = {item.party_position for item in items}
    return (
        0 in positions
        and len(AGATHA_PARTY) - 1 in positions
        and all(
            0 <= item.party_position < len(AGATHA_PARTY)
            and (item.species, item.level) == AGATHA_PARTY[item.party_position]
            for item in items
        )
    )


def _turns_valid(turns: Iterable[AgathaTurn]) -> bool:
    items = tuple(turns)
    return bool(items) and all(
        item.move_slot in {1, 2, 3, 4} and item.lead_hp > 0 for item in items
    )


def _agatha_move_slot(raw: RawGameState) -> int:
    species = raw.enemy_species_id or 0
    pp = raw.first_party_pp or ()
    surf_pp = (pp[3] & 0x3F) if len(pp) >= 4 else 0
    surf_disabled = raw.player_disabled_move_slot == 4 and (raw.player_disable_turns or 0) > 0
    if species in {0x82, 0x2D}:
        priorities = (1, 4, 3, 2)
    elif surf_pp > AGATHA_SURF_RESERVE and not surf_disabled:
        priorities = (4, 3, 1, 2)
    else:
        priorities = (3, 4, 1, 2)
    for slot in priorities:
        if (
            len(pp) >= slot
            and pp[slot - 1] & 0x3F
            and not (raw.player_disabled_move_slot == slot and (raw.player_disable_turns or 0) > 0)
        ):
            return slot
    raise AgathaChapterError("Agatha policy has no legal move with PP.")


def _battle_x_special(
    reader: PokemonRedStateReader,
    actions: _CountingExecutor,
    emulator: EmulatorState,
    *,
    item: ItemId = ItemId.X_SPECIAL,
) -> None:
    raw = reader.read()
    if (
        raw.battle_state != 2
        or reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN
    ):
        raise AgathaChapterError(f"{item.name} requires the trainer MAIN menu.")
    initial = _bag(emulator).get(item, 0)
    if initial == 0:
        raise AgathaChapterError(f"{item.name} reserve was exhausted.")
    for attempt in range(2):
        before = _bag(emulator).get(item, 0)
        _select_battle_main_command(actions, reader, 1)
        _pulse(actions, MacroActionKind.CONFIRM)
        _select_bag_item(actions, emulator, item, DEFAULT_LAVENDER_TIMING)
        _pulse(actions, MacroActionKind.CONFIRM)
        consumed = False
        for _ in range(30):
            current = reader.read()
            after = _bag(emulator).get(item, 0)
            if after == before - 1:
                consumed = True
            elif after != before:
                raise AgathaChapterError(
                    f"{item.name} changed by an invalid quantity: before={before}, after={after}."
                )
            at_main = (
                current.battle_state == 2
                and reader.read_battle_menu_state(current).phase is BattleMenuPhase.MAIN
            )
            if consumed and at_main:
                if initial - after != 1:
                    raise AgathaChapterError(
                        f"{item.name} cumulative use was invalid: initial={initial}, after={after}."
                    )
                return
            if at_main and not consumed:
                break
            # B advances battle text but is inert on the restored MAIN menu.
            # A can spill across the final text boundary and immediately reopen
            # ITEM, consuming a second boost before the next observation.
            _pulse(actions, MacroActionKind.CANCEL)
        else:
            raise AgathaChapterError(
                f"{item.name} use did not settle: before={before}, "
                f"after={_bag(emulator).get(item, 0)}."
            )
        if attempt == 0:
            continue
    raise AgathaChapterError(
        f"{item.name} was not consumed after two bounded selections: "
        f"initial={initial}, after={_bag(emulator).get(item, 0)}."
    )


def _use_field_elixir(actions, reader, emulator) -> None:
    before = _bag(emulator).get(ItemId.ELIXIR, 0)
    if before != AGATHA_ELIXIR_USE:
        raise AgathaChapterError(f"Agatha Elixir reserve mismatch: {before!r}.")
    _open_bag(actions, emulator, DEFAULT_LAVENDER_TIMING)
    _select_bag_item(actions, emulator, ItemId.ELIXIR, DEFAULT_LAVENDER_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    _select_cursor(actions, emulator, 0, DEFAULT_LAVENDER_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(24):
        if _bag(emulator).get(ItemId.ELIXIR, 0) == 0:
            _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
            pp = tuple(value & 0x3F for value in (reader.read().first_party_pp or ()))
            if (
                len(pp) != 4
                or not all(value > 0 for value in pp)
                or pp[2] != 10
                or pp[3] <= AGATHA_SURF_RESERVE
            ):
                raise AgathaChapterError(f"Agatha Elixir reload failed: pp={pp!r}.")
            return
        _pulse(actions, MacroActionKind.CONFIRM)
    raise AgathaChapterError("Agatha Elixir did not restore the lead move PP.")


def _teach_take_down(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    *,
    expected_remaining: int = 0,
    expected_moves: tuple[int, int, int, int] = (0x24, 0x46, 0x3A, 0x39),
    replacement_slot: int = 0,
    item: ItemId = ItemId.TM09_TAKE_DOWN,
) -> None:
    _open_bag(actions, emulator, DEFAULT_LAVENDER_TIMING)
    _select_bag_item(
        actions,
        emulator,
        item,
        DEFAULT_LAVENDER_TIMING,
    )
    for _ in range(24):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (0, 1):
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise AgathaChapterError(f"{item.name} did not reach party selection.")
    _select_cursor(actions, emulator, 0, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(24):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (5, 8) and _menu_cursor_active(emulator):
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise AgathaChapterError(f"{item.name} did not reach move deletion.")
    for _ in range(replacement_slot):
        _pulse(actions, MacroActionKind.MOVE, "down")
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(24):
        raw = reader.read()
        if (
            raw.first_party_moves == expected_moves
            and _bag(emulator).get(item, 0) == expected_remaining
        ):
            _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
            return
        _pulse(actions, MacroActionKind.CONFIRM)
    raise AgathaChapterError(
        f"{item.name} did not install the expected move set: "
        f"actual={reader.read().first_party_moves!r}, expected={expected_moves!r}, "
        f"remaining={_bag(emulator).get(item, 0)}, expected_remaining={expected_remaining}."
    )
