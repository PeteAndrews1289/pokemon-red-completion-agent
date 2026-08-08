"""Qualified Champion and Hall of Fame chapter for Pokémon Red."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, overload

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.agatha import AGATHA_X_SPECIAL_USE
from pokemon_red_completion.battle_actions import (
    BattleAction,
    BattleBoostStat,
    BattleControlRequest,
    control_request_matches,
    recovery_request_matches,
)
from pokemon_red_completion.battle_plan import RedBattlePlanId
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattleRecoveryCapability,
    BattleResourcePolicy,
    BattleRuntimeError,
    BattleRuntimeTiming,
    note_observed_trainer_battle_exit,
    run_adaptive_trainer_battle,
)
from pokemon_red_completion.celadon import (
    _bag,
    _party_hp,
    _party_levels,
    _party_status,
)
from pokemon_red_completion.executor import ChapterExecutor, CountingExecutor
from pokemon_red_completion.lance import LANCE_X_SPECIAL_USE
from pokemon_red_completion.lavender import (
    DEFAULT_LAVENDER_TIMING,
    _select_bag_item,
)
from pokemon_red_completion.lorelei import LoreleiChapterError, _battle_x_accuracy
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.participation import summarize_party_participation
from pokemon_red_completion.silph import (
    DEFAULT_SILPH_TIMING,
    SilphChapterError,
    _battle_healing_item,
)
from pokemon_red_completion.team_training import COMPLETION_LEVEL_PARITY
from pokemon_red_completion.tower import party_core_intact
from pokemon_red_completion.victory_road import (
    INDIGO_X_SPECIAL_RESERVE,
    _event,
    _pulse,
    _select_battle_main_command,
)

CHAMPION_CHECKPOINT_COUNT = 3
CHAMPION_BATTLE_CHECKPOINT_COUNT = 3
HALL_OF_FAME_CHECKPOINT_COUNT = 1
# Removed local level parity contract, using COMPLETION_LEVEL_PARITY instead
CHAMPION_RNG_DELAY_FRAMES = 150
CHAMPION_SAFE_HP = 90
CHAMPION_RHYDON_SAFE_HP = 50
CHAMPION_GYARADOS_FINISH_SAFE_HP = 50
CHAMPION_ARCANINE_FINISH_SAFE_HP = 50
CHAMPION_FULL_RESTORE_INPUT_RESERVE = 2
CHAMPION_FORCED_SWITCH_LIMIT = 5
CHAMPION_PARTY = (
    (0x97, 61),
    (0x95, 59),
    (0x01, 61),
    (0x16, 61),
    (0x14, 63),
    (0x9A, 65),
)


class EmulatorState(Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def read_u8(self, address: int) -> int: ...


class ChampionChapterError(RuntimeError):
    """Raised when the Champion completion contract fails."""


@dataclass(frozen=True, slots=True)
class ChampionProgress:
    checkpoint_id: str
    label: str
    completed: int
    total: int
    frames_executed: int


ProgressSink = Callable[[ChampionProgress], None]


@dataclass(frozen=True, slots=True)
class ChampionCheckpoint:
    checkpoint_id: str
    label: str
    raw: RawGameState


@dataclass(frozen=True, slots=True)
class ChampionTurn:
    species: int
    level: int
    enemy_hp: int
    lead_hp: int
    lead_status: int
    pp: tuple[int, int, int, int]
    move_slot: int
    party_position: int
    active_party_index: int | None


@dataclass(frozen=True, slots=True)
class ChampionChapterReport:
    records: tuple[ChampionCheckpoint, ...]
    final_raw: RawGameState
    turns: tuple[ChampionTurn, ...]
    party: tuple[tuple[int, int], ...]
    hyper_potions_used: int
    full_restores_used: int
    full_heals_used: int
    x_accuracy_used: int
    x_specials_used: int
    party_hp: tuple[int, ...]
    party_status: tuple[int, ...]
    frames_executed: int
    actions_executed: int
    controller_released: bool
    require_teacher_strategy_evidence: bool
    party_levels: tuple[int, ...] = ()

    @property
    def completion_evidence_passed(self) -> bool:
        """Verify the game objective independently of one prescribed strategy."""
        return (
            len(self.records) == CHAMPION_CHECKPOINT_COUNT
            and _event(self.final_raw, EventFlag.BEAT_CHAMPION_RIVAL)
            and self.final_raw.map_id == MapId.HALL_OF_FAME
            and party_core_intact(self.final_raw.party_species_ids)
            and self.controller_released
        )

    @property
    def teacher_strategy_evidence_passed(self) -> bool:
        """Verify the deterministic teacher's exact Champion demonstration."""
        return (
            self.party == CHAMPION_PARTY
            and _turns_valid(self.turns)
            and self.x_accuracy_used == 1
            and self.x_specials_used == 6
        )

    @property
    def passed(self) -> bool:
        return self.completion_evidence_passed and (
            not self.require_teacher_strategy_evidence or self.teacher_strategy_evidence_passed
        )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return tuple((item.checkpoint_id, item.label, item.raw) for item in self.records)

    def public_dict(self) -> dict[str, object]:
        participation = summarize_party_participation(
            (turn.active_party_index for turn in self.turns),
            party_size=len(self.party_levels),
        )

        return {
            "status": "ok" if self.passed else "failed",
            "objective": "enter_hall_of_fame",
            "verification": {
                "completion_evidence_passed": self.completion_evidence_passed,
                "teacher_strategy_required": self.require_teacher_strategy_evidence,
                "teacher_strategy_evidence_passed": (self.teacher_strategy_evidence_passed),
            },
            "party": [list(item) for item in self.party],
            "turns": [
                {
                    "species": item.species,
                    "level": item.level,
                    "enemy_hp": item.enemy_hp,
                    "lead_hp": item.lead_hp,
                    "lead_status": item.lead_status,
                    "pp": list(item.pp),
                    "move_slot": item.move_slot,
                    "party_position": item.party_position,
                    "active_party_index": item.active_party_index,
                }
                for item in self.turns
            ],
            "participation": participation.public_dict(),
            "resources": {
                "hyper_potions_used": self.hyper_potions_used,
                "full_restores_used": self.full_restores_used,
                "full_heals_used": self.full_heals_used,
                "x_accuracy_used": self.x_accuracy_used,
                "x_specials_used": self.x_specials_used,
            },
            "terminal": {
                "map": int(self.final_raw.map_id),
                "position": [self.final_raw.player_x, self.final_raw.player_y],
                "party_hp": list(self.party_hp),
                "party_status": list(self.party_status),
                "party_levels": list(self.party_levels),
                "team_balance": {
                    "size": len(self.party_levels),
                    "turns_per_member": list(participation.turns_per_member),
                    "opposition_levels": [level for _, level in self.party],
                    "opposition_maximum_level": (
                        max((level for _, level in self.party), default=None)
                    ),
                    "level_parity_tolerance": COMPLETION_LEVEL_PARITY.max_levels_behind,
                    "level_parity_required": (
                        COMPLETION_LEVEL_PARITY.required_level(
                            max(level for _, level in self.party)
                        )
                        if self.party
                        else None
                    ),
                    "members_behind_opposition": (
                        sum(
                            1
                            for level in self.party_levels
                            if level
                            < COMPLETION_LEVEL_PARITY.required_level(
                                max(level for _, level in self.party)
                            )
                        )
                        if self.party and self.party_levels
                        else None
                    ),
                    "minimum_level": min(self.party_levels) if self.party_levels else None,
                    "maximum_level": max(self.party_levels) if self.party_levels else None,
                    "level_spread": (
                        max(self.party_levels) - min(self.party_levels)
                        if self.party_levels
                        else None
                    ),
                },
                "turns_per_party_member": [
                    sum(1 for t in self.turns if t.active_party_index == i)
                    for i in range(len(self.party_levels))
                ],
                "moves": list(self.final_raw.first_party_moves or ()),
                "pp": list(self.final_raw.first_party_pp or ()),
                "champion_event": _event(
                    self.final_raw,
                    EventFlag.BEAT_CHAMPION_RIVAL,
                ),
                "hall_of_fame": self.final_raw.map_id == MapId.HALL_OF_FAME,
            },
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


@dataclass(frozen=True, slots=True)
class ChampionBattleReport:
    """Evidence for defeating the Champion before the Hall of Fame transition."""

    records: tuple[ChampionCheckpoint, ...]
    final_raw: RawGameState
    turns: tuple[ChampionTurn, ...]
    party: tuple[tuple[int, int], ...]
    hyper_potions_used: int
    full_restores_used: int
    full_heals_used: int
    x_accuracy_used: int
    x_specials_used: int
    party_hp: tuple[int, ...]
    party_levels: tuple[int, ...]
    party_status: tuple[int, ...]
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            len(self.records) == CHAMPION_BATTLE_CHECKPOINT_COUNT
            and _event(self.final_raw, EventFlag.BEAT_CHAMPION_RIVAL)
            and self.final_raw.map_id == MapId.CHAMPIONS_ROOM
            and self.party == CHAMPION_PARTY
            and _turns_valid(self.turns)
            and self.x_accuracy_used == 1
            and self.x_specials_used == 6
            and party_core_intact(self.final_raw.party_species_ids)
            and self.controller_released
        )

    def public_dict(self) -> dict[str, object]:
        participation = summarize_party_participation(
            (turn.active_party_index for turn in self.turns),
            party_size=len(self.party_levels),
        )
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "defeat_champion",
            "party": [list(item) for item in self.party],
            "participation": participation.public_dict(),
            "resources": {
                "hyper_potions_used": self.hyper_potions_used,
                "full_restores_used": self.full_restores_used,
                "full_heals_used": self.full_heals_used,
                "x_accuracy_used": self.x_accuracy_used,
                "x_specials_used": self.x_specials_used,
            },
            "terminal": {
                "map": int(self.final_raw.map_id),
                "position": [self.final_raw.player_x, self.final_raw.player_y],
                "party_hp": list(self.party_hp),
                "party_levels": list(self.party_levels),
                "party_status": list(self.party_status),
                "champion_event": _event(self.final_raw, EventFlag.BEAT_CHAMPION_RIVAL),
                "hall_of_fame": self.final_raw.map_id == MapId.HALL_OF_FAME,
            },
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


