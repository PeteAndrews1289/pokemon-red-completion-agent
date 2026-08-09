from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_plan import RED_BATTLE_PLAN_IDS
from pokemon_red_completion.battle_policy import choose_cerulean_rival_move_slot
from pokemon_red_completion.battle_runtime import (
    BattleIntent,
    BattlePolicyObservation,
    BattleRecoveryCapability,
    BattleResourcePolicy,
    BattleRuntimeError,
    BattleRuntimeTimeoutError,
    BattleRuntimeTiming,
    BattleSwitchCapability,
    RequiredMovePolicy,
    _confirm_attack_with_pp_gate,
    _require_present_state,
    battle_policy_override_active,
    bind_battle_decision_observer,
    bind_battle_policy_override,
    bind_battle_schedule_observer,
    note_observed_battle_exit,
    recovery_action_due,
    run_adaptive_trainer_battle,
    run_adaptive_wild_battle,
)
from pokemon_red_completion.battle_schedule import (
    BattleScheduleError,
    BattleStartScheduleController,
    bind_battle_start_schedule,
)
from pokemon_red_completion.collection_protocol import BattleStartOffset
from pokemon_red_completion.observation import (
    BULBASAUR_SPECIES_ID,
    PIDGEOTTO_SPECIES_ID,
    TACKLE_MOVE_ID,
    WATER_GUN_MOVE_ID,
    BattleMenuPhase,
    BattleMenuState,
    InputReadiness,
    MapId,
    RawGameState,
)
from pokemon_red_completion.red_battle_catalog import pokemon_red_move_ref
from pokemon_red_completion.red_trajectory import (
    PokemonRedBattleDecisionObserver,
    PokemonRedBattleScheduleObserver,
    PokemonRedObservationEncoder,
)
from pokemon_red_completion.trajectory import (
    InMemoryTrajectorySink,
    RecordingExecutor,
    canonical_json,
)

READY = InputReadiness(0, 0, 0, 0, 0, 0)
NOT_READY = InputReadiness(1, 0, 0, 0, 0, 0)
TAIL_WHIP_MOVE_ID = 0x27
BUBBLE_MOVE_ID = 0x91
MEGA_PUNCH_MOVE_ID = 0x05
DIG_MOVE_ID = 0x5B
TEST_BATTLE_PLAN_ID = "battle-001-test"
SCHEDULED_BATTLE_PLAN_ID = RED_BATTLE_PLAN_IDS[0]


def test_battle_policy_override_scope_is_observable_and_resets() -> None:
    class Policy:
        def choose_move(
            self,
            observation: BattlePolicyObservation,
            fallback: Callable[[], int],
        ) -> int:
            return fallback()

    assert not battle_policy_override_active()
    with bind_battle_policy_override(Policy()):
        assert battle_policy_override_active()
    assert not battle_policy_override_active()


def _raw(
    *,
    map_id: int = MapId.CERULEAN_CITY,
    battle_state: int | None = 2,
    party_count: int | None = 1,
    hp: int | None = 26,
    enemy_species_id: int | None = PIDGEOTTO_SPECIES_ID,
    enemy_hp: int | None = 20,
    moves: tuple[int, ...] | None = (
        TACKLE_MOVE_ID,
        TAIL_WHIP_MOVE_ID,
        MEGA_PUNCH_MOVE_ID,
        WATER_GUN_MOVE_ID,
    ),
    pp: tuple[int, ...] | None = (35, 30, 30, 11),
    player_attack_stage: int | None = 7,
    player_accuracy_stage: int | None = 7,
    enemy_defense_stage: int | None = 6,
) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=map_id,
        player_x=21,
        player_y=6,
        party_count=party_count,
        battle_state=battle_state,
        party_species_ids=(0xB3,) if party_count else (),
        first_party_hp=hp,
        first_party_max_hp=49,
        first_party_status=0,
        first_party_moves=moves,
        first_party_pp=pp,
        enemy_species_id=enemy_species_id,
        enemy_hp=enemy_hp,
        player_attack_stage=player_attack_stage,
        player_accuracy_stage=player_accuracy_stage,
        enemy_defense_stage=enemy_defense_stage,
    )


def _scheduled_offsets(
    *,
    first_frames: int,
) -> tuple[BattleStartOffset, ...]:
    return tuple(
        BattleStartOffset(
            battle_plan_id,
            first_frames if index == 0 else 0,
        )
        for index, battle_plan_id in enumerate(RED_BATTLE_PLAN_IDS)
    )


class FakeRuntime:
    def __init__(
        self,
        *,
        raw: RawGameState | None = None,
        menu: BattleMenuState | None = None,
        controls: InputReadiness = NOT_READY,
        on_action: Callable[[MacroAction], None] | None = None,
    ) -> None:
        self.raw = raw or _raw()
        self.menu = menu or BattleMenuState(
            BattleMenuPhase.MAIN,
            selected_main_command=0,
        )
        self.controls = controls
        self.on_action = on_action
        self.actions: list[MacroAction] = []

    def read(self) -> RawGameState:
        return self.raw

    def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
        assert raw is self.raw
        return self.menu

    def read_input_readiness(self) -> InputReadiness:
        return self.controls

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)
        if self.on_action is not None:
            self.on_action(action)


class ImmediateBattleExitRuntime(FakeRuntime):
    """Expose one active initial read followed by an exit before any policy turn."""

    def __init__(self) -> None:
        super().__init__(controls=READY)
        self.reads = 0

    def read(self) -> RawGameState:
        self.reads += 1
        if self.reads == 2:
            self.raw = replace(self.raw, battle_state=0)
        return self.raw


def test_wild_runtime_accepts_truthful_wild_state_and_restores_trainer_default() -> None:
    wild = ImmediateBattleExitRuntime()
    wild.raw = replace(wild.raw, battle_state=1)
    final = run_adaptive_wild_battle(
        wild,
        wild,
        lambda _raw: 4,
        expected_map=MapId.CERULEAN_CITY,
    )
    assert final.battle_state == 0

    trainer = ImmediateBattleExitRuntime()
    assert (
        run_adaptive_trainer_battle(
            trainer,
            trainer,
            lambda _raw: 4,
            expected_map=MapId.CERULEAN_CITY,
        ).battle_state
        == 0
    )


class RecordingDecisionObserver:
    def __init__(self, runtime: FakeRuntime) -> None:
        self.runtime = runtime
        self.starts: list[BattleIntent | None] = []
        self.finishes = 0
        self.failures = 0
        self.entries: list[tuple[int, int]] = []
        self.exits: list[int] = []

    def note_instrumentation_failure(self) -> None:
        self.failures += 1

    def battle_started(self, *, intent: BattleIntent | None) -> None:
        self.starts.append(intent)

    def battle_finished(self) -> None:
        self.finishes += 1

    @contextmanager
    def decision_scope(
        self,
        *,
        policy_state: RawGameState,
        policy_menu: BattleMenuState,
        selected_slot: int,
        intent: BattleIntent | None,
    ) -> Iterator[None]:
        assert policy_state is self.runtime.raw
        assert policy_menu is self.runtime.menu
        assert intent is not None and intent.objective_id == "help_bill"
        self.entries.append((selected_slot, len(self.runtime.actions)))
        try:
            yield
        finally:
            self.exits.append(len(self.runtime.actions))


class FailingLifecycleObserver:
    def __init__(self, failure_phase: str) -> None:
        self.failure_phase = failure_phase
        self.failures = 0

    def note_instrumentation_failure(self) -> None:
        self.failures += 1

    def battle_started(self, *, intent: BattleIntent | None) -> None:
        del intent

    def battle_finished(self) -> None:
        return

    def decision_scope(self, **kwargs: object):
        del kwargs
        failure_phase = self.failure_phase

        class Manager:
            def __enter__(self) -> None:
                if failure_phase == "enter":
                    raise RuntimeError("observer enter failed")

            def __exit__(self, *args: object) -> bool:
                del args
                if failure_phase == "exit":
                    raise RuntimeError("observer exit failed")
                return False

        return Manager()


def test_runtime_rejects_selected_slot_when_required_move_id_differs() -> None:
    runtime = FakeRuntime()

    def expose_move_menu(action: MacroAction) -> None:
        if action.kind is MacroActionKind.CONFIRM:
            runtime.menu = BattleMenuState(
                BattleMenuPhase.MOVE,
                selected_move_slot=1,
            )

    runtime.on_action = expose_move_menu

    with pytest.raises(BattleRuntimeError, match="selected move id"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
            required_move_id=DIG_MOVE_ID,
        )

    assert runtime.raw.first_party_pp == (35, 30, 30, 11)


@pytest.mark.parametrize(
    ("intent", "required_move_id"),
    (
        (
            BattleIntent(
                "defeat_rival",
                TEST_BATTLE_PLAN_ID,
                required_move_policy=RequiredMovePolicy.EXACT_REQUIRED,
                required_move_ref=pokemon_red_move_ref(TACKLE_MOVE_ID),
            ),
            None,
        ),
        (BattleIntent("defeat_rival", TEST_BATTLE_PLAN_ID), TACKLE_MOVE_ID),
    ),
)
def test_explicit_move_policy_must_agree_with_required_move_id(
    intent: BattleIntent,
    required_move_id: int | None,
) -> None:
    runtime = FakeRuntime()

    with pytest.raises(ValueError, match="required_move_policy must agree"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
            intent=intent,
            required_move_id=required_move_id,
        )

    assert runtime.actions == []


@pytest.mark.parametrize("battle_plan_id", ["", "Unsafe", "../battle", "battle id"])
def test_battle_intent_requires_a_safe_public_plan_id(battle_plan_id: str) -> None:
    with pytest.raises(ValueError, match="safe public battle identity"):
        BattleIntent("defeat_rival", battle_plan_id)


