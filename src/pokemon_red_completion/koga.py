"""Qualified Fuchsia Gym and Koga chapter.

The post-Safari boundary cannot return east across Route 15, cannot use the
Cycling Road without the Bicycle, and cannot Surf before earning the Soul
Badge.  Koga is therefore the legal geographic prerequisite for returning to
Celadon to finish Erika.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_recovery import ProtectedRecoveryError, switch_active_battler
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleRuntimeError,
    BattleRuntimeTiming,
    RequiredMovePolicy,
    note_observed_trainer_battle_exit,
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
from pokemon_red_completion.red_battle_catalog import pokemon_red_move_ref
from pokemon_red_completion.tower import party_core_intact

KOGA_CHECKPOINT_COUNT = 11
KOGA_TRAINER_REWARD_TOTAL = 7_852
SURF = 0x39
SURF_SLOT = 4
KOGA_OPPONENT = 0xEE
KOGA_TRAINER_CLASS = 0x26
KOGA_TRAINER_NUMBER = 1
MUK_SPECIES_ID = 0x88
# Disable can legally force Juggler 3 onto reserve moves and extend the battle.
# Bound its Surf consumption by the carried 15-PP pool rather than one historical
# eight-turn outcome; the remaining fights retain their tighter qualified limits.
KOGA_PP_BOUNDS = ((0, 15), (1, 8), (1, 8), (1, 15))
JUGGLER_4_PIVOT_HP_THRESHOLD = 50


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "D": "down", "L": "left", "R": "right"}[item] for item in value)


CENTER_TO_GYM = _directions("DDDDDLLLLLLLLLLLLLLU")
GYM_TO_JUGGLER3 = _directions("URRRRRUUUUUUULU")
JUGGLER3_TO_TAMER2 = _directions("UUUU")
TAMER2_TO_CENTER = _directions("DDDDDDDDRDDDDDLLLLDRRRRRRRRRRRRRRUUUU")
CENTER_TO_JUGGLER4 = CENTER_TO_GYM + _directions("URRRRRUUUUUUUUUUUUUUULLLLLLLLDDRDDLDD")
JUGGLER4_TO_CENTER = _directions("UURUULUURRRRRRRRDDDDDDDDDDDDDDDDLLLLLDRRRRRRRRRRRRRRUUUU")
CENTER_TO_KOGA = CENTER_TO_GYM + _directions("URRRRRUUUUUUUUUUUUUUULLLLLLLLDDRDDLDDDDRRDDR")
KOGA_TO_CENTER = _directions("LUULLUUUURUULUURRRRRRRRDDDDDDDDDDDDDDDDLLLLLDRRRRRRRRRRRRRRUUUU")

REGULAR_TRAINER_EVENTS = (
    EventFlag.BEAT_FUCHSIA_GYM_TRAINER_0,
    EventFlag.BEAT_FUCHSIA_GYM_TRAINER_1,
    EventFlag.BEAT_FUCHSIA_GYM_TRAINER_2,
    EventFlag.BEAT_FUCHSIA_GYM_TRAINER_3,
    EventFlag.BEAT_FUCHSIA_GYM_TRAINER_4,
    EventFlag.BEAT_FUCHSIA_GYM_TRAINER_5,
)
MANDATORY_TRAINER_EVENTS = (
    EventFlag.BEAT_FUCHSIA_GYM_TRAINER_1,
    EventFlag.BEAT_FUCHSIA_GYM_TRAINER_4,
    EventFlag.BEAT_FUCHSIA_GYM_TRAINER_5,
)
OPTIONAL_TRAINER_EVENTS = tuple(
    event for event in REGULAR_TRAINER_EVENTS if event not in MANDATORY_TRAINER_EVENTS
)


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class KogaChapterError(RuntimeError):
    """Raised when the Fuchsia Gym evidence contract fails."""


@dataclass(frozen=True, slots=True)
class KogaTiming:
    wait_frames: int = 180
    movement_frames: int = 240
    movement_retries: int = 18
    dialogue_pulses: int = 48
    heal_pulses: int = 20

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_KOGA_TIMING = KogaTiming()
KOGA_BATTLE_TIMING = BattleRuntimeTiming(
    max_runtime_pulses=720,
    max_move_menu_transition_pulses=24,
    max_pp_confirmation_pulses=12,
    max_attack_confirmation_pulses=6,
    max_post_attack_transition_pulses=24,
)


@dataclass(frozen=True, slots=True)
class KogaProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[KogaProgress], None]


@dataclass(frozen=True, slots=True)
class KogaCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class KogaBattleEvidence:
    label: str
    opponent: int
    trainer_class: int
    trainer_number: int
    event: int
    selected_pp_spent: int
    hp_after: int
    max_hp_after: int
    status_after: int
    terminal_mutual_ko: bool = False
    continued_after_faint: bool = False


@dataclass(frozen=True, slots=True)
class KogaChapterReport:
    records: tuple[KogaCheckpoint, ...]
    battles: tuple[KogaBattleEvidence, ...]
    final_raw: RawGameState
    initial_bag: tuple[tuple[int, int], ...]
    final_bag: tuple[tuple[int, int], ...]
    initial_money: int
    final_money: int
    trainer_events_before_koga: tuple[bool, ...]
    trainer_events_after_koga: tuple[bool, ...]
    got_tm06: bool
    beat_koga: bool
    soul_badge: bool
    soul_badge_mirror: bool
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    surf_pp: int
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        expected_bag = tuple(sorted((*self.initial_bag, (int(ItemId.TM06_TOXIC), 1))))
        return (
            len(self.records) == KOGA_CHECKPOINT_COUNT
            and tuple(item.trainer_number for item in self.battles) == (3, 2, 4, 1)
            and len(self.battles) == len(KOGA_PP_BOUNDS)
            and all(
                lower <= battle.selected_pp_spent <= upper
                for battle, (lower, upper) in zip(self.battles, KOGA_PP_BOUNDS, strict=True)
            )
            and all(
                0 < item.hp_after <= item.max_hp_after
                or (
                    (item.terminal_mutual_ko or item.continued_after_faint)
                    and item.hp_after == 0
                )
                for item in self.battles
            )
            and self.trainer_events_before_koga == (False, True, False, False, True, True)
            and self.trainer_events_after_koga == (True,) * 6
            and self.got_tm06
            and self.beat_koga
            and self.soul_badge
            and self.soul_badge_mirror
            and all(item != int(ItemId.TM06_TOXIC) for item, _ in self.initial_bag)
            and self.final_bag == expected_bag
            and self.initial_money >= 0
            and self.final_money == self.initial_money + KOGA_TRAINER_REWARD_TOTAL
            and self.final_raw.map_id == MapId.FUCHSIA_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and party_core_intact(self.final_raw.party_species_ids)
            and self.party_hp == self.party_max_hp
            and all(hp > 0 for hp in self.party_hp)
            and all(status == 0 for status in self.party_status)
            and self.surf_pp == 15
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "defeat_koga",
            "geographic_dependency": {
                "reason": "post-Surf Fuchsia cannot legally return to Celadon before Soul Badge",
                "route15_return": "one_way_blocked",
                "cycling_road": "bicycle_required",
                "surf": "soul_badge_required",
                "unblocks": "Surf route toward the western Kanto network",
            },
            "mandatory_trainers": [
                {
                    "label": item.label,
                    "opponent": item.opponent,
                    "trainer_class": item.trainer_class,
                    "trainer_number": item.trainer_number,
                    "event": item.event,
                    "move_id": SURF,
                    "selected_pp_spent": item.selected_pp_spent,
                }
                for item in self.battles[:-1]
            ],
            "recoveries": {
                "pokemon_center_visits_before_koga": 2,
                "mart_purchases": 0,
                "consumables_used": 0,
            },
            "koga": {
                "opponent": self.battles[-1].opponent,
                "trainer_class": self.battles[-1].trainer_class,
                "trainer_number": self.battles[-1].trainer_number,
                "party": ["Koffing L37", "Muk L39", "Koffing L37", "Weezing L43"],
                "surf_pp_spent": self.battles[-1].selected_pp_spent,
                # Retained for receipt-schema compatibility. This describes
                # the healed chapter boundary, not whether Selfdestruct
                # caused a temporary terminal mutual KO inside the battle.
                "no_faint": all(value > 0 for value in self.party_hp),
                "terminal_mutual_ko": self.battles[-1].terminal_mutual_ko,
                "continued_after_faint": self.battles[-1].continued_after_faint,
                "party_restored_at_boundary": all(value > 0 for value in self.party_hp),
            },
            "rewards": {
                "beat_koga_event": self.beat_koga,
                "soul_badge": self.soul_badge,
                "soul_badge_mirror": self.soul_badge_mirror,
                "got_tm06_event": self.got_tm06,
                "tm06_toxic_retained": (int(ItemId.TM06_TOXIC), 1) in self.final_bag,
                "regular_trainers_deactivated": self.trainer_events_after_koga == (True,) * 6,
            },
            "money_remaining": self.final_money,
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


def run_koga_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    timing: KogaTiming = DEFAULT_KOGA_TIMING,
    progress: ProgressSink | None = None,
) -> KogaChapterReport:
    start_frames = emulator.frame_count
    actions = _CountingExecutor(executor)
    records: list[KogaCheckpoint] = []
    battles: list[KogaBattleEvidence] = []
    initial = reader.read()
    _require(initial, MapId.FUCHSIA_POKECENTER, (3, 3), "Surf boundary")
    initial_bag = _bag_tuple(emulator)
    initial_money = _money(emulator)
    if initial.first_party_moves is None or initial.first_party_moves[SURF_SLOT - 1] != SURF:
        raise KogaChapterError("Koga input lacks Surf in slot four.")
    if any(_event(emulator, event) for event in REGULAR_TRAINER_EVENTS):
        raise KogaChapterError("Fuchsia Gym trainers were not pristine at chapter start.")
    if _event(emulator, EventFlag.BEAT_KOGA) or _event(emulator, EventFlag.GOT_TM06):
        raise KogaChapterError("Koga reward events were already set.")
    if any(item == int(ItemId.TM06_TOXIC) for item, _ in initial_bag):
        raise KogaChapterError("TM06 was already present at chapter start.")
    _checkpoint(records, progress, emulator, initial, "koga_ready", "Surf-ready Fuchsia boundary")

    _move(actions, reader, CENTER_TO_GYM, timing, "Fuchsia Gym entry")
    _require(reader.read(), MapId.FUCHSIA_GYM, (4, 17), "Fuchsia Gym entry")
    _checkpoint(records, progress, emulator, reader.read(), "gym_entry", "Entered Fuchsia Gym")

    _move(actions, reader, GYM_TO_JUGGLER3, timing, "Juggler 3 sight line")
    battles.append(
        _fight(
            actions,
            reader,
            emulator,
            timing,
            "Juggler 3",
            (0xDD, 0x15, 3),
            EventFlag.BEAT_FUCHSIA_GYM_TRAINER_1,
            KOGA_PP_BOUNDS[0][1],
            RedBattlePlanId.KOGA_JUGGLER_3,
            allow_disable_fallback=True,
        )
    )
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "juggler3",
        "Defeated mandatory Juggler 3",
    )

    _move(actions, reader, JUGGLER3_TO_TAMER2, timing, "Tamer 2 sight line")
    battles.append(
        _fight(
            actions,
            reader,
            emulator,
            timing,
            "Tamer 2",
            (0xDE, 0x16, 2),
            EventFlag.BEAT_FUCHSIA_GYM_TRAINER_4,
            8,
            RedBattlePlanId.KOGA_TAMER_2,
        )
    )
    _checkpoint(records, progress, emulator, reader.read(), "tamer2", "Defeated mandatory Tamer 2")

    _move(actions, reader, TAMER2_TO_CENTER, timing, "first Fuchsia recovery")
    _heal_center(actions, reader, emulator, timing)
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "recovery1",
        "Healed after east Gym pair",
    )

    _move(actions, reader, CENTER_TO_JUGGLER4, timing, "Juggler 4 sight line")
    battles.append(
        _fight(
            actions,
            reader,
            emulator,
            timing,
            "Juggler 4",
            (0xDD, 0x15, 4),
            EventFlag.BEAT_FUCHSIA_GYM_TRAINER_5,
            8,
            RedBattlePlanId.KOGA_JUGGLER_4,
            allow_disable_fallback=True,
            reserve_pivot_threshold=JUGGLER_4_PIVOT_HP_THRESHOLD,
        )
    )
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "juggler4",
        "Defeated mandatory Juggler 4",
    )

    trainer_events_before_koga = tuple(_event(emulator, event) for event in REGULAR_TRAINER_EVENTS)
    if trainer_events_before_koga != (False, True, False, False, True, True):
        raise KogaChapterError(f"Minimum-trainer gate changed: {trainer_events_before_koga!r}.")
    _move(actions, reader, JUGGLER4_TO_CENTER, timing, "second Fuchsia recovery")
    _heal_center(actions, reader, emulator, timing)
    _checkpoint(records, progress, emulator, reader.read(), "recovery2", "Healed before Koga")

    _move(actions, reader, CENTER_TO_KOGA, timing, "Koga stance")
    _require(reader.read(), MapId.FUCHSIA_GYM, (4, 11), "Koga stance")
    _checkpoint(records, progress, emulator, reader.read(), "koga_stance", "Reached Koga")

    _pulse(actions, MacroActionKind.MOVE, "up", frames=120)
    actions.execute(MacroAction(MacroActionKind.INTERACT))
    bag_before_koga = _bag_tuple(emulator)
    battles.append(
        _fight(
            actions,
            reader,
            emulator,
            timing,
            "Koga",
            (KOGA_OPPONENT, KOGA_TRAINER_CLASS, KOGA_TRAINER_NUMBER),
            EventFlag.BEAT_KOGA,
            15,
            RedBattlePlanId.KOGA_LEADER,
            clear_text=False,
            allow_disable_fallback=True,
            reserve_pivot_enemy_species=MUK_SPECIES_ID,
        )
    )
    _checkpoint(records, progress, emulator, reader.read(), "koga_defeated", "Defeated Koga")

    _clear_text(actions, reader, timing)
    trainer_events_after_koga = tuple(_event(emulator, event) for event in REGULAR_TRAINER_EVENTS)
    got_tm06 = _event(emulator, EventFlag.GOT_TM06)
    beat_koga = _event(emulator, EventFlag.BEAT_KOGA)
    soul_badge = bool(emulator.read_u8(RamAddress.OBTAINED_BADGES) & int(Badge.SOUL))
    soul_badge_mirror = bool(emulator.read_u8(RamAddress.BEAT_GYM_FLAGS) & int(Badge.SOUL))
    if (
        _bag_tuple(emulator) != tuple(sorted((*bag_before_koga, (int(ItemId.TM06_TOXIC), 1))))
        or not got_tm06
        or not beat_koga
        or not soul_badge
        or not soul_badge_mirror
        or trainer_events_after_koga != (True,) * 6
    ):
        raise KogaChapterError(
            "Koga reward or trainer-deactivation gate failed: "
            f"bag_before={bag_before_koga!r}, bag_after={_bag_tuple(emulator)!r}, "
            f"events={(got_tm06, beat_koga)!r}, "
            f"badges={(soul_badge, soul_badge_mirror)!r}, "
            f"trainers={trainer_events_after_koga!r}."
        )
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "rewards",
        "Verified Soul Badge and TM06",
    )

    _move(actions, reader, KOGA_TO_CENTER, timing, "post-Koga recovery")
    _heal_center(actions, reader, emulator, timing)
    final = reader.read()
    _require(final, MapId.FUCHSIA_POKECENTER, (3, 3), "stable Koga boundary")
    _checkpoint(records, progress, emulator, final, "koga_stable", "Stable healed Fuchsia boundary")

    report = KogaChapterReport(
        tuple(records),
        tuple(battles),
        final,
        initial_bag,
        _bag_tuple(emulator),
        initial_money,
        _money(emulator),
        trainer_events_before_koga,
        trainer_events_after_koga,
        got_tm06,
        beat_koga,
        soul_badge,
        soul_badge_mirror,
        _party_hp(emulator),
        _party_max_hp(emulator),
        _party_status(emulator),
        int((final.first_party_pp or (0, 0, 0, 0))[SURF_SLOT - 1] & 0x3F),
        emulator.frame_count - start_frames,
        actions.actions_executed,
        not emulator.pressed_buttons,
    )
    if not report.passed:
        raise KogaChapterError(
            f"Koga chapter failed its public evidence contract: {report.public_dict()!r}."
        )
    return report


def _fight(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: KogaTiming,
    label: str,
    identity: tuple[int, int, int],
    event: EventFlag,
    max_spent: int,
    battle_plan_id: str,
    *,
    clear_text: bool = True,
    allow_disable_fallback: bool = False,
    reserve_pivot_threshold: int | None = None,
    reserve_pivot_enemy_species: int | None = None,
) -> KogaBattleEvidence:
    battle = _settle_trainer_identity(actions, reader, emulator, timing, label, identity)
    before_pp = battle.first_party_pp
    required_policy = (
        RequiredMovePolicy.ANY_USABLE
        if allow_disable_fallback
        else RequiredMovePolicy.EXACT_REQUIRED
    )

    last_active_party_index = battle.active_party_index

    def choose_move(raw: RawGameState) -> int:
        nonlocal last_active_party_index
        if raw.active_party_index is not None:
            last_active_party_index = raw.active_party_index
        party_hp = _party_hp(emulator)
        pivot_target = _koga_matchup_pivot_target(
            raw, party_hp, reserve_pivot_enemy_species
        ) or _koga_reserve_pivot_target(
            raw, party_hp, reserve_pivot_threshold
        )
        if pivot_target is not None:
            raise _PauseForKogaReservePivot(pivot_target)
        try:
            return _koga_move_slot(raw, allow_disable_fallback=allow_disable_fallback)
        except KogaChapterError as error:
            raise KogaChapterError(f"{label}: {error}") from error

    terminal_mutual_ko = False
    continued_after_faint = False
    faint_pivots = 0
    intent = BattleIntent(
        "defeat_koga",
        battle_plan_id=battle_plan_id,
        required_move_policy=required_policy,
        required_move_ref=(
            None if allow_disable_fallback else pokemon_red_move_ref(SURF)
        ),
    )
    try:
        while True:
            try:
                final = run_adaptive_trainer_battle(
                    reader,
                    actions,
                    choose_move,
                    expected_map=MapId.FUCHSIA_GYM,
                    intent=intent,
                    required_move_id=None if allow_disable_fallback else SURF,
                    timing=KOGA_BATTLE_TIMING,
                    label=label,
                    unknown_cancel_interval=3,
                )
                break
            except BattleRuntimeError as error:
                if isinstance(error.__cause__, _PauseForKogaReservePivot):
                    pivot_target = error.__cause__.party_index
                    pivot_label = f"{label} healthy reserve pivot"
                else:
                    if (
                        not allow_disable_fallback
                        or "active battler fainted" not in str(error)
                    ):
                        raise
                    pivot_target = _settle_koga_fainted_pivot_target(
                        actions,
                        reader,
                        emulator,
                        timing,
                        last_active_party_index=last_active_party_index,
                    )
                    party_hp = _party_hp(emulator)
                    if faint_pivots >= max(0, len(party_hp) - 1):
                        raise KogaChapterError(
                            f"{label} exhausted its living-party continuation bound."
                        ) from error
                    pivot_label = f"{label} fainted-member continuation"
                try:
                    switch_active_battler(
                        actions,
                        reader,
                        emulator,
                        pivot_target,
                        label=pivot_label,
                        wait_frames=timing.wait_frames,
                    )
                except ProtectedRecoveryError as pivot_error:
                    raise KogaChapterError(str(pivot_error)) from pivot_error
                if not isinstance(error.__cause__, _PauseForKogaReservePivot):
                    faint_pivots += 1
                    continued_after_faint = True
    except BattleRuntimeError:
        mutual = reader.read()
        if (
            label != "Koga"
            or mutual.battle_state != 2
            or mutual.battler_hp != 0
            or mutual.enemy_hp != 0
            or not any(hp > 0 for hp in _party_hp(emulator)[1:])
        ):
            raise
        final = _settle_terminal_mutual_ko(actions, reader, emulator, timing)
        note_observed_trainer_battle_exit(intent)
        terminal_mutual_ko = True
    if before_pp is None or final.first_party_pp is None:
        raise KogaChapterError(f"{label} lacks PP evidence.")
    spent = (before_pp[SURF_SLOT - 1] & 0x3F) - (final.first_party_pp[SURF_SLOT - 1] & 0x3F)
    hp = _party_hp(emulator)
    max_hp = _party_max_hp(emulator)
    status = _party_status(emulator)
    if clear_text:
        _clear_text(actions, reader, timing)
    minimum_spent = 0 if allow_disable_fallback else 1
    if (
        not minimum_spent <= spent <= max_spent
        or not _event(emulator, event)
        or (
            any(value <= 0 for value in hp)
            and not (
                terminal_mutual_ko
                and hp[0] == 0
                and all(value > 0 for value in hp[1:])
            )
            and not (
                continued_after_faint
                and any(value > 0 for value in hp)
            )
        )
    ):
        raise KogaChapterError(
            f"{label} evidence mismatch: spent={spent}, event={_event(emulator, event)}, hp={hp!r}."
        )
    return KogaBattleEvidence(
        label,
        identity[0],
        identity[1],
        identity[2],
        int(event),
        spent,
        hp[0],
        max_hp[0],
        status[0],
        terminal_mutual_ko,
        continued_after_faint,
    )


def _settle_terminal_mutual_ko(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: KogaTiming,
) -> RawGameState:
    """Select a living teammate after Weezing's terminal Selfdestruct."""

    target = next(index for index, hp in enumerate(_party_hp(emulator)) if hp > 0)
    for pulse_index in range(64):
        raw = reader.read()
        if raw.battle_state == 0:
            if reader.read_input_readiness().ready:
                return raw
            _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
            continue
        if raw.battle_state != 2:
            raise KogaChapterError("Koga mutual-KO recovery changed battle type.")
        if (raw.battler_hp or 0) > 0:
            _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
            continue
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == target:
            _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
        else:
            _pulse(
                actions,
                MacroActionKind.MOVE,
                "down" if cursor < target else "up",
                frames=120,
            )
        if pulse_index % 5 == 4:
            _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    raise KogaChapterError("Koga terminal mutual-KO recovery exceeded its bound.")


