"""Deterministic Vermilion-to-HM01 chapter for the pinned Pokémon Red ROM."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_actions import BattleAction, BattleControlRequest
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleResourcePolicy,
    BattleRuntimeError,
    BattleRuntimeTiming,
    run_adaptive_trainer_battle,
    run_adaptive_wild_battle,
)
from pokemon_red_completion.cascade import (
    CERULEAN_GYM_START_POTION_RESERVE,
    DEFAULT_CASCADE_TIMING,
    SS_ANNE_RIVAL_POTION_RESERVE,
    CascadeChapterError,
    _bag_quantity,
    _use_battle_recovery_item,
    _use_cerulean_rival_potion,
)
from pokemon_red_completion.lavender import (
    BUBBLEBEAM,
    DEFAULT_LAVENDER_TIMING,
    LavenderChapterError,
    _buy_mart_item,
    _close_menus,
    _money,
    _teach_tm11,
)
from pokemon_red_completion.observation import (
    MEGA_PUNCH_MOVE_ID,
    PIDGEOTTO_SPECIES_ID,
    WATER_GUN_MOVE_ID,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RawGameState,
    SSAnnePhase,
    SSAnneProgressError,
    SSAnneProgressTracker,
    SSAnneState,
)
from pokemon_red_completion.training import (
    TrainingDirective,
    TrainingObservation,
    TrainingPolicy,
    TrainingReport,
    choose_training_directive,
)

SS_ANNE_CHECKPOINT_COUNT = 9
RATICATE_SPECIES_ID = 0xA6
KADABRA_SPECIES_ID = 0x26
IVYSAUR_SPECIES_ID = 0x09
BITE_MOVE_ID = 0x2C
SS_ANNE_RIVAL_SPECIES_IDS = frozenset(
    {
        PIDGEOTTO_SPECIES_ID,
        RATICATE_SPECIES_ID,
        KADABRA_SPECIES_ID,
        IVYSAUR_SPECIES_ID,
    }
)
SS_ANNE_SUPER_POTION_RESERVE = 3
SS_ANNE_SUPER_POTION_RECOVERY_HP = 60
SUPER_POTION_HEAL_AMOUNT = 50
SUPER_POTION_PRICE = 700
VERMILION_SAILOR_BLOCK_POSITIONS = frozenset({(21, 27), (22, 27)})
VERMILION_SAILOR_CLEAR_ATTEMPTS = 10
SS_ANNE_WAITER_BLOCK_POSITION = (9, 6)
SS_ANNE_WAITER_YIELD_POSITION = (9, 7)
SS_ANNE_WAITER_CLEAR_POSITION = (8, 6)
SS_ANNE_WAITER_CORRIDOR_X_BOUNDS = (2, 9)
SS_ANNE_WAITER_CLEAR_ATTEMPTS = 10
PRE_SHIP_TRAINING_PATROL_DIRECTIONS = ("right", "left")
PRE_SHIP_TRAINING_POLICY = TrainingPolicy(
    target_level=30,
    preferred_move_slots=(3, 4, 1),
    retreat_hp_ratio=0.65,
    reserve_total_pp=8,
    max_enemy_level_delta=12,
    max_battles=120,
    max_steps=2_000,
    max_healing_trips=8,
)
PRE_SHIP_TRAINING_INTENT = BattleIntent(
    "develop_workhorse",
    battle_plan_id="red.route-11.pre-ship-leveling",
    resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
)


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "D": "down", "L": "left", "R": "right"}[letter] for letter in value)


VERMILION_TO_CENTER_DIRECTIONS = _directions("DDDLDDLLLLLLLUU")
CENTER_TO_NURSE_DIRECTIONS = _directions("UUUU")
CENTER_EXIT_DIRECTIONS = _directions("DDDDD")
CENTER_EXTERIOR_TO_MART_DIRECTIONS = _directions("R" * 10 + "D" * 10 + "RRU")
MART_TO_CENTER_EXTERIOR_DIRECTIONS = _directions("LL" + "U" * 10 + "L" * 10)
CENTER_TO_HARBOR_DIRECTIONS = _directions(
    "DDD" + "R" * 5 + "DD" + "RR" + "D" * 5 + "R" * 12 + "D" * 12 + "L" * 6 + "D" + "L" * 5 + "DDLD"
)
DOCK_TO_SHIP_DIRECTIONS = _directions("DDD")
SHIP_1F_TO_2F_DIRECTIONS = _directions("DDDD" + "L" + "DDD" + "L" * 15 + "U" + "L" * 9)
SHIP_2F_TO_RIVAL_DIRECTIONS = _directions(
    "D" * 7 + "R" + "D" + "R" * 31 + "U" * 2 + "R" * 2 + "U" * 2
)
RIVAL_TO_CAPTAIN_ROOM_DIRECTIONS = _directions("UUUU")
CAPTAIN_APPROACH_DIRECTIONS = _directions("UUURRRUR")


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class SSAnneChapterError(RuntimeError):
    """Raised when the bounded S.S. Anne route misses a semantic gate."""


@dataclass(frozen=True, slots=True)
class SSAnneTiming:
    transition_wait_frames: int = 120
    dialogue_wait_frames: int = 240
    rival_intro_wait_frames: int = 180
    ticket_dialogue_pulses: int = 5
    heal_dialogue_pulses: int = 9
    rival_intro_pulses: int = 12
    captain_rub_pulses: int = 6
    captain_hm_pulses: int = 8
    movement_retries: int = 10
    movement_retry_wait_frames: int = 12
    battle_runtime: BattleRuntimeTiming = BattleRuntimeTiming(
        max_runtime_pulses=720,
        max_main_navigation_pulses=6,
        max_move_menu_transition_pulses=6,
        max_move_navigation_pulses=6,
        max_pp_confirmation_pulses=8,
        max_attack_confirmation_pulses=4,
        max_post_attack_transition_pulses=12,
        max_sleep_recovery_pulses=16,
        max_sleep_reapplications=4,
    )

    def __post_init__(self) -> None:
        for name in (
            "transition_wait_frames",
            "dialogue_wait_frames",
            "rival_intro_wait_frames",
            "ticket_dialogue_pulses",
            "heal_dialogue_pulses",
            "rival_intro_pulses",
            "captain_rub_pulses",
            "captain_hm_pulses",
            "movement_retries",
            "movement_retry_wait_frames",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_SS_ANNE_TIMING = SSAnneTiming()


@dataclass(frozen=True, slots=True)
class SSAnneProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[SSAnneProgress], None]


@dataclass(frozen=True, slots=True)
class SSAnneCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState
    evidence: SSAnneState


@dataclass(frozen=True, slots=True)
class SSAnneChapterReport:
    records: tuple[SSAnneCheckpoint, ...]
    final_raw: RawGameState
    final_evidence: SSAnneState
    saw_rival_battle: bool
    frames_executed: int
    actions_executed: int
    controller_released: bool
    training: TrainingReport

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == SS_ANNE_CHECKPOINT_COUNT
            and self.final_evidence.hm01_snapshot
            and self.saw_rival_battle
            and self.training.passed
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((record.checkpoint_id, record.label, record.raw) for record in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "obtain_cut",
            "rival_battle_observed": self.saw_rival_battle,
            "training": {
                "area_id": self.training.area_id,
                "starting_level": self.training.starting_level,
                "target_level": self.training.target_level,
                "final_level": self.training.final_level,
                "battles_won": self.training.battles_won,
                "battles_fled": self.training.battles_fled,
                "steps_taken": self.training.steps_taken,
                "healing_trips": self.training.healing_trips,
            },
            "captain": {
                "rubbed_back": self.final_evidence.rubbed_captains_back,
                "got_hm01_event": self.final_evidence.got_hm01,
                "hm01_in_bag": self.final_evidence.hm01_in_bag,
                "cut_fact": self.final_evidence.cut_fact,
            },
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


class _CountingExecutor:
    def __init__(self, executor: ChapterExecutor) -> None:
        self._executor = executor
        self.actions_executed = 0

    def execute(self, action: MacroAction) -> object:
        result = self._executor.execute(action)
        self.actions_executed += 1
        return result


def run_ss_anne_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    timing: SSAnneTiming = DEFAULT_SS_ANNE_TIMING,
    progress: ProgressSink | None = None,
) -> SSAnneChapterReport:
    """Continue verified Vermilion state through the Captain's HM01 reward."""

    start_frames = emulator.frame_count
    chapter_executor = _CountingExecutor(executor)
    starting_raw = reader.read()
    try:
        tracker = SSAnneProgressTracker(reader.read_vermilion_state(starting_raw))
    except SSAnneProgressError as error:
        raise SSAnneChapterError(str(error)) from error
    records: list[SSAnneCheckpoint] = []
    _checkpoint(
        reader,
        tracker,
        SSAnnePhase.VERMILION_READY,
        "vermilion_ready",
        "Verified the clean Vermilion boundary",
        records,
        progress,
        emulator,
    )

    _move(chapter_executor, reader, VERMILION_TO_CENTER_DIRECTIONS, timing, "Vermilion Center")
    _wait(chapter_executor, timing.transition_wait_frames)
    _move(chapter_executor, reader, CENTER_TO_NURSE_DIRECTIONS, timing, "Vermilion nurse")
    _confirm_pulses(chapter_executor, timing.heal_dialogue_pulses, timing.dialogue_wait_frames)
    _checkpoint(
        reader,
        tracker,
        SSAnnePhase.HEALED,
        "healed",
        "Restored HP, status, and move PP",
        records,
        progress,
        emulator,
    )
    if _bag_quantity(emulator, ItemId.TM11_BUBBLEBEAM):
        try:
            _teach_tm11(
                chapter_executor,
                reader,
                emulator,
                DEFAULT_LAVENDER_TIMING,
            )
        except LavenderChapterError as error:
            raise SSAnneChapterError(str(error)) from error
    prepared = reader.read()
    if prepared.first_party_moves != (BITE_MOVE_ID, 0x27, BUBBLEBEAM, WATER_GUN_MOVE_ID):
        raise SSAnneChapterError(
            "S.S. Anne preparation lacks the qualified BubbleBeam moveset: "
            f"{prepared.first_party_moves!r}."
        )
    _purchase_ss_anne_super_potions(
        chapter_executor,
        reader,
        emulator,
        timing,
    )
    training = _run_pre_ship_training(
        chapter_executor,
        reader,
        emulator,
        timing,
    )
    _move(chapter_executor, reader, CENTER_TO_HARBOR_DIRECTIONS, timing, "Vermilion harbor")
    _confirm_pulses(chapter_executor, timing.ticket_dialogue_pulses, timing.dialogue_wait_frames)
    _move(chapter_executor, reader, ("down", "down"), timing, "Vermilion dock entry")
    _wait(chapter_executor, timing.transition_wait_frames)
    _checkpoint(
        reader,
        tracker,
        SSAnnePhase.DOCK_REACHED,
        "dock_reached",
        "Passed the ticket guard and reached the dock",
        records,
        progress,
        emulator,
    )

    _move(chapter_executor, reader, DOCK_TO_SHIP_DIRECTIONS, timing, "S.S. Anne entry")
    _wait(chapter_executor, timing.transition_wait_frames)
    _checkpoint(
        reader,
        tracker,
        SSAnnePhase.SHIP_1F_REACHED,
        "ship_1f_reached",
        "Boarded the S.S. Anne",
        records,
        progress,
        emulator,
    )
    _move(chapter_executor, reader, SHIP_1F_TO_2F_DIRECTIONS, timing, "S.S. Anne first floor")
    _wait(chapter_executor, timing.transition_wait_frames)
    _checkpoint(
        reader,
        tracker,
        SSAnnePhase.SHIP_2F_REACHED,
        "ship_2f_reached",
        "Reached the safe second-floor corridor",
        records,
        progress,
        emulator,
    )
    _move(chapter_executor, reader, SHIP_2F_TO_RIVAL_DIRECTIONS, timing, "S.S. Anne rival")
    _enter_rival_battle(chapter_executor, reader, timing)
    _checkpoint(
        reader,
        tracker,
        SSAnnePhase.RIVAL_BATTLE,
        "rival_battle",
        "Verified the live S.S. Anne RIVAL2 battle",
        records,
        progress,
        emulator,
    )
    _run_ss_anne_rival_with_potion(
        reader,
        chapter_executor,
        emulator,
        timing,
    )
    _checkpoint(
        reader,
        tracker,
        SSAnnePhase.RIVAL_DEFEATED,
        "rival_defeated",
        "Defeated the S.S. Anne rival",
        records,
        progress,
        emulator,
    )

    _move(chapter_executor, reader, RIVAL_TO_CAPTAIN_ROOM_DIRECTIONS, timing, "Captain room")
    _wait(chapter_executor, timing.transition_wait_frames)
    _checkpoint(
        reader,
        tracker,
        SSAnnePhase.CAPTAIN_ROOM_REACHED,
        "captain_room_reached",
        "Reached the Captain's room",
        records,
        progress,
        emulator,
    )
    _move(chapter_executor, reader, CAPTAIN_APPROACH_DIRECTIONS, timing, "Captain approach")
    chapter_executor.execute(MacroAction(MacroActionKind.MOVE, "up"))
    chapter_executor.execute(MacroAction(MacroActionKind.INTERACT))
    _wait(chapter_executor, timing.dialogue_wait_frames)
    _confirm_pulses(
        chapter_executor,
        timing.captain_rub_pulses - 1,
        timing.dialogue_wait_frames,
    )
    rubbed = reader.read_ss_anne_state(reader.read())
    if not rubbed.rubbed_captains_back or rubbed.got_hm01 or rubbed.hm01_in_bag or rubbed.cut_fact:
        raise SSAnneChapterError("Captain rub stage failed its exact pre-HM01 semantic gate.")
    chapter_executor.execute(MacroAction(MacroActionKind.CANCEL))
    _wait(chapter_executor, timing.dialogue_wait_frames)
    chapter_executor.execute(MacroAction(MacroActionKind.MOVE, "up"))
    chapter_executor.execute(MacroAction(MacroActionKind.INTERACT))
    _wait(chapter_executor, timing.dialogue_wait_frames)
    _confirm_pulses(
        chapter_executor,
        timing.captain_hm_pulses,
        timing.dialogue_wait_frames,
    )
    final_raw, final_evidence = _checkpoint(
        reader,
        tracker,
        SSAnnePhase.HM01_OBTAINED,
        "hm01_obtained",
        "Rubbed the Captain's back and obtained HM01",
        records,
        progress,
        emulator,
    )
    report = SSAnneChapterReport(
        records=tuple(records),
        final_raw=final_raw,
        final_evidence=final_evidence,
        saw_rival_battle=tracker.saw_rival_battle,
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=chapter_executor.actions_executed,
        controller_released=not emulator.pressed_buttons,
        training=training,
    )
    if not report.passed:
        raise SSAnneChapterError("The S.S. Anne chapter failed its evidence contract.")
    return report