def test_battle_intent_accepts_declared_bounded_recovery_capabilities() -> None:
    intent = BattleIntent(
        "defeat_rival",
        TEST_BATTLE_PLAN_ID,
        resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
        recovery_capabilities=frozenset(
            {
                BattleRecoveryCapability.RESTORE_HP,
                BattleRecoveryCapability.CURE_PARALYSIS,
            }
        ),
    )

    assert intent.recovery_capabilities == frozenset(
        {
            BattleRecoveryCapability.RESTORE_HP,
            BattleRecoveryCapability.CURE_PARALYSIS,
        }
    )


def test_battle_intent_rejects_recovery_capabilities_without_bounded_policy() -> None:
    with pytest.raises(ValueError, match="bounded recovery"):
        BattleIntent(
            "defeat_rival",
            TEST_BATTLE_PLAN_ID,
            recovery_capabilities=frozenset({BattleRecoveryCapability.RESTORE_HP}),
        )


def test_battle_intent_rejects_untyped_recovery_capabilities() -> None:
    with pytest.raises(TypeError, match="must contain recovery capabilities"):
        BattleIntent(
            "defeat_rival",
            TEST_BATTLE_PLAN_ID,
            resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
            recovery_capabilities=frozenset({"restore_hp"}),  # type: ignore[arg-type]
        )


def test_battle_intent_accepts_typed_switch_capabilities() -> None:
    intent = BattleIntent(
        "defeat_rival",
        TEST_BATTLE_PLAN_ID,
        switch_capabilities=frozenset({BattleSwitchCapability.RESET_STAT_STAGES}),
    )

    assert intent.switch_capabilities == frozenset(
        {BattleSwitchCapability.RESET_STAT_STAGES}
    )


def test_battle_intent_rejects_untyped_switch_capabilities() -> None:
    with pytest.raises(TypeError, match="must contain switch capabilities"):
        BattleIntent(
            "defeat_rival",
            TEST_BATTLE_PLAN_ID,
            switch_capabilities=frozenset({"direct"}),  # type: ignore[arg-type]
        )


class AdaptiveRivalSimulation(FakeRuntime):
    """Two-opponent battle with bounded dialogue and post-battle cleanup."""

    def __init__(
        self,
        *,
        first_main_command: int = 0,
        between_opponent_dialogues: int = 3,
        completion_dialogues: int = 2,
    ) -> None:
        super().__init__(
            menu=BattleMenuState(
                BattleMenuPhase.MAIN,
                selected_main_command=first_main_command,
            )
        )
        self.between_opponent_dialogues = between_opponent_dialogues
        self.completion_dialogues = completion_dialogues
        self.defeated_opponents = 0
        self.bulbasaur_tail_whipped = False
        self.read_calls = 0

    def read(self) -> RawGameState:
        self.read_calls += 1
        return super().read()

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)
        if action.kind is MacroActionKind.WAIT:
            return
        if action.kind is MacroActionKind.MOVE:
            self._move_cursor(str(action.value))
            return
        if action.kind is not MacroActionKind.CONFIRM:
            raise AssertionError(f"controller emitted unsupported action {action.kind}")

        if self.raw.battle_state == 0:
            self.completion_dialogues -= 1
            if self.completion_dialogues <= 0:
                self.controls = READY
            return
        if self.menu.phase is BattleMenuPhase.MAIN:
            assert self.menu.selected_main_command == 0
            self.menu = BattleMenuState(
                BattleMenuPhase.MOVE,
                selected_move_slot=1,
            )
            return
        if self.menu.phase is BattleMenuPhase.MOVE:
            slot = self.menu.selected_move_slot
            assert slot is not None
            pp = list(self.raw.first_party_pp or ())
            pp[slot - 1] -= 1
            self.raw = replace(self.raw, first_party_pp=tuple(pp))
            if (
                self.raw.enemy_species_id == BULBASAUR_SPECIES_ID
                and slot == 2
                and not self.bulbasaur_tail_whipped
            ):
                self.bulbasaur_tail_whipped = True
                self.raw = replace(self.raw, enemy_defense_stage=6)
                self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
                self.between_opponent_dialogues = 1
                return
            self.defeated_opponents += 1
            self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
            if self.defeated_opponents == 2:
                self.raw = replace(self.raw, battle_state=0)
            return

        if self.defeated_opponents == 1:
            self.between_opponent_dialogues -= 1
            if self.between_opponent_dialogues <= 0:
                self.raw = replace(
                    self.raw,
                    enemy_species_id=BULBASAUR_SPECIES_ID,
                    enemy_hp=20,
                    player_attack_stage=6,
                    enemy_defense_stage=(
                        self.raw.enemy_defense_stage if self.bulbasaur_tail_whipped else 7
                    ),
                )
                self.menu = BattleMenuState(
                    BattleMenuPhase.MAIN,
                    selected_main_command=0,
                )

    def _move_cursor(self, direction: str) -> None:
        if self.menu.phase is BattleMenuPhase.MAIN:
            command = self.menu.selected_main_command
            command = {
                (1, "up"): 0,
                (2, "left"): 0,
                (3, "up"): 2,
            }.get((command, direction), command)
            self.menu = BattleMenuState(
                BattleMenuPhase.MAIN,
                selected_main_command=command,
            )
            return
        if self.menu.phase is BattleMenuPhase.MOVE:
            slot = self.menu.selected_move_slot
            assert slot is not None
            slot += 1 if direction == "down" else -1
            self.menu = BattleMenuState(
                BattleMenuPhase.MOVE,
                selected_move_slot=slot,
            )


class SleepRecoverySimulation(FakeRuntime):
    def __init__(self, *, sleep_dialogue_pulses: int = 0) -> None:
        super().__init__()
        self.sleep_started = False
        self.sleep_dialogue_pulses = sleep_dialogue_pulses

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)
        if action.kind is MacroActionKind.WAIT:
            return
        if action.kind is MacroActionKind.CANCEL:
            assert self.menu.phase is BattleMenuPhase.MOVE
            self.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)
            return
        if action.kind is not MacroActionKind.CONFIRM:
            raise AssertionError(f"unsupported sleep simulation action {action.kind}")
        if self.raw.battle_state == 0:
            self.controls = READY
            return
        if self.menu.phase is BattleMenuPhase.MAIN:
            if not self.sleep_started:
                self.sleep_started = True
                self.raw = replace(self.raw, first_party_status=4)
                self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
            else:
                self.menu = BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1)
            return
        if self.menu.phase is BattleMenuPhase.UNKNOWN:
            if self.sleep_dialogue_pulses:
                self.sleep_dialogue_pulses -= 1
                return
            count = (self.raw.first_party_status or 0) & 0x07
            next_count = 1 if count == 4 else 0
            self.raw = replace(self.raw, first_party_status=next_count)
            if next_count == 0:
                self.menu = BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1)
            return
        pp = list(self.raw.first_party_pp or ())
        pp[0] -= 1
        self.raw = replace(self.raw, first_party_pp=tuple(pp), battle_state=0, enemy_hp=0)
        self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)


class OffSlotSleepPPSimulation(SleepRecoverySimulation):
    def execute(self, action: MacroAction) -> None:
        recovering = (
            action.kind is MacroActionKind.CONFIRM
            and self.menu.phase is BattleMenuPhase.UNKNOWN
            and bool((self.raw.first_party_status or 0) & 0x07)
        )
        super().execute(action)
        if recovering:
            pp = list(self.raw.first_party_pp or ())
            pp[3] -= 1
            self.raw = replace(self.raw, first_party_pp=tuple(pp))


class PostSelectionSleepSimulation(FakeRuntime):
    """Model a faster opponent applying sleep after a move was selected."""

    def __init__(self) -> None:
        super().__init__()
        self.sleep_started = False

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)
        if action.kind is MacroActionKind.WAIT:
            return
        if action.kind is MacroActionKind.CANCEL:
            assert self.menu.phase is BattleMenuPhase.MOVE
            self.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)
            return
        if action.kind is not MacroActionKind.CONFIRM:
            raise AssertionError(f"unsupported sleep simulation action {action.kind}")
        if self.raw.battle_state == 0:
            self.controls = READY
            return
        if self.menu.phase is BattleMenuPhase.MAIN:
            self.menu = BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1)
            return
        if self.menu.phase is BattleMenuPhase.MOVE and not self.sleep_started:
            self.sleep_started = True
            self.raw = replace(self.raw, first_party_status=4)
            self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
            return
        if self.menu.phase is BattleMenuPhase.UNKNOWN:
            count = (self.raw.first_party_status or 0) & 0x07
            next_count = 1 if count == 4 else 0
            self.raw = replace(self.raw, first_party_status=next_count)
            if next_count == 0:
                self.menu = BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1)
            return
        pp = list(self.raw.first_party_pp or ())
        pp[0] -= 1
        self.raw = replace(self.raw, first_party_pp=tuple(pp), battle_state=0, enemy_hp=0)
        self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)


class ReappliedSleepSimulation(SleepRecoverySimulation):
    """Model waking and being put back to sleep before the next observation."""

    def __init__(self, *, reapplications: int) -> None:
        super().__init__()
        self.reapplications = reapplications

    def execute(self, action: MacroAction) -> None:
        recovering = (
            action.kind is MacroActionKind.CONFIRM
            and self.menu.phase is BattleMenuPhase.UNKNOWN
            and bool((self.raw.first_party_status or 0) & 0x07)
        )
        if not recovering:
            sleep_was_started = self.sleep_started
            super().execute(action)
            if (
                not sleep_was_started
                and self.sleep_started
                and self.menu.phase is BattleMenuPhase.UNKNOWN
            ):
                self.raw = replace(self.raw, first_party_status=2)
            return

        self.actions.append(action)
        count = (self.raw.first_party_status or 0) & 0x07
        if count == 1 and self.reapplications:
            self.reapplications -= 1
            self.raw = replace(self.raw, first_party_status=5)
            return
        next_count = max(0, count - 1)
        self.raw = replace(self.raw, first_party_status=next_count)
        if next_count == 0:
            self.menu = BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1)


