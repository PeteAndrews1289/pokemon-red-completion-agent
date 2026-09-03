from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from pokemon_red_completion.executor import (
    ControllerFrameBudgetExhausted,
    GoalExecutionBudgetExhausted,
    WindowedFrameBudgetController,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    ActionFreeAdmissionExecutor,
    CompositionActionBudgetExhausted,
    CompositionIndependentBudgetMeter,
    FreshCompositionQualificationError,
    HardCompositionActionLimiter,
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    read_root_claim,
    root_claim_is_available,
    root_consumption_sha256,
    write_root_claim,
)


@dataclass
class _ActionDelegate:
    calls: int = 0
    fail: bool = False

    def execute(self, action: object) -> object:
        self.calls += 1
        if self.fail:
            raise RuntimeError("partial macro")
        return action


@dataclass
class _Controller:
    frame_count: int = 100

    def tick(self, frames: int) -> None:
        self.frame_count += frames


def test_action_limiter_reserves_failed_dispatch_and_refuses_before_overrun() -> None:
    delegate = _ActionDelegate(fail=True)
    limiter = HardCompositionActionLimiter(
        delegate,
        maximum_actions_per_decision=1,
        maximum_episode_actions=2,
    )

    with pytest.raises(RuntimeError, match="partial macro"):
        limiter.execute("first")
    assert limiter.attempted_actions == 1
    assert limiter.completed_actions == 0
    with pytest.raises(CompositionActionBudgetExhausted, match="action budget") as error:
        limiter.execute("second")
    assert isinstance(error.value, GoalExecutionBudgetExhausted)
    assert delegate.calls == 1

    limiter.begin_decision_window()
    delegate.fail = False
    assert limiter.execute("second") == "second"
    with pytest.raises(CompositionActionBudgetExhausted, match="action budget"):
        limiter.execute("third")
    assert delegate.calls == 2


def test_admission_executor_refuses_before_any_controller_delegate_exists() -> None:
    blocker = ActionFreeAdmissionExecutor()

    with pytest.raises(FreshCompositionQualificationError, match="admission"):
        blocker.execute("forbidden")

    assert blocker.attempted_actions == 1


def test_frame_limiter_refuses_tick_before_per_decision_or_episode_overrun() -> None:
    controller = _Controller()
    limiter = WindowedFrameBudgetController(
        controller,
        maximum_frames_per_window=5,
        maximum_total_frames=8,
    )
    limiter.tick(5)
    with pytest.raises(ControllerFrameBudgetExhausted, match="frame budget") as error:
        limiter.tick(1)
    assert isinstance(error.value, GoalExecutionBudgetExhausted)
    assert controller.frame_count == 105

    limiter.begin_window()
    limiter.tick(3)
    with pytest.raises(ControllerFrameBudgetExhausted, match="frame budget"):
        limiter.tick(1)
    assert controller.frame_count == 108


def test_independent_meter_counts_attempts_and_authoritative_frames() -> None:
    action_delegate = _ActionDelegate(fail=True)
    actions = HardCompositionActionLimiter(action_delegate)
    frames = WindowedFrameBudgetController(
        _Controller(),
        maximum_frames_per_window=600_000,
        maximum_total_frames=1_800_000,
    )
    meter = CompositionIndependentBudgetMeter(actions, frames)

    with pytest.raises(RuntimeError):
        actions.execute("partial")
    frames.tick(7)

    assert meter.checkpoint().controller_actions == 1
    assert meter.checkpoint().emulator_frames == 7


def test_root_consumption_identity_is_code_version_independent() -> None:
    first = root_consumption_sha256(
        state_sha256="a" * 64,
        envelope_sha256="b" * 64,
    )
    second = root_consumption_sha256(
        state_sha256="a" * 64,
        envelope_sha256="b" * 64,
    )

    assert first == second
    assert len(first) == 64


def test_fixed_account_registry_is_read_only_exclusive_and_durable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = tmp_path / "claims"
    registry.mkdir(mode=0o700)
    os.chmod(registry, 0o700)
    opened = open_fixed_account_claim_registry(registry)
    identity = "c" * 64
    synced: list[int] = []
    real_fsync = os.fsync

    def note_fsync(descriptor: int) -> None:
        synced.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", note_fsync)
    assert root_claim_is_available(opened, identity)
    write_root_claim(
        opened,
        root_consumption_sha256=identity,
        execution_identity_sha256="d" * 64,
        source_commit="e" * 40,
        runner_sha256="f" * 64,
    )

    assert len(synced) == 2
    assert not root_claim_is_available(opened, identity)
    assert read_root_claim(opened, identity) == {
        "schema": "pokemon.red.fresh-composition-root-claim.v1",
        "root_consumption_sha256": identity,
        "execution_identity_sha256": "d" * 64,
        "source_commit": "e" * 40,
        "runner_sha256": "f" * 64,
    }
    with pytest.raises(FreshCompositionQualificationError, match="already consumed"):
        write_root_claim(
            opened,
            root_consumption_sha256=identity,
            execution_identity_sha256="d" * 64,
            source_commit="e" * 40,
            runner_sha256="f" * 64,
        )


def test_root_claim_reader_rejects_noncanonical_or_unsafe_markers(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "claims"
    registry.mkdir(mode=0o700)
    os.chmod(registry, 0o700)
    identity = "a" * 64
    marker = registry / f"{identity}.json"
    marker.write_text('{"schema": "wrong"}\n', encoding="ascii")
    os.chmod(marker, 0o600)

    with pytest.raises(FreshCompositionQualificationError, match="authenticated"):
        read_root_claim(registry, identity)


def test_fixed_account_registry_must_be_preprovisioned_0700(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(FreshCompositionQualificationError, match="provisioned"):
        open_fixed_account_claim_registry(missing)
    assert not missing.exists()

    invalid = tmp_path / "invalid"
    invalid.mkdir(mode=0o755)
    os.chmod(invalid, 0o755)
    with pytest.raises(FreshCompositionQualificationError, match="invalid"):
        open_fixed_account_claim_registry(invalid)


def test_fixed_account_registry_lease_coordinates_shared_and_exclusive_users(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "claims"
    registry.mkdir(mode=0o700)
    os.chmod(registry, 0o700)

    with (
        fixed_account_claim_registry_lease(registry, exclusive=False),
        fixed_account_claim_registry_lease(registry, exclusive=False),
        pytest.raises(FreshCompositionQualificationError, match="busy"),
        fixed_account_claim_registry_lease(registry, exclusive=True),
    ):
        pass

    with (
        fixed_account_claim_registry_lease(registry, exclusive=True),
        pytest.raises(FreshCompositionQualificationError, match="busy"),
        fixed_account_claim_registry_lease(registry, exclusive=False),
    ):
        pass
