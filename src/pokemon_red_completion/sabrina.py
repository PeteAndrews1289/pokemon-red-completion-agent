"""Qualified Saffron Gym and Sabrina chapter.

The warp graph, trainer events, leader identity, party, and reward order are
pinned to pret/pokered commit ``1e96034092686d006e863cace09e87273051a3d8``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleResourcePolicy,
    BattleRuntimeError,
    BattleRuntimeTiming,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.celadon import _bag, _money, _party_hp, _party_max_hp, _party_status
from pokemon_red_completion.dojo import _prove_center_field_control
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
    _battle_x_special,
    _CountingExecutor,
    _event,
    _heal,
    _interact,
    _move,
    _move_verified,
    _navigate_saffron_coordinate,
    _pulse,
)
from pokemon_red_completion.tower import party_core_intact

SABRINA_CHECKPOINT_COUNT = 6
SABRINA_OPPONENT = 0xF0
SABRINA_TRAINER_CLASS = 0xF0
SABRINA_TRAINER_SET = 1
SABRINA_PARTY = ((0x26, 38), (0x2A, 37), (0x77, 38), (0x95, 43))
REGULAR_TRAINER_EVENTS = tuple(range(0x362, 0x369))
PC_DEPOSIT_ITEMS = (ItemId.SILPH_SCOPE, ItemId.CARD_KEY)
HYPER_POTION_THRESHOLD = 70
ALAKAZAM_HYPER_POTION_THRESHOLD = 110
# The next chapter restocks before its first required battle, so Sabrina may
# consume the complete held-out reserve when her Alakazam damage requires it.
MAX_SABRINA_HYPER_POTIONS = 7
SABRINA_BATTLE_TIMING = BattleRuntimeTiming(
    max_runtime_pulses=720,
    max_move_menu_transition_pulses=24,
    max_pp_confirmation_pulses=12,
    max_attack_confirmation_pulses=6,
    max_post_attack_transition_pulses=24,
)


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
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    controller_released: bool
    frames_executed: int
    actions_executed: int

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == SABRINA_CHECKPOINT_COUNT
            and self.identity == (SABRINA_OPPONENT, SABRINA_TRAINER_CLASS, SABRINA_TRAINER_SET)
            and _encounter_party(self.turns) == SABRINA_PARTY
            and all(_sabrina_turn_is_allowed(turn) for turn in self.turns)
            and self.trainer_events_before == (False,) * 7
            and self.trainer_events_after == (True,) * 7
            and self.got_tm46
            and self.beat_sabrina
            and self.marsh_badge
            and self.marsh_badge_mirror
            and self.tm46_quantity == 1
            and 0 <= self.hyper_potions_used <= MAX_SABRINA_HYPER_POTIONS
            and self.hyper_potions_remaining == self.hyper_potions_before - self.hyper_potions_used
            and self.money_remaining == self.initial_money + 4_257
            and all(turn.lead_hp > 0 for turn in self.turns)
            and all(_sabrina_status_is_supported(turn.lead_status) for turn in self.turns)
            and self.final_raw.map_id == MapId.SAFFRON_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and self.final_raw.battle_state == 0
            and party_core_intact(self.final_raw.party_species_ids)
            and self.party_hp == self.party_max_hp
            and all(status == 0 for status in self.party_status)
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
    _store_obsolete_key_items(actions, reader, emulator, timing)

    _move_verified(actions, reader, CENTER_EXIT, timing, "Saffron Center exit")
    _navigate_saffron_coordinate(actions, reader, timing, (34, 4), "Saffron Gym")
    _move_verified(actions, reader, ("up",), timing, "Saffron Gym entry")
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

    _battle_x_special(reader, actions, emulator, timing)

    turns: list[SabrinaTurn] = []

    def policy(raw: RawGameState) -> int:
        slot = _sabrina_move_slot(raw)
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
            _sabrina_recovery_required,
            "Sabrina",
        )
        if complete:
            break
        if (
            hyper_before - _bag(emulator).get(ItemId.HYPER_POTION, 0)
            >= MAX_SABRINA_HYPER_POTIONS
        ):
            raise SabrinaChapterError(
                f"Sabrina recovery exceeded {MAX_SABRINA_HYPER_POTIONS} Hyper Potions."
            )
        _battle_hyper_potion(reader, actions, emulator, timing)

    if _encounter_party(turns) != SABRINA_PARTY:
        raise SabrinaChapterError(f"Sabrina party or turn policy changed: {turns!r}.")
    if any(not _sabrina_status_is_supported(turn.lead_status) for turn in turns):
        raise SabrinaChapterError("Sabrina policy encountered an unsupported persistent status.")
    _checkpoint(records, progress, emulator, reader.read(), "sabrina_defeated", "Defeated Sabrina")

    for _ in range(64):
        got_tm46 = _event(emulator, EventFlag.GOT_TM46)
        beat_sabrina = _event(emulator, EventFlag.BEAT_SABRINA)
        trainer_events_after = tuple(
            _event(emulator, event) for event in REGULAR_TRAINER_EVENTS
        )
        marsh_badge = bool(emulator.read_u8(RamAddress.OBTAINED_BADGES) & Badge.MARSH)
        marsh_badge_mirror = bool(emulator.read_u8(RamAddress.BEAT_GYM_FLAGS) & Badge.MARSH)
        tm46_quantity = _bag(emulator).get(ItemId.TM46_PSYWAVE, 0)
        if (
            got_tm46
            and beat_sabrina
            and trainer_events_after == (True,) * 7
            and marsh_badge
            and marsh_badge_mirror
            and tm46_quantity == 1
            and reader.read_input_readiness().ready
        ):
            break
        _interact(actions, timing.dialogue_frames)
    else:
        readiness = reader.read_input_readiness()
        raw = reader.read()
        raise SabrinaChapterError(
            "Sabrina rewards did not settle inside the dialogue bound: "
            f"got_tm46={got_tm46}, beat_sabrina={beat_sabrina}, "
            f"trainer_events={trainer_events_after!r}, marsh_badge={marsh_badge}, "
            f"marsh_badge_mirror={marsh_badge_mirror}, tm46_quantity={tm46_quantity}, "
            f"input_ready={readiness.ready}, map={raw.map_id!r}, "
            f"position={(raw.player_x, raw.player_y)!r}, battle={raw.battle_state}."
        )
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
    _navigate_saffron_coordinate(actions, reader, timing, (9, 30), "Saffron Center")
    _move_verified(actions, reader, ("up",), timing, "Saffron Center entry")
    _require(reader.read(), MapId.SAFFRON_POKECENTER, (3, 7), "Saffron Center entry")
    _move(actions, reader, ("up",) * 4, timing)
    _heal(actions, timing)
    _prove_center_field_control(actions, reader, timing)
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
            timing=SABRINA_BATTLE_TIMING,
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


def _sabrina_move_slot(raw: RawGameState) -> int:
    priorities = (3, 2, 4) if raw.enemy_species_id == 0x77 else (2, 4, 3)
    pp = raw.first_party_pp or ()
    for slot in priorities:
        if (
            len(pp) >= slot
            and pp[slot - 1] & 0x3F
            and not (
                raw.player_disabled_move_slot == slot
                and (raw.player_disable_turns or 0) > 0
            )
        ):
            return slot
    raise SabrinaChapterError("Sabrina policy has no legal move with PP.")


def _sabrina_turn_is_allowed(turn: SabrinaTurn) -> bool:
    allowed = {2, 3, 4}
    return turn.move_slot in allowed


def _sabrina_status_is_supported(status: int) -> bool:
    return status == 0 or 1 <= status <= 7 or status == 0x40


def _sabrina_recovery_required(raw: RawGameState) -> bool:
    threshold = (
        ALAKAZAM_HYPER_POTION_THRESHOLD
        if raw.enemy_species_id == 0x95
        else HYPER_POTION_THRESHOLD
    )
    return 0 < (raw.first_party_hp or 0) < threshold


def _store_obsolete_key_items(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SilphTiming,
) -> None:
    before = _bag(emulator)
    if not _sabrina_capacity_ready(before):
        raise SabrinaChapterError(
            "Sabrina inventory cleanup lacks safe capacity or its spent key items."
        )
    expected_slots = len(before) - len(PC_DEPOSIT_ITEMS)

    _move(actions, reader, ("down",) + ("right",) * 10, timing)
    _require(reader.read(), MapId.SAFFRON_POKECENTER, (13, 4), "Saffron PC approach")
    for item in PC_DEPOSIT_ITEMS:
        _deposit_pc_item(actions, reader, emulator, item, timing)
    returned = reader.read()
    after = _bag(emulator)
    if (
        returned.map_id != MapId.SAFFRON_POKECENTER
        or (returned.player_x, returned.player_y) != (13, 4)
        or not reader.read_input_readiness().ready
        or len(after) != expected_slots
        or len(after) > 18
        or any(item in after for item in PC_DEPOSIT_ITEMS)
    ):
        raise SabrinaChapterError("Saffron PC cleanup did not restore safe field capacity.")
    _move(actions, reader, ("left",) * 10 + ("up",), timing)
    _require(reader.read(), MapId.SAFFRON_POKECENTER, (3, 3), "Saffron PC return")


def _sabrina_capacity_ready(bag: Mapping[object, int]) -> bool:
    """Prove that archiving two obsolete keys leaves room for the Gym reward."""

    return len(bag) <= 20 and all(bag.get(item, 0) == 1 for item in PC_DEPOSIT_ITEMS)


def _deposit_pc_item(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    item: ItemId,
    timing: SilphTiming,
) -> None:
    _pulse(actions, MacroActionKind.MOVE, timing, "up", timing.menu_frames)
    _pulse(actions, MacroActionKind.INTERACT, timing, frames=timing.menu_frames)
    _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    _select_menu_cursor(actions, emulator, 1, timing)
    for _ in range(3):
        _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    if emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) != 0:
        raise SabrinaChapterError("Saffron PC did not expose WITHDRAW ITEM.")
    _pulse(actions, MacroActionKind.MOVE, timing, "down", timing.menu_frames)
    _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    _select_bag_list_item(actions, emulator, item, timing)
    for _ in range(3):
        _pulse(actions, MacroActionKind.CONFIRM, timing, frames=timing.menu_frames)
    if item in _bag(emulator):
        raise SabrinaChapterError(f"Saffron PC did not store {item.name}.")
    for _ in range(4):
        _pulse(actions, MacroActionKind.CANCEL, timing, frames=timing.menu_frames)
    if not reader.read_input_readiness().ready:
        raise SabrinaChapterError(f"Saffron PC did not close after storing {item.name}.")


def _select_menu_cursor(
    actions: _CountingExecutor,
    emulator: EmulatorState,
    target: int,
    timing: SilphTiming,
) -> None:
    for _ in range(16):
        current = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if current == target:
            return
        _pulse(
            actions,
            MacroActionKind.MOVE,
            timing,
            "down" if current < target else "up",
            timing.menu_frames,
        )
    raise SabrinaChapterError(f"Menu could not select cursor {target}.")


def _select_bag_list_item(
    actions: _CountingExecutor,
    emulator: EmulatorState,
    item: ItemId,
    timing: SilphTiming,
) -> None:
    for _ in range(24):
        items = tuple(_bag(emulator))
        if item not in items:
            raise SabrinaChapterError(f"Required PC item {item.name} is unavailable.")
        absolute = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM) + emulator.read_u8(
            RamAddress.LIST_SCROLL_OFFSET
        )
        target = items.index(item)
        if absolute == target:
            return
        _pulse(
            actions,
            MacroActionKind.MOVE,
            timing,
            "down" if absolute < target else "up",
            timing.menu_frames,
        )
    raise SabrinaChapterError(f"Could not select PC item {item.name}.")


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
