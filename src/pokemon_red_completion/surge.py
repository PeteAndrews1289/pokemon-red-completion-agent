"""Deterministic HM01-to-Thunder-Badge chapter for pinned Pokémon Red."""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_actions import (
    BattleAction,
    BattleControlRequest,
    recovery_request_matches,
)
from pokemon_red_completion.battle_recovery import (
    ProtectedRecoveryError,
    switch_active_battler,
)
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleRecoveryCapability,
    BattleResourcePolicy,
    BattleRuntimeError,
    RequiredMovePolicy,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.capture import (
    CaptureDirective,
    CaptureObservation,
    CapturePolicy,
    plan_capture,
)
from pokemon_red_completion.collection import CollectionObservation
from pokemon_red_completion.executor import ChapterExecutor, CountingExecutor
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
from pokemon_red_completion.party import PartyObservation, StatusCondition
from pokemon_red_completion.pewter import (
    FOREST_GATE_TO_FOREST_DIRECTIONS,
    FOREST_ROUTE_DIRECTIONS,
    ROUTE_1_TO_VIRIDIAN_DIRECTIONS,
    ROUTE_2_TO_FOREST_GATE_DIRECTIONS,
    VIRIDIAN_TO_ROUTE_2_DIRECTIONS,
)
from pokemon_red_completion.red_acquisition import (
    RedAreaExecutionError,
    RedAreaExecutionPolicy,
    RedAreaExecutionReport,
    run_red_area_survey,
)
from pokemon_red_completion.red_battle_catalog import pokemon_red_move_ref
from pokemon_red_completion.red_collection import (
    red_collection_observation,
    red_internal_species_number,
    red_species_ref,
)
from pokemon_red_completion.red_party import PokemonRedPartyReader
from pokemon_red_completion.red_pc_storage import (
    RedPCStorageError,
    RedPCStorageTiming,
    deposit_party_member,
    open_bills_pc,
)

SURGE_CHECKPOINT_COUNT = 15
SPEAROW_SPECIES_ID = 0x05
SPEAROW_CAPTURE_LEVELS = frozenset({17})
DUX_SPECIES_ID = 0x40
DIGLETT_SPECIES_ID = 0x3B
# A Ground specialist is a development lesson, not a disposable key.  Lower
# level Diglett lineages can legally arrive at Surge with too little bulk to
# survive schedule-dependent Quick Attack sequences even after consuming the
# chapter's complete recovery reserve.  Select from the cave's naturally
# available upper level band so the same capture teaches matchup preparation
# without adding a brittle sacrifice or a trainer-specific menu exception.
DIGLETT_CAPTURE_LEVELS = frozenset({21, 22})
DIGLETT_CAPTURE_THROW_LIMIT = 30
DIGLETT_CAPTURE_HELPER_PARTY_INDEX = 1
DIGLETT_CAPTURE_HELPER_MOVE_INDEX = 0
DIGLETT_SEARCH_SEED_WAIT_FRAMES = 199
WARTORTLE_SPECIES_ID = 0xB3
PIDGEY_SPECIES_ID = 0x24
RATTATA_SPECIES_ID = 0xA5
CATERPIE_SPECIES_ID = 0x7B
METAPOD_SPECIES_ID = 0x7C
KAKUNA_SPECIES_ID = 0x71
PIKACHU_SPECIES_ID = 0x54
COLLECTION_POKE_BALL_TARGET = 30
# The Forest lesson retains six specimens and permits five throws per live
# encounter.  Keep the full predeclared Poké Ball budget instead of treating
# an empirically successful smaller reserve as a resource invariant.
FOREST_POKE_BALL_RESERVE = COLLECTION_POKE_BALL_TARGET
POKE_BALL_PRICE = 200
SURGE_ITEM_SETTLE_PULSES = 720
# Diglett is deliberately the lesson lead here, but it is still a fragile new
# capture.  Restore any missing HP at a stable MAIN boundary so damage carried
# from Voltorb cannot turn Pikachu's priority Quick Attack into a schedule-
# dependent knockout.  The chapter already funds and caps two recoveries.
SURGE_RECOVERY_HP_NUMERATOR = 1
SURGE_RECOVERY_HP_DENOMINATOR = 1
WILD_CAPTURE_THROWS_PER_ENCOUNTER = 5
# Ordinary collection must never spend the unique Master Ball.  Prefer the
# weakest supported ball first so the deterministic route retains stronger
# reserves, while still allowing late-game contexts whose Mart sells only
# Great or Ultra Balls.
WILD_CAPTURE_BALL_PRIORITY = (
    ItemId.POKE_BALL,
    ItemId.GREAT_BALL,
    ItemId.ULTRA_BALL,
)
BALL_THROW_SETTLE_ACTION = MacroActionKind.CANCEL
ROUTE_1_WALKER_APPROACH = (14, 14)
ROUTE_1_WALKER_YIELD = (15, 14)
ROUTE_1_WALKER_SOUTH_APPROACH = (14, 12)
ROUTE_1_WALKER_SOUTH_YIELD = (15, 12)
ROUTE_1_WALKER_CLEAR_ATTEMPTS = 24
ROUTE_1_WALKER_GATES = {
    (ROUTE_1_WALKER_APPROACH, "up"): (ROUTE_1_WALKER_YIELD, (14, 13)),
    (ROUTE_1_WALKER_SOUTH_APPROACH, "down"): (
        ROUTE_1_WALKER_SOUTH_YIELD,
        (14, 13),
    ),
}
VIRIDIAN_FOREST_MAX_SURVEY_LEGS = 256
TACKLE_MOVE_ID = 0x21
GUST_MOVE_ID = 0x10
WILD_CAPTURE_POLICY = CapturePolicy(
    throw_at_or_below_hp_ratio=0.65,
    prefer_status_first=False,
    max_throws=WILD_CAPTURE_THROWS_PER_ENCOUNTER,
)
WILD_CAPTURE_DIRECT_THROW_SPECIES = frozenset({PIKACHU_SPECIES_ID})
WILD_CAPTURE_HIGH_RISK_SPECIES = frozenset({PIKACHU_SPECIES_ID})
WILD_CAPTURE_HIGH_RISK_HELPER_HP_RATIO = 0.75
WILD_CAPTURE_PASSIVE_SPECIES = frozenset({METAPOD_SPECIES_ID, KAKUNA_SPECIES_ID})
WILD_CAPTURE_PASSIVE_POLICY = CapturePolicy(
    throw_at_or_below_hp_ratio=0.30,
    prefer_status_first=False,
    max_throws=WILD_CAPTURE_THROWS_PER_ENCOUNTER,
)
WILD_CAPTURE_MAX_WEAKENING_ATTACKS = 8
WILD_CAPTURE_ADAPTIVE_WEAKENING_CAP = 32
SPEAROW_DIRECT_THROW_LEVEL_FLOOR = 30
SPEAROW_CAPTURE_THROW_LIMIT = 15
CUT_MOVE_ID = 0x0F
DIG_MOVE_ID = 0x5B
LT_SURGE_OPPONENT_ID = 0xEC
LT_SURGE_TRAINER_CLASS_ID = 0x24
LT_SURGE_TRAINER_SET = 1
DUX_NICKNAME = (0x83, 0x94, 0x97, 0x50)
SURGE_BATTLE_INTENT = BattleIntent(
    "defeat_surge",
    battle_plan_id="red.vermilion.lt-surge",
    required_move_policy=RequiredMovePolicy.EXACT_REQUIRED,
    required_move_ref=pokemon_red_move_ref(DIG_MOVE_ID),
    resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
    recovery_capabilities=frozenset({BattleRecoveryCapability.RESTORE_HP}),
)


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "D": "down", "L": "left", "R": "right"}[letter] for letter in value)


CAPTAIN_EXIT = _directions("LDLLLDDD")
SHIP_2F_RETURN = _directions("D" * 6 + "L" * 2 + "D" * 2 + "L" * 31 + "UL" + "U" * 7)
# Leave the 2F stair tile into the open y=7 lane immediately. The y=6
# corridor contains a source-pinned left/right waiter whose timing varies with
# the preceding rival battle; the parallel lane reaches the same x=26 turn
# without racing that moving object.
SHIP_1F_RETURN = _directions("D" + "R" * 24 + "U" * 3 + "R" + "U" * 4)
CITY_TO_CENTER = _directions(
    "RUURRRRRURRRRRR" + "U" * 12 + "L" * 12 + "U" * 5 + "LLUU" + "L" * 5 + "U" * 5
)
CENTER_TO_MART = _directions("DDDD" + "R" * 5 + "DDRR" + "D" * 5 + "R" * 5 + "UU")
VIRIDIAN_TO_MART_DIRECTIONS = _directions("UUUUULUULUUUUUUUURRRRRRRRRRU")
VIRIDIAN_MART_RETURN_DIRECTIONS = _directions("LLLLLLLLLLDDDDDDDDRDDRDDDDD")
VIRIDIAN_TO_CENTER_DIRECTIONS = _directions("UUUUULUULUURRRRU")
VIRIDIAN_CENTER_RETURN_DIRECTIONS = _directions("LLLLDDRDDRDDDDD")
# The shortest vertical line through x=21 crosses the roaming Vermilion NPC's
# measured tile at (21, 7).  Long team-training runs eventually meet a timing
# where repeated UP pulses pin that NPC instead of letting it clear.  The
# cartridge collision map provides an equal-cost parallel lane through x=20;
# enter it below the roaming tile and use the exact inverse on the return leg.
VERMILION_ROUTE_11_TO_CENTER_EXTERIOR = _directions("LL" + "U" * 6 + "L" + "U" * 4 + "L" * 9)
VERMILION_CENTER_TO_ROUTE_11 = _directions("R" * 9 + "D" * 4 + "R" + "D" * 6 + "RR")
VERMILION_PC_TO_NURSE = _directions("LLLLDLLLLDLUULU")
VERMILION_NURSE_TO_EXIT = _directions("DDDDD")


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...

    def press(self, button: str) -> None: ...

    def release(self, button: str) -> None: ...

    def tick(self, frames: int) -> None: ...


class SurgeChapterError(RuntimeError):
    """Raised when the bounded Thunder Badge route misses a semantic gate."""


@dataclass(frozen=True, slots=True)
class SurgeTiming:
    wait_frames: int = 180
    transition_frames: int = 120
    movement_retries: int = 14
    encounter_steps: int = 1800
    encounter_limit: int = 72
    spearow_encounter_steps: int = 3600
    spearow_encounter_limit: int = 192
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
    actions = CountingExecutor(executor)
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
    starting_surge_super_potions = _bag(emulator).get(ItemId.SUPER_POTION, 0)
    if not 0 <= starting_surge_super_potions <= 3:
        raise SurgeChapterError(
            "Vermilion preparation has an unexpected Super Potion surplus: "
            f"{starting_surge_super_potions}."
        )
    surge_super_potion_target = max(2, starting_surge_super_potions)
    _move(actions, reader, _directions("UUL"), timing, "Mart clerk")
    _pulse(actions, MacroActionKind.MOVE, "left", 60)
    _confirm(actions, 4, 180)
    _confirm(actions, 2, 240)
    for _ in range(180):
        quantity = _bag(emulator).get(ItemId.POKE_BALL, 0)
        if quantity == COLLECTION_POKE_BALL_TARGET:
            break
        if not 1 <= quantity < COLLECTION_POKE_BALL_TARGET:
            raise SurgeChapterError(f"Unexpected Poké Ball quantity {quantity}.")
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    else:
        money_bytes = tuple(
            emulator.read_u8(int(RamAddress.PLAYER_MONEY) + offset) for offset in range(3)
        )
        raise SurgeChapterError(
            "Repeated single-ball purchase missed collection reserve: "
            f"target={COLLECTION_POKE_BALL_TARGET}, "
            f"quantity={_bag(emulator).get(ItemId.POKE_BALL, 0)}, "
            f"money_bytes={money_bytes!r}."
        )
    _open_mart_buy_list(actions, emulator, 240)
    if starting_surge_super_potions < surge_super_potion_target:
        _buy_mart_item(
            actions,
            emulator,
            absolute_index=1,
            item=ItemId.SUPER_POTION,
            quantity=surge_super_potion_target - starting_surge_super_potions,
            target_bag_quantity=surge_super_potion_target,
            wait_frames=240,
        )
    _confirm_kind(actions, MacroActionKind.CANCEL, 4, 180)
    raw = reader.read()
    _gate(
        raw,
        _bag(emulator).get(ItemId.POKE_BALL) == COLLECTION_POKE_BALL_TARGET
        and _bag(emulator).get(ItemId.SUPER_POTION) == surge_super_potion_target,
        tracker,
        SurgePhase.BALLS_PURCHASED,
        "balls_purchased",
        f"Purchased {COLLECTION_POKE_BALL_TARGET} Poké Balls and funded recovery",
        records,
        progress,
        emulator,
    )

    _move(actions, reader, _directions("RDDDD" + "R" * 17), timing, "Route 11")
    _require(reader.read(), MapId.ROUTE_11, (0, 6), 0, "Route 11 entry")
    _move_fleeing_wild(
        emulator,
        actions,
        reader,
        _directions("R" * 12),
        timing,
        "Route 11 grass",
    )
    encounter = _find_spearow(emulator, actions, reader, timing)
    _gate(
        encounter,
        encounter.battle_state == 1
        and encounter.enemy_species_id == SPEAROW_SPECIES_ID
        and encounter.enemy_level in SPEAROW_CAPTURE_LEVELS,
        tracker,
        SurgePhase.SPEAROW_ENCOUNTER,
        "spearow_encounter",
        "Found an allowed Route 11 Spearow",
        records,
        progress,
        emulator,
    )
    if (encounter.first_party_level or 0) < SPEAROW_DIRECT_THROW_LEVEL_FLOOR:
        raise SurgeChapterError(
            "Spearow direct-throw lesson requires the staged-development level floor."
        )
    spearow_balls_before = _bag(emulator).get(ItemId.POKE_BALL, 0)
    for _ in range(SPEAROW_CAPTURE_THROW_LIMIT):
        if _throw_ball(emulator, actions, reader):
            break
    else:
        raise SurgeChapterError(
            f"{SPEAROW_CAPTURE_THROW_LIMIT} bounded throws did not capture Spearow."
        )
    raw = reader.read()
    spearow_balls_used = spearow_balls_before - _bag(emulator).get(ItemId.POKE_BALL, 0)
    _gate(
        raw,
        raw.party_species_ids == (WARTORTLE_SPECIES_ID, SPEAROW_SPECIES_ID)
        and 1 <= spearow_balls_used <= SPEAROW_CAPTURE_THROW_LIMIT,
        tracker,
        SurgePhase.SPEAROW_CAPTURED,
        "spearow_captured",
        "Captured Spearow within the bounded direct-throw reserve",
        records,
        progress,
        emulator,
    )
    _heal_after_spearow_capture(emulator, actions, reader, timing)

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

    _run_route_1_collection_detour(emulator, actions, reader, timing)
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
    defeated, dig_attacks, super_potions_used = _run_dig_battle(
        actions, reader, timing, emulator=emulator
    )
    super_potion_used = super_potions_used > 0
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
        and _bag(emulator).get(ItemId.SUPER_POTION, 0)
        == surge_super_potion_target - super_potions_used
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


