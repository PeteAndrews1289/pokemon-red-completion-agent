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
from pokemon_red_completion.capture import (
    CaptureDirective,
    CaptureObservation,
    CapturePolicy,
    plan_capture,
)
from pokemon_red_completion.celadon import _bag, _money, _party_hp, _party_max_hp, _party_status
from pokemon_red_completion.lavender import (
    CENTER_EXIT,
    DEFAULT_LAVENDER_TIMING,
    LAVENDER_CENTER_TO_MART,
    LAVENDER_MART_TO_CENTER,
    LAVENDER_MART_TO_CLERK,
    LAVENDER_MART_TO_TOWN,
    LavenderChapterError,
    _buy_mart_item,
    _close_menus,
    _flee,
    _open_bag,
    _select_bag_item,
    _sell_mart_item_stack,
    _sell_single_mart_item,
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
from pokemon_red_completion.red_party import PokemonRedPartyReader
from pokemon_red_completion.tower import party_core_intact

FUCHSIA_CHECKPOINT_COUNT = 14
BITE = 0x2C
BUBBLEBEAM = 0x3D
SNORLAX = 0x84
SNORLAX_BUBBLEBEAM_PP_BOUND = (1, 20)
SNORLAX_RUNTIME_PULSE_BOUND = 720
SNORLAX_GREAT_BALL_RESERVE = 32
SNORLAX_MIN_GREAT_BALL_RESERVE = 29
SNORLAX_SUPER_POTION_RESERVE = 2
SNORLAX_TM34_SALE_PROCEEDS = 1_000
SNORLAX_POTION_SALE_PROCEEDS = 150
SNORLAX_ANTIDOTE_SALE_PROCEEDS = 50
SNORLAX_POKE_BALL_SALE_PROCEEDS = 100
SNORLAX_SUPER_POTION_SALE_PROCEEDS = 350
SNORLAX_POKE_BALL_RESERVE = 1
ROUTE13_BIRD_KEEPER_BITE_PP_BOUND = 15
GREAT_BALL_PRICE = 600
SUPER_POTION_PRICE = 700
SNORLAX_CAPTURE_POLICY = CapturePolicy(
    # Snorlax can heal itself with Rest.  A high threshold permits one safe
    # weakening hit from full health but never chases that healing into a
    # low-health knockout, including after a critical hit changes damage.
    throw_at_or_below_hp_ratio=0.90,
    prefer_status_first=False,
    # A static one-time encounter deserves a completion-oriented reserve.
    # Thirty-two newly purchased Great Balls plus the retained legal Poké Ball
    # cover the complete bounded throw policy and are sold after capture, but
    # do not depend on variable leftovers from earlier species searches.
    max_throws=33,
    # A failed throw gives Snorlax a free turn.  Heal before the lead enters
    # Headbutt's held-out critical/damage-roll range instead of waiting for a
    # generic low-health threshold that is only safe between attacks.
    retreat_hp_ratio=0.65,
)
BATTLE_PP_BOUNDS = (
    (1, 8),
    SNORLAX_BUBBLEBEAM_PP_BOUND,
    (1, 8),
    (1, ROUTE13_BIRD_KEEPER_BITE_PP_BOUND),
    (1, 10),
)


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "D": "down", "L": "left", "R": "right"}[item] for item in value)


def _reverse(directions: tuple[str, ...]) -> tuple[str, ...]:
    opposite = {"up": "down", "down": "up", "left": "right", "right": "left"}
    return tuple(opposite[item] for item in reversed(directions))


