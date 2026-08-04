"""Qualified Indigo Plateau and Lorelei chapter.

Room coordinates and trainer data are pinned to pret/pokered commit
``1e96034092686d006e863cace09e87273051a3d8`` and verified against the
supported English Pokémon Red ROM.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleResourcePolicy,
    BattleRuntimeError,
    BattleRuntimeTiming,
    note_observed_trainer_battle_exit,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.celadon import (
    _bag,
    _party_hp,
    _party_max_hp,
    _party_status,
)
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    _select_bag_item,
    _use_bag_item,
)
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RawGameState,
)
from pokemon_red_completion.silph import (
    DEFAULT_SILPH_TIMING,
    SilphChapterError,
    _battle_healing_item,
)
from pokemon_red_completion.tower import party_core_intact
from pokemon_red_completion.victory_road import (
    INDIGO_FULL_HEAL_RESERVE,
    INDIGO_FULL_RESTORE_RESERVE,
    INDIGO_X_SPECIAL_RESERVE,
    _CountingExecutor,
    _event,
    _move,
    _pulse,
    _select_battle_main_command,
    _settle_confirm,
)

LORELEI_CHECKPOINT_COUNT = 3
LORELEI_RNG_DELAY_FRAMES = 119
# Leave enough room for the strongest observed post-menu hit without forcing
# an item after every multi-turn Clamp sequence.  A higher threshold can
# deadlock into heal/Clamp/heal while the lead is otherwise healthy enough to
# finish the matchup.
LORELEI_SAFE_HP = 70
LORELEI_PARTY = (
    (0x78, 54),
    (0x8B, 53),
    (0x08, 54),
    (0x48, 56),
    (0x13, 56),
)
INDIGO_TO_LORELEI = (
    "up",
    "up",
    "up",
    "right",
    "right",
    "right",
    "right",
    "up",
    "right",
    "right",
    "up",
)
LORELEI_APPROACH = ("right", "up", "up")


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class LoreleiChapterError(RuntimeError):
    """Raised when the Lorelei evidence contract fails."""


@dataclass(frozen=True, slots=True)
class LoreleiProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[LoreleiProgress], None]


@dataclass(frozen=True, slots=True)
class LoreleiCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class LoreleiTurn:
    species: int
    level: int
    enemy_hp: int
    lead_hp: int
    lead_status: int
    pp: tuple[int, int, int, int]
    move_slot: int


@dataclass(frozen=True, slots=True)
class LoreleiChapterReport:
    records: tuple[LoreleiCheckpoint, ...]
    final_raw: RawGameState
    turns: tuple[LoreleiTurn, ...]
    party: tuple[tuple[int, int], ...]
    x_accuracy_used: int
    hyper_potions_used: int
    full_restores_used: int
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == LORELEI_CHECKPOINT_COUNT
            and self.party == LORELEI_PARTY
            and _turns_valid(self.turns)
            and self.x_accuracy_used == 1
            and self.hyper_potions_used <= 11
            and self.full_restores_used <= 12
            and _event(self.final_raw, EventFlag.BEAT_LORELEI)
            and self.final_raw.map_id == MapId.BRUNOS_ROOM
            and party_core_intact(self.final_raw.party_species_ids)
            and self.party_hp[0] >= LORELEI_SAFE_HP
            and self.party_hp[1:] == self.party_max_hp[1:]
            and all(status == 0 for status in self.party_status)
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "defeat_lorelei",
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
                }
                for item in self.turns
            ],
            "recovery": {
                "x_accuracy_used": self.x_accuracy_used,
                "hyper_potions_used": self.hyper_potions_used,
                "full_restores_used": self.full_restores_used,
            },
            "terminal": {
                "map": int(self.final_raw.map_id),
                "position": [self.final_raw.player_x, self.final_raw.player_y],
                "party_hp": list(self.party_hp),
                "party_max_hp": list(self.party_max_hp),
                "party_status": list(self.party_status),
                "pp": list(self.final_raw.first_party_pp or ()),
            },
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


def run_lorelei_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    progress: ProgressSink | None = None,
) -> LoreleiChapterReport:
    start_frames = emulator.frame_count
    actions = _CountingExecutor(executor)
    records: list[LoreleiCheckpoint] = []
    initial = reader.read()
    if (
        initial.map_id != MapId.INDIGO_PLATEAU_LOBBY
        or (initial.player_x, initial.player_y) != (2, 5)
        or not party_core_intact(initial.party_species_ids)
        or initial.first_party_moves != (0x42, 0x46, 0x3A, 0x39)
        or _bag(emulator).get(ItemId.FULL_RESTORE, 0) != INDIGO_FULL_RESTORE_RESERVE
        or _bag(emulator).get(ItemId.FULL_HEAL, 0) != INDIGO_FULL_HEAL_RESERVE
        or _bag(emulator).get(ItemId.HYPER_POTION, 0) != 11
        or _bag(emulator).get(ItemId.X_ACCURACY, 0) != 3
        or _bag(emulator).get(ItemId.X_SPECIAL, 0) != INDIGO_X_SPECIAL_RESERVE
        or _event(initial, EventFlag.BEAT_LORELEI)
    ):
        raise LoreleiChapterError("Lorelei input boundary is not qualified.")
    _checkpoint(records, progress, emulator, initial, "lorelei_ready", "Lorelei supplies ready")
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=LORELEI_RNG_DELAY_FRAMES))

    _move(actions, reader, INDIGO_TO_LORELEI, "Lorelei room entry")
    entered = reader.read()
    if entered.map_id != MapId.LORELEIS_ROOM or (
        entered.player_x,
        entered.player_y,
    ) != (4, 5):
        raise LoreleiChapterError("Lorelei room entry did not reach its scripted boundary.")
    _checkpoint(records, progress, emulator, entered, "lorelei_entered", "Entered Lorelei's room")
    _move(actions, reader, LORELEI_APPROACH, "Lorelei approach")
    _pulse(actions, MacroActionKind.INTERACT)
    for _ in range(40):
        if reader.read().battle_state == 2:
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise LoreleiChapterError("Lorelei battle did not start.")

    turns: list[LoreleiTurn] = []

    class _HealBoundary(Exception):
        pass

    class _AccuracyBoundary(Exception):
        pass

    accuracy_used = 0

    def policy(raw: RawGameState) -> int:
        hp = raw.first_party_hp or 0
        status = raw.first_party_status or 0
        if accuracy_used == 0:
            raise _AccuracyBoundary
        if hp < LORELEI_SAFE_HP or status:
            raise _HealBoundary
        species = raw.enemy_species_id or 0
        pp = raw.first_party_pp or (0, 0, 0, 0)
        if species != 0x08 and pp[0] > 0:
            slot = 1
        elif pp[1] > 0:
            slot = 2
        elif pp[3] > 0:
            slot = 4
        else:
            slot = 3
        turns.append(
            LoreleiTurn(
                species,
                raw.enemy_level or 0,
                raw.enemy_hp or 0,
                hp,
                status,
                pp,
                slot,
            )
        )
        return slot

    hyper_before = _bag(emulator).get(ItemId.HYPER_POTION, 0)
    restore_before = _bag(emulator).get(ItemId.FULL_RESTORE, 0)
    accuracy_before = _bag(emulator).get(ItemId.X_ACCURACY, 0)
    battle_intent = BattleIntent(
        "defeat_lorelei",
        battle_plan_id=RedBattlePlanId.LEAGUE_LORELEI,
        resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
    )
    while reader.read().battle_state:
        try:
            run_adaptive_trainer_battle(
                reader,
                actions,
                policy,
                expected_map=MapId.LORELEIS_ROOM,
                intent=battle_intent,
                timing=BattleRuntimeTiming(
                    max_runtime_pulses=1600,
                    max_pp_confirmation_pulses=12,
                    max_post_attack_transition_pulses=24,
                ),
                label="Lorelei",
            )
        except BattleRuntimeError as error:
            if isinstance(error.__cause__, _AccuracyBoundary):
                _battle_x_accuracy(reader, actions, emulator)
                accuracy_used += 1
                continue
            if not isinstance(error.__cause__, _HealBoundary):
                raise LoreleiChapterError("Lorelei battle runtime failed.") from error
            raw = reader.read()
            if (raw.first_party_status or 0) and (raw.first_party_hp or 0) >= 70:
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
                inventory = _bag(emulator)
                raise LoreleiChapterError(
                    "Lorelei exhausted the bounded recovery reserve: "
                    f"hp={raw.first_party_hp}/{raw.first_party_max_hp}, "
                    f"status={raw.first_party_status}, enemy="
                    f"{(raw.enemy_species_id, raw.enemy_hp, raw.enemy_max_hp)!r}, "
                    f"pp={raw.first_party_pp!r}, bag={inventory!r}."
                ) from error
            try:
                terminal_exit = _battle_healing_item(
                    reader,
                    actions,
                    emulator,
                    DEFAULT_SILPH_TIMING,
                    item,
                )
            except SilphChapterError as healing_error:
                raise LoreleiChapterError("Lorelei recovery failed.") from healing_error
            if terminal_exit:
                note_observed_trainer_battle_exit(battle_intent)

    for _ in range(4):
        _pulse(actions, MacroActionKind.CONFIRM)
    _settle_confirm(actions, reader, 40)
    if _party_hp(emulator)[0] < _party_max_hp(emulator)[0] or _party_status(emulator)[0]:
        try:
            item = (
                ItemId.FULL_RESTORE
                if _party_hp(emulator)[0] < _party_max_hp(emulator)[0]
                else ItemId.FULL_HEAL
            )
            _use_bag_item(
                actions,
                reader,
                emulator,
                DEFAULT_LAVENDER_TIMING,
                item,
            )
        except Exception as error:
            raise LoreleiChapterError("Post-Lorelei recovery failed.") from error
    defeated = reader.read()
    if not _event(defeated, EventFlag.BEAT_LORELEI):
        raise LoreleiChapterError("Lorelei event did not set after battle.")
    _checkpoint(records, progress, emulator, defeated, "lorelei_defeated", "Defeated Lorelei")
    _move(actions, reader, ("left", "up", "up", "up", "up"), "Bruno room entry")
    final = reader.read()

    report = LoreleiChapterReport(
        records=tuple(records),
        final_raw=final,
        turns=tuple(turns),
        party=_encounter_party(turns),
        x_accuracy_used=accuracy_before - _bag(emulator).get(ItemId.X_ACCURACY, 0),
        hyper_potions_used=hyper_before - _bag(emulator).get(ItemId.HYPER_POTION, 0),
        full_restores_used=restore_before - _bag(emulator).get(ItemId.FULL_RESTORE, 0),
        party_hp=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise LoreleiChapterError(f"Lorelei terminal evidence failed: {report!r}.")
    return report


def _battle_x_accuracy(
    reader: PokemonRedStateReader,
    actions: _CountingExecutor,
    emulator: EmulatorState,
) -> None:
    raw = reader.read()
    if (
        raw.battle_state != 2
        or reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN
    ):
        raise LoreleiChapterError("X Accuracy gate requires the trainer MAIN menu.")
    initial = _bag(emulator).get(ItemId.X_ACCURACY, 0)
    if initial < 1:
        raise LoreleiChapterError("Lorelei requires an X Accuracy.")
    for attempt in range(2):
        before = _bag(emulator).get(ItemId.X_ACCURACY, 0)
        _select_battle_main_command(actions, reader, 1)
        _pulse(actions, MacroActionKind.CONFIRM)
        _select_bag_item(
            actions,
            emulator,
            ItemId.X_ACCURACY,
            DEFAULT_LAVENDER_TIMING,
        )
        _pulse(actions, MacroActionKind.CONFIRM)
        consumed = False
        for _ in range(30):
            current = reader.read()
            after = _bag(emulator).get(ItemId.X_ACCURACY, 0)
            if after == before - 1:
                consumed = True
            elif after != before:
                raise LoreleiChapterError(
                    "X Accuracy changed by an invalid quantity: "
                    f"before={before}, after={after}."
                )
            at_main = (
                current.battle_state == 2
                and reader.read_battle_menu_state(current).phase is BattleMenuPhase.MAIN
            )
            if consumed and at_main:
                if initial - after != 1:
                    raise LoreleiChapterError(
                        "X Accuracy cumulative use was invalid: "
                        f"initial={initial}, after={after}."
                    )
                return
            if at_main and not consumed:
                break
            # Use the safe text-advance button: B cannot reopen ITEM if the
            # battle menu returns during the input pulse.
            _pulse(actions, MacroActionKind.CANCEL)
        else:
            raise LoreleiChapterError(
                "X Accuracy use did not settle: "
                f"before={before}, after={_bag(emulator).get(ItemId.X_ACCURACY, 0)}."
            )
        if attempt == 0:
            continue
    raise LoreleiChapterError(
        "X Accuracy was not consumed after two bounded selections: "
        f"initial={initial}, after={_bag(emulator).get(ItemId.X_ACCURACY, 0)}."
    )


def _checkpoint(
    records: list[LoreleiCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(LoreleiCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            LoreleiProgress(
                checkpoint_id,
                label,
                len(records),
                LORELEI_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )


def _encounter_party(turns: Iterable[LoreleiTurn]) -> tuple[tuple[int, int], ...]:
    result: list[tuple[int, int]] = []
    for turn in turns:
        identity = (turn.species, turn.level)
        if not result or result[-1] != identity:
            result.append(identity)
    return tuple(result)


def _turns_valid(turns: Iterable[LoreleiTurn]) -> bool:
    items = tuple(turns)
    return bool(items) and all(
        item.species in {species for species, _ in LORELEI_PARTY}
        and item.move_slot in {1, 2, 3, 4}
        and item.lead_hp >= LORELEI_SAFE_HP
        and item.lead_status == 0
        for item in items
    )
