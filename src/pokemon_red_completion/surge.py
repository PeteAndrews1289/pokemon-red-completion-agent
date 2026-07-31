"""Deterministic HM01-to-Thunder-Badge chapter for pinned Pokémon Red."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.observation import (
    Badge,
    BattleMenuPhase,
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
    SurgePhase,
    SurgeProgressError,
    SurgeProgressTracker,
    SurgeState,
    event_flag_is_set,
)

SURGE_CHECKPOINT_COUNT = 15
SPEAROW_SPECIES_ID = 0x05
DUX_SPECIES_ID = 0x40
DIGLETT_SPECIES_ID = 0x3B
DIGLETT_CAPTURE_LEVELS = frozenset(range(19, 23))
DIGLETT_SEARCH_SEED_WAIT_FRAMES = 199
WARTORTLE_SPECIES_ID = 0xB3
SPEAROW_CAPTURE_MOVE_ID = 0x37
SPEAROW_CAPTURE_MOVE_SLOT = 4
CUT_MOVE_ID = 0x0F
DIG_MOVE_ID = 0x5B
LT_SURGE_OPPONENT_ID = 0xEC
LT_SURGE_TRAINER_CLASS_ID = 0x24
LT_SURGE_TRAINER_SET = 1
DUX_NICKNAME = (0x83, 0x94, 0x97, 0x50)


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "D": "down", "L": "left", "R": "right"}[letter] for letter in value)


CAPTAIN_EXIT = _directions("LDLLLDDD")
SHIP_2F_RETURN = _directions("D" * 6 + "L" * 2 + "D" * 2 + "L" * 31 + "UL" + "U" * 7)
SHIP_1F_RETURN = _directions("R" * 9 + "DR" + "R" * 14 + "U" * 3 + "R" + "U" * 4)
CITY_TO_CENTER = _directions(
    "RUURRRRRURRRRRR" + "U" * 12 + "L" * 12 + "U" * 5 + "LLUU" + "L" * 5 + "U" * 5
)
CENTER_TO_MART = _directions("DDDD" + "R" * 5 + "DDRR" + "D" * 5 + "R" * 5 + "UU")


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...

    def press(self, button: str) -> None: ...

    def release(self, button: str) -> None: ...

    def tick(self, frames: int) -> None: ...


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class SurgeChapterError(RuntimeError):
    """Raised when the bounded Thunder Badge route misses a semantic gate."""


@dataclass(frozen=True, slots=True)
class SurgeTiming:
    wait_frames: int = 180
    transition_frames: int = 120
    movement_retries: int = 14
    encounter_steps: int = 600
    encounter_limit: int = 24
    battle_pulses: int = 720
    reward_pulses: int = 40

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_SURGE_TIMING = SurgeTiming()


@dataclass(frozen=True, slots=True)
class SurgeProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[SurgeProgress], None]


@dataclass(frozen=True, slots=True)
class SurgeCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class SurgeChapterReport:
    records: tuple[SurgeCheckpoint, ...]
    final_raw: RawGameState
    beat_lt_surge: bool
    got_tm24: bool
    tm24_in_bag: bool
    badge_bits: int
    badge_mirror_bits: int
    dig_attacks: int
    wrong_move_count: int
    super_potion_used: bool
    final_lead_hp: int
    final_lead_max_hp: int
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == SURGE_CHECKPOINT_COUNT
            and self.beat_lt_surge
            and self.got_tm24
            and self.tm24_in_bag
            and self.badge_bits & Badge.THUNDER
            and self.badge_mirror_bits & Badge.THUNDER
            and self.dig_attacks >= 3
            and self.wrong_move_count == 0
            and self.final_raw.battle_state == 0
            and self.final_raw.first_party_status == 0
            and self.final_raw.first_party_hp == self.final_lead_hp
            and self.final_raw.first_party_max_hp == self.final_lead_max_hp
            and 0 < self.final_lead_hp <= self.final_lead_max_hp
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "defeat_surge",
            "battle": {
                "dig_attacks": self.dig_attacks,
                "wrong_move_count": self.wrong_move_count,
            },
            "reward": {
                "beat_lt_surge": self.beat_lt_surge,
                "got_tm24": self.got_tm24,
                "tm24_in_bag": self.tm24_in_bag,
                "thunder_badge": bool(self.badge_bits & Badge.THUNDER),
                "thunder_badge_mirror": bool(self.badge_mirror_bits & Badge.THUNDER),
            },
            "recovery": {
                "super_potion_used": self.super_potion_used,
                "lead_hp": self.final_lead_hp,
                "lead_max_hp": self.final_lead_max_hp,
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


def run_surge_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    timing: SurgeTiming = DEFAULT_SURGE_TIMING,
    progress: ProgressSink | None = None,
) -> SurgeChapterReport:
    """Continue the verified Captain boundary through Lt. Surge's reward."""

    start_frames = emulator.frame_count
    actions = _CountingExecutor(executor)
    tracker = SurgeProgressTracker()
    records: list[SurgeCheckpoint] = []

    raw = reader.read()
    _gate(
        raw,
        _event(raw, EventFlag.GOT_HM01) and ItemId.HM01_CUT in _bag_ids(emulator),
        tracker,
        SurgePhase.HM01_READY,
        "hm01_ready",
        "Verified HM01-ready Captain boundary",
        records,
        progress,
        emulator,
    )

    _confirm(actions, 3, 240)
    _move(actions, reader, CAPTAIN_EXIT, timing, "Captain exit")
    _wait(actions, timing.transition_frames)
    _move(actions, reader, SHIP_2F_RETURN, timing, "ship second-floor return")
    _wait(actions, timing.transition_frames)
    _move(actions, reader, SHIP_1F_RETURN, timing, "ship first-floor return")
    _wait(actions, timing.transition_frames)
    _move(actions, reader, ("up", "up"), timing, "dock return")
    _confirm(actions, 3, 240)
    _require(reader.read(), MapId.VERMILION_CITY, (18, 29), 0, "ship departure")

    _move(actions, reader, CITY_TO_CENTER, timing, "Vermilion Center")
    _require(reader.read(), MapId.VERMILION_POKECENTER, (3, 7), 0, "Center entry")
    _move(actions, reader, _directions("UUUU"), timing, "nurse")
    _confirm(actions, 9, 240)
    raw = reader.read()
    _gate(
        raw,
        raw.first_party_hp == raw.first_party_max_hp and raw.first_party_status == 0,
        tracker,
        SurgePhase.HEALED,
        "healed",
        "Healed Wartortle before the capture route",
        records,
        progress,
        emulator,
    )
    _move(actions, reader, _directions("DDDDD"), timing, "Center exit")
    _move(actions, reader, CENTER_TO_MART, timing, "Vermilion Mart")
    _require(reader.read(), MapId.VERMILION_MART, (3, 7), 0, "Mart entry")
    _move(actions, reader, _directions("UUL"), timing, "Mart clerk")
    _pulse(actions, MacroActionKind.MOVE, "left", 60)
    _confirm(actions, 4, 180)
    _confirm(actions, 2, 240)
    for _ in range(60):
        quantity = _bag(emulator).get(ItemId.POKE_BALL, 0)
        if quantity == 10:
            break
        if not 1 <= quantity < 10:
            raise SurgeChapterError(f"Unexpected Poké Ball quantity {quantity}.")
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    else:
        raise SurgeChapterError("Repeated single-ball purchase missed quantity ten.")
    _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    _pulse(actions, MacroActionKind.MOVE, "down", 180)
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 1:
        raise SurgeChapterError(
            "Mart list could not select Super Potion after Poké Balls: "
            f"cursor={emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)}, "
            f"scroll={emulator.read_u8(RamAddress.LIST_SCROLL_OFFSET)}."
        )
    _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    for _ in range(6):
        if _bag(emulator).get(ItemId.SUPER_POTION, 0) == 1:
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    else:
        raise SurgeChapterError(
            "Super Potion purchase missed quantity one: "
            f"bag={_bag(emulator)!r}, "
            f"cursor={emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)}, "
            f"scroll={emulator.read_u8(RamAddress.LIST_SCROLL_OFFSET)}."
        )
    _confirm_kind(actions, MacroActionKind.CANCEL, 4, 180)
    raw = reader.read()
    _gate(
        raw,
        _bag(emulator).get(ItemId.POKE_BALL) == 10 and _bag(emulator).get(ItemId.SUPER_POTION) == 1,
        tracker,
        SurgePhase.BALLS_PURCHASED,
        "balls_purchased",
        "Purchased ten Poké Balls and one recovery Super Potion",
        records,
        progress,
        emulator,
    )

    _move(actions, reader, _directions("RDDDD" + "R" * 17), timing, "Route 11")
    _require(reader.read(), MapId.ROUTE_11, (0, 6), 0, "Route 11 entry")
    _move(actions, reader, _directions("R" * 12), timing, "Route 11 grass")
    encounter = _find_spearow(emulator, actions, reader, timing)
    _gate(
        encounter,
        encounter.battle_state == 1
        and encounter.enemy_species_id == SPEAROW_SPECIES_ID
        and encounter.enemy_level in {13, 15, 17},
        tracker,
        SurgePhase.SPEAROW_ENCOUNTER,
        "spearow_encounter",
        "Found an allowed Route 11 Spearow",
        records,
        progress,
        emulator,
    )
    for _ in range(4):
        if _use_spearow_capture_move_once(actions, reader, encounter):
            break
        encounter = _find_spearow(emulator, actions, reader, timing)
    else:
        raise SurgeChapterError("Four bounded attempts did not weaken Spearow.")
    _throw_ball(emulator, actions, reader)
    raw = reader.read()
    _gate(
        raw,
        raw.party_species_ids == (WARTORTLE_SPECIES_ID, SPEAROW_SPECIES_ID)
        and _bag(emulator).get(ItemId.POKE_BALL) == 9,
        tracker,
        SurgePhase.SPEAROW_CAPTURED,
        "spearow_captured",
        "Captured Spearow with one Poké Ball",
        records,
        progress,
        emulator,
    )

    raw = _catch_diglett_chapter(emulator, actions, reader, timing)
    _gate(
        raw,
        raw.party_species_ids == (WARTORTLE_SPECIES_ID, SPEAROW_SPECIES_ID, DIGLETT_SPECIES_ID)
        and emulator.read_u8(RamAddress.PARTY_MON_3_LEVEL) in DIGLETT_CAPTURE_LEVELS,
        tracker,
        SurgePhase.DIGLETT_CAPTURED,
        "diglett_captured",
        "Captured a source-valid Diglett in Diglett's Cave",
        records,
        progress,
        emulator,
    )

    raw = _move_until_map(
        actions,
        reader,
        "left",
        MapId.VERMILION_CITY,
        timing,
        "Route 11 return",
    )
    if raw.player_y != 14 or raw.player_x is None or raw.player_x < 15:
        raise SurgeChapterError("Route 11 return missed the trade-house row.")
    _move(
        actions,
        reader,
        _directions("L" * (raw.player_x - 15) + "UU"),
        timing,
        "trade house",
    )
    _require(reader.read(), MapId.VERMILION_TRADE_HOUSE, (2, 7), 0, "trade house")
    _move(actions, reader, _directions("UR"), timing, "trade girl")
    _pulse(actions, MacroActionKind.MOVE, "up", 60)
    _confirm(actions, 3, 240)
    _pulse(actions, MacroActionKind.MOVE, "down", 120)
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 1:
        raise SurgeChapterError("Trade party cursor did not select Spearow.")
    _confirm(actions, 2, 240)
    _wait(actions, 2000)
    _confirm(actions, 4, 240)
    raw = reader.read()
    traded = bool(emulator.read_u8(RamAddress.NPC_TRADE_FLAGS) & 0x10)
    received_nickname = tuple(
        emulator.read_u8(int(RamAddress.PARTY_MON_3_NICKNAME) + index) for index in range(4)
    )
    if not (
        traded
        and raw.party_species_ids == (WARTORTLE_SPECIES_ID, DIGLETT_SPECIES_ID, DUX_SPECIES_ID)
        and received_nickname == DUX_NICKNAME
    ):
        raise SurgeChapterError(
            "Raw DUX trade result failed: "
            f"flag={traded}, party={raw.party_species_ids!r}, "
            f"nickname={received_nickname!r}."
        )
    _swap_party_slots(
        emulator,
        actions,
        reader,
        source_index=2,
        destination_index=1,
        label="DUX party normalization",
    )
    raw = reader.read()
    nickname = tuple(
        emulator.read_u8(int(RamAddress.PARTY_MON_2_NICKNAME) + index) for index in range(4)
    )
    trade_valid = (
        traded
        and raw.party_species_ids == (WARTORTLE_SPECIES_ID, DUX_SPECIES_ID, DIGLETT_SPECIES_ID)
        and nickname == DUX_NICKNAME
    )
    if not trade_valid:
        raise SurgeChapterError(
            "DUX trade gate failed: "
            f"flag={traded}, party={raw.party_species_ids!r}, "
            f"nickname={nickname!r}."
        )
    _gate(
        raw,
        trade_valid,
        tracker,
        SurgePhase.DUX_TRADED,
        "dux_traded",
        "Traded Spearow for DUX",
        records,
        progress,
        emulator,
    )

    _teach_cut(emulator, actions, reader)
    raw = reader.read()
    dux_moves = _read_four(emulator, RamAddress.PARTY_MON_2_MOVES)
    _gate(
        raw,
        dux_moves[2] == CUT_MOVE_ID and ItemId.HM01_CUT in _bag_ids(emulator),
        tracker,
        SurgePhase.CUT_TAUGHT,
        "cut_taught",
        "Taught reusable HM01 Cut to DUX",
        records,
        progress,
        emulator,
    )
    _prepare_diglett_dig(emulator, actions)
    raw = reader.read()
    diglett_moves = _read_four(emulator, RamAddress.PARTY_MON_3_MOVES)
    diglett_level = emulator.read_u8(RamAddress.PARTY_MON_3_LEVEL)
    dig_ready = DIG_MOVE_ID in diglett_moves and (
        diglett_level >= 19 or ItemId.TM28_DIG not in _bag_ids(emulator)
    )
    if not dig_ready:
        raise SurgeChapterError(
            "Diglett Dig evidence failed: "
            f"level={diglett_level}, moves={diglett_moves!r}, "
            f"tm28_in_bag={ItemId.TM28_DIG in _bag_ids(emulator)}."
        )
    _gate(
        raw,
        dig_ready,
        tracker,
        SurgePhase.DIG_TAUGHT,
        "diglett_dig_ready",
        "Verified natural or TM-taught Dig on Diglett",
        records,
        progress,
        emulator,
    )

    _confirm_kind(actions, MacroActionKind.CANCEL, 2, 180)
    _move(actions, reader, _directions("LDDD"), timing, "trade house exit")
    _move(actions, reader, _directions("DDD"), timing, "Gym tree")
    _cut_tree(emulator, actions, reader)
    _move(actions, reader, _directions("DDLLLU"), timing, "Gym entry")
    _wait(actions, timing.transition_frames)
    raw = reader.read()
    if raw.map_id == MapId.VERMILION_GYM and (raw.player_x, raw.player_y) == (5, 17):
        _move(actions, reader, ("left",), timing, "Gym entry normalization")
        raw = reader.read()
    _gate(
        raw,
        raw.map_id == MapId.VERMILION_GYM and (raw.player_x, raw.player_y) == (4, 17),
        tracker,
        SurgePhase.GYM_REACHED,
        "gym_reached",
        "Entered Vermilion Gym through the cut tree",
        records,
        progress,
        emulator,
    )

    _solve_switches(emulator, actions, reader, timing, tracker, records, progress)
    _swap_party_lead(
        emulator,
        actions,
        reader,
        DIGLETT_SPECIES_ID,
        "Diglett Surge lead",
    )
    raw = reader.read()
    if raw.player_x is None or raw.player_y is None:
        raise SurgeChapterError("Lt. Surge approach lacks a Gym coordinate.")
    _navigate_gym_adaptive(actions, reader, frozenset({(5, 2)}), timing)
    _pulse(actions, MacroActionKind.MOVE, "up", 120)
    _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    battle = _enter_surge(actions, reader, emulator, timing)
    _gate(
        battle,
        battle.battle_state == 2
        and battle.party_species_ids == (DIGLETT_SPECIES_ID, DUX_SPECIES_ID, WARTORTLE_SPECIES_ID)
        and battle.first_party_moves is not None
        and DIG_MOVE_ID in battle.first_party_moves
        and emulator.read_u8(RamAddress.CURRENT_OPPONENT) == LT_SURGE_OPPONENT_ID
        and emulator.read_u8(RamAddress.TRAINER_CLASS) == LT_SURGE_TRAINER_CLASS_ID
        and emulator.read_u8(RamAddress.TRAINER_NUMBER) == LT_SURGE_TRAINER_SET,
        tracker,
        SurgePhase.SURGE_BATTLE,
        "surge_battle",
        "Observed the live Lt. Surge battle",
        records,
        progress,
        emulator,
    )
    pre_battle_pp = battle.first_party_pp
    dig_slot = (battle.first_party_moves or ()).index(DIG_MOVE_ID)
    defeated, dig_attacks = _run_dig_battle(actions, reader, timing)
    off_slot_unchanged = (
        pre_battle_pp is not None
        and defeated.first_party_pp is not None
        and tuple(defeated.first_party_pp[index] for index in range(4) if index != dig_slot)
        == tuple(pre_battle_pp[index] for index in range(4) if index != dig_slot)
    )
    wrong_move_count = 0 if off_slot_unchanged else 1
    _gate(
        defeated,
        defeated.battle_state == 0 and (defeated.first_party_hp or 0) > 0 and wrong_move_count == 0,
        tracker,
        SurgePhase.SURGE_DEFEATED,
        "surge_defeated",
        "Defeated all three Lt. Surge Pokémon using only Dig",
        records,
        progress,
        emulator,
    )
    _clear_rewards(actions, reader, emulator, timing)
    _swap_party_lead(
        emulator,
        actions,
        reader,
        WARTORTLE_SPECIES_ID,
        "Wartortle lead restoration",
    )
    super_potion_used = False
    final = reader.read()
    beat = _event(final, EventFlag.BEAT_LT_SURGE)
    got_tm = _event(final, EventFlag.GOT_TM24)
    tm24 = ItemId.TM24_THUNDERBOLT in _bag_ids(emulator)
    mirror = emulator.read_u8(RamAddress.BEAT_GYM_FLAGS)
    stable = reader.read_input_readiness().ready
    reward_valid = (
        beat
        and got_tm
        and tm24
        and bool((final.badge_bits or 0) & Badge.THUNDER)
        and bool(mirror & Badge.THUNDER)
        and final.battle_state == 0
        and final.party_species_ids == (WARTORTLE_SPECIES_ID, DUX_SPECIES_ID, DIGLETT_SPECIES_ID)
        and final.first_party_hp is not None
        and final.first_party_max_hp is not None
        and 0 < final.first_party_hp <= final.first_party_max_hp
        and final.first_party_status == 0
        and _bag(emulator).get(ItemId.SUPER_POTION, 0) == 1
        and stable
    )
    if not reward_valid:
        raise SurgeChapterError(
            "Surge reward terminal gate failed: "
            f"events={(beat, got_tm)}, tm24={tm24}, "
            f"badges={(final.badge_bits, mirror)}, battle={final.battle_state}, "
            f"party={final.party_species_ids!r}, "
            f"hp={(final.first_party_hp, final.first_party_max_hp)}, "
            f"status={final.first_party_status!r}, "
            f"stable={stable}."
        )
    _gate(
        final,
        reward_valid,
        tracker,
        SurgePhase.REWARD_STABLE,
        "surge_reward_stable",
        "Verified Thunder Badge, TM24, events, and restored control",
        records,
        progress,
        emulator,
    )
    report = SurgeChapterReport(
        records=tuple(records),
        final_raw=final,
        beat_lt_surge=beat,
        got_tm24=got_tm,
        tm24_in_bag=tm24,
        badge_bits=final.badge_bits or 0,
        badge_mirror_bits=mirror,
        dig_attacks=dig_attacks,
        wrong_move_count=wrong_move_count,
        super_potion_used=super_potion_used,
        final_lead_hp=final.first_party_hp or 0,
        final_lead_max_hp=final.first_party_max_hp or 0,
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise SurgeChapterError("Surge chapter failed its evidence contract.")
    return report


def _gate(
    raw: RawGameState,
    valid: bool,
    tracker: SurgeProgressTracker,
    phase: SurgePhase,
    checkpoint_id: str,
    label: str,
    records: list[SurgeCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
) -> None:
    try:
        tracker.observe(SurgeState(phase=phase, **{phase.value: valid}))
    except SurgeProgressError as error:
        raise SurgeChapterError(str(error)) from error
    records.append(SurgeCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            SurgeProgress(
                checkpoint_id, label, len(records), SURGE_CHECKPOINT_COUNT, emulator.frame_count
            )
        )


def _bag(emulator: EmulatorState) -> dict[int, int]:
    count = emulator.read_u8(RamAddress.NUM_BAG_ITEMS)
    return {
        emulator.read_u8(int(RamAddress.BAG_ITEMS) + 2 * index): emulator.read_u8(
            int(RamAddress.BAG_ITEMS) + 2 * index + 1
        )
        for index in range(count)
    }


def _bag_ids(emulator: EmulatorState) -> set[int]:
    return set(_bag(emulator))


def _event(raw: RawGameState, event: EventFlag) -> bool:
    return event_flag_is_set(raw.event_flags, event)


def _read_four(emulator: EmulatorState, address: RamAddress) -> tuple[int, ...]:
    return tuple(emulator.read_u8(int(address) + index) for index in range(4))


def _require(
    raw: RawGameState, map_id: int, coordinate: tuple[int, int], battle: int, label: str
) -> None:
    if (
        raw.map_id != map_id
        or (raw.player_x, raw.player_y) != coordinate
        or raw.battle_state != battle
    ):
        raise SurgeChapterError(f"{label} missed map/coordinate/battle gate.")


def _move(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    directions: Iterable[str],
    timing: SurgeTiming,
    label: str,
) -> RawGameState:
    raw = reader.read()
    for step, direction in enumerate(directions, 1):
        before = raw
        for attempt in range(timing.movement_retries):
            _pulse(executor, MacroActionKind.MOVE, direction, 12 * (attempt + 1))
            raw = reader.read()
            if (
                raw.battle_state
                or raw.map_id != before.map_id
                or (raw.player_x, raw.player_y) != (before.player_x, before.player_y)
            ):
                break
        else:
            raise SurgeChapterError(
                f"{label} blocked at step {step}: "
                f"direction={direction}, map={raw.map_id!r}, "
                f"coordinate={(raw.player_x, raw.player_y)!r}."
            )
        if raw.battle_state:
            raise SurgeChapterError(f"{label} was interrupted by a battle.")
    return raw


def _move_until_map(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    direction: str,
    target_map: int,
    timing: SurgeTiming,
    label: str,
) -> RawGameState:
    for _ in range(24):
        raw = reader.read()
        if raw.map_id == target_map:
            return raw
        _pulse(executor, MacroActionKind.MOVE, direction, 60)
        if reader.read().battle_state:
            raise SurgeChapterError(f"{label} was interrupted by a battle.")
    raise SurgeChapterError(f"{label} missed map {target_map:#04x}.")


def _navigate_main(
    executor: _CountingExecutor, reader: PokemonRedStateReader, target: int
) -> RawGameState:
    for _ in range(32):
        raw = reader.read()
        menu = reader.read_battle_menu_state(raw)
        if menu.phase is BattleMenuPhase.UNKNOWN:
            _pulse(executor, MacroActionKind.CONFIRM)
            continue
        if menu.phase is BattleMenuPhase.MOVE:
            _pulse(executor, MacroActionKind.CANCEL, frames=120)
            continue
        current = menu.selected_main_command
        if current == target:
            return raw
        directions = {
            0: {1: "up", 2: "left", 3: "up"},
            1: {0: "down", 2: "left", 3: "left"},
            3: {0: "right", 1: "right", 2: "down"},
        }
        direction = directions.get(target, {}).get(current)
        if direction is None:
            raise SurgeChapterError("Invalid battle-menu navigation.")
        _pulse(executor, MacroActionKind.MOVE, direction, 120)
    raise SurgeChapterError("Battle menu navigation exceeded its bound.")


def _flee(
    executor: _CountingExecutor, reader: PokemonRedStateReader, encounter: RawGameState
) -> None:
    party = encounter.party_species_ids
    pp = encounter.first_party_pp
    _navigate_main(executor, reader, 3)
    _pulse(executor, MacroActionKind.CONFIRM, frames=240)
    for _ in range(16):
        raw = reader.read()
        if raw.battle_state == 0:
            if (
                raw.party_species_ids != party
                or raw.first_party_pp != pp
                or (raw.first_party_hp or 0) <= 0
            ):
                raise SurgeChapterError("Flee changed protected capture state.")
            return
        _pulse(executor, MacroActionKind.CONFIRM)
    raise SurgeChapterError("Flee exceeded its bounded dialogue.")


def _find_spearow(
    emulator: EmulatorState,
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
) -> RawGameState:
    raw = reader.read()
    encounters = 0
    for step in range(timing.encounter_steps):
        if not raw.battle_state:
            _pulse(executor, MacroActionKind.MOVE, "left" if step % 2 == 0 else "right", 60)
            raw = reader.read()
            continue
        encounters += 1
        if encounters > timing.encounter_limit:
            break
        if raw.enemy_species_id == SPEAROW_SPECIES_ID and raw.enemy_level in {13, 15, 17}:
            return raw
        balls = _bag(emulator).get(ItemId.POKE_BALL)
        _flee(executor, reader, raw)
        if _bag(emulator).get(ItemId.POKE_BALL) != balls:
            raise SurgeChapterError("Non-target flee changed Poké Balls.")
        raw = reader.read()
    raise SurgeChapterError("Spearow search exceeded its bounded encounter budget.")


def _use_spearow_capture_move_once(
    executor: _CountingExecutor, reader: PokemonRedStateReader, encounter: RawGameState
) -> bool:
    slot = SPEAROW_CAPTURE_MOVE_SLOT
    index = slot - 1
    if (
        encounter.first_party_moves is None
        or encounter.first_party_moves[index] != SPEAROW_CAPTURE_MOVE_ID
    ):
        raise SurgeChapterError("Qualified Spearow capture move is unavailable.")
    initial_pp = encounter.first_party_pp
    initial_hp = encounter.enemy_hp
    _navigate_main(executor, reader, 0)
    _pulse(executor, MacroActionKind.CONFIRM, frames=120)
    for _ in range(8):
        raw = reader.read()
        menu = reader.read_battle_menu_state(raw)
        if menu.phase is BattleMenuPhase.MOVE:
            break
        _pulse(
            executor,
            MacroActionKind.CONFIRM if menu.phase is BattleMenuPhase.MAIN else MacroActionKind.WAIT,
            frames=120,
        )
    else:
        raise SurgeChapterError("FIGHT did not expose the move menu.")
    for _ in range(6):
        raw = reader.read()
        menu = reader.read_battle_menu_state(raw)
        slot = menu.selected_move_slot
        if menu.phase is BattleMenuPhase.MOVE and slot == SPEAROW_CAPTURE_MOVE_SLOT:
            break
        if menu.phase is not BattleMenuPhase.MOVE or slot is None:
            raise SurgeChapterError("Lost the capture move cursor.")
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if slot < SPEAROW_CAPTURE_MOVE_SLOT else "up",
            120,
        )
    else:
        raise SurgeChapterError("Could not select the qualified Spearow capture move.")
    if (
        raw.first_party_moves is None
        or raw.first_party_moves[index] != SPEAROW_CAPTURE_MOVE_ID
    ):
        raise SurgeChapterError("Selected the wrong Spearow capture move.")
    _pulse(executor, MacroActionKind.CONFIRM)
    for _ in range(24):
        raw = reader.read()
        if (
            raw.first_party_pp
            and initial_pp
            and raw.first_party_pp[index] == initial_pp[index] - 1
        ):
            if tuple(
                raw.first_party_pp[other]
                for other in range(4)
                if other != index
            ) != tuple(
                initial_pp[other] for other in range(4) if other != index
            ):
                raise SurgeChapterError("An off-slot move spent PP during capture.")
            break
        _pulse(executor, MacroActionKind.CONFIRM)
    else:
        raise SurgeChapterError("Spearow capture move did not spend exactly one PP.")
    for _ in range(16):
        raw = reader.read()
        if raw.battle_state == 0:
            if raw.party_species_ids != encounter.party_species_ids:
                raise SurgeChapterError("Capture-move knockout changed the protected party.")
            return False
        if raw.enemy_hp == 0:
            for _ in range(16):
                _pulse(executor, MacroActionKind.CONFIRM)
                cleared = reader.read()
                if cleared.battle_state == 0:
                    if cleared.party_species_ids != encounter.party_species_ids:
                        raise SurgeChapterError(
                            "Capture-move knockout changed the protected party."
                        )
                    return False
            raise SurgeChapterError("Capture-move knockout did not clear its battle dialogue.")
        if reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN:
            if raw.enemy_hp == initial_hp:
                return False
            if raw.enemy_hp is None or initial_hp is None or not 0 < raw.enemy_hp < initial_hp:
                raise SurgeChapterError("Spearow capture damage gate failed.")
            return True
        _pulse(executor, MacroActionKind.CONFIRM)
    raise SurgeChapterError("Capture battle did not return to MAIN.")


def _throw_ball(
    emulator: EmulatorState, executor: _CountingExecutor, reader: PokemonRedStateReader
) -> None:
    before = _bag(emulator).get(ItemId.POKE_BALL, 0)
    _navigate_main(executor, reader, 1)
    _pulse(executor, MacroActionKind.CONFIRM)
    for _ in range(12):
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        items = tuple(_bag(emulator))
        if absolute < len(items) and items[absolute] == ItemId.POKE_BALL:
            break
        # Preserve the former 98-frame pulse while keeping all controller I/O
        # inside the authoritative executor: 8 pressed + 16 released + 74 wait.
        _pulse(executor, MacroActionKind.MOVE, "down", frames=74)
    else:
        raise SurgeChapterError("Could not select Poké Ball by absolute bag index.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=360)
    for _ in range(30):
        raw = reader.read()
        if raw.battle_state == 0 and raw.party_species_ids == (
            WARTORTLE_SPECIES_ID,
            SPEAROW_SPECIES_ID,
        ):
            break
        _pulse(executor, MacroActionKind.CONFIRM)
    else:
        raise SurgeChapterError("Poké Ball did not capture Spearow.")
    _confirm_kind(executor, MacroActionKind.CANCEL, 3, 180)
    if _bag(emulator).get(ItemId.POKE_BALL) != before - 1:
        raise SurgeChapterError("Capture did not consume exactly one Poké Ball.")


def _catch_diglett_chapter(
    emulator: EmulatorState,
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
) -> RawGameState:
    raw = reader.read()
    if (
        raw.map_id != MapId.ROUTE_11
        or raw.player_x is None
        or raw.player_y != 6
        or raw.player_x < 4
    ):
        raise SurgeChapterError("Diglett Cave detour lacked its Route 11 origin.")
    _move(
        executor,
        reader,
        _directions("L" * (raw.player_x - 4) + "U"),
        timing,
        "Diglett Cave Route 11 gate",
    )
    _wait(executor, timing.transition_frames)
    raw = reader.read()
    if raw.map_id != MapId.DIGLETTS_CAVE_ROUTE_11 or raw.player_x is None or raw.player_y is None:
        raise SurgeChapterError("Route 11 Diglett Cave gate did not load.")
    to_cave = "U" * max(raw.player_y - 4, 0)
    to_cave += ("R" if raw.player_x < 4 else "L") * abs(raw.player_x - 4)
    _move(executor, reader, _directions(to_cave), timing, "Diglett Cave entry")
    _wait(executor, timing.transition_frames)
    entry = reader.read()
    if entry.map_id != MapId.DIGLETTS_CAVE or entry.player_x is None or entry.player_y is None:
        raise SurgeChapterError(
            "Diglett Cave interior did not load: "
            f"map={entry.map_id!r}, coordinate={(entry.player_x, entry.player_y)!r}."
        )

    _wait(executor, DIGLETT_SEARCH_SEED_WAIT_FRAMES)
    encounter = reader.read()
    for step in range(240):
        if encounter.battle_state == 0:
            _pulse(
                executor,
                MacroActionKind.MOVE,
                "left" if step % 2 == 0 else "right",
                60,
            )
            encounter = reader.read()
            continue
        if (
            encounter.enemy_species_id == DIGLETT_SPECIES_ID
            and encounter.enemy_level in DIGLETT_CAPTURE_LEVELS
            and (encounter.enemy_hp or 0) > 0
        ):
            break
        _flee(executor, reader, encounter)
        encounter = reader.read()
    else:
        raise SurgeChapterError("Diglett search exceeded its bounded encounter steps.")
    _throw_until_caught_diglett(emulator, executor, reader)
    raw = reader.read()
    if (
        raw.party_species_ids != (WARTORTLE_SPECIES_ID, SPEAROW_SPECIES_ID, DIGLETT_SPECIES_ID)
        or raw.player_x is None
        or raw.player_y is None
    ):
        raise SurgeChapterError("Diglett capture produced the wrong party.")

    horizontal = (
        "R" * (entry.player_x - raw.player_x)
        if raw.player_x < entry.player_x
        else "L" * (raw.player_x - entry.player_x)
    )
    vertical = (
        "D" * (entry.player_y - raw.player_y)
        if raw.player_y < entry.player_y
        else "U" * (raw.player_y - entry.player_y)
    )
    _move(executor, reader, _directions(horizontal + vertical + "D"), timing, "cave exit")
    _wait(executor, timing.transition_frames)
    raw = reader.read()
    if raw.map_id != MapId.DIGLETTS_CAVE_ROUTE_11 or raw.player_x is None or raw.player_y is None:
        raise SurgeChapterError("Diglett Cave return gate did not load.")
    if raw.player_x > 3:
        _move(
            executor,
            reader,
            ("left",) * (raw.player_x - 3),
            timing,
            "Route 11 gate exit column",
        )
    returned = _move_until_map(
        executor,
        reader,
        "down",
        MapId.ROUTE_11,
        timing,
        "Diglett Cave Route 11 return",
    )
    _wait(executor, timing.transition_frames)
    return reader.read() if returned.map_id == MapId.ROUTE_11 else returned


def _throw_until_caught_diglett(
    emulator: EmulatorState,
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
) -> None:
    starting_balls = _bag(emulator).get(ItemId.POKE_BALL, 0)
    for _ in range(min(starting_balls, 8)):
        _navigate_main(executor, reader, 1)
        _pulse(executor, MacroActionKind.CONFIRM)
        _select_bag_item(emulator, executor, ItemId.POKE_BALL)
        _pulse(executor, MacroActionKind.CONFIRM, frames=360)
        for _ in range(32):
            raw = reader.read()
            if raw.battle_state == 0 and raw.party_species_ids == (
                WARTORTLE_SPECIES_ID,
                SPEAROW_SPECIES_ID,
                DIGLETT_SPECIES_ID,
            ):
                _confirm_kind(executor, MacroActionKind.CANCEL, 3, 180)
                used = starting_balls - _bag(emulator).get(ItemId.POKE_BALL, 0)
                if not 1 <= used <= 8:
                    raise SurgeChapterError("Diglett capture used an invalid ball count.")
                return
            if (
                raw.battle_state == 1
                and reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN
            ):
                break
            _pulse(executor, MacroActionKind.CONFIRM)
    raise SurgeChapterError("Diglett capture exhausted its bounded Poké Balls.")


def _select_bag_item(emulator: EmulatorState, executor: _CountingExecutor, item: int) -> None:
    for _ in range(20):
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        items = tuple(_bag(emulator))
        if absolute < len(items) and items[absolute] == item:
            return
        _pulse(executor, MacroActionKind.MOVE, "down", 120)
    raise SurgeChapterError(f"Could not select bag item {item:#04x}.")


def _teach_cut(
    emulator: EmulatorState, executor: _CountingExecutor, reader: PokemonRedStateReader
) -> None:
    executor.execute(MacroAction(MacroActionKind.OPEN_MENU))
    _wait(executor, 180)
    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == 2:
            break
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if cursor < 2 else "up",
            120,
        )
    else:
        raise SurgeChapterError("Start menu could not select ITEM for HM01.")
    _pulse(executor, MacroActionKind.CONFIRM)
    _select_bag_item(emulator, executor, ItemId.HM01_CUT)
    _confirm(executor, 5)
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 1:
        raise SurgeChapterError("HM01 did not preserve the DUX party cursor.")
    _pulse(executor, MacroActionKind.CONFIRM)
    _confirm(executor, 6)
    _pulse(executor, MacroActionKind.MOVE, "down", 120)
    _pulse(executor, MacroActionKind.MOVE, "down", 120)
    _pulse(executor, MacroActionKind.CONFIRM)
    _confirm(executor, 4)
    if _read_four(emulator, RamAddress.PARTY_MON_2_MOVES)[2] != CUT_MOVE_ID:
        raise SurgeChapterError("HM01 did not replace DUX's third move.")


def _prepare_diglett_dig(
    emulator: EmulatorState,
    executor: _CountingExecutor,
) -> None:
    if DIG_MOVE_ID in _read_four(emulator, RamAddress.PARTY_MON_3_MOVES):
        return
    _pulse(executor, MacroActionKind.MOVE, "up", 120)
    _select_bag_item(emulator, executor, ItemId.TM28_DIG)
    _confirm(executor, 5)
    for _ in range(3):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == 2:
            break
        _pulse(executor, MacroActionKind.MOVE, "down", 120)
    else:
        raise SurgeChapterError("TM28 could not select party-slot-three Diglett.")
    _pulse(executor, MacroActionKind.CONFIRM)
    for _ in range(20):
        if DIG_MOVE_ID in _read_four(
            emulator, RamAddress.PARTY_MON_3_MOVES
        ) and ItemId.TM28_DIG not in _bag_ids(emulator):
            return
        _pulse(executor, MacroActionKind.CONFIRM)
    raise SurgeChapterError("TM28 did not teach Dig and consume exactly one TM.")


def _cut_tree(
    emulator: EmulatorState, executor: _CountingExecutor, reader: PokemonRedStateReader
) -> None:
    for _ in range(20):
        before = reader.read()
        _pulse(executor, MacroActionKind.MOVE, "down", 120)
        after = reader.read()
        if (after.player_x, after.player_y) != (before.player_x, before.player_y):
            raise SurgeChapterError("Tree orientation probe moved unexpectedly.")
        if emulator.read_u8(RamAddress.TILE_IN_FRONT_OF_PLAYER) == 0x3D:
            break
    else:
        raise SurgeChapterError("No cuttable Gym tree was observed.")
    executor.execute(MacroAction(MacroActionKind.OPEN_MENU))
    _wait(executor, 180)
    while emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 1:
        _pulse(executor, MacroActionKind.MOVE, "up", 120)
    _pulse(executor, MacroActionKind.CONFIRM)
    for _ in range(6):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == 1:
            break
        _pulse(executor, MacroActionKind.MOVE, "down" if cursor < 1 else "up", 120)
    else:
        raise SurgeChapterError("Cut could not select DUX by party index.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=180)
    for _ in range(6):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == 0:
            break
        _pulse(executor, MacroActionKind.MOVE, "up", 120)
    else:
        raise SurgeChapterError("DUX field menu could not select Cut.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=180)
    for _ in range(12):
        if (
            emulator.read_u8(RamAddress.TILE_IN_FRONT_OF_PLAYER) != 0x3D
            and reader.read_input_readiness().ready
        ):
            break
        _pulse(executor, MacroActionKind.CONFIRM, frames=180)
    else:
        raise SurgeChapterError("Cut did not clear the Gym tree and restore field input.")
    _move(executor, reader, ("down",), DEFAULT_SURGE_TIMING, "cut tree passage")


def _swap_party_lead(
    emulator: EmulatorState,
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    species_id: int,
    label: str,
) -> RawGameState:
    before = reader.read()
    species = before.party_species_ids or ()
    if species and species[0] == species_id:
        return before
    try:
        target_index = species.index(species_id)
    except ValueError as error:
        raise SurgeChapterError(f"{label} target species is absent.") from error
    executor.execute(MacroAction(MacroActionKind.OPEN_MENU))
    _wait(executor, 180)
    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == 1:
            break
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if cursor < 1 else "up",
            120,
        )
    else:
        raise SurgeChapterError(f"{label} could not select POKéMON.")
    _pulse(executor, MacroActionKind.CONFIRM)
    for _ in range(6):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == target_index:
            break
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if cursor < target_index else "up",
            120,
        )
    else:
        raise SurgeChapterError(f"{label} could not select its party slot.")
    _pulse(executor, MacroActionKind.CONFIRM)
    target_moves = _party_moves_for_index(emulator, before, target_index)
    field_move_count = sum(move in {CUT_MOVE_ID, DIG_MOVE_ID} for move in target_moves)
    for _ in range(field_move_count + 1):
        _pulse(executor, MacroActionKind.MOVE, "down", 120)
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != field_move_count + 1:
        raise SurgeChapterError(f"{label} did not select SWITCH.")
    _pulse(executor, MacroActionKind.CONFIRM)
    for _ in range(target_index):
        _pulse(executor, MacroActionKind.MOVE, "up", 120)
    _pulse(executor, MacroActionKind.CONFIRM)
    _confirm_kind(executor, MacroActionKind.CANCEL, 4, 180)
    for _ in range(8):
        if reader.read_input_readiness().ready:
            break
        _pulse(executor, MacroActionKind.CANCEL, frames=180)
    else:
        raise SurgeChapterError(f"{label} did not restore field input.")
    after = reader.read()
    if not after.party_species_ids or after.party_species_ids[0] != species_id:
        raise SurgeChapterError(f"{label} failed its party-order gate.")
    return after


def _party_moves_for_index(
    emulator: EmulatorState,
    state: RawGameState,
    party_index: int,
) -> tuple[int, ...]:
    """Read moves from the selected party struct, never from the current lead."""

    if party_index == 0:
        return state.first_party_moves or ()
    addresses = {
        1: RamAddress.PARTY_MON_2_MOVES,
        2: RamAddress.PARTY_MON_3_MOVES,
    }
    try:
        address = addresses[party_index]
    except KeyError as error:
        raise SurgeChapterError(f"Unsupported party move index {party_index}.") from error
    return _read_four(emulator, address)


def _swap_party_slots(
    emulator: EmulatorState,
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    *,
    source_index: int,
    destination_index: int,
    label: str,
) -> RawGameState:
    before = reader.read()
    species = before.party_species_ids or ()
    if len(species) <= max(source_index, destination_index):
        raise SurgeChapterError(f"{label} lacks the required party slots.")
    expected = list(species)
    expected[source_index], expected[destination_index] = (
        expected[destination_index],
        expected[source_index],
    )
    executor.execute(MacroAction(MacroActionKind.OPEN_MENU))
    _wait(executor, 180)
    for _ in range(8):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == 1:
            break
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if cursor < 1 else "up",
            120,
        )
    else:
        raise SurgeChapterError(f"{label} could not select POKéMON.")
    _pulse(executor, MacroActionKind.CONFIRM)
    for _ in range(6):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == source_index:
            break
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if cursor < source_index else "up",
            120,
        )
    else:
        raise SurgeChapterError(f"{label} could not select its source slot.")
    _pulse(executor, MacroActionKind.CONFIRM)
    _pulse(executor, MacroActionKind.MOVE, "down", 120)
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 1:
        raise SurgeChapterError(f"{label} did not select SWITCH.")
    _pulse(executor, MacroActionKind.CONFIRM)
    direction = "down" if destination_index > source_index else "up"
    for _ in range(abs(destination_index - source_index)):
        _pulse(executor, MacroActionKind.MOVE, direction, 120)
    _pulse(executor, MacroActionKind.CONFIRM)
    _confirm_kind(executor, MacroActionKind.CANCEL, 2, 180)
    after = reader.read()
    if after.party_species_ids != tuple(expected):
        raise SurgeChapterError(f"{label} failed its party-order gate.")
    return after