def _koga_move_slot(raw: RawGameState, *, allow_disable_fallback: bool) -> int:
    """Choose Surf or the first legal reserve attack after Gen I Disable."""

    moves = raw.battler_moves
    pp = raw.battler_pp
    if moves is None or pp is None:
        raise KogaChapterError("battle lacks live move and PP evidence")
    candidates = (
        (1, 2, 3, 4)
        if raw.active_party_index not in {None, 0}
        else ((SURF_SLOT, 3, 1, 2) if allow_disable_fallback else (SURF_SLOT,))
    )
    for slot in candidates:
        index = slot - 1
        if (
            len(moves) > index
            and len(pp) > index
            and moves[index] != 0
            and pp[index] & 0x3F
            and raw.player_disabled_move_slot != slot
        ):
            return slot
    raise KogaChapterError("battle has no legal ranked attack")


class _PauseForKogaReservePivot(Exception):
    def __init__(self, party_index: int) -> None:
        self.party_index = party_index


def _koga_reserve_pivot_target(
    raw: RawGameState,
    party_hp: tuple[int, ...],
    threshold: int | None,
) -> int | None:
    """Protect the story lead by handing a dangerous finish to the healthiest reserve."""

    if (
        threshold is None
        or raw.active_party_index not in {None, 0}
        or not 0 < (raw.battler_hp or 0) <= threshold
    ):
        return None
    living_reserves = tuple(
        (hp, index) for index, hp in enumerate(party_hp[1:], start=1) if hp > threshold
    )
    return max(living_reserves, default=(0, -1))[1] if living_reserves else None