class MainMenuSleepRecoverySimulation(FakeRuntime):
    """Model Gen I returning to MAIN between suppressed sleeping turns."""

    def __init__(self) -> None:
        super().__init__()
        self.sleep_started = False

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)
        if action.kind is MacroActionKind.WAIT:
            return
        if action.kind is MacroActionKind.CANCEL:
            assert self.menu.phase is BattleMenuPhase.MOVE
            self.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)
            return
        if action.kind is MacroActionKind.MOVE:
            if self.menu.phase is BattleMenuPhase.MAIN:
                assert action.value == "up"
                self.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)
                return
            raise AssertionError("unexpected move-menu navigation in sleep simulation")
        if action.kind is not MacroActionKind.CONFIRM:
            raise AssertionError(f"unsupported sleep simulation action {action.kind}")
        if self.raw.battle_state == 0:
            self.controls = READY
            return
        if self.menu.phase is BattleMenuPhase.MAIN:
            if not self.sleep_started:
                self.sleep_started = True
                self.raw = replace(self.raw, first_party_status=3)
                self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
            else:
                self.menu = BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1)
            return
        if self.menu.phase is BattleMenuPhase.UNKNOWN:
            self.raw = replace(self.raw, first_party_status=2)
            self.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=1)
            return
        count = (self.raw.first_party_status or 0) & 0x07
        if count:
            next_count = count - 1
            self.raw = replace(self.raw, first_party_status=next_count)
            self.menu = (
                BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1)
                if next_count == 0
                else BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=1)
            )
            return
        pp = list(self.raw.first_party_pp or ())
        pp[0] -= 1
        self.raw = replace(self.raw, first_party_pp=tuple(pp), battle_state=0, enemy_hp=0)
        self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)


class TerminalWildSleepSimulation(SleepRecoverySimulation):
    def execute(self, action: MacroAction) -> None:
        ending_sleep_turn = (
            action.kind is MacroActionKind.CONFIRM
            and self.menu.phase is BattleMenuPhase.UNKNOWN
            and bool((self.raw.first_party_status or 0) & 0x07)
        )
        if ending_sleep_turn:
            self.actions.append(action)
            self.raw = replace(self.raw, battle_state=0, enemy_hp=0)
            self.controls = READY
            return
        super().execute(action)


def _non_wait_actions(runtime: FakeRuntime) -> list[MacroAction]:
    return [action for action in runtime.actions if action.kind is not MacroActionKind.WAIT]


def test_adaptive_controller_recovers_a_decreasing_sleep_counter() -> None:
    runtime = SleepRecoverySimulation()

    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        lambda raw: 1,
        expected_map=MapId.CERULEAN_CITY,
        timing=BattleRuntimeTiming(max_move_menu_transition_pulses=1),
    )

    assert final.battle_state == 0
    assert final.first_party_status == 0
    assert final.first_party_pp == (34, 30, 30, 11)
    assert MacroAction(MacroActionKind.CANCEL) in runtime.actions


def test_adaptive_controller_recovers_sleep_applied_after_move_selection() -> None:
    runtime = PostSelectionSleepSimulation()

    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        lambda _raw: 1,
        expected_map=MapId.CERULEAN_CITY,
    )

    assert final.battle_state == 0
    assert final.first_party_status == 0
    assert final.first_party_pp == (34, 30, 30, 11)
    assert MacroAction(MacroActionKind.CANCEL) in runtime.actions


def test_adaptive_controller_bounds_but_survives_a_long_sing_sequence() -> None:
    runtime = SleepRecoverySimulation(sleep_dialogue_pulses=30)

    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        lambda raw: 1,
        expected_map=MapId.CERULEAN_CITY,
        timing=BattleRuntimeTiming(max_move_menu_transition_pulses=1),
    )

    assert final.battle_state == 0
    assert final.first_party_status == 0
    assert final.first_party_pp == (34, 30, 30, 11)
    assert runtime.sleep_dialogue_pulses == 0


def test_sleep_recovery_budget_scales_with_semantic_turn_counter() -> None:
    runtime = SleepRecoverySimulation(sleep_dialogue_pulses=60)

    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        lambda raw: 1,
        expected_map=MapId.CERULEAN_CITY,
        timing=BattleRuntimeTiming(max_move_menu_transition_pulses=1),
    )

    assert final.battle_state == 0
    assert final.first_party_status == 0
    assert final.first_party_pp == (34, 30, 30, 11)
    assert runtime.sleep_dialogue_pulses == 0


def test_sleep_recovery_reenters_fight_after_each_suppressed_turn() -> None:
    runtime = MainMenuSleepRecoverySimulation()

    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        lambda raw: 1,
        expected_map=MapId.CERULEAN_CITY,
        timing=BattleRuntimeTiming(max_move_menu_transition_pulses=1),
    )

    assert final.battle_state == 0
    assert final.first_party_status == 0
    assert final.first_party_pp == (34, 30, 30, 11)
    assert MacroAction(MacroActionKind.MOVE, "up") in runtime.actions


def test_sleep_recovery_accepts_bounded_immediate_reapplications() -> None:
    runtime = ReappliedSleepSimulation(reapplications=2)

    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        lambda raw: 1,
        expected_map=MapId.CERULEAN_CITY,
        timing=BattleRuntimeTiming(max_move_menu_transition_pulses=1),
    )

    assert final.battle_state == 0
    assert final.first_party_status == 0
    assert final.first_party_pp == (34, 30, 30, 11)
    assert runtime.reapplications == 0


def test_sleep_recovery_rejects_excessive_immediate_reapplications() -> None:
    runtime = ReappliedSleepSimulation(reapplications=3)

    with pytest.raises(BattleRuntimeError, match="bounded sleep reapplications"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda raw: 1,
            expected_map=MapId.CERULEAN_CITY,
            timing=BattleRuntimeTiming(max_move_menu_transition_pulses=1),
        )


def test_sleep_recovery_supports_a_larger_explicit_curriculum_bound() -> None:
    runtime = ReappliedSleepSimulation(reapplications=3)

    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        lambda raw: 1,
        expected_map=MapId.CERULEAN_CITY,
        timing=BattleRuntimeTiming(
            max_move_menu_transition_pulses=1,
            max_sleep_reapplications=3,
        ),
    )

    assert final.battle_state == 0
    assert final.first_party_status == 0
    assert runtime.reapplications == 0


def test_sleep_recovery_rejects_an_off_slot_pp_decrement() -> None:
    runtime = OffSlotSleepPPSimulation()

    with pytest.raises(BattleRuntimeError, match="off-slot PP"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda raw: 1,
            expected_map=MapId.CERULEAN_CITY,
            timing=BattleRuntimeTiming(max_move_menu_transition_pulses=1),
        )


def test_wild_battle_may_end_without_pp_while_sleep_recovery_is_active() -> None:
    runtime = TerminalWildSleepSimulation()
    runtime.raw = replace(runtime.raw, battle_state=1)

    final = run_adaptive_wild_battle(
        runtime,
        runtime,
        lambda raw: 1,
        expected_map=MapId.CERULEAN_CITY,
        timing=BattleRuntimeTiming(max_move_menu_transition_pulses=1),
    )

    assert final.battle_state == 0
    assert final.first_party_hp == 26
    assert final.first_party_pp == (35, 30, 30, 11)


def test_actor_error_propagation_is_not_counted_as_observer_loss() -> None:
    runtime = OffSlotSleepPPSimulation()
    observer = RecordingDecisionObserver(runtime)

    with (
        bind_battle_decision_observer(observer),
        pytest.raises(BattleRuntimeError, match="off-slot PP"),
    ):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda raw: 1,
            expected_map=MapId.CERULEAN_CITY,
            intent=BattleIntent("help_bill", TEST_BATTLE_PLAN_ID),
            timing=BattleRuntimeTiming(max_move_menu_transition_pulses=1),
        )

    assert observer.failures == 0


def test_adaptive_controller_rechecks_species_and_switches_water_gun_to_mega_punch() -> None:
    runtime = AdaptiveRivalSimulation()
    policy_species: list[int | None] = []

    def policy(raw: RawGameState) -> int:
        policy_species.append(raw.enemy_species_id)
        return choose_cerulean_rival_move_slot(raw)

    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        policy,
        expected_map=MapId.CERULEAN_CITY,
    )

    assert policy_species == [
        PIDGEOTTO_SPECIES_ID,
        BULBASAUR_SPECIES_ID,
        BULBASAUR_SPECIES_ID,
    ]
    assert final.battle_state == 0
    assert final.first_party_hp == 26
    assert final.first_party_pp == (35, 29, 29, 10)
    moves = [
        action.value for action in _non_wait_actions(runtime) if action.kind is MacroActionKind.MOVE
    ]
    assert moves == ["down", "down", "down", "down", "down", "down"]
    assert runtime.controls.ready
    assert runtime.actions[-1] == MacroAction(MacroActionKind.WAIT)
    assert {action.kind for action in runtime.actions} <= {
        MacroActionKind.MOVE,
        MacroActionKind.CONFIRM,
        MacroActionKind.WAIT,
    }


def test_intent_aware_policy_receives_the_predeclared_planner_context() -> None:
    runtime = AdaptiveRivalSimulation()
    intent = BattleIntent("help_bill", TEST_BATTLE_PLAN_ID)

    class IntentAwarePolicy:
        def __init__(self) -> None:
            self.observations: list[BattlePolicyObservation] = []

        def choose_move(self, observation: BattlePolicyObservation) -> int:
            self.observations.append(observation)
            return choose_cerulean_rival_move_slot(observation.state)

    policy = IntentAwarePolicy()
    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        policy,
        expected_map=MapId.CERULEAN_CITY,
        intent=intent,
    )

    assert final.battle_state == 0
    assert len(policy.observations) == 3
    assert all(observation.intent == intent for observation in policy.observations)