@dataclass(frozen=True, slots=True)
class HallOfFameReport:
    initial_raw: RawGameState
    final_raw: RawGameState
    frames_executed: int
    actions_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            self.initial_raw.map_id == MapId.CHAMPIONS_ROOM
            and _event(self.initial_raw, EventFlag.BEAT_CHAMPION_RIVAL)
            and self.final_raw.map_id == MapId.HALL_OF_FAME
            and _event(self.final_raw, EventFlag.BEAT_CHAMPION_RIVAL)
            and party_core_intact(self.final_raw.party_species_ids)
            and self.controller_released
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.passed else "failed",
            "objective": "enter_hall_of_fame",
            "champion_event": _event(self.final_raw, EventFlag.BEAT_CHAMPION_RIVAL),
            "terminal": {
                "map": int(self.final_raw.map_id),
                "position": [self.final_raw.player_x, self.final_raw.player_y],
            },
            "frames_executed": self.frames_executed,
            "actions_executed": self.actions_executed,
            "controller_released": self.controller_released,
        }


@overload
def run_champion_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    progress: ProgressSink | None = None,
    require_teacher_strategy_evidence: bool = True,
    stop_after_victory: Literal[True],
) -> ChampionBattleReport: ...


@overload
def run_champion_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    progress: ProgressSink | None = None,
    require_teacher_strategy_evidence: bool = True,
    stop_after_victory: Literal[False] = False,
) -> ChampionChapterReport: ...