GYM_CAN_COORDINATES = tuple((column, row) for column in (1, 3, 5, 7, 9) for row in (7, 9, 11))
GYM_OBJECT_COORDINATES = frozenset({(9, 6), (3, 8), (0, 10), (4, 14), (5, 1)})
GYM_SIGHTLINE_EXCLUSIONS = frozenset(
    {(x, 6) for x in range(6, 9)} | {(x, 8) for x in range(0, 3)} | {(x, 10) for x in range(1, 4)}
)


def _plan_gym_path(
    start: tuple[int, int],
    goals: frozenset[tuple[int, int]],
    extra_blocked: frozenset[tuple[int, int]] = frozenset(),
) -> tuple[str, ...]:
    blocked = (
        frozenset(GYM_CAN_COORDINATES)
        | GYM_OBJECT_COORDINATES
        | GYM_SIGHTLINE_EXCLUSIONS
        | extra_blocked
    )
    queue = deque([(start, ())])
    visited = {start}
    steps = (
        ("up", (0, -1)),
        ("left", (-1, 0)),
        ("right", (1, 0)),
        ("down", (0, 1)),
    )
    while queue:
        coordinate, route = queue.popleft()
        if coordinate in goals:
            return route
        for direction, (dx, dy) in steps:
            candidate = (coordinate[0] + dx, coordinate[1] + dy)
            if (
                not 0 <= candidate[0] <= 9
                or not 2 <= candidate[1] <= 17
                or candidate in blocked
                or candidate in visited
            ):
                continue
            visited.add(candidate)
            queue.append((candidate, (*route, direction)))
    raise SurgeChapterError(f"No safe Gym route from {start!r} to {sorted(goals)!r}.")


