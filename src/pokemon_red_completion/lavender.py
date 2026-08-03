"""Qualified Thunder-Badge-to-Lavender traversal for pinned Pokémon Red.

The route is intentionally explicit.  It proves every unavoidable trainer
identity and event bit, treats random encounters as bounded recoverable
interruptions, and finishes only after the complete protected party is healed
inside Lavender's Pokémon Center.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_recovery import ProtectedRecoveryError, switch_active_battler
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleResourcePolicy,
    BattleRuntimeError,
    RequiredMovePolicy,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.economy import LAVENDER_SUPER_POTION_RESERVE
from pokemon_red_completion.observation import (
    BULBASAUR_SPECIES_ID,
    Badge,
    BattleMenuPhase,
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.red_party import PARTY_STRUCT_STRIDE
from pokemon_red_completion.surge import _swap_party_lead

LAVENDER_CHECKPOINT_COUNT = 15
WARTORTLE = 0xB3
DUX = 0x40
DIGLETT = 0x3B
BITE = 0x2C
BUBBLEBEAM = 0x3D
PECK = 0x40
CUT = 0x0F
PROTECTED_PARTY = (WARTORTLE, DUX, DIGLETT)
SUPER_POTION_PRICE = 700
NUGGET_SALE_PROCEEDS = 5_000
PARLYZ_HEAL_PRICE = 200
AWAKENING_PRICE = 200
REPEL_PRICE = 350
POST_MART_RNG_ALIGNMENT_FRAMES = 191
TUNNEL_RECOVERY_THRESHOLD = 40
TRAVERSAL_RECOVERY_THRESHOLD = 30
BATTLE_RECOVERY_THRESHOLD = 40
DUX_BATTLE_RECOVERY_THRESHOLD = 20
TUNNEL_TRAINER_7_BATTLE_RECOVERY_THRESHOLD = 40
FINAL_TUNNEL_RECOVERY_THRESHOLD = 90
FINAL_TUNNEL_GRASS_SPECIES = frozenset(
    {BULBASAUR_SPECIES_ID, 0xB9, 0xBA, 0xBC, 0xBD}
)
SLOWPOKE_SPECIES_ID = 0x25
ROUTE_9_MIN_SUPER_POTION_RESERVE = 5
TUNNEL_SUPER_POTIONS_PURCHASED = 10
TUNNEL_AWAKENINGS_PURCHASED = 1
TUNNEL_AWAKENING_RESERVE = 2
TUNNEL_PARLYZ_HEALS_PURCHASED = 2
TM28_SALE_PROCEEDS = 1_000


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "D": "down", "L": "left", "R": "right"}[c] for c in value)


GYM_EXIT = _directions("DDDDRDDDDDDLDDDDDD")
VERMILION_TREE_STANCE = _directions("RRRU")
TREE_TO_CENTER = _directions("UUUURRRUUUUUUUUUULLLLLLLU")
CENTER_EXIT = _directions("DDDDD")
VERMILION_CENTER_TO_MART = _directions("R" * 10 + "D" * 10 + "RRU")
VERMILION_TO_ROUTE_6 = _directions("LL" + "U" * 10 + "LL" + "U" * 5)
ROUTE_6_TO_SOUTH_GATE = _directions("U" * 7 + "R" * 5 + "U" * 14 + "R" * 3 + "U")
SOUTH_GATE_TO_TUNNEL = _directions("UURU")
TUNNEL_TO_NORTH_GATE = _directions("U" * 37 + "R" * 3)
NORTH_GATE_EXIT = _directions("DDDD")
ROUTE_5_TO_CERULEAN_TREE = _directions("LL" + "U" * 35 + "L" * 6)
CERULEAN_TREE_TO_ROUTE_9 = _directions("D" + "R" * 17 + "U" * 12 + "R" * 4)
ROUTE_9_TREE_STANCE = _directions("U" + "R" * 4)

_ROUTE_9 = "RRRRRRRDDDRRRRRRRRURRRRRRRRRDRRRRRRRRRRRRUUUUUULLUURRRRRURRRRRRRDDDDRRRRRRRRR"
ROUTE_9_TO_TRAINER_0_STANCE = _directions(_ROUTE_9[:8])
ROUTE_9_TRAINER_0_TRIGGER = _directions(_ROUTE_9[8:9])
ROUTE_9_TRAINER_0_TO_8 = _directions(_ROUTE_9[9:45])
ROUTE_9_AFTER_TRAINER_8 = _directions(_ROUTE_9[45:])
ROUTE_10_TO_CENTER = _directions("R" * 12 + "DDD" + "RR" + "D" * 8 + "LLLU")
ROCK_CENTER_TO_TUNNEL = _directions("D" * 6 + "L" * 9 + "U" * 8 + "R" * 6)

TUNNEL_TO_1F_TRAINER_3 = _directions("DDDDRRRRRD")
TUNNEL_1F_TO_B1 = _directions("DRRRDRRRRRRRRRRRUUUUUUURRR")
B1_TO_TRAINER_7 = _directions("D" * 6 + "L" * 7)
B1_TO_TRAINER_5_STANCE = _directions("LULLLLLLLLU")
B1_TRAINER_5_TRIGGER = _directions("U")
B1_TO_TRAINER_3 = _directions("UUUURRRUURU")
B1_TO_TRAINER_4 = _directions("UUUUURRRRRRRRRRRUUUUULL")
B1_TO_1F_WEST = _directions("LUUUULUUULU")
ONE_F_WEST_TO_B1 = _directions("RDDDDDDRRRRRDDDDDRRRUUURRR")
B1_TO_TRAINER_0 = _directions("DDLLLLLLDLLLLLL")
B1_TO_TRAINER_1 = _directions("LUUULLLL")
B1_TO_1F_EAST = _directions("RURUDDLLLUUUUUUUULL")
ONE_F_TO_TRAINER_4 = _directions("DDDLLLD")
ONE_F_TO_TRAINER_5 = _directions("DRRRDDDDDDLLLLLLLLLLULLLLL")
ONE_F_TO_SOUTH_EXIT = _directions("LLLDDDDDDLLLL")
ROUTE_10_TO_LAVENDER = _directions(
    "R" * 7 + "D" * 6 + "U" + "D" * 3 + "DD" + "L" * 4 + "D" * 3 + "LL" + "D" * 4
)
LAVENDER_TO_CENTER = _directions("DDLDDDDLLLLLU")
LAVENDER_CENTER_TO_MART = _directions("RRRRRRRRRDDDDDDDDRRRU")
LAVENDER_MART_TO_CLERK = _directions("UUL")
LAVENDER_MART_TO_TOWN = _directions("RDDD")
LAVENDER_MART_TO_CENTER = _directions("LLLUUUUUUUULLLLLLLLLU")


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class LavenderChapterError(RuntimeError):
    """Raised when the qualified Lavender route loses semantic evidence."""


@dataclass(frozen=True, slots=True)
class LavenderTiming:
    wait_frames: int = 180
    transition_frames: int = 120
    movement_retries: int = 18
    dialogue_pulses: int = 24
    flee_pulses: int = 20

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_LAVENDER_TIMING = LavenderTiming()


@dataclass(frozen=True, slots=True)
class LavenderProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[LavenderProgress], None]


@dataclass(frozen=True, slots=True)
class LavenderCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class TrainerEvidence:
    label: str
    map_id: int
    event: int
    opponent: int
    trainer_class: int
    trainer_set: int
    move_id: int
    selected_pp_spent: int


@dataclass(frozen=True, slots=True)
class WildFleeEvidence:
    map_id: int
    x: int
    y: int
    species: int
    level: int
    party_preserved: bool
    pp_preserved: bool
    hp_safe: bool
    inventory_preserved: bool


@dataclass(frozen=True, slots=True)
class LavenderChapterReport:
    records: tuple[LavenderCheckpoint, ...]
    trainers: tuple[TrainerEvidence, ...]
    wild_flees: tuple[WildFleeEvidence, ...]
    final_raw: RawGameState
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    repels_purchased: int
    repels_used: int
    parlyz_heals_purchased: int
    parlyz_heals_used: int
    parlyz_heals_remaining: int
    awakenings_used: int
    awakenings_remaining: int
    starting_super_potions: int
    super_potions_purchased: int
    super_potions_used: int
    super_potions_remaining: int
    purchase_cost: int
    tm28_sale_proceeds: int
    money_remaining: int
    route_10_trainer_2_bypassed: bool
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == LAVENDER_CHECKPOINT_COUNT
            and len(self.trainers) == 11
            and len({item.event for item in self.trainers}) == 11
            and all(item.selected_pp_spent > 0 for item in self.trainers)
            and all(
                item.party_preserved
                and item.pp_preserved
                and item.hp_safe
                and item.inventory_preserved
                for item in self.wild_flees
            )
            and self.final_raw.map_id == MapId.LAVENDER_POKECENTER
            and self.final_raw.party_species_ids == PROTECTED_PARTY
            and self.final_raw.battle_state == 0
            and self.party_hp == self.party_max_hp
            and all(status == 0 for status in self.party_status)
            and self.repels_purchased == self.repels_used == 4
            and self.parlyz_heals_purchased >= 1
            and self.parlyz_heals_used + self.parlyz_heals_remaining == self.parlyz_heals_purchased
            and 0 <= self.awakenings_used <= 2
            and self.awakenings_remaining >= 1
            and self.awakenings_used + self.awakenings_remaining
            == TUNNEL_AWAKENING_RESERVE
            and self.starting_super_potions in {0, 1}
            and self.super_potions_purchased >= 8
            and self.super_potions_used + self.super_potions_remaining
            == self.super_potions_purchased + self.starting_super_potions
            and self.super_potions_remaining == LAVENDER_SUPER_POTION_RESERVE
            and self.purchase_cost
            == self.super_potions_purchased * SUPER_POTION_PRICE
            + self.parlyz_heals_purchased * PARLYZ_HEAL_PRICE
            + TUNNEL_AWAKENINGS_PURCHASED * AWAKENING_PRICE
            + 4 * REPEL_PRICE
            and self.tm28_sale_proceeds in {0, TM28_SALE_PROCEEDS}
            and ItemId.TM28_DIG not in set(self.final_raw.bag_item_ids or ())
            and self.money_remaining >= 0
            and self.route_10_trainer_2_bypassed
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "reach_lavender",
            "trainer_battles": [
                {
                    "label": item.label,
                    "map_id": item.map_id,
                    "event": item.event,
                    "opponent": item.opponent,
                    "class": item.trainer_class,
                    "set": item.trainer_set,
                    "move_id": item.move_id,
                    "selected_pp_spent": item.selected_pp_spent,
                }
                for item in self.trainers
            ],
            "wild_flees": len(self.wild_flees),
            "inventory": {
                "repels_purchased": self.repels_purchased,
                "repels_used": self.repels_used,
                "parlyz_heals_purchased": self.parlyz_heals_purchased,
                "parlyz_heals_used": self.parlyz_heals_used,
                "parlyz_heals_remaining": self.parlyz_heals_remaining,
                "awakenings_used": self.awakenings_used,
                "awakenings_remaining": self.awakenings_remaining,
                "awakenings_purchased": TUNNEL_AWAKENINGS_PURCHASED,
                "starting_super_potions": self.starting_super_potions,
                "super_potions_purchased": self.super_potions_purchased,
                "super_potions_used": self.super_potions_used,
                "super_potions_remaining": self.super_potions_remaining,
                "purchase_cost": self.purchase_cost,
                "tm28_sale_proceeds": self.tm28_sale_proceeds,
                "money_remaining": self.money_remaining,
            },
            "route_10_trainer_2_bypassed": self.route_10_trainer_2_bypassed,
            "party": {
                "species": list(self.final_raw.party_species_ids or ()),
                "hp": list(self.party_hp),
                "max_hp": list(self.party_max_hp),
                "status": list(self.party_status),
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


@dataclass(slots=True)
class _RunState:
    wilds: list[WildFleeEvidence]
    trainers: list[TrainerEvidence]
    repels_used: int = 0
    parlyz_heals_used: int = 0
    awakenings_used: int = 0
    potions_used: int = 0


def run_lavender_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    timing: LavenderTiming = DEFAULT_LAVENDER_TIMING,
    progress: ProgressSink | None = None,
) -> LavenderChapterReport:
    """Continue the verified Surge boundary to a stable Lavender Center."""

    start_frames = emulator.frame_count
    actions = _CountingExecutor(executor)
    run = _RunState([], [])
    records: list[LavenderCheckpoint] = []

    start = reader.read()
    _require(
        start,
        MapId.VERMILION_GYM,
        (5, 2),
        "Surge terminal boundary",
        party=PROTECTED_PARTY,
    )
    if not (start.badge_bits or 0) & Badge.THUNDER:
        raise LavenderChapterError("Lavender chapter requires the Thunder Badge.")
    initial_sp = _bag(emulator).get(ItemId.SUPER_POTION, 0)
    initial_repel = _bag(emulator).get(ItemId.REPEL, 0)
    # Surge may consume the single reserved potion to keep the Dig-only proof
    # alive.  Both outcomes are legal and the Lavender Mart later tops the
    # observed quantity back up to the same fixed downstream reserve.
    if initial_sp not in {0, 1} or initial_repel != 0:
        raise LavenderChapterError(
            f"Unexpected starting recovery inventory: SP={initial_sp}, Repel={initial_repel}."
        )
    _checkpoint(records, progress, emulator, start, "surge_ready", "Verified Surge boundary")

    _move(actions, reader, emulator, run, GYM_EXIT, timing, "Vermilion Gym exit")
    _wait(actions, timing.transition_frames)
    gym_exited = reader.read()
    _require(gym_exited, MapId.VERMILION_CITY, (12, 20), "Gym exterior")
    _checkpoint(records, progress, emulator, gym_exited, "gym_exited", "Exited Vermilion Gym")

    _move(actions, reader, emulator, run, VERMILION_TREE_STANCE, timing, "second tree stance")
    _face_blocked(actions, reader, emulator, "up", 0x3D, timing, "second Gym tree")
    _use_cut(actions, reader, emulator, "up", timing)
    cut = reader.read()
    _require(cut, MapId.VERMILION_CITY, (15, 18), "second Cut passage")
    _checkpoint(records, progress, emulator, cut, "second_cut", "Cleared the second Gym tree")

    _move(actions, reader, emulator, run, TREE_TO_CENTER, timing, "Vermilion Center")
    _wait(actions, timing.transition_frames)
    _heal_center(actions, reader, emulator, timing, MapId.VERMILION_POKECENTER)
    healed = reader.read()
    _checkpoint(records, progress, emulator, healed, "healed", "Healed before Rock Tunnel")

    _teach_tm11(actions, reader, emulator, timing)
    bubblebeam = reader.read()
    if bubblebeam.first_party_moves != (BITE, 0x27, BUBBLEBEAM, 0x37):
        raise LavenderChapterError(f"TM11 produced wrong moves: {bubblebeam.first_party_moves!r}.")
    _checkpoint(records, progress, emulator, bubblebeam, "bubblebeam", "Taught BubbleBeam")

    _move(actions, reader, emulator, run, CENTER_EXIT, timing, "Vermilion Center exit")
    _wait(actions, timing.transition_frames)
    _move(
        actions,
        reader,
        emulator,
        run,
        VERMILION_CENTER_TO_MART,
        timing,
        "Vermilion Mart",
    )
    _wait(actions, timing.transition_frames)
    _require(reader.read(), MapId.VERMILION_MART, (3, 7), "Mart entrance")
    tunnel_purchase_cost = _purchase_supplies(
        actions, reader, emulator, timing, starting_super_potions=initial_sp
    )
    # Restore the qualified Route 9 battle lineage after the bounded quantity menu.
    _wait(actions, POST_MART_RNG_ALIGNMENT_FRAMES)
    supplies = reader.read()
    if (
        _bag(emulator).get(ItemId.SUPER_POTION)
        != initial_sp + TUNNEL_SUPER_POTIONS_PURCHASED
        or _bag(emulator).get(ItemId.PARLYZ_HEAL) != TUNNEL_PARLYZ_HEALS_PURCHASED
        or _bag(emulator).get(ItemId.AWAKENING) != TUNNEL_AWAKENING_RESERVE
        or _bag(emulator).get(ItemId.REPEL) != 4
    ):
        raise LavenderChapterError(
            "Mart purchase did not produce the ten-potion purchase plus the observed "
            "starting reserve, two Awakenings, "
            "two Parlyz Heals, and four Repels."
        )
    _checkpoint(records, progress, emulator, supplies, "supplies", "Purchased tunnel supplies")

    mart_position = reader.read()
    if (
        mart_position.map_id != MapId.VERMILION_MART
        or mart_position.player_x != 2
        or mart_position.player_y is None
        or not 5 <= mart_position.player_y <= 7
    ):
        raise LavenderChapterError("Mart menu closure lost the qualified exit column.")
    _move(
        actions,
        reader,
        emulator,
        run,
        _directions("R" + "D" * (8 - mart_position.player_y)),
        timing,
        "Vermilion Mart exit",
    )
    _wait(actions, timing.transition_frames)
    _move(
        actions,
        reader,
        emulator,
        run,
        VERMILION_TO_ROUTE_6,
        timing,
        "Route 6 return",
    )
    _wait(actions, timing.transition_frames)
    _use_repel(actions, reader, emulator, run, timing)
    _move(actions, reader, emulator, run, ROUTE_6_TO_SOUTH_GATE, timing, "Route 6 gate")
    _wait(actions, timing.transition_frames)
    _move(actions, reader, emulator, run, SOUTH_GATE_TO_TUNNEL, timing, "Underground Path")
    _wait(actions, timing.transition_frames)
    _move(actions, reader, emulator, run, TUNNEL_TO_NORTH_GATE, timing, "Underground Path north")
    _wait(actions, timing.transition_frames)
    _move(actions, reader, emulator, run, NORTH_GATE_EXIT, timing, "Route 5 exit")
    _wait(actions, timing.transition_frames)
    reverse = reader.read()
    _require(reverse, MapId.ROUTE_5, (17, 28), "Route 5 Underground exit")
    _checkpoint(
        records,
        progress,
        emulator,
        reverse,
        "reverse_underground",
        "Traversed Underground Path in reverse",
    )

    _move(
        actions,
        reader,
        emulator,
        run,
        ROUTE_5_TO_CERULEAN_TREE,
        timing,
        "Cerulean east tree",
        auto_repel=True,
    )
    _face_blocked(actions, reader, emulator, "up", 0x3D, timing, "Cerulean tree")
    _use_cut(actions, reader, emulator, "up", timing)
    cerulean_cut = reader.read()
    _require(cerulean_cut, MapId.CERULEAN_CITY, (19, 28), "Cerulean Cut passage")
    _checkpoint(records, progress, emulator, cerulean_cut, "cerulean_cut", "Opened Route 9 access")

    _move(
        actions,
        reader,
        emulator,
        run,
        CERULEAN_TREE_TO_ROUTE_9,
        timing,
        "Route 9 entry",
    )
    _wait(actions, timing.transition_frames)
    _move(actions, reader, emulator, run, ROUTE_9_TREE_STANCE, timing, "Route 9 tree")
    _face_blocked(actions, reader, emulator, "right", 0x3D, timing, "Route 9 tree")
    _use_cut(actions, reader, emulator, "right", timing)
    route9_cut = reader.read()
    _require(route9_cut, MapId.ROUTE_9, (5, 8), "Route 9 Cut passage")
    _checkpoint(records, progress, emulator, route9_cut, "route9_cut", "Cleared Route 9 tree")

    _move(
        actions,
        reader,
        emulator,
        run,
        ROUTE_9_TO_TRAINER_0_STANCE,
        timing,
        "Route 9 trainer 0 stance",
    )
    _swap(actions, reader, emulator, DUX, "Route 9 DUX lead")
    _trainer(
        actions,
        reader,
        emulator,
        run,
        ROUTE_9_TRAINER_0_TRIGGER,
        timing,
        "Route 9 trainer 0",
        MapId.ROUTE_9,
        EventFlag.BEAT_ROUTE_9_TRAINER_0,
        0xCE,
        0x06,
        5,
        PECK,
        1,
        RedBattlePlanId.LAVENDER_ROUTE_9_TRAINER_0,
        battle_recovery_threshold=DUX_BATTLE_RECOVERY_THRESHOLD,
        battle_recovery_limit=6,
    )
    _swap(actions, reader, emulator, WARTORTLE, "Route 9 Wartortle restoration")
    _move(
        actions,
        reader,
        emulator,
        run,
        ROUTE_9_TRAINER_0_TO_8,
        timing,
        "Route 9 trainer 8 route",
        auto_repel=True,
    )
    _trainer(
        actions,
        reader,
        emulator,
        run,
        (),
        timing,
        "Route 9 trainer 8",
        MapId.ROUTE_9,
        EventFlag.BEAT_ROUTE_9_TRAINER_8,
        0xCA,
        0x02,
        14,
        BUBBLEBEAM,
        3,
        RedBattlePlanId.LAVENDER_ROUTE_9_TRAINER_8,
        already_triggered=True,
        battle_recovery_limit=2,
    )
    _move(
        actions,
        reader,
        emulator,
        run,
        ROUTE_9_AFTER_TRAINER_8,
        timing,
        "Route 9 east",
        auto_repel=True,
    )
    route9_done = reader.read()
    _require(route9_done, MapId.ROUTE_10, (0, 8), "Route 10 north")
    route9_reserve = _bag(emulator).get(ItemId.SUPER_POTION, 0)
    if route9_reserve < ROUTE_9_MIN_SUPER_POTION_RESERVE:
        raise LavenderChapterError(
            "Route 9 did not preserve its declared Rock Tunnel recovery reserve: "
            f"observed {route9_reserve}, expected at least "
            f"{ROUTE_9_MIN_SUPER_POTION_RESERVE}."
        )
    _checkpoint(
        records,
        progress,
        emulator,
        route9_done,
        "route9_trainers",
        "Defeated both mandatory Route 9 trainers",
    )

    _move(actions, reader, emulator, run, ROUTE_10_TO_CENTER, timing, "Rock Tunnel Center")
    _wait(actions, timing.transition_frames)
    _heal_center(actions, reader, emulator, timing, MapId.ROCK_TUNNEL_POKECENTER)
    rock_center = reader.read()
    _checkpoint(records, progress, emulator, rock_center, "rock_center", "Healed at Route 10")

    _move(actions, reader, emulator, run, CENTER_EXIT, timing, "Rock Center exit")
    _wait(actions, timing.transition_frames)
    _move(
        actions,
        reader,
        emulator,
        run,
        ROCK_CENTER_TO_TUNNEL,
        timing,
        "Rock Tunnel entrance",
    )
    _clear_field_text(actions, reader, timing)
    _use_repel(actions, reader, emulator, run, timing)
    _move(actions, reader, emulator, run, ("up",), timing, "Rock Tunnel entry")
    _wait(actions, timing.transition_frames)
    tunnel_entered = reader.read()
    _require(tunnel_entered, MapId.ROCK_TUNNEL_1F, (15, 3), "Rock Tunnel 1F")
    _checkpoint(
        records, progress, emulator, tunnel_entered, "tunnel_entered", "Entered Rock Tunnel"
    )
    tunnel_start_reserve = _bag(emulator).get(ItemId.SUPER_POTION, 0)

    _trainer(
        actions,
        reader,
        emulator,
        run,
        TUNNEL_TO_1F_TRAINER_3,
        timing,
        "Rock Tunnel 1F trainer 3",
        MapId.ROCK_TUNNEL_1F,
        EventFlag.BEAT_ROCK_TUNNEL_1_TRAINER_3,
        0xCF,
        0x07,
        7,
        BUBBLEBEAM,
        3,
        RedBattlePlanId.LAVENDER_ROCK_TUNNEL_1F_TRAINER_3,
        battle_recovery_threshold=BATTLE_RECOVERY_THRESHOLD,
        battle_recovery_limit=1,
    )
    _require_potion_floor(emulator, tunnel_start_reserve - 1, "first tunnel trainer")
    _heal_if_below(actions, reader, emulator, run, timing, 0, TUNNEL_RECOVERY_THRESHOLD)
    _require_potion_floor(emulator, tunnel_start_reserve - 2, "first tunnel field recovery")
    _move(actions, reader, emulator, run, TUNNEL_1F_TO_B1, timing, "first B1 ladder")
    _wait(actions, timing.transition_frames)
    _trainer(
        actions,
        reader,
        emulator,
        run,
        B1_TO_TRAINER_7,
        timing,
        "Rock Tunnel B1F trainer 7",
        MapId.ROCK_TUNNEL_B1F,
        EventFlag.BEAT_ROCK_TUNNEL_2_TRAINER_7,
        0xCF,
        0x07,
        5,
        BITE,
        1,
        RedBattlePlanId.LAVENDER_ROCK_TUNNEL_B1F_TRAINER_7,
        battle_recovery_threshold=TUNNEL_TRAINER_7_BATTLE_RECOVERY_THRESHOLD,
        battle_recovery_limit=1,
    )
    _require_potion_floor(emulator, tunnel_start_reserve - 3, "trainer 7")
    _heal_if_below(
        actions,
        reader,
        emulator,
        run,
        timing,
        0,
        TRAVERSAL_RECOVERY_THRESHOLD,
    )
    _heal_if_below(
        actions,
        reader,
        emulator,
        run,
        timing,
        1,
        TRAVERSAL_RECOVERY_THRESHOLD,
    )
    _move(
        actions,
        reader,
        emulator,
        run,
        B1_TO_TRAINER_5_STANCE,
        timing,
        "B1 trainer 5 stance",
    )
    _swap(actions, reader, emulator, DUX, "B1 DUX lead")
    _trainer(
        actions,
        reader,
        emulator,
        run,
        B1_TRAINER_5_TRIGGER,
        timing,
        "Rock Tunnel B1F trainer 5",
        MapId.ROCK_TUNNEL_B1F,
        EventFlag.BEAT_ROCK_TUNNEL_2_TRAINER_5,
        0xCE,
        0x06,
        10,
        PECK,
        1,
        RedBattlePlanId.LAVENDER_ROCK_TUNNEL_B1F_TRAINER_5,
        protect_dux_status=True,
        battle_recovery_threshold=BATTLE_RECOVERY_THRESHOLD,
        battle_recovery_limit=2,
    )
    _heal_if_below(actions, reader, emulator, run, timing, 1, TRAVERSAL_RECOVERY_THRESHOLD)
    _swap(actions, reader, emulator, WARTORTLE, "B1 Wartortle restoration")
    _heal_if_below(actions, reader, emulator, run, timing, 0, TUNNEL_RECOVERY_THRESHOLD)
    # Preserve required-move evidence against the self-destructing Hiker set.
    # A held-out lineage arrived paralyzed, lost its turn, and won without
    # spending BubbleBeam PP when the final opponent self-KO'd.
    _cure_tunnel_status_if_present(actions, reader, emulator, run, timing)
    _trainer(
        actions,
        reader,
        emulator,
        run,
        B1_TO_TRAINER_3,
        timing,
        "Rock Tunnel B1F trainer 3",
        MapId.ROCK_TUNNEL_B1F,
        EventFlag.BEAT_ROCK_TUNNEL_2_TRAINER_3,
        0xCF,
        0x07,
        4,
        BUBBLEBEAM,
        3,
        RedBattlePlanId.LAVENDER_ROCK_TUNNEL_B1F_TRAINER_3,
    )
    _heal_if_below(actions, reader, emulator, run, timing, 0, TUNNEL_RECOVERY_THRESHOLD)
    _trainer(
        actions,
        reader,
        emulator,
        run,
        B1_TO_TRAINER_4,
        timing,
        "Rock Tunnel B1F trainer 4",
        MapId.ROCK_TUNNEL_B1F,
        EventFlag.BEAT_ROCK_TUNNEL_2_TRAINER_4,
        0xD1,
        0x09,
        10,
        BUBBLEBEAM,
        3,
        RedBattlePlanId.LAVENDER_ROCK_TUNNEL_B1F_TRAINER_4,
    )
    _heal_if_below(actions, reader, emulator, run, timing, 0, TUNNEL_RECOVERY_THRESHOLD)
    _move(actions, reader, emulator, run, B1_TO_1F_WEST, timing, "B1 west ladder")
    _wait(actions, timing.transition_frames)
    _move(actions, reader, emulator, run, ONE_F_WEST_TO_B1, timing, "1F west traverse")
    _wait(actions, timing.transition_frames)
    _trainer(
        actions,
        reader,
        emulator,
        run,
        B1_TO_TRAINER_0,
        timing,
        "Rock Tunnel B1F trainer 0",
        MapId.ROCK_TUNNEL_B1F,
        EventFlag.BEAT_ROCK_TUNNEL_2_TRAINER_0,
        0xCE,
        0x06,
        9,
        BUBBLEBEAM,
        3,
        RedBattlePlanId.LAVENDER_ROCK_TUNNEL_B1F_TRAINER_0,
    )
    _heal_if_below(actions, reader, emulator, run, timing, 0, TUNNEL_RECOVERY_THRESHOLD)
    _trainer(
        actions,
        reader,
        emulator,
        run,
        B1_TO_TRAINER_1,
        timing,
        "Rock Tunnel B1F trainer 1",
        MapId.ROCK_TUNNEL_B1F,
        EventFlag.BEAT_ROCK_TUNNEL_2_TRAINER_1,
        0xD1,
        0x09,
        9,
        BUBBLEBEAM,
        3,
        RedBattlePlanId.LAVENDER_ROCK_TUNNEL_B1F_TRAINER_1,
    )
    _heal_if_below(actions, reader, emulator, run, timing, 1, TRAVERSAL_RECOVERY_THRESHOLD)
    _move(actions, reader, emulator, run, B1_TO_1F_EAST, timing, "B1 east ladder")
    _wait(actions, timing.transition_frames)
    _heal_if_below(
        actions,
        reader,
        emulator,
        run,
        timing,
        0,
        FINAL_TUNNEL_RECOVERY_THRESHOLD,
    )
    _prepare_dux_sleep_pivot(actions, reader, emulator, run, timing)
    _swap(actions, reader, emulator, DUX, "final tunnel Grass lead")
    _trainer(
        actions,
        reader,
        emulator,
        run,
        ONE_F_TO_TRAINER_4,
        timing,
        "Rock Tunnel 1F trainer 4",
        MapId.ROCK_TUNNEL_1F,
        EventFlag.BEAT_ROCK_TUNNEL_1_TRAINER_4,
        0xCE,
        0x06,
        17,
        PECK,
        1,
        RedBattlePlanId.LAVENDER_ROCK_TUNNEL_1F_TRAINER_4,
        finish_with_bubblebeam=True,
        protect_dux_status=True,
    )
    _heal_if_below(
        actions,
        reader,
        emulator,
        run,
        timing,
        0,
        FINAL_TUNNEL_RECOVERY_THRESHOLD,
    )
    _cure_tunnel_status_if_present(actions, reader, emulator, run, timing)
    _trainer(
        actions,
        reader,
        emulator,
        run,
        ONE_F_TO_TRAINER_5,
        timing,
        "Rock Tunnel 1F trainer 5",
        MapId.ROCK_TUNNEL_1F,
        EventFlag.BEAT_ROCK_TUNNEL_1_TRAINER_5,
        0xCE,
        0x06,
        18,
        PECK,
        1,
        RedBattlePlanId.LAVENDER_ROCK_TUNNEL_1F_TRAINER_5,
        finish_with_bubblebeam=True,
        protect_dux_status=True,
    )
    _swap(actions, reader, emulator, WARTORTLE, "final tunnel Wartortle restoration")
    _heal_if_below(actions, reader, emulator, run, timing, 0, TRAVERSAL_RECOVERY_THRESHOLD)
    _move(actions, reader, emulator, run, ONE_F_TO_SOUTH_EXIT, timing, "Rock Tunnel exit")
    _wait(actions, timing.transition_frames)
    tunnel_cleared = reader.read()
    _require(tunnel_cleared, MapId.ROUTE_10, (8, 54), "Rock Tunnel south exit")
    _checkpoint(
        records,
        progress,
        emulator,
        tunnel_cleared,
        "rock_tunnel_cleared",
        "Cleared all nine mandatory tunnel trainers",
    )

    if _event(emulator, EventFlag.BEAT_ROUTE_10_TRAINER_2):
        raise LavenderChapterError("Optional Route 10 trainer 2 was already defeated.")
    _move(actions, reader, emulator, run, ROUTE_10_TO_LAVENDER, timing, "Lavender approach")
    _wait(actions, timing.transition_frames)
    lavender = reader.read()
    _require(lavender, MapId.LAVENDER_TOWN, (9, 0), "Lavender north entrance")
    if _event(emulator, EventFlag.BEAT_ROUTE_10_TRAINER_2):
        raise LavenderChapterError("Route 10 bypass defeated optional trainer 2.")
    if _party_hp(emulator)[1] <= 0:
        raise LavenderChapterError("DUX did not survive the qualified poisoned traversal.")
    _checkpoint(records, progress, emulator, lavender, "lavender_reached", "Reached Lavender Town")

    _move(actions, reader, emulator, run, LAVENDER_TO_CENTER, timing, "Lavender Center")
    _wait(actions, timing.transition_frames)
    _heal_center(actions, reader, emulator, timing, MapId.LAVENDER_POKECENTER)
    top_up_quantity, top_up_parlyz_heals, top_up_cost, tm28_sale_proceeds = (
        _top_up_lavender_supplies(
            actions,
            reader,
            emulator,
            run,
            timing,
        )
    )
    final = reader.read()
    hp = _party_hp(emulator)
    max_hp = _party_max_hp(emulator)
    status = _party_status(emulator)
    if (
        final.party_species_ids != PROTECTED_PARTY
        or hp != max_hp
        or status != (0, 0, 0)
        or not reader.read_input_readiness().ready
    ):
        raise LavenderChapterError("Lavender Center failed the full-party stable gate.")
    _checkpoint(records, progress, emulator, final, "lavender_stable", "Healed safely in Lavender")

    report = LavenderChapterReport(
        records=tuple(records),
        trainers=tuple(run.trainers),
        wild_flees=tuple(run.wilds),
        final_raw=final,
        party_hp=hp,
        party_max_hp=max_hp,
        party_status=status,
        repels_purchased=4,
        repels_used=run.repels_used,
        parlyz_heals_purchased=TUNNEL_PARLYZ_HEALS_PURCHASED + top_up_parlyz_heals,
        parlyz_heals_used=run.parlyz_heals_used,
        parlyz_heals_remaining=_bag(emulator).get(ItemId.PARLYZ_HEAL, 0),
        awakenings_used=run.awakenings_used,
        awakenings_remaining=_bag(emulator).get(ItemId.AWAKENING, 0),
        starting_super_potions=initial_sp,
        super_potions_purchased=TUNNEL_SUPER_POTIONS_PURCHASED + top_up_quantity,
        super_potions_used=run.potions_used,
        super_potions_remaining=_bag(emulator).get(ItemId.SUPER_POTION, 0),
        purchase_cost=tunnel_purchase_cost + top_up_cost,
        tm28_sale_proceeds=tm28_sale_proceeds,
        money_remaining=_money(emulator),
        route_10_trainer_2_bypassed=not _event(emulator, EventFlag.BEAT_ROUTE_10_TRAINER_2),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise LavenderChapterError("Lavender chapter failed its evidence contract.")
    return report


class _PauseForBattleSuperPotion(Exception):
    pass


class _PauseForBattleAwakening(Exception):
    pass


class _PauseForFinalTunnelPivot(Exception):
    def __init__(self, party_index: int) -> None:
        self.party_index = party_index


def _run_lavender_trainer_battle(
    reader: PokemonRedStateReader,
    executor: _CountingExecutor,
    emulator: EmulatorState,
    run: _RunState,
    timing: LavenderTiming,
    *,
    move_slot: int,
    map_id: int,
    label: str,
    intent: BattleIntent,
    finish_with_bubblebeam: bool = False,
    protect_dux_status: bool = False,
    battle_recovery_threshold: int | None = None,
    battle_recovery_limit: int | None = None,
) -> RawGameState:
    """Preserve the required move while recovering from held-out damage rolls."""

    starting_reserve = _bag(emulator).get(ItemId.SUPER_POTION, 0)
    starting_pp = reader.read().first_party_pp
    if starting_pp is None or len(starting_pp) < move_slot:
        raise LavenderChapterError(f"{label} lacks starting PP evidence.")
    starting_selected_pp = starting_pp[move_slot - 1] & 0x3F

    dux_status_escaped = False
    selected_move_evidence_observed = False

    def guarded_policy(raw: RawGameState) -> int:
        nonlocal selected_move_evidence_observed
        if (
            raw.active_party_index == 0
            and raw.battler_pp is not None
            and len(raw.battler_pp) >= move_slot
            and (raw.battler_pp[move_slot - 1] & 0x3F) < starting_selected_pp
        ):
            selected_move_evidence_observed = True
        status_recovery, pivot_target = _dux_status_recovery_strategy(
            raw,
            _party_hp(emulator),
            protect_dux_status,
            awakenings=_bag(emulator).get(ItemId.AWAKENING, 0),
        )
        if status_recovery == "pivot" and pivot_target is not None:
            raise _PauseForFinalTunnelPivot(pivot_target)
        if status_recovery == "awakening":
            raise _PauseForBattleAwakening
        pivot_target = _final_tunnel_pivot_target(
            raw,
            _party_hp(emulator),
            finish_with_bubblebeam,
            dux_unavailable=dux_status_escaped,
            required_move_spent=selected_move_evidence_observed,
        )
        if pivot_target is not None:
            raise _PauseForFinalTunnelPivot(pivot_target)
        hp = raw.battler_hp or 0
        max_hp = raw.battler_max_hp or 0
        recovery_threshold = (
            battle_recovery_threshold
            if battle_recovery_threshold is not None
            else BATTLE_RECOVERY_THRESHOLD
        )
        recovery_available = (
            battle_recovery_limit is None or recoveries < battle_recovery_limit
        )
        if (
            0 < hp < max_hp
            and hp <= recovery_threshold
            and recovery_available
            and _bag(emulator).get(ItemId.SUPER_POTION, 0)
        ):
            raise _PauseForBattleSuperPotion
        moves = raw.battler_moves
        pp = raw.battler_pp
        if moves is None or pp is None:
            raise LavenderChapterError(f"{label} lacks live move and PP evidence.")
        selected_pp = pp[move_slot - 1] & 0x3F
        ranked_slots = _ranked_lavender_move_slots(
            move_slot=move_slot,
            starting_selected_pp=starting_selected_pp,
            current_selected_pp=selected_pp,
            finish_with_bubblebeam=finish_with_bubblebeam,
            enemy_species_id=raw.enemy_species_id,
            active_party_index=raw.active_party_index,
        )
        for candidate in ranked_slots:
            index = candidate - 1
            if (
                len(moves) > index
                and len(pp) > index
                and moves[index] != 0
                and pp[index] & 0x3F
                and raw.player_disabled_move_slot != candidate
            ):
                return candidate
        raise LavenderChapterError(f"{label} has no usable ranked attack.")

    recoveries = 0
    while True:
        try:
            return run_adaptive_trainer_battle(
                reader,
                executor,
                guarded_policy,
                expected_map=int(map_id),
                intent=intent,
                label=label,
            )
        except BattleRuntimeError as error:
            if isinstance(error.__cause__, _PauseForBattleAwakening):
                _use_battle_status_item(
                    reader,
                    executor,
                    emulator,
                    timing,
                    label,
                    item=ItemId.AWAKENING,
                    expected_status=reader.read().battler_status or 0,
                )
                run.awakenings_used += 1
                continue
            if isinstance(error.__cause__, _PauseForFinalTunnelPivot):
                before_pivot = reader.read()
                if (
                    before_pivot.active_party_index == 0
                    and (before_pivot.battler_status or 0)
                ):
                    dux_status_escaped = True
                try:
                    switch_active_battler(
                        executor,
                        reader,
                        emulator,
                        error.__cause__.party_index,
                        label=f"{label} observed role pivot",
                        wait_frames=timing.wait_frames,
                    )
                except ProtectedRecoveryError as pivot_error:
                    raise LavenderChapterError(str(pivot_error)) from pivot_error
                continue
            if not isinstance(error.__cause__, _PauseForBattleSuperPotion):
                raise
        _use_battle_super_potion(reader, executor, emulator, run, timing, label)
        recoveries += 1
        if recoveries > starting_reserve:
            raise LavenderChapterError(f"{label} exceeded its bounded recovery reserve.")


def _ranked_lavender_move_slots(
    *,
    move_slot: int,
    starting_selected_pp: int,
    current_selected_pp: int,
    finish_with_bubblebeam: bool,
    enemy_species_id: int | None,
    active_party_index: int | None,
) -> tuple[int, ...]:
    """Spend the evidence move once, then exploit without feeding resisted Wrap turns."""

    selected_move_spent = current_selected_pp < starting_selected_pp
    if (
        active_party_index in {None, 0}
        and enemy_species_id == SLOWPOKE_SPECIES_ID
        and (move_slot == 1 or selected_move_spent)
    ) or (
        active_party_index == 1
        and enemy_species_id in FINAL_TUNNEL_GRASS_SPECIES
        and selected_move_spent
    ):
        ranked = (1, move_slot, 3, 4)
    elif finish_with_bubblebeam and active_party_index == 0:
        ranked = (move_slot, 1, 3, 4)
    elif (
        finish_with_bubblebeam and active_party_index == 1
    ) or selected_move_spent:
        ranked = (3, move_slot, 1, 4)
    else:
        ranked = (move_slot, 3, 1, 4)
    return tuple(dict.fromkeys(ranked))


def _use_battle_super_potion(
    reader: PokemonRedStateReader,
    executor: _CountingExecutor,
    emulator: EmulatorState,
    run: _RunState,
    timing: LavenderTiming,
    label: str,
) -> None:
    before = reader.read()
    menu = reader.read_battle_menu_state(before)
    target_index = before.active_party_index
    before_quantity = _bag(emulator).get(ItemId.SUPER_POTION, 0)
    if (
        before.battle_state != 2
        or target_index is None
        or menu.phase is not BattleMenuPhase.MAIN
        or before.battler_hp is None
        or before.battler_max_hp is None
        or not 0 < before.battler_hp < before.battler_max_hp
        or before_quantity <= 0
    ):
        raise LavenderChapterError(f"{label} recovery lacks a stable damaged MAIN gate.")

    command = menu.selected_main_command
    if command == 0:
        _pulse(executor, MacroActionKind.MOVE, "down", timing.wait_frames)
    elif command == 2:
        _pulse(executor, MacroActionKind.MOVE, "left", timing.wait_frames)
        _pulse(executor, MacroActionKind.MOVE, "down", timing.wait_frames)
    elif command == 3:
        _pulse(executor, MacroActionKind.MOVE, "left", timing.wait_frames)
    elif command != 1:
        raise LavenderChapterError(f"{label} exposed an invalid battle command cursor.")

    selected = reader.read_battle_menu_state(reader.read())
    if selected.phase is not BattleMenuPhase.MAIN or selected.selected_main_command != 1:
        raise LavenderChapterError(f"{label} recovery could not select ITEM.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    _select_bag_item(executor, emulator, ItemId.SUPER_POTION, timing)
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    _select_cursor(executor, emulator, target_index, timing)
    _pulse(executor, MacroActionKind.CONFIRM, frames=240)

    expected_hp = min(before.battler_max_hp, before.battler_hp + 50)
    saw_heal = False
    for _ in range(timing.dialogue_pulses * 3):
        current = reader.read()
        party_hp = _party_hp(emulator)
        if len(party_hp) > target_index and party_hp[target_index] == expected_hp:
            saw_heal = True
        if (
            saw_heal
            and _bag(emulator).get(ItemId.SUPER_POTION, 0) == before_quantity - 1
            and current.battle_state == 2
            and reader.read_battle_menu_state(current).phase is BattleMenuPhase.MAIN
        ):
            run.potions_used += 1
            return
        if (
            current.battle_state != 2
            or len(party_hp) <= target_index
            or party_hp[target_index] <= 0
        ):
            raise LavenderChapterError(f"{label} recovery lost the active battle.")
        _pulse(executor, MacroActionKind.CANCEL, frames=timing.wait_frames)
    raise LavenderChapterError(f"{label} recovery missed its bounded proof.")


def _use_battle_status_item(
    reader: PokemonRedStateReader,
    executor: _CountingExecutor,
    emulator: EmulatorState,
    timing: LavenderTiming,
    label: str,
    *,
    item: ItemId,
    expected_status: int,
) -> None:
    before = reader.read()
    menu = reader.read_battle_menu_state(before)
    target_index = before.active_party_index
    before_quantity = _bag(emulator).get(item, 0)
    if (
        before.battle_state != 2
        or target_index is None
        or before.battler_status != expected_status
        or not expected_status & 0x07
        or before_quantity <= 1
        or menu.phase is not BattleMenuPhase.MAIN
    ):
        raise LavenderChapterError(f"{label} Awakening lacks its stable sleep gate.")

    command = menu.selected_main_command
    if command == 0:
        _pulse(executor, MacroActionKind.MOVE, "down", timing.wait_frames)
    elif command == 2:
        _pulse(executor, MacroActionKind.MOVE, "left", timing.wait_frames)
        _pulse(executor, MacroActionKind.MOVE, "down", timing.wait_frames)
    elif command == 3:
        _pulse(executor, MacroActionKind.MOVE, "left", timing.wait_frames)
    elif command != 1:
        raise LavenderChapterError(f"{label} Awakening exposed an invalid command cursor.")

    selected = reader.read_battle_menu_state(reader.read())
    if selected.phase is not BattleMenuPhase.MAIN or selected.selected_main_command != 1:
        raise LavenderChapterError(f"{label} Awakening could not select ITEM.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    _select_bag_item(executor, emulator, item, timing)
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    _select_cursor(executor, emulator, target_index, timing)
    _pulse(executor, MacroActionKind.CONFIRM, frames=1)

    saw_cure = False
    saw_consumption = False
    for _ in range(timing.dialogue_pulses * 20):
        current = reader.read()
        statuses = _party_status(emulator)
        if len(statuses) > target_index and statuses[target_index] == 0:
            saw_cure = True
        if _bag(emulator).get(item, 0) == before_quantity - 1:
            saw_consumption = True
        if (
            saw_cure
            and saw_consumption
            and current.battle_state == 2
            and reader.read_battle_menu_state(current).phase is BattleMenuPhase.MAIN
        ):
            return
        if current.battle_state != 2 or (current.battler_hp or 0) <= 0:
            raise LavenderChapterError(f"{label} Awakening lost the active battle.")
        _pulse(executor, MacroActionKind.CANCEL, frames=1)
    raise LavenderChapterError(
        f"{label} Awakening missed its bounded cure proof: "
        f"cure={saw_cure}, consumption={saw_consumption}."
    )


def _final_tunnel_pivot_target(
    raw: RawGameState,
    party_hp: tuple[int, ...],
    enabled: bool,
    *,
    dux_unavailable: bool = False,
    required_move_spent: bool = True,
) -> int | None:
    """Assign Grass to DUX and every other final-tunnel matchup to Wartortle."""

    if (
        not enabled
        or not required_move_spent
        or raw.active_party_index is None
        or len(party_hp) < 2
    ):
        return None
    target = (
        0
        if raw.enemy_species_id in FINAL_TUNNEL_GRASS_SPECIES and not dux_unavailable
        else 1
    )
    if target == raw.active_party_index or party_hp[target] <= 0:
        return None
    return target


def _dux_status_escape_target(
    raw: RawGameState,
    party_hp: tuple[int, ...],
    enabled: bool,
) -> int | None:
    """Hand a status-locked DUX matchup to the healthy story lead before it faints."""

    if (
        not enabled
        or raw.active_party_index != 0
        or not (raw.battler_status or 0)
        or len(party_hp) < 2
        or party_hp[1] <= 0
    ):
        return None
    return 1


def _dux_status_recovery_strategy(
    raw: RawGameState,
    party_hp: tuple[int, ...],
    enabled: bool,
    *,
    awakenings: int,
) -> tuple[str, int | None]:
    """Prefer a healthy role pivot before spending the protected Tower reserve."""

    pivot_target = _dux_status_escape_target(raw, party_hp, enabled)
    if pivot_target is not None:
        return "pivot", pivot_target
    if enabled and (raw.battler_status or 0) & 0x07 and awakenings > 1:
        return "awakening", None
    return "none", None


def _prepare_dux_sleep_pivot(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    timing: LavenderTiming,
) -> None:
    """Make the declared reserve healthy before the final sleep-producing trainer."""

    _swap(executor, reader, emulator, DUX, "final tunnel DUX reserve preparation")
    _heal_if_below(
        executor,
        reader,
        emulator,
        run,
        timing,
        0,
        TRAVERSAL_RECOVERY_THRESHOLD,
    )
    _cure_tunnel_status_if_present(executor, reader, emulator, run, timing)
    _swap(executor, reader, emulator, WARTORTLE, "final tunnel Wartortle restoration")


def _trainer(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    route: Iterable[str],
    timing: LavenderTiming,
    label: str,
    map_id: int,
    event: EventFlag,
    opponent: int,
    trainer_class: int,
    trainer_set: int,
    move_id: int,
    move_slot: int,
    battle_plan_id: str,
    *,
    already_triggered: bool = False,
    finish_with_bubblebeam: bool = False,
    protect_dux_status: bool = False,
    battle_recovery_threshold: int | None = None,
    battle_recovery_limit: int | None = None,
) -> None:
    if _event(emulator, event):
        raise LavenderChapterError(f"{label} event was already set.")
    if not already_triggered:
        _move(
            executor,
            reader,
            emulator,
            run,
            route,
            timing,
            label,
            allow_trainer=True,
        )
    battle = _enter_trainer_battle(executor, reader, timing, label)
    identity = (
        emulator.read_u8(RamAddress.CURRENT_OPPONENT),
        emulator.read_u8(RamAddress.TRAINER_CLASS),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_CLASS),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_SET),
    )
    expected_identity = (opponent, trainer_class, opponent, trainer_set)
    if battle.map_id != map_id or identity != expected_identity:
        raise LavenderChapterError(f"{label} identity mismatch: observed {identity!r}.")
    before_pp = battle.first_party_pp
    intent = BattleIntent(
        "reach_lavender",
        battle_plan_id=battle_plan_id,
        resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
        required_move_policy=RequiredMovePolicy.ANY_USABLE,
    )
    final = _run_lavender_trainer_battle(
        reader,
        executor,
        emulator,
        run,
        timing,
        move_slot=move_slot,
        map_id=map_id,
        label=label,
        intent=intent,
        finish_with_bubblebeam=finish_with_bubblebeam,
        protect_dux_status=protect_dux_status,
        battle_recovery_threshold=battle_recovery_threshold,
        battle_recovery_limit=battle_recovery_limit,
    )
    if not _event(emulator, event):
        raise LavenderChapterError(f"{label} did not set event {int(event):#05x}.")
    if before_pp is None or final.first_party_pp is None:
        raise LavenderChapterError(f"{label} lacks PP evidence.")
    spent = (before_pp[move_slot - 1] & 0x3F) - (final.first_party_pp[move_slot - 1] & 0x3F)
    if spent <= 0:
        raise LavenderChapterError(f"{label} did not spend selected-move PP.")
    run.trainers.append(
        TrainerEvidence(
            label,
            int(map_id),
            int(event),
            opponent,
            trainer_class,
            trainer_set,
            move_id,
            spent,
        )
    )


def _move(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    directions: Iterable[str],
    timing: LavenderTiming,
    label: str,
    *,
    allow_trainer: bool = False,
    auto_repel: bool = False,
) -> RawGameState:
    route = tuple(directions)
    state = reader.read()
    history: list[tuple[int | None, int | None, int | None]] = [
        (state.map_id, state.player_x, state.player_y)
    ]
    for step, direction in enumerate(route, 1):
        if auto_repel and emulator.read_u8(RamAddress.REPEL_REMAINING_STEPS) == 0:
            _clear_field_text(executor, reader, timing)
            if _bag(emulator).get(ItemId.REPEL, 0):
                _use_repel(executor, reader, emulator, run, timing)
        before = (state.map_id, state.player_x, state.player_y)
        for attempt in range(timing.movement_retries):
            _pulse(executor, MacroActionKind.MOVE, direction, 12 * (attempt + 1))
            state = reader.read()
            if state.battle_state == 1:
                _flee(executor, reader, emulator, run, timing)
                state = reader.read()
                after = (state.map_id, state.player_x, state.player_y)
                if after != before:
                    history.append(after)
                    break
                continue
            if state.battle_state == 2:
                if allow_trainer and step == len(route):
                    return state
                raise LavenderChapterError(
                    f"Unexpected trainer interrupted {label} at step {step}."
                )
            after = (state.map_id, state.player_x, state.player_y)
            if after != before:
                history.append(after)
                break
            if not reader.read_input_readiness().ready:
                _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
                state = reader.read()
                if state.battle_state == 2 and allow_trainer and step == len(route):
                    return state
        else:
            if allow_trainer and step == len(route):
                return state
            raise LavenderChapterError(
                f"{label} blocked at step {step}: {direction}, "
                f"{(state.map_id, state.player_x, state.player_y)!r}, history={history!r}."
            )
        if (
            state.first_party_hp == 0
            or state.party_species_ids is None
            or sorted(state.party_species_ids) != sorted(PROTECTED_PARTY)
        ):
            raise LavenderChapterError(f"{label} changed the protected lead/party.")
    return state


def _enter_trainer_battle(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: LavenderTiming,
    label: str,
) -> RawGameState:
    for _ in range(timing.dialogue_pulses):
        raw = reader.read()
        if raw.battle_state == 2:
            return raw
        if raw.battle_state == 1:
            raise LavenderChapterError(f"A wild battle replaced {label}.")
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    raise LavenderChapterError(f"{label} did not enter a trainer battle.")


def _flee(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    timing: LavenderTiming,
    *,
    unknown_with_cancel: bool = False,
    allow_purified_zone_heal: bool = False,
) -> None:
    before = reader.read()
    species = before.party_species_ids
    pp = before.first_party_pp
    hp = _party_hp(emulator)
    inventory = _bag(emulator)
    if before.battle_state != 1:
        raise LavenderChapterError("Wild flee requires an active wild battle.")
    if unknown_with_cancel:
        for _ in range(timing.flee_pulses):
            if reader.read().battle_state == 0:
                break
            for kind, value, frames in _normalized_run_actions(timing):
                _pulse(executor, kind, value, frames=frames)
                if reader.read().battle_state == 0:
                    break
        else:
            raise LavenderChapterError("Wild flee could not normalize and select RUN.")
        for _ in range(timing.flee_pulses):
            final = reader.read()
            if final.battle_state == 0 and reader.read_input_readiness().ready:
                _record_wild_flee_evidence(
                    before,
                    final,
                    emulator,
                    run,
                    species,
                    pp,
                    hp,
                    inventory,
                    allow_purified_zone_heal=allow_purified_zone_heal,
                )
                return
            _pulse(executor, MacroActionKind.CANCEL, frames=timing.wait_frames)
        raise LavenderChapterError("Wild flee exceeded its bounded normalized dialogue.")
    for _ in range(timing.flee_pulses):
        raw = reader.read()
        menu = reader.read_battle_menu_state(raw)
        if menu.phase is BattleMenuPhase.UNKNOWN:
            _pulse(
                executor,
                _unknown_flee_action(unknown_with_cancel),
                frames=timing.wait_frames,
            )
            continue
        if menu.phase is BattleMenuPhase.MOVE:
            _pulse(executor, MacroActionKind.CANCEL, frames=timing.wait_frames)
            continue
        command = menu.selected_main_command
        if command == 3:
            break
        direction = {0: "right", 1: "right", 2: "down"}.get(command)
        if direction is None:
            raise LavenderChapterError("Wild flee exposed an invalid main-menu cursor.")
        _pulse(executor, MacroActionKind.MOVE, direction, timing.wait_frames)
    else:
        raise LavenderChapterError("Wild flee could not select RUN.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=240)
    for _ in range(timing.flee_pulses):
        final = reader.read()
        if final.battle_state == 0 and reader.read_input_readiness().ready:
            _record_wild_flee_evidence(
                before,
                final,
                emulator,
                run,
                species,
                pp,
                hp,
                inventory,
                allow_purified_zone_heal=allow_purified_zone_heal,
            )
            return
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    raise LavenderChapterError("Wild flee exceeded its bounded dialogue.")


def _unknown_flee_action(cancel_for_safety: bool) -> MacroActionKind:
    return MacroActionKind.CANCEL if cancel_for_safety else MacroActionKind.CONFIRM


def _normalized_run_actions(
    timing: LavenderTiming,
) -> tuple[tuple[MacroActionKind, str | None, int], ...]:
    return (
        (MacroActionKind.CANCEL, None, timing.wait_frames),
        (MacroActionKind.MOVE, "down", timing.wait_frames),
        (MacroActionKind.MOVE, "right", timing.wait_frames),
        (MacroActionKind.CONFIRM, None, 240),
    )


def _record_wild_flee_evidence(
    before: RawGameState,
    final: RawGameState,
    emulator: EmulatorState,
    run: _RunState,
    species: tuple[int, ...] | None,
    pp: tuple[int, ...] | None,
    hp: tuple[int, int, int],
    inventory: dict[int, int],
    *,
    allow_purified_zone_heal: bool = False,
) -> None:
    party_ok = final.party_species_ids == species
    pp_preserved = final.first_party_pp == pp
    final_hp = _party_hp(emulator)
    hp_preserved = all(
        0 < after <= before_hp for before_hp, after in zip(hp, final_hp, strict=True)
    )
    purified_zone_heal = (
        allow_purified_zone_heal
        and _event(emulator, EventFlag.IN_PURIFIED_ZONE)
        and final_hp == _party_max_hp(emulator)
        and all(status == 0 for status in _party_status(emulator))
    )
    pp_ok = pp_preserved or purified_zone_heal
    hp_safe = hp_preserved or purified_zone_heal
    inventory_ok = _bag(emulator) == inventory
    evidence = WildFleeEvidence(
        int(before.map_id or 0),
        int(before.player_x or 0),
        int(before.player_y or 0),
        int(before.enemy_species_id or 0),
        int(before.enemy_level or 0),
        party_ok,
        pp_ok,
        hp_safe,
        inventory_ok,
    )
    if (
        not party_ok
        or not pp_ok
        or not hp_safe
        or not inventory_ok
        or (final.first_party_hp or 0) <= 0
    ):
        raise LavenderChapterError(
            "Wild flee violated protected state: "
            f"hp={hp!r}->{final_hp!r}, party={party_ok}, "
            f"pp_preserved={pp_preserved}, inventory={inventory_ok}, "
            f"purified_zone_heal={purified_zone_heal}."
        )
    run.wilds.append(evidence)


def _use_repel(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    timing: LavenderTiming,
) -> None:
    before = _bag(emulator).get(ItemId.REPEL, 0)
    if before <= 0 or emulator.read_u8(RamAddress.REPEL_REMAINING_STEPS) != 0:
        raise LavenderChapterError("Repel use lacked an expired effect and carried item.")
    _use_bag_item(executor, reader, emulator, timing, ItemId.REPEL)
    if (
        _bag(emulator).get(ItemId.REPEL, 0) != before - 1
        or emulator.read_u8(RamAddress.REPEL_REMAINING_STEPS) == 0
    ):
        raise LavenderChapterError("Repel did not consume exactly one item and activate.")
    run.repels_used += 1


def _heal_if_below(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    timing: LavenderTiming,
    party_index: int,
    threshold: int,
) -> bool:
    hp = _party_hp(emulator)[party_index]
    max_hp = _party_max_hp(emulator)[party_index]
    if hp <= 0:
        raise LavenderChapterError(f"Recovery target {party_index} has fainted.")
    if hp >= max_hp or hp > threshold:
        return False
    if _bag(emulator).get(ItemId.SUPER_POTION, 0) <= 0:
        if hp > BATTLE_RECOVERY_THRESHOLD:
            return False
        raw = reader.read()
        raise LavenderChapterError(
            f"Recovery target {party_index} is unsafe without a Super Potion: "
            f"{hp}/{max_hp}, map={raw.map_id}, "
            f"position={(raw.player_x, raw.player_y)}, used={run.potions_used}."
        )
    _use_super_potion(executor, reader, emulator, run, timing, party_index)
    return True


def _require_potion_floor(emulator: EmulatorState, minimum: int, label: str) -> None:
    observed = _bag(emulator).get(ItemId.SUPER_POTION, 0)
    if observed < minimum:
        raise LavenderChapterError(
            f"{label} violated its Super Potion floor: observed {observed}, "
            f"expected at least {minimum}."
        )


def _use_super_potion(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    timing: LavenderTiming,
    party_index: int,
) -> None:
    hp_addresses = (
        RamAddress.PARTY_MON_1_HP,
        RamAddress.PARTY_MON_2_HP,
        RamAddress.PARTY_MON_3_HP,
    )
    max_addresses = (
        RamAddress.PARTY_MON_1_MAX_HP,
        RamAddress.PARTY_MON_2_MAX_HP,
        RamAddress.PARTY_MON_3_MAX_HP,
    )
    before_hp = _u16(emulator, hp_addresses[party_index])
    max_hp = _u16(emulator, max_addresses[party_index])
    before_qty = _bag(emulator).get(ItemId.SUPER_POTION, 0)
    if not 0 < before_hp < max_hp or before_qty <= 0:
        raise LavenderChapterError(
            f"Potion target {party_index} lacks damage/item evidence: {before_hp}/{max_hp}."
        )
    _open_bag(executor, emulator, timing)
    _select_bag_item(executor, emulator, ItemId.SUPER_POTION, timing)
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    _pulse(executor, MacroActionKind.CONFIRM, frames=240)
    _select_cursor(executor, emulator, party_index, timing)
    _pulse(executor, MacroActionKind.CONFIRM, frames=240)
    expected = min(max_hp, before_hp + 50)
    for _ in range(timing.dialogue_pulses):
        if (
            _u16(emulator, hp_addresses[party_index]) == expected
            and _bag(emulator).get(ItemId.SUPER_POTION, 0) == before_qty - 1
        ):
            _close_menus(executor, reader, timing)
            run.potions_used += 1
            return
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    raise LavenderChapterError("Super Potion missed its HP/quantity proof.")


def _cure_tunnel_status_if_present(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    timing: LavenderTiming,
) -> None:
    before_status = _party_status(emulator)[0]
    if before_status == 0:
        return
    if before_status & 0x40:
        item = ItemId.PARLYZ_HEAL
        label = "Parlyz Heal"
    elif before_status & 0x08:
        item = ItemId.ANTIDOTE
        label = "Antidote"
    elif before_status & 0x07:
        item = ItemId.AWAKENING
        label = "Awakening"
    else:
        raise LavenderChapterError(
            f"Tunnel lead has an unsupported status condition: {before_status:#04x}."
        )
    before_qty = _bag(emulator).get(item, 0)
    if before_qty < 1:
        raise LavenderChapterError(
            f"{label} gate requires its supported status and a carried item."
        )
    _use_bag_item(executor, reader, emulator, timing, item)
    if _party_status(emulator)[0] != 0 or _bag(emulator).get(item, 0) != before_qty - 1:
        raise LavenderChapterError(f"{label} did not cure the lead and consume exactly once.")
    if item is ItemId.PARLYZ_HEAL:
        run.parlyz_heals_used += 1
    elif item is ItemId.AWAKENING:
        run.awakenings_used += 1


def _use_bag_item(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: LavenderTiming,
    item: int,
) -> None:
    before = _bag(emulator).get(item, 0)
    _open_bag(executor, emulator, timing)
    _select_bag_item(executor, emulator, item, timing)
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    _pulse(executor, MacroActionKind.CONFIRM, frames=240)
    for _ in range(timing.dialogue_pulses):
        if _bag(emulator).get(item, 0) == before - 1:
            _close_menus(executor, reader, timing)
            return
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    raise LavenderChapterError(f"Bag item {int(item):#04x} was not consumed.")


def _teach_tm11(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: LavenderTiming,
) -> None:
    _open_bag(executor, emulator, timing)
    _select_bag_item(executor, emulator, ItemId.TM11_BUBBLEBEAM, timing)
    for _ in range(timing.dialogue_pulses):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (0, 1):
            break
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    else:
        raise LavenderChapterError("TM11 did not reach party selection.")
    _select_cursor(executor, emulator, 0, timing)
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(timing.dialogue_pulses):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (5, 8):
            break
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    else:
        raise LavenderChapterError("TM11 did not reach move deletion.")
    _select_cursor(executor, emulator, 2, timing)
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(timing.dialogue_pulses):
        raw = reader.read()
        if ItemId.TM11_BUBBLEBEAM not in _bag(emulator):
            if raw.first_party_moves == (
                BITE,
                0x27,
                BUBBLEBEAM,
                0x37,
            ):
                _close_menus(executor, reader, timing)
                return
            raise LavenderChapterError(
                f"TM11 was consumed but produced unexpected moves: {raw.first_party_moves!r}."
            )
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    raise LavenderChapterError("TM11 did not replace Bubble and consume the TM.")


def _purchase_supplies(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: LavenderTiming,
    *,
    starting_super_potions: int,
) -> int:
    if starting_super_potions not in {0, 1}:
        raise LavenderChapterError("Invalid starting Super Potion reserve for Mart purchase.")
    money_before = _money(emulator)
    _move(executor, reader, emulator, _RunState([], []), _directions("UUL"), timing, "Mart clerk")
    _pulse(executor, MacroActionKind.MOVE, "left", 60)
    # The expanded early collection needs a larger legal Ball reserve.  Liquidate
    # the Nugget at the first shop where that cash is needed instead of weakening
    # the Rock Tunnel healing and repel contract.
    _sell_single_mart_item(
        executor,
        reader,
        emulator,
        timing,
        ItemId.NUGGET,
        expected_proceeds=NUGGET_SALE_PROCEEDS,
    )
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    _buy_mart_item(
        executor,
        emulator,
        timing,
        absolute_index=1,
        item=ItemId.SUPER_POTION,
        quantity=TUNNEL_SUPER_POTIONS_PURCHASED,
        target_bag_quantity=starting_super_potions + TUNNEL_SUPER_POTIONS_PURCHASED,
    )
    _buy_mart_item(
        executor,
        emulator,
        timing,
        absolute_index=3,
        item=ItemId.AWAKENING,
        quantity=TUNNEL_AWAKENINGS_PURCHASED,
        target_bag_quantity=TUNNEL_AWAKENING_RESERVE,
    )
    _buy_mart_item(
        executor,
        emulator,
        timing,
        absolute_index=4,
        item=ItemId.PARLYZ_HEAL,
        quantity=TUNNEL_PARLYZ_HEALS_PURCHASED,
        target_bag_quantity=TUNNEL_PARLYZ_HEALS_PURCHASED,
    )
    _buy_mart_item(
        executor,
        emulator,
        timing,
        absolute_index=5,
        item=ItemId.REPEL,
        quantity=4,
        target_bag_quantity=4,
    )
    _close_menus(executor, reader, timing)
    money_after = _money(emulator)
    expected_cost = (
        TUNNEL_SUPER_POTIONS_PURCHASED * SUPER_POTION_PRICE
        + TUNNEL_AWAKENINGS_PURCHASED * AWAKENING_PRICE
        + TUNNEL_PARLYZ_HEALS_PURCHASED * PARLYZ_HEAL_PRICE
        + 4 * REPEL_PRICE
    )
    if money_before + NUGGET_SALE_PROCEEDS - money_after != expected_cost:
        raise LavenderChapterError(
            "Mart money gate did not preserve the sale/purchase ledger: "
            f"sale={NUGGET_SALE_PROCEEDS}, cost={expected_cost}, "
            f"before={money_before}, after={money_after}."
        )
    return expected_cost


def _sell_single_mart_item(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: LavenderTiming,
    item: ItemId,
    *,
    expected_proceeds: int,
) -> None:
    """Sell one declared inventory item and prove both sides of the ledger."""

    if _bag(emulator).get(item, 0) != 1:
        raise LavenderChapterError(f"Expected one {item.name} for the declared sale.")
    money_before = _money(emulator)
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    _pulse(executor, MacroActionKind.MOVE, "down", frames=120)
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 1:
        raise LavenderChapterError("Lavender shop did not select SELL.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(24):
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        items = tuple(_bag(emulator))
        if absolute < len(items) and items[absolute] == item:
            break
        _pulse(executor, MacroActionKind.MOVE, "down", frames=120)
    else:
        raise LavenderChapterError(f"Sell list could not select {item.name}.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(timing.dialogue_pulses):
        if _bag(emulator).get(item, 0) == 0:
            _close_menus(executor, reader, timing)
            proceeds = _money(emulator) - money_before
            if proceeds != expected_proceeds:
                raise LavenderChapterError(
                    f"{item.name} sale expected {expected_proceeds}, observed {proceeds}."
                )
            return
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    raise LavenderChapterError(f"Lavender Mart did not sell {item.name}.")


def _top_up_lavender_supplies(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    timing: LavenderTiming,
) -> tuple[int, int, int, int]:
    """Restore the downstream reserve from the observed post-Tunnel inventory."""

    quantity_before = _bag(emulator).get(ItemId.SUPER_POTION, 0)
    if quantity_before > LAVENDER_SUPER_POTION_RESERVE:
        raise LavenderChapterError(
            "Rock Tunnel exceeded the bounded Lavender reserve: "
            f"observed {quantity_before}, expected at most {LAVENDER_SUPER_POTION_RESERVE}."
        )
    quantity = LAVENDER_SUPER_POTION_RESERVE - quantity_before
    parlyz_before = _bag(emulator).get(ItemId.PARLYZ_HEAL, 0)
    parlyz_quantity = 1

    money_before = _money(emulator)
    _move(executor, reader, emulator, run, CENTER_EXIT, timing, "Lavender Center exit")
    _wait(executor, timing.transition_frames)
    _require(reader.read(), MapId.LAVENDER_TOWN, (3, 6), "Lavender Center exterior")
    _move(
        executor,
        reader,
        emulator,
        run,
        LAVENDER_CENTER_TO_MART,
        timing,
        "Lavender Mart",
    )
    _wait(executor, timing.transition_frames)
    _require(reader.read(), MapId.LAVENDER_MART, (3, 7), "Lavender Mart entrance")
    _move(
        executor,
        reader,
        emulator,
        run,
        LAVENDER_MART_TO_CLERK,
        timing,
        "Lavender Mart clerk",
    )
    _pulse(executor, MacroActionKind.MOVE, "left", 60)
    tm28_sale_proceeds = 0
    if _bag(emulator).get(ItemId.TM28_DIG, 0):
        _sell_single_mart_item(
            executor,
            reader,
            emulator,
            timing,
            ItemId.TM28_DIG,
            expected_proceeds=TM28_SALE_PROCEEDS,
        )
        tm28_sale_proceeds = TM28_SALE_PROCEEDS
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    if quantity:
        _buy_mart_item(
            executor,
            emulator,
            timing,
            absolute_index=1,
            item=ItemId.SUPER_POTION,
            quantity=quantity,
            target_bag_quantity=LAVENDER_SUPER_POTION_RESERVE,
        )
    _buy_mart_item(
        executor,
        emulator,
        timing,
        absolute_index=8,
        item=ItemId.PARLYZ_HEAL,
        quantity=parlyz_quantity,
        target_bag_quantity=parlyz_before + parlyz_quantity,
    )
    _close_menus(executor, reader, timing)

    expected_cost = quantity * SUPER_POTION_PRICE + parlyz_quantity * PARLYZ_HEAL_PRICE
    if (
        _money(emulator) != money_before + tm28_sale_proceeds - expected_cost
        or _bag(emulator).get(ItemId.SUPER_POTION, 0) != LAVENDER_SUPER_POTION_RESERVE
        or _bag(emulator).get(ItemId.PARLYZ_HEAL, 0) != parlyz_before + parlyz_quantity
    ):
        raise LavenderChapterError("Lavender Mart top-up missed its inventory/economy proof.")

    _move(
        executor,
        reader,
        emulator,
        run,
        LAVENDER_MART_TO_TOWN,
        timing,
        "Lavender Mart exit",
    )
    _wait(executor, timing.transition_frames)
    _require(reader.read(), MapId.LAVENDER_TOWN, (15, 14), "Lavender Mart exterior")
    _move(
        executor,
        reader,
        emulator,
        run,
        LAVENDER_MART_TO_CENTER,
        timing,
        "Lavender Center return",
    )
    _heal_center(executor, reader, emulator, timing, MapId.LAVENDER_POKECENTER)
    return quantity, parlyz_quantity, expected_cost, tm28_sale_proceeds


def _buy_mart_item(
    executor: _CountingExecutor,
    emulator: EmulatorState,
    timing: LavenderTiming,
    *,
    absolute_index: int,
    item: int,
    quantity: int,
    target_bag_quantity: int,
) -> None:
    for _ in range(12):
        current = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        if current == absolute_index:
            break
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if current < absolute_index else "up",
            120,
        )
    else:
        raise LavenderChapterError(
            f"Mart could not select inventory index {absolute_index}; "
            f"cursor={emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)}, "
            f"scroll={emulator.read_u8(RamAddress.LIST_SCROLL_OFFSET)}, "
            f"max={emulator.read_u8(RamAddress.MAX_MENU_ITEM)}, "
            f"top=({emulator.read_u8(RamAddress.TOP_MENU_ITEM_X)}, "
            f"{emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y)}), "
            f"selected={emulator.read_u8(RamAddress.SHOP_SELECTED_ITEM):#04x}."
        )
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(max(12, quantity + 1)):
        selected = emulator.read_u8(RamAddress.SHOP_SELECTED_ITEM)
        current_quantity = emulator.read_u8(RamAddress.SHOP_QUANTITY)
        if selected == item and current_quantity == quantity:
            break
        if selected != item:
            raise LavenderChapterError(f"Mart selected {selected:#04x}, expected {int(item):#04x}.")
        _pulse(executor, MacroActionKind.MOVE, "up", 120)
    else:
        raise LavenderChapterError(f"Mart quantity selector missed {quantity}.")
    for _ in range(timing.dialogue_pulses):
        if _bag(emulator).get(item, 0) == target_bag_quantity:
            _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
            return
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    raise LavenderChapterError(
        f"Mart did not purchase {quantity} of {int(item):#04x}: "
        f"money={_money(emulator)}, bag={_bag(emulator)!r}, "
        f"selected={emulator.read_u8(RamAddress.SHOP_SELECTED_ITEM):#04x}, "
        f"shop_quantity={emulator.read_u8(RamAddress.SHOP_QUANTITY)}."
    )


def _heal_center(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: LavenderTiming,
    map_id: int,
) -> None:
    _wait(executor, timing.transition_frames)
    raw = reader.read()
    if raw.map_id != map_id:
        raise LavenderChapterError(f"Expected Center map {int(map_id):#04x}, got {raw.map_id!r}.")
    _move(
        executor,
        reader,
        emulator,
        _RunState([], []),
        ("up",) * 4,
        timing,
        "Center nurse",
    )
    for _ in range(9):
        _pulse(executor, MacroActionKind.CONFIRM, frames=240)
    for _ in range(timing.dialogue_pulses):
        if (
            _party_hp(emulator) == _party_max_hp(emulator)
            and all(status == 0 for status in _party_status(emulator))
            and reader.read_input_readiness().ready
        ):
            return
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    raise LavenderChapterError("Pokémon Center did not heal the complete party.")


def _use_cut(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    direction: str,
    timing: LavenderTiming,
) -> None:
    before = emulator.read_u8(RamAddress.TILE_IN_FRONT_OF_PLAYER)
    if before != 0x3D:
        raise LavenderChapterError("Cut lacked a cuttable tree in front.")
    executor.execute(MacroAction(MacroActionKind.OPEN_MENU))
    _wait(executor, timing.wait_frames)
    _select_cursor(executor, emulator, 1, timing)
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    _select_cursor(executor, emulator, 1, timing)
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    _select_cursor(executor, emulator, 0, timing)
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(timing.dialogue_pulses):
        if (
            emulator.read_u8(RamAddress.TILE_IN_FRONT_OF_PLAYER) != 0x3D
            and reader.read_input_readiness().ready
        ):
            break
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    else:
        raise LavenderChapterError("Cut did not clear the tree.")
    _move(
        executor,
        reader,
        emulator,
        _RunState([], []),
        (direction,),
        timing,
        "Cut passage",
    )


def _face_blocked(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    direction: str,
    tile: int,
    timing: LavenderTiming,
    label: str,
) -> None:
    before = reader.read()
    _pulse(executor, MacroActionKind.MOVE, direction, 120)
    after = reader.read()
    if (after.player_x, after.player_y) != (before.player_x, before.player_y) or emulator.read_u8(
        RamAddress.TILE_IN_FRONT_OF_PLAYER
    ) != tile:
        raise LavenderChapterError(f"{label} orientation probe failed.")


def _swap(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    species: int,
    label: str,
) -> None:
    try:
        _swap_party_lead(emulator, executor, reader, species, label)
    except Exception as error:
        raise LavenderChapterError(str(error)) from error


def _open_bag(
    executor: _CountingExecutor,
    emulator: EmulatorState,
    timing: LavenderTiming,
) -> None:
    executor.execute(MacroAction(MacroActionKind.OPEN_MENU))
    _wait(executor, timing.wait_frames)
    _select_cursor(executor, emulator, 2, timing)
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)


def _select_bag_item(
    executor: _CountingExecutor,
    emulator: EmulatorState,
    item: int,
    timing: LavenderTiming,
) -> None:
    for _ in range(24):
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        items = tuple(_bag(emulator))
        if item not in items:
            raise LavenderChapterError(f"Bag item {int(item):#04x} is unavailable.")
        if absolute < len(items) and items[absolute] == item:
            return
        target = items.index(item)
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if absolute < target else "up",
            120,
        )
    raise LavenderChapterError(f"Could not select bag item {int(item):#04x}.")


def _select_cursor(
    executor: _CountingExecutor,
    emulator: EmulatorState,
    target: int,
    timing: LavenderTiming,
) -> None:
    for _ in range(12):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == target:
            return
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if cursor < target else "up",
            min(timing.wait_frames, 120),
        )
    raise LavenderChapterError(f"Menu cursor could not select {target}.")


def _close_menus(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: LavenderTiming,
) -> None:
    # The generic input-ready flags are also true in several field menus, so
    # readiness alone cannot prove that ITEM/party screens were closed.
    for _ in range(4):
        _pulse(executor, MacroActionKind.CANCEL, frames=timing.wait_frames)
    for _ in range(6):
        if reader.read_input_readiness().ready:
            return
        _pulse(executor, MacroActionKind.CANCEL, frames=timing.wait_frames)
    raise LavenderChapterError("Menu closure did not restore field input.")


def _clear_field_text(
    executor: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: LavenderTiming,
) -> None:
    for _ in range(timing.dialogue_pulses):
        raw = reader.read()
        if raw.battle_state == 0 and reader.read_input_readiness().ready:
            return
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    raise LavenderChapterError("Field dialogue did not restore input.")


def _checkpoint(
    records: list[LavenderCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(LavenderCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            LavenderProgress(
                checkpoint_id,
                label,
                len(records),
                LAVENDER_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )


def _require(
    raw: RawGameState,
    map_id: int,
    coordinate: tuple[int, int],
    label: str,
    *,
    party: tuple[int, ...] | None = None,
) -> None:
    if (
        raw.map_id != map_id
        or (raw.player_x, raw.player_y) != coordinate
        or raw.battle_state != 0
        or (party is not None and raw.party_species_ids != party)
    ):
        raise LavenderChapterError(
            f"{label} missed gate: map={raw.map_id!r}, "
            f"coordinate={(raw.player_x, raw.player_y)!r}, battle={raw.battle_state!r}, "
            f"party={raw.party_species_ids!r}."
        )


def _bag(emulator: EmulatorState) -> dict[int, int]:
    return {
        emulator.read_u8(int(RamAddress.BAG_ITEMS) + index * 2): emulator.read_u8(
            int(RamAddress.BAG_ITEMS) + index * 2 + 1
        )
        for index in range(emulator.read_u8(RamAddress.NUM_BAG_ITEMS))
    }


def _money(emulator: EmulatorState) -> int:
    value = 0
    for offset in range(3):
        packed = emulator.read_u8(int(RamAddress.PLAYER_MONEY) + offset)
        high, low = packed >> 4, packed & 0x0F
        if high > 9 or low > 9:
            raise LavenderChapterError(f"Player money contains invalid BCD byte {packed:#04x}.")
        value = value * 100 + high * 10 + low
    return value


def _event(emulator: EmulatorState, event: EventFlag) -> bool:
    value = int(event)
    return bool(emulator.read_u8(int(RamAddress.EVENT_FLAGS) + value // 8) & (1 << (value % 8)))


def _u16(emulator: EmulatorState, address: int) -> int:
    return emulator.read_u8(address) * 0x100 + emulator.read_u8(address + 1)


def _party_size(emulator: EmulatorState) -> int:
    return min(emulator.read_u8(RamAddress.PARTY_COUNT), 6)


def _party_hp(emulator: EmulatorState) -> tuple[int, ...]:
    return tuple(
        _u16(emulator, int(RamAddress.PARTY_MON_1_HP) + index * PARTY_STRUCT_STRIDE)
        for index in range(_party_size(emulator))
    )


def _party_max_hp(emulator: EmulatorState) -> tuple[int, ...]:
    return tuple(
        _u16(emulator, int(RamAddress.PARTY_MON_1_MAX_HP) + index * PARTY_STRUCT_STRIDE)
        for index in range(_party_size(emulator))
    )


def _party_status(emulator: EmulatorState) -> tuple[int, ...]:
    return tuple(
        emulator.read_u8(int(RamAddress.PARTY_MON_1_STATUS) + index * PARTY_STRUCT_STRIDE)
        for index in range(_party_size(emulator))
    )


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