def run_champion_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
    *,
    progress: ProgressSink | None = None,
    require_teacher_strategy_evidence: bool = True,
    stop_after_victory: bool = False,
) -> ChampionChapterReport | ChampionBattleReport:
    start_frames = emulator.frame_count
    actions = CountingExecutor(executor)
    records: list[ChampionCheckpoint] = []
    initial = reader.read()
    if (
        initial.map_id != MapId.CHAMPIONS_ROOM
        or (initial.player_x, initial.player_y) != (4, 3)
        or not party_core_intact(initial.party_species_ids)
        or not _event(initial, EventFlag.BEAT_LANCE)
        or _event(initial, EventFlag.BEAT_CHAMPION_RIVAL)
        or initial.first_party_moves != (0x05, 0x46, 0x3B, 0x39)
        or _bag(emulator).get(ItemId.X_ACCURACY, 0) != 1
        or _bag(emulator).get(ItemId.X_SPECIAL, 0)
        != INDIGO_X_SPECIAL_RESERVE - AGATHA_X_SPECIAL_USE - LANCE_X_SPECIAL_USE
        or _bag(emulator).get(ItemId.FULL_RESTORE, 0) < CHAMPION_FULL_RESTORE_INPUT_RESERVE
    ):
        raise ChampionChapterError(
            "Champion input boundary is not qualified: "
            f"map={initial.map_id!r}, position={(initial.player_x, initial.player_y)!r}, "
            f"party={initial.party_species_ids!r}, moves={initial.first_party_moves!r}, "
            f"beat_lance={_event(initial, EventFlag.BEAT_LANCE)!r}, "
            f"beat_champion={_event(initial, EventFlag.BEAT_CHAMPION_RIVAL)!r}, "
            f"party_hp={_party_hp(emulator)!r}, bag={_bag(emulator)!r}."
        )
    _checkpoint(
        records,
        progress,
        emulator,
        initial,
        "champion_ready",
        "Champion room ready",
    )
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=CHAMPION_RNG_DELAY_FRAMES))
    for _ in range(50):
        if reader.read().battle_state == 2:
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise ChampionChapterError("Champion battle did not start.")
    _checkpoint(
        records,
        progress,
        emulator,
        reader.read(),
        "champion_engaged",
        "Engaged Champion",
    )

    turns: list[ChampionTurn] = []
    boosts_used = 0

    class _HealBoundary(BattleControlRequest):
        default_action = BattleAction.recovery()

    class _BoostBoundary(BattleControlRequest):
        default_action = BattleAction.boost(BattleBoostStat.SPECIAL)

    class _AccuracyBoundary(BattleControlRequest):
        default_action = BattleAction.boost(BattleBoostStat.ACCURACY)

    def policy(raw: RawGameState) -> int:
        hp = raw.battler_hp or 0
        status = raw.battler_status or 0
        inventory = _bag(emulator)
        if accuracy_used == 0:
            raise _AccuracyBoundary
        if (
            raw.active_party_index in {None, 0}
            and (hp < _champion_recovery_threshold(raw) or status)
            and _champion_recovery_available(status, inventory)
            and len(turns) != last_recovery_turn
        ):
            raise _HealBoundary
        if boosts_used < 6:
            raise _BoostBoundary
        species = raw.enemy_species_id or 0
        pp = raw.battler_pp or (0, 0, 0, 0)
        slot = _champion_move_slot(raw)
        turns.append(
            ChampionTurn(
                species=species,
                level=raw.enemy_level or 0,
                enemy_hp=raw.enemy_hp or 0,
                lead_hp=hp,
                lead_status=status,
                pp=pp,
                move_slot=slot,
                party_position=emulator.read_u8(RamAddress.ENEMY_MON_PARTY_POS),
                active_party_index=raw.active_party_index,
            )
        )
        return slot

    hyper_before = _bag(emulator).get(ItemId.HYPER_POTION, 0)
    restore_before = _bag(emulator).get(ItemId.FULL_RESTORE, 0)
    heal_before = _bag(emulator).get(ItemId.FULL_HEAL, 0)
    accuracy_before = _bag(emulator).get(ItemId.X_ACCURACY, 0)
    x_special_before = _bag(emulator).get(ItemId.X_SPECIAL, 0)
    accuracy_used = 0
    last_recovery_turn = -1
    forced_switches = 0
    champion_intent = BattleIntent(
        "defeat_champion",
        battle_plan_id=RedBattlePlanId.LEAGUE_CHAMPION,
        resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
        recovery_capabilities=frozenset(
            {
                BattleRecoveryCapability.RESTORE_HP,
                BattleRecoveryCapability.CURE_ANY_STATUS,
            }
        ),
    )
    while True:
        raw = reader.read()
        if stop_after_victory and _champion_victory_observed(raw):
            break
        if _completed(raw):
            break
        if raw.battle_state != 2:
            _pulse(actions, MacroActionKind.CONFIRM)
            continue
        try:
            run_adaptive_trainer_battle(
                reader,
                actions,
                policy,
                expected_map=MapId.CHAMPIONS_ROOM,
                intent=champion_intent,
                timing=BattleRuntimeTiming(
                    max_runtime_pulses=3000,
                    max_post_attack_transition_pulses=30,
                ),
                label="Champion",
            )
        except BattleRuntimeError as error:
            if _completed(reader.read()):
                break
            current = reader.read()
            if (
                current.battle_state == 2
                and current.enemy_hp == 0
                and any(hp > 0 for hp in _party_hp(emulator))
            ):
                _settle_champion_battle_exit(reader, actions)
                note_observed_trainer_battle_exit(champion_intent)
                continue
            if (
                current.battle_state == 2
                and current.battler_hp == 0
                and forced_switches < CHAMPION_FORCED_SWITCH_LIMIT
            ):
                terminal = _settle_champion_forced_switch(
                    reader,
                    actions,
                    emulator,
                )
                forced_switches += 1
                if terminal:
                    break
                continue
            if control_request_matches(error.__cause__, _AccuracyBoundary.default_action):
                try:
                    _battle_x_accuracy(reader, actions, emulator)
                except LoreleiChapterError as accuracy_error:
                    raise ChampionChapterError(
                        "Champion X Accuracy setup failed."
                    ) from accuracy_error
                accuracy_used += 1
                continue
            if control_request_matches(error.__cause__, _BoostBoundary.default_action):
                _battle_x_special(reader, actions, emulator)
                boosts_used += 1
                continue
            if not recovery_request_matches(error.__cause__, _HealBoundary):
                current = reader.read()
                if current.enemy_hp == 0 and any(hp > 0 for hp in _party_hp(emulator)):
                    if current.battle_state == 2:
                        _settle_champion_battle_exit(reader, actions)
                    elif current.battle_state != 0:
                        raise ChampionChapterError(
                            "Champion final KO exposed an unsupported battle state."
                        ) from error
                    note_observed_trainer_battle_exit(champion_intent)
                    continue
                raise ChampionChapterError(
                    "Champion battle runtime failed: "
                    f"party_hp={_party_hp(emulator)!r}, "
                    f"enemy={(current.enemy_species_id, current.enemy_hp, current.enemy_level)!r}, "
                    f"lead_status={current.first_party_status!r}, "
                    f"pp={current.first_party_pp!r}, "
                    f"bag={_bag(emulator)!r}, turns={turns!r}."
                ) from error
            current = reader.read()
            inventory = _bag(emulator)
            item = _select_recovery_item(
                current.first_party_hp or 0,
                current.first_party_status or 0,
                inventory,
            )
            if item is None:
                raise ChampionChapterError(
                    "Champion exhausted the recovery reserve: "
                    f"party_hp={_party_hp(emulator)!r}, "
                    f"enemy={(current.enemy_species_id, current.enemy_hp, current.enemy_level)!r}, "
                    f"lead_status={current.first_party_status!r}, "
                    f"pp={current.first_party_pp!r}, "
                    f"boosts_used={boosts_used!r}, "
                    f"bag={inventory!r}, "
                    f"turns={turns!r}."
                ) from error
            try:
                terminal_exit = _battle_healing_item(
                    reader,
                    actions,
                    emulator,
                    DEFAULT_SILPH_TIMING,
                    item,
                )
            except SilphChapterError as healing_error:
                raise ChampionChapterError("Champion recovery failed.") from healing_error
            if terminal_exit:
                note_observed_trainer_battle_exit(champion_intent)
            last_recovery_turn = len(turns)

    final = reader.read()
    if stop_after_victory:
        _checkpoint(
            records,
            progress,
            emulator,
            final,
            "champion_defeated",
            "Champion defeated before Hall of Fame",
        )
        battle_report = ChampionBattleReport(
            records=tuple(records),
            final_raw=final,
            turns=tuple(turns),
            party=_encounter_party(turns),
            hyper_potions_used=hyper_before - _bag(emulator).get(ItemId.HYPER_POTION, 0),
            full_restores_used=restore_before - _bag(emulator).get(ItemId.FULL_RESTORE, 0),
            full_heals_used=heal_before - _bag(emulator).get(ItemId.FULL_HEAL, 0),
            x_accuracy_used=accuracy_before - _bag(emulator).get(ItemId.X_ACCURACY, 0),
            x_specials_used=x_special_before - _bag(emulator).get(ItemId.X_SPECIAL, 0),
            party_hp=_party_hp(emulator),
            party_levels=_party_levels(emulator),
            party_status=_party_status(emulator),
            frames_executed=emulator.frame_count - start_frames,
            actions_executed=actions.actions_executed,
            controller_released=not emulator.pressed_buttons,
        )
        if not battle_report.passed:
            raise ChampionChapterError(
                f"Champion battle boundary evidence failed: {battle_report!r}."
            )
        return battle_report
    _checkpoint(
        records,
        progress,
        emulator,
        final,
        "hall_of_fame",
        "Champion defeated and Hall of Fame entered",
    )
    report = ChampionChapterReport(
        records=tuple(records),
        final_raw=final,
        turns=tuple(turns),
        party=_encounter_party(turns),
        hyper_potions_used=hyper_before - _bag(emulator).get(ItemId.HYPER_POTION, 0),
        full_restores_used=restore_before - _bag(emulator).get(ItemId.FULL_RESTORE, 0),
        full_heals_used=heal_before - _bag(emulator).get(ItemId.FULL_HEAL, 0),
        x_accuracy_used=accuracy_before - _bag(emulator).get(ItemId.X_ACCURACY, 0),
        x_specials_used=x_special_before - _bag(emulator).get(ItemId.X_SPECIAL, 0),
        party_hp=_party_hp(emulator),
        party_levels=_party_levels(emulator),
        party_status=_party_status(emulator),
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
        require_teacher_strategy_evidence=require_teacher_strategy_evidence,
    )
    if not report.passed:
        raise ChampionChapterError(f"Champion terminal evidence failed: {report!r}.")
    return report