def _navigate_gym_adaptive(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    goals: frozenset[tuple[int, int]],
    timing: SurgeTiming,
) -> RawGameState:
    """Discover static collision tiles while preserving trainer exclusions."""

    blocked: set[tuple[int, int]] = set()
    deltas = {"up": (0, -1), "left": (-1, 0), "right": (1, 0), "down": (0, 1)}
    for _ in range(80):
        raw = reader.read()
        if raw.player_x is None or raw.player_y is None:
            raise SurgeChapterError("Adaptive Gym navigation lacks a coordinate.")
        start = (raw.player_x, raw.player_y)
        if start in goals:
            return raw
        route = _plan_gym_path(start, goals, frozenset(blocked))
        direction = route[0]
        dx, dy = deltas[direction]
        candidate = (start[0] + dx, start[1] + dy)
        for attempt in range(timing.movement_retries):
            _pulse(executor, MacroActionKind.MOVE, direction, 12 * (attempt + 1))
            after = reader.read()
            if after.battle_state:
                raise SurgeChapterError("Adaptive Gym navigation triggered a battle.")
            if (after.player_x, after.player_y) != start:
                break
        else:
            blocked.add(candidate)
    raise SurgeChapterError("Adaptive Gym navigation exceeded its bounded discoveries.")


def _plan_gym_can_path(
    start: tuple[int, int],
    can_index: int,
) -> tuple[tuple[str, ...], str]:
    if not 0 <= can_index < len(GYM_CAN_COORDINATES):
        raise SurgeChapterError(f"Invalid Gym can index {can_index}.")
    target = GYM_CAN_COORDINATES[can_index]
    directions = (
        ("up", (0, -1)),
        ("left", (-1, 0)),
        ("right", (1, 0)),
        ("down", (0, 1)),
    )
    goals = frozenset(
        (target[0] - dx, target[1] - dy)
        for _, (dx, dy) in directions
        if 0 <= target[0] - dx <= 9 and 2 <= target[1] - dy <= 17
    )
    route = _plan_gym_path(start, goals)
    end = start
    for direction in route:
        dx, dy = dict(directions)[direction]
        end = (end[0] + dx, end[1] + dy)
    for direction, (dx, dy) in directions:
        if (end[0] + dx, end[1] + dy) == target:
            return route, direction
    raise SurgeChapterError(f"Gym can {can_index} lacks a facing stance.")


