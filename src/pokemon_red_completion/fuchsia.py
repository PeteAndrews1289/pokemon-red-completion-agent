"""Qualified Poké Flute, Route 12--15, and Fuchsia arrival chapter."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleRuntimeTiming,
    RequiredMovePolicy,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.celadon import _bag, _money, _party_hp, _party_max_hp, _party_status
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    _flee,
    _open_bag,
    _select_bag_item,
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
from pokemon_red_completion.red_battle_catalog import pokemon_red_move_ref
from pokemon_red_completion.tower import TOWER_FINAL_PARTY

FUCHSIA_CHECKPOINT_COUNT = 14
BITE = 0x2C
BUBBLEBEAM = 0x3D
SNORLAX = 0x84


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "D": "down", "L": "left", "R": "right"}[item] for item in value)


def _reverse(directions: tuple[str, ...]) -> tuple[str, ...]:
    opposite = {"up": "down", "down": "up", "left": "right", "right": "left"}
    return tuple(opposite[item] for item in reversed(directions))


LAVENDER_TO_ROUTE12 = _directions("DDDDDRRRRRRDRDDDDDDDDLDDD")
ROUTE12_FISHER = _directions("DDDDDDDDDDRDDDDDDDDDDDDDDRDDDDRRRDDDDLLLLD")
FISHER_TO_SNORLAX = _directions(
    "DDDLLLLLLDDDDDDRRRDRRDDDRRRRDDDDDDRDDDLLLLLLUUUULLLDDDDDDDRRRRRDDDDD"
)
SNORLAX_TO_LAVENDER = (
    _reverse(FISHER_TO_SNORLAX)
    + _reverse(ROUTE12_FISHER)
    + _reverse(LAVENDER_TO_ROUTE12)
)
LAVENDER_TO_SNORLAX = LAVENDER_TO_ROUTE12 + ROUTE12_FISHER + FISHER_TO_SNORLAX
SNORLAX_OBJECT_TILE = _directions("D")
SNORLAX_TO_ROCKER = _directions("DDRDDDDDDDDRRDR")
ROCKER_TO_ROUTE13 = _directions(
    "RDDDDDLLLLLLLLLLDDDDRRRRRDDDDDDDLLLDDLDDRRRRRDRRRDDDDDLDDDDDDLL"
    "DDDDDDDDDDDDLD"
)
ROUTE13_TRAINER_PAIR = _directions("DLL")
ROUTE13_TO_FUCHSIA = _directions(
    "LLLLLLLLLLLLLDLLLLLLLLLLUURUULLLLLLLLLUURRRRRRRUULLLLLLLLLDDLLLLDD"
    "LLLLLLDDLLLLLLLLLLLLDDDDDDRDDDDDDDDDDDDRDRDDDDDDDDDDDDDDDLLLLLL"
    "LLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLL"
)
FUCHSIA_TO_CENTER = _directions(
    "DLLDLLLLLLLLLLLLDLDDLLLLLLLLLLLLLLLLLLLLLLLDDDDDDDDDDDRRRRRRR"
    "UUUURRRRRRRRRRRU"
)

REQUIRED_EVENTS = (
    EventFlag.BEAT_ROUTE_12_TRAINER_0,
    EventFlag.BEAT_ROUTE_12_TRAINER_3,
    EventFlag.BEAT_ROUTE12_SNORLAX,
    EventFlag.BEAT_ROUTE_13_TRAINER_1,
    EventFlag.BEAT_ROUTE_13_TRAINER_0,
)
OPTIONAL_EVENTS = (
    EventFlag.GOT_TM39,
    EventFlag.BEAT_ROUTE_12_TRAINER_1,
    EventFlag.BEAT_ROUTE_12_TRAINER_2,
    EventFlag.BEAT_ROUTE_12_TRAINER_4,
    EventFlag.BEAT_ROUTE_12_TRAINER_5,
    EventFlag.BEAT_ROUTE_12_TRAINER_6,
    EventFlag.BEAT_ROUTE_13_TRAINER_2,
    EventFlag.BEAT_ROUTE_13_TRAINER_3,
    EventFlag.BEAT_ROUTE_13_TRAINER_4,
    EventFlag.BEAT_ROUTE_13_TRAINER_5,
    EventFlag.BEAT_ROUTE_13_TRAINER_6,
    EventFlag.BEAT_ROUTE_13_TRAINER_7,
    EventFlag.BEAT_ROUTE_13_TRAINER_8,
    EventFlag.BEAT_ROUTE_13_TRAINER_9,
    EventFlag.BEAT_ROUTE_14_TRAINER_0,
    EventFlag.BEAT_ROUTE_14_TRAINER_1,
    EventFlag.BEAT_ROUTE_14_TRAINER_2,
    EventFlag.BEAT_ROUTE_14_TRAINER_3,
    EventFlag.BEAT_ROUTE_14_TRAINER_4,
    EventFlag.BEAT_ROUTE_14_TRAINER_5,
    EventFlag.BEAT_ROUTE_14_TRAINER_6,
    EventFlag.BEAT_ROUTE_14_TRAINER_7,
    EventFlag.BEAT_ROUTE_14_TRAINER_8,
    EventFlag.BEAT_ROUTE_14_TRAINER_9,
    EventFlag.GOT_EXP_ALL,
    EventFlag.BEAT_ROUTE_15_TRAINER_0,
    EventFlag.BEAT_ROUTE_15_TRAINER_1,
    EventFlag.BEAT_ROUTE_15_TRAINER_2,
    EventFlag.BEAT_ROUTE_15_TRAINER_3,
    EventFlag.BEAT_ROUTE_15_TRAINER_4,
    EventFlag.BEAT_ROUTE_15_TRAINER_5,
    EventFlag.BEAT_ROUTE_15_TRAINER_6,
    EventFlag.BEAT_ROUTE_15_TRAINER_7,
    EventFlag.BEAT_ROUTE_15_TRAINER_8,
    EventFlag.BEAT_ROUTE_15_TRAINER_9,
)
OPTIONAL_ITEMS = (
    ItemId.IRON,
    ItemId.EXP_ALL,
    ItemId.SUPER_ROD,
    ItemId.TM16_PAY_DAY,
    ItemId.TM20_RAGE,
)


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class FuchsiaChapterError(RuntimeError):
    """Raised when the qualified Fuchsia route loses semantic evidence."""


@dataclass(frozen=True, slots=True)
class FuchsiaTiming:
    wait_frames: int = 180
    transition_frames: int = 180
    movement_retries: int = 18
    dialogue_pulses: int = 40

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_FUCHSIA_TIMING = FuchsiaTiming()
FUCHSIA_BATTLE_TIMING = BattleRuntimeTiming(
    max_move_menu_transition_pulses=24,
    max_pp_confirmation_pulses=12,
    max_attack_confirmation_pulses=6,
    max_post_attack_transition_pulses=24,
)


@dataclass(frozen=True, slots=True)
class FuchsiaProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[FuchsiaProgress], None]


@dataclass(frozen=True, slots=True)
class FuchsiaCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class FuchsiaBattleEvidence:
    label: str
    opponent: int
    trainer_class: int | None
    trainer_number: int | None
    event: int
    move_id: int
    selected_pp_spent: int
    enemy_species: tuple[int, ...] = ()
    enemy_level: int | None = None


@dataclass(frozen=True, slots=True)
class FuchsiaChapterReport:
    records: tuple[FuchsiaCheckpoint, ...]
    battles: tuple[FuchsiaBattleEvidence, ...]
    final_raw: RawGameState
    required_events: tuple[bool, ...]
    optional_events: tuple[bool, ...]
    optional_items_carried: tuple[bool, ...]
    flute_retained: bool
    snorlax_fight_before: bool
    snorlax_fight_after: bool
    snorlax_object_tile_crossed: bool
    wild_flees: int
    initial_bag: tuple[tuple[int, int], ...]
    final_bag: tuple[tuple[int, int], ...]
    party_hp: tuple[int, int, int]
    party_max_hp: tuple[int, int, int]
    party_status: tuple[int, int, int]
    money_remaining: int
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == FUCHSIA_CHECKPOINT_COUNT
            and tuple(item.selected_pp_spent for item in self.battles) == (5, 4, 2, 4, 5)
            and tuple(item.trainer_number for item in self.battles) == (3, None, 2, 1, 12)
            and self.required_events == (True,) * len(REQUIRED_EVENTS)
            and self.optional_events == (False,) * len(OPTIONAL_EVENTS)
            and self.optional_items_carried == (False,) * len(OPTIONAL_ITEMS)
            and self.flute_retained
            and not self.snorlax_fight_before
            and not self.snorlax_fight_after
            and self.snorlax_object_tile_crossed
            and self.initial_bag == self.final_bag
            and self.final_raw.map_id == MapId.FUCHSIA_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and self.final_raw.party_species_ids == TOWER_FINAL_PARTY
            and self.party_hp == self.party_max_hp
            and self.party_status == (0, 0, 0)
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "reach_fuchsia",
            "battles": [
                {
                    "label": item.label,
                    "opponent": item.opponent,
                    "class": item.trainer_class,
                    "set": item.trainer_number,
                    "event": item.event,
                    "move_id": item.move_id,
                    "selected_pp_spent": item.selected_pp_spent,
                    "enemy_species": list(item.enemy_species),
                    "enemy_level": item.enemy_level,
                }
                for item in self.battles
            ],
            "snorlax": {
                "species": SNORLAX,
                "level": 30,
                "fight_event_before": self.snorlax_fight_before,
                "fight_event_after": self.snorlax_fight_after,
                "beat_event": self.required_events[2],
                "object_tile_crossed": self.snorlax_object_tile_crossed,
                "flute_retained": self.flute_retained,
            },
            "optional_events_false": len(OPTIONAL_EVENTS),
            "optional_items_untouched": len(OPTIONAL_ITEMS),
            "wild_flees": self.wild_flees,
            "party": {
                "species": list(self.final_raw.party_species_ids or ()),
                "hp": list(self.party_hp),
                "max_hp": list(self.party_max_hp),
                "status": list(self.party_status),
            },
            "money_remaining": self.money_remaining,
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


@dataclass(slots=True)
class _RunState:
    wilds: list[object] = field(default_factory=list)
    trainers: list[object] = field(default_factory=list)


def run_fuchsia_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    timing: FuchsiaTiming = DEFAULT_FUCHSIA_TIMING,
    progress: ProgressSink | None = None,
) -> FuchsiaChapterReport:
    start_frames = emulator.frame_count
    actions = _CountingExecutor(executor)
    run = _RunState()
    records: list[FuchsiaCheckpoint] = []
    battles: list[FuchsiaBattleEvidence] = []
    start = reader.read()
    _require(start, MapId.LAVENDER_POKECENTER, (3, 3), "Fuji boundary")
    initial_bag = _bag_tuple(emulator)
    if ItemId.POKE_FLUTE not in _bag(emulator):
        raise FuchsiaChapterError("Fuchsia input lacks the qualified Poké Flute.")
    _checkpoint(records, progress, emulator, start, "fuji_ready", "Poké Flute ready")

    _move(actions, reader, emulator, run, LAVENDER_TO_ROUTE12, timing, "Route 12 entry")
    _require(reader.read(), MapId.ROUTE_12, (9, 0), "Route 12 entry")
    _checkpoint(records, progress, emulator, reader.read(), "route12", "Reached Route 12")
    _move(actions, reader, emulator, run, ROUTE12_FISHER, timing, "Route 12 Fisher")
    battles.append(
        _fight_trainer(
            actions,
            reader,
            emulator,
            timing,
            "Route 12 Fisher",
            (0xD6, 0x0E, 3),
            EventFlag.BEAT_ROUTE_12_TRAINER_0,
            BUBBLEBEAM,
            3,
            5,
            RedBattlePlanId.FUCHSIA_ROUTE_12_FISHER,
            trigger_direction="right",
        )
    )
    _checkpoint(records, progress, emulator, reader.read(), "fisher", "Defeated mandatory Fisher")

    _move(actions, reader, emulator, run, FISHER_TO_SNORLAX, timing, "Route 12 Snorlax")
    snorlax_fight_before = _event(emulator, EventFlag.FIGHT_ROUTE12_SNORLAX)
    battles.append(_fight_snorlax(actions, reader, emulator, timing))
    snorlax_fight_after = _event(emulator, EventFlag.FIGHT_ROUTE12_SNORLAX)
    _checkpoint(records, progress, emulator, reader.read(), "snorlax", "Defeated Route 12 Snorlax")
    _move(
        actions,
        reader,
        emulator,
        run,
        SNORLAX_TO_LAVENDER,
        timing,
        "Lavender recovery return",
    )
    _require(reader.read(), MapId.LAVENDER_POKECENTER, (3, 3), "Lavender recovery nurse")
    _heal_at_nurse(actions, reader, emulator, timing)
    _checkpoint(records, progress, emulator, reader.read(), "recovered", "Healed after Snorlax")
    _move(
        actions,
        reader,
        emulator,
        run,
        LAVENDER_TO_SNORLAX,
        timing,
        "Route 12 recovery return",
    )
    _require(reader.read(), MapId.ROUTE_12, (10, 61), "removed Snorlax north stance")
    _move(actions, reader, emulator, run, SNORLAX_OBJECT_TILE, timing, "removed Snorlax tile")
    snorlax_object_tile_crossed = (
        reader.read().map_id == MapId.ROUTE_12
        and (reader.read().player_x, reader.read().player_y) == (10, 62)
    )
    if not snorlax_object_tile_crossed:
        raise FuchsiaChapterError("Removed Snorlax object tile did not become traversable.")
    _move(actions, reader, emulator, run, SNORLAX_TO_ROCKER, timing, "Route 12 Rocker")
    battles.append(
        _fight_trainer(
            actions,
            reader,
            emulator,
            timing,
            "Route 12 Rocker",
            (0xDC, 0x14, 2),
            EventFlag.BEAT_ROUTE_12_TRAINER_3,
            BITE,
            1,
            2,
            RedBattlePlanId.FUCHSIA_ROUTE_12_ROCKER,
            trigger_direction="down",
        )
    )
    _checkpoint(records, progress, emulator, reader.read(), "rocker", "Defeated mandatory Rocker")

    _move(actions, reader, emulator, run, ROCKER_TO_ROUTE13, timing, "Route 13 east maze")
    battles.append(
        _fight_trainer(
            actions,
            reader,
            emulator,
            timing,
            "Route 13 Bird Keeper1",
            (0xDF, 0x17, 1),
            EventFlag.BEAT_ROUTE_13_TRAINER_0,
            BITE,
            1,
            4,
            RedBattlePlanId.FUCHSIA_ROUTE_13_BIRD_KEEPER_1,
            trigger_direction="up",
        )
    )
    _move(actions, reader, emulator, run, ROUTE13_TRAINER_PAIR, timing, "Route 13 west trainer")
    battles.append(
        _fight_trainer(
            actions,
            reader,
            emulator,
            timing,
            "Route 13 Jr. Trainer F1",
            (0xCE, 0x06, 12),
            EventFlag.BEAT_ROUTE_13_TRAINER_1,
            BITE,
            1,
            5,
            RedBattlePlanId.FUCHSIA_ROUTE_13_JR_TRAINER_F_1,
            interact_direction="up",
        )
    )
    _checkpoint(records, progress, emulator, reader.read(), "route13_pair", "Cleared Route 13 pair")

    _move(actions, reader, emulator, run, ROUTE13_TO_FUCHSIA, timing, "Routes 13 to 15")
    _require(reader.read(), MapId.FUCHSIA_CITY, (39, 16), "Fuchsia east entry")
    for checkpoint_id, label in (
        ("route13_clear", "Route 13 optional trainers bypassed"),
        ("route14_clear", "Route 14 optional trainers bypassed"),
        ("route15_clear", "Route 15 optional trainers and item bypassed"),
        ("fuchsia", "Reached Fuchsia City"),
    ):
        _checkpoint(records, progress, emulator, reader.read(), checkpoint_id, label)

    _move(actions, reader, emulator, run, FUCHSIA_TO_CENTER, timing, "Fuchsia Center")
    _require(reader.read(), MapId.FUCHSIA_POKECENTER, (3, 7), "Fuchsia Center entrance")
    _heal_center(actions, reader, emulator, run, timing)
    final = reader.read()
    _require(final, MapId.FUCHSIA_POKECENTER, (3, 3), "stable Fuchsia boundary")
    for checkpoint_id, label in (
        ("healed", "Healed complete party"),
        ("optionals", "Verified optional routes untouched"),
        ("fuchsia_stable", "Stable Fuchsia boundary"),
    ):
        _checkpoint(records, progress, emulator, final, checkpoint_id, label)

    report = FuchsiaChapterReport(
        tuple(records),
        tuple(battles),
        final,
        tuple(_event(emulator, item) for item in REQUIRED_EVENTS),
        tuple(_event(emulator, item) for item in OPTIONAL_EVENTS),
        tuple(item in _bag(emulator) for item in OPTIONAL_ITEMS),
        ItemId.POKE_FLUTE in _bag(emulator),
        snorlax_fight_before,
        snorlax_fight_after,
        snorlax_object_tile_crossed,
        len(run.wilds),
        initial_bag,
        _bag_tuple(emulator),
        _party_hp(emulator),
        _party_max_hp(emulator),
        _party_status(emulator),
        _money(emulator),
        emulator.frame_count - start_frames,
        actions.actions_executed,
        not emulator.pressed_buttons,
    )
    if not report.passed:
        raise FuchsiaChapterError(f"Fuchsia evidence contract failed: {report.public_dict()!r}.")
    return report


def _fight_trainer(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: FuchsiaTiming,
    label: str,
    identity: tuple[int, int, int],
    event: EventFlag,
    move_id: int,
    move_slot: int,
    exact_spent: int,
    battle_plan_id: str,
    *,
    trigger_direction: str | None = None,
    interact_direction: str | None = None,
    observed_trainer_number: int | None = None,
) -> FuchsiaBattleEvidence:
    direction = trigger_direction or interact_direction
    if direction is not None:
        _pulse(actions, MacroActionKind.MOVE, direction, frames=120)
    if interact_direction is not None:
        actions.execute(MacroAction(MacroActionKind.INTERACT))
    observed_identity = (
        identity[0],
        identity[1],
        identity[2] if observed_trainer_number is None else observed_trainer_number,
    )
    battle = _settle_trainer_identity(
        actions, reader, emulator, timing, label, observed_identity
    )
    before_pp = battle.first_party_pp
    final = run_adaptive_trainer_battle(
        reader,
        actions,
        lambda _: move_slot,
        expected_map=int(battle.map_id or 0),
        intent=BattleIntent(
            "reach_fuchsia",
            battle_plan_id=battle_plan_id,
            required_move_policy=RequiredMovePolicy.EXACT_REQUIRED,
            required_move_ref=pokemon_red_move_ref(move_id),
        ),
        required_move_id=move_id,
        timing=FUCHSIA_BATTLE_TIMING,
        label=label,
        # Periodic CANCEL declines the Gen I optional switch prompt without
        # starving ordinary battle dialogue of CONFIRM pulses.
        unknown_cancel_interval=3,
    )
    if before_pp is None or final.first_party_pp is None:
        raise FuchsiaChapterError(f"{label} lacks PP evidence.")
    spent = (before_pp[move_slot - 1] & 0x3F) - (final.first_party_pp[move_slot - 1] & 0x3F)
    _clear_text(actions, reader, timing)
    if spent != exact_spent or not _event(emulator, event):
        raise FuchsiaChapterError(
            f"{label} evidence mismatch: spent={spent}, event={_event(emulator, event)}."
        )
    return FuchsiaBattleEvidence(
        label,
        identity[0],
        identity[1],
        identity[2],
        int(event),
        move_id,
        spent,
    )


def _settle_trainer_identity(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: FuchsiaTiming,
    label: str,
    identity: tuple[int, int, int],
) -> RawGameState:
    for _ in range(timing.dialogue_pulses):
        raw = reader.read()
        observed = (
            emulator.read_u8(RamAddress.CURRENT_OPPONENT),
            emulator.read_u8(RamAddress.TRAINER_CLASS),
            emulator.read_u8(RamAddress.TRAINER_NUMBER),
        )
        if raw.battle_state == 2 and observed == identity and (raw.enemy_hp or 0) > 0:
            return raw
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    raise FuchsiaChapterError(f"{label} identity did not settle to {identity!r}.")


def _fight_snorlax(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: FuchsiaTiming,
) -> FuchsiaBattleEvidence:
    if _event(emulator, EventFlag.BEAT_ROUTE12_SNORLAX):
        raise FuchsiaChapterError("Route 12 Snorlax was already beaten at chapter start.")
    _open_bag(actions, emulator, DEFAULT_LAVENDER_TIMING)
    _select_bag_item(actions, emulator, ItemId.POKE_FLUTE, DEFAULT_LAVENDER_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(timing.dialogue_pulses):
        raw = reader.read()
        if (
            raw.battle_state == 1
            and raw.enemy_species_id == SNORLAX
            and raw.enemy_level == 30
            and emulator.read_u8(RamAddress.CURRENT_OPPONENT) == SNORLAX
            and (raw.enemy_hp or 0) > 0
        ):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    else:
        raise FuchsiaChapterError("Poké Flute did not wake the level-30 Route 12 Snorlax.")
    before_pp = raw.first_party_pp
    final = _run_wild_defeat(actions, reader, int(MapId.ROUTE_12), timing)
    if before_pp is None or final.first_party_pp is None:
        raise FuchsiaChapterError("Snorlax battle lacks PP evidence.")
    spent = (before_pp[2] & 0x3F) - (final.first_party_pp[2] & 0x3F)
    _clear_text(actions, reader, timing)
    if (
        spent != 4
        or not _event(emulator, EventFlag.BEAT_ROUTE12_SNORLAX)
        or _event(emulator, EventFlag.FIGHT_ROUTE12_SNORLAX)
        or ItemId.POKE_FLUTE not in _bag(emulator)
    ):
        raise FuchsiaChapterError(
            "Snorlax defeat lacks exact PP/event/item evidence: "
            f"spent={spent}, beat={_event(emulator, EventFlag.BEAT_ROUTE12_SNORLAX)}, "
            f"fight={_event(emulator, EventFlag.FIGHT_ROUTE12_SNORLAX)}, "
            f"flute={ItemId.POKE_FLUTE in _bag(emulator)}."
        )
    return FuchsiaBattleEvidence(
        "Route 12 Snorlax",
        SNORLAX,
        None,
        None,
        int(EventFlag.BEAT_ROUTE12_SNORLAX),
        BUBBLEBEAM,
        spent,
        (SNORLAX,),
        30,
    )


def _run_wild_defeat(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    expected_map: int,
    timing: FuchsiaTiming,
) -> RawGameState:
    ready_reads = 0
    for pulse_index in range(360):
        raw = reader.read()
        if raw.map_id != expected_map:
            raise FuchsiaChapterError("Snorlax battle changed map unexpectedly.")
        if raw.battle_state == 0:
            if reader.read_input_readiness().ready:
                ready_reads += 1
                if ready_reads >= 2:
                    return raw
                _wait(actions, 1)
            else:
                ready_reads = 0
                _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
            continue
        if raw.battle_state != 1 or (raw.first_party_hp or 0) <= 0:
            raise FuchsiaChapterError("Snorlax battle lost the qualified lead.")
        menu = reader.read_battle_menu_state(raw)
        if menu.phase is BattleMenuPhase.UNKNOWN:
            _pulse(
                actions,
                MacroActionKind.CANCEL if pulse_index % 5 == 4 else MacroActionKind.CONFIRM,
                frames=timing.wait_frames,
            )
            continue
        if menu.phase is BattleMenuPhase.MAIN:
            command = menu.selected_main_command
            if command == 0:
                _pulse(actions, MacroActionKind.CONFIRM, frames=120)
            else:
                direction = {1: "up", 2: "left", 3: "up"}.get(command)
                if direction is None:
                    raise FuchsiaChapterError("Snorlax exposed an invalid battle command.")
                _pulse(actions, MacroActionKind.MOVE, direction, frames=120)
            continue
        slot = menu.selected_move_slot
        if slot == 3:
            _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
        elif slot is None:
            raise FuchsiaChapterError("Snorlax exposed an invalid move cursor.")
        else:
            _pulse(
                actions,
                MacroActionKind.MOVE,
                "down" if slot < 3 else "up",
                frames=120,
            )
    raise FuchsiaChapterError("Snorlax battle exceeded its bounded runtime.")


def _move(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    directions: Iterable[str],
    timing: FuchsiaTiming,
    label: str,
) -> RawGameState:
    state = reader.read()
    for step, direction in enumerate(directions, 1):
        before = (state.map_id, state.player_x, state.player_y)
        for _attempt in range(timing.movement_retries):
            # These outdoor maze paths were qualified at a full settled step;
            # shorter waits can observe the previous direction still in flight
            # and falsely credit the next input.
            _pulse(actions, MacroActionKind.MOVE, direction, frames=240)
            state = reader.read()
            if state.battle_state == 1:
                _flee(
                    actions,
                    reader,
                    emulator,
                    run,
                    DEFAULT_LAVENDER_TIMING,
                    unknown_with_cancel=True,
                )
                state = reader.read()
            if state.battle_state == 2:
                return state
            if (state.map_id, state.player_x, state.player_y) != before:
                break
            if not reader.read_input_readiness().ready:
                _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
                state = reader.read()
        else:
            raise FuchsiaChapterError(
                f"{label} blocked at step {step}: {direction}; "
                f"map={state.map_id!r}, coordinate={(state.player_x, state.player_y)!r}."
            )
        if state.party_species_ids != TOWER_FINAL_PARTY or (state.first_party_hp or 0) <= 0:
            raise FuchsiaChapterError(
                f"{label} changed the protected party: {state.party_species_ids!r}, "
                f"lead_hp={state.first_party_hp!r}."
            )
    _wait(actions, timing.transition_frames)
    return reader.read()


def _heal_center(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    timing: FuchsiaTiming,
) -> None:
    _move(actions, reader, emulator, run, ("up",) * 4, timing, "Fuchsia nurse")
    for _ in range(20):
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
        if _party_hp(emulator) == _party_max_hp(emulator) and _party_status(emulator) == (0, 0, 0):
            _clear_text(actions, reader, timing)
            return
    raise FuchsiaChapterError("Fuchsia Center did not heal the complete party.")


def _heal_at_nurse(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: FuchsiaTiming,
) -> None:
    for _ in range(20):
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
        if _party_hp(emulator) == _party_max_hp(emulator) and _party_status(emulator) == (0, 0, 0):
            _clear_text(actions, reader, timing)
            return
    raise FuchsiaChapterError("Lavender recovery did not heal the complete party.")


def _clear_text(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: FuchsiaTiming,
) -> None:
    for _ in range(6):
        _pulse(actions, MacroActionKind.CANCEL, frames=timing.wait_frames)
    if not reader.read_input_readiness().ready:
        raise FuchsiaChapterError("Dialogue did not return input authority.")


def _event(emulator: EmulatorState, event: EventFlag) -> bool:
    value = int(event)
    return bool(emulator.read_u8(int(RamAddress.EVENT_FLAGS) + value // 8) & (1 << (value % 8)))


def _bag_tuple(emulator: EmulatorState) -> tuple[tuple[int, int], ...]:
    return tuple(
        sorted((int(item), quantity) for item, quantity in Counter(_bag(emulator)).items())
    )


def _require(
    raw: RawGameState,
    map_id: int,
    coordinate: tuple[int, int],
    label: str,
) -> None:
    if (
        raw.map_id != map_id
        or (raw.player_x, raw.player_y) != coordinate
        or raw.battle_state != 0
        or raw.party_species_ids != TOWER_FINAL_PARTY
    ):
        raise FuchsiaChapterError(
            f"{label} missed gate: map={raw.map_id!r}, "
            f"coordinate={(raw.player_x, raw.player_y)!r}, battle={raw.battle_state!r}."
        )


def _checkpoint(
    records: list[FuchsiaCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(FuchsiaCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            FuchsiaProgress(
                checkpoint_id,
                label,
                len(records),
                FUCHSIA_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )


def _pulse(
    actions: _CountingExecutor,
    kind: MacroActionKind,
    value: str | int | None = None,
    *,
    frames: int = 180,
) -> None:
    actions.execute(MacroAction(kind, value))
    _wait(actions, frames)


def _wait(actions: _CountingExecutor, frames: int) -> None:
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))