LAVENDER_TO_ROUTE12 = _directions("DDDDDRRRRRRDRDDDDDDDDLDDD")
ROUTE12_FISHER = _directions("DDDDDDDDDDRDDDDDDDDDDDDDDRDDDDRRRDDDDLLLLD")
FISHER_TO_LAVENDER = _reverse(ROUTE12_FISHER) + _reverse(LAVENDER_TO_ROUTE12)
FISHER_TO_SNORLAX = _directions(
    "DDDLLLLLLDDDDDDRRRDRRDDDRRRRDDDDDDRDDDLLLLLLUUUULLLDDDDDDDRRRRRDDDDD"
)
SNORLAX_TO_LAVENDER = (
    _reverse(FISHER_TO_SNORLAX) + _reverse(ROUTE12_FISHER) + _reverse(LAVENDER_TO_ROUTE12)
)
LAVENDER_TO_SNORLAX = LAVENDER_TO_ROUTE12 + ROUTE12_FISHER + FISHER_TO_SNORLAX
SNORLAX_OBJECT_TILE = _directions("D")
SNORLAX_TO_ROCKER = _directions("DDRDDDDDDDDRRDR")
ROCKER_TO_ROUTE13 = _directions(
    "RDDDDDLLLLLLLLLLDDDDRRRRRDDDDDDDLLLDDLDDRRRRRDRRRDDDDDLDDDDDDLLDDDDDDDDDDDDLD"
)
ROUTE13_TRAINER_PAIR = _directions("DLL")
ROUTE13_TO_FUCHSIA = _directions(
    "LLLLLLLLLLLLLDLLLLLLLLLLUURUULLLLLLLLLUURRRRRRRUULLLLLLLLLDDLLLLDD"
    "LLLLLLDDLLLLLLLLLLLLDDDDDDRDDDDDDDDDDDDRDRDDDDDDDDDDDDDDDLLLLLL"
    "LLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLL"
)
FUCHSIA_TO_CENTER = _directions(
    "DLLDLLLLLLLLLLLLDLDDLLLLLLLLLLLLLLLLLLLLLLLDDDDDDDDDDDRRRRRRRUUUURRRRRRRRRRRU"
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
    captured: bool = False
    balls_used: int = 0
    recovery_items_used: int = 0
    party_before: tuple[int, ...] = ()
    party_after: tuple[int, ...] = ()


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
    great_balls_purchased: int
    funding_super_potions_sold: int
    funding_potions_sold: int
    funding_antidotes_sold: int
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    money_remaining: int
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == FUCHSIA_CHECKPOINT_COUNT
            and len(self.battles) == len(BATTLE_PP_BOUNDS)
            and all(
                lower <= battle.selected_pp_spent <= upper
                for battle, (lower, upper) in zip(self.battles, BATTLE_PP_BOUNDS, strict=True)
            )
            and tuple(item.trainer_number for item in self.battles) == (3, None, 2, 1, 12)
            and self.required_events == (True,) * len(REQUIRED_EVENTS)
            and self.optional_events == (False,) * len(OPTIONAL_EVENTS)
            and self.optional_items_carried == (False,) * len(OPTIONAL_ITEMS)
            and self.flute_retained
            and not self.snorlax_fight_before
            and not self.snorlax_fight_after
            and self.snorlax_object_tile_crossed
            and self.battles[1].captured
            and 1 <= self.battles[1].balls_used <= SNORLAX_CAPTURE_POLICY.max_throws
            and self.battles[1].party_after == self.battles[1].party_before + (SNORLAX,)
            and _bag_quantity(self.final_bag, ItemId.GREAT_BALL) == 0
            and _bag_quantity(self.final_bag, ItemId.SUPER_POTION) == 0
            and self.battles[1].balls_used <= SNORLAX_CAPTURE_POLICY.max_throws
            and self.battles[1].recovery_items_used
            <= max(
                SNORLAX_SUPER_POTION_RESERVE,
                _bag_quantity(self.initial_bag, ItemId.SUPER_POTION),
            )
            and _bag_quantity(self.initial_bag, ItemId.TM34_BIDE) in {0, 1}
            and _bag_quantity(self.final_bag, ItemId.TM34_BIDE) == 0
            and SNORLAX_MIN_GREAT_BALL_RESERVE
            <= self.great_balls_purchased
            <= SNORLAX_GREAT_BALL_RESERVE
            and self.funding_super_potions_sold
            == max(
                0,
                _bag_quantity(self.initial_bag, ItemId.SUPER_POTION)
                - SNORLAX_SUPER_POTION_RESERVE,
            )
            and _bag_quantity(self.initial_bag, ItemId.POTION)
            - _bag_quantity(self.final_bag, ItemId.POTION)
            == self.funding_potions_sold
            and _bag_quantity(self.initial_bag, ItemId.ANTIDOTE)
            - _bag_quantity(self.final_bag, ItemId.ANTIDOTE)
            == self.funding_antidotes_sold
            and _bag_quantity(self.initial_bag, ItemId.POKE_BALL)
            - _bag_quantity(self.final_bag, ItemId.POKE_BALL)
            == max(0, self.battles[1].balls_used - self.great_balls_purchased)
            and _without_bag_items(
                self.initial_bag,
                (
                    ItemId.GREAT_BALL,
                    ItemId.SUPER_POTION,
                    ItemId.POKE_BALL,
                    ItemId.TM34_BIDE,
                    ItemId.POTION,
                    ItemId.ANTIDOTE,
                ),
            )
            == _without_bag_items(
                self.final_bag,
                (
                    ItemId.GREAT_BALL,
                    ItemId.SUPER_POTION,
                    ItemId.POKE_BALL,
                    ItemId.TM34_BIDE,
                    ItemId.POTION,
                    ItemId.ANTIDOTE,
                ),
            )
            and self.final_raw.map_id == MapId.FUCHSIA_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and party_core_intact(self.final_raw.party_species_ids)
            and self.party_hp == self.party_max_hp
            and all(status == 0 for status in self.party_status)
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
                "captured": self.battles[1].captured,
                "throws_used": self.battles[1].balls_used,
                "recovery_items_used": self.battles[1].recovery_items_used,
                "great_balls_purchased": self.great_balls_purchased,
                "funding_super_potions_sold": self.funding_super_potions_sold,
                "funding_potions_sold": self.funding_potions_sold,
                "funding_antidotes_sold": self.funding_antidotes_sold,
                "party_before": list(self.battles[1].party_before),
                "party_after": list(self.battles[1].party_after),
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
            8,
            RedBattlePlanId.FUCHSIA_ROUTE_12_FISHER,
            trigger_direction="right",
        )
    )
    _checkpoint(records, progress, emulator, reader.read(), "fisher", "Defeated mandatory Fisher")

    # Collect the mandatory Fisher's deterministic payout before committing to
    # the full 33-throw Snorlax reserve.  Held-out battle timing can change how
    # many early Poké Balls survive for resale, but it cannot remove this
    # route-required income.
    _move(actions, reader, emulator, run, FISHER_TO_LAVENDER, timing, "Fisher income return")
    _require(reader.read(), MapId.LAVENDER_POKECENTER, (3, 3), "Fisher income return")
    (
        great_balls_purchased,
        funding_super_potions_sold,
        funding_potions_sold,
        funding_antidotes_sold,
    ) = _purchase_snorlax_capture_reserve(
        actions,
        reader,
        emulator,
        run,
        timing,
    )

    _move(actions, reader, emulator, run, LAVENDER_TO_SNORLAX, timing, "Route 12 Snorlax")
    snorlax_fight_before = _event(emulator, EventFlag.FIGHT_ROUTE12_SNORLAX)
    battles.append(_fight_snorlax(actions, reader, emulator, timing))
    snorlax_fight_after = _event(emulator, EventFlag.FIGHT_ROUTE12_SNORLAX)
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "snorlax",
        f"Caught Route 12 Snorlax in {battles[-1].balls_used} throw(s)",
    )
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
    _sell_capture_surplus(actions, reader, emulator, run, timing)
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
    snorlax_object_tile_crossed = reader.read().map_id == MapId.ROUTE_12 and (
        reader.read().player_x,
        reader.read().player_y,
    ) == (10, 62)
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
            BUBBLEBEAM,
            3,
            8,
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
            ROUTE13_BIRD_KEEPER_BITE_PP_BOUND,
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
            10,
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
        great_balls_purchased,
        funding_super_potions_sold,
        funding_potions_sold,
        funding_antidotes_sold,
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
    max_spent: int,
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
    battle = _settle_trainer_identity(actions, reader, emulator, timing, label, observed_identity)
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
    if not 0 < spent <= max_spent or not _event(emulator, event):
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
    party_before = raw.party_species_ids or ()
    before_pp = raw.first_party_pp
    final, balls_used, recovery_items_used = _run_wild_capture(
        actions,
        reader,
        emulator,
        int(MapId.ROUTE_12),
        timing,
        party_before,
    )
    if before_pp is None or final.first_party_pp is None:
        raise FuchsiaChapterError("Snorlax battle lacks PP evidence.")
    spent = (before_pp[2] & 0x3F) - (final.first_party_pp[2] & 0x3F)
    _clear_text(actions, reader, timing)
    if (
        not SNORLAX_BUBBLEBEAM_PP_BOUND[0] <= spent <= SNORLAX_BUBBLEBEAM_PP_BOUND[1]
        or not _event(emulator, EventFlag.BEAT_ROUTE12_SNORLAX)
        or _event(emulator, EventFlag.FIGHT_ROUTE12_SNORLAX)
        or ItemId.POKE_FLUTE not in _bag(emulator)
    ):
        raise FuchsiaChapterError(
            "Snorlax capture lacks exact PP/event/item evidence: "
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
        True,
        balls_used,
        recovery_items_used,
        party_before,
        final.party_species_ids or (),
    )