def _navigate_to_gym_can(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    can_index: int,
    timing: SurgeTiming,
) -> RawGameState:
    raw = reader.read()
    if raw.map_id != MapId.VERMILION_GYM or raw.player_x is None or raw.player_y is None:
        raise SurgeChapterError("Gym can navigation lacks a present map coordinate.")
    if not 0 <= can_index < len(GYM_CAN_COORDINATES):
        raise SurgeChapterError(f"Invalid Gym can index {can_index}.")
    target = GYM_CAN_COORDINATES[can_index]
    deltas = {
        "up": (0, -1),
        "left": (-1, 0),
        "right": (1, 0),
        "down": (0, 1),
    }
    goals = frozenset(
        (target[0] - dx, target[1] - dy)
        for dx, dy in deltas.values()
        if 0 <= target[0] - dx <= 9 and 2 <= target[1] - dy <= 17
    )
    before = _navigate_gym_adaptive(executor, reader, goals, timing)
    stance = (before.player_x, before.player_y)
    facing = next(
        (
            direction
            for direction, (dx, dy) in deltas.items()
            if (stance[0] + dx, stance[1] + dy) == target
        ),
        None,
    )
    if facing is None:
        raise SurgeChapterError(f"Gym can {can_index} lacks a facing stance.")
    _pulse(executor, MacroActionKind.MOVE, facing, 120)
    after = reader.read()
    if (after.player_x, after.player_y) != (before.player_x, before.player_y):
        raise SurgeChapterError(f"Gym can {can_index} facing probe moved unexpectedly.")
    return after