def _open_mart_buy_list(
    executor: CountingExecutor,
    emulator: EmulatorState,
    wait_frames: int,
) -> None:
    """Settle variable purchase dialogue at the priced item list."""

    for _ in range(8):
        if (
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_X),
            emulator.read_u8(RamAddress.TOP_MENU_ITEM_Y),
        ) == (5, 4):
            return
        _pulse(executor, MacroActionKind.CONFIRM, frames=wait_frames)
    raise SurgeChapterError("Vermilion Mart dialogue did not return to the priced item list.")


def _buy_mart_item(
    executor: CountingExecutor,
    emulator: EmulatorState,
    *,
    absolute_index: int,
    item: int,
    quantity: int,
    target_bag_quantity: int,
    wait_frames: int,
) -> None:
    """Select and buy an exact item quantity from an already-open Mart list."""

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
        raise SurgeChapterError(
            f"Mart could not select inventory index {absolute_index}; "
            f"cursor={emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)}, "
            f"scroll={emulator.read_u8(RamAddress.LIST_SCROLL_OFFSET)}."
        )

    _pulse(executor, MacroActionKind.CONFIRM, frames=wait_frames)
    for _ in range(max(12, quantity + 1)):
        selected = emulator.read_u8(RamAddress.SHOP_SELECTED_ITEM)
        current_quantity = emulator.read_u8(RamAddress.SHOP_QUANTITY)
        if selected == item and current_quantity == quantity:
            break
        if selected != item:
            raise SurgeChapterError(f"Mart selected {selected:#04x}, expected {int(item):#04x}.")
        _pulse(executor, MacroActionKind.MOVE, "up", 120)
    else:
        raise SurgeChapterError(f"Mart quantity selector missed {quantity}.")

    for _ in range(12):
        if _bag(emulator).get(item, 0) == target_bag_quantity:
            _pulse(executor, MacroActionKind.CONFIRM, frames=wait_frames)
            return
        _pulse(executor, MacroActionKind.CONFIRM, frames=wait_frames)
    raise SurgeChapterError(
        f"Mart did not purchase {quantity} of {int(item):#04x}: "
        f"bag={_bag(emulator)!r}, "
        f"selected={emulator.read_u8(RamAddress.SHOP_SELECTED_ITEM):#04x}, "
        f"shop_quantity={emulator.read_u8(RamAddress.SHOP_QUANTITY)}."
    )


def _bag_ids(emulator: EmulatorState) -> set[int]:
    return set(_bag(emulator))


def _money(emulator: EmulatorState) -> int:
    value = 0
    for offset in range(3):
        packed = emulator.read_u8(int(RamAddress.PLAYER_MONEY) + offset)
        high, low = packed >> 4, packed & 0x0F
        if high > 9 or low > 9:
            raise SurgeChapterError(f"Player money contains invalid BCD byte {packed:#04x}.")
        value = value * 100 + high * 10 + low
    return value


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
        raise SurgeChapterError(
            f"{label} missed map/coordinate/battle gate: "
            f"expected={(map_id, *coordinate, battle)!r}, "
            f"actual={(raw.map_id, raw.player_x, raw.player_y, raw.battle_state)!r}."
        )


def _move(
    executor: CountingExecutor,
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
    executor: CountingExecutor,
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
    executor: CountingExecutor, reader: PokemonRedStateReader, target: int
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
            2: {0: "right", 1: "up", 3: "up"},
            3: {0: "right", 1: "right", 2: "down"},
        }
        direction = directions.get(target, {}).get(current)
        if direction is None:
            raise SurgeChapterError("Invalid battle-menu navigation.")
        _pulse(executor, MacroActionKind.MOVE, direction, 120)
    raise SurgeChapterError("Battle menu navigation exceeded its bound.")


def _flee(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    encounter: RawGameState,
) -> None:
    party = encounter.party_species_ids
    pp = encounter.first_party_pp
    attempts = 0
    # Count actual RUN selections, not generic dialogue presses. A failed
    # escape can include several opponent-action text boxes, especially when
    # paralysis and repeated Speed drops make the lead slower than the wild
    # opponent. B is safe while settling because it cannot select a command
    # if MAIN becomes visible between observations.
    for _ in range(128):
        raw = reader.read()
        if raw.battle_state == 0:
            living_hp = raw.party_hp or ((raw.first_party_hp or 0),)
            if (
                raw.party_species_ids != party
                or raw.first_party_pp != pp
                or not any(hp > 0 for hp in living_hp)
            ):
                raise SurgeChapterError("Flee changed protected capture state.")
            return
        if raw.party_species_ids != party or raw.first_party_pp != pp:
            raise SurgeChapterError("Flee changed protected capture state.")
        if (raw.battler_hp or 0) <= 0:
            raw = _force_switch_failed_flee_to_living(emulator, executor, reader, raw)
            if raw.battle_state == 0:
                continue
        menu = reader.read_battle_menu_state(raw)
        if menu.phase is BattleMenuPhase.MAIN:
            if attempts >= 16:
                raise SurgeChapterError("Flee exceeded its bounded RUN attempts.")
            _navigate_main(executor, reader, 3)
            _pulse(executor, MacroActionKind.CONFIRM, frames=240)
            attempts += 1
            continue
        if menu.phase is BattleMenuPhase.MOVE:
            _pulse(executor, MacroActionKind.CANCEL, frames=120)
            continue
        if menu.phase is BattleMenuPhase.UNKNOWN:
            _pulse(executor, MacroActionKind.CANCEL)
            continue
        raise SurgeChapterError("Flee exposed an invalid battle-menu phase.")
    raise SurgeChapterError(
        f"Flee exceeded its bounded transition pulses after {attempts} RUN attempts."
    )


def _force_switch_failed_flee_to_living(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    fainted: RawGameState,
) -> RawGameState:
    """Select a living party member after a failed escape faints the battler."""

    party_hp = fainted.party_hp or ()
    living_index = next((index for index, hp in enumerate(party_hp) if hp > 0), None)
    if living_index is None:
        raise SurgeChapterError("Flee left no living party member.")
    expected_species = fainted.enemy_species_id
    expected_enemy_hp = fainted.enemy_hp
    try:
        switch_active_battler(
            executor,
            reader,
            emulator,
            living_index,
            expected_battle_state=1,
            label="Failed-flee living-member continuation",
            wait_frames=120,
        )
    except ProtectedRecoveryError as error:
        restored = reader.read()
        if restored.battle_state == 0 and any(hp > 0 for hp in (restored.party_hp or ())):
            return restored
        raise SurgeChapterError(
            "Failed-flee shared switch failed: "
            f"cause={error}, battle={restored.battle_state}, "
            f"species={restored.enemy_species_id}, enemy_hp={restored.enemy_hp}, "
            f"party_hp={restored.party_hp}, active={restored.active_party_index}."
        ) from error
    restored = reader.read()
    if (
        restored.battle_state != 1
        or restored.enemy_species_id != expected_species
        or restored.enemy_hp != expected_enemy_hp
        or restored.active_party_index != living_index
        or (restored.battler_hp or 0) <= 0
        or reader.read_battle_menu_state(restored).phase is not BattleMenuPhase.MAIN
    ):
        raise SurgeChapterError(
            "Failed-flee shared switch changed its protected encounter: "
            f"battle={restored.battle_state}, species={restored.enemy_species_id}, "
            f"enemy_hp={restored.enemy_hp}, expected_species={expected_species}, "
            f"expected_enemy_hp={expected_enemy_hp}, party_hp={restored.party_hp}, "
            f"active={restored.active_party_index}."
        )
    return restored


def _find_spearow(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
) -> RawGameState:
    raw = reader.read()
    encounters = 0
    for step in range(timing.spearow_encounter_steps):
        if not raw.battle_state:
            _pulse(executor, MacroActionKind.MOVE, "left" if step % 2 == 0 else "right", 60)
            raw = reader.read()
            continue
        encounters += 1
        if encounters > timing.spearow_encounter_limit:
            break
        if raw.enemy_species_id == SPEAROW_SPECIES_ID and raw.enemy_level in SPEAROW_CAPTURE_LEVELS:
            return raw
        balls = _bag(emulator).get(ItemId.POKE_BALL)
        _flee(emulator, executor, reader, raw)
        if _bag(emulator).get(ItemId.POKE_BALL) != balls:
            raise SurgeChapterError("Non-target flee changed Poké Balls.")
        raw = reader.read()
    raise SurgeChapterError(
        "Spearow search exceeded its bounded encounter budget: "
        f"steps={timing.spearow_encounter_steps}, encounters={encounters}, "
        f"encounter_limit={timing.spearow_encounter_limit}, "
        f"last_species={raw.enemy_species_id}, last_level={raw.enemy_level}."
    )


def _throw_ball(
    emulator: EmulatorState, executor: CountingExecutor, reader: PokemonRedStateReader
) -> bool:
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
            _confirm_kind(executor, MacroActionKind.CANCEL, 3, 180)
            _await_exact_ball_decrement(
                emulator,
                executor,
                before,
                "Capture",
            )
            return True
        if (
            raw.battle_state == 1
            and reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN
        ):
            if (
                raw.enemy_species_id != SPEAROW_SPECIES_ID
                or raw.enemy_level not in SPEAROW_CAPTURE_LEVELS
                or raw.enemy_hp is None
                or raw.enemy_hp <= 0
                or (raw.first_party_hp or 0) <= 0
            ):
                raise SurgeChapterError(
                    "Failed Spearow throw did not preserve its live capture boundary."
                )
            _await_exact_ball_decrement(
                emulator,
                executor,
                before,
                "Failed throw",
            )
            return False
        # B advances battle dialogue without selecting another command if the
        # game crosses the MAIN-menu boundary between observations.  Repeated
        # A presses can otherwise enter ITEM and throw a second ball before the
        # first throw's persistent bag update is observed.
        _pulse(executor, BALL_THROW_SETTLE_ACTION)
    raise SurgeChapterError("Poké Ball throw did not reach a capture or retry boundary.")


def _await_exact_ball_decrement(
    emulator: EmulatorState,
    executor: CountingExecutor,
    before: int,
    label: str,
) -> None:
    """Allow the capture script to synchronize its persistent bag stack."""

    for _ in range(12):
        after = _bag(emulator).get(ItemId.POKE_BALL, 0)
        if after == before - 1:
            return
        if after != before:
            raise SurgeChapterError(
                f"{label} changed Poké Balls by an invalid quantity: {before} -> {after}."
            )
        _pulse(executor, MacroActionKind.CANCEL, frames=180)
    raise SurgeChapterError(f"{label} did not persist exactly one Poké Ball decrement.")


def _heal_after_spearow_capture(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
) -> None:
    """Restore both capture candidates before the damaging Diglett encounter."""

    raw = reader.read()
    if raw.map_id != MapId.ROUTE_11 or raw.player_x is None or raw.player_y != 6:
        raise SurgeChapterError("Post-Spearow recovery lacks its Route 11 boundary.")
    raw = _move_until_map_fleeing_wild(
        emulator,
        executor,
        reader,
        "left",
        MapId.VERMILION_CITY,
        timing,
        "Post-Spearow Vermilion return",
    )
    _wait(executor, timing.transition_frames)
    raw = reader.read() if raw.map_id == MapId.VERMILION_CITY else raw
    if raw.player_x is None or raw.player_y != 14 or raw.player_x < 23:
        raise SurgeChapterError("Post-Spearow return missed the Vermilion east boundary.")
    _move(
        executor,
        reader,
        ("left",) * (raw.player_x - 23),
        timing,
        "Post-Spearow east-boundary normalization",
    )
    _move(
        executor,
        reader,
        VERMILION_ROUTE_11_TO_CENTER_EXTERIOR,
        timing,
        "Post-Spearow Center return",
    )
    _require(reader.read(), MapId.VERMILION_CITY, (11, 4), 0, "Post-Spearow Center exterior")
    _move(executor, reader, ("up",), timing, "Post-Spearow Center entry")
    _wait(executor, timing.transition_frames)
    _require(reader.read(), MapId.VERMILION_POKECENTER, (3, 7), 0, "Post-Spearow Center")
    _move(executor, reader, _directions("UUUU"), timing, "Post-Spearow nurse")
    _confirm(executor, 9, 240)
    healed = reader.read()
    if (
        healed.party_species_ids != (WARTORTLE_SPECIES_ID, SPEAROW_SPECIES_ID)
        or healed.party_hp != healed.party_max_hp
        or any(healed.party_status or ())
    ):
        raise SurgeChapterError("Post-Spearow Center did not restore the capture party.")
    _move(executor, reader, _directions("DDDDD"), timing, "Post-Spearow Center exit")
    _move(
        executor,
        reader,
        VERMILION_CENTER_TO_ROUTE_11,
        timing,
        "Post-Spearow Route 11 return",
    )
    _move_until_map(
        executor,
        reader,
        "right",
        MapId.ROUTE_11,
        timing,
        "Post-Spearow Route 11 entry",
    )
    _wait(executor, timing.transition_frames)
    _move_fleeing_wild(
        emulator,
        executor,
        reader,
        ("right",) * 4,
        timing,
        "Post-Spearow Diglett Cave approach",
    )
    _require(reader.read(), MapId.ROUTE_11, (4, 6), 0, "Post-Spearow recovery boundary")