def _move(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    directions: Iterable[str],
    timing: SSAnneTiming,
    label: str,
) -> RawGameState:
    state = reader.read()
    for step_number, direction in enumerate(directions, start=1):
        if state.battle_state:
            raise SSAnneChapterError(
                f"Unexpected battle interrupted {label} before step {step_number}."
            )
        before = state
        for attempt in range(timing.movement_retries):
            executor.execute(MacroAction(MacroActionKind.MOVE, direction))
            state = reader.read()
            if state.map_id != before.map_id or (state.player_x, state.player_y) != (
                before.player_x,
                before.player_y,
            ):
                break
            if (
                label == "Vermilion harbor"
                and before.map_id == MapId.VERMILION_CITY
                and (before.player_x, before.player_y) in VERMILION_SAILOR_BLOCK_POSITIONS
                and direction == "left"
            ):
                state = _yield_to_vermilion_sailor(executor, reader, timing)
                break
            if (
                label == "S.S. Anne first floor"
                and before.map_id == MapId.SS_ANNE_1F
                and before.player_y == SS_ANNE_WAITER_BLOCK_POSITION[1]
                and SS_ANNE_WAITER_CORRIDOR_X_BOUNDS[0]
                <= (before.player_x or -1)
                <= SS_ANNE_WAITER_CORRIDOR_X_BOUNDS[1]
                and direction == "left"
            ):
                state = _yield_to_ss_anne_waiter(executor, reader, timing)
                break
            _wait(executor, timing.movement_retry_wait_frames * (attempt + 1))
        else:
            raise SSAnneChapterError(
                f"{label} was blocked at map {before.map_id!r} "
                f"coordinate {(before.player_x, before.player_y)!r}."
            )
    return state