def test_move_decision_sink_observes_learned_choices_without_querying_teacher() -> None:
    runtime = AdaptiveRivalSimulation()
    teacher_queries = 0
    observed: list[tuple[int | None, int]] = []

    def teacher(_raw: RawGameState) -> int:
        nonlocal teacher_queries
        teacher_queries += 1
        raise AssertionError("the learned policy must not query its teacher")

    class LearnedPolicy:
        def choose_move(
            self,
            observation: BattlePolicyObservation,
            _fallback: Callable[[], int],
        ) -> int:
            return choose_cerulean_rival_move_slot(observation.state)

    with bind_battle_policy_override(LearnedPolicy()):
        final = run_adaptive_trainer_battle(
            runtime,
            runtime,
            teacher,
            expected_map=MapId.CERULEAN_CITY,
            move_decision_sink=lambda raw, slot: observed.append(
                (raw.enemy_species_id, slot)
            ),
        )

    assert final.battle_state == 0
    assert teacher_queries == 0
    assert observed == [
        (PIDGEOTTO_SPECIES_ID, 4),
        (BULBASAUR_SPECIES_ID, 2),
        (BULBASAUR_SPECIES_ID, 3),
    ]


def test_preregistered_offset_runs_before_policy_on_the_refreshed_state() -> None:
    runtime = AdaptiveRivalSimulation()
    controller = BattleStartScheduleController(_scheduled_offsets(first_frames=7))
    policy_observations: list[tuple[int | None, int, tuple[MacroAction, ...]]] = []
    scheduled_wait_seen = False

    original_execute = runtime.execute

    def execute(action: MacroAction) -> None:
        nonlocal scheduled_wait_seen
        original_execute(action)
        if action == MacroAction(MacroActionKind.WAIT, repeat=7):
            scheduled_wait_seen = True
            runtime.raw = replace(runtime.raw)

    runtime.execute = execute  # type: ignore[method-assign]

    def policy(raw: RawGameState) -> int:
        policy_observations.append((raw.enemy_hp, runtime.read_calls, tuple(runtime.actions)))
        return choose_cerulean_rival_move_slot(raw)

    with bind_battle_start_schedule(controller):
        final = run_adaptive_trainer_battle(
            runtime,
            runtime,
            policy,
            expected_map=MapId.CERULEAN_CITY,
            intent=BattleIntent("help_bill", SCHEDULED_BATTLE_PLAN_ID),
        )

    assert scheduled_wait_seen is True
    assert final.battle_state == 0
    assert runtime.actions[0] == MacroAction(MacroActionKind.WAIT, repeat=7)
    assert policy_observations[0][0] == 20
    assert policy_observations[0][1] >= 3
    assert policy_observations[0][2][0] == MacroAction(
        MacroActionKind.WAIT,
        repeat=7,
    )
    assert controller.finished_count == 1
    assert controller.failed is False


def test_zero_offset_rereads_without_emitting_a_zero_repeat_wait() -> None:
    baseline = AdaptiveRivalSimulation()
    run_adaptive_trainer_battle(
        baseline,
        baseline,
        choose_cerulean_rival_move_slot,
        expected_map=MapId.CERULEAN_CITY,
    )

    scheduled = AdaptiveRivalSimulation()
    controller = BattleStartScheduleController(_scheduled_offsets(first_frames=0))
    with bind_battle_start_schedule(controller):
        run_adaptive_trainer_battle(
            scheduled,
            scheduled,
            choose_cerulean_rival_move_slot,
            expected_map=MapId.CERULEAN_CITY,
            intent=BattleIntent("help_bill", SCHEDULED_BATTLE_PLAN_ID),
        )

    assert scheduled.actions == baseline.actions
    assert scheduled.read_calls == baseline.read_calls + 1
    assert controller.finished_count == 1


def test_unscheduled_adaptive_battle_does_not_consume_bound_schedule() -> None:
    runtime = AdaptiveRivalSimulation()
    controller = BattleStartScheduleController(_scheduled_offsets(first_frames=7))
    with bind_battle_start_schedule(controller):
        final = run_adaptive_trainer_battle(
            runtime,
            runtime,
            choose_cerulean_rival_move_slot,
            expected_map=MapId.CERULEAN_CITY,
            intent=BattleIntent("help_bill", TEST_BATTLE_PLAN_ID),
            consume_battle_start_schedule=False,
        )

    assert final.battle_state == 0
    assert controller.finished_count == 0
    assert MacroAction(MacroActionKind.WAIT, repeat=7) not in runtime.actions


def test_preregistered_offset_is_not_reapplied_across_runtime_reentry() -> None:
    runtime = AdaptiveRivalSimulation()
    controller = BattleStartScheduleController(_scheduled_offsets(first_frames=7))
    intent = BattleIntent(
        "help_bill",
        SCHEDULED_BATTLE_PLAN_ID,
        resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
    )

    with bind_battle_start_schedule(controller):
        with pytest.raises(BattleRuntimeTimeoutError, match="bounded runtime pulses"):
            run_adaptive_trainer_battle(
                runtime,
                runtime,
                choose_cerulean_rival_move_slot,
                expected_map=MapId.CERULEAN_CITY,
                intent=intent,
                timing=replace(BattleRuntimeTiming(), max_runtime_pulses=1),
            )
        final = run_adaptive_trainer_battle(
            runtime,
            runtime,
            choose_cerulean_rival_move_slot,
            expected_map=MapId.CERULEAN_CITY,
            intent=intent,
        )

    assert final.battle_state == 0
    assert runtime.actions.count(MacroAction(MacroActionKind.WAIT, repeat=7)) == 1
    assert controller.finished_count == 1
    assert controller.failed is False


@pytest.mark.parametrize("failure", ["menu", "enemy", "visible_drift"])
def test_preregistered_offset_fails_if_main_menu_evidence_changes(
    failure: str,
) -> None:
    runtime = FakeRuntime()
    controller = BattleStartScheduleController(_scheduled_offsets(first_frames=7))
    policy_calls = 0

    def invalidate_after_wait(action: MacroAction) -> None:
        if action != MacroAction(MacroActionKind.WAIT, repeat=7):
            return
        if failure == "menu":
            runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
        elif failure == "enemy":
            runtime.raw = replace(runtime.raw, enemy_hp=0)
        else:
            runtime.raw = replace(runtime.raw, enemy_hp=19)

    runtime.on_action = invalidate_after_wait

    def policy(_raw: RawGameState) -> int:
        nonlocal policy_calls
        policy_calls += 1
        return 1

    with (
        bind_battle_start_schedule(controller),
        pytest.raises(BattleRuntimeError, match="battle-start offset"),
    ):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            policy,
            expected_map=MapId.CERULEAN_CITY,
            intent=BattleIntent("help_bill", SCHEDULED_BATTLE_PLAN_ID),
        )

    assert policy_calls == 0
    assert controller.failed is True
    assert runtime.actions == [MacroAction(MacroActionKind.WAIT, repeat=7)]


def test_final_move_closes_schedule_and_observer_before_one_pulse_timeout() -> None:
    runtime = FakeRuntime()
    observer = RecordingDecisionObserver(runtime)
    controller = BattleStartScheduleController(_scheduled_offsets(first_frames=0))
    intent = BattleIntent("help_bill", SCHEDULED_BATTLE_PLAN_ID)

    def execute(action: MacroAction) -> None:
        if action.kind is not MacroActionKind.CONFIRM:
            return
        if runtime.menu.phase is BattleMenuPhase.MAIN:
            runtime.menu = BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1)
            return
        if runtime.menu.phase is BattleMenuPhase.MOVE:
            pp = list(runtime.raw.first_party_pp or ())
            pp[0] -= 1
            runtime.raw = replace(
                runtime.raw,
                battle_state=0,
                enemy_hp=0,
                first_party_pp=tuple(pp),
            )
            runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)

    runtime.on_action = execute
    with (
        bind_battle_start_schedule(controller),
        bind_battle_decision_observer(observer),
        pytest.raises(BattleRuntimeTimeoutError, match="bounded runtime pulses"),
    ):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
            intent=intent,
            timing=replace(BattleRuntimeTiming(), max_runtime_pulses=1),
        )

    assert runtime.raw.battle_state == 0
    assert controller.finished_count == 1
    assert controller.failed is False
    assert observer.finishes == 1
    assert observer.failures == 0


def test_preregistered_schedule_rejects_missing_or_wrong_battle_intent() -> None:
    missing = FakeRuntime()
    missing_controller = BattleStartScheduleController(_scheduled_offsets(first_frames=0))
    with (
        bind_battle_start_schedule(missing_controller),
        pytest.raises(BattleScheduleError, match="missing an explicit intent"),
    ):
        run_adaptive_trainer_battle(
            missing,
            missing,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
        )
    assert missing.actions == []

    wrong = FakeRuntime()
    wrong_controller = BattleStartScheduleController(_scheduled_offsets(first_frames=0))
    with (
        bind_battle_start_schedule(wrong_controller),
        pytest.raises(BattleScheduleError, match="order"),
    ):
        run_adaptive_trainer_battle(
            wrong,
            wrong,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
            intent=BattleIntent("help_bill", RED_BATTLE_PLAN_IDS[1]),
        )
    assert wrong.actions == []


def test_battle_decision_observer_scopes_each_validated_policy_turn() -> None:
    runtime = AdaptiveRivalSimulation()
    observer = RecordingDecisionObserver(runtime)
    intent = BattleIntent("help_bill", TEST_BATTLE_PLAN_ID)

    with bind_battle_decision_observer(observer):
        final = run_adaptive_trainer_battle(
            runtime,
            runtime,
            choose_cerulean_rival_move_slot,
            expected_map=MapId.CERULEAN_CITY,
            intent=intent,
            label="Cerulean rival",
        )

    assert final.battle_state == 0
    assert observer.starts == [intent]
    assert observer.finishes == 1
    assert [entry[0] for entry in observer.entries] == [4, 2, 3]
    assert len(observer.exits) == len(observer.entries)
    assert all(
        exit_action_count > entry[1]
        for entry, exit_action_count in zip(observer.entries, observer.exits, strict=True)
    )

    unobserved = AdaptiveRivalSimulation()
    run_adaptive_trainer_battle(
        unobserved,
        unobserved,
        choose_cerulean_rival_move_slot,
        expected_map=MapId.CERULEAN_CITY,
    )
    assert len(observer.entries) == 3


