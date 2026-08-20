#!/usr/bin/env python3
"""Qualify Crystal's first real goal/navigation slice; score and train nothing."""

from __future__ import annotations

import argparse
import json
import os
import time
import webbrowser
from contextlib import ExitStack
from pathlib import Path

from pokemon_crystal_completion.dashboard import crystal_dashboard_snapshot
from pokemon_crystal_completion.prerequisites import (
    CrystalPrerequisiteError,
    assess_crystal_transfer_prerequisites,
    supported_rom_from_crystal_audit,
)
from pokemon_crystal_completion.qualification import (
    CRYSTAL_BOOT_FRAMES,
    CRYSTAL_IN_GAME_SAVE_QUALIFICATION_TRANSCRIPT,
    CRYSTAL_NEW_GAME_QUALIFICATION_TRANSCRIPT,
    CrystalQualificationError,
    execute_crystal_qualification_steps,
    qualification_transcript_sha256,
)
from pokemon_crystal_completion.source_contract import CRYSTAL_ROM_ENVIRONMENT_VARIABLE
from pokemon_crystal_completion.transfer_protocol import (
    CRYSTAL_TRANSFER_PLAN_FILENAME,
    CrystalTransferProtocolError,
    parse_crystal_transfer_plan,
)
from pokemon_crystal_completion.vertical_slice import (
    CrystalStartingVerticalSliceQualification,
    CrystalVerticalSliceError,
    build_crystal_starting_goal_bindings,
    observe_crystal_starting_goal_state,
)
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.emulator import EmulatorError, PyBoyAdapter
from pokemon_red_completion.executor import ControllerTiming, FrameSafeExecutor
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalDecisionOutcome,
    GoalKind,
    GoalManagerQuestion,
)
from pokemon_red_completion.progress_dashboard import (
    DASHBOARD_DEFAULT_PORT,
    DashboardExperimentState,
    DashboardFrameObserver,
    DashboardModelState,
    DashboardSnapshot,
    DashboardState,
    ProgressDashboardServer,
)
from pokemon_red_completion.provenance import (
    EvaluationIdentityError,
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.rom import RomFingerprint, fingerprint_rom

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "configs" / CRYSTAL_TRANSFER_PLAN_FILENAME
MENU_CLOSE_ACTIONS = 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--dashboard", action="store_true")
    parser.add_argument("--port", type=int, default=DASHBOARD_DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--hold-seconds", type=int, default=0)
    return parser


def _waiting_snapshot() -> DashboardSnapshot:
    return DashboardSnapshot(
        game="Pokémon Crystal 1.1",
        run_status="waiting",
        stage="Starting vertical-slice qualification",
        message="Authenticating one unscored story/exploration boundary.",
        model=DashboardModelState(mode="waiting", candidate="No model executed"),
        experiment=DashboardExperimentState(phase="qualification"),
        events=(
            "Exact source and cartridge identities required",
            "Two declared bindings · no teacher label",
            "Predictions 0 · contexts 0 · training examples 0",
        ),
    )


def _policy_question_sha256(question: GoalManagerQuestion) -> str:
    return canonical_sha256(
        {
            "schema": "pokemon.core.goal-manager-unlabeled-question.v1",
            "situation": question.situation.policy_dict(),
            "candidates": [item.policy_dict() for item in question.opportunities],
        }
    )


def _require_same_rom(before: RomFingerprint, after: RomFingerprint) -> bool:
    if before != after:
        raise CrystalVerticalSliceError("Crystal ROM identity changed during the slice")
    return True


def _run(args: argparse.Namespace) -> CrystalStartingVerticalSliceQualification:
    if args.hold_seconds < 0:
        raise CrystalVerticalSliceError("dashboard hold must be non-negative")
    source = detect_source_identity(ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(ROOT, source)
    source_commit = source.git_commit
    if source_commit is None or source_commit != args.expected_source_commit:
        raise CrystalVerticalSliceError("Crystal slice source commit differs")

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
    expected_rom = supported_rom_from_crystal_audit(
        assess_crystal_transfer_prerequisites(plan, fingerprint=before_fingerprint)
    )

    dashboard_state = DashboardState(_waiting_snapshot())
    observer = DashboardFrameObserver(dashboard_state, maximum_fps=12) if args.dashboard else None
    started = time.monotonic()
    setup_actions = 0
    with ExitStack() as stack:
        if args.dashboard:
            dashboard = stack.enter_context(
                ProgressDashboardServer(dashboard_state, port=args.port)
            )
            print(
                json.dumps(
                    {
                        "schema": "pokemon.crystal.vertical-slice-dashboard.v1",
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
            PyBoyAdapter(rom_path, expected_rom=expected_rom, frame_observer=observer)
        )
        emulator.tick(CRYSTAL_BOOT_FRAMES)
        setup_actions += execute_crystal_qualification_steps(
            emulator,
            CRYSTAL_NEW_GAME_QUALIFICATION_TRANSCRIPT,
        )
        setup_actions += execute_crystal_qualification_steps(
            emulator,
            CRYSTAL_IN_GAME_SAVE_QUALIFICATION_TRANSCRIPT,
        )
        menu = FrameSafeExecutor(
            emulator,
            ControllerTiming(press_frames=6, release_frames=300, wait_frames=1),
        )
        for _ in range(MENU_CLOSE_ACTIONS):
            menu.execute(MacroAction(MacroActionKind.CANCEL))

        observation = observe_crystal_starting_goal_state(emulator)
        binding_set = build_crystal_starting_goal_bindings(observation, emulator)
        question = GoalManagerQuestion(observation.situation, binding_set.opportunities)
        available = tuple(
            item.kind
            for item in question.opportunities
            if item.availability is GoalAvailability.AVAILABLE
        )
        if available != (GoalKind.ADVANCE_STORY, GoalKind.EXPLORE):
            raise CrystalVerticalSliceError("Crystal starting goal menu differs")
        model = DashboardModelState(mode="waiting", candidate="No model executed")
        experiment = DashboardExperimentState(phase="qualification")
        dashboard_state.publish(
            crystal_dashboard_snapshot(
                observation,
                run_status="running",
                stage="Qualifying exploration binding",
                message="The shared router must visit the first floor and return to its start.",
                frame_count=emulator.frame_count,
                actions=setup_actions + MENU_CLOSE_ACTIONS,
                emulation_speed=emulator.frame_count
                / max(time.monotonic() - started, 1e-9)
                / 60.0,
                stage_progress=0.35,
                experiment=experiment,
                model=model,
                question=question,
                location="Player's bedroom",
                events=(
                    "Story and exploration are both genuinely executable",
                    "Candidate policy view contains no map, coordinate, or binding identity",
                    "No teacher or model is choosing during qualification",
                ),
            )
        )
        explore = binding_set.require(
            next(
                binding.binding_ref
                for binding in binding_set.bindings
                if binding.kind is GoalKind.EXPLORE
            )
        )
        exploration = explore.execute()
        exploration_verdict = explore.verify(exploration)
        if exploration_verdict.status is not GoalDecisionOutcome.SUCCEEDED:
            raise CrystalVerticalSliceError("Crystal exploration binding did not verify")
        dashboard_state.publish(
            crystal_dashboard_snapshot(
                observation,
                run_status="running",
                stage="Qualifying story binding",
                message="The same observed boundary must now reach the declared story handoff.",
                frame_count=emulator.frame_count,
                actions=(
                    setup_actions + MENU_CLOSE_ACTIONS + exploration.actions_executed
                ),
                emulation_speed=emulator.frame_count
                / max(time.monotonic() - started, 1e-9)
                / 60.0,
                stage_progress=0.7,
                experiment=experiment,
                model=model,
                question=question,
                location="Player's bedroom",
                events=(
                    "Exploration returned to its exact start",
                    "Turn-only inputs were retried only after live acknowledgement",
                    "Teacher 0 · predictions 0 · contexts 0",
                ),
            )
        )
        story = binding_set.require(
            next(
                binding.binding_ref
                for binding in binding_set.bindings
                if binding.kind is GoalKind.ADVANCE_STORY
            )
        )
        story_execution = story.execute()
        story_verdict = story.verify(story_execution)
        if story_verdict.status is not GoalDecisionOutcome.SUCCEEDED:
            raise CrystalVerticalSliceError("Crystal story binding did not verify")
        after_fingerprint = fingerprint_rom(rom_path)
        receipt = CrystalStartingVerticalSliceQualification(
            source_commit=source_commit,
            plan_sha256=plan.plan_sha256,
            rom_sha1=after_fingerprint.sha1,
            rom_sha256=after_fingerprint.sha256,
            setup_transcript_sha256=qualification_transcript_sha256(),
            policy_question_sha256=_policy_question_sha256(question),
            setup_actions=setup_actions,
            menu_close_actions=MENU_CLOSE_ACTIONS,
            exploration_actions=exploration.actions_executed,
            exploration_frames=exploration.frames_executed,
            exploration_semantic_steps=int(exploration.evidence["semantic_steps"]),
            story_actions=story_execution.actions_executed,
            story_frames=story_execution.frames_executed,
            story_semantic_steps=int(story_execution.evidence["semantic_steps"]),
            available_goal_kinds=available,
            exploration_verified=True,
            story_verified=True,
            controller_released=not emulator.pressed_buttons,
            rom_unchanged=_require_same_rom(before_fingerprint, after_fingerprint),
        )
        dashboard_state.publish(
            crystal_dashboard_snapshot(
                observation,
                run_status="passed",
                stage="Starting vertical slice qualified",
                message=(
                    "Two real goal bindings passed without a teacher query, model prediction, "
                    "or training example."
                ),
                frame_count=emulator.frame_count,
                actions=int(receipt.public_dict()["total_controller_actions"]),
                emulation_speed=emulator.frame_count
                / max(time.monotonic() - started, 1e-9)
                / 60.0,
                stage_progress=1.0,
                experiment=experiment,
                model=model,
                question=question,
                location="Player's house, first floor",
                events=(
                    "Story binding independently verified at its destination",
                    "Exploration binding independently verified after its round trip",
                    "Qualification passed · experiment counters remain zero",
                ),
            )
        )
        if args.dashboard and args.hold_seconds:
            time.sleep(args.hold_seconds)
    return receipt


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = _run(args)
    except (
        CrystalPrerequisiteError,
        CrystalQualificationError,
        CrystalTransferProtocolError,
        CrystalVerticalSliceError,
        EmulatorError,
        EvaluationIdentityError,
        OSError,
    ):
        print(
            json.dumps(
                {
                    "schema": "pokemon.crystal.starting-vertical-slice-error.v1",
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
