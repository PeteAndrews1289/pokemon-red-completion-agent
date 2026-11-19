"""A soft admission window cannot silently replace sealed native limits."""

import hashlib
import json
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.red_sequence_native_audit import actor_admission_seconds


def bound_order(tmp_path, seconds=120, *, changed_caps=False):
    path = tmp_path / "work-order.json"
    hard = {"seconds": 210, "actions": 22000, "frames": 2200000}
    path.write_text(json.dumps({"admission_seconds": seconds, "native_limits": hard}))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    plan = {"source": {"experiment_sha256": digest}, "limits": dict(hard)}
    if changed_caps:
        plan["limits"]["actions"] += 1
    return path, plan


def test_default_keeps_legacy_exact_limit():
    assert actor_admission_seconds({}, NS(seconds=210)) == 210


def test_bound_earlier_admission_keeps_hard_limit(tmp_path):
    path, plan = bound_order(tmp_path)
    assert actor_admission_seconds(plan, NS(seconds=210), path) == 120
    assert plan["limits"]["seconds"] == 210


def test_tampered_work_order_cannot_change_admission(tmp_path):
    path, plan = bound_order(tmp_path)
    path.write_text(path.read_text().replace("120", "200"))
    with pytest.raises(ValueError, match="sealed experiment"):
        actor_admission_seconds(plan, NS(seconds=210), path)


def test_shorter_admission_cannot_excuse_changed_native_caps(tmp_path):
    path, plan = bound_order(tmp_path, changed_caps=True)
    with pytest.raises(ValueError, match="hard limits"):
        actor_admission_seconds(plan, NS(seconds=210), path)


@pytest.mark.parametrize("seconds", [True, None, 0, -1, 211, float("nan"), float("inf")])
def test_invalid_or_larger_admission_never_passes(tmp_path, seconds):
    path, plan = bound_order(tmp_path, seconds)
    with pytest.raises(ValueError, match="hard limits"):
        actor_admission_seconds(plan, NS(seconds=210), path)