def test_wild_battle_carries_training_intent_to_the_decision_observer() -> None:
    runtime = AdaptiveRivalSimulation()
    runtime.raw = replace(runtime.raw, battle_state=1)
    observer = RecordingDecisionObserver(runtime)
    intent = BattleIntent("help_bill", "red.mansion.balanced-team-training")

    with bind_battle_decision_observer(observer):
        final = run_adaptive_wild_battle(
            runtime,
            runtime,
            lambda raw: choose_cerulean_rival_move_slot(replace(raw, battle_state=2)),
            expected_map=MapId.CERULEAN_CITY,
            intent=intent,
            label="balanced-team training",
        )

    assert final.battle_state == 0
    assert observer.starts == [intent]
    assert observer.finishes == 1
    assert observer.failures == 0
    assert len(observer.entries) == 3


def test_external_flee_hook_closes_the_observed_battle_instance() -> None:
    runtime = FakeRuntime(raw=_raw(battle_state=1))
    observer = RecordingDecisionObserver(runtime)
    first = BattleIntent("help_bill", "red.mansion.training-recovery")
    second = BattleIntent("help_bill", "red.mansion.training-resumed")

    with bind_battle_decision_observer(observer):
        observer.battle_started(intent=first)
        note_observed_battle_exit()
        observer.battle_started(intent=second)

    assert observer.starts == [first, second]
    assert observer.finishes == 1
    assert observer.failures == 0


@pytest.mark.parametrize("failure_phase", ["enter", "exit"])
def test_observer_context_lifecycle_failures_never_interrupt_the_actor(
    failure_phase: str,
) -> None:
    runtime = AdaptiveRivalSimulation()
    observer = FailingLifecycleObserver(failure_phase)

    with bind_battle_decision_observer(observer):
        final = run_adaptive_trainer_battle(
            runtime,
            runtime,
            choose_cerulean_rival_move_slot,
            expected_map=MapId.CERULEAN_CITY,
            intent=BattleIntent("help_bill", TEST_BATTLE_PLAN_ID),
        )

    assert final.battle_state == 0
    assert observer.failures == 3


def test_adaptive_battle_records_linked_privacy_safe_decision_spans() -> None:
    runtime = AdaptiveRivalSimulation()
    encoder = PokemonRedObservationEncoder(runtime)
    sink = InMemoryTrajectorySink()
    recorder = RecordingExecutor(
        delegate=runtime,
        snapshot_provider=encoder,
        sink=sink,
        episode_id="battle-episode",
    )
    observer = PokemonRedBattleDecisionObserver(
        encoder=encoder,
        recorder=recorder,
    )
    intent = BattleIntent("help_bill", TEST_BATTLE_PLAN_ID)

    with bind_battle_decision_observer(observer):
        final = run_adaptive_trainer_battle(
            runtime,
            recorder,
            choose_cerulean_rival_move_slot,
            expected_map=MapId.CERULEAN_CITY,
            intent=intent,
            label="private encounter label",
        )

    assert final.battle_state == 0
    assert recorder.recording_failures == 0
    assert len(sink.executions) == len(runtime.actions)
    assert [decision.action["slot_index"] for decision in sink.decisions] == [3, 1, 2]
    assert all("private encounter label" not in canonical_json(item) for item in sink.decisions)
    assert {decision.context.metadata["battle_instance_id"] for decision in sink.decisions} == {
        "battle-episode:battle:0"
    }
    assert all(decision.context.objective_id == "help_bill" for decision in sink.decisions)
    assert all(
        decision.context.metadata["battle_plan_id"] == TEST_BATTLE_PLAN_ID
        for decision in sink.decisions
    )
    assert all(decision.context.metadata["battle_goal"] == "win" for decision in sink.decisions)
    assert all(
        decision.context.metadata["battle_policy_context"]
        == {
            "goal": "win",
            "move_policy": "any_usable",
            "required_move_ref": None,
        }
        for decision in sink.decisions
    )
    assert all(
        decision.context.metadata["teacher_recovery_marker"] == "none"
        for decision in sink.decisions
    )
    for decision in sink.decisions:
        linked = [
            execution
            for execution in sink.executions
            if execution.decision_id == decision.decision_id
        ]
        assert linked
        assert linked[0].step_index == decision.step_index
        assert linked[0].before_sha256 == decision.snapshot_sha256


def test_scheduled_wait_is_recorded_outside_the_policy_decision_span() -> None:
    runtime = AdaptiveRivalSimulation()
    encoder = PokemonRedObservationEncoder(runtime)
    sink = InMemoryTrajectorySink()
    recorder = RecordingExecutor(
        delegate=runtime,
        snapshot_provider=encoder,
        sink=sink,
        episode_id="scheduled-battle-episode",
    )
    observer = PokemonRedBattleDecisionObserver(
        encoder=encoder,
        recorder=recorder,
    )
    controller = BattleStartScheduleController(_scheduled_offsets(first_frames=7))
    schedule_observer = PokemonRedBattleScheduleObserver(
        encoder=encoder,
        recorder=recorder,
        sink=sink,
        schedule_sha256=controller.schedule_sha256,
    )
    intent = BattleIntent("help_bill", SCHEDULED_BATTLE_PLAN_ID)

    with (
        bind_battle_start_schedule(controller),
        bind_battle_decision_observer(observer),
        bind_battle_schedule_observer(schedule_observer),
    ):
        final = run_adaptive_trainer_battle(
            runtime,
            recorder,
            choose_cerulean_rival_move_slot,
            expected_map=MapId.CERULEAN_CITY,
            intent=intent,
        )

    assert final.battle_state == 0
    assert recorder.recording_failures == 0
    assert sink.executions[0].action == {
        "kind": "wait",
        "repeat": 7,
        "value": None,
    }
    assert sink.executions[0].decision_id is None
    assert sink.decisions[0].step_index > sink.executions[0].step_index
    schedule_events = [
        event for event in sink.events if event.kind == "battle_start_offset_applied"
    ]
    assert len(schedule_events) == 1
    assert schedule_events[0].payload["battle_ordinal"] == 1
    assert schedule_events[0].payload["battle_plan_id"] == SCHEDULED_BATTLE_PLAN_ID
    assert schedule_events[0].payload["frames"] == 7
    assert schedule_events[0].payload["execution_step_index"] == 0
    assert (
        schedule_events[0].payload["before_snapshot_sha256"]
        == schedule_events[0].payload["after_snapshot_sha256"]
    )
    assert schedule_events[0].payload["schedule_sha256"] == controller.schedule_sha256
    assert controller.finished_count == 1


def test_zero_offset_has_an_attestation_without_a_fake_execution() -> None:
    runtime = AdaptiveRivalSimulation()
    encoder = PokemonRedObservationEncoder(runtime)
    sink = InMemoryTrajectorySink()
    recorder = RecordingExecutor(
        delegate=runtime,
        snapshot_provider=encoder,
        sink=sink,
        episode_id="zero-offset-episode",
    )
    decision_observer = PokemonRedBattleDecisionObserver(
        encoder=encoder,
        recorder=recorder,
    )
    controller = BattleStartScheduleController(_scheduled_offsets(first_frames=0))
    schedule_observer = PokemonRedBattleScheduleObserver(
        encoder=encoder,
        recorder=recorder,
        sink=sink,
        schedule_sha256=controller.schedule_sha256,
    )

    with (
        bind_battle_start_schedule(controller),
        bind_battle_decision_observer(decision_observer),
        bind_battle_schedule_observer(schedule_observer),
    ):
        run_adaptive_trainer_battle(
            runtime,
            recorder,
            choose_cerulean_rival_move_slot,
            expected_map=MapId.CERULEAN_CITY,
            intent=BattleIntent("help_bill", SCHEDULED_BATTLE_PLAN_ID),
        )

    event = next(event for event in sink.events if event.kind == "battle_start_offset_applied")
    assert event.payload["frames"] == 0
    assert event.payload["execution_step_index"] is None
    assert all(
        execution.action != {"kind": "wait", "repeat": 0, "value": None}
        for execution in sink.executions
    )


def test_recorded_battle_without_explicit_intent_fails_closed() -> None:
    runtime = AdaptiveRivalSimulation()
    encoder = PokemonRedObservationEncoder(runtime)
    sink = InMemoryTrajectorySink()
    recorder = RecordingExecutor(
        delegate=runtime,
        snapshot_provider=encoder,
        sink=sink,
        episode_id="missing-intent-episode",
    )
    observer = PokemonRedBattleDecisionObserver(
        encoder=encoder,
        recorder=recorder,
    )

    with bind_battle_decision_observer(observer):
        final = run_adaptive_trainer_battle(
            runtime,
            recorder,
            choose_cerulean_rival_move_slot,
            expected_map=MapId.CERULEAN_CITY,
        )

    assert final.battle_state == 0
    assert sink.decisions == ()
    assert recorder.recording_failures == 4
    assert len(sink.executions) == len(runtime.actions)