def _purchase_snorlax_capture_reserve(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    timing: FuchsiaTiming,
) -> tuple[int, int, int, int]:
    """Buy a bounded reliable-ball reserve before the static encounter."""

    before_money = _money(emulator)
    before_balls = _bag(emulator).get(ItemId.GREAT_BALL, 0)
    before_potions = _bag(emulator).get(ItemId.SUPER_POTION, 0)
    super_potion_sale_quantity = _snorlax_super_potion_sale_quantity(before_potions)
    super_potion_sale_proceeds = (
        super_potion_sale_quantity * SNORLAX_SUPER_POTION_SALE_PROCEEDS
    )
    poke_ball_sale_quantity = _snorlax_poke_ball_sale_quantity(
        _bag(emulator).get(ItemId.POKE_BALL, 0)
    )
    poke_ball_sale_proceeds = poke_ball_sale_quantity * SNORLAX_POKE_BALL_SALE_PROCEEDS
    potion_purchase_quantity = max(0, SNORLAX_SUPER_POTION_RESERVE - before_potions)
    if before_balls:
        raise FuchsiaChapterError("Fuchsia input unexpectedly already carries Great Balls.")
    _move(actions, reader, emulator, run, CENTER_EXIT, timing, "Lavender Center exit")
    _require(reader.read(), MapId.LAVENDER_TOWN, (3, 6), "Lavender Center exterior")
    _move(
        actions,
        reader,
        emulator,
        run,
        LAVENDER_CENTER_TO_MART,
        timing,
        "Lavender capture-supply Mart",
    )
    _require(reader.read(), MapId.LAVENDER_MART, (3, 7), "Lavender Mart entrance")
    _move(
        actions,
        reader,
        emulator,
        run,
        LAVENDER_MART_TO_CLERK,
        timing,
        "Lavender Mart clerk",
    )
    _pulse(actions, MacroActionKind.MOVE, "left", frames=60)
    tm34_sale_proceeds = 0
    if _bag(emulator).get(ItemId.TM34_BIDE, 0):
        _sell_single_mart_item(
            actions,
            reader,
            emulator,
            DEFAULT_LAVENDER_TIMING,
            ItemId.TM34_BIDE,
            expected_proceeds=SNORLAX_TM34_SALE_PROCEEDS,
        )
        tm34_sale_proceeds = SNORLAX_TM34_SALE_PROCEEDS
    available_funding = (
        before_money
        + tm34_sale_proceeds
        + poke_ball_sale_proceeds
        + super_potion_sale_proceeds
        + _bag(emulator).get(ItemId.POTION, 0) * SNORLAX_POTION_SALE_PROCEEDS
        + _bag(emulator).get(ItemId.ANTIDOTE, 0) * SNORLAX_ANTIDOTE_SALE_PROCEEDS
    )
    fixed_recovery_cost = potion_purchase_quantity * SUPER_POTION_PRICE
    great_ball_purchase_quantity = min(
        SNORLAX_GREAT_BALL_RESERVE,
        max(0, (available_funding - fixed_recovery_cost) // GREAT_BALL_PRICE),
    )
    if great_ball_purchase_quantity < SNORLAX_MIN_GREAT_BALL_RESERVE:
        raise FuchsiaChapterError(
            "Available resources cannot fund the minimum Snorlax capture reserve: "
            f"affordable={great_ball_purchase_quantity}, "
            f"minimum={SNORLAX_MIN_GREAT_BALL_RESERVE}."
        )
    expected_cost = (
        great_ball_purchase_quantity * GREAT_BALL_PRICE + fixed_recovery_cost
    )
    potion_sale_quantity, antidote_sale_quantity = _snorlax_funding_sale_quantities(
        money=(
            before_money
            + tm34_sale_proceeds
            + poke_ball_sale_proceeds
            + super_potion_sale_proceeds
        ),
        potions=_bag(emulator).get(ItemId.POTION, 0),
        antidotes=_bag(emulator).get(ItemId.ANTIDOTE, 0),
        required_cost=expected_cost,
    )
    funding_sale_proceeds = 0
    if poke_ball_sale_quantity:
        _sell_mart_item_stack(
            actions,
            reader,
            emulator,
            DEFAULT_LAVENDER_TIMING,
            ItemId.POKE_BALL,
            quantity=poke_ball_sale_quantity,
            expected_proceeds=poke_ball_sale_proceeds,
        )
        funding_sale_proceeds += poke_ball_sale_proceeds
    if super_potion_sale_quantity:
        _sell_mart_item_stack(
            actions,
            reader,
            emulator,
            DEFAULT_LAVENDER_TIMING,
            ItemId.SUPER_POTION,
            quantity=super_potion_sale_quantity,
            expected_proceeds=super_potion_sale_proceeds,
        )
        funding_sale_proceeds += super_potion_sale_proceeds
    if potion_sale_quantity:
        proceeds = potion_sale_quantity * SNORLAX_POTION_SALE_PROCEEDS
        _sell_mart_item_stack(
            actions,
            reader,
            emulator,
            DEFAULT_LAVENDER_TIMING,
            ItemId.POTION,
            quantity=potion_sale_quantity,
            expected_proceeds=proceeds,
        )
        funding_sale_proceeds += proceeds
    if antidote_sale_quantity:
        proceeds = antidote_sale_quantity * SNORLAX_ANTIDOTE_SALE_PROCEEDS
        _sell_mart_item_stack(
            actions,
            reader,
            emulator,
            DEFAULT_LAVENDER_TIMING,
            ItemId.ANTIDOTE,
            quantity=antidote_sale_quantity,
            expected_proceeds=proceeds,
        )
        funding_sale_proceeds += proceeds
    _pulse(actions, MacroActionKind.CONFIRM, frames=DEFAULT_LAVENDER_TIMING.wait_frames)
    _pulse(actions, MacroActionKind.CONFIRM, frames=DEFAULT_LAVENDER_TIMING.wait_frames)
    try:
        _buy_mart_item(
            actions,
            emulator,
            DEFAULT_LAVENDER_TIMING,
            absolute_index=0,
            item=ItemId.GREAT_BALL,
            quantity=great_ball_purchase_quantity,
            target_bag_quantity=great_ball_purchase_quantity,
        )
        # Reopen BUY from a verified field boundary so the completed 24-ball
        # quantity dialogue cannot be mistaken for the next product list.
        _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
        if potion_purchase_quantity:
            _pulse(actions, MacroActionKind.CONFIRM, frames=DEFAULT_LAVENDER_TIMING.wait_frames)
            _pulse(actions, MacroActionKind.CONFIRM, frames=DEFAULT_LAVENDER_TIMING.wait_frames)
            _buy_mart_item(
                actions,
                emulator,
                DEFAULT_LAVENDER_TIMING,
                absolute_index=1,
                item=ItemId.SUPER_POTION,
                quantity=potion_purchase_quantity,
                target_bag_quantity=before_potions + potion_purchase_quantity,
            )
            _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
    except LavenderChapterError as error:
        raise FuchsiaChapterError(f"Could not buy the Snorlax capture reserve: {error}") from error
    if (
        _bag(emulator).get(ItemId.GREAT_BALL, 0) != great_ball_purchase_quantity
        or _bag(emulator).get(ItemId.POKE_BALL, 0) != SNORLAX_POKE_BALL_RESERVE
        or _bag(emulator).get(ItemId.SUPER_POTION, 0)
        != before_potions - super_potion_sale_quantity + potion_purchase_quantity
        or before_money + tm34_sale_proceeds + funding_sale_proceeds - _money(emulator)
        != expected_cost
    ):
        raise FuchsiaChapterError("Snorlax capture-reserve economy proof failed.")
    _move(
        actions,
        reader,
        emulator,
        run,
        LAVENDER_MART_TO_TOWN,
        timing,
        "Lavender Mart exit",
    )
    _require(reader.read(), MapId.LAVENDER_TOWN, (15, 14), "Lavender Mart exterior")
    _move(
        actions,
        reader,
        emulator,
        run,
        LAVENDER_MART_TO_CENTER,
        timing,
        "Lavender Center return",
    )
    _require(reader.read(), MapId.LAVENDER_POKECENTER, (3, 7), "Lavender Center return")
    _move(actions, reader, emulator, run, ("up",) * 4, timing, "Lavender nurse return")
    _heal_at_nurse(actions, reader, emulator, timing)
    _require(reader.read(), MapId.LAVENDER_POKECENTER, (3, 3), "capture-ready boundary")
    return (
        great_ball_purchase_quantity,
        super_potion_sale_quantity,
        potion_sale_quantity,
        antidote_sale_quantity,
    )


def _snorlax_funding_sale_quantities(
    *,
    money: int,
    potions: int,
    antidotes: int,
    required_cost: int,
) -> tuple[int, int]:
    """Fund the throw ceiling from obsolete cures without overselling."""

    shortfall = max(0, required_cost - money)
    potion_quantity = min(
        potions,
        (shortfall + SNORLAX_POTION_SALE_PROCEEDS - 1) // SNORLAX_POTION_SALE_PROCEEDS,
    )
    shortfall = max(0, shortfall - potion_quantity * SNORLAX_POTION_SALE_PROCEEDS)
    antidote_quantity = min(
        antidotes,
        (shortfall + SNORLAX_ANTIDOTE_SALE_PROCEEDS - 1) // SNORLAX_ANTIDOTE_SALE_PROCEEDS,
    )
    shortfall = max(0, shortfall - antidote_quantity * SNORLAX_ANTIDOTE_SALE_PROCEEDS)
    if shortfall:
        raise FuchsiaChapterError(
            "Obsolete cure inventory cannot fund the declared Snorlax throw ceiling: "
            f"shortfall={shortfall}, money={money}, potions={potions}, "
            f"antidotes={antidotes}, required={required_cost}."
        )
    return potion_quantity, antidote_quantity


def _snorlax_poke_ball_sale_quantity(current_quantity: int) -> int:
    """Sell variable early-capture surplus while retaining one legal fallback ball."""

    if type(current_quantity) is not int or current_quantity < SNORLAX_POKE_BALL_RESERVE:
        raise FuchsiaChapterError(
            f"Snorlax preparation lacks its retained Poke Ball: {current_quantity}."
        )
    return current_quantity - SNORLAX_POKE_BALL_RESERVE


def _snorlax_super_potion_sale_quantity(current_quantity: int) -> int:
    """Liquidate tunnel surplus while retaining the full static-capture reserve."""

    if type(current_quantity) is not int or current_quantity < 0:
        raise FuchsiaChapterError(
            f"Snorlax preparation has invalid Super Potion inventory: {current_quantity}."
        )
    return max(0, current_quantity - SNORLAX_SUPER_POTION_RESERVE)


def _sell_capture_surplus(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    timing: FuchsiaTiming,
) -> None:
    """Recover capture spending and free both temporary bag slots."""

    surplus = tuple(
        (item, _bag(emulator).get(item, 0))
        for item in (ItemId.GREAT_BALL, ItemId.SUPER_POTION)
        if _bag(emulator).get(item, 0)
    )
    before_money = _money(emulator)
    _move(actions, reader, emulator, run, CENTER_EXIT, timing, "post-capture Center exit")
    _require(reader.read(), MapId.LAVENDER_TOWN, (3, 6), "post-capture Center exterior")
    _move(
        actions,
        reader,
        emulator,
        run,
        LAVENDER_CENTER_TO_MART,
        timing,
        "post-capture Lavender Mart",
    )
    _require(reader.read(), MapId.LAVENDER_MART, (3, 7), "post-capture Mart entrance")
    _move(
        actions,
        reader,
        emulator,
        run,
        LAVENDER_MART_TO_CLERK,
        timing,
        "post-capture Mart clerk",
    )
    _pulse(actions, MacroActionKind.MOVE, "left", frames=60)
    for item, quantity in surplus:
        _sell_capture_stack(actions, emulator, item, quantity, timing)
        _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)
    expected_proceeds = sum(
        quantity * (GREAT_BALL_PRICE if item is ItemId.GREAT_BALL else SUPER_POTION_PRICE) // 2
        for item, quantity in surplus
    )
    if (
        any(_bag(emulator).get(item, 0) for item, _ in surplus)
        or _money(emulator) - before_money != expected_proceeds
    ):
        raise FuchsiaChapterError("Post-capture sale missed its inventory/economy proof.")
    _move(
        actions,
        reader,
        emulator,
        run,
        LAVENDER_MART_TO_TOWN,
        timing,
        "post-capture Mart exit",
    )
    _require(reader.read(), MapId.LAVENDER_TOWN, (15, 14), "post-capture Mart exterior")
    _move(
        actions,
        reader,
        emulator,
        run,
        LAVENDER_MART_TO_CENTER,
        timing,
        "post-capture Center return",
    )
    _require(reader.read(), MapId.LAVENDER_POKECENTER, (3, 7), "post-capture Center return")
    _move(actions, reader, emulator, run, ("up",) * 4, timing, "post-capture nurse stance")
    _require(reader.read(), MapId.LAVENDER_POKECENTER, (3, 3), "post-capture route boundary")


