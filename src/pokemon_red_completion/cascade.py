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
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_policy import choose_cerulean_rival_move_slot
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleResourcePolicy,
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
from pokemon_red_completion.economy import CERULEAN_RIVAL_POTION_RESERVE
from pokemon_red_completion.misty_policy import choose_misty_move_slot
from pokemon_red_completion.observation import (
    ABRA_SPECIES_ID,
    BUBBLE_MOVE_ID,
    BULBASAUR_SPECIES_ID,
    MEGA_PUNCH_MOVE_ID,
    PIDGEOTTO_SPECIES_ID,
    RATTATA_SPECIES_ID,
    ROUTE_24_REQUIRED_TRAINER_SPECS,
    ROUTE_25_REQUIRED_TRAINER_SPECS,
    WARTORTLE_SPECIES_ID,
    ZUBAT_SPECIES_ID,
    BattleMenuPhase,
    CascadePhase,
    CascadeProgressError,
    CascadeProgressTracker,
    CascadeState,
    CeruleanChapterState,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.red_pc_storage import (
    RedPCStorageError,
    RedPCStorageTiming,
    deposit_party_member,
    open_bills_pc,
    switch_box,
)

CASCADE_CHECKPOINT_COUNT = 22
CERULEAN_RIVAL_BATTLE_PLAN_ID = RedBattlePlanId.CASCADE_CERULEAN_RIVAL
MISTY_BATTLE_PLAN_ID = RedBattlePlanId.CASCADE_MISTY
CERULEAN_RIVAL_RECOVERY_HP_THRESHOLDS = {
    PIDGEOTTO_SPECIES_ID: 25,
    ABRA_SPECIES_ID: 30,
    RATTATA_SPECIES_ID: 25,
    BULBASAUR_SPECIES_ID: 30,
}
CERULEAN_RIVAL_MAX_POTION_RESERVE = CERULEAN_RIVAL_POTION_RESERVE + 4
POTION_HEAL_AMOUNT = 20
TM01_FIELD_MENU_CLOSE_PULSES = 2
ROUTE_24_RECOVERY_POTION_RESERVE = 6
ROUTE_24_CENTER_RECOVERY_POSITION = 2
ROUTE_24_ACCURACY_RECOVERY_POSITION = 3
ROUTE_24_FINAL_RECOVERY_POSITION = 4
ROUTE_24_ACCURACY_RECOVERY_HP = 40
ROUTE_25_RECOVERY_POTION_RESERVE = 5
CERULEAN_GYM_POTION_RESERVE = 8
CERULEAN_GYM_START_POTION_RESERVE = 7
ROCKET_THIEF_POTION_RESERVE = 4
VERMILION_ROUTE_6_POTION_RESERVE = 3
SS_ANNE_RIVAL_POTION_RESERVE = 2
FIELD_ITEM_MENU_CLOSE_PULSES = 4
CERULEAN_GYM_TRAINER_MOVE_SLOT = 3
CERULEAN_GYM_TRAINER_RECOVERY_HP = 30
ROUTE_25_NON_HIKER_MOVE_SLOT = 3
ROUTE_24_REQUIRED_TRAINER_INDEXES = tuple(spec[0] for spec in ROUTE_24_REQUIRED_TRAINER_SPECS)
ROUTE_25_REQUIRED_TRAINER_INDEXES = tuple(spec[0] for spec in ROUTE_25_REQUIRED_TRAINER_SPECS)


def _directions(compact: str) -> tuple[str, ...]:
    lookup = {"U": "up", "D": "down", "L": "left", "R": "right"}
    return tuple(lookup[direction] for direction in compact)


CERULEAN_TO_CENTER_DIRECTIONS = _directions("DD" + "R" * 19 + "UUU")
CENTER_HEAL_APPROACH_DIRECTIONS = _directions("UUUU")
CENTER_HEAL_TO_PC_DIRECTIONS = _directions("D" + "R" * 10)
CENTER_PC_TO_HEAL_DIRECTIONS = _directions("L" * 10 + "U")
CENTER_EXIT_DIRECTIONS = _directions("DDDDD")
CENTER_TO_MART_DIRECTIONS = _directions("D" * 5 + "L" * 2 + "D" * 3 + "R" * 8 + "U" * 3)
MART_CLERK_DIRECTIONS = _directions("UULL")
MART_REPEAT_CLERK_DIRECTIONS = _directions("RUULL")
MART_TO_CENTER_STAGING_DIRECTIONS = _directions(
    "RR" + "D" * 3 + "L" * 10 + "U" * 3 + "R" * 2 + "U" * 5
)
MART_REPEAT_TO_CENTER_STAGING_DIRECTIONS = _directions(
    "DDRD" + "L" * 10 + "U" * 3 + "R" * 2 + "U" * 5
)
CENTER_TO_RIVAL_STAGING_DIRECTIONS = _directions("LLUU" + "L" * 9 + "U" * 4 + "R" * 12 + "U" * 5)
RIVAL_TRIGGER_DIRECTIONS = ("up",)
RIVAL_TO_CENTER_DIRECTIONS = _directions("D" * 6 + "L" * 12 + "D" * 4 + "R" * 9 + "DDRRU")
RIVAL_CENTER_NPC_CORRECTION_DIRECTIONS = _directions("DRRRU")
CENTER_TO_ROUTE_24_WAIT_STAGING_DIRECTIONS = _directions("LLUUL")
CENTER_TO_ROUTE_24_STAGING_CORRECTION_DIRECTIONS = ("left",)
CENTER_TO_ROUTE_24_DIRECTIONS = _directions("L" * 8 + "U" * 4 + "R" * 12 + "U" * 13)
ROUTE_24_AFTER_NPC_DIRECTIONS = CENTER_TO_ROUTE_24_DIRECTIONS[8:]
ROUTE_24_TRAINER_SEGMENTS = tuple(
    _directions(segment) for segment in ("U" * 4, "UURU", "UULU", "UURU", "UULU")
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
GYM_TRAINER_DIRECTIONS = _directions("U" * 5 + "LL" + "UUU" + "R" * 5 + "UU" + "LL")
GYM_TRAINER_TO_EXIT_DIRECTIONS = _directions("RR" + "DD" + "L" * 5 + "DDD" + "RR" + "D" * 6)
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

    def read_u8(self, address: int) -> int: ...


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
            and self.observed_route_24_trainers == ROUTE_24_REQUIRED_TRAINER_INDEXES
            and self.observed_route_25_trainers == ROUTE_25_REQUIRED_TRAINER_INDEXES
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
        return tuple((record.checkpoint_id, record.label, record.raw) for record in self.records)

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
                    self.final_evidence.cascade_badge and self.final_evidence.cascade_badge_mirror
                ),
                "tm11_verified": (self.final_evidence.got_tm11 and self.final_evidence.tm11_in_bag),
                "ss_ticket_verified": (
                    self.final_evidence.got_ss_ticket and self.final_evidence.ss_ticket_in_bag
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
    _heal(
        chapter_executor,
        reader,
        timing,
        emulator=emulator,
        withdraw_pc_potion=True,
    )
    _teach_cerulean_rival_mega_punch(
        reader,
        chapter_executor,
        emulator,
        timing,
    )
    _purchase_cerulean_supplies(
        reader,
        chapter_executor,
        emulator,
        timing,
    )
    _move(
        chapter_executor,
        reader,
        CENTER_TO_RIVAL_STAGING_DIRECTIONS,
        "Cerulean rival staging",
    )
    rival_staging = reader.read()
    if (
        rival_staging.map_id != MapId.CERULEAN_CITY
        or (rival_staging.player_x, rival_staging.player_y) != (20, 7)
        or rival_staging.battle_state != 0
        or rival_staging.party_species_ids != (WARTORTLE_SPECIES_ID, ZUBAT_SPECIES_ID)
        or rival_staging.first_party_moves != (0x21, 0x27, MEGA_PUNCH_MOVE_ID, 0x37)
        or _bag_quantity(emulator, ItemId.POTION) != CERULEAN_RIVAL_MAX_POTION_RESERVE
        or _bag_quantity(emulator, ItemId.TM01_MEGA_PUNCH) != 0
    ):
        raise CascadeChapterError("Cerulean rival staging missed its bounded reserve gate.")
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
    _run_cerulean_rival_with_potion(
        reader,
        chapter_executor,
        emulator,
        timing,
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
    _heal(
        chapter_executor,
        reader,
        timing,
        emulator=emulator,
        cleanup_rival_resources=True,
    )
    _enter_route_24(chapter_executor, reader, timing)

    route_24_prefix: tuple[str, ...] = ()
    for position, (trainer_index, segment) in enumerate(
        zip(
            ROUTE_24_REQUIRED_TRAINER_INDEXES,
            ROUTE_24_TRAINER_SEGMENTS,
            strict=True,
        )
    ):
        # The third required trainer leads with three Bug/Poison Pokémon and
        # finishes with an Ekans that can trap Wartortle with Wrap. Recover
        # before this battle: a held-out schedule showed that healing
        # immediately afterward is too late when the preceding fights poison
        # and weaken the only party member.
        if position in {
            ROUTE_24_CENTER_RECOVERY_POSITION,
            ROUTE_24_ACCURACY_RECOVERY_POSITION,
            ROUTE_24_FINAL_RECOVERY_POSITION,
        }:
            _recover_route_24(
                chapter_executor,
                reader,
                emulator,
                timing,
                route_24_prefix,
            )
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
        if position == ROUTE_24_ACCURACY_RECOVERY_POSITION:
            _run_route_24_accuracy_battle_with_potion(
                reader,
                chapter_executor,
                emulator,
                timing,
                f"Route 24 trainer {trainer_index}",
            )
        else:
            _run_fixed_slot_battle(
                reader,
                chapter_executor,
                4,
                MapId.ROUTE_24,
                timing,
                f"Route 24 trainer {trainer_index}",
            )

    # Spend the planned Route 24 field Potion before the Rocket instead of
    # after it.  A held-out schedule left the lead at two HP after the fifth
    # bridge trainer; waiting until victory made the recovery unreachable.
    _use_route_24_antidote_if_needed(
        reader,
        chapter_executor,
        emulator,
    )
    route_24_potions = _bag_quantity(emulator, ItemId.POTION)
    if route_24_potions == ROUTE_24_RECOVERY_POTION_RESERVE:
        _use_route_24_recovery_potion(
            reader,
            chapter_executor,
            emulator,
        )
    elif route_24_potions == ROUTE_25_RECOVERY_POTION_RESERVE:
        _recover_route_24(
            chapter_executor,
            reader,
            emulator,
            timing,
            route_24_prefix,
        )
    else:
        raise CascadeChapterError(
            "Route 24 bridge recovery changed its protected four-Potion handoff."
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
        emulator,
        timing,
        route_24_prefix + ROUTE_24_ROCKET_SEGMENT,
        buy_awakening_topup=True,
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
            ROUTE_25_NON_HIKER_MOVE_SLOT if trainer_index != 8 else 4,
            MapId.ROUTE_25,
            timing,
            f"Route 25 trainer {trainer_index}",
        )
        _use_route_25_antidote_if_needed(
            reader,
            chapter_executor,
            emulator,
        )
        if trainer_index == 2:
            _use_route_25_recovery_potion(
                reader,
                chapter_executor,
                emulator,
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
    _run_cerulean_gym_trainer_with_potion(
        reader,
        chapter_executor,
        emulator,
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
        BattleIntent(
            "defeat_misty",
            battle_plan_id=MISTY_BATTLE_PLAN_ID,
        ),
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
            raise CascadeChapterError(f"Unexpected battle interrupted {label} before step {step}.")
        executor.execute(MacroAction(MacroActionKind.MOVE, direction))
        state = reader.read()
        allowed = allow_trainer_trigger and step == len(direction_list) and state.battle_state == 2
        if state.battle_state and not allowed:
            raise CascadeChapterError(f"Unexpected battle interrupted {label} at step {step}.")
        if state.first_party_hp == 0:
            raise CascadeChapterError(f"Squirtle's lineage fainted during {label}.")
    return state


def _heal(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: CascadeTiming,
    *,
    emulator: EmulatorState | None = None,
    withdraw_pc_potion: bool = False,
    cleanup_rival_resources: bool = False,
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
    if withdraw_pc_potion:
        if emulator is None:
            raise CascadeChapterError("Cerulean PC withdrawal requires emulator evidence.")
        _withdraw_cerulean_rival_potion(executor, reader, emulator, timing)
    if cleanup_rival_resources:
        if emulator is None:
            raise CascadeChapterError("Cerulean rival cleanup requires emulator evidence.")
        _store_cerulean_rival_resources(executor, reader, emulator, timing)
    _move(executor, reader, CENTER_EXIT_DIRECTIONS, "Cerulean Center exit")
    _wait(executor, timing.transition_wait_frames)


def _withdraw_cerulean_rival_potion(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: CascadeTiming,
) -> None:
    """Withdraw the guaranteed new-game Potion from RED's PC exactly once."""

    before = reader.read()
    before_count = emulator.read_u8(RamAddress.NUM_BAG_ITEMS)
    if (
        before.map_id != MapId.CERULEAN_POKECENTER
        or (before.player_x, before.player_y) != (3, 3)
        or before.battle_state != 0
        or not reader.read_input_readiness().ready
        or not 0 <= before_count < 20
        or _bag_quantity(emulator, ItemId.POTION) != CERULEAN_RIVAL_POTION_RESERVE - 1
    ):
        raise CascadeChapterError("Cerulean PC Potion withdrawal has an invalid starting gate.")

    _approach_cerulean_pc(executor, reader, emulator, timing, "Cerulean PC")

    _pc_pulse(executor, MacroActionKind.INTERACT, None, timing)
    _pc_pulse(executor, MacroActionKind.CONFIRM, None, timing)
    for _ in range(4):
        if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) == 1:
            break
        _pc_pulse(executor, MacroActionKind.MOVE, "down", timing)
    else:
        raise CascadeChapterError("Cerulean PC could not select RED's PC.")

    _pc_pulse(executor, MacroActionKind.CONFIRM, None, timing)
    _pc_pulse(executor, MacroActionKind.CONFIRM, None, timing)
    _pc_pulse(executor, MacroActionKind.CONFIRM, None, timing)
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 0:
        raise CascadeChapterError("Cerulean PC did not expose WITHDRAW ITEM.")
    _pc_pulse(executor, MacroActionKind.CONFIRM, None, timing)
    _pc_pulse(executor, MacroActionKind.CONFIRM, None, timing)
    _pc_pulse(executor, MacroActionKind.CONFIRM, None, timing)
    if (
        _bag_quantity(emulator, ItemId.POTION) != CERULEAN_RIVAL_POTION_RESERVE
        or emulator.read_u8(RamAddress.NUM_BAG_ITEMS) != before_count
    ):
        raise CascadeChapterError("Cerulean PC did not withdraw exactly one Potion.")

    for _ in range(4):
        _pc_pulse(executor, MacroActionKind.CANCEL, None, timing)
    returned = reader.read()
    if (
        returned.map_id != MapId.CERULEAN_POKECENTER
        or (returned.player_x, returned.player_y) != (13, 4)
        or returned.battle_state != 0
        or not reader.read_input_readiness().ready
        or _bag_quantity(emulator, ItemId.POTION) != CERULEAN_RIVAL_POTION_RESERVE
    ):
        raise CascadeChapterError("Cerulean PC did not return stable field control.")

    _move(
        executor,
        reader,
        CENTER_PC_TO_HEAL_DIRECTIONS,
        "Cerulean PC return",
    )
    back_at_heal_route = reader.read()
    if (
        back_at_heal_route.map_id != MapId.CERULEAN_POKECENTER
        or (back_at_heal_route.player_x, back_at_heal_route.player_y) != (3, 3)
        or _bag_quantity(emulator, ItemId.POTION) != CERULEAN_RIVAL_POTION_RESERVE
    ):
        raise CascadeChapterError("Cerulean PC return missed the bounded healing route.")


def _teach_cerulean_rival_mega_punch(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    emulator: EmulatorState,
    timing: CascadeTiming,
) -> None:
    """Teach the legally collected TM01 into the former Bubble slot."""

    before = reader.read()
    if (
        before.map_id != MapId.CERULEAN_CITY
        or before.battle_state != 0
        or before.party_species_ids != (WARTORTLE_SPECIES_ID, ZUBAT_SPECIES_ID)
        or before.first_party_moves is None
        or before.first_party_moves[2] != BUBBLE_MOVE_ID
        or _bag_quantity(emulator, ItemId.TM01_MEGA_PUNCH) != 1
    ):
        raise CascadeChapterError("TM01 teaching has an invalid starting gate.")

    executor.execute(MacroAction(MacroActionKind.OPEN_MENU))
    _wait(executor, timing.dialogue_wait_frames)
    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == 2:
            break
        _pc_pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if cursor < 2 else "up",
            timing,
        )
    else:
        raise CascadeChapterError("TM01 teaching could not select ITEM.")
    _pc_pulse(executor, MacroActionKind.CONFIRM, None, timing)
    _select_bag_item(executor, emulator, ItemId.TM01_MEGA_PUNCH, timing)
    _pc_pulse(executor, MacroActionKind.CONFIRM, None, timing)

    for _ in range(24):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (0, 1):
            break
        _pc_pulse(executor, MacroActionKind.CONFIRM, None, timing)
    else:
        raise CascadeChapterError("TM01 teaching did not reach party selection.")

    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == 0:
            break
        _pc_pulse(executor, MacroActionKind.MOVE, "up", timing)
    else:
        raise CascadeChapterError("TM01 teaching could not select Wartortle.")
    _pc_pulse(executor, MacroActionKind.CONFIRM, None, timing)

    for _ in range(24):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (5, 8):
            break
        _pc_pulse(executor, MacroActionKind.CONFIRM, None, timing)
    else:
        raise CascadeChapterError("TM01 teaching did not reach move deletion.")

    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == 2:
            break
        _pc_pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if cursor < 2 else "up",
            timing,
        )
    else:
        raise CascadeChapterError("TM01 teaching could not select Bubble slot three.")
    _pc_pulse(executor, MacroActionKind.CONFIRM, None, timing)

    for _ in range(24):
        learned = reader.read()
        if (
            learned.first_party_moves
            == (
                before.first_party_moves[0],
                before.first_party_moves[1],
                MEGA_PUNCH_MOVE_ID,
                before.first_party_moves[3],
            )
            and _bag_quantity(emulator, ItemId.TM01_MEGA_PUNCH) == 0
        ):
            break
        _pc_pulse(executor, MacroActionKind.CONFIRM, None, timing)
    else:
        raise CascadeChapterError("TM01 did not replace Bubble and consume the item.")

    for _ in range(TM01_FIELD_MENU_CLOSE_PULSES):
        _pc_pulse(executor, MacroActionKind.CANCEL, None, timing)
    for _ in range(12):
        if reader.read_input_readiness().ready:
            return
        _pc_pulse(executor, MacroActionKind.CANCEL, None, timing)
    raise CascadeChapterError("TM01 teaching did not restore field control.")


def _store_cerulean_rival_resources(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: CascadeTiming,
) -> None:
    """Deposit the helper and all but one guaranteed Route 24 recovery Potion."""

    before = reader.read()
    lead_before = _read_bytes(emulator, RamAddress.PARTY_MON_1, 44)
    money_before = _read_bytes(emulator, RamAddress.PLAYER_MONEY, 3)
    bag_before = _bag_entries(emulator)
    if (
        before.map_id != MapId.CERULEAN_POKECENTER
        or (before.player_x, before.player_y) != (3, 3)
        or before.battle_state != 0
        or before.party_species_ids != (WARTORTLE_SPECIES_ID, ZUBAT_SPECIES_ID)
        or not reader.read_input_readiness().ready
    ):
        raise CascadeChapterError("Cerulean rival cleanup has an invalid starting gate.")

    _approach_cerulean_pc(executor, reader, emulator, timing, "Cerulean cleanup PC")
    storage_timing = RedPCStorageTiming(wait_frames=timing.dialogue_wait_frames)
    try:
        open_bills_pc(executor, reader, timing=storage_timing)
        deposit_report = deposit_party_member(
            executor,
            reader,
            party_slot=2,
            expected_species_id=ZUBAT_SPECIES_ID,
            timing=storage_timing,
        )
        switch_out_report = switch_box(
            executor,
            reader,
            target_box_index=1,
            timing=storage_timing,
        )
        switch_back_report = switch_box(
            executor,
            reader,
            target_box_index=0,
            timing=storage_timing,
        )
    except RedPCStorageError as error:
        raise CascadeChapterError(f"Cerulean helper storage failed: {error}") from error
    if not deposit_report.passed:
        raise CascadeChapterError("Cerulean helper deposit lacked a verified transition.")
    if not switch_out_report.passed or not switch_back_report.passed:
        raise CascadeChapterError("Cerulean helper storage cycle lacked a verified transition.")

    after_helper = reader.read()
    if (
        after_helper.party_species_ids != (WARTORTLE_SPECIES_ID,)
        or _read_bytes(emulator, RamAddress.PARTY_MON_1, 44) != lead_before
        or _read_bytes(emulator, RamAddress.PLAYER_MONEY, 3) != money_before
        or _bag_entries(emulator) != bag_before
    ):
        raise CascadeChapterError(
            "Cerulean cleanup changed protected state while storing Zubat: "
            f"party={after_helper.party_species_ids!r}, "
            f"lead_unchanged={_read_bytes(emulator, RamAddress.PARTY_MON_1, 44) == lead_before}, "
            f"money_unchanged={_read_bytes(emulator, RamAddress.PLAYER_MONEY, 3) == money_before}, "
            f"bag_before={bag_before!r}, bag_after={_bag_entries(emulator)!r}."
        )

    _pc_pulse(executor, MacroActionKind.CANCEL, None, timing)
    remaining = _bag_quantity(emulator, ItemId.POTION)
    if not ROUTE_24_RECOVERY_POTION_RESERVE <= remaining <= CERULEAN_RIVAL_MAX_POTION_RESERVE:
        raise CascadeChapterError(
            "Cerulean rival cleanup lacks the guaranteed Route 24 recovery Potion."
        )
    to_store = remaining - ROUTE_24_RECOVERY_POTION_RESERVE
    if to_store:
        _pc_pulse(executor, MacroActionKind.MOVE, "down", timing)
        for _ in range(3):
            _pc_pulse(executor, MacroActionKind.CONFIRM, None, timing)
        if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 0:
            raise CascadeChapterError("Cerulean cleanup did not open RED'S PC.")
        _pc_pulse(executor, MacroActionKind.MOVE, "down", timing)
        _pc_pulse(executor, MacroActionKind.CONFIRM, None, timing)
        _select_pc_item(executor, emulator, ItemId.POTION, timing)
        _pc_pulse(executor, MacroActionKind.CONFIRM, None, timing)
        for _ in range(to_store - 1):
            _pc_pulse(executor, MacroActionKind.MOVE, "up", timing)
        _pc_pulse(executor, MacroActionKind.CONFIRM, None, timing)
        _pc_pulse(executor, MacroActionKind.CONFIRM, None, timing)
        if _bag_quantity(emulator, ItemId.POTION) != ROUTE_24_RECOVERY_POTION_RESERVE:
            raise CascadeChapterError(
                "Cerulean cleanup did not retain the two planned recovery Potions."
            )
        for _ in range(3):
            _pc_pulse(executor, MacroActionKind.CANCEL, None, timing)
    else:
        _pc_pulse(executor, MacroActionKind.CANCEL, None, timing)

    returned = reader.read()
    if (
        returned.map_id != MapId.CERULEAN_POKECENTER
        or (returned.player_x, returned.player_y) != (13, 4)
        or returned.battle_state != 0
        or returned.party_species_ids != (WARTORTLE_SPECIES_ID,)
        or _read_bytes(emulator, RamAddress.PARTY_MON_1, 44) != lead_before
        or _read_bytes(emulator, RamAddress.PLAYER_MONEY, 3) != money_before
        or _bag_quantity(emulator, ItemId.POTION) != ROUTE_24_RECOVERY_POTION_RESERVE
        or not reader.read_input_readiness().ready
    ):
        raise CascadeChapterError("Cerulean cleanup did not restore stable field control.")
    _return_from_cerulean_pc(executor, reader, timing)
    final = reader.read()
    if (
        final.map_id != MapId.CERULEAN_POKECENTER
        or (final.player_x, final.player_y) != (3, 3)
        or final.party_species_ids != (WARTORTLE_SPECIES_ID,)
    ):
        raise CascadeChapterError(
            "Cerulean cleanup missed the bounded healing route: "
            f"map={final.map_id!r}, "
            f"position={(final.player_x, final.player_y)!r}, "
            f"party={final.party_species_ids!r}, "
            f"ready={reader.read_input_readiness().ready!r}."
        )


def _return_from_cerulean_pc(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: CascadeTiming,
) -> None:
    """Return to the healing route while tolerating the Center's moving NPC."""
    _move(executor, reader, CENTER_PC_TO_HEAL_DIRECTIONS, "Cerulean cleanup return")
    target = (3, 3)
    for attempt in range(24):
        state = reader.read()
        position = (state.player_x, state.player_y)
        if position == target:
            return
        if state.map_id != MapId.CERULEAN_POKECENTER or state.battle_state != 0:
            raise CascadeChapterError("Cerulean cleanup return left its safe Center map.")
        if state.player_x is None or state.player_y is None:
            raise CascadeChapterError("Cerulean cleanup return lacks coordinates.")
        direction = _cerulean_return_direction(position)
        executor.execute(MacroAction(MacroActionKind.MOVE, direction))
        moved = reader.read()
        if (moved.player_x, moved.player_y) == position:
            detour = _cerulean_return_blocked_detour(position, direction)
            if detour is not None:
                executor.execute(MacroAction(MacroActionKind.MOVE, detour))
                moved = reader.read()
                if (moved.player_x, moved.player_y) != position:
                    continue
            _wait(executor, max(1, timing.dialogue_wait_frames // 4) * (attempt + 1))
    state = reader.read()
    raise CascadeChapterError(
        "Cerulean cleanup return could not clear the moving NPC: "
        f"position={(state.player_x, state.player_y)!r}."
    )


def _cerulean_return_direction(position: tuple[int, int]) -> str:
    x, y = position
    if x > 3:
        return "left"
    if x < 3:
        return "right"
    return "up" if y > 3 else "down"


def _cerulean_return_blocked_detour(
    position: tuple[int, int],
    direction: str,
) -> str | None:
    if direction == "left" and position[1] == 3 and position[0] > 3:
        return "down"
    return None


def _approach_cerulean_pc(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: CascadeTiming,
    label: str,
) -> None:
    """Reach the PC despite the Center's moving NPC, then prove its facing gate."""

    _move(executor, reader, CENTER_HEAL_TO_PC_DIRECTIONS, label)
    target = (13, 4)
    for attempt in range(24):
        state = reader.read()
        position = (state.player_x, state.player_y)
        if position == target:
            break
        if state.map_id != MapId.CERULEAN_POKECENTER or state.battle_state != 0:
            raise CascadeChapterError(f"{label} left its safe Center map.")
        if state.player_x is None or state.player_y is None:
            raise CascadeChapterError(f"{label} lacks live coordinate evidence.")
        if state.player_y < target[1]:
            direction = "down"
        elif state.player_y > target[1]:
            direction = "up"
        elif state.player_x < target[0]:
            direction = "right"
        else:
            direction = "left"
        executor.execute(MacroAction(MacroActionKind.MOVE, direction))
        moved = reader.read()
        if (moved.player_x, moved.player_y) == position:
            _wait(executor, max(1, timing.dialogue_wait_frames // 4) * (attempt + 1))
    else:
        state = reader.read()
        raise CascadeChapterError(
            f"{label} could not reach the PC interaction tile: "
            f"position={(state.player_x, state.player_y)!r}."
        )

    _pc_pulse(executor, MacroActionKind.MOVE, "up", timing)
    faced = reader.read()
    if (faced.player_x, faced.player_y) != target or emulator.read_u8(
        RamAddress.PLAYER_FACING_DIRECTION
    ) != 0x04:
        raise CascadeChapterError(
            f"{label} missed its interaction gate: "
            f"position={(faced.player_x, faced.player_y)!r}, "
            f"facing={emulator.read_u8(RamAddress.PLAYER_FACING_DIRECTION):#04x}."
        )


def _select_pc_item(
    executor: _CountingChapterExecutor,
    emulator: EmulatorState,
    item: ItemId,
    timing: CascadeTiming,
) -> None:
    for _ in range(24):
        items = tuple(item_id for item_id, _ in _bag_entries(emulator))
        if item not in items:
            raise CascadeChapterError(f"Required PC item {int(item):#04x} is unavailable.")
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        target = items.index(item)
        if absolute == target:
            return
        _pc_pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if absolute < target else "up",
            timing,
        )
    raise CascadeChapterError(f"Could not select PC item {int(item):#04x}.")


def _bag_entries(emulator: EmulatorState) -> tuple[tuple[int, int], ...]:
    return tuple(
        (
            emulator.read_u8(int(RamAddress.BAG_ITEMS) + index * 2),
            emulator.read_u8(int(RamAddress.BAG_ITEMS) + index * 2 + 1),
        )
        for index in range(emulator.read_u8(RamAddress.NUM_BAG_ITEMS))
    )


def _read_bytes(
    emulator: EmulatorState,
    address: RamAddress,
    length: int,
) -> tuple[int, ...]:
    return tuple(emulator.read_u8(int(address) + offset) for offset in range(length))


def _pc_pulse(
    executor: _CountingChapterExecutor,
    kind: MacroActionKind,
    value: str | None,
    timing: CascadeTiming,
) -> None:
    executor.execute(MacroAction(kind, value))
    _wait(executor, timing.dialogue_wait_frames)


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
    if staging.map_id == MapId.CERULEAN_CITY and staging.player_x == 17 and staging.player_y == 16:
        _wait(executor, timing.route_24_npc_wait_frames)
        _move(
            executor,
            reader,
            CENTER_TO_ROUTE_24_STAGING_CORRECTION_DIRECTIONS,
            "Route 24 NPC staging correction",
        )
        staging = reader.read()
    if staging.map_id != MapId.CERULEAN_CITY or staging.player_x != 16 or staging.player_y != 16:
        raise CascadeChapterError("Route 24 NPC wait missed its stable Cerulean staging tile.")
    _wait(executor, timing.route_24_npc_wait_frames)
    _cross_route_24_npc(executor, reader, timing)
    _move(
        executor,
        reader,
        ROUTE_24_AFTER_NPC_DIRECTIONS,
        "Route 24 post-NPC entry corridor",
    )
    _wait(executor, timing.transition_wait_frames)
    reached = reader.read()
    if reached.map_id != MapId.ROUTE_24 or (reached.player_x, reached.player_y) != (10, 35):
        raise CascadeChapterError("Route 24 NPC crossing missed its bounded semantic entry gate.")


def _cross_route_24_npc(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    timing: CascadeTiming,
) -> None:
    """Reach the west corridor by observing progress instead of consuming blocked inputs."""

    target_x = 8
    expected_y = 16
    required_steps = 8
    retry_budget = timing.max_route_24_npc_attempts * required_steps
    for pulse in range(1, required_steps + retry_budget + 1):
        before = reader.read()
        if (
            before.map_id != MapId.CERULEAN_CITY
            or before.player_y != expected_y
            or not target_x <= before.player_x <= 16
        ):
            raise CascadeChapterError(
                "Route 24 NPC crossing left its bounded west corridor: "
                f"position={(before.map_id, before.player_x, before.player_y)!r}."
            )
        if before.player_x == target_x:
            return
        after = _move(
            executor,
            reader,
            ("left",),
            f"Route 24 NPC crossing pulse {pulse}",
        )
        if (
            after.map_id != MapId.CERULEAN_CITY
            or after.player_y != expected_y
            or after.player_x not in {before.player_x, before.player_x - 1}
        ):
            raise CascadeChapterError(
                "Route 24 NPC crossing made an invalid corridor transition: "
                f"before={(before.player_x, before.player_y)!r}, "
                f"after={(after.map_id, after.player_x, after.player_y)!r}."
            )
    raise CascadeChapterError("Route 24 NPC crossing exhausted its bounded progress retries.")


def _recover_route_24(
    executor: _CountingChapterExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: CascadeTiming,
    route_prefix: tuple[str, ...],
    *,
    buy_awakening_topup: bool = False,
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
    if buy_awakening_topup:
        _purchase_cerulean_awakening_topup(reader, executor, emulator, timing)
    _enter_route_24(executor, reader, timing)
    _move(executor, reader, route_prefix, "Route 24 recovery replay")
    _wait(executor, timing.transition_wait_frames)


def _use_route_24_recovery_potion(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    emulator: EmulatorState,
) -> None:
    _use_field_recovery_potion(
        reader,
        executor,
        emulator,
        expected_map=MapId.ROUTE_24,
        starting_quantity=ROUTE_24_RECOVERY_POTION_RESERVE,
        ending_quantity=ROUTE_25_RECOVERY_POTION_RESERVE,
        label="Route 24 recovery",
    )


def _use_route_25_recovery_potion(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    emulator: EmulatorState,
) -> None:
    _use_field_recovery_potion(
        reader,
        executor,
        emulator,
        expected_map=MapId.ROUTE_25,
        starting_quantity=CERULEAN_GYM_POTION_RESERVE,
        ending_quantity=CERULEAN_GYM_START_POTION_RESERVE,
        label="Route 25 recovery",
    )


def _use_field_recovery_potion(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    emulator: EmulatorState,
    *,
    expected_map: MapId,
    starting_quantity: int,
    ending_quantity: int,
    label: str,
) -> None:
    """Consume one field Potion under an exact map, HP, and inventory gate."""

    before = reader.read()
    if (
        before.map_id != expected_map
        or before.battle_state != 0
        or before.party_species_ids != (WARTORTLE_SPECIES_ID,)
        or before.first_party_hp is None
        or before.first_party_max_hp is None
        or not 0 < before.first_party_hp < before.first_party_max_hp
        or _bag_quantity(emulator, ItemId.POTION) != starting_quantity
        or not reader.read_input_readiness().ready
    ):
        raise CascadeChapterError(f"{label} Potion has an invalid starting gate.")

    executor.execute(MacroAction(MacroActionKind.OPEN_MENU))
    _wait(executor, 180)
    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == 2:
            break
        executor.execute(
            MacroAction(
                MacroActionKind.MOVE,
                "down" if cursor < 2 else "up",
            )
        )
        _wait(executor, 120)
    else:
        raise CascadeChapterError(f"{label} could not select ITEM.")

    executor.execute(MacroAction(MacroActionKind.CONFIRM))
    _wait(executor, 180)
    for _ in range(24):
        items = _bag_item_ids(emulator)
        if ItemId.POTION not in items:
            raise CascadeChapterError(f"{label} lost its retained Potion.")
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        target = items.index(ItemId.POTION)
        if absolute == target:
            break
        executor.execute(
            MacroAction(
                MacroActionKind.MOVE,
                "down" if absolute < target else "up",
            )
        )
        _wait(executor, 120)
    else:
        raise CascadeChapterError(f"{label} could not select its Potion.")

    executor.execute(MacroAction(MacroActionKind.CONFIRM))
    _wait(executor, 180)
    executor.execute(MacroAction(MacroActionKind.CONFIRM))
    _wait(executor, 240)
    expected_hp = min(
        before.first_party_max_hp,
        before.first_party_hp + POTION_HEAL_AMOUNT,
    )
    for _ in range(24):
        current = reader.read()
        if (
            current.first_party_hp == expected_hp
            and _bag_quantity(emulator, ItemId.POTION) == ending_quantity
        ):
            break
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, 180)
    else:
        raise CascadeChapterError(f"{label} Potion missed its exact heal gate.")

    for _ in range(FIELD_ITEM_MENU_CLOSE_PULSES):
        executor.execute(MacroAction(MacroActionKind.CANCEL))
        _wait(executor, 180)
    for _ in range(6):
        if reader.read_input_readiness().ready:
            break
        executor.execute(MacroAction(MacroActionKind.CANCEL))
        _wait(executor, 180)
    else:
        raise CascadeChapterError(f"{label} Potion did not restore field control.")

    final = reader.read()
    if (
        final.map_id != expected_map
        or final.battle_state != 0
        or final.party_species_ids != (WARTORTLE_SPECIES_ID,)
        or final.first_party_hp != expected_hp
        or _bag_quantity(emulator, ItemId.POTION) != ending_quantity
        or not reader.read_input_readiness().ready
    ):
        raise CascadeChapterError(f"{label} Potion failed its persistent gate.")


def _purchase_cerulean_supplies(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    emulator: EmulatorState,
    timing: CascadeTiming,
) -> None:
    """Buy four extra Potions plus bounded poison and sleep contingencies."""

    before = reader.read()
    if (
        before.map_id != MapId.CERULEAN_CITY
        or (before.player_x, before.player_y) != (19, 18)
        or before.battle_state != 0
        or _bag_quantity(emulator, ItemId.POTION) != CERULEAN_RIVAL_POTION_RESERVE
        or _bag_quantity(emulator, ItemId.ANTIDOTE) != 0
        or _bag_quantity(emulator, ItemId.AWAKENING) != 0
        or not reader.read_input_readiness().ready
    ):
        raise CascadeChapterError("Cerulean supply purchase has an invalid starting gate.")

    _move(executor, reader, CENTER_TO_MART_DIRECTIONS, "Cerulean Mart")
    _wait(executor, timing.transition_wait_frames)
    entered = reader.read()
    if entered.map_id != MapId.CERULEAN_MART or (
        entered.player_x,
        entered.player_y,
    ) != (3, 7):
        raise CascadeChapterError(
            "Cerulean Mart entry missed its pinned gate: "
            f"map={entered.map_id!r}, position={(entered.player_x, entered.player_y)}."
        )

    _move(executor, reader, MART_CLERK_DIRECTIONS, "Cerulean Mart clerk")
    _battle_pulse(executor, MacroActionKind.MOVE, "left", timing, frames=60)
    _battle_pulse(executor, MacroActionKind.INTERACT, None, timing, frames=180)
    _battle_pulse(executor, MacroActionKind.CONFIRM, None, timing, frames=180)

    def buy_one(
        *,
        shop_index: int,
        item: ItemId,
        purchase_quantity: int,
        expected_quantity: int,
        label: str,
    ) -> None:
        for _ in range(12):
            selected_index = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
                RamAddress.LIST_SCROLL_OFFSET
            )
            if selected_index == shop_index:
                break
            _battle_pulse(
                executor,
                MacroActionKind.MOVE,
                "down" if selected_index < shop_index else "up",
                timing,
                frames=120,
            )
        else:
            raise CascadeChapterError(f"Cerulean Mart could not select {label}.")

        _battle_pulse(executor, MacroActionKind.CONFIRM, None, timing, frames=180)
        for _ in range(purchase_quantity - 1):
            _battle_pulse(executor, MacroActionKind.MOVE, "up", timing, frames=120)
        if (
            emulator.read_u8(RamAddress.SHOP_SELECTED_ITEM) != item
            or emulator.read_u8(RamAddress.SHOP_QUANTITY) != purchase_quantity
        ):
            raise CascadeChapterError(f"Cerulean Mart {label} quantity gate failed.")
        for _ in range(8):
            if _bag_quantity(emulator, item) == expected_quantity:
                break
            _battle_pulse(executor, MacroActionKind.CONFIRM, None, timing, frames=240)
        else:
            raise CascadeChapterError(
                f"Cerulean Mart did not purchase {purchase_quantity} {label}."
            )
        _battle_pulse(executor, MacroActionKind.CONFIRM, None, timing, frames=180)

    buy_one(
        shop_index=1,
        item=ItemId.POTION,
        purchase_quantity=4,
        expected_quantity=CERULEAN_RIVAL_MAX_POTION_RESERVE,
        label="Potions",
    )
    buy_one(
        shop_index=3,
        item=ItemId.ANTIDOTE,
        purchase_quantity=2,
        expected_quantity=2,
        label="Antidotes",
    )
    buy_one(
        shop_index=5,
        item=ItemId.AWAKENING,
        purchase_quantity=1,
        expected_quantity=1,
        label="Awakenings",
    )

    for _ in range(4):
        _battle_pulse(executor, MacroActionKind.CANCEL, None, timing, frames=180)
    if not reader.read_input_readiness().ready:
        raise CascadeChapterError("Cerulean Mart purchase did not restore field control.")
    _move(
        executor,
        reader,
        MART_TO_CENTER_STAGING_DIRECTIONS,
        "Cerulean Center staging return",
    )
    _wait(executor, timing.transition_wait_frames)
    returned = reader.read()
    if (
        returned.map_id != MapId.CERULEAN_CITY
        or (returned.player_x, returned.player_y) != (19, 18)
        or _bag_quantity(emulator, ItemId.POTION) != CERULEAN_RIVAL_MAX_POTION_RESERVE
        or _bag_quantity(emulator, ItemId.ANTIDOTE) != 2
        or _bag_quantity(emulator, ItemId.AWAKENING) != 1
        or not reader.read_input_readiness().ready
    ):
        raise CascadeChapterError(
            "Cerulean supply purchase failed its persistent gate: "
            f"map={returned.map_id!r}, position={(returned.player_x, returned.player_y)}, "
            f"potions={_bag_quantity(emulator, ItemId.POTION)}, "
            f"antidotes={_bag_quantity(emulator, ItemId.ANTIDOTE)}, "
            f"awakenings={_bag_quantity(emulator, ItemId.AWAKENING)}."
        )


def _purchase_cerulean_awakening_topup(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    emulator: EmulatorState,
    timing: CascadeTiming,
) -> None:
    """Buy the Tower reserve copy after the Nugget reward funds it."""

    before = reader.read()
    if (
        before.map_id != MapId.CERULEAN_CITY
        or (before.player_x, before.player_y) != (19, 18)
        or before.battle_state != 0
        or _bag_quantity(emulator, ItemId.AWAKENING) != 1
        or not reader.read_input_readiness().ready
    ):
        raise CascadeChapterError("Cerulean Awakening top-up has an invalid starting gate.")

    _move(executor, reader, CENTER_TO_MART_DIRECTIONS, "Cerulean Mart Awakening top-up")
    _wait(executor, timing.transition_wait_frames)
    entered = reader.read()
    if entered.map_id != MapId.CERULEAN_MART or (
        entered.player_x,
        entered.player_y,
    ) != (3, 7):
        raise CascadeChapterError("Cerulean Awakening top-up missed the Mart entry gate.")

    _move(executor, reader, MART_REPEAT_CLERK_DIRECTIONS, "Cerulean Mart repeat clerk")
    clerk_stance = reader.read()
    if (
        clerk_stance.map_id != MapId.CERULEAN_MART
        or (clerk_stance.player_x, clerk_stance.player_y) != (2, 5)
        or not reader.read_input_readiness().ready
    ):
        raise CascadeChapterError(
            "Cerulean Mart repeat clerk approach missed its pinned gate: "
            f"position={(clerk_stance.player_x, clerk_stance.player_y)}."
        )
    _battle_pulse(executor, MacroActionKind.MOVE, "left", timing, frames=60)
    if _bag_quantity(emulator, ItemId.NUGGET) != 1:
        raise CascadeChapterError("Cerulean Awakening top-up requires the earned Nugget.")
    money_before_sale = _money(emulator)
    _battle_pulse(executor, MacroActionKind.CONFIRM, None, timing, frames=180)
    _battle_pulse(executor, MacroActionKind.MOVE, "down", timing, frames=120)
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 1:
        raise CascadeChapterError("Cerulean Mart did not select SELL for the Nugget.")
    _battle_pulse(executor, MacroActionKind.CONFIRM, None, timing, frames=180)
    for _ in range(24):
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        items = _bag_item_ids(emulator)
        if absolute < len(items) and items[absolute] == ItemId.NUGGET:
            break
        _battle_pulse(executor, MacroActionKind.MOVE, "down", timing, frames=120)
    else:
        raise CascadeChapterError("Cerulean Mart could not select the earned Nugget.")
    _battle_pulse(executor, MacroActionKind.CONFIRM, None, timing, frames=180)
    for _ in range(12):
        if _bag_quantity(emulator, ItemId.NUGGET) == 0:
            break
        _battle_pulse(executor, MacroActionKind.CONFIRM, None, timing, frames=240)
    else:
        raise CascadeChapterError("Cerulean Mart did not sell the earned Nugget.")
    if _money(emulator) - money_before_sale != 5_000:
        raise CascadeChapterError("Cerulean Nugget sale missed its exact ₽5,000 ledger.")
    for _ in range(4):
        _battle_pulse(executor, MacroActionKind.CANCEL, None, timing, frames=180)
    if not reader.read_input_readiness().ready:
        raise CascadeChapterError("Cerulean Nugget sale did not restore field control.")

    _battle_pulse(executor, MacroActionKind.INTERACT, None, timing, frames=180)
    _battle_pulse(executor, MacroActionKind.CONFIRM, None, timing, frames=180)

    def buy_topup(
        *,
        shop_index: int,
        item: ItemId,
        purchase_quantity: int,
        expected_quantity: int,
    ) -> None:
        observed_menu_states: list[tuple[int, int, int, int, int]] = []
        for _ in range(12):
            menu = reader.read_menu_cursor_state()
            selected_index = menu.selected_visible_index + menu.scroll_offset
            observed_menu_states.append(
                (
                    menu.selected_visible_index,
                    menu.scroll_offset,
                    menu.maximum_visible_index,
                    menu.top_x,
                    menu.top_y,
                )
            )
            if selected_index == shop_index:
                break
            _battle_pulse(
                executor,
                MacroActionKind.MOVE,
                "down" if selected_index < shop_index else "up",
                timing,
                frames=120,
            )
        else:
            raise CascadeChapterError(
                f"Cerulean Mart could not select the {item.name} top-up: "
                f"menu_states={observed_menu_states}."
            )

        _battle_pulse(executor, MacroActionKind.CONFIRM, None, timing, frames=180)
        if (
            emulator.read_u8(RamAddress.SHOP_SELECTED_ITEM) != item
            or emulator.read_u8(RamAddress.SHOP_QUANTITY) != 1
        ):
            raise CascadeChapterError(f"Cerulean {item.name} top-up quantity gate failed.")
        for _ in range(purchase_quantity - 1):
            _battle_pulse(executor, MacroActionKind.MOVE, "up", timing, frames=120)
        if emulator.read_u8(RamAddress.SHOP_QUANTITY) != purchase_quantity:
            raise CascadeChapterError(f"Cerulean {item.name} top-up quantity gate failed.")
        for _ in range(8):
            if _bag_quantity(emulator, item) == expected_quantity:
                break
            _battle_pulse(executor, MacroActionKind.CONFIRM, None, timing, frames=240)
        else:
            raise CascadeChapterError(f"Cerulean Mart did not purchase the {item.name} top-up.")
        _battle_pulse(executor, MacroActionKind.CONFIRM, None, timing, frames=180)

    buy_topup(
        shop_index=1,
        item=ItemId.POTION,
        purchase_quantity=3,
        expected_quantity=CERULEAN_GYM_POTION_RESERVE,
    )
    buy_topup(
        shop_index=5,
        item=ItemId.AWAKENING,
        purchase_quantity=1,
        expected_quantity=2,
    )

    for _ in range(4):
        _battle_pulse(executor, MacroActionKind.CANCEL, None, timing, frames=180)
    if not reader.read_input_readiness().ready:
        raise CascadeChapterError("Cerulean Awakening top-up did not restore field control.")
    _move(
        executor,
        reader,
        MART_REPEAT_TO_CENTER_STAGING_DIRECTIONS,
        "Cerulean Center staging return",
    )
    _wait(executor, timing.transition_wait_frames)
    returned = reader.read()
    if (
        returned.map_id != MapId.CERULEAN_CITY
        or (returned.player_x, returned.player_y) != (19, 18)
        or _bag_quantity(emulator, ItemId.POTION) != CERULEAN_GYM_POTION_RESERVE
        or _bag_quantity(emulator, ItemId.AWAKENING) != 2
        or not reader.read_input_readiness().ready
    ):
        raise CascadeChapterError("Cerulean Awakening top-up failed its persistent gate.")


def _use_route_24_antidote_if_needed(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    emulator: EmulatorState,
) -> None:
    _use_field_antidote_if_needed(
        reader,
        executor,
        emulator,
        expected_map=MapId.ROUTE_24,
        label="Route 24",
    )


def _use_route_25_antidote_if_needed(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    emulator: EmulatorState,
) -> None:
    _use_field_antidote_if_needed(
        reader,
        executor,
        emulator,
        expected_map=MapId.ROUTE_25,
        label="Route 25",
    )


def _use_field_antidote_if_needed(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    emulator: EmulatorState,
    *,
    expected_map: MapId,
    label: str,
) -> None:
    """Cure observed field poison before any movement can apply another tick."""

    before = reader.read()
    if (
        before.map_id == expected_map
        and before.battle_state == 0
        and before.party_species_ids == (WARTORTLE_SPECIES_ID,)
        and before.first_party_status == 0
        and 0 <= _bag_quantity(emulator, ItemId.ANTIDOTE) <= 2
        and reader.read_input_readiness().ready
    ):
        return
    if (
        before.map_id != expected_map
        or before.battle_state != 0
        or before.party_species_ids != (WARTORTLE_SPECIES_ID,)
        or before.first_party_status != 8
        or not 1 <= _bag_quantity(emulator, ItemId.ANTIDOTE) <= 2
        or not reader.read_input_readiness().ready
    ):
        raise CascadeChapterError(
            f"{label} Antidote has an invalid starting gate: "
            f"map={before.map_id!r}, battle={before.battle_state}, "
            f"party={before.party_species_ids!r}, status={before.first_party_status!r}, "
            f"quantity={_bag_quantity(emulator, ItemId.ANTIDOTE)}."
        )

    before_quantity = _bag_quantity(emulator, ItemId.ANTIDOTE)
    expected_quantity = before_quantity - 1
    executor.execute(MacroAction(MacroActionKind.OPEN_MENU))
    _wait(executor, 180)
    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == 2:
            break
        executor.execute(
            MacroAction(
                MacroActionKind.MOVE,
                "down" if cursor < 2 else "up",
            )
        )
        _wait(executor, 120)
    else:
        raise CascadeChapterError(f"{label} Antidote could not select ITEM.")

    executor.execute(MacroAction(MacroActionKind.CONFIRM))
    _wait(executor, 180)
    for _ in range(24):
        items = _bag_item_ids(emulator)
        if ItemId.ANTIDOTE not in items:
            raise CascadeChapterError(f"{label} Antidote disappeared before use.")
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        target = items.index(ItemId.ANTIDOTE)
        if absolute == target:
            break
        executor.execute(
            MacroAction(
                MacroActionKind.MOVE,
                "down" if absolute < target else "up",
            )
        )
        _wait(executor, 120)
    else:
        raise CascadeChapterError(f"{label} recovery could not select Antidote.")

    executor.execute(MacroAction(MacroActionKind.CONFIRM))
    _wait(executor, 180)
    executor.execute(MacroAction(MacroActionKind.CONFIRM))
    _wait(executor, 240)
    for _ in range(24):
        current = reader.read()
        if (
            current.first_party_status == 0
            and _bag_quantity(emulator, ItemId.ANTIDOTE) == expected_quantity
        ):
            break
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, 180)
    else:
        raise CascadeChapterError(f"{label} Antidote missed its exact cure gate.")

    for _ in range(FIELD_ITEM_MENU_CLOSE_PULSES):
        executor.execute(MacroAction(MacroActionKind.CANCEL))
        _wait(executor, 180)
    final = reader.read()
    if (
        final.map_id != expected_map
        or final.battle_state != 0
        or final.first_party_status != 0
        or _bag_quantity(emulator, ItemId.ANTIDOTE) != expected_quantity
        or not reader.read_input_readiness().ready
    ):
        raise CascadeChapterError(f"{label} Antidote failed its persistent gate.")


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


def _run_route_24_accuracy_battle_with_potion(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    emulator: EmulatorState,
    timing: CascadeTiming,
    label: str,
) -> RawGameState:
    """Survive the bridge Sand-Attack/poison combination with one reserve.

    This battle is intentionally outside the preregistered adaptive-battle
    roster, so it cannot use ``run_adaptive_trainer_battle`` while a collection
    schedule is bound.  It retains the existing fixed Water Gun controller but
    observes each stable MAIN boundary and may spend exactly one Potion before
    confirming the next attack.  The Potion replaces the field Potion formerly
    spent after all five bridge trainers; four downstream Potions remain either
    way.
    """

    starting_quantity = _bag_quantity(emulator, ItemId.POTION)
    if starting_quantity != ROUTE_24_RECOVERY_POTION_RESERVE:
        raise CascadeChapterError(
            "Route 24 accuracy recovery lacks its five-Potion starting reserve."
        )
    try:
        _select_battle_move(
            executor,
            reader,
            DEFAULT_CERULEAN_TIMING,
            slot=4,
            label=label,
        )
    except CeruleanChapterError as error:
        raise CascadeChapterError(str(error)) from error

    saw_battle = True
    stable_reads = 0
    recovery_used = False
    for _ in range(DEFAULT_CERULEAN_TIMING.max_battle_pulses):
        before = reader.read()
        if before.map_id != MapId.ROUTE_24 or before.battle_state not in {0, 2}:
            raise CascadeChapterError(f"{label} left its bounded battle state.")
        if before.first_party_hp == 0:
            raise CascadeChapterError(f"Squirtle's lineage fainted during {label}.")
        if before.battle_state == 0:
            if saw_battle and reader.read_input_readiness().ready:
                stable_reads += 1
                if stable_reads >= 2:
                    expected_quantity = starting_quantity - int(recovery_used)
                    if _bag_quantity(emulator, ItemId.POTION) != expected_quantity:
                        raise CascadeChapterError(
                            "Route 24 accuracy recovery changed its bounded Potion reserve."
                        )
                    return before
                _wait(executor, timing.dialogue_wait_frames)
                continue
            stable_reads = 0
        else:
            stable_reads = 0
            menu = reader.read_battle_menu_state(before)
            should_recover = (
                not recovery_used
                and menu.phase is BattleMenuPhase.MAIN
                and before.first_party_hp is not None
                and 0 < before.first_party_hp <= ROUTE_24_ACCURACY_RECOVERY_HP
            )
            if should_recover:
                _use_cerulean_rival_potion(
                    reader,
                    executor,
                    emulator,
                    timing,
                )
                recovery_used = True
                continue
            if menu.phase is BattleMenuPhase.MAIN:
                try:
                    _select_battle_move(
                        executor,
                        reader,
                        DEFAULT_CERULEAN_TIMING,
                        slot=4,
                        label=label,
                    )
                except CeruleanChapterError as error:
                    raise CascadeChapterError(str(error)) from error
                continue

        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(
            executor,
            timing.dialogue_wait_frames,
        )

    raise CascadeChapterError(f"{label} failed its bounded battle-completion gate.")


def _run_cerulean_gym_trainer_with_potion(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    emulator: EmulatorState,
    timing: CascadeTiming,
    label: str,
) -> RawGameState:
    """Preserve the downstream reserve while surviving bounded confusion."""

    starting_quantity = _bag_quantity(emulator, ItemId.POTION)
    if starting_quantity != CERULEAN_GYM_START_POTION_RESERVE:
        raise CascadeChapterError(
            "Cerulean Gym recovery lacks its seven-Potion starting reserve."
        )
    starting_pp = reader.read().first_party_pp
    if starting_pp is None:
        raise CascadeChapterError("Cerulean Gym recovery lacks move-PP evidence.")
    try:
        _select_battle_move(
            executor,
            reader,
            DEFAULT_CERULEAN_TIMING,
            slot=CERULEAN_GYM_TRAINER_MOVE_SLOT,
            label=label,
            allow_resolved_turn_without_pp=True,
        )
    except CeruleanChapterError as error:
        raise CascadeChapterError(str(error)) from error

    stable_reads = 0
    recovery_used = False
    for _ in range(DEFAULT_CERULEAN_TIMING.max_battle_pulses):
        before = reader.read()
        if before.map_id != MapId.CERULEAN_GYM or before.battle_state not in {0, 2}:
            raise CascadeChapterError(f"{label} left its bounded battle state.")
        if before.first_party_hp == 0:
            raise CascadeChapterError(f"Squirtle's lineage fainted during {label}.")
        if before.battle_state == 0:
            if reader.read_input_readiness().ready:
                stable_reads += 1
                if stable_reads >= 2:
                    if (
                        not recovery_used
                        and before.first_party_hp is not None
                        and before.first_party_max_hp is not None
                        and 0 < before.first_party_hp < before.first_party_max_hp
                    ):
                        _use_field_recovery_potion(
                            reader,
                            executor,
                            emulator,
                            expected_map=MapId.CERULEAN_GYM,
                            starting_quantity=starting_quantity,
                            ending_quantity=starting_quantity - 1,
                            label="Cerulean Gym reserve",
                        )
                        recovery_used = True
                        before = reader.read()
                    ending_quantity = starting_quantity - int(recovery_used)
                    ending_pp = before.first_party_pp
                    if (
                        not CERULEAN_GYM_START_POTION_RESERVE - 1
                        <= ending_quantity
                        <= CERULEAN_GYM_START_POTION_RESERVE
                        or _bag_quantity(emulator, ItemId.POTION) != ending_quantity
                        or ending_pp is None
                        or ending_pp[CERULEAN_GYM_TRAINER_MOVE_SLOT - 1]
                        >= starting_pp[CERULEAN_GYM_TRAINER_MOVE_SLOT - 1]
                    ):
                        raise CascadeChapterError(
                            "Cerulean Gym recovery missed its Potion or move-evidence contract."
                        )
                    return before
                _wait(executor, timing.dialogue_wait_frames)
                continue
            stable_reads = 0
        else:
            stable_reads = 0
            menu = reader.read_battle_menu_state(before)
            should_recover = (
                not recovery_used
                and menu.phase is BattleMenuPhase.MAIN
                and before.first_party_hp is not None
                and 0 < before.first_party_hp <= CERULEAN_GYM_TRAINER_RECOVERY_HP
            )
            if should_recover:
                _use_cerulean_rival_potion(reader, executor, emulator, timing)
                recovery_used = True
                continue
            if menu.phase is BattleMenuPhase.MAIN:
                try:
                    _select_battle_move(
                        executor,
                        reader,
                        DEFAULT_CERULEAN_TIMING,
                        slot=CERULEAN_GYM_TRAINER_MOVE_SLOT,
                        label=label,
                        allow_resolved_turn_without_pp=True,
                    )
                except CeruleanChapterError as error:
                    raise CascadeChapterError(str(error)) from error
                continue

        executor.execute(MacroAction(MacroActionKind.CONFIRM))
        _wait(executor, timing.dialogue_wait_frames)

    raise CascadeChapterError(f"{label} failed its bounded battle-completion gate.")


def _run_battle(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    policy: Callable[[RawGameState], int],
    expected_map: MapId,
    timing: CascadeTiming,
    label: str,
    intent: BattleIntent,
) -> RawGameState:
    try:
        return run_adaptive_trainer_battle(
            reader,
            executor,
            policy,
            expected_map=expected_map,
            intent=intent,
            timing=timing.battle_runtime,
            label=label,
        )
    except BattleRuntimeError as error:
        raise CascadeChapterError(str(error)) from error


class _PauseForCeruleanRivalPotion(Exception):
    pass


class _PauseForCeruleanRivalAccuracyReset(Exception):
    pass


def _run_cerulean_rival_with_potion(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    emulator: EmulatorState,
    timing: CascadeTiming,
) -> RawGameState:
    """Use the fixed Potion reserve only at stable semantic gates."""

    starting_reserve = _bag_quantity(emulator, ItemId.POTION)
    if not 1 <= starting_reserve <= CERULEAN_RIVAL_MAX_POTION_RESERVE:
        raise CascadeChapterError("Cerulean rival recovery reserve is outside its fixed bound.")
    intent = BattleIntent(
        "help_bill",
        battle_plan_id=CERULEAN_RIVAL_BATTLE_PLAN_ID,
        resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
    )
    accuracy_reset_complete = False
    forced_switches = 0
    must_attack_after_recovery = False

    def guarded_policy(raw: RawGameState) -> int:
        nonlocal must_attack_after_recovery
        if raw.active_party_index not in {None, 0}:
            return _cerulean_rival_reserve_move_slot(raw)
        if (
            not must_attack_after_recovery
            and _bag_quantity(emulator, ItemId.POTION) > ROUTE_24_RECOVERY_POTION_RESERVE
            and _should_use_cerulean_rival_potion(raw)
        ):
            raise _PauseForCeruleanRivalPotion
        if raw.enemy_species_id == ABRA_SPECIES_ID and not accuracy_reset_complete:
            raise _PauseForCeruleanRivalAccuracyReset
        must_attack_after_recovery = False
        return choose_cerulean_rival_move_slot(raw)

    recoveries = 0
    while True:
        try:
            return run_adaptive_trainer_battle(
                reader,
                executor,
                guarded_policy,
                expected_map=MapId.CERULEAN_CITY,
                intent=intent,
                timing=timing.battle_runtime,
                label="Cerulean rival",
            )
        except BattleRuntimeError as error:
            if isinstance(error.__cause__, _PauseForCeruleanRivalAccuracyReset):
                _reset_cerulean_rival_accuracy(reader, executor, emulator, timing)
                accuracy_reset_complete = True
                continue
            if not isinstance(error.__cause__, _PauseForCeruleanRivalPotion):
                raw = reader.read()
                party_hp = _rival_party_hp(emulator)
                if (
                    raw.battle_state == 2
                    and raw.battler_hp == 0
                    and forced_switches == 0
                    and party_hp[1] > 0
                ):
                    _settle_cerulean_rival_forced_switch(
                        reader,
                        executor,
                        emulator,
                        timing,
                        target_index=1,
                    )
                    forced_switches += 1
                    continue
                raise CascadeChapterError(str(error)) from error
        _use_cerulean_rival_potion(reader, executor, emulator, timing)
        must_attack_after_recovery = True
        recoveries += 1
        if recoveries > starting_reserve - ROUTE_24_RECOVERY_POTION_RESERVE:
            raise CascadeChapterError("Cerulean rival exceeded its fixed recovery reserve.")


def _cerulean_rival_reserve_move_slot(raw: RawGameState) -> int:
    """Choose one legal reserve attack after the protected lead is knocked out."""

    if raw.active_party_index in {None, 0} or raw.battler_moves is None or raw.battler_pp is None:
        raise CascadeChapterError("Cerulean rival reserve lacks active move evidence.")
    for slot, (move, pp) in enumerate(
        zip(raw.battler_moves, raw.battler_pp, strict=True),
        start=1,
    ):
        if move and pp & 0x3F and raw.player_disabled_move_slot != slot:
            return slot
    raise CascadeChapterError("Cerulean rival reserve has no legal attack.")


def _settle_cerulean_rival_forced_switch(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    emulator: EmulatorState,
    timing: CascadeTiming,
    *,
    target_index: int,
) -> None:
    """Select the sole living reserve after a KO and prove stable battle MAIN."""

    party_hp = _rival_party_hp(emulator)
    if target_index != 1 or party_hp[target_index] <= 0:
        raise CascadeChapterError("Cerulean rival forced switch lacks a living reserve.")
    for pulse_index in range(64):
        raw = reader.read()
        if (
            raw.battle_state == 2
            and raw.active_party_index == target_index
            and (raw.battler_hp or 0) > 0
            and reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN
        ):
            return
        if raw.battle_state != 2:
            raise CascadeChapterError("Cerulean rival forced switch left its battle.")
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        _battle_pulse(
            executor,
            MacroActionKind.CONFIRM if cursor == target_index else MacroActionKind.MOVE,
            None if cursor == target_index else ("down" if cursor < target_index else "up"),
            timing,
            frames=timing.battle_runtime.menu_wait_frames,
        )
        if pulse_index % 5 == 4:
            _battle_pulse(
                executor,
                MacroActionKind.CONFIRM,
                None,
                timing,
                frames=timing.battle_runtime.menu_wait_frames,
            )
    raise CascadeChapterError("Cerulean rival forced switch exceeded its bounded menu pulses.")


def _should_use_cerulean_rival_potion(raw: RawGameState) -> bool:
    hp = raw.first_party_hp
    max_hp = raw.first_party_max_hp
    if (
        hp is None
        or max_hp is None
        or hp <= 0
        or hp > max_hp
        or raw.enemy_species_id not in CERULEAN_RIVAL_RECOVERY_HP_THRESHOLDS
    ):
        raise ValueError("Cerulean rival recovery lacks valid live HP/species evidence.")
    return hp <= CERULEAN_RIVAL_RECOVERY_HP_THRESHOLDS[raw.enemy_species_id]


def _reset_cerulean_rival_accuracy(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    emulator: EmulatorState,
    timing: CascadeTiming,
) -> None:
    """Switch out and back during Abra to clear Pidgeotto's accuracy drops."""

    before = reader.read()
    before_menu = reader.read_battle_menu_state(before)
    before_party_hp = _rival_party_hp(emulator)
    before_pp = before.first_party_pp
    before_enemy_hp = before.enemy_hp
    if (
        before.battle_state != 2
        or before.enemy_species_id != ABRA_SPECIES_ID
        or before_menu.phase is not BattleMenuPhase.MAIN
        or before.party_species_ids != (WARTORTLE_SPECIES_ID, ZUBAT_SPECIES_ID)
        or emulator.read_u8(RamAddress.PLAYER_MON_NUMBER) != 0
        or before_pp is None
        or before_enemy_hp is None
        or before.player_accuracy_stage is None
        or not 1 <= before.player_accuracy_stage <= 7
    ):
        raise CascadeChapterError("Cerulean rival accuracy reset has an invalid starting gate.")

    _switch_cerulean_rival_party_slot(
        reader,
        executor,
        emulator,
        timing,
        target_index=1,
    )
    helper = reader.read()
    if (
        emulator.read_u8(RamAddress.PLAYER_MON_NUMBER) != 1
        or helper.player_accuracy_stage != 7
        or helper.enemy_species_id != ABRA_SPECIES_ID
        or helper.enemy_hp != before_enemy_hp
        or _rival_party_hp(emulator) != before_party_hp
        or helper.first_party_pp != before_pp
    ):
        raise CascadeChapterError("Cerulean rival helper switch changed protected battle state.")

    _switch_cerulean_rival_party_slot(
        reader,
        executor,
        emulator,
        timing,
        target_index=0,
    )
    returned = reader.read()
    if (
        emulator.read_u8(RamAddress.PLAYER_MON_NUMBER) != 0
        or returned.player_accuracy_stage != 7
        or returned.enemy_species_id != ABRA_SPECIES_ID
        or returned.enemy_hp != before_enemy_hp
        or _rival_party_hp(emulator) != before_party_hp
        or returned.first_party_pp != before_pp
    ):
        raise CascadeChapterError("Cerulean rival accuracy reset changed protected battle state.")


def _switch_cerulean_rival_party_slot(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    emulator: EmulatorState,
    timing: CascadeTiming,
    *,
    target_index: int,
) -> None:
    raw = reader.read()
    menu = reader.read_battle_menu_state(raw)
    if (
        target_index not in {0, 1}
        or raw.battle_state != 2
        or raw.enemy_species_id != ABRA_SPECIES_ID
        or menu.phase is not BattleMenuPhase.MAIN
    ):
        raise CascadeChapterError("Cerulean rival party switch lacks a stable MAIN-menu gate.")

    _navigate_rival_main_command(executor, menu.selected_main_command, 2, timing)
    _battle_pulse(executor, MacroActionKind.CONFIRM, None, timing)
    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == target_index:
            break
        _battle_pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if cursor < target_index else "up",
            timing,
        )
    else:
        raise CascadeChapterError("Cerulean rival could not select the intended party slot.")

    _battle_pulse(executor, MacroActionKind.CONFIRM, None, timing)
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 0:
        raise CascadeChapterError("Cerulean rival party submenu did not select SWITCH.")
    _battle_pulse(
        executor,
        MacroActionKind.CONFIRM,
        None,
        timing,
        frames=timing.battle_runtime.dialogue_wait_frames,
    )
    for pulse in range(48):
        settled = reader.read()
        settled_menu = reader.read_battle_menu_state(settled)
        if (
            settled.battle_state == 2
            and settled.enemy_species_id == ABRA_SPECIES_ID
            and settled_menu.phase is BattleMenuPhase.MAIN
            and emulator.read_u8(RamAddress.PLAYER_MON_NUMBER) == target_index
        ):
            return
        _battle_pulse(
            executor,
            MacroActionKind.CANCEL if (pulse + 1) % 4 == 0 else MacroActionKind.CONFIRM,
            None,
            timing,
            frames=timing.battle_runtime.dialogue_wait_frames,
        )
    raise CascadeChapterError("Cerulean rival party switch did not return to MAIN.")


def _navigate_rival_main_command(
    executor: _CountingChapterExecutor,
    current: int | None,
    target: int,
    timing: CascadeTiming,
) -> None:
    if target != 2:
        raise CascadeChapterError("Cerulean rival main-menu target is unsupported.")
    directions = {
        0: ("right",),
        1: ("up", "right"),
        2: (),
        3: ("up",),
    }.get(current)
    if directions is None:
        raise CascadeChapterError("Cerulean rival exposed an invalid main battle cursor.")
    for direction in directions:
        _battle_pulse(executor, MacroActionKind.MOVE, direction, timing)


def _rival_party_hp(emulator: EmulatorState) -> tuple[int, int]:
    return (
        _read_u16(emulator, RamAddress.PARTY_MON_1_HP),
        _read_u16(emulator, RamAddress.PARTY_MON_2_HP),
    )


def _read_u16(emulator: EmulatorState, address: RamAddress) -> int:
    return emulator.read_u8(int(address)) * 0x100 + emulator.read_u8(int(address) + 1)


def _use_cerulean_rival_potion(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    emulator: EmulatorState,
    timing: CascadeTiming,
) -> None:
    _use_battle_recovery_item(
        reader,
        executor,
        emulator,
        timing,
        item=ItemId.POTION,
        heal_amount=POTION_HEAL_AMOUNT,
        max_quantity=CERULEAN_RIVAL_MAX_POTION_RESERVE,
        label="Cerulean rival Potion",
    )


def _use_battle_recovery_item(
    reader: PokemonRedStateReader,
    executor: _CountingChapterExecutor,
    emulator: EmulatorState,
    timing: CascadeTiming,
    *,
    item: ItemId,
    heal_amount: int,
    max_quantity: int,
    label: str,
) -> None:
    """Use one bounded healing item and prove its HP, quantity, and MAIN return."""

    before = reader.read()
    menu = reader.read_battle_menu_state(before)
    before_quantity = _bag_quantity(emulator, item)
    if (
        before.battle_state != 2
        or menu.phase is not BattleMenuPhase.MAIN
        or before.first_party_hp is None
        or before.first_party_max_hp is None
        or not 0 < before.first_party_hp < before.first_party_max_hp
        or not 1 <= before_quantity <= max_quantity
    ):
        raise CascadeChapterError(
            f"{label} recovery requires one item and a damaged living lead "
            "at the trainer MAIN menu."
        )

    command = menu.selected_main_command
    if command == 0:
        _battle_pulse(executor, MacroActionKind.MOVE, "down", timing)
    elif command == 2:
        _battle_pulse(executor, MacroActionKind.MOVE, "left", timing)
        _battle_pulse(executor, MacroActionKind.MOVE, "down", timing)
    elif command == 3:
        _battle_pulse(executor, MacroActionKind.MOVE, "left", timing)
    elif command != 1:
        raise CascadeChapterError(f"{label} exposed an invalid battle command cursor.")

    selected = reader.read_battle_menu_state(reader.read())
    if selected.phase is not BattleMenuPhase.MAIN or selected.selected_main_command != 1:
        raise CascadeChapterError(f"{label} recovery could not select ITEM.")
    _battle_pulse(executor, MacroActionKind.CONFIRM, None, timing)
    _select_bag_item(executor, emulator, item, timing)
    _battle_pulse(executor, MacroActionKind.CONFIRM, None, timing)

    for _ in range(6):
        if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) == 0:
            break
        _battle_pulse(executor, MacroActionKind.MOVE, "up", timing)
    else:
        raise CascadeChapterError(f"{label} recovery could not select the party lead.")

    executor.execute(MacroAction(MacroActionKind.CONFIRM))
    expected_healed_hp = min(
        before.first_party_max_hp,
        before.first_party_hp + heal_amount,
    )
    current = reader.read()
    saw_exact_heal = (
        current.first_party_hp == expected_healed_hp
        and _bag_quantity(emulator, item) == before_quantity - 1
    )
    for _ in range(30):
        _wait(executor, timing.battle_runtime.dialogue_wait_frames)
        current = reader.read()
        if current.first_party_hp == expected_healed_hp:
            saw_exact_heal = True
        if (
            saw_exact_heal
            and _bag_quantity(emulator, item) == before_quantity - 1
            and current.battle_state == 2
            and current.first_party_hp is not None
            and current.first_party_hp > 0
            and reader.read_battle_menu_state(current).phase is BattleMenuPhase.MAIN
        ):
            return
        if current.battle_state != 2 or (current.first_party_hp or 0) <= 0:
            raise CascadeChapterError(
                f"{label} recovery lost the active living battle before returning to MAIN."
            )
        executor.execute(MacroAction(MacroActionKind.CANCEL))
    raise CascadeChapterError(
        f"{label} missed its bounded heal, quantity, or MAIN-menu proof."
    )


def _select_bag_item(
    executor: _CountingChapterExecutor,
    emulator: EmulatorState,
    item: ItemId,
    timing: CascadeTiming,
) -> None:
    for _ in range(24):
        items = _bag_item_ids(emulator)
        if item not in items:
            raise CascadeChapterError(f"Required bag item {int(item):#04x} is unavailable.")
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        target = items.index(item)
        if absolute == target:
            return
        _battle_pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if absolute < target else "up",
            timing,
        )
    raise CascadeChapterError(f"Could not select bag item {int(item):#04x}.")


def _bag_item_ids(emulator: EmulatorState) -> tuple[int, ...]:
    count = emulator.read_u8(RamAddress.NUM_BAG_ITEMS)
    if not 0 <= count <= 20:
        raise CascadeChapterError("Bag item count is outside the supported bound.")
    return tuple(emulator.read_u8(int(RamAddress.BAG_ITEMS) + index * 2) for index in range(count))


def _bag_quantity(emulator: EmulatorState, item: ItemId) -> int:
    items = _bag_item_ids(emulator)
    if item not in items:
        return 0
    index = items.index(item)
    return emulator.read_u8(int(RamAddress.BAG_ITEMS) + index * 2 + 1)


def _money(emulator: EmulatorState) -> int:
    value = 0
    for offset in range(3):
        packed = emulator.read_u8(int(RamAddress.PLAYER_MONEY) + offset)
        high, low = packed >> 4, packed & 0x0F
        if high > 9 or low > 9:
            raise CascadeChapterError(f"Player money contains invalid BCD byte {packed:#04x}.")
        value = value * 100 + high * 10 + low
    return value


def _battle_pulse(
    executor: _CountingChapterExecutor,
    kind: MacroActionKind,
    value: str | None,
    timing: CascadeTiming,
    *,
    frames: int | None = None,
) -> None:
    executor.execute(MacroAction(kind, value))
    _wait(
        executor,
        timing.battle_runtime.menu_wait_frames if frames is None else frames,
    )


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
    raise CascadeChapterError(f"Bill dialogue missed the bounded {expected[position].value} gate.")


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