def run_hall_of_fame_chapter(
    emulator: EmulatorState,
    reader: PokemonRedStateReader,
    executor: ChapterExecutor,
) -> HallOfFameReport:
    """Advance only the post-Champion ceremony and verify the Hall of Fame map."""

    start_frames = emulator.frame_count
    actions = CountingExecutor(executor)
    initial = reader.read()
    if (
        initial.map_id != MapId.CHAMPIONS_ROOM
        or not _event(initial, EventFlag.BEAT_CHAMPION_RIVAL)
        or initial.battle_state != 0
    ):
        raise ChampionChapterError("Hall of Fame input boundary is not qualified.")
    for _ in range(256):
        raw = reader.read()
        if raw.map_id == MapId.HALL_OF_FAME:
            break
        _pulse(actions, MacroActionKind.CONFIRM)
    else:
        raise ChampionChapterError("Champion ceremony did not reach the Hall of Fame.")
    final = reader.read()
    report = HallOfFameReport(
        initial_raw=initial,
        final_raw=final,
        frames_executed=emulator.frame_count - start_frames,
        actions_executed=actions.actions_executed,
        controller_released=not emulator.pressed_buttons,
    )
    if not report.passed:
        raise ChampionChapterError(f"Hall of Fame evidence failed: {report!r}.")
    return report


