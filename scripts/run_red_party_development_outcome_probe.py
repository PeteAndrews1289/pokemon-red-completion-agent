#!/usr/bin/env python3
"""Preflight or execute the frozen Red evolution-venue outcome probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
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
    MANSION_TEAM_POLICY,
    MANSION_TRAINING_FLEE_TIMING,
    MANSION_VOLATILE_ENEMY_SPECIES,
    ROUTE_11_TRAINING_VENUE,
    _flee,
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
from pokemon_red_completion.hideout import DEFAULT_HIDEOUT_TIMING  # noqa: E402
from pokemon_red_completion.observation import MapId, PokemonRedStateReader  # noqa: E402
from pokemon_red_completion.party import (  # noqa: E402
    PartyObservation,
)
from pokemon_red_completion.private_artifacts import open_private_root  # noqa: E402
from pokemon_red_completion.provenance import (  # noqa: E402
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_party import (  # noqa: E402
    DUGTRIO_SPECIES_ID,
    PokemonRedPartyReader,
)
from pokemon_red_completion.red_party_development_outcome_probe import (  # noqa: E402
    RED_PARTY_DEVELOPMENT_ORDER_RULE,
    RED_PARTY_DEVELOPMENT_SCENARIO_ID,
    BoundedEvolutionVenueQuestion,
    build_bounded_evolution_venue_question,
)
from pokemon_red_completion.red_team_training import (  # noqa: E402
    TeamTrainingExecutionSummary,
    run_red_team_balancing,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts  # noqa: E402
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402
from pokemon_red_completion.scenario_outcome_adapters import (  # noqa: E402
    PARTY_DEVELOPMENT_OBJECTIVE,
    PartyDevelopmentOutcomeTrial,
    adapt_party_development_outcomes,
)
from pokemon_red_completion.team_training import (  # noqa: E402
    TeamTrainingProgress,
)
from pokemon_red_completion.training_candidate_rank import (  # noqa: E402
    TrainingCandidateDecision,
    TrainingChoiceKind,
)

PLAN_PATH = (
    PROJECT_ROOT / "docs" / "evidence" / "red-party-development-outcome-plan-v2-2026-08-14.json"
)
SOURCE_CHECKPOINT_ID = "red-goal-v1-029-evolve_species-train-02"
NATURAL_VENUES = (
    ROUTE_11_TRAINING_VENUE,
    DIGLETTS_CAVE_TRAINING_VENUE,
)
OUTCOME_POLICY = replace(
    MANSION_TEAM_POLICY,
    retreat_hp_ratio=0.45,
    reserve_total_pp=2,
    max_battles=200,
    max_steps=20_000,
    max_healing_trips=50,
    max_faints=0,
)


class RedPartyDevelopmentRunError(RuntimeError):
    """Raised before a bounded party comparison can overstate its evidence."""


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
        help="consume the deterministic one-shot private artifact",
    )
    return parser


def _mapping(source: dict[str, object], key: str) -> dict[str, object]:
    value = source.get(key)
    if not isinstance(value, dict):
        raise RedPartyDevelopmentRunError(f"party plan {key} is invalid")
    return value


def _load_plan() -> tuple[dict[str, object], str]:
    payload = PLAN_PATH.read_bytes()
    try:
        value = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RedPartyDevelopmentRunError("party plan is invalid") from error
    if not isinstance(value, dict):
        raise RedPartyDevelopmentRunError("party plan is not an object")
    if (
        value.get("schema") != "pokemon-red-party-development-outcome-plan-v2"
        or value.get("status") != "prospective_unexecuted"
        or value.get("experiment_id") != RED_PARTY_DEVELOPMENT_SCENARIO_ID
    ):
        raise RedPartyDevelopmentRunError("party plan identity is unsupported")
    objective = _mapping(value, "outcome_objective")
    if (
        objective.get("objective_id") != PARTY_DEVELOPMENT_OBJECTIVE.objective_id
        or objective.get("objective_sha256") != PARTY_DEVELOPMENT_OBJECTIVE.objective_sha256
    ):
        raise RedPartyDevelopmentRunError("party objective differs from its plan")
    construction = _mapping(value, "candidate_construction")
    if construction.get("candidate_order_rule") != RED_PARTY_DEVELOPMENT_ORDER_RULE:
        raise RedPartyDevelopmentRunError("party candidate order rule drifted")
    training_policy = _mapping(value, "training_policy")
    if (
        training_policy.get("retreat_hp_ratio") != OUTCOME_POLICY.retreat_hp_ratio
        or training_policy.get("reserve_total_pp") != OUTCOME_POLICY.reserve_total_pp
        or training_policy.get("minimum_direct_level_advantage")
        != OUTCOME_POLICY.minimum_direct_level_advantage
        or training_policy.get("safe_escort_level") != OUTCOME_POLICY.safe_lead_level
        or training_policy.get("maximum_battles") != OUTCOME_POLICY.max_battles
        or training_policy.get("maximum_steps") != OUTCOME_POLICY.max_steps
        or training_policy.get("max_healing_trips_runtime_value")
        != OUTCOME_POLICY.max_healing_trips
        or training_policy.get("maximum_budgeted_center_calls") != OUTCOME_POLICY.max_healing_trips
        or training_policy.get("budgeted_center_call_phases")
        != ["venue_transition", "required_recovery", "optional_recovery"]
        or training_policy.get("final_cleanup_outside_budget_but_counted") is not True
        or training_policy.get("required_final_cleanup_calls") != 1
        or training_policy.get("maximum_faints") != OUTCOME_POLICY.max_faints
        or training_policy.get("optional_heal_selected_by_executor") is not False
    ):
        raise RedPartyDevelopmentRunError("party Center-call policy differs from its plan")
    return value, hashlib.sha256(payload).hexdigest()


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
        raise RedPartyDevelopmentRunError(
            "party capture is not the frozen ready Cinnabar Center nurse boundary"
        )
    party = PokemonRedPartyReader(emulator).read()
    if party.size != 6 or party.fainted_count:
        raise RedPartyDevelopmentRunError("party capture is not a healthy full team")
    if any(member.experience is None for member in party.members):
        raise RedPartyDevelopmentRunError("party capture lacks exact experience")
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


def _require_materialized_question(
    plan: dict[str, object],
    question: BoundedEvolutionVenueQuestion,
    party: PartyObservation,
) -> None:
    construction = _mapping(plan, "candidate_construction")
    target = _mapping(plan, "bounded_objective")
    target_member = party.member_in_slot(question.target_slot)
    if target_member is None:  # pragma: no cover - question establishes this
        raise AssertionError("party target binding disappeared")
    observed = (
        question.ordered_policy_input_sha256,
        question.target_slot,
        target_member.level,
        len(question.candidate_set.candidates),
        [venue.band.minimum_encounter_level for venue in question.venue_bindings],
        [venue.band.maximum_encounter_level for venue in question.venue_bindings],
    )
    expected = (
        construction.get("ordered_policy_input_sha256"),
        target.get("initial_target_slot"),
        target.get("initial_target_level"),
        construction.get("candidate_count"),
        construction.get("ordered_minimum_encounter_levels"),
        construction.get("ordered_maximum_encounter_levels"),
    )
    if observed != expected:
        raise RedPartyDevelopmentRunError("party venue candidates differ from the prospective plan")


def _target_experience(party: PartyObservation, target_slot: int) -> int:
    member = party.member_in_slot(target_slot)
    if member is None or member.experience is None:
        raise RedPartyDevelopmentRunError("party target experience is unavailable")
    return member.experience


def _execute_candidate(
    *,
    candidate_index: int,
    question: BoundedEvolutionVenueQuestion,
    expected_party: PartyObservation,
    rom_path: Path,
    state_path: Path,
) -> tuple[PartyDevelopmentOutcomeTrial, dict[str, object]]:
    candidate = question.candidate_set.candidates[candidate_index]
    selected_venue = question.venue_bindings[candidate_index]
    natural_index = NATURAL_VENUES.index(selected_venue)
    venue_decisions = 0
    summaries: list[TeamTrainingExecutionSummary] = []

    def force_frozen_venue(decision: TrainingCandidateDecision) -> int:
        nonlocal venue_decisions
        if (
            decision.observation.kind is not TrainingChoiceKind.VENUE
            or len(decision.observation.candidates) != 2
        ):
            raise RedPartyDevelopmentRunError("party execution changed its frozen venue choice set")
        venue_decisions += 1
        return natural_index

    with PyBoyAdapter(rom_path) as emulator:
        emulator.load_state(state_path)
        reader, before_party = _stable_party(emulator)
        if before_party != expected_party:
            raise RedPartyDevelopmentRunError(
                "party clone does not match the frozen starting observation"
            )
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
            policy=OUTCOME_POLICY,
            intent=MANSION_BALANCED_TEAM_TRAINING_INTENT,
            flee_timing=MANSION_TRAINING_FLEE_TIMING,
            hideout_timing=DEFAULT_HIDEOUT_TIMING,
            flee_func=_flee,
            volatile_enemy_species=MANSION_VOLATILE_ENEMY_SPECIES,
            escort_enemy_species=MANSION_ESCORT_ENEMY_SPECIES,
            max_consecutive_flees=MANSION_MAX_CONSECUTIVE_FLEES,
            cancel_interval=MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
            candidate_decision_authority=force_frozen_venue,
            execution_summary_sink=summaries.append,
            evolution_target=(DIGLETT_SPECIES_ID, DUGTRIO_SPECIES_ID),
            venues=NATURAL_VENUES,
            report_label="bounded party-development outcome probe",
            checkpoint_count=1,
        )
        if len(summaries) != 1 or venue_decisions < 1:
            raise RedPartyDevelopmentRunError(
                "party execution did not retain one exact bounded summary"
            )
        summary = summaries[0]
        budgeted_center_calls = (
            summary.venue_transition_trips
            + summary.required_recovery_trips
            + summary.optional_recovery_trips
        )
        if (
            budgeted_center_calls > OUTCOME_POLICY.max_healing_trips
            or summary.cleanup_trips != 1
            or summary.optional_recovery_trips != 0
        ):
            raise RedPartyDevelopmentRunError(
                "party execution violated its phase-separated Center-call contract"
            )
        after_party = PokemonRedPartyReader(emulator).read()
        after_target = after_party.member_in_slot(question.target_slot)
        if (
            after_target is None
            or after_target.species_id != question.final_species_id
            or after_party.fainted_count
        ):
            raise RedPartyDevelopmentRunError(
                "party execution did not verify the frozen evolution objective"
            )
        frames_executed = emulator.frame_count - start_frame
        trial = PartyDevelopmentOutcomeTrial(
            candidate=candidate,
            target_slot=question.target_slot,
            before_party=before_party,
            after_party=after_party,
            progress_before=TeamTrainingProgress(),
            progress_after=summary.progress,
            frames_executed=frames_executed,
            rotations_executed=summary.rotations_executed,
            evolution_completed=True,
        )
        retained = {
            "record_type": "bounded_party_development_trial",
            "candidate_index": candidate_index,
            "private_venue_binding": selected_venue.band.area_id,
            "candidate_sha256": canonical_sha256(candidate.public_dict()),
            "before_party": _party_evidence(before_party),
            "after_party": _party_evidence(after_party),
            "target_experience_gained": (
                _target_experience(after_party, question.target_slot)
                - _target_experience(before_party, question.target_slot)
            ),
            "execution": {
                **summary.public_dict(),
                "budgeted_center_calls": budgeted_center_calls,
            },
            "frames_executed": frames_executed,
            "controller_actions": controller.actions_executed,
            "venue_decisions": venue_decisions,
            "teacher_queries": 0,
            "teacher_choice_targets": 0,
        }
    return trial, retained


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.execute and (args.private_root is None or args.exact_ci_run is None):
        raise RedPartyDevelopmentRunError(
            "execution requires a private root and exact green CI run identity"
        )
    if args.exact_ci_run is not None and (
        type(args.exact_ci_run) is not int or args.exact_ci_run <= 0  # noqa: E721
    ):
        raise RedPartyDevelopmentRunError("exact CI run identity is invalid")
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
        raise RedPartyDevelopmentRunError(
            "party capture differs from the prospectively frozen root"
        )
    registry = load_committed_goal_manager_registry(PROJECT_ROOT)
    if (
        source.git_commit != registry.execution.source_commit
        or working_source_bundle_sha256(PROJECT_ROOT) != registry.execution.source_bundle_sha256
    ):
        raise RedPartyDevelopmentRunError(
            "party source differs from its committed execution registry"
        )
    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    if fingerprint.sha256 != authenticated.get("rom_sha256"):
        raise RedPartyDevelopmentRunError("party ROM differs from its plan")
    adjacent_before = rom_adjacent_artifacts(rom_path)
    with PyBoyAdapter(rom_path) as emulator:
        emulator.load_state(state_path)
        _reader, party = _stable_party(emulator)
    question = build_bounded_evolution_venue_question(
        party,
        OUTCOME_POLICY,
        NATURAL_VENUES,
        source_species_id=DIGLETT_SPECIES_ID,
        final_species_id=DUGTRIO_SPECIES_ID,
        initial_state_sha256=capture.state_sha256,
    )
    _require_materialized_question(plan, question, party)
    catalog = question.public_catalog()
    preflight = {
        "schema": "pokemon-red-party-development-outcome-preflight-v2",
        "status": "ready",
        "source_commit": source.git_commit,
        "source_bundle_sha256": registry.execution.source_bundle_sha256,
        "public_plan_sha256": plan_sha256,
        "catalog": catalog,
        "objective_id": PARTY_DEVELOPMENT_OBJECTIVE.objective_id,
        "objective_sha256": PARTY_DEVELOPMENT_OBJECTIVE.objective_sha256,
        "teacher_queries": 0,
        "teacher_choice_targets": 0,
        "red_sealed_test_cases_opened": 0,
        "crystal_contexts_opened": 0,
        "full_game_replays": 0,
        "private_path_fields": 0,
    }
    if not args.execute:
        return preflight

    artifact_id = f"red-party-outcome-{source.git_commit[:12]}-{capture.state_sha256[:12]}"
    root_lineage_id = f"red-party-root-{capture.state_sha256[:16]}"
    private_root = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
    writer = private_root.begin_artifact(
        artifact_id,
        kind="party_development_outcome_probe",
    )
    trials: list[PartyDevelopmentOutcomeTrial] = []
    retained_trials: list[dict[str, object]] = []
    with writer:
        writer.append(
            "catalog",
            {
                "record_type": "bounded_party_development_catalog",
                "source": source.public_dict(),
                "exact_ci_run": args.exact_ci_run,
                "public_plan_sha256": plan_sha256,
                "catalog": catalog,
                "catalog_sha256": canonical_sha256(catalog),
                "private_bindings": {
                    "target_slot": question.target_slot,
                    "source_species_id": question.source_species_id,
                    "final_species_id": question.final_species_id,
                    "ordered_venues": [venue.band.area_id for venue in question.venue_bindings],
                },
                "teacher_queries": 0,
                "teacher_choice_targets": 0,
            },
        )
        for candidate_index in range(2):
            trial, retained = _execute_candidate(
                candidate_index=candidate_index,
                question=question,
                expected_party=party,
                rom_path=rom_path,
                state_path=state_path,
            )
            writer.append("trials", retained)
            trials.append(trial)
            retained_trials.append(retained)
        example = adapt_party_development_outcomes(
            question.candidate_set,
            tuple(trials),
            scenario_id=RED_PARTY_DEVELOPMENT_SCENARIO_ID,
            root_lineage_id=root_lineage_id,
            initial_state_sha256=capture.state_sha256,
            partition=ScenarioPartition.TRAIN,
        )
        writer.append(
            "outcomes",
            {
                "record_type": "bounded_party_development_outcome_example",
                "example": example.public_dict(),
                "learner_update_eligible": example.learner_update_eligible,
                "best_candidate_indices": list(example.best_candidate_indices),
                "authority": "shadow_only",
            },
        )
    if hashlib.sha256(state_path.read_bytes()).hexdigest() != state_sha256_before:
        raise RedPartyDevelopmentRunError("party capture changed during execution")
    if hashlib.sha256(envelope_path.read_bytes()).hexdigest() != envelope_sha256_before:
        raise RedPartyDevelopmentRunError("party envelope changed during execution")
    if rom_adjacent_artifacts(rom_path) != adjacent_before:
        raise RedPartyDevelopmentRunError("party execution created a ROM-adjacent artifact")
    trial_summaries: list[dict[str, object]] = []
    for trial, retained in zip(trials, retained_trials, strict=True):
        execution = retained.get("execution")
        if not isinstance(execution, dict):
            raise RedPartyDevelopmentRunError(
                "party trial lacks phase-separated execution evidence"
            )
        phase_counts: dict[str, int] = {}
        for key in (
            "venue_transition_trips",
            "required_recovery_trips",
            "optional_recovery_trips",
            "cleanup_trips",
        ):
            value = execution.get(key)
            if type(value) is not int or value < 0:  # noqa: E721
                raise RedPartyDevelopmentRunError(
                    "party trial has invalid phase-separated execution evidence"
                )
            phase_counts[key] = value
        budgeted_center_calls = execution.get("budgeted_center_calls")
        expected_budgeted_center_calls = sum(
            phase_counts[key]
            for key in (
                "venue_transition_trips",
                "required_recovery_trips",
                "optional_recovery_trips",
            )
        )
        if (
            type(budgeted_center_calls) is not int  # noqa: E721
            or budgeted_center_calls != expected_budgeted_center_calls
            or expected_budgeted_center_calls > OUTCOME_POLICY.max_healing_trips
            or phase_counts["cleanup_trips"] != 1
            or expected_budgeted_center_calls + phase_counts["cleanup_trips"]
            != trial.progress_after.healing_trips
        ):
            raise RedPartyDevelopmentRunError(
                "party trial phase-separated execution evidence is inconsistent"
            )
        trial_summaries.append(
            {
                "candidate_index": trial.candidate_index,
                "target_experience_gained": (
                    _target_experience(trial.after_party, trial.target_slot)
                    - _target_experience(trial.before_party, trial.target_slot)
                ),
                "battles_completed": trial.progress_after.battles_completed,
                "steps_taken": trial.progress_after.steps_taken,
                "healing_trips": trial.progress_after.healing_trips,
                "venue_transition_trips": phase_counts["venue_transition_trips"],
                "required_recovery_trips": phase_counts["required_recovery_trips"],
                "optional_recovery_trips": phase_counts["optional_recovery_trips"],
                "cleanup_trips": phase_counts["cleanup_trips"],
                "budgeted_center_calls": budgeted_center_calls,
                "faints": trial.progress_after.faints,
                "rotations_executed": trial.rotations_executed,
                "frames_executed": trial.frames_executed,
                "evolution_completed": trial.evolution_completed,
            }
        )
    return {
        **preflight,
        "schema": "pokemon-red-party-development-outcome-receipt-v2",
        "status": "complete",
        "exact_ci_run": args.exact_ci_run,
        "artifact": writer.summary.public_dict(),
        "trials": trial_summaries,
        "fully_measured": example.fully_measured,
        "learner_update_eligible": example.learner_update_eligible,
        "best_candidate_indices": list(example.best_candidate_indices),
        "target_distribution": example.target_distribution.tolist(),
        "model_fit": False,
        "authority_promoted": False,
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
            "Red party-development outcome probe failed closed; private paths were withheld. "
            f"Failure type: {type(error).__name__}."
        )
    print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