def _koga_matchup_pivot_target(
    raw: RawGameState,
    party_hp: tuple[int, ...],
    enemy_species_id: int | None,
) -> int | None:
    """Hand a preregistered dangerous matchup to the healthiest living teammate."""

    if (
        enemy_species_id is None
        or raw.enemy_species_id != enemy_species_id
        or raw.active_party_index not in {None, 0}
        or (raw.battler_hp or 0) <= 0
    ):
        return None
    living_reserves = tuple(
        (hp, index) for index, hp in enumerate(party_hp[1:], start=1) if hp > 0
    )
    return max(living_reserves, default=(0, -1))[1] if living_reserves else None


def _koga_fainted_pivot_target(
    raw: RawGameState,
    party_hp: tuple[int, ...],
    *,
    last_active_party_index: int | None = None,
) -> int | None:
    """Choose the healthiest living teammate after an observed active-member KO."""

    active_party_index = raw.active_party_index
    if active_party_index is None:
        active_party_index = last_active_party_index
    if raw.battle_state != 2 or (
        raw.active_party_index is not None and (raw.battler_hp or 0) > 0
    ):
        return None
    # PLAYER_MON_NUMBER briefly carries an out-of-party sentinel while the
    # forced-switch dialogue is opening, so RawGameState intentionally exposes
    # no active index at this exact boundary, before the fainted HP is copied
    # back into the ordinary party table.  Carrying forward the last active
    # index excludes that member without trusting the temporarily stale HP.
    living = tuple(
        (hp, index)
        for index, hp in enumerate(party_hp)
        if index != active_party_index and hp > 0
    )
    return max(living, default=(0, -1))[1] if living else None


