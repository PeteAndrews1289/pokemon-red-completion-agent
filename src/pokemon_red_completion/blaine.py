"""Qualified Pokémon Mansion, Secret Key, Cinnabar Gym, and Blaine chapter.

The map routes, quiz answers, event IDs, trainer identity, party, and reward
order are pinned to pret/pokered commit
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
from pokemon_red_completion.celadon import (
    DEFAULT_CELADON_TIMING,
    CeladonWildFleeEvidence,
    _bag,
    _flee,
    _money,
    _party_hp,
    _party_max_hp,
    _party_status,
    _RunState,
)
from pokemon_red_completion.cinnabar import _four
from pokemon_red_completion.hideout import DEFAULT_HIDEOUT_TIMING, DIG
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    _buy_mart_item,
    _close_menus,
    _use_bag_item,
)
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
from pokemon_red_completion.silph import DEFAULT_SILPH_TIMING, _await_trainer_battle
from pokemon_red_completion.tower import TOWER_FINAL_PARTY

BLAINE_CHECKPOINT_COUNT = 8
BLAINE_OPPONENT = 0xEF
BLAINE_TRAINER_CLASS = 0xEF
BLAINE_TRAINER_SET = 1
BLAINE_PARTY = ((0x21, 42), (0xA3, 40), (0xA4, 42), (0x14, 47))
SURF_MOVE_ID = 0x39
MANSION_TRAINER_EVENTS = (
    EventFlag.BEAT_MANSION_1_TRAINER_0,
    EventFlag.BEAT_MANSION_2_TRAINER_0,
    EventFlag.BEAT_MANSION_3_TRAINER_0,
    EventFlag.BEAT_MANSION_3_TRAINER_1,
    EventFlag.BEAT_MANSION_4_TRAINER_0,
    EventFlag.BEAT_MANSION_4_TRAINER_1,
)
GYM_TRAINER_EVENTS = tuple(
    EventFlag(int(EventFlag.BEAT_CINNABAR_GYM_TRAINER_0) + offset)
    for offset in range(7)
)
GYM_GATE_EVENTS = tuple(
    EventFlag(int(EventFlag.CINNABAR_GYM_GATE_0_UNLOCKED) + offset)
    for offset in range(7)
)
QUIZ_ANSWERS = (True, False, False, False, True, False)
QUIZ_TEXT_PULSES = (9, 10, 9, 11, 11, 9)


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "R": "right", "D": "down", "L": "left"}[item] for item in value)


CENTER_TO_MART = ("down",) * 5 + ("right",) * 4 + ("up",)
MART_TO_MANSION = _directions("RDDDRRRUUUUUUULULLLLLLLLLLLU")
MANSION_1F_TO_3F = _directions("U" * 17 + "RRRURRUUUUUULLUUULL")
MANSION_3F_TO_STATUE = _directions("RRRRRDDDDL")
MANSION_3F_TO_B1F = _directions("RRRRDDDDRDRDDDLLLDDDDDDRRRRRRRRDDD")
MANSION_B1F_TO_STATUE = _directions("UUUUUUULLLLLLDDDRDDDDLDDDDR")
MANSION_B1F_TO_NORTH_STATUE = _directions(
    "LUUUULLLLLUUUUUUURRRRRRRRRRRRDDDRRUUUUUUUUUUUULUULLLLL"
)
MANSION_B1F_TO_SECRET_KEY = _directions("RRRRDDLLLLLLLLLLLLLLLLLLLLDDDDDDDDR")
GYM_ENTRY_ROUTE = _directions("RRRRRRRUUUUUUUUU")
GYM_QUIZ_ROUTES = (
    _directions("UUURRUUUUULLUL"),
    _directions("RURRUUUUUULLLLLLDLL"),
    _directions("RRDDDDDLLDL"),
    _directions("RDRRDDDDLLDL"),
    _directions("DDLLLLULLLUL"),
    _directions("RURRUUUULLUL"),
)
QUIZ_6_TO_BLAINE = _directions("RURRUUUL")
BLAINE_TO_GYM_EXIT = _directions(
    "RRDDDDDDDDDDDDRRRRUURURRUUUUUUUUUUUURRRRRRDDDDDDDDDDDDDLLDD"
)
MART_TO_GYM = _directions("RDDDRRRUUUUUUUUUU")
GYM_RETURN_TO_BLAINE = _directions(
    "UURRUUUUUUUUUUUUULLLLLLDDDDDDDDDDDDLLDLDDLLLLUUUUUUUUUUUULL"
)
GYM_EXIT_TO_CENTER = ("down",) * 8 + ("left",) * 7 + ("up",)


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class BlaineChapterError(RuntimeError):
    """Raised when the Mansion or Blaine evidence contract fails."""


@dataclass(frozen=True, slots=True)
class BlaineProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[BlaineProgress], None]


@dataclass(frozen=True, slots=True)
class BlaineCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class BlaineTurn:
    enemy_species: int
    enemy_level: int
    enemy_hp: int
    lead_hp: int
    lead_status: int
    pp: tuple[int, int, int, int]
    move_slot: int


@dataclass(frozen=True, slots=True)
class BlaineChapterReport:
    records: tuple[BlaineCheckpoint, ...]
    final_raw: RawGameState
    mansion_switch_trace: tuple[bool, ...]
    mansion_trainer_events_before: tuple[bool, ...]
    mansion_trainer_events_after: tuple[bool, ...]
    mansion_wild_flees: tuple[CeladonWildFleeEvidence, ...]
    secret_key_quantity: int
    quiz_answers: tuple[bool, ...]
    gym_gate_events_after_quizzes: tuple[bool, ...]
    gym_trainer_events_before: tuple[bool, ...]
    gym_trainer_events_after: tuple[bool, ...]
    identity: tuple[int, int, int]
    turns: tuple[BlaineTurn, ...]
    got_tm38: bool
    beat_blaine: bool
    volcano_badge: bool
    volcano_badge_mirror: bool
    tm38_quantity: int
    x_accuracy_sold: bool
    bide_sold: bool
    max_repel_bought: int
    initial_money: int
    money_remaining: int
    party_hp: tuple[int, int, int]
    party_max_hp: tuple[int, int, int]
    party_status: tuple[int, int, int]
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == BLAINE_CHECKPOINT_COUNT
            and self.mansion_switch_trace == (False, True, False, True)
            and self.mansion_trainer_events_before == (False,) * 6
            and self.mansion_trainer_events_after == (False,) * 6
            and len(self.mansion_wild_flees) <= 2
            and all(
                item.party_preserved
                and item.pp_preserved
                and item.hp_safe
                and item.inventory_preserved
                for item in self.mansion_wild_flees
            )
            and self.secret_key_quantity == 1
            and self.quiz_answers == QUIZ_ANSWERS
            and self.gym_gate_events_after_quizzes == (False,) + (True,) * 6
            and self.gym_trainer_events_before == (False,) * 7
            and self.gym_trainer_events_after == (True,) * 7
            and self.identity == (BLAINE_OPPONENT, BLAINE_TRAINER_CLASS, BLAINE_TRAINER_SET)
            and _encounter_party(self.turns) == BLAINE_PARTY
            and tuple(turn.move_slot for turn in self.turns) == (4, 4, 4, 4, 4)
            and all(turn.lead_hp > 0 and turn.lead_status == 0 for turn in self.turns)
            and self.got_tm38
            and self.beat_blaine
            and self.volcano_badge
            and self.volcano_badge_mirror
            and self.tm38_quantity == 1
            and self.x_accuracy_sold
            and self.bide_sold
            and self.max_repel_bought == 1
            and self.money_remaining == self.initial_money + 5_428
            and self.final_raw.map_id == MapId.CINNABAR_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and self.final_raw.party_species_ids == TOWER_FINAL_PARTY
            and self.final_raw.first_party_level == 47
            and self.final_raw.first_party_moves == (0x82, 0x46, 0x3A, SURF_MOVE_ID)
            and self.final_raw.first_party_pp == (15, 15, 10, 15)
            and self.party_hp == self.party_max_hp == (145, 47, 40)
            and self.party_status == (0, 0, 0)
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objectives": ["obtain_secret_key", "defeat_blaine"],
            "mansion": {
                "switch_trace": list(self.mansion_switch_trace),
                "optional_trainers_before": list(self.mansion_trainer_events_before),
                "optional_trainers_after": list(self.mansion_trainer_events_after),
                "wild_flees": [
                    {
                        "map": item.map_id,
                        "position": [item.x, item.y],
                        "species": item.species,
                        "level": item.level,
                        "party_preserved": item.party_preserved,
                        "pp_preserved": item.pp_preserved,
                        "hp_safe": item.hp_safe,
                        "inventory_preserved": item.inventory_preserved,
                    }
                    for item in self.mansion_wild_flees
                ],
                "secret_key": self.secret_key_quantity,
            },
            "quiz": {
                "answers": ["yes" if answer else "no" for answer in self.quiz_answers],
                "gates_after": list(self.gym_gate_events_after_quizzes),
                "trainers_before": list(self.gym_trainer_events_before),
            },
            "blaine": {
                "identity": list(self.identity),
                "party": [list(member) for member in BLAINE_PARTY],
                "move_slots": [turn.move_slot for turn in self.turns],
                "trainers_after": list(self.gym_trainer_events_after),
            },
            "rewards": {
                "tm38": self.tm38_quantity,
                "tm38_event": self.got_tm38,
                "blaine_event": self.beat_blaine,
                "volcano_badge": self.volcano_badge,
                "volcano_badge_mirror": self.volcano_badge_mirror,
            },
            "inventory": {
                "x_accuracy_sold": self.x_accuracy_sold,
                "bide_sold": self.bide_sold,
                "max_repel_bought": self.max_repel_bought,
                "money": [self.initial_money, self.money_remaining],
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


class _CountingExecutor:
    def __init__(self, delegate: ChapterExecutor) -> None:
        self.delegate = delegate
        self.actions_executed = 0

    def execute(self, action: MacroAction) -> object:
        result = self.delegate.execute(action)
        self.actions_executed += 1
        return result


def run_blaine_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    progress: ProgressSink | None = None,
) -> BlaineChapterReport:
    start_frames = emulator.frame_count
    actions = _CountingExecutor(executor)
    records: list[BlaineCheckpoint] = []
    initial = reader.read()
    _require(initial, MapId.CINNABAR_POKECENTER, (3, 3), "post-Cinnabar boundary")
    initial_money = _money(emulator)
    initial_bag = _bag(emulator)
    if (
        initial_bag.get(ItemId.SECRET_KEY, 0)
        or _event(emulator, EventFlag.BEAT_BLAINE)
        or _event(emulator, EventFlag.GOT_TM38)
        or initial.badge_bits & Badge.VOLCANO
    ):
        raise BlaineChapterError("Mansion/Blaine input boundary is not pristine.")
    if (
        len(initial_bag) != 20
        or initial_bag.get(ItemId.X_ACCURACY, 0) != 1
        or initial_bag.get(ItemId.TM34_BIDE, 0) != 1
    ):
        raise BlaineChapterError("Expected full Cinnabar input inventory was not present.")
    mansion_before = _events(emulator, MANSION_TRAINER_EVENTS)
    if mansion_before != (False,) * 6:
        raise BlaineChapterError("A Pokémon Mansion trainer was already defeated.")
    switch_trace = [_event(emulator, EventFlag.MANSION_SWITCH_ON)]
    if switch_trace != [False]:
        raise BlaineChapterError("Pokémon Mansion switch did not start off.")
    _checkpoint(records, progress, emulator, initial, "blaine_ready", "Mansion route ready")

    _move(actions, reader, CENTER_TO_MART, "Cinnabar Mart")
    _require(reader.read(), MapId.CINNABAR_MART, (3, 7), "Cinnabar Mart entry")
    _move(actions, reader, ("up", "up", "left"), "Cinnabar clerk")
    _pulse(actions, MacroActionKind.MOVE, "left", 120)
    _sell_current_bag_item(actions, reader, emulator, ItemId.X_ACCURACY)
    if _bag(emulator).get(ItemId.X_ACCURACY, 0):
        raise BlaineChapterError("X Accuracy sale did not settle.")
    _buy_repel(actions, reader, emulator)
    _use_bag_item(actions, reader, emulator, DEFAULT_LAVENDER_TIMING, ItemId.MAX_REPEL)
    if (
        _bag(emulator).get(ItemId.MAX_REPEL, 0)
        or emulator.read_u8(RamAddress.REPEL_REMAINING_STEPS) != 250
    ):
        raise BlaineChapterError("Max Repel did not activate from a one-item purchase.")

    _move(actions, reader, MART_TO_MANSION, "Cinnabar Mart to Mansion")
    _require(reader.read(), MapId.POKEMON_MANSION_1F, (5, 27), "Mansion entrance")
    _checkpoint(records, progress, emulator, reader.read(), "mansion_entered", "Entered Mansion")

    wilds = _move_mansion(
        actions,
        reader,
        emulator,
        MANSION_1F_TO_3F + MANSION_3F_TO_STATUE,
        "Mansion 3F statue",
    )
    _require(reader.read(), MapId.POKEMON_MANSION_3F, (10, 6), "Mansion 3F statue")
    _toggle_statue(actions, reader, emulator, expected=True)
    switch_trace.append(True)

    wilds += _move_mansion(
        actions,
        reader,
        emulator,
        MANSION_3F_TO_B1F + MANSION_B1F_TO_STATUE,
        "Mansion B1F south statue",
    )
    _require(reader.read(), MapId.POKEMON_MANSION_B1F, (18, 26), "B1F south statue")
    _toggle_statue(actions, reader, emulator, expected=False)
    switch_trace.append(False)

    wilds += _move_mansion(
        actions,
        reader,
        emulator,
        MANSION_B1F_TO_NORTH_STATUE,
        "Mansion B1F north statue",
    )
    _require(reader.read(), MapId.POKEMON_MANSION_B1F, (20, 4), "B1F north statue")
    _toggle_statue(actions, reader, emulator, expected=True)
    switch_trace.append(True)

    wilds += _move_mansion(
        actions,
        reader,
        emulator,
        MANSION_B1F_TO_SECRET_KEY,
        "Mansion Secret Key",
    )
    _require(reader.read(), MapId.POKEMON_MANSION_B1F, (5, 14), "Secret Key approach")
    _pick_up_secret_key(actions, reader, emulator)
    mansion_after = _events(emulator, MANSION_TRAINER_EVENTS)
    if mansion_after != mansion_before:
        raise BlaineChapterError("Mansion route changed an optional trainer event.")
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "secret_key_obtained",
        "Recovered Secret Key",
    )

    _field_dig(actions, reader, emulator)
    _require(reader.read(), MapId.SAFFRON_CITY, (9, 30), "Mansion Dig return")
    _field_fly_to_cinnabar(actions, reader, emulator)
    _require(reader.read(), MapId.CINNABAR_ISLAND, (11, 12), "Cinnabar Fly return")
    _move(actions, reader, ("up",), "Cinnabar Center entry")
    _require(reader.read(), MapId.CINNABAR_POKECENTER, (3, 7), "Cinnabar Center")
    _move(actions, reader, ("up",) * 4, "Cinnabar nurse")
    _heal(actions, reader, emulator)
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "mansion_returned",
        "Returned safely from Mansion",
    )

    _move(actions, reader, ("down",) * 5 + GYM_ENTRY_ROUTE, "Cinnabar Gym")
    _require(reader.read(), MapId.CINNABAR_GYM, (16, 17), "Cinnabar Gym entrance")
    gym_before = _events(emulator, GYM_TRAINER_EVENTS)
    if gym_before != (False,) * 7:
        raise BlaineChapterError("A Cinnabar Gym trainer was already defeated.")
    for index, (route, answer, text_pulses) in enumerate(
        zip(GYM_QUIZ_ROUTES, QUIZ_ANSWERS, QUIZ_TEXT_PULSES, strict=True),
        1,
    ):
        _move(actions, reader, route, f"Cinnabar quiz {index}")
        _answer_quiz(actions, reader, emulator, index, answer, text_pulses)
        if _events(emulator, GYM_TRAINER_EVENTS) != gym_before:
            raise BlaineChapterError(f"Quiz {index} changed a regular trainer event.")
    gates_after = _events(emulator, GYM_GATE_EVENTS)
    if gates_after != (False,) + (True,) * 6:
        raise BlaineChapterError(f"Unexpected Cinnabar gate state: {gates_after!r}.")
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "gym_quizzes_cleared",
        "Cleared six Gym quizzes",
    )

    _move(actions, reader, QUIZ_6_TO_BLAINE, "Blaine approach")
    _require(reader.read(), MapId.CINNABAR_GYM, (3, 4), "Blaine approach")
    _face_and_interact(actions, "up")
    _await_trainer_battle(actions, reader, DEFAULT_SILPH_TIMING)
    identity = (
        emulator.read_u8(RamAddress.CURRENT_OPPONENT),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_CLASS),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_SET),
    )
    if identity != (BLAINE_OPPONENT, BLAINE_TRAINER_CLASS, BLAINE_TRAINER_SET):
        raise BlaineChapterError(f"Unexpected Blaine identity: {identity!r}.")
    turns: list[BlaineTurn] = []

    def policy(raw: RawGameState) -> int:
        turns.append(
            BlaineTurn(
                raw.enemy_species_id or 0,
                raw.enemy_level or 0,
                raw.enemy_hp or 0,
                raw.first_party_hp or 0,
                raw.first_party_status or 0,
                raw.first_party_pp or (0, 0, 0, 0),
                4,
            )
        )
        return 4

    run_adaptive_trainer_battle(
        reader,
        actions,
        policy,
        expected_map=MapId.CINNABAR_GYM,
        intent=BattleIntent(
            "defeat_blaine",
            battle_plan_id=RedBattlePlanId.BLAINE_LEADER,
            required_move_policy=RequiredMovePolicy.EXACT_REQUIRED,
            required_move_ref=pokemon_red_move_ref(SURF_MOVE_ID),
        ),
        required_move_id=SURF_MOVE_ID,
        label="Blaine",
    )
    if _encounter_party(tuple(turns)) != BLAINE_PARTY:
        raise BlaineChapterError(f"Blaine party or Surf policy changed: {turns!r}.")
    _checkpoint(records, progress, emulator, reader.read(), "blaine_defeated", "Defeated Blaine")
    if not _event(emulator, EventFlag.BEAT_BLAINE):
        raise BlaineChapterError("Blaine victory event did not settle.")
    if _event(emulator, EventFlag.GOT_TM38):
        raise BlaineChapterError("Full-bag reward boundary unexpectedly accepted TM38.")

    _move(actions, reader, BLAINE_TO_GYM_EXIT, "Blaine to Gym exit")
    _move(actions, reader, ("down", "down"), "Cinnabar Gym exit")
    _require(reader.read(), MapId.CINNABAR_ISLAND, (18, 4), "Gym exterior")
    _move(
        actions,
        reader,
        ("down",) * 8 + ("left",) * 3 + ("up",),
        "Cinnabar Mart return",
    )
    _require(reader.read(), MapId.CINNABAR_MART, (3, 7), "Cinnabar Mart return")
    _move(actions, reader, ("up", "up", "left"), "Cinnabar clerk return")
    _pulse(actions, MacroActionKind.MOVE, "left", 120)
    _sell_current_bag_item(actions, reader, emulator, ItemId.TM34_BIDE)
    if _bag(emulator).get(ItemId.TM34_BIDE, 0):
        raise BlaineChapterError("TM34 Bide sale did not settle.")
    _close(actions, reader)
    _move(actions, reader, MART_TO_GYM, "Mart to Cinnabar Gym")
    _require(reader.read(), MapId.CINNABAR_GYM, (16, 16), "Gym reward return")
    _move(actions, reader, GYM_RETURN_TO_BLAINE, "Blaine reward approach")
    _require(reader.read(), MapId.CINNABAR_GYM, (3, 4), "Blaine reward approach")
    _face_and_interact(actions, "up")
    for _ in range(16):
        if _event(emulator, EventFlag.GOT_TM38):
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise BlaineChapterError("Blaine did not award TM38 after the bag slot was freed.")
    _checkpoint(records, progress, emulator, reader.read(), "tm38_received", "Received TM38")

    _move(actions, reader, BLAINE_TO_GYM_EXIT, "Blaine reward to Gym exit")
    _move(actions, reader, ("down", "down"), "Cinnabar Gym final exit")
    _require(reader.read(), MapId.CINNABAR_ISLAND, (18, 4), "Gym final exterior")
    _move(actions, reader, GYM_EXIT_TO_CENTER, "Cinnabar Center return")
    _require(reader.read(), MapId.CINNABAR_POKECENTER, (3, 7), "Cinnabar Center return")
    _move(actions, reader, ("up",) * 4, "Cinnabar final nurse")
    _heal(actions, reader, emulator)
    final = reader.read()
    _checkpoint(records, progress, emulator, final, "blaine_terminal", "Blaine terminal ready")

    report = BlaineChapterReport(
        records=tuple(records),
        final_raw=final,
        mansion_switch_trace=tuple(switch_trace),
        mansion_trainer_events_before=mansion_before,
        mansion_trainer_events_after=mansion_after,
        mansion_wild_flees=tuple(wilds),
        secret_key_quantity=_bag(emulator).get(ItemId.SECRET_KEY, 0),
        quiz_answers=QUIZ_ANSWERS,
        gym_gate_events_after_quizzes=gates_after,
        gym_trainer_events_before=gym_before,
        gym_trainer_events_after=_events(emulator, GYM_TRAINER_EVENTS),
        identity=identity,
        turns=tuple(turns),
        got_tm38=_event(emulator, EventFlag.GOT_TM38),
        beat_blaine=_event(emulator, EventFlag.BEAT_BLAINE),
        volcano_badge=bool(final.badge_bits & Badge.VOLCANO),
        volcano_badge_mirror=bool(emulator.read_u8(RamAddress.BEAT_GYM_FLAGS) & Badge.VOLCANO),
        tm38_quantity=_bag(emulator).get(ItemId.TM38_FIRE_BLAST, 0),
        x_accuracy_sold=ItemId.X_ACCURACY not in _bag(emulator),
        bide_sold=ItemId.TM34_BIDE not in _bag(emulator),
        max_repel_bought=1,
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
        raise BlaineChapterError(f"Blaine terminal evidence failed: {report!r}.")
    return report


def _sell_current_bag_item(actions, reader, emulator, item: ItemId) -> None:
    before = _bag(emulator)
    if before.get(item, 0) != 1:
        raise BlaineChapterError(f"Expected one {item.name} to sell.")
    _pulse(actions, MacroActionKind.INTERACT)
    _pulse(actions, MacroActionKind.MOVE, "down")
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 1:
        raise BlaineChapterError("Cinnabar shop did not select SELL.")
    _pulse(actions, MacroActionKind.CONFIRM)
    for _ in range(24):
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        if absolute < len(_bag(emulator)) and tuple(_bag(emulator))[absolute] == item:
            break
        _pulse(actions, MacroActionKind.MOVE, "down", 120)
    else:
        raise BlaineChapterError(f"Sell list could not select {item.name}.")
    for _ in range(12):
        _pulse(actions, MacroActionKind.CONFIRM)
        if item not in _bag(emulator):
            return
    raise BlaineChapterError(f"Sale of {item.name} did not settle.")


def _buy_repel(actions, reader, emulator) -> None:
    _pulse(actions, MacroActionKind.CANCEL)
    _select_cursor(actions, emulator, 0, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _buy_mart_item(
        actions,
        emulator,
        DEFAULT_LAVENDER_TIMING,
        absolute_index=3,
        item=ItemId.MAX_REPEL,
        quantity=1,
        target_bag_quantity=1,
    )
    _close_menus(actions, reader, DEFAULT_LAVENDER_TIMING)


def _move_mansion(
    actions,
    reader,
    emulator,
    route: Iterable[str],
    label: str,
) -> tuple[CeladonWildFleeEvidence, ...]:
    run = _RunState([])
    for index, direction in enumerate(tuple(route), 1):
        before = reader.read()
        for _ in range(4):
            _pulse(actions, MacroActionKind.MOVE, direction, 240)
            raw = reader.read()
            if raw.battle_state == 2:
                raise BlaineChapterError(f"{label} entered trainer battle at step {index}.")
            if raw.battle_state == 1:
                _flee(actions, reader, emulator, run, DEFAULT_CELADON_TIMING)
                raw = reader.read()
            if (raw.map_id, raw.player_x, raw.player_y) != (
                before.map_id,
                before.player_x,
                before.player_y,
            ):
                break
            _pulse(actions, MacroActionKind.CONFIRM, frames=240)
        else:
            raise BlaineChapterError(f"{label} blocked at step {index}.")
        if _events(emulator, MANSION_TRAINER_EVENTS) != (False,) * 6:
            raise BlaineChapterError(f"{label} changed an optional trainer event.")
    return tuple(run.wilds)


def _toggle_statue(actions, reader, emulator, *, expected: bool) -> None:
    before = _event(emulator, EventFlag.MANSION_SWITCH_ON)
    if before == expected:
        raise BlaineChapterError("Mansion statue toggle began in its target state.")
    _pulse(actions, MacroActionKind.MOVE, "up", 120)
    for _ in range(8):
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
        if (
            _event(emulator, EventFlag.MANSION_SWITCH_ON) is expected
            and reader.read_input_readiness().ready
        ):
            return
    raise BlaineChapterError("Mansion statue did not toggle to the expected state.")


def _pick_up_secret_key(actions, reader, emulator) -> None:
    before = len(_bag(emulator))
    for _ in range(8):
        if reader.read_input_readiness().ready:
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    else:
        raise BlaineChapterError("Secret Key approach did not settle field text.")
    _pulse(actions, MacroActionKind.MOVE, "up", 120)
    _pulse(actions, MacroActionKind.INTERACT)
    for _ in range(32):
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
        if (
            _bag(emulator).get(ItemId.SECRET_KEY, 0) == 1
            and reader.read_input_readiness().ready
        ):
            if len(_bag(emulator)) != before + 1:
                raise BlaineChapterError("Secret Key changed an unexpected bag slot count.")
            return
    raw = reader.read()
    raise BlaineChapterError(
        "Secret Key did not enter the bag: "
        f"bag_slots={len(_bag(emulator))}, input_ready={reader.read_input_readiness().ready}, "
        f"map={raw.map_id!r}, position={(raw.player_x, raw.player_y)!r}."
    )


def _field_dig(actions, reader, emulator) -> None:
    before_bag = _bag(emulator)
    before_hp = _party_hp(emulator)
    before_status = _party_status(emulator)
    before_pp = emulator.read_u8(int(RamAddress.PARTY_MON_3_PP) + 2)
    _pulse(actions, MacroActionKind.OPEN_MENU, frames=DEFAULT_HIDEOUT_TIMING.wait_frames)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM, frames=DEFAULT_HIDEOUT_TIMING.wait_frames)
    _select_cursor(actions, emulator, 2, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM, frames=DEFAULT_HIDEOUT_TIMING.wait_frames)
    if emulator.read_u8(int(RamAddress.PARTY_MON_3_MOVES) + 2) != DIG:
        raise BlaineChapterError("Diglett no longer exposes Dig in field slot zero.")
    _select_cursor(actions, emulator, 0, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM, frames=DEFAULT_HIDEOUT_TIMING.wait_frames)
    for _ in range(DEFAULT_HIDEOUT_TIMING.dialogue_pulses):
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
        if reader.read().map_id == MapId.SAFFRON_CITY:
            break
    else:
        raise BlaineChapterError("Field Dig did not return to Saffron.")
    if (
        _bag(emulator) != before_bag
        or _party_hp(emulator) != before_hp
        or _party_status(emulator) != before_status
        or emulator.read_u8(int(RamAddress.PARTY_MON_3_PP) + 2) != before_pp
    ):
        raise BlaineChapterError("Field Dig changed protected party or inventory state.")


def _field_fly_to_cinnabar(actions, reader, emulator) -> None:
    before_bag = _bag(emulator)
    before_hp = _party_hp(emulator)
    before_status = _party_status(emulator)
    before_moves = _four(emulator, RamAddress.PARTY_MON_2_MOVES)
    before_pp = _four(emulator, RamAddress.PARTY_MON_2_PP)
    _pulse(actions, MacroActionKind.OPEN_MENU)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _select_cursor(actions, emulator, 1, DEFAULT_HIDEOUT_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM)
    _pulse(actions, MacroActionKind.MOVE, "down", 120)
    _pulse(actions, MacroActionKind.MOVE, "down", 120)
    _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    for _ in range(12):
        if reader.read().map_id == MapId.CINNABAR_ISLAND:
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    else:
        raise BlaineChapterError("Fly did not return to Cinnabar.")
    if (
        _bag(emulator) != before_bag
        or _party_hp(emulator) != before_hp
        or _party_status(emulator) != before_status
        or _four(emulator, RamAddress.PARTY_MON_2_MOVES) != before_moves
        or _four(emulator, RamAddress.PARTY_MON_2_PP) != before_pp
    ):
        raise BlaineChapterError("Fly changed protected party or inventory state.")


def _answer_quiz(actions, reader, emulator, index: int, answer: bool, text_pulses: int) -> None:
    target_event = GYM_GATE_EVENTS[index]
    if _event(emulator, target_event):
        raise BlaineChapterError(f"Quiz gate {index} was already open.")
    _face_and_interact(actions, "up")
    for _ in range(text_pulses - 1):
        _pulse(actions, MacroActionKind.CONFIRM)
    if not answer:
        _pulse(actions, MacroActionKind.MOVE, "down", 120)
    _pulse(actions, MacroActionKind.CONFIRM)
    _pulse(actions, MacroActionKind.CONFIRM)
    _pulse(actions, MacroActionKind.CONFIRM)
    if not _event(emulator, target_event) or not reader.read_input_readiness().ready:
        raise BlaineChapterError(f"Quiz gate {index} did not open on the qualified answer.")


def _heal(actions, reader, emulator) -> None:
    for _ in range(20):
        _pulse(actions, MacroActionKind.CONFIRM)
        if (
            _party_hp(emulator) == _party_max_hp(emulator)
            and _party_status(emulator) == (0, 0, 0)
            and reader.read().first_party_pp == (15, 15, 10, 15)
        ):
            break
    _close(actions, reader)


def _move(actions, reader, route: Iterable[str], label: str, *, frames: int = 240) -> None:
    route = tuple(route)
    for index, direction in enumerate(route, 1):
        before = reader.read()
        for _ in range(8):
            _pulse(actions, MacroActionKind.MOVE, direction, frames)
            after = reader.read()
            if after.battle_state:
                raise BlaineChapterError(f"{label} entered battle at step {index}.")
            if (after.map_id, after.player_x, after.player_y) != (
                before.map_id,
                before.player_x,
                before.player_y,
            ):
                break
        else:
            raise BlaineChapterError(f"{label} blocked at step {index}/{len(route)}.")


def _face_and_interact(actions, direction: str) -> None:
    _pulse(actions, MacroActionKind.MOVE, direction, 120)
    _pulse(actions, MacroActionKind.INTERACT)


def _close(actions, reader) -> None:
    for _ in range(6):
        _pulse(actions, MacroActionKind.CANCEL)
    if not reader.read_input_readiness().ready:
        raise BlaineChapterError("Menus did not restore field input.")


def _select_cursor(actions, emulator, target: int, timing) -> None:
    for _ in range(20):
        current = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if current == target:
            return
        _pulse(actions, MacroActionKind.MOVE, "down" if current < target else "up", 120)
    raise BlaineChapterError(f"Menu could not select cursor {target}.")


def _pulse(actions, kind: MacroActionKind, value: str | None = None, frames: int = 180) -> None:
    actions.execute(MacroAction(kind, value))
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))


def _event(emulator, event: EventFlag) -> bool:
    index = int(event)
    value = emulator.read_u8(int(RamAddress.EVENT_FLAGS) + index // 8)
    return bool(value & (1 << (index % 8)))


def _events(emulator, events: Iterable[EventFlag]) -> tuple[bool, ...]:
    return tuple(_event(emulator, event) for event in events)


def _encounter_party(turns: tuple[BlaineTurn, ...]) -> tuple[tuple[int, int], ...]:
    party: list[tuple[int, int]] = []
    for turn in turns:
        member = (turn.enemy_species, turn.enemy_level)
        if not party or member != party[-1]:
            party.append(member)
    return tuple(party)


def _checkpoint(
    records: list[BlaineCheckpoint],
    progress: ProgressSink | None,
    emulator,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(BlaineCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            BlaineProgress(
                checkpoint_id,
                label,
                len(records),
                BLAINE_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )


def _require(raw: RawGameState, map_id: int, coordinate: tuple[int, int], label: str) -> None:
    if (raw.map_id, raw.player_x, raw.player_y) != (map_id, *coordinate):
        raise BlaineChapterError(
            f"{label} expected {(int(map_id), *coordinate)!r}, got "
            f"{(raw.map_id, raw.player_x, raw.player_y)!r}."
        )