def _solve_switches(
    emulator: EmulatorState,
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
    tracker: SurgeProgressTracker,
    records: list[SurgeCheckpoint],
    progress: ProgressSink | None,
) -> None:
    first = emulator.read_u8(RamAddress.VERMILION_GYM_FIRST_LOCK)
    if not 0 <= first <= 14:
        raise SurgeChapterError(f"Invalid first Gym switch index {first}.")
    _navigate_to_gym_can(executor, reader, first, timing)
    _pulse(executor, MacroActionKind.CONFIRM, frames=240)
    second = emulator.read_u8(RamAddress.VERMILION_GYM_SECOND_LOCK)
    if not 0 <= second <= 14 or second == first:
        raise SurgeChapterError(f"Unexpected qualified switch pair {(first, second)}.")
    _confirm_kind(executor, MacroActionKind.CANCEL, 4, 180)
    raw = reader.read()
    event_byte = _event_byte(raw, EventFlag.BEAT_LT_SURGE)
    _gate(
        raw,
        bool(event_byte & 0x02),
        tracker,
        SurgePhase.FIRST_SWITCH,
        "first_switch",
        "Opened the first electric lock",
        records,
        progress,
        emulator,
    )
    _navigate_to_gym_can(executor, reader, second, timing)
    _pulse(executor, MacroActionKind.CONFIRM, frames=240)
    _confirm_kind(executor, MacroActionKind.CANCEL, 4, 180)
    raw = reader.read()
    event_byte = _event_byte(raw, EventFlag.BEAT_LT_SURGE)
    _gate(
        raw,
        event_byte & 0x03 == 0x03,
        tracker,
        SurgePhase.SECOND_SWITCH,
        "second_switch",
        "Opened both electric locks",
        records,
        progress,
        emulator,
    )


