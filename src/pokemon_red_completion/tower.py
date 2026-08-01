"""Qualified Pokémon Tower, Mr. Fuji, and Poké Flute chapter."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleResourcePolicy,
    BattleRuntimeError,
    BattleRuntimeTiming,
    RequiredMovePolicy,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.celadon import (
    PROTECTED_PARTY,
    _bag,
    _money,
    _party_hp,
    _party_max_hp,
    _party_status,
)
from pokemon_red_completion.economy import HIDEOUT_SUPER_POTION_RESERVE
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    _flee,
    _select_bag_item,
    _select_cursor,
    _use_battle_super_potion,
    _use_super_potion,
)
from pokemon_red_completion.observation import (
    PIDGEOTTO_SPECIES_ID,
    BattleMenuPhase,
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)

TOWER_CHECKPOINT_COUNT = 28
TOWER_TRAINER_REWARD_TOTAL = 7_325
TOWER_RIVAL_GROWLITHE = 0x21
BITE = 0x2C
BUBBLEBEAM = 0x3D
RIVAL2 = (0xF2, 0x2A)
CHANNELER = (0xF5, 0x2D)
ROCKET = (0xE6, 0x1E)
MAROWAK = 0x91
TOWER_FINAL_PARTY = (0x1C, PROTECTED_PARTY[1], PROTECTED_PARTY[2])

OPTIONAL_EVENTS = (
    EventFlag.BEAT_POKEMONTOWER_3_TRAINER_0,
    EventFlag.BEAT_POKEMONTOWER_3_TRAINER_1,
    EventFlag.BEAT_POKEMONTOWER_3_TRAINER_2,
    EventFlag.BEAT_POKEMONTOWER_4_TRAINER_0,
    EventFlag.BEAT_POKEMONTOWER_4_TRAINER_2,
    EventFlag.BEAT_POKEMONTOWER_5_TRAINER_1,
    EventFlag.BEAT_POKEMONTOWER_5_TRAINER_2,
    EventFlag.BEAT_POKEMONTOWER_5_TRAINER_3,
)
REQUIRED_EVENTS = (
    EventFlag.BEAT_POKEMON_TOWER_RIVAL,
    EventFlag.BEAT_POKEMONTOWER_4_TRAINER_1,
    EventFlag.BEAT_POKEMONTOWER_5_TRAINER_0,
    EventFlag.BEAT_POKEMONTOWER_6_TRAINER_0,
    EventFlag.BEAT_POKEMONTOWER_6_TRAINER_2,
    EventFlag.BEAT_POKEMONTOWER_6_TRAINER_1,
    EventFlag.BEAT_GHOST_MAROWAK,
    EventFlag.BEAT_POKEMONTOWER_7_TRAINER_0,
    EventFlag.BEAT_POKEMONTOWER_7_TRAINER_1,
    EventFlag.BEAT_POKEMONTOWER_7_TRAINER_2,
    EventFlag.RESCUED_MR_FUJI,
    EventFlag.RESCUED_MR_FUJI_WORLD,
    EventFlag.GOT_POKE_FLUTE,
)


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "D": "down", "L": "left", "R": "right"}[item] for item in value)


CENTER_EXIT = _directions("DDDDD")
CELADON_EAST = _directions("DRRRRRRRR")
ROUTE_7 = _directions("RRRRRDDDDDRRRRDDDDDDLLL")
ROUTE_7_GATE = _directions("UUUU")
WEST_GATE_TO_TUNNEL = _directions("RUU")
UNDERGROUND_EAST = _directions("UUU" + "R" * 45)
EAST_GATE_EXIT = _directions("DDDD")
ROUTE_8_SAFE_ROW_MASKS = (
    0x000000000000000,
    0x000000000000000,
    0x0007BFFFFBF0000,
    0x0007BFFF8810000,
    0x0007BFFC3BDFFE0,
    0x0F87BFFF83DDEE0,
    0x0F87BFFE3BDC0E0,
    0x0F87F003F81DFE0,
    0xFF87E3F1FBDC003,
    0x0F87EFFDFBDDF03,
    0x0F87F3F1FFDFF03,
    0x0F87EFFDFC1FC00,
    0x0F7FE3F3FFFFFE0,
    0x0FFBEFFEFFFFFE0,
    0x0FFBE001FFFFFE0,
    0x0FFBEFFDFFFFFE0,
    0x000000000000000,
    0x000000000000000,
)
ROUTE_8_EAST_GOAL = (59, 8)
LAVENDER_TO_TOWER = _directions("UURRRRRRRRRRRRRRU")
TOWER_1_TO_2 = _directions("UUUUUUUURRRRRRRR")
TOWER_2_RIVAL = _directions("UULULUL")
TOWER_2_TO_3 = _directions("LLLLLLLLDDLLDDLL")
TOWER_3_TO_4 = _directions("RRRDDDDRRRULUUUUURRRRURRRRRDRDD")
TOWER_4_CHANNELER = _directions("LLL")
TOWER_4_TO_ELIXIR = _directions("DLL")
TOWER_4_ELIXIR_TO_5 = _directions("RRULULLLDLDDDLLLULLLULU")
TOWER_5_HEAL = _directions("UURURRRRRRRRRDDDLL")
TOWER_5_CHANNELER = _directions("RRUURR")
TOWER_5_REHEAL = _directions("LLDDLL")
TOWER_5_TO_6 = _directions("RRUUURRRRDRDD")
TOWER_6_CHANNELER_19 = _directions("DLLL")
TOWER_6_CHANNELER_21 = _directions("UUUULU")
TOWER_6_TO_5 = _directions("DRDRRRDD")
TOWER_5_RETURN_HEAL = _directions("DLDLLLDLLLLLUUUR")
TOWER_5_FINAL_ASCENT = _directions("DLDDRRRURRURRRUR")
TOWER_6_CHANNELER_20 = _directions("UULLLUUUULLLLDDDDDLL")
TOWER_6_X_ACCURACY = _directions("RUUUUURRRRRDDDDDDDDDDD")
TOWER_6_RARE_CANDY = _directions("UUUUUUUUUUULLLLDDLDLLDLL")
TOWER_6_MAROWAK = _directions("DDDRDRRRDDDDD")
TOWER_7_ROCKET_1 = _directions("LRUUUUL")
TOWER_7_ROCKET_2 = _directions("UUU")
TOWER_7_ROCKET_3 = _directions("URU")
TOWER_7_FUJI = _directions("UUU")
FUJI_HOUSE_TO_FUJI = _directions("ULUUUUR")
FUJI_HOUSE_EXIT = _directions("LDDDDDD")
LAVENDER_TO_CENTER = _directions("LLLUUUULU")


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class TowerChapterError(RuntimeError):
    """Raised when the qualified Fuji route loses semantic evidence."""


@dataclass(frozen=True, slots=True)
class TowerTiming:
    wait_frames: int = 180
    transition_frames: int = 180
    movement_retries: int = 18
    dialogue_pulses: int = 32

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_TOWER_TIMING = TowerTiming()
TOWER_LAVENDER_TIMING = replace(DEFAULT_LAVENDER_TIMING, flee_pulses=64)
TOWER_BATTLE_TIMING = BattleRuntimeTiming(
    max_move_menu_transition_pulses=24,
    max_pp_confirmation_pulses=12,
    max_attack_confirmation_pulses=6,
    max_post_attack_transition_pulses=24,
)
TOWER_EVOLUTION_BATTLE_TIMING = BattleRuntimeTiming(
    max_move_menu_transition_pulses=24,
    max_pp_confirmation_pulses=12,
    max_attack_confirmation_pulses=6,
    max_post_attack_transition_pulses=24,
)


@dataclass(frozen=True, slots=True)
class TowerProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[TowerProgress], None]


@dataclass(frozen=True, slots=True)
class TowerCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class TowerBattleEvidence:
    label: str
    opponent: int
    trainer_class: int | None
    trainer_number: int | None
    event: int
    move_id: int
    selected_pp_spent: int
    enemy_level: int | None = None


@dataclass(frozen=True, slots=True)
class TowerChapterReport:
    records: tuple[TowerCheckpoint, ...]
    battles: tuple[TowerBattleEvidence, ...]
    final_raw: RawGameState
    optional_events: tuple[bool, ...]
    required_events: tuple[bool, ...]
    x_accuracy_carried: bool
    rare_candy_carried: bool
    elixir_carried: bool
    poke_flute_carried: bool
    evolution_before: tuple[int, int, int]
    evolution_after: tuple[int, int, int]
    evolution_moves_preserved: bool
    purified_zone_event: bool
    purified_heals: int
    super_potions_used: int
    super_potions_remaining: int
    super_potion_inventory_path: tuple[int, ...]
    party_hp: tuple[int, int, int]
    party_max_hp: tuple[int, int, int]
    party_status: tuple[int, int, int]
    money_before: int
    money_remaining: int
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == TOWER_CHECKPOINT_COUNT
            and len(self.battles) == 10
            and tuple(item.trainer_number for item in self.battles)
            == (5, 10, 14, 19, 21, 20, None, 19, 20, 21)
            and all(item.selected_pp_spent > 0 for item in self.battles)
            and self.battles[6].enemy_level == 30
            and self.optional_events == (False,) * len(OPTIONAL_EVENTS)
            and self.required_events == (True,) * len(REQUIRED_EVENTS)
            and self.x_accuracy_carried
            and self.rare_candy_carried
            and self.elixir_carried
            and self.poke_flute_carried
            and self.evolution_before == PROTECTED_PARTY
            and self.evolution_after == TOWER_FINAL_PARTY
            and self.evolution_moves_preserved
            and self.purified_zone_event
            and self.purified_heals == 3
            and bool(self.super_potion_inventory_path)
            and self.super_potion_inventory_path[0] >= HIDEOUT_SUPER_POTION_RESERVE
            and self.super_potion_inventory_path[-1] == self.super_potions_remaining
            and self.super_potions_used == len(self.super_potion_inventory_path) - 1
            and self.super_potions_used
            == self.super_potion_inventory_path[0] - self.super_potions_remaining
            and all(
                after == before - 1
                for before, after in zip(
                    self.super_potion_inventory_path,
                    self.super_potion_inventory_path[1:],
                    strict=False,
                )
            )
            and self.final_raw.map_id == MapId.LAVENDER_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and self.final_raw.party_species_ids == TOWER_FINAL_PARTY
            and self.party_hp == self.party_max_hp
            and self.party_status == (0, 0, 0)
            and self.money_before >= 0
            and self.money_remaining == self.money_before + TOWER_TRAINER_REWARD_TOTAL
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "rescue_fuji",
            "battles": [
                {
                    "label": item.label,
                    "opponent": item.opponent,
                    "class": item.trainer_class,
                    "set": item.trainer_number,
                    "event": item.event,
                    "move_id": item.move_id,
                    "selected_pp_spent": item.selected_pp_spent,
                    "enemy_level": item.enemy_level,
                }
                for item in self.battles
            ],
            "optional_trainers_bypassed": len(OPTIONAL_EVENTS),
            "required_pickups": {
                "x_accuracy": self.x_accuracy_carried,
                "rare_candy": self.rare_candy_carried,
                "elixir": self.elixir_carried,
                "poke_flute": self.poke_flute_carried,
            },
            "inventory": {
                "super_potions_used": self.super_potions_used,
                "super_potions_remaining": self.super_potions_remaining,
                "super_potion_inventory_path": list(self.super_potion_inventory_path),
                "money_before": self.money_before,
                "money_remaining": self.money_remaining,
            },
            "purified_zone": {
                "event_set": self.purified_zone_event,
                "full_party_heals": self.purified_heals,
            },
            "evolution": {
                "before": list(self.evolution_before),
                "after": list(self.evolution_after),
                "moves_preserved": self.evolution_moves_preserved,
            },
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
    wilds: list[object] = field(default_factory=list)
    trainers: list[object] = field(default_factory=list)
    potions_used: int = 0
    purified_heals: int = 0
    purified_zone_event_seen: bool = False
    evolved: bool = False
    potion_inventory: list[int] = field(default_factory=list)


def run_tower_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    timing: TowerTiming = DEFAULT_TOWER_TIMING,
    progress: ProgressSink | None = None,
) -> TowerChapterReport:
    start_frames = emulator.frame_count
    actions = _CountingExecutor(executor)
    run = _RunState()
    records: list[TowerCheckpoint] = []
    battles: list[TowerBattleEvidence] = []
    _require(reader.read(), MapId.CELADON_POKECENTER, (3, 3), "Scope boundary")
    money_before = _money(emulator)
    starting_super_potions = _bag(emulator).get(ItemId.SUPER_POTION, 0)
    if (
        ItemId.SILPH_SCOPE not in _bag(emulator)
        or starting_super_potions < HIDEOUT_SUPER_POTION_RESERVE
    ):
        raise TowerChapterError("Tower input lacks the qualified Scope resources.")
    run.potion_inventory.append(starting_super_potions)
    _checkpoint(records, progress, emulator, reader.read(), "scope_ready", "Silph Scope ready")

    for route, label in (
        (CENTER_EXIT, "Celadon Center exit"),
        (CELADON_EAST, "Celadon east"),
        (ROUTE_7, "Route 7"),
        (ROUTE_7_GATE, "Route 7 gate"),
        (WEST_GATE_TO_TUNNEL, "west underground gate"),
        (UNDERGROUND_EAST, "Underground Path"),
        (EAST_GATE_EXIT, "east underground gate"),
    ):
        _move(actions, reader, emulator, run, route, timing, label)
    _navigate_route_8_east(actions, reader, emulator, run, timing)
    for route, label in (
        (LAVENDER_TO_TOWER, "Lavender Tower entry"),
        (TOWER_1_TO_2, "Tower 2F"),
    ):
        _move(actions, reader, emulator, run, route, timing, label)
    _require(reader.read(), MapId.POKEMON_TOWER_2F, (18, 9), "Tower 2F")
    _checkpoint(records, progress, emulator, reader.read(), "tower_2f", "Reached Tower 2F")

    _wait(actions, 120)
    _move(actions, reader, emulator, run, TOWER_2_RIVAL, timing, "Tower rival")
    battles.append(
        _fight(
            actions,
            reader,
            emulator,
            timing,
            "Tower rival",
            RIVAL2,
            5,
            EventFlag.BEAT_POKEMON_TOWER_RIVAL,
            BITE,
            1,
        RedBattlePlanId.TOWER_RIVAL,
        run=run,
        bounded_recovery=True,
    )
    )
    _checkpoint(records, progress, emulator, reader.read(), "rival", "Defeated mandatory rival")
    while _party_hp(emulator)[0] < _party_max_hp(emulator)[0]:
        if _bag(emulator).get(ItemId.SUPER_POTION, 0) == 0:
            raise TowerChapterError("Rival recovery exhausted before reaching full HP.")
        _use_super_potion(actions, reader, emulator, run, DEFAULT_LAVENDER_TIMING, 0)
        run.potion_inventory.append(_bag(emulator).get(ItemId.SUPER_POTION, 0))
    _move(actions, reader, emulator, run, TOWER_2_TO_3, timing, "Tower 3F")
    _checkpoint(records, progress, emulator, reader.read(), "tower_3f", "Bypassed 3F Channelers")
    _move(actions, reader, emulator, run, TOWER_3_TO_4, timing, "Tower 4F")
    _move(actions, reader, emulator, run, TOWER_4_CHANNELER, timing, "4F Channeler")
    battles.append(
        _fight(
            actions,
            reader,
            emulator,
            timing,
            "4F Channeler",
            CHANNELER,
            10,
            EventFlag.BEAT_POKEMONTOWER_4_TRAINER_1,
            BUBBLEBEAM,
            3,
            RedBattlePlanId.TOWER_4F_CHANNELER,
        )
    )
    _checkpoint(records, progress, emulator, reader.read(), "tower_4f", "Cleared 4F Channeler")
    _move(actions, reader, emulator, run, TOWER_4_TO_ELIXIR, timing, "4F Elixir")
    _pickup(actions, reader, emulator, run, timing, "left", ItemId.ELIXIR)
    _checkpoint(records, progress, emulator, reader.read(), "elixir", "Collected Elixir")
    _move(actions, reader, emulator, run, TOWER_4_ELIXIR_TO_5, timing, "Tower 5F")
    _move(actions, reader, emulator, run, TOWER_5_HEAL, timing, "purified zone")
    _clear_text(actions, reader, timing)
    _require_purified_heal(emulator, run, "first purified heal")
    _checkpoint(records, progress, emulator, reader.read(), "purified_1", "Purified-zone heal")
    _move(actions, reader, emulator, run, TOWER_5_CHANNELER, timing, "5F Channeler")
    battles.append(
        _fight(
            actions,
            reader,
            emulator,
            timing,
            "5F Channeler",
            CHANNELER,
            14,
            EventFlag.BEAT_POKEMONTOWER_5_TRAINER_0,
            BUBBLEBEAM,
            3,
            RedBattlePlanId.TOWER_5F_CHANNELER,
        )
    )
    _move(actions, reader, emulator, run, TOWER_5_REHEAL, timing, "purified return")
    _clear_text(actions, reader, timing)
    _require_purified_heal(emulator, run, "second purified heal")
    _checkpoint(records, progress, emulator, reader.read(), "purified_2", "Re-healed after 5F")

    _move(actions, reader, emulator, run, TOWER_5_TO_6, timing, "Tower 6F")
    _move(actions, reader, emulator, run, TOWER_6_CHANNELER_19, timing, "6F Channeler 19")
    battles.append(
        _fight(
            actions,
            reader,
            emulator,
            timing,
            "6F Channeler 19",
            CHANNELER,
            19,
            EventFlag.BEAT_POKEMONTOWER_6_TRAINER_0,
            BUBBLEBEAM,
            3,
            RedBattlePlanId.TOWER_6F_CHANNELER_19,
        )
    )
    if _party_hp(emulator)[0] < _party_max_hp(emulator)[0]:
        _use_super_potion(actions, reader, emulator, run, DEFAULT_LAVENDER_TIMING, 0)
        run.potion_inventory.append(_bag(emulator).get(ItemId.SUPER_POTION, 0))
    _move(actions, reader, emulator, run, TOWER_6_CHANNELER_21, timing, "6F Channeler 21")
    battles.append(
        _fight(
            actions,
            reader,
            emulator,
            timing,
            "6F Channeler 21",
            CHANNELER,
            21,
            EventFlag.BEAT_POKEMONTOWER_6_TRAINER_2,
            BUBBLEBEAM,
            3,
            RedBattlePlanId.TOWER_6F_CHANNELER_21,
            run=run,
            bounded_recovery=True,
        )
    )
    _move(actions, reader, emulator, run, TOWER_6_TO_5, timing, "6F recovery descent")
    _move(actions, reader, emulator, run, TOWER_5_RETURN_HEAL, timing, "third purified heal")
    _clear_text(actions, reader, timing)
    _require_purified_heal(emulator, run, "third purified heal")
    _checkpoint(records, progress, emulator, reader.read(), "purified_3", "Recovered after 6F pair")
    _move(actions, reader, emulator, run, TOWER_5_FINAL_ASCENT, timing, "final 6F ascent")
    _move(actions, reader, emulator, run, TOWER_6_CHANNELER_20, timing, "6F Channeler 20")
    battles.append(
        _fight(
            actions,
            reader,
            emulator,
            timing,
            "6F Channeler 20",
            CHANNELER,
            20,
            EventFlag.BEAT_POKEMONTOWER_6_TRAINER_1,
            BUBBLEBEAM,
            3,
            RedBattlePlanId.TOWER_6F_CHANNELER_20,
        )
    )
    _checkpoint(
        records, progress, emulator, reader.read(), "channelers", "Cleared mandatory Channelers"
    )

    _move(actions, reader, emulator, run, TOWER_6_X_ACCURACY, timing, "X Accuracy")
    _pickup(actions, reader, emulator, run, timing, "left", ItemId.X_ACCURACY)
    _checkpoint(
        records, progress, emulator, reader.read(), "x_accuracy", "Removed X Accuracy object"
    )
    _move(actions, reader, emulator, run, TOWER_6_RARE_CANDY, timing, "Rare Candy")
    _pickup(actions, reader, emulator, run, timing, "down", ItemId.RARE_CANDY)
    _checkpoint(records, progress, emulator, reader.read(), "rare_candy", "Removed Rare Candy gate")
    _move(actions, reader, emulator, run, TOWER_6_MAROWAK, timing, "Marowak")
    battles.append(_fight_marowak(actions, reader, emulator, timing))
    _checkpoint(records, progress, emulator, reader.read(), "marowak", "Calmed Marowak")

    _move(actions, reader, emulator, run, TOWER_7_ROCKET_1, timing, "Tower 7F")
    battles.append(
        _fight(
            actions,
            reader,
            emulator,
            timing,
            "7F Rocket 19",
            ROCKET,
            19,
            EventFlag.BEAT_POKEMONTOWER_7_TRAINER_0,
            BITE,
            1,
            RedBattlePlanId.TOWER_7F_ROCKET_19,
            interact_direction="up",
            run=run,
        )
    )
    _checkpoint(records, progress, emulator, reader.read(), "rocket_19", "Defeated first Rocket")
    if _party_hp(emulator)[0] < _party_max_hp(emulator)[0]:
        _use_super_potion(actions, reader, emulator, run, DEFAULT_LAVENDER_TIMING, 0)
        run.potion_inventory.append(_bag(emulator).get(ItemId.SUPER_POTION, 0))
    _move(actions, reader, emulator, run, TOWER_7_ROCKET_2, timing, "second Rocket")
    battles.append(
        _fight(
            actions,
            reader,
            emulator,
            timing,
            "7F Rocket 20",
            ROCKET,
            20,
            EventFlag.BEAT_POKEMONTOWER_7_TRAINER_1,
            BITE,
            1,
            RedBattlePlanId.TOWER_7F_ROCKET_20,
        )
    )
    _checkpoint(records, progress, emulator, reader.read(), "rocket_20", "Defeated second Rocket")
    while _party_hp(emulator)[0] < _party_max_hp(emulator)[0]:
        if _bag(emulator).get(ItemId.SUPER_POTION, 0) == 0:
            raise TowerChapterError("Third Rocket recovery exhausted before full HP.")
        _use_super_potion(actions, reader, emulator, run, DEFAULT_LAVENDER_TIMING, 0)
        run.potion_inventory.append(_bag(emulator).get(ItemId.SUPER_POTION, 0))
    _move(actions, reader, emulator, run, TOWER_7_ROCKET_3, timing, "third Rocket")
    evolution_start = reader.read()
    battles.append(
        _fight(
            actions,
            reader,
            emulator,
            timing,
            "7F Rocket 21",
            ROCKET,
            21,
            EventFlag.BEAT_POKEMONTOWER_7_TRAINER_2,
            BUBBLEBEAM,
            3,
            RedBattlePlanId.TOWER_7F_ROCKET_21,
            clear_after=False,
            battle_timing=TOWER_EVOLUTION_BATTLE_TIMING,
            unknown_cancel_interval=5,
            bounded_recovery=True,
            recovery_hp_threshold=70,
            run=run,
        )
    )
    evolution_before, evolution_after, evolution_moves_preserved = _qualify_evolution(
        actions, reader, run, evolution_start
    )
    _checkpoint(records, progress, emulator, reader.read(), "rocket_21", "Defeated third Rocket")

    _move(actions, reader, emulator, run, TOWER_7_FUJI, timing, "Mr Fuji")
    _interact_until_map(actions, reader, timing, "up", MapId.MR_FUJIS_HOUSE)
    _require(
        reader.read(),
        MapId.MR_FUJIS_HOUSE,
        (3, 7),
        "Fuji rescue warp",
        TOWER_FINAL_PARTY,
    )
    if not _event(emulator, EventFlag.RESCUED_MR_FUJI) or not _event(
        emulator, EventFlag.RESCUED_MR_FUJI_WORLD
    ):
        raise TowerChapterError("Fuji rescue did not set both mirrored events.")
    _checkpoint(records, progress, emulator, reader.read(), "fuji_rescued", "Rescued Mr Fuji")
    _clear_text(actions, reader, timing)
    _move(actions, reader, emulator, run, FUJI_HOUSE_TO_FUJI, timing, "Fuji reward")
    _interact_until_item(actions, reader, emulator, timing, "up", ItemId.POKE_FLUTE)
    _clear_text(actions, reader, timing)
    if not _event(emulator, EventFlag.GOT_POKE_FLUTE):
        raise TowerChapterError("Poké Flute event did not follow the item reward.")
    _checkpoint(records, progress, emulator, reader.read(), "poke_flute", "Received Poké Flute")

    _move(actions, reader, emulator, run, FUJI_HOUSE_EXIT, timing, "Fuji house exit")
    _move(actions, reader, emulator, run, LAVENDER_TO_CENTER, timing, "Lavender Center")
    _heal_center(actions, reader, emulator, run, timing)
    final = reader.read()
    _require(
        final,
        MapId.LAVENDER_POKECENTER,
        (3, 3),
        "stable Flute boundary",
        TOWER_FINAL_PARTY,
    )
    for checkpoint_id, label in (
        ("tower_cleared", "Pokémon Tower cleared"),
        ("fuji_verified", "Fuji rescue verified"),
        ("flute_verified", "Poké Flute verified"),
        ("resources_verified", "Resources verified"),
        ("objective_ready", "Fuji objective input-ready"),
        ("semantic_gate", "Objective semantics verified"),
        ("party_verified", "Party verified"),
        ("controller_verified", "Controller released"),
        ("lavender_stable", "Stable Lavender boundary"),
        ("chapter_complete", "Tower chapter complete"),
    ):
        _checkpoint(records, progress, emulator, final, checkpoint_id, label)

    report = TowerChapterReport(
        tuple(records),
        tuple(battles),
        final,
        tuple(_event(emulator, item) for item in OPTIONAL_EVENTS),
        tuple(_event(emulator, item) for item in REQUIRED_EVENTS),
        ItemId.X_ACCURACY in _bag(emulator),
        ItemId.RARE_CANDY in _bag(emulator),
        ItemId.ELIXIR in _bag(emulator),
        ItemId.POKE_FLUTE in _bag(emulator),
        evolution_before,
        evolution_after,
        evolution_moves_preserved,
        run.purified_zone_event_seen,
        run.purified_heals,
        run.potions_used,
        _bag(emulator).get(ItemId.SUPER_POTION, 0),
        tuple(run.potion_inventory),
        _party_hp(emulator),
        _party_max_hp(emulator),
        _party_status(emulator),
        money_before,
        _money(emulator),
        emulator.frame_count - start_frames,
        actions.actions_executed,
        not emulator.pressed_buttons,
    )
    if not report.passed:
        raise TowerChapterError(f"Tower evidence contract failed: {report.public_dict()!r}.")
    return report


class _PauseForTowerSuperPotion(Exception):
    pass


class _PauseForTowerAwakening(Exception):
    pass


class _PauseForTowerParlyzHeal(Exception):
    pass


def _use_tower_battle_status_item(
    reader: PokemonRedStateReader,
    actions: _CountingExecutor,
    emulator: EmulatorState,
    label: str,
    *,
    item: ItemId,
    expected_status: int,
) -> None:
    before = reader.read()
    menu = reader.read_battle_menu_state(before)
    before_quantity = _bag(emulator).get(item, 0)
    item_label = "Awakening" if item is ItemId.AWAKENING else "Parlyz Heal"
    if (
        before.battle_state != 2
        or before.first_party_status != expected_status
        or before_quantity < 1
        or menu.phase is not BattleMenuPhase.MAIN
    ):
        raise TowerChapterError(f"{label} {item_label} lacks its stable status gate.")

    wait_frames = DEFAULT_LAVENDER_TIMING.wait_frames
    command = menu.selected_main_command
    if command == 0:
        _pulse(actions, MacroActionKind.MOVE, "down", frames=wait_frames)
    elif command == 2:
        _pulse(actions, MacroActionKind.MOVE, "left", frames=wait_frames)
        _pulse(actions, MacroActionKind.MOVE, "down", frames=wait_frames)
    elif command == 3:
        _pulse(actions, MacroActionKind.MOVE, "left", frames=wait_frames)
    elif command != 1:
        raise TowerChapterError(f"{label} {item_label} exposed an invalid command cursor.")

    selected = reader.read_battle_menu_state(reader.read())
    if selected.phase is not BattleMenuPhase.MAIN or selected.selected_main_command != 1:
        raise TowerChapterError(f"{label} {item_label} could not select ITEM.")
    _pulse(actions, MacroActionKind.CONFIRM, frames=wait_frames)
    _select_bag_item(actions, emulator, item, DEFAULT_LAVENDER_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM, frames=wait_frames)
    _select_cursor(actions, emulator, 0, DEFAULT_LAVENDER_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM, frames=1)
    saw_cure = False
    saw_consumption = False
    for _ in range(DEFAULT_LAVENDER_TIMING.dialogue_pulses * 20):
        current = reader.read()
        if current.first_party_status == 0:
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
        if current.battle_state != 2 or (current.first_party_hp or 0) <= 0:
            raise TowerChapterError(f"{label} {item_label} lost the active battle.")
        _pulse(actions, MacroActionKind.CANCEL, frames=1)
    final = reader.read()
    raise TowerChapterError(
        f"{label} {item_label} missed its bounded cure proof: "
        f"saw_cure={saw_cure}, saw_consumption={saw_consumption}, "
        f"status={final.first_party_status}, hp={final.first_party_hp}, "
        f"quantity={_bag(emulator).get(item, 0)}, "
        f"phase={reader.read_battle_menu_state(final).phase.value}."
    )


def _fight(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: TowerTiming,
    label: str,
    identity: tuple[int, int],
    trainer_number: int,
    event: EventFlag,
    move_id: int,
    move_slot: int,
    battle_plan_id: str,
    *,
    interact_direction: str | None = None,
    clear_after: bool = True,
    battle_timing: BattleRuntimeTiming = TOWER_BATTLE_TIMING,
    run: _RunState | None = None,
    unknown_cancel_interval: int = 3,
    bounded_recovery: bool = False,
    recovery_hp_threshold: int = 40,
) -> TowerBattleEvidence:
    if interact_direction is not None:
        for _attempt in range(3):
            _pulse(actions, MacroActionKind.MOVE, interact_direction, frames=120)
            if reader.read().battle_state == 1:
                if run is None:
                    raise TowerChapterError(f"A wild battle interrupted {label}.")
                _flee(
                    actions,
                    reader,
                    emulator,
                    run,
                    TOWER_LAVENDER_TIMING,
                    unknown_with_cancel=True,
                )
                continue
            actions.execute(MacroAction(MacroActionKind.INTERACT))
            break
        else:
            raise TowerChapterError(f"Wild battles repeatedly interrupted {label}.")
    battle = _enter_battle(actions, reader, timing, label, 2)
    observed = _scripted_trainer_identity(emulator)
    if observed != (*identity, trainer_number):
        raise TowerChapterError(f"{label} identity mismatch: {observed!r}.")
    before_pp = battle.first_party_pp
    intent = BattleIntent(
        "rescue_fuji",
        battle_plan_id=battle_plan_id,
        resource_policy=(
            BattleResourcePolicy.BOUNDED_RECOVERY
            if bounded_recovery
            else BattleResourcePolicy.NO_ADDITIONAL_CONSTRAINT
        ),
        required_move_policy=RequiredMovePolicy.ANY_USABLE,
        required_move_ref=None,
    )

    def policy(raw: RawGameState) -> int:
        if (
            bounded_recovery
            and (raw.first_party_status or 0) & 0x07
            and _bag(emulator).get(ItemId.AWAKENING, 0) > 0
        ):
            raise _PauseForTowerAwakening
        if (
            bounded_recovery
            and raw.first_party_status == 0x40
            and _bag(emulator).get(ItemId.PARLYZ_HEAL, 0) > 0
        ):
            raise _PauseForTowerParlyzHeal
        if (
            bounded_recovery
            and (raw.first_party_hp or 0) <= recovery_hp_threshold
            and _bag(emulator).get(ItemId.SUPER_POTION, 0) > 0
        ):
            raise _PauseForTowerSuperPotion
        preferred = (
            3
            if bounded_recovery
            and raw.enemy_species_id in {PIDGEOTTO_SPECIES_ID, TOWER_RIVAL_GROWLITHE}
            else move_slot
        )
        moves = raw.first_party_moves
        pp = raw.first_party_pp
        if moves is None or pp is None:
            raise TowerChapterError(f"{label} lacks live move and PP evidence.")
        for candidate in dict.fromkeys((preferred, move_slot, 3, 4)):
            index = candidate - 1
            if (
                len(moves) > index
                and len(pp) > index
                and moves[index] != 0
                and pp[index] & 0x3F
                and raw.player_disabled_move_slot != candidate
            ):
                return candidate
        raise TowerChapterError(f"{label} has no usable ranked attack.")

    while True:
        try:
            final = run_adaptive_trainer_battle(
                reader,
                actions,
                policy,
                expected_map=int(battle.map_id or 0),
                intent=intent,
                required_move_id=None,
                timing=battle_timing,
                label=label,
                unknown_cancel_interval=unknown_cancel_interval,
            )
            break
        except BattleRuntimeError as error:
            if isinstance(error.__cause__, _PauseForTowerAwakening):
                _use_tower_battle_status_item(
                    reader,
                    actions,
                    emulator,
                    label,
                    item=ItemId.AWAKENING,
                    expected_status=reader.read().first_party_status or 0,
                )
                continue
            if isinstance(error.__cause__, _PauseForTowerParlyzHeal):
                _use_tower_battle_status_item(
                    reader,
                    actions,
                    emulator,
                    label,
                    item=ItemId.PARLYZ_HEAL,
                    expected_status=0x40,
                )
                continue
            if not isinstance(error.__cause__, _PauseForTowerSuperPotion):
                raise
        if run is None:
            raise TowerChapterError(f"{label} recovery lacks its chapter resource ledger.")
        _use_battle_super_potion(
            reader,
            actions,
            emulator,
            run,
            TOWER_LAVENDER_TIMING,
            label,
        )
        run.potion_inventory.append(_bag(emulator).get(ItemId.SUPER_POTION, 0))
    if before_pp is None or final.first_party_pp is None:
        raise TowerChapterError(f"{label} lacks PP evidence.")
    spent = (before_pp[move_slot - 1] & 0x3F) - (final.first_party_pp[move_slot - 1] & 0x3F)
    if clear_after:
        _clear_text(actions, reader, timing)
    if not _event(emulator, event):
        raise TowerChapterError(f"{label} did not set event {int(event):#05x}.")
    return TowerBattleEvidence(
        label, identity[0], identity[1], trainer_number, int(event), move_id, spent
    )


def _scripted_trainer_identity(emulator: EmulatorState) -> tuple[int, int, int]:
    """Read scripted identity fields, never the stale engagement-set mirror."""
    return (
        emulator.read_u8(RamAddress.CURRENT_OPPONENT),
        emulator.read_u8(RamAddress.TRAINER_CLASS),
        emulator.read_u8(RamAddress.TRAINER_NUMBER),
    )


def _fight_marowak(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: TowerTiming,
) -> TowerBattleEvidence:
    battle = _enter_battle(actions, reader, timing, "restless Marowak", 1)
    if (
        ItemId.SILPH_SCOPE not in _bag(emulator)
        or battle.enemy_species_id != MAROWAK
        or battle.enemy_level != 30
        or emulator.read_u8(RamAddress.CURRENT_OPPONENT) != MAROWAK
    ):
        raise TowerChapterError("Silph Scope did not reveal the level-30 Marowak.")
    before = battle.first_party_pp
    if (
        before is None
        or battle.first_party_moves is None
        or battle.first_party_moves[2] != BUBBLEBEAM
    ):
        raise TowerChapterError("Marowak lacks BubbleBeam PP evidence.")
    for _pulse_index in range(160):
        raw = reader.read()
        if raw.battle_state == 0:
            _clear_text(actions, reader, timing)
            break
        if raw.battle_state != 1:
            raise TowerChapterError("Marowak changed to an invalid battle state.")
        menu = reader.read_battle_menu_state(raw)
        if menu.phase is BattleMenuPhase.UNKNOWN:
            _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
        elif menu.phase is BattleMenuPhase.MAIN:
            command = menu.selected_main_command
            if command == 0:
                _pulse(actions, MacroActionKind.CONFIRM, frames=120)
            else:
                direction = {1: "up", 2: "left", 3: "up"}.get(command)
                if direction is None:
                    raise TowerChapterError("Marowak exposed an invalid command cursor.")
                _pulse(actions, MacroActionKind.MOVE, direction, frames=120)
        else:
            slot = menu.selected_move_slot
            if slot == 3:
                _pulse(actions, MacroActionKind.CONFIRM, frames=240)
            elif slot is None:
                raise TowerChapterError("Marowak exposed an invalid move cursor.")
            else:
                _pulse(actions, MacroActionKind.MOVE, "down" if slot < 3 else "up", frames=120)
    else:
        raise TowerChapterError("Marowak battle exceeded its bounded runtime.")
    final = reader.read()
    if final.first_party_pp is None:
        raise TowerChapterError("Marowak final PP is unavailable.")
    spent = (before[2] & 0x3F) - (final.first_party_pp[2] & 0x3F)
    if spent <= 0 or not _event(emulator, EventFlag.BEAT_GHOST_MAROWAK):
        raise TowerChapterError("Marowak victory lacks PP/event evidence.")
    return TowerBattleEvidence(
        "restless Marowak",
        MAROWAK,
        None,
        None,
        int(EventFlag.BEAT_GHOST_MAROWAK),
        BUBBLEBEAM,
        spent,
        30,
    )


def _route_8_coordinate_is_safe(coordinate: tuple[int, int]) -> bool:
    x, y = coordinate
    return (
        0 <= y < len(ROUTE_8_SAFE_ROW_MASKS)
        and 0 <= x < 60
        and bool(ROUTE_8_SAFE_ROW_MASKS[y] & (1 << x))
    )


def _plan_route_8_east(
    start: tuple[int, int],
    blocked: frozenset[tuple[int, int]] = frozenset(),
) -> tuple[str, ...]:
    if not 0 <= start[0] < 60 or not 0 <= start[1] < 18:
        raise TowerChapterError(f"Route 8 planner started out of bounds at {start!r}.")
    queue = deque([(start, ())])
    visited = {start}
    steps = (
        ("right", (1, 0)),
        ("up", (0, -1)),
        ("down", (0, 1)),
        ("left", (-1, 0)),
    )
    while queue:
        coordinate, route = queue.popleft()
        if coordinate == ROUTE_8_EAST_GOAL:
            return route
        for direction, (dx, dy) in steps:
            candidate = (coordinate[0] + dx, coordinate[1] + dy)
            if (
                candidate in visited
                or candidate in blocked
                or not _route_8_coordinate_is_safe(candidate)
            ):
                continue
            visited.add(candidate)
            queue.append((candidate, (*route, direction)))
    raise TowerChapterError(
        f"Route 8 has no trainer-safe path from {start!r} after discoveries "
        f"{sorted(blocked)!r}."
    )


def _navigate_route_8_east(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    timing: TowerTiming,
) -> RawGameState:
    """Replan over the source-derived collision map without optional trainers."""

    state = reader.read()
    if (
        state.map_id != MapId.ROUTE_8
        or state.player_x is None
        or state.player_y is None
    ):
        raise TowerChapterError("Adaptive Route 8 navigation lacks its entry coordinate.")
    discovered_blocked: set[tuple[int, int]] = set()
    deltas = {"up": (0, -1), "left": (-1, 0), "right": (1, 0), "down": (0, 1)}
    for _ in range(180):
        start = (state.player_x, state.player_y)
        if start == ROUTE_8_EAST_GOAL:
            final = _move(
                actions,
                reader,
                emulator,
                run,
                ("right",),
                timing,
                "Route 8 Lavender boundary",
            )
            if final.map_id != MapId.LAVENDER_TOWN:
                raise TowerChapterError("Route 8 east goal did not enter Lavender Town.")
            return final
        route = _plan_route_8_east(start, frozenset(discovered_blocked))
        direction = route[0]
        dx, dy = deltas[direction]
        candidate = (start[0] + dx, start[1] + dy)
        for attempt in range(timing.movement_retries):
            _pulse(actions, MacroActionKind.MOVE, direction, frames=12 * (attempt + 1))
            state = reader.read()
            if state.battle_state == 1:
                _flee(
                    actions,
                    reader,
                    emulator,
                    run,
                    TOWER_LAVENDER_TIMING,
                    unknown_with_cancel=True,
                )
                state = reader.read()
            if state.battle_state == 2:
                raise TowerChapterError(
                    "Adaptive Route 8 navigation entered an optional trainer battle."
                )
            if (state.player_x, state.player_y) != start:
                break
            if not reader.read_input_readiness().ready:
                _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
                state = reader.read()
        else:
            discovered_blocked.add(candidate)
        expected_party = TOWER_FINAL_PARTY if run.evolved else PROTECTED_PARTY
        if state.party_species_ids != expected_party or (state.first_party_hp or 0) <= 0:
            raise TowerChapterError(
                "Adaptive Route 8 navigation changed the protected party."
            )
    raise TowerChapterError("Adaptive Route 8 navigation exceeded its bounded discoveries.")


def _move(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    directions: Iterable[str],
    timing: TowerTiming,
    label: str,
) -> RawGameState:
    state = reader.read()
    for step, direction in enumerate(directions, 1):
        before = (state.map_id, state.player_x, state.player_y)
        for attempt in range(timing.movement_retries):
            _pulse(actions, MacroActionKind.MOVE, direction, frames=12 * (attempt + 1))
            state = reader.read()
            if state.battle_state == 1:
                _flee(
                    actions,
                    reader,
                    emulator,
                    run,
                    TOWER_LAVENDER_TIMING,
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
            raise TowerChapterError(
                f"{label} blocked at step {step}: {direction}; "
                f"map={state.map_id!r}, coordinate={(state.player_x, state.player_y)!r}."
            )
        expected_party = TOWER_FINAL_PARTY if run.evolved else PROTECTED_PARTY
        if state.party_species_ids != expected_party or (state.first_party_hp or 0) <= 0:
            raise TowerChapterError(
                f"{label} changed the protected party: {state.party_species_ids!r}, "
                f"lead_hp={state.first_party_hp!r}."
            )
    _wait(actions, timing.transition_frames)
    return reader.read()


def _enter_battle(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: TowerTiming,
    label: str,
    battle_state: int,
) -> RawGameState:
    for _ in range(timing.dialogue_pulses):
        raw = reader.read()
        if raw.battle_state == battle_state:
            return raw
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    raise TowerChapterError(f"{label} did not enter battle state {battle_state}.")


def _pickup(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    timing: TowerTiming,
    direction: str,
    item: ItemId,
) -> None:
    for _attempt in range(3):
        _pulse(actions, MacroActionKind.MOVE, direction, frames=120)
        if reader.read().battle_state == 1:
            _flee(
                actions,
                reader,
                emulator,
                run,
                TOWER_LAVENDER_TIMING,
                unknown_with_cancel=True,
            )
            continue
        if reader.read().battle_state != 0:
            raise TowerChapterError("A trainer battle interrupted a required pickup.")
        actions.execute(MacroAction(MacroActionKind.INTERACT))
        for _ in range(timing.dialogue_pulses):
            _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
            if item in _bag(emulator):
                _clear_text(actions, reader, timing)
                return
        _clear_text(actions, reader, timing)
    raw = reader.read()
    raise TowerChapterError(
        f"Required pickup {int(item):#04x} failed at "
        f"map={raw.map_id!r}, coordinate={(raw.player_x, raw.player_y)!r}."
    )


def _interact_until_map(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: TowerTiming,
    direction: str,
    target: MapId,
) -> None:
    _pulse(actions, MacroActionKind.MOVE, direction, frames=120)
    actions.execute(MacroAction(MacroActionKind.INTERACT))
    for _ in range(timing.dialogue_pulses):
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
        if reader.read().map_id == target:
            _wait(actions, timing.transition_frames)
            return
    raise TowerChapterError(f"Interaction did not reach map {int(target):#04x}.")


def _interact_until_item(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: TowerTiming,
    direction: str,
    item: ItemId,
) -> None:
    _pulse(actions, MacroActionKind.MOVE, direction, frames=120)
    actions.execute(MacroAction(MacroActionKind.INTERACT))
    for _ in range(timing.dialogue_pulses):
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
        if item in _bag(emulator):
            return
    raise TowerChapterError(f"Interaction did not obtain item {int(item):#04x}.")


def _heal_center(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    timing: TowerTiming,
) -> None:
    _require(
        reader.read(),
        MapId.LAVENDER_POKECENTER,
        (3, 7),
        "Lavender Center",
        TOWER_FINAL_PARTY,
    )
    _move(actions, reader, emulator, run, ("up",) * 4, timing, "Lavender nurse")
    for _ in range(16):
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
        if _party_hp(emulator) == _party_max_hp(emulator) and _party_status(emulator) == (0, 0, 0):
            _clear_text(actions, reader, timing)
            return
    raise TowerChapterError("Lavender Center did not heal the party.")


def _clear_text(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: TowerTiming,
) -> None:
    for _ in range(6):
        _pulse(actions, MacroActionKind.CANCEL, frames=timing.wait_frames)
    if not reader.read_input_readiness().ready:
        raise TowerChapterError("Dialogue did not return input authority.")


def _qualify_evolution(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    run: _RunState,
    before: RawGameState,
) -> tuple[tuple[int, int, int], tuple[int, int, int], bool]:
    if before.party_species_ids != PROTECTED_PARTY or before.first_party_moves is None:
        raise TowerChapterError("Evolution did not start from the qualified Wartortle party.")
    after = reader.read()
    for _ in range(32):
        if after.party_species_ids == TOWER_FINAL_PARTY:
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=180)
        after = reader.read()
    if (
        after.party_species_ids != TOWER_FINAL_PARTY
        or after.first_party_moves != before.first_party_moves
        or (after.first_party_hp or 0) <= 0
    ):
        raise TowerChapterError(
            "Level-36 evolution did not preserve the qualified party semantics: "
            f"before_party={before.party_species_ids!r}, "
            f"after_party={after.party_species_ids!r}, "
            f"before_moves={before.first_party_moves!r}, "
            f"after_moves={after.first_party_moves!r}, "
            f"after_hp={after.first_party_hp!r}, after_status={after.first_party_status!r}."
        )
    run.evolved = True
    return PROTECTED_PARTY, TOWER_FINAL_PARTY, True


def _require_purified_heal(
    emulator: EmulatorState,
    run: _RunState,
    label: str,
) -> None:
    if _party_hp(emulator) != _party_max_hp(emulator) or _party_status(emulator) != (0, 0, 0):
        raise TowerChapterError(f"{label} did not restore the complete party.")
    if not _event(emulator, EventFlag.IN_PURIFIED_ZONE):
        raise TowerChapterError(f"{label} did not set the purified-zone event.")
    run.purified_zone_event_seen = True
    run.purified_heals += 1


def _event(emulator: EmulatorState, event: EventFlag) -> bool:
    value = int(event)
    return bool(emulator.read_u8(int(RamAddress.EVENT_FLAGS) + value // 8) & (1 << (value % 8)))


def _checkpoint(
    records: list[TowerCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(TowerCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            TowerProgress(
                checkpoint_id, label, len(records), TOWER_CHECKPOINT_COUNT, emulator.frame_count
            )
        )


def _require(
    raw: RawGameState,
    map_id: int,
    coordinate: tuple[int, int],
    label: str,
    party: tuple[int, int, int] = PROTECTED_PARTY,
) -> None:
    if (
        raw.map_id != map_id
        or (raw.player_x, raw.player_y) != coordinate
        or raw.battle_state != 0
        or raw.party_species_ids != party
    ):
        raise TowerChapterError(
            f"{label} missed gate: map={raw.map_id!r}, "
            f"coordinate={(raw.player_x, raw.player_y)!r}, battle={raw.battle_state!r}."
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