def test_reentry_intent_mismatch_is_counted_even_without_another_decision() -> None:
    runtime = ImmediateBattleExitRuntime()
    encoder = PokemonRedObservationEncoder(runtime)
    sink = InMemoryTrajectorySink()
    recorder = RecordingExecutor(
        delegate=runtime,
        snapshot_provider=encoder,
        sink=sink,
        episode_id="mismatched-reentry-episode",
    )
    observer = PokemonRedBattleDecisionObserver(
        encoder=encoder,
        recorder=recorder,
    )
    observer.battle_started(intent=BattleIntent("help_bill", TEST_BATTLE_PLAN_ID))

    with bind_battle_decision_observer(observer):
        final = run_adaptive_trainer_battle(
            runtime,
            recorder,
            choose_cerulean_rival_move_slot,
            expected_map=MapId.CERULEAN_CITY,
            intent=BattleIntent("defeat_misty", TEST_BATTLE_PLAN_ID),
            timing=replace(BattleRuntimeTiming(), required_ready_reads=1),
        )

    assert final.battle_state == 0
    assert sink.decisions == ()
    assert recorder.recording_failures == 1
    assert runtime.actions == []


def test_battle_instance_id_survives_bounded_runtime_reentry() -> None:
    runtime = AdaptiveRivalSimulation()
    encoder = PokemonRedObservationEncoder(runtime)
    sink = InMemoryTrajectorySink()
    recorder = RecordingExecutor(
        delegate=runtime,
        snapshot_provider=encoder,
        sink=sink,
        episode_id="retry-episode",
    )
    observer = PokemonRedBattleDecisionObserver(
        encoder=encoder,
        recorder=recorder,
    )
    intent = BattleIntent(
        "help_bill",
        TEST_BATTLE_PLAN_ID,
        resource_policy=BattleResourcePolicy.BOUNDED_RECOVERY,
    )

    with bind_battle_decision_observer(observer):
        with pytest.raises(BattleRuntimeTimeoutError, match="bounded runtime pulses"):
            run_adaptive_trainer_battle(
                runtime,
                recorder,
                choose_cerulean_rival_move_slot,
                expected_map=MapId.CERULEAN_CITY,
                intent=intent,
                timing=replace(BattleRuntimeTiming(), max_runtime_pulses=1),
            )
        final = run_adaptive_trainer_battle(
            runtime,
            recorder,
            choose_cerulean_rival_move_slot,
            expected_map=MapId.CERULEAN_CITY,
            intent=intent,
        )

    assert final.battle_state == 0
    assert recorder.recording_failures == 0
    assert len(sink.decisions) == 3
    assert {decision.context.metadata["battle_instance_id"] for decision in sink.decisions} == {
        "retry-episode:battle:0"
    }


def test_policy_is_called_once_while_main_cursor_moves_to_fight() -> None:
    runtime = AdaptiveRivalSimulation(first_main_command=3)
    policy_species: list[int | None] = []

    def policy(raw: RawGameState) -> int:
        policy_species.append(raw.enemy_species_id)
        return choose_cerulean_rival_move_slot(raw)

    run_adaptive_trainer_battle(
        runtime,
        runtime,
        policy,
        expected_map=MapId.CERULEAN_CITY,
    )

    assert policy_species == [
        PIDGEOTTO_SPECIES_ID,
        BULBASAUR_SPECIES_ID,
        BULBASAUR_SPECIES_ID,
    ]
    assert [action.value for action in _non_wait_actions(runtime)[:2]] == ["up", "left"]


def test_unknown_semantic_screens_survive_level_up_and_move_learning_dialogue() -> None:
    runtime = AdaptiveRivalSimulation(
        between_opponent_dialogues=6,
        completion_dialogues=4,
    )

    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        choose_cerulean_rival_move_slot,
        expected_map=MapId.CERULEAN_CITY,
    )

    assert final.battle_state == 0
    assert runtime.defeated_opponents == 2
    assert sum(action.kind is MacroActionKind.CONFIRM for action in runtime.actions) >= 14


@pytest.mark.parametrize("slot", [0, 5, True])
def test_invalid_policy_slot_fails_before_opening_fight(slot: int) -> None:
    runtime = FakeRuntime()

    with pytest.raises(BattleRuntimeError, match="invalid one-based slot"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: slot,
            expected_map=MapId.CERULEAN_CITY,
        )

    assert runtime.actions == []


def test_policy_exception_fails_without_pressing_through() -> None:
    runtime = FakeRuntime()

    def rejecting_policy(_raw: RawGameState) -> int:
        raise ValueError("unsupported enemy")

    with pytest.raises(BattleRuntimeError, match="policy rejected"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            rejecting_policy,
            expected_map=MapId.CERULEAN_CITY,
        )

    assert runtime.actions == []


def test_transient_main_menu_with_zero_enemy_hp_never_calls_policy() -> None:
    calls = 0
    runtime = FakeRuntime(raw=_raw(enemy_hp=0))

    def finish_transition(action: MacroAction) -> None:
        if action.kind is MacroActionKind.WAIT:
            runtime.raw = replace(runtime.raw, battle_state=0)
            runtime.controls = READY

    runtime.on_action = finish_transition

    def policy(_raw: RawGameState) -> int:
        nonlocal calls
        calls += 1
        return 1

    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        policy,
        expected_map=MapId.CERULEAN_CITY,
    )

    assert calls == 0
    assert final.battle_state == 0
    assert runtime.actions
    assert all(action.kind is MacroActionKind.WAIT for action in runtime.actions)


def test_opponent_recoil_ko_before_selected_move_preserves_pp() -> None:
    runtime = FakeRuntime()

    def recoil_before_player_move(action: MacroAction) -> None:
        if action.kind is not MacroActionKind.CONFIRM:
            return
        if runtime.menu.phase is BattleMenuPhase.MAIN:
            runtime.menu = BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1)
        elif runtime.menu.phase is BattleMenuPhase.MOVE:
            runtime.raw = replace(runtime.raw, enemy_hp=0)
            runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
        elif runtime.raw.enemy_hp == 0:
            runtime.raw = replace(runtime.raw, battle_state=0)
            runtime.controls = READY

    runtime.on_action = recoil_before_player_move
    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        lambda _raw: 1,
        expected_map=MapId.CERULEAN_CITY,
        required_move_id=TACKLE_MOVE_ID,
    )

    assert final.battle_state == 0
    assert final.first_party_pp == (35, 30, 30, 11)


def test_wild_selfdestruct_exit_can_preserve_selected_move_pp() -> None:
    runtime = FakeRuntime(raw=_raw(battle_state=1))

    def selfdestruct_before_player_move(action: MacroAction) -> None:
        if action.kind is not MacroActionKind.CONFIRM:
            return
        if runtime.menu.phase is BattleMenuPhase.MAIN:
            runtime.menu = BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1)
        elif runtime.menu.phase is BattleMenuPhase.MOVE:
            runtime.raw = replace(runtime.raw, battle_state=0)
            runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
            runtime.controls = READY

    runtime.on_action = selfdestruct_before_player_move
    final = run_adaptive_wild_battle(
        runtime,
        runtime,
        lambda _raw: 1,
        expected_map=MapId.CERULEAN_CITY,
    )

    assert final.battle_state == 0
    assert final.first_party_pp == (35, 30, 30, 11)


def test_trainer_exit_without_selected_move_pp_still_fails_closed() -> None:
    runtime = FakeRuntime()

    def unexplained_exit(action: MacroAction) -> None:
        if action.kind is not MacroActionKind.CONFIRM:
            return
        if runtime.menu.phase is BattleMenuPhase.MAIN:
            runtime.menu = BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1)
        elif runtime.menu.phase is BattleMenuPhase.MOVE:
            runtime.raw = replace(runtime.raw, battle_state=0)
            runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
            runtime.controls = READY

    runtime.on_action = unexplained_exit
    with pytest.raises(BattleRuntimeError, match="ended without"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
        )


def test_stale_main_after_pp_decrement_uses_cancel_without_spending_twice() -> None:
    runtime = FakeRuntime()
    policy_calls = 0

    def resolve_stale_main(action: MacroAction) -> None:
        if action.kind is MacroActionKind.WAIT:
            return
        if action.kind is MacroActionKind.CONFIRM and runtime.menu.phase is BattleMenuPhase.MAIN:
            runtime.menu = BattleMenuState(
                BattleMenuPhase.MOVE,
                selected_move_slot=1,
            )
            return
        if action.kind is MacroActionKind.CONFIRM and runtime.menu.phase is BattleMenuPhase.MOVE:
            pp = list(runtime.raw.first_party_pp or ())
            pp[0] -= 1
            runtime.raw = replace(runtime.raw, first_party_pp=tuple(pp))
            runtime.menu = BattleMenuState(
                BattleMenuPhase.MAIN,
                selected_main_command=0,
            )
            return
        if action.kind is MacroActionKind.CANCEL:
            runtime.raw = replace(runtime.raw, enemy_hp=10)
            runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
            return
        if action.kind is MacroActionKind.CONFIRM and runtime.menu.phase is BattleMenuPhase.UNKNOWN:
            runtime.raw = replace(runtime.raw, battle_state=0)
            runtime.controls = READY

    runtime.on_action = resolve_stale_main

    def policy(_raw: RawGameState) -> int:
        nonlocal policy_calls
        policy_calls += 1
        return 1

    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        policy,
        expected_map=MapId.CERULEAN_CITY,
    )

    assert final.battle_state == 0
    assert policy_calls == 1
    assert final.first_party_pp == (34, 30, 30, 11)
    non_wait = _non_wait_actions(runtime)
    assert MacroAction(MacroActionKind.CANCEL) in non_wait
    assert sum(action.kind is MacroActionKind.CONFIRM for action in non_wait) == 3


def test_main_menu_requires_live_enemy_hp_evidence() -> None:
    runtime = FakeRuntime(raw=_raw(enemy_hp=None))

    with pytest.raises(BattleRuntimeError, match="enemy HP evidence"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
        )

    assert runtime.actions == []


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (_raw(moves=(0, TAIL_WHIP_MOVE_ID, BUBBLE_MOVE_ID, WATER_GUN_MOVE_ID)), "move evidence"),
        (_raw(pp=None), "lacks PP evidence"),
        (_raw(pp=(0, 30, 30, 11)), "no usable PP"),
    ],
)
def test_policy_choice_requires_move_and_usable_pp_evidence(
    raw: RawGameState,
    message: str,
) -> None:
    runtime = FakeRuntime(raw=raw)

    with pytest.raises(BattleRuntimeError, match=message):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
        )

    assert runtime.actions == []


