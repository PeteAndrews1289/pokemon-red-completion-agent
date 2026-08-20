#!/usr/bin/env python3
"""Run a view-only Crystal dashboard without opening an experiment context."""

from __future__ import annotations

import argparse
import json
import os
import time
import webbrowser
from pathlib import Path

from pokemon_crystal_completion.prerequisites import (
    CrystalPrerequisiteError,
    assess_crystal_transfer_prerequisites,
    supported_rom_from_crystal_audit,
)
from pokemon_crystal_completion.source_contract import CRYSTAL_ROM_ENVIRONMENT_VARIABLE
from pokemon_crystal_completion.transfer_protocol import (
    CRYSTAL_TRANSFER_PLAN_FILENAME,
    parse_crystal_transfer_plan,
)
from pokemon_red_completion.emulator import EmulatorError, PyBoyAdapter
from pokemon_red_completion.progress_dashboard import (
    DASHBOARD_DEFAULT_PORT,
    DashboardExperimentState,
    DashboardFrameObserver,
    DashboardModelState,
    DashboardSnapshot,
    DashboardState,
    ProgressDashboardServer,
)
from pokemon_red_completion.rom import fingerprint_rom

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "configs" / CRYSTAL_TRANSFER_PLAN_FILENAME


def _snapshot(
    *,
    status: str,
    frame_count: int,
    speed: float,
    message: str,
    events: tuple[str, ...],
) -> DashboardSnapshot:
    return DashboardSnapshot(
        game="Pokémon Crystal 1.1",
        run_status=status,
        stage="Authenticated observer preview",
        message=message,
        frame_count=frame_count,
        actions=0,
        emulation_speed=speed,
        stage_progress=1.0,
        model=DashboardModelState(mode="waiting"),
        experiment=DashboardExperimentState(phase="qualification"),
        events=events,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Show the authenticated cartridge and experiment counters without controller input, "
            "teacher access, predictions, or context opening."
        )
    )
    parser.add_argument("--port", type=int, default=DASHBOARD_DEFAULT_PORT)
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=0,
        help="Stop after this many seconds; zero runs until Ctrl-C.",
    )
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if args.duration_seconds < 0:
        parser.error("--duration-seconds must be non-negative")

    raw_path = os.environ.get(CRYSTAL_ROM_ENVIRONMENT_VARIABLE)
    if not raw_path:
        raise CrystalPrerequisiteError(
            f"set {CRYSTAL_ROM_ENVIRONMENT_VARIABLE} to the private Crystal ROM"
        )
    rom_path = Path(raw_path).expanduser().resolve()
    if not rom_path.is_file():
        raise CrystalPrerequisiteError("owner-supplied Crystal ROM is not a file")
    plan = parse_crystal_transfer_plan(PLAN.read_bytes())
    audit = assess_crystal_transfer_prerequisites(
        plan,
        fingerprint=fingerprint_rom(rom_path),
    )
    expected_rom = supported_rom_from_crystal_audit(audit)

    events = (
        "Crystal 1.1 identity and exact owner digest verified",
        "Dashboard is view-only; controller endpoints are absent",
        "No experiment context, teacher label, or prediction opened",
    )
    state = DashboardState(
        _snapshot(
            status="waiting",
            frame_count=0,
            speed=0.0,
            message="Starting the authenticated no-input emulator preview.",
            events=events,
        )
    )
    observer = DashboardFrameObserver(state)
    with ProgressDashboardServer(state, port=args.port) as dashboard:
        print(
            json.dumps(
                {
                    "schema": "pokemon.crystal.dashboard-preview.v1",
                    "url": dashboard.url,
                    "view_only": True,
                    "context_opened": False,
                    "teacher_executed": False,
                    "prediction_computed": False,
                },
                sort_keys=True,
            )
        )
        if not args.no_browser:
            webbrowser.open(dashboard.url)
        started = time.monotonic()
        last_status = started
        final_frame_count = 0
        with PyBoyAdapter(
            rom_path,
            expected_rom=expected_rom,
            frame_observer=observer,
        ) as emulator:
            try:
                while (
                    args.duration_seconds == 0
                    or time.monotonic() - started < args.duration_seconds
                ):
                    emulator.tick(1)
                    time.sleep(1.0 / 60.0)
                    now = time.monotonic()
                    if now - last_status >= 0.25:
                        elapsed = max(now - started, 1e-9)
                        speed = emulator.frame_count / (elapsed * 60.0)
                        state.publish(
                            _snapshot(
                                status="running",
                                frame_count=emulator.frame_count,
                                speed=speed,
                                message=(
                                    "Showing live cartridge frames. Model execution waits for "
                                    "the exact-commit qualification run."
                                ),
                                events=events,
                            )
                        )
                        last_status = now
            except KeyboardInterrupt:
                pass
            final_frame_count = emulator.frame_count
        state.publish(
            _snapshot(
                status="paused",
                frame_count=final_frame_count,
                speed=0.0,
                message="Observer preview stopped without saving cartridge state.",
                events=events + ("Preview stopped without saving",),
            )
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CrystalPrerequisiteError, EmulatorError) as error:
        print(
            json.dumps(
                {
                    "schema": "pokemon.crystal.dashboard-preview-error.v1",
                    "status": "blocked",
                    "reason": str(error),
                    "context_opened": False,
                    "teacher_executed": False,
                    "prediction_computed": False,
                },
                sort_keys=True,
            )
        )
        raise SystemExit(2) from None
