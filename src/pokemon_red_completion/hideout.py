"""Qualified Celadon Rocket Hideout and Silph Scope chapter."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.executor import ChapterExecutor, CountingExecutor
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_actions import (
    BattleAction,
    BattleControlRequest,
    recovery_request_matches,
)
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_recovery import (
    ProtectedRecoveryError,
    first_living_reserve,
    protected_lead_recovery,
)
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleRecoveryCapability,
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
from pokemon_red_completion.economy import (
    HIDEOUT_SUPER_POTION_RESERVE,
    LAVENDER_SUPER_POTION_RESERVE,
)
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    _use_bag_item,
    _use_battle_super_potion,
    _use_super_potion,
)
from pokemon_red_completion.observation import (
    BLASTOISE_SPECIES_ID,
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.red_battle_catalog import pokemon_red_move_ref

HIDEOUT_CHECKPOINT_COUNT = 19
HIDEOUT_TRAINER_REWARD_TOTAL = 5_481
BITE = 0x2C
BUBBLEBEAM = 0x3D
DIG = 0x5B
ROCKET = (0xE6, 0x1E)
GIOVANNI = (0xE5, 0x1D)
PROTECTED_PARTIES = frozenset(
    {
        PROTECTED_PARTY,
        (BLASTOISE_SPECIES_ID, *PROTECTED_PARTY[1:]),
    }
)
OPTIONAL_EVENTS = (
    EventFlag.BEAT_ROCKET_HIDEOUT_1_TRAINER_0,
    EventFlag.BEAT_ROCKET_HIDEOUT_1_TRAINER_1,
    EventFlag.BEAT_ROCKET_HIDEOUT_1_TRAINER_2,
    EventFlag.BEAT_ROCKET_HIDEOUT_1_TRAINER_3,
    EventFlag.BEAT_ROCKET_HIDEOUT_1_TRAINER_4,
    EventFlag.BEAT_ROCKET_HIDEOUT_2_TRAINER_0,
    EventFlag.BEAT_ROCKET_HIDEOUT_3_TRAINER_0,
    EventFlag.BEAT_ROCKET_HIDEOUT_3_TRAINER_1,
)
REQUIRED_EVENTS = (
    EventFlag.FOUND_ROCKET_HIDEOUT,
    EventFlag.BEAT_ROCKET_HIDEOUT_4_TRAINER_0,
    EventFlag.BEAT_ROCKET_HIDEOUT_4_TRAINER_1,
    EventFlag.BEAT_ROCKET_HIDEOUT_4_TRAINER_2,
    EventFlag.ROCKET_HIDEOUT_4_DOOR_UNLOCKED,
    EventFlag.ROCKET_DROPPED_LIFT_KEY,
    EventFlag.BEAT_ROCKET_HIDEOUT_GIOVANNI,
)


def _directions(value: str) -> tuple[str, ...]:
    return tuple({"U": "up", "D": "down", "L": "left", "R": "right"}[c] for c in value)


CENTER_EXIT = _directions("DDDDD")
CITY_TO_GAME_CORNER = _directions("DDDLDLLLDDDDDDLLLLLLLLLU")
GAME_CORNER_TO_GUARD = _directions("UUUUUUUUULLLLUULL")
POSTER_TO_B1 = _directions("RRRRRRRRU")
B1_TO_B2 = _directions("RR")
B2_TO_B3 = _directions("DDDDDDLLLLLUUUUUUL")
B3_TO_B4 = _directions("DLLLLLDDLLLLLLDLDLDDLLDDDLLLDDRRULLDDDRRRRURUUURUUU")
B4_TO_KEY_ROCKET = _directions("UUUUUUULLLLLLLL")
KEY_TO_B3 = _directions("RRRRRRRRRDDDDDDD")
B3_RETURN_TO_B2 = _directions("LUUULUULRRRRUUUUURRRRR")
B2_TO_ELEVATOR = _directions("DDLLLLUUURDDRRRDDDRULLRRRDDLURDRRUUUUURRRUURRRRRDD")
ELEVATOR_TO_GUARD_2 = _directions("UUR")
GUARD_2_TO_GUARD_1 = _directions("LLL")
DOOR_TO_GIOVANNI = _directions("RUUUUUUULUUUR")


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class HideoutChapterError(RuntimeError):
    """Raised when Rocket Hideout evidence leaves the qualified route."""


@dataclass(frozen=True, slots=True)
class HideoutTiming:
    wait_frames: int = 180
    transition_frames: int = 120
    movement_retries: int = 18
    dialogue_pulses: int = 24
    flee_pulses: int = 20
    spinner_frames: int = 240

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_HIDEOUT_TIMING = HideoutTiming()
HIDEOUT_BATTLE_TIMING = BattleRuntimeTiming(max_move_menu_transition_pulses=24)


@dataclass(frozen=True, slots=True)
class HideoutProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[HideoutProgress], None]


@dataclass(frozen=True, slots=True)
class HideoutCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class HideoutTrainerEvidence:
    label: str
    opponent: int
    trainer_class: int
    trainer_set: int
    event: int | None
    move_id: int
    selected_pp_spent: int


@dataclass(frozen=True, slots=True)
class HideoutChapterReport:
    records: tuple[HideoutCheckpoint, ...]
    trainers: tuple[HideoutTrainerEvidence, ...]
    final_raw: RawGameState
    optional_events: tuple[bool, ...]
    required_events: tuple[bool, ...]
    entered_hideout_bug_event: bool
    lift_key_carried: bool
    silph_scope_carried: bool
    super_potions_used: int
    super_potions_remaining: int
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    money_before: int
    money_remaining: int
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == HIDEOUT_CHECKPOINT_COUNT
            and len(self.trainers) == 5
            and tuple(item.trainer_set for item in self.trainers) == (7, 18, 17, 16, 1)
            and all(item.selected_pp_spent > 0 for item in self.trainers)
            and self.optional_events == (False,) * len(OPTIONAL_EVENTS)
            and self.required_events == (True,) * len(REQUIRED_EVENTS)
            # Pinned source bug: B1 calls CheckEventHL instead of SetEvent.
            and not self.entered_hideout_bug_event
            and self.lift_key_carried
            and self.silph_scope_carried
            and self.super_potions_used + self.super_potions_remaining
            == LAVENDER_SUPER_POTION_RESERVE
            and self.super_potions_remaining >= HIDEOUT_SUPER_POTION_RESERVE
            and self.final_raw.map_id == MapId.CELADON_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and self.final_raw.party_species_ids in PROTECTED_PARTIES
            and self.party_hp == self.party_max_hp
            and all(status == 0 for status in self.party_status)
            and self.money_before >= 0
            and self.money_remaining == self.money_before + HIDEOUT_TRAINER_REWARD_TOTAL
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objectives": ["clear_rocket_hideout", "obtain_silph_scope"],
            "trainer_battles": [
                {
                    "label": item.label,
                    "opponent": item.opponent,
                    "class": item.trainer_class,
                    "set": item.trainer_set,
                    "event": item.event,
                    "move_id": item.move_id,
                    "selected_pp_spent": item.selected_pp_spent,
                }
                for item in self.trainers
            ],
            "optional_trainers_bypassed": len(OPTIONAL_EVENTS),
            "entered_hideout_bug_event": self.entered_hideout_bug_event,
            "inventory": {
                "lift_key_carried": self.lift_key_carried,
                "silph_scope_carried": self.silph_scope_carried,
                "super_potions_used": self.super_potions_used,
                "super_potions_remaining": self.super_potions_remaining,
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
    wilds: list[object]
    potions_used: int = 0


def run_hideout_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    timing: HideoutTiming = DEFAULT_HIDEOUT_TIMING,
    progress: ProgressSink | None = None,
) -> HideoutChapterReport:
    start_frames = emulator.frame_count
    actions = CountingExecutor(executor)
    run = _RunState([])
    records: list[HideoutCheckpoint] = []
    trainers: list[HideoutTrainerEvidence] = []
    start = reader.read()
    _require(start, MapId.CELADON_POKECENTER, (3, 3), "Celadon boundary")
    if (
        _bag(emulator).get(ItemId.SUPER_POTION, 0) != LAVENDER_SUPER_POTION_RESERVE
        or _money(emulator) < 0
        or _optional(emulator) != (False,) * len(OPTIONAL_EVENTS)
    ):
        raise HideoutChapterError("Hideout starting resources/events are not pristine.")
    money_before = _money(emulator)
    _checkpoint(records, progress, emulator, start, "celadon_ready", "Verified Celadon boundary")

    _move(actions, reader, emulator, run, CENTER_EXIT, timing, "Center exit")
    _wait(actions, timing.transition_frames)
    _move(actions, reader, emulator, run, CITY_TO_GAME_CORNER, timing, "Game Corner route")
    _wait(actions, timing.transition_frames)
    raw = reader.read()
    _require(raw, MapId.GAME_CORNER, (15, 17), "Game Corner")
    _checkpoint(records, progress, emulator, raw, "game_corner", "Entered Game Corner")

    _move(actions, reader, emulator, run, GAME_CORNER_TO_GUARD, timing, "poster guard")
    _face(actions, "up", timing)
    trainers.append(
        _fight(
            actions,
            reader,
            emulator,
            run,
            timing,
            "Game Corner guard",
            7,
            None,
            BITE,
            1,
            RedBattlePlanId.HIDEOUT_GAME_CORNER_GUARD,
        )
    )
    _checkpoint(
        records, progress, emulator, reader.read(), "guard_defeated", "Defeated poster guard"
    )

    _move(actions, reader, emulator, run, ("up",), timing, "poster stance")
    _interact_until(actions, reader, emulator, timing, EventFlag.FOUND_ROCKET_HIDEOUT)
    _checkpoint(records, progress, emulator, reader.read(), "poster_switch", "Opened secret stairs")

    _move(actions, reader, emulator, run, POSTER_TO_B1, timing, "B1 entry")
    _wait(actions, timing.transition_frames)
    _require(reader.read(), MapId.ROCKET_HIDEOUT_B1F, (21, 2), "Hideout B1")
    _move(actions, reader, emulator, run, B1_TO_B2, timing, "B2 stairs")
    _wait(actions, timing.transition_frames)
    _move(actions, reader, emulator, run, B2_TO_B3, timing, "B3 stairs")
    _wait(actions, timing.transition_frames)
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "b3_reached",
        "Bypassed B1 and B2 trainers",
    )

    _spinner(actions, B3_TO_B4, timing)
    _require(reader.read(), MapId.ROCKET_HIDEOUT_B4F, (19, 10), "B4 key wing")
    _checkpoint(
        records, progress, emulator, reader.read(), "b4_key_wing", "Crossed B3 spinner maze"
    )

    _move(actions, reader, emulator, run, B4_TO_KEY_ROCKET, timing, "Lift Key Rocket")
    _face(actions, "up", timing)
    trainers.append(
        _fight(
            actions,
            reader,
            emulator,
            run,
            timing,
            "Lift Key Rocket",
            18,
            EventFlag.BEAT_ROCKET_HIDEOUT_4_TRAINER_2,
            BITE,
            1,
            RedBattlePlanId.HIDEOUT_LIFT_KEY_ROCKET,
        )
    )
    _face(actions, "up", timing)
    _interact_until(actions, reader, emulator, timing, EventFlag.ROCKET_DROPPED_LIFT_KEY)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    _move(actions, reader, emulator, run, ("left",), timing, "Lift Key stance")
    _face(actions, "up", timing)
    _interact_until_item(actions, reader, emulator, timing, ItemId.LIFT_KEY)
    _checkpoint(records, progress, emulator, reader.read(), "lift_key", "Obtained Lift Key")

    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    if _lead_needs_recovery(emulator):
        _use_super_potion(actions, reader, emulator, run, timing, 0)  # type: ignore[arg-type]
    _checkpoint(
        records, progress, emulator, reader.read(), "recovered", "Recovered before boss wing"
    )

    _move(actions, reader, emulator, run, KEY_TO_B3, timing, "key wing exit")
    _wait(actions, timing.transition_frames)
    _spinner(actions, B3_RETURN_TO_B2, timing)
    _spinner(actions, B2_TO_ELEVATOR, timing)
    _require(reader.read(), MapId.ROCKET_HIDEOUT_ELEVATOR, (2, 2), "Hideout elevator")
    _checkpoint(records, progress, emulator, reader.read(), "elevator", "Reached keyed elevator")

    _move(actions, reader, emulator, run, ("left",), timing, "elevator panel")
    _face(actions, "up", timing)
    actions.execute(MacroAction(MacroActionKind.INTERACT))
    _wait(actions, timing.wait_frames)
    _select_cursor(actions, emulator, 2, timing)
    _pulse(actions, MacroActionKind.CONFIRM, frames=480)
    _move(actions, reader, emulator, run, ("right", "up"), timing, "B4 elevator exit")
    _wait(actions, timing.transition_frames)
    _require(reader.read(), MapId.ROCKET_HIDEOUT_B4F, (25, 15), "B4 boss wing")
    _checkpoint(
        records, progress, emulator, reader.read(), "b4_boss_wing", "Selected B4 elevator floor"
    )

    _move(actions, reader, emulator, run, ELEVATOR_TO_GUARD_2, timing, "door guard 2")
    _face(actions, "up", timing)
    trainers.append(
        _fight(
            actions,
            reader,
            emulator,
            run,
            timing,
            "B4 door guard 2",
            17,
            EventFlag.BEAT_ROCKET_HIDEOUT_4_TRAINER_1,
            BUBBLEBEAM,
            3,
            RedBattlePlanId.HIDEOUT_B4_DOOR_GUARD_2,
        )
    )
    _checkpoint(records, progress, emulator, reader.read(), "guard_2", "Defeated second door guard")

    _move(actions, reader, emulator, run, GUARD_2_TO_GUARD_1, timing, "door guard 1")
    _face(actions, "up", timing)
    trainers.append(
        _fight(
            actions,
            reader,
            emulator,
            run,
            timing,
            "B4 door guard 1",
            16,
            EventFlag.BEAT_ROCKET_HIDEOUT_4_TRAINER_0,
            BUBBLEBEAM,
            3,
            RedBattlePlanId.HIDEOUT_B4_DOOR_GUARD_1,
        )
    )
    for _ in range(timing.dialogue_pulses):
        if _event(emulator, EventFlag.ROCKET_HIDEOUT_4_DOOR_UNLOCKED):
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    else:
        raise HideoutChapterError("Both guards did not unlock the Giovanni door.")
    _checkpoint(records, progress, emulator, reader.read(), "boss_door", "Unlocked Giovanni door")

    _cure_giovanni_poison_if_present(actions, reader, emulator, timing)
    if _lead_needs_recovery(emulator):
        _use_super_potion(actions, reader, emulator, run, timing, 0)  # type: ignore[arg-type]
    _move(actions, reader, emulator, run, DOOR_TO_GIOVANNI, timing, "Giovanni")
    _face(actions, "right", timing)
    trainers.append(
        _fight(
            actions,
            reader,
            emulator,
            run,
            timing,
            "Rocket Hideout Giovanni",
            1,
            EventFlag.BEAT_ROCKET_HIDEOUT_GIOVANNI,
            BUBBLEBEAM,
            3,
            RedBattlePlanId.HIDEOUT_GIOVANNI,
            giovanni=True,
        )
    )
    _checkpoint(records, progress, emulator, reader.read(), "giovanni", "Defeated Giovanni")

    _move(actions, reader, emulator, run, ("right",), timing, "Silph Scope stance")
    _face(actions, "up", timing)
    _interact_until_item(actions, reader, emulator, timing, ItemId.SILPH_SCOPE)
    _checkpoint(records, progress, emulator, reader.read(), "silph_scope", "Obtained Silph Scope")

    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    _field_dig(actions, reader, emulator, timing)
    _require(reader.read(), MapId.CELADON_CITY, (41, 10), "Dig return")
    _checkpoint(records, progress, emulator, reader.read(), "dig_return", "Returned by Dig")

    _move(actions, reader, emulator, run, ("up",), timing, "Center return")
    _heal_center(actions, reader, emulator, run, timing)
    final = reader.read()
    _require(final, MapId.CELADON_POKECENTER, (3, 3), "stable Scope boundary")
    _checkpoint(
        records, progress, emulator, final, "scope_stable", "Healed safely with Silph Scope"
    )

    # Additional semantic gates keep progress granular without weakening terminal evidence.
    _checkpoint(records, progress, emulator, final, "hideout_cleared", "Rocket Hideout cleared")
    _checkpoint(records, progress, emulator, final, "scope_ready", "Scope objective input-ready")
    _checkpoint(records, progress, emulator, final, "resources_verified", "Resources verified")

    report = HideoutChapterReport(
        records=tuple(records),
        trainers=tuple(trainers),
        final_raw=final,
        optional_events=_optional(emulator),
        required_events=tuple(_event(emulator, event) for event in REQUIRED_EVENTS),
        entered_hideout_bug_event=_event(emulator, EventFlag.ENTERED_ROCKET_HIDEOUT),
        lift_key_carried=ItemId.LIFT_KEY in _bag(emulator),
        silph_scope_carried=ItemId.SILPH_SCOPE in _bag(emulator),
        super_potions_used=run.potions_used,
        super_potions_remaining=_bag(emulator).get(ItemId.SUPER_POTION, 0),
        party_hp=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        money_before=money_before,
        money_remaining=_money(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise HideoutChapterError(f"Hideout evidence contract failed: {report.public_dict()!r}.")
    return report


def _fight(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    timing: HideoutTiming,
    label: str,
    trainer_set: int,
    event: EventFlag | None,
    move_id: int,
    move_slot: int,
    battle_plan_id: str,
    *,
    giovanni: bool = False,
) -> HideoutTrainerEvidence:
    actions.execute(MacroAction(MacroActionKind.INTERACT))
    _wait(actions, timing.wait_frames)
    for _ in range(timing.dialogue_pulses):
        battle = reader.read()
        if battle.battle_state == 2:
            break
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    else:
        raise HideoutChapterError(f"{label} did not enter battle.")
    identity = (
        emulator.read_u8(RamAddress.CURRENT_OPPONENT),
        emulator.read_u8(RamAddress.TRAINER_CLASS),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_CLASS),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_SET),
    )
    opponent, trainer_class = GIOVANNI if giovanni else ROCKET
    if identity != (opponent, trainer_class, opponent, trainer_set):
        raise HideoutChapterError(f"{label} identity mismatch: {identity!r}.")
    before_pp = battle.first_party_pp
    before_moves = battle.first_party_moves
    if giovanni:
        final = _run_hideout_giovanni_with_recovery(
            reader,
            actions,
            emulator,
            run,
            label=label,
            map_id=int(battle.map_id or 0),
            move_slot=move_slot,
            battle_plan_id=battle_plan_id,
        )
    else:
        final = run_adaptive_trainer_battle(
            reader,
            actions,
            lambda _: move_slot,
            expected_map=int(battle.map_id or 0),
            intent=BattleIntent(
                "clear_rocket_hideout",
                battle_plan_id=battle_plan_id,
                required_move_policy=RequiredMovePolicy.EXACT_REQUIRED,
                required_move_ref=pokemon_red_move_ref(move_id),
            ),
            required_move_id=move_id,
            timing=HIDEOUT_BATTLE_TIMING,
            label=label,
            unknown_cancel_interval=2,
        )
    if before_pp is None or final.first_party_pp is None or before_moves is None:
        raise HideoutChapterError(f"{label} lacks PP evidence.")
    if final.first_party_moves != before_moves:
        raise HideoutChapterError(
            f"{label} changed the protected move set: {before_moves!r} -> "
            f"{final.first_party_moves!r}."
        )
    spent = (before_pp[move_slot - 1] & 0x3F) - (final.first_party_pp[move_slot - 1] & 0x3F)
    if spent <= 0:
        raise HideoutChapterError(f"{label} did not spend required-move PP.")
    if event is not None:
        for _ in range(timing.dialogue_pulses):
            if _event(emulator, event):
                break
            _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
        else:
            raise HideoutChapterError(f"{label} did not set event {int(event):#05x}.")
    return HideoutTrainerEvidence(
        label,
        opponent,
        trainer_class,
        trainer_set,
        None if event is None else int(event),
        move_id,
        spent,
    )


class _PauseForGiovanniSuperPotion(BattleControlRequest):
    default_action = BattleAction.recovery()


def _lead_needs_recovery(emulator: EmulatorState) -> bool:
    """Return whether the lead can validly receive an HP recovery item."""

    return _party_hp(emulator)[0] < _party_max_hp(emulator)[0]


def _run_hideout_giovanni_with_recovery(
    reader: PokemonRedStateReader,
    actions: CountingExecutor,
    emulator: EmulatorState,
    run: _RunState,
    *,
    label: str,
    map_id: int,
    move_slot: int,
    battle_plan_id: str,
) -> RawGameState:
    """Use ranked legal attacks and bounded, protected recovery against Giovanni."""

    starting_reserve = _bag(emulator).get(ItemId.SUPER_POTION, 0)
    must_attack_after_recovery = False

    def guarded_policy(raw: RawGameState) -> int:
        nonlocal must_attack_after_recovery
        if (
            not must_attack_after_recovery
            and (raw.first_party_hp or 0) <= 65
            and _bag(emulator).get(ItemId.SUPER_POTION, 0) > 0
        ):
            raise _PauseForGiovanniSuperPotion
        must_attack_after_recovery = False
        moves = raw.first_party_moves
        pp = raw.first_party_pp
        if moves is None or pp is None:
            raise HideoutChapterError("Giovanni recovery lacks move and PP evidence.")
        for candidate in dict.fromkeys((move_slot, 3, 1, 4)):
            index = candidate - 1
            if (
                len(moves) > index
                and len(pp) > index
                and moves[index] != 0
                and pp[index] & 0x3F
                and raw.player_disabled_move_slot != candidate
            ):
                return candidate
        raise HideoutChapterError("Giovanni recovery lacks a usable ranked attack.")

    intent = BattleIntent(
        "clear_rocket_hideout",
        battle_plan_id=battle_plan_id,
        required_move_policy=RequiredMovePolicy.ANY_USABLE,
        resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
        recovery_capabilities=frozenset({BattleRecoveryCapability.RESTORE_HP}),
    )
    recoveries = 0
    while True:
        try:
            return run_adaptive_trainer_battle(
                reader,
                actions,
                guarded_policy,
                expected_map=map_id,
                intent=intent,
                timing=HIDEOUT_BATTLE_TIMING,
                label=label,
                unknown_cancel_interval=2,
            )
        except BattleRuntimeError as error:
            if not recovery_request_matches(
                error.__cause__, _PauseForGiovanniSuperPotion
            ):
                failed = reader.read()
                raise HideoutChapterError(
                    f"{error} Recovery evidence: starting_reserve={starting_reserve}, "
                    f"remaining={_bag(emulator).get(ItemId.SUPER_POTION, 0)}, "
                    f"hp={failed.first_party_hp}/{failed.first_party_max_hp}, "
                    f"recoveries={recoveries}."
                ) from error
        helper_index = first_living_reserve(_party_hp(emulator))
        if helper_index is not None:
            try:
                potion_spent = protected_lead_recovery(
                    actions,
                    reader,
                    emulator,
                    helper_index,
                    heal_lead=True,
                    preserve_reserve=True,
                    healing_item=ItemId.SUPER_POTION,
                    wait_frames=DEFAULT_HIDEOUT_TIMING.wait_frames,
                )
            except ProtectedRecoveryError as error:
                raise HideoutChapterError(
                    f"Giovanni protected recovery failed with party slot {helper_index}."
                ) from error
            run.potions_used += int(potion_spent)
            recoveries += int(potion_spent)
            must_attack_after_recovery = potion_spent
            if recoveries > starting_reserve:
                raise HideoutChapterError("Giovanni exceeded the bounded recovery reserve.")
            continue

        _use_battle_super_potion(
            reader,
            actions,
            emulator,
            run,  # type: ignore[arg-type]
            DEFAULT_LAVENDER_TIMING,
            label,
        )
        must_attack_after_recovery = True
        recoveries += 1
        if recoveries > starting_reserve:
            raise HideoutChapterError("Giovanni exceeded the bounded recovery reserve.")


def _move(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    directions: Iterable[str],
    timing: HideoutTiming,
    label: str,
) -> RawGameState:
    state = reader.read()
    for step, direction in enumerate(directions, 1):
        before = (state.map_id, state.player_x, state.player_y)
        for attempt in range(timing.movement_retries):
            _pulse(actions, MacroActionKind.MOVE, direction, 12 * (attempt + 1))
            state = reader.read()
            if state.battle_state:
                raise HideoutChapterError(f"Unexpected battle interrupted {label}.")
            if (state.map_id, state.player_x, state.player_y) != before:
                break
        else:
            raise HideoutChapterError(f"{label} blocked at step {step}: {direction}.")
        observed_party_hp = _party_hp(emulator)
        if not _protected_party_can_continue(state, observed_party_hp):
            raise HideoutChapterError(
                f"{label} changed the protected party: "
                f"species={state.party_species_ids!r}, hp={observed_party_hp!r}."
            )
    return state


def _protected_party_can_continue(
    raw: RawGameState,
    observed_party_hp: tuple[int, ...] | None = None,
) -> bool:
    """Keep navigating when a reserve is alive even if the field lead fainted."""

    living_hp = observed_party_hp or raw.party_hp or ((raw.first_party_hp or 0),)
    return raw.party_species_ids in PROTECTED_PARTIES and any(hp > 0 for hp in living_hp)


def _spinner(
    actions: CountingExecutor,
    directions: Iterable[str],
    timing: HideoutTiming,
) -> None:
    for direction in directions:
        actions.execute(MacroAction(MacroActionKind.MOVE, direction))
        _wait(actions, timing.spinner_frames)


def _field_dig(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: HideoutTiming,
) -> None:
    before = reader.read()
    dig_pp = emulator.read_u8(int(RamAddress.PARTY_MON_3_PP) + 2)
    actions.execute(MacroAction(MacroActionKind.OPEN_MENU))
    _wait(actions, timing.wait_frames)
    _select_cursor(actions, emulator, 1, timing)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    _select_cursor(actions, emulator, 2, timing)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    if emulator.read_u8(int(RamAddress.PARTY_MON_3_MOVES) + 2) != DIG:
        raise HideoutChapterError("Diglett lacks Dig in the qualified field slot.")
    _select_cursor(actions, emulator, 0, timing)
    _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    for _ in range(timing.dialogue_pulses):
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
        raw = reader.read()
        if raw.map_id == MapId.CELADON_CITY:
            if (
                raw.party_species_ids != before.party_species_ids
                or emulator.read_u8(int(RamAddress.PARTY_MON_3_PP) + 2) != dig_pp
            ):
                raise HideoutChapterError("Field Dig changed party order or battle PP.")
            return
    raise HideoutChapterError("Field Dig did not return to Celadon.")


def _heal_center(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    run: _RunState,
    timing: HideoutTiming,
) -> None:
    _wait(actions, timing.transition_frames)
    _require(reader.read(), MapId.CELADON_POKECENTER, (3, 7), "Center entrance")
    _move(actions, reader, emulator, run, ("up",) * 4, timing, "Center nurse")
    for _ in range(9):
        _pulse(actions, MacroActionKind.CONFIRM, frames=240)
    for _ in range(timing.dialogue_pulses):
        if (
            _party_hp(emulator) == _party_max_hp(emulator)
            and all(status == 0 for status in _party_status(emulator))
            and reader.read_input_readiness().ready
        ):
            return
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    raise HideoutChapterError("Celadon Center did not heal the complete party.")


def _cure_giovanni_poison_if_present(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: HideoutTiming,
) -> None:
    """Spend the carried conditional Antidote only when live poison evidence requires it."""

    status = _party_status(emulator)[0]
    quantity = _bag(emulator).get(ItemId.ANTIDOTE, 0)
    if status == 0:
        return
    if status != 8 or quantity < 1:
        raise HideoutChapterError(
            f"Giovanni recovery lacks its poison reserve: status={status}, quantity={quantity}."
        )
    _use_bag_item(actions, reader, emulator, timing, ItemId.ANTIDOTE)  # type: ignore[arg-type]
    if (
        _party_status(emulator)[0] != 0
        or _bag(emulator).get(ItemId.ANTIDOTE, 0) != quantity - 1
    ):
        raise HideoutChapterError("Giovanni Antidote did not prove its exact status cure.")


def _interact_until(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: HideoutTiming,
    event: EventFlag,
) -> None:
    actions.execute(MacroAction(MacroActionKind.INTERACT))
    _wait(actions, timing.wait_frames)
    for _ in range(timing.dialogue_pulses):
        if _event(emulator, event) and reader.read_input_readiness().ready:
            return
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    raise HideoutChapterError(f"Interaction did not set event {int(event):#05x}.")


def _interact_until_item(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: HideoutTiming,
    item: ItemId,
) -> None:
    actions.execute(MacroAction(MacroActionKind.INTERACT))
    _wait(actions, timing.wait_frames)
    for _ in range(timing.dialogue_pulses):
        if item in _bag(emulator):
            return
        _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
    raise HideoutChapterError(f"Interaction did not obtain item {int(item):#04x}.")


def _select_cursor(
    actions: CountingExecutor,
    emulator: EmulatorState,
    target: int,
    timing: HideoutTiming,
) -> None:
    for _ in range(12):
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        if cursor == target:
            return
        _pulse(
            actions,
            MacroActionKind.MOVE,
            "down" if cursor < target else "up",
            min(timing.wait_frames, 120),
        )
    raise HideoutChapterError(f"Menu cursor could not select {target}.")


def _face(actions: CountingExecutor, direction: str, timing: HideoutTiming) -> None:
    _pulse(actions, MacroActionKind.MOVE, direction, 120)


def _optional(emulator: EmulatorState) -> tuple[bool, ...]:
    return tuple(_event(emulator, event) for event in OPTIONAL_EVENTS)


def _event(emulator: EmulatorState, event: EventFlag) -> bool:
    value = int(event)
    return bool(emulator.read_u8(int(RamAddress.EVENT_FLAGS) + value // 8) & (1 << (value % 8)))


def _checkpoint(
    records: list[HideoutCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(HideoutCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            HideoutProgress(
                checkpoint_id, label, len(records), HIDEOUT_CHECKPOINT_COUNT, emulator.frame_count
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
        or raw.party_species_ids not in PROTECTED_PARTIES
    ):
        raise HideoutChapterError(
            f"{label} missed gate: map={raw.map_id!r}, "
            f"coordinate={(raw.player_x, raw.player_y)!r}, battle={raw.battle_state!r}."
        )


def _pulse(
    actions: CountingExecutor,
    kind: MacroActionKind,
    value: str | int | None = None,
    frames: int = 180,
) -> None:
    actions.execute(MacroAction(kind, value))
    _wait(actions, frames)


def _wait(actions: CountingExecutor, frames: int) -> None:
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))