def _sell_capture_stack(
    actions: _CountingExecutor,
    emulator: EmulatorState,
    item: ItemId,
    quantity: int,
    timing: FuchsiaTiming,
) -> None:
    _pulse(actions, MacroActionKind.INTERACT, frames=timing.wait_frames)
    _pulse(actions, MacroActionKind.MOVE, "down", frames=120)
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 1:
        raise FuchsiaChapterError("Lavender shop did not select SELL.")
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(24):
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        items = tuple(_bag(emulator))
        if absolute < len(items) and items[absolute] == item:
            break
        _pulse(actions, MacroActionKind.MOVE, "down", frames=120)
    else:
        raise FuchsiaChapterError(f"Sell list could not select {item.name}.")
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(quantity + 2):
        if (
            emulator.read_u8(RamAddress.SHOP_SELECTED_ITEM) == item
            and emulator.read_u8(RamAddress.SHOP_QUANTITY) == quantity
        ):
            break
        _pulse(actions, MacroActionKind.MOVE, "up", frames=120)
    else:
        raise FuchsiaChapterError(f"Sale quantity missed {quantity} {item.name}.")
    for _ in range(24):
        if _bag(emulator).get(item, 0) == 0:
            return
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    raise FuchsiaChapterError(f"Lavender Mart did not sell the {item.name} stack.")