def test_policy_and_safety_gates_use_the_current_active_battler() -> None:
    active = replace(
        _raw(),
        active_party_index=1,
        active_party_hp=18,
        active_party_max_hp=52,
        active_party_status=0,
        active_party_moves=(0, TAIL_WHIP_MOVE_ID, BUBBLE_MOVE_ID, WATER_GUN_MOVE_ID),
        active_party_pp=(0, 30, 30, 11),
    )
    runtime = FakeRuntime(raw=active)

    with pytest.raises(BattleRuntimeError, match="move evidence"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
        )

    assert runtime.actions == []

    runtime = FakeRuntime(raw=replace(active, active_party_hp=0))
    with pytest.raises(BattleRuntimeError, match="active battler fainted"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 2,
            expected_map=MapId.CERULEAN_CITY,
        )


def test_attack_requires_persistent_pp_decrement() -> None:
    runtime = FakeRuntime()

    def ignore_attack(action: MacroAction) -> None:
        if action.kind is MacroActionKind.CONFIRM and runtime.menu.phase is BattleMenuPhase.MAIN:
            runtime.menu = BattleMenuState(
                BattleMenuPhase.MOVE,
                selected_move_slot=1,
            )

    runtime.on_action = ignore_attack
    timing = replace(
        BattleRuntimeTiming(),
        max_pp_confirmation_pulses=3,
        max_attack_confirmation_pulses=2,
    )

    with pytest.raises(BattleRuntimeError, match="PP-decrement gate"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
            timing=timing,
        )

    confirms = [action for action in runtime.actions if action.kind is MacroActionKind.CONFIRM]
    assert len(confirms) == 3


def test_attack_rejects_pp_change_larger_than_one() -> None:
    runtime = FakeRuntime()

    def spend_two_pp(action: MacroAction) -> None:
        if action.kind is not MacroActionKind.CONFIRM:
            return
        if runtime.menu.phase is BattleMenuPhase.MAIN:
            runtime.menu = BattleMenuState(
                BattleMenuPhase.MOVE,
                selected_move_slot=1,
            )
            return
        if runtime.menu.phase is BattleMenuPhase.MOVE:
            pp = list(runtime.raw.first_party_pp or ())
            pp[0] -= 2
            runtime.raw = replace(runtime.raw, first_party_pp=tuple(pp))
            runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)

    runtime.on_action = spend_two_pp

    with pytest.raises(BattleRuntimeError, match="invalid amount"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
        )


def test_default_pp_confirmation_window_covers_long_status_dialogue() -> None:
    assert BattleRuntimeTiming().max_pp_confirmation_pulses == 12


def test_faster_enemy_attack_text_is_confirmed_until_latched_move_spends_pp() -> None:
    runtime = FakeRuntime()
    opponent_text_pulses = 2

    def resolve_opponent_first_turn(action: MacroAction) -> None:
        nonlocal opponent_text_pulses
        if action.kind is not MacroActionKind.CONFIRM:
            return
        if runtime.menu.phase is BattleMenuPhase.MAIN:
            runtime.menu = BattleMenuState(
                BattleMenuPhase.MOVE,
                selected_move_slot=1,
            )
            return
        if runtime.menu.phase is BattleMenuPhase.MOVE:
            runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
            return
        opponent_text_pulses -= 1
        if opponent_text_pulses == 0:
            runtime.raw = replace(
                runtime.raw,
                battle_state=0,
                first_party_pp=(34, 30, 30, 11),
            )
            runtime.controls = READY

    runtime.on_action = resolve_opponent_first_turn
    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        lambda _raw: 1,
        expected_map=MapId.CERULEAN_CITY,
        timing=replace(BattleRuntimeTiming(), required_ready_reads=1),
    )

    assert final.first_party_pp == (34, 30, 30, 11)
    assert opponent_text_pulses == 0
    assert [
        action.kind for action in runtime.actions if action.kind is MacroActionKind.CONFIRM
    ] == [MacroActionKind.CONFIRM] * 4


def test_pp_proof_waits_out_delayed_move_menu_without_confirming_twice() -> None:
    runtime = FakeRuntime()
    delayed_waits = 0

    def delay_menu_cleanup(action: MacroAction) -> None:
        nonlocal delayed_waits
        if action.kind is MacroActionKind.CONFIRM:
            if runtime.menu.phase is BattleMenuPhase.MAIN:
                runtime.menu = BattleMenuState(
                    BattleMenuPhase.MOVE,
                    selected_move_slot=1,
                )
                return
            if runtime.menu.phase is BattleMenuPhase.MOVE:
                runtime.raw = replace(
                    runtime.raw,
                    first_party_pp=(34, 30, 30, 11),
                )
                return
        if (
            action.kind is MacroActionKind.WAIT
            and runtime.menu.phase is BattleMenuPhase.MOVE
            and runtime.raw.first_party_pp == (34, 30, 30, 11)
        ):
            delayed_waits += 1
            if delayed_waits == 3:
                runtime.raw = replace(runtime.raw, battle_state=0)
                runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
                runtime.controls = READY

    runtime.on_action = delay_menu_cleanup
    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        lambda _raw: 1,
        expected_map=MapId.CERULEAN_CITY,
        timing=replace(BattleRuntimeTiming(), required_ready_reads=1),
    )

    assert final.battle_state == 0
    assert delayed_waits == 3
    assert sum(action.kind is MacroActionKind.CONFIRM for action in runtime.actions) == 2


def test_last_pp_can_be_spent_when_decrement_reaches_zero() -> None:
    runtime = FakeRuntime(raw=_raw(pp=(1, 30, 30, 11)))

    def finish_on_attack(action: MacroAction) -> None:
        if action.kind is not MacroActionKind.CONFIRM:
            return
        if runtime.menu.phase is BattleMenuPhase.MAIN:
            runtime.menu = BattleMenuState(
                BattleMenuPhase.MOVE,
                selected_move_slot=1,
            )
            return
        if runtime.menu.phase is BattleMenuPhase.MOVE:
            runtime.raw = replace(
                runtime.raw,
                battle_state=0,
                first_party_pp=(0, 30, 30, 11),
            )
            runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
            runtime.controls = READY

    runtime.on_action = finish_on_attack
    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        lambda _raw: 1,
        expected_map=MapId.CERULEAN_CITY,
        timing=replace(BattleRuntimeTiming(), required_ready_reads=1),
    )

    assert final.first_party_pp == (0, 30, 30, 11)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (_raw(battle_state=1), "wild battle"),
        (_raw(battle_state=0), "must start"),
        (_raw(map_id=MapId.ROUTE_24), "left expected map"),
        (_raw(hp=0), "active battler fainted"),
        (_raw(party_count=0, hp=None), "lacks living active-battler evidence"),
    ],
)
def test_initial_gate_fails_closed(
    raw: RawGameState,
    message: str,
) -> None:
    runtime = FakeRuntime(raw=raw)

    with pytest.raises(BattleRuntimeError, match=message):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
        )

    assert runtime.actions == []


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ({"battle_state": 1}, "wild battle"),
        ({"map_id": MapId.ROUTE_24}, "left expected map"),
        ({"first_party_hp": 0}, "active battler fainted"),
    ],
)
def test_runtime_gate_rechecks_wild_map_and_hp_after_every_pulse(
    replacement: dict[str, int | MapId],
    message: str,
) -> None:
    runtime = FakeRuntime(menu=BattleMenuState(BattleMenuPhase.UNKNOWN))

    def corrupt_after_confirm(action: MacroAction) -> None:
        if action.kind is MacroActionKind.CONFIRM:
            runtime.raw = replace(runtime.raw, **replacement)

    runtime.on_action = corrupt_after_confirm

    with pytest.raises(BattleRuntimeError, match=message):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
        )


@pytest.mark.parametrize(
    "menu",
    [
        BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=9),
        BattleMenuState(
            BattleMenuPhase.MAIN,
            selected_main_command=0,
            selected_move_slot=1,
        ),
        BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=0),
        BattleMenuState(
            BattleMenuPhase.UNKNOWN,
            selected_main_command=0,
        ),
    ],
)
def test_invalid_semantic_menu_fails_closed(menu: BattleMenuState) -> None:
    runtime = FakeRuntime(menu=menu)

    with pytest.raises(BattleRuntimeError, match="invalid semantic battle menu"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
        )

    assert runtime.actions == []


def test_unlatched_move_menu_is_cancelled_before_policy_or_pp_change() -> None:
    runtime = FakeRuntime(menu=BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1))
    policy_observations: list[tuple[BattleMenuPhase, tuple[int, ...] | None]] = []

    def on_action(action: MacroAction) -> None:
        if action.kind is MacroActionKind.WAIT:
            return
        if action.kind is MacroActionKind.CANCEL:
            runtime.menu = BattleMenuState(
                BattleMenuPhase.MAIN,
                selected_main_command=0,
            )
            return
        if runtime.menu.phase is BattleMenuPhase.MAIN:
            runtime.menu = BattleMenuState(
                BattleMenuPhase.MOVE,
                selected_move_slot=1,
            )
            return
        pp = list(runtime.raw.first_party_pp or ())
        pp[0] -= 1
        runtime.raw = replace(
            runtime.raw,
            battle_state=0,
            enemy_hp=0,
            first_party_pp=tuple(pp),
        )
        runtime.controls = READY

    runtime.on_action = on_action

    def policy(raw: RawGameState) -> int:
        policy_observations.append((runtime.menu.phase, raw.first_party_pp))
        return 1

    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        policy,
        expected_map=MapId.CERULEAN_CITY,
    )

    assert final.battle_state == 0
    assert policy_observations == [(BattleMenuPhase.MAIN, (35, 30, 30, 11))]
    non_wait = _non_wait_actions(runtime)
    assert non_wait[0] == MacroAction(MacroActionKind.CANCEL)
    assert final.first_party_pp == (34, 30, 30, 11)


