from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path

import pytest

from pokemon_red_completion import red_living_dex_production_runtime as runtime
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.emulator import CausallyMeteredEmulator
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.red_living_dex_production_runtime import (
    RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
    RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
    RedLivingDexProductionRuntimeError,
    RedLivingDexProductionRuntimeLimits,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexSetupEffectMeter,
)


class _FakeEmulator:
    def __init__(self, *, start_frames: int = 0, fail_start: bool = False) -> None:
        self.frame_count = 0
        self.pressed_buttons: frozenset[str] = frozenset()
        self.start_frames = start_frames
        self.fail_start = fail_start
        self.closed = 0
        self.payload = b"state"

    def start(self) -> _FakeEmulator:
        self.frame_count += self.start_frames
        if self.fail_start:
            raise RuntimeError("start failed")
        return self

    def close(self) -> None:
        self.closed += 1

    def tick(self, frames: int) -> None:
        self.frame_count += frames

    def press(self, button: str) -> None:
        self.pressed_buttons = self.pressed_buttons.union({button})

    def release(self, button: str) -> None:
        self.pressed_buttons = self.pressed_buttons.difference({button})

    def load_state_bytes(self, payload: bytes) -> None:
        self.payload = payload

    def save_state_bytes(self) -> bytes:
        return self.payload

    def read_u8(self, _address: int) -> int:
        return 0

    def read_cartridge_ram_u8(self, _bank: int, _address: int) -> int:
        return 0


class _TickThenFail:
    def __init__(self, emulator: CausallyMeteredEmulator) -> None:
        self.emulator = emulator

    def execute(self, _action: MacroAction) -> None:
        self.emulator.tick(7)
        raise RuntimeError("delegate failed")


class _TickThenSucceed:
    def __init__(self, emulator: CausallyMeteredEmulator) -> None:
        self.emulator = emulator

    def execute(self, action: MacroAction) -> MacroAction:
        self.emulator.tick(5)
        return action


def test_action_is_reserved_and_frames_are_reconciled_when_delegate_fails() -> None:
    meter = RedLivingDexSetupEffectMeter()
    emulator = runtime._build_metered_emulator(_FakeEmulator(), meter)
    attempted = runtime._AttemptMeteredActionExecutor(
        _TickThenFail(emulator),
        emulator=emulator,
        meter=meter,
    )
    counted = CountingExecutor(attempted)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="delegate failed"):
        counted.execute(MacroAction(MacroActionKind.MOVE, "up"))

    assert meter.controller_actions == 1
    assert meter.emulator_frames == 7
    assert counted.actions_executed == 0


def test_successful_action_has_identical_validator_and_effect_counts() -> None:
    meter = RedLivingDexSetupEffectMeter()
    emulator = runtime._build_metered_emulator(_FakeEmulator(), meter)
    attempted = runtime._AttemptMeteredActionExecutor(
        _TickThenSucceed(emulator),
        emulator=emulator,
        meter=meter,
    )
    counted = CountingExecutor(attempted)  # type: ignore[arg-type]

    counted.execute(MacroAction(MacroActionKind.MOVE, "right"))

    assert counted.actions_executed == meter.controller_actions == 1
    assert meter.emulator_frames == 5


def test_process_wide_limits_reject_input_before_it_crosses_the_boundary() -> None:
    limits = RedLivingDexProductionRuntimeLimits(
        maximum_controller_actions=1,
        maximum_emulator_frames=5,
    )
    meter = RedLivingDexSetupEffectMeter()
    raw = _FakeEmulator()
    emulator = runtime._build_metered_emulator(raw, meter, limits=limits)
    attempted = runtime._AttemptMeteredActionExecutor(
        _TickThenSucceed(emulator),
        emulator=emulator,
        meter=meter,
        limits=limits,
    )

    attempted.execute(MacroAction(MacroActionKind.MOVE, "right"))
    with pytest.raises(RedLivingDexProductionRuntimeError, match="action bound"):
        attempted.execute(MacroAction(MacroActionKind.MOVE, "left"))
    with pytest.raises(RedLivingDexProductionRuntimeError, match="frame bound"):
        emulator.tick(1)

    assert raw.frame_count == 5
    assert meter.controller_actions == 1
    assert meter.emulator_frames == 5


