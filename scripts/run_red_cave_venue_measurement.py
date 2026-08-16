#!/usr/bin/env python3
"""Preflight or execute one independent Red Cave venue measurement."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.blaine import (  # noqa: E402
    DIGLETT_SPECIES_ID,
    DIGLETTS_CAVE_TRAINING_VENUE,
    MANSION_BALANCED_TEAM_TRAINING_INTENT,
    MANSION_ESCORT_ENEMY_SPECIES,
    MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
    MANSION_MAX_CONSECUTIVE_FLEES,
    MANSION_TRAINING_FLEE_TIMING,
    MANSION_VOLATILE_ENEMY_SPECIES,
    ROUTE_11_TRAINING_VENUE,
    _flee,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING  # noqa: E402
from pokemon_red_completion.captured_progress import (  # noqa: E402
    load_captured_progress,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.goal_manager_context_catalog import (  # noqa: E402
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (  # noqa: E402
    load_committed_goal_manager_registry,
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.hideout import DEFAULT_HIDEOUT_TIMING  # noqa: E402
from pokemon_red_completion.observation import MapId, PokemonRedStateReader  # noqa: E402
from pokemon_red_completion.party import PartyObservation  # noqa: E402
from pokemon_red_completion.party_development_question_reservations import (  # noqa: E402
    PartyDevelopmentQuestionReservationPlan,
)
from pokemon_red_completion.party_development_venue_priors import (  # noqa: E402
    PartyDevelopmentVenuePriorRegistry,
    VenuePriorMeasurementContract,
)
from pokemon_red_completion.private_artifacts import open_private_root  # noqa: E402
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_cave_venue_measurement import (  # noqa: E402
    RED_CAVE_CONTEXT_CATALOG_FILE_SHA256,
    RED_CAVE_CONTEXT_CATALOG_REGISTRY_SHA256,
    RED_CAVE_CONTEXT_CATALOG_SOURCE_COMMIT,
    RED_CAVE_FINAL_TARGET_LEVEL,
    RED_CAVE_INITIAL_TARGET_LEVEL,
    RED_CAVE_PROGRESS_UNITS_REQUIRED,
    RED_CAVE_RESERVATION_PLAN_FILE_SHA256,
    RED_CAVE_RESERVATION_PLAN_SHA256,
    RED_CAVE_SUPPORT_ASSIGNMENT_ID,
    RED_CAVE_SUPPORT_CHECKPOINT_ID,
    RED_CAVE_SUPPORT_ENVELOPE_SHA256,
    RED_CAVE_SUPPORT_ROOT_LINEAGE_ID,
    RED_CAVE_SUPPORT_STATE_SHA256,
    RED_CAVE_TARGET_SLOT,
    RED_CAVE_VENUE_MEASUREMENT_ARTIFACT_ID,
    RED_CAVE_VENUE_MEASUREMENT_RESULT_SCHEMA,
    RED_CAVE_VENUE_PRIOR_REGISTRY_FILE_SHA256,
    RED_CAVE_VENUE_PRIOR_REGISTRY_SHA256,
    RED_ROM_SHA256,
    load_red_cave_venue_measurement_plan,
    red_cave_venue_binding_sha256,
)
from pokemon_red_completion.red_party import (  # noqa: E402
    DUGTRIO_SPECIES_ID,
    PokemonRedPartyReader,
)
from pokemon_red_completion.red_party_development_venue_priors import (  # noqa: E402
    RED_PARTY_DEVELOPMENT_OUTCOME_POLICY,
)
from pokemon_red_completion.red_team_training import (  # noqa: E402
    TeamTrainingExecutionSummary,
    run_red_team_balancing,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts  # noqa: E402
from pokemon_red_completion.training_candidate_rank import (  # noqa: E402
    TrainingCandidateDecision,
)

DEFAULT_PLAN_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-cave-venue-measurement-plan-2026-08-15.json"
)


class RedCaveVenueMeasurementRunError(RuntimeError):
    """Raised before the Cave measurement can overstate or replace evidence."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--envelope", type=Path, default=None)
    parser.add_argument("--reservation-plan", type=Path, required=True)
    parser.add_argument("--reservation-plan-file-sha256", required=True)
    parser.add_argument("--venue-prior-registry", type=Path, required=True)
    parser.add_argument("--venue-prior-registry-file-sha256", required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--context-catalog-file-sha256", required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--private-root", type=Path, default=None)
    parser.add_argument("--exact-ci-run", type=int, default=None)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="consume the prospective one-shot Cave measurement",
    )
    return parser