def _catch_diglett_chapter(
    emulator: EmulatorState,
    executor: CountingExecutor,
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
    rejected_encounters: list[tuple[int | None, int | None]] = []
    bounce_direction: str | None = None
    direction_delta = {
        "up": (0, -1),
        "right": (1, 0),
        "down": (0, 1),
        "left": (-1, 0),
    }
    opposite = {"up": "down", "right": "left", "down": "up", "left": "right"}
    warp_tiles = {(5, 5), (37, 31)}
    for _ in range(timing.encounter_steps):
        if encounter.battle_state == 0:
            directions = (
                (bounce_direction,)
                if bounce_direction is not None
                else ("up", "right", "down", "left")
            )
            moved = False
            for direction in directions:
                if encounter.player_x is None or encounter.player_y is None:
                    raise SurgeChapterError("Diglett search lacks live coordinates.")
                dx, dy = direction_delta[direction]
                if (encounter.player_x + dx, encounter.player_y + dy) in warp_tiles:
                    continue
                before_position = (encounter.player_x, encounter.player_y)
                _pulse(executor, MacroActionKind.MOVE, direction, 60)
                encounter = reader.read()
                if encounter.map_id != MapId.DIGLETTS_CAVE:
                    raise SurgeChapterError("Diglett search crossed an excluded cave warp.")
                if (encounter.player_x, encounter.player_y) != before_position:
                    bounce_direction = opposite[direction]
                    moved = True
                    break
            if not moved:
                bounce_direction = None
                _wait(executor, 60)
                encounter = reader.read()
            continue
        if (
            encounter.enemy_species_id == DIGLETT_SPECIES_ID
            and encounter.enemy_level in DIGLETT_CAPTURE_LEVELS
            and (encounter.enemy_hp or 0) > 0
        ):
            # The level-17 Spearow's first move is Peck.  One bounded hit both
            # lowers the number of balls needed for the later Forest reserve and
            # moves the fragile capture off Wartortle.  Spearow is immune to
            # Diglett's Ground attack; the shared weakening primitive safely
            # abandons a miss or knockout and lets this bounded search find a new
            # source-valid target instead of turning bad RNG into a party wipe.
            prepared = _prepare_diglett_capture_target(
                emulator,
                executor,
                reader,
                encounter,
            )
            if prepared is not None:
                encounter = prepared
                break
            encounter = reader.read()
            bounce_direction = None
            continue
        rejected_encounters.append((encounter.enemy_species_id, encounter.enemy_level))
        _flee(emulator, executor, reader, encounter)
        encounter = reader.read()
    else:
        raise SurgeChapterError(
            "Diglett search exceeded its bounded encounter steps: "
            f"rejected={rejected_encounters!r}, "
            f"position={(encounter.player_x, encounter.player_y)!r}."
        )
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


def _prepare_diglett_capture_target(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    encounter: RawGameState,
) -> RawGameState | None:
    """Apply one safe Peck and retain only the proven live Diglett encounter."""

    if (
        encounter.battle_state != 1
        or encounter.enemy_species_id != DIGLETT_SPECIES_ID
        or encounter.enemy_level not in DIGLETT_CAPTURE_LEVELS
        or (encounter.enemy_hp or 0) <= 0
    ):
        raise SurgeChapterError("Diglett weakening received an invalid encounter.")
    weakened = _weaken_wild_capture_once(
        emulator,
        executor,
        reader,
        DIGLETT_CAPTURE_HELPER_PARTY_INDEX,
        DIGLETT_CAPTURE_HELPER_MOVE_INDEX,
        "Diglett capture",
    )
    current = reader.read()
    if not weakened:
        return None
    if (
        current.battle_state != 1
        or current.enemy_species_id != DIGLETT_SPECIES_ID
        or current.enemy_level not in DIGLETT_CAPTURE_LEVELS
        or (current.enemy_hp or 0) <= 0
        or current.enemy_hp >= encounter.enemy_hp
    ):
        raise SurgeChapterError("Diglett weakening lost its source-valid live target.")
    return current


def _run_route_1_collection_detour(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
) -> None:
    """Acquire Route 1's species, store them, and restore the Gym-tree boundary."""

    _confirm_kind(executor, MacroActionKind.CANCEL, 2, 180)
    _move(executor, reader, _directions("LDDD"), timing, "trade house exit")
    _move(
        executor,
        reader,
        _directions("R" * 8 + "D" + "R" * 5 + "U" + "RRD" + "R" * 14 + "UU"),
        timing,
        "Route 11 cave return",
    )
    _wait(executor, timing.transition_frames)
    raw = reader.read()
    if raw.map_id != MapId.DIGLETTS_CAVE_ROUTE_11:
        raise SurgeChapterError(
            f"Route 2 probe missed the Route 11 gate: map={raw.map_id!r}, "
            f"coordinate={(raw.player_x, raw.player_y)!r}."
        )
    if raw.player_x is None or raw.player_y is None:
        raise SurgeChapterError("Route 2 probe lacks Route 11 gate coordinates.")
    _move(
        executor,
        reader,
        _directions("U" * max(raw.player_y - 4, 0) + "R" * max(4 - raw.player_x, 0)),
        timing,
        "Route 11 cave entry",
    )
    _wait(executor, timing.transition_frames)
    raw = reader.read()
    if raw.map_id != MapId.DIGLETTS_CAVE or raw.player_x is None or raw.player_y is None:
        raise SurgeChapterError(f"Route 2 probe missed Diglett's Cave: {raw!r}")
    cave_route_to_route_2: list[str] = []
    _traverse_cave_to_route_2(
        emulator,
        executor,
        reader,
        timing,
        route_sink=cave_route_to_route_2,
    )
    _wait(executor, timing.transition_frames)
    raw = reader.read()
    if raw.map_id != MapId.DIGLETTS_CAVE_ROUTE_2:
        raise SurgeChapterError(f"Route 2 probe missed its cave house: {raw!r}")
    _move(executor, reader, _directions("LDDD"), timing, "Route 2 cave-house exit")
    _move_until_map(
        executor,
        reader,
        "down",
        MapId.ROUTE_2,
        timing,
        "Route 2 exterior",
    )
    _wait(executor, timing.transition_frames)
    _traverse_route_2_to_viridian(emulator, executor, reader, timing)
    _wait(executor, timing.transition_frames)
    raw = reader.read()
    _require(raw, MapId.VIRIDIAN_CITY, (19, 0), 0, "Route 2 south return")
    _move(
        executor,
        reader,
        ("left", *_inverse_directions(VIRIDIAN_TO_ROUTE_2_DIRECTIONS)),
        timing,
        "Viridian southbound",
    )
    _survey_route_1(emulator, executor, reader, timing)
    _recover_for_viridian_forest(emulator, executor, reader, timing)
    _restock_for_viridian_forest(emulator, executor, reader, timing)
    _run_viridian_forest_collection(emulator, executor, reader, timing)
    _move(
        executor,
        reader,
        VIRIDIAN_TO_ROUTE_2_DIRECTIONS,
        timing,
        "Viridian north return",
    )
    _traverse_route_2_to_cave_house(emulator, executor, reader, timing)
    raw = reader.read()
    if raw.map_id != MapId.DIGLETTS_CAVE_ROUTE_2 or raw.player_x is None or raw.player_y is None:
        raise SurgeChapterError("Route 2 return missed Diglett's Cave house.")
    _move(
        executor,
        reader,
        _directions("U" * max(raw.player_y - 4, 0) + "R" * max(4 - raw.player_x, 0)),
        timing,
        "Route 2 cave re-entry",
    )
    _wait(executor, timing.transition_frames)
    if reader.read().map_id != MapId.DIGLETTS_CAVE:
        raise SurgeChapterError("Route 2 return did not enter Diglett's Cave.")
    _field_dig_to_viridian(emulator, executor, reader, timing)
    _return_from_viridian_to_vermilion(
        emulator,
        executor,
        reader,
        timing,
        cave_route_to_route_2=tuple(cave_route_to_route_2),
    )
    _store_wild_collection_specimens(emulator, executor, reader, timing)
    _move(
        executor,
        reader,
        _directions("DDD" + "R" * 5 + "DDRR" + "D" * 5 + "LLLDDD"),
        timing,
        "Vermilion Center to Gym tree",
    )
    _require(reader.read(), MapId.VERMILION_CITY, (15, 17), 0, "Gym tree detour return")


def _inverse_directions(directions: Iterable[str]) -> tuple[str, ...]:
    opposite = {"up": "down", "down": "up", "left": "right", "right": "left"}
    return tuple(opposite[direction] for direction in reversed(tuple(directions)))


def _survey_route_1(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
) -> RedAreaExecutionReport:
    """Catch and retain Route 1's two wild species through live encounters."""

    live = LiveWildCorridorSurveyExecutor(
        emulator,
        executor,
        reader,
        timing,
        label="Route 1",
        forward_directions=ROUTE_1_TO_VIRIDIAN_DIRECTIONS,
        starting_endpoint="north",
        max_legs=12,
    )
    try:
        report = run_red_area_survey(
            "wild:Route1:grass",
            live,
            policy=RedAreaExecutionPolicy(
                max_actions=2_000,
                max_encounters=72,
                capture_in_requirement_order=True,
            ),
        )
        live.finish_at_starting_endpoint()
    except RedAreaExecutionError as error:
        raise SurgeChapterError(f"Route 1 semantic survey failed: {error}") from error
    if not report.passed or report.captures != 2:
        raise SurgeChapterError(f"Route 1 semantic survey lacked two captures: {report!r}.")
    raw = reader.read()
    if raw.map_id == MapId.ROUTE_1:
        raw = _move_until_map_fleeing_wild(
            emulator,
            executor,
            reader,
            "up",
            MapId.VIRIDIAN_CITY,
            timing,
            "Route 1 north transition",
        )
    if raw.map_id != MapId.VIRIDIAN_CITY or raw.party_species_ids != (
        WARTORTLE_SPECIES_ID,
        DUX_SPECIES_ID,
        DIGLETT_SPECIES_ID,
        PIDGEY_SPECIES_ID,
        RATTATA_SPECIES_ID,
    ):
        raise SurgeChapterError(
            "Route 1 survey missed its Viridian living gate: "
            f"map={raw.map_id!r}, coordinate={(raw.player_x, raw.player_y)!r}, "
            f"party={raw.party_species_ids!r}."
        )
    owned = reader.read_pokedex_state().owned_species
    if not {16, 19} <= owned:
        raise SurgeChapterError(f"Route 1 captures lack Pokédex ownership: {sorted(owned)!r}.")
    return report


def _recover_for_viridian_forest(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
) -> None:
    """Restore the newly caught low-power helpers before the long survey."""

    _require(reader.read(), MapId.VIRIDIAN_CITY, (21, 35), 0, "Route 1 recovery boundary")
    _move(
        executor,
        reader,
        VIRIDIAN_TO_CENTER_DIRECTIONS,
        timing,
        "Viridian Forest helper recovery",
    )
    _wait(executor, timing.transition_frames)
    _require(
        reader.read(),
        MapId.VIRIDIAN_POKECENTER,
        (3, 7),
        0,
        "Viridian Center entry",
    )
    _move(executor, reader, _directions("UUUU"), timing, "Viridian Center nurse")
    _confirm(executor, 9, 240)

    party = PokemonRedPartyReader(emulator).read()
    if any(
        member.hp != member.max_hp or member.status is not StatusCondition.HEALTHY
        for member in party.members
    ):
        raise SurgeChapterError("Viridian Center did not restore the complete capture party.")
    helper_pp: dict[int, int] = {}
    helper_moves = {
        RATTATA_SPECIES_ID: TACKLE_MOVE_ID,
        PIDGEY_SPECIES_ID: GUST_MOVE_ID,
    }
    for member in party.members:
        helper_move = helper_moves.get(member.species_id)
        if helper_move is None:
            continue
        helper_pp[member.species_id] = next(
            (move.current_pp for move in member.moves if move.move_id == helper_move),
            -1,
        )
    if helper_pp != {RATTATA_SPECIES_ID: 35, PIDGEY_SPECIES_ID: 35}:
        raise SurgeChapterError(
            f"Viridian Center missed the capture-helper PP contract: {helper_pp!r}."
        )

    _move(executor, reader, _directions("DDDDD"), timing, "Viridian Center exit")
    _wait(executor, timing.transition_frames)
    _require(
        reader.read(),
        MapId.VIRIDIAN_CITY,
        (23, 26),
        0,
        "Viridian Center exterior",
    )
    _move(
        executor,
        reader,
        VIRIDIAN_CENTER_RETURN_DIRECTIONS,
        timing,
        "Viridian Forest recovery return",
    )
    _require(reader.read(), MapId.VIRIDIAN_CITY, (21, 35), 0, "Forest recovery return")


def _restock_for_viridian_forest(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
) -> None:
    """Use earned cash to restore the empirically qualified Forest reserve."""

    _require(reader.read(), MapId.VIRIDIAN_CITY, (21, 35), 0, "Route 1 reserve boundary")
    starting_balls = _bag(emulator).get(ItemId.POKE_BALL, 0)
    if not 0 <= starting_balls <= COLLECTION_POKE_BALL_TARGET:
        raise SurgeChapterError(
            f"Forest restock received an invalid Poké Ball quantity: {starting_balls}."
        )
    if starting_balls >= FOREST_POKE_BALL_RESERVE:
        return
    purchase_quantity = FOREST_POKE_BALL_RESERVE - starting_balls
    purchase_cost = purchase_quantity * POKE_BALL_PRICE
    money_before = _money(emulator)
    if money_before < purchase_cost:
        raise SurgeChapterError(
            "Forest restock is not funded by the live money ledger: "
            f"money={money_before}, cost={purchase_cost}."
        )

    _move(executor, reader, VIRIDIAN_TO_MART_DIRECTIONS, timing, "Viridian Mart restock")
    _wait(executor, timing.transition_frames)
    _require(reader.read(), MapId.VIRIDIAN_MART, (3, 7), 0, "Viridian Mart entry")
    _move(executor, reader, _directions("UUL"), timing, "Viridian Mart clerk")
    _pulse(executor, MacroActionKind.MOVE, "left", 60)
    _confirm(executor, 4, 180)
    _confirm(executor, 2, 240)
    for _ in range(180):
        quantity = _bag(emulator).get(ItemId.POKE_BALL, 0)
        if quantity == FOREST_POKE_BALL_RESERVE:
            break
        if not starting_balls <= quantity < FOREST_POKE_BALL_RESERVE:
            raise SurgeChapterError(
                f"Viridian restock observed invalid Poké Ball quantity {quantity}."
            )
        _pulse(executor, MacroActionKind.CONFIRM, frames=240)
    else:
        raise SurgeChapterError(
            "Viridian Mart missed the Forest Poké Ball reserve: "
            f"target={FOREST_POKE_BALL_RESERVE}, "
            f"quantity={_bag(emulator).get(ItemId.POKE_BALL, 0)}, "
            f"money={_money(emulator)}."
        )
    if _money(emulator) != money_before - purchase_cost:
        raise SurgeChapterError("Viridian Forest restock missed its exact purchase ledger.")

    _confirm_kind(executor, MacroActionKind.CANCEL, 4, 180)
    _move(executor, reader, _directions("RDDD"), timing, "Viridian Mart exit")
    _wait(executor, timing.transition_frames)
    _require(reader.read(), MapId.VIRIDIAN_CITY, (29, 20), 0, "Viridian Mart exterior")
    _move(
        executor,
        reader,
        VIRIDIAN_MART_RETURN_DIRECTIONS,
        timing,
        "Viridian Forest reserve return",
    )
    _require(reader.read(), MapId.VIRIDIAN_CITY, (21, 35), 0, "Forest reserve return")


def _run_viridian_forest_collection(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
) -> RedAreaExecutionReport:
    """Retain Forest evolution roots and restore Viridian's south boundary."""

    _move_fleeing_wild(
        emulator,
        executor,
        reader,
        VIRIDIAN_TO_ROUTE_2_DIRECTIONS,
        timing,
        "Viridian Forest Route 2 approach",
    )
    _move_fleeing_wild(
        emulator,
        executor,
        reader,
        ROUTE_2_TO_FOREST_GATE_DIRECTIONS,
        timing,
        "Viridian Forest south-gate approach",
    )
    _wait(executor, timing.transition_frames)
    _require(
        reader.read(),
        MapId.VIRIDIAN_FOREST_SOUTH_GATE,
        (4, 7),
        0,
        "Viridian Forest south gate",
    )
    _move(
        executor,
        reader,
        FOREST_GATE_TO_FOREST_DIRECTIONS,
        timing,
        "Viridian Forest entrance",
    )
    _wait(executor, timing.transition_frames)
    raw = reader.read()
    if raw.map_id != MapId.VIRIDIAN_FOREST or raw.player_x not in {16, 17} or raw.player_y != 47:
        raise SurgeChapterError(
            "Viridian Forest collection missed its south entrance: "
            f"map={raw.map_id!r}, coordinate={(raw.player_x, raw.player_y)!r}."
        )

    live = LiveWildCorridorSurveyExecutor(
        emulator,
        executor,
        reader,
        timing,
        label="Viridian Forest",
        forward_directions=FOREST_ROUTE_DIRECTIONS,
        starting_endpoint="south",
        max_legs=VIRIDIAN_FOREST_MAX_SURVEY_LEGS,
    )
    try:
        report = run_red_area_survey(
            "wild:ViridianForest:grass",
            live,
            policy=RedAreaExecutionPolicy(
                max_actions=20_000,
                max_encounters=1_000,
                capture_in_requirement_order=True,
            ),
        )
        live.finish_at_starting_endpoint()
    except RedAreaExecutionError as error:
        raise SurgeChapterError(f"Viridian Forest semantic survey failed: {error}") from error
    if not report.passed or report.captures != 6:
        raise SurgeChapterError(f"Viridian Forest semantic survey lacked six captures: {report!r}.")

    raw = reader.read()
    for _ in range(4):
        if raw.map_id == MapId.VIRIDIAN_FOREST and raw.player_x in {16, 17} and raw.player_y == 47:
            break
        raw = _survey_step(executor, reader, "down", timing, "Viridian Forest endpoint")
        if raw.battle_state:
            live.flee_encounter()
            raw = reader.read()
    else:
        raise SurgeChapterError(
            "Viridian Forest could not normalize its physical south endpoint: "
            f"map={raw.map_id!r}, coordinate={(raw.player_x, raw.player_y)!r}."
        )
    expected_party = (
        WARTORTLE_SPECIES_ID,
        DUX_SPECIES_ID,
        DIGLETT_SPECIES_ID,
        PIDGEY_SPECIES_ID,
        RATTATA_SPECIES_ID,
        CATERPIE_SPECIES_ID,
    )
    if (
        raw.map_id != MapId.VIRIDIAN_FOREST
        or raw.player_x not in {16, 17}
        or raw.player_y != 47
        or raw.party_species_ids != expected_party
    ):
        raise SurgeChapterError(
            "Viridian Forest survey missed its south living gate: "
            f"map={raw.map_id!r}, coordinate={(raw.player_x, raw.player_y)!r}, "
            f"party={raw.party_species_ids!r}."
        )
    owned = reader.read_pokedex_state().owned_species
    if not {10, 11, 14, 25} <= owned:
        raise SurgeChapterError(
            f"Viridian Forest captures lack Pokédex ownership: {sorted(owned)!r}."
        )

    # The south warp is not directionally symmetric: entering the Forest consumes
    # the gate's final north step, while returning materializes at the top of the
    # gate.  Normalize each side from live coordinates instead of replaying the
    # inverse entrance trace and assuming the warp consumed an ordinary tile.
    if raw.player_x == 16:
        raw = _survey_step(
            executor,
            reader,
            "right",
            timing,
            "Viridian Forest south-door column",
        )
        if raw.battle_state:
            live.flee_encounter()
            raw = reader.read()
    if raw.map_id != MapId.VIRIDIAN_FOREST or (raw.player_x, raw.player_y) != (17, 47):
        raise SurgeChapterError(
            "Viridian Forest could not align with its south door: "
            f"map={raw.map_id!r}, coordinate={(raw.player_x, raw.player_y)!r}."
        )
    raw = _move_until_map_fleeing_wild(
        emulator,
        executor,
        reader,
        "down",
        MapId.VIRIDIAN_FOREST_SOUTH_GATE,
        timing,
        "Viridian Forest south exit",
    )
    _wait(executor, timing.transition_frames)
    raw = reader.read()
    if raw.player_x is None or raw.player_y is None:
        raise SurgeChapterError("Viridian Forest return gate lacks live coordinates.")
    gate_directions = (
        *(("left",) * max(0, raw.player_x - 4)),
        *(("right",) * max(0, 4 - raw.player_x)),
        *(("down",) * max(0, 7 - raw.player_y)),
        *(("up",) * max(0, raw.player_y - 7)),
    )
    raw = _move(
        executor,
        reader,
        gate_directions,
        timing,
        "Viridian Forest return-gate normalization",
    )
    _require(
        raw,
        MapId.VIRIDIAN_FOREST_SOUTH_GATE,
        (4, 7),
        0,
        "Viridian Forest return gate",
    )
    _move_fleeing_wild(
        emulator,
        executor,
        reader,
        _inverse_directions(ROUTE_2_TO_FOREST_GATE_DIRECTIONS),
        timing,
        "Viridian Forest Route 2 return",
    )
    _move_fleeing_wild(
        emulator,
        executor,
        reader,
        _inverse_directions(VIRIDIAN_TO_ROUTE_2_DIRECTIONS),
        timing,
        "Viridian Forest Viridian return",
        stop_at_map=MapId.VIRIDIAN_CITY,
    )
    _wait(executor, timing.transition_frames)
    raw = reader.read()
    if (
        raw.map_id != MapId.VIRIDIAN_CITY
        or raw.player_x is None
        or raw.player_y is None
        or raw.player_x > 19
        or raw.player_y > 2
    ):
        raise SurgeChapterError(
            "Viridian Forest return missed the settled north boundary: "
            f"map={raw.map_id!r}, coordinate={(raw.player_x, raw.player_y)!r}."
        )
    raw = _move(
        executor,
        reader,
        (
            *(("down",) * (2 - raw.player_y)),
            *(("right",) * (19 - raw.player_x)),
        ),
        timing,
        "Viridian north-boundary normalization",
    )
    _require(raw, MapId.VIRIDIAN_CITY, (19, 2), 0, "Viridian north route column")
    raw = _move(
        executor,
        reader,
        _directions("D" * 26 + "R" + "DD" + "R" + "D" * 5),
        timing,
        "Viridian south-boundary restoration",
    )
    _require(raw, MapId.VIRIDIAN_CITY, (21, 35), 0, "Viridian south-boundary restoration")
    return report


def _move_fleeing_wild(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    directions: Iterable[str],
    timing: SurgeTiming,
    label: str,
    *,
    stop_at_map: int | None = None,
) -> RawGameState:
    """Follow a known corridor while safely dismissing incidental encounters.

    A map terminal may end the trace early because Generation I door and edge
    warps do not consume movement symmetrically in both directions.
    """

    pending = deque(directions)
    raw = reader.read()
    maximum_attempts = len(pending) + timing.encounter_limit
    for _ in range(maximum_attempts):
        if stop_at_map is not None and raw.map_id == stop_at_map:
            return raw
        if not pending:
            if stop_at_map is not None:
                raise SurgeChapterError(f"{label} missed map {stop_at_map:#04x}.")
            return raw
        before = reader.read()
        direction = pending[0]
        raw = _survey_step(executor, reader, direction, timing, label)
        if raw.map_id != before.map_id or (raw.player_x, raw.player_y) != (
            before.player_x,
            before.player_y,
        ):
            pending.popleft()
        if raw.battle_state:
            balls = _bag(emulator).get(ItemId.POKE_BALL, 0)
            _flee(emulator, executor, reader, raw)
            if _bag(emulator).get(ItemId.POKE_BALL, 0) != balls:
                raise SurgeChapterError(f"{label} flee changed Poké Balls.")
            raw = reader.read()
        if stop_at_map is not None and raw.map_id == stop_at_map:
            return raw
    if stop_at_map is not None:
        raise SurgeChapterError(f"{label} missed map {stop_at_map:#04x}.")
    raise SurgeChapterError(f"{label} exceeded its movement/encounter bound.")


def _move_until_map_fleeing_wild(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    direction: str,
    target_map: int,
    timing: SurgeTiming,
    label: str,
) -> RawGameState:
    """Reach an adjacent map while dismissing encounters on the boundary tiles."""

    for _ in range(24):
        raw = reader.read()
        if raw.map_id == target_map:
            return raw
        raw = _survey_step(executor, reader, direction, timing, label)
        if raw.battle_state:
            balls = _bag(emulator).get(ItemId.POKE_BALL, 0)
            _flee(emulator, executor, reader, raw)
            if _bag(emulator).get(ItemId.POKE_BALL, 0) != balls:
                raise SurgeChapterError(f"{label} flee changed Poké Balls.")
    raise SurgeChapterError(f"{label} missed map {target_map:#04x}.")


def _wild_capture_policy(species_id: int) -> CapturePolicy:
    """Use deeper, repeatable weakening only against passive cocoon targets."""

    return (
        WILD_CAPTURE_PASSIVE_POLICY
        if species_id in WILD_CAPTURE_PASSIVE_SPECIES
        else WILD_CAPTURE_POLICY
    )


def _wild_capture_weakening_budget(
    species_id: int,
    current_hp: int,
    maximum_hp: int,
) -> int:
    """Bound attempts by the observed damage needed at one HP per landed hit."""

    if type(current_hp) is not int or type(maximum_hp) is not int:
        raise TypeError("wild capture HP must be integers")
    if maximum_hp <= 0 or not 0 < current_hp <= maximum_hp:
        raise ValueError("wild capture HP must describe a living target")
    policy = _wild_capture_policy(species_id)
    target_hp = int(maximum_hp * policy.throw_at_or_below_hp_ratio)
    minimum_landed_hits = max(0, current_hp - target_hp)
    return min(
        WILD_CAPTURE_ADAPTIVE_WEAKENING_CAP,
        max(WILD_CAPTURE_MAX_WEAKENING_ATTACKS, minimum_landed_hits),
    )


def _weakening_attack_allowed(
    directive: CaptureDirective,
    *,
    attacks_completed: int,
    attack_budget: int,
) -> bool:
    """Allow a terminal replan after the final budgeted weakening attack."""

    if directive is not CaptureDirective.WEAKEN_TARGET:
        return False
    if attacks_completed >= attack_budget:
        raise RedAreaExecutionError("capture still requires weakening after its attack budget")
    return True


def _wild_weakening_settle_action(
    phase: BattleMenuPhase,
    pulse_index: int,
) -> MacroActionKind:
    """Advance one attack result without confirming a stale move selection."""

    if phase is BattleMenuPhase.MOVE:
        return MacroActionKind.CANCEL
    return MacroActionKind.CANCEL if (pulse_index + 1) % 4 == 0 else MacroActionKind.CONFIRM


def _wild_weakening_turn_result(
    *,
    expected_species_id: int,
    before_enemy_hp: int,
    current_species_id: int | None,
    current_enemy_hp: int | None,
    pp_spent: bool,
    phase: BattleMenuPhase,
) -> bool | None:
    """Return hit/miss after one selected move settles, or None while pending."""

    if (
        current_species_id != expected_species_id
        or current_enemy_hp is None
        or current_enemy_hp <= 0
        or not pp_spent
        or phase is not BattleMenuPhase.MAIN
    ):
        return None
    return current_enemy_hp < before_enemy_hp


class LiveWildCorridorSurveyExecutor:
    """Bind a reversible two-endpoint wild corridor to the shared area loop."""

    def __init__(
        self,
        emulator: EmulatorState,
        executor: CountingExecutor,
        reader: PokemonRedStateReader,
        timing: SurgeTiming,
        *,
        label: str,
        forward_directions: tuple[str, ...],
        starting_endpoint: str,
        max_legs: int,
    ) -> None:
        if not label.strip():
            raise ValueError("live wild corridor label must not be empty")
        if not forward_directions:
            raise ValueError("live wild corridor requires movement directions")
        if starting_endpoint not in {"south", "north"}:
            raise ValueError("starting_endpoint must be south or north")
        if type(max_legs) is not int or max_legs <= 0:
            raise ValueError("max_legs must be a positive integer")
        self._emulator = emulator
        self._executor = executor
        self._reader = reader
        self._timing = timing
        self._label = label
        self._forward_directions = forward_directions
        self._starting_endpoint = starting_endpoint
        self._max_legs = max_legs
        self._party_reader = PokemonRedPartyReader(emulator)
        self._endpoint = starting_endpoint
        self._directions: deque[str] = deque()
        self._completed_legs = 0

    def read_collection(self) -> CollectionObservation:
        return red_collection_observation(
            self._reader.read_pokedex_state(),
            self._party_reader.read(),
            self._reader.read_all_box_states(),
        )

    def encountered_species_ref(self) -> str | None:
        raw = self._reader.read()
        if not raw.battle_state:
            return None
        if raw.enemy_species_id is None:
            raise RedAreaExecutionError(f"{self._label} battle lacks an enemy species")
        try:
            return red_species_ref(red_internal_species_number(raw.enemy_species_id))
        except ValueError as error:
            raise RedAreaExecutionError(
                f"{self._label} battle exposed invalid species {raw.enemy_species_id:#04x}"
            ) from error

    def seek_encounter(self) -> None:
        if self.encountered_species_ref() is not None:
            raise RedAreaExecutionError(f"{self._label} cannot seek during an encounter")
        if not self._directions:
            self._start_leg()
        self._advance_one_direction()

    def capture_encounter(self, species_ref: str) -> bool:
        encountered = self.encountered_species_ref()
        if encountered != species_ref:
            raise RedAreaExecutionError(
                f"{self._label} capture expected {species_ref}, encountered {encountered}"
            )
        raw = self._reader.read()
        if raw.enemy_species_id is None:
            raise RedAreaExecutionError(f"{self._label} capture lacks an enemy species")
        policy = _wild_capture_policy(raw.enemy_species_id)
        if raw.enemy_hp is None or raw.enemy_max_hp is None:
            raise RedAreaExecutionError(f"{self._label} capture lacks enemy HP evidence")
        weakening_budget = _wild_capture_weakening_budget(
            raw.enemy_species_id,
            raw.enemy_hp,
            raw.enemy_max_hp,
        )
        for weakening_attacks in range(weakening_budget + 1):
            raw = self._reader.read()
            party = self._party_reader.read()
            helper = (
                None
                if raw.enemy_species_id in WILD_CAPTURE_DIRECT_THROW_SPECIES
                else _select_wild_capture_helper(
                    party,
                    minimum_hp_ratio=(
                        WILD_CAPTURE_HIGH_RISK_HELPER_HP_RATIO
                        if raw.enemy_species_id in WILD_CAPTURE_HIGH_RISK_SPECIES
                        else WILD_CAPTURE_POLICY.retreat_hp_ratio
                    ),
                )
            )
            if helper is None or raw.enemy_hp is None or raw.enemy_max_hp is None:
                break
            helper_index, move_index = helper
            collection = self.read_collection()
            decision = plan_capture(
                CaptureObservation(
                    target_species_id=raw.enemy_species_id,
                    target_level=raw.enemy_level or 1,
                    target_hp=raw.enemy_hp,
                    target_max_hp=raw.enemy_max_hp,
                    catcher=party.members[helper_index],
                    balls_available=_ordinary_capture_ball_total(_bag(self._emulator)),
                    party_has_room=party.is_incomplete,
                    storage_has_room=any(
                        count < collection.box_capacity for count in collection.box_counts
                    ),
                ),
                policy,
            )
            try:
                attack_allowed = _weakening_attack_allowed(
                    decision.directive,
                    attacks_completed=weakening_attacks,
                    attack_budget=weakening_budget,
                )
            except RedAreaExecutionError as error:
                raise RedAreaExecutionError(
                    f"{self._label} exceeded its bounded weakening attack budget"
                ) from error
            if not attack_allowed:
                break
            if not _weaken_wild_capture_once(
                self._emulator,
                self._executor,
                self._reader,
                helper_index,
                move_index,
                self._label,
            ):
                return False
        return _try_catch_wild(
            self._emulator,
            self._executor,
            self._reader,
            raw.enemy_species_id,
            self._label,
            max_throws=WILD_CAPTURE_THROWS_PER_ENCOUNTER,
        )

    def flee_encounter(self) -> None:
        raw = self._reader.read()
        if not raw.battle_state:
            raise RedAreaExecutionError(f"{self._label} cannot flee without an encounter")
        balls = _ordinary_capture_ball_inventory(_bag(self._emulator))
        _flee(self._emulator, self._executor, self._reader, raw)
        if _ordinary_capture_ball_inventory(_bag(self._emulator)) != balls:
            raise RedAreaExecutionError(f"{self._label} flee changed ordinary capture balls")

    def switch_box(self, box_index: int) -> None:
        raise RedAreaExecutionError(
            f"{self._label} cannot switch to box {box_index} without leaving the source"
        )

    def finish_at_starting_endpoint(self) -> None:
        """Normalize an early successful stop to the corridor's starting end."""

        maximum_attempts = len(self._forward_directions) * 2 + 240
        for _ in range(maximum_attempts):
            if not self._directions and self._endpoint == self._starting_endpoint:
                return
            if not self._directions:
                self._start_leg()
            raw = self._advance_one_direction()
            if raw.battle_state:
                self.flee_encounter()
        raise RedAreaExecutionError(f"{self._label} could not normalize to its starting endpoint")

    def _start_leg(self) -> None:
        if self._completed_legs >= self._max_legs:
            raise RedAreaExecutionError(
                f"{self._label} exceeded {self._max_legs} bounded survey legs"
            )
        directions = (
            _inverse_directions(self._forward_directions)
            if self._endpoint == "north"
            else self._forward_directions
        )
        self._directions.extend(directions)

    def _advance_one_direction(self) -> RawGameState:
        """Consume a route step only when its tile movement actually completed."""

        before = self._reader.read()
        direction = self._directions[0]
        try:
            raw = _survey_step(
                self._executor,
                self._reader,
                direction,
                self._timing,
                self._label,
            )
        except SurgeChapterError:
            if not _is_route_1_walker_gate(self._label, before, direction):
                raise
            raw = self._yield_to_route_1_walker(direction)
        moved = raw.map_id != before.map_id or (raw.player_x, raw.player_y) != (
            before.player_x,
            before.player_y,
        )
        if moved:
            self._directions.popleft()
            if not self._directions:
                self._endpoint = "south" if self._endpoint == "north" else "north"
                self._completed_legs += 1
        elif not raw.battle_state:
            raise RedAreaExecutionError(
                f"{self._label} route step neither moved nor entered battle"
            )
        return raw

    def _yield_to_route_1_walker(self, crossing_direction: str) -> RawGameState:
        """Create room for Route 1's horizontal youngster, then retry crossing."""

        for attempt in range(ROUTE_1_WALKER_CLEAR_ATTEMPTS):
            state = self._reader.read()
            gate = ROUTE_1_WALKER_GATES.get(((state.player_x, state.player_y), crossing_direction))
            if state.map_id != MapId.ROUTE_1 or state.battle_state != 0 or gate is None:
                raise SurgeChapterError("Route 1 walker recovery left its bounded approach gate.")
            yield_position, crossed_position = gate

            yielded = _survey_step(
                self._executor,
                self._reader,
                "right",
                self._timing,
                "Route 1 walker yield",
            )
            if yielded.battle_state:
                self.flee_encounter()
                yielded = self._reader.read()
            if (yielded.player_x, yielded.player_y) != yield_position:
                raise SurgeChapterError("Route 1 walker recovery could not yield east.")

            _wait(
                self._executor,
                max(1, self._timing.wait_frames // 4) * (attempt + 1),
            )
            returned = _survey_step(
                self._executor,
                self._reader,
                "left",
                self._timing,
                "Route 1 walker return",
            )
            if returned.battle_state:
                self.flee_encounter()
                returned = self._reader.read()
            if (returned.player_x, returned.player_y) != (
                state.player_x,
                state.player_y,
            ):
                raise SurgeChapterError("Route 1 walker recovery could not restore its approach.")

            try:
                crossed = _survey_step(
                    self._executor,
                    self._reader,
                    crossing_direction,
                    self._timing,
                    "Route 1 walker crossing",
                )
                if (crossed.player_x, crossed.player_y) != crossed_position:
                    raise SurgeChapterError(
                        "Route 1 walker recovery crossed to an unexpected tile."
                    )
                return crossed
            except SurgeChapterError:
                continue
        raise SurgeChapterError("Route 1 youngster did not clear within its bounded retries.")


def _is_route_1_walker_gate(
    label: str,
    state: RawGameState,
    direction: str,
) -> bool:
    """Recognize only the source-defined Route 1 youngster crossing."""

    return (
        label == "Route 1"
        and state.map_id == MapId.ROUTE_1
        and state.battle_state == 0
        and ((state.player_x, state.player_y), direction) in ROUTE_1_WALKER_GATES
    )


def _survey_step(
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    direction: str,
    timing: SurgeTiming,
    label: str,
) -> RawGameState:
    before = reader.read()
    for attempt in range(timing.movement_retries):
        _pulse(executor, MacroActionKind.MOVE, direction, 12 * (attempt + 1))
        raw = reader.read()
        if (
            raw.battle_state
            or raw.map_id != before.map_id
            or (raw.player_x, raw.player_y) != (before.player_x, before.player_y)
        ):
            return raw
    raise SurgeChapterError(
        f"{label} survey blocked moving {direction} at "
        f"{(before.map_id, before.player_x, before.player_y)!r}."
    )


def _select_wild_capture_helper(
    party: PartyObservation,
    *,
    minimum_hp_ratio: float = WILD_CAPTURE_POLICY.retreat_hp_ratio,
) -> tuple[int, int] | None:
    """Choose a low-level adapter-specific weakening move for a wild capture."""

    if not 0 < minimum_hp_ratio < 1:
        raise ValueError("minimum_hp_ratio must be between zero and one")

    move_preferences = {
        RATTATA_SPECIES_ID: (TACKLE_MOVE_ID,),
        CATERPIE_SPECIES_ID: (TACKLE_MOVE_ID,),
        PIDGEY_SPECIES_ID: (GUST_MOVE_ID,),
    }
    species_order = {
        RATTATA_SPECIES_ID: 0,
        CATERPIE_SPECIES_ID: 1,
        PIDGEY_SPECIES_ID: 2,
    }
    candidates: list[tuple[int, int, int, int]] = []
    for party_index, member in enumerate(party.members):
        preferred_moves = move_preferences.get(member.species_id)
        if (
            preferred_moves is None
            or member.status is not StatusCondition.HEALTHY
            or member.hp_ratio <= minimum_hp_ratio
        ):
            continue
        for move_index, move in enumerate(member.moves):
            if move.move_id in preferred_moves and move.is_usable:
                candidates.append(
                    (
                        species_order[member.species_id],
                        member.level,
                        party_index,
                        move_index,
                    )
                )
                break
    if not candidates:
        return None
    _, _, party_index, move_index = min(candidates)
    return party_index, move_index


def _switch_wild_capture_party_slot(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    party_index: int,
    expected_species_id: int,
    expected_enemy_hp: int,
    label: str,
) -> RawGameState:
    """Switch wild-battle battlers without changing the protected target."""

    _navigate_main(executor, reader, 2)
    before = reader.read()
    party = before.party_species_ids
    if (
        before.battle_state != 1
        or before.enemy_species_id != expected_species_id
        or before.enemy_hp != expected_enemy_hp
        or party is None
        or not 0 <= party_index < len(party)
        or reader.read_battle_menu_state(before).phase is not BattleMenuPhase.MAIN
    ):
        raise SurgeChapterError(f"{label} switch lacks a stable wild MAIN gate.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=120)
    for _ in range(12):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == party_index:
            break
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if cursor < party_index else "up",
            120,
        )
    else:
        raise SurgeChapterError(f"{label} could not select party slot {party_index + 1}.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=120)
    for _ in range(6):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == 0:
            break
        _pulse(executor, MacroActionKind.MOVE, "up", 120)
    else:
        raise SurgeChapterError(f"{label} party submenu did not select SWITCH.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=240)
    for pulse in range(48):
        switched = reader.read()
        if (
            switched.battle_state == 1
            and switched.enemy_species_id == expected_species_id
            and switched.enemy_hp == expected_enemy_hp
            and switched.active_party_index == party_index
            and (switched.battler_hp or 0) > 0
            and reader.read_battle_menu_state(switched).phase is BattleMenuPhase.MAIN
        ):
            return switched
        if switched.battle_state != 1:
            raise SurgeChapterError(f"{label} lost its encounter during switching.")
        if (switched.battler_hp or 0) <= 0:
            protected_index = next(
                (index for index, hp in enumerate(switched.party_hp or ()) if hp > 0),
                None,
            )
            if protected_index is None:
                raise SurgeChapterError(f"{label} switching left no living catcher.")
            return _force_switch_wild_capture_to_lead(
                emulator,
                executor,
                reader,
                expected_species_id,
                expected_enemy_hp,
                label,
                party_index=protected_index,
            )
        _pulse(
            executor,
            MacroActionKind.CANCEL if (pulse + 1) % 4 == 0 else MacroActionKind.CONFIRM,
            frames=120,
        )
    raise SurgeChapterError(f"{label} party switch did not return to MAIN.")


def _wild_menu_cursor_address(emulator: EmulatorState) -> int:
    address = emulator.read_u8(RamAddress.MENU_CURSOR_LOCATION)
    address |= emulator.read_u8(int(RamAddress.MENU_CURSOR_LOCATION) + 1) << 8
    return address


def _wild_menu_cursor_active(emulator: EmulatorState) -> bool:
    address = _wild_menu_cursor_address(emulator)
    tile_map = int(RamAddress.TILE_MAP)
    return tile_map <= address < tile_map + 360 and emulator.read_u8(address) == 0xED


def _force_switch_wild_capture_to_lead(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    expected_species_id: int,
    expected_enemy_hp: int,
    label: str,
    *,
    party_index: int = 0,
) -> RawGameState:
    """Recover a fainted helper through the mandatory party selection."""

    party_size = len(reader.read().party_species_ids or ())
    if not 0 <= party_index < party_size:
        raise SurgeChapterError(f"{label} protected party index is invalid.")
    try:
        switch_active_battler(
            executor,
            reader,
            emulator,
            party_index,
            expected_battle_state=1,
            label=f"{label} forced living-member continuation",
            wait_frames=120,
        )
    except ProtectedRecoveryError as error:
        raise SurgeChapterError(f"{label} shared forced switch failed: {error}") from error
    restored = reader.read()
    if (
        restored.battle_state != 1
        or restored.enemy_species_id != expected_species_id
        or restored.enemy_hp != expected_enemy_hp
        or restored.active_party_index != party_index
        or (restored.battler_hp or 0) <= 0
        or reader.read_battle_menu_state(restored).phase is not BattleMenuPhase.MAIN
    ):
        raise SurgeChapterError(f"{label} shared forced switch changed its protected target.")
    return restored


def _weaken_wild_capture_once(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    party_index: int,
    move_index: int,
    label: str,
) -> bool:
    """Switch to a qualified helper and attempt exactly one weakening attack."""

    initial = reader.read()
    initial_party = initial.party_species_ids
    if (
        initial.battle_state != 1
        or initial.enemy_species_id is None
        or initial.enemy_hp is None
        or initial.enemy_hp <= 0
        or initial_party is None
        or not 0 <= party_index < len(initial_party)
        or not 0 <= move_index < 4
    ):
        raise SurgeChapterError(f"{label} weakening lacks a coherent wild encounter.")

    before = _switch_wild_capture_party_slot(
        emulator,
        executor,
        reader,
        party_index,
        initial.enemy_species_id,
        initial.enemy_hp,
        f"{label} helper",
    )
    before_party = before.party_species_ids
    before_enemy_hp = before.enemy_hp
    if (
        before.battle_state != 1
        or before.enemy_species_id != initial.enemy_species_id
        or before_enemy_hp is None
        or before_enemy_hp <= 0
        or before_party != initial_party
    ):
        raise SurgeChapterError(f"{label} weakening did not normalize to a stable MAIN gate.")
    if before.active_party_index != party_index:
        _flee(emulator, executor, reader, before)
        return False

    party_before_attack = PokemonRedPartyReader(emulator).read()
    helper_before = party_before_attack.members[party_index]
    pp_before = helper_before.moves[move_index].current_pp
    _navigate_main(executor, reader, 0)
    _pulse(executor, MacroActionKind.CONFIRM, frames=120)
    target_slot = move_index + 1
    for _ in range(8):
        current = reader.read()
        menu = reader.read_battle_menu_state(current)
        if menu.phase is BattleMenuPhase.MOVE and menu.selected_move_slot == target_slot:
            break
        if menu.phase is not BattleMenuPhase.MOVE or menu.selected_move_slot is None:
            raise SurgeChapterError(f"{label} lost its helper move menu.")
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if menu.selected_move_slot < target_slot else "up",
            120,
        )
    else:
        raise SurgeChapterError(f"{label} could not select its weakening move.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=180)

    for pulse in range(48):
        current = reader.read()
        helper_after = PokemonRedPartyReader(emulator).read().members[party_index]
        pp_spent = helper_after.moves[move_index].current_pp == pp_before - 1
        if current.battle_state == 0:
            if current.party_species_ids != before_party or not pp_spent:
                raise SurgeChapterError(f"{label} weakening knockout changed protected state.")
            return False
        phase = reader.read_battle_menu_state(current).phase
        turn_result = _wild_weakening_turn_result(
            expected_species_id=before.enemy_species_id,
            before_enemy_hp=before_enemy_hp,
            current_species_id=current.enemy_species_id,
            current_enemy_hp=current.enemy_hp,
            pp_spent=pp_spent,
            phase=phase,
        )
        if current.battle_state == 1 and turn_result is not None:
            protected_index = next(
                (index for index, hp in enumerate(current.party_hp or ()) if hp > 0),
                None,
            )
            if protected_index is None:
                raise SurgeChapterError(f"{label} weakening left no living catcher.")
            if current.active_party_index != protected_index:
                _switch_wild_capture_party_slot(
                    emulator,
                    executor,
                    reader,
                    protected_index,
                    before.enemy_species_id,
                    current.enemy_hp,
                    f"{label} protected catcher",
                )
            if turn_result:
                return True
            _flee(emulator, executor, reader, reader.read())
            return False
        if (current.battler_hp or 0) <= 0:
            landed = (
                current.enemy_hp is not None and 0 < current.enemy_hp < before_enemy_hp and pp_spent
            )
            protected_index = next(
                (index for index, hp in enumerate(current.party_hp or ()) if hp > 0),
                None,
            )
            if protected_index is None:
                raise SurgeChapterError(f"{label} weakening left no living catcher.")
            restored = _force_switch_wild_capture_to_lead(
                emulator,
                executor,
                reader,
                before.enemy_species_id,
                current.enemy_hp if landed else before_enemy_hp,
                label,
                party_index=protected_index,
            )
            if landed:
                return True
            _flee(emulator, executor, reader, restored)
            return False
        if phase is BattleMenuPhase.MOVE:
            # A completed turn can return through the previously selected move
            # menu. Cancel back to MAIN so one weakening proof cannot issue a
            # second attack before the outer policy replans.
            _pulse(executor, MacroActionKind.CANCEL, frames=120)
            continue
        _pulse(
            executor,
            _wild_weakening_settle_action(phase, pulse),
            frames=120,
        )
    raise SurgeChapterError(f"{label} weakening attack did not settle.")


def _try_catch_wild(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    species_id: int | None,
    label: str,
    *,
    max_throws: int,
) -> bool:
    if species_id is None:
        raise SurgeChapterError(f"{label} capture received no target species.")
    if type(max_throws) is not int or max_throws <= 0:
        raise ValueError("max_throws must be a positive integer")
    starting_inventory = _ordinary_capture_ball_inventory(_bag(emulator))
    starting_balls = sum(starting_inventory)
    starting_specimens = _living_specimen_count(reader)
    if starting_balls <= 0:
        raise SurgeChapterError(f"{label} capture has no ordinary capture balls remaining.")
    throws = min(starting_balls, max_throws)
    for throws_used in range(1, throws + 1):
        ball = _next_ordinary_capture_ball(_bag(emulator))
        _navigate_main(executor, reader, 1)
        _pulse(executor, MacroActionKind.CONFIRM)
        _select_bag_item(emulator, executor, ball)
        _pulse(executor, MacroActionKind.CONFIRM, frames=360)
        for _ in range(48):
            raw = reader.read()
            if raw.battle_state == 0:
                _confirm_kind(executor, MacroActionKind.CANCEL, 6, 180)
                for settle_pulse in range(7):
                    ending_specimens = _living_specimen_count(reader)
                    if ending_specimens == starting_specimens + 1:
                        ending_balls = _ordinary_capture_ball_total(_bag(emulator))
                        if ending_balls != starting_balls - throws_used:
                            raise SurgeChapterError(
                                f"{label} capture changed ordinary balls by an invalid quantity."
                            )
                        return True
                    if ending_specimens != starting_specimens:
                        raise SurgeChapterError(
                            f"{label} capture changed the living collection by an invalid quantity."
                        )
                    if settle_pulse < 6:
                        _pulse(executor, MacroActionKind.CANCEL, frames=180)
                ending_balls = _ordinary_capture_ball_total(_bag(emulator))
                if ending_balls != starting_balls - throws_used:
                    raise SurgeChapterError(
                        f"{label} ended encounter changed ordinary-ball accounting."
                    )
                # Roar, Teleport and similar wild exits can end battle after a
                # failed throw.  Battle termination is not capture evidence.
                return False
            if (
                raw.battle_state == 1
                and reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN
            ):
                break
            _pulse(executor, MacroActionKind.CONFIRM)
    raw = reader.read()
    if not raw.battle_state:
        raise SurgeChapterError(f"{label} capture retry lost its live encounter.")
    _flee(emulator, executor, reader, raw)
    ending_balls = _ordinary_capture_ball_total(_bag(emulator))
    if ending_balls != starting_balls - throws:
        raise SurgeChapterError(f"{label} capture retry changed its ordinary-ball accounting.")
    return False


def _living_specimen_count(reader: PokemonRedStateReader) -> int:
    """Count party plus all boxes without confusing a wild exit for a catch."""

    raw = reader.read()
    party = tuple(raw.party_species_ids or ())
    if raw.party_count is None or raw.party_count != len(party):
        raise SurgeChapterError("Wild capture lost complete party-count evidence.")
    boxes = reader.read_all_box_states()
    return len(party) + sum(boxes.counts)


def _ordinary_capture_ball_inventory(
    inventory: Mapping[int, int],
) -> tuple[int, ...]:
    return tuple(inventory.get(item, 0) for item in WILD_CAPTURE_BALL_PRIORITY)


def _ordinary_capture_ball_total(inventory: Mapping[int, int]) -> int:
    return sum(_ordinary_capture_ball_inventory(inventory))


def _next_ordinary_capture_ball(inventory: Mapping[int, int]) -> ItemId:
    try:
        return next(item for item in WILD_CAPTURE_BALL_PRIORITY if inventory.get(item, 0) > 0)
    except StopIteration as error:
        raise SurgeChapterError("No ordinary capture ball remains") from error


def _store_wild_collection_specimens(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
) -> None:
    raw = reader.read()
    _require(raw, MapId.VERMILION_CITY, (11, 4), 0, "wild collection Dig return")
    _move(executor, reader, ("up",), timing, "Vermilion Center")
    _wait(executor, timing.transition_frames)
    _require(reader.read(), MapId.VERMILION_POKECENTER, (3, 7), 0, "Vermilion Center entry")
    _approach_vermilion_pc(executor, reader, timing)
    storage_timing = RedPCStorageTiming(wait_frames=timing.wait_frames)
    try:
        open_bills_pc(executor, reader, timing=storage_timing)
        pidgey = deposit_party_member(
            executor,
            reader,
            party_slot=4,
            expected_species_id=PIDGEY_SPECIES_ID,
            timing=storage_timing,
        )
        rattata = deposit_party_member(
            executor,
            reader,
            party_slot=4,
            expected_species_id=RATTATA_SPECIES_ID,
            timing=storage_timing,
        )
        caterpie = deposit_party_member(
            executor,
            reader,
            party_slot=4,
            expected_species_id=CATERPIE_SPECIES_ID,
            timing=storage_timing,
        )
    except RedPCStorageError as error:
        raise SurgeChapterError(f"Wild collection specimen storage failed: {error}") from error
    if not pidgey.passed or not rattata.passed or not caterpie.passed:
        raise SurgeChapterError("Wild collection storage lacked exact deposit transitions.")
    observation = red_collection_observation(
        reader.read_pokedex_state(),
        PokemonRedPartyReader(emulator).read(),
        reader.read_all_box_states(),
    )
    living = Counter(item.species_ref for item in observation.specimens)
    required = {10: 1, 11: 2, 14: 2, 16: 1, 19: 1, 25: 1}
    missing = {
        number: quantity - living[red_species_ref(number)]
        for number, quantity in required.items()
        if living[red_species_ref(number)] < quantity
    }
    if missing or reader.read().party_species_ids != (
        WARTORTLE_SPECIES_ID,
        DUX_SPECIES_ID,
        DIGLETT_SPECIES_ID,
    ):
        raise SurgeChapterError(
            "Wild collection storage missed its living gate: "
            f"missing={missing!r}, party={reader.read().party_species_ids!r}."
        )
    _confirm_kind(executor, MacroActionKind.CANCEL, 5, 180)
    _move(
        executor,
        reader,
        VERMILION_PC_TO_NURSE,
        timing,
        "Vermilion collection nurse",
    )
    _require(reader.read(), MapId.VERMILION_POKECENTER, (3, 3), 0, "collection nurse")
    _confirm(executor, 9, 240)
    healed = reader.read()
    if (
        healed.party_species_ids != (WARTORTLE_SPECIES_ID, DUX_SPECIES_ID, DIGLETT_SPECIES_ID)
        or healed.party_hp != healed.party_max_hp
        or any(healed.party_status or ())
    ):
        raise SurgeChapterError(
            "Vermilion Center did not restore the complete post-collection party."
        )
    _move(
        executor,
        reader,
        VERMILION_NURSE_TO_EXIT,
        timing,
        "Vermilion Center collection exit",
    )
    _wait(executor, timing.transition_frames)
    _require(
        reader.read(),
        MapId.VERMILION_CITY,
        (11, 4),
        0,
        "post-collection healed boundary",
    )


def _approach_vermilion_pc(
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
) -> None:
    _move(
        executor,
        reader,
        _directions("UUURDDRU" + "R" * 4 + "U" + "R" * 4),
        timing,
        "Vermilion PC safe corridor",
    )
    _require(reader.read(), MapId.VERMILION_POKECENTER, (13, 4), 0, "Vermilion PC")
    _pulse(executor, MacroActionKind.MOVE, "up", 60)


def _field_dig_to_viridian(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
) -> None:
    before = reader.read()
    executor.execute(MacroAction(MacroActionKind.OPEN_MENU))
    _wait(executor, timing.wait_frames)
    while emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 1:
        _pulse(executor, MacroActionKind.MOVE, "up", 120)
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    while emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 2:
        _pulse(executor, MacroActionKind.MOVE, "down", 120)
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    if DIG_MOVE_ID not in _read_four(emulator, RamAddress.PARTY_MON_3_MOVES):
        raise SurgeChapterError("Diglett lost Dig before the Route 1 return.")
    while emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 0:
        _pulse(executor, MacroActionKind.MOVE, "up", 120)
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(timing.reward_pulses):
        _pulse(executor, MacroActionKind.CONFIRM, frames=240)
        raw = reader.read()
        if raw.map_id == MapId.VIRIDIAN_CITY:
            if raw.party_species_ids != before.party_species_ids:
                raise SurgeChapterError("Route 1 Dig return changed the protected party.")
            if (raw.player_x, raw.player_y) != (23, 26):
                raise SurgeChapterError(
                    "Route 1 Dig return missed the healed Viridian anchor: "
                    f"{(raw.player_x, raw.player_y)!r}."
                )
            return
    raw = reader.read()
    raise SurgeChapterError(
        "Route 1 Dig did not return to Viridian: "
        f"map={raw.map_id!r}, coordinate={(raw.player_x, raw.player_y)!r}, "
        f"party={raw.party_species_ids!r}, ready={reader.read_input_readiness().ready}."
    )


def _return_from_viridian_to_vermilion(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
    *,
    cave_route_to_route_2: tuple[str, ...],
) -> None:
    """Walk back through Diglett's Cave after the verified Viridian Dig."""

    _require(reader.read(), MapId.VIRIDIAN_CITY, (23, 26), 0, "Viridian Dig anchor")
    _move(
        executor,
        reader,
        VIRIDIAN_CENTER_RETURN_DIRECTIONS,
        timing,
        "Viridian Dig south-boundary return",
    )
    _require(reader.read(), MapId.VIRIDIAN_CITY, (21, 35), 0, "Viridian Dig south boundary")
    _move_fleeing_wild(
        emulator,
        executor,
        reader,
        VIRIDIAN_TO_ROUTE_2_DIRECTIONS,
        timing,
        "Viridian Dig Route 2 return",
    )
    _traverse_route_2_to_cave_house(emulator, executor, reader, timing)
    raw = reader.read()
    if raw.map_id != MapId.DIGLETTS_CAVE_ROUTE_2 or raw.player_x is None or raw.player_y is None:
        raise SurgeChapterError("Viridian Dig return missed the Route 2 cave house.")
    _move(
        executor,
        reader,
        _directions("U" * max(raw.player_y - 4, 0) + "R" * max(4 - raw.player_x, 0)),
        timing,
        "Viridian Dig cave re-entry",
    )
    _wait(executor, timing.transition_frames)
    if reader.read().map_id != MapId.DIGLETTS_CAVE:
        raise SurgeChapterError("Viridian Dig return did not enter Diglett's Cave.")
    if not cave_route_to_route_2:
        raise SurgeChapterError("Viridian Dig return lacks its proven cave route.")
    _move_fleeing_wild(
        emulator,
        executor,
        reader,
        _inverse_directions(cave_route_to_route_2),
        timing,
        "Route 11 inverse cave traversal",
    )
    _move_until_map_fleeing_wild(
        emulator,
        executor,
        reader,
        "down",
        MapId.DIGLETTS_CAVE_ROUTE_11,
        timing,
        "Route 11 cave-house return",
    )
    _wait(executor, timing.transition_frames)
    raw = reader.read()
    if raw.map_id != MapId.DIGLETTS_CAVE_ROUTE_11 or raw.player_x is None or raw.player_y is None:
        raise SurgeChapterError("Viridian Dig return missed the Route 11 cave house.")
    if raw.player_x > 3:
        _move(
            executor,
            reader,
            ("left",) * (raw.player_x - 3),
            timing,
            "Viridian Dig Route 11 exit column",
        )
    _move_until_map(executor, reader, "down", MapId.ROUTE_11, timing, "Route 11 cave exit")
    _wait(executor, timing.transition_frames)
    raw = _move_until_map_fleeing_wild(
        emulator,
        executor,
        reader,
        "left",
        MapId.VERMILION_CITY,
        timing,
        "Route 11 Vermilion return",
    )
    _wait(executor, timing.transition_frames)
    raw = reader.read() if raw.map_id == MapId.VERMILION_CITY else raw
    if raw.player_x is None or raw.player_y != 14 or raw.player_x < 23:
        raise SurgeChapterError(
            f"Route 11 return missed the Vermilion east boundary: {(raw.player_x, raw.player_y)!r}."
        )
    _move(
        executor,
        reader,
        ("left",) * (raw.player_x - 23),
        timing,
        "Vermilion east-boundary normalization",
    )
    _move(
        executor,
        reader,
        VERMILION_ROUTE_11_TO_CENTER_EXTERIOR,
        timing,
        "Vermilion Center collection return",
    )
    _require(reader.read(), MapId.VERMILION_CITY, (11, 4), 0, "wild collection return")


def _traverse_route_2_to_viridian(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
) -> tuple[tuple[int, int], ...]:
    """Explore Route 2's Cut corridor and return its proven coordinate trail."""

    raw = reader.read()
    if raw.map_id != MapId.ROUTE_2 or raw.player_x is None or raw.player_y is None:
        raise SurgeChapterError("Route 2 traversal lacks its exterior entry gate.")
    entry = (raw.player_x, raw.player_y)
    stack = [entry]
    visited = {entry}
    parents: dict[tuple[int, int], tuple[int, int] | None] = {entry: None}
    recent: deque[tuple[int, int]] = deque((entry,), maxlen=24)
    attempted: dict[tuple[int, int], set[str]] = {}
    deltas = {
        "down": (0, 1),
        "right": (1, 0),
        "left": (-1, 0),
        "up": (0, -1),
    }
    excluded = {
        (12, 9),
        (15, 19),
        (3, 11),
        (3, 43),
    }
    for _ in range(timing.encounter_steps):
        raw = reader.read()
        if raw.map_id == MapId.VIRIDIAN_CITY:
            return tuple(stack)
        if raw.map_id == MapId.ROUTE_2_GATE:
            _move_until_map(
                executor,
                reader,
                "down",
                MapId.ROUTE_2,
                timing,
                "Route 2 bypass gate",
            )
            raw = reader.read()
            if raw.player_x is None or raw.player_y is None:
                raise SurgeChapterError("Route 2 gate return lacks coordinates.")
            position = (raw.player_x, raw.player_y)
            stack = [position]
            visited.add(position)
            parents[position] = None
            recent.append(position)
            continue
        if raw.map_id != MapId.ROUTE_2:
            raise SurgeChapterError(f"Route 2 traversal reached an unexpected map {raw.map_id!r}.")
        if raw.battle_state:
            balls = _bag(emulator).get(ItemId.POKE_BALL, 0)
            _flee(emulator, executor, reader, raw)
            if _bag(emulator).get(ItemId.POKE_BALL, 0) != balls:
                raise SurgeChapterError("Route 2 flee changed Poké Balls.")
            continue
        if raw.player_x is None or raw.player_y is None:
            raise SurgeChapterError("Route 2 traversal lacks live coordinates.")
        position = (raw.player_x, raw.player_y)
        if position != stack[-1]:
            raise SurgeChapterError(f"Route 2 traversal lost its search stack at {position!r}.")
        tried = attempted.setdefault(position, set())
        direction = next(
            (
                candidate
                for candidate, delta in deltas.items()
                if candidate not in tried
                and (position[0] + delta[0], position[1] + delta[1]) not in visited
                and (position[0] + delta[0], position[1] + delta[1]) not in excluded
                and position[0] + delta[0] >= 9
            ),
            None,
        )
        backtracking = direction is None
        if backtracking:
            if len(stack) == 1:
                raise SurgeChapterError("Route 2 traversal exhausted its reachable corridor.")
            parent = stack[-2]
            dx, dy = parent[0] - position[0], parent[1] - position[1]
            try:
                direction = next(name for name, delta in deltas.items() if delta == (dx, dy))
            except StopIteration as error:
                raise SurgeChapterError(
                    "Route 2 traversal cannot reverse a one-way transition: "
                    f"position={position!r}, parent={parent!r}, recent={tuple(recent)!r}."
                ) from error
        else:
            tried.add(direction)
        _pulse(executor, MacroActionKind.MOVE, direction, 60)
        moved = reader.read()
        if (
            moved.map_id == MapId.ROUTE_2
            and not moved.battle_state
            and (moved.player_x, moved.player_y) == position
            and emulator.read_u8(RamAddress.TILE_IN_FRONT_OF_PLAYER) == 0x3D
        ):
            _cut_tree_facing(emulator, executor, reader, direction, timing, "Route 2 Cut")
            moved = reader.read()
        if moved.battle_state:
            balls = _bag(emulator).get(ItemId.POKE_BALL, 0)
            _flee(emulator, executor, reader, moved)
            if _bag(emulator).get(ItemId.POKE_BALL, 0) != balls:
                raise SurgeChapterError("Route 2 flee changed Poké Balls.")
            moved = reader.read()
        if moved.map_id != MapId.ROUTE_2:
            continue
        next_position = (moved.player_x, moved.player_y)
        if next_position != position:
            recent.append(next_position)
        if backtracking:
            if next_position != stack[-2]:
                raise SurgeChapterError("Route 2 traversal could not backtrack.")
            stack.pop()
        elif next_position != position:
            if next_position in visited:
                rebuilt = [next_position]
                while parents[rebuilt[-1]] is not None:
                    rebuilt.append(parents[rebuilt[-1]])  # type: ignore[arg-type]
                stack = list(reversed(rebuilt))
            else:
                visited.add(next_position)
                parents[next_position] = position
                stack.append(next_position)
    raise SurgeChapterError("Route 2 traversal exceeded its bounded step budget.")


def _traverse_route_2_to_cave_house(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
) -> RawGameState:
    """Explore north through Route 2's Cut lanes to Diglett's Cave."""

    raw = reader.read()
    if raw.map_id != MapId.ROUTE_2 or raw.player_x is None or raw.player_y is None:
        raise SurgeChapterError("Northbound Route 2 traversal lacks its entry gate.")
    position = (raw.player_x, raw.player_y)
    attempted: dict[tuple[int, int], set[str]] = {}
    edges: dict[tuple[int, int], dict[tuple[int, int], str]] = {}
    deltas = {
        "up": (0, -1),
        "right": (1, 0),
        "left": (-1, 0),
        "down": (0, 1),
    }
    excluded = {(3, 11), (15, 19), (3, 43)}

    def unexplored(current: tuple[int, int]) -> tuple[str, ...]:
        tried = attempted.setdefault(current, set())
        return tuple(
            direction
            for direction, delta in deltas.items()
            if direction not in tried
            and (current[0] + delta[0], current[1] + delta[1]) not in excluded
        )

    def route_to_frontier(current: tuple[int, int]) -> tuple[tuple[int, int], ...]:
        queue = deque((current,))
        parent: dict[tuple[int, int], tuple[int, int] | None] = {current: None}
        target: tuple[int, int] | None = None
        while queue:
            node = queue.popleft()
            if unexplored(node):
                target = node
                break
            for neighbor in edges.get(node, {}):
                if neighbor not in parent:
                    parent[neighbor] = node
                    queue.append(neighbor)
        if target is None:
            return ()
        path = [target]
        while parent[path[-1]] is not None:
            path.append(parent[path[-1]])  # type: ignore[arg-type]
        return tuple(reversed(path))

    for _ in range(timing.encounter_steps):
        raw = reader.read()
        if raw.map_id == MapId.DIGLETTS_CAVE_ROUTE_2:
            return raw
        if raw.map_id == MapId.ROUTE_2_GATE:
            if raw.player_x is None or raw.player_y is None:
                raise SurgeChapterError("Route 2 north gate lacks entry coordinates.")
            gate_entry = (raw.player_x, raw.player_y)
            if raw.player_y > 1:
                _move(
                    executor,
                    reader,
                    ("up",) * (raw.player_y - 1),
                    timing,
                    "Route 2 north gate corridor",
                )
            raw = reader.read()
            if raw.player_x is None:
                raise SurgeChapterError("Route 2 north gate lost its exit coordinate.")
            if raw.player_x != 5:
                _move(
                    executor,
                    reader,
                    ("right",) * (5 - raw.player_x),
                    timing,
                    "Route 2 north gate exit column",
                )
            try:
                _move_until_map(
                    executor,
                    reader,
                    "up",
                    MapId.ROUTE_2,
                    timing,
                    "Route 2 northbound bypass gate",
                )
            except SurgeChapterError as error:
                stuck = reader.read()
                raise SurgeChapterError(
                    "Route 2 northbound bypass gate did not exit: "
                    f"entry={gate_entry!r}, current={(stuck.player_x, stuck.player_y)!r}."
                ) from error
            raw = reader.read()
            if raw.player_x is None or raw.player_y is None:
                raise SurgeChapterError("Route 2 north gate return lacks coordinates.")
            position = (raw.player_x, raw.player_y)
            continue
        if raw.map_id != MapId.ROUTE_2:
            raise SurgeChapterError(f"Northbound Route 2 traversal reached map {raw.map_id!r}.")
        if raw.battle_state:
            balls = _bag(emulator).get(ItemId.POKE_BALL, 0)
            _flee(emulator, executor, reader, raw)
            if _bag(emulator).get(ItemId.POKE_BALL, 0) != balls:
                raise SurgeChapterError("Northbound Route 2 flee changed Poké Balls.")
            continue
        if raw.player_x is None or raw.player_y is None:
            raise SurgeChapterError("Northbound Route 2 traversal lacks coordinates.")
        position = (raw.player_x, raw.player_y)
        choices = unexplored(position)
        if choices:
            direction = choices[0]
            attempted[position].add(direction)
        else:
            path = route_to_frontier(position)
            if len(path) < 2:
                raise SurgeChapterError(f"Northbound Route 2 traversal exhausted at {position!r}.")
            direction = edges[position][path[1]]
        _pulse(executor, MacroActionKind.MOVE, direction, 60)
        moved = reader.read()
        if (
            moved.map_id == MapId.ROUTE_2
            and not moved.battle_state
            and (moved.player_x, moved.player_y) == position
            and emulator.read_u8(RamAddress.TILE_IN_FRONT_OF_PLAYER) == 0x3D
        ):
            _cut_tree_facing(
                emulator,
                executor,
                reader,
                direction,
                timing,
                "northbound Route 2 Cut",
            )
            moved = reader.read()
        if moved.battle_state:
            balls = _bag(emulator).get(ItemId.POKE_BALL, 0)
            _flee(emulator, executor, reader, moved)
            if _bag(emulator).get(ItemId.POKE_BALL, 0) != balls:
                raise SurgeChapterError("Northbound Route 2 flee changed Poké Balls.")
            moved = reader.read()
        if moved.map_id != MapId.ROUTE_2:
            continue
        next_position = (moved.player_x, moved.player_y)
        if next_position != position:
            edges.setdefault(position, {})[next_position] = direction
            reverse = next(
                (
                    name
                    for name, delta in deltas.items()
                    if delta == (position[0] - next_position[0], position[1] - next_position[1])
                ),
                None,
            )
            if reverse is not None:
                edges.setdefault(next_position, {})[position] = reverse
    raw = reader.read()
    raise SurgeChapterError(
        "Northbound Route 2 traversal exceeded its step budget: "
        f"map={raw.map_id!r}, coordinate={(raw.player_x, raw.player_y)!r}."
    )


def _traverse_cave_to_route_2(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
    *,
    route_sink: list[str] | None = None,
) -> RawGameState:
    """Cross Diglett's Cave toward Route 2."""

    return _traverse_cave(
        emulator,
        executor,
        reader,
        timing,
        target_map=MapId.DIGLETTS_CAVE_ROUTE_2,
        entrance_warp=(37, 31),
        label="Route 2 cave traversal",
        route_sink=route_sink,
    )


def _traverse_cave(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
    *,
    target_map: MapId,
    entrance_warp: tuple[int, int],
    label: str,
    route_sink: list[str] | None = None,
) -> RawGameState:
    """Cross Diglett's Cave while safely recovering from random encounters."""

    raw = reader.read()
    if raw.player_x is None or raw.player_y is None:
        raise SurgeChapterError(f"{label} lacks its entry coordinates.")
    entry = (raw.player_x, raw.player_y)
    stack = [entry]
    path_directions: list[str] = []
    visited = {entry}
    attempted: dict[tuple[int, int], set[str]] = {}
    deltas = {
        "left": (-1, 0),
        "up": (0, -1),
        "right": (1, 0),
        "down": (0, 1),
    }
    for _ in range(timing.encounter_steps):
        raw = reader.read()
        if raw.map_id == target_map:
            return raw
        if raw.map_id != MapId.DIGLETTS_CAVE:
            raise SurgeChapterError(f"{label} reached an unexpected map {raw.map_id!r}.")
        if raw.battle_state:
            balls = _bag(emulator).get(ItemId.POKE_BALL, 0)
            _flee(emulator, executor, reader, raw)
            if _bag(emulator).get(ItemId.POKE_BALL, 0) != balls:
                raise SurgeChapterError(f"{label} flee changed Poké Balls.")
            continue
        if raw.player_x is None or raw.player_y is None:
            raise SurgeChapterError(f"{label} lacks live coordinates.")
        position = (raw.player_x, raw.player_y)
        if position != stack[-1]:
            raise SurgeChapterError(f"{label} lost its search stack at {position!r}.")
        tried = attempted.setdefault(position, set())
        direction = next(
            (
                candidate
                for candidate in ("left", "up", "right", "down")
                if candidate not in tried
                and (
                    position[0] + deltas[candidate][0],
                    position[1] + deltas[candidate][1],
                )
                not in visited
                and (
                    position[0] + deltas[candidate][0],
                    position[1] + deltas[candidate][1],
                )
                != entrance_warp
            ),
            None,
        )
        backtracking = direction is None
        if backtracking:
            if len(stack) == 1:
                raise SurgeChapterError(f"{label} exhausted its reachable map.")
            parent = stack[-2]
            dx, dy = parent[0] - position[0], parent[1] - position[1]
            direction = next(name for name, delta in deltas.items() if delta == (dx, dy))
        else:
            tried.add(direction)
        _pulse(executor, MacroActionKind.MOVE, direction, 60)
        moved = reader.read()
        if moved.battle_state:
            balls = _bag(emulator).get(ItemId.POKE_BALL, 0)
            _flee(emulator, executor, reader, moved)
            if _bag(emulator).get(ItemId.POKE_BALL, 0) != balls:
                raise SurgeChapterError(f"{label} flee changed Poké Balls.")
            moved = reader.read()
        if moved.map_id == target_map:
            if route_sink is not None:
                route_sink[:] = (*path_directions, direction)
            return moved
        if moved.map_id != MapId.DIGLETTS_CAVE:
            raise SurgeChapterError(f"{label} reached an unexpected map {moved.map_id!r}.")
        next_position = (moved.player_x, moved.player_y)
        if backtracking:
            if next_position != stack[-2]:
                raise SurgeChapterError(f"{label} could not backtrack.")
            stack.pop()
            path_directions.pop()
        elif next_position != position:
            if next_position in visited:
                raise SurgeChapterError(f"{label} revisited an unplanned cell.")
            visited.add(next_position)
            stack.append(next_position)
            path_directions.append(direction)
    raw = reader.read()
    raise SurgeChapterError(
        f"{label} exceeded its bounded step budget: "
        f"map={raw.map_id!r}, coordinate={(raw.player_x, raw.player_y)!r}, "
        f"battle={raw.battle_state}."
    )


def _throw_until_caught_diglett(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
) -> None:
    starting_balls = _bag(emulator).get(ItemId.POKE_BALL, 0)
    throw_limit = min(starting_balls, DIGLETT_CAPTURE_THROW_LIMIT)
    for _ in range(throw_limit):
        if _settle_caught_diglett(emulator, executor, reader, starting_balls, throw_limit):
            return
        restored = _restore_diglett_capture_catcher_if_fainted(emulator, executor, reader)
        if restored.battle_state == 0:
            if _settle_caught_diglett(emulator, executor, reader, starting_balls, throw_limit):
                return
            raise SurgeChapterError("Diglett capture ended before acquisition.")
        _navigate_main(executor, reader, 1)
        _pulse(executor, MacroActionKind.CONFIRM)
        _select_bag_item(emulator, executor, ItemId.POKE_BALL)
        _pulse(executor, MacroActionKind.CONFIRM, frames=360)
        for _ in range(32):
            raw = reader.read()
            if _settle_caught_diglett(emulator, executor, reader, starting_balls, throw_limit):
                return
            active_hp = raw.battler_hp if raw.battler_hp is not None else raw.active_party_hp
            if raw.battle_state == 1 and active_hp == 0:
                restored = _restore_diglett_capture_catcher_if_fainted(
                    emulator,
                    executor,
                    reader,
                )
                if restored.battle_state == 0:
                    if _settle_caught_diglett(
                        emulator,
                        executor,
                        reader,
                        starting_balls,
                        throw_limit,
                    ):
                        return
                    raise SurgeChapterError("Diglett capture ended before acquisition.")
                break
            if (
                raw.battle_state == 1
                and reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN
            ):
                break
            _pulse(executor, MacroActionKind.CONFIRM)
    raise SurgeChapterError("Diglett capture exhausted its bounded Poké Balls.")


def _settle_caught_diglett(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    starting_balls: int,
    throw_limit: int,
) -> bool:
    """Finish capture dialogue once the observed party already contains Diglett."""

    target_party = (
        WARTORTLE_SPECIES_ID,
        SPEAROW_SPECIES_ID,
        DIGLETT_SPECIES_ID,
    )
    raw = reader.read()
    if raw.party_species_ids != target_party:
        return False
    for _ in range(32):
        if raw.battle_state == 0:
            _confirm_kind(executor, MacroActionKind.CANCEL, 3, 180)
            used = starting_balls - _bag(emulator).get(ItemId.POKE_BALL, 0)
            if not 1 <= used <= throw_limit:
                raise SurgeChapterError("Diglett capture used an invalid ball count.")
            return True
        _pulse(executor, MacroActionKind.CANCEL, frames=120)
        raw = reader.read()
        if raw.party_species_ids != target_party:
            raise SurgeChapterError("Diglett capture dialogue changed the acquired party.")
    raise SurgeChapterError("Diglett capture dialogue did not settle.")


def _restore_diglett_capture_catcher_if_fainted(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
) -> RawGameState:
    """Select a living party member when Diglett KOs the current catcher."""

    raw = reader.read()
    active_hp = raw.battler_hp if raw.battler_hp is not None else raw.active_party_hp
    if raw.battle_state != 1 or (active_hp is not None and active_hp > 0):
        return raw
    if raw.enemy_species_id is None or raw.enemy_hp is None:
        return raw
    if active_hp is None:
        raise SurgeChapterError("Diglett capture lacks active-catcher HP evidence.")
    if raw.enemy_species_id != DIGLETT_SPECIES_ID:
        raise SurgeChapterError(
            "Diglett forced switch lost its protected encounter: "
            f"enemy={(raw.enemy_species_id, raw.enemy_hp)}, "
            f"active={(raw.active_party_index, active_hp)}, "
            f"party_hp={raw.party_hp!r}."
        )
    living_index = next(
        (index for index, hp in enumerate(raw.party_hp or ()) if hp > 0),
        None,
    )
    if living_index is None:
        raise SurgeChapterError("Diglett capture left no living catcher.")
    try:
        return _force_switch_wild_capture_to_lead(
            emulator,
            executor,
            reader,
            DIGLETT_SPECIES_ID,
            raw.enemy_hp,
            "Diglett capture",
            party_index=living_index,
        )
    except SurgeChapterError:
        settled = reader.read()
        if settled.battle_state == 0:
            return settled
        raise


def _select_bag_item(emulator: EmulatorState, executor: CountingExecutor, item: int) -> None:
    for _ in range(20):
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        items = tuple(_bag(emulator))
        if item not in items:
            raise SurgeChapterError(f"Bag item {item:#04x} is unavailable.")
        if absolute < len(items) and items[absolute] == item:
            return
        target = items.index(item)
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if absolute < target else "up",
            120,
        )
    raise SurgeChapterError(f"Could not select bag item {item:#04x}.")


def _teach_cut(
    emulator: EmulatorState, executor: CountingExecutor, reader: PokemonRedStateReader
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
    executor: CountingExecutor,
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
    emulator: EmulatorState, executor: CountingExecutor, reader: PokemonRedStateReader
) -> None:
    _cut_tree_facing(
        emulator,
        executor,
        reader,
        "down",
        DEFAULT_SURGE_TIMING,
        "Gym tree",
    )


def _cut_tree_facing(
    emulator: EmulatorState,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    direction: str,
    timing: SurgeTiming,
    label: str,
) -> None:
    for _ in range(20):
        before = reader.read()
        _pulse(executor, MacroActionKind.MOVE, direction, 120)
        after = reader.read()
        if (after.player_x, after.player_y) != (before.player_x, before.player_y):
            raise SurgeChapterError(f"{label} orientation probe moved unexpectedly.")
        if emulator.read_u8(RamAddress.TILE_IN_FRONT_OF_PLAYER) == 0x3D:
            break
    else:
        raise SurgeChapterError(f"No cuttable {label} was observed.")
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
    _move(executor, reader, (direction,), timing, f"{label} passage")


def _swap_party_lead(
    emulator: EmulatorState,
    executor: CountingExecutor,
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
    executor: CountingExecutor,
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
    executor: CountingExecutor,
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
    executor: CountingExecutor,
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
    executor: CountingExecutor,
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
    # The pinned Gen I source has a documented underflow bug that can select
    # can 0 as the second lock even when can 0 was also the first lock.
    if not 0 <= second <= 14:
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
    executor: CountingExecutor,
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
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SurgeTiming,
    *,
    emulator: EmulatorState | None = None,
) -> tuple[RawGameState, int, int]:
    initial = reader.read()
    moves = initial.battler_moves or initial.first_party_moves or ()
    pp = initial.battler_pp or initial.first_party_pp or ()
    if DIG_MOVE_ID not in moves:
        raise SurgeChapterError("Diglett lead lacks observed Dig move evidence.")
    dig_index = moves.index(DIG_MOVE_ID)
    if dig_index >= len(pp):
        raise SurgeChapterError("Diglett lead lacks observed Dig PP evidence.")
    initial_dig_pp = pp[dig_index] & 0x3F
    super_potions_used = 0

    def dig_policy(raw: RawGameState) -> int:
        if (
            super_potions_used < 2
            and raw.battler_hp is not None
            and raw.battler_max_hp is not None
            and 0 < raw.battler_hp < raw.battler_max_hp
        ):
            raise _PauseForSurgeSuperPotion
        live_moves = raw.battler_moves or ()
        try:
            return live_moves.index(DIG_MOVE_ID) + 1
        except ValueError as error:
            raise SurgeChapterError("Diglett lead lacks live Dig move evidence.") from error

    while True:
        try:
            final = run_adaptive_trainer_battle(
                reader,
                executor,
                dig_policy,
                expected_map=MapId.VERMILION_GYM,
                intent=SURGE_BATTLE_INTENT,
                required_move_id=DIG_MOVE_ID,
                label="Lt. Surge",
                unknown_cancel_interval=3,
                consume_battle_start_schedule=False,
            )
            break
        except BattleRuntimeError as error:
            if not recovery_request_matches(error.__cause__, _PauseForSurgeSuperPotion):
                raise SurgeChapterError(str(error)) from error
        if emulator is None:
            raise SurgeChapterError("Lt. Surge recovery requires live emulator state.")
        if not _use_surge_super_potion(executor, reader, emulator, timing):
            continue
        super_potions_used += 1
        if super_potions_used > 2:
            raise SurgeChapterError("Lt. Surge exceeded its two-item recovery bound.")

    final_pp = final.first_party_pp or final.battler_pp or ()
    if dig_index >= len(final_pp):
        raise SurgeChapterError("Lt. Surge terminal state lacks Dig PP evidence.")
    dig_attacks = initial_dig_pp - (final_pp[dig_index] & 0x3F)
    if dig_attacks < 0:
        raise SurgeChapterError("Lt. Surge Dig PP increased during the battle.")
    return final, dig_attacks, super_potions_used


class _PauseForSurgeSuperPotion(BattleControlRequest):
    default_action = BattleAction.recovery()


def _use_surge_super_potion(
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SurgeTiming,
) -> bool:
    before = reader.read()
    menu = reader.read_battle_menu_state(before)
    target_index = before.active_party_index
    before_quantity = _bag(emulator).get(ItemId.SUPER_POTION, 0)
    # The observation that requested recovery can straddle an opponent or
    # level-up transition.  Revalidate at the action boundary and accept an
    # already-full battler without spending or falsely accounting for an item.
    if (
        before.battle_state == 2
        and target_index is not None
        and menu.phase is BattleMenuPhase.MAIN
        and before.battler_hp is not None
        and before.battler_max_hp is not None
        and before.battler_hp == before.battler_max_hp
    ):
        return False
    if (
        before.battle_state != 2
        or target_index is None
        or menu.phase is not BattleMenuPhase.MAIN
        or before.battler_hp is None
        or before.battler_max_hp is None
        or not 0 < before.battler_hp < before.battler_max_hp
        or before_quantity <= 0
    ):
        raise SurgeChapterError(
            "Lt. Surge recovery lacks a stable damaged MAIN gate: "
            f"battle={before.battle_state}, active={target_index!r}, "
            f"hp={(before.battler_hp, before.battler_max_hp)!r}, "
            f"phase={menu.phase.value}, quantity={before_quantity}."
        )

    _navigate_main(executor, reader, 1)
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    _select_bag_item(emulator, executor, ItemId.SUPER_POTION)
    _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(12):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == target_index:
            break
        _pulse(
            executor,
            MacroActionKind.MOVE,
            "down" if cursor < target_index else "up",
            min(timing.wait_frames, 120),
        )
    else:
        raise SurgeChapterError("Lt. Surge recovery could not select the active battler.")
    _pulse(executor, MacroActionKind.CONFIRM, frames=240)

    expected_hp = min(before.battler_max_hp, before.battler_hp + 50)
    hp_effect_observed = False
    quantity_effect_observed = False
    for _ in range(SURGE_ITEM_SETTLE_PULSES):
        current = reader.read()
        current_quantity = _bag(emulator).get(ItemId.SUPER_POTION, 0)
        hp_effect_observed = hp_effect_observed or current.battler_hp == expected_hp
        quantity_effect_observed = (
            quantity_effect_observed or current_quantity == before_quantity - 1
        )
        if current_quantity < before_quantity - 1:
            raise SurgeChapterError("Lt. Surge recovery spent more than one Super Potion.")
        if (
            current.battle_state == 2
            and hp_effect_observed
            and quantity_effect_observed
            and reader.read_battle_menu_state(current).phase is BattleMenuPhase.MAIN
        ):
            return True
        if current.battle_state != 2 or (current.battler_hp or 0) <= 0:
            raise SurgeChapterError("Lt. Surge recovery lost its living battle gate.")
        # B advances battle text but is inert when MAIN returns. A can reopen
        # the still-selected ITEM command before the quantity update and spend
        # another recovery item if the two effects become observable on
        # adjacent frames.
        _pulse(executor, MacroActionKind.CANCEL, frames=1)
    final = reader.read()
    raise SurgeChapterError(
        "Lt. Surge recovery did not prove its HP and inventory effects: "
        f"hp={final.battler_hp}/{final.battler_max_hp}, "
        f"quantity={_bag(emulator).get(ItemId.SUPER_POTION, 0)}, "
        f"phase={reader.read_battle_menu_state(final).phase.value}."
    )


def _clear_rewards(
    executor: CountingExecutor,
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


def _confirm(executor: CountingExecutor, count: int, frames: int = 180) -> None:
    _confirm_kind(executor, MacroActionKind.CONFIRM, count, frames)


def _confirm_kind(
    executor: CountingExecutor, kind: MacroActionKind, count: int, frames: int
) -> None:
    for _ in range(count):
        _pulse(executor, kind, frames=frames)


def _pulse(
    executor: CountingExecutor,
    kind: MacroActionKind,
    value: str | int | None = None,
    frames: int = 180,
) -> None:
    executor.execute(MacroAction(kind, value))
    _wait(executor, frames)


def _wait(executor: CountingExecutor, frames: int) -> None:
    executor.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))
