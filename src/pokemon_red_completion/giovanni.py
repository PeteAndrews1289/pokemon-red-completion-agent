"""Qualified Viridian Gym and Giovanni chapter.

The map routes, spinner behavior, trainer identities, parties, and reward
events are pinned to pret/pokered commit
``1e96034092686d006e863cace09e87273051a3d8``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    RequiredMovePolicy,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.blaine import (
    CENTER_TO_MART as CINNABAR_CENTER_TO_MART,
)
from pokemon_red_completion.blaine import MANSION_TRAINING_POLICY, _select_cursor
from pokemon_red_completion.celadon import (
    _bag,
    _money,
    _party_hp,
    _party_max_hp,
    _party_status,
)
from pokemon_red_completion.executor import ChapterExecutor, CountingExecutor
from pokemon_red_completion.hideout import DEFAULT_HIDEOUT_TIMING
from pokemon_red_completion.observation import (
    Badge,
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.red_battle_catalog import pokemon_red_move_ref
from pokemon_red_completion.tower import party_core_intact

GIOVANNI_CHECKPOINT_COUNT = 8
GIOVANNI_OPPONENT = 0xE5
GIOVANNI_TRAINER_CLASS = 0xE5
GIOVANNI_TRAINER_SET = 3
GIOVANNI_PARTY = (
    (0x12, 45),
    (0x76, 42),
    (0x10, 44),
    (0x07, 45),
    (0x01, 50),
)
SURF_MOVE_ID = 0x39
ICE_BEAM_MOVE_ID = 0x3A
HYDRO_PUMP_MOVE_ID = 0x38
GYM_TRAINER_EVENTS = tuple(
    EventFlag(int(EventFlag.BEAT_VIRIDIAN_GYM_TRAINER_0) + offset)
    for offset in range(8)
)
REQUIRED_TRAINER_EVENTS = (
    True,
    True,
    True,
    False,
    True,
    True,
    False,
    True,
)


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "R": "right", "D": "down", "L": "left"}[item] for item in value)


FLY_ARRIVAL_TO_MART = _directions("RRRUUUUUURRRU")
MART_EXIT_TO_GYM = _directions("LLUUUULLLLLLLLUUUUUUUUUUUURRRRRURRRRRRRRRRDDDDDLLU")
GYM_ENTRY_TO_HIKER = _directions("URUUUURURU")
HIKER_TO_BLACKBELT = _directions("DRDLLLLULL")
BLACKBELT_TO_COOLTRAINER_9 = ("up",)
COOLTRAINER_9_TO_TAMER = ("left", "left")
TAMER_TO_COOLTRAINER_10 = _directions("RUUURRRRUU")
COOLTRAINER_10_TO_COOLTRAINER_1 = _directions("ULLDLLLUUULLLDDLD")
GYM_GATE_TO_EXIT = _directions("RUURRRRRDDLDDDDD")
CENTER_EXIT_TO_GYM = _directions(
    "LLUUUUUUUULLUUUUUUUUUUUUUURRRRRURRRRRRRRRRDDDDDLLU"
)
GYM_REENTRY_TO_GIOVANNI = _directions("ULLUUUUUUULUURRUUULLLDLLUUULLLDDLLLUULL")
GIOVANNI_TO_GYM_EXIT = _directions("RRDDRRRUURRRRRDDLDDDDD")
GYM_EXIT_TO_CENTER = _directions("DDDLLLLLLLLLLLLLDDDDDDRRDDDDDDDDRRU")


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class GiovanniChapterError(RuntimeError):
    """Raised when the Viridian Gym evidence contract fails."""


@dataclass(frozen=True, slots=True)
class GiovanniProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[GiovanniProgress], None]


@dataclass(frozen=True, slots=True)
class GiovanniCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class GiovanniTurn:
    enemy_species: int
    enemy_level: int
    enemy_hp: int
    lead_hp: int
    lead_status: int
    pp: tuple[int, int, int, int]
    move_slot: int


@dataclass(frozen=True, slots=True)
class TrainerReceipt:
    label: str
    identity: tuple[int, int, int]
    expected_party: tuple[tuple[int, int], ...]
    turns: tuple[GiovanniTurn, ...]

    @property
    def passed(self) -> bool:
        return (
            _encounter_party(self.turns) == self.expected_party
            and all(turn.lead_hp > 0 and turn.lead_status == 0 for turn in self.turns)
        )


REQUIRED_TRAINERS = (
    ("hiker_set_8", (0xE0, 0xE0, 8), ((0x29, 38), (0x6A, 38), (0x29, 38)), 2),
    ("blackbelt_set_6", (0xE0, 0xE0, 6), ((0x6A, 40), (0x29, 40)), 2),
    ("cooltrainer_set_9", (0xE7, 0xE7, 9), ((0x61, 39), (0x76, 39)), 3),
    ("tamer_set_3", (0xDE, 0xDE, 3), ((0x12, 43),), 3),
    ("cooltrainer_set_10", (0xE7, 0xE7, 10), ((0x12, 43),), 3),
    ("cooltrainer_set_1", (0xE7, 0xE7, 1), ((0xA7, 39), (0x07, 39)), 3),
)


@dataclass(frozen=True, slots=True)
class GiovanniChapterReport:
    records: tuple[GiovanniCheckpoint, ...]
    final_raw: RawGameState
    initial_badges: int
    trainer_events_before: tuple[bool, ...]
    trainer_events_before_giovanni: tuple[bool, ...]
    trainer_events_after: tuple[bool, ...]
    trainer_receipts: tuple[TrainerReceipt, ...]
    identity: tuple[int, int, int]
    turns: tuple[GiovanniTurn, ...]
    tm46_sold: bool
    tm27_quantity: int
    got_tm27: bool
    beat_giovanni: bool
    earth_badge: bool
    earth_badge_mirror: bool
    route22_rival_visible: bool
    route22_rival_wants_battle: bool
    initial_money: int
    money_remaining: int
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        expected_receipts = tuple(item[:3] for item in REQUIRED_TRAINERS)
        actual_receipts = tuple(
            (receipt.label, receipt.identity, receipt.expected_party)
            for receipt in self.trainer_receipts
        )
        return (
            len(self.records) == GIOVANNI_CHECKPOINT_COUNT
            and self.initial_badges == 0x7F
            and self.trainer_events_before == (False,) * 8
            and self.trainer_events_before_giovanni == REQUIRED_TRAINER_EVENTS
            and self.trainer_events_after == (True,) * 8
            and actual_receipts == expected_receipts
            and all(receipt.passed for receipt in self.trainer_receipts)
            and all(
                receipt.turns
                and all(
                    turn.move_slot == REQUIRED_TRAINERS[index][3]
                    for turn in receipt.turns
                )
                for index, receipt in enumerate(self.trainer_receipts)
            )
            and self.identity
            == (GIOVANNI_OPPONENT, GIOVANNI_TRAINER_CLASS, GIOVANNI_TRAINER_SET)
            and _encounter_party(self.turns) == GIOVANNI_PARTY
            and self.turns
            and all(turn.move_slot == 4 for turn in self.turns)
            and all(turn.lead_hp > 0 and turn.lead_status == 0 for turn in self.turns)
            and self.tm46_sold
            and self.tm27_quantity == 1
            and self.got_tm27
            and self.beat_giovanni
            and self.earth_badge
            and self.earth_badge_mirror
            and self.route22_rival_visible
            and self.route22_rival_wants_battle
            and self.money_remaining == self.initial_money + 14_855
            and self.final_raw.map_id == MapId.VIRIDIAN_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and party_core_intact(self.final_raw.party_species_ids)
            and (self.final_raw.first_party_level or 0)
            >= MANSION_TRAINING_POLICY.target_level
            and self.final_raw.first_party_moves
            == (HYDRO_PUMP_MOVE_ID, 0x46, ICE_BEAM_MOVE_ID, SURF_MOVE_ID)
            and self.final_raw.first_party_pp == (5, 15, 10, 15)
            and self.party_hp == self.party_max_hp
            and all(hp > 0 for hp in self.party_hp)
            and self.final_raw.first_party_hp == self.party_hp[0]
            and self.final_raw.first_party_max_hp == self.party_max_hp[0]
            and all(status == 0 for status in self.party_status)
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objectives": ["defeat_giovanni"],
            "inventory": {
                "tm46_sold": self.tm46_sold,
                "tm27": self.tm27_quantity,
                "money": [self.initial_money, self.money_remaining],
            },
            "gym": {
                "trainers_before": list(self.trainer_events_before),
                "trainers_before_giovanni": list(self.trainer_events_before_giovanni),
                "trainers_after": list(self.trainer_events_after),
                "required_battles": [
                    {
                        "label": receipt.label,
                        "identity": list(receipt.identity),
                        "party": [list(member) for member in receipt.expected_party],
                        "move_slots": [turn.move_slot for turn in receipt.turns],
                    }
                    for receipt in self.trainer_receipts
                ],
            },
            "giovanni": {
                "identity": list(self.identity),
                "party": [list(member) for member in GIOVANNI_PARTY],
                "move_slots": [turn.move_slot for turn in self.turns],
            },
            "rewards": {
                "tm27": self.tm27_quantity,
                "tm27_event": self.got_tm27,
                "giovanni_event": self.beat_giovanni,
                "earth_badge": self.earth_badge,
                "earth_badge_mirror": self.earth_badge_mirror,
                "route22_rival_visible": self.route22_rival_visible,
                "route22_rival_wants_battle": self.route22_rival_wants_battle,
            },
            "terminal": {
                "map": int(self.final_raw.map_id),
                "position": [self.final_raw.player_x, self.final_raw.player_y],
                "party_hp": list(self.party_hp),
                "party_max_hp": list(self.party_max_hp),
                "party_status": list(self.party_status),
            },
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


def run_giovanni_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    progress: ProgressSink | None = None,
) -> GiovanniChapterReport:
    start_frames = emulator.frame_count
    actions = CountingExecutor(executor)
    records: list[GiovanniCheckpoint] = []
    initial = reader.read()
    _require(initial, MapId.CINNABAR_POKECENTER, (3, 3), "post-Blaine boundary")
    initial_bag = _bag(emulator)
    initial_money = _money(emulator)
    trainer_before = _events(emulator, GYM_TRAINER_EVENTS)
    if (
        initial.badge_bits != 0x7F
        or _event(emulator, EventFlag.GOT_TM27)
        or _event(emulator, EventFlag.BEAT_VIRIDIAN_GYM_GIOVANNI)
        or trainer_before != (False,) * 8
    ):
        raise GiovanniChapterError("Viridian Gym input boundary is not pristine.")
    if (
        len(initial_bag) != 20
        or initial_bag.get(ItemId.TM46_PSYWAVE, 0) != 1
        or initial_bag.get(ItemId.TM38_FIRE_BLAST, 0) != 1
    ):
        raise GiovanniChapterError("Expected full seven-badge inventory was not present.")
    _checkpoint(records, progress, emulator, initial, "giovanni_ready", "Viridian route ready")

    _move(actions, reader, CINNABAR_CENTER_TO_MART, "Cinnabar Mart")
    _require(reader.read(), MapId.CINNABAR_MART, (3, 7), "Cinnabar Mart entry")
    _move(actions, reader, ("up", "up", "left"), "Cinnabar clerk")
    _pulse(actions, MacroActionKind.MOVE, "left", 120)
    _sell_current_bag_item(actions, emulator, ItemId.TM46_PSYWAVE)
    _close(actions, reader)
    if _bag(emulator).get(ItemId.TM46_PSYWAVE, 0) or len(_bag(emulator)) != 19:
        raise GiovanniChapterError("TM46 sale did not free exactly one bag slot.")
    _move(actions, reader, ("right", "down", "down", "down"), "Cinnabar Mart exit")
    _require(reader.read(), MapId.CINNABAR_ISLAND, (15, 12), "Cinnabar Mart exterior")
    _field_fly_to_viridian(actions, reader, emulator)
    _require(reader.read(), MapId.VIRIDIAN_CITY, (23, 26), "Viridian Fly arrival")
    _checkpoint(records, progress, emulator, reader.read(), "viridian_arrived", "Flew to Viridian")
    _checkpoint(records, progress, emulator, reader.read(), "tm_slot_freed", "Freed TM27 slot")

    _move(actions, reader, CENTER_EXIT_TO_GYM, "Viridian Gym")
    _require(reader.read(), MapId.VIRIDIAN_GYM, (16, 17), "Viridian Gym entry")
    _checkpoint(records, progress, emulator, reader.read(), "viridian_gym_entered", "Entered Gym")

    receipts: list[TrainerReceipt] = []
    _move(actions, reader, GYM_ENTRY_TO_HIKER, "Hiker approach")
    _require(reader.read(), MapId.VIRIDIAN_GYM, (11, 1), "Hiker approach")
    _face_and_interact(actions, "left")
    receipts.append(
        _finish_trainer(
            actions,
            reader,
            emulator,
            REQUIRED_TRAINERS[0],
            RedBattlePlanId.GIOVANNI_HIKER_SET_8,
        )
    )

    _move(actions, reader, HIKER_TO_BLACKBELT, "Blackbelt approach")
    _require(reader.read(), MapId.VIRIDIAN_GYM, (12, 11), "Blackbelt approach")
    _pulse(actions, MacroActionKind.INTERACT)
    receipts.append(
        _finish_trainer(
            actions,
            reader,
            emulator,
            REQUIRED_TRAINERS[1],
            RedBattlePlanId.GIOVANNI_BLACKBELT_SET_6,
        )
    )

    _trigger_line_battle(actions, reader, BLACKBELT_TO_COOLTRAINER_9, "Cooltrainer set 9")
    receipts.append(
        _finish_trainer(
            actions,
            reader,
            emulator,
            REQUIRED_TRAINERS[2],
            RedBattlePlanId.GIOVANNI_COOLTRAINER_SET_9,
        )
    )

    _move(actions, reader, COOLTRAINER_9_TO_TAMER[:-1], "Tamer approach")
    _trigger_line_battle(actions, reader, COOLTRAINER_9_TO_TAMER[-1:], "Tamer set 3")
    receipts.append(
        _finish_trainer(
            actions,
            reader,
            emulator,
            REQUIRED_TRAINERS[3],
            RedBattlePlanId.GIOVANNI_TAMER_SET_3,
        )
    )

    _move(actions, reader, TAMER_TO_COOLTRAINER_10[:-1], "Cooltrainer set 10 approach")
    _trigger_line_battle(
        actions,
        reader,
        TAMER_TO_COOLTRAINER_10[-1:],
        "Cooltrainer set 10",
    )
    receipts.append(
        _finish_trainer(
            actions,
            reader,
            emulator,
            REQUIRED_TRAINERS[4],
            RedBattlePlanId.GIOVANNI_COOLTRAINER_SET_10,
        )
    )

    _move(actions, reader, COOLTRAINER_10_TO_COOLTRAINER_1[:-1], "Gym gate approach")
    _require(reader.read(), MapId.VIRIDIAN_GYM, (6, 4), "Gym gate approach")
    _face_and_interact(actions, "down")
    receipts.append(
        _finish_trainer(
            actions,
            reader,
            emulator,
            REQUIRED_TRAINERS[5],
            RedBattlePlanId.GIOVANNI_COOLTRAINER_SET_1,
        )
    )

    trainer_before_giovanni = _events(emulator, GYM_TRAINER_EVENTS)
    if trainer_before_giovanni != REQUIRED_TRAINER_EVENTS:
        raise GiovanniChapterError(
            f"Qualified Gym battle set changed: {trainer_before_giovanni!r}."
        )
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "viridian_trainers_cleared",
        "Cleared required Gym trainers",
    )

    _move(actions, reader, GYM_GATE_TO_EXIT, "pre-Giovanni Gym exit")
    _require(reader.read(), MapId.VIRIDIAN_CITY, (32, 8), "pre-Giovanni Gym exterior")
    _move(actions, reader, GYM_EXIT_TO_CENTER, "pre-Giovanni Viridian Center")
    _require(
        reader.read(),
        MapId.VIRIDIAN_POKECENTER,
        (3, 7),
        "pre-Giovanni Center entry",
    )
    _move(actions, reader, ("up",) * 4, "pre-Giovanni nurse")
    _heal(actions, reader, emulator)
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "giovanni_recovered",
        "Restored party before Giovanni",
    )
    _move(actions, reader, ("down",) * 5, "Viridian Center return exit")
    _move(actions, reader, CENTER_EXIT_TO_GYM, "Viridian Gym return")
    _require(reader.read(), MapId.VIRIDIAN_GYM, (16, 17), "Viridian Gym return")
    _move(actions, reader, GYM_REENTRY_TO_GIOVANNI, "Giovanni approach")
    _require(reader.read(), MapId.VIRIDIAN_GYM, (2, 2), "Giovanni approach")
    _face_and_interact(actions, "up")
    _await_trainer_battle(actions, reader, "Giovanni")
    identity = _identity(emulator)
    if identity != (GIOVANNI_OPPONENT, GIOVANNI_TRAINER_CLASS, GIOVANNI_TRAINER_SET):
        raise GiovanniChapterError(f"Unexpected Giovanni identity: {identity!r}.")
    turns = _run_policy_battle(
        actions,
        reader,
        4,
        "Giovanni",
        RedBattlePlanId.GIOVANNI_LEADER,
    )
    if _encounter_party(turns) != GIOVANNI_PARTY:
        raise GiovanniChapterError(f"Giovanni party or Surf policy changed: {turns!r}.")
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "giovanni_defeated",
        "Defeated Giovanni",
    )

    if (
        not _event(emulator, EventFlag.GOT_TM27)
        or not _event(emulator, EventFlag.BEAT_VIRIDIAN_GYM_GIOVANNI)
        or _bag(emulator).get(ItemId.TM27_FISSURE, 0) != 1
        or reader.read().badge_bits != 0xFF
        or emulator.read_u8(RamAddress.BEAT_GYM_FLAGS) != 0xFF
    ):
        raise GiovanniChapterError("Giovanni reward sequence did not settle.")

    _move(actions, reader, GIOVANNI_TO_GYM_EXIT, "Viridian Gym exit")
    _require(reader.read(), MapId.VIRIDIAN_CITY, (32, 8), "Viridian Gym exterior")
    _move(actions, reader, GYM_EXIT_TO_CENTER, "Viridian Center")
    _require(reader.read(), MapId.VIRIDIAN_POKECENTER, (3, 7), "Viridian Center entry")
    _move(actions, reader, ("up",) * 4, "Viridian nurse")
    _heal(actions, reader, emulator)
    final = reader.read()
    _require(final, MapId.VIRIDIAN_POKECENTER, (3, 3), "eight-badge terminal")
    _checkpoint(
        records,
        progress,
        emulator,
        final,
        "giovanni_terminal",
        "Eight-badge terminal ready",
    )

    report = GiovanniChapterReport(
        records=tuple(records),
        final_raw=final,
        initial_badges=initial.badge_bits or 0,
        trainer_events_before=trainer_before,
        trainer_events_before_giovanni=trainer_before_giovanni,
        trainer_events_after=_events(emulator, GYM_TRAINER_EVENTS),
        trainer_receipts=tuple(receipts),
        identity=identity,
        turns=turns,
        tm46_sold=ItemId.TM46_PSYWAVE not in _bag(emulator),
        tm27_quantity=_bag(emulator).get(ItemId.TM27_FISSURE, 0),
        got_tm27=_event(emulator, EventFlag.GOT_TM27),
        beat_giovanni=_event(emulator, EventFlag.BEAT_VIRIDIAN_GYM_GIOVANNI),
        earth_badge=bool(final.badge_bits and final.badge_bits & Badge.EARTH),
        earth_badge_mirror=bool(emulator.read_u8(RamAddress.BEAT_GYM_FLAGS) & Badge.EARTH),
        route22_rival_visible=_event(emulator, EventFlag.SECOND_ROUTE_22_RIVAL_BATTLE),
        route22_rival_wants_battle=_event(emulator, EventFlag.ROUTE_22_RIVAL_WANTS_BATTLE),
        initial_money=initial_money,
        money_remaining=_money(emulator),
        party_hp=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise GiovanniChapterError(f"Giovanni terminal evidence failed: {report!r}.")
    return report


def _field_fly_to_viridian(actions, reader, emulator) -> None:
    _pulse(actions, MacroActionKind.OPEN_MENU)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _pulse(actions, MacroActionKind.MOVE, "up", 120)
    _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    for _ in range(12):
        raw = reader.read()
        if raw.map_id == MapId.VIRIDIAN_CITY:
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    else:
        raise GiovanniChapterError("Fly did not reach Viridian.")
    for _ in range(8):
        if reader.read_input_readiness().ready:
            return
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    raise GiovanniChapterError("Viridian Fly arrival did not restore input.")


def _sell_current_bag_item(actions, emulator, item: ItemId) -> None:
    if _bag(emulator).get(item, 0) != 1:
        raise GiovanniChapterError(f"Expected one {item.name} to sell.")
    _pulse(actions, MacroActionKind.INTERACT)
    _pulse(actions, MacroActionKind.MOVE, "down")
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 1:
        raise GiovanniChapterError("Viridian shop did not select SELL.")
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(24):
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        if absolute < len(_bag(emulator)) and tuple(_bag(emulator))[absolute] == item:
            break
        _pulse(actions, MacroActionKind.MOVE, "down", 120)
    else:
        raise GiovanniChapterError(f"Sell list could not select {item.name}.")
    for _ in range(12):
        _pulse(actions, MacroActionKind.CONFIRM)
        if item not in _bag(emulator):
            return
    raise GiovanniChapterError(f"Sale of {item.name} did not settle.")


def _finish_trainer(
    actions,
    reader,
    emulator,
    expected: tuple[
        str,
        tuple[int, int, int],
        tuple[tuple[int, int], ...],
        int,
    ],
    battle_plan_id: str,
) -> TrainerReceipt:
    label, expected_identity, expected_party, move_slot = expected
    _await_trainer_battle(actions, reader, label)
    identity = _identity(emulator)
    if identity != expected_identity:
        raise GiovanniChapterError(
            f"{label} identity changed: expected {expected_identity!r}, got {identity!r}."
        )
    turns = _run_policy_battle(actions, reader, move_slot, label, battle_plan_id)
    receipt = TrainerReceipt(label, identity, expected_party, turns)
    if not receipt.passed:
        raise GiovanniChapterError(f"{label} party or move policy changed: {turns!r}.")
    return receipt


def _run_policy_battle(
    actions,
    reader,
    move_slot: int,
    label: str,
    battle_plan_id: str,
) -> tuple[GiovanniTurn, ...]:
    turns: list[GiovanniTurn] = []

    def record_turn(raw: RawGameState, selected_slot: int) -> None:
        turns.append(
            GiovanniTurn(
                raw.enemy_species_id or 0,
                raw.enemy_level or 0,
                raw.enemy_hp or 0,
                raw.first_party_hp or 0,
                raw.first_party_status or 0,
                raw.first_party_pp or (0, 0, 0, 0),
                selected_slot,
            )
        )

    run_adaptive_trainer_battle(
        reader,
        actions,
        lambda _raw: move_slot,
        expected_map=MapId.VIRIDIAN_GYM,
        intent=BattleIntent(
            "defeat_giovanni",
            battle_plan_id=battle_plan_id,
            required_move_policy=RequiredMovePolicy.EXACT_REQUIRED,
            required_move_ref=pokemon_red_move_ref(
                {2: 0x46, 3: ICE_BEAM_MOVE_ID, 4: SURF_MOVE_ID}[move_slot]
            ),
        ),
        required_move_id={2: 0x46, 3: ICE_BEAM_MOVE_ID, 4: SURF_MOVE_ID}[move_slot],
        label=label,
        move_decision_sink=record_turn,
    )
    return tuple(turns)


def _trigger_line_battle(actions, reader, route: Iterable[str], label: str) -> None:
    route = tuple(route)
    if not route:
        raise ValueError("line-battle route cannot be empty")
    for direction in route:
        _pulse(actions, MacroActionKind.MOVE, direction, 240)
    _await_trainer_battle(actions, reader, label)


def _await_trainer_battle(actions, reader, label: str) -> None:
    for _ in range(40):
        if reader.read().battle_state == 2:
            return
        _pulse(actions, MacroActionKind.CONFIRM)
    raise GiovanniChapterError(f"{label} battle did not start inside its bound.")


def _heal(actions, reader, emulator) -> None:
    for _ in range(20):
        _pulse(actions, MacroActionKind.CONFIRM)
        if (
            _party_hp(emulator) == _party_max_hp(emulator)
            and all(status == 0 for status in _party_status(emulator))
            and reader.read().first_party_pp == (5, 15, 10, 15)
        ):
            break
    _close(actions, reader)


def _move(actions, reader, route: Iterable[str], label: str) -> None:
    route = tuple(route)
    for index, direction in enumerate(route, 1):
        before = reader.read()
        for _ in range(8):
            _pulse(actions, MacroActionKind.MOVE, direction, 240)
            after = reader.read()
            if after.battle_state:
                raise GiovanniChapterError(f"{label} entered battle at step {index}.")
            if (after.map_id, after.player_x, after.player_y) != (
                before.map_id,
                before.player_x,
                before.player_y,
            ):
                break
        else:
            raise GiovanniChapterError(f"{label} blocked at step {index}/{len(route)}.")
        for _ in range(32):
            if reader.read_input_readiness().ready:
                break
            _pulse(actions, MacroActionKind.WAIT, frames=60)
        else:
            raise GiovanniChapterError(f"{label} did not settle at step {index}/{len(route)}.")


def _face_and_interact(actions, direction: str) -> None:
    _pulse(actions, MacroActionKind.MOVE, direction, 120)
    _pulse(actions, MacroActionKind.INTERACT)


def _close(actions, reader) -> None:
    for _ in range(6):
        _pulse(actions, MacroActionKind.CANCEL)
    if not reader.read_input_readiness().ready:
        raise GiovanniChapterError("Menus did not restore field input.")


def _pulse(
    actions,
    kind: MacroActionKind,
    value: str | None = None,
    frames: int = 180,
) -> None:
    actions.execute(MacroAction(kind, value))
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))


def _identity(emulator) -> tuple[int, int, int]:
    return (
        emulator.read_u8(RamAddress.CURRENT_OPPONENT),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_CLASS),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_SET),
    )


def _event(emulator, event: EventFlag) -> bool:
    index = int(event)
    value = emulator.read_u8(int(RamAddress.EVENT_FLAGS) + index // 8)
    return bool(value & (1 << (index % 8)))


def _events(emulator, events: Iterable[EventFlag]) -> tuple[bool, ...]:
    return tuple(_event(emulator, event) for event in events)


def _encounter_party(turns: Iterable[GiovanniTurn]) -> tuple[tuple[int, int], ...]:
    party: list[tuple[int, int]] = []
    for turn in turns:
        member = (turn.enemy_species, turn.enemy_level)
        if not party or member != party[-1]:
            party.append(member)
    return tuple(party)


def _checkpoint(
    records: list[GiovanniCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(GiovanniCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            GiovanniProgress(
                checkpoint_id,
                label,
                len(records),
                GIOVANNI_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )


def _require(
    raw: RawGameState,
    map_id: MapId,
    coordinate: tuple[int, int],
    label: str,
) -> None:
    if raw.map_id != map_id or (raw.player_x, raw.player_y) != coordinate:
        raise GiovanniChapterError(
            f"{label} expected map {int(map_id):#04x} at {coordinate}, got "
            f"{raw.map_id!r} at {(raw.player_x, raw.player_y)}."
        )
