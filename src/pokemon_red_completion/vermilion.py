"""Deterministic Misty-to-Vermilion chapter for the pinned Pokémon Red revision."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_runtime import (
    BattleActionExecutor,
    BattleRuntimeError,
    BattleRuntimeTiming,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.cascade import (
    CENTER_EXIT_DIRECTIONS,
    CENTER_HEAL_APPROACH_DIRECTIONS,
    GYM_TO_CENTER_DIRECTIONS,
    GYM_TRAINER_TO_EXIT_DIRECTIONS,
)
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    MapId,
    PokemonRedStateReader,
    RawGameState,
    VermilionPhase,
    VermilionProgressError,
    VermilionProgressTracker,
    VermilionState,
)

VERMILION_CHECKPOINT_COUNT = 15
MACHOP_SPECIES_ID = 0x6A
DROWZEE_SPECIES_ID = 0x30
QUALIFIED_ROUTE_6_WILDS = (
    (15, 19, 0x24),
    (15, 22, 0x24),
    (15, 26, 0x24),
)


def _directions(value: str) -> tuple[str, ...]:
    return tuple(
        {"U": "up", "D": "down", "L": "left", "R": "right"}[direction]
        for direction in value
    )


GYM_EXIT_DIRECTIONS = ("down", *GYM_TRAINER_TO_EXIT_DIRECTIONS)
GYM_RETURN_DIRECTIONS = _directions("DD" + "R" * 11)
TRASHED_HOUSE_DIRECTIONS = _directions(
    "LLLLLLLLUULLLLLUULLLLLLLLLUUUURRRRRRRRRRRR"
    "UUUUUUUUUUUURDDDDDDDDDDRRUUUUUURRDLDDDDDRD"
    "LLLLDRRRRRR"
)
TRASHED_HOUSE_INTERIOR_DIRECTIONS = _directions("UUUUURU")
ROCKET_TRIGGER_DIRECTIONS = _directions("RRR")
ROCKET_TO_ROUTE_5_DIRECTIONS = _directions(
    "R" * 3 + "D" * 9 + "R" * 3 + "D" * 13 + "L" * 23 + "D" * 5
)
ROUTE_5_TO_UNDERGROUND_DIRECTIONS = _directions(
    "D" * 27 + "R" * 12 + "D" + "R" * 2 + "U"
)
UNDERGROUND_NORTH_INTERIOR_DIRECTIONS = _directions("UURU")
UNDERGROUND_TUNNEL_DIRECTIONS = _directions("D" * 37 + "L" * 3)
UNDERGROUND_SOUTH_EXIT_DIRECTIONS = _directions("DDDD")
ROUTE_6_TO_FIRST_TRAINER_DIRECTIONS = _directions(
    "L" * 2 + "D" * 15 + "L" * 7 + "R" + "D"
)
ROUTE_6_REPLAY_AFTER_WILD_DIRECTIONS = _directions(
    "D" * 10 + "L" * 7 + "RD"
)
VERMILION_ENTRY_DIRECTIONS = _directions("D" * 5)
ROUTE_6_FIRST_TRAINER_TO_SOUTH_BUILDING_DIRECTIONS = _directions(
    "U" + "R" * 6 + "U" * 15 + "R" * 2 + "U"
)
UNDERGROUND_TUNNEL_NORTHBOUND_DIRECTIONS = _directions("U" * 37 + "R" * 3)
ROUTE_5_TO_CERULEAN_DIRECTIONS = _directions(
    "L" * 2 + "U" + "L" * 12 + "U" * 28
)
CERULEAN_SOUTH_TO_CENTER_DIRECTIONS = _directions(
    "U" * 4
    + "R" * 23
    + "U" * 13
    + "L" * 3
    + "U" * 9
    + "L" * 3
    + "R" * 3
    + "D" * 14
    + "L" * 5
    + "U" * 3
    + "L" * 9
    + "U" * 3
)
class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...


class ChapterExecutor(BattleActionExecutor, Protocol):
    def execute(self, action: MacroAction) -> object: ...


class VermilionChapterError(RuntimeError):
    """Raised when the bounded route misses a live semantic gate."""


@dataclass(frozen=True, slots=True)
class VermilionTiming:
    transition_wait_frames: int = 120
    dialogue_wait_frames: int = 240
    rocket_seed_wait_frames: int = 41
    heal_dialogue_pulses: int = 9
    rocket_reward_pulses: int = 10
    route_6_cleanup_pulses: int = 5
    max_trainer_intro_pulses: int = 48
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
            "rocket_seed_wait_frames",
            "heal_dialogue_pulses",
            "rocket_reward_pulses",
            "route_6_cleanup_pulses",
            "max_trainer_intro_pulses",
            "movement_retries",
            "movement_retry_wait_frames",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_VERMILION_TIMING = VermilionTiming()


@dataclass(frozen=True, slots=True)
class VermilionProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[VermilionProgress], None]


@dataclass(frozen=True, slots=True)
class VermilionCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState
    evidence: VermilionState


@dataclass(frozen=True, slots=True)
class Route6WildFleeEvidence:
    initial_battle_state: int
    final_battle_state: int
    map_id: int
    player_x: int
    player_y: int
    enemy_species_id: int
    initial_pp: tuple[int, ...]
    final_pp: tuple[int, ...]
    final_hp: int
    final_status: int
    trainer_events: tuple[bool, ...]
    control_ready: bool

    @property
    def verified(self) -> bool:
        return (
            self.initial_battle_state == 1
            and self.final_battle_state == 0
            and self.map_id == MapId.ROUTE_6
            and self.player_x >= 0
            and self.player_y >= 0
            and self.enemy_species_id > 0
            and self.initial_pp == self.final_pp
            and all((value & 0x3F) > 0 for value in self.final_pp)
            and self.final_hp > 0
            and self.final_status == 0
            and self.trainer_events
            == (False, False, False, False, True, False)
            and self.control_ready
        )

    @property
    def qualified_step_7_pidgey(self) -> bool:
        return (
            self.verified
            and (self.player_x, self.player_y) == (15, 19)
            and self.enemy_species_id == 0x24
        )


@dataclass(frozen=True, slots=True)
class VermilionChapterReport:
    records: tuple[VermilionCheckpoint, ...]
    final_raw: RawGameState
    final_evidence: VermilionState
    route_6_wild_flees: tuple[Route6WildFleeEvidence, ...]
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == VERMILION_CHECKPOINT_COUNT
            and self.final_evidence.vermilion_snapshot
            and tuple(
                (item.player_x, item.player_y, item.enemy_species_id)
                for item in self.route_6_wild_flees
            )
            == QUALIFIED_ROUTE_6_WILDS
            and all(item.verified for item in self.route_6_wild_flees)
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
            "checkpoint_ids": [
                record.checkpoint_id for record in self.records
            ],
            "route": {
                "rocket_battle_observed": any(
                    record.evidence.phase is VermilionPhase.ROCKET_THIEF_BATTLE
                    for record in self.records
                ),
                "tm28_verified": self.final_evidence.tm28_in_bag,
                "route_6_trainer_events": list(
                    self.final_evidence.route_6_trainer_events
                ),
                "wild_flees": [
                    {
                        "battle_state_before": item.initial_battle_state,
                        "battle_state_after": item.final_battle_state,
                        "map_id": item.map_id,
                        "x": item.player_x,
                        "y": item.player_y,
                        "species_id": item.enemy_species_id,
                        "pp_unchanged": item.initial_pp == item.final_pp,
                        "control_ready": item.control_ready,
                    }
                    for item in self.route_6_wild_flees
                ],
                "vermilion_map_id": self.final_raw.map_id,
                "vermilion_x": self.final_raw.player_x,
                "vermilion_y": self.final_raw.player_y,
            },
            "wartortle": {
                "hp": self.final_raw.first_party_hp,
                "max_hp": self.final_raw.first_party_max_hp,
                "status": self.final_raw.first_party_status,
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


def run_vermilion_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    timing: VermilionTiming = DEFAULT_VERMILION_TIMING,
    progress: ProgressSink | None = None,
) -> VermilionChapterReport:
    """Continue a verified Misty victory to stable Vermilion City."""

    start_frames = emulator.frame_count
    chapter_executor = _CountingExecutor(executor)
    starting_raw = reader.read()
    try:
        tracker = VermilionProgressTracker(
            reader.read_cascade_state(starting_raw)
        )
    except VermilionProgressError as error:
        raise VermilionChapterError(str(error)) from error
    records: list[VermilionCheckpoint] = []
    _checkpoint(
        reader,
        tracker,
        VermilionPhase.MISTY_READY,
        "misty_ready",
        "Verified the clean Misty victory boundary",
        records,
        progress,
        emulator,
    )

    _move(chapter_executor, reader, GYM_EXIT_DIRECTIONS, timing, "Gym exit")
    _wait(chapter_executor, timing.transition_wait_frames)
    _move(
        chapter_executor,
        reader,
        GYM_TO_CENTER_DIRECTIONS,
        timing,
        "Cerulean Center",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    _heal(chapter_executor, reader, timing)
    _move(chapter_executor, reader, GYM_RETURN_DIRECTIONS, timing, "Gym corridor")
    _move(
        chapter_executor,
        reader,
        TRASHED_HOUSE_DIRECTIONS,
        timing,
        "trashed house approach",
    )
    _move(chapter_executor, reader, ("up",), timing, "trashed house entry")
    _wait(chapter_executor, timing.transition_wait_frames)
    _checkpoint(
        reader,
        tracker,
        VermilionPhase.TRASHED_HOUSE_ENTERED,
        "trashed_house_entered",
        "Entered the robbed Cerulean house",
        records,
        progress,
        emulator,
    )
    _move(
        chapter_executor,
        reader,
        TRASHED_HOUSE_INTERIOR_DIRECTIONS,
        timing,
        "robbery rear door",
    )
    _move(chapter_executor, reader, ("up",), timing, "robbery rear exit")
    _wait(chapter_executor, timing.transition_wait_frames)
    _checkpoint(
        reader,
        tracker,
        VermilionPhase.ROBBERY_REAR_EXIT,
        "robbery_rear_exit",
        "Exited behind the robbed house",
        records,
        progress,
        emulator,
    )
    _wait(chapter_executor, timing.rocket_seed_wait_frames)
    _move(
        chapter_executor,
        reader,
        ROCKET_TRIGGER_DIRECTIONS,
        timing,
        "Rocket thief trigger",
    )
    _enter_trainer_battle(
        chapter_executor,
        reader,
        timing,
        MapId.CERULEAN_CITY,
        "Rocket thief",
    )
    _checkpoint(
        reader,
        tracker,
        VermilionPhase.ROCKET_THIEF_BATTLE,
        "rocket_thief_battle",
        "Verified the Cerulean Rocket thief battle",
        records,
        progress,
        emulator,
    )
    _battle(
        reader,
        chapter_executor,
        _choose_rocket_move,
        MapId.CERULEAN_CITY,
        timing,
        "Rocket thief",
    )
    _confirm_pulses(
        chapter_executor,
        timing.rocket_reward_pulses,
        timing.dialogue_wait_frames,
    )
    _checkpoint(
        reader,
        tracker,
        VermilionPhase.TM28_OBTAINED,
        "tm28_obtained",
        "Defeated the Rocket thief and obtained TM28",
        records,
        progress,
        emulator,
    )

    _move(
        chapter_executor,
        reader,
        ROCKET_TO_ROUTE_5_DIRECTIONS,
        timing,
        "Cerulean south route",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    _checkpoint(
        reader,
        tracker,
        VermilionPhase.ROUTE_5_REACHED,
        "route_5_reached",
        "Reached Route 5",
        records,
        progress,
        emulator,
    )
    _move(
        chapter_executor,
        reader,
        ROUTE_5_TO_UNDERGROUND_DIRECTIONS,
        timing,
        "Route 5 Underground Path",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    _checkpoint(
        reader,
        tracker,
        VermilionPhase.UNDERGROUND_NORTH_ENTRANCE,
        "underground_north_entrance",
        "Entered the north Underground Path building",
        records,
        progress,
        emulator,
    )
    _move(
        chapter_executor,
        reader,
        UNDERGROUND_NORTH_INTERIOR_DIRECTIONS,
        timing,
        "Underground Path tunnel entry",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    _checkpoint(
        reader,
        tracker,
        VermilionPhase.UNDERGROUND_TUNNEL,
        "underground_tunnel",
        "Entered the north-south Underground Path tunnel",
        records,
        progress,
        emulator,
    )
    _move(
        chapter_executor,
        reader,
        UNDERGROUND_TUNNEL_DIRECTIONS,
        timing,
        "Underground Path southbound",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    _checkpoint(
        reader,
        tracker,
        VermilionPhase.UNDERGROUND_SOUTH_ENTRANCE,
        "underground_south_entrance",
        "Reached the south Underground Path building",
        records,
        progress,
        emulator,
    )
    _move(
        chapter_executor,
        reader,
        UNDERGROUND_SOUTH_EXIT_DIRECTIONS,
        timing,
        "Route 6 exit",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    _checkpoint(
        reader,
        tracker,
        VermilionPhase.ROUTE_6_REACHED,
        "route_6_reached",
        "Reached Route 6",
        records,
        progress,
        emulator,
    )
    _move(
        chapter_executor,
        reader,
        ROUTE_6_TO_FIRST_TRAINER_DIRECTIONS,
        timing,
        "Route 6 lower gap",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    _enter_trainer_battle(
        chapter_executor,
        reader,
        timing,
        MapId.ROUTE_6,
        "Route 6 Jr Trainer F",
    )
    _checkpoint(
        reader,
        tracker,
        VermilionPhase.ROUTE_6_TRAINER_F_BATTLE,
        "route_6_trainer_f_battle",
        "Verified the required Route 6 Jr Trainer F battle",
        records,
        progress,
        emulator,
    )
    _battle(
        reader,
        chapter_executor,
        lambda state: 1,
        MapId.ROUTE_6,
        timing,
        "Route 6 Jr Trainer F",
    )
    _confirm_pulses(
        chapter_executor,
        timing.route_6_cleanup_pulses,
        timing.dialogue_wait_frames,
    )
    _require_route_6_events(
        reader,
        (False, False, False, False, True, False),
        "first Route 6 victory",
    )
    _checkpoint(
        reader,
        tracker,
        VermilionPhase.ROUTE_6_TRAINER_F_DEFEATED,
        "route_6_trainer_f_defeated",
        "Defeated the required Route 6 Jr Trainer F",
        records,
        progress,
        emulator,
    )
    route_6_wild_flees = _backtrack_heal_and_replay(
        chapter_executor,
        reader,
        timing,
    )
    _move(
        chapter_executor,
        reader,
        ("down",),
        timing,
        "second Route 6 trainer trigger",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    _enter_trainer_battle(
        chapter_executor,
        reader,
        timing,
        MapId.ROUTE_6,
        "Route 6 Jr Trainer M",
    )
    _checkpoint(
        reader,
        tracker,
        VermilionPhase.ROUTE_6_TRAINER_M_BATTLE,
        "route_6_trainer_m_battle",
        "Verified the required Route 6 Jr Trainer M battle",
        records,
        progress,
        emulator,
    )
    _battle(
        reader,
        chapter_executor,
        lambda state: 1,
        MapId.ROUTE_6,
        timing,
        "Route 6 Jr Trainer M",
    )
    _confirm_pulses(
        chapter_executor,
        timing.route_6_cleanup_pulses,
        timing.dialogue_wait_frames,
    )
    _require_route_6_events(
        reader,
        (False, False, False, True, True, False),
        "second Route 6 victory",
    )
    _checkpoint(
        reader,
        tracker,
        VermilionPhase.ROUTE_6_TRAINER_M_DEFEATED,
        "route_6_trainer_m_defeated",
        "Defeated the required Route 6 Jr Trainer M",
        records,
        progress,
        emulator,
    )
    _move(
        chapter_executor,
        reader,
        VERMILION_ENTRY_DIRECTIONS,
        timing,
        "Vermilion entrance",
    )
    _wait(chapter_executor, timing.transition_wait_frames)
    final_raw, final_evidence = _checkpoint(
        reader,
        tracker,
        VermilionPhase.VERMILION_REACHED,
        "vermilion_reached",
        "Reached stable Vermilion City",
        records,
        progress,
        emulator,
    )
    report = VermilionChapterReport(
        records=tuple(records),
        final_raw=final_raw,
        final_evidence=final_evidence,
        route_6_wild_flees=route_6_wild_flees,
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=chapter_executor.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise VermilionChapterError(
            "The Misty-to-Vermilion chapter failed its evidence contract."
        )
    return report


def _choose_rocket_move(state: RawGameState) -> int:
    if state.enemy_species_id == MACHOP_SPECIES_ID:
        return 4
    if state.enemy_species_id == DROWZEE_SPECIES_ID:
        return 1 if (state.enemy_hp or 0) > 11 else 4
    raise VermilionChapterError(
        f"Unexpected Rocket thief species {state.enemy_species_id!r}."
    )


def _backtrack_heal_and_replay(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: VermilionTiming,
) -> tuple[Route6WildFleeEvidence, ...]:
    _move(
        executor,
        reader,
        ROUTE_6_FIRST_TRAINER_TO_SOUTH_BUILDING_DIRECTIONS,
        timing,
        "Route 6 healing backtrack",
    )
    _wait(executor, timing.transition_wait_frames)
    _move(
        executor,
        reader,
        UNDERGROUND_NORTH_INTERIOR_DIRECTIONS,
        timing,
        "south Underground Path re-entry",
    )
    _wait(executor, timing.transition_wait_frames)
    _move(
        executor,
        reader,
        UNDERGROUND_TUNNEL_NORTHBOUND_DIRECTIONS,
        timing,
        "Underground Path northbound healing route",
    )
    _wait(executor, timing.transition_wait_frames)
    _move(
        executor,
        reader,
        UNDERGROUND_SOUTH_EXIT_DIRECTIONS,
        timing,
        "north Underground Path building exit",
    )
    _wait(executor, timing.transition_wait_frames)
    _move(
        executor,
        reader,
        ROUTE_5_TO_CERULEAN_DIRECTIONS,
        timing,
        "Route 5 northbound healing route",
    )
    _wait(executor, timing.transition_wait_frames)
    _move(
        executor,
        reader,
        CERULEAN_SOUTH_TO_CENTER_DIRECTIONS,
        timing,
        "Cerulean Center healing route",
    )
    _wait(executor, timing.transition_wait_frames)
    _heal(executor, reader, timing)
    healed = reader.read()
    if (
        healed.map_id != MapId.CERULEAN_CITY
        or healed.player_x != 19
        or healed.player_y != 18
        or healed.first_party_hp != healed.first_party_max_hp
        or healed.first_party_status != 0
    ):
        raise VermilionChapterError(
            "Route 6 recovery failed its healed Cerulean replay gate."
        )
    _move(
        executor,
        reader,
        GYM_RETURN_DIRECTIONS,
        timing,
        "Cerulean Gym corridor replay",
    )
    _move(
        executor,
        reader,
        TRASHED_HOUSE_DIRECTIONS,
        timing,
        "trashed house approach replay",
    )
    _move(executor, reader, ("up",), timing, "trashed house re-entry")
    _wait(executor, timing.transition_wait_frames)
    _move(
        executor,
        reader,
        TRASHED_HOUSE_INTERIOR_DIRECTIONS,
        timing,
        "robbery rear door replay",
    )
    _move(executor, reader, ("up",), timing, "robbery rear exit replay")
    _wait(executor, timing.transition_wait_frames)
    _move(
        executor,
        reader,
        ROCKET_TRIGGER_DIRECTIONS,
        timing,
        "Rocket yard replay",
    )
    _move(
        executor,
        reader,
        ROCKET_TO_ROUTE_5_DIRECTIONS,
        timing,
        "Route 5 replay",
    )
    _wait(executor, timing.transition_wait_frames)
    _move(
        executor,
        reader,
        ROUTE_5_TO_UNDERGROUND_DIRECTIONS,
        timing,
        "north Underground Path replay",
    )
    _wait(executor, timing.transition_wait_frames)
    _move(
        executor,
        reader,
        UNDERGROUND_NORTH_INTERIOR_DIRECTIONS,
        timing,
        "Underground Path tunnel replay",
    )
    _wait(executor, timing.transition_wait_frames)
    _move(
        executor,
        reader,
        UNDERGROUND_TUNNEL_DIRECTIONS,
        timing,
        "Underground Path southbound replay",
    )
    _wait(executor, timing.transition_wait_frames)
    _move(
        executor,
        reader,
        UNDERGROUND_SOUTH_EXIT_DIRECTIONS,
        timing,
        "Route 6 replay",
    )
    _wait(executor, timing.transition_wait_frames)
    wild_flees = _replay_route_6_lower_gap(executor, reader, timing)
    replay = reader.read()
    evidence = reader.read_vermilion_state(replay)
    if (
        replay.map_id != MapId.ROUTE_6
        or replay.player_x != 9
        or replay.player_y != 30
        or replay.battle_state != 0
        or replay.first_party_hp != replay.first_party_max_hp
        or replay.first_party_status != 0
        or evidence.route_6_trainer_events
        != (False, False, False, False, True, False)
    ):
        raise VermilionChapterError(
            "Route 6 healing replay failed its persistent return gate."
        )
    return wild_flees


def _replay_route_6_lower_gap(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: VermilionTiming,
) -> tuple[Route6WildFleeEvidence, ...]:
    prefix = _directions("LL" + "D" * 4)

    _move(executor, reader, prefix, timing, "Route 6 lower-gap replay prefix")
    before = reader.read()
    if (
        before.map_id != MapId.ROUTE_6
        or (before.player_x, before.player_y) != (15, 18)
        or before.battle_state != 0
    ):
        raise VermilionChapterError(
            "Route 6 replay missed its exact wild-encounter approach gate."
        )

    encounter = before
    for attempt in range(timing.movement_retries):
        executor.execute(MacroAction(MacroActionKind.MOVE, "down"))
        encounter = reader.read()
        if (
            encounter.battle_state
            or encounter.map_id != before.map_id
            or (encounter.player_x, encounter.player_y)
            != (before.player_x, before.player_y)
        ):
            break
        _wait(executor, timing.movement_retry_wait_frames * (attempt + 1))
    else:
        raise VermilionChapterError(
            "Route 6 replay wild-encounter step was blocked."
        )

    if (
        encounter.battle_state != 1
        or encounter.map_id != MapId.ROUTE_6
        or (encounter.player_x, encounter.player_y) != (15, 19)
        or encounter.enemy_species_id != 0x24
        or encounter.first_party_pp is None
    ):
        raise VermilionChapterError(
            "Route 6 replay missed the qualified step-7 wild Pidgey encounter."
        )
    first_wild_flee = _flee_qualified_route_6_wild(
        executor,
        reader,
        timing,
        encounter,
    )
    additional_wild_flees = _move_route_6_replay_suffix(
        executor,
        reader,
        ROUTE_6_REPLAY_AFTER_WILD_DIRECTIONS,
        timing,
    )
    return (first_wild_flee, *additional_wild_flees)


def _move_route_6_replay_suffix(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    directions: Iterable[str],
    timing: VermilionTiming,
) -> tuple[Route6WildFleeEvidence, ...]:
    expected_wilds = QUALIFIED_ROUTE_6_WILDS[1:]
    wild_flees: list[Route6WildFleeEvidence] = []
    state = reader.read()
    for step_number, direction in enumerate(directions, start=1):
        before = state
        for attempt in range(timing.movement_retries):
            executor.execute(MacroAction(MacroActionKind.MOVE, direction))
            state = reader.read()
            if (
                state.battle_state
                or state.map_id != before.map_id
                or (state.player_x, state.player_y)
                != (before.player_x, before.player_y)
            ):
                break
            _wait(executor, timing.movement_retry_wait_frames * (attempt + 1))
        else:
            raise VermilionChapterError(
                "Route 6 lower-gap replay suffix was blocked at "
                f"{(before.player_x, before.player_y)!r}."
            )

        if state.battle_state:
            if state.battle_state != 1 or len(wild_flees) >= len(expected_wilds):
                raise VermilionChapterError(
                    "Unexpected battle interrupted Route 6 lower-gap replay "
                    f"suffix at step {step_number}: type={state.battle_state}, "
                    f"coordinate={(state.player_x, state.player_y)!r}, "
                    f"enemy={state.enemy_species_id!r}."
                )
            expected_x, expected_y, expected_species = expected_wilds[len(wild_flees)]
            if (
                (state.player_x, state.player_y) != (expected_x, expected_y)
                or state.enemy_species_id != expected_species
            ):
                raise VermilionChapterError(
                    "Route 6 replay exposed an unqualified additional wild battle."
                )
            wild_flees.append(
                _flee_qualified_route_6_wild(executor, reader, timing, state)
            )
            state = reader.read()

    if len(wild_flees) != len(expected_wilds):
        raise VermilionChapterError(
            "Route 6 replay missed its recorded additional wild Pidgey encounters."
        )
    return tuple(wild_flees)


def _flee_qualified_route_6_wild(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: VermilionTiming,
    encounter: RawGameState,
) -> Route6WildFleeEvidence:
    initial_pp = encounter.first_party_pp
    if initial_pp is None:
        raise VermilionChapterError("Route 6 wild flee lacks initial PP evidence.")

    raw = encounter
    expected_map = encounter.map_id
    expected_coordinate = (encounter.player_x, encounter.player_y)
    for _ in range(timing.max_trainer_intro_pulses):
        if raw.battle_state == 0:
            break
        if (
            raw.battle_state != 1
            or raw.map_id != expected_map
            or (raw.player_x, raw.player_y) != expected_coordinate
            or (raw.first_party_hp or 0) <= 0
        ):
            raise VermilionChapterError(
                "Route 6 wild flee lost its qualified battle gate."
            )
        menu = reader.read_battle_menu_state(raw)
        if menu.phase is BattleMenuPhase.UNKNOWN:
            executor.execute(MacroAction(MacroActionKind.CONFIRM))
            _wait(executor, timing.dialogue_wait_frames)
        elif menu.phase is BattleMenuPhase.MOVE:
            executor.execute(MacroAction(MacroActionKind.CANCEL))
            _wait(executor, timing.battle_runtime.menu_wait_frames)
        elif menu.phase is BattleMenuPhase.MAIN:
            command = menu.selected_main_command
            if command == 3:
                executor.execute(MacroAction(MacroActionKind.CONFIRM))
                _wait(executor, timing.dialogue_wait_frames)
            else:
                direction = {0: "right", 1: "right", 2: "down"}.get(command)
                if direction is None:
                    raise VermilionChapterError(
                        "Route 6 wild flee exposed an invalid main-menu cursor."
                    )
                executor.execute(MacroAction(MacroActionKind.MOVE, direction))
                _wait(executor, timing.battle_runtime.menu_wait_frames)
        else:
            raise VermilionChapterError(
                "Route 6 wild flee exposed an unsupported menu phase."
            )
        raw = reader.read()
    else:
        raise VermilionChapterError(
            "Route 6 wild flee exceeded its bounded RUN navigation."
        )

    control_ready = False
    for _ in range(timing.max_trainer_intro_pulses):
        raw = reader.read()
        if reader.read_input_readiness().ready:
            control_ready = True
            break
        _wait(executor, timing.movement_retry_wait_frames)

    evidence = reader.read_vermilion_state(raw)
    final_pp = raw.first_party_pp
    result = Route6WildFleeEvidence(
        initial_battle_state=encounter.battle_state or 0,
        final_battle_state=raw.battle_state if raw.battle_state is not None else -1,
        map_id=raw.map_id if raw.map_id is not None else -1,
        player_x=raw.player_x if raw.player_x is not None else -1,
        player_y=raw.player_y if raw.player_y is not None else -1,
        enemy_species_id=encounter.enemy_species_id or 0,
        initial_pp=initial_pp,
        final_pp=final_pp or (),
        final_hp=raw.first_party_hp or 0,
        final_status=(
            raw.first_party_status if raw.first_party_status is not None else -1
        ),
        trainer_events=evidence.route_6_trainer_events,
        control_ready=control_ready,
    )
    if not result.verified:
        raise VermilionChapterError(
            "Route 6 wild flee failed its post-RUN semantic evidence gate."
        )
    return result


def _move(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    directions: Iterable[str],
    timing: VermilionTiming,
    label: str,
) -> RawGameState:
    state = reader.read()
    for step_number, direction in enumerate(directions, start=1):
        if state.battle_state:
            raise VermilionChapterError(
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
            _wait(
                executor,
                timing.movement_retry_wait_frames * (attempt + 1),
            )
        else:
            raise VermilionChapterError(
                f"{label} was blocked at map {before.map_id!r} "
                f"coordinate {(before.player_x, before.player_y)!r}."
            )
        if state.battle_state:
            raise VermilionChapterError(
                f"Unexpected battle interrupted {label} at step {step_number}: "
                f"type={state.battle_state}, map={state.map_id!r}, "
                f"coordinate={(state.player_x, state.player_y)!r}, "
                f"enemy={state.enemy_species_id!r}."
            )
        if state.first_party_hp == 0:
            raise VermilionChapterError(
                f"Squirtle's lineage fainted during {label}."
            )
    return state


def _heal(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: VermilionTiming,
) -> None:
    if reader.read().map_id != MapId.CERULEAN_POKECENTER:
        raise VermilionChapterError("Cerulean healing route missed the Center.")
    _move(
        executor,
        reader,
        CENTER_HEAL_APPROACH_DIRECTIONS,
        timing,
        "Cerulean nurse",
    )
    _confirm_pulses(
        executor,
        timing.heal_dialogue_pulses,
        timing.dialogue_wait_frames,
    )
    healed = reader.read()
    if (
        healed.first_party_hp != healed.first_party_max_hp
        or healed.first_party_status != 0
        or not all((value & 0x3F) > 0 for value in (healed.first_party_pp or ()))
    ):
        raise VermilionChapterError("Cerulean healing failed its persistent gate.")
    _move(
        executor,
        reader,
        CENTER_EXIT_DIRECTIONS,
        timing,
        "Cerulean Center exit",
    )
    _wait(executor, timing.transition_wait_frames)


def _enter_trainer_battle(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: VermilionTiming,
    expected_map: MapId,
    label: str,
) -> RawGameState:
    for _ in range(timing.max_trainer_intro_pulses):
        raw = reader.read()
        if raw.battle_state == 1:
            raise VermilionChapterError(f"Wild battle replaced {label}.")
        if raw.battle_state == 2:
            return raw
        if raw.map_id != expected_map:
            raise VermilionChapterError(f"{label} left its expected map.")
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.dialogue_wait_frames)
    raise VermilionChapterError(f"{label} missed its bounded battle gate.")


def _battle(
    reader: PokemonRedStateReader,
    executor: _CountingExecutor,
    policy: Callable[[RawGameState], int],
    expected_map: MapId,
    timing: VermilionTiming,
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
        raise VermilionChapterError(str(error)) from error


def _require_route_6_events(
    reader: PokemonRedStateReader,
    expected: tuple[bool, bool, bool, bool, bool, bool],
    label: str,
) -> None:
    raw = reader.read()
    evidence = reader.read_vermilion_state(raw)
    if (
        raw.map_id != MapId.ROUTE_6
        or raw.battle_state != 0
        or raw.first_party_hp == 0
        or evidence.route_6_trainer_events != expected
    ):
        raise VermilionChapterError(f"{label} failed its persistent event gate.")


def _checkpoint(
    reader: PokemonRedStateReader,
    tracker: VermilionProgressTracker,
    expected: VermilionPhase,
    checkpoint_id: str,
    label: str,
    records: list[VermilionCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
) -> tuple[RawGameState, VermilionState]:
    raw = reader.read()
    evidence = reader.read_vermilion_state(raw)
    try:
        phase = tracker.observe(evidence)
    except VermilionProgressError as error:
        raise VermilionChapterError(str(error)) from error
    if phase is not expected:
        raise VermilionChapterError(
            f"Expected {expected.value}, observed {phase.value}."
        )
    records.append(VermilionCheckpoint(checkpoint_id, label, raw, evidence))
    if progress is not None:
        progress(
            VermilionProgress(
                checkpoint_id=checkpoint_id,
                label=label,
                completed=len(records),
                total=VERMILION_CHECKPOINT_COUNT,
                frames_executed=emulator.frame_count,
            )
        )
    return raw, evidence


def _confirm_pulses(
    executor: _CountingExecutor,
    pulses: int,
    wait_frames: int,
) -> None:
    for _ in range(pulses):
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, wait_frames)


def _wait(executor: _CountingExecutor, frames: int) -> None:
    executor.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))
