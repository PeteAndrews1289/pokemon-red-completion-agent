"""Private proposal failure-path tests: fake adapters only, no ROM or native load."""

from hashlib import sha256

import pytest

from pokemon_red_completion.red_teacher_story_unit import (
    managed_teacher_guest,
    record_teacher_phase,
)


def result():
    return dict(actions=0, frames=0, goal_attempts=0, phase_results=[])


def closed(actions=7, frames=120):
    return dict(actions_attempted=actions, frames=frames, admitted=True, succeeded=True)


class Adapter:
    def __init__(self, *, entry_error=None, close_error=None, save_error=None, frame_error=None):
        self.entry_error, self.close_error, self.save_error = entry_error, close_error, save_error
        self.frame_error = frame_error
        self.entered = self.close_calls = 0
        self.pressed_buttons = {"a"}

    def __enter__(self):
        self.entered += 1
        if self.entry_error:
            raise self.entry_error
        return self

    @property
    def frame_count(self):
        if self.frame_error:
            raise self.frame_error
        return 240

    def save_state_bytes(self):
        if self.save_error:
            raise self.save_error
        return b"fake terminal bytes; never an emulator save"

    def close(self):
        self.close_calls += 1
        if self.close_error:
            raise self.close_error


def lifecycle(adapter, r, **overrides):
    kwargs = dict(
        release=lambda em: em.pressed_buttons.clear(),
        export_terminal=lambda payload: None,
        cancel_timer=lambda: None,
        clock=lambda: 20.0,
        native_started=10.0,
    )
    kwargs.update(overrides)
    return managed_teacher_guest(adapter, r, **kwargs)


def throw(error):
    raise error


def test_recorder_exception_after_closed_phase_preserves_lower_bound_not_zero():
    r = result()
    record_teacher_phase(r, "approach", lambda: closed())
    error = TimeoutError("timer fired after unreported actions")
    with pytest.raises(TimeoutError) as caught:
        record_teacher_phase(r, "interaction", lambda: throw(error))
    assert caught.value is error
    assert r["goal_attempts"] == 2 and len(r["phase_results"]) == 1
    assert r["actions"] is None and r["actions_cost_known"] is False
    assert r["actions_lower_bound"] == 7
    assert r["frames"] is None and r["frames_lower_bound"] == 120
    assert r["active_phase"] == "interaction"
    assert "timer fired" in r["phase_error"]["traceback"]


def test_recorder_first_attempt_throw_is_unknown_even_with_zero_lower_bound():
    r = result()
    with pytest.raises(OSError):
        record_teacher_phase(r, "approach", lambda: throw(OSError("journal broke after inputs")))
    assert r["actions"] is None and r["actions_lower_bound"] == 0
    assert r["frames"] is None and r["goal_attempts"] == 1


def test_returned_failed_attempt_still_has_exact_measured_costs():
    r = result()
    attempt = dict(closed(), admitted=False, succeeded=False, execution_or_verification_failed=True)
    assert record_teacher_phase(r, "approach", lambda: attempt) is attempt
    assert r["actions"] == 7 and r["frames"] == 120
    assert r["actions_cost_known"] and r["frames_cost_known"]


@pytest.mark.parametrize("bad", [-1, True, None, "9"])
def test_untrustworthy_returned_cost_stays_unknown(bad):
    r = result()
    with pytest.raises(ValueError):
        record_teacher_phase(r, "approach", lambda: dict(closed(), actions_attempted=bad))
    assert r["actions"] is None and r["actions_lower_bound"] == 0


def test_primary_error_survives_release_export_and_close_failures():
    r = result()
    adapter = Adapter(close_error=OSError("close failed"))
    primary = RuntimeError("native failure")
    with (
        pytest.raises(RuntimeError) as caught,
        lifecycle(
            adapter,
            r,
            release=lambda _: throw(ValueError("release failed")),
            export_terminal=lambda _: throw(OSError("disk full")),
        ),
    ):
        raise primary
    assert caught.value is primary
    assert r["native_error"]["error"] == "native failure"
    assert {e["stage"] for e in r["cleanup_errors"]} == {
        "release_controls",
        "export_terminal",
        "close_guest",
    }
    assert all(e["traceback"] for e in r["cleanup_errors"])
    assert r["emulator_closed"] is None and r["emulator_close_known"] is False
    assert adapter.close_calls == 1 and "terminal_sha256" not in r
    assert r["terminal_observed_sha256"] == sha256(adapter.save_state_bytes()).hexdigest()
    assert r["terminal_exported"] is False
    assert r["frames"] == 240 and r["native_seconds"] == 10.0


def test_error_exit_closes_guest_truthfully_and_keeps_terminal():
    r = result()
    adapter = Adapter()
    exported = []
    with pytest.raises(TimeoutError), lifecycle(adapter, r, export_terminal=exported.append):
        raise TimeoutError("native timeout")
    assert r["emulator_closed"] is True and r["emulator_close_known"] is True
    assert r["controls_released"] is True and adapter.close_calls == 1
    assert r["terminal_sha256"] == sha256(exported[0]).hexdigest()


