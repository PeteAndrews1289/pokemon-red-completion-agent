#!/usr/bin/env python3
"""Qualify Crystal's banked semantic observation from clean power; train nothing."""

from __future__ import annotations

import argparse
import json
import os
import time
import webbrowser
from contextlib import ExitStack
from pathlib import Path

from pokemon_crystal_completion.observation import (
    CrystalObservationError,
    read_crystal_inventory,
    read_crystal_observation_bundle,
    read_crystal_party,
    read_crystal_pokedex,
    read_crystal_storage,
)
from pokemon_crystal_completion.prerequisites import (
    CrystalPrerequisiteError,
    assess_crystal_transfer_prerequisites,
    supported_rom_from_crystal_audit,
)
from pokemon_crystal_completion.qualification import (
    CRYSTAL_BOOT_FRAMES,
    CRYSTAL_IN_GAME_SAVE_QUALIFICATION_TRANSCRIPT,
    CRYSTAL_NEW_GAME_QUALIFICATION_TRANSCRIPT,
    CRYSTAL_POST_SAVE_STABILITY_FRAMES,
    CrystalBankedObservationQualification,
    CrystalQualificationError,
    execute_crystal_qualification_steps,
    qualification_transcript_sha256,
    read_crystal_qualification_runtime,
)
from pokemon_crystal_completion.source_contract import CRYSTAL_ROM_ENVIRONMENT_VARIABLE
from pokemon_crystal_completion.transfer_protocol import (
    CRYSTAL_TRANSFER_PLAN_FILENAME,
    CrystalTransferProtocolError,
    parse_crystal_transfer_plan,
)
from pokemon_red_completion.emulator import EmulatorError, PyBoyAdapter
from pokemon_red_completion.progress_dashboard import (
    DASHBOARD_DEFAULT_PORT,
    DashboardExperimentState,
    DashboardFrameObserver,
    DashboardModelState,
    DashboardPartyMember,
    DashboardSnapshot,
    DashboardState,
    ProgressDashboardServer,
)
from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.rom import RomFingerprint, fingerprint_rom

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "configs" / CRYSTAL_TRANSFER_PLAN_FILENAME


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--dashboard", action="store_true")
    parser.add_argument("--port", type=int, default=DASHBOARD_DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--hold-seconds",
        type=int,
        default=0,
        help="Keep a successful dashboard visible for this many seconds.",
    )
    return parser


def _dashboard_snapshot(
    *,
    status: str,
    stage: str,
    message: str,
    frame_count: int,
    actions: int,
    speed: float,
    progress: float,
    bundle: object | None = None,
    events: tuple[str, ...] = (),
) -> DashboardSnapshot:
    registered = living = level_cap = capture_items = free_slots = 0
    party: tuple[DashboardPartyMember, ...] = ()
    if bundle is not None:
        from pokemon_crystal_completion.observation import CrystalObservationBundle

        if not isinstance(bundle, CrystalObservationBundle):
            raise TypeError("dashboard bundle must be CrystalObservationBundle")
        registered = bundle.pokedex.registered.completed
        living = bundle.ownership.living.completed
        level_cap = bundle.ownership.level_cap.completed
        capture_items = bundle.inventory.capture_item_count
        free_slots = bundle.storage.free_slots
        party = tuple(
            DashboardPartyMember(
                slot=member.slot,
                label=f"Species #{member.species_id:03d}",
                level=member.level,
                hp=member.hp,
                max_hp=member.max_hp,
                status=member.status.value,
            )
            for member in bundle.party.members
        )
    return DashboardSnapshot(
        game="Pokémon Crystal 1.1",
        run_status=status,
        stage=stage,
        message=message,
        frame_count=frame_count,
        actions=actions,
        emulation_speed=speed,
        stage_progress=progress,
        location="Player's bedroom" if bundle is not None else None,
        registered_species=registered,
        living_species=living,
        level_cap_species=level_cap,
        collection_target=250,
        capture_items=capture_items,
        free_storage_slots=free_slots,
        party=party,
        model=DashboardModelState(mode="waiting"),
        experiment=DashboardExperimentState(phase="qualification"),
        events=events,
    )


def _require_pristine_new_game_state(emulator: PyBoyAdapter) -> bool:
    party = read_crystal_party(emulator)
    pokedex = read_crystal_pokedex(emulator)
    inventory = read_crystal_inventory(emulator)
    if (
        party.size != 0
        or pokedex.registered.completed != 0
        or pokedex.seen.completed != 0
        or inventory.capture_item_count != 0
        or inventory.recovery_item_count != 0
    ):
        raise CrystalQualificationError("Crystal clean-power state is not pristine")
    try:
        read_crystal_storage(emulator)
    except CrystalObservationError as error:
        if "terminator" not in str(error):
            raise CrystalQualificationError(
                "Crystal pre-save storage failed for an unexpected reason"
            ) from error
        return True
    raise CrystalQualificationError("Crystal storage was initialized before the in-game save")


def _require_same_rom(before: RomFingerprint, after: RomFingerprint) -> bool:
    if before != after:
        raise CrystalQualificationError("Crystal ROM identity changed during qualification")
    return True


