#!/usr/bin/env python3
"""Generate or execute repeatable Red party-outcome development scenarios.

This is deliberately not a successor to the one-shot 14/55 campaign.  It
selects fresh scenario identities from independent authenticated non-sealed
roots, keeps train and development isolated, applies deterministic candidate
permutations and timing offsets, and records measured outcomes without teacher
choices.  Development failures remain evidence but may be rerun under a new
development artifact; no sealed or benchmark claim is made here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
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
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (  # noqa: E402
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.hideout import DEFAULT_HIDEOUT_TIMING  # noqa: E402
from pokemon_red_completion.observation import (  # noqa: E402
    PokemonRedStateReader,
    RamAddress,
)
from pokemon_red_completion.party import (  # noqa: E402
    MAX_LEVEL,
    PartyMemberObservation,
    PartyObservation,
)
from pokemon_red_completion.party_development_adapter import (  # noqa: E402
    BoundPartyDevelopmentMenu,
    PartyDevelopmentCapabilityState,
    PartyDevelopmentSemanticSnapshot,
)
from pokemon_red_completion.party_development_catalog import (  # noqa: E402
    PartyDevelopmentProspectiveCatalog,
)
from pokemon_red_completion.party_development_frozen_catalog import (  # noqa: E402
    PartyDevelopmentFrozenQuestion,
)
from pokemon_red_completion.party_development_inventory import (  # noqa: E402
    PartyDevelopmentCheckpointInventory,
    PartyDevelopmentInventoryEntry,
)
from pokemon_red_completion.party_development_outcome_campaign import (  # noqa: E402
    PartyDevelopmentOutcomeDose,
    PartyDevelopmentOutcomeTrialAssignment,
)
from pokemon_red_completion.party_development_outcome_dataset import (  # noqa: E402
    PartyDevelopmentReadinessPolicy,
    audit_party_development_outcome_catalog,
)
from pokemon_red_completion.party_development_outcomes import (  # noqa: E402
    PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE,
    PartyDevelopmentOutcomeTrialV2,
    adapt_party_development_outcomes_v2,
)
from pokemon_red_completion.party_development_question_reservations import (  # noqa: E402
    PartyDevelopmentContextPreparation,
    PartyDevelopmentQuestionReservation,
    PartyDevelopmentQuestionReservationPlan,
)
from pokemon_red_completion.party_development_rank import (  # noqa: E402
    PARTY_DEVELOPMENT_FEATURE_NAMES,
    EvolutionRouteKind,
    PartyDevelopmentGoal,
    VenuePriorFeatureMode,
)
from pokemon_red_completion.party_development_scenarios import (  # noqa: E402
    PartyDevelopmentScenarioAssignment,
    PartyDevelopmentScenarioOption,
    RepeatablePartyScenarioPlan,
    permute_bound_party_development_menu,
    select_repeatable_party_scenarios,
)
from pokemon_red_completion.party_development_venue_priors import (  # noqa: E402
    PartyDevelopmentVenuePriorRegistry,
)
from pokemon_red_completion.private_artifacts import (  # noqa: E402
    PRIVATE_ARTIFACT_SCHEMA_VERSION,
    PRIVATE_JSON_ARTIFACT_FORMAT,
    open_private_root,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    canonical_sha256,
    detect_source_identity,
)
from pokemon_red_completion.red_goal_context import (  # noqa: E402
    build_red_goal_context_runtime,
)
from pokemon_red_completion.red_goal_context_profile import (  # noqa: E402
    RedGoalContextProfile,
    load_red_goal_context_profile,
)
from pokemon_red_completion.red_goal_manager import RedGoalObservation  # noqa: E402
from pokemon_red_completion.red_party import PokemonRedPartyReader  # noqa: E402
from pokemon_red_completion.red_party_development_adapter import (  # noqa: E402
    RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY,
    RED_PARTY_DEVELOPMENT_TRANSITION_GUARDS,
    RedPartyDevelopmentExecutionCapabilityError,
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
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402
from pokemon_red_completion.scenario_outcomes import (  # noqa: E402
    CandidateOutcome,
    OutcomeCandidate,
    OutcomeEvidenceStatus,
    ScenarioOutcomeExample,
)
from pokemon_red_completion.team_training import (  # noqa: E402
    BalancedTeamPolicy,
    GrindingArea,
    TeamTrainingProgress,
)
from pokemon_red_completion.training_candidate_rank import (  # noqa: E402
    TrainingChoiceKind,
)

_TRAINING_VENUES = (
    ROUTE_11_TRAINING_VENUE,
    DIGLETTS_CAVE_TRAINING_VENUE,
)
_HP_PP_BIN_ORDER = ("empty", "low", "middle", "high")
_DEVELOPMENT_LANE_ID = "repeatable-party-outcome-learning-v1"
_BATTLE_CREDIT_PROTOCOL_ID = "switch-assisted-fixed-dose-v1"


def _battle_credit_protocol(completed_battles: int) -> dict[str, object]:
    """Describe the title-neutral intervention used by every candidate trial."""

    if type(completed_battles) is not int or completed_battles <= 0:  # noqa: E721
        raise RepeatablePartyOutcomeRunError(
            "repeatable development battle-credit dose must be positive"
        )
    return {
        "protocol_id": _BATTLE_CREDIT_PROTOCOL_ID,
        "selected_member_participates": True,
        "qualified_escort_completes_battle": True,
        "candidate_eligibility_scope": "curriculum_venue_band_relevant",
        "candidate_eligibility_is_direct_combat_claim": False,
        "venue_prior_feature_mode": VenuePriorFeatureMode.MASKED_UNCALIBRATED.value,
        "completed_battles": completed_battles,
        "teacher_choices": 0,
        "private_identity_fields": 0,
    }


def _switch_assisted_venue_contract_sha256(
    calibrated_contract_sha256: str,
    *,
    completed_battles: int,
) -> str:
    """Bind a venue to the new intervention without reusing its old statistics."""

    if (
        not isinstance(calibrated_contract_sha256, str)
        or len(calibrated_contract_sha256) != 64
        or any(character not in "0123456789abcdef" for character in calibrated_contract_sha256)
    ):
        raise RepeatablePartyOutcomeRunError(
            "repeatable development calibrated venue contract is invalid"
        )
    return canonical_sha256(
        {
            "schema": "pokemon.core.switch-assisted-venue-operational-contract.v1",
            "calibrated_predecessor_contract_sha256": calibrated_contract_sha256,
            "battle_credit_protocol": _battle_credit_protocol(completed_battles),
            "calibrated_performance_values_reused": False,
        }
    )


def _switch_assisted_outcome_policy(
    dose: PartyDevelopmentOutcomeDose,
) -> BalancedTeamPolicy:
    """Bind the fixed dose to participation credit instead of direct combat."""

    if not isinstance(dose, PartyDevelopmentOutcomeDose):
        raise TypeError("dose must be a PartyDevelopmentOutcomeDose")
    return replace(
        RED_PARTY_DEVELOPMENT_OUTCOME_POLICY,
        # No below-floor trainee can satisfy this direct-fight margin. The
        # selected member still leads and participates; the qualified escort
        # completes the battle after the switch.
        safe_lead_level=None,
        minimum_direct_level_advantage=MAX_LEVEL,
        max_battles=dose.completed_battles,
        max_steps=dose.maximum_encounter_steps,
        max_healing_trips=dose.maximum_healing_trips - 1,
        max_faints=dose.maximum_faints,
    )


class RepeatablePartyOutcomeRunError(RuntimeError):
    """Raised when development evidence would cross a protected boundary."""


@dataclass(frozen=True, slots=True)
class _RedOptionRuntime:
    option: PartyDevelopmentScenarioOption
    reservation: PartyDevelopmentQuestionReservation
    capture: GoalManagerContextCapture
    profile: RedGoalContextProfile
    snapshot: PartyDevelopmentSemanticSnapshot
    menu: (
        BoundPartyDevelopmentMenu[PartyMemberObservation] | BoundPartyDevelopmentMenu[GrindingArea]
    )
    venue_question_trainee: PartyMemberObservation | None
    profile_file_sha256: str


@dataclass(frozen=True, slots=True)
class _SelectedRuntime:
    assignment: PartyDevelopmentScenarioAssignment
    reservation: PartyDevelopmentQuestionReservation
    capture: GoalManagerContextCapture
    profile: RedGoalContextProfile
    snapshot: PartyDevelopmentSemanticSnapshot
    menu: (
        BoundPartyDevelopmentMenu[PartyMemberObservation] | BoundPartyDevelopmentMenu[GrindingArea]
    )
    binding_question: PartyDevelopmentFrozenQuestion
    venue_question_trainee: PartyMemberObservation | None


@dataclass(frozen=True, slots=True)
class _ExecutionPorts:
    observation_emulator: PyBoyAdapter
    controller: FrameBudgetEmulator
    reader: PokemonRedStateReader
    party_reader: PokemonRedPartyReader


@dataclass(frozen=True, slots=True)
class _TrialMeasurement:
    outcome: CandidateOutcome
    private_evidence: Mapping[str, object]
    controller_actions: int
    frames_executed: int


@dataclass(frozen=True, slots=True)
class _DevelopmentArtifactExclusion:
    """Verified, path-free exclusions recovered from one prior pilot."""

    root_lineage_ids: frozenset[str]
    initial_state_sha256: frozenset[str]
    manifest_sha256: str
    plan_sha256: str


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--venue-prior-registry", type=Path, required=True)
    parser.add_argument("--prior-reservation-plan", type=Path, required=True)
    parser.add_argument("--catalog-root", type=Path, required=True)
    parser.add_argument("--private-artifact-root", type=Path, default=None)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--train-count", type=int, default=8)
    parser.add_argument("--development-count", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260816)
    parser.add_argument("--completed-battles", type=int, default=1)
    parser.add_argument("--maximum-timing-offset-frames", type=int, default=255)
    parser.add_argument(
        "--exclude-root-lineage-id",
        action="append",
        default=[],
        help="development-private roots with consumed outcome trials",
    )
    parser.add_argument(
        "--exclude-development-artifact",
        type=Path,
        action="append",
        default=[],
        help="verified prior repeatable-development artifact whose roots must not recur",
    )
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser


def _load_json(path: Path, *, subject: str) -> tuple[Mapping[str, object], str]:
    try:
        payload = path.read_bytes()
        document = json.loads(payload.decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RepeatablePartyOutcomeRunError(
            f"repeatable development {subject} is unavailable or invalid"
        ) from error
    if not isinstance(document, Mapping):
        raise RepeatablePartyOutcomeRunError(f"repeatable development {subject} is not an object")
    return document, hashlib.sha256(payload).hexdigest()


def _require_external(path: Path, *, subject: str) -> Path:
    resolved = path.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise RepeatablePartyOutcomeRunError(
            f"repeatable development {subject} must remain outside the repository"
        )
    return resolved


def _development_artifact_exclusion(
    artifact_path: Path,
) -> _DevelopmentArtifactExclusion:
    """Authenticate one prior pilot and recover only disjointness identities.

    The current runner never opens its outcomes or failures. It verifies the
    immutable manifest and the single plan stream, then retains only root and
    state digests needed to prevent accidental reuse.
    """

    artifact = _require_external(
        artifact_path,
        subject="excluded development artifact",
    )
    manifest, manifest_sha256 = _load_json(
        artifact / "manifest.json",
        subject="excluded development artifact manifest",
    )
    if (
        manifest.get("format") != PRIVATE_JSON_ARTIFACT_FORMAT
        or manifest.get("schema_version") != PRIVATE_ARTIFACT_SCHEMA_VERSION
        or manifest.get("kind") != "repeatable_party_outcome_development"
        or manifest.get("status") != "complete"
    ):
        raise RepeatablePartyOutcomeRunError(
            "excluded development artifact manifest identity is invalid"
        )
    files = manifest.get("files")
    if not isinstance(files, list):
        raise RepeatablePartyOutcomeRunError(
            "excluded development artifact file inventory is invalid"
        )
    plan_entries = tuple(
        entry
        for entry in files
        if isinstance(entry, Mapping) and entry.get("filename") == "plan.jsonl"
    )
    if len(plan_entries) != 1:
        raise RepeatablePartyOutcomeRunError(
            "excluded development artifact must bind exactly one plan stream"
        )
    plan_entry = plan_entries[0]
    try:
        plan_payload = (artifact / "plan.jsonl").read_bytes()
    except OSError as error:
        raise RepeatablePartyOutcomeRunError(
            "excluded development artifact plan is unavailable"
        ) from error
    declared_bytes = plan_entry.get("bytes")
    declared_records = plan_entry.get("records")
    declared_sha256 = plan_entry.get("sha256")
    if (
        type(declared_bytes) is not int  # noqa: E721
        or declared_bytes != len(plan_payload)
        or declared_records != 1
        or not isinstance(declared_sha256, str)
        or hashlib.sha256(plan_payload).hexdigest() != declared_sha256
    ):
        raise RepeatablePartyOutcomeRunError(
            "excluded development artifact plan differs from its manifest"
        )
    try:
        lines = plan_payload.decode("ascii").splitlines()
        record = json.loads(lines[0]) if len(lines) == 1 else None
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RepeatablePartyOutcomeRunError(
            "excluded development artifact plan is invalid ASCII JSONL"
        ) from error
    if not isinstance(record, Mapping) or record.get("record_type") != (
        "repeatable_party_development_plan"
    ):
        raise RepeatablePartyOutcomeRunError(
            "excluded development artifact plan record identity is invalid"
        )
    plan = record.get("plan")
    plan_sha256 = record.get("plan_sha256")
    if (
        not isinstance(plan, Mapping)
        or plan.get("schema") != "pokemon.core.repeatable-party-development-scenario-plan.v1"
        or not isinstance(plan_sha256, str)
        or canonical_sha256(plan) != plan_sha256
    ):
        raise RepeatablePartyOutcomeRunError(
            "excluded development artifact semantic plan binding is invalid"
        )
    assignments = plan.get("assignments")
    if not isinstance(assignments, list) or not assignments:
        raise RepeatablePartyOutcomeRunError(
            "excluded development artifact plan has no assignments"
        )
    roots: list[str] = []
    states: list[str] = []
    partition_counts: Counter[str] = Counter()
    for assignment in assignments:
        if not isinstance(assignment, Mapping):
            raise RepeatablePartyOutcomeRunError(
                "excluded development artifact assignment is invalid"
            )
        root = assignment.get("root_lineage_id")
        state = assignment.get("initial_state_sha256")
        partition = assignment.get("partition")
        if (
            assignment.get("schema") != "pokemon.core.repeatable-party-development-assignment.v1"
            or not isinstance(root, str)
            or not root
            or not isinstance(state, str)
            or len(state) != 64
            or any(character not in "0123456789abcdef" for character in state)
            or partition
            not in {
                ScenarioPartition.TRAIN.value,
                ScenarioPartition.DEVELOPMENT.value,
            }
            or type(assignment.get("candidate_count")) is not int  # noqa: E721
            or assignment["candidate_count"] < 2
            or assignment.get("private_path_fields") != 0
        ):
            raise RepeatablePartyOutcomeRunError(
                "excluded development artifact assignment semantics are invalid"
            )
        roots.append(root)
        states.append(state)
        partition_counts[partition] += 1
    if (
        len(set(roots)) != len(roots)
        or len(set(states)) != len(states)
        or plan.get("unique_root_count") != len(roots)
        or plan.get("unique_initial_state_count") != len(states)
        or plan.get("partition_counts") != dict(partition_counts)
        or plan.get("teacher_choice_targets") != 0
        or plan.get("sealed_test_cases_opened") != 0
        or plan.get("private_path_fields") != 0
    ):
        raise RepeatablePartyOutcomeRunError(
            "excluded development artifact plan summary is inconsistent"
        )
    return _DevelopmentArtifactExclusion(
        root_lineage_ids=frozenset(roots),
        initial_state_sha256=frozenset(states),
        manifest_sha256=manifest_sha256,
        plan_sha256=plan_sha256,
    )


def _inventory_reservation(
    entry: PartyDevelopmentInventoryEntry,
    *,
    option_id: str,
    kind: TrainingChoiceKind,
    goal: PartyDevelopmentGoal,
) -> PartyDevelopmentQuestionReservation:
    hp_bins = tuple(
        value for value in _HP_PP_BIN_ORDER if value in {member.hp_bin for member in entry.members}
    )
    pp_bins = tuple(
        value for value in _HP_PP_BIN_ORDER if value in {member.pp_bin for member in entry.members}
    )
    routes = tuple(
        route
        for route in EvolutionRouteKind
        if route in {item for member in entry.members for item in member.evolution_routes}
    )
    return PartyDevelopmentQuestionReservation(
        scenario_id=option_id,
        source_checkpoint_id=entry.checkpoint_id,
        source_state_sha256=entry.state_sha256,
        source_envelope_sha256=entry.envelope_sha256,
        source_semantic_signature_sha256=entry.semantic_signature_sha256,
        partition=entry.partition,
        kind=kind,
        goal=goal,
        preparation=PartyDevelopmentContextPreparation.NONE,
        target_pp_bin=None,
        source_member_count=len(entry.members),
        source_trainable_count=sum(member.trainable for member in entry.members),
        source_hp_bins=hp_bins,
        source_pp_bins=pp_bins,
        source_evolution_route_kinds=routes,
    )


def _question_paths(
    catalog_root: Path,
    checkpoint_id: str,
) -> tuple[Path, Path, Path]:
    state = catalog_root / "captures" / f"{checkpoint_id}.state"
    envelope = state.with_suffix(".state.json")
    profile = catalog_root / "profiles" / f"{checkpoint_id}.json"
    if not state.is_file() or not envelope.is_file() or not profile.is_file():
        raise RepeatablePartyOutcomeRunError(
            "repeatable development root lacks its capture, envelope, or profile"
        )
    return state, envelope, profile


def _menu_for_snapshot(
    snapshot: PartyDevelopmentSemanticSnapshot,
    kind: TrainingChoiceKind,
) -> tuple[
    BoundPartyDevelopmentMenu[PartyMemberObservation]
    | BoundPartyDevelopmentMenu[GrindingArea]
    | None,
    PartyMemberObservation | None,
]:
    if kind is TrainingChoiceKind.TRAINEE:
        return snapshot.trainee_menu(ROUTE_11_TRAINING_VENUE.band), None
    trainee = snapshot.unique_weakest_goal_relevant_venue_trainee()
    return snapshot.venue_menu(trainee), trainee


def _capability_root_rejection_code(
    snapshot: PartyDevelopmentSemanticSnapshot,
) -> str | None:
    """Return one identity-free reason when no pair can satisfy an axis."""

    capabilities = tuple(
        capability
        for profile in snapshot.member_profiles
        for capability in profile.execution_capabilities_by_venue
    )
    for axis in ("transition", "battle", "recovery"):
        if capabilities and all(
            getattr(capability, axis) is PartyDevelopmentCapabilityState.BLOCKED
            for capability in capabilities
        ):
            return f"all_{axis}_capabilities_blocked"
    return None


def _build_option_pool(
    *,
    inventory: PartyDevelopmentCheckpointInventory,
    context_catalog_payload: bytes,
    venue_registry: PartyDevelopmentVenuePriorRegistry,
    catalog_root: Path,
    rom_path: Path,
    excluded_roots: frozenset[str],
    excluded_states: frozenset[str],
    source_commit: str,
    source_bundle_sha256: str,
    completed_battles: int,
) -> tuple[tuple[_RedOptionRuntime, ...], dict[str, int]]:
    try:
        context_document = json.loads(context_catalog_payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RepeatablePartyOutcomeRunError(
            "repeatable development context catalog is invalid"
        ) from error
    context_source_commit = (
        context_document.get("source_commit") if isinstance(context_document, Mapping) else None
    )
    if not isinstance(context_source_commit, str):
        raise RepeatablePartyOutcomeRunError("repeatable development context source is invalid")
    historical_registry = load_committed_goal_manager_registry_at_revision(
        PROJECT_ROOT,
        context_source_commit,
    )
    context_catalog = parse_goal_manager_context_catalog(
        context_catalog_payload,
        historical_registry,
    )
    route_evidence = venue_registry.evidence_for(ROUTE_11_TRAINING_VENUE.band)
    cave_evidence = venue_registry.evidence_for(DIGLETTS_CAVE_TRAINING_VENUE.band)
    if route_evidence is None or cave_evidence is None:
        raise RepeatablePartyOutcomeRunError(
            "repeatable development lacks two executable venue priors"
        )
    areas = (ROUTE_11_TRAINING_VENUE.band, DIGLETTS_CAVE_TRAINING_VENUE.band)
    contracts = (
        _switch_assisted_venue_contract_sha256(
            route_evidence.operational_contract_sha256,
            completed_battles=completed_battles,
        ),
        _switch_assisted_venue_contract_sha256(
            cave_evidence.operational_contract_sha256,
            completed_battles=completed_battles,
        ),
    )
    evolutions = evolution_graph(rom_path.read_bytes())
    runtimes: list[_RedOptionRuntime] = []
    capability_rejected_roots: dict[str, set[str]] = {}
    for entry in inventory.entries:
        if (
            entry.checkpoint_id.startswith("red-party-pp-v1-")
            or entry.state_sha256 in excluded_states
            or not entry.controls_ready
            or entry.battle_active
            or sum(member.trainable for member in entry.members) < 2
        ):
            continue
        context_entry = context_catalog.entry(entry.checkpoint_id)
        root_lineage_id = context_entry.authenticated_root_lineage_id(
            slot_id=entry.checkpoint_id,
            capture_id=entry.checkpoint_id,
            state_sha256=entry.state_sha256,
            envelope_sha256=entry.envelope_sha256,
        )
        if root_lineage_id in excluded_roots:
            continue
        state_path, envelope_path, profile_path = _question_paths(
            catalog_root,
            entry.checkpoint_id,
        )
        capture = open_goal_manager_context_capture(state_path, envelope_path)
        profile = load_red_goal_context_profile(profile_path)
        with PyBoyAdapter(rom_path) as emulator:
            emulator.load_state_bytes(capture.state_bytes)
            reader = PokemonRedStateReader(emulator)
            runtime = build_red_goal_context_runtime(
                profile=profile,
                capture=capture,
                emulator=emulator,
                reader=reader,
            )
            observation = runtime.adapter.observe()
            last_blackout_map = reader.read_last_blackout_map()
            current_map_tileset = emulator.read_u8(RamAddress.CURRENT_MAP_TILESET)
        reject_entry = False
        for goal in entry.goal_hints:
            for kind in TrainingChoiceKind:
                option_id = f"repeatable-option-{entry.checkpoint_id}-{kind.value}-{goal.value}"
                reservation = _inventory_reservation(
                    entry,
                    option_id=option_id,
                    kind=kind,
                    goal=goal,
                )
                try:
                    snapshot = build_red_party_development_snapshot(
                        reservation,
                        source_root_lineage_id=root_lineage_id,
                        observation=observation,
                        evolutions=evolutions,
                        policy=RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY,
                        areas=areas,
                        venue_prior_registry=venue_registry,
                        venue_operational_contract_sha256=contracts,
                        source_commit=source_commit,
                        source_bundle_sha256=source_bundle_sha256,
                        training_venues=_TRAINING_VENUES,
                        transition_guards=RED_PARTY_DEVELOPMENT_TRANSITION_GUARDS,
                        last_blackout_map=last_blackout_map,
                        current_map_tileset=current_map_tileset,
                        venue_prior_feature_mode=(
                            VenuePriorFeatureMode.MASKED_UNCALIBRATED
                        ),
                        switch_assisted_battle_credit=True,
                    )
                    capability_code = _capability_root_rejection_code(snapshot)
                    if capability_code is not None:
                        capability_rejected_roots.setdefault(
                            capability_code,
                            set(),
                        ).add(root_lineage_id)
                        reject_entry = True
                        break
                    menu, venue_trainee = _menu_for_snapshot(snapshot, kind)
                except RedPartyDevelopmentExecutionCapabilityError as error:
                    if error.code == "adapter_contract_misaligned":
                        raise RepeatablePartyOutcomeRunError(
                            "repeatable development capability contract is misaligned"
                        ) from error
                    capability_rejected_roots.setdefault(error.code, set()).add(root_lineage_id)
                    reject_entry = True
                    break
                except (RuntimeError, ValueError):
                    continue
                if menu is None or sum(menu.candidate_available) < 2:
                    continue
                binding = snapshot.freeze_binding(menu, scenario_id=option_id)
                option = PartyDevelopmentScenarioOption(
                    option_id=option_id,
                    root_lineage_id=root_lineage_id,
                    initial_state_sha256=entry.state_sha256,
                    partition=entry.partition,
                    candidate_set=menu.candidate_set,
                    binding=binding,
                )
                runtimes.append(
                    _RedOptionRuntime(
                        option=option,
                        reservation=reservation,
                        capture=capture,
                        profile=profile,
                        snapshot=snapshot,
                        menu=menu,
                        venue_question_trainee=venue_trainee,
                        profile_file_sha256=hashlib.sha256(profile_path.read_bytes()).hexdigest(),
                    )
                )
            if reject_entry:
                break
    if not runtimes:
        raise RepeatablePartyOutcomeRunError(
            "repeatable development produced no genuine candidate menus"
        )
    return tuple(runtimes), {
        code: len(roots) for code, roots in sorted(capability_rejected_roots.items())
    }


def _selected_runtimes(
    plan: RepeatablePartyScenarioPlan,
    pool: tuple[_RedOptionRuntime, ...],
) -> tuple[_SelectedRuntime, ...]:
    by_option = {item.option.option_id: item for item in pool}
    selected = []
    for assignment in plan.assignments:
        runtime = by_option.get(assignment.option_id)
        if runtime is None or runtime.option.option_sha256 != assignment.option_sha256:
            raise RepeatablePartyOutcomeRunError(
                "repeatable development selection differs from its option pool"
            )
        permuted = permute_bound_party_development_menu(
            runtime.menu,
            assignment.candidate_order,
        )
        binding = runtime.snapshot.freeze_binding(
            permuted,
            scenario_id=assignment.scenario_id,
        )
        question = PartyDevelopmentFrozenQuestion(
            capture_id=runtime.capture.capture_id,
            capture_envelope_sha256=runtime.capture.envelope_sha256,
            profile_id=runtime.capture.capture_id,
            profile_file_sha256=runtime.profile_file_sha256,
            binding=binding,
            candidate_set=permuted.candidate_set,
        )
        selected.append(
            _SelectedRuntime(
                assignment=assignment,
                reservation=replace(
                    runtime.reservation,
                    scenario_id=assignment.scenario_id,
                ),
                capture=runtime.capture,
                profile=runtime.profile,
                snapshot=runtime.snapshot,
                menu=permuted,
                binding_question=question,
                venue_question_trainee=runtime.venue_question_trainee,
            )
        )
    return tuple(selected)


def _trial_assignments(
    selected: tuple[_SelectedRuntime, ...],
) -> dict[str, tuple[PartyDevelopmentOutcomeTrialAssignment, ...]]:
    ordinal = 0
    result: dict[str, tuple[PartyDevelopmentOutcomeTrialAssignment, ...]] = {}
    for runtime in selected:
        question = runtime.binding_question
        assignments = []
        for candidate in question.candidate_set.candidates:
            if not question.binding.candidate_available[candidate.candidate_index]:
                continue
            ordinal += 1
            assignments.append(
                PartyDevelopmentOutcomeTrialAssignment.build(
                    ordinal=ordinal,
                    scenario_id=question.scenario_id,
                    root_lineage_id=question.binding.root_lineage_id,
                    initial_state_sha256=question.binding.initial_state_sha256,
                    partition=question.binding.partition,
                    kind=question.binding.kind,
                    goal=question.binding.goal,
                    binding_sha256=question.binding.binding_sha256,
                    candidate_index=candidate.candidate_index,
                    candidate_sha256=canonical_sha256(candidate.public_dict()),
                    candidate_feature_sha256=(
                        question.binding.candidate_feature_sha256[candidate.candidate_index]
                    ),
                )
            )
        result[question.scenario_id] = tuple(assignments)
    return result


def _execution_ports(
    emulator: PyBoyAdapter,
    *,
    maximum_frames: int,
) -> _ExecutionPorts:
    return _ExecutionPorts(
        observation_emulator=emulator,
        controller=FrameBudgetEmulator(emulator, maximum_frames=maximum_frames),
        reader=PokemonRedStateReader(emulator),
        party_reader=PokemonRedPartyReader(emulator),
    )


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


def _require_randomization_preserves_question(
    runtime: _SelectedRuntime,
    *,
    observation: RedGoalObservation,
    evolutions: Mapping[int, tuple[Evolution, ...]],
    venue_registry: PartyDevelopmentVenuePriorRegistry,
    source_commit: str,
    source_bundle_sha256: str,
    last_blackout_map: int,
    current_map_tileset: int,
    completed_battles: int,
) -> None:
    route_evidence = venue_registry.evidence_for(ROUTE_11_TRAINING_VENUE.band)
    cave_evidence = venue_registry.evidence_for(DIGLETTS_CAVE_TRAINING_VENUE.band)
    if route_evidence is None or cave_evidence is None:
        raise RepeatablePartyOutcomeRunError(
            "repeatable development lost venue priors during execution"
        )
    delayed = build_red_party_development_snapshot(
        runtime.reservation,
        source_root_lineage_id=runtime.binding_question.binding.root_lineage_id,
        observation=observation,
        evolutions=evolutions,
        policy=RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY,
        areas=(ROUTE_11_TRAINING_VENUE.band, DIGLETTS_CAVE_TRAINING_VENUE.band),
        venue_prior_registry=venue_registry,
        venue_operational_contract_sha256=(
            _switch_assisted_venue_contract_sha256(
                route_evidence.operational_contract_sha256,
                completed_battles=completed_battles,
            ),
            _switch_assisted_venue_contract_sha256(
                cave_evidence.operational_contract_sha256,
                completed_battles=completed_battles,
            ),
        ),
        source_commit=source_commit,
        source_bundle_sha256=source_bundle_sha256,
        training_venues=_TRAINING_VENUES,
        transition_guards=RED_PARTY_DEVELOPMENT_TRANSITION_GUARDS,
        last_blackout_map=last_blackout_map,
        current_map_tileset=current_map_tileset,
        venue_prior_feature_mode=VenuePriorFeatureMode.MASKED_UNCALIBRATED,
        switch_assisted_battle_credit=True,
    )
    delayed_menu, delayed_trainee = _menu_for_snapshot(
        delayed,
        runtime.binding_question.binding.kind,
    )
    if delayed_menu is None:
        raise RepeatablePartyOutcomeRunError(
            "repeatable timing randomization removed the candidate menu"
        )
    delayed_menu = permute_bound_party_development_menu(
        delayed_menu,
        runtime.assignment.candidate_order,
    )
    if delayed_menu != runtime.menu or delayed_trainee != runtime.venue_question_trainee:
        raise RepeatablePartyOutcomeRunError(
            "repeatable timing randomization changed learner-visible semantics"
        )


def _execute_trial(
    *,
    runtime: _SelectedRuntime,
    assignment: PartyDevelopmentOutcomeTrialAssignment,
    binding: RedPartyDevelopmentTrialBinding,
    rom_path: Path,
    evolutions: Mapping[int, tuple[Evolution, ...]],
    venue_registry: PartyDevelopmentVenuePriorRegistry,
    dose: PartyDevelopmentOutcomeDose,
    source_commit: str,
    source_bundle_sha256: str,
    watch: bool,
) -> _TrialMeasurement:
    summaries: list[TeamTrainingExecutionSummary] = []
    policy = _switch_assisted_outcome_policy(dose)
    with PyBoyAdapter(
        rom_path,
        watch=watch,
        speed=2 if watch else None,
    ) as emulator:
        emulator.load_state_bytes(runtime.capture.state_bytes)
        if runtime.assignment.timing_offset_frames:
            emulator.tick(runtime.assignment.timing_offset_frames)
        ports = _execution_ports(emulator, maximum_frames=dose.maximum_frames)
        goal_runtime = build_red_goal_context_runtime(
            profile=runtime.profile,
            capture=runtime.capture,
            emulator=ports.observation_emulator,
            reader=ports.reader,
        )
        before_observation = goal_runtime.adapter.observe()
        last_blackout_map = ports.reader.read_last_blackout_map()
        current_map_tileset = ports.observation_emulator.read_u8(
            RamAddress.CURRENT_MAP_TILESET
        )
        _require_randomization_preserves_question(
            runtime,
            observation=before_observation,
            evolutions=evolutions,
            venue_registry=venue_registry,
            source_commit=source_commit,
            source_bundle_sha256=source_bundle_sha256,
            last_blackout_map=last_blackout_map,
            current_map_tileset=current_map_tileset,
            completed_battles=dose.completed_battles,
        )
        before_party = ports.party_reader.read()
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
            ports.reader,
            ports.observation_emulator,
            policy=policy,
            intent=MANSION_BALANCED_TEAM_TRAINING_INTENT,
            flee_timing=MANSION_TRAINING_FLEE_TIMING,
            hideout_timing=DEFAULT_HIDEOUT_TIMING,
            flee_func=_flee,  # type: ignore[arg-type]
            volatile_enemy_species=MANSION_VOLATILE_ENEMY_SPECIES,
            escort_enemy_species=MANSION_ESCORT_ENEMY_SPECIES,
            max_consecutive_flees=MANSION_MAX_CONSECUTIVE_FLEES,
            cancel_interval=MANSION_LEVEL_UP_MOVE_CANCEL_INTERVAL,
            execution_summary_sink=summaries.append,
            venues=_TRAINING_VENUES,
            report_label="repeatable completion-aware party development",
            checkpoint_count=1,
            fixed_dose=binding.fixed_dose,
        )
        if len(summaries) != 1:
            raise RepeatablePartyOutcomeRunError(
                "repeatable development did not retain one execution summary"
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
            raise RepeatablePartyOutcomeRunError(
                "repeatable development lost its unique trainee lineage"
            )
        after_target = after_targets[0]
        after_completion = red_party_completion_snapshot(
            after_observation,
            evolutions=evolutions,
            policy=RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY,
        )
        trial = PartyDevelopmentOutcomeTrialV2(
            candidate=runtime.binding_question.candidate_set.candidates[assignment.candidate_index],
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
        partial = adapt_party_development_outcomes_v2(
            runtime.binding_question.candidate_set,
            (trial,),
            scenario_id=runtime.binding_question.scenario_id,
            root_lineage_id=runtime.binding_question.binding.root_lineage_id,
            initial_state_sha256=(runtime.binding_question.binding.initial_state_sha256),
            partition=runtime.binding_question.binding.partition,
            prospective_binding=runtime.binding_question.binding,
        )
        outcome = partial.outcomes[assignment.candidate_index]
        if not isinstance(outcome, CandidateOutcome) or not outcome.measured:
            raise RepeatablePartyOutcomeRunError(
                "repeatable development trial produced no measured outcome"
            )
        evidence = {
            "schema": "pokemon.red.repeatable-party-development-trial-evidence.v1",
            "scenario_id": runtime.binding_question.scenario_id,
            "trial_id": assignment.trial_id,
            "assignment_sha256": assignment.assignment_sha256,
            "candidate_index": assignment.candidate_index,
            "timing_offset_frames": runtime.assignment.timing_offset_frames,
            "before_party": _party_evidence(before_party),
            "after_party": _party_evidence(after_party),
            "before_completion": before_completion.public_dict(),
            "after_completion": after_completion.public_dict(),
            "execution": summary.public_dict(),
            "criterion_values": list(outcome.criterion_values),
            "controller_actions": actions.actions_executed,
            "frames_executed": ports.controller.frames_executed,
            "teacher_queries": 0,
            "model_predictions": 0,
            "model_updates": 0,
            "private_path_fields": 0,
        }
        return _TrialMeasurement(
            outcome=replace(
                outcome,
                evidence_sha256=canonical_sha256(evidence),
            ),
            private_evidence=evidence,
            controller_actions=actions.actions_executed,
            frames_executed=ports.controller.frames_executed,
        )


def _invalid_outcome(error: BaseException) -> tuple[CandidateOutcome, dict[str, object]]:
    message = str(error)
    evidence = {
        "schema": "pokemon.red.repeatable-party-development-trial-failure.v1",
        "status": "invalid",
        "failure_type": type(error).__name__,
        "failure_message": message,
        "failure_message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
        "retryable_development_evidence": True,
        "teacher_queries": 0,
        "model_predictions": 0,
        "model_updates": 0,
        "private_path_fields": 0,
    }
    return (
        CandidateOutcome(
            OutcomeEvidenceStatus.INVALID,
            evidence_sha256=canonical_sha256(evidence),
        ),
        evidence,
    )


def _assemble_examples(
    selected: tuple[_SelectedRuntime, ...],
    outcomes_by_scenario: Mapping[str, Mapping[int, CandidateOutcome]],
) -> tuple[ScenarioOutcomeExample, ...]:
    examples = []
    for runtime in selected:
        question = runtime.binding_question
        measured = outcomes_by_scenario.get(question.scenario_id, {})
        examples.append(
            ScenarioOutcomeExample(
                scenario_id=question.scenario_id,
                root_lineage_id=question.binding.root_lineage_id,
                initial_state_sha256=question.binding.initial_state_sha256,
                partition=question.binding.partition,
                objective=PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE,
                feature_schema_id=question.binding.feature_schema_id,
                feature_names=PARTY_DEVELOPMENT_FEATURE_NAMES,
                candidates=tuple(
                    OutcomeCandidate(
                        candidate_index=candidate.candidate_index,
                        features=candidate.features,
                        available=question.binding.candidate_available[candidate.candidate_index],
                    )
                    for candidate in question.candidate_set.candidates
                ),
                outcomes=tuple(
                    measured.get(candidate.candidate_index)
                    if question.binding.candidate_available[candidate.candidate_index]
                    else None
                    for candidate in question.candidate_set.candidates
                ),
                prospective_binding_sha256=question.binding.binding_sha256,
            )
        )
    return tuple(examples)


def _pool_summary(
    pool: tuple[_RedOptionRuntime, ...],
    *,
    capability_rejected_root_counts: Mapping[str, int],
) -> dict[str, object]:
    roots_by_partition = {
        partition.value: len(
            {item.option.root_lineage_id for item in pool if item.option.partition is partition}
        )
        for partition in (ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT)
    }
    return {
        "option_count": len(pool),
        "independent_root_counts": roots_by_partition,
        "kind_counts": dict(
            sorted(
                Counter(
                    f"{item.option.partition.value}:{item.option.candidate_set.kind.value}"
                    for item in pool
                ).items()
            )
        ),
        "goal_counts": dict(
            sorted(
                Counter(
                    f"{item.option.partition.value}:{item.option.candidate_set.goal.value}"
                    for item in pool
                ).items()
            )
        ),
        "candidate_widths": sorted({item.option.available_candidate_count for item in pool}),
        "unavailable_reason_counts": dict(
            sorted(
                Counter(
                    reason.value
                    for item in pool
                    for reason in item.menu.candidate_unavailable_reasons
                    if reason is not None
                ).items()
            )
        ),
        "capability_rejected_root_counts": dict(capability_rejected_root_counts),
        "candidate_feature_values_public": False,
        "private_path_fields": 0,
    }


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.execute and args.private_artifact_root is None:
        raise RepeatablePartyOutcomeRunError(
            "repeatable development execution needs a private artifact root"
        )
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    if source.git_commit is None:
        raise RepeatablePartyOutcomeRunError(
            "repeatable development needs a committed source ancestor"
        )
    source_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    inventory_path = _require_external(args.inventory, subject="inventory")
    context_path = _require_external(args.context_catalog, subject="context catalog")
    venue_path = _require_external(
        args.venue_prior_registry,
        subject="venue-prior registry",
    )
    prior_path = _require_external(
        args.prior_reservation_plan,
        subject="prior reservation plan",
    )
    catalog_root = _require_external(args.catalog_root, subject="catalog root")
    inventory_document, inventory_file_sha = _load_json(
        inventory_path,
        subject="inventory",
    )
    venue_document, venue_file_sha = _load_json(
        venue_path,
        subject="venue-prior registry",
    )
    prior_document, prior_file_sha = _load_json(
        prior_path,
        subject="prior reservation plan",
    )
    inventory = PartyDevelopmentCheckpointInventory.from_private_dict(inventory_document)
    venue_registry = PartyDevelopmentVenuePriorRegistry.from_private_dict(venue_document)
    prior_plan = PartyDevelopmentQuestionReservationPlan.from_private_dict(prior_document)
    artifact_exclusions = tuple(
        _development_artifact_exclusion(path) for path in args.exclude_development_artifact
    )
    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    manual_consumed_roots = frozenset(args.exclude_root_lineage_id)
    artifact_roots = frozenset(
        root for exclusion in artifact_exclusions for root in exclusion.root_lineage_ids
    )
    excluded_roots = frozenset(
        (
            *prior_plan.excluded_root_lineage_ids,
            *manual_consumed_roots,
            *artifact_roots,
        )
    )
    excluded_states = frozenset(
        (
            *prior_plan.excluded_state_sha256,
            *(
                state
                for exclusion in artifact_exclusions
                for state in exclusion.initial_state_sha256
            ),
        )
    )
    pool, capability_rejected_root_counts = _build_option_pool(
        inventory=inventory,
        context_catalog_payload=context_path.read_bytes(),
        venue_registry=venue_registry,
        catalog_root=catalog_root,
        rom_path=rom_path,
        excluded_roots=excluded_roots,
        excluded_states=excluded_states,
        source_commit=source.git_commit,
        source_bundle_sha256=source_bundle,
        completed_battles=args.completed_battles,
    )
    plan = select_repeatable_party_scenarios(
        tuple(item.option for item in pool),
        train_count=args.train_count,
        development_count=args.development_count,
        seed=args.seed,
        maximum_timing_offset_frames=args.maximum_timing_offset_frames,
    )
    selected = _selected_runtimes(plan, pool)
    assignments = _trial_assignments(selected)
    base_receipt: dict[str, object] = {
        "schema": "pokemon.red.repeatable-party-development-receipt.v1",
        "status": "ready" if not args.execute else "executing",
        "active_lane": _DEVELOPMENT_LANE_ID,
        "source_commit": source.git_commit,
        "source_bundle_sha256": source_bundle,
        "input_file_sha256": {
            "inventory": inventory_file_sha,
            "context_catalog": hashlib.sha256(context_path.read_bytes()).hexdigest(),
            "venue_prior_registry": venue_file_sha,
            "prior_reservation_plan": prior_file_sha,
            "excluded_development_artifact_manifests": sorted(
                exclusion.manifest_sha256 for exclusion in artifact_exclusions
            ),
        },
        "rom": fingerprint.public_dict(),
        "scenario_pool": _pool_summary(
            pool,
            capability_rejected_root_counts=capability_rejected_root_counts,
        ),
        "plan": plan.public_dict(),
        "plan_sha256": plan.plan_sha256,
        "question_count": len(selected),
        "candidate_trial_count": sum(len(value) for value in assignments.values()),
        "excluded_prior_root_count": len(prior_plan.excluded_root_lineage_ids),
        "excluded_consumed_root_count": len(manual_consumed_roots),
        "excluded_development_artifact_count": len(artifact_exclusions),
        "excluded_development_artifact_root_count": len(artifact_roots),
        "excluded_total_unique_root_count": len(excluded_roots),
        "excluded_development_plan_sha256": sorted(
            exclusion.plan_sha256 for exclusion in artifact_exclusions
        ),
        "development_repeatable": True,
        "battle_credit_protocol": _battle_credit_protocol(args.completed_battles),
        "teacher_queries": 0,
        "teacher_choice_targets": 0,
        "model_predictions": 0,
        "model_fits": 0,
        "authority_promoted": False,
        "sealed_red_cases_opened": 0,
        "crystal_cases_opened": 0,
        "full_game_replays": 0,
        "private_path_fields": 0,
    }
    if not args.execute:
        base_receipt.update(
            {
                "controller_actions": 0,
                "measured_trials": 0,
                "invalid_trials": 0,
                "complete_questions": 0,
                "learner_update_eligible_questions": 0,
            }
        )
        return base_receipt

    private_root = open_private_root(
        _require_external(args.private_artifact_root, subject="artifact root"),
        repository_root=PROJECT_ROOT,
    )
    artifact_id = f"repeatable-party-development-{uuid.uuid4().hex}"
    writer = private_root.begin_artifact(
        artifact_id,
        kind="repeatable_party_outcome_development",
    )
    dose = PartyDevelopmentOutcomeDose(
        completed_battles=args.completed_battles,
        maximum_encounter_steps=1_200,
        maximum_controller_actions=50_000,
        maximum_frames=750_000,
        maximum_healing_trips=3,
        maximum_rotations=8,
        maximum_faints=0,
    )
    evolutions = evolution_graph(rom_path.read_bytes())
    species_mapping = internal_to_dex(rom_path.read_bytes())
    outcomes_by_scenario: dict[str, dict[int, CandidateOutcome]] = {}
    measured_trials = invalid_trials = controller_actions = frames_executed = 0
    with writer:
        writer.append(
            "plan",
            {
                "record_type": "repeatable_party_development_plan",
                "plan": plan.public_dict(),
                "plan_sha256": plan.plan_sha256,
                "dose": dose.public_dict(),
                "source": source.public_dict(),
                "source_bundle_sha256": source_bundle,
                "rom_sha256": fingerprint.sha256,
                "inputs": base_receipt["input_file_sha256"],
                "development_repeatable": True,
                "battle_credit_protocol": _battle_credit_protocol(dose.completed_battles),
                "sealed": False,
            },
        )
        for runtime in selected:
            scenario_outcomes = outcomes_by_scenario.setdefault(
                runtime.binding_question.scenario_id,
                {},
            )
            question_assignments = assignments[runtime.binding_question.scenario_id]
            for trial_assignment in question_assignments:
                try:
                    trial_binding = bind_red_party_development_outcome_trial(
                        runtime.binding_question,
                        runtime.menu,
                        trial_assignment,
                        party=runtime.snapshot.party,
                        venue_question_trainee=runtime.venue_question_trainee,
                        training_venues=_TRAINING_VENUES,
                        evolutions=evolutions,
                        internal_to_national=species_mapping,
                        dose=dose,
                    )
                    measurement = _execute_trial(
                        runtime=runtime,
                        assignment=trial_assignment,
                        binding=trial_binding,
                        rom_path=rom_path,
                        evolutions=evolutions,
                        venue_registry=venue_registry,
                        dose=dose,
                        source_commit=source.git_commit,
                        source_bundle_sha256=source_bundle,
                        watch=args.watch,
                    )
                    scenario_outcomes[trial_assignment.candidate_index] = measurement.outcome
                    measured_trials += 1
                    controller_actions += measurement.controller_actions
                    frames_executed += measurement.frames_executed
                    writer.append(
                        "outcomes",
                        {
                            "record_type": "repeatable_party_candidate_outcome",
                            "assignment": trial_assignment.private_dict(),
                            "evidence": dict(measurement.private_evidence),
                            "outcome": {
                                "status": measurement.outcome.status.value,
                                "criterion_values": list(measurement.outcome.criterion_values),
                                "evidence_sha256": (measurement.outcome.evidence_sha256),
                            },
                        },
                    )
                except Exception as error:
                    invalid, evidence = _invalid_outcome(error)
                    scenario_outcomes[trial_assignment.candidate_index] = invalid
                    invalid_trials += 1
                    writer.append(
                        "failures",
                        {
                            "record_type": "repeatable_party_candidate_failure",
                            "assignment": trial_assignment.private_dict(),
                            "evidence": evidence,
                        },
                    )
        examples = _assemble_examples(selected, outcomes_by_scenario)
        prospective = PartyDevelopmentProspectiveCatalog.freeze(
            tuple(item.binding_question.binding for item in selected)
        )
        audit = audit_party_development_outcome_catalog(
            examples,
            prospective_catalog=prospective,
            policy=PartyDevelopmentReadinessPolicy(
                minimum_train_examples=args.train_count,
                minimum_development_examples=args.development_count,
                minimum_goals_per_partition=2,
                minimum_candidate_count_observed=3,
                minimum_health_bins=2,
                minimum_pp_bins=1,
                minimum_survival_bins=2,
                minimum_evolution_route_kinds=2,
                minimum_semantic_menus_per_partition=min(
                    3,
                    args.development_count,
                ),
                require_complete_venue_priors=False,
            ),
        )
        writer.append(
            "evaluation",
            {
                "record_type": "repeatable_party_development_audit",
                "audit": audit.public_dict(),
                "model_fit": False,
                "authority_promoted": False,
            },
        )

    complete_questions = sum(item.fully_measured for item in examples)
    eligible_questions = sum(item.learner_update_eligible for item in examples)
    partition_eligible = Counter(
        item.partition.value for item in examples if item.learner_update_eligible
    )
    base_receipt.update(
        {
            "status": (
                "complete"
                if invalid_trials == 0 and complete_questions == len(selected)
                else "complete_with_invalid_trials"
            ),
            "artifact": writer.summary.public_dict(),
            "dose": dose.public_dict(),
            "measured_trials": measured_trials,
            "invalid_trials": invalid_trials,
            "complete_questions": complete_questions,
            "learner_update_eligible_questions": eligible_questions,
            "partition_eligible_questions": dict(sorted(partition_eligible.items())),
            "controller_actions": controller_actions,
            "frames_executed": frames_executed,
            "audit": audit.public_dict(),
        }
    )
    return base_receipt


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        result = _run(parser.parse_args(argv))
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        parser.error(f"repeatable party development failed closed: {error}")
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
