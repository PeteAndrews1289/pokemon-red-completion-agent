"""Native recovery snapshots must preserve the measured snapshot boundary."""

from hashlib import sha256
from types import SimpleNamespace

import pytest

from pokemon_red_completion.red_routed_recovery import (
    RecoveryRouteInterruptionHandler,
    RedRoutedRecoveryError,
)


def _handler(actions, emulator):
    return RecoveryRouteInterruptionHandler(
        executor=actions,
        reader=SimpleNamespace(),
        post_prep_species=(),
        post_prep_living_slots=(),
        inner=SimpleNamespace(),
        emulator=emulator,
    )


def test_native_recovery_checkpoint_includes_snapshot_observer_cost():
    actions = SimpleNamespace(actions_executed=4)
    emulator = SimpleNamespace(frame_count=10)
    calls = []

    def snapshot():
        calls.append("snapshot")
        actions.actions_executed += 2
        emulator.frame_count += 7
        return b"retained native boundary"

    emulator.save_state_bytes = snapshot
    checkpoint = _handler(actions, emulator)._native_recovery_checkpoint()

    assert checkpoint == (sha256(b"retained native boundary").hexdigest(), 6, 17)
    assert calls == ["snapshot"]


@pytest.mark.parametrize(
    ("target", "attribute", "value"),
    [
        ("emulator", "save_state_bytes", None),
        ("emulator", "save_state_bytes", lambda: bytearray(b"mutable")),
        ("emulator", "frame_count", -1),
        ("emulator", "frame_count", True),
        ("actions", "actions_executed", -1),
        ("actions", "actions_executed", True),
    ],
)
def test_native_recovery_checkpoint_rejects_unknown_or_invalid_observers(target, attribute, value):
    actions = SimpleNamespace(actions_executed=4)
    emulator = SimpleNamespace(frame_count=10, save_state_bytes=lambda: b"state")
    setattr(emulator if target == "emulator" else actions, attribute, value)

    with pytest.raises(RedRoutedRecoveryError, match="native recovery"):
        _handler(actions, emulator)._native_recovery_checkpoint()