def _yield_to_vermilion_sailor(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SSAnneTiming,
) -> RawGameState:
    """Step off the harbor lane so its left/right sailor can pass."""

    initial = reader.read()
    block_position = (initial.player_x, initial.player_y)
    if initial.map_id != MapId.VERMILION_CITY or block_position not in (
        VERMILION_SAILOR_BLOCK_POSITIONS
    ):
        raise SSAnneChapterError("Vermilion sailor recovery lacks a supported harbor gate.")
    yield_position = (block_position[0], block_position[1] - 1)
    clear_position = (block_position[0] - 1, block_position[1])

    for attempt in range(VERMILION_SAILOR_CLEAR_ATTEMPTS):
        state = reader.read()
        if (state.player_x, state.player_y) == clear_position:
            return state
        if (
            state.map_id != MapId.VERMILION_CITY
            or state.battle_state != 0
            or (state.player_x, state.player_y) != block_position
        ):
            raise SSAnneChapterError("Vermilion sailor recovery left its bounded harbor gate.")

        executor.execute(MacroAction(MacroActionKind.MOVE, "up"))
        yielded = reader.read()
        if (yielded.player_x, yielded.player_y) != yield_position:
            raise SSAnneChapterError("Vermilion sailor recovery could not yield the harbor lane.")

        for return_attempt in range(VERMILION_SAILOR_CLEAR_ATTEMPTS):
            _wait(
                executor,
                timing.movement_retry_wait_frames * (attempt + return_attempt + 1),
            )
            executor.execute(MacroAction(MacroActionKind.MOVE, "down"))
            returned = reader.read()
            if returned.map_id != MapId.VERMILION_CITY or returned.battle_state != 0:
                raise SSAnneChapterError("Vermilion sailor recovery left Vermilion City.")
            if (returned.player_x, returned.player_y) == block_position:
                break
            if (returned.player_x, returned.player_y) != yield_position:
                raise SSAnneChapterError("Vermilion sailor recovery left its step-aside tile.")
        else:
            raise SSAnneChapterError("Vermilion sailor did not release the harbor return tile.")

        executor.execute(MacroAction(MacroActionKind.MOVE, "left"))
        state = reader.read()
        if (state.player_x, state.player_y) == clear_position:
            return state
        if (state.player_x, state.player_y) != block_position:
            raise SSAnneChapterError("Vermilion sailor recovery left its final approach gate.")

    raise SSAnneChapterError(
        "Vermilion sailor did not clear the harbor lane within its bounded retries."
    )


