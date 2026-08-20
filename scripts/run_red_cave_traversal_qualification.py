#!/usr/bin/env python3
"""Preflight or execute the frozen Red Cave traversal qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.blaine import (  # noqa: E402
    DIGLETTS_CAVE_TRAINING_VENUE,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING  # noqa: E402
from pokemon_red_completion.captured_progress import (  # noqa: E402
    CapturedProgressEnvelope,
    load_captured_progress,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.goal_manager_protocol import (  # noqa: E402
    load_committed_goal_manager_registry,
)
from pokemon_red_completion.observation import MapId, PokemonRedStateReader  # noqa: E402
from pokemon_red_completion.party import PartyObservation, StatusCondition  # noqa: E402
from pokemon_red_completion.private_artifacts import open_private_root  # noqa: E402
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_cave_traversal_qualification import (  # noqa: E402
    CaveTraversalQualificationPolicy,
    run_cave_traversal_qualification,
)
from pokemon_red_completion.red_party import PokemonRedPartyReader  # noqa: E402
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts  # noqa: E402

PLAN_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-cave-traversal-live-qualification-plan-2026-08-14.json"
)
EXPERIMENT_ID = "red-cave-traversal-live-qualification-v1"
SOURCE_CHECKPOINT_ID = "red-goal-v1-030-evolve_species-train-03"
QUALIFICATION_POLICY = CaveTraversalQualificationPolicy(
    minimum_successful_steps=2,
    maximum_successful_steps=12,
    maximum_movement_attempts=48,
    require_excluded_transition_skip=True,
)


class RedCaveTraversalRunError(RuntimeError):
    """Raised before the qualification can overstate its evidence."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--envelope", type=Path, default=None)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--private-root", type=Path, default=None)
    parser.add_argument("--exact-ci-run", type=int, default=None)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="consume the deterministic one-shot qualification identity",
    )
    return parser


def _mapping(source: dict[str, object], key: str) -> dict[str, object]:
    value = source.get(key)
    if not isinstance(value, dict):
        raise RedCaveTraversalRunError(f"Cave qualification plan {key} is invalid")
    return value


def _load_plan() -> tuple[dict[str, object], str]:
    payload = PLAN_PATH.read_bytes()
    try:
        value = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RedCaveTraversalRunError("Cave qualification plan is invalid") from error
    if not isinstance(value, dict):
        raise RedCaveTraversalRunError("Cave qualification plan is not an object")
    if (
        value.get("schema")
        != "pokemon-red-cave-traversal-live-qualification-plan-v1"
        or value.get("status") != "prospective_unexecuted"
        or value.get("experiment_id") != EXPERIMENT_ID
    ):
        raise RedCaveTraversalRunError("Cave qualification plan identity is unsupported")
    root = _mapping(value, "authenticated_root")
    if (
        root.get("checkpoint_id") != SOURCE_CHECKPOINT_ID
        or root.get("partition") != "train"
        or root.get("independent_from_v2_root") is not True
        or root.get("sealed_test") is not False
        or root.get("crystal") is not False
    ):
        raise RedCaveTraversalRunError("Cave qualification root boundary drifted")
    planned_policy = _mapping(value, "qualification_policy")
    expected_policy = {
        **QUALIFICATION_POLICY.public_dict(),
        "route_and_recovery_calls": 1,
        "require_entry_on_declared_transition": True,
        "require_full_recovery_before_walking": True,
        "unexpected_map_departure_fails": True,
        "battle_before_minimum_steps_fails": True,
        "battle_after_minimum_steps_is_a_natural_terminal": True,
        "battle_commands_allowed": 0,
        "candidate_count": 1,
    }
    if planned_policy != expected_policy:
        raise RedCaveTraversalRunError("Cave qualification policy differs from its plan")
    execution = _mapping(value, "execution")
    if (
        execution.get("exact_published_source_required") is not True
        or execution.get("exact_commit_ci_success_required_before_execution") is not True
        or execution.get("read_only_preflight_required") is not True
        or execution.get("open_private_artifact_before_first_controller_input") is not True
        or execution.get("execute_exactly_once") is not True
        or execution.get("retry_after_observation") is not False
        or execution.get("save_cartridge_state") is not False
    ):
        raise RedCaveTraversalRunError("Cave qualification execution boundary drifted")
    protected = _mapping(value, "protected_access")
    if set(protected.values()) != {0} or value.get("private_path_fields") != 0:
        raise RedCaveTraversalRunError("Cave qualification protected-access boundary drifted")
    return value, hashlib.sha256(payload).hexdigest()


