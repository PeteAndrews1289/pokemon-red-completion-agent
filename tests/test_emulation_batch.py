import json
import os
import sys
import time

import pytest

import pokemon_red_completion.emulation_batch as batch_module
from pokemon_red_completion.emulation_batch import (
    EmulationJob,
    file_digest,
    freeze_runtime,
    run_emulation_batch,
    verify_pins,
)


def job(name, script, timeout=5):
    return EmulationJob(name, (sys.executable, "-c", script), timeout)


def run(tmp_path, jobs, **kwargs):
    return run_emulation_batch(
        tuple(jobs),
        output=tmp_path,
        pins={},
        environment=dict(os.environ),
        stop_grace_seconds=0.2,
        **kwargs,
    )


def test_parallel_matches_serial_and_overlaps_exactly_two(tmp_path):
    jobs = [job(str(i), f"import time;time.sleep(.15);print({i}**2)") for i in range(4)]
    serial = run(tmp_path / "serial", jobs, workers=1)
    parallel = run(tmp_path / "parallel", jobs, workers=2)
    assert serial["completed"] and parallel["completed"]
    for item in jobs:
        assert (tmp_path / "serial" / item.identity / "worker.log").read_bytes() == (
            tmp_path / "parallel" / item.identity / "worker.log"
        ).read_bytes()
    events = sorted(
        (row[key], delta)
        for row in parallel["results"]
        for key, delta in (("start_seconds", 1), ("end_seconds", -1))
    )
    active, peak = 0, 0
    for _, delta in events:
        active += delta
        peak = max(peak, active)
    assert active == 0 and peak == 2
    assert len({row["pid"] for row in parallel["results"]}) == 4
    with pytest.raises(FileExistsError):
        run(tmp_path / "parallel", jobs)


def test_failure_stops_pending_but_drains_active(tmp_path):
    result = run(
        tmp_path / "batch",
        [
            job("bad", "raise ValueError('failed')"),
            job("active", "import time;time.sleep(.15);print('retained')"),
            job("pending", "raise AssertionError('must not launch')"),
        ],
    )
    assert not result["completed"] and result["unstarted"] == ["pending"]
    assert result["active_processes"] == 0
    assert {r["identity"]: r["returncode"] for r in result["results"]} == {
        "bad": 1,
        "active": 0,
    }
    assert not (tmp_path / "batch/pending").exists()


def test_timeout_retains_worker_cleanup_and_actual_exit(tmp_path):
    script = (
        "import time\nfrom pathlib import Path\ntry:\n time.sleep(10)\n"
        "finally:\n Path('terminal').write_text('retained')\n"
    )
    result = run(tmp_path / "batch", [job("slow", script, timeout=0.3)])
    assert not result["completed"] and result["active_processes"] == 0
    row = result["results"][0]
    assert row["timed_out"] and row["signals"] == ["SIGINT"]
    assert row["returncode"] is not None
    assert (tmp_path / "batch/slow/terminal").read_text() == "retained"
    with pytest.raises(ProcessLookupError):
        os.kill(row["pid"], 0)


def test_batch_deadline_stops_both_workers_and_skips_pending(tmp_path):
    jobs = [job(str(i), "import time;time.sleep(10)") for i in range(3)]
    result = run(tmp_path / "batch", jobs, batch_seconds=0.3)
    assert result["failure"] == "batch deadline reached"
    assert result["unstarted"] == ["2"]
    assert all(row["timed_out"] and row["returncode"] is not None for row in result["results"])


@pytest.mark.parametrize("workers", [0, 3, True])
def test_refuses_other_worker_counts(tmp_path, workers):
    with pytest.raises(ValueError):
        run(tmp_path / "batch", [job("one", "pass")], workers=workers)
    assert not (tmp_path / "batch").exists()


@pytest.mark.parametrize(
    "jobs",
    [
        [],
        [job("same", "pass"), job("same", "pass")],
        [job("../escape", "pass")],
        [job("one", "pass", float("nan"))],
        [EmulationJob("one", ("python",), 1)],
    ],
)
def test_refuses_unsafe_job_declarations(tmp_path, jobs):
    with pytest.raises(ValueError):
        run(tmp_path / "batch", jobs)
    assert not (tmp_path / "batch").exists()


def test_runtime_is_frozen_and_pins_reject_mutation(tmp_path):
    source = tmp_path / "repo/src/pokemon_red_completion"
    source.mkdir(parents=True)
    (source / "unit.py").write_text("VERSION = 1\n")
    scripts = tmp_path / "repo/scripts"
    scripts.mkdir()
    (scripts / "worker.py").write_text("print('frozen')\n")
    pins = freeze_runtime(tmp_path / "repo", tmp_path / "runtime", ("worker.py",))
    (source / "unit.py").write_text("VERSION = 2\n")
    verify_pins(pins)
    frozen = tmp_path / "runtime/src/pokemon_red_completion/unit.py"
    assert frozen.read_text() == "VERSION = 1\n"
    frozen.write_text("VERSION = 3\n")
    with pytest.raises(ValueError, match="hash changed"):
        run_emulation_batch(
            (job("one", "pass"),),
            output=tmp_path / "batch",
            pins=pins,
            environment=dict(os.environ),
        )
    assert not (tmp_path / "batch").exists()


def test_changed_pin_during_job_retains_failure_summary(tmp_path):
    source = tmp_path / "pinned"
    source.write_text("original")
    script = f"from pathlib import Path;Path({str(source)!r}).write_text('changed')"
    with pytest.raises(ValueError, match="hash changed"):
        run_emulation_batch(
            (job("mutate", script),),
            output=tmp_path / "batch",
            pins={str(source): file_digest(source)},
            environment=dict(os.environ),
        )
    result = json.loads((tmp_path / "batch/result.json").read_bytes())
    assert not result["completed"] and result["active_processes"] == 0
    assert result["results"][0]["returncode"] is not None


def test_launch_error_retains_summary(tmp_path):
    with pytest.raises(FileNotFoundError):
        run(tmp_path / "batch", [EmulationJob("absent", ("/not-a-real-worker",), 1)])
    result = json.loads((tmp_path / "batch/result.json").read_bytes())
    assert not result["completed"] and result["active_processes"] == 0
    assert result["unstarted"] == ["absent"]


def test_slow_pin_check_cannot_dispatch_after_deadline(tmp_path, monkeypatch):
    calls = 0

    def slow_pins(pins):
        nonlocal calls
        calls += 1
        if calls == 2:
            time.sleep(0.05)

    monkeypatch.setattr(batch_module, "verify_pins", slow_pins)
    result = run(tmp_path / "batch", [job("pending", "pass")], batch_seconds=0.02)
    assert not result["completed"] and result["failure"] == "batch deadline reached"
    assert result["unstarted"] == ["pending"] and result["results"] == []