def test_frame_observer_projects_fresh_emulators_onto_one_monotonic_timeline() -> None:
    class Observer:
        def __init__(self) -> None:
            self.requested: list[int] = []
            self.published: list[int] = []

        def wants_frame(self, logical_frame: int) -> bool:
            self.requested.append(logical_frame)
            return True

        def publish_frame(
            self,
            _width: int,
            _height: int,
            _rgb: bytes,
            logical_frame: int,
        ) -> None:
            self.published.append(logical_frame)

    observer = Observer()
    meter = RedLivingDexSetupEffectMeter()
    meter.record_emulator_frames(120)
    translated = runtime._MeteredFrameObserver(observer, meter=meter)

    assert translated.wants_frame(7) is True
    translated.publish_frame(1, 1, b"\x00\x00\x00", 7)

    assert observer.requested == [127]
    assert observer.published == [127]

    meter.record_emulator_frames(7)
    next_emulator = runtime._MeteredFrameObserver(observer, meter=meter)
    assert next_emulator.wants_frame(2) is True
    next_emulator.publish_frame(1, 1, b"\x00\x00\x00", 2)
    assert observer.requested == [127, 129]
    assert observer.published == [127, 129]


def test_frame_observer_failure_cannot_change_controller_execution() -> None:
    class BrokenObserver:
        def wants_frame(self, _logical_frame: int) -> bool:
            raise RuntimeError("dashboard closed")

        def publish_frame(
            self,
            _width: int,
            _height: int,
            _rgb: bytes,
            _logical_frame: int,
        ) -> None:
            raise RuntimeError("dashboard closed")

    meter = RedLivingDexSetupEffectMeter()
    translated = runtime._MeteredFrameObserver(BrokenObserver(), meter=meter)

    assert translated.wants_frame(5) is False
    assert translated.wants_frame(10) is False
    translated.publish_frame(1, 1, b"\x00\x00\x00", 10)


@pytest.mark.parametrize("exception", (None, RuntimeError("ordinary"), KeyboardInterrupt()))
def test_recipe_scope_closes_every_registered_arm_for_all_exit_kinds(
    exception: BaseException | None,
) -> None:
    first = _FakeEmulator()
    second = _FakeEmulator()
    stack = ExitStack()
    runtime._register_emulator(stack, first)
    runtime._register_emulator(stack, second)

    if exception is None:
        stack.__exit__(None, None, None)
    else:
        stack.__exit__(type(exception), exception, exception.__traceback__)

    assert first.closed == 1
    assert second.closed == 1


def test_start_boundary_rejects_hidden_frames_and_registered_failure_closes() -> None:
    changed = _FakeEmulator(start_frames=1)
    with ExitStack() as stack:
        runtime._register_emulator(stack, changed)
        with pytest.raises(RedLivingDexProductionRuntimeError, match="protected effects"):
            runtime._start_emulator(changed)
    assert changed.closed == 1

    failed = _FakeEmulator(fail_start=True)
    with pytest.raises(RuntimeError, match="start failed"), ExitStack() as stack:
        runtime._register_emulator(stack, failed)
        runtime._start_emulator(failed)
    assert failed.closed == 1


def test_runtime_contract_is_path_free_and_provider_execution_is_forbidden() -> None:
    assert len(RED_LIVING_DEX_TITLE_ADAPTER_SHA256) == 64
    assert len(RED_LIVING_DEX_RUNTIME_FACTORY_SHA256) == 64
    with pytest.raises(RedLivingDexProductionRuntimeError, match="never execute"):
        runtime._forbid_provider_execution()
    source = Path(runtime.__file__).read_text(encoding="utf-8")
    assert "teacher_choice" not in source
    assert "model.fit(" not in source