def _champion_victory_observed(raw: RawGameState) -> bool:
    return (
        raw.map_id == MapId.CHAMPIONS_ROOM
        and raw.battle_state == 0
        and _event(raw, EventFlag.BEAT_CHAMPION_RIVAL)
    )


def _battle_x_special(
    reader: PokemonRedStateReader,
    actions: CountingExecutor,
    emulator: EmulatorState,
) -> None:
    raw = reader.read()
    if (
        raw.battle_state != 2
        or reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN
    ):
        raise ChampionChapterError("X Special gate requires the trainer MAIN menu.")
    initial = _bag(emulator).get(ItemId.X_SPECIAL, 0)
    if initial == 0:
        raise ChampionChapterError("X Special reserve was exhausted.")
    for attempt in range(2):
        before = _bag(emulator).get(ItemId.X_SPECIAL, 0)
        _select_battle_main_command(actions, reader, 1)
        _pulse(actions, MacroActionKind.CONFIRM)
        _select_bag_item(
            actions,
            emulator,
            ItemId.X_SPECIAL,
            DEFAULT_LAVENDER_TIMING,
        )
        _pulse(actions, MacroActionKind.CONFIRM)
        consumed = False
        for _ in range(30):
            current = reader.read()
            after = _bag(emulator).get(ItemId.X_SPECIAL, 0)
            if after == before - 1:
                consumed = True
            elif after != before:
                raise ChampionChapterError(
                    f"X Special changed by an invalid quantity: before={before}, after={after}."
                )
            at_main = (
                current.battle_state == 2
                and reader.read_battle_menu_state(current).phase is BattleMenuPhase.MAIN
            )
            if consumed and at_main:
                if initial - after != 1:
                    raise ChampionChapterError(
                        f"X Special cumulative use was invalid: initial={initial}, after={after}."
                    )
                return
            if at_main and not consumed:
                break
            # Use the safe text-advance button: B cannot reopen ITEM if the
            # battle menu returns during the input pulse.
            _pulse(actions, MacroActionKind.CANCEL)
        else:
            raise ChampionChapterError(
                "X Special use did not settle: "
                f"before={before}, after={_bag(emulator).get(ItemId.X_SPECIAL, 0)}."
            )
        if attempt == 0:
            continue
    raise ChampionChapterError(
        "X Special was not consumed after two bounded selections: "
        f"initial={initial}, after={_bag(emulator).get(ItemId.X_SPECIAL, 0)}."
    )


