#!/usr/bin/env python3
"""Preflight or execute Red's frozen 14-question / 55-trial campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.blaine import (  # noqa: E402
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
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.gen1_cartridge import (  # noqa: E402
    Evolution,
    evolution_graph,
    internal_to_dex,
)
from pokemon_red_completion.goal_manager_context_catalog import (  # noqa: E402
    GoalManagerContextCapture,
    open_goal_manager_context_capture,
)
from pokemon_red_completion.hideout import DEFAULT_HIDEOUT_TIMING  # noqa: E402
from pokemon_red_completion.observation import PokemonRedStateReader  # noqa: E402
from pokemon_red_completion.party import (  # noqa: E402
    PartyMemberObservation,
    PartyObservation,
)
from pokemon_red_completion.party_development_adapter import (  # noqa: E402
    BoundPartyDevelopmentMenu,
)
from pokemon_red_completion.party_development_frozen_catalog import (  # noqa: E402
    PartyDevelopmentFrozenCatalog,
    PartyDevelopmentFrozenQuestion,
)
from pokemon_red_completion.party_development_outcome_campaign import (  # noqa: E402
    RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_COUNT,
    PartyDevelopmentOutcomeCampaignPlan,
    PartyDevelopmentOutcomeTrialAssignment,
    PartyDevelopmentOutcomeTrialClaim,
    party_development_outcome_record_ids,
)
from pokemon_red_completion.party_development_outcome_lineage import (  # noqa: E402
    PARTY_DEVELOPMENT_OUTCOME_CLAIM_KIND,
    PARTY_DEVELOPMENT_OUTCOME_TERMINAL_KIND,
    validate_successor_campaign_lineage,
)
from pokemon_red_completion.party_development_outcome_results import (  # noqa: E402
    PARTY_DEVELOPMENT_OUTCOME_PRIVATE_EVIDENCE_SCHEMA,
    PartyDevelopmentOutcomeTrialResult,
    assemble_party_development_outcome_examples,
    build_party_development_trial_terminal,
    parse_party_development_trial_terminal,
)
from pokemon_red_completion.party_development_outcomes import (  # noqa: E402
    PartyDevelopmentOutcomeTrialV2,
    adapt_party_development_outcomes_v2,
)
from pokemon_red_completion.party_development_question_reservations import (  # noqa: E402
    PartyDevelopmentContextPreparation,
    PartyDevelopmentQuestionReservation,
    PartyDevelopmentQuestionReservationPlan,
)
from pokemon_red_completion.party_development_venue_priors import (  # noqa: E402
    PartyDevelopmentVenuePriorRegistry,
)
from pokemon_red_completion.private_artifacts import (  # noqa: E402
    PrivateArtifactRoot,
    open_private_root,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_goal_context import (  # noqa: E402
    build_red_goal_context_runtime,
)
from pokemon_red_completion.red_goal_context_profile import (  # noqa: E402
    RedGoalContextProfile,
    load_red_goal_context_profile,
)
from pokemon_red_completion.red_party import PokemonRedPartyReader  # noqa: E402
from pokemon_red_completion.red_party_development_adapter import (  # noqa: E402
    RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY,
    RedPartyDevelopmentQuestionPreflight,
    build_red_party_development_snapshot,
    red_party_completion_snapshot,
)
from pokemon_red_completion.red_party_development_outcome_runtime import (  # noqa: E402
    BoundedActionExecutor,
    FrameBudgetEmulator,
    RedPartyDevelopmentTrialBinding,
    bind_red_party_development_outcome_trial,
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
from pokemon_red_completion.scenario_outcomes import (  # noqa: E402
    CandidateOutcome,
    OutcomeEvidenceStatus,
)
from pokemon_red_completion.team_training import (  # noqa: E402
    GrindingArea,
    TeamTrainingProgress,
)
from pokemon_red_completion.training_candidate_rank import (  # noqa: E402
    TrainingChoiceKind,
)

_MAX_JSON_BYTES = 8 * 1024 * 1024
_GITHUB_REPOSITORY = "PeteAndrews1289/pokemon-red-completion-agent"
_CI_WORKFLOW_NAME = "CI"
_CI_RUN_JSON_FIELDS = "attempt,conclusion,databaseId,event,headSha,status,url,workflowName"
_CLAIM_KIND = PARTY_DEVELOPMENT_OUTCOME_CLAIM_KIND
_TERMINAL_KIND = PARTY_DEVELOPMENT_OUTCOME_TERMINAL_KIND
_COLLECTION_ID_PREFIX = "red-party-development-outcomes-v1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_AUDIT_ACCEPTANCE_KEYS = frozenset(
    {
        "all_candidate_menus_reconstructed",
        "all_capture_envelope_joins_reconstructed",
        "all_reservation_joins_reconstructed",
        "all_root_lineages_reconstructed",
        "all_source_profile_joins_reconstructed",
        "committed_catalog_source_reproduced",
        "input_files_unchanged",
        "path_and_target_scan_clean",
        "rom_adjacent_artifacts_unchanged",
    }
)
_AUDIT_PROTECTED_COUNT_KEYS = frozenset(
    {
        "answers_selected",
        "controller_actions",
        "crystal_cases_opened",
        "model_predictions",
        "model_updates",
        "outcomes_opened",
        "sealed_red_cases_opened",
        "teacher_queries",
    }
)
_TRAINING_VENUES = (
    ROUTE_11_TRAINING_VENUE,
    DIGLETTS_CAVE_TRAINING_VENUE,
)


class RedPartyDevelopmentOutcomeCampaignRunError(RuntimeError):
    """Raised before campaign evidence can be silently changed or retried."""


@dataclass(frozen=True, slots=True)
class _QuestionRuntime:
    question: PartyDevelopmentFrozenQuestion
    reservation: PartyDevelopmentQuestionReservation
    capture: GoalManagerContextCapture
    profile: RedGoalContextProfile
    menu: (
        BoundPartyDevelopmentMenu[PartyMemberObservation]
        | BoundPartyDevelopmentMenu[GrindingArea]
    )
    venue_question_trainee: PartyMemberObservation | None
    assignments: tuple[PartyDevelopmentOutcomeTrialAssignment, ...]
    trial_bindings: tuple[RedPartyDevelopmentTrialBinding, ...]


@dataclass(frozen=True, slots=True)
class _TrialExecutionPorts:
    """Keep complete read authority separate from bounded input authority."""

    observation_emulator: PyBoyAdapter
    controller: FrameBudgetEmulator
    reader: PokemonRedStateReader
    party_reader: PokemonRedPartyReader


def _build_trial_execution_ports(
    emulator: PyBoyAdapter,
    *,
    maximum_frames: int,
) -> _TrialExecutionPorts:
    return _TrialExecutionPorts(
        observation_emulator=emulator,
        controller=FrameBudgetEmulator(
            emulator,
            maximum_frames=maximum_frames,
        ),
        reader=PokemonRedStateReader(emulator),
        party_reader=PokemonRedPartyReader(emulator),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-plan", type=Path, required=True)
    parser.add_argument("--campaign-plan-file-sha256", required=True)
    parser.add_argument("--predecessor-campaign-plan", type=Path, default=None)
    parser.add_argument(
        "--predecessor-campaign-plan-file-sha256",
        default=None,
    )
    parser.add_argument("--frozen-catalog", type=Path, required=True)
    parser.add_argument("--reservation-plan", type=Path, required=True)
    parser.add_argument("--venue-prior-registry", type=Path, required=True)
    parser.add_argument("--catalog-root", type=Path, required=True)
    parser.add_argument("--input-audit-receipt", type=Path, required=True)
    parser.add_argument("--private-artifact-root", type=Path, default=None)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--execute-authorized-plan-sha256",
        default=None,
        help="must equal the prospectively frozen plan digest",
    )
    return parser


def _require_external(path: Path, *, subject: str) -> Path:
    resolved = path.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            f"private {subject} must remain outside the repository"
        )
    return resolved


def _load_private_json(
    path: Path,
    *,
    expected_sha256: str,
    subject: str,
    external: bool = True,
) -> tuple[Mapping[str, object], bytes]:
    resolved = (
        _require_external(path, subject=subject) if external else path.resolve()
    )
    metadata = resolved.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            f"private {subject} must be a regular file"
        )
    payload = resolved.read_bytes()
    if (
        not payload
        or len(payload) > _MAX_JSON_BYTES
        or hashlib.sha256(payload).hexdigest() != expected_sha256
    ):
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            f"private {subject} file digest or size differs"
        )
    try:
        value = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            f"private {subject} is not valid ASCII JSON"
        ) from error
    if not isinstance(value, Mapping):
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            f"private {subject} is not an object"
        )
    return value, payload


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON object key")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> object:
    del value
    raise ValueError("non-finite JSON number")


def _require_exact_green_ci_run(
    exact_ci_run: int,
    exact_ci_attempt: int,
    *,
    source_commit: str,
) -> Mapping[str, object]:
    if (
        type(exact_ci_run) is not int  # noqa: E721
        or exact_ci_run <= 0
        or type(exact_ci_attempt) is not int  # noqa: E721
        or exact_ci_attempt <= 0
        or not isinstance(source_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
    ):
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "campaign CI identity is invalid"
        )
    command = (
        "gh",
        "run",
        "view",
        str(exact_ci_run),
        "--repo",
        _GITHUB_REPOSITORY,
        "--json",
        _CI_RUN_JSON_FIELDS,
    )
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env={**os.environ, "GH_PROMPT_DISABLED": "1"},
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "campaign could not authenticate exact CI"
        ) from error
    if completed.returncode != 0:
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "campaign could not authenticate exact CI"
        )
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "campaign CI evidence is invalid"
        ) from error
    expected_url = f"https://github.com/{_GITHUB_REPOSITORY}/actions/runs/{exact_ci_run}"
    if (
        not isinstance(document, Mapping)
        or document.get("databaseId") != exact_ci_run
        or document.get("headSha") != source_commit
        or document.get("status") != "completed"
        or document.get("conclusion") != "success"
        or document.get("workflowName") != _CI_WORKFLOW_NAME
        or document.get("event") != "pull_request"
        or document.get("url") != expected_url
        or document.get("attempt") != exact_ci_attempt
    ):
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "campaign CI is not the exact successful source-bound run"
        )
    return document


def _question_paths(
    catalog_root: Path,
    question: PartyDevelopmentFrozenQuestion,
) -> tuple[Path, Path, Path]:
    state = catalog_root / "captures" / f"{question.capture_id}.state"
    envelope = state.with_suffix(".state.json")
    profile = catalog_root / "profiles" / f"{question.profile_id}.json"
    for directory in (state.parent, profile.parent):
        metadata = directory.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise RedPartyDevelopmentOutcomeCampaignRunError(
                "campaign input directory is invalid"
            )
    for path in (state, envelope, profile):
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise RedPartyDevelopmentOutcomeCampaignRunError(
                "campaign question input is not a regular file"
            )
    return state, envelope, profile


def _execution_reservation(
    original: PartyDevelopmentQuestionReservation,
    question: PartyDevelopmentFrozenQuestion,
) -> PartyDevelopmentQuestionReservation:
    if (
        original.scenario_id != question.scenario_id
        or original.partition is not question.binding.partition
        or original.kind is not question.binding.kind
        or original.goal is not question.binding.goal
    ):
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "campaign question differs from its reserved semantics"
        )
    return replace(
        original,
        source_checkpoint_id=question.capture_id,
        source_state_sha256=question.binding.initial_state_sha256,
        source_envelope_sha256=question.capture_envelope_sha256,
        preparation=PartyDevelopmentContextPreparation.NONE,
        target_pp_bin=None,
    )


def _validate_input_audit(
    document: Mapping[str, object],
    *,
    plan: PartyDevelopmentOutcomeCampaignPlan,
    catalog: PartyDevelopmentFrozenCatalog,
) -> None:
    catalog_receipt = document.get("catalog")
    source_receipt = document.get("catalog_source")
    acceptance = document.get("acceptance")
    protected = document.get("protected_access")
    if (
        document.get("schema")
        != "pokemon.red.party-development-frozen-input-catalog-v1-audit.v1"
        or document.get("status") != "input_integrity_verified_outcomes_closed"
        or canonical_sha256(document) != plan.input_audit_result_sha256
        or not isinstance(catalog_receipt, Mapping)
        or catalog_receipt.get("catalog_file_sha256")
        != plan.frozen_catalog_file_sha256
        or catalog_receipt.get("catalog_sha256") != catalog.catalog_sha256
        or catalog_receipt.get("prospective_catalog_sha256")
        != catalog.prospective_catalog_sha256
        or catalog_receipt.get("question_count") != 14
        or catalog_receipt.get("candidate_row_count")
        != RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_COUNT
        or not isinstance(source_receipt, Mapping)
        or source_receipt.get("source_commit") != catalog.source_commit
        or source_receipt.get("source_bundle_sha256")
        != catalog.source_bundle_sha256
        or not isinstance(acceptance, Mapping)
        or set(acceptance) != _AUDIT_ACCEPTANCE_KEYS
        or any(acceptance.get(key) is not True for key in _AUDIT_ACCEPTANCE_KEYS)
        or not isinstance(protected, Mapping)
        or set(protected)
        != _AUDIT_PROTECTED_COUNT_KEYS | {"authority_promoted"}
        or any(
            type(protected.get(key)) is not int  # noqa: E721
            or protected.get(key) != 0
            for key in _AUDIT_PROTECTED_COUNT_KEYS
        )
        or protected.get("authority_promoted") is not False
    ):
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "campaign input-audit receipt does not authorize its frozen inputs"
        )


def _validate_execution_request(
    args: argparse.Namespace,
    *,
    expected_plan_sha256: str | None = None,
) -> None:
    """Reject ambiguous or over-broad execution flags before protected reads."""

    predecessor_path = getattr(args, "predecessor_campaign_plan", None)
    predecessor_digest = getattr(
        args, "predecessor_campaign_plan_file_sha256", None
    )
    predecessor_requested = (
        predecessor_path is not None or predecessor_digest is not None
    )
    if predecessor_requested and (
        not isinstance(predecessor_path, Path)
        or not isinstance(predecessor_digest, str)
        or _SHA256.fullmatch(predecessor_digest) is None
        or args.private_artifact_root is None
    ):
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "successor preflight needs the exact predecessor plan and private artifact root"
        )
    if args.watch and not args.execute:
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "watch mode is presentation for an authorized execution only"
        )
    if not args.execute:
        if args.execute_authorized_plan_sha256 is not None:
            raise RedPartyDevelopmentOutcomeCampaignRunError(
                "campaign authorization digest was supplied without execution"
            )
        if args.private_artifact_root is not None and not predecessor_requested:
            raise RedPartyDevelopmentOutcomeCampaignRunError(
                "read-only preflight must not receive the private artifact root"
            )
        return
    if args.private_artifact_root is None:
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "campaign execution needs the private artifact root"
        )
    authorization = args.execute_authorized_plan_sha256
    if not isinstance(authorization, str) or _SHA256.fullmatch(authorization) is None:
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "campaign execution needs one exact plan authorization digest"
        )
    if expected_plan_sha256 is not None and authorization != expected_plan_sha256:
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "campaign execution lacks the exact prospectively frozen authorization digest"
        )


def _validate_lineage_request(
    args: argparse.Namespace,
    plan: PartyDevelopmentOutcomeCampaignPlan,
) -> None:
    predecessor_path = getattr(args, "predecessor_campaign_plan", None)
    predecessor_digest = getattr(
        args, "predecessor_campaign_plan_file_sha256", None
    )
    supplied = predecessor_path is not None or predecessor_digest is not None
    if plan.is_successor:
        if (
            not supplied
            or args.private_artifact_root is None
            or plan.predecessor is None
            or predecessor_digest != plan.predecessor.plan_file_sha256
        ):
            raise RedPartyDevelopmentOutcomeCampaignRunError(
                "successor campaign lacks its exact predecessor lineage inputs"
            )
        return
    if supplied:
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "original campaign must not receive successor lineage inputs"
        )


def _require_protected_inputs_unchanged(
    protected_files: Mapping[Path, str],
    *,
    rom_path: Path,
    rom_before: tuple[tuple[bool, str | None], ...],
) -> None:
    if (
        {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected_files}
        != protected_files
        or rom_adjacent_artifacts(rom_path) != rom_before
    ):
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "campaign execution changed a protected input"
        )


def _reconstruct_questions(
    *,
    catalog: PartyDevelopmentFrozenCatalog,
    plan: PartyDevelopmentOutcomeCampaignPlan,
    reservations: PartyDevelopmentQuestionReservationPlan,
    venue_registry: PartyDevelopmentVenuePriorRegistry,
    catalog_root: Path,
    rom_path: Path,
    rom_bytes: bytes,
) -> tuple[tuple[_QuestionRuntime, ...], dict[Path, str]]:
    route_area = ROUTE_11_TRAINING_VENUE.band
    cave_area = DIGLETTS_CAVE_TRAINING_VENUE.band
    route_evidence = venue_registry.evidence_for(route_area)
    cave_evidence = venue_registry.evidence_for(cave_area)
    if route_evidence is None or cave_evidence is None:
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "campaign lacks both frozen executable venue priors"
        )
    areas = (route_area, cave_area)
    contracts = (
        route_evidence.operational_contract_sha256,
        cave_evidence.operational_contract_sha256,
    )
    evolutions: Mapping[int, tuple[Evolution, ...]] = evolution_graph(rom_bytes)
    species_mapping = internal_to_dex(rom_bytes)
    reservation_by_scenario = {
        item.scenario_id: item for item in reservations.reservations
    }
    assignments_by_scenario: dict[
        str, list[PartyDevelopmentOutcomeTrialAssignment]
    ] = {}
    for assignment in plan.assignments:
        assignments_by_scenario.setdefault(assignment.scenario_id, []).append(
            assignment
        )
    protected_files: dict[Path, str] = {}
    runtimes: list[_QuestionRuntime] = []
    for question in catalog.questions:
        original = reservation_by_scenario.get(question.scenario_id)
        if original is None:
            raise RedPartyDevelopmentOutcomeCampaignRunError(
                "campaign frozen question has no reservation"
            )
        reservation = _execution_reservation(original, question)
        state_path, envelope_path, profile_path = _question_paths(
            catalog_root, question
        )
        for path in (state_path, envelope_path, profile_path):
            protected_files[path] = hashlib.sha256(path.read_bytes()).hexdigest()
        if protected_files[profile_path] != question.profile_file_sha256:
            raise RedPartyDevelopmentOutcomeCampaignRunError(
                "campaign profile file differs from its frozen digest"
            )
        capture = open_goal_manager_context_capture(state_path, envelope_path)
        if (
            capture.capture_id != question.capture_id
            or capture.state_sha256 != question.binding.initial_state_sha256
            or capture.envelope_sha256 != question.capture_envelope_sha256
        ):
            raise RedPartyDevelopmentOutcomeCampaignRunError(
                "campaign capture differs from its frozen state"
            )
        profile = load_red_goal_context_profile(profile_path)
        with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
            emulator.load_state_bytes(capture.state_bytes)
            ports = _build_trial_execution_ports(
                emulator,
                maximum_frames=plan.dose.maximum_frames,
            )
            reader = ports.reader
            runtime = build_red_goal_context_runtime(
                profile=profile,
                capture=capture,
                emulator=ports.observation_emulator,
                reader=reader,
            )
            observation = runtime.adapter.observe()
            if ports.controller.frames_executed != 0:
                raise RedPartyDevelopmentOutcomeCampaignRunError(
                    "campaign read-only port preflight advanced controller frames"
                )
        snapshot = build_red_party_development_snapshot(
            reservation,
            source_root_lineage_id=question.binding.root_lineage_id,
            observation=observation,
            evolutions=evolutions,
            policy=RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY,
            areas=areas,
            venue_prior_registry=venue_registry,
            venue_operational_contract_sha256=contracts,
            source_commit=catalog.source_commit,
            source_bundle_sha256=catalog.source_bundle_sha256,
        )
        venue_trainee: PartyMemberObservation | None
        menu: (
            BoundPartyDevelopmentMenu[PartyMemberObservation]
            | BoundPartyDevelopmentMenu[GrindingArea]
            | None
        )
        if question.binding.kind is TrainingChoiceKind.TRAINEE:
            venue_trainee = None
            menu = snapshot.trainee_menu(route_area)
        else:
            venue_trainee = snapshot.unique_weakest_goal_relevant_venue_trainee()
            menu = snapshot.venue_menu(venue_trainee)
        if menu is None:
            raise RedPartyDevelopmentOutcomeCampaignRunError(
                "campaign question no longer reconstructs a candidate menu"
            )
        binding = snapshot.freeze_binding(menu, scenario_id=question.scenario_id)
        RedPartyDevelopmentQuestionPreflight(
            reservation=reservation,
            source_root_lineage_id=question.binding.root_lineage_id,
            snapshot=snapshot,
            menu=menu,
            binding=binding,
        )
        if binding != question.binding or menu.candidate_set != question.candidate_set:
            raise RedPartyDevelopmentOutcomeCampaignRunError(
                "campaign reconstruction differs from the frozen learner question"
            )
        assignments = tuple(
            sorted(
                assignments_by_scenario.get(question.scenario_id, ()),
                key=lambda item: item.candidate_index,
            )
        )
        trial_bindings = tuple(
            bind_red_party_development_outcome_trial(
                question,
                menu,
                assignment,
                party=observation.party,
                venue_question_trainee=venue_trainee,
                training_venues=_TRAINING_VENUES,
                evolutions=evolutions,
                internal_to_national=species_mapping,
                dose=plan.dose,
            )
            for assignment in assignments
        )
        if len(trial_bindings) != len(question.candidate_set.candidates):
            raise RedPartyDevelopmentOutcomeCampaignRunError(
                "campaign question does not bind every candidate trial"
            )
        runtimes.append(
            _QuestionRuntime(
                question=question,
                reservation=reservation,
                capture=capture,
                profile=profile,
                menu=menu,
                venue_question_trainee=venue_trainee,
                assignments=assignments,
                trial_bindings=trial_bindings,
            )
        )
    if (
        len(runtimes) != 14
        or sum(len(item.assignments) for item in runtimes)
        != RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_COUNT
    ):
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "campaign reconstruction did not cover exact 14/55"
        )
    return tuple(runtimes), protected_files


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
                "moves": [
                    {
                        "move_id": move.move_id,
                        "current_pp": move.current_pp,
                    }
                    for move in member.known_moves
                ],
            }
            for member in party.members
        ]
    }


def _execute_trial(
    *,
    plan: PartyDevelopmentOutcomeCampaignPlan,
    runtime: _QuestionRuntime,
    assignment: PartyDevelopmentOutcomeTrialAssignment,
    binding: RedPartyDevelopmentTrialBinding,
    claim: PartyDevelopmentOutcomeTrialClaim,
    rom_path: Path,
    evolutions: Mapping[int, tuple[Evolution, ...]],
    watch: bool,
) -> tuple[PartyDevelopmentOutcomeTrialResult, dict[str, object]]:
    summaries: list[TeamTrainingExecutionSummary] = []
    dose = plan.dose
    policy = replace(
        RED_PARTY_DEVELOPMENT_OUTCOME_POLICY,
        max_battles=dose.completed_battles,
        max_steps=dose.maximum_encounter_steps,
        # The final cleanup is counted but intentionally outside the live
        # recovery budget in run_red_team_balancing.
        max_healing_trips=dose.maximum_healing_trips - 1,
        max_faints=dose.maximum_faints,
    )
    with PyBoyAdapter(
        rom_path,
        watch=watch,
        speed=2 if watch else None,
    ) as emulator:
        emulator.load_state_bytes(runtime.capture.state_bytes)
        ports = _build_trial_execution_ports(
            emulator,
            maximum_frames=dose.maximum_frames,
        )
        # Observation keeps the emulator's complete read-only capability,
        # including banked cartridge RAM.  Only the executor receives the
        # frame-budget controller proxy.  Passing that proxy to observation
        # hid the all-box port from runtime structural checks and consumed the
        # first campaign trial before input.
        reader = ports.reader
        goal_runtime = build_red_goal_context_runtime(
            profile=runtime.profile,
            capture=runtime.capture,
            emulator=ports.observation_emulator,
            reader=reader,
        )
        before_observation = goal_runtime.adapter.observe()
        before_party = ports.party_reader.read()
        if (
            before_observation.party.species_ids() != before_party.species_ids()
            or tuple(member.level for member in before_observation.party.members)
            != before_party.levels
        ):
            raise RedPartyDevelopmentOutcomeCampaignRunError(
                "campaign clone party differs across coherent readers"
            )
        before_completion = red_party_completion_snapshot(
            before_observation,
            evolutions=evolutions,
            policy=RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY,
        )
        actions = BoundedActionExecutor(
            FrameSafeExecutor(
                ports.controller,
                DEFAULT_NEW_GAME_TIMING.controller_timing(),
            ),
            maximum_actions=dose.maximum_controller_actions,
        )
        run_red_team_balancing(
            actions,
            reader,
            ports.observation_emulator,
            policy=policy,
            intent=MANSION_BALANCED_TEAM_TRAINING_INTENT,
            flee_timing=MANSION_TRAINING_FLEE_TIMING,
            hideout_timing=DEFAULT_HIDEOUT_TIMING,
            flee_func=_flee,  # type: ignore[arg-type]  # legacy emulator protocols
            volatile_enemy_species=MANSION_VOLATILE_ENEMY_SPECIES,
            escort_enemy_species=MANSION_ESCORT_ENEMY_SPECIES,
            max_consecutive_flees=MANSION_MAX_CONSECUTIVE_FLEES,
            cancel_interval=MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
            execution_summary_sink=summaries.append,
            venues=_TRAINING_VENUES,
            report_label="completion-aware party outcome dose",
            checkpoint_count=1,
            fixed_dose=binding.fixed_dose,
        )
        if len(summaries) != 1:
            raise RedPartyDevelopmentOutcomeCampaignRunError(
                "campaign trial did not retain one execution summary"
            )
        summary = summaries[0]
        after_observation = goal_runtime.adapter.observe()
        after_party = ports.party_reader.read()
        after_targets = tuple(
            member
            for member in after_party.members
            if member.species_id in binding.trainee_species_lineage
        )
        if len(after_targets) != 1:
            raise RedPartyDevelopmentOutcomeCampaignRunError(
                "campaign trial lost its unique target lineage"
            )
        after_target = after_targets[0]
        after_completion = red_party_completion_snapshot(
            after_observation,
            evolutions=evolutions,
            policy=RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY,
        )
        trial = PartyDevelopmentOutcomeTrialV2(
            candidate=runtime.question.candidate_set.candidates[
                assignment.candidate_index
            ],
            target_slot=binding.target_slot,
            after_target_slot=after_target.slot,
            before_party=before_party,
            after_party=after_party,
            progress_before=TeamTrainingProgress(),
            progress_after=summary.progress,
            completion_before=before_completion,
            completion_after=after_completion,
            frames_executed=ports.controller.frames_executed,
            rotations_executed=summary.rotations_executed,
            evolution_completed=(after_target.species_id != binding.target_species_id),
        )
        partial_example = adapt_party_development_outcomes_v2(
            runtime.question.candidate_set,
            (trial,),
            scenario_id=runtime.question.scenario_id,
            root_lineage_id=runtime.question.binding.root_lineage_id,
            initial_state_sha256=runtime.question.binding.initial_state_sha256,
            partition=runtime.question.binding.partition,
            prospective_binding=runtime.question.binding,
        )
        outcome = partial_example.outcomes[assignment.candidate_index]
        if (
            not isinstance(outcome, CandidateOutcome)
            or outcome.status is not OutcomeEvidenceStatus.MEASURED
            or outcome.actions_executed is None
        ):
            raise RedPartyDevelopmentOutcomeCampaignRunError(
                "campaign trial did not produce one measured candidate outcome"
            )
        evidence = {
            "schema": PARTY_DEVELOPMENT_OUTCOME_PRIVATE_EVIDENCE_SCHEMA,
            "campaign_plan_sha256": plan.plan_sha256,
            "trial_id": assignment.trial_id,
            "assignment_sha256": assignment.assignment_sha256,
            "claim_sha256": claim.claim_sha256,
            "candidate_index": assignment.candidate_index,
            "status": OutcomeEvidenceStatus.MEASURED.value,
            "before_party": _party_evidence(before_party),
            "after_party": _party_evidence(after_party),
            "before_completion": before_completion.public_dict(),
            "after_completion": after_completion.public_dict(),
            "execution": summary.public_dict(),
            "semantic_actions": outcome.actions_executed,
            "controller_actions": actions.actions_executed,
            "frames_executed": ports.controller.frames_executed,
            "criterion_values": list(outcome.criterion_values),
            "evolution_completed": trial.evolution_completed,
            "outcome_evidence_sha256": outcome.evidence_sha256,
            "teacher_queries": 0,
            "model_predictions": 0,
            "model_updates": 0,
            "private_path_fields": 0,
        }
        result = PartyDevelopmentOutcomeTrialResult.build(
            plan,
            assignment,
            claim,
            status=OutcomeEvidenceStatus.MEASURED,
            evidence_sha256=canonical_sha256(evidence),
            criterion_values=outcome.criterion_values,
            semantic_actions=outcome.actions_executed,
            controller_actions=actions.actions_executed,
            frames_executed=ports.controller.frames_executed,
            battles_completed=summary.progress.battles_completed,
            encounter_steps=summary.progress.steps_taken,
            healing_trips=summary.progress.healing_trips,
            rotations_executed=summary.rotations_executed,
            faints=summary.progress.faints,
            evolution_completed=trial.evolution_completed,
        )
    return result, evidence


def _claim_id(
    plan: PartyDevelopmentOutcomeCampaignPlan,
    assignment: PartyDevelopmentOutcomeTrialAssignment,
) -> str:
    return party_development_outcome_record_ids(plan, assignment)[0]


def _terminal_id(
    plan: PartyDevelopmentOutcomeCampaignPlan,
    assignment: PartyDevelopmentOutcomeTrialAssignment,
) -> str:
    return party_development_outcome_record_ids(plan, assignment)[1]


def _load_claim(
    store: PrivateArtifactRoot,
    plan: PartyDevelopmentOutcomeCampaignPlan,
    assignment: PartyDevelopmentOutcomeTrialAssignment,
) -> PartyDevelopmentOutcomeTrialClaim | None:
    record = store.find_sealed_record(
        _claim_id(plan, assignment), expected_kind=_CLAIM_KIND
    )
    if record is None:
        return None
    claim = PartyDevelopmentOutcomeTrialClaim.from_private_dict(record.read())
    expected = PartyDevelopmentOutcomeTrialClaim.build(plan, assignment)
    if claim != expected:
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "campaign claim differs from its frozen assignment"
        )
    return claim


def _load_terminal(
    store: PrivateArtifactRoot,
    plan: PartyDevelopmentOutcomeCampaignPlan,
    assignment: PartyDevelopmentOutcomeTrialAssignment,
) -> PartyDevelopmentOutcomeTrialResult | None:
    record = store.find_sealed_record(
        _terminal_id(plan, assignment), expected_kind=_TERMINAL_KIND
    )
    if record is None:
        return None
    result = parse_party_development_trial_terminal(record.read())
    result.require_within_plan(plan, assignment)
    return result


def _publish_censored_terminal(
    store: PrivateArtifactRoot,
    plan: PartyDevelopmentOutcomeCampaignPlan,
    assignment: PartyDevelopmentOutcomeTrialAssignment,
    claim: PartyDevelopmentOutcomeTrialClaim,
) -> PartyDevelopmentOutcomeTrialResult:
    evidence = {
        "schema": PARTY_DEVELOPMENT_OUTCOME_PRIVATE_EVIDENCE_SCHEMA,
        "campaign_plan_sha256": plan.plan_sha256,
        "trial_id": assignment.trial_id,
        "assignment_sha256": assignment.assignment_sha256,
        "claim_sha256": claim.claim_sha256,
        "candidate_index": assignment.candidate_index,
        "status": "censored",
        "failure_code": "process_interrupted",
        "measurements_recovered": False,
        "retry_after_controller_input": False,
        "teacher_queries": 0,
        "model_predictions": 0,
        "model_updates": 0,
        "private_path_fields": 0,
    }
    result = PartyDevelopmentOutcomeTrialResult.build(
        plan,
        assignment,
        claim,
        status=OutcomeEvidenceStatus.CENSORED,
        evidence_sha256=canonical_sha256(evidence),
        failure_code="process_interrupted",
    )
    terminal = build_party_development_trial_terminal(result, evidence=evidence)
    store.publish_sealed_record(
        _terminal_id(plan, assignment),
        kind=_TERMINAL_KIND,
        record=terminal,
    )
    return result


def _publish_invalid_terminal(
    store: PrivateArtifactRoot,
    plan: PartyDevelopmentOutcomeCampaignPlan,
    assignment: PartyDevelopmentOutcomeTrialAssignment,
    claim: PartyDevelopmentOutcomeTrialClaim,
    *,
    failure_code: str,
) -> PartyDevelopmentOutcomeTrialResult:
    evidence = {
        "schema": PARTY_DEVELOPMENT_OUTCOME_PRIVATE_EVIDENCE_SCHEMA,
        "campaign_plan_sha256": plan.plan_sha256,
        "trial_id": assignment.trial_id,
        "assignment_sha256": assignment.assignment_sha256,
        "claim_sha256": claim.claim_sha256,
        "candidate_index": assignment.candidate_index,
        "status": "invalid",
        "failure_code": failure_code,
        "retry_after_controller_input": False,
        "teacher_queries": 0,
        "model_predictions": 0,
        "model_updates": 0,
        "private_path_fields": 0,
    }
    result = PartyDevelopmentOutcomeTrialResult.build(
        plan,
        assignment,
        claim,
        status=OutcomeEvidenceStatus.INVALID,
        evidence_sha256=canonical_sha256(evidence),
        failure_code=failure_code,
    )
    terminal = build_party_development_trial_terminal(result, evidence=evidence)
    store.publish_sealed_record(
        _terminal_id(plan, assignment),
        kind=_TERMINAL_KIND,
        record=terminal,
    )
    return result


def _run(args: argparse.Namespace) -> dict[str, object]:
    _validate_execution_request(args)
    runner_path = Path(__file__).resolve()
    runner_sha256 = hashlib.sha256(runner_path.read_bytes()).hexdigest()
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:
        raise AssertionError("published campaign runner lost its commit")
    source_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    plan_document, _plan_payload = _load_private_json(
        args.campaign_plan,
        expected_sha256=args.campaign_plan_file_sha256,
        subject="campaign plan",
    )
    plan = PartyDevelopmentOutcomeCampaignPlan.from_private_dict(plan_document)
    _validate_lineage_request(args, plan)
    if (
        plan.source_commit != source.git_commit
        or plan.source_bundle_sha256 != source_bundle
        or plan.runner_source_sha256 != runner_sha256
    ):
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "campaign executable differs from its frozen plan"
        )
    _require_exact_green_ci_run(
        plan.exact_ci_run,
        plan.exact_ci_attempt,
        source_commit=source.git_commit,
    )
    _validate_execution_request(args, expected_plan_sha256=plan.plan_sha256)

    store: PrivateArtifactRoot | None = None
    predecessor_plan: PartyDevelopmentOutcomeCampaignPlan | None = None
    inherited_results: tuple[PartyDevelopmentOutcomeTrialResult, ...] = ()
    predecessor_plan_path: Path | None = None
    if plan.is_successor:
        assert plan.predecessor is not None
        assert args.predecessor_campaign_plan is not None
        assert args.predecessor_campaign_plan_file_sha256 is not None
        assert args.private_artifact_root is not None
        predecessor_plan_path = _require_external(
            args.predecessor_campaign_plan,
            subject="predecessor campaign plan",
        )
        predecessor_document, _ = _load_private_json(
            predecessor_plan_path,
            expected_sha256=args.predecessor_campaign_plan_file_sha256,
            subject="predecessor campaign plan",
        )
        predecessor_plan = PartyDevelopmentOutcomeCampaignPlan.from_private_dict(
            predecessor_document
        )
        private_root_path = _require_external(
            args.private_artifact_root, subject="private artifact root"
        )
        store = open_private_root(private_root_path, repository_root=PROJECT_ROOT)
        inherited_results = validate_successor_campaign_lineage(
            plan,
            predecessor_plan,
            predecessor_plan_file_sha256=(
                args.predecessor_campaign_plan_file_sha256
            ),
            store=store,
        )

    catalog_document, _catalog_payload = _load_private_json(
        args.frozen_catalog,
        expected_sha256=plan.frozen_catalog_file_sha256,
        subject="frozen catalog",
    )
    catalog = PartyDevelopmentFrozenCatalog.from_private_dict(catalog_document)
    reservation_document, _ = _load_private_json(
        args.reservation_plan,
        expected_sha256=catalog.reservation_plan_file_sha256,
        subject="reservation plan",
    )
    reservations = PartyDevelopmentQuestionReservationPlan.from_private_dict(
        reservation_document
    )
    venue_document, _ = _load_private_json(
        args.venue_prior_registry,
        expected_sha256=catalog.venue_prior_registry_file_sha256,
        subject="venue-prior registry",
    )
    venue_registry = PartyDevelopmentVenuePriorRegistry.from_private_dict(
        venue_document
    )
    audit_document, _ = _load_private_json(
        args.input_audit_receipt,
        expected_sha256=plan.input_audit_receipt_file_sha256,
        subject="input-audit receipt",
        external=False,
    )
    _validate_input_audit(audit_document, plan=plan, catalog=catalog)
    if (
        reservations.plan_sha256 != catalog.reservation_plan_sha256
        or venue_registry.registry_sha256 != catalog.venue_prior_registry_sha256
    ):
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "campaign supporting contracts differ from the frozen catalog"
        )

    catalog_root = _require_external(args.catalog_root, subject="catalog root")
    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    if fingerprint.sha256 != plan.rom_sha256:
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "campaign ROM differs from its frozen plan"
        )
    rom_before = rom_adjacent_artifacts(rom_path)
    rom_bytes = rom_path.read_bytes()
    runtimes, question_files = _reconstruct_questions(
        catalog=catalog,
        plan=plan,
        reservations=reservations,
        venue_registry=venue_registry,
        catalog_root=catalog_root,
        rom_path=rom_path,
        rom_bytes=rom_bytes,
    )
    protected_files = {
        _require_external(args.campaign_plan, subject="campaign plan"):
        args.campaign_plan_file_sha256,
        _require_external(args.frozen_catalog, subject="frozen catalog"):
        plan.frozen_catalog_file_sha256,
        _require_external(args.reservation_plan, subject="reservation plan"):
        catalog.reservation_plan_file_sha256,
        _require_external(args.venue_prior_registry, subject="venue-prior registry"):
        catalog.venue_prior_registry_file_sha256,
        args.input_audit_receipt.resolve(): plan.input_audit_receipt_file_sha256,
        rom_path: plan.rom_sha256,
    }
    if predecessor_plan_path is not None:
        assert plan.predecessor is not None
        protected_files[predecessor_plan_path] = plan.predecessor.plan_file_sha256
    protected_files.update(question_files)
    if {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in protected_files
    } != protected_files:
        raise RedPartyDevelopmentOutcomeCampaignRunError(
            "campaign protected input differs before collection"
        )

    preflight: dict[str, object] = {
        "schema": "pokemon.red.party-development-outcome-campaign-preflight.v1",
        "status": (
            "ready_for_exact_controller_authorization"
            if not args.execute
            else "authorized_execution_started"
        ),
        "source_commit": source.git_commit,
        "source_bundle_sha256": source_bundle,
        "runner_source_sha256": runner_sha256,
        "exact_ci_run": plan.exact_ci_run,
        "exact_ci_attempt": plan.exact_ci_attempt,
        "campaign_plan_file_sha256": args.campaign_plan_file_sha256,
        "campaign_plan_sha256": plan.plan_sha256,
        "frozen_catalog_sha256": catalog.catalog_sha256,
        "prospective_catalog_sha256": catalog.prospective_catalog_sha256,
        "question_count": len(runtimes),
        "candidate_trial_count": sum(len(item.assignments) for item in runtimes),
        "inherited_terminal_count": len(inherited_results),
        "remaining_candidate_trial_count": len(plan.active_assignments),
        "remaining_trial_partition_counts": dict(
            sorted(Counter(item.partition.value for item in plan.active_assignments).items())
        ),
        "inherited_terminal_status_counts": dict(
            sorted(Counter(item.status.value for item in plan.inherited_terminals).items())
        ),
        "trial_bindings_reconstructed": sum(
            len(item.trial_bindings) for item in runtimes
        ),
        "execution_observation_ports_verified": len(runtimes),
        "all_candidates_available": True,
        "input_files_unchanged": True,
        "rom_adjacent_artifacts_unchanged": True,
        "execution_authorized": args.execute,
        "controller_actions": 0,
        "teacher_queries": 0,
        "model_predictions": 0,
        "model_updates": 0,
        "model_fits": 0,
        "sealed_red_cases_opened": 0,
        "crystal_cases_opened": 0,
        "full_game_replays": 0,
        "authority_promoted": False,
        "candidate_feature_values_public": False,
        "private_binding_values_public": False,
        "private_path_fields": 0,
    }
    if not args.execute:
        _require_protected_inputs_unchanged(
            protected_files,
            rom_path=rom_path,
            rom_before=rom_before,
        )
        if plan.is_successor:
            assert plan.predecessor is not None
            assert predecessor_plan is not None
            assert store is not None
            validate_successor_campaign_lineage(
                plan,
                predecessor_plan,
                predecessor_plan_file_sha256=(
                    plan.predecessor.plan_file_sha256
                ),
                store=store,
            )
        return preflight

    assert args.private_artifact_root is not None
    if store is None:
        private_root_path = _require_external(
            args.private_artifact_root, subject="private artifact root"
        )
        store = open_private_root(private_root_path, repository_root=PROJECT_ROOT)
    collection_id = f"{_COLLECTION_ID_PREFIX}-{plan.plan_sha256[:16]}"
    evolutions = evolution_graph(rom_bytes)
    results: list[PartyDevelopmentOutcomeTrialResult] = list(inherited_results)
    claims = len(inherited_results)
    measured = sum(
        item.status is OutcomeEvidenceStatus.MEASURED for item in inherited_results
    )
    invalid = sum(
        item.status is OutcomeEvidenceStatus.INVALID for item in inherited_results
    )
    censored = sum(
        item.status is OutcomeEvidenceStatus.CENSORED for item in inherited_results
    )
    runtime_by_scenario = {item.question.scenario_id: item for item in runtimes}
    binding_by_assignment = {
        binding.assignment.assignment_sha256: binding
        for runtime in runtimes
        for binding in runtime.trial_bindings
    }
    try:
        with store.collection_session(collection_id):
            for assignment in plan.active_assignments:
                claim = _load_claim(store, plan, assignment)
                terminal = _load_terminal(store, plan, assignment)
                if terminal is not None and claim is None:
                    raise RedPartyDevelopmentOutcomeCampaignRunError(
                        "campaign terminal exists without its durable claim"
                    )
                if claim is not None:
                    claims += 1
                    if terminal is None:
                        terminal = _publish_censored_terminal(
                            store, plan, assignment, claim
                        )
                    results.append(terminal)
                    measured += terminal.status is OutcomeEvidenceStatus.MEASURED
                    invalid += terminal.status is OutcomeEvidenceStatus.INVALID
                    censored += terminal.status is OutcomeEvidenceStatus.CENSORED
                    continue

                claim = PartyDevelopmentOutcomeTrialClaim.build(plan, assignment)
                store.publish_sealed_record(
                    _claim_id(plan, assignment),
                    kind=_CLAIM_KIND,
                    record=claim.private_dict(),
                )
                claims += 1
                runtime = runtime_by_scenario[assignment.scenario_id]
                binding = binding_by_assignment[assignment.assignment_sha256]
                try:
                    result, evidence = _execute_trial(
                        plan=plan,
                        runtime=runtime,
                        assignment=assignment,
                        binding=binding,
                        claim=claim,
                        rom_path=rom_path,
                        evolutions=evolutions,
                        watch=args.watch,
                    )
                    terminal_document = build_party_development_trial_terminal(
                        result, evidence=evidence
                    )
                    store.publish_sealed_record(
                        _terminal_id(plan, assignment),
                        kind=_TERMINAL_KIND,
                        record=terminal_document,
                    )
                except Exception as error:
                    _publish_invalid_terminal(
                        store,
                        plan,
                        assignment,
                        claim,
                        failure_code="execution_error",
                    )
                    raise RedPartyDevelopmentOutcomeCampaignRunError(
                        "campaign stopped after retaining one consumed invalid trial; "
                        f"failure type {type(error).__name__}"
                    ) from None
                results.append(result)
                measured += 1
    finally:
        _require_protected_inputs_unchanged(
            protected_files,
            rom_path=rom_path,
            rom_before=rom_before,
        )
        if plan.is_successor:
            assert plan.predecessor is not None
            assert predecessor_plan is not None
            validate_successor_campaign_lineage(
                plan,
                predecessor_plan,
                predecessor_plan_file_sha256=(
                    plan.predecessor.plan_file_sha256
                ),
                store=store,
            )

    examples = assemble_party_development_outcome_examples(
        catalog,
        plan,
        tuple(results),
    )
    statuses = Counter(result.status.value for result in results)
    return {
        **preflight,
        "schema": "pokemon.red.party-development-outcome-campaign-receipt.v1",
        "status": (
            "complete_measured"
            if measured == RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_COUNT
            else (
                "complete_with_unusable_trials"
                if claims == RED_PARTY_DEVELOPMENT_OUTCOME_TRIAL_COUNT
                else "incomplete"
            )
        ),
        "trial_claims": claims,
        "measured_trials": measured,
        "invalid_trials": invalid,
        "censored_trials": censored,
        "terminal_status_counts": dict(sorted(statuses.items())),
        "complete_examples": sum(item.fully_measured for item in examples),
        "learner_update_eligible_examples": sum(
            item.learner_update_eligible for item in examples
        ),
        "controller_actions": sum(
            result.controller_actions or 0 for result in results
        ),
        "execution_authorized": True,
        "model_fits": 0,
        "authority_promoted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        result = _run(parser.parse_args(argv))
    except (OSError, RuntimeError, TypeError, ValueError):
        parser.error(
            "Red party-development outcome campaign failed closed; private paths were withheld."
        )
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