def _run_wild_capture(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    expected_map: int,
    timing: FuchsiaTiming,
    party_before: tuple[int, ...],
) -> tuple[RawGameState, int, int]:
    throws_used = 0
    recovery_items_used = 0
    starting_balls = sum(
        _bag(emulator).get(item, 0) for item in (ItemId.GREAT_BALL, ItemId.POKE_BALL)
    )
    for pulse_index in range(SNORLAX_RUNTIME_PULSE_BOUND):
        raw = reader.read()
        balls_remaining = sum(
            _bag(emulator).get(item, 0) for item in (ItemId.GREAT_BALL, ItemId.POKE_BALL)
        )
        observed_throws = starting_balls - balls_remaining
        if observed_throws < throws_used or observed_throws > SNORLAX_CAPTURE_POLICY.max_throws:
            raise FuchsiaChapterError("Snorlax ball accounting left its bounded budget.")
        throws_used = observed_throws
        if raw.map_id != expected_map:
            raise FuchsiaChapterError("Snorlax battle changed map unexpectedly.")
        if raw.battle_state == 0:
            expected_party = party_before + (SNORLAX,)
            if raw.party_species_ids == expected_party:
                if (
                    starting_balls
                    - sum(
                        _bag(emulator).get(item, 0)
                        for item in (ItemId.GREAT_BALL, ItemId.POKE_BALL)
                    )
                    != throws_used
                ):
                    raise FuchsiaChapterError("Snorlax ball accounting drifted after capture.")
                if reader.read_input_readiness().ready:
                    return raw, throws_used, recovery_items_used
                _pulse(actions, MacroActionKind.CANCEL, frames=timing.wait_frames)
                continue
            if _event(emulator, EventFlag.BEAT_ROUTE12_SNORLAX):
                raise FuchsiaChapterError(
                    "Route 12 Snorlax was knocked out instead of captured: "
                    f"throws={throws_used}, enemy_hp={raw.enemy_hp!r}."
                )
            # A successful Gen I capture briefly clears battle state before the
            # nickname/party-transfer dialogue commits the new member.
            _pulse(actions, MacroActionKind.CANCEL, frames=timing.wait_frames)
            continue
        if raw.battle_state != 1 or (raw.battler_hp or 0) <= 0:
            raise FuchsiaChapterError(
                "Snorlax battle lost the qualified lead: "
                f"battle_state={raw.battle_state}, hp={raw.battler_hp!r}, "
                f"max_hp={raw.battler_max_hp!r}, throws={throws_used}, "
                f"recovery_items={recovery_items_used}."
            )
        menu = reader.read_battle_menu_state(raw)
        if menu.phase is BattleMenuPhase.UNKNOWN:
            _pulse(
                actions,
                MacroActionKind.CANCEL if pulse_index % 5 == 4 else MacroActionKind.CONFIRM,
                frames=timing.wait_frames,
            )
            continue
        if menu.phase is BattleMenuPhase.MAIN:
            decision = plan_capture(
                _snorlax_capture_observation(raw, emulator, throws_used),
                SNORLAX_CAPTURE_POLICY,
            )
            if decision.directive is CaptureDirective.WEAKEN_TARGET:
                _navigate_battle_main(actions, menu.selected_main_command, 0)
                _pulse(actions, MacroActionKind.CONFIRM, frames=120)
            elif decision.directive is CaptureDirective.THROW_BALL:
                _navigate_battle_main(actions, menu.selected_main_command, 1)
                _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
                ball = (
                    ItemId.GREAT_BALL
                    if _bag(emulator).get(ItemId.GREAT_BALL, 0)
                    else ItemId.POKE_BALL
                )
                _select_battle_bag_item(actions, emulator, ball)
                _pulse(actions, MacroActionKind.CONFIRM, frames=360)
            elif decision.directive is CaptureDirective.RESTORE_CATCHER:
                _restore_capture_catcher(actions, reader, emulator, raw, timing)
                recovery_items_used += 1
            else:
                raise FuchsiaChapterError(f"Snorlax capture stopped: {decision.reason}.")
            continue
        slot = menu.selected_move_slot
        target_slot = _snorlax_move_slot(raw)
        if slot == target_slot:
            _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
        elif slot is None:
            raise FuchsiaChapterError("Snorlax exposed an invalid move cursor.")
        else:
            _pulse(
                actions,
                MacroActionKind.MOVE,
                "down" if slot < target_slot else "up",
                frames=120,
            )
    raise FuchsiaChapterError("Snorlax battle exceeded its bounded runtime.")


