"""Deterministic Vermilion-to-HM01 chapter for the pinned Pokémon Red ROM."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleRuntimeError,
    BattleRuntimeTiming,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.observation import (
    MEGA_PUNCH_MOVE_ID,
    PIDGEOTTO_SPECIES_ID,
    WATER_GUN_MOVE_ID,
    MapId,
    PokemonRedStateReader,
    RawGameState,
    SSAnnePhase,
    SSAnneProgressError,
    SSAnneProgressTracker,
    SSAnneState,
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


def _directions(value: str) -> tuple[str, ...]:
    return tuple(
        {"U": "up", "D": "down", "L": "left", "R": "right"}[letter]
        for letter in value
    )


VERMILION_TO_CENTER_DIRECTIONS = _directions("DDDLDDLLLLLLLUU")
CENTER_TO_NURSE_DIRECTIONS = _directions("UUUU")
CENTER_EXIT_DIRECTIONS = _directions("DDDDD")
CENTER_TO_HARBOR_DIRECTIONS = _directions(
    "DDD"
    + "R" * 5
    + "DD"
    + "RR"
    + "D" * 5
    + "R" * 12
    + "D" * 12
    + "L" * 6
    + "D"
    + "L" * 5
    + "DDLD"
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

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == SS_ANNE_CHECKPOINT_COUNT
            and self.final_evidence.hm01_snapshot
            and self.saw_rival_battle
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple(
            (record.checkpoint_id, record.label, record.raw)
            for record in self.records
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "obtain_cut",
            "rival_battle_observed": self.saw_rival_battle,
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
        reader, tracker, SSAnnePhase.HEALED, "healed",
        "Restored HP, status, and move PP", records, progress, emulator,
    )
    _move(chapter_executor, reader, CENTER_EXIT_DIRECTIONS, timing, "Vermilion Center exit")
    _wait(chapter_executor, timing.transition_wait_frames)
    _move(chapter_executor, reader, CENTER_TO_HARBOR_DIRECTIONS, timing, "Vermilion harbor")
    _confirm_pulses(chapter_executor, timing.ticket_dialogue_pulses, timing.dialogue_wait_frames)
    _move(chapter_executor, reader, ("down", "down"), timing, "Vermilion dock entry")
    _wait(chapter_executor, timing.transition_wait_frames)
    _checkpoint(
        reader, tracker, SSAnnePhase.DOCK_REACHED, "dock_reached",
        "Passed the ticket guard and reached the dock", records, progress, emulator,
    )

    _move(chapter_executor, reader, DOCK_TO_SHIP_DIRECTIONS, timing, "S.S. Anne entry")
    _wait(chapter_executor, timing.transition_wait_frames)
    _checkpoint(
        reader, tracker, SSAnnePhase.SHIP_1F_REACHED, "ship_1f_reached",
        "Boarded the S.S. Anne", records, progress, emulator,
    )
    _move(chapter_executor, reader, SHIP_1F_TO_2F_DIRECTIONS, timing, "S.S. Anne first floor")
    _wait(chapter_executor, timing.transition_wait_frames)
    _checkpoint(
        reader, tracker, SSAnnePhase.SHIP_2F_REACHED, "ship_2f_reached",
        "Reached the safe second-floor corridor", records, progress, emulator,
    )
    _move(chapter_executor, reader, SHIP_2F_TO_RIVAL_DIRECTIONS, timing, "S.S. Anne rival")
    _enter_rival_battle(chapter_executor, reader, timing)
    _checkpoint(
        reader, tracker, SSAnnePhase.RIVAL_BATTLE, "rival_battle",
        "Verified the live S.S. Anne RIVAL2 battle", records, progress, emulator,
    )
    try:
        run_adaptive_trainer_battle(
            reader,
            chapter_executor,
            _choose_ss_anne_rival_move,
            expected_map=MapId.SS_ANNE_2F,
            intent=BattleIntent(
                "obtain_cut",
                battle_plan_id=RedBattlePlanId.SS_ANNE_RIVAL,
            ),
            timing=timing.battle_runtime,
            label="S.S. Anne rival",
        )
    except BattleRuntimeError as error:
        raise SSAnneChapterError(str(error)) from error
    _checkpoint(
        reader, tracker, SSAnnePhase.RIVAL_DEFEATED, "rival_defeated",
        "Defeated the S.S. Anne rival", records, progress, emulator,
    )

    _move(chapter_executor, reader, RIVAL_TO_CAPTAIN_ROOM_DIRECTIONS, timing, "Captain room")
    _wait(chapter_executor, timing.transition_wait_frames)
    _checkpoint(
        reader, tracker, SSAnnePhase.CAPTAIN_ROOM_REACHED, "captain_room_reached",
        "Reached the Captain's room", records, progress, emulator,
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
    if (
        not rubbed.rubbed_captains_back
        or rubbed.got_hm01
        or rubbed.hm01_in_bag
        or rubbed.cut_fact
    ):
        raise SSAnneChapterError(
            "Captain rub stage failed its exact pre-HM01 semantic gate."
        )
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
        reader, tracker, SSAnnePhase.HM01_OBTAINED, "hm01_obtained",
        "Rubbed the Captain's back and obtained HM01", records, progress, emulator,
    )
    report = SSAnneChapterReport(
        records=tuple(records),
        final_raw=final_raw,
        final_evidence=final_evidence,
        saw_rival_battle=tracker.saw_rival_battle,
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=chapter_executor.actions_executed,
        controller_released=not emulator.pressed_buttons,
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
            if (
                state.map_id != before.map_id
                or (state.player_x, state.player_y)
                != (before.player_x, before.player_y)
            ):
                break
            _wait(executor, timing.movement_retry_wait_frames * (attempt + 1))
        else:
            raise SSAnneChapterError(
                f"{label} was blocked at map {before.map_id!r} "
                f"coordinate {(before.player_x, before.player_y)!r}."
            )
    return state


def _enter_rival_battle(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SSAnneTiming,
) -> RawGameState:
    for _ in range(timing.rival_intro_pulses):
        raw = reader.read()
        if raw.battle_state == 2:
            return raw
        if raw.battle_state:
            raise SSAnneChapterError("A wild battle replaced the S.S. Anne rival.")
        if raw.map_id != MapId.SS_ANNE_2F:
            raise SSAnneChapterError("The rival intro left the S.S. Anne second floor.")
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.rival_intro_wait_frames)
    raise SSAnneChapterError("The rival intro missed its bounded battle gate.")


def _choose_ss_anne_rival_move(state: RawGameState) -> int:
    """Choose a usable species-specific move for the live RIVAL2 party."""

    if (
        state.battle_state != 2
        or state.map_id != MapId.SS_ANNE_2F
        or state.enemy_species_id not in SS_ANNE_RIVAL_SPECIES_IDS
    ):
        raise SSAnneChapterError("S.S. Anne rival policy lacks pinned battle evidence.")
    if state.enemy_species_id == RATICATE_SPECIES_ID:
        slot, expected_move = 4, WATER_GUN_MOVE_ID
    elif state.enemy_species_id == KADABRA_SPECIES_ID:
        slot, expected_move = 1, BITE_MOVE_ID
    else:
        slot, expected_move = 3, MEGA_PUNCH_MOVE_ID
    moves = state.first_party_moves
    pp = state.first_party_pp
    if (
        moves is None
        or pp is None
        or len(moves) < slot
        or len(pp) < slot
        or moves[slot - 1] != expected_move
        or pp[slot - 1] & 0x3F == 0
    ):
        raise SSAnneChapterError(
            f"S.S. Anne rival policy lacks usable move {expected_move:#04x} in slot {slot}."
        )
    return slot


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
        raise SSAnneChapterError(
            f"{label} observed {phase.value!r}, expected {expected.value!r}."
        )
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