def _yield_to_ss_anne_waiter(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SSAnneTiming,
) -> RawGameState:
    """Step off the corridor so the first-floor waiter can walk past."""

    initial = reader.read()
    block_position = (initial.player_x, initial.player_y)
    if (
        initial.map_id != MapId.SS_ANNE_1F
        or initial.battle_state != 0
        or initial.player_y != SS_ANNE_WAITER_BLOCK_POSITION[1]
        or not SS_ANNE_WAITER_CORRIDOR_X_BOUNDS[0]
        <= (initial.player_x or -1)
        <= SS_ANNE_WAITER_CORRIDOR_X_BOUNDS[1]
    ):
        raise SSAnneChapterError("S.S. Anne waiter recovery lacks a supported corridor gate.")
    yield_position = ((initial.player_x or 0), (initial.player_y or 0) + 1)
    clear_position = ((initial.player_x or 0) - 1, (initial.player_y or 0))

    for attempt in range(SS_ANNE_WAITER_CLEAR_ATTEMPTS):
        state = reader.read()
        if (state.player_x, state.player_y) == clear_position:
            return state
        if (
            state.map_id != MapId.SS_ANNE_1F
            or state.battle_state != 0
            or (state.player_x, state.player_y) != block_position
        ):
            raise SSAnneChapterError("S.S. Anne waiter recovery left its corridor gate.")

        executor.execute(MacroAction(MacroActionKind.MOVE, "down"))
        yielded = reader.read()
        if (yielded.player_x, yielded.player_y) != yield_position:
            raise SSAnneChapterError("S.S. Anne waiter recovery could not yield the corridor.")

        for return_attempt in range(SS_ANNE_WAITER_CLEAR_ATTEMPTS):
            _wait(
                executor,
                timing.movement_retry_wait_frames * (attempt + return_attempt + 1),
            )
            executor.execute(MacroAction(MacroActionKind.MOVE, "up"))
            returned = reader.read()
            if returned.map_id != MapId.SS_ANNE_1F or returned.battle_state != 0:
                raise SSAnneChapterError("S.S. Anne waiter recovery left the first floor.")
            if (returned.player_x, returned.player_y) == block_position:
                break
            if (returned.player_x, returned.player_y) != yield_position:
                raise SSAnneChapterError("S.S. Anne waiter recovery left its step-aside tile.")
        else:
            raise SSAnneChapterError("S.S. Anne waiter did not release the return tile.")

        executor.execute(MacroAction(MacroActionKind.MOVE, "left"))
        state = reader.read()
        if (state.player_x, state.player_y) == clear_position:
            return state
        if (state.player_x, state.player_y) != block_position:
            raise SSAnneChapterError("S.S. Anne waiter recovery left its final approach gate.")

    raise SSAnneChapterError(
        "S.S. Anne waiter did not clear the corridor within its bounded retries."
    )


def _enter_rival_battle(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SSAnneTiming,
) -> RawGameState:
    for _ in range(timing.rival_intro_pulses):
        raw = reader.read()
        if raw.battle_state == 2:
            if reader.read_ss_anne_state(raw).rival_battle_snapshot:
                return raw
            _wait(executor, timing.rival_intro_wait_frames)
            continue
        if raw.battle_state:
            raise SSAnneChapterError("A wild battle replaced the S.S. Anne rival.")
        if raw.map_id != MapId.SS_ANNE_2F:
            raise SSAnneChapterError("The rival intro left the S.S. Anne second floor.")
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.rival_intro_wait_frames)
    raw = reader.read()
    raise SSAnneChapterError(
        f"The rival intro missed its bounded battle gate: {reader.read_ss_anne_state(raw)!r}."
    )