def _completed(raw: RawGameState) -> bool:
    return raw.map_id == MapId.HALL_OF_FAME and _event(raw, EventFlag.BEAT_CHAMPION_RIVAL)


def _select_recovery_item(
    hp: int,
    status: int,
    inventory: Mapping[ItemId, int],
) -> ItemId | None:
    if status and hp >= CHAMPION_SAFE_HP and inventory.get(ItemId.FULL_HEAL, 0):
        return ItemId.FULL_HEAL
    if inventory.get(ItemId.FULL_RESTORE, 0):
        return ItemId.FULL_RESTORE
    return None


def _champion_move_slot(raw: RawGameState) -> int:
    """Use matchup coverage while reserving Blizzard for the final Venusaur."""
    pp = raw.battler_pp or (0, 0, 0, 0)
    if raw.active_party_index not in {None, 0}:
        for slot, remaining in enumerate(pp, start=1):
            if remaining > 0 and not _champion_move_disabled(raw, slot):
                return slot
        raise ChampionChapterError("Champion reserve has no usable move PP.")
    species = raw.enemy_species_id or 0
    priorities = {
        # Six X Specials plus X Accuracy make Blizzard a reliable knockout
        # against the dangerous fast opener. Four Ice PP remain for Venusaur
        # and contingencies; preserving all five can instead expose a second
        # Pidgeot reply after accurate Strength leaves it alive.
        0x97: (3, 2, 1, 4),
        0x95: (2, 1, 4, 3),  # Alakazam: exploit its lower physical Defense.
        0x01: (4, 3, 2, 1),  # Rhydon: four-times-effective Surf.
        0x16: (2, 1, 3, 4),  # Gyarados: preserve the irreplaceable Ice PP.
        0x14: (4, 2, 3, 1),  # Arcanine: super-effective Surf.
        0x9A: (3, 2, 1, 4),  # Venusaur: reserve all possible Blizzard PP.
    }.get(species, (2, 1, 4, 3))
    for slot in priorities:
        if pp[slot - 1] > 0 and not _champion_move_disabled(raw, slot):
            return slot
    raise ChampionChapterError("Champion has no usable move PP.")