def _snorlax_capture_observation(
    raw: RawGameState,
    emulator: EmulatorState,
    throws_used: int,
) -> CaptureObservation:
    if (
        raw.enemy_species_id != SNORLAX
        or raw.enemy_level != 30
        or raw.enemy_hp is None
        or raw.enemy_max_hp is None
        or raw.active_party_index is None
    ):
        raise FuchsiaChapterError("Snorlax capture observation lost live battle identity.")
    party = PokemonRedPartyReader(emulator).read()
    if not 0 <= raw.active_party_index < len(party.members):
        raise FuchsiaChapterError("Snorlax capture exposed an invalid active party slot.")
    return CaptureObservation(
        target_species_id=raw.enemy_species_id,
        target_level=raw.enemy_level,
        target_hp=raw.enemy_hp,
        target_max_hp=raw.enemy_max_hp,
        catcher=party.members[raw.active_party_index],
        balls_available=sum(
            _bag(emulator).get(item, 0) for item in (ItemId.GREAT_BALL, ItemId.POKE_BALL)
        ),
        party_has_room=len(party.members) < 6,
        throws_used=throws_used,
    )


def _navigate_battle_main(
    actions: _CountingExecutor,
    selected_command: int | None,
    target_command: int,
) -> None:
    if selected_command is None or not 0 <= selected_command <= 3:
        raise FuchsiaChapterError("Snorlax exposed an invalid battle command cursor.")
    directions = {
        0: {1: "up", 2: "left", 3: "up"},
        1: {0: "down", 2: "left", 3: "left"},
        2: {0: "right", 1: "right", 3: "up"},
        3: {0: "right", 1: "right", 2: "down"},
    }
    if selected_command == target_command:
        return
    direction = directions.get(target_command, {}).get(selected_command)
    if direction is None:
        raise FuchsiaChapterError("Snorlax battle-menu navigation is invalid.")
    _pulse(actions, MacroActionKind.MOVE, direction, frames=120)


