"""Qualified Saffron Gym and Sabrina chapter.

The warp graph, trainer events, leader identity, party, and reward order are
pinned to pret/pokered commit ``1e96034092686d006e863cace09e87273051a3d8``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleResourcePolicy,
    BattleRuntimeError,
    BattleRuntimeTiming,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.celadon import _bag, _money, _party_hp, _party_max_hp, _party_status
from pokemon_red_completion.observation import (
    Badge,
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.silph import (
    CENTER_EXIT,
    CITY_TO_MART_APPROACH,
    DEFAULT_SILPH_TIMING,
    ChapterExecutor,
    EmulatorState,
    SilphTiming,
    _await_trainer_battle,
    _battle_hyper_potion,
    _CountingExecutor,
    _event,
    _heal,
    _interact,
    _move,
)
from pokemon_red_completion.tower import TOWER_FINAL_PARTY

SABRINA_CHECKPOINT_COUNT = 6
SABRINA_OPPONENT = 0xF0
SABRINA_TRAINER_CLASS = 0xF0
SABRINA_TRAINER_SET = 1
SABRINA_PARTY = ((0x26, 38), (0x2A, 37), (0x77, 38), (0x95, 43))
REGULAR_TRAINER_EVENTS = tuple(range(0x362, 0x369))
HYPER_POTION_THRESHOLD = 70


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "D": "down", "L": "left", "R": "right"}[part] for part in value)


CENTER_TO_GYM = (
    CENTER_EXIT + CITY_TO_MART_APPROACH + ("right",) * 8 + ("up",) * 8 + ("left",) * 4 + ("up",)
)
GYM_TO_SABRINA = (
    _directions("RRRUU") + _directions("LLLL") + _directions("DLDLLL") + _directions("UUDLDLLLUULL")
)
SABRINA_TO_CITY = _directions("RRDDUUUURRRRDDDDLLD")
CITY_TO_CENTER = _directions("RRRRDDDDDDDDDDDDDDLDDDDDDDDDDDDDLLLLLLLLLLLLLLLLLLLLLLLULLLLLU")


class SabrinaChapterError(RuntimeError):
    """Raised when the Sabrina evidence contract fails."""


@dataclass(frozen=True, slots=True)
class SabrinaProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[SabrinaProgress], None]


@dataclass(frozen=True, slots=True)
class SabrinaCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class SabrinaTurn:
    enemy_species: int
    enemy_level: int
    enemy_hp: int
    lead_hp: int
    lead_status: int
    pp: tuple[int, int, int, int]
    move_slot: int


@dataclass(frozen=True, slots=True)
class SabrinaChapterReport:
    records: tuple[SabrinaCheckpoint, ...]
    final_raw: RawGameState
    turns: tuple[SabrinaTurn, ...]
    identity: tuple[int, int, int]
    trainer_events_before: tuple[bool, ...]
    trainer_events_after: tuple[bool, ...]
    got_tm46: bool
    beat_sabrina: bool
    marsh_badge: bool
    marsh_badge_mirror: bool
    tm46_quantity: int
    hyper_potions_before: int
    hyper_potions_used: int
    hyper_potions_remaining: int
    initial_money: int
    money_remaining: int
    party_hp: tuple[int, int, int]
    party_max_hp: tuple[int, int, int]
    party_status: tuple[int, int, int]
    controller_released: bool
    frames_executed: int
    actions_executed: int

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == SABRINA_CHECKPOINT_COUNT
            and self.identity == (SABRINA_OPPONENT, SABRINA_TRAINER_CLASS, SABRINA_TRAINER_SET)
            and _encounter_party(self.turns) == SABRINA_PARTY
            and tuple(turn.move_slot for turn in self.turns) == (2, 2, 3, 3, 3, 2)
            and self.trainer_events_before == (False,) * 7
            and self.trainer_events_after == (True,) * 7
            and self.got_tm46
            and self.beat_sabrina
            and self.marsh_badge
            and self.marsh_badge_mirror
            and self.tm46_quantity == 1
            and 0 <= self.hyper_potions_used <= 1
            and self.hyper_potions_remaining == self.hyper_potions_before - self.hyper_potions_used
            and self.money_remaining == self.initial_money + 4_257
            and all(turn.lead_hp > 0 for turn in self.turns)
            and self.final_raw.map_id == MapId.SAFFRON_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and self.final_raw.battle_state == 0
            and self.final_raw.party_species_ids == TOWER_FINAL_PARTY
            and self.party_hp == self.party_max_hp
            and self.party_status == (0, 0, 0)
            and self.final_raw.first_party_moves == (0x82, 0x46, 0x3A, 0x39)
            and self.final_raw.first_party_pp == (15, 15, 10, 15)
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "defeat_sabrina",
            "trainer_free_warp_route": self.trainer_events_before == (False,) * 7,
            "identity": list(self.identity),
            "party": [list(member) for member in SABRINA_PARTY],
            "move_slots": [turn.move_slot for turn in self.turns],
            "rewards": {
                "tm46": self.tm46_quantity,
                "tm46_event": self.got_tm46,
                "sabrina_event": self.beat_sabrina,
                "marsh_badge": self.marsh_badge,
                "marsh_badge_mirror": self.marsh_badge_mirror,
                "regular_trainers_deactivated": all(self.trainer_events_after),
            },
            "recovery": {
                "hyper_potions_before": self.hyper_potions_before,
                "used": self.hyper_potions_used,
                "remaining": self.hyper_potions_remaining,
            },
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


def run_sabrina_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    timing: SilphTiming = DEFAULT_SILPH_TIMING,
    progress: ProgressSink | None = None,
) -> SabrinaChapterReport:
    start_frames = emulator.frame_count
    actions = _CountingExecutor(executor)
    records: list[SabrinaCheckpoint] = []
    initial = reader.read()
    _require(initial, MapId.SAFFRON_POKECENTER, (3, 3), "post-Silph boundary")
    initial_money = _money(emulator)
    initial_bag = _bag(emulator)
    if (
        _event(emulator, EventFlag.BEAT_SABRINA)
        or _event(emulator, EventFlag.GOT_TM46)
        or initial_bag.get(ItemId.TM46_PSYWAVE, 0)
        or initial.badge_bits & Badge.MARSH
        or emulator.read_u8(RamAddress.BEAT_GYM_FLAGS) & Badge.MARSH
    ):
        raise SabrinaChapterError("Sabrina input boundary is not pristine.")
    _checkpoint(records, progress, emulator, initial, "sabrina_ready", "Sabrina plan ready")

    _move(actions, reader, CENTER_TO_GYM, timing)
    _require(reader.read(), MapId.SAFFRON_GYM, (8, 17), "Saffron Gym entrance")
    trainer_events_before = tuple(_event(emulator, event) for event in REGULAR_TRAINER_EVENTS)
    if trainer_events_before != (False,) * 7:
        raise SabrinaChapterError("A regular Saffron Gym trainer was already defeated.")

    _move(actions, reader, _directions("RRRUU"), timing)
    _require(reader.read(), MapId.SAFFRON_GYM, (19, 17), "warp 20 to 32")
    _move(actions, reader, _directions("LLLL"), timing)
    _require(reader.read(), MapId.SAFFRON_GYM, (5, 15), "warp 31 to 12")
    _move(actions, reader, _directions("DLDLLL"), timing)
    _require(reader.read(), MapId.SAFFRON_GYM, (11, 5), "warp 13 to 18")
    _move(actions, reader, _directions("UUDLDLLLUULL"), timing)
    _require(reader.read(), MapId.SAFFRON_GYM, (9, 9), "Sabrina approach")
    if tuple(_event(emulator, event) for event in REGULAR_TRAINER_EVENTS) != (False,) * 7:
        raise SabrinaChapterError("Trainer-free warp route changed a regular trainer event.")
    _checkpoint(records, progress, emulator, reader.read(), "leader_reached", "Reached Sabrina")

    _move(actions, reader, ("up",), timing)
    _interact(actions, timing.dialogue_frames)
    _await_trainer_battle(actions, reader, timing)
    identity = (
        emulator.read_u8(RamAddress.CURRENT_OPPONENT),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_CLASS),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_SET),
    )
    if identity != (SABRINA_OPPONENT, SABRINA_TRAINER_CLASS, SABRINA_TRAINER_SET):
        raise SabrinaChapterError(f"Unexpected Sabrina identity: {identity!r}.")

    turns: list[SabrinaTurn] = []

    def policy(raw: RawGameState) -> int:
        slot = 3 if raw.enemy_species_id == 0x77 else 2
        turns.append(
            SabrinaTurn(
                raw.enemy_species_id or 0,
                raw.enemy_level or 0,
                raw.enemy_hp or 0,
                raw.first_party_hp or 0,
                raw.first_party_status or 0,
                raw.first_party_pp or (0, 0, 0, 0),
                slot,
            )
        )
        return slot

    hyper_before = initial_bag.get(ItemId.HYPER_POTION, 0)
    while True:
        complete = _run_until_sabrina(
            reader,
            actions,
            policy,
            lambda raw: 0 < (raw.first_party_hp or 0) < HYPER_POTION_THRESHOLD,
            "Sabrina",
        )
        if complete:
            break
        if hyper_before - _bag(emulator).get(ItemId.HYPER_POTION, 0) >= 1:
            raise SabrinaChapterError("Sabrina recovery exceeded one Hyper Potion.")
        _battle_hyper_potion(reader, actions, emulator, timing)

    if _encounter_party(turns) != SABRINA_PARTY:
        raise SabrinaChapterError(f"Sabrina party or turn policy changed: {turns!r}.")
    if any(turn.lead_status for turn in turns):
        raise SabrinaChapterError("Sabrina policy encountered an unsupported persistent status.")
    _checkpoint(records, progress, emulator, reader.read(), "sabrina_defeated", "Defeated Sabrina")

    got_tm46 = _event(emulator, EventFlag.GOT_TM46)
    beat_sabrina = _event(emulator, EventFlag.BEAT_SABRINA)
    trainer_events_after = tuple(_event(emulator, event) for event in REGULAR_TRAINER_EVENTS)
    marsh_badge = bool(emulator.read_u8(RamAddress.OBTAINED_BADGES) & Badge.MARSH)
    marsh_badge_mirror = bool(emulator.read_u8(RamAddress.BEAT_GYM_FLAGS) & Badge.MARSH)
    tm46_quantity = _bag(emulator).get(ItemId.TM46_PSYWAVE, 0)
    if not (
        got_tm46
        and beat_sabrina
        and trainer_events_after == (True,) * 7
        and marsh_badge
        and marsh_badge_mirror
        and tm46_quantity == 1
    ):
        raise SabrinaChapterError("Sabrina reward gate failed.")
    _checkpoint(records, progress, emulator, reader.read(), "marsh_badge", "Verified Marsh Badge")

    _move(actions, reader, SABRINA_TO_CITY, timing)
    _require(reader.read(), MapId.SAFFRON_CITY, (34, 4), "Saffron Gym exit")
    _checkpoint(records, progress, emulator, reader.read(), "gym_exited", "Exited Saffron Gym")
    _move(actions, reader, CITY_TO_CENTER, timing)
    _require(reader.read(), MapId.SAFFRON_POKECENTER, (3, 7), "Saffron Center entry")
    _move(actions, reader, ("up",) * 4, timing)
    _heal(actions, timing)
    final = reader.read()
    _require(final, MapId.SAFFRON_POKECENTER, (3, 3), "healed Sabrina boundary")
    _checkpoint(records, progress, emulator, final, "sabrina_terminal", "Healed Sabrina boundary")

    hyper_remaining = _bag(emulator).get(ItemId.HYPER_POTION, 0)
    report = SabrinaChapterReport(
        tuple(records),
        final,
        tuple(turns),
        identity,
        trainer_events_before,
        trainer_events_after,
        got_tm46,
        beat_sabrina,
        marsh_badge,
        marsh_badge_mirror,
        tm46_quantity,
        hyper_before,
        hyper_before - hyper_remaining,
        hyper_remaining,
        initial_money,
        _money(emulator),
        _party_hp(emulator),
        _party_max_hp(emulator),
        _party_status(emulator),
        not emulator.pressed_buttons,
        emulator.frame_count - start_frames,
        actions.actions_executed,
    )
    if not report.passed:
        raise SabrinaChapterError(f"Sabrina chapter failed its evidence contract: {report!r}.")
    return report


class _PauseBattle(Exception):
    pass


def _run_until_sabrina(
    reader: PokemonRedStateReader,
    actions: _CountingExecutor,
    policy: Callable[[RawGameState], int],
    pause: Callable[[RawGameState], bool],
    label: str,
) -> bool:
    def guarded(raw: RawGameState) -> int:
        if pause(raw):
            raise _PauseBattle
        return policy(raw)

    try:
        run_adaptive_trainer_battle(
            reader,
            actions,
            guarded,
            expected_map=int(MapId.SAFFRON_GYM),
            intent=BattleIntent(
                "defeat_sabrina",
                battle_plan_id=RedBattlePlanId.SABRINA_LEADER,
                resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
            ),
            timing=BattleRuntimeTiming(max_runtime_pulses=720),
            label=label,
            unknown_cancel_interval=3,
        )
    except BattleRuntimeError as error:
        if not isinstance(error.__cause__, _PauseBattle):
            raise
        return False
    return True


def _encounter_party(
    turns: tuple[SabrinaTurn, ...] | list[SabrinaTurn],
) -> tuple[tuple[int, int], ...]:
    party: list[tuple[int, int]] = []
    for turn in turns:
        member = (turn.enemy_species, turn.enemy_level)
        if not party or party[-1] != member:
            party.append(member)
    return tuple(party)


def _checkpoint(
    records: list[SabrinaCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(SabrinaCheckpoint(checkpoint_id, label, raw))
    if progress:
        progress(
            SabrinaProgress(
                checkpoint_id,
                label,
                len(records),
                SABRINA_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )


def _require(raw: RawGameState, map_id: int, position: tuple[int, int], label: str) -> None:
    if (
        raw.map_id != int(map_id)
        or (raw.player_x, raw.player_y) != position
        or raw.battle_state != 0
    ):
        raise SabrinaChapterError(
            f"{label} failed: map={raw.map_id:#04x}, "
            f"position={(raw.player_x, raw.player_y)!r}, battle={raw.battle_state}."
        )
