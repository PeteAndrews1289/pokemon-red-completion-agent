"""Deterministic Misty-to-Vermilion chapter for the pinned Pokémon Red revision."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_runtime import (
    BattleActionExecutor,
    BattleIntent,
    BattleResourcePolicy,
    BattleRuntimeError,
    BattleRuntimeTiming,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.cascade import (
    CENTER_EXIT_DIRECTIONS,
    CENTER_HEAL_APPROACH_DIRECTIONS,
    DEFAULT_CASCADE_TIMING,
    GYM_TO_CENTER_DIRECTIONS,
    GYM_TRAINER_TO_EXIT_DIRECTIONS,
    ROCKET_THIEF_POTION_RESERVE,
    SS_ANNE_RIVAL_POTION_RESERVE,
    VERMILION_ROUTE_6_POTION_RESERVE,
    CascadeChapterError,
    _bag_quantity,
    _use_cerulean_rival_potion,
)
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    ItemId,
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
ROUTE_6_JR_TRAINER_F_MOVE_SLOT = 3
ROUTE_6_JR_TRAINER_M_MOVE_SLOT = 3
POST_ROCKET_WARTORTLE_MOVES = (0x2C, 0x27, 0x05, 0x37)
BITE_MOVE_ID = 0x2C
BITE_BASE_PP = 25
ROCKET_THIEF_BATTLE_PLAN_ID = RedBattlePlanId.VERMILION_ROCKET_THIEF
QUALIFIED_ROUTE_6_WILDS = (
    (15, 19, 0x24),
    (15, 22, 0x24),
    (15, 26, 0x24),
)
"""Historical control-lineage encounters; current replay tolerates zero or more wilds."""


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
CERULEAN_WALKER_BLOCK_POSITION = (16, 16)
CERULEAN_WALKER_CLEAR_POSITION = (15, 16)
CERULEAN_WALKER_YIELD_POSITION = (17, 16)
CERULEAN_WALKER_CLEAR_ATTEMPTS = 12
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

    def read_u8(self, address: int) -> int: ...


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
    expected_trainer_events: tuple[bool, ...] = (
        False,
        False,
        False,
        False,
        True,
        False,
    )

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
            and self.trainer_events == self.expected_trainer_events
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
            and self.final_raw.first_party_moves == POST_ROCKET_WARTORTLE_MOVES
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
    _run_rocket_thief_with_potion(
        reader,
        chapter_executor,
        emulator,
        timing,
    )
    _confirm_pulses(
        chapter_executor,
        timing.rocket_reward_pulses,
        timing.dialogue_wait_frames,
    )
    rocket_reward, _ = _checkpoint(
        reader,
        tracker,
        VermilionPhase.TM28_OBTAINED,
        "tm28_obtained",
        "Defeated the Rocket thief and obtained TM28",
        records,
        progress,
        emulator,
    )
    if rocket_reward.first_party_moves != POST_ROCKET_WARTORTLE_MOVES:
        raise VermilionChapterError(
            "Rocket victory did not learn Bite into Wartortle's first move slot."
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
    initial_route_6_wild_flees = _move_route_6_with_wild_flees(
        chapter_executor,
        reader,
        ROUTE_6_TO_FIRST_TRAINER_DIRECTIONS,
        timing,
        expected_trainer_events=(False,) * 6,
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
    _run_route_6_trainer_f_with_potion(
        reader,
        chapter_executor,
        emulator,
        timing,
        RedBattlePlanId.VERMILION_ROUTE_6_JR_TRAINER_F,
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
    route_6_wild_flees = (
        *initial_route_6_wild_flees,
        *_backtrack_heal_and_replay(
            chapter_executor,
            reader,
            timing,
        ),
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
        lambda state: ROUTE_6_JR_TRAINER_M_MOVE_SLOT,
        MapId.ROUTE_6,
        timing,
        "Route 6 Jr Trainer M",
        RedBattlePlanId.VERMILION_ROUTE_6_JR_TRAINER_M,
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
        moves = state.first_party_moves or ()
        pp = state.first_party_pp or ()
        # One fresh Bite wins enough tempo to survive, but Drowzee can then
        # disable it. Its exact PP decrement is the semantic one-use latch.
        if (
            len(moves) >= 1
            and len(pp) >= 1
            and moves[0] == BITE_MOVE_ID
            and (pp[0] & 0x3F) == BITE_BASE_PP
        ):
            return 1
        for slot in (3, 1, 4):
            if (
                len(pp) >= slot
                and (pp[slot - 1] & 0x3F) > 0
                and state.player_disabled_move_slot != slot
            ):
                return slot
        raise VermilionChapterError("Rocket thief Drowzee left no usable ranked attack.")
    raise VermilionChapterError(
        f"Unexpected Rocket thief species {state.enemy_species_id!r}."
    )


def _backtrack_heal_and_replay(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: VermilionTiming,
) -> tuple[Route6WildFleeEvidence, ...]:
    backtrack_wild_flees = _move_route_6_with_wild_flees(
        executor,
        reader,
        ROUTE_6_FIRST_TRAINER_TO_SOUTH_BUILDING_DIRECTIONS,
        timing,
        expected_trainer_events=(False, False, False, False, True, False),
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
    return (*backtrack_wild_flees, *wild_flees)


def _replay_route_6_lower_gap(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: VermilionTiming,
) -> tuple[Route6WildFleeEvidence, ...]:
    prefix = _directions("LL" + "D" * 4)

    prefix_wild_flees = _move_route_6_with_wild_flees(
        executor,
        reader,
        prefix,
        timing,
    )
    before = reader.read()
    if (
        before.map_id != MapId.ROUTE_6
        or (before.player_x, before.player_y) != (15, 18)
        or before.battle_state != 0
    ):
        raise VermilionChapterError(
            "Route 6 replay missed its exact wild-encounter approach gate."
        )

    return (
        *prefix_wild_flees,
        *_move_route_6_with_wild_flees(
            executor,
            reader,
            ("down", *ROUTE_6_REPLAY_AFTER_WILD_DIRECTIONS),
            timing,
        ),
    )


def _move_route_6_with_wild_flees(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    directions: Iterable[str],
    timing: VermilionTiming,
    *,
    expected_trainer_events: tuple[bool, ...] = (
        False,
        False,
        False,
        False,
        True,
        False,
    ),
) -> tuple[Route6WildFleeEvidence, ...]:
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
                "Route 6 traversal was blocked at "
                f"{(before.player_x, before.player_y)!r}."
            )

        if state.battle_state:
            if state.battle_state != 1:
                raise VermilionChapterError(
                    "Unexpected battle interrupted Route 6 traversal "
                    f"at step {step_number}: type={state.battle_state}, "
                    f"coordinate={(state.player_x, state.player_y)!r}, "
                    f"enemy={state.enemy_species_id!r}."
                )
            wild_flees.append(
                _flee_qualified_route_6_wild(
                    executor,
                    reader,
                    timing,
                    state,
                    expected_trainer_events=expected_trainer_events,
                )
            )
            state = reader.read()

    return tuple(wild_flees)


def _flee_qualified_route_6_wild(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: VermilionTiming,
    encounter: RawGameState,
    *,
    expected_trainer_events: tuple[bool, ...] = (
        False,
        False,
        False,
        False,
        True,
        False,
    ),
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
        expected_trainer_events=expected_trainer_events,
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
            if (
                label == "trashed house approach replay"
                and before.map_id == MapId.CERULEAN_CITY
                and (before.player_x, before.player_y) == CERULEAN_WALKER_BLOCK_POSITION
                and direction == "left"
            ):
                state = _yield_to_cerulean_walker(executor, reader, timing)
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


def _yield_to_cerulean_walker(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: VermilionTiming,
) -> RawGameState:
    """Let the north/south Cerulean walker vacate the replay corridor."""

    for attempt in range(CERULEAN_WALKER_CLEAR_ATTEMPTS):
        state = reader.read()
        if (state.player_x, state.player_y) == CERULEAN_WALKER_CLEAR_POSITION:
            return state
        if (
            state.map_id != MapId.CERULEAN_CITY
            or state.battle_state != 0
            or (state.player_x, state.player_y) != CERULEAN_WALKER_BLOCK_POSITION
        ):
            raise VermilionChapterError(
                "Cerulean walker recovery left its bounded corridor gate."
            )

        executor.execute(MacroAction(MacroActionKind.MOVE, "right"))
        yielded = reader.read()
        if (yielded.player_x, yielded.player_y) != CERULEAN_WALKER_YIELD_POSITION:
            raise VermilionChapterError(
                "Cerulean walker recovery could not yield the corridor."
            )
        _wait(executor, timing.movement_retry_wait_frames * (attempt + 1))

        executor.execute(MacroAction(MacroActionKind.MOVE, "left"))
        returned = reader.read()
        if (returned.player_x, returned.player_y) != CERULEAN_WALKER_BLOCK_POSITION:
            raise VermilionChapterError(
                "Cerulean walker recovery could not restore its approach gate."
            )
        executor.execute(MacroAction(MacroActionKind.MOVE, "left"))
        state = reader.read()
        if (state.player_x, state.player_y) == CERULEAN_WALKER_CLEAR_POSITION:
            return state

    raise VermilionChapterError(
        "Cerulean walker did not clear the replay corridor within its bounded retries."
    )


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


class _PauseForRocketThiefPotion(Exception):
    pass


def _run_rocket_thief_with_potion(
    reader: PokemonRedStateReader,
    executor: _CountingExecutor,
    emulator: EmulatorState,
    timing: VermilionTiming,
) -> RawGameState:
    """Spend at most one retained Potion when live Rocket damage requires it."""

    if _bag_quantity(emulator, ItemId.POTION) != ROCKET_THIEF_POTION_RESERVE:
        raise VermilionChapterError("Rocket thief lacks its three-Potion recovery boundary.")

    def guarded_policy(raw: RawGameState) -> int:
        if (
            _bag_quantity(emulator, ItemId.POTION) == ROCKET_THIEF_POTION_RESERVE
            and raw.first_party_hp is not None
            and 0 < raw.first_party_hp <= 40
        ):
            raise _PauseForRocketThiefPotion
        return _choose_rocket_move(raw)

    intent = BattleIntent(
        "reach_vermilion",
        battle_plan_id=ROCKET_THIEF_BATTLE_PLAN_ID,
        resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
    )
    used_potion = False
    while True:
        try:
            result = run_adaptive_trainer_battle(
                reader,
                executor,
                guarded_policy,
                expected_map=MapId.CERULEAN_CITY,
                intent=intent,
                timing=timing.battle_runtime,
                label="Rocket thief",
                # The level-24 prompt occurs inside this battle and must accept
                # Bite over Tackle when no switch prompt is possible.
                unknown_cancel_interval=10_000,
            )
        except BattleRuntimeError as error:
            if not isinstance(error.__cause__, _PauseForRocketThiefPotion):
                raise VermilionChapterError(str(error)) from error
            if used_potion:
                raise VermilionChapterError(
                    "Rocket thief requested more than one Potion recovery."
                ) from error
            try:
                _use_cerulean_rival_potion(
                    reader,
                    executor,
                    emulator,
                    DEFAULT_CASCADE_TIMING,
                )
            except CascadeChapterError as recovery_error:
                raise VermilionChapterError(str(recovery_error)) from recovery_error
            used_potion = True
            continue

        expected_quantity = (
            VERMILION_ROUTE_6_POTION_RESERVE
            if used_potion
            else ROCKET_THIEF_POTION_RESERVE
        )
        if _bag_quantity(emulator, ItemId.POTION) != expected_quantity:
            raise VermilionChapterError(
                "Rocket thief changed its bounded Potion reserve unexpectedly."
            )
        return result


class _PauseForRoute6Potion(Exception):
    pass


def _run_route_6_trainer_f_with_potion(
    reader: PokemonRedStateReader,
    executor: _CountingExecutor,
    emulator: EmulatorState,
    timing: VermilionTiming,
    battle_plan_id: str,
) -> RawGameState:
    """Spend at most one Route 6 Potion while preserving the S.S. Anne reserve."""

    starting_reserve = _bag_quantity(emulator, ItemId.POTION)
    if not VERMILION_ROUTE_6_POTION_RESERVE <= starting_reserve <= ROCKET_THIEF_POTION_RESERVE:
        raise VermilionChapterError("Route 6 recovery reserve is outside its bounded range.")

    def guarded_policy(raw: RawGameState) -> int:
        if (
            _bag_quantity(emulator, ItemId.POTION) > SS_ANNE_RIVAL_POTION_RESERVE
            and raw.first_party_hp is not None
            and 0 < raw.first_party_hp <= 40
        ):
            raise _PauseForRoute6Potion
        return _choose_route_6_trainer_f_move(raw)

    recoveries = 0
    while True:
        try:
            result = run_adaptive_trainer_battle(
                reader,
                executor,
                guarded_policy,
                expected_map=MapId.ROUTE_6,
                intent=BattleIntent(
                    "reach_vermilion",
                    battle_plan_id=battle_plan_id,
                    resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
                ),
                timing=timing.battle_runtime,
                label="Route 6 Jr Trainer F",
                unknown_cancel_interval=3,
            )
        except BattleRuntimeError as error:
            if not isinstance(error.__cause__, _PauseForRoute6Potion):
                raise VermilionChapterError(str(error)) from error
            if recoveries >= starting_reserve - SS_ANNE_RIVAL_POTION_RESERVE:
                raise VermilionChapterError(
                    "Route 6 exhausted its protected S.S. Anne reserve."
                ) from error
            try:
                _use_cerulean_rival_potion(
                    reader,
                    executor,
                    emulator,
                    DEFAULT_CASCADE_TIMING,
                )
            except CascadeChapterError as recovery_error:
                raise VermilionChapterError(str(recovery_error)) from recovery_error
            recoveries += 1
            continue

        remaining = _bag_quantity(emulator, ItemId.POTION)
        if (
            remaining != starting_reserve - recoveries
            or not SS_ANNE_RIVAL_POTION_RESERVE <= remaining <= starting_reserve
        ):
            raise VermilionChapterError(
                "Route 6 changed its bounded Potion reserve unexpectedly."
            )
        return result


def _choose_route_6_trainer_f_move(raw: RawGameState) -> int:
    """Prefer power at neutral accuracy and Bite after Sand-Attack or near a KO."""

    moves = raw.first_party_moves
    pp = raw.first_party_pp
    if moves is None or pp is None or raw.enemy_hp is None:
        raise VermilionChapterError("Route 6 move policy lacks live battle evidence.")
    lowered_accuracy = (
        raw.player_accuracy_stage is not None and raw.player_accuracy_stage < 7
    )
    candidates = (
        (1, BITE_MOVE_ID),
        (3, POST_ROCKET_WARTORTLE_MOVES[2]),
        (4, POST_ROCKET_WARTORTLE_MOVES[3]),
    ) if lowered_accuracy or raw.enemy_hp <= 10 else (
        (3, POST_ROCKET_WARTORTLE_MOVES[2]),
        (1, BITE_MOVE_ID),
        (4, POST_ROCKET_WARTORTLE_MOVES[3]),
    )
    for slot, expected_move in candidates:
        if (
            len(moves) >= slot
            and len(pp) >= slot
            and moves[slot - 1] == expected_move
            and pp[slot - 1] & 0x3F
            and raw.player_disabled_move_slot != slot
        ):
            return slot
    raise VermilionChapterError("Route 6 move policy lacks a usable ranked attack.")


def _battle(
    reader: PokemonRedStateReader,
    executor: _CountingExecutor,
    policy: Callable[[RawGameState], int],
    expected_map: MapId,
    timing: VermilionTiming,
    label: str,
    battle_plan_id: str,
    *,
    learn_level_up_move: bool = False,
) -> RawGameState:
    try:
        return run_adaptive_trainer_battle(
            reader,
            executor,
            policy,
            expected_map=expected_map,
            intent=BattleIntent(
                "reach_vermilion",
                battle_plan_id=battle_plan_id,
            ),
            timing=timing.battle_runtime,
            label=label,
            # The Rocket battle is the pinned level-24 transition. With only
            # Wartortle in the party there is no switch prompt to decline, so
            # confirming UNKNOWN phases accepts Bite and replaces Tackle.
            unknown_cancel_interval=10_000 if learn_level_up_move else 3,
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
