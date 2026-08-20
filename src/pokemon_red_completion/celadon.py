"""Qualified Lavender-to-Celadon traversal for pinned Pokémon Red.

The chapter crosses Route 8 and the west-east Underground Path, proves the
single unavoidable trainer identity and event transition, and stops only at a
healed, input-ready Celadon Pokémon Center boundary.
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
    note_observed_battle_exit,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.economy import (
    LAVENDER_SUPER_POTION_RESERVE,
)
from pokemon_red_completion.executor import ChapterExecutor, CountingExecutor
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
from pokemon_red_completion.red_party import PARTY_STRUCT_STRIDE

CELADON_CHECKPOINT_COUNT = 12
WARTORTLE = 0xB3
DUX = 0x40
DIGLETT = 0x3B
BITE = 0x2C
ROUTE_8_TRAINER_REWARD = 330
PROTECTED_PARTY = (WARTORTLE, DUX, DIGLETT)
ROUTE_8_EVENTS = tuple(
    EventFlag(int(EventFlag.BEAT_ROUTE_8_TRAINER_0) + index) for index in range(9)
)


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "D": "down", "L": "left", "R": "right"}[c] for c in value)


CENTER_EXIT = _directions("DDDDD")
LAVENDER_TO_ROUTE_8 = _directions("LLLDDL")
ROUTE_8_TRAINER_TRIGGER = _directions("LLLLDDDDDLLLLLU")
ROUTE_8_AFTER_TRAINER = _directions("LLLLUUUUULLLLLULLLLLLLLLLLLDLDDDDDLLLLLLLLLLLLUUUUULL")
ROUTE_8_TO_GATE = _directions("UUULU")
GATE_TO_TUNNEL = _directions("RUUU")
TUNNEL_TO_ROUTE_7_GATE = _directions("DDD" + "L" * 45)
ROUTE_7_GATE_EXIT = _directions("DDDD")
ROUTE_7_TO_CELADON = _directions("RRRUUUUUULLLLUUUUULLLLL")
CELADON_TO_CENTER = _directions("ULLLLLLLLU")


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class CeladonChapterError(RuntimeError):
    """Raised when the qualified Celadon route loses semantic evidence."""


@dataclass(frozen=True, slots=True)
class CeladonTiming:
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


DEFAULT_CELADON_TIMING = CeladonTiming()


@dataclass(frozen=True, slots=True)
class CeladonProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[CeladonProgress], None]


@dataclass(frozen=True, slots=True)
class CeladonCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class Route8TrainerEvidence:
    label: str
    map_id: int
    event: int
    opponent: int
    trainer_class: int
    trainer_set: int
    move_id: int
    selected_pp_spent: int


@dataclass(frozen=True, slots=True)
class CeladonWildFleeEvidence:
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
class CeladonChapterReport:
    records: tuple[CeladonCheckpoint, ...]
    trainers: tuple[Route8TrainerEvidence, ...]
    wild_flees: tuple[CeladonWildFleeEvidence, ...]
    route_8_events_before: tuple[bool, ...]
    route_8_events_after: tuple[bool, ...]
    final_raw: RawGameState
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    super_potions_remaining: int
    repels_remaining: int
    money_before: int
    money_remaining: int
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == CELADON_CHECKPOINT_COUNT
            and len(self.trainers) == 1
            and self.trainers[0].event == EventFlag.BEAT_ROUTE_8_TRAINER_8
            and self.trainers[0].move_id == BITE
            and self.trainers[0].selected_pp_spent > 0
            and self.route_8_events_before == (False,) * 9
            and self.route_8_events_after == (False,) * 8 + (True,)
            and all(
                item.party_preserved
                and item.pp_preserved
                and item.hp_safe
                and item.inventory_preserved
                for item in self.wild_flees
            )
            and self.final_raw.map_id == MapId.CELADON_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and self.final_raw.party_species_ids == PROTECTED_PARTY
            and self.final_raw.battle_state == 0
            and self.party_hp == self.party_max_hp
            and all(status == 0 for status in self.party_status)
            and self.super_potions_remaining == LAVENDER_SUPER_POTION_RESERVE
            and self.repels_remaining == 0
            and self.money_before >= 0
            and self.money_remaining == self.money_before + ROUTE_8_TRAINER_REWARD
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        trainer = self.trainers[0]
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "reach_celadon",
            "trainer_battles": [
                {
                    "label": trainer.label,
                    "map_id": trainer.map_id,
                    "event": trainer.event,
                    "opponent": trainer.opponent,
                    "class": trainer.trainer_class,
                    "set": trainer.trainer_set,
                    "move_id": trainer.move_id,
                    "selected_pp_spent": trainer.selected_pp_spent,
                }
            ],
            "route_8_trainers_bypassed": [
                index for index, defeated in enumerate(self.route_8_events_after) if not defeated
            ],
            "wild_flees": len(self.wild_flees),
            "inventory": {
                "super_potions_remaining": self.super_potions_remaining,
                "repels_remaining": self.repels_remaining,
                "money_before": self.money_before,
                "money_remaining": self.money_remaining,
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


@dataclass(slots=True)
class _RunState:
    wilds: list[CeladonWildFleeEvidence]


def run_celadon_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    timing: CeladonTiming = DEFAULT_CELADON_TIMING,
    progress: ProgressSink | None = None,
) -> CeladonChapterReport:
    """Continue the verified Lavender boundary to a stable Celadon Center."""

    start_frames = emulator.frame_count
    actions = CountingExecutor(executor)
    run = _RunState([])
    records: list[CeladonCheckpoint] = []
    start = reader.read()
    _require(start, MapId.LAVENDER_POKECENTER, (3, 3), "Lavender terminal boundary")
    _require_resources(emulator)
    money_before = _money(emulator)
    events_before = _events(emulator)
    if events_before != (False,) * 9:
        raise CeladonChapterError(f"Route 8 trainer events were not pristine: {events_before!r}.")
    _checkpoint(records, progress, emulator, start, "lavender_ready", "Verified Lavender boundary")

    _move(actions, reader, emulator, run, CENTER_EXIT, timing, "Lavender Center exit")
    _wait(actions, timing.transition_frames)
    raw = reader.read()
    _require(raw, MapId.LAVENDER_TOWN, (3, 6), "Lavender Center exterior")
    _checkpoint(records, progress, emulator, raw, "lavender_exited", "Exited Lavender Center")

    _move(actions, reader, emulator, run, LAVENDER_TO_ROUTE_8, timing, "Route 8 entrance")
    _wait(actions, timing.transition_frames)
    raw = reader.read()
    _require(raw, MapId.ROUTE_8, (59, 8), "Route 8 east entrance")
    _checkpoint(records, progress, emulator, raw, "route8_reached", "Reached Route 8")

    _move(
        actions,
        reader,
        emulator,
        run,
        ROUTE_8_TRAINER_TRIGGER,
        timing,
        "Route 8 Lass",
        allow_trainer=True,
    )
    battle = _enter_trainer_battle(actions, reader, timing, "Route 8 Lass")
    identity = (
        emulator.read_u8(RamAddress.CURRENT_OPPONENT),
        emulator.read_u8(RamAddress.TRAINER_CLASS),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_CLASS),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_SET),
    )
    if battle.map_id != MapId.ROUTE_8 or identity != (0xCB, 0x03, 0xCB, 16):
        raise CeladonChapterError(f"Route 8 Lass identity mismatch: {identity!r}.")
    _checkpoint(
        records, progress, emulator, battle, "route8_trainer8_battle", "Verified Route 8 Lass"
    )
    before_pp = battle.first_party_pp
    final_battle = run_adaptive_trainer_battle(
        reader,
        actions,
        lambda _: 1,
        expected_map=int(MapId.ROUTE_8),
        intent=BattleIntent(
            "reach_celadon",
            battle_plan_id=RedBattlePlanId.CELADON_ROUTE_8_LASS,
            required_move_policy=RequiredMovePolicy.EXACT_REQUIRED,
            required_move_ref=pokemon_red_move_ref(BITE),
        ),
        required_move_id=BITE,
        label="Route 8 Lass",
    )
    if before_pp is None or final_battle.first_party_pp is None:
        raise CeladonChapterError("Route 8 Lass lacks PP evidence.")
    spent = (before_pp[0] & 0x3F) - (final_battle.first_party_pp[0] & 0x3F)
    if spent <= 0 or _events(emulator) != (False,) * 8 + (True,):
        raise CeladonChapterError("Route 8 Lass missed its move/event transition proof.")
    trainer = Route8TrainerEvidence(
        "Route 8 Lass",
        int(MapId.ROUTE_8),
        int(EventFlag.BEAT_ROUTE_8_TRAINER_8),
        0xCB,
        0x03,
        16,
        BITE,
        spent,
    )
    _checkpoint(
        records,
        progress,
        emulator,
        final_battle,
        "route8_trainer8_defeated",
        "Defeated only the required Route 8 trainer",
    )

    _move(actions, reader, emulator, run, ROUTE_8_AFTER_TRAINER, timing, "Route 8 westbound")
    raw = reader.read()
    _require(raw, MapId.ROUTE_8, (14, 7), "Route 8 west approach")
    _checkpoint(records, progress, emulator, raw, "route8_entrance", "Reached Route 8 gate")

    _move(actions, reader, emulator, run, ROUTE_8_TO_GATE, timing, "Route 8 gate entry")
    _wait(actions, timing.transition_frames)
    raw = reader.read()
    _require(raw, MapId.UNDERGROUND_PATH_ROUTE_8, (3, 7), "Route 8 gate")
    _checkpoint(records, progress, emulator, raw, "route8_gate", "Entered Route 8 gate")

    _move(actions, reader, emulator, run, GATE_TO_TUNNEL, timing, "Underground Path entry")
    _wait(actions, timing.transition_frames)
    raw = reader.read()
    _require(raw, MapId.UNDERGROUND_PATH_WEST_EAST, (47, 2), "west-east tunnel")
    _checkpoint(records, progress, emulator, raw, "west_east_tunnel", "Entered Underground Path")

    _move(
        actions,
        reader,
        emulator,
        run,
        TUNNEL_TO_ROUTE_7_GATE,
        timing,
        "Underground Path crossing",
    )
    _wait(actions, timing.transition_frames)
    raw = reader.read()
    _require(raw, MapId.UNDERGROUND_PATH_ROUTE_7, (4, 4), "Route 7 gate")
    _checkpoint(
        records,
        progress,
        emulator,
        raw,
        "west_east_tunnel_crossed",
        "Crossed the west-east Underground Path",
    )

    _move(actions, reader, emulator, run, ROUTE_7_GATE_EXIT, timing, "Route 7 gate exit")
    _wait(actions, timing.transition_frames)
    raw = reader.read()
    _require(raw, MapId.ROUTE_7, (5, 14), "Route 7 entrance")
    _checkpoint(records, progress, emulator, raw, "route7_reached", "Reached Route 7")

    _move(actions, reader, emulator, run, ROUTE_7_TO_CELADON, timing, "Celadon approach")
    _wait(actions, timing.transition_frames)
    raw = reader.read()
    _require(raw, MapId.CELADON_CITY, (49, 11), "Celadon east entrance")
    _checkpoint(records, progress, emulator, raw, "celadon_reached", "Reached Celadon City")

    _move(actions, reader, emulator, run, CELADON_TO_CENTER, timing, "Celadon Center")
    _heal_center(actions, reader, emulator, run, timing)
    final = reader.read()
    _require(final, MapId.CELADON_POKECENTER, (3, 3), "Celadon stable boundary")
    _checkpoint(records, progress, emulator, final, "celadon_stable", "Healed safely in Celadon")

    report = CeladonChapterReport(
        records=tuple(records),
        trainers=(trainer,),
        wild_flees=tuple(run.wilds),
        route_8_events_before=events_before,
        route_8_events_after=_events(emulator),
        final_raw=final,
        party_hp=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        super_potions_remaining=_bag(emulator).get(ItemId.SUPER_POTION, 0),
        repels_remaining=_bag(emulator).get(ItemId.REPEL, 0),
        money_before=money_before,
        money_remaining=_money(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise CeladonChapterError(
            f"Celadon chapter failed its evidence contract: {report.public_dict()!r}."
        )
    return report


def _move(
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    directions: Iterable[str],
    timing: CeladonTiming,
    label: str,
    *,
    allow_trainer: bool = False,
) -> RawGameState:
    route = tuple(directions)
    state = reader.read()
    for step, direction in enumerate(route, 1):
        before = (state.map_id, state.player_x, state.player_y)
        for attempt in range(timing.movement_retries):
            _pulse(executor, MacroActionKind.MOVE, direction, 12 * (attempt + 1))
            state = reader.read()
            if state.battle_state == 1:
                _flee(executor, reader, emulator, run, timing)
                state = reader.read()
                if (state.map_id, state.player_x, state.player_y) != before:
                    break
                continue
            if state.battle_state == 2:
                if allow_trainer and step == len(route):
                    return state
                raise CeladonChapterError(f"Unexpected trainer interrupted {label} at step {step}.")
            if (state.map_id, state.player_x, state.player_y) != before:
                break
            if not reader.read_input_readiness().ready:
                _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
                state = reader.read()
                if state.battle_state == 2 and allow_trainer and step == len(route):
                    return state
        else:
            if allow_trainer and step == len(route):
                return state
            raise CeladonChapterError(
                f"{label} blocked at step {step}: {direction}, "
                f"{(state.map_id, state.player_x, state.player_y)!r}."
            )
        if (
            state.first_party_hp == 0
            or state.party_species_ids is None
            or sorted(state.party_species_ids) != sorted(PROTECTED_PARTY)
        ):
            raise CeladonChapterError(f"{label} changed the protected lead/party.")
    return state


def _enter_trainer_battle(
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: CeladonTiming,
    label: str,
) -> RawGameState:
    for _ in range(timing.dialogue_pulses):
        raw = reader.read()
        if raw.battle_state == 2:
            return raw
        if raw.battle_state == 1:
            raise CeladonChapterError(f"A wild battle replaced {label}.")
        _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    raise CeladonChapterError(f"{label} did not enter a trainer battle.")


def _flee(
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    timing: CeladonTiming,
) -> None:
    before = reader.read()
    species, pp = before.party_species_ids, before.first_party_pp
    hp, inventory = _party_hp(emulator), _bag(emulator)
    if before.battle_state != 1:
        raise CeladonChapterError("Wild flee requires an active wild battle.")
    trace: list[tuple[int, str, int | None, int | None, int | None]] = []
    for _ in range(timing.flee_pulses):
        final = reader.read()
        if final.battle_state == 0 and reader.read_input_readiness().ready:
            final_hp = _party_hp(emulator)
            evidence = CeladonWildFleeEvidence(
                int(before.map_id or 0),
                int(before.player_x or 0),
                int(before.player_y or 0),
                int(before.enemy_species_id or 0),
                int(before.enemy_level or 0),
                final.party_species_ids == species,
                final.first_party_pp == pp,
                all(0 < after <= prior for prior, after in zip(hp, final_hp, strict=True)),
                _bag(emulator) == inventory,
            )
            if not all(
                (
                    evidence.party_preserved,
                    evidence.pp_preserved,
                    evidence.hp_safe,
                    evidence.inventory_preserved,
                )
            ):
                raise CeladonChapterError("Wild flee violated protected state.")
            run.wilds.append(evidence)
            note_observed_battle_exit()
            return
        if final.battle_state != 1:
            trace.append(
                (
                    final.battle_state,
                    "field-transition",
                    None,
                    final.first_party_hp,
                    final.enemy_hp,
                )
            )
            _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
            continue
        menu = reader.read_battle_menu_state(final)
        trace.append(
            (
                final.battle_state,
                menu.phase.value,
                menu.selected_main_command,
                final.first_party_hp,
                final.enemy_hp,
            )
        )
        del trace[:-12]
        if menu.phase is BattleMenuPhase.UNKNOWN:
            _pulse(executor, MacroActionKind.CONFIRM, frames=timing.wait_frames)
            continue
        if menu.phase is BattleMenuPhase.MOVE:
            _pulse(executor, MacroActionKind.CANCEL, frames=timing.wait_frames)
            continue
        command = menu.selected_main_command
        if command == 3:
            _pulse(executor, MacroActionKind.CONFIRM, frames=240)
            continue
        direction = {0: "right", 1: "right", 2: "down"}.get(command)
        if direction is None:
            raise CeladonChapterError("Wild flee exposed an invalid main-menu cursor.")
        _pulse(executor, MacroActionKind.MOVE, direction, timing.wait_frames)
    raise CeladonChapterError(f"Wild flee exceeded its bounded dialogue: trace={trace!r}.")


def _heal_center(
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    timing: CeladonTiming,
) -> None:
    _wait(executor, timing.transition_frames)
    _require(reader.read(), MapId.CELADON_POKECENTER, (3, 7), "Celadon Center entrance")
    _move(executor, reader, emulator, run, ("up",) * 4, timing, "Celadon Center nurse")
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
    raise CeladonChapterError("Celadon Center did not heal the complete party.")


def _require_resources(emulator: EmulatorState) -> None:
    bag = _bag(emulator)
    resources = (bag.get(ItemId.SUPER_POTION, 0), bag.get(ItemId.REPEL, 0), _money(emulator))
    if resources[0] != LAVENDER_SUPER_POTION_RESERVE or resources[1] != 0 or resources[2] < 0:
        raise CeladonChapterError(f"Unexpected starting resources: {resources!r}.")
    if _party_hp(emulator) != _party_max_hp(emulator) or any(
        status != 0 for status in _party_status(emulator)
    ):
        raise CeladonChapterError("Lavender boundary party was not fully healed.")


def _checkpoint(
    records: list[CeladonCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(CeladonCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            CeladonProgress(
                checkpoint_id, label, len(records), CELADON_CHECKPOINT_COUNT, emulator.frame_count
            )
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
        or raw.party_species_ids != PROTECTED_PARTY
    ):
        raise CeladonChapterError(
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
            raise CeladonChapterError(f"Player money contains invalid BCD byte {packed:#04x}.")
        value = value * 100 + high * 10 + low
    return value


def _events(emulator: EmulatorState) -> tuple[bool, ...]:
    return tuple(_event(emulator, event) for event in ROUTE_8_EVENTS)


def _event(emulator: EmulatorState, event: EventFlag) -> bool:
    value = int(event)
    return bool(emulator.read_u8(int(RamAddress.EVENT_FLAGS) + value // 8) & (1 << (value % 8)))


def _u16(emulator: EmulatorState, address: int) -> int:
    return emulator.read_u8(address) * 0x100 + emulator.read_u8(address + 1)


def _party_size(emulator: EmulatorState) -> int:
    """Return the bounded live party size used by whole-party receipts."""

    return min(emulator.read_u8(RamAddress.PARTY_COUNT), 6)


def _party_hp(emulator: EmulatorState) -> tuple[int, ...]:
    return tuple(
        _u16(emulator, int(RamAddress.PARTY_MON_1_HP) + index * PARTY_STRUCT_STRIDE)
        for index in range(_party_size(emulator))
    )


def _party_levels(emulator: EmulatorState) -> tuple[int, ...]:
    """Read every party member's level.

    Receipts previously reported the Champion's fixed party levels as though
    they were ours, which is why twelve independent runs all recorded the same
    six numbers.  Sourcing our own levels makes that class of claim checkable.
    """

    return tuple(
        emulator.read_u8(int(RamAddress.PARTY_MON_1_LEVEL) + index * PARTY_STRUCT_STRIDE)
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
    executor: CountingExecutor,
    kind: MacroActionKind,
    value: str | int | None = None,
    frames: int = 180,
) -> None:
    executor.execute(MacroAction(kind, value))
    _wait(executor, frames)


def _wait(executor: CountingExecutor, frames: int) -> None:
    executor.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))