def _require_external(path: Path, *, subject: str) -> Path:
    resolved = path.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise RedCaveVenueMeasurementRunError(
            f"private {subject} must remain outside the repository"
        )
    return resolved


def _validate_execution_request(
    *,
    execute: bool,
    private_root: Path | None,
    exact_ci_run: int | None,
) -> tuple[Path, int] | None:
    if exact_ci_run is not None and (
        type(exact_ci_run) is not int or exact_ci_run <= 0  # noqa: E721
    ):
        raise RedCaveVenueMeasurementRunError("exact CI run identity is invalid")
    if not execute:
        return None
    if private_root is None or exact_ci_run is None:
        raise RedCaveVenueMeasurementRunError(
            "execution requires a private root and exact green CI run identity"
        )
    return private_root, exact_ci_run


def _require_designated_private_root(
    private_root: Path,
    *,
    protected_inputs: tuple[Path, ...],
) -> Path:
    resolved_root = _require_external(private_root, subject="artifact root")
    if not all(path.resolve().is_relative_to(resolved_root) for path in protected_inputs):
        raise RedCaveVenueMeasurementRunError(
            "execution root does not contain every authenticated protected input"
        )
    return resolved_root


def _require_protected_files_unchanged(expected_digests: Mapping[Path, str]) -> None:
    try:
        observed = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in expected_digests
        }
    except OSError:
        raise RedCaveVenueMeasurementRunError(
            "Cave measurement could not revalidate every protected input"
        ) from None
    if observed != expected_digests:
        raise RedCaveVenueMeasurementRunError(
            "Cave measurement changed a protected input"
        )


def _require_rom_adjacent_unchanged(
    rom_path: Path,
    expected: tuple[tuple[bool, str | None], ...],
    *,
    operation: str,
) -> None:
    if rom_adjacent_artifacts(rom_path) != expected:
        raise RedCaveVenueMeasurementRunError(
            f"Cave {operation} created a ROM-adjacent artifact"
        )


def _load_private_json(
    path: Path,
    *,
    expected_sha256: str,
    subject: str,
) -> Mapping[str, object]:
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise RedCaveVenueMeasurementRunError(f"{subject} file digest differs")
    try:
        value = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RedCaveVenueMeasurementRunError(f"{subject} is invalid") from error
    if not isinstance(value, Mapping):
        raise RedCaveVenueMeasurementRunError(f"{subject} is not an object")
    return value


def _require_independent_support(
    reservation_plan: PartyDevelopmentQuestionReservationPlan,
    venue_registry: PartyDevelopmentVenuePriorRegistry,
    *,
    support_root_lineage_id: str,
) -> None:
    if (
        reservation_plan.plan_sha256 != RED_CAVE_RESERVATION_PLAN_SHA256
        or reservation_plan.venue_prior_registry_sha256
        != RED_CAVE_VENUE_PRIOR_REGISTRY_SHA256
        or venue_registry.registry_sha256 != RED_CAVE_VENUE_PRIOR_REGISTRY_SHA256
        or len(reservation_plan.reservations) != 14
        or len(venue_registry.entries) != 1
    ):
        raise RedCaveVenueMeasurementRunError(
            "Cave support differs from the frozen question/prior identities"
        )
    if any(
        reservation.source_checkpoint_id == RED_CAVE_SUPPORT_CHECKPOINT_ID
        or reservation.source_state_sha256 == RED_CAVE_SUPPORT_STATE_SHA256
        for reservation in reservation_plan.reservations
    ):
        raise RedCaveVenueMeasurementRunError(
            "Cave support overlaps a reserved learner question"
        )
    if (
        support_root_lineage_id
        in reservation_plan.excluded_root_lineage_ids
        or RED_CAVE_SUPPORT_STATE_SHA256 in reservation_plan.excluded_state_sha256
    ):
        raise RedCaveVenueMeasurementRunError(
            "Cave support overlaps teacher or prior evidence"
        )
    venue_registry.require_scenario_is_independent(
        root_lineage_id=support_root_lineage_id,
        initial_state_sha256=RED_CAVE_SUPPORT_STATE_SHA256,
    )
    if venue_registry.evidence_for(DIGLETTS_CAVE_TRAINING_VENUE.band) is not None:
        raise RedCaveVenueMeasurementRunError(
            "Cave venue already has prior evidence; replacement is forbidden"
        )
    route_evidence = venue_registry.evidence_for(ROUTE_11_TRAINING_VENUE.band)
    if (
        route_evidence is None
        or route_evidence.measurement_contract_sha256
        != VenuePriorMeasurementContract().measurement_contract_sha256
    ):
        raise RedCaveVenueMeasurementRunError(
            "Cave measurement lacks one comparable existing venue prior"
        )