def _purchase_ss_anne_super_potions(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SSAnneTiming,
) -> None:
    """Buy a disclosed high-value reserve before the early attrition battle."""

    if _bag_quantity(emulator, ItemId.SUPER_POTION) != 0:
        raise SSAnneChapterError("S.S. Anne preparation began with an unexpected Super Potion.")
    money_before = _money(emulator)
    _move(executor, reader, CENTER_EXIT_DIRECTIONS, timing, "Vermilion Center reserve exit")
    _wait(executor, timing.transition_wait_frames)
    _move(
        executor,
        reader,
        CENTER_EXTERIOR_TO_MART_DIRECTIONS,
        timing,
        "Vermilion Mart reserve",
    )
    _wait(executor, timing.transition_wait_frames)
    mart_entry = reader.read()
    if mart_entry.map_id != MapId.VERMILION_MART or (mart_entry.player_x, mart_entry.player_y) != (
        3,
        7,
    ):
        raise SSAnneChapterError("S.S. Anne reserve missed the Vermilion Mart entry.")
    _move(executor, reader, ("up", "up", "left"), timing, "Vermilion Mart clerk")
    executor.execute(MacroAction(MacroActionKind.MOVE, "left"))
    _wait(executor, 60)
    _confirm_pulses(executor, 2, DEFAULT_LAVENDER_TIMING.wait_frames)
    try:
        _buy_mart_item(
            executor,
            emulator,
            DEFAULT_LAVENDER_TIMING,
            absolute_index=1,
            item=ItemId.SUPER_POTION,
            quantity=SS_ANNE_SUPER_POTION_RESERVE,
            target_bag_quantity=SS_ANNE_SUPER_POTION_RESERVE,
        )
        _close_menus(executor, reader, DEFAULT_LAVENDER_TIMING)
    except LavenderChapterError as error:
        raise SSAnneChapterError(str(error)) from error
    if (
        _bag_quantity(emulator, ItemId.SUPER_POTION) != SS_ANNE_SUPER_POTION_RESERVE
        or money_before - _money(emulator) != SS_ANNE_SUPER_POTION_RESERVE * SUPER_POTION_PRICE
    ):
        raise SSAnneChapterError("S.S. Anne Super Potion purchase missed its inventory ledger.")

    mart_position = reader.read()
    if (
        mart_position.map_id != MapId.VERMILION_MART
        or mart_position.player_x != 2
        or mart_position.player_y is None
        or not 5 <= mart_position.player_y <= 7
    ):
        raise SSAnneChapterError("S.S. Anne Mart closure lost its exit column.")
    _move(
        executor,
        reader,
        ("right",) + ("down",) * (8 - mart_position.player_y),
        timing,
        "Vermilion Mart exit",
    )
    _wait(executor, timing.transition_wait_frames)