def _select_battle_bag_item(
    actions: _CountingExecutor,
    emulator: EmulatorState,
    item: int,
) -> None:
    """Select one carried item using the battle bag's scrolling semantics."""

    for _ in range(24):
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        items = tuple(_bag(emulator))
        if item not in items:
            raise FuchsiaChapterError(f"Battle bag item {int(item):#04x} is unavailable.")
        if absolute < len(items) and items[absolute] == item:
            return
        target = items.index(item)
        _pulse(
            actions,
            MacroActionKind.MOVE,
            "down" if absolute < target else "up",
            frames=74,
        )
    raise FuchsiaChapterError(f"Could not select battle bag item {int(item):#04x}.")


def _restore_capture_catcher(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    raw: RawGameState,
    timing: FuchsiaTiming,
) -> None:
    """Spend one planned potion while preserving every party member."""

    target = raw.active_party_index
    if target is None:
        raise FuchsiaChapterError("Snorlax recovery lost the active catcher slot.")
    before_items = _bag(emulator).get(ItemId.SUPER_POTION, 0)
    if before_items <= 0:
        raise FuchsiaChapterError("Snorlax recovery exhausted its Super Potion reserve.")
    for pulse_index in range(24):
        menu = reader.read_battle_menu_state(reader.read())
        if menu.phase is BattleMenuPhase.MAIN and menu.selected_main_command == 1:
            break
        if menu.phase is BattleMenuPhase.MAIN:
            _navigate_battle_main(actions, menu.selected_main_command, 1)
        else:
            _pulse(
                actions,
                MacroActionKind.CANCEL if pulse_index % 5 == 4 else MacroActionKind.CONFIRM,
                frames=timing.wait_frames,
            )
    else:
        raise FuchsiaChapterError("Snorlax recovery could not select ITEM.")
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    _select_battle_bag_item(actions, emulator, ItemId.SUPER_POTION)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(12):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == target:
            break
        _pulse(
            actions,
            MacroActionKind.MOVE,
            "down" if cursor < target else "up",
            frames=120,
        )
    else:
        raise FuchsiaChapterError("Snorlax recovery could not select its catcher slot.")
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for pulse_index in range(32):
        settled = reader.read()
        if (
            settled.battle_state == 1
            and settled.active_party_index == target
            and (settled.battler_hp or 0) > 0
            and reader.read_battle_menu_state(settled).phase is BattleMenuPhase.MAIN
        ):
            if _bag(emulator).get(ItemId.SUPER_POTION, 0) != before_items - 1:
                raise FuchsiaChapterError(
                    "Snorlax recovery did not consume exactly one Super Potion."
                )
            return
        _pulse(
            actions,
            MacroActionKind.CANCEL if pulse_index % 5 == 4 else MacroActionKind.CONFIRM,
            frames=timing.wait_frames,
        )
    raise FuchsiaChapterError("Snorlax recovery did not settle safely.")