def test_unknown_menu_is_bounded_dialogue_not_unbounded_button_spam() -> None:
    runtime = FakeRuntime(menu=BattleMenuState(BattleMenuPhase.UNKNOWN))
    timing = replace(BattleRuntimeTiming(), max_runtime_pulses=3)

    with pytest.raises(BattleRuntimeTimeoutError, match="bounded runtime pulses"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
            timing=timing,
        )

    assert [action.kind for action in runtime.actions] == [
        MacroActionKind.CONFIRM,
        MacroActionKind.WAIT,
        MacroActionKind.CONFIRM,
        MacroActionKind.WAIT,
        MacroActionKind.CANCEL,
        MacroActionKind.WAIT,
    ]


def test_opted_in_zero_pp_main_snapshot_is_confirmed_as_move_learning_dialogue() -> None:
    runtime = FakeRuntime(raw=_raw(pp=(0, 0, 0, 0)))
    policy_calls = 0

    def on_action(action: MacroAction) -> None:
        if action.kind is MacroActionKind.WAIT:
            return
        if runtime.raw.first_party_pp == (0, 0, 0, 0):
            assert action.kind is MacroActionKind.CONFIRM
            runtime.raw = replace(runtime.raw, first_party_pp=(5, 15, 10, 15))
            return
        if runtime.menu.phase is BattleMenuPhase.MAIN:
            runtime.menu = BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1)
            return
        runtime.raw = replace(runtime.raw, battle_state=0, enemy_hp=0)
        runtime.controls = READY

    def policy(_raw: RawGameState) -> int:
        nonlocal policy_calls
        policy_calls += 1
        return 1

    runtime.on_action = on_action
    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        policy,
        expected_map=MapId.CERULEAN_CITY,
        transient_zero_pp_main_is_dialogue=True,
    )

    assert final.battle_state == 0
    assert policy_calls == 1
    assert _non_wait_actions(runtime)[0] == MacroAction(MacroActionKind.CONFIRM)


def test_status_suppressed_turn_can_return_without_spending_pp() -> None:
    runtime = FakeRuntime(raw=replace(_raw(), first_party_status=0x40))
    confirmations = 0

    def suppress_then_finish(action: MacroAction) -> None:
        nonlocal confirmations
        if action.kind is not MacroActionKind.CONFIRM:
            return
        confirmations += 1
        if confirmations == 1:
            runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
        else:
            runtime.raw = replace(runtime.raw, battle_state=0)
            runtime.controls = READY

    runtime.on_action = suppress_then_finish
    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        lambda _raw: 1,
        expected_map=MapId.CERULEAN_CITY,
    )

    assert final.battle_state == 0
    assert final.first_party_pp == (35, 30, 30, 11)


def test_enemy_trapping_turn_can_suppress_move_selection_without_spending_pp() -> None:
    runtime = FakeRuntime(raw=replace(_raw(), enemy_using_trapping_move=True))
    confirmations = 0

    def trap_then_finish(action: MacroAction) -> None:
        nonlocal confirmations
        if action.kind is not MacroActionKind.CONFIRM:
            return
        confirmations += 1
        if confirmations == 1:
            runtime.raw = replace(runtime.raw, enemy_using_trapping_move=False)
            runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
        else:
            runtime.raw = replace(
                runtime.raw,
                battle_state=0,
                enemy_using_trapping_move=None,
            )
            runtime.controls = READY

    runtime.on_action = trap_then_finish
    final = run_adaptive_trainer_battle(
        runtime,
        runtime,
        lambda _raw: 1,
        expected_map=MapId.CERULEAN_CITY,
    )

    assert final.battle_state == 0
    assert final.first_party_pp == (35, 30, 30, 11)


def test_faster_opponent_disable_suppresses_selected_turn_without_pp() -> None:
    runtime = FakeRuntime(menu=BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1))
    initial = runtime.raw

    def disable_selected_move(action: MacroAction) -> None:
        if action.kind is MacroActionKind.CONFIRM:
            runtime.raw = replace(
                runtime.raw,
                player_disabled_move_slot=1,
                player_disable_turns=3,
            )
            runtime.menu = BattleMenuState(
                BattleMenuPhase.MAIN,
                selected_main_command=0,
            )

    runtime.on_action = disable_selected_move
    _confirm_attack_with_pp_gate(
        runtime,
        runtime,
        expected_map=MapId.CERULEAN_CITY,
        initial_raw=initial,
        slot=1,
        initial_pp=35,
        timing=BattleRuntimeTiming(),
        label="faster Disable",
    )

    assert runtime.raw.first_party_pp == initial.first_party_pp
    assert runtime.raw.player_disabled_move_slot == 1


def test_faster_opponent_trapping_move_suppresses_selected_turn_without_pp() -> None:
    runtime = FakeRuntime(menu=BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1))
    initial = runtime.raw

    def trap_before_selected_move(action: MacroAction) -> None:
        if action.kind is MacroActionKind.CONFIRM:
            runtime.raw = replace(runtime.raw, enemy_using_trapping_move=True)
            runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)

    runtime.on_action = trap_before_selected_move
    _confirm_attack_with_pp_gate(
        runtime,
        runtime,
        expected_map=MapId.CERULEAN_CITY,
        initial_raw=initial,
        slot=1,
        initial_pp=35,
        timing=BattleRuntimeTiming(),
        label="faster trapping move",
    )

    assert runtime.raw.first_party_pp == initial.first_party_pp
    assert runtime.raw.enemy_using_trapping_move is True


def test_pp_proof_accepts_an_observed_level_up_move_replacement() -> None:
    runtime = FakeRuntime(menu=BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1))
    initial = runtime.raw
    confirmations = 0

    def learn_move_after_attack(action: MacroAction) -> None:
        nonlocal confirmations
        if action.kind is not MacroActionKind.CONFIRM:
            return
        confirmations += 1
        if confirmations == 1:
            runtime.raw = replace(runtime.raw, first_party_pp=(34, 30, 30, 11))
            runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
        else:
            runtime.raw = replace(
                runtime.raw,
                first_party_moves=(0x38, TAIL_WHIP_MOVE_ID, MEGA_PUNCH_MOVE_ID, WATER_GUN_MOVE_ID),
                first_party_pp=(5, 30, 30, 11),
            )

    runtime.on_action = learn_move_after_attack
    _confirm_attack_with_pp_gate(
        runtime,
        runtime,
        expected_map=MapId.CERULEAN_CITY,
        initial_raw=initial,
        slot=1,
        initial_pp=35,
        timing=BattleRuntimeTiming(),
        label="level-up move replacement",
    )

    assert runtime.raw.first_party_moves[0] == 0x38
    assert runtime.raw.first_party_pp[0] == 5


def test_pp_proof_accepts_move_replacement_inside_the_first_accelerated_wait() -> None:
    runtime = FakeRuntime(menu=BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1))
    initial = runtime.raw

    def learn_move_during_wait(action: MacroAction) -> None:
        if action.kind is MacroActionKind.CONFIRM:
            runtime.raw = replace(
                runtime.raw,
                battle_state=0,
                first_party_moves=(0x82, TAIL_WHIP_MOVE_ID, MEGA_PUNCH_MOVE_ID, WATER_GUN_MOVE_ID),
                first_party_pp=(15, 30, 30, 11),
            )
            runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)

    runtime.on_action = learn_move_during_wait
    _confirm_attack_with_pp_gate(
        runtime,
        runtime,
        expected_map=MapId.CERULEAN_CITY,
        initial_raw=initial,
        slot=1,
        initial_pp=35,
        timing=BattleRuntimeTiming(),
        label="accelerated level-up move replacement",
    )

    assert runtime.raw.first_party_moves[0] == 0x82
    assert runtime.raw.first_party_pp[0] == 15


def test_completion_rechecks_living_lead_before_returning() -> None:
    runtime = FakeRuntime(
        raw=_raw(battle_state=0, hp=0),
        controls=READY,
    )

    with pytest.raises(BattleRuntimeError, match="active battler fainted"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=MapId.CERULEAN_CITY,
        )


def test_terminal_enemy_ko_precedes_a_stale_fainted_party_lead_view() -> None:
    _require_present_state(
        _raw(battle_state=2, hp=0, enemy_hp=0),
        expected_map=MapId.CERULEAN_CITY,
        label="forced-party final KO",
    )


def test_recovery_gate_requires_an_actor_decision_between_items() -> None:
    assert recovery_action_due(
        hp=40,
        status=0,
        safe_hp=100,
        decisions_made=5,
        last_recovery_decision=4,
    )
    assert not recovery_action_due(
        hp=40,
        status=0,
        safe_hp=100,
        decisions_made=5,
        last_recovery_decision=5,
    )
    assert not recovery_action_due(
        hp=120,
        status=0x40,
        safe_hp=100,
        decisions_made=5,
        last_recovery_decision=5,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dialogue_wait_frames", 0),
        ("max_runtime_pulses", False),
        ("required_ready_reads", -1),
    ],
)
def test_timing_requires_positive_integer_fields(field: str, value: int) -> None:
    with pytest.raises(ValueError, match=field):
        BattleRuntimeTiming(**{field: value})


@pytest.mark.parametrize("expected_map", [-1, 0x100, True])
def test_expected_map_requires_an_unsigned_byte(expected_map: int) -> None:
    runtime = FakeRuntime()

    with pytest.raises(ValueError, match="unsigned one-byte"):
        run_adaptive_trainer_battle(
            runtime,
            runtime,
            lambda _raw: 1,
            expected_map=expected_map,
        )