def _run(args: argparse.Namespace) -> CrystalBankedObservationQualification:
    if args.hold_seconds < 0:
        raise CrystalQualificationError("dashboard hold must be non-negative")
    source = detect_source_identity(ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(ROOT, source)
    source_commit = source.git_commit
    if source_commit is None or source_commit != args.expected_source_commit:
        raise CrystalQualificationError("Crystal qualification source commit differs")

    raw_path = os.environ.get(CRYSTAL_ROM_ENVIRONMENT_VARIABLE)
    if not raw_path:
        raise CrystalPrerequisiteError(
            f"set {CRYSTAL_ROM_ENVIRONMENT_VARIABLE} to the private Crystal ROM"
        )
    rom_path = Path(raw_path).expanduser().resolve()
    if not rom_path.is_file():
        raise CrystalPrerequisiteError("owner-supplied Crystal ROM is not a file")
    plan = parse_crystal_transfer_plan(PLAN.read_bytes())
    before_fingerprint = fingerprint_rom(rom_path)
    prerequisite = assess_crystal_transfer_prerequisites(
        plan,
        fingerprint=before_fingerprint,
    )
    expected_rom = supported_rom_from_crystal_audit(prerequisite)

    events = (
        "Exact owner cartridge and public source identities authenticated",
        "Qualification-only setup; no context, label, or prediction",
        "PC storage must fail closed until an actual in-game save",
    )
    dashboard_state = DashboardState(
        _dashboard_snapshot(
            status="waiting",
            stage="Banked observation qualification",
            message="Starting from clean cartridge power.",
            frame_count=0,
            actions=0,
            speed=0.0,
            progress=0.0,
            events=events,
        )
    )
    observer = DashboardFrameObserver(dashboard_state, maximum_fps=12) if args.dashboard else None
    started = time.monotonic()
    actions = 0
    with ExitStack() as stack:
        if args.dashboard:
            dashboard = stack.enter_context(
                ProgressDashboardServer(dashboard_state, port=args.port)
            )
            print(
                json.dumps(
                    {
                        "schema": "pokemon.crystal.qualification-dashboard.v1",
                        "url": dashboard.url,
                        "view_only": True,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            if not args.no_browser:
                webbrowser.open(dashboard.url)
        emulator = stack.enter_context(
            PyBoyAdapter(
                rom_path,
                expected_rom=expected_rom,
                frame_observer=observer,
            )
        )
        emulator.tick(CRYSTAL_BOOT_FRAMES)
        actions += execute_crystal_qualification_steps(
            emulator,
            CRYSTAL_NEW_GAME_QUALIFICATION_TRANSCRIPT,
        )
        before_save_runtime = read_crystal_qualification_runtime(emulator)
        if not before_save_runtime.at_starting_bedroom or not before_save_runtime.input_ready:
            raise CrystalQualificationError("Crystal setup did not reach the ready starting room")
        pre_save_storage_rejected = _require_pristine_new_game_state(emulator)
        dashboard_state.publish(
            _dashboard_snapshot(
                status="running",
                stage="Initializing cartridge storage",
                message="The fresh game state is coherent; initializing PC storage in-game.",
                frame_count=emulator.frame_count,
                actions=actions,
                speed=emulator.frame_count / max(time.monotonic() - started, 1e-9) / 60.0,
                progress=0.6,
                events=events,
            )
        )
        actions += execute_crystal_qualification_steps(
            emulator,
            CRYSTAL_IN_GAME_SAVE_QUALIFICATION_TRANSCRIPT,
        )
        first_runtime = read_crystal_qualification_runtime(emulator)
        first_bundle = read_crystal_observation_bundle(emulator)
        emulator.tick(CRYSTAL_POST_SAVE_STABILITY_FRAMES)
        second_runtime = read_crystal_qualification_runtime(emulator)
        second_bundle = read_crystal_observation_bundle(emulator)
        if first_runtime != second_runtime or first_bundle != second_bundle:
            raise CrystalQualificationError("Crystal post-save semantic observations differ")
        if not first_runtime.at_starting_bedroom or not first_runtime.input_ready:
            raise CrystalQualificationError("Crystal post-save runtime is not ready")
        controller_released = not emulator.pressed_buttons
        if not controller_released:
            raise CrystalQualificationError("Crystal controller remained pressed")
        after_fingerprint = fingerprint_rom(rom_path)
        receipt = CrystalBankedObservationQualification(
            source_commit=source_commit,
            plan_sha256=plan.plan_sha256,
            rom_sha1=after_fingerprint.sha1,
            rom_sha256=after_fingerprint.sha256,
            transcript_sha256=qualification_transcript_sha256(),
            actions=actions,
            frames=emulator.frame_count,
            runtime=second_runtime,
            observation=second_bundle,
            pre_save_storage_rejected=pre_save_storage_rejected,
            post_save_observations_identical=True,
            controller_released=controller_released,
            rom_unchanged=_require_same_rom(before_fingerprint, after_fingerprint),
        )
        dashboard_state.publish(
            _dashboard_snapshot(
                status="passed",
                stage="Banked observation qualified",
                message=(
                    "Two complete semantic reads matched after a real in-game save. "
                    "Training counters remain untouched."
                ),
                frame_count=emulator.frame_count,
                actions=actions,
                speed=emulator.frame_count / max(time.monotonic() - started, 1e-9) / 60.0,
                progress=1.0,
                bundle=second_bundle,
                events=events
                + (
                    "Whole-state stability confirmed across 600 no-input frames",
                    "Qualification passed with teacher 0 · predictions 0 · contexts 0",
                ),
            )
        )
        if args.dashboard and args.hold_seconds:
            time.sleep(args.hold_seconds)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        receipt = _run(args)
    except (
        CrystalObservationError,
        CrystalPrerequisiteError,
        CrystalQualificationError,
        CrystalTransferProtocolError,
        EmulatorError,
        EvaluationIdentityError,
        OSError,
    ):
        print(
            json.dumps(
                {
                    "schema": "pokemon.crystal.banked-observation-qualification-error.v1",
                    "status": "blocked",
                    "reason": "qualification_failed_closed",
                    "context_opened": False,
                    "teacher_executed": False,
                    "prediction_computed": False,
                    "private_path_fields": 0,
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(receipt.public_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