def _event_byte(raw: RawGameState, event: EventFlag) -> int:
    if raw.event_flags is None:
        return 0
    byte_index = int(event) // 8
    return raw.event_flags[byte_index]


def _enter_surge(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SurgeTiming,
) -> RawGameState:
    for _ in range(32):
        raw = reader.read()
        if raw.battle_state == 2:
            return raw
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    opponent = emulator.read_u8(RamAddress.CURRENT_OPPONENT)
    raise SurgeChapterError(f"Lt. Surge intro did not start battle; opponent={opponent:#04x}.")


def _run_dig_battle(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
) -> tuple[RawGameState, int]:
    dig_attacks = 0
    declining_switch = False
    switch_pulses = 0
    protected_party: tuple[int, ...] | None = None
    protected_pp: tuple[int, ...] | None = None
    for _ in range(timing.battle_pulses):
        raw = reader.read()
        if raw.battle_state == 0:
            return raw, dig_attacks
        if raw.battle_state != 2 or (raw.first_party_hp or 0) <= 0:
            raise SurgeChapterError("Lt. Surge battle lost its living trainer-state gate.")
        menu = reader.read_battle_menu_state(raw)
        if raw.enemy_hp == 0:
            if not declining_switch:
                declining_switch = True
                switch_pulses = 0
                protected_party = raw.party_species_ids
                protected_pp = raw.first_party_pp
            _pulse(executor, MacroActionKind.CANCEL)
            continue
        if declining_switch:
            if raw.party_species_ids != protected_party or raw.first_party_pp != protected_pp:
                raise SurgeChapterError(
                    "Post-KO switch decline changed protected party or PP state."
                )
            if menu.phase is BattleMenuPhase.MAIN:
                declining_switch = False
                switch_pulses = 0
            else:
                switch_pulses += 1
                if switch_pulses > 24:
                    raise SurgeChapterError("Post-KO switch decline exceeded its bounded pulses.")
                _pulse(executor, MacroActionKind.CANCEL)
                continue
        if menu.phase is BattleMenuPhase.UNKNOWN:
            _pulse(executor, MacroActionKind.CONFIRM)
            continue
        if menu.phase is BattleMenuPhase.MOVE:
            _pulse(executor, MacroActionKind.CANCEL, frames=120)
            continue
        moves = raw.first_party_moves or ()
        if DIG_MOVE_ID not in moves:
            raise SurgeChapterError("Diglett lead lacks observed Dig move evidence.")
        dig_index = moves.index(DIG_MOVE_ID)
        dig_slot = dig_index + 1
        _navigate_main(executor, reader, 0)
        _pulse(executor, MacroActionKind.CONFIRM, frames=120)
        for _ in range(8):
            selected = reader.read()
            selected_menu = reader.read_battle_menu_state(selected)
            if selected_menu.phase is BattleMenuPhase.MOVE:
                break
            _pulse(
                executor,
                MacroActionKind.CONFIRM
                if selected_menu.phase is BattleMenuPhase.MAIN
                else MacroActionKind.WAIT,
                frames=120,
            )
        else:
            raise SurgeChapterError("Lt. Surge FIGHT menu did not expose moves.")
        for _ in range(6):
            slot = selected_menu.selected_move_slot
            if slot == dig_slot:
                break
            if slot is None:
                raise SurgeChapterError("Lt. Surge move menu lacks a cursor.")
            _pulse(
                executor,
                MacroActionKind.MOVE,
                "down" if slot < dig_slot else "up",
                120,
            )
            selected = reader.read()
            selected_menu = reader.read_battle_menu_state(selected)
        else:
            raise SurgeChapterError("Could not normalize the persisted cursor to Dig.")
        if (
            selected.first_party_moves is None
            or selected.first_party_moves[dig_index] != DIG_MOVE_ID
        ):
            raise SurgeChapterError("Selected Surge move is not Dig (0x5B).")
        before_pp = selected.first_party_pp
        _pulse(executor, MacroActionKind.CONFIRM)
        for _ in range(24):
            after = reader.read()
            if after.battle_state == 0:
                return after, dig_attacks + 1
            if (
                before_pp
                and after.first_party_pp
                and after.first_party_pp[dig_index] == before_pp[dig_index] - 1
            ):
                if tuple(
                    after.first_party_pp[index] for index in range(4) if index != dig_index
                ) != tuple(before_pp[index] for index in range(4) if index != dig_index):
                    raise SurgeChapterError("An off-slot move spent PP against Lt. Surge.")
                dig_attacks += 1
                break
            phase = reader.read_battle_menu_state(after).phase
            if phase in {BattleMenuPhase.MAIN, BattleMenuPhase.MOVE}:
                raise SurgeChapterError("Dig failed closed before its PP proof.")
            _pulse(executor, MacroActionKind.CONFIRM)
        else:
            terminal_menu = reader.read_battle_menu_state(after)
            raise SurgeChapterError(
                "Dig did not reach its bounded PP gate: "
                f"enemy={(after.enemy_species_id, after.enemy_hp)}, "
                f"hp={(after.first_party_hp, after.first_party_max_hp)}, "
                f"status={after.first_party_status!r}, "
                f"pp={after.first_party_pp!r}, "
                f"menu={(terminal_menu.phase, terminal_menu.selected_move_slot)!r}."
            )
    raise SurgeChapterError("Lt. Surge battle exceeded its bounded runtime.")


