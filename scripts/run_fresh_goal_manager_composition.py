#!/usr/bin/env python3
"""Qualify or execute one frozen fresh Red goal-manager composition episode."""

# ruff: noqa: E402 -- pin the reviewed workspace source before project imports

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar, cast

_BOOTSTRAP_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_BOOTSTRAP_SRC = _BOOTSTRAP_PROJECT_ROOT / "src"
while str(_BOOTSTRAP_SRC) in sys.path:
    sys.path.remove(str(_BOOTSTRAP_SRC))
sys.path.insert(0, str(_BOOTSTRAP_SRC))

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    CountingExecutor,
    FrameSafeExecutor,
    ReadOnlyController,
    WindowedFrameBudgetController,
)
from pokemon_red_completion.goal_manager_collection_runtime import (
    goal_binding_manifest_sha256,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    ActionFreeAdmissionExecutor,
    CompositionIndependentBudgetMeter,
    HardCompositionActionLimiter,
    composition_skill_manifest,
    living_collection_checkpoint,
    open_fixed_account_claim_registry,
    root_claim_is_available,
    root_consumption_sha256,
    write_root_claim,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    FRESH_COMPOSITION_ACTIONS_PER_DECISION,
    FRESH_COMPOSITION_CONFIDENCE_FLOOR,
    FRESH_COMPOSITION_FRAMES_PER_DECISION,
    FRESH_COMPOSITION_MAX_ACTIONS,
    FRESH_COMPOSITION_MAX_FRAMES,
    FRESH_COMPOSITION_REQUIRED_KINDS,
    GoalManagerCompositionObservation,
    run_goal_manager_composition_episode,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCapture,
    open_goal_manager_context_capture,
)
from pokemon_red_completion.goal_manager_model import LearnedGoalManagerPolicy
from pokemon_red_completion.goal_manager_preflight import parse_goal_manager_preflight
from pokemon_red_completion.goal_manager_promotion import (
    AuthenticatedGoalManagerCandidate,
    authenticate_goal_manager_candidate,
    load_committed_goal_manager_promotion_plan,
)
from pokemon_red_completion.goal_manager_protocol import (
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.goal_manager_trajectory import (
    GoalManagerTrajectoryObserver,
)
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.private_artifacts import (
    EpisodeWriter,
    PrivateArtifactRoot,
    open_private_root,
)
from pokemon_red_completion.provenance import (
    SourceIdentity,
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_goal_context import (
    RedGoalContextRuntime,
    build_red_goal_context_runtime,
)
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfile,
    load_red_goal_context_profile,
)
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.rom import RomFingerprint, resolve_rom_path, verify_rom
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts
from pokemon_red_completion.runtime_identity import RuntimeIdentity, build_runtime_identity
from pokemon_red_completion.trajectory import JSONValue, RecordingExecutor, SparseEvent
from pokemon_red_completion.trajectory_io import EpisodeTrajectorySink

PROJECT_ROOT = _BOOTSTRAP_PROJECT_ROOT
DESIGN_PATH = (
    PROJECT_ROOT / "docs/evidence/fresh-goal-manager-composition-design-v2-2026-08-17.json"
)
QUALIFICATION_MODULE_PATH = (
    PROJECT_ROOT / "src/pokemon_red_completion/goal_manager_composition_qualification.py"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MAX_ATTESTATION_BYTES = 64 * 1024
_PREFLIGHT_FAILURE_STAGES = frozenset(
    {
        "action_free_admission",
        "execution_authorization",
        "readiness_authentication",
        "success_receipt_construction",
    }
)
_ResultT = TypeVar("_ResultT")


class FreshCompositionRunError(RuntimeError):
    """Raised without disclosing a private path or root identity."""


class FreshCompositionPreclaimFailure(RuntimeError):
    """A caught preclaim failure reduced to one public, allowlisted stage."""

    def __init__(self, stage: str) -> None:
        if stage not in _PREFLIGHT_FAILURE_STAGES:
            raise ValueError("preclaim failure stage is not allowlisted")
        super().__init__(stage)
        self.stage = stage


@dataclass(frozen=True, slots=True)
class _Readiness:
    source: SourceIdentity
    capture: GoalManagerContextCapture
    profile: RedGoalContextProfile
    candidate: AuthenticatedGoalManagerCandidate
    output_root: PrivateArtifactRoot
    claim_registry: Path
    rom_path: Path
    rom: RomFingerprint
    root_consumption_sha256: str
    episode_id: str
    design_sha256: str
    runner_sha256: str
    qualification_module_sha256: str
    skill_manifest: dict[str, object]
    state_path: Path
    envelope_path: Path
    profile_path: Path
    nonsealed_attestation_path: Path
    root_provenance_path: Path
    nonsealed_attestation_sha256: str
    root_provenance_sha256: str
    root_lineage_id: str
    historical_binding_manifest_sha256: str
    runtime: RuntimeIdentity


@dataclass(frozen=True, slots=True)
class _Admission:
    execution_identity_sha256: str
    binding_manifest_sha256: str
    semantic_state_sha256: str
    completion_contract_sha256: str
    specimen_ledger_sha256: str
    required_specimens_sha256: str
    initial_available_goal_count: int
    initial_available_goal_kinds: tuple[str, ...]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-executable-source", required=True)
    parser.add_argument("--expected-runner-sha256", required=True)
    parser.add_argument("--expected-qualification-module-sha256", required=True)
    parser.add_argument("--expected-design-sha256", required=True)
    parser.add_argument("--expected-skill-manifest-sha256", required=True)
    parser.add_argument("--expected-runtime-sha256", required=True)
    parser.add_argument("--expected-state-sha256", required=True)
    parser.add_argument("--expected-envelope-sha256", required=True)
    parser.add_argument("--expected-profile-sha256", required=True)
    parser.add_argument("--expected-nonsealed-attestation-sha256", required=True)
    parser.add_argument("--expected-root-provenance-sha256", required=True)
    parser.add_argument("--expected-execution-identity-sha256")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--envelope", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--nonsealed-attestation", type=Path, required=True)
    parser.add_argument("--root-provenance", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--fit-summary", type=Path, required=True)
    parser.add_argument("--private-artifact-root", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, default=None)
    return parser


def _prepare_readiness(args: argparse.Namespace) -> _Readiness:
    if args.watch or args.speed is not None:
        raise FreshCompositionRunError(
            "composition execution presentation is frozen to headless mode"
        )
    _require_imported_code_from_project()
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if (
        _GIT_COMMIT.fullmatch(args.expected_executable_source) is None
        or source.git_commit != args.expected_executable_source
    ):
        raise FreshCompositionRunError(
            "composition executable source differs from its external attestation"
        )
    runner_sha256 = _file_sha256(Path(__file__).resolve(), subject="runner")
    qualification_sha256 = _file_sha256(
        QUALIFICATION_MODULE_PATH,
        subject="qualification module",
    )
    design_sha256 = _file_sha256(DESIGN_PATH, subject="V2 design")
    for actual, expected, subject in (
        (runner_sha256, args.expected_runner_sha256, "runner"),
        (
            qualification_sha256,
            args.expected_qualification_module_sha256,
            "qualification module",
        ),
        (design_sha256, args.expected_design_sha256, "V2 design"),
    ):
        if actual != _require_sha256(expected, subject=subject):
            raise FreshCompositionRunError(
                "composition executable bytes differ from external attestation"
            )

    skill_manifest = composition_skill_manifest(PROJECT_ROOT)
    if skill_manifest.get("manifest_sha256") != _require_sha256(
        args.expected_skill_manifest_sha256,
        subject="skill manifest",
    ):
        raise FreshCompositionRunError("composition skill sources differ from external attestation")
    runtime_identity = build_runtime_identity()
    if runtime_identity.sha256 != _require_sha256(
        args.expected_runtime_sha256,
        subject="runtime identity",
    ):
        raise FreshCompositionRunError("composition runtime differs from external attestation")

    expected_state_sha256 = _require_sha256(
        args.expected_state_sha256,
        subject="state",
    )
    expected_envelope_sha256 = _require_sha256(
        args.expected_envelope_sha256,
        subject="envelope",
    )
    expected_profile_sha256 = _require_sha256(
        args.expected_profile_sha256,
        subject="profile",
    )
    state_path = _external_regular(args.state, subject="state")
    envelope_path = _external_regular(args.envelope, subject="envelope")
    profile_path = _external_regular(args.profile, subject="profile")
    if (
        _file_sha256(state_path, subject="state") != expected_state_sha256
        or _file_sha256(envelope_path, subject="envelope") != expected_envelope_sha256
        or _file_sha256(profile_path, subject="profile") != expected_profile_sha256
    ):
        raise FreshCompositionRunError("composition root inputs differ from attestation")

    capture = open_goal_manager_context_capture(state_path, envelope_path)
    profile = load_red_goal_context_profile(profile_path)
    if (
        capture.state_sha256 != expected_state_sha256
        or capture.envelope_sha256 != expected_envelope_sha256
        or profile.profile_sha256 != expected_profile_sha256
        or _file_sha256(state_path, subject="state") != expected_state_sha256
        or _file_sha256(envelope_path, subject="envelope") != expected_envelope_sha256
        or _file_sha256(profile_path, subject="profile") != expected_profile_sha256
    ):
        raise FreshCompositionRunError(
            "composition parsed root differs from its external attestation"
        )
    attestation_path = _external_regular(
        args.nonsealed_attestation,
        subject="nonsealed attestation",
    )
    attestation_sha256 = _file_sha256(
        attestation_path,
        subject="nonsealed attestation",
    )
    if attestation_sha256 != _require_sha256(
        args.expected_nonsealed_attestation_sha256,
        subject="nonsealed attestation",
    ):
        raise FreshCompositionRunError("nonsealed attestation digest differs")
    provenance_path = _external_regular(
        args.root_provenance,
        subject="root provenance",
    )
    provenance_sha256 = _file_sha256(
        provenance_path,
        subject="root provenance",
    )
    if provenance_sha256 != _require_sha256(
        args.expected_root_provenance_sha256,
        subject="root provenance",
    ):
        raise FreshCompositionRunError("root provenance digest differs")
    root_lineage_id, historical_binding_manifest_sha256 = _authenticate_root_provenance(
        provenance_path,
        capture=capture,
        expected_sha256=provenance_sha256,
    )
    _require_nonsealed_attestation(
        attestation_path,
        capture=capture,
        profile_sha256=expected_profile_sha256,
        expected_attestation_sha256=attestation_sha256,
        root_provenance_sha256=provenance_sha256,
        root_lineage_id=root_lineage_id,
    )

    promotion_plan, _plan_commit = load_committed_goal_manager_promotion_plan(PROJECT_ROOT)
    candidate = authenticate_goal_manager_candidate(
        repository_root=PROJECT_ROOT,
        plan=promotion_plan,
        context_catalog_path=_external_regular(
            args.context_catalog,
            subject="context catalog",
        ),
        model_path=_external_regular(args.model, subject="model"),
        fit_summary_path=_external_regular(args.fit_summary, subject="fit summary"),
    )
    if len(candidate.catalog.entries) != 81:
        raise FreshCompositionRunError("prior context exclusion catalog differs")
    if any(
        entry.state_sha256 == capture.state_sha256
        or entry.envelope_sha256 == capture.envelope_sha256
        or entry.capture_id == capture.capture_id
        for entry in candidate.catalog.entries
    ):
        raise FreshCompositionRunError("composition root overlaps a prior context")
    if root_lineage_id in {entry.root_lineage_id for entry in candidate.catalog.entries}:
        raise FreshCompositionRunError("composition root overlaps a prior lineage")

    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    output_root = open_private_root(
        args.private_artifact_root,
        repository_root=PROJECT_ROOT,
    )
    root_identity = root_consumption_sha256(
        state_sha256=capture.state_sha256,
        envelope_sha256=capture.envelope_sha256,
    )
    episode_id = f"red-fresh-composition-v2-{root_identity[:32]}"
    if output_root.inspect_episode_state(episode_id).status != "absent":
        raise FreshCompositionRunError("composition root is already consumed locally")
    claim_registry = open_fixed_account_claim_registry()
    if not root_claim_is_available(claim_registry, root_identity):
        raise FreshCompositionRunError("composition root is already consumed")
    return _Readiness(
        source=source,
        capture=capture,
        profile=profile,
        candidate=candidate,
        output_root=output_root,
        claim_registry=claim_registry,
        rom_path=rom_path,
        rom=rom,
        root_consumption_sha256=root_identity,
        episode_id=episode_id,
        design_sha256=design_sha256,
        runner_sha256=runner_sha256,
        qualification_module_sha256=qualification_sha256,
        skill_manifest=skill_manifest,
        state_path=state_path,
        envelope_path=envelope_path,
        profile_path=profile_path,
        nonsealed_attestation_path=attestation_path,
        root_provenance_path=provenance_path,
        nonsealed_attestation_sha256=attestation_sha256,
        root_provenance_sha256=provenance_sha256,
        root_lineage_id=root_lineage_id,
        historical_binding_manifest_sha256=historical_binding_manifest_sha256,
        runtime=runtime_identity,
    )


def _admit_root(readiness: _Readiness) -> _Admission:
    adjacent_before = rom_adjacent_artifacts(readiness.rom_path)
    with PyBoyAdapter(readiness.rom_path, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(readiness.capture.state_bytes)
        loaded_frame_count = emulator.frame_count
        read_only_emulator = ReadOnlyController(emulator)
        reader = PokemonRedStateReader(read_only_emulator)
        runtime = build_red_goal_context_runtime(
            profile=readiness.profile,
            capture=readiness.capture,
            emulator=read_only_emulator,
            reader=reader,
        )
        action_blocker = ActionFreeAdmissionExecutor()
        actions = CountingExecutor(action_blocker)
        live = runtime.adapter.observe()
        binding_set = runtime.enumerator(actions).enumerate(live)
        if (
            action_blocker.attempted_actions
            or actions.actions_executed
            or emulator.frame_count != loaded_frame_count
        ):
            raise FreshCompositionRunError(
                "composition admission attempted emulator or controller work"
            )
        available = tuple(binding.kind for binding in binding_set.bindings)
        if not FRESH_COMPOSITION_REQUIRED_KINDS.issubset(set(available)):
            raise FreshCompositionRunError("composition root lacks the V2 field-composition menu")
        checkpoint = living_collection_checkpoint(live)
        semantic_state_sha256 = canonical_sha256(
            {
                "schema": "pokemon.red.fresh-composition-semantic-state.v1",
                "goal_observation": live.public_dict(),
                "collection": checkpoint.public_dict(),
                "available_goal_kinds": [kind.value for kind in available],
            }
        )
        binding_manifest_sha256 = goal_binding_manifest_sha256(binding_set)
        if binding_manifest_sha256 != readiness.historical_binding_manifest_sha256:
            raise FreshCompositionRunError(
                "composition bindings differ from the authenticated historical root"
            )
    _require_unchanged_inputs(readiness, adjacent_before=adjacent_before)
    execution_identity = _execution_identity_sha256(
        readiness,
        binding_manifest_sha256=binding_manifest_sha256,
        semantic_state_sha256=semantic_state_sha256,
        completion_contract_sha256=checkpoint.completion_contract_sha256,
        specimen_ledger_sha256=checkpoint.specimen_ledger_sha256,
        required_specimens_sha256=checkpoint.required_specimens_sha256,
    )
    return _Admission(
        execution_identity_sha256=execution_identity,
        binding_manifest_sha256=binding_manifest_sha256,
        semantic_state_sha256=semantic_state_sha256,
        completion_contract_sha256=checkpoint.completion_contract_sha256,
        specimen_ledger_sha256=checkpoint.specimen_ledger_sha256,
        required_specimens_sha256=checkpoint.required_specimens_sha256,
        initial_available_goal_count=len(available),
        initial_available_goal_kinds=tuple(kind.value for kind in available),
    )


def _execution_identity_sha256(
    readiness: _Readiness,
    *,
    binding_manifest_sha256: str,
    semantic_state_sha256: str,
    completion_contract_sha256: str,
    specimen_ledger_sha256: str,
    required_specimens_sha256: str,
) -> str:
    """Bind authorization to the exact root, executable, and promoted candidate."""

    identity = canonical_sha256(
        {
            "schema": "pokemon.red.fresh-composition-execution-identity.v2",
            "root_consumption_sha256": readiness.root_consumption_sha256,
            "source_commit": _source_commit(readiness.source),
            "runner_sha256": readiness.runner_sha256,
            "qualification_module_sha256": readiness.qualification_module_sha256,
            "design_sha256": readiness.design_sha256,
            "nonsealed_attestation_sha256": readiness.nonsealed_attestation_sha256,
            "root_provenance_sha256": readiness.root_provenance_sha256,
            "rom_sha256": readiness.rom.sha256,
            "runtime_sha256": readiness.runtime.sha256,
            "promotion_plan_sha256": readiness.candidate.plan.plan_sha256,
            "registry_sha256": readiness.candidate.registry.registry_sha256,
            "context_catalog_sha256": readiness.candidate.catalog.catalog_sha256,
            "model_file_sha256": readiness.candidate.plan.model_file_sha256,
            "model_canonical_sha256": readiness.candidate.plan.model_canonical_sha256,
            "fit_summary_file_sha256": readiness.candidate.fit_summary_sha256,
            "profile_sha256": readiness.profile.profile_sha256,
            "skill_manifest_sha256": readiness.skill_manifest["manifest_sha256"],
            "binding_manifest_sha256": binding_manifest_sha256,
            "semantic_state_sha256": semantic_state_sha256,
            "completion_contract_sha256": completion_contract_sha256,
            "specimen_ledger_sha256": specimen_ledger_sha256,
            "required_specimens_sha256": required_specimens_sha256,
            "root_lineage_sha256": canonical_sha256({"root_lineage_id": readiness.root_lineage_id}),
        }
    )
    return cast(str, identity)


def _preflight_receipt(
    readiness: _Readiness,
    admission: _Admission,
) -> dict[str, object]:
    return {
        "schema": "pokemon.red.fresh-goal-manager-composition-execution-preflight.v2",
        "status": "zero_action_preflight_passed_execution_identity_unclaimed",
        "source": readiness.source.public_dict(),
        "input_bindings": {
            "source_commit": _source_commit(readiness.source),
            "design_sha256": readiness.design_sha256,
            "runner_sha256": readiness.runner_sha256,
            "qualification_module_sha256": readiness.qualification_module_sha256,
            "rom_sha256": readiness.rom.sha256,
            "runtime_sha256": readiness.runtime.sha256,
            "runtime": readiness.runtime.public_dict(),
            "promotion_plan_sha256": readiness.candidate.plan.plan_sha256,
            "registry_sha256": readiness.candidate.registry.registry_sha256,
            "context_catalog_sha256": readiness.candidate.catalog.catalog_sha256,
            "model_file_sha256": readiness.candidate.plan.model_file_sha256,
            "model_canonical_sha256": readiness.candidate.plan.model_canonical_sha256,
            "fit_summary_file_sha256": readiness.candidate.fit_summary_sha256,
            "profile_sha256": readiness.profile.profile_sha256,
            "skill_manifest_sha256": readiness.skill_manifest["manifest_sha256"],
            "binding_manifest_sha256": admission.binding_manifest_sha256,
            "semantic_state_sha256": admission.semantic_state_sha256,
            "completion_contract_sha256": admission.completion_contract_sha256,
            "specimen_ledger_sha256": admission.specimen_ledger_sha256,
            "required_specimens_sha256": admission.required_specimens_sha256,
            "nonsealed_attestation_sha256": readiness.nonsealed_attestation_sha256,
            "root_provenance_sha256": readiness.root_provenance_sha256,
            "root_lineage_sha256": canonical_sha256({"root_lineage_id": readiness.root_lineage_id}),
            "execution_identity_sha256": admission.execution_identity_sha256,
        },
        "root_admission": {
            "roots_inspected": 1,
            "roots_admitted": 1,
            "action_free": True,
            "root_partition": "fresh_nonsealed_red_development",
            "sealed": False,
            "prior_contexts_checked": 81,
            "prior_context_overlap": 0,
            "prior_root_lineage_overlap": 0,
            "selection_basis": "title_neutral_semantic_admission_only",
            "model_guided_search": False,
            "predictions_before_freeze": 0,
            "controller_actions": 0,
            "emulator_frames": 0,
            "initial_state_integrity_verified": True,
            "initial_available_goal_count": admission.initial_available_goal_count,
            "required_field_goal_kinds": sorted(
                kind.value for kind in FRESH_COMPOSITION_REQUIRED_KINDS
            ),
            "initial_available_goal_kinds": list(admission.initial_available_goal_kinds),
        },
        "attestations": {
            "exact_model_loader_authenticated": True,
            "existing_skill_bindings_authenticated": True,
            "existing_verifiers_authenticated": True,
            "canonical_collection_ledgers_authenticated": True,
            "protected_source_isolation_attested": True,
            "development_outcomes_accessed": 0,
            "teacher_queries": 0,
            "sealed_red_accesses": 0,
            "crystal_accesses": 0,
        },
        "runner_and_one_shot": {
            "root_safe_runner_qualified": True,
            "claim_before_controller_input_enforced": True,
            "local_execution_identity_available": True,
            "fixed_account_execution_identity_available": True,
            "execution_identity_consumed": False,
            "root_claimed": False,
            "retry_same_root_after_controller_input": False,
        },
        "hard_limits": {
            "maximum_actions_per_decision": FRESH_COMPOSITION_ACTIONS_PER_DECISION,
            "maximum_frames_per_decision": FRESH_COMPOSITION_FRAMES_PER_DECISION,
            "maximum_episode_actions": FRESH_COMPOSITION_MAX_ACTIONS,
            "maximum_episode_frames": FRESH_COMPOSITION_MAX_FRAMES,
            "hard_action_limiter_qualified": True,
            "hard_frame_limiter_qualified": True,
            "in_flight_enforcement": True,
            "independent_accounting_reconciled": True,
        },
        "durability": {
            "decision_write_before_action_enforced": True,
            "failure_artifact_abort_attempted_when_episode_writer_available": True,
            "failure_storage_failure_conservatively_consumes_root": True,
            "first_failure_phase_retained_when_storage_available": True,
            "pre_writer_storage_failure_leaves_durable_root_consumption_claim": True,
            "failed_decision_write_stops_before_action": True,
            "success_terminal_durable_before_result_claim": True,
            "claim_consumption_bound_to_first_controller_input": True,
        },
        "zero_effects": {
            "model_predictions": 0,
            "goal_manager_decisions": 0,
            "controller_actions": 0,
            "emulator_frames": 0,
            "game_executions": 0,
            "composition_episodes": 0,
            "model_fits": 0,
            "model_updates": 0,
            "teacher_queries": 0,
            "sealed_red_accesses": 0,
            "crystal_accesses": 0,
            "full_replays": 0,
        },
        "claim_boundary": {
            "supported": (
                "One exact published V2 runner/root identity passed a zero-action, "
                "zero-prediction execution preflight and remains unclaimed."
            ),
            "unsupported": [
                "episode_execution_or_pass",
                "fresh_context_generalization",
                "authority_or_promotion",
                "transfer",
                "red_completion",
                "living_pokedex_ability",
            ],
        },
        "tracked_private_identities": 0,
        "tracked_private_paths": 0,
    }


def _execute(
    args: argparse.Namespace,
    readiness: _Readiness,
    admission: _Admission,
) -> dict[str, object]:
    try:
        adjacent_before = rom_adjacent_artifacts(readiness.rom_path)
        source_commit = _source_commit(readiness.source)
        if args.expected_execution_identity_sha256 != admission.execution_identity_sha256:
            raise FreshCompositionRunError("execution identity differs from authorization")
    except Exception:
        raise FreshCompositionPreclaimFailure("execution_authorization") from None
    # Crash ordering is intentional: the account-wide root marker is the source of
    # truth across output roots, so it is synchronized before the local episode claim.
    write_root_claim(
        readiness.claim_registry,
        root_consumption_sha256=readiness.root_consumption_sha256,
        execution_identity_sha256=admission.execution_identity_sha256,
        source_commit=source_commit,
        runner_sha256=readiness.runner_sha256,
    )
    writer: EpisodeWriter | None = None
    sink: EpisodeTrajectorySink | None = None
    try:
        writer = readiness.output_root.begin_episode(readiness.episode_id)
        writer.append(
            "preregistration",
            {
                "schema": "pokemon.red.fresh-composition-preregistration.v2",
                "execution_identity_sha256": admission.execution_identity_sha256,
                "root_consumption_sha256": readiness.root_consumption_sha256,
                "design_sha256": readiness.design_sha256,
                "source": readiness.source.public_dict(),
                "runner_sha256": readiness.runner_sha256,
                "skill_manifest_sha256": readiness.skill_manifest["manifest_sha256"],
                "runtime_sha256": readiness.runtime.sha256,
                "model_canonical_sha256": readiness.candidate.plan.model_canonical_sha256,
                "teacher_queries": 0,
                "teacher_fallbacks": 0,
                "sealed_red_accesses": 0,
                "crystal_accesses": 0,
            },
            durable=True,
        )
        trajectory_sink = EpisodeTrajectorySink(
            writer,
            episode_id=readiness.episode_id,
            game_id="pokemon.mainline:red:gb:us:rev0",
            durable_writes=True,
        )
        trajectory_sink.write_episode_header(
            metadata={
                "schema": "pokemon.red.fresh-composition-episode-header.v2",
                "execution_identity_sha256": admission.execution_identity_sha256,
                "root_consumption_sha256": readiness.root_consumption_sha256,
                "model_canonical_sha256": readiness.candidate.plan.model_canonical_sha256,
                "source": readiness.source.public_dict(),
                "rom": readiness.rom.public_dict(),
                "runtime": readiness.runtime.public_dict(),
            }
        )
        sink = trajectory_sink
        with PyBoyAdapter(
            readiness.rom_path,
            watch=False,
            speed=None,
        ) as emulator:
            emulator.load_state_bytes(readiness.capture.state_bytes)
            frames = WindowedFrameBudgetController(
                emulator,
                maximum_frames_per_window=FRESH_COMPOSITION_FRAMES_PER_DECISION,
                maximum_total_frames=FRESH_COMPOSITION_MAX_FRAMES,
            )
            reader = PokemonRedStateReader(frames)
            runtime = build_red_goal_context_runtime(
                profile=readiness.profile,
                capture=readiness.capture,
                emulator=frames,
                reader=reader,
            )
            frame_safe = FrameSafeExecutor(
                frames,
                DEFAULT_NEW_GAME_TIMING.controller_timing(),
            )
            snapshot_provider = PokemonRedObservationEncoder.from_state_reader(reader)
            recorder: RecordingExecutor[Any, Any] = RecordingExecutor(
                delegate=frame_safe,
                snapshot_provider=snapshot_provider,
                sink=sink,
                episode_id=readiness.episode_id,
            )
            hard_actions = HardCompositionActionLimiter(recorder)
            actions = CountingExecutor(hard_actions)
            meter = CompositionIndependentBudgetMeter(hard_actions, frames)
            policy = LearnedGoalManagerPolicy(
                readiness.candidate.model,
                confidence_threshold=FRESH_COMPOSITION_CONFIDENCE_FLOOR,
            )
            trajectory = GoalManagerTrajectoryObserver(
                episode_id=readiness.episode_id,
                root_lineage_id=readiness.root_lineage_id,
                # This is a nonsealed development episode, but not a reusable model-fit
                # dataset partition.  Keep its trajectory explicitly non-counting.
                partition="unassigned",
                environment_id="pokemon.mainline:red:gb:us:rev0",
                actor="learned_goal_manager",
                policy_id="red-goal-manager-af29d7e7",
                collection_id="fresh-goal-manager-composition-v2",
                assignment_id=admission.execution_identity_sha256,
                source_commit=source_commit,
                snapshot_provider=snapshot_provider,
                recorder=recorder,
                sink=sink,
            )
            observe = _live_observer(
                runtime=runtime,
                actions=actions,
                meter=meter,
                admission=admission,
            )
            result = run_goal_manager_composition_episode(
                observe=observe,
                policy=policy,
                trajectory=trajectory,
                budget_meter=meter,
            )
            if recorder.recording_failures:
                raise FreshCompositionRunError("composition trajectory instrumentation failed")
        _require_unchanged_inputs(
            readiness,
            adjacent_before=adjacent_before,
        )
        sink.record_event(
            SparseEvent(
                event_id=f"{readiness.episode_id}:terminal",
                episode_id=readiness.episode_id,
                step_index=recorder.next_step_index,
                kind="terminal",
                payload={
                    "status": "complete",
                    "execution_identity_sha256": admission.execution_identity_sha256,
                    "composition": cast(
                        Mapping[str, JSONValue],
                        result.public_dict(),
                    ),
                },
            )
        )
        sink.finalize()
        summary = writer.complete()
        return {
            "schema": "pokemon.red.fresh-composition-execution-summary.v2",
            "status": "complete",
            "execution_identity_sha256": admission.execution_identity_sha256,
            "episode": summary.public_dict(),
            "composition": result.public_dict(),
            "teacher_queries": 0,
            "teacher_fallbacks": 0,
            "sealed_red_accesses": 0,
            "crystal_accesses": 0,
            "private_path_fields": 0,
        }
    except BaseException as failure:
        if writer is not None:
            _retain_failure_terminal(
                writer,
                sink=sink,
                episode_id=readiness.episode_id,
                execution_identity_sha256=admission.execution_identity_sha256,
                failure=failure,
            )
        raise


def _live_observer(
    *,
    runtime: RedGoalContextRuntime,
    actions: CountingExecutor,
    meter: CompositionIndependentBudgetMeter,
    admission: _Admission,
) -> Callable[[], GoalManagerCompositionObservation]:
    observations = 0

    def observe() -> GoalManagerCompositionObservation:
        nonlocal observations
        if observations:
            meter.begin_decision_window()
        before = meter.checkpoint()
        live = runtime.adapter.observe()
        binding_set = runtime.enumerator(actions).enumerate(live)
        if meter.checkpoint() != before:
            raise FreshCompositionRunError(
                "composition reobservation attempted emulator or controller work"
            )
        checkpoint = living_collection_checkpoint(live)
        available = tuple(binding.kind.value for binding in binding_set.bindings)
        semantic = canonical_sha256(
            {
                "schema": "pokemon.red.fresh-composition-semantic-state.v1",
                "goal_observation": live.public_dict(),
                "collection": checkpoint.public_dict(),
                "available_goal_kinds": list(available),
            }
        )
        if observations == 0 and (
            semantic != admission.semantic_state_sha256
            or goal_binding_manifest_sha256(binding_set) != admission.binding_manifest_sha256
        ):
            raise FreshCompositionRunError("composition root changed after action-free admission")
        observations += 1
        return GoalManagerCompositionObservation(
            semantic_state_sha256=semantic,
            situation=live.situation,
            binding_set=binding_set,
            collection=checkpoint,
        )

    return observe


def _retain_failure_terminal(
    writer: EpisodeWriter,
    *,
    sink: EpisodeTrajectorySink | None,
    episode_id: str,
    execution_identity_sha256: str,
    failure: BaseException,
) -> None:
    failure_phase = _failure_phase(failure)
    terminal = {
        "status": "failed",
        "execution_identity_sha256": execution_identity_sha256,
        "first_failure_retained": True,
        "failure_class": _failure_class(failure),
        "failure_phase": failure_phase,
    }
    try:
        if sink is None:
            writer.append(
                "terminal",
                {
                    "schema": "pokemon.red.fresh-composition-terminal.v2",
                    **terminal,
                },
                durable=True,
            )
        else:
            sink.record_event(
                SparseEvent(
                    event_id=f"{episode_id}:terminal",
                    episode_id=episode_id,
                    step_index=0,
                    kind="terminal",
                    payload=cast(Mapping[str, JSONValue], terminal),
                )
            )
            sink.finalize()
    except BaseException:
        # Do not attempt a second terminal append: the first write may have reached
        # the stream before its fsync failed.  A duplicate would corrupt recovery.
        pass
    try:
        writer.abort("composition_failed")
    except BaseException:
        # The fixed-account claim is already durable, so even storage failure keeps
        # this exact root conservatively consumed across output roots.
        return


def _failure_phase(failure: BaseException) -> str:
    if isinstance(failure, FreshCompositionRunError):
        return "runner_guard"
    return "composition_execution"


def _failure_class(failure: BaseException) -> str:
    if isinstance(failure, FreshCompositionRunError):
        return "runner_guard_error"
    if isinstance(failure, (KeyboardInterrupt, SystemExit)):
        return "external_interruption"
    return "composition_error"


def _run(args: argparse.Namespace) -> dict[str, object]:
    readiness = _observe_preclaim_failure(
        "readiness_authentication",
        lambda: _prepare_readiness(args),
    )
    admission = _observe_preclaim_failure(
        "action_free_admission",
        lambda: _admit_root(readiness),
    )
    if args.preflight_only:
        return _observe_preclaim_failure(
            "success_receipt_construction",
            lambda: _preflight_receipt(readiness, admission),
        )
    return _execute(args, readiness, admission)


def _observe_preclaim_failure(
    stage: str,
    operation: Callable[[], _ResultT],
) -> _ResultT:
    if stage not in _PREFLIGHT_FAILURE_STAGES:
        raise ValueError("preclaim failure stage is not allowlisted")
    try:
        return operation()
    except Exception:
        raise FreshCompositionPreclaimFailure(stage) from None


def _preclaim_failure_receipt(failure: FreshCompositionPreclaimFailure) -> dict[str, object]:
    admission_status = (
        "passed"
        if failure.stage in {"execution_authorization", "success_receipt_construction"}
        else "not_attested"
    )
    return {
        "schema": "pokemon.fresh-root.composition-preclaim-failure.v1",
        "status": "caught_in_process_preclaim_failure",
        "failure_stage": failure.stage,
        "admission_status": admission_status,
        "runner_success_receipt_emitted": False,
        "claim_written_by_this_invocation": False,
        "execution_identity_authorized": False,
        "protected_access_status": (
            "not_attested" if failure.stage == "readiness_authentication" else "verified_absent"
        ),
        "counter_treatment": {
            "outcome_questions_added": 0,
            "composition_episodes_added": 0,
            "model_fits_added": 0,
            "unseen_comparisons_added": 0,
            "authority_promotions_added": 0,
            "transfer_results_added": 0,
        },
        "zero_effects": {
            "model_predictions": 0,
            "goal_manager_decisions": 0,
            "controller_actions": 0,
            "emulator_frames": 0,
            "game_executions": 0,
            "composition_episodes": 0,
            "episode_outcomes": 0,
            "model_fits": 0,
            "model_updates": 0,
            "teacher_queries": 0,
            "full_replays": 0,
        },
        "claim_boundary": {
            "supported": (
                "A caught in-process composition-runner preclaim failure was reduced to one "
                "allowlisted stage before this invocation wrote an execution claim or made a "
                "model decision."
            ),
            "unsupported": [
                "private_failure_cause",
                "root_identity",
                "episode_execution_or_outcome",
                "learned_authority",
                "transfer",
                "red_completion",
                "living_pokedex_ability",
            ],
        },
        "tracked_private_identities": 0,
        "tracked_private_paths": 0,
    }


def _require_nonsealed_attestation(
    path: Path,
    *,
    capture: GoalManagerContextCapture,
    profile_sha256: str,
    expected_attestation_sha256: str,
    root_provenance_sha256: str,
    root_lineage_id: str,
) -> None:
    try:
        payload = path.read_bytes()
        document = json.loads(payload.decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FreshCompositionRunError("nonsealed attestation is invalid") from error
    if (
        not isinstance(document, dict)
        or len(payload) > _MAX_ATTESTATION_BYTES
        or hashlib.sha256(payload).hexdigest()
        != _require_sha256(
            expected_attestation_sha256,
            subject="nonsealed attestation",
        )
        or json.dumps(
            document,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
        != payload
        or set(document)
        != {
            "controller_actions_before_freeze",
            "envelope_sha256",
            "model_predictions_before_freeze",
            "origin_class",
            "partition",
            "prior_root_lineage_id",
            "profile_sha256",
            "root_provenance_sha256",
            "schema",
            "sealed",
            "state_sha256",
        }
        or document.get("schema") != "pokemon.red.fresh-composition-nonsealed-root-attestation.v1"
        or document.get("partition") != "fresh_nonsealed_red_development"
        or document.get("sealed") is not False
        or document.get("origin_class")
        != "preexisting_nonsealed_goal_manager_qualification_capture"
        or document.get("state_sha256") != capture.state_sha256
        or document.get("envelope_sha256") != capture.envelope_sha256
        or document.get("profile_sha256") != profile_sha256
        or document.get("root_provenance_sha256") != root_provenance_sha256
        or document.get("prior_root_lineage_id") != root_lineage_id
        or document.get("model_predictions_before_freeze") != 0
        or document.get("controller_actions_before_freeze") != 0
    ):
        raise FreshCompositionRunError("nonsealed root attestation differs")


def _authenticate_root_provenance(
    path: Path,
    *,
    capture: GoalManagerContextCapture,
    expected_sha256: str,
) -> tuple[str, str]:
    try:
        payload = path.read_bytes()
        document = json.loads(payload.decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FreshCompositionRunError("root provenance is invalid") from error
    source_commit = document.get("source_commit") if isinstance(document, dict) else None
    slot_id = document.get("slot_id") if isinstance(document, dict) else None
    if (
        not isinstance(document, dict)
        or len(payload) > _MAX_ATTESTATION_BYTES
        or hashlib.sha256(payload).hexdigest()
        != _require_sha256(expected_sha256, subject="root provenance")
        or not isinstance(source_commit, str)
        or _GIT_COMMIT.fullmatch(source_commit) is None
        or not isinstance(slot_id, str)
        or not slot_id
    ):
        raise FreshCompositionRunError("root provenance differs")
    try:
        registry = load_committed_goal_manager_registry_at_revision(
            PROJECT_ROOT,
            source_commit,
        )
        assignment = registry.assignment(slot_id)
        preflight = parse_goal_manager_preflight(payload, assignment)
    except Exception as error:
        raise FreshCompositionRunError(
            "root provenance is not an authenticated historical preflight"
        ) from error
    if (
        preflight.capture_id != capture.capture_id
        or preflight.state_sha256 != capture.state_sha256
        or preflight.envelope_sha256 != capture.envelope_sha256
    ):
        raise FreshCompositionRunError("root provenance capture differs")
    return assignment.root_lineage_id, preflight.binding_manifest_sha256


def _require_unchanged_inputs(
    readiness: _Readiness,
    *,
    adjacent_before: tuple[tuple[bool, str | None], ...],
) -> None:
    if (
        _file_sha256(readiness.state_path, subject="state") != readiness.capture.state_sha256
        or _file_sha256(readiness.envelope_path, subject="envelope")
        != readiness.capture.envelope_sha256
        or _file_sha256(readiness.profile_path, subject="profile")
        != readiness.profile.profile_sha256
        or _file_sha256(
            readiness.nonsealed_attestation_path,
            subject="nonsealed attestation",
        )
        != readiness.nonsealed_attestation_sha256
        or _file_sha256(
            readiness.root_provenance_path,
            subject="root provenance",
        )
        != readiness.root_provenance_sha256
        or rom_adjacent_artifacts(readiness.rom_path) != adjacent_before
        or build_runtime_identity().sha256 != readiness.runtime.sha256
    ):
        raise FreshCompositionRunError("composition private inputs changed")


def _external_regular(path: Path, *, subject: str) -> Path:
    resolved = path.resolve()
    try:
        metadata = path.lstat()
    except OSError as error:
        raise FreshCompositionRunError(f"{subject} is unavailable") from error
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or resolved.is_relative_to(PROJECT_ROOT.resolve())
    ):
        raise FreshCompositionRunError(f"{subject} must be a private external file")
    return resolved


def _file_sha256(path: Path, *, subject: str) -> str:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError as error:
        raise FreshCompositionRunError(f"{subject} cannot be authenticated") from error
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise FreshCompositionRunError(f"{subject} must be a regular file")
    return hashlib.sha256(payload).hexdigest()


def _require_sha256(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise FreshCompositionRunError(f"{subject} digest is invalid")
    return value


def _source_commit(source: SourceIdentity) -> str:
    if source.git_commit is None or _GIT_COMMIT.fullmatch(source.git_commit) is None:
        raise FreshCompositionRunError("composition source commit is unavailable")
    return cast(str, source.git_commit)


def _require_imported_code_from_project() -> None:
    expected_root = _BOOTSTRAP_SRC.resolve()
    for name, module in tuple(sys.modules.items()):
        if name != "pokemon_red_completion" and not name.startswith("pokemon_red_completion."):
            continue
        module_file = getattr(module, "__file__", None)
        if module_file is None:
            continue
        try:
            imported_path = Path(module_file).resolve(strict=True)
        except OSError as error:
            raise FreshCompositionRunError(
                "composition imported source cannot be authenticated"
            ) from error
        if not imported_path.is_relative_to(expected_root):
            raise FreshCompositionRunError(
                "composition imported code is outside the reviewed source tree"
            )


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        result = _run(args)
        encoded = _serialize_success_result(args, result)
    except FreshCompositionPreclaimFailure as failure:
        print(
            json.dumps(
                _preclaim_failure_receipt(failure),
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 2
    except Exception:
        parser.error("Fresh composition runner failed closed; private details were withheld.")
    print(encoded)
    return 0


def _serialize_success_result(
    args: argparse.Namespace,
    result: dict[str, object],
) -> str:
    def operation() -> str:
        return json.dumps(result, indent=2, sort_keys=True)

    if args.preflight_only:
        return _observe_preclaim_failure("success_receipt_construction", operation)
    return operation()


if __name__ == "__main__":
    raise SystemExit(main())
