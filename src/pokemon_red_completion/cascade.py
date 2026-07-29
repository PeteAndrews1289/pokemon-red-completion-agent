"""Deterministic Cerulean chapter through a verified Cascade Badge.

The route is pinned to pret/pokered commit
``1e96034092686d006e863cace09e87273051a3d8`` and continues the same clean,
save-free emulator session used by the opening, Pewter, and Mt. Moon chapters.
Every story transition is accepted only through the semantic observation
adapter; movement strings are execution details rather than completion proof.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_policy import choose_cerulean_rival_move_slot
from pokemon_red_completion.battle_runtime import (
    BattleRuntimeError,
    BattleRuntimeTiming,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.cerulean import (
    DEFAULT_CERULEAN_TIMING,
    CeruleanChapterError,
    _finish_battle,
    _select_battle_move,
)
from pokemon_red_completion.misty_policy import choose_misty_move_slot
from pokemon_red_completion.observation import (
    ROUTE_24_REQUIRED_TRAINER_SPECS,
    ROUTE_25_REQUIRED_TRAINER_SPECS,
    CascadePhase,
    CascadeProgressError,
    CascadeProgressTracker,
    CascadeState,
    CeruleanChapterState,
    MapId,
    PokemonRedStateReader,
    RawGameState,
)

CASCADE_CHECKPOINT_COUNT = 22
ROUTE_24_REQUIRED_TRAINER_INDEXES = tuple(
    spec[0] for spec in ROUTE_24_REQUIRED_TRAINER_SPECS
)
ROUTE_25_REQUIRED_TRAINER_INDEXES = tuple(
    spec[0] for spec in ROUTE_25_REQUIRED_TRAINER_SPECS
)


def _directions(compact: str) -> tuple[str, ...]:
    lookup = {"U": "up", "D": "down", "L": "left", "R": "right"}
    return tuple(lookup[direction] for direction in compact)


CERULEAN_TO_CENTER_DIRECTIONS = _directions("DD" + "R" * 19 + "UUU")
CENTER_HEAL_APPROACH_DIRECTIONS = _directions("UUUU")
CENTER_EXIT_DIRECTIONS = _directions("DDDDD")
CENTER_TO_RIVAL_STAGING_DIRECTIONS = _directions(
    "LLUU" + "L" * 9 + "U" * 4 + "R" * 12 + "U" * 5
)
RIVAL_TRIGGER_DIRECTIONS = ("up",)
RIVAL_TO_CENTER_DIRECTIONS = _directions(
    "D" * 6 + "L" * 12 + "D" * 4 + "R" * 9 + "DDRRU"
)
RIVAL_CENTER_NPC_CORRECTION_DIRECTIONS = _directions("DRRRU")
CENTER_TO_ROUTE_24_WAIT_STAGING_DIRECTIONS = _directions("LLUUL")
CENTER_TO_ROUTE_24_STAGING_CORRECTION_DIRECTIONS = ("left",)
CENTER_TO_ROUTE_24_DIRECTIONS = _directions("L" * 8 + "U" * 4 + "R" * 12 + "U" * 13)
ROUTE_24_TRAINER_SEGMENTS = tuple(
    _directions(segment)
    for segment in ("U" * 4, "UURU", "UULU", "UURU", "UULU")
)
ROUTE_24_ROCKET_SEGMENT = _directions("UUUU")
ROUTE_24_TO_ROUTE_25_DIRECTIONS = _directions("U" * 6 + "R" * 10 + "U")
ROUTE_25_TRAINER_SEGMENTS = tuple(
    _directions(segment)
    for segment in (
        "R" * 9 + "U" + "RR" + "DD" + "RRR" + "U" + "R" + "U",
        "UUU" + "RR" + "DDD" + "RRR" + "D",
        "RRUURR",
        "R" * 8 + "U" + "R" * 5,
    )
)
ROUTE_25_TO_BILL_DIRECTIONS = _directions("R" * 8 + "UU")
BILL_TO_POKEMON_DIRECTIONS = _directions("UURRR")
BILL_TO_PC_DIRECTIONS = _directions("LLLLU")
BILL_PC_TO_HUMAN_DIRECTIONS = _directions("RRRU")
BILL_EXIT_DIRECTIONS = _directions("DLDD")
BILL_TO_CENTER_SEGMENTS = tuple(
    _directions(segment)
    for segment in (
        "D" + "L" * 8,
        "L" * 5 + "D" + "L" * 8,
        "LLDDLL",
        "U" + "LLL" + "UUU" + "LL" + "DDD",
        "DLD" + "LLL" + "UU" + "LL" + "D" + "L" * 9,
        "D" + "L" * 10 + "D" * 6,
        "D" * 4,
        "DRDD",
        "DLDD",
        "DRDD",
        "DLDD",
        "D" * 4,
        "D",
        "D" * 12 + "L" * 12 + "D" * 4 + "R" * 9 + "DDRRU",
    )
)
BILL_RETURN_WAIT_SEGMENTS = frozenset({6, 13, 14})
CENTER_TO_GYM_DIRECTIONS = _directions("DD" + "R" * 11 + "U")
GYM_TRAINER_DIRECTIONS = _directions(
    "U" * 5 + "LL" + "UUU" + "R" * 5 + "UU" + "LL"
)
GYM_TRAINER_TO_EXIT_DIRECTIONS = _directions(
    "RR" + "DD" + "L" * 5 + "DDD" + "RR" + "D" * 6
)
GYM_TO_CENTER_DIRECTIONS = _directions("L" * 11 + "UUU")
GYM_TRAINER_TO_MISTY_DIRECTIONS = _directions("UL")


class CascadeChapterError(RuntimeError):
    """Raised when the bounded Cerulean-to-Misty chapter misses a gate."""


class ActionExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class EmulatorState(Protocol):
    frame_count: int

    @property
    def pressed_buttons(self) -> frozenset[str]: ...


@dataclass(frozen=True, slots=True)
class CascadeTiming:
    transition_wait_frames: int = 120
    dialogue_wait_frames: int = 240
    rival_seed_wait_frames: int = 41
    misty_seed_wait_frames: int = 2
    route_24_npc_wait_frames: int = 240
    heal_dialogue_pulses: int = 9
    post_battle_cleanup_pulses: int = 1
    gym_trainer_cleanup_pulses: int = 3
    bill_ticket_cleanup_pulses: int = 9
    misty_reward_pulses: int = 9
    max_trainer_intro_pulses: int = 48
    max_bill_phase_pulses: int = 24
    max_route_24_npc_attempts: int = 4
    battle_runtime: BattleRuntimeTiming = BattleRuntimeTiming(
        max_runtime_pulses=720,
        max_main_navigation_pulses=6,
        max_move_menu_transition_pulses=6,
        max_move_navigation_pulses=6,
        max_pp_confirmation_pulses=8,
        max_attack_confirmation_pulses=4,
        max_post_attack_transition_pulses=12,
    )

    def __post_init__(self) -> None:
        for name in (
            "transition_wait_frames",
            "dialogue_wait_frames",
            "rival_seed_wait_frames",
            "misty_seed_wait_frames",
            "route_24_npc_wait_frames",
            "heal_dialogue_pulses",
            "post_battle_cleanup_pulses",
            "gym_trainer_cleanup_pulses",
            "bill_ticket_cleanup_pulses",
            "misty_reward_pulses",
            "max_trainer_intro_pulses",
            "max_bill_phase_pulses",
            "max_route_24_npc_attempts",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.battle_runtime, BattleRuntimeTiming):
            raise ValueError("battle_runtime must be BattleRuntimeTiming")


DEFAULT_CASCADE_TIMING = CascadeTiming()


@dataclass(frozen=True, slots=True)
class CascadeProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[CascadeProgress], None]


@dataclass(frozen=True, slots=True)
class CascadeCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState
    evidence: CascadeState


@dataclass(frozen=True, slots=True)
class CascadeChapterReport:
    starting_cerulean_evidence: CeruleanChapterState
    records: tuple[CascadeCheckpoint, ...]
    final_raw: RawGameState
    final_evidence: CascadeState
    observed_route_24_trainers: tuple[int, ...]
    observed_route_25_trainers: tuple[int, ...]
    saw_rival_battle: bool
    rival_defeated: bool
    saw_nugget_rocket_battle: bool
    nugget_rocket_defeated: bool
    bills_house_left: bool
    saw_cerulean_gym_trainer_battle: bool
    cerulean_gym_trainer_defeated: bool
    saw_misty_battle: bool
    misty_defeated: bool
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            self.starting_cerulean_evidence.cerulean_snapshot
            and len(self.records) == CASCADE_CHECKPOINT_COUNT
            and self.observed_route_24_trainers
            == ROUTE_24_REQUIRED_TRAINER_INDEXES
            and self.observed_route_25_trainers
            == ROUTE_25_REQUIRED_TRAINER_INDEXES
            and self.saw_rival_battle
            and self.rival_defeated
            and self.saw_nugget_rocket_battle
            and self.nugget_rocket_defeated
            and self.bills_house_left
            and self.saw_cerulean_gym_trainer_battle
            and self.cerulean_gym_trainer_defeated
            and self.saw_misty_battle
            and self.misty_defeated
            and self.final_evidence.misty_victory_snapshot
            and self.final_raw.first_party_status == 0
            and (self.final_raw.first_party_hp or 0) > 0
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
            "route": {
                "route_24_trainers": list(self.observed_route_24_trainers),
                "route_25_trainers": list(self.observed_route_25_trainers),
                "rival_battle_observed": self.saw_rival_battle,
                "nugget_rocket_battle_observed": self.saw_nugget_rocket_battle,
                "bill_help_verified": self.bills_house_left,
                "gym_trainer_battle_observed": self.saw_cerulean_gym_trainer_battle,
                "misty_battle_observed": self.saw_misty_battle,
            },
            "cascade": {
                "victory_verified": self.final_evidence.misty_victory_snapshot,
                "badge_verified": (
                    self.final_evidence.cascade_badge
                    and self.final_evidence.cascade_badge_mirror
                ),
                "tm11_verified": (
                    self.final_evidence.got_tm11
                    and self.final_evidence.tm11_in_bag
                ),
                "ss_ticket_verified": (
                    self.final_evidence.got_ss_ticket
                    and self.final_evidence.ss_ticket_in_bag
                ),
                "wartortle_level": self.final_raw.first_party_level,
                "wartortle_hp": self.final_raw.first_party_hp,
                "wartortle_max_hp": self.final_raw.first_party_max_hp,
                "wartortle_status": self.final_raw.first_party_status,
            },
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


class _CountingChapterExecutor:
    def __init__(self, executor: ActionExecutor) -> None:
        self._executor = executor
        self.actions_executed = 0

    def execute(self, action: MacroAction) -> object:
        result = self._executor.execute(action)
        self.actions_executed += 1
        return result


def run_cascade_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ActionExecutor,
    *,
    timing: CascadeTiming = DEFAULT_CASCADE_TIMING,
    progress: ProgressSink | None = None,
) -> CascadeChapterReport:
    """Continue the clean run from Cerulean arrival through Misty's rewards."""

    start_frames = emulator.frame_count
    chapter_executor = _CountingChapterExecutor(executor)
    starting_raw = reader.read()
    starting_evidence = reader.read_cerulean_chapter_state(starting_raw)
    try:
        tracker = CascadeProgressTracker(starting_evidence)
    except CascadeProgressError as error:
        raise CascadeChapterError(str(error)) from error

    records: list[CascadeCheckpoint] = []
    _observe(
        reader,
        tracker,
        CascadePhase.CERULEAN_READY,
        records=None,
    )

    _move(chapter_executor, reader, CERULEAN_TO_CENTER_DIRECTIONS, "Cerulean Center")
    _wait(chapter_executor, timing.transition_wait_frames)
    _heal(chapter_executor, reader, timing)
    _move(
        chapter_executor,
        reader,
        CENTER_TO_RIVAL_STAGING_DIRECTIONS,
        "Cerulean rival staging",
    )
    _wait(chapter_executor, timing.rival_seed_wait_frames)
    _move(
        chapter_executor,
        reader,
        RIVAL_TRIGGER_DIRECTIONS,
        "Cerulean rival trigger",
        allow_trainer_trigger=True,
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    _enter_trainer_battle(
        chapter_executor,
        reader,
        timing,
        MapId.CERULEAN_CITY,
        "Cerulean rival",
    )
    _checkpoint(
        reader,
        tracker,
        CascadePhase.RIVAL_BATTLE,
        "cerulean_rival_battle",
        "Verified the live Cerulean rival battle",
        records,
        progress,
        emulator,
    )
    _run_battle(
        reader,
        chapter_executor,
        choose_cerulean_rival_move_slot,
        MapId.CERULEAN_CITY,
        timing,
        "Cerulean rival",
    )
    _confirm_pulses(
        chapter_executor,
        timing.post_battle_cleanup_pulses,
        timing.dialogue_wait_frames,
    )
    _checkpoint(
        reader,
        tracker,
        CascadePhase.RIVAL_DEFEATED,
        "cerulean_rival_defeated",
        "Defeated the Cerulean rival",
        records,
        progress,
        emulator,
    )

    _move(chapter_executor, reader, RIVAL_TO_CENTER_DIRECTIONS, "rival recovery")
    _wait(chapter_executor, timing.transition_wait_frames)
    recovery = reader.read()
    if (
        recovery.map_id == MapId.CERULEAN_CITY
        and recovery.player_x == 16
        and recovery.player_y == 17
    ):
        _move(
            chapter_executor,
            reader,
            RIVAL_CENTER_NPC_CORRECTION_DIRECTIONS,
            "rival recovery NPC correction",
        )
        _wait(chapter_executor, timing.transition_wait_frames)
    _heal(chapter_executor, reader, timing)
    _enter_route_24(chapter_executor, reader, timing)

    route_24_prefix: tuple[str, ...] = ()
    for position, (trainer_index, segment) in enumerate(
        zip(
            ROUTE_24_REQUIRED_TRAINER_INDEXES,
            ROUTE_24_TRAINER_SEGMENTS,
            strict=True,
        )
    ):
        route_24_prefix += segment
        _move(
            chapter_executor,
            reader,
            segment,
            f"Route 24 trainer {trainer_index}",
            allow_trainer_trigger=True,
        )
        _wait(chapter_executor, timing.transition_wait_frames)
        _enter_trainer_battle(
            chapter_executor,
            reader,
            timing,
            MapId.ROUTE_24,
            f"Route 24 trainer {trainer_index}",
        )
        _checkpoint(
            reader,
            tracker,
            CascadePhase.ROUTE_24_TRAINER_BATTLE,
            f"route_24_trainer_{trainer_index}",
            f"Verified Route 24 trainer {trainer_index}",
            records,
            progress,
            emulator,
        )
        _run_fixed_slot_battle(
            reader,
            chapter_executor,
            4,
            MapId.ROUTE_24,
            timing,
            f"Route 24 trainer {trainer_index}",
        )
        if position == 2:
            _recover_route_24(
                chapter_executor,
                reader,
                timing,
                route_24_prefix,
            )

    _move(
        chapter_executor,
        reader,
        ROUTE_24_ROCKET_SEGMENT,
        "Nugget Rocket trigger",
        allow_trainer_trigger=True,
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    _enter_trainer_battle(
        chapter_executor,
        reader,
        timing,
        MapId.ROUTE_24,
        "Nugget Rocket",
    )
    _checkpoint(
        reader,
        tracker,
        CascadePhase.NUGGET_ROCKET_BATTLE,
        "nugget_rocket_battle",
        "Verified the Nugget Rocket battle and reward",
        records,
        progress,
        emulator,
    )
    _run_fixed_slot_battle(
        reader,
        chapter_executor,
        4,
        MapId.ROUTE_24,
        timing,
        "Nugget Rocket",
    )
    _checkpoint(
        reader,
        tracker,
        CascadePhase.NUGGET_ROCKET_DEFEATED,
        "nugget_rocket_defeated",
        "Defeated the Nugget Rocket",
        records,
        progress,
        emulator,
    )
    _recover_route_24(
        chapter_executor,
        reader,
        timing,
        route_24_prefix + ROUTE_24_ROCKET_SEGMENT,
    )

    _move(
        chapter_executor,
        reader,
        ROUTE_24_TO_ROUTE_25_DIRECTIONS,
        "Route 25 entry",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    for trainer_index, segment in zip(
        ROUTE_25_REQUIRED_TRAINER_INDEXES,
        ROUTE_25_TRAINER_SEGMENTS,
        strict=True,
    ):
        _move(
            chapter_executor,
            reader,
            segment,
            f"Route 25 trainer {trainer_index}",
            allow_trainer_trigger=True,
        )
        _wait(chapter_executor, timing.transition_wait_frames)
        _enter_trainer_battle(
            chapter_executor,
            reader,
            timing,
            MapId.ROUTE_25,
            f"Route 25 trainer {trainer_index}",
        )
        _checkpoint(
            reader,
            tracker,
            CascadePhase.ROUTE_25_TRAINER_BATTLE,
            f"route_25_trainer_{trainer_index}",
            f"Verified Route 25 trainer {trainer_index}",
            records,
            progress,
            emulator,
        )
        _run_fixed_slot_battle(
            reader,
            chapter_executor,
            1 if trainer_index == 5 else 4,
            MapId.ROUTE_25,
            timing,
            f"Route 25 trainer {trainer_index}",
        )

    _move(chapter_executor, reader, ROUTE_25_TO_BILL_DIRECTIONS, "Bill's House")
    _wait(chapter_executor, timing.transition_wait_frames)
    _move(chapter_executor, reader, BILL_TO_POKEMON_DIRECTIONS, "Pokémon Bill")
    chapter_executor.execute(MacroAction(MacroActionKind.INTERACT))
    _wait(chapter_executor, timing.dialogue_wait_frames)
    _advance_dialogue_phases(
        chapter_executor,
        reader,
        tracker,
        (CascadePhase.BILL_REQUESTED_HELP,),
        (("bill_requested_help", "Verified Bill's request for help"),),
        records,
        progress,
        emulator,
        timing,
    )

    _move(chapter_executor, reader, BILL_TO_PC_DIRECTIONS, "Bill's separator PC")
    chapter_executor.execute(MacroAction(MacroActionKind.INTERACT))
    _wait(chapter_executor, timing.dialogue_wait_frames)
    _advance_dialogue_phases(
        chapter_executor,
        reader,
        tracker,
        (
            CascadePhase.BILL_CELL_SEPARATOR_USED,
            CascadePhase.BILL_RESTORED,
        ),
        (
            ("bill_cell_separator_used", "Used Bill's cell separator"),
            ("bill_restored", "Restored Bill's human form"),
        ),
        records,
        progress,
        emulator,
        timing,
    )

    _move(chapter_executor, reader, BILL_PC_TO_HUMAN_DIRECTIONS, "human Bill")
    chapter_executor.execute(MacroAction(MacroActionKind.INTERACT))
    _wait(chapter_executor, timing.dialogue_wait_frames)
    _advance_dialogue_phases(
        chapter_executor,
        reader,
        tracker,
        (CascadePhase.SS_TICKET_OBTAINED,),
        (("ss_ticket_obtained", "Received the S.S. Ticket"),),
        records,
        progress,
        emulator,
        timing,
    )
    _confirm_pulses(
        chapter_executor,
        timing.bill_ticket_cleanup_pulses,
        timing.dialogue_wait_frames,
    )
    _move(chapter_executor, reader, BILL_EXIT_DIRECTIONS, "Bill's House exit")
    _wait(chapter_executor, timing.transition_wait_frames)
    _checkpoint(
        reader,
        tracker,
        CascadePhase.BILLS_HOUSE_LEFT,
        "bills_house_left",
        "Left Bill's House with the S.S. Ticket",
        records,
        progress,
        emulator,
    )

    for position, segment in enumerate(BILL_TO_CENTER_SEGMENTS, start=1):
        _move(
            chapter_executor,
            reader,
            segment,
            f"Bill-to-Cerulean return segment {position}",
        )
        if position in BILL_RETURN_WAIT_SEGMENTS:
            _wait(chapter_executor, timing.transition_wait_frames)
    _heal(chapter_executor, reader, timing)
    _enter_gym(chapter_executor, reader, timing)

    _move(
        chapter_executor,
        reader,
        GYM_TRAINER_DIRECTIONS,
        "Cerulean Gym trainer",
        allow_trainer_trigger=True,
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    _enter_trainer_battle(
        chapter_executor,
        reader,
        timing,
        MapId.CERULEAN_GYM,
        "Cerulean Gym trainer",
    )
    _checkpoint(
        reader,
        tracker,
        CascadePhase.CERULEAN_GYM_TRAINER_BATTLE,
        "cerulean_gym_trainer_battle",
        "Verified the mandatory Cerulean Gym trainer",
        records,
        progress,
        emulator,
    )
    _run_fixed_slot_battle(
        reader,
        chapter_executor,
        1,
        MapId.CERULEAN_GYM,
        timing,
        "Cerulean Gym trainer",
    )
    _checkpoint(
        reader,
        tracker,
        CascadePhase.CERULEAN_GYM_TRAINER_DEFEATED,
        "cerulean_gym_trainer_defeated",
        "Defeated the mandatory Cerulean Gym trainer",
        records,
        progress,
        emulator,
    )
    _confirm_pulses(
        chapter_executor,
        timing.gym_trainer_cleanup_pulses,
        timing.dialogue_wait_frames,
    )

    _move(
        chapter_executor,
        reader,
        GYM_TRAINER_TO_EXIT_DIRECTIONS,
        "Cerulean Gym recovery exit",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    _move(chapter_executor, reader, GYM_TO_CENTER_DIRECTIONS, "Cerulean Center return")
    _wait(chapter_executor, timing.transition_wait_frames)
    _heal(chapter_executor, reader, timing)
    _enter_gym(chapter_executor, reader, timing)
    _move(
        chapter_executor,
        reader,
        GYM_TRAINER_DIRECTIONS,
        "Misty row return",
    )
    _move(
        chapter_executor,
        reader,
        GYM_TRAINER_TO_MISTY_DIRECTIONS,
        "Misty staging",
    )
    _wait(chapter_executor, timing.misty_seed_wait_frames)
    chapter_executor.execute(MacroAction(MacroActionKind.INTERACT))
    _wait(chapter_executor, timing.dialogue_wait_frames)
    _enter_trainer_battle(
        chapter_executor,
        reader,
        timing,
        MapId.CERULEAN_GYM,
        "Misty",
    )
    _checkpoint(
        reader,
        tracker,
        CascadePhase.MISTY_BATTLE,
        "misty_battle",
        "Verified the live Misty battle",
        records,
        progress,
        emulator,
    )
    _run_battle(
        reader,
        chapter_executor,
        choose_misty_move_slot,
        MapId.CERULEAN_GYM,
        timing,
        "Misty",
    )
    _confirm_pulses(
        chapter_executor,
        timing.misty_reward_pulses,
        timing.dialogue_wait_frames,
    )
    final_raw, final_evidence = _checkpoint(
        reader,
        tracker,
        CascadePhase.MISTY_DEFEATED,
        "misty_defeated",
        "Defeated Misty and verified the Cascade Badge and TM11",
        records,
        progress,
        emulator,
    )

    report = CascadeChapterReport(
        starting_cerulean_evidence=starting_evidence,
        records=tuple(records),
        final_raw=final_raw,
        final_evidence=final_evidence,
        observed_route_24_trainers=tracker.observed_route_24_trainers,
        observed_route_25_trainers=tracker.observed_route_25_trainers,
        saw_rival_battle=tracker.saw_rival_battle,
        rival_defeated=tracker.rival_defeated,
        saw_nugget_rocket_battle=tracker.saw_nugget_rocket_battle,
        nugget_rocket_defeated=tracker.nugget_rocket_defeated,
        bills_house_left=tracker.bills_house_left,
        saw_cerulean_gym_trainer_battle=tracker.saw_cerulean_gym_trainer_battle,
        cerulean_gym_trainer_defeated=tracker.cerulean_gym_trainer_defeated,
        saw_misty_battle=tracker.saw_misty_battle,
        misty_defeated=tracker.misty_defeated,
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=chapter_executor.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise CascadeChapterError(
            "The Cerulean-to-Cascade chapter failed its public evidence contract."
        )
    return report


def _move(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    directions: Iterable[str],
    label: str,
    *,
    allow_trainer_trigger: bool = False,
) -> RawGameState:
    direction_list = tuple(directions)
    state = reader.read()
    for step, direction in enumerate(direction_list, start=1):
        if state.battle_state:
            raise CascadeChapterError(
                f"Unexpected battle interrupted {label} before step {step}."
            )
        executor.execute(MacroAction(MacroActionKind.MOVE, direction))
        state = reader.read()
        allowed = (
            allow_trainer_trigger
            and step == len(direction_list)
            and state.battle_state == 2
        )
        if state.battle_state and not allowed:
            raise CascadeChapterError(
                f"Unexpected battle interrupted {label} at step {step}."
            )
        if state.first_party_hp == 0:
            raise CascadeChapterError(f"Squirtle's lineage fainted during {label}.")
    return state


def _heal(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: CascadeTiming,
) -> None:
    raw = reader.read()
    if raw.map_id != MapId.CERULEAN_POKECENTER:
        raise CascadeChapterError("Cerulean healing route missed the Pokémon Center.")
    _move(executor, reader, CENTER_HEAL_APPROACH_DIRECTIONS, "Cerulean nurse")
    _confirm_pulses(
        executor,
        timing.heal_dialogue_pulses,
        timing.dialogue_wait_frames,
    )
    healed = reader.read()
    current_pp = tuple(value & 0x3F for value in (healed.first_party_pp or ()))
    learned_pp = tuple(
        value
        for move, value in zip(
            healed.first_party_moves or (),
            current_pp,
            strict=False,
        )
        if move
    )
    if (
        healed.first_party_hp is None
        or healed.first_party_hp != healed.first_party_max_hp
        or healed.first_party_status != 0
        or not learned_pp
        or not all(value > 0 for value in learned_pp)
    ):
        raise CascadeChapterError("Cerulean healing failed its persistent gate.")
    _move(executor, reader, CENTER_EXIT_DIRECTIONS, "Cerulean Center exit")
    _wait(executor, timing.transition_wait_frames)


def _enter_route_24(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: CascadeTiming,
) -> None:
    _move(
        executor,
        reader,
        CENTER_TO_ROUTE_24_WAIT_STAGING_DIRECTIONS,
        "Route 24 NPC wait staging",
    )
    staging = reader.read()
    if (
        staging.map_id == MapId.CERULEAN_CITY
        and staging.player_x == 17
        and staging.player_y == 16
    ):
        _wait(executor, timing.route_24_npc_wait_frames)
        _move(
            executor,
            reader,
            CENTER_TO_ROUTE_24_STAGING_CORRECTION_DIRECTIONS,
            "Route 24 NPC staging correction",
        )
        staging = reader.read()
    if (
        staging.map_id != MapId.CERULEAN_CITY
        or staging.player_x != 16
        or staging.player_y != 16
    ):
        raise CascadeChapterError(
            "Route 24 NPC wait missed its stable Cerulean staging tile."
        )
    for attempt in range(1, timing.max_route_24_npc_attempts + 1):
        wait_frames = (
            timing.route_24_npc_wait_frames
            if attempt == 1
            else attempt - 2
        )
        if wait_frames:
            _wait(executor, wait_frames)
        _move(
            executor,
            reader,
            CENTER_TO_ROUTE_24_DIRECTIONS,
            f"Route 24 entry attempt {attempt}",
        )
        _wait(executor, timing.transition_wait_frames)
        reached = reader.read()
        if (
            reached.map_id == MapId.ROUTE_24
            and reached.player_x == 10
            and reached.player_y == 35
        ):
            return
        if (
            reached.map_id != MapId.CERULEAN_CITY
            or reached.player_x != 17
            or reached.player_y != 16
        ):
            break
        _move(
            executor,
            reader,
            CENTER_TO_ROUTE_24_STAGING_CORRECTION_DIRECTIONS,
            "Route 24 retry staging correction",
        )
        corrected = reader.read()
        if corrected.player_x != 16 or corrected.player_y != 16:
            break
    raise CascadeChapterError(
        "Route 24 NPC crossing missed its bounded semantic entry gate."
    )


def _recover_route_24(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: CascadeTiming,
    route_prefix: tuple[str, ...],
) -> None:
    _move(
        executor,
        reader,
        _reverse_directions(route_prefix),
        "Route 24 recovery return",
    )
    _move(executor, reader, ("down",), "Route 24 south transition")
    _wait(executor, timing.transition_wait_frames)
    _move(
        executor,
        reader,
        _directions("D" * 12 + "L" * 12 + "D" * 4 + "R" * 9 + "DDRRU"),
        "Route 24 recovery Center",
    )
    _wait(executor, timing.transition_wait_frames)
    _heal(executor, reader, timing)
    _enter_route_24(executor, reader, timing)
    _move(executor, reader, route_prefix, "Route 24 recovery replay")
    _wait(executor, timing.transition_wait_frames)


def _enter_gym(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: CascadeTiming,
) -> None:
    _move(executor, reader, CENTER_TO_GYM_DIRECTIONS, "Cerulean Gym entry")
    _wait(executor, timing.transition_wait_frames)
    if reader.read().map_id != MapId.CERULEAN_GYM:
        raise CascadeChapterError("Cerulean Gym entry missed its map transition.")


def _enter_trainer_battle(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: CascadeTiming,
    expected_map: MapId,
    label: str,
) -> RawGameState:
    for _ in range(timing.max_trainer_intro_pulses):
        raw = reader.read()
        if raw.battle_state == 1:
            raise CascadeChapterError(f"Unexpected wild battle replaced {label}.")
        if raw.battle_state == 2:
            return raw
        if raw.map_id != expected_map:
            raise CascadeChapterError(f"{label} left its expected map before battle.")
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.dialogue_wait_frames)
    raise CascadeChapterError(f"{label} failed its bounded trainer-battle gate.")


def _run_fixed_slot_battle(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    slot: int,
    expected_map: MapId,
    timing: CascadeTiming,
    label: str,
) -> RawGameState:
    try:
        _select_battle_move(
            executor,
            reader,
            DEFAULT_CERULEAN_TIMING,
            slot=slot,
            label=label,
        )
        return _finish_battle(
            executor,
            reader,
            DEFAULT_CERULEAN_TIMING,
            expected_map,
            label,
        )
    except CeruleanChapterError as error:
        raise CascadeChapterError(str(error)) from error


def _run_battle(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    policy: Callable[[RawGameState], int],
    expected_map: MapId,
    timing: CascadeTiming,
    label: str,
) -> RawGameState:
    try:
        return run_adaptive_trainer_battle(
            reader,
            executor,
            policy,
            expected_map=expected_map,
            timing=timing.battle_runtime,
            label=label,
        )
    except BattleRuntimeError as error:
        raise CascadeChapterError(str(error)) from error


def _advance_dialogue_phases(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    tracker: CascadeProgressTracker,
    expected: tuple[CascadePhase, ...],
    labels: tuple[tuple[str, str], ...],
    records: list[CascadeCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    timing: CascadeTiming,
) -> None:
    position = 0
    for pulse in range(timing.max_bill_phase_pulses + 1):
        raw = reader.read()
        evidence = reader.read_cascade_state(raw)
        if evidence.phase is expected[position]:
            _observe_state(tracker, evidence, expected[position])
            checkpoint_id, label = labels[position]
            _append_checkpoint(
                raw,
                evidence,
                checkpoint_id,
                label,
                records,
                progress,
                emulator,
            )
            position += 1
            if position == len(expected):
                return
        elif evidence.phase in expected[position + 1 :]:
            _observe_state(tracker, evidence, evidence.phase)
        if pulse == timing.max_bill_phase_pulses:
            break
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.dialogue_wait_frames)
    raise CascadeChapterError(
        f"Bill dialogue missed the bounded {expected[position].value} gate."
    )


def _checkpoint(
    reader: PokemonRedStateReader,
    tracker: CascadeProgressTracker,
    expected: CascadePhase,
    checkpoint_id: str,
    label: str,
    records: list[CascadeCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
) -> tuple[RawGameState, CascadeState]:
    raw, evidence = _observe(reader, tracker, expected, records=None)
    _append_checkpoint(
        raw,
        evidence,
        checkpoint_id,
        label,
        records,
        progress,
        emulator,
    )
    return raw, evidence


def _observe(
    reader: PokemonRedStateReader,
    tracker: CascadeProgressTracker,
    expected: CascadePhase,
    records: object | None,
) -> tuple[RawGameState, CascadeState]:
    del records
    raw = reader.read()
    evidence = reader.read_cascade_state(raw)
    _observe_state(tracker, evidence, expected)
    return raw, evidence


def _observe_state(
    tracker: CascadeProgressTracker,
    evidence: CascadeState,
    expected: CascadePhase,
) -> None:
    try:
        phase = tracker.observe(evidence)
    except CascadeProgressError as error:
        raise CascadeChapterError(str(error)) from error
    if phase is not expected:
        raise CascadeChapterError(f"Expected {expected.value}, observed {phase.value}.")


def _append_checkpoint(
    raw: RawGameState,
    evidence: CascadeState,
    checkpoint_id: str,
    label: str,
    records: list[CascadeCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
) -> None:
    records.append(CascadeCheckpoint(checkpoint_id, label, raw, evidence))
    if progress is not None:
        progress(
            CascadeProgress(
                checkpoint_id=checkpoint_id,
                label=label,
                completed=len(records),
                total=CASCADE_CHECKPOINT_COUNT,
                frames_executed=emulator.frame_count,
            )
        )


def _confirm_pulses(
    executor: _CountingChapterExecutor,
    pulses: int,
    wait_frames: int,
) -> None:
    for _ in range(pulses):
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, wait_frames)


def _reverse_directions(directions: tuple[str, ...]) -> tuple[str, ...]:
    opposite = {
        "up": "down",
        "down": "up",
        "left": "right",
        "right": "left",
    }
    return tuple(opposite[direction] for direction in reversed(directions))


def _wait(executor: _CountingChapterExecutor, frames: int) -> None:
    executor.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))