def _settle_koga_fainted_pivot_target(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: KogaTiming,
    *,
    last_active_party_index: int | None,
) -> int:
    """Advance the transient KO boundary until the party table is stable."""

    raw = reader.read()
    party_hp = _party_hp(emulator)
    for pulse_index in range(16):
        target = _koga_fainted_pivot_target(
            raw,
            party_hp,
            last_active_party_index=last_active_party_index,
        )
        if target is not None:
            return target
        if raw.battle_state != 2:
            raise KogaChapterError("Koga faint continuation left its trainer battle.")
        _pulse(
            actions,
            MacroActionKind.CANCEL if (pulse_index + 1) % 4 == 0 else MacroActionKind.CONFIRM,
            frames=timing.wait_frames,
        )
        raw = reader.read()
        party_hp = _party_hp(emulator)
    raise KogaChapterError(
        "Koga faint continuation never exposed a living teammate: "
        f"party_hp={party_hp!r}, active={raw.active_party_index!r}, "
        f"battler_hp={raw.battler_hp!r}."
    )


def _settle_trainer_identity(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: KogaTiming,
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
    raise KogaChapterError(f"{label} identity did not settle to {identity!r}.")


def _move(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    directions: Iterable[str],
    timing: KogaTiming,
    label: str,
) -> None:
    state = reader.read()
    for step, direction in enumerate(directions, 1):
        before = (state.map_id, state.player_x, state.player_y)
        for _ in range(timing.movement_retries):
            _pulse(actions, MacroActionKind.MOVE, direction, frames=timing.movement_frames)
            state = reader.read()
            if state.battle_state:
                raise KogaChapterError(f"{label} entered an unexpected battle at step {step}.")
            if (state.map_id, state.player_x, state.player_y) != before:
                break
            if not reader.read_input_readiness().ready:
                _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
                state = reader.read()
        else:
            raise KogaChapterError(
                f"{label} blocked at step {step}: {direction}; "
                f"{(state.map_id, state.player_x, state.player_y)!r}."
            )
        if not party_core_intact(state.party_species_ids):
            raise KogaChapterError(f"{label} changed the qualified party.")


def _heal_center(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: KogaTiming,
) -> None:
    approach = reader.read()
    _move(
        actions,
        reader,
        _nurse_approach_directions(approach),
        timing,
        "Fuchsia nurse approach",
    )
    _require(reader.read(), MapId.FUCHSIA_POKECENTER, (3, 3), "Fuchsia nurse")
    actions.execute(MacroAction(MacroActionKind.INTERACT))
    for _ in range(timing.heal_pulses):
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
        if (
            _party_hp(emulator) == _party_max_hp(emulator)
            and all(status == 0 for status in _party_status(emulator))
            and ((reader.read().first_party_pp or (0, 0, 0, 0))[SURF_SLOT - 1] & 0x3F) == 15
        ):
            _clear_text(actions, reader, timing)
            return
    raise KogaChapterError("Fuchsia Center did not restore the complete party and Surf PP.")


def _nurse_approach_directions(raw: RawGameState) -> tuple[str, ...]:
    if raw.map_id != MapId.FUCHSIA_POKECENTER or raw.player_x != 3:
        return ()
    if raw.player_y == 4:
        return ("up",)
    return ()


def _clear_text(
    actions: _CountingExecutor,
    reader: PokemonRedStateReader,
    timing: KogaTiming,
) -> None:
    for _ in range(6):
        _pulse(actions, MacroActionKind.CANCEL, frames=timing.wait_frames)
    if not reader.read_input_readiness().ready:
        raise KogaChapterError("Dialogue did not return input authority.")


def _event(emulator: EmulatorState, event: EventFlag) -> bool:
    value = int(event)
    return bool(emulator.read_u8(int(RamAddress.EVENT_FLAGS) + value // 8) & (1 << (value % 8)))


def _bag_tuple(emulator: EmulatorState) -> tuple[tuple[int, int], ...]:
    return tuple(sorted((int(item), count) for item, count in Counter(_bag(emulator)).items()))


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
        raise KogaChapterError(
            f"{label} missed gate: map={raw.map_id!r}, "
            f"coordinate={(raw.player_x, raw.player_y)!r}, battle={raw.battle_state!r}."
        )


def _checkpoint(
    records: list[KogaCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(KogaCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            KogaProgress(
                checkpoint_id,
                label,
                len(records),
                KOGA_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )


def _pulse(
    actions: _CountingExecutor,
    kind: MacroActionKind,
    value: str | int | None = None,
    *,
    frames: int,
) -> None:
    actions.execute(MacroAction(kind, value))
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))