def _champion_move_disabled(raw: RawGameState, slot: int) -> bool:
    return raw.player_disabled_move_slot == slot and (raw.player_disable_turns or 0) > 0


def _champion_forced_switch_target(
    party_hp: tuple[int, ...],
    active_party_index: int | None,
) -> int | None:
    candidates = [
        index for index, hp in enumerate(party_hp) if hp > 0 and index != active_party_index
    ]
    return max(candidates, key=lambda index: party_hp[index], default=None)


def _settle_champion_forced_switch(
    reader: PokemonRedStateReader,
    actions: CountingExecutor,
    emulator: EmulatorState,
) -> bool:
    """Continue the final battle with the healthiest developed teammate."""

    target = _champion_forced_switch_target(
        _party_hp(emulator),
        reader.read().active_party_index,
    )
    if target is None:
        raise ChampionChapterError("Champion KO left no living teammate.")
    for pulse_index in range(64):
        raw = reader.read()
        if raw.battle_state == 0:
            return True
        if (
            raw.battle_state == 2
            and raw.active_party_index == target
            and (raw.battler_hp or 0) > 0
            and reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN
        ):
            return False
        if raw.battle_state != 2:
            raise ChampionChapterError("Champion forced switch left the battle.")
        cursor = emulator.read_u8(RamAddress.CURRENT_MENU_ITEM)
        _pulse(
            actions,
            MacroActionKind.CONFIRM if cursor == target else MacroActionKind.MOVE,
            None if cursor == target else ("down" if cursor < target else "up"),
            DEFAULT_SILPH_TIMING.menu_frames,
        )
        if pulse_index % 5 == 4:
            _pulse(
                actions,
                MacroActionKind.CONFIRM,
                frames=DEFAULT_SILPH_TIMING.menu_frames,
            )
    raise ChampionChapterError("Champion forced switch exceeded its bounded menu pulses.")