def _run_pre_ship_training(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SSAnneTiming,
) -> TrainingReport:
    """Develop the workhorse safely in Route 11 grass before boarding."""

    initial = reader.read()
    if initial.map_id != MapId.VERMILION_CITY:
        raise SSAnneChapterError("Pre-ship training did not begin outside the Vermilion Mart.")
    starting_level = initial.first_party_level or 0
    entry = _enter_pre_ship_training_route11(executor, reader, timing)
    anchor_position = (entry.player_x, entry.player_y)
    opposite = {"up": "down", "right": "left", "down": "up", "left": "right"}
    bounce_direction: str | None = None

    battles_won = 0
    battles_fled = 0
    steps = 0
    healing_trips = 0

    def observation(raw: RawGameState) -> TrainingObservation:
        return TrainingObservation(
            level=raw.first_party_level or 0,
            hp=raw.first_party_hp or 0,
            max_hp=raw.first_party_max_hp or 0,
            pp=raw.first_party_pp or (),
            in_battle=raw.battle_state == 1,
            status=raw.first_party_status or 0,
            enemy_level=raw.enemy_level,
            battles_completed=battles_won,
            steps_taken=steps,
            healing_trips=healing_trips,
        )

    while True:
        raw = reader.read()
        if raw.battle_state == 0 and (raw.player_x, raw.player_y) != anchor_position:
            if bounce_direction is None:
                raise SSAnneChapterError(
                    "Pre-ship training lost its return direction at "
                    f"{(raw.player_x, raw.player_y)!r}."
                )
            executor.execute(MacroAction(MacroActionKind.MOVE, bounce_direction))
            _wait(executor, 60)
            steps += 1
            returned = reader.read()
            if returned.map_id != MapId.ROUTE_11:
                raise SSAnneChapterError("Pre-ship training left Route 11.")
            if (returned.player_x, returned.player_y) == anchor_position:
                bounce_direction = None
            elif returned.battle_state != 1:
                raise SSAnneChapterError(
                    "Pre-ship training could not restore its safe anchor: "
                    f"position={(returned.player_x, returned.player_y)!r}."
                )
            continue
        directive = _pre_ship_training_directive(
            raw,
            observation(raw),
        )
        if directive is TrainingDirective.STOP:
            if (raw.first_party_level or 0) < PRE_SHIP_TRAINING_POLICY.target_level:
                raise SSAnneChapterError(
                    "Pre-ship training exhausted a safety bound before level 30: "
                    f"level={raw.first_party_level}, battles={battles_won}, steps={steps}."
                )
            break
        if raw.battle_state == 1:
            if directive is TrainingDirective.FLEE:
                raise SSAnneChapterError(
                    "Route 11 training unexpectedly classified a lower-level wild as unsafe."
                )
            if directive is not TrainingDirective.FIGHT:
                raise SSAnneChapterError(
                    f"Pre-ship training produced unsafe battle directive {directive}."
                )
            try:
                run_adaptive_wild_battle(
                    reader,
                    executor,
                    _pre_ship_training_move_slot,
                    expected_map=MapId.ROUTE_11,
                    intent=PRE_SHIP_TRAINING_INTENT,
                    label="pre-ship Route 11 training",
                    timing=timing.battle_runtime,
                    unknown_cancel_interval=10_000,
                )
            except BattleRuntimeError as error:
                raise SSAnneChapterError(str(error)) from error
            battles_won += 1
            continue
        if directive is TrainingDirective.RETURN_TO_HEAL:
            if healing_trips >= PRE_SHIP_TRAINING_POLICY.max_healing_trips:
                raise SSAnneChapterError("Pre-ship training exhausted its healing-trip bound.")
            healed, exit_battles, exit_steps = _heal_pre_ship_training_anchor(
                executor, reader, timing, anchor_position
            )
            battles_won += exit_battles
            steps += exit_steps
            healing_trips += 1
            _move(
                executor,
                reader,
                CENTER_EXIT_DIRECTIONS,
                timing,
                "training recovery Center exit",
            )
            _wait(executor, timing.transition_wait_frames)
            _move(
                executor,
                reader,
                CENTER_EXTERIOR_TO_MART_DIRECTIONS[:-1],
                timing,
                "training recovery Mart exterior",
            )
            entry = _enter_pre_ship_training_route11(executor, reader, timing)
            if (entry.player_x, entry.player_y) != anchor_position:
                raise SSAnneChapterError(
                    "Pre-ship training recovery changed its safe Route 11 anchor."
                )
            bounce_direction = None
            continue
        if directive is not TrainingDirective.SEEK_ENCOUNTER:
            raise SSAnneChapterError(f"Invalid pre-ship training directive {directive}.")
        if raw.map_id != MapId.ROUTE_11 or raw.player_x is None or raw.player_y is None:
            raise SSAnneChapterError("Pre-ship training left Route 11.")
        current = (raw.player_x, raw.player_y)
        # Stay on the reversible east-west grass row.  The tile immediately
        # north of the anchor can be entered but did not permit the scheduled
        # return step in qualification, so it is not a safe patrol edge.
        candidates = (
            (bounce_direction,)
            if bounce_direction is not None
            else PRE_SHIP_TRAINING_PATROL_DIRECTIONS
        )
        moved_any = False
        for direction in candidates:
            if direction is None:
                continue
            executor.execute(MacroAction(MacroActionKind.MOVE, direction))
            _wait(executor, 60)
            steps += 1
            moved = reader.read()
            if moved.map_id != MapId.ROUTE_11:
                raise SSAnneChapterError("Pre-ship training left Route 11.")
            next_position = (moved.player_x, moved.player_y)
            moved_any, bounce_direction = _pre_ship_training_step_outcome(
                current=current,
                next_position=next_position,
                in_battle=moved.battle_state == 1,
                direction=direction,
                prior_bounce_direction=bounce_direction,
                opposite=opposite,
            )
            if moved_any:
                break
        if not moved_any:
            bounce_direction = None

    healed, exit_battles, exit_steps = _heal_pre_ship_training_anchor(
        executor, reader, timing, anchor_position
    )
    battles_won += exit_battles
    steps += exit_steps
    if (
        healed.first_party_level is None
        or healed.first_party_level < PRE_SHIP_TRAINING_POLICY.target_level
        or healed.first_party_hp != healed.first_party_max_hp
        or healed.first_party_status != 0
    ):
        raise SSAnneChapterError("Pre-ship training did not finish healed at level 30.")
    _move(executor, reader, CENTER_EXIT_DIRECTIONS, timing, "training Center exit")
    _wait(executor, timing.transition_wait_frames)
    return TrainingReport(
        area_id="route_11",
        starting_level=starting_level,
        target_level=PRE_SHIP_TRAINING_POLICY.target_level,
        final_level=healed.first_party_level,
        battles_won=battles_won,
        battles_fled=battles_fled,
        steps_taken=steps,
        healing_trips=healing_trips + 1,
        fainted=False,
    )


def _enter_pre_ship_training_route11(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SSAnneTiming,
) -> RawGameState:
    """Reach the source-qualified Route 11 grass from the Vermilion Mart."""

    _move(executor, reader, ("right",) * 17, timing, "Route 11 training entry")
    _wait(executor, timing.transition_wait_frames)
    _require_position(reader.read(), MapId.ROUTE_11, (0, 6), "Route 11 training entry")
    anchor = _move(
        executor,
        reader,
        ("right",) * 12,
        timing,
        "Route 11 training grass",
    )
    if anchor.map_id != MapId.ROUTE_11 or (anchor.player_x, anchor.player_y) != (12, 6):
        raise SSAnneChapterError(
            "Pre-ship training missed its Route 11 grass anchor: "
            f"map={anchor.map_id!r}, position={(anchor.player_x, anchor.player_y)!r}."
        )
    return anchor