def _stable_party(
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
        raise RedCaveVenueMeasurementRunError(
            "Cave support is not the ready Cinnabar Center boundary"
        )
    party = PokemonRedPartyReader(emulator).read()
    target = party.member_in_slot(RED_CAVE_TARGET_SLOT)
    if (
        party.size != 6
        or party.fainted_count
        or target is None
        or target.species_id != DIGLETT_SPECIES_ID
        or target.level != RED_CAVE_INITIAL_TARGET_LEVEL
        or target.experience is None
        or any(member.experience is None for member in party.members)
    ):
        raise RedCaveVenueMeasurementRunError(
            "Cave support differs from the fixed healthy evolution party"
        )
    return reader, party


def _party_evidence(party: PartyObservation) -> dict[str, object]:
    return {
        "members": [
            {
                "slot": member.slot,
                "species_id": member.species_id,
                "level": member.level,
                "hp": member.hp,
                "max_hp": member.max_hp,
                "status": member.status.value,
                "experience": member.experience,
            }
            for member in party.members
        ]
    }


def _execute_measurement(
    *,
    rom_path: Path,
    state_path: Path,
    expected_party: PartyObservation,
) -> dict[str, object]:
    summaries: list[TeamTrainingExecutionSummary] = []
    candidate_decisions: list[TrainingCandidateDecision] = []
    with PyBoyAdapter(rom_path) as emulator:
        emulator.load_state(state_path)
        reader, before_party = _stable_party(emulator)
        if before_party != expected_party:
            raise RedCaveVenueMeasurementRunError(
                "Cave execution clone differs from its authenticated preflight"
            )
        before_target = before_party.member_in_slot(RED_CAVE_TARGET_SLOT)
        if before_target is None or before_target.experience is None:  # pragma: no cover
            raise AssertionError("Cave target disappeared after stable-party validation")
        controller = CountingExecutor(
            FrameSafeExecutor(
                emulator,
                DEFAULT_NEW_GAME_TIMING.controller_timing(),
            )
        )
        start_frame = emulator.frame_count
        run_red_team_balancing(
            controller,
            reader,
            emulator,
            policy=RED_PARTY_DEVELOPMENT_OUTCOME_POLICY,
            intent=MANSION_BALANCED_TEAM_TRAINING_INTENT,
            flee_timing=MANSION_TRAINING_FLEE_TIMING,
            hideout_timing=DEFAULT_HIDEOUT_TIMING,
            flee_func=_flee,  # type: ignore[arg-type]  # legacy emulator protocols
            volatile_enemy_species=MANSION_VOLATILE_ENEMY_SPECIES,
            escort_enemy_species=MANSION_ESCORT_ENEMY_SPECIES,
            max_consecutive_flees=MANSION_MAX_CONSECUTIVE_FLEES,
            cancel_interval=MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
            candidate_decision_sink=candidate_decisions.append,
            execution_summary_sink=summaries.append,
            evolution_target=(DIGLETT_SPECIES_ID, DUGTRIO_SPECIES_ID),
            venues=(DIGLETTS_CAVE_TRAINING_VENUE,),
            report_label="independent Cave venue measurement",
            checkpoint_count=1,
        )
        frames_executed = emulator.frame_count - start_frame
        if len(summaries) != 1:
            raise RedCaveVenueMeasurementRunError(
                "Cave execution did not retain exactly one bounded summary"
            )
        summary = summaries[0]
        after_party = PokemonRedPartyReader(emulator).read()
        after_target = after_party.member_in_slot(RED_CAVE_TARGET_SLOT)
        if (
            after_target is None
            or after_target.species_id != DUGTRIO_SPECIES_ID
            or after_target.level != RED_CAVE_FINAL_TARGET_LEVEL
            or after_target.experience is None
            or after_party.fainted_count
            or candidate_decisions
        ):
            raise RedCaveVenueMeasurementRunError(
                "Cave execution did not meet its fixed no-choice evolution objective"
            )
        progress_gained = after_target.level - before_target.level
        budgeted_center_calls = (
            summary.venue_transition_trips
            + summary.required_recovery_trips
            + summary.optional_recovery_trips
        )
        total_center_calls = budgeted_center_calls + summary.cleanup_trips
        if (
            progress_gained != RED_CAVE_PROGRESS_UNITS_REQUIRED
            or summary.progress.battles_completed > 200
            or summary.progress.steps_taken > 20_000
            or budgeted_center_calls > 50
            or summary.cleanup_trips != 1
            or summary.optional_recovery_trips != 0
            or summary.progress.faints != 0
            or summary.progress.healing_trips != total_center_calls
            or summary.traversal_instrumented_walkers != 1
            or summary.traversal_movement_attempts <= 0
            or controller.actions_executed <= 0
            or frames_executed <= 0
        ):
            raise RedCaveVenueMeasurementRunError(
                "Cave execution violated its prospective operating bounds"
            )
        return {
            "record_type": "independent_cave_venue_measurement",
            "venue_binding_sha256": red_cave_venue_binding_sha256(),
            "private_venue_binding": DIGLETTS_CAVE_TRAINING_VENUE.band.area_id,
            "before_party": _party_evidence(before_party),
            "after_party": _party_evidence(after_party),
            "objective_completed": True,
            "progress_units_gained": progress_gained,
            "progress_units_required": RED_CAVE_PROGRESS_UNITS_REQUIRED,
            "target_experience_gained": (
                after_target.experience - before_target.experience
            ),
            "battles_completed": summary.progress.battles_completed,
            "steps_taken": summary.progress.steps_taken,
            "faints": summary.progress.faints,
            "venue_transition_trips": summary.venue_transition_trips,
            "required_recovery_trips": summary.required_recovery_trips,
            "optional_recovery_trips": summary.optional_recovery_trips,
            "cleanup_trips": summary.cleanup_trips,
            "budgeted_center_calls": budgeted_center_calls,
            "total_counted_center_routes": total_center_calls,
            "rotations_executed": summary.rotations_executed,
            "traversal_instrumented_walkers": (
                summary.traversal_instrumented_walkers
            ),
            "traversal_movement_attempts": summary.traversal_movement_attempts,
            "traversal_successful_steps": summary.traversal_successful_steps,
            "traversal_blocked_attempts": summary.traversal_blocked_attempts,
            "frames_executed": frames_executed,
            "controller_actions": controller.actions_executed,
            "candidate_decisions": 0,
            "teacher_queries": 0,
            "model_predictions": 0,
            "model_updates": 0,
            "learner_outcomes_opened": 0,
        }


def _run(args: argparse.Namespace) -> dict[str, object]:
    execution_request = _validate_execution_request(
        execute=args.execute,
        private_root=args.private_root,
        exact_ci_run=args.exact_ci_run,
    )
    if (
        args.reservation_plan_file_sha256
        != RED_CAVE_RESERVATION_PLAN_FILE_SHA256
        or args.venue_prior_registry_file_sha256
        != RED_CAVE_VENUE_PRIOR_REGISTRY_FILE_SHA256
        or args.context_catalog_file_sha256
        != RED_CAVE_CONTEXT_CATALOG_FILE_SHA256
    ):
        raise RedCaveVenueMeasurementRunError(
            "private input arguments differ from the prospective plan"
        )

    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - publication guard owns this
        raise AssertionError("published Cave measurement source lost its commit")
    source_bundle_sha256 = working_source_bundle_sha256(PROJECT_ROOT)
    registry = load_committed_goal_manager_registry(PROJECT_ROOT)
    if source_bundle_sha256 != registry.execution.source_bundle_sha256:
        raise RedCaveVenueMeasurementRunError(
            "Cave measurement source differs from its generated execution registry"
        )

    _plan, plan_file_sha256 = load_red_cave_venue_measurement_plan(args.plan)
    reservation_plan_path = _require_external(
        args.reservation_plan,
        subject="reservation plan",
    )
    venue_registry_path = _require_external(
        args.venue_prior_registry,
        subject="venue-prior registry",
    )
    context_catalog_path = _require_external(
        args.context_catalog,
        subject="historical context catalog",
    )
    reservation_plan = PartyDevelopmentQuestionReservationPlan.from_private_dict(
        _load_private_json(
            reservation_plan_path,
            expected_sha256=args.reservation_plan_file_sha256,
            subject="reservation plan",
        )
    )
    venue_registry = PartyDevelopmentVenuePriorRegistry.from_private_dict(
        _load_private_json(
            venue_registry_path,
            expected_sha256=args.venue_prior_registry_file_sha256,
            subject="venue-prior registry",
        )
    )
    context_catalog_document = _load_private_json(
        context_catalog_path,
        expected_sha256=args.context_catalog_file_sha256,
        subject="historical context catalog",
    )
    if (
        context_catalog_document.get("source_commit")
        != RED_CAVE_CONTEXT_CATALOG_SOURCE_COMMIT
        or context_catalog_document.get("registry_sha256")
        != RED_CAVE_CONTEXT_CATALOG_REGISTRY_SHA256
    ):
        raise RedCaveVenueMeasurementRunError(
            "historical context catalog identity differs from the prospective plan"
        )
    historical_registry = load_committed_goal_manager_registry_at_revision(
        PROJECT_ROOT,
        RED_CAVE_CONTEXT_CATALOG_SOURCE_COMMIT,
    )
    context_catalog = parse_goal_manager_context_catalog(
        context_catalog_path.read_bytes(),
        historical_registry,
    )
    support_entry = context_catalog.entry(RED_CAVE_SUPPORT_CHECKPOINT_ID)
    support_root_lineage_id = support_entry.authenticated_root_lineage_id(
        slot_id=RED_CAVE_SUPPORT_CHECKPOINT_ID,
        capture_id=RED_CAVE_SUPPORT_CHECKPOINT_ID,
        state_sha256=RED_CAVE_SUPPORT_STATE_SHA256,
        envelope_sha256=RED_CAVE_SUPPORT_ENVELOPE_SHA256,
    )
    if (
        support_entry.assignment_id != RED_CAVE_SUPPORT_ASSIGNMENT_ID
        or support_root_lineage_id != RED_CAVE_SUPPORT_ROOT_LINEAGE_ID
    ):
        raise RedCaveVenueMeasurementRunError(
            "Cave support differs from its historical canonical lineage"
        )
    _require_independent_support(
        reservation_plan,
        venue_registry,
        support_root_lineage_id=support_root_lineage_id,
    )

    state_path = _require_external(args.state, subject="support state")
    envelope_path = _require_external(
        args.envelope or Path(f"{state_path}.json"),
        subject="support envelope",
    )
    protected_files = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (
            state_path,
            envelope_path,
            reservation_plan_path,
            venue_registry_path,
            context_catalog_path,
        )
    }
    designated_private_root = (
        None
        if execution_request is None
        else _require_designated_private_root(
            execution_request[0],
            protected_inputs=tuple(protected_files),
        )
    )
    if (
        protected_files[state_path] != RED_CAVE_SUPPORT_STATE_SHA256
        or protected_files[envelope_path] != RED_CAVE_SUPPORT_ENVELOPE_SHA256
    ):
        raise RedCaveVenueMeasurementRunError(
            "Cave support bytes differ from the prospective root"
        )
    capture = load_captured_progress(envelope_path, state_path=state_path)
    if (
        capture.checkpoint_id != RED_CAVE_SUPPORT_CHECKPOINT_ID
        or capture.state_sha256 != RED_CAVE_SUPPORT_STATE_SHA256
    ):
        raise RedCaveVenueMeasurementRunError(
            "Cave capture identity differs from the prospective root"
        )

    rom_path = resolve_rom_path(args.rom)
    if verify_rom(rom_path).sha256 != RED_ROM_SHA256:
        raise RedCaveVenueMeasurementRunError("Cave measurement ROM differs")
    adjacent_before = rom_adjacent_artifacts(rom_path)
    with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
        emulator.load_state(state_path)
        _reader, party = _stable_party(emulator)

    preflight = {
        "schema": "pokemon.red.party-development-cave-venue-measurement-preflight.v1",
        "status": "ready",
        "source_commit": source.git_commit,
        "source_bundle_sha256": source_bundle_sha256,
        "public_plan_file_sha256": plan_file_sha256,
        "measurement_contract_sha256": (
            VenuePriorMeasurementContract().measurement_contract_sha256
        ),
        "venue_binding_sha256": red_cave_venue_binding_sha256(),
        "independent_of_reserved_questions": True,
        "independent_of_existing_priors": True,
        "historical_context_catalog_sha256": context_catalog.catalog_sha256,
        "canonical_root_lineage_authenticated": True,
        "candidate_menus_constructed": 0,
        "controller_actions": 0,
        "teacher_queries": 0,
        "model_predictions": 0,
        "model_updates": 0,
        "learner_outcomes_opened": 0,
        "sealed_red_cases_opened": 0,
        "crystal_cases_opened": 0,
        "full_game_replays": 0,
        "venue_prior_entries_added": 0,
        "authority_promoted": False,
        "private_path_fields": 0,
    }
    if not args.execute:
        _require_rom_adjacent_unchanged(
            rom_path,
            adjacent_before,
            operation="preflight",
        )
        return preflight

    if execution_request is None or designated_private_root is None:  # pragma: no cover
        raise AssertionError("validated Cave execution request disappeared")
    _requested_private_root, exact_ci_run = execution_request
    private_root = open_private_root(
        designated_private_root,
        repository_root=PROJECT_ROOT,
    )
    writer = private_root.begin_artifact(
        RED_CAVE_VENUE_MEASUREMENT_ARTIFACT_ID,
        kind="party_development_venue_measurement",
    )
    with writer:
        writer.append(
            "plan",
            {
                "record_type": "independent_cave_venue_measurement_plan",
                "source": source.public_dict(),
                "source_bundle_sha256": source_bundle_sha256,
                "exact_ci_run": exact_ci_run,
                "public_plan_file_sha256": plan_file_sha256,
                "reservation_plan_sha256": reservation_plan.plan_sha256,
                "venue_prior_registry_sha256": venue_registry.registry_sha256,
                "root_lineage_id": support_root_lineage_id,
                "initial_state_sha256": RED_CAVE_SUPPORT_STATE_SHA256,
                "venue_binding_sha256": red_cave_venue_binding_sha256(),
                "teacher_queries": 0,
                "model_predictions": 0,
                "learner_outcomes_opened": 0,
            },
        )
        measurement = _execute_measurement(
            rom_path=rom_path,
            state_path=state_path,
            expected_party=party,
        )
        writer.append("measurement", measurement)
        # These postconditions run before the writer can publish a complete
        # artifact.  A violation therefore retains a consumed failed attempt,
        # never a result that another process could mistake for valid evidence.
        _require_protected_files_unchanged(protected_files)
        _require_rom_adjacent_unchanged(
            rom_path,
            adjacent_before,
            operation="measurement",
        )

    return {
        **preflight,
        "schema": RED_CAVE_VENUE_MEASUREMENT_RESULT_SCHEMA,
        "status": "complete",
        "exact_ci_run": exact_ci_run,
        "artifact": writer.summary.public_dict(),
        "measurement": {
            key: measurement[key]
            for key in (
                "objective_completed",
                "progress_units_gained",
                "progress_units_required",
                "target_experience_gained",
                "battles_completed",
                "steps_taken",
                "faints",
                "venue_transition_trips",
                "required_recovery_trips",
                "optional_recovery_trips",
                "cleanup_trips",
                "budgeted_center_calls",
                "total_counted_center_routes",
                "rotations_executed",
                "traversal_instrumented_walkers",
                "traversal_movement_attempts",
                "traversal_successful_steps",
                "traversal_blocked_attempts",
                "frames_executed",
                "controller_actions",
                "candidate_decisions",
            )
        },
        "candidate_menus_constructed": 0,
        "learner_outcomes_opened": 0,
        "model_fit": False,
        "venue_prior_entries_added": 0,
        "authority_promoted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        result = _run(args)
    except Exception as error:
        if isinstance(error, KeyboardInterrupt):  # pragma: no cover
            raise
        parser.error(
            "Red Cave venue measurement failed closed; private paths were withheld. "
            f"Failure type: {type(error).__name__}."
        )
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
