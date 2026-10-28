"""Exercise real TRAIN constructor guards without a ROM or an emulator."""
from hashlib import sha256
from types import SimpleNamespace

import pytest

from pokemon_red_completion.red_native_player import (
    NativeExecutionIdentity, NativePlayerLimits, NativePlayerSession,
)
from pokemon_red_completion.red_teacher_case import SESSION


class FakePort:
    frame_count = 0
    pressed_buttons = frozenset()

    def save_state_bytes(self):
        return b"synthetic TRAIN constructor test"

    def press(self, *_):
        pytest.fail("constructor must not press controls")

    def release(self, *_):
        pytest.fail("constructor must not release controls")

    def tick(self, *_):
        pytest.fail("constructor must not advance frames")


class GuardedRuntimeReached(Exception):
    pass


def constructor_arguments(tmp_path, monkeypatch):
    from pokemon_red_completion.emulator import PyBoyAdapter

    def forbidden(*_, **__):
        pytest.fail("ROM-free contract test attempted an emulator")

    monkeypatch.setattr(PyBoyAdapter, "__init__", forbidden)
    monkeypatch.setattr(PyBoyAdapter, "load_state_bytes", forbidden)
    port, calls, records = FakePort(), [], []

    def runtime_factory(controller):
        assert controller is not port
        assert controller.input_enabled is False
        assert controller.frames_executed == 0
        assert controller.save_state_bytes() == port.save_state_bytes()
        calls.append("guarded runtime")
        raise GuardedRuntimeReached

    store = SimpleNamespace(
        find_sealed_record=lambda _: None,
        publish_sealed_record=lambda *args, **kwargs: records.append((args, kwargs)),
    )
    kwargs = dict(
        store=store, emulator=port, runtime_factory=runtime_factory,
        source=dict(partition="train", state_sha256=sha256(port.save_state_bytes()).hexdigest()),
        execution=NativeExecutionIdentity("synthetic-contract", "train", "a" * 64, 13),
        output=tmp_path / "native", limits=NativePlayerLimits(),
        combat_specimen_refs=("red-preparation:" + "b" * 64,),
        battle_observer=lambda: None, target_cash=0,
        collection_teacher_setup_receipt="c" * 64, consequence_spec=None,
        **SESSION,
    )
    return kwargs, calls, records


def test_shared_train_configuration_reaches_real_guarded_runtime(tmp_path, monkeypatch):
    kwargs, calls, records = constructor_arguments(tmp_path, monkeypatch)
    with pytest.raises(GuardedRuntimeReached):
        NativePlayerSession(**kwargs)
    assert calls == ["guarded runtime"] and len(records) == 1
    recorded = records[0][1]["record"]
    assert recorded["source"]["partition"] == "train"
    assert recorded["player_resource_configuration"] == {
        "force_resource_safety": True, "include_live_pp_readiness": True,
    }
    assert "continue_safe_route_failures" not in recorded
    assert kwargs["emulator"].frame_count == 0


def test_development_route_continuation_rejects_train_before_claim_or_runtime(tmp_path, monkeypatch):
    kwargs, calls, records = constructor_arguments(tmp_path, monkeypatch)
    kwargs["continue_safe_route_failures"] = True
    with pytest.raises(ValueError, match="native safe route continuation requires DEVELOPMENT"):
        NativePlayerSession(**kwargs)
    assert calls == [] and records == []
    assert not kwargs["output"].exists()


def test_shared_restoration_configuration_requires_train_setup_receipt(tmp_path, monkeypatch):
    kwargs, calls, records = constructor_arguments(tmp_path, monkeypatch)
    kwargs["collection_teacher_setup_receipt"] = None
    with pytest.raises(ValueError, match="collection nursing requires DEVELOPMENT or authenticated TRAIN setup"):
        NativePlayerSession(**kwargs)
    assert calls == [] and records == []