def _heal_pre_ship_training_anchor(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SSAnneTiming,
    anchor_position: tuple[int | None, int | None],
) -> tuple[RawGameState, int, int]:
    """Fight safely out of Route 11 and heal at Vermilion's Center."""

    raw = reader.read()
    if raw.battle_state:
        raise SSAnneChapterError("Pre-ship training tried to heal inside a battle.")
    if raw.map_id != MapId.ROUTE_11 or (raw.player_x, raw.player_y) != anchor_position:
        raise SSAnneChapterError(
            "Pre-ship training missed its safe return anchor: "
            f"map={raw.map_id!r}, position={(raw.player_x, raw.player_y)!r}."
        )
    exit_battles = 0
    exit_steps = 0
    for _ in range(64):
        returned = reader.read()
        if returned.map_id == MapId.VERMILION_CITY:
            break
        if returned.map_id != MapId.ROUTE_11:
            raise SSAnneChapterError("Pre-ship training return left Route 11.")
        if returned.battle_state == 1:
            try:
                run_adaptive_wild_battle(
                    reader,
                    executor,
                    _pre_ship_training_move_slot,
                    expected_map=MapId.ROUTE_11,
                    intent=PRE_SHIP_TRAINING_INTENT,
                    label="Route 11 training return",
                    timing=timing.battle_runtime,
                    unknown_cancel_interval=10_000,
                )
            except BattleRuntimeError as error:
                raise SSAnneChapterError(str(error)) from error
            exit_battles += 1
            continue
        executor.execute(MacroAction(MacroActionKind.MOVE, "left"))
        _wait(executor, timing.movement_retry_wait_frames)
        exit_steps += 1
    else:
        raise SSAnneChapterError("Pre-ship training could not return to Vermilion.")
    if returned.player_x is None or returned.player_y != 14 or returned.player_x < 23:
        raise SSAnneChapterError(
            "Pre-ship training missed the Vermilion east boundary: "
            f"{(returned.player_x, returned.player_y)!r}."
        )
    _move(
        executor,
        reader,
        ("left",) * (returned.player_x - 23),
        timing,
        "Vermilion Mart exterior return",
    )
    _require_position(
        reader.read(),
        MapId.VERMILION_CITY,
        (23, 14),
        "Vermilion Mart exterior return",
    )
    _move(
        executor,
        reader,
        MART_TO_CENTER_EXTERIOR_DIRECTIONS,
        timing,
        "Vermilion Center exterior return",
    )
    _move(executor, reader, ("up",), timing, "Vermilion training Center")
    _wait(executor, timing.transition_wait_frames)
    _require_position(reader.read(), MapId.VERMILION_POKECENTER, (3, 7), "training Center")
    _move(executor, reader, ("up",) * 4, timing, "training nurse")
    _confirm_pulses(executor, timing.heal_dialogue_pulses, timing.dialogue_wait_frames)
    healed = reader.read()
    if healed.first_party_hp != healed.first_party_max_hp or healed.first_party_status != 0:
        raise SSAnneChapterError("Pre-ship training Center recovery did not restore the lead.")
    return healed, exit_battles, exit_steps


def _pre_ship_training_move_slot(raw: RawGameState) -> int:
    if raw.battle_state != 1 or raw.map_id != MapId.ROUTE_11:
        raise SSAnneChapterError("Pre-ship training move policy lacks a Route 11 wild battle.")
    moves = raw.first_party_moves or ()
    pp = raw.first_party_pp or ()
    for slot in PRE_SHIP_TRAINING_POLICY.preferred_move_slots:
        if (
            slot <= len(moves)
            and slot <= len(pp)
            and moves[slot - 1]
            and (pp[slot - 1] & 0x3F)
            and raw.player_disabled_move_slot != slot
        ):
            return slot
    raise SSAnneChapterError("Pre-ship training has no legal preferred move.")


def _pre_ship_training_directive(
    raw: RawGameState,
    observation: TrainingObservation,
) -> TrainingDirective:
    """Apply the bounded curriculum to Route 11's lower-level encounters."""

    return choose_training_directive(observation, PRE_SHIP_TRAINING_POLICY)


def _pre_ship_training_step_outcome(
    *,
    current: tuple[int, int],
    next_position: tuple[int | None, int | None],
    in_battle: bool,
    direction: str,
    prior_bounce_direction: str | None,
    opposite: dict[str, str],
) -> tuple[bool, str | None]:
    """Preserve a known return step when an encounter starts before movement."""

    if next_position != current:
        return True, opposite[direction]
    if in_battle:
        return True, prior_bounce_direction
    return False, prior_bounce_direction


def _require_position(
    raw: RawGameState,
    map_id: MapId,
    position: tuple[int, int],
    label: str,
) -> None:
    if raw.map_id != map_id or (raw.player_x, raw.player_y) != position:
        raise SSAnneChapterError(
            f"{label} mismatch: map={raw.map_id!r}, position={(raw.player_x, raw.player_y)!r}."
        )


class _PauseForSSAnneRivalPotion(BattleControlRequest):
    def __init__(self, item: ItemId = ItemId.POTION) -> None:
        self.item = item
        super().__init__(BattleAction.recovery())