@pytest.mark.parametrize(
    "failure", ["release", "save", "export", "close", "frames", "timer", "clock"]
)
def test_cleanup_only_failure_fails_case_and_runs_remaining_steps(failure):
    r = result()
    adapter = Adapter()
    overrides = {}
    if failure == "release":
        overrides["release"] = lambda _: throw(RuntimeError("release"))
    elif failure == "save":
        adapter.save_error = RuntimeError("save")
    elif failure == "export":
        overrides["export_terminal"] = lambda _: throw(RuntimeError("export"))
    elif failure == "close":
        adapter.close_error = RuntimeError("close")
    elif failure == "frames":
        adapter.frame_error = RuntimeError("frames")
    elif failure == "timer":
        overrides["cancel_timer"] = lambda: throw(RuntimeError("timer"))
    else:
        overrides["clock"] = lambda: throw(RuntimeError("clock"))
    with pytest.raises(ExceptionGroup), lifecycle(adapter, r, **overrides):
        pass
    assert len(r["cleanup_errors"]) == 1 and adapter.close_calls == 1
    assert r["emulator_closed"] is (None if failure == "close" else True)
    if failure == "frames":
        assert r["frames"] is None and r["frames_cost_known"] is False
    if failure == "clock":
        assert r["native_seconds"] is None


def test_partial_guest_start_failure_still_closes_without_fake_release_or_terminal():
    r = result()
    error = OSError("backend partially allocated")
    adapter = Adapter(entry_error=error)
    with pytest.raises(OSError) as caught, lifecycle(adapter, r):
        pytest.fail("failed entry must not execute phase")
    assert caught.value is error and adapter.close_calls == 1
    assert r["emulator_closed"] is True and r["controls_released"] is None
    assert "terminal_sha256" not in r and r["frames"] is None


def test_native_unknown_actions_remain_unknown_after_successful_cleanup():
    r = result()
    adapter = Adapter()
    with pytest.raises(TimeoutError), lifecycle(adapter, r):
        record_teacher_phase(r, "approach", lambda: closed())
        record_teacher_phase(r, "interaction", lambda: throw(TimeoutError("interrupted")))
    assert r["actions"] is None and r["actions_lower_bound"] == 7
    assert r["actions_cost_known"] is False
    assert r["frames"] == 240 and r["frames_cost_known"] is True
    assert r["emulator_closed"] is True


def test_existing_closeout_classifies_unknown_costs_without_zero_substitution():
    import runpy
    from pathlib import Path

    import pokemon_red_completion

    project = Path(pokemon_red_completion.__file__).resolve().parents[2]
    classify = runpy.run_path(project / "scripts/red_teacher_closeout.py")["classify_closed_phase"]
    r = result()
    adapter = Adapter()
    with pytest.raises(TimeoutError), lifecycle(adapter, r):
        record_teacher_phase(r, "approach", lambda: throw(TimeoutError("after input")))
    r.update(
        passed=False,
        physical_emulator_accounting=dict(
            construction_attempts=1, emulators_constructed=1, load_attempts=1, state_loads=1
        ),
        heals=0,
        wild_battles=None,
        story_battles=0,
    )
    closed_result = classify(
        r,
        phase="direct",
        processes_absent=True,
        cgroup_empty=True,
        terminal_sha256=r["terminal_sha256"],
    )
    assert closed_result["native_costs_known"] is False
    assert closed_result["native_costs"]["actions"] is None
    assert closed_result["native_costs"]["frames"] == 240
    assert closed_result["controls_released"] is True


def test_private_error_receipt_write_failure_never_replaces_native_error():
    from pokemon_red_completion.red_teacher_story_unit import retain_native_call_error

    r = result()
    original = ValueError("original executor error")
    guarded = retain_native_call_error(
        lambda: throw(original),
        result=r,
        phase="interaction",
        stage="execute",
        write_error=lambda _: throw(OSError("receipt disk full")),
    )
    with pytest.raises(ValueError) as caught:
        guarded()
    assert caught.value is original
    assert r["recorded_execution_errors"][0]["error"] == "original executor error"
    assert r["error_receipt_write_errors"][0]["error"] == "receipt disk full"


def test_base_exception_is_preserved_with_cleanup_failure():
    r = result()
    original = KeyboardInterrupt("interrupted during action")
    with (
        pytest.raises(KeyboardInterrupt) as caught,
        lifecycle(Adapter(close_error=OSError("close error")), r),
    ):
        record_teacher_phase(r, "interaction", lambda: throw(original))
    assert caught.value is original and r["actions"] is None
    assert r["cleanup_errors"][0]["stage"] == "close_guest"


@pytest.mark.parametrize("value", [-1.0, float("nan")])
def test_invalid_native_clock_stays_unknown(value):
    r = result()
    with pytest.raises(ExceptionGroup), lifecycle(Adapter(), r, clock=lambda: 10.0 + value):
        pass
    assert r["native_seconds"] is None
    assert r["emulator_closed"] is True
