"""Small bounded process scheduler; workers own emulator and terminal-state retention.

This module grants no gameplay authority. Callers must supply a prospective protocol,
frozen inputs and independently audit semantic results. A zero exit is not a battle win.
"""

from __future__ import annotations

import json
import math
import os
import re
import signal
import subprocess
import time
from contextlib import suppress
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, BinaryIO


@dataclass(frozen=True)
class EmulationJob:
    identity: str
    argv: tuple[str, ...]
    timeout_seconds: float


def file_digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _record(path: Path, value: Any) -> None:
    # Exclusive records: failed attempts cannot silently become successful reruns.
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def verify_pins(pins: dict[str, str]) -> None:
    for name, expected in pins.items():
        if file_digest(Path(name)) != expected:
            raise ValueError(f"input hash changed: {name}")


def freeze_runtime(repository: Path, output: Path, scripts: tuple[str, ...]) -> dict[str, str]:
    """Copy Python sources, not Git state or private data, to an exclusive runtime."""
    paths = sorted((repository / "src/pokemon_red_completion").glob("*.py"))
    for name in scripts:
        if Path(name).name != name or not name.endswith(".py"):
            raise ValueError("runtime scripts must be plain Python filenames")
        paths.append(repository / "scripts" / name)
    if not paths or len(paths) != len(set(paths)):
        raise ValueError("runtime sources missing or duplicated")
    # Read once: the copied bytes and their hashes always describe the same version.
    payloads = [(path.relative_to(repository), path.read_bytes()) for path in paths]
    output.mkdir(parents=False, exist_ok=False, mode=0o700)
    pins = {}
    for relative, payload in payloads:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(payload)
        pins[str(target.resolve())] = sha256(payload).hexdigest()
    _record(output / "manifest.json", pins)
    return pins


def _stop(process: subprocess.Popen, grace: float) -> list[str]:
    """Request retention first, then bound a stuck worker; return only observed exits."""
    sent = []
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        if process.poll() is not None:
            break
        with suppress(ProcessLookupError):
            os.killpg(process.pid, sig)
        sent.append(sig.name)
        try:
            process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            continue
    process.wait(timeout=grace)
    return sent


def run_emulation_batch(
    jobs: tuple[EmulationJob, ...],
    *,
    output: Path,
    pins: dict[str, str],
    environment: dict[str, str],
    workers: int = 2,
    batch_seconds: float = 600,
    stop_grace_seconds: float = 5,
) -> dict[str, Any]:
    """Run one or two jobs concurrently; fail-stop pending jobs, drain active jobs.

    Jobs must not spawn detached descendants. The environment is explicit so callers
    can select a frozen PYTHONPATH rather than importing a changing working checkout.
    """
    if type(workers) is not int or workers not in (1, 2):
        raise ValueError("only one or two workers are supported")
    identities = [job.identity for job in jobs]
    if not jobs or len(set(identities)) != len(jobs):
        raise ValueError("job identities must be nonempty and unique")
    for job in jobs:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}", job.identity):
            raise ValueError("unsafe job identity")
        if not job.argv or not Path(job.argv[0]).is_absolute():
            raise ValueError("job executable must be absolute")
    budgets = (batch_seconds, stop_grace_seconds, *(job.timeout_seconds for job in jobs))
    if any(not math.isfinite(value) or value <= 0 for value in budgets):
        raise ValueError("budgets must be positive and finite")
    verify_pins(pins)
    output.mkdir(parents=False, exist_ok=False, mode=0o700)
    _record(
        output / "plan.json",
        dict(
            jobs=[asdict(job) for job in jobs],
            workers=workers,
            pins=pins,
            batch_seconds=batch_seconds,
            stop_grace_seconds=stop_grace_seconds,
        ),
    )
    # Each record has its own stream and directory; no interleaved shared log.
    active: dict[str, tuple[subprocess.Popen, BinaryIO, float, EmulationJob]] = {}
    results: list[dict[str, Any]] = []
    started = time.monotonic()
    next_index = 0
    failure: str | None = None

    def finish(identity: str, signals: list[str], timed_out: bool) -> None:
        nonlocal failure
        process, stream, began, job = active.pop(identity)
        stream.close()
        row = dict(
            identity=identity,
            pid=process.pid,
            returncode=process.returncode,
            start_seconds=began - started,
            end_seconds=time.monotonic() - started,
            timed_out=timed_out,
            signals=signals,
        )
        results.append(row)
        _record(output / identity / "process-result.json", row)
        if process.returncode != 0 or timed_out:
            failure = failure or f"worker failed: {job.identity}"

    try:
        while next_index < len(jobs) or active:
            now = time.monotonic()
            expired = now - started >= batch_seconds
            if expired:
                failure = failure or "batch deadline reached"
            # Observe every completed process before assigning another job.
            for identity, (process, _, began, job) in tuple(active.items()):
                if process.poll() is not None:
                    finish(identity, [], False)
                elif expired or now - began >= job.timeout_seconds:
                    finish(identity, _stop(process, stop_grace_seconds), True)
            if failure is None and next_index < len(jobs) and len(active) < workers:
                verify_pins(pins)
            while failure is None and next_index < len(jobs) and len(active) < workers:
                if time.monotonic() - started >= batch_seconds:
                    failure = "batch deadline reached"
                    break
                job = jobs[next_index]
                directory = output / job.identity
                directory.mkdir(mode=0o700)
                stream = (directory / "worker.log").open("xb")
                try:
                    process = subprocess.Popen(
                        job.argv,
                        cwd=directory,
                        env=environment,
                        stdout=stream,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                except BaseException:
                    stream.close()
                    raise
                began = time.monotonic()
                active[job.identity] = (process, stream, began, job)
                next_index += 1
                _record(
                    directory / "claim.json",
                    dict(
                        identity=job.identity,
                        pid=process.pid,
                        start_seconds=began - started,
                    ),
                )
            if not active:
                break
            time.sleep(0.02)
        verify_pins(pins)
    except BaseException as error:
        failure = f"{type(error).__name__}: {error}"
        raise
    finally:
        for identity, (process, _, _, _) in tuple(active.items()):
            finish(identity, _stop(process, stop_grace_seconds), True)
        summary = dict(
            completed=failure is None and len(results) == len(jobs),
            failure=failure,
            results=results,
            unstarted=[job.identity for job in jobs[next_index:]],
            elapsed_seconds=time.monotonic() - started,
            active_processes=0,
        )
        _record(output / "result.json", summary)
    return summary