def _clear_rewards(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SurgeTiming,
) -> RawGameState:
    for _ in range(timing.reward_pulses):
        raw = reader.read()
        mirror = emulator.read_u8(RamAddress.BEAT_GYM_FLAGS)
        if (
            _event(raw, EventFlag.BEAT_LT_SURGE)
            and _event(raw, EventFlag.GOT_TM24)
            and ItemId.TM24_THUNDERBOLT in _bag_ids(emulator)
            and bool((raw.badge_bits or 0) & Badge.THUNDER)
            and bool(mirror & Badge.THUNDER)
            and reader.read_input_readiness().ready
        ):
            return raw
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    raise SurgeChapterError("Lt. Surge reward did not reach its stable semantic gate.")


def _confirm(executor: _CountingExecutor, count: int, frames: int = 180) -> None:
    _confirm_kind(executor, MacroActionKind.CONFIRM, count, frames)


def _confirm_kind(
    executor: _CountingExecutor, kind: MacroActionKind, count: int, frames: int
) -> None:
    for _ in range(count):
        _pulse(executor, kind, frames=frames)


def _pulse(
    executor: _CountingExecutor,
    kind: MacroActionKind,
    value: str | int | None = None,
    frames: int = 180,
) -> None:
    executor.execute(MacroAction(kind, value))
    _wait(executor, frames)


def _wait(executor: _CountingExecutor, frames: int) -> None:
    executor.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))
