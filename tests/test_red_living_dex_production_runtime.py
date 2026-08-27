from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path

import pytest

from pokemon_red_completion import red_living_dex_production_runtime as runtime
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.red_living_dex_production_runtime import (
    RED_LIVING_DEX_RUNTIME_FACTORY_SHA256,
    RED_LIVING_DEX_TITLE_ADAPTER_SHA256,
    RedLivingDexProductionRuntimeError,
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
    def __init__(self, emulator: runtime._MeteredEmulator) -> None:
        self.emulator = emulator

    def execute(self, _action: MacroAction) -> None:
        self.emulator.tick(7)
        raise RuntimeError("delegate failed")


class _TickThenSucceed:
    def __init__(self, emulator: runtime._MeteredEmulator) -> None:
        self.emulator = emulator

    def execute(self, action: MacroAction) -> MacroAction:
        self.emulator.tick(5)
        return action


def test_action_is_reserved_and_frames_are_reconciled_when_delegate_fails() -> None:
    meter = RedLivingDexSetupEffectMeter()
    emulator = runtime._MeteredEmulator(_FakeEmulator(), meter)
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
    emulator = runtime._MeteredEmulator(_FakeEmulator(), meter)
    attempted = runtime._AttemptMeteredActionExecutor(
        _TickThenSucceed(emulator),
        emulator=emulator,
        meter=meter,
    )
    counted = CountingExecutor(attempted)  # type: ignore[arg-type]

    counted.execute(MacroAction(MacroActionKind.MOVE, "right"))

    assert counted.actions_executed == meter.controller_actions == 1
    assert meter.emulator_frames == 5


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