def _stable_boundary(
    emulator: PyBoyAdapter,
) -> tuple[PokemonRedStateReader, PartyObservation]:
    reader = PokemonRedStateReader(emulator)
    raw = reader.read()
    if (
        not raw.game_started
        or raw.map_id != MapId.CINNABAR_POKECENTER
        or (raw.player_x, raw.player_y) != (3, 3)
        or raw.battle_state != 0
        or not reader.read_input_readiness().ready
    ):
        raise RedCaveTraversalRunError(
            "Cave qualification root is not the frozen ready Center nurse boundary"
        )
    party = PokemonRedPartyReader(emulator).read()
    if party.size != 6 or party.fainted_count:
        raise RedCaveTraversalRunError(
            "Cave qualification root is not a live full party"
        )
    if any(member.experience is None for member in party.members):
        raise RedCaveTraversalRunError(
            "Cave qualification root lacks exact party experience"
        )
    return reader, party


def _party_summary(party: PartyObservation) -> dict[str, int]:
    return {
        "party_size": party.size,
        "fainted_members": party.fainted_count,
        "damaged_members": sum(member.hp < member.max_hp for member in party.members),
        "statused_members": sum(
            member.status is not StatusCondition.HEALTHY for member in party.members
        ),
    }


def _require_planned_party_summary(
    plan: dict[str, object],
    party: PartyObservation,
) -> dict[str, int]:
    root = _mapping(plan, "authenticated_root")
    observed = _party_summary(party)
    expected = {
        "party_size": root.get("initial_party_size"),
        "fainted_members": root.get("initial_fainted_members"),
        "damaged_members": root.get("initial_damaged_members"),
        "statused_members": root.get("initial_statused_members"),
    }
    if observed != expected:
        raise RedCaveTraversalRunError(
            "Cave qualification party summary differs from its plan"
        )
    return observed


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.execute and (args.private_root is None or args.exact_ci_run is None):
        raise RedCaveTraversalRunError(
            "Cave qualification execution requires private storage and exact CI"
        )
    if args.exact_ci_run is not None and (
        type(args.exact_ci_run) is not int or args.exact_ci_run <= 0  # noqa: E721
    ):
        raise RedCaveTraversalRunError("Cave qualification CI identity is invalid")

    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - clean source establishes this
        raise AssertionError("clean source identity lacks a commit")
    plan, plan_sha256 = _load_plan()
    authenticated = _mapping(plan, "authenticated_root")

    state_path = args.state
    envelope_path = args.envelope or Path(f"{state_path}.json")
    state_sha256_before = hashlib.sha256(state_path.read_bytes()).hexdigest()
    envelope_sha256_before = hashlib.sha256(envelope_path.read_bytes()).hexdigest()
    capture: CapturedProgressEnvelope = load_captured_progress(
        envelope_path,
        state_path=state_path,
    )
    if (
        capture.checkpoint_id != SOURCE_CHECKPOINT_ID
        or capture.state_sha256 != authenticated.get("state_sha256")
        or envelope_sha256_before != authenticated.get("capture_envelope_sha256")
    ):
        raise RedCaveTraversalRunError(
            "Cave qualification capture differs from the prospective root"
        )

    registry = load_committed_goal_manager_registry(PROJECT_ROOT)
    if (
        source.git_commit != registry.execution.source_commit
        or working_source_bundle_sha256(PROJECT_ROOT)
        != registry.execution.source_bundle_sha256
    ):
        raise RedCaveTraversalRunError(
            "Cave qualification source differs from its execution registry"
        )
    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    if fingerprint.sha256 != authenticated.get("rom_sha256"):
        raise RedCaveTraversalRunError("Cave qualification ROM differs from its plan")
    adjacent_before = rom_adjacent_artifacts(rom_path)
    with PyBoyAdapter(rom_path) as emulator:
        emulator.load_state(state_path)
        _reader, party = _stable_boundary(emulator)
    initial_party = _require_planned_party_summary(plan, party)

    preflight = {
        "schema": "pokemon-red-cave-traversal-live-qualification-preflight-v1",
        "status": "ready",
        "experiment_id": EXPERIMENT_ID,
        "source_commit": source.git_commit,
        "source_bundle_sha256": registry.execution.source_bundle_sha256,
        "public_plan_sha256": plan_sha256,
        "root_checkpoint_id": SOURCE_CHECKPOINT_ID,
        "partition": "train",
        "initial_party": initial_party,
        "qualification_policy": QUALIFICATION_POLICY.public_dict(),
        "teacher_queries": 0,
        "teacher_choice_targets": 0,
        "red_sealed_test_cases_opened": 0,
        "crystal_contexts_opened": 0,
        "full_game_replays": 0,
        "private_path_fields": 0,
    }
    if not args.execute:
        return preflight

    artifact_id = f"red-cave-traversal-{source.git_commit[:12]}-{capture.state_sha256[:12]}"
    private_root = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
    writer = private_root.begin_artifact(
        artifact_id,
        kind="cave_traversal_live_qualification",
    )
    result = None
    frames_executed = 0
    controller_actions = 0
    with writer:
        writer.append(
            "catalog",
            {
                "record_type": "cave_traversal_qualification_catalog",
                "source": source.public_dict(),
                "exact_ci_run": args.exact_ci_run,
                "public_plan_sha256": plan_sha256,
                "root_checkpoint_id": SOURCE_CHECKPOINT_ID,
                "state_sha256": capture.state_sha256,
                "initial_party": initial_party,
                "qualification_policy": QUALIFICATION_POLICY.public_dict(),
                "teacher_queries": 0,
                "teacher_choice_targets": 0,
            },
        )
        try:
            with PyBoyAdapter(rom_path) as emulator:
                emulator.load_state(state_path)
                reader, execute_party = _stable_boundary(emulator)
                if execute_party != party:
                    raise RedCaveTraversalRunError(
                        "Cave qualification clone differs from preflight"
                    )
                controller = CountingExecutor(
                    FrameSafeExecutor(
                        emulator,
                        DEFAULT_NEW_GAME_TIMING.controller_timing(),
                    )
                )
                start_frame = emulator.frame_count
                result = run_cave_traversal_qualification(
                    controller,
                    reader,
                    emulator,
                    venue=DIGLETTS_CAVE_TRAINING_VENUE,
                    policy=QUALIFICATION_POLICY,
                )
                frames_executed = emulator.frame_count - start_frame
                controller_actions = controller.actions_executed
                final = reader.read()
                writer.append(
                    "qualifications",
                    {
                        "record_type": "cave_traversal_live_qualification",
                        "status": "passed",
                        "result": result.public_dict(),
                        "private_final_map_id": final.map_id,
                        "private_final_coordinate": [final.player_x, final.player_y],
                        "frames_executed": frames_executed,
                        "controller_actions": controller_actions,
                        "battle_commands_executed": 0,
                        "teacher_queries": 0,
                        "teacher_choice_targets": 0,
                    },
                )
        except Exception as error:
            writer.append(
                "qualifications",
                {
                    "record_type": "cave_traversal_live_qualification",
                    "status": "failed",
                    "failure_type": type(error).__name__,
                    "teacher_queries": 0,
                    "teacher_choice_targets": 0,
                },
            )
            raise

    if result is None:  # pragma: no cover - writer success implies a result
        raise AssertionError("Cave qualification completed without a result")
    if hashlib.sha256(state_path.read_bytes()).hexdigest() != state_sha256_before:
        raise RedCaveTraversalRunError("Cave qualification capture changed")
    if hashlib.sha256(envelope_path.read_bytes()).hexdigest() != envelope_sha256_before:
        raise RedCaveTraversalRunError("Cave qualification envelope changed")
    if rom_adjacent_artifacts(rom_path) != adjacent_before:
        raise RedCaveTraversalRunError("Cave qualification created a ROM-adjacent artifact")

    return {
        **preflight,
        "schema": "pokemon-red-cave-traversal-live-qualification-receipt-v1",
        "status": "complete_live_qualified",
        "exact_ci_run": args.exact_ci_run,
        "artifact": writer.summary.public_dict(),
        "qualification": result.public_dict(),
        "frames_executed": frames_executed,
        "controller_actions": controller_actions,
        "battle_commands_executed": 0,
        "training_example_added": False,
        "model_fit": False,
        "authority_promoted": False,
        "state_saved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        payload = _run(args)
    except Exception as error:
        if isinstance(error, KeyboardInterrupt):  # pragma: no cover
            raise
        parser.error(
            "Red Cave traversal qualification failed closed; private paths were withheld. "
            f"Failure type: {type(error).__name__}."
        )
    print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