def _run_ss_anne_rival_with_potion(
    reader: PokemonRedStateReader,
    executor: _CountingExecutor,
    emulator: EmulatorState,
    timing: SSAnneTiming,
) -> RawGameState:
    """Spend retained Potions only at a live, bounded HP threshold."""

    starting_reserve = _bag_quantity(emulator, ItemId.POTION)
    starting_super_potions = _bag_quantity(emulator, ItemId.SUPER_POTION)
    if not (SS_ANNE_RIVAL_POTION_RESERVE <= starting_reserve <= CERULEAN_GYM_START_POTION_RESERVE):
        raise SSAnneChapterError("S.S. Anne rival recovery reserve is outside its bound.")
    if starting_super_potions != SS_ANNE_SUPER_POTION_RESERVE:
        raise SSAnneChapterError("S.S. Anne rival lacks its three-Super-Potion reserve.")

    def guarded_policy(raw: RawGameState) -> int:
        if (
            _bag_quantity(emulator, ItemId.SUPER_POTION) > 0
            and raw.first_party_hp is not None
            and 0 < raw.first_party_hp <= SS_ANNE_SUPER_POTION_RECOVERY_HP
        ):
            raise _PauseForSSAnneRivalPotion(ItemId.SUPER_POTION)
        if (
            _bag_quantity(emulator, ItemId.POTION) > 0
            and raw.first_party_hp is not None
            and 0 < raw.first_party_hp <= 40
        ):
            raise _PauseForSSAnneRivalPotion(ItemId.POTION)
        return _choose_ss_anne_rival_move(raw)

    intent = BattleIntent(
        "obtain_cut",
        battle_plan_id=RedBattlePlanId.SS_ANNE_RIVAL,
        resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
    )
    recoveries = 0
    super_recoveries = 0
    while True:
        try:
            result = run_adaptive_trainer_battle(
                reader,
                executor,
                guarded_policy,
                expected_map=MapId.SS_ANNE_2F,
                intent=intent,
                timing=timing.battle_runtime,
                label="S.S. Anne rival",
            )
        except BattleRuntimeError as error:
            if not isinstance(error.__cause__, _PauseForSSAnneRivalPotion):
                raise SSAnneChapterError(str(error)) from error
            pause = error.__cause__
            if not isinstance(pause, _PauseForSSAnneRivalPotion):
                raise SSAnneChapterError(str(error)) from error
            if pause.item is ItemId.SUPER_POTION:
                if super_recoveries >= starting_super_potions:
                    raise SSAnneChapterError(
                        "S.S. Anne rival exhausted its bounded Super Potion reserve."
                    ) from error
                try:
                    _use_battle_recovery_item(
                        reader,
                        executor,
                        emulator,
                        DEFAULT_CASCADE_TIMING,
                        item=ItemId.SUPER_POTION,
                        heal_amount=SUPER_POTION_HEAL_AMOUNT,
                        max_quantity=SS_ANNE_SUPER_POTION_RESERVE,
                        label="S.S. Anne Super Potion",
                    )
                except CascadeChapterError as recovery_error:
                    raise SSAnneChapterError(str(recovery_error)) from recovery_error
                super_recoveries += 1
                continue
            if recoveries >= starting_reserve:
                raise SSAnneChapterError(
                    "S.S. Anne rival exhausted its bounded Potion reserve."
                ) from error
            try:
                _use_cerulean_rival_potion(
                    reader,
                    executor,
                    emulator,
                    DEFAULT_CASCADE_TIMING,
                )
            except CascadeChapterError as recovery_error:
                raise SSAnneChapterError(str(recovery_error)) from recovery_error
            recoveries += 1
            continue

        if _bag_quantity(emulator, ItemId.POTION) != starting_reserve - recoveries:
            raise SSAnneChapterError(
                "S.S. Anne rival changed its bounded Potion reserve unexpectedly."
            )
        if (
            _bag_quantity(emulator, ItemId.SUPER_POTION)
            != starting_super_potions - super_recoveries
        ):
            raise SSAnneChapterError(
                "S.S. Anne rival changed its bounded Super Potion reserve unexpectedly."
            )
        return result


def _choose_ss_anne_rival_move(state: RawGameState) -> int:
    """Choose a usable species-specific move for the live RIVAL2 party."""

    if (
        state.battle_state != 2
        or state.map_id != MapId.SS_ANNE_2F
        or state.enemy_species_id not in SS_ANNE_RIVAL_SPECIES_IDS
    ):
        raise SSAnneChapterError("S.S. Anne rival policy lacks pinned battle evidence.")
    if state.enemy_species_id == RATICATE_SPECIES_ID:
        candidates = (
            (3, BUBBLEBEAM),
            (4, WATER_GUN_MOVE_ID),
            (1, BITE_MOVE_ID),
            (3, MEGA_PUNCH_MOVE_ID),
        )
    elif state.enemy_species_id == KADABRA_SPECIES_ID:
        candidates = (
            (1, BITE_MOVE_ID),
            (3, BUBBLEBEAM),
            (3, MEGA_PUNCH_MOVE_ID),
            (4, WATER_GUN_MOVE_ID),
        )
    elif state.enemy_species_id == IVYSAUR_SPECIES_ID:
        candidates = (
            (1, BITE_MOVE_ID),
            (3, MEGA_PUNCH_MOVE_ID),
            (4, WATER_GUN_MOVE_ID),
            (3, BUBBLEBEAM),
        )
    else:
        candidates = (
            (3, BUBBLEBEAM),
            (3, MEGA_PUNCH_MOVE_ID),
            (4, WATER_GUN_MOVE_ID),
            (1, BITE_MOVE_ID),
        )
    moves = state.first_party_moves
    pp = state.first_party_pp
    if moves is not None and pp is not None:
        for slot, expected_move in candidates:
            if (
                len(moves) >= slot
                and len(pp) >= slot
                and moves[slot - 1] == expected_move
                and pp[slot - 1] & 0x3F
                and state.player_disabled_move_slot != slot
            ):
                return slot
    raise SSAnneChapterError("S.S. Anne rival policy lacks a usable ranked attack.")


def _checkpoint(
    reader: PokemonRedStateReader,
    tracker: SSAnneProgressTracker,
    expected: SSAnnePhase,
    checkpoint_id: str,
    label: str,
    records: list[SSAnneCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
) -> tuple[RawGameState, SSAnneState]:
    raw = reader.read()
    evidence = reader.read_ss_anne_state(raw)
    try:
        phase = tracker.observe(evidence)
    except SSAnneProgressError as error:
        raise SSAnneChapterError(str(error)) from error
    if phase is not expected:
        raise SSAnneChapterError(f"{label} observed {phase.value!r}, expected {expected.value!r}.")
    records.append(SSAnneCheckpoint(checkpoint_id, label, raw, evidence))
    if progress is not None:
        progress(
            SSAnneProgress(
                checkpoint_id,
                label,
                len(records),
                SS_ANNE_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )
    return raw, evidence


def _confirm_pulses(executor: _CountingExecutor, count: int, frames: int) -> None:
    for _ in range(count):
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, frames)


def _wait(executor: _CountingExecutor, frames: int) -> None:
    executor.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))