def _settle_champion_battle_exit(
    reader: PokemonRedStateReader,
    actions: CountingExecutor,
) -> None:
    """Advance a reserve's verified final KO to the post-battle dialogue."""

    for _ in range(128):
        raw = reader.read()
        if raw.battle_state == 0 or _completed(raw):
            return
        if raw.battle_state != 2 or raw.enemy_hp != 0:
            raise ChampionChapterError("Champion final KO exposed an invalid transition.")
        _pulse(
            actions,
            MacroActionKind.CONFIRM,
            frames=DEFAULT_SILPH_TIMING.menu_frames,
        )
    raise ChampionChapterError("Champion final KO did not reach post-battle dialogue.")


def _champion_recovery_threshold(raw: RawGameState) -> int:
    """Reserve recovery against Rhydon's low-pressure, Rest-heavy matchup."""
    if raw.enemy_species_id == 0x9A:
        # The final Venusaur's high-critical-rate Razor Leaf can erase more
        # than the generic safety margin in one turn, so use any remaining
        # recovery before committing the reserved Ice coverage.
        return raw.first_party_max_hp or CHAMPION_SAFE_HP
    if raw.enemy_species_id == 0x01:
        return CHAMPION_RHYDON_SAFE_HP
    if raw.enemy_species_id == 0x16 and (raw.enemy_hp or 0) <= 50:
        return CHAMPION_GYARADOS_FINISH_SAFE_HP
    if raw.enemy_species_id == 0x16:
        return raw.first_party_max_hp or CHAMPION_SAFE_HP
    if raw.enemy_species_id == 0x14 and (raw.enemy_hp or 0) <= 30:
        return CHAMPION_ARCANINE_FINISH_SAFE_HP
    return CHAMPION_SAFE_HP


def _champion_recovery_available(
    status: int,
    inventory: Mapping[ItemId, int],
) -> bool:
    return bool(
        inventory.get(ItemId.FULL_RESTORE, 0) or (status and inventory.get(ItemId.FULL_HEAL, 0))
    )


def _encounter_party(
    turns: Iterable[ChampionTurn],
) -> tuple[tuple[int, int], ...]:
    result: list[tuple[int, int]] = []
    previous_position: int | None = None
    for turn in turns:
        if turn.party_position != previous_position:
            result.append((turn.species, turn.level))
            previous_position = turn.party_position
    return tuple(result)


def _turns_valid(turns: Iterable[ChampionTurn]) -> bool:
    items = tuple(turns)
    return bool(items) and all(
        item.species in {species for species, _ in CHAMPION_PARTY}
        and item.move_slot in {1, 2, 3, 4}
        and item.lead_hp > 0
        and item.lead_status == 0
        for item in items
    )


def _checkpoint(
    records: list[ChampionCheckpoint],
    progress: ProgressSink | None,
    emulator: EmulatorState,
    raw: RawGameState,
    checkpoint_id: str,
    label: str,
) -> None:
    records.append(ChampionCheckpoint(checkpoint_id, label, raw))
    if progress is not None:
        progress(
            ChampionProgress(
                checkpoint_id,
                label,
                len(records),
                CHAMPION_CHECKPOINT_COUNT,
                emulator.frame_count,
            )
        )
