"""Qualified Fighting Dojo and Hitmonlee recruitment chapter.

The map, trainer order, parties, events, and gift behavior are pinned to
pret/pokered commit ``1e96034092686d006e863cace09e87273051a3d8``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleResourcePolicy,
    BattleRuntimeTiming,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.celadon import _party_hp, _party_max_hp, _party_status
from pokemon_red_completion.executor import ChapterExecutor, CountingExecutor
from pokemon_red_completion.observation import (
    EventFlag,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.silph import (
    CENTER_EXIT,
    DEFAULT_SILPH_TIMING,
    EmulatorState,
    SilphChapterError,
    SilphTiming,
    _await_trainer_battle,
    _event,
    _heal,
    _move,
    _move_verified,
    _navigate_saffron_coordinate,
)
from pokemon_red_completion.tower import party_core_intact

DOJO_CHECKPOINT_COUNT = 9
BLACKBELT_OPPONENT = 0xE0
BLACKBELT_TRAINER_CLASS = 0xE0
HITMONLEE = 0x2B
HITMONCHAN = 0x2C
HITMONLEE_GIFT_LEVEL = 30
DOJO_CITY_APPROACH = (26, 4)
DOJO_TRAINER_EVENTS = (
    EventFlag.BEAT_FIGHTING_DOJO_TRAINER_3,
    EventFlag.BEAT_FIGHTING_DOJO_TRAINER_1,
    EventFlag.BEAT_FIGHTING_DOJO_TRAINER_2,
    EventFlag.BEAT_FIGHTING_DOJO_TRAINER_0,
    EventFlag.BEAT_KARATE_MASTER,
)
DOJO_BATTLE_IDENTITIES = (
    (BLACKBELT_OPPONENT, BLACKBELT_TRAINER_CLASS, 5),
    (BLACKBELT_OPPONENT, BLACKBELT_TRAINER_CLASS, 3),
    (BLACKBELT_OPPONENT, BLACKBELT_TRAINER_CLASS, 4),
    (BLACKBELT_OPPONENT, BLACKBELT_TRAINER_CLASS, 2),
    (BLACKBELT_OPPONENT, BLACKBELT_TRAINER_CLASS, 1),
)
DOJO_BATTLE_PARTIES = (
    ((0x6A, 31), (0x39, 31), (0x75, 31)),
    ((0x6A, 32), (0x29, 32)),
    ((0x75, 36),),
    ((0x39, 31), (0x39, 31), (0x75, 31)),
    ((HITMONLEE, 37), (HITMONCHAN, 37)),
)
DOJO_BATTLE_PLANS = (
    RedBattlePlanId.DOJO_BLACKBELT_SET_5,
    RedBattlePlanId.DOJO_BLACKBELT_SET_3,
    RedBattlePlanId.DOJO_BLACKBELT_SET_4,
    RedBattlePlanId.DOJO_BLACKBELT_SET_2,
    RedBattlePlanId.DOJO_KARATE_MASTER,
)
DOJO_TRIGGER_STEPS = (4, 1, 1, 1, 1)
DOJO_BATTLE_TIMING = BattleRuntimeTiming(
    max_runtime_pulses=420,
    max_move_menu_transition_pulses=24,
    max_pp_confirmation_pulses=12,
    max_attack_confirmation_pulses=6,
    max_post_attack_transition_pulses=24,
)


class DojoChapterError(RuntimeError):
    """Raised when Fighting Dojo evidence violates its contract."""


@dataclass(frozen=True, slots=True)
class DojoProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[DojoProgress], None]


@dataclass(frozen=True, slots=True)
class DojoCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class DojoTurn:
    enemy_species: int
    enemy_level: int
    move_slot: int


@dataclass(frozen=True, slots=True)
class DojoBattleEvidence:
    identity: tuple[int, int, int]
    party: tuple[tuple[int, int], ...]
    turns: tuple[DojoTurn, ...]
    event: int


@dataclass(frozen=True, slots=True)
class DojoChapterReport:
    records: tuple[DojoCheckpoint, ...]
    final_raw: RawGameState
    battles: tuple[DojoBattleEvidence, ...]
    events_before: tuple[bool, ...]
    events_after: tuple[bool, ...]
    party_before: tuple[int, ...]
    party_after: tuple[int, ...]
    party_levels: tuple[int, ...]
    party_hp: tuple[int, ...]
    party_max_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    got_hitmonlee: bool
    got_hitmonchan: bool
    dojo_defeated: bool
    frames_executed: int
    actions_executed: int
    input_ready: bool
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == DOJO_CHECKPOINT_COUNT
            and self.events_before == (False,) * len(DOJO_TRAINER_EVENTS)
            and self.events_after == (True,) * len(DOJO_TRAINER_EVENTS)
            and tuple(battle.identity for battle in self.battles) == DOJO_BATTLE_IDENTITIES
            and tuple(battle.party for battle in self.battles) == DOJO_BATTLE_PARTIES
            and all(
                turn.move_slot in (1, 2, 3, 4)
                for battle in self.battles
                for turn in battle.turns
            )
            and len(self.party_before) == 5
            and len(self.party_after) == 6
            and self.party_after[:-1] == self.party_before
            and self.party_after[-1] == HITMONLEE
            and self.party_levels[-1] == HITMONLEE_GIFT_LEVEL
            and self.got_hitmonlee
            and not self.got_hitmonchan
            and self.dojo_defeated
            and self.final_raw.map_id == MapId.SAFFRON_POKECENTER
            and (self.final_raw.player_x, self.final_raw.player_y) == (3, 3)
            and self.final_raw.battle_state == 0
            and party_core_intact(self.party_after)
            and self.party_hp == self.party_max_hp
            and all(hp > 0 for hp in self.party_hp)
            and all(status == 0 for status in self.party_status)
            and self.input_ready
            and self.controller_released
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "recruit_hitmonlee",
            "trainer_order": [list(battle.identity) for battle in self.battles],
            "trainer_parties": [
                [list(member) for member in battle.party] for battle in self.battles
            ],
            "party_before": list(self.party_before),
            "party_after": list(self.party_after),
            "hitmonlee_level": self.party_levels[-1] if self.party_levels else None,
            "events": {
                "all_trainers_defeated": self.events_after == (True,) * 5,
                "dojo_defeated": self.dojo_defeated,
                "got_hitmonlee": self.got_hitmonlee,
                "got_hitmonchan": self.got_hitmonchan,
            },
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "input_ready": self.input_ready,
            "controller_released": self.controller_released,
        }


def run_dojo_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    timing: SilphTiming = DEFAULT_SILPH_TIMING,
    progress: ProgressSink | None = None,
) -> DojoChapterReport:
    start_frames = emulator.frame_count
    actions = CountingExecutor(executor)
    records: list[DojoCheckpoint] = []
    battles: list[DojoBattleEvidence] = []
    initial = reader.read()
    _require(initial, MapId.SAFFRON_POKECENTER, (3, 3), "post-Silph boundary")
    party_before = tuple(initial.party_species_ids or ())
    events_before = tuple(_event(emulator, event) for event in DOJO_TRAINER_EVENTS)
    if (
        len(party_before) != 5
        or events_before != (False,) * len(DOJO_TRAINER_EVENTS)
        or _event(emulator, EventFlag.GOT_HITMONLEE)
        or _event(emulator, EventFlag.GOT_HITMONCHAN)
        or _event(emulator, EventFlag.DEFEATED_FIGHTING_DOJO)
    ):
        raise DojoChapterError("Fighting Dojo input boundary is not pristine.")
    _checkpoint(records, progress, emulator, initial, "dojo_ready", "Fighting Dojo plan ready")

    _move_verified_safe(actions, reader, CENTER_EXIT, timing, "Saffron Center exit")
    _navigate_safe(actions, reader, timing, DOJO_CITY_APPROACH, "Fighting Dojo")
    _move_verified_safe(actions, reader, ("up",), timing, "Fighting Dojo entry")
    _require(reader.read(), MapId.FIGHTING_DOJO, (4, 11), "Fighting Dojo entrance")
    _checkpoint(records, progress, emulator, reader.read(), "dojo_entered", "Entered Fighting Dojo")

    labels = ("Blackbelt 4", "Blackbelt 2", "Blackbelt 3", "Blackbelt 1", "Karate Master")
    for index, (label, identity, expected_party, event, plan, trigger_steps) in enumerate(
        zip(
            labels,
            DOJO_BATTLE_IDENTITIES,
            DOJO_BATTLE_PARTIES,
            DOJO_TRAINER_EVENTS,
            DOJO_BATTLE_PLANS,
            DOJO_TRIGGER_STEPS,
            strict=True,
        )
    ):
        battles.append(
            _fight_next(
                actions,
                reader,
                emulator,
                timing,
                label,
                identity,
                expected_party,
                event,
                plan,
                trigger_steps,
            )
        )
        if index < 4:
            _checkpoint(
                records,
                progress,
                emulator,
                reader.read(),
                f"dojo_trainer_{index + 1}",
                f"Defeated {label}",
            )
    _clear_dialogue(actions, reader, timing, "Karate Master reward offer")
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "karate_master",
        "Defeated Karate Master",
    )

    _require(reader.read(), MapId.FIGHTING_DOJO, (4, 3), "Karate Master terminal")
    _move_verified_safe(actions, reader, ("up",), timing, "Hitmonlee gift approach")
    _require(reader.read(), MapId.FIGHTING_DOJO, (4, 2), "Hitmonlee gift stance")
    actions.execute(MacroAction(MacroActionKind.INTERACT))
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=timing.dialogue_frames))
    for _ in range(96):
        party = tuple(reader.read().party_species_ids or ())
        if len(party) == 6 and _event(emulator, EventFlag.GOT_HITMONLEE):
            break
        actions.execute(MacroAction(MacroActionKind.CONFIRM))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=timing.dialogue_frames))
    else:
        raise DojoChapterError("Hitmonlee gift did not enter the party inside its dialogue bound.")
    _clear_dialogue(actions, reader, timing, "Hitmonlee gift dialogue")
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "hitmonlee_received",
        "Received Hitmonlee",
    )

    _move_verified_safe(actions, reader, ("down",) * 10, timing, "Fighting Dojo exit")
    _require(reader.read(), MapId.SAFFRON_CITY, (26, 4), "Fighting Dojo exterior")
    _navigate_safe(actions, reader, timing, (9, 30), "Saffron Center")
    _move_verified_safe(actions, reader, ("up",), timing, "Saffron Center entry")
    _require(reader.read(), MapId.SAFFRON_POKECENTER, (3, 7), "Saffron Center entry")
    _move(actions, reader, ("up",) * 4, timing)
    _heal(actions, timing)
    _prove_center_field_control(actions, reader, timing)
    final = reader.read()
    _require(final, MapId.SAFFRON_POKECENTER, (3, 3), "healed Dojo boundary")
    _checkpoint(records, progress, emulator, final, "dojo_terminal", "Healed six-member boundary")

    report = DojoChapterReport(
        records=tuple(records),
        final_raw=final,
        battles=tuple(battles),
        events_before=events_before,
        events_after=tuple(_event(emulator, event) for event in DOJO_TRAINER_EVENTS),
        party_before=party_before,
        party_after=tuple(final.party_species_ids or ()),
        party_levels=_party_levels(emulator),
        party_hp=_party_hp(emulator),
        party_max_hp=_party_max_hp(emulator),
        party_status=_party_status(emulator),
        got_hitmonlee=_event(emulator, EventFlag.GOT_HITMONLEE),
        got_hitmonchan=_event(emulator, EventFlag.GOT_HITMONCHAN),
        dojo_defeated=_event(emulator, EventFlag.DEFEATED_FIGHTING_DOJO),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        input_ready=reader.read_input_readiness().ready,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise DojoChapterError(f"Fighting Dojo failed its evidence contract: {report!r}.")
    return report


def _fight_next(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SilphTiming,
    label: str,
    identity: tuple[int, int, int],
    expected_party: tuple[tuple[int, int], ...],
    event: EventFlag,
    plan: RedBattlePlanId,
    trigger_steps: int,
) -> DojoBattleEvidence:
    _move(actions, reader, ("up",) * trigger_steps, timing)
    _await_trainer_battle_safe(actions, reader, timing, label)
    observed_identity = (
        emulator.read_u8(RamAddress.CURRENT_OPPONENT),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_CLASS),
        emulator.read_u8(RamAddress.ENGAGED_TRAINER_SET),
    )
    if observed_identity != identity:
        raise DojoChapterError(f"Unexpected {label} identity: {observed_identity!r}.")
    turns: list[DojoTurn] = []

    def choose_move(raw: RawGameState) -> int:
        for slot in (4, 2, 3, 1):
            pp = raw.first_party_pp or ()
            if (
                len(pp) >= slot
                and pp[slot - 1] & 0x3F
                and not (
                    raw.player_disabled_move_slot == slot
                    and (raw.player_disable_turns or 0) > 0
                )
            ):
                turns.append(DojoTurn(raw.enemy_species_id or 0, raw.enemy_level or 0, slot))
                return slot
        raise DojoChapterError(f"{label} has no legal damaging move with PP.")

    run_adaptive_trainer_battle(
        reader,
        actions,
        choose_move,
        expected_map=MapId.FIGHTING_DOJO,
        intent=BattleIntent(
            "defeat_fighting_dojo",
            battle_plan_id=plan,
            resource_policy=BattleResourcePolicy.NO_ADDITIONAL_CONSTRAINT,
        ),
        timing=DOJO_BATTLE_TIMING,
        label=label,
        unknown_cancel_interval=3,
    )
    _settle_battle_event(actions, reader, emulator, timing, event, label)
    turns_match = _turns_match_source_party(turns, expected_party)
    event_set = _event(emulator, event)
    party_hp = _party_hp(emulator)
    if not turns_match or not event_set or any(hp <= 0 for hp in party_hp):
        raise DojoChapterError(
            f"{label} did not settle a zero-faint event boundary: "
            f"turns_match={turns_match}, turns={turns!r}, expected={expected_party!r}, "
            f"event={event_set}, party_hp={party_hp!r}."
        )
    return DojoBattleEvidence(observed_identity, expected_party, tuple(turns), int(event))


def _encounter_party(turns: list[DojoTurn] | tuple[DojoTurn, ...]) -> tuple[tuple[int, int], ...]:
    party: list[tuple[int, int]] = []
    for turn in turns:
        member = (turn.enemy_species, turn.enemy_level)
        if not party or party[-1] != member:
            party.append(member)
    return tuple(party)


def _turns_match_source_party(
    turns: list[DojoTurn] | tuple[DojoTurn, ...],
    expected: tuple[tuple[int, int], ...],
) -> bool:
    """Match live turns while allowing an indistinguishable adjacent duplicate.

    Gen I exposes species and level but no stable enemy-party index. Two
    consecutive same-species, same-level opponents therefore look identical at
    the policy boundary. The verified trainer-set identity pins the exact source
    roster; live turns must cover its collapsed order and be numerous enough to
    have attacked every member at least once.
    """

    collapsed_expected: list[tuple[int, int]] = []
    for member in expected:
        if not collapsed_expected or collapsed_expected[-1] != member:
            collapsed_expected.append(member)
    return len(turns) >= len(expected) and _encounter_party(turns) == tuple(
        collapsed_expected
    )


def _party_levels(emulator: EmulatorState) -> tuple[int, ...]:
    count = emulator.read_u8(RamAddress.PARTY_COUNT)
    return tuple(
        emulator.read_u8(int(RamAddress.PARTY_MON_1_LEVEL) + 44 * index)
        for index in range(count)
    )


def _clear_dialogue(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SilphTiming,
    label: str,
) -> None:
    for _ in range(timing.max_script_pulses * 4):
        raw = reader.read()
        if raw.battle_state == 0 and reader.read_input_readiness().ready:
            return
        actions.execute(MacroAction(MacroActionKind.CONFIRM))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=timing.dialogue_frames))
    raise DojoChapterError(f"{label} did not restore field input inside its bound.")


def _settle_battle_event(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: SilphTiming,
    event: EventFlag,
    label: str,
) -> None:
    """Clear post-battle text only after the trainer event is durably set."""

    for _ in range(timing.max_script_pulses * 4):
        raw = reader.read()
        if (
            raw.battle_state == 0
            and _event(emulator, event)
            and reader.read_input_readiness().ready
        ):
            return
        actions.execute(MacroAction(MacroActionKind.CONFIRM))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=timing.dialogue_frames))
    raise DojoChapterError(f"{label} event or field input did not settle inside its bound.")


def _prove_center_field_control(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SilphTiming,
) -> None:
    """Advance lingering heal text until a real down-and-up probe succeeds."""

    for _ in range(timing.max_script_pulses * 4):
        state = reader.read()
        coordinate = (state.player_x, state.player_y)
        if state.map_id != MapId.SAFFRON_POKECENTER or state.battle_state != 0:
            raise DojoChapterError("Six-member healing left the Saffron Center boundary.")
        if coordinate == (3, 4):
            _move_verified_safe(
                actions,
                reader,
                ("up",),
                timing,
                "six-member field-control return",
            )
            return
        if coordinate != (3, 3):
            raise DojoChapterError(
                f"Six-member field-control probe reached unexpected {coordinate!r}."
            )
        actions.execute(MacroAction(MacroActionKind.MOVE, "down"))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=timing.movement_frames))
        if (reader.read().player_x, reader.read().player_y) == (3, 4):
            continue
        actions.execute(MacroAction(MacroActionKind.CONFIRM))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=timing.dialogue_frames))
    raise DojoChapterError("Six-member healing never restored physical field control.")


def _await_trainer_battle_safe(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SilphTiming,
    label: str,
) -> None:
    try:
        _await_trainer_battle(actions, reader, timing)
    except SilphChapterError as error:
        raise DojoChapterError(f"{label} battle did not start.") from error


def _navigate_safe(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    timing: SilphTiming,
    target: tuple[int, int],
    label: str,
) -> None:
    try:
        _navigate_saffron_coordinate(actions, reader, timing, target, label)
    except SilphChapterError as error:
        raise DojoChapterError(str(error)) from error


def _move_verified_safe(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    directions: tuple[str, ...],
    timing: SilphTiming,
    label: str,
) -> None:
    try:
        _move_verified(actions, reader, directions, timing, label)
    except SilphChapterError as error:
        raise DojoChapterError(str(error)) from error


def _require(
    raw: RawGameState,
    map_id: int,
    coordinate: tuple[int, int],
    label: str,
) -> None:
    if raw.map_id != map_id or (raw.player_x, raw.player_y) != coordinate:
        raise DojoChapterError(
            f"{label} expected map {int(map_id):#04x} at {coordinate}, got "
            f"{raw.map_id!r} at {(raw.player_x, raw.player_y)!r}."
        )


def _checkpoint(
    records: list[DojoCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(DojoCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            DojoProgress(
                checkpoint_id,
                label,
                len(records),
                DOJO_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )
