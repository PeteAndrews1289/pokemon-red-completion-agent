from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.surge as surge_module
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.observation import (
    Badge,
    BattleMenuPhase,
    BattleMenuState,
    ItemId,
    MapId,
    RawGameState,
)
from pokemon_red_completion.surge import (
    SurgeChapterError,
    _ordinary_capture_ball_total,
    _try_catch_wild,
)


def _base_raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_15,
        player_x=14,
        player_y=9,
        party_count=2,
        battle_state=1,
        badge_bits=int(Badge.BOULDER | Badge.CASCADE | Badge.THUNDER),
        party_species_ids=(0xB3, 0x40),
        first_party_hp=48,
        first_party_max_hp=73,
        first_party_status=0,
        first_party_moves=(44, 89, 145, 55),
        first_party_pp=(25, 7, 30, 25),
        enemy_species_id=0x15,
        enemy_level=20,
        enemy_hp=30,
        enemy_max_hp=30,
    )


class _StatefulBattleSimulator:
    """Distinguish escape invocation from observation after the exit."""

    _GRID: dict[tuple[int, str | int | None], int] = {
        (0, "down"): 1,
        (0, "right"): 2,
        (1, "up"): 0,
        (1, "right"): 3,
        (2, "left"): 0,
        (2, "down"): 3,
        (3, "up"): 2,
        (3, "left"): 1,
    }

    def __init__(
        self,
        *,
        battle_state: int = 1,
        bag: dict[int, int] | None = None,
        box_counts: tuple[int, ...] = (0,) * 12,
        escape_attempt: int | None = 1,
        escape_fails_to_clear_battle: bool = False,
        mutate_specimens_on_escape: bool = False,
        mutate_balls_on_escape: bool = False,
        capture_on_throw: bool = False,
    ) -> None:
        self.raw = replace(_base_raw(), battle_state=battle_state)
        self.bag = dict(bag if bag is not None else {})
        self.box_counts = list(box_counts)
        self.escape_attempt = escape_attempt
        self.escape_fails_to_clear_battle = escape_fails_to_clear_battle
        self.mutate_specimens_on_escape = mutate_specimens_on_escape
        self.mutate_balls_on_escape = mutate_balls_on_escape
        self.capture_on_throw = capture_on_throw
        self.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)
        self.actions: list[MacroAction] = []
        self.attempts = 0
        self.dialogue_pulses = 0
        self.throw_confirmations = 0

    def read(self) -> RawGameState:
        return self.raw

    def read_battle_menu_state(self, _raw: RawGameState) -> BattleMenuState:
        return self.menu

    def read_all_box_states(self) -> SimpleNamespace:
        return SimpleNamespace(counts=tuple(self.box_counts))

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)
        if action.kind is MacroActionKind.WAIT:
            return
        if action.kind is MacroActionKind.MOVE:
            if (
                self.menu.phase is BattleMenuPhase.MAIN
                and self.menu.selected_main_command is not None
            ):
                next_cmd = self._GRID.get((self.menu.selected_main_command, action.value))
                if next_cmd is not None:
                    self.menu = BattleMenuState(
                        BattleMenuPhase.MAIN, selected_main_command=next_cmd
                    )
            return
        if action.kind is MacroActionKind.CONFIRM:
            if self.menu.phase is BattleMenuPhase.MAIN and self.menu.selected_main_command == 3:
                self.attempts += 1
                self.dialogue_pulses = 2
                self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
                return
            if self.menu.phase is BattleMenuPhase.MAIN and self.menu.selected_main_command == 1:
                # Bag item selection confirmation during throw
                self.throw_confirmations += 1
                if self.throw_confirmations % 2 == 0:
                    for ball_id in (ItemId.POKE_BALL, ItemId.GREAT_BALL, ItemId.ULTRA_BALL):
                        if self.bag.get(ball_id, 0) > 0:
                            self.bag[ball_id] -= 1
                            break
                    if self.capture_on_throw:
                        self.raw = replace(self.raw, battle_state=0)
                        self.box_counts[0] += 1
                return
        if action.kind is MacroActionKind.CANCEL and self.menu.phase is BattleMenuPhase.UNKNOWN:
            self.dialogue_pulses -= 1
            if self.dialogue_pulses <= 0:
                if self.escape_attempt is not None and self.attempts >= self.escape_attempt:
                    if not self.escape_fails_to_clear_battle:
                        self.raw = replace(self.raw, battle_state=0)
                    if self.mutate_specimens_on_escape:
                        self.box_counts[0] += 1
                    if self.mutate_balls_on_escape:
                        self.bag[ItemId.POKE_BALL] = self.bag.get(ItemId.POKE_BALL, 0) + 1
                else:
                    self.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=3)
            return


def test_no_balls_initially_escapes_to_field_and_raises_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulator = _StatefulBattleSimulator(bag={ItemId.POKE_BALL: 0, ItemId.GREAT_BALL: 0})
    executor = CountingExecutor(simulator)
    monkeypatch.setattr(surge_module, "_bag", lambda _emulator: simulator.bag)

    with pytest.raises(SurgeChapterError, match="no ordinary capture balls remaining"):
        _try_catch_wild(
            simulator,  # type: ignore[arg-type]
            executor,
            simulator,  # type: ignore[arg-type]
            0x15,
            "Route 15 no-balls initial",
            max_throws=5,
        )

    # Verified safe field boundary reached before raising
    assert simulator.raw.battle_state == 0
    assert simulator.attempts == 1
    assert _ordinary_capture_ball_total(simulator.bag) == 0
    assert sum(simulator.box_counts) == 0
    assert any(action.kind is MacroActionKind.CONFIRM for action in simulator.actions)


def test_exhausted_balls_flee_preserves_field_boundary_before_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulator = _StatefulBattleSimulator(bag={ItemId.POKE_BALL: 0})
    executor = CountingExecutor(simulator)
    monkeypatch.setattr(surge_module, "_bag", lambda _emulator: simulator.bag)

    with pytest.raises(
        SurgeChapterError,
        match="Route 15 boundary check capture has no ordinary capture balls remaining",
    ):
        _try_catch_wild(
            simulator,  # type: ignore[arg-type]
            executor,
            simulator,  # type: ignore[arg-type]
            0x15,
            "Route 15 boundary check",
            max_throws=5,
        )

    # Battle was safely exited to the field before raising the original exception
    assert simulator.raw.battle_state == 0
    assert simulator.attempts == 1
    assert executor.actions_executed > 0


def test_exhausted_after_previous_encounter_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulator = _StatefulBattleSimulator(
        bag={ItemId.POKE_BALL: 1},
        capture_on_throw=False,
    )
    executor = CountingExecutor(simulator)
    monkeypatch.setattr(surge_module, "_bag", lambda _emulator: simulator.bag)
    monkeypatch.setattr(surge_module, "_select_bag_item", lambda *_args: None)
    monkeypatch.setattr(surge_module, "_confirm_kind", lambda *_args: None)

    # First encounter: throw single ball, fail catch, flee successfully
    first_result = _try_catch_wild(
        simulator,  # type: ignore[arg-type]
        executor,
        simulator,  # type: ignore[arg-type]
        0x15,
        "Encounter 1",
        max_throws=1,
    )
    assert first_result is False
    assert simulator.bag[ItemId.POKE_BALL] == 0
    assert simulator.raw.battle_state == 0

    # Second encounter: triggered with 0 balls remaining from previous encounter
    simulator.raw = replace(simulator.raw, battle_state=1)
    simulator.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)
    simulator.attempts = 0
    simulator.dialogue_pulses = 0
    simulator.throw_confirmations = 0

    with pytest.raises(SurgeChapterError, match="no ordinary capture balls remaining"):
        _try_catch_wild(
            simulator,  # type: ignore[arg-type]
            executor,
            simulator,  # type: ignore[arg-type]
            0x15,
            "Encounter 2",
            max_throws=5,
        )
    assert simulator.bag[ItemId.POKE_BALL] == 0
    assert simulator.raw.battle_state == 0
    assert simulator.attempts == 1


def test_successful_escape_distinguishes_invocation_and_observe_after_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulator = _StatefulBattleSimulator(bag={}, escape_attempt=2)
    executor = CountingExecutor(simulator)
    monkeypatch.setattr(surge_module, "_bag", lambda _emulator: simulator.bag)

    with pytest.raises(SurgeChapterError, match="no ordinary capture balls remaining"):
        _try_catch_wild(
            simulator,  # type: ignore[arg-type]
            executor,
            simulator,  # type: ignore[arg-type]
            0x15,
            "Multi-attempt flee",
            max_throws=5,
        )

    assert simulator.attempts == 2
    assert simulator.raw.battle_state == 0
    assert executor.actions_executed > 0


def test_escape_failure_bounded_run_attempts_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulator = _StatefulBattleSimulator(bag={}, escape_attempt=None)
    executor = CountingExecutor(simulator)
    monkeypatch.setattr(surge_module, "_bag", lambda _emulator: simulator.bag)

    with pytest.raises(SurgeChapterError, match="bounded RUN attempts"):
        _try_catch_wild(
            simulator,  # type: ignore[arg-type]
            executor,
            simulator,  # type: ignore[arg-type]
            0x15,
            "Bounded flee failure",
            max_throws=5,
        )

    assert simulator.attempts == 16
    assert simulator.raw.battle_state == 1


def test_escape_failure_when_battle_remains_active_post_flee(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulator = _StatefulBattleSimulator(bag={})
    executor = CountingExecutor(simulator)
    monkeypatch.setattr(surge_module, "_bag", lambda _emulator: simulator.bag)
    # Stub _flee returning without clearing battle_state
    monkeypatch.setattr(surge_module, "_flee", lambda *_args: None)

    with pytest.raises(SurgeChapterError, match="flee did not end the encounter"):
        _try_catch_wild(
            simulator,  # type: ignore[arg-type]
            executor,
            simulator,  # type: ignore[arg-type]
            0x15,
            "Uncleared battle",
            max_throws=5,
        )


def test_no_balls_escape_rejects_changed_specimens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulator = _StatefulBattleSimulator(bag={}, mutate_specimens_on_escape=True)
    executor = CountingExecutor(simulator)
    monkeypatch.setattr(surge_module, "_bag", lambda _emulator: simulator.bag)

    with pytest.raises(SurgeChapterError, match="no-balls exit changed the living collection"):
        _try_catch_wild(
            simulator,  # type: ignore[arg-type]
            executor,
            simulator,  # type: ignore[arg-type]
            0x15,
            "Specimen tamper",
            max_throws=5,
        )


def test_no_balls_escape_rejects_changed_balls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulator = _StatefulBattleSimulator(bag={}, mutate_balls_on_escape=True)
    executor = CountingExecutor(simulator)
    monkeypatch.setattr(surge_module, "_bag", lambda _emulator: simulator.bag)

    with pytest.raises(SurgeChapterError, match="no-balls exit changed ordinary-ball accounting"):
        _try_catch_wild(
            simulator,  # type: ignore[arg-type]
            executor,
            simulator,  # type: ignore[arg-type]
            0x15,
            "Ball tamper",
            max_throws=5,
        )


def test_trainer_battle_refusal_without_balls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulator = _StatefulBattleSimulator(battle_state=2, bag={})
    executor = CountingExecutor(simulator)
    monkeypatch.setattr(surge_module, "_bag", lambda _emulator: simulator.bag)

    with pytest.raises(SurgeChapterError, match="trainer battle"):
        _try_catch_wild(
            simulator,  # type: ignore[arg-type]
            executor,
            simulator,  # type: ignore[arg-type]
            0x15,
            "Trainer battle check",
            max_throws=5,
        )

    # Never attempted to flee or input in a trainer battle
    assert simulator.attempts == 0
    assert len(simulator.actions) == 0


def test_trainer_battle_refusal_with_balls_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulator = _StatefulBattleSimulator(battle_state=2, bag={ItemId.POKE_BALL: 5})
    executor = CountingExecutor(simulator)
    monkeypatch.setattr(surge_module, "_bag", lambda _emulator: simulator.bag)

    with pytest.raises(SurgeChapterError, match="trainer battle"):
        _try_catch_wild(
            simulator,  # type: ignore[arg-type]
            executor,
            simulator,  # type: ignore[arg-type]
            0x15,
            "Trainer battle with balls",
            max_throws=5,
        )

    # Input rejected before attempting battle menu navigation
    assert simulator.attempts == 0
    assert len(simulator.actions) == 0


def test_refusal_when_not_in_battle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulator = _StatefulBattleSimulator(battle_state=0, bag={})
    executor = CountingExecutor(simulator)
    monkeypatch.setattr(surge_module, "_bag", lambda _emulator: simulator.bag)

    with pytest.raises(SurgeChapterError, match="no live encounter"):
        _try_catch_wild(
            simulator,  # type: ignore[arg-type]
            executor,
            simulator,  # type: ignore[arg-type]
            0x15,
            "Not in battle",
            max_throws=5,
        )

    assert simulator.attempts == 0
    assert len(simulator.actions) == 0


def test_master_ball_is_never_used_as_ordinary_capture_ball(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulator = _StatefulBattleSimulator(bag={ItemId.MASTER_BALL: 1})
    executor = CountingExecutor(simulator)
    monkeypatch.setattr(surge_module, "_bag", lambda _emulator: simulator.bag)

    with pytest.raises(SurgeChapterError, match="no ordinary capture balls remaining"):
        _try_catch_wild(
            simulator,  # type: ignore[arg-type]
            executor,
            simulator,  # type: ignore[arg-type]
            0x15,
            "Master ball test",
            max_throws=5,
        )

    assert simulator.bag[ItemId.MASTER_BALL] == 1
    assert simulator.raw.battle_state == 0
    assert simulator.attempts == 1


def test_existing_valid_capture_behavior_remains_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulator = _StatefulBattleSimulator(
        bag={ItemId.POKE_BALL: 3},
        capture_on_throw=True,
    )
    executor = CountingExecutor(simulator)
    monkeypatch.setattr(surge_module, "_bag", lambda _emulator: simulator.bag)
    monkeypatch.setattr(surge_module, "_select_bag_item", lambda *_args: None)
    monkeypatch.setattr(surge_module, "_confirm_kind", lambda *_args: None)

    captured = _try_catch_wild(
        simulator,  # type: ignore[arg-type]
        executor,
        simulator,  # type: ignore[arg-type]
        0x15,
        "Valid capture test",
        max_throws=5,
    )

    assert captured is True
    assert simulator.bag[ItemId.POKE_BALL] == 2
    assert simulator.box_counts[0] == 1
    assert simulator.raw.battle_state == 0


def test_existing_throw_exhaustion_flee_remains_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulator = _StatefulBattleSimulator(
        bag={ItemId.POKE_BALL: 2},
        capture_on_throw=False,
    )
    executor = CountingExecutor(simulator)
    monkeypatch.setattr(surge_module, "_bag", lambda _emulator: simulator.bag)
    monkeypatch.setattr(surge_module, "_select_bag_item", lambda *_args: None)
    monkeypatch.setattr(surge_module, "_confirm_kind", lambda *_args: None)

    captured = _try_catch_wild(
        simulator,  # type: ignore[arg-type]
        executor,
        simulator,  # type: ignore[arg-type]
        0x15,
        "Throw exhaustion flee test",
        max_throws=2,
    )

    assert captured is False
    assert simulator.bag[ItemId.POKE_BALL] == 0
    assert simulator.raw.battle_state == 0
    assert simulator.attempts == 1