def _snorlax_move_slot(raw: RawGameState) -> int:
    pp = raw.first_party_pp or ()
    for slot in (3, 1, 4, 2):
        if (
            len(pp) >= slot
            and pp[slot - 1] & 0x3F
            and not (raw.player_disabled_move_slot == slot and (raw.player_disable_turns or 0) > 0)
        ):
            return slot
    raise FuchsiaChapterError("Snorlax policy has no legal move with PP.")


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
        if not party_core_intact(state.party_species_ids) or (state.first_party_hp or 0) <= 0:
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
        if _party_hp(emulator) == _party_max_hp(emulator) and all(
            status == 0 for status in _party_status(emulator)
        ):
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
        if _party_hp(emulator) == _party_max_hp(emulator) and all(
            status == 0 for status in _party_status(emulator)
        ):
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


def _bag_quantity(bag: tuple[tuple[int, int], ...], item: int) -> int:
    return next((quantity for bag_item, quantity in bag if bag_item == int(item)), 0)


def _without_bag_items(
    bag: tuple[tuple[int, int], ...], items: tuple[int, ...]
) -> tuple[tuple[int, int], ...]:
    excluded = {int(item) for item in items}
    return tuple(entry for entry in bag if entry[0] not in excluded)


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
        or not party_core_intact(raw.party_species_ids)
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
